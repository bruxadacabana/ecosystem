"""
Data Tables — extração estruturada de entidades dos documentos.

O usuário especifica as colunas desejadas (ex: "Nome, Data, Valor, Fonte")
e o LLM extrai as entidades correspondentes de todos os documentos indexados.

Saída: tabela Markdown (`| col1 | col2 | ... |`) pronta para copiar
ou exportar como CSV.

Modo: map-reduce obrigatório — cada fonte é processada individualmente
para garantir cobertura completa; a fase Reduce consolida as linhas.
"""
from __future__ import annotations

from typing import Any, Iterator

from langchain_ollama import OllamaLLM

from .config import AppConfig
from .errors import MnemosyneError
from .rag import strip_think


class TablesError(MnemosyneError):
    """Falha ao extrair tabela de dados."""


_DEFAULT_SCHEMA = "Nome, Descrição, Fonte"
_MAP_K = 30
_MAP_CHUNK_CAP = 1_500

_MAP_PROMPT = (
    "Extraia do trecho abaixo todas as entidades que se encaixam nas colunas: {schema}.\n"
    "Para cada entidade encontrada, escreva uma linha com os valores separados por pipe:\n"
    "{schema_pipes}\n\n"
    "Se não houver entidades relevantes no trecho, escreva: (nenhuma entidade encontrada)\n"
    "Seja preciso — use apenas informações explicitamente presentes no trecho.\n"
    "Responda em português.\n\n"
    "Trecho:\n{chunk}\n\n"
    "Linhas extraídas:"
)

_REDUCE_PROMPT = (
    "Você recebeu linhas de dados extraídas de múltiplos documentos "
    "com as colunas: {schema}.\n\n"
    "Consolide-as numa tabela Markdown completa:\n"
    "1. Cabeçalho com as colunas: {schema}\n"
    "2. Linha separadora com `---`\n"
    "3. Todas as linhas de dados, sem duplicatas\n\n"
    "Formato esperado:\n"
    "| {schema_pipes} |\n"
    "| {dashes} |\n"
    "| valor1 | valor2 | ... |\n\n"
    "Elimine duplicatas mantendo a linha mais completa.\n"
    "Se um campo estiver ausente, use `-`.\n"
    "Responda em português.\n\n"
    "Linhas extraídas:\n{rows}\n\n"
    "Tabela:"
)


def _parse_schema(schema: str) -> list[str]:
    """Converte 'Nome, Data, Valor' em ['Nome', 'Data', 'Valor']."""
    return [col.strip() for col in schema.split(",") if col.strip()]


def _get_all_docs(vectorstore: Any, k: int, schema: str) -> list[tuple[str, str]]:
    """Busca documentos com query derivada do schema."""
    query = f"dados informações {schema.replace(',', ' ')}"
    try:
        docs = vectorstore.similarity_search(query, k=k)
    except Exception as exc:
        raise TablesError(f"Falha ao buscar documentos: {exc}") from exc

    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for doc in docs:
        src = doc.metadata.get("source", "")
        if src not in seen:
            seen.add(src)
            result.append((src, doc.page_content[:_MAP_CHUNK_CAP]))
    return result


def iter_tables(
    vectorstore: Any,
    config: AppConfig,
    schema: str = _DEFAULT_SCHEMA,
    **_kwargs: Any,
) -> Iterator[str]:
    """
    Gerador que produz tokens da tabela Markdown em streaming.
    Sempre usa map-reduce para garantir cobertura de todas as fontes.

    Args:
        schema: colunas desejadas separadas por vírgula (ex: 'Nome, Data, Valor').

    Raises:
        TablesError: se não houver documentos ou a extração falhar.
    """
    cols = _parse_schema(schema)
    if not cols:
        raise TablesError("Schema inválido. Informe colunas separadas por vírgula.")

    schema_pipes = " | ".join(cols)
    dashes = " | ".join("---" for _ in cols)

    docs = _get_all_docs(vectorstore, _MAP_K, schema)
    if not docs:
        raise TablesError("Nenhum documento indexado para extrair tabela.")

    llm_map = OllamaLLM(model=config.llm_model, temperature=0.0, timeout=120)

    all_rows: list[str] = []
    for _, content in docs:
        try:
            raw = llm_map.invoke(
                _MAP_PROMPT.format(
                    schema=schema,
                    schema_pipes=schema_pipes,
                    chunk=content,
                )
            )
            extracted = strip_think(raw).strip()
            if extracted and "(nenhuma entidade encontrada)" not in extracted.lower():
                all_rows.append(extracted)
        except Exception:
            continue

    if not all_rows:
        raise TablesError(
            f"Nenhuma entidade encontrada para as colunas '{schema}'. "
            "Tente um schema diferente ou verifique se os documentos contêm esses dados."
        )

    prompt = _REDUCE_PROMPT.format(
        schema=schema,
        schema_pipes=schema_pipes,
        dashes=dashes,
        rows="\n\n---\n".join(all_rows),
    )

    llm_reduce = OllamaLLM(model=config.llm_model, temperature=0.0, timeout=180)
    yield from llm_reduce.stream(prompt)
