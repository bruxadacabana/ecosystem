"""
Testes para log_visit_dedup, get_recent_visits e get_top_visited_domains.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db(tmp_path):
    import database as _db

    orig = _db.DB_PATH
    _db.DB_PATH = tmp_path / "akasha.db"
    run(_db.init_db())
    yield _db
    _db.DB_PATH = orig


# ---------------------------------------------------------------------------
# log_visit_dedup
# ---------------------------------------------------------------------------

class TestLogVisitDedup:
    def test_insere_visita(self, db):
        run(db.log_visit_dedup("https://example.com/page", "Example Page"))
        visits = run(db.get_recent_visits(10))
        assert len(visits) == 1
        assert visits[0]["url"] == "https://example.com/page"
        assert visits[0]["title"] == "Example Page"

    def test_dedup_mesma_url_na_janela(self, db):
        run(db.log_visit_dedup("https://example.com/page", "Page"))
        run(db.log_visit_dedup("https://example.com/page", "Page"))
        visits = run(db.get_recent_visits(10))
        assert len(visits) == 1

    def test_urls_diferentes_sao_ambas_inseridas(self, db):
        run(db.log_visit_dedup("https://a.com/", "Site A"))
        run(db.log_visit_dedup("https://b.com/", "Site B"))
        visits = run(db.get_recent_visits(10))
        assert len(visits) == 2

    def test_titulo_vazio_usa_url_como_fallback(self, db):
        run(db.log_visit_dedup("https://example.com/", ""))
        visits = run(db.get_recent_visits(10))
        assert visits[0]["title"] == "https://example.com/"

    def test_visitas_separadas_acumulam(self, db):
        """Cinco URLs distintas geram cinco entradas."""
        for i in range(5):
            run(db.log_visit_dedup(f"https://site{i}.com/", f"Site {i}"))
        visits = run(db.get_recent_visits(10))
        assert len(visits) == 5


# ---------------------------------------------------------------------------
# get_recent_visits
# ---------------------------------------------------------------------------

class TestGetRecentVisits:
    def test_retorna_mais_recente_primeiro(self, db):
        run(db.log_visit_dedup("https://first.com/", "First", window_minutes=0))
        run(db.log_visit_dedup("https://second.com/", "Second", window_minutes=0))
        visits = run(db.get_recent_visits(10))
        assert visits[0]["url"] == "https://second.com/"

    def test_respeita_limite(self, db):
        for i in range(5):
            run(db.log_visit_dedup(f"https://site{i}.com/", f"Site {i}", window_minutes=0))
        visits = run(db.get_recent_visits(3))
        assert len(visits) == 3

    def test_lista_vazia_sem_visitas(self, db):
        visits = run(db.get_recent_visits(10))
        assert visits == []

    def test_campos_presentes(self, db):
        run(db.log_visit_dedup("https://example.com/p", "Título"))
        v = run(db.get_recent_visits(1))[0]
        assert "title" in v
        assert "url" in v
        assert "created_at" in v


# ---------------------------------------------------------------------------
# get_top_visited_domains
# ---------------------------------------------------------------------------

class TestGetTopVisitedDomains:
    def test_conta_dominio_corretamente(self, db):
        for i in range(3):
            run(db.log_visit_dedup(f"https://example.com/page{i}", f"P{i}", window_minutes=0))
        run(db.log_visit_dedup("https://other.com/", "Other"))
        domains = run(db.get_top_visited_domains(5))
        dom_map = dict(domains)
        assert dom_map.get("example.com", 0) == 3
        assert dom_map.get("other.com", 0) == 1

    def test_ordena_por_frequencia(self, db):
        for i in range(4):
            run(db.log_visit_dedup(f"https://popular.com/{i}", f"P{i}", window_minutes=0))
        run(db.log_visit_dedup("https://rare.com/", "R"))
        domains = run(db.get_top_visited_domains(5))
        assert domains[0][0] == "popular.com"

    def test_lista_vazia_sem_visitas(self, db):
        domains = run(db.get_top_visited_domains(5))
        assert domains == []

    def test_remove_prefixo_www(self, db):
        run(db.log_visit_dedup("https://www.example.com/", "E"))
        domains = run(db.get_top_visited_domains(5))
        domain_names = [d for d, _ in domains]
        assert "example.com" in domain_names
        assert "www.example.com" not in domain_names
