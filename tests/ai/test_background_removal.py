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
        mask[height // 2, width // 2] = 255
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
    assert mask[15, 20] == 1.0
    assert mask[0, 0] == 0.0


def test_remove_background_sets_u2net_home_env_var(tmp_path, monkeypatch, fake_rembg):
    monkeypatch.setattr(background_removal, "cache_dir", lambda: tmp_path)
    monkeypatch.delenv("U2NET_HOME", raising=False)
    image = Image.new("RGB", (10, 10))

    background_removal.remove_background(image)

    assert os.environ["U2NET_HOME"] == str(tmp_path)
