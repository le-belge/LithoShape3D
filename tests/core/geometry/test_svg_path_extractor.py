"""Tests du parseur vectoriel SVG direct (`svg_path_extractor.py`) --
sans rasterisation prealable, extraction des courbes de Bezier exactes.

Couvre :
  - tessellation adaptative sur une courbe cubique connue (preuve que
    l'algorithme est reellement ADAPTATIF, pas juste "beaucoup de points
    partout") ;
  - application correcte d'un `transform` de groupe (translate) ;
  - gestion propre d'un SVG invalide/vide (erreur claire, pas de crash) ;
  - test de non-regression OBLIGATOIRE sur `Tesla_T_symbol.svg` (distance de
    Hausdorff au contour vectoriel "verite terrain", tessellee a une
    tolerance beaucoup plus fine)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from shapely.geometry import Polygon
from svgpathtools import CubicBezier, Line

from lithoshape3d.core.geometry.svg_path_extractor import (
    SvgPathExtractionError,
    adaptive_tessellate_segment,
    extract_polygon_from_svg,
    extract_svg_components_from_svg,
)

_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "svg"
_TESLA_SVG = _FIXTURES_DIR / "Tesla_T_symbol.svg"

_IDENTITY = __import__("numpy").eye(3)


# --------------------------------------------------------------------- #
# Tessellation adaptative -- courbe connue
# --------------------------------------------------------------------- #


def test_adaptive_tessellation_respects_chord_error_tolerance():
    """Courbe cubique tres cambree (control points loin de la corde) --
    verifie que TOUS les points produits respectent la tolerance d'erreur de
    corde demandee (aucun segment resultant ne s'ecarte de plus de `tol` de
    la vraie courbe, teste par echantillonnage dense independant)."""
    curve = CubicBezier(0 + 0j, 0 + 100j, 100 + 100j, 100 + 0j)
    tol = 0.05
    pts = adaptive_tessellate_segment(curve, _IDENTITY, tol)

    assert len(pts) >= 4  # une courbe cambree ne peut pas se resumer a 2 points

    # Verification independante : le point milieu PARAMETRIQUE de chaque
    # sous-segment produit (approx : on reechantillonne finement la courbe
    # complete et on verifie qu'aucun point dense n'est loin de la polyligne
    # obtenue de plus de quelques tolerances).
    dense_ts = [i / 2000 for i in range(2001)]
    dense_pts = [curve.point(t) for t in dense_ts]
    max_dev = 0.0
    for z in dense_pts:
        p = (z.real, z.imag)
        best = min(
            _point_to_segment_dist(p, pts[i], pts[i + 1]) for i in range(len(pts) - 1)
        )
        max_dev = max(max_dev, best)
    # tolerance x3 : marge pour l'erreur de corde vs erreur de deviation max
    # (le test de flatness porte sur le point median, pas le pire point du
    # sous-segment, mais reste borne par une petite marge constante).
    assert max_dev <= tol * 3


def _point_to_segment_dist(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def test_adaptive_tessellation_uses_fewer_points_on_near_straight_segment():
    """Sur un segment PRESQUE droit, la tessellation adaptative doit
    produire tres peu de points (2, la tolerance est immediatement
    satisfaite) -- bien moins qu'un echantillonnage a nombre fixe eleve visant
    la meme precision. Preuve que l'algorithme est adaptatif, pas uniforme."""
    # Cubique quasi-degeneree en une droite (les points de controle sont
    # presque alignes avec les extremites).
    curve = CubicBezier(0 + 0j, 33 + 0.001j, 66 + 0.001j, 100 + 0j)
    tol = 0.05
    pts = adaptive_tessellate_segment(curve, _IDENTITY, tol)

    fixed_sampling_count = 200  # tessellation naive a nombre fixe pour comparaison
    assert len(pts) < fixed_sampling_count
    assert len(pts) <= 4


def test_adaptive_tessellation_line_segment_is_always_two_points():
    """Une droite est deja "plate" par construction : la subdivision ne
    doit jamais se declencher, quelle que soit la tolerance."""
    line = Line(0 + 0j, 100 + 50j)
    pts = adaptive_tessellate_segment(line, _IDENTITY, 0.001)
    assert pts == [(0.0, 0.0), (100.0, 50.0)]


# --------------------------------------------------------------------- #
# Transform de groupe
# --------------------------------------------------------------------- #


def test_extract_polygon_from_svg_applies_group_translate_transform(tmp_path):
    """Un `<path>` enfant d'un `<g transform="translate(...)">` doit voir sa
    geometrie effectivement translatee avant mise a l'echelle -- reproduit
    la structure de `Tesla_T_symbol.svg` (`<g id="T" transform=
    "translate(-45.84,-64.297)">`)."""
    svg_no_transform = tmp_path / "square_no_transform.svg"
    svg_no_transform.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
        '<path d="M 0,0 L 100,0 L 100,100 L 0,100 Z" /></svg>'
    )
    svg_with_transform = tmp_path / "square_with_transform.svg"
    svg_with_transform.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
        '<g transform="translate(500,-300)">'
        '<path d="M 0,0 L 100,0 L 100,100 L 0,100 Z" /></g></svg>'
    )

    poly_plain, height_plain = extract_polygon_from_svg(str(svg_no_transform), 40.0)
    poly_translated, height_translated = extract_polygon_from_svg(str(svg_with_transform), 40.0)

    # Une translation globale ne doit rien changer a la FORME resultante
    # (le polygone est toujours recadre/mis a l'echelle depuis sa propre
    # boite englobante) : les deux doivent produire un carre identique.
    assert poly_plain.equals_exact(poly_translated, tolerance=1e-6)
    assert height_plain == pytest.approx(height_translated, abs=1e-9)
    assert height_plain == pytest.approx(40.0, abs=1e-6)


def test_extract_polygon_from_svg_group_transform_scale_and_rotate(tmp_path):
    """Un `matrix(...)`/`scale(...)` sur le groupe doit changer l'ASPECT
    (rapport largeur/hauteur) du polygone resultant si la transformation
    n'est pas isotrope -- verifie que la matrice n'est pas ignoree."""
    svg_square = tmp_path / "square.svg"
    svg_square.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
        '<path d="M 0,0 L 10,0 L 10,10 L 0,10 Z" /></svg>'
    )
    svg_stretched = tmp_path / "stretched.svg"
    svg_stretched.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
        '<g transform="scale(1,3)">'
        '<path d="M 0,0 L 10,0 L 10,10 L 0,10 Z" /></g></svg>'
    )

    _poly_square, h_square = extract_polygon_from_svg(str(svg_square), 50.0)
    _poly_stretched, h_stretched = extract_polygon_from_svg(str(svg_stretched), 50.0)

    assert h_square == pytest.approx(50.0, abs=1e-6)
    assert h_stretched == pytest.approx(150.0, abs=1e-6)


# --------------------------------------------------------------------- #
# Erreurs
# --------------------------------------------------------------------- #


def test_extract_polygon_from_svg_missing_file_raises_clear_error():
    with pytest.raises(SvgPathExtractionError):
        extract_polygon_from_svg("/no/such/file/here.svg", 50.0)


def test_extract_polygon_from_svg_no_path_element_raises_clear_error(tmp_path):
    svg_empty = tmp_path / "empty.svg"
    svg_empty.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>')
    with pytest.raises(SvgPathExtractionError, match="Aucun element"):
        extract_polygon_from_svg(str(svg_empty), 50.0)


def test_extract_polygon_from_svg_degenerate_bbox_raises_clear_error(tmp_path):
    """Un chemin reduit a un point (largeur nulle) doit lever une erreur
    explicite, pas produire une division par zero silencieuse."""
    svg_point = tmp_path / "point.svg"
    svg_point.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
        '<path d="M 5,5 L 5,5 Z" /></svg>'
    )
    with pytest.raises(SvgPathExtractionError):
        extract_polygon_from_svg(str(svg_point), 50.0)


def test_extract_polygon_from_svg_invalid_width_mm_raises():
    with pytest.raises(ValueError):
        extract_polygon_from_svg(str(_TESLA_SVG), 0.0)
    with pytest.raises(ValueError):
        extract_polygon_from_svg(str(_TESLA_SVG), -10.0)


def test_extract_polygon_from_svg_invalid_chord_error_raises():
    with pytest.raises(ValueError):
        extract_polygon_from_svg(str(_TESLA_SVG), 50.0, max_chord_error_mm=0.0)


# --------------------------------------------------------------------- #
# Regression : contamination croisee entre <path> nonzero independants
# (diagnostic Cherry Moon -- voir examples/physical_validation/
# cherry_moon_source/pipeline_debug/) et ilots imbriques a profondeur > 1.
# --------------------------------------------------------------------- #


def test_two_independent_nonzero_paths_do_not_hole_each_other(tmp_path):
    """Un `<path>` B geometriquement CONTENU dans la bbox/aire d'un `<path>`
    A independant ne doit JAMAIS devenir un trou de A -- la regle
    `fill-rule` (nonzero par defaut) ne s'applique QU'AUX sous-chemins d'un
    MEME `<path>`. Reproduit le bug reel trouve sur Cherry Moon : le "O"
    d'un `<path>` independant etait absorbe comme trou parasite (216.98
    mm2) dans le demi-disque d'un autre `<path>`, simplement parce que son
    centre tombait geometriquement dedans."""
    svg = tmp_path / "cross_path.svg"
    # Path A : grand carre 0..100. Path B : petit cercle (approx octogone)
    # centre en (50,50), entierement contenu dans A -- mais un <path> SEPARE.
    square = "M 0,0 L 100,0 L 100,100 L 0,100 Z"
    circle = "M 60,50 L 57,57 L 50,60 L 43,57 L 40,50 L 43,43 L 50,40 L 57,43 Z"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
        f'<path d="{square}" /><path d="{circle}" /></svg>'
    )

    result = extract_svg_components_from_svg(str(svg), 100.0)

    assert len(result.polygons) == 2, "Les deux <path> doivent rester deux composantes SOLIDES distinctes."
    for poly in result.polygons:
        holes = list(poly.interiors) if poly.geom_type == "Polygon" else []
        assert len(holes) == 0, "Aucun des deux <path> ne doit avoir de trou -- ils sont independants."


def test_nested_island_within_hole_becomes_separate_solid_component(tmp_path):
    """Un `<path>` avec 3 sous-chemins imbriques (exterieur plein, trou,
    ilot plein A L'INTERIEUR DU TROU -- profondeur 2) doit produire DEUX
    composantes solides valides : l'exterieur avec son trou, ET l'ilot
    comme composante separee -- pas un trou de plus qui grignoterait
    l'exterieur (limitation de l'ancien algorithme a un seul niveau
    racine/trou, corrigee dans `classify_contours_by_containment`)."""
    svg = tmp_path / "nested_island.svg"
    outer = "M 0,0 L 100,0 L 100,100 L 0,100 Z"
    hole = "M 20,20 L 80,20 L 80,80 L 20,80 Z"
    island = "M 40,40 L 60,40 L 60,60 L 40,60 Z"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
        f'<path d="{outer} {hole} {island}" /></svg>'
    )

    result = extract_svg_components_from_svg(str(svg), 100.0)

    assert len(result.polygons) == 2
    areas = sorted((p.area for p in result.polygons), reverse=True)
    # exterieur (100x100 - trou 60x60) = 6400, ilot (20x20) = 400.
    assert areas[0] == pytest.approx(6400.0, rel=1e-6)
    assert areas[1] == pytest.approx(400.0, rel=1e-6)
    outer_poly = max(result.polygons, key=lambda p: p.area)
    island_poly = min(result.polygons, key=lambda p: p.area)
    assert len(outer_poly.interiors) == 1
    assert len(island_poly.interiors) == 0


# --------------------------------------------------------------------- #
# Non-regression Tesla_T_symbol.svg -- distance de Hausdorff a la
# reference haute-fidelite (tolerance de subdivision beaucoup plus fine)
# --------------------------------------------------------------------- #

_TESLA_WIDTH_MM = 100.0
_DEFAULT_CHORD_ERROR_MM = 0.08
_REFERENCE_CHORD_ERROR_MM = 0.001
# Tolerance geometrique maximale acceptee entre le polygone "production"
# (tolerance par defaut, 0.08mm) et la reference haute-fidelite (0.001mm) :
# choisie a 10x la tolerance de production -- large marge de securite (la
# distance de Hausdorff reelle mesuree est bien en-dessous, voir assertion
# et rapport de session), mais un seuil qui DETECTE reellement une
# regression grossiere (ex. un retour accidentel a une tessellation a pas
# fixe grossier, ou une mauvaise application de transform) plutot qu'un
# controle qui passe par construction.
_MAX_HAUSDORFF_MM = _DEFAULT_CHORD_ERROR_MM * 10


@pytest.mark.skipif(not _TESLA_SVG.exists(), reason="fixture Tesla_T_symbol.svg absente")
def test_tesla_svg_extraction_matches_high_fidelity_reference_within_tolerance():
    production_polygon, _h1 = extract_polygon_from_svg(
        str(_TESLA_SVG), _TESLA_WIDTH_MM, max_chord_error_mm=_DEFAULT_CHORD_ERROR_MM
    )
    reference_polygon, _h2 = extract_polygon_from_svg(
        str(_TESLA_SVG), _TESLA_WIDTH_MM, max_chord_error_mm=_REFERENCE_CHORD_ERROR_MM
    )

    hausdorff = production_polygon.hausdorff_distance(reference_polygon)

    assert hausdorff <= _MAX_HAUSDORFF_MM, (
        f"Distance de Hausdorff {hausdorff:.4f}mm entre l'extraction production "
        f"(tol={_DEFAULT_CHORD_ERROR_MM}mm) et la reference haute-fidelite "
        f"(tol={_REFERENCE_CHORD_ERROR_MM}mm) depasse la tolerance de "
        f"{_MAX_HAUSDORFF_MM}mm."
    )
    # Les deux extractions doivent rester la MEME silhouette globale (aire
    # comparable) -- un ecart d'aire important indiquerait une classification
    # de contour differente (ex. un morceau perdu), pas juste une difference
    # de finesse de tessellation.
    area_ratio = production_polygon.area / reference_polygon.area
    assert area_ratio == pytest.approx(1.0, abs=0.01)


def test_tesla_svg_production_tessellation_is_actually_coarser_than_reference():
    """Preuve que le test ci-dessus peut reellement ECHOUER (pas un test qui
    passe par construction) : la tessellation `production` doit avoir
    nettement MOINS de sommets que la reference haute-fidelite -- si elles
    avaient le meme nombre de sommets, `max_chord_error_mm` serait ignore et
    la comparaison de Hausdorff serait triviale."""
    production_polygon, _ = extract_polygon_from_svg(
        str(_TESLA_SVG), _TESLA_WIDTH_MM, max_chord_error_mm=_DEFAULT_CHORD_ERROR_MM
    )
    reference_polygon, _ = extract_polygon_from_svg(
        str(_TESLA_SVG), _TESLA_WIDTH_MM, max_chord_error_mm=_REFERENCE_CHORD_ERROR_MM
    )

    def _vertex_count(poly):
        geoms = poly.geoms if poly.geom_type == "MultiPolygon" else [poly]
        return sum(len(g.exterior.coords) for g in geoms)

    assert _vertex_count(production_polygon) < _vertex_count(reference_polygon)


def test_tesla_svg_result_matches_expected_tesla_t_silhouette():
    """Sanity check visuel automatise : la silhouette extraite doit couvrir
    une fraction d'aire de sa boite englobante coherente avec un logo "T"
    (ni un rectangle plein -- bug historique rapporte ou tout le canevas
    devenait "encre" -- ni une silhouette quasi-vide)."""
    polygon, height_mm = extract_polygon_from_svg(str(_TESLA_SVG), _TESLA_WIDTH_MM)
    minx, miny, maxx, maxy = polygon.bounds
    bbox_area = (maxx - minx) * (maxy - miny)
    coverage = polygon.area / bbox_area

    assert 0.15 < coverage < 0.85
    assert 50.0 < height_mm < 150.0
