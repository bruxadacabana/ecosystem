"""
nav_rail.py — Barra de navegação à esquerda (design antigo do KOSMOS).

Navegação por páginas: cabeçalho com campo estelar, título KOSMOS, botões de
atualizar (↻) e adicionar feed (+), e itens de navegação que trocam a página
ativa no QStackedWidget da MainWindow.

Portado do design pré-v3 (era PyQt6 → agora PySide6) e re-wired ao shell v3.
Object names usam o prefixo ``nav*`` para não colidir com o ``#sidebar`` do
FeedSidebar do v3 (que vive dentro da página de Leitura).

Sinais:
    nav_requested(view)    — item de navegação clicado (nome da página, inclui "settings").
    add_feed_requested()   — botão "+" clicado.
    refresh_requested()    — botão "↻" clicado.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.theme.cosmos_painter import paint_cosmos

log = logging.getLogger("kosmos.ui.nav_rail")


class _CosmosHeader(QWidget):
    """Cabeçalho do nav rail com campo estelar de fundo (design antigo)."""

    def __init__(self, theme: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setObjectName("navRailHeader")
        self.setFixedHeight(46)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            pix = paint_cosmos(self.width(), self.height(), theme=self._theme)
            painter.drawPixmap(0, 0, pix)
        finally:
            painter.end()
        super().paintEvent(event)


class _Divider(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("navDivider")
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class NavRail(QWidget):
    """Barra de navegação por páginas do KOSMOS (design antigo)."""

    nav_requested = Signal(str)
    add_feed_requested = Signal()
    refresh_requested = Signal()

    def __init__(self, theme: str = "day", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._active_btn: QPushButton | None = None
        self._buttons: dict[str, QPushButton] = {}
        self.setObjectName("navRail")
        self.setFixedWidth(220)
        self._build_ui()

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = _CosmosHeader(self._theme)
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 0, 8, 0)
        h.setSpacing(0)

        title = QPushButton("KOSMOS")
        title.setObjectName("navRailTitle")
        title.setFlat(True)
        title.setCursor(Qt.CursorShape.PointingHandCursor)
        tf = QFont("Special Elite")
        if not tf.exactMatch():
            tf = QFont("Courier New")
        tf.setPointSize(15)
        title.setFont(tf)
        title.clicked.connect(lambda: self._select("dashboard"))
        h.addWidget(title, 1)

        refresh_btn = QPushButton("↻")
        refresh_btn.setObjectName("navIconBtn")
        refresh_btn.setFixedSize(24, 24)
        refresh_btn.setFlat(True)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setToolTip("Recarregar feeds e artigos")
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        h.addWidget(refresh_btn)

        add_btn = QPushButton("+")
        add_btn.setObjectName("navIconBtn")
        add_btn.setFixedSize(24, 24)
        add_btn.setFlat(True)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("Adicionar feed")
        add_btn.clicked.connect(self.add_feed_requested.emit)
        h.addWidget(add_btn)

        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setObjectName("navRailScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setObjectName("navRailContent")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 6, 0, 6)
        cl.setSpacing(1)

        # Itens que mapeiam para conteúdo v3 existente.
        cl.addWidget(self._nav_btn("★", "Dashboard", "dashboard"))
        cl.addWidget(self._nav_btn("☰", "Leitura", "leitura"))
        cl.addWidget(self._nav_btn("♥", "Salvos", "salvos"))
        cl.addWidget(self._nav_btn("⊞", "Fontes", "fontes"))
        cl.addWidget(self._nav_btn("≡", "Análise", "analise"))
        cl.addSpacing(4)
        cl.addWidget(_Divider())
        cl.addSpacing(4)
        cl.addWidget(self._nav_btn("⚙", "Configurações", "settings"))
        cl.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _nav_btn(self, icon: str, label: str, view: str) -> QPushButton:
        btn = QPushButton(f"  {icon}  {label}")
        btn.setObjectName("navItem")
        btn.setFlat(True)
        btn.setFixedHeight(32)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setCheckable(True)
        f = QFont("Courier Prime")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(12)
        btn.setFont(f)
        btn.clicked.connect(lambda _checked=False, v=view: self._on_clicked(v))
        self._buttons[view] = btn
        return btn

    # ------------------------------------------------------------------
    # Navegação
    # ------------------------------------------------------------------

    def _on_clicked(self, view: str) -> None:
        self._select(view)

    def _select(self, view: str) -> None:
        """Marca o item como ativo e emite nav_requested(view)."""
        btn = self._buttons.get(view)
        if btn is None:
            return
        if self._active_btn is not None and self._active_btn is not btn:
            self._active_btn.setChecked(False)
        btn.setChecked(True)
        self._active_btn = btn
        log.debug("Nav: página '%s' solicitada.", view)
        self.nav_requested.emit(view)

    def set_active(self, view: str) -> None:
        """Marca um item como ativo SEM emitir o sinal (sincroniza com mudança externa)."""
        btn = self._buttons.get(view)
        if btn is None:
            return
        if self._active_btn is not None and self._active_btn is not btn:
            self._active_btn.setChecked(False)
        btn.setChecked(True)
        self._active_btn = btn
