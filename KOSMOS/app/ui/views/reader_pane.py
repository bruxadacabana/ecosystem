"""
reader_pane.py — Painel direito: exibe o conteúdo do artigo selecionado.

Exibe metadados do cabeçalho + corpo. Se o artigo já tem texto completo
(`content_text`, scraping concluído), mostra-o; senão mostra o excerpt do feed
e um botão "Carregar texto completo" que dispara o scraping P1 via ScraperWorker
(sinal `scrape_requested`). Resultados de análise AI chegam na Fase 4.

Quando um artigo é aberto, marca-o como lido no banco (is_read=1, read_at=now).
Isso permite que a sidebar atualize os contadores de não-lidos corretamente.

O painel emite article_read(int) após marcar o artigo — a MainWindow usa esse
sinal para recarregar a sidebar.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.database import get_conn

log = logging.getLogger("kosmos.reader_pane")


def _fmt_date_full(iso: str | None) -> str:
    """ISO8601 → data legível completa: '01 Jun 2026 às 10:00'."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%-d %b %Y às %H:%M")
    except Exception:
        try:
            # Fallback sem strftime %-d (Windows não suporta)
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return iso


class ReaderPane(QWidget):
    """Painel direito: exibe artigo selecionado e gerencia estado de leitura."""

    article_read = Signal(int)  # article_id — emitido após marcar como lido
    scrape_requested = Signal(int, str)  # (article_id, url) — pedido P1 de texto completo

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_article_id: int | None = None
        self._current_url: str = ""
        self._setup_ui()
        log.debug("ReaderPane inicializada.")

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scroll area que envolve todo o conteúdo
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        # Container interno
        container = QWidget()
        scroll.setWidget(container)
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(32, 24, 32, 32)
        self._layout.setSpacing(0)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Estado inicial — placeholder
        self._placeholder = QLabel("← Selecione um artigo para ler.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setObjectName("placeholder")
        self._layout.addWidget(self._placeholder)

        # Widgets de conteúdo (ocultos no início)
        self._title_lbl = QLabel()
        self._title_lbl.setObjectName("reader_title")
        self._title_lbl.setProperty("class", "title")
        self._title_lbl.setWordWrap(True)
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._layout.addWidget(self._title_lbl)

        self._meta_lbl = QLabel()
        self._meta_lbl.setObjectName("reader_meta")
        self._meta_lbl.setProperty("class", "meta")
        self._meta_lbl.setWordWrap(True)
        self._layout.addWidget(self._meta_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("reader_sep")
        self._layout.addSpacing(12)
        self._layout.addWidget(sep)
        self._layout.addSpacing(16)
        self._sep = sep

        self._body_lbl = QLabel()
        self._body_lbl.setObjectName("reader_body")
        self._body_lbl.setWordWrap(True)
        self._body_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._body_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._layout.addWidget(self._body_lbl)

        # Botão para carregar o texto completo (scraping P1, sob demanda)
        self._fulltext_btn = QPushButton("Carregar texto completo")
        self._fulltext_btn.setObjectName("reader_fulltext_btn")
        self._fulltext_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fulltext_btn.clicked.connect(self._on_load_fulltext)
        self._layout.addSpacing(16)
        self._layout.addWidget(self._fulltext_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        # Status do scraping (carregando / falha)
        self._fulltext_status = QLabel()
        self._fulltext_status.setProperty("class", "meta")
        self._fulltext_status.setWordWrap(True)
        self._layout.addWidget(self._fulltext_status)

        self._layout.addStretch()
        self._set_content_visible(False)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def show_article(
        self,
        article_id: int,
        conn: sqlite3.Connection | None = None,
    ) -> bool:
        """Carrega e exibe o artigo; marca-o como lido no banco.

        Args:
            article_id: ID do artigo na tabela articles.
            conn:       conexão existente (testes); None → cria e fecha própria.

        Returns:
            True se o artigo foi encontrado e exibido.
        """
        _conn = conn if conn is not None else get_conn()
        should_close = conn is None
        row = None
        try:
            row = _conn.execute(
                """
                SELECT a.id, a.title, a.author, a.published_at,
                       a.article_type, a.estimated_reading_min,
                       a.language_detected, a.content_excerpt, a.is_read,
                       a.url, a.content_text, a.is_scraped,
                       COALESCE(f.title, f.url) AS feed_title,
                       f.site_url
                  FROM articles a
                  JOIN feeds f ON f.id = a.feed_id
                 WHERE a.id = ?
                """,
                (article_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            log.error("Falha ao carregar artigo %d: %s", article_id, exc)
        finally:
            if should_close and row is None:
                _conn.close()

        if row is None:
            log.warning("Artigo %d não encontrado.", article_id)
            return False

        self._current_article_id = article_id
        self._current_url = row["url"] or ""
        self._render(dict(row))

        # Marca como lido (usa a mesma conn se ainda aberta, ou abre nova)
        was_unread = not row["is_read"]
        try:
            self._mark_as_read(article_id, _conn if not should_close else None)
        finally:
            if should_close:
                _conn.close()

        if was_unread:
            log.info("Artigo %d marcado como lido.", article_id)
            self.article_read.emit(article_id)

        return True

    def clear(self) -> None:
        """Volta ao estado de placeholder (nenhum artigo selecionado)."""
        self._current_article_id = None
        self._set_content_visible(False)
        self._placeholder.show()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _render(self, data: dict) -> None:
        self._placeholder.hide()
        self._set_content_visible(True)

        self._title_lbl.setText(data.get("title") or "(sem título)")

        meta_parts: list[str] = []
        if data.get("feed_title"):
            meta_parts.append(data["feed_title"])
        if data.get("author"):
            meta_parts.append(data["author"])
        date_str = _fmt_date_full(data.get("published_at"))
        if date_str:
            meta_parts.append(date_str)
        art_type = data.get("article_type") or ""
        if art_type and art_type != "news":
            meta_parts.append(art_type.upper())
        reading = data.get("estimated_reading_min")
        if reading:
            meta_parts.append(f"{reading} min de leitura")
        self._meta_lbl.setText("  ·  ".join(meta_parts))

        self._render_body(
            content_text=(data.get("content_text") or "").strip(),
            excerpt=(data.get("content_excerpt") or "").strip(),
            is_scraped=int(data.get("is_scraped") or 0),
        )

        log.debug("Artigo renderizado: id=%d título='%s'", data["id"], data.get("title", ""))

    def _render_body(self, content_text: str, excerpt: str, is_scraped: int) -> None:
        """Renderiza o corpo: texto completo se disponível, senão excerpt + botão.

        is_scraped: 0 = pendente (mostra botão), 1 = ok (texto completo já está em
        content_text), -1 = falhou (mostra aviso, sem botão).
        """
        if content_text:
            # Texto completo já disponível — exibe e oculta o botão.
            self._body_lbl.setText(content_text)
            self._body_lbl.show()
            self._fulltext_btn.hide()
            self._fulltext_status.hide()
            return

        # Sem texto completo — mostra o excerpt do feed (se houver)
        self._body_lbl.setText(excerpt)
        self._body_lbl.setVisible(bool(excerpt))

        if is_scraped == -1:
            # Falha definitiva — não oferece botão
            self._fulltext_btn.hide()
            self._fulltext_status.setText(
                "Não foi possível carregar o texto completo desta página."
            )
            self._fulltext_status.show()
        else:
            self._fulltext_btn.setText("Carregar texto completo")
            self._fulltext_btn.setEnabled(True)
            self._fulltext_btn.show()
            self._fulltext_status.hide()

    def _on_load_fulltext(self) -> None:
        """Botão 'Carregar texto completo' → pede scraping P1 do artigo atual."""
        if self._current_article_id is None or not self._current_url:
            return
        self._fulltext_btn.setEnabled(False)
        self._fulltext_btn.setText("Carregando texto completo…")
        self._fulltext_status.hide()
        log.info("Solicitando texto completo (P1) do artigo %d.", self._current_article_id)
        self.scrape_requested.emit(self._current_article_id, self._current_url)

    def on_scrape_done(self, article_id: int, success: bool) -> None:
        """Slot: ScraperWorker terminou um artigo. Atualiza o corpo se for o atual."""
        if article_id != self._current_article_id:
            return
        if success:
            self._reload_body()
        else:
            self._fulltext_btn.hide()
            self._fulltext_status.setText(
                "Não foi possível carregar o texto completo desta página."
            )
            self._fulltext_status.show()

    def _reload_body(self, conn: sqlite3.Connection | None = None) -> None:
        """Recarrega apenas content_text/is_scraped do artigo atual e re-renderiza o corpo."""
        if self._current_article_id is None:
            return
        _conn = conn if conn is not None else get_conn()
        should_close = conn is None
        try:
            row = _conn.execute(
                "SELECT content_text, content_excerpt, is_scraped FROM articles WHERE id = ?",
                (self._current_article_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            log.error("Falha ao recarregar corpo do artigo %d: %s",
                      self._current_article_id, exc)
            return
        finally:
            if should_close:
                _conn.close()
        if row is not None:
            self._render_body(
                content_text=(row["content_text"] or "").strip(),
                excerpt=(row["content_excerpt"] or "").strip(),
                is_scraped=int(row["is_scraped"] or 0),
            )

    def _mark_as_read(
        self,
        article_id: int,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Atualiza is_read=1 e read_at para o artigo dado."""
        _conn = conn if conn is not None else get_conn()
        should_close = conn is None
        try:
            _conn.execute(
                """
                UPDATE articles
                   SET is_read = 1,
                       read_at  = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                 WHERE id = ? AND is_read = 0
                """,
                (article_id,),
            )
            _conn.commit()
        except sqlite3.Error as exc:
            log.error("Falha ao marcar artigo %d como lido: %s", article_id, exc)
        finally:
            if should_close:
                _conn.close()

    def _set_content_visible(self, visible: bool) -> None:
        for widget in (
            self._title_lbl,
            self._meta_lbl,
            self._sep,
            self._body_lbl,
            self._fulltext_btn,
            self._fulltext_status,
        ):
            widget.setVisible(visible)
