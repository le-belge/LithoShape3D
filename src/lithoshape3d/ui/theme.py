"""Theme centralise de LithoShape3D : gris anthracite, accents sobres.

Remplacable facilement : modifier les constantes de couleur ci-dessous (ou
substituer entierement `STYLESHEET`) sans toucher au reste de l'UI. Les
widgets "notables" (bouton d'action principale, banniere perimee) sont cibles
par `objectName` plutot que par une logique dispersee dans main_window.py.
"""

from __future__ import annotations

BACKGROUND = "#1e1f22"
SURFACE = "#26272b"
SURFACE_ALT = "#2e3034"
BORDER = "#3a3c40"
TEXT = "#e6e6e6"
TEXT_MUTED = "#9a9da3"
ACCENT = "#4fa3c7"
ACCENT_HOVER = "#63b6d9"
WARNING = "#d9a441"
DISABLED_TEXT = "#5c5f66"

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {BACKGROUND};
    color: {TEXT};
    font-size: 12px;
}}

QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 600;
    color: {TEXT_MUTED};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}

QPushButton {{
    background-color: {SURFACE_ALT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 14px;
    color: {TEXT};
}}
QPushButton:hover {{
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: {BORDER};
}}
QPushButton:disabled {{
    color: {DISABLED_TEXT};
    border-color: {BORDER};
}}

QPushButton#generateButton {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
    color: {BACKGROUND};
    font-weight: 600;
    padding: 7px 18px;
}}
QPushButton#generateButton:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton#generateButton:disabled {{
    background-color: {SURFACE_ALT};
    color: {DISABLED_TEXT};
    border-color: {BORDER};
}}

QLabel#previewLabel {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    background-color: {SURFACE};
    color: {TEXT_MUTED};
}}

QLabel#staleBanner {{
    color: {BACKGROUND};
    background-color: {WARNING};
    padding: 5px 10px;
    border-radius: 3px;
    font-weight: 600;
}}

QDoubleSpinBox, QComboBox, QLineEdit {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 3px 6px;
    color: {TEXT};
    min-height: 20px;
}}
QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}

QCheckBox {{
    spacing: 6px;
}}

QSplitter::handle {{
    background-color: {BORDER};
}}

QMenuBar {{
    background-color: {SURFACE};
    color: {TEXT};
}}
QMenu {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
}}
QMenu::item:selected {{
    background-color: {ACCENT};
    color: {BACKGROUND};
}}

QStatusBar {{
    background-color: {SURFACE};
    color: {TEXT_MUTED};
}}

QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 3px;
    background-color: {SURFACE};
    text-align: center;
    color: {TEXT};
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
}}
"""


def apply_theme(app) -> None:
    app.setStyleSheet(STYLESHEET)
