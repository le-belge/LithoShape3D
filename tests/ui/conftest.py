import tempfile

import pytest
import pyvista as pv
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from lithoshape3d.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    # Isole TOUTE lecture/ecriture QSettings (theme, licence, ...) de la
    # suite dans un repertoire jetable -- jamais les vraies preferences de
    # la machine qui fait tourner les tests.
    settings_dir = tempfile.mkdtemp(prefix="lithoshape3d-test-settings-")
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, settings_dir)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    yield app


@pytest.fixture(autouse=True)
def _licensed_by_default(monkeypatch):
    """La quasi-totalite des tests UI existants exportent un STL sans se
    soucier de licence -- ce n'est pas leur sujet. Seuls les tests dedies a
    `core/licensing.py`/`license_dialog.py` (voir test_main_window.py et
    test_license_dialog.py) desactivent ce defaut pour exercer le blocage
    reel, sinon `_ensure_licensed_for_export` ouvrirait une vraie boite de
    dialogue modale (`LicenseDialog.exec()`) qui bloque indefiniment."""
    monkeypatch.setattr("lithoshape3d.ui.license_dialog.is_licensed", lambda: True)


@pytest.fixture
def main_window(qapp):
    """MainWindow avec un Plotter off-screen injecte : jamais de vraie
    fenetre Qt/VTK ouverte, jamais de crash lie a QT_QPA_PLATFORM."""
    window = MainWindow(plotter=pv.Plotter(off_screen=True))
    yield window
    window.plotter.close()
