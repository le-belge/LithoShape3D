import numpy as np

from lithoshape3d.core.scene.models import GeometryParameters
from lithoshape3d.ui.worker import GenerationWorker
from tests.fixtures.synthetic_images import make_uniform_image


def test_worker_emits_succeeded_for_valid_params(tmp_path):
    image_path = make_uniform_image(tmp_path / "mid.png", value=128)
    params = GeometryParameters(width_mm=30.0, height_mm=20.0, resolution=2.0)
    worker = GenerationWorker(str(image_path), params)

    results = []
    errors = []
    finished = []
    worker.signals.succeeded.connect(results.append)
    worker.signals.failed.connect(errors.append)
    worker.signals.finished.connect(lambda: finished.append(True))

    worker.run()  # execution synchrone directe, sans QThreadPool

    assert len(results) == 1
    assert not errors
    assert finished == [True]
    mesh = results[0]
    assert len(mesh.vertices) > 0


def test_worker_emits_failed_for_invalid_params(tmp_path):
    image_path = make_uniform_image(tmp_path / "mid.png", value=128)
    # min >= max : rejete par core/geometry/thickness.py
    params = GeometryParameters(
        width_mm=30.0, height_mm=20.0, resolution=2.0, min_thickness_mm=2.0, max_thickness_mm=2.0
    )
    worker = GenerationWorker(str(image_path), params)

    results = []
    errors = []
    finished = []
    worker.signals.succeeded.connect(results.append)
    worker.signals.failed.connect(errors.append)
    worker.signals.finished.connect(lambda: finished.append(True))

    worker.run()

    assert not results
    assert len(errors) == 1
    assert "thickness" in errors[0] or "superieur" in errors[0]
    assert finished == [True]


def test_worker_generates_a_valid_mesh_for_a_partial_mask(tmp_path):
    """Depuis la Phase 2B, un masque partiel est reellement supporte par le
    moteur (voir tests/core/geometry/test_masked_mesh.py pour la couverture
    complete des topologies)."""
    image_path = make_uniform_image(tmp_path / "mid.png", value=128, width=20, height=20)
    params = GeometryParameters(width_mm=30.0, height_mm=20.0, resolution=2.0)
    rows, cols = 10, 15
    partial_mask = np.ones((rows, cols), dtype=np.float32)
    partial_mask[:, cols // 2 :] = 0.0  # moitie seulement
    worker = GenerationWorker(str(image_path), params, mask=partial_mask)

    errors = []
    results = []
    worker.signals.failed.connect(errors.append)
    worker.signals.succeeded.connect(results.append)

    worker.run()

    assert not errors
    assert len(results) == 1


def test_worker_accepts_fully_active_mask_like_no_mask(tmp_path):
    image_path = make_uniform_image(tmp_path / "mid.png", value=128, width=20, height=20)
    params = GeometryParameters(width_mm=30.0, height_mm=20.0, resolution=2.0)
    worker_no_mask = GenerationWorker(str(image_path), params)
    worker_full_mask = GenerationWorker(
        str(image_path), params, mask=np.ones((10, 15), dtype=np.float32)
    )

    results_a, results_b = [], []
    worker_no_mask.signals.succeeded.connect(results_a.append)
    worker_full_mask.signals.succeeded.connect(results_b.append)

    worker_no_mask.run()
    worker_full_mask.run()

    assert len(results_a) == 1
    assert len(results_b) == 1


def test_worker_emits_failed_for_missing_image():
    params = GeometryParameters(width_mm=30.0, height_mm=20.0, resolution=2.0)
    worker = GenerationWorker("/chemin/inexistant.png", params)

    errors = []
    worker.signals.failed.connect(errors.append)

    worker.run()

    assert len(errors) == 1
