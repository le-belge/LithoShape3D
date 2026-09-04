# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec pour LithoShape3D (Windows, dossier d'application
distribuable). Non teste sur une vraie machine Windows dans cette session
(voir le rapport de livraison) -- ecrit par symetrie avec le spec macOS
valide (lithoshape3d.spec), qui utilise exactement le meme point d'entree
et la meme strategie de collecte de dependances (PyVista/VTK/trimesh).

Build (depuis une machine Windows, venv actif avec l'extra app installe,
PyInstaller installe) :
    pyinstaller packaging\\lithoshape3d_windows.spec --noconfirm

Le backend SAM2 CoreML est exclu explicitement : il est deja gate par
`sys.platform == "darwin"` cote code (voir
ai/segmentation/sam2_coreml_backend.py), mais on evite aussi de tirer
`coremltools` dans le bundle Windows (dependance inutile ici -- app-full
n'est de toute facon pas l'extra recommande sous Windows, `app` suffit).
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

hidden_imports = (
    collect_submodules("pyvista")
    + collect_submodules("pyvistaqt")
    + collect_submodules("vtkmodules")
    + collect_submodules("trimesh")
    + collect_submodules("rembg")
    + collect_submodules("onnxruntime")
)

datas = (
    collect_data_files("pyvista")
    + collect_data_files("vtkmodules")
    # Gabarits geometriques non-.py du package (ex. lithophane_helper_100mm.stl
    # pour les stabilisateurs lateraux, core/geometry/assets/) -- doivent
    # etre embarques dans le bundle, sinon build_side_stabilizer_pair echoue
    # a l'execution dans l'app packagee.
    + collect_data_files("lithoshape3d")
)

a = Analysis(
    ["../src/lithoshape3d/cli.py"],
    pathex=["../src"],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    excludes=["coremltools"],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LithoShape3D",
    icon="icons/lithoshape3d.ico",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="LithoShape3D",
)
