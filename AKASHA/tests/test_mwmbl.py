"""
Testes da integração mwmbl (fallback leve indie) em services/web_search.py.

Cobre:
  - _fetch_mwmbl: usa param `s=` (não `q=`); reconstrói título/snippet a partir dos
    fragmentos {value,is_bold}; descarta sem url; erro de rede e resposta não-lista
    → lista vazia; respeita max.
  - _merge_rrf com weights: fonte de peso menor (mwmbl 0.3) ranqueia abaixo.
  - _fetch_web: mwmbl chamado só quando SearXNG+Marginalia retornam < N; ignorado
    quando há resultados suficientes.
"""
from __future__ import annotations

import asyncio
import sys
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


class _FakeClient:
    script = None       # httpx.Response | Exception
    calls: list = []

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
        item.request = httpx.Request("GET", url)
        return item


@pytest.fixture(autouse=True)
def _patch_httpx(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    _FakeClient.calls = []
    _FakeClient.script = None


def _mwmbl_payload(items):
    # items: (url, title_str, extract_str) — devolve no formato de fragmentos do mwmbl
    return [
        {
            "url": u,
            "title": [{"value": t, "is_bold": False}],
            "extract": [{"value": " ", "is_bold": False}, {"value": e, "is_bold": True}],
            "source": "mwmbl",
        }
        for (u, t, e) in items
    ]


# ---------------------------------------------------------------------------
# _fetch_mwmbl
# ---------------------------------------------------------------------------

def test_mwmbl_uses_s_param_and_joins_fragments():
    _FakeClient.script = httpx.Response(200, json=_mwmbl_payload(
        [("https://a.com", "Craftivism - Wikipedia", "is a form of activism")]))
    out = _run(ws._fetch_mwmbl("craftivism", 5))
    assert len(out) == 1
    assert out[0].url == "https://a.com"
    assert out[0].title == "Craftivism - Wikipedia"   # fragmentos juntados
    assert "is a form of activism" in out[0].snippet   # extract juntado
    assert out[0].source == "WEB"
    url, params = _FakeClient.calls[0]
    assert "api.mwmbl.org/search" in url
    assert params == {"s": "craftivism"}               # param 's', não 'q'


def test_mwmbl_skips_results_without_url():
    _FakeClient.script = httpx.Response(200, json=[
        {"title": [{"value": "no url"}], "extract": []},
        {"url": "https://b.com", "title": [{"value": "B"}], "extract": []},
    ])
    out = _run(ws._fetch_mwmbl("q", 5))
    assert [r.url for r in out] == ["https://b.com"]


def test_mwmbl_network_error_returns_empty():
    _FakeClient.script = httpx.ConnectError("down")
    assert _run(ws._fetch_mwmbl("q", 5)) == []


def test_mwmbl_non_list_response_returns_empty():
    # mwmbl devolve {"detail": ...} em erro de validação — não deve quebrar
    _FakeClient.script = httpx.Response(200, json={"detail": "missing s"})
    assert _run(ws._fetch_mwmbl("q", 5)) == []


def test_mwmbl_respects_max():
    _FakeClient.script = httpx.Response(200, json=_mwmbl_payload(
        [(f"https://d{i}.com", str(i), "x") for i in range(10)]))
    assert len(_run(ws._fetch_mwmbl("q", 3))) == 3


# ---------------------------------------------------------------------------
# _merge_rrf com pesos
# ---------------------------------------------------------------------------

def test_merge_rrf_weights_lower_source_ranks_lower():
    primary = [SearchResult(title="p", url="https://primary.com", snippet="")]
    mwmbl   = [SearchResult(title="m", url="https://mwmbl-only.com", snippet="")]
    out = ws._merge_rrf([primary, mwmbl], 0, weights=[1.0, 0.3])
    assert out[0].url == "https://primary.com"     # peso 1.0 > 0.3
    assert out[1].url == "https://mwmbl-only.com"


def test_merge_rrf_default_weights_uniform():
    # sem weights → comportamento antigo (uniforme)
    a = [SearchResult(title="1", url="https://x.com", snippet="")]
    b = [SearchResult(title="2", url="https://y.com", snippet="")]
    out = ws._merge_rrf([a, b], 0)
    assert {r.url for r in out} == {"https://x.com", "https://y.com"}


# ---------------------------------------------------------------------------
# _fetch_web — mwmbl como fallback condicional
# ---------------------------------------------------------------------------

def _setup_web(monkeypatch, sx_n: int, marg_n: int):
    monkeypatch.setattr(ws, "_get_searxng_url", lambda: "http://sx")
    monkeypatch.setattr(ws, "_get_marginalia_key", lambda: "")

    async def fake_sx(q, m, base, n_pages=1, lang=""):
        return [SearchResult(title=f"sx{i}", url=f"https://sx{i}.com", snippet="") for i in range(sx_n)]

    async def fake_marg(q, key, m):
        return [SearchResult(title=f"mg{i}", url=f"https://mg{i}.com", snippet="") for i in range(marg_n)]

    monkeypatch.setattr(ws, "_fetch_searxng", fake_sx)
    monkeypatch.setattr(ws, "_fetch_marginalia", fake_marg)

    calls = {"mwmbl": 0}

    async def fake_mwmbl(q, m):
        calls["mwmbl"] += 1
        return [SearchResult(title="mw", url="https://mwmbl-extra.com", snippet="")]

    monkeypatch.setattr(ws, "_fetch_mwmbl", fake_mwmbl)
    return calls


def test_fetch_web_calls_mwmbl_when_few_results(monkeypatch):
    calls = _setup_web(monkeypatch, sx_n=2, marg_n=1)  # 3 < 10 → complementa
    out = _run(ws._fetch_web("q", 0))
    assert calls["mwmbl"] == 1
    assert "https://mwmbl-extra.com" in {r.url for r in out}


def test_fetch_web_skips_mwmbl_when_enough_results(monkeypatch):
    calls = _setup_web(monkeypatch, sx_n=8, marg_n=8)  # 16 ≥ 10 → não chama
    out = _run(ws._fetch_web("q", 0))
    assert calls["mwmbl"] == 0
    assert "https://mwmbl-extra.com" not in {r.url for r in out}


def test_fetch_web_mwmbl_primary_when_others_empty(monkeypatch):
    # SearXNG+Marginalia vazios → mwmbl vira fonte primária antes do DDG
    monkeypatch.setattr(ws, "_get_searxng_url", lambda: "http://sx")
    monkeypatch.setattr(ws, "_get_marginalia_key", lambda: "")

    async def empty(*a, **k):
        return []

    ddg = {"n": 0}

    async def fake_ddg(q, m):
        ddg["n"] += 1
        return [SearchResult(title="ddg", url="https://ddg.com", snippet="")]

    async def fake_mwmbl(q, m):
        return [SearchResult(title="mw", url="https://mwmbl.com", snippet="")]

    monkeypatch.setattr(ws, "_fetch_searxng", empty)
    monkeypatch.setattr(ws, "_fetch_marginalia", empty)
    monkeypatch.setattr(ws, "_fetch_mwmbl", fake_mwmbl)
    monkeypatch.setattr(ws, "_fetch_ddg", fake_ddg)

    out = _run(ws._fetch_web("q", 0))
    assert out[0].url == "https://mwmbl.com"
    assert ddg["n"] == 0    # mwmbl retornou → não cai para DDG
