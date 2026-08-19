import numpy as np

from lithoshape3d.core.geometry.heightmap import Heightmap, heightmap_from_image_path
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.scene.models import GeometryParameters
from lithoshape3d.viewer.adapter import mesh_to_polydata
from tests.fixtures.synthetic_images import make_gradient_image


def _sample_mesh():
    heightmap = Heightmap(values=np.full((6, 8), 0.5, dtype=np.float32))
    params = GeometryParameters(width_mm=40.0, height_mm=30.0, resolution=5.0)
    return build_slab_mesh(heightmap, mask=None, params=params)


def test_polydata_preserves_point_count():
    mesh = _sample_mesh()
    polydata = mesh_to_polydata(mesh)
    assert polydata.n_points == len(mesh.vertices)


def test_polydata_preserves_face_count():
    mesh = _sample_mesh()
    polydata = mesh_to_polydata(mesh)
    assert polydata.n_faces == len(mesh.faces)


def test_polydata_preserves_bounds():
    mesh = _sample_mesh()
    polydata = mesh_to_polydata(mesh)

    expected = mesh.bounds  # [[xmin,ymin,zmin],[xmax,ymax,zmax]]
    actual = polydata.bounds  # (xmin,xmax,ymin,ymax,zmin,zmax)

    assert actual[0] == expected[0][0]
    assert actual[1] == expected[1][0]
    assert actual[2] == expected[0][1]
    assert actual[3] == expected[1][1]
    assert actual[4] == expected[0][2]
    assert actual[5] == expected[1][2]


def test_polydata_preserves_physical_dimensions_from_real_image(tmp_path):
    image_path = make_gradient_image(tmp_path / "gradient.png", width=40, height=30)
    params = GeometryParameters(width_mm=60.0, height_mm=45.0, resolution=2.0)
    heightmap = heightmap_from_image_path(image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)

    polydata = mesh_to_polydata(mesh)

    assert polydata.bounds[1] - polydata.bounds[0] == params.width_mm
    assert polydata.bounds[3] - polydata.bounds[2] == params.height_mm


def test_adapter_does_not_mutate_source_mesh():
    mesh = _sample_mesh()
    vertices_before = mesh.vertices.copy()
    faces_before = mesh.faces.copy()

    mesh_to_polydata(mesh)

    assert np.array_equal(mesh.vertices, vertices_before)
    assert np.array_equal(mesh.faces, faces_before)


def test_adapter_returns_independent_copy_of_vertices():
    mesh = _sample_mesh()
    polydata = mesh_to_polydata(mesh)

    polydata.points[0] = [999.0, 999.0, 999.0]

    assert not np.array_equal(mesh.vertices[0], [999.0, 999.0, 999.0])
