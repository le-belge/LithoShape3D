"""ShapeMask (v0.4 Shape Composer) : silhouette physique de l'objet compose,
independante des ZoneMask (voir docstring de core/geometry/shape.py)."""

import numpy as np
import pytest

from lithoshape3d.core.geometry.shape import (
    apply_border,
    build_shape_mask,
    build_shape_mask_from_image_array,
    count_connected_components,
)
from lithoshape3d.core.scene.models import ShapeParams, ShapeType

ROWS, COLS = 200, 160


def test_rectangle_fills_the_whole_grid():
    mask = build_shape_mask(ShapeParams(shape_type=ShapeType.RECTANGLE), ROWS, COLS)

    assert mask.shape == (ROWS, COLS)
    assert mask.all()


@pytest.mark.parametrize("shape_type", [ShapeType.CIRCLE, ShapeType.OVAL, ShapeType.HEART, ShapeType.STAR])
def test_builtin_shapes_are_a_single_connected_component_and_partial_coverage(shape_type):
    mask = build_shape_mask(ShapeParams(shape_type=shape_type), ROWS, COLS)

    assert mask.shape == (ROWS, COLS)
    assert count_connected_components(mask) == 1
    assert 0.0 < mask.mean() < 1.0  # ni vide, ni plein cadre


def test_circle_is_centered_and_bounded_by_the_smaller_dimension():
    mask = build_shape_mask(ShapeParams(shape_type=ShapeType.CIRCLE), ROWS, COLS)

    cy, cx = ROWS // 2, COLS // 2
    assert mask[cy, cx]  # centre toujours dans le cercle
    assert not mask[0, 0]  # coin toujours hors du cercle


def test_star_has_five_reflex_points_fewer_pixels_than_a_circle():
    star = build_shape_mask(ShapeParams(shape_type=ShapeType.STAR), ROWS, COLS)
    circle = build_shape_mask(ShapeParams(shape_type=ShapeType.CIRCLE), ROWS, COLS)

    assert star.sum() < circle.sum()


def test_text_shape_renders_nonempty_mask_for_a_letter():
    mask = build_shape_mask(ShapeParams(shape_type=ShapeType.TEXT, text="M"), ROWS, COLS)

    assert mask.any()
    assert count_connected_components(mask) == 1


def test_text_shape_preserves_holes_in_letters_like_o():
    mask = build_shape_mask(ShapeParams(shape_type=ShapeType.TEXT, text="O", bold=True), 200, 200)

    center = mask[95:105, 95:105]
    assert not center.any()  # le trou du O doit rester vide
    assert mask.any()  # mais la lettre elle-meme est bien dessinee


def test_text_shape_with_multiple_letters_has_multiple_components():
    """Chaque lettre disjointe est sa propre composante -- jamais de pont
    invente automatiquement (cf. 2.6)."""
    mask = build_shape_mask(ShapeParams(shape_type=ShapeType.TEXT, text="LOVE"), 100, 300)

    assert count_connected_components(mask) == 4


def test_text_shape_empty_string_produces_empty_mask():
    mask = build_shape_mask(ShapeParams(shape_type=ShapeType.TEXT, text=""), ROWS, COLS)

    assert not mask.any()


def test_build_shape_mask_rejects_image_and_svg_without_prior_loading():
    with pytest.raises(ValueError):
        build_shape_mask(ShapeParams(shape_type=ShapeType.IMAGE, source_image_path="x.png"), ROWS, COLS)


def test_build_shape_mask_from_image_array_uses_white_as_interior():
    alpha = np.zeros((50, 50), dtype=np.float32)
    alpha[10:40, 10:40] = 1.0  # carre blanc/opaque = interieur

    mask = build_shape_mask_from_image_array(alpha, ROWS, COLS)

    assert mask.shape == (ROWS, COLS)
    assert mask.any()
    assert not mask.all()


def test_apply_border_grows_the_silhouette():
    mask = build_shape_mask(ShapeParams(shape_type=ShapeType.CIRCLE), ROWS, COLS)

    bordered = apply_border(mask, border_width_px=6)

    assert bordered.sum() > mask.sum()
    assert (mask & bordered == mask).all()  # la silhouette d'origine reste incluse


def test_apply_border_zero_width_is_a_no_op():
    mask = build_shape_mask(ShapeParams(shape_type=ShapeType.CIRCLE), ROWS, COLS)

    assert apply_border(mask, 0.0) is mask


def test_count_connected_components_counts_disjoint_islands():
    mask = np.zeros((50, 50), dtype=bool)
    mask[5:10, 5:10] = True
    mask[30:35, 30:35] = True
    mask[30:35, 5:10] = True

    assert count_connected_components(mask) == 3
