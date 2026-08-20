"""Composition sequentielle de plusieurs Zones en un unique volume ferme.

Pipeline (Strategie A/hybride validee en conception) :
    Scene + image + zones + masques
    -> contribution de chaque zone (core/geometry/relief.py)
    -> composition sequentielle du champ de hauteur (NumPy pur, ci-dessous)
    -> masque d'occupation final
    -> UN SEUL appel a build_mesh_from_heightfield (reutilise Phase 1A/2B)
    -> validation (core/validation, inchange)

Aucune union manifold3d n'est utilisee pour composer les zones entre elles :
manifold3d reste reserve a la validation finale et aux futurs volumes 3D non
representables par un champ de hauteur unique.

Grille canonique : les dimensions/resolution utilisees pour la composition
sont celles de la premiere zone visible en CompositionMode.BASE (fondation).
Le `width_mm`/`height_mm`/`resolution` des autres zones n'est pas utilise en
composition (uniquement pertinent pour une generation mono-zone autonome) ;
seuls leur ReliefMode, GeometryParameters.min/max_thickness_mm et masque
comptent.

Plateau commun : le dos reste toujours a Z=0 pour l'ensemble du resultat
compose (comme en mono-zone). Une contribution ADD ou une zone sans
fondation dessous ne peut donc jamais "flotter" : elle repose necessairement
sur ce meme plateau -- au pire elle forme une composante connexe
supplementaire (deja accepte depuis la Phase 2B), jamais un volume detache
dans l'espace.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh

from lithoshape3d.core.geometry.heightmap import grid_dimensions
from lithoshape3d.core.geometry.mesh_builder import (
    DEFAULT_MASK_THRESHOLD,
    build_mesh_from_heightfield,
)
from lithoshape3d.core.geometry.relief import compute_zone_contribution_mm
from lithoshape3d.core.image.pipeline import preprocess_image
from lithoshape3d.core.image.preprocessing import resize_array
from lithoshape3d.core.scene.models import CompositionMode, Zone


@dataclass
class ZoneSource:
    """Entrees necessaires pour composer une Zone : image deja resolue
    (chemin absolu utilisable directement) et masque deja en memoire.
    `mask=None` signifie masque entierement actif (comportement historique)."""

    zone: Zone
    image_path: str
    mask: np.ndarray | None = None
    brightness: float = 0.0
    contrast: float = 1.0


def _find_base_zone(zone_sources: list[ZoneSource]) -> ZoneSource:
    for source in zone_sources:
        if source.zone.visible and source.zone.composition_mode == CompositionMode.BASE:
            return source
    raise ValueError(
        "Composition impossible : aucune zone BASE visible dans la Scene "
        "(une zone de fondation est necessaire pour definir la grille et le point de depart)."
    )


def compose_scene_heightfield(
    zone_sources: list[ZoneSource],
    mask_threshold: float = DEFAULT_MASK_THRESHOLD,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Compose sequentiellement les zones (dans l'ordre de la liste, qui doit
    deja refleter Scene.zones) en un champ de hauteur unique.

    Retourne (z_final_mm, active_final, width_mm, height_mm), tous deja
    orientes Y-up (haut de l'image -> Y max), prets pour
    `build_mesh_from_heightfield`.
    """
    if not zone_sources:
        raise ValueError("Aucune zone a composer.")

    base_source = _find_base_zone(zone_sources)
    canonical_params = base_source.zone.geometry_params
    rows, cols = grid_dimensions(canonical_params)

    z_final = np.zeros((rows, cols), dtype=np.float32)
    active_final = np.zeros((rows, cols), dtype=bool)

    for source in zone_sources:
        zone = source.zone
        if not zone.visible:
            continue

        processed = preprocess_image(
            source.image_path,
            width_px=cols,
            height_px=rows,
            brightness=source.brightness,
            contrast=source.contrast,
        )
        processed = np.flipud(processed)

        mask = source.mask
        if mask is None:
            mask = np.ones((rows, cols), dtype=np.float32)
        elif mask.shape != (rows, cols):
            mask = resize_array(mask, width_px=cols, height_px=rows)
        mask = np.flipud(mask)

        active = mask >= mask_threshold
        contribution = compute_zone_contribution_mm(processed, zone.geometry_params, zone.relief_mode)

        if zone.composition_mode in (CompositionMode.BASE, CompositionMode.REPLACE):
            z_final[active] = contribution[active]
        elif zone.composition_mode == CompositionMode.ADD:
            z_final[active] += contribution[active]
        else:
            raise NotImplementedError(f"CompositionMode {zone.composition_mode} non supporte")

        active_final |= active

    if not active_final.any():
        raise ValueError("Composition insuffisante : aucune cellule active dans le resultat final.")

    return z_final, active_final, canonical_params.width_mm, canonical_params.height_mm


def compose_scene_mesh(
    zone_sources: list[ZoneSource],
    mask_threshold: float = DEFAULT_MASK_THRESHOLD,
) -> trimesh.Trimesh:
    """Pipeline complet : zones -> champ de hauteur compose -> mesh unique ferme."""
    z_final, active_final, width_mm, height_mm = compose_scene_heightfield(zone_sources, mask_threshold)
    return build_mesh_from_heightfield(z_final, active_final, width_mm, height_mm)
