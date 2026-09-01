"""Ressources de l'identite visuelle de LithoShape3D."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon


BRAND_NAME = "LithoShape3D"


def application_icon() -> QIcon:
    """Retourne l'embleme vectoriel de l'application, a toute taille."""
    return QIcon(str(Path(__file__).with_name("assets") / "lithoshape3d_mark.svg"))
