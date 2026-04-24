"""
Carregadores de documentos para diferentes formatos.
Suporta: PDF, DOCX, TXT, MD, EPUB.
Para .md em vault Obsidian: extrai frontmatter YAML e wikilinks.
"""
from __future__ import annotations

import os
import re

from langchain_core.documents import Document
from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
)

from .errors import DocumentLoadError, FrontmatterParseError, UnsupportedFormatError


_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".epub"}

# Cobre os 4 formatos de wikilink do Obsidian:
# [[nota]], [[nota|alias]], [[nota#secção]], [[nota#secção|alias]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]")

# Diretórios a ignorar ao percorrer um vault Obsidian
_OBSIDIAN_IGNORE = {".obsidian", "templates", "attachments", ".trash"}


def load_documents(
    directory: str,
    source_type: str = "library",
) -> tuple[list[Document], list[DocumentLoadError]]:
    """
    Carrega todos os documentos suportados de um diretório (recursivo).
    source_type "vault" ativa o loader Obsidian para arquivos .md.

    Retorna (documentos_carregados, erros_por_arquivo).
    """
    if not os.path.exists(directory):
        raise FileNotFoundError(f"Diretório não encontrado: {directory}")

    documents: list[Document] = []
    errors: list[DocumentLoadError] = []

    ignore_dirs = {".mnemosyne"}
    if source_type == "vault":
        ignore_dirs |= _OBSIDIAN_IGNORE

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for filename in sorted(files):
            _, ext = os.path.splitext(filename.lower())
            if ext not in _SUPPORTED_EXTENSIONS:
                continue
            file_path = os.path.join(root, filename)
            try:
                docs = _load_file(file_path, source_type=source_type)
                documents.extend(docs)
            except DocumentLoadError as exc:
                errors.append(exc)

    return documents, errors


def load_single_file(
    file_path: str, source_type: str = "library"
) -> list[Document]:
    """
    Carrega um único arquivo.

    Raises:
        FileNotFoundError: se o arquivo não existir.
        UnsupportedFormatError: se o formato não for suportado.
        DocumentLoadError: se a leitura falhar.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")
    return _load_file(file_path, source_type=source_type)


def _load_file(file_path: str, source_type: str = "library") -> list[Document]:
    """
    Despacha para o loader correto e define source_type no metadata.

    Raises:
        UnsupportedFormatError: se a extensão não for suportada.
        DocumentLoadError: em qualquer falha de leitura.
    """
    _, ext = os.path.splitext(file_path.lower())

    try:
        if ext == ".pdf":
            docs = _load_pdf(file_path)
        elif ext == ".docx":
            docs = _load_docx(file_path)
        elif ext in (".txt", ".md"):
            if source_type == "vault":
                docs = _load_obsidian_note(file_path)
            else:
                docs = TextLoader(file_path, encoding="utf-8").load()
        elif ext == ".epub":
            docs = _load_epub(file_path)
        else:
            raise UnsupportedFormatError(file_path)
    except (DocumentLoadError, UnsupportedFormatError):
        raise
    except OSError as exc:
        raise DocumentLoadError(file_path, str(exc)) from exc
    except Exception as exc:
        raise DocumentLoadError(file_path, str(exc)) from exc

    for doc in docs:
        doc.metadata["source_type"] = source_type
    return docs


def _load_pdf(file_path: str) -> list[Document]:
    """Carrega PDF e garante metadata title/author nas páginas."""
    docs = PyPDFLoader(file_path).load()
    # PyPDFLoader já inclui metadata do PDF; apenas normalizar chaves
    for doc in docs:
        if "title" not in doc.metadata:
            doc.metadata["title"] = os.path.splitext(os.path.basename(file_path))[0]
        if "author" not in doc.metadata:
            doc.metadata["author"] = ""
    return docs


def _load_docx(file_path: str) -> list[Document]:
    """Carrega DOCX e extrai title/author das propriedades do documento."""
    docs = Docx2txtLoader(file_path).load()
    title = os.path.splitext(os.path.basename(file_path))[0]
    author = ""
    try:
        import docx as _docx
        d = _docx.Document(file_path)
        props = d.core_properties
        if props.title:
            title = props.title
        if props.author:
            author = props.author
    except Exception:
        pass
    for doc in docs:
        doc.metadata.setdefault("title", title)
        doc.metadata.setdefault("author", author)
    return docs


def extract_wikilinks(text: str) -> list[str]:
    """Extrai nomes de notas de todos os wikilinks presentes no texto."""
    return [m.group(1).strip() for m in _WIKILINK_RE.finditer(text)]


def _load_obsidian_note(file_path: str) -> list[Document]:
    """
    Carrega uma nota Obsidian (.md) com:
    - Frontmatter YAML (title, tags, aliases)
    - Wikilinks extraídos como metadata
    - Chunking por cabeçalho ##: uma nota vira 1 ou N documentos por secção
    - Notas com menos de 50 chars de corpo são ignoradas

    Raises:
        DocumentLoadError: se o arquivo não puder ser lido.
        FrontmatterParseError: se o frontmatter for inválido (capturado internamente).
    """
    try:
        raw_text = open(file_path, encoding="utf-8", errors="ignore").read()
    except OSError as exc:
        raise DocumentLoadError(file_path, str(exc)) from exc

    # Extrair frontmatter
    fm: dict = {}
    body = raw_text
    try:
        import frontmatter as _fm  # python-frontmatter
        post = _fm.loads(raw_text)
        fm = dict(post.metadata)
        body = post.content
    except Exception:
        pass  # sem frontmatter ou erro de parse: usa texto bruto

    title = str(fm.get("title", "")) or os.path.splitext(os.path.basename(file_path))[0]
    tags: list[str] = []
    raw_tags = fm.get("tags", [])
    if isinstance(raw_tags, list):
        tags = [str(t) for t in raw_tags]
    elif isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

    aliases: list[str] = []
    raw_aliases = fm.get("aliases", [])
    if isinstance(raw_aliases, list):
        aliases = [str(a) for a in raw_aliases]
    elif isinstance(raw_aliases, str):
        aliases = [raw_aliases]

    wikilinks = extract_wikilinks(body)

    base_meta = {
        "source": file_path,
        "title": title,
        "tags": ", ".join(tags),
        "aliases": ", ".join(aliases),
        "wikilinks": ", ".join(wikilinks),
    }

    # Chunking por cabeçalho ## (nível 2)
    sections = _split_by_heading(body, title)

    documents: list[Document] = []
    for sec_title, sec_body in sections:
        sec_body = sec_body.strip()
        if len(sec_body) < 50:
            continue
        meta = {**base_meta, "section": sec_title}
        documents.append(Document(page_content=sec_body, metadata=meta))

    return documents


def _split_by_heading(text: str, fallback_title: str) -> list[tuple[str, str]]:
    """
    Divide texto por cabeçalhos ## (nível 2).
    Retorna lista de (título_da_secção, corpo).
    Se não houver cabeçalhos, retorna o texto inteiro com fallback_title.
    """
    lines = text.splitlines()
    sections: list[tuple[str, str]] = []
    current_title = fallback_title
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("## "):
            if current_lines:
                sections.append((current_title, "\n".join(current_lines)))
            current_title = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_title, "\n".join(current_lines)))

    return sections if sections else [(fallback_title, text)]


def _load_epub(file_path: str) -> list[Document]:
    """
    Carrega um EPUB e retorna 1 Document por capítulo com metadata title/author/chapter.
    Capítulos com menos de 100 chars (capa, índice) são ignorados.

    Raises:
        DocumentLoadError: se ebooklib ou BeautifulSoup não estiver disponível ou falhar.
    """
    try:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise DocumentLoadError(
            file_path,
            f"Dependências em falta para EPUB: {exc}. "
            "Instale com: pip install ebooklib beautifulsoup4",
        ) from exc

    try:
        book = epub.read_epub(file_path, options={"ignore_ncx": True})
    except Exception as exc:
        raise DocumentLoadError(file_path, f"Falha ao abrir EPUB: {exc}") from exc

    title = ""
    author = ""
    try:
        title_meta = book.get_metadata("DC", "title")
        if title_meta:
            title = title_meta[0][0]
        creator_meta = book.get_metadata("DC", "creator")
        if creator_meta:
            author = creator_meta[0][0]
    except Exception:
        pass

    documents: list[Document] = []
    chapter_num = 0

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        try:
            soup = BeautifulSoup(item.get_content(), "lxml")
            text = soup.get_text(separator="\n", strip=True)
        except Exception:
            continue

        if len(text) < 100:
            continue

        chapter_num += 1
        chapter_title = ""
        heading = soup.find(["h1", "h2", "h3"])
        if heading:
            chapter_title = heading.get_text(strip=True)

        documents.append(
            Document(
                page_content=text,
                metadata={
                    "source": file_path,
                    "title": title,
                    "author": author,
                    "chapter": chapter_num,
                    "chapter_title": chapter_title,
                },
            )
        )

    return documents
