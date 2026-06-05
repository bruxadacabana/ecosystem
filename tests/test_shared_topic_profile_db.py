"""
Testes de integração para shared_topic_profile.py — camada de DB.

Cobre:
  - _ensure_db: criação de schema em DB novo
  - update_scores: escrita real, filtragem de stopwords, contagem por source
  - get_top_topics: leitura e ordenação por score
  - apply_seed_topics: inserção sem sobrescrever scores existentes
  - decay_scores: decaimento de scores antigos
  - Filtragem de stopwords registrada via log

Recuperação de corrupção (BUG-011):
  - _ensure_db detecta SQLITE_CORRUPT e chama _recreate_from_backup
  - _recreate_from_backup recria schema e restaura dados do JSON
  - update_scores continua funcionando após recuperação transparente
  - DatabaseError não-corrupção não é engolida
  - Backup JSON ausente resulta em banco vazio (sem crash)
  - WAL/SHM são removidos junto com o banco corrompido

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


# ---------------------------------------------------------------------------
# Recuperação de corrupção — BUG-011
# ---------------------------------------------------------------------------

class TestCorruptionRecovery:
    def _corrupt_db(self, path: Path) -> None:
        """Sobrescreve os primeiros bytes do arquivo para simular corrupção."""
        with open(path, "r+b") as f:
            f.write(b"\x00" * 64)

    def test_ensure_db_recovers_from_corrupt_db_without_backup(self, db_path):
        """Banco corrompido sem backup JSON → _ensure_db recria schema vazio sem crash."""
        import shared_topic_profile as stp

        # Criar DB válido primeiro
        stp._ensure_db(db_path)
        assert db_path.exists()

        # Corromper
        self._corrupt_db(db_path)

        # _ensure_db deve detectar e recriar (sem backup disponível — fixture já tem backup=None)
        stp._ensure_db(db_path)

        # Banco deve existir e ter schema correto
        con = sqlite3.connect(str(db_path))
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        con.close()
        assert "topic_interest_profile" in tables

    def test_ensure_db_restores_data_from_backup_json(self, tmp_path):
        """Banco corrompido COM backup JSON → dados restaurados após _ensure_db."""
        import json
        import shared_topic_profile as stp

        db = tmp_path / "shared_topic_profile.db"
        bk = tmp_path / "shared_topic_profile.json"

        # Criar backup JSON com dados
        backup_data = [
            {"topic": "linguística", "score": 5.0, "akasha_count": 3,
             "mnemosyne_count": 1, "kosmos_count": 0, "last_updated": "2026-05-27 00:00:00"},
            {"topic": "semiótica", "score": 2.5, "akasha_count": 1,
             "mnemosyne_count": 0, "kosmos_count": 1, "last_updated": "2026-05-27 00:00:00"},
        ]
        bk.write_text(json.dumps(backup_data), encoding="utf-8")

        orig_profile = stp._profile_path
        orig_backup  = stp._backup_path
        stp._profile_path = lambda: db
        stp._backup_path  = lambda: bk
        try:
            # Criar DB corrompido
            db.write_bytes(b"\x00" * 128)

            # _ensure_db deve detectar e restaurar
            stp._ensure_db(db)

            con = sqlite3.connect(str(db))
            rows = {r[0]: r[1] for r in con.execute(
                "SELECT topic, score FROM topic_interest_profile"
            ).fetchall()}
            con.close()

            assert rows.get("linguística") == pytest.approx(5.0)
            assert rows.get("semiótica") == pytest.approx(2.5)
        finally:
            stp._profile_path = orig_profile
            stp._backup_path  = orig_backup

    def test_update_scores_transparent_recovery(self, tmp_path):
        """update_scores funciona normalmente após recuperação transparente de corrupção."""
        import json
        import shared_topic_profile as stp

        db = tmp_path / "shared_topic_profile.db"
        bk = tmp_path / "shared_topic_profile.json"
        bk.write_text(json.dumps([]), encoding="utf-8")  # backup vazio

        orig_profile = stp._profile_path
        orig_backup  = stp._backup_path
        stp._profile_path = lambda: db
        stp._backup_path  = lambda: bk
        try:
            # Criar DB corrompido
            db.write_bytes(b"\x00" * 128)

            # update_scores deve recuperar e escrever normalmente
            stp.update_scores(["pragmática"], 3.0, "mnemosyne")

            con = sqlite3.connect(str(db))
            row = con.execute(
                "SELECT score FROM topic_interest_profile WHERE topic='pragmática'"
            ).fetchone()
            con.close()
            assert row is not None
            assert row[0] == pytest.approx(3.0)
        finally:
            stp._profile_path = orig_profile
            stp._backup_path  = orig_backup

    def test_recreate_removes_wal_and_shm(self, db_path):
        """_recreate_from_backup apaga arquivos WAL e SHM do banco corrompido.

        SQLite pode recriar um WAL vazio ao abrir o novo banco em modo WAL — o que
        importa é que o conteúdo ANTIGO dos sidecars foi removido antes da recriação.
        Verificamos isso checando que o conteúdo antigo não persiste.
        """
        import shared_topic_profile as stp

        # Criar DB e sidecars simulados com conteúdo identificável
        db_path.write_bytes(b"\x00" * 64)
        wal = db_path.with_name(db_path.name + "-wal")
        shm = db_path.with_name(db_path.name + "-shm")
        wal.write_bytes(b"FAKE_OLD_WAL_CONTENT")
        shm.write_bytes(b"FAKE_OLD_SHM_CONTENT")

        stp._recreate_from_backup(db_path)

        # O novo DB deve existir e ter schema válido
        assert db_path.exists(), "Novo banco deve existir após recriação"
        con = sqlite3.connect(str(db_path))
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        con.close()
        assert "topic_interest_profile" in tables

        # Conteúdo antigo dos sidecars deve ter sido removido
        # (SQLite pode recriar o WAL vazio no modo WAL — mas o conteúdo antigo sumiu)
        if wal.exists():
            assert wal.read_bytes() != b"FAKE_OLD_WAL_CONTENT", \
                "conteúdo do WAL antigo deve ter sido deletado"
        if shm.exists():
            assert shm.read_bytes() != b"FAKE_OLD_SHM_CONTENT", \
                "conteúdo do SHM antigo deve ter sido deletado"

    def test_ensure_db_does_not_swallow_non_corrupt_errors(self, db_path):
        """DatabaseError que NÃO seja corrupção deve propagar normalmente."""
        import shared_topic_profile as stp
        import unittest.mock as mock

        with mock.patch.object(
            stp.sqlite3, "connect",
            side_effect=sqlite3.DatabaseError("disk I/O error")
        ):
            with pytest.raises(sqlite3.DatabaseError, match="disk I/O error"):
                stp._ensure_db(db_path)

    def test_recreate_backup_json_malformed_does_not_crash(self, tmp_path):
        """JSON de backup malformado → _recreate_from_backup não crasha, banco fica vazio."""
        import shared_topic_profile as stp

        db = tmp_path / "shared_topic_profile.db"
        bk = tmp_path / "shared_topic_profile.json"
        bk.write_text("ISTO NAO E JSON VALIDO {{{", encoding="utf-8")

        orig_profile = stp._profile_path
        orig_backup  = stp._backup_path
        stp._profile_path = lambda: db
        stp._backup_path  = lambda: bk
        try:
            stp._recreate_from_backup(db)

            con = sqlite3.connect(str(db))
            count = con.execute(
                "SELECT COUNT(*) FROM topic_interest_profile"
            ).fetchone()[0]
            con.close()
            assert count == 0
        finally:
            stp._profile_path = orig_profile
            stp._backup_path  = orig_backup


# ---------------------------------------------------------------------------
# Filtro de termos-lixo no caminho de escrita compartilhado
# ---------------------------------------------------------------------------

class TestMeaningfulTopicFilter:
    """Termos-lixo (verbos, gerúndios, abstrações de prosa de LLM) não podem
    entrar no perfil de interesses — filtro aplicado por todos os apps."""

    # Exatamente os exemplos relatados pela usuária na aba Interesses do HUB.
    LIXO = ["encontrei", "começando", "conexão", "interessante", "temas", "incluindo"]
    # Interesses reais que NÃO podem ser descartados (incl. armadilhas morfológicas).
    REAIS = [
        "crochê", "sociolinguística", "python", "neuroplasticidade", "marketing",
        "aprendizado", "comando", "bateria", "livraria", "história", "mercado",
    ]

    @pytest.mark.parametrize("termo", LIXO)
    def test_lixo_e_descartado(self, termo):
        from shared_topic_profile import _is_meaningful_topic
        assert _is_meaningful_topic(termo) is False, f"'{termo}' deveria ser filtrado"

    @pytest.mark.parametrize("termo", REAIS)
    def test_interesse_real_sobrevive(self, termo):
        from shared_topic_profile import _is_meaningful_topic
        assert _is_meaningful_topic(termo) is True, f"'{termo}' NÃO deveria ser filtrado"

    def test_gerundio_curto_nao_confunde(self):
        # "lindo" (5 chars) e "findo" (5) ficam abaixo do limiar de 6 — preservados.
        from shared_topic_profile import _is_meaningful_topic
        assert _is_meaningful_topic("lindo") is True

    def test_participio_nao_e_filtrado(self):
        # -ado/-ido são particípios usados por muitos substantivos — preservar.
        from shared_topic_profile import _is_meaningful_topic
        for t in ("resultado", "significado", "conteúdo", "partido", "sentido"):
            assert _is_meaningful_topic(t) is True, f"'{t}' não deveria ser filtrado"

    def test_filtro_aplicado_na_escrita(self, db_path):
        # Integração: update_scores só grava os termos reais, descartando o lixo.
        from shared_topic_profile import update_scores
        update_scores(self.LIXO + ["sociolinguística"], 1.0, "akasha")

        con = sqlite3.connect(db_path)
        topics = {r[0] for r in con.execute("SELECT topic FROM topic_interest_profile")}
        con.close()
        assert topics == {"sociolinguística"}, (
            f"só 'sociolinguística' deveria ter sido gravado, obteve {topics}"
        )


# ---------------------------------------------------------------------------
# Consolidação cross-idioma (unificação por embedding)
# ---------------------------------------------------------------------------

def _fake_embed(texts):
    """Embeddings determinísticos: as duas formas de 'ML' iguais; python ortogonal."""
    vecs = []
    for t in texts:
        if t in ("machine learning", "aprendizado de máquina"):
            vecs.append([1.0, 0.0, 0.0])
        elif t == "python":
            vecs.append([0.0, 1.0, 0.0])
        else:
            vecs.append([0.0, 0.0, 1.0])
    return vecs


class TestConsolidateInterests:
    def _seed(self):
        from shared_topic_profile import update_scores
        update_scores(["machine learning"], 2.0, "akasha")
        update_scores(["aprendizado de máquina"], 1.0, "mnemosyne")
        update_scores(["python"], 3.0, "akasha")

    def test_mescla_equivalentes_e_soma_score(self, db_path):
        from shared_topic_profile import consolidate_interests
        self._seed()
        removed = consolidate_interests(embed_fn=_fake_embed, sim_threshold=0.88)
        assert removed == 1, f"deveria remover 1 duplicado, removeu {removed}"

        con = sqlite3.connect(db_path)
        rows = dict(con.execute("SELECT topic, score FROM topic_interest_profile"))
        con.close()
        # python intacto; as duas formas de ML viraram uma só com score somado (3.0)
        assert "python" in rows and rows["python"] == pytest.approx(3.0)
        ml = [t for t in rows if t != "python"]
        assert len(ml) == 1, f"as duas formas de ML deveriam virar uma, sobraram {ml}"
        assert rows[ml[0]] == pytest.approx(3.0), "score do grupo = soma (2.0 + 1.0)"

    def test_rotulo_default_e_maior_score(self, db_path):
        from shared_topic_profile import consolidate_interests
        self._seed()
        # sem detector de idioma → mantém o de maior score ('machine learning', 2.0)
        consolidate_interests(embed_fn=_fake_embed, sim_threshold=0.88, lang_detect_fn=lambda t: "")
        con = sqlite3.connect(db_path)
        topics = {r[0] for r in con.execute("SELECT topic FROM topic_interest_profile")}
        con.close()
        assert "machine learning" in topics

    def test_rotulo_prefere_portugues_quando_detectado(self, db_path):
        from shared_topic_profile import consolidate_interests
        self._seed()
        # detector marca a forma PT → vira o rótulo, mesmo com score menor
        lang = lambda t: "pt" if t == "aprendizado de máquina" else "en"
        consolidate_interests(embed_fn=_fake_embed, sim_threshold=0.88, lang_detect_fn=lang)
        con = sqlite3.connect(db_path)
        topics = {r[0] for r in con.execute("SELECT topic FROM topic_interest_profile")}
        con.close()
        assert "aprendizado de máquina" in topics
        assert "machine learning" not in topics

    def test_sem_embed_fn_nao_faz_nada(self, db_path):
        from shared_topic_profile import consolidate_interests
        self._seed()
        # embed_fn que sinaliza indisponibilidade não deve mesclar nada
        removed = consolidate_interests(embed_fn=lambda texts: [], sim_threshold=0.88)
        assert removed == 0

    def test_threshold_alto_nao_mescla_distintos(self, db_path):
        from shared_topic_profile import consolidate_interests, update_scores
        update_scores(["python"], 1.0, "akasha")
        update_scores(["rust"], 1.0, "akasha")  # ortogonal a python no _fake_embed
        removed = consolidate_interests(embed_fn=_fake_embed, sim_threshold=0.88)
        assert removed == 0, "tópicos distintos não podem ser mesclados"


class TestMergeTopicsManual:
    def test_merge_manual_soma_e_apaga(self, db_path):
        from shared_topic_profile import update_scores, merge_topics
        update_scores(["python"], 3.0, "akasha")
        update_scores(["pythonista"], 1.0, "akasha")
        update_scores(["python3"], 1.0, "mnemosyne")

        removed = merge_topics("python", ["pythonista", "python3"])
        assert removed == 2

        con = sqlite3.connect(db_path)
        rows = dict(con.execute("SELECT topic, score FROM topic_interest_profile"))
        con.close()
        assert set(rows) == {"python"}
        assert rows["python"] == pytest.approx(5.0)

    def test_merge_ignora_self(self, db_path):
        from shared_topic_profile import update_scores, merge_topics
        update_scores(["python"], 3.0, "akasha")
        # remover == keep → nada a fazer
        assert merge_topics("python", ["python"]) == 0
