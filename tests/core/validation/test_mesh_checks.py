import numpy as np
import trimesh

from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.scene.models import GeometryParameters
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from tests.fixtures.synthetic_images import make_uniform_image


def test_valid_slab_mesh_passes_validation(tmp_path):
    image_path = make_uniform_image(tmp_path / "mid.png", value=128)
    params = GeometryParameters(width_mm=30.0, height_mm=20.0, resolution=2.0)

    heightmap = heightmap_from_image_path(image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)
    result = validate_mesh(mesh)

    assert result.is_valid
    assert result.issues() == []


def test_open_mesh_is_rejected():
    """Un unique triangle ouvert doit etre detecte comme invalide (watertight
    False, rejete par manifold3d) - la validation ne doit pas se contenter
    d'accepter n'importe quel mesh."""
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    faces = np.array([[0, 1, 2]])
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

    result = validate_mesh(mesh)

    assert not result.is_watertight
    assert not result.manifold3d_compatible
    assert not result.is_valid
    assert "watertight" in " ".join(result.issues())


def test_nan_vertex_is_detected():
    vertices = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [np.nan, 0, 1]], dtype=np.float64
    )
    faces = np.array([[0, 1, 2], [0, 1, 3]])
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

    result = validate_mesh(mesh)

    assert result.has_nan_or_inf
    assert not result.is_valid
