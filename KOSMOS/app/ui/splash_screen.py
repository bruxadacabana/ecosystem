from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.theme.cosmos_painter import paint_cosmos

log = logging.getLogger("kosmos.splash")


class SplashScreen(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.SplashScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(480, 320)
        self._cosmos = paint_cosmos(480, 320, theme="day")
        self._center_on_screen()
        self._setup_ui()
        log.debug("SplashScreen criada.")

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.center().x() - 240, geo.center().y() - 160)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 40, 32, 24)
        layout.setSpacing(0)

        title = QLabel("KOSMOS")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont("Special Elite", 52)
        title.setFont(title_font)
        title.setStyleSheet("color: #2C2416; background: transparent;")

        subtitle = QLabel("Agregador de Notícias e Feeds")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_font = QFont("Courier Prime", 13)
        subtitle.setFont(sub_font)
        subtitle.setStyleSheet("color: #6B5A3E; background: transparent;")

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminado
        self._progress.setFixedHeight(5)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet("""
            QProgressBar {
                background: #d4c4a0;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: #8B7355;
                border-radius: 2px;
            }
        """)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(spacer)
        layout.addWidget(self._progress)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._cosmos)

    def finish(self, main_window: QWidget) -> None:
        log.debug("SplashScreen fechada.")
        self.close()
