"""
Teste de integração: pipeline completo de extração de temas.

Cria um ChromaDB in-memory com documentos sintéticos, executa extract_topics()
e verifica o arquivo topics.json resultante. Não usa modelo de embedding real —
passa embeddings pré-computados diretamente.

Requer: chromadb, scikit-learn (ambos no requirements.txt da Mnemosyne).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


CORPUS = [
    "linguística computacional processa linguagem natural",
    "morfologia estuda a estrutura das palavras",
    "sintaxe descreve regras de combinação em frases",
    "semântica investiga significado de palavras",
    "fonologia analisa sons e padrões",
    "pragmática estuda uso da linguagem em contexto",
    "sociolinguística examina variação linguística",
    "psicolinguística estuda o processamento cerebral da linguagem",
    "tradução automática usa redes neurais entre idiomas",
    "reconhecimento de voz transcreve fala em texto",
    "aprendizado de máquina classifica dados com algoritmos",
    "redes neurais artificiais imitam neurônios biológicos",
]


@pytest.fixture
def chroma_vs(tmp_path):
    """Cria um Chroma vectorstore in-memory com documentos e embeddings sintéticos."""
    chromadb = pytest.importorskip("chromadb")
    langchain_chroma = pytest.importorskip("langchain_chroma")

    # Nome único por test run — EphemeralClient compartilha estado in-process
    import uuid
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(f"test_{uuid.uuid4().hex[:8]}")

    rng  = np.random.default_rng(0)
    embs = rng.random((len(CORPUS), 32)).tolist()

    collection.add(
        ids=[f"id_{i}" for i in range(len(CORPUS))],
        documents=CORPUS,
        embeddings=embs,
        metadatas=[{"source": f"/docs/file_{i}.pdf"} for i in range(len(CORPUS))],
    )

    # Wrap num objeto com _collection compatível com extract_topics
    class _FakeVS:
        _collection = collection

    return _FakeVS()


@pytest.fixture
def coll_mock():
    from unittest.mock import MagicMock
    m = MagicMock()
    m.mnemosyne_dir = ""
    return m


class TestTopicsPipelineIntegration:
    def test_pipeline_produces_valid_json(self, chroma_vs, coll_mock, tmp_path):
        from core.topic_extractor import extract_topics

        result = extract_topics(chroma_vs, coll_mock, mnemosyne_dir=str(tmp_path))

        topics_file = tmp_path / "topics.json"
        assert topics_file.exists(), "topics.json deve ser criado"

        loaded = json.loads(topics_file.read_text(encoding="utf-8"))
        assert "topics" in loaded
        assert "doc_topic" in loaded
        assert "doc_keywords" in loaded
        assert "doc_sources" in loaded

    def test_pipeline_doc_ids_match_collection(self, chroma_vs, coll_mock, tmp_path):
        from core.topic_extractor import extract_topics

        result = extract_topics(chroma_vs, coll_mock, mnemosyne_dir=str(tmp_path))

        expected_ids = {f"id_{i}" for i in range(len(CORPUS))}
        assert set(result["doc_topic"].keys()) == expected_ids
        assert set(result["doc_keywords"].keys()) == expected_ids

    def test_pipeline_topics_have_words(self, chroma_vs, coll_mock, tmp_path):
        from core.topic_extractor import extract_topics

        result = extract_topics(chroma_vs, coll_mock, mnemosyne_dir=str(tmp_path))

        for topic in result["topics"]:
            assert "id" in topic
            assert "words" in topic
            assert len(topic["words"]) > 0

    def test_pipeline_keywords_are_strings(self, chroma_vs, coll_mock, tmp_path):
        from core.topic_extractor import extract_topics

        result = extract_topics(chroma_vs, coll_mock, mnemosyne_dir=str(tmp_path))

        for doc_id, kws in result["doc_keywords"].items():
            assert isinstance(kws, list), f"keywords de {doc_id} não é lista"
            assert all(isinstance(k, str) for k in kws)

    def test_pipeline_load_roundtrip(self, chroma_vs, coll_mock, tmp_path):
        from core.topic_extractor import extract_topics, load_topics

        result = extract_topics(chroma_vs, coll_mock, mnemosyne_dir=str(tmp_path))
        loaded = load_topics(str(tmp_path))

        assert loaded is not None
        assert loaded["topics"] == result["topics"]
        assert loaded["doc_topic"] == result["doc_topic"]
