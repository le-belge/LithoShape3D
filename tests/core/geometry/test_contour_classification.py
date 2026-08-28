"""Regression tests pour `contour_classification.py` -- en particulier la
reparation d'un contour auto-intersectant (pincement local, ex. hole qui
touche son propre contour exterieur apres simplification) qui NE DOIT PAS
jeter silencieusement un morceau significatif du dessin.

Contexte reel qui a motive ces tests : `generate_lightbox_from_image(...,
shape_mode="artwork_envelope", cap_mode="flat_two_color", threshold_mode=
"auto")` sur `examples/physical_validation/thunderdome_source/
thunderdome_ref.png` produisait un `buffer(0)` de reparation qui scindait le
polygone d'encre en plusieurs morceaux et ne conservait QUE le plus grand --
amputant silencieusement un poing entier du dessin (~7.2% de l'aire totale,
confirme par capture BambuStudio). Voir aussi
`test_letter_glyph_extractor.py::test_hole_touching_exterior_is_repaired_on_real_font`
pour le cas d'origine (police tres condensee) qui a motive la reparation
generique elle-meme -- ces tests couvrent le raffinement qui evite qu'elle
ampute une composante reelle."""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from lithoshape3d.core.geometry.contour_classification import (
    _reunite_split_pieces,
    classify_contours_by_containment,
)


def _exterior_rectangle() -> list[tuple[float, float]]:
    """Rectangle exterieur simple (40x20 mm) -- VALIDE tout seul (contrairement
    a un contour deja auto-intersectant) : reproduit fidelement le cas reel,
    ou l'exterieur d'`envelope_mask`/`ink_mask` est deja une composante
    connexe propre (voir `artwork_shape_extractor.compute_envelope_mask`) et
    ou c'est la combinaison exterieur+trou (pas l'exterieur seul) qui devient
    invalide."""
    return [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)]


def _splitting_hole() -> list[tuple[float, float]]:
    """Trou qui traverse tout le rectangle de bas en haut et dont le bord
    superieur COINCIDE avec le bord superieur de l'exterieur (touche le
    contour exterieur) -- exactement le schema degenere du cas reel
    (fermeture morphologique + simplification `approxPolyDP` sur le dessin
    Thunderdome : `Self-intersection[125.06, 87.29]`, un trou qui touche le
    contour exterieur et dont la reparation naive scinde la forme en un gros
    morceau gauche ET un gros morceau droit, ~50/50 -- PAS un artefact de
    bruit ponctuel a jeter silencieusement)."""
    return [(18.0, 0.0), (22.0, 0.0), (22.0, 20.0), (18.0, 20.0)]


def _small_hole_inside_left_piece() -> list[tuple[float, float]]:
    """Petit trou bien a l'interieur du morceau GAUCHE (x < 18, loin du
    pincement) -- verifie que la reparation ressoudee preserve les trous
    internes legitimes plutot que de les engloutir (ce qu'un simple
    dilate/erode global sur toute la piece ferait, voir docstring de
    `_reunite_split_pieces`)."""
    return [(4.0, 8.0), (6.0, 8.0), (6.0, 10.0), (4.0, 10.0)]


def test_touching_hole_split_reunites_both_pieces_without_loss():
    contours = [
        _exterior_rectangle(),
        _splitting_hole(),
        _small_hole_inside_left_piece(),
    ]
    parts, warnings = classify_contours_by_containment(contours, touching_hole_note="test")

    assert len(parts) == 1, "les deux moities doivent former UNE seule composante ressoudee"
    polygon = parts[0].to_shapely()
    assert polygon.geom_type == "Polygon"

    # Aire attendue : rectangle 40x20 (800) moins le trou traversant 4x20
    # (80) moins le petit trou 2x2 (4) = 716. Le morceau droit (360 mm2,
    # ~45% de l'aire totale) NE DOIT PAS disparaitre silencieusement.
    assert polygon.area == pytest.approx(716.0, abs=1.0)
    assert len(parts[0].holes) == 1, "le petit trou interne du morceau gauche doit etre preserve"

    joined = " ".join(warnings)
    assert "pontage local" in joined or "ressouder" in joined
    assert "PERTE DE MATIERE" not in joined


def test_reunite_split_pieces_returns_none_when_pieces_are_truly_far_apart():
    """Deux polygones reellement disjoints et distants (pas un pincement
    local) ne doivent PAS etre pontes de force -- `_reunite_split_pieces`
    doit renoncer (retourne `None`) au-dela de son plafond de distance
    relative, laissant l'appelant emettre l'avertissement de perte de
    matiere plutot que de deformer massivement la silhouette."""
    left = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    far_right = Polygon([(1000, 0), (1001, 0), (1001, 1), (1000, 1)])
    assert _reunite_split_pieces([left, far_right]) is None


def test_reunite_split_pieces_bridges_a_single_point_touch():
    """Deux polygones qui ne se touchent qu'en un seul point (contact exact,
    gap == 0) doivent tout de meme etre pontes -- un simple `unary_union`
    sans pont ne garantit pas un `Polygon` unique pour un contact
    ponctuel (topologie degeneree), c'est precisement le cas reel
    (pincement `approxPolyDP`)."""
    left = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    right = Polygon([(10, 0), (20, 0), (20, -10), (10, -10)])
    assert left.distance(right) == 0.0

    result = _reunite_split_pieces([left, right])
    assert result is not None
    assert result.geom_type == "Polygon"
    assert result.area >= left.area + right.area - 1e-6
