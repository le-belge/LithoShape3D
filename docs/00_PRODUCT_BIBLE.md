# Product Bible — LithoShape3D

*Document de référence produit. Toute décision de roadmap ou de priorité
doit pouvoir se justifier par rapport à ce document. Propriétaire : Mike
(Product Owner). Voir `docs/versions/CURRENT_STATE.md` pour l'état
technique réel correspondant, et la section "Avis libre Claude" de
`docs/06_TESTING_RELEASE_GATES.md`... non — voir le compte-rendu de mission
pour une critique argumentée de ce document.*

## North Star (formulation actuelle)

> LithoShape3D doit permettre à quelqu'un qui sait utiliser une imprimante
> 3D, mais pas un logiciel de CAO, de passer d'une image à un objet
> personnalisé réellement imprimable en quelques minutes.

Cette formulation est ouverte à la critique (voir compte-rendu de mission)
mais constitue la base actuelle et n'est pas modifiée dans ce document.

## Mission 1.0

Transformer facilement une photo en lithophanie personnalisée, imprimable
et éventuellement multicolore, sans obliger l'utilisateur à jongler entre
Blender, Fusion 360 ou plusieurs outils spécialisés.

## Principes non négociables

1. Image → objet imprimable doit rester simple.
2. L'utilisateur ne doit pas avoir besoin de comprendre la CAO.
3. Les fonctions avancées ne doivent pas dégrader le workflow simple.
4. Le résultat exporté doit être réellement imprimable.
5. Les erreurs doivent être détectées avant impression autant que possible.
6. L'IA doit assister et non rendre le logiciel dépendant d'elle.
7. Le workflow manuel doit toujours rester disponible.
8. `core` reste indépendant de Qt/PyVista/VTK.
9. Les projets restent versionnés et migrables.
10. Géométrie, composition et matériau sont des concepts séparés.
11. Une couleur ne modifie jamais implicitement la géométrie.
12. Une fonctionnalité doit être testable.
13. Les formats standards sont privilégiés.
14. macOS + Windows sont les plateformes commerciales prioritaires.
15. Français + anglais sont les langues minimales prévues pour la
    commercialisation.
16. Le projet est conçu pour être commercialisé, maintenu et distribué.
17. Une fonction spectaculaire ne doit jamais compromettre la fiabilité du
    cœur du produit.

### État réel de ces principes (audit, pas une opinion)

Les principes 8, 9, 10, 11, 12, 13 sont **vérifiés par le code et les
tests aujourd'hui** — ce ne sont pas des aspirations, voir
`docs/versions/CURRENT_STATE.md` et `docs/07_ARCHITECTURE.md`.

Les principes 14 (Windows) et 15 (anglais) sont des **objectifs affirmés,
pas encore des faits techniques** : aucun test réel sur machine Windows,
aucune infrastructure de traduction dans le code (recherche exhaustive,
zéro `QTranslator`/`tr()`/fichier `.ts`). Voir CURRENT_STATE.md.

## Ce que LithoShape3D N'EST PAS pour la 1.0

- Pas Blender.
- Pas Fusion 360.
- Pas un logiciel CAO généraliste.
- Pas un slicer.
- Pas une marketplace.
- Pas encore un générateur universel de produits 3D.
- Pas encore LightSign.
- Pas encore un moteur de personnalisation sportive.
- Pas encore un assistant de conception universel.

Ces exclusions sont volontaires et **protègent le scope** — voir
`docs/02_IDEA_PARKING.md` pour où vivent ces idées en attendant.

## Utilisateur cible (rappel synthétique — détail dans 05_BUSINESS.md)

Un possesseur d'imprimante 3D qui sait déjà slicer et imprimer, mais ne
veut pas apprendre un logiciel de CAO généraliste uniquement pour fabriquer
des objets personnalisés (lithophanies, objets photo, formes découpées).

## Comment lire ce document dans le temps

Ce document est stable par nature — il ne change pas à chaque release.
Les statuts d'implémentation des principes vivent dans
`docs/versions/CURRENT_STATE.md`, mis à jour à chaque version. Si un
principe listé ici s'avère contredit durablement par une décision produit
réelle, ce document doit être révisé explicitement par Mike — pas laissé
silencieusement obsolète.
