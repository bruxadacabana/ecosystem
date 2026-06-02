"""
Testes para sugestão de indexação de domínios frequentes no chat.

Cobre:
  - get_unindexed_frequent_domains: threshold, filtragem de já-indexados, limite
  - _build_prompt: injeção de contexto quando há sugestões
  - _build_prompt: sem injeção quando não há sugestões
  - Domínio com www. reconhecido como já indexado
  - Domínio abaixo do threshold não aparece
  - Domínio no crawl_sites não aparece mesmo com muitos cliques
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_AKASHA_ROOT = Path(__file__).parent.parent
if str(_AKASHA_ROOT) not in sys.path:
    sys.path.insert(0, str(_AKASHA_ROOT))


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(tmp_path):
    """Banco temporário com schema completo."""
    import database as _db

    orig_db  = _db.DB_PATH
    orig_kdb = _db.KNOWLEDGE_DB_PATH

    _db.DB_PATH = tmp_path / "akasha.db"
    _db.KNOWLEDGE_DB_PATH = tmp_path / "akasha_knowledge.db"
    _run(_db.init_db())

    yield _db

    _db.DB_PATH = orig_db
    _db.KNOWLEDGE_DB_PATH = orig_kdb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_clicks(db, domain: str, count: int, tmp_path):
    """Insere N cliques para um domínio no click_log."""
    import aiosqlite

    async def _do():
        async with aiosqlite.connect(db.DB_PATH) as conn:
            for _ in range(count):
                await conn.execute(
                    "INSERT INTO click_log (domain, url, query_norm) VALUES (?, ?, ?)",
                    (domain, f"https://{domain}/page", "test query"),
                )
            await conn.commit()

    _run(_do())


def _insert_site(db, base_url: str):
    """Adiciona domínio à Biblioteca (crawl_sites)."""
    _run(db.add_crawl_site(base_url, base_url, 2, "[]"))


# ---------------------------------------------------------------------------
# get_unindexed_frequent_domains
# ---------------------------------------------------------------------------

def test_frequent_domain_above_threshold(db, tmp_path):
    """Domínio clicado >= threshold vezes e não indexado deve aparecer."""
    _insert_clicks(db, "craftivism.com", 5, tmp_path)

    result = _run(db.get_unindexed_frequent_domains(threshold=3))

    domains = [d for d, _ in result]
    assert "craftivism.com" in domains


def test_domain_below_threshold_absent(db, tmp_path):
    """Domínio clicado < threshold vezes não deve aparecer."""
    _insert_clicks(db, "example.com", 2, tmp_path)

    result = _run(db.get_unindexed_frequent_domains(threshold=3))

    domains = [d for d, _ in result]
    assert "example.com" not in domains


def test_already_indexed_domain_filtered_out(db, tmp_path):
    """Domínio já na Biblioteca não deve aparecer nas sugestões."""
    _insert_clicks(db, "craftivism.com", 10, tmp_path)
    _insert_site(db, "https://craftivism.com")

    result = _run(db.get_unindexed_frequent_domains(threshold=3))

    domains = [d for d, _ in result]
    assert "craftivism.com" not in domains


def test_www_prefix_recognized_as_indexed(db, tmp_path):
    """Domínio clicado como 'craftivism.com' mas indexado como 'www.craftivism.com' deve ser filtrado."""
    _insert_clicks(db, "craftivism.com", 5, tmp_path)
    _insert_site(db, "https://www.craftivism.com")

    result = _run(db.get_unindexed_frequent_domains(threshold=3))

    domains = [d for d, _ in result]
    assert "craftivism.com" not in domains


def test_multiple_domains_sorted_by_count(db, tmp_path):
    """Domínios devem ser ordenados por contagem decrescente."""
    _insert_clicks(db, "b.com", 3, tmp_path)
    _insert_clicks(db, "a.com", 7, tmp_path)
    _insert_clicks(db, "c.com", 5, tmp_path)

    result = _run(db.get_unindexed_frequent_domains(threshold=3))

    counts = [c for _, c in result]
    assert counts == sorted(counts, reverse=True)


def test_returns_at_most_five(db, tmp_path):
    """Retorna no máximo 5 domínios mesmo se houver mais."""
    for i in range(8):
        _insert_clicks(db, f"domain{i}.com", 4, tmp_path)

    result = _run(db.get_unindexed_frequent_domains(threshold=3))

    assert len(result) <= 5


def test_empty_click_log_returns_empty(db, tmp_path):
    """Sem cliques, retorna lista vazia."""
    result = _run(db.get_unindexed_frequent_domains(threshold=3))
    assert result == []


def test_visit_count_returned_correctly(db, tmp_path):
    """A contagem retornada deve refletir o número real de cliques."""
    _insert_clicks(db, "craftivism.com", 6, tmp_path)

    result = _run(db.get_unindexed_frequent_domains(threshold=3))

    assert any(d == "craftivism.com" and c == 6 for d, c in result)


# ---------------------------------------------------------------------------
# _build_prompt — injeção de contexto
# ---------------------------------------------------------------------------

def test_build_prompt_injects_domain_context():
    """Com domain_suggestions, o system prompt deve mencionar os domínios."""
    from routers.chat import _build_prompt
    import config as _config

    orig = _config.PERSONALITY_PROMPT
    _config.PERSONALITY_PROMPT = "persona"
    try:
        msgs = _run(_build_prompt(
            question="Olá",
            snippets=[],
            persona_prefix="",
            domain_suggestions=[("craftivism.com", 4), ("ravelry.com", 3)],
        ))
    finally:
        _config.PERSONALITY_PROMPT = orig

    system_content = msgs[0]["content"]
    assert "craftivism.com" in system_content
    assert "ravelry.com" in system_content
    assert "Biblioteca" in system_content


def test_build_prompt_no_injection_when_no_suggestions():
    """Sem domain_suggestions, o system prompt não deve mencionar indexação de domínios."""
    from routers.chat import _build_prompt
    import config as _config

    orig = _config.PERSONALITY_PROMPT
    _config.PERSONALITY_PROMPT = "persona"
    try:
        msgs = _run(_build_prompt(
            question="Olá",
            snippets=[],
            persona_prefix="",
            domain_suggestions=None,
        ))
    finally:
        _config.PERSONALITY_PROMPT = orig

    system_content = msgs[0]["content"]
    # Não deve mencionar indexação proativa sem sugestões
    assert "Biblioteca local" not in system_content
    assert "não estão indexados" not in system_content


def test_build_prompt_no_injection_empty_list():
    """Com lista vazia, comportamento idêntico a None."""
    from routers.chat import _build_prompt
    import config as _config

    orig = _config.PERSONALITY_PROMPT
    _config.PERSONALITY_PROMPT = "persona"
    try:
        msgs = _run(_build_prompt(
            question="Olá",
            snippets=[],
            persona_prefix="",
            domain_suggestions=[],
        ))
    finally:
        _config.PERSONALITY_PROMPT = orig

    system_content = msgs[0]["content"]
    assert "não estão indexados" not in system_content


def test_build_prompt_limits_to_three_domains():
    """Mesmo com 5 sugestões, o prompt deve mencionar no máximo 3."""
    from routers.chat import _build_prompt
    import config as _config

    orig = _config.PERSONALITY_PROMPT
    _config.PERSONALITY_PROMPT = "persona"
    suggestions = [(f"domain{i}.com", 5 - i) for i in range(5)]
    try:
        msgs = _run(_build_prompt(
            question="Olá",
            snippets=[],
            persona_prefix="",
            domain_suggestions=suggestions,
        ))
    finally:
        _config.PERSONALITY_PROMPT = orig

    system_content = msgs[0]["content"]
    # Os 3 primeiros devem aparecer; o 4º e 5º não
    assert "domain0.com" in system_content
    assert "domain1.com" in system_content
    assert "domain2.com" in system_content
    assert "domain3.com" not in system_content
    assert "domain4.com" not in system_content
