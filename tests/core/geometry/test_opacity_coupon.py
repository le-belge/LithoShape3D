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


def test_opacity_coupon_thickness_labels_sit_in_the_bottom_label_band():
    """Regression : `_draw_labels` combinait un masque Pillow indexe Y-DOWN
    (ligne 0 = haut) avec `front_z` indexe Y-UP (ligne 0 = y=0mm, bas) sans
    retourner le masque -- les labels d'epaisseur (destines a la bande
    dediee pres de y=0) se retrouvaient inverses, empietant sur la zone de
    mesure optique elle-meme au lieu de rester dans leur bande. Verifie que
    les sommets en relief lies aux labels d'epaisseur (pas au tag de
    version, qui lui doit rester en haut) restent dans la bande basse
    dediee (`margin_mm` a `measurement_y_min_mm`)."""
    params = OpacityCouponParameters(labels=True, label_relief_mm=0.2)
    mesh = build_opacity_coupon_mesh(params)

    raised = mesh.vertices[mesh.vertices[:, 2] > params.max_coupon_thickness_mm + 0.05]
    assert raised.size > 0, "Aucun sommet en relief -- les labels n'ont pas ete dessines."

    # Les labels d'epaisseur sont sous le tag de version : on les isole en
    # se limitant a la moitie basse du coupon.
    thickness_label_verts = raised[raised[:, 1] < params.height_mm / 2.0]
    assert thickness_label_verts.size > 0
    assert thickness_label_verts[:, 1].max() <= params.measurement_y_min_mm + 0.5, (
        "Un label d'epaisseur deborde dans la zone de mesure optique -- regression du bug "
        "d'inversion verticale."
    )
    assert thickness_label_verts[:, 1].min() >= params.margin_mm - 0.5
