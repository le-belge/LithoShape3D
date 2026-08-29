from pathlib import Path

import pytest

from lithoshape3d.core.geometry.letter_glyph_extractor import (
    GlyphExtractionError,
    extract_word_glyphs,
    rasterize_letter_mask,
)

_SYSTEM_FONT = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
# Police macOS avec un "0" (zero barre) dont l'anneau interne touche
# reellement l'anneau externe au niveau de la barre oblique -- trouvee par
# balayage systematique de toutes les polices systeme macOS (Supplemental +
# Fonts) sur les caracteres alphanumeriques + quelques symboles, en cherchant
# un `shapely.Polygon(exterieur, holes=[...])` invalide apres classification
# par confinement geometrique. Resultat : `Andale Mono.ttf` / '0' produit un
# vrai cas degenere ("Holes are nested"), reproduit et fixe par
# `test_hole_touching_exterior_is_repaired_on_real_font` ci-dessous.
_TOUCHING_HOLE_FONT = Path("/System/Library/Fonts/Supplemental/Andale Mono.ttf")

pytestmark = pytest.mark.skipif(
    not _SYSTEM_FONT.exists(), reason="Police systeme Arial.ttf indisponible sur cette machine."
)


def test_letter_without_hole():
    layout = extract_word_glyphs("F", _SYSTEM_FONT, font_size_mm=20.0)
    letter = layout.letters[0]
    assert letter.character == "F"
    assert letter.holes == []
    assert len(letter.exterior) >= 3


def test_letter_with_one_hole():
    layout = extract_word_glyphs("A", _SYSTEM_FONT, font_size_mm=20.0)
    letter = layout.letters[0]
    assert letter.character == "A"
    assert len(letter.holes) == 1


def test_letter_with_two_holes():
    layout = extract_word_glyphs("B", _SYSTEM_FONT, font_size_mm=20.0)
    letter = layout.letters[0]
    assert letter.character == "B"
    assert len(letter.holes) == 2


def test_word_layout_keeps_absolute_positions_not_recentered():
    layout = extract_word_glyphs("FAB", _SYSTEM_FONT, font_size_mm=20.0)
    f_letter, a_letter, b_letter = layout.letters
    # Positions absolues croissantes : chaque lettre suit la precedente,
    # aucune n'est recentree individuellement autour de zero.
    assert f_letter.bbox_mm[0] < a_letter.bbox_mm[0] < b_letter.bbox_mm[0]
    assert f_letter.bbox_mm[0] > 0.0  # F n'est pas replace en x=0


def test_missing_glyph_in_font_raises_clear_error():
    with pytest.raises(GlyphExtractionError, match="absent de la police"):
        extract_word_glyphs("あ", _SYSTEM_FONT, font_size_mm=20.0)


def test_missing_font_file_raises_clear_error(tmp_path):
    with pytest.raises(GlyphExtractionError, match="introuvable"):
        extract_word_glyphs("A", tmp_path / "does_not_exist.ttf", font_size_mm=20.0)


def test_empty_text_raises_value_error():
    with pytest.raises(ValueError, match="vide"):
        extract_word_glyphs("", _SYSTEM_FONT, font_size_mm=20.0)


def test_rasterize_letter_mask_matches_shape_at_canvas_scale():
    layout = extract_word_glyphs("A", _SYSTEM_FONT, font_size_mm=20.0)
    letter = layout.letters[0]
    rows, cols = 100, 100
    mask = rasterize_letter_mask(letter, layout.width_mm, layout.width_mm, rows, cols)
    assert mask.shape == (rows, cols)
    assert mask.any()
    # Le "trou" du A doit laisser au moins un pixel vide au centre haut de
    # la boite englobante de la lettre (approx.).
    assert not mask.all()


@pytest.mark.skipif(
    not _TOUCHING_HOLE_FONT.exists(),
    reason="Police Andale Mono.ttf indisponible sur cette machine (voir recherche ci-dessus).",
)
def test_hole_touching_exterior_is_repaired_on_real_font():
    """Cas reel (pas un mock) : le glyphe "0" de `Andale Mono.ttf` a 3
    contours imbriques -- anneau exterieur, anneau interieur (le "trou"),
    et la barre oblique qui traverse ce trou (elle-meme imbriquee DANS le
    trou). Avec la classification par profondeur d'imbrication arbitraire
    (`classify_contours_by_containment`), la barre est correctement
    reconnue comme un ILOT PLEIN a la profondeur 2 (pas un second trou
    plat du contour exterieur comme avant ce correctif) : la lettre produit
    2 composantes valides (l'anneau troue + la barre pleine separee),
    aucune reparation d'invalidite necessaire. Verifie que l'extraction ne
    plante pas et retourne des contours finaux valides et geometriquement
    corrects (le trou de l'anneau ET la barre solide doivent survivre)."""
    layout = extract_word_glyphs("0", _TOUCHING_HOLE_FONT, font_size_mm=20.0)
    letter = layout.letters[0]

    assert len(letter.parts) == 2
    polys = [part.to_shapely() for part in letter.parts]
    for poly in polys:
        assert poly.is_valid

    ring_part = max(polys, key=lambda p: p.area)
    bar_part = min(polys, key=lambda p: p.area)
    assert len(ring_part.interiors) == 1, "L'anneau exterieur doit garder son trou."
    assert len(bar_part.interiors) == 0, "La barre oblique est un ilot plein, pas un trou."
    assert bar_part.area > 0


def test_multi_part_glyph_i_keeps_both_disjoint_components():
    """Le "i" est fait de deux composantes exterieures disjointes (le point
    et la barre), aucune contenue dans l'autre. Les DEUX doivent survivre
    -- avant ce correctif, seule la plus grande (la barre) etait gardee et
    le point etait jete silencieusement."""
    layout = extract_word_glyphs("i", _SYSTEM_FONT, font_size_mm=20.0)
    letter = layout.letters[0]

    assert len(letter.parts) == 2
    # Les deux composantes doivent etre verticalement disjointes (le point
    # au-dessus de la barre), preuve que ce sont bien deux ilots distincts
    # et pas un artefact de decoupe d'un seul contour.
    tops = sorted(max(p[1] for p in part.exterior) for part in letter.parts)
    bottoms = sorted(min(p[1] for p in part.exterior) for part in letter.parts)
    assert bottoms[1] >= tops[0]  # la composante haute ne chevauche pas la basse

    mask = rasterize_letter_mask(letter, layout.width_mm, layout.height_mm, 200, 200)
    assert mask.any()

    polygon = letter.to_shapely()
    assert polygon.geom_type == "MultiPolygon"
    assert len(polygon.geoms) == 2


def test_multi_part_glyph_percent_keeps_all_components_and_holes():
    """Le "%" a typiquement 2-3 composantes disjointes (deux ronds troues +
    la barre oblique). Toutes doivent etre conservees, avec leurs trous
    respectifs intacts."""
    layout = extract_word_glyphs("%", _SYSTEM_FONT, font_size_mm=20.0)
    letter = layout.letters[0]

    assert len(letter.parts) >= 2
    # Au moins deux composantes doivent avoir un trou (les deux ronds du %).
    parts_with_holes = [p for p in letter.parts if p.holes]
    assert len(parts_with_holes) >= 2
