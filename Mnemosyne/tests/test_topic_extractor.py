"""
Testes unitários para core/topic_extractor.py.

Cobre:
  - _run_small: pipeline c-TF-IDF sobre corpus pequeno
  - _extract_keywords: keywords por documento via TF-IDF
  - save_topics / load_topics: roundtrip em disco (tmp dir)
  - extract_topics: via mock do ChromaDB (_collection.get)

Não requer ChromaDB real nem modelo de embedding instalado — todo acesso
externo é mockado com pytest-mock ou unittest.mock.
"""
from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Corpus sintético reutilizável
# ---------------------------------------------------------------------------

CORPUS_PT = [
    "linguística computacional processa linguagem natural com algoritmos",
    "morfologia estuda a estrutura interna das palavras",
    "sintaxe descreve as regras de combinação de palavras em frases",
    "semântica investiga o significado das palavras e sentenças",
    "fonologia analisa os sons da língua e seus padrões",
    "pragmática estuda o uso da linguagem em contexto comunicativo",
    "sociolinguística examina a variação da língua na sociedade",
    "psicolinguística investiga como o cérebro processa linguagem",
    "tradução automática usa redes neurais para converter textos entre idiomas",
    "reconhecimento de voz transcreve fala em texto usando aprendizado de máquina",
]


# ---------------------------------------------------------------------------
# _run_small
# ---------------------------------------------------------------------------

class TestRunSmall:
    def test_returns_one_topic(self):
        from core.topic_extractor import _run_small

        topics_list, doc_topic_list = _run_small(CORPUS_PT)

        assert len(topics_list) == 1, "corpus pequeno deve gerar exatamente 1 tópico global"
        assert topics_list[0]["id"] == 0

    def test_topic_has_words(self):
        from core.topic_extractor import _run_small, _TOP_WORDS_PER_TOPIC

        topics_list, _ = _run_small(CORPUS_PT)

        words = topics_list[0]["words"]
        assert len(words) <= _TOP_WORDS_PER_TOPIC
        assert all(isinstance(w, list) and len(w) == 2 for w in words), (
            "cada entrada deve ser [str, float]"
        )
        assert all(isinstance(w[0], str) and isinstance(w[1], float) for w in words)

    def test_doc_topic_length_matches_corpus(self):
        from core.topic_extractor import _run_small

        _, doc_topic_list = _run_small(CORPUS_PT)

        assert len(doc_topic_list) == len(CORPUS_PT)
        assert all(t == 0 for t in doc_topic_list), "todos os docs devem ter topic_id=0"

    def test_empty_corpus_returns_empty(self):
        from core.topic_extractor import _run_small

        topics_list, doc_topic_list = _run_small([])

        assert topics_list == []
        assert doc_topic_list == []

    def test_single_doc(self):
        from core.topic_extractor import _run_small

        topics_list, doc_topic_list = _run_small(["único documento de teste"])

        assert len(topics_list) == 1
        assert len(doc_topic_list) == 1

    def test_word_scores_are_positive(self):
        from core.topic_extractor import _run_small

        topics_list, _ = _run_small(CORPUS_PT)

        for word, score in topics_list[0]["words"]:
            assert score >= 0.0, f"score negativo para '{word}'"

    def test_scores_rounded_to_4_decimals(self):
        from core.topic_extractor import _run_small

        topics_list, _ = _run_small(CORPUS_PT)

        for word, score in topics_list[0]["words"]:
            assert score == round(score, 4), f"score de '{word}' não está arredondado"


# ---------------------------------------------------------------------------
# _extract_keywords
# ---------------------------------------------------------------------------

class TestExtractKeywords:
    def test_returns_list_per_doc(self):
        from core.topic_extractor import _extract_keywords

        result = _extract_keywords(CORPUS_PT)

        assert len(result) == len(CORPUS_PT)

    def test_each_entry_is_list_of_strings(self):
        from core.topic_extractor import _extract_keywords

        result = _extract_keywords(CORPUS_PT)

        for kws in result:
            assert isinstance(kws, list)
            assert all(isinstance(k, str) for k in kws)

    def test_max_keywords_per_doc(self):
        from core.topic_extractor import _extract_keywords, _KEYWORDS_PER_DOC

        result = _extract_keywords(CORPUS_PT)

        for kws in result:
            assert len(kws) <= _KEYWORDS_PER_DOC

    def test_empty_corpus(self):
        from core.topic_extractor import _extract_keywords

        result = _extract_keywords([])

        assert result == []

    def test_keywords_are_non_empty_strings(self):
        from core.topic_extractor import _extract_keywords

        result = _extract_keywords(CORPUS_PT)

        for kws in result:
            assert all(len(k) > 0 for k in kws)


# ---------------------------------------------------------------------------
# save_topics / load_topics
# ---------------------------------------------------------------------------

class TestSaveLoadTopics:
    def _make_result(self) -> dict:
        return {
            "topics": [{"id": 0, "words": [["linguística", 0.85], ["morfologia", 0.72]]}],
            "doc_topic": {"id_a": 0, "id_b": 0},
            "doc_keywords": {"id_a": ["linguística", "morfologia"], "id_b": ["sintaxe"]},
            "doc_sources": {"id_a": "/docs/a.pdf", "id_b": "/docs/b.epub"},
        }

    def test_roundtrip(self, tmp_path):
        from core.topic_extractor import save_topics, load_topics

        result = self._make_result()
        save_topics(result, str(tmp_path))
        loaded = load_topics(str(tmp_path))

        assert loaded == result

    def test_file_is_created(self, tmp_path):
        from core.topic_extractor import save_topics

        save_topics(self._make_result(), str(tmp_path))

        assert (tmp_path / "topics.json").exists()

    def test_file_is_valid_json(self, tmp_path):
        from core.topic_extractor import save_topics

        save_topics(self._make_result(), str(tmp_path))
        raw = (tmp_path / "topics.json").read_text(encoding="utf-8")

        parsed = json.loads(raw)
        assert "topics" in parsed

    def test_atomic_write_no_partial_file(self, tmp_path):
        """O arquivo .tmp não deve persistir após save_topics."""
        from core.topic_extractor import save_topics

        save_topics(self._make_result(), str(tmp_path))

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"arquivo temporário não removido: {tmp_files}"

    def test_load_returns_none_when_absent(self, tmp_path):
        from core.topic_extractor import load_topics

        result = load_topics(str(tmp_path))

        assert result is None

    def test_load_returns_none_on_corrupt_json(self, tmp_path):
        from core.topic_extractor import load_topics

        (tmp_path / "topics.json").write_text("{ broken json }", encoding="utf-8")
        result = load_topics(str(tmp_path))

        assert result is None

    def test_save_creates_parent_dirs(self, tmp_path):
        from core.topic_extractor import save_topics

        nested = tmp_path / "a" / "b" / "c"
        save_topics(self._make_result(), str(nested))

        assert (nested / "topics.json").exists()

    def test_overwrite_existing(self, tmp_path):
        from core.topic_extractor import save_topics, load_topics

        first = self._make_result()
        save_topics(first, str(tmp_path))

        second = self._make_result()
        second["topics"][0]["words"] = [["sintaxe", 0.99]]
        save_topics(second, str(tmp_path))

        loaded = load_topics(str(tmp_path))
        assert loaded["topics"][0]["words"][0][0] == "sintaxe"


# ---------------------------------------------------------------------------
# extract_topics (mock ChromaDB)
# ---------------------------------------------------------------------------

class TestExtractTopics:
    """Testa a função pública extract_topics() sem ChromaDB real.

    O ChromaDB é mockado via _collection.get() que retorna dados sintéticos.
    A CollectionConfig é um MagicMock com mnemosyne_dir configurado.
    """

    def _make_vs_mock(
        self,
        n_docs: int = 10,
        include_embeddings: bool = True,
    ) -> MagicMock:
        ids  = [f"id_{i}" for i in range(n_docs)]
        docs = [CORPUS_PT[i % len(CORPUS_PT)] for i in range(n_docs)]
        metas = [{"source": f"/docs/file_{i}.pdf"} for i in range(n_docs)]

        raw: dict = {"ids": ids, "documents": docs, "metadatas": metas}
        if include_embeddings:
            # Embeddings sintéticos — dimensão 16 é suficiente para o mock
            raw["embeddings"] = np.random.default_rng(42).random((n_docs, 16))
        else:
            raw["embeddings"] = None

        vs = MagicMock()
        vs._collection.get.return_value = raw
        return vs

    def _make_coll_mock(self, mnemosyne_dir: str = "") -> MagicMock:
        coll = MagicMock()
        coll.mnemosyne_dir = mnemosyne_dir
        return coll

    def test_returns_dict_with_expected_keys(self, tmp_path):
        from core.topic_extractor import extract_topics

        vs   = self._make_vs_mock()
        coll = self._make_coll_mock()

        result = extract_topics(vs, coll, mnemosyne_dir=str(tmp_path))

        assert isinstance(result, dict)
        for key in ("topics", "doc_topic", "doc_keywords", "doc_sources"):
            assert key in result, f"chave ausente: {key}"

    def test_saves_file_when_mnemosyne_dir_given(self, tmp_path):
        from core.topic_extractor import extract_topics

        vs   = self._make_vs_mock()
        coll = self._make_coll_mock()

        extract_topics(vs, coll, mnemosyne_dir=str(tmp_path))

        assert (tmp_path / "topics.json").exists()

    def test_no_file_when_no_dir(self, tmp_path):
        from core.topic_extractor import extract_topics

        vs   = self._make_vs_mock()
        coll = self._make_coll_mock(mnemosyne_dir="")  # sem dir

        extract_topics(vs, coll, mnemosyne_dir=None)

        assert not (tmp_path / "topics.json").exists()

    def test_empty_collection_returns_empty(self):
        from core.topic_extractor import extract_topics

        vs = MagicMock()
        vs._collection.get.return_value = {"ids": [], "documents": [], "metadatas": [], "embeddings": None}
        coll = self._make_coll_mock()

        result = extract_topics(vs, coll)

        assert result == {}

    def test_filters_blank_documents(self, tmp_path):
        """Chunks vazios devem ser ignorados no processamento."""
        from core.topic_extractor import extract_topics

        vs = MagicMock()
        vs._collection.get.return_value = {
            "ids":        ["id_0", "id_1", "id_2"],
            "documents":  ["texto real", "   ", ""],
            "metadatas":  [{}, {}, {}],
            "embeddings": None,
        }
        coll = self._make_coll_mock()

        result = extract_topics(vs, coll, mnemosyne_dir=str(tmp_path))

        # Somente id_0 deve aparecer em doc_topic
        assert "id_0" in result.get("doc_topic", {})
        assert "id_1" not in result.get("doc_topic", {})
        assert "id_2" not in result.get("doc_topic", {})

    def test_numpy_embeddings_do_not_crash(self, tmp_path):
        """Regression: embeddings como ndarray causavam ValueError no 'if embeddings'."""
        from core.topic_extractor import extract_topics

        vs   = self._make_vs_mock(n_docs=5, include_embeddings=True)
        coll = self._make_coll_mock()

        # Não deve levantar ValueError
        result = extract_topics(vs, coll, mnemosyne_dir=str(tmp_path))

        assert isinstance(result, dict)
