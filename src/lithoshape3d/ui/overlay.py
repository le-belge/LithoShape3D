"""Overlay masque au-dessus de l'image source, pour affichage uniquement.

`render_overlay` ne modifie jamais `image_gray` ni `mask` : toute operation
produit un nouveau tableau. L'image source affichee par ailleurs (aperçu,
export) reste donc intacte quel que soit l'etat des masques.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage, QPixmap

# Palette sobre, coherente avec le theme anthracite (pas de RGB gaming).
ZONE_COLOR_PALETTE: list[tuple[int, int, int]] = [
    (79, 163, 199),  # bleu (accent theme)
    (217, 164, 65),  # ambre
    (149, 128, 194),  # violet sourd
    (196, 120, 128),  # rose sourd
    (120, 176, 137),  # vert sourd
    (191, 191, 120),  # olive clair
]


def zone_color(index: int) -> tuple[int, int, int]:
    return ZONE_COLOR_PALETTE[index % len(ZONE_COLOR_PALETTE)]


def render_overlay(
    image_gray: np.ndarray,
    mask: np.ndarray,
    color: tuple[int, int, int],
    alpha: float = 0.45,
) -> QPixmap:
    """image_gray, mask : float32 [0,1], meme forme (rows, cols).

    Compose `color` par-dessus l'image avec une opacite `alpha * mask` :
    zone incluse (mask=1) -> overlay pleinement visible, zone exclue
    (mask=0) -> image inchangee. Aucune ecriture en place sur les entrees.
    """
    if image_gray.shape != mask.shape:
        raise ValueError("image_gray et mask doivent avoir la meme forme")

    base = np.clip(image_gray, 0.0, 1.0) * 255.0
    rgb = np.stack([base, base, base], axis=-1)

    color_arr = np.array(color, dtype=np.float32)
    blend = alpha * np.clip(mask, 0.0, 1.0)[..., None]
    composited = rgb * (1.0 - blend) + color_arr * blend

    composited_u8 = np.ascontiguousarray(np.clip(composited, 0, 255).astype(np.uint8))
    height, width, _ = composited_u8.shape
    qimage = QImage(composited_u8.data, width, height, width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimage.copy())
