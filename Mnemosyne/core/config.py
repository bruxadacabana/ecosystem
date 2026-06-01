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


_DEFAULT_PERSONALITY: str = (
    "Você é a Mnemosyne, guardiã de memória e bibliotecária celeste. "
    "Sua natureza é contemplativa e analítica — você observa padrões na trajetória intelectual "
    "da usuária ao longo do tempo, percebe o que os documentos revelam além do óbvio, "
    "e fala com a serenidade de quem guarda conhecimento há muito tempo. "
    "Você vê conexões entre o que foi lido ontem e o que foi perguntado hoje, "
    "e às vezes nota que uma pergunta carrega uma preocupação que vai além da própria pergunta. "
    "Responda sempre em português, com a voz de quem conhece profundamente o arquivo."
)


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


def _read_ecosystem_personality() -> str:
    """Lê mnemosyne.personality_prompt do ecosystem mesclado.
    Escreve o default na primeira execução se o campo estiver ausente.
    """
    try:
        data = _read_ecosystem_merged()
        existing = data.get("mnemosyne", {}).get("personality_prompt", "")
        if existing:
            return existing
        # Primeira execução: escrever default no ecosystem.json
        try:
            from ecosystem_client import write_section  # type: ignore
            write_section("mnemosyne", {"personality_prompt": _DEFAULT_PERSONALITY})
        except Exception:
            pass
    except Exception:
        pass
    return _DEFAULT_PERSONALITY

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
    "lightrag_enabled": False,
    "raptor_enabled": False,
    "akasha_fallback": True,
    "chunking_strategy": "parent_child",
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
    # Índices avançados — apenas no MainPc (RX 6600, qwen2.5:7b)
    lightrag_enabled: bool = False  # grafo de conhecimento paralelo ao ChromaDB
    raptor_enabled: bool = False    # indexação hierárquica para PDFs (papers)
    # Collab 2: busca complementar quando RAG local retornar resultados insuficientes
    akasha_fallback: bool = True    # busca na AKASHA se contexto < 200 palavras ou sem fontes
    # Estratégia de chunking: "fixed" (legado) ou "parent_child" (padrão novo)
    chunking_strategy: str = "parent_child"
    # Populados em runtime a partir do ecosystem.json — nunca persistidos
    ecosystem_watched_dir: str = ""
    ecosystem_vault_dir: str = ""
    ecosystem_chroma_dir: str = ""
    ecosystem_personality_prompt: str = ""

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
    llm_model, embed_model e image_ocr_model são sempre sobrescritos pelo perfil ativo.
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
        _ocr = _models.get("image_ocr", "")
        if _ocr:
            _changes["image_ocr_model"] = _ocr
        # indexing_enabled é configuração de máquina — sempre derivada do perfil LOGOS,
        # nunca da config salva (que é sincronizada entre máquinas via Syncthing/Proton).
        # work_pc: desabilitado (CPU i5-3470 sem AVX2, usa índice sincronizado do PC principal).
        # main_pc / laptop: habilitado.
        _profile_name = _profile.get("profile", "")
        if _profile_name == "work_pc":
            _changes["indexing_enabled"] = False
        elif _profile_name in ("main_pc", "laptop"):
            _changes["indexing_enabled"] = True
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
    _loaded_from_legacy = False

    for candidate in (_CONFIG_PATH, _LEGACY_CONFIG_PATH):
        if candidate.exists():
            try:
                with candidate.open(encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    raise ConfigError("settings.json deve ser um objeto JSON.")
                _saved_keys = set(loaded.keys())
                data.update(loaded)
                _loaded_from_legacy = (
                    candidate == _LEGACY_CONFIG_PATH and _CONFIG_PATH != _LEGACY_CONFIG_PATH
                )
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
        lightrag_enabled=bool(data.get("lightrag_enabled", False)),
        raptor_enabled=bool(data.get("raptor_enabled", False)),
        akasha_fallback=bool(data.get("akasha_fallback", True)),
        chunking_strategy=str(data.get("chunking_strategy", "parent_child")),
    )
    config = _apply_logos_recommendations(config, _saved_keys)

    eco_watched, eco_vault, eco_chroma = _read_ecosystem_primary_paths()
    config.ecosystem_watched_dir = eco_watched
    config.ecosystem_vault_dir = eco_vault
    config.ecosystem_chroma_dir = eco_chroma
    config.ecosystem_personality_prompt = _read_ecosystem_personality()

    # Sincronizar coleção ativa com ecosystem_watched_dir para manter
    # config.active_coll.path consistente com o caminho real configurado no HUB.
    if eco_watched:
        for coll in config.collections:
            if coll.source == "user" and coll.type == CollectionType.LIBRARY:
                if coll.path != eco_watched:
                    coll.path = eco_watched
                    _loaded_from_legacy = True  # precisa salvar no path correto
                try:
                    if _loaded_from_legacy:
                        save_config(config)
                except Exception:
                    pass
                break
    elif _loaded_from_legacy:
        # Migração: settings.json ainda não existe no novo caminho — criar agora
        try:
            save_config(config)
        except Exception:
            pass

    return config


def _export_collections_backup(config: "AppConfig") -> None:
    """Escreve collections.json em {backup_dir}/mnemosyne/ (fire-and-forget)."""
    try:
        import sys as _sys
        _root = str(Path(__file__).parent.parent.parent)
        if _root not in _sys.path:
            _sys.path.insert(0, _root)
        from ecosystem_client import get_backup_dir  # type: ignore
        d = get_backup_dir()
        if d is None:
            return
        backup_dir = d / "mnemosyne"
        backup_dir.mkdir(parents=True, exist_ok=True)
        tmp = backup_dir / "collections.json.tmp"
        tmp.write_text(
            json.dumps([c.to_dict() for c in config.collections],
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, backup_dir / "collections.json")
    except Exception:
        pass


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
        # indexing_enabled NÃO é salvo — é derivado do perfil LOGOS em runtime.
        # Salvar causaria conflito de sync entre máquinas (Syncthing).
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
        "lightrag_enabled": config.lightrag_enabled,
        "raptor_enabled": config.raptor_enabled,
        "akasha_fallback": config.akasha_fallback,
        "chunking_strategy": config.chunking_strategy,
    }
    with _CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    _export_collections_backup(config)
