"""
AKASHA — Router de busca
GET /search?q=&sources=all|web|local → renderiza search.html
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import config
import database
from services.archiver import archive_url, fetch_and_extract
from services.web_search import SearchResult, search_web
from services.local_search import search_local
from services.crawler import search_sites
from database import (
    get_all_crawl_sites,
    get_favorite_domains,
    search_watch_later as _db_search_wl,
    log_activity,
)

router = APIRouter()

_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


@router.post("/archive")
async def archive(
    url: str = Form(...),
    tags: str = Form(""),    # comma-separated, ex: "python, web, referência"
    notes: str = Form(""),
) -> Response:
    """Arquiva uma URL em {AKASHA}/data/archive/."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    try:
        await archive_url(url, str(config.ARCHIVE_PATH), tags=tag_list, notes=notes)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Erro HTTP ao buscar URL: {exc.response.status_code}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Falha de rede: {exc}")
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    import json as _json
    await log_activity("archive", url, url, _json.dumps({"tags": tag_list}))
    return Response(status_code=200)


_PAGE_SIZE = 10


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q:         str = "",
    src_web:   str = "",   # "on" quando checkbox marcado
    src_eco:   str = "",
    src_sites: str = "",
    # retrocompat
    sources: str = "",
) -> HTMLResponse:
    # Retrocompat: mapeia ?sources=all|web|local para os novos params
    if sources and not any([src_web, src_eco, src_sites]):
        src_web   = "on" if sources in ("web",   "all") else ""
        src_eco   = "on" if sources in ("local", "all") else ""

    # Padrão: web + eco quando nada selecionado
    if not any([src_web, src_eco, src_sites]):
        src_web = src_eco = "on"

    web_results:        list[SearchResult] = []
    fav_results:        list[SearchResult] = []
    local_results:      list[SearchResult] = []
    site_results:       list[SearchResult] = []
    watch_later_results: list[SearchResult] = []
    error: str | None = None

    if q:
        try:
            tasks = await asyncio.gather(
                search_web(q, max_results=_PAGE_SIZE) if src_web   else asyncio.sleep(0, result=[]),
                search_local(q)                        if src_eco   else asyncio.sleep(0, result=[]),
                search_sites(q)                        if src_sites else asyncio.sleep(0, result=[]),
                _db_search_wl(q),
                return_exceptions=True,
            )
            web_r, eco_r, sites_r, wl_r = tasks
            if isinstance(web_r,   list): web_results   = web_r
            if isinstance(eco_r,   list): local_results = eco_r
            if isinstance(sites_r, list): site_results  = sites_r
            if isinstance(wl_r,    list):
                watch_later_results = [
                    SearchResult(title=r[2] or r[1], url=r[1], snippet=r[3], source="DEPOIS")
                    for r in wl_r
                ]
            # Propaga o primeiro erro real (RuntimeError da busca web)
            for res in tasks:
                if isinstance(res, RuntimeError):
                    error = str(res)
                    break
        except Exception as exc:
            error = str(exc)

        # Separar web_results em P2 (favoritos) e P3 (restante)
        if web_results:
            from urllib.parse import urlparse
            fav_domains = await get_favorite_domains()
            if fav_domains:
                def _domain(url: str) -> str:
                    return (urlparse(url).hostname or "").removeprefix("www.").lower()
                fav_results  = [r for r in web_results if _domain(r.url) in fav_domains]
                web_results  = [r for r in web_results if _domain(r.url) not in fav_domains]

        total = len(web_results) + len(fav_results) + len(local_results) + len(site_results) + len(watch_later_results)
        src_label = "+".join(filter(None, [
            "web" if src_web else "",
            "local" if src_eco else "",
            "sites" if src_sites else "",
        ]))
        import json as _json
        await database.save_search(q, src_label or "web", total)
        await log_activity("search", q, "", _json.dumps({"sources": src_label or "web", "results": total}))

    has_sites = src_sites and bool(await get_all_crawl_sites())
    recent = await database.recent_searches()

    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "web_results":          web_results,
            "fav_results":          fav_results,
            "local_results":        local_results,
            "site_results":         site_results,
            "watch_later_results":  watch_later_results,
            "has_more_web":         len(web_results) >= _PAGE_SIZE,
            "query":         q,
            "src_web":       bool(src_web),
            "src_eco":       bool(src_eco),
            "src_sites":     bool(src_sites),
            "has_sites":     has_sites,
            "recent":        recent,
            "error":         error,
            "active_tab":    "search",
        },
    )


@router.get("/search/json")
async def search_json(
    q:       str = "",
    sources: str = "web,sites",   # vírgula separada: web, eco, sites
    max:     int = 10,
) -> list[SearchResult]:
    """
    API JSON para o Mnemosyne (Pesquisa Profunda).
    Retorna resultados combinados das fontes selecionadas sem renderizar HTML.
    """
    if not q:
        return []

    src_list  = {s.strip() for s in sources.split(",")}
    src_web   = "web"   in src_list
    src_eco   = "eco"   in src_list
    src_sites = "sites" in src_list

    tasks = await asyncio.gather(
        search_web(q, max_results=max) if src_web   else asyncio.sleep(0, result=[]),
        search_local(q)                if src_eco   else asyncio.sleep(0, result=[]),
        search_sites(q)                if src_sites else asyncio.sleep(0, result=[]),
        return_exceptions=True,
    )

    combined: list[SearchResult] = []
    for result in tasks:
        if isinstance(result, list):
            combined.extend(result)

    return combined[:max]


class _FetchBody(BaseModel):
    url:       str
    max_words: int = 2000


class _FetchResponse(BaseModel):
    url:        str
    title:      str
    content_md: str
    word_count: int
    error:      str | None = None


@router.post("/fetch")
async def fetch(body: _FetchBody) -> _FetchResponse:
    """
    Fetch + scraping de uma URL (sem persistência). Usado pelo Mnemosyne para
    carregar conteúdo web na sessão de Pesquisa Profunda.
    Cascata: ecosystem_scraper → Jina Reader (fallback < 100 palavras).
    """
    try:
        page = await fetch_and_extract(body.url, max_words=body.max_words)
        return _FetchResponse(
            url=page.url,
            title=page.title,
            content_md=page.content_md,
            word_count=page.word_count,
        )
    except httpx.HTTPStatusError as exc:
        return _FetchResponse(
            url=body.url, title="", content_md="", word_count=0,
            error=f"HTTP {exc.response.status_code}",
        )
    except httpx.RequestError as exc:
        return _FetchResponse(
            url=body.url, title="", content_md="", word_count=0,
            error=f"Erro de rede: {exc}",
        )


@router.get("/search/more", response_class=HTMLResponse)
async def search_more(
    request: Request,
    q: str = "",
    sources: str = "web",
    offset: int = 0,
) -> HTMLResponse:
    """Fragmento HTMX: próxima página de resultados web."""
    results: list[SearchResult] = []
    if q and sources in ("web", "all"):
        try:
            results = await search_web(q, max_results=_PAGE_SIZE, offset=offset)
        except RuntimeError:
            pass

    return templates.TemplateResponse(
        request,
        "search_more.html",
        {
            "results": results,
            "query": q,
            "sources": sources,
            "next_offset": offset + _PAGE_SIZE,
            "has_more": len(results) >= _PAGE_SIZE,
        },
    )
