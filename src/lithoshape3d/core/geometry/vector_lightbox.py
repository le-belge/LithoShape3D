"""Moteur generique d'extrusion vectorielle "parois lisses + epaulement"
pour un caisson lumineux, a partir d'un polygone Shapely ARBITRAIRE.

Extrait de `lightbox_letters_export.py` (ou il a ete developpe et valide en
premier pour LightBox Letters -- corriger le retour utilisateur "hyper
crenele, pas de fond, pas d'epaulement") afin d'etre reutilise SANS
DUPLICATION par le pipeline "LightBox depuis image"
(`image_lightbox_export.py`) : les deux ont exactement le meme besoin --
un corps a cavite en DEUX PALIERS (paroi normale en bas, paroi elargie
-- epaulement -- pres du sommet, pour retenir un capot rapporte) plus un
fond, extrudes DIRECTEMENT depuis un contour vectoriel exact (pas de
rasterisation/voxelisation intermediaire comme le fait `lightbox.py` V1).
Seule la SOURCE du polygone differe (glyphe de police vs silhouette
extraite d'image) -- le moteur d'extrusion/booleen ne le sait jamais.

`lightbox_letters_export.py` garde ses fonctions "lettre" (meme nom, meme
signature, meme comportement observable -- verifie par les tests existants
qui n'ont pas ete modifies) en fines enveloppes qui appellent ce moteur
avec `letter.to_shapely()`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from shapely.geometry import MultiPolygon, Polygon

from lithoshape3d.core.geometry.support import _from_manifold, _to_manifold

if TYPE_CHECKING:
    import trimesh

SHOULDER_DEPTH_MM = 1.75
"""Profondeur (Z) sur laquelle le capot s'encastre dans l'epaulement du
corps. Choisie au milieu de la plage 1.5-2mm suggeree : assez pour une
tenue mecanique reelle (empeche le capot de glisser lateralement une fois
pose, pas seulement pose a plat sur les parois), assez peu pour ne pas trop
mordre sur l'epaisseur imprimee du capot lithophanie a cet endroit (le
capot garde son relief normal au-dela de cette zone d'encastrement)."""

SHOULDER_WIDTH_MM = 1.25
"""Largeur (XY, en retrait vers l'interieur) du rebord d'epaulement.
Choisie au milieu de la plage 1-1.5mm suggeree : assez pour tenir
mecaniquement un capot fin sans dependre d'une tolerance d'impression trop
serree, assez peu pour ne pas fragiliser une paroi deja fine
(wall_thickness_mm typique 1.6-2mm)."""

_TRIANGULATION_MAX_EDGE_RATIO = 0.12
"""Fraction de la plus grande dimension XY du contour source utilisee comme
longueur d'arete maximale cible pour la re-triangulation post-hoc (voir
`_refine_triangulation`). Choisie apres verification visuelle sur le cas
Cherry Moon (~90mm de large -> ~10.8mm d'arete max, ~9x plus de faces que la
triangulation brute mais fini watertight et sans triangles longs visibles en
eventail -- voir
`examples/physical_validation/cherry_moon_source/qualite_corps_apres_fix.png`)."""

_TRIANGULATION_MIN_MAX_EDGE_MM = 1.5
"""Plancher absolu (petites formes, ex. lettres etroites) : en dessous, la
subdivision exploserait le nombre de faces sans benefice visuel reel."""

_TRIANGULATION_MAX_MAX_EDGE_MM = 12.0
"""Plafond absolu (tres grandes formes) : au-dela, le gain visuel marginal
ne justifie plus le cout en nombre de faces."""


def _max_subdivision_edge_mm(outer) -> float:
    minx, miny, maxx, maxy = outer.bounds
    span = max(maxx - minx, maxy - miny)
    target = span * _TRIANGULATION_MAX_EDGE_RATIO
    return min(max(target, _TRIANGULATION_MIN_MAX_EDGE_MM), _TRIANGULATION_MAX_MAX_EDGE_MM)


def _refine_triangulation(mesh, max_edge_mm: float):
    """Re-triangulation post-hoc par subdivision d'aretes longues
    (`trimesh.remesh.subdivide_to_size`), pour corriger la triangulation en
    "eventail" (triangles tres allonges partant d'un seul sommet) produite
    par `trimesh.creation.extrude_polygon` (moteur `manifold3d`, seul
    disponible dans cet environnement -- ni `triangle` ni `mapbox_earcut` qui
    permettraient une contrainte d'aire/angle de triangulation directe ne
    sont installes ; ajouter cette dependance n'a pas ete fait ici). Bisection
    recursive d'aretes -- ne modifie ni le contour ni le volume (a la
    precision de subdivision pres), seulement la densite/repartition des
    faces : un mesh watertight reste watertight apres coup.

    Cette approche ATTENUE le probleme (triangles nettement plus courts et
    reguliers, plus de long eventail visible) sans le resoudre au sens strict
    d'une triangulation Delaunay/qualite optimale -- limitation documentee
    dans le rapport de tache correspondant."""
    import trimesh

    if mesh is None or max_edge_mm <= 0:
        return mesh
    vertices, faces = trimesh.remesh.subdivide_to_size(
        mesh.vertices, mesh.faces, max_edge=max_edge_mm
    )
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=True)


ASSEMBLY_CLEARANCE_MM = 0.15
"""Jeu d'assemblage FDM (rayon, donc par cote) entre le capot et
l'ouverture de l'epaulement : valeur usuelle pour une impression FDM
standard (buse 0.4mm), au milieu de la plage 0.1-0.2mm suggeree -- assez
pour que le capot s'encastre sans forcer malgre les tolerances
d'impression habituelles, assez peu pour rester maintenu sans jeu excessif."""


def _extrude_geom(geom, height: float, z0: float):
    """Extrude une geometrie Shapely (`Polygon` ou `MultiPolygon`, chaque
    composante extrudee separement puis unies par union manifold3d) sur
    `height` mm, translatee en Z a `z0`. `None` si `geom` est vide/degeneree.

    Une union manifold3d (pas une simple concatenation de meshes) est
    necessaire des qu'une forme a plusieurs composantes disjointes (glyphe
    "i"/"j"/"%", ou silhouette d'image avec plusieurs ilots) : deux
    extrusions independantes ne partagent aucune face a fusionner, mais
    rester deux corps disjoints dans le meme fichier STL est un mesh
    valide -- l'union reste utile pour uniformiser le traitement en aval
    (une difference booleenne unique avec la cavite)."""
    import trimesh

    if geom is None or geom.is_empty:
        return None
    polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    meshes = []
    for poly in polys:
        if poly.is_empty or poly.area <= 0:
            continue
        mesh = trimesh.creation.extrude_polygon(poly, height=height)
        mesh.apply_translation((0.0, 0.0, z0))
        meshes.append(mesh)
    if not meshes:
        return None
    if len(meshes) == 1:
        return meshes[0]
    merged = _to_manifold(meshes[0])
    for mesh in meshes[1:]:
        merged = merged + _to_manifold(mesh)
    return _from_manifold(merged)


def build_vector_lightbox_body_mesh(
    outer: Polygon | MultiPolygon,
    depth_mm: float,
    wall_thickness_mm: float,
    *,
    shoulder_depth_mm: float = SHOULDER_DEPTH_MM,
    shoulder_width_mm: float = SHOULDER_WIDTH_MM,
    back_thickness_mm: float = 0.0,
) -> tuple[trimesh.Trimesh, list[str]]:
    """Construit le corps d'un caisson par EXTRUSION DIRECTE d'un contour
    vectoriel Shapely EXACT (pas de rasterisation), avec un epaulement
    annulaire de RETENUE pres du FOND du corps (cavite retrecie sur la
    portion profonde, de `back_thickness_mm` a `depth_mm - shoulder_depth_mm`)
    sur lequel le capot -- de meme largeur que le reste du corps -- vient
    reposer, tandis que la cavite pres de l'AVANT/OUVERTURE (les derniers
    `shoulder_depth_mm` avant `depth_mm`) garde la largeur NORMALE (comme le
    reste du corps) pour loger le capot en affleurement.

    Sens du rebord confirme par l'utilisateur (schema "Option B" valide,
    `examples/physical_validation/cherry_moon_source/rebord_options_AB_schema.png`) :
    l'ancien design ("Option A", cavite large pres du FOND et etroite pres de
    l'AVANT) laissait le capot flotter dans un puits sans rien pour le
    porter par en dessous. Ici la paroi est PLUS EPAISSE pres du fond (elle
    reduit l'ouverture juste sous le capot pour le bloquer) et de largeur
    normale pres de l'ouverture (ou le capot, de meme largeur que le corps,
    vient se loger).

    `back_thickness_mm` (>0) : le fond est integre DIRECTEMENT dans cette
    meme extrusion/soustraction (la cavite basse ne part plus de Z=0 mais de
    `back_thickness_mm`) plutot que fusionne apres coup par une union
    booleenne de deux meshes deja construits -- une union post-hoc entre
    l'exterieur plein et un panneau separe s'est revelee numeriquement
    fragile sur des contours complexes/multi-composantes (triangles
    degeneres a la jonction, cf. retour utilisateur sur un logo tres
    detaille) alors qu'une seule extrusion+soustraction reste robuste,
    identique en substance au reste de ce moteur.

    `outer` : contour exterieur du caisson (`Polygon` ou `MultiPolygon`,
    typiquement `LetterGlyph.to_shapely()` ou `ImageShapeResult.polygon`) --
    ce moteur ne fait AUCUNE hypothese sur son origine."""
    if outer is None or outer.is_empty:
        raise ValueError("Contour vide : corps impossible.")

    warnings: list[str] = []
    eps = min(0.05, depth_mm * 0.001)

    outer_mesh = _extrude_geom(outer, depth_mm + 2 * eps, -eps)
    if outer_mesh is None:
        raise ValueError("Contour degenere : corps impossible.")

    shoulder_top = max(depth_mm - shoulder_depth_mm, eps)
    cavity_bottom = max(back_thickness_mm, 0.0)

    cavity_meshes = []

    # Cavite profonde (du fond jusqu'a `shoulder_top`) : ETROITE -- paroi
    # elargie de `shoulder_width_mm`, c'est le rebord annulaire qui SOUTIENT
    # le capot par en dessous (voir docstring de la fonction, Option B).
    inner_shoulder = outer.buffer(-(wall_thickness_mm + shoulder_width_mm))
    lower_height = (shoulder_top - cavity_bottom) + 2 * eps
    lower_mesh = (
        _extrude_geom(inner_shoulder, lower_height, cavity_bottom - eps)
        if lower_height > 0
        else None
    )
    if lower_mesh is not None:
        cavity_meshes.append(lower_mesh)
    else:
        warnings.append(
            "Forme trop fine pour creuser un epaulement a cette largeur de paroi : "
            "le fond du corps reste plein localement (le capot ne sera pas retenu par un rebord)."
        )

    # Cavite pres de l'avant/ouverture (de `shoulder_top` a `depth_mm`) :
    # LARGE, meme largeur que le reste du corps -- c'est ici que le capot
    # (meme largeur que le corps) vient se loger, en affleurant l'ouverture.
    inner_lower = outer.buffer(-wall_thickness_mm)
    upper_height = (depth_mm - shoulder_top) + 2 * eps
    upper_mesh = (
        _extrude_geom(inner_lower, upper_height, shoulder_top - eps) if upper_height > 0 else None
    )
    if upper_mesh is not None:
        cavity_meshes.append(upper_mesh)
    else:
        warnings.append(
            "Epaisseur de paroi trop grande pour la largeur de la forme : "
            "corps plein (aucune cavite) sur la majeure partie de sa hauteur."
        )

    max_edge_mm = _max_subdivision_edge_mm(outer)

    if not cavity_meshes:
        return _refine_triangulation(outer_mesh, max_edge_mm), warnings

    merged_cavity = _to_manifold(cavity_meshes[0])
    for mesh in cavity_meshes[1:]:
        merged_cavity = merged_cavity + _to_manifold(mesh)
    body_mesh = _from_manifold(_to_manifold(outer_mesh) - merged_cavity)
    if body_mesh.is_empty:
        raise ValueError("Caisson impossible : la cavite supprime tout le volume de la forme.")
    body_mesh = _refine_triangulation(body_mesh, max_edge_mm)
    return body_mesh, warnings


def build_vector_lightbox_back_panel_mesh(
    outer: Polygon | MultiPolygon, thickness_mm: float
) -> trimesh.Trimesh:
    """Panneau plein extrude directement depuis un contour vectoriel exact :
    lisse, sans cavite. Sert a la fois de FOND de caisson (lettre ou image)
    et, translate en Z, de CAPOT PLAT/LISSE quand aucune lithophanie n'est
    demandee (cas d'usage LightBox depuis image "circuit foil" -- meme
    forme d'extrusion, seule la position/l'appelant different)."""
    mesh = _extrude_geom(outer, thickness_mm, 0.0)
    if mesh is None:
        raise ValueError("Contour vide ou degenere : panneau impossible.")
    return _refine_triangulation(mesh, _max_subdivision_edge_mm(outer))


def vector_lightbox_cap_footprint(
    outer: Polygon | MultiPolygon,
    wall_thickness_mm: float,
    *,
    shoulder_width_mm: float = SHOULDER_WIDTH_MM,
    assembly_clearance_mm: float = ASSEMBLY_CLEARANCE_MM,
) -> Polygon | MultiPolygon:
    """Contour (Shapely) du capot : desormais de la MEME largeur que le
    corps normal (en retrait de `wall_thickness_mm` seulement, PAS
    `+ shoulder_width_mm`), puisque le capot se loge dans la cavite LARGE
    pres de l'ouverture (voir `build_vector_lightbox_body_mesh`, Option B) --
    seul le jeu d'assemblage FDM (`assembly_clearance_mm`) est retire en
    plus, pour que le capot rentre sans forcer a l'impression.

    `shoulder_width_mm` est conserve dans la signature pour compatibilite
    des appelants existants (`letter_cap_footprint`,
    `image_lightbox_export.py`) mais N'EST PLUS UTILISE dans le calcul :
    c'est desormais le rebord profond (pas le capot) qui porte cette
    largeur supplementaire."""
    del shoulder_width_mm  # conserve pour compat signature, plus utilise (Option B)
    return outer.buffer(-(wall_thickness_mm + assembly_clearance_mm))
