"""Modele de donnees Project / Scene / Zone.

Une Zone reference une image source et un masque optionnel plutot que de les
contenir : le pipeline image (core/image) reste responsable du chargement et
du pretraitement. mesh_cache_path est une reference vers un mesh genere sur
disque, jamais un mesh serialise dans le projet.
"""

from __future__ import annotations

import warnings
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


class ColorStrategy(Enum):
    """Comment une Zone destinee a un materiau/couleur distinct affecte (ou
    non) la geometrie partagee (v0.4.1). Concept independant de ReliefMode/
    CompositionMode -- voir core/geometry/composition.py pour l'effet exact.

    `None` (valeur par defaut de `Zone.color_strategy`, PAS un membre de cet
    enum) signifie "aucune strategie couleur" : la Zone garde le comportement
    historique ADD/REPLACE/BASE + ReliefMode, une contribution geometrique
    reelle (ex. relief grave). Des qu'une des valeurs ci-dessous est
    positionnee, la Zone est EXCLUE de la composition du champ de hauteur
    partage (`compose_scene_heightfield`) -- son ReliefMode/CompositionMode
    propres deviennent alors sans effet sur la geometrie visible, seule son
    appartenance materiau (et, pour BACKLIGHT_INSERT, sa cavite/insert)
    compte. Garantit qu'assigner un materiau ne modifie jamais implicitement
    la surface (cf. mission 0.4.1, bug de la rose en sur-relief)."""

    MATERIAL_ONLY = "material_only"
    """La Zone partage EXACTEMENT la geometrie deja composee par les autres
    zones a cet endroit -- seule la partition materiau change, aucune
    difference de surface avant/apres selection."""

    BACKLIGHT_INSERT = "backlight_insert"
    """Comme MATERIAL_ONLY pour la surface avant (aucune bosse), mais en
    plus : une fine peau blanche est conservee en facade et un insert
    colore independant est genere derriere, pour un rendu retro-eclaire
    colore sans modifier la facade eteinte -- voir core/geometry/backlight.py."""


MIN_BACKLIGHT_WALL_THICKNESS_MM = 0.60
"""Plancher commun a `white_skin_thickness_mm` ET `insert_thickness_mm`
(retour terrain post-0.4.1, cf. echange de commercialisation Backlight
Insert) : sous ~0.5mm en FDM (buse 0.4mm, 2 parois), la peau/l'insert
deviennent trop fragiles a l'impression et au demoulage/assemblage --
0.6mm (= 2 couches de paroi confortables avec la plupart des profils) est
le minimum recommande avant validation par de vraies impressions. Pas
impose de force (on ne corrige jamais silencieusement une valeur choisie
par l'utilisateur) : `BacklightInsertParams.__post_init__` emet un
avertissement `UserWarning` explicite en dessous de ce plancher, meme
esprit que les avertissements "jamais silencieux" de backlight.py."""


@dataclass
class BacklightInsertParams:
    """Parametres du mode BACKLIGHT_INSERT (v0.4.1) -- toutes les valeurs
    par defaut sont EXPERIMENTALES (a valider par de vraies impressions,
    cf. mission), pas des constantes physiquement optimales."""

    white_skin_thickness_mm: float = MIN_BACKLIGHT_WALL_THICKNESS_MM
    """Remonte de 0.40mm (defaut 0.4.1 initial) a 0.60mm : retour terrain
    montrant qu'une peau plus fine se fissure/se voile facilement en FDM
    et a la manipulation avant assemblage avec l'insert -- alignee sur
    `MIN_BACKLIGHT_WALL_THICKNESS_MM`, le meme plancher que l'insert."""
    insert_thickness_mm: float = 0.60
    """Milieu de la plage recommandee par la mission (0.40-0.80mm) : assez
    epais pour rester manipulable/imprimable independamment, assez fin pour
    laisser passer la lumiere en retro-eclairage. Deja egal au plancher
    `MIN_BACKLIGHT_WALL_THICKNESS_MM` -- ne pas descendre en dessous."""
    xy_clearance_mm: float = 0.20
    """Jeu lateral (pas en profondeur) entre le contour de l'insert et la
    paroi de la cavite qui l'accueille, pour qu'il s'insere sans forcer.
    Presets : Serre=0.10, Standard=0.20 (par defaut), Facile=0.30."""
    pocket_extra_depth_mm: float = 0.08
    """Surepaisseur (mm) de la poche creusee au dos par rapport a
    `insert_thickness_mm` -- `pocket_depth = insert_thickness_mm +
    pocket_extra_depth_mm`. Contrairement a l'ancienne cavite (qui suivait
    le relief local jusqu'a `white_skin_thickness_mm`), la poche reste
    volontairement peu profonde et quasi constante : moins de matiere
    retiree, moins de fragilite en facade. Valeur validee par impression
    physique reelle (cf. `examples/physical_validation/`)."""
    transition_width_mm: float = 1.20
    """Largeur (en XY, mesuree depuis le bord de l'empreinte de l'insert)
    de la rampe de transition entre la poche (profondeur `pocket_depth`)
    et le dos plein de la lithophanie (Z=0) -- "soft organic pocket" :
    evite la marche quasi verticale qui produit des micro-surfaces
    fragiles au slicer sur un contour organique. Contrairement a l'ancien
    chanfrein, l'insert lui-meme reste a epaisseur CONSTANTE (jamais
    rampe) -- seule la cavite qui l'entoure est progressive. Valeur
    validee par impression physique reelle (cf.
    `examples/physical_validation/`). 0.0 desactive la rampe (la cavite se
    limite alors exactement a l'empreinte de l'insert, marche abrupte)."""

    def __post_init__(self) -> None:
        # Plancher "jamais impose silencieusement" (cf.
        # MIN_BACKLIGHT_WALL_THICKNESS_MM) : on avertit sans corriger, pour
        # ne jamais changer une valeur choisie explicitement par
        # l'utilisateur/l'appelant dans son dos.
        if 0.0 < self.white_skin_thickness_mm < MIN_BACKLIGHT_WALL_THICKNESS_MM:
            warnings.warn(
                f"BacklightInsertParams.white_skin_thickness_mm={self.white_skin_thickness_mm:.2f}mm "
                f"est sous le plancher recommande de {MIN_BACKLIGHT_WALL_THICKNESS_MM:.2f}mm "
                "(peau fragile/fissurable en FDM) -- valeur conservee telle quelle, aucune correction "
                "automatique.",
                stacklevel=2,
            )
        if 0.0 < self.insert_thickness_mm < MIN_BACKLIGHT_WALL_THICKNESS_MM:
            warnings.warn(
                f"BacklightInsertParams.insert_thickness_mm={self.insert_thickness_mm:.2f}mm "
                f"est sous le plancher recommande de {MIN_BACKLIGHT_WALL_THICKNESS_MM:.2f}mm "
                "(insert fragile/difficile a manipuler independamment en FDM) -- valeur conservee "
                "telle quelle, aucune correction automatique.",
                stacklevel=2,
            )


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
    side_stabilizers: bool = False
    """Deux corps SEPARES (jamais fusionnes au panneau) qui effleurent les
    bords gauche/droit sur toute la hauteur, avec des languettes de contact
    ponctuelles -- aide a l'impression verticale d'une lithophanie fine,
    inspire du modele communautaire "Lithophane Helper" (Thingiverse
    #2718124), teste physiquement avec succes. Voir
    `core/geometry/support.build_side_stabilizer_pair`. Independant de
    `support_type` (le pied stabilise la base, les stabilisateurs
    maintiennent les cotes -- les deux peuvent etre actifs ensemble)."""


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
    offset_x: float = 0.0
    offset_y: float = 0.0
    """Decalage de la forme, fraction de la largeur/hauteur canonique de la
    Scene (meme convention que ImageTransform.offset_x/y) -- non borne, la
    forme peut sortir du cadre. Utilise uniquement par TEXT aujourd'hui (voir
    core/geometry/shape.py:_text_mask)."""


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
    color_strategy: ColorStrategy | None = None
    """`None` = comportement historique (ReliefMode/CompositionMode font
    foi, cf. docstring de `ColorStrategy`). Reste `None` pour la zone BASE
    et pour tout projet migre depuis v5 (aucun changement de geometrie a la
    migration) ; mis explicitement a `MATERIAL_ONLY` pour toute nouvelle
    zone creee depuis la 0.4.1 (voir ui/main_window.py), pour que le
    workflow "SAM2 + materiau" ne cree plus jamais de relief involontaire."""
    backlight_insert: BacklightInsertParams = field(default_factory=BacklightInsertParams)
    """Pertinent uniquement si `color_strategy is ColorStrategy.BACKLIGHT_INSERT` ;
    conserve sinon (valeurs par defaut inoffensives, jamais lues)."""
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
    format_version: int = 6
