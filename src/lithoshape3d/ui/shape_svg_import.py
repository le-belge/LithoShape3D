"""Import SVG comme Shape (v0.4) : rasterise une fois via QtSvg (deja une
dependance du projet -- pas de parseur SVG maison, cf. mission) puis traite
exactement comme une Shape IMAGE ensuite (meme mecanisme, un seul moteur
"image alpha" pour SVG et IMAGE -- voir core/geometry/shape.py).

Volontairement dans ui/ (pas core/) : QtSvg est Qt, et core/ ne doit jamais
importer Qt (cf. tests/test_architecture_boundaries.py)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

_RASTER_SIZE = 1024


def rasterize_svg_to_alpha_png(svg_path: str) -> str:
    """Rasterise `svg_path` vers un PNG RGBA carre (`_RASTER_SIZE`), fond
    transparent -- oppose/blanc = interieur, transparent = exterieur (meme
    convention que ShapeType.IMAGE). Ecrit dans un fichier temporaire ;
    l'appelant (MainWindow) le fait ensuite copier dans le bundle projet a
    la sauvegarde, comme n'importe quelle autre source externe."""
    renderer = QSvgRenderer(svg_path)
    if not renderer.isValid():
        raise ValueError(f"SVG invalide ou illisible : {svg_path}")

    view_box = renderer.viewBoxF()
    if view_box.width() > 0 and view_box.height() > 0:
        aspect = view_box.width() / view_box.height()
    else:
        aspect = 1.0

    if aspect >= 1.0:
        width, height = _RASTER_SIZE, max(1, round(_RASTER_SIZE / aspect))
    else:
        width, height = max(1, round(_RASTER_SIZE * aspect)), _RASTER_SIZE

    image = QImage(_RASTER_SIZE, _RASTER_SIZE, QImage.Format.Format_ARGB32)
    image.fill(0)  # transparent = exterieur

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    x = (_RASTER_SIZE - width) // 2
    y = (_RASTER_SIZE - height) // 2
    renderer.render(painter, image.rect().adjusted(x, y, -x, -y))
    painter.end()

    stem = Path(svg_path).stem
    fd, out_path = tempfile.mkstemp(prefix=f"{stem}_", suffix=".png")
    os.close(fd)
    if not image.save(out_path, "PNG"):
        raise ValueError(f"Echec de l'ecriture du PNG rasterise depuis : {svg_path}")
    return out_path
