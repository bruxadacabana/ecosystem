"""
Testes unitários para AKASHA/services/query_understanding.py.

Cobre funções puras sem I/O:
  - needs_rewrite: detecta queries curtas ou com anáforas
"""
from __future__ import annotations

import pytest


class TestNeedsRewrite:
    """needs_rewrite retorna True para queries curtas (< 3 tokens) ou com anáforas PT/EN."""

    def _check(self, q):
        from services.query_understanding import needs_rewrite
        return needs_rewrite(q)

    # ── Queries que precisam de reescrita ──

    def test_single_word_needs_rewrite(self):
        assert self._check("isso")

    def test_two_words_needs_rewrite(self):
        assert self._check("isso aqui")

    def test_portuguese_anaphor_esse(self):
        assert self._check("o que é esse assunto que você mencionou")

    def test_portuguese_anaphor_isso(self):
        assert self._check("explique melhor isso que foi dito")

    def test_portuguese_anaphor_ela(self):
        assert self._check("quem é ela que escreveu o livro")

    def test_english_anaphor_this(self):
        assert self._check("what does this refer to in physics")

    def test_english_anaphor_it(self):
        assert self._check("can you explain it in simpler terms")

    def test_english_anaphor_they(self):
        assert self._check("why do they say that about history")

    def test_case_insensitive_anaphor(self):
        assert self._check("ISSO não faz sentido no contexto")

    # ── Queries que NÃO precisam de reescrita ──

    def test_specific_query_no_rewrite(self):
        assert not self._check("aprendizado de máquina federado privacidade")

    def test_three_tokens_no_rewrite(self):
        assert not self._check("linguística computacional semântica")

    def test_long_query_no_anaphor_no_rewrite(self):
        assert not self._check(
            "quais são as principais técnicas de compressão de redes neurais"
        )

    def test_english_specific_query_no_rewrite(self):
        assert not self._check("federated learning privacy preservation techniques")

    def test_empty_string_needs_rewrite(self):
        # Menos de 3 tokens
        assert self._check("")

    def test_three_word_query_with_anaphor(self):
        # Tem anáfora "esse" mesmo com 4 tokens
        assert self._check("o que é esse")
