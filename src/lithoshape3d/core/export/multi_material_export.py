"""Export multi-materiau : un fichier 3MF standard multi-objets en priorite,
avec repli propre sur un STL par materiau si le 3MF echoue.

Ne connait ni la geometrie ni l'interface utilisateur : recoit des meshes
deja construits (issus de `core/geometry/materials.py`, deja alignes sur le
meme repere XYZ) et des chemins, rien d'autre.

Choix delibere : 3MF standard (via `trimesh.Scene`, sans dependance
supplementaire au-dela de `lxml`/`networkx` deja necessaires a
`trimesh[easy]`), PAS le format `.3mf` proprietaire Bambu Studio (qui
embarque des parametres internes specifiques au slicer). L'objectif est
qu'un slicer tiers (Bambu Studio inclus) importe ce fichier avec plusieurs
objets deja parfaitement alignes, puis laisse l'utilisateur affecter chaque
objet a un filament -- pas de reverse engineering du format proprietaire.
"""

from __future__ import annotations

import re
from pathlib import Path

import trimesh


def _safe_filename_component(name: str) -> str:
    """Nom de materiau -> composant de nom de fichier sûr (pas d'espaces, pas
    de caracteres speciaux) : ex. "Rose vif" -> "Rose_vif"."""
    cleaned = re.sub(r"[^\w\-]+", "_", name.strip())
    return cleaned.strip("_") or "materiau"


def export_multi_material_3mf(material_meshes: dict[str, trimesh.Trimesh], path: str | Path) -> None:
    """Ecrit un unique fichier .3mf standard, un objet nomme par materiau.

    Leve toute exception rencontree (a charge de l'appelant de basculer sur
    `export_stl_per_material` si l'export 3MF echoue -- voir la note de
    module sur le principe de repli)."""
    path = Path(path)
    scene = trimesh.Scene()
    for material_name, mesh in material_meshes.items():
        scene.add_geometry(mesh, node_name=material_name, geom_name=material_name)
    scene.export(path, file_type="3mf")


def export_stl_per_material(
    material_meshes: dict[str, trimesh.Trimesh], directory: str | Path, base_name: str
) -> list[Path]:
    """Repli : un fichier STL par materiau, tous dans le meme repere XYZ (ils
    n'ont subi aucun recadrage independant -- importes ensemble dans un
    slicer, ils s'alignent sans deplacement manuel). Noms explicites :
    `{base_name}_{MATERIAU}.stl`. Retourne la liste des chemins ecrits."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    written_paths = []
    for material_name, mesh in material_meshes.items():
        filename = f"{base_name}_{_safe_filename_component(material_name).upper()}.stl"
        output_path = directory / filename
        mesh.export(output_path, file_type="stl")
        written_paths.append(output_path)
    return written_paths
