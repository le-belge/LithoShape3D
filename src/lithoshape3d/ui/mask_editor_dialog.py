"""Editeur de masque 2D (pinceau/gomme/fill/clear/invert/undo/redo + selection
intelligente optionnelle).

Toute la logique de masque vit dans `MaskEditController` (pur NumPy). Ce
module ne fait que : afficher l'overlay, traduire les evenements souris en
coordonnees image et appeler le controleur (ou un backend de segmentation)
en consequence. Le resultat d'une selection intelligente est applique comme
n'importe quel autre masque -- il reste ensuite modifiable au pinceau/gomme.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lithoshape3d.ai.segmentation.base import SegmentationBackend, SegmentationPrompt
from lithoshape3d.ui.mask_edit_controller import MaskEditController
from lithoshape3d.ui.overlay import render_overlay
from lithoshape3d.ui.segmentation_worker import (
    DownloadModelWorker,
    PrepareSessionWorker,
    SegmentWorker,
)

logger = logging.getLogger("lithoshape3d.ui.mask_editor")

_POSITIVE_COLOR = QColor(80, 220, 120)
_NEGATIVE_COLOR = QColor(220, 80, 80)


class _MaskCanvas(QWidget):
    ai_point_added = Signal(float, float, bool)  # x, y (coords image), is_positive

    def __init__(self, controller: MaskEditController, base_image: np.ndarray, color, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.base_image = base_image  # float32 [0,1], jamais modifie
        self.color = color
        self.brush_radius = 12
        self.tool = "brush"

        self.preview_mask: np.ndarray | None = None
        self.preview_points: list[tuple[float, float, bool]] = []

        self.setMinimumSize(320, 320)
        self.setMouseTracking(True)
        self._painting = False
        self._draw_origin = (0, 0)
        self._draw_scale = 1.0
        self._pixmap = None
        self.refresh()

    def refresh(self) -> None:
        mask = self.preview_mask if self.preview_mask is not None else self.controller.mask
        self._pixmap = render_overlay(self.base_image, mask, self.color, alpha=0.5)
        self.update()

    def set_preview(self, mask: np.ndarray | None) -> None:
        self.preview_mask = mask
        self.refresh()

    def set_preview_points(self, points: list[tuple[float, float, bool]]) -> None:
        self.preview_points = points
        self.update()

    def paintEvent(self, event) -> None:
        if self._pixmap is None:
            return
        scaled = self._pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        self._draw_origin = (x, y)
        self._draw_scale = scaled.width() / self.base_image.shape[1] if self.base_image.shape[1] else 1.0
        painter = QPainter(self)
        painter.drawPixmap(x, y, scaled)

        if self.tool == "ai" and self.preview_points:
            for px, py, is_positive in self.preview_points:
                wx = x + px * self._draw_scale
                wy = y + py * self._draw_scale
                color = _POSITIVE_COLOR if is_positive else _NEGATIVE_COLOR
                painter.setPen(QPen(color, 2))
                painter.setBrush(color)
                painter.drawEllipse(int(wx) - 4, int(wy) - 4, 8, 8)

    def _widget_to_image_xy(self, pos) -> tuple[float, float]:
        ox, oy = self._draw_origin
        scale = self._draw_scale or 1.0
        image_x = (pos.x() - ox) / scale
        image_y = (pos.y() - oy) / scale
        return image_x, image_y

    def _paint_at(self, pos) -> None:
        x, y = self._widget_to_image_xy(pos)
        radius = max(1, int(self.brush_radius / (self._draw_scale or 1.0)))
        value = 1.0 if self.tool == "brush" else 0.0
        self.controller.paint(int(x), int(y), radius, value)
        self.refresh()

    def mousePressEvent(self, event) -> None:
        if self.tool == "ai":
            if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
                x, y = self._widget_to_image_xy(event.position().toPoint())
                is_negative = (
                    event.button() == Qt.MouseButton.RightButton
                    or bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
                )
                self.ai_point_added.emit(x, y, not is_negative)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self._painting = True
            self.controller.begin_stroke()
            self._paint_at(event.position().toPoint())

    def mouseMoveEvent(self, event) -> None:
        if self._painting:
            self._paint_at(event.position().toPoint())

    def mouseReleaseEvent(self, event) -> None:
        if self._painting:
            self._painting = False
            self.controller.end_stroke()
            self.refresh()


class MaskEditorDialog(QDialog):
    def __init__(
        self,
        zone_name: str,
        base_image: np.ndarray,
        initial_mask: np.ndarray,
        color,
        segmentation_backend: SegmentationBackend | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Editer le masque - {zone_name}")
        self.resize(760, 680)

        self.controller = MaskEditController(initial_mask)
        self.canvas = _MaskCanvas(self.controller, base_image, color)
        self.canvas.ai_point_added.connect(self._on_ai_point_added)

        self._segmentation_backend = segmentation_backend
        self._segmentation_session = None
        self._thread_pool = QThreadPool.globalInstance()
        self._ai_points: list[tuple[float, float, bool]] = []

        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()

        self.brush_button = QPushButton("Pinceau")
        self.brush_button.setCheckable(True)
        self.brush_button.setChecked(True)
        self.brush_button.clicked.connect(lambda: self._set_tool("brush"))
        toolbar.addWidget(self.brush_button)

        self.eraser_button = QPushButton("Gomme")
        self.eraser_button.setCheckable(True)
        self.eraser_button.clicked.connect(lambda: self._set_tool("eraser"))
        toolbar.addWidget(self.eraser_button)

        self.ai_button = QPushButton("Selection intelligente")
        self.ai_button.setCheckable(True)
        self.ai_button.clicked.connect(lambda: self._set_tool("ai"))
        self.ai_button.setEnabled(segmentation_backend is not None)
        if segmentation_backend is None:
            self.ai_button.setToolTip("Selection intelligente indisponible (dependance IA non installee)")
        elif segmentation_backend.is_available():
            self.ai_button.setToolTip("Clic gauche = point positif, clic droit/Option+clic = point negatif")
        else:
            self.ai_button.setToolTip("Clic pour telecharger le modele de selection intelligente (~95 Mo)")
        toolbar.addWidget(self.ai_button)

        toolbar.addWidget(QLabel("Taille"))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 300)
        self.size_spin.setValue(self.canvas.brush_radius)
        self.size_spin.valueChanged.connect(self._on_size_changed)
        toolbar.addWidget(self.size_spin)

        self.clear_button = QPushButton("Effacer tout")
        self.clear_button.clicked.connect(self._on_clear)
        toolbar.addWidget(self.clear_button)

        self.fill_button = QPushButton("Remplir tout")
        self.fill_button.clicked.connect(self._on_fill)
        toolbar.addWidget(self.fill_button)

        self.invert_button = QPushButton("Inverser")
        self.invert_button.clicked.connect(self._on_invert)
        toolbar.addWidget(self.invert_button)

        self.undo_button = QPushButton("Annuler")
        self.undo_button.clicked.connect(self._on_undo)
        toolbar.addWidget(self.undo_button)

        self.redo_button = QPushButton("Retablir")
        self.redo_button.clicked.connect(self._on_redo)
        toolbar.addWidget(self.redo_button)

        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.ai_toolbar = QWidget()
        ai_layout = QHBoxLayout(self.ai_toolbar)
        ai_layout.setContentsMargins(0, 0, 0, 0)
        self.ai_status_label = QLabel("")
        ai_layout.addWidget(self.ai_status_label)
        ai_layout.addStretch(1)
        self.ai_undo_point_button = QPushButton("Annuler dernier point")
        self.ai_undo_point_button.clicked.connect(self._on_ai_undo_point)
        ai_layout.addWidget(self.ai_undo_point_button)
        self.ai_reset_button = QPushButton("Reinitialiser points")
        self.ai_reset_button.clicked.connect(self._on_ai_reset)
        ai_layout.addWidget(self.ai_reset_button)
        self.ai_apply_button = QPushButton("Appliquer")
        self.ai_apply_button.setObjectName("generateButton")
        self.ai_apply_button.clicked.connect(self._on_ai_apply)
        ai_layout.addWidget(self.ai_apply_button)
        self.ai_toolbar.setVisible(False)
        layout.addWidget(self.ai_toolbar)

        layout.addWidget(self.canvas, 1)

        self.close_button = QPushButton("Fermer")
        self.close_button.clicked.connect(self.accept)
        layout.addWidget(self.close_button)

        self.addAction(_shortcut_action(self, QKeySequence.StandardKey.Undo, self._on_undo))
        self.addAction(_shortcut_action(self, QKeySequence.StandardKey.Redo, self._on_redo))

    # ------------------------------------------------------------------ #
    # Outils pinceau/gomme/global
    # ------------------------------------------------------------------ #
    def _set_tool(self, tool: str) -> None:
        if tool == "ai" and self._segmentation_backend is not None and not self._segmentation_backend.is_available():
            self.ai_button.setChecked(False)
            self._offer_model_download()
            return

        self.canvas.tool = tool
        self.brush_button.setChecked(tool == "brush")
        self.eraser_button.setChecked(tool == "eraser")
        self.ai_button.setChecked(tool == "ai")
        self.ai_toolbar.setVisible(tool == "ai")
        if tool == "ai" and self._segmentation_session is None and self._segmentation_backend is not None:
            self._prepare_ai_session()

    def _on_size_changed(self, value: int) -> None:
        self.canvas.brush_radius = value

    def _on_clear(self) -> None:
        self.controller.clear()
        self.canvas.refresh()

    def _on_fill(self) -> None:
        self.controller.fill()
        self.canvas.refresh()

    def _on_invert(self) -> None:
        self.controller.invert()
        self.canvas.refresh()

    def _on_undo(self) -> None:
        self.controller.undo()
        self.canvas.refresh()

    def _on_redo(self) -> None:
        self.controller.redo()
        self.canvas.refresh()

    def resulting_mask(self) -> np.ndarray:
        return self.controller.mask.copy()

    # ------------------------------------------------------------------ #
    # Selection intelligente
    # ------------------------------------------------------------------ #
    def _offer_model_download(self) -> None:
        from lithoshape3d.ai.segmentation.model_cache import APPROX_SIZE_MB, LICENSE

        reply = QMessageBox.question(
            self,
            "Selection intelligente",
            f"Le modele de selection intelligente (SAM2, licence {LICENSE}, "
            f"~{APPROX_SIZE_MB} Mo) n'est pas encore installe.\n\n"
            "Le telecharger maintenant ? Il sera conserve dans un cache local "
            "et reutilise ensuite : aucune image n'est jamais envoyee en ligne.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.ai_toolbar.setVisible(True)
        self.ai_status_label.setText("Telechargement du modele en cours...")
        self.ai_button.setEnabled(False)
        worker = DownloadModelWorker()
        worker.signals.finished.connect(self._on_model_downloaded)
        worker.signals.failed.connect(self._on_model_download_failed)
        self._thread_pool.start(worker)

    def _on_model_downloaded(self) -> None:
        self.ai_button.setEnabled(True)
        self.ai_button.setToolTip("Clic gauche = point positif, clic droit/Option+clic = point negatif")
        self.ai_status_label.setText("Modele installe.")
        self._set_tool("ai")

    def _on_model_download_failed(self, message: str) -> None:
        self.ai_button.setEnabled(True)
        self.ai_toolbar.setVisible(False)
        logger.error("Telechargement du modele echoue : %s", message)
        QMessageBox.warning(
            self,
            "Selection intelligente",
            "Le telechargement du modele a echoue. Vous pouvez continuer "
            "avec l'edition manuelle (pinceau/gomme).",
        )

    def _prepare_ai_session(self) -> None:
        self.ai_status_label.setText("Analyse de l'image...")
        self.ai_apply_button.setEnabled(False)
        worker = PrepareSessionWorker(self._segmentation_backend, self.canvas.base_image)
        worker.signals.session_ready.connect(self._on_ai_session_ready)
        worker.signals.failed.connect(self._on_ai_failed)
        self._thread_pool.start(worker)

    def _on_ai_session_ready(self, session) -> None:
        self._segmentation_session = session
        self.ai_status_label.setText("Cliquez sur l'image pour selectionner un element.")

    def _on_ai_point_added(self, x: float, y: float, is_positive: bool) -> None:
        self._ai_points.append((x, y, is_positive))
        self.canvas.set_preview_points(self._ai_points)
        self._run_ai_segmentation()

    def _on_ai_undo_point(self) -> None:
        if self._ai_points:
            self._ai_points.pop()
        self.canvas.set_preview_points(self._ai_points)
        if self._ai_points:
            self._run_ai_segmentation()
        else:
            self.canvas.set_preview(None)
            self.ai_apply_button.setEnabled(False)

    def _on_ai_reset(self) -> None:
        self._ai_points = []
        self.canvas.set_preview_points([])
        self.canvas.set_preview(None)
        self.ai_apply_button.setEnabled(False)

    def _run_ai_segmentation(self) -> None:
        if self._segmentation_session is None:
            return
        prompt = SegmentationPrompt(
            positive_points=[(x, y) for x, y, positive in self._ai_points if positive],
            negative_points=[(x, y) for x, y, positive in self._ai_points if not positive],
        )
        self.ai_status_label.setText("Calcul du masque...")
        worker = SegmentWorker(self._segmentation_session, prompt)
        worker.signals.mask_ready.connect(self._on_ai_mask_ready)
        worker.signals.failed.connect(self._on_ai_failed)
        self._thread_pool.start(worker)

    def _on_ai_mask_ready(self, mask: np.ndarray) -> None:
        self.canvas.set_preview(mask)
        self.ai_status_label.setText("Proposition prete. Ajustez les points ou cliquez Appliquer.")
        self.ai_apply_button.setEnabled(True)

    def _on_ai_failed(self, message: str) -> None:
        logger.error("Selection intelligente : %s", message)
        self.ai_status_label.setText("Selection intelligente indisponible pour cette action.")
        self.ai_apply_button.setEnabled(False)

    def _on_ai_apply(self) -> None:
        if self.canvas.preview_mask is None:
            return
        self.controller.apply_external_mask((self.canvas.preview_mask >= 0.5).astype(np.float32))
        self._on_ai_reset()
        self._set_tool("brush")
        self.canvas.refresh()


def _shortcut_action(parent, standard_key, callback):
    from PySide6.QtGui import QAction

    action = QAction(parent)
    action.setShortcut(QKeySequence(standard_key))
    action.triggered.connect(callback)
    return action
