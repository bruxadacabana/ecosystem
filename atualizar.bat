@echo off
REM Atualiza dependências de todos os apps do ecossistema.
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
REM Remove trailing backslash
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set ERROS=0

echo.
echo ============================================
echo    ECOSSISTEMA -- Atualizacao de deps
echo ============================================
echo.

REM ── Git ──────────────────────────────────────────────────────────────────────
echo [Git] git pull
cd /d "%ROOT%"
git pull
if %errorlevel% neq 0 (
    echo   AVISO: git pull falhou -- continuando com versao local
) else (
    echo   OK: Repositorio atualizado
)

REM ── AKASHA (uv) ───────────────────────────────────────────────────────────────
echo.
echo [AKASHA] uv sync
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo   ERRO: 'uv' nao encontrado -- instale em https://docs.astral.sh/uv/
    set /a ERROS+=1
) else (
    cd /d "%ROOT%\AKASHA"
    uv sync
    if %errorlevel% neq 0 (
        echo   ERRO: uv sync falhou
        set /a ERROS+=1
    ) else (
        echo   OK: AKASHA
    )
)

REM ── Venv compartilhado (KOSMOS . Mnemosyne . Hermes) ─────────────────────────
echo.
echo [Python] Ambiente virtual compartilhado -- KOSMOS, Mnemosyne, Hermes

set "VENV=%ROOT%\.venv"
set "PIP=%VENV%\Scripts\pip.exe"
set "PYTHON=%VENV%\Scripts\python.exe"

if not exist "%VENV%" (
    echo   Criando .venv...
    python -m venv "%VENV%"
    if %errorlevel% neq 0 (
        echo   ERRO: Falha ao criar .venv -- verifique se Python esta instalado
        set /a ERROS+=1
        goto :NODE
    )
)

"%PIP%" install --upgrade pip --quiet

"%PIP%" install -r "%ROOT%\KOSMOS\requirements.txt" --quiet
if %errorlevel% neq 0 (
    echo   ERRO: KOSMOS -- pip install falhou
    set /a ERROS+=1
) else (
    echo   OK: KOSMOS
)

"%PIP%" install -r "%ROOT%\Mnemosyne\requirements.txt" --quiet
if %errorlevel% neq 0 (
    echo   ERRO: Mnemosyne -- pip install falhou
    set /a ERROS+=1
) else (
    echo   OK: Mnemosyne
)

"%PIP%" install --upgrade yt-dlp openai-whisper --quiet
if %errorlevel% neq 0 (
    echo   ERRO: Hermes -- pip install falhou
    set /a ERROS+=1
) else (
    echo   OK: Hermes (yt-dlp + openai-whisper)
)

REM ── Node (AETHER . HUB . OGMA) ────────────────────────────────────────────────
:NODE
echo.
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo   ERRO: npm nao encontrado -- AETHER, HUB e OGMA nao foram atualizados
    set /a ERROS+=1
    goto :RESUMO
)

for %%A in (AETHER HUB OGMA) do (
    echo.
    echo [%%A] npm install
    if not exist "%ROOT%\%%A\package.json" (
        echo   ERRO: %%A -- package.json nao encontrado
        set /a ERROS+=1
    ) else (
        cd /d "%ROOT%\%%A"
        call npm install --silent
        if !errorlevel! neq 0 (
            echo   ERRO: %%A -- npm install falhou
            set /a ERROS+=1
        ) else (
            echo   OK: %%A
        )
    )
)

REM ── Resumo ────────────────────────────────────────────────────────────────────
:RESUMO
echo.
echo ============================================
if %ERROS%==0 (
    echo    Tudo atualizado com sucesso!
) else (
    echo    Concluido com %ERROS% erro(s) -- veja o log acima.
)
echo ============================================
echo.
pause
