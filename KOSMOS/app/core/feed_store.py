"""
KOSMOS — Persistência de feeds e categorias em JSON.

Feeds e categorias são dados configurados pelo usuário — insubstituíveis
se o banco SQLite corromper. Este módulo os persiste em dois arquivos JSON
no diretório de dados do app; o banco é populado a partir deles no startup.

Escritas são atômicas: .tmp + os.replace() evita corrupção parcial.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from app.utils.paths import Paths

DATA_DIR: Path = Paths.DATA / "userdata"

FEEDS_FILE      : Path = DATA_DIR / "feeds.json"
CATEGORIES_FILE : Path = DATA_DIR / "categories.json"


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


def load_feeds() -> list[dict]:
    return _load(FEEDS_FILE)

def save_feeds(feeds: list[dict]) -> None:
    _save(FEEDS_FILE, feeds)


def load_categories() -> list[dict]:
    return _load(CATEGORIES_FILE)

def save_categories(cats: list[dict]) -> None:
    _save(CATEGORIES_FILE, cats)
