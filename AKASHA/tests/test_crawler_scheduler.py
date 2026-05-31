"""
Testes de integração para services/crawler_scheduler.py e integração com crawler.py.

Cobre:
  - classify_frequency: URL com padrão news/blog → 'daily'
  - classify_frequency: URL com padrão docs → 'monthly'
  - classify_frequency: >3 alterações recentes → 'daily'
  - classify_frequency: ≤3 alterações, URL neutra → 'weekly'
  - compute_next_crawl_at: cálculo correto por frequência
  - update_site_schedule: lê páginas recentes do DB e atualiza crawl_sites
  - get_sites_due: retorna apenas sites com next_crawl_at ≤ now
  - _upsert_page: hash igual → last_modified_at não atualizado
  - _upsert_page: hash diferente → last_modified_at atualizado
"""
from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path

import pytest


def run(coro):
    """Executa corrotina em event loop de teste (Python 3.12+ requer asyncio.run)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixture: DB completo com schema AKASHA (via init_db)
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
# classify_frequency — função pura, sem DB
# ---------------------------------------------------------------------------

class TestClassifyFrequency:
    def _cf(self, url: str, recent_changes: int = 0):
        from services.crawler_scheduler import classify_frequency
        return classify_frequency(url, recent_changes)

    def test_news_url_is_daily(self):
        assert self._cf("https://news.example.com") == "daily"

    def test_blog_url_is_daily(self):
        assert self._cf("https://example.com/blog") == "daily"

    def test_feed_url_is_daily(self):
        assert self._cf("https://example.com/feed") == "daily"

    def test_high_change_rate_is_daily(self):
        assert self._cf("https://example.com", recent_changes=4) == "daily"

    def test_exactly_three_changes_not_daily(self):
        # limiar é >3, portanto 3 não promove
        assert self._cf("https://example.com", recent_changes=3) != "daily"

    def test_docs_url_is_monthly(self):
        assert self._cf("https://docs.example.com") == "monthly"

    def test_documentation_url_is_monthly(self):
        assert self._cf("https://example.com/documentation/intro") == "monthly"

    def test_neutral_url_is_weekly(self):
        assert self._cf("https://example.com") == "weekly"

    def test_neutral_url_low_changes_is_weekly(self):
        assert self._cf("https://example.com", recent_changes=1) == "weekly"

    def test_news_pattern_takes_priority_over_monthly(self):
        # "news" antes de "docs" → deve ser daily
        assert self._cf("https://news-docs.example.com") == "daily"


# ---------------------------------------------------------------------------
# compute_next_crawl_at — função pura
# ---------------------------------------------------------------------------

class TestComputeNextCrawlAt:
    def test_daily_adds_one_day(self):
        from services.crawler_scheduler import compute_next_crawl_at
        epoch = 1_000_000.0
        result = compute_next_crawl_at(epoch, "daily")
        assert result == int(epoch + 1 * 86400)

    def test_weekly_adds_seven_days(self):
        from services.crawler_scheduler import compute_next_crawl_at
        epoch = 1_000_000.0
        result = compute_next_crawl_at(epoch, "weekly")
        assert result == int(epoch + 7 * 86400)

    def test_monthly_adds_thirty_days(self):
        from services.crawler_scheduler import compute_next_crawl_at
        epoch = 1_000_000.0
        result = compute_next_crawl_at(epoch, "monthly")
        assert result == int(epoch + 30 * 86400)

    def test_returns_int(self):
        from services.crawler_scheduler import compute_next_crawl_at
        result = compute_next_crawl_at(time.time(), "weekly")
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# update_site_schedule + get_sites_due — integração com DB
# ---------------------------------------------------------------------------

class TestUpdateSiteSchedule:
    def _add_site(self, con: sqlite3.Connection, base_url: str) -> int:
        cur = con.execute(
            "INSERT INTO crawl_sites (base_url, label) VALUES (?, ?)",
            (base_url, "test"),
        )
        con.commit()
        return cur.lastrowid

    def _add_page(
        self,
        con: sqlite3.Connection,
        site_id: int,
        url: str,
        last_modified_at: str = "",
    ) -> None:
        con.execute(
            """INSERT INTO crawl_pages
               (site_id, url, title, content_md, content_hash, last_modified_at)
               VALUES (?, ?, '', '', '', ?)""",
            (site_id, url, last_modified_at),
        )
        con.commit()

    def test_high_change_rate_promotes_to_daily(self, db_paths):
        """Site com >3 páginas alteradas nos últimos 14 dias → promovido para 'daily'."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)

        site_id = self._add_site(con, "https://example.com")
        # 4 páginas com last_modified_at recente (hoje)
        from datetime import datetime
        recent = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for i in range(4):
            self._add_page(con, site_id, f"https://example.com/p{i}", last_modified_at=recent)
        con.close()

        async def _run():
            import aiosqlite
            async with aiosqlite.connect(main_path) as db:
                from services.crawler_scheduler import update_site_schedule
                freq = await update_site_schedule(site_id, db)
                await db.commit()
                return freq

        freq = run(_run())
        assert freq == "daily", f"Esperava 'daily' com 4 alterações recentes, obteve '{freq}'"

        con = sqlite3.connect(main_path)
        row = con.execute(
            "SELECT crawl_frequency FROM crawl_sites WHERE id = ?", (site_id,)
        ).fetchone()
        con.close()
        assert row[0] == "daily"

    def test_no_changes_keeps_weekly(self, db_paths):
        """Site sem alterações recentes e URL neutra → permanece 'weekly'."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        site_id = self._add_site(con, "https://example.com")
        # Páginas sem last_modified_at
        for i in range(3):
            self._add_page(con, site_id, f"https://example.com/static{i}")
        con.close()

        async def _run():
            import aiosqlite
            async with aiosqlite.connect(main_path) as db:
                from services.crawler_scheduler import update_site_schedule
                return await update_site_schedule(site_id, db)

        freq = run(_run())
        assert freq == "weekly"

    def test_next_crawl_at_is_set(self, db_paths):
        """Após update_site_schedule, next_crawl_at deve ser > 0."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        site_id = self._add_site(con, "https://example.com")
        con.close()

        async def _run():
            import aiosqlite
            async with aiosqlite.connect(main_path) as db:
                from services.crawler_scheduler import update_site_schedule
                await update_site_schedule(site_id, db)
                await db.commit()

        run(_run())

        con = sqlite3.connect(main_path)
        row = con.execute(
            "SELECT next_crawl_at FROM crawl_sites WHERE id = ?", (site_id,)
        ).fetchone()
        con.close()
        assert row[0] > 0


class TestGetSitesDue:
    def _add_site(self, con: sqlite3.Connection, base_url: str, next_crawl_at: int = 0) -> int:
        cur = con.execute(
            "INSERT INTO crawl_sites (base_url, label, next_crawl_at) VALUES (?, ?, ?)",
            (base_url, "test", next_crawl_at),
        )
        con.commit()
        return cur.lastrowid

    def test_site_with_zero_next_crawl_is_due(self, db_paths):
        """Sites com next_crawl_at=0 (nunca agendados) devem ser devolvidos."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        site_id = self._add_site(con, "https://a.com", next_crawl_at=0)
        con.close()

        async def _run():
            import aiosqlite
            async with aiosqlite.connect(main_path) as db:
                from services.crawler_scheduler import get_sites_due
                return await get_sites_due(db)

        due = run(_run())
        assert site_id in due

    def test_future_site_not_due(self, db_paths):
        """Site com next_crawl_at no futuro não deve ser devolvido."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        future = int(time.time()) + 99999
        site_id = self._add_site(con, "https://b.com", next_crawl_at=future)
        con.close()

        async def _run():
            import aiosqlite
            async with aiosqlite.connect(main_path) as db:
                from services.crawler_scheduler import get_sites_due
                return await get_sites_due(db)

        due = run(_run())
        assert site_id not in due

    def test_past_site_is_due(self, db_paths):
        """Site com next_crawl_at no passado deve ser devolvido."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        past = int(time.time()) - 100
        site_id = self._add_site(con, "https://c.com", next_crawl_at=past)
        con.close()

        async def _run():
            import aiosqlite
            async with aiosqlite.connect(main_path) as db:
                from services.crawler_scheduler import get_sites_due
                return await get_sites_due(db)

        due = run(_run())
        assert site_id in due


# ---------------------------------------------------------------------------
# _upsert_page — hash igual → last_modified_at não atualizado
# ---------------------------------------------------------------------------

class TestUpsertPageHashTracking:
    def _add_site(self, con: sqlite3.Connection, base_url: str) -> int:
        cur = con.execute(
            "INSERT INTO crawl_sites (base_url, label) VALUES (?, ?)",
            (base_url, "test"),
        )
        con.commit()
        return cur.lastrowid

    def test_unchanged_hash_preserves_last_modified_at(self, db_paths):
        """Re-crawl de página com mesmo hash não deve atualizar last_modified_at."""
        import database as _db
        main_path, _ = db_paths

        async def _run():
            import aiosqlite
            import services.crawler as _crawler
            orig = _crawler.DB_PATH
            _crawler.DB_PATH = main_path
            try:
                async with aiosqlite.connect(main_path) as db:
                    # Inserir site
                    cur = await db.execute(
                        "INSERT INTO crawl_sites (base_url, label) VALUES (?, ?)",
                        ("https://example.com", "test"),
                    )
                    site_id = cur.lastrowid
                    await db.commit()

                    # Conteúdo com >= MIN_WORDS_TO_STORE palavras para passar a validação
                    _content = " ".join(["palavra"] * 60)

                    # Primeiro crawl: nova página
                    await _crawler._upsert_page(
                        db, site_id, "https://example.com/p1",
                        "Título", _content, "hash_abc",
                        200, "2026-01-01 10:00:00",
                    )
                    await db.commit()

                    # Captura last_modified_at após primeiro crawl
                    row = await (await db.execute(
                        "SELECT last_modified_at FROM crawl_pages WHERE url = ?",
                        ("https://example.com/p1",),
                    )).fetchone()
                    lm_first = row[0]

                    # Segundo crawl: mesmo hash
                    await _crawler._upsert_page(
                        db, site_id, "https://example.com/p1",
                        "Título", _content, "hash_abc",
                        200, "2026-01-02 10:00:00",
                    )
                    await db.commit()

                    # last_modified_at NÃO deve ter mudado
                    row2 = await (await db.execute(
                        "SELECT last_modified_at, last_checked_at FROM crawl_pages WHERE url = ?",
                        ("https://example.com/p1",),
                    )).fetchone()
                    lm_second = row2[0]
                    lc_second = row2[1]
                    return lm_first, lm_second, lc_second
            finally:
                _crawler.DB_PATH = orig

        lm_first, lm_second, lc_second = run(_run())
        assert lm_first == lm_second, (
            f"Hash idêntico: last_modified_at não deve mudar ({lm_first} → {lm_second})"
        )
        assert lc_second == "2026-01-02 10:00:00", (
            f"last_checked_at deve ser atualizado mesmo sem mudança de conteúdo"
        )

    def test_changed_hash_updates_last_modified_at(self, db_paths):
        """Re-crawl de página com hash diferente deve atualizar last_modified_at."""
        import services.crawler as _crawler
        main_path, _ = db_paths

        async def _run():
            import aiosqlite
            orig = _crawler.DB_PATH
            _crawler.DB_PATH = main_path
            try:
                async with aiosqlite.connect(main_path) as db:
                    cur = await db.execute(
                        "INSERT INTO crawl_sites (base_url, label) VALUES (?, ?)",
                        ("https://example2.com", "test"),
                    )
                    site_id = cur.lastrowid
                    await db.commit()

                    _content_v1 = " ".join(["palavra"] * 60)
                    _content_v2 = " ".join(["outro"] * 60)

                    await _crawler._upsert_page(
                        db, site_id, "https://example2.com/p1",
                        "Título", _content_v1, "hash_v1",
                        200, "2026-01-01 10:00:00",
                    )
                    await db.commit()

                    row1 = await (await db.execute(
                        "SELECT last_modified_at FROM crawl_pages WHERE url = ?",
                        ("https://example2.com/p1",),
                    )).fetchone()
                    lm_first = row1[0]

                    # Conteúdo mudou (hash diferente)
                    await _crawler._upsert_page(
                        db, site_id, "https://example2.com/p1",
                        "Título", _content_v2, "hash_v2",
                        200, "2026-02-15 08:00:00",
                    )
                    await db.commit()

                    row2 = await (await db.execute(
                        "SELECT last_modified_at FROM crawl_pages WHERE url = ?",
                        ("https://example2.com/p1",),
                    )).fetchone()
                    lm_second = row2[0]
                    return lm_first, lm_second
            finally:
                _crawler.DB_PATH = orig

        lm_first, lm_second = run(_run())
        assert lm_second == "2026-02-15 08:00:00", (
            f"Hash mudou: last_modified_at deve ser atualizado para '2026-02-15 08:00:00', "
            f"obtido '{lm_second}'"
        )
        assert lm_first != lm_second, "last_modified_at deve mudar quando hash muda"
