"""
Rastreamento de arquivos por hash SHA-256 para indexação incremental.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


_SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".txt", ".md"})


@dataclass
class FileRecord:
    path: str
    hash: str
    indexed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    score_avg: float = 0.0          # score médio de similaridade nas consultas
    last_retrieved_at: str = ""     # timestamp da última vez retornado como fonte
    retrieve_count: int = 0         # total de consultas em que foi retornado


class FileTracker:
    """
    Rastreia hashes SHA-256 de arquivos indexados.
    Persiste em <mnemosyne_dir>/tracker.json.
    """

    def __init__(self, mnemosyne_dir: str) -> None:
        self._path = Path(mnemosyne_dir) / "tracker.json"
        self._records: dict[str, FileRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open(encoding="utf-8") as f:
                raw = json.load(f)
            records: dict[str, FileRecord] = {}
            for item in raw:
                try:
                    rec = FileRecord(
                        path=item["path"],
                        hash=item["hash"],
                        indexed_at=item.get("indexed_at", ""),
                        score_avg=float(item.get("score_avg", 0.0)),
                        last_retrieved_at=item.get("last_retrieved_at", ""),
                        retrieve_count=int(item.get("retrieve_count", 0)),
                    )
                    records[rec.path] = rec
                except (KeyError, ValueError, TypeError):
                    continue
            self._records = records
        except (json.JSONDecodeError, TypeError, OSError):
            self._records = {}

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(
                [asdict(r) for r in self._records.values()],
                f,
                indent=2,
                ensure_ascii=False,
            )

    def compute_hash(self, file_path: str) -> str:
        """Calcula SHA-256 do arquivo.

        Raises:
            OSError: se o arquivo não puder ser lido.
        """
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def is_changed(self, file_path: str) -> bool:
        """True se o arquivo for novo ou se o hash divergir do registado."""
        if file_path not in self._records:
            return True
        try:
            return self.compute_hash(file_path) != self._records[file_path].hash
        except OSError:
            return False

    def mark_indexed(self, file_path: str) -> None:
        """Registra/atualiza o hash do arquivo após indexação bem-sucedida."""
        try:
            h = self.compute_hash(file_path)
        except OSError:
            return
        self._records[file_path] = FileRecord(path=file_path, hash=h)
        self.save()

    def remove(self, file_path: str) -> None:
        """Remove o registo de um arquivo deletado ou renomeado."""
        if file_path in self._records:
            del self._records[file_path]
            self.save()

    def get_pending(
        self, watched_dir: str
    ) -> tuple[list[str], list[str], list[str]]:
        """
        Escaneia watched_dir e retorna (novos, modificados, deletados).
        Ignora a pasta .mnemosyne.
        """
        found: set[str] = set()
        new: list[str] = []
        modified: list[str] = []

        for root, dirs, files in os.walk(watched_dir):
            dirs[:] = [d for d in dirs if d != ".mnemosyne"]
            for fname in files:
                ext = Path(fname).suffix.lower()
                if ext not in _SUPPORTED_EXTENSIONS:
                    continue
                full = os.path.join(root, fname)
                found.add(full)
                if full not in self._records:
                    new.append(full)
                else:
                    try:
                        current = self.compute_hash(full)
                    except OSError:
                        continue
                    if current != self._records[full].hash:
                        modified.append(full)

        deleted = [p for p in self._records if p not in found]
        return new, modified, deleted

    def update_retrieved(self, file_path: str, score: float = 1.0) -> None:
        """
        Actualiza metadados de relevância após o documento ser retornado
        como fonte numa consulta RAG.

        score: [0.0, 1.0] — contribuição desta consulta para o score médio.
        """
        rec = self._records.get(file_path)
        if rec is None:
            return
        n = rec.retrieve_count
        rec.score_avg = (rec.score_avg * n + max(0.0, min(1.0, score))) / (n + 1)
        rec.retrieve_count = n + 1
        rec.last_retrieved_at = datetime.now().isoformat()
        self.save()

    @property
    def records(self) -> dict[str, FileRecord]:
        return dict(self._records)
