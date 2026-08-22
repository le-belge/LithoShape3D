import copy

from lithoshape3d.core.scene.models import ColorStrategy
from lithoshape3d.core.scene.serialization import project_from_dict

_V5_PROJECT = {
    "format_version": 5,
    "name": "projet-v5",
    "scene": {
        "zones": [
            {
                "id": "zone-1",
                "name": "Lithophanie",
                "visible": True,
                "source_image_path": None,
                "mask_path": None,
                "geometry_params": {"width_mm": 100.0, "height_mm": 80.0},
                "material": {"name": "Blanc"},
                "transform": {},
                "relief_mode": "lithophane",
                "composition_mode": "base",
                "mesh_cache_path": None,
            },
            {
                "id": "zone-2",
                "name": "Rose",
                "visible": True,
                "source_image_path": None,
                "mask_path": None,
                "geometry_params": {"width_mm": 100.0, "height_mm": 80.0},
                "material": {"name": "Rose"},
                "transform": {},
                "relief_mode": "solid",
                "composition_mode": "replace",
                "mesh_cache_path": None,
            },
        ],
        "source_image_path": "source/photo.jpg",
        "active_zone_id": "zone-1",
        "support": {"support_type": "none"},
        "shape": {"shape_type": "rectangle"},
        "image_transform": {"offset_x": 0.0, "offset_y": 0.0, "scale": 1.0, "rotation_deg": 0.0, "fit_mode": "fill"},
    },
}


def test_v5_migration_defaults_every_zone_to_no_color_strategy():
    """Comportement historique intact : une zone REPLACE existante (ex. une
    gravure ou un ancien contournement "rose" manuel) doit continuer a
    affecter la geometrie exactement comme avant -- `color_strategy=None`
    explicite, pas `MATERIAL_ONLY`, qui changerait silencieusement son rendu."""
    project = project_from_dict(copy.deepcopy(_V5_PROJECT))

    assert project.format_version == 6
    for zone in project.scene.zones:
        assert zone.color_strategy is None


def test_v5_migration_gives_every_zone_harmless_default_backlight_params():
    project = project_from_dict(copy.deepcopy(_V5_PROJECT))

    for zone in project.scene.zones:
        assert zone.backlight_insert.white_skin_thickness_mm == 0.40
        assert zone.backlight_insert.insert_thickness_mm == 0.60
        assert zone.backlight_insert.xy_clearance_mm == 0.20


def test_v5_migration_preserves_existing_zones_and_shape():
    project = project_from_dict(copy.deepcopy(_V5_PROJECT))

    assert len(project.scene.zones) == 2
    assert project.scene.zones[1].name == "Rose"
    assert project.scene.zones[1].material.name == "Rose"
    assert project.scene.source_image_path == "source/photo.jpg"


def test_zone_with_explicit_color_strategy_roundtrips(tmp_path):
    """Une fois qu'un projet a explicitement une zone MATERIAL_ONLY (deja en
    v6, pas migree), elle doit survivre a un aller-retour dict tel quel."""
    from lithoshape3d.core.scene.models import (
        CompositionMode,
        GeometryParameters,
        Project,
        Scene,
        Zone,
    )
    from lithoshape3d.core.scene.serialization import project_from_dict, project_to_dict

    zone = Zone(
        name="Rose",
        composition_mode=CompositionMode.ADD,
        geometry_params=GeometryParameters(width_mm=100.0, height_mm=100.0),
        color_strategy=ColorStrategy.MATERIAL_ONLY,
    )
    project = Project(scene=Scene(zones=[zone]))

    restored = project_from_dict(project_to_dict(project))

    assert restored.scene.zones[0].color_strategy is ColorStrategy.MATERIAL_ONLY
