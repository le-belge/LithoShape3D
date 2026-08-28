"""Extraction "artwork au trait" (dessin noir/blanc, ex. logo dessine a la
main, PAS de canal alpha exploitable) pour le mode "LightBox depuis image"
enveloppe unifiee + capot 2 couleurs.

Nouveau module distinct de `image_shape_extractor.py` (Cas A/B "silhouette")
car le besoin est different dans sa nature, pas seulement un troisieme cas de
seuillage : `image_shape_extractor.py` produit UN SEUL masque/polygone
consomme tel quel comme contour du caisson. Ici on a besoin de DEUX masques
distincts et complementaires a partir de la MEME image --

  - `ink_mask` : l'encre elle-meme (trait fin, fidele au dessin original),
    utilisee pour le CAPOT 2 couleurs (chaque zone -- encre/fond -- devient
    une piece plate imprimee dans un filament different) ;
  - `envelope_mask` : le contour EXTERIEUR global du dessin, calcule par
    "fill-from-border" (voir `_fill_enclosed_regions`) puis, si necessaire,
    une fermeture morphologique pour souder des elements du dessin
    physiquement disjoints (ex. poings qui ne touchent pas le cercle) en une
    seule composante connexe -- exigence confirmee par l'utilisateur : UN
    SEUL caisson imprimable, meme si le dessin source a des zones
    disjointes.

Reutilise au maximum le Cas B existant plutot que de dupliquer :
`threshold_and_clean_mask` (seuillage Otsu/manuel + nettoyage de bruit),
`mask_to_polygon` (masque -> polygone(s) Shapely via
`contour_classification.classify_contours_by_containment`, PAS reimplemente
ici) depuis `image_shape_extractor.py`, et `count_connected_components`
depuis `shape.py` (deja utilise pour un usage similaire -- compte de
composantes d'une silhouette)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage
from shapely.geometry import MultiPolygon, Polygon

from lithoshape3d.core.geometry.image_shape_extractor import (
    ImageShapeExtractionError,
    mask_to_polygon,
    threshold_and_clean_mask,
)
from lithoshape3d.core.geometry.shape import count_connected_components

_DEFAULT_INK_MIN_COMPONENT_AREA_RATIO = 0.0002
"""0.02% de l'aire totale -- beaucoup plus petit que le defaut Cas B
(0.1%, `image_shape_extractor._DEFAULT_MIN_COMPONENT_AREA_RATIO`) : le but
ici n'est PAS de nettoyer un sujet isole sur fond uniforme mais de garder le
DETAIL fin d'un dessin au trait (petits elements reels du dessin -- pointes
de corne, doigts fins) tout en filtrant les vrais artefacts de compression/
anti-aliasing (specks de quelques pixels)."""

_INK_SIMPLIFY_TOLERANCE_RATIO = 0.003
"""Tolerance de simplification du contour d'encre (`mask_to_polygon`) : plus
fine que le Cas A (logo alpha propre, 0.004) et le Cas B photo (0.008) --
le capot 2 couleurs doit rester fidele au trait, c'est tout l'interet de ce
mode par rapport a une silhouette globale."""

_ENVELOPE_SIMPLIFY_TOLERANCE_RATIO = 0.006
"""Tolerance de simplification de l'enveloppe (corps/fond du caisson) --
volontairement plus genereuse que l'encre : l'enveloppe est deja une forme
"lissee" par le fill-from-border et l'eventuelle fermeture morphologique,
inutile de conserver son detail pixel-a-pixel pour l'extrusion du corps."""

_DEFAULT_MAX_CLOSING_RADIUS_RATIO = 0.06
"""Plafond par defaut de recherche de rayon de fermeture, en fraction de la
plus grande dimension du masque de travail -- ex. ~48px sur un masque
800px. Au-dela, une fermeture aussi large deformerait significativement le
contour (au lieu de simplement "souder" des elements proches) : mieux vaut
echouer avec un message clair (dessin trop eclate) que produire un caisson
meconnaissable."""

_MIN_MAX_CLOSING_RADIUS_PX = 8
"""Plancher absolu du plafond de recherche, pour les tres petites images de
travail (mask_resolution_px reduit) ou la fraction ci-dessus donnerait un
plafond derisoire (< quelques pixels)."""


class ArtworkExtractionError(ImageShapeExtractionError):
    """Erreur specifique a l'extraction artwork -- sous-classe de
    `ImageShapeExtractionError` : tout code appelant qui attrape deja cette
    derniere (ex. `image_lightbox_export.py`) continue de fonctionner sans
    modification, tout en pouvant distinguer explicitement ce cas si besoin."""


@dataclass
class ArtworkExtractionResult:
    envelope_polygon: Polygon | MultiPolygon
    """Contour exterieur unifie (mm, Y-up origine bas-gauche) -- consomme
    par le moteur d'extrusion (`vector_lightbox.py`) exactement comme
    `ImageShapeResult.polygon`, pour le corps et le fond du caisson."""
    ink_polygon: Polygon | MultiPolygon
    """Contour(s) de l'encre SEULE (mm, meme referentiel) -- detail fin, non
    ferme/unifie, pour le capot 2 couleurs."""
    width_mm: float
    height_mm: float
    ink_mask: np.ndarray
    """Masque d'encre (convention image, row0=haut) -- expose pour la
    previsualisation UI."""
    envelope_mask: np.ndarray
    """Masque enveloppe final (apres fill-from-border + fermeture
    eventuelle) -- expose pour la previsualisation UI."""
    threshold_used: int
    closing_radius_px: int
    """Rayon de fermeture morphologique effectivement applique, en pixels
    du masque de travail. 0 si l'encre etait deja une seule composante
    connexe (aucune fermeture necessaire)."""
    num_components_before_closing: int
    num_components_after_closing: int
    warnings: list[str] = field(default_factory=list)


def _fill_enclosed_regions(ink_mask: np.ndarray) -> np.ndarray:
    """Technique standard "fill-from-border" : flood-fill du fond (pixels
    hors encre) depuis les bords de l'image -- tout ce qui n'est PAS atteint
    par ce flood-fill (l'encre elle-meme, ET les poches de fond enfermees
    par l'encre, ex. l'interieur d'un cercle ferme ou l'espace entre des
    doigts) devient "matiere" pour le contour du caisson.

    `scipy.ndimage.binary_fill_holes` implemente exactement cet algorithme
    (flood-fill du complementaire depuis le bord, puis inversion) -- pas de
    reimplementation manuelle."""
    return ndimage.binary_fill_holes(ink_mask)


def _closing_kernel(radius_px: int) -> np.ndarray:
    size = 2 * radius_px + 1
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


def _apply_closing(ink_mask: np.ndarray, radius_px: int) -> np.ndarray:
    """Fermeture morphologique (dilatation puis erosion) sur `ink_mask`,
    rayon `radius_px` -- via OpenCV (deja une dependance du projet, utilise
    massivement dans `image_shape_extractor.py` pour le meme genre
    d'operations sur masque), pas `scipy.ndimage.binary_closing` (equivalent
    fonctionnel, choisi ici uniquement pour beneficier du meme
    `cv2.getStructuringElement` elliptique que le reste du pipeline
    seuillage/nettoyage)."""
    if radius_px <= 0:
        return ink_mask
    mask_u8 = ink_mask.astype(np.uint8) * 255
    closed = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, _closing_kernel(radius_px))
    return closed > 0


def _default_max_closing_radius_px(mask_shape: tuple[int, int]) -> int:
    return max(_MIN_MAX_CLOSING_RADIUS_PX, round(_DEFAULT_MAX_CLOSING_RADIUS_RATIO * max(mask_shape)))


def _search_min_closing_radius(ink_mask: np.ndarray, max_radius_px: int) -> tuple[int, np.ndarray]:
    """Recherche dichotomique du plus petit rayon de fermeture (1..
    `max_radius_px`) qui unifie `ink_mask` en une seule composante connexe.
    La fermeture est monotone dans la pratique (un rayon plus grand ne peut
    que souder davantage, jamais scinder une composante deja unifiee), d'ou
    la recherche par dichotomie plutot qu'un balayage lineaire -- O(log n)
    fermetures au lieu de O(n).

    Leve `ArtworkExtractionError` si meme `max_radius_px` ne suffit pas
    (dessin trop eclate pour un seul caisson a ce plafond)."""
    lo, hi = 1, max_radius_px
    best_radius: int | None = None
    best_mask: np.ndarray | None = None
    while lo <= hi:
        mid = (lo + hi) // 2
        closed = _apply_closing(ink_mask, mid)
        if count_connected_components(closed) == 1:
            best_radius = mid
            best_mask = closed
            hi = mid - 1
        else:
            lo = mid + 1

    if best_radius is None:
        raise ArtworkExtractionError(
            "Le dessin est trop eclate pour former un seul caisson : meme une fermeture "
            f"morphologique au rayon plafond ({max_radius_px}px) ne suffit pas a unifier toutes "
            "les composantes d'encre en une seule enveloppe connectee. Augmentez "
            "max_closing_radius_px si les elements disjoints sont volontairement eloignes, ou "
            "verifiez que l'image ne contient pas plusieurs sujets distincts."
        )
    return best_radius, best_mask


def compute_envelope_mask(
    ink_mask: np.ndarray,
    *,
    closing_radius_px: int | None = None,
    max_closing_radius_px: int | None = None,
) -> tuple[np.ndarray, int, int, int]:
    """Calcule le masque enveloppe (fill-from-border + fermeture
    morphologique automatique si necessaire) a partir du masque d'encre.

    Retourne `(envelope_mask, closing_radius_used, num_components_before,
    num_components_after)`. Si `closing_radius_px` est fourni explicitement
    (ex. UI exposant un slider plus tard), il est applique tel quel --
    erreur claire si le resultat n'est toujours pas une seule composante.
    Sinon, recherche automatique du plus petit rayon suffisant (plafonne a
    `max_closing_radius_px`, auto-calcule depuis la resolution du masque si
    omis -- voir `_default_max_closing_radius_px`)."""
    if not ink_mask.any():
        raise ArtworkExtractionError(
            "Aucune encre detectee dans le masque : rien a envelopper."
        )

    num_components_before = count_connected_components(ink_mask)

    if closing_radius_px is not None:
        working = _apply_closing(ink_mask, closing_radius_px)
        num_components_after = count_connected_components(working)
        if num_components_after != 1:
            raise ArtworkExtractionError(
                f"La fermeture morphologique au rayon impose ({closing_radius_px}px) ne suffit "
                f"pas a unifier le dessin en une seule composante connexe ({num_components_after} "
                "composantes restantes) -- augmentez le rayon."
            )
        envelope = _fill_enclosed_regions(working)
        return envelope, closing_radius_px, num_components_before, num_components_after

    if num_components_before <= 1:
        envelope = _fill_enclosed_regions(ink_mask)
        return envelope, 0, num_components_before, num_components_before

    max_radius = (
        max_closing_radius_px
        if max_closing_radius_px is not None
        else _default_max_closing_radius_px(ink_mask.shape)
    )
    radius, working = _search_min_closing_radius(ink_mask, max_radius)
    envelope = _fill_enclosed_regions(working)
    num_components_after = count_connected_components(working)
    return envelope, radius, num_components_before, num_components_after


def extract_artwork_from_arrays(
    gray: np.ndarray,
    width_mm: float,
    *,
    threshold_mode: str = "auto",
    threshold_value: int | None = None,
    min_component_area_ratio: float = _DEFAULT_INK_MIN_COMPONENT_AREA_RATIO,
    closing_radius_px: int | None = None,
    max_closing_radius_px: int | None = None,
) -> ArtworkExtractionResult:
    """Coeur du pipeline d'extraction artwork, a partir d'un tableau
    niveaux de gris DEJA CHARGE (pas de lecture disque) -- meme separation
    array/fichier que `image_shape_extractor.extract_shape_from_arrays`,
    pour que l'UI recalcule une previsualisation a chaque changement de
    seuil sans relire le fichier.

    Un dessin au trait n'a, par definition, pas de canal alpha exploitable
    (voir docstring de module) : contrairement au pipeline silhouette, il
    n'y a qu'un seul chemin -- seuillage Cas B (`threshold_and_clean_mask`,
    REUTILISE, pas duplique) -- suivi du calcul enveloppe."""
    if width_mm <= 0:
        raise ValueError("width_mm doit etre > 0.")

    warnings: list[str] = []

    ink_mask, threshold_used, threshold_warnings = threshold_and_clean_mask(
        gray,
        mode=threshold_mode,
        threshold_value=threshold_value,
        min_component_area_ratio=min_component_area_ratio,
    )
    warnings.extend(threshold_warnings)

    (
        envelope_mask,
        closing_radius_used,
        num_components_before,
        num_components_after,
    ) = compute_envelope_mask(
        ink_mask,
        closing_radius_px=closing_radius_px,
        max_closing_radius_px=max_closing_radius_px,
    )

    if closing_radius_used > 0:
        warnings.append(
            f"Dessin en {num_components_before} composante(s) d'encre disjointe(s) : fermeture "
            f"morphologique (rayon {closing_radius_used}px) appliquee pour former un seul caisson "
            "unifie."
        )

    envelope_polygon, height_mm, envelope_class_warnings = mask_to_polygon(
        envelope_mask, width_mm, simplify_tolerance_ratio=_ENVELOPE_SIMPLIFY_TOLERANCE_RATIO
    )
    warnings.extend(envelope_class_warnings)

    ink_polygon, _ink_height_mm, ink_class_warnings = mask_to_polygon(
        ink_mask, width_mm, simplify_tolerance_ratio=_INK_SIMPLIFY_TOLERANCE_RATIO
    )
    warnings.extend(ink_class_warnings)

    return ArtworkExtractionResult(
        envelope_polygon=envelope_polygon,
        ink_polygon=ink_polygon,
        width_mm=width_mm,
        height_mm=height_mm,
        ink_mask=ink_mask,
        envelope_mask=envelope_mask,
        threshold_used=threshold_used,
        closing_radius_px=closing_radius_used,
        num_components_before_closing=num_components_before,
        num_components_after_closing=num_components_after,
        warnings=warnings,
    )


def extract_artwork_from_image(
    image_path: str | Path,
    width_mm: float,
    *,
    threshold_mode: str = "auto",
    threshold_value: int | None = None,
    min_component_area_ratio: float = _DEFAULT_INK_MIN_COMPONENT_AREA_RATIO,
    closing_radius_px: int | None = None,
    max_closing_radius_px: int | None = None,
) -> ArtworkExtractionResult:
    """Point d'entree haut niveau : charge `image_path` (niveaux de gris
    uniquement -- un dessin au trait n'a pas de canal alpha exploitable, le
    canal alpha eventuel d'un PNG est ignore ici, contrairement au pipeline
    silhouette) puis delegue a `extract_artwork_from_arrays`."""
    from lithoshape3d.core.geometry.image_shape_extractor import load_image_for_extraction

    _alpha, gray = load_image_for_extraction(image_path)
    return extract_artwork_from_arrays(
        gray,
        width_mm,
        threshold_mode=threshold_mode,
        threshold_value=threshold_value,
        min_component_area_ratio=min_component_area_ratio,
        closing_radius_px=closing_radius_px,
        max_closing_radius_px=max_closing_radius_px,
    )
