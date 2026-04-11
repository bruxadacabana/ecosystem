#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/../.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Ambiente virtual não encontrado em $VENV_DIR"
    echo "Execute o setup na raiz do ecossistema primeiro."
    exit 1
fi

source "$VENV_DIR/bin/activate"
python "$SCRIPT_DIR/hermes.py"
