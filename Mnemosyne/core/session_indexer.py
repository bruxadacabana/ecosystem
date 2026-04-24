"""
Indexação temporária em memória para sessões de pesquisa profunda.
Usa chromadb.EphemeralClient — nada é persistido em disco.
Estimativa de RAM: ~50-100 MB por sessão com 10 páginas web típicas.
"""
from __future__ import annotations

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .akasha_client import FetchResult
from .errors import IndexBuildError

_MAX_PAGES_DEFAULT = 10
_COLLECTION_NAME = "deep_research_session"
# Chunks menores que na indexação permanente: conteúdo web é mais denso
_CHUNK_SIZE = 1200
_CHUNK_OVERLAP = 150


class SessionIndexer:
    """
    Vectorstore efêmero (in-memory) para páginas web de uma sessão de pesquisa.
    Criar uma instância por sessão; chamar clear() após receber a resposta.

    Exemplo:
        indexer = SessionIndexer(embed_model="nomic-embed-text")
        indexer.add_pages(pages)
        docs = indexer.search("minha pergunta", k=5)
        indexer.clear()
    """

    def __init__(
        self,
        embed_model: str,
        max_pages: int = _MAX_PAGES_DEFAULT,
    ) -> None:
        self._embed_model = embed_model
        self._max_pages = max_pages
        self._page_count = 0
        self._chroma_client = chromadb.EphemeralClient()
        self._embeddings = OllamaEmbeddings(model=embed_model)
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=_CHUNK_SIZE,
            chunk_overlap=_CHUNK_OVERLAP,
        )
        self._vs: Chroma | None = None

    @property
    def page_count(self) -> int:
        return self._page_count

    @property
    def is_empty(self) -> bool:
        return self._page_count == 0

    def _ensure_vectorstore(self) -> Chroma:
        if self._vs is None:
            self._vs = Chroma(
                client=self._chroma_client,
                collection_name=_COLLECTION_NAME,
                embedding_function=self._embeddings,
                collection_metadata={"hnsw:space": "cosine"},
            )
        return self._vs

    def add_pages(self, pages: list[FetchResult]) -> None:
        """
        Chunka e indexa páginas em memória.
        Páginas sem conteúdo são ignoradas. Respeita o limite max_pages.

        Raises:
            IndexBuildError: se a indexação falhar.
        """
        if not pages:
            return

        docs: list[Document] = []
        for page in pages:
            if self._page_count >= self._max_pages:
                break
            if not page.content_md.strip():
                continue
            docs.append(Document(
                page_content=page.content_md,
                metadata={
                    "source": page.url,
                    "title": page.title,
                    "word_count": page.word_count,
                    "source_type": "web",
                },
            ))
            self._page_count += 1

        if not docs:
            return

        try:
            chunks = self._splitter.split_documents(docs)
            self._ensure_vectorstore().add_documents(chunks)
        except Exception as exc:
            raise IndexBuildError(f"Falha ao indexar páginas em memória: {exc}") from exc

    def search(self, query: str, k: int = 5) -> list[Document]:
        """
        Busca semântica no índice em memória.
        Retorna lista vazia se nada estiver indexado.
        """
        if self._vs is None or self._page_count == 0:
            return []
        return self._vs.similarity_search(query, k=k)

    def clear(self) -> None:
        """Descarta a coleção em memória e reseta o estado."""
        try:
            self._chroma_client.delete_collection(_COLLECTION_NAME)
        except Exception:
            pass  # EphemeralClient: sem colecção para apagar se nunca foi criada
        self._vs = None
        self._page_count = 0
