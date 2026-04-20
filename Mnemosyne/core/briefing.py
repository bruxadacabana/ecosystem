"""
Briefing Document — sumário executivo estruturado da coleção indexada.

Seções fixas: Temas Principais · Achados · Insights Acionáveis · Divergências
Modo: stuff para coleções pequenas; map-reduce para coleções grandes.
"""
from __future__ import annotations

from typing import Any, Iterator

from langchain_ollama import OllamaLLM

from .config import AppConfig
from .errors import BriefingError
from .rag import strip_think


_STUFF_CHAR_LIMIT = 12_000
_MAP_K = 20
_MAP_CHUNK_CAP = 1_500

_MAP_PROMPT = (
    "Extraia do trecho abaixo, em tópicos curtos:\n"
    "- Temas abordados\n"
    "- Fatos ou conclusões relevantes\n"
    "- Qualquer posição controversa ou limitação mencionada\n\n"
    "Seja conciso. Responda em português.\n\n"
    "Trecho:\n{chunk}\n\n"
    "Extração:"
)

_REDUCE_PROMPT = (
    "Você recebeu extrações de múltiplos documentos de uma coleção de pesquisa.\n"
    "Gere um Briefing Document em Markdown com exatamente estas quatro seções:\n\n"
    "## Temas Principais\n"
    "(os grandes temas recorrentes na coleção)\n\n"
    "## Achados\n"
    "(conclusões, dados e fatos mais relevantes encontrados nas fontes)\n\n"
    "## Insights Acionáveis\n"
    "(o que pode ser feito, investigado ou aprofundado a partir deste material)\n\n"
    "## Divergências e Limitações\n"
    "(perspectivas contraditórias entre fontes, lacunas ou ressalvas importantes)\n\n"
    "Use bullet points em cada seção. Seja direto e denso — este é um sumário executivo.\n"
    "Responda em português.\n\n"
    "Extrações:\n{extractions}\n\n"
    "Briefing:"
)

_STUFF_PROMPT = (
    "Analise os trechos abaixo e gere um Briefing Document em Markdown "
    "com exatamente estas quatro seções:\n\n"
    "## Temas Principais\n"
    "(os grandes temas recorrentes na coleção)\n\n"
    "## Achados\n"
    "(conclusões, dados e fatos mais relevantes encontrados nas fontes)\n\n"
    "## Insights Acionáveis\n"
    "(o que pode ser feito, investigado ou aprofundado a partir deste material)\n\n"
    "## Divergências e Limitações\n"
    "(perspectivas contraditórias entre fontes, lacunas ou ressalvas importantes)\n\n"
    "Use bullet points em cada seção. Seja direto e denso — este é um sumário executivo.\n"
    "Responda em português.\n\n"
    "Trechos:\n{context}\n\n"
    "Briefing:"
)


def _get_unique_docs(vectorstore: Any, k: int) -> list[tuple[str, str]]:
    """Retorna (source, page_content) únicos por source, amostrados com query temática."""
    try:
        docs = vectorstore.similarity_search(
            "tema principal achado conclusão insight divergência", k=k
        )
    except Exception as exc:
        raise BriefingError(f"Falha ao buscar documentos: {exc}") from exc

    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for doc in docs:
        src = doc.metadata.get("source", "")
        if src not in seen:
            seen.add(src)
            result.append((src, doc.page_content[:_MAP_CHUNK_CAP]))
    return result


def iter_briefing(
    vectorstore: Any, config: AppConfig, **_kwargs: Any
) -> Iterator[str]:
    """
    Gerador que produz tokens do Briefing Document em streaming.
    Fase Map síncrona (extração por documento) → streaming da fase Reduce.

    Raises:
        BriefingError: se não houver documentos ou a geração falhar.
    """
    docs = _get_unique_docs(vectorstore, _MAP_K)
    if not docs:
        raise BriefingError("Nenhum documento indexado para gerar briefing.")

    total_chars = sum(len(content) for _, content in docs)
    llm_map = OllamaLLM(model=config.llm_model, temperature=0.2, timeout=120)

    if total_chars <= _STUFF_CHAR_LIMIT:
        context = "\n\n---\n".join(content for _, content in docs)
        prompt = _STUFF_PROMPT.format(context=context)
    else:
        extractions: list[str] = []
        for _, content in docs:
            try:
                raw = llm_map.invoke(_MAP_PROMPT.format(chunk=content))
                extractions.append(strip_think(raw))
            except Exception:
                continue

        if not extractions:
            raise BriefingError("Falha ao extrair informações dos documentos (fase Map).")

        prompt = _REDUCE_PROMPT.format(extractions="\n\n---\n".join(extractions))

    llm_reduce = OllamaLLM(model=config.llm_model, temperature=0.2, timeout=180)
    yield from llm_reduce.stream(prompt)
