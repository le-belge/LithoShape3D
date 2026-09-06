"""Point d'entree de l'application graphique LithoShape3D."""

from __future__ import annotations

import sys

from lithoshape3d.ui.logging_config import configure_logging


def run_app() -> int:
    from PySide6.QtWidgets import QApplication

    from lithoshape3d.ui.branding import application_icon
    from lithoshape3d.ui.main_window import MainWindow
    from lithoshape3d.ui.theme import apply_theme, stored_theme_is_dark

    logger = configure_logging()
    logger.info("Lancement de LithoShape3D")

    app = QApplication.instance() or QApplication(sys.argv)
    # Force Fusion : le style natif "macOS" (QMacStyle) laisse le materiau
    # de fond systeme (clair) transparaitre derriere certains QDialog au
    # lieu du fond QSS (#101820 en theme sombre) -- constate concretement
    # sur AboutDialog/LicenseDialog une fois affiches en fenetre reelle
    # (invisible sur un rendu hors-ecran, uniquement sur le vrai widget a
    # l'ecran). Fusion applique la feuille de style a l'identique sur
    # toutes les plateformes, coherent avec une identite visuelle propre a
    # l'app plutot que des controles Aqua natifs melanges au theme carbone.
    app.setStyle("Fusion")
    app.setOrganizationName("LithoShape3D")
    app.setApplicationName("LithoShape3D")
    app.setWindowIcon(application_icon())
    app.setApplicationDisplayName("LithoShape3D")
    apply_theme(app, dark=stored_theme_is_dark())
    window = MainWindow()
    window.show()
    return app.exec()
