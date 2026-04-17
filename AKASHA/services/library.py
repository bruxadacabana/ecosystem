"""
AKASHA — Biblioteca de URLs
Scraping periódico com versionamento por diff e metadados estendidos.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import sys
from pathlib import Path as _Path

import aiosqlite
import httpx
import trafilatura

from config import DB_PATH

sys.path.insert(0, str(_Path(__file__).parent.parent.parent))
from ecosystem_scraper import extract as _cascade_extract


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

@dataclass
class LibraryEntry:
    id:                  int
    url:                 str
    title:               str
    snippet:             str
    content_md:          str
    content_hash:        str
    language:            str
    word_count:          int
    tags:                list[str]
    notes:               str
    check_interval_days: int
    last_checked_at:     str | None
    status:              str
    created_at:          str
    has_recent_diff:     bool = False


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _snippet(content: str, max_chars: int = 220) -> str:
    text = re.sub(r"[#*`_\[\]()\n]+", " ", content)
    text = re.sub(r" {2,}", " ", text).strip()
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def compute_diff(old: str, new: str) -> str:
    """Diff unificado entre dois textos em markdown."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    return "".join(difflib.unified_diff(old_lines, new_lines, lineterm=""))


def _row_to_entry(row: tuple, has_recent_diff: bool = False) -> LibraryEntry:
    (
        id_, url, title, snippet, content_md, content_hash, language,
        word_count, tags_json, notes, check_interval_days,
        last_checked_at, status, created_at,
    ) = row
    return LibraryEntry(
        id=id_,
        url=url,
        title=title,
        snippet=snippet,
        content_md=content_md,
        content_hash=content_hash,
        language=language,
        word_count=word_count,
        tags=json.loads(tags_json or "[]"),
        notes=notes,
        check_interval_days=check_interval_days,
        last_checked_at=last_checked_at,
        status=status,
        created_at=created_at,
        has_recent_diff=has_recent_diff,
    )


async def _recent_diff_ids() -> set[int]:
    """IDs de entradas com diff nos últimos 7 dias."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT DISTINCT url_id FROM library_diffs WHERE scraped_at > ?", (cutoff,)
        )).fetchall()
    return {row[0] for row in rows}


async def _update_fts(db: aiosqlite.Connection, entry_id: int, url: str, title: str, body: str) -> None:
    await db.execute(
        "DELETE FROM library_fts WHERE url_id = ?", (str(entry_id),)
    )
    await db.execute(
        "INSERT INTO library_fts (url_id, url, title, body) VALUES (?, ?, ?, ?)",
        (str(entry_id), url, title, body[:12000]),
    )


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

async def _fetch_and_extract(url: str) -> tuple[str, str, str, int]:
    """Retorna (title, language, content_md, word_count)."""
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AKASHA-library/1.0)"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        html = response.text

    metadata  = trafilatura.extract_metadata(html, default_url=url)
    title:    str = (metadata and metadata.title) or urlparse(url).netloc
    language: str = (metadata and getattr(metadata, "language", "")) or ""
    content: str = _cascade_extract(html, url, output_format="markdown")
    return title, language, content, len(content.split())


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def queue_url(url: str, interval_days: int = 7) -> None:
    """Insere URL na biblioteca sem scrape imediato (status='pending').
    O loop horário fará o scrape automaticamente."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO library_urls
               (url, check_interval_days, status)
               VALUES (?, ?, 'pending')""",
            (url, interval_days),
        )
        await db.commit()


async def add_url(
    url: str,
    interval_days: int = 7,
    tags: list[str] | None = None,
    notes: str = "",
) -> LibraryEntry:
    """Adiciona URL à biblioteca e faz o primeiro scrape."""
    tags = tags or []
    title, language, content_md, word_count = await _fetch_and_extract(url)
    content_hash = _hash(content_md)
    snippet_text = _snippet(content_md)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT OR REPLACE INTO library_urls
               (url, title, snippet, content_md, content_hash, language, word_count,
                tags_json, notes, check_interval_days, last_checked_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
            (url, title, snippet_text, content_md, content_hash, language,
             word_count, json.dumps(tags), notes, interval_days, now),
        )
        entry_id = cursor.lastrowid
        await _update_fts(db, entry_id, url, title, content_md)
        await db.commit()

    return LibraryEntry(
        id=entry_id, url=url, title=title, snippet=snippet_text,
        content_md=content_md, content_hash=content_hash, language=language,
        word_count=word_count, tags=tags, notes=notes,
        check_interval_days=interval_days, last_checked_at=now,
        status="active", created_at=now,
    )


async def scrape_and_store(entry_id: int) -> LibraryEntry:
    """Re-scrape de uma entrada; salva diff se o conteúdo mudou."""
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT * FROM library_urls WHERE id = ?", (entry_id,)
        )).fetchone()
    if not row:
        raise ValueError(f"Entrada {entry_id} não encontrada")

    entry = _row_to_entry(row)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        title, language, content_md, word_count = await _fetch_and_extract(entry.url)
    except Exception as exc:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE library_urls SET status='error', last_checked_at=? WHERE id=?",
                (now, entry_id),
            )
            await db.commit()
        raise RuntimeError(f"Falha ao re-scrape: {exc}") from exc

    new_hash    = _hash(content_md)
    changed     = new_hash != entry.content_hash
    snippet_txt = _snippet(content_md)

    async with aiosqlite.connect(DB_PATH) as db:
        if changed:
            diff_text = compute_diff(entry.content_md, content_md)
            await db.execute(
                "INSERT INTO library_diffs (url_id, diff_text, scraped_at) VALUES (?, ?, ?)",
                (entry_id, diff_text, now),
            )
        await db.execute(
            """UPDATE library_urls
               SET title=?, snippet=?, content_md=?, content_hash=?,
                   language=?, word_count=?, last_checked_at=?, status='active'
               WHERE id=?""",
            (title, snippet_txt, content_md, new_hash, language, word_count, now, entry_id),
        )
        await _update_fts(db, entry_id, entry.url, title, content_md)
        await db.commit()

    entry.title           = title
    entry.snippet         = snippet_txt
    entry.content_md      = content_md
    entry.content_hash    = new_hash
    entry.language        = language
    entry.word_count      = word_count
    entry.last_checked_at = now
    entry.status          = "active"
    entry.has_recent_diff = changed
    return entry


async def check_overdue() -> list[LibraryEntry]:
    """Retorna entradas ativas cujo prazo de re-scrape já venceu."""
    now = datetime.now(timezone.utc)
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT * FROM library_urls WHERE status != 'paused'"
        )).fetchall()

    overdue: list[LibraryEntry] = []
    for row in rows:
        entry = _row_to_entry(row)
        if entry.last_checked_at is None:
            overdue.append(entry)
            continue
        last = datetime.fromisoformat(entry.last_checked_at).replace(tzinfo=timezone.utc)
        if now - last >= timedelta(days=entry.check_interval_days):
            overdue.append(entry)
    return overdue


async def list_entries(tag: str = "", lang: str = "") -> list[LibraryEntry]:
    """Lista entradas com filtro opcional por tag e idioma."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT * FROM library_urls ORDER BY created_at DESC"
        )).fetchall()

    diff_ids = await _recent_diff_ids()
    entries: list[LibraryEntry] = []
    for row in rows:
        e = _row_to_entry(row, has_recent_diff=(row[0] in diff_ids))
        if tag and tag not in e.tags:
            continue
        if lang and e.language != lang:
            continue
        entries.append(e)
    return entries


async def update_entry(
    entry_id: int,
    notes: str | None = None,
    tags: list[str] | None = None,
    interval_days: int | None = None,
) -> None:
    """Atualiza campos editáveis de uma entrada."""
    parts: list[str] = []
    values: list[object] = []
    if notes is not None:
        parts.append("notes = ?")
        values.append(notes)
    if tags is not None:
        parts.append("tags_json = ?")
        values.append(json.dumps(tags))
    if interval_days is not None:
        parts.append("check_interval_days = ?")
        values.append(interval_days)
    if not parts:
        return
    values.append(entry_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE library_urls SET {', '.join(parts)} WHERE id = ?", values
        )
        await db.commit()


async def delete_entry(entry_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM library_fts WHERE url_id = ?", (str(entry_id),))
        await db.execute("DELETE FROM library_urls WHERE id = ?", (entry_id,))
        await db.commit()


async def get_diffs(entry_id: int, limit: int = 5) -> list[tuple[str, str]]:
    """Retorna os últimos diffs de uma entrada: [(scraped_at, diff_text)]."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT scraped_at, diff_text FROM library_diffs WHERE url_id = ? ORDER BY id DESC LIMIT ?",
            (entry_id, limit),
        )).fetchall()
    return [(row[0], row[1]) for row in rows]
