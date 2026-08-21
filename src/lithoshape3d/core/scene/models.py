"""Modele de donnees Project / Scene / Zone.

Une Zone reference une image source et un masque optionnel plutot que de les
contenir : le pipeline image (core/image) reste responsable du chargement et
du pretraitement. mesh_cache_path est une reference vers un mesh genere sur
disque, jamais un mesh serialise dans le projet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4


class ReliefMode(Enum):
    LITHOPHANE = "lithophane"
    RELIEF = "relief"
    SOLID = "solid"


class CompositionMode(Enum):
    """Comment la contribution d'une Zone interagit avec le resultat deja
    compose (voir core/geometry/composition.py pour les formules exactes).
    Concept independant de ReliefMode (qui decrit comment la Zone transforme
    son image en relief). SUBTRACT reserve pour une phase future."""

    BASE = "base"
    ADD = "add"
    REPLACE = "replace"


@dataclass
class Transform:
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)


@dataclass
class Material:
    """Materiau/filament logique d'une Zone -- pour l'impression, pas pour le
    relief. Volontairement minimal (v0.3) : pas de base de donnees de
    filaments, juste de quoi partitionner la geometrie finale par materiau et
    l'exporter/l'afficher correctement. `name` sert de cle de regroupement
    (deux zones portant le meme `name` fusionnent en un seul corps exporte)."""

    name: str = "default"
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    filament_type: str | None = None
    translucent: bool = False
    slot: int | None = None
    """Index logique de slot filament (ex. position AMS) -- purement informatif
    cote LithoShape3D, l'affectation reelle se fait dans le slicer."""


class SupportType(Enum):
    NONE = "none"
    FLAT = "flat"
    REINFORCED = "reinforced"


@dataclass
class PrintSupport:
    """Pied/support imprime fusionne au modele pour le stabiliser sur le
    plateau (PAS un support de surplomb type slicer -- voir
    core/geometry/support.py). S'applique au resultat compose dans son
    ensemble, pas a une Zone individuelle."""

    support_type: SupportType = SupportType.NONE
    depth_mm: float = 25.0
    """Profondeur (etendue en Z) du pied -- volontairement bien plus grande
    que l'epaisseur fine de la lithophanie, pour donner une base stable."""
    height_mm: float = 8.0
    """Hauteur (etendue en Y) du pied, sous le bord bas du panneau."""
    overhang_left_mm: float = 5.0
    overhang_right_mm: float = 5.0
    rib_count: int = 3
    """Nombre de renforts/goussets -- utilise seulement si REINFORCED."""
    rib_thickness_mm: float = 2.0


class ShapeType(Enum):
    """Silhouette physique de l'objet compose (Scene entiere, pas une Zone).
    Independant de ReliefMode/CompositionMode/Material -- voir
    core/geometry/shape.py. SVG et IMAGE partagent le meme mecanisme
    (`ShapeParams.source_image_path`) : un SVG est rasterise une fois a
    l'import puis traite exactement comme une image alpha -- pas un
    sixieme moteur geometrique distinct."""

    RECTANGLE = "rectangle"
    CIRCLE = "circle"
    OVAL = "oval"
    HEART = "heart"
    STAR = "star"
    TEXT = "text"
    SVG = "svg"
    IMAGE = "image"


@dataclass
class ShapeParams:
    shape_type: ShapeType = ShapeType.RECTANGLE
    text: str = ""
    """Utilise si shape_type == TEXT."""
    font_path: str | None = None
    """Chemin (absolu ou relatif au bundle) vers un fichier .ttf/.otf.
    `None` = police de secours choisie automatiquement (voir
    core/geometry/shape.py:_fallback_font_path)."""
    bold: bool = False
    source_image_path: str | None = None
    """Utilise si shape_type in (SVG, IMAGE) : image alpha/N&B (opaque ou
    blanc = interieur, transparent ou noir = exterieur). Un SVG importe est
    rasterise une fois vers ce meme mecanisme (voir ui/shape_svg_import.py)."""
    border_width_mm: float = 0.0
    """Bordure geometrique qui suit le contour de la forme (dilatation) --
    0 = pas de bordure. Optionnellement multi-materiau (voir Zone.material) ;
    la geometrie fonctionne independamment de tout materiau assigne."""


@dataclass
class ImageTransform:
    """Cadrage de la photo A L'INTERIEUR de la Shape -- concept independant
    du zoom/pan de visualisation (qui ne modifie jamais rien de persistant,
    voir ui/mask_editor_dialog.py) et de toute transformation de geometrie
    3D. Coordonnees en fraction de la largeur/hauteur canonique de la Scene
    (pas des pixels ni des mm) : reste valide quels que soient resolution ou
    dimensions physiques choisies ensuite."""

    offset_x: float = 0.0
    offset_y: float = 0.0
    scale: float = 1.0
    rotation_deg: float = 0.0
    fit_mode: str = "fit"
    """"fill" | "fit" | "center" | "free" -- purement informatif/UX (quel
    bouton de cadrage a produit ces valeurs) ; le rendu utilise toujours
    offset/scale/rotation directement, jamais le mode en lui-meme."""


@dataclass
class GeometryParameters:
    width_mm: float
    height_mm: float
    min_thickness_mm: float = 0.8
    max_thickness_mm: float = 3.0
    invert: bool = False
    resolution: float = 0.3
    base_shape: str = "rectangle"


@dataclass
class Zone:
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = "zone"
    visible: bool = True
    source_image_path: str | None = None
    """Override rare et optionnel : une zone peut un jour referencer sa
    propre source (logo, texte rasterise, texture independante). Pour le
    workflow classique, reste a None et la zone utilise Scene.source_image_path."""
    mask_path: str | None = None
    geometry_params: GeometryParameters = field(
        default_factory=lambda: GeometryParameters(width_mm=100.0, height_mm=100.0)
    )
    material: Material = field(default_factory=Material)
    transform: Transform = field(default_factory=Transform)
    relief_mode: ReliefMode = ReliefMode.LITHOPHANE
    composition_mode: CompositionMode = CompositionMode.ADD
    """BASE pour une zone de fondation (typiquement la premiere), ADD par
    defaut pour toute nouvelle zone (cas le plus frequent : ajouter un
    element sur une base existante)."""
    mesh_cache_path: str | None = None


@dataclass
class Scene:
    zones: list[Zone] = field(default_factory=list)
    source_image_path: str | None = None
    """Image partagee par le workflow classique 1 image -> plusieurs zones."""
    active_zone_id: str | None = None
    support: PrintSupport = field(default_factory=PrintSupport)
    shape: ShapeParams = field(default_factory=ShapeParams)
    image_transform: ImageTransform = field(default_factory=ImageTransform)


@dataclass
class Project:
    name: str = "untitled"
    scene: Scene = field(default_factory=Scene)
    format_version: int = 5
