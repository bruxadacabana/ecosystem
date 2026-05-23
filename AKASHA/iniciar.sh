#!/usr/bin/env bash
# AKASHA — Script de inicialização
# Usa o venv local gerenciado pelo uv (AKASHA/.venv, Python 3.13).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Garante que uv está no PATH ───────────────────────────────────────
if ! command -v uv &>/dev/null; then
    for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" /usr/local/bin/uv; do
        if [ -x "$candidate" ]; then
            export PATH="$(dirname "$candidate"):$PATH"
            break
        fi
    done
fi
if ! command -v uv &>/dev/null; then
    echo "[AKASHA] ERRO: uv não encontrado. Instale em https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

# ── Sincroniza dependências no venv local (Python 3.13) ──────────────
echo "[AKASHA] Sincronizando dependências…"
uv sync --python 3.13

# ── Inicia o servidor ─────────────────────────────────────────────────
echo "[AKASHA] Iniciando na porta 7071…"
xdg-open "http://localhost:7071" 2>/dev/null &
uv run --python 3.13 python main.py
