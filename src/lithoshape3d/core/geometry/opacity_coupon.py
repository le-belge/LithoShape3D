"""Coupon LithoLab V1 pour mesurer l'opacite d'un filament imprime.

Le coupon est une lithophanie technique sans image source : une plaque avec
plusieurs zones planes d'epaisseurs connues. Il sert au protocole LithoLab /
LithoMeter pour mesurer la transmission lumineuse d'un filament imprime.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont

from lithoshape3d.core.geometry.mesh_builder import build_mesh_from_heightfield

DEFAULT_LITHOLAB_OPACITY_THICKNESSES_MM = (0.6, 0.8, 1.0, 1.5, 2.0, 2.5, 3.0)
DEFAULT_LITHOLAB_OPACITY_OUTPUT_NAME = "LithoLab_Opacity_Coupon_V1.stl"


@dataclass(frozen=True)
class OpacityCouponParameters:
    width_mm: float = 100.0
    height_mm: float = 30.0
    resolution_mm: float = 0.5
    thicknesses_mm: tuple[float, ...] = DEFAULT_LITHOLAB_OPACITY_THICKNESSES_MM
    margin_mm: float = 4.0
    gap_mm: float = 2.0
    label_band_height_mm: float = 6.0
    label_relief_mm: float = 0.2
    labels: bool = True

    @property
    def max_coupon_thickness_mm(self) -> float:
        return max(self.thicknesses_mm)

    @property
    def measurement_y_min_mm(self) -> float:
        return self.margin_mm + self.label_band_height_mm

    @property
    def measurement_y_max_mm(self) -> float:
        return self.height_mm - self.margin_mm

    def patch_spans(self) -> list[tuple[float, float, float]]:
        available_width = self.width_mm - (2.0 * self.margin_mm) - (
            self.gap_mm * (len(self.thicknesses_mm) - 1)
        )
        patch_width = available_width / len(self.thicknesses_mm)
        spans = []
        x = self.margin_mm
        for thickness in self.thicknesses_mm:
            spans.append((x, x + patch_width, thickness))
            x += patch_width + self.gap_mm
        return spans


def _validate_params(params: OpacityCouponParameters) -> None:
    if params.width_mm <= 0 or params.height_mm <= 0:
        raise ValueError("Les dimensions du coupon doivent etre > 0.")
    if params.resolution_mm <= 0:
        raise ValueError("La resolution doit etre > 0.")
    if len(params.thicknesses_mm) < 2:
        raise ValueError("Le coupon doit contenir au moins deux epaisseurs.")
    if any(thickness <= 0 for thickness in params.thicknesses_mm):
        raise ValueError("Toutes les epaisseurs doivent etre > 0.")
    if params.margin_mm < 0 or params.gap_mm < 0 or params.label_band_height_mm < 0:
        raise ValueError("Les marges, espaces et bande label doivent etre >= 0.")
    if params.label_relief_mm < 0:
        raise ValueError("Le relief des labels doit etre >= 0.")
    if params.measurement_y_max_mm <= params.measurement_y_min_mm:
        raise ValueError("La zone de mesure est vide : reduisez marges ou bande label.")
    available_width = params.width_mm - (2.0 * params.margin_mm) - (
        params.gap_mm * (len(params.thicknesses_mm) - 1)
    )
    if available_width <= 0:
        raise ValueError("Largeur insuffisante pour placer les zones de mesure.")


def _grid_dimensions(params: OpacityCouponParameters) -> tuple[int, int]:
    cols = max(2, round(params.width_mm / params.resolution_mm) + 1)
    rows = max(2, round(params.height_mm / params.resolution_mm) + 1)
    return rows, cols


def _draw_labels(front_z: np.ndarray, params: OpacityCouponParameters) -> None:
    if not params.labels:
        return

    rows, cols = front_z.shape
    image = Image.new("L", (cols, rows), 0)
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Arial.ttf", max(6, round(params.label_band_height_mm * 2.2)))
    except OSError:
        font = ImageFont.load_default()

    def y_to_pillow_row(y_mm: float) -> float:
        return (1.0 - (y_mm / params.height_mm)) * (rows - 1)

    label_y_mm = params.margin_mm + (params.label_band_height_mm * 0.45)
    label_row = y_to_pillow_row(label_y_mm)
    version_row = y_to_pillow_row(params.height_mm - (params.margin_mm * 0.55))

    for x_min, x_max, thickness in params.patch_spans():
        x_center_px = ((x_min + x_max) * 0.5 / params.width_mm) * (cols - 1)
        label = f"{thickness:g}"
        bbox = draw.textbbox((0, 0), label, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        draw.text(
            (x_center_px - text_width / 2, label_row - text_height / 2),
            label,
            fill=255,
            font=font,
        )

    version = "LithoLab V1"
    bbox = draw.textbbox((0, 0), version, font=font)
    draw.text(
        ((cols - (bbox[2] - bbox[0])) / 2, version_row - (bbox[3] - bbox[1]) / 2),
        version,
        fill=255,
        font=font,
    )

    label_mask = np.asarray(image, dtype=np.uint8) > 0
    front_z[label_mask] = params.max_coupon_thickness_mm + params.label_relief_mm


def build_opacity_coupon_mesh(
    params: OpacityCouponParameters | None = None,
) -> trimesh.Trimesh:
    """Construit le coupon d'opacite LithoLab V1.

    La plaque reste un seul solide ferme : les zones de mesure sont plus
    fines, tandis que le cadre et les separateurs gardent l'epaisseur max.
    """
    params = params or OpacityCouponParameters()
    _validate_params(params)

    rows, cols = _grid_dimensions(params)
    xs = np.linspace(0.0, params.width_mm, cols, dtype=np.float32)
    ys = np.linspace(0.0, params.height_mm, rows, dtype=np.float32)
    grid_x, grid_y = np.meshgrid(xs, ys)

    front_z = np.full(
        (rows, cols),
        params.max_coupon_thickness_mm,
        dtype=np.float32,
    )
    measurement_y = (grid_y >= params.measurement_y_min_mm) & (
        grid_y <= params.measurement_y_max_mm
    )

    for x_min, x_max, thickness in params.patch_spans():
        patch = (grid_x >= x_min) & (grid_x <= x_max) & measurement_y
        front_z[patch] = thickness

    _draw_labels(front_z, params)

    active = np.ones((rows, cols), dtype=bool)
    return build_mesh_from_heightfield(front_z, active, params.width_mm, params.height_mm)
