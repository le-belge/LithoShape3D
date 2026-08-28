"""Classification generique de contours 2D en composantes exterieures
disjointes + trous, par confinement geometrique (shapely).

Extrait de `letter_glyph_extractor.py` (ou cette logique a ete developpee et
validee en premier pour les glyphes de police) afin d'etre reutilisee SANS
DUPLICATION par `image_shape_extractor.py` (silhouettes vectorisees depuis
une image) -- l'algorithme ne fait AUCUNE hypothese specifique a la
typographie (pas de convention even-odd/nonzero par type de police, pas de
notion de glyphe) : il prend une liste de contours 2D bruts (chacun une
liste de points `(x, y)`) et les regroupe en composantes exterieures
disjointes, chacune avec ses propres trous, par un test de confinement
geometrique (un contour est un "trou" s'il est contenu dans un contour de
plus grande aire deja classe exterieur).

Gere aussi le cas degenere ou un trou touche/chevauche son propre contour
exterieur (polygone invalide au sens OGC) : fusion via `buffer(0)` avec
avertissement explicite, plutot que de laisser une geometrie invalide se
propager en aval -- voir `letter_glyph_extractor.py` pour le cas reel qui a
motive cette reparation (police tres condensee), reproductible aussi sur
des silhouettes d'image bruitees (deux composantes qui se touchent
exactement apres seuillage/simplification)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.geometry import LineString, Polygon
from shapely.ops import nearest_points, unary_union
from shapely.validation import explain_validity


class ContourClassificationError(ValueError):
    """Aucun contour exploitable dans la liste fournie (vide, tous
    degeneres/aire nulle, ou geometrie invalide et irreparable)."""


_SIGNIFICANT_LOSS_RATIO = 0.02
"""Si la reparation `buffer(0)` d'un contour auto-intersectant le scinde en
plusieurs morceaux et que les morceaux non retenus representent plus de 2%
de l'aire totale, ce n'est probablement PAS un artefact de bruit ponctuel
mais un vrai lobe du dessin (ex. fermeture morphologique d'`artwork_shape_
extractor.py` qui a produit un pincement a un seul point entre deux lobes
legitimement connectes -- pas un trou qui touche le bord). Dans ce cas on
tente de RESSOUDER les morceaux plutot que d'en jeter un silencieusement
(voir `_reunite_split_pieces`)."""

_RECONNECT_MAX_GAP_RATIO = 0.15
"""Plafond de distance de pontage (`_reunite_split_pieces`), en fraction de
la diagonale de la boite englobante de TOUS les morceaux : le vrai
pincement mesure (issu de la simplification `approxPolyDP` ou de la
fermeture morphologique) est en general tres inferieur a ce plafond --
au-dela, les morceaux sont probablement reellement disjoints (pas juste une
jonction fragile) et on renonce plutot que de forcer un pont absurde."""

_BRIDGE_WIDTH_RATIO = 0.02
"""Largeur du pont local (`_reunite_split_pieces`), en fraction de la
distance a combler -- juste assez pour garantir un chevauchement robuste
aux deux extremites (evite un contact a un seul point, topologiquement
fragile), sans jamais s'approcher de la taille des trous fins internes du
dessin (contrairement a un dilate/erode global sur route la piece, voir
note ci-dessous)."""

_MIN_BRIDGE_WIDTH_MM = 0.01


def _reunite_split_pieces(geoms: list[Polygon]) -> Polygon | None:
    """Tente de ressouder des morceaux issus d'un `buffer(0)` qui a scinde
    une forme auto-intersectante (pincement local -- ex. hole touchant
    l'exterieur en un point apres simplification -- PAS des elements
    reellement disjoints).

    IMPORTANT : ne PAS dilater/eroder les morceaux entiers (un `buffer(eps)`
    global suffisant pour combler un pincement distant est presque toujours
    assez large pour aussi COMBLER les trous fins internes legitimes du plus
    gros morceau -- ex. 23 trous representant le detail fin d'un dessin au
    trait -- l'erosion qui suit ne les recree pas). A la place : on construit
    un pont LOCAL (un `LineString` entre les points les plus proches de deux
    morceaux, buffer'e d'une largeur minime) qui ne touche que le voisinage
    immediat du pincement, puis on unionne tous les morceaux + ponts d'un
    coup via `unary_union` -- qui preserve nativement les trous internes de
    chaque polygone (un trou n'est efface que si un pont le recouvre
    explicitement, ce qui n'arrive pas pour un pont fin entre deux points de
    bord). Ressoude iterativement le morceau le plus proche du groupe deja
    fusionne (plus proche voisin d'abord). Retourne `None` si un ecart
    depasse `_RECONNECT_MAX_GAP_RATIO` de la diagonale globale -- morceaux
    alors reellement disjoints, pas juste une jonction fragile."""
    if len(geoms) < 2:
        return geoms[0] if geoms else None

    minx = min(g.bounds[0] for g in geoms)
    miny = min(g.bounds[1] for g in geoms)
    maxx = max(g.bounds[2] for g in geoms)
    maxy = max(g.bounds[3] for g in geoms)
    diag = math.hypot(maxx - minx, maxy - miny)
    if diag <= 0:
        return None
    max_gap = diag * _RECONNECT_MAX_GAP_RATIO

    remaining = sorted(geoms, key=lambda g: g.area, reverse=True)
    fused_parts: list = [remaining.pop(0)]
    merged_union = fused_parts[0]

    while remaining:
        distances = [merged_union.distance(g) for g in remaining]
        idx = min(range(len(remaining)), key=lambda i: distances[i])
        gap = distances[idx]
        if gap > max_gap:
            return None
        piece = remaining.pop(idx)

        # Meme un contact exact (gap == 0, cas frequent d'un pincement a un
        # seul point issu de la simplification) ne suffit PAS a garantir
        # qu'`unary_union` fusionne les deux morceaux en un seul `Polygon` --
        # deux polygones qui ne se touchent qu'en un point restent souvent
        # une geometrie a plusieurs composantes (contact non planaire). Un
        # pont de largeur strictement positive est donc toujours construit,
        # meme pour gap == 0.
        p_on_merged, p_on_piece = nearest_points(merged_union, piece)
        width = max(gap * _BRIDGE_WIDTH_RATIO, _MIN_BRIDGE_WIDTH_MM)
        bridge = LineString([p_on_merged, p_on_piece]).buffer(width, cap_style=1)
        fused_parts.append(bridge)
        fused_parts.append(piece)
        merged_union = unary_union(fused_parts)

    if merged_union.geom_type == "Polygon" and not merged_union.is_empty and merged_union.area > 0:
        return merged_union
    return None


@dataclass
class ContourPart:
    """Une composante exterieure disjointe (racine de confinement), avec
    ses propres trous internes eventuels."""

    exterior: list[tuple[float, float]]
    holes: list[list[tuple[float, float]]] = field(default_factory=list)

    def to_shapely(self) -> Polygon:
        return Polygon(self.exterior, holes=self.holes)


def _repair_touching_hole(
    exterior_pts: list[tuple[float, float]],
    holes: list[list[tuple[float, float]]],
    warnings: list[str],
    touching_hole_note: str | None,
) -> tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]:
    """Repare le cas degenere ou un trou touche le contour exterieur :
    fusionne via `buffer(0)` (le trou est absorbe, donc disparait) et
    avertit, plutot que de laisser un `Polygon` invalide au sens OGC se
    propager en aval. `touching_hole_note` : precision contextuelle
    optionnelle sur la cause probable (ex. "police tres condensee"), ajoutee
    entre parentheses au message pour l'appelant."""
    candidate = Polygon(exterior_pts, holes=holes)
    if candidate.is_valid:
        return exterior_pts, holes

    reason = explain_validity(candidate)
    suffix = f" ({touching_hole_note})" if touching_hole_note else ""
    warnings.append(
        f"Trou interne touchant le contour exterieur detecte et fusionne{suffix} : {reason}."
    )
    repaired = candidate.buffer(0)
    if repaired.geom_type == "Polygon" and list(repaired.interiors):
        return list(repaired.exterior.coords), [list(ring.coords) for ring in repaired.interiors]
    # Fusion totale : plus de trou distinguable (repaired peut aussi etre un
    # MultiPolygon si la reparation a scinde la forme -- on garde alors la
    # plus grande composante, cas tres rare qui merite un avertissement.
    if repaired.geom_type == "MultiPolygon":
        geoms = sorted(repaired.geoms, key=lambda g: g.area, reverse=True)
        largest = geoms[0]
        total_area = sum(g.area for g in geoms)
        lost_area = total_area - largest.area
        lost_ratio = (lost_area / total_area) if total_area > 0 else 0.0

        if lost_ratio > _SIGNIFICANT_LOSS_RATIO:
            reunited = _reunite_split_pieces(geoms)
            if reunited is not None:
                warnings.append(
                    f"Trou interne touchant le contour exterieur detecte{suffix} : {reason}. La "
                    f"reparation standard aurait rejete {lost_area:.1f} mm2 ({lost_ratio * 100:.1f}% "
                    "de l'aire) comme morceau distinct -- pontage local applique pour ressouder les "
                    "morceaux et ne perdre aucune matiere."
                )
                if reunited.interiors:
                    return list(reunited.exterior.coords), [
                        list(r.coords) for r in reunited.interiors
                    ]
                return list(reunited.exterior.coords), []

            warnings.append(
                "La reparation du trou touchant le contour a scinde la forme en plusieurs "
                f"morceaux ; seul le plus grand est conserve -- PERTE DE MATIERE SIGNIFICATIVE : "
                f"{lost_area:.1f} mm2 ({lost_ratio * 100:.1f}% de l'aire totale) rejetes silencieusement "
                "sans ce message. Verifiez le resultat et ajustez le seuil/la fermeture si ce morceau "
                "etait un element reel du dessin."
            )
            return list(largest.exterior.coords), [list(r.coords) for r in largest.interiors]

        warnings.append(
            "La reparation du trou touchant le contour a scinde la forme en plusieurs morceaux ; "
            f"seul le plus grand est conserve (perte : {lost_area:.1f} mm2, {lost_ratio * 100:.1f}% "
            "de l'aire, sous le seuil de signalement)."
        )
        return list(largest.exterior.coords), [list(r.coords) for r in largest.interiors]
    return exterior_pts if repaired.is_empty else list(repaired.exterior.coords), []


def classify_contours_by_containment(
    contours: list[list[tuple[float, float]]],
    *,
    touching_hole_note: str | None = None,
) -> tuple[list[ContourPart], list[str]]:
    """Groupe une liste de contours 2D bruts en composantes exterieures
    DISJOINTES (`ContourPart`), chacune avec ses propres trous, par
    confinement geometrique (aucune hypothese even-odd/nonzero).

    Un contour non contenu dans un autre est une nouvelle composante
    (racine). Un contour contenu dans une composante deja connue est un trou
    de cette composante. Les composantes sont triees par aire decroissante.

    Leve `ContourClassificationError` si `contours` est vide ou si aucun
    contour n'est exploitable (tous degeneres/aire nulle)."""
    warnings: list[str] = []
    if not contours:
        return [], warnings

    rings = []
    for pts in contours:
        try:
            poly = Polygon(pts)
        except Exception as exc:  # pragma: no cover - defensif
            raise ContourClassificationError(f"Contour invalide : {exc}") from exc
        if not poly.is_valid or poly.area == 0:
            continue
        rings.append((abs(poly.area), pts, poly))

    if not rings:
        raise ContourClassificationError("Aucun contour exploitable dans cette liste.")

    rings.sort(key=lambda r: r[0], reverse=True)

    # roots: liste de dicts {exterior, poly, holes} -- une entree par
    # composante exterieure disjointe deja identifiee.
    roots: list[dict] = []
    for area, pts, poly in rings:
        rep = poly.representative_point()
        containing_root = next((r for r in roots if r["poly"].contains(rep)), None)
        if containing_root is not None:
            containing_root["holes"].append(pts)
        else:
            roots.append({"exterior": pts, "poly": poly, "holes": []})

    parts: list[ContourPart] = []
    for root in roots:
        exterior_pts, holes = _repair_touching_hole(
            root["exterior"], root["holes"], warnings, touching_hole_note
        )
        parts.append(ContourPart(exterior=exterior_pts, holes=holes))

    return parts, warnings
