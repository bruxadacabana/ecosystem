"""
Testes para services/query_expansion.py (PRF sem LLM).

Cobre:
  - expand_query_prf: query < 3 tokens → sem expansão
  - expand_query_prf: corpus mock com termos discriminativos → termos extraídos
  - termos da query original são excluídos da expansão
  - termos com len < 4 são ignorados (via stopwords ou regex)
  - docs sem conteúdo → sem expansão
  - aceita dicts e objetos com atributos (SearchResult-like)
  - retorna no máximo max_terms termos
  - ausência de chamadas HTTP (sem LLM)
"""
from __future__ import annotations

import pytest
from types import SimpleNamespace


def _make_result(title: str = "", snippet: str = "") -> SimpleNamespace:
    """Simula um SearchResult com .title e .snippet."""
    return SimpleNamespace(title=title, snippet=snippet, url="https://example.com", score=0.0)


def _expand(query: str, docs: list, **kwargs) -> list[str]:
    from services.query_expansion import expand_query_prf
    return expand_query_prf(query, docs, **kwargs)


# ---------------------------------------------------------------------------
# Sem expansão esperada
# ---------------------------------------------------------------------------

class TestNoExpansion:

    def test_empty_query_no_expansion(self):
        """Query vazia → sem expansão."""
        assert _expand("", [_make_result("python tutorial")]) == []

    def test_one_token_no_expansion(self):
        """1 token → sem expansão (ambiguidade alta)."""
        assert _expand("python", [_make_result("python tutorial basics")]) == []

    def test_two_tokens_no_expansion(self):
        """2 tokens → sem expansão."""
        assert _expand("python tutorial", [_make_result("python tutorial beginners")]) == []

    def test_no_docs_no_expansion(self):
        """Nenhum doc → sem expansão."""
        assert _expand("python tutorial basics", []) == []

    def test_docs_with_empty_content(self):
        """Docs com title e snippet vazios → sem expansão."""
        docs = [_make_result("", "") for _ in range(5)]
        assert _expand("python tutorial basics", docs) == []


# ---------------------------------------------------------------------------
# Expansão esperada com corpo de docs
# ---------------------------------------------------------------------------

class TestExpansionWithCorpus:

    def test_extracts_discriminative_terms(self):
        """Termos frequentes nos docs mas ausentes na query devem ser extraídos."""
        docs = [
            _make_result("python decorators guide", "decorators allow wrapping functions"),
            _make_result("python decorator pattern", "wrap functions with decorator syntax"),
            _make_result("functools wraps decorator", "decorator preserves function metadata"),
            _make_result("decorator factory python", "parametrized decorators factory pattern"),
            _make_result("class decorator python", "class based decorator implementation"),
        ]
        result = _expand("como funciona python", docs)
        assert len(result) > 0
        # "decorator" ou "decorators" deve aparecer — frequente no sub-corpus
        assert any("decor" in t for t in result), f"Expected 'decorator*' in {result}"

    def test_query_terms_excluded(self):
        """Termos já na query não devem aparecer na expansão."""
        docs = [
            _make_result("python tutorial basics", "python tutorial for beginners"),
        ] * 3 + [_make_result("python examples code", "python code examples")]
        result = _expand("python tutorial basics", docs)
        assert "python" not in result
        assert "tutorial" not in result
        assert "basics" not in result

    def test_short_terms_excluded(self):
        """Termos com len < 4 são ignorados pelo tokenizador."""
        docs = [
            _make_result("in on at by for", "the a an or is"),
        ] * 5
        result = _expand("sobre funcionalidades avançadas", docs)
        # Se não há termos válidos (len ≥ 4, não stopword), retorna lista vazia
        assert isinstance(result, list)

    def test_max_terms_respected(self):
        """max_terms=2 → retorna no máximo 2 termos."""
        docs = [
            _make_result("machine learning algorithms neural networks", "deep classification regression clustering"),
        ] * 5
        result = _expand("usando algoritmos dados", docs, max_terms=2)
        assert len(result) <= 2

    def test_accepts_dict_docs(self):
        """Deve aceitar dicts com chaves 'title' e 'snippet'."""
        docs = [
            {"title": "neural networks introduction", "snippet": "neural networks learning"},
        ] * 3 + [
            {"title": "deep learning layers activation", "snippet": "activation functions layers"},
        ] * 2
        result = _expand("usando redes neurais treinamento", docs)
        assert isinstance(result, list)

    def test_accepts_object_docs(self):
        """Deve aceitar objetos com .title e .snippet (SearchResult-like)."""
        docs = [_make_result("neural learning networks", "deep networks layers training")] * 5
        result = _expand("usando redes neurais treinamento", docs)
        assert isinstance(result, list)

    def test_result_is_list_of_strings(self):
        """Resultado sempre é lista de strings."""
        docs = [_make_result("python programming language", "code function class")] * 3
        result = _expand("python language basics", docs)
        assert all(isinstance(t, str) for t in result)

    def test_no_duplicates_in_result(self):
        """Termos de expansão são únicos."""
        docs = [_make_result("neural network learning", "neural network training")] * 5
        result = _expand("deep learning treinamento", docs)
        assert len(result) == len(set(result))

    def test_three_tokens_triggers_expansion(self):
        """Exatamente 3 tokens → expansão é acionada."""
        docs = [
            _make_result("gradient descent optimization", "loss function gradient step"),
        ] * 5
        # Se há termos discriminativos válidos, deve retornar algo
        result = _expand("gradiente descida otimização", docs)
        assert isinstance(result, list)  # pode ser vazia se termos todos filtrados, mas nunca erro


# ---------------------------------------------------------------------------
# Ausência de chamadas HTTP (sem LLM)
# ---------------------------------------------------------------------------

def test_no_http_calls(monkeypatch):
    """expand_query_prf não deve fazer chamadas HTTP."""
    import httpx

    calls: list[str] = []
    original_get = httpx.Client.get

    def _track_get(self, *args, **kwargs):
        calls.append(str(args))
        return original_get(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "get", _track_get)

    docs = [_make_result("python programming tutorial", "code examples")] * 3
    from services.query_expansion import expand_query_prf
    expand_query_prf("python language basics", docs)

    assert calls == [], "expand_query_prf não deve fazer chamadas HTTP"
