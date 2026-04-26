# Threads para indexação, consultas e resumos.
from __future__ import annotations

from langchain_ollama import ChatOllama, OllamaLLM
from PySide6.QtCore import QThread, Signal

from core.config import AppConfig
from core.errors import (
    MnemosyneError,
    OllamaUnavailableError,
    ModelNotFoundError,
    DocumentLoadError,
    IndexBuildError,
    EmptyDirectoryError,
    QueryError,
    SummarizationError,
    GuideError,
    AkashaOfflineError,
    AkashaFetchError,
)
from core.faq import iter_faq, parse_faq
from core.indexer import (
    create_vectorstore,
    index_single_file,
    load_vectorstore,
    update_vectorstore,
    _detect_batch_config,
    _get_splitter,
    _clear_orphan_wal,
    IndexCheckpoint,
)
from core.loaders import load_documents, load_single_file
from core.memory import MemoryStore, Turn
from core.ollama_client import list_models, validate_model
from core.rag import prepare_ask, strip_think, AskResult, SourceRecord
from core.summarizer import iter_summary
from core.tracker import FileTracker


class OllamaCheckWorker(QThread):
    """Verifica disponibilidade do Ollama e lista modelos instalados."""

    models_loaded = Signal(list)      # list[OllamaModel]
    ollama_unavailable = Signal(str)  # mensagem de erro

    def run(self) -> None:
        try:
            models = list_models()
            self.models_loaded.emit(models)
        except OllamaUnavailableError as exc:
            self.ollama_unavailable.emit(str(exc))
        except Exception as exc:
            self.ollama_unavailable.emit(f"Erro inesperado ao contatar Ollama: {exc}")


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

    finished = Signal(bool, str)
    progress = Signal(str, int, int)  # label, posição, total

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
        from langchain_ollama import OllamaEmbeddings

        _SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".epub"}

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
            self.finished.emit(False, f"Pasta não encontrada: {exc}")
            return

        if not files:
            self.finished.emit(False, str(EmptyDirectoryError(self.config.watched_dir)))
            return

        # ── 2. Limpar toda a pasta .mnemosyne (parte do zero) ────────────────
        mnemosyne_dir = self.config.mnemosyne_dir
        if mnemosyne_dir and os.path.exists(mnemosyne_dir):
            try:
                shutil.rmtree(mnemosyne_dir)
            except OSError as exc:
                self.finished.emit(False, f"Erro ao limpar estado anterior: {exc}")
                return
        try:
            os.makedirs(self.config.persist_dir, exist_ok=True)
        except OSError as exc:
            self.finished.emit(False, f"Erro ao criar diretório: {exc}")
            return

        _BATCH, _SLEEP = _detect_batch_config()
        embeddings = OllamaEmbeddings(model=self.config.embed_model)
        splitter = _get_splitter(self.config, embeddings)
        tracker = FileTracker(self.config.mnemosyne_dir)
        checkpoint = IndexCheckpoint(self.config.mnemosyne_dir)
        total = len(files)
        errors: list[str] = []

        # ── 3. Abrir Chroma vazio ─────────────────────────────────────────────
        try:
            vs = Chroma(
                persist_directory=self.config.persist_dir,
                embedding_function=embeddings,
                collection_metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            self.finished.emit(False, f"Erro ao criar vectorstore: {exc}")
            return

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

            try:
                docs = load_single_file(file_path)
                chunks = splitter.split_documents(docs)
            except MnemosyneError as exc:
                errors.append(str(exc))
                checkpoint.record(file_path, "error")
                continue

            if not chunks:
                tracker.mark_indexed(file_path)
                checkpoint.record(file_path, "ok")
                continue

            # Probe de GPU no primeiro batch de chunks encontrado
            if not probe_done:
                probe_batch = chunks[:_BATCH]
                try:
                    t0 = time.time()
                    probe_embs = embeddings.embed_documents([c.page_content for c in probe_batch])
                    t_probe = time.time() - t0
                    vs._collection.add(
                        ids=[str(uuid.uuid4()) for _ in probe_batch],
                        documents=[c.page_content for c in probe_batch],
                        embeddings=probe_embs,
                        metadatas=[c.metadata or {} for c in probe_batch],
                    )
                    use_parallel = t_probe < 2.0 and _BATCH >= 50
                    probe_done = True
                except Exception as exc:
                    self.finished.emit(False, f"Erro ao criar vectorstore: {exc}")
                    return
                remaining = chunks[len(probe_batch):]
            else:
                remaining = chunks

            # Embedar chunks restantes do arquivo em batches
            if remaining:
                batch_list = [remaining[b : b + _BATCH] for b in range(0, len(remaining), _BATCH)]
                n_batches = len(batch_list)
                try:
                    if use_parallel and n_batches > 1:
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            futures = [
                                (batch, pool.submit(
                                    embeddings.embed_documents,
                                    [c.page_content for c in batch],
                                ))
                                for batch in batch_list
                            ]
                            for b_idx, (batch, future) in enumerate(futures):
                                if self.isInterruptionRequested():
                                    self.finished.emit(False, "Interrompido.")
                                    return
                                embs = future.result()
                                vs._collection.add(
                                    ids=[str(uuid.uuid4()) for _ in batch],
                                    documents=[c.page_content for c in batch],
                                    embeddings=embs,
                                    metadatas=[c.metadata or {} for c in batch],
                                )
                                self.progress.emit(f"Incorporando {name}", i, total)
                                if b_idx + 1 < n_batches:
                                    time.sleep(_SLEEP)
                    else:
                        for b_idx, batch in enumerate(batch_list):
                            if self.isInterruptionRequested():
                                self.finished.emit(False, "Interrompido.")
                                return
                            embs = embeddings.embed_documents([c.page_content for c in batch])
                            vs._collection.add(
                                ids=[str(uuid.uuid4()) for _ in batch],
                                documents=[c.page_content for c in batch],
                                embeddings=embs,
                                metadatas=[c.metadata or {} for c in batch],
                            )
                            self.progress.emit(f"Incorporando {name}", i, total)
                            if b_idx + 1 < n_batches:
                                time.sleep(_SLEEP)
                except Exception as exc:
                    errors.append(f"{name}: {exc}")
                    checkpoint.record(file_path, "error")
                    continue

            # Salvar progresso no tracker e no checkpoint após cada arquivo
            tracker.mark_indexed(file_path)
            checkpoint.record(file_path, "ok")

        # Apagar checkpoint: indexação concluída — botão "Retomar" não deve aparecer
        checkpoint.delete()
        msg = f"Indexação concluída — {total} arquivo(s) processado(s)."
        if errors:
            msg += f" {len(errors)} erro(s) ignorado(s)."
        self.finished.emit(True, msg)


class ResumeIndexWorker(QThread):
    """
    Retoma indexação interrompida usando o IndexCheckpoint existente.
    Processa apenas os arquivos que ainda NÃO estão no checkpoint como 'ok'.
    Não apaga persist_dir nem o checkpoint — continua de onde parou.
    Deleta o checkpoint ao concluir com sucesso.
    """

    finished = Signal(bool, str)
    progress = Signal(str, int, int)

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
        from langchain_chroma import Chroma
        from langchain_ollama import OllamaEmbeddings

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
        embeddings = OllamaEmbeddings(model=self.config.embed_model)
        splitter = _get_splitter(self.config, embeddings)
        tracker = FileTracker(self.config.mnemosyne_dir)
        errors: list[str] = []

        try:
            vs = Chroma(
                persist_directory=self.config.persist_dir,
                embedding_function=embeddings,
                collection_metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            checkpoint.close()
            self.finished.emit(False, f"Erro ao abrir vectorstore: {exc}")
            return

        # ── 4. Processar arquivos pendentes ───────────────────────────────────
        total = len(pending)
        for i, file_path in enumerate(pending, 1):
            if self.isInterruptionRequested():
                checkpoint.close()
                self.finished.emit(False, "Retomada interrompida.")
                return

            name = os.path.basename(file_path)
            self.progress.emit(name, already_done + i, total_all)

            try:
                docs = load_single_file(file_path)
                chunks = splitter.split_documents(docs)
            except MnemosyneError as exc:
                errors.append(str(exc))
                checkpoint.record(file_path, "error")
                continue

            if not chunks:
                tracker.mark_indexed(file_path)
                checkpoint.record(file_path, "ok")
                continue

            try:
                batch_list = [chunks[b : b + _BATCH] for b in range(0, len(chunks), _BATCH)]
                for b_idx, batch in enumerate(batch_list):
                    if self.isInterruptionRequested():
                        checkpoint.close()
                        self.finished.emit(False, "Retomada interrompida.")
                        return
                    embs = embeddings.embed_documents([c.page_content for c in batch])
                    vs._collection.add(
                        ids=[str(uuid.uuid4()) for _ in batch],
                        documents=[c.page_content for c in batch],
                        embeddings=embs,
                        metadatas=[c.metadata or {} for c in batch],
                    )
                    self.progress.emit(f"Incorporando {name}", already_done + i, total_all)
                    if b_idx + 1 < len(batch_list):
                        time.sleep(_SLEEP)
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                checkpoint.record(file_path, "error")
                continue

            tracker.mark_indexed(file_path)
            checkpoint.record(file_path, "ok")

        checkpoint.delete()
        msg = f"Retomada concluída — {already_done} já indexados, {total} processados agora."
        if errors:
            msg += f" {len(errors)} erro(s) ignorado(s)."
        self.finished.emit(True, msg)


class UpdateIndexWorker(QThread):
    """Actualiza o vectorstore incrementalmente via FileTracker."""

    finished = Signal(bool, str)  # sucesso, mensagem com stats

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config

    def start(self, priority: QThread.Priority = QThread.Priority.IdlePriority) -> None:
        super().start(priority)

    def run(self) -> None:
        try:
            _, stats = update_vectorstore(self.config)
            msg = (
                f"Índice actualizado — "
                f"{stats['new']} novo(s), "
                f"{stats['modified']} modificado(s), "
                f"{stats['deleted']} removido(s)."
            )
            if stats["errors"]:
                msg += f" {stats['errors']} erro(s) ignorado(s)."
            self.finished.emit(True, msg)
        except VectorstoreNotFoundError:
            self.finished.emit(False, "Nenhum índice encontrado. Use 'Indexar tudo' primeiro.")
        except MnemosyneError as exc:
            self.finished.emit(False, str(exc))
        except Exception as exc:
            self.finished.emit(False, f"Erro ao actualizar índice: {exc}")


class IndexFileWorker(QThread):
    """Indexa um único arquivo — usado pelo watcher de pasta."""

    finished = Signal(bool, str)  # sucesso, mensagem

    def __init__(self, file_path: str, config: AppConfig) -> None:
        super().__init__()
        self.file_path = file_path
        self.config = config

    def start(self, priority: QThread.Priority = QThread.Priority.LowPriority) -> None:
        super().start(priority)

    def run(self) -> None:
        import os

        try:
            index_single_file(self.file_path, self.config)
            name = os.path.basename(self.file_path)
            self.finished.emit(True, f"'{name}' indexado.")
        except DocumentLoadError as exc:
            self.finished.emit(False, f"Erro ao carregar arquivo: {exc}")
        except IndexBuildError as exc:
            self.finished.emit(False, f"Erro na indexação: {exc}")
        except MnemosyneError as exc:
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
            self.finished.emit(False, str(exc))
        except Exception as exc:
            self.finished.emit(False, f"Erro inesperado ao compactar: {exc}")


class AskWorker(QThread):
    """Executa uma consulta RAG com streaming token a token."""

    token = Signal(str)                       # token recebido durante streaming
    finished = Signal(bool, str, list, list)  # sucesso, resposta/erro, fontes, turns_updated

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

    def run(self) -> None:
        try:
            messages, sources = prepare_ask(
                self.vectorstore, self.question, self.config,
                self.chat_history, self.source_type, self.retrieval_mode,
                self.tracker, self.persona, self.source_files,
                self.collection_type,
            )
        except QueryError as exc:
            self.finished.emit(False, str(exc), [], self.chat_history)
            return
        except Exception as exc:
            self.finished.emit(False, f"Erro na recuperação: {exc}", [], self.chat_history)
            return

        try:
            validate_model(self.config.llm_model)
        except ModelNotFoundError as exc:
            self.finished.emit(False, str(exc), [], self.chat_history)
            return
        except OllamaUnavailableError as exc:
            self.finished.emit(False, str(exc), [], self.chat_history)
            return

        try:
            llm = ChatOllama(model=self.config.llm_model, temperature=0, num_ctx=8192)
            full = ""
            for chunk in llm.stream(messages):
                if self.isInterruptionRequested():
                    self.finished.emit(False, "Interrompido.", [], self.chat_history)
                    return
                # AIMessageChunk: chunks de metadata chegam com content="" — ignorar
                if chunk.content:
                    self.token.emit(chunk.content)
                    full += chunk.content
            answer = strip_think(full)
            source_paths = [s["path"] for s in sources]
            updated = list(self.chat_history) + [
                Turn(role="user", content=self.question),
                Turn(role="assistant", content=answer, sources=source_paths),
            ]
            if self.tracker and sources:
                for rank, src in enumerate(sources):
                    score = max(0.3, 1.0 - rank * 0.2)
                    self.tracker.update_retrieved(src["path"], score)
            self.finished.emit(True, answer, sources, updated)
        except Exception as exc:
            self.finished.emit(False, f"Erro na consulta: {exc}", [], self.chat_history)


class DeepResearchWorker(QThread):
    """Pesquisa profunda: combina biblioteca local com páginas buscadas no AKASHA em tempo real.

    Pipeline:
      1. AkashaClient.search() → lista de URLs candidatas
      2. fetch() paralelo via asyncio.gather → conteúdo Markdown de cada página
      3. SessionIndexer.add_pages() → índice efêmero em memória (ou stuffing em RAM limitada)
      4. Retrieval local (vectorstore) + retrieval web (session)
      5. Prompt combinado [Local] + [WEB] → streaming com ChatOllama
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
        except Exception:
            pass  # vectorstore pode estar vazio

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
            llm  = ChatOllama(model=self.config.llm_model, temperature=0, num_ctx=8192)
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
    "Briefing":       ("core.briefing",    "iter_briefing"),
    "Relatório":      ("core.report",      "iter_report"),
    "Guia de Estudo": ("core.study_guide", "iter_study_guide"),
    "Índice de Temas":("core.toc",         "iter_toc"),
    "Linha do Tempo": ("core.timeline",    "iter_timeline"),
    "Blog Post":      ("core.blogpost",    "iter_blogpost"),
    "Mind Map":       ("core.mindmap",     "iter_mindmap"),
    "Tabela de Dados":("core.tables",      "iter_tables"),
    "Slides":         ("core.slides",      "iter_slides"),
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
