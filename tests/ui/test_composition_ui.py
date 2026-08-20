import numpy as np

from lithoshape3d.core.scene.models import CompositionMode, ReliefMode
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from lithoshape3d.ui.state import AppState
from tests.fixtures.synthetic_images import make_gradient_image


def _load(main_window, tmp_path, width=60, height=45):
    image_path = make_gradient_image(tmp_path / "gradient.png", width=width, height=height)
    main_window._load_image(str(image_path))
    return image_path


def test_default_zone_is_base_composition_mode(main_window, tmp_path):
    _load(main_window, tmp_path)
    zone = main_window._active_zone()

    assert zone.composition_mode is CompositionMode.BASE


def test_new_zone_defaults_to_add(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._on_new_zone_clicked()
    zone = main_window._active_zone()

    assert zone.composition_mode is CompositionMode.ADD


def test_role_combo_changes_are_written_to_active_zone(main_window, tmp_path):
    _load(main_window, tmp_path)
    zone = main_window._active_zone()

    idx = main_window.composition_mode_combo.findData(CompositionMode.REPLACE)
    main_window.composition_mode_combo.setCurrentIndex(idx)
    idx2 = main_window.relief_mode_combo.findData(ReliefMode.SOLID)
    main_window.relief_mode_combo.setCurrentIndex(idx2)

    assert zone.composition_mode is CompositionMode.REPLACE
    assert zone.relief_mode is ReliefMode.SOLID


def test_role_combo_loads_correct_values_on_zone_switch(main_window, tmp_path):
    _load(main_window, tmp_path)
    first_zone = main_window._active_zone()
    idx = main_window.composition_mode_combo.findData(CompositionMode.REPLACE)
    main_window.composition_mode_combo.setCurrentIndex(idx)

    main_window._on_new_zone_clicked()  # nouvelle zone active, defaut ADD
    assert main_window.composition_mode_combo.currentData() is CompositionMode.ADD

    main_window.zones_list.setCurrentRow(0)
    main_window._on_zone_selection_changed()

    assert main_window._active_zone() is first_zone
    assert main_window.composition_mode_combo.currentData() is CompositionMode.REPLACE


def test_role_change_marks_ready_mesh_as_dirty(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window.resolution_spin.setValue(3.0)
    zone = main_window._active_zone()

    from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
    from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh

    params = main_window._current_geometry_parameters()
    heightmap = heightmap_from_image_path(main_window._image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)
    main_window._on_generation_succeeded(mesh)
    assert main_window._state is AppState.MESH_READY

    idx = main_window.relief_mode_combo.findData(ReliefMode.SOLID)
    main_window.relief_mode_combo.setCurrentIndex(idx)

    assert main_window._state is AppState.PARAMS_DIRTY
    assert zone.relief_mode is ReliefMode.SOLID


def test_view_scope_defaults_to_zone_active(main_window):
    assert main_window.view_zone_button.isChecked()
    assert not main_window.view_composition_button.isChecked()


def test_build_zone_sources_reflects_all_zones_in_order(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._on_new_zone_clicked()
    main_window._on_new_zone_clicked()

    sources = main_window._build_zone_sources()

    assert [s.zone.id for s in sources] == [z.id for z in main_window._project.scene.zones]
    assert all(s.image_path == main_window._image_path for s in sources)


def test_composition_generation_end_to_end_via_composition_worker(main_window, tmp_path):
    """Critere de reussite Phase 2C : base + zone ADD + zone REPLACE ->
    un seul mesh compose manifold, affichable et exportable."""
    _load(main_window, tmp_path, width=60, height=45)
    main_window.resolution_spin.setValue(3.0)

    # zone ADD : carre surelevee
    main_window._on_new_zone_clicked()
    add_zone = main_window._active_zone()
    add_zone.relief_mode = ReliefMode.SOLID
    add_zone.geometry_params.min_thickness_mm = 1.0
    add_zone.geometry_params.max_thickness_mm = 1.0
    add_mask = np.zeros((45, 60), dtype=np.float32)
    add_mask[10:20, 15:30] = 1.0
    main_window._zone_masks[add_zone.id] = add_mask

    # zone REPLACE : coin remplace
    main_window._on_new_zone_clicked()
    replace_zone = main_window._active_zone()
    replace_zone.composition_mode = CompositionMode.REPLACE
    replace_zone.relief_mode = ReliefMode.SOLID
    replace_zone.geometry_params.min_thickness_mm = 0.3
    replace_zone.geometry_params.max_thickness_mm = 0.3
    replace_mask = np.zeros((45, 60), dtype=np.float32)
    replace_mask[30:40, 5:20] = 1.0
    main_window._zone_masks[replace_zone.id] = replace_mask

    main_window.view_composition_button.setChecked(True)
    main_window._on_generate_clicked()
    assert main_window._state is AppState.GENERATING

    from lithoshape3d.core.geometry.composition import compose_scene_mesh

    # execute directement le meme calcul (synchrone) pour verifier le resultat
    mesh = compose_scene_mesh(main_window._build_zone_sources())
    result = validate_mesh(mesh)
    assert result.is_valid

    main_window._on_generation_succeeded(mesh)
    assert main_window._state is AppState.MESH_READY
    assert main_window._current_mesh is mesh
