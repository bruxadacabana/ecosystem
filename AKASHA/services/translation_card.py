"""
AKASHA — Tradução inline via Argos Translate.

Padrões suportados:
  tr:TEXTO IDIOMA              → traduz TEXTO para IDIOMA
  translate:TEXTO IDIOMA       → traduz TEXTO para IDIOMA
  traduzir TEXTO para IDIOMA
  como se diz/escreve TEXTO em IDIOMA
  TEXTO em inglês/português/espanhol/...

Se o par de idiomas não estiver instalado, retorna fallback_url para LibreTranslate.
"""
from __future__ import annotations

import re
from typing import Optional

_LIBRETRANSLATE_URL = "https://libretranslate.com"

# Mapa de nomes e códigos de idioma → código ISO 639-1
_LANG_MAP: dict[str, str] = {
    "inglês": "en", "ingles": "en", "english": "en", "en": "en",
    "português": "pt", "portugues": "pt", "portuguese": "pt", "pt": "pt",
    "espanhol": "es", "spanish": "es", "es": "es", "castellano": "es",
    "francês": "fr", "frances": "fr", "french": "fr", "fr": "fr",
    "alemão": "de", "alemao": "de", "german": "de", "de": "de",
    "italiano": "it", "italian": "it", "it": "it",
    "japonês": "ja", "japones": "ja", "japanese": "ja", "ja": "ja",
    "chinês": "zh", "chines": "zh", "chinese": "zh", "zh": "zh",
    "árabe": "ar", "arabe": "ar", "arabic": "ar", "ar": "ar",
    "russo": "ru", "russian": "ru", "ru": "ru",
}

# Idiomas nomeados em PT/EN — para o padrão "TEXTO em IDIOMA"
_NAMED_LANGS = (
    "inglês", "ingles", "português", "portugues", "espanhol",
    "francês", "frances", "alemão", "alemao", "italiano",
    "japonês", "japones", "chinês", "chines", "russo",
    "english", "portuguese", "spanish", "french", "german",
    "italian", "japanese", "chinese", "russian",
)

_NAMED_LANGS_PATTERN = "|".join(re.escape(l) for l in sorted(_NAMED_LANGS, key=len, reverse=True))

_PATTERNS = [
    # tr:TEXTO IDIOMA  ou  translate:TEXTO IDIOMA
    re.compile(r"^(?:tr|translate):(.+?)\s+(\S+)$", re.IGNORECASE),
    # traduzir TEXTO para IDIOMA
    re.compile(r"^traduzir\s+(.+?)\s+para\s+(\S+)$", re.IGNORECASE),
    # como se diz/escreve/fala TEXTO em IDIOMA
    re.compile(r"^como se (?:diz|escreve|fala)\s+(.+?)\s+em\s+(\S+)$", re.IGNORECASE),
    # TEXTO em IDIOMA (nomes conhecidos)
    re.compile(rf"^(.+?)\s+em\s+({_NAMED_LANGS_PATTERN})$", re.IGNORECASE),
]


def _resolve_lang(raw: str) -> Optional[str]:
    """Converte nome ou código de idioma em código ISO 639-1."""
    return _LANG_MAP.get(raw.lower().rstrip("?.!,"))


def parse_translation_query(query: str) -> Optional[dict]:
    """Extrai {text, target_lang} de uma query de tradução. Retorna None se não casar."""
    q = query.strip()
    for pattern in _PATTERNS:
        m = pattern.match(q)
        if m:
            text = m.group(1).strip()
            lang_code = _resolve_lang(m.group(2).strip())
            if lang_code and text:
                return {"text": text, "target_lang": lang_code}
    return None


def _detect_source_lang(text: str) -> str:
    """Detecta idioma via langdetect; fallback por heurística se indisponível."""
    try:
        from langdetect import detect as _detect
        lang = _detect(text)
        return lang[:2] if lang else "pt"
    except Exception:
        if any(c in text for c in "ãõáéíóúàêôç"):
            return "pt"
        return "en"


def get_translation_card(query: str) -> Optional[dict]:
    """Tenta traduzir via argostranslate. Retorna card com resultado ou fallback_url.

    Retorna None se a query não for reconhecida como pedido de tradução.
    Retorna dict com fallback_url se o par de idiomas não estiver instalado.
    """
    parsed = parse_translation_query(query)
    if not parsed:
        return None

    text = parsed["text"]
    target_lang = parsed["target_lang"]
    source_lang = _detect_source_lang(text)

    if source_lang == target_lang:
        source_lang = "pt" if target_lang == "en" else "en"

    _fallback: dict = {
        "original":     text,
        "source_lang":  source_lang,
        "target_lang":  target_lang,
        "translated":   None,
        "fallback_url": _LIBRETRANSLATE_URL,
    }

    try:
        from argostranslate import translate as _tr
        installed = _tr.get_installed_languages()
        src_langs = [l for l in installed if l.code == source_lang]
        tgt_langs = [l for l in installed if l.code == target_lang]

        if not src_langs or not tgt_langs:
            return _fallback

        translation = src_langs[0].get_translation(tgt_langs[0])
        if not translation:
            return _fallback

        translated = translation.translate(text)
        return {
            "original":     text,
            "source_lang":  source_lang,
            "target_lang":  target_lang,
            "translated":   translated,
            "fallback_url": None,
        }
    except Exception:
        return _fallback
