"""Caminhos centralizados do projeto — nunca use strings hardcoded.

Todos os módulos devem importar daqui::

    from app.utils.paths import Paths
    db = Paths.DB          # Path object
    log_dir = Paths.LOGS   # Path object
"""

from __future__ import annotations

from pathlib import Path


class Paths:
    # Raiz = diretório onde main.py reside (dois níveis acima deste arquivo)
    ROOT: Path = Path(__file__).parent.parent.parent

    DATA:         Path = ROOT / "data"
    CACHE:        Path = DATA / "cache"
    FAVICONS:     Path = CACHE / "favicons"
    IMAGES:       Path = CACHE / "images"
    ARCHIVE:      Path = DATA / "archive"
    EXPORTS:      Path = DATA / "exports"
    ARGOS_MODELS: Path = DATA / "argos_models"
    LOGS:         Path = DATA / "logs"

    APP:   Path = ROOT / "app"
    THEME: Path = APP  / "theme"
    FONTS: Path = THEME / "fonts"

    DB:       Path = DATA / "kosmos.db"
    SETTINGS: Path = DATA / "settings.json"

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
