# Business

*Aucune hypothèse financière ci-dessous ne doit être lue comme une
certitude. Ce document capture le positionnement et le modèle envisagés,
et liste explicitement ce qui reste à trancher.*

## Positionnement actuel

Outil de création de lithophanies et objets photo 3D personnalisés, plus
accessible qu'un workflow CAO traditionnel (Blender/Fusion 360) pour ce
cas d'usage précis.

## Cible initiale

Utilisateurs d'imprimantes 3D capables de slicer et imprimer, mais ne
voulant pas apprendre Blender/Fusion 360 uniquement pour fabriquer leurs
objets personnalisés.

## Modèle envisagé

- **LithoShape Free** — découverte / fonctions simples.
- **LithoShape Pro** — logiciel complet.
- **LithoShape AI** — éventuelle option cloud payante future (voir
  `docs/02_IDEA_PARKING.md`, section LithoShape AI, et le compte-rendu de
  mission pour l'avis de Claude sur ce point précis).

Licence commerciale : à définir selon droits d'exploitation.

## Objectif initial

100 premiers clients payants qui ne connaissent pas personnellement les
créateurs du projet — un objectif délibérément choisi pour forcer une
vraie validation marché plutôt qu'un cercle de complaisance.

## Sujets business restant à résoudre (liste, pas un plan)

- Pricing (montant, structure — abonnement vs licence perpétuelle vs
  freemium).
- TVA / fiscalité selon pays de vente.
- Merchant of Record éventuel (Paddle, Stripe, LemonSqueezy...).
- Moyen de paiement.
- Mécanisme de licence (clé, compte, activation machine...).
- Protection anti-piratage raisonnable — **"raisonnable" mérite d'être
  défini explicitement** : le principe 12 de la Product Bible ("une
  fonctionnalité doit être testable") s'applique mal à un DRM par
  construction ; à trancher tôt pour éviter un chantier disproportionné
  plus tard.
- Support utilisateur (canal, langue(s), SLA implicite).
- Coût IA (le téléchargement/l'inférence SAM2 sont locaux et gratuits
  aujourd'hui — un futur backend cloud, si "LithoShape AI" avance,
  introduirait un coût variable réel à modéliser).
- Site web / présence commerciale.
- Marketing.
- Traductions (au minimum FR/EN, voir Product Bible principe 15 — aucune
  infrastructure technique n'existe encore, voir CURRENT_STATE.md).
- Analytics, si mis en place : **opt-in explicite**, cohérent avec
  l'absence actuelle de toute télémétrie dans le code.
- Crash reporting, si mis en place : **opt-in explicite**, même remarque.

## Ce que l'audit technique apporte à ces questions business

- Le logiciel étant 100% local aujourd'hui (aucun serveur, aucun compte,
  aucune télémétrie), le positionnement "respectueux de la vie privée par
  défaut" est un fait technique vérifiable dès maintenant, pas une
  promesse marketing à construire — argument commercial disponible
  immédiatement sans développement supplémentaire.
- Le format de projet `.l3dproj` étant un dossier portable et le format
  d'export STL/3MF étant standard (pas de format propriétaire), il n'y a
  aujourd'hui **aucun verrou technique retenant l'utilisateur** — cohérent
  avec le principe "formats standards privilégiés", mais à assumer
  consciemment dans la stratégie de rétention/pricing (le modèle payant ne
  peut pas reposer sur "vos fichiers sont piégés chez nous").
