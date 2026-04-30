"""
Indexing e vectorstore: divide documentos em chunks e persiste com Chroma.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Callable

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

from .bm25_index import BM25Index
from .config import AppConfig
from .errors import EmptyDirectoryError, IndexBuildError, VectorstoreNotFoundError
from .loaders import load_documents, load_single_file
from .ollama_client import _BASE_URL as _OLLAMA_BASE
from .reflection import generate_reflection, MIN_CHUNKS
from .tracker import FileTracker

# Arquivo JSON que contabiliza reflexões geradas por tema — usado pelo
# mecanismo de meta-reflexão para detectar quando consolidar 3 reflexões.
_REFLECTION_META_FILE = "reflection_meta.json"


def _clear_orphan_wal(persist_dir: str) -> None:
    """
    Apaga arquivos de lock SQLite órfãos (-wal, -shm) antes de abrir o ChromaDB.
    Quando o processo é encerrado abruptamente, esses arquivos permanecem no disco
    e fazem o SQLite reabrir a coleção em modo readonly na próxima tentativa.
    Removê-los força o SQLite a descartar a WAL pendente e reabrir normalmente.
    """
    base = Path(persist_dir) / "chroma.sqlite3"
    for suffix in ("-wal", "-shm"):
        lock = base.with_name(base.name + suffix)
        if lock.exists():
            try:
                lock.unlink()
            except OSError:
                pass


class IndexCheckpoint:
    """
    Registro SQLite de progresso de indexação em {mnemosyne_dir}/index_checkpoint.db.

    Criado pelo IndexWorker ao iniciar; registra cada arquivo processado.
    Deletado quando a indexação conclui com sucesso.
    A mera existência do arquivo indica que a indexação foi interrompida.
    O ResumeIndexWorker lê este checkpoint para pular arquivos já concluídos.
    """

    _FILENAME = "index_checkpoint.db"

    def __init__(self, mnemosyne_dir: str) -> None:
        self._db_path = Path(mnemosyne_dir) / self._FILENAME
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS indexed_files (
                path       TEXT PRIMARY KEY,
                mtime      REAL NOT NULL,
                status     TEXT NOT NULL DEFAULT 'ok',
                indexed_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self._conn.commit()

    def is_done(self, file_path: str) -> bool:
        """True se o arquivo foi indexado com sucesso e o mtime não mudou."""
        try:
            mtime = os.stat(file_path).st_mtime
        except OSError:
            return False
        row = self._conn.execute(
            "SELECT mtime FROM indexed_files WHERE path = ? AND status = 'ok'",
            (file_path,),
        ).fetchone()
        return row is not None and abs(row[0] - mtime) < 1.0

    def record(self, file_path: str, status: str = "ok") -> None:
        try:
            mtime = os.stat(file_path).st_mtime
        except OSError:
            mtime = 0.0
        self._conn.execute(
            "INSERT OR REPLACE INTO indexed_files (path, mtime, status) VALUES (?, ?, ?)",
            (file_path, mtime, status),
        )
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def delete(self) -> None:
        """Apaga o banco de checkpoint após conclusão bem-sucedida."""
        self.close()
        try:
            self._db_path.unlink(missing_ok=True)
        except OSError:
            pass

    @classmethod
    def exists(cls, mnemosyne_dir: str) -> bool:
        """True se existe checkpoint de indexação interrompida."""
        return (Path(mnemosyne_dir) / cls._FILENAME).exists()


def _embed_batch(texts: list[str], model: str, base_url: str = _OLLAMA_BASE) -> list[list[float]]:
    """Chama /api/embed do Ollama com um lote de textos — 1 HTTP por lote.

    Muito mais eficiente que OllamaEmbeddings (que faz 1 chamada por texto).
    """
    import httpx
    resp = httpx.post(
        f"{base_url}/api/embed",
        json={"model": model, "input": texts},
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"]


CHUNK_PARAMS: dict[str, dict[str, int]] = {
    "article":    {"chunk_size": 768,  "chunk_overlap": 100},
    "transcript": {"chunk_size": 400,  "chunk_overlap": 60},
    "note":       {"chunk_size": 384,  "chunk_overlap": 50},
    "document":   {"chunk_size": 512,  "chunk_overlap": 75},
}

_TRANSCRIPT_EXTS = frozenset({".vtt", ".srt"})
_DOCUMENT_EXTS   = frozenset({".pdf", ".epub", ".docx"})


def _chunk_type_for(source_type: str, file_path: str = "") -> str:
    """Detecta o tipo lógico de conteúdo para selecionar parâmetros de chunking."""
    ext = os.path.splitext(file_path.lower())[1] if file_path else ""
    if ext in _TRANSCRIPT_EXTS:
        return "transcript"
    if source_type == "vault":
        return "note"
    if ext in _DOCUMENT_EXTS:
        return "document"
    return "article"  # .md/.txt em library → artigos scraped


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


def _get_splitter(
    config: AppConfig,
    embeddings: OllamaEmbeddings | None = None,
    source_type: str = "",
    file_path: str = "",
):
    """Retorna splitter configurado com parâmetros adaptativos por tipo de conteúdo.

    Se semantic_chunking=True, usa SemanticChunker (langchain-experimental).
    Caso contrário, usa RecursiveCharacterTextSplitter com separadores hierárquicos
    e parâmetros de chunk_size/overlap ajustados ao tipo de documento detectado:
      vault/.md        → note (384/50)
      .pdf/.epub/.docx → document (512/75)
      .vtt/.srt        → transcript (400/60)
      .md/.txt library → article (768/100)
    """
    if config.semantic_chunking:
        try:
            from langchain_experimental.text_splitter import SemanticChunker
            emb = embeddings or _get_embeddings(config)
            return SemanticChunker(emb)
        except ImportError:
            pass

    chunk_type = _chunk_type_for(source_type or config.collection_type, file_path)
    params = CHUNK_PARAMS.get(chunk_type, CHUNK_PARAMS["document"])
    return RecursiveCharacterTextSplitter(
        chunk_size=params["chunk_size"],
        chunk_overlap=params["chunk_overlap"],
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def _get_embeddings(config: AppConfig) -> OllamaEmbeddings:
    return OllamaEmbeddings(model=config.embed_model)


def _load_reflection_counts(mnemosyne_dir: str) -> dict[str, int]:
    path = Path(mnemosyne_dir) / _REFLECTION_META_FILE
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_reflection_counts(mnemosyne_dir: str, counts: dict[str, int]) -> None:
    path = Path(mnemosyne_dir) / _REFLECTION_META_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding="utf-8")


def _group_by_source(chunks: list[Document]) -> dict[str, list[Document]]:
    """Agrupa chunks por arquivo-fonte (metadata["source"])."""
    groups: dict[str, list[Document]] = {}
    for chunk in chunks:
        src = chunk.metadata.get("source", "")
        if src:
            groups.setdefault(src, []).append(chunk)
    return groups


def _add_reflection_to_index(
    vs: Chroma,
    bm25_idx: BM25Index,
    reflection: Document,
    embed_model: str,
) -> None:
    """Embeda e persiste uma reflexão no ChromaDB e no BM25Index."""
    import uuid
    embs = _embed_batch([reflection.page_content], embed_model)
    vs._collection.add(
        ids=[str(uuid.uuid4())],
        documents=[reflection.page_content],
        embeddings=embs,
        metadatas=[reflection.metadata or {}],
    )
    bm25_idx.add_documents([reflection])


def _generate_and_index_reflections(
    chunks_by_source: dict[str, list[Document]],
    vs: Chroma,
    bm25_idx: BM25Index,
    config: AppConfig,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """
    Gera reflexões para cada grupo de arquivo-fonte com ≥ MIN_CHUNKS chunks.

    Seta metadata["source"] = source_file na reflexão gerada para que a deleção
    padrão via _delete_file_chunks() / remove_source() funcione automaticamente
    quando o arquivo for modificado ou removido.

    Retorna número de reflexões geradas.
    """
    eligible = {s: c for s, c in chunks_by_source.items() if len(c) >= MIN_CHUNKS}
    if not eligible:
        return 0

    counts = _load_reflection_counts(config.mnemosyne_dir)
    total = len(eligible)
    n_generated = 0

    for idx, (source_file, chunks) in enumerate(eligible.items(), 1):
        label = f"{idx}/{total}"
        reflection = generate_reflection(
            chunks, config, progress_cb=progress_cb, group_label=label
        )
        if reflection is None:
            continue

        # Setar "source" igual ao arquivo de origem para que _delete_file_chunks()
        # e bm25_idx.remove_source() apaguem a reflexão automaticamente ao
        # modificar/deletar o arquivo.
        reflection.metadata["source"] = source_file

        _add_reflection_to_index(vs, bm25_idx, reflection, config.embed_model)

        theme = reflection.metadata.get("theme", "unknown")
        counts[theme] = counts.get(theme, 0) + 1
        n_generated += 1

    if n_generated:
        _save_reflection_counts(config.mnemosyne_dir, counts)

    return n_generated


def create_vectorstore(
    config: AppConfig,
    progress_cb: Callable[[str], None] | None = None,
) -> Chroma:
    """
    Carrega documentos de config.watched_dir (e opcionalmente config.vault_dir),
    divide em chunks e cria vectorstore único com metadata source_type.

    Args:
        progress_cb: callback opcional para emitir progresso na UI durante
                     geração de reflexões (ex: lambda msg: worker.progress.emit(msg)).

    Raises:
        FileNotFoundError: se o diretório não existir.
        EmptyDirectoryError: se nenhum documento for encontrado.
        IndexBuildError: se a criação do Chroma falhar.
    """
    source_type = config.collection_type  # "vault" or "library"
    documents, _ = load_documents(config.watched_dir, source_type=source_type)

    for extra_dir in config.extra_dirs:
        if os.path.isdir(extra_dir):
            extra_docs, _ = load_documents(extra_dir, source_type="library")
            documents.extend(extra_docs)

    if not documents:
        raise EmptyDirectoryError(config.watched_dir)

    embeddings = _get_embeddings(config)
    splitter = _get_splitter(config, embeddings, source_type=config.collection_type)
    chunks = splitter.split_documents(documents)

    _BATCH, _SLEEP = _detect_batch_config()
    try:
        import time
        import uuid
        os.makedirs(config.persist_dir, exist_ok=True)
        vs = Chroma(
            persist_directory=config.persist_dir,
            embedding_function=embeddings,
            collection_metadata={"hnsw:space": "cosine"},
        )
        for start in range(0, len(chunks), _BATCH):
            batch = chunks[start : start + _BATCH]
            embs = _embed_batch([c.page_content for c in batch], config.embed_model)
            vs._collection.add(
                ids=[str(uuid.uuid4()) for _ in batch],
                documents=[c.page_content for c in batch],
                embeddings=embs,
                metadatas=[c.metadata or {} for c in batch],
            )
            if start + _BATCH < len(chunks):
                time.sleep(_SLEEP)
    except Exception as exc:
        raise IndexBuildError(f"Falha ao criar vectorstore: {exc}") from exc

    bm25_idx = BM25Index(config.mnemosyne_dir)
    bm25_idx.add_documents(chunks)

    chunks_by_source = _group_by_source(chunks)
    _generate_and_index_reflections(chunks_by_source, vs, bm25_idx, config, progress_cb)

    bm25_idx.save()

    return vs


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

    splitter = _get_splitter(config, source_type=config.collection_type, file_path=file_path)
    chunks = splitter.split_documents(docs)

    try:
        import time
        import uuid
        os.makedirs(config.persist_dir, exist_ok=True)
        _clear_orphan_wal(config.persist_dir)
        vs = Chroma(
            persist_directory=config.persist_dir,
            embedding_function=_get_embeddings(config),
            collection_metadata={"hnsw:space": "cosine"},
        )
        _BATCH, _SLEEP = _detect_batch_config()
        batch_list = [chunks[b : b + _BATCH] for b in range(0, len(chunks), _BATCH)]
        for b_idx, batch in enumerate(batch_list):
            embs = _embed_batch([c.page_content for c in batch], config.embed_model)
            vs._collection.add(
                ids=[str(uuid.uuid4()) for _ in batch],
                documents=[c.page_content for c in batch],
                embeddings=embs,
                metadatas=[c.metadata or {} for c in batch],
            )
            if b_idx + 1 < len(batch_list):
                time.sleep(_SLEEP)
    except Exception as exc:
        raise IndexBuildError(f"Falha ao adicionar ao vectorstore: {exc}") from exc

    bm25_idx = BM25Index.load(config.mnemosyne_dir)
    bm25_idx.add_documents(chunks)
    bm25_idx.save()

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


def update_vectorstore(
    config: AppConfig,
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[Chroma, dict[str, int]]:
    """
    Actualiza o vectorstore incrementalmente usando FileTracker:
      - Adiciona chunks de ficheiros novos
      - Remove chunks antigos e re-indexa ficheiros modificados
      - Remove chunks de ficheiros deletados/renomeados
      - Gera reflexões de conhecimento para ficheiros novos/modificados

    Retorna (vectorstore, stats) onde stats = {new, modified, deleted, errors, reflections}.

    Raises:
        VectorstoreNotFoundError: se não houver vectorstore para actualizar.
        IndexBuildError: se uma operação crítica falhar.
    """
    _clear_orphan_wal(config.persist_dir)
    vs = load_vectorstore(config)
    tracker = FileTracker(config.mnemosyne_dir)

    source_type = config.collection_type  # "vault" or "library"
    dirs: list[tuple[str, str]] = [(config.watched_dir, source_type)]
    for extra_dir in config.extra_dirs:
        if os.path.isdir(extra_dir):
            dirs.append((extra_dir, "library"))

    new_files: list[tuple[str, str]] = []
    modified_files: list[tuple[str, str]] = []
    deleted_files: list[str] = []

    for directory, source_type in dirs:
        n, m, d = tracker.get_pending(directory)
        new_files.extend((f, source_type) for f in n)
        modified_files.extend((f, source_type) for f in m)
        deleted_files.extend(d)

    _BATCH, _SLEEP = _detect_batch_config()
    stats = {"new": 0, "modified": 0, "deleted": 0, "errors": 0, "reflections": 0}
    bm25_idx = BM25Index.load(config.mnemosyne_dir)

    # Deletados: _delete_file_chunks e remove_source apagam tanto chunks quanto
    # reflexões, pois reflexões têm metadata["source"] = file_path.
    for file_path in deleted_files:
        _delete_file_chunks(vs, file_path)
        bm25_idx.remove_source(file_path)
        tracker.remove(file_path)
        stats["deleted"] += 1

    import time
    import uuid

    def _add_chunks(vs: Chroma, chunks: list, embed_model: str) -> None:
        """Adiciona lista de chunks ao vectorstore via _embed_batch (sem OllamaEmbeddings)."""
        batch_list = [chunks[b : b + _BATCH] for b in range(0, len(chunks), _BATCH)]
        for b_idx, batch in enumerate(batch_list):
            embs = _embed_batch([c.page_content for c in batch], embed_model)
            vs._collection.add(
                ids=[str(uuid.uuid4()) for _ in batch],
                documents=[c.page_content for c in batch],
                embeddings=embs,
                metadatas=[c.metadata or {} for c in batch],
            )
            if b_idx + 1 < len(batch_list):
                time.sleep(_SLEEP)

    # Modificados: remove chunks e reflexões antigas (pelo source), re-indexa.
    # A deleção das reflexões é automática via _delete_file_chunks + remove_source.
    for file_path, source_type in modified_files:
        _delete_file_chunks(vs, file_path)
        bm25_idx.remove_source(file_path)
        try:
            docs = load_single_file(file_path, source_type=source_type)
            splitter = _get_splitter(config, source_type=source_type, file_path=file_path)
            chunks = splitter.split_documents(docs)
            _add_chunks(vs, chunks, config.embed_model)
            bm25_idx.add_documents(chunks)
            tracker.mark_indexed(file_path)
            stats["modified"] += 1
            # Gerar reflexão para o arquivo reindexado
            n = _generate_and_index_reflections(
                {file_path: chunks}, vs, bm25_idx, config, progress_cb
            )
            stats["reflections"] += n
        except Exception:
            stats["errors"] += 1

    # Novos
    for file_path, source_type in new_files:
        try:
            docs = load_single_file(file_path, source_type=source_type)
            splitter = _get_splitter(config, source_type=source_type, file_path=file_path)
            chunks = splitter.split_documents(docs)
            _add_chunks(vs, chunks, config.embed_model)
            bm25_idx.add_documents(chunks)
            tracker.mark_indexed(file_path)
            stats["new"] += 1
            # Gerar reflexão para o arquivo novo
            n = _generate_and_index_reflections(
                {file_path: chunks}, vs, bm25_idx, config, progress_cb
            )
            stats["reflections"] += n
        except Exception:
            stats["errors"] += 1

    bm25_idx.save()
    return vs, stats


def load_vectorstore(config: AppConfig) -> Chroma:
    """
    Carrega um vectorstore já persistido.

    Raises:
        VectorstoreNotFoundError: se o persist_dir não existir.
    """
    if not config.persist_dir or not os.path.exists(config.persist_dir):
        raise VectorstoreNotFoundError(config.persist_dir)

    _clear_orphan_wal(config.persist_dir)
    return Chroma(
        persist_directory=config.persist_dir,
        embedding_function=_get_embeddings(config),
        collection_metadata={"hnsw:space": "cosine"},
    )
