"""
Testes para _apply_wiki_citation_boost em routers/search.py.

Casos cobertos:
  - resultado cujo domínio está nas citações → boost 1.3 aplicado e wiki_cited=True
  - resultado sem citação → score inalterado, wiki_cited=False
  - cited_domains vazio → nenhum boost, lista inalterada
  - lista vazia → retorna lista vazia sem erro
  - re-ordenação: resultado citado sobe quando boost supera desvantagem posicional
  - www. prefixo é ignorado no match
  - sem nenhum match → ordem preservada
"""
from __future__ import annotations
import pytest


def _make(url: str, source: str = "WEB"):
    from services.web_search import SearchResult
    return SearchResult(title="T", url=url, snippet="s", source=source)


def _boost(results, cited_domains):
    from routers.search import _apply_wiki_citation_boost
    return _apply_wiki_citation_boost(results, cited_domains)


# ---------------------------------------------------------------------------
# Caso 1: resultado citado recebe boost e flag
# ---------------------------------------------------------------------------
def test_cited_result_gets_flag():
    r1 = _make("https://example.com/page")
    r2 = _make("https://other.org/page")
    out = _boost([r1, r2], {"example.com"})
    cited_out = [r for r in out if r.wiki_cited]
    assert len(cited_out) == 1
    assert cited_out[0].url == "https://example.com/page"


# ---------------------------------------------------------------------------
# Caso 2: resultado sem citação → wiki_cited permanece False
# ---------------------------------------------------------------------------
def test_non_cited_result_flag_false():
    r1 = _make("https://example.com/page")
    r2 = _make("https://other.org/page")
    out = _boost([r1, r2], {"example.com"})
    non_cited = [r for r in out if not r.wiki_cited]
    assert len(non_cited) == 1
    assert non_cited[0].url == "https://other.org/page"


# ---------------------------------------------------------------------------
# Caso 3: cited_domains vazio → lista inalterada, nenhum boost
# ---------------------------------------------------------------------------
def test_empty_cited_domains_no_boost():
    r1 = _make("https://example.com/page")
    r2 = _make("https://other.org/page")
    out = _boost([r1, r2], set())
    assert not any(r.wiki_cited for r in out)
    assert out[0].url == r1.url
    assert out[1].url == r2.url


# ---------------------------------------------------------------------------
# Caso 4: lista vazia → retorna lista vazia sem erro
# ---------------------------------------------------------------------------
def test_empty_results_returns_empty():
    out = _boost([], {"example.com"})
    assert out == []


# ---------------------------------------------------------------------------
# Caso 5: resultado citado sobe quando boost supera gap posicional
#   5 itens: citado na posição 4 (índice 4, última)
#   score sem boost: 1/5 = 0.200
#   score com boost: 1/5 * 1.3 = 0.260 > penúltimo 1/4 * 1.0 = 0.250 → sobe
# ---------------------------------------------------------------------------
def test_cited_result_moves_up():
    r1 = _make("https://a.com/")
    r2 = _make("https://b.com/")
    r3 = _make("https://c.com/")
    r4 = _make("https://d.com/")
    r5 = _make("https://wiki-cited.org/")  # posição 4 (última)
    out = _boost([r1, r2, r3, r4, r5], {"wiki-cited.org"})
    # Com boost, r5 sobe acima de r4 (0.260 > 0.250)
    positions = {r.url: i for i, r in enumerate(out)}
    assert positions["https://wiki-cited.org/"] < positions["https://d.com/"]
    assert out[positions["https://wiki-cited.org/"]].wiki_cited is True


# ---------------------------------------------------------------------------
# Caso 6: www. é removido no match de domínio
# ---------------------------------------------------------------------------
def test_www_prefix_stripped():
    r1 = _make("https://www.example.com/page")
    out = _boost([r1], {"example.com"})
    assert out[0].wiki_cited is True


# ---------------------------------------------------------------------------
# Caso 7: sem nenhum match → ordem preservada e nenhum wiki_cited
# ---------------------------------------------------------------------------
def test_no_matches_preserves_order():
    r1 = _make("https://a.com/")
    r2 = _make("https://b.com/")
    r3 = _make("https://c.com/")
    out = _boost([r1, r2, r3], {"totally-different.org"})
    assert [r.url for r in out] == ["https://a.com/", "https://b.com/", "https://c.com/"]
    assert not any(r.wiki_cited for r in out)
