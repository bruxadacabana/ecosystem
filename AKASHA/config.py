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

AKASHA_PORT: int = 7070
AKASHA_BASE_URL: str = f"http://localhost:{AKASHA_PORT}"

_AKASHA_DIR = Path(__file__).parent
DB_PATH: Path = _AKASHA_DIR / "akasha.db"

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

# Caminhos expostos (string vazia = não configurado)
kosmos_archive: str  = _eco.get("kosmos", {}).get("archive_path", "")
aether_vault:   str  = _eco.get("aether", {}).get("vault_path", "")
mnemosyne_indices: list[str] = _eco.get("mnemosyne", {}).get("index_paths", [])

# qBittorrent (defaults sobrescrevíveis pelo banco de settings)
QBT_HOST_DEFAULT: str = "localhost"
QBT_PORT_DEFAULT: int = 8080


# ---------------------------------------------------------------------------
# Registro no ecossistema
# ---------------------------------------------------------------------------

def register_akasha() -> None:
    """Escreve base_url e exe_path do AKASHA no ecosystem.json."""
    if not _ECO_AVAILABLE:
        return
    try:
        import sys as _sys
        script = "iniciar.bat" if _sys.platform == "win32" else "iniciar.sh"
        _write_section("akasha", {
            "base_url": AKASHA_BASE_URL,
            "exe_path": str(_AKASHA_DIR / script),
        })
    except Exception:
        pass  # ecosystem é opcional — nunca bloquear o startup
