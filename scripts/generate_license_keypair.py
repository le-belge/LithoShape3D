"""Outil vendeur (usage unique) : genere la paire de cles Ed25519 pour la
licence de LithoShape3D/LithoGift.

NE JAMAIS committer la cle privee. Ce script l'affiche une seule fois --
copiez-la immediatement dans un gestionnaire de mots de passe (elle sert a
signer chaque licence vendue via scripts/issue_license.py). La cle PUBLIQUE
doit ensuite etre collee dans `PUBLIC_KEY_HEX` de
`src/lithoshape3d/core/licensing.py` puis committee normalement (elle est
sans danger a diffuser : elle ne permet que de VERIFIER une signature,
jamais d'en creer une).

Usage : python scripts/generate_license_keypair.py
"""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_hex = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()
    public_hex = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()

    print("=== Cle PRIVEE (a garder secrete, ne JAMAIS committer) ===")
    print(private_hex)
    print()
    print("=== Cle PUBLIQUE (a coller dans core/licensing.py::PUBLIC_KEY_HEX) ===")
    print(public_hex)


if __name__ == "__main__":
    main()
