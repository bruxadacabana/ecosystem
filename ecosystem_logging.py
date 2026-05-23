"""
ecosystem_logging — utilitário de logging compartilhado do ecossistema.

Fornece setup_ecosystem_logger(name, log_dir) para módulos utilitários como
vram_monitor e logits_worker que precisam de logging persistente independente
do logger raiz do processo principal que os importa.

Padrão de uso:
    from pathlib import Path
    from ecosystem_logging import setup_ecosystem_logger
    log = setup_ecosystem_logger("ecosystem.meu_modulo", Path("~/.local/share/ecosystem/logs"))
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FMT          = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATEFMT      = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES    = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5

# Bibliotecas com logging excessivo — silenciadas por padrão
_NOISY_LIBS = ("urllib3", "PIL", "filelock", "trafilatura", "charset_normalizer", "httpx")


def setup_ecosystem_logger(name: str, log_dir: Path) -> logging.Logger:
    """Configura e retorna um logger nomeado com RotatingFileHandler (10 MB, 5 backups).

    Idempotente: chamadas subsequentes com o mesmo nome retornam o logger já
    configurado sem adicionar handlers duplicados.

    O arquivo de log é criado em {log_dir}/{name_sanitized}.log
    onde name_sanitized substitui '.' por '_' (ex: "ecosystem.vram_monitor" →
    "ecosystem_vram_monitor.log").

    propagate=False garante que entradas não sejam duplicadas caso o root logger
    também tenha handlers (ex: quando importado por AKASHA ou Mnemosyne que já
    configuram seu próprio logging).
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # já configurado — não duplicar

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    log_dir = Path(log_dir).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace(".", "_")
    log_path  = log_dir / f"{safe_name}.log"

    fmt = logging.Formatter(_FMT, _DATEFMT)

    file_h = RotatingFileHandler(
        log_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_h.setLevel(logging.DEBUG)
    file_h.setFormatter(fmt)

    console_h = logging.StreamHandler()
    console_h.setLevel(logging.INFO)
    console_h.setFormatter(fmt)

    logger.addHandler(file_h)
    logger.addHandler(console_h)

    for noisy in _NOISY_LIBS:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return logger


def default_log_dir() -> Path:
    """Retorna o diretório de logs padrão do ecossistema (~/.local/share/ecosystem/logs)."""
    import os
    xdg = os.environ.get("XDG_DATA_HOME", "")
    if xdg:
        return Path(xdg) / "ecosystem" / "logs"
    return Path.home() / ".local" / "share" / "ecosystem" / "logs"
