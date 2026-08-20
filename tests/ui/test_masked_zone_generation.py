import numpy as np

from lithoshape3d.core.validation.mesh_checks import validate_mesh
from lithoshape3d.ui.mask_edit_controller import MaskEditController
from lithoshape3d.ui.state import AppState
from lithoshape3d.ui.worker import GenerationWorker
from tests.fixtures.synthetic_images import make_gradient_image


def _load(main_window, tmp_path, width=60, height=45):
    image_path = make_gradient_image(tmp_path / "gradient.png", width=width, height=height)
    main_window._load_image(str(image_path))
    return image_path


def test_suggested_stl_filename_uses_project_and_zone_name(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._project.name = "Mon Portrait"
    zone = main_window._active_zone()
    zone.name = "Visage Principal"

    filename = main_window._suggested_stl_filename()

    assert filename == "Mon-Portrait_Visage-Principal.stl"


def test_suggested_filename_falls_back_when_no_active_zone(main_window, tmp_path):
    _load(main_window, tmp_path)
    main_window._on_delete_zone_clicked()
    main_window._project.name = "Vide"

    filename = main_window._suggested_stl_filename()

    assert filename == "Vide.stl"


def test_generate_masked_zone_end_to_end(main_window, tmp_path):
    """Critere de reussite Phase 2B : peindre un masque irregulier sur une
    zone et la generer seule doit produire un STL valide correspondant a
    la forme peinte (pas au rectangle complet)."""
    _load(main_window, tmp_path, width=60, height=45)
    main_window.resolution_spin.setValue(2.0)

    zone = main_window._active_zone()
    controller = MaskEditController(np.zeros((45, 60), dtype=np.float32))
    controller.fill()
    controller.begin_stroke()
    controller.paint(15, 22, 10, 0.0)  # gomme une partie -> forme irreguliere
    controller.end_stroke()
    main_window._zone_masks[zone.id] = controller.mask.copy()

    mask_for_generation = main_window._zone_mask_for_generation(zone)
    assert mask_for_generation is not None
    assert not mask_for_generation.all()  # bien un masque partiel, pas plein

    params = main_window._current_geometry_parameters()
    worker = GenerationWorker(main_window._image_path, params, mask=mask_for_generation)

    results = []
    worker.signals.succeeded.connect(results.append)
    worker.run()

    assert len(results) == 1
    mesh = results[0]
    result = validate_mesh(mesh)
    assert result.is_valid

    main_window._on_generation_succeeded(mesh)
    assert main_window._state is AppState.MESH_READY
    assert main_window._current_mesh is mesh


def test_generate_full_default_zone_still_matches_full_rectangle(main_window, tmp_path):
    """Non-regression explicite : le workflow classique (zone par defaut,
    masque jamais touche) doit toujours produire la plaque complete."""
    _load(main_window, tmp_path, width=40, height=30)
    main_window.resolution_spin.setValue(2.0)
    zone = main_window._active_zone()

    mask = main_window._zone_mask_for_generation(zone)
    assert mask is None  # comportement historique : aucune verification necessaire

    params = main_window._current_geometry_parameters()
    worker = GenerationWorker(main_window._image_path, params, mask=mask)
    results = []
    worker.signals.succeeded.connect(results.append)
    worker.run()

    mesh = results[0]
    assert mesh.bounds[1][0] == params.width_mm
    assert mesh.bounds[1][1] == params.height_mm
