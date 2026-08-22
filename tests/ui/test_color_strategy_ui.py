"""UI v0.4.1 : panneau "Strategie couleur" (Materiau seul / Insert retro-
eclaire), visibilite conditionnelle des parametres Backlight Insert, et
persistance projet (Test E de la mission -- save/close/reopen)."""

import numpy as np

from lithoshape3d.core.geometry.composition import compose_scene_mesh
from lithoshape3d.core.scene.models import ColorStrategy, CompositionMode
from lithoshape3d.core.scene.project_io import load_project_bundle
from tests.fixtures.synthetic_images import make_gradient_image


def _load(main_window, tmp_path, width=60, height=45):
    image_path = make_gradient_image(tmp_path / "gradient.png", width=width, height=height)
    main_window._load_image(str(image_path))
    return image_path


def test_new_zone_defaults_to_material_only(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._on_new_zone_clicked()
    zone = main_window._active_zone()

    assert zone.color_strategy is ColorStrategy.MATERIAL_ONLY


def test_color_strategy_combo_writes_to_active_zone(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._on_new_zone_clicked()
    zone = main_window._active_zone()

    idx = main_window.color_strategy_combo.findData(ColorStrategy.BACKLIGHT_INSERT)
    main_window.color_strategy_combo.setCurrentIndex(idx)

    assert zone.color_strategy is ColorStrategy.BACKLIGHT_INSERT


def test_backlight_params_write_to_active_zone(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._on_new_zone_clicked()
    zone = main_window._active_zone()

    idx = main_window.color_strategy_combo.findData(ColorStrategy.BACKLIGHT_INSERT)
    main_window.color_strategy_combo.setCurrentIndex(idx)
    main_window.backlight_skin_spin.setValue(0.5)
    main_window.backlight_insert_thickness_spin.setValue(0.7)
    idx = main_window.backlight_clearance_combo.findData(0.30)
    main_window.backlight_clearance_combo.setCurrentIndex(idx)

    assert zone.backlight_insert.white_skin_thickness_mm == 0.5
    assert zone.backlight_insert.insert_thickness_mm == 0.7
    assert zone.backlight_insert.xy_clearance_mm == 0.30


def test_backlight_params_hidden_unless_backlight_selected(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._on_new_zone_clicked()
    # `_on_new_zone_clicked` seul ne rafraichit pas le panneau (comme pour
    # relief/composition/materiau) -- il faut une vraie selection pour que
    # `_load_zone_params_into_panel` (et donc la visibilite) se synchronise,
    # exactement comme le ferait un vrai clic dans la liste des zones.
    main_window._refresh_zones_list()
    main_window.zones_list.setCurrentRow(main_window.zones_list.count() - 1)
    main_window._on_zone_selection_changed()

    assert main_window.color_strategy_combo.currentData() is ColorStrategy.MATERIAL_ONLY
    assert main_window.backlight_skin_spin.isHidden()
    assert main_window.backlight_insert_thickness_spin.isHidden()
    assert main_window.backlight_clearance_combo.isHidden()

    idx = main_window.color_strategy_combo.findData(ColorStrategy.BACKLIGHT_INSERT)
    main_window.color_strategy_combo.setCurrentIndex(idx)

    assert not main_window.backlight_skin_spin.isHidden()
    assert not main_window.backlight_insert_thickness_spin.isHidden()
    assert not main_window.backlight_clearance_combo.isHidden()


def test_switching_zone_does_not_corrupt_color_strategy(main_window, tmp_path):
    """Meme regression que relief/composition/materiau (cf. memoire de
    session 0.2.0) : charger le panneau d'une zone ne doit pas ecraser
    color_strategy d'une autre zone avec une valeur perimee du combo."""
    _load(main_window, tmp_path)
    main_window._on_new_zone_clicked()
    zone_a = main_window._active_zone()
    zone_a.color_strategy = ColorStrategy.BACKLIGHT_INSERT

    main_window._on_new_zone_clicked()
    zone_b = main_window._active_zone()
    zone_b.color_strategy = ColorStrategy.MATERIAL_ONLY
    main_window._refresh_zones_list()

    main_window.zones_list.setCurrentRow(0)
    main_window.zones_list.setCurrentRow(1)

    assert zone_a.color_strategy is ColorStrategy.BACKLIGHT_INSERT
    assert zone_b.color_strategy is ColorStrategy.MATERIAL_ONLY


def test_backlight_project_round_trip_preserves_all_parameters(main_window, tmp_path):
    """Test E de la mission 0.4.1 : sauvegarder un projet Backlight Insert,
    le rouvrir, comparer tous les parametres -- aucun reset silencieux."""
    import pyvista as pv

    from lithoshape3d.ui.main_window import MainWindow

    _load(main_window, tmp_path, width=60, height=45)
    base_zone = main_window._active_zone()
    base_zone.material.name = "Blanc"

    main_window._on_new_zone_clicked()
    rose_zone = main_window._active_zone()
    rose_zone.composition_mode = CompositionMode.ADD
    rose_zone.material.name = "Rose"
    mask = np.zeros((45, 60), dtype=np.float32)
    mask[10:20, 15:30] = 1.0
    main_window._zone_masks[rose_zone.id] = mask

    idx = main_window.color_strategy_combo.findData(ColorStrategy.BACKLIGHT_INSERT)
    main_window.color_strategy_combo.setCurrentIndex(idx)
    main_window.backlight_skin_spin.setValue(0.45)
    main_window.backlight_insert_thickness_spin.setValue(0.65)
    idx = main_window.backlight_clearance_combo.findData(0.10)
    main_window.backlight_clearance_combo.setCurrentIndex(idx)

    assert rose_zone.color_strategy is ColorStrategy.BACKLIGHT_INSERT
    assert rose_zone.backlight_insert.white_skin_thickness_mm == 0.45

    bundle_dir = tmp_path / "BacklightTest.l3dproj"
    main_window._save_project_to(bundle_dir)

    reloaded_project = load_project_bundle(bundle_dir)
    reloaded_rose = next(z for z in reloaded_project.scene.zones if z.name == rose_zone.name)
    assert reloaded_rose.color_strategy is ColorStrategy.BACKLIGHT_INSERT
    assert reloaded_rose.backlight_insert.white_skin_thickness_mm == 0.45
    assert reloaded_rose.backlight_insert.insert_thickness_mm == 0.65
    assert reloaded_rose.backlight_insert.xy_clearance_mm == 0.10
    assert reloaded_rose.material.name == "Rose"

    reopened = MainWindow(plotter=pv.Plotter(off_screen=True))
    try:
        reopened._project = reloaded_project
        reopened._project_bundle_dir = bundle_dir
        reopened_zone = next(z for z in reopened._project.scene.zones if z.name == rose_zone.name)
        assert reopened_zone.color_strategy is ColorStrategy.BACKLIGHT_INSERT
    finally:
        reopened.plotter.close()


def test_generation_ignores_material_only_zone_height_via_ui(main_window, tmp_path):
    """Regression bout-en-bout (pas seulement au niveau core) : generer via
    le vrai chemin UI (_build_zone_sources) avec une zone MATERIAL_ONLY ne
    doit produire aucune difference de hauteur par rapport a la version
    entierement blanche."""
    image_path = make_gradient_image(tmp_path / "gradient.png", width=60, height=45)
    main_window._load_image(str(image_path))
    main_window.resolution_spin.setValue(1.0)

    baseline_mesh = compose_scene_mesh(main_window._build_zone_sources())

    main_window._on_new_zone_clicked()
    colored_zone = main_window._active_zone()
    assert colored_zone.color_strategy is ColorStrategy.MATERIAL_ONLY
    mask = np.zeros((45, 60), dtype=np.float32)
    mask[10:20, 15:30] = 1.0
    main_window._zone_masks[colored_zone.id] = mask

    colored_mesh = compose_scene_mesh(main_window._build_zone_sources())

    assert np.array_equal(baseline_mesh.vertices, colored_mesh.vertices)
