"""Pipeline complet "image -> caisson lumineux vectoriel" (LightBox depuis
image). Meme moteur d'extrusion/epaulement que LightBox Letters
(`vector_lightbox.py`, partage sans duplication -- voir sa docstring), mais
la source du contour est une silhouette extraite d'image
(`image_shape_extractor.py`) au lieu d'un glyphe de police.

Capot par defaut PLAT/LISSE (extrusion vectorielle directe du footprint
d'epaulement, pas de relief lithophanie) : cas d'usage confirme "pour
circuit foil, pas besoin de litho, juste un capot lumineux". Une image de
lithophanie separee peut etre assignee au capot (`cap_image_path`), auquel
cas le capot reutilise EXACTEMENT le meme pipeline heightfield/lithophanie
que LightBox Letters (`lightbox.build_lightbox_lithophane_face_mesh`) --
aucune logique de generation dupliquee ici, seulement de la glue.

Factorise pour eviter toute duplication entre le CLI (`lightbox-image`) et
l'ecran GUI (`ui/lightbox_image_dialog.py`) : les deux se contentent
d'appeler `generate_lightbox_from_image` puis de formater le resultat --
meme principe que `lightbox_letters_export.py`."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lithoshape3d.core.scene.models import GeometryParameters, ImageTransform

DEFAULT_CAP_THICKNESS_MM = 1.5
"""Epaisseur du capot plat/lisse par defaut (mode sans lithophanie) : reste
dans l'epaisseur de l'epaulement (`SHOULDER_DEPTH_MM` = 1.75mm, voir
`vector_lightbox.py`) pour un capot affleurant, assez epais pour rester
rigide et opaque a l'impression -- un capot pour circuit foil n'a pas besoin
d'etre translucide (PLA blanc standard convient), contrairement a une
facade lithophanie."""


@dataclass
class LightboxImageResult:
    """Resultat structure d'une generation lightbox-image -- meme forme que
    `LightboxLettersResult` (`lightbox_letters_export.py`), pour que CLI et
    UI le consomment de la meme maniere."""

    written: list[Path] = field(default_factory=list)
    messages: list[tuple[str, str]] = field(default_factory=list)
    threshold_used: int | None = None
    """Seuil 0-255 effectivement applique (Cas B / photo uniquement),
    `None` si la silhouette a ete extraite depuis un canal alpha (Cas A)."""

    @property
    def warnings(self) -> list[str]:
        return [text for level, text in self.messages if level == "warning"]

    @property
    def errors(self) -> list[str]:
        return [text for level, text in self.messages if level == "error"]

    @property
    def ok(self) -> bool:
        return bool(self.written)


def _slug_from_path(image_path: str | Path) -> str:
    stem = Path(image_path).stem
    slug = "".join(c if c.isalnum() else "_" for c in stem).lower()
    return slug or "image"


def compute_shape_and_cap_mask(
    image_path: str | Path,
    width_mm: float,
    *,
    threshold_mode: str = "auto",
    threshold_value: int | None = None,
    min_component_area_ratio: float = 0.001,
    wall_thickness_mm: float = 1.6,
    resolution: float | None = None,
):
    """Calcule la forme extraite ET le masque rasterise du footprint du
    capot (retreci pour l'epaulement) -- reutilise par l'UI pour le cadrage
    visuel de l'image de capot lithophanie (`CadrageDialog`), avec EXACTEMENT
    le meme calcul que la generation reelle (aucune duplication). Retourne
    `(ImageShapeResult, GeometryParameters, cap_mask)`."""
    from dataclasses import fields

    from lithoshape3d.core.geometry.heightmap import grid_dimensions
    from lithoshape3d.core.geometry.image_shape_extractor import extract_shape_from_image
    from lithoshape3d.core.geometry.letter_glyph_extractor import rasterize_polygon_mask
    from lithoshape3d.core.geometry.vector_lightbox import vector_lightbox_cap_footprint

    shape = extract_shape_from_image(
        image_path,
        width_mm,
        threshold_mode=threshold_mode,
        threshold_value=threshold_value,
        min_component_area_ratio=min_component_area_ratio,
    )
    cap_polygon = vector_lightbox_cap_footprint(shape.polygon, wall_thickness_mm)

    gp_defaults = {f.name: f.default for f in fields(GeometryParameters)}
    face_params = GeometryParameters(
        width_mm=shape.width_mm,
        height_mm=shape.height_mm,
        resolution=resolution if resolution is not None else gp_defaults["resolution"],
    )
    rows, cols = grid_dimensions(face_params)
    cap_mask = rasterize_polygon_mask(cap_polygon, shape.width_mm, shape.height_mm, rows, cols)
    return shape, face_params, cap_mask


def generate_lightbox_from_image(
    image_path: str | Path,
    output_dir: str | Path,
    *,
    width_mm: float = 100.0,
    depth_mm: float = 25.0,
    wall_thickness_mm: float = 1.6,
    back_thickness_mm: float = 1.2,
    threshold_mode: str = "auto",
    threshold_value: int | None = None,
    min_component_area_ratio: float = 0.001,
    cap_thickness_mm: float = DEFAULT_CAP_THICKNESS_MM,
    cap_image_path: str | Path | None = None,
    cap_image_transform: ImageTransform | None = None,
    resolution: float | None = None,
    min_thickness_mm: float | None = None,
    max_thickness_mm: float | None = None,
) -> LightboxImageResult:
    """Genere un caisson lumineux vectoriel depuis une image (corps + fond +
    capot + DXF). `image_path` doit deja etre un raster PNG/JPG (la
    conversion SVG -> PNG, via Qt, est la responsabilite de l'appelant --
    voir `ui/shape_svg_import.py` -- `core/` ne depend jamais de Qt).

    Capot : PLAT/LISSE par defaut (`cap_image_path=None`, extrusion
    vectorielle directe du footprint d'epaulement) ; lithophanie si
    `cap_image_path` est fourni (meme moteur heightfield que
    `lightbox-letters`)."""
    from dataclasses import fields

    import trimesh

    from lithoshape3d.core.export.stl_export import export_stl
    from lithoshape3d.core.geometry.heightmap import grid_dimensions
    from lithoshape3d.core.geometry.image_shape_extractor import (
        ImageShapeExtractionError,
        extract_shape_from_image,
    )
    from lithoshape3d.core.geometry.letter_glyph_extractor import rasterize_polygon_mask
    from lithoshape3d.core.geometry.lightbox import build_lightbox_lithophane_face_mesh
    from lithoshape3d.core.geometry.vector_lightbox import (
        SHOULDER_DEPTH_MM,
        build_vector_lightbox_back_panel_mesh,
        build_vector_lightbox_body_mesh,
        vector_lightbox_cap_footprint,
    )
    from lithoshape3d.core.validation.mesh_checks import validate_mesh

    result = LightboxImageResult()

    if width_mm <= 0 or depth_mm <= 0 or wall_thickness_mm <= 0 or back_thickness_mm <= 0:
        raise ValueError(
            "Toutes les dimensions (largeur, profondeur, parois, fond) doivent etre > 0."
        )

    try:
        shape = extract_shape_from_image(
            image_path,
            width_mm,
            threshold_mode=threshold_mode,
            threshold_value=threshold_value,
            min_component_area_ratio=min_component_area_ratio,
        )
    except (ImageShapeExtractionError, ValueError, OSError) as exc:
        result.messages.append(("error", f"extraction de la silhouette : {exc}"))
        return result

    result.threshold_used = shape.threshold_used
    for warning in shape.warnings:
        result.messages.append(("warning", warning))

    outer = shape.polygon

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = _slug_from_path(image_path)

    # Corps : extrusion directe du contour vectoriel exact de la silhouette
    # (parois lisses + epaulement de retention du capot) -- meme moteur que
    # LightBox Letters, voir `vector_lightbox.py`.
    try:
        body_mesh, body_warnings = build_vector_lightbox_body_mesh(outer, depth_mm, wall_thickness_mm)
    except ValueError as exc:
        result.messages.append(("error", f"corps : {exc}"))
        return result
    for warning in body_warnings:
        result.messages.append(("warning", warning))

    body_validation = validate_mesh(body_mesh)
    if not body_validation.is_valid:
        result.messages.append(
            ("error", f"validation corps : {', '.join(body_validation.issues())}")
        )
        return result
    body_path = output_dir / f"{slug}_corps.stl"
    export_stl(body_mesh, body_path)
    result.written.append(body_path)

    # Fond : meme extrusion vectorielle, plein, sans cavite.
    try:
        back_panel_mesh = build_vector_lightbox_back_panel_mesh(outer, back_thickness_mm)
    except ValueError as exc:
        result.messages.append(("error", f"fond : {exc}"))
    else:
        back_validation = validate_mesh(back_panel_mesh)
        if back_validation.is_valid:
            back_path = output_dir / f"{slug}_fond.stl"
            export_stl(back_panel_mesh, back_path)
            result.written.append(back_path)
        else:
            result.messages.append(
                ("error", f"validation fond : {', '.join(back_validation.issues())}")
            )

    # Capot : plat/lisse par defaut, ou lithophanie si une image est fournie.
    cap_polygon = vector_lightbox_cap_footprint(outer, wall_thickness_mm)
    cap_depth_mm = depth_mm - SHOULDER_DEPTH_MM
    if cap_polygon.is_empty or cap_polygon.area <= 0:
        result.messages.append(
            (
                "warning",
                "capot ignore (footprint d'epaulement vide -- silhouette trop fine pour ces "
                "parametres d'epaisseur de paroi).",
            )
        )
    elif cap_image_path:
        gp_defaults = {f.name: f.default for f in fields(GeometryParameters)}
        face_params = GeometryParameters(
            width_mm=shape.width_mm,
            height_mm=shape.height_mm,
            min_thickness_mm=(
                min_thickness_mm if min_thickness_mm is not None else gp_defaults["min_thickness_mm"]
            ),
            max_thickness_mm=(
                max_thickness_mm if max_thickness_mm is not None else gp_defaults["max_thickness_mm"]
            ),
            resolution=resolution if resolution is not None else gp_defaults["resolution"],
        )
        rows, cols = grid_dimensions(face_params)
        cap_shape_mask = rasterize_polygon_mask(cap_polygon, shape.width_mm, shape.height_mm, rows, cols)
        if cap_shape_mask.any():
            face_mesh = build_lightbox_lithophane_face_mesh(
                cap_image_path, cap_shape_mask, face_params, cap_depth_mm, cap_image_transform
            )
            face_validation = validate_mesh(face_mesh)
            if face_validation.is_valid:
                cap_path = output_dir / f"{slug}_capot.stl"
                export_stl(face_mesh, cap_path)
                result.written.append(cap_path)
            else:
                result.messages.append(
                    ("error", f"validation capot : {', '.join(face_validation.issues())}")
                )
        else:
            result.messages.append(("warning", "capot ignore (footprint vide a cette resolution)."))
    else:
        cap_mesh = build_vector_lightbox_back_panel_mesh(cap_polygon, cap_thickness_mm)
        cap_mesh = cap_mesh.copy()
        cap_mesh.apply_translation((0.0, 0.0, cap_depth_mm))
        cap_validation = validate_mesh(cap_mesh)
        if cap_validation.is_valid:
            cap_path = output_dir / f"{slug}_capot.stl"
            export_stl(cap_mesh, cap_path)
            result.written.append(cap_path)
        else:
            result.messages.append(
                ("error", f"validation capot : {', '.join(cap_validation.issues())}")
            )

    # Export DXF decoupe (contour de la silhouette) et base/LED (meme
    # contour, reserve a un futur offset de clairance) -- meme principe que
    # `generate_lightbox_letters`.
    try:
        path2d = trimesh.load_path(outer)
        decoupe_path = output_dir / f"{slug}_decoupe.dxf"
        path2d.export(str(decoupe_path))
        result.written.append(decoupe_path)

        base_led_path = output_dir / f"{slug}_base_led.dxf"
        path2d.export(str(base_led_path))
        result.written.append(base_led_path)
    except Exception as exc:  # pragma: no cover - export best-effort
        result.messages.append(("warning", f"export DXF impossible : {exc}"))

    return result
