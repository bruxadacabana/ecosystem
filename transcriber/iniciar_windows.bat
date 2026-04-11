@echo off
setlocal EnableDelayedExpansion

:: ─────────────────────────────────────────────────────────
::  Video Transcriber — Launcher para Windows
::  Instala tudo automaticamente na primeira execução.
:: ─────────────────────────────────────────────────────────

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "PORTABLE=%ROOT%\_portable"
set "PYTHON=%PORTABLE%\python\python.exe"
set "FFMPEG=%PORTABLE%\ffmpeg"
set "DONE_FLAG=%PORTABLE%\.setup_done"

:: ── 1. Verificar se já configurou ────────────────────────
if exist "%DONE_FLAG%" goto :launch

:: ── 2. Verificar conectividade básica ────────────────────
ping -n 1 8.8.8.8 >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -Command ^
      "[System.Windows.MessageBox]::Show('Sem conexao com a internet. A configuracao inicial requer internet.','Video Transcriber','OK','Error')" >nul 2>&1
    echo [ERRO] Sem conexao com a internet. A configuracao inicial requer internet.
    pause
    exit /b 1
)

:: ── 3. Verificar permissão para executar PowerShell ──────
powershell -NoProfile -Command "exit 0" >nul 2>&1
if errorlevel 1 (
    echo [ERRO] PowerShell bloqueado por politica de seguranca.
    echo Execute como Administrador ou libere scripts PS no seu sistema.
    pause
    exit /b 1
)

:: ── 4. Executar setup automatico ─────────────────────────
echo Configurando pela primeira vez, aguarde...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\setup.ps1" -BaseDir "%ROOT%"

if errorlevel 1 (
    echo.
    echo [ERRO] A configuracao falhou. Verifique sua conexao e tente novamente.
    pause
    exit /b 1
)

:: ── 5. Verificar se setup teve sucesso ───────────────────
if not exist "%DONE_FLAG%" (
    echo [ERRO] Setup nao foi concluido corretamente.
    pause
    exit /b 1
)

:launch
:: ── 6. Adicionar portateis ao PATH desta sessao ──────────
set "PATH=%PORTABLE%\python;%PORTABLE%\python\Scripts;%FFMPEG%;%PATH%"

:: ── 7. Atualizar yt-dlp silenciosamente (se tiver internet) ──
ping -n 1 8.8.8.8 >nul 2>&1
if not errorlevel 1 (
    start "" /B "%PORTABLE%\python\Scripts\pip.exe" install --quiet -U yt-dlp >nul 2>&1
)

:: ── 8. Iniciar aplicativo ─────────────────────────────────
"%PYTHON%" "%ROOT%\transcriber.py"

if errorlevel 1 (
    echo.
    echo [ERRO] O aplicativo encerrou com erro.
    echo Tente deletar a pasta _portable e executar novamente para reinstalar.
    pause
)

endlocal
