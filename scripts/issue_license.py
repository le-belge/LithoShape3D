"""Outil vendeur : genere une cle de licence signee pour un client.

Usage courant, apres une configuration unique (voir plus bas) :

    python scripts/issue_license.py client@example.com

Affiche la cle de licence a copier/coller dans un email de confirmation
d'achat -- l'app la verifie hors-ligne via `core/licensing.py`.

Configuration unique de la cle privee (jamais lue depuis le depot git) --
deux options, la premiere suffit pour un usage local normal :

  1. Fichier local (recommande, une seule fois) :
        mkdir -p ~/.lithoshape3d
        echo "<cle_privee_hex>" > ~/.lithoshape3d/seller_private_key.hex
        chmod 600 ~/.lithoshape3d/seller_private_key.hex

  2. Variable d'environnement (prioritaire sur le fichier si les deux
     existent -- utile en CI, jamais dans l'historique shell si possible) :
        LITHOSHAPE3D_PRIVATE_KEY_HEX=<cle_privee_hex> python scripts/issue_license.py ...
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import uuid
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SELLER_KEY_PATH = Path.home() / ".lithoshape3d" / "seller_private_key.hex"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def issue_license(email: str, private_key_hex: str) -> str:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    payload = {"id": str(uuid.uuid4()), "email": email}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature_bytes = private_key.sign(payload_bytes)
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature_bytes)}"


def _load_private_key_hex() -> str | None:
    env_value = os.environ.get("LITHOSHAPE3D_PRIVATE_KEY_HEX")
    if env_value:
        return env_value.strip()
    if SELLER_KEY_PATH.exists():
        return SELLER_KEY_PATH.read_text().strip()
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("email", help="Email de l'acheteur (informatif, inclus dans la cle)")
    args = parser.parse_args()

    private_key_hex = _load_private_key_hex()
    if not private_key_hex:
        print(
            f"Erreur : aucune cle privee trouvee (ni $LITHOSHAPE3D_PRIVATE_KEY_HEX, "
            f"ni {SELLER_KEY_PATH}).\n\nConfiguration unique :\n"
            f"    mkdir -p {SELLER_KEY_PATH.parent}\n"
            f'    echo "<cle_privee_hex>" > {SELLER_KEY_PATH}\n'
            f"    chmod 600 {SELLER_KEY_PATH}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(issue_license(args.email, private_key_hex))


if __name__ == "__main__":
    main()
