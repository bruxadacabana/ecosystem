"""
Timeline — linha do tempo extraída dos documentos indexados.

Extrai eventos com data/período e os ordena cronologicamente.
Formato de saída: lista Markdown `- **[data]** — [evento] *(fonte)*`

Modo: stuff para coleções pequenas; map-reduce para coleções grandes
(cada fonte contribui com seus eventos; a fase Reduce consolida e ordena).
"""
from __future__ import annotations

from typing import Any, Iterator

from langchain_ollama import OllamaLLM

from .config import AppConfig
from .errors import MnemosyneError
from .rag import strip_think


class TimelineError(MnemosyneError):
    """Falha ao gerar Timeline."""


_STUFF_CHAR_LIMIT = 12_000
_MAP_K = 25
_MAP_CHUNK_CAP = 1_500

_MAP_PROMPT = (
    "Extraia do trecho abaixo todos os eventos que tenham data ou período identificável.\n"
    "Para cada evento, escreva uma linha no formato:\n"
    "[data ou período] | [descrição concisa do evento]\n\n"
    "Se não houver eventos com data, escreva: (sem eventos datados)\n"
    "Responda em português.\n\n"
    "Trecho:\n{chunk}\n\n"
    "Eventos:"
)

_REDUCE_PROMPT = (
    "Você recebeu listas de eventos extraídos de múltiplos documentos.\n"
    "Consolide-os numa Linha do Tempo em Markdown, "
    "ordenando cronologicamente do mais antigo ao mais recente.\n\n"
    "Formato de cada entrada:\n"
    "- **[data ou período]** — [descrição do evento]\n\n"
    "Regras:\n"
    "- Elimine duplicatas (mantenha a versão mais completa)\n"
    "- Agrupe eventos do mesmo período quando fizer sentido\n"
    "- Se a data for imprecisa (ex: 'início do século XX'), inclua mesmo assim\n"
    "- Eventos sem qualquer referência temporal devem ser omitidos\n\n"
    "Responda em português.\n\n"
    "Eventos extraídos:\n{events}\n\n"
    "Linha do Tempo:"
)

_STUFF_PROMPT = (
    "Analise os trechos abaixo e extraia todos os eventos com data ou período identificável.\n"
    "Gere uma Linha do Tempo em Markdown, ordenada cronologicamente.\n\n"
    "Formato de cada entrada:\n"
    "- **[data ou período]** — [descrição do evento]\n\n"
    "Se não houver eventos datados suficientes, indique isso claramente.\n"
    "Responda em português.\n\n"
    "Trechos:\n{context}\n\n"
    "Linha do Tempo:"
)


def _get_unique_docs(vectorstore: Any, k: int) -> list[tuple[str, str]]:
    try:
        docs = vectorstore.similarity_search(
            "data ano evento período história cronologia aconteceu", k=k
        )
    except Exception as exc:
        raise TimelineError(f"Falha ao buscar documentos: {exc}") from exc

    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for doc in docs:
        src = doc.metadata.get("source", "")
        if src not in seen:
            seen.add(src)
            result.append((src, doc.page_content[:_MAP_CHUNK_CAP]))
    return result


def iter_timeline(
    vectorstore: Any, config: AppConfig, **_kwargs: Any
) -> Iterator[str]:
    """
    Gerador que produz tokens da Linha do Tempo em streaming.
    A query de retrieval favorece documentos com datas e eventos.

    Raises:
        TimelineError: se não houver documentos ou a geração falhar.
    """
    docs = _get_unique_docs(vectorstore, _MAP_K)
    if not docs:
        raise TimelineError("Nenhum documento indexado para gerar linha do tempo.")

    total_chars = sum(len(content) for _, content in docs)
    llm_map = OllamaLLM(model=config.llm_model, temperature=0.0, timeout=90)

    if total_chars <= _STUFF_CHAR_LIMIT:
        context = "\n\n---\n".join(content for _, content in docs)
        prompt = _STUFF_PROMPT.format(context=context)
    else:
        event_lists: list[str] = []
        for _, content in docs:
            try:
                raw = llm_map.invoke(_MAP_PROMPT.format(chunk=content))
                extracted = strip_think(raw).strip()
                if extracted and "(sem eventos datados)" not in extracted.lower():
                    event_lists.append(extracted)
            except Exception:
                continue

        if not event_lists:
            raise TimelineError("Nenhum evento datado encontrado nos documentos.")

        prompt = _REDUCE_PROMPT.format(events="\n\n---\n".join(event_lists))

    llm_reduce = OllamaLLM(model=config.llm_model, temperature=0.0, timeout=120)
    yield from llm_reduce.stream(prompt)
