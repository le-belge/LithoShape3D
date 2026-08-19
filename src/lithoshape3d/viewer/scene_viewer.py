"""Gestion de scene : camera, eclairage, affichage, interactions.

`SceneViewer` recoit un objet "plotter" (pyvista.Plotter ou
pyvistaqt.QtInteractor -- les deux exposent la meme API de rendu) par
injection de dependance : ceci permet de le tester avec un Plotter
off-screen, sans ouvrir de fenetre Qt. C'est le seul endroit du projet qui
dessine reellement ; il ne recalcule et ne repare jamais le mesh recu.

Convention des axes (identique a core/geometry/mesh_builder.py) :
    X = largeur, Y = hauteur (haut de l'image -> Y max), Z = epaisseur.
Toutes les vues utilisent Y comme axe "vertical" a l'ecran, sauf la vue de
dessus (ou Y est l'axe de visee).
"""

from __future__ import annotations

from enum import Enum

import trimesh

from lithoshape3d.viewer.adapter import mesh_to_polydata

BACKGROUND_COLOR = "#2b2b2b"
MESH_COLOR = "#e0dccb"

# vecteur camera (direction objet -> camera) et "up" ecran, par vue.
_VIEW_PRESETS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "front": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    "back": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
    "left": ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "right": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "top": ((0.0, 1.0, 0.0), (0.0, 0.0, -1.0)),
    "isometric": ((1.0, 1.0, 1.0), (0.0, 1.0, 0.0)),
}


class DisplayMode(Enum):
    SURFACE = "surface"
    WIREFRAME = "wireframe"
    SURFACE_WITH_EDGES = "surface_with_edges"


def _add_mesh_kwargs(display_mode: DisplayMode) -> dict:
    if display_mode is DisplayMode.WIREFRAME:
        return {"style": "wireframe", "color": MESH_COLOR}
    if display_mode is DisplayMode.SURFACE_WITH_EDGES:
        return {"style": "surface", "show_edges": True, "color": MESH_COLOR}
    return {"style": "surface", "show_edges": False, "color": MESH_COLOR}


class SceneViewer:
    def __init__(self, plotter) -> None:
        self.plotter = plotter
        self._mesh_actor = None
        self.plotter.set_background(BACKGROUND_COLOR)
        try:
            self.plotter.enable_anti_aliasing("msaa")
        except (AttributeError, RuntimeError, ValueError):
            pass  # non bloquant : selon le backend/l'environnement de rendu

    def show_mesh(self, mesh: trimesh.Trimesh, display_mode: DisplayMode = DisplayMode.SURFACE) -> None:
        """Affiche exactement le mesh fourni (aucune reparation, aucun recalcul)."""
        polydata = mesh_to_polydata(mesh)

        if self._mesh_actor is not None:
            self.plotter.remove_actor(self._mesh_actor)

        self._mesh_actor = self.plotter.add_mesh(
            polydata,
            smooth_shading=(display_mode is not DisplayMode.WIREFRAME),
            specular=0.3,
            specular_power=15,
            **_add_mesh_kwargs(display_mode),
        )
        self.plotter.reset_camera()

    def set_display_mode(self, mesh: trimesh.Trimesh, display_mode: DisplayMode) -> None:
        self.show_mesh(mesh, display_mode=display_mode)

    def _apply_view(self, name: str) -> None:
        vector, viewup = _VIEW_PRESETS[name]
        self.plotter.view_vector(vector, viewup=viewup)

    def view_front(self) -> None:
        self._apply_view("front")

    def view_back(self) -> None:
        self._apply_view("back")

    def view_left(self) -> None:
        self._apply_view("left")

    def view_right(self) -> None:
        self._apply_view("right")

    def view_top(self) -> None:
        self._apply_view("top")

    def view_isometric(self) -> None:
        self._apply_view("isometric")

    def reset_camera(self) -> None:
        """Recadre la camera sur le modele sans changer son orientation."""
        self.plotter.reset_camera()
