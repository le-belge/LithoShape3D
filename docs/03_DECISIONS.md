# Journal de décisions techniques

Format par entrée : **Décision** · **Raison** · **Alternatives rejetées**
(si connues) · **Conséquences** · **Phase approximative**.

Règle appliquée en écrivant ce document : si la raison exacte d'une
décision ancienne n'est pas connue avec certitude, elle est marquée
`RAISON APPROXIMATIVE` plutôt qu'inventée.

---

### Python 3.11+, `src/` layout, `hatchling`

**Décision** : projet Python packagé en `src/lithoshape3d/`, build backend
`hatchling`, version dynamique lue depuis `__init__.py`.
**Raison** : layout `src/` évite les imports accidentels du code non
installé pendant les tests ; version dynamique évite la classe de bug
"version qui diverge entre plusieurs fichiers" (rencontrée concrètement en
0.3.1 : `pyproject.toml` et `packaging/*.spec` avaient chacun leur propre
version figée, désynchronisée du titre de fenêtre réel).
**Conséquences** : un seul endroit à changer pour bumper la version ; un
test dédié (`test_package_metadata_version_matches_module_version`) garde
ça vrai dans le temps.
**Phase** : dès la Phase 0.

---

### PySide6 (pas PyQt)

**Décision** : PySide6 pour l'UI.
**Raison** : `RAISON APPROXIMATIVE` — licence LGPL (vs GPL/commercial pour
PyQt), pertinent pour un projet à vocation commerciale. Cohérent avec les
principes du Product Bible (commercialisation = objectif architectural
depuis le début), mais la décision elle-même précède la formalisation
explicite de ce principe.
**Phase** : Phase 1C (première UI).

---

### PyVista / PyVistaQt pour le rendu 3D

**Décision** : PyVista (wrapper VTK haut niveau) plutôt que VTK brut ou un
moteur maison.
**Raison** : `SceneViewer` prend un plotter **injecté** (`pv.Plotter` ou
`pyvistaqt.QtInteractor`), ce qui rend le viewer testable off-screen sans
jamais ouvrir de vraie fenêtre — décision structurante qui a permis tous
les tests automatisés du viewer et de l'UI (`main_window` fixture avec
`pv.Plotter(off_screen=True)`).
**Conséquence connue et documentée** : `QT_QPA_PLATFORM=offscreen` fait
planter (segfault) VTK/PyVistaQt sur macOS — ne jamais le forcer avec un
vrai backend Qt ; un `pv.Plotter(off_screen=True)` sans Qt fonctionne bien
en revanche (c'est ce que toute la suite de tests utilise).
**Phase** : Phase 1B.

---

### NumPy vectorisé pour la géométrie, pas de boucle Python par pixel

**Décision** : construction du mesh (front/back/parois) entièrement
vectorisée NumPy ; seule la détection des arêtes de bord parcourt une
boucle Python, et seulement sur le **périmètre** du masque (pas sa
surface).
**Raison** : mesuré — benchmark confirme un coût quasi-nul (moins de
350ms même à haute résolution) ; la boucle sur le périmètre reste rapide
car son coût croît avec le contour, pas l'aire.
**Alternative rejetée** : boucle par cellule de grille (bien plus lente,
jamais implémentée car le vectorisé a fonctionné dès le prototype).
**Phase** : Phase 2B (masques irréguliers).

---

### trimesh + manifold3d, pas de moteur CAO maison

**Décision** : `trimesh.Trimesh` comme structure de mesh universelle,
`manifold3d` réservé aux opérations booléennes réelles (union du pied,
union du corps blanc + renforts) et à la validation finale — jamais pour
composer des Zones entre elles (ça reste un champ de hauteur NumPy
séquentiel, pas des booléens 3D).
**Raison** : `RAISON APPROXIMATIVE` (jamais formalisée noir sur blanc dans
les sessions passées) — probablement : booléens 3D répétés sont coûteux et
fragiles (topologie), un champ de hauteur composé une fois puis maillé une
seule fois est plus simple à garantir manifold.
**Fait empirique important, documenté dans le code** : une union
manifold3d entre deux solides qui ne font qu'**affleurer** (faces
coïncidentes, aucun recouvrement volumique réel) peut les laisser
distincts (`connected_components > 1`) au lieu de les fusionner. Toute
pièce générée pour être fusionnée (pied, renforts, cavité Backlight
Insert) doit être dimensionnée pour un recouvrement volumique réel — cette
règle a dû être réappliquée deux fois indépendamment (pied plat vs
Shapes non rectangulaires en 0.4.0, renforts vs pied plat en 0.4.1).
**Phase** : Phase 1A (trimesh), Phase 0.3.0 (premier usage réel de
manifold3d pour construire, pas seulement valider).

---

### `core/` headless, jamais de Qt/PyVista/VTK

**Décision** : frontière stricte, vérifiée par un test automatisé
(`test_architecture_boundaries.py`, import en sous-processus).
**Raison** : permet CLI headless, tests rapides sans fenêtre, et évite
qu'une logique métier ne finisse dupliquée entre `core/` et `ui/`.
**Conséquence concrète** : quand du texte a dû être rendu pour une Shape
"Texte" (v0.4), le choix a été Pillow (`ImageFont`/`ImageDraw`) plutôt que
`QFont`/`QPainter`, précisément pour ne pas casser cette frontière ; l'
import SVG (qui a réellement besoin de Qt, `QSvgRenderer`) a été placé
dans `ui/shape_svg_import.py`, pas dans `core/`, pour la même raison.
**Phase** : Phase 1B (test créé), respectée depuis sans exception.

---

### Scene multi-zones (LithoFusion) plutôt qu'un mono-objet

**Décision** : `Scene.zones: list[Zone]`, composées séquentiellement en un
champ de hauteur unique.
**Raison** : nécessaire dès qu'on veut plusieurs régions de comportement
différent (relief différent, matériau différent) sur une même image —
c'est devenu le socle de toutes les fonctionnalités ultérieures
(matériaux, Shape Composer, Backlight Insert n'auraient pas pu exister
sans ce socle).
**Conséquence structurante** : `ReliefMode` et `CompositionMode` ont été
gardés strictement indépendants dès le départ ("Concept indépendant de
ReliefMode", commentaire dans le code) — ce découplage a permis d'ajouter
`ColorStrategy` comme un troisième axe orthogonal en 0.4.1 sans toucher
aux deux premiers.
**Phase** : Phase 2A→2C.

---

### Masque = float32 [0,1], stocké en PNG 8 bits

**Décision** : convention unique du dépôt pour tout masque (Zone, Shape,
Backlight Insert).
**Raison** : `RAISON APPROXIMATIVE` — float32 [0,1] laisse la porte
ouverte à un feathering futur (bords progressifs) sans jamais avoir muté
le masque source pour la décision de topologie (le seuillage binaire, ex.
`DEFAULT_MASK_THRESHOLD`, reste une étape séparée en aval, jamais
destructive) ; PNG 8 bits pour la persistance reste un format universel,
lisible par n'importe quel outil, pas de dépendance à un format
propriétaire.
**Phase** : Phase 2A.

---

### Bundle-dossier `.l3dproj/`, pas un fichier unique

**Décision** : un projet est un dossier (`project.json` + `source/` +
`masks/` + `shapes/`), tous les chemins internes relatifs.
**Raison** : rend le projet déplaçable/copiable tel quel (vérifié
explicitement par un test de portabilité : déplacer le bundle et supprimer
l'original, il se recharge quand même).
**Phase** : Phase 2A.

---

### `format_version` explicite + migrations chaînées

**Décision** : chaque évolution du schéma JSON incrémente
`CURRENT_FORMAT_VERSION` et ajoute une fonction `_migrate_vN_to_vN+1`
purement additive, jamais de "devine le format".
**Raison** : garantit qu'un ancien projet reste ouvrable sans jamais
changer silencieusement de comportement — condition explicitement testée
à chaque migration (ex. migration Shape v4→v5 : un projet existant devient
`Shape=Rectangle` avec cadrage identité, prouvé visuellement identique).
**Conséquence documentée** : la migration v5→v6 (ColorStrategy) donne
`color_strategy=None` à toute zone existante plutôt que `MATERIAL_ONLY`,
précisément pour ne jamais réinterpréter rétroactivement l'intention d'une
zone déjà existante (elle pouvait être une vraie zone géométrique, ex.
gravure).
**Phase** : dès Phase 2A (v1→v2), 6 versions à ce jour.

---

### SAM2 local (CoreML), IA facultative

**Décision** : segmentation intelligente via un modèle SAM2.1 Small
converti CoreML, exécuté localement, téléchargé à la demande (~95 Mo, mis
en cache utilisateur), jamais en CI.
**Raison** : garde le logiciel utilisable sans compte/abonnement/réseau
pour la fonction de sélection — cohérent avec le principe produit "l'IA
doit assister, pas rendre le logiciel dépendant d'elle" (voir Product
Bible).
**Conséquence structurante** : `SegmentationBackend` est une interface
(`ai/segmentation/base.py`), avec un `MockSegmentationBackend`
déterministe utilisé par **tous** les tests automatisés — le vrai backend
CoreML n'est exercé que par des tests optionnels, sautés silencieusement
si le modèle n'est pas en cache.
**Limite acceptée et documentée** : CoreML est une techno Apple —
`Sam2CoreMLBackend.is_available()` retourne explicitement `False` sur
non-macOS (`sys.platform != "darwin"`), pas un TODO caché : la sélection
intelligente est **actuellement une fonction macOS uniquement**.
**Alternative rejetée** : aucune trace d'un backend alternatif
(ONNX/PyTorch cross-plateforme) tenté ou même évalué dans ce dépôt à ce
jour — pas une décision documentée, une absence de décision.
**Phase** : 0.2.0.

---

### `ColorStrategy` comme axe orthogonal (pas une extension de `CompositionMode`)

**Décision** : nouveau champ `Zone.color_strategy: ColorStrategy | None`,
plutôt que d'ajouter un nouveau membre à `CompositionMode` ou de changer
le comportement par défaut de `ADD`.
**Raison** : un bug réel signalé par l'utilisateur (une zone de couleur
"ressortait en relief") venait du fait que le workflow naturel (nouvelle
zone → sélection SAM2 → matériau) laissait `CompositionMode.ADD` actif par
défaut, ajoutant silencieusement une hauteur non désirée. Changer le
comportement de `ADD`/`REPLACE` directement aurait cassé 3 tests
existants qui valident explicitement que `REPLACE` change la hauteur (cas
d'usage légitime : gravure). Un axe séparé, optionnel, avec un défaut
`None` qui préserve tout l'historique, a résolu le bug sans regarder en
arrière.
**Conséquences** : `MATERIAL_ONLY` (skip total de la hauteur, quel que
soit le `CompositionMode`) et `BACKLIGHT_INSERT` (même garantie + cavité +
insert séparé) partagent la même règle de composition ; `None` reste le
seul état qui laisse `CompositionMode`/`ReliefMode` faire foi.
**Phase** : 0.4.1.

---

### Formats standards avant formats propriétaires (3MF/STL, pas de format Bambu)

**Décision** : export 3MF via `trimesh.Scene.export(file_type="3mf")`
(standard, plusieurs objets nommés), jamais le format `.3mf` propriétaire
Bambu Studio (qui embarque des paramètres internes spécifiques au
slicer).
**Raison** : objectif explicite qu'un slicer tiers (Bambu Studio inclus)
importe le fichier avec plusieurs objets déjà alignés, puis laisse
l'utilisateur assigner un filament par objet — pas de rétro-ingénierie
d'un format propriétaire.
**Limite non résolue** : ce choix n'a **jamais été vérifié dans un vrai
slicer** — la garantie "Bambu Studio importe correctement" reste une
hypothèse de conception, pas un fait observé (accès refusé deux fois lors
des tentatives de vérification via automatisation cette session).
**Phase** : 0.3.0.

---

### macOS + Windows comme cibles commerciales

**Décision explicite du Product Owner** (formulée dans le Product Bible) :
macOS et Windows sont les deux plateformes prioritaires pour la
commercialisation.
**État réel** : macOS activement construit/lancé à chaque release ;
Windows a un spec PyInstaller écrit et des dépendances vérifiées
disponibles en wheel, mais zéro exécution réelle — c'est un **choix
produit affirmé**, pas encore une réalité technique vérifiée côté Windows.
**Phase** : formalisé dans cette mission (Product Reset), mais implicite
depuis que le spec Windows existe (0.3.0).
