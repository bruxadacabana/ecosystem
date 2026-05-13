"""
AKASHA — Download de PDFs de artigos científicos
Fluxo: URL direta → arXiv → Unpaywall (REST).
Extração: pymupdf4llm com fallback pypdf.
"""
from __future__ import annotations

import asyncio
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx

_UNPAYWALL_EMAIL = os.environ.get("UNPAYWALL_EMAIL", "")
_TIMEOUT_PDF     = 40.0


_ISBN_RE = re.compile(
    r'(?:ISBN[-‐]?(?:13|10)?[:\s]?)?'
    r'(97[89][-\s]?\d[-\s]?\d{2,7}[-\s]?\d{1,7}[-\s]?\d'
    r'|\d{9}[\dXx])'
)
_PDF_DATE_RE = re.compile(r'D:(\d{4})')


@dataclass
class PdfResult:
    pdf_bytes: bytes
    source:    str   # "direct" | "arxiv" | "unpaywall"


@dataclass
class PdfNativeMetadata:
    """Metadados extraídos dos campos nativos do PDF via PyMuPDF (fitz)."""
    isbn:      str       = field(default="")
    publisher: str       = field(default="")
    year:      int | None = field(default=None)


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
# Metadados nativos do PDF (isbn, publisher, year)
# ---------------------------------------------------------------------------

def pdf_get_native_metadata(pdf_bytes: bytes) -> PdfNativeMetadata:
    """
    Extrai metadados nativos do PDF via fitz (PyMuPDF).

    O formato PDF armazena metadados num dicionário acessível via
    fitz.Document().metadata. Os campos disponíveis são: title, author,
    subject, keywords, creator, producer, creationDate, modDate.
    Nenhum deles tem um campo dedicado para ISBN ou publisher, então:
    - isbn: busca regex em subject, keywords e title
    - publisher: campo creator quando parece nome de editora, senão subject
    - year: extraído de creationDate (formato PDF: "D:YYYYMMDDHHMMSS")

    Retorna PdfNativeMetadata com campos vazios/None se fitz não estiver
    disponível ou se o PDF não tiver os metadados.
    """
    try:
        import fitz  # PyMuPDF — instalado como dependência do pymupdf4llm
    except ImportError:
        return PdfNativeMetadata()

    tmp_path: Path | None = None
    try:
        import io
        doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
        meta = doc.metadata or {}
        doc.close()
    except Exception:
        return PdfNativeMetadata()
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)

    isbn = ""
    publisher = ""
    year: int | None = None

    # Busca ISBN nos campos de texto livre
    for field_name in ("subject", "keywords", "title"):
        text = meta.get(field_name, "") or ""
        m = _ISBN_RE.search(text)
        if m:
            isbn = re.sub(r"[-\s]", "", m.group(1))
            break

    # Publisher: creator quando não é software (não contém "Acrobat", "Word", etc.)
    _SOFTWARE_KEYWORDS = {"acrobat", "word", "latex", "tex", "libre", "open", "foxit", "pdfmaker"}
    creator = (meta.get("creator", "") or "").strip()
    if creator and not any(sw in creator.lower() for sw in _SOFTWARE_KEYWORDS):
        publisher = creator
    else:
        # Tenta extrair de subject (ex: "Publisher: Springer Nature")
        subject = (meta.get("subject", "") or "").strip()
        pub_m = re.search(r'publisher[:\s]+(.+?)(?:\.|,|;|$)', subject, re.IGNORECASE)
        if pub_m:
            publisher = pub_m.group(1).strip()

    # Ano: de creationDate no formato PDF "D:YYYYMMDD..."
    creation_date = (meta.get("creationDate", "") or "").strip()
    m_year = _PDF_DATE_RE.search(creation_date)
    if m_year:
        try:
            year = int(m_year.group(1))
        except ValueError:
            pass

    return PdfNativeMetadata(isbn=isbn, publisher=publisher, year=year)


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
