"""Backend SAM2.1 Small via Core ML (Apple, Apache 2.0).

Pipeline valide empiriquement (IoU > 0.99 sur images carrees et
rectangulaires) : encodeur d'image (1x par session) -> encodeur de prompt +
decodeur de masque (par clic, rapide une fois la forme "warmee").

`coremltools`, `huggingface_hub`, `cv2` et `PIL` sont importes uniquement
dans ce module -- jamais dans base.py/mock_backend.py, jamais dans core/.
"""

from __future__ import annotations

import logging

import numpy as np

from lithoshape3d.ai.segmentation.base import (
    SegmentationBackend,
    SegmentationPrompt,
    SegmentationSession,
)
from lithoshape3d.ai.segmentation.model_cache import MODEL_FILES, cache_dir, is_downloaded

logger = logging.getLogger("lithoshape3d.ai.sam2")

_ENCODER_INPUT_SIZE = 1024


class Sam2CoreMLSession(SegmentationSession):
    def __init__(
        self,
        prompt_encoder,
        mask_decoder,
        image_embedding,
        feats_s0,
        feats_s1,
        original_shape: tuple[int, int],
        scale_xy: tuple[float, float],
    ) -> None:
        self._prompt_encoder = prompt_encoder
        self._mask_decoder = mask_decoder
        self._image_embedding = image_embedding
        self._feats_s0 = feats_s0
        self._feats_s1 = feats_s1
        self._original_shape = original_shape
        self._scale_xy = scale_xy

    def segment(self, prompt: SegmentationPrompt) -> np.ndarray:
        rows, cols = self._original_shape
        if prompt.is_empty():
            return np.zeros((rows, cols), dtype=np.float32)

        scale_x, scale_y = self._scale_xy
        points: list[tuple[float, float]] = []
        labels: list[float] = []
        for x, y in prompt.positive_points:
            points.append((x * scale_x, y * scale_y))
            labels.append(1.0)
        for x, y in prompt.negative_points:
            points.append((x * scale_x, y * scale_y))
            labels.append(0.0)

        points_arr = np.array([points], dtype=np.float16)
        labels_arr = np.array([labels], dtype=np.float16)

        prompt_out = self._prompt_encoder.predict({"points": points_arr, "labels": labels_arr})
        decoder_out = self._mask_decoder.predict(
            {
                "image_embedding": self._image_embedding,
                "sparse_embedding": prompt_out["sparse_embeddings"],
                "dense_embedding": prompt_out["dense_embeddings"],
                "feats_s0": self._feats_s0,
                "feats_s1": self._feats_s1,
            }
        )

        masks = decoder_out["low_res_masks"][0]
        scores = decoder_out["scores"][0]
        best = int(np.argmax(scores))
        logits = masks[best].astype(np.float32)

        import cv2

        upsampled = cv2.resize(logits, (cols, rows), interpolation=cv2.INTER_LINEAR)
        probability = 1.0 / (1.0 + np.exp(-upsampled))
        return probability.astype(np.float32)


class Sam2CoreMLBackend(SegmentationBackend):
    name = "sam2-coreml"

    def __init__(self) -> None:
        self._image_encoder = None
        self._prompt_encoder = None
        self._mask_decoder = None

    def is_available(self) -> bool:
        try:
            import coremltools  # noqa: F401
        except ImportError:
            return False
        return is_downloaded()

    def _ensure_models_loaded(self) -> None:
        if self._image_encoder is not None:
            return
        import coremltools as ct

        directory = cache_dir()
        logger.info("Chargement des modeles SAM2 CoreML depuis %s", directory)
        self._image_encoder = ct.models.MLModel(str(directory / MODEL_FILES[0]))
        self._prompt_encoder = ct.models.MLModel(str(directory / MODEL_FILES[1]))
        self._mask_decoder = ct.models.MLModel(str(directory / MODEL_FILES[2]))

    def prepare_image(self, image: np.ndarray) -> Sam2CoreMLSession:
        from PIL import Image

        self._ensure_models_loaded()

        rows, cols = image.shape[:2]
        array_u8 = image if image.dtype == np.uint8 else (np.clip(image, 0.0, 1.0) * 255).astype(np.uint8)
        if array_u8.ndim == 2:
            array_u8 = np.stack([array_u8] * 3, axis=-1)

        pil_image = Image.fromarray(array_u8, mode="RGB").resize(
            (_ENCODER_INPUT_SIZE, _ENCODER_INPUT_SIZE)
        )
        encoder_out = self._image_encoder.predict({"image": pil_image})

        scale_xy = (_ENCODER_INPUT_SIZE / cols, _ENCODER_INPUT_SIZE / rows)
        return Sam2CoreMLSession(
            self._prompt_encoder,
            self._mask_decoder,
            encoder_out["image_embedding"],
            encoder_out["feats_s0"],
            encoder_out["feats_s1"],
            (rows, cols),
            scale_xy,
        )
