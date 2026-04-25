"""
AKASHA — Router de artigos científicos
POST /papers/download — baixa PDF e arquiva em {archive_path}/Papers/.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

import config

router = APIRouter()


class _DownloadBody(BaseModel):
    title:      str
    source_url: str
    arxiv_id:   str | None = None
    doi:        str | None = None
    pdf_url:    str | None = None
    authors:    str = ""
    year:       int | None = None


@router.post("/papers/download")
async def download_paper(body: _DownloadBody) -> Response:
    """
    Baixa o PDF (url direta → arXiv → Unpaywall), extrai Markdown e arquiva
    em {archive_path}/Papers/. Retorna 200 OK ou 500 com mensagem de erro.
    """
    if not config.ARCHIVE_PATH:
        return Response(
            content="ARCHIVE_PATH não configurado — configure no HUB.",
            status_code=500,
        )

    from services.paper_download import download_pdf, pdf_to_markdown
    from services.archiver import archive_pdf

    try:
        result = await download_pdf(
            arxiv_id=body.arxiv_id,
            doi=body.doi,
            pdf_url=body.pdf_url,
        )
    except RuntimeError as exc:
        return Response(content=str(exc), status_code=500)

    try:
        md = await __import__("asyncio").to_thread(pdf_to_markdown, result.pdf_bytes)
    except RuntimeError as exc:
        return Response(content=str(exc), status_code=500)

    try:
        await archive_pdf(
            content_md=md,
            title=body.title,
            authors=body.authors,
            year=body.year,
            doi=body.doi,
            arxiv_id=body.arxiv_id,
            source_url=body.source_url,
            archive_path=str(config.ARCHIVE_PATH),
        )
    except OSError as exc:
        return Response(content=f"Erro ao salvar: {exc}", status_code=500)

    return Response(status_code=200)
