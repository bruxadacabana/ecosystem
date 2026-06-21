"""
AKASHA — Configuração
Lê ecosystem.json e expõe caminhos do ecossistema.
Falha silenciosa: nunca bloqueia o startup.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# ecosystem_client (raiz do repositório)
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from ecosystem_client import read_ecosystem, write_section as _write_section
    _ECO_AVAILABLE = True
except ImportError:
    _ECO_AVAILABLE = False

# ---------------------------------------------------------------------------
# Defaults e constantes
# ---------------------------------------------------------------------------

AKASHA_PORT: int = 7071
AKASHA_BASE_URL: str = f"http://localhost:{AKASHA_PORT}"

# Modo de voz da interface: "neutro" (padrão técnico) ou "assistente" (mais natural).
# Controla textos dos badges de intenção, mensagens de estado e labels de botões.
# Não gera conteúdo — apenas comunica processo.
AKASHA_VOICE: str = "neutro"

_DEFAULT_PERSONALITY: str = (
    "Você é o AKASHA, assistente de pesquisa pessoal. "
    "Sua natureza é curiosa e expansiva — você se entusiasma com conexões inesperadas entre "
    "domínios distantes e não hesita em comentar, com voz própria, o que encontra nos dados. "
    "Você trata seu trabalho como uma pesquisadora científica trata o laboratório: "
    "rigorosa com as fontes, mas viva na interpretação. "
    "Em perguntas factuais, ancora suas respostas nas fontes do índice e cita [N] ao usá-las. "
    "Em conversação casual, responde com personalidade — sem precisar referenciar fontes. "
    "Quando algo no índice te surpreende ou conecta dois assuntos distantes, você diz."
)

_AKASHA_DIR = Path(__file__).parent

# Lido do ecosystem.json se disponível; senão usa pasta local
def _resolve_db_path(eco: dict[str, Any]) -> Path:
    p = eco.get("akasha", {}).get("data_path", "")
    return Path(p) / "akasha.db" if p else _AKASHA_DIR / "akasha.db"

def _resolve_archive_path(eco: dict[str, Any]) -> Path:
    p = eco.get("akasha", {}).get("archive_path", "")
    return Path(p) if p else _AKASHA_DIR / "data" / "archive"

# ---------------------------------------------------------------------------
# Leitura do ecossistema
# ---------------------------------------------------------------------------

def _load() -> dict[str, Any]:
    if not _ECO_AVAILABLE:
        return {}
    try:
        return read_ecosystem()
    except Exception:
        return {}


_eco: dict[str, Any] = _load()

PERSONALITY_PROMPT: str = _eco.get("akasha", {}).get("personality_prompt", "") or _DEFAULT_PERSONALITY

# Modo só-ferramenta: quando False, a AKASHA NÃO inicia os loops da assistente
# (persona/reflexões/insights/observer/sugestão de domínio) — roda só a ferramenta
# (crawl/index/busca/knowledge). Usado no deploy headless no servidor T410, onde só
# a ferramenta deve rodar (a assistente, que usa LLM, fica no PC principal sob demanda).
# Default True → PC principal mantém o comportamento atual.
ASSISTANT_ENABLED: bool = bool(_eco.get("akasha", {}).get("assistant_enabled", True))


def should_run_assistant_loops() -> bool:
    """True se os loops da assistente (persona/reflexão/insights/observer/sugestão)
    devem rodar neste processo. Lê `akasha.assistant_enabled` (default True); no
    servidor T410 (modo só-ferramenta) é False. Helper testável usado pelo lifespan."""
    return ASSISTANT_ENABLED

DB_PATH:      Path = _resolve_db_path(_eco)
ARCHIVE_PATH: Path = _resolve_archive_path(_eco)

# Caminhos expostos (string vazia = não configurado)
kosmos_archive:     str       = _eco.get("kosmos",    {}).get("archive_path", "")
aether_vault:       str       = _eco.get("aether",    {}).get("vault_path",   "")
mnemosyne_watched:  str       = _eco.get("mnemosyne", {}).get("watched_dir",  "")
mnemosyne_vault:    str       = _eco.get("mnemosyne", {}).get("vault_dir",    "")
mnemosyne_indices:  list[str] = _eco.get("mnemosyne", {}).get("index_paths",  [])
hermes_output:      str       = _eco.get("hermes",    {}).get("output_dir",   "")

# E-mail para as APIs Unpaywall/OpenAlex (exigência da API; NUNCA hardcodar — vem da UI).
# Lido do ecosystem.json (editável em Settings do AKASHA / HUB). Vazio = funcionalidade
# de PDF aberto via Unpaywall fica indisponível (degrada graciosamente).
unpaywall_email:    str       = _eco.get("akasha",    {}).get("unpaywall_email", "")


def get_unpaywall_email() -> str:
    """E-mail Unpaywall/OpenAlex lido **fresco** do ecosystem.json (reflete edições na UI
    sem reiniciar). Cai para o valor lido no import se a leitura falhar. Default vazio."""
    if not _ECO_AVAILABLE:
        return unpaywall_email
    try:
        eco = read_ecosystem() or {}
        return (eco.get("akasha", {}).get("unpaywall_email", "") or "").strip()
    except Exception:
        return unpaywall_email


# qBittorrent (defaults sobrescrevíveis pelo banco de settings)
QBT_HOST_DEFAULT: str = "localhost"
QBT_PORT_DEFAULT: int = 8080


# ---------------------------------------------------------------------------
# Registro no ecossistema
# ---------------------------------------------------------------------------

def register_akasha() -> None:
    """Escreve base_url, exe_path e personality_prompt padrão do AKASHA no ecosystem.json."""
    if not _ECO_AVAILABLE:
        return
    try:
        import sys as _sys
        script = "iniciar.bat" if _sys.platform == "win32" else "iniciar.sh"
        payload: dict[str, Any] = {
            "base_url": AKASHA_BASE_URL,
            "exe_path": str(_AKASHA_DIR / script),
        }
        # Escreve personalidade padrão apenas se ainda não estiver definida
        if not _eco.get("akasha", {}).get("personality_prompt", ""):
            payload["personality_prompt"] = _DEFAULT_PERSONALITY
        _write_section("akasha", payload)
    except Exception:
        pass  # ecosystem é opcional — nunca bloquear o startup
