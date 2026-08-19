"""Verifie automatiquement la regle : core -> aucune dependance Qt/PyVista/VTK.

Deux angles complementaires :
  1. analyse statique du code source de core/ (rapide, ne necessite aucun
     import) ;
  2. verification runtime : core doit rester importable meme si pyvista,
     pyvistaqt et PySide6 sont absents de l'environnement (execute dans un
     sous-processus isole pour ne pas dependre du cache d'imports du reste
     de la suite de tests).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BANNED_TOKENS = ("pyvista", "pyvistaqt", "pyside6", "pyside2", "pyqt5", "pyqt6", "vtkmodules", "import vtk")

CORE_DIR = Path(__file__).resolve().parents[1] / "src" / "lithoshape3d" / "core"


def _core_python_files() -> list[Path]:
    return sorted(CORE_DIR.rglob("*.py"))


def test_core_has_python_files_to_check():
    assert _core_python_files(), "core/ devrait contenir des fichiers .py"


def test_core_source_never_mentions_graphics_dependencies():
    offenders = []
    for path in _core_python_files():
        text = path.read_text(encoding="utf-8").lower()
        for token in BANNED_TOKENS:
            if token in text:
                offenders.append((path, token))

    assert not offenders, (
        "core/ ne doit jamais dependre de Qt/PyVista/VTK, trouve dans : "
        + ", ".join(f"{p.relative_to(CORE_DIR.parents[2])} ({t})" for p, t in offenders)
    )


def test_core_importable_without_qt_or_pyvista_installed():
    """Bloque volontairement pyvista/pyvistaqt/PySide6 (via sys.modules =
    None, qui force ImportError sur tout `import`) puis verifie que
    `lithoshape3d.core` s'importe et fonctionne quand meme."""
    script = """
import sys
for name in ("pyvista", "pyvistaqt", "PySide6", "vtk", "vtkmodules"):
    sys.modules[name] = None

import lithoshape3d.core  # noqa: F401
from lithoshape3d.core.geometry.heightmap import Heightmap
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.scene.models import GeometryParameters
from lithoshape3d.core.validation.mesh_checks import validate_mesh
import numpy as np

heightmap = Heightmap(values=np.full((4, 4), 0.5, dtype=np.float32))
params = GeometryParameters(width_mm=10.0, height_mm=10.0, resolution=3.0)
mesh = build_slab_mesh(heightmap, mask=None, params=params)
result = validate_mesh(mesh)
assert result.is_valid
print("CORE_HEADLESS_OK")
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CORE_HEADLESS_OK" in proc.stdout
