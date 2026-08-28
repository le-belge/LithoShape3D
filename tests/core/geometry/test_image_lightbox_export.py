"""Tests du pipeline complet "image -> caisson lumineux vectoriel"
(`generate_lightbox_from_image`) -- images synthetiques generees en memoire
(PIL/numpy), meme style que `test_lightbox_letters_export.py`."""

from __future__ import annotations

import numpy as np
import pytest
import trimesh
from PIL import Image, ImageDraw

from lithoshape3d.core.geometry.image_lightbox_export import generate_lightbox_from_image


def _save_alpha_logo(tmp_path, name: str = "logo.png"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse([50, 50, 250, 250], fill=(255, 255, 255, 255))
    path = tmp_path / name
    image.save(path)
    return path


def _save_photo_like(tmp_path, name: str = "photo.jpg"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    image = Image.new("L", (300, 300), 210)
    draw = ImageDraw.Draw(image)
    draw.rectangle([60, 60, 240, 240], fill=35)
    rng = np.random.default_rng(7)
    arr = np.asarray(image, dtype=np.float32)
    arr = np.clip(arr + rng.normal(0, 6, arr.shape), 0, 255).astype(np.uint8)
    noisy = Image.fromarray(arr, mode="L").convert("RGB")
    path = tmp_path / name
    noisy.save(path)
    return path


def test_generate_lightbox_from_image_alpha_logo_produces_watertight_pieces(tmp_path):
    image_path = _save_alpha_logo(tmp_path / "src")
    output_dir = tmp_path / "out_logo"

    result = generate_lightbox_from_image(
        image_path,
        output_dir,
        width_mm=60.0,
        depth_mm=20.0,
        wall_thickness_mm=1.6,
        back_thickness_mm=1.2,
    )

    assert not result.errors, result.errors
    assert result.threshold_used is None
    corps = [p for p in result.written if p.name.endswith("_corps.stl")]
    fond = [p for p in result.written if p.name.endswith("_fond.stl")]
    capot = [p for p in result.written if p.name.endswith("_capot.stl")]
    assert len(corps) == 1
    assert fond == []  # fond fusionne dans le corps, pas de fichier separe
    assert len(capot) == 1

    for path in corps + capot:
        mesh = trimesh.load(path)
        assert mesh.is_watertight, f"{path} n'est pas watertight"


def test_generate_lightbox_from_image_photo_threshold_produces_watertight_pieces(tmp_path):
    image_path = _save_photo_like(tmp_path / "src")
    output_dir = tmp_path / "out_photo"

    result = generate_lightbox_from_image(
        image_path,
        output_dir,
        width_mm=60.0,
        depth_mm=20.0,
        wall_thickness_mm=1.6,
        back_thickness_mm=1.2,
        threshold_mode="auto",
    )

    assert not result.errors, result.errors
    assert result.threshold_used is not None
    corps = [p for p in result.written if p.name.endswith("_corps.stl")]
    fond = [p for p in result.written if p.name.endswith("_fond.stl")]
    assert len(corps) == 1
    assert fond == []  # fond fusionne dans le corps, pas de fichier separe
    for path in corps:
        mesh = trimesh.load(path)
        assert mesh.is_watertight


def test_generate_lightbox_from_image_flat_cap_sits_within_depth(tmp_path):
    """Capot par defaut plat/lisse : doit rester compris dans la profondeur
    du caisson (pas de depassement au-dela de depth_mm)."""
    image_path = _save_alpha_logo(tmp_path / "src")
    output_dir = tmp_path / "out"
    depth_mm = 20.0

    result = generate_lightbox_from_image(
        image_path, output_dir, width_mm=60.0, depth_mm=depth_mm, wall_thickness_mm=1.6
    )
    assert not result.errors, result.errors
    capot = next(p for p in result.written if p.name.endswith("_capot.stl"))
    mesh = trimesh.load(capot)
    assert mesh.bounds[1][2] <= depth_mm + 1e-6


def test_generate_lightbox_from_image_reports_clean_error_on_degenerate_image(tmp_path):
    """Image totalement uniforme (aucune forme detectable) : le pipeline
    doit rapporter une erreur claire dans `result.errors`, PAS lever une
    exception non geree."""
    image = Image.new("L", (100, 100), 128)
    image_path = tmp_path / "src" / "blank.png"
    image_path.parent.mkdir()
    image.save(image_path)

    result = generate_lightbox_from_image(image_path, tmp_path / "out", width_mm=50.0)

    assert not result.ok
    assert result.errors
    assert any("extraction" in e for e in result.errors)


def _save_artwork_with_disjoint_parts(tmp_path, name: str = "artwork.png"):
    """Dessin au trait : un cercle + deux blobs disjoints (poings) -- meme
    esprit que le cas reel Thunderdome (elements physiquement disjoints du
    cercle central dans le dessin source)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    image = Image.new("L", (300, 300), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse([90, 90, 210, 210], outline=0, width=10)
    draw.ellipse([20, 100, 70, 150], fill=0)
    draw.ellipse([230, 100, 280, 150], fill=0)
    path = tmp_path / name
    image.save(path)
    return path


def test_generate_lightbox_artwork_envelope_unifies_disjoint_parts_into_one_body(tmp_path):
    image_path = _save_artwork_with_disjoint_parts(tmp_path / "src")
    output_dir = tmp_path / "out_artwork"

    result = generate_lightbox_from_image(
        image_path,
        output_dir,
        width_mm=80.0,
        depth_mm=20.0,
        wall_thickness_mm=1.6,
        back_thickness_mm=1.2,
        shape_mode="artwork_envelope",
        cap_mode="flat_two_color",
    )

    assert not result.errors, result.errors
    corps = [p for p in result.written if p.name.endswith("_corps.stl")]
    fond = [p for p in result.written if p.name.endswith("_fond.stl")]
    capot_a = [p for p in result.written if p.name.endswith("_capot_couleur_a.stl")]
    capot_b = [p for p in result.written if p.name.endswith("_capot_couleur_b.stl")]
    assert len(corps) == 1
    assert fond == []  # fond fusionne dans le corps, pas de fichier separe
    assert len(capot_a) == 1
    assert len(capot_b) == 1

    for path in corps + capot_a + capot_b:
        mesh = trimesh.load(path)
        assert mesh.is_watertight, f"{path} n'est pas watertight"

    # Le corps doit rester UNE seule enveloppe connectee malgre les 2
    # blobs disjoints du dessin source -- c'est tout l'interet du mode
    # artwork_envelope (fermeture morphologique automatique).
    body_mesh = trimesh.load(corps[0])
    assert len(body_mesh.split(only_watertight=False)) == 1
    assert any("fermeture" in w for w in result.warnings)


def test_generate_lightbox_flat_two_color_requires_artwork_envelope_shape_mode(tmp_path):
    image_path = _save_photo_like(tmp_path / "src")

    with pytest.raises(ValueError, match="artwork_envelope"):
        generate_lightbox_from_image(
            image_path,
            tmp_path / "out",
            width_mm=60.0,
            cap_mode="flat_two_color",
        )


def test_generate_lightbox_from_image_with_lithophane_cap_reuses_heightfield_engine(tmp_path):
    """Quand une image de capot est fournie, le capot doit passer par le
    meme moteur heightfield/lithophanie que LightBox Letters (au lieu du
    capot plat par defaut) -- verifie surtout l'absence de crash dans la
    glue (rasterisation du footprint + `compose_scene_mesh`), pas le detail
    du relief lui-meme (deja teste ailleurs)."""
    image_path = _save_alpha_logo(tmp_path / "src")
    cap_image = Image.new("L", (100, 100), 128)
    ImageDraw.Draw(cap_image).ellipse([20, 20, 80, 80], fill=220)
    cap_image_path = tmp_path / "src" / "cap.png"
    cap_image.save(cap_image_path)

    result = generate_lightbox_from_image(
        image_path,
        tmp_path / "out",
        width_mm=60.0,
        depth_mm=20.0,
        wall_thickness_mm=1.6,
        cap_image_path=cap_image_path,
    )

    assert not result.errors, result.errors
    capot = [p for p in result.written if p.name.endswith("_capot.stl")]
    assert len(capot) == 1
    mesh = trimesh.load(capot[0])
    assert mesh.is_watertight
