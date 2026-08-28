"""LightBox Designer : generation core d'un caisson de forme + facade.

Premiere brique volontairement headless et testable : elle reutilise le
ShapeMask et le moteur lithophanie existants, puis ajoute un corps creux
extrude en Z. L'insert backlight experimental reste hors de ce chemin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np
import trimesh
from scipy import ndimage

from lithoshape3d.core.geometry.composition import ZoneSource, compose_scene_mesh
from lithoshape3d.core.geometry.heightmap import grid_dimensions
from lithoshape3d.core.geometry.mesh_builder import build_mesh_from_heightfield
from lithoshape3d.core.geometry.shape import build_shape_mask
from lithoshape3d.core.geometry.support import _from_manifold, _to_manifold
from lithoshape3d.core.scene.models import (
    CompositionMode,
    GeometryParameters,
    ImageTransform,
    ReliefMode,
    ShapeParams,
    ShapeType,
    Zone,
)


class LightBoxFaceMode(Enum):
    OPEN = "open"
    SOLID = "solid"
    LITHOPHANE = "lithophane"


@dataclass(frozen=True)
class LightBoxParameters:
    depth_mm: float = 35.0
    wall_thickness_mm: float = 2.0
    back_panel_thickness_mm: float = 1.2
    include_back_panel: bool = True
    face_mode: LightBoxFaceMode = LightBoxFaceMode.LITHOPHANE
    solid_face_thickness_mm: float = 1.2


@dataclass(frozen=True)
class LightBoxBuildResult:
    body_mesh: trimesh.Trimesh
    face_mesh: trimesh.Trimesh | None = None
    back_panel_mesh: trimesh.Trimesh | None = None
    warnings: list[str] = field(default_factory=list)

    def as_meshes(self) -> dict[str, trimesh.Trimesh]:
        meshes = {"body": self.body_mesh}
        if self.face_mesh is not None:
            meshes["face"] = self.face_mesh
        if self.back_panel_mesh is not None:
            meshes["back_panel"] = self.back_panel_mesh
        return meshes


def _validate_box_params(face_params: GeometryParameters, box_params: LightBoxParameters) -> None:
    if face_params.width_mm <= 0 or face_params.height_mm <= 0:
        raise ValueError("Les dimensions de facade doivent etre > 0.")
    if face_params.resolution <= 0:
        raise ValueError("La resolution doit etre > 0.")
    if box_params.depth_mm <= 0:
        raise ValueError("La profondeur du caisson doit etre > 0.")
    if box_params.wall_thickness_mm <= 0:
        raise ValueError("L'epaisseur de paroi doit etre > 0.")
    if box_params.include_back_panel and box_params.back_panel_thickness_mm <= 0:
        raise ValueError("L'epaisseur du fond doit etre > 0 si le fond est active.")
    if box_params.face_mode is LightBoxFaceMode.SOLID and box_params.solid_face_thickness_mm <= 0:
        raise ValueError("L'epaisseur de facade pleine doit etre > 0.")


def _pixel_size_mm(rows: int, cols: int, width_mm: float, height_mm: float) -> float:
    px_x = width_mm / max(1, cols - 1)
    px_y = height_mm / max(1, rows - 1)
    return min(px_x, px_y)


def _erode_mask_by_mm(mask: np.ndarray, distance_mm: float, width_mm: float, height_mm: float) -> np.ndarray:
    rows, cols = mask.shape
    sampling = (
        height_mm / max(1, rows - 1),
        width_mm / max(1, cols - 1),
    )
    padded = np.pad(mask, 1, constant_values=False)
    distance = ndimage.distance_transform_edt(padded, sampling=sampling)
    return distance[1:-1, 1:-1] > distance_mm


def _shape_mask_y_up(shape_mask: np.ndarray, rows: int, cols: int) -> np.ndarray:
    if shape_mask.shape != (rows, cols):
        raise ValueError(
            f"shape_mask doit avoir la forme {(rows, cols)}, recu {shape_mask.shape}."
        )
    return np.flipud(shape_mask.astype(bool))


def _meshable_vertex_mask(mask: np.ndarray) -> np.ndarray:
    """Garde uniquement les sommets appartenant a au moins une cellule complete."""
    cell_active = mask[:-1, :-1] & mask[:-1, 1:] & mask[1:, :-1] & mask[1:, 1:]
    cleaned = np.zeros_like(mask, dtype=bool)
    cleaned[:-1, :-1] |= cell_active
    cleaned[:-1, 1:] |= cell_active
    cleaned[1:, :-1] |= cell_active
    cleaned[1:, 1:] |= cell_active
    return cleaned


def build_lightbox_body_mesh(
    shape_mask: np.ndarray,
    face_params: GeometryParameters,
    box_params: LightBoxParameters,
) -> tuple[trimesh.Trimesh, list[str]]:
    """Construit uniquement les parois du caisson, sans fond ni facade.

    `shape_mask` suit la convention image/Shape Composer. La fonction le
    retourne en Y-up avant d'appeler `build_mesh_from_heightfield`.
    """
    _validate_box_params(face_params, box_params)
    rows, cols = grid_dimensions(face_params)
    shape_active = _shape_mask_y_up(shape_mask, rows, cols)
    if not shape_active.any():
        raise ValueError("Caisson impossible : la forme ne contient aucune matiere.")

    warnings: list[str] = []
    pixel = _pixel_size_mm(rows, cols, face_params.width_mm, face_params.height_mm)
    # Le builder cree des cellules a partir de 4 sommets actifs. Une paroi
    # d'un seul sommet de large est visible dans le masque, mais impossible a
    # fermer en volume ; on force donc au moins deux pas de grille.
    min_meshable_wall_mm = pixel * 2.0
    erosion_mm = max(box_params.wall_thickness_mm, min_meshable_wall_mm)
    if erosion_mm > box_params.wall_thickness_mm:
        warnings.append(
            "Paroi arrondie a la resolution courante : augmentez la resolution "
            "pour representer plus finement l'epaisseur demandee."
        )

    inner_active = _erode_mask_by_mm(
        shape_active, erosion_mm, face_params.width_mm, face_params.height_mm
    )
    inner_active = _meshable_vertex_mask(inner_active)

    if not inner_active.any():
        warnings.append(
            "La forme est trop fine pour creer une cavite interne a cette resolution ; "
            "le corps sera plein localement."
        )
        inner_active = np.zeros_like(shape_active)

    front_z = np.full((rows, cols), box_params.depth_mm, dtype=np.float32)
    outer_mesh = build_mesh_from_heightfield(
        front_z, shape_active, face_params.width_mm, face_params.height_mm
    )
    if not inner_active.any():
        return outer_mesh, warnings

    eps = min(0.05, box_params.depth_mm * 0.001)
    inner_front_z = np.full((rows, cols), box_params.depth_mm + (eps * 2.0), dtype=np.float32)
    inner_mesh = build_mesh_from_heightfield(
        inner_front_z, inner_active, face_params.width_mm, face_params.height_mm
    )
    inner_mesh.apply_translation((0.0, 0.0, -eps))

    body_mesh = _from_manifold(_to_manifold(outer_mesh) - _to_manifold(inner_mesh))
    if body_mesh.is_empty:
        raise ValueError("Caisson impossible : la cavite supprime tout le volume de la forme.")
    return body_mesh, warnings


def build_lightbox_back_panel_mesh(
    shape_mask: np.ndarray,
    face_params: GeometryParameters,
    box_params: LightBoxParameters,
) -> trimesh.Trimesh:
    _validate_box_params(face_params, box_params)
    rows, cols = grid_dimensions(face_params)
    shape_active = _shape_mask_y_up(shape_mask, rows, cols)
    front_z = np.full((rows, cols), box_params.back_panel_thickness_mm, dtype=np.float32)
    return build_mesh_from_heightfield(front_z, shape_active, face_params.width_mm, face_params.height_mm)


def build_lightbox_lithophane_face_mesh(
    image_path: str | Path,
    shape_mask: np.ndarray,
    face_params: GeometryParameters,
    depth_mm: float,
    image_transform: ImageTransform | None = None,
) -> trimesh.Trimesh:
    zone = Zone(
        name="LightBox lithophane facade",
        composition_mode=CompositionMode.BASE,
        relief_mode=ReliefMode.LITHOPHANE,
        geometry_params=face_params,
    )
    mesh = compose_scene_mesh(
        [ZoneSource(zone=zone, image_path=str(image_path))],
        shape_mask=shape_mask,
        image_transform=image_transform,
    )
    mesh = mesh.copy()
    mesh.apply_translation((0.0, 0.0, depth_mm))
    return mesh


def build_lightbox_solid_face_mesh(
    shape_mask: np.ndarray,
    face_params: GeometryParameters,
    box_params: LightBoxParameters,
) -> trimesh.Trimesh:
    rows, cols = grid_dimensions(face_params)
    shape_active = _shape_mask_y_up(shape_mask, rows, cols)
    front_z = np.full((rows, cols), box_params.solid_face_thickness_mm, dtype=np.float32)
    mesh = build_mesh_from_heightfield(front_z, shape_active, face_params.width_mm, face_params.height_mm)
    mesh.apply_translation((0.0, 0.0, box_params.depth_mm))
    return mesh


def build_lightbox_from_shape_mask(
    shape_mask: np.ndarray,
    face_params: GeometryParameters,
    box_params: LightBoxParameters,
    image_path: str | Path | None = None,
    image_transform: ImageTransform | None = None,
) -> LightBoxBuildResult:
    """Construit les pieces V1 : corps creux, fond optionnel, facade optionnelle."""
    if box_params.face_mode is LightBoxFaceMode.LITHOPHANE and image_path is None:
        raise ValueError("Une image source est requise pour une facade lithophanie.")

    body_mesh, warnings = build_lightbox_body_mesh(shape_mask, face_params, box_params)

    face_mesh: trimesh.Trimesh | None = None
    if box_params.face_mode is LightBoxFaceMode.LITHOPHANE:
        face_mesh = build_lightbox_lithophane_face_mesh(
            image_path, shape_mask, face_params, box_params.depth_mm, image_transform
        )
    elif box_params.face_mode is LightBoxFaceMode.SOLID:
        face_mesh = build_lightbox_solid_face_mesh(shape_mask, face_params, box_params)
    elif box_params.face_mode is not LightBoxFaceMode.OPEN:
        raise NotImplementedError(f"Mode de facade non supporte : {box_params.face_mode}")

    back_panel = (
        build_lightbox_back_panel_mesh(shape_mask, face_params, box_params)
        if box_params.include_back_panel
        else None
    )
    return LightBoxBuildResult(body_mesh=body_mesh, face_mesh=face_mesh, back_panel_mesh=back_panel, warnings=warnings)


def build_text_lightbox(
    text: str,
    image_path: str | Path,
    face_params: GeometryParameters,
    box_params: LightBoxParameters | None = None,
    font_path: str | None = None,
    bold: bool = True,
    image_transform: ImageTransform | None = None,
) -> LightBoxBuildResult:
    """Raccourci V1 pour le cas commercial prioritaire : texte -> box litho."""
    params = ShapeParams(shape_type=ShapeType.TEXT, text=text, font_path=font_path, bold=bold)
    rows, cols = grid_dimensions(face_params)
    shape_mask = build_shape_mask(params, rows, cols)
    return build_lightbox_from_shape_mask(
        shape_mask,
        face_params,
        box_params or LightBoxParameters(),
        image_path=image_path,
        image_transform=image_transform,
    )
