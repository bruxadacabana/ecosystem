# Janela principal do Mnemosyne
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.config import AppConfig, load_config, save_config
from core.errors import ConfigError, VectorstoreNotFoundError
from core.indexer import IndexCheckpoint, load_vectorstore
from core.memory import (
    ChatSession,
    CollectionIndex,
    CollectionInfo,
    MemoryStore,
    SessionManager,
    SessionMemory,
    Turn,
)
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
    ResumeIndexWorker,
    StudioWorker,
    SummarizeWorker,
    UpdateIndexWorker,
)


class SetupDialog(QDialog):
    """Diálogo de configuração — modelos LLM/embedding, pasta biblioteca, toggles de ecossistema."""

    def __init__(
        self,
        models: list[OllamaModel],
        current: AppConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuração do Mnemosyne")
        self.setMinimumWidth(540)

        from PySide6.QtWidgets import QCheckBox, QScrollArea
        from core.collections import available_ecosystem_paths

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Configure o Mnemosyne.\nAs configurações são salvas em config.json."))

        form = QFormLayout()

        # Pasta principal (Biblioteca do utilizador)
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit(current.watched_dir)
        self.folder_edit.setPlaceholderText("Selecione a pasta com seus documentos…")
        folder_btn = QPushButton("Escolher…")
        folder_btn.clicked.connect(self._pick_folder)
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(folder_btn)
        form.addRow("Biblioteca (pasta):", folder_row)

        chat_models = filter_chat_models(models)
        embed_models = filter_embed_models(models)

        # Perfil de hardware do LOGOS (para botões "Recomendado")
        self._logos_llm = ""
        self._logos_embed = ""
        self._logos_display = ""
        try:
            from pathlib import Path as _Path
            _root = str(_Path(__file__).parent.parent.parent)
            if _root not in sys.path:
                sys.path.insert(0, _root)
            from ecosystem_client import get_active_profile as _get_profile
            _p = _get_profile()
            if _p:
                self._logos_llm     = _p.get("models", {}).get("llm_mnemosyne", "")
                self._logos_embed   = _p.get("models", {}).get("embed", "")
                self._logos_display = _p.get("profile_display", "")
        except Exception:
            pass

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
        llm_row = QHBoxLayout()
        llm_row.setContentsMargins(0, 0, 0, 0)
        llm_row.addWidget(self.llm_combo, 1)
        llm_rec_btn = QPushButton("↩ Recomendado")
        llm_rec_btn.setToolTip(
            f"Recomendado pelo LOGOS ({self._logos_display}): {self._logos_llm}"
            if self._logos_llm else "LOGOS não disponível"
        )
        llm_rec_btn.setEnabled(bool(self._logos_llm))
        llm_rec_btn.clicked.connect(self._use_logos_llm)
        llm_row.addWidget(llm_rec_btn)
        form.addRow("Modelo LLM:", llm_row)

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
        self.embed_combo.setToolTip("Usado na indexação — roda na sua máquina via Ollama")
        embed_row = QHBoxLayout()
        embed_row.setContentsMargins(0, 0, 0, 0)
        embed_row.addWidget(self.embed_combo, 1)
        embed_rec_btn = QPushButton("↩ Recomendado")
        embed_rec_btn.setToolTip(
            f"Recomendado pelo LOGOS ({self._logos_display}): {self._logos_embed}"
            if self._logos_embed else "LOGOS não disponível"
        )
        embed_rec_btn.setEnabled(bool(self._logos_embed))
        embed_rec_btn.clicked.connect(self._use_logos_embed)
        embed_row.addWidget(embed_rec_btn)
        form.addRow("Modelo de embedding:", embed_row)

        layout.addLayout(form)

        # Integrações do ecossistema (toggles por fonte detectada)
        eco_paths = available_ecosystem_paths()
        self._eco_checkboxes: dict[str, QCheckBox] = {}
        if eco_paths:
            eco_group = QGroupBox("Integrações do ecossistema")
            eco_layout = QVBoxLayout(eco_group)
            eco_layout.addWidget(QLabel(
                "Pastas detectadas automaticamente — activa/desactiva a indexação:"
            ))
            for label, eco_key, path in eco_paths:
                cb = QCheckBox(f"{label}  —  {path}")
                cb.setChecked(current.ecosystem_enabled.get(eco_key, True))
                eco_layout.addWidget(cb)
                self._eco_checkboxes[eco_key] = cb
            layout.addWidget(eco_group)

        # Opções de qualidade
        opts_group = QGroupBox("Opções de qualidade")
        opts_layout = QVBoxLayout(opts_group)
        self.reranking_check = QCheckBox("Reranking semântico (FlashRank) — melhora precisão, usa ~200 MB RAM extra")
        self.reranking_check.setChecked(current.reranking_enabled)
        opts_layout.addWidget(self.reranking_check)
        layout.addWidget(opts_group)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _use_logos_llm(self) -> None:
        if not self._logos_llm:
            return
        idx = self.llm_combo.findText(self._logos_llm)
        if idx >= 0:
            self.llm_combo.setCurrentIndex(idx)

    def _use_logos_embed(self) -> None:
        if not self._logos_embed:
            return
        idx = self.embed_combo.findText(self._logos_embed)
        if idx >= 0:
            self.embed_combo.setCurrentIndex(idx)

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Selecionar pasta de documentos")
        if folder:
            self.folder_edit.setText(folder)

    def get_values(self) -> tuple[str, str, str, dict[str, bool], bool]:
        """Retorna (library_path, llm_model, embed_model, ecosystem_enabled, reranking_enabled)."""
        eco_enabled = {key: cb.isChecked() for key, cb in self._eco_checkboxes.items()}
        return (
            self.folder_edit.text().strip(),
            self.llm_combo.currentText(),
            self.embed_combo.currentText(),
            eco_enabled,
            self.reranking_check.isChecked(),
        )


class NewCollectionDialog(QDialog):
    """Diálogo para criar uma nova coleção — nome, caminho e tipo."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QButtonGroup, QRadioButton
        self.setWindowTitle("Nova Coleção")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ex: Notas de filosofia, Vault pessoal…")
        form.addRow("Nome:", self.name_edit)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Selecione a pasta da coleção…")
        self.path_edit.textChanged.connect(self._on_path_changed)
        path_btn = QPushButton("…")
        path_btn.setFixedWidth(32)
        path_btn.clicked.connect(self._pick_path)
        path_row.addWidget(self.path_edit)
        path_row.addWidget(path_btn)
        form.addRow("Pasta:", path_row)

        layout.addLayout(form)

        # Tipo de coleção
        type_group = QGroupBox("Tipo")
        type_layout = QVBoxLayout(type_group)
        self._rb_library = QRadioButton("📚  Biblioteca — vozes externas (livros, artigos, documentos)")
        self._rb_vault   = QRadioButton("🔮  Vault Obsidian — memória pessoal (notas e pensamentos)")
        self._rb_library.setChecked(True)
        type_layout.addWidget(self._rb_library)
        type_layout.addWidget(self._rb_vault)
        layout.addWidget(type_group)

        self._auto_label = QLabel()
        self._auto_label.setObjectName("sidebarFolder")
        self._auto_label.setVisible(False)
        layout.addWidget(self._auto_label)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _pick_path(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Selecionar pasta da coleção")
        if folder:
            self.path_edit.setText(folder)
            if not self.name_edit.text().strip():
                self.name_edit.setText(os.path.basename(folder))

    def _on_path_changed(self, path: str) -> None:
        """Auto-detecta .obsidian/ e pré-seleciona tipo Vault."""
        obsidian = os.path.isdir(os.path.join(path.strip(), ".obsidian"))
        if obsidian:
            self._rb_vault.setChecked(True)
            self._auto_label.setText("✔  Vault Obsidian detectado automaticamente")
            self._auto_label.setVisible(True)
        else:
            self._rb_library.setChecked(True)
            self._auto_label.setVisible(False)

    def get_values(self) -> tuple[str, str, "CollectionType"]:
        from core.collections import CollectionType
        coll_type = CollectionType.VAULT if self._rb_vault.isChecked() else CollectionType.LIBRARY
        return self.name_edit.text().strip(), self.path_edit.text().strip(), coll_type


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
        self._session_manager: SessionManager | None = None
        self._current_session: ChatSession | None = None
        self._updating_sessions = False
        self._ollama_ok = False
        self._raw_answer = ""
        self._raw_summary = ""
        self._raw_faq = ""
        self._studio_raw = ""
        self._studio_worker: StudioWorker | None = None
        self._studio_table_data: tuple[list[str], list[list[str]]] | None = None

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
            if self.config.persist_dir:
                data["index_paths"] = [self.config.persist_dir]
            write_section("mnemosyne", data)
        except Exception:
            pass

    def _open_new_collection_dialog(self) -> None:
        dialog = NewCollectionDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, path, coll_type = dialog.get_values()
        if not name or not path:
            QMessageBox.warning(self, "Aviso", "Nome e caminho são obrigatórios.")
            return
        from core.collections import CollectionConfig
        coll = CollectionConfig(name=name, path=path, type=coll_type, source="user")
        self.config.collections.append(coll)
        self.config.active_collection = name
        save_config(self.config)
        self._populate_collection_combo()
        self._post_config_init()
        self._log_event(f"Coleção adicionada: {name} ({coll_type.value})")

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Ollama banner
        self.ollama_banner = QLabel(
            "⚠  Ollama não encontrado. Inicie o Ollama para usar o Mnemosyne."
        )
        self.ollama_banner.setObjectName("ollamaBanner")
        self.ollama_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ollama_banner.setVisible(False)
        root.addWidget(self.ollama_banner)

        # ── Splitter principal ──────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")
        splitter.setHandleWidth(1)

        # ── Sidebar ─────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(234)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(14, 18, 14, 14)
        sb.setSpacing(4)

        # Brand
        brand_lbl = QLabel("Mnemosyne")
        brand_lbl.setObjectName("sidebarBrand")
        sb.addWidget(brand_lbl)

        # Seletor de coleção ativa + botão nova coleção
        coll_row = QHBoxLayout()
        coll_row.setContentsMargins(0, 0, 0, 0)
        coll_row.setSpacing(4)
        self.collection_combo = QComboBox()
        self.collection_combo.setToolTip("Coleção ativa — clique para trocar")
        self.collection_combo.currentIndexChanged.connect(self._on_collection_changed)
        coll_add_btn = QPushButton("+")
        coll_add_btn.setFixedSize(22, 22)
        coll_add_btn.setToolTip("Nova coleção")
        coll_add_btn.clicked.connect(self._open_new_collection_dialog)
        coll_row.addWidget(self.collection_combo, 1)
        coll_row.addWidget(coll_add_btn)
        sb.addLayout(coll_row)

        self.folder_label = QLabel(self.config.watched_dir or "Pasta não configurada")
        self.folder_label.setObjectName("sidebarFolder")
        self.folder_label.setWordWrap(True)
        sb.addWidget(self.folder_label)

        sb.addSpacing(12)

        # Nav buttons
        self._content_stack = QStackedWidget()

        self._nav_chat_btn     = QPushButton("Chat")
        self._nav_analysis_btn = QPushButton("Análise")
        self._nav_manage_btn   = QPushButton("Gerenciar")
        for idx, btn in enumerate((self._nav_chat_btn, self._nav_analysis_btn, self._nav_manage_btn)):
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, i=idx: self._switch_page(i))
            sb.addWidget(btn)
        self._nav_chat_btn.setChecked(True)

        # Sessions panel
        sb.addSpacing(8)
        self._add_sidebar_rule(sb)
        sb.addSpacing(4)

        sessions_header = QHBoxLayout()
        sessions_header.setContentsMargins(0, 0, 0, 0)
        sessions_lbl = QLabel("CONVERSAS")
        sessions_lbl.setObjectName("sidebarLabel")
        sessions_header.addWidget(sessions_lbl)
        sessions_header.addStretch()
        self._new_session_btn = QPushButton("+")
        self._new_session_btn.setFixedSize(22, 18)
        self._new_session_btn.setToolTip("Nova sessão")
        self._new_session_btn.clicked.connect(self._on_new_session)
        sessions_header.addWidget(self._new_session_btn)
        sb.addLayout(sessions_header)

        self._sessions_list = QListWidget()
        self._sessions_list.setObjectName("sessionsList")
        self._sessions_list.setMaximumHeight(110)
        self._sessions_list.itemClicked.connect(self._on_session_item_clicked)
        self._sessions_list.itemDoubleClicked.connect(self._on_session_double_clicked)
        self._sessions_list.itemChanged.connect(self._on_session_title_changed)
        self._sessions_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._sessions_list.customContextMenuRequested.connect(
            self._show_session_context_menu
        )
        sb.addWidget(self._sessions_list)

        sb.addSpacing(8)
        self._add_sidebar_rule(sb)
        sb.addSpacing(8)

        # Modo de recuperação
        lbl_mode = QLabel("Modo:")
        lbl_mode.setObjectName("sidebarLabel")
        sb.addWidget(lbl_mode)
        self.retrieval_combo = QComboBox()
        self.retrieval_combo.addItems(["Híbrido", "Multi-Query", "HyDE"])
        self.retrieval_combo.setCurrentIndex(0)
        self.retrieval_combo.setToolTip(
            "Híbrido: semântico + BM25 (padrão)\n"
            "Multi-Query: 3 reformulações da pergunta (+1 LLM call)\n"
            "HyDE: embeds resposta hipotética (melhor para perguntas abstractas)"
        )
        sb.addWidget(self.retrieval_combo)

        sb.addSpacing(10)

        # Filtro por arquivo
        self.file_filter_box = QGroupBox("Filtrar por arquivo")
        self.file_filter_box.setObjectName("sidebarGroup")
        self.file_filter_box.setCheckable(True)
        self.file_filter_box.setChecked(False)
        ff_layout = QVBoxLayout(self.file_filter_box)
        ff_layout.setContentsMargins(6, 6, 6, 6)
        ff_layout.setSpacing(4)

        ff_btn_row = QHBoxLayout()
        select_all_btn = QPushButton("Todos")
        select_all_btn.setFixedWidth(52)
        select_all_btn.clicked.connect(lambda: self._set_all_files_checked(True))
        select_none_btn = QPushButton("Nenhum")
        select_none_btn.setFixedWidth(52)
        select_none_btn.clicked.connect(lambda: self._set_all_files_checked(False))
        ff_btn_row.addWidget(select_all_btn)
        ff_btn_row.addWidget(select_none_btn)
        ff_btn_row.addStretch()
        ff_layout.addLayout(ff_btn_row)

        self.file_list_widget = QListWidget()
        self.file_list_widget.setMaximumHeight(96)
        self.file_list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        ff_layout.addWidget(self.file_list_widget)
        sb.addWidget(self.file_filter_box)

        sb.addSpacing(12)
        self._add_sidebar_rule(sb)
        sb.addSpacing(8)

        # Ações
        self.new_chat_btn = QPushButton("↺  Nova Conversa")
        self.new_chat_btn.setToolTip("Reseta o histórico da conversa actual")
        self.new_chat_btn.clicked.connect(self._reset_conversation)
        sb.addWidget(self.new_chat_btn)

        self.index_btn = QPushButton("⊞  Indexar tudo")
        self.index_btn.setEnabled(False)
        self.index_btn.clicked.connect(self.start_indexing)
        sb.addWidget(self.index_btn)

        self.resume_btn = QPushButton("↩  Retomar indexação")
        self.resume_btn.setObjectName("resumeBtn")
        self.resume_btn.setToolTip("Continua a indexação interrompida sem apagar o progresso")
        self.resume_btn.setVisible(False)
        self.resume_btn.clicked.connect(self.start_resume_indexing)
        sb.addWidget(self.resume_btn)

        self.config_btn = QPushButton("⚙  Configurar")
        self.config_btn.setEnabled(False)
        self.config_btn.clicked.connect(self.open_config)
        sb.addWidget(self.config_btn)

        # Badge + progresso + cancelar
        self.badge_label = QLabel()
        self.badge_label.setObjectName("badgeLabel")
        self.badge_label.setVisible(False)
        sb.addWidget(self.badge_label)

        self.progress_file_label = QLabel()
        self.progress_file_label.setObjectName("progressFileLabel")
        self.progress_file_label.setWordWrap(False)
        self.progress_file_label.setVisible(False)
        sb.addWidget(self.progress_file_label)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(4)
        progress_row.setContentsMargins(0, 0, 0, 0)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.cancel_btn = QPushButton("■")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setFixedSize(24, 24)
        self.cancel_btn.setToolTip("Interromper")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_worker)
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.cancel_btn)
        sb.addLayout(progress_row)

        self._bg_label = QLabel()
        self._bg_label.setObjectName("bgIndexLabel")
        self._bg_label.setWordWrap(True)
        self._bg_label.setVisible(False)
        sb.addWidget(self._bg_label)

        sb.addStretch()

        # Theme toggle
        self._theme_btn = QPushButton("☀  Modo Dia")
        self._theme_btn.setObjectName("navBtn")
        self._theme_btn.clicked.connect(self._toggle_theme)
        sb.addWidget(self._theme_btn)
        self._update_theme_btn_label()

        splitter.addWidget(sidebar)

        # ── Content stack ────────────────────────────────────────────
        self._build_page_chat()
        self._build_page_analysis()
        self._build_page_manage()

        splitter.addWidget(self._content_stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter)

    def _add_sidebar_rule(self, layout: QVBoxLayout) -> None:
        rule = QLabel()
        rule.setObjectName("sidebarRule")
        rule.setFixedHeight(1)
        layout.addWidget(rule)

    def _switch_page(self, index: int) -> None:
        self._content_stack.setCurrentIndex(index)
        for i, btn in enumerate((self._nav_chat_btn, self._nav_analysis_btn, self._nav_manage_btn)):
            btn.setChecked(i == index)

    def _build_page_chat(self) -> None:
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        # Resposta (streaming)
        self.similar_label = QLabel()
        self.similar_label.setObjectName("similarLabel")
        self.similar_label.setVisible(False)
        layout.addWidget(self.similar_label)

        self.answer_text = QTextEdit()
        self.answer_text.setObjectName("answerText")
        self.answer_text.setReadOnly(True)
        self.answer_text.setPlaceholderText("A resposta aparecerá aqui…")
        layout.addWidget(self.answer_text, 1)

        # Fontes
        sources_lbl = QLabel("Fontes:")
        sources_lbl.setObjectName("sectionLabel")
        layout.addWidget(sources_lbl)
        self.sources_text = QTextEdit()
        self.sources_text.setObjectName("sourcesText")
        self.sources_text.setReadOnly(True)
        self.sources_text.setMaximumHeight(130)
        layout.addWidget(self.sources_text)

        # Modo de consulta
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_lbl = QLabel("Modo:")
        mode_lbl.setObjectName("sectionLabel")
        mode_row.addWidget(mode_lbl)
        self.persona_combo = QComboBox()
        self.persona_combo.addItems([
            "Curador",
            "Socrático",
            "Resumido",
            "Comparação",
            "Podcaster",
            "Crítico",
        ])
        self.persona_combo.setToolTip(
            "Curador: resposta directa usando as fontes (padrão)\n"
            "Socrático: faz perguntas para guiar o raciocínio antes de responder\n"
            "Resumido: resposta curta, máximo 3 frases\n"
            "Comparação: semelhanças e diferenças em bullet points entre fontes\n"
            "Podcaster: tom conversacional e entusiasta\n"
            "Crítico: analisa argumentos, premissas e limitações"
        )
        mode_row.addWidget(self.persona_combo)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # Input
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.question_edit = QLineEdit()
        self.question_edit.setObjectName("questionInput")
        self.question_edit.setPlaceholderText("Pergunte à sua memória…")
        self.question_edit.returnPressed.connect(self.ask_question)
        self.ask_btn = QPushButton("Enviar")
        self.ask_btn.setObjectName("sendBtn")
        self.ask_btn.setEnabled(False)
        self.ask_btn.clicked.connect(self.ask_question)
        input_row.addWidget(self.question_edit, 1)
        input_row.addWidget(self.ask_btn)
        layout.addLayout(input_row)

        self._content_stack.addWidget(page)

    def _build_page_analysis(self) -> None:
        page = QWidget()
        page.setObjectName("contentPage")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        # Pill nav row
        pill_row = QHBoxLayout()
        pill_row.setSpacing(4)
        self._analysis_stack = QStackedWidget()

        def make_pill(label: str, idx: int) -> QPushButton:
            btn = QPushButton(label)
            btn.setObjectName("pillBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda: self._switch_analysis(idx))
            return btn

        self._pill_summary = make_pill("Resumo", 0)
        self._pill_faq     = make_pill("FAQ", 1)
        self._pill_guide   = make_pill("Guide", 2)
        self._pill_studio  = make_pill("Studio", 3)
        self._pill_summary.setChecked(True)
        for btn in (self._pill_summary, self._pill_faq, self._pill_guide, self._pill_studio):
            pill_row.addWidget(btn)
        pill_row.addStretch()
        outer.addLayout(pill_row)
        outer.addWidget(self._analysis_stack, 1)

        # ── Sub-página: Resumo ──────────────────────────────────────
        summary_page = QWidget()
        sl = QVBoxLayout(summary_page)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(8)
        self.summary_btn = QPushButton("Gerar resumo geral")
        self.summary_btn.setEnabled(False)
        self.summary_btn.clicked.connect(self.summarize)
        sl.addWidget(self.summary_btn)
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setPlaceholderText("Clique em 'Gerar resumo geral' para resumir a coleção indexada…")
        sl.addWidget(self.summary_text, 1)
        self._analysis_stack.addWidget(summary_page)

        # ── Sub-página: FAQ ─────────────────────────────────────────
        faq_page = QWidget()
        fl = QVBoxLayout(faq_page)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(8)
        self.faq_btn = QPushButton("Gerar FAQ")
        self.faq_btn.setEnabled(False)
        self.faq_btn.setToolTip("Gera perguntas frequentes com respostas a partir dos documentos indexados")
        self.faq_btn.clicked.connect(self._start_faq_generation)
        fl.addWidget(self.faq_btn)
        self.faq_text = QTextEdit()
        self.faq_text.setReadOnly(True)
        self.faq_text.setPlaceholderText("Clique em 'Gerar FAQ' para criar perguntas frequentes sobre os documentos indexados…")
        fl.addWidget(self.faq_text, 1)
        self._analysis_stack.addWidget(faq_page)

        # ── Sub-página: Guide ───────────────────────────────────────
        guide_page = QWidget()
        gl = QVBoxLayout(guide_page)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)

        lbl_gs = QLabel("Resumo da coleção:")
        lbl_gs.setObjectName("sectionLabel")
        gl.addWidget(lbl_gs)
        self.guide_summary_text = QTextEdit()
        self.guide_summary_text.setReadOnly(True)
        self.guide_summary_text.setMaximumHeight(100)
        self.guide_summary_text.setPlaceholderText("Indexe documentos para gerar o guide…")
        gl.addWidget(self.guide_summary_text)

        lbl_gq = QLabel("Perguntas sugeridas (duplo clique para perguntar):")
        lbl_gq.setObjectName("sectionLabel")
        gl.addWidget(lbl_gq)
        self.guide_questions_list = QListWidget()
        self.guide_questions_list.setMaximumHeight(120)
        self.guide_questions_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.guide_questions_list.itemDoubleClicked.connect(self._on_guide_question_clicked)
        gl.addWidget(self.guide_questions_list)

        lbl_gg = QLabel("Pérolas escondidas:")
        lbl_gg.setObjectName("sectionLabel")
        gl.addWidget(lbl_gg)
        self.guide_gems_text = QTextEdit()
        self.guide_gems_text.setReadOnly(True)
        self.guide_gems_text.setMaximumHeight(100)
        gl.addWidget(self.guide_gems_text)

        self.guide_refresh_btn = QPushButton("Atualizar Guide")
        self.guide_refresh_btn.setEnabled(False)
        self.guide_refresh_btn.setToolTip("Regenera o Notebook Guide para a coleção actual")
        self.guide_refresh_btn.clicked.connect(self._start_guide_generation)
        gl.addWidget(self.guide_refresh_btn)
        gl.addStretch()
        self._analysis_stack.addWidget(guide_page)

        # ── Sub-página: Studio Panel ────────────────────────────────
        studio_page = QWidget()
        stl = QVBoxLayout(studio_page)
        stl.setContentsMargins(0, 0, 0, 0)
        stl.setSpacing(8)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)
        self.studio_type_combo = QComboBox()
        self.studio_type_combo.addItems([
            "Briefing",
            "Relatório",
            "Guia de Estudo",
            "Índice de Temas",
            "Linha do Tempo",
            "Blog Post",
            "Mind Map",
            "Tabela de Dados",
            "Slides",
        ])
        self.studio_type_combo.setToolTip(
            "Briefing: sumário executivo com temas, achados e insights acionáveis\n"
            "Relatório: relatório multi-seção completo via Map-Reduce\n"
            "Guia de Estudo: conceitos-chave, termos e questões de revisão\n"
            "Índice de Temas: hierarquia de temas/subtemas dos documentos\n"
            "Linha do Tempo: eventos extraídos em ordem cronológica\n"
            "Blog Post: texto narrativo acessível sobre o conteúdo\n"
            "Mind Map: estrutura hierárquica em sintaxe Mermaid\n"
            "Tabela de Dados: extração de entidades em tabela estruturada\n"
            "Slides: apresentação em Markdown (Marp/reveal.js)"
        )
        self.studio_generate_btn = QPushButton("Gerar")
        self.studio_generate_btn.setObjectName("sendBtn")
        self.studio_generate_btn.setEnabled(False)
        self.studio_generate_btn.clicked.connect(self._start_studio_generation)
        ctrl_row.addWidget(self.studio_type_combo, 1)
        ctrl_row.addWidget(self.studio_generate_btn)
        stl.addLayout(ctrl_row)

        # Schema row — visível apenas para "Tabela de Dados"
        self._studio_schema_row = QHBoxLayout()
        schema_lbl = QLabel("Colunas:")
        schema_lbl.setObjectName("sectionLabel")
        self._studio_schema_row.addWidget(schema_lbl)
        self.studio_schema_edit = QLineEdit()
        self.studio_schema_edit.setPlaceholderText("ex: Nome, Data, Valor, Fonte")
        self.studio_schema_edit.setText("Nome, Descrição, Fonte")
        self._studio_schema_row.addWidget(self.studio_schema_edit, 1)
        self._studio_schema_widget = QWidget()
        self._studio_schema_widget.setLayout(self._studio_schema_row)
        self._studio_schema_widget.setVisible(False)
        stl.addWidget(self._studio_schema_widget)

        self.studio_result_text = QTextEdit()
        self.studio_result_text.setReadOnly(True)
        self.studio_result_text.setPlaceholderText(
            "Selecione o tipo de documento e clique em Gerar…"
        )
        stl.addWidget(self.studio_result_text, 1)

        # Tabela — visível apenas para "Tabela de Dados" após geração
        self.studio_table = QTableWidget()
        self.studio_table.setVisible(False)
        self.studio_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        stl.addWidget(self.studio_table, 1)

        export_row = QHBoxLayout()
        export_row.addStretch()
        self.studio_export_csv_btn = QPushButton("Exportar CSV")
        self.studio_export_csv_btn.setEnabled(False)
        self.studio_export_csv_btn.setVisible(False)
        self.studio_export_csv_btn.clicked.connect(self._studio_export_csv)
        export_row.addWidget(self.studio_export_csv_btn)
        self.studio_export_btn = QPushButton("Exportar .md")
        self.studio_export_btn.setEnabled(False)
        self.studio_export_btn.clicked.connect(self._studio_export_md)
        export_row.addWidget(self.studio_export_btn)
        stl.addLayout(export_row)

        self.studio_type_combo.currentTextChanged.connect(self._on_studio_type_changed)

        self._analysis_stack.addWidget(studio_page)

        self._content_stack.addWidget(page)

    def _switch_analysis(self, index: int) -> None:
        self._analysis_stack.setCurrentIndex(index)
        for i, btn in enumerate((self._pill_summary, self._pill_faq, self._pill_guide, self._pill_studio)):
            btn.setChecked(i == index)

    def _build_page_manage(self) -> None:
        tab = QWidget()
        tab.setObjectName("contentPage")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # ── Coleções ──────────────────────────────────────────────────────────
        colls_group = QGroupBox("Coleções")
        colls_layout = QVBoxLayout(colls_group)
        colls_layout.setSpacing(6)

        self.collections_table = QTableWidget(0, 4)
        self.collections_table.setHorizontalHeaderLabels(["Nome", "Tipo", "Caminho", "Estado"])
        self.collections_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.collections_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.collections_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.collections_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.collections_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.collections_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.collections_table.setMaximumHeight(160)
        colls_layout.addWidget(self.collections_table)

        colls_btns = QHBoxLayout()
        self.coll_activate_btn = QPushButton("Ativar")
        self.coll_activate_btn.setToolTip("Definir como coleção ativa")
        self.coll_activate_btn.setEnabled(False)
        self.coll_activate_btn.clicked.connect(self._on_coll_activate)
        self.coll_index_now_btn = QPushButton("Indexar agora")
        self.coll_index_now_btn.setEnabled(False)
        self.coll_index_now_btn.clicked.connect(self._on_coll_index_now)
        self.coll_remove_btn = QPushButton("Remover")
        self.coll_remove_btn.setEnabled(False)
        self.coll_remove_btn.clicked.connect(self._on_coll_remove)
        colls_btns.addWidget(self.coll_activate_btn)
        colls_btns.addWidget(self.coll_index_now_btn)
        colls_btns.addWidget(self.coll_remove_btn)
        colls_btns.addStretch()
        colls_layout.addLayout(colls_btns)

        self.collections_table.itemSelectionChanged.connect(self._on_coll_selection_changed)
        layout.addWidget(colls_group)

        # ── Coleção ativa ────────────────────────────────────────────────────
        info = QGroupBox("Coleção ativa")
        info_form = QFormLayout(info)
        self.manage_path_label = QLabel(self.config.watched_dir or "—")
        self.manage_path_label.setWordWrap(True)
        self.manage_watcher_label = QLabel("Inativo")
        self.manage_files_label = QLabel("—")
        self.manage_types_label = QLabel("—")
        self.manage_date_label = QLabel("—")
        info_form.addRow("Caminho:", self.manage_path_label)
        info_form.addRow("Watcher:", self.manage_watcher_label)
        info_form.addRow("Arquivos:", self.manage_files_label)
        info_form.addRow("Tipos:", self.manage_types_label)
        info_form.addRow("Última indexação:", self.manage_date_label)
        layout.addWidget(info)

        actions = QHBoxLayout()
        self.refresh_manage_btn = QPushButton("Atualizar informações")
        self.refresh_manage_btn.clicked.connect(self.refresh_manage_info)
        self.update_index_btn = QPushButton("Atualizar índice")
        self.update_index_btn.setEnabled(False)
        self.update_index_btn.setToolTip("Indexa apenas arquivos novos ou modificados")
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

        self._content_stack.addWidget(tab)

    def _refresh_collections_table(self) -> None:
        """Preenche a tabela de coleções com o estado actual do config."""
        self.collections_table.setRowCount(0)
        for coll in self.config.collections:
            row = self.collections_table.rowCount()
            self.collections_table.insertRow(row)

            active_mark = " ★" if coll.name == self.config.active_collection else ""
            name_item = QTableWidgetItem(coll.name + active_mark)
            type_item = QTableWidgetItem(
                "🔮 Vault" if coll.type.value == "vault" else "📚 Biblioteca"
            )
            path_item = QTableWidgetItem(coll.path)
            path_item.setToolTip(coll.path)

            indexed = os.path.isdir(coll.persist_dir) if coll.persist_dir else False
            state_item = QTableWidgetItem("✔ indexada" if indexed else "— sem índice")

            for col, item in enumerate((name_item, type_item, path_item, state_item)):
                item.setData(Qt.ItemDataRole.UserRole, coll.name)
                self.collections_table.setItem(row, col, item)

        self._on_coll_selection_changed()

    def _on_coll_selection_changed(self) -> None:
        has_sel = bool(self.collections_table.selectedItems())
        self.coll_activate_btn.setEnabled(has_sel)
        self.coll_index_now_btn.setEnabled(has_sel)
        # Não permitir remover a última coleção user-defined
        user_count = sum(1 for c in self.config.collections if c.source == "user")
        sel_name = self._selected_coll_name()
        sel_coll = next((c for c in self.config.collections if c.name == sel_name), None)
        can_remove = has_sel and sel_coll is not None and not (
            sel_coll.source == "user" and user_count <= 1
        )
        self.coll_remove_btn.setEnabled(can_remove)

    def _selected_coll_name(self) -> str:
        items = self.collections_table.selectedItems()
        if not items:
            return ""
        return items[0].data(Qt.ItemDataRole.UserRole) or ""

    def _on_coll_activate(self) -> None:
        name = self._selected_coll_name()
        if not name or name == self.config.active_collection:
            return
        self.config.active_collection = name
        save_config(self.config)
        self.vectorstore = None
        self._disable_query_buttons()
        self._post_config_init()
        self._reset_conversation()
        self._log_event(f"Coleção ativada: {name}")

    def _on_coll_index_now(self) -> None:
        name = self._selected_coll_name()
        if not name:
            return
        if name != self.config.active_collection:
            self.config.active_collection = name
            save_config(self.config)
            self._populate_collection_combo()
            self._post_config_init()
        self._switch_page(0)
        self.start_indexing()

    def _on_coll_remove(self) -> None:
        name = self._selected_coll_name()
        if not name:
            return
        reply = QMessageBox.question(
            self,
            "Confirmar remoção",
            f"Remover a coleção '{name}' da lista?\n\n"
            "O vectorstore no disco não será apagado.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        was_active = name == self.config.active_collection
        self.config.collections = [c for c in self.config.collections if c.name != name]
        if was_active:
            enabled = [c for c in self.config.collections if c.enabled]
            self.config.active_collection = enabled[0].name if enabled else ""
        save_config(self.config)
        self._populate_collection_combo()
        self._post_config_init()
        self._log_event(f"Coleção removida: {name}")

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
            folder, llm, embed, eco_enabled, reranking = dialog.get_values()
            if not folder:
                QMessageBox.warning(self, "Aviso", "Selecione uma pasta para continuar.")
                return
            self._apply_setup_values(folder, llm, embed, eco_enabled, reranking)
            self._post_config_init()
        else:
            self.statusBar().showMessage("Configuração cancelada.")

    def open_config(self) -> None:
        dialog = SetupDialog(self._available_models, self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            folder, llm, embed, eco_enabled, reranking = dialog.get_values()
            if not folder:
                return
            changed_dir = folder != self.config.watched_dir
            self._apply_setup_values(folder, llm, embed, eco_enabled, reranking)
            self.folder_label.setText(self.config.watched_dir)
            self.manage_path_label.setText(self.config.watched_dir)
            if changed_dir:
                self.vectorstore = None
                self._disable_query_buttons()
            self._log_event("Configuração atualizada.")
            self._post_config_init()

    def _apply_setup_values(
        self, folder: str, llm: str, embed: str, eco_enabled: dict[str, bool],
        reranking_enabled: bool = True,
    ) -> None:
        """Aplica os valores do SetupDialog ao config e guarda."""
        from core.collections import CollectionConfig, CollectionType

        self.config.llm_model = llm
        self.config.embed_model = embed
        self.config.ecosystem_enabled.update(eco_enabled)
        self.config.reranking_enabled = reranking_enabled

        # Atualiza ou cria a coleção Biblioteca do utilizador
        user_colls = [c for c in self.config.collections if c.source == "user"]
        if user_colls:
            user_colls[0].path = folder
            if not self.config.active_collection:
                self.config.active_collection = user_colls[0].name
        else:
            coll = CollectionConfig(
                name="Biblioteca",
                path=folder,
                type=CollectionType.LIBRARY,
                source="user",
            )
            self.config.collections.insert(0, coll)
            self.config.active_collection = coll.name

        save_config(self.config)
        self._populate_collection_combo()

    def _populate_collection_combo(self) -> None:
        """Preenche o QComboBox de coleções com as coleções habilitadas."""
        self.collection_combo.blockSignals(True)
        self.collection_combo.clear()
        for coll in self.config.collections:
            if not coll.enabled:
                continue
            icon = "🔮" if coll.type.value == "vault" else "📚"
            self.collection_combo.addItem(f"{icon} {coll.name}", userData=coll.name)
        # Selecionar a coleção ativa
        active = self.config.active_collection
        if active:
            idx = self.collection_combo.findData(active)
            if idx >= 0:
                self.collection_combo.setCurrentIndex(idx)
        self.collection_combo.blockSignals(False)

    def _on_collection_changed(self, index: int) -> None:
        """Troca a coleção ativa, recarrega o vectorstore e reseta o chat."""
        if index < 0:
            return
        name = self.collection_combo.itemData(index)
        if not name or name == self.config.active_collection:
            return
        self.config.active_collection = name
        save_config(self.config)
        self.vectorstore = None
        self._disable_query_buttons()
        self._post_config_init()
        self._reset_conversation()
        self._log_event(f"Coleção ativa: {name}")

    def _post_config_init(self) -> None:
        """Chamado após configuração válida estar disponível."""
        self._populate_collection_combo()
        self.folder_label.setText(self.config.watched_dir or "Pasta não configurada")
        self.manage_path_label.setText(self.config.watched_dir or "—")

        if self.config.mnemosyne_dir:
            self._collection_index = CollectionIndex(self.config.mnemosyne_dir)
            self._file_tracker = FileTracker(self.config.mnemosyne_dir)
            self._memory_store = MemoryStore(self.config.mnemosyne_dir)
            self._session_manager = SessionManager(self.config.mnemosyne_dir)
            sessions = self._session_manager.list_sessions()
            if not sessions:
                self._current_session = self._session_manager.new_session()
            else:
                self._current_session = sessions[0]
            self._chat_history = self._session_manager.load_turns(self._current_session.id)
            self._refresh_sessions_list()

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
        self._check_resume_available()
        self._refresh_collections_table()
        self.refresh_manage_info()

        if self.config.auto_index_on_change:
            self._start_watcher()

        if self.config.background_index_enabled:
            self._start_idle_indexer()

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

    # ── Indexador idle (ecossistema) ──────────────────────────────────────────

    def _start_idle_indexer(self) -> None:
        from core.idle_indexer import IdleIndexer

        existing: IdleIndexer | None = getattr(self, "_idle_indexer", None)
        if existing is not None:
            existing.stop()

        def _is_busy() -> bool:
            for attr in ("_index_worker", "_resume_worker", "_update_worker", "_file_worker"):
                w = getattr(self, attr, None)
                if w is not None and w.isRunning():
                    return True
            return False

        self._idle_indexer = IdleIndexer(self)
        self._idle_indexer.queue_size_changed.connect(self._on_bg_queue_size_changed)
        self._idle_indexer.file_indexed.connect(self._on_bg_file_indexed)
        self._idle_indexer.setup(self.config, _is_busy)

    def _on_bg_queue_size_changed(self, size: int) -> None:
        if size > 0:
            self._bg_label.setText(f"⟳ Indexando {size} arquivo(s) do ecossistema…")
            self._bg_label.setVisible(True)
        else:
            self._bg_label.setVisible(False)

    def _on_bg_file_indexed(self, file_path: str, coll_name: str, success: bool, msg: str) -> None:
        name = os.path.basename(file_path)
        if success:
            self._log_event(f"[{coll_name}] Indexado: {name}")
        else:
            self._log_event(f"[{coll_name}] Erro ao indexar {name}: {msg}")

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
        self.progress_file_label.setText("Iniciando…")
        self.progress_file_label.setVisible(True)
        self.cancel_btn.setVisible(True)
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
        self.progress_file_label.setText("Verificando arquivos…")
        self.progress_file_label.setVisible(True)
        self.cancel_btn.setVisible(True)
        self.statusBar().showMessage("Actualizando índice incrementalmente…")
        self._log_event("Iniciando actualização incremental do índice.")

        self._update_worker = UpdateIndexWorker(self.config)
        self._update_worker.finished.connect(self._on_update_index_finished)
        self._update_worker.start()

    def _on_update_index_finished(self, success: bool, message: str) -> None:
        self.progress.setVisible(False)
        self.progress_file_label.setVisible(False)
        self.cancel_btn.setVisible(False)
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

    @staticmethod
    def _elide_middle(text: str, max_chars: int = 26) -> str:
        if len(text) <= max_chars:
            return text
        half = (max_chars - 1) // 2
        return text[:half] + "…" + text[-(max_chars - half - 1):]

    def _on_index_progress(self, name: str, pos: int, total: int) -> None:
        elided = self._elide_middle(name)
        self.progress_file_label.setText(f"{elided}  ({pos}/{total})")
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(pos)
        self.statusBar().showMessage(f"Indexando {name}… ({pos}/{total})")

    def _on_index_finished(self, success: bool, message: str) -> None:
        self.index_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.progress_file_label.setVisible(False)
        self.cancel_btn.setVisible(False)
        self._log_event(message)
        self._check_resume_available()

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
            self._log_event("Indexação interrompida — clique 'Retomar indexação' para continuar.")

        self.statusBar().showMessage(message)

    def _check_resume_available(self) -> None:
        """Mostra o botão 'Retomar' se há checkpoint de indexação interrompida."""
        mnemosyne_dir = self.config.mnemosyne_dir if self.config else ""
        persist_dir   = self.config.persist_dir   if self.config else ""
        can_resume = bool(
            mnemosyne_dir
            and persist_dir
            and os.path.exists(persist_dir)
            and IndexCheckpoint.exists(mnemosyne_dir)
        )
        self.resume_btn.setVisible(can_resume)

    def start_resume_indexing(self) -> None:
        if not self.config or not self.config.watched_dir:
            return
        self.resume_btn.setVisible(False)
        self.index_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.progress_file_label.setText("Retomando indexação…")
        self.progress_file_label.setVisible(True)
        self.cancel_btn.setVisible(True)
        self.statusBar().showMessage("Retomando indexação interrompida…")
        self._log_event("Retomando indexação interrompida.")

        self._resume_worker = ResumeIndexWorker(self.config)
        self._resume_worker.finished.connect(self._on_resume_finished)
        self._resume_worker.progress.connect(self._on_index_progress)
        self._resume_worker.start()

    def _on_resume_finished(self, success: bool, message: str) -> None:
        self.index_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.progress_file_label.setVisible(False)
        self.cancel_btn.setVisible(False)
        self._log_event(message)
        self._check_resume_available()

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
            self._log_event("Retomada interrompida — clique 'Retomar indexação' para continuar.")

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
        """Popula o campo de pergunta e muda para a página Chat."""
        self.question_edit.setText(item.text())
        self._switch_page(0)

    # ── Studio Panel ──────────────────────────────────────────────────────────

    def _on_studio_type_changed(self, doc_type: str) -> None:
        is_table = doc_type == "Tabela de Dados"
        self._studio_schema_widget.setVisible(is_table)
        self.studio_table.setVisible(False)
        self.studio_result_text.setVisible(not is_table)
        self.studio_export_csv_btn.setVisible(is_table)

    def _start_studio_generation(self) -> None:
        if self.vectorstore is None:
            return
        doc_type = self.studio_type_combo.currentText()
        self.studio_generate_btn.setEnabled(False)
        self.studio_export_btn.setEnabled(False)
        self.studio_export_csv_btn.setEnabled(False)
        self.studio_result_text.setPlainText("")
        self.studio_table.setVisible(False)
        self._studio_raw = ""
        self.statusBar().showMessage(f"Gerando {doc_type}…")

        extra: dict = {}
        if doc_type == "Tabela de Dados":
            schema = self.studio_schema_edit.text().strip()
            if schema:
                extra["schema"] = schema

        self._studio_worker = StudioWorker(self.vectorstore, self.config, doc_type, extra)
        self._studio_worker.token.connect(self._on_studio_token)
        self._studio_worker.finished.connect(self._on_studio_finished)
        self._studio_worker.start()

    def _on_studio_token(self, chunk: str) -> None:
        self._studio_raw += chunk
        self.studio_result_text.setPlainText(self._studio_raw)
        sb = self.studio_result_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_studio_finished(self, success: bool, text: str) -> None:
        self.studio_generate_btn.setEnabled(self.vectorstore is not None)
        doc_type = self.studio_type_combo.currentText()
        if success:
            if doc_type == "Tabela de Dados":
                self.studio_result_text.setVisible(False)
                self._studio_populate_table(text)
                self.studio_export_csv_btn.setEnabled(True)
            else:
                self.studio_result_text.setPlainText(text)
            self.studio_export_btn.setEnabled(bool(text))
            self.statusBar().showMessage("Documento gerado.")
        else:
            self.studio_result_text.setVisible(True)
            self.studio_result_text.setPlainText(f"Erro: {text}")
            self.statusBar().showMessage("Erro ao gerar documento.")

    def _studio_populate_table(self, markdown_table: str) -> None:
        """Parseia tabela Markdown e preenche o QTableWidget."""
        lines = [
            ln.strip() for ln in markdown_table.splitlines()
            if ln.strip().startswith("|") and "---" not in ln
        ]
        if not lines:
            self.studio_result_text.setVisible(True)
            self.studio_result_text.setPlainText(markdown_table)
            return

        def parse_row(line: str) -> list[str]:
            return [cell.strip() for cell in line.strip("|").split("|")]

        headers = parse_row(lines[0])
        rows = [parse_row(ln) for ln in lines[1:]]

        self.studio_table.clear()
        self.studio_table.setColumnCount(len(headers))
        self.studio_table.setRowCount(len(rows))
        self.studio_table.setHorizontalHeaderLabels(headers)
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                if c < len(headers):
                    self.studio_table.setItem(r, c, QTableWidgetItem(cell))
        self.studio_table.setVisible(True)
        self._studio_table_data = (headers, rows)

    def _studio_export_md(self) -> None:
        text = self.studio_result_text.toPlainText()
        if not text:
            return
        doc_type = self.studio_type_combo.currentText()
        default_name = doc_type.lower().replace(" ", "_") + ".md"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar como Markdown", default_name, "Markdown (*.md)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                self.statusBar().showMessage(f"Exportado: {path}")
            except OSError as exc:
                QMessageBox.warning(self, "Erro ao exportar", str(exc))

    def _studio_export_csv(self) -> None:
        data = getattr(self, "_studio_table_data", None)
        if not data:
            return
        headers, rows = data
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar como CSV", "tabela.csv", "CSV (*.csv)"
        )
        if path:
            try:
                import csv
                with open(path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    writer.writerows(rows)
                self.statusBar().showMessage(f"CSV exportado: {path}")
            except OSError as exc:
                QMessageBox.warning(self, "Erro ao exportar", str(exc))

    # ── Seleção de arquivos ───────────────────────────────────────────────────

    def _populate_file_list(self) -> None:
        """Popula a lista de arquivos com checkboxes na aba Perguntar."""
        self.file_list_widget.clear()
        supported = {".pdf", ".docx", ".txt", ".md", ".epub"}
        ignore_dirs = {".mnemosyne", ".obsidian", "templates", "attachments", ".trash"}
        paths: list[str] = []

        if self.config.watched_dir and os.path.isdir(self.config.watched_dir):
            for root, dirs, files in os.walk(self.config.watched_dir):
                dirs[:] = [d for d in dirs if d not in ignore_dirs]
                for f in sorted(files):
                    _, ext = os.path.splitext(f.lower())
                    if ext in supported:
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

        # Auto-título: primeira pergunta da sessão vira o título
        if (
            self._current_session
            and self._session_manager
            and self._current_session.title == "Nova conversa"
            and not self._chat_history
        ):
            auto_title = question[:60]
            self._session_manager.rename_session(self._current_session.id, auto_title)
            self._current_session.title = auto_title
            self._refresh_sessions_list()

        # Persistir turno do utilizador
        if self._current_session and self._session_manager:
            self._session_manager.append_turn(
                self._current_session.id, Turn(role="user", content=question)
            )

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

        retrieval_map = {"Híbrido": "hybrid", "Multi-Query": "multi_query", "HyDE": "hyde"}
        retrieval_mode = retrieval_map.get(self.retrieval_combo.currentText(), "hybrid")

        persona_map = {
            "Curador": "curador",
            "Socrático": "socrático",
            "Resumido": "resumido",
            "Comparação": "comparação",
            "Podcaster": "podcaster",
            "Crítico": "crítico",
        }
        persona = persona_map.get(self.persona_combo.currentText(), "curador")

        source_files = self._get_selected_files()
        collection_type = self.config.collection_type

        self._ask_worker = AskWorker(
            self.vectorstore, question, self.config,
            self._chat_history, None, retrieval_mode,
            self._file_tracker, persona=persona, source_files=source_files,
            collection_type=collection_type,
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
            # Persistir turno do assistente
            if self._current_session and self._session_manager:
                self._session_manager.append_turn(
                    self._current_session.id,
                    Turn(role="assistant", content=text, sources=[s["path"] for s in sources]),
                )
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

    # ── Sessões de chat ───────────────────────────────────────────────────────

    def _refresh_sessions_list(self) -> None:
        if not hasattr(self, "_sessions_list") or self._session_manager is None:
            return
        self._updating_sessions = True
        self._sessions_list.clear()
        for session in self._session_manager.list_sessions():
            label = session.title[:32] if len(session.title) <= 32 else session.title[:29] + "…"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, session.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            try:
                from datetime import datetime as _dt
                dt = _dt.fromisoformat(session.updated_at)
                date_str = dt.strftime("%d/%m %H:%M")
            except ValueError:
                date_str = session.updated_at[:16]
            item.setToolTip(f"{session.title}\n{date_str}")
            self._sessions_list.addItem(item)
            if self._current_session and session.id == self._current_session.id:
                self._sessions_list.setCurrentItem(item)
        self._updating_sessions = False

    def _on_new_session(self) -> None:
        if self._session_manager is None:
            return
        self._current_session = self._session_manager.new_session()
        self._chat_history = []
        self._session_memory.clear()
        self.answer_text.clear()
        self.sources_text.clear()
        self.similar_label.setVisible(False)
        self.question_edit.clear()
        self._refresh_sessions_list()
        self._log_event("Nova sessão iniciada.")

    def _load_session(self, session: ChatSession) -> None:
        if self._session_manager is None:
            return
        self._current_session = session
        turns = self._session_manager.load_turns(session.id)
        self._chat_history = turns
        self._session_memory.clear()
        i = 0
        while i < len(turns) - 1:
            if turns[i].role == "user" and turns[i + 1].role == "assistant":
                self._session_memory.save_query(
                    turns[i].content, turns[i + 1].content, turns[i + 1].sources
                )
                i += 2
            else:
                i += 1
        self.answer_text.clear()
        self.sources_text.clear()
        self.similar_label.setVisible(False)
        self.question_edit.clear()
        for turn in reversed(turns):
            if turn.role == "assistant":
                self.answer_text.setPlainText(turn.content)
                break
        self._log_event(f'Sessão carregada: "{session.title}"')

    def _on_session_item_clicked(self, item: QListWidgetItem) -> None:
        if self._updating_sessions:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if session_id and self._session_manager:
            session = self._session_manager.get_session(session_id)
            if session and (
                self._current_session is None or session.id != self._current_session.id
            ):
                self._load_session(session)

    def _on_session_double_clicked(self, item: QListWidgetItem) -> None:
        self._sessions_list.editItem(item)

    def _on_session_title_changed(self, item: QListWidgetItem) -> None:
        if self._updating_sessions:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if session_id and self._session_manager:
            new_title = item.text().strip() or "Nova conversa"
            self._session_manager.rename_session(session_id, new_title)
            if self._current_session and self._current_session.id == session_id:
                self._current_session.title = new_title

    def _show_session_context_menu(self, pos: object) -> None:
        item = self._sessions_list.itemAt(pos)  # type: ignore[arg-type]
        if item is None:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if not session_id:
            return
        menu = QMenu(self)
        rename_action = menu.addAction("Renomear")
        delete_action = menu.addAction("Excluir")
        action = menu.exec(self._sessions_list.mapToGlobal(pos))  # type: ignore[arg-type]
        if action == rename_action:
            self._sessions_list.editItem(item)
        elif action == delete_action:
            self._delete_session(session_id)

    def _delete_session(self, session_id: str) -> None:
        if self._session_manager is None:
            return
        remaining = [
            s for s in self._session_manager.list_sessions() if s.id != session_id
        ]
        is_current = self._current_session and self._current_session.id == session_id
        self._session_manager.delete_session(session_id)
        if is_current:
            if remaining:
                self._current_session = remaining[0]
                self._chat_history = self._session_manager.load_turns(
                    self._current_session.id
                )
            else:
                self._current_session = self._session_manager.new_session()
                self._chat_history = []
            self.answer_text.clear()
            self.sources_text.clear()
            self.question_edit.clear()
        self._refresh_sessions_list()

    def _reset_conversation(self) -> None:
        self._on_new_session()

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
        idle: object = getattr(self, "_idle_indexer", None)
        if idle is not None:
            idle.stop()  # type: ignore[union-attr]

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
            # Turnos já persistidos incrementalmente; passar para compactação
            turns_to_compact = self._chat_history or []
            self._compact_worker = CompactMemoryWorker(
                self._memory_store, self.config.llm_model, turns_to_compact
            )
            self.statusBar().showMessage("A guardar memória…")
            self._compact_worker.start()
            # Aguarda no máximo 15 s para não bloquear indefinidamente
            self._compact_worker.wait(15_000)

        event.accept()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _cancel_worker(self) -> None:
        for attr in ("_index_worker", "_resume_worker", "_ask_worker", "_summary_worker"):
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
        self.studio_generate_btn.setEnabled(True)

    def _disable_query_buttons(self) -> None:
        self.ask_btn.setEnabled(False)
        self.summary_btn.setEnabled(False)
        self.faq_btn.setEnabled(False)
        self.update_index_btn.setEnabled(False)
        self.guide_refresh_btn.setEnabled(False)
        self.studio_generate_btn.setEnabled(False)

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

    def _update_theme_btn_label(self) -> None:
        if not hasattr(self, "_theme_btn"):
            return
        if self.config.dark_mode:
            self._theme_btn.setText("☀  Modo Dia")
        else:
            self._theme_btn.setText("☽  Modo Noite")

    def _toggle_theme(self) -> None:
        self.config.dark_mode = not self.config.dark_mode
        save_config(self.config)
        self._update_theme_btn_label()
        self.apply_style()

    def apply_style(self) -> None:
        self._load_fonts()
        qss_file = "styles.qss" if self.config.dark_mode else "styles_light.qss"
        style_path = os.path.join(os.path.dirname(__file__), qss_file)
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
