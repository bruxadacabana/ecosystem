"""Configuração centralizada do logger do Mnemosyne."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_LOGS_DIR = Path(__file__).parent.parent / "logs"


def setup_logger(level: int = logging.INFO) -> None:
    """Configura logging para arquivo rotativo e stderr.

    O arquivo fica em Mnemosyne/logs/mnemosyne.log.
    Rotação diária, mantém 7 backups.
    """
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _LOGS_DIR / "mnemosyne.log"

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.handlers.TimedRotatingFileHandler(
                log_file,
                when="midnight",
                backupCount=7,
                encoding="utf-8",
            ),
            logging.StreamHandler(),
        ],
    )

    for noisy_lib in ("chromadb", "httpx", "httpcore", "urllib3", "sentence_transformers"):
        logging.getLogger(noisy_lib).setLevel(logging.WARNING)
