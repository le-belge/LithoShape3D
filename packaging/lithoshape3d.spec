# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec pour LithoShape3D (macOS .app).

Build : `pyinstaller packaging/lithoshape3d.spec --noconfirm` depuis la
racine du depot (avec le venv actif -- app-full recommande).
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

hidden_imports = (
    collect_submodules("pyvista")
    + collect_submodules("pyvistaqt")
    + collect_submodules("vtkmodules")
    + collect_submodules("trimesh")
)

datas = collect_data_files("pyvista") + collect_data_files("vtkmodules")

a = Analysis(
    ["../src/lithoshape3d/cli.py"],
    pathex=["../src"],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
app = BUNDLE(
    coll,
    name="LithoShape3D.app",
    icon=None,
    bundle_identifier="com.lithoshape3d.app",
    info_plist={
        "CFBundleShortVersionString": "0.3.0",
        "NSHighResolutionCapable": True,
    },
)
