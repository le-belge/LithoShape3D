"""Pied/support d'impression, fusionne au modele compose.

Pas un support de surplomb (ca reste le travail du slicer) : le but est
uniquement de stabiliser physiquement une lithophanie fine et large sur le
plateau, via un pied analytique simple (des boites), fusionne au modele par
une union manifold3d -- pas de construction topologique main sur la couture,
ce qui serait fragile pour un gain de robustesse minime : manifold3d gere
deja tres bien l'union de solides fermes qui se recouvrent en volume.

Point important verifie empiriquement : une union manifold3d entre deux
solides qui ne font qu'AFFLEURER (faces exactement coincidentes, aucun
recouvrement volumique reel) peut les laisser distincts au lieu de les
fusionner (`connected_components` > 1 en sortie). Toutes les pieces
generees ici (pied, renforts) sont donc volontairement dimensionnees pour
se recouvrir en profondeur, jamais seulement se toucher.

Convention (identique a mesh_builder.py) : X = largeur, Y = hauteur (bas de
l'image = Y=0), Z = epaisseur (dos a Z=0). Le pied se fixe sous le bord bas
du panneau (Y=0), s'etend vers Y negatif, et vers Z positif sur une
profondeur bien plus grande que l'epaisseur fine de la lithophanie -- c'est
cette largeur en Z (pas visible en usage normal, seulement au sol) qui donne
au resultat imprime une base stable, y compris pour un affichage/impression
"debout" (panneau vertical)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

from lithoshape3d.core.scene.models import PrintSupport, SupportType

_FOOT_PANEL_PENETRATION_MM = 2.0
"""De combien le pied plat lui-meme remonte au-dela de `y_top` (le point le
plus bas reel du panneau, pas Y=0 suppose -- voir `attach_support`) :
minimum necessaire pour un recouvrement volumique reel avec le panneau,
quelle que soit la Shape (une Shape inscrite avec marge, comme le coeur,
peut n'avoir qu'une pointe etroite a cette altitude)."""

_RIB_PANEL_PENETRATION_MM = 2 * _FOOT_PANEL_PENETRATION_MM
"""De combien un renfort remonte au-dela de `y_top` -- volontairement PLUS
que `_FOOT_PANEL_PENETRATION_MM` : un renfort qui ne remonterait pas plus
haut que le pied plat lui-meme serait entierement englobe dans son volume
(donc sans effet reel), ce qui viderait `SupportType.REINFORCED` de son
interet par rapport a `SupportType.FLAT`."""


def _to_manifold(mesh: trimesh.Trimesh):
    import manifold3d

    m3d_mesh = manifold3d.Mesh(
        vert_properties=mesh.vertices.astype(np.float32),
        tri_verts=mesh.faces.astype(np.uint32),
    )
    return manifold3d.Manifold(m3d_mesh)


def _from_manifold(manifold) -> trimesh.Trimesh:
    mesh = manifold.to_mesh()
    vertices = np.asarray(mesh.vert_properties)[:, :3]
    faces = np.asarray(mesh.tri_verts)
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=True)


def _flat_foot_mesh(x_min: float, x_max: float, y_top: float, support: PrintSupport) -> trimesh.Trimesh:
    """Le pied remonte de `_FOOT_PANEL_PENETRATION_MM` au-dessus de `y_top`
    (pas seulement affleurant) : necessaire des qu'une Shape (v0.4) n'a plus
    un bord bas rectangulaire plein A Y=0 -- un coeur inscrit avec marge, un
    cercle ou une lettre isolee ont leur point le plus bas a un `y_top` reel
    (parfois tres au-dessus de 0, cf. `attach_support`), et sur une portion
    etroite (pointe/jambage) plutot que la largeur X totale du mesh. Sans
    caler le pied sur ce `y_top` reel (et non sur un Y=0 suppose), l'union
    manifold3d peut laisser panneau et pied entierement disjoints
    (`connected_components` > 1) meme si le pied semble visuellement en
    place -- meme principe que pour les renforts, voir note de module."""
    x_min = x_min - support.overhang_left_mm
    x_max = x_max + support.overhang_right_mm
    top_y = y_top + _FOOT_PANEL_PENETRATION_MM
    extents = [x_max - x_min, support.height_mm + _FOOT_PANEL_PENETRATION_MM, support.depth_mm]
    box = trimesh.creation.box(extents=extents)
    center = [
        (x_min + x_max) / 2.0,
        top_y - extents[1] / 2.0,
        support.depth_mm / 2.0,
    ]
    box.apply_translation(center)
    return box


def _reinforcement_ribs(
    x_min: float, x_max: float, y_top: float, support: PrintSupport
) -> list[trimesh.Trimesh]:
    """Renforts : petits piliers pleins repartis sur la largeur utile (hors
    debords), qui prolongent localement le pied vers le haut, a l'interieur
    du panneau, sur `_RIB_PANEL_PENETRATION_MM`.

    Volontairement de simples boites recouvrant profondement le pied ET le
    panneau (pas un gousset diagonal fin) : un premier essai avec un prisme
    triangulaire affleurant les faces du pied a laisse des corps disjoints
    apres union (`connected_components` > 1) -- un vrai recouvrement
    volumique, pas seulement un contact de surface, est necessaire pour une
    fusion manifold3d fiable."""
    if support.rib_count <= 0:
        return []

    width = x_max - x_min
    margin = support.rib_thickness_mm  # evite un renfort colle au bord
    usable_start, usable_end = x_min + margin, max(x_max - margin, x_min + margin)
    if usable_end <= usable_start:
        centers = [x_min + width / 2.0]
    else:
        centers = np.linspace(usable_start, usable_end, support.rib_count)

    half_thickness = support.rib_thickness_mm / 2.0
    y_min, y_max = y_top - support.height_mm, y_top + _RIB_PANEL_PENETRATION_MM
    extents = [support.rib_thickness_mm, y_max - y_min, support.depth_mm]
    y_center = (y_min + y_max) / 2.0
    z_center = support.depth_mm / 2.0

    ribs = []
    for x_center in centers:
        x_center = float(np.clip(x_center, x_min + half_thickness, x_max - half_thickness))
        rib = trimesh.creation.box(extents=extents)
        rib.apply_translation([x_center, y_center, z_center])
        ribs.append(rib)
    return ribs


def build_support_mesh(
    x_min: float, x_max: float, y_top: float, support: PrintSupport
) -> trimesh.Trimesh | None:
    """Construit le pied seul (pas encore fusionne), sur l'etendue X
    [x_min, x_max] fournie -- generalise a toute Shape (v0.4) : passer les
    bornes X reelles du mesh compose (pas forcement [0, width_mm], une
    forme non rectangulaire -- coeur, lettre -- peut avoir une empreinte
    plus etroite ou decalee a son bord bas). `y_top` : altitude Y reelle du
    point le plus bas du mesh (pas forcement 0 -- une Shape inscrite avec
    marge, comme le coeur, peut avoir tout son bord bas au-dessus de Y=0,
    cf. `attach_support`). `None` si SupportType.NONE."""
    if support.support_type is SupportType.NONE:
        return None

    parts = [_flat_foot_mesh(x_min, x_max, y_top, support)]
    if support.support_type is SupportType.REINFORCED:
        parts.extend(_reinforcement_ribs(x_min, x_max, y_top, support))

    if len(parts) == 1:
        return parts[0]

    # Union manifold3d (pas une simple concatenation) : depuis que le pied
    # plat penetre lui-meme dans le panneau (cf. `_flat_foot_mesh`), il
    # recouvre desormais aussi les renforts en volume (les deux occupent la
    # meme plage Y pres du panneau) -- une concatenation naive produirait
    # alors des faces internes dupliquees/qui se recouvrent, rejetees par
    # `_to_manifold` en aval (mesh non watertight apres fusion).
    merged = _to_manifold(parts[0])
    for part in parts[1:]:
        merged = merged + _to_manifold(part)
    return _from_manifold(merged)


# --------------------------------------------------------------------- #
# Stabilisateurs lateraux (aide a l'impression, jamais fusionnes)
# --------------------------------------------------------------------- #
#
# Modele communautaire "Lithophane Helper" (madpenguin, Thingiverse
# #2718124, CC-BY -- voir assets/ATTRIBUTION.md) utilise TEL QUEL comme
# gabarit, pas reinvente : une lithophanie fine et large imprimee DEBOUT
# peut vibrer/flechir localement pendant l'impression (bruit visible dans
# les couches). Contrairement au pied (`build_support_mesh`, fusionne au
# panneau), un stabilisateur lateral reste un corps SEPARE : il vient
# juste EFFLEURER le bord gauche ou droit du panneau (jamais la face avant
# ni arriere), pour le maintenir sans y adherer -- a detacher a la pince
# une fois l'impression terminee, comme l'original. Deux exemplaires
# (gauche/droite), a placer de part et d'autre du panneau dans le slicer.
#
# Geometrie du gabarit (mesuree directement sur le STL source, PAS
# redessinee a la main -- voir `tests/core/geometry/test_support.py` pour
# les mesures de validation) : coin triangulaire plein, base 30mm x hauteur
# 100mm x epaisseur 5mm dans son orientation NATIVE. Cette face plate
# (30x100mm) n'est PAS le cote de contact -- confirme par une impression
# reelle (photo utilisateur) : ce sont les languettes en "escalier"
# (profil en dents, cf. coupe Y-Z a X=15mm natif) qui doivent toucher la
# litho, pas la face large du coin. Le gabarit est donc tourne de 90°
# autour de l'axe Y (hauteur) avant usage : l'ancienne epaisseur (5mm,
# ancien Z) devient la nouvelle largeur de contact (nouveau X), et
# l'ancienne largeur (30mm, ancien X) devient la profondeur du corps de
# calage qui s'eloigne du panneau (nouveau Z) -- le coin triangulaire
# stabilise sur le plateau via cette profondeur, tandis que seules les
# dents de l'escalier (nouveau X, alternant 2mm/5mm periodiquement sur
# toute la hauteur) viennent affleurer le bord du panneau.

_STABILIZER_TEMPLATE_PATH = Path(__file__).parent / "assets" / "lithophane_helper_100mm.stl"
_STABILIZER_TEMPLATE_NATIVE_HEIGHT_MM = 100.0
_STABILIZER_ROTATION = trimesh.transformations.rotation_matrix(
    np.radians(90.0), [0.0, 1.0, 0.0], point=[0.0, 0.0, 0.0]
)
"""Rotation 90 deg autour de Y : ancien Z (epaisseur, 0-5mm, dents) ->
nouveau X (contact) ; ancien X (largeur, 0-30mm, corps du coin) ->
nouveau Z, neglige (voir `_STABILIZER_DEPTH_FLIP`)."""

_STABILIZER_DEPTH_FLIP = np.diag([1.0, 1.0, -1.0, 1.0])
"""Applique apres la rotation : le nouveau Z issu de la rotation est
negatif (le corps du coin s'eloignait du panneau vers Z<0) -- inverse
pour obtenir une profondeur positive (Z=0 au contact, Z croissant en
s'eloignant), plus lisible/coherent avec le reste du module."""

_STABILIZER_RIDGE_DEPTH_MM = 15.0
"""Position Z (mm, repere du gabarit apres rotation+mise a plat, AVANT
mise a l'echelle en hauteur) du CENTRE de la nervure de contact -- le
coin est symetrique (nervure a l'ancien X natif 14-16mm, sur une largeur
totale de 30mm), donc naturellement au milieu de sa profondeur propre.
Mesuree directement par coupe transversale (voir
`tests/core/geometry/test_support.py`), PAS redessinee a la main.

Bug reel corrige ici (retour terrain, mesure au regle du slicer sur un
export reel : ~13mm d'ecart) : cette profondeur (15mm) n'a AUCUN rapport
avec l'epaisseur du panneau lui-meme (souvent < 3mm) -- sans
realignement explicite, la nervure de contact se retrouve tres loin
(en profondeur/epaisseur) de la ou le panneau existe reellement, et les
deux corps ne se touchent jamais malgre un alignement X/Y par ailleurs
correct. `build_side_stabilizer_mesh` recentre donc la nervure sur le
MILIEU de l'epaisseur reelle du panneau (`panel_thickness_mm / 2`)."""

_STABILIZER_CONTACT_OVERLAP_MM = 0.12
"""Recouvrement X volontaire (pas une simple tangence) entre les dents et
le bord du panneau -- retour terrain (mesure au regle du slicer) : meme
apres correction de `_STABILIZER_RIDGE_DEPTH_MM`, un contact exactement
affleurant (0.000mm) peut ne pas etre vu comme un vrai contact par le
slicer (arrondi flottant a l'export 3MF/STL, notamment introduit par le
miroir `apply_scale([-1,1,1])` du cote droit -- deux solides qui ne se
recouvrent pas en volume peuvent finir separes de quelques microns a
quelques centiemes de mm apres export, invisibles sur les mesures
symboliques mais reels une fois le fichier charge). Documente aussi en
tete de module (union manifold3d entre solides qui ne font qu'affleurer)
-- meme risque ici bien que les stabilisateurs restent volontairement des
corps separes (jamais fusionnes, detachables)."""


def real_edge_profile(
    meshes: list[trimesh.Trimesh], side: str, x_tolerance_mm: float = 1.0
) -> tuple[float, float, float, float]:
    """Bord REEL du panneau du cote demande (pas sa bbox globale) : les
    stabilisateurs doivent affleurer la matiere qui existe vraiment a
    X=x_min/x_max, pas une boite englobante qui peut etre plus large que
    le panneau lui-meme si sa forme n'est pas un rectangle parfait (bord
    incline, aminci localement, decoupe). Retourne
    (y_bottom, y_top, z_bottom, z_top) mesures sur les sommets reels
    situes a moins de `x_tolerance_mm` du bord concerne.

    Si `meshes` est vide ou qu'aucun sommet n'est trouve dans la marge
    (forme trop fine/anguleuse a cette tolerance), leve `ValueError` --
    mieux vaut echouer explicitement que caler un stabilisateur sur des
    donnees vides."""
    if side not in ("left", "right"):
        raise ValueError(f"side doit etre 'left' ou 'right', recu {side!r}.")
    if not meshes:
        raise ValueError("real_edge_profile: aucun mesh fourni.")

    all_vertices = np.concatenate([m.vertices for m in meshes], axis=0)
    x_ref = float(all_vertices[:, 0].min() if side == "left" else all_vertices[:, 0].max())
    near = all_vertices[np.abs(all_vertices[:, 0] - x_ref) < x_tolerance_mm]
    if len(near) == 0:
        raise ValueError(
            f"real_edge_profile: aucun sommet a moins de {x_tolerance_mm}mm du bord "
            f"{side} (x_ref={x_ref}) -- forme trop etroite a cette tolerance ?"
        )
    return (
        float(near[:, 1].min()),
        float(near[:, 1].max()),
        float(near[:, 2].min()),
        float(near[:, 2].max()),
    )


_stabilizer_template_cache: trimesh.Trimesh | None = None


def _load_stabilizer_template() -> trimesh.Trimesh:
    """Charge le gabarit, deja tourne pour presenter les dents de contact
    (l'escalier) le long de l'axe X, pret a etre mis a l'echelle en Y et
    positionne."""
    global _stabilizer_template_cache
    if _stabilizer_template_cache is None:
        mesh = trimesh.load(_STABILIZER_TEMPLATE_PATH, force="mesh")
        if not mesh.is_watertight:
            raise ValueError(
                f"Gabarit stabilisateur lateral non watertight : {_STABILIZER_TEMPLATE_PATH}"
            )
        mesh.apply_transform(_STABILIZER_ROTATION)
        mesh.apply_transform(_STABILIZER_DEPTH_FLIP)
        _stabilizer_template_cache = mesh
    return _stabilizer_template_cache.copy()


def build_side_stabilizer_mesh(
    y_bottom: float,
    y_top: float,
    side: str,
    panel_thickness_mm: float,
    *,
    ridge_center_z_mm: float | None = None,
    contact_overlap_mm: float = _STABILIZER_CONTACT_OVERLAP_MM,
) -> trimesh.Trimesh:
    """Charge le gabarit "Lithophane Helper" (deja tourne pour presenter
    ses dents de contact le long de X, voir `_load_stabilizer_template`)
    et le met a l'echelle en HAUTEUR SEULEMENT (axe Y, pour couvrir
    `y_top - y_bottom`) -- profondeur (30mm) et le profil des dents
    restent ceux du modele original, jamais deformes (une mise a
    l'echelle non uniforme changerait l'angle du coin et l'espacement
    des languettes).

    Positionne pour que les dents affleurent (avec un leger recouvrement
    volontaire, voir `contact_overlap_mm`) le bord gauche (`side="left"`,
    bord a X=0) ou droit (`side="right"`, bord a X=`panel_width_mm` --
    fourni par l'appelant via une translation, cf.
    `build_side_stabilizer_pair`, point d'entree recommande).

    `panel_thickness_mm` (obligatoire, cf. bug reel documente sur
    `_STABILIZER_RIDGE_DEPTH_MM`) : epaisseur reelle du panneau AU BORD
    CONCERNE (pas necessairement l'epaisseur globale/bbox -- voir
    `real_edge_profile`, a utiliser en amont si le panneau n'est pas un
    rectangle parfait). `ridge_center_z_mm` : override optionnel du
    centre Z cible (sinon `panel_thickness_mm / 2`, suppose le panneau
    a Z=0..panel_thickness_mm) -- utile si le bord reel du panneau a ce
    cote n'est pas centre sur Z=0..panel_thickness_mm (ex. bord incline).

    `contact_overlap_mm` (retour terrain, cf. `_STABILIZER_CONTACT_OVERLAP_MM`)
    : recouvrement X volontaire, pas une simple tangence -- un contact
    exactement affleurant (0.000mm) peut se retrouver separe de quelques
    microns apres export (arrondi flottant, notamment introduit par le
    miroir du cote droit), et donc ne pas etre vu comme un contact reel
    une fois le fichier charge dans un slicer."""
    if y_top <= y_bottom:
        raise ValueError("y_top doit etre strictement superieur a y_bottom.")
    if side not in ("left", "right"):
        raise ValueError(f"side doit etre 'left' ou 'right', recu {side!r}.")
    if panel_thickness_mm <= 0:
        raise ValueError("panel_thickness_mm doit etre > 0.")

    height_mm = y_top - y_bottom
    scale_y = height_mm / _STABILIZER_TEMPLATE_NATIVE_HEIGHT_MM

    result = _load_stabilizer_template()
    result.apply_scale([1.0, scale_y, 1.0])

    # Apres rotation, X=0 est le DOS PLAT du gabarit (present a toutes les
    # hauteurs) et les DENTS ressortent periodiquement jusqu'a X positif
    # (bounds[1][0]) -- ce sont elles, pas le dos, qui doivent affleurer
    # le panneau. Decale donc pour amener la pointe des dents (pas le
    # dos) a X=+contact_overlap_mm (un peu A L'INTERIEUR du panneau, pas
    # exactement X=0 -- voir `contact_overlap_mm`), le dos s'eloignant
    # alors en X negatif.
    tooth_reach = float(result.bounds[1][0])
    ridge_z_target = (
        ridge_center_z_mm if ridge_center_z_mm is not None else panel_thickness_mm / 2.0
    )
    result.apply_translation(
        [-tooth_reach + contact_overlap_mm, y_bottom, ridge_z_target - _STABILIZER_RIDGE_DEPTH_MM]
    )

    # Position "gauche" par construction (dents a X=+overlap, dos en
    # X<0). Pour le bord droit, miroiter en X (dents restent a
    # X=+overlap avant mirroir, donc a X=-overlap apres) --
    # `build_side_stabilizer_pair` translate ensuite ce resultat de
    # panel_width_mm pour amener les dents a panel_width_mm - overlap,
    # legerement A L'INTERIEUR du bord droit reel.
    if side == "right":
        result.apply_scale([-1.0, 1.0, 1.0])

    return result


def build_side_stabilizer_pair(
    panel_width_mm: float,
    y_bottom: float,
    y_top: float,
    panel_thickness_mm: float,
    *,
    left_ridge_center_z_mm: float | None = None,
    right_ridge_center_z_mm: float | None = None,
    contact_overlap_mm: float = _STABILIZER_CONTACT_OVERLAP_MM,
) -> tuple[trimesh.Trimesh, trimesh.Trimesh]:
    """Point d'entree recommande : construit et positionne les DEUX
    stabilisateurs (gauche affleurant pres de X=0, droit affleurant pres
    de X=`panel_width_mm`, avec un leger recouvrement volontaire -- voir
    `contact_overlap_mm`), prets a etre places tels quels a cote du
    panneau (meme repere XYZ, aucun repositionnement manuel necessaire
    dans le slicer -- meme convention que les autres corps generes par ce
    module).

    `panel_thickness_mm` : epaisseur par defaut (Z max globale) si aucun
    override de cote n'est fourni. `left_ridge_center_z_mm` /
    `right_ridge_center_z_mm` : centre Z cible INDEPENDANT par cote (cf.
    retour terrain ChatGPT : le bord gauche et le bord droit d'un panneau
    ne sont pas garantis symetriques -- inclinaison, amincissement local,
    forme non rectangulaire -- donc chaque cote doit pouvoir etre recale
    sur SA PROPRE geometrie reelle, voir `real_edge_profile`), sinon
    `panel_thickness_mm / 2` pour les deux."""
    left = build_side_stabilizer_mesh(
        y_bottom,
        y_top,
        "left",
        panel_thickness_mm,
        ridge_center_z_mm=left_ridge_center_z_mm,
        contact_overlap_mm=contact_overlap_mm,
    )
    right = build_side_stabilizer_mesh(
        y_bottom,
        y_top,
        "right",
        panel_thickness_mm,
        ridge_center_z_mm=right_ridge_center_z_mm,
        contact_overlap_mm=contact_overlap_mm,
    )
    right.apply_translation([panel_width_mm, 0.0, 0.0])
    return left, right


def attach_support(mesh: trimesh.Trimesh, support: PrintSupport) -> trimesh.Trimesh:
    """Fusionne le pied au modele compose (union manifold3d). Retourne `mesh`
    inchange si `support.support_type is SupportType.NONE`.

    L'etendue X ET l'altitude Y d'accroche du pied sont deduites des bornes
    REELLES du mesh (jamais d'une largeur canonique ni d'un Y=0 supposes) :
    generalise automatiquement a toute Shape -- un coeur inscrit avec marge,
    un cercle ou une lettre isolee obtiennent un pied cale sur leur propre
    empreinte ET sur leur point le plus bas reel, pas sur un rectangle
    touchant Y=0 qui n'existe plus. Sans ce calage sur `y_top`, le pied et
    le panneau peuvent rester des solides disjoints apres union manifold3d
    (aucun recouvrement volumique reel) meme si le pied semble, visuellement,
    juste en dessous."""
    if support.support_type is SupportType.NONE:
        return mesh
    x_min, x_max = float(mesh.bounds[0][0]), float(mesh.bounds[1][0])
    y_top = float(mesh.bounds[0][1])
    support_mesh = build_support_mesh(x_min, x_max, y_top, support)
    if support_mesh is None:
        return mesh

    fused = _to_manifold(mesh) + _to_manifold(support_mesh)
    return _from_manifold(fused)
