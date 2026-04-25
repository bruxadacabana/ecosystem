"""
AKASHA — Busca de artigos científicos
Semantic Scholar + arXiv em paralelo; retorna PaperResult.
"""
from __future__ import annotations

import asyncio

import httpx
from pydantic import BaseModel

from services.web_search import SearchResult

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
# Função pública
# ---------------------------------------------------------------------------

async def search_papers(query: str, max_results: int = 10) -> list[PaperResult]:
    """Busca paralela em Semantic Scholar + arXiv; deduplica por arXiv ID e DOI."""
    ss_task = _search_semantic_scholar(query, max_results)
    ax_task = _search_arxiv(query, max(max_results // 2, 5))

    ss_res, ax_res = await asyncio.gather(ss_task, ax_task, return_exceptions=True)

    combined: list[PaperResult] = []
    if isinstance(ss_res, list):
        combined.extend(ss_res)
    if isinstance(ax_res, list):
        combined.extend(ax_res)

    seen_arxiv: set[str] = set()
    seen_doi:   set[str] = set()
    deduped: list[PaperResult] = []
    for r in combined:
        if r.arxiv_id and r.arxiv_id in seen_arxiv:
            continue
        if r.doi and r.doi in seen_doi:
            continue
        if r.arxiv_id:
            seen_arxiv.add(r.arxiv_id)
        if r.doi:
            seen_doi.add(r.doi)
        deduped.append(r)

    return deduped[:max_results]
