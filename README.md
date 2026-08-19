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

## État actuel

**Phase 1A — Moteur de lithophanie headless.** Chaîne fonctionnelle complète
`IMAGE → PRÉTRAITEMENT → HEIGHTMAP → MESH MANIFOLD → STL`, testée et validée
(watertight, winding cohérent, volume positif, compatible `manifold3d`),
utilisable en CLI sans aucune interface graphique. Le viewer 3D (PyVista) et
l'interface PySide6 n'ont volontairement pas encore été intégrés — c'est
l'objet de la Phase 1B.
