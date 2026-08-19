import numpy as np
import pytest
import pyvista as pv

from lithoshape3d.core.geometry.heightmap import Heightmap
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.scene.models import GeometryParameters
from lithoshape3d.viewer.scene_viewer import DisplayMode, SceneViewer


def _sample_mesh():
    heightmap = Heightmap(values=np.full((6, 8), 0.5, dtype=np.float32))
    params = GeometryParameters(width_mm=40.0, height_mm=30.0, resolution=5.0)
    return build_slab_mesh(heightmap, mask=None, params=params)


@pytest.fixture
def offscreen_plotter():
    plotter = pv.Plotter(off_screen=True, window_size=(200, 150))
    yield plotter
    plotter.close()


def test_show_mesh_adds_an_actor(offscreen_plotter):
    viewer = SceneViewer(offscreen_plotter)
    mesh = _sample_mesh()

    viewer.show_mesh(mesh)

    assert viewer._mesh_actor is not None
    assert len(offscreen_plotter.renderer.actors) >= 1


def test_show_mesh_replaces_previous_actor_without_leaking(offscreen_plotter):
    viewer = SceneViewer(offscreen_plotter)
    mesh = _sample_mesh()

    viewer.show_mesh(mesh)
    actor_count_after_first = len(offscreen_plotter.renderer.actors)
    viewer.show_mesh(mesh)
    actor_count_after_second = len(offscreen_plotter.renderer.actors)

    assert actor_count_after_first == actor_count_after_second


@pytest.mark.parametrize("mode", list(DisplayMode))
def test_all_display_modes_render_without_error(offscreen_plotter, mode):
    viewer = SceneViewer(offscreen_plotter)
    viewer.show_mesh(_sample_mesh(), display_mode=mode)
    offscreen_plotter.render()


@pytest.mark.parametrize(
    "view_method",
    ["view_front", "view_back", "view_left", "view_right", "view_top", "view_isometric"],
)
def test_view_presets_run_without_error(offscreen_plotter, view_method):
    viewer = SceneViewer(offscreen_plotter)
    viewer.show_mesh(_sample_mesh())

    getattr(viewer, view_method)()

    position = offscreen_plotter.camera.position
    assert all(np.isfinite(position))


def test_view_front_looks_along_z_with_y_up(offscreen_plotter):
    viewer = SceneViewer(offscreen_plotter)
    viewer.show_mesh(_sample_mesh())

    viewer.view_front()

    camera = offscreen_plotter.camera
    direction = np.array(camera.position) - np.array(camera.focal_point)
    direction /= np.linalg.norm(direction)

    assert direction[2] == pytest.approx(1.0, abs=1e-6)
    assert direction[0] == pytest.approx(0.0, abs=1e-6)
    assert direction[1] == pytest.approx(0.0, abs=1e-6)
    assert tuple(round(v, 6) for v in camera.up) == (0.0, 1.0, 0.0)


def test_reset_camera_does_not_raise(offscreen_plotter):
    viewer = SceneViewer(offscreen_plotter)
    viewer.show_mesh(_sample_mesh())
    viewer.view_top()

    viewer.reset_camera()  # ne doit pas lever, ne change pas l'orientation
