"""
Testes da integração direta com a Marginalia (SearXNG 10) em services/web_search.py.

Cobre:
  - _fetch_marginalia: chave pública por default; chave própria na URL; parsing de
    url/title/description; 503 e erro de rede → lista vazia; query URL-encoded;
    resultados sem url descartados.
  - _get_marginalia_key: lê akasha.marginalia_api_key (strip); vazio quando ausente.
  - _merge_rrf: dedup por URL, ranking RRF (URL em 2 fontes sobe), respeita max.
  - _fetch_web: funde SearXNG + Marginalia; cai para DDG só se ambos vazios.
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import httpx
import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import services.web_search as ws
from services.web_search import SearchResult


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fake httpx.AsyncClient — registra a URL chamada e devolve resposta/exceção
# ---------------------------------------------------------------------------

class _FakeClient:
    script = None       # httpx.Response | Exception
    calls: list = []    # (url, params)

    def __init__(self, *a, **k) -> None:
        pass

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def get(self, url, params=None):
        _FakeClient.calls.append((url, params))
        item = _FakeClient.script
        if isinstance(item, Exception):
            raise item
        item.request = httpx.Request("GET", url)  # necessário p/ raise_for_status
        return item


@pytest.fixture(autouse=True)
def _patch_httpx(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    _FakeClient.calls = []
    _FakeClient.script = None


def _payload(items):
    return {"license": "x", "query": "q",
            "results": [{"url": u, "title": t, "description": d} for (u, t, d) in items]}


# ---------------------------------------------------------------------------
# _fetch_marginalia
# ---------------------------------------------------------------------------

def test_marginalia_default_key_uses_public():
    _FakeClient.script = httpx.Response(200, json=_payload([("https://a.com", "A", "da")]))
    out = _run(ws._fetch_marginalia("craftivism", "", 5))
    assert len(out) == 1 and out[0].url == "https://a.com"
    url, _ = _FakeClient.calls[0]
    assert "/public/search/" in url
    assert "craftivism" in url


def test_marginalia_custom_key_in_url():
    _FakeClient.script = httpx.Response(200, json=_payload([]))
    _run(ws._fetch_marginalia("q", "MYKEY", 5))
    url, _ = _FakeClient.calls[0]
    assert "/MYKEY/search/" in url


def test_marginalia_key_whitespace_stripped():
    _FakeClient.script = httpx.Response(200, json=_payload([]))
    _run(ws._fetch_marginalia("q", "  K  ", 5))
    url, _ = _FakeClient.calls[0]
    assert "/K/search/" in url


def test_marginalia_parses_fields():
    _FakeClient.script = httpx.Response(200, json=_payload([("https://b.org", "Title B", "Desc B")]))
    out = _run(ws._fetch_marginalia("q", "", 5))
    assert out[0].title == "Title B"
    assert out[0].snippet == "Desc B"
    assert out[0].source == "WEB"


def test_marginalia_query_url_encoded():
    _FakeClient.script = httpx.Response(200, json=_payload([]))
    _run(ws._fetch_marginalia("urban foraging", "", 5))
    url, _ = _FakeClient.calls[0]
    assert "urban%20foraging" in url


def test_marginalia_503_returns_empty():
    _FakeClient.script = httpx.Response(503)
    out = _run(ws._fetch_marginalia("q", "", 5))
    assert out == []
    assert len(_FakeClient.calls) == 1  # não re-tenta


def test_marginalia_network_error_returns_empty():
    _FakeClient.script = httpx.ConnectError("down")
    out = _run(ws._fetch_marginalia("q", "", 5))
    assert out == []


def test_marginalia_skips_results_without_url():
    _FakeClient.script = httpx.Response(200, json={"results": [
        {"title": "no url", "description": "x"},
        {"url": "https://c.com", "title": "C", "description": "y"},
    ]})
    out = _run(ws._fetch_marginalia("q", "", 5))
    assert [r.url for r in out] == ["https://c.com"]


# ---------------------------------------------------------------------------
# _get_marginalia_key
# ---------------------------------------------------------------------------

def _fake_eco(cfg):
    m = types.ModuleType("ecosystem_client")
    m.get_akasha_config = lambda: cfg  # type: ignore[attr-defined]
    return m


def test_get_marginalia_key_reads_and_strips(monkeypatch):
    monkeypatch.setitem(sys.modules, "ecosystem_client", _fake_eco({"marginalia_api_key": "  KEY123  "}))
    assert ws._get_marginalia_key() == "KEY123"


def test_get_marginalia_key_empty_when_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "ecosystem_client", _fake_eco({}))
    assert ws._get_marginalia_key() == ""


# ---------------------------------------------------------------------------
# _merge_rrf
# ---------------------------------------------------------------------------

def test_merge_rrf_dedups_and_ranks():
    a = [SearchResult(title="1", url="https://x.com", snippet=""),
         SearchResult(title="2", url="https://y.com", snippet="")]
    b = [SearchResult(title="3", url="https://y.com", snippet=""),  # compartilhada
         SearchResult(title="4", url="https://z.com", snippet="")]
    out = ws._merge_rrf([a, b], 0)
    urls = [r.url for r in out]
    assert set(urls) == {"https://x.com", "https://y.com", "https://z.com"}  # dedup
    assert urls[0] == "https://y.com"   # aparece nas 2 fontes → maior RRF
    assert len(out) == 3


def test_merge_rrf_respects_max():
    a = [SearchResult(title=str(i), url=f"https://d{i}.com", snippet="") for i in range(10)]
    out = ws._merge_rrf([a], 3)
    assert len(out) == 3


def test_merge_rrf_skips_empty_url():
    a = [SearchResult(title="x", url="", snippet=""),
         SearchResult(title="y", url="https://ok.com", snippet="")]
    out = ws._merge_rrf([a], 0)
    assert [r.url for r in out] == ["https://ok.com"]


# ---------------------------------------------------------------------------
# _fetch_web — fusão SearXNG + Marginalia, fallback DDG
# ---------------------------------------------------------------------------

def test_fetch_web_merges_searxng_and_marginalia(monkeypatch):
    monkeypatch.setattr(ws, "_get_searxng_url", lambda: "http://sx")
    monkeypatch.setattr(ws, "_get_marginalia_key", lambda: "")

    async def fake_sx(q, m, base, n_pages=1, lang=""):
        return [SearchResult(title="sx", url="https://sx-only.com", snippet="")]

    async def fake_marg(q, key, m):
        return [SearchResult(title="mg", url="https://marg-only.com", snippet="")]

    monkeypatch.setattr(ws, "_fetch_searxng", fake_sx)
    monkeypatch.setattr(ws, "_fetch_marginalia", fake_marg)

    out = _run(ws._fetch_web("q", 0, n_pages=1))
    urls = {r.url for r in out}
    assert "https://sx-only.com" in urls     # SearXNG
    assert "https://marg-only.com" in urls   # Marginalia somou resultado único


def test_fetch_web_marginalia_runs_even_without_searxng(monkeypatch):
    monkeypatch.setattr(ws, "_get_searxng_url", lambda: "")   # SearXNG não configurado
    monkeypatch.setattr(ws, "_get_marginalia_key", lambda: "")
    called = {"marg": 0, "ddg": 0}

    async def fake_marg(q, key, m):
        called["marg"] += 1
        return [SearchResult(title="mg", url="https://m.com", snippet="")]

    async def fake_ddg(q, m):
        called["ddg"] += 1
        return []

    monkeypatch.setattr(ws, "_fetch_marginalia", fake_marg)
    monkeypatch.setattr(ws, "_fetch_ddg", fake_ddg)

    out = _run(ws._fetch_web("q", 0))
    assert called["marg"] == 1
    assert called["ddg"] == 0                # Marginalia retornou → não cai para DDG
    assert out[0].url == "https://m.com"


def test_fetch_web_falls_to_ddg_when_both_empty(monkeypatch):
    monkeypatch.setattr(ws, "_get_searxng_url", lambda: "http://sx")
    monkeypatch.setattr(ws, "_get_marginalia_key", lambda: "")

    async def empty_sx(*a, **k):
        return []

    async def empty_marg(*a, **k):
        return []

    ddg = {"n": 0}

    async def fake_ddg(q, m):
        ddg["n"] += 1
        return [SearchResult(title="ddg", url="https://ddg.com", snippet="")]

    monkeypatch.setattr(ws, "_fetch_searxng", empty_sx)
    monkeypatch.setattr(ws, "_fetch_marginalia", empty_marg)
    monkeypatch.setattr(ws, "_fetch_ddg", fake_ddg)

    out = _run(ws._fetch_web("q", 0))
    assert ddg["n"] == 1
    assert out[0].url == "https://ddg.com"


def test_fetch_web_marginalia_exception_does_not_break(monkeypatch):
    """Se a Marginalia lançar, a busca continua com os resultados do SearXNG."""
    monkeypatch.setattr(ws, "_get_searxng_url", lambda: "http://sx")
    monkeypatch.setattr(ws, "_get_marginalia_key", lambda: "")

    async def fake_sx(q, m, base, n_pages=1, lang=""):
        return [SearchResult(title="sx", url="https://sx.com", snippet="")]

    async def boom_marg(q, key, m):
        raise RuntimeError("marginalia down")

    monkeypatch.setattr(ws, "_fetch_searxng", fake_sx)
    monkeypatch.setattr(ws, "_fetch_marginalia", boom_marg)

    out = _run(ws._fetch_web("q", 0))
    assert [r.url for r in out] == ["https://sx.com"]
