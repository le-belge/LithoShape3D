# LithoLab x LithoShape3D — fonctions prévues

Document de cadrage produit.

Date : 29 août 2026  
Statut : proposition de roadmap fonctionnelle  
Objectif : connecter LithoShape3D au projet LithoLab sans transformer le
logiciel en outil de laboratoire complexe.

---

## 1. Vision

LithoShape3D ne doit pas seulement générer des lithophanies.

Il doit devenir l'outil qui aide l'utilisateur à :

- choisir une bonne image ;
- anticiper le rendu lumineux ;
- générer une lithophanie imprimable ;
- comprendre les réglages importants ;
- tester un filament ;
- réutiliser les résultats LithoLab ;
- produire une lightbox ou un support cohérent.

La direction produit :

> passer d'un générateur de lithophanie à un assistant de réussite
> lithophanie.

LithoLab sert de laboratoire public. LithoShape3D transforme les résultats
du laboratoire en fonctions concrètes pour les utilisateurs.

---

## 2. Principe de gouvernance

Toutes les fonctions ci-dessous doivent respecter les principes du Product
Bible :

- le workflow simple Image -> Objet imprimable reste prioritaire ;
- les fonctions avancées ne doivent pas compliquer le premier usage ;
- le coeur `core/` reste utilisable sans UI ;
- les fonctions doivent rester testables ;
- les mesures LithoLab doivent assister la génération, pas la rendre
  dépendante d'un matériel externe ;
- aucune connexion obligatoire au LithoMeter avant la 1.0.

Règle de protection :

> Une fonction LithoLab n'entre dans LithoShape3D que si elle améliore
> directement la réussite d'une impression ou la crédibilité du résultat.

---

## 3. Priorités proposées

### P0 — À intégrer dès que possible

Ces fonctions sont proches du coeur actuel et apportent une valeur immédiate.

#### Benchmark opacité LithoLab V1

Ajouter un preset de génération d'éprouvette :

- nom : LithoLab Opacity Coupon V1 ;
- 7 zones d'épaisseur : 0,6 / 0,8 / 1,0 / 1,5 / 2,0 / 2,5 / 3,0 mm ;
- zones planes ;
- labels optionnels ;
- export STL ;
- documentation d'impression.

But :

- permettre à la communauté d'imprimer le même coupon ;
- préparer les tests LithoLab ;
- créer un pont naturel entre chaîne YouTube, protocole et logiciel.

Ce qui n'est pas inclus en P0 :

- lecture de l'ESP32 ;
- base de données de mesures ;
- score automatique.

Statut d'implémentation :

- première brique headless : commande `opacity-coupon` ;
- sortie STL par défaut : `LithoLab_Opacity_Coupon_V1.stl` ;
- l'UI pourra ensuite exposer ce preset sans changer le moteur.

#### Rapport d'impression lithophanie

Ajouter une fiche exportable ou affichable résumant :

- dimensions ;
- épaisseur min/max ;
- orientation recommandée ;
- hauteur de couche conseillée ;
- buse ;
- filament estimé ;
- temps estimé si disponible ;
- avertissements de printability ;
- conseils slicer.

But :

- réduire les erreurs ;
- donner une sortie claire après génération ;
- préparer les tutoriels et supports LithoLab.

---

### P1 — À viser dans les phases 0.5 / 0.6

Ces fonctions renforcent la promesse produit sans changer de domaine.

#### Assistant photo

Analyser l'image source avant génération :

- contraste trop faible ;
- image trop sombre ;
- visage trop petit ;
- arrière-plan trop chargé ;
- détails trop fins ;
- zones qui risquent de disparaître ;
- recadrage conseillé ;
- inversion recommandée ou non.

Sortie attendue :

- alertes simples ;
- suggestions compréhensibles ;
- presets rapides.

Positionnement :

> éviter les impressions ratées avant de lancer plusieurs heures de print.

#### Preview rétroéclairé amélioré

Afficher un rendu plus proche de l'objet final :

- simulation lumière chaude/froide ;
- contraste perçu ;
- zones bouchées ;
- zones trop transparentes ;
- aperçu avant/après réglages ;
- comparaison de deux réglages.

Attention :

> le preview doit rester une aide visuelle, pas une promesse physique
> parfaite.

#### Auto-réglage lithophanie

Ajouter des presets intelligents :

- portrait doux ;
- contraste fort ;
- détails fins ;
- impression rapide ;
- lithophanie couleur ;
- test filament ;
- lightbox.

Chaque preset ajuste :

- épaisseur min/max ;
- contraste ;
- luminosité ;
- gamma ou courbe équivalente ;
- résolution ;
- orientation conseillée.

#### Print Intelligence

Étendre la validation existante pour détecter :

- zones trop fines ;
- détails non imprimables ;
- base instable ;
- dimensions hors plateau ;
- épaisseurs incohérentes ;
- risque de casse ;
- temps ou taille déraisonnable.

Cette fonction doit réutiliser `core/validation/printability.py`.

---

### P2 — Après stabilisation des bases

Ces fonctions sont stratégiques, mais demandent une architecture plus
prudente.

#### Profils filaments lithophanie

Créer une fiche filament dans le logiciel :

- marque ;
- matière ;
- couleur ;
- température ;
- épaisseur min/max conseillée ;
- LithoCurve ;
- commentaires LithoLab ;
- source des mesures ;
- date de mesure ;
- protocole utilisé.

Usage :

- choisir un filament ;
- appliquer des réglages de départ ;
- comparer deux filaments ;
- afficher les limites.

Important :

> un profil filament doit rester optionnel. LithoShape3D doit toujours
> fonctionner sans base de données de filaments.

#### Import CSV LithoMeter

Importer les mesures produites par le LithoMeter ESP32 :

- CSV ;
- association à un filament ;
- visualisation de la LithoCurve ;
- calcul transmission/opacité ;
- export d'une fiche résultat.

Ce qui reste hors scope :

- connexion série directe obligatoire ;
- cloud ;
- synchronisation automatique.

#### Comparateur de réglages

Comparer deux versions d'une même lithophanie :

- épaisseur min/max ;
- contraste ;
- gamma ;
- preview rétroéclairé ;
- zones modifiées ;
- impact sur les avertissements.

But :

- rendre les réglages compréhensibles ;
- aider les débutants à choisir.

#### Bibliothèque de presets

Créer des presets orientés usage :

- portrait ;
- mariage ;
- bébé ;
- animal ;
- paysage ;
- veilleuse ;
- lampe lune ;
- lightbox ;
- benchmark filament ;
- test machine.

---

### P3 — Parking stratégique

Fonctions intéressantes mais à ne pas laisser envahir la route vers 1.0.

#### Connexion directe au LithoMeter

Connexion USB/série au capteur ESP32 :

- lecture en direct ;
- calibration ;
- acquisition guidée ;
- export automatique ;
- génération de graphique.

Raison du report :

- très utile pour LithoLab ;
- moins utile pour l'utilisateur grand public ;
- ajoute du support matériel.

#### Base communautaire LithoLab

Base de données publique de mesures :

- filaments testés ;
- machines ;
- réglages ;
- scores ;
- photos ;
- commentaires.

Raison du report :

- implique modération, qualité des données, format stable ;
- peut vivre d'abord hors logiciel.

#### Simulation matière avancée

Simulation plus physique :

- diffusion lumineuse ;
- comportement spectral ;
- couleur LED ;
- couleur filament ;
- épaisseur réelle ;
- profil imprimante.

Raison du report :

- très séduisant ;
- difficile à rendre fiable ;
- risque de surpromesse.

#### Couleur avancée / AMS / CMYK

Fonctions possibles :

- prévisualisation lithophanie couleur ;
- profils AMS ;
- mapping CMYK ;
- comparaison HueForge ;
- recommandations de piles couleurs.

Raison du report :

- gros potentiel vidéo et commercial ;
- nécessite des tests physiques sérieux.

---

## 4. Roadmap fonctionnelle proposée

### 0.5 — Réussite impression

Objectif :

> éviter les échecs évidents avant impression.

Fonctions :

- Print Intelligence ;
- rapport d'impression ;
- avertissements clairs ;
- recommandations slicer simples.

### 0.6 — Image et lumière

Objectif :

> aider l'utilisateur à obtenir une belle lithophanie, pas seulement un STL.

Fonctions :

- assistant photo ;
- preview rétroéclairé amélioré ;
- presets intelligents ;
- première notion de calibration filament manuelle.

### 0.6.x — Pont LithoLab

Objectif :

> produire les outils utiles aux tests LithoLab sans dépendance matérielle.

Fonctions :

- Benchmark opacité LithoLab V1 ;
- documentation protocole ;
- export de fiche d'impression ;
- préparation future des profils filaments.

### 0.7 — Produit commercialisable

Objectif :

> transformer le logiciel en produit distribuable.

Fonctions :

- Windows réel ;
- i18n FR/EN ;
- préférences ;
- onboarding ;
- crash reporting ;
- packaging robuste.

### Après 1.0

Objectif :

> exploiter les données LithoLab comme différenciation.

Fonctions candidates :

- profils filaments ;
- import CSV LithoMeter ;
- comparateur de réglages ;
- bibliothèque de presets ;
- couleur avancée ;
- base LithoLab.

---

## 5. Modèle de données futur

Ne pas implémenter maintenant, mais garder en tête.

### FilamentProfile

Champs possibles :

- id ;
- brand ;
- name ;
- material ;
- color_name ;
- color_code ;
- diameter_mm ;
- recommended_nozzle_temp_c ;
- recommended_bed_temp_c ;
- source ;
- notes.

### LithoCurve

Champs possibles :

- profile_id ;
- protocol_version ;
- coupon_version ;
- printer ;
- nozzle_mm ;
- layer_height_mm ;
- thickness_points_mm ;
- transmission_pct ;
- opacity_pct ;
- optical_density ;
- measured_at ;
- source_csv.

### PrintReport

Champs possibles :

- project_name ;
- generated_at ;
- dimensions ;
- min_thickness ;
- max_thickness ;
- resolution ;
- selected_preset ;
- warnings ;
- recommendations ;
- export_files.

---

## 6. Critères pour décider qu'une fonction entre en développement

Une fonction est candidate si elle répond oui à au moins trois questions :

- Est-ce qu'elle évite une impression ratée ?
- Est-ce qu'elle rend le résultat plus beau ?
- Est-ce qu'elle simplifie le workflow d'un débutant ?
- Est-ce qu'elle renforce la crédibilité LithoLab ?
- Est-ce qu'elle réutilise l'architecture existante ?
- Est-ce qu'elle peut être testée automatiquement ?
- Est-ce qu'elle peut être expliquée simplement en vidéo ?

Une fonction est reportée si elle répond oui à l'une de ces questions :

- Est-ce qu'elle oblige à maintenir du matériel ?
- Est-ce qu'elle demande un backend cloud ?
- Est-ce qu'elle complique le premier écran ?
- Est-ce qu'elle impose une refonte du moteur géométrique ?
- Est-ce qu'elle mélange trop vite produit logiciel et média YouTube ?

---

## 7. Décision de cadrage

Décision proposée :

> LithoShape3D doit intégrer d'abord les fonctions LithoLab qui génèrent ou
> expliquent mieux les objets imprimables. Les fonctions de mesure,
> connexion capteur et base de données restent progressives.

Ordre recommandé :

1. Rapport d'impression.
2. Benchmark opacité LithoLab V1.
3. Assistant photo.
4. Preview rétroéclairé amélioré.
5. Profils filaments manuels.
6. Import CSV LithoMeter.
7. Connexion directe au LithoMeter seulement si la demande est prouvée.
