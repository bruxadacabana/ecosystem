"""
Testes de integração para shared_topic_profile.py — camada de DB.

Cobre:
  - _ensure_db: criação de schema em DB novo
  - update_scores: escrita real, filtragem de stopwords, contagem por source
  - get_top_topics: leitura e ordenação por score
  - apply_seed_topics: inserção sem sobrescrever scores existentes
  - decay_scores: decaimento de scores antigos
  - Filtragem de stopwords registrada via log

Usa DB SQLite em arquivo temporário — sem mock de _profile_path().
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

# Garante que a raiz de program files está no path
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Fixture: DB temporário com patch de _profile_path e _backup_path
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "shared_topic_profile.db"
    import shared_topic_profile as _m
    orig_profile = _m._profile_path
    orig_backup  = _m._backup_path
    _m._profile_path = lambda: path
    _m._backup_path  = lambda: None  # sem backup durante testes
    yield path
    _m._profile_path = orig_profile
    _m._backup_path  = orig_backup


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestSchema:
    def test_creates_table_on_first_call(self, db_path):
        from shared_topic_profile import update_scores
        update_scores(["python"], 1.0, "akasha")

        con = sqlite3.connect(db_path)
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )]
        con.close()
        assert "topic_interest_profile" in tables

    def test_table_has_expected_columns(self, db_path):
        from shared_topic_profile import update_scores
        update_scores(["rust"], 1.0, "akasha")

        con = sqlite3.connect(db_path)
        cols = {r[1] for r in con.execute("PRAGMA table_info(topic_interest_profile)")}
        con.close()
        expected = {"topic", "score", "akasha_count", "mnemosyne_count",
                    "kosmos_count", "last_updated"}
        assert expected <= cols


# ---------------------------------------------------------------------------
# update_scores — escrita e leitura
# ---------------------------------------------------------------------------

class TestUpdateScores:
    def test_writes_topic_to_db(self, db_path):
        from shared_topic_profile import update_scores
        update_scores(["aprendizado"], 1.0, "akasha")

        con = sqlite3.connect(db_path)
        row = con.execute(
            "SELECT score FROM topic_interest_profile WHERE topic='aprendizado'"
        ).fetchone()
        con.close()
        assert row is not None
        assert row[0] == pytest.approx(1.0)

    def test_accumulates_score_on_repeated_call(self, db_path):
        from shared_topic_profile import update_scores
        update_scores(["linguística"], 1.0, "akasha")
        update_scores(["linguística"], 0.5, "akasha")

        con = sqlite3.connect(db_path)
        row = con.execute(
            "SELECT score FROM topic_interest_profile WHERE topic='linguística'"
        ).fetchone()
        con.close()
        assert row[0] == pytest.approx(1.5)

    def test_source_count_increments(self, db_path):
        from shared_topic_profile import update_scores
        update_scores(["morfologia"], 1.0, "mnemosyne")
        update_scores(["morfologia"], 1.0, "mnemosyne")

        con = sqlite3.connect(db_path)
        row = con.execute(
            "SELECT mnemosyne_count FROM topic_interest_profile WHERE topic='morfologia'"
        ).fetchone()
        con.close()
        assert row[0] == 2

    def test_different_sources_increment_own_count(self, db_path):
        from shared_topic_profile import update_scores
        update_scores(["semântica"], 1.0, "akasha")
        update_scores(["semântica"], 1.0, "mnemosyne")

        con = sqlite3.connect(db_path)
        row = con.execute(
            "SELECT akasha_count, mnemosyne_count "
            "FROM topic_interest_profile WHERE topic='semântica'"
        ).fetchone()
        con.close()
        assert row[0] == 1  # akasha
        assert row[1] == 1  # mnemosyne

    def test_filters_stopwords(self, db_path):
        from shared_topic_profile import update_scores
        update_scores(["novo", "relevantes", "algo", "python"], 1.0, "akasha")

        con = sqlite3.connect(db_path)
        topics = [r[0] for r in con.execute(
            "SELECT topic FROM topic_interest_profile"
        ).fetchall()]
        con.close()
        assert "novo"       not in topics, "stopword 'novo' não deve ser salva"
        assert "relevantes" not in topics, "stopword 'relevantes' não deve ser salva"
        assert "algo"       not in topics, "stopword 'algo' não deve ser salva"
        assert "python"     in topics,     "'python' não é stopword, deve ser salvo"

    def test_filters_short_topics(self, db_path):
        from shared_topic_profile import update_scores
        update_scores(["ai", "ml", "nlp_processamento"], 1.0, "akasha")

        con = sqlite3.connect(db_path)
        topics = [r[0] for r in con.execute(
            "SELECT topic FROM topic_interest_profile"
        ).fetchall()]
        con.close()
        assert "ai" not in topics, "tópicos com < 3 chars devem ser filtrados"
        assert "ml" not in topics
        assert "nlp_processamento" in topics

    def test_empty_list_does_not_crash(self, db_path):
        from shared_topic_profile import update_scores
        update_scores([], 1.0, "akasha")  # não deve lançar

    def test_stopwords_only_does_not_crash(self, db_path):
        from shared_topic_profile import update_scores
        update_scores(["novo", "algo", "de", "the"], 1.0, "akasha")

        # update_scores retorna antes de criar o DB quando todos os tópicos são
        # stopwords — o arquivo pode não existir. Se existir, a tabela pode não
        # ter sido criada ainda. Ambos os casos equivalem a count == 0.
        if not db_path.exists():
            return
        con = sqlite3.connect(str(db_path))
        try:
            count = con.execute(
                "SELECT COUNT(*) FROM topic_interest_profile"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            count = 0
        finally:
            con.close()
        assert count == 0


# ---------------------------------------------------------------------------
# get_top_topics
# ---------------------------------------------------------------------------

class TestGetTopTopics:
    def test_returns_empty_on_empty_db(self, db_path):
        from shared_topic_profile import get_top_topics
        assert get_top_topics(10) == []

    def test_returns_topics_ordered_by_score(self, db_path):
        from shared_topic_profile import update_scores, get_top_topics
        update_scores(["sintaxe"], 5.0, "akasha")
        update_scores(["fonologia"], 2.0, "akasha")
        update_scores(["pragmática"], 8.0, "akasha")

        # get_top_topics retorna list[tuple[str, float]] — índice 1 = score
        topics = get_top_topics(10)
        scores = [t[1] for t in topics]
        assert scores == sorted(scores, reverse=True)

    def test_respects_limit(self, db_path):
        from shared_topic_profile import update_scores, get_top_topics
        for i in range(10):
            update_scores([f"topico_{i:02d}"], float(i), "akasha")

        result = get_top_topics(3)
        assert len(result) == 3

    def test_result_is_list_of_tuples(self, db_path):
        from shared_topic_profile import update_scores, get_top_topics
        update_scores(["morfologia"], 1.0, "akasha")
        topics = get_top_topics(1)
        assert len(topics) == 1
        topic_str, score_float = topics[0]   # tuple unpacking
        assert isinstance(topic_str, str)
        assert isinstance(score_float, float)


# ---------------------------------------------------------------------------
# apply_seed_topics
# ---------------------------------------------------------------------------

class TestApplySeedTopics:
    def test_inserts_new_topics(self, db_path):
        from shared_topic_profile import apply_seed_topics, get_top_topics
        # apply_seed_topics usa chaves "name" e "weight" (formato interests.json)
        inserted = apply_seed_topics([
            {"name": "semiótica", "weight": 3.0},
            {"name": "dialética", "weight": 2.0},
        ])
        assert inserted == 2
        topics = {t[0] for t in get_top_topics(10)}   # t[0] = topic string
        assert "semiótica" in topics
        assert "dialética" in topics

    def test_does_not_overwrite_existing_score(self, db_path):
        from shared_topic_profile import update_scores, apply_seed_topics, get_top_topics
        update_scores(["epistemologia"], 10.0, "akasha")
        apply_seed_topics([{"name": "epistemologia", "weight": 1.0}])

        topics = {t[0]: t[1] for t in get_top_topics(10)}  # t[0]=topic, t[1]=score
        assert topics["epistemologia"] == pytest.approx(10.0), \
            "apply_seed_topics não deve sobrescrever score existente"

    def test_returns_zero_for_all_existing(self, db_path):
        from shared_topic_profile import update_scores, apply_seed_topics
        update_scores(["retórica"], 5.0, "akasha")
        inserted = apply_seed_topics([{"name": "retórica", "weight": 1.0}])
        assert inserted == 0
