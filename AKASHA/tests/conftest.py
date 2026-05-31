"""
Fixtures compartilhadas entre todos os testes do AKASHA.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_AKASHA_ROOT = Path(__file__).parent.parent
if str(_AKASHA_ROOT) not in sys.path:
    sys.path.insert(0, str(_AKASHA_ROOT))


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db_paths(tmp_path):
    """Banco AKASHA temporário com schema completo.

    Usado por testes que precisam de page_images, crawl_pages, FTS5, etc.
    Restaura DB_PATH após o teste.
    """
    import database as _db

    main_path = tmp_path / "akasha.db"
    knowledge_path = tmp_path / "akasha_knowledge.db"

    orig_db  = _db.DB_PATH
    orig_kdb = _db.KNOWLEDGE_DB_PATH
    _db.DB_PATH = main_path
    _db.KNOWLEDGE_DB_PATH = knowledge_path

    _run(_db.init_db())

    yield main_path, knowledge_path

    _db.DB_PATH = orig_db
    _db.KNOWLEDGE_DB_PATH = orig_kdb
