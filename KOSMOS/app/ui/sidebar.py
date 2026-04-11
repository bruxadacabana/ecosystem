"""Sidebar dinâmica com categorias, feeds e navegação principal."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPainter
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

if TYPE_CHECKING:
    from app.core.feed_manager import FeedManager

log = logging.getLogger("kosmos.ui.sidebar")


class _CosmosHeader(QWidget):
    """Cabeçalho da sidebar com campo estelar de fundo."""

    def __init__(self, theme_manager, parent=None) -> None:
        super().__init__(parent)
        self._theme = theme_manager
        self.setObjectName("sidebarHeader")
        self.setFixedHeight(46)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        from app.ui.widgets.cosmos_painter import paint_cosmos
        paint_cosmos(
            painter, self.width(), self.height(),
            theme=self._theme.current,
            density="sparse",
        )
        painter.end()
        super().paintEvent(event)


class _Divider(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebarDivider")
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class Sidebar(QWidget):
    """Sidebar de navegação — categorias, feeds e seções de sistema.

    Sinais:
        nav_requested(view_name)         — navegar para uma view pelo nome.
        feed_selected(feed_id)           — feed clicado.
        add_feed_requested()             — botão "+" clicado.
        feed_context(feed_id, pos)       — menu de contexto de um feed.
    """

    nav_requested      = pyqtSignal(str)
    add_feed_requested = pyqtSignal()
    refresh_requested  = pyqtSignal()

    def __init__(self, theme_manager, feed_manager: "FeedManager", parent=None) -> None:
        super().__init__(parent)
        self._theme       = theme_manager
        self._fm          = feed_manager
        self._active_btn: QPushButton | None = None

        self.setObjectName("sidebar")
        self._build_ui()

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Cabeçalho KOSMOS + botão "+"
        header = _CosmosHeader(self._theme)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 0, 8, 0)
        h_layout.setSpacing(0)

        title_lbl = QPushButton("KOSMOS")
        title_lbl.setObjectName("sidebarAppName")
        title_lbl.setFlat(True)
        title_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        title_font = QFont("Special Elite")
        if not title_font.exactMatch():
            title_font = QFont("Courier New")
        title_font.setPointSize(15)
        title_lbl.setFont(title_font)
        title_lbl.clicked.connect(lambda: self.nav_requested.emit("dashboard"))
        h_layout.addWidget(title_lbl, 1)

        refresh_btn = QPushButton("↻")
        refresh_btn.setObjectName("addFeedBtn")
        refresh_btn.setFixedSize(24, 24)
        refresh_btn.setFlat(True)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setToolTip("Atualizar feeds agora")
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        h_layout.addWidget(refresh_btn)

        add_btn = QPushButton("+")
        add_btn.setObjectName("addFeedBtn")
        add_btn.setFixedSize(24, 24)
        add_btn.setFlat(True)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("Adicionar feed")
        add_btn.clicked.connect(self.add_feed_requested.emit)
        h_layout.addWidget(add_btn)

        outer.addWidget(header)

        # Área rolável
        scroll = QScrollArea()
        scroll.setObjectName("sidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.viewport().setStyleSheet("background: transparent;")

        self._content = QWidget()
        self._content.setObjectName("sidebarContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 6, 0, 6)
        self._content_layout.setSpacing(1)

        self._build_static_top()
        self._content_layout.addStretch()
        self._build_static_bottom()

        scroll.setWidget(self._content)
        outer.addWidget(scroll)

    def _build_static_top(self) -> None:
        cl = self._content_layout

        self._all_unread_btn = self._nav_btn("\u2605", "Dashboard", "all_unread")
        cl.addWidget(self._all_unread_btn)

        self._feeds_btn = self._nav_btn("\u2630", "Feeds", "feeds")
        cl.addWidget(self._feeds_btn)

        self._sources_btn = self._nav_btn("\u229e", "Fontes", "sources")
        cl.addWidget(self._sources_btn)

        self._saved_btn = self._nav_btn("\u2665", "Salvos", "saved")
        cl.addWidget(self._saved_btn)

        self._archive_btn = self._nav_btn("\u25a6", "Arquivo", "archive")
        cl.addWidget(self._archive_btn)

        cl.addSpacing(4)
        cl.addWidget(_Divider())

    def _build_static_bottom(self) -> None:
        cl = self._content_layout
        cl.addSpacing(4)
        cl.addWidget(self._nav_btn("\u2261", "Estatísticas",  "stats"))
        cl.addWidget(self._nav_btn("\u2699", "Configurações", "settings"))

    # ------------------------------------------------------------------
    # Compatibilidade (chamados por MainWindow / BackgroundUpdater)
    # ------------------------------------------------------------------

    def refresh_feeds(self) -> None:
        """Sem-op — feeds agora são gerenciados na UnifiedFeedView."""

    def update_badge(self, feed_id: int, count: int | None = None) -> None:
        """Sem-op — badges individuais removidos da sidebar."""

    def update_all_badges(self) -> None:
        """Sem-op — badges individuais removidos da sidebar."""

    # ------------------------------------------------------------------
    # Helpers e eventos
    # ------------------------------------------------------------------

    def _nav_btn(self, icon: str, label: str, view: str) -> QPushButton:
        btn = QPushButton(f"  {icon}  {label}")
        btn.setObjectName("sidebarNavItem")
        btn.setFlat(True)
        btn.setFixedHeight(32)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setCheckable(True)
        font = QFont("Courier Prime")
        if not font.exactMatch():
            font = QFont("Courier New")
        font.setPointSize(12)
        btn.setFont(font)
        btn.clicked.connect(lambda _c, b=btn, v=view: self._on_nav_clicked(b, v))
        return btn

    def _on_nav_clicked(self, btn: QPushButton, view: str) -> None:
        if self._active_btn and self._active_btn is not btn:
            self._active_btn.setChecked(False)
        self._active_btn = btn
        self.nav_requested.emit(view)

