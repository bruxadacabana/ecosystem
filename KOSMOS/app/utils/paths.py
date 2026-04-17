"""Caminhos centralizados do projeto — nunca use strings hardcoded.

Todos os módulos devem importar daqui::

    from app.utils.paths import Paths
    db = Paths.DB          # Path object
    log_dir = Paths.LOGS   # Path object
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _read_kosmos_eco() -> dict:
    """Lê a seção 'kosmos' do ecosystem.json; retorna {} em caso de erro."""
    try:
        appdata = os.environ.get("APPDATA", "")
        candidates = [
            Path(appdata) / "ecosystem" / "ecosystem.json",
            Path.home() / ".local" / "share" / "ecosystem" / "ecosystem.json",
        ]
        for eco_path in candidates:
            if eco_path.exists():
                return json.loads(eco_path.read_text(encoding="utf-8")).get("kosmos", {})
    except Exception:
        pass
    return {}


_kosmos_eco = _read_kosmos_eco()


def _eco_archive(default: Path) -> Path:
    archive = _kosmos_eco.get("archive_path", "")
    return Path(archive) if archive else default


def _eco_config_dir(default: Path) -> Path:
    config_path = _kosmos_eco.get("config_path", "")
    return Path(config_path) if config_path else default


class Paths:
    # Raiz = diretório onde main.py reside (dois níveis acima deste arquivo)
    ROOT: Path = Path(__file__).parent.parent.parent

    DATA:         Path = ROOT / "data"
    CACHE:        Path = DATA / "cache"
    FAVICONS:     Path = CACHE / "favicons"
    IMAGES:       Path = CACHE / "images"
    ARCHIVE:      Path = _eco_archive(DATA / "archive")
    EXPORTS:      Path = DATA / "exports"
    ARGOS_MODELS: Path = DATA / "argos_models"
    LOGS:         Path = DATA / "logs"

    APP:   Path = ROOT / "app"
    THEME: Path = APP  / "theme"
    FONTS: Path = THEME / "fonts"

    DB:       Path = DATA / "kosmos.db"
    SETTINGS: Path = _eco_config_dir(DATA) / "settings.json"

    @classmethod
    def ensure_directories(cls) -> None:
        """Cria todos os diretórios de dados necessários se não existirem."""
        for directory in (
            cls.DATA,
            cls.CACHE,
            cls.FAVICONS,
            cls.IMAGES,
            cls.ARCHIVE,
            cls.EXPORTS,
            cls.ARGOS_MODELS,
            cls.LOGS,
        ):
            directory.mkdir(parents=True, exist_ok=True)
