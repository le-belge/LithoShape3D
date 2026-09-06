"""Tests de la decoupe connecteur (USB-C / pogo pin) dans le fond integre
d'un caisson lumineux vectoriel (`apply_back_panel_connector_cutout`,
`vector_lightbox.py`) -- retour utilisateur : "un emplacement pour fixer un
port usb c ou un connecteur pogo"."""

from __future__ import annotations

import pytest
from shapely.geometry import Point

from lithoshape3d.core.geometry.vector_lightbox import (
    CONNECTOR_SHAPE_CIRCLE,
    CONNECTOR_SHAPE_RECT,
    apply_back_panel_connector_cutout,
    build_vector_lightbox_body_mesh,
)
from lithoshape3d.core.validation.mesh_checks import validate_mesh

_OUTER = Point(0, 0).buffer(30.0)  # disque de rayon 30mm
_DEPTH_MM = 20.0
_WALL_THICKNESS_MM = 1.6
_BACK_THICKNESS_MM = 1.2


def _build_body():
    body_mesh, warnings = build_vector_lightbox_body_mesh(
        _OUTER, _DEPTH_MM, _WALL_THICKNESS_MM, back_thickness_mm=_BACK_THICKNESS_MM
    )
    assert not warnings
    return body_mesh


def test_rect_cutout_produces_watertight_mesh_and_removes_expected_volume():
    body_mesh = _build_body()
    width_mm, height_mm = 9.5, 3.8

    cut_mesh = apply_back_panel_connector_cutout(
        body_mesh,
        _OUTER,
        _BACK_THICKNESS_MM,
        shape=CONNECTOR_SHAPE_RECT,
        width_mm=width_mm,
        height_mm=height_mm,
        corner_radius_mm=0.0,  # coins non arrondis : volume exact, pas d'approximation
        center_x_mm=0.0,
        center_y_mm=-20.0,
    )

    validation = validate_mesh(cut_mesh)
    assert validation.is_valid, validation.issues()
    assert cut_mesh.is_watertight

    expected_removed = width_mm * height_mm * _BACK_THICKNESS_MM
    assert body_mesh.volume - cut_mesh.volume == pytest.approx(expected_removed, rel=0.02)


def test_circle_cutout_produces_watertight_mesh_and_removes_expected_volume():
    import math

    body_mesh = _build_body()
    diameter_mm = 6.0

    cut_mesh = apply_back_panel_connector_cutout(
        body_mesh,
        _OUTER,
        _BACK_THICKNESS_MM,
        shape=CONNECTOR_SHAPE_CIRCLE,
        width_mm=diameter_mm,
        center_x_mm=10.0,
        center_y_mm=10.0,
    )

    validation = validate_mesh(cut_mesh)
    assert validation.is_valid, validation.issues()
    assert cut_mesh.is_watertight

    expected_removed = math.pi * (diameter_mm / 2.0) ** 2 * _BACK_THICKNESS_MM
    assert body_mesh.volume - cut_mesh.volume == pytest.approx(expected_removed, rel=0.02)


def test_cutout_center_outside_silhouette_raises_clear_error():
    body_mesh = _build_body()

    with pytest.raises(ValueError, match="hors de la silhouette"):
        apply_back_panel_connector_cutout(
            body_mesh,
            _OUTER,
            _BACK_THICKNESS_MM,
            shape=CONNECTOR_SHAPE_CIRCLE,
            width_mm=6.0,
            center_x_mm=100.0,
            center_y_mm=100.0,
        )


def test_rect_cutout_requires_height_mm():
    body_mesh = _build_body()

    with pytest.raises(ValueError, match="height_mm"):
        apply_back_panel_connector_cutout(
            body_mesh,
            _OUTER,
            _BACK_THICKNESS_MM,
            shape=CONNECTOR_SHAPE_RECT,
            width_mm=9.5,
            center_x_mm=0.0,
            center_y_mm=-20.0,
        )


def test_invalid_shape_raises_clear_error():
    body_mesh = _build_body()

    with pytest.raises(ValueError, match="shape invalide"):
        apply_back_panel_connector_cutout(
            body_mesh,
            _OUTER,
            _BACK_THICKNESS_MM,
            shape="triangle",
            width_mm=6.0,
            center_x_mm=0.0,
            center_y_mm=-20.0,
        )
