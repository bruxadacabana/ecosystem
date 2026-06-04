"""LightRAG — grafo de conhecimento paralelo ao ChromaDB do Mnemosyne.

Wrapper com inicialização lazy e fallback silencioso.
Se lightrag-hku não estiver instalado ou o LOGOS estiver fora do ar,
todas as funções retornam sem erro e sem bloquear.

Inferência (LLM + embeddings) passa SEMPRE pelo LOGOS, que é OpenAI-compatível
em {base}/v1 — Ollama foi descartado no ecossistema.
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import AppConfig

log = logging.getLogger("mnemosyne.lightrag")

_rag_instance: object | None = None
_init_attempted: bool = False


def _get_working_dir(config: AppConfig) -> Path:
    """Retorna {chroma_dir}/../lightrag/ como diretório de persistência."""
    if config.persist_dir:
        return Path(config.persist_dir).parent / "lightrag"
    return Path.home() / ".local" / "share" / "mnemosyne" / "lightrag"


async def init_lightrag(config: AppConfig) -> bool:
    """Inicializa instância LightRAG. Retorna True se bem-sucedido.

    Seguro para chamar múltiplas vezes — tentativa única guardada em flag.
    """
    global _rag_instance, _init_attempted
    if _init_attempted:
        return _rag_instance is not None
    _init_attempted = True

    try:
        from lightrag import LightRAG  # type: ignore[import]
        from lightrag.utils import EmbeddingFunc  # type: ignore[import]
        from lightrag.llm.openai import (  # type: ignore[import]
            openai_complete_if_cache,
            openai_embed,
        )
    except ImportError:
        log.info("lightrag: lightrag-hku não instalado — funcionalidade desativada")
        return False

    try:
        from ecosystem_client import get_inference_url  # type: ignore[import]

        # Toda inferência passa pelo LOGOS (OpenAI-compatível em {base}/v1).
        openai_base = f"{get_inference_url().rstrip('/')}/v1"

        working_dir = str(_get_working_dir(config))
        Path(working_dir).mkdir(parents=True, exist_ok=True)

        embed_model = config.embed_model or "bge-m3"
        embed_dim = 1024 if "bge-m3" in embed_model else 128
        llm_model_name = config.llm_model or "qwen2.5:7b"

        async def _llm(
            prompt: str,
            system_prompt: str | None = None,
            history_messages: list | None = None,
            keyword_extraction: bool = False,
            **kwargs,
        ) -> str:
            return await openai_complete_if_cache(
                llm_model_name,
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages or [],
                base_url=openai_base,
                api_key="not-needed",
                keyword_extraction=keyword_extraction,
                **kwargs,
            )

        async def _embed(texts: list[str]) -> list[list[float]]:
            return await openai_embed(
                texts,
                model=embed_model,
                base_url=openai_base,
                api_key="not-needed",
            )

        _rag_instance = LightRAG(
            working_dir=working_dir,
            llm_model_func=_llm,
            llm_model_name=llm_model_name,
            embedding_func=EmbeddingFunc(
                embedding_dim=embed_dim,
                max_token_size=8192,
                func=_embed,
            ),
        )
        # LightRAG 1.x exige init explícito dos storages (e do pipeline status);
        # sem isto, ainsert/aquery falham mesmo com a instância construída.
        await _rag_instance.initialize_storages()  # type: ignore[union-attr]
        log.info("lightrag: inicializado em %s (LOGOS %s, llm=%s, embed=%s)",
                 working_dir, openai_base, llm_model_name, embed_model)
        return True
    except Exception as exc:
        log.warning("lightrag: falha na inicialização — %s", exc)
        return False


async def insert_text(text: str, config: AppConfig) -> None:
    """Insere texto no grafo para extração de entidades.

    Chama init_lightrag se ainda não inicializado. Silencioso em falhas.
    Chamado pelo indexer após inserir chunks no ChromaDB.
    """
    if not config.lightrag_enabled:
        return
    if _rag_instance is None:
        ok = await init_lightrag(config)
        if not ok:
            return
    try:
        await _rag_instance.ainsert(text)  # type: ignore[union-attr]
        log.debug("lightrag: texto inserido (%d chars)", len(text))
    except Exception as exc:
        log.debug("lightrag.insert: %s", exc)


async def query_hybrid(question: str, config: AppConfig) -> str:
    """Consulta o grafo em modo hybrid para perguntas relacionais.

    Retorna string de contexto adicional, vazia se falhar.
    Integrado em prepare_ask antes da montagem do contexto final.
    """
    if not config.lightrag_enabled or _rag_instance is None:
        return ""
    try:
        from lightrag import QueryParam  # type: ignore[import]
        result = await _rag_instance.aquery(  # type: ignore[union-attr]
            question, param=QueryParam(mode="hybrid")
        )
        return result or ""
    except Exception as exc:
        log.debug("lightrag.query: %s", exc)
        return ""


def _looks_relational(query: str) -> bool:
    """Heurística: True se a query parece pedir relações entre entidades.

    Detecta dois padrões:
    1. Palavras-chave relacionais explícitas (autor, colaborou, entre, quem…)
    2. Presença de ≥2 nomes próprios no corpo da query
    """
    q_lower = query.lower()
    relational_kws = {
        "quem", "autor", "autores", "escreveu", "publicou", "colaborou",
        "colaboração", "parceria", "relação", "ligação", "vínculo", "entre",
        "associação", "baseado em", "inspirado por", "referenciado por",
        "who", "author", "wrote", "published", "collaborated", "relation",
        "between", "link", "connection", "based on", "inspired by",
    }
    if any(kw in q_lower for kw in relational_kws):
        return True
    # ≥2 nomes próprios (capitalizado, alfabético) após a primeira palavra
    words = query.split()
    proper = sum(
        1 for w in words[1:]
        if w and w[0].isupper() and re.match(r"^[A-ZÀ-Ý][a-zA-Zà-ÿ\-]+$", w)
    )
    return proper >= 2


def is_available() -> bool:
    """True se a instância LightRAG está inicializada e pronta."""
    return _rag_instance is not None


def has_index(config: AppConfig) -> bool:
    """True se o diretório do grafo existe e contém arquivos de dados."""
    wd = _get_working_dir(config)
    if not wd.exists():
        return False
    return any(wd.iterdir())
