"""
Testes para services/semantic_search.py (Semântico 2).

Cobre:
  - embed_text: LOGOS mockado → retorna lista de floats; LOGOS offline → None
  - embed_and_store: insere em page_embeddings e page_vec; LOGOS offline → silencioso
  - semantic_search_local: retorna URLs por distância KNN; LOGOS offline → []
  - hybrid_rrf: fusão correta; URL em ambas as listas com rank alto → score máximo;
    URL só em uma lista; listas vazias; k de separação correto
"""
from __future__ import annotations

import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_EMBEDDING_768 = [0.1] * 768


def _make_logos_mock(embedding: list[float] = _FAKE_EMBEDDING_768) -> MagicMock:
    """Mock de httpx.AsyncClient que retorna embedding LOGOS."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": [{"embedding": embedding}]}
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)
    return mock_client


# ---------------------------------------------------------------------------
# embed_text
# ---------------------------------------------------------------------------

class TestEmbedText:

    def test_returns_list_when_logos_online(self):
        """LOGOS disponível → retorna lista de floats com comprimento correto."""
        from services.semantic_search import embed_text

        with patch("httpx.AsyncClient", return_value=_make_logos_mock()):
            result = run(embed_text("pesquisa semântica"))

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 768
        assert all(isinstance(v, float) for v in result)

    def test_returns_none_when_logos_offline(self):
        """LOGOS offline (ConnectError) → retorna None sem propagar."""
        import httpx
        from services.semantic_search import embed_text

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("offline"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = run(embed_text("test"))

        assert result is None

    def test_empty_text_returns_none(self):
        """Query vazia → None sem chamar LOGOS."""
        from services.semantic_search import embed_text
        result = run(embed_text(""))
        assert result is None

    def test_whitespace_text_returns_none(self):
        """Query só espaços → None."""
        from services.semantic_search import embed_text
        result = run(embed_text("   "))
        assert result is None

    def test_truncates_long_input(self):
        """Textos longos são truncados para ~2000 chars (não deve falhar)."""
        from services.semantic_search import embed_text

        with patch("httpx.AsyncClient", return_value=_make_logos_mock()) as mock_cls:
            run(embed_text("x" * 10_000))

        # Verifica que o payload enviado foi truncado
        call_kwargs = mock_cls.return_value.post.call_args
        payload = call_kwargs[1]["json"] if call_kwargs[1] else call_kwargs[0][1]
        assert len(payload["input"][0]) <= 2001


# ---------------------------------------------------------------------------
# embed_and_store
# ---------------------------------------------------------------------------

class TestEmbedAndStore:

    def test_inserts_in_both_tables(self, db_paths, monkeypatch):
        """embed_and_store com LOGOS mockado cria entrada em page_embeddings e page_vec."""
        try:
            import sqlite_vec  # noqa: F401
        except ImportError:
            pytest.skip("sqlite_vec não disponível")

        import services.semantic_search as _mod
        import config as _cfg

        main_path, _ = db_paths

        # Setup page
        con = sqlite3.connect(main_path)
        con.execute("PRAGMA foreign_keys = OFF")
        con.execute("INSERT OR REPLACE INTO crawl_pages (site_id, url, word_count) VALUES (0, 'https://store.test', 100)")
        con.commit()
        con.close()

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path
        try:
            run(_mod._ensure_page_vec_table())
            with patch("httpx.AsyncClient", return_value=_make_logos_mock()):
                run(_mod.embed_and_store("https://store.test", "conteúdo de teste com muitas palavras"))
        finally:
            _cfg.DB_PATH = orig_db

        con = sqlite3.connect(main_path)
        con.enable_load_extension(True)
        import sqlite_vec as sv
        sv.load(con)
        con.enable_load_extension(False)

        emb = con.execute("SELECT id FROM page_embeddings WHERE url = 'https://store.test'").fetchone()
        assert emb is not None, "page_embeddings não foi preenchida"

        rows = con.execute("SELECT rowid FROM page_vec WHERE rowid = ?", (emb[0],)).fetchall()
        assert len(rows) == 1, "page_vec não recebeu o vetor"
        con.close()

    def test_logos_offline_is_silent(self, db_paths, monkeypatch):
        """LOGOS offline → embed_and_store retorna sem erro, sem inserir."""
        try:
            import sqlite_vec  # noqa: F401
        except ImportError:
            pytest.skip("sqlite_vec não disponível")

        import httpx
        import services.semantic_search as _mod
        import config as _cfg

        main_path, _ = db_paths

        con = sqlite3.connect(main_path)
        con.execute("PRAGMA foreign_keys = OFF")
        con.execute("INSERT OR REPLACE INTO crawl_pages (site_id, url, word_count) VALUES (0, 'https://offline.test', 100)")
        con.commit()
        con.close()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("offline"))

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path
        try:
            run(_mod._ensure_page_vec_table())
            with patch("httpx.AsyncClient", return_value=mock_client):
                run(_mod.embed_and_store("https://offline.test", "conteúdo"))
        finally:
            _cfg.DB_PATH = orig_db

        con = sqlite3.connect(main_path)
        row = con.execute("SELECT id FROM page_embeddings WHERE url = 'https://offline.test'").fetchone()
        con.close()
        assert row is None, "Nenhuma entrada deve ser criada quando LOGOS está offline"

    def test_upserts_existing_embedding(self, db_paths):
        """embed_and_store chamado duas vezes para a mesma URL atualiza o vetor."""
        try:
            import sqlite_vec  # noqa: F401
        except ImportError:
            pytest.skip("sqlite_vec não disponível")

        import services.semantic_search as _mod
        import config as _cfg

        main_path, _ = db_paths

        con = sqlite3.connect(main_path)
        con.execute("PRAGMA foreign_keys = OFF")
        con.execute("INSERT OR REPLACE INTO crawl_pages (site_id, url, word_count) VALUES (0, 'https://upsert.test', 100)")
        con.commit()
        con.close()

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path
        try:
            run(_mod._ensure_page_vec_table())
            with patch("httpx.AsyncClient", return_value=_make_logos_mock([0.1] * 768)):
                run(_mod.embed_and_store("https://upsert.test", "primeira vez"))
            with patch("httpx.AsyncClient", return_value=_make_logos_mock([0.9] * 768)):
                run(_mod.embed_and_store("https://upsert.test", "segunda vez"))
        finally:
            _cfg.DB_PATH = orig_db

        con = sqlite3.connect(main_path)
        rows = con.execute("SELECT id FROM page_embeddings WHERE url = 'https://upsert.test'").fetchall()
        assert len(rows) == 1, "URL deve aparecer uma única vez em page_embeddings"
        con.close()


# ---------------------------------------------------------------------------
# semantic_search_local
# ---------------------------------------------------------------------------

class TestSemanticSearchLocal:

    def _insert_embedding(self, main_path, url: str, vec: list[float]) -> None:
        import sqlite_vec as sv
        con = sqlite3.connect(main_path)
        con.execute("PRAGMA foreign_keys = OFF")
        con.enable_load_extension(True)
        sv.load(con)
        con.enable_load_extension(False)
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS page_vec USING vec0(embedding float[768])")
        con.execute("INSERT OR REPLACE INTO crawl_pages (site_id, url, word_count) VALUES (0, ?, 100)", (url,))
        cur = con.execute("INSERT INTO page_embeddings (url) VALUES (?)", (url,))
        emb_id = cur.lastrowid
        con.execute("INSERT INTO page_vec(rowid, embedding) VALUES (?, ?)",
                    (emb_id, sv.serialize_float32(vec)))
        con.commit()
        con.close()

    def test_returns_urls_by_knn_distance(self, db_paths):
        """Vetor idêntico à query retorna distância ~0 em primeiro lugar."""
        try:
            import sqlite_vec  # noqa: F401
        except ImportError:
            pytest.skip("sqlite_vec não disponível")

        import services.semantic_search as _mod
        import config as _cfg

        main_path, _ = db_paths

        exact_vec = [1.0] * 768
        self._insert_embedding(main_path, "https://exact.test", exact_vec)

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path
        try:
            with patch("httpx.AsyncClient", return_value=_make_logos_mock(exact_vec)):
                results = run(_mod.semantic_search_local("query semântica", top_k=10))
        finally:
            _cfg.DB_PATH = orig_db

        assert len(results) >= 1
        assert results[0][0] == "https://exact.test"
        assert results[0][1] == pytest.approx(0.0, abs=1e-4)

    def test_logos_offline_returns_empty(self, db_paths):
        """LOGOS offline → [] sem exceção."""
        import httpx
        import services.semantic_search as _mod
        import config as _cfg

        main_path, _ = db_paths

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("offline"))

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path
        try:
            with patch("httpx.AsyncClient", return_value=mock_client):
                results = run(_mod.semantic_search_local("query"))
        finally:
            _cfg.DB_PATH = orig_db

        assert results == []

    def test_returns_list_of_tuples(self, db_paths):
        """Cada item do resultado deve ser (url: str, distance: float)."""
        try:
            import sqlite_vec  # noqa: F401
        except ImportError:
            pytest.skip("sqlite_vec não disponível")

        import services.semantic_search as _mod
        import config as _cfg

        main_path, _ = db_paths
        vec = [0.5] * 768
        self._insert_embedding(main_path, "https://tuple.test", vec)

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path
        try:
            with patch("httpx.AsyncClient", return_value=_make_logos_mock(vec)):
                results = run(_mod.semantic_search_local("query"))
        finally:
            _cfg.DB_PATH = orig_db

        for item in results:
            assert isinstance(item, tuple) and len(item) == 2
            assert isinstance(item[0], str)
            assert isinstance(item[1], float)


# ---------------------------------------------------------------------------
# hybrid_rrf
# ---------------------------------------------------------------------------

class TestHybridRRF:

    def test_url_in_both_lists_ranks_highest(self):
        """URL com rank 1 em ambas as listas deve ter score maior que qualquer outra."""
        from services.semantic_search import hybrid_rrf

        lexical = ["https://a.com", "https://b.com", "https://c.com"]
        semantic = [("https://a.com", 0.1), ("https://d.com", 0.2), ("https://e.com", 0.3)]

        result = hybrid_rrf(lexical, semantic)

        assert result[0] == "https://a.com", (
            "URL com rank 1 em ambas as listas deve ser o primeiro resultado"
        )

    def test_url_only_in_lexical_contributes(self):
        """URL presente só em lexical deve aparecer no resultado com contribuição lexical."""
        from services.semantic_search import hybrid_rrf

        lexical = ["https://only-lex.com"]
        semantic: list[tuple[str, float]] = []

        result = hybrid_rrf(lexical, semantic)
        assert "https://only-lex.com" in result

    def test_url_only_in_semantic_contributes(self):
        """URL presente só em semantic deve aparecer no resultado com contribuição vetorial."""
        from services.semantic_search import hybrid_rrf

        lexical: list[str] = []
        semantic = [("https://only-sem.com", 0.05)]

        result = hybrid_rrf(lexical, semantic)
        assert "https://only-sem.com" in result

    def test_empty_lists_return_empty(self):
        """Ambas as listas vazias → resultado vazio."""
        from services.semantic_search import hybrid_rrf
        assert hybrid_rrf([], []) == []

    def test_order_preserves_combined_rank(self):
        """Resultado ordenado por score descendente (URL dupla > URL simples)."""
        from services.semantic_search import hybrid_rrf

        lexical = ["https://shared.com", "https://lex-only.com"]
        semantic = [("https://shared.com", 0.0), ("https://sem-only.com", 0.1)]

        result = hybrid_rrf(lexical, semantic)

        # shared.com está em ambas → score maior, deve ser primeiro
        pos_shared = result.index("https://shared.com")
        pos_lex = result.index("https://lex-only.com")
        pos_sem = result.index("https://sem-only.com")

        assert pos_shared < pos_lex, "shared deve preceder lex-only"
        assert pos_shared < pos_sem, "shared deve preceder sem-only"

    def test_scores_use_correct_weights(self):
        """Score = 0.6×(1/(k+r_bm25)) + 0.4×(1/(k+r_vec)) com k=60."""
        from services.semantic_search import hybrid_rrf

        # URL A: rank 1 em lexical, ausente em semantic
        # URL B: ausente em lexical, rank 1 em semantic
        # Score A = 0.6/(60+1) + 0.4/(60+2) ≈ 0.00984 + 0.00645 ≈ 0.01629
        # Score B = 0.6/(60+2) + 0.4/(60+1) ≈ 0.00968 + 0.00656 ≈ 0.01623
        # A deve ter score levemente maior (0.6 > 0.4)

        lexical = ["https://A.com"]
        semantic = [("https://B.com", 0.0)]

        result = hybrid_rrf(lexical, semantic, k=60)
        assert result[0] == "https://A.com", (
            "Com peso lexical 0.6 > semântico 0.4, A (rank 1 BM25) "
            "deve preceder B (rank 1 vec) quando ausentes na outra lista"
        )

    def test_all_urls_present_in_result(self):
        """Todas as URLs das duas listas devem aparecer no resultado."""
        from services.semantic_search import hybrid_rrf

        lexical = ["https://l1.com", "https://l2.com"]
        semantic = [("https://s1.com", 0.1), ("https://l1.com", 0.2)]

        result = hybrid_rrf(lexical, semantic)
        assert set(result) == {"https://l1.com", "https://l2.com", "https://s1.com"}
