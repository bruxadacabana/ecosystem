"""
Testes de app/ui/views/article_list.py — visuais de análise nos cards (Fase 4, item 3).

Cobre:
  - _analysis_from_data: parse de ai_tags JSON; None/inválido → [].
  - ArticleCard: renderiza borda por sentimento (property), chips e ícone de clickbait;
    visual neutro sem análise; ícone só acima do limiar; chips limitados; apply ao vivo.
  - ArticleList: load_articles traz campos de AI; on_quick_analysis_done atualiza o card;
    id inexistente e on_analysis_failed não quebram; _card_for.
"""
from __future__ import annotations

import itertools
import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401 — configura sys.path
import pytest
from PySide6.QtWidgets import QLabel

from app.ui.views import article_list as al
from app.ui.views.article_list import ArticleCard, ArticleList, _analysis_from_data
from app.ui.views.feed_sidebar import ALL_FEEDS_ID

_counter = itertools.count()


def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_db_at(path: Path) -> None:
    import app.core.database as db_module
    with patch.object(db_module, "DB_PATH", path):
        db_module.init_db()


def _insert(conn, fid, *, title="T", ai_sentiment=None, ai_clickbait_score=None, ai_tags=None) -> int:
    cur = conn.execute(
        "INSERT INTO articles (feed_id, url, title, published_at, ai_sentiment, "
        "ai_clickbait_score, ai_tags) VALUES (?,?,?,?,?,?,?)",
        (fid, f"https://j.com/a{next(_counter)}", title, "2026-06-01T00:00:00Z",
         ai_sentiment, ai_clickbait_score, ai_tags),
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
    yield conn, cur.lastrowid, db_file
    conn.close()


def _chips(card) -> list[str]:
    return [w.text() for w in card.findChildren(QLabel) if w.objectName() == "tag_chip"]


def _clickbait_icon(card):
    return card.findChild(QLabel, "clickbait_icon")


def _clickbait_shown(card) -> bool:
    """No design novo o badge de clickbait sempre existe, mas fica oculto até a Call A
    indicar valor alto — então testamos visibilidade, não presença."""
    w = _clickbait_icon(card)
    return w is not None and not w.isHidden()


# ---------------------------------------------------------------------------
# _analysis_from_data
# ---------------------------------------------------------------------------

class TestAnalysisFromData:
    def test_parses_tags_json(self):
        s, c, tags = _analysis_from_data({"ai_sentiment": "positivo", "ai_clickbait_score": 0.3,
                                          "ai_tags": '["a", "b"]'})
        assert s == "positivo" and c == 0.3 and tags == ["a", "b"]

    def test_invalid_tags_empty(self):
        assert _analysis_from_data({"ai_tags": "não json"})[2] == []

    def test_missing_all(self):
        assert _analysis_from_data({}) == (None, None, [])


# ---------------------------------------------------------------------------
# ArticleCard
# ---------------------------------------------------------------------------

class TestArticleCard:
    def test_neutral_without_analysis(self, qapp):
        card = ArticleCard({"id": 1, "title": "X"})
        assert card.property("sentiment") in (None, "")
        assert card._tags_container.isHidden() is True
        assert card._clickbait_badge.isHidden() is True

    def test_renders_sentiment_border_and_chips(self, qapp):
        card = ArticleCard({"id": 1, "title": "X", "ai_sentiment": "negativo",
                            "ai_clickbait_score": 0.1, "ai_tags": '["ia", "python"]'})
        assert card.property("sentiment") == "negativo"
        assert _chips(card) == ["ia", "python"]
        assert not _clickbait_shown(card)   # clickbait baixo → badge oculto

    def test_clickbait_icon_above_threshold(self, qapp):
        card = ArticleCard({"id": 1, "title": "X", "ai_sentiment": "neutro",
                            "ai_clickbait_score": 0.9, "ai_tags": None})
        assert _clickbait_shown(card)

    def test_chips_capped(self, qapp):
        card = ArticleCard({"id": 1, "title": "X",
                            "ai_tags": '["a","b","c","d","e","f"]'})
        assert len(_chips(card)) == 4   # _MAX_CHIPS

    def test_apply_quick_analysis_live(self, qapp):
        card = ArticleCard({"id": 1, "title": "X"})   # começa neutro
        card.apply_quick_analysis("positivo", 0.8, ["tag"])
        assert card.property("sentiment") == "positivo"
        assert _chips(card) == ["tag"]
        assert _clickbait_shown(card)
        assert card._tags_container.isHidden() is False

    def test_invalid_sentiment_clears_property(self, qapp):
        card = ArticleCard({"id": 1, "title": "X"})
        card.apply_quick_analysis("raivoso", None, [])
        assert card.property("sentiment") == ""

    def test_read_dot_reflects_is_read(self, qapp):
        unread = ArticleCard({"id": 1, "title": "X", "is_read": 0})
        read = ArticleCard({"id": 2, "title": "Y", "is_read": 1})
        assert unread._dot.property("read") is False
        assert read._dot.property("read") is True

    def test_lang_badge_when_language(self, qapp):
        card = ArticleCard({"id": 1, "title": "X", "language_detected": "en"})
        badge = card.findChild(QLabel, "lang_badge")
        assert badge is not None and badge.text() == "EN"

    def test_no_lang_badge_without_language(self, qapp):
        card = ArticleCard({"id": 1, "title": "X"})
        assert card.findChild(QLabel, "lang_badge") is None

    def test_summary_strips_html(self, qapp):
        card = ArticleCard({"id": 1, "title": "X", "content_excerpt": "<p>Resumo do <b>feed</b></p>"})
        assert "<" not in card._summary_lbl.text()
        assert "Resumo do feed" in card._summary_lbl.text()
        assert not card._summary_lbl.isHidden()

    def test_author_in_meta(self, qapp):
        card = ArticleCard({"id": 1, "title": "X", "feed_title": "Feed", "author": "Maria"})
        assert "Maria" in card._meta_lbl.text()

    def test_alert_prefix_preserved_on_title_update(self, qapp):
        card = ArticleCard({"id": 1, "title": "Orig", "alerted": True})
        card.set_title("Traduzido")
        assert card._title_lbl.text() == "🔔 Traduzido"


# ---------------------------------------------------------------------------
# ArticleList
# ---------------------------------------------------------------------------

class TestArticleList:
    def test_load_brings_analysis_fields(self, qapp, db):
        conn, fid, _ = db
        aid = _insert(conn, fid, title="Card", ai_sentiment="positivo",
                      ai_clickbait_score=0.2, ai_tags='["x"]')
        lst = ArticleList()
        lst.load_articles(ALL_FEEDS_ID, conn=conn)
        card = lst._card_for(aid)
        assert card is not None
        assert card.property("sentiment") == "positivo"
        assert _chips(card) == ["x"]

    def test_on_quick_analysis_done_updates_card(self, qapp, db):
        conn, fid, _ = db
        aid = _insert(conn, fid, title="Pendente")   # sem análise ainda
        lst = ArticleList()
        lst.load_articles(ALL_FEEDS_ID, conn=conn)
        assert lst._card_for(aid).property("sentiment") in (None, "")
        # análise chega e é persistida
        conn.execute("UPDATE articles SET ai_sentiment='negativo', ai_clickbait_score=0.9, "
                     "ai_tags='[\"alerta\"]' WHERE id=?", (aid,))
        conn.commit()
        lst.on_quick_analysis_done(aid, conn=conn)
        card = lst._card_for(aid)
        assert card.property("sentiment") == "negativo"
        assert _chips(card) == ["alerta"]
        assert _clickbait_shown(card)

    def test_on_quick_analysis_done_unknown_id_no_crash(self, qapp, db):
        conn, _, _ = db
        lst = ArticleList()
        lst.load_articles(ALL_FEEDS_ID, conn=conn)
        lst.on_quick_analysis_done(99999, conn=conn)   # não deve levantar

    def test_on_analysis_failed_no_crash(self, qapp, db):
        conn, fid, _ = db
        aid = _insert(conn, fid)
        lst = ArticleList()
        lst.load_articles(ALL_FEEDS_ID, conn=conn)
        lst.on_analysis_failed(aid)   # apenas loga; card segue neutro
        assert lst._card_for(aid).property("sentiment") in (None, "")

    def test_card_for_returns_none_when_absent(self, qapp, db):
        conn, _, _ = db
        lst = ArticleList()
        lst.load_articles(ALL_FEEDS_ID, conn=conn)
        assert lst._card_for(12345) is None

    def test_context_menu_request_emits_add_to_investigation(self, qapp, db):
        conn, fid, _ = db
        aid = _insert(conn, fid, title="X")
        lst = ArticleList()
        lst.load_articles(ALL_FEEDS_ID, conn=conn)
        got = []
        lst.add_to_investigation_requested.connect(got.append)
        lst._request_add_to_investigation(lst._list.item(0))
        assert got == [aid]
