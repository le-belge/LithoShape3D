"""Chargement d'image depuis le disque. Aucune transformation ici."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def load_image(path: str | Path) -> Image.Image:
    return Image.open(path)
