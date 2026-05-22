"""
Testes unitários para o conjunto _STOPWORDS do knowledge_worker.

Verifica que palavras genéricas que contaminavam o perfil de interesses
estão presentes no conjunto e que termos legítimos não estão.
"""
from __future__ import annotations

import pytest


class TestStopwords:
    @pytest.fixture(autouse=True)
    def _load(self):
        from services.knowledge_worker import _STOPWORDS
        self.sw = _STOPWORDS

    # ── Palavras que DEVEM estar nas stopwords ──

    def test_contains_novo(self):
        assert "novo" in self.sw

    def test_contains_observacao(self):
        assert "observação" in self.sw

    def test_contains_relevantes(self):
        assert "relevantes" in self.sw

    def test_contains_dominio(self):
        assert "domínio" in self.sw

    def test_contains_algo(self):
        assert "algo" in self.sw

    def test_contains_contexto(self):
        assert "contexto" in self.sw

    def test_contains_portuguese_prepositions(self):
        for word in ("de", "da", "do", "em", "para", "com", "sobre"):
            assert word in self.sw, f"'{word}' deveria ser stopword"

    def test_contains_english_basics(self):
        for word in ("the", "and", "or", "is", "to", "in"):
            assert word in self.sw, f"'{word}' deveria ser stopword"

    def test_contains_data_and_model(self):
        assert "data" in self.sw
        assert "model" in self.sw

    # ── Termos técnicos que NÃO devem estar nas stopwords ──

    def test_does_not_contain_python(self):
        assert "python" not in self.sw

    def test_does_not_contain_machine_learning(self):
        assert "machine" not in self.sw

    def test_does_not_contain_rust(self):
        assert "rust" not in self.sw

    def test_does_not_contain_proper_nouns(self):
        for term in ("chromadb", "sqlite", "pytorch", "fastapi"):
            assert term not in self.sw, f"'{term}' não deveria ser stopword"

    def test_is_frozenset(self):
        assert isinstance(self.sw, frozenset)

    def test_all_lowercase(self):
        for w in self.sw:
            assert w == w.lower() or any(
                c > '\x7f' for c in w
            ), f"stopword não normalizada: '{w}'"
