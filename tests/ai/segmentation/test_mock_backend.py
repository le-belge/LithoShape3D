"""Tests standard : backend mock uniquement, zero telechargement, zero
dependance IA. Les tests SAM2 reels vivent dans test_sam2_coreml_backend.py
et sont marques/optionnels (voir ce fichier)."""

import numpy as np

from lithoshape3d.ai.segmentation import (
    MockSegmentationBackend,
    SegmentationPrompt,
)


def test_backend_is_always_available():
    assert MockSegmentationBackend().is_available() is True


def test_empty_prompt_returns_empty_mask():
    backend = MockSegmentationBackend()
    session = backend.prepare_image(np.zeros((50, 60), dtype=np.float32))

    mask = session.segment(SegmentationPrompt())

    assert mask.shape == (50, 60)
    assert mask.dtype == np.float32
    assert np.all(mask == 0.0)


def test_positive_point_activates_a_region():
    backend = MockSegmentationBackend()
    session = backend.prepare_image(np.zeros((200, 200), dtype=np.float32))

    mask = session.segment(SegmentationPrompt(positive_points=[(100, 100)]))

    assert mask[100, 100] == 1.0
    assert mask.sum() > 0


def test_negative_point_removes_from_positive_region():
    backend = MockSegmentationBackend()
    session = backend.prepare_image(np.zeros((200, 200), dtype=np.float32))

    mask_positive_only = session.segment(SegmentationPrompt(positive_points=[(100, 100)]))
    mask_with_negative = session.segment(
        SegmentationPrompt(positive_points=[(100, 100)], negative_points=[(100, 100)])
    )

    assert mask_positive_only.sum() > mask_with_negative.sum()
    assert mask_with_negative[100, 100] == 0.0


def test_box_prompt_activates_rectangle():
    backend = MockSegmentationBackend()
    session = backend.prepare_image(np.zeros((100, 100), dtype=np.float32))

    mask = session.segment(SegmentationPrompt(box=(10, 10, 40, 40)))

    assert mask[25, 25] == 1.0
    assert mask[0, 0] == 0.0


def test_mask_matches_source_image_resolution_exactly():
    backend = MockSegmentationBackend()
    session = backend.prepare_image(np.zeros((77, 133), dtype=np.float32))

    mask = session.segment(SegmentationPrompt(positive_points=[(10, 10)]))

    assert mask.shape == (77, 133)


def test_prompt_is_empty_helper():
    assert SegmentationPrompt().is_empty()
    assert not SegmentationPrompt(positive_points=[(1, 1)]).is_empty()
    assert not SegmentationPrompt(box=(0, 0, 1, 1)).is_empty()
