from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from lithoshape3d.core.licensing import (
    InvalidLicenseError,
    is_valid_license_key,
    issue_license_key,
    seller_private_key_hex,
    verify_license_key,
)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@pytest.fixture()
def keypair():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    from cryptography.hazmat.primitives import serialization

    public_hex = public_key.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    ).hex()
    return private_key, public_hex


def _issue(private_key: Ed25519PrivateKey, license_id: str = "abc", email: str = "mike@example.com") -> str:
    payload_bytes = json.dumps({"id": license_id, "email": email}).encode("utf-8")
    signature_bytes = private_key.sign(payload_bytes)
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature_bytes)}"


def test_valid_key_verifies_and_returns_info(keypair):
    private_key, public_hex = keypair
    key = _issue(private_key, license_id="order-42", email="mike@example.com")

    info = verify_license_key(key, public_key_hex=public_hex)

    assert info.license_id == "order-42"
    assert info.email == "mike@example.com"
    assert is_valid_license_key(key, public_key_hex=public_hex)


def test_key_signed_by_a_different_private_key_is_rejected(keypair):
    _, public_hex = keypair
    other_private_key = Ed25519PrivateKey.generate()
    forged_key = _issue(other_private_key)

    with pytest.raises(InvalidLicenseError):
        verify_license_key(forged_key, public_key_hex=public_hex)
    assert not is_valid_license_key(forged_key, public_key_hex=public_hex)


def test_tampered_payload_is_rejected(keypair):
    private_key, public_hex = keypair
    key = _issue(private_key, email="mike@example.com")
    payload_part, _, signature_part = key.partition(".")

    tampered_payload = _b64url_encode(json.dumps({"id": "abc", "email": "attacker@evil.com"}).encode())
    tampered_key = f"{tampered_payload}.{signature_part}"

    with pytest.raises(InvalidLicenseError):
        verify_license_key(tampered_key, public_key_hex=public_hex)


@pytest.mark.parametrize(
    "bad_key",
    ["", "not-a-license-key", "onlyonepart", "..", "abc.def"],
)
def test_malformed_keys_are_rejected_not_crashed(bad_key, keypair):
    _, public_hex = keypair
    with pytest.raises(InvalidLicenseError):
        verify_license_key(bad_key, public_key_hex=public_hex)
    assert not is_valid_license_key(bad_key, public_key_hex=public_hex)


def test_missing_fields_in_payload_are_rejected(keypair):
    private_key, public_hex = keypair
    payload_bytes = json.dumps({"id": "abc"}).encode("utf-8")  # pas de "email"
    signature_bytes = private_key.sign(payload_bytes)
    key = f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature_bytes)}"

    with pytest.raises(InvalidLicenseError):
        verify_license_key(key, public_key_hex=public_hex)


def test_issue_license_key_round_trips_through_verify(keypair):
    private_key, public_hex = keypair
    from cryptography.hazmat.primitives import serialization

    private_hex = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()

    key = issue_license_key("client@example.com", private_hex)
    info = verify_license_key(key, public_key_hex=public_hex)

    assert info.email == "client@example.com"


def test_seller_private_key_hex_reads_the_local_file(tmp_path, monkeypatch):
    key_path = tmp_path / "seller_private_key.hex"
    key_path.write_text("  abcdef  \n")
    monkeypatch.setattr("lithoshape3d.core.licensing.SELLER_KEY_PATH", key_path)

    assert seller_private_key_hex() == "abcdef"


def test_seller_private_key_hex_is_none_when_file_absent(tmp_path, monkeypatch):
    monkeypatch.setattr("lithoshape3d.core.licensing.SELLER_KEY_PATH", tmp_path / "does_not_exist.hex")

    assert seller_private_key_hex() is None
