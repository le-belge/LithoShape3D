"""Heightmap : etape intermediaire explicite entre l'image traitee et le mesh.

Chaine voulue :
    processed_image -> heightmap
    heightmap + mask + GeometryParameters -> mesh   (voir mesh_builder.py)

Jamais d'API directe image -> mesh.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from lithoshape3d.core.image.pipeline import preprocess_image
from lithoshape3d.core.scene.models import GeometryParameters


@dataclass(frozen=True)
class Heightmap:
    """values : float32, forme (rows, cols), valeurs dans [0.0, 1.0] (0.0=noir, 1.0=blanc)."""

    values: np.ndarray

    def __post_init__(self) -> None:
        if self.values.ndim != 2:
            raise ValueError(f"Heightmap attend un tableau 2D, recu shape={self.values.shape}")
        if self.values.size and (self.values.min() < 0.0 or self.values.max() > 1.0):
            raise ValueError("Heightmap.values doit etre dans [0.0, 1.0]")

    @property
    def shape(self) -> tuple[int, int]:
        return self.values.shape


def grid_dimensions(params: GeometryParameters) -> tuple[int, int]:
    """(rows, cols) de la grille d'echantillonnage, derives de `resolution` (mm/pixel)."""
    if params.resolution <= 0:
        raise ValueError("GeometryParameters.resolution doit etre > 0")
    cols = max(2, round(params.width_mm / params.resolution))
    rows = max(2, round(params.height_mm / params.resolution))
    return rows, cols


def build_heightmap(processed_image: np.ndarray) -> Heightmap:
    return Heightmap(values=processed_image.astype(np.float32))


def heightmap_from_image_path(
    path: str | Path,
    params: GeometryParameters,
    brightness: float = 0.0,
    contrast: float = 1.0,
) -> Heightmap:
    rows, cols = grid_dimensions(params)
    processed = preprocess_image(
        path, width_px=cols, height_px=rows, brightness=brightness, contrast=contrast
    )
    return build_heightmap(processed)


def height_mm_from_aspect_ratio(
    width_mm: float, image_width_px: int, image_height_px: int
) -> float:
    if image_width_px <= 0:
        raise ValueError("image_width_px doit etre > 0")
    return width_mm * (image_height_px / image_width_px)
