"""
feeds_admin.py — gerenciamento de feeds pela usuária (adicionar/remover/editar/OPML).

A janela de Configurações usa estas funções para a seção Feeds. O título de um feed
recém-adicionado pode vir vazio: o `feed_fetcher.update_feed_meta` preenche o nome
real no primeiro fetch (a sidebar mostra `COALESCE(title, url)` até lá).
"""
from __future__ import annotations

import logging
import sqlite3
import xml.etree.ElementTree as ET

from app.core.database import get_conn

log = logging.getLogger("kosmos.feeds_admin")


def _backup_sources() -> None:
    """Reexporta o sources.json (backup das fontes) após uma mudança em produção."""
    try:
        from app.core.sources_backup import export_sources
        export_sources()
    except Exception as exc:  # nunca deixar o backup quebrar a operação de feed
        log.error("feeds_admin: falha ao exportar backup das fontes: %s", exc)


def add_feed(url: str, title: str = "", category: str = "Sem categoria",
             conn: sqlite3.Connection | None = None) -> int | None:
    """Adiciona um feed (idempotente por URL). Retorna o id (novo ou já existente); None se URL vazia."""
    url = (url or "").strip()
    if not url:
        return None
    category = (category or "").strip() or "Sem categoria"
    title = (title or "").strip() or None
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute(
            "INSERT OR IGNORE INTO feeds (url, title, category) VALUES (?, ?, ?)",
            (url, title, category),
        )
        _conn.commit()
        row = _conn.execute("SELECT id FROM feeds WHERE url = ?", (url,)).fetchone()
        if row is not None:
            log.info("Feed adicionado/já existia: %s (id=%s, categoria=%s).", url, row[0], category)
            if should_close:
                _backup_sources()
            return row[0]
        return None
    except sqlite3.Error as exc:
        log.error("Falha ao adicionar feed %s: %s", url, exc)
        return None
    finally:
        if should_close:
            _conn.close()


def list_feeds(conn: sqlite3.Connection | None = None) -> list[dict]:
    """Todos os feeds, por categoria e nome."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            "SELECT id, url, title, category, enabled FROM feeds "
            "ORDER BY category COLLATE NOCASE, COALESCE(title, url) COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        log.error("Falha ao listar feeds: %s", exc)
        return []
    finally:
        if should_close:
            _conn.close()


def delete_feed(feed_id: int, conn: sqlite3.Connection | None = None) -> bool:
    """Remove um feed (e seus artigos, por ON DELETE CASCADE)."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
        _conn.commit()
        log.info("Feed %d removido.", feed_id)
        if should_close:
            _backup_sources()
        return True
    except sqlite3.Error as exc:
        log.error("Falha ao remover feed %d: %s", feed_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def update_feed(feed_id: int, *, title: str | None = None, category: str | None = None,
                enabled: bool | None = None, conn: sqlite3.Connection | None = None) -> bool:
    """Atualiza campos editáveis de um feed (só os fornecidos)."""
    sets, params = [], []
    if title is not None:
        sets.append("title = ?")
        params.append(title.strip() or None)
    if category is not None:
        sets.append("category = ?")
        params.append(category.strip() or "Sem categoria")
    if enabled is not None:
        sets.append("enabled = ?")
        params.append(1 if enabled else 0)
    if not sets:
        return False
    params.append(feed_id)
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute(f"UPDATE feeds SET {', '.join(sets)} WHERE id = ?", params)
        _conn.commit()
        if should_close:
            _backup_sources()
        return True
    except sqlite3.Error as exc:
        log.error("Falha ao atualizar feed %d: %s", feed_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def _collect_opml(node: ET.Element, category: str, out: list[tuple[str, str, str]]) -> None:
    for outline in node.findall("outline"):
        xml_url = outline.get("xmlUrl")
        text = (outline.get("text") or outline.get("title") or "").strip()
        if xml_url:
            out.append((xml_url.strip(), text, category or "Sem categoria"))
        else:
            # outline de agrupamento → o texto vira a categoria dos filhos
            _collect_opml(outline, text or category, out)


def import_opml(opml_text: str, conn: sqlite3.Connection | None = None) -> int:
    """Importa feeds de um texto OPML. Retorna o nº de feeds NOVOS adicionados."""
    try:
        root = ET.fromstring(opml_text)
    except ET.ParseError as exc:
        log.warning("OPML inválido: %s", exc)
        return 0
    body = root.find("body")
    if body is None:
        return 0
    collected: list[tuple[str, str, str]] = []
    _collect_opml(body, "", collected)

    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        added = 0
        for url, title, category in collected:
            if not url:
                continue
            cur = _conn.execute(
                "INSERT OR IGNORE INTO feeds (url, title, category) VALUES (?, ?, ?)",
                (url, title or None, category),
            )
            if cur.rowcount > 0:
                added += 1
        _conn.commit()
        log.info("OPML importado: %d feed(s) novo(s) de %d no arquivo.", added, len(collected))
        if should_close:
            _backup_sources()
        return added
    except sqlite3.Error as exc:
        log.error("Falha ao importar OPML: %s", exc)
        return 0
    finally:
        if should_close:
            _conn.close()
