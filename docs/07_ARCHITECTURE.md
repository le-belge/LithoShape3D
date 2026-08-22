# Architecture — état réel du dépôt

Ce document décrit l'architecture **actuelle**, pas une architecture visée.
Toute divergence future avec le code doit être corrigée ici, pas dans le
code (sauf décision explicite contraire).

## Frontières de dépendances (règle fondamentale)

```
core/    ne dépend JAMAIS de Qt / PyVista / PyVistaQt / VTK
ai/      dépendances IA (coremltools, huggingface_hub) isolées dans
         sam2_coreml_backend.py uniquement — jamais importées par core/
viewer/  dépend de PyVista, jamais de Qt directement
ui/      dépend de Qt (PySide6) et assemble core/ + viewer/ + ai/,
         ne réimplémente jamais leur logique
```

Cette frontière est vérifiée **automatiquement**, pas seulement par
convention : `tests/test_architecture_boundaries.py` fait un import
headless de `core` en sous-processus et échoue si Qt/PyVista/VTK sont
chargés. C'est ce test qui a permis de garder `core/` réellement
utilisable en CLI/headless/tests sans jamais ouvrir de fenêtre, sur toutes
les phases du projet.

## Arborescence

```
src/lithoshape3d/
├── core/                   moteur pur, headless, testable sans Qt
│   ├── image/              chargement, prétraitement (contraste/luminosité/
│   │                       inversion), cadrage (transform.py)
│   ├── geometry/           heightmap → mesh. Modules clés :
│   │   ├── thickness.py    formule luminosité → épaisseur (UN seul endroit)
│   │   ├── relief.py       ReliefMode → contribution de hauteur d'une Zone
│   │   ├── mesh_builder.py grille+masque(+face arrière optionnelle) → mesh
│   │   │                   fermé (front/back/parois vectorisées)
│   │   ├── composition.py  plusieurs Zones → un champ de hauteur unique
│   │   ├── materials.py    partition du mesh composé par matériau
│   │   ├── backlight.py    corps blanc à cavité + insert (Backlight Insert)
│   │   ├── support.py      pied d'impression, union manifold3d réelle
│   │   └── shape.py        ShapeMask (Rectangle/Cercle/Ovale/Cœur/Étoile/
│   │                       Texte/Image), indépendant de Qt (texte via Pillow)
│   ├── scene/               modèle de données + persistance
│   │   ├── models.py        Project/Scene/Zone/GeometryParameters/Material/
│   │   │                     Transform/ReliefMode/CompositionMode/
│   │   │                     ColorStrategy/ShapeParams/ImageTransform/
│   │   │                     BacklightInsertParams/PrintSupport
│   │   ├── serialization.py dict JSON versionné + chaîne de migrations
│   │   │                     (v1→v6)
│   │   ├── mask_io.py       masque float32[0,1] ↔ PNG 8 bits
│   │   └── project_io.py    bundle-dossier `.l3dproj/` portable
│   ├── export/              STL, 3MF multi-objets (trimesh.Scene)
│   └── validation/          mesh_checks.py (watertight/manifold/volume),
│                             printability.py (composantes/dimensions/
│                             éléments fins — diagnostic, jamais bloquant)
├── ai/
│   └── segmentation/        SegmentationBackend (interface) +
│                             MockSegmentationBackend (tests, déterministe)
│                             + Sam2CoreMLBackend (macOS uniquement,
│                             sys.platform gate explicite)
├── viewer/
│   ├── adapter.py            trimesh → pyvista.PolyData (pur, testable)
│   └── scene_viewer.py       SceneViewer(plotter injecté) : vues, modes
│                             d'affichage (surface/fil de fer/matériaux/
│                             rétro-éclairé), jamais de fenêtre Qt directe
├── ui/                       PySide6 — seule couche qui connaît Qt
│   ├── main_window.py        assemble tout : panneaux, génération, export,
│                             projet (fichier le plus volumineux du dépôt)
│   ├── worker.py              QRunnable : GenerationWorker/CompositionWorker/
│   │                          BacklightCompositionWorker — jamais de widget
│   │                          touché depuis un thread, résultats via signaux
│   ├── mask_editor_dialog.py + mask_edit_controller.py (undo/redo local
│   │                          au masque, séparé de tout état applicatif)
│   ├── cadrage_dialog.py      vue seule, ne touche jamais mesh/manifold
│   ├── shape_svg_import.py    seul point du dépôt qui importe QtSvg
│   └── state.py                AppState (machine d'état explicite, pilote
│                               l'activation des boutons)
└── cli.py                     point d'entrée : sans argument → GUI (lazy
                                import Qt/PyVista), `generate` → headless
```

## Structures de données principales

```
Project
 ├─ format_version: int          (source de vérité de compatibilité — jamais
 │                                 déduit, toujours explicite dans le JSON)
 └─ Scene
     ├─ zones: list[Zone]
     ├─ source_image_path
     ├─ active_zone_id
     ├─ support: PrintSupport
     ├─ shape: ShapeParams        (Shape Composer, v0.4+)
     └─ image_transform: ImageTransform  (cadrage photo dans la Shape)

Zone
 ├─ geometry_params: GeometryParameters   (largeur/hauteur/épaisseurs/résolution)
 ├─ material: Material                    (nom/couleur/filament/slot)
 ├─ transform: Transform                  (réservé, peu utilisé aujourd'hui)
 ├─ relief_mode: ReliefMode                (LITHOPHANE/RELIEF/SOLID)
 ├─ composition_mode: CompositionMode      (BASE/ADD/REPLACE)
 ├─ color_strategy: ColorStrategy | None   (v0.4.1 — voir plus bas)
 └─ backlight_insert: BacklightInsertParams (pertinent seulement si
                                              color_strategy=BACKLIGHT_INSERT)
```

Trois axes **délibérément séparés** (principe non négociable du produit,
voir Product Bible) :

1. **Géométrie/relief** — `ReliefMode` + `GeometryParameters` : comment le
   pixel devient une hauteur.
2. **Composition** — `CompositionMode` : comment cette hauteur s'intègre au
   résultat déjà composé (écrase ou s'additionne).
3. **Couleur** — `Material` (quel filament) + `ColorStrategy` (est-ce que
   cette zone a le droit de modifier la géométrie partagée, ou seulement
   de revendiquer un matériau sur une géométrie déjà décidée par ailleurs).

`ColorStrategy` a été ajouté en 0.4.1 précisément parce que (2) et (3)
avaient fini par se confondre dans l'usage réel : une zone REPLACE/ADD
existait à la fois pour de la vraie géométrie (gravure) et pour de la
simple différenciation de couleur, et rien n'empêchait une zone "couleur"
d'affecter silencieusement la hauteur. Un axe orthogonal, avec un défaut
`None` qui préserve exactement le comportement historique pour tout
projet migré, a résolu ça sans toucher aux deux premiers axes.

## Pipeline réel (schéma texte)

```
Image source (disque)
   │
   ▼
core/image  ── prétraitement (contraste/luminosité/inversion) ──┐
                cadrage (ImageTransform, si Shape non-Rectangle) │
   │                                                             │
   ▼                                                             │
core/geometry/relief.py   pixel → contribution de hauteur (mm)  │
   │                       par Zone, selon ReliefMode            │
   ▼                                                             │
core/geometry/composition.py                                     │
   séquentiel sur Scene.zones (ordre = ordre d'affichage) :       │
   - BASE/REPLACE écrasent, ADD additionne                        │
   - zone à ColorStrategy ≠ None (hors BASE) : SKIP hauteur ◄─────┘
   - masque de zone ∩ ShapeMask (jamais de matière hors Shape)
   │
   ├──► core/geometry/mesh_builder.py
   │     grille + masque actif (+ face arrière non plane optionnelle,
   │     pour la cavité Backlight Insert) → UN SEUL mesh fermé
   │     (front/back/parois vectorisées numpy, winding validé empiriquement)
   │
   ├──► core/geometry/materials.py
   │     même règle de recouvrement, calcule un "propriétaire" par cellule
   │     → un mesh fermé indépendant PAR matériau, même repère XYZ
   │
   ├──► core/geometry/backlight.py
   │     si zone(s) BACKLIGHT_INSERT : corps blanc à cavité (réutilise
   │     mesh_builder avec back_z non plan) + insert(s) plat(s) séparé(s)
   │     (jeu XY via carte de distance sub-pixel, pas une érosion entière)
   │
   ├──► core/geometry/support.py
   │     pied optionnel, union manifold3d réelle (pas juste un contact de
   │     surface — recouvrement volumique obligatoire), calé sur les
   │     bornes réelles du mesh (généralisé aux Shapes non rectangulaires)
   │
   └──► core/validation/
         mesh_checks.py (watertight/manifold/volume — bloquant)
         printability.py (composantes disjointes/dimensions/éléments fins
         — diagnostic informatif, jamais bloquant)
   │
   ▼
core/export/  → STL / 3MF multi-objets (trimesh.Scene, formats standards,
                aucune dépendance à un format propriétaire de slicer)
   │
   ▼
core/scene/serialization.py + project_io.py
   → bundle .l3dproj/ (project.json + source/ + masks/ + shapes/),
     chemins toujours relatifs, migrations v1→v6 chaînées et testées
```

`viewer/` et `ui/` se branchent sur ce pipeline en aval (affichage,
édition interactive) mais ne dupliquent jamais son calcul.

## Convention géométrique constante depuis la Phase 1A

```
X = largeur (image gauche → droite)
Y = hauteur (bas → haut du modèle, flip vertical à la lecture image)
Z = épaisseur (face arrière plane à Z=0 par défaut ; face avant = relief)
```

Toute nouvelle pièce géométrique (Backlight Insert compris) réutilise cette
convention plutôt que d'en inventer une nouvelle localement.

## Ce que ce document ne couvre pas

Les décisions et leurs raisons vivent dans `docs/03_DECISIONS.md`, pas ici.
Ce document décrit *quoi*, pas *pourquoi*.
