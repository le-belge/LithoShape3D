"""Logique d'export partagee entre le CLI (`lightbox-letters`) et l'UI.

Factorise le pipeline "mot -> lettres -> caissons STL/DXF" pour eviter toute
duplication entre `cli._cmd_lightbox_letters` et le futur ecran GUI : les
deux se contentent d'appeler `generate_lightbox_letters` puis de formater le
resultat (print pour le CLI, widgets pour l'UI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lithoshape3d.core.scene.models import GeometryParameters, ImageTransform


@dataclass
class LightboxLettersResult:
    """Resultat structure d'une generation lightbox-letters.

    `messages` conserve l'ordre chronologique d'emission (avertissements et
    echecs melanges) sous forme de tuples `(niveau, texte)` avec
    `niveau` dans {"warning", "error"}, pour que l'appelant (CLI ou UI)
    choisisse librement comment les afficher sans perdre d'information."""

    written: list[Path] = field(default_factory=list)
    messages: list[tuple[str, str]] = field(default_factory=list)

    @property
    def warnings(self) -> list[str]:
        return [text for level, text in self.messages if level == "warning"]

    @property
    def errors(self) -> list[str]:
        return [text for level, text in self.messages if level == "error"]

    @property
    def ok(self) -> bool:
        return bool(self.written)


def generate_lightbox_letters(
    text: str,
    font_path: str,
    output_dir: str | Path,
    *,
    font_size_mm: float = 40.0,
    resolution: float | None = None,
    depth_mm: float = 25.0,
    wall_thickness_mm: float = 1.6,
    back_thickness_mm: float = 1.2,
    min_thickness_mm: float | None = None,
    max_thickness_mm: float | None = None,
    images_by_index: dict[int, str] | None = None,
    transforms_by_index: dict[int, ImageTransform] | None = None,
) -> LightboxLettersResult:
    """Genere un caisson lumineux par lettre (corps + capot + DXF).

    Reproduit exactement le comportement de `lithoshape3d lightbox-letters`
    (voir `cli.py`) mais retourne un `LightboxLettersResult` structure au
    lieu d'imprimer sur stdout et de renvoyer un code de sortie -- utilise
    a la fois par le CLI et par l'ecran GUI correspondant.
    """
    from lithoshape3d.core.export.stl_export import export_stl
    from lithoshape3d.core.geometry.lightbox import (
        LightBoxFaceMode,
        LightBoxParameters,
        build_lightbox_from_shape_mask,
    )
    from lithoshape3d.core.geometry.letter_glyph_extractor import (
        extract_word_glyphs,
        rasterize_letter_mask,
    )
    from lithoshape3d.core.geometry.heightmap import grid_dimensions
    from lithoshape3d.core.validation.mesh_checks import validate_mesh
    import trimesh

    gp_defaults = {f.name: f.default for f in __import__("dataclasses").fields(GeometryParameters)}
    if resolution is None:
        resolution = gp_defaults["resolution"]
    if min_thickness_mm is None:
        min_thickness_mm = gp_defaults["min_thickness_mm"]
    if max_thickness_mm is None:
        max_thickness_mm = gp_defaults["max_thickness_mm"]

    images_by_index = images_by_index or {}
    transforms_by_index = transforms_by_index or {}

    result = LightboxLettersResult()

    layout = extract_word_glyphs(text, font_path, font_size_mm=font_size_mm)
    for warning in layout.warnings:
        result.messages.append(("warning", warning))

    face_params = GeometryParameters(
        width_mm=layout.width_mm,
        height_mm=layout.height_mm,
        min_thickness_mm=min_thickness_mm,
        max_thickness_mm=max_thickness_mm,
        resolution=resolution,
    )
    box_params_lithophane = LightBoxParameters(
        depth_mm=depth_mm,
        wall_thickness_mm=wall_thickness_mm,
        back_panel_thickness_mm=back_thickness_mm,
        face_mode=LightBoxFaceMode.LITHOPHANE,
    )
    box_params_solid = LightBoxParameters(
        depth_mm=depth_mm,
        wall_thickness_mm=wall_thickness_mm,
        back_panel_thickness_mm=back_thickness_mm,
        face_mode=LightBoxFaceMode.SOLID,
    )

    rows, cols = grid_dimensions(face_params)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = "".join(c if c.isalnum() else "_" for c in text).lower() or "mot"

    for letter in layout.letters:
        for w in letter.warnings:
            result.messages.append(
                ("warning", f"lettre '{letter.character}' (#{letter.index}): {w}")
            )

        min_wall = wall_thickness_mm
        # La composante la plus fine (ex. la barre du "i") est le vrai
        # facteur limitant, pas la bbox globale du glyphe (qui peut inclure
        # plusieurs composantes disjointes largement espacees).
        narrowest_part = min(
            (max(p[0] for p in part.exterior) - min(p[0] for p in part.exterior))
            for part in letter.parts
        )
        if narrowest_part < min_wall * 2:
            result.messages.append(
                (
                    "warning",
                    f"lettre '{letter.character}' (#{letter.index}) trop fine "
                    f"({narrowest_part:.2f} mm) pour l'epaisseur de paroi demandee "
                    f"({min_wall} mm) -- caisson ignore pour cette lettre.",
                )
            )
            continue

        shape_mask = rasterize_letter_mask(letter, layout.width_mm, layout.height_mm, rows, cols)

        image_path = images_by_index.get(letter.index)
        image_transform = transforms_by_index.get(letter.index)
        box_params = box_params_lithophane if image_path else box_params_solid

        prefix = f"{slug}_lettre_{letter.index}_{letter.character.lower()}"
        try:
            letter_result = build_lightbox_from_shape_mask(
                shape_mask,
                face_params,
                box_params,
                image_path=image_path,
                image_transform=image_transform,
            )
        except ValueError as exc:
            result.messages.append(
                ("error", f"lettre '{letter.character}' (#{letter.index}) : {exc}")
            )
            continue

        for warning in letter_result.warnings:
            result.messages.append(("warning", f"lettre '{letter.character}': {warning}"))

        body_validation = validate_mesh(letter_result.body_mesh)
        if not body_validation.is_valid:
            result.messages.append(
                (
                    "error",
                    f"validation corps lettre '{letter.character}' : "
                    f"{', '.join(body_validation.issues())}",
                )
            )
            continue
        body_path = output_dir / f"{prefix}_corps.stl"
        export_stl(letter_result.body_mesh, body_path)
        result.written.append(body_path)

        if letter_result.face_mesh is not None:
            face_validation = validate_mesh(letter_result.face_mesh)
            if face_validation.is_valid:
                face_path = output_dir / f"{prefix}_capot.stl"
                export_stl(letter_result.face_mesh, face_path)
                result.written.append(face_path)
            else:
                result.messages.append(
                    (
                        "error",
                        f"validation capot lettre '{letter.character}' : "
                        f"{', '.join(face_validation.issues())}",
                    )
                )

        # Export DXF decoupe (contour de la lettre) et base/LED (meme
        # contour, reserve a un futur offset de clairance) -- reutilise
        # directement le contour deja extrait, en unites mm absolues.
        try:
            polygon = letter.to_shapely()
            path2d = trimesh.load_path(polygon)
            decoupe_path = output_dir / f"{prefix}_decoupe.dxf"
            path2d.export(str(decoupe_path))
            result.written.append(decoupe_path)

            base_led_path = output_dir / f"{prefix}_base_led.dxf"
            path2d.export(str(base_led_path))
            result.written.append(base_led_path)
        except Exception as exc:  # pragma: no cover - export best-effort
            result.messages.append(
                ("warning", f"export DXF impossible pour '{letter.character}' : {exc}")
            )

    return result
