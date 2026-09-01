"""UI v0.3 : materiaux par zone, support d'impression, mode d'affichage
Materiaux, export multi-materiaux."""

import numpy as np
import pytest

from lithoshape3d.core.geometry.composition import compose_scene_mesh
from lithoshape3d.core.scene.models import CompositionMode, ReliefMode, SupportType
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from lithoshape3d.ui.state import AppState
from lithoshape3d.viewer.scene_viewer import DisplayMode
from tests.fixtures.synthetic_images import make_gradient_image


def _load(main_window, tmp_path, width=60, height=45):
    image_path = make_gradient_image(tmp_path / "gradient.png", width=width, height=height)
    main_window._load_image(str(image_path))
    return image_path


def test_material_fields_write_to_active_zone(main_window, tmp_path):
    _load(main_window, tmp_path)
    zone = main_window._active_zone()

    main_window.material_name_edit.setText("Rose")
    main_window._on_material_changed()
    idx = main_window.material_filament_combo.findData("PETG")
    main_window.material_filament_combo.setCurrentIndex(idx)
    main_window.material_slot_spin.setValue(2)

    assert zone.material.name == "Rose"
    assert zone.material.filament_type == "PETG"
    assert zone.material.slot == 2


def test_material_slot_special_value_maps_to_none(main_window, tmp_path):
    _load(main_window, tmp_path)
    zone = main_window._active_zone()

    main_window.material_slot_spin.setValue(3)
    assert zone.material.slot == 3
    main_window.material_slot_spin.setValue(-1)
    assert zone.material.slot is None


def test_switching_zone_does_not_corrupt_material_fields(main_window, tmp_path):
    """Meme regression que pour relief/composition (voir test_main_window.py) :
    charger les champs materiau d'une zone ne doit pas ecraser ceux d'une
    autre zone avec des valeurs perimees des widgets."""
    _load(main_window, tmp_path)
    zone_a = main_window._active_zone()
    zone_a.material.name = "Blanc"
    zone_a.material.filament_type = "PLA"

    main_window._on_new_zone_clicked()
    zone_b = main_window._active_zone()
    zone_b.material.name = "Rose"
    zone_b.material.filament_type = "PETG"
    main_window._refresh_zones_list()

    main_window.zones_list.setCurrentRow(0)
    main_window.zones_list.setCurrentRow(1)

    assert zone_a.material.name == "Blanc"
    assert zone_a.material.filament_type == "PLA"
    assert zone_b.material.name == "Rose"
    assert zone_b.material.filament_type == "PETG"


def test_support_fields_write_to_scene_support(main_window):
    idx = main_window.support_type_combo.findData(SupportType.FLAT)
    main_window.support_type_combo.setCurrentIndex(idx)
    main_window.support_height_spin.setValue(12.0)
    main_window.support_depth_spin.setValue(30.0)
    main_window.support_overhang_left_spin.setValue(4.0)
    main_window.support_overhang_right_spin.setValue(6.0)

    support = main_window._project.scene.support
    assert support.support_type is SupportType.FLAT
    assert support.height_mm == 12.0
    assert support.depth_mm == 30.0
    assert support.overhang_left_mm == 4.0
    assert support.overhang_right_mm == 6.0


def test_side_stabilizers_checkbox_writes_to_scene_support(main_window):
    assert main_window._project.scene.support.side_stabilizers is False
    main_window.support_side_stabilizers_checkbox.setChecked(True)
    assert main_window._project.scene.support.side_stabilizers is True


def test_load_support_into_panel_reflects_side_stabilizers(main_window):
    from lithoshape3d.core.scene.models import PrintSupport

    main_window._project.scene.support = PrintSupport(side_stabilizers=True)
    main_window._load_support_into_panel()

    assert main_window.support_side_stabilizers_checkbox.isChecked()


def test_materials_display_includes_two_detachable_side_stabilizers(main_window, tmp_path):
    _load(main_window, tmp_path, width=60, height=45)
    main_window.resolution_spin.setValue(3.0)
    main_window.support_side_stabilizers_checkbox.setChecked(True)

    panel_mesh = compose_scene_mesh(main_window._build_zone_sources())
    main_window._current_mesh = panel_mesh
    main_window._current_material_meshes = {"Blanc": panel_mesh}

    materials = main_window._materials_for_display()
    left_mesh, _color_l = materials["Stabilisateur gauche (detachable)"]
    right_mesh, _color_r = materials["Stabilisateur droit (detachable)"]

    for mesh in (left_mesh, right_mesh):
        result = validate_mesh(mesh)
        assert result.is_valid

    # Jamais fusionnes au panneau (des fichiers separes a l'export) et
    # positionnes pour que les dents du gabarit (pas sa face large, cf.
    # rotation dans support.py -- retour terrain utilisateur) penetrent
    # legerement dans le bord gauche du panneau (recouvrement volontaire,
    # pas une simple tangence -- cf. `_STABILIZER_CONTACT_OVERLAP_MM`) --
    # meme verification que test_support.py::test_side_stabilizer_teeth_....
    overlap = 0.06
    panel_x_min = float(panel_mesh.bounds[0][0])
    section = left_mesh.section(plane_origin=[0, left_mesh.bounds[0][1] + 2, 0], plane_normal=[0, 1, 0])
    assert section.vertices[:, 0].max() == pytest.approx(panel_x_min + overlap, abs=1e-3)


def test_export_routes_through_multi_file_when_stabilizers_enabled(main_window, tmp_path, monkeypatch):
    _load(main_window, tmp_path, width=60, height=45)
    main_window.resolution_spin.setValue(3.0)
    main_window.support_side_stabilizers_checkbox.setChecked(True)

    panel_mesh = compose_scene_mesh(main_window._build_zone_sources())
    main_window._current_mesh = panel_mesh
    main_window._current_material_meshes = {"Blanc": panel_mesh}
    main_window._set_state(AppState.MESH_READY)

    stl_dir = tmp_path / "stl_export"
    stl_dir.mkdir()
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getExistingDirectory",
        lambda *a, **k: str(stl_dir),
    )
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(tmp_path / "ne-devrait-pas-etre-utilise.stl"), ""),
    )
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.critical", lambda *a, **k: None)

    main_window._on_export_clicked()

    written_stl = list(stl_dir.glob("*.stl"))
    assert len(written_stl) == 3  # Blanc + stabilisateur gauche + droit
    assert not (tmp_path / "ne-devrait-pas-etre-utilise.stl").exists()


def test_exported_stl_is_oriented_for_vertical_printing(main_window, tmp_path, monkeypatch):
    """Le modele travaille en Y=hauteur/Z=epaisseur (convention interne),
    mais s'imprime reellement DEBOUT -- l'export doit livrer un fichier
    deja tourne pour ca (l'ancienne hauteur devient l'axe vertical Z),
    sans que l'utilisateur ait a le reorienter dans le slicer."""
    _load(main_window, tmp_path, width=60, height=45)
    main_window.resolution_spin.setValue(3.0)

    panel_mesh = compose_scene_mesh(main_window._build_zone_sources())
    original_height = float(panel_mesh.bounds[1][1] - panel_mesh.bounds[0][1])
    original_thickness = float(panel_mesh.bounds[1][2] - panel_mesh.bounds[0][2])

    main_window._current_mesh = panel_mesh
    main_window._set_state(AppState.MESH_READY)

    stl_path = tmp_path / "oriented.stl"
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(stl_path), ""),
    )
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.critical", lambda *a, **k: None)

    main_window._on_export_clicked()

    import trimesh

    reloaded = trimesh.load(stl_path)
    # L'ancienne hauteur (Y) est maintenant portee par Z (axe vertical
    # d'impression) ; l'ancienne epaisseur (Z) est maintenant sur Y.
    assert float(reloaded.bounds[1][2] - reloaded.bounds[0][2]) == pytest.approx(original_height, abs=1e-3)
    assert float(reloaded.bounds[1][1] - reloaded.bounds[0][1]) == pytest.approx(
        original_thickness, abs=1e-3
    )
    # Coordonnees non negatives, pret pour un slicer (plateau a Z=0).
    assert reloaded.bounds[0][2] >= -1e-6


def test_load_support_into_panel_reflects_project_state(main_window):
    from lithoshape3d.core.scene.models import PrintSupport

    main_window._project.scene.support = PrintSupport(
        support_type=SupportType.REINFORCED, height_mm=15.0
    )
    main_window._load_support_into_panel()

    assert main_window.support_type_combo.currentData() is SupportType.REINFORCED
    assert main_window.support_height_spin.value() == 15.0


def test_composition_with_support_produces_single_manifold_body(main_window, tmp_path):
    _load(main_window, tmp_path, width=60, height=45)
    main_window.resolution_spin.setValue(3.0)

    idx = main_window.support_type_combo.findData(SupportType.FLAT)
    main_window.support_type_combo.setCurrentIndex(idx)

    main_window.view_composition_button.setChecked(True)
    main_window._on_generate_clicked()
    assert main_window._state is AppState.GENERATING

    from lithoshape3d.core.geometry.support import attach_support

    panel_mesh = compose_scene_mesh(main_window._build_zone_sources())
    fused = attach_support(panel_mesh, main_window._project.scene.support)
    result = validate_mesh(fused)
    assert result.is_valid
    assert result.connected_components == 1

    main_window._on_composition_succeeded(fused, float(panel_mesh.vertices[:, 2].max()))
    assert main_window._state is AppState.MESH_READY
    assert main_window._current_mesh is fused
    assert main_window._current_panel_z_max == float(panel_mesh.vertices[:, 2].max())


def test_materials_display_mode_partitions_by_zone_material(main_window, tmp_path):
    _load(main_window, tmp_path, width=60, height=45)
    main_window.resolution_spin.setValue(3.0)
    white_zone = main_window._active_zone()
    white_zone.material.name = "Blanc"

    main_window._on_new_zone_clicked()
    rose_zone = main_window._active_zone()
    rose_zone.composition_mode = CompositionMode.REPLACE
    rose_zone.relief_mode = ReliefMode.SOLID
    rose_zone.material.name = "Rose"
    mask = np.zeros((45, 60), dtype=np.float32)
    mask[10:20, 15:30] = 1.0
    main_window._zone_masks[rose_zone.id] = mask
    main_window._refresh_zones_list()

    materials = main_window._materials_for_display()

    assert set(materials.keys()) == {"Blanc", "Rose"}


def test_display_mode_materials_renders_without_error(main_window, tmp_path):
    _load(main_window, tmp_path, width=60, height=45)
    main_window.resolution_spin.setValue(3.0)
    mesh = compose_scene_mesh(main_window._build_zone_sources())
    main_window._on_composition_succeeded(mesh, float(mesh.vertices[:, 2].max()))

    idx = main_window.display_mode_combo.findData(DisplayMode.MATERIALS)
    main_window.display_mode_combo.setCurrentIndex(idx)  # ne doit pas lever

    assert len(main_window.scene_viewer._material_actors) >= 1


def test_export_multi_material_disabled_hint_for_single_material(main_window, tmp_path, monkeypatch):
    """Un seul materiau utilise : le bouton multi-materiaux doit informer
    plutot que tenter un export 3MF inutile (verifie via l'absence d'appel
    au dialogue de sauvegarde)."""
    _load(main_window, tmp_path, width=60, height=45)
    main_window.resolution_spin.setValue(3.0)
    mesh = compose_scene_mesh(main_window._build_zone_sources())
    main_window._on_composition_succeeded(mesh, float(mesh.vertices[:, 2].max()))

    called = []
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: called.append(True) or ("", ""),
    )
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.information", lambda *a, **k: None)

    main_window._on_export_multi_material_clicked()

    assert not called
