"""Verification de licence hors-ligne (Ed25519), sans serveur.

Modele volontairement simple, choisi par l'utilisateur (Mike) apres avoir
ete prevenu qu'aucune protection locale n'est inviolable : une cle privee
Ed25519 (jamais expediee avec l'app, gardee par le vendeur) signe un petit
paquet d'infos ; seule la cle PUBLIQUE (ci-dessous) est embarquee dans
l'application pour verifier cette signature. Quiconque possede une cle
signee valide est considere licencie -- il n'y a pas de serveur de
revocation, c'est un compromis assume de cette approche "simple et hors
ligne" plutot que "calcul deporte" (rejete : demande une connexion
permanente).

Format d'une cle de licence (chaine que l'utilisateur colle dans l'app) :
    "<payload_b64url>.<signature_b64url>"
`payload_b64url` decode en JSON UTF-8 : {"id": str, "email": str}.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

# Cle PUBLIQUE seulement -- generee par scripts/generate_license_keypair.py.
# La cle privee correspondante ne doit JAMAIS apparaitre dans ce depot.
PUBLIC_KEY_HEX = "0bfb928984d7883fb234a5f098c4c9a35403880ecf67a172d168f8b6736cf3da"

# Emplacement local (jamais dans ce depot) ou le vendeur garde sa cle privee
# -- voir scripts/issue_license.py. Sa seule PRESENCE sur une machine (la
# sienne, jamais celle d'un client qui recoit l'app packagee sans ce fichier)
# sert aussi de garde pour reveler le bouton "Generer une licence..." dans
# l'app -- voir ui/main_window.py::_maybe_add_seller_menu.
SELLER_KEY_PATH = Path.home() / ".lithoshape3d" / "seller_private_key.hex"


class InvalidLicenseError(ValueError):
    """Cle de licence absente, malformee, ou signature invalide."""


@dataclass(frozen=True)
class LicenseInfo:
    license_id: str
    email: str


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def verify_license_key(key_str: str, public_key_hex: str | None = None) -> LicenseInfo:
    """Verifie une cle de licence et retourne ses infos si elle est valide.

    Leve `InvalidLicenseError` pour toute cle absente, malformee, ou dont la
    signature ne correspond pas a `public_key_hex` -- jamais d'autre
    exception, pour que l'appelant UI n'ait qu'un seul cas d'erreur a gerer.

    `public_key_hex` par defaut lit le module `PUBLIC_KEY_HEX` au moment de
    l'appel (pas comme valeur par defaut figee a la definition) -- sinon un
    test qui monkeypatch `licensing.PUBLIC_KEY_HEX` n'aurait aucun effet.
    """
    if public_key_hex is None:
        public_key_hex = PUBLIC_KEY_HEX
    key_str = (key_str or "").strip()
    if not key_str or "." not in key_str:
        raise InvalidLicenseError("Cle de licence vide ou mal formee.")

    payload_part, _, signature_part = key_str.partition(".")
    try:
        payload_bytes = _b64url_decode(payload_part)
        signature_bytes = _b64url_decode(signature_part)
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        public_key.verify(signature_bytes, payload_bytes)
        payload = json.loads(payload_bytes.decode("utf-8"))
        license_id = payload["id"]
        email = payload["email"]
    except (InvalidSignature, ValueError, KeyError, UnicodeDecodeError) as exc:
        raise InvalidLicenseError("Cle de licence invalide.") from exc

    if not isinstance(license_id, str) or not isinstance(email, str):
        raise InvalidLicenseError("Cle de licence invalide.")
    return LicenseInfo(license_id=license_id, email=email)


def is_valid_license_key(key_str: str, public_key_hex: str | None = None) -> bool:
    try:
        verify_license_key(key_str, public_key_hex)
        return True
    except InvalidLicenseError:
        return False


def issue_license_key(email: str, private_key_hex: str) -> str:
    """Emet une cle de licence signee pour `email`. Reserve au vendeur --
    ne jamais appeler avec une cle qui n'est pas la cle privee du vendeur.
    Partagee par scripts/issue_license.py et le bouton vendeur de l'app."""
    private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    payload = {"id": str(uuid.uuid4()), "email": email}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature_bytes = private_key.sign(payload_bytes)
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature_bytes)}"


def seller_private_key_hex() -> str | None:
    """Cle privee du vendeur si ce fichier local existe, sinon None -- ne
    lit jamais rien depuis ce depot ni depuis l'app packagee elle-meme."""
    if SELLER_KEY_PATH.exists():
        return SELLER_KEY_PATH.read_text().strip()
    return None
