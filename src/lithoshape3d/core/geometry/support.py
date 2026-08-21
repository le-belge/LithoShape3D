"""Pied/support d'impression, fusionne au modele compose.

Pas un support de surplomb (ca reste le travail du slicer) : le but est
uniquement de stabiliser physiquement une lithophanie fine et large sur le
plateau, via un pied analytique simple (des boites), fusionne au modele par
une union manifold3d -- pas de construction topologique main sur la couture,
ce qui serait fragile pour un gain de robustesse minime : manifold3d gere
deja tres bien l'union de solides fermes qui se recouvrent en volume.

Point important verifie empiriquement : une union manifold3d entre deux
solides qui ne font qu'AFFLEURER (faces exactement coincidentes, aucun
recouvrement volumique reel) peut les laisser distincts au lieu de les
fusionner (`connected_components` > 1 en sortie). Toutes les pieces
generees ici (pied, renforts) sont donc volontairement dimensionnees pour
se recouvrir en profondeur, jamais seulement se toucher.

Convention (identique a mesh_builder.py) : X = largeur, Y = hauteur (bas de
l'image = Y=0), Z = epaisseur (dos a Z=0). Le pied se fixe sous le bord bas
du panneau (Y=0), s'etend vers Y negatif, et vers Z positif sur une
profondeur bien plus grande que l'epaisseur fine de la lithophanie -- c'est
cette largeur en Z (pas visible en usage normal, seulement au sol) qui donne
au resultat imprime une base stable, y compris pour un affichage/impression
"debout" (panneau vertical)."""

from __future__ import annotations

import numpy as np
import trimesh

from lithoshape3d.core.scene.models import PrintSupport, SupportType

_RIB_PANEL_PENETRATION_MM = 2.0
"""De combien un renfort remonte au-dela de Y=0 (dans le panneau) -- garantit
un recouvrement volumique reel avec le panneau, pas juste un contact de
surface (voir note de module)."""


def _to_manifold(mesh: trimesh.Trimesh):
    import manifold3d

    m3d_mesh = manifold3d.Mesh(
        vert_properties=mesh.vertices.astype(np.float32),
        tri_verts=mesh.faces.astype(np.uint32),
    )
    return manifold3d.Manifold(m3d_mesh)


def _from_manifold(manifold) -> trimesh.Trimesh:
    mesh = manifold.to_mesh()
    vertices = np.asarray(mesh.vert_properties)[:, :3]
    faces = np.asarray(mesh.tri_verts)
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=True)


def _flat_foot_mesh(x_min: float, x_max: float, support: PrintSupport) -> trimesh.Trimesh:
    x_min = x_min - support.overhang_left_mm
    x_max = x_max + support.overhang_right_mm
    extents = [x_max - x_min, support.height_mm, support.depth_mm]
    box = trimesh.creation.box(extents=extents)
    center = [
        (x_min + x_max) / 2.0,
        -support.height_mm / 2.0,
        support.depth_mm / 2.0,
    ]
    box.apply_translation(center)
    return box


def _reinforcement_ribs(x_min: float, x_max: float, support: PrintSupport) -> list[trimesh.Trimesh]:
    """Renforts : petits piliers pleins repartis sur la largeur utile (hors
    debords), qui prolongent localement le pied vers le haut, a l'interieur
    du panneau, sur `_RIB_PANEL_PENETRATION_MM`.

    Volontairement de simples boites recouvrant profondement le pied ET le
    panneau (pas un gousset diagonal fin) : un premier essai avec un prisme
    triangulaire affleurant les faces du pied a laisse des corps disjoints
    apres union (`connected_components` > 1) -- un vrai recouvrement
    volumique, pas seulement un contact de surface, est necessaire pour une
    fusion manifold3d fiable."""
    if support.rib_count <= 0:
        return []

    width = x_max - x_min
    margin = support.rib_thickness_mm  # evite un renfort colle au bord
    usable_start, usable_end = x_min + margin, max(x_max - margin, x_min + margin)
    if usable_end <= usable_start:
        centers = [x_min + width / 2.0]
    else:
        centers = np.linspace(usable_start, usable_end, support.rib_count)

    half_thickness = support.rib_thickness_mm / 2.0
    y_min, y_max = -support.height_mm, _RIB_PANEL_PENETRATION_MM
    extents = [support.rib_thickness_mm, y_max - y_min, support.depth_mm]
    y_center = (y_min + y_max) / 2.0
    z_center = support.depth_mm / 2.0

    ribs = []
    for x_center in centers:
        x_center = float(np.clip(x_center, x_min + half_thickness, x_max - half_thickness))
        rib = trimesh.creation.box(extents=extents)
        rib.apply_translation([x_center, y_center, z_center])
        ribs.append(rib)
    return ribs


def build_support_mesh(x_min: float, x_max: float, support: PrintSupport) -> trimesh.Trimesh | None:
    """Construit le pied seul (pas encore fusionne), sur l'etendue X
    [x_min, x_max] fournie -- generalise a toute Shape (v0.4) : passer les
    bornes X reelles du mesh compose (pas forcement [0, width_mm], une
    forme non rectangulaire -- coeur, lettre -- peut avoir une empreinte
    plus etroite ou decalee a son bord bas). `None` si SupportType.NONE."""
    if support.support_type is SupportType.NONE:
        return None

    parts = [_flat_foot_mesh(x_min, x_max, support)]
    if support.support_type is SupportType.REINFORCED:
        parts.extend(_reinforcement_ribs(x_min, x_max, support))

    if len(parts) == 1:
        return parts[0]
    return trimesh.util.concatenate(parts)


def attach_support(mesh: trimesh.Trimesh, support: PrintSupport) -> trimesh.Trimesh:
    """Fusionne le pied au modele compose (union manifold3d). Retourne `mesh`
    inchange si `support.support_type is SupportType.NONE`.

    L'etendue X du pied est deduite des bornes REELLES du mesh (pas d'une
    largeur canonique supposee) : generalise automatiquement a toute Shape
    -- un coeur, un cercle ou une lettre isolee obtiennent un pied cale sur
    leur propre empreinte, pas sur un rectangle qui n'existe plus."""
    if support.support_type is SupportType.NONE:
        return mesh
    x_min, x_max = float(mesh.bounds[0][0]), float(mesh.bounds[1][0])
    support_mesh = build_support_mesh(x_min, x_max, support)
    if support_mesh is None:
        return mesh

    fused = _to_manifold(mesh) + _to_manifold(support_mesh)
    return _from_manifold(fused)
