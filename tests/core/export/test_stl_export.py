import pytest

from lithoshape3d.core.export.stl_export import export_stl, load_stl
from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.scene.models import GeometryParameters
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from tests.fixtures.synthetic_images import make_gradient_image


def _sample_mesh(tmp_path):
    image_path = make_gradient_image(tmp_path / "gradient.png", width=32, height=24)
    params = GeometryParameters(width_mm=40.0, height_mm=30.0, resolution=2.0)
    heightmap = heightmap_from_image_path(image_path, params)
    return build_slab_mesh(heightmap, mask=None, params=params), params


def test_export_creates_a_non_empty_file(tmp_path):
    mesh, _ = _sample_mesh(tmp_path)
    stl_path = tmp_path / "out.stl"

    export_stl(mesh, stl_path)

    assert stl_path.exists()
    assert stl_path.stat().st_size > 0


def test_stl_roundtrip_preserves_dimensions(tmp_path):
    mesh, params = _sample_mesh(tmp_path)
    stl_path = tmp_path / "out.stl"
    export_stl(mesh, stl_path)

    reloaded = load_stl(stl_path)

    assert reloaded.bounds[1][0] == pytest.approx(params.width_mm, abs=1e-2)
    assert reloaded.bounds[1][1] == pytest.approx(params.height_mm, abs=1e-2)
    assert reloaded.volume == pytest.approx(mesh.volume, rel=1e-3)


def test_stl_roundtrip_stays_watertight_and_manifold(tmp_path):
    mesh, _ = _sample_mesh(tmp_path)
    stl_path = tmp_path / "out.stl"
    export_stl(mesh, stl_path)

    reloaded = load_stl(stl_path)
    result = validate_mesh(reloaded)

    assert result.is_valid, result.issues()
