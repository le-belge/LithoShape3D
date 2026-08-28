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
  imprimable, alors qu'un rejet bloquerait tout le mot. Reproduit et
  verifie par un test reel sur le "0" (zero) de la police systeme macOS
  `Andale Mono.ttf` (voir test_letter_glyph_extractor.py) : ce glyphe
  dessine le zero barre avec un anneau interne qui touche l'anneau externe
  au niveau de la barre oblique, produisant un `Polygon` invalide au sens
  Shapely avant reparation.
- Glyphe multi-composantes disjointes (point du "i"/"j", boucles du "%",
  double-point ":") : UNE lettre peut legitimement correspondre a PLUSIEURS
  contours exterieurs disjoints (aucun n'est contenu dans un autre), chacun
  pouvant lui-meme avoir ses propres trous. `LetterGlyph` modelise donc
  `parts: list[GlyphPart]` (1..n composantes) plutot qu'un unique
  exterieur+trous. La classification groupe les contours par confinement
  geometrique : les contours non contenus dans un autre sont des racines
  (une composante par racine), les contours contenus dans une racine
  deviennent ses trous. Le pipeline de generation (rasterisation, export
  DXF) traite alors la lettre comme l'UNION de toutes ses composantes -- un
  seul caisson "corps" par lettre, meme si son capot/sa silhouette a
  plusieurs ilots disjoints (comportement attendu pour un "i" ou un ":").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union
from shapely.validation import explain_validity

_CURVE_SAMPLES = 12  # segments par courbe -- suffisant pour l'impression 3D


class GlyphExtractionError(ValueError):
    """Glyphe absent, ouvert, ou autrement mal forme dans la police source."""


@dataclass
class GlyphPart:
    """Une composante exterieure disjointe d'un glyphe (ex: le rond du "i"
    OU sa barre verticale), avec ses propres trous internes eventuels."""

    exterior: list[tuple[float, float]]
    holes: list[list[tuple[float, float]]] = field(default_factory=list)

    def to_shapely(self) -> Polygon:
        return Polygon(self.exterior, holes=self.holes)


@dataclass
class LetterGlyph:
    character: str
    index: int
    parts: list[GlyphPart]
    """1..n composantes exterieures disjointes, en mm, referentiel ABSOLU du mot."""
    bbox_mm: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    advance_mm: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def exterior(self) -> list[tuple[float, float]]:
        """Compatibilite retro : exterieur de la premiere composante (la
        plus grande, par construction de `_classify_contours`)."""
        return self.parts[0].exterior

    @property
    def holes(self) -> list[list[tuple[float, float]]]:
        """Compatibilite retro : trous de la premiere composante uniquement.
        Pour les glyphes multi-composantes, prefer `parts` ou `to_shapely()`."""
        return self.parts[0].holes

    def to_shapely(self) -> Polygon | MultiPolygon:
        """Union de toutes les composantes -- represente le glyphe complet,
        y compris les parties disjointes (point du i/j, boucles du %)."""
        polygons = [part.to_shapely() for part in self.parts]
        if len(polygons) == 1:
            return polygons[0]
        return unary_union(polygons)


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


def _repair_touching_hole(
    exterior_pts: list[tuple[float, float]],
    holes: list[list[tuple[float, float]]],
    warnings: list[str],
) -> tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]:
    """Repare le cas degenere ou un trou touche le contour exterieur (fonts
    tres condensees) : fusionne via `buffer(0)` et avertit, plutot que de
    laisser un `Polygon` invalide au sens OGC se propager en aval."""
    candidate = Polygon(exterior_pts, holes=holes)
    if candidate.is_valid:
        return exterior_pts, holes

    reason = explain_validity(candidate)
    warnings.append(
        f"Trou interne touchant le contour exterieur detecte et fusionne "
        f"(police tres condensee) : {reason}."
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
            "La reparation du trou touchant le contour a scinde le glyphe en "
            "plusieurs morceaux ; seul le plus grand est conserve."
        )
        return list(largest.exterior.coords), [list(r.coords) for r in largest.interiors]
    return exterior_pts if repaired.is_empty else list(repaired.exterior.coords), []


def _classify_contours(
    contours: list[list[tuple[float, float]]],
) -> tuple[list[GlyphPart], list[str]]:
    """Groupe les contours d'un glyphe en composantes exterieures DISJOINTES
    (`GlyphPart`), chacune avec ses propres trous, par confinement
    geometrique (aucune hypothese even-odd/nonzero specifique a une police).

    Un contour non contenu dans un autre est une nouvelle composante
    (racine). Un contour contenu dans une composante deja connue est un trou
    de cette composante. Les composantes sont triees par aire decroissante
    (la plus grande, generalement le corps principal de la lettre, en
    premier -- utilise par les proprietes de compatibilite retro
    `LetterGlyph.exterior`/`.holes`)."""
    warnings: list[str] = []
    if not contours:
        return [], warnings

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

    parts: list[GlyphPart] = []
    for root in roots:
        exterior_pts, holes = _repair_touching_hole(root["exterior"], root["holes"], warnings)
        parts.append(GlyphPart(exterior=exterior_pts, holes=holes))

    return parts, warnings


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

        raw_parts, classify_warnings = _classify_contours(pen.contours)
        warnings.extend(f"Lettre '{char}' (#{index}) : {w}" for w in classify_warnings)

        def to_mm(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
            return [(x * scale + cursor_x_mm, y * scale) for x, y in pts]

        parts_mm = [
            GlyphPart(exterior=to_mm(part.exterior), holes=[to_mm(h) for h in part.holes])
            for part in raw_parts
        ]

        xs = [p[0] for part in parts_mm for p in part.exterior]
        ys = [p[1] for part in parts_mm for p in part.exterior]
        bbox = (min(xs), min(ys), max(xs), max(ys))

        letter_warnings: list[str] = []
        min_wall_mm = 0.4  # heuristique conservatrice, verifiee par l'appelant CLI
        # Largeur minimale a considerer : la composante la plus fine (ex. la
        # barre du "i") est le vrai facteur limitant pour l'epaisseur de
        # paroi, pas la bbox globale du glyphe.
        narrowest_part_mm = min(
            (max(p[0] for p in part.exterior) - min(p[0] for p in part.exterior)) for part in parts_mm
        )
        if 0 < narrowest_part_mm < min_wall_mm * 2:
            letter_warnings.append(
                f"Lettre '{char}' avec une composante tres fine ({narrowest_part_mm:.2f} mm) : "
                "l'epaisseur de paroi demandee risque de depasser sa largeur -- "
                "reduisez wall_thickness_mm ou augmentez font_size_mm."
            )
        if len(parts_mm) > 1:
            letter_warnings.append(
                f"Lettre '{char}' composee de {len(parts_mm)} composantes disjointes "
                "(ex. point de i/j, boucles de %) -- generees comme un seul caisson "
                "avec plusieurs ilots dans la silhouette."
            )

        letters.append(
            LetterGlyph(
                character=char,
                index=index,
                parts=parts_mm,
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
    for part in letter.parts:
        draw.polygon(mm_to_px(part.exterior), fill=1)
        for hole in part.holes:
            draw.polygon(mm_to_px(hole), fill=0)

    return np.array(image, dtype=bool)


def rasterize_polygon_mask(
    polygon,
    canvas_width_mm: float,
    canvas_height_mm: float,
    rows: int,
    cols: int,
) -> np.ndarray:
    """Rasterise un polygone Shapely arbitraire (`Polygon` ou `MultiPolygon`,
    typiquement derive d'un contour de lettre par `buffer()`) dans le meme
    referentiel canvas du mot entier que `rasterize_letter_mask`.

    Generalisation necessaire pour LightBox Letters avec epaulement : le
    capot doit etre rasterise depuis un contour RETRECI (cavite
    d'epaulement, cf. `lightbox_letters_export.py`), pas depuis le contour
    brut de la lettre -- pas de `LetterGlyph` disponible a ce stade, d'ou
    une fonction prenant directement une geometrie Shapely."""
    from PIL import Image, ImageDraw

    if rows <= 0 or cols <= 0:
        raise ValueError("rows/cols doivent etre > 0.")

    def mm_to_px(pts) -> list[tuple[float, float]]:
        return [
            (x / canvas_width_mm * (cols - 1), (canvas_height_mm - y) / canvas_height_mm * (rows - 1))
            for x, y in pts
        ]

    image = Image.new("1", (cols, rows), 0)
    draw = ImageDraw.Draw(image)
    if polygon is None or polygon.is_empty:
        return np.array(image, dtype=bool)

    geoms = list(polygon.geoms) if polygon.geom_type == "MultiPolygon" else [polygon]
    for geom in geoms:
        if geom.is_empty or geom.area <= 0:
            continue
        draw.polygon(mm_to_px(list(geom.exterior.coords)), fill=1)
        for hole in geom.interiors:
            draw.polygon(mm_to_px(list(hole.coords)), fill=0)

    return np.array(image, dtype=bool)
