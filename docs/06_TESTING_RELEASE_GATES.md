# Testing & Release Gates + Gouvernance

## Principe

**Une version n'est pas terminée parce que le code est écrit.** Chaque
version doit franchir un *exit gate* explicite avant d'être taguée. Ne
jamais marquer `DONE` (dans `docs/versions/CURRENT_STATE.md` ou ailleurs)
uniquement parce que le code existe — voir Règle 10 plus bas.

## Exit gate — checklist type

Selon la nature des changements d'une version, tout ou partie de :

- [ ] Tests unitaires (core/) passants.
- [ ] Tests d'intégration (ui/, viewer/) passants.
- [ ] Au moins un test E2E réel pilotant la vraie `MainWindow` (pas
      seulement des unit tests — c'est la classe de bug qui a
      historiquement échappé aux tests unitaires dans ce projet, voir
      `docs/03_DECISIONS.md` et les exemples concrets ci-dessous).
- [ ] Lint (`ruff check`) clean.
- [ ] Build packaging (macOS a minima).
- [ ] Lancement réel du build (process confirmé vivant, pas seulement
      "la construction a réussi").
- [ ] Migration de projet testée si le format a changé (aucun reset
      silencieux, comportement historique préservé pour les projets
      existants).
- [ ] STL/3MF générés validés manifold/watertight par un test automatisé.
- [ ] Sauvegarde/réouverture testée pour toute nouvelle donnée persistée.
- [ ] Performances vérifiées si le changement touche un chemin
      interactif (ex. cadrage, zoom/pan).
- [ ] Tests physiques (impression réelle) si le résultat dépend
      intrinsèquement du monde physique (Backlight Insert, futures
      calibrations filament) — **les tests automatisés ne remplacent
      jamais ça**, voir Règle 11.
- [ ] Windows réel si le changement affecte un chemin spécifique à cette
      plateforme.
- [ ] macOS réel systématiquement (déjà en place depuis 0.3.0).

### Pourquoi le test E2E réel est non négociable

Fait établi par l'historique du projet, pas une opinion : plusieurs bugs
réels et significatifs n'ont été trouvés **que** par un test E2E pilotant
la vraie application, jamais par la suite de tests unitaires seule :

- 0.2.0 : crash SIGSEGV à la fermeture de fenêtre (VTK + Cocoa), et
  corruption de `composition_mode` en changeant de zone active (signaux
  non bloqués).
- 0.4.0 : désalignement zone/photo après cadrage (la "rose" se détachait
  du sujet), pied d'impression flottant sur les Shapes non rectangulaires,
  Shape/cadrage jamais relus à la réouverture d'un projet.

Aucun de ces bugs n'était couvert par les tests unitaires existants au
moment où il a été introduit. C'est un signal structurel, pas une
coïncidence : ce projet a un historique concret de bugs qui ne vivent
qu'à l'intersection de plusieurs modules, invisibles module par module.

## Golden Workflow

Scénario emblématique actuel, à faire évoluer progressivement en **test
produit de référence** (au-delà d'un test automatisé — un scénario que
Mike ou un testeur externe peut rejouer manuellement pour juger de
l'expérience, pas seulement de la correction technique) :

1. Ouvrir photo.
2. Cadrer.
3. Choisir forme cœur.
4. Sélectionner la rose.
5. Corriger le masque.
6. Choisir couleur.
7. Material Only.
8. Générer.
9. Viewer.
10. Aperçu rétro-éclairé.
11. Ajouter pied.
12. Export 3MF.
13. Sauvegarder.
14. Fermer.
15. Rouvrir.
16. Vérifier état.
17. Ouvrir dans slicer.
18. Imprimer.

**État réel de couverture (audit)** : les étapes 1 à 16 sont couvertes par
un test E2E automatisé réel (`tests/ui/test_e2e_heart_rose.py`, avec
Material Only comme stratégie couleur par défaut désormais). Les étapes
17 et 18 (slicer réel, impression réelle) n'ont **jamais** été exécutées
— c'est le trou le plus significatif de la couverture actuelle par
rapport à ce golden workflow.

## Statuts explicites (rappel, détaillés dans CURRENT_STATE.md)

`DONE` · `IMPLEMENTED_NOT_FIELD_VALIDATED` · `EXPERIMENTAL` · `TODO` ·
`BLOCKED`. Ne jamais utiliser `DONE` pour quelque chose simplement parce
que le code existe (Règle 10).

---

## Règles de gouvernance

**Règle 1** — Toute nouvelle idée est d'abord classée P0/P1/P2/P3 (voir
`docs/02_IDEA_PARKING.md` pour le mécanisme de capture).

**Règle 2** — Une idée P3 ne déclenche pas de développement immédiat.

**Règle 3** — Claude Code ne choisit pas automatiquement la prochaine
grosse phase. Fin de mission : compte-rendu → Mike + ChatGPT → revue →
décision → nouvelle mission éventuelle.

**Règle 4** — Claude dispose d'un droit de proposition.

**Règle 5** — Claude dispose d'un droit d'alerte. S'il identifie une
mauvaise architecture, une dette dangereuse, un risque commercial, une
incohérence, une fonctionnalité inutile ou un scope excessif, il doit le
signaler.

**Règle 6** — Claude peut être en désaccord avec Mike ou ChatGPT. Une
objection argumentée est préférable à une validation complaisante.

**Règle 7** — Droit de proposition ≠ droit d'implémentation. Claude ne
développe aucune idée supplémentaire sans validation.

**Règle 8** — Pas de refactoring sans problème concret.

**Règle 9** — Pas de dépendance importante sans justification.

**Règle 10** — Pas de `DONE` sans release gate franchi.

**Règle 11** — Les tests automatisés ne remplacent pas les tests
physiques lorsque le résultat dépend de l'impression réelle.

**Règle 12** — Toute fonction doit préserver le workflow simple.

**Règle 13** — La commercialisation est un objectif architectural.

**Règle 14** — La fiabilité du cœur prime sur une fonctionnalité
spectaculaire.

### Répartition des rôles (rappel)

- **Mike** — Product Owner, décision finale.
- **ChatGPT** — produit, stratégie, recherche, priorisation, orchestration
  des futures missions.
- **Claude Code** — implémentation, architecture réelle du dépôt, analyse
  technique, tests, identification des risques, propositions techniques
  et produit.

Les trois peuvent proposer. Les trois peuvent être en désaccord. Les
désaccords doivent être argumentés. Aucune idée ne devient
automatiquement une fonctionnalité.
