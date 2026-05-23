"""
Testes para gc_with_reflection e reflect_on_session em services/session_memory.py.

Cobre:
  - gc_with_reflection: sessão expirada com ≥3 queries → dispara reflect_on_session
  - gc_with_reflection: sessão expirada com <3 queries → NÃO dispara reflexão
  - gc_with_reflection: sessão ativa não é removida
  - _is_meaningful_reflection: respostas genéricas/curtas são descartadas
  - reflect_on_session: sem modelo configurado → retorna sem chamar save_memory
  - reflect_on_session: Ollama responde → save_memory chamado com tag correta
  - reflect_on_session: resposta genérica → save_memory NÃO chamado
"""
from __future__ import annotations
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── _is_meaningful_reflection ───────────────────────────────────────────────

def test_meaningful_normal_text():
    from services.session_memory import _is_meaningful_reflection
    assert _is_meaningful_reflection("Interessante conexão entre tópicos de ML e privacidade.") is True


def test_meaningful_rejects_short():
    from services.session_memory import _is_meaningful_reflection
    assert _is_meaningful_reflection("ok") is False


def test_meaningful_rejects_nada():
    from services.session_memory import _is_meaningful_reflection
    assert _is_meaningful_reflection("nada.") is False
    assert _is_meaningful_reflection("nada") is False


def test_meaningful_rejects_generic_prefix():
    from services.session_memory import _is_meaningful_reflection
    assert _is_meaningful_reflection("Não posso gerar reflexões sobre isso.") is False
    assert _is_meaningful_reflection("Desculpe, não tenho dados suficientes.") is False


# ─── gc_with_reflection ───────────────────────────────────────────────────────

def test_gc_triggers_reflection_for_expired_with_enough_queries():
    """Sessão expirada com ≥3 queries → reflect_on_session é agendada."""
    from services import session_memory as sm

    # Inserir sessão artificialmente expirada
    entry = sm.SessionEntry(
        queries=["busca um", "busca dois", "busca tres"],
        last_at=time.time() - sm.SESSION_TTL_S - 10,
    )
    sid = "test-session-gc-ok"
    sm._sessions[sid] = entry

    tasks_scheduled: list = []

    async def run():
        with patch("asyncio.create_task", side_effect=tasks_scheduled.append) as _mk:
            removed = await sm.gc_with_reflection()
        return removed

    removed = asyncio.get_event_loop().run_until_complete(run())

    assert removed >= 1
    assert sid not in sm._sessions
    assert len(tasks_scheduled) >= 1  # reflect_on_session foi agendada


def test_gc_no_reflection_for_expired_with_too_few_queries():
    """Sessão expirada com <3 queries → NÃO dispara reflexão."""
    from services import session_memory as sm

    entry = sm.SessionEntry(
        queries=["só uma query"],
        last_at=time.time() - sm.SESSION_TTL_S - 10,
    )
    sid = "test-session-gc-few"
    sm._sessions[sid] = entry

    tasks_scheduled: list = []

    async def run():
        with patch("asyncio.create_task", side_effect=tasks_scheduled.append):
            removed = await sm.gc_with_reflection()
        return removed

    removed = asyncio.get_event_loop().run_until_complete(run())

    assert removed >= 1
    assert len(tasks_scheduled) == 0


def test_gc_does_not_remove_active_session():
    """Sessão ativa não é removida pelo GC."""
    from services import session_memory as sm

    entry = sm.SessionEntry(
        queries=["query recente"],
        last_at=time.time(),  # ativa
    )
    sid = "test-session-gc-active"
    sm._sessions[sid] = entry

    async def run():
        return await sm.gc_with_reflection()

    asyncio.get_event_loop().run_until_complete(run())
    assert sid in sm._sessions

    # cleanup
    del sm._sessions[sid]


# ─── reflect_on_session ───────────────────────────────────────────────────────

def test_reflect_no_model_returns_silently():
    """Sem modelo configurado → retorna sem chamar save_memory."""
    from services import session_memory as sm

    async def run():
        with patch.object(sm, "_get_reflect_model", return_value=""):
            with patch("services.personal_memory.save_memory", new_callable=AsyncMock) as mock_save:
                await sm.reflect_on_session(["query a", "query b", "query c"])
                mock_save.assert_not_called()

    asyncio.get_event_loop().run_until_complete(run())


def test_reflect_saves_when_ollama_responds():
    """Resposta válida → save_memory chamado com tag 'session_reflection'."""
    from services import session_memory as sm

    async def run():
        with patch.object(sm, "_get_reflect_model", return_value="mistral"):
            with patch.object(sm, "_call_inference_reflect", new_callable=AsyncMock,
                              return_value="Parece que o interesse em privacidade e ML se intensifica."):
                with patch("services.personal_memory.save_memory", new_callable=AsyncMock) as mock_save:
                    await sm.reflect_on_session(["privacidade", "machine learning", "dados pessoais"])
                    mock_save.assert_called_once()
                    call_kwargs = mock_save.call_args
                    tags = call_kwargs.kwargs.get("tags") or call_kwargs.args[2] if len(call_kwargs.args) > 2 else []
                    assert "session_reflection" in (call_kwargs.kwargs.get("tags", []) or [])

    asyncio.get_event_loop().run_until_complete(run())


def test_reflect_discards_generic_ollama_response():
    """Resposta genérica ('nada.') → save_memory NÃO chamado."""
    from services import session_memory as sm

    async def run():
        with patch.object(sm, "_get_reflect_model", return_value="mistral"):
            with patch.object(sm, "_call_inference_reflect", new_callable=AsyncMock,
                              return_value="nada."):
                with patch("services.personal_memory.save_memory", new_callable=AsyncMock) as mock_save:
                    await sm.reflect_on_session(["busca um", "busca dois", "busca tres"])
                    mock_save.assert_not_called()

    asyncio.get_event_loop().run_until_complete(run())
