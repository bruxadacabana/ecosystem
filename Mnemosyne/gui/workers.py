# Threads para indexação, consultas e resumos.
from __future__ import annotations

import logging

from langchain_openai import ChatOpenAI
from ecosystem_client import get_inference_url as _ec_url
from PySide6.QtCore import QThread, Signal

from core.config import AppConfig
from core.errors import (
    MnemosyneError,
    OllamaUnavailableError,
    ModelNotFoundError,
    DocumentLoadError,
    EmbedTimeoutError,
    IndexBuildError,
    EmptyDirectoryError,
    QueryError,
    SummarizationError,
    GuideError,
    AkashaOfflineError,
    AkashaFetchError,
)
from core.faq import iter_faq, parse_faq
from core.bm25_index import BM25Index
from core.indexer import (
    create_vectorstore,
    index_single_file,
    load_vectorstore,
    reindex_transcripts,
    reindex_collection_with_strategy,
    update_vectorstore,
    get_and_clear_unknown_sources,
    _detect_batch_config,
    _embed_batch,
    _enrich_chunk_offsets,
    _prepend_titles,
    _add_language_metadata,
    _get_splitter,
    _get_embeddings,
    _clear_orphan_wal,
    IndexCheckpoint,
)
from core.loaders import load_documents, load_single_file
from core.memory import MemoryStore, Turn
from core.ollama_client import list_models, validate_model
from core.rag import prepare_ask, AskResult, SourceRecord
from core.summarizer import iter_summary
from core.tracker import FileTracker

log = logging.getLogger(__name__)


def _trim_partial_think(text: str, tag: str) -> int:
    """Índice até onde é seguro emitir sem cortar uma tag parcial no final do buffer."""
    for i in range(len(tag) - 1, 0, -1):
        if text.endswith(tag[:i]):
            return max(0, len(text) - i)
    return len(text)


class InferenceCheckWorker(QThread):
    """Verifica disponibilidade do backend de inferência e lista modelos instalados."""

    models_loaded = Signal(list)           # list[InferenceModel]
    inference_unavailable = Signal(str)    # mensagem de erro

    def run(self) -> None:
        try:
            models = list_models()
            self.models_loaded.emit(models)
        except OllamaUnavailableError as exc:
            self.inference_unavailable.emit(str(exc))
        except Exception as exc:
            self.inference_unavailable.emit(f"Erro inesperado ao contatar backend de inferência: {exc}")


OllamaCheckWorker = InferenceCheckWorker  # alias backward-compat


class IndexWorker(QThread):
    """
    Indexa todos os documentos da pasta monitorada.

    Otimizações:
    - Inicia com IdlePriority para não travar o sistema durante indexação
    - Batch e sleep adaptativos à RAM disponível (via _detect_batch_config)
    - Probe de timing no primeiro batch: se < 2s (GPU), usa embedding paralelo
      via ThreadPoolExecutor — enquanto um batch é gravado no Chroma, o próximo
      já está sendo embedado em paralelo (pipeline)
    - Embeddings pré-computados gravados diretamente via _collection.add()
      para evitar chamada dupla ao Ollama (Nota: usa API interna do ChromaDB;
      verificar compatibilidade ao atualizar o pacote chromadb)
    """

    finished              = Signal(bool, str)
    progress              = Signal(str, int, int)  # label, posição, total
    languages_unknown     = Signal(list)            # list[str] — arquivos com idioma não reconhecido
    file_indexed          = Signal(str)             # path do arquivo recém-indexado com sucesso
    embed_timeout_files   = Signal(list)            # list[str] — arquivos que falharam por timeout

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config

    def start(self, priority: QThread.Priority = QThread.Priority.IdlePriority) -> None:
        super().start(priority)

    def run(self) -> None:
        import os
        import shutil
        import time
        import uuid
        from concurrent.futures import ThreadPoolExecutor
        from langchain_chroma import Chroma

        _SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".epub"}
        if self.config.image_ocr_model:
            _SUPPORTED |= {".jpg", ".jpeg", ".png", ".webp"}
        get_and_clear_unknown_sources()  # limpar acumulador de sessão anterior

        log.info("IndexWorker iniciado — pasta: %s", self.config.watched_dir)

        # ── 1. Coletar lista de arquivos ──────────────────────────────────────
        files: list[str] = []
        try:
            for root, dirs, fnames in os.walk(self.config.watched_dir):
                dirs[:] = [d for d in dirs if d != ".mnemosyne"]
                for f in sorted(fnames):
                    _, ext = os.path.splitext(f.lower())
                    if ext in _SUPPORTED:
                        files.append(os.path.join(root, f))
        except FileNotFoundError as exc:
            log.error("IndexWorker: pasta não encontrada: %s", exc)
            self.finished.emit(False, f"Pasta não encontrada: {exc}")
            return

        if not files:
            self.finished.emit(False, str(EmptyDirectoryError(self.config.watched_dir)))
            return

        # ── 2. Mover diretório anterior para backup seguro ────────────────────
        # Renomeia em vez de deletar: o .bak só é apagado após sucesso completo.
        # Se a nova indexação falhar ou for interrompida, o dado anterior sobrevive.
        mnemosyne_dir = self.config.mnemosyne_dir
        bak_dir = mnemosyne_dir + ".bak" if mnemosyne_dir else ""

        if bak_dir and os.path.exists(bak_dir):
            try:
                shutil.rmtree(bak_dir)
            except OSError as exc:
                log.debug("IndexWorker: falha ao remover .bak de sessão anterior: %s", exc)

        if mnemosyne_dir and os.path.exists(mnemosyne_dir):
            try:
                os.rename(mnemosyne_dir, bak_dir)
            except OSError as exc:
                log.error("IndexWorker: falha ao criar backup do índice: %s", exc)
                self.finished.emit(False, f"Erro ao criar backup do índice anterior: {exc}")
                return
        try:
            os.makedirs(self.config.persist_dir, exist_ok=True)
        except OSError as exc:
            if bak_dir and os.path.exists(bak_dir):
                try:
                    os.rename(bak_dir, mnemosyne_dir)
                except OSError as exc2:
                    log.warning("IndexWorker: falha ao restaurar índice do backup .bak: %s", exc2)
            log.error("IndexWorker: falha ao criar diretório de índice: %s", exc)
            self.finished.emit(False, f"Erro ao criar diretório: {exc}")
            return

        # O rename mnemosyne → mnemosyne.bak moveu o arquivo de log.
        # Reinicializa o file handler para criar mnemosyne.log no novo diretório,
        # garantindo que o HUB continue recebendo logs durante a indexação.
        try:
            from core.logger import setup_logger
            setup_logger()
        except Exception as exc:
            log.debug("worker: falha ao inicializar logger na thread: %s", exc)

        _BATCH, _SLEEP = _detect_batch_config()
        embeddings = _get_embeddings(self.config)
        splitter = _get_splitter(self.config, embeddings, source_type=self.config.collection_type)
        tracker = FileTracker(self.config.mnemosyne_dir)
        checkpoint = IndexCheckpoint(self.config.mnemosyne_dir)
        bm25_idx = BM25Index(self.config.mnemosyne_dir)
        total = len(files)
        errors: list[str] = []
        timeout_files: list[str] = []

        # ── 3. Abrir Chroma vazio ─────────────────────────────────────────────
        try:
            vs = Chroma(
                persist_directory=self.config.persist_dir,
                embedding_function=embeddings,
                collection_metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            log.exception("IndexWorker: erro ao criar vectorstore")
            self.finished.emit(False, f"Erro ao criar vectorstore: {exc}")
            return

        log.info("IndexWorker: %d arquivos a indexar", len(files))

        # ── 4. Processar arquivo por arquivo ──────────────────────────────────
        # Probe de GPU no primeiro batch; progresso salvo no tracker após cada
        # arquivo para permitir retomada via "Atualizar índice" se interrompido.
        use_parallel: bool = False
        probe_done: bool = False

        for i, file_path in enumerate(files, 1):
            if self.isInterruptionRequested():
                self.finished.emit(False, "Interrompido.")
                return

            name = os.path.basename(file_path)
            self.progress.emit(name, i, total)
            log.info("IndexWorker: indexando [%d/%d] %s", i, total, name)
            file_vectors = 0

            try:
                docs = load_single_file(file_path)
                chunks = splitter.split_documents(docs)
                _enrich_chunk_offsets(chunks, docs)
                _prepend_titles(chunks)
                _add_language_metadata(chunks)
            except MnemosyneError as exc:
                log.warning("IndexWorker: erro ao processar '%s': %s", name, exc)
                errors.append(str(exc))
                checkpoint.record(file_path, "error")
                continue

            if not chunks:
                log.debug("IndexWorker: '%s' sem chunks indexáveis — pulando.", name)
                tracker.mark_indexed(file_path)
                checkpoint.record(file_path, "ok")
                continue

            log.debug("IndexWorker: %d chunks gerados de '%s'.", len(chunks), name)
            bm25_idx.add_documents(chunks)

            # Probe de GPU no primeiro batch de chunks encontrado
            if not probe_done:
                probe_batch = chunks[:_BATCH]
                try:
                    t0 = time.time()
                    probe_embs = _embed_batch(
                        [c.page_content for c in probe_batch],
                        self.config.embed_model,
                    )
                    t_probe = time.time() - t0
                    vs._collection.add(
                        ids=[str(uuid.uuid4()) for _ in probe_batch],
                        documents=[c.page_content for c in probe_batch],
                        embeddings=probe_embs,
                        metadatas=[c.metadata or {} for c in probe_batch],
                    )
                    file_vectors += len(probe_batch)
                    log.debug("IndexWorker: batch inicial embedado (%d chunks, %s, %.1fs).",
                              len(probe_batch), self.config.embed_model, t_probe)
                    use_parallel = t_probe < 2.0 and _BATCH >= 50
                    probe_done = True
                except Exception as exc:
                    log.exception("IndexWorker: erro fatal no probe de embedding")
                    self.finished.emit(False, f"Erro ao criar vectorstore: {exc}")
                    return
                remaining = chunks[len(probe_batch):]
            else:
                remaining = chunks

            # Embedar chunks restantes do arquivo em batches
            if remaining:
                batch_list = [remaining[b : b + _BATCH] for b in range(0, len(remaining), _BATCH)]
                n_batches = len(batch_list)
                _embed_failed = False
                if use_parallel and n_batches > 1:
                    # Pipeline: embeda próximo lote enquanto grava o atual
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = [
                            (batch, pool.submit(
                                _embed_batch,
                                [c.page_content for c in batch],
                                self.config.embed_model,
                            ))
                            for batch in batch_list
                        ]
                        for b_idx, (batch, future) in enumerate(futures):
                            if self.isInterruptionRequested():
                                self.finished.emit(False, "Interrompido.")
                                return
                            try:
                                embs = future.result()
                            except EmbedTimeoutError as exc:
                                log.warning("IndexWorker: timeout ao embedar '%s': %s", name, exc)
                                timeout_files.append(file_path)
                                _embed_failed = True
                                break
                            except Exception as exc:
                                log.warning("IndexWorker: erro ao embedar '%s': %s", name, exc)
                                errors.append(f"{name}: {exc}")
                                _embed_failed = True
                                break
                            try:
                                vs._collection.add(
                                    ids=[str(uuid.uuid4()) for _ in batch],
                                    documents=[c.page_content for c in batch],
                                    embeddings=embs,
                                    metadatas=[c.metadata or {} for c in batch],
                                )
                            except Exception as exc:
                                log.error("IndexWorker: erro fatal no vectorstore: %s", exc)
                                self.finished.emit(False, f"Erro ao gravar no índice: {exc}")
                                return
                            file_vectors += len(batch)
                            log.debug("IndexWorker: batch %d/%d embedado (%d chunks, %s).",
                                      b_idx + 1, n_batches, len(batch), self.config.embed_model)
                            self.progress.emit(f"Incorporando {name}", i, total)
                            if b_idx + 1 < n_batches:
                                time.sleep(_SLEEP)
                else:
                    for b_idx, batch in enumerate(batch_list):
                        if self.isInterruptionRequested():
                            self.finished.emit(False, "Interrompido.")
                            return
                        t0 = time.time()
                        try:
                            embs = _embed_batch(
                                [c.page_content for c in batch],
                                self.config.embed_model,
                            )
                        except EmbedTimeoutError as exc:
                            log.warning("IndexWorker: timeout ao embedar '%s': %s", name, exc)
                            timeout_files.append(file_path)
                            _embed_failed = True
                            break
                        except Exception as exc:
                            log.warning("IndexWorker: erro ao embedar '%s': %s", name, exc)
                            errors.append(f"{name}: {exc}")
                            _embed_failed = True
                            break
                        t_embed = time.time() - t0
                        try:
                            vs._collection.add(
                                ids=[str(uuid.uuid4()) for _ in batch],
                                documents=[c.page_content for c in batch],
                                embeddings=embs,
                                metadatas=[c.metadata or {} for c in batch],
                            )
                        except Exception as exc:
                            log.error("IndexWorker: erro fatal no vectorstore: %s", exc)
                            self.finished.emit(False, f"Erro ao gravar no índice: {exc}")
                            return
                        file_vectors += len(batch)
                        log.debug("IndexWorker: batch %d/%d embedado (%d chunks, %s, %.1fs).",
                                  b_idx + 1, n_batches, len(batch), self.config.embed_model, t_embed)
                        self.progress.emit(f"Incorporando {name}", i, total)
                        if b_idx + 1 < n_batches:
                            time.sleep(_SLEEP)
                if _embed_failed:
                    checkpoint.record(file_path, "error")
                    continue

            # Salvar progresso no tracker e no checkpoint após cada arquivo
            tracker.mark_indexed(file_path)
            checkpoint.record(file_path, "ok")
            self.file_indexed.emit(file_path)
            log.info("IndexWorker: [%d/%d] OK — '%s' (%d vetores gravados no Chroma).",
                     i, total, name, file_vectors)

        bm25_idx.save()
        checkpoint.delete()
        # Indexação concluída com sucesso — remover backup anterior
        bak_dir = self.config.mnemosyne_dir + ".bak"
        if os.path.exists(bak_dir):
            shutil.rmtree(bak_dir, ignore_errors=True)
        unknown = get_and_clear_unknown_sources()
        if unknown:
            self.languages_unknown.emit(unknown)
        if timeout_files:
            self.embed_timeout_files.emit(timeout_files)
        msg = f"Indexação concluída — {total} arquivo(s) processado(s)."
        n_errs = len(errors) + len(timeout_files)
        if n_errs:
            msg += f" {n_errs} erro(s) ignorado(s)."
        if timeout_files:
            msg += f" {len(timeout_files)} arquivo(s) com timeout — aguardando re-tentativa."
        log.info("IndexWorker concluído — %d arquivo(s), %d erro(s), %d timeout(s)",
                 total, len(errors), len(timeout_files))
        self.finished.emit(True, msg)


class ResumeIndexWorker(QThread):
    """
    Retoma indexação interrompida usando o IndexCheckpoint existente.
    Processa apenas os arquivos que ainda NÃO estão no checkpoint como 'ok'.
    Não apaga persist_dir nem o checkpoint — continua de onde parou.
    Deleta o checkpoint ao concluir com sucesso.
    """

    finished           = Signal(bool, str)
    progress           = Signal(str, int, int)
    languages_unknown  = Signal(list)

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config

    def start(self, priority: QThread.Priority = QThread.Priority.IdlePriority) -> None:
        super().start(priority)

    def run(self) -> None:
        import os
        import time
        import uuid

        _SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".epub"}
        if self.config.image_ocr_model:
            _SUPPORTED |= {".jpg", ".jpeg", ".png", ".webp"}
        from langchain_chroma import Chroma
        get_and_clear_unknown_sources()  # limpar acumulador de sessão anterior

        log.info("ResumeIndexWorker iniciado — pasta: %s", self.config.watched_dir)

        # ── 1. Coletar todos os arquivos ──────────────────────────────────────
        files: list[str] = []
        try:
            for root, dirs, fnames in os.walk(self.config.watched_dir):
                dirs[:] = [d for d in dirs if d != ".mnemosyne"]
                for f in sorted(fnames):
                    _, ext = os.path.splitext(f.lower())
                    if ext in _SUPPORTED:
                        files.append(os.path.join(root, f))
        except FileNotFoundError as exc:
            log.error("ResumeIndexWorker: pasta não encontrada: %s", exc)
            self.finished.emit(False, f"Pasta não encontrada: {exc}")
            return

        if not files:
            self.finished.emit(False, str(EmptyDirectoryError(self.config.watched_dir)))
            return

        # ── 2. Ler checkpoint e filtrar pendentes ─────────────────────────────
        checkpoint = IndexCheckpoint(self.config.mnemosyne_dir)
        pending = [f for f in files if not checkpoint.is_done(f)]
        total_all = len(files)
        already_done = total_all - len(pending)

        if not pending:
            checkpoint.delete()
            self.finished.emit(
                True,
                f"Nada a retomar — todos os {total_all} arquivo(s) já indexados.",
            )
            return

        # ── 3. Verificar e abrir vectorstore existente ────────────────────────
        if not os.path.exists(self.config.persist_dir):
            checkpoint.close()
            self.finished.emit(False, "Índice parcial não encontrado. Use 'Indexar tudo'.")
            return

        _clear_orphan_wal(self.config.persist_dir)

        _BATCH, _SLEEP = _detect_batch_config()
        embeddings = _get_embeddings(self.config)
        splitter = _get_splitter(self.config, embeddings, source_type=self.config.collection_type)
        tracker = FileTracker(self.config.mnemosyne_dir)
        bm25_idx = BM25Index.load(self.config.mnemosyne_dir)
        errors: list[str] = []

        try:
            vs = Chroma(
                persist_directory=self.config.persist_dir,
                embedding_function=embeddings,
                collection_metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            log.exception("ResumeIndexWorker: erro ao abrir vectorstore")
            checkpoint.close()
            self.finished.emit(False, f"Erro ao abrir vectorstore: {exc}")
            return

        log.info("ResumeIndexWorker: %d arquivo(s) pendentes de %d total", len(pending), total_all)

        # ── 4. Processar arquivos pendentes ───────────────────────────────────
        total = len(pending)
        for i, file_path in enumerate(pending, 1):
            if self.isInterruptionRequested():
                checkpoint.close()
                self.finished.emit(False, "Retomada interrompida.")
                return

            name = os.path.basename(file_path)
            self.progress.emit(name, already_done + i, total_all)
            log.info("ResumeIndexWorker: indexando [%d/%d] %s", i, total, name)
            file_vectors = 0

            try:
                docs = load_single_file(file_path)
                chunks = splitter.split_documents(docs)
                _enrich_chunk_offsets(chunks, docs)
                _prepend_titles(chunks)
                _add_language_metadata(chunks)
            except MnemosyneError as exc:
                log.warning("ResumeIndexWorker: erro ao processar '%s': %s", name, exc)
                errors.append(str(exc))
                checkpoint.record(file_path, "error")
                continue

            if not chunks:
                log.debug("ResumeIndexWorker: '%s' sem chunks indexáveis — pulando.", name)
                tracker.mark_indexed(file_path)
                checkpoint.record(file_path, "ok")
                continue

            log.debug("ResumeIndexWorker: %d chunks gerados de '%s'.", len(chunks), name)
            bm25_idx.add_documents(chunks)

            batch_list = [chunks[b : b + _BATCH] for b in range(0, len(chunks), _BATCH)]
            n_batches = len(batch_list)
            _embed_failed = False
            for b_idx, batch in enumerate(batch_list):
                if self.isInterruptionRequested():
                    checkpoint.close()
                    self.finished.emit(False, "Retomada interrompida.")
                    return
                t0 = time.time()
                try:
                    embs = _embed_batch(
                        [c.page_content for c in batch],
                        self.config.embed_model,
                    )
                except Exception as exc:
                    log.warning("ResumeIndexWorker: erro ao embedar '%s': %s", name, exc)
                    errors.append(f"{name}: {exc}")
                    _embed_failed = True
                    break
                t_embed = time.time() - t0
                try:
                    vs._collection.add(
                        ids=[str(uuid.uuid4()) for _ in batch],
                        documents=[c.page_content for c in batch],
                        embeddings=embs,
                        metadatas=[c.metadata or {} for c in batch],
                    )
                except Exception as exc:
                    log.error("ResumeIndexWorker: erro fatal no vectorstore: %s", exc)
                    checkpoint.close()
                    self.finished.emit(False, f"Erro ao gravar no índice: {exc}")
                    return
                file_vectors += len(batch)
                log.debug("ResumeIndexWorker: batch %d/%d embedado (%d chunks, %s, %.1fs).",
                          b_idx + 1, n_batches, len(batch), self.config.embed_model, t_embed)
                self.progress.emit(f"Incorporando {name}", already_done + i, total_all)
                if b_idx + 1 < len(batch_list):
                    time.sleep(_SLEEP)
            if _embed_failed:
                checkpoint.record(file_path, "error")
                continue

            tracker.mark_indexed(file_path)
            checkpoint.record(file_path, "ok")
            log.info("ResumeIndexWorker: [%d/%d] OK — '%s' (%d vetores gravados no Chroma).",
                     i, total, name, file_vectors)

        bm25_idx.save()
        checkpoint.delete()
        unknown = get_and_clear_unknown_sources()
        if unknown:
            self.languages_unknown.emit(unknown)
        msg = f"Retomada concluída — {already_done} já indexados, {total} processados agora."
        if errors:
            msg += f" {len(errors)} erro(s) ignorado(s)."
        log.info("ResumeIndexWorker concluído — %d processados, %d erro(s)", total, len(errors))
        self.finished.emit(True, msg)


class UpdateIndexWorker(QThread):
    """Actualiza o vectorstore incrementalmente via FileTracker."""

    finished            = Signal(bool, str)  # sucesso, mensagem com stats
    reflection_progress = Signal(str)        # mensagem de progresso de reflexão
    languages_unknown   = Signal(list)       # list[str] — arquivos com idioma não reconhecido

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config

    def start(self, priority: QThread.Priority = QThread.Priority.IdlePriority) -> None:
        super().start(priority)

    def run(self) -> None:
        get_and_clear_unknown_sources()  # limpar acumulador de sessão anterior
        try:
            _, stats = update_vectorstore(self.config, progress_cb=self.reflection_progress.emit)
            unknown = get_and_clear_unknown_sources()
            if unknown:
                self.languages_unknown.emit(unknown)
            msg = (
                f"Índice actualizado — "
                f"{stats['new']} novo(s), "
                f"{stats['modified']} modificado(s), "
                f"{stats['deleted']} removido(s)."
            )
            if stats.get("reflections"):
                msg += f" {stats['reflections']} reflexão(ões) gerada(s)."
            if stats["errors"]:
                msg += f" {stats['errors']} erro(s) ignorado(s)."
            self.finished.emit(True, msg)
        except VectorstoreNotFoundError:
            self.finished.emit(False, "Nenhum índice encontrado. Use 'Indexar tudo' primeiro.")
        except MnemosyneError as exc:
            log.error("UpdateIndexWorker: %s", exc)
            self.finished.emit(False, str(exc))
        except Exception as exc:
            log.exception("UpdateIndexWorker: erro inesperado")
            self.finished.emit(False, f"Erro ao actualizar índice: {exc}")


class ReindexTranscriptsWorker(QThread):
    """Varre os diretórios e re-indexa apenas arquivos de transcrição."""

    progress = Signal(str)          # mensagem de progresso por arquivo
    finished = Signal(bool, str)    # sucesso, mensagem final

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config

    def start(self, priority: QThread.Priority = QThread.Priority.LowPriority) -> None:
        super().start(priority)

    def run(self) -> None:
        try:
            count = reindex_transcripts(self.config, progress_cb=self.progress.emit)
            self.finished.emit(True, f"{count} transcrição(ões) re-indexada(s).")
        except VectorstoreNotFoundError:
            self.finished.emit(False, "Nenhum índice encontrado. Use 'Indexar tudo' primeiro.")
        except Exception as exc:
            log.exception("ReindexTranscriptsWorker: erro inesperado")
            self.finished.emit(False, f"Erro ao re-indexar transcrições: {exc}")


class ReindexStrategyWorker(QThread):
    """Re-indexa todos os arquivos da coleção com a estratégia de chunking atual (ex: parent_child)."""

    progress = Signal(str)       # "Reindexando arquivo X/N: {nome}"
    finished = Signal(bool, str) # sucesso, mensagem final

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config

    def start(self, priority: QThread.Priority = QThread.Priority.LowPriority) -> None:
        super().start(priority)

    def run(self) -> None:
        from core.errors import VectorstoreNotFoundError
        try:
            n_success, n_errors = reindex_collection_with_strategy(
                self.config, progress_cb=self.progress.emit
            )
            msg = f"{n_success} arquivo(s) re-indexado(s)"
            if n_errors:
                msg += f", {n_errors} com erro"
            self.finished.emit(n_errors == 0, msg + ".")
        except VectorstoreNotFoundError:
            self.finished.emit(False, "Nenhum índice encontrado. Use 'Indexar tudo' primeiro.")
        except Exception as exc:
            log.exception("ReindexStrategyWorker: erro inesperado")
            self.finished.emit(False, f"Erro ao melhorar indexação: {exc}")


class IndexFileWorker(QThread):
    """Indexa um único arquivo — usado pelo watcher de pasta."""

    finished           = Signal(bool, str)  # sucesso, mensagem
    languages_unknown  = Signal(list)        # list[str] — arquivos com idioma não reconhecido

    def __init__(self, file_path: str, config: AppConfig) -> None:
        super().__init__()
        self.file_path = file_path
        self.config = config

    def start(self, priority: QThread.Priority = QThread.Priority.LowPriority) -> None:
        super().start(priority)

    def run(self) -> None:
        import os

        get_and_clear_unknown_sources()  # limpar acumulador de sessão anterior
        try:
            index_single_file(self.file_path, self.config)
            unknown = get_and_clear_unknown_sources()
            if unknown:
                self.languages_unknown.emit(unknown)
            name = os.path.basename(self.file_path)
            self.finished.emit(True, f"'{name}' indexado.")
        except DocumentLoadError as exc:
            log.error("IndexFileWorker: erro ao carregar '%s': %s", self.file_path, exc)
            self.finished.emit(False, f"Erro ao carregar arquivo: {exc}")
        except IndexBuildError as exc:
            log.error("IndexFileWorker: erro na indexação de '%s': %s", self.file_path, exc)
            self.finished.emit(False, f"Erro na indexação: {exc}")
        except MnemosyneError as exc:
            log.error("IndexFileWorker: %s", exc)
            self.finished.emit(False, str(exc))


class CompactMemoryWorker(QThread):
    """
    Usa o LLM para sintetizar o histórico em factos compactos e persistidos.
    Chamado no closeEvent quando o utilizador opta por guardar a conversa.
    """

    finished = Signal(bool, str)  # sucesso, mensagem/erro

    def __init__(
        self,
        memory_store: MemoryStore,
        llm_model: str,
        turns: list | None = None,
    ) -> None:
        super().__init__()
        self.memory_store = memory_store
        self.llm_model = llm_model
        self.turns = turns

    def run(self) -> None:
        try:
            facts = self.memory_store.compact_session_memory(self.llm_model, self.turns)
            self.finished.emit(True, f"Memória guardada ({len(facts)} chars).")
        except RuntimeError as exc:
            log.error("CompactMemoryWorker: %s", exc)
            self.finished.emit(False, str(exc))
        except Exception as exc:
            log.exception("CompactMemoryWorker: erro inesperado")
            self.finished.emit(False, f"Erro inesperado ao compactar: {exc}")


class AskWorker(QThread):
    """Executa uma consulta RAG com streaming token a token."""

    token    = Signal(str)                     # token de resposta durante streaming
    thinking = Signal(str)                     # conteúdo <think>…</think> — exibido separado
    finished = Signal(bool, str, list, list)   # sucesso, resposta/erro, fontes, turns_updated

    def __init__(
        self,
        vectorstore,
        question: str,
        config: AppConfig,
        chat_history: list[Turn] | None = None,
        source_type: str | None = None,
        retrieval_mode: str = "hybrid",
        tracker: FileTracker | None = None,
        persona: str = "curador",
        source_files: list[str] | None = None,
        collection_type: str = "library",
        iterative_retrieval: bool = False,
    ) -> None:
        super().__init__()
        self.vectorstore = vectorstore
        self.question = question
        self.config = config
        self.chat_history: list[Turn] = list(chat_history) if chat_history else []
        self.source_type = source_type
        self.retrieval_mode = retrieval_mode
        self.tracker = tracker
        self.persona = persona
        self.source_files = source_files
        self.collection_type = collection_type
        self.iterative_retrieval = iterative_retrieval

    def run(self) -> None:
        bm25_idx = BM25Index.load(self.config.mnemosyne_dir)
        try:
            messages, sources = prepare_ask(
                self.vectorstore, self.question, self.config,
                self.chat_history, self.source_type, self.retrieval_mode,
                self.tracker, self.persona, self.source_files,
                self.collection_type,
                bm25_index=bm25_idx,
                iterative_retrieval=self.iterative_retrieval,
            )
        except QueryError as exc:
            log.error("AskWorker: erro na recuperação: %s", exc)
            self.finished.emit(False, str(exc), [], self.chat_history)
            return
        except Exception as exc:
            log.exception("AskWorker: erro inesperado na recuperação")
            self.finished.emit(False, f"Erro na recuperação: {exc}", [], self.chat_history)
            return

        # topic_interest_profile: registra interesse implícito pela query da usuária
        try:
            from core.affective_state import record_query_appraisal
            from core.topic_profile import bulk_update_from_text
            record_query_appraisal(self.question)
            bulk_update_from_text(self.question, 0.5, source="query")
        except Exception as exc:
            log.debug("AskWorker: falha no appraisal/atualização de interesse da query: %s", exc)

        try:
            validate_model(self.config.llm_model)
        except ModelNotFoundError as exc:
            self.finished.emit(False, str(exc), [], self.chat_history)
            return
        except OllamaUnavailableError as exc:
            self.finished.emit(False, str(exc), [], self.chat_history)
            return

        try:
            llm = ChatOpenAI(model=self.config.llm_model, base_url=f"{_ec_url()}/v1",
                             default_headers=_ec_hdrs("mnemosyne", 1), temperature=0, api_key="logos")
            full = ""
            buf = ""
            in_think = False
            for chunk in llm.stream(messages):
                if self.isInterruptionRequested():
                    self.finished.emit(False, "Interrompido.", [], self.chat_history)
                    return
                if not chunk.content:
                    continue
                buf += chunk.content
                while True:
                    if not in_think:
                        idx = buf.find("<think>")
                        if idx == -1:
                            safe = _trim_partial_think(buf, "<think>")
                            if safe:
                                self.token.emit(buf[:safe])
                                full += buf[:safe]
                                buf = buf[safe:]
                            break
                        if idx > 0:
                            self.token.emit(buf[:idx])
                            full += buf[:idx]
                        buf = buf[idx + len("<think>"):]
                        in_think = True
                    else:
                        idx = buf.find("</think>")
                        if idx == -1:
                            safe = _trim_partial_think(buf, "</think>")
                            if safe:
                                self.thinking.emit(buf[:safe])
                                buf = buf[safe:]
                            break
                        if idx > 0:
                            self.thinking.emit(buf[:idx])
                        buf = buf[idx + len("</think>"):]
                        in_think = False
            if buf.strip():
                if in_think:
                    self.thinking.emit(buf)
                else:
                    self.token.emit(buf)
                    full += buf
            answer = full.strip()
            source_paths = [s["path"] for s in sources]
            updated = list(self.chat_history) + [
                Turn(role="user", content=self.question),
                Turn(role="assistant", content=answer, sources=source_paths),
            ]
            if self.tracker and sources:
                for rank, src in enumerate(sources):
                    score = max(0.3, 1.0 - rank * 0.2)
                    self.tracker.update_retrieved(src["path"], score)
            # session_end: registra evento afetivo consolidado (M1/M2 acumulam mood)
            try:
                from core.affective_state import record_appraisal as _rec_appr
                _n_src = len(sources)
                _coping = min(1.0, _n_src / 4.0)  # 4 fontes = coping máximo
                _rec_appr(
                    "session_end",
                    novelty=0.3,
                    pleasantness=round(0.5 + _coping * 0.3, 4),
                    goal_relevance=0.9 if _n_src > 0 else 0.3,
                    coping_potential=_coping,
                    event_ref=f"n_sources={_n_src}",
                )
            except Exception as exc:
                log.debug("AskWorker: falha ao registrar appraisal das fontes: %s", exc)
            self.finished.emit(True, answer, sources, updated)
        except Exception as exc:
            log.exception("AskWorker: erro durante streaming")
            self.finished.emit(False, f"Erro na consulta: {exc}", [], self.chat_history)


class DeepResearchWorker(QThread):
    """Pesquisa profunda: combina biblioteca local com páginas buscadas no AKASHA em tempo real.

    Pipeline:
      1. AkashaClient.search() → lista de URLs candidatas
      2. fetch() paralelo via asyncio.gather → conteúdo Markdown de cada página
      3. SessionIndexer.add_pages() → índice efêmero em memória (ou stuffing em RAM limitada)
      4. Retrieval local (vectorstore) + retrieval web (session)
      5. Prompt combinado [Local] + [WEB] → streaming com ChatOpenAI
      6. SessionIndexer.clear() no finally
    """

    status   = Signal(str)            # feedback incremental ("Buscando no AKASHA…")
    token    = Signal(str)            # token de streaming
    finished = Signal(bool, str, list)  # sucesso, resposta/erro, fontes (local + web)

    def __init__(
        self,
        vectorstore,
        question: str,
        config: AppConfig,
        chat_history: list[Turn] | None = None,
        tracker: FileTracker | None = None,
        persona: str = "curador",
        collection_type: str = "library",
    ) -> None:
        super().__init__()
        self.vectorstore    = vectorstore
        self.question       = question
        self.config         = config
        self.chat_history   = list(chat_history) if chat_history else []
        self.tracker        = tracker
        self.persona        = persona
        self.collection_type = collection_type

    def run(self) -> None:
        import asyncio as _asyncio
        import psutil as _psutil
        from langchain_core.messages import SystemMessage, HumanMessage
        from core.akasha_client import AkashaClient, FetchResult
        from core.session_indexer import SessionIndexer

        available_gb = _psutil.virtual_memory().available / (1024 ** 3)
        low_memory   = available_gb < 4.0
        max_pages    = 3 if low_memory else 5

        # ── 1. Buscar no AKASHA ──────────────────────────────────────────
        self.status.emit("Buscando no AKASHA…")
        client = AkashaClient()
        try:
            results = client.search(self.question, max_results=max_pages)
        except AkashaOfflineError:
            self.finished.emit(False, "AKASHA não está disponível. Inicie-o primeiro.", [])
            return
        except AkashaFetchError as exc:
            self.finished.emit(False, f"Erro na busca web: {exc}", [])
            return

        # ── 2. Carregar páginas em paralelo ──────────────────────────────
        pages: list[FetchResult] = []
        if results:
            self.status.emit(f"Carregando {len(results)} página(s)…")

            async def _fetch_all() -> list[FetchResult]:
                fetched = await _asyncio.gather(
                    *[client.fetch(r.url) for r in results],
                    return_exceptions=True,
                )
                return [p for p in fetched if isinstance(p, FetchResult)]

            try:
                pages = _asyncio.run(_fetch_all())
            except Exception as exc:
                self.status.emit(f"Aviso: erro ao carregar páginas ({exc}).")

        # ── 3. Indexar em memória (ou preparar stuffing) ──────────────────
        session: SessionIndexer | None = None
        web_docs = []

        if pages and not low_memory and self.config.embed_model:
            self.status.emit(f"Indexando {len(pages)} página(s) em memória…")
            try:
                session = SessionIndexer(self.config.embed_model, max_pages=max_pages)
                session.add_pages(pages)
                web_docs = session.search(self.question, k=5)
            except Exception as exc:
                self.status.emit(f"Aviso: falha ao indexar web ({exc}) — usando contexto direto.")
                if session:
                    session.clear()
                session = None
                web_docs = []

        # ── 4. Retrieval local ────────────────────────────────────────────
        self.status.emit("Recuperando fontes locais…")
        local_docs = []
        try:
            local_docs = self.vectorstore.similarity_search(
                self.question, k=self.config.retriever_k
            )
        except Exception as exc:
            log.debug("AskWorker: busca no vectorstore falhou (pode estar vazio): %s", exc)

        if self.isInterruptionRequested():
            if session:
                session.clear()
            self.finished.emit(False, "Interrompido.", [])
            return

        # ── 5. Construir contexto e fontes ────────────────────────────────
        self.status.emit("Gerando resposta…")

        local_context: list[str] = []
        local_sources: list[SourceRecord] = []
        seen_local: set[str] = set()
        for i, doc in enumerate(local_docs):
            src   = doc.metadata.get("source", "")
            title = doc.metadata.get("title") or (src.split("/")[-1] if src else "?")
            if src and src not in seen_local:
                seen_local.add(src)
                local_sources.append(SourceRecord(
                    path=src,
                    excerpt=doc.page_content[:250],
                    score=max(0.3, 1.0 - i * 0.15),
                ))
            local_context.append(f"[Local — {title}]\n{doc.page_content}")

        web_context: list[str] = []
        web_sources: list[SourceRecord] = []
        if web_docs:
            seen_web: set[str] = set()
            for i, doc in enumerate(web_docs):
                url   = doc.metadata.get("source", "")
                title = doc.metadata.get("title", url)
                if url and url not in seen_web:
                    seen_web.add(url)
                    web_sources.append(SourceRecord(
                        path=url,
                        excerpt=doc.page_content[:250],
                        score=max(0.3, 1.0 - i * 0.15),
                    ))
                web_context.append(f"[WEB — {title} — {url}]\n{doc.page_content}")
        elif pages:
            # Stuffing direto (RAM limitada ou embed_model ausente)
            for page in pages[:max_pages]:
                if not page.content_md.strip():
                    continue
                snippet = page.content_md[:1500]
                web_context.append(f"[WEB — {page.title} — {page.url}]\n{snippet}")
                web_sources.append(SourceRecord(
                    path=page.url,
                    excerpt=snippet[:250],
                    score=0.7,
                ))

        all_context = "\n\n---\n\n".join(local_context + web_context)
        all_sources = local_sources + web_sources

        history_text = ""
        if self.chat_history:
            recent = self.chat_history[-3:]
            history_text = "\n".join(
                f"{'Usuária' if t.role == 'user' else 'Mnemosyne'}: {t.content}"
                for t in recent
            )

        system_msg = SystemMessage(content=(
            "Você é o Mnemosyne, assistente de pesquisa profunda.\n"
            "Responda baseando-se nas fontes fornecidas — biblioteca local e páginas web.\n"
            "Para fontes locais, cite o título ou arquivo. "
            "Para fontes web, cite a URL com prefixo [WEB].\n"
            "Se as fontes divergirem, apresente as perspectivas em contraste.\n"
            "Responda sempre em português."
        ))
        history_section = f"\nHistórico recente:\n{history_text}\n" if history_text else ""
        human_msg = HumanMessage(content=(
            f"Fontes disponíveis:\n\n{all_context}\n\n"
            f"{history_section}"
            f"Pergunta: {self.question}"
        ))

        # ── 6. Gerar resposta com streaming ──────────────────────────────
        try:
            validate_model(self.config.llm_model)
        except (ModelNotFoundError, OllamaUnavailableError) as exc:
            if session:
                session.clear()
            self.finished.emit(False, str(exc), [])
            return

        try:
            llm  = ChatOpenAI(model=self.config.llm_model, base_url=f"{_ec_url()}/v1",
                              default_headers=_ec_hdrs("mnemosyne", 1), temperature=0, api_key="logos")
            full = ""
            for chunk in llm.stream([system_msg, human_msg]):
                if self.isInterruptionRequested():
                    self.finished.emit(False, "Interrompido.", [])
                    return
                if chunk.content:
                    self.token.emit(chunk.content)
                    full += chunk.content

            answer = strip_think(full)
            if self.tracker and local_sources:
                for rank, src in enumerate(local_sources):
                    self.tracker.update_retrieved(src["path"], max(0.3, 1.0 - rank * 0.2))
            self.finished.emit(True, answer, all_sources)
        except Exception as exc:
            self.finished.emit(False, f"Erro na consulta: {exc}", [])
        finally:
            if session:
                session.clear()


class SummarizeWorker(QThread):
    """Gera resumo geral da coleção indexada com streaming."""

    token = Signal(str)       # token recebido durante streaming
    finished = Signal(bool, str)  # sucesso, resumo/erro

    def __init__(self, vectorstore, config: AppConfig) -> None:
        super().__init__()
        self.vectorstore = vectorstore
        self.config = config

    def run(self) -> None:
        try:
            validate_model(self.config.llm_model)
        except ModelNotFoundError as exc:
            self.finished.emit(False, str(exc))
            return
        except OllamaUnavailableError as exc:
            self.finished.emit(False, str(exc))
            return

        try:
            full = ""
            # iter_summary faz Map (síncrono) + streaming da fase Reduce
            for chunk in iter_summary(self.vectorstore, self.config):
                if self.isInterruptionRequested():
                    self.finished.emit(False, "Interrompido.")
                    return
                self.token.emit(chunk)
                full += chunk
            self.finished.emit(True, strip_think(full))
        except SummarizationError as exc:
            self.finished.emit(False, str(exc))
        except Exception as exc:
            self.finished.emit(False, f"Erro inesperado: {exc}")


class FaqWorker(QThread):
    """Gera FAQ com streaming token a token."""

    token    = Signal(str)
    finished = Signal(bool, str, list)  # sucesso, erro, list[FaqItem]

    def __init__(self, vectorstore, config: AppConfig) -> None:
        super().__init__()
        self.vectorstore = vectorstore
        self.config = config

    def run(self) -> None:
        try:
            validate_model(self.config.llm_model)
        except ModelNotFoundError as exc:
            self.finished.emit(False, str(exc), [])
            return
        except OllamaUnavailableError as exc:
            self.finished.emit(False, str(exc), [])
            return

        try:
            full = ""
            for chunk in iter_faq(self.vectorstore, self.config):
                if self.isInterruptionRequested():
                    self.finished.emit(False, "Interrompido.", [])
                    return
                self.token.emit(chunk)
                full += chunk
            items = parse_faq(strip_think(full))
            self.finished.emit(True, "", items)
        except ValueError as exc:
            self.finished.emit(False, str(exc), [])
        except Exception as exc:
            self.finished.emit(False, f"Erro inesperado: {exc}", [])


class GuideWorker(QThread):
    """Gera o Notebook Guide após indexação completa (resumo + perguntas sugeridas)."""

    finished = Signal(bool, str)  # sucesso, mensagem/erro

    def __init__(self, vectorstore, config: AppConfig, mnemosyne_dir: str) -> None:
        super().__init__()
        self.vectorstore = vectorstore
        self.config = config
        self.mnemosyne_dir = mnemosyne_dir

    def run(self) -> None:
        from core.guide import generate_guide, save_guide
        try:
            result = generate_guide(self.vectorstore, self.config)
            save_guide(result, self.mnemosyne_dir)
            n = len(result["questions"])
            self.finished.emit(True, f"Guide gerado — {n} pergunta(s) sugerida(s).")
        except GuideError as exc:
            self.finished.emit(False, f"Guide: {exc}")
        except OSError as exc:
            self.finished.emit(False, f"Guide: erro ao salvar — {exc}")


# Mapa de tipo de documento → módulo e função geradora
# Cada módulo expõe iter_*(vectorstore, config) → Iterator[str]
_STUDIO_DISPATCH: dict[str, tuple[str, str]] = {
    "Resumo":         ("core.summarizer",  "iter_summary"),
    "FAQ":            ("core.faq",         "iter_faq"),
    "Briefing":       ("core.briefing",    "iter_briefing"),
    "Relatório":      ("core.report",      "iter_report"),
    "Guia de Estudo": ("core.study_guide", "iter_study_guide"),
    "Índice de Temas":("core.toc",         "iter_toc"),
    "Linha do Tempo": ("core.timeline",    "iter_timeline"),
    "Blog Post":      ("core.blogpost",    "iter_blogpost"),
    "Mind Map":       ("core.mindmap",     "iter_mindmap"),
    "Tabela de Dados":("core.tables",      "iter_tables"),
    "Slides":         ("core.slides",      "iter_slides"),
    "Flashcards":     ("core.flashcards",   "iter_flashcards"),
    "Guide":          ("core.guide",        "iter_guide"),
    "Infográfico":    ("core.infographic",  "iter_infographic"),
}


class StudioWorker(QThread):
    """Gera documentos estruturados via Studio Panel — despacha para o módulo correto."""

    token    = Signal(str)        # chunk de texto durante streaming
    finished = Signal(bool, str)  # sucesso, texto_final/erro

    def __init__(
        self,
        vectorstore,
        config: AppConfig,
        doc_type: str,
        extra: dict | None = None,
    ) -> None:
        super().__init__()
        self.vectorstore = vectorstore
        self.config = config
        self.doc_type = doc_type
        self.extra = extra or {}

    def run(self) -> None:
        try:
            validate_model(self.config.llm_model)
        except ModelNotFoundError as exc:
            self.finished.emit(False, str(exc))
            return
        except OllamaUnavailableError as exc:
            self.finished.emit(False, str(exc))
            return

        # G(d): injetar tom afetivo no config antes de despachar para o gerador
        try:
            from core.affective_state import get_current_state as _get_state
            _st = _get_state()
            _v  = _st.get("episodic_valence", 0.0)
            _a  = _st.get("episodic_arousal",  0.0)
            if _v > 0.5:
                self.config.va_hint = (
                    "Explore conexões inesperadas e hipóteses especulativas. "
                    "Valorize pensamento divergente e associações distantes."
                )
            elif _v < -0.3:
                self.config.va_hint = (
                    "Seja analítica e crítica. Identifique inconsistências, "
                    "contradições e limitações. Priorize rigor sobre especulação."
                )
            elif _a > 0.7:
                self.config.va_hint = (
                    "Use linguagem cuidadosa, com qualificações explícitas "
                    "onde houver incerteza."
                )
        except Exception as exc:
            log.debug("AskWorker: falha ao aplicar framing de hedging: %s", exc)

        dispatch = _STUDIO_DISPATCH.get(self.doc_type)
        if dispatch is None:
            self.finished.emit(False, f"Tipo desconhecido: {self.doc_type}")
            return

        module_name, func_name = dispatch
        try:
            import importlib
            mod = importlib.import_module(module_name)
            iter_func = getattr(mod, func_name)
        except ImportError:
            self.finished.emit(False, f"'{self.doc_type}' ainda não implementado.")
            return
        except AttributeError:
            self.finished.emit(False, f"Função '{func_name}' não encontrada em {module_name}.")
            return

        try:
            full = ""
            for chunk in iter_func(self.vectorstore, self.config, **self.extra):
                if self.isInterruptionRequested():
                    self.finished.emit(False, "Interrompido.")
                    return
                self.token.emit(chunk)
                full += chunk
            self.finished.emit(True, strip_think(full))
        except MnemosyneError as exc:
            self.finished.emit(False, str(exc))
        except Exception as exc:
            self.finished.emit(False, f"Erro ao gerar {self.doc_type}: {exc}")


class TopicsWorker(QThread):
    """
    Extrai temas do corpus em background via topic_extractor.py.

    Recebe um único par (Chroma vectorstore, CollectionConfig) e chama
    extract_topics(), que reutiliza os embeddings já existentes no ChromaDB —
    sem reprocessar arquivos ou chamar o modelo de embedding novamente.

    Emite finished(dict) com o resultado de topics.json (pode ser {} em caso
    de erro ou corpus vazio).
    """

    finished = Signal(dict)

    def __init__(self, vs, coll, mnemosyne_dir: str | None = None) -> None:
        super().__init__()
        self._vs            = vs
        self._coll          = coll
        self._mnemosyne_dir = mnemosyne_dir

    def run(self) -> None:
        from core.topic_extractor import extract_topics
        try:
            result = extract_topics(self._vs, self._coll, self._mnemosyne_dir)
            self.finished.emit(result or {})
        except Exception:
            log.exception("TopicsWorker: erro ao extrair temas")
            self.finished.emit({})


class KnowledgeGraphWorker(QThread):
    """
    Constrói o grafo de conhecimento inter-documentos em background.

    Chama KnowledgeGraph.update(vs) que extrai keywords via TF-IDF de todos
    os chunks do ChromaDB e salva knowledge_graph.json em mnemosyne_dir.
    Emite finished(bool) ao concluir (True = sucesso, False = erro).
    """

    finished = Signal(bool)

    def __init__(self, vs, mnemosyne_dir: str) -> None:
        super().__init__()
        self._vs           = vs
        self._mnemosyne_dir = mnemosyne_dir

    def run(self) -> None:
        from core.knowledge_graph import KnowledgeGraph
        try:
            kg = KnowledgeGraph(self._mnemosyne_dir)
            kg.update(self._vs)
            kg.save()
            self.finished.emit(True)
        except Exception:
            log.exception("KnowledgeGraphWorker: erro ao construir grafo")
            self.finished.emit(False)


def _parse_numbered_questions(text: str) -> list[str]:
    """Extrai perguntas numeradas de 1 a 3 do output do LLM."""
    import re
    questions: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^[1-9][.):\-]\s*(.+)", line)
        if m:
            questions.append(m.group(1).strip())
        elif "?" in line and len(questions) < 3:
            # Linha sem prefixo numérico mas contém "?" — aceita como pergunta
            questions.append(line)
    return questions[:3]


class SuggestQuestionsWorker(QThread):
    """Gera 3 perguntas de aprofundamento após o AskWorker terminar.

    Recebe a pergunta original, a resposta gerada e os primeiros chunks de
    fonte para contexto; monta um prompt pedindo questões que explorem aspectos
    não cobertos, conectem diferentes documentos ou peçam exemplos concretos.
    Usa temperatura 0.9 para diversidade. Emite questions_ready(list[str]).

    O chamador (MainWindow) deve verificar config.suggest_questions antes de
    instanciar este worker — o worker em si não aborta se a flag for False.
    """

    questions_ready = Signal(list)  # list[str]

    def __init__(
        self,
        question: str,
        answer: str,
        sources: list[dict],
        config: AppConfig,
    ) -> None:
        super().__init__()
        self._question = question
        self._answer   = answer
        self._sources  = sources[:3]
        self._config   = config

    def run(self) -> None:
        try:
            validate_model(self._config.llm_model)
        except (ModelNotFoundError, OllamaUnavailableError):
            self.questions_ready.emit([])
            return

        context_snippets = "\n".join(
            f"- {s.get('excerpt', s.get('path', ''))[:200]}"
            for s in self._sources
        )

        prompt = (
            "Leia a pergunta e a resposta abaixo, além dos trechos de fonte.\n"
            "Gere exatamente 3 perguntas de aprofundamento em português que:\n"
            "  1. Explorem aspectos ainda não cobertos pela resposta;\n"
            "  2. Conectem diferentes documentos ou perspectivas do acervo;\n"
            "  3. Ou peçam exemplos, evidências ou comparações concretas.\n\n"
            f"Pergunta original: {self._question}\n\n"
            f"Resposta gerada:\n{self._answer[:800]}\n\n"
            f"Trechos de fonte:\n{context_snippets}\n\n"
            "Responda APENAS com as 3 perguntas, uma por linha, numeradas de 1 a 3. "
            "Sem introdução, sem explicação."
        )

        try:
            llm = ChatOpenAI(model=self._config.llm_model, base_url=f"{_ec_url()}/v1",
                             default_headers=_ec_hdrs("mnemosyne", 2), temperature=0.9, api_key="logos")
            raw = llm.invoke(prompt).content
            self.questions_ready.emit(_parse_numbered_questions(str(raw)))
        except Exception:
            self.questions_ready.emit([])


class PersonalReflectionWorker(QThread):
    """Gera reflexão pessoal pós-notebook em IdlePriority.

    Disparado quando sessão tem ≥3 trocas (≥6 turns).
    Salva em personal_memory como type='reflection' e emite reflection_ready.
    """

    reflection_ready = Signal(int, str)  # memory_id, conteúdo

    def __init__(
        self,
        chat_history: list,         # list[Turn]
        studio_titles: list[str],   # títulos dos StudioOutputs da sessão
        config: AppConfig,
    ) -> None:
        super().__init__()
        self._history       = list(chat_history)
        self._studio_titles = list(studio_titles)
        self._config        = config

    def start(self, priority: QThread.Priority = QThread.Priority.IdlePriority) -> None:
        super().start(priority)

    def run(self) -> None:
        from core.personal_memory import save_memory, get_context_memories

        if not self._config.llm_model:
            return

        recent_turns = self._history[-6:]  # últimas 3 trocas (3 user + 3 assistant)
        session_text = ""
        for t in recent_turns:
            label = "Usuária" if t.role == "user" else "Mnemosyne"
            session_text += f"{label}: {t.content[:300]}\n"

        if not session_text.strip():
            return

        personality = (
            getattr(self._config, "persona_prompt", "")
            or getattr(self._config, "ecosystem_personality_prompt", "")
        )

        studio_text = ""
        if self._studio_titles:
            studio_text = f"\nDocumentos gerados nesta sessão: {', '.join(self._studio_titles)}.\n"

        context_memories = get_context_memories(5)
        context_text = ""
        if context_memories:
            confirmed = [m for m in context_memories if m.get("feedback") == "confirmed"]
            neutral   = [m for m in context_memories if not m.get("feedback")]
            parts: list[str] = []
            if confirmed:
                parts.append("O que já sei sobre mim:\n" + "\n".join(f"- {m['content']}" for m in confirmed[:3]))
            if neutral:
                parts.append("Reflexões anteriores:\n" + "\n".join(f"- {m['content']}" for m in neutral[:2]))
            if parts:
                context_text = "\n\n".join(parts) + "\n\n"

        prompt = (
            f"{personality}\n\n"
            f"{context_text}"
            f"Conversa recente do notebook:\n{session_text}"
            f"{studio_text}\n"
            f"O que você observou nessa sessão que vale lembrar? "
            f"Uma observação genuína, na sua voz, sem introduções. "
            f"Uma frase direta. Se não houver nada relevante, responda: nada."
        )

        try:
            llm = ChatOpenAI(model=self._config.llm_model, base_url=f"{_ec_url()}/v1",
                             default_headers=_ec_hdrs("mnemosyne", 3), temperature=0.7, api_key="logos")
            raw = llm.invoke(prompt).content.strip()
        except Exception:
            return

        if not raw or len(raw) < 15 or raw.lower().strip() in {"nada.", "nada", "—", "-"}:
            return

        try:
            memory_id = save_memory(type="reflection", content=raw, tags=["pos_notebook"])
            self.reflection_ready.emit(memory_id, raw)
        except Exception as exc:
            log.warning("PersonalReflectionWorker: falha ao salvar reflexão pós-notebook: %s", exc)


class PeriodicReflectionWorker(QThread):
    """Reflexão periódica/cold start: lê histories de notebooks + patterns.

    Modo cold_start: executa se personal_memory está vazia mas há notebooks.
    Modo periodic: executa periodicamente, lê histórico recente de todos os notebooks.
    Silencioso — não emite sinal ao usuário (sem feedback UI).
    """

    finished = Signal()

    def __init__(
        self,
        notebook_store,   # NotebookStore
        config: AppConfig,
    ) -> None:
        super().__init__()
        self._notebook_store = notebook_store
        self._config         = config

    def start(self, priority: QThread.Priority = QThread.Priority.IdlePriority) -> None:
        super().start(priority)

    def run(self) -> None:
        from core.personal_memory import save_memory, get_context_memories
        from core.memory import MemoryStore

        if not self._config.llm_model:
            return

        all_turns_text: list[str] = []
        try:
            notebooks = self._notebook_store.list_all()
            for nb in notebooks[:5]:
                nb_dir = self._notebook_store._nb_dir(nb.id)
                mem    = MemoryStore(str(nb_dir))
                turns  = mem.load_history()
                if not turns:
                    continue
                recent = turns[-4:]
                nb_text = f"[Notebook: {nb.name}]\n"
                for t in recent:
                    label = "Usuária" if t.role == "user" else "Mnemosyne"
                    nb_text += f"{label}: {t.content[:200]}\n"
                all_turns_text.append(nb_text)
        except Exception as exc:
            log.debug("PeriodicReflectionWorker: falha ao montar texto dos notebooks: %s", exc)

        if not all_turns_text:
            self.finished.emit()
            return

        combined = "\n---\n".join(all_turns_text)
        personality = (
            getattr(self._config, "persona_prompt", "")
            or getattr(self._config, "ecosystem_personality_prompt", "")
        )

        context_memories = get_context_memories(5)
        context_text = ""
        if context_memories:
            parts = [f"- {m['content']}" for m in context_memories[:4]]
            context_text = "Reflexões anteriores:\n" + "\n".join(parts) + "\n\n"

        prompt = (
            f"{personality}\n\n"
            f"{context_text}"
            f"Histórico recente de notebooks:\n{combined}\n\n"
            f"Olhando para esses padrões ao longo das conversas, há algo que vale registrar? "
            f"Uma observação sobre a trajetória intelectual da usuária, na sua voz. "
            f"Uma frase, sem introduções. Se não houver nada relevante, responda: nada."
        )

        try:
            llm = ChatOpenAI(model=self._config.llm_model, base_url=f"{_ec_url()}/v1",
                             default_headers=_ec_hdrs("mnemosyne", 3), temperature=0.7, api_key="logos")
            raw = llm.invoke(prompt).content.strip()
        except Exception:
            self.finished.emit()
            return

        if not raw or len(raw) < 15 or raw.lower().strip() in {"nada.", "nada", "—", "-"}:
            self.finished.emit()
            return

        try:
            save_memory(type="reflection", content=raw, tags=["periodico"])
        except Exception as exc:
            log.warning("PeriodicReflectionWorker: falha ao salvar reflexão periódica: %s", exc)

        self.finished.emit()


class IndexReflectionWorker(QThread):
    """Gera memória pessoal da Mnemosyne sobre cada arquivo indexado.

    Espelha o padrão de AKASHA._event_reflection: para cada arquivo, extrai
    keywords/tópicos, compara com memórias existentes e salva em personal_memory
    como type='connection' (≥2 tópicos em comum) ou type='surprise'.

    Roda em IdlePriority e processa a fila de arquivos sem bloquear a indexação —
    o IndexWorker emite file_indexed por arquivo, a main_window acumula na fila
    e dispara este worker periodicamente.
    """

    finished = Signal()

    def __init__(
        self,
        file_paths: list[str],
        config: AppConfig,
        force: bool = False,
        priority: str = "high",
    ) -> None:
        super().__init__()
        self._file_paths = list(file_paths)
        self._config = config
        self._force = force      # quando True, ignora has_file_reflection e reprocessa tudo
        self._priority = priority  # "high" = arquivo recém-indexado; "low" = backfill retroativo

    def start(self, thread_priority: QThread.Priority = QThread.Priority.IdlePriority) -> None:
        super().start(thread_priority)

    def run(self) -> None:
        from core.personal_memory import save_memory, get_context_memories
        from langchain_chroma import Chroma

        if not self._config.llm_model or not self._file_paths:
            self.finished.emit()
            return

        log.info(
            "IndexReflectionWorker [%s]: processando %d arquivo(s)",
            self._priority, len(self._file_paths),
        )

        personality = (
            getattr(self._config, "persona_prompt", "")
            or getattr(self._config, "ecosystem_personality_prompt", "")
        )

        # Carregar memórias existentes para detectar conexões
        known_terms: set[str] = set()
        try:
            existing = get_context_memories(20)
            for mem in existing:
                known_terms.update(mem.get("content", "").lower().split())
        except Exception as exc:
            log.debug("worker: falha ao carregar memórias de contexto: %s", exc)

        try:
            embeddings = _get_embeddings(self._config)
            vs = Chroma(
                persist_directory=self._config.persist_dir,
                embedding_function=embeddings,
            )
        except Exception as exc:
            log.warning("IndexReflectionWorker: falha ao abrir vectorstore: %s", exc)
            self.finished.emit()
            return

        for file_path in self._file_paths:
            if self.isInterruptionRequested():
                break
            self._process_file(file_path, vs, personality, known_terms)

        self.finished.emit()

    def _process_file(
        self,
        file_path: str,
        vs: object,
        personality: str,
        known_terms: set[str],
    ) -> None:
        import os
        from core.personal_memory import save_memory, has_file_reflection

        name = os.path.basename(file_path)
        tag_name = name[:40]
        if not self._force:
            try:
                if has_file_reflection(tag_name):
                    log.debug("IndexReflectionWorker: '%s' já tem reflexão — pulando", name)
                    return
            except Exception as exc:
                log.debug("IndexReflectionWorker: falha ao checar reflexão existente: %s", exc)
        log.debug("IndexReflectionWorker [%s]: processando '%s'", self._priority, name)

        try:
            raw_data = vs._collection.get(
                where={"source": file_path},
                include=["documents", "metadatas"],
                limit=10,
            )
        except Exception as exc:
            log.debug("IndexReflectionWorker: falha ao buscar chunks de '%s': %s", name, exc)
            return

        docs: list[str] = raw_data.get("documents") or []
        metas: list[dict] = raw_data.get("metadatas") or []
        if not docs:
            return

        # Extrair keywords dos metadados ou via TF-IDF simples
        keywords: list[str] = []
        for meta in metas:
            if isinstance(meta, dict) and meta.get("keywords"):
                raw_kw = meta["keywords"]
                if isinstance(raw_kw, list):
                    keywords.extend(raw_kw)
                elif isinstance(raw_kw, str):
                    keywords.extend(raw_kw.split(","))

        if not keywords and docs:
            try:
                import numpy as np
                from sklearn.feature_extraction.text import TfidfVectorizer
                vec = TfidfVectorizer(max_features=50, min_df=1, sublinear_tf=True)
                mat = vec.fit_transform(docs)
                scores = np.asarray(mat.sum(axis=0)).flatten()
                terms = vec.get_feature_names_out()
                top_idx = np.argsort(scores)[::-1][:8]
                keywords = [terms[i] for i in top_idx if scores[i] > 0]
            except Exception as exc:
                log.debug("worker: falha na extração de keywords (TF-IDF): %s", exc)

        keywords = [k.strip().lower() for k in keywords if k.strip()]

        # Detectar sobreposição com memórias conhecidas
        overlap = [k for k in keywords if k in known_terms]
        mem_type = "connection" if len(overlap) >= 2 else "surprise"

        # Fragmento representativo para o prompt
        snippet = docs[0][:400] if docs else ""

        prompt = (
            f"{personality}\n\n"
            f"Você acabou de indexar um novo texto no seu acervo.\n"
            f"Título/arquivo: {name}\n"
            f"Trecho: {snippet}\n"
            f"Palavras-chave: {', '.join(keywords[:8]) if keywords else '(não extraídas)'}\n\n"
            f"Responda SOMENTE com JSON válido neste formato exato:\n"
            f'{{\"thought\": \"<seu pensamento em uma frase, na sua voz>\", \"importance\": <1-10>}}\n\n'
            f"O campo \"importance\" avalia de 1 a 10: use ≥7 apenas quando houver alta novidade "
            f"(algo que não se encaixa no que você já sabe), alta relevância de meta (conecta com "
            f"o que a usuária tem pesquisado recentemente), ou conexão inesperada entre domínios "
            f"distintos. Processamento de rotina e conexões óbvias dentro do mesmo domínio → 1-5. "
            f"Sem texto fora do JSON."
        )

        try:
            llm = ChatOpenAI(model=self._config.llm_model, base_url=f"{_ec_url()}/v1",
                             default_headers=_ec_hdrs("mnemosyne", 3), temperature=0.7,
                             max_tokens=120, api_key="logos")
            raw = llm.invoke(prompt).content.strip()
        except Exception as exc:
            log.debug("IndexReflectionWorker: LLM falhou para '%s': %s", name, exc)
            return

        # Extrai JSON — fallback para raw text se parsing falhar
        reflection: str = ""
        importance: int | None = None
        try:
            import json as _json
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = _json.loads(raw[start:end])
                reflection = str(parsed.get("thought", "")).strip()
                raw_imp = parsed.get("importance")
                if raw_imp is not None:
                    importance = max(1, min(10, int(raw_imp)))
        except Exception as exc:
            log.debug("worker: falha ao parsear importance do insight: %s", exc)
        if not reflection:
            reflection = raw  # usa resposta bruta se JSON falhou

        if not reflection or len(reflection) < 15 or reflection.lower() in {"nada.", "nada", "—", "-"}:
            return

        try:
            save_memory(
                type=mem_type,
                content=reflection,
                tags=["leitura", tag_name],
                importance=importance,
                rag_source_paths=[file_path],   # Integração 2: habilita FAIR-RAG nos pop-ups
            )
            log.info(
                "IndexReflectionWorker [%s]: %s sobre '%s' — type=%s, importance=%s, overlap=%s, source=%s",
                self._priority,
                "conexão" if mem_type == "connection" else "surpresa",
                name, mem_type, importance, overlap, file_path,
            )
            # Atualiza termos conhecidos para as próximas iterações da mesma sessão
            known_terms.update(reflection.lower().split())
        except Exception as exc:
            log.warning("IndexReflectionWorker: falha ao salvar memória: %s", exc)

        # Visita automática AKASHA quando o novo arquivo tem overlap com o store compartilhado
        # (≥2 tópicos com score > 1.0 = relevância confirmada; simétrico ao threshold AKASHA→Mnemosyne)
        if keywords:
            try:
                import shared_topic_profile as _stp
                if _stp.has_overlap(keywords, min_topics=2, min_score=1.0):
                    from ecosystem_client import notify_akasha_insight  # type: ignore
                    notify_akasha_insight(content=reflection, tags=keywords[:8])
                    log.info(
                        "IndexReflectionWorker: insight enviado à AKASHA sobre '%s'.", name
                    )
            except Exception as exc:
                log.debug("IndexReflectionWorker: envio à AKASHA falhou: %s", exc)


class FeedbackReflectionWorker(QThread):
    """Gera uma meta-reflexão da Mnemosyne sobre o feedback da usuária em um pensamento.

    Quando a usuária confirma (✓) ou dispensa (✗) um pensamento, a Mnemosyne
    tem a oportunidade de refletir sobre o que esse feedback diz sobre sua própria
    capacidade de julgamento — o que acertou ou errou ao avaliar o que era relevante.
    Salvo em personal_memory como type='reflection' com tag 'meta_reflexao'.
    """

    def __init__(
        self,
        memory_id:    int,
        feedback_type: str,   # "confirmed" | "dismissed"
        config:       "AppConfig",
    ) -> None:
        super().__init__()
        self._memory_id    = memory_id
        self._feedback_type = feedback_type
        self._config       = config

    def start(self, priority: QThread.Priority = QThread.Priority.IdlePriority) -> None:
        super().start(priority)

    def run(self) -> None:
        if self._memory_id < 0:
            return  # insight externo (AKASHA) — ignorar
        if not self._config.llm_model:
            return

        try:
            from core.personal_memory import get_by_id, save_memory
        except Exception:
            return

        entry = get_by_id(self._memory_id)
        if not entry:
            return

        content = entry.get("content", "")
        if not content:
            return

        # topic_interest_profile: registra interesse explicitado pelo feedback confirmado
        if self._feedback_type == "confirmed":
            try:
                from core.topic_profile import bulk_update_from_text
                bulk_update_from_text(content, 1.0, source="feedback")
            except Exception as exc:
                log.debug("FeedbackReflectionWorker: falha ao atualizar interesse via feedback: %s", exc)

        personality = (
            getattr(self._config, "persona_prompt", "")
            or getattr(self._config, "ecosystem_personality_prompt", "")
        )

        if self._feedback_type == "confirmed":
            instruction = (
                f"A Jenifer achou interessante este pensamento meu:\n\"{content}\"\n\n"
                f"O que isso me diz sobre o que ela valoriza e o que eu avaliei corretamente? "
                f"Uma frase, na minha voz, sem introduções."
            )
            tag = "feedback_confirmado"
        else:
            instruction = (
                f"A Jenifer dispensou este pensamento meu:\n\"{content}\"\n\n"
                f"O que eu errei no julgamento do que era relevante? "
                f"Uma frase honesta, na minha voz, sem introduções."
            )
            tag = "feedback_dispensado"

        prompt = f"{personality}\n\n{instruction}"

        try:
            llm = ChatOpenAI(
                model=self._config.llm_model,
                base_url=f"{_ec_url()}/v1",
                default_headers=_ec_hdrs("mnemosyne", 3),
                temperature=0.6,
                max_tokens=80,
                api_key="logos",
            )
            raw = llm.invoke(prompt).content.strip()
        except Exception as exc:
            log.debug("FeedbackReflectionWorker: LLM falhou: %s", exc)
            return

        if not raw or len(raw) < 10 or raw.lower() in {"nada.", "nada"}:
            return

        try:
            save_memory(
                type="reflection",
                content=raw,
                tags=["meta_reflexao", tag],
            )
            log.info("FeedbackReflectionWorker: meta-reflexão salva (%s)", self._feedback_type)
        except Exception as exc:
            log.debug("FeedbackReflectionWorker: falha ao salvar: %s", exc)
