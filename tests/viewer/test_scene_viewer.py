import numpy as np
import pytest
import pyvista as pv

from lithoshape3d.core.geometry.heightmap import Heightmap
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.scene.models import GeometryParameters
from lithoshape3d.viewer.scene_viewer import (
    DisplayMode,
    SceneViewer,
    _backlight_brightness_from_z,
)


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


@pytest.mark.parametrize(
    "mode",
    [
        m
        for m in DisplayMode
        if m not in (DisplayMode.MATERIALS, DisplayMode.BACKLIGHT_INSERT_PREVIEW)
    ],
)
def test_all_display_modes_render_without_error(offscreen_plotter, mode):
    """MATERIALS et BACKLIGHT_INSERT_PREVIEW ne passent pas par `show_mesh`
    (ils affichent plusieurs corps, pas un seul) -- voir
    show_material_meshes/show_backlight_insert_preview, testes separement
    plus bas."""
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


def test_backlight_brightness_is_higher_for_thinner_z():
    """Fin = lumineux (brille sous retro-eclairage), epais = sombre."""
    points = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.5], [0.0, 0.0, 1.0]])

    brightness = _backlight_brightness_from_z(points)

    assert brightness[0] > brightness[1] > brightness[2]
    assert 0.0 <= brightness.min()
    assert brightness.max() <= 1.0


def test_backlight_brightness_handles_flat_mesh_without_error():
    points = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]])

    brightness = _backlight_brightness_from_z(points)

    assert brightness.shape == (3,)
    assert np.all(np.isfinite(brightness))


def test_backlight_preview_switches_lighting_and_background(offscreen_plotter):
    viewer = SceneViewer(offscreen_plotter)

    viewer.show_mesh(_sample_mesh(), display_mode=DisplayMode.BACKLIGHT_PREVIEW)
    offscreen_plotter.render()
    assert len(offscreen_plotter.renderer.lights) >= 1

    # revenir a un mode normal doit restaurer un rendu utilisable sans erreur
    viewer.show_mesh(_sample_mesh(), display_mode=DisplayMode.SURFACE)
    offscreen_plotter.render()
    assert viewer._mesh_actor is not None


def test_backlight_brightness_uses_panel_z_max_override_not_full_mesh_range():
    """Un pied d'impression fusionne (Z jusqu'a 25mm de profondeur, bien plus
    que l'epaisseur fine du panneau) ne doit pas ecraser la partie la plus
    epaisse DU PANNEAU (0.8 a 3mm) vers un gris uniformement clair si on
    normalise par erreur sur l'etendue complete du mesh fusionne -- voir
    docstring de `_backlight_brightness_from_z`. Avec la bonne reference
    (z_max_override=epaisseur reelle du panneau), le point le plus epais doit
    friser le plancher de luminosite (quasi noir, comme une vraie photo
    retro-eclairee correctement exposee) ; sans elle (normalise sur 0..25 a
    cause du pied), il reste artificiellement clair."""
    thickest_panel_point = np.array([[0.0, 0.0, 3.0]])
    tall_support_point = np.array([[0.0, 0.0, 25.0]])
    points = np.concatenate([thickest_panel_point, tall_support_point])

    without_override = _backlight_brightness_from_z(points)  # normalise sur 0..25 (fausse)
    with_override = _backlight_brightness_from_z(points, z_max_override=3.0)  # panneau seul

    assert with_override[0] < without_override[0]
    assert with_override[0] == pytest.approx(0.04, abs=0.02)  # proche du plancher (floor)


def test_show_material_meshes_adds_one_actor_per_material(offscreen_plotter):
    viewer = SceneViewer(offscreen_plotter)
    mesh_a = _sample_mesh()
    mesh_b = _sample_mesh()

    viewer.show_material_meshes(
        {"Blanc": (mesh_a, (1.0, 1.0, 1.0)), "Rose": (mesh_b, (1.0, 0.4, 0.6))}
    )
    offscreen_plotter.render()

    assert len(viewer._material_actors) == 2
    assert viewer._mesh_actor is None


def test_show_material_meshes_then_show_mesh_clears_material_actors(offscreen_plotter):
    viewer = SceneViewer(offscreen_plotter)
    viewer.show_material_meshes({"Blanc": (_sample_mesh(), (1.0, 1.0, 1.0))})
    assert len(viewer._material_actors) == 1

    viewer.show_mesh(_sample_mesh())

    assert viewer._material_actors == []
    assert viewer._mesh_actor is not None


def test_show_backlight_insert_preview_adds_white_and_insert_actors(offscreen_plotter):
    """Corps blanc (retro-eclaire) + insert(s) doivent tous les deux etre
    des acteurs visibles simultanement dans la scene."""
    viewer = SceneViewer(offscreen_plotter)
    white_mesh = _sample_mesh()
    insert_mesh = _sample_mesh()

    viewer.show_backlight_insert_preview(
        white_mesh, {"Rose": (insert_mesh, (0.85, 0.08, 0.28))}
    )
    offscreen_plotter.render()

    assert viewer._mesh_actor is not None  # le corps blanc
    assert len(viewer._material_actors) == 1  # l'insert


def test_show_backlight_insert_preview_uses_the_real_insert_color(offscreen_plotter):
    """La couleur passee pour l'insert doit etre reellement appliquee a son
    acteur (pas une couleur generique/par defaut)."""
    viewer = SceneViewer(offscreen_plotter)
    insert_color = (0.1, 0.9, 0.2)

    viewer.show_backlight_insert_preview(
        _sample_mesh(), {"Vert": (_sample_mesh(), insert_color)}
    )
    offscreen_plotter.render()

    actor = viewer._material_actors[0]
    prop = actor.GetProperty()
    # VTK quantifie la couleur sur 8 bits (1/255 ~= 0.0039) -- tolerance
    # legerement plus large que l'arrondi flottant pur.
    assert prop.GetColor() == pytest.approx(insert_color, abs=1e-2)


def test_show_backlight_insert_preview_never_shows_breakaway_supports(offscreen_plotter):
    """Seuls le corps blanc et les inserts sont passes a cette methode --
    verifie qu'avec un seul insert fourni (aucun support), un seul acteur
    materiau existe (pas de troisieme corps ajoute implicitement)."""
    viewer = SceneViewer(offscreen_plotter)

    viewer.show_backlight_insert_preview(
        _sample_mesh(), {"Rose": (_sample_mesh(), (0.85, 0.08, 0.28))}
    )

    assert len(viewer._material_actors) == 1


def test_show_backlight_insert_preview_with_no_inserts_still_shows_white_body(offscreen_plotter):
    """Dict d'inserts vide (ex. scene sans zone Backlight Insert active) --
    ne doit jamais lever d'erreur, le corps blanc reste affiche seul."""
    viewer = SceneViewer(offscreen_plotter)

    viewer.show_backlight_insert_preview(_sample_mesh(), {})
    offscreen_plotter.render()

    assert viewer._mesh_actor is not None
    assert viewer._material_actors == []


def test_show_backlight_insert_preview_then_show_mesh_clears_all_actors(offscreen_plotter):
    viewer = SceneViewer(offscreen_plotter)
    viewer.show_backlight_insert_preview(
        _sample_mesh(), {"Rose": (_sample_mesh(), (0.85, 0.08, 0.28))}
    )

    viewer.show_mesh(_sample_mesh())

    assert viewer._material_actors == []
    assert viewer._mesh_actor is not None
