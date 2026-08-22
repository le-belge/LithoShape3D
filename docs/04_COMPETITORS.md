# Concurrents identifiés

**Aucune recherche web n'a été menée pour produire ce document** (hors
scope explicite de cette mission). Contenu = ce qui était déjà connu au
moment de la mission, complété par la connaissance générale de Claude
(entraînement, pas de vérification en ligne à cette date). Toute
information non vérifiée directement dans ce dépôt ou communiquée avec
certitude par l'utilisateur est marquée **TO_VERIFY** — ne pas la traiter
comme un fait établi avant vérification.

Axes à surveiller pour chaque concurrent : formes, couleur, 3MF, AMS,
calibration filament, preview, supports, IA, UX, prix, licence,
plateformes, export, workflow.

---

## ItsLitho

**Ce qui est raisonnablement connu** : outil web (navigateur) de
génération de lithophanies à partir d'une photo, gratuit, orienté
simplicité — proche du cœur historique de LithoShape3D (image →
lithophanie → export imprimable).

**TO_VERIFY** : support multi-zones/multi-matériaux, formes non
rectangulaires, export 3MF, intégration slicer, modèle économique exact,
roadmap.

**Axe de comparaison le plus pertinent avec LithoShape3D** : ItsLitho
étant web, il n'a probablement pas d'intégration profonde avec un viewer
3D natif ni de gestion de projet locale versionnée (`.l3dproj`) — mais
ceci est TO_VERIFY, pas confirmé.

---

## HueForge

**Ce qui est raisonnablement connu** : outil orienté "peinture par
filament" (multi-color single-extruder, transmission lumineuse des
filaments pour recréer une image en couches de hauteur variable) —
proche conceptuellement de Backlight Insert et du futur Light/Filament
Calibration (voir roadmap 0.6), mais sur un principe différent (couches
superposées d'épaisseur variable dans le sens de l'impression, pas un
insert physique séparé).

**TO_VERIFY** : fonctionnement exact, formats supportés, prix, courbe
d'apprentissage, degré de calibration filament proposé.

**Axe de comparaison le plus pertinent** : si HueForge fait déjà bien la
calibration filament/transmission lumineuse, c'est directement le
concurrent le plus proche du futur "Light/Filament Calibration" de
LithoShape3D (roadmap 0.6) — **à étudier sérieusement avant de construire
cette phase**, pas après.

---

## LithoForge

**TO_VERIFY intégralement** — nom connu, fonctionnalités et positionnement
non vérifiés dans cette mission. Ne pas supposer de recoupement avec
HueForge au-delà de la similarité de nom.

---

## PlainMesh

**TO_VERIFY intégralement** — nom connu, fonctionnalités et positionnement
non vérifiés dans cette mission.

---

## Concurrents génériques à ne pas oublier (contexte, pas une liste fermée)

Les logiciels CAO généralistes (Blender, Fusion 360) ne sont pas des
concurrents directs mais définissent le point de comparaison implicite du
North Star ("sans logiciel de CAO") — toute communication produit devrait
se positionner par rapport à eux sans prétendre les remplacer (cohérent
avec "Ce que LithoShape3D n'est pas pour la 1.0", Product Bible).

## Recommandation pour la prochaine itération de ce document

Une vraie recherche comparative (fonctionnalités, prix, plateformes,
retours utilisateurs) sur ces 4 noms — et la question de savoir s'il en
manque d'autres dans le même segment — est un travail légitime pour
ChatGPT (rôle "recherche" explicitement attribué dans la gouvernance de
cette mission), pas pour Claude Code dans cette session.
