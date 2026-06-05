"""
Testes do BUG-031 / Opção 2 — IA do Mnemosyne roteada pelo LOGOS.

- POTION (model2vec) removido: embedding é SEMPRE bge-m3 via LOGOS (mesmo modelo
  em todas as máquinas → banco sincronizado coerente).
- cardiffnlp removido: valence/arousal autoritativo derivado do vetor Plutchik
  computado pelo LOGOS (`_plutchik_to_va` / `_update_plutchik_bg`); léxico
  determinístico (NRC-VAD/VADER) só como proxy rápido na gravação.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_INDEXER = _ROOT / "core" / "indexer.py"
_PM      = _ROOT / "core" / "personal_memory.py"


@pytest.fixture
def pm_db(tmp_path, monkeypatch):
    import core.personal_memory as pm
    monkeypatch.setattr(pm, "_DB_PATH", tmp_path / "personal_memory.db")
    pm._conn()
    yield pm


# ---------------------------------------------------------------------------
# Derivação Plutchik → valence/arousal (sentimento via LOGOS)
# ---------------------------------------------------------------------------

class TestPlutchikToVA:
    def test_alegria_da_valence_positiva(self):
        from core.personal_memory import _plutchik_to_va
        # joy dominante (índice 0)
        vec = [1.0, 0, 0, 0, 0, 0, 0, 0]
        val, aro = _plutchik_to_va(vec)
        assert val > 0.5, f"joy deveria dar valence positivo, deu {val}"

    def test_tristeza_da_valence_negativa(self):
        from core.personal_memory import _plutchik_to_va
        # sadness dominante (índice 4)
        vec = [0, 0, 0, 0, 1.0, 0, 0, 0]
        val, _aro = _plutchik_to_va(vec)
        assert val < 0, f"sadness deveria dar valence negativo, deu {val}"

    def test_medo_da_arousal_alto(self):
        from core.personal_memory import _plutchik_to_va
        # fear (índice 2) é alta ativação
        val_fear, aro_fear = _plutchik_to_va([0, 0, 1.0, 0, 0, 0, 0, 0])
        # trust (índice 1) é baixa ativação
        _val_trust, aro_trust = _plutchik_to_va([0, 1.0, 0, 0, 0, 0, 0, 0])
        assert aro_fear > aro_trust, "medo deveria ter arousal maior que confiança"

    def test_clamp_e_vazio(self):
        from core.personal_memory import _plutchik_to_va
        assert _plutchik_to_va([]) == (0.0, 0.0)
        assert _plutchik_to_va([0.1] * 8) is not None
        val, aro = _plutchik_to_va([1.0] * 8)
        assert -1.0 <= val <= 1.0 and 0.0 <= aro <= 1.0


class TestPlutchikBgGravaVA:
    def test_update_plutchik_grava_valence_arousal_via_logos(self, pm_db, monkeypatch):
        import core.personal_memory as pm
        # insere uma memória crua (valence/arousal NULL)
        con = pm._conn()
        con.execute("INSERT INTO personal_memory (id, type, content) VALUES (1, 'observation', 'que alegria!')")
        con.commit(); con.close()

        # mocka o LOGOS para classificar como joy dominante
        import ecosystem_client
        def _fake_llm(msgs, **kw):
            return {"message": {"content":
                '{"joy":0.9,"trust":0.1,"fear":0,"surprise":0,"sadness":0,"disgust":0,"anger":0,"anticipation":0}'}}
        monkeypatch.setattr(ecosystem_client, "request_llm", _fake_llm, raising=False)

        pm._update_plutchik_bg(1, "que alegria!", "fake-model", pm._get_db())

        con = pm._conn()
        row = con.execute("SELECT valence, arousal, plutchik FROM personal_memory WHERE id = 1").fetchone()
        con.close()
        assert row is not None
        assert row[0] is not None and row[0] > 0.4, f"valence (joy) deveria ser positivo, é {row[0]}"
        assert row[2] is not None, "vetor plutchik deveria estar salvo"
        assert json.loads(row[2])[0] > 0.5, "joy deveria dominar o vetor"


# ---------------------------------------------------------------------------
# Remoção da IA fora do LOGOS (inspeção de source)
# ---------------------------------------------------------------------------

class TestPotionRemovido:
    def test_indexer_sem_model2vec(self):
        src = _INDEXER.read_text(encoding="utf-8")
        assert "_POTION_MODEL_NAME" not in src
        assert "_Model2VecEmbeddings" not in src
        assert "_embed_batch_model2vec" not in src
        assert "from model2vec import" not in src

    def test_get_embeddings_sempre_inference(self):
        # _get_embeddings não ramifica mais para model2vec — sempre LOGOS.
        src = _INDEXER.read_text(encoding="utf-8")
        assert "return _InferenceEmbeddings(config.embed_model)" in src
        # não deve haver branch de POTION em _get_embeddings
        assert "_Model2VecEmbeddings()" not in src


class TestCardiffnlpRemovido:
    def test_personal_memory_sem_cardiffnlp(self):
        src = _PM.read_text(encoding="utf-8")
        assert "cardiffnlp" not in src
        assert "_xlmr_pipe" not in src
        assert "xlm_roberta" not in src

    def test_sentimento_autoritativo_via_plutchik(self):
        src = _PM.read_text(encoding="utf-8")
        # o update do plutchik grava valence/arousal derivados
        assert "_plutchik_to_va" in src
        assert "SET plutchik = ?, valence = ?, arousal = ?" in src
