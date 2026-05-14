"""
Extração de temas de um corpus indexado no ChromaDB.

Reutiliza embeddings já calculados pelo indexador — sem re-processar arquivos.
Pipeline:
  corpus >= 30 docs → UMAP + HDBSCAN + c-TF-IDF (BERTopic)
  corpus  < 30 docs → c-TF-IDF sobre todo o corpus (1 tópico global, mais estável)
Keywords por documento via TF-IDF (leve, sem chamadas de embedding adicionais).

Resultado salvo em {coll.mnemosyne_dir}/topics.json:
  {
    "topics":       [{"id": int, "words": [[str, float], ...]}, ...],
    "doc_topic":    {"chroma_id": topic_id, ...},
    "doc_keywords": {"chroma_id": ["kw1", ...], ...}
  }

Dependências opcionais (instalar via pip):
  bertopic>=0.16   umap-learn>=0.5   hdbscan>=0.8   scikit-learn>=1.0
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_chroma import Chroma
    from .collections import CollectionConfig

log = logging.getLogger("mnemosyne.topic_extractor")

_TOPICS_FILE = "topics.json"
_SMALL_CORPUS_THRESHOLD = 30
_TOP_WORDS_PER_TOPIC = 10
_KEYWORDS_PER_DOC = 5


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def extract_topics(vs: "Chroma", coll: "CollectionConfig") -> dict:
    """Extrai temas do corpus e salva em topics.json.

    Args:
        vs:   Chroma vectorstore (langchain_chroma.Chroma).
        coll: CollectionConfig da coleção correspondente.

    Returns:
        Dicionário com 'topics', 'doc_topic' e 'doc_keywords'. Vazio se o
        corpus não tiver documentos suficientes.
    """
    raw = vs._collection.get(include=["embeddings", "documents", "metadatas"])
    ids: list[str]              = raw.get("ids") or []
    docs: list[str]             = raw.get("documents") or []
    embeddings: list | None     = raw.get("embeddings")

    # Filtra entradas com texto vazio
    valid = [(i, d, (embeddings[idx] if embeddings else None))
             for idx, (i, d) in enumerate(zip(ids, docs)) if d and d.strip()]

    if not valid:
        log.warning("ChromaDB vazio — nenhum tópico extraído.")
        return {}

    valid_ids, valid_docs, valid_embs = zip(*valid)
    valid_ids  = list(valid_ids)
    valid_docs = list(valid_docs)

    n = len(valid_docs)
    log.info("Extraindo temas de %d documentos…", n)

    if n < _SMALL_CORPUS_THRESHOLD:
        topics_list, doc_topic_list = _run_small(valid_docs)
    else:
        # Se embeddings não estiverem disponíveis, recalcula com model2vec
        if any(e is None for e in valid_embs):
            log.info("Embeddings ausentes — recalculando com model2vec.")
            from .indexer import _embed_batch_model2vec
            valid_embs = _embed_batch_model2vec(valid_docs)
        else:
            valid_embs = list(valid_embs)
        topics_list, doc_topic_list = _run_large(valid_docs, valid_embs, n)

    doc_keywords = _extract_keywords(valid_docs)

    result = {
        "topics":       topics_list,
        "doc_topic":    {valid_ids[i]: doc_topic_list[i] for i in range(n)},
        "doc_keywords": {valid_ids[i]: doc_keywords[i]  for i in range(n)},
    }

    if coll.mnemosyne_dir:
        save_topics(result, coll.mnemosyne_dir)

    return result


def save_topics(result: dict, mnemosyne_dir: str) -> None:
    """Persiste topics.json em {mnemosyne_dir}."""
    out = Path(mnemosyne_dir) / _TOPICS_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, out)
    log.info("Temas salvos em %s (%d tópicos).", out, len(result.get("topics", [])))


def load_topics(mnemosyne_dir: str) -> dict | None:
    """Carrega topics.json se existir, retorna None caso contrário."""
    path = Path(mnemosyne_dir) / _TOPICS_FILE
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Falha ao carregar topics.json: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Pipelines de extração
# ---------------------------------------------------------------------------

def _run_large(docs: list[str], embeddings: list, n: int) -> tuple[list[dict], list[int]]:
    """Pipeline BERTopic: UMAP → HDBSCAN → c-TF-IDF."""
    try:
        import numpy as np
        from bertopic import BERTopic
        from umap import UMAP
        from hdbscan import HDBSCAN

        min_cluster_size = max(2, n // 50)
        n_components = min(5, n - 1)
        n_neighbors  = min(15, max(2, n // 5))

        umap_model    = UMAP(
            n_components=n_components,
            n_neighbors=n_neighbors,
            min_dist=0.0,
            metric="cosine",
            random_state=42,
        )
        hdbscan_model = HDBSCAN(
            min_cluster_size=min_cluster_size,
            metric="euclidean",
            prediction_data=True,
        )
        topic_model = BERTopic(
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            calculate_probabilities=False,
            verbose=False,
        )
        topic_assignments, _ = topic_model.fit_transform(
            docs, embeddings=np.array(embeddings, dtype=float)
        )
        topics_raw = topic_model.get_topics()

        topics_list: list[dict] = []
        for tid, word_scores in sorted(topics_raw.items()):
            if tid == -1:
                continue  # -1 = ruído (outliers não clusterizados)
            words = [[w, round(float(s), 4)] for w, s in word_scores[:_TOP_WORDS_PER_TOPIC]]
            topics_list.append({"id": int(tid), "words": words})

        doc_topic_list = [int(t) for t in topic_assignments]
        log.info("BERTopic: %d tópicos encontrados.", len(topics_list))
        return topics_list, doc_topic_list

    except ImportError as exc:
        log.warning("BERTopic/UMAP/HDBSCAN não instalados (%s) — usando c-TF-IDF.", exc)
        return _run_small(docs)
    except Exception as exc:
        log.warning("Falha no pipeline BERTopic: %s — usando c-TF-IDF.", exc)
        return _run_small(docs)


def _run_small(docs: list[str]) -> tuple[list[dict], list[int]]:
    """c-TF-IDF simples sobre todo o corpus como único tópico."""
    try:
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(
            max_features=500,
            min_df=1,
            sublinear_tf=True,
        )
        tfidf_matrix = vectorizer.fit_transform(docs)
        scores       = np.asarray(tfidf_matrix.sum(axis=0)).flatten()
        terms        = vectorizer.get_feature_names_out()
        top_idx      = np.argsort(scores)[::-1][:_TOP_WORDS_PER_TOPIC]
        words        = [[terms[i], round(float(scores[i]), 4)] for i in top_idx]

        topics_list    = [{"id": 0, "words": words}]
        doc_topic_list = [0] * len(docs)
        log.info("c-TF-IDF simples: 1 tópico global extraído (%d docs).", len(docs))
        return topics_list, doc_topic_list

    except ImportError as exc:
        log.warning("scikit-learn não instalado: %s", exc)
        return [], [0] * len(docs)
    except Exception as exc:
        log.warning("Falha no c-TF-IDF: %s", exc)
        return [], [0] * len(docs)


# ---------------------------------------------------------------------------
# Keywords por documento
# ---------------------------------------------------------------------------

def _extract_keywords(docs: list[str]) -> list[list[str]]:
    """Extrai top-N keywords por documento via TF-IDF.

    Usa o vocabulário do corpus inteiro para que palavras raras em um único
    documento mas irrelevantes no corpus sejam penalizadas pelo IDF.
    """
    try:
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer   = TfidfVectorizer(max_features=1000, min_df=1, sublinear_tf=True)
        tfidf_matrix = vectorizer.fit_transform(docs)
        terms        = vectorizer.get_feature_names_out()

        result: list[list[str]] = []
        for i in range(len(docs)):
            row     = tfidf_matrix[i]
            indices = np.asarray(row.todense()).flatten().argsort()[::-1]
            kws     = [terms[j] for j in indices[:_KEYWORDS_PER_DOC]
                       if tfidf_matrix[i, j] > 0]
            result.append(kws)
        return result

    except Exception as exc:
        log.warning("Falha ao extrair keywords: %s", exc)
        return [[] for _ in docs]
