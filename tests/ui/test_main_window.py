import time

from lithoshape3d.ui.state import AppState
from tests.fixtures.synthetic_images import make_gradient_image


def _load(main_window, tmp_path, width=64, height=48):
    image_path = make_gradient_image(tmp_path / "gradient.png", width=width, height=height)
    main_window._load_image(str(image_path))
    return image_path


def test_initial_state_has_everything_disabled(main_window):
    assert main_window._state is AppState.NO_IMAGE
    assert not main_window.generate_button.isEnabled()
    assert not main_window.export_button.isEnabled()


def test_loading_image_enables_generate_but_not_export(main_window, tmp_path):
    _load(main_window, tmp_path)

    assert main_window._state is AppState.IMAGE_LOADED
    assert main_window.generate_button.isEnabled()
    assert not main_window.export_button.isEnabled()
    assert "64" in main_window.dimensions_label.text()
    assert "48" in main_window.dimensions_label.text()


def test_ratio_logic_updates_height_display(main_window, tmp_path):
    _load(main_window, tmp_path, width=200, height=100)  # ratio 2:1

    main_window.width_spin.setValue(80.0)

    assert main_window.height_display.text().strip() == "40.0 mm"


def test_param_change_before_generation_stays_image_loaded(main_window, tmp_path):
    _load(main_window, tmp_path)

    main_window.resolution_spin.setValue(0.5)

    assert main_window._state is AppState.IMAGE_LOADED


def test_successful_generation_reaches_mesh_ready_and_enables_export(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window.resolution_spin.setValue(3.0)  # grille modeste pour un test rapide

    params = main_window._current_geometry_parameters()
    from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
    from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh

    heightmap = heightmap_from_image_path(main_window._image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)

    main_window._on_generation_succeeded(mesh)

    assert main_window._state is AppState.MESH_READY
    assert main_window.export_button.isEnabled()
    assert main_window._current_mesh is mesh


def test_param_change_after_mesh_ready_invalidates_it(main_window, tmp_path):
    _load(main_window, tmp_path)
    params = main_window._current_geometry_parameters()
    from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
    from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh

    heightmap = heightmap_from_image_path(main_window._image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)
    main_window._on_generation_succeeded(mesh)
    assert main_window._state is AppState.MESH_READY

    main_window.max_thickness_spin.setValue(5.0)

    assert main_window._state is AppState.PARAMS_DIRTY
    assert not main_window.export_button.isEnabled()
    # le mesh perime reste en memoire mais ne doit jamais etre exportable
    assert main_window._current_mesh is mesh


def test_generation_failure_reaches_error_state_without_raising(main_window, tmp_path, monkeypatch):
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.warning", lambda *a, **k: None)
    _load(main_window, tmp_path)
    main_window.min_thickness_spin.setValue(2.0)
    main_window.max_thickness_spin.setValue(2.0)  # invalide : min >= max

    main_window._on_generation_failed("Mesh invalide : max_thickness_mm doit etre superieur")

    assert main_window._state is AppState.ERROR
    assert not main_window.export_button.isEnabled()


def test_export_without_mesh_does_nothing(main_window, tmp_path, monkeypatch):
    _load(main_window, tmp_path)
    called = []
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: called.append(True) or ("", ""),
    )

    main_window._on_export_clicked()

    assert not called  # jamais atteint : pas de mesh pret


def test_export_writes_a_valid_stl(main_window, tmp_path, monkeypatch):
    _load(main_window, tmp_path)
    params = main_window._current_geometry_parameters()
    from lithoshape3d.core.export.stl_export import load_stl
    from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
    from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
    from lithoshape3d.core.validation.mesh_checks import validate_mesh

    heightmap = heightmap_from_image_path(main_window._image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)
    main_window._on_generation_succeeded(mesh)

    output_path = tmp_path / "export.stl"
    monkeypatch.setattr(
        "lithoshape3d.ui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(output_path), "STL (*.stl)"),
    )
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.information", lambda *a, **k: None)

    main_window._on_export_clicked()

    assert output_path.exists()
    reloaded = load_stl(output_path)
    assert validate_mesh(reloaded).is_valid


def test_reset_restores_default_parameters(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window.width_spin.setValue(250.0)
    main_window.invert_checkbox.setChecked(True)

    main_window._on_reset_clicked()

    assert main_window.width_spin.value() == 100.0
    assert main_window.invert_checkbox.isChecked() is False


def test_end_to_end_generate_via_thread_pool(qapp, main_window, tmp_path, monkeypatch):
    """Verifie le cablage reel worker -> QThreadPool -> signal -> UI thread."""
    monkeypatch.setattr("lithoshape3d.ui.main_window.QMessageBox.warning", lambda *a, **k: None)
    _load(main_window, tmp_path)
    main_window.resolution_spin.setValue(3.0)

    main_window._on_generate_clicked()
    assert main_window._state is AppState.GENERATING
    assert not main_window.generate_button.isEnabled()

    deadline = time.monotonic() + 10
    while main_window._state is AppState.GENERATING and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)

    assert main_window._state is AppState.MESH_READY
    assert main_window.export_button.isEnabled()
    assert main_window._current_mesh is not None
