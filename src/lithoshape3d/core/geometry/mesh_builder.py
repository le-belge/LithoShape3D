"""heightmap + mask + GeometryParameters -> mesh (plaque rectangulaire fermee).

Convention des axes :
    X = largeur  (image gauche -> droite)
    Y = hauteur  (bas -> haut du modele ; le haut de l'image source correspond
                  au Y maximum, cf. flip vertical ci-dessous)
    Z = epaisseur (face arriere plane a Z=0, relief en face avant)

La face arriere est un plan a Z=0 ; la face avant porte le relief issu de la
heightmap, entre min_thickness_mm et max_thickness_mm. Le resultat est un
volume unique ferme (watertight) et manifold (voir core/validation).

Le winding des faces est construit de facon localement coherente sur toute
la grille (front, back, 4 bords lateraux), puis retourne globalement une
seule fois (`faces[:, ::-1]`) pour obtenir des normales sortantes -- ce
choix a ete verifie empiriquement (watertight + winding coherent + volume
positif + accepte par manifold3d) plutot que suppose.
"""

from __future__ import annotations

import numpy as np
import trimesh

from lithoshape3d.core.geometry.heightmap import Heightmap
from lithoshape3d.core.geometry.thickness import compute_thickness_mm
from lithoshape3d.core.scene.models import GeometryParameters


def _side_strip(p: np.ndarray, q: np.ndarray, p_back: np.ndarray, q_back: np.ndarray) -> np.ndarray:
    """2 triangles par segment de bord, reliant l'arete avant p->q a l'arriere.

    L'ordre (p, q, p_back) puis (q, q_back, p_back) doit etre appele avec
    p->q oppose a l'arete deja utilisee par la face avant sur ce meme bord,
    pour garantir un winding globalement coherent.
    """
    t1 = np.stack([p, q, p_back], axis=1)
    t2 = np.stack([q, q_back, p_back], axis=1)
    return np.concatenate([t1, t2], axis=0)


def build_slab_mesh(
    heightmap: Heightmap,
    mask: np.ndarray | None,
    params: GeometryParameters,
) -> trimesh.Trimesh:
    """Genere une plaque rectangulaire fermee a partir d'une heightmap.

    `mask` est reserve aux futures zones LithoFusion : en Phase 1A il doit
    etre `None` ou entierement actif (True partout) et n'affecte pas encore
    la geometrie generee.
    """
    if params.base_shape != "rectangle":
        raise NotImplementedError(
            f"base_shape={params.base_shape!r} non supporte en Phase 1A (rectangle uniquement)"
        )

    values = heightmap.values
    if mask is not None:
        if mask.shape != values.shape:
            raise ValueError("mask doit avoir la meme forme que la heightmap")
        if not mask.all():
            raise NotImplementedError(
                "les masques partiels seront geres en phase LithoFusion ; "
                "Phase 1A ne supporte qu'un mask entierement actif ou None"
            )

    thickness_mm = compute_thickness_mm(values, params)
    # L'image a pour origine (0,0) en haut-gauche (convention Pillow/numpy) ;
    # on retourne verticalement pour que le haut de l'image corresponde au Y
    # maximum du modele (orientation "a l'endroit" une fois le modele debout).
    thickness_mm = np.flipud(thickness_mm)

    rows, cols = thickness_mm.shape

    xs = np.linspace(0.0, params.width_mm, cols, dtype=np.float32)
    ys = np.linspace(0.0, params.height_mm, rows, dtype=np.float32)
    grid_x, grid_y = np.meshgrid(xs, ys)

    front_z = thickness_mm
    back_z = np.zeros_like(front_z)

    front_vertices = np.stack([grid_x, grid_y, front_z], axis=-1).reshape(-1, 3)
    back_vertices = np.stack([grid_x, grid_y, back_z], axis=-1).reshape(-1, 3)

    n_grid = rows * cols
    idx = np.arange(n_grid, dtype=np.int64).reshape(rows, cols)
    back_idx = idx + n_grid

    a = idx[:-1, :-1].ravel()
    b = idx[:-1, 1:].ravel()
    c = idx[1:, :-1].ravel()
    d = idx[1:, 1:].ravel()
    front_faces = np.concatenate(
        [np.stack([a, d, b], axis=1), np.stack([a, c, d], axis=1)], axis=0
    )

    ab = back_idx[:-1, :-1].ravel()
    bb = back_idx[:-1, 1:].ravel()
    cb = back_idx[1:, :-1].ravel()
    db = back_idx[1:, 1:].ravel()
    back_faces = np.concatenate(
        [np.stack([ab, bb, db], axis=1), np.stack([ab, db, cb], axis=1)], axis=0
    )

    top = _side_strip(idx[0, :-1], idx[0, 1:], back_idx[0, :-1], back_idx[0, 1:])
    bottom = _side_strip(idx[-1, 1:], idx[-1, :-1], back_idx[-1, 1:], back_idx[-1, :-1])
    left = _side_strip(idx[1:, 0], idx[:-1, 0], back_idx[1:, 0], back_idx[:-1, 0])
    right = _side_strip(idx[:-1, -1], idx[1:, -1], back_idx[:-1, -1], back_idx[1:, -1])

    faces = np.concatenate([front_faces, back_faces, top, bottom, left, right], axis=0)
    faces = faces[:, ::-1]  # flip global : normales sortantes (verifie empiriquement)

    vertices = np.concatenate([front_vertices, back_vertices], axis=0)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

    if mesh.volume < 0:
        mesh.invert()

    return mesh
