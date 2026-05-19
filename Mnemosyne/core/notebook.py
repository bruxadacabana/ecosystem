"""
Mnemosyne — Notebook: conversa temática persistente.

Cada notebook é uma conversa salva com nome, coleções associadas e histórico
próprio. O conceito de "chat" no Mnemosyne é sempre um notebook — nunca uma
sessão temporária.

Estrutura de arquivos de um notebook:
    {data_dir}/notebooks/{id}/
        metadata.json   — campos do dataclass Notebook
        history.jsonl   — mensagens (append-only)
        memory.json     — contexto RAG da sessão
        studio/         — outputs do Studio deste notebook
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Notebook:
    """Conversa temática persistente.

    Atributos
    ---------
    id
        UUID4 gerado na criação; também serve de nome do diretório.
    name
        Nome legível dado pela usuária (ex: "Notas de Filosofia").
    created_at
        Timestamp ISO 8601 da criação.
    updated_at
        Timestamp ISO 8601 da última modificação (mensagem, rename, etc.).
    collection_names
        Coleções que este notebook consulta. Lista vazia = todas habilitadas.
    description
        Descrição opcional do tema ou propósito do notebook.
    """

    id: str
    name: str
    created_at: str
    updated_at: str
    collection_names: list[str]
    description: str = ""
    themes: list[str] = None       # type: ignore[assignment]
    keywords: list[str] = None     # type: ignore[assignment]
    top_sources: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.themes is None:
            self.themes = []
        if self.keywords is None:
            self.keywords = []
        if self.top_sources is None:
            self.top_sources = []

    # ------------------------------------------------------------------
    # Serialização
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "collection_names": self.collection_names,
            "description": self.description,
            "themes": self.themes,
            "keywords": self.keywords,
            "top_sources": self.top_sources,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Notebook":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            collection_names=list(data.get("collection_names", [])),
            description=str(data.get("description", "")),
            themes=list(data.get("themes", [])),
            keywords=list(data.get("keywords", [])),
            top_sources=list(data.get("top_sources", [])),
        )

    @classmethod
    def new(
        cls,
        name: str,
        collection_names: list[str] | None = None,
        description: str = "",
    ) -> "Notebook":
        """Cria um Notebook novo com UUID e timestamps preenchidos."""
        now = _now_iso()
        return cls(
            id=str(uuid4()),
            name=name,
            created_at=now,
            updated_at=now,
            collection_names=collection_names or [],
            description=description,
        )
