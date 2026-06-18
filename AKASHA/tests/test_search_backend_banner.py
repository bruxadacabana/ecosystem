"""
Testes do banner de status do backend de busca web.

- web_search_backend_status(): nominal (remoto servindo) → sem aviso; degradado
  (backend de menor prioridade em uso) → aviso; nenhum SearXNG → aviso; work-pc
  (só vendor configurado, vendor servindo) → nominal; marginalia_public reflete config.
- GET /search/backend-status: renderiza o banner quando warn; vazio quando nominal.
"""
from __future__ import annotations

import httpx
import pytest

import services.web_search as ws


def _patch(monkeypatch, candidates, active, cfg):
    monkeypatch.setattr(ws, "_searxng_candidates", lambda: candidates)

    async def _act():
        return active

    monkeypatch.setattr(ws, "_active_searxng", _act)
    monkeypatch.setattr(ws, "_akasha_cfg", lambda: cfg)


@pytest.mark.asyncio
async def test_status_nominal_remote(monkeypatch):
    _patch(monkeypatch,
           [("remoto", "http://r:8080"), ("vendor", ws.VENDOR_SEARXNG_URL)],
           ("remoto", "http://r:8080"),
           {"marginalia_api_key": "minha-chave"})
    s = await ws.web_search_backend_status()
    assert s["warn"] is False
    assert s["degraded"] is False
    assert s["searxng_down"] is False
    assert s["marginalia_public"] is False


@pytest.mark.asyncio
async def test_status_degraded_using_vendor(monkeypatch):
    _patch(monkeypatch,
           [("remoto", "http://r:8080"), ("vendor", ws.VENDOR_SEARXNG_URL)],
           ("vendor", ws.VENDOR_SEARXNG_URL),
           {"marginalia_api_key": ""})
    s = await ws.web_search_backend_status()
    assert s["warn"] is True
    assert s["degraded"] is True
    assert s["searxng_down"] is False
    assert s["active_label"] == "vendor"
    assert s["marginalia_public"] is True


@pytest.mark.asyncio
async def test_status_searxng_down(monkeypatch):
    _patch(monkeypatch,
           [("remoto", "http://r:8080"), ("vendor", ws.VENDOR_SEARXNG_URL)],
           None,
           {"marginalia_api_key": "k"})
    s = await ws.web_search_backend_status()
    assert s["warn"] is True
    assert s["searxng_down"] is True
    assert s["active_label"] is None


@pytest.mark.asyncio
async def test_status_workpc_vendor_only_is_nominal(monkeypatch):
    # Sem remoto/local configurados → vendor é o de maior prioridade; vendor servindo = nominal.
    _patch(monkeypatch,
           [("vendor", ws.VENDOR_SEARXNG_URL)],
           ("vendor", ws.VENDOR_SEARXNG_URL),
           {"marginalia_api_key": "k"})
    s = await ws.web_search_backend_status()
    assert s["warn"] is False
    assert s["degraded"] is False


@pytest.mark.asyncio
async def test_endpoint_renders_banner_when_warn(monkeypatch):
    async def _st():
        return {"active_label": None, "active_url": "", "searxng_down": True,
                "degraded": False, "marginalia_public": True, "warn": True}
    monkeypatch.setattr(ws, "web_search_backend_status", _st)
    from main import app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.get("/search/backend-status")
    assert r.status_code == 200
    assert "Nenhum SearXNG" in r.text
    assert "backend-banner" in r.text


@pytest.mark.asyncio
async def test_endpoint_empty_when_nominal(monkeypatch):
    async def _st():
        return {"active_label": "remoto", "active_url": "http://r", "searxng_down": False,
                "degraded": False, "marginalia_public": False, "warn": False}
    monkeypatch.setattr(ws, "web_search_backend_status", _st)
    from main import app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.get("/search/backend-status")
    assert r.status_code == 200
    assert "backend-banner" not in r.text
