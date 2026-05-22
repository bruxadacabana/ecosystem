"""
Testes de integração para Mnemosyne/core/affective_state.py — camada de DB.

Cobre:
  - _conn() / _ensure_schema: migrations aplicadas em DB antigo (síncrono)
  - record_appraisal: escrita real em SQLite temporário
  - get_current_state: leitura e cálculo a partir de dados reais
  - record_curiosity_event / get_epistemic_curiosity

Idêntico em cobertura ao AKASHA/tests/test_affective_state_db.py,
mas usando a versão síncrona do módulo (sqlite3 em vez de aiosqlite).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixture: substitui _get_db() para usar arquivo temporário
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "personal_memory_test.db"
    import core.affective_state as _m
    original = _m._get_db
    _m._get_db = lambda: path
    yield path
    _m._get_db = original
    _m._mood_cache    = {"valence": 0.0, "arousal": 0.0}
    _m._mood_cache_at = 0.0


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

class TestMigrations:
    def _create_old_db(self, path: Path) -> None:
        con = sqlite3.connect(path)
        con.execute("""
            CREATE TABLE affective_state (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT    NOT NULL DEFAULT (datetime('now')),
                event_type TEXT    NOT NULL,
                valence    REAL    NOT NULL,
                arousal    REAL    NOT NULL
            )
        """)
        con.commit()
        con.close()

    def _column_exists(self, path: Path, column: str) -> bool:
        con = sqlite3.connect(path)
        cols = [row[1] for row in con.execute("PRAGMA table_info(affective_state)")]
        con.close()
        return column in cols

    def test_migration_adds_decay_half_life_hours(self, db_path):
        self._create_old_db(db_path)
        assert not self._column_exists(db_path, "decay_half_life_hours")

        from core.affective_state import _conn
        con = _conn()
        con.close()

        assert self._column_exists(db_path, "decay_half_life_hours")

    def test_migration_adds_curiosity_delta(self, db_path):
        self._create_old_db(db_path)
        assert not self._column_exists(db_path, "curiosity_delta")

        from core.affective_state import _conn
        con = _conn()
        con.close()

        assert self._column_exists(db_path, "curiosity_delta")

    def test_migration_idempotent(self, db_path):
        from core.affective_state import _conn
        con = _conn(); con.close()
        con = _conn(); con.close()  # segunda chamada não deve lançar


# ---------------------------------------------------------------------------
# record_appraisal → get_current_state
# ---------------------------------------------------------------------------

class TestRecordAndRead:
    def test_record_appraisal_persists_to_db(self, db_path):
        from core.affective_state import record_appraisal
        record_appraisal("doc_indexed", 0.8, 0.9, 0.7, 0.6)

        con = sqlite3.connect(db_path)
        count = con.execute("SELECT COUNT(*) FROM affective_state").fetchone()[0]
        con.close()
        assert count >= 1

    def test_get_current_state_baseline_on_empty_db(self, db_path):
        from core.affective_state import get_current_state, _BASELINE
        state = get_current_state()
        assert state["valence"]      == _BASELINE["valence"]
        assert state["sample_count"] == 0

    def test_get_current_state_after_appraisal(self, db_path):
        from core.affective_state import record_appraisal, get_current_state
        record_appraisal("doc_indexed", 0.2, 0.9, 0.8, 0.9)
        state = get_current_state()
        assert state["sample_count"] > 0
        assert -1.0 <= state["valence"] <= 1.0
        assert  0.0 <= state["arousal"] <= 1.0

    def test_state_valence_positive_for_high_pleasantness(self, db_path):
        from core.affective_state import record_appraisal, get_current_state
        record_appraisal("user_query", 0.3, 1.0, 0.5, 0.8)
        state = get_current_state()
        assert state["valence"] > 0

    def test_half_life_stored_for_event_types(self, db_path):
        from core.affective_state import record_appraisal
        record_appraisal("user_query", 0.5, 0.5, 0.5, 0.5)
        con = sqlite3.connect(db_path)
        rows = con.execute(
            "SELECT decay_half_life_hours FROM affective_state WHERE event_type='user_query'"
        ).fetchall()
        con.close()
        assert rows, "deve existir linha com event_type='user_query'"
        hl = rows[0][0]
        assert hl == 3.0, f"user_query deve ter half_life=3.0h, obteve {hl}"


# ---------------------------------------------------------------------------
# Curiosidade epistêmica
# ---------------------------------------------------------------------------

class TestCuriosity:
    def test_curiosity_zero_on_empty_db(self, db_path):
        from core.affective_state import get_epistemic_curiosity
        assert get_epistemic_curiosity() == 0.0

    def test_positive_delta_increases_curiosity(self, db_path):
        from core.affective_state import record_curiosity_event, get_epistemic_curiosity
        record_curiosity_event(0.4)
        assert get_epistemic_curiosity() > 0.0

    def test_curiosity_clamped_to_zero_one(self, db_path):
        from core.affective_state import record_curiosity_event, get_epistemic_curiosity
        record_curiosity_event(99.0)
        c = get_epistemic_curiosity()
        assert 0.0 <= c <= 1.0

    def test_high_novelty_appraisal_triggers_curiosity(self, db_path):
        from core.affective_state import record_appraisal, get_epistemic_curiosity
        record_appraisal("doc_indexed", 0.9, 0.5, 0.5, 0.8)
        assert get_epistemic_curiosity() > 0.0
