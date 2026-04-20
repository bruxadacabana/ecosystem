"""
Relatório de Pesquisa Completo — geração multi-seção via Map-Reduce.

Seções fixas (6):
  1. Sumário Executivo
  2. Principais Temas e Findings
  3. Análise por Fonte
  4. Convergências e Divergências
  5. Lacunas Identificadas
  6. Referências

Para coleções pequenas usa "stuff" (um único prompt).
Para coleções grandes usa Map-Reduce: extrai metadados por fonte na fase Map,
depois gera o relatório completo na fase Reduce com streaming.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from langchain_ollama import OllamaLLM

from .config import AppConfig
from .errors import MnemosyneError
from .rag import strip_think


class ReportError(MnemosyneError):
    """Falha ao gerar Relatório de Pesquisa."""


_STUFF_CHAR_LIMIT = 10_000
_MAP_K = 30
_MAP_CHUNK_CAP = 1_500

_MAP_PROMPT = (
    "Analise o trecho abaixo e extraia:\n"
    "1. Fonte (nome do arquivo se disponível): {source}\n"
    "2. Temas abordados (2-4 tópicos)\n"
    "3. Principais argumentos ou conclusões\n"
    "4. Dados, datas ou fatos concretos mencionados\n"
    "5. Limitações, críticas ou ressalvas presentes\n\n"
    "Seja conciso e factual. Responda em português.\n\n"
    "Trecho:\n{chunk}\n\n"
    "Extração:"
)

_REDUCE_PROMPT = (
    "Você recebeu extrações detalhadas de múltiplas fontes de uma coleção de pesquisa.\n"
    "Gere um Relatório de Pesquisa Completo em Markdown com exatamente estas seis seções:\n\n"
    "## 1. Sumário Executivo\n"
    "(2-3 parágrafos resumindo o escopo, os achados centrais e as conclusões principais)\n\n"
    "## 2. Principais Temas e Findings\n"
    "(para cada tema recorrente: título do tema + bullet points com os achados específicos)\n\n"
    "## 3. Análise por Fonte\n"
    "(para cada fonte identificada: nome/título + contribuição principal em 2-3 frases)\n\n"
    "## 4. Convergências e Divergências\n"
    "(onde as fontes concordam vs. onde apresentam perspectivas opostas ou complementares)\n\n"
    "## 5. Lacunas Identificadas\n"
    "(o que está ausente, pouco desenvolvido ou que mereceria investigação adicional)\n\n"
    "## 6. Referências\n"
    "(lista das fontes identificadas com trecho representativo de cada uma)\n\n"
    "Seja analítico e preciso. Use bullet points nas seções 2-5. Responda em português.\n\n"
    "Extrações:\n{extractions}\n\n"
    "Relatório:"
)

_STUFF_PROMPT = (
    "Analise os trechos abaixo e gere um Relatório de Pesquisa Completo em Markdown "
    "com exatamente estas seis seções:\n\n"
    "## 1. Sumário Executivo\n"
    "(2-3 parágrafos resumindo o escopo, os achados centrais e as conclusões principais)\n\n"
    "## 2. Principais Temas e Findings\n"
    "(para cada tema recorrente: título do tema + bullet points com os achados específicos)\n\n"
    "## 3. Análise por Fonte\n"
    "(para cada fonte identificada: nome/título + contribuição principal em 2-3 frases)\n\n"
    "## 4. Convergências e Divergências\n"
    "(onde as fontes concordam vs. onde apresentam perspectivas opostas ou complementares)\n\n"
    "## 5. Lacunas Identificadas\n"
    "(o que está ausente, pouco desenvolvido ou que mereceria investigação adicional)\n\n"
    "## 6. Referências\n"
    "(lista das fontes identificadas com trecho representativo de cada uma)\n\n"
    "Seja analítico e preciso. Use bullet points nas seções 2-5. Responda em português.\n\n"
    "Trechos:\n{context}\n\n"
    "Relatório:"
)


def _get_docs_by_source(vectorstore: Any, k: int) -> list[tuple[str, str]]:
    """Retorna (source, page_content) únicos por source, amostrados com query abrangente."""
    try:
        docs = vectorstore.similarity_search(
            "tema argumento conclusão dado fato análise pesquisa", k=k
        )
    except Exception as exc:
        raise ReportError(f"Falha ao buscar documentos: {exc}") from exc

    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for doc in docs:
        src = doc.metadata.get("source", "")
        if src not in seen:
            seen.add(src)
            result.append((src, doc.page_content[:_MAP_CHUNK_CAP]))
    return result


def iter_report(
    vectorstore: Any, config: AppConfig, **_kwargs: Any
) -> Iterator[str]:
    """
    Gerador que produz tokens do Relatório de Pesquisa em streaming.
    Fase Map síncrona (extração por fonte) → streaming da fase Reduce.

    Raises:
        ReportError: se não houver documentos ou a geração falhar.
    """
    docs = _get_docs_by_source(vectorstore, _MAP_K)
    if not docs:
        raise ReportError("Nenhum documento indexado para gerar relatório.")

    total_chars = sum(len(content) for _, content in docs)
    llm_map = OllamaLLM(model=config.llm_model, temperature=0.1, timeout=120)

    if total_chars <= _STUFF_CHAR_LIMIT:
        context = "\n\n---\n".join(content for _, content in docs)
        prompt = _STUFF_PROMPT.format(context=context)
    else:
        extractions: list[str] = []
        for src, content in docs:
            source_label = Path(src).name if src else "desconhecida"
            try:
                raw = llm_map.invoke(
                    _MAP_PROMPT.format(source=source_label, chunk=content)
                )
                extractions.append(strip_think(raw))
            except Exception:
                continue

        if not extractions:
            raise ReportError("Falha ao extrair informações das fontes (fase Map).")

        prompt = _REDUCE_PROMPT.format(extractions="\n\n---\n".join(extractions))

    llm_reduce = OllamaLLM(model=config.llm_model, temperature=0.1, timeout=240)
    yield from llm_reduce.stream(prompt)
