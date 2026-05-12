"""
AKASHA — Arquivação de páginas web no formato KOSMOS estendido
Fetch via httpx; extração delegada ao ecosystem_scraper (cascata compartilhada).
"""
from __future__ import annotations

import asyncio
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse, urlencode, parse_qsl

import httpx
import trafilatura

# ---------------------------------------------------------------------------
# Imports opcionais — deduplicação e normalização de URL
# ---------------------------------------------------------------------------

try:
    from url_normalize import url_normalize as _url_normalize_lib
    _URL_NORMALIZE_AVAILABLE = True
except ImportError:
    _URL_NORMALIZE_AVAILABLE = False

try:
    from simhash import Simhash as _Simhash
    _SIMHASH_AVAILABLE = True
except ImportError:
    _SIMHASH_AVAILABLE = False

try:
    from langdetect import detect as _langdetect
    _LANGDETECT_AVAILABLE = True
except ImportError:
    _LANGDETECT_AVAILABLE = False

# Módulo compartilhado do ecossistema
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from ecosystem_scraper import extract as _cascade_extract, get_fetch_url as _get_fetch_url, get_fetch_url_fallbacks as _get_fetch_url_fallbacks

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "_", text)
    return text[:max_len].strip("_") or "pagina"


def _yaml_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _yaml_tags(tags: list[str]) -> str:
    if not tags:
        return "[]"
    items = ", ".join(t.strip() for t in tags if t.strip())
    return f"[{items}]"


def _url_fallback_title(url: str) -> str:
    parsed = urlparse(url)
    segment = parsed.path.rstrip("/").split("/")[-1]
    if segment:
        return segment.replace("-", " ").replace("_", " ").title()
    return parsed.netloc


# Domínios cujos conteúdos são considerados artigos científicos
_SCIENTIFIC_DOMAINS: frozenset[str] = frozenset({
    "arxiv.org", "ar5iv.org",
    "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov",
    "doi.org", "semanticscholar.org",
    "biorxiv.org", "medrxiv.org", "chemrxiv.org", "ssrn.com", "papers.ssrn.com",
    "plos.org", "journals.plos.org", "plosone.org",
    "nature.com", "science.org", "cell.com",
    "sciencedirect.com", "springer.com", "link.springer.com",
    "wiley.com", "onlinelibrary.wiley.com",
    "acs.org", "pubs.acs.org",
    "thelancet.com", "bmj.com", "nejm.org", "jama.jamanetwork.com",
    "academic.oup.com", "dl.acm.org", "ieeexplore.ieee.org",
    "researchgate.net", "zenodo.org",
    "scholar.google.com",
})


def _is_scientific_url(url: str) -> bool:
    """Retorna True se a URL pertence a um domínio de publicação científica."""
    try:
        hostname = (urlparse(url).hostname or "").removeprefix("www.").lower()
        if hostname in _SCIENTIFIC_DOMAINS:
            return True
        return any(hostname.endswith("." + d) for d in _SCIENTIFIC_DOMAINS)
    except Exception:
        return False


# Parâmetros de rastreamento a remover na normalização de URL
_TRACKING_PARAMS: frozenset[str] = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid",
})


# ---------------------------------------------------------------------------
# Deduplicação near-duplicate (SimHash + normalização de URL)
# ---------------------------------------------------------------------------

class NearDuplicateError(Exception):
    """Levantada quando o conteúdo a arquivar é near-duplicate de documento já existente."""
    def __init__(self, existing_url: str, existing_path: str) -> None:
        self.existing_url = existing_url
        self.existing_path = existing_path
        super().__init__(f"Near-duplicate de: {existing_url}")


def _normalize_url(url: str) -> str:
    """
    Normaliza URL para forma canônica:
      - lowercase scheme + host (via url-normalize se disponível)
      - remove parâmetros de rastreamento (utm_*, fbclid, etc.)
      - ordena os query params restantes para forma estável
    """
    try:
        if _URL_NORMALIZE_AVAILABLE:
            url = _url_normalize_lib(url)
        parsed = urlparse(url)
        clean_params = sorted(
            (k, v) for k, v in parse_qsl(parsed.query)
            if k.lower() not in _TRACKING_PARAMS
        )
        return urlunparse(parsed._replace(query=urlencode(clean_params)))
    except Exception:
        return url


def _compute_simhash(text: str) -> int | None:
    """Calcula SimHash do texto. Retorna None se a biblioteca não estiver disponível."""
    if not _SIMHASH_AVAILABLE or not text:
        return None
    try:
        return _Simhash(text).value
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

@dataclass
class FetchedPage:
    """Resultado de fetch + extração de conteúdo, sem persistência."""
    url: str
    title: str
    content_md: str
    word_count: int
    author:   str = field(default="")
    language: str = field(default="")
    pub_date: str = field(default="")  # data de publicação (trafilatura metadata.date)


@dataclass
class ArchivedPage:
    title:       str
    source:      str
    author:      str
    pub_date:    str        # data de publicação do conteúdo (YYYY-MM-DD ou vazio)
    archived_at: str        # data/hora do download (YYYY-MM-DD HH:MM)
    source_url:  str        # URL original
    language:    str
    word_count:  int
    tags:        list[str]
    notes:       str
    path:        Path
    content_md:  str = field(default="")


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------

async def fetch_and_extract(url: str, max_words: int = 0) -> FetchedPage:
    """
    Faz fetch de uma URL e extrai conteúdo em Markdown (sem salvar em disco).
    Inclui fallback Jina Reader se a cascata retornar < 100 palavras.
    max_words=0 significa sem limite de truncamento.

    Levanta:
        httpx.HTTPStatusError — status HTTP >= 400
        httpx.RequestError    — falha de rede
    """
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AKASHA-archiver/1.0)"},
    ) as client:
        # 1. Tenta proxies HTML em ordem (Medium: freedium → original)
        html = ""
        last_exc: Exception | None = None
        for fetch_url in _get_fetch_url_fallbacks(url):
            try:
                response = await client.get(fetch_url)
                response.raise_for_status()
                html = response.text
                break
            except Exception as exc:
                last_exc = exc
                continue

        # 2. Extrai metadados e conteúdo do HTML obtido (se houver)
        title:    str = _url_fallback_title(url)
        author:   str = ""
        language: str = ""
        content:  str = ""

        pub_date: str = ""
        if html:
            metadata  = trafilatura.extract_metadata(html, default_url=url)
            title     = (metadata and metadata.title)                    or title
            author    = (metadata and metadata.author)                   or ""
            language  = (metadata and getattr(metadata, "language", "")) or ""
            pub_date  = (metadata and getattr(metadata, "date", ""))     or ""
            content   = _cascade_extract(html, url, output_format="markdown")

        # 3. Jina Reader como fallback — acionado quando:
        #    (a) todos os proxies falharam (content == "") OU
        #    (b) conteúdo extraído insuficiente (< 100 palavras)
        #    Colocado ANTES de lançar exceção para dar chance ao Jina mesmo sem HTML.
        if len(content.split()) < 100:
            try:
                jina_resp = await client.get(
                    f"https://r.jina.ai/{url}",
                    headers={"Accept": "text/plain", "X-Return-Format": "markdown"},
                    timeout=20,
                )
                jina_resp.raise_for_status()
                jina_text = jina_resp.text.strip()
                if len(jina_text.split()) > len(content.split()):
                    content = jina_text
                    # Jina retorna "Title: ..." nas primeiras linhas quando extrai com sucesso
                    if title == _url_fallback_title(url):
                        for line in jina_text.splitlines()[:6]:
                            if line.startswith("Title:"):
                                title = line.removeprefix("Title:").strip()
                                break
            except Exception:
                pass  # Jina indisponível — mantém resultado parcial

        # 4. Só levanta se não obtivemos nenhum conteúdo de nenhuma fonte
        if not content and not html:
            raise last_exc or httpx.RequestError(f"Nenhuma fonte retornou conteúdo para {url}")

    words = content.split()
    if max_words > 0 and len(words) > max_words:
        content = " ".join(words[:max_words])

    return FetchedPage(
        url=url,
        title=title,
        content_md=content,
        word_count=len(words),
        author=author,
        language=language,
        pub_date=pub_date,
    )


async def archive_pdf(
    *,
    content_md:  str,
    title:       str,
    authors:     str,
    year:        int | None,
    doi:         str | None,
    arxiv_id:    str | None,
    source_url:  str,
    archive_path: str,
) -> Path:
    """
    Salva Markdown extraído de um PDF em:
        {archive_path}/Papers/{YYYY-MM-DD}_{slug}.md

    Levanta:
        OSError — falha ao gravar no disco.
    """
    now         = datetime.now()
    archived_at = now.strftime("%Y-%m-%d")
    pub_date    = str(year) if year else ""

    language = ""
    if _LANGDETECT_AVAILABLE:
        try:
            sample = content_md[:2000].strip()
            if sample:
                language = _langdetect(sample)
        except Exception:
            pass

    frontmatter = (
        f'---\n'
        f'title: "{_yaml_str(title)}"\n'
        f'source: "paper"\n'
        f'source_url: {source_url}\n'
        f'date: {pub_date}\n'
        f'archived_at: {archived_at}\n'
        f'author: "{_yaml_str(authors)}"\n'
        f'language: {language}\n'
        f'word_count: {len(content_md.split())}\n'
        f'type: scientific\n'
    )
    if doi:
        frontmatter += f'doi: "{_yaml_str(doi)}"\n'
    if arxiv_id:
        frontmatter += f'arxiv_id: {arxiv_id}\n'
    frontmatter += 'tags: []\nnotes: ""\n---\n\n'

    body = frontmatter + f'# {title}\n\n'
    if authors:
        body += f'*{authors}*\n\n'
    body += content_md

    dest_dir = Path(archive_path) / "Papers"
    dest_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = now.strftime("%Y-%m-%d")
    slug        = _slugify(title)
    dest_path   = dest_dir / f"{date_prefix}_{slug}.md"
    counter = 1
    while dest_path.exists():
        dest_path = dest_dir / f"{date_prefix}_{slug}_{counter}.md"
        counter += 1

    dest_path.write_text(body, encoding="utf-8")
    return dest_path


async def archive_url(
    url: str,
    archive_path: str,
    tags: list[str] | None = None,
    notes: str = "",
) -> ArchivedPage:
    """
    Faz fetch da URL, extrai conteúdo via cascata compartilhada e salva em:
        {archive_path}/Web/{YYYY-MM-DD}_{slug}.md

    Levanta:
        httpx.HTTPStatusError — status HTTP >= 400
        httpx.RequestError    — falha de rede
        RuntimeError          — erro ao salvar
    """
    tags = tags or []

    # Normaliza URL antes de tudo: remove tracking params, lowercase scheme+host
    url = _normalize_url(url)

    page = await fetch_and_extract(url)  # sem truncamento — arquivo completo

    # Near-duplicate check via SimHash (distância de Hamming ≤ 3 → rejeitar)
    simhash_val = _compute_simhash(page.content_md)
    if simhash_val is not None:
        import database as _db
        dup = await _db.find_near_duplicate(simhash_val)
        if dup:
            raise NearDuplicateError(existing_url=dup[0], existing_path=dup[1])

    now         = datetime.now()
    archived_at = now.strftime("%Y-%m-%d %H:%M")
    domain      = urlparse(url).netloc
    type_line   = "type: scientific\n" if _is_scientific_url(url) else ""
    pub_date    = page.pub_date or ""

    body = (
        f'---\n'
        f'title: "{_yaml_str(page.title)}"\n'
        f'source: "{_yaml_str(domain)}"\n'
        f'source_url: {url}\n'
        f'date: {pub_date}\n'
        f'archived_at: {archived_at}\n'
        f'author: "{_yaml_str(page.author)}"\n'
        f'language: {page.language}\n'
        f'word_count: {page.word_count}\n'
        f'{type_line}'
        f'tags: {_yaml_tags(tags)}\n'
        f'notes: "{_yaml_str(notes)}"\n'
        f'---\n\n'
        f'# {page.title}\n\n'
        f'{page.content_md}'
    )

    dest_dir = Path(archive_path) / "Web"
    dest_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = now.strftime("%Y-%m-%d")
    slug        = _slugify(page.title)
    dest_path   = dest_dir / f"{date_prefix}_{slug}.md"

    counter = 1
    while dest_path.exists():
        dest_path = dest_dir / f"{date_prefix}_{slug}_{counter}.md"
        counter += 1

    try:
        dest_path.write_text(body, encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Não foi possível salvar o arquivo: {exc}") from exc

    # Persiste SimHash para deduplicação de arquivamentos futuros
    if simhash_val is not None:
        import database as _db
        await _db.store_archive_simhash(simhash_val, str(dest_path), url)

    # Fire-and-forget: extrai DOIs e armazena em doc_citations em background
    asyncio.create_task(_store_dois_background(str(dest_path), page.content_md))

    return ArchivedPage(
        title=page.title, source=domain, author=page.author,
        pub_date=pub_date, archived_at=archived_at,
        source_url=url, language=page.language, word_count=page.word_count,
        tags=tags, notes=notes, path=dest_path, content_md=page.content_md,
    )


# ---------------------------------------------------------------------------
# Citation graph — extração de DOIs + enriquecimento CrossRef (background)
# ---------------------------------------------------------------------------

_DOI_RE = re.compile(r'\b(10\.\d{4,}/\S{3,})')
_DOI_STRIP = re.compile(r'[.,;:)\]}"\']+$')


async def _store_dois_background(path: str, content: str) -> None:
    """Extrai DOIs do conteúdo e armazena em doc_citations (fire-and-forget).

    Para cada DOI (máx. 8 únicos), tenta enriquecer o título via CrossRef REST API
    com timeout de 4s. Falhas são silenciosas — os DOIs sem título ainda são salvos.
    """
    raw_dois = _DOI_RE.findall(content)
    # Limpa trailing punctuation e deduplica preservando ordem
    seen: set[str] = set()
    dois: list[str] = []
    for d in raw_dois:
        d = _DOI_STRIP.sub("", d)
        if d and d not in seen:
            seen.add(d)
            dois.append(d)
        if len(dois) >= 8:
            break
    if not dois:
        return

    citations: list[tuple[str, str]] = []
    try:
        async with httpx.AsyncClient(
            timeout=4.0,
            headers={"User-Agent": "AKASHA-archiver/1.0 (mailto:akasha@local)"},
        ) as client:
            for doi in dois:
                title = ""
                try:
                    r = await client.get(f"https://api.crossref.org/works/{doi}")
                    if r.status_code == 200:
                        msg = r.json().get("message", {})
                        titles = msg.get("title", [])
                        title = titles[0] if titles else ""
                except Exception:
                    pass
                citations.append((doi, title))
    except Exception:
        citations = [(d, "") for d in dois]

    try:
        import database as _db
        await _db.store_citations(path, citations)
    except Exception:
        pass
