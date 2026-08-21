from lithoshape3d.core.scene import GeometryParameters, Project, Scene, Zone


def test_project_default_format_version():
    project = Project()

    assert project.format_version == 5
    assert isinstance(project.scene, Scene)
    assert project.scene.zones == []


def test_scene_can_hold_multiple_zones():
    scene = Scene()
    zone_a = Zone(name="sujet", geometry_params=GeometryParameters(80.0, 120.0))
    zone_b = Zone(name="arriere-plan", geometry_params=GeometryParameters(80.0, 120.0))

    scene.zones.append(zone_a)
    scene.zones.append(zone_b)

    assert len(scene.zones) == 2
    assert scene.zones[0].id != scene.zones[1].id


def test_zone_default_relief_mode_is_lithophane():
    zone = Zone()

    assert zone.relief_mode.value == "lithophane"
    assert zone.mesh_cache_path is None


def test_zone_default_visible_and_no_image_override():
    zone = Zone()

    assert zone.visible is True
    assert zone.source_image_path is None


def test_scene_default_source_image_and_active_zone():
    scene = Scene()

    assert scene.source_image_path is None
    assert scene.active_zone_id is None
