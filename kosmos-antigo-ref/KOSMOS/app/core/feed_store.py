"""
KOSMOS — Persistência de feeds e categorias em JSON.

Feeds e categorias são dados configurados pelo usuário — insubstituíveis
se o banco SQLite corromper. Persiste em dois formatos:

- Local (userdata/): feeds.json + categories.json — fallback sempre disponível.
- Backup (sync_root/.backup/kosmos/): sources.json combinado {"feeds":[...],"categories":[...]}
  — fonte de verdade sincronizada via Syncthing.

Escritas são atômicas: .tmp + os.replace() evita corrupção parcial.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from app.utils.paths import Paths

DATA_DIR: Path = Paths.DATA / "userdata"

FEEDS_FILE      : Path = DATA_DIR / "feeds.json"
CATEGORIES_FILE : Path = DATA_DIR / "categories.json"


def _get_backup_sources() -> Path | None:
    """Retorna caminho para {backup_dir}/kosmos/sources.json, ou None."""
    try:
        _root = str(Path(__file__).parent.parent.parent.parent)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from ecosystem_client import get_backup_dir  # type: ignore
        d = get_backup_dir()
        if d is not None:
            target = d / "kosmos"
            target.mkdir(parents=True, exist_ok=True)
            return target / "sources.json"
    except Exception:
        pass
    return None


def _load(path: Path) -> list[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except Exception:
        return []


def _save(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _load_sources_backup() -> dict | None:
    """Lê sources.json do backup; retorna None se não disponível."""
    p = _get_backup_sources()
    if p is None or not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def _update_sources_backup(feeds: list[dict] | None = None,
                            categories: list[dict] | None = None) -> None:
    """Atualiza sources.json no backup (read-modify-write, atômico)."""
    p = _get_backup_sources()
    if p is None:
        return
    try:
        current: dict = {}
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    current = data
            except Exception:
                pass
        if feeds is not None:
            current["feeds"] = feeds
        if categories is not None:
            current["categories"] = categories
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)
    except Exception:
        pass


def load_feeds() -> list[dict]:
    src = _load_sources_backup()
    if src is not None and "feeds" in src:
        return src["feeds"]
    return _load(FEEDS_FILE)

def save_feeds(feeds: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _save(FEEDS_FILE, feeds)
    _update_sources_backup(feeds=feeds)


def load_categories() -> list[dict]:
    src = _load_sources_backup()
    if src is not None and "categories" in src:
        return src["categories"]
    return _load(CATEGORIES_FILE)

def save_categories(cats: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _save(CATEGORIES_FILE, cats)
    _update_sources_backup(categories=cats)
