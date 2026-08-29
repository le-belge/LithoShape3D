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

Deuxieme mode confirme par l'utilisateur (retour "Thunderdome" -- dessin au
trait noir/blanc avec elements physiquement disjoints, ex. poings qui ne
touchent pas un cercle) : `shape_mode="artwork_envelope"` -- corps/fond
extrudes depuis l'ENVELOPPE unifiee (`artwork_shape_extractor.py`, un seul
caisson meme si le dessin source a des zones disjointes), et
`cap_mode="flat_two_color"` -- capot en DEUX pieces plates complementaires
(encre/fond, pour une impression 2 couleurs) decoupees depuis le masque
d'encre FIN (pas l'enveloppe fermee, qui perdrait le detail du trait).

Factorise pour eviter toute duplication entre le CLI (`lightbox-image`) et
l'ecran GUI (`ui/lightbox_image_dialog.py`) : les deux se contentent
d'appeler `generate_lightbox_from_image` puis de formater le resultat --
meme principe que `lightbox_letters_export.py`."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lithoshape3d.core.scene.models import GeometryParameters, ImageTransform

SHAPE_MODE_SILHOUETTE = "silhouette"
SHAPE_MODE_ARTWORK_ENVELOPE = "artwork_envelope"
_SHAPE_MODES = (SHAPE_MODE_SILHOUETTE, SHAPE_MODE_ARTWORK_ENVELOPE)

CAP_MODE_FLAT = "flat"
CAP_MODE_LITHOPHANE = "lithophane"
CAP_MODE_FLAT_TWO_COLOR = "flat_two_color"
_CAP_MODES = (CAP_MODE_FLAT, CAP_MODE_LITHOPHANE, CAP_MODE_FLAT_TWO_COLOR)

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
    min_component_area_ratio: float | None = None,
    cap_thickness_mm: float = DEFAULT_CAP_THICKNESS_MM,
    cap_image_path: str | Path | None = None,
    cap_image_transform: ImageTransform | None = None,
    resolution: float | None = None,
    min_thickness_mm: float | None = None,
    max_thickness_mm: float | None = None,
    shape_mode: str = SHAPE_MODE_SILHOUETTE,
    cap_mode: str | None = None,
    closing_radius_px: int | None = None,
    max_closing_radius_px: int | None = None,
    force_convex_envelope: bool = False,
) -> LightboxImageResult:
    """Genere un caisson lumineux vectoriel depuis une image (corps + fond +
    capot + DXF).

    `image_path` peut etre soit un raster PNG/JPG, soit -- en `shape_mode=
    "silhouette"` uniquement -- un fichier `.svg` source, auquel cas le
    contour vectoriel EXACT (courbes de Bezier tessellees adaptativement,
    voir `svg_path_extractor.py`) est utilise directement, SANS rasterisation
    prealable : la rasterisation via QtSvg (`ui/shape_svg_import.py`)
    perdait les vraies courbes du SVG des la premiere etape, quelle que soit
    la qualite de la simplification/lissage appliquee ensuite sur le contour
    pixel resultant. `svg_path_extractor.py` est pur `core/` (lxml +
    svgpathtools, aucun Qt), donc ce branchement ne viole pas la contrainte
    architecturale `core/` -> jamais Qt.

    En `shape_mode="artwork_envelope"`, un `.svg` doit TOUJOURS etre
    rasterise par l'appelant avant l'appel (comme avant) : ce mode repose
    sur des operations morphologiques raster (fermeture, fill-from-border,
    voir `artwork_shape_extractor.py`) qui n'ont pas d'equivalent vectoriel
    direct dans ce pipeline -- limitation documentee, pas un branchement
    fragile force.

    `shape_mode` :
      - `"silhouette"` (par defaut, inchange pour les rasters) : contour =
        silhouette extraite par `image_shape_extractor.extract_shape_from_image`
        (Cas A alpha ou Cas B seuillage photo) pour un raster, ou par
        `svg_path_extractor.extract_polygon_from_svg` pour un `.svg`.
      - `"artwork_envelope"` : contour = enveloppe unifiee d'un dessin au
        trait (`artwork_shape_extractor.extract_artwork_from_image`) -- un
        seul caisson meme si le dessin source a des elements disjoints
        (ex. poings qui ne touchent pas un cercle). Source toujours raster
        (voir note ci-dessus).

    `cap_mode` (`None` = comportement historique : lithophanie si
    `cap_image_path` fourni, sinon plat) :
      - `"flat"` : capot plat/lisse (extrusion directe du footprint).
      - `"lithophane"` : capot heightfield depuis `cap_image_path` (meme
        moteur que `lightbox-letters`).
      - `"flat_two_color"` : DEUX capots plats complementaires (encre/fond)
        decoupes depuis le masque d'encre fin -- necessite
        `shape_mode="artwork_envelope"` (le masque d'encre n'existe que
        dans ce mode)."""
    from dataclasses import fields

    import trimesh
    from shapely.geometry import GeometryCollection
    from shapely.ops import unary_union

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
    if shape_mode not in _SHAPE_MODES:
        raise ValueError(f"shape_mode invalide : {shape_mode!r} (attendu {_SHAPE_MODES}).")

    effective_cap_mode = cap_mode if cap_mode is not None else (
        CAP_MODE_LITHOPHANE if cap_image_path else CAP_MODE_FLAT
    )
    if effective_cap_mode not in _CAP_MODES:
        raise ValueError(f"cap_mode invalide : {effective_cap_mode!r} (attendu {_CAP_MODES}).")
    if effective_cap_mode == CAP_MODE_FLAT_TWO_COLOR:
        if shape_mode != SHAPE_MODE_ARTWORK_ENVELOPE:
            raise ValueError(
                "cap_mode='flat_two_color' necessite shape_mode='artwork_envelope' (le masque "
                "d'encre necessaire au capot 2 couleurs n'existe que dans ce mode)."
            )
        if cap_image_path:
            raise ValueError(
                "cap_mode='flat_two_color' ne prend pas d'image de capot separee (cap_image_path) "
                "-- les deux couleurs sont decoupees depuis l'encre du dessin source lui-meme."
            )

    # Profondeur d'epaulement (retrait du haut du corps ou le capot vient
    # s'encastrer) : pour un capot PLAT (flat/flat_two_color), elle doit
    # correspondre EXACTEMENT a `cap_thickness_mm` -- sinon un capot plus
    # epais que l'epaulement par defaut (SHOULDER_DEPTH_MM=1.75mm) depasse
    # du corps au lieu d'affleurer, et un capot plus fin flotte dans une
    # cavite trop profonde sans y etre maintenu. Retour utilisateur : "un
    # rebord interieur au depart du fond de [depth-cap_thickness] pour que
    # le capot repose dessus". Pour un capot LITHOPHANE (relief, pas une
    # epaisseur unique), on garde l'epaulement par defaut du moteur
    # (`SHOULDER_DEPTH_MM`) -- non concerne par ce retour.
    effective_shoulder_depth_mm = (
        cap_thickness_mm
        if effective_cap_mode in (CAP_MODE_FLAT, CAP_MODE_FLAT_TWO_COLOR)
        else SHOULDER_DEPTH_MM
    )
    if effective_shoulder_depth_mm >= depth_mm:
        raise ValueError(
            f"cap_thickness_mm ({cap_thickness_mm:.2f}mm) doit rester inferieur a depth_mm "
            f"({depth_mm:.2f}mm) : le capot ne peut pas etre plus epais que le caisson."
        )

    ink_polygon = None
    if shape_mode == SHAPE_MODE_SILHOUETTE:
        if str(image_path).lower().endswith(".svg"):
            # Chemin vectoriel direct (pas de rasterisation) : voir
            # docstring de fonction et `svg_path_extractor.py`.
            from lithoshape3d.core.geometry.svg_path_extractor import (
                SvgPathExtractionError,
                extract_svg_polygon_result,
            )

            try:
                svg_result = extract_svg_polygon_result(image_path, width_mm)
            except (SvgPathExtractionError, ValueError, OSError) as exc:
                result.messages.append(("error", f"extraction vectorielle SVG : {exc}"))
                return result
            for warning in svg_result.warnings:
                result.messages.append(("warning", warning))
            outer = svg_result.polygon
            shape_width_mm, shape_height_mm = svg_result.width_mm, svg_result.height_mm
        else:
            try:
                silhouette_kwargs = {}
                if min_component_area_ratio is not None:
                    silhouette_kwargs["min_component_area_ratio"] = min_component_area_ratio
                shape = extract_shape_from_image(
                    image_path,
                    width_mm,
                    threshold_mode=threshold_mode,
                    threshold_value=threshold_value,
                    **silhouette_kwargs,
                )
            except (ImageShapeExtractionError, ValueError, OSError) as exc:
                result.messages.append(("error", f"extraction de la silhouette : {exc}"))
                return result
            result.threshold_used = shape.threshold_used
            for warning in shape.warnings:
                result.messages.append(("warning", warning))
            outer = shape.polygon
            shape_width_mm, shape_height_mm = shape.width_mm, shape.height_mm
    else:
        from lithoshape3d.core.geometry.artwork_shape_extractor import (
            ArtworkExtractionError,
            extract_artwork_from_image,
        )

        try:
            artwork_kwargs = {}
            if min_component_area_ratio is not None:
                artwork_kwargs["min_component_area_ratio"] = min_component_area_ratio
            artwork = extract_artwork_from_image(
                image_path,
                width_mm,
                threshold_mode=threshold_mode,
                threshold_value=threshold_value,
                closing_radius_px=closing_radius_px,
                max_closing_radius_px=max_closing_radius_px,
                force_convex_envelope=force_convex_envelope,
                **artwork_kwargs,
            )
        except (ArtworkExtractionError, ValueError, OSError) as exc:
            result.messages.append(("error", f"extraction de l'enveloppe artwork : {exc}"))
            return result
        result.threshold_used = artwork.threshold_used
        for warning in artwork.warnings:
            result.messages.append(("warning", warning))
        outer = artwork.envelope_polygon
        ink_polygon = artwork.ink_polygon
        shape_width_mm, shape_height_mm = artwork.width_mm, artwork.height_mm

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = _slug_from_path(image_path)

    # Corps AVEC fond integre : extrusion directe du contour vectoriel exact
    # de la silhouette (parois lisses + epaulement de retention du capot),
    # cavite basse partant de `back_thickness_mm` au lieu de Z=0 -- le fond
    # fait donc partie de la MEME extrusion/soustraction, pas d'union
    # booleenne post-hoc entre deux meshes separes (fragile sur des contours
    # complexes/multi-composantes -- triangles degeneres constates sur un
    # logo tres detaille). Meme moteur que LightBox Letters, voir
    # `vector_lightbox.py`.
    try:
        body_mesh, body_warnings = build_vector_lightbox_body_mesh(
            outer,
            depth_mm,
            wall_thickness_mm,
            back_thickness_mm=back_thickness_mm,
            shoulder_depth_mm=effective_shoulder_depth_mm,
        )
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

    # Capot : plat/lisse par defaut, lithophanie si une image est fournie,
    # ou deux pieces plates complementaires (encre/fond) en mode 2 couleurs.
    cap_polygon = vector_lightbox_cap_footprint(outer, wall_thickness_mm)
    cap_depth_mm = depth_mm - effective_shoulder_depth_mm
    if cap_polygon.is_empty or cap_polygon.area <= 0:
        result.messages.append(
            (
                "warning",
                "capot ignore (footprint d'epaulement vide -- silhouette trop fine pour ces "
                "parametres d'epaisseur de paroi).",
            )
        )
    elif effective_cap_mode == CAP_MODE_LITHOPHANE:
        gp_defaults = {f.name: f.default for f in fields(GeometryParameters)}
        face_params = GeometryParameters(
            width_mm=shape_width_mm,
            height_mm=shape_height_mm,
            min_thickness_mm=(
                min_thickness_mm if min_thickness_mm is not None else gp_defaults["min_thickness_mm"]
            ),
            max_thickness_mm=(
                max_thickness_mm if max_thickness_mm is not None else gp_defaults["max_thickness_mm"]
            ),
            resolution=resolution if resolution is not None else gp_defaults["resolution"],
        )
        rows, cols = grid_dimensions(face_params)
        cap_shape_mask = rasterize_polygon_mask(
            cap_polygon, shape_width_mm, shape_height_mm, rows, cols
        )
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
    elif effective_cap_mode == CAP_MODE_FLAT_TWO_COLOR:
        if ink_polygon is None or ink_polygon.is_empty or ink_polygon.area <= 0:
            result.messages.append(
                ("warning", "capot 2 couleurs ignore (aucune encre detectee dans le dessin).")
            )
        else:
            # Decoupe exacte du footprint du capot en deux pieces complementaires
            # (encre / fond) via booleenne shapely -- garantit par construction
            # une union == footprint et une intersection vide entre les deux.
            color_a_polygon = ink_polygon.intersection(cap_polygon)
            color_b_polygon = cap_polygon.difference(ink_polygon)
            # Aire de reference pour filtrer les esquilles degenerees issues
            # de la booleenne (contours d'encre tres detailles/nombreux --
            # cf. Thunderdome) : sans ce filtrage, `extrude_polygon` peut
            # produire des triangles quasi-nuls et un mesh non watertight.
            min_piece_area_mm2 = max(cap_polygon.area * 0.0002, 0.01)
            any_piece_written = False
            for label, piece_polygon in (("a", color_a_polygon), ("b", color_b_polygon)):
                if isinstance(piece_polygon, GeometryCollection):
                    polys = [g for g in piece_polygon.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
                    piece_polygon = unary_union(polys) if polys else None
                if piece_polygon is not None and not piece_polygon.is_empty:
                    piece_polygon = piece_polygon.buffer(0)
                if piece_polygon is not None and piece_polygon.geom_type == "MultiPolygon":
                    kept = [g for g in piece_polygon.geoms if g.area >= min_piece_area_mm2]
                    piece_polygon = unary_union(kept) if kept else None
                if piece_polygon is None or piece_polygon.is_empty or piece_polygon.area <= 0:
                    result.messages.append(
                        ("warning", f"capot couleur {label} ignore (aire nulle a cette resolution).")
                    )
                    continue
                piece_mesh = build_vector_lightbox_back_panel_mesh(piece_polygon, cap_thickness_mm)
                piece_mesh = piece_mesh.copy()
                piece_mesh.apply_translation((0.0, 0.0, cap_depth_mm))
                piece_validation = validate_mesh(piece_mesh)
                if piece_validation.is_valid:
                    piece_path = output_dir / f"{slug}_capot_couleur_{label}.stl"
                    export_stl(piece_mesh, piece_path)
                    result.written.append(piece_path)
                    any_piece_written = True
                else:
                    result.messages.append(
                        (
                            "error",
                            f"validation capot couleur {label} : "
                            f"{', '.join(piece_validation.issues())}",
                        )
                    )
            if not any_piece_written:
                result.messages.append(
                    ("error", "capot 2 couleurs : aucune des deux pieces n'a pu etre generee.")
                )
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
