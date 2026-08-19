"""Fenetre principale de LithoShape3D 0.1.

Assemble les briques existantes (core Phase 1A, viewer Phase 1B) sans les
reecrire. `plotter` est injectable (comme `SceneViewer`) : en tests on passe
un `pv.Plotter(off_screen=True)`, en usage reel un `pyvistaqt.QtInteractor`
est cree automatiquement.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QAction, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from lithoshape3d.core.export.stl_export import export_stl
from lithoshape3d.core.geometry.heightmap import height_mm_from_aspect_ratio
from lithoshape3d.core.image.io import load_image
from lithoshape3d.core.image.pipeline import image_size
from lithoshape3d.core.image.preprocessing import (
    apply_brightness_contrast,
    normalize,
    resize_array,
    to_grayscale_array,
)
from lithoshape3d.core.scene.models import GeometryParameters
from lithoshape3d.ui.state import AppState
from lithoshape3d.ui.worker import GenerationWorker
from lithoshape3d.viewer.scene_viewer import DisplayMode, SceneViewer

logger = logging.getLogger("lithoshape3d.ui")

PRESETS: dict[str, dict[str, float]] = {
    "Standard": {"resolution": 0.3, "min_thickness_mm": 0.8, "max_thickness_mm": 3.0},
    "Fine": {"resolution": 0.15, "min_thickness_mm": 0.6, "max_thickness_mm": 3.0},
    "Draft": {"resolution": 0.6, "min_thickness_mm": 1.0, "max_thickness_mm": 3.0},
}

_STATE_MESSAGES = {
    AppState.NO_IMAGE: "Aucune image chargee.",
    AppState.IMAGE_LOADED: "Image chargee. Reglez les parametres puis cliquez sur Generer.",
    AppState.PARAMS_DIRTY: "Parametres modifies : le mesh affiche est perime, regenerez.",
    AppState.GENERATING: "Generation en cours...",
    AppState.MESH_READY: "Mesh genere. Vous pouvez l'exporter en STL.",
    AppState.ERROR: "Erreur lors de la generation (voir le journal).",
}


def _array_to_pixmap(array: np.ndarray) -> QPixmap:
    array_u8 = np.ascontiguousarray((np.clip(array, 0.0, 1.0) * 255).astype(np.uint8))
    height, width = array_u8.shape
    image = QImage(array_u8.data, width, height, width, QImage.Format.Format_Grayscale8)
    return QPixmap.fromImage(image.copy())


class MainWindow(QMainWindow):
    def __init__(self, plotter=None) -> None:
        super().__init__()
        self.setWindowTitle("LithoShape3D 0.1")
        self.resize(1300, 800)

        self._image_path: str | None = None
        self._image_width_px = 0
        self._image_height_px = 0
        self._current_mesh = None
        self._state = AppState.NO_IMAGE
        self._thread_pool = QThreadPool.globalInstance()

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_source_panel())

        if plotter is None:
            from pyvistaqt import QtInteractor

            plotter = QtInteractor(splitter)
        self.plotter = plotter
        viewer_widget = getattr(plotter, "interactor", None)
        if isinstance(viewer_widget, QWidget):
            splitter.addWidget(viewer_widget)
        else:
            # Plotter off-screen (tests) : pas de widget Qt a integrer, la
            # logique du viewer reste testable via `self.scene_viewer`.
            placeholder = QLabel("Viewer 3D (plotter off-screen, tests)")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            splitter.addWidget(placeholder)

        splitter.addWidget(self._build_params_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([260, 780, 260])
        root_layout.addWidget(splitter, 1)

        self.scene_viewer = SceneViewer(self.plotter)

        root_layout.addWidget(self._build_action_bar())

        self._build_menu()

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(160)
        self.statusBar().addPermanentWidget(self.progress_bar)

        self._set_state(AppState.NO_IMAGE)

    # ------------------------------------------------------------------ #
    # Construction de l'interface
    # ------------------------------------------------------------------ #
    def _build_source_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(220)
        layout = QVBoxLayout(panel)

        self.open_button = QPushButton("Ouvrir image...")
        self.open_button.clicked.connect(self._choose_image)
        layout.addWidget(self.open_button)

        self.preview_label = QLabel("Aucune image")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(200, 200)
        self.preview_label.setStyleSheet("border: 1px solid #444; background: #1e1e1e; color: #888;")
        layout.addWidget(self.preview_label, 1)

        self.filename_label = QLabel("")
        self.filename_label.setWordWrap(True)
        layout.addWidget(self.filename_label)

        self.dimensions_label = QLabel("")
        layout.addWidget(self.dimensions_label)

        layout.addStretch(0)
        return panel

    def _build_params_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(220)
        layout = QVBoxLayout(panel)
        form = QFormLayout()

        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Personnalise")
        for name in PRESETS:
            self.preset_combo.addItem(name)
        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        form.addRow("Preset", self.preset_combo)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(5.0, 500.0)
        self.width_spin.setSuffix(" mm")
        self.width_spin.setValue(100.0)
        form.addRow("Largeur", self.width_spin)

        self.height_display = QLabel("- mm")
        form.addRow("Hauteur (auto)", self.height_display)

        self.min_thickness_spin = QDoubleSpinBox()
        self.min_thickness_spin.setRange(0.1, 10.0)
        self.min_thickness_spin.setSingleStep(0.1)
        self.min_thickness_spin.setSuffix(" mm")
        self.min_thickness_spin.setValue(0.8)
        form.addRow("Epaisseur min", self.min_thickness_spin)

        self.max_thickness_spin = QDoubleSpinBox()
        self.max_thickness_spin.setRange(0.2, 15.0)
        self.max_thickness_spin.setSingleStep(0.1)
        self.max_thickness_spin.setSuffix(" mm")
        self.max_thickness_spin.setValue(3.0)
        form.addRow("Epaisseur max", self.max_thickness_spin)

        self.resolution_spin = QDoubleSpinBox()
        self.resolution_spin.setRange(0.05, 2.0)
        self.resolution_spin.setSingleStep(0.05)
        self.resolution_spin.setSuffix(" mm/px")
        self.resolution_spin.setValue(0.3)
        form.addRow("Resolution", self.resolution_spin)

        self.invert_checkbox = QCheckBox("Inverser (clair = epais)")
        form.addRow(self.invert_checkbox)

        self.contrast_spin = QDoubleSpinBox()
        self.contrast_spin.setRange(0.1, 3.0)
        self.contrast_spin.setSingleStep(0.05)
        self.contrast_spin.setValue(1.0)
        form.addRow("Contraste", self.contrast_spin)

        self.brightness_spin = QDoubleSpinBox()
        self.brightness_spin.setRange(-0.5, 0.5)
        self.brightness_spin.setSingleStep(0.02)
        self.brightness_spin.setValue(0.0)
        form.addRow("Luminosite", self.brightness_spin)

        layout.addLayout(form)

        layout.addWidget(QLabel("Affichage"))
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItem("Surface", DisplayMode.SURFACE)
        self.display_mode_combo.addItem("Fil de fer", DisplayMode.WIREFRAME)
        self.display_mode_combo.addItem("Surface + aretes", DisplayMode.SURFACE_WITH_EDGES)
        self.display_mode_combo.currentIndexChanged.connect(self._on_display_mode_changed)
        layout.addWidget(self.display_mode_combo)

        views_layout = QHBoxLayout()
        self.view_front_button = QPushButton("Face")
        self.view_front_button.clicked.connect(lambda: self.scene_viewer.view_front())
        self.view_iso_button = QPushButton("Iso")
        self.view_iso_button.clicked.connect(lambda: self.scene_viewer.view_isometric())
        self.view_reset_button = QPushButton("Reset camera")
        self.view_reset_button.clicked.connect(lambda: self.scene_viewer.reset_camera())
        for button in (self.view_front_button, self.view_iso_button, self.view_reset_button):
            views_layout.addWidget(button)
        layout.addLayout(views_layout)

        layout.addStretch(1)

        for widget, signal_name in [
            (self.width_spin, "valueChanged"),
            (self.min_thickness_spin, "valueChanged"),
            (self.max_thickness_spin, "valueChanged"),
            (self.resolution_spin, "valueChanged"),
            (self.contrast_spin, "valueChanged"),
            (self.brightness_spin, "valueChanged"),
        ]:
            getattr(widget, signal_name).connect(self._on_param_changed)
        self.invert_checkbox.toggled.connect(self._on_param_changed)
        self.width_spin.valueChanged.connect(self._update_height_display)
        self.contrast_spin.valueChanged.connect(self._update_source_preview)
        self.brightness_spin.valueChanged.connect(self._update_source_preview)
        self.invert_checkbox.toggled.connect(self._update_source_preview)

        return panel

    def _build_action_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)

        self.generate_button = QPushButton("Generer")
        self.generate_button.clicked.connect(self._on_generate_clicked)
        layout.addWidget(self.generate_button)

        self.export_button = QPushButton("Exporter STL...")
        self.export_button.clicked.connect(self._on_export_clicked)
        layout.addWidget(self.export_button)

        self.reset_button = QPushButton("Reset parametres")
        self.reset_button.clicked.connect(self._on_reset_clicked)
        layout.addWidget(self.reset_button)

        layout.addStretch(1)
        return bar

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Fichier")
        open_action = QAction("Ouvrir image", self)
        open_action.triggered.connect(self._choose_image)
        file_menu.addAction(open_action)

        export_action = QAction("Exporter STL", self)
        export_action.triggered.connect(self._on_export_clicked)
        file_menu.addAction(export_action)

        file_menu.addSeparator()
        quit_action = QAction("Quitter", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = self.menuBar().addMenu("Vue")
        view_menu.addAction("Face", lambda: self.scene_viewer.view_front())
        view_menu.addAction("Isometrique", lambda: self.scene_viewer.view_isometric())
        view_menu.addAction("Reset camera", lambda: self.scene_viewer.reset_camera())

        help_menu = self.menuBar().addMenu("Aide")
        about_action = QAction("A propos", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ------------------------------------------------------------------ #
    # Etat
    # ------------------------------------------------------------------ #
    def _set_state(self, state: AppState) -> None:
        self._state = state
        self.statusBar().showMessage(_STATE_MESSAGES[state])

        has_image = self._image_path is not None
        generating = state is AppState.GENERATING

        self.generate_button.setEnabled(has_image and not generating)
        self.export_button.setEnabled(state is AppState.MESH_READY)
        self.open_button.setEnabled(not generating)
        self.reset_button.setEnabled(not generating)
        self._params_panel_set_enabled(not generating)
        self.progress_bar.setVisible(generating)

    def _params_panel_set_enabled(self, enabled: bool) -> None:
        for widget in (
            self.width_spin,
            self.min_thickness_spin,
            self.max_thickness_spin,
            self.resolution_spin,
            self.invert_checkbox,
            self.contrast_spin,
            self.brightness_spin,
            self.preset_combo,
        ):
            widget.setEnabled(enabled)

    def _on_param_changed(self, *_args) -> None:
        if self._state is AppState.MESH_READY:
            self._set_state(AppState.PARAMS_DIRTY)
        elif self._state is AppState.ERROR:
            self._set_state(AppState.IMAGE_LOADED if self._image_path else AppState.NO_IMAGE)
        # NO_IMAGE / IMAGE_LOADED / PARAMS_DIRTY / GENERATING : pas de changement d'etat

    # ------------------------------------------------------------------ #
    # Image source
    # ------------------------------------------------------------------ #
    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une image", "", "Images (*.png *.jpg *.jpeg)"
        )
        if path:
            self._load_image(path)

    def _load_image(self, path: str) -> None:
        try:
            width_px, height_px = image_size(path)
        except (OSError, ValueError) as exc:
            logger.exception("Impossible de lire l'image")
            QMessageBox.critical(self, "LithoShape3D", f"Impossible de lire l'image :\n{exc}")
            return

        self._image_path = path
        self._image_width_px = width_px
        self._image_height_px = height_px
        self._current_mesh = None

        self.filename_label.setText(path.rsplit("/", 1)[-1])
        self.dimensions_label.setText(f"{width_px} x {height_px} px")

        self._update_height_display()
        self._update_source_preview()
        self._set_state(AppState.IMAGE_LOADED)

    def _update_height_display(self) -> None:
        if not self._image_path:
            self.height_display.setText("- mm")
            return
        height_mm = height_mm_from_aspect_ratio(
            self.width_spin.value(), self._image_width_px, self._image_height_px
        )
        self.height_display.setText(f"{height_mm:.1f} mm")

    def _update_source_preview(self) -> None:
        if not self._image_path:
            return
        image = load_image(self._image_path)
        array = to_grayscale_array(image)
        preview_width = 320
        preview_height = max(1, round(preview_width * array.shape[0] / array.shape[1]))
        array = resize_array(array, width_px=preview_width, height_px=preview_height)
        array = apply_brightness_contrast(
            array, brightness=self.brightness_spin.value(), contrast=self.contrast_spin.value()
        )
        array = normalize(array)
        if self.invert_checkbox.isChecked():
            array = 1.0 - array
        pixmap = _array_to_pixmap(array)
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    # ------------------------------------------------------------------ #
    # Parametres / presets
    # ------------------------------------------------------------------ #
    def _apply_preset(self, name: str) -> None:
        if name not in PRESETS:
            return
        preset = PRESETS[name]
        self.resolution_spin.setValue(preset["resolution"])
        self.min_thickness_spin.setValue(preset["min_thickness_mm"])
        self.max_thickness_spin.setValue(preset["max_thickness_mm"])

    def _current_geometry_parameters(self) -> GeometryParameters:
        height_mm = height_mm_from_aspect_ratio(
            self.width_spin.value(), self._image_width_px, self._image_height_px
        )
        return GeometryParameters(
            width_mm=self.width_spin.value(),
            height_mm=height_mm,
            min_thickness_mm=self.min_thickness_spin.value(),
            max_thickness_mm=self.max_thickness_spin.value(),
            invert=self.invert_checkbox.isChecked(),
            resolution=self.resolution_spin.value(),
        )

    def _on_reset_clicked(self) -> None:
        self.preset_combo.setCurrentIndex(0)
        self.width_spin.setValue(100.0)
        self.min_thickness_spin.setValue(0.8)
        self.max_thickness_spin.setValue(3.0)
        self.resolution_spin.setValue(0.3)
        self.invert_checkbox.setChecked(False)
        self.contrast_spin.setValue(1.0)
        self.brightness_spin.setValue(0.0)

    # ------------------------------------------------------------------ #
    # Generation
    # ------------------------------------------------------------------ #
    def _on_generate_clicked(self) -> None:
        if not self._image_path:
            return

        params = self._current_geometry_parameters()
        worker = GenerationWorker(
            self._image_path,
            params,
            brightness=self.brightness_spin.value(),
            contrast=self.contrast_spin.value(),
        )
        worker.signals.succeeded.connect(self._on_generation_succeeded)
        worker.signals.failed.connect(self._on_generation_failed)

        self._set_state(AppState.GENERATING)
        self._thread_pool.start(worker)

    def _on_generation_succeeded(self, mesh) -> None:
        self._current_mesh = mesh
        self.scene_viewer.show_mesh(mesh, display_mode=self.display_mode_combo.currentData())
        self.scene_viewer.view_isometric()
        self._set_state(AppState.MESH_READY)

    def _on_generation_failed(self, message: str) -> None:
        self._current_mesh = None
        self._set_state(AppState.ERROR)
        QMessageBox.warning(self, "LithoShape3D", f"La generation a echoue :\n{message}")

    def _on_display_mode_changed(self) -> None:
        if self._current_mesh is not None:
            self.scene_viewer.show_mesh(
                self._current_mesh, display_mode=self.display_mode_combo.currentData()
            )

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    def _on_export_clicked(self) -> None:
        if self._state is not AppState.MESH_READY or self._current_mesh is None:
            return

        path, _ = QFileDialog.getSaveFileName(self, "Exporter en STL", "lithophanie.stl", "STL (*.stl)")
        if not path:
            return

        try:
            export_stl(self._current_mesh, path)
        except OSError as exc:
            logger.exception("Echec de l'export STL")
            QMessageBox.critical(self, "LithoShape3D", f"Echec de l'export :\n{exc}")
            return

        logger.info("STL exporte : %s", path)
        self.statusBar().showMessage(f"Export reussi : {path}", 8000)
        QMessageBox.information(self, "LithoShape3D", f"STL exporte avec succes :\n{path}")

    # ------------------------------------------------------------------ #
    # Divers
    # ------------------------------------------------------------------ #
    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "A propos de LithoShape3D",
            "LithoShape3D 0.1\nImage -> lithophanie -> STL.\nPhase 1C.",
        )
