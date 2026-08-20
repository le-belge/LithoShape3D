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

## Zones et masques (Phase 2A)

Une image peut désormais être découpée en plusieurs zones indépendantes
(panneau "Zones" sous l'aperçu source) : création/suppression/renommage
inline/visibilité/réordonnancement par glisser-déposer. Chaque zone possède
son propre masque (peint via "Éditer le masque..." — pinceau, gomme, taille,
remplir, effacer, inverser, undo/redo ⌘Z/⇧⌘Z) et ses propres paramètres
géométriques. La zone active est mise en surbrillance dans l'aperçu 2D
(overlay coloré, une teinte par zone, l'image source n'est jamais modifiée).

Ouvrir une image crée automatiquement une zone "Lithophanie" à masque plein
(comportement historique préservé). La génération/le viewer 3D ciblent la
zone active — y compris désormais un masque réellement irrégulier (voir
Phase 2B ci-dessous).

Menu Fichier : Nouveau projet / Ouvrir projet.../ Enregistrer / Enregistrer
sous... — un projet est un bundle-dossier `MonProjet.l3dproj/` (image copiée
dans `source/`, masques dans `masks/`, `project.json`), entièrement
déplaçable (aucun chemin absolu enregistré).

## Géométrie d'une zone masquée (Phase 2B)

`build_slab_mesh` épouse désormais la forme réelle du masque d'une zone,
plutôt que de se limiter à la plaque rectangulaire complète : contour
extérieur, trous internes (ex. anneau) et îlots multiples disjoints sont
tous gérés nativement (grille régulière + extraction vectorisée des arêtes
de frontière actif/inactif — voir `core/geometry/mesh_builder.py`). Un
masque plein (ou `mask=None`) reproduit exactement le comportement
historique (aucune régression). Un masque insuffisant (zone trop petite/
fine) est refusé proprement au lieu de produire un mesh corrompu. Les
coordonnées XY restent toujours celles de la Scene complète — pas de
recentrage/rescale automatique sur le contour du masque, condition
nécessaire à la fusion multi-zones de la Phase 2C.

```bash
python scripts/benchmark_masked_mesh.py
```

## Composition multi-zones — LithoFusion (Phase 2C)

Plusieurs zones peuvent maintenant être combinées en un seul objet
imprimable. Chaque zone a un **rôle** (panneau "Rôle de la zone") :

- `ReliefMode` (Lithophanie / Relief-amplitude / Solide) — comment la zone
  transforme son image en hauteur.
- `CompositionMode` (Base / Ajouter / Remplacer) — comment cette
  contribution s'intègre au résultat déjà composé. `Base` et `Remplacer`
  écrasent la hauteur dans leur masque, `Ajouter` s'y additionne.

Composition séquentielle selon l'ordre `Scene.zones` (le glisser-déposer du
panneau Zones a donc maintenant un effet géométrique réel), entièrement par
champ de hauteur NumPy — aucun booléen `manifold3d` entre zones, réservé à
la validation finale et aux futurs volumes non planaires. Le dos reste
toujours à `Z=0` : une contribution ne peut jamais "flotter", au pire elle
forme une composante connexe supplémentaire posée sur le même plateau.

Dans l'affichage, bascule "Zone active / Composition" détermine ce que
`Générer` produit ; l'export STL exporte toujours le résultat actuellement
affiché.

```bash
python scripts/benchmark_composition.py
```

## État actuel

**Phase 2C — Composition multi-zones (LithoFusion).** Base + zones `ADD`/
`REPLACE` se combinent en un unique mesh manifold (watertight, winding
cohérent, 0 bord ouvert, compatible `manifold3d`), exportable en un seul
STL. `core` reste strictement indépendant de Qt/PyVista/VTK (vérifié par
test automatisé). Toujours pas de `SUBTRACT`, de segmentation IA, de
formes non rectangulaires, de couleurs/AMS/3MF ni d'intégration Bambu
Studio.
