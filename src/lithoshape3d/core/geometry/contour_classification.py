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

from dataclasses import dataclass, field

from shapely.geometry import Polygon
from shapely.validation import explain_validity


class ContourClassificationError(ValueError):
    """Aucun contour exploitable dans la liste fournie (vide, tous
    degeneres/aire nulle, ou geometrie invalide et irreparable)."""


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
        largest = max(repaired.geoms, key=lambda g: g.area)
        warnings.append(
            "La reparation du trou touchant le contour a scinde la forme en "
            "plusieurs morceaux ; seul le plus grand est conserve."
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
