"""
Testes de app/core/analysis_worker.py.

Cobre:
  - _extract_json: JSON limpo, com cercas markdown, com ruído antes/depois, vírgula
    final, não-JSON → None, não-dict → None.
  - _normalize_quick/_normalize_full: defaults seguros contra deriva do modelo.
  - analyze_quick/analyze_full: parse OK; JSON inválido 2x → None (chat 2x);
    LogosUnavailable propaga.
  - Helpers de DB: fila pending/failed/old-schema, claim atômico, save Call A/B,
    failed/revert, flags has_quick/has_full, TTL > 6 meses.
  - AnalysisWorker: _preanalyze (sucesso/falha/offline), _analyze_opened (Call A+B,
    só B, nada), fila P1 e preempção.

logos_client.chat é mockado (sem rede). DB em arquivo temporário.
"""
from __future__ import annotations

import itertools
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401 — configura sys.path para ecosystem_client
import pytest

import app.core.analysis_worker as aw
from app.core.analysis_worker import (
    ANALYSIS_SCHEMA_VERSION,
    LogosUnavailable,
    _extract_json,
    _normalize_full,
    _normalize_quick,
    analyze_full,
    analyze_quick,
    apply_analysis_ttl,
    claim_for_analysis,
    get_article_for_analysis,
    get_pending_analysis,
    mark_analysis_failed,
    revert_to_pending,
    save_full_analysis,
    save_quick_analysis,
)

_counter = itertools.count()


# ---------------------------------------------------------------------------
# Banco temporário
# ---------------------------------------------------------------------------

def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_db_at(path: Path) -> None:
    import app.core.database as db_module
    with patch.object(db_module, "DB_PATH", path):
        db_module.init_db()


def _insert(conn, fid, *, title="T", published_at="2026-06-01T00:00:00Z",
            content_text=None, content_excerpt=None, status="pending",
            schema_version=0, ai_tags=None, ai_five_ws=None, ai_entities=None) -> int:
    cur = conn.execute(
        "INSERT INTO articles (feed_id, url, title, published_at, content_text, content_excerpt, "
        "analysis_status, analysis_schema_version, ai_tags, ai_five_ws, ai_entities) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (fid, f"https://j.com/a{next(_counter)}", title, published_at, content_text,
         content_excerpt, status, schema_version, ai_tags, ai_five_ws, ai_entities),
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


@pytest.fixture
def worker(qapp, db):
    """Worker com get_conn redirecionado para o DB de teste (cada helper abre o seu)."""
    _, _, db_file = db
    w = aw.AnalysisWorker()
    with patch.object(aw, "get_conn", lambda: _open_db(db_file)):
        yield w
    if w.isRunning():
        w.stop()
        w.wait(2000)


# ===========================================================================
# _extract_json
# ===========================================================================

class TestExtractJson:
    def test_clean(self):
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_markdown_fenced(self):
        assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_noise_around(self):
        assert _extract_json('Claro! Aqui:\n{"a": 1}\nEspero ter ajudado.') == {"a": 1}

    def test_trailing_comma_repaired(self):
        assert _extract_json('{"a": 1, "b": [2, 3,],}') == {"a": 1, "b": [2, 3]}

    def test_non_json_returns_none(self):
        assert _extract_json("desculpe, não consego analisar") is None

    def test_empty_returns_none(self):
        assert _extract_json("") is None

    def test_non_dict_returns_none(self):
        assert _extract_json("[1, 2, 3]") is None


# ===========================================================================
# Normalização
# ===========================================================================

class TestNormalizeQuick:
    def test_valid(self):
        out = _normalize_quick({"tags": ["IA", "Python"], "sentimento": "Positivo",
                                "clickbait": 0.4, "idioma": "pt", "resumo": "x"})
        assert out["tags"] == ["ia", "python"]
        assert out["sentimento"] == "positivo"
        assert out["clickbait"] == 0.4

    def test_bad_sentiment_defaults_neutro(self):
        assert _normalize_quick({"sentimento": "raivoso"})["sentimento"] == "neutro"

    def test_clickbait_clamped(self):
        assert _normalize_quick({"clickbait": 5})["clickbait"] == 1.0
        assert _normalize_quick({"clickbait": -2})["clickbait"] == 0.0
        assert _normalize_quick({"clickbait": "x"})["clickbait"] == 0.0

    def test_tags_capped_and_string(self):
        assert _normalize_quick({"tags": [str(i) for i in range(10)]})["tags"] == ["0", "1", "2", "3", "4", "5"]
        assert _normalize_quick({"tags": "única"})["tags"] == ["única"]

    def test_missing_fields_safe(self):
        out = _normalize_quick({})
        assert out["tags"] == [] and out["sentimento"] == "neutro" and out["resumo"] == ""


class TestNormalizeFull:
    def test_five_ws_filled_and_missing(self):
        out = _normalize_full({"cinco_ws": {"quem": "A", "o_que": "B"}})
        assert out["cinco_ws"]["quem"] == "A"
        assert out["cinco_ws"]["por_que"] == ""

    def test_entities_dict_and_string(self):
        out = _normalize_full({"entidades": [{"nome": "Lula", "tipo": "Pessoa"}, "Brasil", {"x": 1}]})
        assert {"nome": "Lula", "tipo": "pessoa"} in out["entidades"]
        assert {"nome": "Brasil", "tipo": ""} in out["entidades"]
        assert len(out["entidades"]) == 2   # dict sem 'nome' descartado

    def test_bias_defaults(self):
        out = _normalize_full({})
        assert out["vies"]["espectro"] == "indefinido"
        assert out["vies"]["marcadores"] == []

    def test_bias_marcadores_string(self):
        out = _normalize_full({"vies": {"espectro": "Centro", "marcadores": "uma"}})
        assert out["vies"]["espectro"] == "centro"
        assert out["vies"]["marcadores"] == ["uma"]


# ===========================================================================
# analyze_quick / analyze_full
# ===========================================================================

class TestAnalyzeCalls:
    def test_quick_parses(self):
        resp = '{"tags":["a"],"sentimento":"neutro","clickbait":0.1,"idioma":"pt","resumo":"r"}'
        with patch("app.core.logos_client.chat", return_value=resp):
            out = analyze_quick("t", "b", priority=3)
        assert out["tags"] == ["a"] and out["idioma"] == "pt"

    def test_quick_invalid_twice_returns_none(self):
        with patch("app.core.logos_client.chat", return_value="não é json") as mc:
            assert analyze_quick("t", "b", priority=3) is None
        assert mc.call_count == 2   # tenta 2x

    def test_quick_offline_propagates(self):
        with patch("app.core.logos_client.chat", side_effect=LogosUnavailable("off")):
            with pytest.raises(LogosUnavailable):
                analyze_quick("t", "b", priority=3)

    def test_full_parses(self):
        resp = '{"cinco_ws":{"quem":"X"},"entidades":[{"nome":"Y","tipo":"tema"}],"vies":{"espectro":"centro"}}'
        with patch("app.core.logos_client.chat", return_value=resp):
            out = analyze_full("t", "b", priority=1)
        assert out["cinco_ws"]["quem"] == "X"
        assert out["entidades"][0]["nome"] == "Y"


# ===========================================================================
# Helpers de DB
# ===========================================================================

class TestDbHelpers:
    def test_pending_includes_pending_failed_oldschema(self, db):
        conn, fid, _ = db
        p = _insert(conn, fid, title="P", status="pending", schema_version=ANALYSIS_SCHEMA_VERSION)
        f = _insert(conn, fid, title="F", status="failed", schema_version=ANALYSIS_SCHEMA_VERSION)
        old = _insert(conn, fid, title="Old", status="done", schema_version=ANALYSIS_SCHEMA_VERSION - 1)
        done = _insert(conn, fid, title="Done", status="done", schema_version=ANALYSIS_SCHEMA_VERSION)
        ids = [r[0] for r in get_pending_analysis(conn=conn)]
        assert p in ids and f in ids and old in ids
        assert done not in ids

    def test_pending_newest_first_and_body_fallback(self, db):
        conn, fid, _ = db
        _insert(conn, fid, title="Older", published_at="2026-01-01T00:00:00Z")
        new = _insert(conn, fid, title="Newer", published_at="2026-06-09T00:00:00Z",
                      content_excerpt="trecho")
        out = get_pending_analysis(conn=conn)
        assert out[0][0] == new          # newest first
        assert out[0][2] == "trecho"     # body cai no excerpt

    def test_pending_excludes_running(self, db):
        # regressão: 'running' (schema 0) não pode reaparecer na fila nem ser re-claimed
        conn, fid, _ = db
        run = _insert(conn, fid, status="running", schema_version=0)
        assert run not in [r[0] for r in get_pending_analysis(conn=conn)]
        assert claim_for_analysis(run, conn=conn) is False

    def test_claim_is_atomic(self, db):
        conn, fid, _ = db
        aid = _insert(conn, fid, status="pending")
        assert claim_for_analysis(aid, conn=conn) is True
        assert claim_for_analysis(aid, conn=conn) is False   # já running
        row = conn.execute("SELECT analysis_status FROM articles WHERE id=?", (aid,)).fetchone()
        assert row["analysis_status"] == "running"

    def test_claim_done_current_rejected_oldschema_ok(self, db):
        conn, fid, _ = db
        cur = _insert(conn, fid, status="done", schema_version=ANALYSIS_SCHEMA_VERSION)
        old = _insert(conn, fid, status="done", schema_version=ANALYSIS_SCHEMA_VERSION - 1)
        assert claim_for_analysis(cur, conn=conn) is False
        assert claim_for_analysis(old, conn=conn) is True

    def test_save_quick_sets_fields_and_done(self, db):
        conn, fid, _ = db
        aid = _insert(conn, fid, status="running")
        save_quick_analysis(aid, {"tags": ["a", "b"], "sentimento": "positivo",
                                  "clickbait": 0.3, "resumo": "r", "idioma": "pt"}, conn=conn)
        row = conn.execute("SELECT * FROM articles WHERE id=?", (aid,)).fetchone()
        assert json.loads(row["ai_tags"]) == ["a", "b"]
        assert row["ai_sentiment"] == "positivo"
        assert row["analysis_status"] == "done"
        assert row["analysis_schema_version"] == ANALYSIS_SCHEMA_VERSION

    def test_save_full_sets_json(self, db):
        conn, fid, _ = db
        aid = _insert(conn, fid)
        save_full_analysis(aid, {"cinco_ws": {"quem": "X"}, "entidades": [{"nome": "Y"}],
                                 "vies": {"espectro": "centro"}}, conn=conn)
        row = conn.execute("SELECT ai_five_ws, ai_entities, ai_bias FROM articles WHERE id=?", (aid,)).fetchone()
        assert json.loads(row["ai_five_ws"])["quem"] == "X"
        assert json.loads(row["ai_bias"])["espectro"] == "centro"

    def test_failed_and_revert(self, db):
        conn, fid, _ = db
        aid = _insert(conn, fid, status="running")
        mark_analysis_failed(aid, conn=conn)
        assert conn.execute("SELECT analysis_status FROM articles WHERE id=?", (aid,)).fetchone()[0] == "failed"
        conn.execute("UPDATE articles SET analysis_status='running' WHERE id=?", (aid,))
        conn.commit()
        revert_to_pending(aid, conn=conn)
        assert conn.execute("SELECT analysis_status FROM articles WHERE id=?", (aid,)).fetchone()[0] == "pending"

    def test_get_article_flags(self, db):
        conn, fid, _ = db
        pend = _insert(conn, fid, status="pending")
        quick = _insert(conn, fid, status="done", schema_version=ANALYSIS_SCHEMA_VERSION, ai_tags='["a"]')
        full = _insert(conn, fid, status="done", schema_version=ANALYSIS_SCHEMA_VERSION,
                       ai_tags='["a"]', ai_five_ws='{"quem":"x"}')
        assert get_article_for_analysis(pend, conn=conn)["has_quick"] is False
        assert get_article_for_analysis(quick, conn=conn)["has_quick"] is True
        assert get_article_for_analysis(quick, conn=conn)["has_full"] is False
        assert get_article_for_analysis(full, conn=conn)["has_full"] is True

    def test_get_article_missing_returns_none(self, db):
        conn, _, _ = db
        assert get_article_for_analysis(99999, conn=conn) is None

    def test_ttl_nulls_old_keeps_recent_and_tags(self, db):
        conn, fid, _ = db
        old = _insert(conn, fid, published_at="2025-01-01T00:00:00Z",
                      ai_tags='["keep"]', ai_five_ws='{"quem":"x"}', ai_entities='[{"nome":"y"}]')
        recent = _insert(conn, fid, published_at="2026-06-01T00:00:00Z", ai_five_ws='{"quem":"z"}')
        n = apply_analysis_ttl(conn=conn)
        assert n == 1
        ro = conn.execute("SELECT ai_five_ws, ai_entities, ai_tags FROM articles WHERE id=?", (old,)).fetchone()
        assert ro["ai_five_ws"] is None and ro["ai_entities"] is None
        assert ro["ai_tags"] == '["keep"]'   # tags preservadas
        rr = conn.execute("SELECT ai_five_ws FROM articles WHERE id=?", (recent,)).fetchone()
        assert rr["ai_five_ws"] == '{"quem":"z"}'


# ===========================================================================
# Worker — unidades de trabalho
# ===========================================================================

_QUICK = {"tags": ["a"], "sentimento": "neutro", "clickbait": 0.1, "resumo": "r", "idioma": "pt"}
_FULL = {"cinco_ws": {"quem": "x"}, "entidades": [{"nome": "y", "tipo": "tema"}],
         "vies": {"espectro": "centro", "marcadores": [], "qualidade_apuracao": "media"}}


class TestWorkerUnits:
    def test_preanalyze_success_emits(self, worker, db):
        conn, fid, _ = db
        aid = _insert(conn, fid, status="pending")
        got = []
        worker.quick_analysis_done.connect(got.append)
        with patch.object(aw, "analyze_quick", return_value=dict(_QUICK)):
            assert worker._preanalyze(aid, "t", "b") == 1
        assert got == [aid]
        assert conn.execute("SELECT analysis_status FROM articles WHERE id=?", (aid,)).fetchone()[0] == "done"

    def test_preanalyze_invalid_marks_failed(self, worker, db):
        conn, fid, _ = db
        aid = _insert(conn, fid, status="pending")
        failed = []
        worker.analysis_failed.connect(failed.append)
        with patch.object(aw, "analyze_quick", return_value=None):
            assert worker._preanalyze(aid, "t", "b") == 0
        assert failed == [aid]
        assert conn.execute("SELECT analysis_status FROM articles WHERE id=?", (aid,)).fetchone()[0] == "failed"

    def test_preanalyze_offline_reverts(self, worker, db):
        conn, fid, _ = db
        aid = _insert(conn, fid, status="pending")
        worker._idle_interval_sec = 0   # sem back-off real no teste
        with patch.object(aw, "analyze_quick", side_effect=LogosUnavailable("off")):
            assert worker._preanalyze(aid, "t", "b") == 0
        assert conn.execute("SELECT analysis_status FROM articles WHERE id=?", (aid,)).fetchone()[0] == "pending"

    def test_analyze_opened_runs_both_calls(self, worker, db):
        conn, fid, _ = db
        aid = _insert(conn, fid, status="pending")
        quick, full = [], []
        worker.quick_analysis_done.connect(quick.append)
        worker.full_analysis_done.connect(full.append)
        with patch.object(aw, "analyze_quick", return_value=dict(_QUICK)), \
             patch.object(aw, "analyze_full", return_value=dict(_FULL)), \
             patch.object(aw, "materialize_entity_links", return_value=0):
            assert worker._analyze_opened(aid) == 2
        assert quick == [aid] and full == [aid]

    def test_analyze_opened_only_full_when_quick_done(self, worker, db):
        conn, fid, _ = db
        aid = _insert(conn, fid, status="done", schema_version=ANALYSIS_SCHEMA_VERSION, ai_tags='["a"]')
        with patch.object(aw, "analyze_quick") as mq, \
             patch.object(aw, "analyze_full", return_value=dict(_FULL)) as mf, \
             patch.object(aw, "materialize_entity_links", return_value=0):
            assert worker._analyze_opened(aid) == 1
        mq.assert_not_called()
        mf.assert_called_once()

    def test_analyze_opened_nothing_when_complete(self, worker, db):
        conn, fid, _ = db
        aid = _insert(conn, fid, status="done", schema_version=ANALYSIS_SCHEMA_VERSION,
                      ai_tags='["a"]', ai_five_ws='{"quem":"x"}')
        with patch.object(aw, "analyze_quick") as mq, patch.object(aw, "analyze_full") as mf:
            assert worker._analyze_opened(aid) == 0
        mq.assert_not_called()
        mf.assert_not_called()


class TestWorkerQueue:
    def test_request_and_drain(self, worker):
        worker.request_full_analysis(7)
        worker.request_full_analysis(9)
        assert worker._drain_priority() == [7, 9]
        assert worker._drain_priority() == []

    def test_run_cycle_p1_preempts_batch(self, worker, db):
        conn, fid, _ = db
        opened = _insert(conn, fid, title="Aberto", status="pending")
        _insert(conn, fid, title="Lote", status="pending")
        worker.request_full_analysis(opened)
        order = []
        with patch.object(worker, "_analyze_opened", side_effect=lambda a: order.append(("P1", a)) or 1), \
             patch.object(worker, "_preanalyze", side_effect=lambda a, t, b: order.append(("P3", a)) or 1):
            worker._run_cycle()
        # o artigo aberto (P1) é processado antes de qualquer item do lote P3
        assert order[0] == ("P1", opened)
        assert any(tag == "P3" for tag, _ in order)   # o lote P3 rodou na sequência
