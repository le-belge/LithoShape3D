"""Generateurs d'images de test synthetiques : aucune dependance a un fichier
externe ni a Internet, dimensions volontairement modestes.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def make_uniform_image(path: str | Path, value: int, width: int = 32, height: int = 32) -> Path:
    """Image entierement uniforme (0=noir, 255=blanc)."""
    path = Path(path)
    array = np.full((height, width), value, dtype=np.uint8)
    Image.fromarray(array, mode="L").save(path)
    return path


def make_gradient_image(path: str | Path, width: int = 64, height: int = 48) -> Path:
    """Degrade horizontal noir (gauche) -> blanc (droite), avec paliers intermediaires."""
    path = Path(path)
    gradient = np.linspace(0, 255, width, dtype=np.uint8)
    array = np.tile(gradient, (height, 1))
    Image.fromarray(array, mode="L").save(path)
    return path


def make_top_bright_image(path: str | Path, width: int = 32, height: int = 32) -> Path:
    """Moitie superieure blanche, moitie inferieure noire.

    Sert a detecter un flip vertical accidentel entre coordonnees image et
    coordonnees 3D (cf. mesh_builder.build_slab_mesh).
    """
    path = Path(path)
    array = np.zeros((height, width), dtype=np.uint8)
    array[: height // 2, :] = 255
    Image.fromarray(array, mode="L").save(path)
    return path
