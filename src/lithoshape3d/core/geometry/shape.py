"""ShapeMask : ou l'objet physique existe, independamment de ou une Zone agit
(ZoneMask). Voir docstring de `core.scene.models.ShapeType`/`ShapeParams`.

`effective_zone_mask = zone_mask AND shape_mask` -- applique en composition
(core/geometry/composition.py), jamais ici : ce module ne construit qu'UN
masque, celui de la silhouette globale.

Toutes les formes integrees (RECTANGLE/CIRCLE/OVAL/HEART/STAR/TEXT) partagent
un seul contrat (`build_shape_mask(params, rows, cols) -> np.ndarray[bool]`)
-- pas cinq moteurs geometriques separes. SVG et IMAGE partagent eux aussi ce
contrat via `source_image_path` (un SVG est rasterise une fois a l'import,
voir ui/shape_svg_import.py, puis traite en tout point comme IMAGE)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

from lithoshape3d.core.scene.models import ShapeParams, ShapeType


def _rectangle_mask(rows: int, cols: int) -> np.ndarray:
    return np.ones((rows, cols), dtype=bool)


def _circle_mask(rows: int, cols: int) -> np.ndarray:
    yy, xx = np.mgrid[0:rows, 0:cols]
    cy, cx = (rows - 1) / 2.0, (cols - 1) / 2.0
    radius = min(rows, cols) / 2.0
    return ((yy - cy) ** 2 + (xx - cx) ** 2) <= radius**2


def _oval_mask(rows: int, cols: int) -> np.ndarray:
    yy, xx = np.mgrid[0:rows, 0:cols]
    cy, cx = (rows - 1) / 2.0, (cols - 1) / 2.0
    ry, rx = rows / 2.0, cols / 2.0
    return ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1.0


def _heart_mask(rows: int, cols: int) -> np.ndarray:
    """Equation implicite classique du coeur : (x^2+y^2-1)^3 - x^2*y^3 <= 0,
    normalisee dans [-1.2, 1.2] puis mise a l'echelle de la grille."""
    yy, xx = np.mgrid[0:rows, 0:cols].astype(np.float64)
    cy, cx = (rows - 1) / 2.0, (cols - 1) / 2.0
    scale = min(rows, cols) / 2.4
    x = (xx - cx) / scale
    y = -(yy - cy) / scale  # Y ecran vers le bas -> Y mathematique vers le haut
    return (x**2 + y**2 - 1.0) ** 3 - (x**2) * (y**3) <= 0.0


def _star_polygon(rows: int, cols: int, points: int = 5) -> list[tuple[float, float]]:
    cy, cx = rows / 2.0, cols / 2.0
    outer = min(rows, cols) / 2.0
    inner = outer * 0.382  # ratio etoile a 5 branches classique
    vertices = []
    for i in range(points * 2):
        angle = -np.pi / 2 + i * np.pi / points
        radius = outer if i % 2 == 0 else inner
        vertices.append((cx + radius * np.cos(angle), cy + radius * np.sin(angle)))
    return vertices


def _star_mask(rows: int, cols: int) -> np.ndarray:
    image = Image.new("1", (cols, rows), 0)
    draw = ImageDraw.Draw(image)
    draw.polygon(_star_polygon(rows, cols), fill=1)
    return np.asarray(image, dtype=bool)


def _fallback_font_path() -> str | None:
    """Police systeme raisonnable par plateforme -- pas de police embarquee
    (pas de dependance/licence supplementaire), l'utilisateur peut toujours
    fournir `ShapeParams.font_path` explicitement."""
    candidates: list[str]
    if sys.platform == "darwin":
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
    elif sys.platform == "win32":
        candidates = [
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    return None


def _text_mask(
    rows: int,
    cols: int,
    text: str,
    font_path: str | None,
    bold: bool,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> np.ndarray:
    """Rendu texte via Pillow (pas Qt : reste testable/headless, respecte la
    frontiere core/ sans Qt). Le texte est mis a l'echelle pour occuper au
    mieux la grille tout en preservant son ratio naturel."""
    if not text.strip():
        return np.zeros((rows, cols), dtype=bool)

    resolved_font_path = font_path or _fallback_font_path()
    if resolved_font_path is None:
        raise ValueError(
            "Aucune police disponible pour la forme Texte : fournissez "
            "ShapeParams.font_path explicitement (aucune police systeme trouvee)."
        )

    # dimensionne la police par recherche (Pillow n'a pas de "fit-to-box" natif)
    probe_size = 200
    font = ImageFont.truetype(resolved_font_path, probe_size)
    bbox = font.getbbox(text, stroke_width=2 if bold else 0)
    text_w, text_h = max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])
    margin = 0.9
    scale = min(cols * margin / text_w, rows * margin / text_h)
    font_size = max(4, int(probe_size * scale))
    font = ImageFont.truetype(resolved_font_path, font_size)
    bbox = font.getbbox(text, stroke_width=2 if bold else 0)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

    image = Image.new("L", (cols, rows), 0)
    draw = ImageDraw.Draw(image)
    origin = (
        (cols - text_w) / 2 - bbox[0] + offset_x * cols,
        (rows - text_h) / 2 - bbox[1] + offset_y * rows,
    )
    draw.text(origin, text, fill=255, font=font, stroke_width=2 if bold else 0, stroke_fill=255)
    return np.asarray(image, dtype=np.float32) / 255.0 >= 0.5


def build_shape_mask_from_image_array(alpha_or_gray: np.ndarray, rows: int, cols: int) -> np.ndarray:
    """IMAGE (et SVG rasterise) : oppose/blanc = interieur, transparent/noir
    = exterieur. `alpha_or_gray` deja resolue en un seul canal float [0,1]
    par l'appelant (canal alpha si present, sinon niveaux de gris)."""
    from lithoshape3d.core.image.preprocessing import resize_array

    resized = resize_array(alpha_or_gray.astype(np.float32), width_px=cols, height_px=rows)
    return resized >= 0.5


_BUILTIN_BUILDERS = {
    ShapeType.RECTANGLE: lambda rows, cols, params: _rectangle_mask(rows, cols),
    ShapeType.CIRCLE: lambda rows, cols, params: _circle_mask(rows, cols),
    ShapeType.OVAL: lambda rows, cols, params: _oval_mask(rows, cols),
    ShapeType.HEART: lambda rows, cols, params: _heart_mask(rows, cols),
    ShapeType.STAR: lambda rows, cols, params: _star_mask(rows, cols),
    ShapeType.TEXT: lambda rows, cols, params: _text_mask(
        rows, cols, params.text, params.font_path, params.bold, params.offset_x, params.offset_y
    ),
}


def build_shape_mask(params: ShapeParams, rows: int, cols: int) -> np.ndarray:
    """Point d'entree unique. IMAGE/SVG necessitent que l'appelant ait deja
    charge `params.source_image_path` (chemin non resolu ici : le bundle
    projet et le chemin absolu different, resolution laissee a l'appelant
    -- meme principe que Zone.mask_path)."""
    if params.shape_type in (ShapeType.IMAGE, ShapeType.SVG):
        raise ValueError(
            "build_shape_mask ne resout pas source_image_path lui-meme -- "
            "chargez l'image et appelez build_shape_mask_from_image_array."
        )
    builder = _BUILTIN_BUILDERS.get(params.shape_type)
    if builder is None:
        raise NotImplementedError(f"ShapeType {params.shape_type} non supporte")
    return builder(rows, cols, params)


def apply_border(mask: np.ndarray, border_width_px: float) -> np.ndarray:
    """Dilate la silhouette de `border_width_px` (suit le contour, cf.
    2.9) -- geometrie uniquement, pas de multi-materiau ici."""
    if border_width_px <= 0:
        return mask
    radius = max(1, round(border_width_px))
    return ndimage.binary_dilation(mask, iterations=radius)


def count_connected_components(mask: np.ndarray) -> int:
    """Nombre de composantes disjointes de la silhouette -- jamais reliees
    automatiquement (cf. 2.10), purement informatif pour l'UI."""
    _labeled, count = ndimage.label(mask)
    return int(count)
