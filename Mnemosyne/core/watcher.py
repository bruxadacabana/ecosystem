"""
Monitoramento em tempo real da pasta de documentos via QFileSystemWatcher.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QFileSystemWatcher, QObject, Signal


_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


class FolderWatcher(QObject):
    """
    Monitora uma pasta e seus subdiretórios em tempo real.
    Emite `file_added` quando um arquivo suportado é detectado pela primeira vez.
    Emite `file_removed` quando um arquivo monitorado desaparece (remoção ou renomeação).
    """

    file_added = Signal(str)    # path absoluto do arquivo novo
    file_removed = Signal(str)  # path absoluto do arquivo removido/renomeado

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_directory_changed)
        self._known_files: set[str] = set()
        self._watched_root: str = ""
        self._enabled: bool = True

    def watch(self, directory: str) -> None:
        """Inicia o monitoramento de `directory` e seus subdiretórios."""
        self.stop()
        if not os.path.isdir(directory):
            return

        self._watched_root = directory
        dirs_to_watch: list[str] = []

        for root, dirs, files in os.walk(directory):
            # Ignorar diretório interno do Mnemosyne
            dirs[:] = [d for d in dirs if d != ".mnemosyne"]
            dirs_to_watch.append(root)
            for filename in files:
                _, ext = os.path.splitext(filename.lower())
                if ext in _SUPPORTED_EXTENSIONS:
                    self._known_files.add(os.path.join(root, filename))

        if dirs_to_watch:
            self._watcher.addPaths(dirs_to_watch)

    def stop(self) -> None:
        """Para o monitoramento e limpa o estado interno."""
        paths = self._watcher.directories() + self._watcher.files()
        if paths:
            self._watcher.removePaths(paths)
        self._known_files.clear()
        self._watched_root = ""

    def set_enabled(self, enabled: bool) -> None:
        """Pausa ou retoma a emissão de sinais sem parar o QFileSystemWatcher."""
        self._enabled = enabled

    @property
    def is_active(self) -> bool:
        return bool(self._watched_root)

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def _on_directory_changed(self, path: str) -> None:
        """Chamado pelo Qt quando um diretório monitorado muda."""
        if not self._enabled:
            return

        try:
            entries = set(os.listdir(path))
        except OSError:
            return

        # Detectar arquivos removidos ou renomeados
        removed = [
            f for f in list(self._known_files)
            if os.path.dirname(f) == path and not os.path.exists(f)
        ]
        for full_path in removed:
            self._known_files.discard(full_path)
            self.file_removed.emit(full_path)

        # Detectar arquivos novos
        for filename in entries:
            _, ext = os.path.splitext(filename.lower())
            if ext not in _SUPPORTED_EXTENSIONS:
                continue
            full_path = os.path.join(path, filename)
            if full_path not in self._known_files and os.path.isfile(full_path):
                self._known_files.add(full_path)
                self.file_added.emit(full_path)

        # Registrar subdiretórios novos para monitoramento
        for filename in entries:
            full_path = os.path.join(path, filename)
            if (
                os.path.isdir(full_path)
                and filename != ".mnemosyne"
                and full_path not in self._watcher.directories()
            ):
                self._watcher.addPath(full_path)
