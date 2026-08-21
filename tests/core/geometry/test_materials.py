"""Partition de la geometrie composee par materiau (v0.3)."""

import pytest

from lithoshape3d.core.geometry.composition import ZoneSource, compose_scene_mesh
from lithoshape3d.core.geometry.materials import partition_mesh_by_material
from lithoshape3d.core.scene.models import (
    CompositionMode,
    GeometryParameters,
    Material,
    ReliefMode,
    Zone,
)
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from tests.fixtures.synthetic_images import make_uniform_image
from tests.fixtures.synthetic_masks import circle_mask

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


def test_single_material_shortcuts_to_full_composed_mesh(base_image):
    zone = Zone(
        name="Blanc",
        composition_mode=CompositionMode.BASE,
        geometry_params=_params(),
        relief_mode=ReliefMode.LITHOPHANE,
        material=Material(name="Blanc"),
    )
    sources = [ZoneSource(zone=zone, image_path=str(base_image))]

    partition = partition_mesh_by_material(sources)
    full_mesh = compose_scene_mesh(sources)

    assert list(partition.keys()) == ["Blanc"]
    assert partition["Blanc"].vertices.shape == full_mesh.vertices.shape


def test_two_materials_produce_two_watertight_aligned_bodies(base_image):
    white_zone = Zone(
        name="Fond",
        composition_mode=CompositionMode.BASE,
        geometry_params=_params(),
        relief_mode=ReliefMode.LITHOPHANE,
        material=Material(name="Blanc"),
    )
    rose_mask = circle_mask(ROWS, COLS, radius_fraction=0.2)
    rose_zone = Zone(
        name="Rose",
        composition_mode=CompositionMode.REPLACE,
        geometry_params=_params(),
        relief_mode=ReliefMode.LITHOPHANE,
        material=Material(name="Rose"),
    )
    sources = [
        ZoneSource(zone=white_zone, image_path=str(base_image)),
        ZoneSource(zone=rose_zone, image_path=str(base_image), mask=rose_mask),
    ]

    partition = partition_mesh_by_material(sources)

    assert set(partition.keys()) == {"Blanc", "Rose"}
    for mesh in partition.values():
        result = validate_mesh(mesh)
        assert result.is_watertight
        assert result.is_winding_consistent
        assert result.manifold3d_compatible

    # meme repere XYZ : aucun corps ne doit deborder du plateau canonique
    # (pas de recadrage/decalage independant entre materiaux).
    assert partition["Blanc"].bounds[0][0] >= -1e-6
    assert partition["Rose"].bounds[0][0] >= -1e-6
    assert partition["Blanc"].bounds[1][0] <= WIDTH_MM + 1e-3
    assert partition["Rose"].bounds[1][0] <= WIDTH_MM + 1e-3


def test_materials_do_not_overlap_in_volume(base_image):
    """Somme des volumes des corps ~= volume du mesh compose complet (pas de
    double-comptage massif entre materiaux)."""
    white_zone = Zone(
        name="Fond",
        composition_mode=CompositionMode.BASE,
        geometry_params=_params(),
        relief_mode=ReliefMode.LITHOPHANE,
        material=Material(name="Blanc"),
    )
    rose_mask = circle_mask(ROWS, COLS, radius_fraction=0.2)
    rose_zone = Zone(
        name="Rose",
        composition_mode=CompositionMode.REPLACE,
        geometry_params=_params(),
        relief_mode=ReliefMode.LITHOPHANE,
        material=Material(name="Rose"),
    )
    sources = [
        ZoneSource(zone=white_zone, image_path=str(base_image)),
        ZoneSource(zone=rose_zone, image_path=str(base_image), mask=rose_mask),
    ]

    partition = partition_mesh_by_material(sources)
    full_mesh = compose_scene_mesh(sources)

    total_partitioned_volume = sum(m.volume for m in partition.values())
    assert total_partitioned_volume == pytest.approx(full_mesh.volume, rel=0.05)


def test_same_material_name_across_zones_merges_into_one_body(base_image):
    white_zone = Zone(
        name="Fond",
        composition_mode=CompositionMode.BASE,
        geometry_params=_params(),
        relief_mode=ReliefMode.LITHOPHANE,
        material=Material(name="Blanc"),
    )
    detail_mask = circle_mask(ROWS, COLS, radius_fraction=0.2)
    detail_zone = Zone(
        name="Detail blanc aussi",
        composition_mode=CompositionMode.ADD,
        geometry_params=_params(min_thickness_mm=0.2, max_thickness_mm=0.6),
        relief_mode=ReliefMode.RELIEF,
        material=Material(name="Blanc"),  # meme materiau que la zone de fond
    )
    sources = [
        ZoneSource(zone=white_zone, image_path=str(base_image)),
        ZoneSource(zone=detail_zone, image_path=str(base_image), mask=detail_mask),
    ]

    partition = partition_mesh_by_material(sources)

    assert list(partition.keys()) == ["Blanc"]


def test_invisible_zone_is_excluded_from_partition(base_image):
    white_zone = Zone(
        name="Fond",
        composition_mode=CompositionMode.BASE,
        geometry_params=_params(),
        relief_mode=ReliefMode.LITHOPHANE,
        material=Material(name="Blanc"),
    )
    hidden_mask = circle_mask(ROWS, COLS, radius_fraction=0.2)
    hidden_zone = Zone(
        name="Cachee",
        visible=False,
        composition_mode=CompositionMode.REPLACE,
        geometry_params=_params(),
        relief_mode=ReliefMode.LITHOPHANE,
        material=Material(name="Rose"),
    )
    sources = [
        ZoneSource(zone=white_zone, image_path=str(base_image)),
        ZoneSource(zone=hidden_zone, image_path=str(base_image), mask=hidden_mask),
    ]

    partition = partition_mesh_by_material(sources)

    assert set(partition.keys()) == {"Blanc"}
