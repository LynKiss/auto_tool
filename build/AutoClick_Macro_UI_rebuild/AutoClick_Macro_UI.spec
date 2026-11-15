# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/Acer/Downloads/auto-20261115T103649Z-1-001/auto/auto_click_ui.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/Acer/Downloads/auto-20261115T103649Z-1-001/auto/macros', 'macros'), ('C:/Users/Acer/Downloads/auto-20261115T103649Z-1-001/auto/macro_settings.json', '.'), ('C:/Users/Acer/Downloads/auto-20261115T103649Z-1-001/auto/window_config.json', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AutoClick_Macro_UI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AutoClick_Macro_UI',
)
