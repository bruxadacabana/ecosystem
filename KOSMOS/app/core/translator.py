"""Wrapper para tradução online via deep-translator (Google Translate)."""

from __future__ import annotations

import logging
import re

log = logging.getLogger("kosmos.translator")

# "auto" é válido apenas como idioma de origem (auto-detecção)
LANGUAGE_NAMES: dict[str, str] = {
    "auto":  "Detectar automaticamente",
    "en":    "English",
    "pt":    "Português",
    "es":    "Español",
    "fr":    "Français",
    "de":    "Deutsch",
    "it":    "Italiano",
    "ja":    "日本語",
    "zh-CN": "中文 (简体)",
    "ru":    "Русский",
    "ar":    "العربية",
    "ko":    "한국어",
    "nl":    "Nederlands",
    "pl":    "Polski",
    "sv":    "Svenska",
    "tr":    "Türkçe",
    "uk":    "Українська",
}

# Apenas idiomas de destino (sem "auto")
TARGET_LANGUAGE_NAMES: dict[str, str] = {
    k: v for k, v in LANGUAGE_NAMES.items() if k != "auto"
}

_CHUNK_SIZE = 4500  # Google Translate suporta ~5000 chars por chamada


def strip_html(html: str) -> str:
    """Remove tags HTML e retorna texto puro (sem preservar estrutura)."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def html_to_paragraphs(html: str) -> str:
    """Converte HTML em texto puro preservando quebras de parágrafo (\\n\\n).

    Cada tag de bloco (<p>, <h1>-<h6>, <li>, <div>, <br>) vira um separador
    antes de as tags serem removidas.  O resultado pode ser dividido por '\\n\\n'
    para recuperar os parágrafos originais.
    """
    # Tags de bloco → dois newlines
    text = re.sub(
        r"</(?:p|h[1-6]|li|div|blockquote|tr|thead|tbody|article|section)>",
        "\n\n", html, flags=re.IGNORECASE,
    )
    # <br> → newline simples
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    # Remover todas as tags restantes
    text = re.sub(r"<[^>]+>", "", text)
    # Decodificar entidades HTML básicas
    text = (text
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&nbsp;", " ")
            .replace("&quot;", '"')
            .replace("&#39;", "'"))
    # Normalizar espaços dentro de cada linha
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    # Colapsar mais de dois newlines consecutivos em exatamente dois
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_language(text: str) -> str | None:
    """Detecta o idioma via langdetect. Retorna código ISO 639-1 ou None."""
    try:
        import langdetect
        return langdetect.detect(text[:2000])
    except Exception:
        return None


def translate_text(text: str, from_code: str, to_code: str) -> str:
    """Traduz texto via Google Translate (deep-translator).

    Divide automaticamente textos longos em chunks por parágrafos para
    respeitar o limite de ~5000 caracteres por chamada.

    Raises:
        Exception: se deep-translator não estiver instalado ou a API falhar.
    """
    from deep_translator import GoogleTranslator

    translator = GoogleTranslator(source=from_code, target=to_code)

    if len(text) <= _CHUNK_SIZE:
        return translator.translate(text) or ""

    # Dividir em parágrafos, agrupando em chunks dentro do limite
    paragraphs = text.split("\n\n")
    parts: list[str] = []
    current = ""

    for para in paragraphs:
        if len(para) > _CHUNK_SIZE:
            # Parágrafo sozinho excede o limite — dividir por palavras
            if current:
                parts.append(translator.translate(current) or "")
                current = ""
            words = para.split(" ")
            sub = ""
            for word in words:
                if len(sub) + len(word) + 1 <= _CHUNK_SIZE:
                    sub = (sub + " " + word).lstrip(" ")
                else:
                    if sub:
                        parts.append(translator.translate(sub) or "")
                    sub = word
            if sub:
                parts.append(translator.translate(sub) or "")
        elif len(current) + len(para) + 2 <= _CHUNK_SIZE:
            current = (current + "\n\n" + para).lstrip("\n")
        else:
            if current:
                parts.append(translator.translate(current) or "")
            current = para

    if current:
        parts.append(translator.translate(current) or "")

    return "\n\n".join(parts)
