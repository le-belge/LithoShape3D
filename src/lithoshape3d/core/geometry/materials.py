"""Partition du resultat compose par materiau, pour l'export/apercu multi-couleur.

Principe : la geometrie finale (`compose_scene_heightfield`) reste un champ
de hauteur UNIQUE (Z = epaisseur, dos a Z=0) -- ce module n'y touche pas.
Ce qu'il ajoute, c'est une notion de "proprietaire" par CELLULE de grille
(quelle Zone -- donc quel Material -- a fourni cette portion de surface),
calculee avec exactement la meme regle de recouvrement que la composition
des hauteurs (derniere zone visible qui couvre une cellule = proprietaire),
puis utilisee pour appeler `build_mesh_from_heightfield` une fois par
materiau distinct sur le MEME champ de hauteur compose, restreint a son
propre sous-ensemble de cellules.

Chaque corps ainsi obtenu est un volume ferme independant (son propre dos a
Z=0, ses propres parois) partageant exactement le meme repere XYZ que les
autres -- pas un depouillement de "peau" sur le mesh compose unique, ce qui
garantit un alignement parfait sans etape de recalage.

Cas a une seule zone/un seul materiau (le cas courant, historique) : court-
circuite toute cette logique et retourne directement le mesh compose complet,
pour ne pas alourdir le chemin le plus frequent."""

from __future__ import annotations

import numpy as np
import trimesh

from lithoshape3d.core.geometry.composition import ZoneSource, compose_scene_heightfield
from lithoshape3d.core.geometry.heightmap import grid_dimensions
from lithoshape3d.core.geometry.mesh_builder import (
    DEFAULT_MASK_THRESHOLD,
    build_mesh_from_heightfield,
)
from lithoshape3d.core.image.preprocessing import resize_array
from lithoshape3d.core.image.transform import apply_image_transform
from lithoshape3d.core.scene.models import ImageTransform


def _compose_cell_ownership(
    zone_sources: list[ZoneSource],
    mask_threshold: float,
    shape_mask: np.ndarray | None,
    image_transform: ImageTransform | None = None,
) -> np.ndarray:
    """Retourne une grille (rows-1, cols-1) d'ids de Zone (ou None), un
    "proprietaire" par cellule -- meme regle de recouvrement et meme ordre
    d'iteration que `compose_scene_heightfield` (la derniere zone visible
    dont le masque couvre entierement les 4 coins d'une cellule en devient
    proprietaire, qu'elle soit BASE/REPLACE/ADD : visuellement, c'est
    toujours la matiere la plus "au-dessus" a cet endroit). `shape_mask`
    (v0.4) restreint l'attribution exactement comme en composition : jamais
    de proprietaire hors de la Shape."""
    base_source = next(
        s for s in zone_sources if s.zone.visible and s.zone.composition_mode.value == "base"
    )
    rows, cols = grid_dimensions(base_source.zone.geometry_params)
    owner = np.full((rows - 1, cols - 1), None, dtype=object)

    if shape_mask is None:
        shape_active = np.ones((rows, cols), dtype=bool)
    else:
        if shape_mask.shape != (rows, cols):
            shape_mask = resize_array(shape_mask.astype(np.float32), width_px=cols, height_px=rows) >= 0.5
        shape_active = np.flipud(shape_mask)
    shape_cell_active = shape_active[:-1, :-1] & shape_active[:-1, 1:] & shape_active[1:, :-1] & shape_active[1:, 1:]

    for source in zone_sources:
        zone = source.zone
        if not zone.visible:
            continue

        mask = source.mask
        if mask is None:
            mask = np.ones((rows, cols), dtype=np.float32)
        elif image_transform is None:
            if mask.shape != (rows, cols):
                mask = resize_array(mask, width_px=cols, height_px=rows)
        else:
            # Meme regle qu'en composition (voir composition.py) : le
            # masque doit subir le meme cadrage que la photo, sinon
            # l'appartenance materiau d'une zone se detache du sujet des
            # que la photo est deplacee/zoomee/tournee (cf. 2.12).
            mask = apply_image_transform(
                mask.astype(np.float32), image_transform, width_px=cols, height_px=rows, fill_value=0.0
            )
        mask = np.flipud(mask)

        active = mask >= mask_threshold
        cell_active = active[:-1, :-1] & active[:-1, 1:] & active[1:, :-1] & active[1:, 1:]
        owner[cell_active & shape_cell_active] = zone.id

    return owner


def partition_mesh_by_material(
    zone_sources: list[ZoneSource],
    mask_threshold: float = DEFAULT_MASK_THRESHOLD,
    image_transform: ImageTransform | None = None,
    shape_mask: np.ndarray | None = None,
) -> dict[str, trimesh.Trimesh]:
    """Retourne {nom_materiau: mesh_ferme_independant}, tous alignes sur le
    meme repere. Les zones invisibles sont ignorees (comme en composition).
    Une cellule active mais orpheline (aucune zone n'en est proprietaire, cas
    limite theorique de bord en dents-de-scie) retombe sur le materiau de la
    zone BASE, pour ne jamais laisser un trou dans le corps imprimable."""
    visible_sources = [s for s in zone_sources if s.zone.visible]
    materials_used = {s.zone.material.name for s in visible_sources}

    z_final, active_final, width_mm, height_mm = compose_scene_heightfield(
        zone_sources, mask_threshold, image_transform=image_transform, shape_mask=shape_mask
    )

    if len(materials_used) <= 1:
        material_name = next(iter(materials_used), "default")
        return {material_name: build_mesh_from_heightfield(z_final, active_final, width_mm, height_mm)}

    base_source = next(s for s in visible_sources if s.zone.composition_mode.value == "base")
    owner_cells = _compose_cell_ownership(zone_sources, mask_threshold, shape_mask, image_transform)

    active_cells = active_final[:-1, :-1] & active_final[:-1, 1:] & active_final[1:, :-1] & active_final[1:, 1:]
    orphan_cells = active_cells & np.equal(owner_cells, None)
    if orphan_cells.any():
        owner_cells = owner_cells.copy()
        owner_cells[orphan_cells] = base_source.zone.id

    zone_by_id = {s.zone.id: s.zone for s in visible_sources}
    material_meshes: dict[str, list[trimesh.Trimesh]] = {}

    for zone_id, zone in zone_by_id.items():
        cells_for_zone = owner_cells == zone_id
        if not cells_for_zone.any():
            continue

        vertex_active = np.zeros_like(active_final)
        vertex_active[:-1, :-1] |= cells_for_zone
        vertex_active[:-1, 1:] |= cells_for_zone
        vertex_active[1:, :-1] |= cells_for_zone
        vertex_active[1:, 1:] |= cells_for_zone

        try:
            mesh = build_mesh_from_heightfield(z_final, vertex_active, width_mm, height_mm)
        except ValueError:
            continue  # empreinte trop fine pour la resolution courante : ignoree proprement
        material_meshes.setdefault(zone.material.name, []).append(mesh)

    return {
        name: (meshes[0] if len(meshes) == 1 else trimesh.util.concatenate(meshes))
        for name, meshes in material_meshes.items()
    }
