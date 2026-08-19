import numpy as np
import pytest

from lithoshape3d.core.geometry.heightmap import Heightmap, heightmap_from_image_path
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.scene.models import GeometryParameters
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from tests.fixtures.synthetic_images import make_top_bright_image, make_uniform_image


def _params(**overrides) -> GeometryParameters:
    defaults = {
        "width_mm": 40.0,
        "height_mm": 30.0,
        "min_thickness_mm": 0.8,
        "max_thickness_mm": 3.0,
        "resolution": 2.0,
    }
    defaults.update(overrides)
    return GeometryParameters(**defaults)


def test_uniform_black_image_gives_uniform_max_thickness(tmp_path):
    image_path = make_uniform_image(tmp_path / "black.png", value=0)
    params = _params()

    heightmap = heightmap_from_image_path(image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)

    front_z = mesh.vertices[:, 2][mesh.vertices[:, 2] > 0]
    assert np.allclose(front_z, params.max_thickness_mm, atol=1e-3)


def test_uniform_white_image_gives_uniform_min_thickness(tmp_path):
    image_path = make_uniform_image(tmp_path / "white.png", value=255)
    params = _params()

    heightmap = heightmap_from_image_path(image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)

    result = validate_mesh(mesh)
    assert result.is_valid
    # Toute la face avant est a min_thickness : bounds Z = [0, min_thickness]
    assert mesh.bounds[1][2] == pytest.approx(params.min_thickness_mm, abs=1e-3)


def test_physical_dimensions_match_parameters(tmp_path):
    image_path = make_uniform_image(tmp_path / "mid.png", value=128, width=20, height=20)
    params = _params(width_mm=50.0, height_mm=35.0, min_thickness_mm=1.0, max_thickness_mm=4.0)

    heightmap = heightmap_from_image_path(image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)

    (x_min, y_min, z_min), (x_max, y_max, z_max) = mesh.bounds
    assert x_min == pytest.approx(0.0, abs=1e-6)
    assert x_max == pytest.approx(50.0, abs=1e-3)
    assert y_min == pytest.approx(0.0, abs=1e-6)
    assert y_max == pytest.approx(35.0, abs=1e-3)
    assert z_min == pytest.approx(0.0, abs=1e-6)
    assert z_max <= 4.0 + 1e-3


def test_orientation_top_of_image_maps_to_high_y(tmp_path):
    """Detecte un flip vertical accidentel entre coordonnees image et 3D.

    Image : moitie superieure blanche (-> mince), moitie inferieure noire
    (-> epaisse). Convention documentee : le haut de l'image doit se
    retrouver a Y eleve dans le modele.
    """
    image_path = make_top_bright_image(tmp_path / "top_bright.png", width=20, height=20)
    params = _params(width_mm=40.0, height_mm=40.0, resolution=2.0)

    heightmap = heightmap_from_image_path(image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)

    front_vertices = mesh.vertices[mesh.vertices[:, 2] > 1e-6]
    mid_y = params.height_mm / 2
    upper = front_vertices[front_vertices[:, 1] > mid_y]
    lower = front_vertices[front_vertices[:, 1] < mid_y]

    assert upper[:, 2].mean() < lower[:, 2].mean()
    assert upper[:, 2].mean() == pytest.approx(params.min_thickness_mm, abs=1e-2)
    assert lower[:, 2].mean() == pytest.approx(params.max_thickness_mm, abs=1e-2)


def test_invert_flag_swaps_thickness_direction(tmp_path):
    image_path = make_uniform_image(tmp_path / "black.png", value=0)
    params_normal = _params(invert=False)
    params_inverted = _params(invert=True)

    heightmap = heightmap_from_image_path(image_path, params_normal)
    mesh_normal = build_slab_mesh(heightmap, mask=None, params=params_normal)
    mesh_inverted = build_slab_mesh(heightmap, mask=None, params=params_inverted)

    assert mesh_normal.bounds[1][2] == pytest.approx(params_normal.max_thickness_mm, abs=1e-3)
    assert mesh_inverted.bounds[1][2] == pytest.approx(params_inverted.min_thickness_mm, abs=1e-3)


def test_mesh_is_watertight_and_manifold(tmp_path):
    image_path = make_uniform_image(tmp_path / "mid.png", value=128)
    params = _params()

    heightmap = heightmap_from_image_path(image_path, params)
    mesh = build_slab_mesh(heightmap, mask=None, params=params)
    result = validate_mesh(mesh)

    assert result.is_watertight
    assert result.is_winding_consistent
    assert result.volume_mm3 > 0
    assert not result.has_degenerate_faces
    assert not result.has_nan_or_inf
    assert result.manifold3d_compatible
    assert result.is_valid


def test_mesh_watertight_across_several_resolutions(tmp_path):
    image_path = make_uniform_image(tmp_path / "grad.png", value=180, width=40, height=25)

    for resolution in (5.0, 2.0, 1.0):
        params = _params(resolution=resolution)
        heightmap = heightmap_from_image_path(image_path, params)
        mesh = build_slab_mesh(heightmap, mask=None, params=params)
        result = validate_mesh(mesh)
        assert result.is_valid, f"resolution={resolution} invalide: {result.issues()}"


def test_rejects_non_rectangle_base_shape():
    heightmap = Heightmap(values=np.full((4, 4), 0.5, dtype=np.float32))
    params = _params(base_shape="cylinder")
    with pytest.raises(NotImplementedError):
        build_slab_mesh(heightmap, mask=None, params=params)


def test_rejects_partial_mask():
    heightmap = Heightmap(values=np.full((4, 4), 0.5, dtype=np.float32))
    params = _params()
    mask = np.ones((4, 4), dtype=bool)
    mask[0, 0] = False
    with pytest.raises(NotImplementedError):
        build_slab_mesh(heightmap, mask=mask, params=params)


def test_fully_active_mask_behaves_like_no_mask():
    heightmap = Heightmap(values=np.full((4, 4), 0.5, dtype=np.float32))
    params = _params()
    mask = np.ones((4, 4), dtype=bool)

    mesh_with_mask = build_slab_mesh(heightmap, mask=mask, params=params)
    mesh_without_mask = build_slab_mesh(heightmap, mask=None, params=params)

    assert np.allclose(mesh_with_mask.vertices, mesh_without_mask.vertices)
