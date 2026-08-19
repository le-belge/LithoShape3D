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
- `viewer/` — conversion mesh -> PyVista et gestion de scène (caméra,
  éclairage, vues), indépendante de Qt.
- `ui/` — application PySide6 (`MainWindow`, worker de génération, état,
  logging). Assemble `core` et `viewer`, ne réimplémente jamais leur logique.
- `cli.py` — point d'entrée unique : `lithoshape3d` (sans argument) lance
  l'application graphique, `lithoshape3d generate ...` reste headless.
- `tests/` — tests du `core`, du `viewer` et de l'`ui`.

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

## Viewer 3D (démo Phase 1B, conservée pour référence)

```bash
pip install -e ".[app]"
python scripts/demo_viewer.py
```

Petite démo minimale ayant servi à valider le viewer avant l'application
complète ci-dessous.

> Remarque macOS : ne pas forcer `QT_QPA_PLATFORM=offscreen` avec PyVistaQt
> — VTK plante (segfault) avec ce backend sur macOS. Lancer normalement
> (fenêtre Qt réelle). Un `pv.Plotter(off_screen=True)` sans Qt fonctionne
> très bien en revanche (utilisé par tous les tests automatisés).

## LithoShape3D 0.1 — application complète

```bash
pip install -e ".[app]"
lithoshape3d
```

(`lithoshape3d` sans argument lance l'application ; `lithoshape3d generate ...`
reste disponible pour l'usage headless en CLI.)

Workflow : Ouvrir image → régler les paramètres (largeur, épaisseur
min/max, résolution, inversion, contraste, luminosité, presets Standard/
Fine/Draft) → Générer → manipuler le résultat en 3D (rotation/zoom/pan, vues
Face/Iso/Reset caméra, modes surface/fil de fer/surface+arêtes) → Exporter
STL. La génération se fait dans un thread séparé (`QThreadPool`), l'interface
reste réactive pendant ce temps. Si un paramètre est modifié après une
génération, le mesh affiché est marqué périmé et l'export est désactivé tant
qu'une nouvelle génération n'a pas été lancée. Les logs sont écrits dans
`~/Library/Logs/LithoShape3D/lithoshape3d.log`.

## État actuel

**Phase 1C — Première application desktop utilisable (LithoShape3D 0.1).**
Assemble les briques des phases précédentes (moteur headless + viewer
PyVista) dans une vraie `MainWindow` PySide6 : import image, réglage des
paramètres, génération asynchrone, aperçu 3D interactif, export STL. `core`
reste strictement indépendant de Qt/PyVista/VTK (vérifié par test
automatisé). Pas encore de thème définitif, de zones multiples, d'IA, de
formes non rectangulaires ni d'intégration Bambu Studio — réservé aux
phases suivantes.
