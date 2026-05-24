"""
Testes pós-migração Ollama → llama-server (OpenAI-compatível) nos serviços AKASHA.

Verifica que _call_inference / _call_inference_reflect em cada serviço:
  - Chama /v1/chat/completions (NÃO /api/generate nem /api/chat)
  - Payload usa campos OpenAI: messages, max_tokens, temperature (sem options/format/keep_alive)
  - Extrai conteúdo de choices[0].message.content (NÃO de response ou message.content Ollama)
  - Retorna None em erro HTTP / timeout / formato inesperado

Serviços cobertos:
  - services/reflection_loop.py  → _call_inference
  - services/session_memory.py   → _call_inference_reflect
  - services/session_insight.py  → _generate (camada HTTP)
  - services/persona.py          → rebuild_persona (camada HTTP)
"""
from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _openai_resp(content: str) -> MagicMock:
    """Mock httpx.Response com formato OpenAI-compatível."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": content}}]
    }
    return resp


def _ollama_resp(content: str) -> MagicMock:
    """Mock httpx.Response com formato Ollama antigo (deve ser ignorado/parsear errado)."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"response": content}  # /api/generate Ollama format
    return resp


def _mock_httpx_client(resp: MagicMock) -> MagicMock:
    """Mock de httpx.AsyncClient como context manager."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, mock_client


# ---------------------------------------------------------------------------
# reflection_loop._call_inference
# ---------------------------------------------------------------------------

def test_reflection_loop_calls_v1_chat_completions():
    """_call_inference deve chamar /v1/chat/completions, não /api/generate."""
    import services.reflection_loop as rl
    cm, mock_client = _mock_httpx_client(_openai_resp("Reflexão profunda sobre os dados."))
    with patch("httpx.AsyncClient", return_value=cm):
        with patch.object(rl, "_get_inference_base", return_value="http://localhost:7072"):
            result = _run(rl._call_inference("prompt de reflexão", "smollm2:1.7b"))
    assert result == "Reflexão profunda sobre os dados."
    called_url = mock_client.post.call_args[0][0]
    assert "/v1/chat/completions" in called_url
    assert "/api/generate" not in called_url
    assert "/api/chat" not in called_url


def test_reflection_loop_payload_openai_format():
    """Payload de _call_inference deve ter messages/max_tokens, sem campos Ollama."""
    import services.reflection_loop as rl
    cm, mock_client = _mock_httpx_client(_openai_resp("Texto de reflexão válido."))
    with patch("httpx.AsyncClient", return_value=cm):
        with patch.object(rl, "_get_inference_base", return_value="http://localhost:7072"):
            _run(rl._call_inference("um prompt", "smollm2:1.7b"))
    payload = mock_client.post.call_args[1]["json"]
    assert "messages" in payload
    assert "max_tokens" in payload
    assert "temperature" in payload
    assert "options" not in payload
    assert "format" not in payload
    assert "keep_alive" not in payload
    assert "prompt" not in payload  # campo /api/generate Ollama


def test_reflection_loop_returns_none_on_ollama_format():
    """Se a resposta for formato Ollama (sem choices), _call_inference retorna None."""
    import services.reflection_loop as rl
    cm, _ = _mock_httpx_client(_ollama_resp("algum texto"))
    with patch("httpx.AsyncClient", return_value=cm):
        with patch.object(rl, "_get_inference_base", return_value="http://localhost:7072"):
            result = _run(rl._call_inference("prompt", "smollm2:1.7b"))
    assert result is None


def test_reflection_loop_returns_none_on_http_error():
    """_call_inference retorna None em erro de conexão."""
    import services.reflection_loop as rl
    import httpx
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", return_value=cm):
        with patch.object(rl, "_get_inference_base", return_value="http://localhost:7072"):
            result = _run(rl._call_inference("prompt", "smollm2:1.7b"))
    assert result is None


# ---------------------------------------------------------------------------
# session_memory._call_inference_reflect
# ---------------------------------------------------------------------------

def test_session_memory_calls_v1_chat_completions():
    """_call_inference_reflect deve chamar /v1/chat/completions."""
    import services.session_memory as sm
    cm, mock_client = _mock_httpx_client(_openai_resp("Sessão revelou interesse crescente em privacidade."))
    with patch("httpx.AsyncClient", return_value=cm):
        with patch.object(sm, "_get_inference_base", return_value="http://localhost:7072"):
            result = _run(sm._call_inference_reflect("prompt reflexão sessão", "smollm2:1.7b"))
    assert result == "Sessão revelou interesse crescente em privacidade."
    called_url = mock_client.post.call_args[0][0]
    assert "/v1/chat/completions" in called_url
    assert "/api/generate" not in called_url


def test_session_memory_payload_openai_format():
    """Payload de _call_inference_reflect sem campos Ollama."""
    import services.session_memory as sm
    cm, mock_client = _mock_httpx_client(_openai_resp("Reflexão válida aqui."))
    with patch("httpx.AsyncClient", return_value=cm):
        with patch.object(sm, "_get_inference_base", return_value="http://localhost:7072"):
            _run(sm._call_inference_reflect("prompt", "smollm2:1.7b"))
    payload = mock_client.post.call_args[1]["json"]
    assert "messages" in payload
    assert payload["stream"] is False
    assert "max_tokens" in payload
    assert "options" not in payload
    assert "prompt" not in payload


def test_session_memory_returns_none_on_ollama_format():
    """Formato Ollama sem choices → retorna None."""
    import services.session_memory as sm
    cm, _ = _mock_httpx_client(_ollama_resp("resposta ollama"))
    with patch("httpx.AsyncClient", return_value=cm):
        with patch.object(sm, "_get_inference_base", return_value="http://localhost:7072"):
            result = _run(sm._call_inference_reflect("prompt", "smollm2:1.7b"))
    assert result is None


def test_session_memory_returns_none_on_timeout():
    """_call_inference_reflect retorna None em timeout."""
    import services.session_memory as sm
    import httpx
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", return_value=cm):
        with patch.object(sm, "_get_inference_base", return_value="http://localhost:7072"):
            result = _run(sm._call_inference_reflect("prompt", "smollm2:1.7b"))
    assert result is None


# ---------------------------------------------------------------------------
# session_insight — camada HTTP de _generate
# ---------------------------------------------------------------------------

def test_session_insight_generate_calls_v1_chat_completions(monkeypatch):
    """_generate deve chamar /v1/chat/completions para gerar insight."""
    import services.session_insight as si

    cm, mock_client = _mock_httpx_client(_openai_resp(
        "Parece que você está explorando privacidade digital com intensidade."
    ))

    mock_config = types.ModuleType("config")
    mock_config.PERSONALITY_PROMPT = "Você é Akasha, sistema de busca pessoal."

    with patch.dict(sys.modules, {"config": mock_config}):
        with patch("httpx.AsyncClient", return_value=cm):
            with patch.object(si, "_get_inference_base", return_value="http://localhost:7072"):
                with patch.object(si, "_get_model", return_value="smollm2:1.7b"):
                    with patch("services.personal_memory.save_memory", new_callable=AsyncMock) as mock_save:
                        mock_save.return_value = 1
                        _run(si._generate("sess-001", ["privacidade", "VPN", "rastreamento"], ["trecho 1"]))

    called_url = mock_client.post.call_args[0][0]
    assert "/v1/chat/completions" in called_url
    assert "/api/generate" not in called_url


def test_session_insight_generate_payload_no_ollama_fields(monkeypatch):
    """Payload de _generate não deve ter campos Ollama (options, format, keep_alive)."""
    import services.session_insight as si

    cm, mock_client = _mock_httpx_client(_openai_resp(
        "Exploração consistente de tópicos de segurança e privacidade digital."
    ))
    mock_config = types.ModuleType("config")
    mock_config.PERSONALITY_PROMPT = "Akasha."

    with patch.dict(sys.modules, {"config": mock_config}):
        with patch("httpx.AsyncClient", return_value=cm):
            with patch.object(si, "_get_inference_base", return_value="http://localhost:7072"):
                with patch.object(si, "_get_model", return_value="smollm2:1.7b"):
                    with patch("services.personal_memory.save_memory", new_callable=AsyncMock, return_value=1):
                        _run(si._generate("sess-001", ["privacidade", "VPN"], ["trecho"]))

    payload = mock_client.post.call_args[1]["json"]
    assert "messages" in payload
    assert "options" not in payload
    assert "keep_alive" not in payload
    assert "format" not in payload


# ---------------------------------------------------------------------------
# persona.rebuild_persona — camada HTTP
# ---------------------------------------------------------------------------

def test_persona_rebuild_calls_v1_chat_completions(monkeypatch):
    """_rebuild_persona deve chamar /v1/chat/completions para gerar self_description."""
    import services.persona as persona

    cm, mock_client = _mock_httpx_client(_openai_resp(
        "Sou um sistema de busca focado em privacidade e tecnologia."
    ))

    mock_db = types.ModuleType("database")
    mock_db.get_top_topics = AsyncMock(return_value=[("privacidade", 10), ("segurança", 8)])
    mock_db.set_profile_value = AsyncMock()

    with patch.dict(sys.modules, {"database": mock_db}):
        with patch("httpx.AsyncClient", return_value=cm):
            with patch.object(persona, "_get_inference_base", return_value="http://localhost:7072"):
                with patch.object(persona, "_get_model", return_value="smollm2:1.7b"):
                    _run(persona._rebuild_persona())

    called_url = mock_client.post.call_args[0][0]
    assert "/v1/chat/completions" in called_url
    assert "/api/generate" not in called_url


def test_persona_rebuild_payload_openai_format(monkeypatch):
    """Payload de _rebuild_persona sem campos Ollama."""
    import services.persona as persona

    cm, mock_client = _mock_httpx_client(_openai_resp(
        "Sou um sistema de busca focado em privacidade e tecnologia."
    ))
    mock_db = types.ModuleType("database")
    mock_db.get_top_topics = AsyncMock(return_value=[("privacidade", 10), ("segurança", 8)])
    mock_db.set_profile_value = AsyncMock()

    with patch.dict(sys.modules, {"database": mock_db}):
        with patch("httpx.AsyncClient", return_value=cm):
            with patch.object(persona, "_get_inference_base", return_value="http://localhost:7072"):
                with patch.object(persona, "_get_model", return_value="smollm2:1.7b"):
                    _run(persona._rebuild_persona())

    payload = mock_client.post.call_args[1]["json"]
    assert "messages" in payload
    assert "max_tokens" in payload
    assert "options" not in payload
    assert "prompt" not in payload


def test_persona_rebuild_extracts_openai_content(monkeypatch):
    """_rebuild_persona usa choices[0].message.content, não campo 'response' Ollama."""
    import services.persona as persona

    expected = "Sou Akasha, focada em privacidade e sistemas distribuídos."
    cm, _ = _mock_httpx_client(_openai_resp(expected))
    mock_db = types.ModuleType("database")
    mock_db.get_top_topics = AsyncMock(return_value=[("privacidade", 10), ("sistemas", 8)])
    mock_db.set_profile_value = AsyncMock()

    with patch.dict(sys.modules, {"database": mock_db}):
        with patch("httpx.AsyncClient", return_value=cm):
            with patch.object(persona, "_get_inference_base", return_value="http://localhost:7072"):
                with patch.object(persona, "_get_model", return_value="smollm2:1.7b"):
                    _run(persona._rebuild_persona())

    calls = {c.args[0]: c.args[1] for c in mock_db.set_profile_value.call_args_list}
    assert calls.get("persona_description") == expected


def test_persona_rebuild_skips_when_no_model():
    """_rebuild_persona retorna silenciosamente se nenhum modelo configurado."""
    import services.persona as persona
    mock_db = types.ModuleType("database")
    mock_db.get_top_topics = AsyncMock(return_value=[("privacidade", 10)])
    mock_db.set_profile_value = AsyncMock()

    with patch.dict(sys.modules, {"database": mock_db}):
        with patch.object(persona, "_get_model", return_value=""):
            _run(persona._rebuild_persona())  # não deve levantar

    mock_db.set_profile_value.assert_not_called()
