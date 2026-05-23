"""
Testes para logos/dispatcher.py.

Cobre:
  - _get_embedding(): chama /v1/embeddings (OpenAI), extrai embedding corretamente
  - _get_embedding(): retorna None em caso de falha HTTP ou formato inválido
  - _llm_route(): chama /v1/chat/completions, parseia resposta OpenAI corretamente
  - _llm_route(): payload usa response_format json_object (não format/keep_alive Ollama)
  - _llm_route(): fallback para _FALLBACK_SKILL se confiança baixa
  - _llm_route(): fallback em timeout/HTTP error
  - _keyword_route(): cobre os principais padrões regex
  - dispatch(): fallback imediato se não há skills carregados
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


def _make_openai_embed_response(embedding: list[float]) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"data": [{"embedding": embedding, "index": 0}]}
    return resp


def _make_openai_chat_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": content}}]
    }
    return resp


def _mock_async_client(mock_client):
    """Retorna context manager que entrega mock_client no __aenter__."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__  = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# _get_embedding
# ---------------------------------------------------------------------------

def test_get_embedding_calls_v1_embeddings():
    """_get_embedding deve chamar /v1/embeddings (não /api/embed)."""
    from logos.dispatcher import _get_embedding

    vec = [0.1, 0.2, 0.3]
    resp = _make_openai_embed_response(vec)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=resp)

    with patch("httpx.AsyncClient", return_value=_mock_async_client(mock_client)):
        result = _run(_get_embedding("hello world", "http://localhost:7072", "nomic-embed-text"))

    assert result == vec
    called_url = mock_client.post.call_args[0][0]
    assert "/v1/embeddings" in called_url
    assert "/api/embed" not in called_url


def test_get_embedding_returns_none_on_http_error():
    """_get_embedding retorna None se a requisição falhar."""
    from logos.dispatcher import _get_embedding

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch("httpx.AsyncClient", return_value=_mock_async_client(mock_client)):
        result = _run(_get_embedding("hello", "http://localhost:7072", "nomic-embed-text"))

    assert result is None


def test_get_embedding_returns_none_on_wrong_format():
    """_get_embedding retorna None se a resposta não tiver data[0].embedding."""
    from logos.dispatcher import _get_embedding

    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"embeddings": [[0.1, 0.2]]}  # formato Ollama antigo

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=resp)

    with patch("httpx.AsyncClient", return_value=_mock_async_client(mock_client)):
        result = _run(_get_embedding("hello", "http://localhost:7072", "nomic-embed-text"))

    assert result is None


# ---------------------------------------------------------------------------
# _llm_route
# ---------------------------------------------------------------------------

def test_llm_route_calls_v1_chat_completions(monkeypatch):
    """_llm_route deve chamar /v1/chat/completions (não /api/chat)."""
    import logos.dispatcher as d
    monkeypatch.setattr(d, "_SKILLS", {"synthesis": {"description": "Resumo", "system_prompt": ""}})

    content = json.dumps({"skill": "synthesis", "confidence": 0.95})
    resp = _make_openai_chat_response(content)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=resp)

    with patch("httpx.AsyncClient", return_value=_mock_async_client(mock_client)):
        result = _run(d._llm_route("resume this text", "smollm2:1.7b", "http://localhost:7072"))

    assert result.skill == "synthesis"
    assert result.tier == "llm"
    called_url = mock_client.post.call_args[0][0]
    assert "/v1/chat/completions" in called_url
    assert "/api/chat" not in called_url


def test_llm_route_uses_response_format_json_object(monkeypatch):
    """Payload deve ter response_format:{type:json_object} e não campos Ollama."""
    import logos.dispatcher as d
    monkeypatch.setattr(d, "_SKILLS", {"synthesis": {"description": "Resumo", "system_prompt": ""}})

    content = json.dumps({"skill": "synthesis", "confidence": 0.9})
    resp = _make_openai_chat_response(content)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=resp)

    with patch("httpx.AsyncClient", return_value=_mock_async_client(mock_client)):
        _run(d._llm_route("some request", "router:3b", "http://localhost:7072"))

    payload = mock_client.post.call_args[1]["json"]
    assert payload.get("response_format") == {"type": "json_object"}
    assert "format" not in payload        # campo Ollama não deve existir
    assert "keep_alive" not in payload    # campo Ollama não deve existir
    assert "options" not in payload       # campo Ollama não deve existir
    assert "temperature" in payload
    assert "max_tokens" in payload


def test_llm_route_fallback_on_low_confidence(monkeypatch):
    """_llm_route deve retornar fallback se confiança < threshold."""
    import logos.dispatcher as d
    monkeypatch.setattr(d, "_SKILLS", {"synthesis": {"description": "Resumo", "system_prompt": ""}})
    monkeypatch.setattr(d, "_FALLBACK_SKILL", "synthesis")
    monkeypatch.setattr(d, "_CONFIDENCE_THRESHOLD", 0.7)

    content = json.dumps({"skill": "synthesis", "confidence": 0.3})
    resp = _make_openai_chat_response(content)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=resp)

    with patch("httpx.AsyncClient", return_value=_mock_async_client(mock_client)):
        result = _run(d._llm_route("vague request", "router:3b", "http://localhost:7072"))

    assert result.tier == "fallback"
    assert result.confidence == 0.3


def test_llm_route_fallback_on_timeout(monkeypatch):
    """_llm_route deve retornar fallback em timeout."""
    import logos.dispatcher as d
    monkeypatch.setattr(d, "_SKILLS", {"synthesis": {"description": "Resumo", "system_prompt": ""}})

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("httpx.AsyncClient", return_value=_mock_async_client(mock_client)):
        result = _run(d._llm_route("some request", "router:3b", "http://localhost:7072"))

    assert result.tier == "fallback"
    assert result.confidence == 0.0


def test_llm_route_parses_openai_response_format(monkeypatch):
    """_llm_route deve ler choices[0].message.content (não message.content Ollama)."""
    import logos.dispatcher as d
    monkeypatch.setattr(d, "_SKILLS", {"synthesis": {"description": "Resumo", "system_prompt": ""}})

    content = json.dumps({"skill": "synthesis", "confidence": 0.85})
    # Resposta OpenAI — não Ollama (que seria {"message": {"content": "..."}})
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 20}
    }
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=resp)

    with patch("httpx.AsyncClient", return_value=_mock_async_client(mock_client)):
        result = _run(d._llm_route("sumario", "router:3b", "http://localhost:7072"))

    assert result.skill == "synthesis"
    assert result.confidence == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# _keyword_route
# ---------------------------------------------------------------------------

def test_keyword_route_synthesis(monkeypatch):
    import logos.dispatcher as d
    monkeypatch.setattr(d, "_SKILLS", {"synthesis": {"description": "", "system_prompt": ""}})
    result = d._keyword_route("resuma esse artigo para mim")
    assert result is not None
    assert result.skill == "synthesis"
    assert result.tier == "keyword"
    assert result.confidence == 1.0


def test_keyword_route_rag_query(monkeypatch):
    import logos.dispatcher as d
    monkeypatch.setattr(d, "_SKILLS", {"rag-query": {"description": "", "system_prompt": ""}})
    result = d._keyword_route("nos meus documentos tem algo sobre kafka?")
    assert result is not None
    assert result.skill == "rag-query"


def test_keyword_route_no_match_returns_none():
    from logos.dispatcher import _keyword_route
    result = _keyword_route("o que é fotossíntese?")
    assert result is None


# ---------------------------------------------------------------------------
# dispatch() — smoke test sem skills carregados
# ---------------------------------------------------------------------------

def test_dispatch_fallback_if_no_skills(monkeypatch):
    """dispatch() retorna fallback imediatamente se não há skills carregados."""
    import logos.dispatcher as d
    monkeypatch.setattr(d, "_SKILLS", {})
    monkeypatch.setattr(d, "_FALLBACK_SKILL", "synthesis")

    result = _run(d.dispatch("qualquer coisa"))
    assert result.skill == "synthesis"
    assert result.tier == "fallback"
