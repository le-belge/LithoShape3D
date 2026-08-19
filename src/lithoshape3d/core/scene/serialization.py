"""Serialisation JSON versionnee du modele Project / Scene / Zone.

Seule la structure legere (parametres, chemins, references) est ecrite.
Les meshes generes ne sont jamais embarques : `Zone.mesh_cache_path` pointe
vers un fichier a part (cache local), pas vers des donnees inline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lithoshape3d.core.scene.models import (
    GeometryParameters,
    Material,
    Project,
    ReliefMode,
    Scene,
    Transform,
    Zone,
)

CURRENT_FORMAT_VERSION = 1


def _transform_to_dict(transform: Transform) -> dict[str, Any]:
    return {
        "translation": list(transform.translation),
        "rotation": list(transform.rotation),
        "scale": list(transform.scale),
    }


def _transform_from_dict(data: dict[str, Any]) -> Transform:
    return Transform(
        translation=tuple(data.get("translation", (0.0, 0.0, 0.0))),
        rotation=tuple(data.get("rotation", (0.0, 0.0, 0.0))),
        scale=tuple(data.get("scale", (1.0, 1.0, 1.0))),
    )


def _material_to_dict(material: Material) -> dict[str, Any]:
    return {
        "name": material.name,
        "color": list(material.color),
        "filament_type": material.filament_type,
        "translucent": material.translucent,
    }


def _material_from_dict(data: dict[str, Any]) -> Material:
    return Material(
        name=data.get("name", "default"),
        color=tuple(data.get("color", (1.0, 1.0, 1.0))),
        filament_type=data.get("filament_type"),
        translucent=data.get("translucent", False),
    )


def _geometry_params_to_dict(params: GeometryParameters) -> dict[str, Any]:
    return {
        "width_mm": params.width_mm,
        "height_mm": params.height_mm,
        "min_thickness_mm": params.min_thickness_mm,
        "max_thickness_mm": params.max_thickness_mm,
        "invert": params.invert,
        "resolution": params.resolution,
        "base_shape": params.base_shape,
    }


def _geometry_params_from_dict(data: dict[str, Any]) -> GeometryParameters:
    return GeometryParameters(
        width_mm=data["width_mm"],
        height_mm=data["height_mm"],
        min_thickness_mm=data.get("min_thickness_mm", 0.8),
        max_thickness_mm=data.get("max_thickness_mm", 3.0),
        invert=data.get("invert", False),
        resolution=data.get("resolution", 0.3),
        base_shape=data.get("base_shape", "rectangle"),
    )


def _zone_to_dict(zone: Zone) -> dict[str, Any]:
    return {
        "id": zone.id,
        "name": zone.name,
        "source_image_path": zone.source_image_path,
        "mask_path": zone.mask_path,
        "geometry_params": _geometry_params_to_dict(zone.geometry_params),
        "material": _material_to_dict(zone.material),
        "transform": _transform_to_dict(zone.transform),
        "relief_mode": zone.relief_mode.value,
        "mesh_cache_path": zone.mesh_cache_path,
    }


def _zone_from_dict(data: dict[str, Any]) -> Zone:
    return Zone(
        id=data.get("id", None) or Zone().id,
        name=data.get("name", "zone"),
        source_image_path=data.get("source_image_path"),
        mask_path=data.get("mask_path"),
        geometry_params=_geometry_params_from_dict(data["geometry_params"]),
        material=_material_from_dict(data.get("material", {})),
        transform=_transform_from_dict(data.get("transform", {})),
        relief_mode=ReliefMode(data.get("relief_mode", ReliefMode.LITHOPHANE.value)),
        mesh_cache_path=data.get("mesh_cache_path"),
    )


def project_to_dict(project: Project) -> dict[str, Any]:
    return {
        "format_version": project.format_version,
        "name": project.name,
        "scene": {
            "zones": [_zone_to_dict(zone) for zone in project.scene.zones],
        },
    }


def project_from_dict(data: dict[str, Any]) -> Project:
    format_version = data.get("format_version", CURRENT_FORMAT_VERSION)
    if format_version > CURRENT_FORMAT_VERSION:
        raise ValueError(
            f"format_version {format_version} non supporte "
            f"(version maximale geree : {CURRENT_FORMAT_VERSION})"
        )
    # Point d'extension : les migrations de format_version 1 -> 2, etc.
    # viendront se brancher ici lorsque le format evoluera.

    zones = [_zone_from_dict(zone_data) for zone_data in data["scene"]["zones"]]
    return Project(
        name=data.get("name", "untitled"),
        scene=Scene(zones=zones),
        format_version=format_version,
    )


def save_project(project: Project, path: str | Path) -> None:
    path = Path(path)
    path.write_text(json.dumps(project_to_dict(project), indent=2), encoding="utf-8")


def load_project(path: str | Path) -> Project:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return project_from_dict(data)
