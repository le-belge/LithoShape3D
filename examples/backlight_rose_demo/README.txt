LithoShape3D 0.4.1 -- Prototype "Backlight Insert" (rose)
============================================================

Scenario : photo d'une femme tenant une rose (examples/demo_woman_rose_0_3.png,
480x640 px). Rose selectionnee via SAM2 (backend mock deterministe dans ce
script de demo -- le vrai SAM2 CoreML fonctionne de la meme facon depuis
l'interface). Materiau "Rose" assigne, strategie couleur "Insert
retro-eclaire". Reste de la lithophanie : materiau "Blanc".

Ce que ca demontre
-------------------
- lithophane_white.stl : la facade reste HOMOGENE (aucune bosse a
  l'emplacement de la rose) -- voir screenshot_front.png.
- rose_backlight_insert.stl : un disque rose INDEPENDANT, plat, qui se loge
  dans la cavite creusee au dos du corps blanc, exactement sous la rose --
  voir screenshot_back.png (rose bien visible depuis l'arriere).
- Les deux corps restent dans le MEME repere XYZ (voir backlight_rose_demo.3mf) :
  aucun repositionnement manuel necessaire dans le slicer.

Parametres exacts
-------------------
Modele
  Dimensions panneau (largeur x hauteur)      : 100.0 x 133.3 mm
  Resolution de generation                    : 0.5 mm/px (grille ~200x267)
  Epaisseur min / max (lithophanie)           : 0.8 / 3.0 mm (defauts)
  Epaisseur reelle mesuree du corps blanc     : 0.0 -- 2.65 mm (+ pied)

Backlight Insert (zone "Rose")
  Epaisseur peau blanche (white_skin_thickness_mm) : 0.40 mm (EXPERIMENTAL)
  Epaisseur insert (insert_thickness_mm)           : 0.60 mm (EXPERIMENTAL)
  Jeu XY (xy_clearance_mm)                         : 0.20 mm -- preset "Standard" (EXPERIMENTAL)
  Empreinte insert (mesure)                        : ~16.1 x 16.0 mm, epaisseur 0.60 mm

Pied d'impression
  Type       : Pied plat (SupportType.FLAT)
  Hauteur    : 8.0 mm
  Profondeur : 25.0 mm (defaut)
  Debords    : 5.0 mm de chaque cote (defauts)

Materiaux (indicatif -- assignation reelle du filament a faire dans le slicer)
  Blanc : PLA blanc (ou autre filament opaque clair)
  Rose  : PLA/PETG rose ou rouge translucide -- PAS teste physiquement dans
          cette session, c'est precisement ce que ce prototype sert a valider.

IMPORTANT -- valeurs experimentales
-------------------------------------
Les epaisseurs peau/insert et le jeu XY ci-dessus sont des valeurs de DEPART
raisonnables, pas des constantes physiquement optimales. Le rendu retro-
eclaire final depend du filament blanc, du filament colore, de leur
transmission lumineuse respective, de la source LED (puissance, distance,
temperature de couleur) -- autant de parametres qu'un futur moteur de
calibration filament devra traiter. Cette version livre la GEOMETRIE
correcte et un prototype imprimable, pas une prediction optique.

Fichiers de ce dossier
-------------------------
lithophane_white.stl        Corps principal blanc (avec cavite), watertight
rose_backlight_insert.stl   Insert plat independant, watertight
support_foot.stl            Pied d'impression (corps distinct, meme filament que le blanc)
backlight_rose_demo.3mf     Les 3 corps ci-dessus, dans leur position d'assemblage reelle
screenshot_front.png        Vue avant (mode Materiaux) -- facade homogene, aucune bosse
screenshot_back.png         Vue arriere (mode Materiaux) -- insert rose bien visible

backlight_skin_calibration.stl   BONUS (section 15 de la mission) : bande de
  120 x 30 mm, 4 zones identiques (meme insert de 0.60mm derriere chacune),
  seule l'epaisseur de peau blanche change : 0.30 / 0.40 / 0.50 / 0.60 mm de
  gauche a droite. A imprimer une fois et comparer devant une LED pour
  choisir l'epaisseur de peau qui donne le meilleur compromis
  facade-opaque/retro-eclairage-visible. screenshot_calibration_piece.png
  montre la geometrie (4 cavites de meme profondeur relative, meme insert).

Comment imprimer/tester
--------------------------
1. Importer backlight_rose_demo.3mf dans Bambu Studio/OrcaSlicer/PrusaSlicer.
2. Verifier que les 3 corps apparaissent deja alignes (pas de repositionnement
   manuel necessaire).
3. Assigner un filament blanc au corps "Blanc" (et au corps "Support"), un
   filament rose/rouge translucide au corps "Rose".
4. Imprimer.
5. Placer une source LED derriere le panneau une fois imprime : la facade doit
   rester homogene lithophanie-blanche eteinte, et la rose doit apparaitre
   coloree une fois retro-eclairee.

Genere par LithoShape3D 0.4.1 -- projet source complet dans
examples/demo_0_4_1_backlight_rose.l3dproj (reouvrable directement dans
l'application).
