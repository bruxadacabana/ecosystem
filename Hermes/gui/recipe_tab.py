"""
Aba "Receitas" do HERMES — extração estruturada de receitas de vídeo.

Layout:
  URL input + botão "Extrair"
  label de status (plataforma + título identificado)
  QProgressBar (indeterminado p/ vídeo único, determinado p/ playlist)
  QListWidget com resultados da playlist (✓ / ✗) — só para playlists
  QTextEdit: preview do Markdown gerado
  botões: "Salvar" e "Limpar"
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.recipe_extractor import RecipeResult, to_markdown


class RecipeTab(QWidget):
    """Aba de extração de receitas do HERMES."""

    log_message = pyqtSignal(str, str)   # (mensagem, tag) — repassa para o log global

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recipes_dir: str = ""
        self._last_result: RecipeResult | None = None
        self._last_md: str = ""
        self._worker = None
        self._build_ui()

    # ── Propriedades ──────────────────────────────────────────────────────────
    @property
    def recipes_dir(self) -> str:
        return self._recipes_dir

    @recipes_dir.setter
    def recipes_dir(self, value: str) -> None:
        self._recipes_dir = value

    # ── Construção da UI ──────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # URL input
        layout.addWidget(self._section_label("URL DO VÍDEO OU PLAYLIST"))
        url_row = QHBoxLayout()
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("Cole a URL do vídeo ou playlist de receitas…")
        self._url_edit.returnPressed.connect(self._on_extract)
        url_row.addWidget(self._url_edit)
        self._extract_btn = QPushButton("✦ EXTRAIR")
        self._extract_btn.setObjectName("primary")
        self._extract_btn.clicked.connect(self._on_extract)
        url_row.addWidget(self._extract_btn)
        self._cancel_btn = QPushButton("CANCELAR")
        self._cancel_btn.setObjectName("danger")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._on_cancel)
        url_row.addWidget(self._cancel_btn)
        layout.addLayout(url_row)

        # Status (plataforma + título identificado)
        self._status_lbl = QLabel()
        self._status_lbl.setObjectName("meta")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.hide()
        layout.addWidget(self._status_lbl)

        # Barra de progresso
        self._progress = QProgressBar()
        self._progress.setValue(0)
        self._progress.hide()
        layout.addWidget(self._progress)

        # Lista de resultados de playlist
        self._playlist_lbl = self._section_label("RESULTADOS DA PLAYLIST")
        self._playlist_lbl.hide()
        layout.addWidget(self._playlist_lbl)
        self._playlist_list = QListWidget()
        self._playlist_list.setMaximumHeight(130)
        self._playlist_list.hide()
        self._playlist_list.itemClicked.connect(self._on_playlist_item_select)
        layout.addWidget(self._playlist_list)

        # Preview do Markdown
        layout.addWidget(self._section_label("PRÉVIA DA RECEITA"))
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText("O Markdown da receita aparecerá aqui após a extração…")
        self._preview.setMinimumHeight(60)
        self._preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._preview)

        # Botões de ação final
        action_row = QHBoxLayout()
        self._save_btn = QPushButton("SALVAR")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save)
        action_row.addWidget(self._save_btn)
        self._clear_btn = QPushButton("LIMPAR")
        self._clear_btn.clicked.connect(self._on_clear)
        action_row.addWidget(self._clear_btn)
        action_row.addStretch()
        self._result_lbl = QLabel()
        self._result_lbl.setObjectName("meta")
        action_row.addWidget(self._result_lbl)
        layout.addLayout(action_row)

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section")
        return lbl

    # ── Lógica ────────────────────────────────────────────────────────────────
    def set_config(self, *, recipes_dir: str = "", model_size: str = "small",
                   language: str = "auto", ollama_model: str = "qwen2.5:7b") -> None:
        """Configura parâmetros de extração vindos das prefs do HERMES."""
        self._recipes_dir = recipes_dir
        self._model_size = model_size
        self._language = language
        self._ollama_model = ollama_model

    def paste_url(self, url: str) -> None:
        """Preenche a URL externamente (chamado pela URL compartilhada do HERMES)."""
        self._url_edit.setText(url)

    def _on_extract(self) -> None:
        url = self._url_edit.text().strip()
        if not url:
            return
        self._set_busy(True)
        self._playlist_list.clear()
        self._playlist_list.hide()
        self._playlist_lbl.hide()
        self._preview.clear()
        self._save_btn.setEnabled(False)
        self._result_lbl.clear()
        self._status_lbl.hide()
        self._last_result = None
        self._last_md = ""

        # Lazy import para não carregar PyQt worker antes de precisar
        from .workers import RecipeExtractWorker  # noqa: PLC0415

        self._worker = RecipeExtractWorker(
            url=url,
            model_size=getattr(self, "_model_size", "small"),
            language=getattr(self, "_language", "auto"),
            ollama_model=getattr(self, "_ollama_model", "qwen2.5:7b"),
            recipes_dir=self._recipes_dir,
        )
        self._worker.identified.connect(self._on_identified)
        self._worker.progress.connect(self._on_progress)
        self._worker.recipe_ready.connect(self._on_recipe_ready)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self._set_busy(False)
        self._status_lbl.setText("Cancelado.")
        self._status_lbl.show()

    def _on_identified(self, platform: str, title: str, is_playlist: bool, count: int) -> None:
        if is_playlist:
            self._status_lbl.setText(f"Playlist · {platform} · {count} vídeo(s): {title}")
            self._progress.setMaximum(count)
            self._progress.setValue(0)
            self._playlist_list.show()
            self._playlist_lbl.show()
        else:
            self._status_lbl.setText(f"{platform.capitalize()} · Identificado: {title}")
            self._progress.setMaximum(0)  # indeterminado
        self._status_lbl.show()
        self._progress.show()

    def _on_progress(self, current: int, total: int, title: str) -> None:
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(current)
        self._status_lbl.setText(f"[{current}/{total}] Processando: {title}")

    def _on_recipe_ready(self, result: RecipeResult) -> None:
        md = to_markdown(result)
        self._last_result = result
        self._last_md = md

        if self._playlist_list.isVisible():
            icon = "✓" if result.ok else "✗"
            item = QListWidgetItem(f"{icon}  {result.title or result.source_url}")
            item.setData(Qt.ItemDataRole.UserRole, md)
            self._playlist_list.addItem(item)
        else:
            # vídeo único — exibe diretamente no preview
            self._preview.setPlainText(md)

    def _on_playlist_item_select(self, item: QListWidgetItem) -> None:
        md = item.data(Qt.ItemDataRole.UserRole) or ""
        self._preview.setPlainText(md)

    def _on_finished(self) -> None:
        self._set_busy(False)
        self._progress.hide()
        if self._last_result and self._last_result.ok:
            self._save_btn.setEnabled(True)
            self._result_lbl.setText("Extração concluída.")
        elif self._last_result:
            self._result_lbl.setText(f"Concluído com erro: {self._last_result.error}")
        self.log_message.emit("Extração de receita concluída.", "ok")

    def _on_error(self, msg: str) -> None:
        self._set_busy(False)
        self._progress.hide()
        self._status_lbl.setText(f"Erro: {msg}")
        self._status_lbl.show()
        self._result_lbl.setText("Falha na extração.")
        self.log_message.emit(f"Erro na extração de receita: {msg}", "err")

    def _on_save(self) -> None:
        md = self._preview.toPlainText()
        if not md:
            return
        # Pergunta o destino se recipes_dir não estiver configurado
        save_dir = self._recipes_dir
        if not save_dir:
            save_dir = QFileDialog.getExistingDirectory(self, "Pasta para salvar receitas")
            if not save_dir:
                return
        if self._last_result:
            from services.recipe_extractor import to_markdown as _save_md  # noqa: PLC0415
            _save_md(self._last_result, recipes_dir=save_dir)
            self._result_lbl.setText(f"Salvo em: {save_dir}")
            self.log_message.emit(f"Receita salva em {save_dir}", "ok")
        else:
            # fallback: salva o texto que está no preview
            import re as _re
            title = self._last_result.recipe_name if self._last_result else "receita"
            slug = _re.sub(r"[\s_-]+", "-", _re.sub(r"[^\w\s-]", "", title.lower()))[:60]
            from datetime import datetime
            fname = f"{slug}-{datetime.now().strftime('%Y%m%d')}.md"
            (Path(save_dir) / fname).write_text(md, encoding="utf-8")
            self._result_lbl.setText(f"Salvo em: {save_dir}/{fname}")

    def _on_clear(self) -> None:
        self._url_edit.clear()
        self._preview.clear()
        self._status_lbl.hide()
        self._progress.hide()
        self._progress.setValue(0)
        self._playlist_list.clear()
        self._playlist_list.hide()
        self._playlist_lbl.hide()
        self._save_btn.setEnabled(False)
        self._result_lbl.clear()
        self._last_result = None
        self._last_md = ""

    def _set_busy(self, busy: bool) -> None:
        self._extract_btn.setEnabled(not busy)
        self._cancel_btn.setEnabled(busy)
        self._url_edit.setReadOnly(busy)
