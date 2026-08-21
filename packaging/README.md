# Packaging LithoShape3D

## macOS (verifie dans cette session)

```bash
source .venv/bin/activate
pip install -e ".[app-full]"
pip install pyinstaller
./packaging/build_macos.sh
```

Produit `packaging/dist/LithoShape3D.app` (~940 Mo, non signe/notarise).
Testé dans cette session : construction réussie, lancement réel confirmé
(process actif + log applicatif écrit dans
`~/Library/Logs/LithoShape3D/lithoshape3d.log`).

Non signee/notariee : au premier lancement, clic droit sur l'app -> Ouvrir
(Gatekeeper bloque sinon un `.app` non identifie).

## Windows (spec écrit, non testé sur machine réelle)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[app]"
pip install pyinstaller
pyinstaller packaging\lithoshape3d_windows.spec --noconfirm
```

Produit `packaging\dist\LithoShape3D\` (dossier distribuable, `LithoShape3D.exe`
a la racine).

Toutes les dependances (`pyside6`, `pyvista`, `pyvistaqt`, `manifold3d`,
`opencv-python-headless`, `trimesh`, `scipy`, `lxml`, `networkx`, `numpy`,
`pillow`) ont ete verifiees disponibles en wheel binaire Windows/Python 3.12
(`win_amd64`) via PyPI dans cette session -- mais la construction/le
lancement reel n'ont pas pu etre executes faute de machine Windows
disponible ici. Le spec suit exactement la meme strategie que le spec macOS
deja valide (meme point d'entree, meme collecte de sous-modules
PyVista/VTK/trimesh).
