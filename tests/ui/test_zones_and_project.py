import numpy as np
from PySide6.QtCore import Qt

from lithoshape3d.ui.state import AppState
from tests.fixtures.synthetic_images import make_gradient_image


def _load(main_window, tmp_path, width=64, height=48):
    image_path = make_gradient_image(tmp_path / "gradient.png", width=width, height=height)
    main_window._load_image(str(image_path))
    return image_path


def test_loading_image_creates_default_lithophane_zone(main_window, tmp_path):
    _load(main_window, tmp_path)

    assert len(main_window._project.scene.zones) == 1
    zone = main_window._project.scene.zones[0]
    assert zone.name == "Lithophanie"
    assert zone.mask_path is None  # masque plein implicite
    assert main_window._project.scene.active_zone_id == zone.id


def test_reopening_existing_zones_does_not_recreate_default(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._on_new_zone_clicked()
    assert len(main_window._project.scene.zones) == 2

    # recharger la meme image ne doit pas ecraser les zones existantes
    image_path = tmp_path / "gradient.png"
    main_window._load_image(str(image_path))

    assert len(main_window._project.scene.zones) == 2


def test_new_zone_has_stable_unique_id(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._on_new_zone_clicked()
    main_window._on_new_zone_clicked()

    ids = [z.id for z in main_window._project.scene.zones]
    assert len(ids) == len(set(ids)) == 3


def test_new_zone_becomes_active(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._on_new_zone_clicked()

    new_zone = main_window._project.scene.zones[-1]
    assert main_window._project.scene.active_zone_id == new_zone.id
    assert main_window._active_zone() is new_zone


def test_rename_zone_via_list_item(main_window, tmp_path):
    _load(main_window, tmp_path)
    item = main_window.zones_list.item(0)

    item.setText("Visage")
    main_window._on_zone_item_changed(item)

    assert main_window._project.scene.zones[0].name == "Visage"


def test_toggle_visibility_via_checkbox(main_window, tmp_path):
    _load(main_window, tmp_path)
    item = main_window.zones_list.item(0)
    assert main_window._project.scene.zones[0].visible is True

    item.setCheckState(Qt.CheckState.Unchecked)
    main_window._on_zone_item_changed(item)

    assert main_window._project.scene.zones[0].visible is False


def test_delete_zone_removes_it_and_selects_another(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._on_new_zone_clicked()
    assert len(main_window._project.scene.zones) == 2

    main_window._on_delete_zone_clicked()

    assert len(main_window._project.scene.zones) == 1
    assert main_window._active_zone() is not None


def test_delete_last_zone_leaves_no_active_zone(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._on_delete_zone_clicked()

    assert main_window._project.scene.zones == []
    assert main_window._project.scene.active_zone_id is None
    assert main_window._active_zone() is None


def test_zone_reorder_updates_model_order(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._on_new_zone_clicked()
    main_window._on_new_zone_clicked()
    original_order = [z.id for z in main_window._project.scene.zones]
    assert len(original_order) == 3

    # simule un drag&drop interne : reordonne la liste puis re-synchronise
    item = main_window.zones_list.takeItem(0)
    main_window.zones_list.insertItem(2, item)
    main_window._on_zones_reordered()

    new_order = [z.id for z in main_window._project.scene.zones]
    assert new_order == [original_order[1], original_order[2], original_order[0]]


def test_selecting_zone_loads_its_geometry_params(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window.width_spin.setValue(150.0)  # applique a la zone active (Lithophanie)
    main_window._on_new_zone_clicked()
    main_window.width_spin.setValue(42.0)  # applique a la nouvelle zone

    main_window.zones_list.setCurrentRow(0)
    main_window._on_zone_selection_changed()

    assert main_window.width_spin.value() == 150.0


def test_edit_mask_stores_painted_mask_in_memory(main_window, tmp_path):
    _load(main_window, tmp_path, width=40, height=30)
    zone = main_window._active_zone()

    # simule ce que fait MaskEditorDialog.exec() + resulting_mask() sans ouvrir
    # de vraie fenetre modale
    from lithoshape3d.ui.mask_edit_controller import MaskEditController

    controller = MaskEditController(np.ones((30, 40), dtype=np.float32))
    controller.begin_stroke()
    controller.paint(10, 10, 3, 0.0)
    controller.end_stroke()
    main_window._zone_masks[zone.id] = controller.mask.copy()

    assert zone.id in main_window._zone_masks
    assert main_window._zone_masks[zone.id][10, 10] == 0.0


def test_generation_uses_none_mask_for_untouched_default_zone(main_window, tmp_path):
    _load(main_window, tmp_path)
    zone = main_window._active_zone()

    mask = main_window._active_zone_mask_for_generation(zone)

    assert mask is None  # comportement historique preserve


def test_generation_uses_in_memory_edited_mask(main_window, tmp_path):
    _load(main_window, tmp_path, width=20, height=20)
    zone = main_window._active_zone()
    edited = np.zeros((20, 20), dtype=np.float32)
    main_window._zone_masks[zone.id] = edited

    mask = main_window._active_zone_mask_for_generation(zone)

    assert mask is edited


def test_new_project_resets_everything(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._on_new_zone_clicked()

    main_window._on_new_project()

    assert main_window._project.scene.zones == []
    assert main_window._image_path is None
    assert main_window._project_bundle_dir is None
    assert main_window._state is AppState.NO_IMAGE


def test_save_project_creates_bundle_and_updates_image_path(main_window, tmp_path, monkeypatch):
    _load(main_window, tmp_path, width=20, height=20)
    bundle_dir = tmp_path / "MonProjet.l3dproj"
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(bundle_dir), ""),
    )

    main_window._on_save_project_as()

    assert (bundle_dir / "project.json").exists()
    assert main_window._project_bundle_dir == bundle_dir
    assert main_window._image_path.startswith(str(bundle_dir))


def test_save_then_open_project_roundtrip(main_window, tmp_path, monkeypatch):
    _load(main_window, tmp_path, width=30, height=20)
    main_window._on_new_zone_clicked()
    zone = main_window._active_zone()
    zone.name = "Visage"
    mask = np.zeros((20, 30), dtype=np.float32)
    mask[:, 15:] = 1.0
    main_window._zone_masks[zone.id] = mask

    bundle_dir = tmp_path / "Portrait.l3dproj"
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(bundle_dir), ""),
    )
    main_window._on_save_project_as()

    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getExistingDirectory",
        lambda *a, **k: str(bundle_dir),
    )
    main_window._on_open_project()

    assert len(main_window._project.scene.zones) == 2
    names = {z.name for z in main_window._project.scene.zones}
    assert "Visage" in names
    assert "Lithophanie" in names
    assert main_window._image_path is not None
    from pathlib import Path

    assert Path(main_window._image_path).exists()


def test_full_acceptance_workflow(main_window, tmp_path, monkeypatch):
    """Critere de reussite Phase 2A : image -> zone par defaut -> nouvelle
    zone -> masque peint -> enregistrer -> fermer/rouvrir -> tout retrouve."""
    _load(main_window, tmp_path, width=40, height=30)
    assert len(main_window._project.scene.zones) == 1
    assert main_window._project.scene.zones[0].name == "Lithophanie"

    main_window._on_new_zone_clicked()
    second_zone = main_window._active_zone()
    second_zone.name = "Cheveux"
    painted_mask = np.zeros((30, 40), dtype=np.float32)
    painted_mask[5:15, 5:15] = 1.0
    main_window._zone_masks[second_zone.id] = painted_mask

    main_window._on_new_zone_clicked()
    assert len(main_window._project.scene.zones) == 3

    bundle_dir = tmp_path / "Complet.l3dproj"
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(bundle_dir), ""),
    )
    main_window._on_save_project_as()

    # "fermer" LithoShape3D : nouvelle fenetre independante simulant un
    # redemarrage
    import pyvista as pv

    from lithoshape3d.ui.main_window import MainWindow

    reopened = MainWindow(plotter=pv.Plotter(off_screen=True))
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getExistingDirectory",
        lambda *a, **k: str(bundle_dir),
    )
    reopened._on_open_project()

    assert len(reopened._project.scene.zones) == 3
    names = [z.name for z in reopened._project.scene.zones]
    assert "Lithophanie" in names
    assert "Cheveux" in names

    cheveux = next(z for z in reopened._project.scene.zones if z.name == "Cheveux")
    from lithoshape3d.core.scene.mask_io import load_zone_mask

    reloaded_mask = load_zone_mask(reopened._project_bundle_dir, cheveux, shape=(30, 40))
    assert reloaded_mask[10, 10] == 1.0
    assert reloaded_mask[0, 0] == 0.0

    reopened.plotter.close()
