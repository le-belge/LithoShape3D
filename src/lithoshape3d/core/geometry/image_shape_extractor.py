"""Extraction vectorielle d'une silhouette (contour de caisson) depuis une
image, pour le mode "LightBox depuis image".

Deux cas d'usage couverts (les deux confirmes necessaires) :

  - Cas A -- logo/silhouette a fond transparent (ou SVG rasterise en amont,
    voir `ui/shape_svg_import.py` -- Qt, donc hors de `core/`) : le canal
    alpha, deja seuille par le mecanisme EXISTANT du Shape Composer
    (`shape.build_shape_mask_from_image_array`), fournit directement un
    masque exploitable, sans pretraitement supplementaire.

  - Cas B -- photo classique sans transparence (ou canal alpha present mais
    non exploitable, ex. PNG RGBA entierement opaque) : seuillage
    automatique Otsu (`cv2.threshold` + `cv2.THRESH_OTSU`), avec option de
    seuil manuel (0-255), suivi d'un nettoyage des petites composantes
    connexes parasites (bruit capteur/JPEG, sous `min_component_area_ratio`
    de l'aire totale).

Dans les deux cas, le masque booleen final est converti en polygone(s)
Shapely (exterieur + trous) via `cv2.findContours` (contours a plat, sans
hierarchie parent/enfant exploitee) suivi d'une simplification
(`cv2.approxPolyDP`, necessaire : le bruit de rasterisation pixel-a-pixel
produirait sinon des polygones a des milliers de sommets, lents et fragiles
a extruder/booleaner via manifold3d) puis de la MEME classification par
confinement geometrique que pour les glyphes de police --
`contour_classification.classify_contours_by_containment`, reutilisee telle
quelle (gestion des composantes disjointes, trous multiples, trou touchant
le contour), PAS dupliquee.

Le polygone final est exprime en mm, referentiel Y-up origine bas-gauche --
exactement la meme convention que `LetterGlyph.to_shapely()` -- pour etre
consomme tel quel par le meme moteur d'extrusion generalise
(`vector_lightbox.py`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from lithoshape3d.core.geometry.contour_classification import (
    ContourClassificationError,
    classify_contours_by_containment,
)
from lithoshape3d.core.geometry.shape import build_shape_mask_from_image_array

_ALPHA_SIMPLIFY_TOLERANCE_RATIO = 0.004
"""Cas A : contours deja propres (alpha seuille a 0.5, pas de bruit photo),
une simplification legere suffit -- juste assez pour eviter le crenelage
pixel-a-pixel inevitable de toute rasterisation."""

_PHOTO_SIMPLIFY_TOLERANCE_RATIO = 0.008
"""Cas B : le seuillage d'une photo produit un contour bien plus bruite
(grain, JPEG, eclairage) -- tolerance plus large pour rester exploitable."""

_DEFAULT_MIN_COMPONENT_AREA_RATIO = 0.001
"""0.1% de l'aire totale -- composantes sous ce seuil considerees comme du
bruit parasite (cf. mission), pas des elements reels de la silhouette."""

_SUSPICIOUS_COVERAGE_LOW = 0.01
_SUSPICIOUS_COVERAGE_HIGH = 0.95
"""Bornes de couverture (Cas B) au-dela desquelles le seuillage automatique
est probablement inadapte (signe d'un sujet mal isole) -- avertissement
indicatif, pas un rejet : la silhouette reste generee."""

_DEFAULT_MASK_RESOLUTION_PX = 800
"""Borne la plus grande dimension du masque de travail : suffisant pour un
contour detaille, sans faire exploser le nombre de sommets bruts avant
simplification (l'extrusion/booleenne manifold3d doit rester rapide, cf.
mission)."""


class ImageShapeExtractionError(ValueError):
    """Image vide/uniforme, aucune forme detectable, ou silhouette
    degeneree (aire nulle) apres extraction du contour."""


@dataclass
class ImageShapeResult:
    polygon: Polygon | MultiPolygon
    """Contour(s) shapely, mm, referentiel Y-up origine bas-gauche -- meme
    convention que `LetterGlyph.to_shapely()`, consommable tel quel par
    `vector_lightbox.py`."""
    width_mm: float
    height_mm: float
    mask: np.ndarray
    """Masque final utilise pour l'extraction (convention image, row0=haut)
    -- expose pour la previsualisation UI (silhouette 2D bon marche, aucun
    recalcul separe necessaire)."""
    threshold_used: int | None = None
    """Seuil 0-255 effectivement applique (Cas B uniquement) ; `None` en
    Cas A (alpha direct, pas de seuillage)."""
    warnings: list[str] = field(default_factory=list)


def _alpha_is_exploitable(alpha: np.ndarray) -> bool:
    """Un canal alpha n'est utile que s'il code reellement une transparence
    partielle : une image RGBA entierement opaque (alpha=1 partout, cas
    frequent pour une photo simplement exportee en PNG) doit retomber sur
    le seuillage Cas B, exactement comme une photo JPEG sans canal alpha."""
    transparent_fraction = float((alpha < 0.5).mean())
    return 0.0 < transparent_fraction < 1.0


def load_image_for_extraction(image_path: str | Path) -> tuple[np.ndarray | None, np.ndarray]:
    """Charge `image_path` et retourne `(alpha_ou_None, gris)` en float
    [0,1] -- meme decision que le Shape Composer (canal alpha si present et
    reellement exploitable, sinon niveaux de gris pour le seuillage Cas B).
    Reutilise directement `core/image` (io + preprocessing), pas de
    logique de chargement dupliquee."""
    from lithoshape3d.core.image.preprocessing import to_grayscale_array

    image = Image.open(image_path)

    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        rgba = np.asarray(image.convert("RGBA"), dtype=np.float32)
        alpha = rgba[:, :, 3] / 255.0
        # Composite sur fond BLANC avant la conversion en niveaux de gris :
        # `Image.convert("L")` ignore le canal alpha et lit le RGB brut des
        # pixels transparents tel quel -- souvent (0,0,0) selon l'exporteur
        # (ex. rasterisation QtSvg), ce qui les fait apparaitre NOIRS (donc
        # "encre") au lieu de BLANCS (fond). Sur un logo a silhouette pleine
        # (ex. logo Tesla) ceci inversait completement la detection : tout
        # le canevas devenait "encre" (seuil Otsu degenere a 0), produisant
        # un contour = rectangle plein au lieu de la silhouette reelle.
        white_bg = Image.new("RGBA", image.size, (255, 255, 255, 255))
        composited = Image.alpha_composite(white_bg, image.convert("RGBA"))
        gray = to_grayscale_array(composited.convert("RGB"))
        if _alpha_is_exploitable(alpha):
            return alpha, gray
        return None, gray

    gray = to_grayscale_array(image)
    return None, gray


def mask_to_polygon(
    mask: np.ndarray,
    width_mm: float,
    *,
    simplify_tolerance_ratio: float = _ALPHA_SIMPLIFY_TOLERANCE_RATIO,
) -> tuple[Polygon | MultiPolygon, float, list[str]]:
    """Convertit un masque booleen (convention image, row0=haut) en
    polygone(s) Shapely en mm (Y-up, origine bas-gauche). `width_mm` fixe
    l'echelle ; `height_mm` (retournee) est deduite du ratio rows/cols du
    masque (pixels consideres carres, comme la grille du Shape Composer).

    Pipeline : `cv2.findContours` (contours bruts en pixels) ->
    `cv2.approxPolyDP` (simplification, cf. docstring de module) ->
    conversion mm -> `classify_contours_by_containment` (meme
    classification exterieur/trous que les glyphes de police, PAS
    dupliquee)."""
    if mask.ndim != 2:
        raise ValueError("mask doit etre 2D (rows, cols).")
    rows, cols = mask.shape
    if rows < 2 or cols < 2:
        raise ImageShapeExtractionError("Masque trop petit pour une extraction de contour.")

    height_mm = width_mm * rows / cols
    px_size_mm = width_mm / cols

    mask_u8 = mask.astype(np.uint8) * 255
    contours_cv, _hierarchy = cv2.findContours(mask_u8, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    contours_mm: list[list[tuple[float, float]]] = []
    for contour in contours_cv:
        if simplify_tolerance_ratio > 0 and len(contour) >= 3:
            perimeter = cv2.arcLength(contour, True)
            epsilon = max(1.0, simplify_tolerance_ratio * perimeter)
            contour = cv2.approxPolyDP(contour, epsilon, True)
        pts = contour.reshape(-1, 2)
        if len(pts) < 3:
            continue
        contour_mm = [
            (float(px) * px_size_mm, height_mm - float(py) * px_size_mm) for px, py in pts
        ]
        contours_mm.append(contour_mm)

    if not contours_mm:
        raise ImageShapeExtractionError(
            "Aucun contour detectable dans le masque : image vide, uniforme, ou seuillage inadapte."
        )

    try:
        parts, warnings = classify_contours_by_containment(
            contours_mm, touching_hole_note="silhouette d'image"
        )
    except ContourClassificationError as exc:
        raise ImageShapeExtractionError(str(exc)) from exc

    polygons = [part.to_shapely() for part in parts]
    polygon = polygons[0] if len(polygons) == 1 else unary_union(polygons)

    if polygon.is_empty or polygon.area <= 0:
        raise ImageShapeExtractionError(
            "Silhouette degeneree (aire nulle) apres extraction du contour."
        )

    return polygon, height_mm, warnings


def _border_mean(gray_u8: np.ndarray) -> float:
    """Niveau de gris moyen sur le pourtour de l'image (2 px) -- utilise
    comme estimation du "fond" pour deviner la polarite du sujet (plus clair
    ou plus sombre que le fond), voir `threshold_and_clean_mask`."""
    border = np.concatenate(
        [
            gray_u8[:2, :].ravel(),
            gray_u8[-2:, :].ravel(),
            gray_u8[:, :2].ravel(),
            gray_u8[:, -2:].ravel(),
        ]
    )
    return float(border.mean())


def threshold_and_clean_mask(
    gray: np.ndarray,
    *,
    mode: str = "auto",
    threshold_value: int | None = None,
    min_component_area_ratio: float = _DEFAULT_MIN_COMPONENT_AREA_RATIO,
) -> tuple[np.ndarray, int, list[str]]:
    """Cas B (photo sans transparence exploitable) : seuillage (Otsu par
    defaut, ou valeur manuelle 0-255) puis suppression des petites
    composantes connexes parasites (bruit) sous `min_component_area_ratio`
    de l'aire totale. Independant/testable isolement : ne decide pas
    lui-meme Cas A vs Cas B (voir `extract_shape_from_arrays`).

    Polarite (sujet plus sombre OU plus clair que le seuil) deduite du
    niveau de gris moyen sur le POURTOUR de l'image (`_border_mean`) : on
    suppose que le fond entoure le sujet et touche les bords (hypothese
    raisonnable pour une photo produit/objet isole, PAS pour une scene
    complexe ou le sujet occupe tout le cadre -- limitation documentee,
    ajustable via le seuil manuel si le resultat automatique est inverse)."""
    if gray.ndim != 2:
        raise ValueError("gray doit etre 2D (rows, cols).")
    if mode not in ("auto", "manual"):
        raise ValueError(f"mode invalide : {mode!r} (attendu 'auto' ou 'manual').")

    gray_u8 = np.ascontiguousarray((np.clip(gray, 0.0, 1.0) * 255).astype(np.uint8))

    if mode == "manual":
        if threshold_value is None:
            raise ValueError("threshold_value requis en mode 'manual'.")
        used_threshold = int(threshold_value)
        if not (0 <= used_threshold <= 255):
            raise ValueError(f"threshold_value hors plage : {used_threshold} (attendu 0-255).")
    else:
        ret, _binary = cv2.threshold(gray_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        used_threshold = int(ret)

    # Fond clair (bord majoritairement au-dessus du seuil) -> le sujet est
    # suppose plus sombre : masque = pixels EN DESSOUS du seuil. Fond
    # sombre -> l'inverse. Sans cette detection de polarite, Otsu seul
    # marquerait arbitrairement le cote "clair" comme sujet, ce qui est
    # invalide une fois sur deux (logo/silhouette sombre sur fond clair,
    # cas tres frequent en photo produit).
    if _border_mean(gray_u8) >= used_threshold:
        _ret, binary = cv2.threshold(gray_u8, used_threshold, 255, cv2.THRESH_BINARY_INV)
    else:
        _ret, binary = cv2.threshold(gray_u8, used_threshold, 255, cv2.THRESH_BINARY)

    mask = binary > 0
    warnings: list[str] = []

    coverage = float(mask.mean())
    if coverage == 0.0:
        raise ImageShapeExtractionError(
            "Le seuillage ne detecte aucune forme (image entierement en dessous du seuil) -- "
            "ajustez le seuil manuel."
        )
    if coverage == 1.0:
        raise ImageShapeExtractionError(
            "Le seuillage couvre l'image entiere (aucun contour possible) -- ajustez le seuil manuel."
        )
    if coverage < _SUSPICIOUS_COVERAGE_LOW or coverage > _SUSPICIOUS_COVERAGE_HIGH:
        warnings.append(
            f"Seuillage suspect : {coverage * 100:.1f}% de l'image couverte -- verifiez/ajustez "
            "le seuil manuel si la silhouette ne correspond pas au sujet attendu."
        )

    total_area_px = mask.size
    min_area_px = max(1, round(total_area_px * min_component_area_ratio))
    num_labels, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    cleaned = np.zeros_like(mask)
    removed_small = 0
    for label in range(1, num_labels):  # label 0 = fond
        area = stats[label, cv2.CC_STAT_AREA]
        if area >= min_area_px:
            cleaned |= labels == label
        else:
            removed_small += 1

    if not cleaned.any():
        raise ImageShapeExtractionError(
            "Toutes les composantes detectees sont sous le seuil de bruit "
            f"({min_component_area_ratio * 100:.2f}% de l'aire totale) -- silhouette vide apres "
            "nettoyage."
        )
    if removed_small:
        warnings.append(
            f"{removed_small} petite(s) composante(s) parasite(s) filtree(s) "
            f"(< {min_component_area_ratio * 100:.2f}% de l'aire totale)."
        )

    return cleaned, used_threshold, warnings


def extract_shape_from_arrays(
    alpha: np.ndarray | None,
    gray: np.ndarray,
    width_mm: float,
    *,
    threshold_mode: str = "auto",
    threshold_value: int | None = None,
    min_component_area_ratio: float = _DEFAULT_MIN_COMPONENT_AREA_RATIO,
    mask_resolution_px: int = _DEFAULT_MASK_RESOLUTION_PX,
) -> ImageShapeResult:
    """Coeur du pipeline d'extraction, a partir de tableaux DEJA CHARGES
    (pas de lecture disque) -- separe de `extract_shape_from_image` pour que
    l'UI puisse recalculer une previsualisation a chaque changement de seuil
    (Cas B) sans relire le fichier a chaque fois (meme discipline que
    `CadrageDialog` : recalcul 2D bon marche, jamais de mesh 3D ici).

    Decide Cas A (alpha exploitable) vs Cas B (seuillage) puis delegue
    l'extraction vectorielle commune a `mask_to_polygon`."""
    if width_mm <= 0:
        raise ValueError("width_mm doit etre > 0.")

    warnings: list[str] = []
    src_rows, src_cols = gray.shape
    scale = min(1.0, mask_resolution_px / max(src_rows, src_cols))
    rows = max(2, round(src_rows * scale))
    cols = max(2, round(src_cols * scale))

    if alpha is not None:
        mask = build_shape_mask_from_image_array(alpha, rows, cols)
        threshold_used = None
        simplify_ratio = _ALPHA_SIMPLIFY_TOLERANCE_RATIO
    else:
        from lithoshape3d.core.image.preprocessing import resize_array

        gray_resized = resize_array(gray, width_px=cols, height_px=rows)
        mask, threshold_used, clean_warnings = threshold_and_clean_mask(
            gray_resized,
            mode=threshold_mode,
            threshold_value=threshold_value,
            min_component_area_ratio=min_component_area_ratio,
        )
        warnings.extend(clean_warnings)
        simplify_ratio = _PHOTO_SIMPLIFY_TOLERANCE_RATIO

    if not mask.any():
        raise ImageShapeExtractionError("Aucune forme detectee dans l'image (masque entierement vide).")

    polygon, height_mm, classify_warnings = mask_to_polygon(
        mask, width_mm, simplify_tolerance_ratio=simplify_ratio
    )
    warnings.extend(classify_warnings)

    return ImageShapeResult(
        polygon=polygon,
        width_mm=width_mm,
        height_mm=height_mm,
        mask=mask,
        threshold_used=threshold_used,
        warnings=warnings,
    )


def extract_shape_from_image(
    image_path: str | Path,
    width_mm: float,
    *,
    threshold_mode: str = "auto",
    threshold_value: int | None = None,
    min_component_area_ratio: float = _DEFAULT_MIN_COMPONENT_AREA_RATIO,
    mask_resolution_px: int = _DEFAULT_MASK_RESOLUTION_PX,
) -> ImageShapeResult:
    """Point d'entree haut niveau : charge `image_path` puis extrait sa
    silhouette vectorielle (Cas A ou Cas B selon l'image, voir docstring de
    module). Fine enveloppe autour de `extract_shape_from_arrays` (chargement
    + extraction) -- utilisee par le pipeline CLI/GUI ; l'UI de
    previsualisation utilise `extract_shape_from_arrays` directement pour
    eviter de relire le fichier a chaque changement de seuil."""
    alpha, gray = load_image_for_extraction(image_path)
    return extract_shape_from_arrays(
        alpha,
        gray,
        width_mm,
        threshold_mode=threshold_mode,
        threshold_value=threshold_value,
        min_component_area_ratio=min_component_area_ratio,
        mask_resolution_px=mask_resolution_px,
    )
