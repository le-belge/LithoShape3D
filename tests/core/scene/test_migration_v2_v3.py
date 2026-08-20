import copy

from lithoshape3d.core.scene.serialization import project_from_dict

_V2_MULTI_ZONE = {
    "format_version": 2,
    "name": "projet-v2",
    "scene": {
        "zones": [
            {
                "id": "zone-1",
                "name": "Lithophanie",
                "visible": True,
                "source_image_path": None,
                "mask_path": None,
                "geometry_params": {"width_mm": 100.0, "height_mm": 80.0},
                "material": {},
                "transform": {},
                "relief_mode": "lithophane",
                "mesh_cache_path": None,
            },
            {
                "id": "zone-2",
                "name": "Detail",
                "visible": True,
                "source_image_path": None,
                "mask_path": "masks/zone-2.png",
                "geometry_params": {"width_mm": 100.0, "height_mm": 80.0},
                "material": {},
                "transform": {},
                "relief_mode": "lithophane",
                "mesh_cache_path": None,
            },
        ],
        "source_image_path": "source/photo.jpg",
        "active_zone_id": "zone-1",
    },
}


def test_v2_migration_sets_first_zone_to_base():
    project = project_from_dict(copy.deepcopy(_V2_MULTI_ZONE))

    assert project.format_version == 3
    assert project.scene.zones[0].composition_mode.value == "base"


def test_v2_migration_sets_subsequent_zones_to_replace_not_add():
    """Choix documente : REPLACE (pas ADD) pour ne pas cumuler silencieusement
    des epaisseurs qui n'ont jamais ete composees auparavant."""
    project = project_from_dict(copy.deepcopy(_V2_MULTI_ZONE))

    assert project.scene.zones[1].composition_mode.value == "replace"


def test_v2_migration_preserves_all_other_fields():
    project = project_from_dict(copy.deepcopy(_V2_MULTI_ZONE))

    assert project.scene.zones[1].mask_path == "masks/zone-2.png"
    assert project.scene.source_image_path == "source/photo.jpg"
    assert project.scene.active_zone_id == "zone-1"


def test_v3_project_with_explicit_composition_mode_is_not_overridden():
    data = copy.deepcopy(_V2_MULTI_ZONE)
    data["format_version"] = 3
    data["scene"]["zones"][0]["composition_mode"] = "add"

    project = project_from_dict(data)

    assert project.scene.zones[0].composition_mode.value == "add"
