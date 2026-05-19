"""BM25 index persistido em disco — paralelo ao ChromaDB.

Corpus = todos os chunks já indexados. Persistido como pickle em
{mnemosyne_dir}/bm25_index.pkl junto ao diretório do ChromaDB.

Usado por _hybrid_retrieve() em rag.py para RRF real sobre todo o corpus
em vez de BM25 sobre o pool semântico restrito.
"""
from __future__ import annotations

import pickle
from pathlib import Path

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi


_FILENAME = "bm25_index.pkl"


class BM25Index:
    """Índice BM25 sobre todos os chunks indexados.

    Mutação:
        add_documents(chunks)  — adiciona chunks ao corpus
        remove_source(path)    — remove todos os chunks de um arquivo
        clear()                — zera o corpus
    Persistência:
        save()                 — pickle para disco
        load(mnemosyne_dir)    — carrega do disco (classmethod)
        exists(mnemosyne_dir)  — verifica se o arquivo existe
    Busca:
        get_top_k(query, k)    — top-k como list[(rank, Document)]
    """

    def __init__(self, mnemosyne_dir: str) -> None:
        self._path = Path(mnemosyne_dir) / _FILENAME
        self._docs:  list[str]  = []
        self._metas: list[dict] = []
        self._bm25:  BM25Okapi | None = None
        self._deleted_paths: set[str] = set()

    # ------------------------------------------------------------------
    # Mutação
    # ------------------------------------------------------------------

    def add_documents(self, chunks: list[Document]) -> None:
        """Adiciona chunks ao corpus e invalida o índice em cache."""
        for chunk in chunks:
            self._docs.append(chunk.page_content)
            self._metas.append(chunk.metadata or {})
        self._bm25 = None

    def remove_source(self, file_path: str) -> None:
        """Remove todos os chunks de um arquivo do corpus."""
        pairs = [(d, m) for d, m in zip(self._docs, self._metas)
                 if m.get("source") != file_path]
        if pairs:
            self._docs, self._metas = map(list, zip(*pairs))  # type: ignore[assignment]
        else:
            self._docs, self._metas = [], []
        self._bm25 = None

    def remove_matching(self, **kwargs: object) -> int:
        """
        Remove documentos cujo metadata satisfaz TODAS as condições kwargs.
        Retorna o número de documentos removidos.

        Exemplo: bm25_idx.remove_matching(type="reflection", order=1, theme="cap3")
        """
        keep_docs:  list[str]  = []
        keep_metas: list[dict] = []
        removed = 0
        for doc, meta in zip(self._docs, self._metas):
            if all(meta.get(k) == v for k, v in kwargs.items()):
                removed += 1
            else:
                keep_docs.append(doc)
                keep_metas.append(meta)
        self._docs  = keep_docs
        self._metas = keep_metas
        if removed:
            self._bm25 = None
        return removed

    def mark_deleted(self, file_path: str) -> None:
        """Soft-delete: chunks desta fonte recebem penalidade 0.1× no score."""
        self._deleted_paths.add(file_path)

    def unmark_deleted(self, file_path: str) -> None:
        """Desfaz o soft-delete de um arquivo."""
        self._deleted_paths.discard(file_path)

    def clear(self) -> None:
        self._docs, self._metas, self._bm25 = [], [], None
        self._deleted_paths = set()

    # ------------------------------------------------------------------
    # Busca
    # ------------------------------------------------------------------

    def _ensure_built(self) -> None:
        if self._bm25 is None and self._docs:
            tokenized = [doc.lower().split() for doc in self._docs]
            self._bm25 = BM25Okapi(tokenized)

    def get_top_k(self, query: str, k: int) -> list[tuple[int, Document]]:
        """Retorna top-k resultados como (rank_posição, Document), ordenados por score.

        rank_posição=0 é o melhor resultado BM25.
        Documentos com score zero são excluídos.
        Chunks de arquivos soft-deleted recebem penalidade de 0.1×.
        """
        if not self._docs:
            return []
        self._ensure_built()
        assert self._bm25 is not None
        raw = self._bm25.get_scores(query.lower().split())
        scores = [
            s * (0.1 if self._metas[i].get("source") in self._deleted_paths else 1.0)
            for i, s in enumerate(raw)
        ]
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [
            (rank, Document(page_content=self._docs[i], metadata=self._metas[i]))
            for rank, i in enumerate(top_idx)
            if scores[i] > 0
        ]

    @property
    def size(self) -> int:
        return len(self._docs)

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Serializa corpus em disco (pickle protocol 4 — compatível Python 3.8+)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "wb") as f:
            pickle.dump(
                {"docs": self._docs, "metas": self._metas, "deleted_paths": self._deleted_paths},
                f, protocol=4,
            )

    @classmethod
    def load(cls, mnemosyne_dir: str) -> "BM25Index":
        """Carrega índice persistido. Retorna instância vazia se ausente ou corrompido."""
        idx = cls(mnemosyne_dir)
        if idx._path.exists():
            try:
                with open(idx._path, "rb") as f:
                    data = pickle.load(f)
                idx._docs          = data.get("docs",  [])
                idx._metas         = data.get("metas", [])
                idx._deleted_paths = set(data.get("deleted_paths", []))
            except Exception:
                pass  # índice corrompido — começa do zero
        return idx

    @classmethod
    def exists(cls, mnemosyne_dir: str) -> bool:
        return (Path(mnemosyne_dir) / _FILENAME).exists()
