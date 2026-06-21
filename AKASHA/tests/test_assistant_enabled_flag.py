"""Fase 2 — flag `akasha.assistant_enabled` (modo só-ferramenta).

Quando False (deploy headless no T410), o `lifespan` do main.py NÃO inicia os loops
da assistente (persona/reflexão/insights/observer/sugestão de domínio) — só a
ferramenta roda. Default True → PC principal mantém o comportamento atual.

A decisão mora em `config.should_run_assistant_loops()` (lido de `config.ASSISTANT_ENABLED`,
derivado do ecosystem.json no import). O `lifespan` apenas faz `if ...:` em cima dela.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_AKASHA_ROOT = Path(__file__).parent.parent
if str(_AKASHA_ROOT) not in sys.path:
    sys.path.insert(0, str(_AKASHA_ROOT))


def _reload_config_with_eco(monkeypatch, eco: dict):
    """Recarrega config.py com um ecosystem.json simulado (recomputa ASSISTANT_ENABLED)."""
    import ecosystem_client
    monkeypatch.setattr(ecosystem_client, "read_ecosystem", lambda: eco)
    import config
    importlib.reload(config)
    return config


@pytest.fixture(autouse=True)
def _restore_config():
    """Recarrega config com o ecosystem.json real após cada teste (sem vazar estado)."""
    yield
    import config
    importlib.reload(config)


def test_default_true_quando_chave_ausente(monkeypatch):
    config = _reload_config_with_eco(monkeypatch, {"akasha": {}})
    assert config.ASSISTANT_ENABLED is True
    assert config.should_run_assistant_loops() is True


def test_default_true_quando_secao_akasha_ausente(monkeypatch):
    config = _reload_config_with_eco(monkeypatch, {})
    assert config.ASSISTANT_ENABLED is True
    assert config.should_run_assistant_loops() is True


def test_flag_false_desliga(monkeypatch):
    config = _reload_config_with_eco(monkeypatch, {"akasha": {"assistant_enabled": False}})
    assert config.ASSISTANT_ENABLED is False
    assert config.should_run_assistant_loops() is False


def test_flag_true_explicito(monkeypatch):
    config = _reload_config_with_eco(monkeypatch, {"akasha": {"assistant_enabled": True}})
    assert config.ASSISTANT_ENABLED is True
    assert config.should_run_assistant_loops() is True


def test_helper_segue_o_atributo_do_modulo(monkeypatch):
    """O helper lê o atributo do módulo em tempo de chamada (monkeypatch reflete)."""
    config = _reload_config_with_eco(monkeypatch, {"akasha": {}})
    monkeypatch.setattr(config, "ASSISTANT_ENABLED", False)
    assert config.should_run_assistant_loops() is False
    monkeypatch.setattr(config, "ASSISTANT_ENABLED", True)
    assert config.should_run_assistant_loops() is True
