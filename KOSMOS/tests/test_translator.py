"""
Testes para app/core/translator.py (KOSMOS v3, Fase 6).

Cobre:
  - translate: no-op quando origem == alvo; texto vazio → None; alvo vazio → None;
  - backend argos (padrão): usa argostranslate quando a origem é conhecida;
  - detecção de origem quando source_lang None;
  - argos pulado quando a origem é desconhecida → tenta LOGOS;
  - backend logos: usa request_llm; parse de choices[0].message.content;
  - fallback entre backends (argos falha → logos; logos falha → argos);
  - ambos falham → None;
  - _translate_logos: LOGOS offline (RuntimeError) → None; resposta vazia → None;
  - config: translation_backend default "argos" e persistente.

argostranslate e ecosystem_client.request_llm são mockados — sem rede.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# translate — casos triviais
# ---------------------------------------------------------------------------

class TestTranslateBasics:
    def test_empty_text_returns_none(self):
        from app.core.translator import translate
        assert translate("", "pt") is None
        assert translate("   ", "pt") is None

    def test_empty_target_returns_none(self):
        from app.core.translator import translate
        assert translate("hello", "") is None

    def test_same_language_is_noop(self):
        from app.core.translator import translate
        assert translate("texto em português", "pt", source_lang="pt") == "texto em português"


# ---------------------------------------------------------------------------
# Backend argos
# ---------------------------------------------------------------------------

class TestArgosBackend:
    def test_argos_translates_with_known_source(self):
        from app.core import translator
        with patch.object(translator, "_ensure_argos_pair", return_value=True), \
             patch("argostranslate.translate.translate", return_value="olá mundo") as mt:
            out = translator.translate("hello world", "pt", source_lang="en", backend="argos")
        assert out == "olá mundo"
        mt.assert_called_once_with("hello world", "en", "pt")

    def test_source_detected_when_not_given(self):
        from app.core import translator
        with patch.object(translator, "detect_language", return_value="en") as md, \
             patch.object(translator, "_ensure_argos_pair", return_value=True), \
             patch("argostranslate.translate.translate", return_value="X") as mt:
            out = translator.translate("some english text", "pt", backend="argos")
        assert out == "X"
        md.assert_called_once()
        mt.assert_called_once_with("some english text", "en", "pt")

    def test_argos_skipped_when_source_unknown_falls_back_to_logos(self):
        from app.core import translator
        resp = {"choices": [{"message": {"content": "traduzido"}}]}
        with patch.object(translator, "detect_language", return_value=""), \
             patch("ecosystem_client.request_llm", return_value=resp) as ml, \
             patch("argostranslate.translate.translate") as mt:
            out = translator.translate("???", "pt", backend="argos")
        assert out == "traduzido"
        mt.assert_not_called()      # argos pulado (origem desconhecida)
        ml.assert_called_once()

    def test_argos_pair_unavailable_returns_none_alone(self):
        from app.core import translator
        with patch.object(translator, "_ensure_argos_pair", return_value=False), \
             patch("ecosystem_client.request_llm", side_effect=RuntimeError("offline")):
            out = translator.translate("hello", "pt", source_lang="en", backend="argos")
        assert out is None


# ---------------------------------------------------------------------------
# Backend LOGOS
# ---------------------------------------------------------------------------

class TestLogosBackend:
    def test_logos_translates(self):
        from app.core import translator
        resp = {"choices": [{"message": {"content": "  olá  "}}]}
        with patch("ecosystem_client.request_llm", return_value=resp) as ml:
            out = translator.translate("hello", "pt", source_lang="en", backend="logos")
        assert out == "olá"          # strip aplicado
        ml.assert_called_once()
        # app e priority repassados
        _, kwargs = ml.call_args
        assert kwargs["app"] == "kosmos"

    def test_logos_offline_returns_none(self):
        from app.core import translator
        # backend logos, e argos também indisponível (par falso) → None
        with patch("ecosystem_client.request_llm", side_effect=RuntimeError("offline")), \
             patch.object(translator, "_ensure_argos_pair", return_value=False):
            out = translator.translate("hello", "pt", source_lang="en", backend="logos")
        assert out is None

    def test_logos_empty_response_returns_none(self):
        from app.core.translator import _translate_logos
        resp = {"choices": [{"message": {"content": "   "}}]}
        with patch("ecosystem_client.request_llm", return_value=resp):
            assert _translate_logos("hello", "pt") is None

    def test_logos_no_choices_returns_none(self):
        from app.core.translator import _translate_logos
        with patch("ecosystem_client.request_llm", return_value={"choices": []}):
            assert _translate_logos("hello", "pt") is None


# ---------------------------------------------------------------------------
# Fallback entre backends
# ---------------------------------------------------------------------------

class TestFallback:
    def test_argos_fails_falls_back_to_logos(self):
        from app.core import translator
        resp = {"choices": [{"message": {"content": "via logos"}}]}
        with patch.object(translator, "_ensure_argos_pair", return_value=True), \
             patch("argostranslate.translate.translate", return_value=None), \
             patch("ecosystem_client.request_llm", return_value=resp):
            out = translator.translate("hello", "pt", source_lang="en", backend="argos")
        assert out == "via logos"

    def test_logos_fails_falls_back_to_argos(self):
        from app.core import translator
        with patch("ecosystem_client.request_llm", side_effect=RuntimeError("offline")), \
             patch.object(translator, "_ensure_argos_pair", return_value=True), \
             patch("argostranslate.translate.translate", return_value="via argos"):
            out = translator.translate("hello", "pt", source_lang="en", backend="logos")
        assert out == "via argos"

    def test_both_fail_returns_none(self):
        from app.core import translator
        with patch.object(translator, "_ensure_argos_pair", return_value=True), \
             patch("argostranslate.translate.translate", return_value=None), \
             patch("ecosystem_client.request_llm", side_effect=RuntimeError("offline")):
            out = translator.translate("hello", "pt", source_lang="en", backend="argos")
        assert out is None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestTranslationConfig:
    def test_default_backend_is_argos(self):
        from app.utils.config import KosmosConfig
        assert KosmosConfig().translation_backend == "argos"

    def test_backend_is_persistent_field(self):
        from app.utils.config import _PERSISTENT_FIELDS
        assert "translation_backend" in _PERSISTENT_FIELDS
