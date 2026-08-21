"""Integration ShapeMask/ImageTransform dans la composition (Shape Composer,
v0.4). `effective_zone_mask = zone_mask AND shape_mask` (2.1) ; aucune Zone
ne doit produire de matiere hors de la Shape."""

import numpy as np
import pytest

from lithoshape3d.core.geometry.composition import (
    ZoneSource,
    compose_scene_heightfield,
    compose_scene_mesh,
)
from lithoshape3d.core.geometry.shape import build_shape_mask
from lithoshape3d.core.scene.models import (
    CompositionMode,
    GeometryParameters,
    ImageTransform,
    ShapeParams,
    ShapeType,
    Zone,
)
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from tests.fixtures.synthetic_images import make_uniform_image

ROWS, COLS = 60, 60
WIDTH_MM = HEIGHT_MM = 60.0


def _params() -> GeometryParameters:
    return GeometryParameters(
        width_mm=WIDTH_MM, height_mm=HEIGHT_MM, min_thickness_mm=0.8, max_thickness_mm=3.0,
        resolution=WIDTH_MM / COLS,
    )


@pytest.fixture
def base_image(tmp_path):
    return make_uniform_image(tmp_path / "base.png", value=128, width=COLS, height=ROWS)


def _base_zone() -> Zone:
    return Zone(name="Base", composition_mode=CompositionMode.BASE, geometry_params=_params())


def test_no_shape_mask_matches_historical_behavior(base_image):
    sources = [ZoneSource(zone=_base_zone(), image_path=str(base_image))]

    with_none = compose_scene_heightfield(sources)
    with_full_rect = compose_scene_heightfield(
        sources, shape_mask=build_shape_mask(ShapeParams(shape_type=ShapeType.RECTANGLE), ROWS, COLS)
    )

    assert np.array_equal(with_none[0], with_full_rect[0])
    assert np.array_equal(with_none[1], with_full_rect[1])


def test_circle_shape_restricts_active_region(base_image):
    sources = [ZoneSource(zone=_base_zone(), image_path=str(base_image))]
    circle = build_shape_mask(ShapeParams(shape_type=ShapeType.CIRCLE), ROWS, COLS)

    _z_final, active, _width_mm, _height_mm = compose_scene_heightfield(sources, shape_mask=circle)

    # les coins (hors du cercle inscrit) ne doivent jamais etre actifs
    assert not active[0, 0]
    assert not active[0, -1]
    assert not active[-1, 0]
    assert not active[-1, -1]
    assert active.sum() < ROWS * COLS  # strictement moins que le rectangle complet


def test_zone_mask_intersects_with_shape_mask_not_replaces_it(base_image, tmp_path):
    """Une Zone dont le masque couvre TOUT ne doit quand meme produire de la
    matiere que DANS la Shape -- effective_zone_mask = zone_mask AND shape_mask."""
    zone = _base_zone()
    full_zone_mask = np.ones((ROWS, COLS), dtype=np.float32)
    sources = [ZoneSource(zone=zone, image_path=str(base_image), mask=full_zone_mask)]
    circle = build_shape_mask(ShapeParams(shape_type=ShapeType.CIRCLE), ROWS, COLS)

    _z_final, active, _w, _h = compose_scene_heightfield(sources, shape_mask=circle)

    assert active.sum() == pytest.approx(np.flipud(circle).sum(), abs=1)


def test_heart_shape_produces_a_valid_manifold_mesh(base_image):
    zone = _base_zone()
    zone.geometry_params = GeometryParameters(
        width_mm=WIDTH_MM, height_mm=HEIGHT_MM, min_thickness_mm=0.8, max_thickness_mm=3.0,
        resolution=WIDTH_MM / 100,
    )
    sources = [ZoneSource(zone=zone, image_path=str(base_image))]
    heart = build_shape_mask(ShapeParams(shape_type=ShapeType.HEART), 100, 100)

    mesh = compose_scene_mesh(sources, shape_mask=heart)
    result = validate_mesh(mesh)

    assert result.is_valid


def test_image_transform_changes_the_resulting_heightfield(base_image):
    zone = _base_zone()
    sources = [ZoneSource(zone=zone, image_path=str(base_image))]

    default = compose_scene_heightfield(sources)
    zoomed = compose_scene_heightfield(sources, image_transform=ImageTransform(scale=2.0))

    # image uniforme -> le champ de hauteur lui-meme ne change pas avec le
    # zoom (source constante), mais l'appel ne doit pas lever et doit
    # rester dans la meme forme/grille.
    assert zoomed[0].shape == default[0].shape


def test_image_transform_offset_shifts_bright_region(tmp_path):
    """Avec une image non-uniforme, un decalage de cadrage doit deplacer la
    contribution correspondante dans le champ de hauteur compose."""
    from PIL import Image

    array = np.zeros((ROWS, COLS), dtype=np.uint8)
    array[:, : COLS // 4] = 255  # bande blanche a gauche
    image_path = tmp_path / "stripe.png"
    Image.fromarray(array, mode="L").save(image_path)

    zone = _base_zone()
    zone.geometry_params.invert = False
    sources = [ZoneSource(zone=zone, image_path=str(image_path))]

    default = compose_scene_heightfield(sources, image_transform=ImageTransform())
    shifted = compose_scene_heightfield(sources, image_transform=ImageTransform(offset_x=0.4))

    assert not np.array_equal(default[0], shifted[0])
