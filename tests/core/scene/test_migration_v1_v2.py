import copy

from lithoshape3d.core.scene.serialization import project_from_dict

_V1_SINGLE_ZONE = {
    "format_version": 1,
    "name": "ancien-projet",
    "scene": {
        "zones": [
            {
                "id": "zone-1",
                "name": "Lithophanie",
                "source_image_path": "images/photo.jpg",
                "mask_path": None,
                "geometry_params": {"width_mm": 100.0, "height_mm": 140.0},
                "material": {},
                "transform": {},
                "relief_mode": "lithophane",
                "mesh_cache_path": None,
            }
        ]
    },
}

_V1_MULTI_ZONE_ATYPICAL = {
    "format_version": 1,
    "name": "projet-manuel",
    "scene": {
        "zones": [
            {
                "id": "zone-a",
                "name": "Sans image",
                "source_image_path": None,
                "mask_path": None,
                "geometry_params": {"width_mm": 50.0, "height_mm": 50.0},
                "material": {},
                "transform": {},
                "relief_mode": "lithophane",
                "mesh_cache_path": None,
            },
            {
                "id": "zone-b",
                "name": "Sujet",
                "source_image_path": "images/portrait.jpg",
                "mask_path": None,
                "geometry_params": {"width_mm": 80.0, "height_mm": 120.0},
                "material": {},
                "transform": {},
                "relief_mode": "lithophane",
                "mesh_cache_path": None,
            },
            {
                "id": "zone-c",
                "name": "Logo different",
                "source_image_path": "images/logo.png",
                "mask_path": None,
                "geometry_params": {"width_mm": 20.0, "height_mm": 20.0},
                "material": {},
                "transform": {},
                "relief_mode": "solid",
                "mesh_cache_path": None,
            },
        ]
    },
}


def test_v1_single_zone_migrates_source_to_scene():
    project = project_from_dict(copy.deepcopy(_V1_SINGLE_ZONE))

    assert project.format_version == 6  # migration chainee v1 -> v2 -> v3 -> v4 -> v5 -> v6
    assert project.scene.source_image_path == "images/photo.jpg"
    assert project.scene.zones[0].source_image_path is None  # promu, plus de doublon
    assert project.scene.zones[0].visible is True
    assert project.scene.active_zone_id == "zone-1"
    assert project.scene.zones[0].composition_mode.value == "base"  # premiere zone -> BASE


def test_v1_atypical_multi_zone_keeps_all_zones():
    project = project_from_dict(copy.deepcopy(_V1_MULTI_ZONE_ATYPICAL))

    assert len(project.scene.zones) == 3
    # premiere zone AVEC source valide (zone-a n'en a pas) -> promue
    assert project.scene.source_image_path == "images/portrait.jpg"


def test_v1_atypical_preserves_differing_source_as_override():
    project = project_from_dict(copy.deepcopy(_V1_MULTI_ZONE_ATYPICAL))
    zones_by_id = {z.id: z for z in project.scene.zones}

    assert zones_by_id["zone-a"].source_image_path is None
    assert zones_by_id["zone-b"].source_image_path is None  # == source promue -> nettoye
    assert zones_by_id["zone-c"].source_image_path == "images/logo.png"  # different -> conserve


def test_v1_migration_sets_active_zone_to_first_zone():
    project = project_from_dict(copy.deepcopy(_V1_MULTI_ZONE_ATYPICAL))

    assert project.scene.active_zone_id == "zone-a"


def test_project_from_dict_does_not_mutate_caller_dict():
    caller_dict = copy.deepcopy(_V1_MULTI_ZONE_ATYPICAL)
    snapshot = copy.deepcopy(caller_dict)

    project_from_dict(caller_dict)

    assert caller_dict == snapshot  # la migration ne doit pas alterer l'argument recu


def test_active_zone_id_absent_falls_back_to_first_zone():
    data = copy.deepcopy(_V1_SINGLE_ZONE)
    data["format_version"] = 2
    data["scene"]["source_image_path"] = "images/photo.jpg"
    data["scene"].pop("active_zone_id", None)

    project = project_from_dict(data)

    assert project.scene.active_zone_id == "zone-1"


def test_active_zone_id_invalid_falls_back_to_first_zone():
    data = copy.deepcopy(_V1_SINGLE_ZONE)
    data["format_version"] = 2
    data["scene"]["source_image_path"] = "images/photo.jpg"
    data["scene"]["active_zone_id"] = "id-inexistant"

    project = project_from_dict(data)

    assert project.scene.active_zone_id == "zone-1"


def test_active_zone_id_none_when_no_zones():
    data = {"format_version": 2, "name": "vide", "scene": {"zones": [], "source_image_path": None}}

    project = project_from_dict(data)

    assert project.scene.active_zone_id is None
