"""
framing_view.py — Comparação de enquadramento (Fase 7, item 5).

Para uma entidade/tema escolhido, mostra **lado a lado** como fontes de espectros
políticos diferentes a enquadram: por coluna (esquerda → direita → indefinido),
quantos artigos, a distribuição de sentimento, as entidades co-citadas e manchetes
de amostra. Revela contraste de cobertura entre veículos de inclinações distintas.

Decisão de escopo: o agrupamento "mesma história" é feito por **entidade** (reusa o
rastreador de entidades) e o espectro vem do `ai_bias.espectro` por artigo — não há
clustering de evento/história (seria um item à parte). Read-only.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.entities import get_entity_framing, list_entities

log = logging.getLogger("kosmos.framing_view")

_TYPE_LABELS = {"person": "Pessoa", "org": "Organização", "place": "Lugar", "topic": "Tema"}
_SPECTRUM_LABELS = {
    "esquerda": "Esquerda", "centro-esquerda": "Centro-esquerda", "centro": "Centro",
    "centro-direita": "Centro-direita", "direita": "Direita", "indefinido": "Indefinido",
}


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d/%m")
    except Exception:
        return iso[:10]


class FramingView(QWidget):
    """Comparação de enquadramento por espectro político, lado a lado."""

    article_selected = Signal(int)  # reservado: abrir manchete na Leitura (futuro)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._columns: list[QWidget] = []
        self._setup_ui()
        log.debug("FramingView inicializada.")

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Entidade:"))
        self._entity_combo = QComboBox()
        self._entity_combo.setObjectName("framing_entity")
        self._entity_combo.currentIndexChanged.connect(lambda _i: self._render())
        top.addWidget(self._entity_combo, 1)
        self._refresh_btn = QPushButton("Atualizar")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(lambda: self.reload())
        top.addWidget(self._refresh_btn)
        layout.addLayout(top)

        self._info = QLabel("Nenhuma entidade rastreada ainda — analise artigos para começar.")
        self._info.setObjectName("framing_info")
        self._info.setWordWrap(True)
        layout.addWidget(self._info)

        # Área rolável horizontal com uma coluna por espectro
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cols_host = QWidget()
        self._cols_layout = QHBoxLayout(self._cols_host)
        self._cols_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._cols_host)
        layout.addWidget(self._scroll, 1)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def reload(self, conn: sqlite3.Connection | None = None) -> None:
        """Recarrega entidades (preservando seleção) e re-renderiza as colunas."""
        prev = self._entity_combo.currentData()
        self._entity_combo.blockSignals(True)
        self._entity_combo.clear()
        for r in list_entities(conn):
            tipo = _TYPE_LABELS.get(r["entity_type"], r["entity_type"])
            self._entity_combo.addItem(f"{r['name']}  ·  {tipo}  ({r['article_count']})", r["id"])
        if prev is not None:
            idx = self._entity_combo.findData(prev)
            if idx >= 0:
                self._entity_combo.setCurrentIndex(idx)
        self._entity_combo.blockSignals(False)

        has = self._entity_combo.count() > 0
        self._info.setVisible(not has)
        self._scroll.setVisible(has)
        if has:
            self._render(conn)
        else:
            self._clear_columns()
        log.debug("FramingView: %d entidade(s) no seletor.", self._entity_combo.count())

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _clear_columns(self) -> None:
        while self._cols_layout.count():
            item = self._cols_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._columns = []

    def _render(self, conn: sqlite3.Connection | None = None) -> None:
        entity_id = self._entity_combo.currentData()
        self._clear_columns()
        if entity_id is None:
            return
        framing = get_entity_framing(int(entity_id), conn=conn)
        if not framing:
            lbl = QLabel("Sem artigos analisados para esta entidade ainda.")
            lbl.setObjectName("framing_empty")
            self._cols_layout.addWidget(lbl)
            return
        for espectro, g in framing.items():
            self._cols_layout.addWidget(self._make_column(espectro, g))
        self._cols_layout.addStretch(1)

    def _make_column(self, espectro: str, g: dict) -> QWidget:
        col = QFrame()
        col.setObjectName("framing_column")
        col.setProperty("spectrum", espectro)
        col.setMinimumWidth(220)
        col.setMaximumWidth(280)
        v = QVBoxLayout(col)

        header = QLabel(f"{_SPECTRUM_LABELS.get(espectro, espectro)}  ({g['count']})")
        header.setObjectName("framing_col_header")
        v.addWidget(header)

        s = g["sentiment"]
        v.addWidget(QLabel(
            f"Sentimento — +{s['positivo']} · ={s['neutro']} · −{s['negativo']}"
        ))

        co = g.get("co_entities") or []
        if co:
            v.addWidget(QLabel("Também citados: " + ", ".join(f"{n} ({c})" for n, c in co)))

        v.addWidget(QLabel("Manchetes:"))
        hl = QListWidget()
        hl.setObjectName("framing_headlines")
        for h in g.get("headlines") or []:
            tag = f"[{h['ai_sentiment']}] " if h.get("ai_sentiment") else ""
            hl.addItem(QListWidgetItem(f"{_fmt_date(h['published_at'])} · {h['feed']} · {tag}{h['title']}"))
        v.addWidget(hl, 1)

        self._columns.append(col)
        return col
