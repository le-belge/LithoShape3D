"""Tests de ai/background_removal.py -- rembg est mocke (aucun vrai
telechargement ni inference ONNX en CI). Les vraies capacites de detourage
sont verifiees manuellement (cf. plan de mission), pas par cette suite."""

import os
import sys
import types

import numpy as np
import pytest
from PIL import Image

from lithoshape3d.ai import background_removal


@pytest.fixture
def fake_rembg(monkeypatch):
    module = types.ModuleType("rembg")

    created_sessions = []

    def new_session(model_name):
        created_sessions.append(model_name)
        return object()

    def remove(image, session=None, only_mask=False):
        assert only_mask is True
        width, height = image.size
        mask = np.zeros((height, width), dtype=np.uint8)
        # Bloc plein (pas un seul pixel) : doit survivre au nettoyage
        # morphologique (`clean_alpha_mask`) applique par `remove_background`
        # -- un seul pixel isole serait, a raison, retire comme du bruit.
        mask[height // 2 - 4 : height // 2 + 4, width // 2 - 4 : width // 2 + 4] = 255
        return Image.fromarray(mask, "L")

    module.new_session = new_session
    module.remove = remove
    monkeypatch.setitem(sys.modules, "rembg", module)
    return module, created_sessions


def test_cache_dir_is_a_dedicated_rembg_home_subdirectory():
    directory = background_removal.cache_dir()
    assert directory.name == "rembg_home"
    assert directory.parent.name == "models"


def test_is_downloaded_false_when_model_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(background_removal, "cache_dir", lambda: tmp_path)
    assert background_removal.is_downloaded() is False


def test_is_downloaded_true_when_model_file_present_at_rembgs_nested_layout(tmp_path, monkeypatch):
    """rembg range le poids sous <U2NET_HOME>/models/<nom>/<nom>.onnx, pas
    directement sous U2NET_HOME -- cf. _model_file()."""
    monkeypatch.setattr(background_removal, "cache_dir", lambda: tmp_path)
    nested = tmp_path / "models" / background_removal.MODEL_NAME
    nested.mkdir(parents=True)
    (nested / background_removal.MODEL_FILENAME).write_bytes(b"fake")
    assert background_removal.is_downloaded() is True


def test_download_creates_a_session_for_the_expected_model(tmp_path, monkeypatch, fake_rembg):
    _, created_sessions = fake_rembg
    monkeypatch.setattr(background_removal, "cache_dir", lambda: tmp_path)

    background_removal.download()

    assert created_sessions == [background_removal.MODEL_NAME]


def test_remove_background_returns_float32_probability_mask(tmp_path, monkeypatch, fake_rembg):
    monkeypatch.setattr(background_removal, "cache_dir", lambda: tmp_path)
    image = Image.new("RGB", (40, 30), (10, 20, 30))

    mask = background_removal.remove_background(image)

    assert mask.shape == (30, 40)
    assert mask.dtype == np.float32
    assert mask[15, 20] > 0.9  # coeur du bloc : proche de 1.0 (leger flou de lissage du contour)
    assert mask[0, 0] == 0.0


def test_remove_background_sets_u2net_home_env_var(tmp_path, monkeypatch, fake_rembg):
    monkeypatch.setattr(background_removal, "cache_dir", lambda: tmp_path)
    monkeypatch.delenv("U2NET_HOME", raising=False)
    image = Image.new("RGB", (10, 10))

    background_removal.remove_background(image)

    assert os.environ["U2NET_HOME"] == str(tmp_path)


def test_clean_alpha_mask_removes_small_isolated_speck_near_a_real_subject():
    """Retour terrain : "artefacts qui genent" autour du detourage --
    reproduit une petite esquille de segmentation (quelques pixels isoles)
    a cote d'un vrai sujet (bloc plein) et verifie qu'elle disparait sans
    faire disparaitre le sujet lui-meme."""
    mask = np.zeros((100, 100), dtype=np.float32)
    mask[20:80, 20:80] = 1.0  # sujet : bloc 60x60
    mask[5:7, 5:7] = 1.0  # esquille isolee : bloc 2x2, loin du sujet

    cleaned = background_removal.clean_alpha_mask(mask)

    assert cleaned[50, 50] > 0.5  # coeur du sujet intact
    assert cleaned[6, 6] < 0.5  # esquille retiree


def test_clean_alpha_mask_smooths_a_jagged_staircase_edge():
    """Un contour en dents de scie pixel-a-pixel (staircase) doit ressortir
    plus lisse (valeurs intermediaires en bordure) apres nettoyage, sans
    que le sujet disparaisse ni que son aire globale change radicalement."""
    mask = np.zeros((60, 60), dtype=np.float32)
    for row in range(10, 50):
        # bord droit en marches d'escalier (largeur variant de 2px a chaque ligne)
        width = 20 + (row % 2) * 3
        mask[row, 10 : 10 + width] = 1.0

    cleaned = background_removal.clean_alpha_mask(mask)

    assert cleaned[30, 15] > 0.5  # coeur du sujet toujours plein
    # Le lissage introduit des valeurs intermediaires (ni 0 ni 1) le long
    # du contour -- signe que le bord n'est plus un pixel dur.
    edge_region = cleaned[10:50, 28:34]
    assert ((edge_region > 0.05) & (edge_region < 0.95)).any()


def test_clean_alpha_mask_leaves_empty_mask_unchanged():
    mask = np.zeros((10, 10), dtype=np.float32)
    cleaned = background_removal.clean_alpha_mask(mask)
    assert not cleaned.any()


def test_clean_alpha_mask_removes_a_thin_bridge_between_two_close_subjects():
    """Retour terrain reel : "il y a un morceau qui depasse" entre les deux
    visages d'un couple proche l'un de l'autre -- un pont de matting etroit
    (mais plus large qu'un simple pixel isole, ex. 4-5px) reliant a tort les
    deux silhouettes a travers le fond etroit qui les separe doit disparaitre,
    sans que les deux sujets eux-memes soient rognes."""
    mask = np.zeros((100, 200), dtype=np.float32)
    mask[20:80, 10:80] = 1.0  # premier visage
    mask[20:80, 120:190] = 1.0  # second visage
    mask[48:53, 80:120] = 1.0  # pont large de 5px entre les deux (fond etroit inclus a tort)

    cleaned = background_removal.clean_alpha_mask(mask)

    assert cleaned[50, 45] > 0.5  # premier visage intact
    assert cleaned[50, 155] > 0.5  # second visage intact
    assert cleaned[50, 100] < 0.5  # pont disparu : les deux sujets restent bien separes


def test_clean_alpha_mask_falls_back_to_original_if_cleanup_erases_everything():
    """Un sujet trop fin/petit pour survivre a l'ouverture morphologique ne
    doit pas se retrouver avec un masque totalement vide (pire que le bruit
    d'origine) -- retombe sur le masque non nettoye."""
    mask = np.zeros((20, 20), dtype=np.float32)
    mask[10, 10] = 1.0  # un seul pixel : ne survit a aucune ouverture

    cleaned = background_removal.clean_alpha_mask(mask)

    assert cleaned[10, 10] == 1.0
