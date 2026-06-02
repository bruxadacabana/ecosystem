"""
Testes de integração para services/pagerank.py.

Cobre:
  - extract_links: extração de hrefs de HTML, normalização, filtragem
  - store_page_links: gravação de arestas no DB
  - compute_pagerank: grafo simples → score calculado; semente → score ≥ 1.0; range 0.8–1.2
  - get_page_rank_scores: batch lookup; URL desconhecida → 1.0
  - autoridade por in-links: página com 5 in-links > página com 1 (critério do TODO)
  - run_pagerank_refresh: wrapper de produção popula page_rank; grafo vazio → 0; erro → 0
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixture: DB com schema AKASHA
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_paths(tmp_path):
    import database as _db

    main_path = tmp_path / "akasha.db"
    knowledge_path = tmp_path / "akasha_knowledge.db"

    orig_db  = _db.DB_PATH
    orig_kdb = _db.KNOWLEDGE_DB_PATH
    _db.DB_PATH = main_path
    _db.KNOWLEDGE_DB_PATH = knowledge_path

    run(_db.init_db())

    yield main_path, knowledge_path

    _db.DB_PATH = orig_db
    _db.KNOWLEDGE_DB_PATH = orig_kdb


# ---------------------------------------------------------------------------
# extract_links — função pura
# ---------------------------------------------------------------------------

class TestExtractLinks:
    def test_extracts_absolute_hrefs(self):
        from services.pagerank import extract_links
        html = '<a href="https://example.com/page">link</a>'
        result = extract_links(html, "https://example.com")
        assert "https://example.com/page" in result

    def test_resolves_relative_hrefs(self):
        from services.pagerank import extract_links
        html = '<a href="/about">sobre</a>'
        result = extract_links(html, "https://example.com/home")
        assert "https://example.com/about" in result

    def test_skips_fragment_only(self):
        from services.pagerank import extract_links
        html = '<a href="#section">ancora</a>'
        result = extract_links(html, "https://example.com")
        assert result == []

    def test_skips_mailto_and_javascript(self):
        from services.pagerank import extract_links
        html = '<a href="mailto:a@b.com">email</a><a href="javascript:void(0)">js</a>'
        result = extract_links(html, "https://example.com")
        assert result == []

    def test_deduplicates_same_url(self):
        from services.pagerank import extract_links
        html = '<a href="https://ex.com/p">1</a><a href="https://ex.com/p">2</a>'
        result = extract_links(html, "https://ex.com")
        assert result.count("https://ex.com/p") == 1

    def test_known_domains_filter(self):
        from services.pagerank import extract_links
        html = (
            '<a href="https://lib.com/page">in</a>'
            '<a href="https://external.com/x">out</a>'
        )
        result = extract_links(html, "https://lib.com", known_domains=frozenset({"lib.com"}))
        assert "https://lib.com/page" in result
        assert "https://external.com/x" not in result

    def test_empty_html_returns_empty(self):
        from services.pagerank import extract_links
        assert extract_links("", "https://example.com") == []

    def test_no_self_links(self):
        """Link para a própria URL não deve ser armazenado."""
        from services.pagerank import extract_links
        html = '<a href="https://example.com/page">self</a>'
        result = extract_links(html, "https://example.com/page")
        assert "https://example.com/page" not in result


# ---------------------------------------------------------------------------
# store_page_links + persistência
# ---------------------------------------------------------------------------

class TestStorePageLinks:
    def test_stores_edges_in_db(self, db_paths):
        main_path, _ = db_paths

        async def _run():
            import aiosqlite
            from services.pagerank import store_page_links
            async with aiosqlite.connect(main_path) as db:
                await store_page_links(db, "https://a.com/p1", ["https://b.com/p2", "https://c.com/p3"])
                await db.commit()
                rows = await (await db.execute("SELECT source_url, target_url FROM page_links")).fetchall()
                return rows

        rows = run(_run())
        assert len(rows) == 2
        targets = {r[1] for r in rows}
        assert "https://b.com/p2" in targets
        assert "https://c.com/p3" in targets

    def test_insert_is_idempotent(self, db_paths):
        main_path, _ = db_paths

        async def _run():
            import aiosqlite
            from services.pagerank import store_page_links
            async with aiosqlite.connect(main_path) as db:
                await store_page_links(db, "https://a.com", ["https://b.com"])
                await store_page_links(db, "https://a.com", ["https://b.com"])
                await db.commit()
                rows = await (await db.execute("SELECT COUNT(*) FROM page_links")).fetchone()
                return rows[0]

        assert run(_run()) == 1

    def test_empty_targets_noop(self, db_paths):
        main_path, _ = db_paths

        async def _run():
            import aiosqlite
            from services.pagerank import store_page_links
            async with aiosqlite.connect(main_path) as db:
                await store_page_links(db, "https://a.com", [])
                await db.commit()
                rows = await (await db.execute("SELECT COUNT(*) FROM page_links")).fetchone()
                return rows[0]

        assert run(_run()) == 0


# ---------------------------------------------------------------------------
# compute_pagerank — grafo simples
# ---------------------------------------------------------------------------

class TestComputePagerank:
    def _insert_links(self, edges: list[tuple[str, str]], main_path: Path) -> None:
        import sqlite3
        con = sqlite3.connect(main_path)
        con.executemany(
            "INSERT OR IGNORE INTO page_links (source_url, target_url) VALUES (?, ?)",
            edges,
        )
        con.commit()
        con.close()

    def test_empty_graph_returns_zero(self, db_paths):
        main_path, _ = db_paths

        async def _run():
            import aiosqlite
            from services.pagerank import compute_pagerank
            async with aiosqlite.connect(main_path) as db:
                return await compute_pagerank(db)

        assert run(_run()) == 0

    def test_simple_graph_scores_calculated(self, db_paths):
        """Grafo A→B, A→C, B→C — 3 nós → 3 scores calculados e normalizados."""
        main_path, _ = db_paths
        self._insert_links([
            ("https://a.com", "https://b.com"),
            ("https://a.com", "https://c.com"),
            ("https://b.com", "https://c.com"),
        ], main_path)

        async def _run():
            import aiosqlite
            from services.pagerank import compute_pagerank
            async with aiosqlite.connect(main_path) as db:
                count = await compute_pagerank(db)
                await db.commit()
                rows = await (await db.execute("SELECT url, score FROM page_rank")).fetchall()
                return count, {r[0]: r[1] for r in rows}

        count, scores = run(_run())
        assert count == 3
        assert set(scores.keys()) == {"https://a.com", "https://b.com", "https://c.com"}
        # C tem 2 in-links (de A e B), deve ter score mais alto
        assert scores["https://c.com"] >= scores["https://a.com"]

    def test_normalized_range(self, db_paths):
        """Todos os scores devem estar em [0.8, 1.2]."""
        main_path, _ = db_paths
        self._insert_links([
            ("https://a.com", "https://b.com"),
            ("https://b.com", "https://c.com"),
            ("https://c.com", "https://a.com"),
        ], main_path)

        async def _run():
            import aiosqlite
            from services.pagerank import compute_pagerank
            async with aiosqlite.connect(main_path) as db:
                await compute_pagerank(db)
                await db.commit()
                rows = await (await db.execute("SELECT score FROM page_rank")).fetchall()
                return [r[0] for r in rows]

        scores = run(_run())
        for s in scores:
            assert 0.79 <= s <= 1.21, f"Score fora do range: {s}"

    def test_hub_node_high_in_links_gets_high_score(self, db_paths):
        """Nó com muitos in-links deve ter score ≥ 1.0 (normalizado)."""
        main_path, _ = db_paths
        # hub recebe links de 4 nós diferentes
        edges = [(f"https://src{i}.com", "https://hub.com") for i in range(4)]
        edges += [("https://hub.com", "https://leaf.com")]
        self._insert_links(edges, main_path)

        async def _run():
            import aiosqlite
            from services.pagerank import compute_pagerank
            async with aiosqlite.connect(main_path) as db:
                await compute_pagerank(db)
                await db.commit()
                row = await (await db.execute(
                    "SELECT score FROM page_rank WHERE url = 'https://hub.com'"
                )).fetchone()
                return row[0] if row else None

        score = run(_run())
        assert score is not None
        assert score >= 1.0, f"Hub deveria ter score ≥ 1.0, obteve {score}"

    def test_seed_domain_gets_boost(self, db_paths):
        """URL cuja domain está em domain_boosts (seeds) deve ter score ≥ 1.0."""
        import sqlite3
        main_path, _ = db_paths

        # Insere aresta simples
        self._insert_links([
            ("https://a.com/p", "https://seed.com/p"),
            ("https://b.com/p", "https://seed.com/p"),
            ("https://seed.com/p", "https://c.com/p"),
        ], main_path)

        # Insere domain_boost manualmente (simula que cliques já foram registrados)
        con = sqlite3.connect(main_path)
        con.execute(
            "CREATE TABLE IF NOT EXISTS domain_boosts (domain TEXT PRIMARY KEY, boost REAL, updated_at INTEGER)"
        )
        con.execute(
            "INSERT OR REPLACE INTO domain_boosts (domain, boost, updated_at) VALUES ('seed.com', 5.0, 0)"
        )
        con.commit()
        con.close()

        async def _run():
            import aiosqlite
            from services.pagerank import compute_pagerank
            async with aiosqlite.connect(main_path) as db:
                await compute_pagerank(db)
                await db.commit()
                row = await (await db.execute(
                    "SELECT score FROM page_rank WHERE url = 'https://seed.com/p'"
                )).fetchone()
                others = await (await db.execute(
                    "SELECT score FROM page_rank WHERE url != 'https://seed.com/p'"
                )).fetchall()
                return row[0] if row else None, [r[0] for r in others]

        seed_score, other_scores = run(_run())
        assert seed_score is not None
        # Semente com personalization bias deve ter score ≥ média dos outros
        avg_others = sum(other_scores) / len(other_scores) if other_scores else 1.0
        assert seed_score >= avg_others, (
            f"Semente ({seed_score:.4f}) deveria ter score ≥ média dos outros ({avg_others:.4f})"
        )


# ---------------------------------------------------------------------------
# get_page_rank_scores — batch lookup
# ---------------------------------------------------------------------------

class TestGetPageRankScores:
    def test_unknown_url_returns_1_0(self, db_paths):
        main_path, _ = db_paths

        async def _run():
            import aiosqlite
            from services.pagerank import get_page_rank_scores
            async with aiosqlite.connect(main_path) as db:
                return await get_page_rank_scores(db, ["https://unknown.com/page"])

        scores = run(_run())
        assert scores["https://unknown.com/page"] == 1.0

    def test_known_url_returns_stored_score(self, db_paths):
        import sqlite3
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        con.execute(
            "INSERT INTO page_rank (url, score, updated_at) VALUES ('https://known.com', 1.15, 0)"
        )
        con.commit()
        con.close()

        async def _run():
            import aiosqlite
            from services.pagerank import get_page_rank_scores
            async with aiosqlite.connect(main_path) as db:
                return await get_page_rank_scores(db, ["https://known.com", "https://unknown.com"])

        scores = run(_run())
        assert abs(scores["https://known.com"] - 1.15) < 1e-6
        assert scores["https://unknown.com"] == 1.0

    def test_empty_list_returns_empty_dict(self, db_paths):
        main_path, _ = db_paths

        async def _run():
            import aiosqlite
            from services.pagerank import get_page_rank_scores
            async with aiosqlite.connect(main_path) as db:
                return await get_page_rank_scores(db, [])

        assert run(_run()) == {}


# ---------------------------------------------------------------------------
# Autoridade por nº de in-links (critério de aceite do TODO)
# ---------------------------------------------------------------------------

class TestInboundAuthority:
    def _insert_links(self, edges, main_path):
        import sqlite3
        con = sqlite3.connect(main_path)
        con.executemany(
            "INSERT OR IGNORE INTO page_links (source_url, target_url) VALUES (?, ?)",
            edges,
        )
        con.commit()
        con.close()

    def test_more_inbound_links_higher_authority(self, db_paths):
        """Página com 5 in-links deve ter autoridade > página com 1 in-link."""
        main_path, _ = db_paths
        edges = [(f"https://s{i}.com", "https://popular.com") for i in range(5)]
        edges += [("https://s0.com", "https://obscura.com")]  # obscura: 1 in-link
        self._insert_links(edges, main_path)

        async def _run():
            import aiosqlite
            from services.pagerank import compute_pagerank
            async with aiosqlite.connect(main_path) as db:
                await compute_pagerank(db)
                await db.commit()
                rows = await (await db.execute(
                    "SELECT url, score FROM page_rank WHERE url IN "
                    "('https://popular.com', 'https://obscura.com')"
                )).fetchall()
                return {r[0]: r[1] for r in rows}

        scores = run(_run())
        assert scores["https://popular.com"] > scores["https://obscura.com"], (
            f"popular ({scores['https://popular.com']:.4f}) deveria superar "
            f"obscura ({scores['https://obscura.com']:.4f})"
        )


# ---------------------------------------------------------------------------
# run_pagerank_refresh — wrapper de produção (chamado pelo job de background)
# ---------------------------------------------------------------------------

class TestRunPagerankRefresh:
    def _insert_links(self, edges, main_path):
        import sqlite3
        con = sqlite3.connect(main_path)
        con.executemany(
            "INSERT OR IGNORE INTO page_links (source_url, target_url) VALUES (?, ?)",
            edges,
        )
        con.commit()
        con.close()

    def test_refresh_populates_page_rank(self, db_paths):
        """run_pagerank_refresh abre a conexão, calcula e comita em page_rank."""
        import sqlite3
        main_path, _ = db_paths
        self._insert_links([
            ("https://a.com", "https://b.com"),
            ("https://a.com", "https://c.com"),
            ("https://b.com", "https://c.com"),
        ], main_path)

        async def _run():
            from services.pagerank import run_pagerank_refresh
            return await run_pagerank_refresh(db_path=main_path)

        n = run(_run())
        assert n == 3

        # Verifica persistência em conexão separada (commit aconteceu)
        con = sqlite3.connect(main_path)
        rows = con.execute("SELECT url, score FROM page_rank").fetchall()
        con.close()
        assert len(rows) == 3

    def test_refresh_empty_graph_returns_zero(self, db_paths):
        """Sem arestas em page_links, refresh retorna 0 e não falha."""
        main_path, _ = db_paths

        async def _run():
            from services.pagerank import run_pagerank_refresh
            return await run_pagerank_refresh(db_path=main_path)

        assert run(_run()) == 0

    def test_refresh_bad_path_returns_zero(self, tmp_path):
        """Caminho de banco inexistente/inválido não propaga exceção — retorna 0."""
        async def _run():
            from services.pagerank import run_pagerank_refresh
            # diretório, não arquivo de banco → erro tratado internamente
            return await run_pagerank_refresh(db_path=tmp_path)

        assert run(_run()) == 0
