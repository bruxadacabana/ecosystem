#!/usr/bin/env bash
# Atualiza dependências de todos os apps do ecossistema.

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.local/bin:$PATH"
ERROS=()

header() { echo -e "\n${BOLD}${CYAN}▶ $1${NC}"; }
ok()     { echo -e "  ${GREEN}✓ $1${NC}"; }
warn()   { echo -e "  ${YELLOW}⚠ $1${NC}"; }
fail()   { echo -e "  ${RED}✗ $1${NC}"; ERROS+=("$1"); }

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════╗"
echo "║   ECOSSISTEMA — Atualização de deps      ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# ── Git ───────────────────────────────────────────────────────────────────────
header "Repositório (git pull)"
cd "$ROOT"
if git pull; then
    ok "Repositório atualizado"
else
    warn "git pull falhou — continuando com a versão local"
fi

# ── AKASHA (uv) ───────────────────────────────────────────────────────────────
header "AKASHA — uv sync"
if command -v uv &>/dev/null; then
    cd "$ROOT/AKASHA"
    if uv sync; then
        ok "AKASHA OK"
    else
        fail "AKASHA — uv sync falhou"
    fi
else
    fail "AKASHA — 'uv' não encontrado (instale: https://docs.astral.sh/uv/)"
fi

# ── SearXNG vendorizado (3ª alternativa de busca — sem Docker, Windows/Linux) ──
header "SearXNG vendorizado — setup (venv + settings)"
if command -v uv &>/dev/null; then
    if python3 "$ROOT/AKASHA/vendor/setup_searxng_vendor.py"; then
        ok "SearXNG vendorizado OK"
    else
        fail "SearXNG vendorizado — setup falhou"
    fi
else
    fail "SearXNG vendorizado — 'uv' não encontrado"
fi

# ── Venv compartilhado (KOSMOS · Mnemosyne · Hermes) ─────────────────────────
header "Ambiente virtual compartilhado — KOSMOS · Mnemosyne · Hermes"
VENV="$ROOT/.venv"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"

if [ ! -d "$VENV" ]; then
    echo "  Criando .venv..."
    if ! python3 -m venv "$VENV"; then
        fail "Falha ao criar .venv — verifique se python3 está instalado"
        VENV=""
    fi
fi

if [ -n "$VENV" ] && [ -d "$VENV" ]; then
    "$PIP" install --upgrade pip --quiet

    if (cd "$ROOT/KOSMOS" && uv sync --quiet 2>&1); then
        ok "KOSMOS OK"
    else
        fail "KOSMOS — uv sync falhou"
    fi

    if "$PIP" install -r "$ROOT/Mnemosyne/requirements.txt" --quiet; then
        ok "Mnemosyne OK"
    else
        fail "Mnemosyne — pip install falhou"
    fi

    "$PIP" uninstall torch openai-whisper -y --quiet 2>/dev/null || true
    if "$PIP" install -r "$ROOT/Hermes/requirements.txt" --quiet; then
        ok "Hermes OK"
    else
        fail "Hermes — pip install falhou"
    fi
fi

# ── Node (AETHER · HUB · OGMA) ────────────────────────────────────────────────
if ! command -v npm &>/dev/null; then
    fail "npm não encontrado — AETHER, HUB e OGMA não foram atualizados"
else
    for app in AETHER HUB OGMA; do
        header "$app — npm install"
        APP_DIR="$ROOT/$app"
        if [ ! -f "$APP_DIR/package.json" ]; then
            fail "$app — package.json não encontrado em $APP_DIR"
            continue
        fi
        cd "$APP_DIR"
        if npm install --silent 2>/dev/null || npm install; then
            ok "$app OK"
        else
            fail "$app — npm install falhou"
        fi
    done
fi

# ── Resumo ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}══════════════════════════════════════════${NC}"
if [ ${#ERROS[@]} -eq 0 ]; then
    echo -e "${BOLD}${GREEN}   Tudo atualizado com sucesso!${NC}"
else
    echo -e "${BOLD}${YELLOW}   Concluído com ${#ERROS[@]} erro(s):${NC}"
    for e in "${ERROS[@]}"; do
        echo -e "  ${RED}• $e${NC}"
    done
fi
echo -e "${BOLD}══════════════════════════════════════════${NC}"
