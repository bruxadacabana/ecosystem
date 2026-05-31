"""
Mnemosyne — StudioTileWidget: card persistente de output do Studio.

Exibe type badge colorido, título, preview de 80 chars e data.
Botões ✏ e 🗑 aparecem no hover.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.studio_output import StudioOutput

_TYPE_COLORS: dict[str, str] = {
    "Briefing":      "#4A90D9",
    "Relatório":     "#4A90D9",
    "FAQ":           "#4CAF50",
    "Guide":         "#9C27B0",
    "Guia de Estudo":"#9C27B0",
    "Flashcards":    "#FF9800",
    "Tabela de Dados":"#E67E22",
    "Linha do Tempo":"#1ABC9C",
    "Índice de Temas":"#3498DB",
    "Blog Post":     "#E91E63",
    "Mind Map":      "#795548",
    "Slides":        "#607D8B",
}
_DEFAULT_COLOR = "#9A9080"


class StudioTileWidget(QWidget):
    """Card de um output persistente do Studio."""

    output_opened: Signal = Signal(object)          # StudioOutput
    output_deleted: Signal = Signal(str)            # output_id
    export_pptx_requested: Signal = Signal(object)  # StudioOutput (só tipo Slides)

    def __init__(self, output: StudioOutput, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._output = output
        self.setObjectName("studioTile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build_ui()
        self._set_action_buttons_visible(False)

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        # Badge de tipo
        badge = QLabel(self._output.type)
        badge.setObjectName("studioBadge")
        color = _TYPE_COLORS.get(self._output.type, _DEFAULT_COLOR)
        badge.setStyleSheet(
            f"background: {color}; color: #FFFFFF; border-radius: 4px;"
            " padding: 2px 7px; font-size: 11px; font-weight: bold;"
        )
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedHeight(22)
        root.addWidget(badge)

        # Coluna central: título + preview + data
        col = QVBoxLayout()
        col.setSpacing(2)

        title_text = self._output.title or self._output.type
        self._title_lbl = QLabel(title_text)
        self._title_lbl.setObjectName("studioTileTitle")
        self._title_lbl.setWordWrap(False)
        col.addWidget(self._title_lbl)

        preview = self._output.content[:80].replace("\n", " ")
        if len(self._output.content) > 80:
            preview += "…"
        preview_lbl = QLabel(preview)
        preview_lbl.setObjectName("studioTilePreview")
        preview_lbl.setWordWrap(False)
        col.addWidget(preview_lbl)

        date_str = self._output.created_at[:16].replace("T", " ")
        date_lbl = QLabel(date_str)
        date_lbl.setObjectName("studioTileDate")
        col.addWidget(date_lbl)

        root.addLayout(col, 1)

        # Botões de ação (hover)
        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)

        self._edit_btn = QPushButton("✏")
        self._edit_btn.setObjectName("studioTileBtn")
        self._edit_btn.setFixedSize(28, 28)
        self._edit_btn.setToolTip("Abrir output")
        self._edit_btn.clicked.connect(lambda: self.output_opened.emit(self._output))

        self._del_btn = QPushButton("🗑")
        self._del_btn.setObjectName("studioTileBtn")
        self._del_btn.setFixedSize(28, 28)
        self._del_btn.setToolTip("Apagar output")
        self._del_btn.clicked.connect(self._confirm_delete)

        btn_col.addWidget(self._edit_btn)
        btn_col.addWidget(self._del_btn)

        if self._output.type == "Slides":
            self._pptx_btn: QPushButton | None = QPushButton("↓")
            self._pptx_btn.setObjectName("studioTileBtn")
            self._pptx_btn.setFixedSize(28, 28)
            self._pptx_btn.setToolTip("Exportar .pptx")
            self._pptx_btn.clicked.connect(
                lambda: self.export_pptx_requested.emit(self._output)
            )
            btn_col.addWidget(self._pptx_btn)
        else:
            self._pptx_btn = None

        root.addLayout(btn_col)

    # ------------------------------------------------------------------
    # Hover
    # ------------------------------------------------------------------

    def enterEvent(self, event) -> None:
        self._set_action_buttons_visible(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._set_action_buttons_visible(False)
        super().leaveEvent(event)

    def _set_action_buttons_visible(self, visible: bool) -> None:
        self._edit_btn.setVisible(visible)
        self._del_btn.setVisible(visible)
        if self._pptx_btn is not None:
            self._pptx_btn.setVisible(visible)

    # ------------------------------------------------------------------
    # Deleção
    # ------------------------------------------------------------------

    def _confirm_delete(self) -> None:
        title = self._output.title or self._output.type
        reply = QMessageBox.question(
            self,
            "Apagar output",
            f"Apagar '{title}'?\n\nEsta ação não pode ser desfeita.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.output_deleted.emit(self._output.id)

    # ------------------------------------------------------------------
    # Dados
    # ------------------------------------------------------------------

    @property
    def output(self) -> StudioOutput:
        return self._output
