"""
Testes para app/core/fetch_worker.py (KOSMOS v3).

Cobre: get_due_feeds (lógica de agendamento), FetchWorker._run_cycle
(orquestração e emissão de sinais), FetchWorker.stop (flag de parada).

Estratégia de isolamento Qt:
  - QCoreApplication criada uma vez por sessão (fixture qapp).
  - _run_cycle() é chamado diretamente (sem iniciar a thread) — sinais
    são emitidos de forma síncrona quando emissor e receptor estão na
    mesma thread, permitindo captura via connect + lambda.
  - O loop run() (sleep/tick) não é testado diretamente por depender de
    event loop em thread separada; a lógica de ciclo é coberta via _run_cycle.

get_due_feeds usa banco SQLite real em tmp_path — sem mock de DB.
_run_cycle usa get_due_feeds e fetch_and_save mockados.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# qapp fixture vem do conftest.py (QApplication, session-scope)


# ---------------------------------------------------------------------------
# Fixtures de banco (mesma abordagem de test_database.py)
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


def _insert_feed(
    conn: sqlite3.Connection,
    url: str,
    enabled: int = 1,
    fetch_interval_min: int = 60,
    last_fetched_at: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO feeds (url, title, enabled, fetch_interval_min, last_fetched_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (url, "Feed " + url, enabled, fetch_interval_min, last_fetched_at),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def db(tmp_path):
    """Banco inicializado em tmp_path, conexão aberta."""
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    yield db_file, conn
    conn.close()


# ---------------------------------------------------------------------------
# Fixture: FetchWorker
# ---------------------------------------------------------------------------

@pytest.fixture
def worker(qapp):
    from app.core.fetch_worker import FetchWorker
    w = FetchWorker()
    yield w
    if w.isRunning():
        w.stop()
        w.wait(2000)


# ---------------------------------------------------------------------------
# TestGetDueFeeds
# ---------------------------------------------------------------------------

class TestGetDueFeeds:
    def test_never_fetched_is_due(self, db):
        _, conn = db
        from app.core.fetch_worker import get_due_feeds
        _insert_feed(conn, "https://a.com/feed", last_fetched_at=None)
        due = get_due_feeds(conn)
        urls = [u for _, u in due]
        assert "https://a.com/feed" in urls

    def test_overdue_is_included(self, db):
        _, conn = db
        from app.core.fetch_worker import get_due_feeds
        # Intervalo de 1 minuto; último fetch há 2 minutos → vencido
        past = conn.execute(
            "SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-2 minutes')"
        ).fetchone()[0]
        _insert_feed(conn, "https://b.com/feed", fetch_interval_min=1, last_fetched_at=past)
        due = get_due_feeds(conn)
        urls = [u for _, u in due]
        assert "https://b.com/feed" in urls

    def test_recently_fetched_not_due(self, db):
        _, conn = db
        from app.core.fetch_worker import get_due_feeds
        # Intervalo de 60 minutos; último fetch agora → não vencido
        now = conn.execute(
            "SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
        ).fetchone()[0]
        _insert_feed(conn, "https://c.com/feed", fetch_interval_min=60, last_fetched_at=now)
        due = get_due_feeds(conn)
        urls = [u for _, u in due]
        assert "https://c.com/feed" not in urls

    def test_disabled_feed_excluded(self, db):
        _, conn = db
        from app.core.fetch_worker import get_due_feeds
        _insert_feed(conn, "https://d.com/feed", enabled=0, last_fetched_at=None)
        due = get_due_feeds(conn)
        urls = [u for _, u in due]
        assert "https://d.com/feed" not in urls

    def test_null_fetched_comes_before_old(self, db):
        """Feeds nunca buscados têm prioridade sobre os mais antigos."""
        _, conn = db
        from app.core.fetch_worker import get_due_feeds
        old = conn.execute(
            "SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-120 minutes')"
        ).fetchone()[0]
        _insert_feed(conn, "https://old.com/feed", fetch_interval_min=1, last_fetched_at=old)
        _insert_feed(conn, "https://never.com/feed", last_fetched_at=None)
        due = get_due_feeds(conn)
        urls = [u for _, u in due]
        assert urls.index("https://never.com/feed") < urls.index("https://old.com/feed")

    def test_empty_db_returns_empty(self, db):
        _, conn = db
        from app.core.fetch_worker import get_due_feeds
        assert get_due_feeds(conn) == []

    def test_returns_id_and_url(self, db):
        _, conn = db
        from app.core.fetch_worker import get_due_feeds
        feed_id = _insert_feed(conn, "https://e.com/feed", last_fetched_at=None)
        due = get_due_feeds(conn)
        assert len(due) == 1
        assert due[0] == (feed_id, "https://e.com/feed")

    def test_mixed_due_and_not_due(self, db):
        _, conn = db
        from app.core.fetch_worker import get_due_feeds
        now = conn.execute(
            "SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
        ).fetchone()[0]
        past = conn.execute(
            "SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-120 minutes')"
        ).fetchone()[0]
        _insert_feed(conn, "https://fresh.com/feed", fetch_interval_min=60, last_fetched_at=now)
        _insert_feed(conn, "https://stale.com/feed", fetch_interval_min=1, last_fetched_at=past)
        _insert_feed(conn, "https://never.com/feed", last_fetched_at=None)
        due = get_due_feeds(conn)
        urls = [u for _, u in due]
        assert "https://fresh.com/feed" not in urls
        assert "https://stale.com/feed" in urls
        assert "https://never.com/feed" in urls


# ---------------------------------------------------------------------------
# TestFetchWorkerInit
# ---------------------------------------------------------------------------

class TestFetchWorkerInit:
    def test_stop_flag_false_by_default(self, worker):
        assert worker._stop_flag is False

    def test_poll_interval_is_60(self, worker):
        from app.core.fetch_worker import _POLL_INTERVAL_SEC
        assert worker._poll_interval_sec == _POLL_INTERVAL_SEC

    def test_not_running_by_default(self, worker):
        assert not worker.isRunning()


# ---------------------------------------------------------------------------
# TestFetchWorkerStop
# ---------------------------------------------------------------------------

class TestFetchWorkerStop:
    def test_stop_sets_flag(self, worker):
        worker.stop()
        assert worker._stop_flag is True

    def test_stop_is_idempotent(self, worker):
        worker.stop()
        worker.stop()
        assert worker._stop_flag is True


# ---------------------------------------------------------------------------
# TestRunCycle
# ---------------------------------------------------------------------------

class TestRunCycle:
    """Testa _run_cycle() diretamente, sem iniciar a QThread.

    get_due_feeds e fetch_and_save são mockados — apenas a lógica de
    orquestração e emissão de sinais é verificada aqui.
    """

    def _collect_signals(self, worker):
        """Conecta todos os sinais do worker a listas e as retorna."""
        started, done, errors, cycles = [], [], [], []
        worker.feed_started.connect(lambda fid: started.append(fid))
        worker.feed_done.connect(lambda fid, n: done.append((fid, n)))
        worker.feed_error.connect(lambda fid, m: errors.append((fid, m)))
        worker.cycle_done.connect(lambda n: cycles.append(n))
        return started, done, errors, cycles

    def test_no_due_feeds_returns_zero(self, worker):
        with patch("app.core.fetch_worker.get_due_feeds", return_value=[]):
            result = worker._run_cycle()
        assert result == 0

    def test_calls_fetch_for_each_feed(self, worker):
        due = [(1, "https://a.com"), (2, "https://b.com")]
        with patch("app.core.fetch_worker.get_due_feeds", return_value=due), \
             patch("app.core.fetch_worker.fetch_and_save", return_value=3) as mock_fetch:
            worker._run_cycle()
        assert mock_fetch.call_count == 2
        mock_fetch.assert_any_call(1, "https://a.com")
        mock_fetch.assert_any_call(2, "https://b.com")

    def test_emits_feed_started_for_each_feed(self, worker):
        started, _, _, _ = self._collect_signals(worker)
        due = [(10, "https://x.com"), (20, "https://y.com")]
        with patch("app.core.fetch_worker.get_due_feeds", return_value=due), \
             patch("app.core.fetch_worker.fetch_and_save", return_value=1):
            worker._run_cycle()
        assert 10 in started
        assert 20 in started

    def test_emits_feed_done_on_success(self, worker):
        _, done, _, _ = self._collect_signals(worker)
        due = [(5, "https://ok.com")]
        with patch("app.core.fetch_worker.get_due_feeds", return_value=due), \
             patch("app.core.fetch_worker.fetch_and_save", return_value=7):
            worker._run_cycle()
        assert (5, 7) in done

    def test_emits_feed_error_on_failure(self, worker):
        _, _, errors, _ = self._collect_signals(worker)
        due = [(9, "https://fail.com")]
        with patch("app.core.fetch_worker.get_due_feeds", return_value=due), \
             patch("app.core.fetch_worker.fetch_and_save", return_value=-1):
            worker._run_cycle()
        assert any(fid == 9 for fid, _ in errors)

    def test_returns_total_new_articles(self, worker):
        due = [(1, "https://a.com"), (2, "https://b.com"), (3, "https://c.com")]
        with patch("app.core.fetch_worker.get_due_feeds", return_value=due), \
             patch("app.core.fetch_worker.fetch_and_save", return_value=4):
            total = worker._run_cycle()
        assert total == 12  # 3 feeds × 4 artigos

    def test_failure_not_counted_in_total(self, worker):
        due = [(1, "https://ok.com"), (2, "https://fail.com")]
        def fake_fetch(feed_id, url):
            return 5 if feed_id == 1 else -1
        with patch("app.core.fetch_worker.get_due_feeds", return_value=due), \
             patch("app.core.fetch_worker.fetch_and_save", side_effect=fake_fetch):
            total = worker._run_cycle()
        assert total == 5  # só o feed bem-sucedido

    def test_stops_mid_cycle_on_flag(self, worker):
        """Se stop_flag for True durante o ciclo, feeds restantes são ignorados."""
        called = []
        def fake_fetch(feed_id, url):
            worker._stop_flag = True  # sinaliza parada após o primeiro
            called.append(feed_id)
            return 1
        due = [(1, "https://a.com"), (2, "https://b.com"), (3, "https://c.com")]
        with patch("app.core.fetch_worker.get_due_feeds", return_value=due), \
             patch("app.core.fetch_worker.fetch_and_save", side_effect=fake_fetch):
            worker._run_cycle()
        assert 1 in called
        assert 2 not in called
        assert 3 not in called
        worker._stop_flag = False  # restaura para outros testes

    def test_no_done_signal_on_error(self, worker):
        _, done, _, _ = self._collect_signals(worker)
        due = [(99, "https://err.com")]
        with patch("app.core.fetch_worker.get_due_feeds", return_value=due), \
             patch("app.core.fetch_worker.fetch_and_save", return_value=-1):
            worker._run_cycle()
        assert all(fid != 99 for fid, _ in done)

    def test_no_feeds_no_error_signal(self, worker):
        _, _, errors, _ = self._collect_signals(worker)
        with patch("app.core.fetch_worker.get_due_feeds", return_value=[]):
            worker._run_cycle()
        assert errors == []
