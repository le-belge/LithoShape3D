"""Soudure GENERIQUE de composantes vectorielles disjointes en une seule
enveloppe -- remplace, pour une source `.svg`, la fermeture morphologique en
PIXELS d'`artwork_shape_extractor.py` (`_search_min_closing_radius`,
recherche dichotomique d'un rayon en pixels sur un masque raster) par une
operation EN ESPACE VECTORIEL directement sur les polygones extraits par
`svg_path_extractor.py`.

Principe (aucune condition specifique a un cas -- meme regle appliquee a
n'importe quel jeu de composantes) :

  1. `shapely.unary_union` sur toutes les composantes -- soude gratuitement
     tout ce qui se touche/chevauche deja (aucun buffer necessaire).
  2. S'il reste plusieurs composantes disjointes dans le resultat, on
     construit un ARBRE COUVRANT DE POIDS MINIMAL (MST) sur le graphe
     complet des distances geometriques REELLES entre composantes
     (`shapely.distance`, PAS une estimation en pixels) : c'est le plus
     petit ensemble d'ecarts a combler pour connecter TOUTES les
     composantes en une seule, avec la distance de soudure la plus PETITE
     possible (un MST minimise par construction le plus grand ecart retenu
     parmi tous les arbres couvrants -- propriete "minimax" standard, cf.
     algorithme de Kruskal : trier les aretes par poids croissant et ne
     garder que celles qui connectent deux composantes encore separees).
  3. La distance de soudure choisie `d` = (le plus grand ecart du MST, donc
     le seul REELLEMENT necessaire pour tout connecter) x
     `(1 + margin_ratio)` (marge de securite FIXE, pas ajustee au cas par
     cas -- 15% par defaut, documente ci-dessous).
  4. `buffer(+d).buffer(-d)` (dilatation puis erosion, technique standard de
     "fermeture morphologique" mais ici en unites reelles mm sur une
     geometrie vectorielle exacte, pas sur un masque pixel) sur l'union
     complete -- soude exactement les composantes qui doivent l'etre, sans
     gonfler le reste du contour de plus que `d` (par construction d'un
     buffer +d/-d symetrique).

Garde-fou trous internes (voir docstring `weld_disjoint_components`) : un
buffer +d/-d peut aussi combler un trou interne dont la plus petite
dimension est <= ~2*d (un trou "avale" par la dilatation avant que l'erosion
ne puisse le "recreer"). On verifie explicitement, apres soudure, qu'aucun
trou n'a disparu par rapport a l'union brute (avant soudure) sauf ceux dont
la caracteristique geometrique (rayon inscrit approxime) etait deja <= d --
dans ce cas on avertit explicitement plutot que de le cacher."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

_DEFAULT_WELD_MARGIN_RATIO = 0.15
"""Marge de securite FIXE (15%) ajoutee a l'ecart minimal mesure entre les
composantes les plus proches restant a souder -- garantit que le buffer
utilise pour la soudure depasse legerement l'ecart reel (evite un echec de
soudure du a une imprecision numerique de la tessellation), sans etre un
multiplicateur ajuste au cas par cas (meme valeur pour toute forme)."""


def _explode(polygons: list[Polygon | MultiPolygon]) -> list[Polygon]:
    flat: list[Polygon] = []
    for geom in polygons:
        if geom.is_empty:
            continue
        if geom.geom_type == "MultiPolygon":
            flat.extend(g for g in geom.geoms if not g.is_empty and g.area > 0)
        elif geom.geom_type == "Polygon" and geom.area > 0:
            flat.append(geom)
    return flat


def _mst_max_edge(components: list[Polygon]) -> float:
    """Distance du plus grand arc retenu par l'arbre couvrant de poids
    minimal (Kruskal) sur le graphe complet des distances `shapely.distance`
    entre composantes -- c'est le SEUL ecart qui, une fois comble, garantit
    que TOUTES les composantes deviennent connectees (les ecarts plus petits
    sont deja combles par construction du MST)."""
    n = len(components)
    edges = sorted(
        (
            (components[i].distance(components[j]), i, j)
            for i, j in itertools.combinations(range(n), 2)
        ),
        key=lambda e: e[0],
    )
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    max_edge = 0.0
    connected = 1
    for dist, i, j in edges:
        ri, rj = find(i), find(j)
        if ri == rj:
            continue
        parent[ri] = rj
        max_edge = max(max_edge, dist)
        connected += 1
        if connected == n:
            break
    return max_edge


def _min_hole_characteristic_size(geom: Polygon | MultiPolygon) -> float:
    """Estimation grossiere mais suffisante de la plus petite "largeur" des
    trous internes d'une geometrie : demi-largeur de la boite englobante de
    chaque anneau interieur (min des deux dimensions / 2, approximation
    d'un "rayon inscrit" -- exacte pour un trou convexe proche d'une
    ellipse/rectangle, ce qui couvre l'immense majorite des trous de logo :
    interieur d'un "O", d'un anneau decoratif). Retourne `math.inf` si la
    geometrie n'a aucun trou (rien a proteger)."""
    geoms = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    best = math.inf
    for g in geoms:
        for interior in g.interiors:
            minx, miny, maxx, maxy = Polygon(interior).bounds
            size = min(maxx - minx, maxy - miny) / 2.0
            best = min(best, size)
    return best


@dataclass
class WeldResult:
    polygon: Polygon | MultiPolygon
    weld_distance_mm: float
    """Distance de buffer +d/-d effectivement appliquee (0.0 si les
    composantes etaient deja toutes connectees par simple union)."""
    num_components_before: int
    num_components_after: int
    warnings: list[str] = field(default_factory=list)


def weld_disjoint_components(
    polygons: list[Polygon | MultiPolygon],
    *,
    margin_ratio: float = _DEFAULT_WELD_MARGIN_RATIO,
) -> WeldResult:
    """Soude des composantes vectorielles disjointes en une seule enveloppe
    (voir docstring de module pour l'algorithme complet). Regle GENERIQUE,
    aucune condition specifique a un logo/une forme donnee : le meme code
    s'applique a un cercle, une etoile, un texte en arc, etc.

    Si l'union simple des composantes suffit deja (rien a souder), retourne
    cette union telle quelle avec `weld_distance_mm=0.0`."""
    flat = _explode(polygons)
    if not flat:
        return WeldResult(
            polygon=MultiPolygon([]),
            weld_distance_mm=0.0,
            num_components_before=0,
            num_components_after=0,
            warnings=["Aucune composante a souder (liste vide apres explosion)."],
        )

    warnings: list[str] = []
    union = unary_union(flat)
    union_pieces = (
        list(union.geoms) if union.geom_type == "MultiPolygon" else [union]
    )
    num_before = len(union_pieces)

    if num_before <= 1:
        return WeldResult(
            polygon=union,
            weld_distance_mm=0.0,
            num_components_before=num_before,
            num_components_after=num_before,
        )

    max_gap = _mst_max_edge(union_pieces)
    d = max_gap * (1.0 + margin_ratio)

    min_hole = _min_hole_characteristic_size(union)
    if d >= min_hole:
        warnings.append(
            f"Distance de soudure requise ({d:.3f}mm) proche ou superieure a la plus petite "
            f"dimension caracteristique d'un trou interne existant ({min_hole:.3f}mm) : ce trou "
            "risque d'etre partiellement ou totalement comble par l'operation de soudure. "
            "Verifiez visuellement le resultat."
        )

    # Le buffer(+d).buffer(-d) (fermeture morphologique standard) avec d =
    # ecart MST + marge est GEOMETRIQUEMENT suffisant pour que deux
    # composantes CONVEXES se touchent (elles se rejoignent exactement a la
    # distance d = ecart/2), mais un contact resultant d'un simple
    # tangentage (bulbe de dilatation qui touche en un "isthme" tres etroit)
    # peut ne pas survivre a l'erosion qui suit -- meme phenomene documente
    # dans `contour_classification._reunite_split_pieces` (un contact a un
    # seul point ne garantit pas une fusion topologique robuste). On
    # verifie donc le resultat et, si necessaire, on ELARGIT `d` (meme
    # marge relative, appliquee iterativement -- toujours une regle
    # GENERIQUE, pas un ajustement au cas par cas) jusqu'a connexite reelle
    # ou un plafond de securite.
    weld_widened = False
    welded = union.buffer(d).buffer(-d)
    attempts = 0
    while welded.geom_type == "MultiPolygon" and len(welded.geoms) > 1 and attempts < 6:
        d *= 1.0 + margin_ratio
        welded = union.buffer(d).buffer(-d)
        weld_widened = True
        attempts += 1

    if welded.is_empty:
        # Degenerescence numerique improbable (buffer +d/-d symetrique ne
        # devrait jamais vider une geometrie non vide) -- repli defensif sur
        # l'union non soudee plutot que de retourner une geometrie vide.
        warnings.append(
            f"La soudure vectorielle (d={d:.3f}mm) a produit une geometrie vide -- repli sur "
            "l'union non soudee (composantes restent disjointes)."
        )
        welded = union

    if weld_widened:
        warnings.append(
            f"La distance de soudure initiale (ecart MST mesure + marge) n'a pas suffi a fusionner "
            f"topologiquement toutes les composantes (contact trop etroit pour survivre a "
            f"l'erosion) : elargie iterativement (meme marge relative) jusqu'a d={d:.3f}mm."
        )

    welded_pieces = (
        list(welded.geoms) if welded.geom_type == "MultiPolygon" else [welded]
    )
    num_after = len(welded_pieces)

    holes_before = sum(len(g.interiors) for g in union_pieces)
    holes_after = sum(len(g.interiors) for g in welded_pieces)
    if holes_after < holes_before:
        warnings.append(
            f"La soudure vectorielle a reduit le nombre de trous internes ({holes_before} -> "
            f"{holes_after}) : au moins un trou dont la dimension caracteristique etait proche de "
            f"la distance de soudure (d={d:.3f}mm) a ete comble. Comportement attendu si ce trou "
            "etait deja signale ci-dessus comme a risque ; sinon, verifiez le resultat."
        )

    if num_after != 1:
        warnings.append(
            f"La soudure vectorielle (d={d:.3f}mm, marge {margin_ratio * 100:.0f}%) n'a pas suffi a "
            f"unifier toutes les composantes en une seule ({num_after} restantes) -- cas inattendu "
            "(le MST garantit theoriquement la connexite a cette distance) ; verifiez la geometrie "
            "source."
        )

    return WeldResult(
        polygon=welded,
        weld_distance_mm=d,
        num_components_before=num_before,
        num_components_after=num_after,
        warnings=warnings,
    )
