"""
alerts.py — alertas de palavras-chave e entidades (Fase 7, item 6).

A usuária configura termos a vigiar: **palavras-chave** (texto livre) e **entidades
rastreadas** (por id). Quando um artigo menciona um termo vigiado, seu card é
destacado na lista — sem push: o destaque aparece na próxima vez que a lista é
aberta/recarregada.

Tabela `alerts(kind, term)`: kind='keyword' → term é a palavra; kind='entity' → term
é o `entity_id` como texto. `get_alerted_article_ids` calcula o conjunto de artigos
que casam com QUALQUER alerta ativo (keyword via LIKE em título/resumo; entidade via
`article_entities`). Tudo best-effort, com log em erro (nunca quebra a lista).
"""
from __future__ import annotations

import logging
import sqlite3

from app.core.database import get_conn

log = logging.getLogger("kosmos.alerts")

_VALID_KINDS = ("keyword", "entity")


def add_alert(kind: str, term: str, conn: sqlite3.Connection | None = None) -> bool:
    """Cria um alerta (idempotente por UNIQUE(kind, term)). True se inseriu agora."""
    kind = (kind or "").strip().lower()
    term = (term or "").strip()
    if kind not in _VALID_KINDS or not term:
        log.warning("alerts: add_alert ignorado (kind=%r term=%r).", kind, term)
        return False
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        cur = _conn.execute(
            "INSERT OR IGNORE INTO alerts (kind, term) VALUES (?, ?)", (kind, term)
        )
        _conn.commit()
        return cur.rowcount > 0
    except sqlite3.Error as exc:
        log.error("alerts: falha ao adicionar alerta (%s=%s): %s", kind, term, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def remove_alert(kind: str, term: str, conn: sqlite3.Connection | None = None) -> bool:
    """Remove um alerta por (kind, term). True se removeu algo."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        cur = _conn.execute(
            "DELETE FROM alerts WHERE kind = ? AND term = ?",
            ((kind or "").strip().lower(), (term or "").strip()),
        )
        _conn.commit()
        return cur.rowcount > 0
    except sqlite3.Error as exc:
        log.error("alerts: falha ao remover alerta (%s=%s): %s", kind, term, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def list_alerts(conn: sqlite3.Connection | None = None) -> list[dict]:
    """Lista os alertas. Para kind='entity', resolve o nome da entidade (label)."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            """
            SELECT al.id, al.kind, al.term,
                   CASE WHEN al.kind = 'entity'
                        THEN (SELECT e.name FROM entities e WHERE e.id = CAST(al.term AS INTEGER))
                        ELSE al.term END AS label
              FROM alerts al
             ORDER BY al.kind, label COLLATE NOCASE
            """
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        log.error("alerts: falha ao listar alertas: %s", exc)
        return []
    finally:
        if should_close:
            _conn.close()


def is_entity_alerted(entity_id: int, conn: sqlite3.Connection | None = None) -> bool:
    """True se há alerta para a entidade dada (usado pelo toggle na UI)."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        row = _conn.execute(
            "SELECT 1 FROM alerts WHERE kind = 'entity' AND term = ?", (str(entity_id),)
        ).fetchone()
        return row is not None
    except sqlite3.Error as exc:
        log.error("alerts: falha ao checar alerta da entidade %s: %s", entity_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def get_alerted_article_ids(conn: sqlite3.Connection | None = None) -> set[int]:
    """Conjunto de article_ids que casam com QUALQUER alerta ativo.

    Keyword: LIKE (case-insensitive) em título ou resumo. Entidade: vínculo em
    `article_entities`. Vazio se não houver alertas ou em erro de banco.
    """
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    ids: set[int] = set()
    try:
        alerts = _conn.execute("SELECT kind, term FROM alerts").fetchall()
        keywords = [r["term"] for r in alerts if r["kind"] == "keyword" and r["term"].strip()]
        entity_ids = [
            int(r["term"]) for r in alerts
            if r["kind"] == "entity" and str(r["term"]).strip().isdigit()
        ]
        for kw in keywords:
            pat = f"%{kw.lower()}%"
            rows = _conn.execute(
                "SELECT id FROM articles "
                "WHERE lower(title) LIKE ? OR lower(COALESCE(content_excerpt, '')) LIKE ?",
                (pat, pat),
            ).fetchall()
            ids.update(r["id"] for r in rows)
        if entity_ids:
            ph = ",".join("?" * len(entity_ids))
            rows = _conn.execute(
                f"SELECT DISTINCT article_id FROM article_entities WHERE entity_id IN ({ph})",
                entity_ids,
            ).fetchall()
            ids.update(r["article_id"] for r in rows)
    except sqlite3.Error as exc:
        log.error("alerts: falha ao computar artigos alertados: %s", exc)
    finally:
        if should_close:
            _conn.close()
    return ids
