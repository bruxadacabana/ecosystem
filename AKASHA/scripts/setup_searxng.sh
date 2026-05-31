#!/usr/bin/env bash
# =============================================================================
# setup_searxng.sh — Instala e configura o SearXNG self-hosted para o AKASHA
#
# Uso: bash AKASHA/scripts/setup_searxng.sh
#
# O que este script faz:
#   1. Clona o repositório SearXNG em ~/.local/share/searxng
#   2. Cria venv e instala dependências via uv
#   3. Gera settings.yml com configurações de privacidade e engines curados
#   4. Cria um serviço systemd --user para iniciar com o login
#   5. Habilita e inicia o serviço
#   6. Verifica que o healthcheck responde em localhost:8888
#
# Requisitos: git, uv, systemd (usuário)
# =============================================================================

set -euo pipefail

# Resolver SCRIPT_DIR antes de qualquer cd — BASH_SOURCE[0] é relativo ao CWD de invocação
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SEARXNG_DIR="${HOME}/.local/share/searxng"
SEARXNG_CONFIG_DIR="${HOME}/.config/searxng"
SEARXNG_PORT=8888
SEARXNG_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")

echo "==> [SearXNG] Verificando dependências..."
command -v git >/dev/null 2>&1 || { echo "ERRO: git não encontrado"; exit 1; }
command -v uv  >/dev/null 2>&1 || { echo "ERRO: uv não encontrado"; exit 1; }

# ---------------------------------------------------------------------------
# 1. Clonar (ou atualizar) repositório
# ---------------------------------------------------------------------------
if [ -d "${SEARXNG_DIR}/.git" ]; then
    echo "==> [SearXNG] Repositório já existe — atualizando..."
    git -C "${SEARXNG_DIR}" pull --ff-only
else
    echo "==> [SearXNG] Clonando repositório..."
    git clone --depth=1 https://github.com/searxng/searxng "${SEARXNG_DIR}"
fi

# ---------------------------------------------------------------------------
# 2. Instalar dependências (venv isolado)
# ---------------------------------------------------------------------------
echo "==> [SearXNG] Instalando dependências via uv..."
cd "${SEARXNG_DIR}"
# SearXNG usa requirements.txt + setup.py (não pyproject.toml)
if [ ! -d ".venv" ]; then
    uv venv .venv
fi
uv pip install --python .venv/bin/python -r requirements.txt
# Instala o próprio pacote searx em modo editável (necessário para python -m searx.webapp)
uv pip install --python .venv/bin/python -e . 2>/dev/null || true

# ---------------------------------------------------------------------------
# 3. Criar diretório de configuração e gerar settings.yml
# ---------------------------------------------------------------------------
mkdir -p "${SEARXNG_CONFIG_DIR}"

# Se já existe settings.yml, faz backup
if [ -f "${SEARXNG_CONFIG_DIR}/settings.yml" ]; then
    cp "${SEARXNG_CONFIG_DIR}/settings.yml" "${SEARXNG_CONFIG_DIR}/settings.yml.bak"
    echo "==> [SearXNG] Backup de settings.yml existente em settings.yml.bak"
fi

# Copia e ajusta settings.yml do AKASHA (gerado com secret_key)
AKASHA_SETTINGS="${SCRIPT_DIR}/searxng_settings.yml"

if [ -f "${AKASHA_SETTINGS}" ]; then
    # Substitui placeholder de secret_key pelo valor gerado
    sed "s/__SECRET_KEY__/${SEARXNG_SECRET}/" "${AKASHA_SETTINGS}" > "${SEARXNG_CONFIG_DIR}/settings.yml"
    echo "==> [SearXNG] settings.yml instalado em ${SEARXNG_CONFIG_DIR}/settings.yml"
else
    echo "AVISO: ${AKASHA_SETTINGS} não encontrado — usando settings.yml padrão"
fi

# ---------------------------------------------------------------------------
# 4. Criar serviço systemd --user
# ---------------------------------------------------------------------------
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
mkdir -p "${SYSTEMD_USER_DIR}"

cat > "${SYSTEMD_USER_DIR}/searxng.service" << EOF
[Unit]
Description=SearXNG — metabuscador privado (AKASHA)
After=network.target

[Service]
Type=simple
WorkingDirectory=${SEARXNG_DIR}
Environment=SEARXNG_SETTINGS_PATH=${SEARXNG_CONFIG_DIR}/settings.yml
ExecStart=${SEARXNG_DIR}/.venv/bin/python -m searx.webapp
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

echo "==> [SearXNG] Serviço systemd criado em ${SYSTEMD_USER_DIR}/searxng.service"

# ---------------------------------------------------------------------------
# 5. Habilitar e iniciar serviço
# ---------------------------------------------------------------------------
systemctl --user daemon-reload
systemctl --user enable searxng
systemctl --user start searxng

echo "==> [SearXNG] Aguardando inicialização (10s)..."
sleep 10

# ---------------------------------------------------------------------------
# 6. Verificação de saúde
# ---------------------------------------------------------------------------
if curl -sf --max-time 5 "http://localhost:${SEARXNG_PORT}/healthz" | grep -q "OK"; then
    echo "==> [SearXNG] ✓ Healthcheck OK em localhost:${SEARXNG_PORT}"
else
    echo "==> [SearXNG] AVISO: healthcheck não respondeu — verifique o serviço:"
    echo "    systemctl --user status searxng"
    echo "    journalctl --user -u searxng -n 30"
    exit 1
fi

# Teste de busca JSON
RESULT_COUNT=$(curl -sf "http://localhost:${SEARXNG_PORT}/search?q=python+programming&format=json" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('results',[])))")
echo "==> [SearXNG] Teste de busca: ${RESULT_COUNT} resultados para 'python programming'"

echo ""
echo "==> [SearXNG] Instalação concluída!"
echo "    URL: http://localhost:${SEARXNG_PORT}"
echo "    Config: ${SEARXNG_CONFIG_DIR}/settings.yml"
echo "    Service: systemctl --user status searxng"
echo ""
echo "==> Próximo passo: configure o AKASHA via Settings ou:"
echo "    Edite ecosystem.json: akasha.web_search_backend = \"http://localhost:${SEARXNG_PORT}\""
