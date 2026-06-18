"""
reader_pane.py — Painel direito: exibe o conteúdo do artigo selecionado.

Layout (design antigo, R1): chrome Qt em cima (título, meta, análise, toolbar de
ações) + **corpo do artigo num QWebEngineView** (``ArticleWebView``) renderizado
com o CSS sépia/serifado do leitor antigo + painel de destaques embaixo. A análise
AI (Call A/B) atualiza no chrome Qt sem mexer no webview, então não atrapalha a
posição de leitura; o webview só é re-renderizado em ações pontuais (texto completo,
alternar tradução, criar/remover destaque).

Se o artigo já tem texto completo (`content_text`), mostra-o; senão mostra o excerpt
e um botão "Carregar texto completo" que dispara o scraping P1 (sinal `scrape_requested`).

Tradução sob demanda (P2): botão "Traduzir" dispara `translate_requested`; quando a
tradução chega (`on_article_translated`), o corpo passa a exibi-la, com o botão
alternando "Ver original"/"Ver tradução".

Destaques (Fase 8): a seleção de texto no webview + menu de contexto criam um destaque
(`ArticleWebView.highlight_requested` → `_create_highlight`); a coloração inline é HTML
(`<mark class='hl-...'>`) montado em Python e re-renderizado no webview.

Quando um artigo é aberto, marca-o como lido (is_read=1) e emite `article_read(int)`.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.database import get_conn
from app.core.highlights import (
    TYPE_LABELS,
    add_highlight,
    delete_highlight,
    list_highlights,
    update_highlight_note,
)
from app.ui.views.article_webview import ArticleWebView

log = logging.getLogger("kosmos.reader_pane")

_FIVE_WS_LABELS = (("quem", "Quem"), ("o_que", "O quê"), ("quando", "Quando"),
                   ("onde", "Onde"), ("por_que", "Por quê"))

# Classes CSS de destaque válidas (correspondem a mark.hl-* no reader_*.css).
_HL_CLASSES = frozenset({"citation", "question", "fact", "contradiction", "generic"})


def _body_html(text: str, highlights: list[dict]) -> str:
    """Escapa o corpo e envolve cada trecho destacado num <mark> colorido por tipo.

    Reserva faixas **não-sobrepostas** no texto original (mais longas primeiro) e
    monta o HTML numa passada só — sem marcas aninhadas nem corrupção. Fragmento que
    não casar (formatação/duplicata/tradução) é ignorado na coloração; o destaque
    continua acessível na lista 'Meus destaques'.
    """
    text = text or ""
    occupied = [False] * len(text)
    claimed: list[tuple[int, int, str]] = []
    for h in sorted(highlights or [], key=lambda x: len(x.get("text") or ""), reverse=True):
        frag = (h.get("text") or "").strip()
        if not frag:
            continue
        idx = text.find(frag)
        while idx != -1 and any(occupied[idx:idx + len(frag)]):
            idx = text.find(frag, idx + 1)
        if idx == -1:
            continue
        for i in range(idx, idx + len(frag)):
            occupied[i] = True
        claimed.append((idx, idx + len(frag), h.get("highlight_type") or "generic"))

    claimed.sort()
    out: list[str] = []
    pos = 0
    for start, end, htype in claimed:
        out.append(escape(text[pos:start]))
        cls = htype if htype in _HL_CLASSES else "generic"
        out.append(f'<mark class="hl-{cls}">{escape(text[start:end])}</mark>')
        pos = end
    out.append(escape(text[pos:]))
    return "".join(out).replace("\n", "<br>")


def _parse_analysis(data: dict) -> dict:
    """Extrai e parseia os campos de análise AI de um dict de artigo (row ou fetch).

    Campos JSON (tags, cinco Ws, entidades, viés) são decodificados com fallback seguro;
    valores de tipo inesperado viram o default vazio.
    """
    def _jload(key: str, default):
        raw = data.get(key)
        if not raw:
            return default
        try:
            val = json.loads(raw)
        except (ValueError, TypeError):
            return default
        return val if isinstance(val, type(default)) else default

    return {
        "summary": (data.get("ai_summary") or "").strip(),
        "sentiment": (data.get("ai_sentiment") or "").strip(),
        "clickbait": data.get("ai_clickbait_score"),
        "tags": _jload("ai_tags", []),
        "five_ws": _jload("ai_five_ws", {}),
        "entities": _jload("ai_entities", []),
        "bias": _jload("ai_bias", {}),
    }


def _analysis_html(ai: dict) -> str:
    """Monta o HTML da seção de análise a partir do que já existe (progressivo).

    Campos rápidos (Call A: resumo, sentimento, clickbait, tags) e ricos (Call B:
    cinco Ws, entidades, viés) aparecem conforme chegam; o que falta é omitido.
    """
    parts: list[str] = []
    if ai.get("summary"):
        parts.append(f"<p><b>Resumo:</b> {escape(ai['summary'])}</p>")

    line = []
    if ai.get("sentiment"):
        line.append(f"Sentimento: {escape(ai['sentiment'])}")
    if ai.get("clickbait") is not None:
        try:
            line.append(f"Clickbait: {float(ai['clickbait']):.0%}")
        except (TypeError, ValueError):
            pass
    if line:
        parts.append(f"<p>{' · '.join(line)}</p>")

    tags = [escape(str(t)) for t in (ai.get("tags") or []) if str(t).strip()]
    if tags:
        parts.append(f"<p><b>Tags:</b> {', '.join(tags)}</p>")

    five = ai.get("five_ws") or {}
    rows = [f"<b>{lbl}:</b> {escape(str(five[k]))}" for k, lbl in _FIVE_WS_LABELS if five.get(k)]
    if rows:
        parts.append("<p>" + "<br>".join(rows) + "</p>")

    ents = []
    for e in (ai.get("entities") or []):
        if isinstance(e, dict) and str(e.get("nome", "")).strip():
            nome = escape(str(e["nome"]))
            tipo = str(e.get("tipo", "")).strip()
            ents.append(f"{nome} ({escape(tipo)})" if tipo else nome)
    if ents:
        parts.append(f"<p><b>Entidades:</b> {', '.join(ents)}</p>")

    bias = ai.get("bias") or {}
    bline = []
    if bias.get("espectro"):
        bline.append(f"espectro {escape(str(bias['espectro']))}")
    if bias.get("qualidade_apuracao"):
        bline.append(f"apuração {escape(str(bias['qualidade_apuracao']))}")
    if bline:
        parts.append(f"<p><b>Viés:</b> {', '.join(bline)}</p>")
    marc = [escape(str(m)) for m in (bias.get("marcadores") or []) if str(m).strip()]
    if marc:
        parts.append(f"<p><b>Marcadores:</b> {', '.join(marc)}</p>")

    return "".join(parts)


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
    translate_requested = Signal(int)    # article_id — pedido P2 de tradução do corpo
    analysis_requested = Signal(int)     # article_id — pedido P1 de análise completa (Call B)
    add_to_investigation_requested = Signal(int)  # article_id — adicionar a uma pasta de investigação
    archive_toggle_requested = Signal(int, bool)  # (article_id, want_saved) — arquivar/desarquivar

    def __init__(self, theme: str = "day", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._current_article_id: int | None = None
        self._current_url: str = ""
        self._orig_body: str = ""              # corpo no idioma original (content_text/excerpt)
        self._translated_body: str = ""        # corpo traduzido (content_text_translated)
        self._showing_translation: bool = False
        self._current_is_saved: bool = False   # artigo arquivado (is_saved=1)?
        self._body_html_cache: str = ""        # último HTML do corpo renderizado no webview
        self._current_highlights: list[dict] = []  # destaques do artigo atual (Fase 8)
        self._current_highlight_id: int | None = None
        self._setup_ui()
        log.debug("ReaderPane inicializada (tema=%s).", theme)

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Estado vazio — placeholder centralizado.
        self._placeholder = QLabel("← Selecione um artigo para ler.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setObjectName("placeholder")
        outer.addWidget(self._placeholder, stretch=1)

        # Conteúdo (quando há artigo): chrome de topo + corpo (webview) + destaques.
        self._content = QWidget()
        cv = QVBoxLayout(self._content)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)

        # --- Chrome de topo: título, meta, separador, análise, toolbar ---
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(32, 20, 32, 10)
        tl.setSpacing(0)

        self._title_lbl = QLabel()
        self._title_lbl.setObjectName("reader_title")
        self._title_lbl.setProperty("class", "title")
        self._title_lbl.setWordWrap(True)
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        tl.addWidget(self._title_lbl)

        self._meta_lbl = QLabel()
        self._meta_lbl.setObjectName("reader_meta")
        self._meta_lbl.setProperty("class", "meta")
        self._meta_lbl.setWordWrap(True)
        tl.addWidget(self._meta_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("reader_sep")
        tl.addSpacing(10)
        tl.addWidget(sep)
        tl.addSpacing(12)
        self._sep = sep

        # Seção de análise AI (Fase 4) — preenchida progressivamente (Call A → Call B).
        self._analysis_header = QLabel("Análise")
        self._analysis_header.setObjectName("reader_analysis_header")
        tl.addWidget(self._analysis_header)
        self._analysis_lbl = QLabel()
        self._analysis_lbl.setObjectName("reader_analysis")
        self._analysis_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._analysis_lbl.setWordWrap(True)
        self._analysis_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        tl.addWidget(self._analysis_lbl)
        tl.addSpacing(12)

        # Toolbar de ações (horizontal, acima do corpo) — texto completo, traduzir, investigação.
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)
        self._fulltext_btn = QPushButton("Carregar texto completo")
        self._fulltext_btn.setObjectName("reader_fulltext_btn")
        self._fulltext_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fulltext_btn.clicked.connect(self._on_load_fulltext)
        btn_row.addWidget(self._fulltext_btn)
        self._translate_btn = QPushButton("Traduzir")
        self._translate_btn.setObjectName("reader_translate_btn")
        self._translate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._translate_btn.clicked.connect(self._on_translate_clicked)
        btn_row.addWidget(self._translate_btn)
        self._investigation_btn = QPushButton("Adicionar à investigação")
        self._investigation_btn.setObjectName("reader_investigation_btn")
        self._investigation_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._investigation_btn.clicked.connect(self._on_add_to_investigation)
        btn_row.addWidget(self._investigation_btn)
        self._archive_btn = QPushButton("Arquivar")
        self._archive_btn.setObjectName("reader_archive_btn")
        self._archive_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._archive_btn.clicked.connect(self._on_archive_clicked)
        btn_row.addWidget(self._archive_btn)
        btn_row.addStretch(1)
        tl.addLayout(btn_row)

        self._fulltext_status = QLabel()
        self._fulltext_status.setProperty("class", "meta")
        self._fulltext_status.setWordWrap(True)
        tl.addWidget(self._fulltext_status)

        cv.addWidget(top)

        # --- Corpo do artigo: QWebEngineView com o CSS do leitor antigo ---
        self._body_view = ArticleWebView(theme=self._theme)
        self._body_view.highlight_requested.connect(self._on_webview_highlight)
        cv.addWidget(self._body_view, stretch=1)

        # --- Rodapé: "Meus destaques" (lista + nota/remover) ---
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(32, 8, 32, 16)
        bl.setSpacing(4)
        self._highlights_header = QLabel("Meus destaques")
        self._highlights_header.setObjectName("reader_highlights_header")
        bl.addWidget(self._highlights_header)
        self._highlights_list = QListWidget()
        self._highlights_list.setObjectName("reader_highlights_list")
        self._highlights_list.setMaximumHeight(120)
        self._highlights_list.currentRowChanged.connect(self._on_highlight_selected)
        bl.addWidget(self._highlights_list)

        self._highlight_detail = QWidget()
        hd = QVBoxLayout(self._highlight_detail)
        hd.setContentsMargins(0, 4, 0, 0)
        self._highlight_note_edit = QPlainTextEdit()
        self._highlight_note_edit.setObjectName("reader_highlight_note")
        self._highlight_note_edit.setMaximumHeight(56)
        self._highlight_note_edit.setPlaceholderText("Nota deste destaque…")
        hd.addWidget(self._highlight_note_edit)
        hrow = QHBoxLayout()
        self._highlight_note_btn = QPushButton("Salvar nota")
        self._highlight_note_btn.clicked.connect(self._on_save_highlight_note)
        hrow.addWidget(self._highlight_note_btn)
        self._highlight_remove_btn = QPushButton("Remover destaque")
        self._highlight_remove_btn.clicked.connect(self._on_remove_highlight)
        hrow.addWidget(self._highlight_remove_btn)
        hrow.addStretch(1)
        hd.addLayout(hrow)
        bl.addWidget(self._highlight_detail)

        cv.addWidget(bottom)

        outer.addWidget(self._content, stretch=1)
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
                       a.language_detected, a.content_excerpt, a.is_read, a.is_saved,
                       a.url, a.content_text, a.content_text_translated, a.is_scraped,
                       a.ai_summary, a.ai_sentiment, a.ai_clickbait_score, a.ai_tags,
                       a.ai_five_ws, a.ai_entities, a.ai_bias,
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
        self._current_highlights = list_highlights(article_id, conn=_conn)
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

        # Dispara a análise completa P1 (Call B) — o worker pula se já estiver feita.
        log.info("Solicitando análise completa (P1) do artigo %d.", article_id)
        self.analysis_requested.emit(article_id)

        return True

    def clear(self) -> None:
        """Volta ao estado de placeholder (nenhum artigo selecionado)."""
        self._current_article_id = None
        self._orig_body = ""
        self._translated_body = ""
        self._showing_translation = False
        self._body_html_cache = ""
        self._current_highlights = []
        self._current_highlight_id = None
        self._body_view.show_empty()
        self._set_content_visible(False)
        self._placeholder.show()

    def current_body_html(self) -> str:
        """HTML do corpo atualmente renderizado no webview (inspeção/testes)."""
        return self._body_html_cache

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _render(self, data: dict) -> None:
        self._placeholder.hide()
        self._set_content_visible(True)

        self._current_is_saved = bool(data.get("is_saved"))
        self._update_archive_btn()
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

        content_text = (data.get("content_text") or "").strip()
        excerpt = (data.get("content_excerpt") or "").strip()
        self._orig_body = content_text or excerpt
        self._translated_body = (data.get("content_text_translated") or "").strip()
        self._showing_translation = False

        self._render_body(
            content_text=content_text,
            excerpt=excerpt,
            is_scraped=int(data.get("is_scraped") or 0),
        )
        self._refresh_translation_ui()
        self._render_analysis(_parse_analysis(data))
        self._populate_highlights_panel()

        log.debug("Artigo renderizado: id=%d título='%s'", data["id"], data.get("title", ""))

    def _render_body(self, content_text: str, excerpt: str, is_scraped: int) -> None:
        """Renderiza o corpo: texto completo se disponível, senão excerpt + botão.

        is_scraped: 0 = pendente (mostra botão), 1 = ok (texto completo já está em
        content_text), -1 = falhou (mostra aviso, sem botão).
        """
        if content_text:
            # Texto completo já disponível — exibe e oculta o botão.
            self._apply_body(content_text, is_original=True)
            self._fulltext_btn.hide()
            self._fulltext_status.hide()
            return

        # Sem texto completo — mostra o excerpt do feed (se houver)
        self._apply_body(excerpt, is_original=True)

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
            content_text = (row["content_text"] or "").strip()
            excerpt = (row["content_excerpt"] or "").strip()
            self._orig_body = content_text or excerpt
            self._showing_translation = False
            self._render_body(
                content_text=content_text,
                excerpt=excerpt,
                is_scraped=int(row["is_scraped"] or 0),
            )
            self._refresh_translation_ui()

    # ------------------------------------------------------------------
    # Tradução sob demanda (P2)
    # ------------------------------------------------------------------

    def _refresh_translation_ui(self) -> None:
        """Configura o botão de tradução e o corpo conforme o estado de tradução."""
        if self._translated_body:
            # Tradução disponível → botão alterna original/tradução
            if self._showing_translation:
                self._apply_body(self._translated_body, is_original=False)
                self._translate_btn.setText("Ver original")
            else:
                self._apply_body(self._orig_body, is_original=True)
                self._translate_btn.setText("Ver tradução")
            self._translate_btn.setEnabled(True)
            self._translate_btn.show()
        elif self._orig_body:
            # Sem tradução ainda → oferece "Traduzir"
            self._translate_btn.setText("Traduzir")
            self._translate_btn.setEnabled(True)
            self._translate_btn.show()
        else:
            self._translate_btn.hide()

    def _on_translate_clicked(self) -> None:
        """Botão de tradução: alterna se já traduzido; senão pede tradução P2."""
        if self._current_article_id is None:
            return
        if self._translated_body:
            self._showing_translation = not self._showing_translation
            self._refresh_translation_ui()
        else:
            self._translate_btn.setEnabled(False)
            self._translate_btn.setText("Traduzindo…")
            log.info("Solicitando tradução (P2) do artigo %d.", self._current_article_id)
            self.translate_requested.emit(self._current_article_id)

    def on_article_translated(self, article_id: int, translated: str) -> None:
        """Slot: TranslationWorker concluiu a tradução do corpo. Exibe se for o atual."""
        if article_id != self._current_article_id:
            return
        if translated and translated.strip():
            self._translated_body = translated.strip()
            self._showing_translation = True  # mostra a tradução assim que chega
            self._refresh_translation_ui()
        else:
            self._translate_btn.setText("Traduzir")
            self._translate_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Análise AI (Call A rápida + Call B rica, progressiva)
    # ------------------------------------------------------------------

    def _render_analysis(self, ai: dict) -> None:
        """Atualiza a seção de análise com o que já existe; oculta-a se nada houver."""
        html = _analysis_html(ai)
        visible = bool(html)
        self._analysis_lbl.setText(html)
        self._analysis_header.setVisible(visible)
        self._analysis_lbl.setVisible(visible)

    def _fetch_analysis(
        self, article_id: int, conn: sqlite3.Connection | None = None
    ) -> dict | None:
        """Lê e parseia os campos de análise do artigo no banco. None se ausente."""
        _conn = conn if conn is not None else get_conn()
        should_close = conn is None
        try:
            row = _conn.execute(
                "SELECT ai_summary, ai_sentiment, ai_clickbait_score, ai_tags, "
                "ai_five_ws, ai_entities, ai_bias FROM articles WHERE id = ?",
                (article_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            log.error("Falha ao ler análise do artigo %d: %s", article_id, exc)
            return None
        finally:
            if should_close:
                _conn.close()
        return _parse_analysis(dict(row)) if row is not None else None

    def _refresh_analysis_if_current(
        self, article_id: int, conn: sqlite3.Connection | None = None
    ) -> None:
        if article_id != self._current_article_id:
            return
        ai = self._fetch_analysis(article_id, conn)
        if ai is not None:
            self._render_analysis(ai)

    def on_quick_analysis_done(self, article_id: int, conn: sqlite3.Connection | None = None) -> None:
        """Slot: Call A concluída — atualiza a análise se for o artigo aberto."""
        self._refresh_analysis_if_current(article_id, conn)

    def on_full_analysis_done(self, article_id: int, conn: sqlite3.Connection | None = None) -> None:
        """Slot: Call B concluída — adiciona os campos ricos se for o artigo aberto."""
        self._refresh_analysis_if_current(article_id, conn)

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

    def _on_add_to_investigation(self) -> None:
        """Botão 'Adicionar à investigação' → entrega o artigo atual ao main_window."""
        if self._current_article_id is not None:
            self.add_to_investigation_requested.emit(self._current_article_id)

    def _update_archive_btn(self) -> None:
        """Rótulo do botão conforme o estado: Arquivar (não salvo) / Desarquivar (salvo)."""
        self._archive_btn.setText("Desarquivar" if self._current_is_saved else "Arquivar")

    def _on_archive_clicked(self) -> None:
        """Botão Arquivar/Desarquivar → pede ao main_window para alternar is_saved."""
        if self._current_article_id is None:
            return
        want_saved = not self._current_is_saved
        log.info("Arquivar=%s solicitado para o artigo %d.", want_saved, self._current_article_id)
        self.archive_toggle_requested.emit(self._current_article_id, want_saved)

    def set_saved_state(self, article_id: int, is_saved: bool) -> None:
        """Slot: o main_window confirmou o novo estado de arquivamento; atualiza o botão."""
        if article_id != self._current_article_id:
            return
        self._current_is_saved = is_saved
        self._update_archive_btn()

    # ------------------------------------------------------------------
    # Destaques / anotações (Fase 8)
    # ------------------------------------------------------------------

    def _apply_body(self, text: str, is_original: bool) -> None:
        """Monta o HTML do corpo (com marcas só no original) e o renderiza no webview."""
        if is_original and self._current_highlights:
            html = _body_html(text, self._current_highlights)
        else:
            html = escape(text or "").replace("\n", "<br>")
        self._body_html_cache = html
        self._body_view.set_body(html)

    def _repaint_body(self) -> None:
        """Re-renderiza o corpo atual (após criar/remover destaque)."""
        if self._showing_translation and self._translated_body:
            self._apply_body(self._translated_body, is_original=False)
        else:
            self._apply_body(self._orig_body, is_original=True)

    def _on_webview_highlight(self, text: str, htype: str) -> None:
        """Sinal do webview: cria um destaque do trecho selecionado no artigo atual."""
        if self._current_article_id is None:
            return
        frag = (text or "").strip()
        if not frag:
            return
        self._create_highlight(frag, htype)

    def _create_highlight(self, text: str, htype: str, position_hint=None) -> None:
        """Cria um destaque do artigo atual e atualiza corpo + painel (testável)."""
        if self._current_article_id is None:
            return
        add_highlight(self._current_article_id, text, htype, position_hint=position_hint)
        log.info("Destaque criado no artigo %d (tipo=%s).", self._current_article_id, htype)
        self._reload_highlights()

    def _reload_highlights(self, conn: sqlite3.Connection | None = None) -> None:
        """Recarrega os destaques do artigo atual e repinta corpo + painel."""
        if self._current_article_id is None:
            return
        self._current_highlights = list_highlights(self._current_article_id, conn=conn)
        self._repaint_body()
        self._populate_highlights_panel()

    def _populate_highlights_panel(self) -> None:
        self._highlights_list.blockSignals(True)
        self._highlights_list.clear()
        for h in self._current_highlights:
            label = TYPE_LABELS.get(h["highlight_type"], "Destaque")
            txt = h.get("text") or ""
            snippet = txt[:70] + ("…" if len(txt) > 70 else "")
            mark = " ✎" if (h.get("note") or "").strip() else ""
            item = QListWidgetItem(f"[{label}] {snippet}{mark}")
            item.setData(Qt.ItemDataRole.UserRole, h["id"])
            self._highlights_list.addItem(item)
        self._highlights_list.blockSignals(False)
        self._current_highlight_id = None
        self._highlight_detail.setVisible(False)
        n = len(self._current_highlights)
        self._highlights_header.setText("Meus destaques" if n else "Meus destaques (nenhum ainda)")

    def _on_highlight_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._current_highlights):
            self._highlight_detail.setVisible(False)
            return
        item = self._highlights_list.item(row)
        hid = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if hid is None:
            return
        self._current_highlight_id = int(hid)
        h = next((x for x in self._current_highlights if x["id"] == self._current_highlight_id), None)
        self._highlight_note_edit.setPlainText((h or {}).get("note") or "")
        self._highlight_detail.setVisible(True)

    def _on_save_highlight_note(self) -> None:
        if self._current_highlight_id is None:
            return
        update_highlight_note(self._current_highlight_id, self._highlight_note_edit.toPlainText())
        self._reload_highlights()

    def _on_remove_highlight(self) -> None:
        if self._current_highlight_id is None:
            return
        delete_highlight(self._current_highlight_id)
        log.info("Destaque %d removido.", self._current_highlight_id)
        self._reload_highlights()

    def _set_content_visible(self, visible: bool) -> None:
        self._content.setVisible(visible)
        self._placeholder.setVisible(not visible)
        if not visible:
            self._highlight_detail.setVisible(False)
