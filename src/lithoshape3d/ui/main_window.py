"""Fenetre principale de LithoShape3D.

Assemble les briques existantes (core Phase 1A, viewer Phase 1B) sans les
reecrire. `plotter` est injectable (comme `SceneViewer`) : en tests on passe
un `pv.Plotter(off_screen=True)`, en usage reel un `pyvistaqt.QtInteractor`
est cree automatiquement.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QAction, QColor, QImage, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from lithoshape3d.core.export.multi_material_export import (
    export_multi_material_3mf,
    export_stl_per_material,
)
from lithoshape3d.core.export.stl_export import export_stl
from lithoshape3d.core.geometry.backlight import BacklightComposition
from lithoshape3d.core.geometry.composition import ZoneSource
from lithoshape3d.core.geometry.heightmap import grid_dimensions, height_mm_from_aspect_ratio
from lithoshape3d.core.geometry.materials import partition_mesh_by_material
from lithoshape3d.core.geometry.shape import (
    apply_border,
    build_shape_mask,
    build_shape_mask_from_image_array,
    count_connected_components,
)
from lithoshape3d.core.geometry.support import build_side_stabilizer_pair, build_support_mesh
from lithoshape3d.core.image.io import load_image
from lithoshape3d.core.image.pipeline import image_size
from lithoshape3d.core.image.preprocessing import (
    apply_brightness_contrast,
    normalize,
    resize_array,
    to_grayscale_array,
)
from lithoshape3d.core.scene.mask_io import load_zone_mask
from lithoshape3d.core.scene.models import (
    BacklightInsertParams,
    ColorStrategy,
    CompositionMode,
    GeometryParameters,
    ImageTransform,
    Project,
    ReliefMode,
    ShapeType,
    SupportType,
    Zone,
)
from lithoshape3d.core.scene.project_io import load_project_bundle, save_project_bundle
from lithoshape3d.core.validation.printability import check_printability
from lithoshape3d.ui.mask_editor_dialog import MaskEditorDialog
from lithoshape3d.ui.overlay import render_overlay, zone_color
from lithoshape3d.ui.state import AppState
from lithoshape3d.ui.worker import BacklightCompositionWorker, CompositionWorker, GenerationWorker
from lithoshape3d.viewer.scene_viewer import DisplayMode, SceneViewer

logger = logging.getLogger("lithoshape3d.ui")

PRESETS: dict[str, dict[str, float]] = {
    "Standard": {"resolution": 0.3, "min_thickness_mm": 0.8, "max_thickness_mm": 3.0},
    "Fine": {"resolution": 0.15, "min_thickness_mm": 0.6, "max_thickness_mm": 3.0},
    "Draft": {"resolution": 0.6, "min_thickness_mm": 1.0, "max_thickness_mm": 3.0},
    # Boitier tiers "Cadre Lithophane CMYK Bambu" (hugo.workshop, MakerWorld
    # #1036463) -- epaisseur max 3.2mm = jeu exact de la fente du cadre pour
    # une litho mono. La largeur seule ne garantit pas 104mm de hauteur (la
    # hauteur suit toujours le ratio de la photo, cf. _current_geometry_parameters) :
    # cadrer la photo en 140:104 (~1.346:1) via Forme > Rectangle pour un
    # ajustement exact au cadre.
    "LithoGift Bambu Mono (140x104mm)": {
        "resolution": 0.2, "min_thickness_mm": 0.8, "max_thickness_mm": 3.2, "width_mm": 140.0,
    },
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


def _create_segmentation_backend():
    """None uniquement si la dependance IA (coremltools) est absente. Si
    presente mais que le modele n'est pas encore telecharge, on renvoie
    quand meme une instance : `MaskEditorDialog` proposera le telechargement
    a la demande (voir mask_editor_dialog._offer_model_download)."""
    try:
        from lithoshape3d.ai.segmentation.sam2_coreml_backend import Sam2CoreMLBackend
    except ImportError:
        logger.info("Selection intelligente indisponible : dependance IA non installee.")
        return None
    return Sam2CoreMLBackend()


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


class _ZoomGraphicsView(QGraphicsView):
    """Vue avec zoom a la molette (centre sous le curseur) et deplacement a
    la main (drag) -- comportement standard d'un visualiseur d'image."""

    _ZOOM_STEP = 1.15
    _MIN_SCALE = 0.1
    _MAX_SCALE = 20.0

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self._scale = 1.0

    def wheelEvent(self, event) -> None:
        factor = self._ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / self._ZOOM_STEP
        new_scale = self._scale * factor
        if not (self._MIN_SCALE <= new_scale <= self._MAX_SCALE):
            return
        self._scale = new_scale
        self.scale(factor, factor)


class ImageZoomDialog(QDialog):
    """Fenetre de previsualisation zoomable/deplacable -- molette pour
    zoomer, glisser pour deplacer. Ouverte a la demande (bouton "Zoom" sous
    l'apercu), jamais automatiquement."""

    def __init__(self, pixmap: QPixmap, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.view = _ZoomGraphicsView()
        scene = QGraphicsScene(self)
        scene.addPixmap(pixmap)
        self.view.setScene(scene)
        layout.addWidget(self.view)

        hint = QLabel("Molette : zoomer -- glisser : deplacer")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(hint)

        self._scene_rect = scene.itemsBoundingRect()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.view.fitInView(self._scene_rect, Qt.AspectRatioMode.KeepAspectRatio)


class MainWindow(QMainWindow):
    def __init__(self, plotter=None) -> None:
        super().__init__()
        from lithoshape3d import __version__

        self.setWindowTitle(f"LithoShape3D {__version__}")
        self.resize(1300, 800)

        self._project: Project = Project()
        self._project_bundle_dir: Path | None = None
        self._zone_masks: dict[str, np.ndarray] = {}

        self._image_path: str | None = None
        self._image_width_px = 0
        self._image_height_px = 0
        self._current_mesh = None
        self._current_panel_z_max: float | None = None
        self._current_material_meshes: dict[str, object] | None = None
        self._current_backlight_result: BacklightComposition | None = None
        self._state = AppState.NO_IMAGE
        self._thread_pool = QThreadPool.globalInstance()
        self._segmentation_backend = _create_segmentation_backend()

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)  # aucun panneau ne doit pouvoir disparaitre a 0px
        splitter.addWidget(self._build_source_panel())

        if plotter is None:
            from pyvistaqt import QtInteractor

            plotter = QtInteractor(splitter)
        self.plotter = plotter
        viewer_widget = getattr(plotter, "interactor", None)

        viewer_container = QWidget()
        viewer_container.setMinimumWidth(240)
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
        splitter.setSizes([260, 740, 320])
        root_layout.addWidget(splitter, 1)

        self.scene_viewer = SceneViewer(self.plotter)

        root_layout.addWidget(self._build_action_bar())

        self._build_menu()

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(160)
        self.statusBar().addPermanentWidget(self.progress_bar)

        self._load_support_into_panel()
        self._load_shape_into_panel()
        self._set_state(AppState.NO_IMAGE)

        # Taille minimale globale = somme des minimums des 3 colonnes du
        # splitter (source/viewer/parametres) : en dessous, un panneau
        # deviendrait inutilisable quel que soit le partage de l'espace.
        self.setMinimumSize(800, 500)

    def closeEvent(self, event) -> None:
        """Finalise proprement le render window VTK avant que Qt ne detruise
        la fenetre native -- sans cela, un rendu VTK mis en file d'attente
        (timer/queued signal) peut s'executer apres coup et segfaulter en
        touchant une fenetre Cocoa deja liberee (crash observe sur macOS)."""
        plotter = getattr(self, "plotter", None)
        if plotter is not None and hasattr(plotter, "close"):
            try:
                plotter.close()
            except Exception:
                logger.exception("Erreur a la fermeture du viewer 3D")
        super().closeEvent(event)

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

        self.zoom_preview_button = QPushButton("Zoom apercu...")
        self.zoom_preview_button.setEnabled(False)
        self.zoom_preview_button.clicked.connect(self._on_zoom_preview_clicked)
        layout.addWidget(self.zoom_preview_button)

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
        """Enveloppe dans une QScrollArea verticale : le nombre de groupes
        (Relief/Composition/Materiau/Geometrie/Image/Support/Affichage) peut
        depasser la hauteur disponible sur un ecran plus petit que celui du
        developpeur -- sans ca, les derniers controles (Affichage, boutons de
        vue) deviennent inaccessibles sans aucun scroll (bug utilisateur
        constate sur le premier vrai test de la 0.3.0)."""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.params_scroll_area = scroll_area

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Personnalise")
        for name in PRESETS:
            self.preset_combo.addItem(name)
        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        layout.addWidget(self.preset_combo)

        relief_group = QGroupBox("Relief")
        relief_form = QFormLayout(relief_group)
        relief_form.setSpacing(8)
        self.relief_mode_combo = QComboBox()
        self.relief_mode_combo.addItem("Lithophanie", ReliefMode.LITHOPHANE)
        self.relief_mode_combo.addItem("Relief (amplitude)", ReliefMode.RELIEF)
        self.relief_mode_combo.addItem("Solide (hauteur constante)", ReliefMode.SOLID)
        relief_form.addRow("Type", self.relief_mode_combo)
        layout.addWidget(relief_group)

        composition_group = QGroupBox("Composition")
        composition_form = QFormLayout(composition_group)
        composition_form.setSpacing(8)
        self.composition_mode_combo = QComboBox()
        self.composition_mode_combo.addItem("Base", CompositionMode.BASE)
        self.composition_mode_combo.addItem("Ajouter", CompositionMode.ADD)
        self.composition_mode_combo.addItem("Remplacer", CompositionMode.REPLACE)
        composition_form.addRow("Mode", self.composition_mode_combo)
        layout.addWidget(composition_group)

        material_group = QGroupBox("Materiau (impression)")
        material_form = QFormLayout(material_group)
        material_form.setSpacing(8)

        self.material_name_edit = QLineEdit()
        self.material_name_edit.setPlaceholderText("ex. Blanc, Rose...")
        material_form.addRow("Nom", self.material_name_edit)

        self.material_color_button = QPushButton()
        self.material_color_button.setFixedWidth(60)
        self.material_color_button.clicked.connect(self._on_pick_material_color)
        material_form.addRow("Couleur", self.material_color_button)

        self.material_filament_combo = QComboBox()
        self.material_filament_combo.addItem("(non specifie)", None)
        for filament_type in ("PLA", "PETG", "TPU", "Autre"):
            self.material_filament_combo.addItem(filament_type, filament_type)
        material_form.addRow("Type", self.material_filament_combo)

        self.material_slot_spin = QSpinBox()
        self.material_slot_spin.setRange(-1, 15)
        self.material_slot_spin.setSpecialValueText("Aucun")
        material_form.addRow("Slot filament", self.material_slot_spin)

        layout.addWidget(material_group)

        color_strategy_group = QGroupBox("Strategie couleur")
        color_strategy_form = QFormLayout(color_strategy_group)
        color_strategy_form.setSpacing(8)

        self.color_strategy_combo = QComboBox()
        self.color_strategy_combo.addItem("Materiau seul", ColorStrategy.MATERIAL_ONLY)
        self.color_strategy_combo.addItem("Insert retro-eclaire", ColorStrategy.BACKLIGHT_INSERT)
        self.color_strategy_combo.setToolTip(
            "Materiau seul : assigner un materiau/une couleur a cette zone ne "
            "change jamais la geometrie deja composee.\n"
            "Insert retro-eclaire : conserve une fine peau blanche en facade et "
            "genere un insert colore independant a placer derriere."
        )
        color_strategy_form.addRow("Mode", self.color_strategy_combo)

        self.backlight_skin_spin = QDoubleSpinBox()
        self.backlight_skin_spin.setRange(0.05, 2.0)
        self.backlight_skin_spin.setSingleStep(0.05)
        self.backlight_skin_spin.setSuffix(" mm")
        self.backlight_skin_spin.setValue(BacklightInsertParams().white_skin_thickness_mm)
        self.backlight_skin_spin.setToolTip("Valeur experimentale, a valider par de vraies impressions.")
        color_strategy_form.addRow("Epaisseur peau blanche", self.backlight_skin_spin)

        self.backlight_insert_thickness_spin = QDoubleSpinBox()
        self.backlight_insert_thickness_spin.setRange(0.1, 2.0)
        self.backlight_insert_thickness_spin.setSingleStep(0.05)
        self.backlight_insert_thickness_spin.setSuffix(" mm")
        self.backlight_insert_thickness_spin.setValue(0.60)
        self.backlight_insert_thickness_spin.setToolTip("Valeur experimentale, a valider par de vraies impressions.")
        color_strategy_form.addRow("Epaisseur insert", self.backlight_insert_thickness_spin)

        self.backlight_clearance_combo = QComboBox()
        self.backlight_clearance_combo.addItem("Serre (0.10 mm)", 0.10)
        self.backlight_clearance_combo.addItem("Standard (0.20 mm)", 0.20)
        self.backlight_clearance_combo.addItem("Facile (0.30 mm)", 0.30)
        self.backlight_clearance_combo.setCurrentIndex(1)
        self.backlight_clearance_combo.setToolTip(
            "Jeu lateral entre l'insert et la cavite -- valeurs experimentales."
        )
        color_strategy_form.addRow("Jeu XY", self.backlight_clearance_combo)

        layout.addWidget(color_strategy_group)

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

        shape_group = QGroupBox("Forme")
        shape_layout = QVBoxLayout(shape_group)
        shape_layout.setSpacing(8)
        shape_form = QFormLayout()
        shape_form.setSpacing(8)

        self.shape_type_combo = QComboBox()
        self.shape_type_combo.addItem("Rectangle", ShapeType.RECTANGLE)
        self.shape_type_combo.addItem("Cercle", ShapeType.CIRCLE)
        self.shape_type_combo.addItem("Ovale", ShapeType.OVAL)
        self.shape_type_combo.addItem("Coeur", ShapeType.HEART)
        self.shape_type_combo.addItem("Etoile", ShapeType.STAR)
        self.shape_type_combo.addItem("Texte", ShapeType.TEXT)
        self.shape_type_combo.addItem("SVG", ShapeType.SVG)
        self.shape_type_combo.addItem("Image", ShapeType.IMAGE)
        self.shape_type_combo.currentIndexChanged.connect(self._on_shape_changed)
        shape_form.addRow("Type", self.shape_type_combo)

        self.shape_text_edit = QLineEdit()
        self.shape_text_edit.setPlaceholderText("ex. M, LOVE, 2026...")
        self.shape_text_edit.editingFinished.connect(self._on_shape_changed)
        shape_form.addRow("Texte", self.shape_text_edit)

        self.shape_bold_checkbox = QCheckBox("Gras")
        self.shape_bold_checkbox.toggled.connect(self._on_shape_changed)
        shape_form.addRow("", self.shape_bold_checkbox)

        self.shape_border_spin = QDoubleSpinBox()
        self.shape_border_spin.setRange(0.0, 20.0)
        self.shape_border_spin.setSingleStep(0.5)
        self.shape_border_spin.setSuffix(" mm")
        self.shape_border_spin.valueChanged.connect(self._on_shape_changed)
        shape_form.addRow("Bordure", self.shape_border_spin)

        shape_layout.addLayout(shape_form)

        self.shape_import_button = QPushButton("Importer SVG/image...")
        self.shape_import_button.clicked.connect(self._on_import_shape_source_clicked)
        shape_layout.addWidget(self.shape_import_button)

        self.shape_source_label = QLabel("")
        self.shape_source_label.setWordWrap(True)
        shape_layout.addWidget(self.shape_source_label)

        self.shape_info_label = QLabel("")
        self.shape_info_label.setWordWrap(True)
        shape_layout.addWidget(self.shape_info_label)

        self.cadrage_button = QPushButton("Cadrer la photo...")
        self.cadrage_button.clicked.connect(self._on_cadrage_clicked)
        shape_layout.addWidget(self.cadrage_button)

        layout.addWidget(shape_group)

        support_group = QGroupBox("Support d'impression")
        support_form = QFormLayout(support_group)
        support_form.setSpacing(8)

        self.support_type_combo = QComboBox()
        self.support_type_combo.addItem("Aucun", SupportType.NONE)
        self.support_type_combo.addItem("Pied plat", SupportType.FLAT)
        self.support_type_combo.addItem("Pied renforce", SupportType.REINFORCED)
        support_form.addRow("Type", self.support_type_combo)

        self.support_height_spin = QDoubleSpinBox()
        self.support_height_spin.setRange(2.0, 60.0)
        self.support_height_spin.setSuffix(" mm")
        self.support_height_spin.setValue(8.0)
        support_form.addRow("Hauteur du pied", self.support_height_spin)

        self.support_depth_spin = QDoubleSpinBox()
        self.support_depth_spin.setRange(5.0, 100.0)
        self.support_depth_spin.setSuffix(" mm")
        self.support_depth_spin.setValue(25.0)
        support_form.addRow("Profondeur du pied", self.support_depth_spin)

        self.support_overhang_left_spin = QDoubleSpinBox()
        self.support_overhang_left_spin.setRange(0.0, 50.0)
        self.support_overhang_left_spin.setSuffix(" mm")
        self.support_overhang_left_spin.setValue(5.0)
        support_form.addRow("Debord gauche", self.support_overhang_left_spin)

        self.support_overhang_right_spin = QDoubleSpinBox()
        self.support_overhang_right_spin.setRange(0.0, 50.0)
        self.support_overhang_right_spin.setSuffix(" mm")
        self.support_overhang_right_spin.setValue(5.0)
        support_form.addRow("Debord droit", self.support_overhang_right_spin)

        self.support_side_stabilizers_checkbox = QCheckBox(
            "Stabilisateurs lateraux (detachables, aide a l'impression debout)"
        )
        self.support_side_stabilizers_checkbox.setToolTip(
            "Deux corps separes qui effleurent les bords gauche/droit du panneau -- "
            "jamais fusionnes, a detacher apres impression. Inspire du modele "
            "communautaire 'Lithophane Helper'."
        )
        support_form.addRow("", self.support_side_stabilizers_checkbox)

        layout.addWidget(support_group)

        display_group = QGroupBox("Affichage")
        display_layout = QVBoxLayout(display_group)
        display_layout.setSpacing(8)

        view_scope_layout = QHBoxLayout()
        view_scope_layout.setSpacing(6)
        self.view_zone_button = QPushButton("Zone active")
        self.view_zone_button.setCheckable(True)
        self.view_zone_button.setChecked(True)
        self.view_composition_button = QPushButton("Composition")
        self.view_composition_button.setCheckable(True)
        self.view_scope_group = QButtonGroup(self)
        self.view_scope_group.setExclusive(True)
        self.view_scope_group.addButton(self.view_zone_button)
        self.view_scope_group.addButton(self.view_composition_button)
        view_scope_layout.addWidget(self.view_zone_button)
        view_scope_layout.addWidget(self.view_composition_button)
        display_layout.addLayout(view_scope_layout)

        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItem("Surface", DisplayMode.SURFACE)
        self.display_mode_combo.addItem("Fil de fer", DisplayMode.WIREFRAME)
        self.display_mode_combo.addItem("Surface + aretes", DisplayMode.SURFACE_WITH_EDGES)
        self.display_mode_combo.addItem("Apercu retro-eclaire", DisplayMode.BACKLIGHT_PREVIEW)
        self.display_mode_combo.addItem("Materiaux", DisplayMode.MATERIALS)
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
        self.relief_mode_combo.currentIndexChanged.connect(self._on_zone_role_changed)
        self.composition_mode_combo.currentIndexChanged.connect(self._on_zone_role_changed)
        self.material_name_edit.editingFinished.connect(self._on_material_changed)
        self.material_filament_combo.currentIndexChanged.connect(self._on_material_changed)
        self.material_slot_spin.valueChanged.connect(self._on_material_changed)
        self.color_strategy_combo.currentIndexChanged.connect(self._on_color_strategy_changed)
        self.backlight_skin_spin.valueChanged.connect(self._on_color_strategy_changed)
        self.backlight_insert_thickness_spin.valueChanged.connect(self._on_color_strategy_changed)
        self.backlight_clearance_combo.currentIndexChanged.connect(self._on_color_strategy_changed)
        self.support_type_combo.currentIndexChanged.connect(self._on_support_changed)
        for spin in (
            self.support_height_spin,
            self.support_depth_spin,
            self.support_overhang_left_spin,
            self.support_overhang_right_spin,
        ):
            spin.valueChanged.connect(self._on_support_changed)
        self.support_side_stabilizers_checkbox.toggled.connect(self._on_support_changed)

        scroll_area.setWidget(panel)
        # Largeur minimale calculee (pas figee en dur) : sans elle, avec
        # ScrollBarAlwaysOff, un contenu plus large que la colonne allouee
        # par le splitter est simplement ROGNE (les suffixes " mm"/" mm/px"
        # des spinbox disparaissent) au lieu de rester lisible -- bug
        # constate par l'utilisateur juste apres l'ajout du scroll vertical.
        # On reserve donc explicitement la largeur naturelle du contenu +
        # celle de la scrollbar verticale (qui grignote sinon le viewport).
        scrollbar_width = scroll_area.verticalScrollBar().sizeHint().width()
        scroll_area.setMinimumWidth(panel.minimumSizeHint().width() + scrollbar_width)
        return scroll_area

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

        self.export_multi_material_button = QPushButton("Exporter multi-materiaux...")
        self.export_multi_material_button.clicked.connect(self._on_export_multi_material_clicked)
        layout.addWidget(self.export_multi_material_button)

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

        tools_menu = self.menuBar().addMenu("Outils")
        lightbox_letters_action = QAction("LightBox Letters...", self)
        lightbox_letters_action.triggered.connect(self._open_lightbox_letters_dialog)
        tools_menu.addAction(lightbox_letters_action)

        lightbox_image_action = QAction("LightBox depuis image...", self)
        lightbox_image_action.triggered.connect(self._open_lightbox_image_dialog)
        tools_menu.addAction(lightbox_image_action)

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
        self.export_multi_material_button.setEnabled(can_export)
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

        self.filename_label.setText(Path(path).name)
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

    def _render_preview_pixmap(self, preview_width: int) -> QPixmap | None:
        """Rendu partage entre la vignette inline (320px, cf.
        `_update_source_preview`) et la fenetre de zoom (haute resolution,
        cf. `_on_zoom_preview_clicked`) -- meme pipeline (niveaux de gris,
        luminosite/contraste, inversion, surimpression du masque de la zone
        active), seule la resolution de sortie change."""
        if not self._image_path:
            return None
        image = load_image(self._image_path)
        array = to_grayscale_array(image)
        preview_width = min(preview_width, array.shape[1])  # jamais suralonger la source
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
            return render_overlay(array, mask_preview, zone_color(index), alpha=0.4)
        return _array_to_pixmap(array)

    def _update_source_preview(self) -> None:
        pixmap = self._render_preview_pixmap(320)
        self.zoom_preview_button.setEnabled(pixmap is not None)
        if pixmap is not None:
            self.preview_label.set_source_pixmap(pixmap)

    def _on_zoom_preview_clicked(self) -> None:
        pixmap = self._render_preview_pixmap(1600)
        if pixmap is None:
            return
        title = Path(self._image_path).name if self._image_path else "Apercu"
        dialog = ImageZoomDialog(pixmap, f"Apercu - {title}", self)
        dialog.exec()

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
        zone = Zone(
            name="Lithophanie",
            composition_mode=CompositionMode.BASE,
            geometry_params=self._current_geometry_parameters(),
        )
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

    def _zone_mask_for_generation(self, zone: Zone) -> np.ndarray | None:
        """None si la zone n'a jamais ete touchee (comportement historique,
        aucune verification necessaire -- pas de fichier, pas de masque).
        Fonctionne pour n'importe quelle zone, pas seulement l'active :
        reutilise par la composition multi-zone."""
        if zone.id in self._zone_masks:
            return self._zone_masks[zone.id]
        if zone.mask_path is None or self._project_bundle_dir is None:
            return None
        width_px, height_px = image_size(self._resolve_zone_image_path(zone))
        return load_zone_mask(self._project_bundle_dir, zone, shape=(height_px, width_px))

    def _resolve_zone_image_path(self, zone: Zone) -> str:
        """La plupart des zones n'ont pas de source propre (override rare,
        voir Zone.source_image_path) et utilisent l'image partagee de la
        Scene, deja resolue dans self._image_path."""
        if zone.source_image_path:
            path = Path(zone.source_image_path)
            if not path.is_absolute() and self._project_bundle_dir is not None:
                path = self._project_bundle_dir / path
            return str(path)
        return self._image_path

    def _build_zone_sources(self) -> list[ZoneSource]:
        return [
            ZoneSource(
                zone=zone,
                image_path=self._resolve_zone_image_path(zone),
                mask=self._zone_mask_for_generation(zone),
                brightness=self.brightness_spin.value(),
                contrast=self.contrast_spin.value(),
            )
            for zone in self._project.scene.zones
        ]

    def _resolve_shape_source_path(self) -> str | None:
        source = self._project.scene.shape.source_image_path
        if not source:
            return None
        path = Path(source)
        if not path.is_absolute() and self._project_bundle_dir is not None:
            path = self._project_bundle_dir / path
        return str(path)

    def _current_shape_mask(self) -> np.ndarray | None:
        """Silhouette physique de la Scene (Shape Composer, v0.4), a la
        resolution de la grille canonique -- `None` = pas de restriction
        (rectangle plein, comportement historique). Erreurs de rendu
        (police manquante, image de forme introuvable) degradent
        proprement vers "pas de forme" plutot que de bloquer la generation."""
        base_zone = next(
            (z for z in self._project.scene.zones if z.composition_mode == CompositionMode.BASE), None
        )
        if base_zone is None:
            return None
        rows, cols = grid_dimensions(base_zone.geometry_params)
        shape = self._project.scene.shape

        try:
            if shape.shape_type in (ShapeType.IMAGE, ShapeType.SVG):
                path = self._resolve_shape_source_path()
                if not path:
                    return None
                with Image.open(path) as image:
                    if "A" in image.getbands():
                        channel = np.asarray(image.split()[-1], dtype=np.float32) / 255.0
                    else:
                        channel = np.asarray(image.convert("L"), dtype=np.float32) / 255.0
                mask = build_shape_mask_from_image_array(channel, rows, cols)
            else:
                mask = build_shape_mask(shape, rows, cols)
        except (ValueError, OSError) as exc:
            logger.warning("Masque de forme indisponible, generation sans restriction : %s", exc)
            return None

        if shape.border_width_mm > 0:
            px_per_mm = cols / base_zone.geometry_params.width_mm
            mask = apply_border(mask, shape.border_width_mm * px_per_mm)
        return mask

    def _base_zone_resolution_mm(self) -> float | None:
        base_zone = next(
            (z for z in self._project.scene.zones if z.composition_mode == CompositionMode.BASE), None
        )
        return base_zone.geometry_params.resolution if base_zone is not None else None

    def _effective_image_transform(self) -> ImageTransform | None:
        """`None` (chemin historique exact, cf. core/geometry/composition.py)
        pour le cas Rectangle+cadrage jamais touche -- garantit qu'un projet
        n'utilisant pas le Shape Composer (nouveau ou migre v4->v5) genere
        des resultats bit-a-bit identiques a la 0.3. Des qu'une Shape non
        rectangulaire est choisie OU que le cadrage a ete modifie, bascule
        sur le vrai pipeline de cadrage isotrope (core/image/transform.py)."""
        shape = self._project.scene.shape
        transform = self._project.scene.image_transform
        if shape.shape_type is ShapeType.RECTANGLE and transform == ImageTransform():
            return None
        return transform

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
        self._load_support_into_panel()
        self._load_shape_into_panel()
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
        # signaux bloques : sinon `setCurrentIndex` sur le 1er combo declenche
        # _on_zone_role_changed AVANT que le 2eme combo ne soit a jour, qui
        # ecrase alors zone.composition_mode avec la valeur perimee du combo.
        self.relief_mode_combo.blockSignals(True)
        self.composition_mode_combo.blockSignals(True)
        self._set_combo_data(self.relief_mode_combo, zone.relief_mode)
        self._set_combo_data(self.composition_mode_combo, zone.composition_mode)
        self.relief_mode_combo.blockSignals(False)
        self.composition_mode_combo.blockSignals(False)

        self.material_name_edit.blockSignals(True)
        self.material_filament_combo.blockSignals(True)
        self.material_slot_spin.blockSignals(True)
        self.material_name_edit.setText(zone.material.name)
        self._set_combo_data(self.material_filament_combo, zone.material.filament_type)
        self.material_slot_spin.setValue(zone.material.slot if zone.material.slot is not None else -1)
        self.material_name_edit.blockSignals(False)
        self.material_filament_combo.blockSignals(False)
        self.material_slot_spin.blockSignals(False)
        self._update_material_color_button(zone.material.color)

        self.color_strategy_combo.blockSignals(True)
        self.backlight_skin_spin.blockSignals(True)
        self.backlight_insert_thickness_spin.blockSignals(True)
        self.backlight_clearance_combo.blockSignals(True)
        # `color_strategy is None` (zone historique/BASE) s'affiche comme
        # "Materiau seul" -- valeur la plus sure -- SANS jamais l'ecrire dans
        # le modele tant que l'utilisateur ne touche pas explicitement ce
        # combo (cf. _on_color_strategy_changed, jamais appele au chargement).
        self._set_combo_data(self.color_strategy_combo, zone.color_strategy or ColorStrategy.MATERIAL_ONLY)
        self.backlight_skin_spin.setValue(zone.backlight_insert.white_skin_thickness_mm)
        self.backlight_insert_thickness_spin.setValue(zone.backlight_insert.insert_thickness_mm)
        self._set_combo_data(self.backlight_clearance_combo, zone.backlight_insert.xy_clearance_mm)
        self.color_strategy_combo.blockSignals(False)
        self.backlight_skin_spin.blockSignals(False)
        self.backlight_insert_thickness_spin.blockSignals(False)
        self.backlight_clearance_combo.blockSignals(False)
        self._update_color_strategy_visibility()

        self._update_height_display()

    def _update_material_color_button(self, color: tuple[float, float, float]) -> None:
        qcolor = QColor.fromRgbF(*color)
        self.material_color_button.setStyleSheet(f"background-color: {qcolor.name()};")

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _on_zone_role_changed(self, *_args) -> None:
        zone = self._active_zone()
        if zone is None:
            return
        zone.relief_mode = self.relief_mode_combo.currentData()
        zone.composition_mode = self.composition_mode_combo.currentData()

        if self._state is AppState.MESH_READY:
            self._set_state(AppState.PARAMS_DIRTY)
        elif self._state is AppState.ERROR:
            self._set_state(AppState.IMAGE_LOADED if self._image_path else AppState.NO_IMAGE)

    def _on_pick_material_color(self) -> None:
        zone = self._active_zone()
        if zone is None:
            return
        initial = QColor.fromRgbF(*zone.material.color)
        chosen = QColorDialog.getColor(initial, self, "Couleur du materiau")
        if not chosen.isValid():
            return
        zone.material.color = (chosen.redF(), chosen.greenF(), chosen.blueF())
        self._update_material_color_button(zone.material.color)
        self._current_material_meshes = None
        self._current_backlight_result = None
        if self._state is AppState.MESH_READY:
            self._set_state(AppState.PARAMS_DIRTY)

    def _on_material_changed(self, *_args) -> None:
        zone = self._active_zone()
        if zone is None:
            return
        zone.material.name = self.material_name_edit.text().strip() or "default"
        zone.material.filament_type = self.material_filament_combo.currentData()
        slot_value = self.material_slot_spin.value()
        zone.material.slot = None if slot_value < 0 else slot_value
        self._current_material_meshes = None
        self._current_backlight_result = None

        if self._state is AppState.MESH_READY:
            self._set_state(AppState.PARAMS_DIRTY)
        elif self._state is AppState.ERROR:
            self._set_state(AppState.IMAGE_LOADED if self._image_path else AppState.NO_IMAGE)

    def _on_color_strategy_changed(self, *_args) -> None:
        zone = self._active_zone()
        if zone is None:
            return
        zone.color_strategy = self.color_strategy_combo.currentData()
        zone.backlight_insert.white_skin_thickness_mm = self.backlight_skin_spin.value()
        zone.backlight_insert.insert_thickness_mm = self.backlight_insert_thickness_spin.value()
        zone.backlight_insert.xy_clearance_mm = self.backlight_clearance_combo.currentData()
        self._current_material_meshes = None
        self._current_backlight_result = None
        self._update_color_strategy_visibility()

        if self._state is AppState.MESH_READY:
            self._set_state(AppState.PARAMS_DIRTY)
        elif self._state is AppState.ERROR:
            self._set_state(AppState.IMAGE_LOADED if self._image_path else AppState.NO_IMAGE)

    def _update_color_strategy_visibility(self) -> None:
        is_backlight = self.color_strategy_combo.currentData() is ColorStrategy.BACKLIGHT_INSERT
        self.backlight_skin_spin.setVisible(is_backlight)
        self.backlight_insert_thickness_spin.setVisible(is_backlight)
        self.backlight_clearance_combo.setVisible(is_backlight)

    def _load_support_into_panel(self) -> None:
        support = self._project.scene.support
        for widget in (
            self.support_type_combo,
            self.support_height_spin,
            self.support_depth_spin,
            self.support_overhang_left_spin,
            self.support_overhang_right_spin,
            self.support_side_stabilizers_checkbox,
        ):
            widget.blockSignals(True)
        self._set_combo_data(self.support_type_combo, support.support_type)
        self.support_height_spin.setValue(support.height_mm)
        self.support_depth_spin.setValue(support.depth_mm)
        self.support_overhang_left_spin.setValue(support.overhang_left_mm)
        self.support_overhang_right_spin.setValue(support.overhang_right_mm)
        self.support_side_stabilizers_checkbox.setChecked(support.side_stabilizers)
        for widget in (
            self.support_type_combo,
            self.support_height_spin,
            self.support_depth_spin,
            self.support_overhang_left_spin,
            self.support_overhang_right_spin,
            self.support_side_stabilizers_checkbox,
        ):
            widget.blockSignals(False)

    def _on_support_changed(self, *_args) -> None:
        support = self._project.scene.support
        support.support_type = self.support_type_combo.currentData()
        support.height_mm = self.support_height_spin.value()
        support.depth_mm = self.support_depth_spin.value()
        support.overhang_left_mm = self.support_overhang_left_spin.value()
        support.overhang_right_mm = self.support_overhang_right_spin.value()
        support.side_stabilizers = self.support_side_stabilizers_checkbox.isChecked()

        if self._state is AppState.MESH_READY:
            self._set_state(AppState.PARAMS_DIRTY)

    # ------------------------------------------------------------------ #
    # Forme (Shape Composer, v0.4)
    # ------------------------------------------------------------------ #
    def _load_shape_into_panel(self) -> None:
        shape = self._project.scene.shape
        for widget in (
            self.shape_type_combo,
            self.shape_text_edit,
            self.shape_bold_checkbox,
            self.shape_border_spin,
        ):
            widget.blockSignals(True)
        self._set_combo_data(self.shape_type_combo, shape.shape_type)
        self.shape_text_edit.setText(shape.text)
        self.shape_bold_checkbox.setChecked(shape.bold)
        self.shape_border_spin.setValue(shape.border_width_mm)
        for widget in (
            self.shape_type_combo,
            self.shape_text_edit,
            self.shape_bold_checkbox,
            self.shape_border_spin,
        ):
            widget.blockSignals(False)
        self._update_shape_source_label()
        self._update_shape_visibility()
        self._update_shape_info_label()

    def _update_shape_source_label(self) -> None:
        source = self._project.scene.shape.source_image_path
        self.shape_source_label.setText(Path(source).name if source else "(aucun fichier importe)")

    def _update_shape_visibility(self) -> None:
        shape_type = self.shape_type_combo.currentData()
        is_text = shape_type is ShapeType.TEXT
        is_import = shape_type in (ShapeType.SVG, ShapeType.IMAGE)
        self.shape_text_edit.setVisible(is_text)
        self.shape_bold_checkbox.setVisible(is_text)
        self.shape_import_button.setVisible(is_import)
        self.shape_source_label.setVisible(is_import)

    def _update_shape_info_label(self) -> None:
        """Comptage de composantes disjointes (2.10) -- purement informatif,
        jamais reliees automatiquement."""
        mask = self._current_shape_mask()
        if mask is None:
            self.shape_info_label.setText("")
            return
        count = count_connected_components(mask)
        if count <= 1:
            self.shape_info_label.setText("")
        else:
            self.shape_info_label.setText(f"Cette forme contient {count} elements separes.")

    def _on_shape_changed(self, *_args) -> None:
        shape = self._project.scene.shape
        shape.shape_type = self.shape_type_combo.currentData()
        shape.text = self.shape_text_edit.text()
        shape.bold = self.shape_bold_checkbox.isChecked()
        shape.border_width_mm = self.shape_border_spin.value()
        self._update_shape_visibility()
        self._update_shape_info_label()
        self._current_material_meshes = None
        self._current_backlight_result = None

        if self._state is AppState.MESH_READY:
            self._set_state(AppState.PARAMS_DIRTY)

    def _on_import_shape_source_clicked(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self, "Importer une forme", "", "SVG (*.svg);;Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if not path:
            return

        shape = self._project.scene.shape
        if path.lower().endswith(".svg"):
            try:
                from lithoshape3d.ui.shape_svg_import import rasterize_svg_to_alpha_png

                rasterized_path = rasterize_svg_to_alpha_png(path)
            except Exception as exc:
                logger.exception("Echec de la rasterisation SVG")
                QMessageBox.critical(self, "LithoShape3D", f"Impossible d'importer ce SVG :\n{exc}")
                return
            shape.shape_type = ShapeType.SVG
            shape.source_image_path = rasterized_path
            self._set_combo_data(self.shape_type_combo, ShapeType.SVG)
        else:
            shape.shape_type = ShapeType.IMAGE
            shape.source_image_path = path
            self._set_combo_data(self.shape_type_combo, ShapeType.IMAGE)

        self._update_shape_source_label()
        self._update_shape_visibility()
        self._update_shape_info_label()
        self._current_material_meshes = None
        self._current_backlight_result = None
        if self._state is AppState.MESH_READY:
            self._set_state(AppState.PARAMS_DIRTY)

    def _on_cadrage_clicked(self) -> None:
        if not self._image_path:
            return
        shape_mask = self._current_shape_mask()
        if shape_mask is None:
            base_zone = self._active_zone()
            if base_zone is None:
                return
            rows, cols = grid_dimensions(base_zone.geometry_params)
            shape_mask = np.ones((rows, cols), dtype=bool)

        from lithoshape3d.ui.cadrage_dialog import CadrageDialog

        source_array = to_grayscale_array(load_image(self._image_path))
        dialog = CadrageDialog(source_array, shape_mask, self._project.scene.image_transform, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._project.scene.image_transform = dialog.transform
            self._current_material_meshes = None
            self._current_backlight_result = None
            self._update_source_preview()
            if self._state is AppState.MESH_READY:
                self._set_state(AppState.PARAMS_DIRTY)

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
        # MATERIAL_ONLY par defaut (pas None) : le workflow le plus courant
        # pour une nouvelle zone est "selectionner une region (SAM2) et lui
        # assigner un materiau" -- sans ceci, CompositionMode.ADD (le defaut
        # de Zone) ajouterait silencieusement sa propre contribution de
        # hauteur par-dessus la base (mission 0.4.1, bug de sur-relief). `None`
        # reste reserve aux zones migrees d'un projet anterieur a la 0.4.1.
        zone = Zone(
            name=f"Zone {index}",
            geometry_params=self._current_geometry_parameters(),
            color_strategy=ColorStrategy.MATERIAL_ONLY,
        )
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
        dialog = MaskEditorDialog(
            zone.name,
            base_array,
            mask,
            zone_color(index),
            segmentation_backend=self._segmentation_backend,
            parent=self,
        )
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
        if "width_mm" in preset:
            self.width_spin.setValue(preset["width_mm"])

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

        if self.view_composition_button.isChecked():
            if self._scene_has_backlight_zone():
                worker = BacklightCompositionWorker(
                    self._build_zone_sources(),
                    support=self._project.scene.support,
                    image_transform=self._effective_image_transform(),
                    shape_mask=self._current_shape_mask(),
                )
                worker.signals.succeeded.connect(self._on_backlight_composition_succeeded)
            else:
                worker = CompositionWorker(
                    self._build_zone_sources(),
                    support=self._project.scene.support,
                    image_transform=self._effective_image_transform(),
                    shape_mask=self._current_shape_mask(),
                )
                worker.signals.succeeded.connect(self._on_composition_succeeded)
        else:
            zone = self._active_zone()
            params = self._current_geometry_parameters()
            mask = self._zone_mask_for_generation(zone) if zone is not None else None
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
        self._current_panel_z_max = None  # pas de pied concevable hors composition
        self._current_material_meshes = None
        self._current_backlight_result = None
        self._render_current_display_mode()
        self.scene_viewer.view_isometric()
        self._set_state(AppState.MESH_READY)

    def _scene_has_backlight_zone(self) -> bool:
        return any(
            zone.visible and zone.color_strategy is ColorStrategy.BACKLIGHT_INSERT
            for zone in self._project.scene.zones
        )

    def _on_backlight_composition_succeeded(self, result, fused_white_mesh, panel_z_max: float) -> None:
        self._current_mesh = fused_white_mesh
        self._current_panel_z_max = panel_z_max
        self._current_material_meshes = None
        self._current_backlight_result = result  # panneau seul (pas de pied), reutilise par la vue Materiaux
        self._render_current_display_mode()
        self.scene_viewer.view_isometric()
        self._set_state(AppState.MESH_READY)
        self._report_printability(fused_white_mesh)
        if result.warnings:
            self.statusBar().showMessage("Backlight Insert -- " + " ".join(result.warnings), 10000)

    def _on_composition_succeeded(self, mesh, panel_z_max: float) -> None:
        self._current_mesh = mesh
        self._current_panel_z_max = panel_z_max
        self._current_material_meshes = None
        self._current_backlight_result = None
        self._render_current_display_mode()
        self.scene_viewer.view_isometric()
        self._set_state(AppState.MESH_READY)
        self._report_printability(mesh)

    def _report_printability(self, mesh) -> None:
        """Diagnostic non bloquant (cf. 2.16) : le mesh a deja passe
        `validate_mesh` dans le worker (sinon `_on_generation_failed` aurait
        ete appele) -- ici on informe seulement l'utilisateur d'eventuels
        points d'attention (composantes disjointes, elements fins, dimension
        limite) sans jamais empecher l'export."""
        try:
            report = check_printability(
                mesh, shape_mask=self._current_shape_mask(), pixel_size_mm=self._base_zone_resolution_mm()
            )
        except (ValueError, OSError) as exc:
            logger.warning("Diagnostic d'imprimabilite indisponible : %s", exc)
            return
        if report.warnings:
            logger.info("Diagnostic d'imprimabilite : %s", "; ".join(report.warnings))
            self.statusBar().showMessage(
                "Mesh genere -- a verifier avant impression : " + "; ".join(report.warnings), 8000
            )

    def _on_generation_failed(self, message: str) -> None:
        self._current_mesh = None
        self._current_panel_z_max = None
        self._current_material_meshes = None
        self._current_backlight_result = None
        self._set_state(AppState.ERROR)
        QMessageBox.warning(self, "LithoShape3D", f"La generation a echoue :\n{message}")

    def _on_display_mode_changed(self) -> None:
        if self._current_mesh is not None:
            self._render_current_display_mode()

    def _render_current_display_mode(self) -> None:
        mode = self.display_mode_combo.currentData()
        if mode is DisplayMode.MATERIALS:
            self.scene_viewer.show_material_meshes(self._materials_for_display())
        else:
            self.scene_viewer.show_mesh(
                self._current_mesh, display_mode=mode, panel_z_max=self._current_panel_z_max
            )

    def _materials_for_display(self) -> dict[str, tuple[object, tuple[float, float, float]]]:
        if self._current_backlight_result is not None:
            # Panneau blanc AVEC cavites (pas la partition naive de
            # partition_mesh_by_material, qui ignorerait la cavite/l'insert
            # et montrerait "Rose" comme une simple tranche pleine epaisseur)
            # + un insert independant par materiau -- cf. mission 0.4.1 s10.
            base_zone = next(
                (z for z in self._project.scene.zones if z.composition_mode is CompositionMode.BASE), None
            )
            white_name = base_zone.material.name if base_zone is not None else "Blanc"
            self._current_material_meshes = {
                white_name: self._current_backlight_result.white_mesh,
                **self._current_backlight_result.insert_meshes,
                **{
                    f"{name} (support sacrificiel a retirer)": mesh
                    for name, mesh in self._current_backlight_result.breakaway_support_meshes.items()
                },
            }
        elif self._current_material_meshes is None:
            try:
                self._current_material_meshes = partition_mesh_by_material(
                    self._build_zone_sources(),
                    image_transform=self._effective_image_transform(),
                    shape_mask=self._current_shape_mask(),
                )
            except (ValueError, NotImplementedError) as exc:
                logger.warning("Partition par materiau indisponible : %s", exc)
                self._current_material_meshes = {}

        color_by_material: dict[str, tuple[float, float, float]] = {}
        for zone in self._project.scene.zones:
            color_by_material.setdefault(zone.material.name, zone.material.color)

        result = {
            name: (mesh, color_by_material.get(name, (0.85, 0.85, 0.85)))
            for name, mesh in self._current_material_meshes.items()
        }

        support = self._project.scene.support
        panel_meshes = list(self._current_material_meshes.values())
        if support.support_type is not SupportType.NONE and panel_meshes:
            # bornes du PANNEAU SEUL (pas self._current_mesh, qui peut deja
            # inclure un pied fusionne -- deriver l'etendue depuis un corps
            # deja-fusionne double-compterait les debords).
            x_min = min(float(m.bounds[0][0]) for m in panel_meshes)
            x_max = max(float(m.bounds[1][0]) for m in panel_meshes)
            y_top = min(float(m.bounds[0][1]) for m in panel_meshes)
            support_mesh = build_support_mesh(x_min, x_max, y_top, support)
            if support_mesh is not None:
                result["Support"] = (support_mesh, (0.5, 0.5, 0.5))

        if support.side_stabilizers and panel_meshes:
            x_min = min(float(m.bounds[0][0]) for m in panel_meshes)
            x_max = max(float(m.bounds[1][0]) for m in panel_meshes)
            y_min = min(float(m.bounds[0][1]) for m in panel_meshes)
            y_max = max(float(m.bounds[1][1]) for m in panel_meshes)
            z_max = max(float(m.bounds[1][2]) for m in panel_meshes)
            left, right = build_side_stabilizer_pair(x_max - x_min, y_min, y_max, z_max)
            left.apply_translation([x_min, 0.0, 0.0])
            right.apply_translation([x_min, 0.0, 0.0])
            result["Stabilisateur gauche (detachable)"] = (left, (0.6, 0.6, 0.65))
            result["Stabilisateur droit (detachable)"] = (right, (0.6, 0.6, 0.65))
        return result

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    @staticmethod
    def _slugify(text: str) -> str:
        cleaned = "".join(c if c.isalnum() else "-" for c in text.strip())
        cleaned = "-".join(filter(None, cleaned.split("-")))
        return cleaned or "sans-titre"

    def _suggested_stl_filename(self) -> str:
        project_name = self._slugify(self._project.name)
        zone = self._active_zone()
        if zone is not None:
            return f"{project_name}_{self._slugify(zone.name)}.stl"
        return f"{project_name}.stl"

    def _on_export_clicked(self) -> None:
        if self._state is not AppState.MESH_READY or self._current_mesh is None:
            return

        if self._current_backlight_result is not None or self._project.scene.support.side_stabilizers:
            # Un seul fichier STL ne suffit pas ici : soit le corps blanc et
            # l'insert Backlight sont deux volumes physiquement separes (cf.
            # mission 0.4.1 s11), soit les stabilisateurs lateraux (jamais
            # fusionnes au panneau, detachables) s'y ajoutent -- dans les
            # deux cas il faut un fichier par corps, pas un seul STL combine.
            self._on_export_backlight_stl_clicked()
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

    def _on_export_backlight_stl_clicked(self) -> None:
        """Malgre son nom (garde du chemin Backlight Insert d'origine), ce
        chemin d'export s'applique a tout resultat necessitant plusieurs
        fichiers STL distincts : corps blanc + insert Backlight, et/ou
        stabilisateurs lateraux (toujours des corps SEPARES, jamais
        fusionnes au panneau) -- voir `_on_export_clicked`."""
        materials = self._materials_for_display()
        material_meshes = {name: mesh for name, (mesh, _color) in materials.items()}
        base_name = self._slugify(self._project.name)
        directory = QFileDialog.getExistingDirectory(self, "Dossier pour les STL (un fichier par corps)")
        if not directory:
            return

        try:
            written = export_stl_per_material(material_meshes, directory, base_name=base_name)
        except OSError as exc:
            logger.exception("Echec de l'export STL multi-corps")
            QMessageBox.critical(self, "LithoShape3D", f"Echec de l'export :\n{exc}")
            return

        names = "\n".join(str(p) for p in written)
        logger.info("STL multi-corps exportes : %s", names)
        self.statusBar().showMessage(f"Export reussi : {directory}", 8000)
        QMessageBox.information(self, "LithoShape3D", f"STL exportes avec succes :\n{names}")

    def _on_export_multi_material_clicked(self) -> None:
        """3MF standard multi-objets en priorite (voir
        core/export/multi_material_export.py) ; repli propre sur un STL par
        materiau, tous alignes dans le meme repere, si le 3MF echoue."""
        if self._state is not AppState.MESH_READY or self._current_mesh is None:
            return

        materials = self._materials_for_display()
        material_meshes = {name: mesh for name, (mesh, _color) in materials.items()}
        if len(material_meshes) <= 1:
            QMessageBox.information(
                self, "LithoShape3D", "Un seul materiau utilise : l'export STL standard suffit."
            )
            return

        base_name = self._slugify(self._project.name)
        suggested_name = f"{base_name}.3mf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter multi-materiaux (3MF)", suggested_name, "3MF (*.3mf)"
        )
        if not path:
            return

        try:
            export_multi_material_3mf(material_meshes, path)
        except Exception as exc:  # noqa: BLE001 -- n'importe quel echec du 3MF doit declencher le repli STL
            logger.warning("Export 3MF multi-objets echoue, repli sur STL par materiau : %s", exc)
            directory = QFileDialog.getExistingDirectory(self, "Dossier pour les STL par materiau")
            if not directory:
                return
            written = export_stl_per_material(material_meshes, directory, base_name=base_name)
            names = "\n".join(str(p) for p in written)
            QMessageBox.information(
                self,
                "LithoShape3D",
                f"Export 3MF indisponible ({exc}), repli sur un STL par materiau :\n{names}",
            )
            return

        logger.info("3MF multi-objets exporte : %s", path)
        self.statusBar().showMessage(f"Export multi-materiaux reussi : {path}", 8000)
        QMessageBox.information(self, "LithoShape3D", f"3MF multi-objets exporte avec succes :\n{path}")

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
        self.zoom_preview_button.setEnabled(False)
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
    def _open_lightbox_letters_dialog(self) -> None:
        from lithoshape3d.ui.lightbox_letters_dialog import LightboxLettersDialog

        dialog = LightboxLettersDialog(self)
        dialog.exec()

    def _open_lightbox_image_dialog(self) -> None:
        from lithoshape3d.ui.lightbox_image_dialog import LightboxImageDialog

        dialog = LightboxImageDialog(self)
        dialog.exec()

    def _show_about(self) -> None:
        from lithoshape3d import __version__

        ai_status = "disponible" if self._segmentation_backend is not None else "indisponible"
        QMessageBox.information(
            self,
            "A propos de LithoShape3D",
            f"LithoShape3D {__version__}\n"
            "Image -> zones -> LithoFusion -> STL.\n\n"
            f"Selection intelligente (SAM2) : {ai_status}.",
        )
