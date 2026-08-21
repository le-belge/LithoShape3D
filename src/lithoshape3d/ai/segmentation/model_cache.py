"""Telechargement/cache local du modele SAM2.1 Small Core ML (Apple, Apache
2.0). Rien n'est telecharge automatiquement en arriere-plan : uniquement a
la demande explicite de l'utilisateur (voir ui/segmentation_tool.py).

Apres telechargement, tout tourne localement : aucune image utilisateur ne
quitte la machine (le modele local ne fait ni requete reseau ni telemetrie).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

MODEL_REPO = "apple/coreml-sam2.1-small"
MODEL_FILES = (
    "SAM2_1SmallImageEncoderFLOAT16.mlpackage",
    "SAM2_1SmallPromptEncoderFLOAT16.mlpackage",
    "SAM2_1SmallMaskDecoderFLOAT16.mlpackage",
)
APPROX_SIZE_MB = 95
LICENSE = "Apache 2.0 (Apple / Meta)"


def cache_dir() -> Path:
    """En pratique n'est utilise que sur macOS (CoreML n'existe pas sur
    Windows/Linux -- voir Sam2CoreMLBackend.is_available()), mais reste
    defini pour toute plateforme par prudence."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or str(Path.home()))
    else:
        base = Path.home() / ".cache"
    return base / "LithoShape3D" / "models" / "sam2.1-small"


def is_downloaded() -> bool:
    directory = cache_dir()
    return all((directory / name).is_dir() for name in MODEL_FILES)


def download() -> Path:
    """Telecharge le modele dans le cache utilisateur. L'integrite de
    chaque fichier est verifiee par huggingface_hub pendant le
    telechargement (hachages du repo, telechargement repris si interrompu)."""
    from huggingface_hub import snapshot_download

    directory = cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        MODEL_REPO,
        local_dir=str(directory),
        allow_patterns=[f"{name}/**" for name in MODEL_FILES],
    )
    return directory
