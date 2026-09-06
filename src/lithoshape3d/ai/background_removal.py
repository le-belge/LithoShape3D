"""Detourage automatique d'image entiere via rembg (ISNet, ONNX Runtime).

Complementaire du moteur SAM2 (ai/segmentation/) : SAM2 est un moteur
*prompte* (points positifs/negatifs, cf. ai/segmentation/base.py) qui
demande un clic utilisateur et ne tourne que sur macOS (CoreML). Ce module
isole automatiquement le sujet principal d'une image sans aucune
interaction, et fonctionne sur toute plateforme (Windows/Linux/macOS).

Modele "isnet-general-use" plutot que le u2net par defaut de rembg :
verifie sur une vraie photo (portrait a mise au point selective), u2net
traite l'objet le plus net comme le seul sujet "saillant" et assigne une
alpha tres faible au reste du sujet (visage flou quasi-transparent) --
isnet-general-use degage un masque bien plus complet et net, qualite
comparable a un service de detourage grand public.

Meme discipline que ai/segmentation/model_cache.py : rien n'est telecharge
automatiquement en arriere-plan, uniquement a la demande explicite de
l'utilisateur (voir ui/main_window.py). Une fois telecharge, tout tourne
localement : aucune image utilisateur ne quitte la machine.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

MODEL_NAME = "isnet-general-use"
MODEL_FILENAME = "isnet-general-use.onnx"
APPROX_SIZE_MB = 179
LICENSE = "MIT (rembg / ISNet)"


def cache_dir() -> Path:
    """Racine passee a rembg via U2NET_HOME (nom impose par rembg lui-meme,
    quel que soit le modele choisi) -- meme arbre que
    ai/segmentation/model_cache.cache_dir() (sous-dossier different,
    `rembg_home` au lieu de `sam2.1-small`, meme racine par
    utilisateur/plateforme). rembg cree lui-meme un sous-arbre
    `models/<nom>/<nom>.onnx` SOUS ce dossier (cf. `_model_file()`) --
    ne pas confondre avec le nom du modele lui-meme."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or str(Path.home()))
    else:
        base = Path.home() / ".cache"
    return base / "LithoShape3D" / "models" / "rembg_home"


def _model_file() -> Path:
    """Emplacement reel du poids telecharge par rembg sous U2NET_HOME --
    rembg range chaque modele dans `<U2NET_HOME>/models/<nom>/<nom>.onnx`,
    verifie empiriquement (ne pas supposer `<U2NET_HOME>/<fichier>`)."""
    return cache_dir() / "models" / MODEL_NAME / MODEL_FILENAME


def _set_u2net_home() -> None:
    """rembg lit U2NET_HOME au moment de l'import -- doit etre positionne
    avant tout `import rembg`, ici plutot que dans un import top-level de ce
    module pour rester lazy (jamais de cout au demarrage de l'app si
    rembg/onnxruntime ne sont pas installes)."""
    directory = cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    os.environ["U2NET_HOME"] = str(directory)


def is_downloaded() -> bool:
    return _model_file().is_file()


def download() -> None:
    """Declenche le telechargement du modele dans le cache utilisateur
    (rembg le fait lui-meme des la creation de la session s'il est absent)."""
    _set_u2net_home()
    from rembg import new_session

    new_session(MODEL_NAME)


_MIN_COMPONENT_AREA_RATIO = 0.01
"""Un ilot dont l'aire est sous ce ratio de la plus grande composante est
considere comme du bruit de matting (meche de cheveux isolee, esquille de
segmentation) et retire -- pas un vrai morceau disjoint du sujet."""

_EDGE_SMOOTHING_SIGMA_PX = 1.5
"""Ecart-type (px, resolution native de l'image -- pas encore
redimensionnee a la grille du panneau) du flou gaussien applique au
contour apres nettoyage morphologique : attenue les marches d'escalier en
dents de scie visibles une fois le masque devenu la silhouette de la piece
(retour terrain "artefacts qui genent autour du detourage"), sans deplacer
le contour global du sujet. `resize_array` (cf. `core/image/preprocessing.py`)
anti-aliase deja le redimensionnement vers la grille du panneau, mais ne
peut pas corriger un contour deja en dents de scie a la resolution
source -- ce lissage agit donc EN AMONT, sur le masque natif."""


def clean_alpha_mask(
    mask: np.ndarray,
    *,
    min_component_area_ratio: float = _MIN_COMPONENT_AREA_RATIO,
    smoothing_sigma_px: float = _EDGE_SMOOTHING_SIGMA_PX,
) -> np.ndarray:
    """Nettoie un masque de probabilite float32 [0,1] issu de la
    segmentation (rembg ou SAM2) : retire les ilots de bruit residuels,
    lisse les petites aigrettes en dents de scie du contour (ouverture puis
    fermeture morphologiques), et adoucit le contour final (flou gaussien
    leger, sans re-binariser -- le masque reste continu [0,1], meme
    contrat de sortie que l'entree).

    Retourne `mask` inchange si entierement vide (rien a nettoyer)."""
    from scipy import ndimage

    binary = mask >= 0.5
    if not binary.any():
        return mask

    labeled, count = ndimage.label(binary)
    if count > 1:
        sizes = ndimage.sum(binary, labeled, index=range(1, count + 1))
        largest = sizes.max()
        keep = [i + 1 for i, size in enumerate(sizes) if size >= largest * min_component_area_ratio]
        binary = np.isin(labeled, keep)

    structure = ndimage.generate_binary_structure(2, 2)
    binary = ndimage.binary_opening(binary, structure=structure, iterations=1)
    binary = ndimage.binary_closing(binary, structure=structure, iterations=1)
    if not binary.any():
        # Nettoyage trop agressif pour un sujet trop fin/petit a cette
        # resolution -- mieux vaut garder le masque d'origine (silhouette
        # brute) qu'un masque entierement vide.
        return mask

    smoothed = ndimage.gaussian_filter(binary.astype(np.float32), sigma=smoothing_sigma_px)
    return smoothed


def remove_background(image: Image.Image) -> np.ndarray:
    """Retourne un masque de probabilite float32 [0,1], meme resolution que
    `image` (H, W) -- 1.0 = sujet, 0.0 = fond. Meme contrat de sortie que
    SegmentationSession.segment() (ai/segmentation/base.py) pour rester
    utilisable partout ou un masque continu est attendu, meme si ce n'est
    pas formellement le meme protocole (pas de prompt par points ici).

    Le masque brut de rembg est ensuite nettoye (`clean_alpha_mask`) avant
    d'etre retourne -- retour terrain : des artefacts en dents de scie
    (bruit de matting, meches isolees) genaient autour du contour une fois
    la photo decoupee a cette silhouette."""
    _set_u2net_home()
    from rembg import new_session, remove

    session = new_session(MODEL_NAME)
    mask = remove(image, session=session, only_mask=True)
    raw_mask = np.asarray(mask, dtype=np.float32) / 255.0
    return clean_alpha_mask(raw_mask)
