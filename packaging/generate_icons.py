"""Genere les icones natives macOS et Windows depuis le SVG de marque.

Usage: ``python packaging/generate_icons.py`` depuis la racine du depot.
Requiert les dependances de developpement deja presentes dans le venv
(CairoSVG et Pillow).
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import struct

import cairosvg
from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
SOURCE_SVG = ROOT / "src/lithoshape3d/ui/assets/lithoshape3d_mark.svg"
OUTPUT_DIR = ROOT / "packaging/icons"
ICO_PATH = OUTPUT_DIR / "lithoshape3d.ico"
ICNS_PATH = OUTPUT_DIR / "lithoshape3d.icns"

_ICNS_CHUNKS = {
    16: b"icp4",
    32: b"icp5",
    64: b"icp6",
    128: b"ic07",
    256: b"ic08",
    512: b"ic09",
    1024: b"ic10",
}


def _raster(size: int) -> Image.Image:
    png = cairosvg.svg2png(url=str(SOURCE_SVG), output_width=size, output_height=size)
    return Image.open(BytesIO(png)).convert("RGBA")


def _png_bytes(size: int) -> bytes:
    buffer = BytesIO()
    _raster(size).save(buffer, format="PNG")
    return buffer.getvalue()


def _write_icns() -> None:
    """Ecrit le conteneur ICNS moderne (chunks PNG) sans ``iconutil``.

    Certaines versions macOS refusent de convertir un iconset, y compris un
    iconset qu'elles viennent elles-memes d'extraire. Le conteneur ICNS est
    simple et documente : un en-tete suivi de chunks PNG identifies par la
    taille native. Ainsi le packaging reste reproductible sur macOS et CI.
    """
    chunks = []
    for size, kind in _ICNS_CHUNKS.items():
        png = _png_bytes(size)
        chunks.append(kind + struct.pack(">I", len(png) + 8) + png)
    payload = b"".join(chunks)
    ICNS_PATH.write_bytes(b"icns" + struct.pack(">I", len(payload) + 8) + payload)


def main() -> None:
    if not SOURCE_SVG.is_file():
        raise FileNotFoundError(f"Logo source introuvable : {SOURCE_SVG}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    master = _raster(1024)
    master.save(
        ICO_PATH,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    _write_icns()

    print(f"Created {ICO_PATH.relative_to(ROOT)}")
    print(f"Created {ICNS_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
