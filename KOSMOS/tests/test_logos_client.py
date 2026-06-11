"""
Testes de app/core/logos_client.py — wrapper do KOSMOS sobre o LOGOS.

Cobre:
  - is_available: logos_status None → False; dict → True; exceção → False.
  - get_analysis_model: perfil com llm_analysis → retorna; perfil sem a chave ou
    None → fallback por hardware; exceção → "".
  - chat: resposta válida → conteúdo; RuntimeError (LOGOS offline/429) →
    LogosUnavailable; vazia / sem choices → LogosUnavailable; repassa priority,
    model, temperature e max_tokens corretos ao request_llm.

`ecosystem_client.*` é mockado (sem rede). `app.utils.paths` é importado primeiro
para configurar sys.path (resolve `ecosystem_client`).
"""
from __future__ import annotations

import app.utils.paths  # noqa: F401 — configura sys.path para ecosystem_client
import pytest
from unittest.mock import patch

from app.core.logos_client import (
    LogosUnavailable,
    chat,
    get_analysis_model,
    is_available,
)


def _resp(content):
    return {"choices": [{"message": {"content": content}}]}


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

def test_is_available_true_when_status_present():
    with patch("ecosystem_client.logos_status", return_value={"active_priority": None}):
        assert is_available() is True


def test_is_available_false_when_status_none():
    with patch("ecosystem_client.logos_status", return_value=None):
        assert is_available() is False


def test_is_available_false_on_exception():
    with patch("ecosystem_client.logos_status", side_effect=RuntimeError("boom")):
        assert is_available() is False


# ---------------------------------------------------------------------------
# get_analysis_model
# ---------------------------------------------------------------------------

def test_get_analysis_model_from_profile():
    prof = {"profile": "main_pc", "models": {"llm_analysis": "gemma2:2b"}}
    with patch("ecosystem_client.get_active_profile", return_value=prof):
        assert get_analysis_model() == "gemma2:2b"


def test_get_analysis_model_fallback_when_profile_none():
    with patch("ecosystem_client.get_active_profile", return_value=None), \
         patch("ecosystem_client._fallback_model_for_app", return_value="fallback:model") as fb:
        assert get_analysis_model() == "fallback:model"
        fb.assert_called_once_with("kosmos")


def test_get_analysis_model_fallback_when_key_missing():
    prof = {"profile": "main_pc", "models": {"llm_rag": "x"}}  # sem llm_analysis
    with patch("ecosystem_client.get_active_profile", return_value=prof), \
         patch("ecosystem_client._fallback_model_for_app", return_value="fb"):
        assert get_analysis_model() == "fb"


def test_get_analysis_model_empty_on_exception():
    with patch("ecosystem_client.get_active_profile", side_effect=RuntimeError("down")):
        assert get_analysis_model() == ""


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------

def test_chat_returns_content():
    with patch("ecosystem_client.request_llm", return_value=_resp("  análise pronta  ")):
        assert chat([{"role": "user", "content": "x"}], priority=3) == "análise pronta"


def test_chat_offline_raises_logos_unavailable():
    with patch("ecosystem_client.request_llm", side_effect=RuntimeError("offline")):
        with pytest.raises(LogosUnavailable):
            chat([{"role": "user", "content": "x"}], priority=1)


def test_chat_empty_content_raises():
    with patch("ecosystem_client.request_llm", return_value=_resp("   ")):
        with pytest.raises(LogosUnavailable):
            chat([{"role": "user", "content": "x"}], priority=3)


def test_chat_no_choices_raises():
    with patch("ecosystem_client.request_llm", return_value={"choices": []}):
        with pytest.raises(LogosUnavailable):
            chat([{"role": "user", "content": "x"}], priority=3)


def test_chat_passes_priority_model_and_options():
    msgs = [{"role": "user", "content": "x"}]
    with patch("ecosystem_client.request_llm", return_value=_resp("ok")) as ml:
        chat(msgs, priority=2, model="m1", temperature=0.1, max_tokens=512)
    _, kwargs = ml.call_args
    assert kwargs["app"] == "kosmos"
    assert kwargs["priority"] == 2
    assert kwargs["model"] == "m1"
    assert kwargs["temperature"] == 0.1
    assert kwargs["max_tokens"] == 512


def test_chat_omits_max_tokens_when_not_given():
    with patch("ecosystem_client.request_llm", return_value=_resp("ok")) as ml:
        chat([{"role": "user", "content": "x"}], priority=3)
    _, kwargs = ml.call_args
    assert "max_tokens" not in kwargs
    assert kwargs["temperature"] == 0.3   # default de análise
