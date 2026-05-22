"""
Testes de integração para AKASHA/services/affective_state.py — camada de DB.

Cobre:
  - _ensure_schema: migrations ALTER TABLE ADD COLUMN aplicadas em DB antigo
  - record_appraisal: escrita real em SQLite temporário
  - get_current_state: leitura e cálculo a partir de dados reais
  - record_curiosity_event / get_epistemic_curiosity: acumulação e decaimento

Usa banco SQLite em arquivo temporário (tmp_path do pytest) — sem mock,
sem patch de caminho — para garantir que o código real de DB funciona.
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixture: substitui _get_db() para usar arquivo temporário
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_path(tmp_path):
    """Retorna um caminho de DB temporário e faz patch de _get_db() no módulo."""
    path = tmp_path / "personal_memory_test.db"
    import services.affective_state as _m
    original = _m._get_db
    _m._get_db = lambda: path
    yield path
    _m._get_db = original
    # Limpa cache de humor entre testes
    _m._mood_cache    = {"valence": 0.0, "arousal": 0.0}
    _m._mood_cache_at = 0.0


def run(coro):
    """Executa corrotina em event loop de teste."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

class TestMigrations:
    """_ensure_schema() deve aplicar migrations em DB antigos sem as colunas."""

    def _create_old_db(self, path: Path) -> None:
        """Cria DB com schema antigo — sem decay_half_life_hours nem curiosity_delta."""
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

        import services.affective_state as _m
        import aiosqlite
        async def _run():
            async with aiosqlite.connect(db_path) as conn:
                await _m._ensure_schema(conn)
        run(_run())

        assert self._column_exists(db_path, "decay_half_life_hours"), \
            "migration deve adicionar coluna decay_half_life_hours"

    def test_migration_adds_curiosity_delta(self, db_path):
        self._create_old_db(db_path)
        assert not self._column_exists(db_path, "curiosity_delta")

        import services.affective_state as _m
        import aiosqlite
        async def _run():
            async with aiosqlite.connect(db_path) as conn:
                await _m._ensure_schema(conn)
        run(_run())

        assert self._column_exists(db_path, "curiosity_delta"), \
            "migration deve adicionar coluna curiosity_delta"

    def test_migration_idempotent_on_fresh_db(self, db_path):
        """_ensure_schema() chamada duas vezes em DB novo não deve lançar."""
        import services.affective_state as _m
        import aiosqlite
        async def _run():
            async with aiosqlite.connect(db_path) as conn:
                await _m._ensure_schema(conn)
            async with aiosqlite.connect(db_path) as conn:
                await _m._ensure_schema(conn)
        run(_run())  # não deve levantar


# ---------------------------------------------------------------------------
# record_appraisal → get_current_state
# ---------------------------------------------------------------------------

class TestRecordAndRead:
    def test_record_appraisal_persists_to_db(self, db_path):
        from services.affective_state import record_appraisal
        import aiosqlite
        run(record_appraisal("doc_indexed", 0.8, 0.9, 0.7, 0.6))

        async def _count():
            async with aiosqlite.connect(db_path) as conn:
                cur = await conn.execute("SELECT COUNT(*) FROM affective_state")
                row = await cur.fetchone()
                return row[0]

        count = run(_count())
        assert count == 2, f"esperava 2 linhas (appraisal + curiosidade), obteve {count}"

    def test_get_current_state_baseline_on_empty_db(self, db_path):
        from services.affective_state import get_current_state, _BASELINE
        state = run(get_current_state())
        assert state["valence"]  == _BASELINE["valence"]
        assert state["arousal"]  == _BASELINE["arousal"]
        assert state["sample_count"] == 0

    def test_get_current_state_after_appraisal(self, db_path):
        from services.affective_state import record_appraisal, get_current_state
        run(record_appraisal("doc_indexed", 0.2, 0.9, 0.8, 0.9))
        state = run(get_current_state())
        assert state["sample_count"] > 0, "sample_count deve ser > 0 após appraisal"
        assert -1.0 <= state["valence"] <= 1.0
        assert  0.0 <= state["arousal"] <= 1.0

    def test_state_valence_sign_matches_pleasantness(self, db_path):
        from services.affective_state import record_appraisal, get_current_state
        # pleasantness muito alta → valência positiva
        run(record_appraisal("user_query", 0.3, 1.0, 0.5, 0.8))
        state = run(get_current_state())
        assert state["valence"] > 0, \
            f"pleasantness=1.0 deve produzir valência positiva, obteve {state['valence']}"

    def test_event_type_stored_correctly(self, db_path):
        from services.affective_state import record_appraisal
        import aiosqlite
        run(record_appraisal("user_query", 0.5, 0.5, 0.5, 0.5))

        async def _get_types():
            async with aiosqlite.connect(db_path) as conn:
                cur = await conn.execute(
                    "SELECT event_type FROM affective_state ORDER BY id"
                )
                return [r[0] for r in await cur.fetchall()]

        types = run(_get_types())
        assert "user_query" in types


# ---------------------------------------------------------------------------
# record_curiosity_event / get_epistemic_curiosity
# ---------------------------------------------------------------------------

class TestCuriosity:
    def test_curiosity_zero_on_empty_db(self, db_path):
        from services.affective_state import get_epistemic_curiosity
        assert run(get_epistemic_curiosity()) == 0.0

    def test_positive_delta_increases_curiosity(self, db_path):
        from services.affective_state import record_curiosity_event, get_epistemic_curiosity
        run(record_curiosity_event(0.4))
        curiosity = run(get_epistemic_curiosity())
        assert curiosity > 0.0, f"delta positivo deve elevar curiosidade, obteve {curiosity}"

    def test_curiosity_clamped_to_zero_one(self, db_path):
        from services.affective_state import record_curiosity_event, get_epistemic_curiosity
        run(record_curiosity_event(10.0))  # delta absurdo
        curiosity = run(get_epistemic_curiosity())
        assert 0.0 <= curiosity <= 1.0

    def test_high_novelty_appraisal_triggers_curiosity(self, db_path):
        from services.affective_state import record_appraisal, get_epistemic_curiosity
        # novelty > 0.7 e coping > 0.5 → deve disparar evento de curiosidade
        run(record_appraisal("doc_indexed", 0.9, 0.5, 0.5, 0.8))
        curiosity = run(get_epistemic_curiosity())
        assert curiosity > 0.0, \
            "novelty=0.9 + coping=0.8 devem disparar curiosidade epistêmica"
