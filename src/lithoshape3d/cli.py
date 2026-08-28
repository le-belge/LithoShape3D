"""Point d'entree headless. Ne depend que de `core` (pas de Qt, pas de PyVista)."""

from __future__ import annotations

import argparse
from dataclasses import fields
from pathlib import Path

from lithoshape3d import __version__
from lithoshape3d.core.scene.models import GeometryParameters

_GP_DEFAULTS = {f.name: f.default for f in fields(GeometryParameters)}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lithoshape3d")
    parser.add_argument("--version", action="version", version=f"lithoshape3d {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    generate = subparsers.add_parser(
        "generate", help="Genere un STL de lithophanie a partir d'une image"
    )
    generate.add_argument("input", help="Image source (PNG/JPG)")
    generate.add_argument("output", help="Fichier STL de sortie")
    generate.add_argument("--width", type=float, required=True, help="Largeur en mm")
    generate.add_argument(
        "--height", type=float, default=None, help="Hauteur en mm (deduite du ratio si omise)"
    )
    generate.add_argument("--min-thickness", type=float, default=_GP_DEFAULTS["min_thickness_mm"])
    generate.add_argument("--max-thickness", type=float, default=_GP_DEFAULTS["max_thickness_mm"])
    generate.add_argument("--resolution", type=float, default=_GP_DEFAULTS["resolution"])
    generate.add_argument("--invert", action="store_true", default=_GP_DEFAULTS["invert"])
    generate.add_argument("--brightness", type=float, default=0.0)
    generate.add_argument("--contrast", type=float, default=1.0)

    lightbox = subparsers.add_parser(
        "lightbox-text",
        help="Genere un caisson texte avec facade lithophanie en STL separes",
    )
    lightbox.add_argument("input", help="Image source de lithophanie (PNG/JPG)")
    lightbox.add_argument("output_dir", help="Dossier de sortie des STL")
    lightbox.add_argument("--text", required=True, help="Texte de la box")
    lightbox.add_argument("--width", type=float, required=True, help="Largeur en mm")
    lightbox.add_argument(
        "--height", type=float, default=None, help="Hauteur en mm (deduite du ratio si omise)"
    )
    lightbox.add_argument("--depth", type=float, default=35.0, help="Profondeur du caisson en mm")
    lightbox.add_argument("--wall-thickness", type=float, default=2.0, help="Epaisseur des parois")
    lightbox.add_argument("--back-thickness", type=float, default=1.2, help="Epaisseur du fond")
    lightbox.add_argument("--no-back-panel", action="store_true", help="Ne pas generer de fond")
    lightbox.add_argument("--min-thickness", type=float, default=_GP_DEFAULTS["min_thickness_mm"])
    lightbox.add_argument("--max-thickness", type=float, default=_GP_DEFAULTS["max_thickness_mm"])
    lightbox.add_argument("--resolution", type=float, default=_GP_DEFAULTS["resolution"])
    lightbox.add_argument("--invert", action="store_true", default=_GP_DEFAULTS["invert"])
    lightbox.add_argument("--font", default=None, help="Chemin optionnel vers une police .ttf/.otf")
    lightbox.add_argument("--regular", action="store_true", help="Desactive le faux gras Pillow")

    letters = subparsers.add_parser(
        "lightbox-letters",
        help="Genere un caisson lumineux par lettre individuelle (corps + capot + DXF)",
    )
    letters.add_argument("--text", required=True, help="Mot a decouper en lettres")
    letters.add_argument("--font", required=True, help="Chemin vers une police .ttf/.otf")
    letters.add_argument("--output-dir", required=True, help="Dossier de sortie")
    letters.add_argument("--font-size", type=float, default=40.0, help="Taille de corps en mm")
    letters.add_argument("--resolution", type=float, default=_GP_DEFAULTS["resolution"])
    letters.add_argument("--depth", type=float, default=25.0, help="Profondeur du caisson en mm")
    letters.add_argument("--wall-thickness", type=float, default=1.6, help="Epaisseur des parois")
    letters.add_argument("--back-thickness", type=float, default=1.2, help="Epaisseur du fond")
    letters.add_argument("--min-thickness", type=float, default=_GP_DEFAULTS["min_thickness_mm"])
    letters.add_argument("--max-thickness", type=float, default=_GP_DEFAULTS["max_thickness_mm"])
    letters.add_argument(
        "--image-letter",
        action="append",
        default=[],
        metavar="INDEX=PATH",
        help="Image de lithophanie pour la lettre d'index INDEX (0-based). Repetable.",
    )
    letters.add_argument(
        "--transform-letter",
        action="append",
        default=[],
        metavar="INDEX=offset_x=..,offset_y=..,scale=..,rotation_deg=..",
        help="Transform de cadrage pour la lettre d'index INDEX. Repetable.",
    )

    return parser


def _cmd_generate(args: argparse.Namespace) -> int:
    from lithoshape3d.core.export.stl_export import export_stl
    from lithoshape3d.core.geometry.heightmap import (
        height_mm_from_aspect_ratio,
        heightmap_from_image_path,
    )
    from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
    from lithoshape3d.core.image.pipeline import image_size
    from lithoshape3d.core.validation.mesh_checks import validate_mesh

    if args.height is not None:
        height_mm = args.height
    else:
        image_width_px, image_height_px = image_size(args.input)
        height_mm = height_mm_from_aspect_ratio(args.width, image_width_px, image_height_px)

    params = GeometryParameters(
        width_mm=args.width,
        height_mm=height_mm,
        min_thickness_mm=args.min_thickness,
        max_thickness_mm=args.max_thickness,
        invert=args.invert,
        resolution=args.resolution,
    )

    heightmap = heightmap_from_image_path(
        args.input, params, brightness=args.brightness, contrast=args.contrast
    )
    mesh = build_slab_mesh(heightmap, mask=None, params=params)

    result = validate_mesh(mesh)
    if not result.is_valid:
        print("ECHEC validation du mesh :", ", ".join(result.issues()))
        return 1

    export_stl(mesh, args.output)
    print(
        f"OK: {args.output} "
        f"({len(mesh.vertices)} sommets, {len(mesh.faces)} faces, "
        f"volume={result.volume_mm3:.1f} mm3)"
    )
    return 0


def _cmd_lightbox_text(args: argparse.Namespace) -> int:
    from lithoshape3d.core.export.stl_export import export_stl
    from lithoshape3d.core.geometry.heightmap import height_mm_from_aspect_ratio
    from lithoshape3d.core.geometry.lightbox import LightBoxParameters, build_text_lightbox
    from lithoshape3d.core.image.pipeline import image_size
    from lithoshape3d.core.validation.mesh_checks import validate_mesh

    if args.height is not None:
        height_mm = args.height
    else:
        image_width_px, image_height_px = image_size(args.input)
        height_mm = height_mm_from_aspect_ratio(args.width, image_width_px, image_height_px)

    face_params = GeometryParameters(
        width_mm=args.width,
        height_mm=height_mm,
        min_thickness_mm=args.min_thickness,
        max_thickness_mm=args.max_thickness,
        invert=args.invert,
        resolution=args.resolution,
    )
    box_params = LightBoxParameters(
        depth_mm=args.depth,
        wall_thickness_mm=args.wall_thickness,
        back_panel_thickness_mm=args.back_thickness,
        include_back_panel=not args.no_back_panel,
    )
    result = build_text_lightbox(
        args.text,
        args.input,
        face_params,
        box_params,
        font_path=args.font,
        bold=not args.regular,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for name, mesh in result.as_meshes().items():
        validation = validate_mesh(mesh)
        if not validation.is_valid:
            print(f"ECHEC validation {name} :", ", ".join(validation.issues()))
            return 1
        path = output_dir / f"lightbox_{name}.stl"
        export_stl(mesh, path)
        written.append(path)

    for warning in result.warnings:
        print(f"AVERTISSEMENT: {warning}")
    print("OK:", ", ".join(str(path) for path in written))
    return 0


def _parse_indexed_kv(raw_values: list[str]) -> dict[int, str]:
    result: dict[int, str] = {}
    for raw in raw_values:
        index_str, _, value = raw.partition("=")
        try:
            index = int(index_str)
        except ValueError as exc:
            raise ValueError(f"Index invalide dans '{raw}' (attendu INDEX=...).") from exc
        result[index] = value
    return result


def _parse_transform(raw: str):
    from lithoshape3d.core.scene.models import ImageTransform

    kwargs: dict[str, float] = {}
    for part in raw.split(","):
        key, _, value = part.partition("=")
        key = key.strip()
        if not key:
            continue
        if key == "offset_x":
            kwargs["offset_x"] = float(value)
        elif key == "offset_y":
            kwargs["offset_y"] = float(value)
        elif key == "scale":
            kwargs["scale"] = float(value)
        elif key == "rotation_deg":
            kwargs["rotation_deg"] = float(value)
        else:
            raise ValueError(f"Cle de transform inconnue : '{key}'.")
    return ImageTransform(**kwargs)


def _cmd_lightbox_letters(args: argparse.Namespace) -> int:
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
    from lithoshape3d.core.validation.mesh_checks import validate_mesh
    import trimesh

    layout = extract_word_glyphs(args.text, args.font, font_size_mm=args.font_size)
    for warning in layout.warnings:
        print(f"AVERTISSEMENT: {warning}")

    images_by_index = _parse_indexed_kv(args.image_letter)
    transforms_raw = _parse_indexed_kv(args.transform_letter)
    transforms_by_index = {idx: _parse_transform(raw) for idx, raw in transforms_raw.items()}

    face_params = GeometryParameters(
        width_mm=layout.width_mm,
        height_mm=layout.height_mm,
        min_thickness_mm=args.min_thickness,
        max_thickness_mm=args.max_thickness,
        resolution=args.resolution,
    )
    box_params_lithophane = LightBoxParameters(
        depth_mm=args.depth,
        wall_thickness_mm=args.wall_thickness,
        back_panel_thickness_mm=args.back_thickness,
        face_mode=LightBoxFaceMode.LITHOPHANE,
    )
    box_params_solid = LightBoxParameters(
        depth_mm=args.depth,
        wall_thickness_mm=args.wall_thickness,
        back_panel_thickness_mm=args.back_thickness,
        face_mode=LightBoxFaceMode.SOLID,
    )

    from lithoshape3d.core.geometry.heightmap import grid_dimensions

    rows, cols = grid_dimensions(face_params)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    slug = "".join(c if c.isalnum() else "_" for c in args.text).lower() or "mot"

    for letter in layout.letters:
        for w in letter.warnings:
            print(f"AVERTISSEMENT lettre '{letter.character}' (#{letter.index}): {w}")

        min_wall = args.wall_thickness
        glyph_width = letter.bbox_mm[2] - letter.bbox_mm[0]
        if glyph_width < min_wall * 2:
            print(
                f"AVERTISSEMENT: lettre '{letter.character}' (#{letter.index}) trop fine "
                f"({glyph_width:.2f} mm) pour l'epaisseur de paroi demandee "
                f"({min_wall} mm) -- caisson ignore pour cette lettre."
            )
            continue

        shape_mask = rasterize_letter_mask(letter, layout.width_mm, layout.height_mm, rows, cols)

        image_path = images_by_index.get(letter.index)
        image_transform = transforms_by_index.get(letter.index)
        box_params = box_params_lithophane if image_path else box_params_solid

        prefix = f"{slug}_lettre_{letter.index}_{letter.character.lower()}"
        try:
            result = build_lightbox_from_shape_mask(
                shape_mask,
                face_params,
                box_params,
                image_path=image_path,
                image_transform=image_transform,
            )
        except ValueError as exc:
            print(f"ECHEC lettre '{letter.character}' (#{letter.index}) : {exc}")
            continue

        for warning in result.warnings:
            print(f"AVERTISSEMENT lettre '{letter.character}': {warning}")

        body_validation = validate_mesh(result.body_mesh)
        if not body_validation.is_valid:
            print(
                f"ECHEC validation corps lettre '{letter.character}' : "
                f"{', '.join(body_validation.issues())}"
            )
            continue
        body_path = output_dir / f"{prefix}_corps.stl"
        export_stl(result.body_mesh, body_path)
        written.append(body_path)

        if result.face_mesh is not None:
            face_validation = validate_mesh(result.face_mesh)
            if face_validation.is_valid:
                face_path = output_dir / f"{prefix}_capot.stl"
                export_stl(result.face_mesh, face_path)
                written.append(face_path)
            else:
                print(
                    f"ECHEC validation capot lettre '{letter.character}' : "
                    f"{', '.join(face_validation.issues())}"
                )

        # Export DXF decoupe (contour de la lettre) et base/LED (meme
        # contour, reserve a un futur offset de clairance) -- reutilise
        # directement le contour deja extrait, en unites mm absolues.
        try:
            polygon = letter.to_shapely()
            path2d = trimesh.load_path(polygon)
            decoupe_path = output_dir / f"{prefix}_decoupe.dxf"
            path2d.export(str(decoupe_path))
            written.append(decoupe_path)

            base_led_path = output_dir / f"{prefix}_base_led.dxf"
            path2d.export(str(base_led_path))
            written.append(base_led_path)
        except Exception as exc:  # pragma: no cover - export best-effort
            print(f"AVERTISSEMENT: export DXF impossible pour '{letter.character}' : {exc}")

    if not written:
        print("ECHEC: aucune lettre n'a pu etre generee.")
        return 1

    print("OK:", ", ".join(str(path) for path in written))
    return 0


def _cmd_launch_app() -> int:
    from lithoshape3d.ui.app import run_app

    return run_app()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    if args.command == "generate":
        return _cmd_generate(args)
    if args.command == "lightbox-text":
        return _cmd_lightbox_text(args)
    if args.command == "lightbox-letters":
        return _cmd_lightbox_letters(args)

    return _cmd_launch_app()


if __name__ == "__main__":
    raise SystemExit(main())
