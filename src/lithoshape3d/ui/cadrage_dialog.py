"""Mode "Cadrer la photo" (Shape Composer, v0.4) : la Shape reste fixe, la
photo se deplace derriere. Glisser = deplacer, molette = zoomer,
Remplir/Ajuster/Centrer/Reinitialiser pour les cadrages courants.

Purement une vue -- ne recalcule jamais de mesh ni de validation manifold
pendant le glissement (cf. 2.3/2.20) : seul `ImageTransform` (offset/scale/
rotation, fractions [-1,1]/facteur/degres) change en temps reel, la
composition 3D ne se declenche qu'au clic explicite sur "Generer" dans la
fenetre principale, comme pour tout autre changement de parametre."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lithoshape3d.core.image.preprocessing import resize_array
from lithoshape3d.core.image.transform import apply_image_transform, fill_scale_relative_to_fit
from lithoshape3d.core.scene.models import ImageTransform

_PREVIEW_MAX_SIDE = 420
_OUTSIDE_DARKEN_FACTOR = 0.25
_ZOOM_BUTTON_STEP_PERCENT = 5
"""Pas (en %) applique par les boutons +/- -- volontairement plus large
que le pas molette (retour terrain : la molette seule est trop brutale
pour un ajustement fin ; les boutons offrent l'inverse, un pas net et
previsible sans avoir a compter les crans de molette)."""


class _CadragePreviewWidget(QWidget):
    transform_changed = Signal(object)  # ImageTransform

    def __init__(self, source_array: np.ndarray, shape_mask: np.ndarray, parent=None) -> None:
        super().__init__(parent)
        self._source = source_array
        self._shape_mask = shape_mask
        self.transform = ImageTransform()
        self.setMinimumSize(280, 280)
        self.setMouseTracking(True)
        self._pixmap: QPixmap | None = None
        self._draw_rect = (0, 0, 1, 1)
        self._dragging = False
        self._drag_start = QPointF()
        self._drag_start_offset = (0.0, 0.0)
        self._refresh()

    @property
    def shape_mask(self) -> np.ndarray:
        return self._shape_mask

    def set_transform(self, transform: ImageTransform) -> None:
        self.transform = transform
        self._refresh()

    def _refresh(self) -> None:
        rows, cols = self._shape_mask.shape
        composed = apply_image_transform(self._source, self.transform, cols, rows, fill_value=1.0)
        darkened = np.where(self._shape_mask, composed, composed * _OUTSIDE_DARKEN_FACTOR)
        array_u8 = np.ascontiguousarray((np.clip(darkened, 0.0, 1.0) * 255).astype(np.uint8))
        image = QImage(array_u8.data, cols, rows, cols, QImage.Format.Format_Grayscale8)
        self._pixmap = QPixmap.fromImage(image.copy())
        self.update()

    def _compute_draw_rect(self) -> tuple[int, int, int, int]:
        """Calcule directement depuis la taille du pixmap/widget courants --
        ne depend jamais d'un paintEvent prealable (sinon un glissement
        demarre avant le tout premier rendu utiliserait un rectangle par
        defaut perime, faussant le mapping delta-ecran -> fraction)."""
        if self._pixmap is None or self._pixmap.isNull():
            return (0, 0, max(1, self.width()), max(1, self.height()))
        size = self._pixmap.size().scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        x = (self.width() - size.width()) // 2
        y = (self.height() - size.height()) // 2
        return (x, y, max(1, size.width()), max(1, size.height()))

    def paintEvent(self, event) -> None:
        if self._pixmap is None:
            return
        self._draw_rect = self._compute_draw_rect()
        x, y, w, h = self._draw_rect
        scaled = self._pixmap.scaled(
            w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        painter = QPainter(self)
        painter.drawPixmap(x, y, scaled)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start = event.position()
            self._drag_start_offset = (self.transform.offset_x, self.transform.offset_y)

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return
        delta = event.position() - self._drag_start
        _x, _y, draw_w, draw_h = self._compute_draw_rect()
        dx_frac = delta.x() / draw_w if draw_w else 0.0
        dy_frac = delta.y() / draw_h if draw_h else 0.0
        self.transform = replace(
            self.transform,
            offset_x=self._drag_start_offset[0] + dx_frac,
            offset_y=self._drag_start_offset[1] + dy_frac,
            fit_mode="free",
        )
        self._refresh()
        self.transform_changed.emit(self.transform)

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False

    def wheelEvent(self, event) -> None:
        # Pas fin (retour terrain : la molette etait "trop brutale") --
        # nettement plus doux que l'ancien facteur 1.1 par cran, tout en
        # restant perceptible sur un simple mouvement de molette.
        factor = 1.03 if event.angleDelta().y() > 0 else 1.0 / 1.03
        new_scale = max(0.2, min(8.0, self.transform.scale * factor))
        self.transform = replace(self.transform, scale=new_scale, fit_mode="free")
        self._refresh()
        self.transform_changed.emit(self.transform)

    def apply_zoom_factor(self, factor: float) -> None:
        """Zoom pas-a-pas (boutons +/-), meme logique que la molette mais
        declenchable sans souris/trackpad pour un controle plus precis."""
        new_scale = max(0.2, min(8.0, self.transform.scale * factor))
        self.transform = replace(self.transform, scale=new_scale, fit_mode="free")
        self._refresh()
        self.transform_changed.emit(self.transform)


class CadrageDialog(QDialog):
    def __init__(
        self,
        source_array: np.ndarray,
        shape_mask: np.ndarray,
        initial_transform: ImageTransform,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Cadrer la photo")
        self.resize(760, 760)

        rows, cols = shape_mask.shape
        scale = min(1.0, _PREVIEW_MAX_SIDE / max(rows, cols))
        preview_rows, preview_cols = max(1, round(rows * scale)), max(1, round(cols * scale))
        preview_shape_mask = (
            resize_array(shape_mask.astype(np.float32), width_px=preview_cols, height_px=preview_rows) >= 0.5
        )
        self._src_h, self._src_w = source_array.shape[:2]

        layout = QVBoxLayout(self)
        hint = QLabel(
            "Glisser : deplacer la photo -- molette ou boutons +/- : zoomer. "
            "La forme reste fixe, l'exterieur est assombri."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.preview = _CadragePreviewWidget(source_array, preview_shape_mask, parent=self)
        self.preview.set_transform(initial_transform)
        self.preview.transform_changed.connect(self._on_preview_transform_changed)
        layout.addWidget(self.preview, 1)

        buttons_row = QHBoxLayout()
        self.fill_button = QPushButton("Remplir")
        self.fill_button.clicked.connect(self._on_fill_clicked)
        buttons_row.addWidget(self.fill_button)
        self.fit_button = QPushButton("Ajuster")
        self.fit_button.clicked.connect(self._on_fit_clicked)
        buttons_row.addWidget(self.fit_button)
        self.center_button = QPushButton("Centrer")
        self.center_button.clicked.connect(self._on_center_clicked)
        buttons_row.addWidget(self.center_button)
        self.reset_button = QPushButton("Reinitialiser")
        self.reset_button.clicked.connect(self._on_reset_clicked)
        buttons_row.addWidget(self.reset_button)
        layout.addLayout(buttons_row)

        # Zoom pas-a-pas + pourcentage affiche (retour terrain : la molette
        # seule est trop brutale pour un cadrage precis) -- meme transform
        # que la molette (`apply_zoom_factor`), juste un declencheur plus fin
        # et sans souris/trackpad.
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Zoom"))
        # Root cause du symbole deforme (retour terrain, 2 tentatives
        # infructueuses avant celle-ci) : le theme applique globalement
        # `padding: 6px 14px` a TOUS les QPushButton (cf. theme.py) -- avec
        # une taille fixe 32x32, ce padding ne laisse presque plus de place
        # pour le glyphe (32 - 2*14 = 4px), qui se retrouve tronque a un
        # point/trait a peine visible. Un style scoped par objectName
        # (padding quasi nul, police normale) contourne cette regle globale
        # sans y toucher ailleurs.
        self.zoom_out_button = QPushButton("-")
        self.zoom_out_button.setObjectName("zoomStepButton")
        self.zoom_out_button.setFixedSize(32, 32)
        self.zoom_out_button.setStyleSheet("QPushButton#zoomStepButton { padding: 0px; }")
        self.zoom_out_button.clicked.connect(self._on_zoom_out_clicked)
        zoom_row.addWidget(self.zoom_out_button)
        self.zoom_percent_label = QLabel()
        self.zoom_percent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_percent_label.setFixedWidth(56)
        zoom_row.addWidget(self.zoom_percent_label)
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setObjectName("zoomStepButton")
        self.zoom_in_button.setFixedSize(32, 32)
        self.zoom_in_button.setStyleSheet("QPushButton#zoomStepButton { padding: 0px; }")
        self.zoom_in_button.clicked.connect(self._on_zoom_in_clicked)
        zoom_row.addWidget(self.zoom_in_button)
        zoom_row.addStretch(1)
        layout.addLayout(zoom_row)

        form = QFormLayout()
        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(-180.0, 180.0)
        self.rotation_spin.setSuffix(" deg")
        self.rotation_spin.setValue(initial_transform.rotation_deg)
        self.rotation_spin.valueChanged.connect(self._on_rotation_changed)
        form.addRow("Rotation", self.rotation_spin)
        layout.addLayout(form)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.transform = initial_transform
        self._refresh_zoom_percent_label()

    def _refresh_zoom_percent_label(self) -> None:
        self.zoom_percent_label.setText(f"{round(self.transform.scale * 100)} %")

    def _on_zoom_in_clicked(self) -> None:
        self.preview.apply_zoom_factor(1.0 + _ZOOM_BUTTON_STEP_PERCENT / 100.0)

    def _on_zoom_out_clicked(self) -> None:
        self.preview.apply_zoom_factor(1.0 / (1.0 + _ZOOM_BUTTON_STEP_PERCENT / 100.0))

    def _on_preview_transform_changed(self, transform: ImageTransform) -> None:
        self.transform = transform
        self.rotation_spin.blockSignals(True)
        self.rotation_spin.setValue(transform.rotation_deg)
        self.rotation_spin.blockSignals(False)
        self._refresh_zoom_percent_label()

    def _on_rotation_changed(self, value: float) -> None:
        self.transform = replace(self.transform, rotation_deg=value, fit_mode="free")
        self.preview.set_transform(self.transform)

    def _on_fit_clicked(self) -> None:
        self.transform = replace(self.transform, offset_x=0.0, offset_y=0.0, scale=1.0, fit_mode="fit")
        self._apply_and_refresh()

    def _on_fill_clicked(self) -> None:
        rows, cols = self.preview.shape_mask.shape
        factor = fill_scale_relative_to_fit(self._src_w, self._src_h, cols, rows)
        self.transform = replace(self.transform, offset_x=0.0, offset_y=0.0, scale=factor, fit_mode="fill")
        self._apply_and_refresh()

    def _on_center_clicked(self) -> None:
        self.transform = replace(self.transform, offset_x=0.0, offset_y=0.0, fit_mode="center")
        self._apply_and_refresh()

    def _on_reset_clicked(self) -> None:
        self.transform = ImageTransform()
        self._apply_and_refresh()

    def _apply_and_refresh(self) -> None:
        self.preview.set_transform(self.transform)
        self.rotation_spin.blockSignals(True)
        self.rotation_spin.setValue(self.transform.rotation_deg)
        self.rotation_spin.blockSignals(False)
        self._refresh_zoom_percent_label()
