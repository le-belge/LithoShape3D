"""Tests du Cas A (alpha) et Cas B (seuillage photo) de l'extraction
vectorielle de silhouette depuis une image -- images synthetiques generees
en memoire (PIL/numpy), aucune dependance a un fichier externe."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from lithoshape3d.core.geometry.image_shape_extractor import (
    ImageShapeExtractionError,
    extract_shape_from_arrays,
    extract_shape_from_image,
    load_image_for_extraction,
    mask_to_polygon,
    threshold_and_clean_mask,
)


def _alpha_gray_from_rgba(image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    rgba = np.asarray(image, dtype=np.float32)
    alpha = rgba[:, :, 3] / 255.0
    gray = np.asarray(image.convert("L"), dtype=np.float32) / 255.0
    return alpha, gray


# --------------------------------------------------------------------- #
# Cas A -- canal alpha exploitable (logo/silhouette a fond transparent)
# --------------------------------------------------------------------- #


def test_alpha_image_simple_rectangle_no_hole():
    image = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 40, 160, 160], fill=(255, 255, 255, 255))
    alpha, gray = _alpha_gray_from_rgba(image)

    result = extract_shape_from_arrays(alpha, gray, width_mm=100.0)

    assert result.threshold_used is None  # Cas A : pas de seuillage
    assert result.polygon.geom_type == "Polygon"
    assert len(result.polygon.interiors) == 0
    # 120px sur 200px de large, a 100mm de large -> 60mm de cote -> 3600 mm2.
    assert result.polygon.area == pytest.approx(3600.0, rel=0.02)
    assert result.height_mm == pytest.approx(100.0, rel=1e-6)


def test_alpha_image_ring_shape_with_one_hole():
    image = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse([30, 30, 270, 270], fill=(255, 255, 255, 255))
    draw.ellipse([100, 100, 200, 200], fill=(255, 255, 255, 0))
    alpha, gray = _alpha_gray_from_rgba(image)

    result = extract_shape_from_arrays(alpha, gray, width_mm=100.0)

    assert result.polygon.geom_type == "Polygon"
    assert len(result.polygon.interiors) == 1
    assert result.polygon.area > 0


def test_fully_opaque_alpha_channel_falls_back_to_grayscale_threshold():
    """Un PNG RGBA techniquement muni d'un canal alpha mais entierement
    opaque (cas frequent d'une photo simplement exportee en PNG) ne doit
    PAS etre traite comme un logo transparent -- il doit retomber sur le
    seuillage Cas B, comme une photo JPEG classique."""
    image = Image.new("RGBA", (200, 200), (230, 230, 230, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse([50, 50, 150, 150], fill=(20, 20, 20, 255))
    _alpha, gray = _alpha_gray_from_rgba(image)

    # Verifie directement le comportement observable de la decision de
    # polarite Cas A/Cas B (pas d'IO disque ici, `alpha` n'est meme pas
    # passe -- ce test documente ce que ferait `load_image_for_extraction`
    # sur un tel fichier, verifie separement par un test round-trip).
    result = extract_shape_from_arrays(None, gray, width_mm=100.0)
    assert result.threshold_used is not None
    assert result.polygon.area > 0


# --------------------------------------------------------------------- #
# Cas B -- photo classique sans transparence (seuillage Otsu + nettoyage)
# --------------------------------------------------------------------- #


def test_photo_without_alpha_otsu_threshold_produces_exploitable_shape():
    image = Image.new("L", (300, 300), 200)
    draw = ImageDraw.Draw(image)
    draw.ellipse([80, 80, 220, 220], fill=40)
    rng = np.random.default_rng(42)
    arr = np.asarray(image, dtype=np.float32)
    arr = np.clip(arr + rng.normal(0, 8, arr.shape), 0, 255)
    gray = (arr / 255.0).astype(np.float32)

    result = extract_shape_from_arrays(None, gray, width_mm=100.0, threshold_mode="auto")

    assert result.threshold_used is not None
    assert 0 <= result.threshold_used <= 255
    expected_area = np.pi * 70.0 * 70.0 * (100.0 / 300.0) ** 2
    assert result.polygon.area == pytest.approx(expected_area, rel=0.1)
    # Simplification (approxPolyDP) : un cercle ne doit pas produire des
    # milliers de sommets issus du bruit de rasterisation pixel-a-pixel.
    exterior = result.polygon.exterior if result.polygon.geom_type == "Polygon" else None
    assert exterior is not None
    assert len(list(exterior.coords)) < 100


def test_manual_threshold_overrides_otsu():
    gray = np.ones((100, 100), dtype=np.float32) * 0.9
    gray[20:80, 20:80] = 0.1

    result = extract_shape_from_arrays(
        None, gray, width_mm=100.0, threshold_mode="manual", threshold_value=128
    )
    assert result.threshold_used == 128
    assert result.polygon.area == pytest.approx(3600.0, rel=0.05)


def test_noisy_small_components_are_filtered_out():
    gray = np.ones((100, 100), dtype=np.float32) * 0.9
    gray[20:80, 20:80] = 0.1  # grand blob (3600 px, 36% de l'image)
    gray[5:7, 5:7] = 0.1  # petites composantes parasites (4 px chacune)
    gray[90:92, 90:92] = 0.1
    gray[2:4, 95:97] = 0.1

    mask, _threshold, warnings = threshold_and_clean_mask(
        gray, mode="auto", min_component_area_ratio=0.001
    )

    assert mask.sum() == 3600  # seul le grand blob survit
    assert any("parasite" in w for w in warnings)


def test_threshold_and_clean_mask_manual_mode_requires_value():
    gray = np.ones((10, 10), dtype=np.float32) * 0.5
    with pytest.raises(ValueError, match="threshold_value"):
        threshold_and_clean_mask(gray, mode="manual")


# --------------------------------------------------------------------- #
# Garde-fous : cas degeneres
# --------------------------------------------------------------------- #


def test_uniform_image_raises_clear_error():
    gray = np.ones((50, 50), dtype=np.float32) * 0.5
    with pytest.raises(ImageShapeExtractionError):
        extract_shape_from_arrays(None, gray, width_mm=50.0)


def test_fully_transparent_alpha_and_uniform_gray_raises_clear_error():
    """Alpha entierement transparent (rien a extraire) ET niveaux de gris
    uniformes (rien a seuiller non plus) -- doit produire une erreur claire,
    pas un plantage silencieux ni une forme vide passee en aval."""
    alpha = np.zeros((50, 50), dtype=np.float32)
    gray = np.ones((50, 50), dtype=np.float32) * 0.5
    with pytest.raises(ImageShapeExtractionError):
        extract_shape_from_arrays(alpha, gray, width_mm=50.0)


def test_mask_to_polygon_empty_mask_raises_clear_error():
    mask = np.zeros((20, 20), dtype=bool)
    with pytest.raises(ImageShapeExtractionError):
        mask_to_polygon(mask, width_mm=20.0)


def test_extract_shape_from_arrays_rejects_non_positive_width():
    gray = np.ones((10, 10), dtype=np.float32) * 0.5
    gray[2:8, 2:8] = 0.1
    with pytest.raises(ValueError, match="width_mm"):
        extract_shape_from_arrays(None, gray, width_mm=0.0)


# --------------------------------------------------------------------- #
# Integration : chargement depuis un vrai fichier image
# --------------------------------------------------------------------- #


def test_extract_shape_from_image_file_round_trip(tmp_path):
    image = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 40, 160, 160], fill=(255, 255, 255, 255))
    path = tmp_path / "logo.png"
    image.save(path)

    result = extract_shape_from_image(path, width_mm=80.0)

    assert result.polygon.area > 0
    assert result.threshold_used is None
    assert result.mask.shape[0] > 0 and result.mask.shape[1] > 0


def test_load_image_for_extraction_fully_opaque_rgba_falls_back_to_gray(tmp_path):
    """Round-trip disque reel (pas seulement en memoire) : un PNG RGBA
    entierement opaque doit faire retomber `load_image_for_extraction` sur
    le chemin niveaux de gris (`alpha is None`), meme si le fichier a
    techniquement un canal alpha."""
    image = Image.new("RGBA", (100, 100), (230, 230, 230, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse([25, 25, 75, 75], fill=(20, 20, 20, 255))
    path = tmp_path / "opaque.png"
    image.save(path)

    alpha, gray = load_image_for_extraction(path)

    assert alpha is None
    assert gray.shape == (100, 100)
