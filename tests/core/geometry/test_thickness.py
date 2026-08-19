import numpy as np
import pytest

from lithoshape3d.core.geometry.thickness import compute_thickness_mm
from lithoshape3d.core.scene.models import GeometryParameters


def _params(**overrides) -> GeometryParameters:
    defaults = {
        "width_mm": 100.0,
        "height_mm": 100.0,
        "min_thickness_mm": 0.8,
        "max_thickness_mm": 3.0,
    }
    defaults.update(overrides)
    return GeometryParameters(**defaults)


def test_black_pixel_is_max_thickness_without_invert():
    values = np.zeros((2, 2), dtype=np.float32)
    thickness = compute_thickness_mm(values, _params(invert=False))
    assert np.allclose(thickness, 3.0)


def test_white_pixel_is_min_thickness_without_invert():
    values = np.ones((2, 2), dtype=np.float32)
    thickness = compute_thickness_mm(values, _params(invert=False))
    assert np.allclose(thickness, 0.8)


def test_invert_swaps_the_relationship():
    values = np.zeros((2, 2), dtype=np.float32)
    thickness_normal = compute_thickness_mm(values, _params(invert=False))
    thickness_inverted = compute_thickness_mm(values, _params(invert=True))

    assert np.allclose(thickness_normal, 3.0)
    assert np.allclose(thickness_inverted, 0.8)


def test_thickness_is_deterministic():
    values = np.array([[0.0, 0.25], [0.5, 1.0]], dtype=np.float32)
    params = _params()

    first = compute_thickness_mm(values, params)
    second = compute_thickness_mm(values, params)

    assert np.array_equal(first, second)


def test_thickness_stays_within_min_max_bounds():
    rng = np.random.default_rng(42)
    values = rng.random((16, 16), dtype=np.float32)
    params = _params()

    thickness = compute_thickness_mm(values, params)

    assert thickness.min() >= params.min_thickness_mm - 1e-6
    assert thickness.max() <= params.max_thickness_mm + 1e-6


def test_rejects_max_not_greater_than_min():
    values = np.zeros((2, 2), dtype=np.float32)
    with pytest.raises(ValueError):
        compute_thickness_mm(values, _params(min_thickness_mm=2.0, max_thickness_mm=2.0))


def test_rejects_non_positive_min_thickness():
    values = np.zeros((2, 2), dtype=np.float32)
    with pytest.raises(ValueError):
        compute_thickness_mm(values, _params(min_thickness_mm=0.0))
