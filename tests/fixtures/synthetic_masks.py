"""Masques synthetiques pour tester la geometrie masquee sans dependre de
photos reelles ni de segmentation. Toutes les fonctions retournent un
tableau bool (rows, cols) - True = actif."""

from __future__ import annotations

import numpy as np


def full_mask(rows: int, cols: int) -> np.ndarray:
    return np.ones((rows, cols), dtype=bool)


def half_mask(rows: int, cols: int) -> np.ndarray:
    """Moitie droite active."""
    mask = np.zeros((rows, cols), dtype=bool)
    mask[:, cols // 2 :] = True
    return mask


def circle_mask(rows: int, cols: int, radius_fraction: float = 1 / 3) -> np.ndarray:
    yy, xx = np.mgrid[0:rows, 0:cols]
    cy, cx = rows / 2, cols / 2
    radius = min(rows, cols) * radius_fraction
    return ((yy - cy) ** 2 + (xx - cx) ** 2) <= radius**2


def ring_mask(rows: int, cols: int) -> np.ndarray:
    """Anneau : contour exterieur + trou interne reel."""
    yy, xx = np.mgrid[0:rows, 0:cols]
    cy, cx = rows / 2, cols / 2
    r_outer = min(rows, cols) / 2.5
    r_inner = r_outer / 2.2
    dist2 = (yy - cy) ** 2 + (xx - cx) ** 2
    return (dist2 <= r_outer**2) & (dist2 >= r_inner**2)


def l_shape_mask(rows: int, cols: int) -> np.ndarray:
    """Forme concave en L."""
    mask = np.zeros((rows, cols), dtype=bool)
    r1, r2 = rows // 8, rows - rows // 8
    c1, c2 = cols // 12, cols // 2
    mask[r1:r2, c1:c2] = True
    mask[r2 - rows // 4 : r2, c1 : cols - cols // 12] = True
    return mask


def concave_star_mask(rows: int, cols: int) -> np.ndarray:
    """Forme concave non triviale (etoile a 5 branches, via seuillage
    angulaire d'un rayon module)."""
    yy, xx = np.mgrid[0:rows, 0:cols]
    cy, cx = rows / 2, cols / 2
    dy, dx = yy - cy, xx - cx
    angle = np.arctan2(dy, dx)
    dist = np.sqrt(dy**2 + dx**2)
    max_r = min(rows, cols) / 2.2
    star_radius = max_r * (0.5 + 0.5 * np.cos(5 * angle))
    return dist <= star_radius


def two_islands_mask(rows: int, cols: int) -> np.ndarray:
    """Deux composantes disjointes."""
    mask = np.zeros((rows, cols), dtype=bool)
    mask[rows // 8 : rows // 3, cols // 8 : cols // 3] = True
    mask[2 * rows // 3 : rows - rows // 8, 2 * cols // 3 : cols - cols // 8] = True
    return mask


def tiny_invalid_mask(rows: int, cols: int) -> np.ndarray:
    """Un seul pixel actif : aucune cellule de grille n'est entierement
    active (il en faut au moins 2x2 pixels actifs adjacents)."""
    mask = np.zeros((rows, cols), dtype=bool)
    mask[rows // 2, cols // 2] = True
    return mask
