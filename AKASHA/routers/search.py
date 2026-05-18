"""
AKASHA — Router de busca
GET /search?q=&sources=all|web|local → renderiza search.html
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

import httpx
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from services import search_session as _session_svc
from services.search_profile import load_profile, apply_to_sources as _apply_profile

import config
import database
from services.archiver import archive_url, fetch_and_extract, NearDuplicateError, DoiDuplicateError
from services.web_search import SearchResult, search_web
from services.local_search import (
    search_local, correct_query, get_ollama_status,
    suggest_related_docs, suggest_related_queries,
)
from services.query_understanding import pin_model, classify_intent, needs_rewrite, rewrite_query, score_ambiguity, summarize_snippets
from services.crawler import search_sites, index_visited_page
from services.paper_search import PaperResult, search_papers
from database import (
    get_all_crawl_sites,
    get_favorite_domains,
    search_watch_later as _db_search_wl,
    log_activity,
    record_search_query,
    get_query_suggestions,
    get_suggested_tags,
)

router = APIRouter()
log = logging.getLogger("akasha.search")

_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


def _voice_texts() -> dict[str, str]:
    """Retorna textos de interface segundo AKASHA_VOICE configurado em config.py."""
    from config import AKASHA_VOICE
    if AKASHA_VOICE == "assistente":
        return {
            "intent_nav":       "Navegação — fui direto ao ponto",
            "intent_fact":      "Factual — priorizei seu arquivo",
            "empty_title":      "Não encontrei nada",
            "empty_hint":       "Tente reformular — posso ter mais sorte.",
            "expand_label":     "Também explorei:",
            "related_label":    "Talvez interesse também:",
            "session_label":    "Sessão ativa:",
        }
    return {  # neutro (padrão)
        "intent_nav":       "Navegação — melhor resultado",
        "intent_fact":      "Factual — priorizando arquivo local",
        "empty_title":      "Nenhum resultado",
        "empty_hint":       "Tente termos diferentes ou verifique a ortografia.",
        "expand_label":     "Expandido com:",
        "related_label":    "Explorar também",
        "session_label":    "Sessão:",
    }


def _local_ext(url: str) -> str:
    """Extrai extensão de arquivo (sem ponto, minúscula) de uma URL file://."""
    if not url.startswith("file://"):
        return ""
    path = unquote(urlparse(url).path)
    ext = PurePosixPath(path).suffix.lower().lstrip(".")
    return ext if ext else "outros"


@router.post("/archive")
async def archive(
    url: str = Form(...),
    tags: str = Form(""),    # comma-separated, ex: "python, web, referência"
    notes: str = Form(""),
) -> Response:
    """Arquiva uma URL em {AKASHA}/data/archive/."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    try:
        page = await archive_url(url, str(config.ARCHIVE_PATH), tags=tag_list, notes=notes)
    except NearDuplicateError as exc:
        raise HTTPException(status_code=409, detail=f"Near-duplicate de documento já arquivado: {exc.existing_url}")
    except DoiDuplicateError as exc:
        raise HTTPException(status_code=409, detail=f"Artigo já arquivado com este DOI ({exc.doi}): {exc.existing_url}")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Erro HTTP ao buscar URL: {exc.response.status_code}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Falha de rede: {exc}")
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        log.error("archive: exceção inesperada para %s: %s", url, exc)
        raise HTTPException(status_code=500, detail=f"Erro inesperado: {exc}")

    import json as _json
    try:
        await log_activity("archive", url, url, _json.dumps({"tags": tag_list}))
    except Exception as exc:
        log.warning("archive: log_activity falhou para %s: %s", url, exc)

    # Agenda extração de conhecimento em background (P3)
    from services.knowledge_worker import schedule_page as _schedule_page
    _schedule_page(url, page.title, page.content_md, "archived")

    # Se o domínio é favorito, indexa a página no crawl_fts em background
    try:
        from urllib.parse import urlparse as _up
        _domain = (_up(url).hostname or "").removeprefix("www.").lower()
        fav_domains = await get_favorite_domains()
        if _domain in fav_domains:
            asyncio.create_task(index_visited_page(url, page.title, page.content_md))
    except Exception as exc:
        log.warning("archive: verificação de favoritos falhou para %s: %s", url, exc)

    return Response(status_code=200)


_PAGE_SIZE = 10


@router.get("/search", response_class=HTMLResponse)
async def search(
    request:    Request,
    q:          str = "",
    src_web:    str = "",   # "on" quando checkbox marcado
    src_eco:    str = "",
    src_sites:  str = "",
    src_papers: str = "",
    filetype:   str = "",   # ex: "pdf", "epub" — acrescenta ao query DDG
    mode:       str = "",   # preset: "papers" | "local" | "archive"
    facet_ext:  str = "",   # filtro de extensão de arquivo para resultados locais
    lens_id:    int = 0,    # id de lens pessoal a aplicar (0 = sem lens)
    intent:       str = "",   # sobrescreve o classificador: navigational|fact-seeking|exploratory
    no_expansion: str = "",   # "on" = desativa expansão LLM para esta busca
    no_rewrite:   str = "",   # "on" = desativa reescrita conversacional para esta busca
    # retrocompat
    sources: str = "",
) -> HTMLResponse:
    # Presets de modo — forçam combinação de sources
    if mode == "papers":
        src_papers, src_web, src_eco, src_sites = "on", "", "", ""
    elif mode == "local":
        src_eco, src_web, src_papers, src_sites = "on", "", "", ""

    # Retrocompat: mapeia ?sources=all|web|local para os novos params
    if sources and not any([src_web, src_eco, src_sites]):
        src_web   = "on" if sources in ("web",   "all") else ""
        src_eco   = "on" if sources in ("local", "all") else ""

    # Perfil persistente: aplicado quando usuária não escolheu fontes explicitamente
    _user_explicit = any([src_web, src_eco, src_sites, src_papers])
    _profile = await load_profile()
    _profile_applied = False
    if not _user_explicit:
        src_web, src_eco, src_sites, src_papers, _profile_applied = _apply_profile(
            _profile, src_web, src_eco, src_sites, src_papers, _user_explicit
        )

    # Padrão: web + eco + sites quando nada selecionado
    if not any([src_web, src_eco, src_sites, src_papers]):
        src_web = src_eco = src_sites = "on"

    web_results:         list[SearchResult] = []
    fav_results:         list[SearchResult] = []
    local_results:       list[SearchResult] = []
    site_results:        list[SearchResult] = []
    watch_later_results: list[SearchResult] = []
    paper_results:       list[PaperResult]  = []
    error: str | None = None
    corrected_query: str | None = None
    local_facets: dict[str, int] = {}
    active_lens: dict | None = None
    _eco_expanded:           list[str]          = []
    related_docs:            list[SearchResult] = []
    related_queries:         list[str]          = []
    _clarification_question: str               = ""
    # intent pode vir da URL (override manual) ou do classificador automático
    _intent_forced = intent in ("navigational", "fact-seeking", "exploratory")

    # Sessão de pesquisa — cookie identifica o browser; gerado se ausente
    _session_id = request.cookies.get("akasha_session") or secrets.token_urlsafe(16)
    _new_cookie = not request.cookies.get("akasha_session")
    _active_session: _session_svc.SearchSession | None = _session_svc.get_session(_session_id)

    if q:
        # Reescrita conversacional: reescreve anáforas/queries curtas usando contexto da sessão.
        # Acontece antes das buscas — _effective_query é o que realmente buscamos.
        _rewritten_query: str = ""
        _effective_query: str = q
        if (
            not no_rewrite
            and _active_session is not None
            and _active_session.context_queries(q)
            and needs_rewrite(q)
            and get_ollama_status()
        ):
            try:
                _rw = await asyncio.wait_for(
                    rewrite_query(q, _active_session.context_queries(q)),
                    timeout=3.0,
                )
                if _rw:
                    _rewritten_query = _rw
                    _effective_query = _rw
            except (asyncio.TimeoutError, Exception):
                pass

        # Fixar modelo em VRAM + classificar intenção em paralelo com as buscas.
        # Classificador usa _effective_query (pode ser a query reescrita).
        intent_future = None
        _ambiguity_future = None
        if get_ollama_status():
            asyncio.ensure_future(pin_model())
            if not _intent_forced:
                intent_future = asyncio.ensure_future(classify_intent(_effective_query))
            # Clarificação seletiva: avalia ambiguidade em paralelo (máx 1 pergunta/sessão)
            if _active_session is not None and not _active_session.asked_clarification:
                _ambiguity_future = asyncio.ensure_future(score_ambiguity(_effective_query))

        _use_expansion = not bool(no_expansion)
        try:
            tasks = await asyncio.gather(
                search_web(_effective_query, max_results=_PAGE_SIZE, filetype=filetype) if src_web    else asyncio.sleep(0, result=[]),
                search_local(_effective_query, expand=_use_expansion,
                             expansion_log=_eco_expanded if _use_expansion else None)
                                                                                         if src_eco    else asyncio.sleep(0, result=[]),
                search_sites(_effective_query)                                            if src_sites  else asyncio.sleep(0, result=[]),
                search_papers(_effective_query)                                           if src_papers else asyncio.sleep(0, result=[]),
                _db_search_wl(_effective_query),
                return_exceptions=True,
            )
            web_r, eco_r, sites_r, papers_r, wl_r = tasks
            if isinstance(web_r,    list): web_results    = web_r
            if isinstance(eco_r,    list): local_results  = eco_r
            if isinstance(sites_r,  list): site_results   = sites_r
            if isinstance(papers_r, list): paper_results  = papers_r
            if isinstance(wl_r,     list):
                watch_later_results = [
                    SearchResult(title=r[2] or r[1], url=r[1], snippet=r[3], source="DEPOIS")
                    for r in wl_r
                ]
            for res in tasks:
                if isinstance(res, RuntimeError):
                    error = str(res)
                    break
        except Exception as exc:
            error = str(exc)

        # Resolver intenção — usa override da URL ou aguarda classificador paralelo
        if _intent_forced:
            pass  # intent já está definido pelo query param
        elif intent_future:
            try:
                intent = await asyncio.wait_for(asyncio.shield(intent_future), timeout=0.1)
            except (asyncio.TimeoutError, Exception):
                intent = "exploratory"
        else:
            intent = "exploratory"

        # Roteamento por intenção — apenas ajusta quantidade/prioridade de resultados;
        # nunca sintetiza nem interpreta conteúdo (AKASHA é amplificador, não respondedor).
        if intent == "navigational":
            # Usuária sabe o que quer — retorna o melhor resultado de cada fonte
            web_results    = web_results[:1]
            fav_results    = fav_results[:1]
            local_results  = local_results[:1]
            site_results   = site_results[:1]
            paper_results  = paper_results[:1]
        elif intent == "fact-seeking":
            # Prioriza fontes locais (arquivo pessoal é mais preciso para fatos conhecidos)
            if not src_eco:
                local_results = await search_local(_effective_query)
                local_results = local_results[:5]

        # Correção ortográfica: tenta reexecutar busca local com query corrigida
        if src_eco and isinstance(eco_r, list) and not eco_r and len(_effective_query.split()) <= 2:
            cq = correct_query(_effective_query)
            if cq:
                corrected_query = cq
                try:
                    local_results = await search_local(cq)
                except Exception:
                    local_results = []

        # Lens pessoal — filtrar resultados por domínio e tipo de arquivo
        if lens_id:
            active_lens = await database.get_lens(lens_id)
        if active_lens:
            domain_list = [d.strip() for d in active_lens["domains"].split(",") if d.strip()]
            ext_list    = [e.strip().lstrip(".").lower() for e in active_lens["content_types"].split(",") if e.strip()]
            if domain_list:
                local_results = [r for r in local_results if any(d in r.url for d in domain_list)]
                site_results  = [r for r in site_results  if any(d in r.url for d in domain_list)]
                web_results   = [r for r in web_results   if any(d in r.url for d in domain_list)]
            if ext_list:
                local_results = [r for r in local_results if not r.url.startswith("file://") or _local_ext(r.url) in ext_list]

        # Faceted search: distribuição por extensão de arquivo nos resultados locais
        for r in local_results:
            ext = _local_ext(r.url)
            if ext:
                local_facets[ext] = local_facets.get(ext, 0) + 1
        local_facets = dict(sorted(local_facets.items(), key=lambda x: -x[1]))

        # Aplicar filtro de faceta (após calcular a distribuição completa)
        if facet_ext and local_results:
            local_results = [r for r in local_results if _local_ext(r.url) == facet_ext]

        # Separar web_results em P2 (favoritos) e P3 (restante)
        if web_results:
            from urllib.parse import urlparse
            fav_domains = await get_favorite_domains()
            if fav_domains:
                def _domain(url: str) -> str:
                    return (urlparse(url).hostname or "").removeprefix("www.").lower()
                fav_results  = [r for r in web_results if _domain(r.url) in fav_domains]
                web_results  = [r for r in web_results if _domain(r.url) not in fav_domains]

        total = len(web_results) + len(fav_results) + len(local_results) + len(site_results) + len(watch_later_results) + len(paper_results)
        src_label = "+".join(filter(None, [
            "web" if src_web else "",
            "local" if src_eco else "",
            "sites" if src_sites else "",
            "papers" if src_papers else "",
        ]))
        import json as _json
        await database.save_search(q, src_label or "web", total)
        await record_search_query(q)
        await log_activity("search", q, "", _json.dumps({"sources": src_label or "web", "results": total}))

        # Clarificação seletiva: resolve resultado paralelo, marca sessão se perguntou
        _clarification_question: str = ""
        if _ambiguity_future is not None:
            try:
                _amb_score, _amb_q = await asyncio.wait_for(
                    asyncio.shield(_ambiguity_future), timeout=0.1
                )
                if _amb_q and _active_session is not None:
                    _clarification_question = _amb_q
                    _active_session.asked_clarification = True
            except (asyncio.TimeoutError, Exception):
                _ambiguity_future.cancel()

        # Leituras e queries relacionadas (TF-IDF sobre snippets, sem LLM)
        _src_related = (local_results + web_results + fav_results + site_results)[:20]
        if _src_related:
            related_docs    = await suggest_related_docs(_src_related, n=5)
            related_queries = suggest_related_queries(q, _src_related, n=3)

        # Atualiza sessão de pesquisa com query atual e URLs recuperados
        _all_urls = [r.url for r in (local_results + web_results + fav_results + site_results)]
        _active_session = _session_svc.update_session(_session_id, q, _all_urls)

        # Atualiza perfil de interesse com tópicos desta busca (sem LLM, fire-and-forget)
        from services.knowledge_worker import schedule_search_update as _sched_search_update
        _all_snippets = [r.snippet for r in (local_results + web_results + fav_results)[:8] if r.snippet]
        _sched_search_update(q, _all_snippets)

        # Session insight: agenda observação espontânea quando ≥4 queries acumuladas
        from services import session_insight as _si
        _si.maybe_schedule(_session_id, _active_session.queries, _all_snippets[:6])

    has_sites = src_sites and bool(await get_all_crawl_sites())
    recent = await database.recent_searches()

    _response = templates.TemplateResponse(
        request,
        "search.html",
        {
            "web_results":          web_results,
            "fav_results":          fav_results,
            "local_results":        local_results,
            "site_results":         site_results,
            "watch_later_results":  watch_later_results,
            "paper_results":        paper_results,
            "has_more_web":         len(web_results) >= _PAGE_SIZE,
            "query":         q,
            "src_web":       bool(src_web),
            "src_eco":       bool(src_eco),
            "src_sites":     bool(src_sites),
            "src_papers":    bool(src_papers),
            "filetype":      filetype,
            "has_sites":     has_sites,
            "recent":            recent,
            "error":             error,
            "corrected_query":   corrected_query,
            "local_facets":      local_facets,
            "facet_ext":         facet_ext,
            "active_lens":       active_lens,
            "lens_id":           lens_id,
            "active_tab":        "search",
            "ollama_available":  get_ollama_status(),
            "intent":            intent,
            "intent_forced":     _intent_forced,
            "expanded_terms":    _eco_expanded,
            "no_expansion":      bool(no_expansion),
            "rewritten_query":         _rewritten_query if q else "",
            "no_rewrite":              bool(no_rewrite),
            "clarification_question":  _clarification_question if q else "",
            "profile_applied":         _profile_applied,
            "profile_source_label":    _profile.source_label if _profile_applied else "",
            "related_docs":      related_docs,
            "related_queries":   related_queries,
            "session":           _active_session,
            "voice":             _voice_texts(),
        },
    )
    if _new_cookie:
        _response.set_cookie(
            "akasha_session", _session_id,
            max_age=86400 * 7, httponly=True, samesite="lax",
        )
    return _response


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request) -> HTMLResponse:
    """Página de edição do perfil de preferências de busca."""
    from services.search_profile import load_profile as _load
    prof = await _load()
    return templates.TemplateResponse(
        request, "profile.html",
        {"profile": prof, "active_tab": "profile"},
    )


@router.post("/profile")
async def profile_save(
    request: Request,
    preferred_sources: list[str] = Form(default=[]),
) -> Response:
    """Salva preferências de fonte do perfil e redireciona de volta."""
    from fastapi.responses import RedirectResponse
    from services.search_profile import save_preferred_sources as _save
    valid = [s for s in preferred_sources if s in ("eco", "web", "sites", "papers")]
    await _save(valid)
    return RedirectResponse("/profile", status_code=303)


@router.post("/search/session/clear")
async def search_session_clear(request: Request) -> Response:
    """Encerra a sessão de pesquisa atual (botão 'encerrar' na UI)."""
    session_id = request.cookies.get("akasha_session", "")
    if session_id:
        _session_svc.clear_session(session_id)
    return Response(status_code=200)


@router.post("/search/summarize", response_class=HTMLResponse)
async def search_summarize(
    request:  Request,
    q:        str       = Form(""),
    snippet:  list[str] = Form(default=[]),
) -> HTMLResponse:
    """Fragmento HTMX: síntese opcional de snippets via LLM.

    Chamado apenas por ação explícita da usuária — nunca automaticamente.
    O LLM lê os snippets passados via form e gera orientação de leitura;
    nunca sintetiza além do que já está nos trechos recuperados.
    """
    from services.query_understanding import DEFAULT_LLM_MODEL
    summary = ""
    if q and snippet and DEFAULT_LLM_MODEL:
        summary = await summarize_snippets(q, snippet)
    return templates.TemplateResponse(
        request,
        "_search_summary.html",
        {"summary": summary, "query": q, "snippets": snippet[:8]},
    )


@router.post("/search/release-model")
async def search_release_model() -> dict:
    """Libera o modelo LLM da VRAM explicitamente (botão 'Encerrar sessão')."""
    from services.query_understanding import release_model, get_pinned_model
    model = get_pinned_model()
    await release_model()
    return {"released": model}


@router.get("/search/suggest", response_class=HTMLResponse)
async def search_suggest(request: Request, q: str = "") -> HTMLResponse:
    """Fragmento HTMX: lista de sugestões de autocomplete por histórico pessoal."""
    suggestions = await get_query_suggestions(q) if q.strip() else []
    return templates.TemplateResponse(
        request,
        "_search_suggest.html",
        {"suggestions": suggestions, "q": q},
    )


@router.get("/tags/suggest")
async def tags_suggest(tag: str = "") -> list[str]:
    """Retorna tags que co-ocorrem com `tag`, ordenadas por frequência. Usado por UIs de input."""
    if not tag.strip():
        return []
    return await get_suggested_tags(tag.strip())


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


@router.get("/insight/current")
async def insight_current(request: Request) -> dict:
    """Retorna o insight atual para a sessão (polling leve do frontend, ~10 s)."""
    from services import session_insight as _si
    session_id = request.cookies.get("akasha_session", "")
    text = _si.get_current(session_id) if session_id else None
    return {"text": text}


@router.post("/insight/dismiss")
async def insight_dismiss(request: Request) -> dict:
    """Descarta o insight atual (botão × no overlay)."""
    from services import session_insight as _si
    session_id = request.cookies.get("akasha_session", "")
    if session_id:
        _si.dismiss(session_id)
    return {"ok": True}


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
