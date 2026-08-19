"""Editeur de masque 2D (pinceau/gomme/fill/clear/invert/undo/redo).

Toute la logique de masque vit dans `MaskEditController` (pur NumPy). Ce
module ne fait que : afficher l'overlay, traduire les evenements souris en
coordonnees image et appeler le controleur en consequence.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lithoshape3d.ui.mask_edit_controller import MaskEditController
from lithoshape3d.ui.overlay import render_overlay


class _MaskCanvas(QWidget):
    def __init__(self, controller: MaskEditController, base_image: np.ndarray, color, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.base_image = base_image  # float32 [0,1], jamais modifie
        self.color = color
        self.brush_radius = 12
        self.tool = "brush"

        self.setMinimumSize(320, 320)
        self.setMouseTracking(True)
        self._painting = False
        self._draw_origin = (0, 0)
        self._draw_scale = 1.0
        self._pixmap = None
        self.refresh()

    def refresh(self) -> None:
        self._pixmap = render_overlay(self.base_image, self.controller.mask, self.color, alpha=0.5)
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

    def _widget_to_image_xy(self, pos) -> tuple[int, int]:
        ox, oy = self._draw_origin
        scale = self._draw_scale or 1.0
        image_x = int((pos.x() - ox) / scale)
        image_y = int((pos.y() - oy) / scale)
        return image_x, image_y

    def _paint_at(self, pos) -> None:
        x, y = self._widget_to_image_xy(pos)
        radius = max(1, int(self.brush_radius / (self._draw_scale or 1.0)))
        value = 1.0 if self.tool == "brush" else 0.0
        self.controller.paint(x, y, radius, value)
        self.refresh()

    def mousePressEvent(self, event) -> None:
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
    def __init__(self, zone_name: str, base_image: np.ndarray, initial_mask: np.ndarray, color, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Editer le masque - {zone_name}")
        self.resize(760, 640)

        self.controller = MaskEditController(initial_mask)
        self.canvas = _MaskCanvas(self.controller, base_image, color)

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
        layout.addWidget(self.canvas, 1)

        self.close_button = QPushButton("Fermer")
        self.close_button.clicked.connect(self.accept)
        layout.addWidget(self.close_button)

        self.addAction(_shortcut_action(self, QKeySequence.StandardKey.Undo, self._on_undo))
        self.addAction(_shortcut_action(self, QKeySequence.StandardKey.Redo, self._on_redo))

    def _set_tool(self, tool: str) -> None:
        self.canvas.tool = tool
        self.brush_button.setChecked(tool == "brush")
        self.eraser_button.setChecked(tool == "eraser")

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


def _shortcut_action(parent, standard_key, callback):
    from PySide6.QtGui import QAction

    action = QAction(parent)
    action.setShortcut(QKeySequence(standard_key))
    action.triggered.connect(callback)
    return action
