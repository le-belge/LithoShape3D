"""Conversion mesh interne (trimesh) -> pyvista.PolyData.

Fonction pure, sans fenetre ni contexte graphique : testable sans ouvrir de
Qt. N'effectue aucune reparation ni recalcul -- le viewer affiche exactement
ce que produit le core. Si le mesh source est invalide, cela doit rester
visible (responsabilite de core/validation, pas du viewer).
"""

from __future__ import annotations

import numpy as np
import pyvista as pv
import trimesh


def mesh_to_polydata(mesh: trimesh.Trimesh) -> pv.PolyData:
    """Convertit un trimesh.Trimesh en pyvista.PolyData sans modifier `mesh`."""
    face_count = len(mesh.faces)
    padded_faces = np.empty((face_count, 4), dtype=np.int64)
    padded_faces[:, 0] = 3
    padded_faces[:, 1:] = mesh.faces
    return pv.PolyData(mesh.vertices.copy(), padded_faces.ravel())
