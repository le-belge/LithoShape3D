"""Image Transform (cadrage, v0.4) : positionnement de la photo dans la
grille canonique, independant de la Shape et de la vue."""

import numpy as np
import pytest

from lithoshape3d.core.image.transform import apply_image_transform
from lithoshape3d.core.scene.models import ImageTransform


def test_identity_transform_is_isotropic_fit_no_distortion(tmp_path):
    """offset=0/scale=1/rotation=0 = "Ajuster" (Fit) : image ENTIERE visible,
    centree, SANS distorsion -- pas d'etirement anisotrope. Note :
    l'equivalence "projet migre ne change pas visuellement" (v4->v5) est
    assuree par un chemin SEPARE (composition.image_transform=None, qui
    n'appelle jamais cette fonction), pas par cette fonction elle-meme --
    voir composition._migrate_v4_to_v5 et le docstring de module."""
    # source plus large que haute (2:1), grille canonique carree -> l'axe
    # le plus contraignant (X) doit dicter l'echelle isotrope, laissant des
    # bandes vides (fill_value) en haut/bas.
    source = np.full((50, 100), 0.2, dtype=np.float32)

    result = apply_image_transform(source, ImageTransform(), width_px=100, height_px=100, fill_value=0.9)

    # bandes vides en haut/bas (letterboxing), pas sur les cotes
    assert result[0, 50] == pytest.approx(0.9, abs=0.05)
    assert result[-1, 50] == pytest.approx(0.9, abs=0.05)
    assert result[50, 0] == pytest.approx(0.2, abs=0.05)
    assert result[50, -1] == pytest.approx(0.2, abs=0.05)


def test_fill_scale_relative_to_fit_covers_without_distortion():
    from lithoshape3d.core.image.transform import fill_scale_relative_to_fit

    # source 2:1, grille carree -> Fill doit agrandir par rapport a Fit
    factor = fill_scale_relative_to_fit(src_w=100, src_h=50, width_px=100, height_px=100)
    assert factor > 1.0

    filled = apply_image_transform(
        np.full((50, 100), 0.3, dtype=np.float32),
        ImageTransform(scale=factor),
        width_px=100,
        height_px=100,
        fill_value=0.9,
    )
    # Remplir : plus aucune bande vide visible (l'image couvre tout)
    assert filled[0, 50] == pytest.approx(0.3, abs=0.05)
    assert filled[-1, 50] == pytest.approx(0.3, abs=0.05)


def test_scale_up_makes_the_image_cover_more_of_the_grid_per_pixel():
    """Zoomer (scale>1) doit agrandir l'image : un carre source centre doit
    occuper une plus grande fraction de la grille de destination."""
    source = np.zeros((100, 100), dtype=np.float32)
    source[40:60, 40:60] = 1.0  # carre blanc au centre

    normal = apply_image_transform(source, ImageTransform(scale=1.0), 100, 100, fill_value=0.0)
    zoomed = apply_image_transform(source, ImageTransform(scale=2.0), 100, 100, fill_value=0.0)

    assert zoomed.sum() > normal.sum()


def test_offset_shifts_the_image_within_the_grid():
    source = np.zeros((100, 100), dtype=np.float32)
    source[45:55, 45:55] = 1.0  # petit carre au centre

    centered = apply_image_transform(source, ImageTransform(), 100, 100, fill_value=0.0)
    shifted = apply_image_transform(source, ImageTransform(offset_x=0.3), 100, 100, fill_value=0.0)

    centered_x = np.argwhere(centered > 0.5)[:, 1].mean()
    shifted_x = np.argwhere(shifted > 0.5)[:, 1].mean()
    assert shifted_x > centered_x + 20  # decalage vers la droite (offset_x positif)


def test_areas_outside_the_transformed_image_use_fill_value():
    source = np.ones((50, 50), dtype=np.float32)

    result = apply_image_transform(source, ImageTransform(scale=0.3), 100, 100, fill_value=0.75)

    corner = result[0:5, 0:5]
    assert corner.mean() == pytest.approx(0.75, abs=0.05)


def test_rotation_changes_the_output_without_erroring():
    source = np.zeros((100, 100), dtype=np.float32)
    source[10:90, 45:55] = 1.0  # bande verticale

    unrotated = apply_image_transform(source, ImageTransform(), 100, 100, fill_value=0.0)
    rotated = apply_image_transform(source, ImageTransform(rotation_deg=90.0), 100, 100, fill_value=0.0)

    assert not np.array_equal(unrotated, rotated)
    assert rotated.sum() == pytest.approx(unrotated.sum(), rel=0.15)  # meme superficie, juste tournee


def test_output_shape_matches_requested_canonical_grid():
    source = np.zeros((30, 20), dtype=np.float32)

    result = apply_image_transform(source, ImageTransform(), width_px=200, height_px=150)

    assert result.shape == (150, 200)
