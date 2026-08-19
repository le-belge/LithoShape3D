# LithoShape3D

Logiciel pour transformer des images en objets 3D imprimables, avec pour cœur
historique la génération de lithophanies :

Image → réglages visuels → aperçu → modèle imprimable → export

## LithoFusion 3D

Évolution visée du projet : combiner lithophanie, relief 3D, formes
personnalisées, couleurs et multi-matériaux (impression multi-couleurs / AMS)
au sein d'une même scène composée de plusieurs zones.

## Architecture

- `core/` — moteur (image, geometry, scene, export, validation). Ne dépend
  jamais de Qt, PyVista, PyVistaQt ou VTK. Utilisable en headless, en CLI ou
  depuis les tests.
- `ai/` — segmentation/assistance IA locale (vide pour l'instant).
- `viewer/` — adaptation d'une `Scene` vers PyVista (aperçu 3D).
- `ui/` — interface graphique PySide6, ne contient pas de logique métier.
- `cli.py` — point d'entrée headless.
- `tests/` — tests du `core`.

## Installation développement

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[viewer,ui,dev]"
```

Installation minimale (core seul, sans interface ni viewer) :

```bash
pip install -e .
```

## Lancer les tests

```bash
pytest
```

## Utilisation (CLI headless, sans interface graphique)

```bash
lithoshape3d generate photo.png sortie.stl --width 100 --min-thickness 0.8 --max-thickness 3.0
```

`--height` est optionnel : déduite du ratio de l'image si omise. Le mesh est
validé (fermé, manifold, sans triangle dégénéré) avant d'être écrit sur
disque ; la commande échoue explicitement si la validation échoue.

## Benchmark

```bash
python scripts/benchmark_mesh.py
```

## Viewer 3D (démo, pas encore l'interface finale)

```bash
pip install -e ".[viewer,ui]"
python scripts/demo_viewer.py
```

Permet de choisir une image, régler quelques paramètres simples et afficher
immédiatement le mesh produit par le moteur (rotation/zoom/pan, vues
face/arrière/gauche/droite/dessus/isométrique, modes surface/fil de
fer/surface+arêtes). Ce n'est qu'une démonstration : l'UI finale (thème,
zones multiples, etc.) reste à construire dans les phases suivantes.

> Remarque macOS : ne pas forcer `QT_QPA_PLATFORM=offscreen` avec cette
> application — VTK/PyVistaQt plante (segfault) avec ce backend sur macOS.
> Lancer normalement (fenêtre Qt réelle).

## État actuel

**Phase 1B — Viewer 3D PyVista.** En plus de la chaîne headless de la Phase
1A, un viewer 3D (`src/lithoshape3d/viewer/`) affiche directement les meshes
produits par le core, sans passer par un fichier STL temporaire. `core` reste
strictement indépendant de Qt/PyVista/VTK (vérifié par test automatisé).
L'interface graphique finale (thème, panneaux, zones multiples) reste à
construire dans les phases suivantes.
