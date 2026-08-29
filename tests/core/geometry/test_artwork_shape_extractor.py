"""Tests de l'extraction "artwork au trait" -- enveloppe unifiee + masque
d'encre -- images synthetiques generees en memoire (PIL/numpy), meme style
que `test_image_shape_extractor.py`."""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw

from lithoshape3d.core.geometry.artwork_shape_extractor import (
    ArtworkExtractionError,
    _fill_enclosed_regions,
    _search_min_closing_radius,
    compute_envelope_mask,
    extract_artwork_from_arrays,
    extract_artwork_from_image,
)
from lithoshape3d.core.geometry.image_shape_extractor import ImageShapeExtractionError


def _gray_from_image(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L"), dtype=np.float32) / 255.0


# --------------------------------------------------------------------- #
# Contour ferme unique -- pas de fermeture necessaire
# --------------------------------------------------------------------- #


def test_single_closed_contour_needs_no_closing():
    image = Image.new("L", (200, 200), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse([40, 40, 160, 160], outline=0, width=8)
    gray = _gray_from_image(image)

    result = extract_artwork_from_arrays(gray, width_mm=50.0)

    assert result.num_components_before_closing == 1
    assert result.num_components_after_closing == 1
    assert result.closing_radius_px == 0
    assert not any("fermeture" in w for w in result.warnings)
    assert result.envelope_polygon.area > 0
    assert result.ink_polygon.area > 0
    # L'enveloppe (interieur du cercle rempli par fill-from-border) doit
    # etre bien plus grande que l'encre seule (juste le trait).
    assert result.envelope_polygon.area > result.ink_polygon.area


# --------------------------------------------------------------------- #
# 2 composantes disjointes -- fermeture automatique -> 1 seule enveloppe
# --------------------------------------------------------------------- #


def test_two_disjoint_components_are_unified_by_automatic_closing():
    image = Image.new("L", (200, 200), 255)
    draw = ImageDraw.Draw(image)
    # deux "poings" (blobs) disjoints d'un cercle central, gap ~10px --
    # reproduit le cas Thunderdome (elements disjoints du dessin source).
    draw.ellipse([20, 80, 70, 130], fill=0)
    draw.ellipse([130, 80, 180, 130], fill=0)
    draw.ellipse([80, 60, 120, 100], outline=0, width=6)
    gray = _gray_from_image(image)

    result = extract_artwork_from_arrays(gray, width_mm=50.0)

    assert result.num_components_before_closing >= 2
    assert result.num_components_after_closing == 1
    assert result.closing_radius_px > 0
    assert any("fermeture" in w for w in result.warnings)
    # Une seule composante exterieure au final (corps imprimable unique).
    assert result.envelope_polygon.geom_type == "Polygon"


def test_compute_envelope_mask_explicit_radius_too_small_raises_clear_error():
    mask = np.zeros((100, 100), dtype=bool)
    mask[10:20, 10:20] = True
    mask[10:20, 70:80] = True  # loin, gap 50px

    with pytest.raises(ArtworkExtractionError):
        compute_envelope_mask(mask, closing_radius_px=2)


def test_compute_envelope_mask_explicit_radius_sufficient_is_accepted():
    mask = np.zeros((100, 100), dtype=bool)
    mask[40:50, 10:20] = True
    mask[40:50, 25:35] = True  # gap 5px

    envelope, radius, before, after = compute_envelope_mask(mask, closing_radius_px=6)
    assert radius == 6
    assert before == 2
    assert after == 1
    assert envelope.any()


# --------------------------------------------------------------------- #
# Regression : encoche locale laissee par une fermeture "juste suffisante"
# pour la connexite GLOBALE mais pas pour la douceur LOCALE du contour --
# cas reel "Cherry Moon" (voir examples/physical_validation/cherry_moon_
# source/) ou un des traits fins de l'anneau decoratif etait bien soude au
# reste du dessin (masque final = 1 seule composante, mesh watertight) mais
# laissait une concavite en V/marche anormale a l'endroit precis de la
# soudure la plus juste. `_search_min_closing_radius` ne garantit que la
# connexite globale au plus petit rayon possible, jamais la douceur locale
# de CHAQUE jonction -- `compute_envelope_mask` doit desormais rattraper ce
# residu via `_smooth_envelope_notches`.
# --------------------------------------------------------------------- #


def _disc_with_two_offset_blobs_mask() -> np.ndarray:
    """Reproduit en miniature la structure exacte du defaut Cherry Moon :
    un disque principal + un petit element d'encre TOUT PRES du bord (se
    soude avec une jonction large, sans encoche) + un second element un peu
    plus loin, juste a la limite du rayon de fermeture necessaire pour
    unifier le dessin (se soude avec une jonction etroite -- l'encoche).
    Grand canevas (800px) pour que l'aire des deux petits elements reste
    tres inferieure a 1% de l'aire totale, comme dans le cas reel (le
    detail radial de l'anneau decoratif est minuscule face au disque
    entier)."""
    mask = np.zeros((800, 800), dtype=np.uint8)
    cv2.circle(mask, (400, 400), 300, 255, thickness=6)
    cv2.circle(mask, (103, 400), 8, 255, thickness=-1)  # gap ~2px : jonction large
    cv2.circle(mask, (68, 435), 8, 255, thickness=-1)  # gap ~15px : jonction etroite -> encoche
    return mask > 0


def test_local_bridging_notch_is_filled_after_global_closing():
    """Cas Cherry Moon reproduit en miniature (voir `_disc_with_two_offset_
    blobs_mask`) : AVANT la correction (fermeture + fill-from-border seuls,
    sans `_smooth_envelope_notches`), la zone entre les deux petits elements
    reste une encoche concave (fond, pas matiere) meme si le masque global
    est deja une seule composante connexe. Verifie a la fois que le defaut
    est bien reproductible dans ce cas synthetique (avant correction) ET que
    `compute_envelope_mask` (avec la correction) le comble."""
    ink_mask = _disc_with_two_offset_blobs_mask()

    from lithoshape3d.core.geometry.artwork_shape_extractor import (
        _default_max_closing_radius_px,
    )

    max_radius = _default_max_closing_radius_px(ink_mask.shape)
    radius, working = _search_min_closing_radius(ink_mask, max_radius)
    envelope_before_smoothing = _fill_enclosed_regions(working)

    # Pixels au coeur de l'encoche (entre les deux petits elements, hors du
    # disque) : encore fond (False) juste apres fermeture + fill-from-border,
    # sans la passe de lissage -- confirme que le defaut est bien reproduit.
    notch_points = [(85, 418), (80, 420), (90, 415)]
    assert all(not envelope_before_smoothing[y, x] for x, y in notch_points), (
        "Le cas synthetique ne reproduit pas l'encoche attendue avant "
        "correction -- ajuster les coordonnees/rayons de test."
    )

    envelope, radius_used, num_before, num_after = compute_envelope_mask(ink_mask)
    assert num_after == 1

    # Apres correction (`_smooth_envelope_notches` applique par
    # `compute_envelope_mask`) : l'encoche est comblee, ces pixels sont
    # devenus matiere.
    assert all(envelope[y, x] for x, y in notch_points), (
        "L'encoche locale n'a pas ete comblee par compute_envelope_mask -- "
        "regression du fix de l'encoche Cherry Moon."
    )

    # La correction ne doit ajouter qu'une petite quantite de matiere (les
    # defauts locaux sont petits par construction) -- pas de gonflement
    # global du contour.
    added_ratio = (envelope.sum() - envelope_before_smoothing.sum()) / envelope.sum()
    assert added_ratio < 0.02


def test_large_real_gap_is_not_erased_by_notch_smoothing():
    """Garde-fou contre une regression inverse : `_smooth_envelope_notches`
    ne doit JAMAIS combler une vraie caracteristique du dessin (ex. une
    grande ouverture volontaire, du meme ordre de grandeur que l'enveloppe
    elle-meme) -- seulement les petits defauts de jonction. Ici, un anneau
    largement ouvert (forme de "C") : l'ouverture doit rester une ouverture
    apres extraction complete."""
    image = Image.new("L", (300, 300), 255)
    draw = ImageDraw.Draw(image)
    # Anneau "C" : ouverture large (~60 degres) sur le cote droit.
    draw.arc([50, 50, 250, 250], start=40, end=320, fill=0, width=14)
    gray = _gray_from_image(image)

    result = extract_artwork_from_arrays(gray, width_mm=60.0)

    # L'enveloppe doit rester nettement plus petite qu'un disque plein
    # (l'ouverture du "C" -- une vraie concavite -- n'a pas ete comblee).
    from shapely.geometry import Point

    full_disc_area = Point(150 * 60.0 / 300, 150 * 60.0 / 300).buffer(100 * 60.0 / 300).area
    assert result.envelope_polygon.area < 0.85 * full_disc_area


# --------------------------------------------------------------------- #
# ink_mask / fond complementaire du capot : disjoints, union == footprint
# --------------------------------------------------------------------- #


def test_ink_and_complementary_cap_footprint_partition_exactly():
    from lithoshape3d.core.geometry.vector_lightbox import vector_lightbox_cap_footprint

    image = Image.new("L", (200, 200), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse([40, 40, 160, 160], outline=0, width=10)
    draw.rectangle([90, 60, 110, 140], fill=0)
    gray = _gray_from_image(image)

    result = extract_artwork_from_arrays(gray, width_mm=80.0)
    cap_polygon = vector_lightbox_cap_footprint(result.envelope_polygon, 1.6)

    color_a = result.ink_polygon.intersection(cap_polygon)
    color_b = cap_polygon.difference(result.ink_polygon)

    assert color_a.intersection(color_b).area == pytest.approx(0.0, abs=1e-9)
    union_area = color_a.union(color_b).area
    assert union_area == pytest.approx(cap_polygon.area, rel=1e-6)


# --------------------------------------------------------------------- #
# Garde-fous : cas degeneres
# --------------------------------------------------------------------- #


def test_blank_image_raises_clear_error():
    """Aucune encre detectable : erreur levee par le seuillage reutilise
    (`threshold_and_clean_mask`, Cas B) -- pas une `ArtworkExtractionError`
    specifique puisque le probleme est en amont du calcul d'enveloppe, mais
    `ArtworkExtractionError` en est une sous-classe donc tout code appelant
    qui l'attrape reste correct."""
    gray = np.ones((50, 50), dtype=np.float32)
    with pytest.raises(ImageShapeExtractionError):
        extract_artwork_from_arrays(gray, width_mm=50.0)


def test_too_scattered_drawing_exceeds_closing_radius_cap_and_raises():
    image = Image.new("L", (400, 400), 255)
    draw = ImageDraw.Draw(image)
    # trois blobs tres eloignes (coins opposes) -- aucune fermeture
    # raisonnable ne peut les unifier au plafond par defaut.
    draw.ellipse([10, 10, 40, 40], fill=0)
    draw.ellipse([360, 360, 390, 390], fill=0)
    draw.ellipse([10, 360, 40, 390], fill=0)
    gray = _gray_from_image(image)

    with pytest.raises(ArtworkExtractionError, match="trop eclate"):
        extract_artwork_from_arrays(gray, width_mm=50.0, max_closing_radius_px=5)


def test_extract_artwork_from_image_file_round_trip(tmp_path):
    image = Image.new("L", (200, 200), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse([40, 40, 160, 160], outline=0, width=8)
    path = tmp_path / "artwork.png"
    image.save(path)

    result = extract_artwork_from_image(path, width_mm=60.0)

    assert result.envelope_polygon.area > 0
    assert result.ink_polygon.area > 0
    assert result.threshold_used is not None
    assert result.ink_mask.shape == result.envelope_mask.shape
