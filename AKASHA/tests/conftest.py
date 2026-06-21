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
    """Roda uma corrotina nos testes **sem deixar o event loop atual zerado**.

    `asyncio.run()` chama `set_event_loop(None)` ao terminar; no Python 3.13 isso faz
    `asyncio.get_event_loop()` levantar `RuntimeError`. Como dezenas de testes usam
    `asyncio.get_event_loop().run_until_complete(...)`, um `_run()` (ou qualquer
    `asyncio.run()`) anterior os quebrava por ordem de execução (BUG-044). Aqui rodamos
    num loop próprio e restauramos um loop atual válido no fim.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


@pytest.fixture(autouse=True)
def _ensure_current_event_loop():
    """Garante um event loop atual válido para cada teste (py3.13).

    Muitos testes chamam `asyncio.get_event_loop().run_until_complete(...)`; um
    `asyncio.run()` de teste/fixture anterior pode ter zerado (ou fechado) o loop
    atual, fazendo `get_event_loop()` levantar. Esta fixture autouse normaliza o
    estado no início de cada teste — defesa contra poluição entre testes (BUG-044).
    """
    policy = asyncio.get_event_loop_policy()
    try:
        loop = policy.get_event_loop()
        valid = loop is not None and not loop.is_closed()
    except (RuntimeError, AssertionError):
        valid = False
    if not valid:
        asyncio.set_event_loop(asyncio.new_event_loop())
    yield


@pytest.fixture(autouse=True)
def _disable_marginalia_by_default(request, monkeypatch):
    """Desabilita a Marginalia (busca web complementar, externa) por padrão em todos
    os testes — evita chamadas de rede reais e mantém o comportamento de `_fetch_web`
    determinístico (SearXNG/DDG) nos testes que não são sobre a Marginalia.

    Exceção: `test_marginalia.py`, que testa a Marginalia de verdade e re-patcha
    o que precisar.
    """
    if request.module.__name__.rsplit(".", 1)[-1] == "test_marginalia":
        return
    try:
        import services.web_search as _ws
    except Exception:
        return

    async def _empty(query, api_key, max_results):  # noqa: ARG001
        return []

    monkeypatch.setattr(_ws, "_get_marginalia_key", lambda: "", raising=False)
    monkeypatch.setattr(_ws, "_fetch_marginalia", _empty, raising=False)


@pytest.fixture(autouse=True)
def _isolate_sync_root(tmp_path_factory, monkeypatch):
    """Isola os stores compartilhados em sync_root (shared_history,
    shared_topic_profile) num diretório temporário em TODOS os testes — nunca
    escreve no sync_root real da usuária. Testes que precisam de um sync_root
    específico podem re-patchar `ecosystem_client.get_sync_root`.
    """
    try:
        import ecosystem_client  # noqa: PLC0415
    except Exception:
        return
    d = tmp_path_factory.mktemp("sync_root")
    monkeypatch.setattr(ecosystem_client, "get_sync_root", lambda: d, raising=False)


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
