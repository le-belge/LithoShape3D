"""Ecran "LightBox depuis image" : genere un caisson lumineux vectoriel a
partir d'une silhouette extraite d'une image -- logo/silhouette a fond
transparent (Cas A) OU photo classique seuillee (Cas B, Otsu + slider
manuel) -- avec previsualisation de la silhouette AVANT generation.

Reutilise `generate_lightbox_from_image`
(core/geometry/image_lightbox_export.py) pour la generation reelle et
`extract_shape_from_arrays` (core/geometry/image_shape_extractor.py) pour
l'apercu -- aucune logique d'extraction/generation dupliquee ici, seulement
construction de formulaire + un worker Qt (meme pattern que
`lightbox_letters_dialog.py`).

Discipline de previsualisation (meme principe que `CadrageDialog`) :
ajuster le slider de seuil (Cas B) recalcule uniquement la silhouette 2D
(masque + contour), JAMAIS de mesh 3D -- le calcul de mesh/booleenne
manifold3d ne se declenche qu'au clic explicite sur "Generer"."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from lithoshape3d.core.geometry.image_lightbox_export import LightboxImageResult
from lithoshape3d.core.scene.models import ImageTransform

logger = logging.getLogger("lithoshape3d.ui.lightbox_image")

_PREVIEW_MAX_SIDE = 360
_CAP_MODE_FLAT = "flat"
_CAP_MODE_LITHOPHANE = "lithophane"


class _ImageLightboxSignals(QObject):
    succeeded = Signal(object)  # LightboxImageResult
    failed = Signal(str)
    finished = Signal()


class _ImageLightboxWorker(QRunnable):
    """Genere le caisson en arriere-plan -- meme discipline que les autres
    workers du projet (worker.py) : aucun widget touche depuis `run()`,
    resultat uniquement via signaux Qt."""

    def __init__(self, **kwargs) -> None:
        super().__init__()
        self._kwargs = kwargs
        self.signals = _ImageLightboxSignals()

    def run(self) -> None:
        from lithoshape3d.core.geometry.image_lightbox_export import generate_lightbox_from_image

        try:
            result = generate_lightbox_from_image(**self._kwargs)
        except (ValueError, OSError, RuntimeError) as exc:
            logger.exception("Echec de la generation LightBox depuis image")
            self.signals.failed.emit(str(exc))
            self.signals.finished.emit()
            return
        self.signals.succeeded.emit(result)
        self.signals.finished.emit()


class LightboxImageDialog(QDialog):
    """Dialogue modal pour generer un caisson lumineux vectoriel depuis une
    image, avec previsualisation de la silhouette extraite."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("LightBox depuis image")
        self.setMinimumWidth(640)

        self._image_path: str | None = None
        """Chemin ORIGINAL choisi par l'utilisateur (affiche, et utilise
        pour nommer les fichiers de sortie)."""
        self._resolved_image_path: str | None = None
        """Chemin reellement passe au pipeline core -- un raster PNG/JPG,
        identique a `_image_path` sauf pour un SVG (converti une fois via
        `ui/shape_svg_import.py`, Qt, hors de `core/`)."""
        self._alpha: np.ndarray | None = None
        self._gray: np.ndarray | None = None
        self._output_dir: str = ""
        self._cap_image_path: str | None = None
        self._cap_transform: ImageTransform | None = None
        self._thread_pool = QThreadPool.globalInstance()

        layout = QVBoxLayout(self)

        hint = QLabel(
            "Importez un logo/silhouette a fond transparent (ou SVG), ou une photo "
            "classique (seuillage automatique, ajustable). Capot plat/lisse par defaut."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        image_row = QHBoxLayout()
        self.image_label = QLabel("(aucune image selectionnee)")
        self.image_label.setWordWrap(True)
        image_button = QPushButton("Choisir une image...")
        image_button.clicked.connect(self._choose_image)
        image_row.addWidget(self.image_label, 1)
        image_row.addWidget(image_button)
        layout.addLayout(image_row)

        content_row = QHBoxLayout()

        self.preview_label = QLabel("Choisissez une image pour voir la silhouette extraite.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(_PREVIEW_MAX_SIDE, _PREVIEW_MAX_SIDE)
        self.preview_label.setStyleSheet("background-color: #202020; color: #ccc;")
        self.preview_label.setWordWrap(True)
        content_row.addWidget(self.preview_label, 1)

        form_widget = QWidget()
        form = QFormLayout(form_widget)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(5.0, 1000.0)
        self.width_spin.setValue(100.0)
        self.width_spin.setSuffix(" mm")
        self.width_spin.valueChanged.connect(self._on_dimension_changed)
        form.addRow("Largeur", self.width_spin)

        self.depth_spin = QDoubleSpinBox()
        self.depth_spin.setRange(1.0, 200.0)
        self.depth_spin.setValue(25.0)
        self.depth_spin.setSuffix(" mm")
        form.addRow("Profondeur du caisson", self.depth_spin)

        self.wall_spin = QDoubleSpinBox()
        self.wall_spin.setRange(0.4, 20.0)
        self.wall_spin.setSingleStep(0.1)
        self.wall_spin.setValue(1.6)
        self.wall_spin.setSuffix(" mm")
        form.addRow("Epaisseur des parois", self.wall_spin)

        self.back_spin = QDoubleSpinBox()
        self.back_spin.setRange(0.4, 20.0)
        self.back_spin.setSingleStep(0.1)
        self.back_spin.setValue(1.2)
        self.back_spin.setSuffix(" mm")
        form.addRow("Epaisseur du fond", self.back_spin)

        self.threshold_row_widget = QWidget()
        threshold_row = QHBoxLayout(self.threshold_row_widget)
        threshold_row.setContentsMargins(0, 0, 0, 0)
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(0, 255)
        self.threshold_slider.setValue(128)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        self.threshold_value_label = QLabel("128")
        self.threshold_value_label.setMinimumWidth(32)
        threshold_row.addWidget(self.threshold_slider, 1)
        threshold_row.addWidget(self.threshold_value_label)
        self.threshold_row_widget.setVisible(False)
        form.addRow("Seuil (photo)", self.threshold_row_widget)

        self.cap_mode_combo = QComboBox()
        self.cap_mode_combo.addItem("Plat / lisse (par defaut, sans litho)", _CAP_MODE_FLAT)
        self.cap_mode_combo.addItem("Lithophanie (image separee)", _CAP_MODE_LITHOPHANE)
        self.cap_mode_combo.currentIndexChanged.connect(self._on_cap_mode_changed)
        form.addRow("Capot", self.cap_mode_combo)

        cap_image_row = QHBoxLayout()
        self.cap_image_label = QLabel("(aucune image)")
        self.cap_image_button = QPushButton("Image du capot...")
        self.cap_image_button.setEnabled(False)
        self.cap_image_button.clicked.connect(self._choose_cap_image)
        cap_image_row.addWidget(self.cap_image_label, 1)
        cap_image_row.addWidget(self.cap_image_button)
        form.addRow("", cap_image_row)

        output_row = QHBoxLayout()
        self.output_label = QLabel("(aucun dossier selectionne)")
        output_button = QPushButton("Choisir un dossier...")
        output_button.clicked.connect(self._choose_output_dir)
        output_row.addWidget(self.output_label, 1)
        output_row.addWidget(output_button)
        form.addRow("Dossier de sortie", output_row)

        content_row.addWidget(form_widget, 1)
        layout.addLayout(content_row)

        self.generate_button = QPushButton("Generer")
        self.generate_button.clicked.connect(self._on_generate_clicked)
        layout.addWidget(self.generate_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.result_view = QPlainTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setPlaceholderText("Le resultat de la generation s'affichera ici.")
        self.result_view.setMinimumHeight(120)
        layout.addWidget(self.result_view)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------ #
    # Selection image / dossier / capot
    # ------------------------------------------------------------------ #
    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Image source", "", "Images (*.png *.jpg *.jpeg *.svg)"
        )
        if not path:
            return
        self._load_image(path)

    def _load_image(self, path: str) -> None:
        resolved_path = path
        if path.lower().endswith(".svg"):
            try:
                from lithoshape3d.ui.shape_svg_import import rasterize_svg_to_alpha_png

                resolved_path = rasterize_svg_to_alpha_png(path)
            except Exception as exc:
                QMessageBox.warning(self, "LightBox depuis image", f"SVG illisible : {exc}")
                return

        try:
            from lithoshape3d.core.geometry.image_shape_extractor import (
                load_image_for_extraction,
                threshold_and_clean_mask,
            )

            alpha, gray = load_image_for_extraction(resolved_path)
        except Exception as exc:
            QMessageBox.warning(self, "LightBox depuis image", f"Image illisible : {exc}")
            return

        self._image_path = path
        self._resolved_image_path = resolved_path
        self._alpha = alpha
        self._gray = gray
        self.image_label.setText(Path(path).name)

        if alpha is not None:
            self.threshold_row_widget.setVisible(False)
        else:
            self.threshold_row_widget.setVisible(True)
            try:
                _mask, otsu_value, _warnings = threshold_and_clean_mask(gray, mode="auto")
            except Exception:
                otsu_value = 128
            self.threshold_slider.blockSignals(True)
            self.threshold_slider.setValue(otsu_value)
            self.threshold_slider.blockSignals(False)
            self.threshold_value_label.setText(str(otsu_value))

        self._refresh_preview()

    def _choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Dossier de sortie")
        if directory:
            self._output_dir = directory
            self.output_label.setText(directory)

    def _on_cap_mode_changed(self, _index: int) -> None:
        is_lithophane = self.cap_mode_combo.currentData() == _CAP_MODE_LITHOPHANE
        self.cap_image_button.setEnabled(is_lithophane)

    def _choose_cap_image(self) -> None:
        if not self._resolved_image_path:
            QMessageBox.warning(
                self, "LightBox depuis image", "Choisissez d'abord l'image source."
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Image de lithophanie (capot)", "", "Images (*.png *.jpg *.jpeg)"
        )
        if not path:
            return

        try:
            from lithoshape3d.core.geometry.image_lightbox_export import compute_shape_and_cap_mask

            threshold_mode = "auto" if self._alpha is not None else "manual"
            threshold_value = None if self._alpha is not None else self.threshold_slider.value()
            _shape, _face_params, cap_mask = compute_shape_and_cap_mask(
                self._resolved_image_path,
                self.width_spin.value(),
                threshold_mode=threshold_mode,
                threshold_value=threshold_value,
                wall_thickness_mm=self.wall_spin.value(),
            )
        except Exception as exc:
            QMessageBox.warning(
                self, "LightBox depuis image", f"Impossible de calculer le footprint du capot : {exc}"
            )
            return

        if not cap_mask.any():
            QMessageBox.warning(
                self,
                "LightBox depuis image",
                "Le footprint du capot est vide a ces parametres (silhouette trop fine pour "
                "l'epaisseur de paroi demandee) -- reduisez l'epaisseur des parois ou augmentez "
                "la largeur.",
            )
            return

        try:
            from lithoshape3d.core.image.io import load_image
            from lithoshape3d.core.image.preprocessing import to_grayscale_array

            source_array = to_grayscale_array(load_image(path))
        except Exception as exc:
            QMessageBox.warning(self, "LightBox depuis image", f"Image illisible : {exc}")
            return

        from lithoshape3d.ui.cadrage_dialog import CadrageDialog

        initial_transform = self._cap_transform or ImageTransform()
        cadrage = CadrageDialog(source_array, cap_mask, initial_transform, self)
        cadrage.setWindowTitle("Cadrer l'image du capot")
        if cadrage.exec() != QDialog.DialogCode.Accepted:
            return

        self._cap_image_path = path
        self._cap_transform = cadrage.transform
        self.cap_image_label.setText(Path(path).name)

    # ------------------------------------------------------------------ #
    # Previsualisation (2D bon marche -- jamais de mesh 3D)
    # ------------------------------------------------------------------ #
    def _on_threshold_changed(self, value: int) -> None:
        self.threshold_value_label.setText(str(value))
        self._refresh_preview()

    def _on_dimension_changed(self, _value: float) -> None:
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if self._gray is None:
            return

        from lithoshape3d.core.geometry.image_shape_extractor import (
            ImageShapeExtractionError,
            extract_shape_from_arrays,
        )

        threshold_mode = "auto" if self._alpha is not None else "manual"
        threshold_value = None if self._alpha is not None else self.threshold_slider.value()

        try:
            result = extract_shape_from_arrays(
                self._alpha,
                self._gray,
                self.width_spin.value(),
                threshold_mode=threshold_mode,
                threshold_value=threshold_value,
            )
        except ImageShapeExtractionError as exc:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(f"Silhouette introuvable : {exc}")
            return
        except Exception as exc:  # pragma: no cover - defensif, UI seulement
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(f"Erreur d'apercu : {exc}")
            return

        self._update_preview_pixmap(result.mask)

    def _update_preview_pixmap(self, mask: np.ndarray) -> None:
        rows, cols = mask.shape
        array_u8 = np.ascontiguousarray((mask.astype(np.uint8)) * 255)
        image = QImage(array_u8.data, cols, rows, cols, QImage.Format.Format_Grayscale8)
        pixmap = QPixmap.fromImage(image.copy()).scaled(
            _PREVIEW_MAX_SIDE,
            _PREVIEW_MAX_SIDE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setText("")
        self.preview_label.setPixmap(pixmap)

    # ------------------------------------------------------------------ #
    # Generation
    # ------------------------------------------------------------------ #
    def _on_generate_clicked(self) -> None:
        if not self._resolved_image_path:
            QMessageBox.warning(self, "LightBox depuis image", "Choisissez d'abord une image.")
            return
        if not self._output_dir:
            QMessageBox.warning(self, "LightBox depuis image", "Choisissez un dossier de sortie.")
            return

        cap_mode = self.cap_mode_combo.currentData()
        cap_image_path = self._cap_image_path if cap_mode == _CAP_MODE_LITHOPHANE else None
        cap_transform = self._cap_transform if cap_mode == _CAP_MODE_LITHOPHANE else None
        if cap_mode == _CAP_MODE_LITHOPHANE and not cap_image_path:
            QMessageBox.warning(
                self,
                "LightBox depuis image",
                "Choisissez une image pour le capot lithophanie, ou repassez le capot en mode plat.",
            )
            return

        threshold_mode = "auto" if self._alpha is not None else "manual"
        threshold_value = None if self._alpha is not None else self.threshold_slider.value()

        self.generate_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.result_view.setPlainText("Generation en cours...")

        worker = _ImageLightboxWorker(
            image_path=self._resolved_image_path,
            output_dir=self._output_dir,
            width_mm=self.width_spin.value(),
            depth_mm=self.depth_spin.value(),
            wall_thickness_mm=self.wall_spin.value(),
            back_thickness_mm=self.back_spin.value(),
            threshold_mode=threshold_mode,
            threshold_value=threshold_value,
            cap_image_path=cap_image_path,
            cap_image_transform=cap_transform,
        )
        worker.signals.succeeded.connect(self._on_generation_succeeded)
        worker.signals.failed.connect(self._on_generation_failed)
        worker.signals.finished.connect(self._on_generation_finished)
        self._thread_pool.start(worker)

    def _on_generation_succeeded(self, result: LightboxImageResult) -> None:
        lines: list[str] = []
        for level, text in result.messages:
            prefix = "ECHEC" if level == "error" else "AVERTISSEMENT"
            lines.append(f"{prefix}: {text}")

        if not result.ok:
            lines.append("ECHEC: aucun fichier n'a pu etre genere.")
        else:
            if result.threshold_used is not None:
                lines.append(f"Seuil utilise : {result.threshold_used}")
            lines.append("")
            lines.append(f"OK -- {len(result.written)} fichier(s) genere(s) :")
            lines.extend(str(path) for path in result.written)

        self.result_view.setPlainText("\n".join(lines))

    def _on_generation_failed(self, message: str) -> None:
        self.result_view.setPlainText(f"ECHEC: {message}")

    def _on_generation_finished(self) -> None:
        self.generate_button.setEnabled(True)
        self.progress_bar.setVisible(False)
