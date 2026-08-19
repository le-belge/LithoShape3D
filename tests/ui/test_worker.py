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


def test_worker_emits_failed_for_missing_image():
    params = GeometryParameters(width_mm=30.0, height_mm=20.0, resolution=2.0)
    worker = GenerationWorker("/chemin/inexistant.png", params)

    errors = []
    worker.signals.failed.connect(errors.append)

    worker.run()

    assert len(errors) == 1
