from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QWidget,
)

from app.utils.config import KosmosConfig, save_config

log = logging.getLogger("kosmos.main_window")


class MainWindow(QMainWindow):
    def __init__(self, config: KosmosConfig) -> None:
        super().__init__()
        self.config = config
        self.setWindowTitle("KOSMOS")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)
        self._setup_ui()
        log.info("MainWindow inicializada.")

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar — substituída por componente real na Fase 2
        self._sidebar = QWidget()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.setFixedWidth(250)
        sidebar_label = QLabel("← feeds aqui (Fase 2)")
        sidebar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_label.setStyleSheet("color: #9C8B6E; font-size: 12px;")
        from PySide6.QtWidgets import QVBoxLayout as _VBox
        _VBox(self._sidebar).addWidget(sidebar_label)

        # Área de conteúdo — dashboard/reader chegam na Fase 3/7
        self._content = QWidget()
        self._content.setObjectName("content")
        content_label = QLabel("KOSMOS v3")
        content_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_label.setStyleSheet(
            "font-family: 'Special Elite', 'Courier New';"
            "font-size: 32px; color: #C4B49A;"
        )
        _VBox(self._content).addWidget(content_label)

        layout.addWidget(self._sidebar)
        layout.addWidget(self._content, 1)

        self.statusBar().showMessage("KOSMOS pronto.")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        try:
            save_config(self.config)
        except OSError as exc:
            log.error("Falha ao salvar config no fechamento: %s", exc)
        event.accept()
