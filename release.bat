@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Release CadastroAuto

rem ============================================================
rem  release.bat [VERSÃO]
rem
rem  Fluxo completo da release:
rem    1. Builda o exe (PyInstaller) + copia o Chromium embutido
rem    2. Compila o instalador (Inno Setup) a partir de caminho
rem       CURTO (o caminho do OneDrive é longo demais pro ISCC)
rem    3. Commita, cria a tag vVERSÃO e publica a Release no GitHub
rem
rem  Exemplo:
rem    release.bat 1.1.0
rem ============================================================

cd /d "%~dp0"

rem ------------------------------------------------------------
rem 0. Validações
rem ------------------------------------------------------------
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC goto :missing_iscc

where gh >nul 2>nul
if errorlevel 1 goto :missing_gh
gh auth status >nul 2>nul
if errorlevel 1 goto :missing_gh_auth

set "VER=%~1"
if not defined VER (
    for /f "usebackq delims=" %%v in (`findstr /r "#define MyAppVersion" cadastroauto.iss`) do set "VERLINE=%%v"
    for /f "tokens=3 delims= " %%v in ("!VERLINE!") do set "VER=%%~v"
    if not defined VER set "VER=1.2.0"
)
echo === Release CadastroAuto v%VER% ===
echo.

rem ------------------------------------------------------------
rem 1. Garante dependencias
rem ------------------------------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo [ERRO] Python nao encontrado. Instale o Python 3.10+ primeiro.
    pause & exit /b 1
)

rem ------------------------------------------------------------
rem 2. Build do exe + Chromium (mesma logica do build.bat)
rem ------------------------------------------------------------
if exist dist\ rmdir /s /q dist
if exist build\ rmdir /s /q build
echo Gerando o executavel (demora alguns minutos)...
%PY% -m PyInstaller cadastroauto.spec -y --clean
if errorlevel 1 goto :build_failed

echo.
echo Descobrindo a revisao do Chromium esperada...
for /f "usebackq delims=" %%i in (`%PY% -c "import json,pathlib,playwright; p=pathlib.Path(playwright.__file__).parent/'driver'/'package'/'browsers.json'; b=json.loads(p.read_text())['browsers']; print([x['revision'] for x in b if x['name']=='chromium'][0])"`) do set "REV=%%i"
if not defined REV goto :revision_failed
echo Revisao esperada: %REV%

set "PW_BASE=%LOCALAPPDATA%\ms-playwright"
if defined PLAYWRIGHT_BROWSERS_PATH set "PW_BASE=%PLAYWRIGHT_BROWSERS_PATH%"

if not exist "%PW_BASE%\chromium-%REV%" goto :chromium_missing
echo Copiando chromium-%REV% (aguarde)...
xcopy "%PW_BASE%\chromium-%REV%" "dist\cadastroauto\chromium-%REV%\" /e /i /q /y >nul
if errorlevel 1 goto :chromium_copy_failed
if not exist "%PW_BASE%\chromium_headless_shell-%REV%" goto :skip_headless
echo Copiando chromium_headless_shell-%REV% (aguarde)...
xcopy "%PW_BASE%\chromium_headless_shell-%REV%" "dist\cadastroauto\chromium_headless_shell-%REV%\" /e /i /q /y >nul
:skip_headless
echo Chromium OK.

rem ------------------------------------------------------------
rem 3. Instalador via caminho curto (OneDrive = caminho longo demais)
rem ------------------------------------------------------------
set "SHORT=%TEMP%\cadauto_release"
if exist "%SHORT%" rmdir /s /q "%SHORT%"
mkdir "%SHORT%"

echo.
echo Copiando app para caminho curto (pode demorar ~1 GB)...
xcopy "dist\cadastroauto" "%SHORT%\cadastroauto" /e /i /q /y >nul
if errorlevel 1 goto :short_copy_failed

rem Gera o .iss com o caminho curto
(
    echo ; Instalador do CadastroAuto - gerado pelo release.bat - NAO editar
    echo #define MyAppName "Cadastro Auto"
    echo #define MyAppVersion "%VER%"
    echo #define MyAppPublisher "Starke Parts"
    echo #define MyAppExeName "cadastroauto.exe"
    echo #define SrcDir "%SHORT%\cadastroauto"
    echo.
    echo [Setup]
    echo AppId={{6A3C9E1F-4B15-4C7E-9D2A-4F8B1C2D3E4F}
    echo AppName={#MyAppName}
    echo AppVersion={#MyAppVersion}
    echo AppPublisher={#MyAppPublisher}
    echo DefaultDirName={localappdata}\Programs\CadastroAuto
    echo DefaultGroupName=Cadastro Auto
    echo DisableProgramGroupPage=yes
    echo PrivilegesRequired=lowest
    echo OutputDir={#SrcDir}\..\installer
    echo OutputBaseFilename=CadastroAuto-Setup
    echo Compression=lzma2/ultra64
    echo SolidCompression=yes
    echo InternalCompressLevel=ultra64
    echo WizardStyle=modern
    echo CloseApplications=yes
    echo RestartApplications=no
    echo.
    echo [Languages]
    echo Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"
    echo.
    echo [Tasks]
    echo Name: "desktopicon"; Description: "Criar atalho na Area de Trabalho"; GroupDescription: "Atalhos:"
    echo.
    echo [Files]
    echo Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
    echo.
    echo [Icons]
    echo Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
    echo Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
    echo Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
    echo.
    echo [Run]
    echo Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: nowait postinstall skipifsilent
    echo.
    echo [UninstallDelete]
    echo Type: filesandordirs; Name: "{app}\data"
) > "%SHORT%\cadastroauto_setup.iss"

echo Compilando instalador (pode demorar 5-10 minutos)...
"%ISCC%" "%SHORT%\cadastroauto_setup.iss"
if errorlevel 1 goto :installer_failed

mkdir "dist\installer" 2>nul
copy /y "%SHORT%\installer\CadastroAuto-Setup.exe" "dist\installer\CadastroAuto-Setup.exe" >nul
if errorlevel 1 goto :installer_copy_failed

echo.
echo Instalador OK: dist\installer\CadastroAuto-Setup.exe

rem ------------------------------------------------------------
rem 4. GitHub: commit + tag + release
rem ------------------------------------------------------------
echo.
echo Verificando mudancas pendentes...
git add -A
git commit -m "release v%VER%" >nul 2>nul
if errorlevel 1 echo (nada novo para commitar)

echo.
echo Criando a tag v%VER%...
git tag -a "v%VER%" -m "CadastroAuto v%VER%" 2>nul
git push origin master
git push origin "v%VER%"

echo.
echo Publicando a Release...
gh release create "v%VER%" "dist/installer/CadastroAuto-Setup.exe" --title "CadastroAuto %VER%" --notes "Instalador do CadastroAuto %VER% (Windows, per-usuario, sem admin)."

if errorlevel 1 (
    echo [ERRO] Falha ao publicar a Release no GitHub.
    pause & exit /b 1
)

echo.
echo ============================================
echo  RELEASE v%VER% PUBLICADA!
echo  Veja em: https://github.com/Brakister/autobot/releases
echo ============================================
pause
exit /b 0

:missing_iscc
echo [ERRO] Inno Setup 6 nao encontrado. Instale de https://jrsoftware.org/isdl.php
exit /b 1

:missing_gh
echo [ERRO] gh (GitHub CLI) nao encontrado. Instale de https://cli.github.com/
exit /b 1

:missing_gh_auth
echo [ERRO] gh nao autenticado. Rode: gh auth login
exit /b 1

:build_failed
echo [ERRO] Falha no PyInstaller.
exit /b 1

:revision_failed
echo [ERRO] Nao consegui detectar a revisao do Chromium.
exit /b 1

:chromium_missing
echo [ERRO] Chromium revisao %REV% nao encontrado em %PW_BASE%.
echo        Rode: playwright install chromium
exit /b 1

:chromium_copy_failed
echo [ERRO] Falha ao copiar chromium-%REV%.
exit /b 1

:short_copy_failed
echo [ERRO] Falha ao copiar para o caminho curto.
exit /b 1

:installer_failed
echo [ERRO] Falha no Inno Setup.
exit /b 1

:installer_copy_failed
echo [ERRO] Falha ao copiar o instalador para dist\installer.
exit /b 1