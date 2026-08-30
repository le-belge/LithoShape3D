"""Backlight Insert (v0.4.1) : la lithophanie principale reste blanche, avec
une fine peau conservee en facade ; un insert colore independant, plat, vient
se loger derriere cette peau, dans une cavite creusee au dos du corps blanc --
sans jamais modifier la surface avant deja composee (meme garantie que
`ColorStrategy.MATERIAL_ONLY`, voir composition.py).

Reutilise l'ensemble du moteur existant plutot qu'un second moteur
geometrique parallele : `compose_scene_heightfield` pour la surface avant
partagee (inchangee), `build_mesh_from_heightfield` generalise a une face
arriere non plane pour creuser la cavite, la meme convention de masque
(espace image -> cadrage -> Y-up) que composition.py/materials.py.

Convention (identique a mesh_builder.py) : Z=0 = dos (cote source de
lumiere), Z=z_final(cellule) = face avant (cote spectateur). L'insert est
donc pose CONTRE le dos (Z=[0, insert_thickness_mm]) et la peau blanche
occupe le haut de la plage [z_final-skin, z_final] -- entre les deux, un
vide (la cavite) que l'insert vient (partiellement) combler."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh
from scipy import ndimage

from lithoshape3d.core.geometry.composition import ZoneSource, compose_scene_heightfield
from lithoshape3d.core.geometry.mesh_builder import (
    DEFAULT_MASK_THRESHOLD,
    build_mesh_from_heightfield,
)
from lithoshape3d.core.image.preprocessing import resize_array
from lithoshape3d.core.image.transform import apply_image_transform
from lithoshape3d.core.scene.models import ColorStrategy, ImageTransform

_MIN_SKIN_RESIDUAL_MM = 0.05
"""Epaisseur de peau plancher, meme si `white_skin_thickness_mm` configure
depasse l'epaisseur locale de la lithophanie a un pixel donne (zone tres
fine/claire) -- degrade proprement vers "pas de cavite a ce pixel" (peau =
epaisseur totale) plutot que de produire une geometrie negative/degeneree."""


@dataclass(frozen=True)
class BacklightComposition:
    white_mesh: trimesh.Trimesh
    """Corps blanc principal -- surface avant identique bit-a-bit a ce que
    `compose_scene_mesh` aurait produit sans aucune zone Backlight Insert."""
    insert_meshes: dict[str, trimesh.Trimesh] = field(default_factory=dict)
    """{nom_materiau: mesh} -- fusionne par nom (meme convention que
    `partition_mesh_by_material`) si plusieurs zones Backlight Insert
    partagent un materiau."""
    warnings: list[str] = field(default_factory=list)
    """Zones trop etroites pour le jeu XY configure (aucun insert genere
    pour elles) -- jamais silencieux, cf. mission 0.4.1 section 7."""

    @property
    def has_inserts(self) -> bool:
        return bool(self.insert_meshes)


def _effective_zone_active(
    source: ZoneSource,
    rows: int,
    cols: int,
    mask_threshold: float,
    image_transform: ImageTransform | None,
    shape_active: np.ndarray,
) -> np.ndarray:
    """Reproduit EXACTEMENT la regle de `compose_scene_heightfield` pour
    transformer le masque source (espace image natif) en masque actif Y-up
    a la resolution canonique -- doit rester identique, sinon la cavite/l'
    insert ne correspondraient plus a la zone reellement active en
    composition (cf. le correctif d'alignement zone/cadrage de la 0.4.0)."""
    mask = source.mask
    if mask is None:
        mask = np.ones((rows, cols), dtype=np.float32)
    elif image_transform is None:
        if mask.shape != (rows, cols):
            mask = resize_array(mask, width_px=cols, height_px=rows)
    else:
        mask = apply_image_transform(
            mask.astype(np.float32), image_transform, width_px=cols, height_px=rows, fill_value=0.0
        )
    mask = np.flipud(mask)
    return (mask >= mask_threshold) & shape_active


def _erode_by_mm(mask: np.ndarray, clearance_mm: float, pixel_size_mm: float) -> np.ndarray:
    """Retrecit le masque de `clearance_mm` (mm reels, precision sub-pixel)
    sur son contour, via une carte de distance plutot qu'une erosion
    binaire par nombre entier de pixels : a une resolution typique
    (0.15-0.5 mm/px), un `binary_erosion` avec un nombre d'iterations
    arrondi confondrait 0.10/0.20/0.30mm (tous arrondis au meme pixel
    entier) -- inacceptable, la mission exige que ces 3 presets produisent
    des geometries reellement distinctes (cf. tests, "Test D")."""
    if clearance_mm <= 0 or pixel_size_mm <= 0 or not mask.any():
        return mask
    distance_mm = ndimage.distance_transform_edt(mask) * pixel_size_mm
    return distance_mm > clearance_mm


def _soft_cavity_back_z(
    back_z: np.ndarray,
    candidate_back: np.ndarray,
    feasible: np.ndarray,
    insert_mask: np.ndarray,
    pixel_size_mm: float,
    blend_mm: float,
) -> None:
    """Creuse plein sous l'insert, puis remonte en rampe autour.

    La rampe ne touche que la face arriere (`back_z`) : surface avant et
    insert plat restent inchanges.
    """
    back_z[insert_mask] = candidate_back[insert_mask]

    if blend_mm <= 0:
        return

    distance_to_insert_mm = ndimage.distance_transform_edt(~insert_mask) * pixel_size_mm
    blend_mask = feasible & ~insert_mask & (distance_to_insert_mm <= blend_mm)
    if not blend_mask.any():
        return

    t = distance_to_insert_mm[blend_mask] / blend_mm
    soft_back = candidate_back[blend_mask] * (1.0 - t)
    back_z[blend_mask] = np.maximum(back_z[blend_mask], soft_back)


def compose_backlight_bodies(
    zone_sources: list[ZoneSource],
    mask_threshold: float = DEFAULT_MASK_THRESHOLD,
    image_transform: ImageTransform | None = None,
    shape_mask: np.ndarray | None = None,
) -> BacklightComposition:
    """Compose le corps blanc (avec cavites) et un insert independant par
    materiau, pour toutes les zones `ColorStrategy.BACKLIGHT_INSERT`
    visibles. Zero zone Backlight Insert -> `insert_meshes` vide et
    `white_mesh` identique a `compose_scene_mesh` (chemin sans effet)."""
    z_final, active_final, width_mm, height_mm = compose_scene_heightfield(
        zone_sources, mask_threshold, image_transform=image_transform, shape_mask=shape_mask
    )
    rows, cols = z_final.shape

    if shape_mask is None:
        shape_active = np.ones((rows, cols), dtype=bool)
    else:
        resized = (
            shape_mask
            if shape_mask.shape == (rows, cols)
            else resize_array(shape_mask.astype(np.float32), width_px=cols, height_px=rows) >= 0.5
        )
        shape_active = np.flipud(resized)

    pixel_size_mm = width_mm / cols
    back_z = np.zeros_like(z_final)
    insert_meshes: dict[str, trimesh.Trimesh] = {}
    warnings: list[str] = []

    for source in zone_sources:
        zone = source.zone
        if not zone.visible or zone.color_strategy is not ColorStrategy.BACKLIGHT_INSERT:
            continue

        zone_active = _effective_zone_active(source, rows, cols, mask_threshold, image_transform, shape_active)
        zone_active &= active_final
        if not zone_active.any():
            continue

        params = zone.backlight_insert
        skin = max(params.white_skin_thickness_mm, 0.0)
        insert_thickness = max(params.insert_thickness_mm, 0.0)

        # Garantie geometrique (hotfix v0.4.2) : l'insert est un pave UNIFORME
        # pose contre le dos (Z=[0, insert_thickness_mm]), independant de la
        # profondeur de cavite locale. La ou la lithophanie est localement
        # trop fine pour loger a la fois la peau demandee ET l'insert
        # (z_final < skin + insert_thickness), creuser quand meme la cavite
        # ferait deborder l'insert DANS le corps blanc solide -- collision
        # silencieuse entre les deux corps, visible en facade (trou/insert
        # traversant). On exclut ces points de la cavite ET de l'empreinte de
        # l'insert : la facade y reste pleine epaisseur (pas de coloration
        # backlight a ces points precis), jamais un trou. Toujours signale,
        # jamais silencieux (mission hotfix 0.4.2, section 9).
        required_total = skin + insert_thickness
        feasible = zone_active & (z_final >= required_total)
        infeasible = zone_active & ~feasible
        if infeasible.any():
            worst_shortfall = float((required_total - z_final[infeasible]).max())
            warnings.append(
                f"Zone '{zone.name}' : {int(infeasible.sum())} point(s) trop fins pour loger "
                f"a la fois la peau ({skin:.2f}mm) et l'insert ({insert_thickness:.2f}mm) -- "
                f"jusqu'a {worst_shortfall:.3f}mm d'epaisseur locale manquante. Aucune cavite "
                f"creusee a ces points (facade pleine epaisseur preservee, insert absent localement)."
            )
        if not feasible.any():
            continue

        insert_mask = _erode_by_mm(feasible, params.xy_clearance_mm, pixel_size_mm)
        if not insert_mask.any():
            warnings.append(
                f"Zone '{zone.name}' : trop etroite pour le jeu XY configure "
                f"({params.xy_clearance_mm:.2f} mm) -- aucun insert genere, cavite non creusee."
            )
            continue

        candidate_back = np.clip(z_final - skin, 0.0, None)
        candidate_back = np.clip(np.minimum(candidate_back, z_final - _MIN_SKIN_RESIDUAL_MM), 0.0, None)
        blend_mm = max(pixel_size_mm * 2.0, params.xy_clearance_mm)
        _soft_cavity_back_z(
            back_z,
            candidate_back,
            feasible,
            insert_mask,
            pixel_size_mm,
            blend_mm,
        )

        insert_front = np.full((rows, cols), insert_thickness, dtype=np.float32)
        insert_mesh = build_mesh_from_heightfield(insert_front, insert_mask, width_mm, height_mm)

        name = zone.material.name
        if name in insert_meshes:
            insert_meshes[name] = trimesh.util.concatenate([insert_meshes[name], insert_mesh])
        else:
            insert_meshes[name] = insert_mesh

    white_mesh = build_mesh_from_heightfield(z_final, active_final, width_mm, height_mm, back_z=back_z)
    return BacklightComposition(white_mesh=white_mesh, insert_meshes=insert_meshes, warnings=warnings)
