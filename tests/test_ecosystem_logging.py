"""
Testes para ecosystem_logging.py.

Cobre:
  - setup_ecosystem_logger(): cria arquivo de log, configura handlers corretos
  - Idempotência: segunda chamada não duplica handlers
  - propagate=False: não duplica entradas no root logger
  - default_log_dir(): retorna caminho baseado em XDG_DATA_HOME ou home
"""
from __future__ import annotations
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import ecosystem_logging as el


# ─── Fixture: diretório temporário isolado por teste ─────────────────────────

@pytest.fixture(autouse=True)
def clean_logger(tmp_path):
    """Garante que o logger de teste começa sem handlers entre testes."""
    name = "ecosystem.test_logger"
    logger = logging.getLogger(name)
    # Remove handlers do teste anterior
    for h in list(logger.handlers):
        h.close()
        logger.removeHandler(h)
    logger.propagate = True
    yield tmp_path
    # Cleanup após cada teste
    for h in list(logger.handlers):
        h.close()
        logger.removeHandler(h)


# ─── setup_ecosystem_logger ───────────────────────────────────────────────────

def test_setup_creates_log_file(clean_logger):
    """Deve criar o arquivo de log no diretório especificado."""
    log_dir = clean_logger / "logs"
    el.setup_ecosystem_logger("ecosystem.test_logger", log_dir)

    log_file = log_dir / "ecosystem_test_logger.log"
    assert log_file.exists(), f"Arquivo de log não criado: {log_file}"


def test_setup_rotating_handler_config(clean_logger):
    """RotatingFileHandler deve ter 10 MB e 5 backups."""
    logger = el.setup_ecosystem_logger("ecosystem.test_logger", clean_logger)

    file_handlers = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
    assert len(file_handlers) == 1, "Deve existir exatamente 1 RotatingFileHandler"

    fh = file_handlers[0]
    assert fh.maxBytes    == 10 * 1024 * 1024, "maxBytes deve ser 10 MB"
    assert fh.backupCount == 5,                "backupCount deve ser 5"


def test_setup_has_console_handler(clean_logger):
    """Deve existir um StreamHandler além do RotatingFileHandler."""
    logger = el.setup_ecosystem_logger("ecosystem.test_logger", clean_logger)

    stream_handlers = [
        h for h in logger.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
    ]
    assert len(stream_handlers) == 1, "Deve existir exatamente 1 StreamHandler"


def test_setup_idempotent(clean_logger):
    """Chamadas repetidas não devem adicionar handlers duplicados."""
    el.setup_ecosystem_logger("ecosystem.test_logger", clean_logger)
    el.setup_ecosystem_logger("ecosystem.test_logger", clean_logger)
    el.setup_ecosystem_logger("ecosystem.test_logger", clean_logger)

    logger = logging.getLogger("ecosystem.test_logger")
    assert len(logger.handlers) == 2, (
        f"Deve ter exatamente 2 handlers (file + console), mas tem {len(logger.handlers)}"
    )


def test_setup_returns_named_logger(clean_logger):
    """Deve retornar um logger com o nome especificado."""
    logger = el.setup_ecosystem_logger("ecosystem.test_logger", clean_logger)
    assert logger.name == "ecosystem.test_logger"


def test_setup_propagate_false(clean_logger):
    """propagate=False evita duplicação de entradas no root logger."""
    logger = el.setup_ecosystem_logger("ecosystem.test_logger", clean_logger)
    assert logger.propagate is False


def test_setup_creates_dir_if_missing(tmp_path):
    """Deve criar o diretório de log se ele não existir."""
    nested = tmp_path / "a" / "b" / "c" / "logs"
    assert not nested.exists()

    logger = logging.getLogger("ecosystem.test_dir_creation")
    for h in list(logger.handlers):
        h.close()
        logger.removeHandler(h)

    el.setup_ecosystem_logger("ecosystem.test_dir_creation", nested)

    assert nested.exists(), "Diretório de log deve ser criado"

    # Cleanup
    for h in list(logger.handlers):
        h.close()
        logger.removeHandler(h)


def test_setup_logger_level_debug(clean_logger):
    """O logger deve aceitar mensagens DEBUG (nível mínimo)."""
    logger = el.setup_ecosystem_logger("ecosystem.test_logger", clean_logger)
    assert logger.level == logging.DEBUG


def test_setup_file_handler_level_debug(clean_logger):
    """O RotatingFileHandler deve registrar a partir de DEBUG."""
    logger = el.setup_ecosystem_logger("ecosystem.test_logger", clean_logger)
    fh = next(h for h in logger.handlers if isinstance(h, RotatingFileHandler))
    assert fh.level == logging.DEBUG


def test_setup_console_handler_level_info(clean_logger):
    """O StreamHandler deve filtrar mensagens abaixo de INFO."""
    logger = el.setup_ecosystem_logger("ecosystem.test_logger", clean_logger)
    sh = next(
        h for h in logger.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
    )
    assert sh.level == logging.INFO


# ─── default_log_dir ─────────────────────────────────────────────────────────

def test_default_log_dir_uses_xdg(monkeypatch):
    """Quando XDG_DATA_HOME está definido, usa-o como base."""
    monkeypatch.setenv("XDG_DATA_HOME", "/custom/data")
    result = el.default_log_dir()
    assert str(result) == "/custom/data/ecosystem/logs"


def test_default_log_dir_fallback_to_home(monkeypatch):
    """Sem XDG_DATA_HOME, usa ~/.local/share/ecosystem/logs."""
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    result = el.default_log_dir()
    expected = Path.home() / ".local" / "share" / "ecosystem" / "logs"
    assert result == expected
