#!/usr/bin/env bash
# Compila os apps do ecossistema que precisam de build.
#
# Uso:
#   ./buildar.sh               — builda AETHER, HUB e OGMA
#   ./buildar.sh hub           — builda só o HUB
#   ./buildar.sh aether hub    — builda AETHER e HUB
#   ./buildar.sh ogma          — builda só o OGMA
#
# Apps Python (KOSMOS, Mnemosyne, Hermes, AKASHA) rodam do source — sem build.

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ERROS=()
BUILDS=()

header() { echo -e "\n${BOLD}${CYAN}▶ $1${NC}"; }
ok()     { echo -e "  ${GREEN}✓ $1${NC}"; }
warn()   { echo -e "  ${YELLOW}⚠ $1${NC}"; }
fail()   { echo -e "  ${RED}✗ $1${NC}"; ERROS+=("$1"); }
info()   { echo -e "  $1"; }

# ── Determina o que buildar ───────────────────────────────────────────────────
if [ $# -eq 0 ]; then
    TARGETS=(aether hub ogma)
else
    TARGETS=("$@")
fi

# Normaliza para minúsculas
for i in "${!TARGETS[@]}"; do
    TARGETS[$i]="${TARGETS[$i],,}"
done

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════╗"
echo "║   ECOSSISTEMA — Build de produção        ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"
echo "  Targets: ${TARGETS[*]}"

# ── AETHER ────────────────────────────────────────────────────────────────────
if [[ " ${TARGETS[*]} " == *" aether "* ]]; then
    header "AETHER — cargo tauri build"
    cd "$ROOT/AETHER"
    if cargo tauri build; then
        BUNDLE="$ROOT/AETHER/src-tauri/target/release/bundle"
        ok "AETHER OK"
        info "  AppImage: $BUNDLE/appimage/"
        info "  .deb:     $BUNDLE/deb/"
        BUILDS+=("AETHER")
    else
        fail "AETHER — cargo tauri build falhou"
    fi
fi

# ── HUB ───────────────────────────────────────────────────────────────────────
if [[ " ${TARGETS[*]} " == *" hub "* ]]; then
    header "HUB — cargo tauri build"
    cd "$ROOT/HUB"
    if cargo tauri build; then
        BUNDLE="$ROOT/HUB/src-tauri/target/release/bundle"
        ok "HUB OK"
        info "  AppImage: $BUNDLE/appimage/"
        info "  .deb:     $BUNDLE/deb/"
        BUILDS+=("HUB")
    else
        fail "HUB — cargo tauri build falhou"
    fi
fi

# ── OGMA ──────────────────────────────────────────────────────────────────────
if [[ " ${TARGETS[*]} " == *" ogma "* ]]; then
    header "OGMA — npm run dist:linux"
    cd "$ROOT/OGMA"
    if npm run dist:linux; then
        ok "OGMA OK"
        info "  Pacote: $ROOT/OGMA/dist/"
        BUILDS+=("OGMA")
    else
        fail "OGMA — npm run dist:linux falhou"
    fi
fi

# ── Aviso apps Python (sem build) ─────────────────────────────────────────────
for app in kosmos mnemosyne hermes akasha; do
    if [[ " ${TARGETS[*]} " == *" $app "* ]]; then
        warn "${app^} roda do source — nenhum build necessário"
    fi
done

# ── Resumo ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}══════════════════════════════════════════${NC}"
if [ ${#ERROS[@]} -eq 0 ] && [ ${#BUILDS[@]} -gt 0 ]; then
    echo -e "${BOLD}${GREEN}   Build concluído: ${BUILDS[*]}${NC}"
elif [ ${#ERROS[@]} -eq 0 ]; then
    echo -e "${BOLD}${YELLOW}   Nenhum app compilável foi especificado${NC}"
else
    echo -e "${BOLD}${YELLOW}   Concluído com ${#ERROS[@]} erro(s):${NC}"
    for e in "${ERROS[@]}"; do
        echo -e "  ${RED}• $e${NC}"
    done
fi
echo -e "${BOLD}══════════════════════════════════════════${NC}"
