"""
Testes da fila de alternativas SearXNG: remoto → local → vendorizado.

Cobre a ordem de candidatos, a escolha do primeiro VIVO (probe paralelo) e que
o `_fetch_web` usa o SearXNG ativo, preservando Marginalia em paralelo.
"""
from __future__ import annotations

import pytest

import services.web_search as ws


# ---------------------------------------------------------------------------
# _searxng_candidates — ordem e presença
# ---------------------------------------------------------------------------

def test_candidates_full_order(monkeypatch):
    monkeypatch.setattr(ws, "_akasha_cfg", lambda: {
        "web_search_backend": "http://remoto:8080/",
        "web_search_backend_fallback": "http://localhost:8080/",
    })
    cands = ws._searxng_candidates()
    assert [c[0] for c in cands] == ["remoto", "local", "vendor"]
    assert cands[0][1] == "http://remoto:8080"   # rstrip "/"
    assert cands[2][1] == ws.VENDOR_SEARXNG_URL


def test_candidates_only_remote(monkeypatch):
    monkeypatch.setattr(ws, "_akasha_cfg", lambda: {"web_search_backend": "http://remoto:8080"})
    assert [c[0] for c in ws._searxng_candidates()] == ["remoto", "vendor"]


def test_candidates_none_configured_keeps_vendor(monkeypatch):
    monkeypatch.setattr(ws, "_akasha_cfg", lambda: {})
    cands = ws._searxng_candidates()
    assert [c[0] for c in cands] == ["vendor"]
    assert cands[0][1] == ws.VENDOR_SEARXNG_URL


def test_candidates_vendor_override(monkeypatch):
    monkeypatch.setattr(ws, "_akasha_cfg", lambda: {"web_search_backend_vendor": "http://127.0.0.1:9999/"})
    assert ws._searxng_candidates()[-1] == ("vendor", "http://127.0.0.1:9999")


# ---------------------------------------------------------------------------
# _active_searxng — escolhe o primeiro vivo por prioridade
# ---------------------------------------------------------------------------

def _set_cfg(monkeypatch):
    monkeypatch.setattr(ws, "_akasha_cfg", lambda: {
        "web_search_backend": "http://remoto:8080",
        "web_search_backend_fallback": "http://localhost:8080",
    })


@pytest.mark.asyncio
async def test_active_prefers_remote(monkeypatch):
    _set_cfg(monkeypatch)
    async def _alive(url): return True
    monkeypatch.setattr(ws, "_searxng_alive", _alive)
    assert await ws._active_searxng() == ("remoto", "http://remoto:8080")


@pytest.mark.asyncio
async def test_active_falls_to_local(monkeypatch):
    _set_cfg(monkeypatch)
    async def _alive(url): return "localhost" in url
    monkeypatch.setattr(ws, "_searxng_alive", _alive)
    assert await ws._active_searxng() == ("local", "http://localhost:8080")


@pytest.mark.asyncio
async def test_active_falls_to_vendor(monkeypatch):
    _set_cfg(monkeypatch)
    async def _alive(url): return url == ws.VENDOR_SEARXNG_URL
    monkeypatch.setattr(ws, "_searxng_alive", _alive)
    assert await ws._active_searxng() == ("vendor", ws.VENDOR_SEARXNG_URL)


@pytest.mark.asyncio
async def test_active_none_when_all_dead(monkeypatch):
    _set_cfg(monkeypatch)
    async def _alive(url): return False
    monkeypatch.setattr(ws, "_searxng_alive", _alive)
    assert await ws._active_searxng() is None


# ---------------------------------------------------------------------------
# _fetch_web — usa o SearXNG ativo; Marginalia em paralelo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_web_uses_active_searxng(monkeypatch):
    used = {}

    async def _active(): return ("local", "http://localhost:8080")
    async def _fetch_searxng(query, max_results, base_url, n_pages=1, lang=""):
        used["url"] = base_url
        return [ws.SearchResult(title=f"r{i}", url=f"http://x/{i}", snippet="") for i in range(10)]
    async def _fetch_marginalia(query, key, max_results): return []

    monkeypatch.setattr(ws, "_active_searxng", _active)
    monkeypatch.setattr(ws, "_fetch_searxng", _fetch_searxng)
    monkeypatch.setattr(ws, "_fetch_marginalia", _fetch_marginalia)
    monkeypatch.setattr(ws, "_get_marginalia_key", lambda: "")

    results = await ws._fetch_web("q", max_results=20)
    assert used["url"] == "http://localhost:8080"
    assert len(results) == 10


@pytest.mark.asyncio
async def test_fetch_web_no_searxng_falls_back(monkeypatch):
    """Sem SearXNG vivo e sem Marginalia → cai para mwmbl/DDG (não chama _fetch_searxng)."""
    called = {"searxng": False}

    async def _active(): return None
    async def _fetch_searxng(*a, **k):
        called["searxng"] = True
        return []
    async def _fetch_marginalia(query, key, max_results): return []
    async def _fetch_mwmbl(query, max_results): return []
    async def _fetch_ddg(query, max_results):
        return [ws.SearchResult(title="ddg", url="http://ddg/1", snippet="")]

    monkeypatch.setattr(ws, "_active_searxng", _active)
    monkeypatch.setattr(ws, "_fetch_searxng", _fetch_searxng)
    monkeypatch.setattr(ws, "_fetch_marginalia", _fetch_marginalia)
    monkeypatch.setattr(ws, "_fetch_mwmbl", _fetch_mwmbl)
    monkeypatch.setattr(ws, "_fetch_ddg", _fetch_ddg)
    monkeypatch.setattr(ws, "_get_marginalia_key", lambda: "")

    results = await ws._fetch_web("q", max_results=20)
    assert called["searxng"] is False
    assert results and results[0].url == "http://ddg/1"
