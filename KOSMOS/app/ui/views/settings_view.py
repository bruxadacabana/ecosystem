"""
settings_view.py — Página de Configurações do KOSMOS (design antigo).

Página (não diálogo) com cabeçalho "⚙ Configurações" + seções (QGroupBox) roláveis:
Aparência (tema, fonte), Tradução (backend, idioma), Tópicos (interesses manuais) e
Fontes (adicionar/listar/remover/OPML). Substitui a antiga SettingsDialog tabulada.

Operações de feed agem direto no banco via `feeds_admin` (que reexporta o
`sources.json` de backup) e emitem `feeds_changed`. As demais configs são gravadas no
"Salvar" (save_config + reaplica tema + aplica tópicos) e emitem `config_saved`. O
`main_window` recarrega a sidebar/lista ao receber os sinais.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.feeds_admin import add_feed, delete_feed, import_opml, list_feeds
from app.core.interests import apply_manual_topics
from app.theme.theme_manager import apply_theme
from app.utils.config import KosmosConfig, save_config

log = logging.getLogger("kosmos.settings_view")

_THEMES = [("day", "Dia (claro)"), ("night", "Noite (escuro)")]
_BACKENDS = [("argos", "Argos (offline)"), ("logos", "LOGOS (online)")]


class SettingsView(QWidget):
    """Página de Configurações: aparência + tradução + tópicos + fontes."""

    feeds_changed = Signal()   # após add/remove/import de feed
    config_saved = Signal()    # após salvar as configs

    def __init__(self, config: KosmosConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.setObjectName("settingsView")
        self._setup_ui()
        self._load_from_config()
        self.reload_feeds()

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("settingsHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(32, 16, 32, 16)
        title = QLabel("⚙  Configurações")
        title.setObjectName("settingsTitle")
        tf = QFont("Special Elite")
        if not tf.exactMatch():
            tf = QFont("Courier New")
        tf.setPointSize(18)
        title.setFont(tf)
        hl.addWidget(title)
        hl.addStretch(1)
        self._save_btn = QPushButton("Salvar configurações")
        self._save_btn.setObjectName("settingsSaveBtn")
        self._save_btn.clicked.connect(self._on_save)
        hl.addWidget(self._save_btn)
        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        cl = QVBoxLayout(container)
        cl.setContentsMargins(32, 16, 32, 32)
        cl.setSpacing(16)
        cl.addWidget(self._section_appearance())
        cl.addWidget(self._section_translation())
        cl.addWidget(self._section_topics())
        cl.addWidget(self._section_feeds())
        cl.addStretch(1)
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

    def _group(self, title: str) -> QGroupBox:
        box = QGroupBox(title)
        box.setObjectName("settingsSection")
        return box

    def _section_appearance(self) -> QGroupBox:
        box = self._group("Aparência")
        form = QFormLayout(box)
        self._theme_combo = QComboBox()
        for _k, label in _THEMES:
            self._theme_combo.addItem(label)
        form.addRow("Tema:", self._theme_combo)
        self._font_spin = QSpinBox()
        self._font_spin.setRange(10, 36)
        form.addRow("Tamanho da fonte do leitor:", self._font_spin)
        return box

    def _section_translation(self) -> QGroupBox:
        box = self._group("Tradução")
        form = QFormLayout(box)
        self._backend_combo = QComboBox()
        for _k, label in _BACKENDS:
            self._backend_combo.addItem(label)
        form.addRow("Backend de tradução:", self._backend_combo)
        self._lang_edit = QLineEdit()
        self._lang_edit.setPlaceholderText("ex.: pt, en, es")
        form.addRow("Idioma alvo:", self._lang_edit)
        return box

    def _section_topics(self) -> QGroupBox:
        box = self._group("Tópicos de interesse")
        lay = QVBoxLayout(box)
        lay.addWidget(QLabel("Um por linha — reforçam o perfil compartilhado:"))
        self._topics_edit = QPlainTextEdit()
        self._topics_edit.setObjectName("settings_topics")
        self._topics_edit.setMaximumHeight(120)
        lay.addWidget(self._topics_edit)
        return box

    def _section_feeds(self) -> QGroupBox:
        box = self._group("Fontes (feeds)")
        lay = QVBoxLayout(box)

        add_row = QHBoxLayout()
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("URL do feed RSS/Atom")
        add_row.addWidget(self._url_edit, 3)
        self._cat_edit = QLineEdit()
        self._cat_edit.setPlaceholderText("Categoria (opcional)")
        add_row.addWidget(self._cat_edit, 1)
        add_btn = QPushButton("Adicionar")
        add_btn.clicked.connect(self._on_add_feed)
        add_row.addWidget(add_btn)
        lay.addLayout(add_row)

        self._feed_list = QListWidget()
        self._feed_list.setObjectName("settings_feed_list")
        self._feed_list.setMinimumHeight(160)
        lay.addWidget(self._feed_list, 1)

        actions = QHBoxLayout()
        opml_btn = QPushButton("Importar OPML…")
        opml_btn.clicked.connect(self._on_import_opml)
        actions.addWidget(opml_btn)
        actions.addStretch(1)
        remove_btn = QPushButton("Remover selecionado")
        remove_btn.clicked.connect(self._on_remove_feed)
        actions.addWidget(remove_btn)
        lay.addLayout(actions)

        self._feeds_status = QLabel("")
        self._feeds_status.setProperty("class", "meta")
        lay.addWidget(self._feeds_status)
        return box

    # ------------------------------------------------------------------
    # Feeds
    # ------------------------------------------------------------------

    def reload_feeds(self) -> None:
        self._feed_list.clear()
        feeds = list_feeds()
        for f in feeds:
            label = f"{f['title'] or f['url']}  ·  {f['category']}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, f["id"])
            self._feed_list.addItem(item)
        self._feeds_status.setText(f"{len(feeds)} fonte(s).")

    def _on_add_feed(self) -> None:
        url = self._url_edit.text().strip()
        if not url:
            return
        fid = add_feed(url, "", self._cat_edit.text().strip() or "Sem categoria")
        if fid is not None:
            self._url_edit.clear()
            self._cat_edit.clear()
            self.reload_feeds()
            self.feeds_changed.emit()
            log.info("Feed adicionado pelas Configurações: %s", url)

    def _on_remove_feed(self) -> None:
        item = self._feed_list.currentItem()
        if item is None:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        if fid is not None:
            delete_feed(int(fid))
            self.reload_feeds()
            self.feeds_changed.emit()
            log.info("Feed %s removido pelas Configurações.", fid)

    def _on_import_opml(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar OPML", "", "OPML/XML (*.opml *.xml)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            log.error("Falha ao ler OPML %s: %s", path, exc)
            self._feeds_status.setText("Não foi possível ler o arquivo.")
            return
        n = import_opml(text)
        self.reload_feeds()
        self.feeds_changed.emit()
        self._feeds_status.setText(f"{n} feed(s) novo(s) importado(s).")
        log.info("OPML importado pelas Configurações: %d feed(s) novo(s).", n)

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _load_from_config(self) -> None:
        keys = [k for k, _ in _THEMES]
        self._theme_combo.setCurrentIndex(keys.index(self.config.theme) if self.config.theme in keys else 0)
        self._font_spin.setValue(int(self.config.reader_font_size or 20))
        bkeys = [k for k, _ in _BACKENDS]
        self._backend_combo.setCurrentIndex(
            bkeys.index(self.config.translation_backend) if self.config.translation_backend in bkeys else 0)
        self._lang_edit.setText(self.config.default_translation_lang or "pt")
        self._topics_edit.setPlainText("\n".join(self.config.manual_topics or []))

    def _on_save(self) -> None:
        self.config.theme = _THEMES[self._theme_combo.currentIndex()][0]
        self.config.reader_font_size = self._font_spin.value()
        self.config.translation_backend = _BACKENDS[self._backend_combo.currentIndex()][0]
        self.config.default_translation_lang = self._lang_edit.text().strip() or "pt"
        self.config.manual_topics = [
            ln.strip() for ln in self._topics_edit.toPlainText().splitlines() if ln.strip()
        ]
        try:
            save_config(self.config)
        except OSError as exc:
            log.error("Falha ao salvar config: %s", exc)
            return
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self.config.theme)
        try:
            apply_manual_topics(self.config.manual_topics)
        except Exception as exc:
            log.error("Falha ao aplicar tópicos manuais: %s", exc)
        log.info("Configurações salvas.")
        self.config_saved.emit()
