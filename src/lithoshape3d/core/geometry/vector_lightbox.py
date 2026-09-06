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

from shapely.geometry import MultiPolygon, Point, Polygon, box

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

_SIMPLIFY_EPSILON_MM = 0.005
"""Tolerance de nettoyage pre-extrusion (voir `_extrude_geom`) -- tres en
dessous de toute precision d'impression FDM ou de la resolution d'un
ecran, elimine uniquement les sommets quasi-degeneres issus de chaines de
booleennes shapely, sans alterer la geometrie percue."""

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
    (une difference booleenne unique avec la cavite).

    Chaque mesh extrude est verifie/CORRIGE en volume (`mesh.invert()` si
    negatif) : une chaine d'operations booleennes shapely (intersection/
    difference/union, ex. decoupe du capot 2 couleurs) peut produire des
    composantes dont l'extrusion ressort a volume negatif (constate
    reellement sur un cas a ~50 composantes, logo "Cherry Moon" -- quelques
    sous-polygones donnaient un solide "invers~e" malgre un contour
    exterieur shapely deja anti-horaire (`shapely.geometry.polygon.orient`
    seul ne suffit PAS : le moteur de triangulation interne de
    `trimesh.creation.extrude_polygon`, ici `manifold3d`, ne suit pas
    necessairement la convention de sens de parcours du polygone source).
    Corriger au niveau du MESH (verifier le signe du volume calcule, inverser
    les faces si negatif) est plus robuste que d'esperer un pre-tri correct
    du polygone source -- fonctionne quel que soit le moteur de
    triangulation. Pas un cas isole a ce fichier : tout polygone complexe
    issu d'une chaine de booleennes peut presenter ce defaut -- correction
    generique, systematique sur CHAQUE composante.

    Chaque `poly` est aussi passe par `simplify(tolerance=_SIMPLIFY_EPSILON_MM,
    preserve_topology=True)` avant extrusion : une chaine d'intersection/
    difference shapely peut laisser des sommets quasi-degeneres (distance
    sub-micrometrique) a la frontiere de la booleenne -- constate reellement
    (meme cas Cherry Moon) : un sous-polygone valide au sens shapely
    (`is_valid=True`) produisait tout de meme un mesh non watertight
    (triangles degeneres) via `trimesh.creation.extrude_polygon`. Une
    tolerance de 0.005mm (largement sous toute precision d'impression FDM)
    ne modifie pas la geometrie percue mais elimine ces sommets quasi-
    colineaires, seule difference entre les deux versions verifiee sur ce
    cas reel."""
    import trimesh

    if geom is None or geom.is_empty:
        return None
    polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    meshes = []
    for poly in polys:
        if poly.is_empty or poly.area <= 0:
            continue
        poly = poly.simplify(_SIMPLIFY_EPSILON_MM, preserve_topology=True)
        if poly.is_empty or poly.area <= 0:
            continue
        mesh = trimesh.creation.extrude_polygon(poly, height=height)
        if mesh.volume < 0:
            mesh.invert()
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

    if not cavity_meshes:
        return outer_mesh, warnings

    merged_cavity = _to_manifold(cavity_meshes[0])
    for mesh in cavity_meshes[1:]:
        merged_cavity = merged_cavity + _to_manifold(mesh)
    body_mesh = _from_manifold(_to_manifold(outer_mesh) - merged_cavity)
    if body_mesh.is_empty:
        raise ValueError("Caisson impossible : la cavite supprime tout le volume de la forme.")
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
    return mesh


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


CONNECTOR_SHAPE_RECT = "rect"
CONNECTOR_SHAPE_CIRCLE = "circle"

CONNECTOR_PRESET_USB_C = {
    "shape": CONNECTOR_SHAPE_RECT,
    "width_mm": 9.5,
    "height_mm": 3.8,
    "corner_radius_mm": 1.0,
}
"""Emprise generique d'un connecteur bulkhead USB-C (legerement genereuse
par rapport aux cotes officiels du connecteur ~8.94x3.26mm) -- laisse un peu
de jeu de montage, a ajuster par l'utilisateur selon le boitier reel de son
connecteur (trop variable d'un fournisseur a l'autre pour une cote exacte)."""

CONNECTOR_PRESET_POGO = {
    "shape": CONNECTOR_SHAPE_CIRCLE,
    "width_mm": 6.0,
    "height_mm": None,
    "corner_radius_mm": 0.0,
}
"""Diametre generique pour un petit bloc pogo-pin (2-4 broches) -- pas une
cote constructeur, juste un passage suffisant pour la plupart des blocs
courants, a ajuster si besoin (mode "Personnalise" cote UI)."""


def apply_back_panel_connector_cutout(
    body_mesh: trimesh.Trimesh,
    outer: Polygon | MultiPolygon,
    back_thickness_mm: float,
    *,
    shape: str,
    width_mm: float,
    height_mm: float | None = None,
    corner_radius_mm: float = 0.0,
    center_x_mm: float,
    center_y_mm: float,
) -> trimesh.Trimesh:
    """Decoupe un trou traversant pour un connecteur dans le FOND INTEGRE du
    corps (Z = 0..`back_thickness_mm`) -- seul endroit du corps qui reste
    plein sur TOUTE l'empreinte de `outer`, quelle que soit l'epaisseur des
    parois/de l'epaulement (voir `build_vector_lightbox_body_mesh` :
    `cavity_bottom = max(back_thickness_mm, 0.0)`, la cavite ne mord jamais
    sous cette cote) -- une decoupe ici ne risque donc jamais de percer une
    paroi laterale par erreur, quelle que soit la position choisie a
    l'interieur de la silhouette.

    `shape` : `CONNECTOR_SHAPE_RECT` (rectangle a coins arrondis via
    `corner_radius_mm`, `width_mm` x `height_mm`) ou `CONNECTOR_SHAPE_CIRCLE`
    (cercle de diametre `width_mm`, `height_mm` ignore).

    Leve `ValueError` si `(center_x_mm, center_y_mm)` tombe hors de `outer` :
    mieux vaut echouer explicitement (meme discipline que
    `real_edge_profile` dans `support.py`) qu'un caisson silencieusement
    sans effet ou incoherent."""
    if not outer.contains(Point(center_x_mm, center_y_mm)):
        raise ValueError(
            f"apply_back_panel_connector_cutout: le centre ({center_x_mm:.2f}, "
            f"{center_y_mm:.2f}) tombe hors de la silhouette -- ajustez la position du connecteur."
        )

    if shape == CONNECTOR_SHAPE_RECT:
        if height_mm is None:
            raise ValueError("apply_back_panel_connector_cutout: height_mm requis pour shape='rect'.")
        half_w, half_h = width_mm / 2.0, height_mm / 2.0
        cutter_polygon = box(
            center_x_mm - half_w, center_y_mm - half_h, center_x_mm + half_w, center_y_mm + half_h
        )
        if corner_radius_mm > 0.0:
            cutter_polygon = cutter_polygon.buffer(corner_radius_mm).buffer(-corner_radius_mm)
    elif shape == CONNECTOR_SHAPE_CIRCLE:
        cutter_polygon = Point(center_x_mm, center_y_mm).buffer(width_mm / 2.0)
    else:
        raise ValueError(
            f"apply_back_panel_connector_cutout: shape invalide {shape!r} "
            f"(attendu {CONNECTOR_SHAPE_RECT!r} ou {CONNECTOR_SHAPE_CIRCLE!r})."
        )

    eps = min(0.05, back_thickness_mm * 0.1)
    cutter_mesh = _extrude_geom(cutter_polygon, back_thickness_mm + 2 * eps, -eps)
    if cutter_mesh is None:
        raise ValueError("apply_back_panel_connector_cutout: decoupe degeneree (dimensions trop petites ?).")

    result = _from_manifold(_to_manifold(body_mesh) - _to_manifold(cutter_mesh))
    if result.is_empty:
        raise ValueError("apply_back_panel_connector_cutout: la decoupe supprime tout le volume du corps.")
    return result
