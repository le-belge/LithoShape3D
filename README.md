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

## État actuel

**Phase 0 — Squelette du projet.** Le modèle de données (`Project` / `Scene`
/ `Zone`) et la sérialisation de projet sont en place. Aucun moteur de
génération (heightmap, mesh, export STL réel) n'est encore implémenté — c'est
l'objet de la Phase 1 (`IMAGE → HEIGHTMAP → MESH MANIFOLD → APERÇU 3D → STL`).
