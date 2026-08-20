from lithoshape3d.core.geometry.composition import (
    ZoneSource,
    compose_scene_heightfield,
    compose_scene_mesh,
)
from lithoshape3d.core.geometry.heightmap import (
    Heightmap,
    build_heightmap,
    grid_dimensions,
    height_mm_from_aspect_ratio,
    heightmap_from_image_path,
)
from lithoshape3d.core.geometry.mesh_builder import build_mesh_from_heightfield, build_slab_mesh
from lithoshape3d.core.geometry.relief import compute_zone_contribution_mm
from lithoshape3d.core.geometry.thickness import compute_thickness_mm

__all__ = [
    "Heightmap",
    "ZoneSource",
    "build_heightmap",
    "build_mesh_from_heightfield",
    "build_slab_mesh",
    "compose_scene_heightfield",
    "compose_scene_mesh",
    "compute_thickness_mm",
    "compute_zone_contribution_mm",
    "grid_dimensions",
    "height_mm_from_aspect_ratio",
    "heightmap_from_image_path",
]
