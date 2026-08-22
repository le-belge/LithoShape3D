"""Worker Qt (QRunnable) pour generer un mesh en arriere-plan.

Aucun widget n'est manipule ici : le worker ne fait que calculer et emettre
des signaux (`succeeded`/`failed`/`finished`). Qt met automatiquement les
connexions cross-thread en file d'attente vers le thread principal, donc les
slots connectes peuvent modifier l'UI sans precaution particuliere.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Signal

from lithoshape3d.core.geometry.backlight import compose_backlight_bodies
from lithoshape3d.core.geometry.composition import ZoneSource, compose_scene_mesh
from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.geometry.support import attach_support
from lithoshape3d.core.image.preprocessing import resize_array
from lithoshape3d.core.scene.models import (
    GeometryParameters,
    ImageTransform,
    PrintSupport,
    SupportType,
)
from lithoshape3d.core.validation.mesh_checks import validate_mesh

logger = logging.getLogger("lithoshape3d.worker")


class GenerationSignals(QObject):
    succeeded = Signal(object)  # trimesh.Trimesh
    failed = Signal(str)
    finished = Signal()


class GenerationWorker(QRunnable):
    def __init__(
        self,
        image_path: str,
        params: GeometryParameters,
        brightness: float = 0.0,
        contrast: float = 1.0,
        mask: np.ndarray | None = None,
    ) -> None:
        super().__init__()
        self.image_path = image_path
        self.params = params
        self.brightness = brightness
        self.contrast = contrast
        self.mask = mask
        self.signals = GenerationSignals()

    def run(self) -> None:
        try:
            heightmap = heightmap_from_image_path(
                self.image_path, self.params, brightness=self.brightness, contrast=self.contrast
            )
            mask = self.mask
            if mask is not None and mask.shape != heightmap.shape:
                mask = resize_array(mask, width_px=heightmap.shape[1], height_px=heightmap.shape[0])
            mesh = build_slab_mesh(heightmap, mask=mask, params=self.params)
            result = validate_mesh(mesh)
        except NotImplementedError as exc:
            logger.info("Generation refusee (fonctionnalite non supportee) : %s", exc)
            self.signals.failed.emit(str(exc))
            self.signals.finished.emit()
            return
        except (ValueError, OSError, RuntimeError) as exc:
            logger.exception("Echec de generation de la lithophanie")
            self.signals.failed.emit(str(exc))
            self.signals.finished.emit()
            return

        if not result.is_valid:
            message = "Mesh invalide : " + ", ".join(result.issues())
            logger.error(message)
            self.signals.failed.emit(message)
        else:
            logger.info(
                "Mesh genere : %d sommets, %d faces, volume=%.1f mm3",
                len(mesh.vertices),
                len(mesh.faces),
                result.volume_mm3,
            )
            self.signals.succeeded.emit(mesh)

        self.signals.finished.emit()


class CompositionSignals(QObject):
    succeeded = Signal(object, float)  # trimesh.Trimesh, panel_z_max (avant fusion du pied)
    failed = Signal(str)
    finished = Signal()


class CompositionWorker(QRunnable):
    """Genere le mesh compose (toutes les zones visibles, dans l'ordre
    Scene.zones) en arriere-plan, puis y fusionne le pied d'impression le cas
    echeant. Meme discipline que GenerationWorker : aucun widget touche,
    resultats uniquement via signaux."""

    def __init__(
        self,
        zone_sources: list[ZoneSource],
        support: PrintSupport | None = None,
        image_transform: ImageTransform | None = None,
        shape_mask: np.ndarray | None = None,
    ) -> None:
        super().__init__()
        self.zone_sources = zone_sources
        self.support = support or PrintSupport()
        self.image_transform = image_transform
        self.shape_mask = shape_mask
        self.signals = CompositionSignals()

    def run(self) -> None:
        try:
            mesh = compose_scene_mesh(
                self.zone_sources, image_transform=self.image_transform, shape_mask=self.shape_mask
            )
            panel_z_max = float(mesh.vertices[:, 2].max())
            if self.support.support_type is not SupportType.NONE:
                mesh = attach_support(mesh, self.support)
            result = validate_mesh(mesh)
        except NotImplementedError as exc:
            logger.info("Composition refusee (fonctionnalite non supportee) : %s", exc)
            self.signals.failed.emit(str(exc))
            self.signals.finished.emit()
            return
        except (ValueError, OSError, RuntimeError) as exc:
            logger.exception("Echec de la composition multi-zone")
            self.signals.failed.emit(str(exc))
            self.signals.finished.emit()
            return

        if not result.is_valid:
            message = "Composition invalide : " + ", ".join(result.issues())
            logger.error(message)
            self.signals.failed.emit(message)
        else:
            logger.info(
                "Composition generee : %d sommets, %d faces, volume=%.1f mm3, %d composante(s)",
                len(mesh.vertices),
                len(mesh.faces),
                result.volume_mm3,
                result.connected_components,
            )
            self.signals.succeeded.emit(mesh, panel_z_max)

        self.signals.finished.emit()


class BacklightCompositionSignals(QObject):
    succeeded = Signal(object, object, float)
    """(BacklightComposition PANNEAU SEUL -- jamais de pied fusionne dedans,
    meme convention que `_current_material_meshes` -- mesh blanc AVEC pied
    fusionne le cas echeant, panel_z_max avant fusion du pied)."""
    failed = Signal(str)
    finished = Signal()


class BacklightCompositionWorker(QRunnable):
    """Comme `CompositionWorker`, mais pour au moins une Zone
    `ColorStrategy.BACKLIGHT_INSERT` : produit un corps blanc (avec cavites)
    ET un insert independant par materiau, cf. core/geometry/backlight.py.
    Le pied d'impression (le cas echeant) se fusionne a une COPIE du corps
    blanc pour l'affichage/export "Geometrie" -- le resultat panneau-seul
    reste disponible separement, comme pour `CompositionWorker`/
    `partition_mesh_by_material` (le pied redevient un corps distinct pour
    la vue/export Materiaux)."""

    def __init__(
        self,
        zone_sources: list[ZoneSource],
        support: PrintSupport | None = None,
        image_transform: ImageTransform | None = None,
        shape_mask: np.ndarray | None = None,
    ) -> None:
        super().__init__()
        self.zone_sources = zone_sources
        self.support = support or PrintSupport()
        self.image_transform = image_transform
        self.shape_mask = shape_mask
        self.signals = BacklightCompositionSignals()

    def run(self) -> None:
        try:
            result = compose_backlight_bodies(
                self.zone_sources, image_transform=self.image_transform, shape_mask=self.shape_mask
            )
            panel_z_max = float(result.white_mesh.vertices[:, 2].max())
            fused_white_mesh = result.white_mesh
            if self.support.support_type is not SupportType.NONE:
                fused_white_mesh = attach_support(fused_white_mesh, self.support)
            fused_validation = validate_mesh(fused_white_mesh)
        except NotImplementedError as exc:
            logger.info("Composition Backlight Insert refusee (fonctionnalite non supportee) : %s", exc)
            self.signals.failed.emit(str(exc))
            self.signals.finished.emit()
            return
        except (ValueError, OSError, RuntimeError) as exc:
            logger.exception("Echec de la composition Backlight Insert")
            self.signals.failed.emit(str(exc))
            self.signals.finished.emit()
            return

        insert_issues = [
            f"{name} : {', '.join(validate_mesh(mesh).issues())}"
            for name, mesh in result.insert_meshes.items()
            if not validate_mesh(mesh).is_valid
        ]
        if not fused_validation.is_valid or insert_issues:
            parts = []
            if not fused_validation.is_valid:
                parts.append("corps blanc invalide : " + ", ".join(fused_validation.issues()))
            parts.extend(insert_issues)
            message = "Composition Backlight Insert invalide : " + " | ".join(parts)
            logger.error(message)
            self.signals.failed.emit(message)
        else:
            for warning in result.warnings:
                logger.warning(warning)
            logger.info(
                "Backlight Insert genere : corps blanc %d composante(s), %d insert(s) distinct(s)",
                fused_validation.connected_components,
                len(result.insert_meshes),
            )
            self.signals.succeeded.emit(result, fused_white_mesh, panel_z_max)

        self.signals.finished.emit()
