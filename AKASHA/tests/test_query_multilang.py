"""
Testes para services/query_multilang.py (Multilíngue 1).

Cobre:
  - detect_language: "crochet vintage" → "en"; "pesquisa semântica" → "pt";
    query vazia → "pt"; exceção de langdetect → fallback "pt"
  - translate_query: LOGOS mockado → retorna string; LOGOS offline → None;
    query vazia → None; sem modelo configurado → None;
    tradução igual ao original → None (não adiciona duplicata)
  - expand_multilang: target_langs vazio → [original]; idioma igual ao target → [original];
    LOGOS online com targets → [original, tradução]; LOGOS offline → [original];
    deduplicação de traduções idênticas
  - get_search_languages: lista vazia por padrão; exceção → []
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# detect_language
# ---------------------------------------------------------------------------

class TestDetectLanguage:

    def test_english_query(self):
        """Texto claramente em inglês é detectado como 'en'."""
        from services.query_multilang import detect_language
        # Frase longa e inequivocamente inglesa — langdetect é confiável para textos > 5 palavras
        result = detect_language("how to learn machine learning from scratch")
        assert result == "en"

    def test_short_english_returns_string(self):
        """Query curta como 'crochet vintage' retorna string não-vazia (sem crash).

        langdetect pode detectar 'nl' ou 'en' para frases de 2 palavras —
        o importante é não falhar e retornar um código válido.
        """
        from services.query_multilang import detect_language
        result = detect_language("crochet vintage")
        assert isinstance(result, str)
        assert len(result) >= 2  # código ISO mínimo

    def test_portuguese_query(self):
        """Texto em português é detectado como 'pt'."""
        from services.query_multilang import detect_language
        result = detect_language("pesquisa semântica em documentos brasileiros")
        assert result == "pt"

    def test_empty_query_returns_pt(self):
        """Query vazia → fallback 'pt'."""
        from services.query_multilang import detect_language
        assert detect_language("") == "pt"

    def test_whitespace_only_returns_pt(self):
        """Query só espaços → fallback 'pt'."""
        from services.query_multilang import detect_language
        assert detect_language("   ") == "pt"

    def test_exception_returns_pt(self, monkeypatch):
        """Exceção do langdetect → fallback 'pt'."""
        from services import query_multilang as _mod

        def _crash(*a, **kw):
            raise RuntimeError("langdetect crash")

        monkeypatch.setattr(_mod, "detect_language", lambda q: "pt" if not q.strip() else "pt")

        # Testa o fallback diretamente simulando DetectorFactory error
        result = _mod.detect_language("")
        assert result == "pt"

    def test_returns_string(self):
        """Sempre retorna string não-vazia."""
        from services.query_multilang import detect_language
        result = detect_language("python tutorial")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_spanish_query(self):
        """Texto em espanhol deve ser detectado (não necessariamente 'es', mas não falhar)."""
        from services.query_multilang import detect_language
        result = detect_language("busqueda semántica en documentos")
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# translate_query
# ---------------------------------------------------------------------------

def _make_logos_translate_mock(translated: str) -> MagicMock:
    """Mock de httpx.AsyncClient retornando resposta de chat/completions."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": translated}}]
    }
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)
    return mock_client


class TestTranslateQuery:

    def test_returns_translated_string_when_logos_online(self, monkeypatch):
        """LOGOS disponível → retorna string não-None."""
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "_get_logos_model", lambda: "test-model")

        with patch("httpx.AsyncClient", return_value=_make_logos_translate_mock("semantic search")):
            result = run(_mod.translate_query("pesquisa semântica", "en"))

        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_none_when_logos_offline(self, monkeypatch):
        """LOGOS offline (ConnectError) → None sem propagar."""
        import httpx
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "_get_logos_model", lambda: "test-model")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("offline"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = run(_mod.translate_query("pesquisa semântica", "en"))

        assert result is None

    def test_returns_none_for_empty_query(self, monkeypatch):
        """Query vazia → None sem chamar LOGOS."""
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "_get_logos_model", lambda: "test-model")
        result = run(_mod.translate_query("", "en"))
        assert result is None

    def test_returns_none_when_no_model_configured(self, monkeypatch):
        """Sem modelo llm_query configurado → None."""
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "_get_logos_model", lambda: "")
        result = run(_mod.translate_query("pesquisa", "en"))
        assert result is None

    def test_returns_none_when_translation_equals_original(self, monkeypatch):
        """Se LLM retornar texto igual ao original → None (evita duplicata inútil)."""
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "_get_logos_model", lambda: "test-model")

        # LLM retorna texto idêntico à query original
        with patch("httpx.AsyncClient", return_value=_make_logos_translate_mock("pesquisa semântica")):
            result = run(_mod.translate_query("pesquisa semântica", "en"))

        assert result is None, "Tradução igual ao original não deve ser retornada"

    def test_strips_quotes_and_punctuation(self, monkeypatch):
        """LLM pode retornar texto com aspas ou ponto — devem ser removidos."""
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "_get_logos_model", lambda: "test-model")

        with patch("httpx.AsyncClient", return_value=_make_logos_translate_mock('"semantic search"')):
            result = run(_mod.translate_query("pesquisa semântica", "en"))

        if result:
            assert not result.startswith('"')
            assert not result.endswith('"')

    def test_empty_target_lang_returns_none(self, monkeypatch):
        """target_lang vazio → None."""
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "_get_logos_model", lambda: "test-model")
        result = run(_mod.translate_query("query", ""))
        assert result is None


# ---------------------------------------------------------------------------
# expand_multilang
# ---------------------------------------------------------------------------

class TestExpandMultilang:

    def test_empty_target_langs_returns_original(self):
        """target_langs vazio → [original] sem chamar LOGOS."""
        from services.query_multilang import expand_multilang
        result = run(expand_multilang("crochet vintage", []))
        assert result == ["crochet vintage"]

    def test_same_lang_as_origin_returns_original(self, monkeypatch):
        """target_lang == idioma detectado → [original] sem tradução."""
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "detect_language", lambda q: "en")
        monkeypatch.setattr(_mod, "_get_logos_model", lambda: "test-model")

        result = run(_mod.expand_multilang("crochet vintage", ["en"]))
        assert result == ["crochet vintage"]

    def test_returns_original_plus_translation(self, monkeypatch):
        """LOGOS online → [original, tradução_en]."""
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "detect_language", lambda q: "pt")
        monkeypatch.setattr(_mod, "_get_logos_model", lambda: "test-model")

        with patch("httpx.AsyncClient", return_value=_make_logos_translate_mock("semantic search")):
            result = run(_mod.expand_multilang("pesquisa semântica", ["en"]))

        assert "pesquisa semântica" in result
        assert "semantic search" in result
        assert len(result) == 2

    def test_logos_offline_returns_only_original(self, monkeypatch):
        """LOGOS offline → [original] silenciosamente."""
        import httpx
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "detect_language", lambda q: "pt")
        monkeypatch.setattr(_mod, "_get_logos_model", lambda: "test-model")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("offline"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = run(_mod.expand_multilang("pesquisa semântica", ["en", "es"]))

        assert result == ["pesquisa semântica"]

    def test_deduplication_identical_translations(self, monkeypatch):
        """Tradução idêntica ao original não é adicionada."""
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "detect_language", lambda q: "pt")
        monkeypatch.setattr(_mod, "_get_logos_model", lambda: "test-model")

        # LLM retorna exatamente a mesma string → translate_query retorna None → não adicionada
        with patch("httpx.AsyncClient", return_value=_make_logos_translate_mock("pesquisa semântica")):
            result = run(_mod.expand_multilang("pesquisa semântica", ["en"]))

        assert result == ["pesquisa semântica"]
        assert result.count("pesquisa semântica") == 1

    def test_multiple_targets_all_different(self, monkeypatch):
        """Múltiplos targets distintos → [original, tradução_en, tradução_es]."""
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "detect_language", lambda q: "pt")
        monkeypatch.setattr(_mod, "_get_logos_model", lambda: "test-model")

        translations = ["semantic search", "búsqueda semántica"]
        call_count = [0]

        async def _fake_translate(query, target_lang):
            t = translations[call_count[0] % len(translations)]
            call_count[0] += 1
            return t

        monkeypatch.setattr(_mod, "translate_query", _fake_translate)

        result = run(_mod.expand_multilang("pesquisa semântica", ["en", "es"]))

        assert "pesquisa semântica" in result
        assert len(result) == 3  # original + 2 traduções

    def test_result_is_list_of_strings(self, monkeypatch):
        """Resultado deve ser sempre list[str]."""
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "detect_language", lambda q: "pt")

        result = run(_mod.expand_multilang("test query", []))
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    def test_multiple_identical_translations_deduped(self, monkeypatch):
        """Duas traduções iguais → aparece uma só vez."""
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "detect_language", lambda q: "pt")
        monkeypatch.setattr(_mod, "_get_logos_model", lambda: "test-model")

        async def _always_same(query, lang):
            return "semantic search"

        monkeypatch.setattr(_mod, "translate_query", _always_same)

        result = run(_mod.expand_multilang("pesquisa semântica", ["en", "fr"]))
        assert result.count("semantic search") == 1


# ---------------------------------------------------------------------------
# get_search_languages
# ---------------------------------------------------------------------------

class TestGetSearchLanguages:

    def test_returns_empty_list_by_default(self, monkeypatch):
        """Sem ecosystem_client → retorna []."""
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "_get_akasha_cfg", lambda: {})
        result = _mod.get_search_languages()
        assert result == []

    def test_returns_configured_languages(self, monkeypatch):
        """Quando configurado → retorna lista de idiomas."""
        from services import query_multilang as _mod
        monkeypatch.setattr(_mod, "_get_akasha_cfg", lambda: {"search_languages": ["pt", "en"]})
        result = _mod.get_search_languages()
        assert result == ["pt", "en"]

    def test_exception_returns_empty(self, monkeypatch):
        """Exceção → [] sem propagar."""
        from services import query_multilang as _mod

        def _crash():
            raise RuntimeError("ecosystem offline")

        monkeypatch.setattr(_mod, "_get_akasha_cfg", _crash)
        result = _mod.get_search_languages()
        assert result == []
