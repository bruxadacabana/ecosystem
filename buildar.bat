@echo off
REM Compila os apps do ecossistema que precisam de build.
REM
REM Uso:
REM   buildar.bat              — builda AETHER, HUB e OGMA
REM   buildar.bat hub          — builda só o HUB
REM   buildar.bat aether hub   — builda AETHER e HUB
REM   buildar.bat ogma         — builda só o OGMA
REM
REM Apps Python (KOSMOS, Mnemosyne, Hermes, AKASHA) rodam do source — sem build.
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set ERROS=0
set BUILDS=

REM ── Determina targets ─────────────────────────────────────────────────────
if "%~1"=="" (
    set "TARGETS=aether hub ogma"
) else (
    set "TARGETS=%*"
)

echo.
echo ============================================
echo    ECOSSISTEMA -- Build de producao
echo ============================================
echo    Targets: %TARGETS%
echo.

REM ── AETHER ──────────────────────────────────────────────────────────────────
echo %TARGETS% | findstr /i "aether" >nul
if %errorlevel%==0 (
    echo [AETHER] cargo tauri build
    cd /d "%ROOT%\AETHER"
    cargo tauri build
    if !errorlevel! neq 0 (
        echo   ERRO: AETHER -- cargo tauri build falhou
        set /a ERROS+=1
    ) else (
        echo   OK: AETHER
        echo   .msi: %ROOT%\AETHER\src-tauri\target\release\bundle\msi\
        echo   .exe: %ROOT%\AETHER\src-tauri\target\release\bundle\nsis\
        set "BUILDS=%BUILDS% AETHER"
    )
    echo.
)

REM ── HUB ─────────────────────────────────────────────────────────────────────
echo %TARGETS% | findstr /i "hub" >nul
if %errorlevel%==0 (
    echo [HUB] cargo tauri build
    cd /d "%ROOT%\HUB"
    cargo tauri build
    if !errorlevel! neq 0 (
        echo   ERRO: HUB -- cargo tauri build falhou
        set /a ERROS+=1
    ) else (
        echo   OK: HUB
        echo   .msi: %ROOT%\HUB\src-tauri\target\release\bundle\msi\
        echo   .exe: %ROOT%\HUB\src-tauri\target\release\bundle\nsis\
        set "BUILDS=%BUILDS% HUB"
    )
    echo.
)

REM ── OGMA ────────────────────────────────────────────────────────────────────
echo %TARGETS% | findstr /i "ogma" >nul
if %errorlevel%==0 (
    echo [OGMA] npm run dist:win
    cd /d "%ROOT%\OGMA"
    call npm run dist:win
    if !errorlevel! neq 0 (
        echo   ERRO: OGMA -- npm run dist:win falhou
        set /a ERROS+=1
    ) else (
        echo   OK: OGMA
        echo   Pacote: %ROOT%\OGMA\dist\
        set "BUILDS=%BUILDS% OGMA"
    )
    echo.
)

REM ── Aviso apps Python (sem build) ────────────────────────────────────────────
for %%A in (kosmos mnemosyne hermes akasha) do (
    echo %TARGETS% | findstr /i "%%A" >nul
    if !errorlevel!==0 (
        echo   AVISO: %%A roda do source -- nenhum build necessario
    )
)

REM ── Resumo ───────────────────────────────────────────────────────────────────
echo.
echo ============================================
if %ERROS%==0 (
    if not "%BUILDS%"=="" (
        echo    Build concluido:%BUILDS%
    ) else (
        echo    Nenhum app compilavel foi especificado
    )
) else (
    echo    Concluido com %ERROS% erro(s) -- veja o log acima.
)
echo ============================================
echo.
pause
