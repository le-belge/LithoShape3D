"""Extraction vectorielle DIRECTE d'une silhouette depuis un fichier `.svg`
source, sans rasterisation prealable.

Contexte (bug rapporte) : le pipeline historique "LightBox depuis image"
traitait un `.svg` en le rasterisant d'abord en PNG 1024x1024
(`ui/shape_svg_import.py::rasterize_svg_to_alpha_png`, QtSvg), puis
extrayait un contour PIXEL depuis ce raster (`cv2.findContours` +
`approxPolyDP`). Les vraies courbes de Bezier du SVG source (commandes `C`/
`S`/`Q`/`T`/`A`) etaient donc perdues des la premiere etape, quelle que soit
la qualite de la simplification/du lissage applique ensuite -- la silhouette
finale restait plafonnee par la resolution du raster (1024px) et sa
polygonalisation implicite.

Ce module lit le XML du `.svg` directement (`lxml`, deja une dependance du
projet) et tessellle les segments de chemin EXACTS (via `svgpathtools`, qui
fournit des objets `Line`/`CubicBezier`/`QuadraticBezier`/`Arc` avec une
methode `.point(t)` parametrique) par subdivision recursive adaptative basee
sur une erreur de corde maximale ("chord error") -- pas un nombre fixe de
segments : une grande courbe presque droite recoit peu de points, une courbe
tres cambree en recoit beaucoup, jusqu'a ce que l'ecart entre la corde et le
point median parametrique de la courbe passe sous la tolerance demandee.

Bibliotheque de parsing choisie : `svgpathtools` (gere nativement `M/L/H/V/
C/S/Q/T/A/Z`, coordonnees absolues et relatives, et les arcs elliptiques `A`
-- pas de reimplementation maison du parseur de commandes de chemin). Les
transformations (`transform="translate(...)"`, `matrix(...)`, `scale(...)`,
`rotate(...)` sur les groupes parents comme sur `Tesla_T_symbol.svg`, qui a
`<g id="T" transform="translate(-45.84,-64.297)">`) sont lues directement
depuis le XML via `lxml` (cumulees le long de la chaine d'ancetres) car
`svgpathtools.svg2paths` n'applique PAS les transforms de groupe -- seulement
les transforms portes par l'element `<path>` lui-meme.

Echelle SVG-unites -> mm : plutot que de reconstituer la logique complete de
mapping `viewBox`/`width`/`height` racine (qui ne definit que la fenetre de
visualisation, pas necessairement la boite englobante reelle du dessin), on
calcule l'echelle directement depuis la boite englobante du contour
GEOMETRIQUE obtenu apres application de tous les transforms de groupe, mise
a l'echelle pour que sa largeur egale `width_mm` demande -- resultat
strictement equivalent pour un SVG dont le contenu remplit le `viewBox`
(cas normal), et plus robuste dans le cas contraire (marge/cadrage interne)
puisqu'on ne met a l'echelle que la matiere reelle du dessin, pas une zone
de canevas potentiellement plus grande.

Plusieurs `<path>`/sous-chemins sont combines en un seul polygone/
MultiPolygon Shapely coherent via `contour_classification.
classify_contours_by_containment` -- REUTILISEE telle quelle (meme
algorithme que `image_shape_extractor.mask_to_polygon` pour les contours
raster, PAS duplique) : classification par confinement geometrique
(profondeur d'imbrication paire/impaire), une approximation pragmatique de
la regle de remplissage SVG (`nonzero` par defaut, `evenodd` si specifie)
qui donne le resultat attendu pour l'immense majorite des logos/silhouettes
sans auto-intersection (cas `Tesla_T_symbol.svg` : 2 `<path>` disjoints,
aucune imbrication -> 2 composantes exterieures separees, unies en
MultiPolygon). LIMITATION CONNUE : pour un chemin auto-intersectant dont le
rendu correct depend precisement de la regle `nonzero` (vs `evenodd`), la
classification par confinement peut differer du rendu navigateur -- cas rare
pour les logos/silhouettes vises par ce pipeline, non rencontre sur les
fichiers de validation de cette session (Tesla, Cherry Moon, Thunderdome,
Circuit Foil)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from lxml import etree
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from lithoshape3d.core.geometry.contour_classification import (
    ContourClassificationError,
    classify_contours_by_containment,
)

try:
    from svgpathtools import parse_path
except ImportError as _exc:  # pragma: no cover - defensif, verifie par un test dedie
    raise ImportError(
        "svgpathtools est requis pour l'extraction vectorielle directe des SVG "
        "(dependance 'core', voir pyproject.toml)."
    ) from _exc

_SVG_NS = "{http://www.w3.org/2000/svg}"
_DEFAULT_MAX_CHORD_ERROR_MM = 0.08
_MAX_SUBDIVISION_DEPTH = 24
"""Garde-fou contre une recursion infinie sur un segment degenere (longueur
nulle, tolerance non atteignable a la precision flottante) -- une
profondeur de 24 correspond a 2**24 subdivisions max sur un seul segment,
tres largement suffisant pour toute courbe realiste et jamais atteint sur
un chemin bien forme."""


class SvgPathExtractionError(ValueError):
    """SVG illisible, vide, sans `<path>` exploitable, ou silhouette
    degeneree (aire nulle) apres extraction."""


@dataclass
class SvgPolygonResult:
    polygon: Polygon | MultiPolygon
    """Contour(s) shapely, mm, referentiel Y-up origine bas-gauche -- meme
    convention que `image_shape_extractor.ImageShapeResult.polygon` et
    `LetterGlyph.to_shapely()`, consommable tel quel par `vector_lightbox.py`."""
    width_mm: float
    height_mm: float
    warnings: list[str]


# --------------------------------------------------------------------- #
# Transformations SVG (translate/matrix/scale/rotate/skewX/skewY) : matrices
# affines 3x3 cumulees le long de la chaine d'ancetres XML.
# --------------------------------------------------------------------- #

_IDENTITY = np.eye(3)


def _matrix(a: float, b: float, c: float, d: float, e: float, f: float) -> np.ndarray:
    return np.array([[a, c, e], [b, d, f], [0.0, 0.0, 1.0]])


def _parse_transform_attr(value: str | None) -> np.ndarray:
    """Parse un attribut `transform="..."` SVG (une ou plusieurs
    fonctions composees dans l'ordre d'ecriture) en une matrice affine 3x3.
    Retourne l'identite si l'attribut est absent/vide."""
    if not value or not value.strip():
        return _IDENTITY.copy()

    result = _IDENTITY.copy()
    for name, args_str in _iter_transform_functions(value):
        args = [float(x) for x in args_str]
        if name == "matrix" and len(args) == 6:
            m = _matrix(*args)
        elif name == "translate":
            tx = args[0] if args else 0.0
            ty = args[1] if len(args) > 1 else 0.0
            m = _matrix(1, 0, 0, 1, tx, ty)
        elif name == "scale":
            sx = args[0] if args else 1.0
            sy = args[1] if len(args) > 1 else sx
            m = _matrix(sx, 0, 0, sy, 0, 0)
        elif name == "rotate":
            angle = math.radians(args[0] if args else 0.0)
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            rot = _matrix(cos_a, sin_a, -sin_a, cos_a, 0, 0)
            if len(args) >= 3:
                cx, cy = args[1], args[2]
                m = _matrix(1, 0, 0, 1, cx, cy) @ rot @ _matrix(1, 0, 0, 1, -cx, -cy)
            else:
                m = rot
        elif name == "skewX" and args:
            m = _matrix(1, 0, math.tan(math.radians(args[0])), 1, 0, 0)
        elif name == "skewY" and args:
            m = _matrix(1, math.tan(math.radians(args[0])), 0, 1, 0, 0)
        else:  # pragma: no cover - fonction non reconnue, ignoree defensivement
            continue
        result = result @ m
    return result


def _iter_transform_functions(value: str):
    import re

    for match in re.finditer(r"(\w+)\s*\(([^)]*)\)", value):
        name = match.group(1)
        args_str = re.split(r"[,\s]+", match.group(2).strip())
        args_str = [a for a in args_str if a]
        yield name, args_str


def _apply_matrix(m: np.ndarray, x: float, y: float) -> tuple[float, float]:
    vec = m @ np.array([x, y, 1.0])
    return float(vec[0]), float(vec[1])


# --------------------------------------------------------------------- #
# Tessellation adaptative par erreur de corde
# --------------------------------------------------------------------- #


def _point_line_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Distance perpendiculaire du point (px,py) a la droite (a,b) -- test
    de "platitude" standard pour la subdivision adaptative de courbes."""
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return math.hypot(px - ax, py - ay)
    return abs(dx * (ay - py) - (ax - px) * dy) / length


def adaptive_tessellate_segment(
    segment,
    transform: np.ndarray,
    tol: float,
) -> list[tuple[float, float]]:
    """Tessellle UN segment de chemin (`Line`/`CubicBezier`/`QuadraticBezier`/
    `Arc`, objets `svgpathtools`) en une liste de points `(x, y)` DEJA
    mappes par `transform` (matrice affine 3x3), par subdivision recursive :
    on evalue le point median parametrique `segment.point(0.5)` et on
    subdivise tant que sa distance a la corde (segment reliant les deux
    extremites deja mappees) depasse `tol` -- equivalent du critere standard
    de subdivision de De Casteljau pour les courbes de Bezier, generalise
    ici a tout segment parametrique via `.point(t)` (donc applicable aussi
    aux arcs elliptiques `A`, que De Casteljau seul ne couvre pas).

    Retourne les points SANS doublon aux jonctions (le premier point de
    chaque sous-segment est omis sauf pour le tout premier appel) -- laisse
    a l'appelant le soin de recoller les segments consecutifs d'un meme
    chemin."""

    def _point(t: float) -> tuple[float, float]:
        z = segment.point(t)
        return _apply_matrix(transform, z.real, z.imag)

    def _subdivide(
        t0: float, t1: float, p0: tuple[float, float], p1: tuple[float, float], depth: int
    ) -> list[tuple[float, float]]:
        if depth >= _MAX_SUBDIVISION_DEPTH:
            return [p0, p1]
        tm = (t0 + t1) / 2.0
        pm = _point(tm)
        err = _point_line_distance(pm[0], pm[1], p0[0], p0[1], p1[0], p1[1])
        if err <= tol:
            return [p0, p1]
        left = _subdivide(t0, tm, p0, pm, depth + 1)
        right = _subdivide(tm, t1, pm, p1, depth + 1)
        return left[:-1] + right

    p_start = _point(0.0)
    p_end = _point(1.0)
    return _subdivide(0.0, 1.0, p_start, p_end, 0)


def _tessellate_path(path, transform: np.ndarray, tol: float) -> list[list[tuple[float, float]]]:
    """Tessellle un `svgpathtools.Path` (une ou plusieurs sous-chemins, une
    commande `M` demarrant chacun) en une liste d'anneaux fermes `(x, y)`."""
    rings: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    subpaths = path.continuous_subpaths() if hasattr(path, "continuous_subpaths") else [path]
    for subpath in subpaths:
        current = []
        for segment in subpath:
            pts = adaptive_tessellate_segment(segment, transform, tol)
            if current and pts and current[-1] == pts[0]:
                pts = pts[1:]
            current.extend(pts)
        if len(current) >= 3:
            rings.append(current)
    return rings


# --------------------------------------------------------------------- #
# Lecture XML : cumul des transforms de groupe, un `<path>` a la fois
# --------------------------------------------------------------------- #


def _local_tag(elem) -> str:
    tag = elem.tag
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


_BACKGROUND_FILL_VALUES = {"#fff", "#ffffff", "white", "none"}
"""Valeurs de `fill` traitees comme "fond" (pas de la matiere) -- un `<path>`
avec l'une de ces couleurs est exclu de l'extraction. Regle GENERIQUE (pas
specifique a un fichier) : un export SVG standard (Illustrator, Inkscape...)
dessine tres souvent un rectangle de fond blanc plein canevas comme PREMIER
`<path>` du document (constate sur `cherry_moon.svg`, source Wikimedia
Commons -- `<path fill="#fff" d="M0 0h192.756v192.756H0V0z"/>`) -- sans ce
filtre, l'union de tous les `<path>` inclut ce rectangle de fond et le
resultat degenere en simple rectangle (le fond, plus grand que tout le
reste, domine `unary_union`). Coherent avec le reste du pipeline : le
chemin raster (`image_shape_extractor.py`) traite deja le blanc/transparent
comme "pas de matiere" (canal alpha ou seuillage par luminosite) -- cette
regle applique le meme principe cote vectoriel, sans aucune dependance a la
taille/position du chemin (donc pas un hack "si plein canevas")."""


def _is_background_fill(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in _BACKGROUND_FILL_VALUES


def _collect_paths_with_transforms(root) -> list[tuple[str, np.ndarray, str]]:
    """Parcourt l'arbre XML et retourne, pour chaque element `<path>`
    exploitable ET dont le remplissage n'est pas du "fond" (voir
    `_is_background_fill` -- blanc/`none`, herite des ancetres si non
    surcharge, convention SVG standard), `(d_attr, cumulative_transform,
    fill_rule)` -- le transform cumule inclut celui de tous les ancetres
    (groupes) ET celui porte par l'element `<path>` lui-meme."""
    results: list[tuple[str, np.ndarray, str]] = []

    def _walk(elem, inherited: np.ndarray, inherited_fill: str | None) -> None:
        own = _parse_transform_attr(elem.get("transform"))
        cumulative = inherited @ own
        own_fill = elem.get("fill")
        effective_fill = own_fill if own_fill is not None else inherited_fill
        tag = _local_tag(elem)
        if tag == "path":
            d_attr = elem.get("d")
            if d_attr and not _is_background_fill(effective_fill):
                fill_rule = elem.get("fill-rule") or elem.get("clip-rule") or "nonzero"
                results.append((d_attr, cumulative, fill_rule))
        for child in elem:
            if isinstance(_local_tag(child), str):
                _walk(child, cumulative, effective_fill)

    _walk(root, _IDENTITY.copy(), None)
    return results


def _repair_self_intersecting_ring(
    ring: list[tuple[float, float]],
) -> list[list[tuple[float, float]]]:
    """Repare un anneau auto-intersectant (`Polygon` invalide au sens OGC)
    issu de la tessellation directe d'un `<path>` SVG -- cas reel rencontre
    sur `Tesla_T_symbol.svg` : le contour du "T" se pince en un point
    proche de sa jonction centrale (artefact du dessin source lui-meme, pas
    un bug de tessellation -- le meme phenomene que `contour_classification
    ._repair_touching_hole` traite deja pour les trous internes touchant
    leur contour, ici applique a un anneau EXTERIEUR isole avant meme la
    classification par confinement).

    Repare via `buffer(0)` (standard shapely pour un polygone auto-
    intersectant) puis reinjecte le resultat comme un ou plusieurs anneaux
    PLATS (exterieur(s) + trou(s) eventuels) -- `classify_contours_by_
    containment`, appelee ensuite par l'appelant, reclassera correctement
    ces anneaux par confinement geometrique (pas de duplication de cette
    logique ici).

    NOTE (nettoyage) : cette fonction etait auparavant definie DEUX FOIS
    dans ce module (une premiere version ici, une seconde plus bas qui
    "shadowait" silencieusement la premiere -- Python ne garde que la
    derniere definition d'un nom de fonction dans un module). Les deux
    versions etaient fonctionnellement equivalentes (meme algorithme
    `buffer(0)`) ; seule celle-ci est conservee."""
    polygon = Polygon(ring)
    if polygon.is_valid and polygon.area > 0:
        return [ring]

    repaired = polygon.buffer(0)
    if repaired.is_empty:
        return []

    geoms = list(repaired.geoms) if repaired.geom_type == "MultiPolygon" else [repaired]
    rings_out: list[list[tuple[float, float]]] = []
    for geom in geoms:
        if geom.area <= 0:
            continue
        rings_out.append(list(geom.exterior.coords))
        for interior in geom.interiors:
            rings_out.append(list(interior.coords))
    return rings_out


@dataclass
class SvgComponentsResult:
    """Resultat "composants" (non-unifie) de l'extraction vectorielle : une
    entree par `<path>` d'origine, DEJA a l'echelle mm/Y-up mais PAS encore
    combinee avec les autres. Consomme par `extract_polygon_from_svg` (union
    simple, mode `silhouette`) ET par le calcul d'enveloppe soudee (mode
    `artwork_envelope`, voir `vector_envelope.py`) -- les DEUX modes
    partagent ainsi le meme moteur de parsing/tessellation, seule l'etape de
    COMBINAISON finale differe."""

    polygons: list[Polygon | MultiPolygon]
    """Un element par `<path>` XML d'origine (dans l'ordre du document),
    deja repare (`buffer(0)`) et avec sa propre regle de remplissage
    appliquee -- voir docstring de `extract_svg_components_from_svg`."""
    width_mm: float
    height_mm: float


def _fill_rule_of(fill_rule: str) -> str:
    normalized = (fill_rule or "nonzero").strip().lower()
    return "evenodd" if normalized == "evenodd" else "nonzero"


def extract_svg_components_from_svg(
    svg_path: str | Path,
    width_mm: float,
    *,
    max_chord_error_mm: float = _DEFAULT_MAX_CHORD_ERROR_MM,
) -> SvgComponentsResult:
    """Coeur du parsing/tessellation vectoriel, PARTAGE par `silhouette` et
    `artwork_envelope` (voir `SvgComponentsResult`) : parse `svg_path`,
    extrait TOUS les `<path>` (avec leurs transforms de groupe cumules), les
    tessellle par subdivision adaptative (erreur de corde <=
    `max_chord_error_mm` UNE FOIS mis a l'echelle physique `width_mm`), puis
    retourne UN polygone/MultiPolygon par `<path>` d'origine -- SANS les
    combiner entre eux (l'appelant decide comment : union simple pour
    `silhouette`, soudure geometrique controlee pour `artwork_envelope`).

    Regle de remplissage (`fill-rule`, lue depuis le XML) :
      - `evenodd` : geree PRECISEMENT -- les sous-chemins d'un MEME `<path>`
        sont combines par difference symetrique (XOR) via shapely
        (`reduce(symmetric_difference, ...)`), ce qui reproduit exactement
        la semantique "parite de croisements" d'`evenodd` pour ce `<path>`,
        y compris des trous imbriques sur plusieurs niveaux.
      - `nonzero` (par defaut, cas le plus frequent) : chaque sous-chemin de
        CE `<path>` est repare individuellement (`_repair_self_intersecting_
        ring`) et laisse "plat" (ni exterieur ni trou impose) -- la
        classification exterieur/trou entre CES rings et ceux des AUTRES
        `<path>` `nonzero` du document reste faite par CONFINEMENT
        GEOMETRIQUE (`classify_contours_by_containment`), une approximation
        documentee de la vraie regle `nonzero` (comptage de direction de
        croisement) qui donne le resultat attendu pour l'immense majorite
        des logos/silhouettes sans auto-intersection complexe. LIMITATION
        CONNUE, non resolue par cette fonction : un `<path>` `nonzero`
        auto-intersectant dont le rendu correct depend precisement du sens
        de parcours (winding) peut differer du rendu navigateur -- cas rare
        pour les logos/silhouettes vises par ce pipeline.

    Leve `SvgPathExtractionError` si le fichier est illisible, vide, sans
    `<path>` exploitable, ou si un composant est degenere (aire nulle)."""
    if width_mm <= 0:
        raise ValueError("width_mm doit etre > 0.")
    if max_chord_error_mm <= 0:
        raise ValueError("max_chord_error_mm doit etre > 0.")

    svg_path = Path(svg_path)
    try:
        tree = etree.parse(str(svg_path))
    except (OSError, etree.XMLSyntaxError) as exc:
        raise SvgPathExtractionError(f"SVG illisible : {svg_path} ({exc}).") from exc
    root = tree.getroot()

    raw_paths = _collect_paths_with_transforms(root)
    if not raw_paths:
        raise SvgPathExtractionError(f"Aucun element <path> exploitable dans : {svg_path}.")

    parsed: list[tuple[object, np.ndarray, str]] = []
    for d_attr, transform, fill_rule in raw_paths:
        try:
            path_obj = parse_path(d_attr)
        except Exception as exc:
            raise SvgPathExtractionError(f"Chemin SVG invalide (d=\"{d_attr[:60]}...\") : {exc}") from exc
        if len(path_obj) == 0:
            continue
        parsed.append((path_obj, transform, _fill_rule_of(fill_rule)))

    if not parsed:
        raise SvgPathExtractionError(f"Tous les <path> de {svg_path} sont vides.")

    # Passe 1 : estimation de l'echelle a partir de la boite englobante des
    # POINTS DE CONTROLE bruts (une courbe de Bezier reste toujours dans
    # l'enveloppe convexe de ses points de controle -- estimation haute mais
    # tres proche, largement suffisante pour choisir une tolerance de
    # subdivision efficace des le premier passage).
    ctrl_minx = ctrl_miny = math.inf
    ctrl_maxx = ctrl_maxy = -math.inf
    for path_obj, transform, _fill_rule in parsed:
        for segment in path_obj:
            for z in _segment_control_points(segment):
                x, y = _apply_matrix(transform, z.real, z.imag)
                ctrl_minx, ctrl_maxx = min(ctrl_minx, x), max(ctrl_maxx, x)
                ctrl_miny, ctrl_maxy = min(ctrl_miny, y), max(ctrl_maxy, y)

    ctrl_width = ctrl_maxx - ctrl_minx
    if not math.isfinite(ctrl_width) or ctrl_width <= 0:
        raise SvgPathExtractionError(
            f"Boite englobante degeneree (largeur nulle) pour les chemins de {svg_path}."
        )
    scale_estimate = width_mm / ctrl_width
    tol_user_units = max_chord_error_mm / scale_estimate

    # Passe 2 : tessellation adaptative reelle (unites document SVG, apres
    # transforms de groupe, AVANT mise a l'echelle mm finale) -- un groupe de
    # rings PAR <path> d'origine (pas encore aplati/fusionne entre <path>).
    per_path_rings: list[tuple[list[list[tuple[float, float]]], str]] = []
    for path_obj, transform, fill_rule in parsed:
        rings = _tessellate_path(path_obj, transform, tol_user_units)
        if rings:
            per_path_rings.append((rings, fill_rule))

    if not per_path_rings:
        raise SvgPathExtractionError(f"Aucun contour ferme exploitable dans : {svg_path}.")

    all_points = [pt for rings, _fr in per_path_rings for ring in rings for pt in ring]
    minx = min(x for x, _ in all_points)
    maxx = max(x for x, _ in all_points)
    miny = min(y for _, y in all_points)
    maxy = max(y for _, y in all_points)
    bbox_width = maxx - minx
    if bbox_width <= 0:
        raise SvgPathExtractionError(
            f"Silhouette degeneree (largeur nulle) apres tessellation de : {svg_path}."
        )
    exact_scale = width_mm / bbox_width
    height_mm = (maxy - miny) * exact_scale

    def _to_mm(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
        # Mise a l'echelle finale + passage en convention Y-up origine
        # bas-gauche (SVG est Y-down origine haut-gauche) -- meme convention
        # que `image_shape_extractor.mask_to_polygon` / `LetterGlyph.to_shapely()`.
        return [((x - minx) * exact_scale, (maxy - y) * exact_scale) for x, y in ring]

    nonzero_flat_rings: list[list[tuple[float, float]]] = []
    evenodd_polygons: list[Polygon | MultiPolygon] = []
    # Association ordonnee composant -> polygone final, pour reconstituer un
    # resultat PAR <path> (voir docstring `SvgComponentsResult`) : les
    # <path> nonzero sont classes ENSEMBLE (confinement geometrique
    # partage entre eux, approximation documentee), donc regroupes en un
    # seul "pseudo-composant" a la fin ; chaque <path> evenodd reste son
    # propre composant (XOR interne exact, independant des autres <path>).
    nonzero_present = False
    for rings, fill_rule in per_path_rings:
        rings_mm = [_to_mm(ring) for ring in rings]
        if fill_rule == "evenodd":
            polys = [Polygon(r) for r in rings_mm if len(r) >= 3]
            polys = [p.buffer(0) if not p.is_valid else p for p in polys]
            polys = [p for p in polys if not p.is_empty and p.area > 0]
            if not polys:
                continue
            combined = polys[0]
            for p in polys[1:]:
                combined = combined.symmetric_difference(p)
            if not combined.is_empty and combined.area > 0:
                evenodd_polygons.append(combined)
        else:
            nonzero_present = True
            for ring in rings_mm:
                nonzero_flat_rings.extend(_repair_self_intersecting_ring(ring))

    components: list[Polygon | MultiPolygon] = []
    if nonzero_present and nonzero_flat_rings:
        try:
            parts, _warnings = classify_contours_by_containment(
                nonzero_flat_rings, touching_hole_note="extraction SVG vectorielle"
            )
        except ContourClassificationError as exc:
            raise SvgPathExtractionError(str(exc)) from exc
        nonzero_polygons = [part.to_shapely() for part in parts]
        nonzero_polygons = [p for p in nonzero_polygons if not p.is_empty and p.area > 0]
        components.extend(nonzero_polygons)
    components.extend(evenodd_polygons)

    if not components:
        raise SvgPathExtractionError(
            f"Silhouette degeneree (aire nulle) apres extraction vectorielle de : {svg_path}."
        )

    return SvgComponentsResult(polygons=components, width_mm=width_mm, height_mm=height_mm)


def extract_polygon_from_svg(
    svg_path: str | Path,
    width_mm: float,
    *,
    max_chord_error_mm: float = _DEFAULT_MAX_CHORD_ERROR_MM,
) -> tuple[Polygon | MultiPolygon, float]:
    """Point d'entree haut niveau MODE `silhouette` : appelle
    `extract_svg_components_from_svg` (moteur de parsing/tessellation
    PARTAGE avec le mode `artwork_envelope`, voir `vector_envelope.py`) puis
    combine tous les composants par simple UNION geometrique -- aucune
    soudure/buffer, un `<path>` disjoint des autres reste disjoint dans le
    resultat (comportement historique inchange pour ce mode).

    Retourne `(polygon_mm, height_mm)`. Leve `SvgPathExtractionError` si le
    fichier est illisible, vide, sans `<path>` exploitable, ou si la
    silhouette resultante est degeneree (aire nulle)."""
    result = extract_svg_components_from_svg(
        svg_path, width_mm, max_chord_error_mm=max_chord_error_mm
    )
    polygons = result.polygons
    polygon = polygons[0] if len(polygons) == 1 else unary_union(polygons)

    if polygon.is_empty or polygon.area <= 0:
        raise SvgPathExtractionError(
            f"Silhouette degeneree (aire nulle) apres extraction vectorielle de : {svg_path}."
        )

    return polygon, result.height_mm


def extract_svg_polygon_result(
    svg_path: str | Path,
    width_mm: float,
    *,
    max_chord_error_mm: float = _DEFAULT_MAX_CHORD_ERROR_MM,
) -> SvgPolygonResult:
    """Enveloppe de `extract_polygon_from_svg` retournant un objet structure
    (meme forme que `ImageShapeResult`, sans `mask`/`threshold_used` qui
    n'ont pas de sens pour une extraction vectorielle) -- utilisee par le
    pipeline `image_lightbox_export.generate_lightbox_from_image` pour les
    sources `.svg`."""
    polygon, height_mm = extract_polygon_from_svg(
        svg_path, width_mm, max_chord_error_mm=max_chord_error_mm
    )
    return SvgPolygonResult(polygon=polygon, width_mm=width_mm, height_mm=height_mm, warnings=[])


def _segment_control_points(segment):
    """Points de controle bruts d'un segment `svgpathtools` (nombres
    complexes), utilises uniquement pour l'estimation d'echelle grossiere du
    passage 1 -- couvre `Line`/`CubicBezier`/`QuadraticBezier` (attributs
    `start`/`control1`/`control2`/`end` ou `start`/`control`/`end`) et
    `Arc` (repli sur un echantillonnage `.point(t)`, un arc n'ayant pas de
    "points de controle" au sens Bezier)."""
    for attr in ("start", "control1", "control2", "control", "end"):
        z = getattr(segment, attr, None)
        if z is not None:
            yield z
    if not any(hasattr(segment, attr) for attr in ("control1", "control")):
        # Arc ou type non reconnu : echantillonne quelques points le long du
        # segment pour une estimation de boite englobante raisonnable.
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            yield segment.point(t)
