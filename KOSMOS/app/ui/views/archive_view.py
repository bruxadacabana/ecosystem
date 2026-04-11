"""View de arquivo — artigos exportados para Markdown."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

if TYPE_CHECKING:
    from app.core.feed_manager import FeedManager

log = logging.getLogger("kosmos.ui.archive")


class ArchiveView(QWidget):
    """View do arquivo de artigos exportados para Markdown.

    Sinais:
        back_requested() — voltar ao dashboard.
    """

    back_requested = pyqtSignal()

    def __init__(self, feed_manager: "FeedManager", parent=None) -> None:
        super().__init__(parent)
        self._fm = feed_manager
        self.setObjectName("feedListView")
        self._build_ui()

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("listSeparator")
        root.addWidget(sep)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._content = QWidget()
        self._content.setObjectName("cardsContainer")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(32, 24, 32, 24)
        self._content_layout.setSpacing(8)

        self._scroll.setWidget(self._content)
        root.addWidget(self._scroll)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("feedListHeader")
        header.setFixedHeight(52)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        back_btn = QPushButton("←  Dashboard")
        back_btn.setObjectName("backButton")
        back_btn.setFlat(True)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setFont(self._mono(11))
        back_btn.clicked.connect(self.back_requested.emit)
        layout.addWidget(back_btn)

        title = QLabel("Arquivo")
        title.setObjectName("feedListTitle")
        f = QFont("Special Elite")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(16)
        title.setFont(f)
        layout.addWidget(title, 1)

        self._export_btn = QPushButton("Exportar artigo atual")
        self._export_btn.setFont(self._mono(11))
        self._export_btn.setEnabled(False)
        self._export_btn.setToolTip("Abra um artigo no leitor para exportá-lo")
        layout.addWidget(self._export_btn)

        return header

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Varre data/archive/ e exibe os arquivos Markdown encontrados."""
        self._refresh_list()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _refresh_list(self) -> None:
        from app.utils.paths import Paths
        archive_dir: Path = Paths.DATA / "archive"

        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        md_files = sorted(archive_dir.glob("**/*.md"), key=lambda p: p.stat().st_mtime, reverse=True) if archive_dir.exists() else []

        if not md_files:
            msg = QLabel(
                "Nenhum artigo arquivado ainda.\n\n"
                "Para exportar um artigo para Markdown, abra-o no leitor\n"
                "e use o botão  Exportar  na toolbar."
            )
            msg.setObjectName("emptyLabel")
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            msg.setContentsMargins(0, 40, 0, 0)
            self._content_layout.addWidget(msg)
            self._content_layout.addStretch()
            return

        mono = self._mono(11)
        for md_path in md_files:
            row = QWidget()
            row.setObjectName("archiveRow")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 4, 0, 4)

            lbl = QLabel(md_path.stem)
            lbl.setFont(mono)
            lbl.setObjectName("cardTitle")
            hl.addWidget(lbl, 1)

            size_kb = md_path.stat().st_size // 1024
            meta = QLabel(f"{size_kb} KB  ·  {md_path.parent.name}")
            meta.setObjectName("cardMeta")
            meta.setFont(self._mono(10))
            hl.addWidget(meta)

            open_btn = QPushButton("Abrir pasta")
            open_btn.setFont(self._mono(10))
            open_btn.clicked.connect(lambda _c, p=md_path.parent: self._open_folder(p))
            hl.addWidget(open_btn)

            self._content_layout.addWidget(row)

            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setObjectName("cardSeparator")
            self._content_layout.addWidget(sep)

        self._content_layout.addStretch()

    @staticmethod
    def _open_folder(path: Path) -> None:
        import subprocess, sys
        try:
            if sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["explorer", str(path)])
        except Exception as exc:
            log.warning("Não foi possível abrir pasta: %s", exc)

    @staticmethod
    def _mono(size: int) -> QFont:
        f = QFont("Courier Prime")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(size)
        return f
