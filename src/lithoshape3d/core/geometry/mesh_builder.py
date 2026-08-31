"""heightmap + mask + GeometryParameters -> mesh (volume ferme, forme du masque).

Convention des axes :
    X = largeur  (image gauche -> droite)
    Y = hauteur  (bas -> haut du modele ; le haut de l'image source correspond
                  au Y maximum, cf. flip vertical ci-dessous)
    Z = epaisseur (face arriere plane a Z=0, relief en face avant)

La face arriere est un plan a Z=0 ; la face avant porte le relief issu de la
heightmap, entre min_thickness_mm et max_thickness_mm. Le resultat est un
volume ferme (watertight) et manifold (voir core/validation) qui epouse la
forme du masque : uniquement les cellules de la grille dont les 4 coins sont
"actifs" (mask >= mask_threshold) recoivent de la geometrie. Un masque
plein (ou mask=None) reproduit exactement la plaque rectangulaire complete
(cas historique Phase 1A) -- un seul chemin de code, pas deux moteurs
separes.

Positionnement : la grille XY couvre toujours params.width_mm x
params.height_mm dans le repere de la Scene, meme si le masque n'occupe
qu'une partie de l'image. Aucun recentrage/rescale automatique -- important
pour superposer plusieurs zones en Phase 2C.

Topologie : le masque peut definir plusieurs composantes disjointes
(ilots) et des trous (ex. anneau) ; chacun devient une frontiere geometrique
a part entiere, geree par la meme regle locale par cellule (voir
`_wall_direction`), sans detection explicite de composantes connexes.

Le winding est construit de facon localement coherente (front, back,
parois), puis retourne globalement une seule fois (`faces[:, ::-1]`) --
regle heritee de Phase 1A, revalidee empiriquement pour les topologies avec
trous/ilots (watertight + winding coherent + volume positif + accepte par
manifold3d, aucune arete non-manifold, aucune arete de bord residuelle).
"""

from __future__ import annotations

import numpy as np
import trimesh
from scipy import ndimage

from lithoshape3d.core.geometry.heightmap import Heightmap
from lithoshape3d.core.geometry.thickness import compute_thickness_mm
from lithoshape3d.core.scene.models import GeometryParameters

DEFAULT_MASK_THRESHOLD = 0.5
"""Seuil binaire applique au masque float32 [0,1] pour decider la topologie
(cellule active ou non). Les valeurs intermediaires du masque restent
disponibles pour un futur feathering (relief/epaisseur progressifs) : ce
seuil ne modifie ni ne detruit le masque source, il ne sert qu'a decider
quelles cellules recoivent de la geometrie dans cette phase."""

MIN_CELL_ISLAND_AREA_MM2 = 1.0
"""Aire minimale (mm2, seuil ABSOLU -- independant de la resolution ou de
la taille du masque) d'un ilot de cellules pour etre conserve dans
`build_mesh_from_heightfield`. Corrige un bug reel : une marche diagonale
d'1 pixel dans un masque (frequente sur une selection IA/SAM2 non nettoyee)
peut laisser, apres la regle "4 coins actifs" qui definit `cell_active`,
un ou deux ilots de 1-2 cellules qui ne touchent le reste de la forme que
par un seul SOMMET partage (pas une arete) -- topologiquement, deux solides
distincts qui ne se rejoignent qu'en un point. Ce point cree une arete
partagee par 4 faces au lieu de 2 (viole la definition d'un maillage
manifold/watertight) des que la grille est assez fine pour que cette marche
tienne sur un seul pixel. Diagnostic complet reproduit sur un masque reel
(export SAM2, marche diagonale a la limite d'un petale de rose) : le mesh
combine echouait la validation watertight alors que chaque composante,
isolee, etait individuellement valide.

Solution generique (pas de detection de diagonale specifique, qui devrait
etre refaite pour chaque nouvelle configuration degeneree possible) : tout
ilot de cellules dont l'aire est sous ce plancher est simplement retire
avant la triangulation -- comme le filtre equivalent deja utilise ailleurs
dans le pipeline SVG (`MIN_CAP_PIECE_AREA_MM2`, cherry_moon). Valeur
choisie pour depasser l'aire d'une seule cellule meme a la resolution la
plus grossiere couramment utilisee dans l'app (preset "Draft", 0.6mm/px ->
0.36mm2/cellule -- un seuil sous cette valeur ne filtrerait jamais un ilot
d'une seule cellule, exactement le cas reel qui a motive ce correctif),
tout en restant tres en dessous de la taille d'un vrai ilot voulu par
l'utilisateur (point d'un "i", boucle d'un "%", element decoratif disjoint
d'un logo) qui occupe toujours plusieurs mm2 meme a cette resolution
grossiere -- ne supprime que le bruit numerique de bord, jamais un ilot
reel."""


def _drop_degenerate_cell_islands(cell_active: np.ndarray, pixel_area_mm2: float) -> np.ndarray:
    """Retire les composantes connexes (4-connexite, partage d'arete --
    seule connexite qui garantit un maillage manifold) de `cell_active`
    dont l'aire est sous `MIN_CELL_ISLAND_AREA_MM2`. Ne fait rien si
    `pixel_area_mm2` est nul/negatif (grille degenerescente, deja rejetee
    ailleurs) ou si toutes les composantes sont deja assez grandes."""
    if pixel_area_mm2 <= 0 or not cell_active.any():
        return cell_active
    labels, num = ndimage.label(cell_active, structure=ndimage.generate_binary_structure(2, 1))
    if num <= 1:
        return cell_active
    sizes = ndimage.sum(cell_active, labels, index=range(1, num + 1))
    min_cells = MIN_CELL_ISLAND_AREA_MM2 / pixel_area_mm2
    keep_labels = {i + 1 for i, size in enumerate(sizes) if size >= min_cells}
    if len(keep_labels) == num:
        return cell_active
    return np.isin(labels, list(keep_labels))


def _side_strip(p: np.ndarray, q: np.ndarray, p_back: np.ndarray, q_back: np.ndarray) -> np.ndarray:
    """2 triangles par segment de bord, reliant l'arete avant p->q a l'arriere.

    L'ordre (p, q, p_back) puis (q, q_back, p_back) doit etre appele avec
    p->q oppose a l'arete deja utilisee par la face avant sur ce meme bord,
    pour garantir un winding globalement coherent.
    """
    t1 = np.stack([p, q, p_back], axis=1)
    t2 = np.stack([q, q_back, p_back], axis=1)
    return np.concatenate([t1, t2], axis=0)


def _build_walls(
    idx: np.ndarray, back_idx: np.ndarray, cell_active: np.ndarray
) -> np.ndarray:
    """Parois le long de toute frontiere active/inactive (bord exterieur,
    trous, ilots) -- detection vectorisee, construction par arete (le
    nombre d'aretes de bord est proportionnel au perimetre du masque, pas a
    sa surface : une boucle Python ici reste rapide, voir benchmark)."""
    # Aretes verticales (entre vertex (r,c) et (r+1,c)) : bord si la cellule
    # a gauche (c-1) et la cellule a droite (c) different (hors grille = inactif).
    padded_h = np.pad(cell_active, ((0, 0), (1, 1)), constant_values=False)
    wall_v = padded_h[:, :-1] != padded_h[:, 1:]
    active_is_right = padded_h[:, 1:]

    # Aretes horizontales (entre vertex (r,c) et (r,c+1)) : bord si la
    # cellule au-dessus (r-1) et la cellule en dessous (r) different.
    padded_v = np.pad(cell_active, ((1, 1), (0, 0)), constant_values=False)
    wall_h = padded_v[:-1, :] != padded_v[1:, :]
    active_is_below = padded_v[1:, :]

    strips: list[np.ndarray] = []

    vr, vc = np.nonzero(wall_v)
    if len(vr):
        top_v, bottom_v = idx[vr, vc], idx[vr + 1, vc]
        top_vb, bottom_vb = back_idx[vr, vc], back_idx[vr + 1, vc]
        right_active = active_is_right[vr, vc]
        # cellule active a droite -> cote "gauche" de cette cellule -> C->A
        strips.append(
            _side_strip(
                bottom_v[right_active], top_v[right_active], bottom_vb[right_active], top_vb[right_active]
            )
        )
        # cellule active a gauche -> cote "droit" -> A->C
        left_active = ~right_active
        strips.append(
            _side_strip(
                top_v[left_active], bottom_v[left_active], top_vb[left_active], bottom_vb[left_active]
            )
        )

    hr, hc = np.nonzero(wall_h)
    if len(hr):
        left_h, right_h = idx[hr, hc], idx[hr, hc + 1]
        left_hb, right_hb = back_idx[hr, hc], back_idx[hr, hc + 1]
        below_active = active_is_below[hr, hc]
        # cellule active en dessous -> cote "haut" -> A->B
        strips.append(
            _side_strip(
                left_h[below_active], right_h[below_active], left_hb[below_active], right_hb[below_active]
            )
        )
        # cellule active au-dessus -> cote "bas" -> B->A
        above_active = ~below_active
        strips.append(
            _side_strip(
                right_h[above_active], left_h[above_active], right_hb[above_active], left_hb[above_active]
            )
        )

    if not strips:
        return np.zeros((0, 3), dtype=np.int64)
    return np.concatenate(strips, axis=0)


def build_mesh_from_heightfield(
    front_z: np.ndarray,
    active: np.ndarray,
    width_mm: float,
    height_mm: float,
    back_z: np.ndarray | None = None,
) -> trimesh.Trimesh:
    """Construit le volume ferme a partir d'un champ de hauteur DEJA oriente
    (Y-up, cf. flip dans `build_slab_mesh`) et DEJA compose si besoin.

    Reutilise a la fois par le moteur mono-zone (`build_slab_mesh`), par la
    composition multi-zone (`core/geometry/composition.py`) et par le corps
    blanc a cavite du Backlight Insert (`core/geometry/backlight.py`) -- un
    seul chemin de construction de mesh, pas deux moteurs separes.

    `back_z=None` (par defaut) reproduit exactement le comportement
    historique : face arriere plane a Z=0 partout. Un `back_z` par-cellule
    permet une face arriere non plane (ex. une cavite de Backlight Insert) --
    doit rester strictement < `front_z` partout ou `active`, sous peine de
    geometrie degeneree (verifie par l'appelant, pas ici : ce module reste
    une brique geometrique pure, sans connaissance de la raison du creux)."""
    rows, cols = front_z.shape

    xs = np.linspace(0.0, width_mm, cols, dtype=np.float32)
    ys = np.linspace(0.0, height_mm, rows, dtype=np.float32)
    grid_x, grid_y = np.meshgrid(xs, ys)

    if back_z is None:
        back_z = np.zeros_like(front_z)

    front_vertices = np.stack([grid_x, grid_y, front_z], axis=-1).reshape(-1, 3)
    back_vertices = np.stack([grid_x, grid_y, back_z], axis=-1).reshape(-1, 3)

    n_grid = rows * cols
    idx = np.arange(n_grid, dtype=np.int64).reshape(rows, cols)
    back_idx = idx + n_grid

    cell_active = active[:-1, :-1] & active[:-1, 1:] & active[1:, :-1] & active[1:, 1:]
    if not cell_active.any():
        raise ValueError(
            "Masque insuffisant pour generer une geometrie : aucune cellule "
            "entierement active (zone trop petite ou trop fine pour la resolution courante)."
        )

    pixel_size_mm = width_mm / cols if cols > 0 else 0.0
    cell_active = _drop_degenerate_cell_islands(cell_active, pixel_size_mm * pixel_size_mm)
    if not cell_active.any():
        raise ValueError(
            "Masque insuffisant pour generer une geometrie : toutes les cellules actives "
            "etaient des ilots degeneres sous le plancher d'aire minimal."
        )

    a = idx[:-1, :-1][cell_active]
    b = idx[:-1, 1:][cell_active]
    c = idx[1:, :-1][cell_active]
    d = idx[1:, 1:][cell_active]
    front_faces = np.concatenate([np.stack([a, d, b], axis=1), np.stack([a, c, d], axis=1)], axis=0)

    ab = back_idx[:-1, :-1][cell_active]
    bb = back_idx[:-1, 1:][cell_active]
    cb = back_idx[1:, :-1][cell_active]
    db = back_idx[1:, 1:][cell_active]
    back_faces = np.concatenate([np.stack([ab, bb, db], axis=1), np.stack([ab, db, cb], axis=1)], axis=0)

    walls = _build_walls(idx, back_idx, cell_active)

    faces = np.concatenate([front_faces, back_faces, walls], axis=0)
    faces = faces[:, ::-1]  # flip global : normales sortantes (verifie empiriquement)

    vertices = np.concatenate([front_vertices, back_vertices], axis=0)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

    if mesh.volume < 0:
        mesh.invert()
    mesh.remove_unreferenced_vertices()

    return mesh


def build_slab_mesh(
    heightmap: Heightmap,
    mask: np.ndarray | None,
    params: GeometryParameters,
    mask_threshold: float = DEFAULT_MASK_THRESHOLD,
) -> trimesh.Trimesh:
    """Genere un volume ferme epousant la forme du masque a partir d'une heightmap.

    `mask=None` (ou un masque entierement >= `mask_threshold`) reproduit
    exactement la plaque rectangulaire complete. Un masque partiel decoupe
    la geometrie selon sa frontiere reelle (trous et ilots geres nativement).
    """
    if params.base_shape != "rectangle":
        raise NotImplementedError(
            f"base_shape={params.base_shape!r} non supporte (rectangle uniquement)"
        )

    values = heightmap.values
    if mask is not None and mask.shape != values.shape:
        raise ValueError("mask doit avoir la meme forme que la heightmap")

    thickness_mm = compute_thickness_mm(values, params)
    active = np.ones_like(values, dtype=bool) if mask is None else (mask >= mask_threshold)

    # L'image a pour origine (0,0) en haut-gauche (convention Pillow/numpy) ;
    # on retourne verticalement pour que le haut de l'image corresponde au Y
    # maximum du modele (orientation "a l'endroit" une fois le modele debout).
    thickness_mm = np.flipud(thickness_mm)
    active = np.flipud(active)

    return build_mesh_from_heightfield(thickness_mm, active, params.width_mm, params.height_mm)
