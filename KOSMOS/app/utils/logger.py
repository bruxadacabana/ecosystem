from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FMT  = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES    = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3


def setup_logger(log_path: Path) -> None:
    """Configura logger raiz com RotatingFileHandler (DEBUG) e stderr (INFO)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if root.handlers:
        return  # já configurado (ex: reimportado em testes)
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(_FMT, _DATEFMT)

    file_h = RotatingFileHandler(
        log_path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    file_h.setLevel(logging.DEBUG)
    file_h.setFormatter(fmt)

    console_h = logging.StreamHandler()
    console_h.setLevel(logging.INFO)
    console_h.setFormatter(fmt)

    root.addHandler(file_h)
    root.addHandler(console_h)

    # Suprimir ruído de bibliotecas
    for noisy in ("urllib3", "PIL", "filelock", "trafilatura", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
