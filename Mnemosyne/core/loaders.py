"""
Carregadores de documentos para diferentes formatos.
Suporta: PDF, DOCX, TXT, MD, EPUB.
"""
from __future__ import annotations

import os

from langchain_core.documents import Document
from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
)

from .errors import DocumentLoadError, UnsupportedFormatError


_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".epub"}


def load_documents(
    directory: str,
    source_type: str = "biblioteca",
) -> tuple[list[Document], list[DocumentLoadError]]:
    """
    Carrega todos os documentos suportados de um diretório (recursivo).

    Retorna tupla (documentos_carregados, erros_por_arquivo).
    Nunca falha por causa de um único arquivo — erros são acumulados e
    retornados para que a camada superior decida o que fazer.

    Raises:
        FileNotFoundError: se o diretório não existir.
    """
    if not os.path.exists(directory):
        raise FileNotFoundError(f"Diretório não encontrado: {directory}")

    documents: list[Document] = []
    errors: list[DocumentLoadError] = []

    for root, _, files in os.walk(directory):
        # Ignorar diretório .mnemosyne (dados internos do app)
        if ".mnemosyne" in root.split(os.sep):
            continue
        for filename in sorted(files):
            _, ext = os.path.splitext(filename.lower())
            if ext not in _SUPPORTED_EXTENSIONS:
                continue
            file_path = os.path.join(root, filename)
            try:
                docs = _load_file(file_path)
                for doc in docs:
                    doc.metadata["source_type"] = source_type
                documents.extend(docs)
            except DocumentLoadError as exc:
                errors.append(exc)

    return documents, errors


def load_single_file(
    file_path: str, source_type: str = "biblioteca"
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
    docs = _load_file(file_path)
    for doc in docs:
        doc.metadata["source_type"] = source_type
    return docs


def _load_file(file_path: str) -> list[Document]:
    """
    Despacha para o loader correto e converte exceções em DocumentLoadError.

    Raises:
        UnsupportedFormatError: se a extensão não for suportada.
        DocumentLoadError: em qualquer falha de leitura.
    """
    _, ext = os.path.splitext(file_path.lower())

    try:
        if ext == ".pdf":
            return PyPDFLoader(file_path).load()
        elif ext == ".docx":
            return Docx2txtLoader(file_path).load()
        elif ext in (".txt", ".md"):
            return TextLoader(file_path, encoding="utf-8").load()
        elif ext == ".epub":
            return _load_epub(file_path)
        else:
            raise UnsupportedFormatError(file_path)
    except (DocumentLoadError, UnsupportedFormatError):
        raise
    except OSError as exc:
        raise DocumentLoadError(file_path, str(exc)) from exc
    except Exception as exc:
        raise DocumentLoadError(file_path, str(exc)) from exc


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

    # Metadata do livro
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
        # Tentar extrair título do capítulo a partir de heading
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
