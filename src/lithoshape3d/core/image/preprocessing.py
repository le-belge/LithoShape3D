"""Pretraitement d'image : niveaux de gris, redimensionnement, contraste/luminosite.

Chaque fonction est une etape pure (entree -> sortie), sans notion de
geometrie. La sortie finale attendue par la couche geometry est un tableau
numpy float32 de forme (rows, cols) avec des valeurs dans [0.0, 1.0]
(0.0 = noir, 1.0 = blanc).
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image


def to_grayscale_array(image: Image.Image) -> np.ndarray:
    """Conversion en niveaux de gris ponderee par la luminance (via Pillow)."""
    gray = image.convert("L")
    return np.asarray(gray, dtype=np.float32) / 255.0


def resize_array(array: np.ndarray, width_px: int, height_px: int) -> np.ndarray:
    """Redimensionne un tableau (rows, cols) vers (height_px, width_px)."""
    is_downscale = width_px * height_px < array.size
    interpolation = cv2.INTER_AREA if is_downscale else cv2.INTER_LINEAR
    resized = cv2.resize(array, (width_px, height_px), interpolation=interpolation)
    return resized.astype(np.float32)


def apply_brightness_contrast(
    array: np.ndarray, brightness: float = 0.0, contrast: float = 1.0
) -> np.ndarray:
    """brightness : decalage additif. contrast : facteur multiplicatif autour de 0.5."""
    return (array - 0.5) * contrast + 0.5 + brightness


def normalize(array: np.ndarray) -> np.ndarray:
    """Ramene les valeurs dans [0.0, 1.0]."""
    return np.clip(array, 0.0, 1.0).astype(np.float32)
