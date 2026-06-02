"""
Testes para domain_quality — ranking boost por arquivamento.

Cobre:
  - increment_domain_archive: cria entrada e incrementa archive_count
  - increment_domain_archive: quality_score = archive_count × 2.0
  - increment_domain_archive: múltiplas chamadas acumulam corretamente
  - increment_domain_archive: normaliza www. prefix
  - increment_domain_archive: domínio vazio não cria entrada
  - get_domain_quality_boosts: boost = 1.0 + score/10 para domínio com histórico
  - get_domain_quality_boosts: boost = 1.0 (neutro) para domínio sem histórico
  - get_domain_quality_boosts: boost capped em 3.0
  - get_domain_quality_boosts: retorna dict vazio para lista vazia
  - _apply_quality_boost: reordena resultados para domínio com boost
  - _apply_quality_boost: não reordena quando todos os boosts são 1.0
  - _apply_quality_boost: lista vazia retorna lista vazia
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import types
import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ddgs não está instalado no Python do sistema — mock antes de importar local_search
if "ddgs" not in sys.modules:
    _fake_ddgs = types.ModuleType("ddgs")
    _fake_ddgs.DDGS = object  # type: ignore
    sys.modules["ddgs"] = _fake_ddgs


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(tmp_path):
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
# increment_domain_archive
# ---------------------------------------------------------------------------

def test_increment_creates_entry(db):
    """Primeira chamada cria entrada com archive_count=1."""
    _run(db.increment_domain_archive("exemplo.com"))
    boosts = _run(db.get_domain_quality_boosts(["exemplo.com"]))
    assert "exemplo.com" in boosts
    assert boosts["exemplo.com"] > 1.0


def test_increment_accumulates(db):
    """Múltiplas chamadas acumulam archive_count corretamente."""
    for _ in range(3):
        _run(db.increment_domain_archive("exemplo.com"))

    import aiosqlite

    async def _check():
        async with aiosqlite.connect(db.DB_PATH) as conn:
            row = await (await conn.execute(
                "SELECT archive_count, quality_score FROM domain_quality WHERE domain='exemplo.com'"
            )).fetchone()
        return row

    row = _run(_check())
    assert row is not None
    assert row[0] == 3                       # archive_count = 3
    assert abs(row[1] - 3 * 2.0) < 0.01     # quality_score = 6.0


def test_increment_normalizes_www(db):
    """www. prefix é removido antes de armazenar."""
    _run(db.increment_domain_archive("www.exemplo.com"))
    boosts = _run(db.get_domain_quality_boosts(["exemplo.com"]))
    assert "exemplo.com" in boosts
    assert boosts["exemplo.com"] > 1.0


def test_increment_empty_domain_ignored(db):
    """Domínio vazio não cria entrada."""
    _run(db.increment_domain_archive(""))
    boosts = _run(db.get_domain_quality_boosts([""]))
    assert boosts == {}


# ---------------------------------------------------------------------------
# get_domain_quality_boosts
# ---------------------------------------------------------------------------

def test_boost_neutral_for_unknown_domain(db):
    """Domínio sem histórico recebe boost 1.0 (neutro)."""
    boosts = _run(db.get_domain_quality_boosts(["desconhecido.com"]))
    # Domínio não está na tabela — deve retornar dict vazio ou 1.0
    assert boosts.get("desconhecido.com", 1.0) == 1.0


def test_boost_formula(db):
    """boost = 1.0 + quality_score / 10.0."""
    _run(db.increment_domain_archive("exemplo.com"))   # quality_score = 2.0
    boosts = _run(db.get_domain_quality_boosts(["exemplo.com"]))
    expected = 1.0 + 2.0 / 10.0   # = 1.2
    assert abs(boosts["exemplo.com"] - expected) < 0.01


def test_boost_capped_at_3(db):
    """Boost é limitado a 3.0 mesmo com muitos arquivos."""
    for _ in range(50):
        _run(db.increment_domain_archive("exemplo.com"))  # quality_score = 100.0
    boosts = _run(db.get_domain_quality_boosts(["exemplo.com"]))
    assert boosts["exemplo.com"] <= 3.0


def test_boost_empty_list(db):
    """Lista vazia retorna dict vazio."""
    boosts = _run(db.get_domain_quality_boosts([]))
    assert boosts == {}


def test_boost_multiple_domains(db):
    """Retorna boosts corretos para múltiplos domínios."""
    _run(db.increment_domain_archive("site-a.com"))
    _run(db.increment_domain_archive("site-a.com"))  # 2 arquivos → score 4.0
    boosts = _run(db.get_domain_quality_boosts(["site-a.com", "site-b.com"]))
    # site-a tem boost > 1.0; site-b não está na tabela → ausente ou 1.0
    assert boosts.get("site-a.com", 1.0) > 1.0
    assert boosts.get("site-b.com", 1.0) == 1.0


# ---------------------------------------------------------------------------
# _apply_quality_boost
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, url, title="T", snippet="S"):
        self.url     = url
        self.title   = title
        self.snippet = snippet


def test_apply_quality_boost_reorders(db):
    """Resultado de domínio com boost alto deve subir no ranking.

    Para posição 1 superar posição 0 com boost neutro, o boost precisa ser > 2.0,
    ou seja quality_score > 10.0 → archive_count >= 6. Usamos 6 arquivos.
    """
    for _ in range(6):
        _run(db.increment_domain_archive("bom.com"))
    # quality_score = 12.0 → boost = 1 + 12/10 = 2.2
    # score posicional: pos0 → 1.0×1.0=1.0; pos1 → 0.5×2.2=1.1 → bom.com sobe

    results = [
        _FakeResult("https://ruim.com/page"),
        _FakeResult("https://bom.com/page"),
    ]

    from services.local_search import _apply_quality_boost

    with patch("database.DB_PATH", db.DB_PATH):
        reordered = _run(_apply_quality_boost(results))

    # bom.com (com boost 2.2) deve superar ruim.com (boost 1.0)
    from urllib.parse import urlparse
    first_domain = urlparse(reordered[0].url).netloc.removeprefix("www.")
    assert first_domain == "bom.com"


def test_apply_quality_boost_no_change_without_data(db):
    """Sem histórico de arquivos, a ordem original é mantida."""
    results = [
        _FakeResult("https://site-x.com/page"),
        _FakeResult("https://site-y.com/page"),
    ]
    from services.local_search import _apply_quality_boost

    with patch("database.DB_PATH", db.DB_PATH):
        reordered = _run(_apply_quality_boost(results))

    assert reordered[0].url == results[0].url
    assert reordered[1].url == results[1].url


def test_apply_quality_boost_empty_list(db):
    """Lista vazia retorna lista vazia."""
    from services.local_search import _apply_quality_boost
    result = _run(_apply_quality_boost([]))
    assert result == []
