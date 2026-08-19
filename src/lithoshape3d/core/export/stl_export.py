"""Export/import STL. Ne connait ni la geometrie ni l'interface utilisateur :
recoit un mesh deja construit et un chemin, rien d'autre.
"""

from __future__ import annotations

from pathlib import Path

import trimesh


def export_stl(mesh: trimesh.Trimesh, path: str | Path) -> None:
    path = Path(path)
    mesh.export(path, file_type="stl")


def load_stl(path: str | Path) -> trimesh.Trimesh:
    """Le format STL binaire ne stocke aucun sommet partage (triangle soup) :
    `process=True` fusionne les sommets coincidents pour retrouver la
    topologie fermee d'origine (sans quoi le mesh releche parait non
    watertight alors qu'il ne l'est pas geometriquement)."""
    path = Path(path)
    return trimesh.load(path, file_type="stl", process=True)
