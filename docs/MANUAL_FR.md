# Manuel LithoShape3D (v0.5.0)

Guide complet des fonctionnalités, expliqué simplement. Version anglaise :
[`MANUAL_EN.md`](MANUAL_EN.md).

## Vue d'ensemble

LithoShape3D prend une image, calcule une épaisseur variable selon la
luminosité de chaque pixel, et en sort un fichier prêt à imprimer en 3D —
la lithophanie qui révèle l'image quand on la rétro-éclaire. Le logiciel
gère aussi les formes non rectangulaires, plusieurs zones combinées sur une
même pièce, les inserts colorés rétro-éclairés, et l'export multi-matériaux
pour une imprimante avec AMS.

## 1. Image source

Tout part d'une photo. Plus un endroit est sombre, plus la matière y sera
épaisse une fois imprimée.

- **Ouvrir image...** — charge une photo (JPG, PNG...).
- **Retirer le fond...** — détoure automatiquement le sujet en un clic.
- **Retirer le fond (précision manuelle)...** *(macOS)* — détourage assisté
  par IA où l'on clique soi-même sur le sujet à garder ou exclure.
- **Cadrer la photo...** — recadre/zoome la photo dans la forme choisie,
  sans toucher au fichier original.
- **Luminosité / Contraste / Inverser** — ajuste le rendu avant génération.
  *Inverser* échange les zones claires et sombres.

> **Astuce** : une photo assez contrastée, avec un sujet net, donne toujours
> un meilleur relief qu'une image plate ou surexposée.

## 2. Formes (Shape Composer)

La pièce n'est pas obligée d'être un rectangle :

- **Rectangle / Cercle / Ovale** — formes de base.
- **Cœur / Étoile** — formes décoratives prêtes à l'emploi.
- **Texte** — la pièce prend la silhouette d'un mot ou d'un court texte,
  déplaçable avec les flèches du clavier.
- **Image / SVG** — utilise un logo ou une silhouette personnalisée comme
  contour de la pièce.
- **Bordure** — réglage d'épaisseur pour ajouter un cadre autour de la forme.

## 3. Zones & masques

Une pièce peut combiner plusieurs zones indépendantes, chacune avec sa
propre portion d'image, son rôle et éventuellement sa couleur.

- **+ Zone / Supprimer** — une zone "Lithophanie" de base est toujours
  créée automatiquement à l'ouverture d'une image.
- **Éditer le masque...** — peint au pinceau/gomme, avec remplir, effacer,
  inverser et un historique annuler/rétablir.
- **Segmentation IA** *(macOS)* — un clic sur le sujet génère
  automatiquement un masque précis.
- **Réordonner les zones** — glisser-déposer dans la liste change l'ordre
  de composition, utile quand deux zones se chevauchent.

## 4. Géométrie & relief

- **Largeur / Épaisseur min & max** — dimensions réelles en millimètres. La
  hauteur suit automatiquement le ratio de la photo.
- **Résolution** — finesse du détail (mm par pixel).
- **Presets Standard / Fin / Brouillon** — réglages prêts à l'emploi.
- **Rôle de la zone** — `ReliefMode` (Lithophanie / Relief-amplitude /
  Solide) et `CompositionMode` (Base / Ajouter / Remplacer).

## 5. Matériaux & couleurs

Donner une couleur à une zone ne change jamais son relief — les deux sont
volontairement indépendants.

- **Matériau seul** — même relief, filament différent (utile pour l'AMS).
- **Insert rétro-éclairé (Backlight Insert)** *(prototype)* — cavité
  derrière une fine peau blanche, remplie d'un insert de couleur. Réglages :
  épaisseur de peau, épaisseur d'insert, jeu XY.

> **Encore expérimental** : le Backlight Insert fonctionne dans le logiciel
> mais n'a pas encore été validé sur toutes les imprimantes.

## 6. Support d'impression

- **Aucun** — export à plat, pour un cadre ou une lightbox.
- **Pied plat / renforcé** — socle imprimé avec la pièce (nervures en plus
  pour la version renforcée).

## 7. Aperçu 3D

- **Générer** — calcule le mesh 3D ; marqué "périmé" si un réglage change
  ensuite.
- **Zone active / Composition** — zone sélectionnée seule, ou pièce finale
  toutes zones combinées.
- **Backlight couleur** — simule le rendu rétro-éclairé, inserts en vraie
  couleur.
- **Vues Face / Isométrique / Reset** — navigation caméra classique.

## 8. Export

- **Exporter STL...** — un seul fichier, pour une pièce à un seul
  matériau/couleur.
- **Exporter multi-matériaux...** — fichier 3MF (ou plusieurs STL en repli)
  pour une pièce multi-couleurs/inserts.

## 9. Thèmes

Menu **Thème** — le choix est mémorisé au prochain lancement.

- **Sombre — Carbon Glow** (par défaut)
- **Clair — Litho Lab**

## 10. Licence

Import, cadrage, zones et aperçu 3D sont utilisables librement. L'export
d'un fichier imprimable (STL/3MF) nécessite une licence — menu
**Aide → Licence...** pour saisir la clé reçue à l'achat.

## Glossaire

| Terme | Définition |
|---|---|
| Lithophanie | Relief fin qui révèle une image quand on l'éclaire par-derrière. |
| Masque | Zone peinte définissant quelle partie de l'image appartient à une zone donnée. |
| Mesh | Le modèle 3D calculé, avant export. |
| Backlight Insert | Insert coloré caché derrière une fine peau blanche, pour un rétro-éclairage en couleur. |
| Jeu XY | Petit espace laissé entre deux pièces pour qu'elles s'emboîtent sans forcer. |
| AMS | Système multi-filaments Bambu Lab, impression multi-couleurs en un seul passage. |
