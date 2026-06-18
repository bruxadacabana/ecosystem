"""
AKASHA — Busca web via SearXNG (primário) + DuckDuckGo (fallback)
Cache dois níveis: memória (LRU, max 100 entradas) + SQLite (TTL variável).
- Queries com ≥3 buscas/semana → TTL 24h; demais → TTL 1h
- Camada transparente: memória → SQLite → SearXNG/DDG
- SearXNG ativado via ecosystem.json["akasha"]["web_search_backend"]
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections import OrderedDict
from urllib.parse import quote, urlparse

log = logging.getLogger("akasha.web_search")

import aiosqlite
import httpx
from ddgs import DDGS
from pydantic import BaseModel

from config import DB_PATH
from database import get_blocked_domains

# ---------------------------------------------------------------------------
# Modelo de resultado
# ---------------------------------------------------------------------------

class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    source: str = "WEB"
    date: str | None = None
    score: float = 0.0  # BM25/relevância; 0.0 = não calculado
    wiki_cited: bool = False  # domínio citado em artigo Wikipedia relevante


# ---------------------------------------------------------------------------
# Camada 1 — cache em memória (LRU, max 100 entradas, TTL por entrada)
# ---------------------------------------------------------------------------

class _MemCache:
    """Dict LRU com TTL por entrada. Thread-safe o suficiente para asyncio."""

    def __init__(self, maxsize: int = 100) -> None:
        self._store: OrderedDict[str, tuple[list, float]] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> list | None:
        if key not in self._store:
            return None
        val, expires_at = self._store[key]
        if time.time() >= expires_at:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return val

    def set(self, key: str, val: list, ttl_s: int) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (val, time.time() + ttl_s)
        while len(self._store) > self._maxsize:
            self._store.popitem(last=False)  # descarta LRU (mais antigo)

    def clear(self) -> None:
        self._store.clear()


_mem_cache = _MemCache(maxsize=100)


def _query_hash(query: str) -> str:
    return hashlib.md5(query.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Camada 2 — cache SQLite (tabela search_cache)
# ---------------------------------------------------------------------------

async def _get_db_cache(query_hash: str) -> list[SearchResult] | None:
    """Busca no cache SQLite. None se expirado ou ausente."""
    ts_now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            """SELECT results_json, cached_at, ttl_hours
               FROM search_cache
               WHERE query_hash = ?""",
            (query_hash,),
        )).fetchone()
    if row is None:
        return None
    results_json, cached_at, ttl_hours = row
    if ts_now > cached_at + ttl_hours * 3600:
        return None  # expirado
    return [SearchResult(**r) for r in json.loads(results_json)]


async def _set_db_cache(
    query: str,
    query_hash: str,
    results: list[SearchResult],
    ttl_hours: int,
) -> None:
    """Armazena no cache SQLite (upsert por query_hash)."""
    ts_now = int(time.time())
    results_json = json.dumps([r.model_dump() for r in results])
    async with aiosqlite.connect(DB_PATH) as db:
        # Delete anterior (se existir) + Insert — simples e seguro com partial UNIQUE INDEX
        await db.execute(
            "DELETE FROM search_cache WHERE query_hash = ?",
            (query_hash,),
        )
        await db.execute(
            """INSERT INTO search_cache
               (query, sources, results_json, query_hash, cached_at, ttl_hours)
               VALUES (?, 'web', ?, ?, ?, ?)""",
            (query, results_json, query_hash, ts_now, ttl_hours),
        )
        await db.commit()


async def _get_ttl_hours(query: str) -> int:
    """Retorna TTL em horas baseado na frequência da query na última semana.

    ≥3 buscas/semana → 24h (query popular, cache mais duradouro).
    Demais → 1h (padrão).
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            row = await (await db.execute(
                """SELECT COUNT(*) FROM searches
                   WHERE query = ?
                   AND created_at > datetime('now', '-7 days')""",
                (query,),
            )).fetchone()
        if row and row[0] >= 3:
            return 24
    except Exception:
        pass
    return 1


# ---------------------------------------------------------------------------
# Deduplicação
# ---------------------------------------------------------------------------

def _normalize(url: str) -> str:
    return url.rstrip("/").lower()


def _hostname(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.").lower()


async def _filter_blocked(results: list[SearchResult]) -> list[SearchResult]:
    blocked = await get_blocked_domains()
    if not blocked:
        return results
    return [r for r in results if _hostname(r.url) not in blocked]


def _deduplicate(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    out: list[SearchResult] = []
    for r in results:
        key = _normalize(r.url)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# Filtro anti-spam
# ---------------------------------------------------------------------------

# TLDs gratuitos frequentemente abusados para SEO spam de redirecionamento.
_SPAM_TLDS: frozenset[str] = frozenset({
    ".ga", ".ml", ".cf", ".gq", ".tk",
})

# TLDs comuns e confiáveis — usados como allowlist no critério 1 (redirect spam).
# Um domínio curto com path curto SÓ é considerado redirect spam se o TLD NÃO
# estiver aqui — caso contrário sites legítimos como bbc.com/news, cnn.com/tech,
# vox.com/2026 seriam falsamente filtrados.
_COMMON_TLDS: frozenset[str] = frozenset({
    ".com", ".org", ".net", ".edu", ".gov", ".mil", ".int",
    ".io", ".co", ".dev", ".app", ".info", ".me", ".tv", ".ai",
    ".biz", ".news", ".blog", ".wiki", ".xyz", ".tech", ".online",
    # ccTLDs de países relevantes para a usuária e mainstream
    ".br", ".uk", ".us", ".ca", ".de", ".fr", ".es", ".it", ".pt",
    ".nl", ".se", ".no", ".fi", ".dk", ".jp", ".cn", ".kr", ".au",
    ".ru", ".pl", ".ch", ".at", ".be", ".ie", ".nz", ".in", ".mx",
})

# Vocabulário para detecção de títulos gerados automaticamente.
# Palavras presentes → "dicionário"; ausentes → candidatas a nonsense.
# Cobre inglês (~300), português (~200) e alguns conectivos de outras línguas.
_DICT_WORDS: frozenset[str] = frozenset({
    # inglês — top 300
    "the","be","to","of","and","a","in","that","have","it","for","not","on",
    "with","he","as","you","do","at","this","but","his","by","from","they",
    "we","say","her","she","or","an","will","my","one","all","would","there",
    "their","what","so","up","out","if","about","who","get","which","go","me",
    "when","make","can","like","time","no","just","him","know","take","people",
    "into","year","your","good","some","could","them","see","other","than",
    "then","now","look","only","come","its","over","think","also","back",
    "after","use","two","how","our","work","first","well","way","even","new",
    "want","because","any","these","give","day","most","us","great","between",
    "need","large","often","hand","high","place","hold","world","life","few",
    "north","open","seem","together","next","white","children","begin","got",
    "walk","example","ease","paper","group","always","music","those","both",
    "mark","book","letter","until","mile","river","car","feet","care","second",
    "enough","girl","young","ready","above","ever","red","list","though",
    "feel","talk","bird","soon","body","dog","family","direct","leave","song",
    "door","product","black","short","class","wind","question","happen",
    "complete","ship","area","half","rock","order","fire","south","problem",
    "piece","told","knew","pass","since","top","whole","king","space","heard",
    "best","hour","better","true","during","hundred","five","remember","step",
    "early","west","ground","interest","reach","fast","simple","several",
    "toward","war","lay","against","pattern","slow","center","love","person",
    "money","serve","appear","road","map","rain","rule","govern","pull",
    "cold","notice","voice","fall","power","town","fine","drive","print",
    "set","copy","hard","start","might","story","saw","far","sea","draw",
    "left","late","run","while","press","close","night","real","type","front",
    "watch","every","page","age","enter","share","write","read","search",
    "find","help","home","add","create","web","site","link","news","click",
    "free","online","view","download","buy","price","review","top","why",
    "where","are","has","was","been","more","much","many","such","per","each",
    "long","little","right","old","big","used","still","should","between",
    "below","country","plant","last","school","father","keep","never","start",
    "city","earth","light","thought","head","under","story","saw","left",
    "dont","wont","cant","isnt","wasnt","didnt","havent","hasnt","couldnt",
    "three","four","six","seven","eight","nine","ten","hundred","thousand",
    "million","billion","yes","yeah","okay","sure","please","thank","thanks",
    "hello","hi","bye","name","number","show","play","live","work","know",
    "may","must","let","too","very","just","also","here","there","when",
    "both","own","same","own","than","then","because","while","where","why",
    "how","again","further","once","off","against","between","through","during",
    "before","after","above","below","each","few","more","most","other","some",
    "such","than","then","these","those","until","within","without","among",
    "along","across","behind","beyond","inside","outside","around","toward",
    "upon","throughout","everybody","everyone","everything","everywhere",
    "somebody","someone","something","somewhere","nobody","nothing","nowhere",
    "anybody","anyone","anything","anywhere","else","instead","however",
    "therefore","moreover","furthermore","nevertheless","nonetheless",
    "although","despite","unless","whether","provided","assuming",
    "article","blog","page","post","guide","tutorial","review","news",
    "video","image","photo","gallery","forum","community","profile",
    "comment","reply","share","like","follow","subscribe","contact","about",
    "privacy","terms","policy","login","sign","register","account","user",
    "category","tag","archive","recent","popular","related","next","prev",
    # português — top 200
    "de","a","o","que","e","do","da","em","um","para","com","uma","os","no",
    "se","na","por","mais","as","dos","como","mas","foi","ao","ele","das",
    "tem","seu","sua","ou","ser","quando","muito","nos","já","está","eu",
    "também","pelo","pela","até","isso","ela","entre","era","depois","sem",
    "mesmo","aos","ter","seus","quem","nas","me","esse","eles","estão","você",
    "tinha","foram","essa","num","nem","suas","meu","às","minha","têm","numa",
    "pelos","elas","havia","seja","qual","será","nós","tenho","lhe","deles",
    "essas","esses","pelas","este","fosse","dele","tu","bastante","assim",
    "nosso","vos","lhes","meus","minhas","teu","tua","teus","tuas","nossos",
    "nossas","dela","delas","esta","estes","estas","aquele","aquela","aqueles",
    "aquelas","isto","aquilo","estou","estamos","fui","somos","são","foram",
    "temos","pode","podem","devem","vai","vão","todos","todas","todo","toda",
    "outro","outra","outros","outras","mesma","mesmos","mesmas","nenhum",
    "nenhuma","algum","alguma","alguns","algumas","grande","grandes",
    "pequeno","pequena","novo","nova","primeiro","primeira","último","última",
    "então","agora","aqui","lá","onde","porque","porém","portanto","além",
    "antes","dentro","fora","sobre","sob","após","desde","durante","segundo",
    "conforme","exceto","embora","caso","ano","anos","dia","dias","vez",
    "vezes","parte","partes","forma","formas","vida","tempo","estado","país",
    "países","cidade","cidades","governo","mundo","homem","homens","mulher",
    "mulheres","filho","filhos","com","foi","para","por","não","sim","tudo",
    "nada","coisa","pessoa","pessoas","lugar","lugares","dizer","fazer",
    "poder","querer","precisar","saber","ver","vir","dar","ficar","passar",
    "deixar","seguir","encontrar","parecer","falar","levar","chegar",
    "muito","pouco","bem","mal","agora","ainda","já","sempre","nunca",
    "talvez","quase","apenas","mais","menos","também","porém","pois",
    "como","quando","onde","por","para","que","quem","qual","quanto",
    "enquanto","embora","apesar","logo","então","portanto","afinal",
    # espanhol (comuns em queries mistas)
    "la","el","los","las","del","al","mi","lo","su","sus","nos","les",
    "hay","fue","han","son","una","uno","pero","sobre","desde","hasta",
    "entre","durante","este","esta","estos","estas","ese","esa","esos",
    "esas","ser","estar","tener","hacer","decir","querer","poder","ir",
    "ver","dar","saber","llevar","salir","pensar","seguir","parecer",
    "también","así","muy","bien","solo","todo","toda","todos","todas",
    # termos comuns em conteúdo legítimo que poderiam não estar no top
    "craft","crafts","crafting","crafted","knit","knitting","crochet",
    "yarn","sewing","stitch","textile","fabric","needle","thread","art",
    "arts","artist","artistic","activism","activist","protest","movement",
    "social","political","feminist","gender","culture","cultural","history",
    "historical","community","collective","design","maker","making","diy",
    "tutorial","pattern","project","handmade","creative","creativity",
    "climate","environmental","justice","rights","media","digital","data",
    "technology","science","research","study","analysis","report","survey",
    "wikipedia","bbc","nyt","guardian","npr","medium","github","twitter",
    "instagram","youtube","reddit","linkedin","facebook","google","amazon",
    "international","national","global","local","regional","official",
    "definition","meaning","example","examples","type","types","form",
    "forms","method","methods","approach","approaches","strategy","tool",
    "tools","practice","practices","resource","resources","information",
    "introduction","overview","summary","guide","handbook","manual",
    "history","origin","origins","background","context","impact","effect",
    "effects","cause","causes","reason","reasons","benefit","benefits",
    "challenge","challenges","issue","issues","problem","problems","solution",
    # universal
    "vs","via","etc","per","re","hi","ok","yes","no","one","two","three",
})

_WORD_SPLIT_RE = re.compile(r"[a-záéíóúàãâêôüçñ]+", re.IGNORECASE | re.UNICODE)


def _is_spam_result(result: SearchResult) -> bool:
    """Detecta resultados spam por três critérios independentes.

    Critério 1 — redirect spam: URL com domínio ≤ 6 chars e path ≤ 4 chars
        (padrão http://ab.cd/ef — domínio curto + path único curto).
    Critério 2 — título nonsense: proporção de palavras fora do dicionário
        > 60% quando o título tem 5+ palavras (detecta texto gerado por bot).
    Critério 3 — TLD spam: domínio em lista de TLDs gratuitos abusados.
    """
    url   = result.url   or ""
    title = result.title or ""

    parsed   = urlparse(url)
    hostname = (parsed.hostname or "").lower().removeprefix("www.")
    path     = (parsed.path or "").strip("/")

    # separa "domínio.tld" → registrable domain e TLD
    parts       = hostname.rsplit(".", 1)
    domain_name = parts[0] if len(parts) == 2 else hostname
    tld         = f".{parts[-1]}" if len(parts) >= 2 else ""

    # Critério 1: redirect spam — domínio curto + path de UM segmento curto E
    # não-vazio, em TLD incomum. O allowlist de TLDs comuns evita falsos positivos
    # em sites legítimos (bbc.com/news, cnn.com/tech, vox.com/2026, r0.com/).
    # O padrão real do redirect spam é http://ka.ga/lo, http://uzo.ae/pak —
    # domínio minúsculo + token aleatório curto + ccTLD obscuro.
    path_alnum = re.sub(r"[^a-z0-9]", "", path.lower())
    if (
        "/" not in path
        and 1 <= len(path_alnum) <= 4
        and len(domain_name) <= 6
        and tld not in _COMMON_TLDS
    ):
        log.debug("web_search: spam [crit-1 redirect] %s", url[:80])
        return True

    # Critério 3: TLD em lista de spam (O(1), verificado antes do crit-2)
    if tld in _SPAM_TLDS:
        log.debug("web_search: spam [crit-3 tld=%s] %s", tld, url[:80])
        return True

    # Critério 2: título com texto nonsense gerado automaticamente
    words = [w.lower() for w in _WORD_SPLIT_RE.findall(title) if len(w) >= 3]
    if len(words) >= 5:
        non_dict = sum(1 for w in words if w not in _DICT_WORDS)
        ratio = non_dict / len(words)
        if ratio > 0.60:
            log.debug(
                "web_search: spam [crit-2 ratio=%.0f%%] %s",
                ratio * 100, url[:80],
            )
            return True

    return False


# ---------------------------------------------------------------------------
# SearXNG — backend primário self-hosted (opcional)
# ---------------------------------------------------------------------------

def _akasha_cfg() -> dict:
    """Config da seção `akasha` do ecosystem.json (vazio em erro)."""
    try:
        from ecosystem_client import get_akasha_config as _gc  # type: ignore
        return _gc() or {}
    except Exception:
        return {}


def _get_searxng_url() -> str:
    """Lê akasha.web_search_backend do ecosystem.json. Vazio = SearXNG remoto desabilitado."""
    return (_akasha_cfg().get("web_search_backend", "") or "").rstrip("/")


# URL padrão da instância SearXNG VENDORIZADA (porta dedicada em settings.base.yml).
# É plumbing interno (porta que controlamos), não config de usuário — constante com
# override opcional via akasha.web_search_backend_vendor.
VENDOR_SEARXNG_URL = "http://127.0.0.1:8889"


def _searxng_candidates() -> list[tuple[str, str]]:
    """Candidatos SearXNG em ordem de prioridade: (label, url).

    1º remoto (`web_search_backend`); 2º local (`web_search_backend_fallback`);
    3º vendorizado (`web_search_backend_vendor` ou VENDOR_SEARXNG_URL). O vendor é
    sempre incluído como último recurso — se o processo não estiver de pé, o probe
    de saúde simplesmente o descarta.
    """
    cfg = _akasha_cfg()
    out: list[tuple[str, str]] = []
    remote = (cfg.get("web_search_backend", "") or "").rstrip("/")
    if remote:
        out.append(("remoto", remote))
    local = (cfg.get("web_search_backend_fallback", "") or "").rstrip("/")
    if local:
        out.append(("local", local))
    vendor = (cfg.get("web_search_backend_vendor", "") or VENDOR_SEARXNG_URL).rstrip("/")
    out.append(("vendor", vendor))
    return out


async def _searxng_alive(url: str) -> bool:
    """True se o SearXNG em `url` responde `/healthz` com 200 (probe rápido)."""
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            resp = await client.get(f"{url}/healthz")
        return resp.status_code == 200
    except Exception:
        return False


async def web_search_backend_status(query: str = "") -> dict:
    """Estado do backend de busca web, para o banner da página de busca.

    Retorna um dict com: qual SearXNG está servindo (remoto/local/vendor/None),
    se está degradado (um backend de maior prioridade caiu), se nenhum SearXNG
    responde, engines que não responderam na última busca (`unresponsive_engines`,
    quando `query` casa com o diagnóstico recente) e se a Marginalia está sem chave
    própria. `warn` indica se há algo a sinalizar (nenhum SearXNG, degradação, ou
    engines fora) — o banner some quando nominal.
    """
    cands = _searxng_candidates()
    first_label = cands[0][0] if cands else None
    active = await _active_searxng()
    label = active[0] if active is not None else None
    url = active[1] if active is not None else ""

    searxng_down = active is None
    # Degradado: está servindo, mas NÃO pelo backend de maior prioridade configurado.
    degraded = active is not None and label != first_label

    cfg = _akasha_cfg()
    marginalia_public = not (cfg.get("marginalia_api_key", "") or "").strip()

    # Engines sem resposta na última busca — só se o diagnóstico for desta query e recente.
    unresponsive: list[str] = []
    if query:
        diag = _LAST_WEB_DIAG
        if diag.get("query") == query and (time.time() - float(diag.get("ts", 0.0))) < _DIAG_TTL:
            unresponsive = list(diag.get("unresponsive") or [])

    status = {
        "active_label":        label,        # "remoto" | "local" | "vendor" | None
        "active_url":          url,
        "searxng_down":        searxng_down,
        "degraded":            degraded,
        "unresponsive_engines": unresponsive,
        "marginalia_public":   marginalia_public,
        "warn":                searxng_down or degraded or bool(unresponsive),
    }
    log.debug("web_search_backend_status(%r): %s", query, status)
    return status


async def _active_searxng() -> tuple[str, str] | None:
    """Escolhe o SearXNG de maior prioridade que está VIVO (probes em paralelo).

    Retorna (label, url) ou None se nenhum candidato responder. Probar em paralelo
    evita somar timeouts; a escolha respeita a ordem de prioridade dos candidatos.
    """
    cands = _searxng_candidates()
    alive = await asyncio.gather(*[_searxng_alive(u) for _, u in cands])
    for (label, url), ok in zip(cands, alive):
        if ok:
            log.debug("web_search: SearXNG ativo = %s (%s)", label, url)
            return label, url
        log.debug("web_search: SearXNG %s indisponível (%s)", label, url)
    log.warning("web_search: nenhum SearXNG disponível (remoto/local/vendor) — usando só Marginalia/mwmbl/DDG")
    return None


_FETCH_PAGE_SIZE = 25   # resultados por página no fetch paralelo
_FETCH_SEMAPHORE = asyncio.Semaphore(2)  # máx 2 páginas SearXNG simultâneas

# Diagnóstico da ÚLTIMA busca web (para o banner reportar engines que não
# responderam). Single-user/local: last-write-wins. TTL evita mostrar dado velho.
_LAST_WEB_DIAG: dict = {"query": "", "unresponsive": [], "ts": 0.0}
_DIAG_TTL = 120.0  # segundos


def get_last_web_diag() -> dict:
    """Diagnóstico da última busca SearXNG (cópia): query, unresponsive, ts."""
    return dict(_LAST_WEB_DIAG)


def _engine_name(item) -> str:
    """Extrai o nome do engine de uma entrada de `unresponsive_engines` (formato
    varia entre versões do SearXNG: ['bing','timeout'] | {'name':...} | 'bing')."""
    if isinstance(item, (list, tuple)) and item:
        return str(item[0]).strip()
    if isinstance(item, dict):
        return str(item.get("name") or item.get("engine") or "").strip()
    return str(item or "").strip()


def _parse_searxng_results(raw: list) -> list[SearchResult]:
    return [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            snippet=r.get("content") or r.get("snippet", ""),
            source="WEB",
            date=r.get("publishedDate") or r.get("published_date"),
        )
        for r in raw
        if r.get("url")
    ]


async def _fetch_searxng(
    query: str,
    max_results: int,
    base_url: str,
    n_pages: int = 1,
    lang: str = "",
) -> list[SearchResult]:
    """Busca via SearXNG JSON API, com suporte a múltiplas páginas em paralelo.

    lang: código ISO 639-1 (ex: "pt", "en"). Vazio = sem restrição de idioma.
    SearXNG aceita o param `language` para filtrar resultados por idioma.
    """
    unresponsive: list[str] = []  # engines que o SearXNG reportou como sem resposta

    async def _one_page(client: httpx.AsyncClient, pageno: int) -> list[SearchResult]:
        async with _FETCH_SEMAPHORE:
            try:
                params: dict = {"q": query, "format": "json", "pageno": pageno}
                if lang:
                    params["language"] = lang
                resp = await client.get(
                    f"{base_url}/search",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
                for u in (data.get("unresponsive_engines") or []):
                    name = _engine_name(u)
                    if name:
                        unresponsive.append(name)  # list.append é atômico (GIL)
                return _parse_searxng_results(data.get("results") or [])
            except Exception:
                return []

    async with httpx.AsyncClient(timeout=8.0) as client:
        pages = await asyncio.gather(*[_one_page(client, i + 1) for i in range(n_pages)])

    # Registra o diagnóstico desta busca (para o banner reportar engines fora).
    global _LAST_WEB_DIAG
    _LAST_WEB_DIAG = {"query": query, "unresponsive": sorted(set(unresponsive)), "ts": time.time()}

    combined: list[SearchResult] = []
    for page in pages:
        combined.extend(page)
    return combined[:max_results] if max_results > 0 else combined


# ---------------------------------------------------------------------------
# Marginalia — índice independente de web indie/nicho (API pública direta)
# ---------------------------------------------------------------------------

_MARGINALIA_TIMEOUT = 8.0

# mwmbl — índice indie comunitário (~500M URLs), grátis, sem chave. Usado como
# fallback leve: só consultado quando SearXNG+Marginalia retornam poucos resultados.
_MWMBL_TIMEOUT = 8.0
_MWMBL_FALLBACK_THRESHOLD = 10  # abaixo disto, complementa com mwmbl


def _get_marginalia_key() -> str:
    """Lê akasha.marginalia_api_key do ecosystem.json. Vazio → usa a chave pública."""
    try:
        from ecosystem_client import get_akasha_config as _gc  # type: ignore
        return ((_gc() or {}).get("marginalia_api_key", "") or "").strip()
    except Exception:
        return ""


async def _fetch_marginalia(query: str, api_key: str, max_results: int) -> list[SearchResult]:
    """Busca via API pública da Marginalia — `GET api.marginalia.nu/{key}/search/{query}`.

    A Marginalia indexa "a web pequena, antiga e estranha" (blogs pessoais, zines,
    ativismo, conteúdo não-comercial) — complementa Google/Bing com domínios de nicho.
    `key` vazio → "public" (rate limit compartilhado; 503 quando saturado, tratado como
    lista vazia). Chave própria (via contact@marginalia-search.com) dá rate limit separado.
    Falha graciosamente: nunca propaga exceção que quebre a busca.
    """
    key = (api_key or "").strip() or "public"
    count = max(5, min(max_results or 20, 100))
    url = f"https://api.marginalia.nu/{key}/search/{quote(query, safe='')}"
    try:
        async with httpx.AsyncClient(timeout=_MARGINALIA_TIMEOUT) as client:
            resp = await client.get(url, params={"count": count})
        if resp.status_code == 503:
            log.debug("web_search: Marginalia rate-limited (503) para %r", query)
            return []
        resp.raise_for_status()
        raw = resp.json().get("results") or []
    except Exception as exc:
        log.debug("web_search: Marginalia erro (%s) para %r", exc, query)
        return []
    return [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            snippet=r.get("description", ""),
            source="WEB",
        )
        for r in raw
        if r.get("url")
    ]


async def _fetch_mwmbl(query: str, max_results: int) -> list[SearchResult]:
    """Busca via API do mwmbl — `GET api.mwmbl.org/search/?s={query}` (grátis, sem chave).

    Índice independente e comunitário (~500M URLs), bom para web de nicho. Usado como
    FALLBACK leve (só quando SearXNG+Marginalia retornam pouco). Título e snippet vêm
    como fragmentos `{value, is_bold}` — reconstruídos por join. Falha graciosamente.
    """
    def _join(frags: object) -> str:
        if isinstance(frags, list):
            return "".join(f.get("value", "") for f in frags if isinstance(f, dict))
        return str(frags or "")

    try:
        async with httpx.AsyncClient(timeout=_MWMBL_TIMEOUT) as client:
            resp = await client.get("https://api.mwmbl.org/search/", params={"s": query})
        resp.raise_for_status()
        raw = resp.json()
        if not isinstance(raw, list):
            return []
    except Exception as exc:
        log.debug("web_search: mwmbl erro (%s) para %r", exc, query)
        return []
    out = [
        SearchResult(
            title=_join(r.get("title")),
            url=r.get("url", ""),
            snippet=_join(r.get("extract")),
            source="WEB",
        )
        for r in raw
        if isinstance(r, dict) and r.get("url")
    ]
    return out[:max_results] if max_results > 0 else out


def _merge_rrf(
    lists: list[list[SearchResult]],
    max_results: int,
    k: int = 60,
    weights: "list[float] | None" = None,
) -> list[SearchResult]:
    """Funde várias listas ranqueadas via Reciprocal Rank Fusion, deduplicando por URL.

    RRF score(url) = Σ_fontes peso_fonte/(k + rank). Resultados que aparecem em mais
    de uma fonte (ou bem ranqueados) sobem; URLs únicas de cada fonte são preservadas.
    `weights` (opcional, paralelo a `lists`) permite dar menos peso a fontes de menor
    qualidade (ex.: mwmbl com 0.3) sem que elas poluam o topo. Default: 1.0 cada.
    """
    scores: dict[str, float] = {}
    first: dict[str, SearchResult] = {}
    for i, results in enumerate(lists):
        w = weights[i] if weights is not None and i < len(weights) else 1.0
        for rank, r in enumerate(results):
            url = r.url
            if not url:
                continue
            scores[url] = scores.get(url, 0.0) + w / (k + rank + 1)
            first.setdefault(url, r)
    ordered = sorted(first.values(), key=lambda r: scores[r.url], reverse=True)
    return ordered[:max_results] if max_results > 0 else ordered


# ---------------------------------------------------------------------------
# DuckDuckGo
# ---------------------------------------------------------------------------

async def _fetch_ddg(query: str, max_results: int) -> list[SearchResult]:
    # DDG não suporta paginação explícita — aumentar max_results coleta mais resultados
    # internamente (a biblioteca faz várias requisições conforme necessário).
    try:
        raw = await asyncio.to_thread(
            lambda: list(DDGS().text(query, max_results=max_results))
        )
    except Exception as exc:
        raise RuntimeError(f"Falha na busca DuckDuckGo: {exc}") from exc
    return [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("href", ""),
            snippet=r.get("body", ""),
            source="WEB",
        )
        for r in raw
        if r.get("href")
    ]


# ---------------------------------------------------------------------------
# Camada de busca — SearXNG primeiro, DDG como fallback
# ---------------------------------------------------------------------------

async def _fetch_web(
    query: str,
    max_results: int,
    n_pages: int = 1,
    lang: str = "",
) -> list[SearchResult]:
    """SearXNG + Marginalia em paralelo (fundidos via RRF); DDG como fallback final.

    Estratégia (objetivo: máximo de resultados):
      1. SearXNG — fila de disponibilidade: remoto (`web_search_backend`) → local
         (`web_search_backend_fallback`) → vendorizado (porta 8889). Usa o de maior
         prioridade que estiver VIVO; n_pages em paralelo (agrega Google/Bing/etc.).
      2. Marginalia (sempre, em paralelo ao SearXNG ativo) — índice indie/nicho.
      → as duas fontes são fundidas via RRF (dedup por URL).
      3. mwmbl — complemento condicional quando há poucos resultados.
      4. DuckDuckGo — último recurso só se SearXNG E Marginalia não retornarem nada.
    """
    active = await _active_searxng()
    marg_key = _get_marginalia_key()

    tasks: list[tuple[str, "asyncio.Future"]] = []
    if active is not None:
        _label, searxng_url = active
        log.info("web_search: SearXNG %s em %s (lang=%r, n_pages=%d)", _label, searxng_url, lang, n_pages)
        tasks.append(("searxng", _fetch_searxng(query, max_results, searxng_url, n_pages=n_pages, lang=lang)))
    # Marginalia sempre roda em paralelo — complementa com web indie/nicho.
    tasks.append(("marginalia", _fetch_marginalia(query, marg_key, max_results)))

    lists: list[list[SearchResult]] = []
    gathered = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
    for (name, _), res in zip(tasks, gathered):
        if isinstance(res, Exception):
            log.debug("web_search: %s erro (%s) para %r", name, res, query)
        elif res:
            log.debug("web_search: %s retornou %d resultados para %r", name, len(res), query)
            lists.append(res)

    if lists:
        merged = _merge_rrf(lists, max_results)
        # Fallback leve: se SearXNG+Marginalia retornaram POUCO, complementar com mwmbl
        # (índice indie independente), com peso baixo no RRF para não poluir o topo.
        if len(merged) < _MWMBL_FALLBACK_THRESHOLD:
            log.debug("web_search: poucos resultados (%d) — complementando com mwmbl (%r)", len(merged), query)
            mwmbl = await _fetch_mwmbl(query, max_results)
            if mwmbl:
                log.debug("web_search: mwmbl retornou %d resultados para %r", len(mwmbl), query)
                merged = _merge_rrf([merged, mwmbl], max_results, weights=[1.0, 0.3])
        return merged

    # Nada do SearXNG/Marginalia → mwmbl como fonte indie; senão DDG.
    log.debug("web_search: SearXNG/Marginalia vazios — tentando mwmbl (%r)", query)
    mwmbl = await _fetch_mwmbl(query, max_results)
    if mwmbl:
        log.debug("web_search: mwmbl retornou %d resultados (primária) para %r", len(mwmbl), query)
        return mwmbl
    log.debug("web_search: mwmbl vazio — fallback para DDG (%r)", query)
    return await _fetch_ddg(query, max_results)


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------

_CACHE_SIZE = 100  # max resultados a cachear por query


async def _fetch_searxng_images(query: str, max: int, base_url: str) -> list[dict]:
    """Busca imagens via SearXNG JSON API com categories=images.

    Campos do resultado SearXNG para imagens:
      img_src / thumbnail_src — URL direta da imagem
      url                     — página de origem
      title                   — descrição / alt text
    """
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{base_url}/search",
                params={"q": query, "format": "json", "categories": "images"},
            )
            resp.raise_for_status()
            items = resp.json().get("results") or []
    except Exception:
        return []

    results: list[dict] = []
    for r in items:
        img_url = r.get("img_src") or r.get("thumbnail_src") or r.get("thumbnail") or ""
        page_url = r.get("url", "")
        if not img_url:
            continue
        results.append({
            "img_url":  img_url,
            "page_url": page_url,
            "alt_text": r.get("title", ""),
            "title":    r.get("title", ""),
        })
        if len(results) >= max:
            break
    return results


async def search_images_web(query: str, max: int = 20) -> list[dict]:
    """Busca imagens via SearXNG (se configurado) ou DDG Images como fallback.

    Retorna lista de dicts com: img_url, page_url, alt_text, title.
    Silenciosa em caso de falha — retorna [].

    Prioridade:
      1. SearXNG com categories=images (fila remoto→local→vendor; o que estiver vivo)
      2. DDG Images API
    """
    active = await _active_searxng()
    if active is not None:
        _label, searxng_url = active
        try:
            results = await _fetch_searxng_images(query, max, searxng_url)
            if results:
                return results
        except Exception:
            pass

    try:
        raw = await asyncio.to_thread(
            lambda: list(DDGS().images(query, max_results=max))
        )
        return [
            {
                "img_url":  r.get("image", ""),
                "page_url": r.get("url", ""),
                "alt_text": r.get("title", ""),
                "title":    r.get("title", ""),
            }
            for r in raw
            if r.get("image")
        ][:max]
    except Exception:
        return []


async def search_web(
    query: str,
    max_results: int = 0,
    offset: int = 0,
    filetype: str = "",
    n_pages: int = 1,
    lang: str = "",
) -> list[SearchResult]:
    """Busca web com cache dois níveis (memória LRU + SQLite TTL variável).

    Pipeline:
    1. Verifica cache de memória (TTL por entrada)
    2. Verifica cache SQLite (query_hash + cached_at + ttl_hours)
    3. Executa busca SearXNG/DDG com n_pages páginas paralelas
    4. Armazena em memória + SQLite

    max_results: 0 = retorna todos os resultados disponíveis (sem teto).
    n_pages: número de páginas a buscar em paralelo (default 1; configurado pelo router).
    filetype: acrescenta "filetype:{ext}" à query efetiva se não vazio.
    lang: código ISO 639-1 (ex: "pt", "en"). Vazio = sem restrição de idioma.
         Incluído na chave de cache para que buscas com filtros distintos sejam independentes.
    """
    effective_query = f"{query} filetype:{filetype}" if filetype else query
    # Chave de cache inclui lang E n_pages (BUG-025): buscas com nº de páginas
    # diferentes têm volumes diferentes, então NÃO podem compartilhar cache. Sem
    # o n_pages na chave, uma busca leve interna (n_pages=1, ex: pop-up observador)
    # envenenava o cache da busca real do usuário (n_pages=10), devolvendo ~1
    # página em vez de ~10. Ex: "python::lang=pt::p=10" ≠ "python::lang=::p=1".
    cache_key = f"{effective_query}::lang={lang}::p={n_pages}"
    qhash = _query_hash(cache_key)
    _fetch_max = min(_CACHE_SIZE, n_pages * _FETCH_PAGE_SIZE)

    def _slice(results: list[SearchResult]) -> list[SearchResult]:
        sliced = results[offset:]
        return sliced if max_results == 0 else sliced[:max_results]

    # 1. Cache de memória
    cached = _mem_cache.get(qhash)
    if cached is not None:
        log.debug("web_search: cache hit (memória) para %r lang=%r", query, lang)
        return _slice(await _filter_blocked(cached))

    # 2. Cache SQLite
    db_cached = await _get_db_cache(qhash)
    if db_cached is not None:
        ttl_hours = await _get_ttl_hours(effective_query)
        _mem_cache.set(qhash, db_cached, ttl_hours * 3600)
        return _slice(await _filter_blocked(db_cached))

    # 3. Busca real — SearXNG (n_pages paralelas) → DDG
    results = await _fetch_web(effective_query, _fetch_max, n_pages=n_pages, lang=lang)
    results = _deduplicate(results)

    # 3b. Filtro anti-spam — remove redirect spam, TLDs abusados e títulos nonsense
    before_spam = len(results)
    results = [r for r in results if not _is_spam_result(r)]
    if len(results) < before_spam:
        log.debug(
            "web_search: %d spam filtrado(s) de %r (%d → %d)",
            before_spam - len(results), query, before_spam, len(results),
        )

    # 4. Armazena em ambas as camadas
    ttl_hours = await _get_ttl_hours(effective_query)
    _mem_cache.set(qhash, results, ttl_hours * 3600)
    await _set_db_cache(cache_key, qhash, results, ttl_hours)

    final = _slice(await _filter_blocked(results))

    # Boost por qualidade de domínio (arquivos históricos) — aplicado fora do cache
    # para refletir o estado atual de domain_quality sem invalidar cache.
    try:
        from urllib.parse import urlparse as _urlparse
        from database import get_domain_quality_boosts as _get_boosts
        _domains = [(_urlparse(r.url).netloc or "").removeprefix("www.").lower() for r in final]
        _unique = list({d for d in _domains if d})
        if _unique:
            _boost_map = await _get_boosts(_unique)
            if any(v != 1.0 for v in _boost_map.values()):
                _scored = [
                    (r, (1.0 / (i + 1)) * _boost_map.get(_domains[i], 1.0))
                    for i, r in enumerate(final)
                ]
                _scored.sort(key=lambda x: x[1], reverse=True)
                final = [r for r, _ in _scored]
    except Exception:
        pass

    return final
