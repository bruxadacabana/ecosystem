"""
investigation_view.py — pastas de investigação (Fase 7, item 3).

Coluna esquerda: lista de pastas + criar/excluir. Coluna direita (pasta selecionada):
nome, notas da pasta (editáveis), botão de exportar dossiê `.md`, e a linha do tempo
cronológica dos artigos dentro — com nota por artigo, remover, e duplo-clique para
abrir na aba de Leitura (`article_selected`).

Artigos entram nas pastas pelo botão "Adicionar à investigação" no leitor e pelo menu
de contexto do card (wireados no main_window) — não por arraste (não funciona entre
abas distintas).
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.investigations import (
    add_article,
    create_investigation,
    delete_investigation,
    export_dossier,
    get_articles,
    list_investigations,
    remove_article,
    set_article_note,
    set_description,
)

log = logging.getLogger("kosmos.investigation_view")


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except Exception:
        return iso[:10]


class InvestigationView(QWidget):
    """Pastas de investigação: lista à esquerda, detalhe + dossiê à direita."""

    article_selected = Signal(int)  # article_id — abrir na aba de Leitura

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_inv_id: int | None = None
        self._current_article_id: int | None = None
        self._setup_ui()
        log.debug("InvestigationView inicializada.")

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)

        # Esquerda: criar / lista / excluir
        left = QVBoxLayout()
        self._new_btn = QPushButton("Nova investigação")
        self._new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_btn.clicked.connect(self._on_new)
        left.addWidget(self._new_btn)
        self._inv_list = QListWidget()
        self._inv_list.setObjectName("investigation_list")
        self._inv_list.currentRowChanged.connect(self._on_inv_selected)
        left.addWidget(self._inv_list, 1)
        self._delete_btn = QPushButton("Excluir")
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.clicked.connect(self._on_delete)
        left.addWidget(self._delete_btn)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setMaximumWidth(260)
        layout.addWidget(left_w)

        # Direita: detalhe da pasta
        right = QVBoxLayout()
        self._header = QLabel("Selecione ou crie uma investigação")
        self._header.setObjectName("investigation_header")
        right.addWidget(self._header)

        right.addWidget(QLabel("Notas da pasta:"))
        self._desc_edit = QPlainTextEdit()
        self._desc_edit.setObjectName("investigation_desc")
        self._desc_edit.setMaximumHeight(70)
        right.addWidget(self._desc_edit)
        row = QHBoxLayout()
        self._desc_btn = QPushButton("Salvar notas")
        self._desc_btn.clicked.connect(self._on_save_desc)
        row.addWidget(self._desc_btn)
        self._export_btn = QPushButton("Exportar dossiê .md")
        self._export_btn.clicked.connect(self._on_export)
        row.addWidget(self._export_btn)
        row.addStretch(1)
        right.addLayout(row)

        right.addWidget(QLabel("Artigos (linha do tempo):"))
        self._articles = QListWidget()
        self._articles.setObjectName("investigation_articles")
        self._articles.currentRowChanged.connect(self._on_article_selected)
        self._articles.itemDoubleClicked.connect(self._on_article_double_clicked)
        right.addWidget(self._articles, 1)

        right.addWidget(QLabel("Nota do artigo:"))
        self._note_edit = QPlainTextEdit()
        self._note_edit.setObjectName("investigation_article_note")
        self._note_edit.setMaximumHeight(60)
        right.addWidget(self._note_edit)
        nrow = QHBoxLayout()
        self._note_btn = QPushButton("Salvar nota")
        self._note_btn.clicked.connect(self._on_save_note)
        nrow.addWidget(self._note_btn)
        self._remove_btn = QPushButton("Remover artigo")
        self._remove_btn.clicked.connect(self._on_remove_article)
        nrow.addWidget(self._remove_btn)
        nrow.addStretch(1)
        right.addLayout(nrow)

        layout.addLayout(right, 1)
        self._set_detail_visible(False)

    # ------------------------------------------------------------------
    # API pública / carregamento
    # ------------------------------------------------------------------

    def load_investigations(self, conn: sqlite3.Connection | None = None) -> int:
        """Carrega a lista de pastas. Retorna a contagem."""
        self._inv_list.blockSignals(True)
        self._inv_list.clear()
        rows = list_investigations(conn)
        for r in rows:
            item = QListWidgetItem(f"{r['name']}  ({r['article_count']})")
            item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self._inv_list.addItem(item)
        self._inv_list.blockSignals(False)
        if not rows:
            self._current_inv_id = None
            self._set_detail_visible(False)
            self._header.setText("Nenhuma investigação ainda — clique em 'Nova investigação'.")
        return len(rows)

    def show_investigation(self, inv_id: int, conn: sqlite3.Connection | None = None) -> None:
        """Mostra o detalhe de uma pasta: nome, notas, artigos."""
        self._current_inv_id = inv_id
        self._current_article_id = None
        self._set_detail_visible(True)
        self._note_edit.clear()

        invs = {r["id"]: r for r in list_investigations(conn)}
        inv = invs.get(inv_id)
        self._header.setText(inv["name"] if inv else "Investigação")
        self._desc_edit.setPlainText((inv or {}).get("description") or "")

        self._articles.clear()
        for a in get_articles(inv_id, conn):
            mark = " ✎" if (a.get("note") or "").strip() else ""
            item = QListWidgetItem(f"{_fmt_date(a['published_at'])}  ·  {a['feed']}  ·  {a['title']}{mark}")
            item.setData(Qt.ItemDataRole.UserRole, a["id"])
            item.setData(Qt.ItemDataRole.UserRole + 1, a.get("note") or "")
            self._articles.addItem(item)

    def select_investigation(self, inv_id: int) -> None:
        """Seleciona uma pasta pelo id na lista (após criar/adicionar)."""
        for i in range(self._inv_list.count()):
            if self._inv_list.item(i).data(Qt.ItemDataRole.UserRole) == inv_id:
                self._inv_list.setCurrentRow(i)
                return

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_inv_selected(self, row: int) -> None:
        if row < 0:
            return
        item = self._inv_list.item(row)
        if item is not None:
            inv_id = item.data(Qt.ItemDataRole.UserRole)
            if inv_id is not None:
                self.show_investigation(int(inv_id))

    def _on_new(self) -> None:
        name, ok = QInputDialog.getText(self, "Nova investigação", "Nome:")
        if not ok or not name.strip():
            return
        inv_id = create_investigation(name.strip())
        if inv_id is not None:
            self.load_investigations()
            self.select_investigation(inv_id)

    def _on_delete(self) -> None:
        if self._current_inv_id is None:
            return
        resp = QMessageBox.question(
            self, "Excluir investigação",
            "Excluir esta investigação? Os artigos não são apagados, só a pasta.",
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        delete_investigation(self._current_inv_id)
        self._current_inv_id = None
        self.load_investigations()

    def _on_save_desc(self) -> None:
        if self._current_inv_id is not None:
            set_description(self._current_inv_id, self._desc_edit.toPlainText())
            log.info("Notas da investigação %d salvas.", self._current_inv_id)

    def _on_article_selected(self, row: int) -> None:
        if row < 0:
            self._current_article_id = None
            return
        item = self._articles.item(row)
        if item is None:
            return
        self._current_article_id = item.data(Qt.ItemDataRole.UserRole)
        self._note_edit.setPlainText(item.data(Qt.ItemDataRole.UserRole + 1) or "")

    def _on_save_note(self) -> None:
        if self._current_inv_id is None or self._current_article_id is None:
            return
        set_article_note(self._current_inv_id, self._current_article_id, self._note_edit.toPlainText())
        self.show_investigation(self._current_inv_id)   # atualiza a marca ✎

    def _on_remove_article(self) -> None:
        if self._current_inv_id is None or self._current_article_id is None:
            return
        remove_article(self._current_inv_id, self._current_article_id)
        self._current_article_id = None
        self.show_investigation(self._current_inv_id)

    def _on_article_double_clicked(self, item: QListWidgetItem) -> None:
        article_id = item.data(Qt.ItemDataRole.UserRole)
        if article_id is not None:
            self.article_selected.emit(int(article_id))

    def _on_export(self) -> None:
        if self._current_inv_id is None:
            return
        md = export_dossier(self._current_inv_id)
        if not md:
            return
        suggested = (self._header.text() or "dossie").replace("/", "-") + ".md"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar dossiê", suggested, "Markdown (*.md)")
        if path:
            self.export_to(path, md)

    def export_to(self, path: str, md: str | None = None) -> bool:
        """Escreve o dossiê em `path` (separado de _on_export para ser testável)."""
        if md is None:
            if self._current_inv_id is None:
                return False
            md = export_dossier(self._current_inv_id)
        if not md:
            return False
        try:
            Path(path).write_text(md, encoding="utf-8")
            log.info("Dossiê exportado para %s.", path)
            return True
        except OSError as exc:
            log.error("Falha ao exportar dossiê para %s: %s", path, exc)
            return False

    def _set_detail_visible(self, visible: bool) -> None:
        for w in (self._desc_edit, self._desc_btn, self._export_btn, self._articles,
                  self._note_edit, self._note_btn, self._remove_btn):
            w.setVisible(visible)
