from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from lithoshape3d.core.licensing import (
    InvalidLicenseError,
    is_valid_license_key,
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
