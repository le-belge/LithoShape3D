"""Point d'entree de l'application graphique LithoShape3D."""

from __future__ import annotations

import sys

from lithoshape3d.ui.logging_config import configure_logging


def run_app() -> int:
    from PySide6.QtWidgets import QApplication

    from lithoshape3d.ui.branding import application_icon
    from lithoshape3d.ui.main_window import MainWindow
    from lithoshape3d.ui.theme import apply_theme

    logger = configure_logging()
    logger.info("Lancement de LithoShape3D")

    app = QApplication.instance() or QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    app.setApplicationDisplayName("LithoShape3D")
    apply_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()
