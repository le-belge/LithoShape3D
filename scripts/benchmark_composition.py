"""Benchmark manuel Phase 2C : composition de 2/5/10 zones (avec overlaps),
en distinguant le cout de chaque etape (contributions+composition NumPy vs
construction du mesh vs validation).

Usage :
    python scripts/benchmark_composition.py
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

from lithoshape3d.core.geometry.composition import ZoneSource, compose_scene_heightfield
from lithoshape3d.core.geometry.mesh_builder import build_mesh_from_heightfield
from lithoshape3d.core.scene.models import CompositionMode, GeometryParameters, ReliefMode, Zone
from lithoshape3d.core.validation.mesh_checks import validate_mesh

WIDTH_MM, HEIGHT_MM = 150.0, 100.0


def _make_image(path: Path, value: int, width: int, height: int) -> None:
    array = np.full((height, width), value, dtype=np.uint8)
    Image.fromarray(array, mode="L").save(path)


def _make_zone_sources(n_zones: int, resolution: float, tmp_dir: Path) -> list[ZoneSource]:
    params = GeometryParameters(width_mm=WIDTH_MM, height_mm=HEIGHT_MM, resolution=resolution)
    rows = round(HEIGHT_MM / resolution)
    cols = round(WIDTH_MM / resolution)

    base_image = tmp_dir / "base.png"
    _make_image(base_image, 128, cols, rows)
    base_zone = Zone(name="Base", composition_mode=CompositionMode.BASE, geometry_params=params)
    sources = [ZoneSource(zone=base_zone, image_path=str(base_image))]

    rng = np.random.default_rng(0)
    for i in range(n_zones - 1):
        add_image = tmp_dir / f"add_{i}.png"
        _make_image(add_image, 0, cols, rows)
        mask = np.zeros((rows, cols), dtype=np.float32)
        # rectangles se chevauchant partiellement pour simuler des overlaps reels
        r0 = rng.integers(0, max(1, rows - rows // 4))
        c0 = rng.integers(0, max(1, cols - cols // 4))
        mask[r0 : r0 + rows // 4, c0 : c0 + cols // 4] = 1.0
        zone = Zone(
            name=f"Add {i}",
            composition_mode=CompositionMode.ADD,
            relief_mode=ReliefMode.SOLID,
            geometry_params=GeometryParameters(
                width_mm=WIDTH_MM, height_mm=HEIGHT_MM, resolution=resolution,
                min_thickness_mm=0.3, max_thickness_mm=0.3,
            ),
        )
        sources.append(ZoneSource(zone=zone, image_path=str(add_image), mask=mask))

    return sources


def run_case(n_zones: int, resolution: float, tmp_dir: Path) -> None:
    sources = _make_zone_sources(n_zones, resolution, tmp_dir)

    start = time.perf_counter()
    z_final, active_final, width_mm, height_mm = compose_scene_heightfield(sources)
    compose_elapsed = time.perf_counter() - start

    start = time.perf_counter()
    mesh = build_mesh_from_heightfield(z_final, active_final, width_mm, height_mm)
    build_elapsed = time.perf_counter() - start

    start = time.perf_counter()
    result = validate_mesh(mesh)
    validate_elapsed = time.perf_counter() - start

    mem_mb = (mesh.vertices.nbytes + mesh.faces.nbytes) / (1024 * 1024)

    print(
        f"{n_zones:>2} zones | res={resolution:4.2f} mm/px | "
        f"{len(mesh.vertices):>8,} sommets | {len(mesh.faces):>8,} faces | "
        f"compose {compose_elapsed * 1000:7.1f} ms | build {build_elapsed * 1000:7.1f} ms | "
        f"validate {validate_elapsed * 1000:7.1f} ms | {mem_mb:6.2f} MB | "
        f"valid={result.is_valid} | composantes={result.connected_components}"
    )


if __name__ == "__main__":
    print("Benchmark composition multi-zone (Phase 2C) - overlaps aleatoires entre zones ADD")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for resolution in (0.3, 0.15):
            for n_zones in (2, 5, 10):
                run_case(n_zones, resolution, tmp_dir)
            print()
