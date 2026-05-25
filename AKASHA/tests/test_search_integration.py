"""
Testes de integração: fluxo completo de busca local.
Banco SQLite temporário em disco (tempdir), sem servidor AKASHA ativo.

Cobre:
  1. Resultado vazio — banco sem documentos indexados
  2. Caracteres especiais — queries com operadores FTS5 não devem explodir
  3. Paginação — offset > total de resultados retorna []
  4. Boost conflitante — pagerank e freshness com sinais opostos não descartam documentos
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Helpers de banco
# ---------------------------------------------------------------------------

def _create_minimal_db(db_path: Path) -> None:
    """Cria tabelas mínimas para que search_local funcione sem o app completo."""
    con = sqlite3.connect(str(db_path))
    con.executescript("""
        CREATE VIRTUAL TABLE local_fts USING fts5(
            path    UNINDEXED,
            title,
            body,
            source  UNINDEXED,
            tokenize = 'unicode61 remove_diacritics 2'
        );
        INSERT INTO local_fts(local_fts, rank)
            VALUES('rank', 'bm25(0, 10.0, 1.0, 0)');

        CREATE TABLE local_index_meta (
            path    TEXT    PRIMARY KEY,
            source  TEXT    NOT NULL,
            mtime   TEXT    NOT NULL,
            lang    TEXT    NOT NULL DEFAULT '',
            deleted INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE highlights (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            url        TEXT    NOT NULL,
            exact      TEXT    NOT NULL,
            prefix     TEXT    NOT NULL DEFAULT '',
            suffix     TEXT    NOT NULL DEFAULT '',
            note       TEXT    NOT NULL DEFAULT '',
            created_at TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE VIRTUAL TABLE highlights_fts USING fts5(
            exact,
            note,
            tokenize = 'unicode61 remove_diacritics 2'
        );
        CREATE INDEX idx_highlights_url ON highlights(url);

        CREATE TABLE doc_accesses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT    NOT NULL,
            accessed_at TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX idx_doc_accesses_url ON doc_accesses(url);

        CREATE TABLE page_rank (
            url        TEXT    PRIMARY KEY,
            score      REAL    NOT NULL DEFAULT 1.0,
            updated_at INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE crawl_pages (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id          INTEGER,
            url              TEXT    NOT NULL UNIQUE,
            title            TEXT    DEFAULT '',
            content_md       TEXT    DEFAULT '',
            http_status      INTEGER DEFAULT 0,
            crawled_at       TEXT    DEFAULT (datetime('now')),
            last_modified_at TEXT    NOT NULL DEFAULT '',
            last_checked_at  TEXT    NOT NULL DEFAULT ''
        );

        CREATE TABLE domain_boosts (
            domain     TEXT    PRIMARY KEY,
            boost      REAL    NOT NULL DEFAULT 1.0,
            updated_at INTEGER NOT NULL DEFAULT 0
        );
    """)
    con.commit()
    con.close()


def _insert_doc(
    db_path: Path,
    path_str: str,
    title: str,
    body: str,
    source: str = "KOSMOS",
    mtime: str | None = None,
) -> None:
    """Insere documento no índice FTS5 e em local_index_meta."""
    if mtime is None:
        mtime = str(time.time())
    con = sqlite3.connect(str(db_path))
    con.execute(
        "INSERT INTO local_fts (path, title, body, source) VALUES (?, ?, ?, ?)",
        (path_str, title, body, source),
    )
    con.execute(
        "INSERT INTO local_index_meta (path, source, mtime) VALUES (?, ?, ?)",
        (path_str, source, mtime),
    )
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_env(tmp_path, monkeypatch):
    """Banco temporário com schema mínimo; patcha DB_PATH em todos os módulos que o usam."""
    db_file = tmp_path / "akasha.db"
    _create_minimal_db(db_file)

    import services.local_search as ls
    import database
    import services.freshness as freshness

    monkeypatch.setattr(ls, "DB_PATH", db_file)
    monkeypatch.setattr(database, "DB_PATH", db_file)
    monkeypatch.setattr(freshness, "DB_PATH", db_file)
    monkeypatch.setattr(ls, "_inference_available", False)   # sem LLM
    monkeypatch.setattr(ls, "VECTOR_SEARCH_ENABLED", False)  # sem sqlite-vec

    return db_file


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

class TestEmptyDatabase:
    def test_empty_db_returns_no_results(self, db_env):
        """Sem documentos indexados, search_local retorna []."""
        from services.local_search import search_local
        results = asyncio.run(search_local("python", expand=False))
        assert results == []

    def test_empty_db_any_query_returns_empty(self, db_env):
        """Qualquer query em banco vazio deve retornar []."""
        from services.local_search import search_local
        for q in ("machine learning", "2024", '"frase exata"'):
            results = asyncio.run(search_local(q, expand=False))
            assert results == [], f"Esperava [] para query {q!r}"


class TestSpecialCharacters:
    def test_fts_operators_do_not_raise(self, db_env):
        """Queries com operadores FTS5, Unicode e pontuação não devem lançar exceção."""
        from services.local_search import search_local
        queries = [
            "(python tutorial)",
            '"machine learning"',
            "query:field",
            "foo^2",
            "a AND b OR NOT c",
            "über café résumé",
            "中文搜索",
            "   ",
            "!@#$%",
        ]
        for q in queries:
            result = asyncio.run(search_local(q, expand=False))
            assert isinstance(result, list), (
                f"search_local deve retornar lista para qualquer query; falhou com {q!r}"
            )

    def test_parentheses_in_query_still_finds_document(self, db_env):
        """Documento indexado deve ser encontrado mesmo com parênteses na query."""
        from services.local_search import search_local
        doc = str(db_env.parent / "doc.md")
        _insert_doc(db_env, doc, "Python Basics", "aprenda python do zero")

        results = asyncio.run(search_local("(python)", expand=False))
        assert any("python" in r.title.lower() for r in results), (
            "Documento com 'python' no título deve aparecer mesmo com query '(python)'"
        )


class TestPagination:
    def test_offset_beyond_total_returns_empty_slice(self, db_env):
        """Simula paginação do router: results[offset:offset+limit] quando offset > total.

        O router fatia a lista retornada por search_local. Quando o offset passa do
        final da lista, Python retorna [] silenciosamente — sem IndexError.
        """
        from services.local_search import search_local
        for i in range(3):
            path = str(db_env.parent / f"doc{i}.md")
            _insert_doc(db_env, path, f"Tutorial Python {i}", f"conteúdo sobre python parte {i}")

        results = asyncio.run(search_local("python", expand=False))
        assert len(results) >= 3, "Os 3 documentos devem aparecer nos resultados"

        # Página inexistente: offset além do total
        offset = len(results) + 10
        page = results[offset:offset + 20]
        assert page == []

    def test_max_results_limits_output(self, db_env):
        """max_results=1 retorna no máximo 1 resultado, mesmo com vários documentos."""
        from services.local_search import search_local
        for i in range(5):
            path = str(db_env.parent / f"doc{i}.md")
            _insert_doc(db_env, path, f"Python Tutorial {i}", f"python guia {i}")

        results = asyncio.run(search_local("python", max_results=1, expand=False))
        assert len(results) <= 1

    def test_max_results_zero_returns_empty(self, db_env):
        """max_results=0 passa LIMIT 0 para o FTS5 e retorna lista vazia."""
        from services.local_search import search_local
        path = str(db_env.parent / "doc.md")
        _insert_doc(db_env, path, "Python Guide", "python guia completo")

        results = asyncio.run(search_local("python", max_results=0, expand=False))
        assert results == []


class TestConflictingBoosts:
    def test_conflicting_pagerank_and_freshness_preserves_all_results(self, db_env):
        """Quando pagerank e freshness apontam em direções opostas, nenhum
        documento deve ser descartado do resultado final.

        Setup:
          doc_a — mtime de 1 ano atrás (baixo frescor) + pagerank 2.0 (alto)
          doc_b — mtime agora          (alto frescor)  + pagerank 0.5 (baixo)
        """
        from services.local_search import search_local

        now = time.time()
        path_a = str(db_env.parent / "doc_a.md")
        path_b = str(db_env.parent / "doc_b.md")

        _insert_doc(db_env, path_a, "Python recente", "conteúdo python recente",
                    mtime=str(now - 365 * 86400))
        _insert_doc(db_env, path_b, "Python recente", "conteúdo python recente",
                    mtime=str(now))

        url_a = Path(path_a).as_uri()
        url_b = Path(path_b).as_uri()

        con = sqlite3.connect(str(db_env))
        con.execute("INSERT INTO page_rank (url, score) VALUES (?, ?)", (url_a, 2.0))
        con.execute("INSERT INTO page_rank (url, score) VALUES (?, ?)", (url_b, 0.5))
        con.commit()
        con.close()

        # "recente" é termo temporal → ativa apply_freshness_rerank
        results = asyncio.run(search_local("python recente", expand=False))

        urls_found = {r.url for r in results}
        assert url_a in urls_found, "doc_a não deve ser descartado pelo freshness"
        assert url_b in urls_found, "doc_b não deve ser descartado pelo pagerank"

    def test_conflicting_boosts_result_is_deterministic(self, db_env):
        """Duas chamadas consecutivas com os mesmos dados devem retornar a mesma ordem."""
        from services.local_search import search_local

        now = time.time()
        path_a = str(db_env.parent / "doc_a.md")
        path_b = str(db_env.parent / "doc_b.md")

        _insert_doc(db_env, path_a, "Python recente", "conteúdo python recente",
                    mtime=str(now - 365 * 86400))
        _insert_doc(db_env, path_b, "Python recente", "conteúdo python recente",
                    mtime=str(now))

        url_a = Path(path_a).as_uri()
        url_b = Path(path_b).as_uri()

        con = sqlite3.connect(str(db_env))
        con.execute("INSERT INTO page_rank (url, score) VALUES (?, ?)", (url_a, 2.0))
        con.execute("INSERT INTO page_rank (url, score) VALUES (?, ?)", (url_b, 0.5))
        con.commit()
        con.close()

        first  = asyncio.run(search_local("python recente", expand=False))
        second = asyncio.run(search_local("python recente", expand=False))

        assert [r.url for r in first] == [r.url for r in second], (
            "Ordem dos resultados deve ser determinística entre chamadas idênticas"
        )

    def test_pagerank_dominates_over_freshness_at_default_weights(self, db_env):
        """Com os pesos padrão (freshness=0.3, original=0.7), o sinal de pagerank
        deve dominar sobre o freshness quando a diferença de posição é de apenas 1.

        Verifica que o documento com pagerank maior (doc_a) precede doc_b na saída
        final, mesmo que doc_b seja mais recente (freshness preferiria doc_b).
        """
        from services.local_search import search_local

        now = time.time()
        path_a = str(db_env.parent / "doc_a.md")
        path_b = str(db_env.parent / "doc_b.md")

        # doc_a: velho, pagerank alto → pipeline deve colocar doc_a na frente
        # doc_b: novo,  pagerank baixo
        _insert_doc(db_env, path_a, "Python recente", "conteúdo python recente",
                    mtime=str(now - 365 * 86400))
        _insert_doc(db_env, path_b, "Python recente", "conteúdo python recente",
                    mtime=str(now))

        url_a = Path(path_a).as_uri()
        url_b = Path(path_b).as_uri()

        con = sqlite3.connect(str(db_env))
        con.execute("INSERT INTO page_rank (url, score) VALUES (?, ?)", (url_a, 2.0))
        con.execute("INSERT INTO page_rank (url, score) VALUES (?, ?)", (url_b, 0.5))
        con.commit()
        con.close()

        results = asyncio.run(search_local("python recente", expand=False))
        assert len(results) >= 2
        urls = [r.url for r in results]

        pos_a = urls.index(url_a)
        pos_b = urls.index(url_b)
        assert pos_a < pos_b, (
            f"doc_a (pagerank=2.0) deve preceder doc_b (pagerank=0.5) com pesos padrão; "
            f"pos_a={pos_a}, pos_b={pos_b}"
        )
