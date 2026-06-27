# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


root = Path(SPECPATH)

a = Analysis(
    ["GifText.py"],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "icon.png"), ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(root / "runtime_hook_mp.py")],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GifText",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(root / "icon.ico"),
)
