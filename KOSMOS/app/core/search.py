"""Busca global de artigos via FTS5 (BM25)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text

from app.core.database import get_session
from app.core.models import Article

log = logging.getLogger("kosmos.search")


@dataclass
class SearchResult:
    """Artigo encontrado com metadados de relevância."""

    article:         Article
    rank:            float
    title_snippet:   str   # fragmento com <mark> nos termos encontrados
    content_snippet: str   # fragmento com <mark> nos termos encontrados


def search_articles(
    query:     str,
    feed_ids:  list[int] | None  = None,
    date_from: datetime  | None  = None,
    date_to:   datetime  | None  = None,
    limit:     int               = 50,
) -> list[SearchResult]:
    """Busca artigos usando FTS5, retorna resultados ordenados por relevância.

    Args:
        query:     Texto livre. Termos simples viram prefixo (term*).
                   Frases entre aspas são buscadas literalmente.
        feed_ids:  Filtrar por feed(s) específico(s). None = todos.
        date_from: Retornar apenas artigos publicados a partir desta data.
        date_to:   Retornar apenas artigos publicados até esta data.
        limit:     Número máximo de resultados retornados.

    Returns:
        Lista de SearchResult em ordem decrescente de relevância.
        Lista vazia se a query for inválida ou não houver resultados.
    """
    if not query or not query.strip():
        return []

    fts_query = _prepare_query(query)
    if not fts_query:
        return []

    session = get_session()
    try:
        params: dict[str, object] = {"query": fts_query, "limit": limit}
        extra_where = ""

        if feed_ids:
            placeholders = ", ".join(f":fid{i}" for i in range(len(feed_ids)))
            extra_where += f" AND a.feed_id IN ({placeholders})"
            for i, fid in enumerate(feed_ids):
                params[f"fid{i}"] = fid

        if date_from:
            extra_where += " AND a.published_at >= :date_from"
            params["date_from"] = date_from

        if date_to:
            extra_where += " AND a.published_at <= :date_to"
            params["date_to"] = date_to

        sql = text(f"""
            SELECT
                a.id,
                fts.rank,
                snippet(fts_articles, 0, '<mark>', '</mark>', '…', 8)  AS title_snip,
                snippet(fts_articles, 1, '<mark>', '</mark>', '…', 20) AS content_snip
            FROM fts_articles fts
            JOIN articles a ON a.id = fts.rowid
            WHERE fts_articles MATCH :query
              AND a.duplicate_of IS NULL
              {extra_where}
            ORDER BY rank
            LIMIT :limit
        """)

        rows = session.execute(sql, params).fetchall()
        if not rows:
            return []

        # Buscar objetos Article completos em lote (uma query só)
        ids = [row[0] for row in rows]
        articles_by_id: dict[int, Article] = {
            a.id: a
            for a in session.query(Article).filter(Article.id.in_(ids))
        }

        results: list[SearchResult] = []
        for row in rows:
            art = articles_by_id.get(row[0])
            if art is None:
                continue
            results.append(SearchResult(
                article=art,
                rank=float(row[1] or 0.0),
                title_snippet=row[2] or "",
                content_snippet=row[3] or "",
            ))

        return results

    except Exception as exc:
        log.error("Erro na busca FTS5 (query=%r): %s", query, exc)
        return []
    finally:
        session.close()


def _prepare_query(raw: str) -> str:
    """Converte texto livre em query FTS5 válida.

    - Frases entre aspas são mantidas literalmente: "machine learning"
    - Palavras simples viram busca por prefixo: python → python*
    - Operadores FTS5 (AND, OR, NOT) são preservados
    - Caracteres inválidos fora de aspas são removidos
    """
    raw = raw.strip()
    if not raw:
        return ""

    tokens: list[str] = []
    remaining = raw

    while remaining:
        # Frase entre aspas — manter intacta
        phrase = re.match(r'"[^"]*"', remaining)
        if phrase:
            tokens.append(phrase.group())
            remaining = remaining[phrase.end():].lstrip()
            continue

        # Próximo token até espaço ou aspas
        word_match = re.match(r'[^\s"]+', remaining)
        if word_match:
            word = word_match.group()
            remaining = remaining[word_match.end():].lstrip()

            # Preservar operadores booleanos FTS5
            if word.upper() in ("AND", "OR", "NOT"):
                tokens.append(word.upper())
                continue

            # Remover caracteres especiais do FTS5 (exceto * e -)
            clean = re.sub(r'[^a-zA-Z0-9\u00C0-\u024F_\-*]', '', word)
            if not clean:
                continue

            # Adicionar * para busca por prefixo se não terminar em *
            tokens.append(clean if clean.endswith("*") else clean + "*")
        else:
            break

    return " ".join(tokens)
