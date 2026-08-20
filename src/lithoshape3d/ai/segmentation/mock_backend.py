"""Backend deterministe, zero dependance : utilise par la suite de tests
standard (jamais de telechargement de modele en CI) et comme filet de repli
conceptuel pour valider le cablage UI independamment du vrai moteur IA.
"""

from __future__ import annotations

import numpy as np

from lithoshape3d.ai.segmentation.base import (
    SegmentationBackend,
    SegmentationPrompt,
    SegmentationSession,
)

_POINT_RADIUS_PX = 40


class MockSegmentationSession(SegmentationSession):
    def __init__(self, shape: tuple[int, int]) -> None:
        self._shape = shape

    def segment(self, prompt: SegmentationPrompt) -> np.ndarray:
        rows, cols = self._shape
        mask = np.zeros(self._shape, dtype=np.float32)
        if prompt.is_empty():
            return mask

        yy, xx = np.mgrid[0:rows, 0:cols]

        if prompt.box is not None:
            x0, y0, x1, y1 = prompt.box
            mask[(yy >= y0) & (yy <= y1) & (xx >= x0) & (xx <= x1)] = 1.0

        for x, y in prompt.positive_points:
            mask[(yy - y) ** 2 + (xx - x) ** 2 <= _POINT_RADIUS_PX**2] = 1.0
        for x, y in prompt.negative_points:
            mask[(yy - y) ** 2 + (xx - x) ** 2 <= _POINT_RADIUS_PX**2] = 0.0

        return mask


class MockSegmentationBackend(SegmentationBackend):
    name = "mock"

    def is_available(self) -> bool:
        return True

    def prepare_image(self, image: np.ndarray) -> MockSegmentationSession:
        return MockSegmentationSession(image.shape[:2])
