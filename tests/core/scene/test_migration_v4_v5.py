import copy

from lithoshape3d.core.scene.models import ShapeType
from lithoshape3d.core.scene.serialization import project_from_dict

_V4_PROJECT = {
    "format_version": 4,
    "name": "projet-v4",
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
                "composition_mode": "base",
                "mesh_cache_path": None,
            }
        ],
        "source_image_path": "source/photo.jpg",
        "active_zone_id": "zone-1",
        "support": {"support_type": "none"},
    },
}


def test_v4_migration_defaults_to_rectangle_shape():
    project = project_from_dict(copy.deepcopy(_V4_PROJECT))

    assert project.format_version == 6
    assert project.scene.shape.shape_type is ShapeType.RECTANGLE


def test_v4_migration_produces_identity_image_transform():
    """Un projet migre ne doit pas changer visuellement : le cadrage par
    defaut doit reproduire le comportement historique (image etiree pour
    couvrir exactement la grille, cf. core/image/transform.py)."""
    project = project_from_dict(copy.deepcopy(_V4_PROJECT))

    transform = project.scene.image_transform
    assert transform.offset_x == 0.0
    assert transform.offset_y == 0.0
    assert transform.scale == 1.0
    assert transform.rotation_deg == 0.0


def test_v4_migration_preserves_existing_zones_and_support():
    project = project_from_dict(copy.deepcopy(_V4_PROJECT))

    assert len(project.scene.zones) == 1
    assert project.scene.zones[0].name == "Lithophanie"
    assert project.scene.source_image_path == "source/photo.jpg"
