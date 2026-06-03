"""
translator.py — tradução de textos (KOSMOS v3, Fase 6).

Backend padrão: **argostranslate** (offline, sem rede após instalar o par de idiomas).
Backend opcional: **LOGOS** (quando `translation_backend == "logos"` na config e o LOGOS
estiver disponível) — usa `ecosystem_client.request_llm`.

O idioma alvo vem da config (`default_translation_lang`, definido em Settings). O idioma
de origem é detectado por heurística (`feed_fetcher.detect_language`) quando não informado.

Tudo é **best-effort**: se um backend falhar/indisponível, cai para o outro; se ambos
falharem, retorna `None` e loga. Nunca propaga exceção — traduzir é melhoria opcional,
não pode quebrar leitura/indexação. Todo caminho de erro é logado (princípio de
observabilidade do ecossistema).
"""
from __future__ import annotations

import logging

from app.core.feed_fetcher import detect_language
from app.utils import paths as _paths  # noqa: F401  (garante program files no sys.path)

log = logging.getLogger("kosmos.translator")

# Nomes de idioma para o prompt do LOGOS (códigos ISO → nome em português).
_LANG_NAMES = {
    "pt": "português", "en": "inglês", "es": "espanhol", "fr": "francês",
    "de": "alemão", "it": "italiano", "nl": "holandês", "ru": "russo",
    "ja": "japonês", "zh": "chinês", "ar": "árabe",
}


# ---------------------------------------------------------------------------
# Backend: argostranslate (offline)
# ---------------------------------------------------------------------------

def _ensure_argos_pair(source: str, target: str) -> bool:
    """Garante que o par de idiomas argostranslate esteja instalado.

    Se já instalado, retorna True imediatamente. Se ausente, tenta baixar/instalar
    o pacote (requer rede, best-effort). Retorna True se o par estiver disponível.
    """
    try:
        import argostranslate.translate as at
    except Exception as exc:
        log.warning("translator: argostranslate indisponível para checar par: %s", exc)
        return False

    try:
        if at.get_translation_from_codes(source, target) is not None:
            return True
    except Exception:
        pass  # par ausente — segue para tentativa de instalação (logada abaixo se falhar)

    try:
        import argostranslate.package as ap
        ap.update_package_index()
        available = ap.get_available_packages()
        pkg = next(
            (p for p in available if p.from_code == source and p.to_code == target),
            None,
        )
        if pkg is None:
            log.warning("translator: par argos %s→%s não existe no índice de pacotes", source, target)
            return False
        ap.install_from_path(pkg.download())
        log.info("translator: par argos %s→%s instalado", source, target)
        return at.get_translation_from_codes(source, target) is not None
    except Exception as exc:
        log.warning("translator: falha ao instalar par argos %s→%s: %s", source, target, exc)
        return False


def _translate_argos(text: str, source: str, target: str) -> str | None:
    """Traduz via argostranslate. Retorna None em qualquer falha (logada)."""
    try:
        import argostranslate.translate as at
    except Exception as exc:
        log.warning("translator: argostranslate indisponível: %s", exc)
        return None
    if not _ensure_argos_pair(source, target):
        return None
    try:
        result = at.translate(text, source, target)
        return result.strip() or None if result else None
    except Exception as exc:
        log.warning("translator: argos falhou %s→%s: %s", source, target, exc)
        return None


# ---------------------------------------------------------------------------
# Backend: LOGOS (online, opcional)
# ---------------------------------------------------------------------------

def _translate_logos(text: str, target: str, priority: int = 3) -> str | None:
    """Traduz via LOGOS (request_llm). Retorna None se offline/falha (logado)."""
    try:
        import ecosystem_client as _ec
    except Exception as exc:
        log.warning("translator: ecosystem_client indisponível para LOGOS: %s", exc)
        return None

    target_name = _LANG_NAMES.get(target, target)
    messages = [
        {
            "role": "system",
            "content": (
                f"Você é um tradutor. Traduza o texto do usuário para {target_name}. "
                "Responda APENAS com a tradução, sem comentários, sem aspas, sem notas."
            ),
        },
        {"role": "user", "content": text},
    ]
    try:
        resp = _ec.request_llm(messages, app="kosmos", priority=priority)
        choices = resp.get("choices") or []
        content = (choices[0].get("message", {}).get("content", "") if choices else "").strip()
        if not content:
            log.warning("translator: LOGOS retornou tradução vazia (alvo=%s)", target)
            return None
        return content
    except Exception as exc:
        log.warning("translator: LOGOS falhou (alvo=%s): %s", target, exc)
        return None


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def translate(
    text: str,
    target_lang: str,
    source_lang: str | None = None,
    backend: str = "argos",
    priority: int = 3,
) -> str | None:
    """Traduz `text` para `target_lang`.

    Args:
        text:        texto a traduzir.
        target_lang: idioma alvo (ISO, ex.: "pt") — vem de Settings.
        source_lang: idioma de origem (ISO); se None, detectado por heurística.
        backend:     "argos" (padrão) ou "logos" — define a 1ª escolha; o outro é fallback.
        priority:    prioridade da chamada LOGOS (P3 background / P2 sob demanda).

    Returns:
        Texto traduzido, ou None se vazio, já no idioma alvo, ou se ambos os
        backends falharem.
    """
    if not text or not text.strip():
        return None
    if not target_lang or not target_lang.strip():
        log.warning("translator: idioma alvo ausente — tradução abortada")
        return None

    target = target_lang.strip().lower()
    source = (source_lang or "").strip().lower() or detect_language(text)

    if source and source == target:
        return text  # já está no idioma alvo — no-op

    order = ["logos", "argos"] if (backend or "argos").lower() == "logos" else ["argos", "logos"]

    for b in order:
        if b == "argos":
            if not source:
                # argos exige código de origem; sem detecção confiável, pula para o LOGOS
                log.debug("translator: origem desconhecida — pulando argos, tentando LOGOS")
                continue
            result = _translate_argos(text, source, target)
        else:
            result = _translate_logos(text, target, priority)
        if result:
            log.info(
                "translator: traduzido via %s (%s→%s, %d chars)",
                b, source or "auto", target, len(result),
            )
            return result

    log.warning(
        "translator: tradução falhou em todos os backends (%s→%s)",
        source or "auto", target,
    )
    return None
