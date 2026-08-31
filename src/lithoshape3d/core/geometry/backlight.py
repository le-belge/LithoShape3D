"""Backlight Insert (v0.4.1) : la lithophanie principale reste blanche, avec
une fine peau conservee en facade ; un insert colore independant, plat, vient
se loger derriere cette peau, dans une cavite creusee au dos du corps blanc --
sans jamais modifier la surface avant deja composee (meme garantie que
`ColorStrategy.MATERIAL_ONLY`, voir composition.py).

Reutilise l'ensemble du moteur existant plutot qu'un second moteur
geometrique parallele : `compose_scene_heightfield` pour la surface avant
partagee (inchangee), `build_mesh_from_heightfield` generalise a une face
arriere non plane pour creuser la cavite, la meme convention de masque
(espace image -> cadrage -> Y-up) que composition.py/materials.py.

Convention (identique a mesh_builder.py) : Z=0 = dos (cote source de
lumiere), Z=z_final(cellule) = face avant (cote spectateur). L'insert est
donc pose CONTRE le dos (Z=[0, insert_thickness_mm]) et la peau blanche
occupe le haut de la plage [z_final-skin, z_final] -- entre les deux, un
vide (la cavite) que l'insert vient (partiellement) combler.

Jonction cavite/insert (chanfrein, retour terrain post-0.4.1) : la marche
verticale d'origine entre "pas de cavite" et "cavite pleine profondeur"
(idem cote insert entre "pas d'insert" et "insert pleine epaisseur") est
difficile a imprimer/assembler proprement en FDM. Les deux profils sont
donc rampes lineairement sur `chamfer_width_mm` a partir du bord de leur
propre masque (cf. `_chamfer_ramp` et son usage dans
`compose_backlight_bodies`), sans nouveau parametre de maillage : seule la
carte de hauteur varie, le meme `build_mesh_from_heightfield` fait le
reste. Cette rampe reste bornee au domaine deja juge `feasible` par le
garde-fou existant -- elle ne fait que lisser une transition deja valide,
jamais deborder dans une zone jugee trop fine.

Limite connue (a documenter cote utilisateur) : le contour de la cavite
(bord de `feasible`) et celui de l'insert (bord de `insert_mask`, erode de
`xy_clearance_mm` par rapport a `feasible`) ne coincident PAS en XY -- deux
rampes independantes sur deux contours decales ne peuvent donc s'aligner
parfaitement pixel pour pixel ; l'alignement visuel du chanfrein
cavite/insert reste approximatif, a l'echelle de `xy_clearance_mm` +
`chamfer_width_mm`."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh
from scipy import ndimage

from lithoshape3d.core.geometry.composition import ZoneSource, compose_scene_heightfield
from lithoshape3d.core.geometry.mesh_builder import (
    DEFAULT_MASK_THRESHOLD,
    build_mesh_from_heightfield,
)
from lithoshape3d.core.image.preprocessing import resize_array
from lithoshape3d.core.image.transform import apply_image_transform
from lithoshape3d.core.scene.models import ColorStrategy, ImageTransform

_MIN_SKIN_RESIDUAL_MM = 0.05
"""Epaisseur de peau plancher, meme si `white_skin_thickness_mm` configure
depasse l'epaisseur locale de la lithophanie a un pixel donne (zone tres
fine/claire) -- degrade proprement vers "pas de cavite a ce pixel" (peau =
epaisseur totale) plutot que de produire une geometrie negative/degeneree."""

BREAKAWAY_SUPPORT_EXTRA_DEPTH_MM = 0.08
"""Surepaisseur (mm) du support sacrificiel par rapport a l'insert final,
sur la MEME empreinte (`insert_mask`) -- presse fermement contre le
plafond de la cavite (la peau blanche) pendant l'impression verticale,
au lieu de laisser un vide sous la peau qui la fait s'affaisser/se
perforer localement (cause dominante suspectee des deux echecs physiques
documentes, voir CURRENT_STATE.md). A retirer (cassable, imprime en
premier plan sur le meme materiau que l'insert ou un materiau facile a
detacher) avant de coller le veritable insert colore a sa place. Valeur
validee par un test physique reel (impression + inspection retro-eclairee
sans perforation, voir examples/physical_validation/). Le support est
plafonne a la profondeur REELLE de la cavite a chaque pixel (jamais plus)
pour ne jamais chevaucher le corps blanc solide, meme aux points ou la
marge disponible est plus etroite que cette surepaisseur."""


@dataclass(frozen=True)
class BacklightComposition:
    white_mesh: trimesh.Trimesh
    """Corps blanc principal -- surface avant identique bit-a-bit a ce que
    `compose_scene_mesh` aurait produit sans aucune zone Backlight Insert."""
    insert_meshes: dict[str, trimesh.Trimesh] = field(default_factory=dict)
    """{nom_materiau: mesh} -- fusionne par nom (meme convention que
    `partition_mesh_by_material`) si plusieurs zones Backlight Insert
    partagent un materiau."""
    breakaway_support_meshes: dict[str, trimesh.Trimesh] = field(default_factory=dict)
    """{nom_materiau: mesh} -- support sacrificiel par materiau, MEME
    empreinte XY que `insert_meshes[nom]` mais legerement plus epais
    (`BREAKAWAY_SUPPORT_EXTRA_DEPTH_MM`) pour presser contre le plafond de
    la cavite pendant l'impression verticale. A imprimer et retirer AVANT
    de coller l'insert final -- jamais les deux en meme temps dans la
    cavite (meme emplacement, cf. `three_mf_note` du protocole physique)."""
    warnings: list[str] = field(default_factory=list)
    """Zones trop etroites pour le jeu XY configure (aucun insert genere
    pour elles) -- jamais silencieux, cf. mission 0.4.1 section 7."""

    @property
    def has_inserts(self) -> bool:
        return bool(self.insert_meshes)


def _effective_zone_active(
    source: ZoneSource,
    rows: int,
    cols: int,
    mask_threshold: float,
    image_transform: ImageTransform | None,
    shape_active: np.ndarray,
) -> np.ndarray:
    """Reproduit EXACTEMENT la regle de `compose_scene_heightfield` pour
    transformer le masque source (espace image natif) en masque actif Y-up
    a la resolution canonique -- doit rester identique, sinon la cavite/l'
    insert ne correspondraient plus a la zone reellement active en
    composition (cf. le correctif d'alignement zone/cadrage de la 0.4.0)."""
    mask = source.mask
    if mask is None:
        mask = np.ones((rows, cols), dtype=np.float32)
    elif image_transform is None:
        if mask.shape != (rows, cols):
            mask = resize_array(mask, width_px=cols, height_px=rows)
    else:
        mask = apply_image_transform(
            mask.astype(np.float32), image_transform, width_px=cols, height_px=rows, fill_value=0.0
        )
    mask = np.flipud(mask)
    return (mask >= mask_threshold) & shape_active


def _erode_by_mm(mask: np.ndarray, clearance_mm: float, pixel_size_mm: float) -> np.ndarray:
    """Retrecit le masque de `clearance_mm` (mm reels, precision sub-pixel)
    sur son contour, via une carte de distance plutot qu'une erosion
    binaire par nombre entier de pixels : a une resolution typique
    (0.15-0.5 mm/px), un `binary_erosion` avec un nombre d'iterations
    arrondi confondrait 0.10/0.20/0.30mm (tous arrondis au meme pixel
    entier) -- inacceptable, la mission exige que ces 3 presets produisent
    des geometries reellement distinctes (cf. tests, "Test D")."""
    if clearance_mm <= 0 or pixel_size_mm <= 0 or not mask.any():
        return mask
    distance_mm = ndimage.distance_transform_edt(mask) * pixel_size_mm
    return distance_mm > clearance_mm


def _chamfer_ramp(mask: np.ndarray, chamfer_width_mm: float, pixel_size_mm: float, zone_name: str) -> tuple[np.ndarray, list[str]]:
    """Rampe 0->1 depuis le bord de `mask` (0 pile au bord, 1 a partir de
    `chamfer_width_mm` a l'interieur) -- meme technique de carte de distance
    que `_erode_by_mm`, mais utilisee comme facteur d'interpolation continu
    plutot que comme seuil binaire. `chamfer_width_mm<=0` degenere en rampe
    constante a 1.0 (comportement d'origine, marche abrupte). Signale (sans
    bloquer) quand une zone est trop etroite pour jamais atteindre un fond
    plat (aucun pixel a distance >= chamfer_width_mm de son propre bord) :
    la cavite/l'insert restent alors entierement en pente."""
    warnings_out: list[str] = []
    if chamfer_width_mm <= 0 or pixel_size_mm <= 0 or not mask.any():
        return np.ones_like(mask, dtype=np.float32), warnings_out
    distance_mm = ndimage.distance_transform_edt(mask) * pixel_size_mm
    ramp = np.clip(distance_mm / chamfer_width_mm, 0.0, 1.0).astype(np.float32)
    if not np.any(distance_mm[mask] >= chamfer_width_mm):
        warnings_out.append(
            f"Zone '{zone_name}' : trop etroite pour un chanfrein complet de "
            f"{chamfer_width_mm:.2f}mm -- la cavite/l'insert restent entierement en pente "
            "(pas de fond plat)."
        )
    return ramp, warnings_out


def compose_backlight_bodies(
    zone_sources: list[ZoneSource],
    mask_threshold: float = DEFAULT_MASK_THRESHOLD,
    image_transform: ImageTransform | None = None,
    shape_mask: np.ndarray | None = None,
) -> BacklightComposition:
    """Compose le corps blanc (avec cavites) et un insert independant par
    materiau, pour toutes les zones `ColorStrategy.BACKLIGHT_INSERT`
    visibles. Zero zone Backlight Insert -> `insert_meshes` vide et
    `white_mesh` identique a `compose_scene_mesh` (chemin sans effet)."""
    z_final, active_final, width_mm, height_mm = compose_scene_heightfield(
        zone_sources, mask_threshold, image_transform=image_transform, shape_mask=shape_mask
    )
    rows, cols = z_final.shape

    if shape_mask is None:
        shape_active = np.ones((rows, cols), dtype=bool)
    else:
        resized = (
            shape_mask
            if shape_mask.shape == (rows, cols)
            else resize_array(shape_mask.astype(np.float32), width_px=cols, height_px=rows) >= 0.5
        )
        shape_active = np.flipud(resized)

    pixel_size_mm = width_mm / cols
    back_z = np.zeros_like(z_final)
    insert_meshes: dict[str, trimesh.Trimesh] = {}
    breakaway_support_meshes: dict[str, trimesh.Trimesh] = {}
    warnings: list[str] = []

    for source in zone_sources:
        zone = source.zone
        if not zone.visible or zone.color_strategy is not ColorStrategy.BACKLIGHT_INSERT:
            continue

        zone_active = _effective_zone_active(source, rows, cols, mask_threshold, image_transform, shape_active)
        zone_active &= active_final
        if not zone_active.any():
            continue

        params = zone.backlight_insert
        skin = max(params.white_skin_thickness_mm, 0.0)
        insert_thickness = max(params.insert_thickness_mm, 0.0)

        # Garantie geometrique (hotfix v0.4.2) : l'insert est un pave UNIFORME
        # pose contre le dos (Z=[0, insert_thickness_mm]), independant de la
        # profondeur de cavite locale. La ou la lithophanie est localement
        # trop fine pour loger a la fois la peau demandee ET l'insert
        # (z_final < skin + insert_thickness), creuser quand meme la cavite
        # ferait deborder l'insert DANS le corps blanc solide -- collision
        # silencieuse entre les deux corps, visible en facade (trou/insert
        # traversant). On exclut ces points de la cavite ET de l'empreinte de
        # l'insert : la facade y reste pleine epaisseur (pas de coloration
        # backlight a ces points precis), jamais un trou. Toujours signale,
        # jamais silencieux (mission hotfix 0.4.2, section 9).
        required_total = skin + insert_thickness
        feasible = zone_active & (z_final >= required_total)
        infeasible = zone_active & ~feasible
        if infeasible.any():
            worst_shortfall = float((required_total - z_final[infeasible]).max())
            warnings.append(
                f"Zone '{zone.name}' : {int(infeasible.sum())} point(s) trop fins pour loger "
                f"a la fois la peau ({skin:.2f}mm) et l'insert ({insert_thickness:.2f}mm) -- "
                f"jusqu'a {worst_shortfall:.3f}mm d'epaisseur locale manquante. Aucune cavite "
                f"creusee a ces points (facade pleine epaisseur preservee, insert absent localement)."
            )
        if not feasible.any():
            continue

        insert_mask = _erode_by_mm(feasible, params.xy_clearance_mm, pixel_size_mm)
        if not insert_mask.any():
            warnings.append(
                f"Zone '{zone.name}' : trop etroite pour le jeu XY configure "
                f"({params.xy_clearance_mm:.2f} mm) -- aucun insert genere, cavite non creusee."
            )
            continue

        candidate_back = np.clip(z_final - skin, 0.0, None)
        candidate_back = np.clip(np.minimum(candidate_back, z_final - _MIN_SKIN_RESIDUAL_MM), 0.0, None)

        chamfer_width = max(params.chamfer_width_mm, 0.0)
        cavity_ramp, cavity_ramp_warnings = _chamfer_ramp(feasible, chamfer_width, pixel_size_mm, zone.name)
        warnings.extend(cavity_ramp_warnings)
        back_z[feasible] = (cavity_ramp * candidate_back)[feasible]

        insert_ramp, insert_ramp_warnings = _chamfer_ramp(insert_mask, chamfer_width, pixel_size_mm, zone.name)
        warnings.extend(insert_ramp_warnings)
        insert_front = insert_ramp * insert_thickness
        insert_mesh = build_mesh_from_heightfield(insert_front, insert_mask, width_mm, height_mm)

        # Support sacrificiel (aide a l'impression) : meme empreinte que
        # l'insert, presse contre le plafond de la cavite (`back_z[feasible]`,
        # deja calcule ci-dessus) pour la soutenir pendant l'impression
        # verticale -- jamais au-dela de la profondeur REELLEMENT creusee a
        # chaque pixel, meme si `insert_thickness + surepaisseur` depasserait
        # localement la marge disponible (evite tout chevauchement avec le
        # corps blanc solide).
        cavity_ceiling = cavity_ramp * candidate_back
        support_front = np.minimum(
            insert_front + BREAKAWAY_SUPPORT_EXTRA_DEPTH_MM, cavity_ceiling
        )
        support_mesh = build_mesh_from_heightfield(support_front, insert_mask, width_mm, height_mm)

        name = zone.material.name
        if name in insert_meshes:
            insert_meshes[name] = trimesh.util.concatenate([insert_meshes[name], insert_mesh])
        else:
            insert_meshes[name] = insert_mesh
        if name in breakaway_support_meshes:
            breakaway_support_meshes[name] = trimesh.util.concatenate(
                [breakaway_support_meshes[name], support_mesh]
            )
        else:
            breakaway_support_meshes[name] = support_mesh

    white_mesh = build_mesh_from_heightfield(z_final, active_final, width_mm, height_mm, back_z=back_z)
    return BacklightComposition(
        white_mesh=white_mesh,
        insert_meshes=insert_meshes,
        breakaway_support_meshes=breakaway_support_meshes,
        warnings=warnings,
    )
