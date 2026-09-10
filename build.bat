@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Build CadastroAuto (com Chromium embutido)

echo ============================================
echo  Build do CadastroAuto
echo  Gera o exe + Chromium portatil
echo ============================================
echo.

cd /d "%~dp0"

rem ------------------------------------------------------------
rem 1. Descobre o Python
rem ------------------------------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo [ERRO] Python nao encontrado. Instale o Python 3.10+ primeiro.
    pause & exit /b 1
)
%PY% --version

rem ------------------------------------------------------------
rem 2. Garante as dependencias
rem ------------------------------------------------------------
echo.
echo Instalando dependencias de build...
%PY% -m pip install --upgrade pip >nul 2>nul
%PY% -m pip install pyinstaller >nul 2>nul
%PY% -c "import playwright" >nul 2>nul || (
    echo Instalando playwright...
    %PY% -m pip install -r requirements.txt
)
if errorlevel 1 pause & exit /b 1

rem ------------------------------------------------------------
rem 3. Roda o PyInstaller (onedir)
rem ------------------------------------------------------------
echo.
echo Gerando o executavel (demora alguns minutos)...
if exist dist\ rmdir /s /q dist
if exist build\ rmdir /s /q build
%PY% -m PyInstaller cadastroauto.spec -y --clean
if errorlevel 1 (
    echo [ERRO] Falha no PyInstaller.
    pause & exit /b 1
)

rem ------------------------------------------------------------
rem 4. Descobre a revisao do Chromium que o Playwright instalado espera
rem    (vem do browsers.json do driver, e o Playwright baixa a pasta
rem     chromium-<rev> e chromium_headless_shell-<rev>)
rem ------------------------------------------------------------
echo.
echo Descobrindo a revisao do navegador esperada...
for /f "usebackq delims=" %%i in (`%PY% -c "import json,pathlib,playwright; p=pathlib.Path(playwright.__file__).parent/'driver'/'package'/'browsers.json'; b=json.loads(p.read_text())['browsers']; print([x['revision'] for x in b if x['name']=='chromium'][0])"`) do set "REV=%%i"
if not defined REV (
    echo [ERRO] Nao consegui detectar a revisao do Chromium.
    echo        Rode:  playwright install chromium
    pause & exit /b 1
)
echo Revisao esperada: %REV%

rem ------------------------------------------------------------
rem 5. Copia o Chromium da revisao certa para junto do exe
rem ------------------------------------------------------------
set "PW_BASE=%LOCALAPPDATA%\ms-playwright"
if defined PLAYWRIGHT_BROWSERS_PATH set "PW_BASE=%PLAYWRIGHT_BROWSERS_PATH%"

if not exist "%PW_BASE%\chromium-%REV%" (
    echo [ERRO] Chromium revisao %REV% nao encontrado em %PW_BASE%.
    echo        Rode:  playwright install chromium
    pause & exit /b 1
)

echo Copiando chromium-%REV% (~400 MB, aguarde)...
xcopy "%PW_BASE%\chromium-%REV%" "dist\cadastroauto\chromium-%REV%\" /e /i /q /y >nul
if errorlevel 1 (
    echo [ERRO] Falha ao copiar chromium-%REV%.
    pause & exit /b 1
)

if exist "%PW_BASE%\chromium_headless_shell-%REV%" (
    echo Copiando chromium_headless_shell-%REV% (~270 MB, aguarde)...
    xcopy "%PW_BASE%\chromium_headless_shell-%REV%" "dist\cadastroauto\chromium_headless_shell-%REV%\" /e /i /q /y >nul
)
echo Chromium OK.

rem ------------------------------------------------------------
rem 6. Empacota tudo num ZIP
rem ------------------------------------------------------------
echo.
echo Criando o ZIP final (pode demorar alguns minutos)...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\cadastroauto\*' -DestinationPath 'dist\cadastroauto-portatil.zip' -Force"
if exist "dist\cadastroauto-portatil.zip" (
    echo.
    echo ============================================
    echo  PRONTO!
    echo    Pasta portatil: dist\cadastroauto\
    echo    ZIP final:       dist\cadastroauto-portatil.zip
    echo  Copie/descompacte em qualquer PC Windows.
    echo  NAO precisa instalar Python nem navegador.
    echo ============================================
) else (
    echo Build concluido, mas o ZIP falhou. Use a pasta dist\cadastroauto\.
)

endlocal
pause