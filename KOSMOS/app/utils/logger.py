"""Configuração centralizada do logger do KOSMOS."""

from __future__ import annotations

import logging
from pathlib import Path

from app.utils.paths import Paths


def setup_logger(level: int = logging.INFO) -> None:
    """Configura o logging para arquivo e stderr.

    Args:
        level: nível de log (padrão: INFO).
    """
    log_file: Path = Paths.LOGS / "kosmos.log"

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    # Reduzir ruído de bibliotecas de terceiros
    for noisy_lib in ("feedparser", "urllib3", "requests", "PIL", "matplotlib"):
        logging.getLogger(noisy_lib).setLevel(logging.WARNING)
