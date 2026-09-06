#!/usr/bin/env bash
# Regenere src/lithoshape3d/ui/translations/lithoshape3d_en.ts (fusion,
# sans perdre les traductions existantes) puis rappelle les etapes
# manuelles restantes. Voir ui/translations/README.md.
set -euo pipefail
cd "$(dirname "$0")/.."

TS_FILE="src/lithoshape3d/ui/translations/lithoshape3d_en.ts"
QM_FILE="src/lithoshape3d/ui/translations/lithoshape3d_en.qm"

pyside6-lupdate \
  src/lithoshape3d/ui/main_window.py \
  src/lithoshape3d/ui/about_dialog.py \
  src/lithoshape3d/ui/license_dialog.py \
  -ts "$TS_FILE"

if grep -q 'type="unfinished"' "$TS_FILE"; then
  echo
  echo "Des textes restent non traduits dans $TS_FILE :"
  grep -B1 'type="unfinished"' "$TS_FILE" | grep '<source>' || true
  echo
  echo "Traduisez-les (balise <translation>...</translation>), puis relancez ce script."
  exit 1
fi

pyside6-lrelease "$TS_FILE" -qm "$QM_FILE"
echo "OK : $QM_FILE regenere."
