"""
Testes para app/core/interests.py (KOSMOS v3, Fase 5).

Cobre:
  - extract_topics: tags + entidades, dedup case-insensitive, vazio sem análise;
  - update_from_article: envia temas ao shared_topic_profile (source kosmos);
    no-op sem análise; no-op para artigo inexistente; delta correto;
  - apply_manual_topics: envia tags manuais com peso maior; limpa vazias; no-op vazio;
  - config: campo manual_topics (default [], persistido em settings.json).

shared_topic_profile.update_scores é mockado (não toca o sync_root real).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


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


def _insert_article(conn, feed_id, ai_tags=None, ai_entities=None) -> int:
    cur = conn.execute(
        """
        INSERT INTO articles (feed_id, url, title, ai_tags, ai_entities)
        VALUES (?, ?, ?, ?, ?)
        """,
        (feed_id, "https://j.com/a", "T", ai_tags, ai_entities),
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
    feed_id = cur.lastrowid
    yield conn, feed_id
    conn.close()


# ---------------------------------------------------------------------------
# extract_topics
# ---------------------------------------------------------------------------

class TestExtractTopics:
    def test_tags_and_entities(self):
        from app.core.interests import extract_topics
        topics = extract_topics(
            json.dumps(["política", "economia"]),
            json.dumps([{"nome": "Lula", "tipo": "pessoa"}, {"nome": "STF", "tipo": "org"}]),
        )
        assert topics == ["política", "economia", "Lula", "STF"]

    def test_dedup_case_insensitive(self):
        from app.core.interests import extract_topics
        topics = extract_topics(
            json.dumps(["Python", "python"]),
            json.dumps([{"nome": "PYTHON", "tipo": "tema"}]),
        )
        assert topics == ["Python"]

    def test_empty_returns_empty(self):
        from app.core.interests import extract_topics
        assert extract_topics(None, None) == []

    def test_malformed_json_ignored(self):
        from app.core.interests import extract_topics
        assert extract_topics("{not json", "also not") == []

    def test_plain_string_entities(self):
        from app.core.interests import extract_topics
        topics = extract_topics(None, json.dumps(["ACME", "Brasil"]))
        assert topics == ["ACME", "Brasil"]


# ---------------------------------------------------------------------------
# update_from_article
# ---------------------------------------------------------------------------

class TestUpdateFromArticle:
    def test_sends_topics_to_profile(self, db):
        conn, fid = db
        from app.core import interests
        aid = _insert_article(
            conn, fid,
            ai_tags=json.dumps(["clima", "energia"]),
            ai_entities=json.dumps([{"nome": "ONU", "tipo": "org"}]),
        )
        with patch("shared_topic_profile.update_scores") as mock:
            n = interests.update_from_article(aid, conn=conn)
        assert n == 3
        mock.assert_called_once()
        topics, delta, source = mock.call_args[0]
        assert topics == ["clima", "energia", "ONU"]
        assert delta == interests._ANALYSIS_DELTA
        assert source == "kosmos"

    def test_no_analysis_noop(self, db):
        conn, fid = db
        from app.core import interests
        aid = _insert_article(conn, fid, ai_tags=None, ai_entities=None)
        with patch("shared_topic_profile.update_scores") as mock:
            n = interests.update_from_article(aid, conn=conn)
        assert n == 0
        mock.assert_not_called()

    def test_missing_article_noop(self, db):
        conn, _ = db
        from app.core import interests
        with patch("shared_topic_profile.update_scores") as mock:
            n = interests.update_from_article(99999, conn=conn)
        assert n == 0
        mock.assert_not_called()


# ---------------------------------------------------------------------------
# apply_manual_topics
# ---------------------------------------------------------------------------

class TestApplyManualTopics:
    def test_applies_with_higher_weight(self):
        from app.core import interests
        with patch("shared_topic_profile.update_scores") as mock:
            n = interests.apply_manual_topics(["craftivismo", "anarquismo"])
        assert n == 2
        topics, delta, source = mock.call_args[0]
        assert topics == ["craftivismo", "anarquismo"]
        assert delta == interests._MANUAL_DELTA
        assert source == "kosmos"
        assert interests._MANUAL_DELTA > interests._ANALYSIS_DELTA

    def test_strips_blank_entries(self):
        from app.core import interests
        with patch("shared_topic_profile.update_scores") as mock:
            n = interests.apply_manual_topics(["  zine  ", "", "  "])
        assert n == 1
        topics, _, _ = mock.call_args[0]
        assert topics == ["zine"]

    def test_empty_noop(self):
        from app.core import interests
        with patch("shared_topic_profile.update_scores") as mock:
            assert interests.apply_manual_topics([]) == 0
            assert interests.apply_manual_topics(None) == 0
        mock.assert_not_called()


# ---------------------------------------------------------------------------
# Config: manual_topics
# ---------------------------------------------------------------------------

class TestManualTopicsConfig:
    def test_default_empty_list(self):
        from app.utils.config import KosmosConfig
        assert KosmosConfig().manual_topics == []

    def test_is_persistent_field(self):
        from app.utils.config import _PERSISTENT_FIELDS
        assert "manual_topics" in _PERSISTENT_FIELDS

    def test_save_persists_manual_topics(self, tmp_path):
        from app.utils.config import KosmosConfig, save_config
        cfg = KosmosConfig()
        cfg.config_path = str(tmp_path)
        cfg.manual_topics = ["política", "tecnologia"]
        save_config(cfg)
        data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert data["manual_topics"] == ["política", "tecnologia"]
