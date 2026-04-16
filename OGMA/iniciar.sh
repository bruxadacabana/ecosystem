#!/usr/bin/env bash
# OGMA — Script de inicialização para CachyOS / Linux
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

# Força X11/XWayland — necessário ao lançar pelo menu em sessão Wayland
export ELECTRON_OZONE_PLATFORM_HINT=x11
export GDK_BACKEND=x11
export DISPLAY="${DISPLAY:-:0}"

# Verifica se o Electron do OGMA está mesmo a correr
ELECTRON_PID=$(pgrep -f "electron.*$SCRIPT_DIR" | head -1)
if [ -n "$ELECTRON_PID" ]; then
    xdotool search --name "OGMA" windowactivate 2>/dev/null || true
    exit 0
fi

# Limpa processos órfãos na porta 5175 (porta exclusiva do OGMA)
STALE_PID=$(lsof -ti:5175 2>/dev/null)
if [ -n "$STALE_PID" ]; then
    kill "$STALE_PID" 2>/dev/null || true
    sleep 1
fi

exec > /tmp/ogma.log 2>&1
echo "=== OGMA $(date) ==="

npm run dev
