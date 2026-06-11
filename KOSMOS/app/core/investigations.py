"""
investigations.py — pastas de investigação (Fase 7, item 3).

Uma investigação é uma pasta curada de artigos (tabelas `investigations` e
`investigation_articles`). Esta camada cria/lista/remove pastas, gerencia os artigos
dentro (com nota por artigo), e exporta a pasta como um dossiê `.md` estruturado.

Os artigos de uma investigação são ordenados **cronologicamente (mais antigo →
mais novo)** — uma linha do tempo de como a história se desenrolou, que é o sentido
de uma pasta de investigação (distinto do feed/entidade, que vêm newest-first).
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from app.core.database import get_conn

log = logging.getLogger("kosmos.investigations")

_NOW = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"


def _touch(conn: sqlite3.Connection, inv_id: int) -> None:
    conn.execute(f"UPDATE investigations SET updated_at = {_NOW} WHERE id = ?", (inv_id,))


def create_investigation(name: str, description: str = "", conn: sqlite3.Connection | None = None) -> int | None:
    """Cria uma pasta de investigação. Retorna o id, ou None em falha/nome vazio."""
    name = (name or "").strip()
    if not name:
        return None
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        cur = _conn.execute(
            "INSERT INTO investigations (name, description) VALUES (?, ?)", (name, description or "")
        )
        _conn.commit()
        log.info("Investigação criada: %r (id=%d).", name, cur.lastrowid)
        return cur.lastrowid
    except sqlite3.Error as exc:
        log.error("Falha ao criar investigação %r: %s", name, exc)
        return None
    finally:
        if should_close:
            _conn.close()


def list_investigations(conn: sqlite3.Connection | None = None) -> list[dict]:
    """Pastas com contagem de artigos, atualizadas mais recentemente primeiro."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            """
            SELECT i.id, i.name, i.description, i.created_at, i.updated_at,
                   COUNT(ia.article_id) AS article_count
              FROM investigations i
              LEFT JOIN investigation_articles ia ON ia.investigation_id = i.id
             GROUP BY i.id
             ORDER BY i.updated_at DESC, i.name COLLATE NOCASE
            """
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        log.error("Falha ao listar investigações: %s", exc)
        return []
    finally:
        if should_close:
            _conn.close()


def get_investigation(inv_id: int, conn: sqlite3.Connection | None = None) -> dict | None:
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        row = _conn.execute("SELECT * FROM investigations WHERE id = ?", (inv_id,)).fetchone()
        return dict(row) if row is not None else None
    except sqlite3.Error as exc:
        log.error("Falha ao ler investigação %d: %s", inv_id, exc)
        return None
    finally:
        if should_close:
            _conn.close()


def set_description(inv_id: int, description: str, conn: sqlite3.Connection | None = None) -> bool:
    """Atualiza as notas/descrição da pasta. True em sucesso."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute("UPDATE investigations SET description = ? WHERE id = ?", (description or "", inv_id))
        _touch(_conn, inv_id)
        _conn.commit()
        return True
    except sqlite3.Error as exc:
        log.error("Falha ao salvar descrição da investigação %d: %s", inv_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def rename_investigation(inv_id: int, name: str, conn: sqlite3.Connection | None = None) -> bool:
    name = (name or "").strip()
    if not name:
        return False
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute("UPDATE investigations SET name = ? WHERE id = ?", (name, inv_id))
        _touch(_conn, inv_id)
        _conn.commit()
        return True
    except sqlite3.Error as exc:
        log.error("Falha ao renomear investigação %d: %s", inv_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def delete_investigation(inv_id: int, conn: sqlite3.Connection | None = None) -> bool:
    """Remove a pasta (os vínculos com artigos caem por ON DELETE CASCADE)."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute("DELETE FROM investigations WHERE id = ?", (inv_id,))
        _conn.commit()
        return True
    except sqlite3.Error as exc:
        log.error("Falha ao excluir investigação %d: %s", inv_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def add_article(inv_id: int, article_id: int, conn: sqlite3.Connection | None = None) -> bool:
    """Adiciona um artigo à pasta (idempotente). True se adicionou agora."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        cur = _conn.execute(
            "INSERT OR IGNORE INTO investigation_articles (investigation_id, article_id) VALUES (?, ?)",
            (inv_id, article_id),
        )
        _touch(_conn, inv_id)
        _conn.commit()
        return cur.rowcount > 0
    except sqlite3.Error as exc:
        log.error("Falha ao adicionar artigo %d à investigação %d: %s", article_id, inv_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def remove_article(inv_id: int, article_id: int, conn: sqlite3.Connection | None = None) -> bool:
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute(
            "DELETE FROM investigation_articles WHERE investigation_id = ? AND article_id = ?",
            (inv_id, article_id),
        )
        _touch(_conn, inv_id)
        _conn.commit()
        return True
    except sqlite3.Error as exc:
        log.error("Falha ao remover artigo %d da investigação %d: %s", article_id, inv_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def get_articles(inv_id: int, conn: sqlite3.Connection | None = None) -> list[dict]:
    """Artigos da pasta em ordem cronológica (mais antigo → mais novo), com a nota."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            """
            SELECT a.id, a.title, a.url, a.published_at, a.ai_sentiment, a.ai_summary,
                   COALESCE(f.title, f.url) AS feed, ia.notes AS note
              FROM investigation_articles ia
              JOIN articles a ON a.id = ia.article_id
              JOIN feeds f    ON f.id = a.feed_id
             WHERE ia.investigation_id = ?
             ORDER BY a.published_at ASC, a.id ASC
            """,
            (inv_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        log.error("Falha ao listar artigos da investigação %d: %s", inv_id, exc)
        return []
    finally:
        if should_close:
            _conn.close()


def set_article_note(inv_id: int, article_id: int, note: str, conn: sqlite3.Connection | None = None) -> bool:
    """Nota da usuária para um artigo dentro de uma investigação específica."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute(
            "UPDATE investigation_articles SET notes = ? WHERE investigation_id = ? AND article_id = ?",
            (note or "", inv_id, article_id),
        )
        _touch(_conn, inv_id)
        _conn.commit()
        return True
    except sqlite3.Error as exc:
        log.error("Falha ao salvar nota do artigo %d na investigação %d: %s", article_id, inv_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "data desconhecida"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except Exception:
        return iso[:10]


def export_dossier(inv_id: int, conn: sqlite3.Connection | None = None) -> str | None:
    """Monta o dossiê `.md` estruturado da investigação. None se a pasta não existir."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        inv = get_investigation(inv_id, _conn)
        if inv is None:
            return None
        articles = get_articles(inv_id, _conn)
    finally:
        if should_close:
            _conn.close()

    lines: list[str] = [f"# {inv['name']}", ""]
    if (inv.get("description") or "").strip():
        lines += [inv["description"].strip(), ""]
    lines += [
        f"_Investigação criada em {_fmt_date(inv.get('created_at'))} · "
        f"{len(articles)} artigo(s) · exportado em {_fmt_date(datetime.now(timezone.utc).isoformat())}._",
        "",
        "## Linha do tempo",
        "",
    ]
    for a in articles:
        lines.append(f"### {a['title']}")
        meta = f"- **Fonte:** {a['feed']}  ·  **Data:** {_fmt_date(a['published_at'])}"
        if a.get("ai_sentiment"):
            meta += f"  ·  **Sentimento:** {a['ai_sentiment']}"
        lines.append(meta)
        if a.get("url"):
            lines.append(f"- **URL:** {a['url']}")
        if (a.get("note") or "").strip():
            lines.append(f"- **Nota:** {a['note'].strip()}")
        if (a.get("ai_summary") or "").strip():
            lines += ["", a["ai_summary"].strip()]
        lines += ["", "---", ""]
    return "\n".join(lines).rstrip() + "\n"
