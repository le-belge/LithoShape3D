"""Tests d'integration SAM2 CoreML REELS -- separes et optionnels.

Ne s'executent QUE si le modele est deja present dans le cache utilisateur
(jamais de telechargement automatique pendant les tests, jamais en CI par
defaut). `pytest tests/` (suite standard) les saute silencieusement si le
modele est absent ou si coremltools n'est pas installe.
"""

import numpy as np
import pytest

from lithoshape3d.ai.segmentation.base import SegmentationPrompt
from lithoshape3d.ai.segmentation.sam2_coreml_backend import Sam2CoreMLBackend

backend = Sam2CoreMLBackend()
pytestmark = pytest.mark.skipif(
    not backend.is_available(), reason="modele SAM2 CoreML non telecharge ou coremltools absent"
)


def _synthetic_image(rows=400, cols=400):
    image = np.zeros((rows, cols, 3), dtype=np.uint8)
    yy, xx = np.mgrid[0:rows, 0:cols]
    cy, cx, r = rows // 2, cols // 2, min(rows, cols) // 4
    image[(yy - cy) ** 2 + (xx - cx) ** 2 <= r * r] = 220
    return image, (cy, cx, r)


def test_positive_point_segments_expected_region():
    image, (cy, cx, r) = _synthetic_image()
    session = backend.prepare_image(image)

    mask = session.segment(SegmentationPrompt(positive_points=[(cx, cy)]))

    assert mask.shape == image.shape[:2]
    assert mask.dtype == np.float32
    yy, xx = np.mgrid[0 : image.shape[0], 0 : image.shape[1]]
    expected = (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r
    predicted = mask > 0.5
    iou = (predicted & expected).sum() / (predicted | expected).sum()
    assert iou > 0.9


def test_session_reuses_encoding_across_multiple_prompts():
    image, (cy, cx, _radius) = _synthetic_image()
    session = backend.prepare_image(image)

    mask_a = session.segment(SegmentationPrompt(positive_points=[(cx, cy)]))
    mask_b = session.segment(SegmentationPrompt(positive_points=[(5, 5)]))

    assert mask_a.sum() != mask_b.sum()  # deux prompts differents -> resultats differents


def test_empty_prompt_returns_empty_mask():
    image, _ = _synthetic_image()
    session = backend.prepare_image(image)

    mask = session.segment(SegmentationPrompt())

    assert np.all(mask == 0.0)


def test_mask_resolution_matches_non_square_source_image():
    image, _ = _synthetic_image(rows=300, cols=500)
    session = backend.prepare_image(image)

    mask = session.segment(SegmentationPrompt(positive_points=[(250, 150)]))

    assert mask.shape == (300, 500)
