"""E2E (mission 2.18, Test A) : workflow complet Shape Composer sur le
scenario de reference -- femme tenant une rose, Shape=Coeur, rose dans un
materiau distinct, reste blanc, pied d'impression, 3 modes de visualisation,
export 3MF multi-materiaux, sauvegarde/fermeture/reouverture.

Utilise `MockSegmentationBackend` (deterministe, zero telechargement) pour
la selection intelligente -- pas le vrai SAM2 CoreML, qui reste couvert
separement et optionnellement par `tests/ai/segmentation/test_sam2_coreml_backend.py`
(ne s'execute que si le modele est deja en cache). Ce test-ci verifie le
CABLAGE UI complet (Shape -> cadrage -> masque -> materiau -> generation ->
viewer -> export -> persistance), pas la qualite de la segmentation
elle-meme."""

import time

import numpy as np
import pyvista as pv
import trimesh
from PIL import Image

from lithoshape3d.ai.segmentation.mock_backend import MockSegmentationBackend
from lithoshape3d.core.geometry.shape import count_connected_components
from lithoshape3d.core.scene.models import CompositionMode, ReliefMode, ShapeType, SupportType
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from lithoshape3d.ui.cadrage_dialog import CadrageDialog
from lithoshape3d.ui.main_window import MainWindow
from lithoshape3d.ui.mask_editor_dialog import MaskEditorDialog
from lithoshape3d.ui.state import AppState
from lithoshape3d.viewer.scene_viewer import DisplayMode

IMAGE_SIZE = 300
ROSE_CENTER_XY = (185, 175)  # (x=colonne, y=ligne) en espace image source native
ROSE_RADIUS = 22


def _wait_until(predicate, qapp, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert predicate(), "timeout en attendant la condition attendue"


def _make_woman_with_rose_photo(path) -> None:
    """Synthetique mais realiste dans sa structure : fond degrade (peau/
    cheveux), tache circulaire distincte (la "rose") a une position connue
    -- suffisant pour verifier le cablage complet sans dependre d'une vraie
    photo."""
    yy, xx = np.mgrid[0:IMAGE_SIZE, 0:IMAGE_SIZE]
    background = (120 + 0.15 * yy).clip(0, 255).astype(np.uint8)
    rose_x, rose_y = ROSE_CENTER_XY
    rose_disk = (xx - rose_x) ** 2 + (yy - rose_y) ** 2 <= ROSE_RADIUS**2
    background[rose_disk] = 235
    Image.fromarray(background, mode="L").save(path)


def _select_rose_with_ai(main_window, qapp, zone, image_path) -> None:
    """Reproduit exactement ce que fait `_on_edit_mask_clicked` a
    l'acceptation du dialogue (voir main_window.py), mais pilote la
    "Selection intelligente" directement plutot que par clics widget --
    le mecanisme async (QThreadPool + signaux) est identique."""
    from lithoshape3d.core.image.io import load_image
    from lithoshape3d.core.image.preprocessing import to_grayscale_array

    base_array = to_grayscale_array(load_image(image_path))
    dialog = MaskEditorDialog(
        zone.name,
        base_array,
        np.ones(base_array.shape, dtype=np.float32),
        (255, 0, 128),
        segmentation_backend=MockSegmentationBackend(),
        parent=main_window,
    )
    dialog._set_tool("ai")
    _wait_until(lambda: dialog._segmentation_session is not None, qapp)

    x, y = ROSE_CENTER_XY
    dialog._on_ai_point_added(float(x), float(y), True)
    _wait_until(lambda: dialog.ai_apply_button.isEnabled(), qapp)

    dialog._on_ai_apply()
    mask = dialog.resulting_mask()
    assert mask.sum() > 0  # la selection intelligente a bien produit quelque chose
    main_window._zone_masks[zone.id] = mask


def test_heart_shaped_lithophane_with_rose_in_distinct_material(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.warning", lambda *a, **k: None)
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.information", lambda *a, **k: None)

    main_window = MainWindow(plotter=pv.Plotter(off_screen=True))
    try:
        # 1. ouvrir photo femme + rose
        image_path = tmp_path / "femme_rose.png"
        _make_woman_with_rose_photo(image_path)
        main_window._load_image(str(image_path))
        main_window.width_spin.setValue(100.0)
        main_window.resolution_spin.setValue(2.0)  # grille 50x50, rapide et suffisante pour le test
        base_zone = main_window._active_zone()
        base_zone.material.name = "Blanc"
        assert main_window._state is AppState.IMAGE_LOADED

        # 2. Shape -> Coeur
        idx = main_window.shape_type_combo.findData(ShapeType.HEART)
        main_window.shape_type_combo.setCurrentIndex(idx)
        assert main_window._project.scene.shape.shape_type is ShapeType.HEART

        # 3. cadrer la femme (deplacement modeste, cadrage reel via CadrageDialog)
        shape_mask = main_window._current_shape_mask()
        assert count_connected_components(shape_mask) == 1  # coeur = une seule piece
        source_array = np.asarray(Image.open(image_path).convert("L"), dtype=np.float32) / 255.0
        cadrage = CadrageDialog(source_array, shape_mask, main_window._project.scene.image_transform)
        cadrage._on_fill_clicked()  # "Remplir" : la photo couvre toute la grille canonique
        main_window._project.scene.image_transform = cadrage.transform
        main_window._current_material_meshes = None

        # 4. selectionner la rose (SAM2 -- backend mock deterministe)
        main_window._on_new_zone_clicked()
        rose_zone = main_window._active_zone()
        rose_zone.composition_mode = CompositionMode.REPLACE
        rose_zone.relief_mode = ReliefMode.SOLID
        rose_zone.geometry_params.max_thickness_mm = 2.0
        _select_rose_with_ai(main_window, qapp, rose_zone, str(image_path))

        # 5. materiau rose
        rose_zone.material.name = "Rose"
        # 6. reste blanc (deja fait a l'etape 1)
        main_window._refresh_zones_list()

        # 7. ajouter un pied d'impression
        idx = main_window.support_type_combo.findData(SupportType.FLAT)
        main_window.support_type_combo.setCurrentIndex(idx)
        main_window.support_height_spin.setValue(6.0)

        # 8. generer
        main_window.view_composition_button.setChecked(True)
        main_window._on_generate_clicked()
        _wait_until(lambda: main_window._state is not AppState.GENERATING, qapp)
        assert main_window._state is AppState.MESH_READY, main_window.statusBar().currentMessage()
        assert main_window._current_mesh is not None
        result = validate_mesh(main_window._current_mesh)
        assert result.is_valid
        assert result.connected_components == 1  # pied fusionne : un seul corps imprimable

        # 9/10/11. viewer Geometrie / Materiaux / Retro-eclaire -- ne doit jamais lever
        for mode in (DisplayMode.SURFACE, DisplayMode.MATERIALS, DisplayMode.BACKLIGHT_PREVIEW):
            idx = main_window.display_mode_combo.findData(mode)
            main_window.display_mode_combo.setCurrentIndex(idx)
        materials = main_window._materials_for_display()
        # "Support" est ajoute separement (corps gris, pas un materiau de
        # zone) des qu'un pied d'impression est actif -- voir
        # `_materials_for_display`.
        assert {"Blanc", "Rose"} <= set(materials.keys())
        rose_mesh, _rose_color = materials["Rose"]
        assert rose_mesh.volume > 0

        # 12. exporter en 3MF multi-materiaux
        export_path = tmp_path / "coeur_rose.3mf"
        monkeypatch.setattr(
            "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
            lambda *a, **k: (str(export_path), "3MF (*.3mf)"),
        )
        main_window._on_export_multi_material_clicked()
        assert export_path.exists()
        reloaded_scene = trimesh.load(export_path)
        assert {"Blanc", "Rose"} <= set(reloaded_scene.geometry.keys())

        # 13. sauvegarder le projet
        bundle_dir = tmp_path / "CoeurRose.l3dproj"
        main_window._save_project_to(bundle_dir)
        assert (bundle_dir / "project.json").exists()

        # 14/15. fermer puis rouvrir (nouvelle fenetre = etat memoire totalement frais)
        reopened = MainWindow(plotter=pv.Plotter(off_screen=True))
        try:
            monkeypatch.setattr(
                "lithoshape3d.ui.main_window.QFileDialog.getExistingDirectory",
                lambda *a, **k: str(bundle_dir),
            )
            reopened._on_open_project()

            # 16. verifier Shape/cadrage/rose/materiaux apres reouverture
            assert reopened._project.scene.shape.shape_type is ShapeType.HEART
            assert reopened._project.scene.image_transform == cadrage.transform
            reopened_zone_names = {z.name: z.material.name for z in reopened._project.scene.zones}
            assert reopened_zone_names[rose_zone.name] == "Rose"
            assert reopened._project.scene.zones[0].material.name == "Blanc"

            # la rose doit rester reconstructible et alignee apres reouverture
            # (le masque de zone est relu depuis le bundle, pas depuis la
            # memoire) : re-partitionner par materiau doit retrouver les deux
            # corps, avec une rose de volume positif.
            from lithoshape3d.core.geometry.materials import partition_mesh_by_material

            reopened_sources = reopened._build_zone_sources()
            reopened_shape_mask = reopened._current_shape_mask()
            reopened_materials = partition_mesh_by_material(
                reopened_sources,
                image_transform=reopened._effective_image_transform(),
                shape_mask=reopened_shape_mask,
            )
            assert set(reopened_materials.keys()) == {"Blanc", "Rose"}
            assert reopened_materials["Rose"].volume > 0
        finally:
            reopened.plotter.close()
    finally:
        main_window.plotter.close()
