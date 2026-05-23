"""
Testes para _build_results_by_source em routers/search.py.

Cobre:
  - 3 fontes com resultados → dict com 3 chaves e contagens corretas
  - fonte sem resultados → chave presente com lista vazia (não KeyError)
  - todas as fontes com resultados → agrupamento correto por categoria
  - chaves fixas presentes mesmo quando todas as listas estão vazias
"""
from __future__ import annotations
import pytest


def _make(url: str, source: str = "WEB"):
    from services.web_search import SearchResult
    return SearchResult(title="T", url=url, snippet="s", source=source)


def _build(**kwargs):
    from routers.search import _build_results_by_source
    defaults = {
        "local_results":        [],
        "watch_later_results":  [],
        "kosmos_results":       [],
        "site_results":         [],
        "web_results":          [],
        "fav_results":          [],
        "paper_results":        [],
    }
    defaults.update(kwargs)
    return _build_results_by_source(**defaults)


# ---------------------------------------------------------------------------
# Caso 1: 3 fontes com resultados → dict com 3 chaves corretas
# ---------------------------------------------------------------------------
def test_three_sources_all_present():
    r_local = _make("file:///doc.pdf", "ECO")
    r_site  = _make("https://site.com/", "SITES")
    r_web   = _make("https://web.com/", "WEB")

    result = _build(local_results=[r_local], site_results=[r_site], web_results=[r_web])

    assert set(result.keys()) == {"Pessoal", "Biblioteca", "Web"}
    assert r_local in result["Pessoal"]
    assert r_site  in result["Biblioteca"]
    assert r_web   in result["Web"]


# ---------------------------------------------------------------------------
# Caso 2: fonte sem resultados → chave presente com lista vazia
# ---------------------------------------------------------------------------
def test_empty_source_key_still_present():
    r_web = _make("https://web.com/", "WEB")
    result = _build(web_results=[r_web])

    assert "Pessoal"    in result
    assert "Biblioteca" in result
    assert "Web"        in result
    assert result["Pessoal"]    == []
    assert result["Biblioteca"] == []
    assert len(result["Web"])   == 1


# ---------------------------------------------------------------------------
# Caso 3: todas as listas vazias → 3 chaves com listas vazias
# ---------------------------------------------------------------------------
def test_all_empty_returns_three_empty_keys():
    result = _build()
    assert set(result.keys()) == {"Pessoal", "Biblioteca", "Web"}
    assert all(v == [] for v in result.values())


# ---------------------------------------------------------------------------
# Caso 4: watch_later e kosmos vão para "Pessoal"
# ---------------------------------------------------------------------------
def test_watch_later_and_kosmos_grouped_as_pessoal():
    r_wl     = _make("https://watch.com/", "DEPOIS")
    r_kosmos = _make("https://kosmos.com/", "KOSMOS")
    result = _build(watch_later_results=[r_wl], kosmos_results=[r_kosmos])

    assert r_wl     in result["Pessoal"]
    assert r_kosmos in result["Pessoal"]
    assert result["Biblioteca"] == []
    assert result["Web"]        == []


# ---------------------------------------------------------------------------
# Caso 5: fav_results e paper_results vão para "Web"
# ---------------------------------------------------------------------------
def test_fav_and_papers_grouped_as_web():
    r_fav   = _make("https://fav.com/", "WEB")
    r_paper = _make("https://arxiv.org/abs/123", "PAPERS")
    result = _build(fav_results=[r_fav], paper_results=[r_paper])

    assert r_fav   in result["Web"]
    assert r_paper in result["Web"]
    assert result["Pessoal"]    == []
    assert result["Biblioteca"] == []


# ---------------------------------------------------------------------------
# Caso 6: contagem total correta com múltiplos resultados por fonte
# ---------------------------------------------------------------------------
def test_counts_with_multiple_results():
    locals_  = [_make(f"file:///doc{i}.pdf") for i in range(3)]
    sites_   = [_make(f"https://site{i}.com/") for i in range(2)]
    webs_    = [_make(f"https://web{i}.com/") for i in range(4)]

    result = _build(local_results=locals_, site_results=sites_, web_results=webs_)

    assert len(result["Pessoal"])    == 3
    assert len(result["Biblioteca"]) == 2
    assert len(result["Web"])        == 4
