"""
sources_backup.py — backup e restauração da lista de fontes (feeds) do KOSMOS.

A lista de fontes é exportada como JSON em DUAS cópias dentro do sync_root (defesa
em profundidade — sobrevivem à perda do banco e sincronizam entre máquinas):

  - {sync_root}/kosmos/sources.json          (cópia viva, na pasta do KOSMOS)
  - {sync_root}/.backup/kosmos/sources.json  (backup; o HUB versiona via git)

Formato v3: lista de objetos `{url, title, category, enabled}`. O arquivo é reescrito
a cada mudança de feed e no fechamento. Na inicialização, se a tabela `feeds` estiver
vazia mas existir um sources.json, as fontes são restauradas — a lista nunca se perde
de vez. (O backup do HUB em backup.rs ainda usa o schema antigo; alinhar é etapa à
parte — este módulo deixa o lado do KOSMOS correto e independente.)
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from app.core.database import get_conn

log = logging.getLogger("kosmos.sources_backup")

_FILENAME = "sources.json"


def _sync_root() -> Path | None:
    try:
        import ecosystem_client
        root = ecosystem_client.get_sync_root()
        return Path(root) if root else None
    except Exception as exc:
        log.debug("sources_backup: sync_root indisponível: %s", exc)
        return None


def sources_paths() -> list[Path]:
    """Os dois destinos do sources.json (vazio se sync_root indisponível)."""
    root = _sync_root()
    if root is None:
        return []
    return [root / "kosmos" / _FILENAME, root / ".backup" / "kosmos" / _FILENAME]


def _read_feeds(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT url, title, category, enabled FROM feeds ORDER BY category, COALESCE(title, url)"
    ).fetchall()
    out = []
    for r in rows:
        out.append({
            "url": r["url"],
            "title": r["title"] or "",
            "category": r["category"] or "Sem categoria",
            "enabled": bool(r["enabled"]),
        })
    return out


def export_sources(conn: sqlite3.Connection | None = None) -> int:
    """Escreve o sources.json (fontes atuais) nas duas cópias do sync_root. Retorna nº de feeds."""
    dests = sources_paths()
    if not dests:
        log.debug("sources_backup: sem sync_root — export de fontes pulado.")
        return 0
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        feeds = _read_feeds(_conn)
    except sqlite3.Error as exc:
        log.error("sources_backup: falha ao ler feeds para export: %s", exc)
        return 0
    finally:
        if should_close:
            _conn.close()

    payload = json.dumps(feeds, ensure_ascii=False, indent=2)
    written = 0
    for dest in dests:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".json.tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(dest)
            written += 1
        except OSError as exc:
            log.error("sources_backup: falha ao escrever %s: %s", dest, exc)
    log.info("sources_backup: %d fonte(s) exportada(s) para %d arquivo(s).", len(feeds), written)
    return len(feeds)


def _load_sources_file() -> list[dict]:
    """Lê o sources.json (prefere a cópia viva; cai para o backup). [] se nada válido."""
    for dest in sources_paths():
        if not dest.exists():
            continue
        try:
            data = json.loads(dest.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (OSError, ValueError) as exc:
            log.warning("sources_backup: %s ilegível: %s", dest, exc)
    return []


def restore_sources_if_empty(conn: sqlite3.Connection | None = None) -> int:
    """Se a tabela feeds estiver vazia mas houver sources.json, importa as fontes. Retorna nº importado."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        count = _conn.execute("SELECT COUNT(*) FROM feeds").fetchone()[0]
        if count > 0:
            return 0  # já há feeds — não restaura por cima
        feeds = _load_sources_file()
        if not feeds:
            return 0
        imported = 0
        for f in feeds:
            url = (f.get("url") or "").strip()
            if not url:
                continue
            cur = _conn.execute(
                "INSERT OR IGNORE INTO feeds (url, title, category, enabled) VALUES (?, ?, ?, ?)",
                (url, (f.get("title") or "").strip() or None,
                 (f.get("category") or "Sem categoria").strip() or "Sem categoria",
                 1 if f.get("enabled", True) else 0),
            )
            if cur.rowcount > 0:
                imported += 1
        _conn.commit()
        if imported:
            log.warning("sources_backup: banco de feeds vazio — %d fonte(s) RESTAURADA(S) do sources.json.", imported)
        return imported
    except sqlite3.Error as exc:
        log.error("sources_backup: falha ao restaurar fontes: %s", exc)
        return 0
    finally:
        if should_close:
            _conn.close()
