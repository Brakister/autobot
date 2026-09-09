# -*- mode: python ; coding: utf-8 -*-
"""Spec do PyInstaller para gerar cadastroauto.exe (onefile, windowed).

Gerar o exe:
    pyinstaller cadastroauto.spec

Requisitos: instalar pyinstaller e gerar os assets do navegador separados.
IMPORTANTE: o Playwright baixa navegadores em cache fora do executável.
Para embutir, o navegador precisa ser baixado e apontado via PLAYWRIGHT_BROWSERS_PATH.
"""
import os

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'playwright.sync_api',
        'playwright.driver',
        'openpyxl',
        'openpyxl.cell._writer',
        'openpyxl.styles',
        'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='cadastroauto',
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
)
