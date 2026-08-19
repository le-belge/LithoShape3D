import numpy as np
import pytest

from lithoshape3d.core.scene.mask_io import (
    load_mask_array,
    load_zone_mask,
    save_mask_array,
    save_zone_mask,
)
from lithoshape3d.core.scene.models import Zone


def test_roundtrip_preserves_shape(tmp_path):
    mask = np.random.default_rng(0).random((40, 60)).astype(np.float32)
    path = tmp_path / "mask.png"

    save_mask_array(path, mask)
    reloaded = load_mask_array(path)

    assert reloaded.shape == mask.shape


def test_roundtrip_stays_within_bounds(tmp_path):
    mask = np.random.default_rng(1).random((20, 20)).astype(np.float32)
    path = tmp_path / "mask.png"

    save_mask_array(path, mask)
    reloaded = load_mask_array(path)

    assert reloaded.min() >= 0.0
    assert reloaded.max() <= 1.0


def test_roundtrip_tolerance_due_to_8bit_quantization(tmp_path):
    mask = np.random.default_rng(2).random((30, 30)).astype(np.float32)
    path = tmp_path / "mask.png"

    save_mask_array(path, mask)
    reloaded = load_mask_array(path)

    # quantification 8 bits -> pas de 1/255 ~= 0.0039 ; on tolere une marge
    assert np.abs(reloaded - mask).max() <= (1.0 / 255.0) + 1e-6


def test_roundtrip_exact_for_pure_binary_mask(tmp_path):
    mask = np.zeros((10, 10), dtype=np.float32)
    mask[2:5, 3:8] = 1.0
    path = tmp_path / "mask.png"

    save_mask_array(path, mask)
    reloaded = load_mask_array(path)

    assert np.array_equal(reloaded, mask)


def test_load_zone_mask_with_no_path_is_fully_active():
    zone = Zone(mask_path=None)

    mask = load_zone_mask("/unused", zone, shape=(8, 12))

    assert mask.shape == (8, 12)
    assert np.all(mask == 1.0)


def test_load_zone_mask_resizes_to_requested_shape(tmp_path):
    stored = np.zeros((10, 10), dtype=np.float32)
    stored[:, 5:] = 1.0
    save_mask_array(tmp_path / "masks" / "zone-x.png", stored)
    zone = Zone(id="zone-x", mask_path="masks/zone-x.png")

    mask = load_zone_mask(tmp_path, zone, shape=(20, 40))

    assert mask.shape == (20, 40)


def test_save_zone_mask_returns_relative_path(tmp_path):
    mask = np.ones((5, 5), dtype=np.float32)

    relative = save_zone_mask(tmp_path, "abc-123", mask)

    assert relative == "masks/abc-123.png"
    assert (tmp_path / relative).exists()


@pytest.mark.parametrize("shape", [(1, 1), (3, 7)])
def test_roundtrip_various_shapes(tmp_path, shape):
    mask = np.random.default_rng(3).random(shape).astype(np.float32)
    path = tmp_path / "mask.png"

    save_mask_array(path, mask)
    reloaded = load_mask_array(path)

    assert reloaded.shape == shape
