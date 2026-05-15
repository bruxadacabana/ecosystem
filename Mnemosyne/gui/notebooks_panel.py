"""
Mnemosyne — NotebooksPanel: painel de notebooks na sidebar.

Exibe a lista de notebooks persistentes como itens clicáveis. Permite criar
novos notebooks (botão "+") e excluir existentes (ícone de lixeira por item,
com confirmação). O notebook ativo fica destacado com a cor de seleção do
tema.

Sinais emitidos:
    notebook_selected(str)  — id do notebook clicado
    notebook_created(str)   — id do notebook recém-criado
    notebook_deleted(str)   — id do notebook excluído

MainWindow conecta esses sinais para carregar o histórico e os tiles do Studio
do notebook selecionado.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from core.notebook import Notebook
from core.notebook_store import NotebookStore


def _fmt_date(iso: str) -> str:
    """Formata timestamp ISO como 'DD/MM/YY HH:MM', ou string vazia se inválido."""
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%d/%m/%y %H:%M")
    except ValueError:
        return iso[:10] if len(iso) >= 10 else iso


class _NotebookItem(QWidget):
    """Item customizado da lista: nome + data + botão lixeira."""

    delete_requested = Signal(str)  # emite notebook_id

    def __init__(self, notebook: Notebook, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.notebook_id = notebook.id

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        text_col.setContentsMargins(0, 0, 0, 0)

        self.name_lbl = QLabel(notebook.name)
        self.name_lbl.setObjectName("notebookItemName")

        self.date_lbl = QLabel(_fmt_date(notebook.updated_at))
        self.date_lbl.setObjectName("notebookItemDate")

        text_col.addWidget(self.name_lbl)
        text_col.addWidget(self.date_lbl)

        self._del_btn = QPushButton("🗑")
        self._del_btn.setObjectName("notebookDeleteBtn")
        self._del_btn.setFixedSize(20, 20)
        self._del_btn.setToolTip("Excluir notebook")
        self._del_btn.clicked.connect(lambda: self.delete_requested.emit(self.notebook_id))

        layout.addLayout(text_col, 1)
        layout.addWidget(self._del_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_active(self, active: bool) -> None:
        """Atualiza o estilo do nome conforme notebook ativo."""
        self.name_lbl.setProperty("active", "true" if active else "false")
        self.name_lbl.style().unpolish(self.name_lbl)
        self.name_lbl.style().polish(self.name_lbl)


class NotebooksPanel(QWidget):
    """Painel de notebooks exibido na sidebar esquerda do Mnemosyne.

    Mostra a lista de notebooks como itens clicáveis (nome + data da última
    mensagem). Botão "+" cria novo notebook pedindo um nome. Ícone de lixeira
    exclui com confirmação. O notebook ativo fica destacado.
    """

    notebook_selected = Signal(str)   # notebook_id
    notebook_created  = Signal(str)   # notebook_id
    notebook_deleted  = Signal(str)   # notebook_id

    def __init__(self, store: NotebookStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._active_id: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Header: label "NOTEBOOKS" + botão "+"
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)

        lbl = QLabel("NOTEBOOKS")
        lbl.setObjectName("sidebarLabel")
        header.addWidget(lbl)
        header.addStretch()

        self._add_btn = QPushButton("+")
        self._add_btn.setFixedSize(22, 18)
        self._add_btn.setToolTip("Novo notebook")
        self._add_btn.clicked.connect(self._on_add)
        header.addWidget(self._add_btn)

        layout.addLayout(header)

        # Lista de notebooks
        self._list = QListWidget()
        self._list.setObjectName("notebooksList")
        self._list.setMaximumHeight(140)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

        self.refresh()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Recarrega a lista a partir do NotebookStore."""
        self._list.clear()
        for nb in self._store.list_all():
            self._add_list_item(nb)

    def set_active(self, notebook_id: str | None) -> None:
        """Marca o notebook ativo (destaca na lista)."""
        self._active_id = notebook_id
        for i in range(self._list.count()):
            item = self._list.item(i)
            widget = self._list.itemWidget(item)
            if isinstance(widget, _NotebookItem):
                widget.set_active(widget.notebook_id == notebook_id)
        self._sync_selection()

    def active_id(self) -> str | None:
        return self._active_id

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    def _add_list_item(self, notebook: Notebook) -> None:
        item = QListWidgetItem(self._list)
        widget = _NotebookItem(notebook, self._list)
        widget.delete_requested.connect(self._on_delete)
        widget.set_active(notebook.id == self._active_id)
        item.setSizeHint(widget.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, notebook.id)
        self._list.setItemWidget(item, widget)

    def _sync_selection(self) -> None:
        """Sincroniza a seleção visual da QListWidget com o notebook ativo."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == self._active_id:
                self._list.setCurrentItem(item)
                return
        self._list.clearSelection()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        notebook_id = item.data(Qt.ItemDataRole.UserRole)
        if notebook_id:
            self.set_active(notebook_id)
            self.notebook_selected.emit(notebook_id)

    def _on_add(self) -> None:
        today = datetime.now().strftime("%d/%m/%Y")
        default_name = f"Notebook {today}"
        name, ok = QInputDialog.getText(
            self,
            "Novo notebook",
            "Nome do notebook:",
            text=default_name,
        )
        if not ok or not name.strip():
            return
        try:
            nb = self._store.create(name.strip())
        except Exception as exc:
            QMessageBox.warning(self, "Erro", f"Não foi possível criar o notebook:\n{exc}")
            return
        self._add_list_item(nb)
        self.set_active(nb.id)
        self.notebook_created.emit(nb.id)

    def _on_delete(self, notebook_id: str) -> None:
        try:
            nb = self._store.load(notebook_id)
            name = nb.name
        except Exception:
            name = notebook_id

        reply = QMessageBox.question(
            self,
            "Excluir notebook",
            f'Excluir "{name}" e todo seu histórico?\n\nEsta ação não pode ser desfeita.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._store.delete(notebook_id)
        except Exception as exc:
            QMessageBox.warning(self, "Erro", f"Não foi possível excluir:\n{exc}")
            return

        # Remove da lista
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == notebook_id:
                self._list.takeItem(i)
                break

        if self._active_id == notebook_id:
            self._active_id = None

        self.notebook_deleted.emit(notebook_id)
