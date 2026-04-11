"""Overlay de busca global — ativado por Ctrl+K."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QPainter
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit,
    QScrollArea, QVBoxLayout, QWidget,
)

if TYPE_CHECKING:
    from app.core.feed_manager import FeedManager
    from app.core.search import SearchResult

log = logging.getLogger("kosmos.ui.search")

_MAX_RESULTS = 40


class _ResultItem(QWidget):
    """Card de resultado individual."""

    clicked = pyqtSignal(int)  # article_id

    def __init__(
        self,
        result: "SearchResult",
        feed_name: str,
        selected: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._article_id = result.article.id
        self.setObjectName("searchResultItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", selected)
        self._build(result, feed_name)

    def _build(self, result: "SearchResult", feed_name: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(3)

        # Feed name
        src = QLabel(feed_name or "—")
        src.setObjectName("searchResultSource")
        src.setFont(self._mono(9))
        layout.addWidget(src)

        # Título — usar snippet se disponível, senão título puro
        title_html = result.title_snippet or (result.article.title or "(sem título)")
        title_lbl = QLabel(title_html)
        title_lbl.setObjectName("searchResultTitle")
        title_lbl.setFont(self._mono(11))
        title_lbl.setTextFormat(Qt.TextFormat.RichText)
        title_lbl.setWordWrap(True)
        layout.addWidget(title_lbl)

        # Snippet de conteúdo
        if result.content_snippet:
            snip = QLabel(result.content_snippet)
            snip.setObjectName("searchResultSnippet")
            snip.setFont(self._mono(10))
            snip.setTextFormat(Qt.TextFormat.RichText)
            snip.setWordWrap(True)
            layout.addWidget(snip)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._article_id)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    @staticmethod
    def _mono(size: int) -> QFont:
        f = QFont("Courier Prime")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(size)
        return f


class SearchOverlay(QWidget):
    """Overlay flutuante de busca global (Ctrl+K).

    Sinais:
        article_selected(article_id) — usuário clicou num resultado.
    """

    article_selected = pyqtSignal(int)

    def __init__(self, feed_manager: "FeedManager", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fm = feed_manager
        self._feeds_by_id: dict[int, str] = {}
        self._result_items: list[_ResultItem] = []
        self._selected_idx: int = -1

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._run_search)

        # Cobrir todo o parent, mas não interceptar eventos do próprio panel
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("searchOverlay")
        self.hide()
        self._build_ui()

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Layout raiz: só para centralizar o painel
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 60, 0, 0)
        root.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        self._panel = QWidget()
        self._panel.setObjectName("searchPanel")
        self._panel.setFixedWidth(640)
        root.addWidget(self._panel)

        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Campo de busca
        search_row = QWidget()
        search_row.setObjectName("searchInputRow")
        search_hl = QHBoxLayout(search_row)
        search_hl.setContentsMargins(12, 10, 12, 10)
        search_hl.setSpacing(8)

        icon = QLabel("⌕")
        icon.setObjectName("searchIcon")
        icon.setFont(self._title_font(16))
        search_hl.addWidget(icon)

        self._search_edit = QLineEdit()
        self._search_edit.setObjectName("searchInput")
        self._search_edit.setPlaceholderText("Buscar em todos os artigos…")
        self._search_edit.setFont(self._mono(13))
        self._search_edit.setFrame(False)
        self._search_edit.textChanged.connect(self._on_text_changed)
        self._search_edit.installEventFilter(self)
        search_hl.addWidget(self._search_edit, 1)

        esc_lbl = QLabel("Esc")
        esc_lbl.setObjectName("searchEscHint")
        esc_lbl.setFont(self._mono(9))
        search_hl.addWidget(esc_lbl)

        panel_layout.addWidget(search_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("listSeparator")
        panel_layout.addWidget(sep)

        # Área de resultados
        self._scroll = QScrollArea()
        self._scroll.setObjectName("searchScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setMaximumHeight(480)

        self._results_widget = QWidget()
        self._results_widget.setObjectName("searchResultsContainer")
        self._results_layout = QVBoxLayout(self._results_widget)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(0)

        self._scroll.setWidget(self._results_widget)
        panel_layout.addWidget(self._scroll)
        self._scroll.hide()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Exibe o overlay e foca o campo de busca."""
        self._feeds_by_id = {f.id: f.name for f in self._fm.get_feeds()}
        if self.parent():
            self.resize(self.parent().size())  # type: ignore[union-attr]
            self.move(0, 0)
        self.raise_()
        self.show()
        self._search_edit.clear()
        self._clear_results()
        self._search_edit.setFocus()

    def deactivate(self) -> None:
        self.hide()
        self._search_timer.stop()

    # ------------------------------------------------------------------
    # Pintura — fundo semi-transparente
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 160))
        painter.end()

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        # Fechar ao clicar fora do painel
        if not self._panel.geometry().contains(event.pos()):
            self.deactivate()
        super().mousePressEvent(event)

    def eventFilter(self, obj: object, event: object) -> bool:
        if obj is self._search_edit and isinstance(event, QKeyEvent):
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.deactivate()
                return True
            if key == Qt.Key.Key_Down:
                self._move_selection(1)
                return True
            if key == Qt.Key.Key_Up:
                self._move_selection(-1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._open_selected()
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Busca
    # ------------------------------------------------------------------

    def _on_text_changed(self, text: str) -> None:
        if not text.strip():
            self._clear_results()
            return
        self._search_timer.start(280)

    def _run_search(self) -> None:
        from app.core.search import search_articles
        query = self._search_edit.text()
        if not query.strip():
            self._clear_results()
            return

        results = search_articles(query, limit=_MAX_RESULTS)
        self._populate_results(results)

    def _populate_results(self, results: list["SearchResult"]) -> None:
        self._clear_results()

        if not results:
            empty = QLabel("Nenhum resultado encontrado.")
            empty.setObjectName("emptyLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setContentsMargins(0, 20, 0, 20)
            self._results_layout.addWidget(empty)
            self._scroll.show()
            return

        for result in results:
            feed_name = self._feeds_by_id.get(result.article.feed_id, "")
            item = _ResultItem(result, feed_name)
            item.clicked.connect(self._on_result_clicked)

            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setObjectName("cardSeparator")

            self._results_layout.addWidget(item)
            self._results_layout.addWidget(sep)
            self._result_items.append(item)

        self._scroll.show()

    def _clear_results(self) -> None:
        self._result_items.clear()
        self._selected_idx = -1
        while self._results_layout.count():
            item = self._results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._scroll.hide()

    # ------------------------------------------------------------------
    # Navegação por teclado
    # ------------------------------------------------------------------

    def _move_selection(self, delta: int) -> None:
        if not self._result_items:
            return
        if self._selected_idx >= 0:
            self._result_items[self._selected_idx].set_selected(False)
        self._selected_idx = max(
            0, min(len(self._result_items) - 1, self._selected_idx + delta)
        )
        item = self._result_items[self._selected_idx]
        item.set_selected(True)
        self._scroll.ensureWidgetVisible(item)

    def _open_selected(self) -> None:
        if 0 <= self._selected_idx < len(self._result_items):
            self._on_result_clicked(
                self._result_items[self._selected_idx]._article_id
            )

    def _on_result_clicked(self, article_id: int) -> None:
        self.deactivate()
        self.article_selected.emit(article_id)

    # ------------------------------------------------------------------
    # Helpers de fonte
    # ------------------------------------------------------------------

    @staticmethod
    def _mono(size: int) -> QFont:
        f = QFont("Courier Prime")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(size)
        return f

    @staticmethod
    def _title_font(size: int) -> QFont:
        f = QFont("Special Elite")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(size)
        return f
