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
        help="Genere un caisson lumineux par lettre individuelle (corps + capot + fond + DXF)",
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
    from lithoshape3d.core.geometry.lightbox_letters_export import generate_lightbox_letters

    images_by_index = _parse_indexed_kv(args.image_letter)
    transforms_raw = _parse_indexed_kv(args.transform_letter)
    transforms_by_index = {idx: _parse_transform(raw) for idx, raw in transforms_raw.items()}

    result = generate_lightbox_letters(
        args.text,
        args.font,
        args.output_dir,
        font_size_mm=args.font_size,
        resolution=args.resolution,
        depth_mm=args.depth,
        wall_thickness_mm=args.wall_thickness,
        back_thickness_mm=args.back_thickness,
        min_thickness_mm=args.min_thickness,
        max_thickness_mm=args.max_thickness,
        images_by_index=images_by_index,
        transforms_by_index=transforms_by_index,
    )

    for level, text in result.messages:
        prefix = "ECHEC" if level == "error" else "AVERTISSEMENT"
        print(f"{prefix}: {text}")

    if not result.ok:
        print("ECHEC: aucune lettre n'a pu etre generee.")
        return 1

    print("OK:", ", ".join(str(path) for path in result.written))
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
