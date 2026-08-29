import pytest

from lithoshape3d.core.geometry.opacity_coupon import (
    DEFAULT_LITHOLAB_OPACITY_THICKNESSES_MM,
    OpacityCouponParameters,
    build_opacity_coupon_mesh,
)
from lithoshape3d.core.validation.mesh_checks import validate_mesh


def test_opacity_coupon_default_mesh_is_valid():
    mesh = build_opacity_coupon_mesh(OpacityCouponParameters(labels=False))
    validation = validate_mesh(mesh)

    assert validation.is_valid
    assert mesh.bounds[0][0] == pytest.approx(0.0)
    assert mesh.bounds[0][1] == pytest.approx(0.0)
    assert mesh.bounds[0][2] == pytest.approx(0.0)
    assert mesh.bounds[1][0] == pytest.approx(100.0)
    assert mesh.bounds[1][1] == pytest.approx(30.0)
    assert mesh.bounds[1][2] == pytest.approx(max(DEFAULT_LITHOLAB_OPACITY_THICKNESSES_MM))


def test_opacity_coupon_contains_default_patch_thicknesses():
    params = OpacityCouponParameters(labels=False)
    mesh = build_opacity_coupon_mesh(params)
    vertices = mesh.vertices

    for x_min, x_max, thickness in params.patch_spans():
        x_center = (x_min + x_max) / 2.0
        patch_vertices = vertices[
            (vertices[:, 0] > x_center - 0.4)
            & (vertices[:, 0] < x_center + 0.4)
            & (vertices[:, 1] > params.measurement_y_min_mm + 2.0)
            & (vertices[:, 1] < params.measurement_y_max_mm - 2.0)
            & (vertices[:, 2] > 0.0)
        ]
        assert patch_vertices.size > 0
        assert patch_vertices[:, 2].min() == pytest.approx(thickness, abs=0.01)


def test_opacity_coupon_labels_add_small_relief():
    params = OpacityCouponParameters(labels=True, label_relief_mm=0.2)
    mesh = build_opacity_coupon_mesh(params)

    assert validate_mesh(mesh).is_valid
    assert mesh.bounds[1][2] == pytest.approx(params.max_coupon_thickness_mm + 0.2)


def test_opacity_coupon_rejects_invalid_thicknesses():
    with pytest.raises(ValueError, match="au moins deux"):
        build_opacity_coupon_mesh(OpacityCouponParameters(thicknesses_mm=(1.0,)))
