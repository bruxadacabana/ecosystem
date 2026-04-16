@echo off
cd /d "%~dp0"

set ECO_VENV=%~dp0..\.venv
set LOCAL_VENV=%~dp0.venv

if exist "%ECO_VENV%\Scripts\activate.bat" (
    set VENV_DIR=%ECO_VENV%
) else (
    set VENV_DIR=%LOCAL_VENV%
    if not exist "%LOCAL_VENV%" (
        echo [AKASHA] Criando venv local em %LOCAL_VENV%...
        uv venv "%LOCAL_VENV%"
    )
)

echo [AKASHA] Sincronizando dependencias...
uv sync

echo [AKASHA] Iniciando na porta 7070...
uv run python main.py
