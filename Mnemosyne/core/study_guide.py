"""
Study Guide Estruturado — guia de estudo completo da coleção indexada.

Seções fixas (4):
  1. Conceitos-Chave  (termo + definição 2-3 frases)
  2. Termos Técnicos  (glossário conciso)
  3. Questões de Revisão  (perguntas abertas para reflexão)
  4. Tópicos para Aprofundar  (lacunas e direções de estudo futuro)

Diferente do NotebookGuide automático (resumo + perguntas sugeridas pós-indexação),
este guia é gerado sob demanda e tem estrutura educacional completa.
"""
from __future__ import annotations

from typing import Any, Iterator

from langchain_ollama import OllamaLLM

from .config import AppConfig
from .errors import MnemosyneError
from .rag import strip_think


class StudyGuideError(MnemosyneError):
    """Falha ao gerar Study Guide."""


_STUFF_CHAR_LIMIT = 12_000
_MAP_K = 20
_MAP_CHUNK_CAP = 1_500

_MAP_PROMPT = (
    "Extraia do trecho abaixo:\n"
    "- Conceitos e termos importantes (com definição breve)\n"
    "- Ideias principais que um estudante deve compreender\n"
    "- Perguntas que o conteúdo levanta\n\n"
    "Seja conciso. Responda em português.\n\n"
    "Trecho:\n{chunk}\n\n"
    "Extração:"
)

_REDUCE_PROMPT = (
    "Com base nas extrações abaixo de uma coleção de estudo, "
    "gere um Study Guide completo em Markdown com exatamente estas quatro seções:\n\n"
    "## Conceitos-Chave\n"
    "(lista de conceitos centrais, cada um com definição de 2-3 frases acessíveis)\n\n"
    "## Termos Técnicos\n"
    "(glossário: **termo** — definição concisa de 1 frase)\n\n"
    "## Questões de Revisão\n"
    "(8-12 perguntas abertas que exijam compreensão, não memorização)\n\n"
    "## Tópicos para Aprofundar\n"
    "(temas que ficaram pouco desenvolvidos e merecem investigação adicional)\n\n"
    "Responda em português.\n\n"
    "Extrações:\n{extractions}\n\n"
    "Study Guide:"
)

_STUFF_PROMPT = (
    "Analise os trechos abaixo e gere um Study Guide completo em Markdown "
    "com exatamente estas quatro seções:\n\n"
    "## Conceitos-Chave\n"
    "(lista de conceitos centrais, cada um com definição de 2-3 frases acessíveis)\n\n"
    "## Termos Técnicos\n"
    "(glossário: **termo** — definição concisa de 1 frase)\n\n"
    "## Questões de Revisão\n"
    "(8-12 perguntas abertas que exijam compreensão, não memorização)\n\n"
    "## Tópicos para Aprofundar\n"
    "(temas que ficaram pouco desenvolvidos e merecem investigação adicional)\n\n"
    "Responda em português.\n\n"
    "Trechos:\n{context}\n\n"
    "Study Guide:"
)


def _get_unique_docs(vectorstore: Any, k: int) -> list[tuple[str, str]]:
    try:
        docs = vectorstore.similarity_search(
            "conceito definição termo técnico aprender compreender", k=k
        )
    except Exception as exc:
        raise StudyGuideError(f"Falha ao buscar documentos: {exc}") from exc

    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for doc in docs:
        src = doc.metadata.get("source", "")
        if src not in seen:
            seen.add(src)
            result.append((src, doc.page_content[:_MAP_CHUNK_CAP]))
    return result


def iter_study_guide(
    vectorstore: Any, config: AppConfig, **_kwargs: Any
) -> Iterator[str]:
    """
    Gerador que produz tokens do Study Guide em streaming.
    Fase Map síncrona → streaming da fase Reduce.

    Raises:
        StudyGuideError: se não houver documentos ou a geração falhar.
    """
    docs = _get_unique_docs(vectorstore, _MAP_K)
    if not docs:
        raise StudyGuideError("Nenhum documento indexado para gerar guia de estudo.")

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
            raise StudyGuideError("Falha ao extrair conteúdo dos documentos (fase Map).")

        prompt = _REDUCE_PROMPT.format(extractions="\n\n---\n".join(extractions))

    llm_reduce = OllamaLLM(model=config.llm_model, temperature=0.2, timeout=180)
    yield from llm_reduce.stream(prompt)
