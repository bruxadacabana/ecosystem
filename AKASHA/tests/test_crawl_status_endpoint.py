"""Fase 3 — `GET /library/crawl/status` enriquecido (fonte HTTP de status p/ o HUB).

O endpoint mescla o estado do crawl (`paused`) com o estado do knowledge worker
(`get_status()`) e `semantic_available` (embed-server do LOGOS alcançável). É
resiliente: falha em qualquer fonte não derruba o endpoint.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_AKASHA_ROOT = Path(__file__).parent.parent
if str(_AKASHA_ROOT) not in sys.path:
    sys.path.insert(0, str(_AKASHA_ROOT))

import routers.crawler as cr  # noqa: E402
import services.knowledge_worker as kw  # noqa: E402
import services.local_search as ls  # noqa: E402

_WORKER = {
    "knowledge_extraction": 3,
    "knowledge_queue_high": 1,
    "knowledge_queue_low": 2,
    "worker_active": True,
    "processed_session": 7,
    "backfill_running": False,
}


def _call() -> dict:
    return asyncio.run(cr.crawl_status_api())


@pytest.fixture
def _patch(monkeypatch):
    """Defaults sãos; cada teste sobrescreve o que precisa."""
    monkeypatch.setattr(cr, "is_crawl_paused", lambda: False)
    monkeypatch.setattr(kw, "get_status", lambda: dict(_WORKER))
    monkeypatch.setattr(ls, "get_inference_status", lambda: True)
    return monkeypatch


def test_inclui_campos_do_worker(_patch):
    r = _call()
    assert r["paused"] is False
    assert r["knowledge_extraction"] == 3
    assert r["worker_active"] is True
    assert r["backfill_running"] is False
    assert r["processed_session"] == 7
    assert r["semantic_available"] is True


def test_paused_reflete_o_flag(_patch):
    _patch.setattr(cr, "is_crawl_paused", lambda: True)
    assert _call()["paused"] is True


def test_semantic_indisponivel_quando_inferencia_offline(_patch):
    _patch.setattr(ls, "get_inference_status", lambda: False)
    r = _call()
    assert r["semantic_available"] is False
    # os demais campos seguem presentes
    assert r["knowledge_extraction"] == 3


def test_resiliente_a_falha_do_worker(_patch):
    def _boom():
        raise RuntimeError("worker indisponível")
    _patch.setattr(kw, "get_status", _boom)
    r = _call()
    # não quebra: ainda devolve paused + semantic_available (defaults)
    assert r["paused"] is False
    assert r["semantic_available"] is True
    assert "knowledge_extraction" not in r


def test_resiliente_a_falha_da_inferencia(_patch):
    def _boom():
        raise RuntimeError("local_search indisponível")
    _patch.setattr(ls, "get_inference_status", _boom)
    r = _call()
    assert r["semantic_available"] is False  # default mantido
    assert r["knowledge_extraction"] == 3    # worker ainda presente
    assert r["paused"] is False
