"""
Configuração do Mnemosyne — lê config.json, usa defaults se ausente.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .collections import CollectionConfig, CollectionType, sync_ecosystem_collections
from .errors import ConfigError


def _resolve_config_path() -> Path:
    """Retorna {mnemosyne.config_path}/settings.json se definido no ecosystem.json."""
    try:
        import os as _os
        appdata = _os.environ.get("APPDATA", "")
        candidates = [
            Path(appdata) / "ecosystem" / "ecosystem.json",
            Path.home() / ".local" / "share" / "ecosystem" / "ecosystem.json",
        ]
        for eco_path in candidates:
            if eco_path.exists():
                data = json.loads(eco_path.read_text(encoding="utf-8"))
                config_dir = data.get("mnemosyne", {}).get("config_path", "")
                if config_dir:
                    return Path(config_dir) / "settings.json"
    except Exception:
        pass
    return Path(__file__).parent.parent / "config.json"


_CONFIG_PATH = _resolve_config_path()
_LEGACY_CONFIG_PATH = Path(__file__).parent.parent / "config.json"

_DEFAULTS: dict = {
    "llm_model": "qwen2.5:7b",    # RAG: qualidade adequada para síntese de documentos longos
    "embed_model": "",
    "chunk_size": 1800,
    "chunk_overlap": 250,
    "retriever_k": 4,
    "collections": [],
    "active_collection": "",
    "ecosystem_enabled": {},
    "auto_index_on_change": True,
    "background_index_enabled": True,
    "relevance_decay_days": 30,
    "semantic_chunking": False,
    "indexing_only": False,
    "dark_mode": True,
    "reranking_enabled": True,
    "reranking_top_n": 6,
}


@dataclass
class AppConfig:
    llm_model: str
    embed_model: str
    chunk_size: int
    chunk_overlap: int
    retriever_k: int
    collections: list[CollectionConfig] = field(default_factory=list)
    active_collection: str = ""
    ecosystem_enabled: dict[str, bool] = field(default_factory=dict)
    auto_index_on_change: bool = True
    background_index_enabled: bool = True
    relevance_decay_days: int = 30
    semantic_chunking: bool = False
    indexing_only: bool = False
    dark_mode: bool = True
    reranking_enabled: bool = True
    reranking_top_n: int = 6

    # ── Propriedades derivadas da coleção ativa ───────────────────────────────

    @property
    def active_coll(self) -> CollectionConfig | None:
        """Retorna a coleção ativa, ou a primeira habilitada como fallback."""
        for c in self.collections:
            if c.name == self.active_collection:
                return c
        # fallback: primeira coleção user-defined habilitada, depois qualquer
        for c in self.collections:
            if c.source == "user" and c.enabled:
                return c
        return self.collections[0] if self.collections else None

    @property
    def watched_dir(self) -> str:
        coll = self.active_coll
        return coll.path if coll else ""

    @property
    def vault_dir(self) -> str:
        """Path da coleção ativa se for VAULT, senão vazio."""
        coll = self.active_coll
        return coll.path if coll and coll.type == CollectionType.VAULT else ""

    @property
    def persist_dir(self) -> str:
        coll = self.active_coll
        return coll.persist_dir if coll else ""

    @property
    def mnemosyne_dir(self) -> str:
        coll = self.active_coll
        return coll.mnemosyne_dir if coll else ""

    @property
    def collection_type(self) -> str:
        coll = self.active_coll
        return coll.type.value if coll else "library"

    @property
    def is_configured(self) -> bool:
        return bool(self.llm_model and self.embed_model and self.active_coll and self.watched_dir)


def _migrate_legacy(data: dict) -> dict:
    """
    Migra config antigo {watched_dir, vault_dir} para o novo formato {collections}.
    Não-destrutivo: preserva campos existentes.
    """
    if data.get("collections"):
        return data  # já no novo formato

    watched = data.get("watched_dir", "")
    vault = data.get("vault_dir", "")
    collections: list[dict] = []

    if watched:
        collections.append(CollectionConfig(
            name="Biblioteca",
            path=watched,
            type=CollectionType.LIBRARY,
        ).to_dict())

    if vault:
        collections.append(CollectionConfig(
            name="Vault Obsidian",
            path=vault,
            type=CollectionType.VAULT,
        ).to_dict())

    data["collections"] = collections
    data["active_collection"] = "Biblioteca" if watched else ""
    return data


def load_config() -> AppConfig:
    """
    Carrega config.json; usa defaults para chaves ausentes.
    Migra automaticamente do formato legado (watched_dir / vault_dir).
    Sincroniza coleções de ecossistema detectadas via ecosystem.json.

    Raises:
        ConfigError: se config.json existir mas for inválido.
    """
    data: dict = dict(_DEFAULTS)

    for candidate in (_CONFIG_PATH, _LEGACY_CONFIG_PATH):
        if candidate.exists():
            try:
                with candidate.open(encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    raise ConfigError("settings.json deve ser um objeto JSON.")
                data.update(loaded)
            except json.JSONDecodeError as exc:
                raise ConfigError(f"settings.json inválido: {exc}") from exc
            break

    data = _migrate_legacy(data)

    # Desserializar coleções
    raw_colls: list[dict] = data.get("collections", [])
    collections = [CollectionConfig.from_dict(c) for c in raw_colls if isinstance(c, dict)]

    # Sincronizar coleções do ecossistema
    ecosystem_enabled: dict[str, bool] = data.get("ecosystem_enabled", {})
    collections = sync_ecosystem_collections(collections, ecosystem_enabled)

    return AppConfig(
        llm_model=str(data.get("llm_model", "")),
        embed_model=str(data.get("embed_model", "")),
        chunk_size=int(data.get("chunk_size", 1800)),
        chunk_overlap=int(data.get("chunk_overlap", 250)),
        retriever_k=int(data.get("retriever_k", 4)),
        collections=collections,
        active_collection=str(data.get("active_collection", "")),
        ecosystem_enabled=ecosystem_enabled,
        auto_index_on_change=bool(data.get("auto_index_on_change", True)),
        background_index_enabled=bool(data.get("background_index_enabled", True)),
        relevance_decay_days=int(data.get("relevance_decay_days", 30)),
        semantic_chunking=bool(data.get("semantic_chunking", False)),
        indexing_only=bool(data.get("indexing_only", False)),
        dark_mode=bool(data.get("dark_mode", True)),
        reranking_enabled=bool(data.get("reranking_enabled", True)),
        reranking_top_n=int(data.get("reranking_top_n", 6)),
    )


def save_config(config: AppConfig) -> None:
    """Persiste AppConfig em settings.json (ou config.json legado)."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "llm_model": config.llm_model,
        "embed_model": config.embed_model,
        "chunk_size": config.chunk_size,
        "chunk_overlap": config.chunk_overlap,
        "retriever_k": config.retriever_k,
        "collections": [c.to_dict() for c in config.collections],
        "active_collection": config.active_collection,
        "ecosystem_enabled": config.ecosystem_enabled,
        "auto_index_on_change": config.auto_index_on_change,
        "background_index_enabled": config.background_index_enabled,
        "relevance_decay_days": config.relevance_decay_days,
        "semantic_chunking": config.semantic_chunking,
        "indexing_only": config.indexing_only,
        "dark_mode": config.dark_mode,
        "reranking_enabled": config.reranking_enabled,
        "reranking_top_n": config.reranking_top_n,
    }
    with _CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
