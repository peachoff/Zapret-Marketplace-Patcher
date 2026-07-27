# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['../main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('../src/zmp/icon.ico', 'zmp'),
        ('../src/zmp/icon.png', 'zmp'),
        ('../src/zmp/fonts/*.ttf', 'zmp/fonts'),
    ],
    hiddenimports=[
        'customtkinter',
        'PIL',
        'PIL._tkinter_finder',
        'yaml',
        'requests',
        'packaging',
        'packaging.version',
        'packaging.requirements',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ZMP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
)
