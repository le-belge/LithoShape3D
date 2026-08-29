"""Verification MESUREE (pas "a l'oeil") de la refonte "source de verite
vectorielle unique" pour une source `.svg`, sur 7 cas geometriques distincts
(cercle parfait, Tesla, Cherry Moon, concave, Bezier prononcee, trou/anneau,
asymetrique) -- voir la tache "LightBox depuis image / SVG vectoriel".

Pour chaque cas :
  - distance de Hausdorff entre le contour "production" (tolerance de corde
    par defaut, 0.08mm) et une reference haute-fidelite du MEME SVG
    (tolerance 0.001mm) -- meme methodologie que le test de non-regression
    Tesla deja existant (`test_svg_path_extractor.py`) ;
  - aire, bounding box, nombre de composantes connexes, nombre de trous,
    validite Shapely (`is_valid`) ;
  - mode `silhouette` (`extract_polygon_from_svg`) ET mode `artwork_envelope`
    (`extract_artwork_from_svg`, moteur PARTAGE + soudure vectorielle
    generique -- verifie explicitement que le contour d'ENCRE (`ink_polygon`,
    fidele) reste geometriquement identique au contour `silhouette` pour le
    MEME fichier, la seule difference etant l'`envelope_polygon` (soude)."""

from __future__ import annotations

from pathlib import Path

import pytest
from shapely.geometry import Polygon

from lithoshape3d.core.geometry.artwork_shape_extractor import extract_artwork_from_svg
from lithoshape3d.core.geometry.svg_path_extractor import extract_polygon_from_svg

_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "svg"
_EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "examples" / "physical_validation"

_TESLA_SVG = _FIXTURES_DIR / "Tesla_T_symbol.svg"
_CHERRY_MOON_SVG = _EXAMPLES_DIR / "cherry_moon_source" / "cherry_moon.svg"

_PRODUCTION_CHORD_ERROR_MM = 0.08
_REFERENCE_CHORD_ERROR_MM = 0.001
_WIDTH_MM = 100.0


def _num_components(poly) -> int:
    return len(poly.geoms) if poly.geom_type == "MultiPolygon" else 1


def _num_holes(poly) -> int:
    geoms = poly.geoms if poly.geom_type == "MultiPolygon" else [poly]
    return sum(len(g.interiors) for g in geoms)


# --------------------------------------------------------------------- #
# Fixtures SVG synthetiques (generes en memoire, pas de fichier externe)
# --------------------------------------------------------------------- #


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">{body}</svg>')
    return path


def _circle_svg(tmp_path: Path) -> Path:
    # Cercle approxime par 4 arcs elliptiques `A` (rayon 80, centre 100,100).
    d = "M 180,100 A 80,80 0 1 1 20,100 A 80,80 0 1 1 180,100 Z"
    return _write(tmp_path, "circle.svg", f'<path d="{d}" />')


def _star_svg(tmp_path: Path) -> Path:
    # Etoile a 5 branches (forme CONCAVE) -- points alternes rayon 90/35.
    import math

    cx, cy = 100.0, 100.0
    pts = []
    for i in range(10):
        r = 90.0 if i % 2 == 0 else 35.0
        angle = math.pi / 2 + i * math.pi / 5
        pts.append((cx + r * math.cos(angle), cy - r * math.sin(angle)))
    d = "M " + " L ".join(f"{x:.3f},{y:.3f}" for x, y in pts) + " Z"
    return _write(tmp_path, "star.svg", f'<path d="{d}" />')


def _bezier_svg(tmp_path: Path) -> Path:
    # Grande courbe cambree (control points tres eloignes de la corde) fermee
    # par une droite -- forme a Bezier prononcee.
    d = "M 20,150 C 20,10 180,10 180,150 L 20,150 Z"
    return _write(tmp_path, "bezier.svg", f'<path d="{d}" />')


def _ring_svg(tmp_path: Path) -> Path:
    # Anneau : deux <path> nonzero de sens de parcours OPPOSE (exterieur
    # horaire, interieur anti-horaire) -- classification par confinement
    # geometrique attendue : cercle interieur = trou.
    outer = "M 180,100 A 80,80 0 1 1 20,100 A 80,80 0 1 1 180,100 Z"
    inner = "M 140,100 A 40,40 0 1 0 60,100 A 40,40 0 1 0 140,100 Z"
    return _write(tmp_path, "ring.svg", f'<path d="{outer}" /><path d="{inner}" />')


def _asymmetric_svg(tmp_path: Path) -> Path:
    # Polygone quelconque sans aucune symetrie, melange droites/Bezier.
    d = "M 10,10 L 150,20 C 190,40 170,120 120,140 L 60,190 L 20,120 Z"
    return _write(tmp_path, "asymmetric.svg", f'<path d="{d}" />')


_SYNTHETIC_CASES = {
    "cercle_parfait": _circle_svg,
    "etoile_concave": _star_svg,
    "bezier_prononcee": _bezier_svg,
    "anneau_avec_trou": _ring_svg,
    "forme_asymetrique": _asymmetric_svg,
}


# --------------------------------------------------------------------- #
# Matrice de non-regression -- mode silhouette (moteur de base)
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("case_name", list(_SYNTHETIC_CASES.keys()))
def test_silhouette_synthetic_case_matches_high_fidelity_reference(tmp_path, case_name):
    svg_path = _SYNTHETIC_CASES[case_name](tmp_path)

    production, h_prod = extract_polygon_from_svg(
        str(svg_path), _WIDTH_MM, max_chord_error_mm=_PRODUCTION_CHORD_ERROR_MM
    )
    reference, h_ref = extract_polygon_from_svg(
        str(svg_path), _WIDTH_MM, max_chord_error_mm=_REFERENCE_CHORD_ERROR_MM
    )

    hausdorff = production.hausdorff_distance(reference)
    max_allowed = _PRODUCTION_CHORD_ERROR_MM * 10

    assert production.is_valid, f"{case_name}: polygone production invalide"
    assert reference.is_valid, f"{case_name}: polygone reference invalide"
    assert hausdorff <= max_allowed, (
        f"{case_name}: Hausdorff {hausdorff:.4f}mm depasse la tolerance {max_allowed}mm"
    )
    assert production.area == pytest.approx(reference.area, rel=0.02), (
        f"{case_name}: aires production/reference divergentes "
        f"({production.area:.2f} vs {reference.area:.2f})"
    )
    assert production.bounds == pytest.approx(reference.bounds, abs=max_allowed), (
        f"{case_name}: bounding boxes production/reference divergentes"
    )
    assert _num_components(production) == _num_components(reference), f"{case_name}: nb composantes"
    assert _num_holes(production) == _num_holes(reference), f"{case_name}: nb trous"
    assert h_prod == pytest.approx(h_ref, abs=max_allowed), f"{case_name}: hauteur mm"


def test_ring_synthetic_case_has_exactly_one_hole():
    """Sanity check dedie a la fixture 'anneau' : preuve que le trou est
    effectivement detecte (pas juste un test qui passerait meme sans trou)."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        svg_path = _ring_svg(Path(tmp))
        polygon, _h = extract_polygon_from_svg(str(svg_path), _WIDTH_MM)
        assert _num_holes(polygon) == 1
        assert _num_components(polygon) == 1


def test_star_synthetic_case_is_actually_concave():
    """Sanity check dedie a la fixture 'etoile' : preuve que la forme est
    reellement concave (aire << aire de son enveloppe convexe)."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        svg_path = _star_svg(Path(tmp))
        polygon, _h = extract_polygon_from_svg(str(svg_path), _WIDTH_MM)
        convex_area = polygon.convex_hull.area
        assert polygon.area < convex_area * 0.7


# --------------------------------------------------------------------- #
# Matrice de non-regression -- Tesla / Cherry Moon (fichiers reels)
# --------------------------------------------------------------------- #


@pytest.mark.skipif(not _TESLA_SVG.exists(), reason="fixture Tesla_T_symbol.svg absente")
def test_tesla_silhouette_matches_high_fidelity_reference():
    production, _h1 = extract_polygon_from_svg(
        str(_TESLA_SVG), _WIDTH_MM, max_chord_error_mm=_PRODUCTION_CHORD_ERROR_MM
    )
    reference, _h2 = extract_polygon_from_svg(
        str(_TESLA_SVG), _WIDTH_MM, max_chord_error_mm=_REFERENCE_CHORD_ERROR_MM
    )
    hausdorff = production.hausdorff_distance(reference)
    assert hausdorff <= _PRODUCTION_CHORD_ERROR_MM * 10
    assert production.area == pytest.approx(reference.area, rel=0.01)
    assert production.is_valid and reference.is_valid


@pytest.mark.skipif(not _CHERRY_MOON_SVG.exists(), reason="fixture cherry_moon.svg absente")
def test_cherry_moon_silhouette_matches_high_fidelity_reference():
    production, _h1 = extract_polygon_from_svg(
        str(_CHERRY_MOON_SVG), _WIDTH_MM, max_chord_error_mm=_PRODUCTION_CHORD_ERROR_MM
    )
    reference, _h2 = extract_polygon_from_svg(
        str(_CHERRY_MOON_SVG), _WIDTH_MM, max_chord_error_mm=_REFERENCE_CHORD_ERROR_MM
    )
    hausdorff = production.hausdorff_distance(reference)
    assert hausdorff <= _PRODUCTION_CHORD_ERROR_MM * 10
    assert production.area == pytest.approx(reference.area, rel=0.01)
    assert production.is_valid and reference.is_valid


# --------------------------------------------------------------------- #
# Moteur PARTAGE silhouette <-> artwork_envelope : le contour d'ENCRE
# (fidele, non-soude) de artwork_envelope doit rester geometriquement
# identique au contour silhouette du MEME fichier -- preuve directe que les
# deux modes partagent la meme source de verite geometrique.
# --------------------------------------------------------------------- #


@pytest.mark.skipif(not _TESLA_SVG.exists(), reason="fixture Tesla_T_symbol.svg absente")
def test_tesla_artwork_ink_polygon_matches_silhouette_polygon_exactly():
    silhouette_polygon, _h = extract_polygon_from_svg(str(_TESLA_SVG), _WIDTH_MM)
    artwork = extract_artwork_from_svg(str(_TESLA_SVG), _WIDTH_MM)

    # Meme moteur de tessellation -> meme geometrie EXACTE (a la precision
    # flottante pres), pas juste "proche" : preuve la plus directe possible
    # que silhouette et artwork_envelope partagent une source de verite
    # geometrique UNIQUE pour une source .svg.
    assert artwork.ink_polygon.equals_exact(silhouette_polygon, tolerance=1e-9)
    assert artwork.ink_polygon.area == pytest.approx(silhouette_polygon.area, rel=1e-9)


@pytest.mark.skipif(not _CHERRY_MOON_SVG.exists(), reason="fixture cherry_moon.svg absente")
def test_cherry_moon_artwork_ink_polygon_matches_silhouette_polygon_exactly():
    silhouette_polygon, _h = extract_polygon_from_svg(str(_CHERRY_MOON_SVG), _WIDTH_MM)
    artwork = extract_artwork_from_svg(str(_CHERRY_MOON_SVG), _WIDTH_MM)

    assert artwork.ink_polygon.equals_exact(silhouette_polygon, tolerance=1e-9)


@pytest.mark.skipif(not _CHERRY_MOON_SVG.exists(), reason="fixture cherry_moon.svg absente")
def test_a_toggling_envelope_computation_leaves_ink_polygon_bit_identical():
    """TEST A (exige explicitement) : le calcul de l'enveloppe (contour
    exterieur physique, soude) ne doit produire AUCUNE difference sur la
    geometrie d'encre (ArtworkGeometry). Verifie par les DEUX metriques
    demandees : distance de Hausdorff ET aire de la difference symetrique
    Shapely -- pas seulement "proche", mais ~0 exactement."""
    from shapely.ops import unary_union

    from lithoshape3d.core.geometry.svg_path_extractor import extract_svg_components_from_svg

    artwork = extract_artwork_from_svg(str(_CHERRY_MOON_SVG), _WIDTH_MM)
    ink_via_full_pipeline = artwork.ink_polygon

    # "ink avant" : union directe des composantes brutes, SANS aucun calcul
    # d'enveloppe/soudure (chemin de code totalement independant).
    raw_components = extract_svg_components_from_svg(str(_CHERRY_MOON_SVG), _WIDTH_MM).polygons
    ink_without_envelope = unary_union(raw_components)

    hausdorff = ink_via_full_pipeline.hausdorff_distance(ink_without_envelope)
    sym_diff_area = ink_via_full_pipeline.symmetric_difference(ink_without_envelope).area

    assert hausdorff == pytest.approx(0.0, abs=1e-9)
    assert sym_diff_area == pytest.approx(0.0, abs=1e-6)


@pytest.mark.skipif(not _CHERRY_MOON_SVG.exists(), reason="fixture cherry_moon.svg absente")
def test_b_only_the_physical_exterior_contour_changes_between_ink_and_envelope():
    """TEST B (exige explicitement) : seul le contour physique EXTERIEUR du
    caisson doit changer entre `ink_polygon` (fidele) et `envelope_polygon`
    (soude) -- pas la geometrie interieure. Verifie que l'enveloppe
    CONTIENT integralement l'encre (aucune partie de l'encre n'est
    deplacee/deformee vers l'exterieur de l'enveloppe) et que l'aire
    ajoutee par la soudure est strictement positive (comportement attendu :
    l'enveloppe comble les ecarts entre composantes disjointes)."""
    artwork = extract_artwork_from_svg(str(_CHERRY_MOON_SVG), _WIDTH_MM)

    ink_outside_envelope = artwork.ink_polygon.difference(artwork.envelope_polygon)
    # Tolerance non-triviale (0.1mm2) mais toujours >3 ordres de grandeur
    # sous l'aire totale de l'encre (~4759mm2) : le buffer +d/-d de la
    # soudure laisse un bruit numerique negligeable (esquilles flottantes
    # sub-pixel) le long du contour, sans rapport avec une perte reelle de
    # detail (voir diagnostic complet, pipeline_debug/metrics.json).
    assert ink_outside_envelope.area == pytest.approx(0.0, abs=0.1), (
        "De l'encre existe hors de l'enveloppe -- l'enveloppe ne devrait qu'AJOUTER de la "
        "matiere (soudure), jamais deplacer/perdre de l'encre existante."
    )
    assert artwork.envelope_polygon.area > artwork.ink_polygon.area


def test_ring_artwork_envelope_does_not_fill_the_legitimate_hole():
    """Garde-fou explicite demande : la soudure vectorielle de
    `artwork_envelope` (buffer +d/-d) ne doit PAS combler un trou legitime
    (ici : l'interieur d'un anneau, dimension caracteristique tres
    superieure a l'ecart -- inexistant ici, une seule composante -- entre
    composantes)."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        svg_path = _ring_svg(Path(tmp))
        artwork = extract_artwork_from_svg(str(svg_path), _WIDTH_MM)
        assert _num_holes(artwork.envelope_polygon) == 1, (
            "Le trou interne de l'anneau a ete comble par la soudure vectorielle -- regression."
        )
        assert artwork.weld_distance_mm == 0.0  # une seule composante : rien a souder
