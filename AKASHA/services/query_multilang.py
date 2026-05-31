"""
AKASHA — Expansão multilíngue de queries.

Objetivo: quando a usuária busca em PT, encontrar também documentos em EN/ES e
vice-versa. Duas estratégias complementares:

  1. Busca vetorial cross-lingual (sempre ativa, zero custo extra):
     O modelo potion-multilingual-128M mapeia queries e documentos de 101 idiomas
     para o mesmo espaço vetorial — uma query em PT já encontra docs em EN/ES/JA
     sem tradução. Esta estratégia cobre embeddings de crawl_pages.

  2. Tradução de query para FTS5 (ativada quando search_languages configurado):
     FTS5 é monolingue por definição (BM25 sobre tokens). Para cruzar idiomas na
     camada lexical, traduzimos a query via LOGOS antes de buscar. Só entra em ação
     quando a usuária configura idiomas-alvo em Settings.

Funções:
  detect_language()   — código ISO do idioma da query (langdetect, fallback "pt")
  translate_query()   — traduz query para um idioma-alvo via LOGOS (llm_query)
  expand_multilang()  — orquestra: detecta idioma + traduz para targets configurados
"""
from __future__ import annotations

import logging

log = logging.getLogger("akasha.query_multilang")

# ---------------------------------------------------------------------------
# Detecção de idioma
# ---------------------------------------------------------------------------

def detect_language(query: str) -> str:
    """Retorna código ISO 639-1 do idioma da query (ex: 'pt', 'en', 'es', 'ja').

    Usa langdetect com seed fixo (42) para resultados deterministas.
    Fallback 'pt' se falhar ou query for muito curta.
    """
    if not query.strip():
        return "pt"
    try:
        from langdetect import detect, DetectorFactory  # type: ignore
        DetectorFactory.seed = 42
        code = detect(query.strip())
        return code if code else "pt"
    except Exception as exc:
        log.debug("detect_language: %s — fallback 'pt'", exc)
        return "pt"


# ---------------------------------------------------------------------------
# Tradução de query via LOGOS
# ---------------------------------------------------------------------------

def _get_logos_base() -> str:
    try:
        from ecosystem_client import get_inference_url  # type: ignore
        return get_inference_url()
    except Exception:
        return "http://localhost:7072"


def _get_logos_model() -> str:
    try:
        from ecosystem_client import get_active_profile  # type: ignore
        p = get_active_profile()
        return ((p or {}).get("models", {}) or {}).get("llm_query", "") if p else ""
    except Exception:
        return ""


async def translate_query(query: str, target_lang: str) -> str | None:
    """Traduz query para target_lang via LOGOS /v1/chat/completions.

    Usa estilo de busca compacto — sem explicação, sem pontuação extra.
    Retorna None se LOGOS offline ou qualquer erro de rede/protocolo.
    Máximo 30 tokens para manter a resposta concisa.
    """
    if not query.strip() or not target_lang.strip():
        return None
    model = _get_logos_model()
    if not model:
        log.debug("translate_query: nenhum modelo llm_query configurado")
        return None
    prompt = (
        f"Translate this search query to {target_lang} "
        f"(keep concise, search query style, no explanation, no punctuation at end): {query.strip()}"
    )
    try:
        import httpx
        base = _get_logos_base()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{base}/v1/chat/completions",
                json={
                    "model":       model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "stream":      False,
                    "max_tokens":  30,
                    "temperature": 0.0,
                },
            )
            resp.raise_for_status()
            translated = resp.json()["choices"][0]["message"]["content"].strip().strip("\"'.,")
            if translated and translated.lower() != query.lower():
                log.debug("translate_query: '%s' → '%s' [%s]", query, translated, target_lang)
                return translated
            return None
    except Exception as exc:
        log.debug("translate_query: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Expansão multilíngue orquestrada
# ---------------------------------------------------------------------------

async def expand_multilang(query: str, target_langs: list[str]) -> list[str]:
    """Retorna lista de queries para busca FTS5 multilíngue.

    Lógica:
    - target_langs vazio → retorna [query] sem tradução (busca vetorial cross-lingual
      já cobre cruzamento de idiomas; FTS5 usa query original).
    - target_langs preenchido → detecta idioma original; traduz para cada target
      diferente do original em paralelo; deduplicação por texto normalizado;
      retorna [original, tradução1, tradução2, ...].

    Deduplicação: remove traduções idênticas ao original ou entre si
    (comparação case-insensitive após strip).

    LOGOS offline → retorna [query] silenciosamente (FTS5 continua com original).
    """
    if not target_langs:
        log.debug("expand_multilang: target_langs vazio — retornando query original")
        return [query]

    origin_lang = detect_language(query)
    langs_to_translate = [l for l in target_langs if l != origin_lang]

    if not langs_to_translate:
        log.debug("expand_multilang: idioma da query já é o alvo — sem tradução")
        return [query]

    import asyncio
    translations = await asyncio.gather(
        *[translate_query(query, lang) for lang in langs_to_translate],
        return_exceptions=True,
    )

    seen = {query.strip().lower()}
    result = [query]
    for t in translations:
        if isinstance(t, str) and t.strip().lower() not in seen:
            seen.add(t.strip().lower())
            result.append(t)
        elif isinstance(t, Exception):
            log.debug("expand_multilang: tradução falhou: %s", t)

    log.debug(
        "expand_multilang: q=%r origin=%s targets=%r → %d variante(s)",
        query, origin_lang, langs_to_translate, len(result),
    )
    return result


# ---------------------------------------------------------------------------
# Leitura de configuração
# ---------------------------------------------------------------------------

def get_search_languages() -> list[str]:
    """Lê ecosystem.json["akasha"]["search_languages"] em runtime.

    Retorna [] (sem restrição) se não configurado ou em qualquer erro.
    """
    try:
        return list((_get_akasha_cfg() or {}).get("search_languages", []))
    except Exception:
        return []


def _get_akasha_cfg() -> dict:
    try:
        from ecosystem_client import get_akasha_config  # type: ignore
        return get_akasha_config() or {}
    except Exception:
        return {}
