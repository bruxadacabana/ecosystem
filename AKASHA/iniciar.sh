#!/usr/bin/env bash
# AKASHA — Script de inicialização
# Detecta o venv do ecossistema ou cria um local, então executa o servidor.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ECO_VENV="$(dirname "$SCRIPT_DIR")/.venv"
LOCAL_VENV="$SCRIPT_DIR/.venv"

cd "$SCRIPT_DIR"

# ── Escolhe o venv a usar ────────────────────────────────────────────
if [ -d "$ECO_VENV" ] && [ -f "$ECO_VENV/bin/activate" ]; then
    VENV_DIR="$ECO_VENV"
else
    VENV_DIR="$LOCAL_VENV"
    if [ ! -d "$VENV_DIR" ]; then
        echo "[AKASHA] Criando venv local em $VENV_DIR"
        uv venv "$VENV_DIR"
    fi
fi

# ── Sincroniza dependências ───────────────────────────────────────────
echo "[AKASHA] Sincronizando dependências…"
uv sync --python "$VENV_DIR/bin/python"

# ── Inicia o servidor ─────────────────────────────────────────────────
echo "[AKASHA] Iniciando na porta 7071…"
xdg-open "http://localhost:7071" 2>/dev/null &
exec uv run python main.py
