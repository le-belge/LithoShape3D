import numpy as np
import pytest

from lithoshape3d.core.geometry.heightmap import (
    Heightmap,
    build_heightmap,
    grid_dimensions,
    height_mm_from_aspect_ratio,
    heightmap_from_image_path,
)
from lithoshape3d.core.scene.models import GeometryParameters
from tests.fixtures.synthetic_images import make_gradient_image


def test_heightmap_rejects_out_of_range_values():
    with pytest.raises(ValueError):
        Heightmap(values=np.array([[0.0, 1.5]], dtype=np.float32))


def test_heightmap_rejects_non_2d_array():
    with pytest.raises(ValueError):
        Heightmap(values=np.zeros((2, 2, 2), dtype=np.float32))


def test_grid_dimensions_derives_from_resolution():
    params = GeometryParameters(width_mm=90.0, height_mm=60.0, resolution=0.3)
    rows, cols = grid_dimensions(params)
    assert cols == round(90.0 / 0.3)
    assert rows == round(60.0 / 0.3)


def test_grid_dimensions_has_a_floor_of_two():
    params = GeometryParameters(width_mm=1.0, height_mm=1.0, resolution=10.0)
    rows, cols = grid_dimensions(params)
    assert rows >= 2
    assert cols >= 2


def test_build_heightmap_wraps_processed_array():
    processed = np.array([[0.0, 0.5], [1.0, 0.25]], dtype=np.float64)
    heightmap = build_heightmap(processed)
    assert heightmap.values.dtype == np.float32
    assert heightmap.shape == (2, 2)


def test_heightmap_from_image_path_matches_grid_dimensions(tmp_path):
    image_path = make_gradient_image(tmp_path / "gradient.png", width=64, height=48)
    params = GeometryParameters(width_mm=64.0, height_mm=48.0, resolution=1.0)

    heightmap = heightmap_from_image_path(image_path, params)

    assert heightmap.shape == grid_dimensions(params)
    assert heightmap.values.min() >= 0.0
    assert heightmap.values.max() <= 1.0


def test_height_mm_from_aspect_ratio():
    height_mm = height_mm_from_aspect_ratio(width_mm=100.0, image_width_px=200, image_height_px=100)
    assert height_mm == pytest.approx(50.0)
