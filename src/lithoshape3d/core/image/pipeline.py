"""Orchestration du pretraitement image : image source -> image traitee.

Ne produit aucune geometrie (pas de notion d'epaisseur/mesh ici) : c'est la
limite stricte entre `core/image` et `core/geometry`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from lithoshape3d.core.image.io import load_image
from lithoshape3d.core.image.preprocessing import (
    apply_brightness_contrast,
    normalize,
    resize_array,
    to_grayscale_array,
)


def preprocess_image(
    path: str | Path,
    width_px: int,
    height_px: int,
    brightness: float = 0.0,
    contrast: float = 1.0,
) -> np.ndarray:
    image = load_image(path)
    array = to_grayscale_array(image)
    array = resize_array(array, width_px=width_px, height_px=height_px)
    array = apply_brightness_contrast(array, brightness=brightness, contrast=contrast)
    return normalize(array)


def image_size(path: str | Path) -> tuple[int, int]:
    """(largeur_px, hauteur_px) de l'image source."""
    with load_image(path) as image:
        return image.size
