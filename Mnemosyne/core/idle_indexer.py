"""
Indexador automático em background: monitora coleções do ecossistema (KOSMOS, AKASHA, Hermes)
e indexa novos arquivos quando o Mnemosyne não está ocupado com indexação principal.
"""
from __future__ import annotations

import queue
from dataclasses import dataclass, replace
from typing import Callable

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from core.collections import CollectionConfig
from core.config import AppConfig
from core.watcher import FolderWatcher


@dataclass
class _IndexJob:
    file_path: str
    collection: CollectionConfig


class _IndexJobWorker(QThread):
    done = Signal(str, str, bool, str)  # file_path, coll_name, success, msg

    def __init__(
        self,
        job: _IndexJob,
        config: AppConfig,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._job = job
        self._config = config

    def run(self) -> None:
        self.setPriority(QThread.Priority.IdlePriority)
        try:
            from core.indexer import index_single_file  # lazy import — heavy
            index_single_file(self._job.file_path, self._config)
            self.done.emit(self._job.file_path, self._job.collection.name, True, "")
        except ValueError as exc:
            self.done.emit(self._job.file_path, self._job.collection.name, False, str(exc))
        except OSError as exc:
            self.done.emit(self._job.file_path, self._job.collection.name, False, str(exc))
        except RuntimeError as exc:
            self.done.emit(self._job.file_path, self._job.collection.name, False, str(exc))


def _make_config_for_collection(base: AppConfig, coll: CollectionConfig) -> AppConfig:
    """Cria uma AppConfig proxy que aponta para `coll` como coleção ativa."""
    colls = base.collections
    if not any(c.name == coll.name for c in colls):
        colls = [*colls, coll]
    return replace(base, active_collection=coll.name, collections=colls)


class IdleIndexer(QObject):
    """
    Monitora coleções do ecossistema e indexa arquivos novos quando o Mnemosyne
    não está realizando indexação principal. Processa um arquivo por vez, na
    prioridade mais baixa possível (IdlePriority), para não interferir com o uso ativo.
    """

    file_indexed = Signal(str, str, bool, str)  # file_path, coll_name, success, msg
    queue_size_changed = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._queue: queue.Queue[_IndexJob] = queue.Queue()
        self._watchers: list[tuple[FolderWatcher, CollectionConfig]] = []
        self._is_busy_fn: Callable[[], bool] = lambda: False
        self._job_worker: _IndexJobWorker | None = None
        self._base_config: AppConfig | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(30_000)
        self._timer.timeout.connect(self._process_next)

    def setup(self, base_config: AppConfig, is_busy_fn: Callable[[], bool]) -> None:
        """
        Inicia o monitoramento das coleções de ecossistema habilitadas.
        `is_busy_fn` retorna True enquanto o Mnemosyne estiver indexando ativamente.
        """
        self.stop()

        self._base_config = base_config
        self._is_busy_fn = is_busy_fn

        eco_colls = [
            c for c in base_config.collections
            if c.source == "ecosystem" and c.enabled and c.exists
        ]

        for coll in eco_colls:
            watcher = FolderWatcher(self)
            watcher.file_added.connect(
                lambda path, c=coll: self._on_file_added(path, c)
            )
            watcher.watch(coll.path)
            self._watchers.append((watcher, coll))

        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        for watcher, _ in self._watchers:
            watcher.stop()
        self._watchers.clear()

    def _on_file_added(self, file_path: str, collection: CollectionConfig) -> None:
        self._queue.put(_IndexJob(file_path=file_path, collection=collection))
        self.queue_size_changed.emit(self._queue.qsize())
        self._process_next()

    def _process_next(self) -> None:
        if self._job_worker is not None and self._job_worker.isRunning():
            return
        if self._is_busy_fn():
            return
        if self._base_config is None:
            return
        try:
            job = self._queue.get_nowait()
        except queue.Empty:
            return

        proxy_config = _make_config_for_collection(self._base_config, job.collection)
        self._job_worker = _IndexJobWorker(job, proxy_config, self)
        self._job_worker.done.connect(self._on_job_done)
        self._job_worker.start()

    def _on_job_done(self, file_path: str, coll_name: str, success: bool, msg: str) -> None:
        self.file_indexed.emit(file_path, coll_name, success, msg)
        self.queue_size_changed.emit(self._queue.qsize())
        self._process_next()

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()
