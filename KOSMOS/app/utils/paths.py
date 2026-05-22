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
# Dados locais (banco, cache, logs) — não sincronizados pelo Syncthing
# ---------------------------------------------------------------------------

def _local_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "kosmos"


LOCAL_DATA_DIR: Path = _local_data_dir()
DB_PATH:        Path = LOCAL_DATA_DIR / "kosmos.db"
LOG_DIR:        Path = LOCAL_DATA_DIR / "logs"
LOG_PATH:       Path = LOG_DIR / "kosmos.log"
CACHE_DIR:      Path = LOCAL_DATA_DIR / "cache"
FAVICON_DIR:    Path = CACHE_DIR / "favicons"
IMAGE_DIR:      Path = CACHE_DIR / "images"

# Recursos estáticos do app
FONTS_DIR:  Path = KOSMOS_ROOT / "app" / "theme" / "fonts"
THEMES_DIR: Path = KOSMOS_ROOT / "app" / "theme"
