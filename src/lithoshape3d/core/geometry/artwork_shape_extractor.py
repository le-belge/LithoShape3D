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

_ENVELOPE_SIMPLIFY_TOLERANCE_RATIO = 0.0003
"""Tolerance de simplification de l'enveloppe (corps/fond du caisson).
Deuxieme abaissement (0.002 -> 0.0003) : le premier passage a 0.002 restait
insuffisant sur un contour a grands arcs doux (logo Tesla T, grandes courbes
en aile) -- seulement ~20-26 sommets sur tout le contour, arcs clairement
factes/segmentes (retour utilisateur direct sur ce cas). Verifie par balayage
visuel (0.002/0.0008/0.0003/0.0001) sur ce meme cas : 0.0003 (~45 sommets sur
le contour complet) donne des arcs visuellement lisses sans repartir sur un
nombre de sommets demesure (0.0001 n'apporte plus de gain visible). Toujours
verifie sans regression sur Cherry Moon et Circuit Foil (silhouette)."""

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

_NOTCH_SMOOTHING_MAX_AREA_RATIO = 0.03
"""Seuil (3% de l'aire totale de l'enveloppe -- releve de 1% : mesure sur un
cas reel, "Cherry Moon", la zone a combler pour une encoche legitime
(jonction texte/anneau decoratif) faisait ~1.0-1.2% de l'aire totale, donc
systematiquement rejetee par l'ancien seuil de 1% quel que soit le rayon de
fermeture utilise -- verifie par mesure directe des composantes ajoutees.
3% reste tres en dessous d'une vraie caracteristique du dessin, voir
paragraphe suivant) utilise par
`_smooth_envelope_notches` pour distinguer une VRAIE encoche -- artefact
d'un pont de fermeture morphologique trop juste entre deux elements
disjoints qui restent localement mal soudes meme si le masque global est
devenu une seule composante connexe -- d'une vraie caracteristique du
dessin (ex. l'ouverture d'un croissant de lune, l'interieur d'un "C").
`_search_min_closing_radius` ne garantit que la CONNEXITE GLOBALE au plus
petit rayon possible ; elle ne garantit PAS que CHAQUE paire d'elements
proches soit individuellement bien soudee -- un pont local peut rester
etroit/concave a un endroit precis du contour meme quand le masque entier
est deja une seule composante (le chemin de connexite passe ailleurs).
Une caracteristique reelle du dessin (bien plus grande, generalement du
meme ordre de grandeur que l'enveloppe elle-meme) reste tres au-dessus de
ce seuil et n'est donc jamais comblee par erreur."""

_NOTCH_SMOOTHING_RADIUS_MULTIPLIER = 4
"""Le rayon de fermeture utilise pour le LISSAGE d'encoches est un multiple
de `max_radius` (le plafond deja utilise pour la recherche d'UNIFICATION
globale), pas `max_radius` lui-meme -- constate sur un cas reel (logo
"Cherry Moon", jonction entre un texte et un anneau decoratif) qu'un rayon
egal au plafond d'unification (24px) laissait une encoche nette et
persistante, alors qu'un rayon 3-4x plus grand la comble entierement (verifie
visuellement, `examples/physical_validation/cherry_moon_source/`). Sans
danger d'effacer une vraie caracteristique du dessin malgre ce rayon plus
genereux : le filtre par aire (`_NOTCH_SMOOTHING_MAX_AREA_RATIO`) reste la
seule garde -- il s'applique independamment du rayon utilise pour la passe de
fermeture supplementaire."""

_NOTCH_SMOOTHING_MAX_RADIUS_PX = 400
"""Plafond absolu sur le rayon de lissage (independant de la taille de
l'image) : evite un cout de calcul demesure sur une tres grande image de
travail ou `max_radius * _NOTCH_SMOOTHING_RADIUS_MULTIPLIER` deviendrait
enorme."""

_ENVELOPE_CHAIKIN_ITERATIONS = 2
"""Nombre d'iterations de lissage de coins (Chaikin) applique au contour de
l'ENVELOPPE apres simplification -- retour utilisateur direct : sur un
contour a grands arcs doux (logo Tesla T), meme un `approxPolyDP` tres fin
reste visiblement facete/segmente (l'ecart entre epsilon=1px, ~48 sommets,
trop grossier, et epsilon=0.5px, ~850 sommets, qui ne fait que recopier le
crenelage pixel du raster sans etre plus lisse, ne laisse aucun compromis
de simplification satisfaisant). Chaikin (coupe de coins recursive, purement
2D sur le CONTOUR avant extrusion -- ne touche jamais la triangulation 3D,
contrairement a la subdivision de maillage retiree precedemment pour cause
de jonctions en "T"/fissures) arrondit reellement les arcs sans reintroduire
le crenelage pixel. 2 iterations (verifie visuellement) suffisent a lisser
sans faire exploser le nombre de sommets (45 -> ~180) ni arrondir a l'exces
des coins qui doivent rester nets (angles voulus du dessin)."""


def _chaikin_smooth_ring(coords: list[tuple[float, float]], iterations: int) -> list[tuple[float, float]]:
    """Lissage de coins de Chaikin sur un anneau FERME (`coords[0] ==
    coords[-1]`, convention Shapely) : a chaque iteration, chaque arete
    `(P0,P1)` est remplacee par deux points `Q=0.75*P0+0.25*P1` et
    `R=0.25*P0+0.75*P1`, coupant chaque coin en un petit segment -- effet
    d'arrondi progressif et stable (contrairement a un lissage par moyenne
    glissante, ne peut jamais faire sortir le contour de l'enveloppe convexe
    locale de ses points d'origine, donc ne peut pas introduire d'auto-
    intersection nouvelle sur un polygone deja simple)."""
    if iterations <= 0 or len(coords) < 4:
        return coords
    pts = np.asarray(coords[:-1], dtype=np.float64)
    for _ in range(iterations):
        p0 = pts
        p1 = np.roll(pts, -1, axis=0)
        q = 0.75 * p0 + 0.25 * p1
        r = 0.25 * p0 + 0.75 * p1
        pts = np.empty((len(p0) * 2, 2), dtype=np.float64)
        pts[0::2] = q
        pts[1::2] = r
    return [tuple(p) for p in pts] + [tuple(pts[0])]


def _smooth_polygon_corners(geom: Polygon | MultiPolygon, iterations: int) -> Polygon | MultiPolygon:
    """Applique `_chaikin_smooth_ring` a l'exterieur ET a chaque trou d'un
    `Polygon`/`MultiPolygon` -- garde les trous lisses au meme titre que le
    contour exterieur (sinon un contour exterieur arrondi avec des trous
    encore factes serait incoherent visuellement)."""
    if iterations <= 0:
        return geom

    def smooth_one(poly: Polygon) -> Polygon:
        exterior = _chaikin_smooth_ring(list(poly.exterior.coords), iterations)
        interiors = [_chaikin_smooth_ring(list(ring.coords), iterations) for ring in poly.interiors]
        return Polygon(exterior, interiors)

    if geom.geom_type == "Polygon":
        return smooth_one(geom)
    return MultiPolygon([smooth_one(p) for p in geom.geoms])


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
    ink_mask: np.ndarray | None
    """Masque d'encre (convention image, row0=haut) -- expose pour la
    previsualisation UI. `None` pour une source `.svg` (pipeline vectoriel,
    voir `extract_artwork_from_svg` -- aucun masque pixel n'est produit ;
    l'UI peut au besoin rasteriser `ink_polygon`/`envelope_polygon`
    UNIQUEMENT pour l'affichage d'apercu, jamais pour l'extraction elle-meme)."""
    envelope_mask: np.ndarray | None
    """Masque enveloppe final (apres fill-from-border + fermeture
    eventuelle) -- expose pour la previsualisation UI. `None` pour une
    source `.svg` (voir `ink_mask`)."""
    threshold_used: int | None
    """`None` pour une source `.svg` (pas de seuillage, pipeline vectoriel)."""
    closing_radius_px: int
    """Rayon de fermeture morphologique effectivement applique, en pixels
    du masque de travail. 0 si l'encre etait deja une seule composante
    connexe (aucune fermeture necessaire), ou pour une source `.svg` (la
    soudure equivalente est `weld_distance_mm`, en mm, pas en pixels --
    voir `vector_envelope.weld_disjoint_components`)."""
    num_components_before_closing: int
    num_components_after_closing: int
    weld_distance_mm: float = 0.0
    """Distance de soudure vectorielle appliquee (mm) -- uniquement pour une
    source `.svg` en mode `artwork_envelope` (0.0 sinon, y compris quand le
    pipeline raster est utilise)."""
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


def _smooth_envelope_notches(
    envelope_mask: np.ndarray,
    radius_px: int,
    area_ratio_threshold: float = _NOTCH_SMOOTHING_MAX_AREA_RATIO,
) -> np.ndarray:
    """Comble les encoches locales laissees par une fermeture morphologique
    qui a suffi a unifier le dessin en une seule composante connexe GLOBALE
    (voir `_search_min_closing_radius`) mais sans souder localement CHAQUE
    paire d'elements proches -- ex. deux traits fins d'un anneau decoratif
    separes par un ecart legerement superieur au rayon de fermeture utilise,
    alors qu'une autre paire d'elements ailleurs a suffi a rendre le masque
    global connexe. Le resultat est topologiquement correct (une seule
    composante, mesh watertight) mais geometriquement defectueux : une
    concavite en forme de "V" ou de marche, anormale, dans un contour censu
    etre lisse a cet endroit.

    Applique une fermeture morphologique supplementaire sur l'ENVELOPPE
    elle-meme (pas sur l'encre) au rayon `radius_px` (le plafond de
    recherche deja calcule -- volontairement plus grand que le rayon minimal
    qui a suffi a unifier le masque, car unifier localement CETTE encoche
    precise peut demander plus que le minimum global), puis ne CONSERVE que
    les pixels ajoutes dont la composante connexe est petite (< `area_ratio_
    threshold` de l'aire totale) -- une vraie caracteristique du dessin
    (ouverture, echancrure volontaire) est bien plus grande et n'est donc
    jamais affectee. Ne s'applique qu'aux pixels AJOUTES par la fermeture
    supplementaire (jamais retires) : ne peut donc jamais faire disparaitre
    de matiere existante ni introduire de nouveau trou."""
    if radius_px <= 0 or not envelope_mask.any():
        return envelope_mask

    total_area = float(envelope_mask.sum())
    if total_area <= 0:
        return envelope_mask

    closed = _apply_closing(envelope_mask, radius_px)
    added = closed & ~envelope_mask
    if not added.any():
        return envelope_mask

    labeled, num_labels = ndimage.label(added)
    if num_labels == 0:
        return envelope_mask

    areas = ndimage.sum(added, labeled, index=range(1, num_labels + 1))
    max_area = area_ratio_threshold * total_area
    keep_labels = [i + 1 for i, area in enumerate(areas) if area <= max_area]
    if not keep_labels:
        return envelope_mask

    fill_mask = np.isin(labeled, keep_labels)
    return envelope_mask | fill_mask


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
        smoothing_radius = min(
            closing_radius_px * _NOTCH_SMOOTHING_RADIUS_MULTIPLIER,
            _NOTCH_SMOOTHING_MAX_RADIUS_PX,
        )
        envelope = _smooth_envelope_notches(envelope, smoothing_radius)
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
    # `radius` est le plus PETIT rayon qui unifie le masque en une seule
    # composante GLOBALE -- pas garanti de souder localement chaque paire
    # d'elements proches (voir docstring de `_smooth_envelope_notches`).
    # La passe de lissage utilise un multiple de CE rayon (`radius`, pas le
    # plafond `max_radius` -- un multiple du plafond peut fermer une zone
    # bien plus grande que necessaire, faisant deborder meme le seuil d'aire
    # relaxe `_NOTCH_SMOOTHING_MAX_AREA_RATIO`, verifie sur le cas reel
    # "Cherry Moon" ou seul un rayon proche de `radius` -- pas de
    # `max_radius` -- comblait effectivement l'encoche sans etre rejete).
    smoothing_radius = min(
        radius * _NOTCH_SMOOTHING_RADIUS_MULTIPLIER, _NOTCH_SMOOTHING_MAX_RADIUS_PX
    )
    envelope = _smooth_envelope_notches(envelope, smoothing_radius)
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
    """Coeur du pipeline d'extraction artwork RASTER, a partir d'un tableau
    niveaux de gris DEJA CHARGE (pas de lecture disque) -- meme separation
    array/fichier que `image_shape_extractor.extract_shape_from_arrays`,
    pour que l'UI recalcule une previsualisation a chaque changement de
    seuil sans relire le fichier. Reserve aux images RASTER sans donnees
    vectorielles disponibles (PNG/JPG) -- pour une source `.svg`, voir
    `extract_artwork_from_svg` (pipeline vectoriel, aucune rasterisation).

    Un dessin au trait n'a, par definition, pas de canal alpha exploitable
    (voir docstring de module) : contrairement au pipeline silhouette, il
    n'y a qu'un seul chemin -- seuillage Cas B (`threshold_and_clean_mask`,
    REUTILISE, pas duplique) -- suivi du calcul enveloppe.

    NOTE (nettoyage architectural) : cette fonction exposait auparavant un
    parametre `force_convex_envelope` qui remplaçait le contour d'enveloppe
    par son cercle englobant minimal -- retire : un contour d'enveloppe qui
    reste visiblement non circulaire a certains endroits est un
    comportement ATTENDU et FIDELE au dessin source (le dessin lui-meme
    n'atteint pas un cercle parfait a ces points), pas un defaut a corriger
    par un hack geometrique specifique. Voir `vector_envelope.py` pour la
    soudure vectorielle GENERIQUE qui remplace ce hack pour les sources
    `.svg`."""
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
    if envelope_polygon.is_valid and not envelope_polygon.is_empty:
        smoothed = _smooth_polygon_corners(envelope_polygon, _ENVELOPE_CHAIKIN_ITERATIONS)
        if smoothed.is_valid and not smoothed.is_empty:
            envelope_polygon = smoothed

    ink_polygon, _ink_height_mm, ink_class_warnings = mask_to_polygon(
        ink_mask, width_mm, simplify_tolerance_ratio=_INK_SIMPLIFY_TOLERANCE_RATIO
    )
    warnings.extend(ink_class_warnings)
    if ink_polygon.is_valid and not ink_polygon.is_empty:
        smoothed_ink = _smooth_polygon_corners(ink_polygon, _ENVELOPE_CHAIKIN_ITERATIONS)
        if smoothed_ink.is_valid and not smoothed_ink.is_empty:
            ink_polygon = smoothed_ink

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
    """Point d'entree haut niveau RASTER : charge `image_path` (niveaux de
    gris uniquement -- un dessin au trait n'a pas de canal alpha
    exploitable, le canal alpha eventuel d'un PNG est ignore ici,
    contrairement au pipeline silhouette) puis delegue a
    `extract_artwork_from_arrays`. Pour une source `.svg`, voir
    `extract_artwork_from_svg` -- ce point d'entree NE DOIT PAS recevoir un
    `.svg` (aucune rasterisation de SVG dans ce pipeline, voir docstring de
    module `image_lightbox_export.py`)."""
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


def _fill_envelope_holes(geom: Polygon | MultiPolygon) -> Polygon | MultiPolygon:
    """Retire tous les trous internes (`interiors`) d'un polygone/
    MultiPolygon -- equivalent vectoriel EXACT du "fill-from-border" raster
    (`_fill_enclosed_regions`, `ndimage.binary_fill_holes`) applique au
    chemin PIXEL historique : ce ne sont pas les trous D'ENCRE (interieur
    d'un "O", espace entre des doigts) qui doivent disparaitre de l'ink
    fin -- ceux-la restent intacts sur `ink_polygon`, non touche ici -- mais
    les zones ENFERMEES par l'encre unifiee/soudee qui, dans le corps
    imprime, doivent devenir de la MATIERE (le mur/fond du caisson est un
    disque PLEIN, pas une dentelle suivant chaque trait de texte).

    Bug reel corrige (retour utilisateur avec capture) : sans cet appel,
    `envelope_polygon` gardait de grands trous a l'emplacement de l'anneau
    de texte/tirets decoratifs (le contour vectoriel des traits fins
    n'entoure PAS une zone pleine par nature), et `vector_lightbox_
    cap_footprint` (derive de cette enveloppe) heritait de ces memes trous
    -- l'intersection avec `ink_polygon` pour le capot 2 couleurs melangeait
    alors ces trous avec les vrais details du texte, deformant/fusionnant
    des lettres entieres. Une SEULE fonction, appliquee une seule fois ici
    (pas de duplication cote raster, qui a deja son propre `_fill_enclosed_
    regions` equivalent pour son propre chemin pixel)."""
    if geom.geom_type == "Polygon":
        if not geom.interiors:
            return geom
        return Polygon(geom.exterior)
    filled = [Polygon(g.exterior) if g.interiors else g for g in geom.geoms]
    return MultiPolygon(filled) if len(filled) > 1 else filled[0]


def extract_artwork_from_svg(
    svg_path: str | Path,
    width_mm: float,
    *,
    max_chord_error_mm: float | None = None,
    weld_margin_ratio: float | None = None,
) -> ArtworkExtractionResult:
    """Pipeline artwork VECTORIEL pour une source `.svg` -- AUCUNE
    rasterisation, contrairement a `extract_artwork_from_image` : reutilise
    le meme moteur de parsing/tessellation que le mode `silhouette`
    (`svg_path_extractor.extract_svg_components_from_svg`, une entree par
    `<path>` d'origine), puis :

      - `ink_polygon` = union simple de TOUS les composants -- la geometrie
        vectorielle fidele au SVG source, SANS soudure (equivalent du
        contour `silhouette` pour ce meme fichier) : detail fin pour le
        capot 2 couleurs.
      - `envelope_polygon` = soudure vectorielle GENERIQUE des composants
        disjoints (`vector_envelope.weld_disjoint_components`) : relie les
        elements physiquement disjoints du dessin (ex. tirets decoratifs,
        poings ecartes d'un cercle) par la distance de soudure REELLEMENT
        necessaire (mesuree, pas une heuristique), sans hack specifique a
        une forme.

    Retourne un `ArtworkExtractionResult` avec `ink_mask`/`envelope_mask`/
    `threshold_used` a `None` (pas de masque pixel dans ce pipeline) et
    `weld_distance_mm` renseigne."""
    from lithoshape3d.core.geometry.svg_path_extractor import (
        SvgPathExtractionError,
        _DEFAULT_MAX_CHORD_ERROR_MM,
        extract_svg_components_from_svg,
    )
    from lithoshape3d.core.geometry.vector_envelope import (
        _DEFAULT_WELD_MARGIN_RATIO,
        weld_disjoint_components,
    )

    if width_mm <= 0:
        raise ValueError("width_mm doit etre > 0.")

    effective_chord_error = (
        max_chord_error_mm if max_chord_error_mm is not None else _DEFAULT_MAX_CHORD_ERROR_MM
    )
    effective_margin = weld_margin_ratio if weld_margin_ratio is not None else _DEFAULT_WELD_MARGIN_RATIO

    try:
        components_result = extract_svg_components_from_svg(
            svg_path, width_mm, max_chord_error_mm=effective_chord_error
        )
    except SvgPathExtractionError as exc:
        raise ArtworkExtractionError(str(exc)) from exc

    warnings: list[str] = []
    components = components_result.polygons

    ink_polygon = components[0] if len(components) == 1 else unary_union_polygons(components)
    if ink_polygon.is_empty or ink_polygon.area <= 0:
        raise ArtworkExtractionError(
            f"Encre degeneree (aire nulle) apres extraction vectorielle de : {svg_path}."
        )

    weld = weld_disjoint_components(components, margin_ratio=effective_margin)
    warnings.extend(weld.warnings)
    if weld.num_components_before > 1:
        warnings.append(
            f"Dessin en {weld.num_components_before} composante(s) vectorielle(s) disjointe(s) : "
            f"soudure vectorielle (distance {weld.weld_distance_mm:.3f}mm) appliquee pour former un "
            "seul caisson unifie."
        )
    # Ne comble les trous internes de l'enveloppe QUE si une soudure a
    # reellement eu lieu (plusieurs composantes disjointes bridees) : dans ce
    # cas, un trou est un artefact de l'assemblage (espace laisse entre des
    # elements a l'origine separes -- tirets, texte en arc), pas une cavite
    # dessinee intentionnellement. Si le dessin etait DEJA une seule
    # composante (aucune soudure necessaire, ex. un vrai anneau/donut), ses
    # trous existaient AVANT toute soudure -- ce sont de vraies
    # caracteristiques du dessin, jamais comblees (regle generique, testee
    # explicitement par `test_ring_artwork_envelope_does_not_fill_the_
    # legitimate_hole`).
    envelope_polygon = (
        _fill_envelope_holes(weld.polygon) if weld.num_components_before > 1 else weld.polygon
    )
    if envelope_polygon.is_empty or envelope_polygon.area <= 0:
        raise ArtworkExtractionError(
            f"Enveloppe degeneree (aire nulle) apres soudure vectorielle de : {svg_path}."
        )

    return ArtworkExtractionResult(
        envelope_polygon=envelope_polygon,
        ink_polygon=ink_polygon,
        width_mm=width_mm,
        height_mm=components_result.height_mm,
        ink_mask=None,
        envelope_mask=None,
        threshold_used=None,
        closing_radius_px=0,
        num_components_before_closing=weld.num_components_before,
        num_components_after_closing=weld.num_components_after,
        weld_distance_mm=weld.weld_distance_mm,
        warnings=warnings,
    )


def unary_union_polygons(polygons):
    """Petit alias local pour eviter d'importer `shapely.ops.unary_union`
    sous deux noms differents dans ce module (deja utilise ailleurs sous son
    nom d'origine dans `svg_path_extractor.py`)."""
    from shapely.ops import unary_union

    return unary_union(polygons)
