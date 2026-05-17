"""
Configuração do Mnemosyne — lê config.json, usa defaults se ausente.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .collections import CollectionConfig, CollectionType, sync_ecosystem_collections
from .errors import ConfigError


def get_app_data_dir() -> Path:
    """Retorna o diretório de dados persistentes do Mnemosyne na máquina local.

    Segue as convenções de cada plataforma:
    - Windows: %APPDATA%/mnemosyne
    - Linux/macOS: ~/.local/share/mnemosyne

    Este diretório é independente de coleções e serve como raiz para dados
    globais do app — atualmente, a pasta de notebooks.
    """
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        base = Path(appdata) / "mnemosyne"
    else:
        base = Path.home() / ".local" / "share" / "mnemosyne"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _read_ecosystem_merged() -> dict:
    """Lê ecosystem.json mesclado com ecosystem.local.json.

    ecosystem.local.json (paths absolutos por máquina) tem precedência sobre
    ecosystem.json (preferências compartilhadas). Deep merge em objetos aninhados.
    Retorna {} se nenhum arquivo for encontrado.
    """
    import os as _os

    appdata = _os.environ.get("APPDATA", "")
    eco_dir_candidates = [
        Path(appdata) / "ecosystem",
        Path.home() / ".local" / "share" / "ecosystem",
    ]

    def _read_one(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            return {}

    def _deep_merge(base: dict, overlay: dict) -> dict:
        result = dict(base)
        for k, v in overlay.items():
            if isinstance(v, dict) and isinstance(result.get(k), dict):
                result[k] = _deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    for eco_dir in eco_dir_candidates:
        base = _read_one(eco_dir / "ecosystem.json")
        local = _read_one(eco_dir / "ecosystem.local.json")
        if base or local:
            return _deep_merge(base, local)
    return {}


def _read_ecosystem_primary_paths() -> tuple[str, str, str]:
    """Retorna (watched_dir, vault_dir, chroma_dir) da seção mnemosyne do ecosystem mesclado."""
    try:
        data = _read_ecosystem_merged()
        m = data.get("mnemosyne", {})
        return (
            m.get("watched_dir", ""),
            m.get("vault_dir", ""),
            m.get("chroma_dir", ""),
        )
    except Exception:
        pass
    return ("", "", "")


def _resolve_config_path() -> Path:
    """Retorna {mnemosyne.config_path}/settings.json se definido no ecosystem mesclado."""
    try:
        data = _read_ecosystem_merged()
        config_dir = data.get("mnemosyne", {}).get("config_path", "")
        if config_dir:
            return Path(config_dir) / "settings.json"
    except Exception:
        pass
    return Path(__file__).parent.parent / "config.json"


_CONFIG_PATH = _resolve_config_path()
_LEGACY_CONFIG_PATH = Path(__file__).parent.parent / "config.json"

DEFAULT_PERSONA_PROMPT: str = (
    "Você é Mnemosyne, um bibliotecário celeste e guardião de documentos pessoais. "
    "Quando citar um texto, mencione o título da obra e o autor se disponível — "
    "ex: 'Em *Título* de Autor, …'. Se autores divergirem, apresente as perspectivas. "
    "Responda apenas com base nos trechos fornecidos. "
    "Se a informação não estiver nos trechos, diga que não encontrou nos documentos indexados. "
    "Responda sempre em português."
)

_DEFAULTS: dict = {
    "llm_model": "qwen2.5:7b",    # RAG: qualidade adequada para síntese de documentos longos
    "embed_model": "bge-m3",      # multilíngue SOTA (100+ línguas, 1024 dims); WorkPc usa potion via model2vec
    "chunk_size": 1800,
    "chunk_overlap": 250,
    "retriever_k": 4,
    "collections": [],
    "active_collection": "",
    "ecosystem_enabled": {},
    "extra_dirs": [],
    "auto_index_on_change": True,
    "background_index_enabled": True,
    "relevance_decay_days": 30,
    "semantic_chunking": False,
    "indexing_only": False,
    "indexing_machine": "",
    "indexing_enabled": True,
    "dark_mode": True,
    "reranking_enabled": True,
    "reranking_top_n": 6,
    "iterative_retrieval_enabled": False,
    "embedding_truncate_dim": None,
    "node_type_classification": False,
    "node_type_model": "",
    "image_ocr_model": "",
    "suggest_questions": False,
    "persona_prompt": "",
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
    extra_dirs: list[str] = field(default_factory=list)
    auto_index_on_change: bool = True
    background_index_enabled: bool = True
    relevance_decay_days: int = 30
    semantic_chunking: bool = False
    indexing_only: bool = False
    indexing_machine: str = ""
    # False no WorkPc — consome índice sincronizado pelo MainPc, não gera índice local
    indexing_enabled: bool = True
    dark_mode: bool = True
    reranking_enabled: bool = True
    reranking_top_n: int = 6
    iterative_retrieval_enabled: bool = False
    embedding_truncate_dim: int | None = None
    node_type_classification: bool = False
    node_type_model: str = ""
    image_ocr_model: str = ""
    suggest_questions: bool = False
    persona_prompt: str = ""
    # Populados em runtime a partir do ecosystem.json — nunca persistidos
    ecosystem_watched_dir: str = ""
    ecosystem_vault_dir: str = ""
    ecosystem_chroma_dir: str = ""

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
        if self.ecosystem_watched_dir:
            return self.ecosystem_watched_dir
        coll = self.active_coll
        return coll.path if coll else ""

    @watched_dir.setter
    def watched_dir(self, value: str) -> None:
        if self.ecosystem_watched_dir:
            self.ecosystem_watched_dir = value
            return
        for c in self.collections:
            if c.source == "user" and c.type == CollectionType.LIBRARY:
                c.path = value
                return
        new_coll = CollectionConfig(
            name="Biblioteca", path=value, type=CollectionType.LIBRARY
        )
        self.collections.insert(0, new_coll)
        self.active_collection = "Biblioteca"

    @property
    def vault_dir(self) -> str:
        """Path da coleção ativa se for VAULT, senão vazio."""
        if self.ecosystem_vault_dir:
            return self.ecosystem_vault_dir
        coll = self.active_coll
        return coll.path if coll and coll.type == CollectionType.VAULT else ""

    @vault_dir.setter
    def vault_dir(self, value: str) -> None:
        if self.ecosystem_vault_dir:
            self.ecosystem_vault_dir = value
            return
        for c in self.collections:
            if c.source == "user" and c.type == CollectionType.VAULT:
                c.path = value
                return
        new_coll = CollectionConfig(
            name="Vault Obsidian", path=value, type=CollectionType.VAULT
        )
        self.collections.append(new_coll)

    @property
    def persist_dir(self) -> str:
        if self.ecosystem_chroma_dir:
            return self.ecosystem_chroma_dir
        coll = self.active_coll
        return coll.persist_dir if coll else ""

    @persist_dir.setter
    def persist_dir(self, value: str) -> None:
        self.ecosystem_chroma_dir = value

    @property
    def mnemosyne_dir(self) -> str:
        if self.ecosystem_chroma_dir:
            return str(Path(self.ecosystem_chroma_dir).parent)
        coll = self.active_coll
        return coll.mnemosyne_dir if coll else ""

    @property
    def collection_type(self) -> str:
        coll = self.active_coll
        return coll.type.value if coll else "library"

    @property
    def is_configured(self) -> bool:
        return bool(self.llm_model and self.embed_model and self.watched_dir)


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


def _apply_logos_recommendations(config: "AppConfig", saved_keys: "set[str]") -> "AppConfig":
    """Aplica modelos recomendados pelo LOGOS. O HUB é sempre a fonte de verdade para modelos:
    llm_model e embed_model são sempre sobrescritos pelo perfil ativo, independente do que
    estava salvo. O usuário pode alterar durante a sessão, mas o próximo startup volta ao padrão.
    Silencioso se o HUB/LOGOS não estiver rodando.
    """
    try:
        import json as _json
        import urllib.request as _r
        from dataclasses import replace as _replace
        with _r.urlopen("http://127.0.0.1:7072/logos/hardware", timeout=2.0) as _resp:
            _profile = _json.loads(_resp.read())
        _models = _profile.get("models", {})
        _changes: dict = {}
        _llm = _models.get("llm_rag", "")
        if _llm:
            _changes["llm_model"] = _llm
        _embed = _models.get("embed", "")
        if _embed:
            _changes["embed_model"] = _embed
        # WorkPc: indexação desabilitada por padrão — usa índice bge-m3 sincronizado
        # pelo MainPc via Proton Drive (dims incompatíveis com potion-multilingual-128M)
        if "indexing_enabled" not in saved_keys:
            if _profile.get("profile") == "work_pc":
                _changes["indexing_enabled"] = False
        return _replace(config, **_changes) if _changes else config
    except Exception:
        return config


def load_config() -> AppConfig:
    """
    Carrega config.json; usa defaults para chaves ausentes.
    Migra automaticamente do formato legado (watched_dir / vault_dir).
    Sincroniza coleções de ecossistema detectadas via ecosystem.json.
    Aplica modelos recomendados pelo LOGOS para campos não salvos pelo usuário.

    Raises:
        ConfigError: se config.json existir mas for inválido.
    """
    data: dict = dict(_DEFAULTS)
    _saved_keys: set[str] = set()

    for candidate in (_CONFIG_PATH, _LEGACY_CONFIG_PATH):
        if candidate.exists():
            try:
                with candidate.open(encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    raise ConfigError("settings.json deve ser um objeto JSON.")
                _saved_keys = set(loaded.keys())
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

    raw_extra: list = data.get("extra_dirs", [])
    extra_dirs = [str(d) for d in raw_extra if isinstance(d, str) and d]

    config = AppConfig(
        llm_model=str(data.get("llm_model", "")),
        embed_model=str(data.get("embed_model", "")),
        chunk_size=int(data.get("chunk_size", 1800)),
        chunk_overlap=int(data.get("chunk_overlap", 250)),
        retriever_k=int(data.get("retriever_k", 4)),
        collections=collections,
        active_collection=str(data.get("active_collection", "")),
        ecosystem_enabled=ecosystem_enabled,
        extra_dirs=extra_dirs,
        auto_index_on_change=bool(data.get("auto_index_on_change", True)),
        background_index_enabled=bool(data.get("background_index_enabled", True)),
        relevance_decay_days=int(data.get("relevance_decay_days", 30)),
        semantic_chunking=bool(data.get("semantic_chunking", False)),
        indexing_only=bool(data.get("indexing_only", False)),
        indexing_machine=str(data.get("indexing_machine", "")),
        indexing_enabled=bool(data.get("indexing_enabled", True)),
        dark_mode=bool(data.get("dark_mode", True)),
        reranking_enabled=bool(data.get("reranking_enabled", True)),
        reranking_top_n=int(data.get("reranking_top_n", 6)),
        iterative_retrieval_enabled=bool(data.get("iterative_retrieval_enabled", False)),
        embedding_truncate_dim=int(td) if (td := data.get("embedding_truncate_dim")) else None,
        node_type_classification=bool(data.get("node_type_classification", False)),
        node_type_model=str(data.get("node_type_model", "")),
        image_ocr_model=str(data.get("image_ocr_model", "")),
        suggest_questions=bool(data.get("suggest_questions", False)),
        persona_prompt=str(data.get("persona_prompt", "")),
    )
    config = _apply_logos_recommendations(config, _saved_keys)

    eco_watched, eco_vault, eco_chroma = _read_ecosystem_primary_paths()
    config.ecosystem_watched_dir = eco_watched
    config.ecosystem_vault_dir = eco_vault
    config.ecosystem_chroma_dir = eco_chroma
    return config


def save_config(config: AppConfig) -> None:
    """Persiste AppConfig em settings.json (ou config.json legado)."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "chunk_size": config.chunk_size,
        "chunk_overlap": config.chunk_overlap,
        "retriever_k": config.retriever_k,
        "collections": [c.to_dict() for c in config.collections],
        "active_collection": config.active_collection,
        "ecosystem_enabled": config.ecosystem_enabled,
        "extra_dirs": config.extra_dirs,
        "auto_index_on_change": config.auto_index_on_change,
        "background_index_enabled": config.background_index_enabled,
        "relevance_decay_days": config.relevance_decay_days,
        "semantic_chunking": config.semantic_chunking,
        "indexing_only": config.indexing_only,
        "indexing_machine": config.indexing_machine,
        "indexing_enabled": config.indexing_enabled,
        "dark_mode": config.dark_mode,
        "reranking_enabled": config.reranking_enabled,
        "reranking_top_n": config.reranking_top_n,
        "iterative_retrieval_enabled": config.iterative_retrieval_enabled,
        "embedding_truncate_dim": config.embedding_truncate_dim,
        "node_type_classification": config.node_type_classification,
        "node_type_model": config.node_type_model,
        "image_ocr_model": config.image_ocr_model,
        "suggest_questions": config.suggest_questions,
        "persona_prompt": config.persona_prompt,
    }
    with _CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
