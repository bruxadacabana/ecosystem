"""
entity_view.py — Rastreador de entidades (Fase 7, item 2).

Lista as entidades materializadas (pessoas/organizações/lugares/temas) por volume de
cobertura. Ao selecionar uma, mostra: a linha do tempo automática de artigos que a
mencionam (mais novo → mais antigo), o sentimento acumulado, quais feeds cobriram
mais, e um campo de notas próprio da usuária. Clicar num artigo da linha do tempo
emite `article_selected(int)` para abri-lo na aba de Leitura.

O botão "Atualizar" roda o backfill (materializa entidades de artigos já analisados)
e recarrega a lista.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.entities import (
    backfill_entity_links,
    get_entity_feed_breakdown,
    get_entity_sentiment_breakdown,
    get_entity_timeline,
    list_entities,
    set_entity_notes,
)

log = logging.getLogger("kosmos.entity_view")

_TYPE_LABELS = {"person": "Pessoa", "org": "Organização", "place": "Lugar", "topic": "Tema"}


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except Exception:
        return iso[:10]


class EntityView(QWidget):
    """Rastreador de entidades: lista à esquerda, detalhe (timeline/sentimento/feeds/notas)."""

    article_selected = Signal(int)  # article_id — abrir na aba de Leitura

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_entity_id: int | None = None
        self._setup_ui()
        log.debug("EntityView inicializada.")

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)

        # Coluna esquerda: botão atualizar + lista de entidades
        left = QVBoxLayout()
        self._refresh_btn = QPushButton("Atualizar")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(lambda: self.refresh())
        left.addWidget(self._refresh_btn)

        self._entity_list = QListWidget()
        self._entity_list.setObjectName("entity_list")
        self._entity_list.currentRowChanged.connect(self._on_entity_selected)
        left.addWidget(self._entity_list, 1)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setMaximumWidth(260)
        layout.addWidget(left_w)

        # Coluna direita: detalhe da entidade
        right = QVBoxLayout()
        self._header = QLabel("Selecione uma entidade")
        self._header.setObjectName("entity_header")
        right.addWidget(self._header)

        self._sentiment_lbl = QLabel()
        self._sentiment_lbl.setObjectName("entity_sentiment")
        self._sentiment_lbl.setWordWrap(True)
        right.addWidget(self._sentiment_lbl)

        self._feeds_lbl = QLabel()
        self._feeds_lbl.setObjectName("entity_feeds")
        self._feeds_lbl.setWordWrap(True)
        right.addWidget(self._feeds_lbl)

        right.addWidget(QLabel("Notas:"))
        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setObjectName("entity_notes")
        self._notes_edit.setMaximumHeight(80)
        right.addWidget(self._notes_edit)
        self._notes_btn = QPushButton("Salvar nota")
        self._notes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._notes_btn.clicked.connect(self._on_save_notes)
        right.addWidget(self._notes_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        right.addWidget(QLabel("Linha do tempo:"))
        self._timeline = QListWidget()
        self._timeline.setObjectName("entity_timeline")
        self._timeline.itemClicked.connect(self._on_timeline_clicked)
        right.addWidget(self._timeline, 1)

        layout.addLayout(right, 1)
        self._set_detail_visible(False)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def load_entities(self, conn: sqlite3.Connection | None = None) -> int:
        """Carrega a lista de entidades (mais cobertas primeiro). Retorna a contagem."""
        self._entity_list.blockSignals(True)
        self._entity_list.clear()
        rows = list_entities(conn)
        for r in rows:
            tipo = _TYPE_LABELS.get(r["entity_type"], r["entity_type"])
            item = QListWidgetItem(f"{r['name']}  ·  {tipo}  ({r['article_count']})")
            item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self._entity_list.addItem(item)
        self._entity_list.blockSignals(False)
        if not rows:
            self._current_entity_id = None
            self._set_detail_visible(False)
            self._header.setText("Nenhuma entidade ainda — abra artigos para analisá-los, ou clique em Atualizar.")
            self._header.show()
        log.debug("EntityView: %d entidade(s) carregada(s).", len(rows))
        return len(rows)

    def refresh(self, conn: sqlite3.Connection | None = None) -> None:
        """Roda o backfill (materializa os já analisados) e recarrega a lista."""
        n = backfill_entity_links(conn)
        log.info("EntityView: backfill processou %d artigo(s).", n)
        self.load_entities(conn)

    def show_entity(self, entity_id: int, conn: sqlite3.Connection | None = None) -> None:
        """Carrega o detalhe de uma entidade (timeline, sentimento, feeds, notas)."""
        self._current_entity_id = entity_id
        self._set_detail_visible(True)

        # Cabeçalho a partir do item selecionado (ou genérico)
        name = self._entity_name(entity_id)
        self._header.setText(name)

        sent = get_entity_sentiment_breakdown(entity_id, conn)
        self._sentiment_lbl.setText(
            "Sentimento acumulado — "
            f"positivo: {sent.get('positivo', 0)}, "
            f"neutro: {sent.get('neutro', 0)}, "
            f"negativo: {sent.get('negativo', 0)}"
        )

        feeds = get_entity_feed_breakdown(entity_id, conn)
        if feeds:
            self._feeds_lbl.setText("Feeds: " + ", ".join(f"{f['feed']} ({f['n']})" for f in feeds[:6]))
        else:
            self._feeds_lbl.setText("Feeds: —")

        self._notes_edit.setPlainText(self._entity_notes(entity_id, conn))

        self._timeline.clear()
        for a in get_entity_timeline(entity_id, conn):
            sent_tag = f"[{a['ai_sentiment']}] " if a.get("ai_sentiment") else ""
            item = QListWidgetItem(f"{_fmt_date(a['published_at'])}  ·  {a['feed']}  ·  {sent_tag}{a['title']}")
            item.setData(Qt.ItemDataRole.UserRole, a["id"])
            self._timeline.addItem(item)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _entity_name(self, entity_id: int) -> str:
        for i in range(self._entity_list.count()):
            it = self._entity_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == entity_id:
                return it.text()
        return "Entidade"

    def _entity_notes(self, entity_id: int, conn: sqlite3.Connection | None = None) -> str:
        for r in list_entities(conn):
            if r["id"] == entity_id:
                return r["notes"] or ""
        return ""

    def _on_entity_selected(self, row: int) -> None:
        if row < 0:
            return
        item = self._entity_list.item(row)
        if item is None:
            return
        entity_id = item.data(Qt.ItemDataRole.UserRole)
        if entity_id is not None:
            self.show_entity(int(entity_id))

    def _on_save_notes(self) -> None:
        if self._current_entity_id is None:
            return
        set_entity_notes(self._current_entity_id, self._notes_edit.toPlainText())
        log.info("EntityView: nota salva para a entidade %d.", self._current_entity_id)

    def _on_timeline_clicked(self, item: QListWidgetItem) -> None:
        article_id = item.data(Qt.ItemDataRole.UserRole)
        if article_id is not None:
            self.article_selected.emit(int(article_id))

    def _set_detail_visible(self, visible: bool) -> None:
        for w in (self._sentiment_lbl, self._feeds_lbl, self._notes_edit,
                  self._notes_btn, self._timeline):
            w.setVisible(visible)
