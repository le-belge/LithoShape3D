import pytest
import pyvista as pv
from PySide6.QtWidgets import QApplication

from lithoshape3d.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def main_window(qapp):
    """MainWindow avec un Plotter off-screen injecte : jamais de vraie
    fenetre Qt/VTK ouverte, jamais de crash lie a QT_QPA_PLATFORM."""
    window = MainWindow(plotter=pv.Plotter(off_screen=True))
    yield window
    window.plotter.close()
