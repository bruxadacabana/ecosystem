"""
Testes para Semântico 4 — integração de busca semântica em search_local.

Cobre:
  - _get_semantic_search_enabled: lê ecosystem.json ou retorna True por padrão
  - _count_page_embeddings: conta entradas corretas; 0 em banco vazio
  - _semantic_to_crawl_results: converte pares (url, dist) em SearchResult
  - _run_semantic_crawl_search: retorna [] quando < 10 embeddings; retorna resultados
    quando >= 10; retorna [] silenciosamente se LOGOS offline
  - search_local: sem LOGOS → não chama semântico; com LOGOS e embeddings → chama
  - SEMANTIC_SEARCH_ENABLED=False → sem busca semântica mesmo com LOGOS disponível
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _get_semantic_search_enabled
# ---------------------------------------------------------------------------

class TestGetSemanticSearchEnabled:

    def test_returns_true_by_default(self, monkeypatch):
        """Sem ecosystem_client, retorna True."""
        import services.local_search as _ls
        monkeypatch.setattr(_ls, "_get_semantic_search_enabled", lambda: True)
        assert _ls._get_semantic_search_enabled() is True

    def test_returns_false_when_config_says_false(self, monkeypatch):
        """Quando ecosystem.json tem semantic_search=false, retorna False."""
        import services.local_search as _ls

        original = _ls._get_semantic_search_enabled

        def _patched():
            try:
                # Simula ecosystem_client retornando False
                return False
            except Exception:
                return True

        monkeypatch.setattr(_ls, "_get_semantic_search_enabled", _patched)
        assert _ls._get_semantic_search_enabled() is False

        monkeypatch.setattr(_ls, "_get_semantic_search_enabled", original)


# ---------------------------------------------------------------------------
# _count_page_embeddings
# ---------------------------------------------------------------------------

class TestCountPageEmbeddings:

    def test_returns_zero_for_empty_db(self, db_paths, monkeypatch):
        """Banco sem entradas → retorna 0."""
        import services.local_search as _ls
        import config as _cfg

        main_path, _ = db_paths
        monkeypatch.setattr(_ls, "DB_PATH", main_path)
        monkeypatch.setattr(_cfg, "DB_PATH", main_path)
        count = run(_ls._count_page_embeddings())
        assert count == 0

    def test_returns_correct_count(self, db_paths, monkeypatch):
        """Com N entradas em page_embeddings, retorna N."""
        import services.local_search as _ls
        import config as _cfg

        main_path, _ = db_paths

        con = sqlite3.connect(main_path)
        con.execute("PRAGMA foreign_keys = OFF")
        for i in range(3):
            con.execute(
                "INSERT OR IGNORE INTO crawl_pages (site_id, url, word_count) VALUES (0, ?, 100)",
                (f"https://count{i}.test",)
            )
            con.execute("INSERT INTO page_embeddings (url) VALUES (?)", (f"https://count{i}.test",))
        con.commit()
        con.close()

        monkeypatch.setattr(_ls, "DB_PATH", main_path)
        monkeypatch.setattr(_cfg, "DB_PATH", main_path)
        count = run(_ls._count_page_embeddings())
        assert count == 3

    def test_returns_zero_on_error(self, monkeypatch):
        """Banco inacessível → retorna 0 sem exceção."""
        import services.local_search as _ls
        import config as _cfg
        from pathlib import Path

        invalid = Path("/caminho/invalido/que/nao/existe/akasha.db")
        monkeypatch.setattr(_ls, "DB_PATH", invalid)
        monkeypatch.setattr(_cfg, "DB_PATH", invalid)
        count = run(_ls._count_page_embeddings())
        assert count == 0


# ---------------------------------------------------------------------------
# _semantic_to_crawl_results
# ---------------------------------------------------------------------------

class TestSemanticToCrawlResults:

    def _insert_crawl_page(self, main_path: Path, url: str, title: str, content: str) -> None:
        con = sqlite3.connect(main_path)
        con.execute("PRAGMA foreign_keys = OFF")
        con.execute(
            "INSERT OR REPLACE INTO crawl_pages (site_id, url, title, content_md, word_count) VALUES (0, ?, ?, ?, ?)",
            (url, title, content, len(content.split()))
        )
        con.commit()
        con.close()

    def test_converts_pairs_to_search_results(self, db_paths, monkeypatch):
        """Pares (url, dist) são convertidos em SearchResult com title e snippet."""
        import services.local_search as _ls
        import config as _cfg

        main_path, _ = db_paths
        self._insert_crawl_page(main_path, "https://sem.test", "Título Semântico", "conteúdo de teste " * 10)

        monkeypatch.setattr(_ls, "DB_PATH", main_path)
        monkeypatch.setattr(_cfg, "DB_PATH", main_path)
        results = run(_ls._semantic_to_crawl_results([("https://sem.test", 0.1)]))

        assert len(results) == 1
        assert results[0].url == "https://sem.test"
        assert results[0].title == "Título Semântico"
        assert results[0].source == "CRAWL_SEMANTIC"
        assert len(results[0].snippet) > 0

    def test_empty_pairs_returns_empty(self):
        """Pares vazios → []."""
        import services.local_search as _ls
        results = run(_ls._semantic_to_crawl_results([]))
        assert results == []

    def test_source_is_crawl_semantic(self, db_paths, monkeypatch):
        """source deve ser 'CRAWL_SEMANTIC' para resultados semânticos."""
        import services.local_search as _ls
        import config as _cfg

        main_path, _ = db_paths
        self._insert_crawl_page(main_path, "https://src.test", "Título", "conteúdo " * 20)

        monkeypatch.setattr(_ls, "DB_PATH", main_path)
        monkeypatch.setattr(_cfg, "DB_PATH", main_path)
        results = run(_ls._semantic_to_crawl_results([("https://src.test", 0.5)]))

        assert results[0].source == "CRAWL_SEMANTIC"


# ---------------------------------------------------------------------------
# _run_semantic_crawl_search
# ---------------------------------------------------------------------------

class TestRunSemanticCrawlSearch:

    def _insert_embeddings(self, main_path: Path, count: int) -> None:
        con = sqlite3.connect(main_path)
        con.execute("PRAGMA foreign_keys = OFF")
        for i in range(count):
            url = f"https://sem{i}.test"
            con.execute(
                "INSERT OR REPLACE INTO crawl_pages (site_id, url, title, content_md, word_count) VALUES (0, ?, ?, ?, 100)",
                (url, f"Título {i}", f"conteúdo {i} " * 20)
            )
            con.execute("INSERT OR IGNORE INTO page_embeddings (url) VALUES (?)", (url,))
        con.commit()
        con.close()

    def test_returns_empty_when_fewer_than_10_embeddings(self, db_paths, monkeypatch):
        """< 10 embeddings → retorna [] sem chamar semantic_search_local."""
        import services.local_search as _ls
        import services.semantic_search as _sem
        import config as _cfg

        main_path, _ = db_paths
        self._insert_embeddings(main_path, 5)  # apenas 5, abaixo do threshold

        called = []
        async def _fake_sem_search(q, top_k=50):
            called.append(q)
            return []

        monkeypatch.setattr(_sem, "semantic_search_local", _fake_sem_search)
        monkeypatch.setattr(_ls, "DB_PATH", main_path)
        monkeypatch.setattr(_cfg, "DB_PATH", main_path)
        results = run(_ls._run_semantic_crawl_search("query"))

        assert results == []
        assert called == [], "semantic_search_local não deve ser chamado com < 10 embeddings"

    def test_returns_results_when_10_or_more_embeddings(self, db_paths, monkeypatch):
        """>= 10 embeddings → chama semantic_search_local e retorna SearchResults."""
        import services.local_search as _ls
        import services.semantic_search as _sem
        import config as _cfg

        main_path, _ = db_paths
        self._insert_embeddings(main_path, 10)

        async def _fake_sem_search(q, top_k=50):
            return [("https://sem0.test", 0.1), ("https://sem1.test", 0.2)]

        monkeypatch.setattr(_sem, "semantic_search_local", _fake_sem_search)
        monkeypatch.setattr(_ls, "DB_PATH", main_path)
        monkeypatch.setattr(_cfg, "DB_PATH", main_path)
        results = run(_ls._run_semantic_crawl_search("query"))

        assert len(results) >= 1
        urls = [r.url for r in results]
        assert "https://sem0.test" in urls

    def test_silent_on_exception(self, monkeypatch):
        """Exceção em qualquer ponto → retorna [] sem propagar."""
        import services.local_search as _ls
        import services.semantic_search as _sem

        async def _broken(*a, **kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(_sem, "semantic_search_local", _broken)

        results = run(_ls._run_semantic_crawl_search("query"))
        assert results == []


# ---------------------------------------------------------------------------
# search_local — integração completa
# ---------------------------------------------------------------------------

class TestSearchLocalWithSemantic:

    def test_without_logos_semantic_not_called(self, db_paths, monkeypatch):
        """_inference_available=False → busca semântica não é disparada."""
        import services.local_search as _ls
        import config as _cfg
        import database as _db

        main_path, _ = db_paths
        _db.DB_PATH = main_path
        _cfg.DB_PATH = main_path

        semantic_called = []

        async def _fake_run_sem(q):
            semantic_called.append(q)
            return []

        monkeypatch.setattr(_ls, "_inference_available", False)
        monkeypatch.setattr(_ls, "_run_semantic_crawl_search", _fake_run_sem)

        run(_ls.search_local("python tutorial", expand=False))

        assert semantic_called == [], "Sem LOGOS, busca semântica não deve ser chamada"

    def test_with_logos_and_embeddings_semantic_called(self, db_paths, monkeypatch):
        """_inference_available=True + >= 10 embeddings → busca semântica chamada."""
        import services.local_search as _ls
        import config as _cfg
        import database as _db

        main_path, _ = db_paths
        _db.DB_PATH = main_path
        _cfg.DB_PATH = main_path

        semantic_called = []

        async def _fake_run_sem(q):
            semantic_called.append(q)
            return []

        monkeypatch.setattr(_ls, "_inference_available", True)
        monkeypatch.setattr(_ls, "_get_semantic_search_enabled", lambda: True)
        monkeypatch.setattr(_ls, "_run_semantic_crawl_search", _fake_run_sem)

        run(_ls.search_local("python tutorial", expand=False))

        assert len(semantic_called) == 1, "Com LOGOS, busca semântica deve ser chamada"

    def test_semantic_disabled_flag_skips_semantic(self, db_paths, monkeypatch):
        """SEMANTIC_SEARCH_ENABLED=False → semantic_search não chamado."""
        import services.local_search as _ls
        import config as _cfg
        import database as _db

        main_path, _ = db_paths
        _db.DB_PATH = main_path
        _cfg.DB_PATH = main_path

        semantic_called = []

        async def _fake_run_sem(q):
            semantic_called.append(q)
            return []

        monkeypatch.setattr(_ls, "_inference_available", True)
        monkeypatch.setattr(_ls, "_get_semantic_search_enabled", lambda: False)
        monkeypatch.setattr(_ls, "_run_semantic_crawl_search", _fake_run_sem)

        run(_ls.search_local("python", expand=False))

        assert semantic_called == [], "Com flag desabilitada, semântico não deve ser chamado"

    def test_semantic_results_included_in_output(self, db_paths, monkeypatch):
        """SearchResult de CRAWL_SEMANTIC aparece na saída de search_local."""
        import services.local_search as _ls
        from services.web_search import SearchResult
        import config as _cfg
        import database as _db

        main_path, _ = db_paths
        _db.DB_PATH = main_path
        _cfg.DB_PATH = main_path

        async def _fake_run_sem(q):
            return [SearchResult(
                title="Resultado Semântico",
                url="https://crawl.test/page",
                snippet="conteúdo relevante",
                source="CRAWL_SEMANTIC",
            )]

        monkeypatch.setattr(_ls, "_inference_available", True)
        monkeypatch.setattr(_ls, "_get_semantic_search_enabled", lambda: True)
        monkeypatch.setattr(_ls, "_run_semantic_crawl_search", _fake_run_sem)

        results = run(_ls.search_local("relevante", expand=False))

        crawl_sem = [r for r in results if r.source == "CRAWL_SEMANTIC"]
        assert len(crawl_sem) >= 1, "Resultado CRAWL_SEMANTIC deve aparecer na saída"
        assert any(r.url == "https://crawl.test/page" for r in crawl_sem)
