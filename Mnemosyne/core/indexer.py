"""
Indexing e vectorstore: divide documentos em chunks e persiste com Chroma.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
from enum import Enum
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings as LCEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from .bm25_index import BM25Index
from .config import AppConfig
from .errors import EmptyDirectoryError, EmbedTimeoutError, IndexBuildError, VectorstoreNotFoundError
from .loaders import load_documents, load_single_file, is_transcript_file
from .parent_store import ParentStore
from .reflection import generate_reflection, maybe_consolidate, MIN_CHUNKS
from .tracker import FileTracker

# Arquivo JSON que contabiliza reflexões geradas por tema — usado pelo
# mecanismo de meta-reflexão para detectar quando consolidar 3 reflexões.
_REFLECTION_META_FILE = "reflection_meta.json"

# Identificador do modelo de embedding estático (model2vec — sem Ollama, sem AVX2).
# Útil no Windows de trabalho (i5-3470, sem GPU) onde bge-m3 satura o CPU.
_POTION_MODEL_NAME = "potion-multilingual-128M"

# Cache singleton do StaticModel — carregado uma vez por processo, reutilizado.
_model2vec_instance: object | None = None


class _Model2VecEmbeddings(LCEmbeddings):
    """Wrapper LangChain para model2vec (StaticModel).

    Carrega o modelo na primeira chamada e o mantém em memória. Não depende do
    Ollama — embeddings gerados localmente via model2vec em ~50ms por chunk.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return _embed_batch_model2vec(texts)

    def embed_query(self, text: str) -> list[float]:
        return _embed_batch_model2vec([text])[0]


def _embed_batch_model2vec(texts: list[str]) -> list[list[float]]:
    global _model2vec_instance
    if _model2vec_instance is None:
        try:
            from model2vec import StaticModel  # type: ignore[import]
            _model2vec_instance = StaticModel.from_pretrained(_POTION_MODEL_NAME)
        except ImportError as exc:
            raise IndexBuildError(
                "model2vec não instalado. Execute: pip install model2vec"
            ) from exc
    return _model2vec_instance.encode(texts).tolist()  # type: ignore[union-attr]


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


# ---------------------------------------------------------------------------
# Indexação incremental em 4 níveis
# ---------------------------------------------------------------------------

class ChangeLevel(Enum):
    COSMETIC   = "cosmetic"    # só espaços/capitalização — sem re-embedding
    STRUCTURAL = "structural"  # chunks específicos mudaram — delta mínimo
    FULL       = "full"        # arquivo novo (sem histórico) — indexação completa


def _ch(text: str) -> str:
    """Hash bruto do chunk — detecta mudanças semânticas."""
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _nh(text: str) -> str:
    """Hash normalizado — ignora espaços e capitalização (detecção cosmética)."""
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


class ChunkHashStore:
    """
    Persiste (content_hash, norm_hash, chroma_id) por arquivo em
    {persist_dir}/.chunk_hashes.db. Permite identificar exatamente quais
    chunks mudaram sem re-embelar todo o arquivo.
    """
    _FILENAME = ".chunk_hashes.db"

    def __init__(self, persist_dir: str) -> None:
        db_path = Path(persist_dir) / self._FILENAME
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS chunk_hashes (
                file_path    TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                norm_hash    TEXT NOT NULL,
                chroma_id    TEXT NOT NULL,
                PRIMARY KEY (file_path, content_hash)
            )
        """)
        self._conn.commit()

    def get_file_records(self, file_path: str) -> list[tuple[str, str, str]]:
        rows = self._conn.execute(
            "SELECT content_hash, norm_hash, chroma_id FROM chunk_hashes WHERE file_path = ?",
            (file_path,),
        ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    def save_file_records(self, file_path: str, records: list[tuple[str, str, str]]) -> None:
        self._conn.execute("DELETE FROM chunk_hashes WHERE file_path = ?", (file_path,))
        self._conn.executemany(
            "INSERT INTO chunk_hashes (file_path, content_hash, norm_hash, chroma_id) "
            "VALUES (?, ?, ?, ?)",
            [(file_path, h, nh, cid) for h, nh, cid in records],
        )
        self._conn.commit()

    def delete_file(self, file_path: str) -> None:
        self._conn.execute("DELETE FROM chunk_hashes WHERE file_path = ?", (file_path,))
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


_NODE_TYPES = frozenset({"article", "entity", "topic", "claim", "source"})

_NODE_TYPE_PROMPT = (
    "Classifica cada trecho em uma categoria: "
    "article (texto informativo), claim (afirmação ou opinião do autor), "
    "entity (pessoa/lugar/objeto específico), topic (introdução de tema), "
    "source (referência, citação ou URL).\n"
    "Responde APENAS com as categorias, uma por linha, sem mais texto.\n\n"
    "Trechos:\n{items}"
)


def _classify_node_types(
    chunks: list[Document],
    model: str,
    base_url: str | None = None,
    batch_size: int = 10,
) -> None:
    """
    Classifica chunks em tipos de nó e define metadata["node_type"] in-place.
    Usa prompt batch para minimizar chamadas HTTP; fallback para "article".
    """
    import httpx

    if base_url is None:
        from ecosystem_client import get_inference_url as _giu
        base_url = _giu()

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        items = "\n".join(f"[{i+1}] {c.page_content[:300]}" for i, c in enumerate(batch))
        prompt = _NODE_TYPE_PROMPT.format(items=items)
        labels: list[str] = []
        try:
            resp = httpx.post(
                f"{base_url}/v1/chat/completions",
                json={"model": model, "messages": [{"role": "user", "content": prompt}],
                      "stream": False, "temperature": 0},
                timeout=60.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            lines = [l.strip().lower() for l in content.splitlines() if l.strip()]
            labels = [l for l in lines if l in _NODE_TYPES]
        except Exception:
            pass
        for j, chunk in enumerate(batch):
            chunk.metadata["node_type"] = labels[j] if j < len(labels) else "article"


def _incremental_update(
    vs: Chroma,
    bm25_idx: BM25Index,
    store: ChunkHashStore,
    file_path: str,
    new_chunks: list[Document],
    embed_model: str,
    truncate_dim: int | None,
    batch_size: int,
    sleep_s: float,
    node_type_model: str = "",
) -> ChangeLevel:
    """
    Atualiza o índice com delta mínimo de chunks.

    FULL       — arquivo novo: embeda tudo.
    STRUCTURAL — alguns chunks mudaram: só re-embeda os diferentes.
    COSMETIC   — só espaços/capitalização: não toca o ChromaDB.

    Retorna o nível de mudança detectado.
    """
    import time as _time
    import uuid

    old_records = store.get_file_records(file_path)
    new_ch_map: dict[str, Document] = {_ch(c.page_content): c for c in new_chunks}
    new_nh_set: set[str] = {_nh(c.page_content) for c in new_chunks}

    if not old_records:
        level = ChangeLevel.FULL
        old_ch_to_rec: dict[str, tuple[str, str, str]] = {}
    else:
        old_ch_to_rec = {h: (h, nh, cid) for h, nh, cid in old_records}
        old_nh_set: set[str] = {nh for _, nh, _ in old_records}
        if new_nh_set == old_nh_set:
            return ChangeLevel.COSMETIC
        level = ChangeLevel.STRUCTURAL

    # Quais chunks adicionar e quais IDs deletar
    if level == ChangeLevel.FULL:
        chunks_to_add = new_chunks
        ids_to_delete: list[str] = []
    else:
        old_ch_set = set(old_ch_to_rec)
        new_ch_set = set(new_ch_map)
        chunks_to_add = [new_ch_map[h] for h in new_ch_set - old_ch_set]
        ids_to_delete = [old_ch_to_rec[h][2] for h in old_ch_set - new_ch_set]

    # Deletar reflexões antigas do arquivo (serão regeneradas pelo chamador)
    if level != ChangeLevel.COSMETIC:
        try:
            vs._collection.delete(
                where={"$and": [{"source": {"$eq": file_path}},
                                {"type":   {"$eq": "reflection"}}]}
            )
        except Exception:
            pass

    if ids_to_delete:
        vs._collection.delete(ids=ids_to_delete)

    # Classificar node_type dos chunks a adicionar (FULL ou STRUCTURAL)
    if node_type_model and chunks_to_add:
        _classify_node_types(chunks_to_add, node_type_model)

    # Embedar apenas os chunks novos/alterados
    new_records: list[tuple[str, str, str]] = []
    for start in range(0, len(chunks_to_add), batch_size):
        batch = chunks_to_add[start : start + batch_size]
        embs = _embed_batch([c.page_content for c in batch], embed_model,
                            truncate_dim=truncate_dim)
        ids = [str(uuid.uuid4()) for _ in batch]
        vs._collection.add(
            ids=ids,
            documents=[c.page_content for c in batch],
            embeddings=embs,
            metadatas=[c.metadata or {} for c in batch],
        )
        for chunk, cid in zip(batch, ids):
            new_records.append((_ch(chunk.page_content), _nh(chunk.page_content), cid))
        if start + batch_size < len(chunks_to_add):
            _time.sleep(sleep_s)

    # Preservar registros dos chunks não-alterados (STRUCTURAL)
    if level == ChangeLevel.STRUCTURAL:
        kept_ch = set(new_ch_map) & set(old_ch_to_rec) - {_ch(c.page_content) for c in chunks_to_add}
        for h in kept_ch:
            new_records.append(old_ch_to_rec[h])

    store.save_file_records(file_path, new_records)

    # BM25: rebuild do arquivo (não tem índice incremental eficiente)
    bm25_idx.remove_source(file_path)
    if new_chunks:
        bm25_idx.add_documents(new_chunks)

    return level


_EMBED_TIMEOUT_S   = 120.0   # timeout por tentativa — detecta rápido
_EMBED_RETRY_WAITS = (30, 60) # aguarda LOGOS/Ollama liberar antes de re-tentar


def _embed_batch(
    texts: list[str],
    model: str,
    base_url: str | None = None,
    truncate_dim: int | None = None,  # ignorado — llama-server não suporta MRL truncation
) -> list[list[float]]:
    """Gera embeddings para um lote de textos via /v1/embeddings (OpenAI-compatível).

    Para potion-multilingual-128M: usa model2vec local (sem GPU, sem AVX2).

    Retries automáticos em dois cenários:
    - Timeout (httpx.TimeoutException): backend ocupado com LLM ativo.
    - 429 (LOGOS P3_TIMEOUT): LOGOS retorna 429 quando fila P3 espera >30s.

    base_url: resolvido em runtime via ecosystem_client (LOGOS 7072).
    """
    if model == _POTION_MODEL_NAME:
        return _embed_batch_model2vec(texts)

    import time
    import httpx

    if base_url is None:
        from ecosystem_client import get_inference_url as _giu
        base_url = _giu()

    payload: dict = {"model": model, "input": texts}

    last_exc: Exception | None = None
    for attempt, wait in enumerate((-1, *_EMBED_RETRY_WAITS)):
        if wait >= 0:
            log.debug("_embed_batch: ocupado (tentativa %d), aguardando %ds…", attempt, wait)
            time.sleep(wait)
        try:
            resp = httpx.post(
                f"{base_url}/v1/embeddings", json=payload, timeout=_EMBED_TIMEOUT_S
            )
            if resp.status_code == 429:
                last_exc = Exception("429 Too Many Requests (LOGOS P3 bloqueado)")
                continue
            resp.raise_for_status()
            return [d["embedding"] for d in resp.json()["data"]]
        except httpx.TimeoutException as exc:
            last_exc = exc
            continue

    raise EmbedTimeoutError(
        f"timed out após {1 + len(_EMBED_RETRY_WAITS)} tentativas "
        f"({len(texts)} chunks, modelo {model})"
    ) from last_exc


# Separadores por tipo: refletem a estrutura natural de cada formato.
# Separadores Unicode zh (。！？) incluídos em todos os tipos — sem custo para
# corpora pt/en (simplesmente não encontrados); essenciais para chinês que não
# usa espaços entre palavras. chunk_size em caracteres Unicode (length_function=len).
# Tamanhos: ~1000–1200 chars ≈ 300–400 words em pt/en ≈ 500–600 chars zh úteis.
# Overlap: ~15% do chunk_size.
CHUNK_PARAMS: dict[str, dict] = {
    "article":    {"chunk_size": 1200, "chunk_overlap": 180,
                   "separators": ["\n\n", "\n", "。", "！", "？", ". ", " ", ""]},
    "transcript": {"chunk_size": 600,  "chunk_overlap": 90,
                   "separators": ["。", "！", "？", ". ", "! ", "? ", "\n", ""]},
    "note":       {"chunk_size": 800,  "chunk_overlap": 120,
                   "separators": ["\n## ", "\n\n", "\n", "。", "！", "？", ". ", ""]},
    "document":   {"chunk_size": 1000, "chunk_overlap": 150,
                   "separators": ["\n# ", "\n## ", "\n\n", "\n", "。", "！", "？", ". ", ""]},
    "scientific": {"chunk_size": 1000, "chunk_overlap": 150,
                   "separators": ["\n## ", "\n\n", "。", "！", "？", ". ", "\n", ""]},
}

_TRANSCRIPT_EXTS = frozenset({".vtt", ".srt"})
_DOCUMENT_EXTS   = frozenset({".pdf", ".epub", ".docx"})

# Tamanhos para parent-child chunking: child preciso para retrieval; parent amplo para LLM.
_PARENT_CHUNK_SIZE = 1024
_CHILD_CHUNK_SIZE  = 256
_CHILD_OVERLAP     = 32


def _make_parent_id(source: str, idx: int) -> str:
    """ID determinístico: hash(source)[:12]_{idx} — mesmo arquivo sempre gera o mesmo ID."""
    return f"{hashlib.sha256(source.encode()).hexdigest()[:12]}_{idx}"


class ParentChildChunker:
    """
    Divide documentos em pares parent-child para retrieval hierárquico.

    Child chunks (256 chars) vão para o ChromaDB com metadata["parent_id"].
    Parent chunks (1024 chars) vão para o ParentStore (SQLite).

    Retrieval: child localiza o trecho preciso; parent fornece contexto amplo ao LLM.
    """

    def __init__(self, source_type: str = "article", file_path: str = "") -> None:
        ctype = _chunk_type_for(source_type, file_path)
        seps = CHUNK_PARAMS.get(ctype, CHUNK_PARAMS["document"]).get(
            "separators", ["\n\n", "\n", "。", "！", "？", ". ", " ", ""]
        )
        self._parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=_PARENT_CHUNK_SIZE,
            chunk_overlap=0,
            separators=seps,
            length_function=len,
            add_start_index=True,
        )
        self._child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=_CHILD_CHUNK_SIZE,
            chunk_overlap=_CHILD_OVERLAP,
            separators=seps,
            length_function=len,
            add_start_index=True,
        )

    def split_documents(
        self,
        docs: list[Document],
    ) -> tuple[list[Document], list[tuple[str, str, str]]]:
        """
        Retorna (child_chunks, parent_records).

        child_chunks: Documents para ChromaDB, cada um com metadata["parent_id"].
        parent_records: [(chunk_id, source, text)] para ParentStore.save_batch().
        """
        child_chunks: list[Document] = []
        parent_records: list[tuple[str, str, str]] = []

        for doc in docs:
            source = doc.metadata.get("source", "")
            parents = self._parent_splitter.split_documents([doc])

            for parent_idx, parent in enumerate(parents):
                parent_id = _make_parent_id(source, parent_idx)
                parent_records.append((parent_id, source, parent.page_content))

                children = self._child_splitter.split_documents([parent])
                for child in children:
                    child.metadata = dict(child.metadata)
                    child.metadata["parent_id"] = parent_id
                    child_chunks.append(child)

        return child_chunks, parent_records


def _delete_parent_chunks(config: "AppConfig", file_path: str) -> None:
    """Remove parent chunks do ParentStore ao deletar ou re-indexar um arquivo."""
    try:
        ps = ParentStore(config.persist_dir)
        ps.delete_by_source(file_path)
        ps.close()
        log.debug("indexer: parent chunks de %s deletados", file_path)
    except Exception as exc:
        log.debug("indexer: falha ao deletar parent chunks de %s: %s", file_path, exc)


def _enrich_file_background(config: "AppConfig", file_path: str, vs: object) -> None:
    """Executa enriquecimento P3 em thread daemon — não bloqueia o indexer."""
    try:
        from .context_enricher import ContextEnricher
        ContextEnricher(config).enrich_file(file_path, vs)
    except Exception as exc:
        log.debug("context_enricher background: %s", exc)


def _maybe_enrich(config: "AppConfig", file_path: str, vs: object) -> None:
    """Dispara enriquecimento P3 como fire-and-forget se habilitado."""
    if not config.enrichment_enabled:
        return
    import threading
    threading.Thread(
        target=_enrich_file_background,
        args=(config, file_path, vs),
        daemon=True,
    ).start()

# Detecta marcadores estruturais de artigos científicos
_SCIENTIFIC_MARKERS_RE = re.compile(
    r"^(abstract|references|referências|bibliography|doi:\s*\S|arxiv:\s*\S)",
    re.I | re.M,
)


def is_scientific_paper(file_path: str) -> bool:
    """
    Detecta se um arquivo .md é um artigo científico.
    Critérios (or):
      1. Frontmatter YAML com 'type: scientific' (gerado pelo AKASHA)
      2. Pelo menos 2 marcadores estruturais: Abstract, References/Referências, DOI:, arXiv:
    Lê apenas os primeiros 4 KB para manter latência baixa.
    """
    try:
        with open(file_path, encoding="utf-8", errors="ignore") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    if re.search(r"^type:\s*scientific", head, re.M):
        return True
    return len(_SCIENTIFIC_MARKERS_RE.findall(head)) >= 2


def _chunk_type_for(source_type: str, file_path: str = "") -> str:
    """Detecta o tipo lógico de conteúdo para selecionar parâmetros de chunking."""
    if source_type == "transcript":
        return "transcript"
    ext = os.path.splitext(file_path.lower())[1] if file_path else ""
    if ext in _TRANSCRIPT_EXTS:
        return "transcript"
    if source_type == "vault":
        return "note"
    if ext in _DOCUMENT_EXTS:
        return "document"
    if ext in (".md", ".txt") and file_path:
        if is_transcript_file(file_path):
            return "transcript"
        if is_scientific_paper(file_path):
            return "scientific"
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
    embeddings: LCEmbeddings | None = None,
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
        separators=params.get("separators", ["\n\n", "\n", "。", "！", "？", ". ", " ", ""]),
        length_function=len,
        add_start_index=True,
    )


def _enrich_chunk_offsets(
    chunks: list[Document],
    source_docs: list[Document],
) -> None:
    """
    Enriquece metadados de chunks com campos de ancoramento de citação. In-place.

    Campos adicionados:
      start_char   — offset do início do chunk no texto da página/arquivo de origem
      end_char     — offset do fim (exclusive)
      prefix_quote — 30 chars antes (desambiguação, padrão Hypothes.is)
      suffix_quote — 30 chars depois
      page_num     — número de página para PDFs (do metadata["page"] do PyPDFLoader)

    Requer splitter criado com add_start_index=True.
    SemanticChunker não suporta add_start_index — este método vira no-op nesses casos.
    """
    # Mapa (source_path, page_str) → texto do documento/página para prefix/suffix
    # page_str = "" para arquivos não-PDF (um único Document por arquivo)
    page_texts: dict[tuple[str, str], str] = {}
    for doc in source_docs:
        src = doc.metadata.get("source", "")
        page = str(doc.metadata.get("page", ""))
        if src:
            key = (src, page)
            page_texts[key] = page_texts.get(key, "") + doc.page_content

    for chunk in chunks:
        start = chunk.metadata.get("start_index")
        if start is None:
            continue
        end = start + len(chunk.page_content)
        chunk.metadata["start_char"] = start
        chunk.metadata["end_char"] = end

        src = chunk.metadata.get("source", "")
        page = str(chunk.metadata.get("page", ""))
        page_text = page_texts.get((src, page), "")
        if page_text:
            chunk.metadata["prefix_quote"] = page_text[max(0, start - 30) : start]
            chunk.metadata["suffix_quote"] = page_text[end : end + 30]

        if "page" in chunk.metadata:
            chunk.metadata["page_num"] = int(chunk.metadata["page"])


class _InferenceEmbeddings(LCEmbeddings):
    """Wrapper LangChain para embeddings via llama-server (/v1/embeddings)."""

    def __init__(self, model: str) -> None:
        self._model = model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return _embed_batch(texts, self._model)

    def embed_query(self, text: str) -> list[float]:
        return _embed_batch([text], self._model)[0]


def _get_embeddings(config: AppConfig) -> LCEmbeddings:
    if config.embed_model == _POTION_MODEL_NAME:
        return _Model2VecEmbeddings()
    return _InferenceEmbeddings(config.embed_model)


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


def _prepend_titles(chunks: list[Document]) -> None:
    """Prefixa cada chunk com o título do documento-fonte para melhorar recall.

    Título vem de metadata["title"]; fallback para o stem do caminho.
    Reflexões são ignoradas (já têm conteúdo estruturado próprio).
    Idempotente: não duplica o prefixo se já estiver presente.
    """
    for chunk in chunks:
        if chunk.metadata.get("type") == "reflection":
            continue
        title = str(chunk.metadata.get("title", "")).strip()
        if not title:
            source = chunk.metadata.get("source", "")
            if source:
                title = Path(source).stem
        if not title:
            continue
        prefix = f"[{title}]\n\n"
        if not chunk.page_content.startswith(prefix):
            chunk.page_content = prefix + chunk.page_content


_lingua_detector_instance: object | None = None

# Fontes com idioma não reconhecido na indexação corrente — limpo por
# get_and_clear_unknown_sources() após cada sessão de indexação.
_unknown_language_sources: set[str] = set()


def _get_lingua_detector():
    """Retorna o detector de idioma (singleton), ou None se não instalado.

    Usa from_all_languages() para cobrir os 75 idiomas da biblioteca sem precisar
    configurar uma lista estática. with_minimum_relative_distance(0.25) garante que
    detecções ambíguas retornem None em vez de um palpite incorreto.
    """
    global _lingua_detector_instance
    if _lingua_detector_instance is not None:
        return _lingua_detector_instance
    try:
        from lingua import LanguageDetectorBuilder
        _lingua_detector_instance = (
            LanguageDetectorBuilder
            .from_all_languages()
            .with_minimum_relative_distance(0.25)
            .build()
        )
        return _lingua_detector_instance
    except ImportError:
        return None


def get_and_clear_unknown_sources() -> list[str]:
    """Retorna e limpa a lista de fontes com idioma não reconhecido.

    Chamado pelos workers após o fim da indexação para emitir o sinal
    languages_unknown. Thread-safe para uso single-threaded (GIL Python).
    """
    global _unknown_language_sources
    result = sorted(_unknown_language_sources)
    _unknown_language_sources = set()
    return result


def _add_language_metadata(chunks: list[Document]) -> None:
    """Detecta o idioma de cada chunk e grava em metadata["language"] (ISO 639-1).

    Usa a amostra após o prefixo de título para não distorcer a detecção.
    Quando a detecção retorna None (confiança abaixo do limiar), grava "unknown"
    e acumula o arquivo-fonte em _unknown_language_sources para notificação na UI.
    Reflexões são ignoradas. Degradação graciosa se lingua não estiver instalado.
    """
    detector = _get_lingua_detector()
    if detector is None:
        return
    for chunk in chunks:
        if chunk.metadata.get("type") == "reflection":
            continue
        if "language" in chunk.metadata:
            continue
        text = chunk.page_content
        if text.startswith("[") and "]\n\n" in text[:100]:
            _, _, text = text.partition("]\n\n")
        sample = text[:300].strip()
        if not sample:
            continue
        try:
            result = detector.detect_language_of(sample)
            if result is not None:
                chunk.metadata["language"] = result.iso_code_639_1.name.lower()
            else:
                chunk.metadata["language"] = "unknown"
                src = chunk.metadata.get("source", "")
                if src:
                    _unknown_language_sources.add(src)
        except Exception:
            pass


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
    truncate_dim: int | None = None,
) -> None:
    """Embeda e persiste uma reflexão no ChromaDB e no BM25Index."""
    import uuid
    embs = _embed_batch([reflection.page_content], embed_model, truncate_dim=truncate_dim)
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
    _reflection_texts: list[str] = []

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

        _add_reflection_to_index(vs, bm25_idx, reflection, config.embed_model,
                                  truncate_dim=config.embedding_truncate_dim)

        theme = reflection.metadata.get("theme", "unknown")
        counts[theme] = counts.get(theme, 0) + 1
        n_generated += 1
        _reflection_texts.append(reflection.page_content)

    if n_generated:
        _save_reflection_counts(config.mnemosyne_dir, counts)

    # Tentar consolidar temas que atingiram ≥ 3 reflexões de ordem 1
    consolidated_themes: set[str] = set()
    for theme, total in counts.items():
        if total >= 3 and theme not in consolidated_themes:
            meta = maybe_consolidate(
                theme, config, vs, bm25_idx, progress_cb=progress_cb
            )
            if meta is not None:
                _add_reflection_to_index(vs, bm25_idx, meta, config.embed_model,
                                          truncate_dim=config.embedding_truncate_dim)
                bm25_idx.save()
                consolidated_themes.add(theme)
                _reflection_texts.append(meta.page_content)

    if _reflection_texts:
        try:
            from .persona import rebuild_persona_from_texts as _rebuild_persona
            _rebuild_persona(_reflection_texts, config.llm_model)
        except Exception:
            pass

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
    documents, _ = load_documents(config.watched_dir, source_type=source_type,
                                   ocr_model=config.image_ocr_model)

    for extra_dir in config.extra_dirs:
        if os.path.isdir(extra_dir):
            extra_docs, _ = load_documents(extra_dir, source_type="library",
                                           ocr_model=config.image_ocr_model)
            documents.extend(extra_docs)

    if not documents:
        raise EmptyDirectoryError(config.watched_dir)

    embeddings = _get_embeddings(config)
    _pc_parent_records: list[tuple[str, str, str]] = []
    if config.semantic_chunking:
        splitter = _get_splitter(config, embeddings, source_type=config.collection_type)
        chunks = splitter.split_documents(documents)
        _prepend_titles(chunks)
        _add_language_metadata(chunks)
    else:
        if config.chunking_strategy == "parent_child":
            chunks = []
            for doc in documents:
                src = doc.metadata.get("source_type", config.collection_type)
                fp = doc.metadata.get("source", "")
                pc = ParentChildChunker(src, fp)
                child_chunks, pr = pc.split_documents([doc])
                chunks.extend(child_chunks)
                _pc_parent_records.extend(pr)
            log.info(
                "create_vectorstore: parent_child — %d child chunks, %d parents",
                len(chunks), len(_pc_parent_records),
            )
        else:
            _splitter_cache: dict[str, RecursiveCharacterTextSplitter] = {}
            chunks = []
            for doc in documents:
                src = doc.metadata.get("source_type", config.collection_type)
                ctype = _chunk_type_for(src, doc.metadata.get("source", ""))
                if ctype not in _splitter_cache:
                    params = CHUNK_PARAMS.get(ctype, CHUNK_PARAMS["document"])
                    _splitter_cache[ctype] = RecursiveCharacterTextSplitter(
                        chunk_size=params["chunk_size"],
                        chunk_overlap=params["chunk_overlap"],
                        separators=params.get("separators", ["\n\n", "\n", "。", "！", "？", ". ", " ", ""]),
                        length_function=len,
                        add_start_index=True,
                    )
                chunks.extend(_splitter_cache[ctype].split_documents([doc]))
        _enrich_chunk_offsets(chunks, documents)
        _prepend_titles(chunks)
        _add_language_metadata(chunks)

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
        chunk_store = ChunkHashStore(config.persist_dir)
        records_by_src: dict[str, list[tuple[str, str, str]]] = {}
        for start in range(0, len(chunks), _BATCH):
            batch = chunks[start : start + _BATCH]
            embs = _embed_batch([c.page_content for c in batch], config.embed_model,
                                truncate_dim=config.embedding_truncate_dim)
            ids = [str(uuid.uuid4()) for _ in batch]
            vs._collection.add(
                ids=ids,
                documents=[c.page_content for c in batch],
                embeddings=embs,
                metadatas=[c.metadata or {} for c in batch],
            )
            for chunk, cid in zip(batch, ids):
                src = chunk.metadata.get("source", "")
                if src:
                    records_by_src.setdefault(src, []).append(
                        (_ch(chunk.page_content), _nh(chunk.page_content), cid)
                    )
            if start + _BATCH < len(chunks):
                time.sleep(_SLEEP)
        for src, recs in records_by_src.items():
            chunk_store.save_file_records(src, recs)
        chunk_store.close()
    except Exception as exc:
        raise IndexBuildError(f"Falha ao criar vectorstore: {exc}") from exc

    if _pc_parent_records:
        try:
            ps = ParentStore(config.persist_dir)
            ps.save_batch(_pc_parent_records)
            ps.close()
            log.info("create_vectorstore: %d parent chunks persistidos", len(_pc_parent_records))
        except Exception as exc:
            log.warning("create_vectorstore: falha ao persistir parent chunks: %s", exc)

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
    docs = load_single_file(file_path, source_type=config.collection_type,
                            ocr_model=config.image_ocr_model)
    if not docs:
        return load_vectorstore(config)

    if config.chunking_strategy == "parent_child":
        pc = ParentChildChunker(config.collection_type, file_path)
        chunks, _pc_pr = pc.split_documents(docs)
        _delete_parent_chunks(config, file_path)
        try:
            ps = ParentStore(config.persist_dir)
            ps.save_batch(_pc_pr)
            ps.close()
            log.debug("index_single_file: %d parent chunks salvos (%s)", len(_pc_pr), file_path)
        except Exception as exc:
            log.warning("index_single_file: falha ao salvar parent chunks: %s", exc)
    else:
        splitter = _get_splitter(config, source_type=config.collection_type, file_path=file_path)
        chunks = splitter.split_documents(docs)
    _enrich_chunk_offsets(chunks, docs)
    _prepend_titles(chunks)
    _add_language_metadata(chunks)

    try:
        os.makedirs(config.persist_dir, exist_ok=True)
        _clear_orphan_wal(config.persist_dir)
        vs = Chroma(
            persist_directory=config.persist_dir,
            embedding_function=_get_embeddings(config),
            collection_metadata={"hnsw:space": "cosine"},
        )
        _BATCH, _SLEEP = _detect_batch_config()
        chunk_store = ChunkHashStore(config.persist_dir)
        bm25_idx = BM25Index.load(config.mnemosyne_dir)
        _incremental_update(vs, bm25_idx, chunk_store, file_path, chunks,
                            config.embed_model, config.embedding_truncate_dim,
                            _BATCH, _SLEEP,
                            node_type_model=config.node_type_model if config.node_type_classification else "")
        chunk_store.close()
    except Exception as exc:
        raise IndexBuildError(f"Falha ao adicionar ao vectorstore: {exc}") from exc

    bm25_idx.save()
    _maybe_enrich(config, file_path, vs)
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
    stats = {"new": 0, "modified": 0, "cosmetic": 0, "deleted": 0, "errors": 0, "reflections": 0}
    bm25_idx = BM25Index.load(config.mnemosyne_dir)
    chunk_store = ChunkHashStore(config.persist_dir)

    # Deletados: remove todos os chunks e reflexões do arquivo e limpa hash store.
    for file_path in deleted_files:
        _delete_file_chunks(vs, file_path)
        bm25_idx.remove_source(file_path)
        chunk_store.delete_file(file_path)
        tracker.remove(file_path)
        _delete_parent_chunks(config, file_path)
        stats["deleted"] += 1

    # Modificados: indexação incremental — só re-embeda chunks que mudaram.
    for file_path, source_type in modified_files:
        try:
            docs = load_single_file(file_path, source_type=source_type,
                                    ocr_model=config.image_ocr_model)
            if config.chunking_strategy == "parent_child":
                pc = ParentChildChunker(source_type, file_path)
                chunks, _pc_pr = pc.split_documents(docs)
                _delete_parent_chunks(config, file_path)
                try:
                    ps = ParentStore(config.persist_dir)
                    ps.save_batch(_pc_pr)
                    ps.close()
                except Exception as _ps_exc:
                    log.warning("update_vectorstore: falha ao salvar parent chunks (mod): %s", _ps_exc)
            else:
                splitter = _get_splitter(config, source_type=source_type, file_path=file_path)
                chunks = splitter.split_documents(docs)
            _enrich_chunk_offsets(chunks, docs)
            _prepend_titles(chunks)
            _add_language_metadata(chunks)
            level = _incremental_update(
                vs, bm25_idx, chunk_store, file_path, chunks,
                config.embed_model, config.embedding_truncate_dim, _BATCH, _SLEEP,
                node_type_model=config.node_type_model if config.node_type_classification else "",
            )
            tracker.mark_indexed(file_path)
            if level == ChangeLevel.COSMETIC:
                stats["cosmetic"] += 1
            else:
                stats["modified"] += 1
                n = _generate_and_index_reflections(
                    {file_path: chunks}, vs, bm25_idx, config, progress_cb
                )
                stats["reflections"] += n
                _maybe_enrich(config, file_path, vs)
        except Exception:
            stats["errors"] += 1

    # Novos
    _lightrag_texts: list[str] = []   # acumulados para inserção async ao final
    _pdf_changed = False              # flag para trigger do RAPTOR
    for file_path, source_type in new_files:
        try:
            docs = load_single_file(file_path, source_type=source_type,
                                    ocr_model=config.image_ocr_model)
            if config.chunking_strategy == "parent_child":
                pc = ParentChildChunker(source_type, file_path)
                chunks, _pc_pr = pc.split_documents(docs)
                _delete_parent_chunks(config, file_path)
                try:
                    ps = ParentStore(config.persist_dir)
                    ps.save_batch(_pc_pr)
                    ps.close()
                except Exception as _ps_exc:
                    log.warning("update_vectorstore: falha ao salvar parent chunks (new): %s", _ps_exc)
            else:
                splitter = _get_splitter(config, source_type=source_type, file_path=file_path)
                chunks = splitter.split_documents(docs)
            _enrich_chunk_offsets(chunks, docs)
            _incremental_update(
                vs, bm25_idx, chunk_store, file_path, chunks,
                config.embed_model, config.embedding_truncate_dim, _BATCH, _SLEEP,
                node_type_model=config.node_type_model if config.node_type_classification else "",
            )
            tracker.mark_indexed(file_path)
            stats["new"] += 1
            n = _generate_and_index_reflections(
                {file_path: chunks}, vs, bm25_idx, config, progress_cb
            )
            stats["reflections"] += n
            _maybe_enrich(config, file_path, vs)
            # LightRAG: acumula texto completo do documento para extração de entidades
            if config.lightrag_enabled:
                _lightrag_texts.append("\n\n".join(c.page_content for c in chunks))
            if str(file_path).lower().endswith(".pdf"):
                _pdf_changed = True
        except Exception:
            stats["errors"] += 1

    # LightRAG: processa inserções acumuladas (sync wrapper — roda no thread do indexer)
    if _lightrag_texts and config.lightrag_enabled and config.indexing_enabled:
        _run_lightrag_inserts(_lightrag_texts, config, progress_cb)

    # RAPTOR: rebuild se algum PDF mudou e o índice não existe ou está desatualizado
    if _pdf_changed and config.raptor_enabled and config.indexing_enabled:
        _schedule_raptor_rebuild(vs, config, progress_cb)

    chunk_store.close()

    bm25_idx.save()
    return vs, stats


def _run_lightrag_inserts(
    texts: list[str],
    config: "AppConfig",
    progress_cb: "Callable[[str], None] | None",
) -> None:
    """Insere textos no LightRAG de forma síncrona (asyncio.run em thread do indexer)."""
    try:
        import asyncio
        from .lightrag_graph import insert_text as _lg_insert

        async def _insert_all() -> None:
            for i, text in enumerate(texts):
                if progress_cb:
                    progress_cb(f"LightRAG: inserindo documento {i + 1}/{len(texts)}…")
                await _lg_insert(text, config)

        asyncio.run(_insert_all())
    except Exception as exc:
        import logging as _log
        _log.getLogger("mnemosyne.indexer").warning("lightrag insert: %s", exc)


def _schedule_raptor_rebuild(
    vs: "Chroma",
    config: "AppConfig",
    progress_cb: "Callable[[str], None] | None",
) -> None:
    """Reconstrói índice RAPTOR de forma síncrona (asyncio.run em thread do indexer)."""
    try:
        import asyncio
        from .raptor_index import build_raptor_index as _build

        asyncio.run(_build(config, vs, progress_cb=progress_cb))
    except Exception as exc:
        import logging as _log
        _log.getLogger("mnemosyne.indexer").warning("raptor rebuild: %s", exc)


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


def load_all_vectorstores(config: AppConfig) -> list[tuple[Chroma, "CollectionConfig"]]:
    """
    Carrega vectorstores de todas as coleções habilitadas com índice no disco.

    Se ecosystem_chroma_dir estiver configurado (índice centralizado), carrega
    apenas esse único vectorstore vinculado à coleção ativa.

    Returns:
        Lista de (Chroma, CollectionConfig). Vazia se nenhum índice existir.
    """
    from .collections import CollectionConfig  # noqa: F401 (type hint only)

    # Índice centralizado: todas as coleções compartilham o mesmo persist_dir
    if config.ecosystem_chroma_dir:
        try:
            vs = load_vectorstore(config)
            if vs._collection.count() == 0:
                # ChromaDB existe mas está vazio — tratar como não-indexado.
                # CRÍTICO: fechar explicitamente antes de retornar; langchain_chroma.Chroma
                # não implementa __del__ com close(), e o SharedSystem do ChromaDB mantém
                # a conexão SQLite viva. Sem close() aqui, um reindex subsequente que
                # apaga e recria o persist_dir no mesmo caminho recebe
                # SQLITE_READONLY_DBMOVED (código 1032) ao tentar escrever.
                try:
                    vs._client.close()
                except Exception:
                    pass
                return []
            active = config.active_coll
            if active:
                return [(vs, active)]
        except VectorstoreNotFoundError:
            pass
        return []

    embeddings = _get_embeddings(config)
    result: list[tuple[Chroma, CollectionConfig]] = []
    for coll in config.collections:
        if not coll.enabled or not coll.exists:
            continue
        persist_dir = coll.persist_dir
        if not persist_dir or not os.path.exists(persist_dir):
            continue
        try:
            _clear_orphan_wal(persist_dir)
            vs = Chroma(
                persist_directory=persist_dir,
                embedding_function=embeddings,
                collection_metadata={"hnsw:space": "cosine"},
            )
            if vs._collection.count() == 0:
                continue
            result.append((vs, coll))
        except Exception:
            pass
    return result


def reindex_transcripts(
    config: AppConfig,
    progress_cb: Callable[[str], None] | None = None,
) -> int:
    """
    Varre watched_dir e extra_dirs, detecta transcrições e re-indexa apenas
    esses arquivos com chunking específico para transcrições (400/60).
    Não requer re-indexação completa do vectorstore.

    Retorna o número de arquivos re-indexados com sucesso.

    Raises:
        VectorstoreNotFoundError: se não houver vectorstore.
    """
    vs = load_vectorstore(config)
    bm25_idx = BM25Index.load(config.mnemosyne_dir)
    chunk_store = ChunkHashStore(config.persist_dir)
    _BATCH, _SLEEP = _detect_batch_config()
    splitter = _get_splitter(config, source_type="transcript")

    dirs: list[tuple[str, str]] = [(config.watched_dir, config.collection_type)]
    for extra_dir in config.extra_dirs:
        if os.path.isdir(extra_dir):
            dirs.append((extra_dir, "library"))

    count = 0
    for directory, src_type in dirs:
        if not os.path.isdir(directory):
            continue
        for root, _, files in os.walk(directory):
            for filename in sorted(files):
                file_path = os.path.join(root, filename)
                if not is_transcript_file(file_path):
                    continue
                try:
                    if progress_cb:
                        progress_cb(f"Transcrição: {filename}")
                    docs = load_single_file(file_path, source_type=src_type,
                                            ocr_model=config.image_ocr_model)
                    chunks = splitter.split_documents(docs)
                    _prepend_titles(chunks)
                    _add_language_metadata(chunks)
                    _incremental_update(
                        vs, bm25_idx, chunk_store, file_path, chunks,
                        config.embed_model, config.embedding_truncate_dim,
                        _BATCH, _SLEEP, node_type_model="",
                    )
                    count += 1
                except Exception:
                    pass

    chunk_store.close()
    bm25_idx.save()
    return count
