import numpy as np
import pytest

from lithoshape3d.core.geometry.lightbox import (
    LightBoxFaceMode,
    LightBoxParameters,
    build_lightbox_from_shape_mask,
)
from lithoshape3d.core.scene.models import GeometryParameters
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from tests.fixtures.synthetic_images import make_uniform_image


def _face_params() -> GeometryParameters:
    return GeometryParameters(
        width_mm=60.0,
        height_mm=60.0,
        min_thickness_mm=0.8,
        max_thickness_mm=3.0,
        resolution=2.0,
    )


def _ring_mask(size: int = 30) -> np.ndarray:
    mask = np.zeros((size, size), dtype=bool)
    mask[3:-3, 3:-3] = True
    mask[11:19, 11:19] = False
    return mask


def _xy_vertices_inside(mesh, x_min, x_max, y_min, y_max):
    vertices = mesh.vertices
    return vertices[
        (vertices[:, 0] > x_min)
        & (vertices[:, 0] < x_max)
        & (vertices[:, 1] > y_min)
        & (vertices[:, 1] < y_max)
    ]


def test_lightbox_body_is_a_valid_hollow_shell(tmp_path):
    image_path = make_uniform_image(tmp_path / "photo.png", value=128, width=30, height=30)
    result = build_lightbox_from_shape_mask(
        np.ones((30, 30), dtype=bool),
        _face_params(),
        LightBoxParameters(depth_mm=25.0, wall_thickness_mm=6.0, include_back_panel=False),
        image_path=image_path,
    )

    validation = validate_mesh(result.body_mesh)

    assert validation.is_valid
    assert _xy_vertices_inside(result.body_mesh, 24.0, 36.0, 24.0, 36.0).size == 0
    assert result.back_panel_mesh is None


def test_lightbox_preserves_internal_letter_holes(tmp_path):
    image_path = make_uniform_image(tmp_path / "photo.png", value=128, width=30, height=30)
    result = build_lightbox_from_shape_mask(
        _ring_mask(),
        _face_params(),
        LightBoxParameters(depth_mm=30.0, wall_thickness_mm=4.0),
        image_path=image_path,
    )

    assert validate_mesh(result.body_mesh).is_valid
    assert validate_mesh(result.face_mesh).is_valid
    assert validate_mesh(result.back_panel_mesh).is_valid
    assert _xy_vertices_inside(result.body_mesh, 24.0, 36.0, 24.0, 36.0).size == 0
    assert _xy_vertices_inside(result.face_mesh, 24.0, 36.0, 24.0, 36.0).size == 0
    assert _xy_vertices_inside(result.back_panel_mesh, 24.0, 36.0, 24.0, 36.0).size == 0


def test_lithophane_face_is_placed_on_front_of_box(tmp_path):
    image_path = make_uniform_image(tmp_path / "photo.png", value=255, width=30, height=30)
    face_params = _face_params()
    box_params = LightBoxParameters(depth_mm=28.0, wall_thickness_mm=5.0)

    result = build_lightbox_from_shape_mask(
        np.ones((30, 30), dtype=bool), face_params, box_params, image_path=image_path
    )

    assert result.face_mesh.bounds[0][2] == pytest.approx(box_params.depth_mm, abs=1e-6)
    assert result.face_mesh.bounds[1][2] == pytest.approx(
        box_params.depth_mm + face_params.min_thickness_mm, abs=1e-3
    )
    assert result.body_mesh.bounds[1][2] == pytest.approx(box_params.depth_mm, abs=1e-6)


def test_open_face_mode_does_not_require_an_image():
    result = build_lightbox_from_shape_mask(
        np.ones((30, 30), dtype=bool),
        _face_params(),
        LightBoxParameters(face_mode=LightBoxFaceMode.OPEN, include_back_panel=False),
    )

    assert validate_mesh(result.body_mesh).is_valid
    assert result.face_mesh is None


def test_lithophane_face_requires_an_image():
    with pytest.raises(ValueError, match="image source"):
        build_lightbox_from_shape_mask(
            np.ones((30, 30), dtype=bool),
            _face_params(),
            LightBoxParameters(face_mode=LightBoxFaceMode.LITHOPHANE),
        )
