"""
Blog Post — texto narrativo acessível sobre o conteúdo da coleção.

Gera um texto corrido com introdução cativante, desenvolvimento em parágrafos
fluidos (sem bullet points) e conclusão. Tom acessível, não acadêmico.
Útil para comunicar conteúdo técnico para não-especialistas ou para
transformar notas de pesquisa em rascunho publicável.

Modo: stuff para coleções pequenas; map-reduce para coleções grandes.
"""
from __future__ import annotations

from typing import Any, Iterator

from langchain_ollama import OllamaLLM

from .config import AppConfig
from .errors import MnemosyneError
from .rag import strip_think


class BlogPostError(MnemosyneError):
    """Falha ao gerar Blog Post."""


_STUFF_CHAR_LIMIT = 12_000
_MAP_K = 20
_MAP_CHUNK_CAP = 1_500

_MAP_PROMPT = (
    "Extraia do trecho abaixo os pontos mais interessantes e acessíveis:\n"
    "- Ideias que surpreendem ou provocam curiosidade\n"
    "- Exemplos concretos ou histórias que ilustram conceitos\n"
    "- Conclusões relevantes para um leitor não-especialista\n\n"
    "Seja conciso. Responda em português.\n\n"
    "Trecho:\n{chunk}\n\n"
    "Pontos interessantes:"
)

_REDUCE_PROMPT = (
    "Você recebeu pontos interessantes extraídos de uma coleção de documentos.\n"
    "Escreva um Blog Post completo e envolvente em Markdown, seguindo esta estrutura:\n\n"
    "# [Título criativo que capture a essência do conteúdo]\n\n"
    "[Introdução: 1 parágrafo que prenda a atenção, levantando uma questão ou "
    "apresentando uma ideia surpreendente]\n\n"
    "[Desenvolvimento: 3-5 parágrafos fluidos, cada um explorando um aspecto central. "
    "Sem bullet points — texto corrido, como um artigo de revista]\n\n"
    "## Conclusão\n"
    "[1-2 parágrafos que amarram as ideias e deixam o leitor com algo para pensar]\n\n"
    "Tom: acessível, curioso, envolvente — como um artigo de divulgação científica ou "
    "uma coluna de opinião inteligente. Evite jargão técnico sem explicação.\n"
    "Responda em português.\n\n"
    "Pontos extraídos:\n{points}\n\n"
    "Blog Post:"
)

_STUFF_PROMPT = (
    "Analise os trechos abaixo e escreva um Blog Post completo e envolvente em Markdown, "
    "seguindo esta estrutura:\n\n"
    "# [Título criativo que capture a essência do conteúdo]\n\n"
    "[Introdução: 1 parágrafo que prenda a atenção, levantando uma questão ou "
    "apresentando uma ideia surpreendente]\n\n"
    "[Desenvolvimento: 3-5 parágrafos fluidos, cada um explorando um aspecto central. "
    "Sem bullet points — texto corrido, como um artigo de revista]\n\n"
    "## Conclusão\n"
    "[1-2 parágrafos que amarram as ideias e deixam o leitor com algo para pensar]\n\n"
    "Tom: acessível, curioso, envolvente — como um artigo de divulgação científica.\n"
    "Responda em português.\n\n"
    "Trechos:\n{context}\n\n"
    "Blog Post:"
)


def _get_unique_docs(vectorstore: Any, k: int) -> list[tuple[str, str]]:
    try:
        docs = vectorstore.similarity_search(
            "ideia interessante exemplo história narrativa conceito", k=k
        )
    except Exception as exc:
        raise BlogPostError(f"Falha ao buscar documentos: {exc}") from exc

    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for doc in docs:
        src = doc.metadata.get("source", "")
        if src not in seen:
            seen.add(src)
            result.append((src, doc.page_content[:_MAP_CHUNK_CAP]))
    return result


def iter_blogpost(
    vectorstore: Any, config: AppConfig, **_kwargs: Any
) -> Iterator[str]:
    """
    Gerador que produz tokens do Blog Post em streaming.
    Temperatura mais alta (0.5) para escrita mais criativa e fluida.

    Raises:
        BlogPostError: se não houver documentos ou a geração falhar.
    """
    docs = _get_unique_docs(vectorstore, _MAP_K)
    if not docs:
        raise BlogPostError("Nenhum documento indexado para gerar blog post.")

    total_chars = sum(len(content) for _, content in docs)
    llm_map = OllamaLLM(model=config.llm_model, temperature=0.3, timeout=120)

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
            raise BlogPostError("Falha ao extrair pontos interessantes (fase Map).")

        prompt = _REDUCE_PROMPT.format(points="\n\n---\n".join(points))

    llm_reduce = OllamaLLM(model=config.llm_model, temperature=0.5, timeout=180)
    yield from llm_reduce.stream(prompt)
