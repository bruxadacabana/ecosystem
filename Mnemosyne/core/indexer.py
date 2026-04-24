"""
Indexing e vectorstore: divide documentos em chunks e persiste com Chroma.
"""
from __future__ import annotations

import os

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

from .config import AppConfig
from .errors import EmptyDirectoryError, IndexBuildError, VectorstoreNotFoundError
from .loaders import load_documents, load_single_file
from .tracker import FileTracker


def _detect_batch_config() -> tuple[int, float]:
    """
    Retorna (batch_size, sleep_s) baseado na RAM disponível.
    Hardware fraco (< 10 GB): batch pequeno e pausa longa para não travar o sistema.
    Hardware forte (com GPU provavelmente): batch grande e pausa mínima.
    """
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024 ** 3)
    except ImportError:
        ram_gb = 8.0  # assume conservador se psutil indisponível
    if ram_gb < 10:
        return 10, 1.0
    elif ram_gb < 20:
        return 25, 0.3
    return 50, 0.05


def _get_splitter(config: AppConfig, embeddings: OllamaEmbeddings | None = None):
    """
    Retorna splitter configurado. Se semantic_chunking=True, usa SemanticChunker
    (requer langchain-experimental; faz chamadas de embedding durante o split
    para detectar fronteiras semânticas — mais lento, chunks mais coesos).
    Fallback para RecursiveCharacterTextSplitter se o pacote não estiver instalado.
    """
    if config.semantic_chunking:
        try:
            from langchain_experimental.text_splitter import SemanticChunker
            emb = embeddings or _get_embeddings(config)
            return SemanticChunker(emb)
        except ImportError:
            pass
    return RecursiveCharacterTextSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )


def _get_embeddings(config: AppConfig) -> OllamaEmbeddings:
    return OllamaEmbeddings(model=config.embed_model)


def create_vectorstore(config: AppConfig) -> Chroma:
    """
    Carrega documentos de config.watched_dir (e opcionalmente config.vault_dir),
    divide em chunks e cria vectorstore único com metadata source_type.

    Raises:
        FileNotFoundError: se o diretório não existir.
        EmptyDirectoryError: se nenhum documento for encontrado.
        IndexBuildError: se a criação do Chroma falhar.
    """
    source_type = config.collection_type  # "vault" or "library"
    documents, _ = load_documents(config.watched_dir, source_type=source_type)

    if not documents:
        raise EmptyDirectoryError(config.watched_dir)

    embeddings = _get_embeddings(config)
    splitter = _get_splitter(config, embeddings)
    chunks = splitter.split_documents(documents)

    _BATCH, _SLEEP = _detect_batch_config()
    try:
        import time
        os.makedirs(config.persist_dir, exist_ok=True)
        vectorstore = None
        for b in range(0, len(chunks), _BATCH):
            batch = chunks[b : b + _BATCH]
            if vectorstore is None:
                vectorstore = Chroma.from_documents(
                    documents=batch,
                    embedding=embeddings,
                    persist_directory=config.persist_dir,
                    collection_metadata={"hnsw:space": "cosine"},
                )
            else:
                vectorstore.add_documents(batch)
            if b + _BATCH < len(chunks):
                time.sleep(_SLEEP)
    except Exception as exc:
        raise IndexBuildError(f"Falha ao criar vectorstore: {exc}") from exc

    return vectorstore  # type: ignore[return-value]


def index_single_file(file_path: str, config: AppConfig) -> Chroma:
    """
    Indexa um único arquivo e adiciona ao vectorstore existente (ou cria novo).
    Usado pelo watcher para indexação incremental sem rebuild completo.

    Raises:
        DocumentLoadError: se o arquivo não puder ser carregado.
        IndexBuildError: se a atualização do Chroma falhar.
    """
    docs = load_single_file(file_path, source_type=config.collection_type)
    if not docs:
        return load_vectorstore(config)

    splitter = _get_splitter(config)
    chunks = splitter.split_documents(docs)

    try:
        os.makedirs(config.persist_dir, exist_ok=True)
        vs = Chroma(
            persist_directory=config.persist_dir,
            embedding_function=_get_embeddings(config),
            collection_metadata={"hnsw:space": "cosine"},
        )
        vs.add_documents(chunks)
    except Exception as exc:
        raise IndexBuildError(f"Falha ao adicionar ao vectorstore: {exc}") from exc

    return vs


def _delete_file_chunks(vs: Chroma, file_path: str) -> None:
    """
    Remove todos os chunks de um arquivo do vectorstore via metadata filter.

    Nota: usa vs._collection (atributo privado do ChromaDB) — verificar
    compatibilidade ao actualizar o pacote chromadb.
    """
    try:
        vs._collection.delete(where={"source": file_path})
    except Exception:
        pass  # Se falhar (ex: versão incompatível), continua sem travar


def update_vectorstore(config: AppConfig) -> tuple[Chroma, dict[str, int]]:
    """
    Actualiza o vectorstore incrementalmente usando FileTracker:
      - Adiciona chunks de ficheiros novos
      - Remove chunks antigos e re-indexa ficheiros modificados
      - Remove chunks de ficheiros deletados/renomeados

    Retorna (vectorstore, stats) onde stats = {new, modified, deleted, errors}.

    Raises:
        VectorstoreNotFoundError: se não houver vectorstore para actualizar.
        IndexBuildError: se uma operação crítica falhar.
    """
    vs = load_vectorstore(config)
    tracker = FileTracker(config.mnemosyne_dir)
    splitter = _get_splitter(config)

    source_type = config.collection_type  # "vault" or "library"
    dirs: list[tuple[str, str]] = [(config.watched_dir, source_type)]

    new_files: list[tuple[str, str]] = []
    modified_files: list[tuple[str, str]] = []
    deleted_files: list[str] = []

    for directory, source_type in dirs:
        n, m, d = tracker.get_pending(directory)
        new_files.extend((f, source_type) for f in n)
        modified_files.extend((f, source_type) for f in m)
        deleted_files.extend(d)

    _BATCH, _SLEEP = _detect_batch_config()
    stats = {"new": 0, "modified": 0, "deleted": 0, "errors": 0}

    # Deletados
    for file_path in deleted_files:
        _delete_file_chunks(vs, file_path)
        tracker.remove(file_path)
        stats["deleted"] += 1

    # Modificados: remove chunks antigos, re-indexa
    for file_path, source_type in modified_files:
        _delete_file_chunks(vs, file_path)
        try:
            import time
            docs = load_single_file(file_path, source_type=source_type)
            chunks = splitter.split_documents(docs)
            for b in range(0, len(chunks), _BATCH):
                vs.add_documents(chunks[b : b + _BATCH])
                if b + _BATCH < len(chunks):
                    time.sleep(_SLEEP)
            tracker.mark_indexed(file_path)
            stats["modified"] += 1
        except Exception:
            stats["errors"] += 1

    # Novos
    for file_path, source_type in new_files:
        try:
            import time
            docs = load_single_file(file_path, source_type=source_type)
            chunks = splitter.split_documents(docs)
            for b in range(0, len(chunks), _BATCH):
                vs.add_documents(chunks[b : b + _BATCH])
                if b + _BATCH < len(chunks):
                    time.sleep(_SLEEP)
            tracker.mark_indexed(file_path)
            stats["new"] += 1
        except Exception:
            stats["errors"] += 1

    return vs, stats


def load_vectorstore(config: AppConfig) -> Chroma:
    """
    Carrega um vectorstore já persistido.

    Raises:
        VectorstoreNotFoundError: se o persist_dir não existir.
    """
    if not config.persist_dir or not os.path.exists(config.persist_dir):
        raise VectorstoreNotFoundError(config.persist_dir)

    return Chroma(
        persist_directory=config.persist_dir,
        embedding_function=_get_embeddings(config),
        collection_metadata={"hnsw:space": "cosine"},
    )
