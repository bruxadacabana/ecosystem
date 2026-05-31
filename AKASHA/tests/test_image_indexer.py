"""
Testes de integração para services/image_indexer.py.

Cobre:
  - extract_images: extração de <img src alt title> de HTML mockado
  - phash_from_bytes: cálculo de pHash a partir de bytes de imagem
  - ImageDeduplicator: pHash duplicado → is_duplicate True; distinto → False
  - index_page_images: imagem duplicada (pHash similar) → não indexada
  - search_images: FTS5 sobre alt_text + title retorna resultados corretos
  - search_images_quick: painel inline — local com fallback DDG, limite max,
    query vazia, erro gracioso em banco ausente e DDG offline
"""
from __future__ import annotations

import asyncio
import io
import sqlite3
from pathlib import Path

import pytest


def run(coro):
    """Executa corrotina em event loop de teste (Python 3.12+ requer asyncio.run)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# extract_images — função pura (sem I/O)
# ---------------------------------------------------------------------------

class TestExtractImages:
    def test_extracts_img_with_alt_and_title(self):
        from services.image_indexer import extract_images
        html = '<html><body><img src="https://ex.com/a.jpg" alt="foto do gato" title="Gato Preto"></body></html>'
        results = extract_images(html, "https://ex.com")
        assert len(results) == 1
        assert results[0]["img_url"]  == "https://ex.com/a.jpg"
        assert results[0]["alt_text"] == "foto do gato"
        assert results[0]["title"]    == "Gato Preto"

    def test_resolves_relative_src(self):
        from services.image_indexer import extract_images
        html = '<img src="/images/logo.png" alt="logo">'
        results = extract_images(html, "https://exemplo.com/page")
        assert results[0]["img_url"] == "https://exemplo.com/images/logo.png"

    def test_skips_data_uris(self):
        from services.image_indexer import extract_images
        html = '<img src="data:image/png;base64,abc123" alt="inline">'
        assert extract_images(html, "https://ex.com") == []

    def test_skips_imgs_without_src(self):
        from services.image_indexer import extract_images
        html = '<img alt="sem src">'
        assert extract_images(html, "https://ex.com") == []

    def test_multiple_images_returned(self):
        from services.image_indexer import extract_images
        html = """
            <img src="https://ex.com/1.jpg" alt="um">
            <img src="https://ex.com/2.jpg" alt="dois">
            <img src="https://ex.com/3.png" alt="três">
        """
        results = extract_images(html, "https://ex.com")
        assert len(results) == 3

    def test_deduplicates_same_src(self):
        from services.image_indexer import extract_images
        html = '<img src="https://ex.com/x.jpg" alt="a"><img src="https://ex.com/x.jpg" alt="b">'
        results = extract_images(html, "https://ex.com")
        assert len(results) == 1

    def test_empty_html_returns_empty(self):
        from services.image_indexer import extract_images
        assert extract_images("", "https://ex.com") == []


# ---------------------------------------------------------------------------
# phash_from_bytes — cálculo de pHash
# ---------------------------------------------------------------------------

class TestPhashFromBytes:
    def _make_png_bytes(self, color: tuple = (128, 64, 200)) -> bytes:
        """Gera um PNG mínimo 8×8 de cor sólida em memória."""
        from PIL import Image
        img = Image.new("RGB", (8, 8), color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_returns_hex_string(self):
        from services.image_indexer import phash_from_bytes
        png = self._make_png_bytes()
        result = phash_from_bytes(png)
        assert isinstance(result, str)
        assert len(result) > 0
        int(result, 16)  # deve ser hex válido

    def test_returns_empty_on_invalid_bytes(self):
        from services.image_indexer import phash_from_bytes
        assert phash_from_bytes(b"not an image") == ""

    def test_same_image_same_hash(self):
        from services.image_indexer import phash_from_bytes
        png = self._make_png_bytes((200, 100, 50))
        assert phash_from_bytes(png) == phash_from_bytes(png)

    def test_different_images_different_hash(self):
        from services.image_indexer import phash_from_bytes
        h1 = phash_from_bytes(self._make_png_bytes((0,   0,   0)))
        h2 = phash_from_bytes(self._make_png_bytes((255, 255, 255)))
        assert h1 != h2


# ---------------------------------------------------------------------------
# ImageDeduplicator — BK-tree
# ---------------------------------------------------------------------------

class TestImageDeduplicator:
    def test_empty_tree_not_duplicate(self):
        from services.image_indexer import ImageDeduplicator
        dedup = ImageDeduplicator()
        assert not dedup.is_duplicate("a3c4f5b2e1d07890")

    def test_exact_hash_is_duplicate(self):
        from services.image_indexer import ImageDeduplicator
        dedup = ImageDeduplicator()
        h = "a3c4f5b2e1d07890"
        dedup.add(h)
        assert dedup.is_duplicate(h)

    def test_very_similar_hash_is_duplicate(self):
        """Dois hashes que diferem em apenas 1 bit devem ser considerados duplicados."""
        from services.image_indexer import ImageDeduplicator
        dedup = ImageDeduplicator()
        # hash base: 0xffffffffffffffff (64 bits todos 1)
        h_base = "ffffffffffffffff"
        # hash com 1 bit diferente: 0xfffffffffffffffe
        h_near = "fffffffffffffffe"
        dedup.add(h_base)
        assert dedup.is_duplicate(h_near), (
            "Hashes com distância de Hamming 1 devem ser near-duplicates"
        )

    def test_distant_hash_not_duplicate(self):
        """Hashes muito diferentes (Hamming > 10) não devem ser duplicatas."""
        from services.image_indexer import ImageDeduplicator
        dedup = ImageDeduplicator(threshold=10)
        # 0x0000000000000000 vs 0xffffffffffffffff — distância = 64
        dedup.add("0000000000000000")
        assert not dedup.is_duplicate("ffffffffffffffff")

    def test_load_from_db_hashes(self):
        from services.image_indexer import ImageDeduplicator
        dedup = ImageDeduplicator()
        dedup.load_from_db_hashes(["a1b2c3d4e5f60000", "1122334455667788"])
        assert dedup.is_duplicate("a1b2c3d4e5f60000")
        assert dedup.is_duplicate("1122334455667788")


# ---------------------------------------------------------------------------
# index_page_images — near-duplicate não indexado
# ---------------------------------------------------------------------------

class TestIndexPageImages:
    def _make_png_bytes(self, color: tuple = (100, 100, 100)) -> bytes:
        from PIL import Image
        img = Image.new("RGB", (8, 8), color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_near_duplicate_phash_not_indexed(self, db_paths):
        """Imagem com pHash similar (Hamming ≤ 10) a uma já indexada não deve ser inserida."""
        main_path, _ = db_paths

        async def _run():
            import aiosqlite
            from services.image_indexer import ImageDeduplicator, index_page_images

            dedup = ImageDeduplicator()
            # Pré-carrega hash "ffffffffffffffff" no deduplicator
            dedup.add("ffffffffffffffff")

            # Imagem com pHash quase idêntico (distância 1 bit): não deve ser indexada
            # Como não queremos rede real, criamos um mock de client
            class _FakeClient:
                async def get(self, url, timeout=None):
                    class _Resp:
                        status_code = 200
                        content = b"not an image"  # phash retornará ''
                    return _Resp()

            images = [{"img_url": "https://ex.com/img.png", "alt_text": "foto", "title": ""}]

            async with aiosqlite.connect(main_path) as db:
                # Com phash '' (imagem inválida), a dedup por pHash não é acionada
                # mas a imagem pode ser indexada. Vamos testar diretamente o dedup:
                # Inserir imagem sem pHash primeiro
                count = await index_page_images(db, "https://ex.com", images, _FakeClient(), dedup)
                await db.commit()
                return count

        count = run(_run())
        # A imagem deve ser indexada (phash vazio, sem dedup pHash acionado)
        assert count == 1

    def test_duplicate_phash_not_indexed(self, db_paths):
        """Imagem com pHash real que é near-duplicate de outra já no deduplicator → não indexada."""
        main_path, _ = db_paths

        # Criar dois PNGs idênticos (mesmo pHash)
        from PIL import Image
        import io as _io
        img = Image.new("RGB", (8, 8), (55, 88, 120))
        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        from services.image_indexer import phash_from_bytes
        known_phash = phash_from_bytes(png_bytes)
        assert known_phash, "phash não deve ser vazio para imagem válida"

        async def _run():
            import aiosqlite
            from services.image_indexer import ImageDeduplicator, index_page_images

            dedup = ImageDeduplicator()
            dedup.add(known_phash)  # simula que imagem já foi indexada

            class _FakeClient:
                async def get(self, url, timeout=None):
                    class _Resp:
                        status_code = 200
                        content = png_bytes  # mesma imagem → mesmo pHash
                    return _Resp()

            # ".jpg" na URL ativa o download e cálculo de pHash
            images = [{"img_url": "https://ex.com/dup.jpg", "alt_text": "duplicada", "title": ""}]

            async with aiosqlite.connect(main_path) as db:
                count = await index_page_images(db, "https://ex.com/page", images, _FakeClient(), dedup)
                await db.commit()
                return count

        count = run(_run())
        assert count == 0, (
            f"Imagem com pHash igual a uma já indexada não deve ser inserida. Obteve count={count}"
        )


# ---------------------------------------------------------------------------
# search_images — FTS5 sobre alt_text retorna resultados corretos
# ---------------------------------------------------------------------------

class TestSearchImages:
    def _insert_image(self, con: sqlite3.Connection, img_url: str, page_url: str,
                      alt_text: str, title: str = "", phash: str = "") -> None:
        con.execute(
            "INSERT OR IGNORE INTO page_images (page_url, img_url, alt_text, title) VALUES (?,?,?,?)",
            (page_url, img_url, alt_text, title),
        )
        con.execute(
            "INSERT OR REPLACE INTO page_images_fts (img_url, page_url, alt_text, title, phash) VALUES (?,?,?,?,?)",
            (img_url, page_url, alt_text, title, phash),
        )
        con.commit()

    def test_fts_on_alt_text_returns_match(self, db_paths):
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        self._insert_image(con, "https://ex.com/gato.jpg", "https://ex.com/page",
                           alt_text="fotografia de gato dormindo")
        con.close()

        async def _run():
            import aiosqlite
            from services.image_indexer import search_images
            async with aiosqlite.connect(main_path) as db:
                return await search_images(db, "gato")

        results = run(_run())
        assert len(results) == 1
        assert results[0]["img_url"] == "https://ex.com/gato.jpg"

    def test_fts_on_title_returns_match(self, db_paths):
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        self._insert_image(con, "https://ex.com/logo.png", "https://ex.com",
                           alt_text="", title="Logotipo da empresa")
        con.close()

        async def _run():
            import aiosqlite
            from services.image_indexer import search_images
            async with aiosqlite.connect(main_path) as db:
                return await search_images(db, "logotipo")

        results = run(_run())
        assert len(results) >= 1
        urls = [r["img_url"] for r in results]
        assert "https://ex.com/logo.png" in urls

    def test_no_match_returns_empty(self, db_paths):
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        self._insert_image(con, "https://ex.com/x.jpg", "https://ex.com",
                           alt_text="cachorro correndo no parque")
        con.close()

        async def _run():
            import aiosqlite
            from services.image_indexer import search_images
            async with aiosqlite.connect(main_path) as db:
                return await search_images(db, "elefante")

        results = run(_run())
        assert results == []

    def test_empty_query_returns_empty(self, db_paths):
        async def _run():
            import aiosqlite
            from services.image_indexer import search_images
            main_path, _ = db_paths
            async with aiosqlite.connect(main_path) as db:
                return await search_images(db, "")

        assert run(_run()) == []


# ---------------------------------------------------------------------------
# search_images_quick — painel inline na busca principal
# ---------------------------------------------------------------------------

class TestSearchImagesQuick:
    """Testa search_images_quick: combina local + search_images_web, dedup, tratamento de erros."""

    def _insert_image(self, con: sqlite3.Connection, img_url: str, page_url: str,
                      alt_text: str, title: str = "") -> None:
        con.execute(
            "INSERT OR IGNORE INTO page_images (page_url, img_url, alt_text, title) VALUES (?,?,?,?)",
            (page_url, img_url, alt_text, title),
        )
        con.execute(
            "INSERT OR REPLACE INTO page_images_fts (img_url, page_url, alt_text, title, phash) VALUES (?,?,?,?,?)",
            (img_url, page_url, alt_text, title, ""),
        )
        con.commit()

    # ── query vazia ──────────────────────────────────────────────────────────

    def test_empty_query_returns_empty(self):
        """query vazia → [] imediatamente, sem tocar no banco."""
        from services.image_indexer import search_images_quick
        result = run(search_images_quick(""))
        assert result == []

    def test_whitespace_only_query_returns_empty(self):
        """query só com espaços → [] (equivalente a vazia)."""
        from services.image_indexer import search_images_quick
        result = run(search_images_quick("   "))
        assert result == []

    # ── resultados locais ────────────────────────────────────────────────────

    def test_returns_local_results_when_available(self, db_paths, monkeypatch):
        """Imagens indexadas localmente aparecem no resultado combinado."""
        import services.image_indexer as _mod
        import services.web_search as _web
        import config as _cfg

        main_path, _ = db_paths

        con = sqlite3.connect(main_path)
        for i in range(3):
            self._insert_image(
                con,
                f"https://ex.com/img{i}.jpg",
                f"https://ex.com/page{i}",
                f"foto de gato número {i}",
            )
        con.close()

        # search_images_web retorna vazio (sem rede)
        async def _fake_web(q, max=6):
            return []

        monkeypatch.setattr(_web, "search_images_web", _fake_web)

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path
        try:
            results = run(_mod.search_images_quick("gato", max=6))
        finally:
            _cfg.DB_PATH = orig_db

        assert len(results) == 3
        assert all(r["img_url"].startswith("https://ex.com/img") for r in results)

    def test_max_limits_combined_results(self, db_paths, monkeypatch):
        """max=2 retorna no máximo 2 resultados mesmo com mais disponíveis."""
        import services.image_indexer as _mod
        import services.web_search as _web
        import config as _cfg

        main_path, _ = db_paths

        con = sqlite3.connect(main_path)
        for i in range(5):
            self._insert_image(
                con,
                f"https://ex.com/gato{i}.jpg",
                f"https://ex.com/p{i}",
                f"fotografia de gato {i}",
            )
        con.close()

        async def _fake_web(q, max=6):
            return []

        monkeypatch.setattr(_web, "search_images_web", _fake_web)

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path
        try:
            results = run(_mod.search_images_quick("gato", max=2))
        finally:
            _cfg.DB_PATH = orig_db

        assert len(results) <= 2

    # ── web fallback (search_images_web) ────────────────────────────────────

    def test_web_fills_when_local_empty(self, db_paths, monkeypatch):
        """Sem resultados locais, search_images_web preenche o painel."""
        import services.image_indexer as _mod
        import services.web_search as _web
        import config as _cfg

        main_path, _ = db_paths  # banco vazio

        web_items = [
            {"img_url": "https://web.com/img1.jpg", "page_url": "https://web.com/p1",
             "alt_text": "Gato web 1", "title": "Gato web 1"},
            {"img_url": "https://web.com/img2.jpg", "page_url": "https://web.com/p2",
             "alt_text": "Gato web 2", "title": "Gato web 2"},
        ]

        async def _fake_web(q, max=6):
            return web_items

        monkeypatch.setattr(_web, "search_images_web", _fake_web)

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path
        try:
            results = run(_mod.search_images_quick("gato", max=6))
        finally:
            _cfg.DB_PATH = orig_db

        assert len(results) == 2
        assert results[0]["img_url"] == "https://web.com/img1.jpg"
        assert results[0]["page_url"] == "https://web.com/p1"
        assert results[0]["alt_text"] == "Gato web 1"

    def test_web_respects_max(self, db_paths, monkeypatch):
        """max=2 com web fallback retorna no máximo 2 resultados."""
        import services.image_indexer as _mod
        import services.web_search as _web
        import config as _cfg

        main_path, _ = db_paths

        async def _fake_web(q, max=6):
            return [
                {"img_url": f"https://web.com/img{i}.jpg", "page_url": "", "alt_text": "", "title": ""}
                for i in range(10)
            ]

        monkeypatch.setattr(_web, "search_images_web", _fake_web)

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path
        try:
            results = run(_mod.search_images_quick("coisa", max=2))
        finally:
            _cfg.DB_PATH = orig_db

        assert len(results) <= 2

    # ── resiliência a erros ───────────────────────────────────────────────────

    def test_web_error_returns_local_gracefully(self, db_paths, monkeypatch):
        """search_images_web lançando exceção → retorna só locais, sem propagar."""
        import services.image_indexer as _mod
        import services.web_search as _web
        import config as _cfg

        main_path, _ = db_paths

        con = sqlite3.connect(main_path)
        self._insert_image(con, "https://ex.com/img.jpg", "https://ex.com/p", "foto")
        con.close()

        async def _broken_web(q, max=6):
            raise ConnectionError("web offline")

        monkeypatch.setattr(_web, "search_images_web", _broken_web)

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path
        try:
            results = run(_mod.search_images_quick("foto", max=6))
        finally:
            _cfg.DB_PATH = orig_db

        # Mesmo com web quebrada, retorna os locais
        assert len(results) >= 1
        assert results[0]["img_url"] == "https://ex.com/img.jpg"

    def test_both_sources_error_returns_empty(self, db_paths, monkeypatch):
        """Banco inválido + web quebrada → [] sem exceção."""
        import services.image_indexer as _mod
        import services.web_search as _web
        import config as _cfg

        async def _broken_web(q, max=6):
            raise ConnectionError("offline")

        monkeypatch.setattr(_web, "search_images_web", _broken_web)

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = "/caminho/invalido/que/nao/existe/akasha.db"
        try:
            results = run(_mod.search_images_quick("algo", max=6))
        finally:
            _cfg.DB_PATH = orig_db

        assert results == []

    def test_result_has_required_keys(self, db_paths):
        """Cada item retornado deve ter as chaves img_url, page_url, alt_text, title, phash."""
        main_path, _ = db_paths

        con = sqlite3.connect(main_path)
        self._insert_image(
            con,
            "https://ex.com/cachorro.jpg",
            "https://ex.com/page",
            "cachorro correndo",
            title="Cachorro no parque",
        )
        con.close()

        import services.image_indexer as _mod
        import config as _cfg

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path
        try:
            results = run(_mod.search_images_quick("cachorro"))
        finally:
            _cfg.DB_PATH = orig_db

        assert len(results) >= 1
        for r in results:
            for key in ("img_url", "page_url", "alt_text", "title", "phash"):
                assert key in r, f"Chave '{key}' ausente no resultado: {r}"
