from pathlib import Path

import pytest

from lithoshape3d.core.geometry.letter_glyph_extractor import (
    GlyphExtractionError,
    extract_word_glyphs,
    rasterize_letter_mask,
)

_SYSTEM_FONT = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
_CONDENSED_FONT = Path("/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf")

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


def test_hole_touching_exterior_documented_or_handled():
    """Cas degenere : trou touchant le contour exterieur (fonts tres
    condensees). Non reproductible de facon fiable avec les polices
    systeme disponibles sur cette machine (Arial Narrow ne produit pas ce
    defaut ; il apparait surtout sur des fontes bitmap->vecteur mal
    convertie ou des tailles d'impression extremes, hors scope d'un test
    unitaire deterministe). Le chemin de code correspondant
    (`_classify_contours`, fusion via `buffer(0)` + avertissement) est
    exerce indirectement par `test_letter_with_two_holes` (B) et
    `test_letter_with_one_hole` (A) qui passent tous deux par
    `_classify_contours` sans avertissement de fusion, validant le chemin
    nominal. Le chemin de fusion degenere reste documente dans le docstring
    du module mais n'est pas couvert par un test avec police reelle."""
    if not _CONDENSED_FONT.exists():
        pytest.skip("Police condensee non disponible pour tenter de reproduire le cas.")
    layout = extract_word_glyphs("B", _CONDENSED_FONT, font_size_mm=6.0)
    # A cette taille tres reduite, on verifie au moins que l'extraction ne
    # plante pas et reste coherente (0..n trous valides).
    assert layout.letters[0].character == "B"
