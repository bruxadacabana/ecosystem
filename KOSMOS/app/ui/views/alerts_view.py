"""
alerts_view.py — Gestão de alertas (Fase 7, item 6).

Ferramenta da aba Análise para configurar o que destaca cards na lista:
  - **Palavras-chave:** campo + "Adicionar"; lista com remoção.
  - **Entidades rastreadas:** lista com caixa de seleção — marcar = vigiar a entidade.

O destaque em si aparece nos cards na próxima vez que a lista é recarregada (sem
push), conforme o comportamento combinado. Esta view só edita as regras.
"""
from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.alerts import add_alert, is_entity_alerted, list_alerts, remove_alert
from app.core.entities import list_entities

log = logging.getLogger("kosmos.alerts_view")

_TYPE_LABELS = {"person": "Pessoa", "org": "Organização", "place": "Lugar", "topic": "Tema"}


class AlertsView(QWidget):
    """Gerencia alertas de palavras-chave e entidades rastreadas."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        log.debug("AlertsView inicializada.")

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Palavras-chave vigiadas:"))
        kw_row = QHBoxLayout()
        self._kw_edit = QLineEdit()
        self._kw_edit.setObjectName("alert_kw_edit")
        self._kw_edit.setPlaceholderText("ex.: reforma tributária")
        self._kw_edit.returnPressed.connect(self._on_add_keyword)
        kw_row.addWidget(self._kw_edit, 1)
        self._kw_add_btn = QPushButton("Adicionar")
        self._kw_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._kw_add_btn.clicked.connect(self._on_add_keyword)
        kw_row.addWidget(self._kw_add_btn)
        layout.addLayout(kw_row)

        self._kw_list = QListWidget()
        self._kw_list.setObjectName("alert_kw_list")
        self._kw_list.setMaximumHeight(140)
        layout.addWidget(self._kw_list)
        self._kw_remove_btn = QPushButton("Remover palavra-chave selecionada")
        self._kw_remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._kw_remove_btn.clicked.connect(self._on_remove_keyword)
        layout.addWidget(self._kw_remove_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addSpacing(8)
        layout.addWidget(QLabel("Entidades rastreadas (marque para vigiar):"))
        self._entity_list = QListWidget()
        self._entity_list.setObjectName("alert_entity_list")
        self._entity_list.itemChanged.connect(self._on_entity_toggled)
        layout.addWidget(self._entity_list, 1)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def reload(self, conn: sqlite3.Connection | None = None) -> None:
        """Recarrega palavras-chave e entidades (com o estado de vigilância)."""
        # Palavras-chave
        self._kw_list.clear()
        for a in list_alerts(conn):
            if a["kind"] == "keyword":
                item = QListWidgetItem(a["term"])
                item.setData(Qt.ItemDataRole.UserRole, a["term"])
                self._kw_list.addItem(item)

        # Entidades (caixa de seleção = vigiar)
        self._entity_list.blockSignals(True)
        self._entity_list.clear()
        for r in list_entities(conn):
            tipo = _TYPE_LABELS.get(r["entity_type"], r["entity_type"])
            item = QListWidgetItem(f"{r['name']}  ·  {tipo}")
            item.setData(Qt.ItemDataRole.UserRole, r["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = is_entity_alerted(r["id"], conn)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self._entity_list.addItem(item)
        self._entity_list.blockSignals(False)
        log.debug("AlertsView: %d keyword(s), %d entidade(s).",
                  self._kw_list.count(), self._entity_list.count())

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _on_add_keyword(self) -> None:
        term = self._kw_edit.text().strip()
        if not term:
            return
        if add_alert("keyword", term):
            log.info("AlertsView: alerta de palavra-chave adicionado: %r", term)
        self._kw_edit.clear()
        self.reload()

    def _on_remove_keyword(self) -> None:
        item = self._kw_list.currentItem()
        if item is None:
            return
        term = item.data(Qt.ItemDataRole.UserRole)
        remove_alert("keyword", term)
        log.info("AlertsView: alerta de palavra-chave removido: %r", term)
        self.reload()

    def _on_entity_toggled(self, item: QListWidgetItem) -> None:
        entity_id = item.data(Qt.ItemDataRole.UserRole)
        if entity_id is None:
            return
        if item.checkState() == Qt.CheckState.Checked:
            add_alert("entity", str(entity_id))
            log.info("AlertsView: entidade %s passou a ser vigiada.", entity_id)
        else:
            remove_alert("entity", str(entity_id))
            log.info("AlertsView: entidade %s deixou de ser vigiada.", entity_id)
