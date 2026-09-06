"""Outil vendeur : genere une cle de licence signee pour un client.

La cle privee n'est jamais lue depuis un fichier du depot -- passez-la par
variable d'environnement (jamais dans l'historique shell si possible) :

    LITHOSHAPE3D_PRIVATE_KEY_HEX=<cle_privee_hex> \\
        python scripts/issue_license.py client@example.com

Affiche la cle de licence a copier/coller dans un email de confirmation
d'achat -- l'app la verifie hors-ligne via `core/licensing.py`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def issue_license(email: str, private_key_hex: str) -> str:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    payload = {"id": str(uuid.uuid4()), "email": email}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature_bytes = private_key.sign(payload_bytes)
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature_bytes)}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", help="Email de l'acheteur (informatif, inclus dans la cle)")
    args = parser.parse_args()

    private_key_hex = os.environ.get("LITHOSHAPE3D_PRIVATE_KEY_HEX")
    if not private_key_hex:
        print(
            "Erreur : variable d'environnement LITHOSHAPE3D_PRIVATE_KEY_HEX absente.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(issue_license(args.email, private_key_hex))


if __name__ == "__main__":
    main()
