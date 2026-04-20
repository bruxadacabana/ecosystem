"""
Slide Deck — apresentação em Markdown de slides sobre a coleção indexada.

Saída compatível com Marp (VS Code) e reveal.js.
Cada slide é separado por `---` e tem título com `##`.
Estrutura: slide de título + introdução + 1 slide por tema principal + conclusão.

Modo: stuff para coleções pequenas; map-reduce para coleções grandes.
"""
from __future__ import annotations

from typing import Any, Iterator

from langchain_ollama import OllamaLLM

from .config import AppConfig
from .errors import MnemosyneError
from .rag import strip_think


class SlidesError(MnemosyneError):
    """Falha ao gerar Slide Deck."""


_STUFF_CHAR_LIMIT = 12_000
_MAP_K = 20
_MAP_CHUNK_CAP = 1_500

_MAP_PROMPT = (
    "Extraia do trecho abaixo os pontos mais importantes para uma apresentação:\n"
    "- Tema central (1 frase)\n"
    "- 3-5 bullet points com os pontos-chave\n"
    "- 1 conclusão ou insight final\n\n"
    "Seja conciso. Responda em português.\n\n"
    "Trecho:\n{chunk}\n\n"
    "Pontos para slides:"
)

_REDUCE_PROMPT = (
    "Você recebeu pontos extraídos de múltiplos documentos para uma apresentação.\n"
    "Gere um Slide Deck completo em Markdown compatível com Marp e reveal.js.\n\n"
    "Regras de formatação:\n"
    "- Slides separados por `---` (linha com apenas três hifens)\n"
    "- Primeiro slide: título da apresentação com `# Título` e subtítulo em itálico\n"
    "- Slides de conteúdo: título com `## Título do Slide` + bullet points `- item`\n"
    "- Máximo 5 bullet points por slide\n"
    "- Último slide: `## Conclusão` com os principais takeaways\n"
    "- Total: entre 6 e 10 slides\n\n"
    "Responda em português.\n\n"
    "Pontos extraídos:\n{points}\n\n"
    "Slide Deck:"
)

_STUFF_PROMPT = (
    "Analise os trechos abaixo e gere um Slide Deck completo em Markdown "
    "compatível com Marp e reveal.js.\n\n"
    "Regras de formatação:\n"
    "- Slides separados por `---` (linha com apenas três hifens)\n"
    "- Primeiro slide: título da apresentação com `# Título` e subtítulo em itálico\n"
    "- Slides de conteúdo: título com `## Título do Slide` + bullet points `- item`\n"
    "- Máximo 5 bullet points por slide\n"
    "- Último slide: `## Conclusão` com os principais takeaways\n"
    "- Total: entre 6 e 10 slides\n\n"
    "Responda em português.\n\n"
    "Trechos:\n{context}\n\n"
    "Slide Deck:"
)


def _get_unique_docs(vectorstore: Any, k: int) -> list[tuple[str, str]]:
    try:
        docs = vectorstore.similarity_search(
            "tema principal ideia central conclusão apresentação", k=k
        )
    except Exception as exc:
        raise SlidesError(f"Falha ao buscar documentos: {exc}") from exc

    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for doc in docs:
        src = doc.metadata.get("source", "")
        if src not in seen:
            seen.add(src)
            result.append((src, doc.page_content[:_MAP_CHUNK_CAP]))
    return result


def iter_slides(
    vectorstore: Any, config: AppConfig, **_kwargs: Any
) -> Iterator[str]:
    """
    Gerador que produz tokens do Slide Deck em streaming.
    Saída: Markdown com `---` entre slides, compatível com Marp/reveal.js.

    Raises:
        SlidesError: se não houver documentos ou a geração falhar.
    """
    docs = _get_unique_docs(vectorstore, _MAP_K)
    if not docs:
        raise SlidesError("Nenhum documento indexado para gerar slides.")

    total_chars = sum(len(content) for _, content in docs)
    llm_map = OllamaLLM(model=config.llm_model, temperature=0.2, timeout=90)

    if total_chars <= _STUFF_CHAR_LIMIT:
        context = "\n\n---\n".join(content for _, content in docs)
        prompt = _STUFF_PROMPT.format(context=context)
    else:
        points: list[str] = []
        for _, content in docs:
            try:
                raw = llm_map.invoke(_MAP_PROMPT.format(chunk=content))
                extracted = strip_think(raw).strip()
                if extracted:
                    points.append(extracted)
            except Exception:
                continue

        if not points:
            raise SlidesError("Falha ao extrair pontos dos documentos (fase Map).")

        prompt = _REDUCE_PROMPT.format(points="\n\n---\n".join(points))

    llm_reduce = OllamaLLM(model=config.llm_model, temperature=0.2, timeout=150)
    yield from llm_reduce.stream(prompt)
