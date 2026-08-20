"""Interface abstraite de segmentation assistee. Zero dependance IA.

Le reste de LithoShape3D (core, ui) ne connait que cette interface et le
tableau `float32 [0,1]` resultant -- exactement le meme contrat que les
masques manuels de la Phase 2A. Aucun module ici n'importe SAM2, CoreML,
PyTorch ou ONNX : ces imports restent confines aux backends concrets
(sam2_coreml_backend.py), charges paresseusement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass
class SegmentationPrompt:
    positive_points: list[tuple[float, float]] = field(default_factory=list)
    negative_points: list[tuple[float, float]] = field(default_factory=list)
    box: tuple[float, float, float, float] | None = None  # (x0, y0, x1, y1)

    def is_empty(self) -> bool:
        return not self.positive_points and not self.negative_points and self.box is None


class SegmentationSession(ABC):
    """Une session encode UNE image une seule fois (cf. `prepare_image`) puis
    repond a plusieurs prompts sans recalculer l'encodage."""

    @abstractmethod
    def segment(self, prompt: SegmentationPrompt) -> np.ndarray:
        """Retourne un masque float32 [0,1] a la resolution EXACTE de l'image
        passee a `prepare_image` -- pas de crop/decalage/changement de ratio."""


class SegmentationBackend(ABC):
    name: str = "backend"

    @abstractmethod
    def is_available(self) -> bool:
        """False si les dependances/le modele ne sont pas prets (ne doit
        jamais lever : simple verification, utilisee pour piloter le
        fallback UX vers l'edition manuelle)."""

    @abstractmethod
    def prepare_image(self, image: np.ndarray) -> SegmentationSession:
        """image : float32 [0,1] ou uint8, HxW (niveaux de gris) ou HxWx3 (RGB)."""
