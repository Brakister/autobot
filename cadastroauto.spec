# -*- mode: python ; coding: utf-8 -*-
r"""Spec do PyInstaller para gerar cadastroauto.exe (onedir, windowed).

Gerar o exe (inclui copiar o Chromium para junto do executável):
    build.bat

Ou manualmente:
    pyinstaller cadastroauto.spec
    xcopy "%LOCALAPPDATA%\ms-playwright\chromium-<rev>" "dist\cadastroauto\chromium-<rev>\" /e /i /y
    xcopy "%LOCALAPPDATA%\ms-playwright\chromium_headless_shell-<rev>" "dist\cadastroauto\chromium_headless_shell-<rev>\" /e /i /y

Importante: modo onedir, porque o onefile demora para extrair ~110 MB
enquanto abre e acaba parecendo travado. O Chromium é embutido ao lado do
exe e localizado via PLAYWRIGHT_BROWSERS_PATH (ver config.configurar_playwright).
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
    [],
    exclude_binaries=True,
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

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='cadastroauto',
)
