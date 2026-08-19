"""Point d'entree headless. Ne depend que de `core` (pas de Qt, pas de PyVista)."""

from __future__ import annotations

import argparse
from dataclasses import fields

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

    return _cmd_launch_app()


if __name__ == "__main__":
    raise SystemExit(main())
