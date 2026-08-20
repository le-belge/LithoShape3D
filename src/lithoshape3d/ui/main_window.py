"""Fenetre principale de LithoShape3D 0.1.

Assemble les briques existantes (core Phase 1A, viewer Phase 1B) sans les
reecrire. `plotter` est injectable (comme `SceneViewer`) : en tests on passe
un `pv.Plotter(off_screen=True)`, en usage reel un `pyvistaqt.QtInteractor`
est cree automatiquement.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QAction, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
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
from lithoshape3d.core.scene.mask_io import load_zone_mask
from lithoshape3d.core.scene.models import GeometryParameters, Project, Zone
from lithoshape3d.core.scene.project_io import load_project_bundle, save_project_bundle
from lithoshape3d.ui.mask_editor_dialog import MaskEditorDialog
from lithoshape3d.ui.overlay import render_overlay, zone_color
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
    AppState.PARAMS_DIRTY: "Parametres modifies : le mesh affiche est perime.",
    AppState.GENERATING: "Generation du mesh...",
    AppState.MESH_READY: "Mesh genere. Vous pouvez l'exporter en STL.",
    AppState.ERROR: "Erreur lors de la generation (voir le journal).",
}

_STALE_BANNER_TEXT = "Apercu a regenerer"


def _array_to_pixmap(array: np.ndarray) -> QPixmap:
    array_u8 = np.ascontiguousarray((np.clip(array, 0.0, 1.0) * 255).astype(np.uint8))
    height, width = array_u8.shape
    image = QImage(array_u8.data, width, height, width, QImage.Format.Format_Grayscale8)
    return QPixmap.fromImage(image.copy())


class AspectRatioImageLabel(QLabel):
    """QLabel qui reescalonne son pixmap source au resize, sans jamais
    recalculer l'image (`set_source_pixmap` seul fait le travail couteux)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._source_pixmap: QPixmap | None = None

    def set_source_pixmap(self, pixmap: QPixmap) -> None:
        self._source_pixmap = pixmap
        self._rescale()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self) -> None:
        if self._source_pixmap is None or self._source_pixmap.isNull():
            return
        scaled = self._source_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)


class MainWindow(QMainWindow):
    def __init__(self, plotter=None) -> None:
        super().__init__()
        self.setWindowTitle("LithoShape3D 0.1")
        self.resize(1300, 800)

        self._project: Project = Project()
        self._project_bundle_dir: Path | None = None
        self._zone_masks: dict[str, np.ndarray] = {}

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

        viewer_container = QWidget()
        viewer_layout = QVBoxLayout(viewer_container)
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.setSpacing(4)

        self.stale_banner = QLabel(_STALE_BANNER_TEXT)
        self.stale_banner.setObjectName("staleBanner")
        self.stale_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stale_banner.setVisible(False)
        viewer_layout.addWidget(self.stale_banner)

        if isinstance(viewer_widget, QWidget):
            viewer_layout.addWidget(viewer_widget, 1)
        else:
            # Plotter off-screen (tests) : pas de widget Qt a integrer, la
            # logique du viewer reste testable via `self.scene_viewer`.
            placeholder = QLabel("Viewer 3D (plotter off-screen, tests)")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            viewer_layout.addWidget(placeholder, 1)

        splitter.addWidget(viewer_container)

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
        layout.setSpacing(8)

        self.open_button = QPushButton("Ouvrir image...")
        self.open_button.clicked.connect(self._choose_image)
        layout.addWidget(self.open_button)

        self.preview_label = AspectRatioImageLabel("Aucune image")
        self.preview_label.setObjectName("previewLabel")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(200, 200)
        layout.addWidget(self.preview_label, 1)

        self.filename_label = QLabel("")
        self.filename_label.setWordWrap(True)
        layout.addWidget(self.filename_label)

        self.dimensions_label = QLabel("")
        layout.addWidget(self.dimensions_label)

        zones_group = QGroupBox("Zones")
        zones_layout = QVBoxLayout(zones_group)
        zones_layout.setSpacing(6)

        self.zones_list = QListWidget()
        self.zones_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.zones_list.itemSelectionChanged.connect(self._on_zone_selection_changed)
        self.zones_list.itemChanged.connect(self._on_zone_item_changed)
        self.zones_list.model().rowsMoved.connect(self._on_zones_reordered)
        zones_layout.addWidget(self.zones_list)

        zones_buttons = QHBoxLayout()
        self.new_zone_button = QPushButton("+ Zone")
        self.new_zone_button.clicked.connect(self._on_new_zone_clicked)
        zones_buttons.addWidget(self.new_zone_button)

        self.delete_zone_button = QPushButton("Supprimer")
        self.delete_zone_button.clicked.connect(self._on_delete_zone_clicked)
        zones_buttons.addWidget(self.delete_zone_button)
        zones_layout.addLayout(zones_buttons)

        self.edit_mask_button = QPushButton("Editer le masque...")
        self.edit_mask_button.clicked.connect(self._on_edit_mask_clicked)
        zones_layout.addWidget(self.edit_mask_button)

        layout.addWidget(zones_group)

        return panel

    def _build_params_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(240)
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Personnalise")
        for name in PRESETS:
            self.preset_combo.addItem(name)
        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        layout.addWidget(self.preset_combo)

        geometry_group = QGroupBox("Geometrie")
        geometry_form = QFormLayout(geometry_group)
        geometry_form.setSpacing(8)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(5.0, 500.0)
        self.width_spin.setSuffix(" mm")
        self.width_spin.setValue(100.0)
        geometry_form.addRow("Largeur", self.width_spin)

        self.height_display = QLabel("- mm")
        geometry_form.addRow("Hauteur (ratio verrouille)", self.height_display)

        self.min_thickness_spin = QDoubleSpinBox()
        self.min_thickness_spin.setRange(0.1, 10.0)
        self.min_thickness_spin.setSingleStep(0.1)
        self.min_thickness_spin.setSuffix(" mm")
        self.min_thickness_spin.setValue(0.8)
        geometry_form.addRow("Epaisseur min", self.min_thickness_spin)

        self.max_thickness_spin = QDoubleSpinBox()
        self.max_thickness_spin.setRange(0.2, 15.0)
        self.max_thickness_spin.setSingleStep(0.1)
        self.max_thickness_spin.setSuffix(" mm")
        self.max_thickness_spin.setValue(3.0)
        geometry_form.addRow("Epaisseur max", self.max_thickness_spin)

        self.resolution_spin = QDoubleSpinBox()
        self.resolution_spin.setRange(0.05, 2.0)
        self.resolution_spin.setSingleStep(0.05)
        self.resolution_spin.setSuffix(" mm/px")
        self.resolution_spin.setValue(0.3)
        geometry_form.addRow("Resolution", self.resolution_spin)

        layout.addWidget(geometry_group)

        image_group = QGroupBox("Image")
        image_form = QFormLayout(image_group)
        image_form.setSpacing(8)

        self.invert_checkbox = QCheckBox("Inverser (clair = epais)")
        image_form.addRow(self.invert_checkbox)

        self.contrast_spin = QDoubleSpinBox()
        self.contrast_spin.setRange(0.1, 3.0)
        self.contrast_spin.setSingleStep(0.05)
        self.contrast_spin.setValue(1.0)
        image_form.addRow("Contraste", self.contrast_spin)

        self.brightness_spin = QDoubleSpinBox()
        self.brightness_spin.setRange(-0.5, 0.5)
        self.brightness_spin.setSingleStep(0.02)
        self.brightness_spin.setValue(0.0)
        image_form.addRow("Luminosite", self.brightness_spin)

        layout.addWidget(image_group)

        display_group = QGroupBox("Affichage")
        display_layout = QVBoxLayout(display_group)
        display_layout.setSpacing(8)

        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItem("Surface", DisplayMode.SURFACE)
        self.display_mode_combo.addItem("Fil de fer", DisplayMode.WIREFRAME)
        self.display_mode_combo.addItem("Surface + aretes", DisplayMode.SURFACE_WITH_EDGES)
        self.display_mode_combo.currentIndexChanged.connect(self._on_display_mode_changed)
        display_layout.addWidget(self.display_mode_combo)

        views_layout = QHBoxLayout()
        views_layout.setSpacing(6)
        self.view_front_button = QPushButton("Face")
        self.view_front_button.clicked.connect(lambda: self.scene_viewer.view_front())
        self.view_iso_button = QPushButton("Iso")
        self.view_iso_button.clicked.connect(lambda: self.scene_viewer.view_isometric())
        self.view_reset_button = QPushButton("Reset")
        self.view_reset_button.setToolTip("Reinitialiser la camera")
        self.view_reset_button.clicked.connect(lambda: self.scene_viewer.reset_camera())
        for button in (self.view_front_button, self.view_iso_button, self.view_reset_button):
            views_layout.addWidget(button)
        display_layout.addLayout(views_layout)

        layout.addWidget(display_group)
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
        self.generate_button.setObjectName("generateButton")
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

        new_project_action = QAction("Nouveau projet", self)
        new_project_action.setShortcut(QKeySequence.StandardKey.New)
        new_project_action.triggered.connect(self._on_new_project)
        file_menu.addAction(new_project_action)

        open_project_action = QAction("Ouvrir projet...", self)
        open_project_action.triggered.connect(self._on_open_project)
        file_menu.addAction(open_project_action)

        save_project_action = QAction("Enregistrer", self)
        save_project_action.setShortcut(QKeySequence.StandardKey.Save)
        save_project_action.triggered.connect(self._on_save_project)
        file_menu.addAction(save_project_action)

        save_project_as_action = QAction("Enregistrer sous...", self)
        save_project_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_project_as_action.triggered.connect(self._on_save_project_as)
        file_menu.addAction(save_project_as_action)

        file_menu.addSeparator()

        self.open_action = QAction("Ouvrir image", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self._choose_image)
        file_menu.addAction(self.open_action)

        self.generate_action = QAction("Generer", self)
        self.generate_action.setShortcut(QKeySequence("Ctrl+R"))
        self.generate_action.triggered.connect(self._on_generate_clicked)
        file_menu.addAction(self.generate_action)

        self.export_action = QAction("Exporter STL", self)
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_action.triggered.connect(self._on_export_clicked)
        file_menu.addAction(self.export_action)

        file_menu.addSeparator()
        quit_action = QAction("Quitter", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
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
        self.stale_banner.setVisible(state is AppState.PARAMS_DIRTY)

        has_image = self._image_path is not None
        generating = state is AppState.GENERATING
        can_generate = has_image and not generating
        can_export = state is AppState.MESH_READY

        self.generate_button.setEnabled(can_generate)
        self.generate_action.setEnabled(can_generate)
        self.export_button.setEnabled(can_export)
        self.export_action.setEnabled(can_export)
        self.open_button.setEnabled(not generating)
        self.open_action.setEnabled(not generating)
        self.reset_button.setEnabled(not generating)
        self._params_panel_set_enabled(not generating)
        self.progress_bar.setVisible(generating)

        self.new_zone_button.setEnabled(has_image and not generating)
        self.delete_zone_button.setEnabled(not generating and self._active_zone() is not None)
        self.edit_mask_button.setEnabled(not generating and self._active_zone() is not None)
        self.zones_list.setEnabled(not generating)

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
        zone = self._active_zone()
        if zone is not None and self._image_path:
            zone.geometry_params = self._current_geometry_parameters()

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
        self._project.scene.source_image_path = path

        self.filename_label.setText(path.rsplit("/", 1)[-1])
        self.dimensions_label.setText(f"{width_px} x {height_px} px")

        self._ensure_default_zone()
        self._refresh_zones_list()
        self._update_height_display()
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

        zone = self._active_zone()
        if zone is not None:
            mask_preview = self._zone_mask_at_shape(zone, array.shape)
            index = self._project.scene.zones.index(zone)
            pixmap = render_overlay(array, mask_preview, zone_color(index), alpha=0.4)
        else:
            pixmap = _array_to_pixmap(array)
        self.preview_label.set_source_pixmap(pixmap)

    # ------------------------------------------------------------------ #
    # Zones
    # ------------------------------------------------------------------ #
    def _active_zone(self) -> Zone | None:
        zone_id = self._project.scene.active_zone_id
        return next((z for z in self._project.scene.zones if z.id == zone_id), None)

    def _ensure_default_zone(self) -> None:
        """Zone "Lithophanie" auto-creee uniquement si aucune zone n'existe
        deja (nouveau workflow) -- un projet rouvert n'est jamais ecrase."""
        if self._project.scene.zones:
            return
        zone = Zone(name="Lithophanie", geometry_params=self._current_geometry_parameters())
        self._project.scene.zones.append(zone)
        self._project.scene.active_zone_id = zone.id

    def _zone_mask_at_shape(self, zone: Zone, shape: tuple[int, int]) -> np.ndarray:
        """Masque float32 [0,1] de `zone` redimensionne a `shape`, sans
        jamais modifier le masque source stocke."""
        mask = self._zone_masks.get(zone.id)
        if mask is None:
            if zone.mask_path and self._project_bundle_dir is not None:
                mask = load_zone_mask(self._project_bundle_dir, zone, shape=shape)
            else:
                mask = np.ones(shape, dtype=np.float32)
        if mask.shape != shape:
            mask = resize_array(mask, width_px=shape[1], height_px=shape[0])
        return mask

    def _active_zone_mask_for_generation(self, zone: Zone) -> np.ndarray | None:
        """None si la zone n'a jamais ete touchee (comportement historique,
        aucune verification necessaire -- pas de fichier, pas de masque)."""
        if zone.id in self._zone_masks:
            return self._zone_masks[zone.id]
        if zone.mask_path is None or self._project_bundle_dir is None:
            return None
        width_px, height_px = image_size(self._image_path)
        return load_zone_mask(self._project_bundle_dir, zone, shape=(height_px, width_px))

    def _refresh_zones_list(self) -> None:
        self.zones_list.blockSignals(True)
        self.zones_list.clear()
        for zone in self._project.scene.zones:
            item = QListWidgetItem(zone.name)
            item.setFlags(
                item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(Qt.CheckState.Checked if zone.visible else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, zone.id)
            self.zones_list.addItem(item)
            if zone.id == self._project.scene.active_zone_id:
                self.zones_list.setCurrentItem(item)
        self.zones_list.blockSignals(False)

        self._load_zone_params_into_panel(self._active_zone())
        self._update_source_preview()
        self._set_state(self._state)  # rafraichit l'activation des boutons zones

    def _load_zone_params_into_panel(self, zone: Zone | None) -> None:
        if zone is None:
            return
        params = zone.geometry_params
        self.width_spin.setValue(params.width_mm)
        self.min_thickness_spin.setValue(params.min_thickness_mm)
        self.max_thickness_spin.setValue(params.max_thickness_mm)
        self.resolution_spin.setValue(params.resolution)
        self.invert_checkbox.setChecked(params.invert)
        self._update_height_display()

    def _on_zone_selection_changed(self) -> None:
        item = self.zones_list.currentItem()
        if item is None:
            return
        self._project.scene.active_zone_id = item.data(Qt.ItemDataRole.UserRole)
        self._load_zone_params_into_panel(self._active_zone())
        self._update_source_preview()
        self._set_state(self._state)

    def _on_zone_item_changed(self, item: QListWidgetItem) -> None:
        zone_id = item.data(Qt.ItemDataRole.UserRole)
        zone = next((z for z in self._project.scene.zones if z.id == zone_id), None)
        if zone is None:
            return
        zone.name = item.text()
        zone.visible = item.checkState() == Qt.CheckState.Checked
        self._update_source_preview()

    def _on_zones_reordered(self, *_args) -> None:
        ordered_ids = [
            self.zones_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.zones_list.count())
        ]
        zones_by_id = {zone.id: zone for zone in self._project.scene.zones}
        self._project.scene.zones = [zones_by_id[zid] for zid in ordered_ids if zid in zones_by_id]

    def _on_new_zone_clicked(self) -> None:
        if not self._image_path:
            return
        index = len(self._project.scene.zones) + 1
        zone = Zone(name=f"Zone {index}", geometry_params=self._current_geometry_parameters())
        self._project.scene.zones.append(zone)
        self._project.scene.active_zone_id = zone.id
        self._refresh_zones_list()

    def _on_delete_zone_clicked(self) -> None:
        zone = self._active_zone()
        if zone is None:
            return
        self._project.scene.zones.remove(zone)
        self._zone_masks.pop(zone.id, None)
        remaining = self._project.scene.zones
        self._project.scene.active_zone_id = remaining[0].id if remaining else None
        self._refresh_zones_list()

    def _on_edit_mask_clicked(self) -> None:
        zone = self._active_zone()
        if zone is None or not self._image_path:
            return

        image = load_image(self._image_path)
        base_array = to_grayscale_array(image)  # resolution native, jamais modifiee

        mask = self._zone_masks.get(zone.id)
        if mask is None:
            if zone.mask_path and self._project_bundle_dir is not None:
                mask = load_zone_mask(self._project_bundle_dir, zone, shape=base_array.shape)
            else:
                mask = np.ones(base_array.shape, dtype=np.float32)

        index = self._project.scene.zones.index(zone)
        dialog = MaskEditorDialog(zone.name, base_array, mask, zone_color(index), parent=self)
        if dialog.exec():
            self._zone_masks[zone.id] = dialog.resulting_mask()
            self._update_source_preview()

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

        zone = self._active_zone()
        params = self._current_geometry_parameters()
        mask = self._active_zone_mask_for_generation(zone) if zone is not None else None
        worker = GenerationWorker(
            self._image_path,
            params,
            brightness=self.brightness_spin.value(),
            contrast=self.contrast_spin.value(),
            mask=mask,
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
    def _suggested_stl_filename(self) -> str:
        def _slug(text: str) -> str:
            cleaned = "".join(c if c.isalnum() else "-" for c in text.strip())
            cleaned = "-".join(filter(None, cleaned.split("-")))
            return cleaned or "sans-titre"

        project_name = _slug(self._project.name)
        zone = self._active_zone()
        if zone is not None:
            return f"{project_name}_{_slug(zone.name)}.stl"
        return f"{project_name}.stl"

    def _on_export_clicked(self) -> None:
        if self._state is not AppState.MESH_READY or self._current_mesh is None:
            return

        suggested_name = self._suggested_stl_filename()
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en STL", suggested_name, "STL (*.stl)")
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
    # Projet
    # ------------------------------------------------------------------ #
    def _on_new_project(self) -> None:
        self._project = Project()
        self._project_bundle_dir = None
        self._zone_masks = {}
        self._image_path = None
        self._image_width_px = 0
        self._image_height_px = 0
        self._current_mesh = None

        self.filename_label.setText("")
        self.dimensions_label.setText("")
        self.preview_label.set_source_pixmap(QPixmap())
        self._refresh_zones_list()
        self._set_state(AppState.NO_IMAGE)

    def _on_open_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Ouvrir un projet LithoShape3D")
        if not directory:
            return

        try:
            project = load_project_bundle(directory)
        except (OSError, ValueError, KeyError) as exc:
            logger.exception("Impossible d'ouvrir le projet")
            QMessageBox.critical(self, "LithoShape3D", f"Impossible d'ouvrir le projet :\n{exc}")
            return

        self._project = project
        self._project_bundle_dir = Path(directory)
        self._zone_masks = {}
        self._current_mesh = None

        if project.scene.source_image_path:
            self._image_path = str(self._project_bundle_dir / project.scene.source_image_path)
            try:
                self._image_width_px, self._image_height_px = image_size(self._image_path)
            except (OSError, ValueError):
                self._image_width_px = self._image_height_px = 0
            self.filename_label.setText(Path(self._image_path).name)
            self.dimensions_label.setText(f"{self._image_width_px} x {self._image_height_px} px")
        else:
            self._image_path = None
            self.filename_label.setText("")
            self.dimensions_label.setText("")

        self._refresh_zones_list()
        self._set_state(AppState.IMAGE_LOADED if self._image_path else AppState.NO_IMAGE)

    def _on_save_project(self) -> None:
        if self._project_bundle_dir is None:
            self._on_save_project_as()
            return
        self._save_project_to(self._project_bundle_dir)

    def _on_save_project_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le projet", "MonProjet.l3dproj", "Projet LithoShape3D (*.l3dproj)"
        )
        if not path:
            return
        self._save_project_to(Path(path))

    def _save_project_to(self, bundle_dir: Path) -> None:
        try:
            save_project_bundle(self._project, bundle_dir, dirty_masks=self._zone_masks)
        except OSError as exc:
            logger.exception("Echec de l'enregistrement du projet")
            QMessageBox.critical(self, "LithoShape3D", f"Echec de l'enregistrement :\n{exc}")
            return

        self._project_bundle_dir = Path(bundle_dir)
        self._zone_masks.clear()
        if self._project.scene.source_image_path:
            self._image_path = str(self._project_bundle_dir / self._project.scene.source_image_path)

        self.statusBar().showMessage(f"Projet enregistre : {bundle_dir}", 8000)

    # ------------------------------------------------------------------ #
    # Divers
    # ------------------------------------------------------------------ #
    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "A propos de LithoShape3D",
            "LithoShape3D 0.1\nImage -> lithophanie -> STL.",
        )
