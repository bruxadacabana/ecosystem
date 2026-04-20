"""
Mind Map — estrutura hierárquica da coleção em sintaxe Mermaid.

Saída primária: bloco Markdown com sintaxe `mindmap` do Mermaid,
compatível com Obsidian (plugin Mermaid), VS Code e GitHub.
O StudioWorker exporta o texto; a UI pode abrir via webbrowser.open()
se o usuário preferir visualização interativa.

Modo: stuff para coleções pequenas; map-reduce para coleções grandes.
"""
from __future__ import annotations

from typing import Any, Iterator

from langchain_ollama import OllamaLLM

from .config import AppConfig
from .errors import MnemosyneError
from .rag import strip_think


class MindMapError(MnemosyneError):
    """Falha ao gerar Mind Map."""


_STUFF_CHAR_LIMIT = 12_000
_MAP_K = 20
_MAP_CHUNK_CAP = 1_200

_MAP_PROMPT = (
    "Identifique no trecho abaixo os conceitos principais e suas relações hierárquicas.\n"
    "Liste no formato:\n"
    "TEMA CENTRAL: [tema principal do trecho]\n"
    "  RAMO: [subtema 1]\n"
    "    FOLHA: [detalhe ou conceito específico]\n"
    "  RAMO: [subtema 2]\n"
    "    FOLHA: [detalhe]\n\n"
    "Seja conciso — apenas os conceitos, sem frases longas.\n"
    "Responda em português.\n\n"
    "Trecho:\n{chunk}\n\n"
    "Estrutura:"
)

_REDUCE_PROMPT = (
    "Você recebeu estruturas hierárquicas extraídas de múltiplos documentos.\n"
    "Consolide-as num Mind Map completo usando a sintaxe Mermaid mindmap.\n\n"
    "IMPORTANTE: responda APENAS com o bloco de código Mermaid, sem texto adicional.\n\n"
    "Formato exato:\n"
    "```mermaid\n"
    "mindmap\n"
    "  root((Tema Central))\n"
    "    Ramo Principal 1\n"
    "      Subtópico A\n"
    "      Subtópico B\n"
    "    Ramo Principal 2\n"
    "      Subtópico C\n"
    "```\n\n"
    "Regras:\n"
    "- O nó raiz usa parênteses duplos: `root((Título))`\n"
    "- Máximo 6 ramos principais, 3-4 subtópicos por ramo\n"
    "- Textos curtos (máximo 5 palavras por nó)\n"
    "- Sem caracteres especiais nos nós (evite aspas, vírgulas, colchetes)\n\n"
    "Estruturas extraídas:\n{structures}\n\n"
    "Mind Map:"
)

_STUFF_PROMPT = (
    "Analise os trechos abaixo e gere um Mind Map usando a sintaxe Mermaid mindmap.\n\n"
    "IMPORTANTE: responda APENAS com o bloco de código Mermaid, sem texto adicional.\n\n"
    "Formato exato:\n"
    "```mermaid\n"
    "mindmap\n"
    "  root((Tema Central))\n"
    "    Ramo Principal 1\n"
    "      Subtópico A\n"
    "      Subtópico B\n"
    "    Ramo Principal 2\n"
    "      Subtópico C\n"
    "```\n\n"
    "Regras:\n"
    "- O nó raiz usa parênteses duplos: `root((Título))`\n"
    "- Máximo 6 ramos principais, 3-4 subtópicos por ramo\n"
    "- Textos curtos (máximo 5 palavras por nó)\n"
    "- Sem caracteres especiais nos nós\n\n"
    "Trechos:\n{context}\n\n"
    "Mind Map:"
)


def _get_unique_docs(vectorstore: Any, k: int) -> list[tuple[str, str]]:
    try:
        docs = vectorstore.similarity_search(
            "conceito principal ideia central tema hierarquia relação", k=k
        )
    except Exception as exc:
        raise MindMapError(f"Falha ao buscar documentos: {exc}") from exc

    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for doc in docs:
        src = doc.metadata.get("source", "")
        if src not in seen:
            seen.add(src)
            result.append((src, doc.page_content[:_MAP_CHUNK_CAP]))
    return result


def iter_mindmap(
    vectorstore: Any, config: AppConfig, **_kwargs: Any
) -> Iterator[str]:
    """
    Gerador que produz tokens do Mind Map em streaming.
    Saída: bloco ```mermaid mindmap``` pronto para colar no Obsidian ou GitHub.

    Raises:
        MindMapError: se não houver documentos ou a geração falhar.
    """
    docs = _get_unique_docs(vectorstore, _MAP_K)
    if not docs:
        raise MindMapError("Nenhum documento indexado para gerar mind map.")

    total_chars = sum(len(content) for _, content in docs)
    llm_map = OllamaLLM(model=config.llm_model, temperature=0.1, timeout=90)

    if total_chars <= _STUFF_CHAR_LIMIT:
        context = "\n\n---\n".join(content for _, content in docs)
        prompt = _STUFF_PROMPT.format(context=context)
    else:
        structures: list[str] = []
        for _, content in docs:
            try:
                raw = llm_map.invoke(_MAP_PROMPT.format(chunk=content))
                extracted = strip_think(raw).strip()
                if extracted:
                    structures.append(extracted)
            except Exception:
                continue

        if not structures:
            raise MindMapError("Falha ao extrair estrutura dos documentos (fase Map).")

        prompt = _REDUCE_PROMPT.format(structures="\n\n---\n".join(structures))

    llm_reduce = OllamaLLM(model=config.llm_model, temperature=0.1, timeout=120)
    yield from llm_reduce.stream(prompt)
