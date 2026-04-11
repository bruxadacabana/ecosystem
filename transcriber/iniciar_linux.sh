#!/bin/bash
# Launcher Linux — usa uv se disponivel, senao venv tradicional
cd "$(dirname "$0")"

# Tenta uv primeiro
if command -v uv &>/dev/null; then
    uv run transcriber.py
    exit $?
fi

# Fallback: venv tradicional
if [ ! -d "venv" ]; then
    echo "uv nao encontrado. Criando venv..."
    python3 -m venv venv
    source venv/bin/activate
    pip install yt-dlp openai-whisper
else
    source venv/bin/activate
fi

python3 transcriber.py
