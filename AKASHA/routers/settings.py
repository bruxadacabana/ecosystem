"""
AKASHA — Settings router
GET  /settings → renderiza settings.html com valores atuais
POST /settings → persiste no ecosystem.json e redireciona
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
log = logging.getLogger("akasha.settings")

_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

_LANGUAGE_OPTIONS = [
    ("pt", "Português"),
    ("en", "Inglês"),
    ("es", "Espanhol"),
    ("fr", "Francês"),
    ("de", "Alemão"),
    ("it", "Italiano"),
    ("ja", "Japonês"),
    ("zh", "Chinês"),
    ("ru", "Russo"),
    ("ar", "Árabe"),
    ("ko", "Coreano"),
]

_DEFAULTS: dict = {
    "web_search_backend":          "",
    "web_search_backend_fallback": "",
    "marginalia_api_key":  "",
    "unpaywall_email":     "",
    "invidious_instance":  "",
    "max_per_domain":      5,
    "web_pages":           4,
    "search_languages":    [],
    "default_city":        "",
    "src_web":             True,
    "src_local":           True,
    "src_sites":           True,
    "src_papers":          False,
    "src_videos":          False,
    "src_images":          False,
    "semantic_search":     True,
    "reranking":           False,
    "llm_query_expansion": True,
    "deep_research_max_docs": 8,
    "save_search_history": True,
    "save_clicks":         True,
    "interest_consolidate_interval_min": 30,
}


def _read_cfg() -> dict:
    try:
        import ecosystem_client as _ec  # type: ignore
        eco = _ec.read_ecosystem() or {}
        return eco.get("akasha", {})
    except Exception:
        return {}


def _save_cfg(updates: dict) -> None:
    try:
        import ecosystem_client as _ec  # type: ignore
        _ec.write_section("akasha", updates)
        log.info("settings saved: %s", sorted(updates.keys()))
    except Exception as exc:
        log.warning("settings: falha ao salvar ecosystem.json: %s", exc)


def _merged(cfg: dict) -> dict:
    """Retorna defaults mesclados com valores lidos do ecosystem.json."""
    merged = dict(_DEFAULTS)
    for k, v in cfg.items():
        if k in merged:
            merged[k] = v
    return merged


@router.get("/settings", response_class=HTMLResponse)
async def settings_get(request: Request, saved: str = "") -> HTMLResponse:
    cfg = _merged(_read_cfg())
    log.debug("settings GET: %s", cfg)  # logado ANTES de decifrar (não vaza segredo)
    # Exibe segredos em claro nos campos do form (ficam cifrados no ecosystem.json).
    try:
        import ecosystem_secrets  # type: ignore
        for _k in list(cfg.keys()):
            if ecosystem_secrets.looks_secret(_k):
                cfg[_k] = ecosystem_secrets.dec_or_keep(cfg.get(_k))
    except Exception as e:
        log.warning("settings GET: falha ao decifrar segredos: %s", e)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "cfg":              cfg,
            "language_options": _LANGUAGE_OPTIONS,
            "saved":            bool(saved),
            "active_tab":       "settings",
        },
    )


@router.post("/settings", response_class=HTMLResponse)
async def settings_post(request: Request) -> RedirectResponse:
    form = await request.form()

    def _int(key: str, default: int, lo: int | None = None, hi: int | None = None) -> int:
        try:
            val = int(form.get(key, default))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            val = default
        if lo is not None:
            val = max(lo, val)
        if hi is not None:
            val = min(hi, val)
        return val

    def _str(key: str) -> str:
        return (form.get(key) or "").strip()  # type: ignore[return-value]

    def _bool(key: str) -> bool:
        return key in form

    updates = {
        "web_search_backend":          _str("web_search_backend"),
        "web_search_backend_fallback": _str("web_search_backend_fallback"),
        "marginalia_api_key":     _str("marginalia_api_key"),
        "unpaywall_email":        _str("unpaywall_email"),
        "invidious_instance":     _str("invidious_instance"),
        "max_per_domain":         _int("max_per_domain", 5, lo=0),
        "web_pages":              _int("web_pages", 4, lo=1, hi=10),
        "search_languages":       list(form.getlist("search_languages")),
        "default_city":           _str("default_city"),
        "src_web":                _bool("src_web"),
        "src_local":              _bool("src_local"),
        "src_sites":              _bool("src_sites"),
        "src_papers":             _bool("src_papers"),
        "src_videos":             _bool("src_videos"),
        "src_images":             _bool("src_images"),
        "semantic_search":        _bool("semantic_search"),
        "reranking":              _bool("reranking"),
        "llm_query_expansion":    _bool("llm_query_expansion"),
        "deep_research_max_docs": _int("deep_research_max_docs", 8, lo=1, hi=20),
        "save_search_history":    _bool("save_search_history"),
        "save_clicks":            _bool("save_clicks"),
        "interest_consolidate_interval_min": _int("interest_consolidate_interval_min", 30, lo=5, hi=1440),
    }

    # Cifra campos sensíveis (marginalia_api_key etc.) antes de persistir.
    try:
        import ecosystem_secrets  # type: ignore
        for _k, _v in list(updates.items()):
            if ecosystem_secrets.looks_secret(_k):
                updates[_k] = ecosystem_secrets.enc_if_plaintext(_v)
    except Exception as e:
        log.warning("settings POST: falha ao cifrar segredos: %s", e)

    _save_cfg(updates)
    return RedirectResponse("/settings?saved=1", status_code=303)
