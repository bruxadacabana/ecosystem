"""
Testes para as funções de gestão de inferência em ecosystem_client.py:
  - get_inference_url(): mesma semântica que get_ollama_url()
  - load_model(): chama /logos/models/load e interpreta resposta
  - unload_model(): chama /logos/models/unload e interpreta resposta

Todos os testes mocam _logos_get/_logos_post para não depender do LOGOS.
"""
from __future__ import annotations
from unittest.mock import patch
import sys
import os

# Adiciona raiz do ecossistema ao path para importar ecosystem_client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ecosystem_client as ec


# ─── get_inference_url ────────────────────────────────────────────────────────

def test_get_inference_url_logos_available():
    """Com LOGOS disponível retorna URL do LOGOS (7072)."""
    with patch.object(ec, "_logos_get", return_value={"status": "ok"}):
        url = ec.get_inference_url()
    assert "7072" in url


def test_get_inference_url_logos_offline():
    """Com LOGOS offline retorna Ollama direto (11434)."""
    with patch.object(ec, "_logos_get", return_value=None):
        url = ec.get_inference_url()
    assert "11434" in url


def test_get_inference_url_same_as_get_ollama_url():
    """get_inference_url() e get_ollama_url() retornam o mesmo valor."""
    with patch.object(ec, "_logos_get", return_value={"status": "ok"}):
        assert ec.get_inference_url() == ec.get_ollama_url()

    with patch.object(ec, "_logos_get", return_value=None):
        assert ec.get_inference_url() == ec.get_ollama_url()


# ─── load_model ───────────────────────────────────────────────────────────────

def test_load_model_success():
    """Resposta {ok: true} → retorna True."""
    with patch.object(ec, "_logos_post", return_value={"ok": True, "model": "smollm2:1.7b"}):
        assert ec.load_model("smollm2:1.7b") is True


def test_load_model_logos_offline():
    """LOGOS offline → _logos_post retorna None → retorna False sem exceção."""
    with patch.object(ec, "_logos_post", return_value=None):
        assert ec.load_model("smollm2:1.7b") is False


def test_load_model_backend_error():
    """Resposta {ok: false} → retorna False."""
    with patch.object(ec, "_logos_post", return_value={"ok": False}):
        assert ec.load_model("smollm2:1.7b") is False


def test_load_model_calls_correct_endpoint():
    """load_model chama /logos/models/load com payload correto."""
    calls = []
    def capture(path, data, **_):
        calls.append((path, data))
        return {"ok": True}

    with patch.object(ec, "_logos_post", side_effect=capture):
        ec.load_model("qwen2.5:7b")

    assert len(calls) == 1
    assert calls[0][0] == "/logos/models/load"
    assert calls[0][1]["model"] == "qwen2.5:7b"


# ─── unload_model ─────────────────────────────────────────────────────────────

def test_unload_model_success():
    """Resposta {ok: true} → retorna True."""
    with patch.object(ec, "_logos_post", return_value={"ok": True, "model": "smollm2:1.7b"}):
        assert ec.unload_model("smollm2:1.7b") is True


def test_unload_model_logos_offline():
    """LOGOS offline → retorna False sem exceção."""
    with patch.object(ec, "_logos_post", return_value=None):
        assert ec.unload_model("smollm2:1.7b") is False


def test_unload_model_calls_correct_endpoint():
    """unload_model chama /logos/models/unload com payload correto."""
    calls = []
    def capture(path, data, **_):
        calls.append((path, data))
        return {"ok": True}

    with patch.object(ec, "_logos_post", side_effect=capture):
        ec.unload_model("qwen2.5:7b")

    assert len(calls) == 1
    assert calls[0][0] == "/logos/models/unload"
    assert calls[0][1]["model"] == "qwen2.5:7b"
