"""
Testes da seção de análise AI do ReaderPane (Fase 4, item 4).

Cobre:
  - _parse_analysis: parse dos campos JSON; inválido/ausente → defaults seguros.
  - _analysis_html: monta progressivamente (só rápidos, rico, vazio); escapa HTML.
  - ReaderPane: render inicial com/sem análise; emite analysis_requested ao abrir;
    on_full_analysis_done/on_quick_analysis_done atualizam só o artigo atual.
"""
from __future__ import annotations

import itertools
import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest

from app.ui.views.reader_pane import _analysis_html, _parse_analysis

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


def _insert(conn, fid, *, ai_summary=None, ai_sentiment=None, ai_clickbait_score=None,
            ai_tags=None, ai_five_ws=None, ai_entities=None, ai_bias=None) -> int:
    cur = conn.execute(
        "INSERT INTO articles (feed_id, url, title, content_excerpt, ai_summary, ai_sentiment, "
        "ai_clickbait_score, ai_tags, ai_five_ws, ai_entities, ai_bias) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (fid, f"https://j.com/a{next(_counter)}", "Título", "trecho", ai_summary, ai_sentiment,
         ai_clickbait_score, ai_tags, ai_five_ws, ai_entities, ai_bias),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def env(tmp_path, qapp):
    import app.core.database as db_module
    from app.ui.views.reader_pane import ReaderPane
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    fid = conn.execute("INSERT INTO feeds (url, title) VALUES (?, ?)", ("https://j.com/rss", "J")).lastrowid
    conn.commit()
    with patch.object(db_module, "DB_PATH", db_file):
        reader = ReaderPane()
        yield reader, conn, fid
    conn.close()


# ---------------------------------------------------------------------------
# _parse_analysis
# ---------------------------------------------------------------------------

class TestParseAnalysis:
    def test_parses_all(self):
        ai = _parse_analysis({
            "ai_summary": "  s  ", "ai_sentiment": "positivo", "ai_clickbait_score": 0.4,
            "ai_tags": '["a","b"]', "ai_five_ws": '{"quem":"X"}',
            "ai_entities": '[{"nome":"Y","tipo":"tema"}]', "ai_bias": '{"espectro":"centro"}',
        })
        assert ai["summary"] == "s"
        assert ai["tags"] == ["a", "b"]
        assert ai["five_ws"] == {"quem": "X"}
        assert ai["entities"] == [{"nome": "Y", "tipo": "tema"}]
        assert ai["bias"] == {"espectro": "centro"}

    def test_invalid_json_defaults(self):
        ai = _parse_analysis({"ai_tags": "xx", "ai_five_ws": "{", "ai_entities": None})
        assert ai["tags"] == [] and ai["five_ws"] == {} and ai["entities"] == []

    def test_wrong_type_defaults(self):
        # JSON válido mas de tipo errado (lista onde se espera dict) → default
        assert _parse_analysis({"ai_five_ws": "[1,2]"})["five_ws"] == {}

    def test_empty(self):
        ai = _parse_analysis({})
        assert ai["summary"] == "" and ai["clickbait"] is None and ai["tags"] == []


# ---------------------------------------------------------------------------
# _analysis_html
# ---------------------------------------------------------------------------

class TestAnalysisHtml:
    def test_quick_only(self):
        html = _analysis_html({"summary": "resumo", "sentiment": "negativo",
                               "clickbait": 0.5, "tags": ["ia"]})
        assert "Resumo:" in html and "resumo" in html
        assert "Sentimento: negativo" in html
        assert "Clickbait: 50%" in html
        assert "Tags:" in html and "ia" in html
        assert "Quem" not in html   # ricos ausentes

    def test_rich_fields(self):
        html = _analysis_html({
            "five_ws": {"quem": "Lula", "por_que": "eleição"},
            "entities": [{"nome": "Brasil", "tipo": "lugar"}, {"nome": "STF", "tipo": ""}],
            "bias": {"espectro": "centro", "qualidade_apuracao": "alta", "marcadores": ["m1"]},
        })
        assert "Quem:" in html and "Lula" in html and "Por quê:" in html
        assert "Brasil (lugar)" in html and "STF" in html
        assert "espectro centro" in html and "apuração alta" in html
        assert "Marcadores:" in html and "m1" in html

    def test_empty_returns_blank(self):
        assert _analysis_html({}) == ""
        assert _analysis_html({"summary": "", "tags": [], "five_ws": {}}) == ""

    def test_escapes_html(self):
        html = _analysis_html({"summary": "<script>x</script>"})
        assert "<script>" not in html and "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# ReaderPane
# ---------------------------------------------------------------------------

class TestReaderAnalysisSection:
    def test_renders_existing_analysis_on_open(self, env):
        reader, conn, fid = env
        aid = _insert(conn, fid, ai_summary="resumo", ai_sentiment="neutro",
                      ai_five_ws='{"quem":"X"}')
        reader.show_article(aid, conn=conn)
        assert reader._analysis_header.isHidden() is False
        assert "resumo" in reader._analysis_lbl.text()
        assert "Quem:" in reader._analysis_lbl.text()

    def test_section_hidden_without_analysis(self, env):
        reader, conn, fid = env
        aid = _insert(conn, fid)   # sem campos de AI
        reader.show_article(aid, conn=conn)
        assert reader._analysis_header.isHidden() is True
        assert reader._analysis_lbl.text() == ""

    def test_open_emits_analysis_requested(self, env):
        reader, conn, fid = env
        aid = _insert(conn, fid)
        got = []
        reader.analysis_requested.connect(got.append)
        reader.show_article(aid, conn=conn)
        assert got == [aid]

    def test_full_analysis_done_updates_current(self, env):
        reader, conn, fid = env
        aid = _insert(conn, fid, ai_summary="resumo")   # só rápido
        reader.show_article(aid, conn=conn)
        assert "Quem:" not in reader._analysis_lbl.text()
        # Call B chega e é persistida
        conn.execute("UPDATE articles SET ai_five_ws='{\"quem\":\"Y\"}', "
                     "ai_bias='{\"espectro\":\"direita\"}' WHERE id=?", (aid,))
        conn.commit()
        reader.on_full_analysis_done(aid, conn=conn)
        assert "Quem:" in reader._analysis_lbl.text() and "Y" in reader._analysis_lbl.text()
        assert "espectro direita" in reader._analysis_lbl.text()

    def test_investigation_button_emits(self, env):
        reader, conn, fid = env
        aid = _insert(conn, fid)
        reader.show_article(aid, conn=conn)
        got = []
        reader.add_to_investigation_requested.connect(got.append)
        reader._on_add_to_investigation()
        assert got == [aid]

    def test_analysis_done_ignored_when_not_current(self, env):
        reader, conn, fid = env
        opened = _insert(conn, fid, ai_summary="aberto")
        other = _insert(conn, fid, ai_five_ws='{"quem":"Z"}')
        reader.show_article(opened, conn=conn)
        reader.on_full_analysis_done(other, conn=conn)   # outro artigo
        assert "Z" not in reader._analysis_lbl.text()
        assert "aberto" in reader._analysis_lbl.text()

    def test_quick_analysis_done_updates_current(self, env):
        reader, conn, fid = env
        aid = _insert(conn, fid)   # sem análise
        reader.show_article(aid, conn=conn)
        assert reader._analysis_header.isHidden() is True
        conn.execute("UPDATE articles SET ai_sentiment='positivo', ai_tags='[\"t\"]' WHERE id=?", (aid,))
        conn.commit()
        reader.on_quick_analysis_done(aid, conn=conn)
        assert reader._analysis_header.isHidden() is False
        assert "Sentimento: positivo" in reader._analysis_lbl.text()
