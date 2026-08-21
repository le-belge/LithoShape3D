#!/usr/bin/env bash
# Construit LithoShape3D.app (macOS, Apple Silicon) via PyInstaller.
# Prerequis : le venv du projet actif, avec l'extra app-full installe
# (pip install -e ".[app-full]"), plus PyInstaller (pip install pyinstaller).
#
# Pas de signature/notarisation ici (necessiterait un compte developpeur
# Apple) : l'app est utilisable localement (clic droit -> Ouvrir la premiere
# fois, Gatekeeper la bloquera sinon puisqu'elle n'est pas notariee).
set -euo pipefail
cd "$(dirname "$0")"
pyinstaller lithoshape3d.spec --noconfirm
echo "Build termine : $(pwd)/dist/LithoShape3D.app"
