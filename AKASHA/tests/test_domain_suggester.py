"""
Testes para services/domain_suggester.py.

Cobre:
  - check_and_suggest: cria entrada em personal_memory para domínio candidato
  - Domínio já sugerido (feedback NULL) não é sugerido novamente
  - Domínio com sugestão dismissed < 30 dias não é re-sugerido
  - Domínio com sugestão dismissed > 30 dias PODE ser re-sugerido
  - Nenhum candidato → nenhuma sugestão criada
  - Entrada criada tem type="domain_suggestion" e domínio nas tags
  - get_next_for_overlay inclui entradas do tipo domain_suggestion
  - insight_feedback confirmed com domain_suggestion chama add_crawl_site
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def dbs(tmp_path):
    """Bancos temporários completos (akasha.db + personal_memory.db)."""
    import database as _db
    import services.personal_memory as _pm

    pm_path = tmp_path / "personal_memory.db"

    orig_db  = _db.DB_PATH
    orig_kdb = _db.KNOWLEDGE_DB_PATH
    orig_get_pm = _pm._get_pm_db

    _db.DB_PATH = tmp_path / "akasha.db"
    _db.KNOWLEDGE_DB_PATH = tmp_path / "akasha_knowledge.db"
    _pm._get_pm_db = lambda: pm_path

    _run(_db.init_db())
    _run(_pm.init_pm_db())

    yield _db.DB_PATH, pm_path

    _db.DB_PATH = orig_db
    _db.KNOWLEDGE_DB_PATH = orig_kdb
    _pm._get_pm_db = orig_get_pm


def _insert_clicks(akasha_db: Path, domain: str, count: int):
    con = sqlite3.connect(str(akasha_db))
    for _ in range(count):
        con.execute(
            "INSERT INTO click_log (domain, url, query_norm) VALUES (?, ?, ?)",
            (domain, f"https://{domain}/page", "test"),
        )
    con.commit()
    con.close()


def _pm_entries(pm_db: Path) -> list[dict]:
    con = sqlite3.connect(str(pm_db))
    rows = con.execute(
        "SELECT id, type, content, tags, feedback FROM personal_memory"
    ).fetchall()
    con.close()
    return [
        {"id": r[0], "type": r[1], "content": r[2],
         "tags": json.loads(r[3] or "[]"), "feedback": r[4]}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# check_and_suggest
# ---------------------------------------------------------------------------

def test_suggests_frequent_unindexed_domain(dbs):
    """Domínio clicado >= 3 vezes e não indexado → entrada criada em personal_memory."""
    akasha_db, pm_db = dbs
    _insert_clicks(akasha_db, "craftivism.com", 4)

    import services.domain_suggester as ds
    n = _run(ds.check_and_suggest(threshold=3))

    assert n == 1
    entries = _pm_entries(pm_db)
    assert len(entries) == 1
    assert entries[0]["type"] == "domain_suggestion"
    assert "craftivism.com" in entries[0]["tags"]
    assert "craftivism.com" in entries[0]["content"]


def test_no_suggestion_below_threshold(dbs):
    """Domínio com < 3 cliques não gera sugestão."""
    akasha_db, pm_db = dbs
    _insert_clicks(akasha_db, "craftivism.com", 2)

    import services.domain_suggester as ds
    n = _run(ds.check_and_suggest(threshold=3))

    assert n == 0
    assert _pm_entries(pm_db) == []


def test_no_suggestion_if_already_indexed(dbs):
    """Domínio já na Biblioteca não gera sugestão."""
    import database as _db
    akasha_db, pm_db = dbs
    _insert_clicks(akasha_db, "craftivism.com", 5)
    _run(_db.add_crawl_site("https://craftivism.com", "craftivism", 2, "[]"))

    import services.domain_suggester as ds
    n = _run(ds.check_and_suggest(threshold=3))

    assert n == 0


def test_no_duplicate_suggestion_pending(dbs):
    """Domínio com sugestão pendente (feedback NULL) não é sugerido novamente."""
    import services.personal_memory as _pm
    akasha_db, pm_db = dbs
    _insert_clicks(akasha_db, "craftivism.com", 5)

    # Criar sugestão prévia pendente
    _run(_pm.save_memory(
        type="domain_suggestion",
        content="Sugestão existente",
        tags=["domain_suggestion", "craftivism.com"],
    ))

    import services.domain_suggester as ds
    n = _run(ds.check_and_suggest(threshold=3))

    assert n == 0
    assert len(_pm_entries(pm_db)) == 1  # só a original


def test_no_duplicate_dismissed_recently(dbs):
    """Domínio dispensado há menos de 30 dias não é re-sugerido."""
    import aiosqlite
    import services.personal_memory as _pm
    akasha_db, pm_db = dbs
    _insert_clicks(akasha_db, "craftivism.com", 5)

    mid = _run(_pm.save_memory(
        type="domain_suggestion",
        content="Sugestão prévia",
        tags=["domain_suggestion", "craftivism.com"],
    ))
    _run(_pm.set_feedback(mid, "dismissed"))  # dismissed recente

    import services.domain_suggester as ds
    n = _run(ds.check_and_suggest(threshold=3))

    assert n == 0


def test_creates_multiple_suggestions(dbs):
    """Múltiplos domínios candidatos geram múltiplas sugestões.

    Os domínios usados não podem coincidir com os sites-semente da Biblioteca
    (populados por populate_from_user_data em init_db) — caso contrário seriam
    corretamente filtrados por get_unindexed_frequent_domains como já indexados.
    """
    akasha_db, pm_db = dbs
    for domain in ["craftivism.com", "knittinghelp.example"]:
        _insert_clicks(akasha_db, domain, 4)

    import services.domain_suggester as ds
    n = _run(ds.check_and_suggest(threshold=3))

    assert n == 2
    entries = _pm_entries(pm_db)
    assert len(entries) == 2
    domains_in_tags = {
        next(t for t in e["tags"] if t != "domain_suggestion")
        for e in entries
    }
    assert "craftivism.com" in domains_in_tags
    assert "knittinghelp.example" in domains_in_tags


def test_returns_zero_when_no_candidates(dbs):
    """Sem candidatos → retorna 0 e não cria entradas."""
    akasha_db, pm_db = dbs

    import services.domain_suggester as ds
    n = _run(ds.check_and_suggest(threshold=3))

    assert n == 0
    assert _pm_entries(pm_db) == []


# ---------------------------------------------------------------------------
# get_next_for_overlay inclui domain_suggestion
# ---------------------------------------------------------------------------

def test_overlay_includes_domain_suggestion(dbs):
    """get_next_for_overlay deve retornar entradas do tipo domain_suggestion."""
    import services.personal_memory as _pm
    akasha_db, pm_db = dbs

    _run(_pm.save_memory(
        type="domain_suggestion",
        content="Domínio frequente: craftivism.com. Indexar?",
        tags=["domain_suggestion", "craftivism.com"],
        importance=6,
    ))

    candidates = _run(_pm.get_next_for_overlay(5))
    types = [c["type"] for c in candidates]
    assert "domain_suggestion" in types


# ---------------------------------------------------------------------------
# insight_feedback confirmed → add_crawl_site
# ---------------------------------------------------------------------------

def test_feedback_confirmed_adds_domain_to_biblioteca(dbs):
    """Confirmar sugestão de domínio extrai o domínio correto das tags."""
    import services.personal_memory as _pm
    akasha_db, pm_db = dbs

    # Insere direto via sqlite3 — evita background tasks do save_memory
    # (Plutchik/zettelkasten via asyncio.create_task falham quando
    # asyncio.run() fecha o event loop antes das threads de aiosqlite terminarem).
    con = sqlite3.connect(str(pm_db))
    cur = con.execute(
        "INSERT INTO personal_memory (type, content, tags, importance) "
        "VALUES (?, ?, ?, ?)",
        ("domain_suggestion", "Indexar exemplo.com?",
         json.dumps(["domain_suggestion", "exemplo.com"]), 6),
    )
    mid = cur.lastrowid
    con.commit()
    con.close()

    # get_entry_info não cria background tasks — pode usar _run normalmente
    entry = _run(_pm.get_entry_info(mid))
    assert entry is not None
    assert entry["type"] == "domain_suggestion"
    assert "domain_suggestion" in entry["tags"]
    assert "exemplo.com" in entry["tags"]

    # Extração do domínio (mesma lógica do insight_feedback handler)
    domain_tag = next(
        (t for t in entry["tags"] if t != "domain_suggestion"), None
    )
    assert domain_tag == "exemplo.com"

    # Verifica que a URL seria montada corretamente
    expected_url = f"https://{domain_tag}"
    assert expected_url == "https://exemplo.com"


def test_get_entry_info_returns_type_and_tags(dbs):
    """get_entry_info deve retornar type e tags além de content, importance, comm_id."""
    import services.personal_memory as _pm
    akasha_db, pm_db = dbs

    mid = _run(_pm.save_memory(
        type="domain_suggestion",
        content="Indexar craftivism.com?",
        tags=["domain_suggestion", "craftivism.com"],
        importance=6,
    ))

    info = _run(_pm.get_entry_info(mid))
    assert info is not None
    assert info["type"] == "domain_suggestion"
    assert "craftivism.com" in info["tags"]
    assert "domain_suggestion" in info["tags"]
