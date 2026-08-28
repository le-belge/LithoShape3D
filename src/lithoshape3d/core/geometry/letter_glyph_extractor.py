"""Extraction de glyphes lettre par lettre pour LightBox Letters.

Objectif : a partir d'un texte + d'une police (.ttf/.otf), produire un
contour vectoriel par lettre (exterieur ferme + 0..n trous internes), avec
sa position ABSOLUE dans le referentiel du mot entier (pas de recentrage
par lettre : necessaire pour un assemblage direct dans le slicer).

Decisions de conception (voir rapport de tache) :
- Extraction des contours via `fontTools.pens.basePen.BasePen`, qui
  decompose deja les segments quadratiques/cubiques multi-points (glyphes
  TrueType `glyf` ou CFF) en segments simples avant qu'on les echantillonne
  -- on n'a donc pas a reimplementer la resolution des points on-curve
  implicites de TrueType.
- Classification exterieur/trou : PAS de distinction even-odd/nonzero par
  type de police. On trie les contours d'un glyphe par aire decroissante et
  on applique un test de confinement geometrique (shapely) : un contour est
  un "trou" s'il est contenu dans un contour de plus grande aire deja
  classe exterieur. Ce choix evite de devoir determiner a l'avance la regle
  de remplissage de la police (TrueType et PostScript/CFF n'utilisent pas
  la meme convention de sens de parcours) et fonctionne pour les glyphes a
  plusieurs boucles (B, %, e) et les glyphes multi-parties sans trou (i, j,
  =, :).
- Trou touchant le contour exterieur (fonts tres condensees) : un polygone
  Shapely avec un trou qui touche/chevauche son propre exterieur est
  invalide au sens OGC. On detecte ce cas (`polygon.is_valid` est False, ou
  l'aire du polygone reparee par `buffer(0)` differe significativement de
  l'aire naive exterieur-trous) et on FUSIONNE (le trou est absorbe, donc
  disparait) via `buffer(0)`, en emettant un avertissement explicite. On ne
  rejette pas la lettre : un caisson sans cette contre-forme reste
  imprimable, alors qu'un rejet bloquerait tout le mot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from shapely.geometry import Polygon
from shapely.validation import explain_validity

_CURVE_SAMPLES = 12  # segments par courbe -- suffisant pour l'impression 3D


class GlyphExtractionError(ValueError):
    """Glyphe absent, ouvert, ou autrement mal forme dans la police source."""


@dataclass
class LetterGlyph:
    character: str
    index: int
    exterior: list[tuple[float, float]]
    """Contour exterieur ferme, en mm, dans le referentiel ABSOLU du mot."""
    holes: list[list[tuple[float, float]]] = field(default_factory=list)
    bbox_mm: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    advance_mm: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_shapely(self) -> Polygon:
        return Polygon(self.exterior, holes=self.holes)


@dataclass
class WordLayout:
    text: str
    font_path: str
    font_size_mm: float
    letters: list[LetterGlyph]
    width_mm: float
    height_mm: float
    warnings: list[str] = field(default_factory=list)


class _FlatteningPen(BasePen):
    """Accumule les contours d'un glyphe sous forme de listes de points
    (unites de police), en echantillonnant les courbes. `BasePen` decompose
    deja `curveTo`/`qCurveTo` multi-points en segments simples via
    `_curveToOne`/`_qCurveToOne` -- on n'a donc a gerer que le cas simple."""

    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.contours: list[list[tuple[float, float]]] = []
        self._current: list[tuple[float, float]] = []

    def _moveTo(self, pt):
        self._current = [pt]

    def _lineTo(self, pt):
        self._current.append(pt)

    def _curveToOne(self, pt1, pt2, pt3):
        p0 = np.array(self._current[-1])
        p1, p2, p3 = np.array(pt1), np.array(pt2), np.array(pt3)
        for i in range(1, _CURVE_SAMPLES + 1):
            t = i / _CURVE_SAMPLES
            point = (
                (1 - t) ** 3 * p0
                + 3 * (1 - t) ** 2 * t * p1
                + 3 * (1 - t) * t**2 * p2
                + t**3 * p3
            )
            self._current.append(tuple(point))

    def _qCurveToOne(self, pt1, pt2):
        p0 = np.array(self._current[-1])
        p1, p2 = np.array(pt1), np.array(pt2)
        for i in range(1, _CURVE_SAMPLES + 1):
            t = i / _CURVE_SAMPLES
            point = (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t**2 * p2
            self._current.append(tuple(point))

    def _closePath(self):
        if len(self._current) >= 3:
            self.contours.append(self._current)
        self._current = []

    def _endPath(self):
        # Glyphe ouvert (pas de closePath) : contour invalide pour un solide.
        if len(self._current) >= 2:
            raise GlyphExtractionError(
                "Glyphe avec un contour ouvert (aucun closePath) : "
                "la police source est mal formee pour une extrusion 3D."
            )


def _classify_contours(contours: list[list[tuple[float, float]]]) -> tuple[
    list[tuple[float, float]] | None, list[list[tuple[float, float]]], list[str]
]:
    """Trie les contours en (exterieur principal, trous), par confinement
    geometrique. Retourne aussi les avertissements de fusion trou/contour."""
    warnings: list[str] = []
    if not contours:
        return None, [], warnings

    rings = []
    for pts in contours:
        try:
            poly = Polygon(pts)
        except Exception as exc:  # pragma: no cover - defensif
            raise GlyphExtractionError(f"Contour de glyphe invalide : {exc}") from exc
        if not poly.is_valid or poly.area == 0:
            continue
        rings.append((abs(poly.area), pts, poly))

    if not rings:
        raise GlyphExtractionError("Aucun contour exploitable dans ce glyphe.")

    rings.sort(key=lambda r: r[0], reverse=True)
    exterior_area, exterior_pts, exterior_poly = rings[0]
    holes: list[list[tuple[float, float]]] = []

    for area, pts, poly in rings[1:]:
        rep = poly.representative_point()
        if exterior_poly.contains(rep):
            holes.append(pts)
        else:
            # Partie exterieure additionnelle (ex: point du "i", barre du
            # "=") : on l'ignore pour le contour principal -- non supporte
            # par ce module V1 (glyphe multi-composantes disjointes). On
            # documente plutot que de crasher.
            warnings.append(
                "Composante de glyphe disjointe ignoree (glyphe multi-parties "
                "non supporte en V1, ex. point de 'i'/'j')."
            )

    # Detection trou touchant le contour (degenere) : le polygone
    # exterieur-moins-trous doit rester un unique Polygon valide non
    # degenere. Sinon on fusionne (le trou est absorbe) et on avertit.
    candidate = Polygon(exterior_pts, holes=holes)
    if not candidate.is_valid:
        reason = explain_validity(candidate)
        warnings.append(
            f"Trou interne touchant le contour exterieur detecte et fusionne "
            f"(police tres condensee) : {reason}."
        )
        repaired = candidate.buffer(0)
        if repaired.geom_type == "Polygon" and list(repaired.interiors):
            holes = [list(ring.coords) for ring in repaired.interiors]
            exterior_pts = list(repaired.exterior.coords)
        else:
            # Fusion totale : plus de trou distinguable.
            holes = []

    return exterior_pts, holes, warnings


def extract_word_glyphs(
    text: str,
    font_path: str | Path,
    font_size_mm: float,
    letter_spacing_mm: float = 0.0,
) -> WordLayout:
    """Extrait un contour par lettre de `text`, positionne en absolu.

    `font_size_mm` correspond a la taille de corps (em) en mm : la mise a
    l'echelle utilise `unitsPerEm` de la police, comme un moteur de texte
    classique. Le kerning avance : ce module V1 utilise uniquement les
    largeurs d'avance `hmtx` (pas de table `kern`/GPOS) -- limitation
    documentee, acceptable pour un premier passage CLI.
    """
    if not text:
        raise ValueError("Le texte ne peut pas etre vide.")

    font_path = Path(font_path)
    if not font_path.exists():
        raise GlyphExtractionError(f"Police introuvable : {font_path}")

    try:
        tt_font = TTFont(str(font_path))
    except Exception as exc:
        raise GlyphExtractionError(f"Police illisible ou corrompue : {font_path} ({exc})") from exc

    units_per_em = tt_font["head"].unitsPerEm
    scale = font_size_mm / units_per_em
    glyph_set = tt_font.getGlyphSet()
    cmap = tt_font.getBestCmap()
    hmtx = tt_font["hmtx"]

    letters: list[LetterGlyph] = []
    warnings: list[str] = []
    cursor_x_mm = 0.0

    for index, char in enumerate(text):
        codepoint = ord(char)
        glyph_name = cmap.get(codepoint)
        if glyph_name is None:
            raise GlyphExtractionError(
                f"Caractere '{char}' (U+{codepoint:04X}) absent de la police {font_path.name}."
            )

        advance_units, _lsb = hmtx[glyph_name]
        advance_mm = advance_units * scale

        if char.isspace():
            cursor_x_mm += advance_mm + letter_spacing_mm
            continue

        pen = _FlatteningPen(glyph_set)
        try:
            glyph_set[glyph_name].draw(pen)
        except GlyphExtractionError:
            raise
        except Exception as exc:
            raise GlyphExtractionError(
                f"Glyphe mal forme pour le caractere '{char}' : {exc}"
            ) from exc

        if not pen.contours:
            raise GlyphExtractionError(
                f"Le caractere '{char}' n'a produit aucun contour (glyphe vide ou "
                "non trace) -- verifiez la police source."
            )

        exterior, holes, classify_warnings = _classify_contours(pen.contours)
        warnings.extend(f"Lettre '{char}' (#{index}) : {w}" for w in classify_warnings)

        def to_mm(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
            return [(x * scale + cursor_x_mm, y * scale) for x, y in pts]

        exterior_mm = to_mm(exterior)
        holes_mm = [to_mm(h) for h in holes]

        xs = [p[0] for p in exterior_mm]
        ys = [p[1] for p in exterior_mm]
        bbox = (min(xs), min(ys), max(xs), max(ys))

        letter_warnings: list[str] = []
        min_wall_mm = 0.4  # heuristique conservatrice, verifiee par l'appelant CLI
        glyph_width_mm = bbox[2] - bbox[0]
        if 0 < glyph_width_mm < min_wall_mm * 2:
            letter_warnings.append(
                f"Lettre '{char}' tres fine ({glyph_width_mm:.2f} mm) : l'epaisseur "
                "de paroi demandee risque de depasser la largeur du glyphe -- "
                "reduisez wall_thickness_mm ou augmentez font_size_mm."
            )

        letters.append(
            LetterGlyph(
                character=char,
                index=index,
                exterior=exterior_mm,
                holes=holes_mm,
                bbox_mm=bbox,
                advance_mm=advance_mm,
                warnings=letter_warnings,
            )
        )
        warnings.extend(f"Lettre '{char}' (#{index}) : {w}" for w in letter_warnings)
        cursor_x_mm += advance_mm + letter_spacing_mm

    if not letters:
        raise GlyphExtractionError("Aucune lettre imprimable dans le texte fourni.")

    for i in range(len(letters) - 1):
        a, b = letters[i], letters[i + 1]
        if a.bbox_mm[2] > b.bbox_mm[0]:
            warnings.append(
                f"Chevauchement de bbox detecte entre '{a.character}' (#{a.index}) et "
                f"'{b.character}' (#{b.index}) : verifiez l'espacement/la police."
            )

    max_x = max(letter.bbox_mm[2] for letter in letters)
    max_y = max(letter.bbox_mm[3] for letter in letters)
    min_y = min(letter.bbox_mm[1] for letter in letters)

    return WordLayout(
        text=text,
        font_path=str(font_path),
        font_size_mm=font_size_mm,
        letters=letters,
        width_mm=max_x,
        height_mm=max_y - min_y,
        warnings=warnings,
    )


def rasterize_letter_mask(
    letter: LetterGlyph,
    canvas_width_mm: float,
    canvas_height_mm: float,
    rows: int,
    cols: int,
) -> np.ndarray:
    """Rasterise UNE lettre dans un masque a la taille du CANVAS DU MOT
    ENTIER (pas de recentrage), convention Shape Composer (image, row0=haut).

    Reutilise PIL (deja dependance du projet via `core/geometry/shape.py`)
    plutot que de reimplementer un rasterizer polygonal."""
    from PIL import Image, ImageDraw

    if rows <= 0 or cols <= 0:
        raise ValueError("rows/cols doivent etre > 0.")

    def mm_to_px(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [
            (x / canvas_width_mm * (cols - 1), (canvas_height_mm - y) / canvas_height_mm * (rows - 1))
            for x, y in pts
        ]

    image = Image.new("1", (cols, rows), 0)
    draw = ImageDraw.Draw(image)
    draw.polygon(mm_to_px(letter.exterior), fill=1)
    for hole in letter.holes:
        draw.polygon(mm_to_px(hole), fill=0)

    return np.array(image, dtype=bool)
