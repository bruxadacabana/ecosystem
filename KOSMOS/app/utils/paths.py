"""Caminhos canônicos do KOSMOS. Importar primeiro — configura sys.path para ecosystem_client."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Raiz da instalação: .../program files/KOSMOS/
KOSMOS_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# ecosystem_client.py está em program files/ (um nível acima)
_PROGRAM_FILES = KOSMOS_ROOT.parent
if str(_PROGRAM_FILES) not in sys.path:
    sys.path.insert(0, str(_PROGRAM_FILES))

# ---------------------------------------------------------------------------
# Caminhos de dados. Cache/logs ficam locais; o BANCO fica no sync_root/kosmos/
# (sincronizado via Syncthing + backup versionado pelo HUB em .backup/kosmos/).
# ---------------------------------------------------------------------------

def _local_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "kosmos"


LOCAL_DATA_DIR: Path = _local_data_dir()
LEGACY_LOCAL_DB: Path = LOCAL_DATA_DIR / "kosmos.db"  # local antigo (migrado p/ sync_root)
LOG_DIR:        Path = LOCAL_DATA_DIR / "logs"   # fallback local (sem sync_root)


def _resolve_db_path() -> Path:
    """Resolve `{sync_root}/kosmos/kosmos.db` (sincronizado entre máquinas).

    O banco mora na pasta sincronizada para que as fontes/artigos sobrevivam à perda
    do disco local e sincronizem entre máquinas (o HUB ainda versiona um backup em
    `.backup/kosmos/`). Sem `sync_root` acessível, cai no caminho local (fallback).
    """
    try:
        import ecosystem_client  # disponível via sys.path configurado acima
        root = ecosystem_client.get_sync_root()
        if root is not None:
            d = Path(root) / "kosmos"
            d.mkdir(parents=True, exist_ok=True)
            return d / "kosmos.db"
    except Exception:
        pass  # bootstrap antes do logger; sync_root indisponível → fallback local
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return LEGACY_LOCAL_DB


DB_PATH:        Path = _resolve_db_path()


def _resolve_log_path() -> Path:
    """Resolve o caminho do log preferindo `{sync_root}/kosmos/kosmos.log`.

    O HUB lê o log de cada app em `{sync_root}/{app}/{app}.log` (comando
    `read_app_log`) para exibir na aba Monitor — mesma convenção do Mnemosyne.
    Escrever nesse caminho é o que faz os logs do KOSMOS aparecerem no Monitor.
    Sem `sync_root` acessível, cai no diretório local (`LOG_DIR`).
    """
    try:
        import ecosystem_client  # disponível via sys.path configurado acima
        root = ecosystem_client.get_sync_root()
        if root is not None:
            d = Path(root) / "kosmos"
            d.mkdir(parents=True, exist_ok=True)
            return d / "kosmos.log"
    except Exception:
        # Bootstrap: isto roda antes do logger existir, então não há como logar.
        # sync_root indisponível/inacessível → usa o caminho local (intencional).
        pass
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / "kosmos.log"


LOG_PATH:       Path = _resolve_log_path()
CACHE_DIR:      Path = LOCAL_DATA_DIR / "cache"
FAVICON_DIR:    Path = CACHE_DIR / "favicons"
IMAGE_DIR:      Path = CACHE_DIR / "images"

# Recursos estáticos do app
FONTS_DIR:  Path = KOSMOS_ROOT / "app" / "theme" / "fonts"
THEMES_DIR: Path = KOSMOS_ROOT / "app" / "theme"
