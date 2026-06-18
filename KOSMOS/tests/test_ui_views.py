"""
Testes para app/ui/views/ (KOSMOS v3 — Fase 2).

Cobre: FeedSidebar (load_feeds, signal feed_selected), ArticleList
(load_articles, article_count, on_feed_updated, signal article_selected),
ReaderPane (show_article, mark_as_read, article_read signal, clear).

Estratégia Qt: fixture qapp (QApplication) vem do conftest.py.
Widgets são instanciados sem ser exibidos. Sinais são capturados via
connect + lambda em listas. DB em tmp_path (sem tocar em produção).

Limitações intencionais: renderização visual, dimensões de widgets e
comportamento de QSplitter não são testados — requerem display e janela
visível. O foco é na lógica de dados e emissão de sinais.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

# qapp vem do conftest.py


# ---------------------------------------------------------------------------
# Helpers de banco
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
    title: str = "Feed Teste",
    category: str = "Geral",
    enabled: int = 1,
) -> int:
    cur = conn.execute(
        "INSERT INTO feeds (url, title, category, enabled) VALUES (?, ?, ?, ?)",
        (url, title, category, enabled),
    )
    conn.commit()
    return cur.lastrowid


def _insert_article(
    conn: sqlite3.Connection,
    feed_id: int,
    url: str,
    title: str = "Artigo Teste",
    is_read: int = 0,
    published_at: str | None = None,
    article_type: str = "news",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO articles (feed_id, url, title, is_read, published_at, article_type)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (feed_id, url, title, is_read, published_at, article_type),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    yield db_file, conn
    conn.close()


# ---------------------------------------------------------------------------
# TestFeedSidebar
# ---------------------------------------------------------------------------

class TestFeedSidebar:
    @pytest.fixture
    def sidebar(self, qapp):
        from app.ui.views.feed_sidebar import FeedSidebar
        w = FeedSidebar()
        yield w
        w.deleteLater()

    def test_instantiation(self, sidebar):
        assert sidebar is not None

    def test_all_feeds_item_always_present(self, sidebar, db):
        _, conn = db
        sidebar.load_feeds(conn)
        # Primeiro item da árvore deve ser "Todos os feeds"
        first = sidebar._tree.invisibleRootItem().child(0)
        assert first is not None
        assert "Todos" in first.text(0)

    def test_load_empty_db_shows_hint(self, sidebar, db):
        _, conn = db
        sidebar.load_feeds(conn)
        # Com banco vazio, deve ter item de hint
        root = sidebar._tree.invisibleRootItem()
        assert root.childCount() >= 1

    def test_feeds_appear_under_category(self, sidebar, db):
        _, conn = db
        _insert_feed(conn, "https://a.com/feed", title="Feed A", category="Tecnologia")
        _insert_feed(conn, "https://b.com/feed", title="Feed B", category="Tecnologia")
        sidebar.load_feeds(conn)
        root = sidebar._tree.invisibleRootItem()
        # Deve haver categoria "Tecnologia" com 2 filhos
        cat_item = None
        for i in range(root.childCount()):
            if root.child(i).text(0) == "Tecnologia":
                cat_item = root.child(i)
                break
        assert cat_item is not None
        assert cat_item.childCount() == 2

    def test_unread_count_shown_in_label(self, sidebar, db):
        _, conn = db
        feed_id = _insert_feed(conn, "https://u.com/feed", title="Feed Unread")
        _insert_article(conn, feed_id, "https://u.com/a1", is_read=0)
        _insert_article(conn, feed_id, "https://u.com/a2", is_read=0)
        sidebar.load_feeds(conn)
        # O item do feed deve conter "(2)"
        root = sidebar._tree.invisibleRootItem()
        found = False
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if "(2)" in child.text(0):
                    found = True
                    break
        assert found

    def test_disabled_feed_not_shown(self, sidebar, db):
        _, conn = db
        _insert_feed(conn, "https://dis.com/feed", title="Disabled", enabled=0)
        sidebar.load_feeds(conn)
        # Percorre toda a árvore procurando "Disabled"
        root = sidebar._tree.invisibleRootItem()
        labels = []
        for i in range(root.childCount()):
            item = root.child(i)
            labels.append(item.text(0))
            for j in range(item.childCount()):
                labels.append(item.child(j).text(0))
        assert not any("Disabled" in lbl for lbl in labels)

    def test_feed_selected_signal_emits_feed_id(self, sidebar, db):
        _, conn = db
        feed_id = _insert_feed(conn, "https://s.com/feed", title="Signal Feed")
        sidebar.load_feeds(conn)

        emitted = []
        sidebar.feed_selected.connect(lambda fid: emitted.append(fid))

        # Encontra o item do feed na árvore e simula clique
        from PySide6.QtCore import Qt
        root = sidebar._tree.invisibleRootItem()
        target = None
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.data(0, Qt.ItemDataRole.UserRole) == feed_id:
                    target = child
                    break
        assert target is not None
        sidebar._on_item_clicked(target, 0)
        assert feed_id in emitted

    def test_all_feeds_click_emits_minus_one(self, sidebar, db):
        _, conn = db
        sidebar.load_feeds(conn)
        emitted = []
        sidebar.feed_selected.connect(lambda fid: emitted.append(fid))

        from PySide6.QtCore import Qt
        first = sidebar._tree.invisibleRootItem().child(0)
        sidebar._on_item_clicked(first, 0)
        assert -1 in emitted

    def test_category_click_does_not_emit(self, sidebar, db):
        _, conn = db
        _insert_feed(conn, "https://c.com/feed", category="Categoria")
        sidebar.load_feeds(conn)
        emitted = []
        sidebar.feed_selected.connect(lambda fid: emitted.append(fid))

        from PySide6.QtCore import Qt
        root = sidebar._tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.data(0, Qt.ItemDataRole.UserRole) is None and item.text(0) == "Categoria":
                sidebar._on_item_clicked(item, 0)
                break
        assert emitted == []

    def test_multiple_categories(self, sidebar, db):
        _, conn = db
        _insert_feed(conn, "https://t.com/feed", category="Tech")
        _insert_feed(conn, "https://p.com/feed", category="Política")
        sidebar.load_feeds(conn)
        root = sidebar._tree.invisibleRootItem()
        cat_names = [root.child(i).text(0) for i in range(root.childCount())]
        assert "Tech" in cat_names
        assert "Política" in cat_names


# ---------------------------------------------------------------------------
# TestArticleList
# ---------------------------------------------------------------------------

class TestArticleList:
    @pytest.fixture
    def article_list(self, qapp):
        from app.ui.views.article_list import ArticleList
        w = ArticleList()
        yield w
        w.deleteLater()

    def test_instantiation(self, article_list):
        assert article_list is not None

    def test_load_all_feeds_returns_count(self, article_list, db):
        _, conn = db
        fid = _insert_feed(conn, "https://al.com/feed")
        _insert_article(conn, fid, "https://al.com/a1")
        _insert_article(conn, fid, "https://al.com/a2")
        count = article_list.load_articles(-1, conn)
        assert count == 2

    def test_load_specific_feed_filters(self, article_list, db):
        _, conn = db
        fid1 = _insert_feed(conn, "https://f1.com/feed")
        fid2 = _insert_feed(conn, "https://f2.com/feed")
        _insert_article(conn, fid1, "https://f1.com/a1")
        _insert_article(conn, fid1, "https://f1.com/a2")
        _insert_article(conn, fid2, "https://f2.com/a1")
        count = article_list.load_articles(fid1, conn)
        assert count == 2

    def test_load_sets_current_feed_id(self, article_list, db):
        _, conn = db
        fid = _insert_feed(conn, "https://cf.com/feed")
        article_list.load_articles(fid, conn)
        assert article_list._current_feed_id == fid

    def test_article_count_matches_loaded(self, article_list, db):
        _, conn = db
        fid = _insert_feed(conn, "https://ac.com/feed")
        _insert_article(conn, fid, "https://ac.com/a1")
        _insert_article(conn, fid, "https://ac.com/a2")
        _insert_article(conn, fid, "https://ac.com/a3")
        article_list.load_articles(-1, conn)
        assert article_list.article_count() == 3

    def test_empty_feed_shows_zero(self, article_list, db):
        _, conn = db
        count = article_list.load_articles(-1, conn)
        assert count == 0
        assert article_list.article_count() == 0

    def test_article_selected_signal(self, article_list, db):
        _, conn = db
        fid = _insert_feed(conn, "https://sig.com/feed")
        aid = _insert_article(conn, fid, "https://sig.com/a1")
        article_list.load_articles(-1, conn)

        emitted = []
        article_list.article_selected.connect(lambda aid: emitted.append(aid))

        from PySide6.QtCore import Qt
        item = article_list._list.item(0)
        assert item is not None
        article_list._on_item_clicked(item)
        assert aid in emitted

    def test_on_feed_updated_reloads_current(self, article_list, db):
        _, conn = db
        fid = _insert_feed(conn, "https://upd.com/feed")
        _insert_article(conn, fid, "https://upd.com/a1")
        article_list.load_articles(fid, conn)
        assert article_list.article_count() == 1

        # Insere mais um artigo e simula sinal do FetchWorker
        _insert_article(conn, fid, "https://upd.com/a2")
        with patch.object(article_list, "load_articles") as mock_load:
            article_list.on_feed_updated(fid, 1)
        mock_load.assert_called_once_with(fid)

    def test_on_feed_updated_does_not_reload_other_feed(self, article_list, db):
        _, conn = db
        fid1 = _insert_feed(conn, "https://r1.com/feed")
        fid2 = _insert_feed(conn, "https://r2.com/feed")
        article_list.load_articles(fid1, conn)
        with patch.object(article_list, "load_articles") as mock_load:
            article_list.on_feed_updated(fid2, 3)
        mock_load.assert_not_called()

    def test_reload_clears_previous_items(self, article_list, db):
        _, conn = db
        fid = _insert_feed(conn, "https://cl.com/feed")
        _insert_article(conn, fid, "https://cl.com/a1")
        article_list.load_articles(-1, conn)
        assert article_list.article_count() == 1
        # Carrega feed diferente vazio — lista deve ser limpa
        fid2 = _insert_feed(conn, "https://empty.com/feed")
        article_list.load_articles(fid2, conn)
        assert article_list.article_count() == 0


# ---------------------------------------------------------------------------
# TestReaderPane
# ---------------------------------------------------------------------------

class TestReaderPane:
    @pytest.fixture
    def reader(self, qapp):
        from app.ui.views.reader_pane import ReaderPane
        w = ReaderPane()
        yield w
        w.deleteLater()

    def test_instantiation(self, reader):
        assert reader is not None

    def test_placeholder_shown_initially(self, reader):
        # isVisible() depende da janela estar exibida; usar isHidden() para testes headless.
        # No design R1 a visibilidade do conteúdo é controlada no container _content
        # (que envolve título, corpo no webview e destaques), não widget a widget.
        assert not reader._placeholder.isHidden()
        assert reader._content.isHidden()

    def test_show_article_displays_title(self, reader, db):
        _, conn = db
        fid = _insert_feed(conn, "https://r.com/feed")
        aid = _insert_article(conn, fid, "https://r.com/a1", title="Título do Artigo")
        result = reader.show_article(aid, conn)
        assert result is True
        assert reader._title_lbl.text() == "Título do Artigo"

    def test_show_article_hides_placeholder(self, reader, db):
        _, conn = db
        fid = _insert_feed(conn, "https://r2.com/feed")
        aid = _insert_article(conn, fid, "https://r2.com/a1")
        reader.show_article(aid, conn)
        assert reader._placeholder.isHidden()

    def test_show_article_makes_content_visible(self, reader, db):
        _, conn = db
        fid = _insert_feed(conn, "https://r3.com/feed")
        aid = _insert_article(conn, fid, "https://r3.com/a1")
        reader.show_article(aid, conn)
        assert not reader._title_lbl.isHidden()

    def test_show_article_marks_as_read(self, reader, db):
        _, conn = db
        fid = _insert_feed(conn, "https://mr.com/feed")
        aid = _insert_article(conn, fid, "https://mr.com/a1", is_read=0)
        reader.show_article(aid, conn)
        row = conn.execute("SELECT is_read FROM articles WHERE id=?", (aid,)).fetchone()
        assert row["is_read"] == 1

    def test_show_already_read_no_signal(self, reader, db):
        _, conn = db
        fid = _insert_feed(conn, "https://ar.com/feed")
        aid = _insert_article(conn, fid, "https://ar.com/a1", is_read=1)
        emitted = []
        reader.article_read.connect(lambda aid: emitted.append(aid))
        reader.show_article(aid, conn)
        assert emitted == []  # já lido → não emite

    def test_show_unread_emits_article_read(self, reader, db):
        _, conn = db
        fid = _insert_feed(conn, "https://er.com/feed")
        aid = _insert_article(conn, fid, "https://er.com/a1", is_read=0)
        emitted = []
        reader.article_read.connect(lambda a: emitted.append(a))
        reader.show_article(aid, conn)
        assert aid in emitted

    def test_show_nonexistent_returns_false(self, reader, db):
        _, conn = db
        result = reader.show_article(99999, conn)
        assert result is False

    def test_clear_restores_placeholder(self, reader, db):
        _, conn = db
        fid = _insert_feed(conn, "https://cl.com/feed")
        aid = _insert_article(conn, fid, "https://cl.com/a1")
        reader.show_article(aid, conn)
        reader.clear()
        assert not reader._placeholder.isHidden()
        assert reader._content.isHidden()

    def test_mark_as_read_updates_read_at(self, reader, db):
        _, conn = db
        fid = _insert_feed(conn, "https://ra.com/feed")
        aid = _insert_article(conn, fid, "https://ra.com/a1", is_read=0)
        reader._mark_as_read(aid, conn)
        row = conn.execute("SELECT is_read, read_at FROM articles WHERE id=?", (aid,)).fetchone()
        assert row["is_read"] == 1
        assert row["read_at"] is not None

    def test_mark_as_read_idempotent(self, reader, db):
        _, conn = db
        fid = _insert_feed(conn, "https://id.com/feed")
        aid = _insert_article(conn, fid, "https://id.com/a1", is_read=0)
        reader._mark_as_read(aid, conn)
        reader._mark_as_read(aid, conn)
        row = conn.execute("SELECT is_read FROM articles WHERE id=?", (aid,)).fetchone()
        assert row["is_read"] == 1

    def test_opinion_type_in_meta(self, reader, db):
        _, conn = db
        fid = _insert_feed(conn, "https://op.com/feed")
        aid = _insert_article(
            conn, fid, "https://op.com/a1",
            title="Opinião sobre tudo", article_type="opinion"
        )
        reader.show_article(aid, conn)
        assert "OPINION" in reader._meta_lbl.text()
