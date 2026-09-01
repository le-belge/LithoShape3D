"""Serialisation JSON versionnee du modele Project / Scene / Zone.

Seule la structure legere (parametres, chemins, references) est ecrite.
Les meshes generes ne sont jamais embarques : `Zone.mesh_cache_path` pointe
vers un fichier a part (cache local), pas vers des donnees inline.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from lithoshape3d.core.scene.models import (
    BacklightInsertParams,
    ColorStrategy,
    CompositionMode,
    GeometryParameters,
    ImageTransform,
    Material,
    PrintSupport,
    Project,
    ReliefMode,
    Scene,
    ShapeParams,
    ShapeType,
    SupportType,
    Transform,
    Zone,
)

CURRENT_FORMAT_VERSION = 6


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
        "slot": material.slot,
    }


def _material_from_dict(data: dict[str, Any]) -> Material:
    return Material(
        name=data.get("name", "default"),
        color=tuple(data.get("color", (1.0, 1.0, 1.0))),
        filament_type=data.get("filament_type"),
        translucent=data.get("translucent", False),
        slot=data.get("slot"),
    )


def _support_to_dict(support: PrintSupport) -> dict[str, Any]:
    return {
        "support_type": support.support_type.value,
        "depth_mm": support.depth_mm,
        "height_mm": support.height_mm,
        "overhang_left_mm": support.overhang_left_mm,
        "overhang_right_mm": support.overhang_right_mm,
        "rib_count": support.rib_count,
        "rib_thickness_mm": support.rib_thickness_mm,
        "side_stabilizers": support.side_stabilizers,
    }


def _support_from_dict(data: dict[str, Any]) -> PrintSupport:
    return PrintSupport(
        support_type=SupportType(data.get("support_type", SupportType.NONE.value)),
        depth_mm=data.get("depth_mm", 25.0),
        height_mm=data.get("height_mm", 8.0),
        overhang_left_mm=data.get("overhang_left_mm", 5.0),
        overhang_right_mm=data.get("overhang_right_mm", 5.0),
        rib_count=data.get("rib_count", 3),
        rib_thickness_mm=data.get("rib_thickness_mm", 2.0),
        side_stabilizers=data.get("side_stabilizers", False),
    )


def _shape_to_dict(shape: ShapeParams) -> dict[str, Any]:
    return {
        "shape_type": shape.shape_type.value,
        "text": shape.text,
        "font_path": shape.font_path,
        "bold": shape.bold,
        "source_image_path": shape.source_image_path,
        "border_width_mm": shape.border_width_mm,
    }


def _shape_from_dict(data: dict[str, Any]) -> ShapeParams:
    return ShapeParams(
        shape_type=ShapeType(data.get("shape_type", ShapeType.RECTANGLE.value)),
        text=data.get("text", ""),
        font_path=data.get("font_path"),
        bold=data.get("bold", False),
        source_image_path=data.get("source_image_path"),
        border_width_mm=data.get("border_width_mm", 0.0),
    )


def _image_transform_to_dict(transform: ImageTransform) -> dict[str, Any]:
    return {
        "offset_x": transform.offset_x,
        "offset_y": transform.offset_y,
        "scale": transform.scale,
        "rotation_deg": transform.rotation_deg,
        "fit_mode": transform.fit_mode,
    }


def _image_transform_from_dict(data: dict[str, Any]) -> ImageTransform:
    return ImageTransform(
        offset_x=data.get("offset_x", 0.0),
        offset_y=data.get("offset_y", 0.0),
        scale=data.get("scale", 1.0),
        rotation_deg=data.get("rotation_deg", 0.0),
        fit_mode=data.get("fit_mode", "fit"),
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


def _backlight_insert_to_dict(params: BacklightInsertParams) -> dict[str, Any]:
    return {
        "white_skin_thickness_mm": params.white_skin_thickness_mm,
        "insert_thickness_mm": params.insert_thickness_mm,
        "xy_clearance_mm": params.xy_clearance_mm,
        "pocket_extra_depth_mm": params.pocket_extra_depth_mm,
        "transition_width_mm": params.transition_width_mm,
    }


def _backlight_insert_from_dict(data: dict[str, Any]) -> BacklightInsertParams:
    # "chamfer_width_mm" : ancien nom du champ (retire au profit de la
    # logique "soft organic pocket", cf. transition_width_mm) -- lu ici
    # uniquement pour ne pas planter sur un projet sauvegarde avant ce
    # changement, jamais ecrit par `_backlight_insert_to_dict`.
    defaults = BacklightInsertParams()
    return BacklightInsertParams(
        white_skin_thickness_mm=data.get("white_skin_thickness_mm", defaults.white_skin_thickness_mm),
        insert_thickness_mm=data.get("insert_thickness_mm", defaults.insert_thickness_mm),
        xy_clearance_mm=data.get("xy_clearance_mm", defaults.xy_clearance_mm),
        pocket_extra_depth_mm=data.get("pocket_extra_depth_mm", defaults.pocket_extra_depth_mm),
        transition_width_mm=data.get(
            "transition_width_mm", data.get("chamfer_width_mm", defaults.transition_width_mm)
        ),
    )


def _zone_to_dict(zone: Zone) -> dict[str, Any]:
    return {
        "id": zone.id,
        "name": zone.name,
        "visible": zone.visible,
        "source_image_path": zone.source_image_path,
        "mask_path": zone.mask_path,
        "geometry_params": _geometry_params_to_dict(zone.geometry_params),
        "material": _material_to_dict(zone.material),
        "transform": _transform_to_dict(zone.transform),
        "relief_mode": zone.relief_mode.value,
        "composition_mode": zone.composition_mode.value,
        "color_strategy": zone.color_strategy.value if zone.color_strategy is not None else None,
        "backlight_insert": _backlight_insert_to_dict(zone.backlight_insert),
        "mesh_cache_path": zone.mesh_cache_path,
    }


def _zone_from_dict(data: dict[str, Any]) -> Zone:
    color_strategy_value = data.get("color_strategy")
    return Zone(
        id=data.get("id", None) or Zone().id,
        name=data.get("name", "zone"),
        visible=data.get("visible", True),
        source_image_path=data.get("source_image_path"),
        mask_path=data.get("mask_path"),
        geometry_params=_geometry_params_from_dict(data["geometry_params"]),
        material=_material_from_dict(data.get("material", {})),
        transform=_transform_from_dict(data.get("transform", {})),
        relief_mode=ReliefMode(data.get("relief_mode", ReliefMode.LITHOPHANE.value)),
        composition_mode=CompositionMode(data.get("composition_mode", CompositionMode.ADD.value)),
        color_strategy=ColorStrategy(color_strategy_value) if color_strategy_value is not None else None,
        backlight_insert=_backlight_insert_from_dict(data.get("backlight_insert", {})),
        mesh_cache_path=data.get("mesh_cache_path"),
    )


def project_to_dict(project: Project) -> dict[str, Any]:
    return {
        "format_version": project.format_version,
        "name": project.name,
        "scene": {
            "zones": [_zone_to_dict(zone) for zone in project.scene.zones],
            "source_image_path": project.scene.source_image_path,
            "active_zone_id": project.scene.active_zone_id,
            "support": _support_to_dict(project.scene.support),
            "shape": _shape_to_dict(project.scene.shape),
            "image_transform": _image_transform_to_dict(project.scene.image_transform),
        },
    }


def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Migration defensive : ne suppose PAS qu'un projet v1 n'a qu'une zone.

    1. cherche la premiere zone avec un source_image_path valide (non vide) ;
    2. la promeut en Scene.source_image_path ;
    3. conserve toutes les zones ;
    4. met a None le source_image_path d'une zone seulement s'il correspond
       exactement a la source commune promue (sinon c'est une vraie source
       differente, conservee comme override) ;
    5. ajoute `visible=True` a chaque zone (champ absent en v1) ;
    6. fixe active_zone_id sur la premiere zone si des zones existent.
    """
    zones_data = data.get("scene", {}).get("zones", [])

    shared_source = next(
        (z.get("source_image_path") for z in zones_data if z.get("source_image_path")),
        None,
    )

    for zone_data in zones_data:
        zone_data.setdefault("visible", True)
        if shared_source is not None and zone_data.get("source_image_path") == shared_source:
            zone_data["source_image_path"] = None

    data.setdefault("scene", {})
    data["scene"]["source_image_path"] = shared_source
    data["scene"]["active_zone_id"] = zones_data[0]["id"] if zones_data else None
    data["format_version"] = 2
    return data


def _migrate_v2_to_v3(data: dict[str, Any]) -> dict[str, Any]:
    """Migration additive : ajoute Zone.composition_mode.

    Un projet v2 n'a jamais compose ses zones entre elles (chaque zone
    n'etait generee qu'independamment, seule). Pour ne PAS changer
    silencieusement l'apparence d'un projet existant si l'utilisateur active
    un jour la composition dessus :
      - la premiere zone devient BASE (fondation, coherent avec le
        comportement historique "generer la zone active" ou la premiere
        zone est typiquement la lithophanie complete) ;
      - toutes les zones suivantes deviennent REPLACE, pas ADD : une zone
        REPLACE conserve exactement son propre contenu dans son masque
        (comme une generation independante), alors qu'ADD cumulerait des
        epaisseurs qui ne se sont jamais sommees auparavant -- un choix ADD
        par defaut aurait modifie le resultat visuel de facon inattendue.
    """
    zones_data = data.get("scene", {}).get("zones", [])
    for index, zone_data in enumerate(zones_data):
        zone_data.setdefault(
            "composition_mode", CompositionMode.BASE.value if index == 0 else CompositionMode.REPLACE.value
        )
    data["format_version"] = 3
    return data


def _migrate_v3_to_v4(data: dict[str, Any]) -> dict[str, Any]:
    """Migration additive : ajoute Zone.material.slot et Scene.support.

    Purement additive -- `_material_from_dict`/`_support_from_dict` savent
    deja fournir des valeurs par defaut sures pour ces champs absents, cette
    migration existe surtout pour documenter explicitement le saut de
    version (introduction des materiaux/supports d'impression en v0.3) plutot
    que de laisser un projet v3 silencieusement "passer" pour v4."""
    data.setdefault("scene", {}).setdefault("support", {"support_type": SupportType.NONE.value})
    data["format_version"] = 4
    return data


def _migrate_v4_to_v5(data: dict[str, Any]) -> dict[str, Any]:
    """Migration additive : ajoute Scene.shape et Scene.image_transform
    (Shape Composer, v0.4). Un projet v4 devient explicitement
    `Shape=Rectangle` avec un cadrage identite (offset=0, scale=1,
    rotation=0) -- ce qui reproduit EXACTEMENT son comportement precedent
    (masque de forme = plein cadre, image non recadree) : un projet
    existant ne doit jamais changer visuellement du seul fait de cette
    migration."""
    scene = data.setdefault("scene", {})
    scene.setdefault("shape", {"shape_type": ShapeType.RECTANGLE.value})
    scene.setdefault(
        "image_transform",
        {"offset_x": 0.0, "offset_y": 0.0, "scale": 1.0, "rotation_deg": 0.0, "fit_mode": "fill"},
    )
    data["format_version"] = 5
    return data


def _migrate_v5_to_v6(data: dict[str, Any]) -> dict[str, Any]:
    """Migration additive : ajoute Zone.color_strategy et
    Zone.backlight_insert (Color Strategies / Backlight Insert, v0.4.1).
    `color_strategy=None` explicite pour chaque zone existante -- comportement
    historique intact (ReliefMode/CompositionMode font foi, comme avant cette
    version), AUCUN changement de geometrie du seul fait de cette migration.
    Voir `core/geometry/composition.py` pour l'effet exact de ColorStrategy."""
    for zone_data in data.get("scene", {}).get("zones", []):
        zone_data.setdefault("color_strategy", None)
        zone_data.setdefault("backlight_insert", {})
    data["format_version"] = 6
    return data


_MIGRATIONS = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
    4: _migrate_v4_to_v5,
    5: _migrate_v5_to_v6,
}


def project_from_dict(data: dict[str, Any]) -> Project:
    format_version = data.get("format_version", CURRENT_FORMAT_VERSION)
    if format_version > CURRENT_FORMAT_VERSION:
        raise ValueError(
            f"format_version {format_version} non supporte "
            f"(version maximale geree : {CURRENT_FORMAT_VERSION})"
        )

    data = copy.deepcopy(data)  # les migrations mutent leur argument : ne jamais alterer l'appelant
    while format_version in _MIGRATIONS:
        data = _MIGRATIONS[format_version](data)
        format_version = data["format_version"]

    zones = [_zone_from_dict(zone_data) for zone_data in data["scene"]["zones"]]
    zone_ids = {zone.id for zone in zones}
    active_zone_id = data["scene"].get("active_zone_id")
    if active_zone_id not in zone_ids:
        active_zone_id = zones[0].id if zones else None

    return Project(
        name=data.get("name", "untitled"),
        scene=Scene(
            zones=zones,
            source_image_path=data["scene"].get("source_image_path"),
            active_zone_id=active_zone_id,
            support=_support_from_dict(data["scene"].get("support", {})),
            shape=_shape_from_dict(data["scene"].get("shape", {})),
            image_transform=_image_transform_from_dict(data["scene"].get("image_transform", {})),
        ),
        format_version=format_version,
    )


def save_project(project: Project, path: str | Path) -> None:
    path = Path(path)
    path.write_text(json.dumps(project_to_dict(project), indent=2), encoding="utf-8")


def load_project(path: str | Path) -> Project:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return project_from_dict(data)
