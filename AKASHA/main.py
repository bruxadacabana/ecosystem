"""
AKASHA — Ponto de entrada
FastAPI app + lifespan: inicializa DB e registra no ecossistema.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
import database
from services.log_buffer import attach_to_root as _attach_log_buffer

_attach_log_buffer()  # buffer circular ativo desde o startup

from routers import search as search_router
from routers import system as system_router
from routers import domains as domains_router
from routers import favorites as favorites_router
from routers import crawler as crawler_router
from routers import watch_later as watch_later_router
from routers import kosmos_bridge as kosmos_bridge_router
from routers import history as history_router
from routers import papers as papers_router
from routers import downloads as downloads_router
from routers import highlights as highlights_router
from routers import lenses as lenses_router
from routers import dialogue as dialogue_router
from routers import chat as chat_router
from routers import memory as memory_router
from routers import graph as graph_router
from routers import interests as interests_router
from routers import context as context_router
from routers import suggestions as suggestions_router
from routers import settings as settings_router
from routers import friendship as friendship_router
from services.local_search import index_local_files, init_vec_index, init_spell_checker, check_inference_available
from services.crawler import crawl_pending_sites
from services.knowledge_worker import process_queue as _knowledge_process_queue, backfill_knowledge as _backfill_knowledge
from services.persona import load_persona as _load_persona, persona_rebuild_loop as _persona_loop
from services.reflection_loop import run_reflection_loop as _reflection_loop
from services.friendship_receiver import run_friendship_receiver_loop as _friendship_receiver_loop
from services.domain_suggester import check_and_suggest as _check_domain_suggestions, _SUGGESTION_INTERVAL_HOURS

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background: monitoramento de URLs da biblioteca
# ---------------------------------------------------------------------------

async def _status_writer() -> None:
    """Escreve status do processamento em background no ecosystem.json a cada 30s."""
    try:
        import sys as _sys
        _root = str(Path(__file__).parent.parent)
        if _root not in _sys.path:
            _sys.path.insert(0, _root)
        from ecosystem_client import write_section as _ws  # noqa: F401
    except ImportError:
        return

    from ecosystem_client import write_section
    from services.knowledge_worker import get_status

    while True:
        try:
            st = get_status()
            write_section("akasha", {
                "bg_processing": {
                    "knowledge_extraction": st["knowledge_extraction"],
                    "worker_active":        st["worker_active"],
                }
            })
        except Exception as exc:
            _log.debug("_status_writer: %s", exc)
        await asyncio.sleep(5)


async def _decay_scores_loop() -> None:
    """Job diário: aplica fator de decaimento EMA nos tópicos inativos há > 7 dias."""
    while True:
        await asyncio.sleep(86400)
        try:
            affected = await database.decay_old_topic_scores()
            if affected:
                _log.info("decay_scores: %d tópico(s) com score decaído.", affected)
        except Exception as exc:
            _log.warning("decay_scores: erro: %s", exc)


async def _cache_cleanup_job() -> None:
    """Job a cada 6h: remove entradas expiradas do cache de busca web (search_cache)."""
    while True:
        await asyncio.sleep(6 * 3600)
        try:
            import aiosqlite as _aiosqlite
            from config import DB_PATH as _DB_PATH
            ts_now = int(__import__("time").time())
            async with _aiosqlite.connect(_DB_PATH) as db:
                # Remove entradas novas (com query_hash) que já expiraram
                await db.execute(
                    "DELETE FROM search_cache "
                    "WHERE query_hash IS NOT NULL "
                    "AND (cached_at + ttl_hours * 3600) < ?",
                    (ts_now,),
                )
                # Remove entradas legadas (sem query_hash) com mais de 24h
                await db.execute(
                    "DELETE FROM search_cache "
                    "WHERE query_hash IS NULL "
                    "AND created_at < datetime('now', '-1 day')"
                )
                await db.commit()
        except Exception as exc:
            _log.warning("cache_cleanup_job: erro: %s", exc)


async def _domain_boost_job() -> None:
    """Job semanal: recalcula domain_boosts a partir dos últimos 90 dias de cliques."""
    while True:
        await asyncio.sleep(7 * 86400)
        try:
            import aiosqlite as _aiosqlite
            from config import DB_PATH as _DB_PATH
            from services.click_log import compute_domain_boosts as _compute
            async with _aiosqlite.connect(_DB_PATH) as db:
                n = await _compute(db)
            if n:
                _log.info("domain_boost_job: %d domínio(s) atualizados.", n)
        except Exception as exc:
            _log.warning("domain_boost_job: erro: %s", exc)


async def _pagerank_job() -> None:
    """Job semanal: recalcula a autoridade por grafo de links (page_rank).

    Lê page_links (povoado incrementalmente a cada crawl) e roda Personalized
    PageRank, gravando os scores em page_rank. Sem este job, a tabela page_rank
    ficaria vazia e o boost de autoridade em _apply_pagerank_boost seria sempre
    neutro (1.0). Roda uma vez ~5 min após o startup — tempo para o crawl inicial
    adicionar arestas frescas — e depois a cada 7 dias.
    """
    from services.pagerank import run_pagerank_refresh as _refresh_pr
    await asyncio.sleep(300)  # deixa o startup_crawl povoar o grafo antes do 1º cálculo
    while True:
        try:
            n = await _refresh_pr()
            if n:
                _log.info("pagerank_job: %d URL(s) com autoridade recalculada.", n)
            else:
                _log.debug("pagerank_job: grafo de links vazio, nada a calcular.")
        except Exception as exc:
            _log.warning("pagerank_job: erro: %s", exc)
        await asyncio.sleep(7 * 86400)


async def _domain_suggestion_loop() -> None:
    """Verifica a cada N horas se há domínios frequentes não indexados para sugerir."""
    while True:
        await asyncio.sleep(_SUGGESTION_INTERVAL_HOURS * 3600)
        try:
            n = await _check_domain_suggestions(threshold=3)
            if n:
                _log.info("domain_suggestion_loop: %d sugestão(ões) criada(s).", n)
        except Exception as exc:
            _log.warning("domain_suggestion_loop: erro: %s", exc)


async def _observer_popups_loop() -> None:
    """A cada 2h: a Akasha observa o comportamento e cria pop-ups proativos.

    Três detectores (camada assistente, P3 — nunca bloqueiam a busca):
      - zonas mortas de busca (queries repetidas sem engajamento local);
      - páginas revisitadas mas não arquivadas (oferece arquivar);
      - domínios indexados desatualizados com interesse recente (oferece recrawl).
    """
    while True:
        await asyncio.sleep(2 * 3600)
        try:
            from services.observer_popups import (
                check_search_dead_ends,
                check_stale_domains_with_interest,
                check_unarchived_frequent_visits,
            )
            n = await check_search_dead_ends()
            if n:
                _log.info("observer_popups_loop: %d zona(s) morta(s) sugerida(s).", n)
            n = await check_unarchived_frequent_visits()
            if n:
                _log.info("observer_popups_loop: %d visita(s) frequente(s) sem arquivo.", n)
            n = await check_stale_domains_with_interest()
            if n:
                _log.info("observer_popups_loop: %d domínio(s) desatualizado(s) com interesse.", n)
        except Exception as exc:
            _log.warning("observer_popups_loop: erro: %s", exc)


async def _session_gc_loop() -> None:
    """Acorda a cada 10 min: remove sessões expiradas e dispara reflexão pós-sessão."""
    while True:
        await asyncio.sleep(600)
        try:
            from services.session_memory import gc_with_reflection as _gc
            n = await _gc()
            if n:
                _log.debug("session_gc_loop: %d sessão(ões) expirada(s) processada(s).", n)
        except Exception as exc:
            _log.debug("session_gc_loop: erro: %s", exc)


async def _monitor_crawler() -> None:
    """Acorda a cada hora: crawla sites pendentes, limpa search_cache e reverifica Ollama."""
    while True:
        await asyncio.sleep(3600)
        try:
            await crawl_pending_sites()
        except Exception as exc:
            _log.warning("monitor: erro ao crawlar sites pendentes: %s", exc)
        # Limpeza de search_cache delegada ao _cache_cleanup_job (a cada 6h)
        try:
            await check_inference_available()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

async def _startup_crawl() -> None:
    """Crawla sites pendentes imediatamente no startup (sem esperar o ciclo horário).

    Isso garante que sites com last_crawled_at IS NULL (incluindo os que foram
    resetados de 'crawling') sejam rastreados assim que o app inicia.
    """
    try:
        await crawl_pending_sites()
    except Exception as exc:
        _log.warning("startup_crawl: %s", exc)


async def _ensure_db_healthy() -> None:
    """Verifica integridade do banco antes de usar. Apaga e recria se corrompido."""
    import aiosqlite
    from config import DB_PATH
    if not DB_PATH.exists():
        return
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            row = await (await db.execute("PRAGMA integrity_check")).fetchone()
            if row and row[0] != "ok":
                raise Exception(f"integrity_check: {row[0]}")
    except Exception as exc:
        _log.warning("Banco de dados corrompido — apagando e recriando: %s", exc)
        DB_PATH.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            sib = DB_PATH.parent / (DB_PATH.name + suffix)
            if sib.exists():
                sib.unlink()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # Re-registra o handler após uvicorn.config.dictConfig() ter reconfigurado o logging
    # (dictConfig reseta o root logger para WARNING, bloqueando INFO dos serviços)
    _attach_log_buffer()
    logging.getLogger().setLevel(logging.INFO)
    await _ensure_db_healthy()
    await database.init_db()
    # Sites presos em 'crawling' de um run anterior (processo encerrado antes do reset)
    # são resetados para 'idle'; em seguida dispara crawl_pending_sites() para que
    # os sites nunca rastreados (last_crawled_at IS NULL) sejam crawleados imediatamente.
    reset_count = await database.reset_stuck_crawling_sites()
    if reset_count:
        _log.info("startup: %d site(s) resetados de 'crawling' para 'idle'", reset_count)
    config.register_akasha()
    await index_local_files()
    await init_vec_index()
    init_spell_checker()
    await check_inference_available()
    asyncio.get_running_loop().create_task(_status_writer())
    asyncio.get_running_loop().create_task(_monitor_crawler())
    asyncio.get_running_loop().create_task(_startup_crawl())
    asyncio.get_running_loop().create_task(_knowledge_process_queue())
    asyncio.get_running_loop().create_task(_backfill_knowledge(config.ARCHIVE_PATH))
    asyncio.get_running_loop().create_task(_persona_loop())
    asyncio.get_running_loop().create_task(_reflection_loop())
    asyncio.get_running_loop().create_task(_friendship_receiver_loop())
    asyncio.get_running_loop().create_task(_decay_scores_loop())
    asyncio.get_running_loop().create_task(_cache_cleanup_job())
    asyncio.get_running_loop().create_task(_domain_boost_job())
    asyncio.get_running_loop().create_task(_pagerank_job())
    asyncio.get_running_loop().create_task(_session_gc_loop())
    asyncio.get_running_loop().create_task(_domain_suggestion_loop())
    asyncio.get_running_loop().create_task(_observer_popups_loop())
    yield
    # Shutdown — nada a liberar por enquanto

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AKASHA",
    description="Buscador pessoal local do ecossistema",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
)

# CORS: aceita qualquer origem — necessário para fetch da extensão Firefox/Zen
# (conteúdo de páginas externas → localhost:7071) e para o HUB (Tauri webview).
# Sem allow_credentials para evitar bloqueio de browsers com política restrita.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)

_BASE_DIR = Path(__file__).parent

app.mount("/static", StaticFiles(directory=_BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

app.include_router(search_router.router)
app.include_router(system_router.router)
app.include_router(domains_router.router)
app.include_router(favorites_router.router)
app.include_router(crawler_router.router)
app.include_router(watch_later_router.router)
app.include_router(kosmos_bridge_router.router)
app.include_router(history_router.router)
app.include_router(papers_router.router)
app.include_router(downloads_router.router)
app.include_router(highlights_router.router)
app.include_router(lenses_router.router)
app.include_router(dialogue_router.router)
app.include_router(chat_router.router)
app.include_router(memory_router.router)
app.include_router(graph_router.router)
app.include_router(interests_router.router)
app.include_router(context_router.router)
app.include_router(suggestions_router.router)
app.include_router(settings_router.router)
app.include_router(friendship_router.router)

# ---------------------------------------------------------------------------
# Rotas principais (Fase 1 — estrutura)
# As rotas de busca, downloads e torrents serão adicionadas nas próximas fases.
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    recent = await database.recent_searches()
    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "web_results":          [],
            "fav_results":          [],
            "local_results":        [],
            "site_results":         [],
            "watch_later_results":  [],
            "has_more_web":         False,
            "query":     "",
            "src_web":    True,
            "src_eco":    True,
            "src_sites":  False,
            "src_papers": False,
            "filetype":   "",
            "has_sites":  False,
            "paper_results": [],
            "recent":           recent,
            "error":            None,
            "corrected_query":  None,
            "local_facets":     {},
            "facet_ext":        "",
            "active_lens":      None,
            "lens_id":          0,
            "active_tab":       "search",
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "app": "AKASHA", "port": str(config.AKASHA_PORT)}


# ---------------------------------------------------------------------------
# Entrypoint direto (uv run main.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.AKASHA_PORT,
        reload=False,
    )
