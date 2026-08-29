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
        help="Genere un caisson texte avec fond integre et facade lithophanie",
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
    lightbox.add_argument("--back-thickness", type=float, default=1.2, help="Epaisseur du fond integre")
    lightbox.add_argument(
        "--separate-back-panel",
        action="store_true",
        help="Genere le fond en STL separe au lieu de l'integrer au corps",
    )
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
    letters.add_argument(
        "--cap-thickness",
        type=float,
        default=1.2,
        help="Epaisseur du capot plat (mm) -- l'epaulement de retention est ajuste pour correspondre exactement.",
    )
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

    image_box = subparsers.add_parser(
        "lightbox-image",
        help="Genere un caisson lumineux vectoriel a partir d'une silhouette extraite d'image",
    )
    image_box.add_argument("--image", required=True, help="Image source (PNG/JPG/SVG)")
    image_box.add_argument("--output-dir", required=True, help="Dossier de sortie")
    image_box.add_argument("--width-mm", type=float, default=100.0, help="Largeur en mm")
    image_box.add_argument("--depth-mm", type=float, default=25.0, help="Profondeur du caisson en mm")
    image_box.add_argument(
        "--wall-thickness-mm", type=float, default=1.6, help="Epaisseur des parois en mm"
    )
    image_box.add_argument("--back-thickness-mm", type=float, default=1.2, help="Epaisseur du fond en mm")
    image_box.add_argument(
        "--threshold",
        default="auto",
        metavar="auto|0-255",
        help="Seuillage Cas B (photo sans transparence) : 'auto' (Otsu) ou une valeur manuelle 0-255.",
    )
    image_box.add_argument(
        "--min-component-area-ratio",
        type=float,
        default=None,
        help=(
            "Aire minimale (fraction de l'aire totale) pour qu'une composante ne soit pas "
            "consideree comme du bruit. Omis : 0.1%% en mode silhouette, 0.02%% en mode "
            "artwork-envelope (garde le detail fin du trait)."
        ),
    )
    image_box.add_argument(
        "--cap-thickness-mm",
        type=float,
        default=None,
        help="Epaisseur du capot plat/lisse (mode par defaut, sans lithophanie).",
    )
    image_box.add_argument("--cap-image", default=None, help="Image de lithophanie optionnelle pour le capot")
    image_box.add_argument(
        "--cap-transform",
        default=None,
        metavar="offset_x=..,offset_y=..,scale=..,rotation_deg=..",
        help="Transform de cadrage pour l'image du capot (ignore si --cap-image absent).",
    )
    image_box.add_argument("--resolution", type=float, default=_GP_DEFAULTS["resolution"])
    image_box.add_argument("--min-thickness", type=float, default=_GP_DEFAULTS["min_thickness_mm"])
    image_box.add_argument("--max-thickness", type=float, default=_GP_DEFAULTS["max_thickness_mm"])
    image_box.add_argument(
        "--shape-mode",
        default="silhouette",
        choices=["silhouette", "artwork-envelope"],
        help=(
            "'silhouette' (par defaut) : contour = silhouette extraite (logo alpha ou photo "
            "seuillee). 'artwork-envelope' : contour = enveloppe unifiee d'un dessin au trait "
            "(un seul caisson meme si le dessin a des elements disjoints, ex. Thunderdome)."
        ),
    )
    image_box.add_argument(
        "--cap-mode",
        default=None,
        choices=["flat", "lithophane", "flat-two-color"],
        help=(
            "Mode du capot. Omis : lithophanie si --cap-image fourni, sinon plat. "
            "'flat-two-color' : deux capots plats complementaires (encre/fond) decoupes depuis "
            "l'encre du dessin -- necessite --shape-mode artwork-envelope."
        ),
    )
    image_box.add_argument(
        "--closing-radius-px",
        type=int,
        default=None,
        help=(
            "Rayon (px, masque de travail) de la fermeture morphologique unifiant les "
            "composantes d'encre disjointes en mode artwork-envelope. Omis : recherche "
            "automatique du plus petit rayon suffisant."
        ),
    )
    image_box.add_argument(
        "--max-closing-radius-px",
        type=int,
        default=None,
        help="Plafond de la recherche automatique de rayon de fermeture (mode artwork-envelope).",
    )

    shape_lightbox = subparsers.add_parser(
        "lightbox-shape",
        help="Genere un caisson LightBox depuis une silhouette image ou SVG",
    )
    shape_lightbox.add_argument("shape", help="Silhouette source (SVG/PNG/JPG/BMP)")
    shape_lightbox.add_argument("output_dir", help="Dossier de sortie des STL")
    shape_lightbox.add_argument("--width", type=float, required=True, help="Largeur en mm")
    shape_lightbox.add_argument(
        "--height",
        type=float,
        required=True,
        help="Hauteur en mm de la LightBox",
    )
    shape_lightbox.add_argument("--depth", type=float, default=35.0, help="Profondeur du caisson")
    shape_lightbox.add_argument("--wall-thickness", type=float, default=2.0, help="Epaisseur des parois")
    shape_lightbox.add_argument(
        "--back-thickness",
        type=float,
        default=1.2,
        help="Epaisseur du fond integre",
    )
    shape_lightbox.add_argument(
        "--separate-back-panel",
        action="store_true",
        help="Genere le fond en STL separe au lieu de l'integrer au corps",
    )
    shape_lightbox.add_argument(
        "--face",
        choices=("solid", "lithophane", "open"),
        default="solid",
        help="Type de facade : capot plat, lithophanie ou ouverte",
    )
    shape_lightbox.add_argument(
        "--lithophane-image",
        default=None,
        help="Image source de la facade lithophanie si --face lithophane",
    )
    shape_lightbox.add_argument("--min-thickness", type=float, default=_GP_DEFAULTS["min_thickness_mm"])
    shape_lightbox.add_argument("--max-thickness", type=float, default=_GP_DEFAULTS["max_thickness_mm"])
    shape_lightbox.add_argument("--resolution", type=float, default=_GP_DEFAULTS["resolution"])
    shape_lightbox.add_argument("--invert", action="store_true", default=_GP_DEFAULTS["invert"])
    shape_lightbox.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Seuil silhouette pour images sans alpha (0.0-1.0)",
    )

    opacity_coupon = subparsers.add_parser(
        "opacity-coupon",
        help="Genere le coupon benchmark opacite LithoLab V1",
    )
    opacity_coupon.add_argument(
        "output",
        nargs="?",
        default="LithoLab_Opacity_Coupon_V1.stl",
        help="Fichier STL de sortie",
    )
    opacity_coupon.add_argument("--width", type=float, default=100.0, help="Largeur en mm")
    opacity_coupon.add_argument("--height", type=float, default=30.0, help="Hauteur en mm")
    opacity_coupon.add_argument(
        "--resolution",
        type=float,
        default=0.5,
        help="Pas de grille en mm",
    )
    opacity_coupon.add_argument(
        "--thicknesses",
        type=float,
        nargs="+",
        default=None,
        help="Epaisseurs en mm, ex: --thicknesses 0.6 0.8 1.0 1.5 2.0 2.5 3.0",
    )
    opacity_coupon.add_argument(
        "--no-labels",
        action="store_true",
        help="Desactive les labels d'epaisseur en relief",
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
        include_back_panel=args.separate_back_panel,
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
        cap_thickness_mm=args.cap_thickness,
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


def _cmd_lightbox_image(args: argparse.Namespace) -> int:
    from lithoshape3d.core.geometry.image_lightbox_export import (
        DEFAULT_CAP_THICKNESS_MM,
        generate_lightbox_from_image,
    )

    image_path = args.image
    shape_mode = args.shape_mode.replace("-", "_")
    # Un `.svg` n'est JAMAIS rasterise avant l'appel, quel que soit le mode :
    # `generate_lightbox_from_image` utilise directement le contour
    # vectoriel exact (`core/geometry/svg_path_extractor.py` pour
    # "silhouette", `core/geometry/vector_envelope.py` en plus pour
    # "artwork_envelope") -- voir sa docstring.

    threshold_raw = args.threshold.strip()
    if threshold_raw.lower() == "auto":
        threshold_mode, threshold_value = "auto", None
    else:
        try:
            threshold_value = int(threshold_raw)
        except ValueError:
            print(f"ECHEC: --threshold invalide : '{threshold_raw}' (attendu 'auto' ou 0-255).")
            return 1
        if not (0 <= threshold_value <= 255):
            print(f"ECHEC: --threshold hors plage : {threshold_value} (attendu 0-255).")
            return 1
        threshold_mode = "manual"

    cap_transform = _parse_transform(args.cap_transform) if args.cap_transform else None

    cap_mode = args.cap_mode.replace("-", "_") if args.cap_mode else None

    kwargs = {
        "width_mm": args.width_mm,
        "depth_mm": args.depth_mm,
        "wall_thickness_mm": args.wall_thickness_mm,
        "back_thickness_mm": args.back_thickness_mm,
        "threshold_mode": threshold_mode,
        "threshold_value": threshold_value,
        "min_component_area_ratio": args.min_component_area_ratio,
        "cap_image_path": args.cap_image,
        "cap_image_transform": cap_transform,
        "resolution": args.resolution,
        "min_thickness_mm": args.min_thickness,
        "max_thickness_mm": args.max_thickness,
        "shape_mode": shape_mode,
        "cap_mode": cap_mode,
        "closing_radius_px": args.closing_radius_px,
        "max_closing_radius_px": args.max_closing_radius_px,
    }
    if args.cap_thickness_mm is not None:
        kwargs["cap_thickness_mm"] = args.cap_thickness_mm
    else:
        kwargs["cap_thickness_mm"] = DEFAULT_CAP_THICKNESS_MM

    try:
        result = generate_lightbox_from_image(image_path, args.output_dir, **kwargs)
    except ValueError as exc:
        print(f"ECHEC: {exc}")
        return 1

    for level, text in result.messages:
        prefix = "ECHEC" if level == "error" else "AVERTISSEMENT"
        print(f"{prefix}: {text}")

    if not result.ok:
        print("ECHEC: aucun fichier n'a pu etre genere.")
        return 1

    if result.threshold_used is not None:
        print(f"Seuil utilise : {result.threshold_used}")
    print("OK:", ", ".join(str(path) for path in result.written))
    return 0


def _shape_mask_from_path(path: str | Path, params: GeometryParameters, threshold: float):
    import numpy as np
    from PIL import Image

    from lithoshape3d.core.geometry.heightmap import grid_dimensions
    from lithoshape3d.core.geometry.shape import build_shape_mask_from_image_array
    from lithoshape3d.core.image.preprocessing import resize_array

    path = Path(path)
    image_path = path
    if path.suffix.lower() == ".svg":
        try:
            from lithoshape3d.ui.shape_svg_import import rasterize_svg_to_alpha_png
        except ImportError as exc:
            raise RuntimeError(
                "L'import SVG direct utilise QtSvg. Installez LithoShape3D avec "
                "`pip install -e \".[app]\"` ou rasterisez le SVG en PNG."
            ) from exc
        image_path = Path(rasterize_svg_to_alpha_png(str(path)))

    rows, cols = grid_dimensions(params)
    with Image.open(image_path) as image:
        has_alpha = "A" in image.getbands()
        if has_alpha:
            channel = np.asarray(image.split()[-1], dtype=np.float32) / 255.0
        else:
            channel = np.asarray(image.convert("L"), dtype=np.float32) / 255.0

    if not has_alpha and threshold != 0.5:
        resized = resize_array(channel, width_px=cols, height_px=rows)
        return resized >= threshold
    mask = build_shape_mask_from_image_array(channel, rows, cols)
    return mask


def _cmd_lightbox_shape(args: argparse.Namespace) -> int:
    from lithoshape3d.core.export.stl_export import export_stl
    from lithoshape3d.core.geometry.lightbox import (
        LightBoxFaceMode,
        LightBoxParameters,
        build_lightbox_from_shape_mask,
    )
    from lithoshape3d.core.validation.mesh_checks import validate_mesh

    face_mode = {
        "solid": LightBoxFaceMode.SOLID,
        "lithophane": LightBoxFaceMode.LITHOPHANE,
        "open": LightBoxFaceMode.OPEN,
    }[args.face]
    if face_mode is LightBoxFaceMode.LITHOPHANE and not args.lithophane_image:
        print("ECHEC: --lithophane-image est requis avec --face lithophane")
        return 1

    face_params = GeometryParameters(
        width_mm=args.width,
        height_mm=args.height,
        min_thickness_mm=args.min_thickness,
        max_thickness_mm=args.max_thickness,
        invert=args.invert,
        resolution=args.resolution,
    )
    box_params = LightBoxParameters(
        depth_mm=args.depth,
        wall_thickness_mm=args.wall_thickness,
        back_panel_thickness_mm=args.back_thickness,
        include_back_panel=args.separate_back_panel,
        face_mode=face_mode,
    )

    try:
        shape_mask = _shape_mask_from_path(args.shape, face_params, args.threshold)
        result = build_lightbox_from_shape_mask(
            shape_mask,
            face_params,
            box_params,
            image_path=args.lithophane_image,
        )
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        print(f"ECHEC: {exc}")
        return 1

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


def _cmd_opacity_coupon(args: argparse.Namespace) -> int:
    from lithoshape3d.core.export.stl_export import export_stl
    from lithoshape3d.core.geometry.opacity_coupon import (
        DEFAULT_LITHOLAB_OPACITY_THICKNESSES_MM,
        OpacityCouponParameters,
        build_opacity_coupon_mesh,
    )
    from lithoshape3d.core.validation.mesh_checks import validate_mesh

    thicknesses = (
        tuple(args.thicknesses)
        if args.thicknesses is not None
        else DEFAULT_LITHOLAB_OPACITY_THICKNESSES_MM
    )
    try:
        params = OpacityCouponParameters(
            width_mm=args.width,
            height_mm=args.height,
            resolution_mm=args.resolution,
            thicknesses_mm=thicknesses,
            labels=not args.no_labels,
        )
        mesh = build_opacity_coupon_mesh(params)
    except ValueError as exc:
        print(f"ECHEC: {exc}")
        return 1

    validation = validate_mesh(mesh)
    if not validation.is_valid:
        print("ECHEC validation du coupon :", ", ".join(validation.issues()))
        return 1

    output = Path(args.output)
    export_stl(mesh, output)
    print(
        f"OK: {output} "
        f"({len(mesh.vertices)} sommets, {len(mesh.faces)} faces, "
        f"volume={validation.volume_mm3:.1f} mm3)"
    )
    print("Epaisseurs:", ", ".join(f"{value:g} mm" for value in thicknesses))
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
    if args.command == "lightbox-image":
        return _cmd_lightbox_image(args)
    if args.command == "lightbox-shape":
        return _cmd_lightbox_shape(args)
    if args.command == "opacity-coupon":
        return _cmd_opacity_coupon(args)

    return _cmd_launch_app()


if __name__ == "__main__":
    raise SystemExit(main())
