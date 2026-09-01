"""Pied/support d'impression (v0.3) : fusion manifold3d au modele compose."""

import numpy as np
import pytest

from lithoshape3d.core.geometry.heightmap import Heightmap
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.geometry.support import (
    attach_support,
    build_side_stabilizer_mesh,
    build_side_stabilizer_pair,
    build_support_mesh,
)
from lithoshape3d.core.scene.models import GeometryParameters, PrintSupport, SupportType
from lithoshape3d.core.validation.mesh_checks import validate_mesh

WIDTH_MM, HEIGHT_MM = 60.0, 40.0


@pytest.fixture
def panel_mesh():
    heightmap = Heightmap(values=np.full((60, 80), 0.5, dtype=np.float32))
    params = GeometryParameters(width_mm=WIDTH_MM, height_mm=HEIGHT_MM, resolution=0.75)
    return build_slab_mesh(heightmap, mask=None, params=params)


def test_support_none_returns_mesh_unchanged(panel_mesh):
    fused = attach_support(panel_mesh, PrintSupport(support_type=SupportType.NONE))

    assert fused is panel_mesh


def test_build_support_mesh_none_returns_none():
    assert build_support_mesh(0.0, WIDTH_MM, 0.0, PrintSupport(support_type=SupportType.NONE)) is None


@pytest.mark.parametrize("support_type", [SupportType.FLAT, SupportType.REINFORCED])
def test_support_fuses_into_single_manifold_body(panel_mesh, support_type):
    fused = attach_support(panel_mesh, PrintSupport(support_type=support_type))

    result = validate_mesh(fused)
    assert result.is_watertight
    assert result.is_winding_consistent
    assert result.manifold3d_compatible
    assert result.connected_components == 1
    assert not np.isnan(fused.vertices).any()
    assert not np.isinf(fused.vertices).any()


def test_support_does_not_float_below_the_panel(panel_mesh):
    """Le pied doit toucher/recouvrir le panneau, pas etre detache dans l'espace."""
    fused = attach_support(panel_mesh, PrintSupport(support_type=SupportType.FLAT))

    assert fused.bounds[0][1] < 0.0  # s'etend bien sous Y=0 (bord bas du panneau)
    assert validate_mesh(fused).connected_components == 1


def test_support_respects_overhang_and_height_params(panel_mesh):
    support = PrintSupport(
        support_type=SupportType.FLAT, height_mm=12.0, overhang_left_mm=3.0, overhang_right_mm=7.0
    )
    fused = attach_support(panel_mesh, support)

    assert fused.bounds[0][0] == pytest.approx(-3.0, abs=0.5)
    assert fused.bounds[1][0] == pytest.approx(WIDTH_MM + 7.0, abs=0.5)
    assert fused.bounds[0][1] == pytest.approx(-12.0, abs=0.5)


def test_support_does_not_alter_panel_content_above_the_seam(panel_mesh):
    """Le pied ne doit pas modifier le contenu lithophanique au-dessus de la
    zone de raccord : les sommets du panneau loin de Y=0 restent inchanges."""
    fused = attach_support(panel_mesh, PrintSupport(support_type=SupportType.FLAT))

    far_from_seam = panel_mesh.vertices[panel_mesh.vertices[:, 1] > HEIGHT_MM * 0.5]
    for vertex in far_from_seam[:: max(1, len(far_from_seam) // 20)]:
        assert np.any(np.linalg.norm(fused.vertices - vertex, axis=1) < 1e-4)


def test_reinforced_uses_more_material_than_flat(panel_mesh):
    flat = attach_support(panel_mesh, PrintSupport(support_type=SupportType.FLAT))
    reinforced = attach_support(panel_mesh, PrintSupport(support_type=SupportType.REINFORCED))

    assert reinforced.volume > flat.volume


@pytest.mark.parametrize("support_type", [SupportType.FLAT, SupportType.REINFORCED])
def test_support_fuses_with_a_shape_whose_lowest_point_is_above_y_zero(support_type, tmp_path):
    """Regression (2.13) : un Coeur (ShapeMask) inscrit avec marge dans la
    grille canonique a son point le plus bas nettement au-dessus de Y=0
    (verifie empiriquement ~10mm sur une grille 100x100mm/2mm-px) -- pas un
    bord bas rectangulaire droit touchant Y=0. Le pied doit se caler sur ce
    point reel (`y_top`), sinon il reste flottant sous le modele et l'union
    manifold3d rend deux composantes disjointes au lieu d'un seul corps
    imprimable."""
    from PIL import Image

    from lithoshape3d.core.geometry.composition import ZoneSource, compose_scene_mesh
    from lithoshape3d.core.geometry.shape import build_shape_mask
    from lithoshape3d.core.scene.models import (
        CompositionMode,
        ReliefMode,
        ShapeParams,
        ShapeType,
        Zone,
    )
    from lithoshape3d.core.validation.mesh_checks import validate_mesh

    image_path = tmp_path / "uniform.png"
    Image.fromarray(np.full((300, 300), 150, dtype=np.uint8), mode="L").save(image_path)

    params = GeometryParameters(width_mm=100.0, height_mm=100.0, resolution=2.0)
    zone = Zone(name="base", composition_mode=CompositionMode.BASE, relief_mode=ReliefMode.LITHOPHANE, geometry_params=params)
    heart = build_shape_mask(ShapeParams(shape_type=ShapeType.HEART), 50, 50)
    panel = compose_scene_mesh([ZoneSource(zone=zone, image_path=str(image_path))], shape_mask=heart)
    assert panel.bounds[0][1] > 5.0  # confirme que le point le plus bas n'est PAS pres de Y=0

    fused = attach_support(panel, PrintSupport(support_type=support_type, height_mm=6.0))
    result = validate_mesh(fused)

    assert result.is_valid
    assert result.connected_components == 1


# --------------------------------------------------------------------- #
# Stabilisateurs lateraux (aide a l'impression, jamais fusionnes)
# --------------------------------------------------------------------- #


def _contact_rib_x_range(mesh, y: float, z_threshold: float = 3.0):
    """Coupe transversale a la hauteur `y` : etendue X des points dont Z
    depasse `z_threshold` -- isole la nervure de contact surelevee du
    gabarit (le corps du coin lui-meme reste sous Z=2mm partout), seule
    partie censee reellement affleurer le panneau. `None` si aucun point
    haut a cette hauteur (creux entre deux languettes, motif periodique
    attendu -- voir docstring de module)."""
    section = mesh.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
    if section is None:
        return None
    pts = section.vertices
    high = pts[pts[:, 2] > z_threshold]
    if not len(high):
        return None
    return float(high[:, 0].min()), float(high[:, 0].max())


def test_side_stabilizer_pair_are_watertight_and_never_fused():
    left, right = build_side_stabilizer_pair(panel_width_mm=100.0, y_bottom=0.0, y_top=140.0)

    for mesh in (left, right):
        result = validate_mesh(mesh)
        assert result.is_valid
        assert result.connected_components == 1


def test_side_stabilizer_contact_rib_touches_left_and_right_edges_of_the_panel():
    """Le CORPS du coin triangulaire ne touche jamais le panneau (design
    original -- seule la nervure de contact, surelevee, le fait par
    endroits) : verifie sur plusieurs hauteurs que cette nervure traverse
    bien X=0 (gauche) / X=panel_width_mm (droite), pas juste s'en approcher."""
    panel_width = 100.0
    left, right = build_side_stabilizer_pair(panel_width_mm=panel_width, y_bottom=0.0, y_top=140.0)

    contacts_left = [_contact_rib_x_range(left, y) for y in np.linspace(2.0, 138.0, 12)]
    contacts_left = [c for c in contacts_left if c is not None]
    assert contacts_left, "Aucune nervure de contact detectee sur le stabilisateur gauche."
    for x_min, x_max in contacts_left:
        assert x_min <= 0.0 <= x_max

    contacts_right = [_contact_rib_x_range(right, y) for y in np.linspace(2.0, 138.0, 12)]
    contacts_right = [c for c in contacts_right if c is not None]
    assert contacts_right, "Aucune nervure de contact detectee sur le stabilisateur droit."
    for x_min, x_max in contacts_right:
        assert x_min <= panel_width <= x_max


def test_side_stabilizer_spans_the_full_panel_height():
    y_bottom, y_top = 5.0, 145.0
    left, _right = build_side_stabilizer_pair(panel_width_mm=100.0, y_bottom=y_bottom, y_top=y_top)

    # Tolerance non-triviale : le gabarit source a lui-meme un residu
    # sub-micrometrique sur ses propres bornes (STL tel que fourni, avant
    # toute transformation) -- voir bounds natifs mesures dans le module.
    assert left.bounds[0][1] == pytest.approx(y_bottom, abs=1e-3)
    assert left.bounds[1][1] == pytest.approx(y_top, abs=1e-3)


def test_side_stabilizer_thickness_matches_the_original_template_regardless_of_panel():
    """Le gabarit reel a sa propre epaisseur fixe (5mm) -- contrairement a
    l'ancienne approximation, elle ne suit JAMAIS l'epaisseur du panneau
    (une lithophanie fine de 0.8mm n'a pas besoin d'un stabilisateur aussi
    fin et fragile)."""
    thin_panel = build_side_stabilizer_mesh(0.0, 100.0, side="left")
    assert thin_panel.bounds[1][2] == pytest.approx(5.0, abs=1e-6)


def test_side_stabilizer_rejects_invalid_side():
    with pytest.raises(ValueError, match="side"):
        build_side_stabilizer_mesh(0.0, 100.0, side="top")
