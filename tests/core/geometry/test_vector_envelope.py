"""Tests de `vector_envelope.weld_disjoint_components` -- soudure vectorielle
GENERIQUE de composantes disjointes (remplace la fermeture morphologique
pixel pour une source `.svg` en mode `artwork_envelope`)."""

from __future__ import annotations

from shapely.geometry import Polygon

from lithoshape3d.core.geometry.vector_envelope import weld_disjoint_components


def _square(x0, y0, size=10.0) -> Polygon:
    return Polygon([(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)])


def test_weld_already_touching_components_needs_no_buffer():
    a = _square(0, 0)
    b = _square(10, 0)  # touche exactement le bord droit de `a`
    result = weld_disjoint_components([a, b])

    assert result.weld_distance_mm == 0.0
    assert result.num_components_before == 1  # deja soudees par unary_union seul
    assert result.num_components_after == 1


def test_weld_disjoint_components_connects_them_with_measured_distance():
    a = _square(0, 0)
    b = _square(15, 0)  # ecart de 5mm entre les deux carres
    result = weld_disjoint_components([a, b])

    assert result.num_components_before == 2
    assert result.num_components_after == 1
    assert result.weld_distance_mm > 5.0  # >= ecart mesure + marge
    assert result.weld_distance_mm < 5.0 * 1.5  # marge raisonnable, pas demesuree
    assert result.polygon.is_valid


def test_weld_three_disjoint_components_uses_minimum_spanning_distance():
    """Trois carres alignes avec des ecarts DIFFERENTS (5mm puis 50mm) : la
    distance de soudure choisie doit rester proche du PLUS PETIT ecart
    necessaire pour TOUT connecter via un arbre couvrant (5mm), PAS du plus
    grand ecart present dans le nuage de points (ce qui prouve que l'algo
    utilise bien un MST minimax, pas juste la distance max/min brute entre
    toutes les paires)."""
    a = _square(0, 0, size=30.0)
    b = _square(35, 0, size=30.0)  # 5mm de a
    c = _square(85, 0, size=30.0)  # 20mm de b -- doit se souder via b, pas directement via a
    result = weld_disjoint_components([a, b, c])

    assert result.num_components_before == 3
    assert result.num_components_after == 1
    # Le MST connecte via l'arete la plus grande retenue (b<->c, 20mm) car
    # a<->b (5mm) est prise en premier par Kruskal -- donc d doit rester
    # ancre sur cet ecart (20mm), pas sur l'ecart direct a<->c (55mm, jamais
    # retenu par le MST) : des composantes plus "larges" (30mm ici, vs 10mm
    # dans le cas precedent) laissent une soudure robuste sans elargissement
    # iteratif significatif.
    assert 20.0 < result.weld_distance_mm < 35.0


def test_weld_does_not_shrink_below_original_union_when_nothing_to_weld():
    a = _square(0, 0)
    result = weld_disjoint_components([a])
    assert result.polygon.equals(a)
    assert result.weld_distance_mm == 0.0


def test_weld_preserves_a_hole_much_larger_than_the_gap():
    """Anneau (carre avec un trou carre au centre, cote 6mm) + un petit carre
    disjoint colle a 1mm -- la soudure necessaire (~1mm) doit rester tres en
    dessous de la demi-largeur du trou (3mm) : le trou ne doit PAS etre
    comble par le buffer +d/-d."""
    ring = Polygon(
        [(0, 0), (20, 0), (20, 20), (0, 20)],
        holes=[[(7, 7), (13, 7), (13, 13), (7, 13)]],
    )
    disjoint_piece = _square(21, 8, size=4.0)  # 1mm d'ecart avec le bord droit de `ring`
    result = weld_disjoint_components([ring, disjoint_piece])

    assert result.num_components_after == 1
    holes_after = sum(len(g.interiors) for g in (
        result.polygon.geoms if result.polygon.geom_type == "MultiPolygon" else [result.polygon]
    ))
    assert holes_after == 1, "Le trou (bien plus grand que l'ecart a souder) a ete comble a tort."
    assert not any("comble" in w or "reduit" in w for w in result.warnings)


def test_weld_warns_when_gap_is_comparable_to_a_hole_size():
    """Cas limite explicite : un trou MINUSCULE (cote 2mm) et un ecart a
    souder du meme ordre de grandeur -- le module doit AVERTIR (pas cacher
    silencieusement le risque) que ce trou peut etre affecte."""
    ring = Polygon(
        [(0, 0), (20, 0), (20, 20), (0, 20)],
        holes=[[(9, 9), (11, 9), (11, 11), (9, 11)]],  # trou 2x2mm
    )
    disjoint_piece = _square(23, 8, size=4.0)  # 3mm d'ecart, comparable au trou
    result = weld_disjoint_components([ring, disjoint_piece])

    assert any("trou" in w for w in result.warnings)
