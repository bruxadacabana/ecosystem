from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QFont


class SplashScreen(QWidget):
    """Splash screen de abertura do KOSMOS — frameless, 520×340px."""

    def __init__(self, theme_manager) -> None:
        super().__init__()
        self._theme = theme_manager

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SplashScreen
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(520, 340)
        self._center_on_screen()
        self._setup_ui()

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width()  - self.width())  // 2,
            (screen.height() - self.height()) // 2,
        )

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(52, 44, 52, 28)
        layout.setSpacing(0)

        is_night = self._theme.current == "night"
        text_color  = "#E8DFC8" if is_night else "#2C2416"
        sub_color   = "#7A7260" if is_night else "#9C8E7A"

        layout.addStretch(2)

        # Título em IM Fell English italic
        title = QLabel("KOSMOS")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {text_color}; background: transparent;")
        font = QFont("IM Fell English")
        if not font.exactMatch():
            font = QFont("Georgia")
        font.setPointSize(52)
        font.setItalic(True)
        title.setFont(font)
        layout.addWidget(title)

        layout.addSpacing(8)

        # Subtítulo em Special Elite com letter-spacing simulado por espaços
        subtitle = QLabel("A G R E G A D O R   D E   N O T Í C I A S")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"color: {sub_color}; background: transparent;")
        sub_font = QFont("Special Elite")
        if not sub_font.exactMatch():
            sub_font = QFont("Courier New")
        sub_font.setPointSize(8)
        subtitle.setFont(sub_font)
        layout.addWidget(subtitle)

        layout.addStretch(3)

        # Barra de progresso
        accent = "#D4A820" if is_night else "#b8860b"
        track  = "#252B3A" if is_night else "#D5CCBA"
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(3)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {track};
                border: none;
                border-radius: 1px;
            }}
            QProgressBar::chunk {{
                background-color: {accent};
                border-radius: 1px;
            }}
        """)
        layout.addWidget(self._progress_bar)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_night = self._theme.current == "night"
        bg_color  = "#12161E" if is_night else "#F5F0E8"
        brd_color = "#2E3445" if is_night else "#C4B9A8"

        painter.fillRect(self.rect(), QColor(bg_color))

        from app.ui.widgets.cosmos_painter import paint_cosmos
        paint_cosmos(
            painter, self.width(), self.height(),
            theme=self._theme.current,
            density="rich",
        )

        pen = QPen(QColor(brd_color))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        painter.end()

    def set_progress(self, value: int) -> None:
        self._progress_bar.setValue(max(0, min(100, value)))

    def finish(self, window: QWidget) -> None:
        self._progress_bar.setValue(100)
        QTimer.singleShot(150, self.close)
