"""Benchmark manuel : mesure temps/memoire de generation pour differentes
resolutions. Pas de framework de benchmark, juste un diagnostic rapide.

Usage :
    python scripts/benchmark_mesh.py
"""

from __future__ import annotations

import time

import numpy as np

from lithoshape3d.core.geometry.heightmap import Heightmap, grid_dimensions
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.scene.models import GeometryParameters
from lithoshape3d.core.validation.mesh_checks import validate_mesh


def run_case(width_mm: float, height_mm: float, resolution: float) -> None:
    params = GeometryParameters(width_mm=width_mm, height_mm=height_mm, resolution=resolution)
    rows, cols = grid_dimensions(params)

    rng = np.random.default_rng(0)
    values = rng.random((rows, cols)).astype(np.float32)
    heightmap = Heightmap(values=values)

    start = time.perf_counter()
    mesh = build_slab_mesh(heightmap, mask=None, params=params)
    build_elapsed = time.perf_counter() - start

    start = time.perf_counter()
    result = validate_mesh(mesh)
    validate_elapsed = time.perf_counter() - start

    mem_mb = (mesh.vertices.nbytes + mesh.faces.nbytes) / (1024 * 1024)

    print(
        f"{rows:>5}x{cols:<5} px | {len(mesh.vertices):>9,} sommets | {len(mesh.faces):>9,} faces | "
        f"build {build_elapsed * 1000:7.1f} ms | validate {validate_elapsed * 1000:7.1f} ms | "
        f"{mem_mb:7.2f} MB | valid={result.is_valid}"
    )


if __name__ == "__main__":
    print("Benchmark generation de mesh (heightmap aleatoire, pire cas pour la compression)")
    print(f"{'grille':<13} | {'sommets':>17} | {'faces':>15} | {'build':>12} | {'validate':>15} | {'memoire':>10}")
    for resolution in (2.0, 1.0, 0.5, 0.3, 0.15):
        run_case(width_mm=150.0, height_mm=100.0, resolution=resolution)
