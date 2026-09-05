"""Backlight Insert (v0.4.1) : la lithophanie principale reste blanche, avec
une fine peau conservee en facade ; un insert colore independant, plat, vient
se loger derriere cette peau, dans une cavite creusee au dos du corps blanc --
sans modifier la surface avant deja composee (meme garantie que
`ColorStrategy.MATERIAL_ONLY`, voir composition.py), SAUF exception locale et
deliberee : la ou la photo est trop fine sous une zone Backlight Insert pour
loger peau+insert, `z_final` y est releve au strict minimum requis (jamais
ailleurs) plutot que d'exclure ces points -- garantit un insert/texte toujours
entier, sans trou, au prix d'une tres legere sur-epaisseur locale confinee au
contour de la zone (voir le detail dans `compose_backlight_bodies`).

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

"Soft organic pocket" (retour terrain, validation physique reelle -- voir
`examples/physical_validation/`) : contrairement a l'ancien chanfrein
(deux rampes lineaires independantes sur la cavite ET sur l'insert,
suivant tout le relief local jusqu'a `white_skin_thickness_mm`), la
cavite reste desormais volontairement PEU PROFONDE et quasi constante
(`pocket_depth = insert_thickness_mm + pocket_extra_depth_mm`, pas
`z_final - skin`) : moins de matiere retiree, moins de fragilite en
facade. Seule une fine rampe de transition (`transition_width_mm`,
`smoothstep`) autour du contour de l'insert ramene progressivement cette
poche vers le dos plein (Z=0) -- l'insert lui-meme reste a EPAISSEUR
CONSTANTE (jamais rampe). Voir `_apply_soft_organic_pocket`,
`_build_insert_mesh` (nettoyage topologique par tentatives successives)
et `BacklightInsertParams.transition_width_mm`/`pocket_extra_depth_mm`.

Les points juges non `feasible` (trop fins pour loger peau + insert, cf.
plus bas) ne sont JAMAIS creuses, quelle que soit la rampe -- la facade y
reste pleine epaisseur, jamais un trou."""

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

# Le support sacrificiel (aide a l'impression) est desormais dimensionne
# directement par `BacklightInsertParams.pocket_extra_depth_mm` (meme
# grandeur que la surepaisseur de la poche elle-meme, cf.
# `compose_backlight_bodies`) plutot que par une constante de module fixe :
# la poche etant maintenant a profondeur quasi constante (pas suivant le
# relief local), le support peut se caler EXACTEMENT sur `pocket_depth`
# (meme empreinte que l'insert, plafonne a la profondeur reellement
# creusee a chaque pixel) sans avoir besoin d'une marge separee.


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
    (`BacklightInsertParams.pocket_extra_depth_mm`) pour presser contre le
    plafond de la cavite pendant l'impression verticale. A imprimer et
    retirer AVANT de coller l'insert final -- jamais les deux en meme
    temps dans la cavite (meme emplacement, cf. `three_mf_note` du
    protocole physique)."""
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


def _clean_insert_mask_for_mesh(mask: np.ndarray) -> np.ndarray:
    """Supprime les micro-contacts d'un pixel qui rendent certains masques
    reels non-manifold une fois extrudes en insert.

    Le jeu XY reste la source principale de retrait. Cette ouverture binaire
    est seulement une regularisation topologique apres retrait : elle evite
    les aretes partagees par plus de deux faces sans introduire de logique
    specifique au contenu de l'image ou au materiau teste."""
    if not mask.any():
        return mask
    return ndimage.binary_opening(mask)


def _build_insert_mesh(
    insert_mask: np.ndarray,
    insert_thickness: float,
    width_mm: float,
    height_mm: float,
) -> tuple[trimesh.Trimesh | None, np.ndarray, int]:
    """Construit un insert a EPAISSEUR CONSTANTE (jamais rampee, cf. note de
    module) et nettoie son masque seulement si necessaire (retente jusqu'a
    4 fois avec une ouverture binaire supplementaire si le premier maillage
    n'est pas watertight -- cf. `_clean_insert_mask_for_mesh`)."""
    if not insert_mask.any():
        return None, insert_mask, 0

    candidate = insert_mask
    removed_total = 0
    for _attempt in range(4):
        insert_front = np.full(candidate.shape, insert_thickness, dtype=np.float32)
        try:
            insert_mesh = build_mesh_from_heightfield(insert_front, candidate, width_mm, height_mm)
        except ValueError:
            return None, candidate, removed_total

        if insert_mesh.is_watertight:
            return insert_mesh, candidate, removed_total

        cleaned = _clean_insert_mask_for_mesh(candidate)
        removed_total += int(candidate.sum() - cleaned.sum())
        if not cleaned.any() or np.array_equal(cleaned, candidate):
            return None, cleaned, removed_total
        candidate = cleaned

    return None, candidate, removed_total


def _smoothstep(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, 0.0, 1.0)
    return clipped * clipped * (3.0 - (2.0 * clipped))


def _apply_soft_organic_pocket(
    back_z: np.ndarray,
    z_final: np.ndarray,
    feasible: np.ndarray,
    insert_mask: np.ndarray,
    *,
    skin: float,
    insert_thickness: float,
    transition_width_mm: float,
    pocket_extra_depth_mm: float,
    pixel_size_mm: float,
) -> np.ndarray:
    """Creuse une poche organique imprimable avec une rampe autour du
    contour (retour terrain, validation physique reelle -- voir note de
    module). Le centre du logement reste plat, a une profondeur quasi
    fixe (`pocket_depth`, PAS suivant le relief local) ; le contour revient
    progressivement vers le dos plein de la lithophanie. On evite ainsi la
    marche quasi verticale qui genere des micro-surfaces fragiles dans le
    slicer sur les masques organiques.

    Toujours plafonne par `z_final - skin` (via `feasible`, deja garanti
    par l'appelant) : la peau reelle ne descend jamais sous `skin`, meme
    au bord de la zone juste assez epaisse."""
    carved = np.zeros_like(feasible, dtype=bool)
    if not insert_mask.any():
        return carved

    max_back = np.clip(z_final - skin, 0.0, None)
    max_back = np.clip(np.minimum(max_back, z_final - _MIN_SKIN_RESIDUAL_MM), 0.0, None)
    pocket_depth = insert_thickness + max(0.0, pocket_extra_depth_mm)

    full_depth = np.minimum(max_back, pocket_depth)
    back_z[insert_mask] = np.maximum(back_z[insert_mask], full_depth[insert_mask])
    carved |= insert_mask

    if transition_width_mm <= 0.0 or pixel_size_mm <= 0.0:
        return carved

    outside_distance_mm = ndimage.distance_transform_edt(~insert_mask) * pixel_size_mm
    transition = feasible & ~insert_mask & (outside_distance_mm <= transition_width_mm)
    if not transition.any():
        return carved

    progress = 1.0 - (outside_distance_mm / transition_width_mm)
    transition_depth = pocket_depth * _smoothstep(progress)
    transition_depth = np.minimum(max_back, transition_depth)
    back_z[transition] = np.maximum(back_z[transition], transition_depth[transition])
    carved |= transition
    return carved


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

        # Garantie geometrique (hotfix v0.4.2, revise -- retour terrain texte
        # Backlight sur photo a luminosite variable) : l'insert est un pave
        # UNIFORME pose contre le dos (Z=[0, insert_thickness_mm]),
        # independant de la profondeur de cavite locale. La ou la lithophanie
        # est localement trop fine pour loger a la fois la peau demandee ET
        # l'insert (z_final < skin + insert_thickness), on ne peut PAS
        # creuser la cavite a pleine profondeur sans faire deborder l'insert
        # DANS le corps blanc solide (collision, trou visible en facade).
        #
        # Plutot que d'exclure ces points (ancien comportement : la facade y
        # restait pleine epaisseur, mais des lettres/formes d'insert
        # devenaient partiellement absentes des qu'elles chevauchaient une
        # zone claire/fine de la photo), on RELEVE localement `z_final` au
        # minimum requis, exactement sous l'empreinte de cette zone. Deroge
        # deliberement a l'invariant "la composition Backlight ne modifie
        # jamais la surface avant deja composee" (voir docstring de module),
        # mais uniquement ici, uniquement sous ce masque de zone precis,
        # jamais ailleurs sur la photo -- decision produit : un insert/texte
        # doit toujours etre entier et sans trou, quitte a une tres legere
        # sur-epaisseur locale invisible a l'oeil. Toujours signale, jamais
        # silencieux (mission hotfix 0.4.2, section 9).
        required_total = skin + insert_thickness
        shortfall = zone_active & (z_final < required_total)
        if shortfall.any():
            max_raise = float((required_total - z_final[shortfall]).max())
            z_final[shortfall] = required_total
            warnings.append(
                f"Zone '{zone.name}' : epaisseur locale relevee jusqu'a {max_raise:.3f}mm "
                f"sur {int(shortfall.sum())} point(s) pour garantir la peau ({skin:.2f}mm) "
                f"et l'insert ({insert_thickness:.2f}mm) sans trou -- limite au contour de "
                "cette zone, jamais au reste de la photo."
            )
        feasible = zone_active  # garanti par l'elevation ci-dessus
        if not feasible.any():
            continue

        insert_mask = _erode_by_mm(feasible, params.xy_clearance_mm, pixel_size_mm)
        if not insert_mask.any():
            warnings.append(
                f"Zone '{zone.name}' : trop etroite pour le jeu XY configure "
                f"({params.xy_clearance_mm:.2f} mm) -- aucun insert genere, cavite non creusee."
            )
            continue

        insert_mesh, cleaned_mask, removed_points = _build_insert_mesh(
            insert_mask, insert_thickness, width_mm, height_mm
        )
        if insert_mesh is None:
            warnings.append(
                f"Zone '{zone.name}' : insert impossible a mailler apres nettoyage "
                "topologique -- aucun insert genere."
            )
            continue
        if removed_points > 0:
            warnings.append(
                f"Zone '{zone.name}' : {removed_points} micro-point(s) retires de l'insert "
                "pour eviter une topologie non-manifold."
            )

        pocket_extra_depth = max(params.pocket_extra_depth_mm, 0.0)
        transition_width = max(params.transition_width_mm, 0.0)
        _apply_soft_organic_pocket(
            back_z,
            z_final,
            feasible,
            cleaned_mask,
            skin=skin,
            insert_thickness=insert_thickness,
            transition_width_mm=transition_width,
            pocket_extra_depth_mm=pocket_extra_depth,
            pixel_size_mm=pixel_size_mm,
        )

        # Support sacrificiel (aide a l'impression) : MEME empreinte que
        # l'insert nettoye, a la profondeur de poche exacte (`pocket_depth`,
        # cf. point 7 du protocole physique -- support_clearance=0.0) --
        # plafonne par `back_z` deja calcule ci-dessus (la profondeur
        # REELLEMENT creusee a chaque pixel), pour ne jamais chevaucher le
        # corps blanc solide meme si la marge locale est plus etroite.
        pocket_depth = insert_thickness + pocket_extra_depth
        support_front = np.minimum(np.full_like(back_z, pocket_depth), back_z)
        support_mesh = build_mesh_from_heightfield(support_front, cleaned_mask, width_mm, height_mm)

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
