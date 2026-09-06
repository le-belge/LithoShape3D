"""Theme LithoShape3D -- identite "Carbone + Lumiere + Prisme" (direction
V5E Strong Light), deux variantes (Carbon Glow sombre / Litho Lab clair)
partageant les memes accents turquoise/menthe/lilas/peche.

Remplacable facilement : modifier les palettes `DARK`/`LIGHT` ci-dessous
(ou `build_stylesheet`) sans toucher au reste de l'UI. Les widgets
"notables" (bouton d'action principale, banniere perimee, repere de
marque) sont cibles par `objectName` plutot que par une logique dispersee
dans main_window.py.
"""

from __future__ import annotations

from pathlib import Path

RADIUS_SMALL = 8
RADIUS_MEDIUM = 12

ACCENT_TURQUOISE = "#38DCD2"
ACCENT_TURQUOISE_HOVER = "#2BC9C0"
ACCENT_MINT = "#B8F3EA"
ACCENT_LILAC = "#D8D0FF"
ACCENT_PEACH = "#FFD6CB"
ACCENT_TEXT_ON_TURQUOISE = "#101820"
WARNING = "#b5790f"

# Palette "Carbon Glow" (sombre, identite par defaut).
DARK = {
    "background": "#101820",
    "surface": "#161F24",
    "surface_elevated": "#202B31",
    "text": "#F7FCFB",
    "text_muted": "#AFC4C8",
    "border": "#344249",
    "disabled_text": "#5A6C72",
}

# Palette "Litho Lab" (claire, au choix de l'utilisateur).
LIGHT = {
    "background": "#F7FCFB",
    "surface": "#FFFFFF",
    "surface_elevated": "#EEF8F8",
    "text": "#101820",
    "text_muted": "#53676E",
    "border": "#DDE8EA",
    "disabled_text": "#A1A3A8",
}

_CARBON_TEXTURE_PATH = (Path(__file__).with_name("assets") / "carbon_texture_dark.jpg").as_posix()


def build_stylesheet(dark: bool = True) -> str:
    palette = DARK if dark else LIGHT
    bg = palette["background"]
    surface = palette["surface"]
    surface_elevated = palette["surface_elevated"]
    text = palette["text"]
    text_muted = palette["text_muted"]
    border = palette["border"]
    disabled_text = palette["disabled_text"]

    # Repere de marque : accent carbone reel uniquement ici (zone "premium"),
    # jamais generalise a tout le theme -- voir integration-checklist.md
    # ("carbone utilise partout" est explicitement a eviter). En theme
    # clair, le repere reste sur une surface neutre (pas de carbone force
    # sur un fond clair).
    brand_lockup_rule = (
        f"""
QWidget#brandLockup {{
    background-image: url({_CARBON_TEXTURE_PATH});
    background-repeat: repeat;
    border: 1px solid rgba(56, 220, 210, 0.24);
    border-radius: {RADIUS_MEDIUM}px;
}}
"""
        if dark
        else f"""
QWidget#brandLockup {{
    background-color: {surface_elevated};
    border: 1px solid {border};
    border-radius: {RADIUS_MEDIUM}px;
}}
"""
    )

    return f"""
QMainWindow, QWidget {{
    background-color: {bg};
    color: {text};
    font-size: 12px;
    font-family: "Inter", "Avenir Next", "Segoe UI", sans-serif;
}}

QDialog {{
    background-color: {bg};
    color: {text};
}}

QGroupBox {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: {RADIUS_MEDIUM}px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 700;
    color: {text_muted};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}

QPushButton {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: {RADIUS_SMALL}px;
    padding: 6px 14px;
    color: {text};
    font-weight: 680;
}}
QPushButton:hover {{
    border-color: {ACCENT_TURQUOISE};
}}
QPushButton:pressed {{
    background-color: {surface_elevated};
}}
QPushButton:focus {{
    border: 2px solid {ACCENT_TURQUOISE};
}}
QPushButton:disabled {{
    color: {disabled_text};
    border-color: {border};
}}

QPushButton#generateButton {{
    background-color: {ACCENT_TURQUOISE};
    border: 1px solid {ACCENT_TURQUOISE};
    color: {ACCENT_TEXT_ON_TURQUOISE};
    font-weight: 760;
    padding: 7px 18px;
}}
QPushButton#generateButton:hover {{
    background-color: {ACCENT_TURQUOISE_HOVER};
}}
QPushButton#generateButton:disabled {{
    background-color: {surface_elevated};
    color: {disabled_text};
    border-color: {border};
}}

QLabel#previewLabel {{
    border: 1px solid {border};
    border-radius: {RADIUS_MEDIUM}px;
    background-color: {surface};
    color: {text_muted};
}}
{brand_lockup_rule}
QLabel#brandName {{
    color: {text};
    font-size: 17px;
    font-weight: 800;
}}

QLabel#aboutName {{
    color: {text};
    font-size: 18px;
    font-weight: 800;
}}
QLabel#aboutVersion {{
    color: {text_muted};
    font-size: 12px;
}}
QWidget#workflowIndicator {{
    background-color: {surface_elevated};
    border-bottom: 1px solid {border};
}}
QPushButton#workflowStep {{
    color: {text_muted};
    font-size: 11.5px;
    font-weight: 600;
    letter-spacing: 0.02em;
    background-color: transparent;
    border: none;
    padding: 2px 3px;
}}
QPushButton#workflowStep:hover {{
    color: {ACCENT_TURQUOISE_HOVER};
    text-decoration: underline;
}}
QPushButton#workflowStep[active="true"] {{
    color: {ACCENT_TURQUOISE};
}}
QLabel#workflowArrow {{
    color: {border};
    font-size: 11.5px;
}}

QLabel#aboutCopyright {{
    color: {text_muted};
    font-size: 11px;
}}

QLabel#staleBanner {{
    color: {ACCENT_TEXT_ON_TURQUOISE};
    background-color: {WARNING};
    padding: 5px 10px;
    border-radius: {RADIUS_SMALL}px;
    font-weight: 700;
}}

QDoubleSpinBox, QComboBox, QLineEdit {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: {RADIUS_SMALL}px;
    padding: 3px 6px;
    color: {text};
    min-height: 20px;
}}
QDoubleSpinBox:focus, QComboBox:focus, QLineEdit:focus {{
    border: 2px solid {ACCENT_TURQUOISE};
}}

QCheckBox {{
    spacing: 6px;
}}

QSplitter::handle {{
    background-color: {border};
}}

QMenuBar {{
    background-color: {surface};
    color: {text};
}}
QMenu {{
    background-color: {surface};
    color: {text};
    border: 1px solid {border};
}}
QMenu::item:selected {{
    background-color: {ACCENT_TURQUOISE};
    color: {ACCENT_TEXT_ON_TURQUOISE};
}}

QStatusBar {{
    background-color: {surface};
    color: {text_muted};
}}

QProgressBar {{
    border: 1px solid {border};
    border-radius: {RADIUS_SMALL}px;
    background-color: {surface};
    text-align: center;
    color: {text};
}}
QProgressBar::chunk {{
    background-color: {ACCENT_TURQUOISE};
}}
"""


# Conserve pour compatibilite (usage historique dans les tests) : la feuille
# par defaut correspond au theme sombre "Carbon Glow", identite principale.
STYLESHEET = build_stylesheet(dark=True)


def apply_theme(app, dark: bool = True) -> None:
    app.setStyleSheet(build_stylesheet(dark))


_SETTINGS_KEY_DARK_THEME = "theme/dark"


def stored_theme_is_dark() -> bool:
    """Sombre ("Carbon Glow") par defaut -- identite principale ; le clair
    ("Litho Lab") est un choix explicite de l'utilisateur, jamais impose."""
    from PySide6.QtCore import QSettings

    settings = QSettings()
    value = settings.value(_SETTINGS_KEY_DARK_THEME, True)
    if isinstance(value, str):
        return value.lower() not in ("false", "0", "")
    return bool(value)


def set_theme_dark(app, dark: bool) -> None:
    """Applique ET persiste le choix -- seul point d'entree pour changer de
    theme a chaud (voir main_window.py::_on_theme_changed)."""
    from PySide6.QtCore import QSettings

    apply_theme(app, dark)
    QSettings().setValue(_SETTINGS_KEY_DARK_THEME, dark)
