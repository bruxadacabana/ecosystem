"""
Testes unitários para Hermes/services/recipe_extractor.py.

Cobre apenas funções puras sem I/O, rede ou modelo de ML:
  - _infer_platform: detecta plataforma a partir da URL
  - _extract_json: extrai dict de strings com/sem bloco de código
  - _clean_vtt: remove timestamps, tags HTML e linhas duplicadas
  - _slugify: gera slug a partir de texto
"""
from __future__ import annotations

import json

import pytest


# ---------------------------------------------------------------------------
# _infer_platform
# ---------------------------------------------------------------------------

class TestInferPlatform:
    def _p(self, url):
        from services.recipe_extractor import _infer_platform
        return _infer_platform(url)

    def test_youtube_com(self):
        assert self._p("https://www.youtube.com/watch?v=abc123") == "youtube"

    def test_youtu_be_short(self):
        assert self._p("https://youtu.be/abc123") == "youtube"

    def test_tiktok(self):
        assert self._p("https://www.tiktok.com/@user/video/123") == "tiktok"

    def test_spotify(self):
        assert self._p("https://open.spotify.com/episode/abc") == "podcast"

    def test_soundcloud(self):
        assert self._p("https://soundcloud.com/user/track") == "podcast"

    def test_generic_web(self):
        assert self._p("https://example.com/recipe/risoto") == "web"

    def test_empty_string(self):
        assert self._p("") == "local"

    def test_no_http_prefix(self):
        assert self._p("/path/to/file.mp4") == "local"

    def test_anchor_fm_podcast(self):
        assert self._p("https://anchor.fm/show/episode") == "podcast"


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------

class TestExtractJson:
    def _ej(self, raw):
        from services.recipe_extractor import _extract_json
        return _extract_json(raw)

    def test_plain_json(self):
        raw = '{"title": "Risoto", "ingredients": []}'
        result = self._ej(raw)
        assert result == {"title": "Risoto", "ingredients": []}

    def test_json_in_markdown_code_block(self):
        raw = '```json\n{"title": "Bolo"}\n```'
        result = self._ej(raw)
        assert result["title"] == "Bolo"

    def test_json_in_plain_code_block(self):
        raw = '```\n{"title": "Sopa"}\n```'
        result = self._ej(raw)
        assert result["title"] == "Sopa"

    def test_json_embedded_in_text(self):
        raw = 'Aqui está o resultado: {"title": "Frango"} fim.'
        result = self._ej(raw)
        assert result["title"] == "Frango"

    def test_raises_on_invalid_json(self):
        with pytest.raises(Exception):
            self._ej("isso não é json")

    def test_nested_json(self):
        raw = '{"a": {"b": 1}}'
        result = self._ej(raw)
        assert result["a"]["b"] == 1


# ---------------------------------------------------------------------------
# _clean_vtt
# ---------------------------------------------------------------------------

class TestCleanVtt:
    def _clean(self, raw):
        from services.recipe_extractor import _clean_vtt
        return _clean_vtt(raw)

    def test_removes_webvtt_header(self):
        raw = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nOlá mundo"
        result = self._clean(raw)
        assert "WEBVTT" not in result
        assert "Olá mundo" in result

    def test_removes_timestamp_lines(self):
        raw = "00:00:01.000 --> 00:00:03.000\nTexto aqui"
        result = self._clean(raw)
        assert "-->" not in result
        assert "Texto aqui" in result

    def test_removes_html_tags(self):
        raw = "00:00:01.000 --> 00:00:02.000\n<c>Palavra</c> normal"
        result = self._clean(raw)
        assert "<c>" not in result
        assert "Palavra" in result

    def test_removes_numeric_index_lines(self):
        raw = "1\n00:00:01.000 --> 00:00:02.000\nLinha de texto"
        result = self._clean(raw)
        assert result.strip() == "Linha de texto"

    def test_deduplicates_adjacent_identical_lines(self):
        raw = (
            "00:00:01.000 --> 00:00:02.000\nTexto repetido\n"
            "00:00:02.000 --> 00:00:03.000\nTexto repetido\n"
            "00:00:03.000 --> 00:00:04.000\nTexto diferente"
        )
        result = self._clean(raw)
        words = result.split()
        # "Texto repetido" não deve aparecer duas vezes consecutivamente no resultado
        assert result.count("Texto repetido") == 1

    def test_empty_input_returns_empty(self):
        assert self._clean("") == ""

    def test_clean_vtt_removes_vtt_timestamp_tags(self):
        raw = "00:00:01.000 --> 00:00:02.000\n<00:00:01.500>texto"
        result = self._clean(raw)
        assert "<" not in result
        assert "texto" in result


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------

class TestSlugify:
    def _slug(self, text):
        from services.recipe_extractor import _slugify
        return _slugify(text)

    def test_spaces_replaced_by_hyphens(self):
        result = self._slug("risoto de funghi")
        assert " " not in result

    def test_lowercase(self):
        result = self._slug("Risoto De Funghi")
        assert result == result.lower()

    def test_special_chars_removed(self):
        result = self._slug("bolo: de-chocolate!")
        # Não deve ter caracteres especiais além de hífens e alfanuméricos
        import re
        assert re.match(r'^[a-z0-9-]+$', result), f"slug com chars inesperados: {result!r}"

    def test_empty_string(self):
        result = self._slug("")
        assert isinstance(result, str)
