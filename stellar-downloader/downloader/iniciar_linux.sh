#!/usr/bin/env bash
cd "$(dirname "$0")"

if command -v uv &>/dev/null; then
    echo "Iniciando com uv..."
    uv run --with yt-dlp downloader.py
elif [ -d "venv" ]; then
    source venv/bin/activate 2>/dev/null || source venv/bin/activate.fish 2>/dev/null
    python3 downloader.py
else
    echo "Criando ambiente virtual..."
    python3 -m venv venv
    source venv/bin/activate
    pip install yt-dlp
    python3 downloader.py
fi
