"""Fase 1 — `ecosystem_client.get_inference_url()` lê `akasha.inference_url`.

Permite que a AKASHA rodando num servidor remoto (T410, sem AVX) aponte os
embeddings/LLM para o LOGOS de outra máquina pela Tailscale (ex.: thewitch:7072);
sem a chave configurada (PC principal), usa o default local 127.0.0.1:7072 —
comportamento inalterado. `_logos_get`/`_logos_post` também passam a seguir essa URL.
"""
from __future__ import annotations

import sys
import urllib.request as _urlreq
from pathlib import Path

import pytest

# raiz do repositório (program files), onde vive ecosystem_client.py
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import ecosystem_client as ec  # noqa: E402

_DEFAULT = "http://127.0.0.1:7072"
_REMOTE = "http://thewitch:7072"


@pytest.fixture(autouse=True)
def _reset_log_flag():
    """Zera o flag de log-once entre testes (não afeta o valor de retorno)."""
    ec._inference_url_logged = False
    yield
    ec._inference_url_logged = False


def _patch_eco(monkeypatch, eco: dict) -> None:
    monkeypatch.setattr(ec, "read_ecosystem", lambda: eco)


def test_default_quando_chave_ausente(monkeypatch):
    _patch_eco(monkeypatch, {"akasha": {}})
    assert ec.get_inference_url() == _DEFAULT


def test_secao_akasha_ausente(monkeypatch):
    _patch_eco(monkeypatch, {})
    assert ec.get_inference_url() == _DEFAULT


def test_le_url_configurada(monkeypatch):
    _patch_eco(monkeypatch, {"akasha": {"inference_url": _REMOTE}})
    assert ec.get_inference_url() == _REMOTE


def test_remove_barra_final(monkeypatch):
    _patch_eco(monkeypatch, {"akasha": {"inference_url": _REMOTE + "/"}})
    assert ec.get_inference_url() == _REMOTE


def test_string_vazia_cai_no_default(monkeypatch):
    _patch_eco(monkeypatch, {"akasha": {"inference_url": ""}})
    assert ec.get_inference_url() == _DEFAULT


def test_valor_nao_string_cai_no_default(monkeypatch):
    _patch_eco(monkeypatch, {"akasha": {"inference_url": None}})
    assert ec.get_inference_url() == _DEFAULT


def test_falha_de_leitura_cai_no_default(monkeypatch):
    def _boom():
        raise OSError("disco indisponível")
    monkeypatch.setattr(ec, "read_ecosystem", _boom)
    assert ec.get_inference_url() == _DEFAULT


def test_logos_get_usa_url_configurada(monkeypatch):
    """_logos_get deve montar a requisição com get_inference_url(), não o base fixo."""
    _patch_eco(monkeypatch, {"akasha": {"inference_url": _REMOTE}})
    captured: dict = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": true}'

    def _fake_urlopen(url, timeout=0):
        captured["url"] = url
        return _Resp()

    monkeypatch.setattr(_urlreq, "urlopen", _fake_urlopen)
    ec._logos_get("/logos/status")
    assert captured["url"] == f"{_REMOTE}/logos/status"


def test_logos_post_usa_url_configurada(monkeypatch):
    """_logos_post idem — o POST vai para a URL remota configurada."""
    _patch_eco(monkeypatch, {"akasha": {"inference_url": _REMOTE}})
    captured: dict = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": true}'

    def _fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        return _Resp()

    monkeypatch.setattr(_urlreq, "urlopen", _fake_urlopen)
    ec._logos_post("/logos/models/load", {"model": "x"})
    assert captured["url"] == f"{_REMOTE}/logos/models/load"
