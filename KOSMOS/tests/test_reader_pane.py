"""
Testes para app/ui/views/reader_pane.py (KOSMOS v3, Fase 3) — texto completo.

Cobre o comportamento novo da Fase 3:
  - exibe texto completo quando content_text está presente (botão oculto);
  - exibe excerpt + botão "Carregar texto completo" quando pendente (is_scraped=0);
  - exibe aviso de falha (sem botão) quando is_scraped=-1;
  - clicar no botão emite scrape_requested(article_id, url) e desabilita o botão;
  - on_scrape_done(sucesso) recarrega o corpo com o texto completo do banco;
  - on_scrape_done(falha) mostra o aviso de falha;
  - on_scrape_done de outro artigo é ignorado.

Visibilidade é checada via isHidden() (confiável offscreen — independe de o
top-level estar mostrado, ao contrário de isVisible()).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

# qapp fixture vem do conftest.py


# ---------------------------------------------------------------------------
# Banco
# ---------------------------------------------------------------------------

def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _init_db_at(path: Path) -> None:
    import app.core.database as db_module
    with patch.object(db_module, "DB_PATH", path):
        db_module.init_db()


def _insert_feed(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "INSERT INTO feeds (url, title) VALUES (?, ?)",
        ("https://feed.com/rss", "Feed Teste"),
    )
    conn.commit()
    return cur.lastrowid


def _insert_article(
    conn: sqlite3.Connection,
    feed_id: int,
    url: str = "https://news.com/artigo",
    content_excerpt: str | None = "Resumo do feed.",
    content_text: str | None = None,
    is_scraped: int = 0,
    content_text_translated: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO articles
            (feed_id, url, title, content_excerpt, content_text, is_scraped, content_text_translated)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (feed_id, url, "Título do Artigo", content_excerpt, content_text, is_scraped,
         content_text_translated),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def env(tmp_path, qapp):
    """Banco temporário + DB_PATH patchado + ReaderPane pronta."""
    import app.core.database as db_module
    from app.ui.views.reader_pane import ReaderPane

    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    feed_id = _insert_feed(conn)

    with patch.object(db_module, "DB_PATH", db_file):
        reader = ReaderPane()
        yield reader, conn, feed_id
    conn.close()


# ---------------------------------------------------------------------------
# Renderização do corpo
# ---------------------------------------------------------------------------

def test_shows_full_text_when_present(env):
    reader, conn, fid = env
    aid = _insert_article(
        conn, fid, content_text="Corpo completo do artigo, já scrapeado.",
        is_scraped=1,
    )
    assert reader.show_article(aid)
    assert reader._body_lbl.text() == "Corpo completo do artigo, já scrapeado."
    assert reader._fulltext_btn.isHidden()
    assert reader._fulltext_status.isHidden()


def test_shows_excerpt_and_button_when_pending(env):
    reader, conn, fid = env
    aid = _insert_article(
        conn, fid, content_excerpt="Apenas o resumo.", content_text=None, is_scraped=0,
    )
    assert reader.show_article(aid)
    assert reader._body_lbl.text() == "Apenas o resumo."
    assert not reader._fulltext_btn.isHidden()       # botão oferecido
    assert reader._fulltext_status.isHidden()


def test_shows_failure_status_when_failed(env):
    reader, conn, fid = env
    aid = _insert_article(conn, fid, content_text=None, is_scraped=-1)
    assert reader.show_article(aid)
    assert reader._fulltext_btn.isHidden()           # sem botão em falha definitiva
    assert not reader._fulltext_status.isHidden()
    assert "não foi possível" in reader._fulltext_status.text().lower()


# ---------------------------------------------------------------------------
# Botão / sinal P1
# ---------------------------------------------------------------------------

def test_load_fulltext_emits_signal(env):
    reader, conn, fid = env
    aid = _insert_article(conn, fid, url="https://news.com/x", content_text=None)
    reader.show_article(aid)

    captured = []
    reader.scrape_requested.connect(lambda a, u: captured.append((a, u)))

    reader._on_load_fulltext()

    assert captured == [(aid, "https://news.com/x")]
    assert not reader._fulltext_btn.isEnabled()       # desabilita enquanto carrega


def test_load_fulltext_noop_without_article(env):
    reader, _, _ = env
    captured = []
    reader.scrape_requested.connect(lambda a, u: captured.append((a, u)))
    reader._on_load_fulltext()  # nenhum artigo aberto
    assert captured == []


# ---------------------------------------------------------------------------
# on_scrape_done
# ---------------------------------------------------------------------------

def test_on_scrape_done_success_reloads_body(env):
    reader, conn, fid = env
    aid = _insert_article(conn, fid, content_excerpt="Resumo.", content_text=None, is_scraped=0)
    reader.show_article(aid)
    assert reader._body_lbl.text() == "Resumo."

    # Simula o ScraperWorker tendo salvo o texto completo no banco
    conn.execute(
        "UPDATE articles SET content_text = ?, is_scraped = 1 WHERE id = ?",
        ("Texto completo recém-extraído.", aid),
    )
    conn.commit()

    reader.on_scrape_done(aid, True)

    assert reader._body_lbl.text() == "Texto completo recém-extraído."
    assert reader._fulltext_btn.isHidden()


def test_on_scrape_done_failure_shows_status(env):
    reader, conn, fid = env
    aid = _insert_article(conn, fid, content_text=None, is_scraped=0)
    reader.show_article(aid)

    reader.on_scrape_done(aid, False)

    assert reader._fulltext_btn.isHidden()
    assert not reader._fulltext_status.isHidden()
    assert "não foi possível" in reader._fulltext_status.text().lower()


def test_on_scrape_done_ignores_other_article(env):
    reader, conn, fid = env
    aid = _insert_article(conn, fid, content_excerpt="Resumo A.", content_text=None, is_scraped=0)
    reader.show_article(aid)

    # Evento de scraping de OUTRO artigo não deve afetar o atual
    reader.on_scrape_done(aid + 999, True)

    assert reader._body_lbl.text() == "Resumo A."
    assert not reader._fulltext_btn.isHidden()


# ---------------------------------------------------------------------------
# Tradução sob demanda (P2)
# ---------------------------------------------------------------------------

def test_translate_button_requests_translation(env):
    reader, conn, fid = env
    aid = _insert_article(conn, fid, content_text="English body text.")
    reader.show_article(aid)

    captured = []
    reader.translate_requested.connect(lambda a: captured.append(a))

    assert reader._translate_btn.text() == "Traduzir"
    reader._on_translate_clicked()

    assert captured == [aid]
    assert not reader._translate_btn.isEnabled()  # "Traduzindo…"


def test_on_article_translated_shows_translation(env):
    reader, conn, fid = env
    aid = _insert_article(conn, fid, content_text="English body text.")
    reader.show_article(aid)
    assert reader._body_lbl.text() == "English body text."

    reader.on_article_translated(aid, "Texto do corpo em português.")

    assert reader._body_lbl.text() == "Texto do corpo em português."
    assert reader._translate_btn.text() == "Ver original"


def test_translation_toggle(env):
    reader, conn, fid = env
    aid = _insert_article(conn, fid, content_text="Original EN.")
    reader.show_article(aid)
    reader.on_article_translated(aid, "Tradução PT.")
    assert reader._body_lbl.text() == "Tradução PT."

    # alterna para o original
    reader._on_translate_clicked()
    assert reader._body_lbl.text() == "Original EN."
    assert reader._translate_btn.text() == "Ver tradução"

    # alterna de volta para a tradução
    reader._on_translate_clicked()
    assert reader._body_lbl.text() == "Tradução PT."
    assert reader._translate_btn.text() == "Ver original"


def test_existing_translation_loaded_on_open(env):
    reader, conn, fid = env
    aid = _insert_article(conn, fid, content_text="EN body", content_text_translated="Corpo PT")
    reader.show_article(aid)
    # tradução já existe → botão oferece alternância, original mostrado por padrão
    assert reader._translate_btn.text() == "Ver tradução"
    assert reader._body_lbl.text() == "EN body"


def test_on_article_translated_ignores_other(env):
    reader, conn, fid = env
    aid = _insert_article(conn, fid, content_text="EN body")
    reader.show_article(aid)
    reader.on_article_translated(aid + 999, "não deve aparecer")
    assert reader._body_lbl.text() == "EN body"
