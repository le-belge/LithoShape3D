# Idea Parking

**IDEA PARKING ≠ ROADMAP.** Une excellente idée peut rester volontairement
non planifiée. Aucune entrée de ce document ne devient une tâche de
développement sans passer explicitement par la classification P0-P3 puis
une décision de Mike (voir règles de gouvernance,
`docs/06_TESTING_RELEASE_GATES.md`).

---

## LightSign

**Description** : génération d'enseignes lumineuses imprimables — texte,
logos, lettres-caissons, diffuseur, coque, logement ruban LED, passage
câble, fond, fixations, découpe automatique selon plateau, BOM LED.
**Problème utilisateur résolu** : fabriquer une enseigne lumineuse
personnalisée sans logiciel CAO ni compétences électroniques poussées.
**Cible** : commerces, particuliers, événementiel.
**Potentiel commercial** : moyen à élevé — marché adjacent réel (Etsy/
Printables regorgent de ce type de projet), mais très concurrentiel côté
modèles gratuits déjà existants.
**Valeur utilisateur** : forte, si l'exécution est bonne.
**Difficulté estimée** : élevée — ce n'est pas une variation du pipeline
lithophanie, c'est un **second domaine géométrique** (coques creuses,
tolérances de logement LED, passages de câbles, ventilation thermique)
avec ses propres contraintes physiques (chaleur, alimentation électrique)
que le moteur actuel ne modélise pas du tout.
**Différenciation** : moyenne — proche de logiciels dédiés existants
(certains outils no-code d'enseignes LED).
**Dépendances architecturales** : nécessiterait probablement un nouveau
sous-module géométrique complet, pas une extension de `core/geometry/`
existant.
**Priorité** : P3.
**Statut** : parking.
**Raison du report** : hors North Star actuelle (objet 2D-relief à partir
d'une photo) ; risque de dispersion majeur signalé explicitement par la
mission elle-même.

---

## Sport / Jersey

**Description** : création de produits inspirés des maillots de clubs —
forme maillot, couleurs, logo, sponsor, nom, numéro, relief, AMS,
porte-clés, plaques, décorations murales.
**Problème utilisateur résolu** : personnalisation rapide d'objets à thème
sportif (fans, clubs amateurs, cadeaux).
**Cible** : supporters, clubs amateurs, boutiques de club.
**Potentiel commercial** : moyen — marché de niche mais fidèle, cycle
saisonnier (rentrée sportive, fêtes).
**Valeur utilisateur** : moyenne à forte pour la cible concernée.
**Difficulté estimée** : moyenne — pourrait en partie réutiliser Shape
Composer (silhouette de maillot = une Shape de plus) et le système de
matériaux/couleurs existant, mais la gestion de texte+numéro+logo combinés
sur une forme complexe est un vrai morceau UX, pas juste une nouvelle
Shape.
**Différenciation** : faible à moyenne — produit très identifiable donc
imitable rapidement par un concurrent.
**Dépendances architecturales** : Shape Composer (existant), Batch
Personalization (voir plus bas, pour les séries de noms/numéros).
**Priorité** : P3.
**Statut** : parking.
**Raison du report** : fonctionnalité verticale spécifique à un usage,
pas au cœur du produit actuel.

---

## Batch Personalization

**Description** : import CSV (ex. `MARTIN,7` / `NOEL,10` / `DUPONT,14`) →
génération automatique d'une série personnalisée.
**Problème utilisateur résolu** : produire N variantes d'un même gabarit
(club, entreprise, événement) sans répéter le workflow manuellement N fois.
**Cible** : clubs, entreprises, organisateurs d'événements, revendeurs.
**Potentiel commercial** : moyen à élevé — argument de vente B2B/volume
réel (un revendeur qui imprime 30 plaques identiques avec juste un nom qui
change).
**Valeur utilisateur** : forte pour un usage volume, nulle pour un usage
occasionnel.
**Difficulté estimée** : moyenne — le pipeline de composition actuel est
déjà entièrement scriptable/headless (`core/` n'a aucune dépendance UI),
ce qui rend un mode batch **techniquement moins coûteux qu'il n'y paraît**
si le gabarit reste simple (texte/numéro variable sur une Shape fixe).
Devient nettement plus difficile si le gabarit doit varier en photo/masque
par ligne du CSV.
**Différenciation** : moyenne à élevée — peu d'outils grand public
proposent ça pour de la lithophanie/gravure personnalisée.
**Dépendances architecturales** : Shape Composer + Texte (existants),
aucune dépendance non résolue identifiée pour le cas simple (texte
variable).
**Priorité** : P2.
**Statut** : à étudier après 1.0 — voir aussi la question 9 du
compte-rendu de mission (fonctionnalité à forte valeur mais étonnamment
accessible avec l'architecture actuelle).

---

## Templates

**Description** : gabarits réutilisables pour clubs, entreprises, mariages,
cadeaux, associations.
**Problème utilisateur résolu** : réduire le temps de mise en route pour
des cas d'usage récurrents.
**Cible** : tous segments, transversal.
**Potentiel commercial** : moyen — plutôt un multiplicateur de valeur pour
d'autres fonctionnalités (Batch, LightSign, Sport) qu'une fonctionnalité
autonome.
**Valeur utilisateur** : moyenne isolément, forte combinée à Batch
Personalization.
**Difficulté estimée** : faible à moyenne — `.l3dproj` est déjà un format
de projet portable et versionné ; un "template" pourrait être, dans sa
version la plus simple, un `.l3dproj` sans image source figée. Se
complexifie si on veut un vrai système de paramètres exposés/verrouillés.
**Différenciation** : faible seule.
**Dépendances architecturales** : format `.l3dproj` (existant).
**Priorité** : P3.
**Statut** : parking, à reconsidérer si Batch Personalization avance.

---

## Projection sur objet 3D (STL/OBJ/3MF importé)

**Description** : projection future d'image/couleur/relief sur un
STL/OBJ/3MF importé (pas seulement une grille plane).
**Problème utilisateur résolu** : appliquer une lithophanie/un motif sur
une forme 3D existante, pas seulement un panneau plat.
**Cible** : utilisateurs avancés, cas créatifs.
**Potentiel commercial** : incertain — dépend fortement de la qualité
d'exécution (le mapping image→surface 3D non plane est un problème
géométrique nettement plus dur que tout ce qui existe aujourd'hui).
**Valeur utilisateur** : forte si bien fait, frustrante si mal fait
(déformations, seams visibles).
**Difficulté estimée** : élevée — sort complètement du modèle actuel
"champ de hauteur sur une grille plane" (`core/geometry/mesh_builder.py`
tout entier repose sur cette hypothèse). Ce n'est pas une extension, c'est
un second moteur géométrique.
**Différenciation** : élevée si réussi — peu d'outils grand public le
font bien.
**Dépendances architecturales** : nécessiterait probablement un nouveau
moteur (UV mapping ou displacement sur mesh arbitraire), largement
indépendant de `core/geometry/` actuel.
**Priorité** : P3.
**Statut** : à étudier après 1.0.
**Raison du report** : incompatible avec le principe "pas de refactoring
massif / pas de second moteur géométrique parallèle" tant que le cœur
plan n'est pas stabilisé et commercialisé.

---

## Marketplace

**Description** : templates/projets partageables ou vendables entre
utilisateurs.
**Problème utilisateur résolu** : distribution/monétisation de créations
par la communauté, pas seulement par l'éditeur.
**Cible** : créateurs actifs, revendeurs.
**Potentiel commercial** : élevé à long terme, nul avant qu'une base
d'utilisateurs existe.
**Valeur utilisateur** : nulle sans masse critique de contenu/utilisateurs.
**Difficulté estimée** : élevée — ce n'est pas une fonctionnalité logicielle
mais une plateforme (comptes, paiement, modération, hébergement,
CGU/propriété intellectuelle) : un projet à part entière.
**Différenciation** : forte si exécutée après une base installée, sinon
sans objet.
**Dépendances architecturales** : nécessite un backend cloud qui n'existe
pas aujourd'hui (le produit est actuellement 100% local/desktop).
**Priorité** : P3.
**Statut** : parking, explicitement hors sujet avant 1.0.
**Raison du report** : dépend d'une base d'utilisateurs qui n'existe pas
encore ; mélangerait un objectif produit (outil de création) avec un
objectif plateforme (marché) prématurément.

---

## Cylindres / abat-jour / formes 3D avancées

**Description** : Shape Composer étendu à des formes non planes
(cylindre, cône, abat-jour) plutôt qu'un panneau plat.
**Problème utilisateur résolu** : lithophanies "lampe" à 360°, un cas
d'usage très demandé dans la communauté lithophanie en général.
**Cible** : grand public, cadeaux, décoration.
**Potentiel commercial** : élevé — c'est un des usages les plus recherchés
du genre "lithophanie" en dehors du panneau mural.
**Valeur utilisateur** : forte.
**Difficulté estimée** : élevée — même famille de problème que la
"Projection sur objet 3D" ci-dessus (sortir du modèle "grille plane"), en
plus contraint par le fait qu'un cylindre doit rester imprimable sans
support interne (auto-portant en impression 3D FDM classique).
**Différenciation** : élevée si bien fait.
**Dépendances architecturales** : nouveau moteur géométrique (même famille
que la projection sur objet 3D — pourrait potentiellement être unifié
avec elle plutôt que développé deux fois séparément).
**Priorité** : P2 (signalée explicitement "à étudier après 1.0" par la
mission, mais son potentiel commercial élevé justifie qu'elle reste au-
dessus de P3 dans le classement, sans pour autant devenir un chantier
avant 1.0).
**Statut** : à étudier après 1.0.

---

*Explicitement classées ailleurs, mentionnées ici pour référence croisée :
**Print Intelligence**, **Photo Intelligence**, **Light/Filament
Calibration** → P1, documentées dans `docs/01_ROADMAP.md` (phases 0.5/0.6).
**LithoShape AI** (langage naturel → intention structurée → moteurs
déterministes) → P2, documentée séparément car elle touche l'architecture
globale, pas un module isolé — voir le compte-rendu de mission pour l'avis
de Claude sur cette piste spécifiquement.*
