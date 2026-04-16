# Janela principal do Mnemosyne
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.config import AppConfig, load_config, save_config
from core.errors import ConfigError, VectorstoreNotFoundError
from core.indexer import load_vectorstore
from core.memory import CollectionIndex, CollectionInfo, MemoryStore, SessionMemory, Turn
from core.ollama_client import OllamaModel, filter_chat_models, filter_embed_models
from core.tracker import FileTracker
from gui.workers import (
    AskWorker,
    CompactMemoryWorker,
    FaqWorker,
    GuideWorker,
    IndexFileWorker,
    IndexWorker,
    OllamaCheckWorker,
    SummarizeWorker,
    UpdateIndexWorker,
)


class SetupDialog(QDialog):
    """Diálogo de configuração — seleção de pasta, modelo LLM e embedding."""

    def __init__(
        self,
        models: list[OllamaModel],
        current: AppConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuração do Mnemosyne")
        self.setMinimumWidth(540)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Configure o Mnemosyne.\n"
                "As configurações são salvas em config.json."
            )
        )

        form = QFormLayout()

        # Pasta monitorada (Biblioteca)
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit(current.watched_dir)
        self.folder_edit.setPlaceholderText("Selecione a pasta com seus documentos…")
        folder_btn = QPushButton("Escolher…")
        folder_btn.clicked.connect(self._pick_folder)
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(folder_btn)
        form.addRow("Biblioteca (pasta):", folder_row)

        # Vault Obsidian (opcional)
        vault_row = QHBoxLayout()
        self.vault_edit = QLineEdit(current.vault_dir)
        self.vault_edit.setPlaceholderText("Opcional — pasta do vault Obsidian…")
        vault_btn = QPushButton("Escolher…")
        vault_btn.clicked.connect(self._pick_vault)
        vault_row.addWidget(self.vault_edit)
        vault_row.addWidget(vault_btn)
        form.addRow("Vault Obsidian:", vault_row)

        chat_models = filter_chat_models(models)
        embed_models = filter_embed_models(models)

        # Modelo LLM
        self.llm_combo = QComboBox()
        for m in chat_models:
            self.llm_combo.addItem(m.name)
        if not chat_models:
            self.llm_combo.addItem("(nenhum modelo de chat encontrado)")
        if current.llm_model:
            idx = self.llm_combo.findText(current.llm_model)
            if idx >= 0:
                self.llm_combo.setCurrentIndex(idx)
        form.addRow("Modelo LLM:", self.llm_combo)

        # Modelo embedding
        self.embed_combo = QComboBox()
        for m in embed_models:
            self.embed_combo.addItem(m.name)
        if not embed_models:
            self.embed_combo.addItem("(nenhum modelo de embedding encontrado)")
        if current.embed_model:
            idx = self.embed_combo.findText(current.embed_model)
            if idx >= 0:
                self.embed_combo.setCurrentIndex(idx)
        form.addRow("Modelo de embedding:", self.embed_combo)

        layout.addLayout(form)

        # Botão de sugestões do ecossistema (só aparece se houver caminhos)
        self._ecosystem_suggestions = self._load_ecosystem_suggestions()
        if self._ecosystem_suggestions:
            suggest_btn = QPushButton("Sugestões do ecossistema")
            suggest_btn.setToolTip(
                "Caminhos detectados nos outros apps do ecossistema"
            )
            suggest_btn.clicked.connect(
                lambda: self._show_ecosystem_menu(suggest_btn)
            )
            layout.addWidget(suggest_btn)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load_ecosystem_suggestions(self) -> list[tuple[str, str, str]]:
        """
        Lê o ecosystem.json e retorna lista de (label, path, field).
        `field` é "folder" ou "vault".
        Retorna lista vazia se ecosystem_client não estiver disponível
        ou não houver caminhos configurados.
        """
        try:
            from pathlib import Path as _Path
            import sys as _sys
            _root = str(_Path(__file__).parent.parent.parent)
            if _root not in _sys.path:
                _sys.path.insert(0, _root)
            from ecosystem_client import read_ecosystem
            eco = read_ecosystem()
        except Exception:
            return []

        suggestions: list[tuple[str, str, str]] = []

        archive = eco.get("kosmos", {}).get("archive_path", "")
        if archive and os.path.isdir(archive):
            suggestions.append(("KOSMOS — archive", archive, "folder"))

        vault = eco.get("aether", {}).get("vault_path", "")
        if vault and os.path.isdir(vault):
            suggestions.append(("AETHER — vault", vault, "vault"))

        akasha_archive = eco.get("akasha", {}).get("archive_path", "")
        if akasha_archive and os.path.isdir(akasha_archive):
            suggestions.append(("AKASHA — archive", akasha_archive, "folder"))

        return suggestions

    def _show_ecosystem_menu(self, btn: QPushButton) -> None:
        """Exibe QMenu com caminhos do ecossistema; clique preenche o campo."""
        menu = QMenu(self)
        for label, path, field in self._ecosystem_suggestions:
            action = menu.addAction(f"{label}  →  {path}")
            action.setData((path, field))
        chosen = menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
        if chosen is not None:
            path, field = chosen.data()
            if field == "folder":
                self.folder_edit.setText(path)
            else:
                self.vault_edit.setText(path)

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Selecionar pasta de documentos"
        )
        if folder:
            self.folder_edit.setText(folder)

    def _pick_vault(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Selecionar vault do Obsidian"
        )
        if folder:
            self.vault_edit.setText(folder)

    def get_values(self) -> tuple[str, str, str, str]:
        """Retorna (watched_dir, llm_model, embed_model, vault_dir)."""
        return (
            self.folder_edit.text().strip(),
            self.llm_combo.currentText(),
            self.embed_combo.currentText(),
            self.vault_edit.text().strip(),
        )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mnemosyne — Seu Bibliotecário Celeste")
        self.setMinimumSize(900, 650)

        self.vectorstore = None
        self._available_models: list[OllamaModel] = []
        self._session_memory = SessionMemory()
        self._chat_history: list[Turn] = []
        self._collection_index: CollectionIndex | None = None
        self._file_tracker: FileTracker | None = None
        self._memory_store: MemoryStore | None = None
        self._ollama_ok = False
        self._raw_answer = ""
        self._raw_summary = ""
        self._raw_faq = ""

        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(30_000)  # 30 segundos
        self._retry_timer.timeout.connect(self._retry_ollama_check)

        try:
            self.config = load_config()
        except ConfigError as exc:
            QMessageBox.critical(None, "Erro de configuração", str(exc))
            self.config = AppConfig(
                llm_model="",
                embed_model="",
                chunk_size=800,
                chunk_overlap=100,
                retriever_k=4,
                watched_dir="",
                vault_dir="",
                auto_index_on_change=True,
            )

        self._register_ecosystem()
        self._build_ui()
        self.apply_style()
        self._start_ollama_check()

    # ── Construção da UI ──────────────────────────────────────────────────────

    def _register_ecosystem(self) -> None:
        try:
            _root = str(Path(__file__).parent.parent.parent)
            if _root not in sys.path:
                sys.path.insert(0, _root)
            from ecosystem_client import write_section
            import platform as _platform
            script = "iniciar.bat" if _platform.system() == "Windows" else "iniciar.sh"
            data: dict = {
                "exe_path": str(Path(__file__).parent.parent / script),
            }
            if self.config.watched_dir:
                data["watched_dir"] = self.config.watched_dir
            if self.config.vault_dir:
                data["vault_dir"] = self.config.vault_dir
            if self.config.persist_dir:
                data["index_paths"] = [self.config.persist_dir]
            write_section("mnemosyne", data)
        except Exception:
            pass

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(6)

        # Banner Ollama indisponível
        self.ollama_banner = QLabel(
            "⚠  Ollama não encontrado. Inicie o Ollama para usar o Mnemosyne."
        )
        self.ollama_banner.setObjectName("ollamaBanner")
        self.ollama_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ollama_banner.setVisible(False)
        root.addWidget(self.ollama_banner)

        # Barra superior
        top = QHBoxLayout()
        self.folder_label = QLabel(self.config.watched_dir or "Pasta não configurada")
        self.folder_label.setObjectName("folderLabel")

        self.config_btn = QPushButton("Configurar")
        self.config_btn.setEnabled(False)
        self.config_btn.clicked.connect(self.open_config)

        self.index_btn = QPushButton("Indexar tudo")
        self.index_btn.setEnabled(False)
        self.index_btn.clicked.connect(self.start_indexing)

        self.cancel_btn = QPushButton("Interromper")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_worker)

        self.badge_label = QLabel()
        self.badge_label.setVisible(False)

        self.progress = QProgressBar()
        self.progress.setVisible(False)

        top.addWidget(QLabel("Pasta:"))
        top.addWidget(self.folder_label, 1)
        top.addWidget(self.badge_label)
        top.addWidget(self.config_btn)
        top.addWidget(self.index_btn)
        top.addWidget(self.cancel_btn)
        top.addWidget(self.progress)
        root.addLayout(top)

        # Abas
        self.tabs = QTabWidget()
        self._build_tab_ask()
        self._build_tab_summary()
        self._build_tab_manage()
        root.addWidget(self.tabs)

    def _build_tab_ask(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        q_row = QHBoxLayout()
        self.question_edit = QLineEdit()
        self.question_edit.setPlaceholderText("Pergunte à sua memória…")
        self.question_edit.returnPressed.connect(self.ask_question)
        self.ask_btn = QPushButton("Perguntar")
        self.ask_btn.setEnabled(False)
        self.ask_btn.clicked.connect(self.ask_question)
        self.new_chat_btn = QPushButton("Nova Conversa")
        self.new_chat_btn.setToolTip("Reseta o histórico da conversa actual")
        self.new_chat_btn.clicked.connect(self._reset_conversation)
        q_row.addWidget(self.question_edit)
        q_row.addWidget(self.ask_btn)
        q_row.addWidget(self.new_chat_btn)
        layout.addLayout(q_row)

        # Seletores de fonte e modo de recuperação
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Buscar em:"))
        self.source_combo = QComboBox()
        self.source_combo.addItems(["Biblioteca", "Vault", "Ambos"])
        self.source_combo.setCurrentIndex(2)  # Ambos por defeito
        source_row.addWidget(self.source_combo)
        source_row.addSpacing(16)
        source_row.addWidget(QLabel("Modo:"))
        self.retrieval_combo = QComboBox()
        self.retrieval_combo.addItems(["Híbrido", "Multi-Query", "HyDE"])
        self.retrieval_combo.setCurrentIndex(0)
        self.retrieval_combo.setToolTip(
            "Híbrido: semântico + BM25 (padrão)\n"
            "Multi-Query: 3 reformulações da pergunta (+1 LLM call)\n"
            "HyDE: embeds resposta hipotética em vez da pergunta (melhor para perguntas abstractas)"
        )
        source_row.addWidget(self.retrieval_combo)
        source_row.addStretch()
        layout.addLayout(source_row)

        # Filtro por arquivo — QGroupBox checkable: desmarcado = sem filtro
        self.file_filter_box = QGroupBox("Filtrar por arquivo")
        self.file_filter_box.setCheckable(True)
        self.file_filter_box.setChecked(False)
        ff_layout = QVBoxLayout(self.file_filter_box)
        ff_layout.setSpacing(4)

        ff_btn_row = QHBoxLayout()
        select_all_btn = QPushButton("Todos")
        select_all_btn.setFixedWidth(64)
        select_all_btn.clicked.connect(lambda: self._set_all_files_checked(True))
        select_none_btn = QPushButton("Nenhum")
        select_none_btn.setFixedWidth(64)
        select_none_btn.clicked.connect(lambda: self._set_all_files_checked(False))
        ff_btn_row.addWidget(select_all_btn)
        ff_btn_row.addWidget(select_none_btn)
        ff_btn_row.addStretch()
        ff_layout.addLayout(ff_btn_row)

        self.file_list_widget = QListWidget()
        self.file_list_widget.setMaximumHeight(120)
        self.file_list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        ff_layout.addWidget(self.file_list_widget)

        layout.addWidget(self.file_filter_box)

        self.similar_label = QLabel()
        self.similar_label.setObjectName("similarLabel")
        self.similar_label.setVisible(False)
        layout.addWidget(self.similar_label)

        layout.addWidget(QLabel("Resposta:"))
        self.answer_text = QTextEdit()
        self.answer_text.setReadOnly(True)
        self.answer_text.setPlaceholderText("A resposta aparecerá aqui…")
        layout.addWidget(self.answer_text)

        layout.addWidget(QLabel("Fontes:"))
        self.sources_text = QTextEdit()
        self.sources_text.setReadOnly(True)
        self.sources_text.setMaximumHeight(160)
        layout.addWidget(self.sources_text)

        self.tabs.addTab(tab, "Perguntar")

    def _build_tab_summary(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Resumo manual (SummarizeWorker)
        self.summary_btn = QPushButton("Gerar resumo geral")
        self.summary_btn.setEnabled(False)
        self.summary_btn.clicked.connect(self.summarize)
        layout.addWidget(self.summary_btn)
        layout.addWidget(QLabel("Resumo:"))
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        layout.addWidget(self.summary_text)

        # FAQ Generator
        faq_box = QGroupBox("FAQ — Perguntas Frequentes")
        faq_layout = QVBoxLayout(faq_box)
        faq_layout.setSpacing(6)

        self.faq_btn = QPushButton("Gerar FAQ")
        self.faq_btn.setEnabled(False)
        self.faq_btn.setToolTip("Gera perguntas frequentes com respostas a partir dos documentos indexados")
        self.faq_btn.clicked.connect(self._start_faq_generation)
        faq_layout.addWidget(self.faq_btn)

        self.faq_text = QTextEdit()
        self.faq_text.setReadOnly(True)
        self.faq_text.setMaximumHeight(200)
        self.faq_text.setPlaceholderText("Clique em 'Gerar FAQ' para criar perguntas frequentes sobre os documentos indexados…")
        faq_layout.addWidget(self.faq_text)

        layout.addWidget(faq_box)

        # Notebook Guide (gerado automaticamente após indexação)
        guide_box = QGroupBox("Notebook Guide")
        guide_layout = QVBoxLayout(guide_box)
        guide_layout.setSpacing(6)

        guide_layout.addWidget(QLabel("Resumo da coleção:"))
        self.guide_summary_text = QTextEdit()
        self.guide_summary_text.setReadOnly(True)
        self.guide_summary_text.setMaximumHeight(90)
        self.guide_summary_text.setPlaceholderText("Indexe documentos para gerar o guide…")
        guide_layout.addWidget(self.guide_summary_text)

        guide_layout.addWidget(QLabel("Perguntas sugeridas (duplo clique para perguntar):"))
        self.guide_questions_list = QListWidget()
        self.guide_questions_list.setMaximumHeight(110)
        self.guide_questions_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.guide_questions_list.itemDoubleClicked.connect(self._on_guide_question_clicked)
        guide_layout.addWidget(self.guide_questions_list)

        guide_layout.addWidget(QLabel("Pérolas escondidas:"))
        self.guide_gems_text = QTextEdit()
        self.guide_gems_text.setReadOnly(True)
        self.guide_gems_text.setMaximumHeight(110)
        guide_layout.addWidget(self.guide_gems_text)

        self.guide_refresh_btn = QPushButton("Atualizar Guide")
        self.guide_refresh_btn.setEnabled(False)
        self.guide_refresh_btn.setToolTip("Regenera o Notebook Guide para a coleção actual")
        self.guide_refresh_btn.clicked.connect(self._start_guide_generation)
        guide_layout.addWidget(self.guide_refresh_btn)

        layout.addWidget(guide_box)
        self.tabs.addTab(tab, "Resumir")

    def _build_tab_manage(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        info = QGroupBox("Pasta monitorada")
        info_form = QFormLayout(info)
        self.manage_path_label = QLabel(self.config.watched_dir or "—")
        self.manage_path_label.setWordWrap(True)
        self.manage_watcher_label = QLabel("Inativo")
        self.manage_files_label = QLabel("—")
        self.manage_types_label = QLabel("—")
        self.manage_date_label = QLabel("—")
        info_form.addRow("Caminho:", self.manage_path_label)
        info_form.addRow("Watcher:", self.manage_watcher_label)
        info_form.addRow("Arquivos indexados:", self.manage_files_label)
        info_form.addRow("Tipos:", self.manage_types_label)
        info_form.addRow("Última indexação:", self.manage_date_label)
        layout.addWidget(info)

        actions = QHBoxLayout()
        self.refresh_manage_btn = QPushButton("Atualizar informações")
        self.refresh_manage_btn.clicked.connect(self.refresh_manage_info)
        self.update_index_btn = QPushButton("Atualizar índice")
        self.update_index_btn.setEnabled(False)
        self.update_index_btn.setToolTip("Indexa apenas arquivos novos ou modificados desde a última indexação")
        self.update_index_btn.clicked.connect(self.start_update_index)
        self.toggle_watcher_btn = QPushButton("Pausar watcher")
        self.toggle_watcher_btn.setEnabled(False)
        self.toggle_watcher_btn.clicked.connect(self._toggle_watcher)
        self.clear_index_btn = QPushButton("Remover índice")
        self.clear_index_btn.setEnabled(False)
        self.clear_index_btn.clicked.connect(self.clear_index)
        actions.addWidget(self.refresh_manage_btn)
        actions.addWidget(self.update_index_btn)
        actions.addWidget(self.toggle_watcher_btn)
        actions.addWidget(self.clear_index_btn)
        layout.addLayout(actions)

        layout.addWidget(QLabel("Log de eventos:"))
        self.event_log = QTextEdit()
        self.event_log.setReadOnly(True)
        layout.addWidget(self.event_log)

        self.tabs.addTab(tab, "Gerenciar")

    # ── Inicialização Ollama ──────────────────────────────────────────────────

    def _start_ollama_check(self) -> None:
        self.statusBar().showMessage("Verificando Ollama…")
        self._ollama_worker = OllamaCheckWorker()
        self._ollama_worker.models_loaded.connect(self._on_models_loaded)
        self._ollama_worker.ollama_unavailable.connect(self._on_ollama_unavailable)
        self._ollama_worker.start()

    def _on_models_loaded(self, models: list) -> None:
        self._available_models = models
        self._ollama_ok = True
        self._retry_timer.stop()
        self.ollama_banner.setVisible(False)
        self.config_btn.setEnabled(True)
        self.statusBar().showMessage(
            f"Ollama ativo — {len(models)} modelo(s) disponível(is)."
        )

        available_names = {m.name for m in models}
        llm_ok    = not self.config.llm_model    or self.config.llm_model    in available_names
        embed_ok  = not self.config.embed_model  or self.config.embed_model  in available_names

        if not self.config.is_configured or not llm_ok or not embed_ok:
            if self.config.is_configured and (not llm_ok or not embed_ok):
                missing: list[str] = []
                if not llm_ok:
                    missing.append(f"LLM '{self.config.llm_model}'")
                if not embed_ok:
                    missing.append(f"embedding '{self.config.embed_model}'")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "Modelo não encontrado",
                    "O(s) modelo(s) configurado(s) não estão disponíveis neste computador:\n"
                    + "\n".join(f"  • {m}" for m in missing)
                    + "\n\nEscolha os modelos disponíveis para continuar.",
                )
            self._show_setup_dialog()
        else:
            self._post_config_init()

    def _on_ollama_unavailable(self, message: str) -> None:
        self._ollama_ok = False
        self.ollama_banner.setVisible(True)
        self.config_btn.setEnabled(True)
        self.statusBar().showMessage("Ollama indisponível — aguardando reconexão…")
        self._log_event(f"Ollama indisponível: {message}")
        if not self._retry_timer.isActive():
            self._retry_timer.start()

    def _retry_ollama_check(self) -> None:
        """Tenta reconectar ao Ollama silenciosamente em background."""
        if self._ollama_ok:
            self._retry_timer.stop()
            return
        worker = OllamaCheckWorker()
        worker.models_loaded.connect(self._on_models_loaded)
        worker.ollama_unavailable.connect(lambda _: None)  # silencioso no retry
        worker.start()
        # Manter referência para evitar GC prematuro
        self._retry_worker = worker

    # ── Configuração ─────────────────────────────────────────────────────────

    def _show_setup_dialog(self) -> None:
        dialog = SetupDialog(self._available_models, self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            folder, llm, embed, vault = dialog.get_values()
            if not folder:
                QMessageBox.warning(self, "Aviso", "Selecione uma pasta para continuar.")
                return
            self.config.watched_dir = folder
            self.config.llm_model = llm
            self.config.embed_model = embed
            self.config.vault_dir = vault
            save_config(self.config)
            self._post_config_init()
        else:
            self.statusBar().showMessage("Configuração cancelada.")

    def open_config(self) -> None:
        dialog = SetupDialog(self._available_models, self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            folder, llm, embed, vault = dialog.get_values()
            if not folder:
                return
            changed_dir = folder != self.config.watched_dir
            self.config.watched_dir = folder
            self.config.llm_model = llm
            self.config.embed_model = embed
            self.config.vault_dir = vault
            save_config(self.config)
            self.folder_label.setText(folder)
            self.manage_path_label.setText(folder)
            if changed_dir:
                self.vectorstore = None
                self._disable_query_buttons()
            self._log_event("Configuração atualizada.")
            self._post_config_init()

    def _post_config_init(self) -> None:
        """Chamado após configuração válida estar disponível."""
        self.folder_label.setText(self.config.watched_dir)
        self.manage_path_label.setText(self.config.watched_dir)

        if self.config.mnemosyne_dir:
            self._collection_index = CollectionIndex(self.config.mnemosyne_dir)
            self._file_tracker = FileTracker(self.config.mnemosyne_dir)
            self._memory_store = MemoryStore(self.config.mnemosyne_dir)

        self._update_badge()

        try:
            self.vectorstore = load_vectorstore(self.config)
            self._enable_query_buttons()
            self.statusBar().showMessage("Memória carregada.")
            self._log_event("Vectorstore carregado com sucesso.")
        except VectorstoreNotFoundError:
            self.statusBar().showMessage(
                "Nenhum índice encontrado. Use 'Indexar tudo'."
            )
            self._log_event("Nenhum índice encontrado — use 'Indexar tudo'.")

        self._populate_file_list()
        self._load_guide_into_ui()
        self.index_btn.setEnabled(True)
        self.refresh_manage_info()

        if self.config.auto_index_on_change:
            self._start_watcher()

    # ── Watcher ───────────────────────────────────────────────────────────────

    def _start_watcher(self) -> None:
        from core.watcher import FolderWatcher

        if hasattr(self, "_watcher") and self._watcher is not None:
            self._watcher.stop()

        self._watcher = FolderWatcher(self)
        self._watcher.file_added.connect(self._on_file_added)
        self._watcher.file_removed.connect(self._on_file_removed)
        self._watcher.watch(self.config.watched_dir)
        self.toggle_watcher_btn.setEnabled(True)
        self._update_watcher_label()
        self._log_event(f"Watcher ativo em: {self.config.watched_dir}")

    def _update_watcher_label(self) -> None:
        watcher = getattr(self, "_watcher", None)
        if watcher and watcher.is_active:
            if watcher.is_enabled:
                self.manage_watcher_label.setText("✔ Ativo")
                self.manage_watcher_label.setStyleSheet("color:#4A6741; font-weight:bold;")
                self.toggle_watcher_btn.setText("Pausar watcher")
            else:
                self.manage_watcher_label.setText("⏸ Pausado")
                self.manage_watcher_label.setStyleSheet("color:#b8860b; font-weight:bold;")
                self.toggle_watcher_btn.setText("Retomar watcher")
        else:
            self.manage_watcher_label.setText("Inativo")
            self.manage_watcher_label.setStyleSheet("color:#9C8E7A;")

    def _toggle_watcher(self) -> None:
        watcher = getattr(self, "_watcher", None)
        if not watcher or not watcher.is_active:
            return
        watcher.set_enabled(not watcher.is_enabled)
        self._update_watcher_label()
        state = "retomado" if watcher.is_enabled else "pausado"
        self._log_event(f"Watcher {state}.")

    def _on_file_added(self, file_path: str) -> None:
        name = os.path.basename(file_path)
        self.statusBar().showMessage(f"Novo arquivo: {name} — indexando…")
        self._log_event(f"Novo arquivo detectado: {name}")

        self._file_worker = IndexFileWorker(file_path, self.config)
        self._file_worker.finished.connect(self._on_file_indexed)
        self._file_worker.start()

    def _on_file_removed(self, file_path: str) -> None:
        import os
        name = os.path.basename(file_path)
        self._log_event(f"Arquivo removido/renomeado: {name}")
        self.refresh_manage_info()

    def _on_file_indexed(self, success: bool, message: str) -> None:
        self._log_event(message)
        if success:
            self._populate_file_list()
            try:
                self.vectorstore = load_vectorstore(self.config)
                self._enable_query_buttons()
                self.refresh_manage_info()
            except VectorstoreNotFoundError:
                pass
        self.statusBar().showMessage(message)

    # ── Indexação ─────────────────────────────────────────────────────────────

    def start_indexing(self) -> None:
        if not self.config.watched_dir or not os.path.isdir(self.config.watched_dir):
            QMessageBox.warning(
                self, "Aviso", "Pasta monitorada inválida. Configure primeiro."
            )
            return

        self.index_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.statusBar().showMessage("Indexando documentos…")
        self._log_event(f"Iniciando indexação de: {self.config.watched_dir}")

        self._index_worker = IndexWorker(self.config)
        self._index_worker.finished.connect(self._on_index_finished)
        self._index_worker.progress.connect(self._on_index_progress)
        self._index_worker.start()

    def start_update_index(self) -> None:
        self.update_index_btn.setEnabled(False)
        self.index_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.statusBar().showMessage("Actualizando índice incrementalmente…")
        self._log_event("Iniciando actualização incremental do índice.")

        self._update_worker = UpdateIndexWorker(self.config)
        self._update_worker.finished.connect(self._on_update_index_finished)
        self._update_worker.start()

    def _on_update_index_finished(self, success: bool, message: str) -> None:
        self.progress.setVisible(False)
        self.index_btn.setEnabled(True)
        self._log_event(message)
        if success:
            self._update_badge()
            self._populate_file_list()
            try:
                self.vectorstore = load_vectorstore(self.config)
                self._enable_query_buttons()
                self.refresh_manage_info()
            except VectorstoreNotFoundError as exc:
                QMessageBox.critical(self, "Erro", str(exc))
        else:
            self.update_index_btn.setEnabled(True)
            QMessageBox.warning(self, "Aviso", message)
        self.statusBar().showMessage(message)

    def _on_index_progress(self, name: str, pos: int, total: int) -> None:
        self.statusBar().showMessage(f"Indexando {name}… ({pos}/{total})")

    def _on_index_finished(self, success: bool, message: str) -> None:
        self.index_btn.setEnabled(True)
        self.progress.setVisible(False)
        self._log_event(message)

        if success:
            self._update_collection_index()
            self._update_badge()
            self._populate_file_list()
            try:
                self.vectorstore = load_vectorstore(self.config)
                self._enable_query_buttons()
                self.refresh_manage_info()
            except VectorstoreNotFoundError as exc:
                QMessageBox.critical(self, "Erro", str(exc))
            self._start_guide_generation()
        else:
            QMessageBox.critical(self, "Erro na indexação", message)

        self.statusBar().showMessage(message)

    def _update_collection_index(self) -> None:
        """Actualiza CollectionIndex com o estado actual da pasta e marca tracker."""
        if not self._collection_index or not self.config.watched_dir:
            return
        from collections import Counter
        from datetime import datetime

        supported = {".pdf", ".docx", ".txt", ".md", ".epub"}
        count = 0
        types: Counter = Counter()
        for root, dirs, files in os.walk(self.config.watched_dir):
            dirs[:] = [d for d in dirs if d != ".mnemosyne"]
            for f in files:
                _, ext = os.path.splitext(f.lower())
                if ext in supported:
                    full = os.path.join(root, f)
                    count += 1
                    types[ext] += 1
                    if self._file_tracker:
                        self._file_tracker.mark_indexed(full)

        info = CollectionInfo(
            name=os.path.basename(self.config.watched_dir),
            path=self.config.watched_dir,
            total_files=count,
            last_indexed=datetime.now().isoformat(),
            file_types=dict(types),
        )
        self._collection_index.update(info)

    def _update_badge(self) -> None:
        """Actualiza o badge de pendentes (novos/modificados vs índice)."""
        if not self._file_tracker or not self.config.watched_dir:
            self.badge_label.setVisible(False)
            return
        try:
            new, modified, _ = self._file_tracker.get_pending(self.config.watched_dir)
        except Exception:
            self.badge_label.setVisible(False)
            return

        total = len(new) + len(modified)
        if total == 0:
            self.badge_label.setText("✓ índice actualizado")
            self.badge_label.setStyleSheet(
                "padding: 3px 8px; border-radius: 2px; font-weight: bold;"
                "background: #4A6741; color: #F5F0E8;"
            )
        else:
            parts = []
            if new:
                parts.append(f"{len(new)} novo(s)")
            if modified:
                parts.append(f"{len(modified)} modificado(s)")
            self.badge_label.setText(" / ".join(parts) + " por indexar")
            self.badge_label.setStyleSheet(
                "padding: 3px 8px; border-radius: 2px; font-weight: bold;"
                "background: #b8860b; color: #F5F0E8;"
            )
        self.badge_label.setVisible(True)

    # ── FAQ Generator ─────────────────────────────────────────────────────────

    def _start_faq_generation(self) -> None:
        """Inicia geração do FAQ em background com streaming."""
        if self.vectorstore is None:
            return
        self.faq_btn.setEnabled(False)
        self.faq_text.clear()
        self._raw_faq = ""
        self._log_event("Gerando FAQ…")
        self._faq_worker = FaqWorker(self.vectorstore, self.config)
        self._faq_worker.token.connect(self._on_faq_token)
        self._faq_worker.finished.connect(self._on_faq_finished)
        self._faq_worker.start()

    def _on_faq_token(self, chunk: str) -> None:
        self._raw_faq += chunk
        self.faq_text.setPlainText(self._raw_faq)
        sb = self.faq_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_faq_finished(self, success: bool, error: str, items: list) -> None:
        self.faq_btn.setEnabled(self.vectorstore is not None)
        if success:
            lines = []
            for i, item in enumerate(items, 1):
                lines.append(f"P{i}: {item['question']}")
                lines.append(f"R: {item['answer']}")
                lines.append("")
            self.faq_text.setPlainText("\n".join(lines).strip())
            self._log_event(f"FAQ gerado — {len(items)} pergunta(s).")
        else:
            self.faq_text.setPlainText(f"Erro: {error}")
            self._log_event(f"Erro ao gerar FAQ: {error}")

    # ── Notebook Guide ────────────────────────────────────────────────────────

    def _start_guide_generation(self) -> None:
        """Inicia geração do Notebook Guide em background."""
        if self.vectorstore is None or not self.config.mnemosyne_dir:
            return
        self.guide_refresh_btn.setEnabled(False)
        self._log_event("Gerando Notebook Guide…")
        self._guide_worker = GuideWorker(
            self.vectorstore, self.config, self.config.mnemosyne_dir
        )
        self._guide_worker.finished.connect(self._on_guide_finished)
        self._guide_worker.start()

    def _on_guide_finished(self, success: bool, message: str) -> None:
        self._log_event(message)
        if success:
            self._load_guide_into_ui()
        self.guide_refresh_btn.setEnabled(self.vectorstore is not None)

    def _load_guide_into_ui(self) -> None:
        """Carrega guide.json e preenche os widgets do painel Guide."""
        if not self.config.mnemosyne_dir:
            return
        from core.guide import load_guide, GuideError
        try:
            result = load_guide(self.config.mnemosyne_dir)
        except GuideError as exc:
            self._log_event(f"Guide: {exc}")
            return

        if result is None:
            return

        self.guide_summary_text.setPlainText(result["summary"])

        self.guide_questions_list.clear()
        for q in result["questions"]:
            self.guide_questions_list.addItem(q)

        gems = result.get("hidden_gems", [])
        if gems:
            parts = []
            for gem in gems:
                fact = gem.get("fact", "")
                citation = gem.get("citation", "")
                entry = f"★ {fact}"
                if citation:
                    entry += f'\n  "{citation}"'
                parts.append(entry)
            self.guide_gems_text.setPlainText("\n\n".join(parts))
        else:
            self.guide_gems_text.setPlainText("(nenhuma pérola identificada)")

    def _on_guide_question_clicked(self, item: QListWidgetItem) -> None:
        """Popula o campo de pergunta e muda para a aba Perguntar."""
        self.question_edit.setText(item.text())
        self.tabs.setCurrentIndex(0)

    # ── Seleção de arquivos ───────────────────────────────────────────────────

    def _populate_file_list(self) -> None:
        """Popula a lista de arquivos com checkboxes na aba Perguntar."""
        self.file_list_widget.clear()
        supported = {".pdf", ".docx", ".txt", ".md", ".epub"}
        paths: list[str] = []

        if self.config.watched_dir and os.path.isdir(self.config.watched_dir):
            for root, dirs, files in os.walk(self.config.watched_dir):
                dirs[:] = [d for d in dirs if d != ".mnemosyne"]
                for f in sorted(files):
                    _, ext = os.path.splitext(f.lower())
                    if ext in supported:
                        paths.append(os.path.join(root, f))

        if self.config.vault_dir and os.path.isdir(self.config.vault_dir):
            for root, dirs, files in os.walk(self.config.vault_dir):
                dirs[:] = [d for d in dirs if d not in {".obsidian", "templates", "attachments"}]
                for f in sorted(files):
                    if f.lower().endswith(".md"):
                        paths.append(os.path.join(root, f))

        for path in paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.file_list_widget.addItem(item)

        if not paths:
            placeholder = QListWidgetItem("(nenhum arquivo encontrado)")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.file_list_widget.addItem(placeholder)

    def _set_all_files_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            if item and (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                item.setCheckState(state)

    def _get_selected_files(self) -> list[str] | None:
        """
        Retorna lista de paths selecionados, ou None se o filtro estiver
        inativo ou todos os arquivos estiverem marcados (= sem restrição).
        """
        if not self.file_filter_box.isChecked():
            return None
        total = 0
        selected: list[str] = []
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            if not item or not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                continue
            total += 1
            if item.checkState() == Qt.CheckState.Checked:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path:
                    selected.append(path)
        # Todos marcados = sem filtro; nenhum marcado = sem filtro (evita resultado vazio)
        if not selected or len(selected) == total:
            return None
        return selected

    # ── Consulta ──────────────────────────────────────────────────────────────

    def ask_question(self) -> None:
        if self.vectorstore is None:
            QMessageBox.warning(
                self, "Aviso", "Nenhuma memória indexada. Indexe primeiro."
            )
            return
        question = self.question_edit.text().strip()
        if not question:
            return

        similar = self._session_memory.find_similar(question)
        if similar:
            preview = similar.question[:60]
            self.similar_label.setText(f'Pergunta similar encontrada: "{preview}…"')
            self.similar_label.setVisible(True)
        else:
            self.similar_label.setVisible(False)

        self.ask_btn.setEnabled(False)
        self._raw_answer = ""
        self.answer_text.setPlainText("")
        self.sources_text.clear()
        self.cancel_btn.setVisible(True)
        self.statusBar().showMessage("Consultando Mnemosyne…")

        source_map = {"Biblioteca": "biblioteca", "Vault": "vault", "Ambos": None}
        source_type = source_map.get(self.source_combo.currentText())

        retrieval_map = {"Híbrido": "hybrid", "Multi-Query": "multi_query", "HyDE": "hyde"}
        retrieval_mode = retrieval_map.get(self.retrieval_combo.currentText(), "hybrid")

        source_files = self._get_selected_files()

        self._ask_worker = AskWorker(
            self.vectorstore, question, self.config,
            self._chat_history, source_type, retrieval_mode,
            self._file_tracker, source_files=source_files,
        )
        self._ask_worker.token.connect(self._on_ask_token)
        self._ask_worker.finished.connect(self._on_answer)
        self._ask_worker.start()

    def _on_ask_token(self, chunk: str) -> None:
        self._raw_answer += chunk
        self.answer_text.setPlainText(self._raw_answer)
        sb = self.answer_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_answer(self, success: bool, text: str, sources: list, updated_history: list) -> None:
        self.cancel_btn.setVisible(False)
        if success:
            self.answer_text.setPlainText(text)
            self._chat_history = updated_history
            self._session_memory.save_query(
                self.question_edit.text().strip(), text,
                [s["path"] for s in sources],
            )
            if sources:
                lines = []
                for s in sources:
                    name = os.path.basename(s["path"])
                    pct = int(s["score"] * 100)
                    filled = round(s["score"] * 10)
                    bar = "█" * filled + "░" * (10 - filled)
                    excerpt = s["excerpt"]
                    if len(excerpt) > 180:
                        excerpt = excerpt[:180] + "…"
                    lines.append(f"• {name}  {bar} {pct}%\n  \"{excerpt}\"")
                self.sources_text.setPlainText("\n\n".join(lines))
            else:
                self.sources_text.setPlainText("(nenhuma fonte identificada)")
        else:
            self.answer_text.setPlainText(f"Erro: {text}")
            self.sources_text.clear()

        self.ask_btn.setEnabled(True)
        self.statusBar().showMessage("Pronto." if success else "Interrompido.")

    def _reset_conversation(self) -> None:
        self._chat_history = []
        self._session_memory.clear()
        self.answer_text.clear()
        self.sources_text.clear()
        self.similar_label.setVisible(False)
        self.question_edit.clear()
        self._log_event("Nova conversa iniciada.")

    # ── Resumo ────────────────────────────────────────────────────────────────

    def summarize(self) -> None:
        if self.vectorstore is None:
            QMessageBox.warning(
                self, "Aviso", "Nenhuma memória indexada. Indexe primeiro."
            )
            return
        self.summary_btn.setEnabled(False)
        self._raw_summary = ""
        self.summary_text.setPlainText("")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.cancel_btn.setVisible(True)
        self.statusBar().showMessage("Sintetizando documentos…")

        self._summary_worker = SummarizeWorker(self.vectorstore, self.config)
        self._summary_worker.token.connect(self._on_summary_token)
        self._summary_worker.finished.connect(self._on_summary)
        self._summary_worker.start()

    def _on_summary_token(self, chunk: str) -> None:
        self._raw_summary += chunk
        self.summary_text.setPlainText(self._raw_summary)
        sb = self.summary_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_summary(self, success: bool, text: str) -> None:
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.summary_text.setPlainText(text if success else f"Erro: {text}")
        self.summary_btn.setEnabled(True)
        self.statusBar().showMessage("Pronto." if success else "Interrompido.")

    # ── Tab Gerenciar ─────────────────────────────────────────────────────────

    def refresh_manage_info(self) -> None:
        if not self.config.persist_dir:
            return

        from collections import Counter

        # Inspecionar arquivos no watched_dir (sem depender do vectorstore)
        if self.config.watched_dir and os.path.isdir(self.config.watched_dir):
            supported = {".pdf", ".docx", ".txt", ".md"}
            count = 0
            types: Counter = Counter()
            for root, dirs, files in os.walk(self.config.watched_dir):
                dirs[:] = [d for d in dirs if d != ".mnemosyne"]
                for f in files:
                    _, ext = os.path.splitext(f.lower())
                    if ext in supported:
                        count += 1
                        types[ext] += 1

            self.manage_files_label.setText(
                f"{count} arquivo(s) na pasta"
                + (" (indexados)" if self.vectorstore else " (não indexados)")
            )
            if types:
                self.manage_types_label.setText(
                    "  ".join(f"{ext}: {n}" for ext, n in sorted(types.items()))
                )
            else:
                self.manage_types_label.setText("—")
        else:
            self.manage_files_label.setText("—")
            self.manage_types_label.setText("—")

        # Última indexação a partir do CollectionIndex
        if self._collection_index and self.config.watched_dir:
            info = self._collection_index.get(self.config.watched_dir)
            if info and info.last_indexed:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(info.last_indexed)
                    self.manage_date_label.setText(dt.strftime("%d/%m/%Y %H:%M"))
                except ValueError:
                    self.manage_date_label.setText(info.last_indexed)
            else:
                self.manage_date_label.setText("—")

        self.clear_index_btn.setEnabled(
            bool(self.config.persist_dir and os.path.exists(self.config.persist_dir))
        )
        self._update_watcher_label()

    def clear_index(self) -> None:
        reply = QMessageBox.question(
            self,
            "Confirmar",
            "Remover o índice apagará todos os dados do vectorstore.\nDeseja continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        import shutil

        persist_dir = self.config.persist_dir
        if persist_dir and os.path.exists(persist_dir):
            try:
                shutil.rmtree(persist_dir)
                self.vectorstore = None
                self._disable_query_buttons()
                self.clear_index_btn.setEnabled(False)
                self._log_event("Índice removido.")
                self.refresh_manage_info()
                self.statusBar().showMessage("Índice removido.")
            except OSError as exc:
                QMessageBox.critical(
                    self, "Erro", f"Não foi possível remover o índice: {exc}"
                )

    # ── Fecho da janela ───────────────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Ao fechar: se houver histórico na sessão, oferece compactar e guardar
        na memória persistida antes de encerrar.
        """
        if not self._chat_history or self._memory_store is None:
            event.accept()
            return

        reply = QMessageBox.question(
            self,
            "Guardar conversa?",
            "Guardar esta conversa na memória antes de fechar?\n\n"
            "Os factos relevantes serão extraídos e persistidos para sessões futuras.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )

        if reply == QMessageBox.StandardButton.Cancel:
            event.ignore()
            return

        if reply == QMessageBox.StandardButton.Yes:
            # Persistir turnos no histórico antes de compactar
            try:
                for turn in self._chat_history:
                    self._memory_store.append_turn(turn)
            except OSError:
                pass

            self._compact_worker = CompactMemoryWorker(
                self._memory_store, self.config.llm_model
            )
            self.statusBar().showMessage("A guardar memória…")
            self._compact_worker.start()
            # Aguarda no máximo 15 s para não bloquear indefinidamente
            self._compact_worker.wait(15_000)

        event.accept()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _cancel_worker(self) -> None:
        for attr in ("_ask_worker", "_summary_worker"):
            worker = getattr(self, attr, None)
            if worker and worker.isRunning():
                worker.requestInterruption()
                break

    def _enable_query_buttons(self) -> None:
        self.ask_btn.setEnabled(True)
        self.summary_btn.setEnabled(True)
        self.faq_btn.setEnabled(True)
        self.clear_index_btn.setEnabled(True)
        self.update_index_btn.setEnabled(True)
        self.guide_refresh_btn.setEnabled(True)

    def _disable_query_buttons(self) -> None:
        self.ask_btn.setEnabled(False)
        self.summary_btn.setEnabled(False)
        self.faq_btn.setEnabled(False)
        self.update_index_btn.setEnabled(False)
        self.guide_refresh_btn.setEnabled(False)

    def _log_event(self, message: str) -> None:
        from datetime import datetime

        ts = datetime.now().strftime("%H:%M:%S")
        self.event_log.append(f"[{ts}] {message}")

    def _load_fonts(self) -> None:
        """Carrega IM Fell English, Special Elite e Courier Prime do sistema."""
        from PySide6.QtGui import QFontDatabase

        font_dirs = [
            os.path.expanduser("~/.local/share/fonts"),
            "/usr/share/fonts",
            "/usr/local/share/fonts",
        ]
        targets = {"IM Fell English", "Special Elite", "Courier Prime"}
        for font_dir in font_dirs:
            if not os.path.isdir(font_dir):
                continue
            for root, _, files in os.walk(font_dir):
                for fname in files:
                    if fname.lower().endswith((".ttf", ".otf")):
                        if any(t.replace(" ", "").lower() in fname.lower().replace(" ", "").replace("-", "") for t in targets):
                            QFontDatabase.addApplicationFont(os.path.join(root, fname))

    def apply_style(self) -> None:
        self._load_fonts()
        style_path = os.path.join(os.path.dirname(__file__), "styles.qss")
        if os.path.exists(style_path):
            with open(style_path, encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        else:
            self.setStyleSheet(
                """
                QMainWindow { background-color: #F5F0E8; }
                QLabel { color: #5C4E3A; }
                QPushButton {
                    background-color: #EDE7D9;
                    border: 1px solid #C4B9A8;
                    padding: 5px 14px;
                    border-radius: 2px;
                    color: #5C4E3A;
                }
                QPushButton:hover { background-color: #E0D8C8; border-color: #7A5C2E; }
                QPushButton:disabled { background-color: #EDE7D9; color: #C4B9A8; }
                QLineEdit, QTextEdit {
                    background-color: #F5F0E8;
                    border: 1px solid #C4B9A8;
                    border-radius: 2px;
                    padding: 4px 8px;
                    color: #2C2416;
                }
                QTabWidget::pane { border: 1px solid #C4B9A8; background-color: #F5F0E8; }
                QTabBar::tab { background-color: #EDE7D9; padding: 5px 16px; color: #9C8E7A; border: 1px solid #C4B9A8; border-bottom: none; }
                QTabBar::tab:selected { background-color: #F5F0E8; color: #2C2416; border-bottom: 2px solid #b8860b; }
                QGroupBox { border: 1px solid #C4B9A8; border-radius: 2px; margin-top: 10px; padding: 8px; }
                QGroupBox::title { color: #5C4E3A; }
                """
            )


def run() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
