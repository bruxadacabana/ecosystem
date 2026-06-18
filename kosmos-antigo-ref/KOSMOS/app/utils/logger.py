"""Configuração centralizada do logger do KOSMOS."""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from pathlib import Path

from app.utils.paths import Paths


def _resolve_sync_log_dir() -> Path | None:
    """Retorna {sync_root}/kosmos/ se sync_root configurado, None caso contrário."""
    try:
        appdata = os.environ.get("APPDATA", "")
        candidates = [
            Path(appdata) / "ecosystem" / "ecosystem.json",
            Path.home() / ".local" / "share" / "ecosystem" / "ecosystem.json",
        ]
        for eco_path in candidates:
            if eco_path.exists():
                sync_root = json.loads(eco_path.read_text(encoding="utf-8")).get("sync_root", "")
                if sync_root:
                    d = Path(sync_root) / "kosmos"
                    d.mkdir(parents=True, exist_ok=True)
                    return d
    except Exception:
        pass
    return None


def setup_logger(level: int = logging.INFO) -> None:
    """Configura logging para arquivo local + arquivo em sync_root (lido pelo HUB) + stderr."""
    local_log: Path = Paths.LOGS / "kosmos.log"
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(local_log, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"),
        logging.StreamHandler(),
    ]

    sync_dir = _resolve_sync_log_dir()
    if sync_dir:
        handlers.append(
            logging.handlers.RotatingFileHandler(
                sync_dir / "kosmos.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
        )

    logging.basicConfig(level=level, format=fmt, handlers=handlers)

    # Reduzir ruído de bibliotecas de terceiros
    for noisy_lib in ("feedparser", "urllib3", "requests", "PIL", "matplotlib"):
        logging.getLogger(noisy_lib).setLevel(logging.WARNING)
