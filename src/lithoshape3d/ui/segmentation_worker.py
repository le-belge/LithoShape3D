"""Workers Qt pour la segmentation assistee (encodage + par-clic), meme
discipline que worker.py : aucun widget touche depuis le thread, resultats
uniquement via signaux.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Signal

from lithoshape3d.ai.segmentation.base import (
    SegmentationBackend,
    SegmentationPrompt,
    SegmentationSession,
)

logger = logging.getLogger("lithoshape3d.ai.worker")


class SegmentationSignals(QObject):
    session_ready = Signal(object)  # SegmentationSession
    mask_ready = Signal(object)  # np.ndarray
    failed = Signal(str)


class PrepareSessionWorker(QRunnable):
    """Encode l'image une seule fois (cf. contrat SegmentationBackend)."""

    def __init__(self, backend: SegmentationBackend, image: np.ndarray) -> None:
        super().__init__()
        self.backend = backend
        self.image = image
        self.signals = SegmentationSignals()

    def run(self) -> None:
        try:
            session = self.backend.prepare_image(self.image)
        except Exception as exc:
            logger.exception("Echec de la preparation de session de segmentation")
            self.signals.failed.emit(str(exc))
            return
        self.signals.session_ready.emit(session)


class SegmentWorker(QRunnable):
    def __init__(self, session: SegmentationSession, prompt: SegmentationPrompt) -> None:
        super().__init__()
        self.session = session
        self.prompt = prompt
        self.signals = SegmentationSignals()

    def run(self) -> None:
        try:
            mask = self.session.segment(self.prompt)
        except Exception as exc:
            logger.exception("Echec de la segmentation")
            self.signals.failed.emit(str(exc))
            return
        self.signals.mask_ready.emit(mask)


class DownloadModelSignals(QObject):
    finished = Signal()
    failed = Signal(str)


class DownloadModelWorker(QRunnable):
    """Telecharge le modele SAM2 CoreML vers le cache utilisateur (voir
    ai/segmentation/model_cache.py). Ne s'execute qu'a la demande explicite
    de l'utilisateur, jamais automatiquement."""

    def __init__(self) -> None:
        super().__init__()
        self.signals = DownloadModelSignals()

    def run(self) -> None:
        try:
            from lithoshape3d.ai.segmentation.model_cache import download

            download()
        except Exception as exc:
            logger.exception("Echec du telechargement du modele de segmentation")
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit()
