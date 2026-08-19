import numpy as np
import pytest

from lithoshape3d.ui.overlay import render_overlay, zone_color


def test_overlay_output_matches_image_size(qapp):
    image = np.full((10, 20), 0.5, dtype=np.float32)
    mask = np.zeros((10, 20), dtype=np.float32)

    pixmap = render_overlay(image, mask, zone_color(0))

    assert pixmap.width() == 20
    assert pixmap.height() == 10


def test_overlay_never_mutates_source_image(qapp):
    image = np.full((8, 8), 0.3, dtype=np.float32)
    mask = np.ones((8, 8), dtype=np.float32)
    image_before = image.copy()
    mask_before = mask.copy()

    render_overlay(image, mask, zone_color(1), alpha=0.6)

    assert np.array_equal(image, image_before)
    assert np.array_equal(mask, mask_before)


def test_overlay_rejects_mismatched_shapes(qapp):
    image = np.zeros((10, 10), dtype=np.float32)
    mask = np.zeros((5, 5), dtype=np.float32)

    with pytest.raises(ValueError):
        render_overlay(image, mask, zone_color(0))


def test_zone_color_cycles_through_palette():
    from lithoshape3d.ui.overlay import ZONE_COLOR_PALETTE

    assert zone_color(0) == ZONE_COLOR_PALETTE[0]
    assert zone_color(len(ZONE_COLOR_PALETTE)) == ZONE_COLOR_PALETTE[0]
    assert zone_color(1) != zone_color(0)
