"""Base de logging minimale : fichier + console, jamais de traceback brut a l'ecran."""

from __future__ import annotations

import logging
from pathlib import Path

_LOGGER_NAME = "lithoshape3d"


def configure_logging() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger  # deja configure (evite les handlers dupliques)

    logger.setLevel(logging.INFO)

    log_dir = Path.home() / "Library" / "Logs" / "LithoShape3D"
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
