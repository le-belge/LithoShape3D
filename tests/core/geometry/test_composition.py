"""Phase 2C : composition sequentielle de plusieurs Zones en un champ de
hauteur unique, puis un mesh unique. Couvre les 10 cas imposes par la
mission (BASE seule, ADD carre, ADD anneau, ilots ADD, ADD+ADD empiles,
REPLACE, REPLACE puis ADD, zones sans overlap, ADD sans support, masques
soft non modifies).
"""

import numpy as np
import pytest

from lithoshape3d.core.geometry.composition import (
    ZoneSource,
    compose_scene_heightfield,
    compose_scene_mesh,
)
from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.scene.models import CompositionMode, GeometryParameters, ReliefMode, Zone
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from tests.fixtures.synthetic_images import make_uniform_image
from tests.fixtures.synthetic_masks import ring_mask, two_islands_mask

ROWS, COLS = 40, 60
WIDTH_MM, HEIGHT_MM = 60.0, 40.0


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


@pytest.fixture
def base_image(tmp_path):
    return make_uniform_image(tmp_path / "base.png", value=128, width=COLS, height=ROWS)


def _base_zone(name="Base") -> Zone:
    return Zone(
        name=name,
        composition_mode=CompositionMode.BASE,
        geometry_params=_params(),
        relief_mode=ReliefMode.LITHOPHANE,
    )


# ------------------------------------------------------------------ #
# 1. BASE seule : doit reproduire le comportement historique
# ------------------------------------------------------------------ #
def test_base_only_matches_historical_single_zone(base_image):
    zone = _base_zone()
    sources = [ZoneSource(zone=zone, image_path=str(base_image))]

    mesh_composed = compose_scene_mesh(sources)

    heightmap = heightmap_from_image_path(str(base_image), zone.geometry_params)
    mesh_direct = build_slab_mesh(heightmap, mask=None, params=zone.geometry_params)

    assert np.allclose(mesh_composed.vertices, mesh_direct.vertices)
    assert np.array_equal(mesh_composed.faces, mesh_direct.faces)


# ------------------------------------------------------------------ #
# 2. BASE + ADD carre
# ------------------------------------------------------------------ #
def test_base_plus_add_square_is_clearly_raised(tmp_path, base_image):
    base = _base_zone()
    add_mask = np.zeros((ROWS, COLS), dtype=np.float32)
    add_mask[10:20, 20:35] = 1.0
    add_image = make_uniform_image(tmp_path / "add.png", value=0, width=COLS, height=ROWS)  # noir -> max relief
    add_zone = Zone(
        name="Carre",
        composition_mode=CompositionMode.ADD,
        geometry_params=_params(min_thickness_mm=1.0, max_thickness_mm=1.0),  # delta constant = 1.0mm
        relief_mode=ReliefMode.SOLID,
    )
    sources = [
        ZoneSource(zone=base, image_path=str(base_image)),
        ZoneSource(zone=add_zone, image_path=str(add_image), mask=add_mask),
    ]

    z_final, active_final, _, _ = compose_scene_heightfield(sources)

    inside = np.flipud(add_mask) >= 0.5
    outside_but_active = active_final & ~inside

    base_only_value = z_final[outside_but_active][0]
    raised_value = z_final[inside][0]
    assert raised_value == pytest.approx(base_only_value + 1.0, abs=1e-4)


# ------------------------------------------------------------------ #
# 3. BASE + ADD anneau : le trou du relief ajoute doit rester visible
#    (Z = base seule au centre du trou, Z = base+ajout dans la bande)
# ------------------------------------------------------------------ #
def test_base_plus_add_ring_preserves_hole_in_added_relief(tmp_path, base_image):
    base = _base_zone()
    ring = ring_mask(ROWS, COLS).astype(np.float32)
    add_image = make_uniform_image(tmp_path / "add.png", value=0, width=COLS, height=ROWS)
    add_zone = Zone(
        name="Anneau",
        composition_mode=CompositionMode.ADD,
        geometry_params=_params(min_thickness_mm=1.5, max_thickness_mm=1.5),
        relief_mode=ReliefMode.SOLID,
    )
    sources = [
        ZoneSource(zone=base, image_path=str(base_image)),
        ZoneSource(zone=add_zone, image_path=str(add_image), mask=ring),
    ]

    z_final, active_final, _, _ = compose_scene_heightfield(sources)

    center_row, center_col = ROWS // 2, COLS // 2
    ring_flipped = np.flipud(ring) >= 0.5
    # centre du trou : actif (base couvre tout) mais SANS l'ajout de l'anneau
    assert active_final[center_row, center_col]
    assert not ring_flipped[center_row, center_col]

    ring_rows, ring_cols = np.nonzero(ring_flipped)
    on_ring_z = z_final[ring_rows[0], ring_cols[0]]
    center_z = z_final[center_row, center_col]
    assert on_ring_z == pytest.approx(center_z + 1.5, abs=1e-4)


# ------------------------------------------------------------------ #
# 4. BASE + plusieurs ilots ADD (texte simule) : tout reste connecte
# ------------------------------------------------------------------ #
def test_base_plus_add_islands_stays_one_component(tmp_path, base_image):
    base = _base_zone()
    islands = two_islands_mask(ROWS, COLS).astype(np.float32)
    add_image = make_uniform_image(tmp_path / "add.png", value=0, width=COLS, height=ROWS)
    add_zone = Zone(
        name="Lettres",
        composition_mode=CompositionMode.ADD,
        geometry_params=_params(min_thickness_mm=2.0, max_thickness_mm=2.0),
        relief_mode=ReliefMode.SOLID,
    )
    sources = [
        ZoneSource(zone=base, image_path=str(base_image)),
        ZoneSource(zone=add_zone, image_path=str(add_image), mask=islands),
    ]

    mesh = compose_scene_mesh(sources)
    result = validate_mesh(mesh)

    assert result.is_valid
    assert result.connected_components == 1  # la base sous-jacente relie tout


# ------------------------------------------------------------------ #
# 5. BASE + ADD + ADD superposes : cumul exact
# ------------------------------------------------------------------ #
def test_two_stacked_add_zones_accumulate_exactly(tmp_path, base_image):
    base = _base_zone()
    overlap_mask = np.zeros((ROWS, COLS), dtype=np.float32)
    overlap_mask[10:20, 20:35] = 1.0
    img_a = make_uniform_image(tmp_path / "a.png", value=0, width=COLS, height=ROWS)
    img_b = make_uniform_image(tmp_path / "b.png", value=0, width=COLS, height=ROWS)
    add_a = Zone(
        name="Add A",
        composition_mode=CompositionMode.ADD,
        geometry_params=_params(min_thickness_mm=0.5, max_thickness_mm=0.5),
        relief_mode=ReliefMode.SOLID,
    )
    add_b = Zone(
        name="Add B",
        composition_mode=CompositionMode.ADD,
        geometry_params=_params(min_thickness_mm=0.7, max_thickness_mm=0.7),
        relief_mode=ReliefMode.SOLID,
    )
    sources = [
        ZoneSource(zone=base, image_path=str(base_image)),
        ZoneSource(zone=add_a, image_path=str(img_a), mask=overlap_mask),
        ZoneSource(zone=add_b, image_path=str(img_b), mask=overlap_mask),
    ]

    z_final, active_final, _, _ = compose_scene_heightfield(sources)

    inside = np.flipud(overlap_mask) >= 0.5
    outside_active = active_final & ~inside
    base_value = z_final[outside_active][0]
    stacked_value = z_final[inside][0]

    assert stacked_value == pytest.approx(base_value + 0.5 + 0.7, abs=1e-4)


# ------------------------------------------------------------------ #
# 6. BASE + REPLACE : remplace localement, ne s'additionne pas
# ------------------------------------------------------------------ #
def test_replace_overwrites_instead_of_adding(tmp_path, base_image):
    base = _base_zone()
    replace_mask = np.zeros((ROWS, COLS), dtype=np.float32)
    replace_mask[5:15, 5:20] = 1.0
    replace_image = make_uniform_image(tmp_path / "replace.png", value=0, width=COLS, height=ROWS)
    replace_zone = Zone(
        name="Fond",
        composition_mode=CompositionMode.REPLACE,
        geometry_params=_params(min_thickness_mm=0.2, max_thickness_mm=0.2),
        relief_mode=ReliefMode.SOLID,
    )
    sources = [
        ZoneSource(zone=base, image_path=str(base_image)),
        ZoneSource(zone=replace_zone, image_path=str(replace_image), mask=replace_mask),
    ]

    z_final, _, _, _ = compose_scene_heightfield(sources)

    inside = np.flipud(replace_mask) >= 0.5
    assert np.allclose(z_final[inside], 0.2, atol=1e-4)  # valeur du REPLACE seule, pas base+0.2


# ------------------------------------------------------------------ #
# 7. REPLACE puis ADD : l'ordre determine le resultat
# ------------------------------------------------------------------ #
def test_replace_then_add_respects_order(tmp_path, base_image):
    base = _base_zone()
    region_mask = np.zeros((ROWS, COLS), dtype=np.float32)
    region_mask[5:15, 5:20] = 1.0
    replace_image = make_uniform_image(tmp_path / "replace.png", value=0, width=COLS, height=ROWS)
    add_image = make_uniform_image(tmp_path / "add.png", value=0, width=COLS, height=ROWS)
    replace_zone = Zone(
        name="Remplace",
        composition_mode=CompositionMode.REPLACE,
        geometry_params=_params(min_thickness_mm=1.0, max_thickness_mm=1.0),
        relief_mode=ReliefMode.SOLID,
    )
    add_zone = Zone(
        name="Ajoute apres",
        composition_mode=CompositionMode.ADD,
        geometry_params=_params(min_thickness_mm=0.3, max_thickness_mm=0.3),
        relief_mode=ReliefMode.SOLID,
    )
    sources = [
        ZoneSource(zone=base, image_path=str(base_image)),
        ZoneSource(zone=replace_zone, image_path=str(replace_image), mask=region_mask),
        ZoneSource(zone=add_zone, image_path=str(add_image), mask=region_mask),
    ]

    z_final, _, _, _ = compose_scene_heightfield(sources)
    inside = np.flipud(region_mask) >= 0.5

    # REPLACE (1.0) puis ADD (0.3) applique par-dessus -> 1.3, pas juste 0.3
    assert np.allclose(z_final[inside], 1.3, atol=1e-4)


def test_add_then_replace_gives_a_different_result_reversed_order(tmp_path, base_image):
    """Confirme que l'ordre Scene.zones compte reellement : ADD puis REPLACE
    efface la contribution ADD dans le masque du REPLACE (contrairement au
    test precedent)."""
    base = _base_zone()
    region_mask = np.zeros((ROWS, COLS), dtype=np.float32)
    region_mask[5:15, 5:20] = 1.0
    replace_image = make_uniform_image(tmp_path / "replace.png", value=0, width=COLS, height=ROWS)
    add_image = make_uniform_image(tmp_path / "add.png", value=0, width=COLS, height=ROWS)
    replace_zone = Zone(
        name="Remplace",
        composition_mode=CompositionMode.REPLACE,
        geometry_params=_params(min_thickness_mm=1.0, max_thickness_mm=1.0),
        relief_mode=ReliefMode.SOLID,
    )
    add_zone = Zone(
        name="Ajoute avant",
        composition_mode=CompositionMode.ADD,
        geometry_params=_params(min_thickness_mm=0.3, max_thickness_mm=0.3),
        relief_mode=ReliefMode.SOLID,
    )
    sources = [
        ZoneSource(zone=base, image_path=str(base_image)),
        ZoneSource(zone=add_zone, image_path=str(add_image), mask=region_mask),
        ZoneSource(zone=replace_zone, image_path=str(replace_image), mask=region_mask),
    ]

    z_final, _, _, _ = compose_scene_heightfield(sources)
    inside = np.flipud(region_mask) >= 0.5

    assert np.allclose(z_final[inside], 1.0, atol=1e-4)  # REPLACE efface l'ADD precedent


# ------------------------------------------------------------------ #
# 8. Zones sans overlap : chacune contribue independamment
# ------------------------------------------------------------------ #
def test_non_overlapping_zones_are_independent_and_preserve_coordinates(tmp_path, base_image):
    base = _base_zone()
    mask_left = np.zeros((ROWS, COLS), dtype=np.float32)
    mask_left[:, :15] = 1.0
    mask_right = np.zeros((ROWS, COLS), dtype=np.float32)
    mask_right[:, 45:] = 1.0
    img_left = make_uniform_image(tmp_path / "left.png", value=0, width=COLS, height=ROWS)
    img_right = make_uniform_image(tmp_path / "right.png", value=0, width=COLS, height=ROWS)
    zone_left = Zone(
        name="Gauche",
        composition_mode=CompositionMode.ADD,
        geometry_params=_params(min_thickness_mm=0.4, max_thickness_mm=0.4),
        relief_mode=ReliefMode.SOLID,
    )
    zone_right = Zone(
        name="Droite",
        composition_mode=CompositionMode.ADD,
        geometry_params=_params(min_thickness_mm=0.9, max_thickness_mm=0.9),
        relief_mode=ReliefMode.SOLID,
    )
    sources = [
        ZoneSource(zone=base, image_path=str(base_image)),
        ZoneSource(zone=zone_left, image_path=str(img_left), mask=mask_left),
        ZoneSource(zone=zone_right, image_path=str(img_right), mask=mask_right),
    ]

    z_final, active_final, width_mm, height_mm = compose_scene_heightfield(sources)

    assert width_mm == WIDTH_MM
    assert height_mm == HEIGHT_MM
    left_region = np.flipud(mask_left) >= 0.5
    right_region = np.flipud(mask_right) >= 0.5
    base_region = active_final & ~left_region & ~right_region

    base_value = z_final[base_region][0]
    assert np.allclose(z_final[left_region], base_value + 0.4, atol=1e-4)
    assert np.allclose(z_final[right_region], base_value + 0.9, atol=1e-4)


# ------------------------------------------------------------------ #
# 9. Zone ADD sans support dessous : acceptee, jamais flottante
# ------------------------------------------------------------------ #
def test_add_zone_without_underlying_support_is_grounded_not_floating(tmp_path):
    """La zone BASE ne couvre qu'une partie de l'image ; la zone ADD deborde
    dessus. La partie sans support doit rester posee sur le plateau Z=0
    (jamais un volume detache dans l'espace) -- acceptee comme composante
    supplementaire, comme documente en conception."""
    base_image = make_uniform_image(tmp_path / "base.png", value=128, width=COLS, height=ROWS)
    base_mask = np.zeros((ROWS, COLS), dtype=np.float32)
    base_mask[:, :30] = 1.0  # base ne couvre que la moitie gauche
    base = Zone(
        name="Base partielle",
        composition_mode=CompositionMode.BASE,
        geometry_params=_params(),
        relief_mode=ReliefMode.LITHOPHANE,
    )

    add_mask = np.zeros((ROWS, COLS), dtype=np.float32)
    add_mask[15:25, 40:55] = 1.0  # entierement hors du masque de base
    add_image = make_uniform_image(tmp_path / "add.png", value=0, width=COLS, height=ROWS)
    add_zone = Zone(
        name="Sans support",
        composition_mode=CompositionMode.ADD,
        geometry_params=_params(min_thickness_mm=1.0, max_thickness_mm=1.0),
        relief_mode=ReliefMode.SOLID,
    )

    sources = [
        ZoneSource(zone=base, image_path=str(base_image), mask=base_mask),
        ZoneSource(zone=add_zone, image_path=str(add_image), mask=add_mask),
    ]

    mesh = compose_scene_mesh(sources)  # ne doit pas lever
    result = validate_mesh(mesh)

    assert result.is_valid  # toujours ferme/manifold, meme non entierement connecte
    assert result.connected_components == 2  # base + ilot ADD independant
    assert mesh.bounds[0][2] == pytest.approx(0.0, abs=1e-6)  # tout repose sur Z=0, rien en dessous


# ------------------------------------------------------------------ #
# 10. Masques soft : jamais modifies par la composition
# ------------------------------------------------------------------ #
def test_soft_masks_are_never_mutated_by_composition(tmp_path, base_image):
    base = _base_zone()
    soft_mask = np.full((ROWS, COLS), 0.5, dtype=np.float32)
    soft_mask[10:20, 10:20] = 0.9
    original = soft_mask.copy()
    add_image = make_uniform_image(tmp_path / "add.png", value=0, width=COLS, height=ROWS)
    add_zone = Zone(
        name="Soft",
        composition_mode=CompositionMode.ADD,
        geometry_params=_params(min_thickness_mm=0.6, max_thickness_mm=0.6),
        relief_mode=ReliefMode.SOLID,
    )
    sources = [
        ZoneSource(zone=base, image_path=str(base_image)),
        ZoneSource(zone=add_zone, image_path=str(add_image), mask=soft_mask),
    ]

    compose_scene_heightfield(sources)

    assert np.array_equal(soft_mask, original)


# ------------------------------------------------------------------ #
# Erreurs explicites
# ------------------------------------------------------------------ #
def test_composition_without_base_zone_raises_clear_error(tmp_path, base_image):
    add_zone = Zone(name="Seule", composition_mode=CompositionMode.ADD, geometry_params=_params())
    sources = [ZoneSource(zone=add_zone, image_path=str(base_image))]

    with pytest.raises(ValueError, match="BASE"):
        compose_scene_heightfield(sources)


def test_invisible_zone_is_excluded_from_composition(tmp_path, base_image):
    base = _base_zone()
    hidden_mask = np.zeros((ROWS, COLS), dtype=np.float32)
    hidden_mask[10:20, 20:35] = 1.0
    hidden_image = make_uniform_image(tmp_path / "hidden.png", value=0, width=COLS, height=ROWS)
    hidden_zone = Zone(
        name="Cachee",
        visible=False,
        composition_mode=CompositionMode.ADD,
        geometry_params=_params(min_thickness_mm=5.0, max_thickness_mm=5.0),
        relief_mode=ReliefMode.SOLID,
    )
    sources = [
        ZoneSource(zone=base, image_path=str(base_image)),
        ZoneSource(zone=hidden_zone, image_path=str(hidden_image), mask=hidden_mask),
    ]

    z_final, _, _, _ = compose_scene_heightfield(sources)
    inside = np.flipud(hidden_mask) >= 0.5
    outside = ~inside

    # aucune trace du +5mm de la zone cachee
    assert z_final[inside].max() == pytest.approx(z_final[outside].max(), abs=1e-3)
