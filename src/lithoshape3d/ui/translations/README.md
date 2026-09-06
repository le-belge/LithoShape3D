# Traductions

Le français est la langue source, écrite directement dans le code
(`self.tr("...")`, voir `ui/main_window.py`, `ui/about_dialog.py`,
`ui/license_dialog.py`).

Après avoir modifié ou ajouté un texte traduisible dans ces fichiers,
régénérer les traductions :

```bash
scripts/update_translations.sh
```

Ça relance `pyside6-lupdate` (fusionne les nouveaux textes dans
`lithoshape3d_en.ts` sans perdre les traductions déjà faites -- les
nouveaux textes apparaissent avec `type="unfinished"`), puis rappelle de
les traduire à la main dans le `.ts` (XML lisible, balises
`<source>`/`<translation>`) avant de recompiler en `.qm` avec
`pyside6-lrelease`.

**Couverture actuelle** : les dialogues et menus les plus visibles
(fenêtre principale, "À propos", licence). Les dialogues plus profonds
(cadrage, éditeur de masque, LightBox) ne sont pas encore couverts --
ils restent en français même en mode "English".
