"""Logique d'export partagee entre le CLI (`lightbox-letters`) et l'UI.

Factorise le pipeline "mot -> lettres -> caissons STL/DXF" pour eviter toute
duplication entre `cli._cmd_lightbox_letters` et le futur ecran GUI : les
deux se contentent d'appeler `generate_lightbox_letters` puis de formater le
resultat (print pour le CLI, widgets pour l'UI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from lithoshape3d.core.scene.models import GeometryParameters, ImageTransform

if TYPE_CHECKING:
    import trimesh


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


def narrowest_part_mm(letter) -> float:
    """Largeur (mm) de la composante la plus etroite d'une lettre extraite.

    C'est le vrai facteur limitant pour la paroi d'un caisson (ex. la barre
    du "i"), pas la bbox globale du glyphe qui peut inclure plusieurs
    composantes disjointes largement espacees. Factorise pour etre reutilise
    tel quel par `generate_lightbox_letters` (rejet reel a la generation) et
    par l'UI (avertissement indicatif avant de lancer la generation)."""
    return min(
        (max(p[0] for p in part.exterior) - min(p[0] for p in part.exterior))
        for part in letter.parts
    )


def compute_word_layout_and_grid(
    text: str,
    font_path: str,
    font_size_mm: float,
    *,
    resolution: float | None = None,
    min_thickness_mm: float | None = None,
    max_thickness_mm: float | None = None,
):
    """Calcule le `WordLayout` (contours par lettre) et la grille (rows,
    cols) associee, exactement comme `generate_lightbox_letters` -- factorise
    ici pour que l'UI puisse rasteriser le masque d'UNE lettre (ex. pour le
    cadrage visuel de son image) sans dupliquer cette glue."""
    from dataclasses import fields

    from lithoshape3d.core.geometry.heightmap import grid_dimensions
    from lithoshape3d.core.geometry.letter_glyph_extractor import extract_word_glyphs

    gp_defaults = {f.name: f.default for f in fields(GeometryParameters)}
    if resolution is None:
        resolution = gp_defaults["resolution"]
    if min_thickness_mm is None:
        min_thickness_mm = gp_defaults["min_thickness_mm"]
    if max_thickness_mm is None:
        max_thickness_mm = gp_defaults["max_thickness_mm"]

    layout = extract_word_glyphs(text, font_path, font_size_mm=font_size_mm)
    face_params = GeometryParameters(
        width_mm=layout.width_mm,
        height_mm=layout.height_mm,
        min_thickness_mm=min_thickness_mm,
        max_thickness_mm=max_thickness_mm,
        resolution=resolution,
    )
    rows, cols = grid_dimensions(face_params)
    return layout, face_params, rows, cols


def letter_wall_thickness_ok(letter, wall_thickness_mm: float) -> bool:
    """True si la lettre est assez epaisse pour la paroi demandee -- meme
    seuil (2x l'epaisseur de paroi) que le garde-fou de generation reelle."""
    return narrowest_part_mm(letter) >= wall_thickness_mm * 2


def rasterize_letter_shape_mask_for_index(
    text: str,
    font_path: str,
    font_size_mm: float,
    index: int,
    *,
    resolution: float | None = None,
):
    """Rasterise le masque de la lettre `index` de `text` dans le meme
    referentiel (canvas du mot entier) que `generate_lightbox_letters` --
    utilise par l'UI pour le cadrage visuel image/lettre (meme masque que
    celui qui sera reellement utilise a la generation, aucune duplication du
    calcul de layout)."""
    from lithoshape3d.core.geometry.letter_glyph_extractor import rasterize_letter_mask

    layout, _face_params, rows, cols = compute_word_layout_and_grid(
        text, font_path, font_size_mm, resolution=resolution
    )
    letter = next((letter for letter in layout.letters if letter.index == index), None)
    if letter is None:
        raise ValueError(f"Aucune lettre a l'index {index} pour le texte '{text}'.")
    return rasterize_letter_mask(letter, layout.width_mm, layout.height_mm, rows, cols)


# Refactor (LightBox depuis image) : le moteur d'extrusion vectorielle
# "parois lisses + epaulement" (corps/fond/footprint de capot) a ete
# generalise et deplace vers `vector_lightbox.py` -- il ne dependait deja
# d'AUCUNE particularite des lettres (uniquement de `letter.to_shapely()`
# en entree), donc reutilisable tel quel pour une silhouette extraite
# d'image. Les fonctions "lettre" ci-dessous restent EXACTEMENT les memes
# noms/signatures/comportements (verifie par les tests existants, non
# modifies) : de fines enveloppes qui appellent le moteur partage avec
# `letter.to_shapely()`.
from lithoshape3d.core.geometry.vector_lightbox import (
    ASSEMBLY_CLEARANCE_MM,
    SHOULDER_DEPTH_MM,
    SHOULDER_WIDTH_MM,
    build_vector_lightbox_back_panel_mesh,
    build_vector_lightbox_body_mesh,
    vector_lightbox_cap_footprint,
)


def build_lightbox_letter_body_mesh(
    letter,
    depth_mm: float,
    wall_thickness_mm: float,
    *,
    shoulder_depth_mm: float = SHOULDER_DEPTH_MM,
    shoulder_width_mm: float = SHOULDER_WIDTH_MM,
) -> tuple[trimesh.Trimesh, list[str]]:
    """Construit le corps (parois seules, sans fond -- meme convention que
    `build_lightbox_body_mesh` V1) d'un caisson de lettre par EXTRUSION
    DIRECTE du contour vectoriel exact (`letter.to_shapely()`), au lieu de
    repasser par le pipeline heightfield/raster voxelise utilise par
    `build_lightbox_body_mesh`. Parois lisses suivant le vrai contour de la
    lettre. Inclut un epaulement en haut du corps (cavite retrecie sur
    `shoulder_depth_mm`) sur lequel le capot vient s'encastrer.

    Fonction ADDITIVE et INDEPENDANTE de `build_lightbox_body_mesh`
    (`lightbox.py`) : ne modifie en rien le comportement de
    `lightbox-text`/V1. Enveloppe fine autour du moteur partage
    `vector_lightbox.build_vector_lightbox_body_mesh`."""
    outer = letter.to_shapely()
    return build_vector_lightbox_body_mesh(
        outer,
        depth_mm,
        wall_thickness_mm,
        shoulder_depth_mm=shoulder_depth_mm,
        shoulder_width_mm=shoulder_width_mm,
    )


def build_lightbox_letter_back_panel_mesh(letter, back_thickness_mm: float):
    """Fond du caisson de lettre, extrude directement depuis le contour
    vectoriel exact de la lettre (comme le corps) : lisse, plein, sans
    cavite -- meme piece separee (a coller) que le fond V1
    (`build_lightbox_back_panel_mesh`), mais sans repasser par le
    raster/heightfield. Enveloppe fine autour du moteur partage
    `vector_lightbox.build_vector_lightbox_back_panel_mesh`."""
    outer = letter.to_shapely()
    return build_vector_lightbox_back_panel_mesh(outer, back_thickness_mm)


def letter_cap_footprint(
    letter,
    wall_thickness_mm: float,
    *,
    shoulder_width_mm: float = SHOULDER_WIDTH_MM,
    assembly_clearance_mm: float = ASSEMBLY_CLEARANCE_MM,
):
    """Contour (Shapely) du capot, retreci pour s'emboiter dans l'epaulement
    du corps : en retrait de `wall_thickness_mm + shoulder_width_mm` par
    rapport au contour exterieur de la lettre (meme retrait que la cavite
    d'epaulement), plus `assembly_clearance_mm` de jeu d'assemblage FDM par
    cote pour que le capot rentre sans forcer a l'impression. Enveloppe fine
    autour du moteur partage `vector_lightbox.vector_lightbox_cap_footprint`."""
    outer = letter.to_shapely()
    return vector_lightbox_cap_footprint(
        outer,
        wall_thickness_mm,
        shoulder_width_mm=shoulder_width_mm,
        assembly_clearance_mm=assembly_clearance_mm,
    )


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
    """Genere un caisson lumineux par lettre (corps + capot + fond + DXF).

    Reproduit exactement le comportement de `lithoshape3d lightbox-letters`
    (voir `cli.py`) mais retourne un `LightboxLettersResult` structure au
    lieu d'imprimer sur stdout et de renvoyer un code de sortie -- utilise
    a la fois par le CLI et par l'ecran GUI correspondant.
    """
    from lithoshape3d.core.export.stl_export import export_stl
    from lithoshape3d.core.geometry.lightbox import (
        LightBoxFaceMode,
        LightBoxParameters,
        build_lightbox_lithophane_face_mesh,
        build_lightbox_solid_face_mesh,
    )
    from lithoshape3d.core.geometry.letter_glyph_extractor import rasterize_polygon_mask
    from lithoshape3d.core.geometry.support import _from_manifold, _to_manifold
    from lithoshape3d.core.validation.mesh_checks import validate_mesh
    import dataclasses
    import trimesh

    images_by_index = images_by_index or {}
    transforms_by_index = transforms_by_index or {}

    result = LightboxLettersResult()

    layout, face_params, rows, cols = compute_word_layout_and_grid(
        text,
        font_path,
        font_size_mm,
        resolution=resolution,
        min_thickness_mm=min_thickness_mm,
        max_thickness_mm=max_thickness_mm,
    )
    for warning in layout.warnings:
        result.messages.append(("warning", warning))

    box_params_solid = LightBoxParameters(
        depth_mm=depth_mm,
        wall_thickness_mm=wall_thickness_mm,
        back_panel_thickness_mm=back_thickness_mm,
        face_mode=LightBoxFaceMode.SOLID,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = "".join(c if c.isalnum() else "_" for c in text).lower() or "mot"

    for letter in layout.letters:
        for w in letter.warnings:
            result.messages.append(
                ("warning", f"lettre '{letter.character}' (#{letter.index}): {w}")
            )

        if not letter_wall_thickness_ok(letter, wall_thickness_mm):
            result.messages.append(
                (
                    "warning",
                    f"lettre '{letter.character}' (#{letter.index}) trop fine "
                    f"({narrowest_part_mm(letter):.2f} mm) pour l'epaisseur de paroi demandee "
                    f"({wall_thickness_mm} mm) -- caisson ignore pour cette lettre.",
                )
            )
            continue

        image_path = images_by_index.get(letter.index)
        image_transform = transforms_by_index.get(letter.index)

        prefix = f"{slug}_lettre_{letter.index}_{letter.character.lower()}"

        # Corps : extrusion directe du contour vectoriel exact de la lettre
        # (parois lisses + epaulement de retention du capot), au lieu du
        # pipeline heightfield/raster voxelise de `build_lightbox_from_shape_mask`
        # (V1, toujours utilise tel quel par `lightbox-text`).
        try:
            body_mesh, body_warnings = build_lightbox_letter_body_mesh(
                letter, depth_mm, wall_thickness_mm
            )
        except ValueError as exc:
            result.messages.append(
                ("error", f"lettre '{letter.character}' (#{letter.index}) : {exc}")
            )
            continue
        for warning in body_warnings:
            result.messages.append(("warning", f"lettre '{letter.character}': {warning}"))

        body_validation = validate_mesh(body_mesh)
        if not body_validation.is_valid:
            result.messages.append(
                (
                    "error",
                    f"validation corps lettre '{letter.character}' : "
                    f"{', '.join(body_validation.issues())}",
                )
            )
            continue

        # Fond fusionne au corps par union booleene (meme moteur manifold3d
        # que le reste du pipeline) : le corps seul n'a pas de fond (cavite
        # ouverte par le bas, voir vector_lightbox.py), donc les exporter
        # separement produisait deux pieces a assembler/coller -- retour
        # utilisateur : "le fond et la box ne doivent faire qu'une piece".
        # Une seule union ici (au lieu d'une extrusion "corps+fond" dediee)
        # reutilise directement les deux extrusions vectorielles existantes
        # sans dupliquer le moteur d'extrusion.
        try:
            back_panel_mesh = build_lightbox_letter_back_panel_mesh(letter, back_thickness_mm)
        except ValueError as exc:
            result.messages.append(
                ("error", f"fond lettre '{letter.character}' (#{letter.index}) : {exc}")
            )
            back_panel_mesh = None

        combined_body_mesh = body_mesh
        if back_panel_mesh is not None:
            combined_body_mesh = _from_manifold(_to_manifold(body_mesh) + _to_manifold(back_panel_mesh))

        combined_validation = validate_mesh(combined_body_mesh)
        if not combined_validation.is_valid:
            result.messages.append(
                (
                    "error",
                    f"validation corps+fond lettre '{letter.character}' : "
                    f"{', '.join(combined_validation.issues())}",
                )
            )
            continue
        body_path = output_dir / f"{prefix}_corps.stl"
        export_stl(combined_body_mesh, body_path)
        result.written.append(body_path)

        # Capot : retreci pour s'emboiter dans l'epaulement du corps (voir
        # `letter_cap_footprint`), toujours genere via le pipeline heightfield
        # existant (`compose_scene_mesh`) puisque c'est un relief lithophanie,
        # pas un simple contour vectoriel -- non concerne par le changement
        # d'extrusion du corps.
        cap_polygon = letter_cap_footprint(letter, wall_thickness_mm)
        cap_shape_mask = rasterize_polygon_mask(
            cap_polygon, layout.width_mm, layout.height_mm, rows, cols
        )
        cap_depth_mm = depth_mm - SHOULDER_DEPTH_MM

        face_mesh = None
        if image_path:
            face_mesh = build_lightbox_lithophane_face_mesh(
                image_path, cap_shape_mask, face_params, cap_depth_mm, image_transform
            )
        elif cap_shape_mask.any():
            solid_box_params = dataclasses.replace(box_params_solid, depth_mm=cap_depth_mm)
            face_mesh = build_lightbox_solid_face_mesh(
                cap_shape_mask, face_params, solid_box_params
            )
        else:
            result.messages.append(
                (
                    "warning",
                    f"lettre '{letter.character}' (#{letter.index}): capot ignore "
                    "(footprint d'epaulement vide a cette resolution).",
                )
            )

        if face_mesh is not None:
            face_validation = validate_mesh(face_mesh)
            if face_validation.is_valid:
                face_path = output_dir / f"{prefix}_capot.stl"
                export_stl(face_mesh, face_path)
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
