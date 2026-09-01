# Packaging LithoShape3D

## macOS (re-verifie -- build a jour, theme clair inclus)

```bash
source .venv/bin/activate
pip install -e ".[app-full]"
pip install pyinstaller
./packaging/build_macos.sh
```

L'icone native est versionnee sous `packaging/icons/`. Apres une modification
du logo SVG, la regenerer une seule fois avec `python packaging/generate_icons.py`.

Produit `packaging/dist/LithoShape3D.app` (~940 Mo, non signe/notarise).
Reconstruit et relance reellement verifies (process actif, fenetre ouverte
via capture d'ecran, log applicatif ecrit dans
`~/Library/Logs/LithoShape3D/lithoshape3d.log`) avec le code le plus recent
(theme clair, corrections Cherry Moon). Demarrage a froid PyVista/VTK
observe a ~25-35s sur cette machine avant l'apparition de la fenetre --
normal pour un premier lancement post-build (pas de cache disque chaud),
pas un signe de blocage.

Non signee/notariee : au premier lancement, clic droit sur l'app -> Ouvrir
(Gatekeeper bloque sinon un `.app` non identifie).

## Windows (build + smoke test CLI verifies par CI a chaque push sur main)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[app]"
pip install pyinstaller
pyinstaller packaging\lithoshape3d_windows.spec --noconfirm
```

Produit `packaging\dist\LithoShape3D\` (dossier distribuable, `LithoShape3D.exe`
a la racine).

L'executable utilise `packaging/icons/lithoshape3d.ico`, genere depuis le meme
logo SVG que l'application macOS.

Aucune machine Windows physique disponible dans ces sessions, mais
`.github/workflows/windows-build.yml` construit et verifie REELLEMENT le
binaire sur un runner `windows-latest` a chaque push sur `main` :
1. build PyInstaller complet ;
2. smoke test CLI (`LithoShape3D.exe generate ...` -> STL genere et non
   vide) ;
3. artefact `LithoShape3D-windows` telechargeable depuis l'onglet Actions du
   run correspondant.

Historique des runs : `gh run list --workflow=windows-build.yml` (tous verts
au 29/08/2026). Le spec suit la meme strategie que le spec macOS deja
valide (meme point d'entree, meme collecte de sous-modules PyVista/VTK/
trimesh).

### Limite connue : pas de smoke test CI pour l'UI graphique

Tente dans cette session (voir historique des runs
`chore/packaging-verification`, deux essais, avec et sans
`QT_QPA_PLATFORM=offscreen`) : lancer l'exe sans argument (mode UI, voir
`cli.py:_cmd_launch_app`) crashe systematiquement sur le runner
`windows-latest` avec un acces memoire invalide (code `-1073741819` /
`0xC0000005`), car VTK n'y trouve NI un vrai GPU/pilote OpenGL (VM sans
carte graphique) NI de rendu logiciel de secours (`osmesa.dll`, absent de
l'image du runner). Ce n'est probablement PAS representatif d'un vrai
poste utilisateur (qui a toujours au moins un pilote graphique basique),
mais **ca revele un vrai defaut de robustesse independant de la CI** :
`ui/app.py:run_app()` n'entoure la creation de `MainWindow()` d'aucune
gestion d'erreur -- si l'initialisation OpenGL/VTK echoue reellement chez
un utilisateur (pilote graphique casse/absent, VM, Remote Desktop sans
acceleration), l'application plante durement au lieu d'afficher un
message d'erreur exploitable. Corrige pas dans cette session (pas
reproductible sans machine Windows/VTK reelle pour verifier un correctif
avec confiance) -- a traiter dans une session dediee avec acces a un
environnement de test adapte.
