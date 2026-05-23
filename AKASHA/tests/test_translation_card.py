"""
Testes para services/translation_card.py.

Cobre:
  - parse_translation_query: tr:TEXT LANG → parsed; translate:TEXT LANG; traduzir…para;
    como se diz…em; TEXT em IDIOMA; query inválida → None
  - get_translation_card: modelo não instalado → fallback_url
  - get_translation_card: argostranslate indisponível → fallback_url (sem crash)
  - get_translation_card: modelo instalado (mock) → tradução retornada
  - get_translation_card: intent não-translation → None
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# parse_translation_query
# ---------------------------------------------------------------------------

def test_tr_colon_pattern():
    from services.translation_card import parse_translation_query
    r = parse_translation_query("tr:hello pt")
    assert r == {"text": "hello", "target_lang": "pt"}


def test_translate_colon_pattern():
    from services.translation_card import parse_translation_query
    r = parse_translation_query("translate:good morning en")
    assert r == {"text": "good morning", "target_lang": "en"}


def test_traduzir_para_pattern():
    from services.translation_card import parse_translation_query
    r = parse_translation_query("traduzir olá para inglês")
    assert r == {"text": "olá", "target_lang": "en"}


def test_como_se_diz_pattern():
    from services.translation_card import parse_translation_query
    r = parse_translation_query("como se diz hello em português")
    assert r == {"text": "hello", "target_lang": "pt"}


def test_texto_em_idioma_pattern():
    from services.translation_card import parse_translation_query
    r = parse_translation_query("hello em espanhol")
    assert r == {"text": "hello", "target_lang": "es"}


def test_invalid_query_returns_none():
    from services.translation_card import parse_translation_query
    assert parse_translation_query("python decorators") is None
    assert parse_translation_query("como funciona machine learning") is None
    assert parse_translation_query("") is None


def test_unknown_lang_returns_none():
    from services.translation_card import parse_translation_query
    # "klingon" não está no _LANG_MAP
    assert parse_translation_query("tr:hello klingon") is None


def test_tr_multiword_text():
    from services.translation_card import parse_translation_query
    r = parse_translation_query("tr:good morning everyone pt")
    assert r == {"text": "good morning everyone", "target_lang": "pt"}


# ---------------------------------------------------------------------------
# get_translation_card — modelo não instalado → fallback_url
# ---------------------------------------------------------------------------

def test_model_not_installed_returns_fallback():
    from services.translation_card import get_translation_card
    # argostranslate installed but get_installed_languages returns []
    with patch("argostranslate.translate.get_installed_languages", return_value=[]):
        result = get_translation_card("tr:hello pt")
    assert result is not None
    assert result["fallback_url"] is not None
    assert "libretranslate" in result["fallback_url"]
    assert result["original"] == "hello"
    assert result["target_lang"] == "pt"
    assert result["translated"] is None


# ---------------------------------------------------------------------------
# get_translation_card — argostranslate não importável → fallback_url (sem crash)
# ---------------------------------------------------------------------------

def test_argostranslate_unavailable_returns_fallback():
    import sys
    import importlib

    saved = sys.modules.get("argostranslate")
    saved_tr = sys.modules.get("argostranslate.translate")
    sys.modules["argostranslate"] = None  # type: ignore
    sys.modules["argostranslate.translate"] = None  # type: ignore

    try:
        # Re-importar o módulo para forçar o caminho de except
        if "services.translation_card" in sys.modules:
            del sys.modules["services.translation_card"]
        from services.translation_card import get_translation_card
        result = get_translation_card("tr:hello pt")
        assert result is not None
        assert result["fallback_url"] is not None
        assert result["translated"] is None
    finally:
        if saved is None:
            sys.modules.pop("argostranslate", None)
        else:
            sys.modules["argostranslate"] = saved
        if saved_tr is None:
            sys.modules.pop("argostranslate.translate", None)
        else:
            sys.modules["argostranslate.translate"] = saved_tr
        if "services.translation_card" in sys.modules:
            del sys.modules["services.translation_card"]


# ---------------------------------------------------------------------------
# get_translation_card — modelo instalado (mock) → tradução retornada
# ---------------------------------------------------------------------------

def test_model_installed_returns_translation():
    from services.translation_card import get_translation_card

    mock_translation = MagicMock()
    mock_translation.translate.return_value = "olá"

    mock_tgt_lang = MagicMock()
    mock_tgt_lang.code = "pt"

    mock_src_lang = MagicMock()
    mock_src_lang.code = "en"
    mock_src_lang.get_translation.return_value = mock_translation

    # langdetect pode identificar "hello" como idioma inesperado (ex: finlandês)
    # → mockar a detecção de idioma fonte para retornar "en" de forma determinística
    with patch("argostranslate.translate.get_installed_languages",
               return_value=[mock_src_lang, mock_tgt_lang]), \
         patch("services.translation_card._detect_source_lang", return_value="en"):
        result = get_translation_card("tr:hello pt")

    assert result is not None
    assert result["translated"] == "olá"
    assert result["fallback_url"] is None
    assert result["original"] == "hello"


# ---------------------------------------------------------------------------
# get_translation_card — query sem intent translation → None
# ---------------------------------------------------------------------------

def test_non_translation_query_returns_none():
    from services.translation_card import get_translation_card
    assert get_translation_card("python decorators") is None
    assert get_translation_card("o que é machine learning") is None


# ---------------------------------------------------------------------------
# _resolve_lang: casos de borda
# ---------------------------------------------------------------------------

def test_resolve_lang_case_insensitive():
    from services.translation_card import _resolve_lang
    assert _resolve_lang("INGLÊS") == "en"
    assert _resolve_lang("Português") == "pt"
    assert _resolve_lang("EN") == "en"
