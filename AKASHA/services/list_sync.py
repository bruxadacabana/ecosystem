"""
AKASHA — Sincronização de listas com .backup/akasha/.

JSON é a fonte de verdade para listas configuradas pelo usuário.
Lê de {sync_root}/.backup/akasha/ se disponível; cai em userdata/ local.
Escreve sempre no caminho canônico (backup se configurado, local caso contrário).
Escritas são atômicas (tmp + os.replace) e fire-and-forget via asyncio.create_task().
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import aiosqlite

from config import DB_PATH

_log = logging.getLogger("akasha.list_sync")

# Caminho de fallback local (histórico — antecede sync_root)
_LOCAL_DIR: Path = DB_PATH.parent / "userdata"

# Mapeamento: nome canônico → nome legado no userdata/
_LEGACY_NAMES: dict[str, str] = {
    "blocklist": "blocked_domains",
}

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _get_backup_dir() -> Path | None:
    """Retorna {sync_root}/.backup/akasha/ ou None se sync_root não configurado."""
    try:
        from ecosystem_client import get_backup_dir
        d = get_backup_dir()
        if d is not None:
            target = d / "akasha"
            target.mkdir(parents=True, exist_ok=True)
            return target
    except Exception:
        pass
    return None


def _canonical_read_path(list_name: str) -> Path:
    """
    Retorna caminho para leitura: backup dir (se disponível e arquivo existe),
    senão backup dir (para acostumar o sistema com o novo local),
    senão legacy userdata/.
    """
    backup = _get_backup_dir()
    if backup is not None:
        p = backup / f"{list_name}.json"
        if p.exists():
            return p
    legacy_name = _LEGACY_NAMES.get(list_name, list_name)
    return _LOCAL_DIR / f"{legacy_name}.json"


def _canonical_write_path(list_name: str) -> Path:
    """Retorna caminho para escrita: backup dir se disponível, senão legacy userdata/."""
    backup = _get_backup_dir()
    if backup is not None:
        return backup / f"{list_name}.json"
    legacy_name = _LEGACY_NAMES.get(list_name, list_name)
    return _LOCAL_DIR / f"{legacy_name}.json"


def _load_json(path: Path) -> list[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except Exception:
        return []


def _save_json(path: Path, items: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Funções de leitura (startup — síncronas, chamadas antes do event loop)
# ---------------------------------------------------------------------------

def load_sites() -> list[dict]:
    return _load_json(_canonical_read_path("sites"))

def load_blocked_domains() -> list[dict]:
    return _load_json(_canonical_read_path("blocklist"))

def load_favorites() -> list[dict]:
    return _load_json(_canonical_read_path("favorites"))

def load_lenses() -> list[dict]:
    return _load_json(_canonical_read_path("lenses"))

def load_watch_later() -> list[dict]:
    return _load_json(_canonical_read_path("watch_later"))

def load_highlights() -> list[dict]:
    return _load_json(_canonical_read_path("highlights"))

def load_papers() -> list[dict]:
    return _load_json(_canonical_read_path("papers"))


# ---------------------------------------------------------------------------
# Função de escrita (fire-and-forget — assíncrona, lê do DB e escreve JSON)
# ---------------------------------------------------------------------------

async def write_json(list_name: str) -> None:
    """Serializa tabela → JSON canônico. Chamar via asyncio.create_task()."""
    try:
        path = _canonical_write_path(list_name)
        items: list = []

        async with aiosqlite.connect(DB_PATH) as db:
            if list_name == "sites":
                rows = await (await db.execute(
                    "SELECT base_url, label, crawl_depth, subdomains_json, created_at, "
                    "crawl_interval_days FROM crawl_sites ORDER BY created_at"
                )).fetchall()
                items = [
                    {
                        "base_url": r[0], "label": r[1], "crawl_depth": r[2],
                        "subdomains": json.loads(r[3] or "[]"), "created_at": r[4],
                        "crawl_interval_days": r[5] if r[5] is not None else 7,
                    }
                    for r in rows
                ]

            elif list_name == "favorites":
                rows = await (await db.execute(
                    "SELECT domain, label, priority_score, added_at "
                    "FROM favorite_domains ORDER BY priority_score DESC, added_at"
                )).fetchall()
                items = [
                    {"domain": r[0], "label": r[1], "priority_score": r[2], "added_at": r[3]}
                    for r in rows
                ]

            elif list_name == "blocklist":
                rows = await (await db.execute(
                    "SELECT domain, added_at FROM blocked_domains ORDER BY added_at"
                )).fetchall()
                items = [{"domain": r[0], "added_at": r[1]} for r in rows]

            elif list_name == "watch_later":
                rows = await (await db.execute(
                    "SELECT url, title, snippet, notes, added_at "
                    "FROM watch_later ORDER BY added_at"
                )).fetchall()
                items = [
                    {
                        "url": r[0], "title": r[1], "snippet": r[2],
                        "notes": r[3], "added_at": r[4],
                    }
                    for r in rows
                ]

            elif list_name == "lenses":
                rows = await (await db.execute(
                    "SELECT name, domains, tags, content_types, date_from, date_to, created_at "
                    "FROM lenses ORDER BY created_at"
                )).fetchall()
                items = [
                    {
                        "name": r[0], "domains": r[1], "tags": r[2],
                        "content_types": r[3], "date_from": r[4],
                        "date_to": r[5], "created_at": r[6],
                    }
                    for r in rows
                ]

            elif list_name == "highlights":
                rows = await (await db.execute(
                    "SELECT url, exact, prefix, suffix, note, created_at "
                    "FROM highlights ORDER BY created_at"
                )).fetchall()
                items = [
                    {
                        "url": r[0], "exact": r[1], "prefix": r[2],
                        "suffix": r[3], "note": r[4], "created_at": r[5],
                    }
                    for r in rows
                ]

            elif list_name == "papers":
                rows = await (await db.execute(
                    "SELECT doi, arxiv_id, path, url FROM archive_dois"
                )).fetchall()
                items = [
                    {"doi": r[0], "arxiv_id": r[1], "path": r[2], "url": r[3]}
                    for r in rows
                ]

            else:
                _log.warning("write_json: list_name desconhecido: %s", list_name)
                return

        _save_json(path, items)
    except Exception as exc:
        _log.warning("write_json(%s): %s", list_name, exc)
