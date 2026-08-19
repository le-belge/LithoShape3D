"""Source de verite unique pour la conversion luminosite -> epaisseur.

Convention lithophanie classique (retro-eclairee), invert=False :
    pixel sombre (v -> 0.0) => epaisseur max (bloque la lumiere)
    pixel clair  (v -> 1.0) => epaisseur min (laisse passer la lumiere)
invert=True inverse cette relation.

    thickness = min_thickness + (max_thickness - min_thickness) * relief_fraction
    relief_fraction = (1 - v) si invert=False, sinon v

Cette formule ne doit exister nulle part ailleurs dans le code.
"""

from __future__ import annotations

import numpy as np

from lithoshape3d.core.scene.models import GeometryParameters


def compute_thickness_mm(values: np.ndarray, params: GeometryParameters) -> np.ndarray:
    if params.max_thickness_mm <= params.min_thickness_mm:
        raise ValueError("max_thickness_mm doit etre strictement superieur a min_thickness_mm")
    if params.min_thickness_mm <= 0:
        raise ValueError("min_thickness_mm doit etre > 0")

    relief_fraction = values if params.invert else (1.0 - values)
    relief_range = params.max_thickness_mm - params.min_thickness_mm
    thickness = params.min_thickness_mm + relief_range * relief_fraction
    return thickness.astype(np.float32)
