# CURRENT STATE — point d'entrée pour reprendre le projet

*Mis à jour à chaque release. Si ce document et le code divergent, le code
a raison — mettre à jour ce fichier, pas l'inverse.*

Dernière mise à jour : 2026-08-22, à la suite du hotfix v0.4.2 (garantie de
peau frontale du Backlight Insert, voir section dédiée plus bas) — HEAD de
départ du hotfix : `6abe390` (commit "Product reset - Road to 1.0
governance").

## Identité de version

| | |
|---|---|
| Version | **0.4.2** (source unique : `src/lithoshape3d/__init__.py`, lu par `pyproject.toml` via `dynamic = ["version"]`) |
| Dernier tag | `v0.4.1` (0.4.2 committé sans tag — validation physique V2 du Backlight Insert en attente, voir plus bas) |
| Tags précédents | v0.2.0, v0.3.0, v0.3.1, v0.4.0 |
| Tests | **346 passants**, 0 échec, `ruff check` clean |
| Répartition tests | core/ 174 · ui/ 127 · viewer/ 26 · ai/ 11 · racine (architecture/CLI/package) ~8 |
| TODO/FIXME/HACK dans `src/` | 0 (recherche exhaustive, aucun marqueur) |

## Plateformes réellement testées

| Plateforme | État réel |
|---|---|
| macOS (Apple Silicon) | **DONE** — build PyInstaller reconstruit et lancé réellement à chaque release depuis 0.3.0 (process confirmé vivant, log applicatif écrit). Non signé/non notarisé. |
| Windows | **BLOCKED** — `packaging/lithoshape3d_windows.spec` existe, toutes les dépendances ont des wheels `win_amd64`/Python 3.12 vérifiées sur PyPI, mais **aucune construction ni aucun lancement n'a jamais eu lieu sur une vraie machine Windows**. Bloqué faute de machine disponible dans les sessions jusqu'ici. |
| Linux | Non ciblé, non testé, non documenté comme objectif. |

## État des fonctions — statuts explicites

Légende : `DONE` (release-gate franchi) · `IMPLEMENTED_NOT_FIELD_VALIDATED`
(code + tests automatisés OK, jamais confronté à un usage/impression réels)
· `EXPERIMENTAL` (fonctionne mais paramètres/algorithme non stabilisés) ·
`TODO` (pas commencé) · `BLOCKED` (dépend d'une ressource indisponible).

### Cœur lithophanie / géométrie

| Fonction | Statut | Note |
|---|---|---|
| Import image + prétraitement | DONE | contraste/luminosité/inversion, presets |
| Génération lithophanie mono-zone | DONE | pipeline d'origine, le plus testé |
| Composition multi-zones (LithoFusion) | DONE | BASE/ADD/REPLACE, champ de hauteur NumPy, un seul appel mesh_builder |
| Mesh manifold/watertight | DONE | validé systématiquement (`core/validation/mesh_checks.py`), y compris masques trous/îlots |
| Export STL | DONE | |
| Viewer 3D (rotation/zoom/pan, vues) | DONE | |
| Aperçu rétro-éclairé | IMPLEMENTED_NOT_FIELD_VALIDATED | rendu logiciel plausible, jamais comparé à une vraie impression sous LED avant la démo Backlight Insert (voir plus bas) |
| Cadrage/zoom photo dans la Shape | DONE | `CadrageDialog`, ~0.7ms/évènement, aucun recalcul mesh pendant le glisser |
| Zoom/pan éditeur de masque | DONE | jusqu'à 800%, pixel-exact, testé avec le vrai SAM2 |

### Shape Composer (v0.4)

| Fonction | Statut | Note |
|---|---|---|
| Rectangle/Cercle/Ovale/Cœur/Étoile | DONE | un seul contrat `build_shape_mask`, pas 5 moteurs |
| Texte (police système) | DONE | trous préservés (testé "O"), lettres disjointes jamais reliées |
| Import SVG | DONE (scope volontairement limité) | rastérisé une fois via `QtSvg` puis traité comme une Shape Image — pas de vrai parseur vectoriel ; SVG complexe (dégradés, groupes imbriqués profonds) non garanti |
| Import image comme silhouette | DONE | |
| Bordure suivant contour | DONE | |
| Détection de composantes disjointes | DONE | jamais reliées automatiquement, remonté à l'utilisateur |
| Migration projet v4→v5 (Shape) | DONE | testée, aucun changement visuel d'un projet existant |

### Zones, masques, IA

| Fonction | Statut | Note |
|---|---|---|
| Zones (création/suppression/réordonnancement) | DONE | |
| Masques manuels (pinceau/gomme) | DONE | undo/redo **limité au masque en cours d'édition**, pas un undo/redo applicatif global |
| Sélection intelligente (SAM2 CoreML) | DONE **macOS uniquement** | `sys.platform != "darwin"` désactive explicitement la fonction sur Windows/Linux — aucun runtime CoreML là-bas. Sur Windows, seuls pinceau/gomme manuels restent disponibles. IoU>0.99 mesuré sur images carrées/rectangulaires (session antérieure), backend mock déterministe utilisé pour tous les tests automatisés |
| Téléchargement modèle SAM2 à la demande | DONE | ~95 Mo, jamais en CI |

### Matériaux / couleur

| Fonction | Statut | Note |
|---|---|---|
| Matériau par zone (nom/couleur/filament/slot) | DONE | |
| Partition mesh par matériau | DONE | même règle de recouvrement que la composition de hauteur |
| **Material Only** (couleur sans changement de géométrie) | DONE | corrige un bug réel signalé par l'utilisateur (relief involontaire) ; invariance de surface prouvée numériquement par test |
| **Backlight Insert** | EXPERIMENTAL | **PHYSICAL TEST #1 — FAIL** (voir note détaillée ci-dessous). Toujours EXPERIMENTAL après le hotfix v0.4.2 : correctif géométrique appliqué et testé, mais validation physique V2 en attente |
| Front Insert | TODO (non commencé, prévu dans l'enum) | |
| Export 3MF multi-matériaux | IMPLEMENTED_NOT_FIELD_VALIDATED | export standard `trimesh.Scene`, corps alignés dans le même repère — **jamais ouvert dans un vrai slicer** (Bambu Studio demandé deux fois cette session, accès refusé les deux fois par l'utilisateur via `request_access`, non contourné) |
| Pied d'impression (plat/renforcé) | DONE | généralisé aux silhouettes non rectangulaires (union manifold3d réelle, pas juste un contact de surface) |

#### Backlight Insert — PHYSICAL TEST #1 (2026-08-22)

Premier test physique réel (démo femme+rose, `examples/backlight_rose_demo/`,
skin=0.40mm, insert=0.60mm, clearance=0.20mm) : **FAIL**. La rose se
colore bien via l'insert rétro-éclairé (le principe optique est
prometteur — retenu comme signal positif), mais la façade présentait des
ouvertures/perforations à l'emplacement de la rose au lieu de rester une
lithophanie blanche continue.

Diagnostic numérique (hotfix v0.4.2, mission dédiée) : le fichier STL livré
était en réalité **géométriquement parfait** — watertight, manifold, peau
blanche exactement 0.40mm partout où une cavité existait (0 point sous la
valeur demandée, vérifié sur les 10 768 points de la zone). Un vrai bug
distinct a été mesuré et corrigé : l'insert (pavé uniforme 0.60mm) n'était
jamais vérifié contre la profondeur réelle de cavité disponible et pouvait
localement chevaucher le corps blanc solide aux points les plus fins de la
lithophanie (5 points sur 10 768 dans cette démo, jusqu'à 0.047mm de
chevauchement) — corrigé dans `core/geometry/backlight.py` : ces points ne
reçoivent plus de cavité (façade préservée, signalé dans `warnings`, jamais
silencieux). 4 nouveaux tests de régression (`tests/core/geometry/test_backlight.py`).

Cette correction, mesurée, ne suffit probablement PAS à expliquer l'ampleur
du défaut physique observé (5/10768 points, ≤0.05mm — trop marginal). La
cause dominante suspectée reste **physique/impression** : un pont/plafond
non supporté d'environ 0.40mm (~2 couches) suivant un contour organique
complexe est intrinsèquement marginal à imprimer de façon fiable en FDM —
hypothèse non résolue par ce hotfix, nécessitant soit une peau plus épaisse
(à valider empiriquement, pas de changement de défaut arbitraire), soit des
réglages de pont dédiés, soit les deux.

Une pièce de validation V2, petite et rapide (`examples/physical_validation/backlight_v2/`,
55×53mm, même photo/pipeline SAM2 réel, mêmes paramètres skin/insert/clearance
non modifiés), est prête à imprimer pour confirmer si le correctif +
d'éventuels réglages d'impression suffisent. **Backlight Insert reste
EXPERIMENTAL** jusqu'au PASS de ce test V2 — ne pas considérer DONE sur la
seule base de la correction logicielle.

### Projet / plateforme

| Fonction | Statut | Note |
|---|---|---|
| Sauvegarde/réouverture `.l3dproj` | DONE | bundle-dossier portable, chemins relatifs, migrations v1→v6 toutes testées |
| Undo/Redo applicatif (zones, paramètres, forme) | TODO | seul le masque en cours d'édition a un undo/redo (voir ci-dessus) |
| Gestion d'erreurs utilisateur | DONE (basique) | messages `QMessageBox` explicites sur échec de génération/export/ouverture ; pas de rapport de crash structuré |
| Crash reporting | TODO | aucune infrastructure (pas de sentry/faulthandler applicatif) |
| Préférences utilisateur persistées | TODO | aucun `QSettings`, tout se réinitialise entre lancements |
| i18n (architecture de traduction) | TODO | recherche exhaustive : aucun `QTranslator`/`tr()`/fichier `.ts` — l'app est **100% française, codée en dur**, zéro infrastructure de traduction |
| Licensing / protection commerciale | TODO | aucune trace dans le code (recherche exhaustive) |
| Packaging macOS | DONE | |
| Packaging Windows | BLOCKED | voir tableau plateformes ci-dessus |
| Onboarding utilisateur | TODO | aucun tutoriel/premier lancement guidé |

## Dette technique identifiée pendant l'audit (non traitée — hors scope de cette mission)

- `GeometryParameters.base_shape: str = "rectangle"` est un champ **vestigial** : jamais positionné à autre chose que `"rectangle"` nulle part dans l'UI ou ailleurs ; seul `build_slab_mesh` (moteur mono-zone historique) le vérifie encore. Candidat à suppression lors d'un futur nettoyage, pas traité ici (règle « pas de refactoring gratuit »).
- Aucune dépendance ajoutée cette mission ; aucun fichier moteur touché.

## Release gate actuel

**Franchi pour 0.4.1** : tests unitaires + intégration + E2E réel (2 scénarios : Cœur+rose, Backlight Insert) + lint + build macOS reconstruit et lancé réellement + migration projet testée + STL/3MF validés watertight par des tests automatisés + sauvegarde/réouverture testée.

**Non franchi** : validation 3MF dans un vrai slicer, impression physique de référence, tout test Windows réel.

## Prochaine étape officielle

Décidée par Mike (Product Owner) après revue du présent audit avec ChatGPT.
Ce document ne préjuge pas de la prochaine mission — voir
`docs/01_ROADMAP.md` pour la proposition de trajectoire vers 1.0 et
`docs/versions/CURRENT_STATE.md` (ce fichier) pour reprendre le contexte
technique exact au moment voulu.
