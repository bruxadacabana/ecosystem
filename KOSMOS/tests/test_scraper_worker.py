"""
Testes para app/core/scraper_worker.py (KOSMOS v3, Fase 3).

Cobre:
  - get_pending_articles: seleção (is_scraped=0), exclusão de 1/-1/url vazia,
    ordem newest-first, limit, banco vazio.
  - ScraperWorker init/stop: flags, fila prioritária, idempotência.
  - request_scrape: enfileira P1; ignora URL vazia.
  - _run_cycle: batch scrapeia cada pendente, emite sinais, conta processados;
    P1 tem prioridade sobre o batch; P1 preempta entre itens do batch;
    stop interrompe o ciclo; sucesso/falha refletem scrape_and_save.

Estratégia Qt (igual a test_fetch_worker): _run_cycle é chamado direto, sem
iniciar a thread — sinais são síncronos na mesma thread. get_pending_articles e
scrape_and_save são mockados nos testes de orquestração; get_pending_articles
usa banco real em tmp_path nos testes de seleção.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

# qapp fixture vem do conftest.py


# ---------------------------------------------------------------------------
# Fixtures de banco
# ---------------------------------------------------------------------------

def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _init_db_at(path: Path) -> None:
    import app.core.database as db_module
    with patch.object(db_module, "DB_PATH", path):
        db_module.init_db()


def _insert_feed(conn: sqlite3.Connection, url: str = "https://feed.com/rss") -> int:
    cur = conn.execute(
        "INSERT INTO feeds (url, title) VALUES (?, ?)", (url, "Feed")
    )
    conn.commit()
    return cur.lastrowid


def _insert_article(
    conn: sqlite3.Connection,
    feed_id: int,
    url: str,
    is_scraped: int = 0,
    published_at: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO articles (feed_id, url, title, is_scraped, published_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (feed_id, url, "Título " + url, is_scraped, published_at),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    feed_id = _insert_feed(conn)
    yield db_file, conn, feed_id
    conn.close()


@pytest.fixture
def worker(qapp):
    from app.core.scraper_worker import ScraperWorker
    w = ScraperWorker()
    yield w
    if w.isRunning():
        w.stop()
        w.wait(2000)


# ---------------------------------------------------------------------------
# get_pending_articles
# ---------------------------------------------------------------------------

class TestGetPendingArticles:
    def test_pending_is_returned(self, db):
        _, conn, fid = db
        from app.core.scraper_worker import get_pending_articles
        aid = _insert_article(conn, fid, "https://a.com/1", is_scraped=0)
        pending = get_pending_articles(conn=conn)
        assert (aid, "https://a.com/1") in pending

    def test_scraped_excluded(self, db):
        _, conn, fid = db
        from app.core.scraper_worker import get_pending_articles
        _insert_article(conn, fid, "https://a.com/done", is_scraped=1)
        urls = [u for _, u in get_pending_articles(conn=conn)]
        assert "https://a.com/done" not in urls

    def test_failed_excluded(self, db):
        _, conn, fid = db
        from app.core.scraper_worker import get_pending_articles
        _insert_article(conn, fid, "https://a.com/fail", is_scraped=-1)
        urls = [u for _, u in get_pending_articles(conn=conn)]
        assert "https://a.com/fail" not in urls

    def test_empty_url_excluded(self, db):
        _, conn, fid = db
        from app.core.scraper_worker import get_pending_articles
        _insert_article(conn, fid, "", is_scraped=0)
        urls = [u for _, u in get_pending_articles(conn=conn)]
        assert "" not in urls

    def test_newest_first(self, db):
        _, conn, fid = db
        from app.core.scraper_worker import get_pending_articles
        _insert_article(conn, fid, "https://a.com/old", published_at="2026-01-01T00:00:00Z")
        _insert_article(conn, fid, "https://a.com/new", published_at="2026-06-01T00:00:00Z")
        urls = [u for _, u in get_pending_articles(conn=conn)]
        assert urls.index("https://a.com/new") < urls.index("https://a.com/old")

    def test_limit_respected(self, db):
        _, conn, fid = db
        from app.core.scraper_worker import get_pending_articles
        for i in range(5):
            _insert_article(conn, fid, f"https://a.com/{i}")
        assert len(get_pending_articles(limit=3, conn=conn)) == 3

    def test_empty_db_returns_empty(self, db):
        _, conn, _ = db
        from app.core.scraper_worker import get_pending_articles
        assert get_pending_articles(conn=conn) == []


# ---------------------------------------------------------------------------
# Init / stop / request
# ---------------------------------------------------------------------------

class TestScraperWorkerInit:
    def test_stop_flag_false_by_default(self, worker):
        assert worker._stop_flag is False

    def test_priority_queue_empty(self, worker):
        assert worker._priority_q.empty()

    def test_not_running_by_default(self, worker):
        assert not worker.isRunning()

    def test_defaults(self, worker):
        from app.core.scraper_worker import _BATCH_SIZE, _IDLE_INTERVAL_SEC
        assert worker._batch_size == _BATCH_SIZE
        assert worker._idle_interval_sec == _IDLE_INTERVAL_SEC


class TestStopAndRequest:
    def test_stop_sets_flag(self, worker):
        worker.stop()
        assert worker._stop_flag is True

    def test_stop_idempotent(self, worker):
        worker.stop()
        worker.stop()
        assert worker._stop_flag is True

    def test_request_scrape_enqueues(self, worker):
        worker.request_scrape(7, "https://x.com/a")
        assert worker._priority_q.get_nowait() == (7, "https://x.com/a")

    def test_request_scrape_ignores_empty_url(self, worker):
        worker.request_scrape(7, "")
        assert worker._priority_q.empty()

    def test_drain_priority_empties(self, worker):
        worker.request_scrape(1, "https://x.com/1")
        worker.request_scrape(2, "https://x.com/2")
        drained = worker._drain_priority()
        assert drained == [(1, "https://x.com/1"), (2, "https://x.com/2")]
        assert worker._priority_q.empty()


# ---------------------------------------------------------------------------
# _run_cycle (orquestração P1/P2)
# ---------------------------------------------------------------------------

class TestRunCycle:
    def _collect(self, worker):
        started, done, cycles = [], [], []
        worker.scrape_started.connect(lambda aid: started.append(aid))
        worker.scrape_done.connect(lambda aid, ok: done.append((aid, ok)))
        worker.cycle_done.connect(lambda n: cycles.append(n))
        return started, done, cycles

    def test_nothing_to_do_returns_zero(self, worker):
        with patch("app.core.scraper_worker.get_pending_articles", return_value=[]):
            assert worker._run_cycle() == 0

    def test_batch_scrapes_each(self, worker):
        pending = [(1, "https://a.com"), (2, "https://b.com")]
        with patch("app.core.scraper_worker.get_pending_articles", return_value=pending), \
             patch("app.core.scraper_worker.scrape_and_save", return_value=True) as m:
            n = worker._run_cycle()
        assert n == 2
        assert m.call_count == 2
        m.assert_any_call(1, "https://a.com")
        m.assert_any_call(2, "https://b.com")

    def test_emits_started_and_done(self, worker):
        started, done, _ = self._collect(worker)
        pending = [(5, "https://ok.com")]
        with patch("app.core.scraper_worker.get_pending_articles", return_value=pending), \
             patch("app.core.scraper_worker.scrape_and_save", return_value=True):
            worker._run_cycle()
        assert 5 in started
        assert (5, True) in done

    def test_done_reflects_failure(self, worker):
        _, done, _ = self._collect(worker)
        pending = [(9, "https://fail.com")]
        with patch("app.core.scraper_worker.get_pending_articles", return_value=pending), \
             patch("app.core.scraper_worker.scrape_and_save", return_value=False):
            worker._run_cycle()
        assert (9, False) in done

    def test_priority_processed_before_batch(self, worker):
        order = []
        worker.request_scrape(99, "https://p1.com")
        pending = [(1, "https://a.com"), (2, "https://b.com")]

        def fake(aid, url):
            order.append(aid)
            return True

        with patch("app.core.scraper_worker.get_pending_articles", return_value=pending), \
             patch("app.core.scraper_worker.scrape_and_save", side_effect=fake):
            worker._run_cycle()
        assert order[0] == 99
        assert order.index(99) < order.index(1)
        assert order.index(99) < order.index(2)

    def test_priority_preempts_between_batch_items(self, worker):
        """Um P1 que chega durante o batch é atendido antes do próximo item."""
        order = []
        pending = [(1, "https://a.com"), (2, "https://b.com")]

        def fake(aid, url):
            order.append(aid)
            if aid == 1:
                worker.request_scrape(50, "https://mid.com")  # injeta P1 no meio
            return True

        with patch("app.core.scraper_worker.get_pending_articles", return_value=pending), \
             patch("app.core.scraper_worker.scrape_and_save", side_effect=fake):
            worker._run_cycle()
        assert order == [1, 50, 2]

    def test_stop_interrupts_batch(self, worker):
        called = []

        def fake(aid, url):
            worker._stop_flag = True
            called.append(aid)
            return True

        pending = [(1, "https://a.com"), (2, "https://b.com"), (3, "https://c.com")]
        with patch("app.core.scraper_worker.get_pending_articles", return_value=pending), \
             patch("app.core.scraper_worker.scrape_and_save", side_effect=fake):
            worker._run_cycle()
        assert called == [1]
        worker._stop_flag = False

    def test_returns_count_with_priority_and_batch(self, worker):
        worker.request_scrape(99, "https://p1.com")
        pending = [(1, "https://a.com"), (2, "https://b.com")]
        with patch("app.core.scraper_worker.get_pending_articles", return_value=pending), \
             patch("app.core.scraper_worker.scrape_and_save", return_value=True):
            n = worker._run_cycle()
        assert n == 3  # 1 P1 + 2 batch
