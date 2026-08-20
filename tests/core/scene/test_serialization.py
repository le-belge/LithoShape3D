import pytest

from lithoshape3d.core.scene import GeometryParameters, Project, Scene, Zone
from lithoshape3d.core.scene.serialization import (
    load_project,
    project_from_dict,
    project_to_dict,
    save_project,
)


def _sample_project() -> Project:
    zone = Zone(
        name="sujet",
        source_image_path="images/photo.jpg",
        geometry_params=GeometryParameters(
            width_mm=100.0,
            height_mm=140.0,
            invert=True,
            resolution=0.15,
            base_shape="rectangle",
        ),
    )
    return Project(name="mon-projet", scene=Scene(zones=[zone]))


def test_roundtrip_dict():
    project = _sample_project()

    data = project_to_dict(project)
    restored = project_from_dict(data)

    assert restored.name == project.name
    assert restored.format_version == project.format_version
    assert len(restored.scene.zones) == 1
    assert restored.scene.zones[0].name == "sujet"
    assert restored.scene.zones[0].geometry_params.width_mm == 100.0
    assert restored.scene.zones[0].geometry_params.invert is True
    assert restored.scene.zones[0].geometry_params.resolution == pytest.approx(0.15)
    assert restored.scene.zones[0].geometry_params.base_shape == "rectangle"


def test_serialized_dict_carries_format_version():
    data = project_to_dict(_sample_project())

    assert data["format_version"] == 3


def test_roundtrip_file(tmp_path):
    project = _sample_project()
    path = tmp_path / "test.lithoproj.json"

    save_project(project, path)
    restored = load_project(path)

    assert restored.name == project.name
    assert restored.scene.zones[0].source_image_path == "images/photo.jpg"
