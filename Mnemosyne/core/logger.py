"""Configuração centralizada do logger do Mnemosyne."""

from __future__ import annotations

import json
import logging
import logging.handlers
from pathlib import Path

_LOCAL_LOGS_DIR = Path(__file__).parent.parent / "logs"


def _resolve_log_dir() -> Path:
    """Tenta usar {sync_root}/mnemosyne/ para que o HUB possa ler o log.

    Lê ecosystem.json/.local.json diretamente (sem importar config.py)
    para evitar import circular no startup.
    """
    candidates = [
        Path.home() / ".local" / "share" / "ecosystem",
    ]
    import os
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidates.insert(0, Path(appdata) / "ecosystem")

    for eco_dir in candidates:
        for name in ("ecosystem.local.json", "ecosystem.json"):
            p = eco_dir / name
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                sync_root = data.get("sync_root", "")
                if sync_root:
                    return Path(sync_root) / "mnemosyne"
            except Exception:
                continue
    return _LOCAL_LOGS_DIR


def setup_logger(level: int = logging.INFO) -> None:
    """Configura logging para arquivo rotativo (5 MB, 3 backups) e stderr.

    Prioridade de destino:
      1. {sync_root}/mnemosyne/mnemosyne.log — onde o HUB pode ler
      2. Mnemosyne/logs/mnemosyne.log        — fallback local
    """
    log_dir = _resolve_log_dir()
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_dir = _LOCAL_LOGS_DIR
        log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "mnemosyne.log"

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[
            logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            ),
            logging.StreamHandler(),
        ],
    )

    for noisy_lib in ("chromadb", "httpx", "httpcore", "urllib3", "sentence_transformers"):
        logging.getLogger(noisy_lib).setLevel(logging.WARNING)


def get_log_path() -> Path | None:
    """Retorna o caminho do arquivo de log atual (para o HUB ler)."""
    log_dir = _resolve_log_dir()
    p = log_dir / "mnemosyne.log"
    return p if p.exists() else None
