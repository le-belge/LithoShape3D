"""Internationalisation (systeme Qt standard : fichiers .ts/.qm, QTranslator).

Le francais reste la langue source directement ecrite dans le code (tous
les textes passent par `self.tr(...)`, voir main_window.py et les
dialogues). Les traductions vivent dans `translations/*.ts` (source XML
editable) compiles en `.qm` (binaire charge au runtime) -- voir
`translations/README.md` pour regenerer apres un changement de texte.

Le choix de langue est persiste (comme le theme, voir theme.py) mais
s'applique au PROCHAIN lancement : reconstruire dynamiquement tous les
widgets deja crees demanderait un `changeEvent`/retranslateUi sur chaque
widget, non fait ici -- compromis assume pour rester simple.

Les .ts/.qm vivent dans `ui/translations/` (pas a la racine du depot) pour
etre embarques automatiquement par `collect_data_files("lithoshape3d")`
dans le packaging PyInstaller, comme `ui/assets/` -- voir
`packaging/lithoshape3d.spec`.
"""

from __future__ import annotations

from pathlib import Path

SUPPORTED_LANGUAGES = {"fr": "Francais", "en": "English"}
DEFAULT_LANGUAGE = "fr"

_SETTINGS_KEY_LANGUAGE = "language/code"

_TRANSLATIONS_DIR = Path(__file__).resolve().with_name("translations")


def stored_language() -> str:
    from PySide6.QtCore import QSettings

    value = QSettings().value(_SETTINGS_KEY_LANGUAGE, DEFAULT_LANGUAGE)
    if value not in SUPPORTED_LANGUAGES:
        return DEFAULT_LANGUAGE
    return value


def set_stored_language(code: str) -> None:
    from PySide6.QtCore import QSettings

    if code not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Langue non supportee : {code}")
    QSettings().setValue(_SETTINGS_KEY_LANGUAGE, code)


def install_translator(app, code: str) -> bool:
    """Installe le fichier .qm de `code` sur `app`. Ne fait rien pour le
    francais (langue source, aucun fichier necessaire). Retourne False si
    le fichier .qm attendu est introuvable (ex. app packagee sans les
    traductions embarquees) -- l'appelant retombe alors sur le francais
    sans planter."""
    if code == "fr":
        return True

    from PySide6.QtCore import QTranslator

    qm_path = _TRANSLATIONS_DIR / f"lithoshape3d_{code}.qm"
    if not qm_path.is_file():
        return False

    translator = QTranslator(app)
    if not translator.load(str(qm_path)):
        return False
    app.installTranslator(translator)
    # Garde une reference vivante sur l'app (QTranslator est autrement
    # collecte par le GC Python des la fin de cette fonction, ce qui
    # desinstallerait silencieusement la traduction).
    app._lithoshape3d_translator = translator
    return True
