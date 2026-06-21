"""
Testes para services/web_search.search_images_web (Mídia 4).

Cobre:
  - SearXNG configurado e retornando imagens → usa SearXNG
  - SearXNG sem resultados → fallback para DDG
  - SearXNG offline (exceção) → fallback para DDG
  - SearXNG não configurado → usa DDG diretamente
  - DDG offline → retorna [] sem exceção
  - max limita o número de resultados
  - chaves obrigatórias presentes em cada resultado
"""
from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_searxng_response(n: int = 3) -> list[dict]:
    return [
        {
            "img_src":  f"https://searxng.example/img{i}.jpg",
            "url":      f"https://example.com/page{i}",
            "title":    f"Imagem SearXNG {i}",
            "content":  f"Descrição {i}",
        }
        for i in range(n)
    ]


def _make_ddg_response(n: int = 3) -> list[dict]:
    return [
        {
            "image": f"https://ddg.example/img{i}.jpg",
            "url":   f"https://example.com/ddg{i}",
            "title": f"Imagem DDG {i}",
        }
        for i in range(n)
    ]


class _FakeDDGS:
    def __init__(self, items: list):
        self._items = items

    def images(self, q, max_results=20):
        return self._items[:max_results]


# ---------------------------------------------------------------------------
# TestSearchImagesWeb
# ---------------------------------------------------------------------------

class TestSearchImagesWeb:

    def test_uses_searxng_when_configured(self, monkeypatch):
        """SearXNG vivo e retornando imagens → DDG não é chamado.

        Mocka os seams atuais (`_active_searxng` + `_fetch_searxng_images`); o código
        deixou de usar `_get_searxng_url`/httpx inline para imagens (fila de
        disponibilidade, 2026-06-17).
        """
        import services.web_search as _mod

        final = [
            {"img_url": f"https://searxng.example/img{i}.jpg",
             "page_url": f"https://example.com/page{i}",
             "alt_text": f"Imagem SearXNG {i}", "title": f"Imagem SearXNG {i}"}
            for i in range(3)
        ]
        ddg_called = []

        async def fake_active():
            return ("remote", "http://localhost:8888")

        async def fake_fetch(query, max, url):
            return final

        def _fake_ddgs(*a, **kw):
            ddg_called.append(True)
            return []

        monkeypatch.setattr(_mod, "_active_searxng", fake_active)
        monkeypatch.setattr(_mod, "_fetch_searxng_images", fake_fetch)

        with patch.object(_mod.DDGS, "images", _fake_ddgs):
            results = run(_mod.search_images_web("gato", max=10))

        assert len(results) == 3
        assert results[0]["img_url"] == "https://searxng.example/img0.jpg"
        assert results[0]["page_url"] == "https://example.com/page0"
        assert not ddg_called, "DDG não deve ser chamado quando SearXNG retorna resultados"

    def test_falls_back_to_ddg_when_searxng_empty(self, monkeypatch):
        """SearXNG retorna resultados vazios → DDG é chamado como fallback."""
        import services.web_search as _mod

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}  # vazio
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        ddg_items = _make_ddg_response(3)

        monkeypatch.setattr(_mod, "_get_searxng_url", lambda: "http://localhost:8888")
        monkeypatch.setattr(_mod, "DDGS", lambda: _FakeDDGS(ddg_items))

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = run(_mod.search_images_web("gato", max=10))

        assert len(results) == 3
        assert results[0]["img_url"] == "https://ddg.example/img0.jpg"

    def test_falls_back_to_ddg_when_searxng_fails(self, monkeypatch):
        """SearXNG lança exceção → DDG é chamado como fallback."""
        import services.web_search as _mod

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("SearXNG offline"))

        ddg_items = _make_ddg_response(2)

        monkeypatch.setattr(_mod, "_get_searxng_url", lambda: "http://localhost:8888")
        monkeypatch.setattr(_mod, "DDGS", lambda: _FakeDDGS(ddg_items))

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = run(_mod.search_images_web("gato", max=10))

        assert len(results) == 2
        assert "ddg.example" in results[0]["img_url"]

    def test_uses_ddg_when_searxng_not_configured(self, monkeypatch):
        """Nenhum SearXNG vivo → usa DDG diretamente."""
        import services.web_search as _mod

        ddg_items = _make_ddg_response(4)

        async def fake_active():
            return None

        monkeypatch.setattr(_mod, "_active_searxng", fake_active)
        monkeypatch.setattr(_mod, "DDGS", lambda: _FakeDDGS(ddg_items))

        results = run(_mod.search_images_web("cachorro", max=10))

        assert len(results) == 4
        assert all("ddg.example" in r["img_url"] for r in results)

    def test_ddg_offline_returns_empty(self, monkeypatch):
        """Sem SearXNG e DDG lançando exceção → retorna [] sem propagar."""
        import services.web_search as _mod

        class _BrokenDDGS:
            def images(self, q, max_results=20):
                raise ConnectionError("DDG offline")

        async def fake_active():
            return None

        monkeypatch.setattr(_mod, "_active_searxng", fake_active)
        monkeypatch.setattr(_mod, "DDGS", lambda: _BrokenDDGS())

        results = run(_mod.search_images_web("teste"))
        assert results == []

    def test_max_limits_results_from_searxng(self, monkeypatch):
        """max=2 limita o número de resultados retornados pelo SearXNG."""
        import services.web_search as _mod

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": _make_searxng_response(10)}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        monkeypatch.setattr(_mod, "_get_searxng_url", lambda: "http://localhost:8888")

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = run(_mod.search_images_web("x", max=2))

        assert len(results) <= 2

    def test_max_limits_results_from_ddg(self, monkeypatch):
        """max=2 limita o número de resultados retornados pelo DDG."""
        import services.web_search as _mod

        ddg_items = _make_ddg_response(10)
        monkeypatch.setattr(_mod, "_get_searxng_url", lambda: "")
        monkeypatch.setattr(_mod, "DDGS", lambda: _FakeDDGS(ddg_items))

        results = run(_mod.search_images_web("x", max=2))
        assert len(results) <= 2

    def test_result_has_required_keys(self, monkeypatch):
        """Cada resultado deve ter img_url, page_url, alt_text, title."""
        import services.web_search as _mod

        ddg_items = _make_ddg_response(2)
        monkeypatch.setattr(_mod, "_get_searxng_url", lambda: "")
        monkeypatch.setattr(_mod, "DDGS", lambda: _FakeDDGS(ddg_items))

        results = run(_mod.search_images_web("teste"))
        for r in results:
            for key in ("img_url", "page_url", "alt_text", "title"):
                assert key in r, f"Chave '{key}' ausente: {r}"

    def test_filters_items_without_img_src(self):
        """Itens SearXNG sem img_src são ignorados (em `_fetch_searxng_images`)."""
        import services.web_search as _mod

        raw = [
            {"url": "https://x.com/p", "title": "sem imagem"},  # sem img_src
            {"img_src": "https://x.com/img.jpg", "url": "https://x.com/p2", "title": "com imagem"},
        ]

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": raw}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = run(_mod._fetch_searxng_images("x", 10, "http://localhost:8888"))

        assert len(results) == 1
        assert results[0]["img_url"] == "https://x.com/img.jpg"


# ---------------------------------------------------------------------------
# TestSearchImagesQuickCombination — integração local + web
# ---------------------------------------------------------------------------

class TestSearchImagesQuickCombination:
    """Testa que search_images_quick combina local + web corretamente."""

    def test_local_results_take_priority_over_web(self, db_paths, monkeypatch):
        """Resultados locais aparecem primeiro; web preenche o restante."""
        import sqlite3
        import database as _db
        import services.web_search as _web
        import services.image_indexer as _img_mod
        import config as _cfg

        main_path, _ = db_paths

        # Inserir 2 imagens locais
        con = sqlite3.connect(main_path)
        for i in range(2):
            con.execute(
                "INSERT OR IGNORE INTO page_images (page_url, img_url, alt_text, title) VALUES (?,?,?,?)",
                (f"https://local.com/p{i}", f"https://local.com/img{i}.jpg", f"local {i}", ""),
            )
            con.execute(
                "INSERT OR REPLACE INTO page_images_fts (img_url, page_url, alt_text, title, phash) VALUES (?,?,?,?,?)",
                (f"https://local.com/img{i}.jpg", f"https://local.com/p{i}", f"local {i}", "", ""),
            )
        con.commit()
        con.close()

        # Web retorna 3 imagens, 1 duplicada (local img0)
        web_results = [
            {"img_url": "https://local.com/img0.jpg",  "page_url": "", "alt_text": "dup", "title": "dup"},
            {"img_url": "https://web.com/img10.jpg", "page_url": "", "alt_text": "web 10", "title": ""},
            {"img_url": "https://web.com/img11.jpg", "page_url": "", "alt_text": "web 11", "title": ""},
        ]

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path

        async def _fake_web(q, max=6):
            return web_results

        monkeypatch.setattr(_web, "search_images_web", _fake_web)

        try:
            results = asyncio.run(_img_mod.search_images_quick("local", max=6))
        finally:
            _cfg.DB_PATH = orig_db

        urls = [r["img_url"] for r in results]
        # local img0 deve aparecer uma só vez (dedup)
        assert urls.count("https://local.com/img0.jpg") == 1, "URL local não deve aparecer duplicada"
        # Deve ter 4 itens únicos (2 locais + 2 web não-dup)
        assert len(results) == 4
        # Os dois primeiros devem ser os locais
        assert results[0]["img_url"].startswith("https://local.com")
        assert results[1]["img_url"].startswith("https://local.com")

    def test_web_fills_when_local_is_empty(self, db_paths, monkeypatch):
        """Sem resultados locais, resultados web preenchem o painel."""
        import database as _db
        import services.web_search as _web
        import services.image_indexer as _img_mod
        import config as _cfg

        main_path, _ = db_paths  # banco vazio

        web_results = [
            {"img_url": f"https://web.com/img{i}.jpg", "page_url": "", "alt_text": f"img{i}", "title": ""}
            for i in range(6)
        ]

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path

        async def _fake_web(q, max=6):
            return web_results

        monkeypatch.setattr(_web, "search_images_web", _fake_web)

        try:
            results = asyncio.run(_img_mod.search_images_quick("algo", max=6))
        finally:
            _cfg.DB_PATH = orig_db

        assert len(results) == 6
        assert all("web.com" in r["img_url"] for r in results)

    def test_deduplication_by_img_url(self, db_paths, monkeypatch):
        """URLs duplicadas entre local e web aparecem apenas uma vez."""
        import sqlite3
        import services.web_search as _web
        import services.image_indexer as _img_mod
        import config as _cfg

        main_path, _ = db_paths

        shared_url = "https://shared.com/img.jpg"
        con = sqlite3.connect(main_path)
        con.execute(
            "INSERT OR IGNORE INTO page_images (page_url, img_url, alt_text, title) VALUES (?,?,?,?)",
            ("https://shared.com/page", shared_url, "compartilhada", ""),
        )
        con.execute(
            "INSERT OR REPLACE INTO page_images_fts (img_url, page_url, alt_text, title, phash) VALUES (?,?,?,?,?)",
            (shared_url, "https://shared.com/page", "compartilhada", "", ""),
        )
        con.commit()
        con.close()

        web_results = [
            {"img_url": shared_url,              "page_url": "", "alt_text": "dup web", "title": ""},
            {"img_url": "https://unique.com/x.jpg", "page_url": "", "alt_text": "única", "title": ""},
        ]

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path

        async def _fake_web(q, max=6):
            return web_results

        monkeypatch.setattr(_web, "search_images_web", _fake_web)

        try:
            results = asyncio.run(_img_mod.search_images_quick("compartilhada", max=6))
        finally:
            _cfg.DB_PATH = orig_db

        urls = [r["img_url"] for r in results]
        assert urls.count(shared_url) == 1, f"URL duplicada apareceu {urls.count(shared_url)}x"
        assert "https://unique.com/x.jpg" in urls
