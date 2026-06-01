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

from langchain_openai import ChatOpenAI
from ecosystem_client import get_inference_url as _ec_url

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
    "Consolide-as num Mind Map e retorne APENAS um objeto JSON válido, sem texto adicional.\n\n"
    "Formato exato:\n"
    '{{"raiz": "Tema Central", "nós": [\n'
    '  {{"id": "1", "label": "Ramo Principal 1", "pai_id": ""}},\n'
    '  {{"id": "1.1", "label": "Subtópico A", "pai_id": "1"}},\n'
    '  {{"id": "2", "label": "Ramo Principal 2", "pai_id": ""}},\n'
    '  {{"id": "2.1", "label": "Subtópico B", "pai_id": "2"}}\n'
    "]}}\n\n"
    "Regras:\n"
    "- pai_id vazio = filho direto da raiz\n"
    "- Máximo 6 ramos principais, 3-4 subtópicos por ramo\n"
    "- Textos curtos (máximo 5 palavras por nó)\n\n"
    "Estruturas extraídas:\n{{structures}}\n\n"
    "JSON:"
).replace("{{structures}}", "{structures}")

_STUFF_PROMPT = (
    "Analise os trechos abaixo e extraia os conceitos principais e suas relações hierárquicas.\n"
    "Retorne APENAS um objeto JSON válido, sem texto adicional.\n\n"
    "Formato exato:\n"
    '{{"raiz": "Tema Central", "nós": [\n'
    '  {{"id": "1", "label": "Ramo Principal 1", "pai_id": ""}},\n'
    '  {{"id": "1.1", "label": "Subtópico A", "pai_id": "1"}},\n'
    '  {{"id": "2", "label": "Ramo Principal 2", "pai_id": ""}},\n'
    '  {{"id": "2.1", "label": "Subtópico B", "pai_id": "2"}}\n'
    "]}}\n\n"
    "Regras:\n"
    "- pai_id vazio = filho direto da raiz\n"
    "- Máximo 6 ramos principais, 3-4 subtópicos por ramo\n"
    "- Textos curtos (máximo 5 palavras por nó)\n\n"
    "Trechos:\n{{context}}\n\n"
    "JSON:"
).replace("{{context}}", "{context}")


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
    llm_map = ChatOpenAI(model=config.llm_model, base_url=f"{_ec_url()}/v1", api_key="logos", temperature=0.1, timeout=90)

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

    llm_reduce = ChatOpenAI(model=config.llm_model, base_url=f"{_ec_url()}/v1", api_key="logos", temperature=0.1, timeout=120)
    yield from llm_reduce.stream(prompt)


def parse_mindmap_json(text: str) -> dict | None:
    """
    Parseia o JSON do mind map a partir do texto bruto do LLM.

    Suporta:
    - JSON direto: {"raiz": ..., "nós": [...]}
    - JSON dentro de bloco ```json ... ```

    Retorna None se o texto não for JSON válido ou não tiver os campos esperados.
    Fallback para outputs legados (Mermaid/texto): retorna None graciosamente.
    """
    import json
    import re

    text = text.strip()

    candidates = [text]

    # JSON em bloco de código ```json ... ```
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if m:
        candidates.insert(0, m.group(1).strip())

    # JSON embutido em texto — procura o primeiro { ... } que pareça JSON
    m2 = re.search(r'(\{[^{}]*"raiz"[^{}]*"nós"[^}]*\})', text, re.DOTALL)
    if not m2:
        m2 = re.search(r'(\{"raiz".*\})', text, re.DOTALL)
    if m2:
        candidates.append(m2.group(1).strip())

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and "raiz" in data and "nós" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            continue

    return None
