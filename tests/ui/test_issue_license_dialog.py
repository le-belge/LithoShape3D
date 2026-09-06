from __future__ import annotations

import pyvista as pv
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from lithoshape3d.core.licensing import verify_license_key
from lithoshape3d.ui.issue_license_dialog import IssueLicenseDialog
from lithoshape3d.ui.main_window import MainWindow

_PRIVATE_KEY_HEX = "d2149f2e171c6c50cb0172fc186d5df9d202de6afa9eff6bcebc228a283ed4ef"


@pytest.fixture()
def with_seller_key(monkeypatch):
    """Simule une machine vendeur (cle privee locale presente) sans jamais
    toucher au vrai ~/.lithoshape3d de la machine qui fait tourner la suite."""
    monkeypatch.setattr(
        "lithoshape3d.core.licensing.seller_private_key_hex", lambda: _PRIVATE_KEY_HEX
    )


@pytest.fixture()
def without_seller_key(monkeypatch):
    monkeypatch.setattr("lithoshape3d.core.licensing.seller_private_key_hex", lambda: None)


def _menu_titles(window):
    return [action.text() for action in window.menuBar().actions()]


def test_seller_menu_present_when_seller_key_exists(qapp, with_seller_key):
    window = MainWindow(plotter=pv.Plotter(off_screen=True))
    try:
        assert "Vendeur" in _menu_titles(window)
    finally:
        window.plotter.close()


def test_seller_menu_absent_without_seller_key(qapp, without_seller_key):
    window = MainWindow(plotter=pv.Plotter(off_screen=True))
    try:
        assert "Vendeur" not in _menu_titles(window)
    finally:
        window.plotter.close()


def test_issue_license_dialog_generates_a_key_verifiable_for_the_given_email(qapp, with_seller_key, monkeypatch):
    public_hex = (
        Ed25519PrivateKey.from_private_bytes(bytes.fromhex(_PRIVATE_KEY_HEX))
        .public_key()
        .public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        .hex()
    )
    monkeypatch.setattr("lithoshape3d.core.licensing.PUBLIC_KEY_HEX", public_hex)
    dialog = IssueLicenseDialog()
    dialog.email_edit.setText("client@example.com")

    dialog._on_generate()

    assert dialog.result_edit.text()
    info = verify_license_key(dialog.result_edit.text())
    assert info.email == "client@example.com"
    assert dialog.copy_button.isEnabled()


def test_issue_license_dialog_requires_an_email(qapp, with_seller_key, monkeypatch):
    warned = []
    monkeypatch.setattr(
        "lithoshape3d.ui.issue_license_dialog.QMessageBox.warning",
        lambda *a, **k: warned.append(True),
    )
    dialog = IssueLicenseDialog()

    dialog._on_generate()

    assert warned == [True]
    assert not dialog.result_edit.text()
