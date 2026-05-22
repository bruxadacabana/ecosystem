"""
Testes unitários para AKASHA/services/query_understanding.py.

Cobre funções puras sem I/O:
  - needs_rewrite: detecta queries curtas ou com anáforas
  - classify_intent_lexical: regras léxicas sem LLM (7 tipos de intenção)
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


# ---------------------------------------------------------------------------
# classify_intent_lexical — AKASHA ferramenta, sem LLM
# ---------------------------------------------------------------------------

class TestClassifyIntentLexical:
    """Regras léxicas — 7 tipos de intenção, zero chamada a Ollama."""

    def _c(self, q):
        from services.query_understanding import classify_intent_lexical
        return classify_intent_lexical(q)

    # Regra 1 — navigational

    def test_navigational_https(self):
        assert self._c("https://github.com/anthropics") == "navigational"

    def test_navigational_www(self):
        assert self._c("www.python.org") == "navigational"

    def test_navigational_domain_tld(self):
        assert self._c("github.com") == "navigational"

    def test_navigational_two_token_domain(self):
        assert self._c("python.org docs") == "navigational"

    def test_not_navigational_three_tokens(self):
        result = self._c("python.org official documentation")
        assert result != "navigational"

    # Regra 2 — informational

    def test_informational_o_que_e(self):
        assert self._c("o que é machine learning") == "informational"

    def test_informational_como_funciona(self):
        assert self._c("como funciona um compilador") == "informational"

    def test_informational_what_is(self):
        assert self._c("what is recursion") == "informational"

    def test_informational_how_to(self):
        assert self._c("how to install python") == "informational"

    def test_informational_por_que(self):
        assert self._c("por que o céu é azul") == "informational"

    def test_informational_explain(self):
        assert self._c("explain gradient descent") == "informational"

    # Regra 3 — visual

    def test_visual_foto(self):
        assert self._c("foto de gato") == "visual"

    def test_visual_logo(self):
        assert self._c("python logo") == "visual"

    def test_visual_image(self):
        assert self._c("linux penguin image") == "visual"

    # Regra 4 — weather

    def test_weather_tempo(self):
        assert self._c("tempo em Lisboa") == "weather"

    def test_weather_clima(self):
        assert self._c("clima amanhã São Paulo") == "weather"

    def test_weather_forecast(self):
        assert self._c("weather forecast london") == "weather"

    # Regra 5 — translation

    def test_translation_traduzir(self):
        assert self._c("traduzir hello para português") == "translation"

    def test_translation_em_ingles(self):
        assert self._c("saudade em inglês") == "translation"

    def test_translation_como_se_diz(self):
        assert self._c("como se diz obrigado em francês") == "translation"

    def test_translation_translate(self):
        assert self._c("translate good morning to portuguese") == "translation"

    # Regra 6 — video

    def test_video_vídeo(self):
        assert self._c("vídeo aula python iniciantes") == "video"

    def test_video_watch(self):
        assert self._c("watch interstellar online") == "video"

    def test_video_assistir(self):
        assert self._c("assistir serie stranger things") == "video"

    def test_video_youtube(self):
        assert self._c("youtube tutorial docker") == "video"

    # Regra 7 — default por tamanho

    def test_default_short_informational(self):
        assert self._c("rust concurrency") == "informational"

    def test_default_long_exploratory(self):
        assert self._c("best practices async python web services") == "exploratory"

    def test_default_empty(self):
        assert self._c("") == "exploratory"

    def test_default_single_token(self):
        assert self._c("python") == "informational"

    # Sem LLM — nenhuma chamada HTTP

    def test_no_http_calls(self, monkeypatch):
        import httpx
        calls: list[str] = []

        original_post = httpx.AsyncClient.post

        async def _track(*args, **kwargs):
            calls.append(str(args))
            return await original_post(*args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "post", _track)

        from services.query_understanding import classify_intent_lexical
        classify_intent_lexical("como funciona recursão")

        assert calls == [], "classify_intent_lexical não deve fazer chamadas HTTP"
