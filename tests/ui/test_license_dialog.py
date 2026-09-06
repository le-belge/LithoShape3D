from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PySide6.QtCore import QSettings

from lithoshape3d.ui import license_dialog as license_dialog_module
from lithoshape3d.ui.license_dialog import LicenseDialog, is_licensed, stored_license_key

_TEST_PRIVATE_KEY = Ed25519PrivateKey.generate()


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _issue(email: str = "mike@example.com") -> str:
    payload_bytes = json.dumps({"id": "order-1", "email": email}).encode("utf-8")
    signature_bytes = _TEST_PRIVATE_KEY.sign(payload_bytes)
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature_bytes)}"


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Jamais de veritable ecriture QSettings pendant les tests -- un
    fichier ini prive au tmp_path de chaque test, jamais les prefs reelles
    de l'utilisateur qui fait tourner la suite."""
    ini_path = str(tmp_path / "settings.ini")

    def _make_settings():
        return QSettings(ini_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(license_dialog_module, "QSettings", _make_settings)


@pytest.fixture(autouse=True)
def real_public_key(monkeypatch):
    """Les cles emises par ce test doivent verifier contre la cle publique
    correspondant a _TEST_PRIVATE_KEY, pas contre PUBLIC_KEY_HEX (celle du
    vendeur reel) -- sinon toute cle forgee ici serait rejetee a raison."""
    from cryptography.hazmat.primitives import serialization

    public_hex = _TEST_PRIVATE_KEY.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    ).hex()
    monkeypatch.setattr("lithoshape3d.core.licensing.PUBLIC_KEY_HEX", public_hex)


def test_no_stored_key_means_not_licensed():
    assert stored_license_key() is None
    assert not is_licensed()


def test_saving_a_valid_key_through_the_dialog_persists_and_licenses(qapp):
    dialog = LicenseDialog()
    dialog.key_edit.setText(_issue())
    dialog._on_save()

    assert stored_license_key() == _issue()
    assert is_licensed()


def test_saving_an_invalid_key_shows_status_and_does_not_persist(qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    dialog = LicenseDialog()
    dialog.key_edit.setText("garbage-not-a-key")
    dialog._on_save()

    assert stored_license_key() is None
    assert not is_licensed()


def test_saving_an_empty_key_clears_the_license(qapp):
    dialog = LicenseDialog()
    dialog.key_edit.setText(_issue())
    dialog._on_save()
    assert is_licensed()

    dialog2 = LicenseDialog()
    dialog2.key_edit.setText("")
    dialog2._on_save()

    assert not is_licensed()
