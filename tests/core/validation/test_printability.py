import numpy as np

from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.geometry.shape import build_shape_mask, count_connected_components
from lithoshape3d.core.scene.models import GeometryParameters, ShapeParams, ShapeType
from lithoshape3d.core.validation.printability import _thin_regions_detected, check_printability
from tests.fixtures.synthetic_images import make_uniform_image


def _rectangle_slab(tmp_path, width_mm=30.0, height_mm=20.0, resolution=2.0):
    image_path = make_uniform_image(tmp_path / "mid.png", value=128)
    params = GeometryParameters(width_mm=width_mm, height_mm=height_mm, resolution=resolution)
    heightmap = heightmap_from_image_path(image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)
    return mesh, params


def test_valid_rectangle_slab_is_printable(tmp_path):
    mesh, _params = _rectangle_slab(tmp_path)

    report = check_printability(mesh)

    assert report.is_printable
    assert report.errors == []
    assert report.width_mm > 0
    assert report.height_mm > 0
    assert report.depth_mm > 0
    assert report.disjoint_components == 1


def test_invalid_mesh_reports_errors_and_is_not_printable():
    import trimesh

    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    faces = np.array([[0, 1, 2]])
    open_mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

    report = check_printability(open_mesh)

    assert not report.is_printable
    assert report.errors != []


def test_disjoint_shape_mask_is_reported_as_warning(tmp_path):
    mesh, params = _rectangle_slab(tmp_path)
    rows, cols = 20, 30
    # deux blocs disjoints (simule une lettre "i" : point + hampe)
    mask = np.zeros((rows, cols), dtype=bool)
    mask[0:3, 10:20] = True
    mask[8:rows, 10:20] = True

    report = check_printability(mesh, shape_mask=mask, pixel_size_mm=params.resolution)

    assert report.disjoint_components == 2
    assert any("composantes disjointes" in w for w in report.warnings)


def test_connected_shape_mask_reports_single_component(tmp_path):
    mesh, params = _rectangle_slab(tmp_path)
    rows, cols = 20, 30
    mask = np.ones((rows, cols), dtype=bool)

    report = check_printability(mesh, shape_mask=mask, pixel_size_mm=params.resolution)

    assert report.disjoint_components == 1
    assert not any("composantes disjointes" in w for w in report.warnings)


def test_thin_region_is_detected():
    rows, cols = 100, 100
    mask = np.zeros((rows, cols), dtype=bool)
    mask[40:60, 40:60] = True  # bloc large, bien au-dessus du seuil
    mask[10:12, :] = True  # bande fine (2 px = 0.4mm a 0.2mm/px), sous le seuil de 0.8mm

    thin = _thin_regions_detected(mask, pixel_size_mm=0.2, min_feature_mm=0.8)

    assert thin is True


def test_thick_region_alone_is_not_flagged_as_thin():
    rows, cols = 100, 100
    mask = np.zeros((rows, cols), dtype=bool)
    mask[20:80, 20:80] = True  # bloc large et uniforme

    thin = _thin_regions_detected(mask, pixel_size_mm=0.2, min_feature_mm=0.8)

    assert thin is False


def test_star_shape_mask_matches_reported_component_count():
    params = ShapeParams(shape_type=ShapeType.STAR)
    mask = build_shape_mask(params, rows=100, cols=100)

    assert count_connected_components(mask) == 1
