"""
highlights.py — destaques/anotações de trechos de artigos (Fase 8).

A usuária seleciona um trecho no leitor e o marca com um tipo (citação,
questionamento, dado verificável, contradição). Cada destaque guarda o texto, o
tipo, uma nota opcional e a posição aproximada no corpo (para ordenar e recolorir).

Tabela `highlights` (criada na Fase 1). As funções aqui servem o leitor (criar,
listar, editar nota, remover) e a exportação (`export_highlights.py`).
"""
from __future__ import annotations

import logging
import sqlite3

from app.core.database import get_conn

log = logging.getLogger("kosmos.highlights")

# tipo canônico (schema) → rótulo em pt
TYPE_LABELS: dict[str, str] = {
    "citation": "Citação",
    "question": "Questionamento",
    "fact": "Dado verificável",
    "contradiction": "Contradição",
    "generic": "Destaque",
}
VALID_TYPES = set(TYPE_LABELS)


def add_highlight(
    article_id: int,
    text: str,
    highlight_type: str = "generic",
    note: str = "",
    position_hint: "str | int | None" = None,
    conn: sqlite3.Connection | None = None,
) -> int | None:
    """Cria um destaque. Retorna o id, ou None se o texto for vazio/falha."""
    text = (text or "").strip()
    if not text:
        return None
    if highlight_type not in VALID_TYPES:
        highlight_type = "generic"
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        cur = _conn.execute(
            "INSERT INTO highlights (article_id, text, note, highlight_type, position_hint) "
            "VALUES (?, ?, ?, ?, ?)",
            (article_id, text, note or "", highlight_type,
             str(position_hint) if position_hint is not None else None),
        )
        _conn.commit()
        log.info("Destaque criado: artigo=%d tipo=%s (id=%d).", article_id, highlight_type, cur.lastrowid)
        return cur.lastrowid
    except sqlite3.Error as exc:
        log.error("Falha ao criar destaque no artigo %d: %s", article_id, exc)
        return None
    finally:
        if should_close:
            _conn.close()


def list_highlights(article_id: int, conn: sqlite3.Connection | None = None) -> list[dict]:
    """Destaques de um artigo, na ordem em que aparecem no corpo (posição, depois id)."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            """
            SELECT id, article_id, text, note, highlight_type, position_hint, created_at
              FROM highlights
             WHERE article_id = ?
             ORDER BY CAST(COALESCE(position_hint, '0') AS INTEGER), id
            """,
            (article_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        log.error("Falha ao listar destaques do artigo %d: %s", article_id, exc)
        return []
    finally:
        if should_close:
            _conn.close()


def update_highlight_note(highlight_id: int, note: str, conn: sqlite3.Connection | None = None) -> bool:
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute("UPDATE highlights SET note = ? WHERE id = ?", (note or "", highlight_id))
        _conn.commit()
        return True
    except sqlite3.Error as exc:
        log.error("Falha ao salvar nota do destaque %d: %s", highlight_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def set_highlight_type(highlight_id: int, highlight_type: str, conn: sqlite3.Connection | None = None) -> bool:
    if highlight_type not in VALID_TYPES:
        return False
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute("UPDATE highlights SET highlight_type = ? WHERE id = ?", (highlight_type, highlight_id))
        _conn.commit()
        return True
    except sqlite3.Error as exc:
        log.error("Falha ao mudar tipo do destaque %d: %s", highlight_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def delete_highlight(highlight_id: int, conn: sqlite3.Connection | None = None) -> bool:
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute("DELETE FROM highlights WHERE id = ?", (highlight_id,))
        _conn.commit()
        return True
    except sqlite3.Error as exc:
        log.error("Falha ao remover destaque %d: %s", highlight_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()
