"""
article_list.py — Painel central: lista de artigos em cards.

Cada card mostra título, feed de origem, data relativa, tipo e tempo de leitura.
Artigos não-lidos têm título em negrito. Artigos lidos ficam em tom mais suave.

Emite article_selected(int) quando a usuária clica num card (article_id).

Fase 2 — cards básicos: sem dados de análise AI (sentimento, tags, clickbait).
Esses campos chegam na Fase 4 (AnalysisWorker). A estrutura do card já prevê
slots para eles, mas não os exibe ainda.

O load_articles é sempre full-refresh, limitado a 200 artigos. Quando o
FetchWorker emite feed_done, on_feed_updated decide se recarga ou não.
"""
from __future__ import annotations

import html
import json
import logging
import re
import sqlite3
from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.database import get_conn
from app.ui.views.feed_sidebar import ALL_FEEDS_ID

log = logging.getLogger("kosmos.article_list")

_MAX_ARTICLES = 200
_CLICKBAIT_ALERT = 0.6   # acima disto, o card mostra o ícone de alerta
_MAX_CHIPS = 4           # nº máximo de chips de tag exibidos por card
_SENTIMENTS = ("positivo", "neutro", "negativo")


def _analysis_from_data(data: dict) -> tuple[str | None, float | None, list]:
    """Extrai (sentimento, clickbait, tags) de um dict de artigo. tags = lista (JSON parseado)."""
    tags: list = []
    raw = data.get("ai_tags")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                tags = parsed
        except (ValueError, TypeError):
            tags = []
    return data.get("ai_sentiment"), data.get("ai_clickbait_score"), tags


def _fetch_card_analysis(
    article_id: int, conn: sqlite3.Connection | None = None
) -> tuple[str | None, float | None, list] | None:
    """Lê os campos de Call A de um artigo para atualizar o card ao vivo. None se ausente."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        row = _conn.execute(
            "SELECT ai_sentiment, ai_clickbait_score, ai_tags FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        log.error("Falha ao ler análise do artigo %d para o card: %s", article_id, exc)
        return None
    finally:
        if should_close:
            _conn.close()
    return _analysis_from_data(dict(row)) if row is not None else None


def _fmt_date(iso: str | None) -> str:
    """Converte ISO8601 UTC para data relativa legível (agora / Xh / Xd / dd/mm)."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - dt
        if diff.days == 0:
            hours = diff.seconds // 3600
            return f"{hours}h atrás" if hours else "agora"
        if diff.days < 7:
            return f"{diff.days}d atrás"
        return dt.strftime("%d/%m")
    except Exception:
        return ""


def _strip_html(text: str) -> str:
    """Remove tags HTML e normaliza espaços (para o snippet de resumo do card)."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def _font(family: str, fallback: str, size: int) -> QFont:
    """Fonte do design antigo com fallback (Special Elite / Courier Prime / IM Fell English)."""
    f = QFont(family)
    if not f.exactMatch():
        f = QFont(fallback)
    f.setPointSize(size)
    return f


class ArticleCard(QFrame):
    """Card de artigo com o design do KOSMOS antigo.

    Bolinha de lido/não-lido à esquerda, borda esquerda colorida por sentimento,
    título serifado (máquina de escrever), meta + badge de idioma, chips de tags
    ao vivo, snippet de resumo e badge de clickbait à direita.

    Mantém a API que a ArticleList consome: `article_id`, `set_title`,
    `apply_quick_analysis` (Call A ao vivo).
    """

    def __init__(self, data: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("article_card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._article_id: int = data["id"]
        self._setup_ui(data)

    def _setup_ui(self, data: dict) -> None:
        # Alerta: card destacado quando casa com keyword/entidade vigiada (🔔 + property).
        self._alerted: bool = bool(data.get("alerted"))
        self.setProperty("alerted", self._alerted)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(12)

        # Bolinha de lido/não-lido (property "read" → estilo no QSS).
        self._dot = QLabel()
        self._dot.setObjectName("read_dot")
        self._dot.setFixedSize(8, 8)
        self._dot.setProperty("read", bool(data.get("is_read")))
        outer.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignTop)

        content = QVBoxLayout()
        content.setSpacing(3)
        content.setContentsMargins(0, 0, 0, 0)

        # Título — prefere a tradução; serifado; negrito se não-lido. Altura fixa a 2
        # linhas para não causar reflow quando a tradução chega ao vivo.
        base_title = data.get("title_translated") or data.get("title") or "(sem título)"
        title_font = _font("Special Elite", "Courier New", 13)
        self._title_lbl = QLabel(("🔔 " + base_title) if self._alerted else base_title)
        self._title_lbl.setObjectName("card_title")
        self._title_lbl.setWordWrap(True)
        if data.get("is_read"):
            self._title_lbl.setFont(title_font)
        else:
            bold = QFont(title_font)
            bold.setBold(True)
            self._title_lbl.setFont(bold)
        fm = QFontMetrics(title_font)
        self._title_lbl.setMaximumHeight(fm.lineSpacing() * 2 + 6)
        content.addWidget(self._title_lbl)

        # Meta: feed · autor · data · tipo · min + badge de idioma.
        meta_parts: list[str] = []
        if data.get("feed_title"):
            meta_parts.append(str(data["feed_title"]))
        if data.get("author"):
            meta_parts.append(str(data["author"]))
        date_str = _fmt_date(data.get("published_at"))
        if date_str:
            meta_parts.append(date_str)
        art_type = data.get("article_type") or "news"
        if art_type != "news":
            meta_parts.append(str(art_type).upper())
        reading = data.get("estimated_reading_min")
        if reading:
            meta_parts.append(f"{reading} min")

        meta_font = _font("Courier Prime", "Courier New", 10)
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)
        meta_row.setContentsMargins(0, 0, 0, 0)
        self._meta_lbl = QLabel("  ·  ".join(meta_parts))
        self._meta_lbl.setObjectName("card_meta")
        self._meta_lbl.setProperty("class", "meta")
        self._meta_lbl.setFont(meta_font)
        meta_row.addWidget(self._meta_lbl)
        lang = (data.get("language_detected") or "").strip()
        if lang:
            lang_lbl = QLabel(lang.upper()[:5])
            lang_lbl.setObjectName("lang_badge")
            lang_lbl.setFont(meta_font)
            meta_row.addWidget(lang_lbl)
        meta_row.addStretch(1)
        content.addLayout(meta_row)

        # Linha de tags (chips) — preenchida pela Call A.
        self._tags_row = QHBoxLayout()
        self._tags_row.setSpacing(4)
        self._tags_row.setContentsMargins(0, 2, 0, 0)
        self._tags_container = QWidget()
        self._tags_container.setLayout(self._tags_row)
        content.addWidget(self._tags_container)
        self._tags_container.hide()

        # Snippet de resumo (excerpt do feed), serifado.
        snippet = _truncate(_strip_html(data.get("content_excerpt") or ""), 180)
        self._summary_lbl = QLabel(snippet)
        self._summary_lbl.setObjectName("card_summary")
        self._summary_lbl.setWordWrap(True)
        self._summary_lbl.setFont(_font("IM Fell English", "Georgia", 12))
        self._summary_lbl.setVisible(bool(snippet))
        content.addWidget(self._summary_lbl)

        outer.addLayout(content, 1)

        # Coluna direita: badge de clickbait (⚠), oculto até a Call A indicar alto.
        self._clickbait_badge = QLabel("⚠")
        self._clickbait_badge.setObjectName("clickbait_icon")
        self._clickbait_badge.setFixedWidth(16)
        self._clickbait_badge.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._clickbait_badge.hide()
        outer.addWidget(self._clickbait_badge, 0, Qt.AlignmentFlag.AlignTop)

        # Pré-análise já no banco → renderiza de imediato.
        sentiment, clickbait, tags = _analysis_from_data(data)
        if sentiment or clickbait is not None or tags:
            self.apply_quick_analysis(sentiment, clickbait, tags)

    @property
    def article_id(self) -> int:
        return self._article_id

    def set_title(self, text: str) -> None:
        """Atualiza o título exibido (tradução ao vivo); preserva o prefixo de alerta."""
        if text:
            self._title_lbl.setText(("🔔 " + text) if self._alerted else text)

    def apply_quick_analysis(self, sentiment: str | None, clickbait: float | None, tags: list) -> None:
        """Call A ao vivo: borda por sentimento + chips de tags + badge de clickbait."""
        # Borda esquerda por sentimento (verde/cinza/laranja via property no QSS).
        self.setProperty("sentiment", sentiment if sentiment in _SENTIMENTS else "")
        self.style().unpolish(self)
        self.style().polish(self)

        # Chips de tags (reconstrói).
        while self._tags_row.count():
            it = self._tags_row.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        chip_font = _font("Courier Prime", "Courier New", 9)
        shown = 0
        for tag in (tags or [])[:_MAX_CHIPS]:
            t = str(tag).strip()
            if not t:
                continue
            chip = QLabel(t)
            chip.setObjectName("tag_chip")
            chip.setFont(chip_font)
            self._tags_row.addWidget(chip)
            shown += 1
        if shown:
            self._tags_row.addStretch(1)
        self._tags_container.setVisible(shown > 0)

        # Badge de clickbait.
        high = clickbait is not None and clickbait >= _CLICKBAIT_ALERT
        if high:
            self._clickbait_badge.setToolTip(f"Clickbait alto ({clickbait:.0%})")
        self._clickbait_badge.setVisible(high)


class ArticleList(QWidget):
    """Painel central: lista de cards de artigos para o feed selecionado."""

    article_selected = Signal(int)  # article_id
    add_to_investigation_requested = Signal(int)  # article_id — via menu de contexto do card

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_feed_id: int = ALL_FEEDS_ID
        self._setup_ui()
        log.debug("ArticleList inicializada.")

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._list = QListWidget()
        self._list.setSpacing(0)
        self._list.setUniformItemSizes(False)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._list)

        self._placeholder = QLabel("Selecione um feed para ver os artigos.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setObjectName("placeholder")
        layout.addWidget(self._placeholder)
        self._placeholder.hide()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def load_articles(
        self,
        feed_id: int = ALL_FEEDS_ID,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        """Carrega (ou recarrega) artigos para o feed dado.

        Args:
            feed_id: feed_id ou ALL_FEEDS_ID (-1) para todos.
            conn:    conexão existente (testes); None → cria e fecha própria.

        Returns:
            Número de artigos carregados.
        """
        self._current_feed_id = feed_id
        _conn = conn if conn is not None else get_conn()
        should_close = conn is None
        rows = []
        self._alerted_ids = set()
        try:
            if feed_id == ALL_FEEDS_ID:
                rows = _conn.execute(
                    """
                    SELECT a.id, a.title, a.title_translated, a.author, a.published_at,
                           a.article_type, a.estimated_reading_min, a.is_read,
                           a.language_detected, a.content_excerpt,
                           a.ai_sentiment, a.ai_clickbait_score, a.ai_tags,
                           COALESCE(f.title, f.url) AS feed_title
                      FROM articles a
                      JOIN feeds f ON f.id = a.feed_id
                     ORDER BY a.published_at DESC, a.created_at DESC
                     LIMIT ?
                    """,
                    (_MAX_ARTICLES,),
                ).fetchall()
            else:
                rows = _conn.execute(
                    """
                    SELECT a.id, a.title, a.title_translated, a.author, a.published_at,
                           a.article_type, a.estimated_reading_min, a.is_read,
                           a.language_detected, a.content_excerpt,
                           a.ai_sentiment, a.ai_clickbait_score, a.ai_tags,
                           COALESCE(f.title, f.url) AS feed_title
                      FROM articles a
                      JOIN feeds f ON f.id = a.feed_id
                     WHERE a.feed_id = ?
                     ORDER BY a.published_at DESC, a.created_at DESC
                     LIMIT ?
                    """,
                    (feed_id, _MAX_ARTICLES),
                ).fetchall()
            # Alertas: conjunto de artigos que casam com keywords/entidades vigiadas.
            # Calculado aqui (conexão aberta) para destacar os cards correspondentes.
            from app.core.alerts import get_alerted_article_ids
            self._alerted_ids = get_alerted_article_ids(_conn)
        except sqlite3.Error as exc:
            log.error("Falha ao carregar artigos (feed_id=%s): %s", feed_id, exc)
        finally:
            if should_close:
                _conn.close()

        self._populate(rows)
        log.info("ArticleList: %d artigo(s) para feed_id=%s.", len(rows), feed_id)
        return len(rows)

    def on_feed_updated(self, feed_id: int, new_count: int) -> None:
        """Chamado pelo FetchWorker (via MainWindow) quando um feed tem novos artigos.

        Recarrega a lista apenas se o feed atualizado é o que está sendo exibido
        (ou se o modo "todos" está ativo).
        """
        if self._current_feed_id in (feed_id, ALL_FEEDS_ID):
            log.debug("Feed %d atualizado (%d novos) — recarregando lista.", feed_id, new_count)
            self.load_articles(self._current_feed_id)

    def _card_for(self, article_id: int) -> "ArticleCard | None":
        """Localiza o card de um artigo na lista por id. None se não estiver visível."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == article_id:
                return self._list.itemWidget(item)
        return None

    def on_title_translated(self, article_id: int, translated_title: str) -> None:
        """Slot: TranslationWorker traduziu um título — atualiza o card ao vivo."""
        card = self._card_for(article_id)
        if card is not None:
            card.set_title(translated_title)

    def on_quick_analysis_done(
        self, article_id: int, conn: sqlite3.Connection | None = None
    ) -> None:
        """Slot: AnalysisWorker concluiu a Call A — atualiza o card (borda, chips, alerta)."""
        card = self._card_for(article_id)
        if card is None:
            return
        analysis = _fetch_card_analysis(article_id, conn)
        if analysis is not None:
            card.apply_quick_analysis(*analysis)

    def on_analysis_failed(self, article_id: int) -> None:
        """Slot: Call A falhou (JSON inválido) — o card permanece neutro."""
        log.debug("Análise rápida falhou para artigo id=%d — card permanece neutro.", article_id)

    def article_count(self) -> int:
        """Retorna o número de itens atualmente na lista."""
        return self._list.count()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _populate(self, rows: list) -> None:
        self._list.clear()
        if not rows:
            self._list.hide()
            self._placeholder.show()
            return

        self._placeholder.hide()
        self._list.show()

        alerted = getattr(self, "_alerted_ids", set())
        for row in rows:
            data = dict(row)
            data["alerted"] = data["id"] in alerted
            card = ArticleCard(data, self._list)
            item = QListWidgetItem(self._list)
            item.setData(Qt.ItemDataRole.UserRole, data["id"])
            item.setSizeHint(card.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, card)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        article_id = item.data(Qt.ItemDataRole.UserRole)
        if article_id is not None:
            log.debug("Artigo selecionado: id=%d", article_id)
            self.article_selected.emit(article_id)

    def _on_context_menu(self, pos) -> None:
        """Menu de contexto do card: 'Adicionar à investigação…' → emite o sinal."""
        item = self._list.itemAt(pos)
        if item is None:
            return
        article_id = item.data(Qt.ItemDataRole.UserRole)
        if article_id is None:
            return
        menu = QMenu(self)
        act = menu.addAction("Adicionar à investigação…")
        if menu.exec(self._list.viewport().mapToGlobal(pos)) is act:
            self._request_add_to_investigation(item)

    def _request_add_to_investigation(self, item: QListWidgetItem) -> None:
        """Resolve o article_id do item e emite o sinal (separado do exec, testável)."""
        article_id = item.data(Qt.ItemDataRole.UserRole)
        if article_id is not None:
            self.add_to_investigation_requested.emit(int(article_id))
