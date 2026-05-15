"""
AKASHA — Persistência de dados configurados pelo usuário em JSON.

Dados preciosos: sites crawleados, domínios bloqueados, domínios
favoritos, lenses e lista "ver mais tarde". Esses dados são inseridos no
banco SQLite a cada startup; o banco pode ser apagado sem perda alguma —
os JSONs são a fonte de verdade.

Escritas são atômicas: o conteúdo vai para um arquivo .tmp e só então
os.replace() o substitui pelo definitivo. Isso garante que uma queda de
energia ou crash nunca deixa um arquivo corrompido no meio da escrita.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from config import DB_PATH

DATA_DIR: Path = DB_PATH.parent / "userdata"

SITES_FILE       : Path = DATA_DIR / "sites.json"
BLOCKED_FILE     : Path = DATA_DIR / "blocked_domains.json"
FAVORITES_FILE   : Path = DATA_DIR / "favorites.json"
LENSES_FILE      : Path = DATA_DIR / "lenses.json"
WATCH_LATER_FILE : Path = DATA_DIR / "watch_later.json"


def _load(path: Path) -> list[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except Exception:
        return []


def _save(path: Path, items: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_sites() -> list[dict]:
    return _load(SITES_FILE)

def save_sites(items: list[dict]) -> None:
    _save(SITES_FILE, items)


def load_blocked_domains() -> list[dict]:
    return _load(BLOCKED_FILE)

def save_blocked_domains(items: list[dict]) -> None:
    _save(BLOCKED_FILE, items)


def load_favorites() -> list[dict]:
    return _load(FAVORITES_FILE)

def save_favorites(items: list[dict]) -> None:
    _save(FAVORITES_FILE, items)


def load_lenses() -> list[dict]:
    return _load(LENSES_FILE)

def save_lenses(items: list[dict]) -> None:
    _save(LENSES_FILE, items)


def load_watch_later() -> list[dict]:
    return _load(WATCH_LATER_FILE)

def save_watch_later(items: list[dict]) -> None:
    _save(WATCH_LATER_FILE, items)
