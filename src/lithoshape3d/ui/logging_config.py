"""Base de logging minimale : fichier + console, jamais de traceback brut a l'ecran."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_LOGGER_NAME = "lithoshape3d"


def _platform_log_dir() -> Path:
    """Repertoire de logs standard par plateforme -- macOS et Windows ont des
    conventions differentes, ni l'une ni l'autre n'est un chemin sur (ni
    portable) sur l'autre systeme."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "LithoShape3D"
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "LithoShape3D" / "Logs"
    return Path.home() / ".local" / "state" / "LithoShape3D" / "logs"


def configure_logging() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger  # deja configure (evite les handlers dupliques)

    logger.setLevel(logging.INFO)

    log_dir = _platform_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_dir / "lithoshape3d.log")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(console_handler)

    return logger
