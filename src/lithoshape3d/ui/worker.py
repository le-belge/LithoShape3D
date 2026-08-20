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

from lithoshape3d.core.geometry.composition import ZoneSource, compose_scene_mesh
from lithoshape3d.core.geometry.heightmap import heightmap_from_image_path
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.image.preprocessing import resize_array
from lithoshape3d.core.scene.models import GeometryParameters
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


class CompositionWorker(QRunnable):
    """Genere le mesh compose (toutes les zones visibles, dans l'ordre
    Scene.zones) en arriere-plan. Meme discipline que GenerationWorker :
    aucun widget touche, resultats uniquement via signaux."""

    def __init__(self, zone_sources: list[ZoneSource]) -> None:
        super().__init__()
        self.zone_sources = zone_sources
        self.signals = GenerationSignals()

    def run(self) -> None:
        try:
            mesh = compose_scene_mesh(self.zone_sources)
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
            self.signals.succeeded.emit(mesh)

        self.signals.finished.emit()
