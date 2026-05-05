"""
Geração de artefatos de reflexão de conhecimento durante a indexação.

Um artefato de reflexão é uma síntese gerada pelo LLM a partir de um grupo de
chunks relacionados. É indexado junto ao corpus com boost de score (1.5×) para
perguntas conceituais/abstratas que se beneficiam de representações sintéticas.

Fluxo esperado (chamado por indexer.py):
  1. Agrupar chunks por arquivo-fonte (ou por tema)
  2. Para cada grupo com ≥ MIN_CHUNKS: chamar generate_reflection()
  3. Adicionar o Document retornado ao ChromaDB e ao BM25Index

A geração usa LOGOS (priority=3 — background) e nunca propaga exceções para
não interromper a indexação caso o LLM falhe ou esteja lento.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Callable

from langchain_core.documents import Document

from .config import AppConfig


def _strip_think(text: str) -> str:
    """Remove blocos <think>...</think> gerados pelo Qwen3. Duplicado de rag.strip_think
    para evitar importação circular (reflection ← rag ← reflection)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

# ecosystem_client: serializa chamadas LLM síncronas via LOGOS (P3 background)
_eco_root = str(Path(__file__).parent.parent.parent)
if _eco_root not in sys.path:
    sys.path.insert(0, _eco_root)
from ecosystem_client import request_llm as _request_llm  # type: ignore  # noqa: E402


# Número mínimo de chunks para gerar uma reflexão (menos que isso é pouco contexto)
MIN_CHUNKS = 3

# Número máximo de chars de contexto passado ao LLM (evita estourar a janela)
_MAX_CONTEXT_CHARS = 6_000

# Boost de score aplicado no retrieval para reflexões de primeira ordem
REFLECTION_BOOST = 1.5

# Boost de score para meta-reflexões (consolidação de 3 reflexões de ordem 1)
META_REFLECTION_BOOST = 1.8

# Threshold de similaridade cosine mínima entre reflexão e query para incluir no contexto
REFLECTION_COSINE_THRESHOLD = 0.65


_PROMPT = (
    "Você recebeu {n} fragmentos de texto sobre um mesmo tema extraídos de documentos pessoais.\n"
    "Sintetize os conceitos-chave, identifique conexões não-óbvias e gere um artefato de "
    "conhecimento estruturado em 150-300 palavras.\n"
    "Escreva em português. Seja preciso e informativo — evite generalidades.\n\n"
    "Fragmentos:\n{context}\n\n"
    "Artefato de conhecimento:"
)


def _chunk_key(doc: Document) -> str:
    """Identificador reproduzível para um chunk — hash SHA-1 dos primeiros 200 chars."""
    return hashlib.sha1(doc.page_content[:200].encode()).hexdigest()[:16]


def _build_context(chunks: list[Document]) -> str:
    """
    Concatena chunks em texto de contexto, respeitando o limite de chars.
    Trunca chunks individuais proporcionalmente se necessário.
    """
    per_chunk_limit = _MAX_CONTEXT_CHARS // max(len(chunks), 1)
    parts: list[str] = []
    for i, doc in enumerate(chunks, 1):
        snippet = doc.page_content[:per_chunk_limit].strip()
        src = Path(doc.metadata.get("source", "")).name
        parts.append(f"[{i}] {src}\n{snippet}")
    return "\n\n---\n".join(parts)


def generate_reflection(
    chunks: list[Document],
    config: AppConfig,
    *,
    progress_cb: Callable[[str], None] | None = None,
    group_label: str = "",
) -> Document | None:
    """
    Gera um artefato de reflexão a partir de um grupo de chunks relacionados.

    Args:
        chunks:      Lista de chunks do mesmo tema/arquivo (mínimo MIN_CHUNKS).
        config:      AppConfig com llm_model e base_url do Ollama.
        progress_cb: Callback opcional para emitir progresso na UI
                     (ex: lambda msg: worker.progress.emit(msg)).
        group_label: Rótulo descritivo do grupo para mensagens de progresso
                     (ex: "cap3.epub" ou "grupo 3/12").

    Returns:
        Document com metadata type="reflection", boost=1.5, order=1
        e source_chunks=[hash1, hash2, ...]; ou None se a geração falhar.

    Raises:
        Nunca — erros são logados internamente e retornam None.
    """
    if len(chunks) < MIN_CHUNKS:
        return None

    if progress_cb:
        label = f" ({group_label})" if group_label else ""
        progress_cb(f"Gerando reflexão{label}…")

    context = _build_context(chunks)
    prompt = _PROMPT.format(n=len(chunks), context=context)

    try:
        resp = _request_llm(
            [{"role": "user", "content": prompt}],
            app="mnemosyne",
            model=config.llm_model,
            priority=3,
        )
        raw = resp.get("message", {}).get("content", "").strip()
        content = _strip_think(raw).strip()
    except Exception as exc:
        # Nunca propagar — a indexação não pode ser bloqueada por falha de reflexão
        _ = exc
        return None

    if not content:
        return None

    # Identificar fontes únicas para rastreabilidade
    source_files: list[str] = []
    seen: set[str] = set()
    for doc in chunks:
        src = doc.metadata.get("source", "")
        if src and src not in seen:
            seen.add(src)
            source_files.append(src)

    source_chunks = [_chunk_key(doc) for doc in chunks]

    # Tema derivado do nome do primeiro arquivo-fonte (sem extensão)
    theme = Path(source_files[0]).stem if source_files else "unknown"

    return Document(
        page_content=content,
        metadata={
            "type": "reflection",
            "order": 1,
            "boost": REFLECTION_BOOST,
            "source_chunks": source_chunks,
            "source_files": source_files,
            "theme": theme,
        },
    )


def generate_meta_reflection(
    reflections: list[Document],
    config: AppConfig,
    *,
    progress_cb: Callable[[str], None] | None = None,
) -> Document | None:
    """
    Consolida 3 reflexões de ordem 1 sobre o mesmo tema numa meta-reflexão (ordem 2).

    Chamado por indexer.py quando ≥ 3 reflexões do mesmo tema estão presentes.
    A meta-reflexão recebe boost=1.8× e as reflexões de origem podem ser removidas
    para evitar redundância (decisão do indexer.py).

    Returns:
        Document com order=2, boost=1.8, ou None se falhar.
    """
    if len(reflections) < 3:
        return None

    if progress_cb:
        progress_cb("Consolidando reflexões em meta-reflexão…")

    context = _build_context(reflections)
    prompt = (
        "Você recebeu {n} sínteses sobre um mesmo tema. "
        "Consolide-as numa única representação de conhecimento de segunda ordem: "
        "mais abstrata, mais abrangente e sem redundâncias. "
        "150-300 palavras. Responda em português.\n\n"
        "Sínteses:\n{context}\n\n"
        "Meta-síntese:"
    ).format(n=len(reflections), context=context)

    try:
        resp = _request_llm(
            [{"role": "user", "content": prompt}],
            app="mnemosyne",
            model=config.llm_model,
            priority=3,
        )
        raw = resp.get("message", {}).get("content", "").strip()
        content = _strip_think(raw).strip()
    except Exception:
        return None

    if not content:
        return None

    # Agregar todas as fontes e chunk-keys das reflexões de origem
    all_source_files: list[str] = []
    all_source_chunks: list[str] = []
    seen_files: set[str] = set()
    for ref in reflections:
        for sf in ref.metadata.get("source_files", []):
            if sf not in seen_files:
                seen_files.add(sf)
                all_source_files.append(sf)
        all_source_chunks.extend(ref.metadata.get("source_chunks", []))

    theme = reflections[0].metadata.get("theme", "unknown")

    return Document(
        page_content=content,
        metadata={
            "type": "reflection",
            "order": 2,
            "boost": META_REFLECTION_BOOST,
            "source_chunks": all_source_chunks,
            "source_files": all_source_files,
            "theme": theme,
        },
    )
