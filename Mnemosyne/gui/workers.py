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
)
from core.indexer import create_vectorstore, index_single_file, load_vectorstore, update_vectorstore
from core.loaders import load_documents, load_single_file
from core.memory import MemoryStore, Turn
from core.ollama_client import list_models, validate_model
from core.rag import prepare_ask, strip_think, AskResult
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
    """Indexa todos os documentos da pasta monitorada."""

    finished = Signal(bool, str)   # sucesso, mensagem
    progress = Signal(str, int, int)  # nome_arquivo, posição, total

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:
        import os
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_chroma import Chroma
        from langchain_ollama import OllamaEmbeddings

        _SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".epub"}

        # Colectar lista de ficheiros
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

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )
        embeddings = OllamaEmbeddings(model=self.config.embed_model)
        total = len(files)
        vectorstore = None
        errors: list[str] = []

        for i, file_path in enumerate(files, 1):
            name = os.path.basename(file_path)
            self.progress.emit(name, i, total)
            try:
                docs = load_single_file(file_path)
            except MnemosyneError as exc:
                errors.append(str(exc))
                continue

            chunks = splitter.split_documents(docs)
            if not chunks:
                continue

            try:
                os.makedirs(self.config.persist_dir, exist_ok=True)
                if vectorstore is None:
                    vectorstore = Chroma.from_documents(
                        documents=chunks,
                        embedding=embeddings,
                        persist_directory=self.config.persist_dir,
                    )
                else:
                    vectorstore.add_documents(chunks)
            except Exception as exc:
                self.finished.emit(False, f"Erro ao indexar '{name}': {exc}")
                return

        if vectorstore is None:
            self.finished.emit(False, "Nenhum documento pôde ser indexado.")
            return

        msg = f"Indexação concluída — {total} arquivo(s) processado(s)."
        if errors:
            msg += f" {len(errors)} erro(s) ignorado(s)."
        self.finished.emit(True, msg)


class UpdateIndexWorker(QThread):
    """Actualiza o vectorstore incrementalmente via FileTracker."""

    finished = Signal(bool, str)  # sucesso, mensagem com stats

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config

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

    def __init__(self, memory_store: MemoryStore, llm_model: str) -> None:
        super().__init__()
        self.memory_store = memory_store
        self.llm_model = llm_model

    def run(self) -> None:
        try:
            facts = self.memory_store.compact_session_memory(self.llm_model)
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

    def run(self) -> None:
        try:
            messages, sources = prepare_ask(
                self.vectorstore, self.question, self.config,
                self.chat_history, self.source_type, self.retrieval_mode,
                self.tracker, self.persona, self.source_files,
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
            llm = ChatOllama(model=self.config.llm_model, temperature=0)
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
