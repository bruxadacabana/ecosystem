"""
AKASHA — Download de PDFs de artigos científicos
Fluxo: URL direta → arXiv → Unpaywall (REST).
Extração: pymupdf4llm com fallback pypdf.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

_UNPAYWALL_EMAIL = os.environ.get("UNPAYWALL_EMAIL", "")
_TIMEOUT_PDF     = 40.0


@dataclass
class PdfResult:
    pdf_bytes: bytes
    source:    str   # "direct" | "arxiv" | "unpaywall"


# ---------------------------------------------------------------------------
# Fontes de PDF
# ---------------------------------------------------------------------------

async def _fetch_url(url: str, client: httpx.AsyncClient) -> bytes | None:
    try:
        resp = await client.get(url, follow_redirects=True, timeout=_TIMEOUT_PDF)
        ct   = resp.headers.get("content-type", "")
        if resp.status_code == 200 and ("pdf" in ct or url.lower().endswith(".pdf")):
            return resp.content
    except httpx.RequestError:
        pass
    return None


async def _fetch_unpaywall(doi: str, client: httpx.AsyncClient) -> bytes | None:
    if not _UNPAYWALL_EMAIL:
        return None
    try:
        resp = await client.get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": _UNPAYWALL_EMAIL},
            timeout=10.0,
        )
        if resp.status_code != 200:
            return None
        for loc in resp.json().get("oa_locations", []):
            pdf_url = loc.get("url_for_pdf")
            if pdf_url:
                data = await _fetch_url(pdf_url, client)
                if data:
                    return data
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Função pública de download
# ---------------------------------------------------------------------------

async def download_pdf(
    *,
    arxiv_id: str | None = None,
    doi:      str | None = None,
    pdf_url:  str | None = None,
) -> PdfResult:
    """
    Tenta baixar o PDF na ordem: URL direta → arXiv → Unpaywall.

    Levanta:
        RuntimeError — nenhuma fonte disponível para este artigo.
    """
    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; AKASHA-paper/1.0)"},
        follow_redirects=True,
    ) as client:
        if pdf_url:
            data = await _fetch_url(pdf_url, client)
            if data:
                return PdfResult(pdf_bytes=data, source="direct")

        if arxiv_id:
            data = await _fetch_url(f"https://arxiv.org/pdf/{arxiv_id}", client)
            if data:
                return PdfResult(pdf_bytes=data, source="arxiv")

        if doi:
            data = await _fetch_unpaywall(doi, client)
            if data:
                return PdfResult(pdf_bytes=data, source="unpaywall")

    raise RuntimeError("PDF não disponível em acesso aberto para este artigo.")


# ---------------------------------------------------------------------------
# Extração PDF → Markdown
# ---------------------------------------------------------------------------

def pdf_to_markdown(pdf_bytes: bytes) -> str:
    """Converte bytes de PDF para Markdown via pymupdf4llm; fallback pypdf."""
    tmp_path: Path | None = None
    try:
        import pymupdf4llm  # type: ignore[import-untyped]
        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        tmp_path = Path(tmp)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(pdf_bytes)
            return pymupdf4llm.to_markdown(str(tmp_path))
        finally:
            tmp_path.unlink(missing_ok=True)
            tmp_path = None
    except ImportError:
        pass
    except Exception as exc:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"pymupdf4llm falhou: {exc}") from exc

    # Fallback: pypdf (texto puro sem estrutura Markdown)
    try:
        import io
        from pypdf import PdfReader  # type: ignore[import-untyped]
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages  = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
    except ImportError:
        raise RuntimeError(
            "pymupdf4llm e pypdf não instalados. "
            "Instale com: uv add pymupdf4llm"
        )
    except Exception as exc:
        raise RuntimeError(f"Falha ao extrair texto do PDF: {exc}") from exc
