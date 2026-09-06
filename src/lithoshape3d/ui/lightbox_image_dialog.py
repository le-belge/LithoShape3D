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
from lithoshape3d.core.geometry.vector_lightbox import (
    CONNECTOR_PRESET_POGO,
    CONNECTOR_PRESET_USB_C,
    CONNECTOR_SHAPE_CIRCLE,
    CONNECTOR_SHAPE_RECT,
)
from lithoshape3d.core.scene.models import ImageTransform
from lithoshape3d.ui.mesh_preview_panel import MeshPreviewPanel

logger = logging.getLogger("lithoshape3d.ui.lightbox_image")

_PREVIEW_MAX_SIDE = 360
_CAP_MODE_FLAT = "flat"
_CAP_MODE_LITHOPHANE = "lithophane"
_CAP_MODE_FLAT_TWO_COLOR = "flat_two_color"
_SHAPE_MODE_SILHOUETTE = "silhouette"
_SHAPE_MODE_ARTWORK = "artwork_envelope"

_CONNECTOR_NONE = "none"

_ARTWORK_PREVIEW_BACKGROUND = (40, 40, 40)
"""Hors enveloppe (exterieur reel du futur caisson)."""
_ARTWORK_PREVIEW_FOND = (225, 225, 225)
"""Dans l'enveloppe mais pas encre -- deviendra la piece "fond" du capot 2
couleurs (ex. interieur d'un cercle ferme, entre les doigts)."""
_ARTWORK_PREVIEW_INK = (15, 15, 15)
"""Encre -- deviendra la piece "encre" du capot 2 couleurs."""


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

    @staticmethod
    def _add_form_row(form: QFormLayout, label_text: str, widget: QWidget) -> QLabel:
        """Ajoute une ligne au `QFormLayout` et retourne son `QLabel` --
        necessaire pour pouvoir masquer/afficher label ET widget ensemble
        (une ligne visible avec seulement le widget cache laisse un label
        orphelin), utilise par `_on_connector_mode_changed`."""
        label = QLabel(label_text)
        form.addRow(label, widget)
        return label

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("LightBox depuis image")
        self.setMinimumWidth(900)

        self._image_path: str | None = None
        """Chemin ORIGINAL choisi par l'utilisateur (affiche, et utilise
        pour nommer les fichiers de sortie)."""
        self._resolved_image_path: str | None = None
        """Chemin RASTER utilise pour la previsualisation 2D et le slider de
        seuil (Cas B) -- identique a `_image_path` sauf pour un SVG
        (rasterise une fois via `ui/shape_svg_import.py`, Qt, hors de
        `core/`, uniquement a des fins de previsualisation/seuillage)."""
        self._svg_source_path: str | None = None
        """Chemin du `.svg` ORIGINAL si la source est un SVG, sinon `None`.
        Transmis TEL QUEL (PAS le raster de previsualisation) a
        `generate_lightbox_from_image`, quel que soit `shape_mode` -- les
        deux modes ("silhouette" ET "artwork_envelope") utilisent le
        contour vectoriel exact pour une source `.svg` (voir
        `core/geometry/svg_path_extractor.py` et
        `core/geometry/vector_envelope.py`), sans jamais rasteriser. Le
        raster resolu (`_resolved_image_path`) reste utilise UNIQUEMENT
        pour l'apercu 2D bon marche de cette fenetre (silhouette) ou est
        rasterise a la volee depuis le resultat vectoriel (artwork,
        `_rasterize_vector_preview`)."""
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

        preview_col = QVBoxLayout()
        self.preview_label = QLabel("Choisissez une image pour voir la silhouette extraite.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(_PREVIEW_MAX_SIDE, _PREVIEW_MAX_SIDE)
        self.preview_label.setStyleSheet("background-color: #202020; color: #ccc;")
        self.preview_label.setWordWrap(True)
        preview_col.addWidget(self.preview_label, 1)

        self.artwork_info_label = QLabel("")
        self.artwork_info_label.setWordWrap(True)
        self.artwork_info_label.setVisible(False)
        preview_col.addWidget(self.artwork_info_label)

        content_row.addLayout(preview_col, 1)

        form_widget = QWidget()
        form = QFormLayout(form_widget)

        self.shape_mode_combo = QComboBox()
        self.shape_mode_combo.addItem("Silhouette (logo/photo)", _SHAPE_MODE_SILHOUETTE)
        self.shape_mode_combo.addItem(
            "Enveloppe dessin au trait (elements disjoints unifies)", _SHAPE_MODE_ARTWORK
        )
        self.shape_mode_combo.currentIndexChanged.connect(self._on_shape_mode_changed)
        form.addRow("Mode de forme", self.shape_mode_combo)

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

        self.connector_combo = QComboBox()
        self.connector_combo.addItem("Aucun", _CONNECTOR_NONE)
        self.connector_combo.addItem("USB-C", CONNECTOR_SHAPE_RECT + "_usb_c")
        self.connector_combo.addItem("Pogo pin", CONNECTOR_SHAPE_CIRCLE + "_pogo")
        self.connector_combo.addItem("Personnalise (rectangle)", CONNECTOR_SHAPE_RECT)
        self.connector_combo.addItem("Personnalise (cercle)", CONNECTOR_SHAPE_CIRCLE)
        self.connector_combo.setToolTip(
            "Decoupe un trou dans le fond du caisson pour un connecteur d'alimentation "
            "(LED internes) -- USB-C et Pogo pin sont des tailles generiques, a ajuster "
            "si besoin selon le connecteur reel."
        )
        self.connector_combo.currentIndexChanged.connect(self._on_connector_mode_changed)
        form.addRow("Connecteur (fond)", self.connector_combo)

        self.connector_width_spin = QDoubleSpinBox()
        self.connector_width_spin.setRange(1.0, 100.0)
        self.connector_width_spin.setSingleStep(0.1)
        self.connector_width_spin.setValue(CONNECTOR_PRESET_USB_C["width_mm"])
        self.connector_width_spin.setSuffix(" mm")
        self.connector_width_label_row = self._add_form_row(form, "Largeur connecteur", self.connector_width_spin)

        self.connector_height_spin = QDoubleSpinBox()
        self.connector_height_spin.setRange(1.0, 100.0)
        self.connector_height_spin.setSingleStep(0.1)
        self.connector_height_spin.setValue(CONNECTOR_PRESET_USB_C["height_mm"])
        self.connector_height_spin.setSuffix(" mm")
        self.connector_height_label_row = self._add_form_row(form, "Hauteur connecteur", self.connector_height_spin)

        self.connector_pos_x_spin = QDoubleSpinBox()
        self.connector_pos_x_spin.setRange(0.0, 100.0)
        self.connector_pos_x_spin.setSingleStep(1.0)
        self.connector_pos_x_spin.setValue(50.0)
        self.connector_pos_x_spin.setSuffix(" %")
        self.connector_pos_x_row = self._add_form_row(form, "Position X connecteur", self.connector_pos_x_spin)

        self.connector_pos_y_spin = QDoubleSpinBox()
        self.connector_pos_y_spin.setRange(0.0, 100.0)
        self.connector_pos_y_spin.setSingleStep(1.0)
        self.connector_pos_y_spin.setValue(10.0)
        self.connector_pos_y_spin.setSuffix(" %")
        self.connector_pos_y_row = self._add_form_row(form, "Position Y connecteur", self.connector_pos_y_spin)

        self._on_connector_mode_changed(0)

        self.cap_thickness_spin = QDoubleSpinBox()
        self.cap_thickness_spin.setRange(0.4, 20.0)
        self.cap_thickness_spin.setSingleStep(0.1)
        self.cap_thickness_spin.setValue(1.5)
        self.cap_thickness_spin.setSuffix(" mm")
        self.cap_thickness_spin.setToolTip(
            "Epaisseur du capot plat -- l'epaulement de retention (rebord interieur) est "
            "ajuste automatiquement pour correspondre exactement, afin que le capot affleure."
        )
        form.addRow("Epaisseur du capot (plat)", self.cap_thickness_spin)

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
        self.cap_mode_combo.addItem(
            "2 couleurs plates (dessin au trait -- necessite mode enveloppe)",
            _CAP_MODE_FLAT_TWO_COLOR,
        )
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

        layout.addWidget(QLabel("Apercu 3D du resultat genere :"))
        self.preview_3d = MeshPreviewPanel()
        self.preview_3d.setMinimumHeight(280)
        layout.addWidget(self.preview_3d, 1)

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
            self, "Image source", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp *.svg)"
        )
        if not path:
            return
        self._load_image(path)

    def _load_image(self, path: str) -> None:
        resolved_path = path
        svg_source_path: str | None = None
        if path.lower().endswith(".svg"):
            svg_source_path = path
            try:
                from lithoshape3d.ui.shape_svg_import import rasterize_svg_to_alpha_png

                # Uniquement pour la previsualisation 2D / le slider de
                # seuil ci-dessous -- la generation reelle en mode
                # silhouette utilisera `svg_source_path` (contour vectoriel
                # exact), pas ce raster (voir `_on_generate_clicked`).
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
        self._svg_source_path = svg_source_path
        self._alpha = alpha
        self._gray = gray
        self.image_label.setText(Path(path).name)

        try:
            _mask, otsu_value, _warnings = threshold_and_clean_mask(gray, mode="auto")
        except Exception:
            otsu_value = 128
        self.threshold_slider.blockSignals(True)
        self.threshold_slider.setValue(otsu_value)
        self.threshold_slider.blockSignals(False)
        self.threshold_value_label.setText(str(otsu_value))
        self.threshold_row_widget.setVisible(self._threshold_relevant())

        self._refresh_preview()

    def _threshold_relevant(self) -> bool:
        """Le mode enveloppe dessin au trait travaille TOUJOURS sur les
        niveaux de gris (l'alpha eventuel est ignore, voir
        `artwork_shape_extractor.extract_artwork_from_image`) -- le slider
        de seuil reste donc pertinent meme pour un PNG avec canal alpha,
        contrairement au mode silhouette (Cas A alpha exploitable = pas de
        seuillage). Sans objet pour une source `.svg` (pipeline vectoriel,
        aucun seuillage, voir `extract_artwork_from_svg`)."""
        if self._svg_source_path:
            return False
        if self.shape_mode_combo.currentData() == _SHAPE_MODE_ARTWORK:
            return True
        return self._alpha is None

    def _resolve_threshold_args(self) -> tuple[str, int | None]:
        if self._threshold_relevant():
            return "manual", self.threshold_slider.value()
        return "auto", None

    def _choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Dossier de sortie")
        if directory:
            self._output_dir = directory
            self.output_label.setText(directory)

    def _on_connector_mode_changed(self, _index: int) -> None:
        mode = self.connector_combo.currentData()
        is_none = mode == _CONNECTOR_NONE
        is_circle = mode in (CONNECTOR_SHAPE_CIRCLE, CONNECTOR_SHAPE_CIRCLE + "_pogo")

        if mode == CONNECTOR_SHAPE_RECT + "_usb_c":
            self.connector_width_spin.setValue(CONNECTOR_PRESET_USB_C["width_mm"])
            self.connector_height_spin.setValue(CONNECTOR_PRESET_USB_C["height_mm"])
        elif mode == CONNECTOR_SHAPE_CIRCLE + "_pogo":
            self.connector_width_spin.setValue(CONNECTOR_PRESET_POGO["width_mm"])

        self.connector_width_label_row.setText("Diametre connecteur" if is_circle else "Largeur connecteur")
        for label, widget in (
            (self.connector_width_label_row, self.connector_width_spin),
            (self.connector_pos_x_row, self.connector_pos_x_spin),
            (self.connector_pos_y_row, self.connector_pos_y_spin),
        ):
            label.setVisible(not is_none)
            widget.setVisible(not is_none)
        self.connector_height_label_row.setVisible(not is_none and not is_circle)
        self.connector_height_spin.setVisible(not is_none and not is_circle)

    def _connector_generation_kwargs(self) -> dict:
        mode = self.connector_combo.currentData()
        if mode == _CONNECTOR_NONE:
            return {"connector_shape": None}
        shape = CONNECTOR_SHAPE_CIRCLE if mode in (CONNECTOR_SHAPE_CIRCLE, CONNECTOR_SHAPE_CIRCLE + "_pogo") else CONNECTOR_SHAPE_RECT
        return {
            "connector_shape": shape,
            "connector_width_mm": self.connector_width_spin.value(),
            "connector_height_mm": None if shape == CONNECTOR_SHAPE_CIRCLE else self.connector_height_spin.value(),
            "connector_corner_radius_mm": 1.0 if shape == CONNECTOR_SHAPE_RECT else 0.0,
            "connector_position_x_fraction": self.connector_pos_x_spin.value() / 100.0,
            "connector_position_y_fraction": self.connector_pos_y_spin.value() / 100.0,
        }

    def _on_cap_mode_changed(self, _index: int) -> None:
        cap_mode = self.cap_mode_combo.currentData()
        if cap_mode == _CAP_MODE_FLAT_TWO_COLOR and self.shape_mode_combo.currentData() != _SHAPE_MODE_ARTWORK:
            QMessageBox.warning(
                self,
                "LightBox depuis image",
                "Le capot 2 couleurs necessite le mode de forme "
                "'Enveloppe dessin au trait'.",
            )
            self.cap_mode_combo.blockSignals(True)
            self.cap_mode_combo.setCurrentIndex(self.cap_mode_combo.findData(_CAP_MODE_FLAT))
            self.cap_mode_combo.blockSignals(False)
            cap_mode = _CAP_MODE_FLAT
        self.cap_image_button.setEnabled(cap_mode == _CAP_MODE_LITHOPHANE)

    def _on_shape_mode_changed(self, _index: int) -> None:
        is_artwork = self.shape_mode_combo.currentData() == _SHAPE_MODE_ARTWORK
        self.artwork_info_label.setVisible(is_artwork)
        if self._gray is not None:
            self.threshold_row_widget.setVisible(self._threshold_relevant())
        if not is_artwork and self.cap_mode_combo.currentData() == _CAP_MODE_FLAT_TWO_COLOR:
            self.cap_mode_combo.blockSignals(True)
            self.cap_mode_combo.setCurrentIndex(self.cap_mode_combo.findData(_CAP_MODE_FLAT))
            self.cap_mode_combo.blockSignals(False)
            self.cap_image_button.setEnabled(False)
        self._refresh_preview()

    def _choose_cap_image(self) -> None:
        if not self._resolved_image_path:
            QMessageBox.warning(
                self, "LightBox depuis image", "Choisissez d'abord l'image source."
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Image de lithophanie (capot)", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
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

        if self.shape_mode_combo.currentData() == _SHAPE_MODE_ARTWORK:
            self._refresh_artwork_preview()
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

    def _refresh_artwork_preview(self) -> None:
        from lithoshape3d.core.geometry.artwork_shape_extractor import (
            ArtworkExtractionError,
            extract_artwork_from_arrays,
            extract_artwork_from_svg,
        )

        try:
            if self._svg_source_path:
                # Source SVG : pipeline vectoriel (`extract_artwork_from_svg`,
                # pas de rasterisation) -- aucun masque pixel produit, donc
                # on RASTERISE uniquement les polygones resultants pour cet
                # apercu 2D bon marche (voir `rasterize_polygon_mask`, deja
                # utilise ailleurs pour la meme raison -- ceci ne concerne
                # QUE l'affichage, pas l'extraction geometrique elle-meme).
                result = extract_artwork_from_svg(self._svg_source_path, self.width_spin.value())
                ink_mask, envelope_mask = self._rasterize_vector_preview(result)
            else:
                threshold_mode, threshold_value = self._resolve_threshold_args()
                result = extract_artwork_from_arrays(
                    self._gray,
                    self.width_spin.value(),
                    threshold_mode=threshold_mode,
                    threshold_value=threshold_value,
                )
                ink_mask, envelope_mask = result.ink_mask, result.envelope_mask
        except ArtworkExtractionError as exc:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(f"Enveloppe introuvable : {exc}")
            self.artwork_info_label.setText("")
            return
        except Exception as exc:  # pragma: no cover - defensif, UI seulement
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(f"Erreur d'apercu : {exc}")
            self.artwork_info_label.setText("")
            return

        self._update_preview_pixmap_rgb(self._artwork_preview_rgb(ink_mask, envelope_mask))

        info = f"{result.num_components_before_closing} composante(s) detectee(s)."
        if result.weld_distance_mm:
            info += (
                f" Soudure vectorielle automatique (distance {result.weld_distance_mm:.2f}mm) -> "
                "1 caisson unique."
            )
        elif result.closing_radius_px:
            info += (
                f" Fermeture automatique (rayon {result.closing_radius_px}px) -> "
                "1 caisson unique."
            )
        else:
            info += " Deja unifiees : aucune soudure/fermeture necessaire."
        self.artwork_info_label.setText(info)

    def _rasterize_vector_preview(self, result) -> tuple[np.ndarray, np.ndarray]:
        """Rasterise `result.ink_polygon`/`result.envelope_polygon` (source
        `.svg`, pipeline vectoriel) en deux masques pixel -- UNIQUEMENT pour
        composer l'apercu 2D bon marche de `_artwork_preview_rgb` (meme
        fonction de rasterisation que `image_lightbox_export.compute_shape_
        and_cap_mask`, deja utilisee pour un usage similaire). N'affecte en
        rien la geometrie extraite/exportee (qui reste 100% vectorielle)."""
        from lithoshape3d.core.geometry.heightmap import grid_dimensions
        from lithoshape3d.core.geometry.letter_glyph_extractor import rasterize_polygon_mask
        from lithoshape3d.core.scene.models import GeometryParameters

        face_params = GeometryParameters(width_mm=result.width_mm, height_mm=result.height_mm)
        rows, cols = grid_dimensions(face_params)
        envelope_mask = rasterize_polygon_mask(
            result.envelope_polygon, result.width_mm, result.height_mm, rows, cols
        )
        ink_mask = rasterize_polygon_mask(
            result.ink_polygon, result.width_mm, result.height_mm, rows, cols
        )
        return ink_mask, envelope_mask

    @staticmethod
    def _artwork_preview_rgb(ink_mask: np.ndarray, envelope_mask: np.ndarray) -> np.ndarray:
        """Composite visuel : fond sombre = exterieur du futur caisson, gris
        clair = enveloppe/matiere (deviendra la piece "fond" du capot 2
        couleurs), noir = encre (deviendra la piece "encre") -- pour que
        l'utilisateur comprenne les DEUX masques generes avant de cliquer
        "Generer", comme demande."""
        rows, cols = envelope_mask.shape
        rgb = np.empty((rows, cols, 3), dtype=np.uint8)
        rgb[:, :] = _ARTWORK_PREVIEW_BACKGROUND
        rgb[envelope_mask] = _ARTWORK_PREVIEW_FOND
        rgb[ink_mask] = _ARTWORK_PREVIEW_INK
        return rgb

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

    def _update_preview_pixmap_rgb(self, rgb: np.ndarray) -> None:
        rows, cols, _channels = rgb.shape
        array_u8 = np.ascontiguousarray(rgb)
        image = QImage(array_u8.data, cols, rows, cols * 3, QImage.Format.Format_RGB888)
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

        threshold_mode, threshold_value = self._resolve_threshold_args()
        shape_mode = self.shape_mode_combo.currentData()

        # Source SVG (silhouette OU artwork_envelope) : passe le SVG
        # ORIGINAL (contour vectoriel exact via
        # `core/geometry/svg_path_extractor.py` + `vector_envelope.py` en
        # artwork_envelope), jamais le raster de previsualisation -- voir
        # `_svg_source_path`. Les deux modes utilisent desormais le meme
        # moteur vectoriel pour une source `.svg` (aucune rasterisation).
        generation_image_path = self._svg_source_path or self._resolved_image_path

        self.generate_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.result_view.setPlainText("Generation en cours...")

        worker = _ImageLightboxWorker(
            image_path=generation_image_path,
            output_dir=self._output_dir,
            width_mm=self.width_spin.value(),
            depth_mm=self.depth_spin.value(),
            wall_thickness_mm=self.wall_spin.value(),
            back_thickness_mm=self.back_spin.value(),
            cap_thickness_mm=self.cap_thickness_spin.value(),
            threshold_mode=threshold_mode,
            threshold_value=threshold_value,
            cap_image_path=cap_image_path,
            cap_image_transform=cap_transform,
            shape_mode=shape_mode,
            cap_mode=cap_mode,
            **self._connector_generation_kwargs(),
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
            self.preview_3d.show_stl_files(result.written)

        self.result_view.setPlainText("\n".join(lines))

    def _on_generation_failed(self, message: str) -> None:
        self.result_view.setPlainText(f"ECHEC: {message}")

    def _on_generation_finished(self) -> None:
        self.generate_button.setEnabled(True)
        self.progress_bar.setVisible(False)
