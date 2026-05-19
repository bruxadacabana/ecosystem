"""Painel de configurações do KOSMOS."""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

if TYPE_CHECKING:
    from app.core.feed_manager import FeedManager
    from app.theme.theme_manager import ThemeManager
    from app.utils.config import Config

log = logging.getLogger("kosmos.ui.settings")


class _OllamaCheckWorker(QThread):
    """Verifica disponibilidade do Ollama em background (não bloqueia a UI)."""

    result = pyqtSignal(bool, str)  # (available, active_model_name)

    def __init__(self, endpoint: str, model: str) -> None:
        super().__init__()
        self._endpoint = endpoint
        self._model    = model

    def run(self) -> None:
        from app.core.ai_bridge import AiBridge
        bridge = AiBridge(endpoint=self._endpoint)
        self.result.emit(bridge.is_available(), self._model)


# Opções dos combos
_UPDATE_OPTIONS  = [("15 minutos", 15), ("30 minutos", 30),
                    ("1 hora", 60),     ("2 horas", 120), ("Manual", 0)]
_PURGE_READ      = [("15 dias", 15), ("30 dias", 30), ("60 dias", 60),
                    ("90 dias", 90), ("Nunca", 0)]
_PURGE_UNREAD    = [("30 dias", 30), ("60 dias", 60), ("90 dias", 90),
                    ("180 dias", 180), ("Nunca", 0)]
_FONT_SIZES      = [14, 16, 18, 20, 22, 24]
_DEV_DATE_LIMIT  = [("Sem limite", 0), ("Últimas 24h", 1), ("Últimos 3 dias", 3),
                    ("Últimos 7 dias", 7), ("Últimos 14 dias", 14),
                    ("Últimos 30 dias", 30)]


class SettingsView(QWidget):
    """View de configurações com seções: Aparência, Feeds, Reddit, Avançado.

    Sinais:
        theme_changed(str)   — tema foi alterado ('day' | 'night').
        feeds_refreshed()    — novo feed adicionado via discovery (sidebar precisa atualizar).
    """

    theme_changed   = pyqtSignal(str)
    feeds_refreshed = pyqtSignal()

    def __init__(
        self,
        config:        "Config",
        theme_manager: "ThemeManager",
        feed_manager:  "FeedManager",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cfg   = config
        self._theme = theme_manager
        self._fm    = feed_manager
        self.setObjectName("settingsView")
        self._build_ui()

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("listSeparator")
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setObjectName("settingsContent")
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(28, 20, 28, 28)
        self._content_layout.setSpacing(20)

        self._content_layout.addWidget(self._section_appearance())
        self._content_layout.addWidget(self._section_feeds())
        self._content_layout.addWidget(self._section_filters())
        self._content_layout.addWidget(self._section_ai())
        self._content_layout.addWidget(self._section_reddit())
        self._content_layout.addWidget(self._section_advanced())
        self._content_layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def _build_header(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("feedListHeader")
        widget.setFixedHeight(52)

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel("⚙  Configurações")
        title.setObjectName("feedListTitle")
        f = QFont("Special Elite")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(16)
        title.setFont(f)
        layout.addWidget(title)

        return widget

    # ------------------------------------------------------------------
    # Seção: Aparência
    # ------------------------------------------------------------------

    def _section_appearance(self) -> QGroupBox:
        box = QGroupBox("APARÊNCIA")
        box.setFont(self._mono(10))
        layout = QVBoxLayout(box)
        layout.setSpacing(14)

        # Tema
        row = QHBoxLayout()
        row.addWidget(self._label("Tema:"))
        self._theme_btn = QPushButton()
        self._theme_btn.setFont(self._mono(11))
        self._theme_btn.setFixedWidth(160)
        self._theme_btn.clicked.connect(self._on_toggle_theme)
        row.addWidget(self._theme_btn)
        row.addStretch()
        layout.addLayout(row)

        # Fonte do leitor
        row2 = QHBoxLayout()
        row2.addWidget(self._label("Fonte no leitor:"))
        self._font_slider = QSlider(Qt.Orientation.Horizontal)
        self._font_slider.setMinimum(0)
        self._font_slider.setMaximum(len(_FONT_SIZES) - 1)
        self._font_slider.setFixedWidth(160)
        self._font_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._font_slider.setTickInterval(1)
        self._font_slider.valueChanged.connect(self._on_font_size_changed)
        row2.addWidget(self._font_slider)
        self._font_size_lbl = QLabel("")
        self._font_size_lbl.setObjectName("cardMeta")
        self._font_size_lbl.setFont(self._mono(10))
        self._font_size_lbl.setFixedWidth(40)
        row2.addWidget(self._font_size_lbl)
        row2.addStretch()
        layout.addLayout(row2)

        # Idioma de exibição dos títulos (tradução dos cards)
        row3 = QHBoxLayout()
        row3.addWidget(self._label("Idioma dos cards:"))
        self._display_lang_combo = QComboBox()
        self._display_lang_combo.setFont(self._mono(11))
        self._display_lang_combo.setFixedWidth(200)
        self._display_lang_combo.addItem("Original (sem tradução)", "")
        from app.core.translator import TARGET_LANGUAGE_NAMES
        for code, name in TARGET_LANGUAGE_NAMES.items():
            self._display_lang_combo.addItem(name, code)
        current_lang = self._cfg.get("display_language", "")
        for i in range(self._display_lang_combo.count()):
            if self._display_lang_combo.itemData(i) == current_lang:
                self._display_lang_combo.setCurrentIndex(i)
                break
        self._display_lang_combo.currentIndexChanged.connect(self._on_display_lang_changed)
        row3.addWidget(self._display_lang_combo)
        row3.addStretch()
        layout.addLayout(row3)

        self._refresh_appearance_widgets()
        return box

    # ------------------------------------------------------------------
    # Seção: Feeds
    # ------------------------------------------------------------------

    def _section_feeds(self) -> QGroupBox:
        box = QGroupBox("FEEDS")
        box.setFont(self._mono(10))
        layout = QVBoxLayout(box)
        layout.setSpacing(14)

        # Intervalo de atualização
        row = QHBoxLayout()
        row.addWidget(self._label("Atualizar a cada:"))
        self._interval_combo = self._combo(_UPDATE_OPTIONS, "update_interval_minutes", 30)
        row.addWidget(self._interval_combo)
        row.addStretch()
        layout.addLayout(row)

        # Purgar lidos
        row2 = QHBoxLayout()
        row2.addWidget(self._label("Purgar lidos após:"))
        self._purge_read_combo = self._combo(_PURGE_READ, "purge_read_days", 30)
        row2.addWidget(self._purge_read_combo)
        row2.addStretch()
        layout.addLayout(row2)

        # Purgar não lidos
        row3 = QHBoxLayout()
        row3.addWidget(self._label("Purgar não lidos após:"))
        self._purge_unread_combo = self._combo(_PURGE_UNREAD, "purge_unread_days", 90)
        row3.addWidget(self._purge_unread_combo)
        row3.addStretch()
        layout.addLayout(row3)

        # Scraping automático
        self._scrape_check = QCheckBox("Scraping automático ao abrir artigos truncados")
        self._scrape_check.setFont(self._mono(12))
        val = self._cfg.get("auto_scrape", False)
        self._scrape_check.setChecked(bool(val))
        self._scrape_check.stateChanged.connect(
            lambda s: self._cfg.set("auto_scrape", s == Qt.CheckState.Checked.value)
        )
        layout.addWidget(self._scrape_check)

        # Limite de data (desenvolvimento)
        row4 = QHBoxLayout()
        row4.addWidget(self._label("Limitar artigos a:"))
        self._date_limit_combo = self._combo(_DEV_DATE_LIMIT, "dev_article_age_days", 0)
        row4.addWidget(self._date_limit_combo)
        dev_note = QLabel("(desenvolvimento)")
        dev_note.setObjectName("cardMeta")
        dev_note.setFont(self._mono(10))
        row4.addWidget(dev_note)
        row4.addStretch()
        layout.addLayout(row4)

        return box

    # ------------------------------------------------------------------
    # Seção: Filtros de conteúdo
    # ------------------------------------------------------------------

    def _section_filters(self) -> QGroupBox:
        box = QGroupBox("FILTROS DE CONTEÚDO")
        box.setFont(self._mono(10))
        layout = QVBoxLayout(box)
        layout.setSpacing(10)

        note = QLabel(
            "Artigos cujo título contenha qualquer um destes termos serão ocultados.\n"
            "Um termo por linha. Não diferencia maiúsculas de minúsculas."
        )
        note.setObjectName("cardMeta")
        note.setFont(self._mono(10))
        note.setWordWrap(True)
        layout.addWidget(note)

        self._blocklist_edit = QPlainTextEdit()
        self._blocklist_edit.setFont(self._mono(12))
        self._blocklist_edit.setFixedHeight(110)
        self._blocklist_edit.setPlaceholderText("publicidade\nclick bait\npatrocinado")
        current = self._cfg.get("keyword_blocklist", [])
        self._blocklist_edit.setPlainText("\n".join(current))
        layout.addWidget(self._blocklist_edit)

        save_row = QHBoxLayout()
        save_btn = QPushButton("Salvar filtros")
        save_btn.setFont(self._mono(11))
        save_btn.clicked.connect(self._on_save_blocklist)
        save_row.addWidget(save_btn)
        self._blocklist_status = QLabel("")
        self._blocklist_status.setObjectName("dialogStatusLabel")
        self._blocklist_status.setFont(self._mono(10))
        save_row.addWidget(self._blocklist_status)
        save_row.addStretch()
        layout.addLayout(save_row)

        return box

    # ------------------------------------------------------------------
    # Seção: IA local (Ollama)
    # ------------------------------------------------------------------

    def _section_ai(self) -> QGroupBox:
        box = QGroupBox("INTELIGÊNCIA ARTIFICIAL  (OLLAMA)")
        box.setFont(self._mono(10))
        layout = QVBoxLayout(box)
        layout.setSpacing(12)

        # Label de status persistente da conexão com Ollama
        self._ollama_conn_lbl = QLabel("○  verificando…")
        self._ollama_conn_lbl.setObjectName("ollamaUnknown")
        self._ollama_conn_lbl.setFont(self._mono(11))
        layout.addWidget(self._ollama_conn_lbl)

        self._ai_enable = QCheckBox("Habilitar IA local  (requer Ollama rodando)")
        self._ai_enable.setFont(self._mono(12))
        self._ai_enable.setChecked(bool(self._cfg.get("ai_enabled", False)))
        self._ai_enable.stateChanged.connect(
            lambda s: self._cfg.set("ai_enabled", s == Qt.CheckState.Checked.value)
        )
        layout.addWidget(self._ai_enable)

        # Endpoint LOGOS (somente leitura — gerenciado pelo HUB)
        row_ep = QHBoxLayout()
        row_ep.addWidget(self._label("Endpoint LOGOS:"))
        self._ai_endpoint = QLineEdit(
            self._cfg.get("ai_endpoint", "http://localhost:7072")
        )
        self._ai_endpoint.setFont(self._mono(12))
        self._ai_endpoint.setReadOnly(True)
        row_ep.addWidget(self._ai_endpoint, 1)
        layout.addLayout(row_ep)

        # Modelos ativos (definidos pelo HUB via perfil LOGOS — não editáveis aqui)
        self._ai_logos_info = QLabel("— modelos definidos pelo HUB —")
        self._ai_logos_info.setFont(self._mono(11))
        layout.addWidget(self._ai_logos_info)

        self._ai_status = QLabel("")
        self._ai_status.setObjectName("dialogStatusLabel")
        self._ai_status.setFont(self._mono(10))
        self._ai_status.setWordWrap(True)
        layout.addWidget(self._ai_status)

        self._ai_relevance_badge = QCheckBox(
            "Mostrar badge de relevância nos cards  (≥ 65%  · requer embeddings gerados)"
        )
        self._ai_relevance_badge.setFont(self._mono(12))
        self._ai_relevance_badge.setChecked(bool(self._cfg.get("ai_relevance_badge", False)))
        self._ai_relevance_badge.stateChanged.connect(
            lambda s: self._cfg.set(
                "ai_relevance_badge", s == Qt.CheckState.Checked.value
            )
        )
        layout.addWidget(self._ai_relevance_badge)

        self._ai_sentiment_border = QCheckBox(
            "Mostrar borda de sentimento nos cards  (verde = positivo · vermelho = negativo)"
        )
        self._ai_sentiment_border.setFont(self._mono(12))
        self._ai_sentiment_border.setChecked(bool(self._cfg.get("ai_sentiment_border", False)))
        self._ai_sentiment_border.stateChanged.connect(
            lambda s: self._cfg.set(
                "ai_sentiment_border", s == Qt.CheckState.Checked.value
            )
        )
        layout.addWidget(self._ai_sentiment_border)

        self._ai_clickbait_badge = QCheckBox(
            "Mostrar badge de clickbait nos cards  (⚠ quando > 60%)"
        )
        self._ai_clickbait_badge.setFont(self._mono(12))
        self._ai_clickbait_badge.setChecked(bool(self._cfg.get("ai_clickbait_badge", False)))
        self._ai_clickbait_badge.stateChanged.connect(
            lambda s: self._cfg.set(
                "ai_clickbait_badge", s == Qt.CheckState.Checked.value
            )
        )
        layout.addWidget(self._ai_clickbait_badge)

        return box

    # ------------------------------------------------------------------
    # Seção: Reddit
    # ------------------------------------------------------------------

    def _section_reddit(self) -> QGroupBox:
        box = QGroupBox("REDDIT")
        box.setFont(self._mono(10))
        layout = QVBoxLayout(box)
        layout.setSpacing(12)

        note = QLabel(
            "Credenciais gratuitas em reddit.com/prefs/apps  "
            "(tipo: script, redirect: http://localhost:8080)"
        )
        note.setObjectName("cardMeta")
        note.setFont(self._mono(10))
        note.setWordWrap(True)
        layout.addWidget(note)

        # Client ID
        row = QHBoxLayout()
        row.addWidget(self._label("Client ID:"))
        self._reddit_id = QLineEdit(self._cfg.get("reddit_client_id", ""))
        self._reddit_id.setFont(self._mono(12))
        self._reddit_id.setPlaceholderText("xxxxxxxxxxxxxxx")
        self._reddit_id.editingFinished.connect(
            lambda: self._cfg.set("reddit_client_id", self._reddit_id.text().strip())
        )
        row.addWidget(self._reddit_id, 1)
        layout.addLayout(row)

        # Client Secret
        row2 = QHBoxLayout()
        row2.addWidget(self._label("Client Secret:"))
        self._reddit_secret = QLineEdit(self._cfg.get("reddit_client_secret", ""))
        self._reddit_secret.setFont(self._mono(12))
        self._reddit_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._reddit_secret.setPlaceholderText("••••••••••••••••••••••••••••")
        self._reddit_secret.editingFinished.connect(
            lambda: self._cfg.set("reddit_client_secret", self._reddit_secret.text().strip())
        )
        row2.addWidget(self._reddit_secret, 1)
        layout.addLayout(row2)

        # Testar conexão
        btn_row = QHBoxLayout()
        test_btn = QPushButton("Testar conexão")
        test_btn.setFont(self._mono(11))
        test_btn.clicked.connect(self._on_test_reddit)
        btn_row.addWidget(test_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._reddit_status = QLabel("")
        self._reddit_status.setObjectName("dialogStatusLabel")
        self._reddit_status.setFont(self._mono(10))
        layout.addWidget(self._reddit_status)

        return box

    # ------------------------------------------------------------------
    # Seção: Avançado
    # ------------------------------------------------------------------

    def _section_advanced(self) -> QGroupBox:
        box = QGroupBox("AVANÇADO")
        box.setFont(self._mono(10))
        layout = QVBoxLayout(box)
        layout.setSpacing(10)

        from app.utils.paths import Paths

        def _path_row(label: str, path: object, tag: str = "") -> QLabel:
            tag_str = f"  [{tag}]" if tag else ""
            lbl = QLabel(f"{label}{tag_str}  {path}")
            lbl.setObjectName("cardMeta")
            lbl.setFont(self._mono(10))
            lbl.setWordWrap(True)
            return lbl

        layout.addWidget(_path_row("Archive (artigos):", Paths.ARCHIVE, "sincronizado"))
        layout.addWidget(_path_row("Configurações:", Paths.SETTINGS, "sincronizado"))
        layout.addWidget(_path_row("Banco de dados:", Paths.DB, "local"))
        layout.addWidget(_path_row("Pasta de dados:", Paths.DATA, "local"))

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("listSeparator")
        layout.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        clear_img_btn = QPushButton("Limpar cache de imagens")
        clear_img_btn.setFont(self._mono(11))
        clear_img_btn.clicked.connect(lambda: self._clear_cache(Paths.IMAGES))
        btn_row.addWidget(clear_img_btn)

        clear_fav_btn = QPushButton("Limpar cache de favicons")
        clear_fav_btn.setFont(self._mono(11))
        clear_fav_btn.clicked.connect(lambda: self._clear_cache(Paths.FAVICONS))
        btn_row.addWidget(clear_fav_btn)

        open_btn = QPushButton("Abrir pasta de dados")
        open_btn.setFont(self._mono(11))
        open_btn.clicked.connect(lambda: self._open_folder(Paths.DATA))
        btn_row.addWidget(open_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        btn_row2 = QHBoxLayout()
        btn_row2.setSpacing(8)

        del_articles_btn = QPushButton("Apagar notícias não arquivadas")
        del_articles_btn.setFont(self._mono(11))
        del_articles_btn.setToolTip(
            "Remove permanentemente todos os artigos que não foram arquivados (is_saved = 0).\n"
            "Artigos salvos/arquivados são preservados."
        )
        del_articles_btn.clicked.connect(self._delete_unarchived_articles)
        btn_row2.addWidget(del_articles_btn)

        btn_row2.addStretch()
        layout.addLayout(btn_row2)

        self._adv_status = QLabel("")
        self._adv_status.setObjectName("dialogStatusLabel")
        self._adv_status.setFont(self._mono(10))
        layout.addWidget(self._adv_status)

        return box

    # ------------------------------------------------------------------
    # Helpers de widgets
    # ------------------------------------------------------------------

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(self._mono(12))
        lbl.setFixedWidth(200)
        lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        return lbl

    def _combo(
        self,
        options: list[tuple[str, int]],
        config_key: str,
        default: int,
    ) -> QComboBox:
        cb = QComboBox()
        cb.setFont(self._mono(11))
        cb.setFixedWidth(160)
        current = self._cfg.get(config_key, default)
        for label, value in options:
            cb.addItem(label, value)
            if value == current:
                cb.setCurrentIndex(cb.count() - 1)
        cb.currentIndexChanged.connect(
            lambda _i, c=cb, k=config_key: self._cfg.set(k, c.currentData())
        )
        return cb

    @staticmethod
    def _mono(size: int) -> QFont:
        f = QFont("Courier Prime")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(size)
        return f

    # ------------------------------------------------------------------
    # Refresh (chamado ao entrar na view)
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Recarrega valores atuais das configurações nos widgets."""
        self._refresh_appearance_widgets()

        # Blocklist
        current = self._cfg.get("keyword_blocklist", [])
        self._blocklist_edit.setPlainText("\n".join(current))
        self._blocklist_status.setText("")

        # IA
        self._ai_enable.setChecked(bool(self._cfg.get("ai_enabled", False)))
        self._ai_endpoint.setText(self._cfg.get("ai_endpoint", "http://localhost:7072"))
        gen_val = self._cfg.get("ai_gen_model", "")
        emb_val = self._cfg.get("ai_embed_model", "")
        parts: list[str] = []
        if gen_val:
            parts.append(f"geração: {gen_val}")
        if emb_val:
            parts.append(f"embeddings: {emb_val}")
        self._ai_logos_info.setText(
            "  ·  ".join(parts) if parts else "— modelos definidos pelo HUB —"
        )
        self._ai_status.setText("")
        self._ai_relevance_badge.setChecked(bool(self._cfg.get("ai_relevance_badge", False)))

        # Reddit
        self._reddit_id.setText(self._cfg.get("reddit_client_id", ""))
        self._reddit_secret.setText(self._cfg.get("reddit_client_secret", ""))
        self._reddit_status.setText("")

        # Combos
        for combo, key, default in [
            (self._interval_combo,    "update_interval_minutes", 30),
            (self._purge_read_combo,  "purge_read_days",         30),
            (self._purge_unread_combo,"purge_unread_days",        90),
            (self._date_limit_combo,  "dev_article_age_days",     0),
        ]:
            val = self._cfg.get(key, default)
            for i in range(combo.count()):
                if combo.itemData(i) == val:
                    combo.setCurrentIndex(i)
                    break

    def _refresh_appearance_widgets(self) -> None:
        theme = self._theme.current
        if theme == "day":
            self._theme_btn.setText("☀  Modo Diurno  (ativo)")
        else:
            self._theme_btn.setText("☾  Modo Noturno  (ativo)")

        current_size = self._cfg.get("reader_font_size", 18)
        idx = _FONT_SIZES.index(current_size) if current_size in _FONT_SIZES else 2
        self._font_slider.blockSignals(True)
        self._font_slider.setValue(idx)
        self._font_slider.blockSignals(False)
        self._font_size_lbl.setText(f"{current_size}px")

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_toggle_theme(self) -> None:
        new_theme = self._theme.toggle_theme()
        self._cfg.set("theme", new_theme)
        self._refresh_appearance_widgets()
        self.theme_changed.emit(new_theme)

    # ------------------------------------------------------------------
    # Verificação de status do Ollama (H.1)
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._check_ollama_status()

    def _check_ollama_status(self) -> None:
        if hasattr(self, "_ollama_check_worker") and self._ollama_check_worker.isRunning():
            return
        endpoint = self._cfg.get("ai_endpoint", "http://localhost:7072")
        model    = str(self._cfg.get("ai_gen_model", ""))
        self._ollama_conn_lbl.setText("○  verificando…")
        self._ollama_conn_lbl.setObjectName("ollamaUnknown")
        self._ollama_conn_lbl.style().unpolish(self._ollama_conn_lbl)
        self._ollama_conn_lbl.style().polish(self._ollama_conn_lbl)
        self._ollama_check_worker = _OllamaCheckWorker(str(endpoint), model)
        self._ollama_check_worker.result.connect(self._on_ollama_check_done)
        self._ollama_check_worker.start()

    def _on_ollama_check_done(self, available: bool, model: str) -> None:
        lbl = self._ollama_conn_lbl
        if available:
            suffix = f"  ·  {model}" if model else ""
            lbl.setText(f"●  Ollama conectado{suffix}")
            lbl.setObjectName("ollamaOnline")
        else:
            lbl.setText("○  Ollama offline")
            lbl.setObjectName("ollamaOffline")
        lbl.style().unpolish(lbl)
        lbl.style().polish(lbl)

    def _on_font_size_changed(self, index: int) -> None:
        size = _FONT_SIZES[index]
        self._cfg.set("reader_font_size", size)
        self._font_size_lbl.setText(f"{size}px")

    def _on_display_lang_changed(self, _index: int) -> None:
        lang = self._display_lang_combo.currentData()
        self._cfg.set("display_language", lang or "")

    def _on_save_blocklist(self) -> None:
        raw   = self._blocklist_edit.toPlainText()
        terms = [t.strip() for t in raw.splitlines() if t.strip()]
        self._cfg.set("keyword_blocklist", terms)
        n = len(terms)
        self._blocklist_status.setText(f"✓ {n} termo{'s' if n != 1 else ''} salvo{'s' if n != 1 else ''}")


    def _on_test_reddit(self) -> None:
        client_id     = self._reddit_id.text().strip()
        client_secret = self._reddit_secret.text().strip()

        if not client_id or not client_secret:
            self._reddit_status.setText("⚠ Preencha o client_id e o client_secret.")
            return

        self._reddit_status.setText("Testando…")

        try:
            import praw
            reddit = praw.Reddit(
                client_id     = client_id,
                client_secret = client_secret,
                user_agent    = "KOSMOS/1.0",
            )
            # Verificar autenticação fazendo um request simples
            list(reddit.subreddit("all").hot(limit=1))
            self._cfg.set("reddit_client_id",     client_id)
            self._cfg.set("reddit_client_secret", client_secret)
            self._reddit_status.setText("✓ Conexão com o Reddit OK.")
        except Exception as exc:
            self._reddit_status.setText(f"✗ Falha: {exc}")

    def _delete_unarchived_articles(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Apagar notícias",
            "Isso vai apagar permanentemente todos os artigos não arquivados.\n"
            "Artigos salvos são preservados. Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        deleted = self._fm.delete_unarchived_articles()
        self._adv_status.setText(f"✓ {deleted} artigo{'s' if deleted != 1 else ''} apagado{'s' if deleted != 1 else ''}.")
        log.info("Usuária apagou %d artigos não arquivados.", deleted)

    @staticmethod
    def _clear_cache(path) -> None:
        import shutil
        if path.exists():
            shutil.rmtree(path)
            path.mkdir(parents=True, exist_ok=True)
            log.info("Cache limpo: %s", path)

    @staticmethod
    def _open_folder(path) -> None:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
