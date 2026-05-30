"""
Testes de integração LOGOS — verifica que os apps Python interagem
corretamente com o proxy LOGOS (porta 7072).

Testa:
  - Headers de prioridade enviados por cada app
  - Comportamento com LOGOS desabilitado (503)
  - Lazy loading: inference_enabled=true + chat_server_online=false
  - Timers de idle independentes para chat e embed
  - get_inference_url() aponta para porta correta

Não requer LOGOS real — usa unittest.mock para interceptar HTTP.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_ECO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ECO_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _logos_status(
    inference_enabled: bool = False,
    chat_online: bool = False,
    embed_online: bool = False,
    chat_model: str = "",
    embed_model: str = "bge-m3",
) -> dict[str, Any]:
    """Constrói um StatusResponse simulado do LOGOS."""
    return {
        "inference_enabled":   inference_enabled,
        "chat_server_online":  chat_online,
        "embed_server_online": embed_online,
        "chat_server_model":   chat_model,
        "embed_server_model":  embed_model,
        "active_priority":     None,
        "active_app":          None,
        "vram_used_mb":        None,
        "vram_pct":            None,
        "cpu_pct":             0.0,
        "ram_free_mb":         8192,
        "ram_total_mb":        16384,
        "on_battery":          False,
        "p3_vram_blocked":     False,
        "queue":               [0, 0, 0],
    }


class _FakeUrlOpenResponse:
    """Simula o objeto retornado por urllib.request.urlopen() como context manager."""
    def __init__(self, data: dict) -> None:
        self._data = json.dumps(data).encode()

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def _mock_logos_get(data: dict):
    """Retorna um side_effect que simula urlopen com dados JSON."""
    return lambda *args, **kwargs: _FakeUrlOpenResponse(data)


# ---------------------------------------------------------------------------
# 1. get_inference_url retorna porta 7072
# ---------------------------------------------------------------------------

def test_get_inference_url_returns_logos_port():
    """get_inference_url() deve retornar URL com porta 7072 — nunca 11434 (Ollama legado)."""
    import ecosystem_client as ec
    url = ec.get_inference_url()
    assert "7072" in url, f"esperado porta 7072 no URL LOGOS, recebido: {url}"
    assert "11434" not in url, "porta 11434 é Ollama legado — não deve ser usada"


# ---------------------------------------------------------------------------
# 2. get_inference_headers retorna headers corretos por prioridade
# ---------------------------------------------------------------------------

def test_akasha_headers_are_p2():
    """AKASHA deve enviar X-Priority=2 (busca inteligente, não interativa)."""
    import ecosystem_client as ec
    headers = ec.get_inference_headers("akasha", priority=2)
    assert headers.get("X-Priority") == "2", \
        f"AKASHA deve enviar X-Priority=2, recebido: {headers}"
    assert headers.get("X-App") == "akasha", \
        f"AKASHA deve enviar X-App=akasha, recebido: {headers}"


def test_mnemosyne_embed_headers_are_p3():
    """Embeddings em background (Mnemosyne indexação) devem usar P3."""
    import ecosystem_client as ec
    headers = ec.get_inference_headers("mnemosyne", priority=3)
    assert headers.get("X-Priority") == "3", \
        f"Mnemosyne background deve enviar X-Priority=3, recebido: {headers}"


def test_mnemosyne_rag_headers_are_p2():
    """RAG interativo do Mnemosyne deve usar P2."""
    import ecosystem_client as ec
    headers = ec.get_inference_headers("mnemosyne", priority=2)
    assert headers.get("X-Priority") == "2", \
        f"Mnemosyne RAG deve enviar X-Priority=2, recebido: {headers}"


def test_hub_interactive_headers_are_p1():
    """Chat interativo do HUB deve usar P1 (prioridade máxima)."""
    import ecosystem_client as ec
    headers = ec.get_inference_headers("hub", priority=1)
    assert headers.get("X-Priority") == "1", \
        f"HUB chat interativo deve enviar X-Priority=1, recebido: {headers}"


def test_priority_values_are_strings():
    """X-Priority em get_inference_headers deve ser string (X-Priority: "2", não 2)."""
    import ecosystem_client as ec
    headers = ec.get_inference_headers("test", priority=2)
    assert isinstance(headers["X-Priority"], str), \
        "X-Priority deve ser string para compatibilidade com headers HTTP"


# ---------------------------------------------------------------------------
# 3. logos_status() retorna inference_enabled
# ---------------------------------------------------------------------------

def test_logos_status_includes_inference_enabled_field():
    """logos_status() deve incluir campo inference_enabled quando LOGOS responde."""
    import urllib.request as urllib_req
    import ecosystem_client as ec

    data = _logos_status(inference_enabled=True, chat_online=False)
    with patch.object(urllib_req, "urlopen", side_effect=_mock_logos_get(data)):
        st = ec.logos_status()

    assert st is not None, "logos_status() não deve retornar None com resposta 200"
    assert "inference_enabled" in st, \
        "StatusResponse deve incluir 'inference_enabled' (adicionado no Passo 8)"
    assert st["inference_enabled"] is True


def test_logos_status_enabled_idle_state():
    """inference_enabled=true + chat_server_online=false = estado 'enabled_idle'."""
    import urllib.request as urllib_req
    import ecosystem_client as ec

    data = _logos_status(inference_enabled=True, chat_online=False, embed_online=True)
    with patch.object(urllib_req, "urlopen", side_effect=_mock_logos_get(data)):
        st = ec.logos_status()

    assert st is not None
    assert st["inference_enabled"] is True
    assert st["chat_server_online"] is False
    assert st["embed_server_online"] is True, \
        "embed deve estar online independentemente do estado do chat"


def test_logos_status_active_state():
    """inference_enabled=true + chat_server_online=true = estado 'active'."""
    import urllib.request as urllib_req
    import ecosystem_client as ec

    data = _logos_status(inference_enabled=True, chat_online=True, chat_model="qwen2.5:7b")
    with patch.object(urllib_req, "urlopen", side_effect=_mock_logos_get(data)):
        st = ec.logos_status()

    assert st is not None
    assert st["inference_enabled"] is True
    assert st["chat_server_online"] is True
    assert st["chat_server_model"] == "qwen2.5:7b"


# ---------------------------------------------------------------------------
# 4. LOGOS 503 (inferência desabilitada) → apps tratam graciosamente
# ---------------------------------------------------------------------------

def test_logos_offline_returns_none_from_status():
    """Quando LOGOS está offline, logos_status() retorna None (não propaga exceção)."""
    import urllib.request as urllib_req
    import ecosystem_client as ec

    with patch.object(urllib_req, "urlopen", side_effect=OSError("connection refused")):
        result = ec.logos_status()

    assert result is None, \
        "logos_status() deve retornar None quando LOGOS está offline, nunca propagar exceção"


def test_logos_503_disabled_body_is_parseable():
    """503 com corpo JSON de 'inferência desabilitada' deve ser parseável."""
    body = json.dumps({
        "error": "LOGOS: inferência desabilitada — ative a IA no HUB antes de fazer requisições"
    })
    parsed = json.loads(body)
    assert "inferência desabilitada" in parsed["error"]
    assert "error" in parsed


# ---------------------------------------------------------------------------
# 5. Timers de idle: chat e embed são independentes
# ---------------------------------------------------------------------------

def test_chat_and_embed_idle_timers_are_independent():
    """
    Verifica o invariante: o status pode mostrar embed online com chat offline
    (e vice-versa) — os dois servidores têm ciclos de vida independentes.
    """
    import urllib.request as urllib_req
    import ecosystem_client as ec

    # Cenário: chat foi descarregado por idle, embed ainda ativo
    data1 = _logos_status(inference_enabled=True, chat_online=False, embed_online=True)
    with patch.object(urllib_req, "urlopen", side_effect=_mock_logos_get(data1)):
        st = ec.logos_status()

    assert st is not None
    assert st["chat_server_online"]  is False, "chat deve estar offline após idle unload"
    assert st["embed_server_online"] is True,  "embed deve continuar online independentemente"

    # Cenário inverso: embed descarregado por idle, chat ativo
    data2 = _logos_status(inference_enabled=True, chat_online=True, embed_online=False)
    with patch.object(urllib_req, "urlopen", side_effect=_mock_logos_get(data2)):
        st2 = ec.logos_status()

    assert st2 is not None
    assert st2["chat_server_online"]  is True,  "chat deve estar online"
    assert st2["embed_server_online"] is False, "embed deve estar offline após idle unload"


# ---------------------------------------------------------------------------
# 6. Invariante: get_inference_url não falha sem ecosystem.json
# ---------------------------------------------------------------------------

def test_get_inference_url_does_not_raise_without_ecosystem_json():
    """get_inference_url() não deve levantar exceção mesmo sem ecosystem.json presente."""
    import ecosystem_client as ec
    with patch.object(ec, "read_ecosystem", return_value={}):
        url = ec.get_inference_url()
    assert isinstance(url, str) and len(url) > 0, \
        "get_inference_url() deve retornar string não-vazia mesmo sem ecosystem.json"
