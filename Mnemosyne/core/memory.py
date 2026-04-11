"""
Gerenciamento de contexto pessoal em camadas.

Estrutura de persistência em <mnemosyne_dir>/:
  history.jsonl  — log append-only; cada linha é um turno JSON {role, content, sources, ts}
  memory.json    — estado persistido; secções:
                     "collection": instruções/descrição editável pelo utilizador
                     "session":    factos extraídos automaticamente pelo LLM

Uso no RAG:
  build_memory_context() → string injectada antes do contexto RAG no prompt
  compact_session_memory() → usa LLM para sintetizar histórico em factos compactos
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Constantes ────────────────────────────────────────────────────────────────

_HISTORY_FILENAME = "history.jsonl"
_MEMORY_FILENAME = "memory.json"

# Limite do histórico injectado no prompt (caracteres)
_HISTORY_CONTEXT_CHARS = 6_000
# Quantos turnos mais recentes incluir no contexto multi-turno
_HISTORY_TURNS = 5


# ── Tipos de turno ────────────────────────────────────────────────────────────


@dataclass
class Turn:
    role: str           # "user" | "assistant"
    content: str
    sources: list[str] = field(default_factory=list)
    ts: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Turn:
        return cls(
            role=data["role"],
            content=data["content"],
            sources=data.get("sources", []),
            ts=data.get("ts", ""),
        )


# ── CollectionIndex (sem alteração de API) ────────────────────────────────────


@dataclass
class CollectionInfo:
    name: str
    path: str
    total_files: int = 0
    last_indexed: str = ""
    file_types: dict[str, int] = field(default_factory=dict)
    summary: str = ""


class CollectionIndex:
    """
    Índice leve de coleções indexadas.
    Persiste em <mnemosyne_dir>/index.json.
    """

    def __init__(self, mnemosyne_dir: str) -> None:
        self._path = Path(mnemosyne_dir) / "index.json"
        self._collections: list[CollectionInfo] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open(encoding="utf-8") as f:
                data = json.load(f)
            self._collections = [CollectionInfo(**item) for item in data]
        except (json.JSONDecodeError, TypeError, KeyError):
            self._collections = []

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(
                [asdict(c) for c in self._collections],
                f,
                indent=2,
                ensure_ascii=False,
            )

    def update(self, info: CollectionInfo) -> None:
        for i, c in enumerate(self._collections):
            if c.path == info.path:
                self._collections[i] = info
                self.save()
                return
        self._collections.append(info)
        self.save()

    def get(self, path: str) -> CollectionInfo | None:
        return next((c for c in self._collections if c.path == path), None)

    @property
    def collections(self) -> list[CollectionInfo]:
        return list(self._collections)


# ── MemoryStore — history.jsonl + memory.json ─────────────────────────────────


class MemoryStore:
    """
    Armazena histórico de turnos (append-only em history.jsonl) e factos
    persistidos em memory.json.

    Secções de memory.json:
      collection  — descrição/instruções da pasta (editável pelo utilizador)
      session     — factos extraídos pelo LLM (compact_session_memory)
    """

    def __init__(self, mnemosyne_dir: str) -> None:
        base = Path(mnemosyne_dir)
        base.mkdir(parents=True, exist_ok=True)
        self._history_path = base / _HISTORY_FILENAME
        self._memory_path = base / _MEMORY_FILENAME
        self._memory: dict[str, str] = self._load_memory()

    # ── memory.json ───────────────────────────────────────────────────────────

    def _load_memory(self) -> dict[str, str]:
        if not self._memory_path.exists():
            return {"collection": "", "session": ""}
        try:
            with self._memory_path.open(encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"collection": "", "session": ""}
            return {
                "collection": str(data.get("collection", "")),
                "session": str(data.get("session", "")),
            }
        except (json.JSONDecodeError, OSError):
            return {"collection": "", "session": ""}

    def _save_memory(self) -> None:
        with self._memory_path.open("w", encoding="utf-8") as f:
            json.dump(self._memory, f, indent=2, ensure_ascii=False)

    @property
    def collection_description(self) -> str:
        return self._memory.get("collection", "")

    @collection_description.setter
    def collection_description(self, value: str) -> None:
        self._memory["collection"] = value
        self._save_memory()

    @property
    def session_facts(self) -> str:
        return self._memory.get("session", "")

    @session_facts.setter
    def session_facts(self, value: str) -> None:
        self._memory["session"] = value
        self._save_memory()

    # ── history.jsonl ─────────────────────────────────────────────────────────

    def append_turn(self, turn: Turn) -> None:
        """Adiciona um turno ao log (append-only)."""
        with self._history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(turn.to_dict(), ensure_ascii=False) + "\n")

    def load_history(self) -> list[Turn]:
        """Carrega todos os turnos do histórico."""
        if not self._history_path.exists():
            return []
        turns: list[Turn] = []
        try:
            with self._history_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        turns.append(Turn.from_dict(json.loads(line)))
                    except (json.JSONDecodeError, KeyError):
                        continue
        except OSError:
            return []
        return turns

    def clear_history(self) -> None:
        """Apaga o histórico (nova conversa)."""
        if self._history_path.exists():
            self._history_path.unlink()

    # ── Contexto para o prompt RAG ────────────────────────────────────────────

    def build_memory_context(self, recent_turns: list[Turn] | None = None) -> str:
        """
        Monta string de contexto de memória para injectar no prompt RAG.
        Inclui: descrição da colecção, factos de sessão e últimos turnos.

        recent_turns: se None, carrega os últimos _HISTORY_TURNS do ficheiro.
        """
        parts: list[str] = []

        if self.collection_description.strip():
            parts.append(f"[Sobre esta colecção]\n{self.collection_description.strip()}")

        if self.session_facts.strip():
            parts.append(f"[Factos relevantes desta sessão]\n{self.session_facts.strip()}")

        if recent_turns is None:
            history = self.load_history()
            recent_turns = history[-_HISTORY_TURNS:]

        if recent_turns:
            lines: list[str] = []
            total = 0
            for turn in reversed(recent_turns):
                prefix = "Utilizador" if turn.role == "user" else "Mnemosyne"
                entry = f"{prefix}: {turn.content}"
                if total + len(entry) > _HISTORY_CONTEXT_CHARS:
                    break
                lines.insert(0, entry)
                total += len(entry)
            if lines:
                parts.append("[Histórico recente]\n" + "\n".join(lines))

        return "\n\n".join(parts)

    def compact_session_memory(self, llm_model: str) -> str:
        """
        Usa o LLM para sintetizar o histórico de turnos em factos compactos
        e guarda o resultado em memory.json["session"].

        Retorna o texto dos factos gerados.

        Raises:
            RuntimeError: se o histórico estiver vazio ou o LLM falhar.
        """
        from langchain_ollama import OllamaLLM
        from .rag import strip_think  # import local para evitar ciclo

        turns = self.load_history()
        if not turns:
            raise RuntimeError("Histórico vazio — nada a compactar.")

        # Formatar turnos para o prompt
        lines: list[str] = []
        total = 0
        for turn in turns:
            prefix = "Utilizador" if turn.role == "user" else "Mnemosyne"
            entry = f"{prefix}: {turn.content}"
            if total + len(entry) > 8_000:
                break
            lines.append(entry)
            total += len(entry)

        history_text = "\n".join(lines)
        prompt = (
            "A seguir está uma conversa entre um utilizador e o assistente Mnemosyne. "
            "Extrai uma lista de factos compactos e relevantes desta conversa "
            "(máximo 10 pontos, uma frase cada). "
            "Foca-te em informação sobre o utilizador, as suas dúvidas recorrentes "
            "e os temas dos documentos que consultou. "
            "Responde em português.\n\n"
            f"Conversa:\n{history_text}\n\n"
            "Factos compactos:"
        )

        try:
            llm = OllamaLLM(model=llm_model, temperature=0, timeout=120)
            result = strip_think(llm.invoke(prompt))
        except Exception as exc:
            raise RuntimeError(f"Falha ao compactar memória: {exc}") from exc

        self.session_facts = result
        return result


# ── SessionMemory — retrocompatibilidade com main_window.py ───────────────────


@dataclass
class QueryRecord:
    question: str
    answer: str
    sources: list[str]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class SessionMemory:
    """
    Histórico in-memory da sessão actual.
    Mantido por retrocompatibilidade com main_window.py.
    Para persistência real, use MemoryStore.
    """

    def __init__(self, max_size: int = 50) -> None:
        self._records: list[QueryRecord] = []
        self._max_size = max_size

    def save_query(self, question: str, answer: str, sources: list[str]) -> None:
        self._records.append(
            QueryRecord(question=question, answer=answer, sources=sources)
        )
        if len(self._records) > self._max_size:
            self._records.pop(0)

    def find_similar(self, question: str, min_overlap: int = 2) -> QueryRecord | None:
        tokens = set(question.lower().split())
        best: QueryRecord | None = None
        best_score = 0
        for record in reversed(self._records):
            overlap = len(tokens & set(record.question.lower().split()))
            if overlap >= min_overlap and overlap > best_score:
                best = record
                best_score = overlap
        return best

    @property
    def records(self) -> list[QueryRecord]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()

    def as_turns(self) -> list[Turn]:
        """Converte para lista de Turn (para uso com MemoryStore)."""
        turns: list[Turn] = []
        for r in self._records:
            turns.append(Turn(role="user", content=r.question, ts=r.timestamp))
            turns.append(
                Turn(role="assistant", content=r.answer, sources=r.sources, ts=r.timestamp)
            )
        return turns
