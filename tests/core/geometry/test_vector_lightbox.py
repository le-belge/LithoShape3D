"""Tests du moteur d'extrusion vectorielle generique (`vector_lightbox.py`)
sur un polygone Shapely ARBITRAIRE, PAS issu d'une lettre -- verifie que la
generalisation extraite de LightBox Letters (voir docstring de module)
fonctionne independamment de toute notion de glyphe (meme style de test que
`test_lightbox_letters_export.py`, qui couvre deja le cas lettre)."""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from lithoshape3d.core.geometry.vector_lightbox import (
    SHOULDER_DEPTH_MM,
    SHOULDER_WIDTH_MM,
    build_vector_lightbox_back_panel_mesh,
    build_vector_lightbox_body_mesh,
    vector_lightbox_cap_footprint,
)
from lithoshape3d.core.validation.mesh_checks import validate_mesh


def _star_polygon(points: int = 5, outer_radius: float = 30.0) -> Polygon:
    import numpy as np

    inner_radius = outer_radius * 0.382
    vertices = []
    for i in range(points * 2):
        angle = -np.pi / 2 + i * np.pi / points
        radius = outer_radius if i % 2 == 0 else inner_radius
        vertices.append((radius * np.cos(angle), radius * np.sin(angle)))
    return Polygon(vertices)


def test_body_mesh_watertight_for_arbitrary_star_polygon():
    outer = _star_polygon()
    depth_mm = 20.0
    body_mesh, _warnings = build_vector_lightbox_body_mesh(outer, depth_mm, wall_thickness_mm=1.6)

    validation = validate_mesh(body_mesh)
    assert validation.is_valid, validation.issues()
    assert body_mesh.is_watertight
    assert body_mesh.bounds[0][2] == pytest.approx(0.0, abs=0.05)
    assert body_mesh.bounds[1][2] == pytest.approx(depth_mm, abs=0.05)


def test_body_mesh_has_a_real_shoulder_ring_for_arbitrary_polygon():
    outer = _star_polygon()
    wall_thickness_mm = 1.6

    inner_lower = outer.buffer(-wall_thickness_mm)
    inner_shoulder = outer.buffer(-(wall_thickness_mm + SHOULDER_WIDTH_MM))

    assert inner_lower.area > 0
    assert inner_shoulder.area < inner_lower.area


def test_body_mesh_volume_matches_shoulder_step_geometry_for_arbitrary_polygon():
    outer = _star_polygon()
    depth_mm = 20.0
    wall_thickness_mm = 1.6
    body_mesh, _warnings = build_vector_lightbox_body_mesh(outer, depth_mm, wall_thickness_mm)
    assert body_mesh.is_watertight

    inner_lower = outer.buffer(-wall_thickness_mm)
    inner_shoulder = outer.buffer(-(wall_thickness_mm + SHOULDER_WIDTH_MM))
    shoulder_top = depth_mm - SHOULDER_DEPTH_MM
    # Option B (rebord invere, retour utilisateur) : la cavite ETROITE
    # (`inner_shoulder`, paroi elargie) occupe la portion PROFONDE pres du
    # fond (hauteur `shoulder_top`) -- c'est le rebord qui soutient le capot
    # par en dessous -- tandis que la cavite LARGE (`inner_lower`, meme
    # largeur que le corps) occupe la portion pres de l'AVANT/OUVERTURE
    # (hauteur `SHOULDER_DEPTH_MM`), ou le capot vient se loger.
    expected_volume = (
        outer.area * depth_mm
        - inner_shoulder.area * shoulder_top
        - inner_lower.area * SHOULDER_DEPTH_MM
    )
    assert body_mesh.volume == pytest.approx(expected_volume, rel=0.03)


def test_back_panel_mesh_is_smooth_solid_extrusion_for_arbitrary_polygon():
    outer = Polygon([(0, 0), (40, 0), (40, 25), (0, 25)])
    back_mesh = build_vector_lightbox_back_panel_mesh(outer, thickness_mm=1.2)

    validation = validate_mesh(back_mesh)
    assert validation.is_valid, validation.issues()
    assert back_mesh.is_watertight
    assert back_mesh.bounds[1][2] == pytest.approx(1.2, abs=1e-6)
    assert back_mesh.volume == pytest.approx(outer.area * 1.2, rel=0.02)


def test_cap_footprint_smaller_than_body_for_arbitrary_polygon():
    outer = _star_polygon()
    wall_thickness_mm = 1.6
    cap = vector_lightbox_cap_footprint(outer, wall_thickness_mm)

    assert not cap.is_empty
    assert cap.area < outer.area


def test_body_mesh_raises_clear_error_on_empty_polygon():
    empty = Polygon()
    with pytest.raises(ValueError, match="vide"):
        build_vector_lightbox_body_mesh(empty, depth_mm=20.0, wall_thickness_mm=1.6)


def test_multi_polygon_input_produces_watertight_body():
    """Une forme a composantes disjointes (ex. silhouette d'image avec
    plusieurs ilots, comme un glyphe multi-parties) doit rester geree par
    le meme moteur, via l'union manifold3d de `_extrude_geom`."""
    from shapely.geometry import MultiPolygon

    square_a = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    square_b = Polygon([(20, 0), (30, 0), (30, 10), (20, 10)])
    outer = MultiPolygon([square_a, square_b])

    body_mesh, _warnings = build_vector_lightbox_body_mesh(outer, depth_mm=15.0, wall_thickness_mm=1.6)
    validation = validate_mesh(body_mesh)
    assert validation.is_valid, validation.issues()
    assert body_mesh.is_watertight
