"""
Grafo de conhecimento inter-documentos.

Nós: termos/keywords extraídos por TF-IDF (top-5 por chunk).
Arestas: par (termo, documento) com peso = escore TF-IDF do termo no chunk.
A estrutura armazena, para cada termo, o conjunto de documentos onde aparece.
Isso permite:
  - Identificar documentos centrais (muitos termos em comum com a query)
  - Navegar vizinhança de um termo (outros termos co-presentes nos mesmos docs)

Resultado salvo em {mnemosyne_dir}/knowledge_graph.json:
  {
    "nodes":     [{"id": "termo", "docs": ["path1", ...]}, ...],
    "doc_terms": {"path": [["termo", 0.82], ...], ...}
  }

Construído a partir dos dados já indexados no ChromaDB — reutiliza o mesmo
padrão de topic_extractor.py (vs._collection.get() sem re-processar arquivos).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_chroma import Chroma

log = logging.getLogger("mnemosyne.knowledge_graph")

_KG_FILE         = "knowledge_graph.json"
_TOP_TERMS       = 5   # keywords por chunk
_MIN_DOC_COUNT   = 2   # termos que aparecem em apenas 1 doc não viram nó


class KnowledgeGraph:
    """
    Grafo de co-ocorrência de keywords entre documentos do corpus.

    A classe mantém dois índices complementares:
      _term_docs: term → set of doc paths  (rota: dado um termo, quais docs?)
      _doc_terms: doc  → list[(term, weight)]  (rota: dado um doc, quais termos?)

    A partir desses dois índices é possível navegar o grafo em ambas as direções
    sem precisar de uma biblioteca de grafos — o NetworkX é usado apenas na
    TopicsView para renderizar o mapa visual.
    """

    def __init__(self, mnemosyne_dir: str) -> None:
        self._dir  = Path(mnemosyne_dir)
        self._path = self._dir / _KG_FILE
        self._term_docs: dict[str, set[str]] = {}
        self._doc_terms: dict[str, list[tuple[str, float]]] = {}

    # ── Construção do grafo ────────────────────────────────────────────────

    def update(self, vs: "Chroma") -> None:
        """Reconstrói o grafo a partir do vectorstore ChromaDB.

        Busca todos os chunks e metadatas; extrai top-5 keywords por chunk
        via TF-IDF (reutiliza scikit-learn já instalado para BERTopic).
        Chunks do mesmo arquivo são agrupados — o peso final de um termo
        num documento é o máximo dos pesos em todos os chunks desse arquivo.
        """
        raw       = vs._collection.get(include=["documents", "metadatas"])
        ids       = raw.get("ids") or []
        docs      = raw.get("documents") or []
        metas     = raw.get("metadatas") or []

        valid = [
            (d, m)
            for d, m in zip(docs, metas)
            if d and d.strip()
        ]
        if not valid:
            log.warning("ChromaDB vazio — knowledge graph não construído.")
            return

        texts, metadatas = zip(*valid)
        texts     = list(texts)
        metadatas = list(metadatas)

        try:
            import numpy as np
            from sklearn.feature_extraction.text import TfidfVectorizer
        except ImportError as exc:
            log.warning("scikit-learn não instalado: %s", exc)
            return

        try:
            vectorizer   = TfidfVectorizer(max_features=2000, min_df=2, sublinear_tf=True)
            tfidf_matrix = vectorizer.fit_transform(texts)
            terms        = vectorizer.get_feature_names_out()
        except Exception as exc:
            log.warning("Falha ao calcular TF-IDF: %s", exc)
            return

        # Acumula: para cada (doc_path, term), guarda o peso máximo entre chunks
        best_weight: dict[tuple[str, str], float] = {}
        for i, meta in enumerate(metadatas):
            source = (meta or {}).get("source", "")
            if not source:
                continue
            row     = tfidf_matrix[i]
            indices = np.asarray(row.todense()).flatten().argsort()[::-1]
            for j in indices[:_TOP_TERMS]:
                w = float(tfidf_matrix[i, j])
                if w <= 0:
                    break
                key = (source, str(terms[j]))
                best_weight[key] = max(best_weight.get(key, 0.0), w)

        # Reconstrói os índices
        self._term_docs.clear()
        self._doc_terms.clear()

        for (source, term), weight in best_weight.items():
            if term not in self._term_docs:
                self._term_docs[term] = set()
            self._term_docs[term].add(source)
            if source not in self._doc_terms:
                self._doc_terms[source] = []
            self._doc_terms[source].append((term, weight))

        n_terms = sum(1 for s in self._term_docs.values() if len(s) >= _MIN_DOC_COUNT)
        n_docs  = len(self._doc_terms)
        log.info("Knowledge graph: %d termos conectivos, %d documentos.", n_terms, n_docs)

    # ── Consulta ───────────────────────────────────────────────────────────

    def score(self, query_keywords: list[str], docs: list) -> list[float]:
        """Re-ranqueia candidatos do retrieval por conectividade no grafo.

        Para cada documento candidato (LangChain Document), soma os pesos
        TF-IDF dos termos da query que estão presentes no grafo desse doc.
        Documentos mais "centrais" — que compartilham muitos termos com a
        query — recebem um boost aditivo, proporcional à soma dos pesos.
        """
        scores: list[float] = []
        for doc in docs:
            source   = getattr(doc, "metadata", {}).get("source", "")
            term_map = dict(self._doc_terms.get(source, []))
            boost    = sum(term_map.get(kw, 0.0) for kw in query_keywords)
            scores.append(boost)
        return scores

    def get_neighbors(self, entity: str) -> dict[str, list]:
        """Retorna documentos e entidades vizinhas de um termo.

        Útil para o mapa mental: dado um tópico, quais documentos o contêm?
        Dados esses documentos, quais outros termos aparecem neles (co-ocorrência)?
        """
        doc_paths = sorted(self._term_docs.get(entity, []))

        # Conta co-ocorrências: outros termos nos mesmos documentos
        cooc: dict[str, int] = {}
        for path in doc_paths:
            for term, _ in self._doc_terms.get(path, []):
                if term != entity:
                    cooc[term] = cooc.get(term, 0) + 1

        top_related = sorted(cooc.items(), key=lambda x: -x[1])[:10]
        return {
            "documents": doc_paths,
            "entities":  [t for t, _ in top_related],
        }

    # ── Persistência ───────────────────────────────────────────────────────

    def save(self) -> None:
        """Persiste knowledge_graph.json."""
        nodes = [
            {"id": term, "docs": sorted(doc_set)}
            for term, doc_set in self._term_docs.items()
            if len(doc_set) >= _MIN_DOC_COUNT
        ]
        data = {
            "nodes":     nodes,
            "doc_terms": {
                doc: [[t, round(w, 4)] for t, w in term_list]
                for doc, term_list in self._doc_terms.items()
            },
        }
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)
        log.info("Knowledge graph salvo em %s.", self._path)

    @classmethod
    def load(cls, mnemosyne_dir: str) -> "KnowledgeGraph | None":
        """Carrega knowledge_graph.json se existir. Retorna None se ausente ou inválido."""
        path = Path(mnemosyne_dir) / _KG_FILE
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            kg = cls(mnemosyne_dir)
            for node in data.get("nodes", []):
                kg._term_docs[node["id"]] = set(node["docs"])
            for doc, term_list in data.get("doc_terms", {}).items():
                kg._doc_terms[doc] = [(t, float(w)) for t, w in term_list]
            return kg
        except Exception as exc:
            log.warning("Falha ao carregar knowledge_graph.json: %s", exc)
            return None
