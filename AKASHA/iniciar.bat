@echo off
cd /d "%~dp0"

echo [AKASHA] Sincronizando dependencias...
uv sync --quiet

if errorlevel 1 (
    echo [AKASHA] Erro ao instalar dependencias. Verifique se uv esta instalado.
    pause
    exit /b 1
)

echo [AKASHA] Iniciando servidor na porta 7070...
echo [AKASHA] Abrindo http://localhost:7070 no navegador...
start "" "http://localhost:7070"

uv run python main.py
