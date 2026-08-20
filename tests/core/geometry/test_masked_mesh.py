"""Couverture Phase 2B : heightmap + masque irregulier + parametres -> volume
3D ferme/manifold, sur une seule Zone. Fixtures synthetiques (pas de photo
reelle necessaire) pour rectangle, cercle, anneau (trou), forme en L,
etoile concave, ilots multiples, et masque insuffisant.
"""

import numpy as np
import pytest

from lithoshape3d.core.geometry.heightmap import Heightmap
from lithoshape3d.core.geometry.mesh_builder import DEFAULT_MASK_THRESHOLD, build_slab_mesh
from lithoshape3d.core.scene.models import GeometryParameters
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from tests.fixtures.synthetic_masks import (
    circle_mask,
    concave_star_mask,
    full_mask,
    half_mask,
    l_shape_mask,
    ring_mask,
    tiny_invalid_mask,
    two_islands_mask,
)

ROWS, COLS = 60, 80
WIDTH_MM, HEIGHT_MM = 80.0, 60.0


def _params(**overrides) -> GeometryParameters:
    defaults = {
        "width_mm": WIDTH_MM,
        "height_mm": HEIGHT_MM,
        "min_thickness_mm": 0.8,
        "max_thickness_mm": 3.0,
        "resolution": WIDTH_MM / COLS,
    }
    defaults.update(overrides)
    return GeometryParameters(**defaults)


def _heightmap(rows=ROWS, cols=COLS, value=0.5) -> Heightmap:
    rng = np.random.default_rng(0)
    values = np.clip(value + rng.normal(0, 0.05, size=(rows, cols)), 0.0, 1.0).astype(np.float32)
    return Heightmap(values=values)


@pytest.mark.parametrize(
    "mask_fn,expected_min_components",
    [
        (full_mask, 1),
        (half_mask, 1),
        (circle_mask, 1),
        (ring_mask, 1),
        (l_shape_mask, 1),
        (concave_star_mask, 1),
        (two_islands_mask, 2),
    ],
)
def test_topology_produces_valid_watertight_manifold_mesh(mask_fn, expected_min_components):
    heightmap = _heightmap()
    mask = mask_fn(ROWS, COLS).astype(np.float32)
    params = _params()

    mesh = build_slab_mesh(heightmap, mask=mask, params=params)
    result = validate_mesh(mesh)

    assert result.is_valid, result.issues()
    assert result.open_boundary_edge_count == 0
    assert result.connected_components == expected_min_components


def test_ring_has_a_real_hole_but_stays_watertight():
    heightmap = _heightmap()
    mask = ring_mask(ROWS, COLS).astype(np.float32)
    params = _params()

    mesh = build_slab_mesh(heightmap, mask=mask, params=params)
    result = validate_mesh(mesh)

    assert result.is_valid
    assert result.connected_components == 1
    # le trou est reel : le mesh n'est PAS un disque plein (moins de volume
    # qu'un cercle plein de meme rayon exterieur)
    full_circle_mesh = build_slab_mesh(
        heightmap, mask=circle_mask(ROWS, COLS, radius_fraction=1 / 2.5).astype(np.float32), params=params
    )
    assert mesh.volume < full_circle_mesh.volume


def test_two_islands_are_two_independent_components_not_merged():
    heightmap = _heightmap()
    mask = two_islands_mask(ROWS, COLS).astype(np.float32)
    params = _params()

    mesh = build_slab_mesh(heightmap, mask=mask, params=params)
    result = validate_mesh(mesh)

    assert result.is_valid
    assert result.connected_components == 2
    components = mesh.split(only_watertight=False)
    for component in components:
        assert validate_mesh(component).is_valid


def test_tiny_mask_is_rejected_cleanly():
    heightmap = _heightmap()
    mask = tiny_invalid_mask(ROWS, COLS).astype(np.float32)
    params = _params()

    with pytest.raises(ValueError, match="insuffisant"):
        build_slab_mesh(heightmap, mask=mask, params=params)


def test_full_mask_regression_matches_historical_rectangle():
    heightmap = _heightmap()
    params = _params()

    mesh_full = build_slab_mesh(heightmap, mask=full_mask(ROWS, COLS).astype(np.float32), params=params)
    mesh_none = build_slab_mesh(heightmap, mask=None, params=params)

    assert np.allclose(mesh_full.vertices, mesh_none.vertices)
    assert np.array_equal(mesh_full.faces, mesh_none.faces)


def test_half_mask_preserves_global_scene_coordinates_no_rescale():
    """Un masque occupant la moitie droite d'une image 80mm de large doit
    garder des coordonnees X reelles proches de [40, 80], PAS etre
    redimensionne pour occuper [0, 80]."""
    heightmap = _heightmap()
    mask = half_mask(ROWS, COLS).astype(np.float32)
    params = _params()

    mesh = build_slab_mesh(heightmap, mask=mask, params=params)

    x_min, x_max = mesh.bounds[0][0], mesh.bounds[1][0]
    assert x_min == pytest.approx(WIDTH_MM / 2, abs=2.0)
    assert x_max == pytest.approx(WIDTH_MM, abs=1e-3)
    # bounds Y inchangees (couvre toute la hauteur, comme le masque le permet)
    assert mesh.bounds[1][1] == pytest.approx(HEIGHT_MM, abs=1e-3)


def test_soft_mask_uses_threshold_not_raw_values():
    """Les valeurs intermediaires du masque ne doivent pas casser la
    topologie : le seuil binaire (0.5 par defaut) determine seul quelles
    cellules sont actives, mais le masque source n'est pas modifie."""
    heightmap = _heightmap()
    soft_mask = np.zeros((ROWS, COLS), dtype=np.float32)
    soft_mask[:, : COLS // 2] = 0.3  # sous le seuil -> inactif
    soft_mask[:, COLS // 2 :] = 0.7  # au-dessus du seuil -> actif
    original = soft_mask.copy()
    params = _params()

    mesh_soft = build_slab_mesh(heightmap, mask=soft_mask, params=params)
    mesh_binary = build_slab_mesh(heightmap, mask=half_mask(ROWS, COLS).astype(np.float32), params=params)

    assert np.array_equal(mesh_soft.faces, mesh_binary.faces)
    assert np.array_equal(soft_mask, original)  # masque source jamais modifie


def test_mask_threshold_is_configurable_and_documented_default():
    assert DEFAULT_MASK_THRESHOLD == 0.5

    heightmap = _heightmap()
    mask = np.full((ROWS, COLS), 0.4, dtype=np.float32)
    params = _params()

    with pytest.raises(ValueError, match="insuffisant"):
        build_slab_mesh(heightmap, mask=mask, params=params)  # 0.4 < seuil par defaut -> rien d'actif

    mesh = build_slab_mesh(heightmap, mask=mask, params=params, mask_threshold=0.3)
    assert validate_mesh(mesh).is_valid


def test_concave_and_l_shapes_have_no_degenerate_or_nonmanifold_edges():
    heightmap = _heightmap()
    params = _params()

    for mask_fn in (l_shape_mask, concave_star_mask):
        mesh = build_slab_mesh(heightmap, mask=mask_fn(ROWS, COLS).astype(np.float32), params=params)
        result = validate_mesh(mesh)
        assert result.is_valid, (mask_fn.__name__, result.issues())
        assert not result.has_degenerate_faces
