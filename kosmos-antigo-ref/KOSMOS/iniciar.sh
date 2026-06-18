#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

VENV_DIR="$(dirname "$0")/../.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "[KOSMOS] Criando ambiente virtual em $VENV_DIR..."
    python -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    echo "[KOSMOS] Instalando dependências..."
    pip install --upgrade pip -q
    pip install -r requirements.txt
else
    source "$VENV_DIR/bin/activate"
fi

python main.py
