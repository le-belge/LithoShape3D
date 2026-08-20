"""Validation d'un mesh genere : fermeture, manifold, orientation, dimensions.

La validation fait partie integrante du moteur : un mesh n'est considere
utilisable qu'apres etre passe par `validate_mesh`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh


@dataclass(frozen=True)
class MeshValidationResult:
    is_watertight: bool
    is_winding_consistent: bool
    volume_mm3: float
    euler_number: int
    has_degenerate_faces: bool
    has_nan_or_inf: bool
    bounds_mm: tuple[tuple[float, float, float], tuple[float, float, float]]
    manifold3d_compatible: bool
    connected_components: int
    open_boundary_edge_count: int
    """Diagnostic : plusieurs composantes sont acceptables (ex. ilots
    disjoints, geres nativement depuis la Phase 2B) et n'invalident pas le
    mesh a elles seules. Un mesh correctement ferme a toujours 0 arete de
    bord ; deja implique par `is_watertight`, expose ici a titre
    d'information/diagnostic explicite."""

    @property
    def is_valid(self) -> bool:
        return (
            self.is_watertight
            and self.is_winding_consistent
            and self.volume_mm3 > 0
            and not self.has_degenerate_faces
            and not self.has_nan_or_inf
            and self.manifold3d_compatible
        )

    def issues(self) -> list[str]:
        problems = []
        if not self.is_watertight:
            problems.append("mesh non watertight (surface ouverte)")
        if not self.is_winding_consistent:
            problems.append("winding incoherent")
        if self.volume_mm3 <= 0:
            problems.append(f"volume non positif ({self.volume_mm3})")
        if self.has_degenerate_faces:
            problems.append("triangles degeneres presents")
        if self.has_nan_or_inf:
            problems.append("NaN/Inf dans les sommets")
        if not self.manifold3d_compatible:
            problems.append("rejete par manifold3d")
        return problems


def _check_manifold3d_compatible(mesh: trimesh.Trimesh) -> bool:
    import manifold3d

    m3d_mesh = manifold3d.Mesh(
        vert_properties=np.ascontiguousarray(mesh.vertices, dtype=np.float32),
        tri_verts=np.ascontiguousarray(mesh.faces, dtype=np.uint32),
    )
    manifold = manifold3d.Manifold(m3d_mesh)
    return manifold.status() == manifold3d.Error.NoError and not manifold.is_empty()


def _count_open_boundary_edges(mesh: trimesh.Trimesh) -> int:
    if len(mesh.faces) == 0:
        return 0
    _, counts = np.unique(mesh.edges_sorted, axis=0, return_counts=True)
    return int((counts == 1).sum())


def _count_connected_components(mesh: trimesh.Trimesh) -> int:
    if len(mesh.faces) == 0:
        return 0
    return len(mesh.split(only_watertight=False))


def validate_mesh(mesh: trimesh.Trimesh) -> MeshValidationResult:
    has_nan_or_inf = not bool(np.all(np.isfinite(mesh.vertices)))
    has_degenerate = not bool(mesh.nondegenerate_faces().all()) if len(mesh.faces) else True

    return MeshValidationResult(
        is_watertight=bool(mesh.is_watertight),
        is_winding_consistent=bool(mesh.is_winding_consistent),
        volume_mm3=float(mesh.volume) if not has_nan_or_inf else float("nan"),
        euler_number=int(mesh.euler_number),
        has_degenerate_faces=has_degenerate,
        has_nan_or_inf=has_nan_or_inf,
        bounds_mm=tuple(map(tuple, mesh.bounds.tolist())),
        manifold3d_compatible=_check_manifold3d_compatible(mesh) if not has_nan_or_inf else False,
        connected_components=_count_connected_components(mesh),
        open_boundary_edge_count=_count_open_boundary_edges(mesh),
    )
