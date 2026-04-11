"""Dialog para descobrir novas fontes RSS por palavra-chave ou tema."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
    QComboBox, QMessageBox,
)

if TYPE_CHECKING:
    from app.core.feed_discovery import FeedCandidate
    from app.core.feed_manager import FeedManager

log = logging.getLogger("kosmos.ui.discover")

_TOPICS = [
    "Notícias mundiais",
    "Política",
    "Economia",
    "Tecnologia",
    "Ciência",
    "Saúde",
    "Meio ambiente",
    "Esporte",
    "Cultura",
    "Brasil",
    "América Latina",
    "Europa",
    "Ásia",
    "África",
    "Inteligência Artificial",
    "Astronomia",
    "Programação",
]


class _WrapWidget(QWidget):
    """Distribui widgets filhos em linhas que quebram automaticamente."""

    def __init__(self, h_spacing: int = 6, v_spacing: int = 6, parent=None) -> None:
        super().__init__(parent)
        self._h = h_spacing
        self._v = v_spacing
        self._items: list[QWidget] = []

    def add_widget(self, w: QWidget) -> None:
        w.setParent(self)
        self._items.append(w)

    def sizeHint(self) -> QSize:
        h = self._layout(QRect(0, 0, self.width() or 640, 0), apply=False)
        return QSize(self.width(), h)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        h = self._layout(self.contentsRect(), apply=True)
        self.setMinimumHeight(h)

    def _layout(self, rect: QRect, apply: bool) -> int:
        x, y, row_h = rect.x(), rect.y(), 0
        for w in self._items:
            hint = w.sizeHint()
            ww = max(hint.width(), 1)
            wh = max(hint.height(), 1)
            if x + ww > rect.right() and x > rect.x():
                x = rect.x()
                y += row_h + self._v
                row_h = 0
            if apply:
                w.setGeometry(x, y, ww, wh)
                w.show()
            x += ww + self._h
            row_h = max(row_h, wh)
        return (y + row_h - rect.y()) if self._items else 0


class _ResultCard(QWidget):
    """Card de resultado com info do feed e botão Adicionar."""

    add_requested = pyqtSignal(str, str)   # url, title

    def __init__(self, candidate: "FeedCandidate", parent=None) -> None:
        super().__init__(parent)
        self._candidate = candidate
        self._added     = False
        self.setObjectName("discoveryCard")
        self._build_ui()
        self._setup_hover()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        mono  = self._font("Courier Prime", 10)
        serif = self._font("IM Fell English", 11, serif=True)
        title_font = self._font("Special Elite", 13)

        # Info (esquerda)
        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(2)

        title_lbl = QLabel(self._candidate.title)
        title_lbl.setObjectName("discoveryTitle")
        title_lbl.setFont(title_font)
        title_lbl.setWordWrap(True)
        info.addWidget(title_lbl)

        # Meta: assinantes · idioma · domínio
        meta_parts: list[str] = []
        if self._candidate.subscribers:
            meta_parts.append(f"{self._candidate.subscribers:,} assinantes")
        if self._candidate.language:
            meta_parts.append(self._candidate.language.upper())
        if self._candidate.website:
            meta_parts.append(self._candidate.website)
        if meta_parts:
            meta_lbl = QLabel("  ·  ".join(meta_parts))
            meta_lbl.setObjectName("discoveryMeta")
            meta_lbl.setFont(mono)
            info.addWidget(meta_lbl)

        if self._candidate.description:
            desc_text = self._candidate.description[:160]
            if len(self._candidate.description) > 160:
                desc_text += "…"
            desc_lbl = QLabel(desc_text)
            desc_lbl.setObjectName("discoveryDesc")
            desc_lbl.setFont(serif)
            desc_lbl.setWordWrap(True)
            info.addWidget(desc_lbl)

        layout.addLayout(info, 1)

        # Botão Adicionar (direita)
        self._add_btn = QPushButton("Adicionar")
        self._add_btn.setObjectName("addSourceBtn")
        self._add_btn.setFont(mono)
        self._add_btn.setFixedWidth(100)
        self._add_btn.clicked.connect(self._on_add)
        layout.addWidget(self._add_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    def _on_add(self) -> None:
        if not self._added:
            self._added = True
            self._add_btn.setText("✓ Adicionado")
            self._add_btn.setEnabled(False)
            self.add_requested.emit(self._candidate.url, self._candidate.title)

    def mark_added(self) -> None:
        self._added = True
        self._add_btn.setText("✓ Adicionado")
        self._add_btn.setEnabled(False)

    def _setup_hover(self) -> None:
        self.setMouseTracking(True)

    def enterEvent(self, event) -> None:
        self.setProperty("hovered", "true")
        self.style().unpolish(self)
        self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setProperty("hovered", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)

    @staticmethod
    def _font(family: str, size: int, serif: bool = False) -> QFont:
        f = QFont(family)
        if not f.exactMatch():
            f = QFont("Georgia" if serif else "Courier New")
        f.setPointSize(size)
        return f


class DiscoverFeedsDialog(QDialog):
    """Dialog de descoberta de feeds por palavra-chave ou tema pré-definido.

    O usuário pode digitar uma busca livre ou clicar num dos temas rápidos.
    Os resultados vêm da API pública do Feedly (sem necessidade de conta).
    """

    def __init__(self, feed_manager: "FeedManager", parent=None) -> None:
        super().__init__(parent)
        self._fm = feed_manager
        self._worker  = None
        self._cards:  list[_ResultCard] = []
        self._existing_urls: set[str] = {
            f.url for f in feed_manager.get_feeds()
        }

        self.setWindowTitle("Descobrir Novas Fontes")
        self.setMinimumSize(680, 600)
        self.resize(720, 660)

        self._build_ui()

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_search_bar())
        root.addWidget(self._build_topics())

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("listSeparator")
        root.addWidget(sep)

        root.addWidget(self._build_results_area(), 1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("feedListHeader")
        widget.setFixedHeight(52)

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel("Descobrir Novas Fontes")
        title.setObjectName("feedListTitle")
        f = QFont("Special Elite")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(16)
        title.setFont(f)
        layout.addWidget(title)
        return widget

    def _build_search_bar(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(20, 12, 20, 8)
        layout.setSpacing(8)

        mono = self._mono(12)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Buscar por palavra-chave ou tema…")
        self._search_input.setFont(mono)
        self._search_input.returnPressed.connect(self._do_search)
        layout.addWidget(self._search_input, 1)

        search_btn = QPushButton("Buscar")
        search_btn.setFont(mono)
        search_btn.clicked.connect(self._do_search)
        layout.addWidget(search_btn)

        # Seletor de categoria para adicionar
        self._cat_combo = QComboBox()
        self._cat_combo.setFont(self._mono(11))
        self._cat_combo.setMinimumWidth(160)
        self._cat_combo.setToolTip("Categoria para os feeds adicionados")
        self._refresh_categories()
        layout.addWidget(self._cat_combo)

        return widget

    def _build_topics(self) -> QWidget:
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(20, 4, 20, 10)
        layout.setSpacing(6)

        lbl = QLabel("Temas:")
        lbl.setObjectName("cardMeta")
        lbl.setFont(self._mono(10))
        layout.addWidget(lbl)

        wrap = _WrapWidget(h_spacing=6, v_spacing=5)
        for topic in _TOPICS:
            btn = QPushButton(topic)
            btn.setObjectName("topicBtn")
            btn.setFont(self._mono(10))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c, t=topic: self._search_topic(t))
            wrap.add_widget(btn)

        layout.addWidget(wrap)
        return outer

    def _build_results_area(self) -> QWidget:
        self._scroll = QScrollArea()
        self._scroll.setObjectName("settingsScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._results_widget = QWidget()
        self._results_widget.setObjectName("cardsContainer")
        self._results_layout = QVBoxLayout(self._results_widget)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(0)
        self._results_layout.addStretch()

        self._status_lbl = QLabel("Digite uma busca ou escolha um tema acima.")
        self._status_lbl.setObjectName("emptyLabel")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setContentsMargins(0, 40, 0, 0)
        self._results_layout.insertWidget(0, self._status_lbl)

        self._scroll.setWidget(self._results_widget)
        return self._scroll

    def _build_footer(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("feedListHeader")
        widget.setFixedHeight(48)

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(20, 0, 20, 0)

        self._info_lbl = QLabel("")
        self._info_lbl.setObjectName("dialogStatusLabel")
        self._info_lbl.setFont(self._mono(10))
        layout.addWidget(self._info_lbl, 1)

        close_btn = QPushButton("Fechar")
        close_btn.setFont(self._mono(11))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        return widget

    # ------------------------------------------------------------------
    # Busca
    # ------------------------------------------------------------------

    def _search_topic(self, topic: str) -> None:
        self._search_input.setText(topic)
        self._do_search()

    def _do_search(self) -> None:
        query = self._search_input.text().strip()
        if not query:
            return

        # Parar worker anterior
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(1000)

        self._clear_results()
        self._status_lbl.setText(f'Buscando "{query}"…')
        self._status_lbl.setVisible(True)
        self._info_lbl.setText("")

        from app.core.feed_discovery import DiscoveryWorker
        self._worker = DiscoveryWorker(query, count=20)
        self._worker.results_ready.connect(self._on_results)
        self._worker.search_error.connect(self._on_error)
        self._worker.start()

    def _on_results(self, candidates: list) -> None:
        self._clear_results()

        if not candidates:
            self._status_lbl.setText("Nenhuma fonte encontrada. Tente outros termos.")
            self._status_lbl.setVisible(True)
            return

        self._status_lbl.setVisible(False)
        self._cards.clear()

        for candidate in candidates:
            card = _ResultCard(candidate)
            card.add_requested.connect(self._on_add_feed)

            # Marcar já adicionados
            if candidate.url in self._existing_urls:
                card.mark_added()

            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setObjectName("cardSeparator")

            idx = self._results_layout.count() - 1
            self._results_layout.insertWidget(idx, card)
            self._results_layout.insertWidget(idx + 1, sep)
            self._cards.append(card)

        self._info_lbl.setText(f"{len(candidates)} fonte(s) encontrada(s)")

    def _on_error(self, error: str) -> None:
        self._status_lbl.setText(
            f"Erro ao buscar fontes: {error}\n"
            "Verifique sua conexão com a internet."
        )
        self._status_lbl.setVisible(True)

    def _on_add_feed(self, url: str, title: str) -> None:
        cat_id = self._cat_combo.currentData()
        try:
            self._fm.add_feed(url=url, name=title, feed_type="rss", category_id=cat_id)
            self._existing_urls.add(url)
            log.info("Feed adicionado via discovery: %r", title)
        except Exception as exc:
            log.warning("Erro ao adicionar feed %r: %s", title, exc)
            QMessageBox.warning(
                self, "Erro", f"Não foi possível adicionar o feed:\n{exc}"
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clear_results(self) -> None:
        # Índice 0 = status_lbl (preservar), último = stretch (preservar)
        while self._results_layout.count() > 2:
            item = self._results_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

    def _refresh_categories(self) -> None:
        self._cat_combo.clear()
        self._cat_combo.addItem("(sem categoria)", None)
        for cat in self._fm.get_categories():
            self._cat_combo.addItem(cat.name, cat.id)

    @staticmethod
    def _mono(size: int) -> QFont:
        f = QFont("Courier Prime")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(size)
        return f
