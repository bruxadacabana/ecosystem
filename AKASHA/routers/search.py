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
    search_local, correct_query, get_inference_status,
    suggest_related_docs, suggest_related_queries,
)
from services.query_understanding import (
    pin_model, classify_intent, needs_rewrite, rewrite_query, score_ambiguity,
    summarize_snippets, classify_intent_lexical,
)
from services.crawler import search_sites, index_visited_page
from services.kosmos_search import search_kosmos
from services.paper_search import PaperResult, search_papers
from database import (
    get_all_crawl_sites,
    get_favorite_domains,
    search_watch_later as _db_search_wl,
    log_activity,
    record_search_query,
    get_query_suggestions,
    get_suggested_tags,
    get_top_topics,
)

router = APIRouter()
log = logging.getLogger("akasha.search")


# ---------------------------------------------------------------------------
# Priorização de índice local — AKASHA ferramenta
# ---------------------------------------------------------------------------

def _get_intent_routing(lexical_intent: str, query: str) -> dict[str, bool]:
    """Mapeia intent léxico → flags de roteamento para widgets/abas no template.

    Cada flag True indica que o widget correspondente deve ser acionado.
    Nenhuma chamada LLM — roteamento puro por regras.
    """
    q_tokens = query.lower().split()
    return {
        "wiki":        lexical_intent == "informational" and len(q_tokens) >= 2,
        "images":      lexical_intent == "visual",
        "weather":     lexical_intent == "weather",
        "translation": lexical_intent == "translation",
        "video":       lexical_intent == "video",
    }


def _diversify_by_domain(results: list, max_per_domain: int = 2) -> list:
    """Limita resultados por domínio (exploratory queries → diversidade de fontes)."""
    from urllib.parse import urlparse as _urlparse
    counts: dict[str, int] = {}
    out = []
    for r in results:
        domain = (_urlparse(getattr(r, "url", "")).hostname or "").removeprefix("www.").lower()
        if counts.get(domain, 0) < max_per_domain:
            out.append(r)
            counts[domain] = counts.get(domain, 0) + 1
    return out


_SOURCE_LABELS = ("Pessoal", "Biblioteca", "Web")


def _build_results_by_source(
    local_results: list,
    watch_later_results: list,
    kosmos_results: list,
    site_results: list,
    web_results: list,
    fav_results: list,
    paper_results: list,
) -> dict[str, list]:
    """Agrupa resultados por origem para as pills de facetação por fonte.

    Retorna dict com chave para cada fonte (lista vazia quando sem resultados).
    Chaves fixas: "Pessoal", "Biblioteca", "Web".
    """
    return {
        "Pessoal":    local_results + watch_later_results + kosmos_results,
        "Biblioteca": list(site_results),
        "Web":        web_results + fav_results + paper_results,
    }


def _local_qualifies_for_priority(
    results: list,
    min_n: int = 5,
    min_score: float = 0.0,
) -> bool:
    """True se resultados locais são suficientes para adiar a busca web.

    min_n: número mínimo de resultados locais para qualificar.
    min_score: score BM25 mínimo (0.0 = não verificado; usa contagem apenas).
    """
    if len(results) < min_n:
        return False
    if min_score > 0.0:
        qualifying = [r for r in results if getattr(r, "score", 0.0) >= min_score]
        return len(qualifying) >= min_n
    return True


def _akasha_cfg() -> dict:
    """Lê ecosystem.json["akasha"] em runtime. Nunca lança exceção."""
    try:
        import ecosystem_client as _ec  # type: ignore
        return (_ec.read_ecosystem() or {}).get("akasha", {})
    except Exception:
        return {}


def _get_local_priority_threshold() -> int:
    return max(1, int(_akasha_cfg().get("local_priority_threshold", 5)))


def _get_max_per_domain() -> int:
    """Lê max_per_domain do ecosystem.json (default 5). 0 = sem limite."""
    return max(0, int(_akasha_cfg().get("max_per_domain", 5)))


def _get_web_pages() -> int:
    """Lê web_pages do ecosystem.json (default 4, range 1–10)."""
    return max(1, min(10, int(_akasha_cfg().get("web_pages", 4))))


_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

_WIKI_CITATION_BOOST = 1.3


def _apply_wiki_citation_boost(
    results: list,
    cited_domains: set[str],
) -> list:
    """Aplica boost 1.3 em resultados cujo domínio está nas citações da Wikipedia.

    Marca `wiki_cited=True` nos resultados afetados e re-ordena por
    (posição_invertida × boost), mantendo neutros com fator 1.0.
    Retorna a lista original se cited_domains estiver vazio.
    """
    if not results or not cited_domains:
        return results
    from urllib.parse import urlparse as _up
    any_boosted = False
    scored: list[tuple] = []
    for i, r in enumerate(results):
        domain = (_up(r.url).hostname or "").removeprefix("www.").lower()
        if domain in cited_domains:
            r.wiki_cited = True
            factor = _WIKI_CITATION_BOOST
            any_boosted = True
        else:
            factor = 1.0
        scored.append((r, (1.0 / (i + 1)) * factor))
    if not any_boosted:
        return results
    scored.sort(key=lambda x: x[1], reverse=True)
    return [r for r, _ in scored]


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
    source: str = Form(""),  # "extension" quando arquivado pela extensão do browser
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

    # Sinal forte de interesse quando arquivado via extensão (usuária leu e achou relevante)
    if source == "extension":
        asyncio.create_task(_archive_extension_signals(url, page.title))

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


async def _archive_extension_signals(url: str, title: str) -> None:
    """Appraisal + memória + boost de tópicos quando arquivado pela extensão."""
    try:
        from services.affective_state import record_appraisal
        await record_appraisal(
            "user_archived", novelty=0.3, pleasantness=0.9,
            goal_relevance=0.9, coping_potential=0.9,
            event_ref=url,
        )
    except Exception as exc:
        log.debug("_archive_extension_signals: appraisal falhou: %s", exc)

    try:
        from services.personal_memory import save_memory
        content = f"Arquivei '{title}' — achei relevante o suficiente para guardar."
        await save_memory(
            type="archive", content=content,
            tags=["arquivo", "extensão"], importance=3,
        )
    except Exception as exc:
        log.debug("_archive_extension_signals: save_memory falhou: %s", exc)

    try:
        page_knowledge = await database.get_page_knowledge(url)
        if page_knowledge:
            topics: list[str] = page_knowledge.get("topics") or []
            for topic in topics:
                await database.update_topic_score(topic, delta=1.5)
    except Exception as exc:
        log.debug("_archive_extension_signals: topic boost falhou: %s", exc)


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
    no_expansion:  str = "",   # "on" = desativa expansão LLM para esta busca
    no_rewrite:    str = "",   # "on" = desativa reescrita conversacional para esta busca
    source_filter: str = "",   # "Pessoal" | "Biblioteca" | "Web" — filtrar por origem
    diversity:     int = 0,    # override de max_per_domain para esta busca (0 = usa config)
    web_pages:     int = 0,    # override de páginas web a buscar (0 = usa config)
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
    kosmos_results:      list[SearchResult] = []
    error: str | None = None
    corrected_query: str | None = None
    local_facets: dict[str, int] = {}
    active_lens: dict | None = None
    _eco_expanded:           list[str]          = []
    related_docs:            list[SearchResult] = []
    related_queries:         list[str]          = []
    _clarification_question: str               = ""
    _show_hedging_banner:    bool               = False
    _affective_curiosity:    float              = 0.0
    _lexical_intent:         str               = ""
    _web_deferred:           bool              = False
    _intent_routing:         dict[str, bool]   = {}
    related_indexed:         list[dict]        = []
    wiki_card:               dict | None       = None
    weather_card:            dict | None       = None
    translation_card:        dict | None       = None
    _results_by_source:      dict[str, list]  = {}
    _sf:                     str              = source_filter.strip() if source_filter else ""
    # intent pode vir da URL (override manual) ou do classificador automático
    _intent_forced = intent in ("navigational", "fact-seeking", "exploratory")

    # Sessão de pesquisa — cookie identifica o browser; gerado se ausente
    _session_id = request.cookies.get("akasha_session") or secrets.token_urlsafe(16)
    _new_cookie = not request.cookies.get("akasha_session")
    _active_session: _session_svc.SearchSession | None = _session_svc.get_session(_session_id)

    if q:
        # Reescrita conversacional: resolve anáforas e reescreve queries curtas.
        # Etapa 1 (regex, sem LLM, instantânea): substitui pronomes anafóricos PT
        #   pelos substantivos da última query — funciona mesmo sem Ollama.
        # Etapa 2 (LLM, opcional): reescrita semântica via Ollama quando disponível.
        _rewritten_query: str = ""
        _effective_query: str = q

        # Etapa 1 — reformulação regex de anáforas (sem LLM)
        if not no_rewrite and _active_session is not None:
            try:
                from services.session_memory import reformulate_if_anaphoric as _reform
                _rr = _reform(q, _active_session.context_queries(q))
                if _rr != q:
                    _rewritten_query = _rr
                    _effective_query = _rr
            except Exception:
                pass

        # Etapa 2 — reescrita semântica via LLM (só quando Ollama disponível
        # e a etapa 1 não produziu resultado)
        if (
            not no_rewrite
            and not _rewritten_query
            and _active_session is not None
            and _active_session.context_queries(q)
            and needs_rewrite(q)
            and get_inference_status()
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
        if get_inference_status():
            asyncio.ensure_future(pin_model())
            if not _intent_forced:
                intent_future = asyncio.ensure_future(classify_intent(_effective_query))
            # Clarificação seletiva: avalia ambiguidade em paralelo (máx 1 pergunta/sessão)
            if _active_session is not None and not _active_session.asked_clarification:
                _ambiguity_future = asyncio.ensure_future(score_ambiguity(_effective_query))

        _use_expansion = not bool(no_expansion)
        _web_deferred = False
        _lexical_intent = classify_intent_lexical(_effective_query)
        _intent_routing = _get_intent_routing(_lexical_intent, _effective_query)
        # Número de páginas a buscar: ?web_pages=N sobrescreve o config do ecosystem.json
        _n_pages = web_pages if web_pages > 0 else _get_web_pages()
        log.debug("web_pages=%d q=%r", _n_pages, q)
        try:
            # Fase 1: busca local primeiro (determina estratégia para web).
            if src_eco:
                try:
                    local_results = await search_local(
                        _effective_query, expand=_use_expansion,
                        expansion_log=_eco_expanded if _use_expansion else None,
                    )
                except RuntimeError as exc:
                    error = str(exc)

            # Se local tem resultados suficientes, adia a busca web para background.
            _web_deferred = src_web and _local_qualifies_for_priority(
                local_results, min_n=_get_local_priority_threshold(),
            )

            # Fase 2: demais fontes + web (se não adiada) em paralelo.
            # max_results=0 → retorna todos os resultados buscados (sem teto fixo).
            tasks = await asyncio.gather(
                search_web(_effective_query, max_results=0, filetype=filetype, n_pages=_n_pages)
                    if src_web and not _web_deferred else asyncio.sleep(0, result=[]),
                search_sites(_effective_query)  if src_sites  else asyncio.sleep(0, result=[]),
                search_papers(_effective_query) if src_papers else asyncio.sleep(0, result=[]),
                _db_search_wl(_effective_query),
                search_kosmos(_effective_query),
                return_exceptions=True,
            )
            web_r, sites_r, papers_r, wl_r, kosmos_r = tasks
            if isinstance(web_r,    list): web_results    = web_r
            if isinstance(sites_r,  list): site_results   = sites_r
            if isinstance(papers_r, list): paper_results  = papers_r
            if isinstance(kosmos_r, list): kosmos_results = kosmos_r
            if isinstance(wl_r,     list):
                watch_later_results = [
                    SearchResult(title=r[2] or r[1], url=r[1], snippet=r[3], source="DEPOIS")
                    for r in wl_r
                ]
            for res in tasks:
                if isinstance(res, RuntimeError):
                    error = str(res)
                    break

            # Web adiada: dispara em background para aquecer cache para a próxima busca.
            if _web_deferred:
                asyncio.create_task(
                    search_web(_effective_query, max_results=0, filetype=filetype, n_pages=_n_pages)
                )
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

        # Roteamento por intenção — afeta apresentação e ordenação no template,
        # nunca a quantidade de resultados retornados. AKASHA é amplificador, não respondedor.
        if intent == "navigational":
            log.debug("intent=navigational q=%r: apresentação destacada, sem corte de resultados", q)
        elif intent == "fact-seeking":
            # Inclui resultados locais mesmo quando src_eco não está selecionado
            if not src_eco:
                log.debug("intent=fact-seeking q=%r: adicionando resultados locais", q)
                local_results = await search_local(_effective_query)

        # Correção ortográfica: tenta reexecutar busca local com query corrigida
        if src_eco and not local_results and len(_effective_query.split()) <= 2:
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

        # Exploratory: diversifica resultados web por domínio.
        # max_per_domain lido do ecosystem.json (default 5); ?diversity=N sobrescreve por busca.
        # 0 = sem limite de resultados por domínio.
        if _lexical_intent == "exploratory" and web_results:
            _max_domain = diversity if diversity > 0 else _get_max_per_domain()
            if _max_domain > 0:
                log.debug("diversify q=%r max_per_domain=%d", q, _max_domain)
                web_results = _diversify_by_domain(web_results, max_per_domain=_max_domain)
            else:
                log.debug("diversify q=%r max_per_domain=0 (sem limite)", q)

        # Facetação por fonte — agrupa antes do filtro para preservar contagens nas pills
        _results_by_source = _build_results_by_source(
            local_results, watch_later_results, kosmos_results,
            site_results, web_results, fav_results, paper_results,
        )

        # Filtro de fonte selecionada: zera listas das outras fontes
        _sf = source_filter.strip() if source_filter else ""
        if _sf in _SOURCE_LABELS:
            if _sf == "Pessoal":
                web_results = fav_results = site_results = paper_results = []
            elif _sf == "Biblioteca":
                web_results = fav_results = local_results = watch_later_results = kosmos_results = paper_results = []
            elif _sf == "Web":
                local_results = watch_later_results = kosmos_results = site_results = []

        total = len(web_results) + len(fav_results) + len(local_results) + len(site_results) + len(watch_later_results) + len(paper_results) + len(kosmos_results)
        log.debug("resultados q=%r: web=%d fav=%d local=%d sites=%d papers=%d total=%d",
                  q, len(web_results), len(fav_results), len(local_results),
                  len(site_results), len(paper_results), total)
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

        # Leituras e queries relacionadas (TF-IDF sobre snippets + perfil de interesse, sem LLM)
        _src_related = (local_results + web_results + fav_results + site_results)[:20]
        if _src_related:
            _interest_topics = await get_top_topics(15)
            related_docs    = await suggest_related_docs(_src_related, n=5)
            related_queries = suggest_related_queries(
                q, _src_related, n=5, interest_topics=_interest_topics
            )

        # Leituras relacionadas do índice (por sobreposição de tópicos do primeiro resultado)
        try:
            _first_indexed_url: str | None = None
            for _r in (local_results + fav_results + site_results + web_results):
                if getattr(_r, "url", ""):
                    _first_indexed_url = _r.url
                    break
            if _first_indexed_url:
                _pk = await database.get_page_knowledge(_first_indexed_url)
                if _pk and _pk.get("topics"):
                    _exclude = [r.url for r in (local_results + fav_results + site_results + web_results + paper_results)[:30]]
                    related_indexed = await database.get_related_indexed_pages(
                        _first_indexed_url, _pk["topics"], _exclude, n=3
                    )
        except Exception:
            pass

        # Wikipedia knowledge card (informational + ≥2 tokens → busca assíncrona)
        if _intent_routing.get("wiki"):
            try:
                from services.wiki_card import get_wiki_card as _get_wiki
                wiki_card = await asyncio.wait_for(_get_wiki(_effective_query), timeout=6.0)
            except (asyncio.TimeoutError, Exception):
                pass

        # Cross-reference das fontes citadas com o índice local
        if wiki_card and wiki_card.get("cited_sources"):
            try:
                from urllib.parse import urlparse as _up
                _cited = wiki_card["cited_sources"]
                _indexed_map = await database.get_page_knowledge_batch(_cited)
                _indexed_urls = set(_indexed_map.keys())
                wiki_card["cited_sources_enriched"] = [
                    {
                        "url":     u,
                        "domain":  (_up(u).hostname or u).removeprefix("www."),
                        "indexed": u in _indexed_urls,
                    }
                    for u in _cited if u
                ]
                # Boost 1.3 em resultados web/favoritos citados pela Wikipedia
                _cited_domains = {
                    (_up(u).hostname or "").removeprefix("www.").lower()
                    for u in _cited if u
                }
                web_results  = _apply_wiki_citation_boost(web_results,  _cited_domains)
                fav_results  = _apply_wiki_citation_boost(fav_results,  _cited_domains)
            except Exception:
                wiki_card["cited_sources_enriched"] = []

        # Widget de clima (weather intent → geocoding + Open-Meteo)
        if _intent_routing.get("weather"):
            try:
                from services.weather_widget import (
                    get_weather_card as _get_weather,
                    extract_city as _extract_city,
                    _default_city as _def_city,
                )
                weather_card = await asyncio.wait_for(
                    _get_weather(_effective_query), timeout=8.0
                )
                # Sem resultado e sem cidade configurada → sinalizar para o template
                if weather_card is None and not _extract_city(_effective_query) and not _def_city():
                    weather_card = {"no_city": True}
                    log.debug("weather intent mas default_city vazio — exibindo banner de configuração")
            except (asyncio.TimeoutError, Exception):
                pass

        # Tradução inline (translation intent → argostranslate ou fallback LibreTranslate)
        if _intent_routing.get("translation"):
            try:
                import asyncio as _aio
                from services.translation_card import get_translation_card as _get_trans
                translation_card = await _aio.wait_for(
                    _aio.to_thread(_get_trans, _effective_query), timeout=5.0
                )
            except (asyncio.TimeoutError, Exception):
                pass

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

        # Modulação afetiva: arousal alto → hedging banner; curiosidade alta → mais queries
        try:
            from services.affective_state import get_current_state as _get_aff_state
            _aff = await _get_aff_state()
            _affective_curiosity = _aff.get("epistemic_curiosity", 0.0)
            if _aff.get("arousal", 0.0) > 0.6:
                _show_hedging_banner = True
            if _affective_curiosity > 0.6 and _src_related and len(related_queries) < 8:
                _interest_topics_ext = await get_top_topics(15)
                related_queries = suggest_related_queries(
                    q, _src_related, n=8, interest_topics=_interest_topics_ext
                )
        except Exception:
            pass

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
            "kosmos_results":       kosmos_results,
            "has_more_web":         len(web_results) >= _PAGE_SIZE,  # mostra botão "ver mais" via /search/more
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
            "local_facets":        local_facets,
            "facet_ext":           facet_ext,
            "results_by_source":   _results_by_source if q else {},
            "source_filter":       _sf,
            "active_lens":       active_lens,
            "lens_id":           lens_id,
            "active_tab":        "search",
            "inference_available":  get_inference_status(),
            "intent":            intent,
            "intent_forced":     _intent_forced,
            "lexical_intent":    _lexical_intent,
            "intent_routing":    _intent_routing,
            "web_deferred":      _web_deferred,
            "expanded_terms":    _eco_expanded,
            "no_expansion":      bool(no_expansion),
            "rewritten_query":         _rewritten_query if q else "",
            "no_rewrite":              bool(no_rewrite),
            "clarification_question":  _clarification_question if q else "",
            "profile_applied":         _profile_applied,
            "profile_source_label":    _profile.source_label if _profile_applied else "",
            "related_docs":        related_docs,
            "related_queries":     related_queries,
            "related_indexed":     related_indexed,
            "wiki_card":           wiki_card,
            "weather_card":        weather_card,
            "translation_card":    translation_card,
            "show_hedging_banner": _show_hedging_banner,
            "session":             _active_session,
            "voice":               _voice_texts(),
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


class _ClickBody(BaseModel):
    url:      str
    query:    str = ""
    position: int = 0


@router.post("/click")
async def record_click(body: _ClickBody, request: Request) -> dict:
    """Registra clique num resultado de busca para o Learning to Rank (domain_boost)."""
    session_id = request.cookies.get("akasha_session", "")
    try:
        from services.click_log import log_click
        await log_click(body.query, body.url, body.position, session_id)
    except Exception:
        pass
    return {"ok": True}


class _FetchBody(BaseModel):
    url:       str
    max_words: int = 2000


class _FetchResponse(BaseModel):
    url:        str
    title:      str
    content_md: str
    word_count: int
    error:      str | None = None


@router.get("/fetch")
async def fetch_get(url: str, max_words: int = 2000) -> _FetchResponse:
    """GET /fetch?url= — busca transiente sem salvar. Equivalente ao POST /fetch mas via query param.

    Usado pelo Mnemosyne Deep Research Mode e outras integrações que não podem enviar body JSON.
    """
    try:
        page = await fetch_and_extract(url, max_words=max_words)
        return _FetchResponse(
            url=page.url,
            title=page.title,
            content_md=page.content_md,
            word_count=page.word_count,
        )
    except httpx.HTTPStatusError as exc:
        return _FetchResponse(
            url=url, title="", content_md="", word_count=0,
            error=f"HTTP {exc.response.status_code}",
        )
    except httpx.RequestError as exc:
        return _FetchResponse(
            url=url, title="", content_md="", word_count=0,
            error=f"Erro de rede: {exc}",
        )


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
    """Retorna o insight atual para a sessão (polling leve do frontend, ~10 s).

    Prioridade: session_insight (gerado on-the-fly) > entrada de personal_memory
    ordenada por arousal × importance DESC.

    Consumidores:
    - UI da interface (cookie akasha_session presente) → consumer="ui"
    - Extensão do browser (sem cookie, cross-origin) → consumer="ext"
    Cada entrada de PM é mostrada por apenas UM consumidor — o primeiro que pede.
    O segundo recebe text=None e não exibe nada.
    """
    # Não interrompe quando o agente está em alta ativação — adia para momento calmo.
    try:
        from services.affective_state import get_current_state
        state = await get_current_state()
        if state.get("arousal", 0.0) > 0.6:
            return {"text": None, "memory_id": None, "reason": "deferred"}
    except Exception:
        pass

    from services import session_insight as _si
    session_id = request.cookies.get("akasha_session", "")
    # UI tem cookie de sessão; extensão não envia cookies (cross-origin sem credentials)
    consumer = "ui" if session_id else "ext"

    # 1. Session insight (gerado durante a sessão de busca)
    # Session insights são keyed por session_id — a extensão não tem sessão, não os recebe.
    entry = _si.get_current(session_id) if session_id else None
    if entry:
        return {"text": entry["text"], "memory_id": entry["memory_id"]}

    # 2. Fallback: entrada de personal_memory de alta saliência
    # O lock serializa o bloco "carregar próxima entrada": sem ele, UI e extensão polando
    # simultaneamente liam _pm_current=None ao mesmo tempo, chamavam mark_shown_as_overlay
    # duas vezes para a mesma entrada → duas linhas em communication_history → uma ficava
    # com feedback=NULL para sempre ("sem resposta" no HUB).
    pm_entry = _si.get_pm_current()
    if pm_entry is None:
        async with _si.pm_load_lock:
            # Double-check após adquirir o lock: outra coroutine pode ter carregado enquanto
            # esperávamos, evitando mark_shown_as_overlay duplicado.
            pm_entry = _si.get_pm_current()
            if pm_entry is None:
                # B1: poda de entradas antigas com alta entropia de Shannon
                try:
                    from services.personal_memory import prune_high_entropy_stale
                    await prune_high_entropy_stale()
                except Exception:
                    pass
                from services.personal_memory import get_next_for_overlay, mark_shown_as_overlay
                candidates = await get_next_for_overlay(5)
                for c in candidates:
                    await mark_shown_as_overlay(c["id"])
                    _si.set_pm_current(c)
                    pm_entry = c
                    break

    if pm_entry:
        # Se o outro consumidor já mostrou esta entrada, não duplicar
        if _si.pm_already_shown_by(consumer):
            return {"text": None, "memory_id": None}
        _si.mark_pm_shown(consumer)
        return {"text": pm_entry["content"], "memory_id": pm_entry["id"]}

    return {"text": None, "memory_id": None}


@router.post("/insight/dismiss")
async def insight_dismiss(request: Request) -> dict:
    """Descarta o insight atual (botão × no overlay)."""
    from services import session_insight as _si
    session_id = request.cookies.get("akasha_session", "")
    if session_id:
        _si.dismiss(session_id)
    return {"ok": True}


class _InsightFeedbackBody(BaseModel):
    memory_id: int
    feedback:  str   # "confirmed" | "dismissed"


@router.post("/insight/feedback")
async def insight_feedback(body: _InsightFeedbackBody, request: Request) -> dict:
    """Registra feedback (✓/✗) num insight já salvo em personal_memory.

    Se dismissed com importance ≥ 7, retorna ask_reason=True e original_text
    para que a interface/extensão pergunte o motivo antes de fechar o overlay.
    """
    from services import session_insight as _si
    from services.personal_memory import set_feedback as _set_feedback, get_entry_info as _get_info
    if body.feedback not in {"confirmed", "dismissed"}:
        raise HTTPException(status_code=422, detail="feedback deve ser 'confirmed' ou 'dismissed'")
    await _set_feedback(body.memory_id, body.feedback)

    entry = await _get_info(body.memory_id)
    comm_id = entry.get("comm_id") if entry else None

    if body.feedback == "confirmed":
        _si.set_pm_current(None)
        from services.knowledge_worker import on_feedback_confirmed as _on_confirmed
        _on_confirmed(body.memory_id)
        _si.on_feedback_confirmed(body.memory_id)
        if comm_id is not None:
            try:
                from ecosystem_client import update_communication_feedback  # type: ignore
                update_communication_feedback(comm_id, "confirmed")
            except Exception:
                pass
        return {"ok": True}

    # dismissed — always dismiss regardless of cookie presence
    # (cookie akasha_session não é enviado em requisições cross-origin da extensão)
    session_id = request.cookies.get("akasha_session", "")
    _si.dismiss(session_id)
    from services.knowledge_worker import on_feedback_dismissed as _on_dismissed
    _on_dismissed(body.memory_id)
    if comm_id is not None:
        try:
            from ecosystem_client import update_communication_feedback  # type: ignore
            update_communication_feedback(comm_id, "dismissed")
        except Exception:
            pass

    # Pergunta o motivo quando importance alta — re-exibe texto original acima
    importance = entry.get("importance") if entry else None
    if importance is not None and importance >= 7:
        return {
            "ok": True,
            "ask_reason": True,
            "original_text": entry["content"],
            "memory_id": body.memory_id,
        }
    return {"ok": True}


class _FeedbackReasonBody(BaseModel):
    memory_id: int
    reason:    str            # "já sabia disso" | "irrelevante agora" | "incorreto" | "outro"
    detail:    str | None = None


@router.post("/insight/feedback_reason")
async def insight_feedback_reason(body: _FeedbackReasonBody) -> dict:
    """Registra o motivo de um dismiss de alta importância.

    Salva em communication_history e em personal_memory (como nota de reflexão)
    para que a AKASHA aprenda com a quebra de expectativa.
    """
    from services.personal_memory import get_entry_info as _get_info, save_memory as _save
    entry = await _get_info(body.memory_id)
    comm_id = entry.get("comm_id") if entry else None

    detail_str = body.detail.strip() if body.detail else ""
    full_reason = f"{body.reason}: {detail_str}" if detail_str else body.reason

    if comm_id is not None:
        try:
            from ecosystem_client import update_communication_feedback  # type: ignore
            update_communication_feedback(comm_id, "dismissed", reason=full_reason)
        except Exception:
            pass

    # Reflexão sobre a quebra de expectativa — alimenta memória com peso maior
    if entry:
        try:
            original = entry["content"][:120]
            reflection = f"Marquei como importante mas foi rejeitada: \"{original}…\" — motivo: {full_reason}"
            await _save(
                type="correction",
                content=reflection,
                tags=["feedback", "quebra_expectativa"],
                importance=8,
            )
        except Exception:
            pass

    return {"ok": True}


@router.get("/search/images", response_class=HTMLResponse)
async def search_images_page(request: Request, q: str = "") -> HTMLResponse:
    """Busca de imagens: FTS5 sobre alt_text + title do índice local.

    Fallback para DDG Images se o índice local retornar <5 resultados.
    """
    local_results: list[dict] = []
    ddg_results:   list[dict] = []

    if q.strip():
        try:
            import aiosqlite
            from config import DB_PATH
            from services.image_indexer import search_images as _search_imgs
            async with aiosqlite.connect(DB_PATH) as db:
                local_results = await _search_imgs(db, q, limit=20)
        except Exception as exc:
            log.debug("search_images local error: %s", exc)

        # Fallback DDG Images quando índice local tem menos de 5 resultados
        if len(local_results) < 5:
            try:
                from ddgs import DDGS
                with DDGS() as ddg:
                    ddg_results = [
                        {
                            "img_url":  r.get("image", ""),
                            "page_url": r.get("url", ""),
                            "alt_text": r.get("title", ""),
                            "title":    r.get("title", ""),
                            "phash":    "",
                        }
                        for r in ddg.images(q, max_results=20)
                        if r.get("image")
                    ]
            except Exception as exc:
                log.debug("DDG images fallback error: %s", exc)

    return templates.TemplateResponse(
        request,
        "images.html",
        {
            "query":         q,
            "local_results": local_results,
            "ddg_results":   ddg_results,
            "active_tab":    "search",
        },
    )


@router.get("/search/videos", response_class=HTMLResponse)
async def search_videos_page(request: Request, q: str = "") -> HTMLResponse:
    """Busca de vídeos via Invidious. Abre no Invidious — sem YouTube direto."""
    video_results: list[dict] = []
    error: str | None = None

    if q.strip():
        try:
            from services.invidious import search_videos as _search_vids
            video_results, error = await asyncio.wait_for(
                _search_vids(q.strip()), timeout=10.0
            )
        except asyncio.TimeoutError:
            error = "Invidious não respondeu a tempo."
        except Exception as exc:
            log.debug("search_videos error: %s", exc)
            error = "Erro ao buscar vídeos."

    return templates.TemplateResponse(
        request,
        "videos.html",
        {
            "query":         q,
            "video_results": video_results,
            "error":         error,
            "active_tab":    "search",
        },
    )


_SEARCH_HISTORY_PAGE_SIZE = 20


def _ts_to_date_label(ts: int) -> str:
    from datetime import date, datetime, timedelta, timezone
    try:
        d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
    except Exception:
        return ""
    today = date.today()
    if d == today:
        return "Hoje"
    if d == today - timedelta(days=1):
        return "Ontem"
    return d.strftime("%d/%m/%Y")


def _ts_to_time_label(ts: int) -> str:
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M")
    except Exception:
        return ""


@router.get("/search/history", response_class=HTMLResponse)
async def search_history_page(request: Request, page: int = 1) -> HTMLResponse:
    """Lista cronológica de sessões de busca — queries feitas e links abertos."""
    page = max(1, page)
    offset = (page - 1) * _SEARCH_HISTORY_PAGE_SIZE

    import aiosqlite
    from services.click_log import get_search_sessions, count_search_sessions
    async with aiosqlite.connect(config.DB_PATH) as db:
        sessions = await get_search_sessions(db, limit=_SEARCH_HISTORY_PAGE_SIZE, offset=offset)
        total = await count_search_sessions(db)

    total_pages = max(1, (total + _SEARCH_HISTORY_PAGE_SIZE - 1) // _SEARCH_HISTORY_PAGE_SIZE)

    for s in sessions:
        s["date_label"] = _ts_to_date_label(s["session_end"])
        s["time_label"] = _ts_to_time_label(s["session_end"])
        for c in s["clicks"]:
            c["time_label"] = _ts_to_time_label(c["timestamp"])

    return templates.TemplateResponse(
        request,
        "search_history.html",
        {
            "sessions":    sessions,
            "page":        page,
            "total_pages": total_pages,
            "total":       total,
            "active_tab":  "history",
        },
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
