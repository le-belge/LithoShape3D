"""Panneau d'apercu 3D reutilisable, passif, pour les dialogues de
generation LightBox (`lightbox_letters_dialog.py`, `lightbox_image_dialog.py`).

Ce panneau ne recalcule JAMAIS de mesh : il se contente de charger les
fichiers STL deja exportes sur disque par la generation et de les afficher,
exactement comme `main_window.py` integre son propre `SceneViewer` (meme
`pyvistaqt.QtInteractor`, meme fond sombre). Aucune logique de generation
dupliquee ici.

Discipline de degradation : si `pyvistaqt`/VTK ne peut pas s'initialiser
(environnement sans rendu, ex. CI offscreen), le panneau se masque et
affiche un message a la place -- la generation et l'export ne doivent
jamais etre affectes par un echec de ce panneau, purement cosmetique."""

from __future__ import annotations

import logging
from pathlib import Path

import trimesh
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from lithoshape3d.viewer.scene_viewer import DisplayMode, SceneViewer

logger = logging.getLogger("lithoshape3d.ui.mesh_preview_panel")

_MIN_SIZE = 280


def _is_offscreen_platform() -> bool:
    """Detecte une session Qt sans affichage reel (`QT_QPA_PLATFORM=offscreen`,
    typiquement CI/tests) -- creer un vrai `QtInteractor` (VTK+GL) dans cet
    environnement peut faire planter le process (crash natif, pas une
    exception Python attrapable). Meme discipline que les tests du projet
    (`tests/ui/conftest.py`) qui injectent alors un `pv.Plotter(off_screen=True)`."""
    app = QApplication.instance()
    return bool(app is not None and app.platformName() == "offscreen")


class MeshPreviewPanel(QWidget):
    """Panneau Qt encapsulant un `SceneViewer`, avec repli propre si le
    rendu 3D interactif n'est pas disponible.

    `plotter` est injectable (meme pattern que `SceneViewer`/`MainWindow`) :
    en tests on peut passer un `pv.Plotter(off_screen=True)` directement.
    Sans injection explicite, un vrai `pyvistaqt.QtInteractor` est cree --
    sauf en plateforme Qt "offscreen" ou un plotter off-screen est utilise a
    la place (pas de widget interactif a afficher, mais `scene_viewer` reste
    fonctionnel pour les tests/verifications)."""

    def __init__(self, parent: QWidget | None = None, plotter=None) -> None:
        super().__init__(parent)
        self.scene_viewer: SceneViewer | None = None
        self._interactor_widget = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._status_label = QLabel("Apercu 3D indisponible dans cet environnement.")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setWordWrap(True)
        self._status_label.setMinimumSize(_MIN_SIZE, _MIN_SIZE)
        self._status_label.setStyleSheet("background-color: #2b2b2b; color: #ccc;")
        layout.addWidget(self._status_label, 1)

        try:
            if plotter is not None:
                self.scene_viewer = SceneViewer(plotter)
            elif _is_offscreen_platform():
                import pyvista as pv

                self.scene_viewer = SceneViewer(pv.Plotter(off_screen=True))
            else:
                from pyvistaqt import QtInteractor

                qt_plotter = QtInteractor(self)
                interactor_widget = getattr(qt_plotter, "interactor", None)
                if interactor_widget is None:
                    raise RuntimeError("QtInteractor sans widget Qt utilisable")
                interactor_widget.setMinimumSize(_MIN_SIZE, _MIN_SIZE)
                layout.addWidget(interactor_widget, 1)
                interactor_widget.setVisible(False)  # cache jusqu'au premier apercu reussi
                self._interactor_widget = interactor_widget
                self.scene_viewer = SceneViewer(qt_plotter)
        except Exception:
            logger.exception("Impossible d'initialiser l'apercu 3D (degrade proprement)")
            self.scene_viewer = None
            self._interactor_widget = None

    def show_stl_files(
        self,
        paths: list[Path],
        display_mode: DisplayMode = DisplayMode.SURFACE_WITH_EDGES,
    ) -> None:
        """Charge et affiche les fichiers STL donnes (concatenes en un seul
        mesh de scene pour un apercu visuel global -- pas d'union booleenne
        manifold, juste un rendu combine). Ne leve jamais : tout echec est
        journalise et affiche comme message dans le panneau, sans jamais
        impacter la generation/l'export qui a deja eu lieu."""
        if self.scene_viewer is None:
            return

        stl_paths = [p for p in paths if Path(p).suffix.lower() == ".stl"]
        if not stl_paths:
            self._show_message("Aucun fichier STL a previsualiser.")
            return

        try:
            meshes = [trimesh.load(str(p), force="mesh") for p in stl_paths]
            meshes = [m for m in meshes if m is not None and len(m.vertices) > 0]
            if not meshes:
                self._show_message("Aucun mesh valide a previsualiser.")
                return
            combined = meshes[0] if len(meshes) == 1 else trimesh.util.concatenate(meshes)
            self.scene_viewer.show_mesh(combined, display_mode=display_mode)
            self.scene_viewer.view_isometric()
        except Exception as exc:
            logger.exception("Echec de l'apercu 3D")
            self._show_message(f"Apercu 3D indisponible : {exc}")
            return

        self._status_label.setVisible(False)
        if self._interactor_widget is not None:
            self._interactor_widget.setVisible(True)

    def _show_message(self, text: str) -> None:
        self._status_label.setText(text)
        self._status_label.setVisible(True)
        if self._interactor_widget is not None:
            self._interactor_widget.setVisible(False)
