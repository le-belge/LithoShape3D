"""Persistance des masques de zone.

Convention (identique en memoire, quelle que soit la source -- edition
manuelle ou future IA) :
    numpy.ndarray, dtype=float32, shape=(rows, cols), valeurs dans [0.0, 1.0]
    0.0 = exclu, 1.0 = inclus.

Sur disque : PNG niveaux de gris 8 bits (256 niveaux, suffisant pour du
feathering futur). Le PNG est uniquement un format de persistance ; l'API
en memoire reste toujours float32 [0,1].
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from lithoshape3d.core.image.preprocessing import resize_array
from lithoshape3d.core.scene.models import Zone


def mask_to_uint8(mask: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray((np.clip(mask, 0.0, 1.0) * 255).astype(np.uint8))


def mask_from_uint8(array_u8: np.ndarray) -> np.ndarray:
    return (array_u8.astype(np.float32)) / 255.0


def save_mask_array(path: str | Path, mask: np.ndarray) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask_to_uint8(mask), mode="L").save(path)


def load_mask_array(path: str | Path) -> np.ndarray:
    path = Path(path)
    array_u8 = np.asarray(Image.open(path).convert("L"), dtype=np.uint8)
    return mask_from_uint8(array_u8)


def load_zone_mask(project_dir: str | Path, zone: Zone, shape: tuple[int, int]) -> np.ndarray:
    """Masque float32 [0,1] a la forme demandee.

    `zone.mask_path` == None -> masque entierement actif (comportement par
    defaut, notamment pour la zone "Lithophanie"). Redimensionne
    automatiquement si le masque stocke ne correspond pas a `shape` (la
    resolution de travail peut differer de celle du masque enregistre).
    """
    if zone.mask_path is None:
        return np.ones(shape, dtype=np.float32)

    array = load_mask_array(Path(project_dir) / zone.mask_path)
    if array.shape != shape:
        array = resize_array(array, width_px=shape[1], height_px=shape[0])
    return array


def save_zone_mask(project_dir: str | Path, zone_id: str, mask: np.ndarray) -> str:
    """Ecrit `masks/<zone_id>.png` sous le bundle projet, retourne le chemin
    relatif a utiliser comme `Zone.mask_path`."""
    relative_path = f"masks/{zone_id}.png"
    save_mask_array(Path(project_dir) / relative_path, mask)
    return relative_path
