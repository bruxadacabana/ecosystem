"""
AKASHA — Busca de artigos científicos
Semantic Scholar + arXiv + OpenAlex em paralelo; Unpaywall para PDFs abertos.
"""
from __future__ import annotations

import asyncio

import httpx
from pydantic import BaseModel

from services.web_search import SearchResult

_UNPAYWALL_EMAIL = "jenmangelo@gmail.com"

# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

class PaperResult(SearchResult):
    source:   str       = "PAPER"
    doi:      str | None = None
    arxiv_id: str | None = None
    authors:  str       = ""
    year:     int | None = None
    has_pdf:  bool      = False
    pdf_url:  str | None = None


# ---------------------------------------------------------------------------
# Semantic Scholar
# ---------------------------------------------------------------------------

_SS_BASE   = "https://api.semanticscholar.org/graph/v1"
_SS_FIELDS = "title,abstract,year,authors,externalIds,openAccessPdf"
_TIMEOUT   = 15.0


async def _search_semantic_scholar(query: str, max_results: int) -> list[PaperResult]:
    params = {
        "query":  query,
        "fields": _SS_FIELDS,
        "limit":  min(max_results, 10),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_SS_BASE}/paper/search", params=params)
            resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    results: list[PaperResult] = []
    for paper in data.get("data", []):
        ext_ids  = paper.get("externalIds") or {}
        doi      = ext_ids.get("DOI")
        arxiv_id = ext_ids.get("ArXiv")
        oa_pdf   = (paper.get("openAccessPdf") or {}).get("url")

        if arxiv_id:
            page_url = f"https://arxiv.org/abs/{arxiv_id}"
            if oa_pdf is None:
                oa_pdf = f"https://arxiv.org/pdf/{arxiv_id}"
        elif oa_pdf:
            page_url = oa_pdf
        else:
            pid = paper.get("paperId", "")
            page_url = f"https://www.semanticscholar.org/paper/{pid}"

        authors_list = paper.get("authors") or []
        authors_str  = ", ".join(a.get("name", "") for a in authors_list[:3])
        if len(authors_list) > 3:
            authors_str += " et al."

        year     = paper.get("year")
        abstract = (paper.get("abstract") or "")[:300]

        results.append(PaperResult(
            title=paper.get("title") or "(sem título)",
            url=page_url,
            snippet=abstract,
            doi=doi,
            arxiv_id=arxiv_id,
            authors=authors_str,
            year=year,
            date=str(year) if year else None,
            has_pdf=bool(oa_pdf),
            pdf_url=oa_pdf,
        ))
    return results


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

async def _search_arxiv(query: str, max_results: int) -> list[PaperResult]:
    try:
        import aioarxiv  # type: ignore[import-untyped]
    except ImportError:
        return []

    results: list[PaperResult] = []
    try:
        search = aioarxiv.Search(query=query, max_results=max_results)
        async with aioarxiv.Client() as client:
            async for paper in client.results(search):
                arxiv_id    = paper.get_short_id()
                pdf_url_val = getattr(paper, "pdf_url", None) or f"https://arxiv.org/pdf/{arxiv_id}"
                authors_list = getattr(paper, "authors", [])
                authors_str  = ", ".join(getattr(a, "name", str(a)) for a in authors_list[:3])
                if len(authors_list) > 3:
                    authors_str += " et al."
                published = getattr(paper, "published", None)
                year  = published.year if published else None
                date  = published.strftime("%Y-%m-%d") if published else None
                summary = (getattr(paper, "summary", "") or "")[:300]
                results.append(PaperResult(
                    title=paper.title,
                    url=str(paper.entry_id),
                    snippet=summary,
                    arxiv_id=arxiv_id,
                    authors=authors_str,
                    year=year,
                    date=date,
                    has_pdf=True,
                    pdf_url=str(pdf_url_val),
                ))
    except Exception:
        pass
    return results


# ---------------------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------------------

_OA_BASE   = "https://api.openalex.org"
_OA_SELECT = "id,doi,display_name,authorships,publication_year,abstract_inverted_index,primary_location,open_access"


async def _search_openalex(query: str, max_results: int) -> list[PaperResult]:
    params = {
        "search":   query,
        "per_page": min(max_results, 25),
        "select":   _OA_SELECT,
        "mailto":   _UNPAYWALL_EMAIL,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_OA_BASE}/works", params=params)
            resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    results: list[PaperResult] = []
    for work in data.get("results", []):
        doi_url = work.get("doi") or ""
        doi     = doi_url.replace("https://doi.org/", "") or None

        title = work.get("display_name") or "(sem título)"
        year  = work.get("publication_year")

        authorships  = work.get("authorships") or []
        author_names = [
            a.get("author", {}).get("display_name", "")
            for a in authorships[:3] if a.get("author")
        ]
        authors_str = ", ".join(filter(None, author_names))
        if len(authorships) > 3:
            authors_str += " et al."

        inv = work.get("abstract_inverted_index") or {}
        abstract = ""
        if inv:
            pos_map: dict[int, str] = {}
            for word, positions in inv.items():
                for p in positions:
                    pos_map[p] = word
            abstract = " ".join(pos_map[i] for i in sorted(pos_map))[:300]

        primary  = work.get("primary_location") or {}
        landing  = primary.get("landing_page_url") or (f"https://doi.org/{doi}" if doi else "")
        pdf_url  = primary.get("pdf_url") or (work.get("open_access") or {}).get("oa_url")

        arxiv_id = None
        if doi and "arxiv" in doi.lower():
            arxiv_id = doi.split("/")[-1]

        if not landing:
            continue

        results.append(PaperResult(
            title=title,
            url=landing,
            snippet=abstract,
            doi=doi,
            arxiv_id=arxiv_id,
            authors=authors_str,
            year=year,
            date=str(year) if year else None,
            has_pdf=bool(pdf_url),
            pdf_url=pdf_url or None,
            source="OPENALEX",
        ))
    return results


# ---------------------------------------------------------------------------
# Unpaywall — enriquecimento de PDF aberto por DOI
# ---------------------------------------------------------------------------

async def _enrich_unpaywall(results: list[PaperResult]) -> None:
    """Acrescenta PDF de acesso aberto via Unpaywall para resultados sem PDF. In-place."""
    needs = [r for r in results if r.doi and not r.pdf_url]
    if not needs:
        return

    async def _fetch(r: PaperResult) -> None:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"https://api.unpaywall.org/v2/{r.doi}",
                    params={"email": _UNPAYWALL_EMAIL},
                )
                if resp.status_code == 200:
                    best = resp.json().get("best_oa_location") or {}
                    pdf  = best.get("url_for_pdf") or best.get("url")
                    if pdf:
                        r.pdf_url = pdf
                        r.has_pdf = True
        except Exception:
            pass

    await asyncio.gather(*[_fetch(r) for r in needs])


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------

async def search_papers(query: str, max_results: int = 10) -> list[PaperResult]:
    """Busca paralela em Semantic Scholar + arXiv + OpenAlex; deduplica e enriquece com Unpaywall."""
    ss_res, ax_res, oa_res = await asyncio.gather(
        _search_semantic_scholar(query, max_results),
        _search_arxiv(query, max(max_results // 2, 5)),
        _search_openalex(query, max_results),
        return_exceptions=True,
    )

    combined: list[PaperResult] = []
    if isinstance(ss_res, list): combined.extend(ss_res)
    if isinstance(ax_res, list): combined.extend(ax_res)
    if isinstance(oa_res, list): combined.extend(oa_res)

    seen_arxiv: set[str] = set()
    seen_doi:   set[str] = set()
    deduped: list[PaperResult] = []
    for r in combined:
        if r.arxiv_id and r.arxiv_id in seen_arxiv:
            continue
        if r.doi and r.doi in seen_doi:
            continue
        if r.arxiv_id: seen_arxiv.add(r.arxiv_id)
        if r.doi:      seen_doi.add(r.doi)
        deduped.append(r)

    deduped = deduped[:max_results]
    await _enrich_unpaywall(deduped)
    return deduped
