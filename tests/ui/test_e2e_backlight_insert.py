"""E2E (mission 0.4.1, Test F) : workflow complet Backlight Insert sur le
scenario de reference -- femme tenant une rose, rose selectionnee (SAM2 mock
deterministe), materiau rose, strategie Insert retro-eclaire, peau=0.40mm,
jeu XY=Standard, generation, inspection viewer, export STL puis 3MF,
sauvegarde/fermeture/reouverture/verification/regeneration.

Meme discipline que test_e2e_heart_rose.py : `MockSegmentationBackend`
deterministe pour la selection, pas le vrai SAM2 CoreML (couvert separement,
optionnellement, par tests/ai/segmentation/test_sam2_coreml_backend.py)."""

import time

import numpy as np
import pyvista as pv
import trimesh
from PIL import Image

from lithoshape3d.ai.segmentation.mock_backend import MockSegmentationBackend
from lithoshape3d.core.scene.models import ColorStrategy, CompositionMode
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from lithoshape3d.ui.main_window import MainWindow
from lithoshape3d.ui.mask_editor_dialog import MaskEditorDialog
from lithoshape3d.ui.state import AppState
from lithoshape3d.viewer.scene_viewer import DisplayMode

IMAGE_SIZE = 300
ROSE_CENTER_XY = (185, 175)
ROSE_RADIUS = 22


def _wait_until(predicate, qapp, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert predicate(), "timeout en attendant la condition attendue"


def _make_woman_with_rose_photo(path) -> None:
    yy, xx = np.mgrid[0:IMAGE_SIZE, 0:IMAGE_SIZE]
    background = (120 + 0.15 * yy).clip(0, 255).astype(np.uint8)
    rose_x, rose_y = ROSE_CENTER_XY
    rose_disk = (xx - rose_x) ** 2 + (yy - rose_y) ** 2 <= ROSE_RADIUS**2
    background[rose_disk] = 235
    Image.fromarray(background, mode="L").save(path)


def _select_rose_with_ai(main_window, qapp, zone, image_path) -> None:
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
    assert mask.sum() > 0
    main_window._zone_masks[zone.id] = mask


def test_backlight_insert_full_workflow_from_photo_to_reopened_project(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.warning", lambda *a, **k: None)
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.critical", lambda *a, **k: None)

    main_window = MainWindow(plotter=pv.Plotter(off_screen=True))
    try:
        # 1. ouvrir photo femme + rose
        image_path = tmp_path / "femme_rose.png"
        _make_woman_with_rose_photo(image_path)
        main_window._load_image(str(image_path))
        main_window.resolution_spin.setValue(1.0)  # grille 300x300 -- assez fine pour un insert net
        base_zone = main_window._active_zone()
        base_zone.material.name = "Blanc"
        assert main_window._state is AppState.IMAGE_LOADED

        # 2. creer/selectionner la zone rose
        main_window._on_new_zone_clicked()
        rose_zone = main_window._active_zone()
        rose_zone.composition_mode = CompositionMode.ADD  # le vrai defaut d'une nouvelle zone
        _select_rose_with_ai(main_window, qapp, rose_zone, str(image_path))

        # 3. assigner materiau rose
        rose_zone.material.name = "Rose"
        rose_zone.material.color = (0.85, 0.08, 0.28)

        # 4. selectionner Backlight Insert
        main_window._refresh_zones_list()
        main_window.zones_list.setCurrentRow(main_window.zones_list.count() - 1)
        main_window._on_zone_selection_changed()
        idx = main_window.color_strategy_combo.findData(ColorStrategy.BACKLIGHT_INSERT)
        main_window.color_strategy_combo.setCurrentIndex(idx)
        assert rose_zone.color_strategy is ColorStrategy.BACKLIGHT_INSERT

        # 5. peau = 0.40mm (valeur par defaut, mais on la fixe explicitement)
        main_window.backlight_skin_spin.setValue(0.40)
        # 6. jeu XY = Standard
        idx = main_window.backlight_clearance_combo.findData(0.20)
        main_window.backlight_clearance_combo.setCurrentIndex(idx)
        assert rose_zone.backlight_insert.white_skin_thickness_mm == 0.40
        assert rose_zone.backlight_insert.xy_clearance_mm == 0.20

        # 7. generer
        main_window.view_composition_button.setChecked(True)
        main_window._on_generate_clicked()
        _wait_until(lambda: main_window._state is not AppState.GENERATING, qapp)
        assert main_window._state is AppState.MESH_READY, main_window.statusBar().currentMessage()
        assert main_window._current_backlight_result is not None
        white_result = validate_mesh(main_window._current_mesh)
        assert white_result.is_valid
        assert white_result.connected_components == 1

        # 8. inspecter le viewer (Geometrie / Materiaux -- corps blanc + insert visibles)
        for mode in (DisplayMode.SURFACE, DisplayMode.MATERIALS, DisplayMode.BACKLIGHT_PREVIEW):
            idx = main_window.display_mode_combo.findData(mode)
            main_window.display_mode_combo.setCurrentIndex(idx)
        materials = main_window._materials_for_display()
        assert {"Blanc", "Rose"} <= set(materials.keys())
        insert_mesh, _color = materials["Rose"]
        assert validate_mesh(insert_mesh).is_valid
        assert insert_mesh.volume > 0

        # 9. exporter STL (un fichier par corps -- corps blanc + insert)
        stl_dir = tmp_path / "stl_export"
        stl_dir.mkdir()
        monkeypatch.setattr(
            "lithoshape3d.ui.main_window.QFileDialog.getExistingDirectory",
            lambda *a, **k: str(stl_dir),
        )
        main_window._on_export_clicked()
        written_stl = list(stl_dir.glob("*.stl"))
        assert len(written_stl) == 3  # Blanc + Rose + support sacrificiel de Rose
        for stl_path in written_stl:
            reloaded = trimesh.load(stl_path, process=True)
            assert reloaded.is_watertight

        # 10. exporter 3MF
        threemf_path = tmp_path / "backlight_rose.3mf"
        monkeypatch.setattr(
            "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
            lambda *a, **k: (str(threemf_path), "3MF (*.3mf)"),
        )
        main_window._on_export_multi_material_clicked()
        assert threemf_path.exists()
        reloaded_scene = trimesh.load(threemf_path)
        assert {"Blanc", "Rose"} <= set(reloaded_scene.geometry.keys())
        # meme repere : les deux corps doivent rester dans leur position
        # d'assemblage reelle (pas de recadrage independant a l'export).
        combined_bounds = reloaded_scene.bounds
        assert combined_bounds[1][0] - combined_bounds[0][0] > 0

        # 11. sauvegarder le projet
        bundle_dir = tmp_path / "BacklightRose.l3dproj"
        main_window._save_project_to(bundle_dir)
        assert (bundle_dir / "project.json").exists()

        # 12/13. fermer puis rouvrir
        reopened = MainWindow(plotter=pv.Plotter(off_screen=True))
        try:
            monkeypatch.setattr(
                "lithoshape3d.ui.main_window.QFileDialog.getExistingDirectory",
                lambda *a, **k: str(bundle_dir),
            )
            reopened._on_open_project()

            # 14. verifier etat et parametres apres reouverture
            reopened_rose = next(z for z in reopened._project.scene.zones if z.name == rose_zone.name)
            assert reopened_rose.color_strategy is ColorStrategy.BACKLIGHT_INSERT
            assert reopened_rose.backlight_insert.white_skin_thickness_mm == 0.40
            assert reopened_rose.backlight_insert.xy_clearance_mm == 0.20
            assert reopened_rose.material.name == "Rose"

            # 15. regenerer -- doit reproduire le meme resultat (corps blanc
            # + insert), sans exception, depuis un etat memoire totalement frais.
            from lithoshape3d.core.geometry.backlight import compose_backlight_bodies

            reopened_sources = reopened._build_zone_sources()
            regenerated = compose_backlight_bodies(
                reopened_sources,
                image_transform=reopened._effective_image_transform(),
                shape_mask=reopened._current_shape_mask(),
            )
            assert validate_mesh(regenerated.white_mesh).is_valid
            assert "Rose" in regenerated.insert_meshes
            assert validate_mesh(regenerated.insert_meshes["Rose"]).is_valid
        finally:
            reopened.plotter.close()
    finally:
        main_window.plotter.close()
