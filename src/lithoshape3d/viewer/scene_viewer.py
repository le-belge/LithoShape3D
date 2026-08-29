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

import numpy as np
import trimesh
from matplotlib.colors import LinearSegmentedColormap

from lithoshape3d.viewer.adapter import mesh_to_polydata

BACKGROUND_COLOR = "#d9dade"
MESH_COLOR = "#8a8672"
BACKLIGHT_BACKGROUND_COLOR = "#0a0a0c"
BACKLIGHT_DARK_COLOR = "#0c0600"  # matiere epaisse : peu de lumiere transmise
BACKLIGHT_BRIGHT_COLOR = "#fffaf0"  # matiere fine : lumiere transmise, "glow"

_BACKLIGHT_BRIGHTNESS_FLOOR = 0.04
"""Luminosite minimale meme pour l'epaisseur la plus forte : une vraie
lithophanie epaisse laisse toujours deviner un peu de lumiere, jamais un
noir pur."""
_BACKLIGHT_ATTENUATION_K = 4.5
"""Coefficient d'attenuation (type loi de Beer-Lambert, brightness =
exp(-k * epaisseur_normalisee)) : plus k est grand, plus le contraste entre
zones fines (lumineuses) et zones epaisses (sombres) est marque."""

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
    BACKLIGHT_PREVIEW = "backlight_preview"
    MATERIALS = "materials"
    """Ce mode ne passe pas par `show_mesh` (il montre plusieurs corps, pas
    un seul) -- voir `SceneViewer.show_material_meshes`. Reste dans cette
    enum pour partager le meme combo d'affichage cote UI."""


def _add_mesh_kwargs(display_mode: DisplayMode) -> dict:
    if display_mode is DisplayMode.WIREFRAME:
        return {"style": "wireframe", "color": MESH_COLOR}
    if display_mode is DisplayMode.SURFACE_WITH_EDGES:
        return {"style": "surface", "show_edges": True, "color": MESH_COLOR}
    return {"style": "surface", "show_edges": False, "color": MESH_COLOR}


def _backlight_brightness_from_z(points: np.ndarray, z_max_override: float | None = None) -> np.ndarray:
    """Approxime la luminosite transmise par sommet a partir de l'epaisseur
    locale, comme une lithophanie photographiee retro-eclairee.

    Convention mesh_builder.py : face arriere plane a Z=0, face avant a
    Z=epaisseur locale -- donc la coordonnee Z d'un sommet EST directement
    l'epaisseur de matiere a cet endroit (pas d'interpolation a faire, les
    parois laterales ne portent que les valeurs 0 ou epaisseur). Attenuation
    de type Beer-Lambert (exponentielle) : fin = lumineux, epais = sombre.

    `z_max_override` : quand un pied d'impression est fusionne au modele, sa
    propre profondeur (souvent bien plus grande que l'epaisseur fine de la
    lithophanie, cf. core/geometry/support.py) fausserait la normalisation si
    elle etait recalculee sur le mesh complet -- on passe alors l'epaisseur
    max du panneau SEUL (avant fusion du pied), ce qui a pour effet
    secondaire voulu de rendre le pied uniformement tres sombre (il n'est pas
    cense faire partie de l'image retro-eclairee).

    Volontairement un mappage epaisseur -> couleur (pas une vraie
    transparence alpha) : avec un vrai blending alpha sur fond sombre, une
    zone fine se fond vers le fond NOIR (donc s'assombrit) au lieu de
    "briller" -- l'inverse de l'effet recherche. Le mappage en couleur
    reproduit fidelement ce que montre une vraie photo retro-eclairee, quel
    que soit l'angle de vue en orbite."""
    z = points[:, 2]
    z_min = 0.0  # convention : le dos est toujours a Z=0
    z_max = z_max_override if z_max_override is not None else float(z.max())
    if z_max - z_min < 1e-9:
        return np.full(len(z), 0.5)
    normalized = np.clip((z - z_min) / (z_max - z_min), 0.0, None)
    attenuated = np.exp(-_BACKLIGHT_ATTENUATION_K * normalized)
    return _BACKLIGHT_BRIGHTNESS_FLOOR + attenuated * (1.0 - _BACKLIGHT_BRIGHTNESS_FLOOR)


class SceneViewer:
    def __init__(self, plotter) -> None:
        self.plotter = plotter
        self._mesh_actor = None
        self._material_actors: list = []
        self.plotter.set_background(BACKGROUND_COLOR)
        try:
            self.plotter.enable_anti_aliasing("msaa")
        except (AttributeError, RuntimeError, ValueError):
            pass  # non bloquant : selon le backend/l'environnement de rendu

    def _clear_actors(self) -> None:
        if self._mesh_actor is not None:
            self.plotter.remove_actor(self._mesh_actor)
            self._mesh_actor = None
        for actor in self._material_actors:
            self.plotter.remove_actor(actor)
        self._material_actors = []

    def show_mesh(
        self,
        mesh: trimesh.Trimesh,
        display_mode: DisplayMode = DisplayMode.SURFACE,
        panel_z_max: float | None = None,
    ) -> None:
        """Affiche exactement le mesh fourni (aucune reparation, aucun recalcul).

        `panel_z_max` : voir `_backlight_brightness_from_z` -- ignore hors
        mode BACKLIGHT_PREVIEW."""
        self._clear_actors()

        if display_mode is DisplayMode.BACKLIGHT_PREVIEW:
            self._show_backlight_preview(mesh, panel_z_max)
        else:
            self._show_normal(mesh, display_mode)

        self.plotter.reset_camera()

    def show_material_meshes(
        self, material_meshes: dict[str, tuple[trimesh.Trimesh, tuple[float, float, float]]]
    ) -> None:
        """Affiche plusieurs corps simultanement, chacun dans sa couleur
        logique -- pour verifier visuellement la repartition des materiaux,
        pas pour simuler precisement un rendu de filament reel."""
        self._clear_actors()
        self.plotter.set_background(BACKGROUND_COLOR)
        self.plotter.remove_all_lights()
        self.plotter.enable_lightkit()

        for mesh, color in material_meshes.values():
            polydata = mesh_to_polydata(mesh)
            actor = self.plotter.add_mesh(
                polydata,
                style="surface",
                show_edges=False,
                color=color,
                smooth_shading=True,
                specular=0.3,
                specular_power=15,
            )
            self._material_actors.append(actor)

        self.plotter.reset_camera()

    def _show_normal(self, mesh: trimesh.Trimesh, display_mode: DisplayMode) -> None:
        self.plotter.set_background(BACKGROUND_COLOR)
        self.plotter.remove_all_lights()
        self.plotter.enable_lightkit()

        polydata = mesh_to_polydata(mesh)
        self._mesh_actor = self.plotter.add_mesh(
            polydata,
            smooth_shading=(display_mode is not DisplayMode.WIREFRAME),
            specular=0.3,
            specular_power=15,
            **_add_mesh_kwargs(display_mode),
        )

    def _show_backlight_preview(self, mesh: trimesh.Trimesh, panel_z_max: float | None = None) -> None:
        """Approxime le rendu d'une lithophanie retro-eclairee, photographiee
        avec une lumiere derriere : la luminosite de chaque sommet est
        derivee de l'epaisseur locale (voir `_backlight_brightness_from_z`)
        et appliquee comme couleur (pas comme transparence -- cf. note dans
        cette fonction). Un eclairage doux et majoritairement ambiant garde
        le relief perceptible en orbite 3D sans ecraser le degrade de
        luminosite qui porte l'essentiel de l'information. Approximation
        visuelle -- pas une simulation physique de transmission lumineuse
        (pas de raytracing/subsurface scattering)."""
        self.plotter.set_background(BACKLIGHT_BACKGROUND_COLOR)
        self.plotter.remove_all_lights()
        self.plotter.enable_lightkit()

        polydata = mesh_to_polydata(mesh)
        polydata["brightness"] = _backlight_brightness_from_z(polydata.points, panel_z_max)
        cmap = LinearSegmentedColormap.from_list(
            "litho_backlight", [BACKLIGHT_DARK_COLOR, BACKLIGHT_BRIGHT_COLOR]
        )

        self._mesh_actor = self.plotter.add_mesh(
            polydata,
            style="surface",
            show_edges=False,
            scalars="brightness",
            cmap=cmap,
            clim=(0.0, 1.0),
            show_scalar_bar=False,
            opacity=1.0,
            smooth_shading=True,
            ambient=0.35,
            diffuse=0.75,
            specular=0.08,
            specular_power=8,
        )

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
