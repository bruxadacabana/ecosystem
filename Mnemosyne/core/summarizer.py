"""
Geração de resumo geral dos documentos indexados.

Modos:
  stuff     — corpus total < _STUFF_CHAR_LIMIT: um único prompt com todo o contexto
  map-reduce — corpus maior: resumo por documento (Map) → resumo combinado (Reduce)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterator

from langchain_ollama import OllamaLLM

from .config import AppConfig
from .errors import SummarizationError
from .rag import strip_think

# ecosystem_client: serializa chamadas LLM síncronas via LOGOS (P3 background)
_eco_root = str(Path(__file__).parent.parent.parent)
if _eco_root not in sys.path:
    sys.path.insert(0, _eco_root)
from ecosystem_client import request_llm as _request_llm  # type: ignore  # noqa: E402


_STUFF_CHAR_LIMIT = 12_000   # chars totais abaixo dos quais usamos "stuff"
_MAP_K = 20                  # documentos únicos a recuperar para o Map
_MAP_CHUNK_CAP = 1_500       # chars máximos por documento na fase Map


# ── Prompts ───────────────────────────────────────────────────────────────────

_STUFF_PROMPT = (
    "Analise os trechos abaixo e forneça um resumo conciso "
    "dos principais temas e conteúdos encontrados na coleção de documentos. "
    "Responda em português.\n\n"
    "Trechos:\n{context}\n\n"
    "Resumo:"
)

_MAP_PROMPT = (
    "Resuma o trecho abaixo em 3 a 5 frases, capturando os pontos principais. "
    "Responda em português.\n\n"
    "Trecho:\n{chunk}\n\n"
    "Resumo parcial:"
)

_REDUCE_PROMPT = (
    "A seguir estão resumos parciais de documentos de uma coleção pessoal. "
    "Combine-os num resumo geral coeso, destacando os temas recorrentes, "
    "pontos principais e qualquer contraste relevante entre os documentos. "
    "Responda em português.\n\n"
    "Resumos parciais:\n{summaries}\n\n"
    "Resumo geral:"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_unique_docs(vectorstore: Any, k: int) -> list[tuple[str, str]]:
    """
    Retorna lista de (source, page_content) únicos por source.
    Usa similarity_search com query genérica para obter amostra representativa.
    """
    try:
        docs = vectorstore.similarity_search(
            "tema principal assunto conteúdo resumo", k=k
        )
    except Exception as exc:
        raise SummarizationError(f"Falha ao buscar documentos: {exc}") from exc

    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for doc in docs:
        src = doc.metadata.get("source", "")
        if src not in seen:
            seen.add(src)
            result.append((src, doc.page_content[:_MAP_CHUNK_CAP]))
    return result


# ── API pública ───────────────────────────────────────────────────────────────

def prepare_summary(vectorstore: Any, config: AppConfig) -> str:
    """
    Decide o modo (stuff vs map-reduce) e retorna o prompt final pronto.
    Usado pelo SummarizeWorker para geração síncrona simples.

    Para streaming com Map-Reduce use iter_summary().

    Raises:
        SummarizationError: se não houver documentos ou a busca falhar.
    """
    docs = _get_unique_docs(vectorstore, _MAP_K)
    if not docs:
        raise SummarizationError("Nenhum documento indexado para resumir.")

    total_chars = sum(len(content) for _, content in docs)

    if total_chars <= _STUFF_CHAR_LIMIT:
        context = "\n\n---\n".join(content for _, content in docs)
        return _STUFF_PROMPT.format(context=context)

    # Map-Reduce: resumir cada documento individualmente via LOGOS (P3)
    partial_summaries: list[str] = []
    for _, content in docs:
        try:
            resp = _request_llm(
                [{"role": "user", "content": _MAP_PROMPT.format(chunk=content)}],
                app="mnemosyne",
                model=config.llm_model,
                priority=3,
            )
            partial_summaries.append(strip_think(resp.get("message", {}).get("content", "")))
        except Exception:
            continue

    if not partial_summaries:
        raise SummarizationError("Falha ao gerar resumos parciais.")

    summaries_text = "\n\n---\n".join(partial_summaries)
    return _REDUCE_PROMPT.format(summaries=summaries_text)


def iter_summary(
    vectorstore: Any, config: AppConfig
) -> Iterator[str]:
    """
    Gerador que produz tokens do resumo final em streaming.
    Faz a fase Map de forma síncrona (necessário para construir o prompt Reduce),
    depois faz streaming da fase Reduce token a token.

    Raises:
        SummarizationError: se não houver documentos ou Map falhar completamente.
    """
    docs = _get_unique_docs(vectorstore, _MAP_K)
    if not docs:
        raise SummarizationError("Nenhum documento indexado para resumir.")

    total_chars = sum(len(content) for _, content in docs)

    if total_chars <= _STUFF_CHAR_LIMIT:
        context = "\n\n---\n".join(content for _, content in docs)
        prompt = _STUFF_PROMPT.format(context=context)
    else:
        # Fase Map via LOGOS (P3 background) — síncrona para construir o prompt Reduce
        partial_summaries: list[str] = []
        for _, content in docs:
            try:
                resp = _request_llm(
                    [{"role": "user", "content": _MAP_PROMPT.format(chunk=content)}],
                    app="mnemosyne",
                    model=config.llm_model,
                    priority=3,
                )
                partial_summaries.append(strip_think(resp.get("message", {}).get("content", "")))
            except Exception:
                continue

        if not partial_summaries:
            raise SummarizationError("Falha ao gerar resumos parciais (fase Map).")

        summaries_text = "\n\n---\n".join(partial_summaries)
        prompt = _REDUCE_PROMPT.format(summaries=summaries_text)

    # Fase Reduce (ou Stuff) em streaming
    llm_reduce = OllamaLLM(model=config.llm_model, temperature=0.2, timeout=180)
    yield from llm_reduce.stream(prompt)


def summarize_all(vectorstore: Any, config: AppConfig) -> str:
    """
    Sumarização síncrona completa (sem streaming). Mantida para compatibilidade.

    Raises:
        SummarizationError: se a busca ou geração falhar.
    """
    try:
        prompt = prepare_summary(vectorstore, config)
        resp = _request_llm(
            [{"role": "user", "content": prompt}],
            app="mnemosyne",
            model=config.llm_model,
            priority=3,
        )
        return strip_think(resp.get("message", {}).get("content", ""))
    except SummarizationError:
        raise
    except Exception as exc:
        raise SummarizationError(f"Falha ao gerar resumo: {exc}") from exc
