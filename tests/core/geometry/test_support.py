"""Pied/support d'impression (v0.3) : fusion manifold3d au modele compose."""

import numpy as np
import pytest

from lithoshape3d.core.geometry.heightmap import Heightmap
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.geometry.support import attach_support, build_support_mesh
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
    assert build_support_mesh(0.0, WIDTH_MM, PrintSupport(support_type=SupportType.NONE)) is None


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
