"""
Testes para app/core/translation_worker.py (KOSMOS v3, Fase 6) — tradução de títulos.

Cobre:
  - get_untranslated_titles: seleciona NULL title_translated com lang != alvo;
    exclui já traduzidos, idioma == alvo, idioma desconhecido, título vazio;
    newest-first; limit.
  - save_title_translation: persiste em title_translated.
  - TranslationWorker init/stop.
  - _run_cycle: traduz cada título (translate mockado), salva, emite, conta;
    pula quando translate retorna None; pula no-op (resultado == título original).
  - ArticleList: card mostra title_translated quando presente; on_title_translated
    atualiza o card ao vivo.

translate é mockado (sem rede/argos/LOGOS).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

# qapp fixture vem do conftest.py


# ---------------------------------------------------------------------------
# Banco
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


def _insert_article(
    conn, feed_id, title="Title", language_detected="en",
    title_translated=None, published_at="2026-06-01T00:00:00Z", url=None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO articles (feed_id, url, title, language_detected, title_translated, published_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (feed_id, url or f"https://j.com/{title}", title, language_detected,
         title_translated, published_at),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    cur = conn.execute("INSERT INTO feeds (url, title) VALUES (?, ?)", ("https://j.com/rss", "J"))
    conn.commit()
    yield conn, cur.lastrowid
    conn.close()


@pytest.fixture
def worker(qapp):
    from app.core.translation_worker import TranslationWorker
    w = TranslationWorker("pt", "argos")
    yield w
    if w.isRunning():
        w.stop()
        w.wait(2000)


# ---------------------------------------------------------------------------
# get_untranslated_titles
# ---------------------------------------------------------------------------

class TestGetUntranslatedTitles:
    def test_selects_pending(self, db):
        conn, fid = db
        from app.core.translation_worker import get_untranslated_titles
        aid = _insert_article(conn, fid, title="Hello", language_detected="en")
        out = get_untranslated_titles("pt", conn=conn)
        assert (aid, "Hello", "en") in out

    def test_excludes_already_translated(self, db):
        conn, fid = db
        from app.core.translation_worker import get_untranslated_titles
        _insert_article(conn, fid, title="Done", language_detected="en", title_translated="Feito")
        assert get_untranslated_titles("pt", conn=conn) == []

    def test_excludes_same_language(self, db):
        conn, fid = db
        from app.core.translation_worker import get_untranslated_titles
        _insert_article(conn, fid, title="Olá", language_detected="pt")
        assert get_untranslated_titles("pt", conn=conn) == []

    def test_excludes_unknown_language(self, db):
        conn, fid = db
        from app.core.translation_worker import get_untranslated_titles
        _insert_article(conn, fid, title="???", language_detected=None)
        assert get_untranslated_titles("pt", conn=conn) == []

    def test_newest_first(self, db):
        conn, fid = db
        from app.core.translation_worker import get_untranslated_titles
        _insert_article(conn, fid, title="Old", language_detected="en", published_at="2026-01-01T00:00:00Z")
        _insert_article(conn, fid, title="New", language_detected="en", published_at="2026-06-01T00:00:00Z")
        titles = [t for _, t, _ in get_untranslated_titles("pt", conn=conn)]
        assert titles.index("New") < titles.index("Old")

    def test_limit(self, db):
        conn, fid = db
        from app.core.translation_worker import get_untranslated_titles
        for i in range(5):
            _insert_article(conn, fid, title=f"T{i}", language_detected="en")
        assert len(get_untranslated_titles("pt", limit=3, conn=conn)) == 3


# ---------------------------------------------------------------------------
# save_title_translation
# ---------------------------------------------------------------------------

def test_save_title_translation(db):
    conn, fid = db
    from app.core.translation_worker import save_title_translation
    aid = _insert_article(conn, fid, title="Hello", language_detected="en")
    assert save_title_translation(aid, "Olá", conn=conn) is True
    row = conn.execute("SELECT title_translated FROM articles WHERE id = ?", (aid,)).fetchone()
    assert row[0] == "Olá"


# ---------------------------------------------------------------------------
# TranslationWorker
# ---------------------------------------------------------------------------

class TestWorkerInit:
    def test_target_lowercased(self, qapp):
        from app.core.translation_worker import TranslationWorker
        w = TranslationWorker("PT", "argos")
        assert w._target_lang == "pt"

    def test_stop_sets_flag(self, worker):
        worker.stop()
        assert worker._stop_flag is True


class TestRunCycle:
    def _collect(self, worker):
        done = []
        worker.title_translated.connect(lambda aid, t: done.append((aid, t)))
        return done

    def test_translates_and_saves(self, db, worker):
        conn, fid = db
        from app.core import translation_worker as tw
        aid = _insert_article(conn, fid, title="Hello world", language_detected="en")
        done = self._collect(worker)
        # get_untranslated_titles / save abrem conexão própria → usam o mesmo DB (patched)
        import app.core.database as db_module
        with patch.object(db_module, "DB_PATH", Path(conn.execute("PRAGMA database_list").fetchone()[2])), \
             patch("app.core.translation_worker.translate", return_value="Olá mundo"):
            n = worker._run_cycle()
        assert n == 1
        assert (aid, "Olá mundo") in done
        row = conn.execute("SELECT title_translated FROM articles WHERE id = ?", (aid,)).fetchone()
        assert row[0] == "Olá mundo"

    def test_skips_when_translate_none(self, db, worker):
        conn, fid = db
        import app.core.database as db_module
        _insert_article(conn, fid, title="Hello", language_detected="en")
        with patch.object(db_module, "DB_PATH", Path(conn.execute("PRAGMA database_list").fetchone()[2])), \
             patch("app.core.translation_worker.translate", return_value=None):
            n = worker._run_cycle()
        assert n == 0

    def test_skips_noop_same_text(self, db, worker):
        conn, fid = db
        import app.core.database as db_module
        _insert_article(conn, fid, title="Hello", language_detected="en")
        # translate devolve o mesmo texto (no-op) → não persiste nem conta
        with patch.object(db_module, "DB_PATH", Path(conn.execute("PRAGMA database_list").fetchone()[2])), \
             patch("app.core.translation_worker.translate", return_value="Hello"):
            n = worker._run_cycle()
        assert n == 0


# ---------------------------------------------------------------------------
# ArticleList — exibição da tradução
# ---------------------------------------------------------------------------

class TestArticleListTranslation:
    def test_card_prefers_translated_title(self, qapp):
        from app.ui.views.article_list import ArticleCard
        card = ArticleCard({"id": 1, "title": "Hello", "title_translated": "Olá", "is_read": 1})
        assert card._title_lbl.text() == "Olá"

    def test_card_falls_back_to_original(self, qapp):
        from app.ui.views.article_list import ArticleCard
        card = ArticleCard({"id": 1, "title": "Hello", "title_translated": None, "is_read": 1})
        assert card._title_lbl.text() == "Hello"

    def test_on_title_translated_updates_card(self, qapp, db):
        conn, fid = db
        _insert_article(conn, fid, title="Hello", language_detected="en")
        from app.ui.views.article_list import ArticleList
        lst = ArticleList()
        lst.load_articles(conn=conn)
        aid = conn.execute("SELECT id FROM articles LIMIT 1").fetchone()[0]
        lst.on_title_translated(aid, "Olá traduzido")
        # localiza o card e confere o texto
        for i in range(lst._list.count()):
            item = lst._list.item(i)
            if item.data(0x0100) == aid:  # Qt.UserRole
                card = lst._list.itemWidget(item)
                assert card._title_lbl.text() == "Olá traduzido"
                break
        else:
            pytest.fail("card não encontrado")
