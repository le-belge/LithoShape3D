"""Validation minimale d'imprimabilite (Shape Composer v0.4, mission 2.16) :
composantes disjointes, dimensions nulles/invalides, elements tres fins si
facilement detectables, dimensions physiques finales.

Volontairement minimal -- prepare une API pour une future "Print
Intelligence" plus complete (calibration filament, profils imprimante...),
sans la construire maintenant (hors perimetre 0.4, cf. 2.21). S'appuie sur
`validate_mesh` pour la couche "geometriquement correcte" (watertight/
manifold/volume) ; ce module ajoute la couche "imprimable en pratique",
separee et complementaire."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh
from scipy import ndimage

from lithoshape3d.core.geometry.shape import count_connected_components
from lithoshape3d.core.validation.mesh_checks import MeshValidationResult, validate_mesh

_MIN_REASONABLE_DIMENSION_MM = 1.0
"""En dessous, une dimension est consideree invalide/inutilisable en
pratique -- pas une limite d'imprimante specifique, juste un garde-fou
contre un mesh degenere ou vide."""


@dataclass(frozen=True)
class PrintabilityReport:
    mesh_validation: MeshValidationResult
    width_mm: float
    height_mm: float
    depth_mm: float
    disjoint_components: int
    """Composantes disjointes de la silhouette (ShapeMask si fourni, sinon
    du mesh) -- jamais reliees automatiquement (cf. 2.10), purement
    informatif pour l'utilisateur/l'UI."""
    thin_regions_detected: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_printable(self) -> bool:
        return not self.errors and self.mesh_validation.is_valid


def _thin_regions_detected(shape_mask: np.ndarray, pixel_size_mm: float, min_feature_mm: float) -> bool:
    """Detection volontairement simple (pas de squelette/distance-transform
    complet) : erode le masque 2D d'un rayon correspondant a la moitie de
    `min_feature_mm`. Si une composante entiere disparait sous l'erosion,
    un element plus fin que `min_feature_mm` existe quelque part."""
    if not shape_mask.any() or pixel_size_mm <= 0:
        return False
    radius_px = max(1, round((min_feature_mm / 2.0) / pixel_size_mm))
    eroded = ndimage.binary_erosion(shape_mask, iterations=radius_px)
    labeled_before, count_before = ndimage.label(shape_mask)
    if count_before == 0:
        return False
    survives = set(np.unique(labeled_before[eroded]))
    survives.discard(0)
    return len(survives) < count_before


def check_printability(
    mesh: trimesh.Trimesh,
    *,
    shape_mask: np.ndarray | None = None,
    pixel_size_mm: float | None = None,
    min_feature_mm: float = 0.8,
) -> PrintabilityReport:
    """`shape_mask`/`pixel_size_mm` optionnels : sans eux, la detection de
    composantes disjointes retombe sur le mesh 3D et la detection
    d'elements fins est simplement ignoree (le mesh seul ne suffit pas a la
    faire de facon fiable)."""
    mesh_result = validate_mesh(mesh)
    (min_x, min_y, min_z), (max_x, max_y, max_z) = mesh_result.bounds_mm
    width_mm = max_x - min_x
    height_mm = max_y - min_y
    depth_mm = max_z - min_z

    warnings: list[str] = []
    errors: list[str] = []

    for label, value in (("largeur", width_mm), ("hauteur", height_mm), ("epaisseur", depth_mm)):
        if not np.isfinite(value) or value <= 0:
            errors.append(f"dimension {label} invalide ou nulle ({value})")
        elif value < _MIN_REASONABLE_DIMENSION_MM:
            warnings.append(f"dimension {label} tres petite ({value:.2f} mm)")

    if shape_mask is not None:
        disjoint = count_connected_components(shape_mask)
    else:
        disjoint = mesh_result.connected_components

    if disjoint > 1:
        warnings.append(
            f"{disjoint} composantes disjointes dans la silhouette "
            "(jamais reliees automatiquement -- verifiez que c'est voulu avant impression)"
        )

    thin = False
    if shape_mask is not None and pixel_size_mm:
        thin = _thin_regions_detected(shape_mask, pixel_size_mm, min_feature_mm)
        if thin:
            warnings.append(
                f"des elements plus fins que {min_feature_mm:.1f} mm ont ete detectes "
                "(risque de casse ou d'impression manquante selon l'imprimante)"
            )

    if not mesh_result.is_valid:
        errors.extend(mesh_result.issues())

    return PrintabilityReport(
        mesh_validation=mesh_result,
        width_mm=width_mm,
        height_mm=height_mm,
        depth_mm=depth_mm,
        disjoint_components=disjoint,
        thin_regions_detected=thin,
        warnings=warnings,
        errors=errors,
    )
