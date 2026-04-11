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


def _get_splitter(config: AppConfig) -> RecursiveCharacterTextSplitter:
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
    documents, _ = load_documents(config.watched_dir, source_type="biblioteca")

    # Indexar vault do Obsidian se configurado
    if config.vault_dir and os.path.isdir(config.vault_dir):
        vault_docs, _ = load_documents(config.vault_dir, source_type="vault")
        documents.extend(vault_docs)

    if not documents:
        raise EmptyDirectoryError(config.watched_dir)

    splitter = _get_splitter(config)
    chunks = splitter.split_documents(documents)

    try:
        os.makedirs(config.persist_dir, exist_ok=True)
        vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=_get_embeddings(config),
            persist_directory=config.persist_dir,
        )
    except Exception as exc:
        raise IndexBuildError(f"Falha ao criar vectorstore: {exc}") from exc

    return vectorstore


def index_single_file(file_path: str, config: AppConfig) -> Chroma:
    """
    Indexa um único arquivo e adiciona ao vectorstore existente (ou cria novo).
    Usado pelo watcher para indexação incremental sem rebuild completo.

    Raises:
        DocumentLoadError: se o arquivo não puder ser carregado.
        IndexBuildError: se a atualização do Chroma falhar.
    """
    docs = load_single_file(file_path)
    if not docs:
        return load_vectorstore(config)

    splitter = _get_splitter(config)
    chunks = splitter.split_documents(docs)

    try:
        os.makedirs(config.persist_dir, exist_ok=True)
        vs = Chroma(
            persist_directory=config.persist_dir,
            embedding_function=_get_embeddings(config),
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

    # Scan das pastas configuradas
    dirs: list[tuple[str, str]] = [(config.watched_dir, "biblioteca")]
    if config.vault_dir and os.path.isdir(config.vault_dir):
        dirs.append((config.vault_dir, "vault"))

    new_files: list[tuple[str, str]] = []
    modified_files: list[tuple[str, str]] = []
    deleted_files: list[str] = []

    for directory, source_type in dirs:
        n, m, d = tracker.get_pending(directory)
        new_files.extend((f, source_type) for f in n)
        modified_files.extend((f, source_type) for f in m)
        deleted_files.extend(d)

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
            docs = load_single_file(file_path, source_type=source_type)
            chunks = splitter.split_documents(docs)
            if chunks:
                vs.add_documents(chunks)
            tracker.mark_indexed(file_path)
            stats["modified"] += 1
        except Exception:
            stats["errors"] += 1

    # Novos
    for file_path, source_type in new_files:
        try:
            docs = load_single_file(file_path, source_type=source_type)
            chunks = splitter.split_documents(docs)
            if chunks:
                vs.add_documents(chunks)
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
    )
