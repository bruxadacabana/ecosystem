"""
Table of Contents — índice temático hierárquico da coleção indexada.

Gera uma hierarquia Tema > Subtema > Tópico específico em Markdown,
útil para orientação quando a coleção é grande e a usuária não sabe
exatamente o que está indexado.

Modo: stuff para coleções pequenas; map-reduce para coleções grandes
(cada fonte contribui com seus tópicos; a fase Reduce consolida).
"""
from __future__ import annotations

from typing import Any, Iterator

from langchain_ollama import OllamaLLM

from .config import AppConfig
from .errors import MnemosyneError
from .rag import strip_think


class TocError(MnemosyneError):
    """Falha ao gerar Índice de Temas."""


_STUFF_CHAR_LIMIT = 12_000
_MAP_K = 25
_MAP_CHUNK_CAP = 1_200

_MAP_PROMPT = (
    "Liste os temas e subtemas abordados no trecho abaixo.\n"
    "Formato: um tópico por linha, indentação com dois espaços para subtópicos.\n"
    "Seja conciso — apenas os temas, sem explicações.\n"
    "Responda em português.\n\n"
    "Trecho:\n{chunk}\n\n"
    "Temas:"
)

_REDUCE_PROMPT = (
    "Você recebeu listas de temas extraídas de múltiplos documentos de uma coleção.\n"
    "Consolide-as num Índice de Temas hierárquico em Markdown, eliminando duplicatas "
    "e agrupando subtemas relacionados sob temas principais.\n\n"
    "Formato esperado:\n"
    "## Tema Principal A\n"
    "- Subtema A1\n"
    "  - Tópico específico\n"
    "- Subtema A2\n\n"
    "## Tema Principal B\n"
    "- ...\n\n"
    "Use no máximo 8 temas principais. Ordene do mais abrangente ao mais específico.\n"
    "Responda em português.\n\n"
    "Listas de temas:\n{topics}\n\n"
    "Índice:"
)

_STUFF_PROMPT = (
    "Analise os trechos abaixo e gere um Índice de Temas hierárquico em Markdown, "
    "mostrando os temas e subtemas cobertos pela coleção.\n\n"
    "Formato esperado:\n"
    "## Tema Principal A\n"
    "- Subtema A1\n"
    "  - Tópico específico\n"
    "- Subtema A2\n\n"
    "Use no máximo 8 temas principais. Ordene do mais abrangente ao mais específico.\n"
    "Responda em português.\n\n"
    "Trechos:\n{context}\n\n"
    "Índice:"
)


def _get_unique_docs(vectorstore: Any, k: int) -> list[tuple[str, str]]:
    try:
        docs = vectorstore.similarity_search(
            "tema assunto tópico conteúdo área conhecimento", k=k
        )
    except Exception as exc:
        raise TocError(f"Falha ao buscar documentos: {exc}") from exc

    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for doc in docs:
        src = doc.metadata.get("source", "")
        if src not in seen:
            seen.add(src)
            result.append((src, doc.page_content[:_MAP_CHUNK_CAP]))
    return result


def iter_toc(
    vectorstore: Any, config: AppConfig, **_kwargs: Any
) -> Iterator[str]:
    """
    Gerador que produz tokens do Índice de Temas em streaming.

    Raises:
        TocError: se não houver documentos ou a geração falhar.
    """
    docs = _get_unique_docs(vectorstore, _MAP_K)
    if not docs:
        raise TocError("Nenhum documento indexado para gerar índice de temas.")

    total_chars = sum(len(content) for _, content in docs)
    llm_map = OllamaLLM(model=config.llm_model, temperature=0.1, timeout=90)

    if total_chars <= _STUFF_CHAR_LIMIT:
        context = "\n\n---\n".join(content for _, content in docs)
        prompt = _STUFF_PROMPT.format(context=context)
    else:
        topic_lists: list[str] = []
        for _, content in docs:
            try:
                raw = llm_map.invoke(_MAP_PROMPT.format(chunk=content))
                extracted = strip_think(raw).strip()
                if extracted:
                    topic_lists.append(extracted)
            except Exception:
                continue

        if not topic_lists:
            raise TocError("Falha ao extrair temas dos documentos (fase Map).")

        prompt = _REDUCE_PROMPT.format(topics="\n\n---\n".join(topic_lists))

    llm_reduce = OllamaLLM(model=config.llm_model, temperature=0.1, timeout=120)
    yield from llm_reduce.stream(prompt)
