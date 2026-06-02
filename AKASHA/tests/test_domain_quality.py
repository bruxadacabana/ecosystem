"""
Testes para domain_quality — reputação de domínio acumulada por histórico de uso.

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
  - increment_domain_click / confirmed_insight / dismissed: cada sinal soma/subtrai seu peso
  - boost < 1.0 (penalidade) para domínio dispensado, com piso _QUALITY_BOOST_FLOOR
  - click saturação em _CLICK_CAP
  - fórmula combinada: 3 arquivos + 1 confirmado > apenas visitado
  - sinais misturados recalculam o score pela soma ponderada
  - DDL fresco já contém as colunas de reputação
  - migration 53 faz backfill de click_count dos últimos 90 dias
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


def test_migration_backfills_existing_archives(tmp_path):
    """Migration 52 deve popular domain_quality com arquivos pré-existentes em archive_simhashes."""
    import database as _db
    import aiosqlite

    orig_db  = _db.DB_PATH
    orig_kdb = _db.KNOWLEDGE_DB_PATH

    _db.DB_PATH = tmp_path / "akasha.db"
    _db.KNOWLEDGE_DB_PATH = tmp_path / "akasha_knowledge.db"

    # Cria banco na versão 51 (sem domain_quality) e insere arquivos históricos
    async def _setup():
        async with aiosqlite.connect(_db.DB_PATH) as conn:
            await conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE archive_simhashes (
                    id INTEGER PRIMARY KEY, simhash INTEGER, path TEXT, url TEXT
                );
                CREATE TABLE archive_dois (
                    id INTEGER PRIMARY KEY, doi TEXT, arxiv_id TEXT, path TEXT, url TEXT
                );
                INSERT INTO settings VALUES ('schema_version', '51');
                INSERT INTO archive_simhashes (simhash, path, url) VALUES
                    (1, '/archive/a.md', 'https://exemplo.com/artigo'),
                    (2, '/archive/b.md', 'https://exemplo.com/outro'),
                    (3, '/archive/c.md', 'https://www.outro-site.com/pagina');
            """)
            await conn.commit()

    _run(_setup())

    # Roda init_db — aplica migration 52 com backfill
    _run(_db.init_db())

    # Verifica que domain_quality foi populada corretamente
    async def _check():
        async with aiosqlite.connect(_db.DB_PATH) as conn:
            rows = await (await conn.execute(
                "SELECT domain, archive_count, quality_score FROM domain_quality ORDER BY domain"
            )).fetchall()
        return {r[0]: (r[1], r[2]) for r in rows}

    result = _run(_check())

    assert "exemplo.com" in result
    assert result["exemplo.com"][0] == 2      # 2 arquivos
    assert abs(result["exemplo.com"][1] - 4.0) < 0.01   # quality_score = 4.0

    assert "outro-site.com" in result
    assert result["outro-site.com"][0] == 1   # 1 arquivo, www removido
    assert abs(result["outro-site.com"][1] - 2.0) < 0.01

    _db.DB_PATH = orig_db
    _db.KNOWLEDGE_DB_PATH = orig_kdb


def test_apply_quality_boost_empty_list(db):
    """Lista vazia retorna lista vazia."""
    from services.local_search import _apply_quality_boost
    result = _run(_apply_quality_boost([]))
    assert result == []


# ---------------------------------------------------------------------------
# Reputação acumulada — sinais de clique, insight confirmado e dispensado
# ---------------------------------------------------------------------------

import aiosqlite


def _score(db, domain):
    """Lê quality_score corrente de um domínio (ou None se ausente)."""
    async def _q():
        async with aiosqlite.connect(db.DB_PATH) as conn:
            row = await (await conn.execute(
                "SELECT quality_score FROM domain_quality WHERE domain=?", (domain,)
            )).fetchone()
        return row[0] if row else None
    return _run(_q())


def _counts(db, domain):
    """Lê todas as colunas de sinal de um domínio."""
    async def _q():
        async with aiosqlite.connect(db.DB_PATH) as conn:
            row = await (await conn.execute(
                "SELECT archive_count, click_count, confirmed_insight_count, dismissed_count "
                "FROM domain_quality WHERE domain=?", (domain,)
            )).fetchone()
        return row
    return _run(_q())


def test_click_increments_score(db):
    """increment_domain_click soma _CLICK_WEIGHT (0.5) ao quality_score."""
    _run(db.increment_domain_click("clicado.com"))
    assert abs(_score(db, "clicado.com") - 0.5) < 0.01
    assert _counts(db, "clicado.com") == (0, 1, 0, 0)


def test_confirmed_insight_increments_score(db):
    """increment_domain_confirmed_insight soma _CONFIRMED_WEIGHT (1.5)."""
    _run(db.increment_domain_confirmed_insight("confiavel.com"))
    assert abs(_score(db, "confiavel.com") - 1.5) < 0.01
    assert _counts(db, "confiavel.com") == (0, 0, 1, 0)


def test_dismissed_penalizes_score(db):
    """increment_domain_dismissed subtrai _DISMISSED_WEIGHT (0.5) → score negativo."""
    _run(db.increment_domain_dismissed("ruim.com"))
    assert abs(_score(db, "ruim.com") - (-0.5)) < 0.01
    assert _counts(db, "ruim.com") == (0, 0, 0, 1)


def test_dismissed_boost_below_one(db):
    """Domínio com penalidade recebe boost < 1.0 (rebaixado no ranking)."""
    for _ in range(3):
        _run(db.increment_domain_dismissed("ruim.com"))  # score = -1.5
    boosts = _run(db.get_domain_quality_boosts(["ruim.com"]))
    assert boosts["ruim.com"] < 1.0
    assert boosts["ruim.com"] >= db._QUALITY_BOOST_FLOOR


def test_click_saturates_at_cap(db):
    """Cliques além de _CLICK_CAP não aumentam mais o quality_score."""
    for _ in range(db._CLICK_CAP + 5):
        _run(db.increment_domain_click("popular.com"))
    expected = db._CLICK_CAP * db._CLICK_WEIGHT   # 20 × 0.5 = 10.0
    assert abs(_score(db, "popular.com") - expected) < 0.01


def test_combined_formula_archive_plus_confirmed(db):
    """Domínio com 3 arquivos + 1 insight confirmado supera domínio apenas visitado.

    A = 3×2.0 + 1×1.5 = 7.5  ;  B = 1×0.5 = 0.5  →  boost(A) > boost(B).
    """
    for _ in range(3):
        _run(db.increment_domain_archive("forte.com"))
    _run(db.increment_domain_confirmed_insight("forte.com"))
    _run(db.increment_domain_click("fraco.com"))

    assert abs(_score(db, "forte.com") - 7.5) < 0.01
    assert abs(_score(db, "fraco.com") - 0.5) < 0.01

    boosts = _run(db.get_domain_quality_boosts(["forte.com", "fraco.com"]))
    assert boosts["forte.com"] > boosts["fraco.com"]


def test_mixed_signals_recompute(db):
    """Sinais misturados recalculam o score pela fórmula ponderada combinada."""
    _run(db.increment_domain_archive("mix.com"))            # +2.0
    _run(db.increment_domain_archive("mix.com"))            # +2.0  → 4.0
    _run(db.increment_domain_confirmed_insight("mix.com"))  # +1.5  → 5.5
    _run(db.increment_domain_click("mix.com"))              # +0.5  → 6.0
    _run(db.increment_domain_dismissed("mix.com"))          # -0.5  → 5.5
    # 2×2.0 + 1×1.5 + min(1,20)×0.5 − 1×0.5 = 4.0 + 1.5 + 0.5 − 0.5 = 5.5
    assert abs(_score(db, "mix.com") - 5.5) < 0.01
    assert _counts(db, "mix.com") == (2, 1, 1, 1)


def test_signal_empty_domain_ignored(db):
    """Domínio vazio não cria entrada em nenhum dos sinais."""
    _run(db.increment_domain_click(""))
    _run(db.increment_domain_confirmed_insight(""))
    _run(db.increment_domain_dismissed(""))
    assert _run(db.get_domain_quality_boosts([""])) == {}


def test_signal_normalizes_www(db):
    """Prefixo www. é removido antes de gravar o sinal."""
    _run(db.increment_domain_confirmed_insight("www.exemplo.com"))
    assert _counts(db, "exemplo.com") == (0, 0, 1, 0)


def test_fresh_db_has_reputation_columns(db):
    """Banco criado do zero já possui as colunas de reputação (DDL atualizado)."""
    async def _cols():
        async with aiosqlite.connect(db.DB_PATH) as conn:
            rows = await (await conn.execute("PRAGMA table_info(domain_quality)")).fetchall()
        return {r[1] for r in rows}
    cols = _run(_cols())
    assert {"click_count", "confirmed_insight_count", "dismissed_count"} <= cols


def test_migration_53_backfills_clicks(tmp_path):
    """Migration 53 popula click_count a partir do click_log dos últimos 90 dias."""
    import database as _db

    orig_db  = _db.DB_PATH
    orig_kdb = _db.KNOWLEDGE_DB_PATH

    _db.DB_PATH = tmp_path / "akasha.db"
    _db.KNOWLEDGE_DB_PATH = tmp_path / "akasha_knowledge.db"

    async def _setup():
        async with aiosqlite.connect(_db.DB_PATH) as conn:
            await conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE archive_simhashes (id INTEGER PRIMARY KEY, simhash INTEGER, path TEXT, url TEXT);
                CREATE TABLE archive_dois (id INTEGER PRIMARY KEY, doi TEXT, arxiv_id TEXT, path TEXT, url TEXT);
                CREATE TABLE click_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    query_norm TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '',
                    domain TEXT NOT NULL DEFAULT '',
                    position_clicked INTEGER NOT NULL DEFAULT 0,
                    session_id TEXT NOT NULL DEFAULT ''
                );
                INSERT INTO settings VALUES ('schema_version', '51');
                INSERT INTO click_log (timestamp, domain) VALUES
                    (strftime('%s','now'), 'noticias.com'),
                    (strftime('%s','now'), 'noticias.com'),
                    (strftime('%s','now','-200 days'), 'antigo.com');
            """)
            await conn.commit()

    _run(_setup())
    _run(_db.init_db())

    async def _check():
        async with aiosqlite.connect(_db.DB_PATH) as conn:
            rows = await (await conn.execute(
                "SELECT domain, click_count, quality_score FROM domain_quality ORDER BY domain"
            )).fetchall()
        return {r[0]: (r[1], r[2]) for r in rows}

    result = _run(_check())

    assert "noticias.com" in result
    assert result["noticias.com"][0] == 2                      # 2 cliques recentes
    assert abs(result["noticias.com"][1] - 2 * 0.5) < 0.01     # score = 1.0
    # clique de 200 dias atrás está fora da janela de 90 dias → não conta
    assert "antigo.com" not in result

    _db.DB_PATH = orig_db
    _db.KNOWLEDGE_DB_PATH = orig_kdb
