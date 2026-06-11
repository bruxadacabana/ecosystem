"""
coverage_map.py — Mapa de cobertura (Fase 7, item 4).

Para uma entidade/tema escolhido, mostra uma tabela **feed × dia**: cada célula traz
quantos artigos daquele feed mencionaram a entidade naquele dia. Células vazias (zero)
e linhas inteiras zeradas tornam o **silêncio editorial** visualmente evidente — dá para
ver de relance qual veículo cobriu o quê, quando, e quem ficou em silêncio.

As linhas são os feeds **ativos** no período (com ≥1 artigo de qualquer assunto), então
um feed que existe e publica mas nunca tocou no tema aparece com a linha toda zerada.
Read-only: é um panorama, não uma lista de leitura.
"""
from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.entities import get_entity_coverage, list_entities

log = logging.getLogger("kosmos.coverage_map")

_TYPE_LABELS = {"person": "Pessoa", "org": "Organização", "place": "Lugar", "topic": "Tema"}
_WINDOWS = [(7, "7 dias"), (14, "14 dias"), (30, "30 dias")]


class CoverageMap(QWidget):
    """Mapa feed×dia da cobertura de uma entidade. Silêncio editorial visível."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        log.debug("CoverageMap inicializado.")

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Barra superior: entidade + janela + atualizar
        top = QHBoxLayout()
        top.addWidget(QLabel("Entidade:"))
        self._entity_combo = QComboBox()
        self._entity_combo.setObjectName("coverage_entity")
        self._entity_combo.currentIndexChanged.connect(lambda _i: self._render())
        top.addWidget(self._entity_combo, 1)

        top.addWidget(QLabel("Janela:"))
        self._window_combo = QComboBox()
        for days, label in _WINDOWS:
            self._window_combo.addItem(label, days)
        self._window_combo.setCurrentIndex(1)  # 14 dias
        self._window_combo.currentIndexChanged.connect(lambda _i: self._render())
        top.addWidget(self._window_combo)

        self._refresh_btn = QPushButton("Atualizar")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(lambda: self.reload())
        top.addWidget(self._refresh_btn)
        layout.addLayout(top)

        # Aviso/estado vazio
        self._info = QLabel("Nenhuma entidade rastreada ainda — analise artigos para começar.")
        self._info.setObjectName("coverage_info")
        self._info.setWordWrap(True)
        layout.addWidget(self._info)

        # Grade feed × dia
        self._table = QTableWidget()
        self._table.setObjectName("coverage_table")
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.verticalHeader().setVisible(True)
        layout.addWidget(self._table, 1)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def reload(self, conn: sqlite3.Connection | None = None) -> None:
        """Recarrega a lista de entidades (preservando a seleção) e re-renderiza."""
        prev = self._entity_combo.currentData()
        self._entity_combo.blockSignals(True)
        self._entity_combo.clear()
        rows = list_entities(conn)
        for r in rows:
            tipo = _TYPE_LABELS.get(r["entity_type"], r["entity_type"])
            self._entity_combo.addItem(f"{r['name']}  ·  {tipo}  ({r['article_count']})", r["id"])
        # Restaura a seleção anterior, se ainda existir
        if prev is not None:
            idx = self._entity_combo.findData(prev)
            if idx >= 0:
                self._entity_combo.setCurrentIndex(idx)
        self._entity_combo.blockSignals(False)

        has_entities = self._entity_combo.count() > 0
        self._info.setVisible(not has_entities)
        self._table.setVisible(has_entities)
        if has_entities:
            self._render(conn)
        else:
            self._table.clear()
            self._table.setRowCount(0)
            self._table.setColumnCount(0)
        log.debug("CoverageMap: %d entidade(s) no seletor.", self._entity_combo.count())

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _render(self, conn: sqlite3.Connection | None = None) -> None:
        entity_id = self._entity_combo.currentData()
        if entity_id is None:
            return
        days = self._window_combo.currentData() or 14
        data = get_entity_coverage(int(entity_id), days=int(days), conn=conn)
        day_list = data["days"]
        feeds = data["feeds"]
        counts = data["counts"]

        self._table.clear()
        self._table.setColumnCount(len(day_list))
        self._table.setRowCount(len(feeds))
        self._table.setHorizontalHeaderLabels([f"{d[8:10]}/{d[5:7]}" for d in day_list])
        self._table.setVerticalHeaderLabels([f["title"] for f in feeds])

        max_n = max([n for n in counts.values()], default=0)

        for row, feed in enumerate(feeds):
            for col, day in enumerate(day_list):
                n = counts.get((feed["id"], day), 0)
                item = QTableWidgetItem(str(n) if n else "")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if n:
                    # Heatmap: quanto mais artigos, mais forte (alpha ∝ n/max).
                    alpha = 70 + int(150 * (n / max_n)) if max_n else 0
                    item.setBackground(QColor(110, 190, 140, alpha))
                    item.setToolTip(f"{feed['title']} — {day}: {n} artigo(s)")
                else:
                    item.setToolTip(f"{feed['title']} — {day}: sem cobertura")
                self._table.setItem(row, col, item)

        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        log.debug("CoverageMap: grade %d feeds × %d dias (entidade %s).",
                  len(feeds), len(day_list), entity_id)
