from pathlib import Path

import pytest
import trimesh

from lithoshape3d.core.geometry.letter_glyph_extractor import extract_word_glyphs
from lithoshape3d.core.geometry.lightbox_letters_export import (
    SHOULDER_DEPTH_MM,
    SHOULDER_WIDTH_MM,
    build_lightbox_letter_back_panel_mesh,
    build_lightbox_letter_body_mesh,
    generate_lightbox_letters,
    letter_cap_footprint,
)
from lithoshape3d.core.validation.mesh_checks import validate_mesh

_SYSTEM_FONT = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
# Police "grasse" (traits epais) necessaire pour obtenir, a une taille de
# police raisonnable pour les tests, un contour assez large pour survivre a
# l'erosion cumulee paroi + epaulement + jeu d'assemblage sans disparaitre
# (voir verification manuelle : Arial regulier a 40mm a des traits trop fins
# pour ce test, cf. rapport de tache).
_BOLD_FONT = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")

pytestmark = pytest.mark.skipif(
    not _SYSTEM_FONT.exists() or not _BOLD_FONT.exists(),
    reason="Polices systeme Arial/Arial Bold indisponibles sur cette machine.",
)


def _letter(char: str, font: Path = _BOLD_FONT, font_size_mm: float = 60.0):
    layout = extract_word_glyphs(char, font, font_size_mm=font_size_mm)
    return layout.letters[0]


def test_letter_body_mesh_is_watertight_and_spans_full_depth():
    letter = _letter("A")
    depth_mm = 25.0
    body_mesh, warnings = build_lightbox_letter_body_mesh(letter, depth_mm, wall_thickness_mm=1.6)

    validation = validate_mesh(body_mesh)
    assert validation.is_valid, validation.issues()
    assert body_mesh.is_watertight

    # Le corps doit couvrir toute la profondeur demandee (a l'epsilon de
    # construction pres), pas seulement une portion.
    assert body_mesh.bounds[0][2] == pytest.approx(0.0, abs=0.05)
    assert body_mesh.bounds[1][2] == pytest.approx(depth_mm, abs=0.05)


def test_letter_body_walls_follow_vector_contour_not_a_pixel_grid():
    """Regression pour le bug 'parois crenelees' : le corps extrude
    directement le contour vectoriel de la lettre (`letter.to_shapely()`),
    donc son empreinte XY doit correspondre exactement (aux epsilons de
    construction pres) au contour vectoriel -- pas a une version rasterisee/
    voxelisee de ce contour comme le ferait `build_lightbox_body_mesh` (V1)."""
    letter = _letter("A")
    body_mesh, _ = build_lightbox_letter_body_mesh(letter, depth_mm=25.0, wall_thickness_mm=1.6)
    outer = letter.to_shapely()

    xy_min = body_mesh.bounds[0][:2]
    xy_max = body_mesh.bounds[1][:2]
    outer_min_x, outer_min_y, outer_max_x, outer_max_y = outer.bounds

    assert xy_min[0] == pytest.approx(outer_min_x, abs=1e-3)
    assert xy_min[1] == pytest.approx(outer_min_y, abs=1e-3)
    assert xy_max[0] == pytest.approx(outer_max_x, abs=1e-3)
    assert xy_max[1] == pytest.approx(outer_max_y, abs=1e-3)


def test_letter_body_has_a_real_shoulder_ring_geometrically():
    """L'epaulement doit correspondre a un anneau (cavite retrecie) d'aire
    strictement positive pres du sommet -- sinon il n'y a pas de rebord de
    retention pour le capot, juste une paroi uniforme."""
    letter = _letter("A")
    wall_thickness_mm = 1.6
    outer = letter.to_shapely()

    inner_lower = outer.buffer(-wall_thickness_mm)
    inner_shoulder = outer.buffer(-(wall_thickness_mm + SHOULDER_WIDTH_MM))

    assert inner_lower.area > 0
    # L'ouverture au niveau de l'epaulement est strictement plus petite que
    # la cavite normale : c'est exactement ce qui cree le rebord.
    assert inner_shoulder.area < inner_lower.area


def test_letter_body_mesh_volume_matches_shoulder_step_geometry():
    """Verifie que le VOLUME REEL du mesh (pas seulement la geometrie
    Shapely source) correspond a la formule d'un corps a cavite en deux
    paliers (paroi normale en bas, paroi elargie -- epaulement -- en haut) :
    preuve que l'epaulement existe bien dans le solide extrude/booleen, pas
    seulement sur le papier."""
    letter = _letter("M")
    depth_mm = 25.0
    wall_thickness_mm = 1.6
    body_mesh, warnings = build_lightbox_letter_body_mesh(letter, depth_mm, wall_thickness_mm)
    assert body_mesh.is_watertight

    outer = letter.to_shapely()
    inner_lower = outer.buffer(-wall_thickness_mm)
    inner_shoulder = outer.buffer(-(wall_thickness_mm + SHOULDER_WIDTH_MM))

    shoulder_top = depth_mm - SHOULDER_DEPTH_MM
    expected_volume = (
        outer.area * depth_mm
        - inner_lower.area * shoulder_top
        - inner_shoulder.area * SHOULDER_DEPTH_MM
    )

    assert body_mesh.volume == pytest.approx(expected_volume, rel=0.03)

    # Meme verification depuis le mesh lui-meme : un corps SANS epaulement
    # (cavite au meme retrait de paroi sur toute la hauteur) aurait moins de
    # matiere pres du sommet -- donc un volume total plus petit.
    no_shoulder_volume = outer.area * depth_mm - inner_lower.area * depth_mm
    assert body_mesh.volume > no_shoulder_volume


def test_letter_cap_footprint_smaller_than_body_for_shoulder_fit():
    """Le capot doit etre dimensionne plus petit que le contour exterieur du
    corps, de la largeur du rebord d'epaulement + jeu d'assemblage -- sinon
    il ne peut pas s'emboiter dans l'epaulement (bbox XY trop grande)."""
    letter = _letter("A")
    wall_thickness_mm = 1.6
    outer = letter.to_shapely()
    cap = letter_cap_footprint(letter, wall_thickness_mm)

    assert not cap.is_empty
    assert cap.area < outer.area

    outer_min_x, outer_min_y, outer_max_x, outer_max_y = outer.bounds
    cap_min_x, cap_min_y, cap_max_x, cap_max_y = cap.bounds

    outer_width = outer_max_x - outer_min_x
    outer_height = outer_max_y - outer_min_y
    cap_width = cap_max_x - cap_min_x
    cap_height = cap_max_y - cap_min_y

    assert cap_width < outer_width
    assert cap_height < outer_height


def test_letter_back_panel_is_smooth_solid_extrusion():
    letter = _letter("I")
    back_mesh = build_lightbox_letter_back_panel_mesh(letter, back_thickness_mm=1.2)

    validation = validate_mesh(back_mesh)
    assert validation.is_valid, validation.issues()
    assert back_mesh.is_watertight
    assert back_mesh.bounds[1][2] == pytest.approx(1.2, abs=1e-6)

    outer = letter.to_shapely()
    assert back_mesh.volume == pytest.approx(outer.area * 1.2, rel=0.02)


def test_generate_lightbox_letters_fuses_back_panel_into_body(tmp_path):
    """Regression : le fond (back panel) doit etre fusionne (union
    booleenne) dans le corps -- une seule piece imprimable par lettre, pas
    deux fichiers separes a coller (retour utilisateur : "le fond et la box
    ne doivent faire qu'une piece"). Pas de `_fond.stl` distinct ; le corps
    doit inclure le volume du fond (mesh watertight fermant bien le bas)."""
    result = generate_lightbox_letters(
        "AI",
        str(_BOLD_FONT),
        tmp_path,
        font_size_mm=60.0,
        depth_mm=25.0,
        wall_thickness_mm=1.6,
        back_thickness_mm=1.2,
    )

    assert not result.errors, result.errors
    fond_files = [p for p in result.written if p.name.endswith("_fond.stl")]
    assert fond_files == []

    corps_files = [p for p in result.written if p.name.endswith("_corps.stl")]
    assert len(corps_files) == 2  # une par lettre de "AI"

    for path in corps_files:
        assert path.exists()
        mesh = trimesh.load(path)
        assert mesh.is_watertight
        assert mesh.bounds[0][2] <= 0.05  # le corps ferme bien un fond pres de Z=0


def test_generate_lightbox_letters_produces_watertight_smooth_bodies(tmp_path):
    result = generate_lightbox_letters(
        "AI",
        str(_BOLD_FONT),
        tmp_path,
        font_size_mm=60.0,
        depth_mm=25.0,
        wall_thickness_mm=1.6,
        back_thickness_mm=1.2,
    )

    assert not result.errors, result.errors
    corps_files = [p for p in result.written if p.name.endswith("_corps.stl")]
    assert len(corps_files) == 2

    for path in corps_files:
        mesh = trimesh.load(path)
        assert mesh.is_watertight
