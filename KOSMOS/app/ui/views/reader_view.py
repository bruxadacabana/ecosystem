"""Painel de leitura de artigos (QWebEngineView com CSS sépia)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QMenu, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from app.utils.paths import Paths
from app.utils.time_utils import format_date

if TYPE_CHECKING:
    from app.core.feed_manager import FeedManager
    from app.core.models import Article, Feed
    from app.theme.theme_manager import ThemeManager
    from app.utils.config import Config

log = logging.getLogger("kosmos.ui.reader")

# JavaScript injetado após cada carregamento de página para suportar highlights
_HIGHLIGHT_SETUP_JS = r"""
(function(){
  if(window._khl)return;
  window._khl=true;
  // Salva a seleção no mouseup para não perder ao clicar fora da webview
  window._kosmos_sel='';
  document.addEventListener('mouseup',function(){
    window._kosmos_sel=window.getSelection().toString();
  });
  window._kosmos_apply_hl=function(text,id,color,note){
    if(!text||!text.trim())return;
    var re=new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'));
    function walk(node){
      if(node.nodeType===3){
        var m=node.textContent.match(re);
        if(!m)return false;
        var i=node.textContent.indexOf(m[0]);
        var mk=document.createElement('mark');
        mk.className='kosmos-hl';
        mk.setAttribute('data-hl-id',String(id));
        mk.title=note||'';
        mk.style.cssText='background:'+color+';border-radius:2px;padding:0 1px;';
        mk.textContent=m[0];
        var p=node.parentNode;
        p.insertBefore(document.createTextNode(node.textContent.slice(0,i)),node);
        p.insertBefore(mk,node);
        p.insertBefore(document.createTextNode(node.textContent.slice(i+m[0].length)),node);
        p.removeChild(node);
        return true;
      }else if(node.nodeType===1){
        var t=node.tagName.toLowerCase();
        if(t==='mark'||t==='script'||t==='style')return false;
        return Array.from(node.childNodes).some(walk);
      }
      return false;
    }
    walk(document.body);
  };
})();
"""


class _ScrapeWorker(QThread):
    """Thread que executa o scraping em background."""

    finished = pyqtSignal(str, str)   # content_html, status
    failed   = pyqtSignal(str)        # mensagem de erro

    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url

    def run(self) -> None:
        from app.core.article_scraper import ArticleScraper
        result = ArticleScraper().scrape(self._url)
        if result.status == "failed":
            self.failed.emit(result.error or "Erro desconhecido.")
        else:
            self.finished.emit(result.content_html, result.status)


class _FallbackScrapeWorker(QThread):
    """Traduz o título para inglês, busca no Google News RSS, resolve o redirect
    de cada resultado e tenta scraping do artigo real."""

    finished = pyqtSignal(str, str)   # content_html, status
    failed   = pyqtSignal(str)

    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    def __init__(self, title: str) -> None:
        super().__init__()
        self._title = title

    def run(self) -> None:
        try:
            from urllib.parse import quote
            import requests
            import feedparser
            from deep_translator import GoogleTranslator
            from app.core.article_scraper import ArticleScraper

            en_title = (
                GoogleTranslator(source="auto", target="en").translate(self._title)
                or self._title
            )
            rss_url = (
                f"https://news.google.com/rss/search"
                f"?q={quote(en_title)}&hl=en&gl=US&ceid=US:en"
            )
            feed = feedparser.parse(rss_url)

            if not feed.entries:
                self.failed.emit(f'Sem resultados para "{en_title}".')
                return

            scraper = ArticleScraper()

            # Tenta os primeiros 3 resultados — Google News usa redirect,
            # então seguimos o redirect para obter a URL real do artigo.
            for entry in feed.entries[:3]:
                redirect_url = entry.get("link", "")
                if not redirect_url:
                    continue

                # Resolve o redirect do Google News → URL real do artigo
                try:
                    r = requests.get(
                        redirect_url, timeout=10,
                        allow_redirects=True,
                        headers=self._HEADERS,
                        stream=True,
                    )
                    actual_url = r.url
                    r.close()
                except Exception as exc:
                    log.debug("Redirect falhou para %s, usando URL original: %s", redirect_url, exc)
                    actual_url = redirect_url

                result = scraper.scrape(actual_url)
                if result.status in ("full", "partial") and result.content_html:
                    self.finished.emit(result.content_html, result.status)
                    return

            self.failed.emit("Nenhum resultado alternativo com conteúdo extraível.")
        except Exception as exc:
            self.failed.emit(str(exc))


class _TranslateWorker(QThread):
    """Traduz o conteúdo do artigo em background."""

    finished = pyqtSignal(str)
    failed   = pyqtSignal(str)

    def __init__(self, text: str, from_code: str, to_code: str) -> None:
        super().__init__()
        self._text      = text
        self._from_code = from_code
        self._to_code   = to_code

    def run(self) -> None:
        try:
            from app.core.translator import translate_text
            result = translate_text(self._text, self._from_code, self._to_code)
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class _SummarizeWorker(QThread):
    """Gera resumo do artigo via Ollama em background, emitindo tokens à medida que chegam."""

    token_received = pyqtSignal(str)
    finished       = pyqtSignal(str)   # texto completo acumulado
    failed         = pyqtSignal(str)   # mensagem de erro

    _SYSTEM = (
        "Você é um assistente especializado em resumir notícias. "
        "Escreva no idioma do artigo. "
        "Seja conciso, objetivo e neutro."
    )

    def __init__(self, endpoint: str, gen_model: str, title: str, content: str) -> None:
        super().__init__()
        self._endpoint  = endpoint
        self._gen_model = gen_model
        self._title     = title
        self._content   = content

    def run(self) -> None:
        from app.core.ai_bridge import AiBridge, OllamaError
        bridge = AiBridge(endpoint=self._endpoint, gen_model=self._gen_model)
        prompt = (
            f"Resuma este artigo em 2 a 3 parágrafos curtos e objetivos.\n\n"
            f"Título: {self._title}\n\n"
            f"{self._content}"
        )
        try:
            full = ""
            for token in bridge.generate_stream(prompt, system=self._SYSTEM):
                full += token
                self.token_received.emit(token)
            self.finished.emit(full.strip())
        except OllamaError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))


class _AnalyzeWorker(QThread):
    """Analisa artigo via Ollama em um único call JSON.

    Retorna: tags, sentiment (-1.0→+1.0), clickbait (0.0→1.0), five_ws e entities.
    """

    done   = pyqtSignal(dict)
    failed = pyqtSignal(str)

    _SYSTEM = (
        'Você é uma API JSON. Responda APENAS com JSON válido. '
        'O primeiro caractere deve ser "{".'
    )
    _SCHEMA = (
        '{"tags": ["tag1", "tag2"], '
        '"sentiment": 0.0, '
        '"clickbait": 0.0, '
        '"five_ws": {"who": "...", "what": "...", "when": "...", "where": "...", "why": "..."}, '
        '"entities": {"people": ["nome1"], "orgs": ["org1"], "places": ["lugar1"]}}'
    )

    def __init__(self, endpoint: str, gen_model: str, title: str, content: str) -> None:
        super().__init__()
        self._endpoint  = endpoint
        self._gen_model = gen_model
        self._title     = title
        self._content   = content

    def run(self) -> None:
        try:
            import json as _json
            from app.core.ai_bridge import AiBridge
            bridge = AiBridge(endpoint=self._endpoint, gen_model=self._gen_model)
            prompt = (
                f"Analise este artigo e responda com JSON.\n\n"
                f"Título: {self._title}\n\n"
                f"{self._content}\n\n"
                f"Responda com este JSON:\n{self._SCHEMA}\n\n"
                f"Regras:\n"
                f"- tags: 3 a 5 palavras-chave em letras minúsculas, no idioma do artigo\n"
                f"- sentiment: -1.0 (muito negativo) até +1.0 (muito positivo)\n"
                f"- clickbait: 0.0 (sem clickbait) até 1.0 (clickbait puro)\n"
                f"- five_ws: respostas concisas (máximo 2 frases), no idioma do artigo\n"
                f"- entities: nomes próprios de pessoas, organizações e lugares mencionados "
                f"(listas vazias se não houver)"
            )
            result = bridge.generate(prompt, system=self._SYSTEM, json_format=True)
            data = _json.loads(result)
            if isinstance(data, dict):
                self.done.emit(data)
        except Exception as exc:
            log.error("Análise de artigo falhou: %s", exc)
            self.failed.emit(str(exc))


class _EmbedWorker(QThread):
    """Gera embedding do artigo via nomic-embed-text. Falha silenciosamente."""

    done = pyqtSignal(bytes)   # embedding BLOB

    def __init__(self, endpoint: str, embed_model: str, text: str) -> None:
        super().__init__()
        self._endpoint    = endpoint
        self._embed_model = embed_model
        self._text        = text

    def run(self) -> None:
        try:
            from app.core.ai_bridge import AiBridge
            bridge = AiBridge(endpoint=self._endpoint, embed_model=self._embed_model)
            blob = bridge.embed_to_blob(self._text)
            if blob:
                self.done.emit(blob)
        except Exception as exc:
            log.debug("Embedding falhou (silencioso): %s", exc)


class ReaderView(QWidget):
    """Painel de leitura com QWebEngineView e toolbar de ações.

    Sinais:
        back_requested()         — voltar para a view anterior.
        article_changed(int)     — navegou para outro artigo (prev/next).
        saved_toggled(int, bool) — estado 'salvo' alterado.
        read_toggled(int, bool)  — estado 'lido' alterado.
    """

    back_requested  = pyqtSignal()
    article_changed = pyqtSignal(int)
    saved_toggled   = pyqtSignal(int, bool)
    read_toggled    = pyqtSignal(int, bool)
    analysis_done   = pyqtSignal()   # emitido quando _AnalyzeWorker conclui

    def __init__(
        self,
        feed_manager:  "FeedManager",
        theme_manager: "ThemeManager",
        config:        "Config",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fm     = feed_manager
        self._theme  = theme_manager
        self._config = config
        self.setObjectName("readerView")

        self._article: Article | None = None
        self._feed:    Feed    | None = None
        self._article_ids:    list[int] = []
        self._current_index:  int       = 0
        self._scrape_worker:    _ScrapeWorker         | None = None
        self._fallback_worker:  _FallbackScrapeWorker | None = None
        self._translate_worker: _TranslateWorker      | None = None
        self._summarize_worker: _SummarizeWorker  | None = None
        self._analyze_worker:   _AnalyzeWorker    | None = None
        self._embed_worker:     _EmbedWorker      | None = None
        self._5ws_labels:       dict[str, QLabel] = {}
        self._suggested_tags:   list[str]             = []
        self._is_translated:    bool = False
        self._highlights:       list = []
        self._translate_to_code: str = ""
        self._session_id:        int            = -1
        self._session_started_at: datetime | None = None

        self._webview = None   # set in _build_webview

        self._build_ui()

    # ------------------------------------------------------------------
    # Construção da UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setObjectName("listSeparator")
        root.addWidget(sep1)

        root.addWidget(self._build_meta())
        root.addWidget(self._build_summary_panel())
        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_tags_row())
        root.addWidget(self._build_highlights_row())

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setObjectName("listSeparator")
        root.addWidget(sep2)

        root.addWidget(self._build_webview(), stretch=1)
        root.addWidget(self._build_citation_panel())
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("feedListHeader")
        widget.setFixedHeight(52)

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        back_btn = QPushButton("←  Voltar")
        back_btn.setObjectName("backButton")
        back_btn.setFlat(True)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setFont(self._mono_font(11))
        back_btn.clicked.connect(self._on_back_clicked)
        layout.addWidget(back_btn)

        self._header_feed = QLabel("")
        self._header_feed.setObjectName("cardMeta")
        self._header_feed.setFont(self._mono_font(11))
        layout.addWidget(self._header_feed)

        dot = QLabel("·")
        dot.setObjectName("cardMeta")
        dot.setFont(self._mono_font(11))
        layout.addWidget(dot)

        self._header_title = QLabel("")
        self._header_title.setObjectName("feedListTitle")
        title_font = QFont("Special Elite")
        if not title_font.exactMatch():
            title_font = QFont("Courier New")
        title_font.setPointSize(14)
        self._header_title.setFont(title_font)
        layout.addWidget(self._header_title, 1)

        return widget

    def _build_meta(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("feedListHeader")

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 5, 16, 6)
        layout.setSpacing(1)

        self._meta_author = QLabel("")
        self._meta_author.setObjectName("readerAuthor")
        author_font = QFont("IM Fell English")
        if not author_font.exactMatch():
            author_font = QFont("Georgia")
        author_font.setPointSize(12)
        author_font.setItalic(True)
        self._meta_author.setFont(author_font)
        layout.addWidget(self._meta_author)

        self._meta_label = QLabel("")
        self._meta_label.setObjectName("cardMeta")
        self._meta_label.setFont(self._mono_font(10))
        layout.addWidget(self._meta_label)

        # Linha de indicadores IA (sentimento + clickbait) — visível só quando disponíveis
        ind_row = QWidget()
        ind_layout = QHBoxLayout(ind_row)
        ind_layout.setContentsMargins(0, 0, 0, 0)
        ind_layout.setSpacing(8)

        self._sentiment_lbl = QLabel("")
        self._sentiment_lbl.setFont(self._mono_font(10))
        self._sentiment_lbl.hide()
        ind_layout.addWidget(self._sentiment_lbl)

        self._clickbait_lbl = QLabel("")
        self._clickbait_lbl.setObjectName("clickbaitIndicator")
        self._clickbait_lbl.setFont(self._mono_font(10))
        self._clickbait_lbl.hide()
        ind_layout.addWidget(self._clickbait_lbl)

        ind_layout.addStretch()
        self._indicators_row = ind_row
        self._indicators_row.hide()
        layout.addWidget(ind_row)

        return widget

    def _build_toolbar(self) -> QWidget:
        outer = QWidget()
        outer.setObjectName("readerToolbar")

        root = QVBoxLayout(outer)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        btn_font = self._mono_font(11)

        # --- Linha 1 (sempre visível) ---
        row1 = QWidget()
        row1.setObjectName("feedListHeader")
        row1.setFixedHeight(44)
        r1 = QHBoxLayout(row1)
        r1.setContentsMargins(16, 0, 16, 0)
        r1.setSpacing(8)

        self._save_btn = QPushButton("☆  Salvar")
        self._save_btn.setObjectName("markAllBtn")
        self._save_btn.setFont(btn_font)
        self._save_btn.clicked.connect(self._on_toggle_saved)
        r1.addWidget(self._save_btn)

        self._read_btn = QPushButton("Marcar como lido")
        self._read_btn.setObjectName("markAllBtn")
        self._read_btn.setFont(btn_font)
        self._read_btn.clicked.connect(self._on_toggle_read)
        r1.addWidget(self._read_btn)

        self._scrape_btn = QPushButton("○  Buscar artigo completo")
        self._scrape_btn.setObjectName("markAllBtn")
        self._scrape_btn.setFont(btn_font)
        self._scrape_btn.clicked.connect(self._on_fetch_full)
        r1.addWidget(self._scrape_btn)

        self._translate_btn = QPushButton("Traduzir")
        self._translate_btn.setObjectName("markAllBtn")
        self._translate_btn.setFont(btn_font)
        self._translate_btn.clicked.connect(self._on_translate)
        r1.addWidget(self._translate_btn)

        self._summarize_btn = QPushButton("∑ Resumir")
        self._summarize_btn.setObjectName("markAllBtn")
        self._summarize_btn.setFont(btn_font)
        self._summarize_btn.setToolTip("Gerar resumo do artigo via IA local (Ollama)")
        self._summarize_btn.clicked.connect(self._on_summarize)
        r1.addWidget(self._summarize_btn)

        r1.addStretch()
        root.addWidget(row1)

        # --- Linha 2 (visível quando a largura é insuficiente) ---
        self._toolbar_row2 = QWidget()
        self._toolbar_row2.setObjectName("feedListHeader")
        self._toolbar_row2.setFixedHeight(44)
        r2 = QHBoxLayout(self._toolbar_row2)
        r2.setContentsMargins(16, 0, 16, 0)
        r2.setSpacing(8)

        self._highlight_btn = QPushButton("◾ Destacar")
        self._highlight_btn.setObjectName("markAllBtn")
        self._highlight_btn.setFont(btn_font)
        self._highlight_btn.setToolTip("Selecione um trecho no artigo e clique para destacar")
        self._highlight_btn.clicked.connect(self._on_highlight_btn)
        r2.addWidget(self._highlight_btn)

        self._export_btn = QPushButton("Exportar")
        self._export_btn.setObjectName("markAllBtn")
        self._export_btn.setFont(btn_font)
        self._export_btn.setToolTip("Exportar artigo para Markdown em data/archive/")
        self._export_btn.clicked.connect(self._on_export)
        r2.addWidget(self._export_btn)

        r2.addStretch()

        open_btn = QPushButton("Abrir no navegador")
        open_btn.setObjectName("markAllBtn")
        open_btn.setFont(btn_font)
        open_btn.clicked.connect(self._on_open_browser)
        r2.addWidget(open_btn)

        self._toolbar_row2.hide()
        root.addWidget(self._toolbar_row2)

        return outer

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_toolbar_row2"):
            self._toolbar_row2.setVisible(self.width() < 950)

    def _build_summary_panel(self) -> QWidget:
        self._summary_panel = QFrame()
        self._summary_panel.setObjectName("summaryPanel")
        self._summary_panel.hide()

        root = QVBoxLayout(self._summary_panel)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("summaryHeader")
        header.setFixedHeight(30)
        h = QHBoxLayout(header)
        h.setContentsMargins(16, 0, 16, 0)

        lbl = QLabel("∑  Resumo  ·  IA")
        lbl.setObjectName("cardMeta")
        lbl.setFont(self._mono_font(10))
        h.addWidget(lbl)
        h.addStretch()

        close_btn = QPushButton("×")
        close_btn.setObjectName("summaryCloseBtn")
        close_btn.setFlat(True)
        close_btn.setFont(self._mono_font(12))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(22, 22)
        close_btn.clicked.connect(self._hide_summary_panel)
        h.addWidget(close_btn)
        root.addWidget(header)

        self._summary_text = QTextEdit()
        self._summary_text.setObjectName("summaryText")
        self._summary_text.setReadOnly(True)
        self._summary_text.setFont(self._mono_font(11))
        self._summary_text.setMaximumHeight(170)
        self._summary_text.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(self._summary_text)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("listSeparator")
        root.addWidget(sep)

        return self._summary_panel

    def _build_tags_row(self) -> QWidget:
        self._tags_container = QWidget()
        self._tags_container.setObjectName("tagsRow")
        self._tags_container.setFixedHeight(34)
        self._tags_layout = QHBoxLayout(self._tags_container)
        self._tags_layout.setContentsMargins(16, 4, 16, 4)
        self._tags_layout.setSpacing(6)
        self._tags_layout.addStretch()
        return self._tags_container

    def _build_highlights_row(self) -> QWidget:
        self._hl_row = QWidget()
        self._hl_row.setObjectName("highlightsRow")
        self._hl_row.hide()
        self._hl_layout = QHBoxLayout(self._hl_row)
        self._hl_layout.setContentsMargins(16, 4, 16, 4)
        self._hl_layout.setSpacing(6)

        lbl = QLabel("Destaques:")
        lbl.setObjectName("cardMeta")
        lbl.setFont(self._mono_font(10))
        self._hl_layout.addWidget(lbl)

        self._hl_layout.addStretch()
        return self._hl_row

    def _build_webview(self) -> QWidget:
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            self._webview = QWebEngineView()
            self._webview.setObjectName("articleWebView")
            self._webview.loadFinished.connect(self._on_page_loaded)
            return self._webview
        except ImportError:
            log.error(
                "PyQt6-WebEngine não disponível — painel de leitura desativado. "
                "Execute: pip install PyQt6-WebEngine"
            )
            fallback = QLabel(
                "PyQt6-WebEngine não disponível.\n"
                "Instale com: pip install PyQt6-WebEngine"
            )
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setObjectName("emptyLabel")
            return fallback

    def _build_footer(self) -> QWidget:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("listSeparator")

        nav = QWidget()
        nav.setFixedHeight(44)

        layout = QHBoxLayout(nav)
        layout.setContentsMargins(16, 0, 16, 0)

        btn_font = self._mono_font(11)

        self._prev_btn = QPushButton("←  Anterior")
        self._prev_btn.setObjectName("backButton")
        self._prev_btn.setFlat(True)
        self._prev_btn.setFont(btn_font)
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.clicked.connect(self._on_prev)
        layout.addWidget(self._prev_btn)

        layout.addStretch()

        from PyQt6.QtWidgets import QLabel as _QLabel
        self._lang_status_lbl = _QLabel("")
        self._lang_status_lbl.setObjectName("cardMeta")
        self._lang_status_lbl.setFont(self._mono_font(10))
        self._lang_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._lang_status_lbl)

        layout.addStretch()

        self._next_btn = QPushButton("Próximo  →")
        self._next_btn.setObjectName("backButton")
        self._next_btn.setFlat(True)
        self._next_btn.setFont(btn_font)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(self._on_next)
        layout.addWidget(self._next_btn)

        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(sep)
        v.addWidget(nav)
        return container

    def _build_citation_panel(self) -> QFrame:
        """Painel de citação ABNT + análise 5Ws. Visível apenas quando o artigo está salvo."""
        self._citation_panel = QFrame()
        self._citation_panel.setObjectName("citationPanel")
        self._citation_panel.hide()

        outer = QVBoxLayout(self._citation_panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("listSeparator")
        outer.addWidget(sep)

        # Header clicável (toggle)
        hdr = QWidget()
        hdr.setObjectName("citationHeader")
        hdr.setFixedHeight(30)
        hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(16, 0, 16, 0)

        self._citation_toggle_lbl = QLabel("▸  Citação & 5Ws")
        self._citation_toggle_lbl.setObjectName("summaryHeader")
        self._citation_toggle_lbl.setFont(self._mono_font(10))
        hdr_layout.addWidget(self._citation_toggle_lbl)
        hdr_layout.addStretch()

        self._5ws_status_lbl = QLabel("")
        self._5ws_status_lbl.setObjectName("cardMeta")
        self._5ws_status_lbl.setFont(self._mono_font(9))
        hdr_layout.addWidget(self._5ws_status_lbl)

        outer.addWidget(hdr)
        hdr.mousePressEvent = lambda _e: self._toggle_citation_body()

        # Corpo colapsível
        self._citation_body = QWidget()
        self._citation_body.hide()
        body = QVBoxLayout(self._citation_body)
        body.setContentsMargins(16, 8, 16, 12)
        body.setSpacing(10)

        # Citação ABNT
        citation_lbl = QLabel("ABNT")
        citation_lbl.setObjectName("5wsKey")
        citation_lbl.setFont(self._mono_font(9))
        body.addWidget(citation_lbl)

        self._citation_text = QTextEdit()
        self._citation_text.setObjectName("citationText")
        self._citation_text.setReadOnly(True)
        self._citation_text.setMaximumHeight(72)
        self._citation_text.setFont(self._mono_font(10))
        body.addWidget(self._citation_text)

        # Separador interno
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setObjectName("cardSeparator")
        body.addWidget(sep2)

        # Grid 5Ws
        self._5ws_widget = QWidget()
        self._5ws_widget.hide()
        grid = QGridLayout(self._5ws_widget)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setSpacing(6)
        grid.setColumnStretch(1, 1)

        _5ws_keys = [
            ("who",   "Quem:"),
            ("what",  "O quê:"),
            ("when",  "Quando:"),
            ("where", "Onde:"),
            ("why",   "Por quê:"),
        ]
        for row, (key, label_text) in enumerate(_5ws_keys):
            key_lbl = QLabel(label_text)
            key_lbl.setObjectName("5wsKey")
            key_lbl.setFont(self._mono_font(10))
            key_lbl.setFixedWidth(72)
            key_lbl.setAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight
            )

            val_lbl = QLabel("")
            val_lbl.setObjectName("5wsValue")
            val_lbl.setWordWrap(True)
            val_font = QFont("IM Fell English")
            if not val_font.exactMatch():
                val_font = QFont("Georgia")
            val_font.setPointSize(11)
            val_lbl.setFont(val_font)

            grid.addWidget(key_lbl, row, 0)
            grid.addWidget(val_lbl, row, 1)
            self._5ws_labels[key] = val_lbl

        body.addWidget(self._5ws_widget)
        outer.addWidget(self._citation_body)

        return self._citation_panel

    # ------------------------------------------------------------------
    # Utilitário de fonte
    # ------------------------------------------------------------------

    @staticmethod
    def _mono_font(size: int) -> QFont:
        f = QFont("Courier Prime")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(size)
        return f

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def open_article(
        self,
        article: "Article",
        feed:    "Feed | None",
        article_ids:   list[int],
        current_index: int,
    ) -> None:
        """Carrega e exibe o artigo. Deve ser chamado do thread principal."""
        self._end_session()

        # Interromper workers anteriores
        if self._scrape_worker and self._scrape_worker.isRunning():
            self._scrape_worker.quit()
            self._scrape_worker.wait(2000)
        if self._summarize_worker and self._summarize_worker.isRunning():
            self._summarize_worker.quit()
            self._summarize_worker.wait(1000)
        if self._analyze_worker and self._analyze_worker.isRunning():
            self._analyze_worker.quit()
            self._analyze_worker.wait(500)
        if self._embed_worker and self._embed_worker.isRunning():
            self._embed_worker.quit()
            self._embed_worker.wait(300)
        if hasattr(self, "_summary_panel"):
            self._summary_panel.hide()
        self._suggested_tags = []

        self._article       = article
        self._feed          = feed
        self._article_ids   = article_ids
        self._current_index = current_index

        self._start_session()
        self._refresh_ui()
        self._start_analyze()
        self._start_embed()

    # ------------------------------------------------------------------
    # Atualização da UI
    # ------------------------------------------------------------------

    def _refresh_ui(self) -> None:
        if self._article is None:
            return

        article = self._article
        feed    = self._feed

        # Cabeçalho
        self._header_feed.setText(feed.name if feed else "—")
        title = (article.title or "(sem título)")
        display_title = title if len(title) <= 80 else title[:77] + "..."
        self._header_title.setText(display_title)
        self._header_title.setToolTip(title)

        # Meta — autor (destaque) + data · tempo
        author_text = (article.author or "").strip()
        self._meta_author.setText(author_text)
        self._meta_author.setVisible(bool(author_text))

        date_parts: list[str] = []
        if article.published_at:
            date_parts.append(format_date(article.published_at))
        content_for_time = article.content_full or article.summary or ""
        est = self._estimate_reading_time(content_for_time)
        if est:
            date_parts.append(f"~{est} min de leitura")
        self._meta_label.setText("  ·  ".join(date_parts))

        # Botões de estado
        self._save_btn.setText("★  Salvo" if article.is_saved else "☆  Salvar")
        self._read_btn.setText(
            "Marcar como não lido" if article.is_read else "Marcar como lido"
        )
        self._update_scrape_btn()
        self._update_summarize_btn()
        self._refresh_tags()

        # Navegação prev/next
        self._prev_btn.setEnabled(self._current_index > 0)
        self._next_btn.setEnabled(
            self._current_index < len(self._article_ids) - 1
        )

        # Indicadores IA
        self._update_meta_indicators()

        # Painel de citação — visível apenas quando salvo
        if article.is_saved:
            self._show_citation_panel()
        else:
            self._citation_panel.hide()

        self._load_content()

    def _load_content(self) -> None:
        if self._webview is None or self._article is None:
            return

        self._is_translated = False
        self._translate_btn.setText("Traduzir")
        self._translate_btn.setEnabled(True)
        self._highlight_btn.setEnabled(True)
        self._lang_status_lbl.setText("")

        content = (
            self._article.content_full
            or self._article.summary
            or "<p><em>Sem conteúdo disponível.</em></p>"
        )

        html = self._build_html(content, title=self._article.title or "")
        self._webview.setHtml(html, QUrl("about:blank"))

    def _build_html(self, content: str, title: str = "") -> str:
        font_css   = self._build_font_faces()
        reader_css = self._load_reader_css()

        cosmos_sep = '<div class="cosmos-sep">· &nbsp; ✦ &nbsp; ·</div>\n'
        import html as _html
        title_html = (
            f'<h1 style="margin-top:0;margin-bottom:0.6em;">'
            f'{_html.escape(title)}</h1>\n'
            if title else ""
        )
        return (
            "<!DOCTYPE html>\n"
            '<html lang="pt">\n'
            "<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            "<style>\n"
            f"{font_css}\n"
            f"{reader_css}\n"
            "</style>\n"
            "</head>\n"
            "<body>\n"
            f"{title_html}"
            f"{cosmos_sep}"
            f"{content}\n"
            "</body>\n"
            "</html>"
        )

    def _build_font_faces(self) -> str:
        fonts_dir = Paths.FONTS
        font_defs = [
            ("IMFellEnglish-Regular.ttf", "IM Fell English", "normal", "normal"),
            ("IMFellEnglish-Italic.ttf",  "IM Fell English", "normal", "italic"),
            ("SpecialElite-Regular.ttf",  "Special Elite",   "normal", "normal"),
            ("CourierPrime-Regular.ttf",  "Courier Prime",   "normal", "normal"),
            ("CourierPrime-Bold.ttf",     "Courier Prime",   "bold",   "normal"),
            ("CourierPrime-Italic.ttf",   "Courier Prime",   "normal", "italic"),
        ]
        faces: list[str] = []
        for filename, family, weight, style in font_defs:
            path = fonts_dir / filename
            if path.exists():
                uri = path.as_uri()
                faces.append(
                    f'@font-face {{\n'
                    f'    font-family: "{family}";\n'
                    f'    src: url("{uri}") format("truetype");\n'
                    f'    font-weight: {weight};\n'
                    f'    font-style: {style};\n'
                    f'}}'
                )
        return "\n".join(faces)

    def _load_reader_css(self) -> str:
        css_path = Paths.THEME / f"reader_{self._theme.current}.css"
        try:
            return css_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    # ------------------------------------------------------------------
    # Estimativa de tempo de leitura
    # ------------------------------------------------------------------

    def _update_meta_indicators(self) -> None:
        """Atualiza os indicadores de sentimento e clickbait na meta bar."""
        if self._article is None:
            return

        sentiment = self._article.ai_sentiment
        clickbait = self._article.ai_clickbait
        has_any   = False

        if sentiment is not None:
            if sentiment >= 0.2:
                self._sentiment_lbl.setObjectName("sentimentPositive")
                self._sentiment_lbl.setText("● tom positivo")
            elif sentiment <= -0.2:
                self._sentiment_lbl.setObjectName("sentimentNegative")
                self._sentiment_lbl.setText("● tom negativo")
            else:
                self._sentiment_lbl.setObjectName("sentimentNeutral")
                self._sentiment_lbl.setText("● tom neutro")
            self._sentiment_lbl.style().unpolish(self._sentiment_lbl)
            self._sentiment_lbl.style().polish(self._sentiment_lbl)
            self._sentiment_lbl.show()
            has_any = True
        else:
            self._sentiment_lbl.hide()

        if clickbait is not None and clickbait >= 0.6:
            self._clickbait_lbl.setText(f"⚠ clickbait {int(clickbait * 100)}%")
            self._clickbait_lbl.show()
            has_any = True
        else:
            self._clickbait_lbl.hide()

        self._indicators_row.setVisible(has_any)

    @staticmethod
    def _estimate_reading_time(html: str) -> int:
        """Retorna minutos estimados. 0 se não houver conteúdo suficiente."""
        if not html:
            return 0
        text = re.sub(r"<[^>]+>", " ", html)
        words = len(text.split())
        if words < 50:
            return 0
        return max(1, round(words / 200))

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def _refresh_tags(self) -> None:
        """Reconstrói os chips de tag e o botão ＋ Tag."""
        while self._tags_layout.count():
            item = self._tags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._article is not None:
            tags = self._fm.get_article_tags(self._article.id)
            for tag in tags:
                chip = QPushButton(f"{tag.name}  ×")
                chip.setObjectName("tagChip")
                chip.setFont(self._mono_font(10))
                chip.setCursor(Qt.CursorShape.PointingHandCursor)
                chip.setToolTip(f'Remover tag "{tag.name}"')
                chip.clicked.connect(lambda _c, tid=tag.id: self._on_remove_tag(tid))
                self._tags_layout.addWidget(chip)

            add_btn = QPushButton("＋ Tag")
            add_btn.setObjectName("addTagBtn")
            add_btn.setFont(self._mono_font(10))
            add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            add_btn.clicked.connect(self._on_add_tag)
            self._tags_layout.addWidget(add_btn)

        # Chips de tags sugeridas pela IA
        for tag_name in self._suggested_tags:
            chip = QPushButton(f"+ {tag_name}")
            chip.setObjectName("suggestedTagChip")
            chip.setFont(self._mono_font(10))
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip(f'Aceitar tag sugerida por IA: "{tag_name}"')
            chip.clicked.connect(
                lambda _c, tn=tag_name: self._on_accept_suggested_tag(tn)
            )
            self._tags_layout.addWidget(chip)

            dis = QPushButton("×")
            dis.setObjectName("suggestedTagDismiss")
            dis.setFont(self._mono_font(10))
            dis.setFixedWidth(16)
            dis.setCursor(Qt.CursorShape.PointingHandCursor)
            dis.setToolTip("Descartar sugestão")
            dis.clicked.connect(
                lambda _c, tn=tag_name: self._on_dismiss_suggested_tag(tn)
            )
            self._tags_layout.addWidget(dis)

        self._tags_layout.addStretch()

    def _start_analyze(self) -> None:
        """Inicia análise completa (tags, sentimento, clickbait, 5Ws) em background."""
        if self._article is None:
            return
        if not bool(self._config.get("ai_enabled", False)):
            return
        gen_model = self._config.get("ai_gen_model", "")
        if not gen_model:
            return

        endpoint = self._config.get("ai_endpoint", "http://localhost:11434")
        raw = self._article.content_full or self._article.summary or ""
        try:
            from bs4 import BeautifulSoup
            content = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
        except Exception:
            content = re.sub(r"<[^>]+>", " ", raw)
        content = content[:3000]

        if self._analyze_worker and self._analyze_worker.isRunning():
            self._analyze_worker.quit()
            self._analyze_worker.wait(300)

        self._analyze_worker = _AnalyzeWorker(
            endpoint  = str(endpoint),
            gen_model = str(gen_model),
            title     = self._article.title or "",
            content   = content,
        )
        self._analyze_worker.done.connect(self._on_analyze_done)
        self._analyze_worker.failed.connect(
            lambda msg: log.error("_AnalyzeWorker: %s", msg)
        )
        self._analyze_worker.start()

    def _on_analyze_done(self, data: dict) -> None:
        if self._article is None:
            return

        # Tags — só sugerir as que ainda não existem no artigo
        tags = data.get("tags", [])
        if isinstance(tags, list) and tags:
            existing = {t.name.lower() for t in self._fm.get_article_tags(self._article.id)}
            clean    = [str(t).strip().lower() for t in tags if str(t).strip()]
            self._suggested_tags = [t for t in clean if t not in existing]
            if self._suggested_tags:
                self._refresh_tags()

        # Sentimento
        sentiment = data.get("sentiment")
        if sentiment is not None:
            try:
                val = max(-1.0, min(1.0, float(sentiment)))
                self._article.ai_sentiment = val
            except (TypeError, ValueError):
                pass

        # Clickbait
        clickbait = data.get("clickbait")
        if clickbait is not None:
            try:
                val = max(0.0, min(1.0, float(clickbait)))
                self._article.ai_clickbait = val
            except (TypeError, ValueError):
                pass

        # 5Ws
        ws_data = data.get("five_ws") or data.get("5ws")

        # Entidades nomeadas
        entities_data = data.get("entities")
        entities_json = (
            json.dumps(entities_data, ensure_ascii=False)
            if isinstance(entities_data, dict) else None
        )
        if entities_json:
            self._article.ai_entities = entities_json

        # Persistir tudo de uma vez
        self._fm.save_ai_analysis(
            article_id = self._article.id,
            sentiment  = self._article.ai_sentiment,
            clickbait  = self._article.ai_clickbait,
            five_ws    = json.dumps(ws_data, ensure_ascii=False) if isinstance(ws_data, dict) else None,
            entities   = entities_json,
        )

        if isinstance(ws_data, dict):
            self._article.ai_5ws = json.dumps(ws_data, ensure_ascii=False)
            if self._citation_panel.isVisible():
                self._populate_5ws_from_cache()
                self._5ws_status_lbl.setText("")

        self._update_meta_indicators()
        self.analysis_done.emit()

    def _on_accept_suggested_tag(self, tag_name: str) -> None:
        if self._article is None:
            return
        try:
            all_tags = {t.name.lower(): t for t in self._fm.get_tags()}
            if tag_name in all_tags:
                tag = all_tags[tag_name]
            else:
                tag = self._fm.create_tag(tag_name)
            self._fm.add_tag_to_article(self._article.id, tag.id)
            self._suggested_tags = [t for t in self._suggested_tags if t != tag_name]
            self._refresh_tags()
        except Exception as exc:
            log.error("Erro ao aceitar tag sugerida '%s': %s", tag_name, exc)

    def _on_dismiss_suggested_tag(self, tag_name: str) -> None:
        self._suggested_tags = [t for t in self._suggested_tags if t != tag_name]
        self._refresh_tags()

    # ------------------------------------------------------------------
    # Embedding e relevância
    # ------------------------------------------------------------------

    def _start_embed(self) -> None:
        """Gera embedding do artigo em background se IA habilitada e embedding ausente."""
        if self._article is None:
            return
        if not bool(self._config.get("ai_enabled", False)):
            return
        embed_model = self._config.get("ai_embed_model", "")
        if not embed_model:
            return
        if self._article.embedding is not None:
            return   # já existe — não regerar

        endpoint = self._config.get("ai_endpoint", "http://localhost:11434")
        title   = self._article.title or ""
        content = self._article.content_full or self._article.summary or ""
        try:
            from bs4 import BeautifulSoup
            content = BeautifulSoup(content, "html.parser").get_text(" ", strip=True)
        except Exception:
            pass
        text = f"{title}\n\n{content[:2000]}"

        if self._embed_worker and self._embed_worker.isRunning():
            self._embed_worker.quit()
            self._embed_worker.wait(300)

        self._embed_worker = _EmbedWorker(str(endpoint), str(embed_model), text)
        self._embed_worker.done.connect(self._on_embed_done)
        self._embed_worker.start()

    def _on_embed_done(self, blob: bytes) -> None:
        """Salva o embedding, recomputa o perfil do usuário e atualiza todos os scores."""
        if self._article is None:
            return
        self._fm.save_embedding(self._article.id, blob)
        self._article.embedding = blob
        profile = self._fm.get_user_profile_embedding()
        if profile:
            self._fm.update_all_relevance_scores(profile)

    # ------------------------------------------------------------------
    # Citação ABNT e análise 5Ws
    # ------------------------------------------------------------------

    def _format_abnt(self) -> str:
        """Formata referência bibliográfica ABNT para artigo online."""
        if self._article is None:
            return ""

        from datetime import date as _date
        _MONTHS = [
            "jan.", "fev.", "mar.", "abr.", "maio", "jun.",
            "jul.", "ago.", "set.", "out.", "nov.", "dez.",
        ]

        author = (self._article.author or "").strip()
        if author:
            name_parts = author.split()
            if len(name_parts) >= 2:
                last  = name_parts[-1].upper()
                first = " ".join(name_parts[:-1])
                author_fmt = f"{last}, {first}. "
            else:
                author_fmt = author.upper() + ". "
        else:
            author_fmt = ""

        title       = (self._article.title or "").strip()
        publication = (self._feed.name if self._feed else "").strip()

        pub_date = ""
        if self._article.published_at:
            d = self._article.published_at
            pub_date = f"{d.day} {_MONTHS[d.month - 1]} {d.year}"

        today  = _date.today()
        access = f"{today.day} {_MONTHS[today.month - 1]} {today.year}"
        url    = (self._article.url or "").strip()

        citation = author_fmt
        citation += f"{title}. "
        if publication:
            citation += f"{publication}, "
        citation += "[s.l.], "
        if pub_date:
            citation += f"{pub_date}. "
        if url:
            citation += f"Disponível em: {url}. "
        citation += f"Acesso em: {access}."
        return citation

    def _show_citation_panel(self) -> None:
        """Preenche e exibe o painel. Usa cache de 5Ws se disponível."""
        self._citation_text.setPlainText(self._format_abnt())
        for lbl in self._5ws_labels.values():
            lbl.setText("")
        self._5ws_widget.hide()
        self._citation_panel.show()

        if self._article and self._article.ai_5ws:
            self._populate_5ws_from_cache()
            self._5ws_status_lbl.setText("")
        elif self._analyze_worker and self._analyze_worker.isRunning():
            self._5ws_status_lbl.setText("⟳  Analisando…")
        else:
            self._5ws_status_lbl.setText("")

    def _toggle_citation_body(self) -> None:
        if self._citation_body.isVisible():
            self._citation_body.hide()
            self._citation_toggle_lbl.setText("▸  Citação & 5Ws")
        else:
            self._citation_body.show()
            self._citation_toggle_lbl.setText("▾  Citação & 5Ws")

    def _populate_5ws_from_cache(self) -> None:
        if not self._article or not self._article.ai_5ws:
            return
        import json as _json
        try:
            data = _json.loads(self._article.ai_5ws)
        except Exception:
            return
        for key, lbl in self._5ws_labels.items():
            val = data.get(key, "")
            if val:
                lbl.setText(str(val))
        self._5ws_widget.show()

    def _on_add_tag(self) -> None:
        if self._article is None:
            return

        all_tags = self._fm.get_tags()
        current_ids = {t.id for t in self._fm.get_article_tags(self._article.id)}

        menu = QMenu(self)
        for tag in all_tags:
            action = menu.addAction(tag.name)
            action.setCheckable(True)
            action.setChecked(tag.id in current_ids)
            action.triggered.connect(
                lambda checked, t=tag: self._on_toggle_tag(t.id, checked)
            )

        menu.addSeparator()
        new_action = menu.addAction("Nova tag…")
        new_action.triggered.connect(self._on_create_tag)

        sender = self.sender()
        if sender:
            menu.exec(sender.mapToGlobal(sender.rect().bottomLeft()))

    def _on_toggle_tag(self, tag_id: int, add: bool) -> None:
        if self._article is None:
            return
        if add:
            self._fm.add_tag_to_article(self._article.id, tag_id)
        else:
            self._fm.remove_tag_from_article(self._article.id, tag_id)
        self._refresh_tags()

    def _on_create_tag(self) -> None:
        name, ok = QInputDialog.getText(self, "Nova Tag", "Nome da tag:")
        if ok and name.strip():
            try:
                tag = self._fm.create_tag(name.strip())
                if self._article:
                    self._fm.add_tag_to_article(self._article.id, tag.id)
                    self._refresh_tags()
            except Exception as exc:
                log.error("Erro ao criar tag: %s", exc)
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Erro", f"Não foi possível criar a tag:\n{exc}")

    def _on_remove_tag(self, tag_id: int) -> None:
        if self._article is None:
            return
        self._fm.remove_tag_from_article(self._article.id, tag_id)
        self._refresh_tags()

    # ------------------------------------------------------------------
    # Estado do botão de scraping
    # ------------------------------------------------------------------

    def _update_scrape_btn(self) -> None:
        if self._article is None:
            return
        status    = self._article.scrape_status or "none"
        integrity = self._article.integrity     or "unknown"

        if status == "full" or integrity == "full":
            self._scrape_btn.setText("● Artigo completo")
            self._scrape_btn.setEnabled(False)
        elif status == "partial":
            self._scrape_btn.setText("◑ Scraping parcial — tentar novamente")
            self._scrape_btn.setEnabled(True)
        elif status == "failed":
            self._scrape_btn.setText("○ Scraping falhou — tentar novamente")
            self._scrape_btn.setEnabled(True)
        else:
            self._scrape_btn.setText("○  Buscar artigo completo")
            self._scrape_btn.setEnabled(bool(self._article.url))

    # ------------------------------------------------------------------
    # Handlers de botões
    # ------------------------------------------------------------------

    def _on_toggle_saved(self) -> None:
        if self._article is None:
            return
        new_state = self._fm.toggle_saved(self._article.id)
        self._article.is_saved = int(new_state)
        self._save_btn.setText("★  Salvo" if new_state else "☆  Salvar")
        self.saved_toggled.emit(self._article.id, new_state)

        # Se está salvando e há resumo no painel ainda não persistido, salvar agora
        if new_state and not self._article.ai_summary:
            current_text = self._summary_text.toPlainText().strip()
            if current_text:
                self._fm.save_ai_summary(self._article.id, current_text)
                self._article.ai_summary = current_text

        # Mostrar/ocultar painel de citação
        if new_state:
            self._show_citation_panel()
        else:
            self._citation_panel.hide()

    def _on_toggle_read(self) -> None:
        if self._article is None:
            return
        new_state = self._fm.toggle_read(self._article.id)
        self._article.is_read = int(new_state)
        self._read_btn.setText(
            "Marcar como não lido" if new_state else "Marcar como lido"
        )
        self.read_toggled.emit(self._article.id, new_state)

    def _on_fetch_full(self) -> None:
        if self._article is None or not self._article.url:
            return
        self._scrape_btn.setText("● Buscando...")
        self._scrape_btn.setEnabled(False)

        self._scrape_worker = _ScrapeWorker(self._article.url)
        self._scrape_worker.finished.connect(self._on_scrape_finished)
        self._scrape_worker.failed.connect(self._on_scrape_failed)
        self._scrape_worker.start()

    def _on_scrape_finished(self, content_html: str, status: str) -> None:
        if self._article is None:
            return
        self._fm.update_article_content(self._article.id, content_html, status)
        self._article.content_full  = content_html
        self._article.scrape_status = status
        self._update_scrape_btn()
        self._load_content()

    def _on_scrape_failed(self, error: str) -> None:
        if self._article is None:
            log.warning("Scraping falhou: %s", error)
            return

        self._fm.update_article_content(self._article.id, "", "failed")
        self._article.scrape_status = "failed"

        title = self._article.title
        if title:
            log.warning("Scraping falhou (%s) — buscando alternativa em inglês.", error)
            self._scrape_btn.setText("● Buscando alternativa…")
            self._scrape_btn.setEnabled(False)
            self._fallback_worker = _FallbackScrapeWorker(title)
            self._fallback_worker.finished.connect(self._on_scrape_finished)
            self._fallback_worker.failed.connect(self._on_fallback_failed)
            self._fallback_worker.start()
        else:
            self._update_scrape_btn()
            log.warning("Scraping falhou: %s", error)

    def _on_fallback_failed(self, error: str) -> None:
        if self._article is not None:
            self._update_scrape_btn()
        log.warning("Fallback de scraping também falhou: %s", error)

    def _on_translate(self) -> None:
        if self._article is None:
            return

        if self._is_translated:
            # Voltar ao original
            self._is_translated = False
            self._translate_btn.setText("Traduzir")
            self._highlight_btn.setEnabled(True)
            self._load_content()
            return

        # Mostrar menu de idiomas
        from app.core.translator import TARGET_LANGUAGE_NAMES
        menu = QMenu(self)
        for code, name in TARGET_LANGUAGE_NAMES.items():
            action = menu.addAction(name)
            action.setData(code)

        sender = self.sender()
        pos = sender.mapToGlobal(sender.rect().bottomLeft()) if sender else self._translate_btn.mapToGlobal(self._translate_btn.rect().bottomLeft())
        chosen = menu.exec(pos)
        if chosen is None:
            return

        to_code = chosen.data()
        self._translate_to_code = to_code
        content = self._article.content_full or self._article.summary or ""
        if not content:
            return

        from app.core.translator import html_to_paragraphs
        text = html_to_paragraphs(content)

        # Prepend title so it gets translated together with the body
        title = self._article.title or ""
        if title:
            text = title + "\n\n" + text

        self._translate_btn.setEnabled(False)
        self._translate_btn.setText("Traduzindo…")

        self._translate_worker = _TranslateWorker(text, "auto", to_code)
        self._translate_worker.finished.connect(self._on_translate_done)
        self._translate_worker.failed.connect(self._on_translate_error)
        self._translate_worker.start()

    def _on_translate_done(self, result: str) -> None:
        if self._webview is None:
            return

        paras = [p.strip() for p in result.split("\n\n") if p.strip()]

        # If we prepended the title, the first paragraph is the translated title
        if self._article and self._article.title and paras:
            translated_title = paras[0]
            body_paras = paras[1:]
        else:
            translated_title = ""
            body_paras = paras

        translated_html = "\n".join(
            f"<p>{para}</p>" for para in body_paras
        ) or f"<p>{result}</p>"

        self._webview.setHtml(
            self._build_html(translated_html, title=translated_title),
            QUrl("about:blank"),
        )
        self._is_translated = True
        self._translate_btn.setText("Ver original")
        self._translate_btn.setEnabled(True)
        self._highlight_btn.setEnabled(False)

        # Update language status label in the footer
        from app.core.translator import LANGUAGE_NAMES
        src_code = (self._article.language if self._article else None) or "auto"
        src_name = LANGUAGE_NAMES.get(src_code, src_code.upper())
        tgt_name = LANGUAGE_NAMES.get(self._translate_to_code, self._translate_to_code.upper())
        self._lang_status_lbl.setText(f"{src_name}  →  {tgt_name}")

    def _on_translate_error(self, error: str) -> None:
        self._translate_btn.setText("Traduzir")
        self._translate_btn.setEnabled(True)
        log.warning("Erro na tradução: %s", error)

    def _on_highlight_btn(self) -> None:
        """Lê a seleção guardada no mouseup e cria um destaque."""
        if self._article is None or self._webview is None or self._is_translated:
            return
        # Usa _kosmos_sel (salvo no mouseup) em vez de getSelection(),
        # que já estaria vazia ao clicar neste botão fora da webview.
        self._webview.page().runJavaScript(
            "var s=window._kosmos_sel||''; window._kosmos_sel=''; s",
            self._on_got_selection,
        )

    def _on_got_selection(self, text: str) -> None:
        if not text or not text.strip() or self._article is None:
            return
        text = text.strip()
        try:
            hl = self._fm.add_highlight(article_id=self._article.id, text=text)
        except Exception as exc:
            log.error("Erro ao salvar destaque: %s", exc)
            self._highlight_btn.setText("! Erro ao destacar")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: self._highlight_btn.setText("◾ Destacar"))
            return
        self._highlights.append(hl)
        self._refresh_highlights_row()

        # Auto-salvar o artigo ao criar o primeiro destaque
        if not self._article.is_saved:
            new_state = self._fm.toggle_saved(self._article.id)
            self._article.is_saved = int(new_state)
            self._save_btn.setText("★  Salvo")
            self.saved_toggled.emit(self._article.id, new_state)

        # Aplicar na página atual sem recarregar
        color = "rgba(230,180,60,0.45)" if self._theme.current == "day" else "rgba(180,140,40,0.5)"
        self._webview.page().runJavaScript(
            _HIGHLIGHT_SETUP_JS +
            f"\nwindow._kosmos_apply_hl({json.dumps(text)}, {hl.id}, "
            f"'{color}', '');"
        )

    def _inject_highlights(self) -> None:
        """Busca os highlights do artigo no DB e os injeta na página.

        O _HIGHLIGHT_SETUP_JS é sempre injetado (registra o listener mouseup
        que salva a seleção), independentemente de já existirem highlights.
        """
        if self._article is None or self._webview is None:
            return
        self._highlights = self._fm.get_highlights(self._article.id)
        self._refresh_highlights_row()
        color = "rgba(230,180,60,0.45)" if self._theme.current == "day" else "rgba(180,140,40,0.5)"
        calls = [_HIGHLIGHT_SETUP_JS]
        for hl in self._highlights:
            calls.append(
                f"window._kosmos_apply_hl({json.dumps(hl.text)}, {hl.id}, "
                f"'{color}', {json.dumps(hl.note or '')});"
            )
        self._webview.page().runJavaScript("\n".join(calls))

    def _refresh_highlights_row(self) -> None:
        """Reconstrói os chips de destaque na barra abaixo das tags."""
        # Remover chips antigos, preservar o QLabel no índice 0 e o stretch no final
        while self._hl_layout.count() > 2:
            item = self._hl_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        if not self._highlights:
            self._hl_row.hide()
            return

        self._hl_row.show()
        mono = self._mono_font(10)

        for hl in self._highlights:
            snippet = hl.text[:28] + ("…" if len(hl.text) > 28 else "")
            if hl.note:
                snippet += " ✎"

            chip = QPushButton(snippet)
            chip.setObjectName("hlChip")
            chip.setFont(mono)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip(hl.note if hl.note else hl.text)
            chip.clicked.connect(lambda _c, hid=hl.id: self._on_edit_highlight_note(hid))

            del_btn = QPushButton("×")
            del_btn.setObjectName("hlChipDel")
            del_btn.setFont(mono)
            del_btn.setFixedWidth(18)
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setToolTip("Remover destaque")
            del_btn.clicked.connect(lambda _c, hid=hl.id: self._on_delete_highlight(hid))

            # Inserir antes do stretch (último item)
            idx = self._hl_layout.count() - 1
            self._hl_layout.insertWidget(idx, chip)
            self._hl_layout.insertWidget(idx + 1, del_btn)

    def _on_edit_highlight_note(self, highlight_id: int) -> None:
        hl = next((h for h in self._highlights if h.id == highlight_id), None)
        if hl is None:
            return
        current_note = hl.note or ""
        note, ok = QInputDialog.getText(
            self, "Anotação", "Nota para este destaque:", text=current_note
        )
        if not ok:
            return
        note = note.strip() or None
        self._fm.update_highlight_note(highlight_id, note)
        hl.note = note
        self._refresh_highlights_row()
        # Atualizar tooltip no mark da página
        if self._webview:
            self._webview.page().runJavaScript(
                f"(function(){{"
                f"  var el=document.querySelector('.kosmos-hl[data-hl-id=\"{highlight_id}\"]');"
                f"  if(el) el.title={json.dumps(note or '')};"
                f"}})();"
            )

    def _on_delete_highlight(self, highlight_id: int) -> None:
        self._fm.delete_highlight(highlight_id)
        self._highlights = [h for h in self._highlights if h.id != highlight_id]
        self._refresh_highlights_row()
        # Remover o mark da página sem recarregar
        if self._webview:
            self._webview.page().runJavaScript(
                f"(function(){{"
                f"  document.querySelectorAll('.kosmos-hl[data-hl-id=\"{highlight_id}\"]')"
                f"  .forEach(function(el){{"
                f"    el.parentNode.replaceChild(document.createTextNode(el.textContent),el);"
                f"  }});"
                f"}})();"
            )

    def _on_open_browser(self) -> None:
        if self._article is None or not self._article.url:
            return
        import webbrowser
        webbrowser.open(self._article.url)

    def _on_export(self) -> None:
        if self._article is None:
            return
        from app.core.archive_manager import export_article
        feed_name = self._feed.name if self._feed else None
        try:
            export_article(self._article, feed_name)
            self._export_btn.setText("✓ Exportado")
        except Exception as exc:
            log.warning("Erro ao exportar artigo: %s", exc)
            self._export_btn.setText("! Erro")
        self._export_btn.setEnabled(False)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(2500, self._reset_export_btn)

    def _reset_export_btn(self) -> None:
        self._export_btn.setText("Exportar")
        self._export_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Resumo IA
    # ------------------------------------------------------------------

    def _on_summarize(self) -> None:
        if self._article is None:
            return

        # Se o painel já está visível, ocultar (toggle)
        if self._summary_panel.isVisible():
            self._hide_summary_panel()
            return

        # Resumo em cache → exibir direto
        if self._article.ai_summary:
            self._summary_text.setPlainText(self._article.ai_summary)
            self._summary_panel.show()
            self._update_summarize_btn()
            return

        # Verificar configuração de IA
        endpoint  = self._config.get("ai_endpoint",  "http://localhost:11434")
        gen_model = self._config.get("ai_gen_model", "")
        if not gen_model:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "IA não configurada",
                "Nenhum modelo de geração selecionado.\n"
                "Vá em Configurações → IA e clique em 'Detectar modelos'.",
            )
            return

        # Extrair texto plano do HTML
        raw = self._article.content_full or self._article.summary or ""
        if not raw:
            return
        try:
            from bs4 import BeautifulSoup
            text_content = BeautifulSoup(raw, "html.parser").get_text(
                separator="\n", strip=True
            )
        except Exception:
            text_content = re.sub(r"<[^>]+>", " ", raw)
        text_content = text_content[:4000]

        # Iniciar worker
        self._summary_panel.show()
        self._summary_text.setPlainText("")
        self._summarize_btn.setText("○ Resumindo…")
        self._summarize_btn.setEnabled(False)

        self._summarize_worker = _SummarizeWorker(
            endpoint=endpoint,
            gen_model=gen_model,
            title=self._article.title or "",
            content=text_content,
        )
        self._summarize_worker.token_received.connect(self._on_summary_token)
        self._summarize_worker.finished.connect(self._on_summary_done)
        self._summarize_worker.failed.connect(self._on_summary_failed)
        self._summarize_worker.start()

    def _on_summary_token(self, token: str) -> None:
        cursor = self._summary_text.textCursor()
        from PyQt6.QtGui import QTextCursor
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(token)
        self._summary_text.setTextCursor(cursor)
        self._summary_text.ensureCursorVisible()

    def _on_summary_done(self, full_text: str) -> None:
        if self._article is not None and full_text:
            self._fm.save_ai_summary(self._article.id, full_text)
            self._article.ai_summary = full_text
        self._update_summarize_btn()

    def _on_summary_failed(self, error: str) -> None:
        log.error("Resumo IA falhou: %s", error)
        self._summary_panel.hide()
        self._summarize_btn.setText("! Falhou")
        self._summarize_btn.setEnabled(True)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(2500, self._update_summarize_btn)

    def _hide_summary_panel(self) -> None:
        self._summary_panel.hide()
        self._update_summarize_btn()

    def _update_summarize_btn(self) -> None:
        if not hasattr(self, "_summarize_btn"):
            return
        ai_on = bool(self._config.get("ai_enabled", False))
        self._summarize_btn.setVisible(ai_on)
        if not ai_on:
            return
        self._summarize_btn.setEnabled(True)
        if self._summary_panel.isVisible():
            self._summarize_btn.setText("▴ Ocultar resumo")
        elif self._article and self._article.ai_summary:
            self._summarize_btn.setText("▾ Ver resumo")
        else:
            self._summarize_btn.setText("∑ Resumir")

    # ------------------------------------------------------------------
    # Scroll — salvar e restaurar
    # ------------------------------------------------------------------

    def _save_scroll(self, callback) -> None:
        """Salva a posição de scroll atual em background, depois chama callback."""
        if self._webview is not None and self._article is not None:
            article_id = self._article.id
            self._webview.page().runJavaScript(
                "window.scrollY",
                lambda y: self._on_got_scroll(int(y or 0), article_id, callback),
            )
        else:
            callback()

    def _on_got_scroll(self, scroll_y: int, article_id: int, callback) -> None:
        if scroll_y > 0:
            self._fm.save_article_scroll(article_id, scroll_y)
        callback()

    def _on_page_loaded(self, ok: bool) -> None:
        """Restaura o scroll e injeta highlights após o conteúdo carregar."""
        if not ok or self._webview is None or self._article is None:
            return
        self._inject_highlights()
        pos = getattr(self._article, "scroll_pos", 0) or 0
        if pos > 0:
            self._webview.page().runJavaScript(f"window.scrollTo(0, {pos})")

    # ------------------------------------------------------------------
    # Sessões de leitura
    # ------------------------------------------------------------------

    def _start_session(self) -> None:
        if self._article is None:
            return
        self._session_id = self._fm.start_read_session(
            article_id=self._article.id,
            feed_id=self._article.feed_id,
        )
        self._session_started_at = datetime.utcnow()

    def _end_session(self) -> None:
        if self._session_id < 0 or self._session_started_at is None:
            return
        duration = int((datetime.utcnow() - self._session_started_at).total_seconds())
        if duration >= 3:   # ignorar aberturas acidentais < 3 s
            self._fm.end_read_session(self._session_id, duration)
        self._session_id = -1
        self._session_started_at = None

    # ------------------------------------------------------------------
    # Navegação entre artigos
    # ------------------------------------------------------------------

    def _on_back_clicked(self) -> None:
        self._end_session()
        self._save_scroll(callback=self.back_requested.emit)

    def _on_prev(self) -> None:
        if self._current_index > 0:
            self._navigate_to(self._current_index - 1)

    def _on_next(self) -> None:
        if self._current_index < len(self._article_ids) - 1:
            self._navigate_to(self._current_index + 1)

    def _navigate_to(self, index: int) -> None:
        self._save_scroll(callback=lambda: self._do_navigate(index))

    def _do_navigate(self, index: int) -> None:
        article_id = self._article_ids[index]
        article    = self._fm.get_article(article_id)
        if article is None:
            return

        # Marcar como lido ao navegar
        if not article.is_read:
            self._fm.mark_as_read(article_id)
            article.is_read = 1

        feed = self._fm.get_feed(article.feed_id)

        self._article       = article
        self._feed          = feed
        self._current_index = index
        self._refresh_ui()
        self.article_changed.emit(article_id)
