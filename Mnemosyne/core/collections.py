"""
Coleções do Mnemosyne: Vault (memória pessoal) e Library (arquivo externo).

Cada coleção tem seu próprio vectorstore em {path}/.mnemosyne/chroma_db.
Coleções de ecossistema são auto-detectadas via ecosystem.json.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class CollectionType(Enum):
    VAULT = "vault"
    LIBRARY = "library"


@dataclass
class CollectionConfig:
    name: str
    path: str
    type: CollectionType
    enabled: bool = True
    source: str = "user"       # "user" | "ecosystem"
    ecosystem_key: str = ""    # ex: "kosmos.archive_path"

    @property
    def persist_dir(self) -> str:
        if self.path:
            return str(Path(self.path) / ".mnemosyne" / "chroma_db")
        return ""

    @property
    def mnemosyne_dir(self) -> str:
        if self.path:
            return str(Path(self.path) / ".mnemosyne")
        return ""

    @property
    def exists(self) -> bool:
        return bool(self.path) and os.path.isdir(self.path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "type": self.type.value,
            "enabled": self.enabled,
            "source": self.source,
            "ecosystem_key": self.ecosystem_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CollectionConfig:
        try:
            ctype = CollectionType(data.get("type", "library"))
        except ValueError:
            ctype = CollectionType.LIBRARY
        return cls(
            name=str(data.get("name", "")),
            path=str(data.get("path", "")),
            type=ctype,
            enabled=bool(data.get("enabled", True)),
            source=str(data.get("source", "user")),
            ecosystem_key=str(data.get("ecosystem_key", "")),
        )


# Fontes do ecossistema que o Mnemosyne pode ouvir automaticamente.
# AETHER excluído intencionalmente (pasta de ficção/escrita, não biblioteca).
ECOSYSTEM_SOURCES: list[tuple[str, str, str]] = [
    # (label legível, ecosystem_key, nome padrão da coleção)
    ("KOSMOS — arquivo", "kosmos.archive_path", "KOSMOS"),
    ("AKASHA — arquivo", "akasha.archive_path", "AKASHA"),
    ("Hermes — saída",   "hermes.output_dir",   "Hermes"),
]


def _read_ecosystem() -> dict:
    try:
        import sys as _sys
        _root = str(Path(__file__).parent.parent.parent)
        if _root not in _sys.path:
            _sys.path.insert(0, _root)
        from ecosystem_client import read_ecosystem  # type: ignore
        return read_ecosystem()
    except Exception:
        return {}


def sync_ecosystem_collections(
    collections: list[CollectionConfig],
    ecosystem_enabled: dict[str, bool] | None = None,
) -> list[CollectionConfig]:
    """
    Lê ecosystem.json e sincroniza coleções de tipo 'ecosystem'.
    Adiciona novas coleções detectadas, atualiza caminhos existentes.
    Coleções de usuário (source='user') nunca são tocadas.
    `ecosystem_enabled`: estado ligado/desligado persistido no config.
    """
    eco = _read_ecosystem()
    if not eco:
        return collections

    if ecosystem_enabled is None:
        ecosystem_enabled = {}

    # Coleções user-defined permanecem intactas; só reconstruímos as de ecossistema
    user_colls = [c for c in collections if c.source == "user"]
    existing_eco: dict[str, CollectionConfig] = {
        c.ecosystem_key: c
        for c in collections
        if c.source == "ecosystem" and c.ecosystem_key
    }

    updated: list[CollectionConfig] = list(user_colls)

    for _label, eco_key, default_name in ECOSYSTEM_SOURCES:
        parts = eco_key.split(".", 1)
        path = eco.get(parts[0], {}).get(parts[1], "") if len(parts) == 2 else ""
        if not path or not os.path.isdir(path):
            continue

        if eco_key in existing_eco:
            coll = existing_eco[eco_key]
            coll.path = path  # atualiza caminho se mudou
            if eco_key in ecosystem_enabled:
                coll.enabled = ecosystem_enabled[eco_key]
            updated.append(coll)
        else:
            updated.append(CollectionConfig(
                name=default_name,
                path=path,
                type=CollectionType.LIBRARY,
                enabled=ecosystem_enabled.get(eco_key, True),
                source="ecosystem",
                ecosystem_key=eco_key,
            ))

    return updated


def available_ecosystem_paths() -> list[tuple[str, str, str]]:
    """
    Retorna (label, ecosystem_key, path) para caminhos detectados no ecosystem.json.
    Só inclui paths que existem no disco.
    """
    eco = _read_ecosystem()
    result: list[tuple[str, str, str]] = []
    for label, eco_key, _name in ECOSYSTEM_SOURCES:
        parts = eco_key.split(".", 1)
        path = eco.get(parts[0], {}).get(parts[1], "") if len(parts) == 2 else ""
        if path and os.path.isdir(path):
            result.append((label, eco_key, path))
    return result
