"""Theme centralise de LithoShape3D : gris clair, accents sobres.

Remplacable facilement : modifier les constantes de couleur ci-dessous (ou
substituer entierement `STYLESHEET`) sans toucher au reste de l'UI. Les
widgets "notables" (bouton d'action principale, banniere perimee) sont cibles
par `objectName` plutot que par une logique dispersee dans main_window.py.
"""

from __future__ import annotations

BACKGROUND = "#f2f2f4"
SURFACE = "#ffffff"
SURFACE_ALT = "#e8e9ec"
BORDER = "#c9cad0"
TEXT = "#202124"
TEXT_MUTED = "#5f6368"
ACCENT = "#157C89"
ACCENT_HOVER = "#0F92A1"
BRAND_INK = "#15232C"
BRAND_CORAL = "#E74B4B"
WARNING = "#b5790f"
DISABLED_TEXT = "#a1a3a8"

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

QWidget#brandLockup {{
    background-color: transparent;
}}
QLabel#brandName {{
    color: {BRAND_INK};
    font-size: 17px;
    font-weight: 700;
}}

QLabel#aboutName {{
    color: {BRAND_INK};
    font-size: 18px;
    font-weight: 700;
}}
QLabel#aboutVersion {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QLabel#aboutCopyright {{
    color: {TEXT_MUTED};
    font-size: 11px;
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
