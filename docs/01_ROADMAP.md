# Roadmap officielle — route vers 1.0

*Confrontée à l'état réel du dépôt au moment de l'audit (0.4.1,
`docs/versions/CURRENT_STATE.md`). Une critique argumentée de cette
trajectoire (ordre des phases, faisabilité) figure dans le compte-rendu de
mission "Avis libre Claude" — ce document reste la proposition de
référence, pas encore amendée.*

Rappel de gouvernance : une nouvelle idée n'est pas automatiquement une
tâche de développement (voir `docs/02_IDEA_PARKING.md` et les règles de
`docs/06_TESTING_RELEASE_GATES.md`). Les phases ci-dessous restent une
proposition à confronter entre Mike, ChatGPT et Claude avant toute
nouvelle mission de développement.

## 0.4.x — Stabilisation *(en cours)*

- [x] Material Only — livré 0.4.1, invariance de géométrie prouvée par test.
- [x] Backlight Insert (prototype) — livré 0.4.1, **EXPERIMENTAL**.
      Premier test physique (2026-08-22) : FAIL (perforations en façade) ;
      hotfix v0.4.2 corrige un bug de collision insert/cavité mesuré et
      confirmé mais probablement pas suffisant à lui seul (voir
      CURRENT_STATE.md) — reste EXPERIMENTAL jusqu'au PASS physique V2.
- [ ] Validation Bambu Studio — jamais réalisée (accès refusé deux fois
      cette session via automatisation ; nécessite une action manuelle de
      Mike).
- [ ] Validation physique V2 Backlight Insert — pièce prête
      (`examples/physical_validation/backlight_v2/`), petite et rapide,
      jamais imprimée. **Prochaine étape avant toute nouvelle
      fonctionnalité Backlight.**
- [ ] Bugs UX critiques restants — aucun identifié activement à ce jour ;
      dépend des retours d'usage réel.
- Règle : aucune grosse nouvelle fonctionnalité tant que ces points ne sont
  pas clos.

**Puis : FEATURE FREEZE temporaire** — jusqu'à ce que la validation
physique (Bambu Studio + impression) referme la boucle ouverte par la 0.4.x.

## 0.5 — Print Intelligence

Première version déterministe (pas d'IA cloud nécessaire). Objectif :
analyser un projet avant impression plutôt qu'après échec.

Périmètre envisagé : profil imprimante, dimensions plateau, diamètre buse,
épaisseurs problématiques, détails trop fins, stabilité, analyse du pied,
orientation, avertissements et recommandations compréhensibles.

**Base existante à réutiliser, pas à réécrire** : `core/validation/
printability.py` fait déjà une partie de ce travail (composantes
disjointes, dimensions, éléments fins détectés par érosion) — 0.5 est une
extension de cette API existante, pas un nouveau module isolé.

## 0.6 — Image & Light Intelligence

- Optimisation photo pour lithophanie (contraste/luminosité/détails,
  presets adaptés).
- Amélioration du preview.
- Premières calibrations filament (transmission, épaisseur, comportement
  rétro-éclairé) — **prérequis direct** : Backlight Insert doit être sorti
  de son statut EXPERIMENTAL avant que cette calibration ait un sens
  (calibrer un phénomène jamais observé physiquement n'est pas possible).

## 0.7 — Productization

- Windows réel (premier build + lancement sur vraie machine — jamais fait
  à ce jour, c'est un vrai bloqueur, pas une formalité).
- macOS (déjà en bon état, maintenance continue).
- FR/EN + architecture i18n (**à construire depuis zéro** — aucune trace
  de `QTranslator`/`tr()` dans le code actuel, ce n'est pas une extension
  d'un système existant).
- Packaging (macOS déjà rodé, Windows à valider en conditions réelles).
- Onboarding, préférences utilisateur, gestion d'erreurs, performances.

## 0.8 — Private Beta

Objectif : 20 à 50 utilisateurs externes. Presque aucune nouvelle
fonctionnalité. Mesurer : compréhension, friction UX, crashes, impressions
ratées, fonctionnalités utilisées/ignorées, problèmes d'installation,
problèmes d'export.

**Prérequis technique non négociable avant cette phase** : un minimum de
crash reporting/error handling structuré doit exister (aujourd'hui : zéro
infrastructure de ce type dans le code) — sans ça, "mesurer les crashes"
n'est pas possible en beta externe.

## 0.9 — Commercial Release Candidate

Licensing, protection raisonnable contre le piratage, paiement,
distribution, updater, site, documentation, juridique, support.

## 1.0 — Commercial Release

Objectif business initial : 100 premiers clients payants qui ne
connaissent pas personnellement les créateurs du projet.

Après 1.0 : réévaluer P2/P3 selon retours clients, utilisation réelle,
potentiel commercial, coût de développement.

## Où en est-on réellement par rapport à cette trajectoire

Le point le plus important de l'audit pour cette roadmap : **le dépôt est
en excellent état technique pour 0.4.x, mais les fondations 0.7-0.8
(i18n, préférences, crash reporting, Windows réel) n'ont pas commencé du
tout.** Ce n'est pas une critique — c'est cohérent avec le fait que le
développement s'est concentré sur le cœur produit jusqu'ici — mais ça
signifie que 0.7 n'est pas "une passe de finition rapide", c'est un
chantier à part entière avec plusieurs zéros à combler.
