# Backlight Insert — Validation physique V2

Mission hotfix v0.4.2 (garantie de peau frontale du Backlight Insert),
section 12. Reproduit **exactement le même mécanisme** que la démo
`examples/backlight_rose_demo/` (photo réelle + segmentation SAM2 réelle +
Backlight Insert), mais recadrée très serrée sur la rose seule pour rester
**petite, rapide et économique** à imprimer.

## Pourquoi cette pièce

Le premier test physique (démo complète femme+rose, 100×133mm) a montré des
ouvertures/perforations à l'emplacement de la rose. Le diagnostic numérique
(voir le rapport de mission) a mesuré que le fichier STL livré était en
réalité **géométriquement parfait** (watertight, manifold, peau blanche
exactement 0.40mm partout où une cavité existait) — mais a révélé un vrai
bug distinct, minoritaire en étendue : l'insert coloré (pavé uniforme de
0.60mm) n'était jamais vérifié contre la profondeur réelle de cavité
disponible, et pouvait localement **chevaucher le corps blanc solide** dans
les zones les plus fines de la lithophanie (points clairs de la photo). Ce
chevauchement a été corrigé (`core/geometry/backlight.py`) : ces points ne
reçoivent plus de cavité du tout (façade pleine épaisseur préservée, signalé
dans `warnings`), plutôt que de produire un défaut silencieux.

Cette pièce V2 sert à valider **physiquement** ce correctif, sur un
échantillon qui reproduit fidèlement le contour organique complexe de la
rose (même photo source, même point de clic, même pipeline SAM2 réel), sans
réimprimer toute la lithophanie complète.

## Paramètres géométriques

| Paramètre | Valeur |
|---|---|
| Dimensions panneau | 55.0 × 52.8 mm |
| Résolution de génération | 0.2 mm/px |
| Épaisseur lithophanie (min/max) | 0.8 / 3.0 mm (défauts, non modifiés) |
| Épaisseur peau blanche (`white_skin_thickness_mm`) | **0.40 mm** (valeur d'origine, non modifiée par ce hotfix) |
| Épaisseur insert (`insert_thickness_mm`) | 0.60 mm (valeur d'origine, non modifiée) |
| Jeu XY (`xy_clearance_mm`) | 0.20 mm (preset Standard) |
| Pied d'impression | Plat, 5.0mm de haut |
| Source photo | `source_crop.png` — recadrage serré de `examples/reference_woman_rose.png` autour de la rose (même image que la démo complète) |
| Segmentation | SAM2 CoreML réel, même point de clic relatif que la démo complète |

Diagnostic numérique généré avec cette pièce (après correctif) :
- 15 495 / 15 516 points de la zone Backlight ont une cavité creusée, peau
  effective **exactement 0.40mm** partout (aucun point sous la valeur
  demandée).
- 21 points (zones les plus claires/fines de la rose) n'ont **volontairement
  aucune cavité** — trop fins pour loger à la fois la peau et l'insert
  (jusqu'à 0.089mm d'épaisseur locale manquante) — signalé explicitement
  dans les avertissements de génération, jamais silencieux.
- Corps blanc et insert : watertight, manifold, un seul composant chacun.

## Fichiers

- `backlight_v2_white.stl` — corps blanc principal (façade + cavité)
- `backlight_v2_insert.stl` — insert rose indépendant
- `backlight_v2_support.stl` — pied d'impression plat
- `backlight_v2.3mf` — les 3 corps assemblés dans leur position réelle
- `source_crop.png` — photo source utilisée (recadrage)
- `screenshot_front.png` / `screenshot_back.png` — vérification visuelle numérique

## Comment imprimer/tester

1. Importer `backlight_v2.3mf` dans votre slicer (Bambu Studio/OrcaSlicer/PrusaSlicer).
2. Assigner un filament blanc au corps "Blanc" (et au "Support"), un
   filament rose/rouge translucide au corps "Rose".
3. Imprimer (petite pièce, impression rapide).
4. Dans une pièce sombre, rétro-éclairer avec votre LED habituelle.

## Critères PASS / FAIL (mission section 13)

**Éteint :**
- [ ] Façade visuellement continue, aucun trou
- [ ] Insert non visible directement
- [ ] Relief avant propre (le relief de la rose doit être visible en surface, comme du papier gaufré — c'est normal et voulu, ce n'est pas un défaut)

**Allumé :**
- [ ] Couleur rouge/rose visible à travers la peau blanche à l'emplacement de la rose
- [ ] Aucune lumière directe/ponctuelle par un trou
- [ ] Contours de la rose acceptables (pas de fuite de lumière en ligne fine sur le pourtour)

**Mécanique :**
- [ ] Insert montable dans sa cavité sans forcer
- [ ] Alignement correct (insert bien positionné sous la silhouette de la rose)
- [ ] Pas de déformation excessive au retrait du plateau

**Important :** cette pièce ne teste PAS la calibration filament, la
fidélité colorimétrique, ni la puissance LED optimale — uniquement la
garantie géométrique de peau frontale (objet de ce hotfix). Un léger défaut
de contour résiduel, s'il apparaît, resterait cohérent avec l'hypothèse
principale non résolue par ce hotfix : la difficulty physique d'imprimer un
pont/plafond non supporté de seulement ~0.40mm sur un contour organique
(voir le rapport de mission complet) — auquel cas Backlight Insert restera
`EXPERIMENTAL` en attendant une itération ultérieure sur l'épaisseur de peau
elle-même ou les réglages de pont du slicer.

Généré par LithoShape3D — hotfix v0.4.2.
