"""Benchmark manuel Phase 2B : temps/memoire de generation pour des masques
irreguliers (silhouette, anneau, ilots), a une resolution realiste et fine.

Usage :
    python scripts/benchmark_masked_mesh.py
"""

from __future__ import annotations

import time

import numpy as np

from lithoshape3d.core.geometry.heightmap import Heightmap, grid_dimensions
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.scene.models import GeometryParameters
from lithoshape3d.core.validation.mesh_checks import validate_mesh

WIDTH_MM, HEIGHT_MM = 150.0, 100.0


def circle_mask(rows: int, cols: int) -> np.ndarray:
    yy, xx = np.mgrid[0:rows, 0:cols]
    cy, cx = rows / 2, cols / 2
    radius = min(rows, cols) / 3
    return ((yy - cy) ** 2 + (xx - cx) ** 2) <= radius**2


def ring_mask(rows: int, cols: int) -> np.ndarray:
    yy, xx = np.mgrid[0:rows, 0:cols]
    cy, cx = rows / 2, cols / 2
    r_outer = min(rows, cols) / 2.5
    r_inner = r_outer / 2.2
    dist2 = (yy - cy) ** 2 + (xx - cx) ** 2
    return (dist2 <= r_outer**2) & (dist2 >= r_inner**2)


def concave_star_mask(rows: int, cols: int) -> np.ndarray:
    yy, xx = np.mgrid[0:rows, 0:cols]
    cy, cx = rows / 2, cols / 2
    dy, dx = yy - cy, xx - cx
    angle = np.arctan2(dy, dx)
    dist = np.sqrt(dy**2 + dx**2)
    max_r = min(rows, cols) / 2.2
    star_radius = max_r * (0.5 + 0.5 * np.cos(5 * angle))
    return dist <= star_radius


def two_islands_mask(rows: int, cols: int) -> np.ndarray:
    mask = np.zeros((rows, cols), dtype=bool)
    mask[rows // 8 : rows // 3, cols // 8 : cols // 3] = True
    mask[2 * rows // 3 : rows - rows // 8, 2 * cols // 3 : cols - cols // 8] = True
    return mask

MASKS = {
    "masque simple (cercle)": circle_mask,
    "silhouette irreguliere (etoile)": concave_star_mask,
    "anneau (trou)": ring_mask,
    "plusieurs ilots": two_islands_mask,
}


def run_case(name: str, mask_fn, resolution: float) -> None:
    params = GeometryParameters(width_mm=WIDTH_MM, height_mm=HEIGHT_MM, resolution=resolution)
    rows, cols = grid_dimensions(params)

    rng = np.random.default_rng(0)
    values = rng.random((rows, cols)).astype(np.float32)
    heightmap = Heightmap(values=values)
    mask = mask_fn(rows, cols).astype(np.float32)

    start = time.perf_counter()
    mesh = build_slab_mesh(heightmap, mask=mask, params=params)
    build_elapsed = time.perf_counter() - start

    start = time.perf_counter()
    result = validate_mesh(mesh)
    validate_elapsed = time.perf_counter() - start

    mem_mb = (mesh.vertices.nbytes + mesh.faces.nbytes) / (1024 * 1024)

    print(
        f"{name:32s} | res={resolution:4.2f} mm/px | grille {rows}x{cols} | "
        f"{len(mesh.vertices):>8,} sommets | {len(mesh.faces):>8,} faces | "
        f"build {build_elapsed * 1000:7.1f} ms | validate {validate_elapsed * 1000:7.1f} ms | "
        f"{mem_mb:6.2f} MB | valid={result.is_valid} | composants={result.connected_components}"
    )


if __name__ == "__main__":
    print("Benchmark generation de mesh masque (Phase 2B), heightmap aleatoire (pire cas)")
    for resolution in (0.3, 0.15):
        for name, mask_fn in MASKS.items():
            run_case(name, mask_fn, resolution)
        print()
