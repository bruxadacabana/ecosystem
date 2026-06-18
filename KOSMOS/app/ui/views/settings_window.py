"""
settings_window.py — janela de Configurações do KOSMOS (Fase Config).

Uma única janela (QDialog) com abas:
  - Feeds: adicionar (URL + categoria), listar, remover, importar OPML.
  - Aparência: tema (day/night) e tamanho da fonte do leitor.
  - Tradução: backend (argos/logos) e idioma alvo.
  - Tópicos: tags de interesse manuais (uma por linha).

Operações de feed agem direto no banco (via `feeds_admin`, que também reexporta o
`sources.json` de backup) e emitem `feeds_changed`. As demais configs são gravadas
no "Salvar" (config.save_config + reaplica tema + aplica tópicos) e emitem
`config_saved`. O `main_window` recarrega a sidebar/lista ao receber os sinais.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.feeds_admin import add_feed, delete_feed, import_opml, list_feeds
from app.core.interests import apply_manual_topics
from app.theme.theme_manager import apply_theme
from app.utils.config import KosmosConfig, save_config

log = logging.getLogger("kosmos.settings_window")

_THEMES = [("day", "Dia (claro)"), ("night", "Noite (escuro)")]
_BACKENDS = [("argos", "Argos (offline)"), ("logos", "LOGOS (online)")]


class SettingsDialog(QDialog):
    """Janela de Configurações: feeds + aparência + tradução + tópicos."""

    feeds_changed = Signal()   # após add/remove/import de feed
    config_saved = Signal()    # após salvar as configs

    def __init__(self, config: KosmosConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Configurações — KOSMOS")
        self.setObjectName("settings_dialog")
        self.resize(660, 500)
        self._setup_ui()
        self._load_from_config()
        self.reload_feeds()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_feeds_tab(), "Feeds")
        self._tabs.addTab(self._build_appearance_tab(), "Aparência")
        self._tabs.addTab(self._build_translation_tab(), "Tradução")
        self._tabs.addTab(self._build_topics_tab(), "Tópicos")
        outer.addWidget(self._tabs)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self._save_btn = QPushButton("Salvar")
        self._save_btn.clicked.connect(self._on_save)
        bottom.addWidget(self._save_btn)
        self._close_btn = QPushButton("Fechar")
        self._close_btn.clicked.connect(self.accept)
        bottom.addWidget(self._close_btn)
        outer.addLayout(bottom)

    # ------------------------------------------------------------------
    # Aba Feeds
    # ------------------------------------------------------------------

    def _build_feeds_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

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
        return w

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
            log.info("Feed adicionado pela janela de Configurações: %s", url)

    def _on_remove_feed(self) -> None:
        item = self._feed_list.currentItem()
        if item is None:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        if fid is not None:
            delete_feed(int(fid))
            self.reload_feeds()
            self.feeds_changed.emit()

    def _on_import_opml(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar OPML", "", "OPML/XML (*.opml *.xml)")
        if not path:
            return
        try:
            text = open(path, encoding="utf-8").read()
        except OSError as exc:
            log.error("Falha ao ler OPML %s: %s", path, exc)
            self._feeds_status.setText("Não foi possível ler o arquivo.")
            return
        n = import_opml(text)
        self.reload_feeds()
        self.feeds_changed.emit()
        self._feeds_status.setText(f"{n} feed(s) novo(s) importado(s).")

    # ------------------------------------------------------------------
    # Abas de config
    # ------------------------------------------------------------------

    def _build_appearance_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._theme_combo = QComboBox()
        for _key, label in _THEMES:
            self._theme_combo.addItem(label)
        form.addRow("Tema:", self._theme_combo)
        self._font_spin = QSpinBox()
        self._font_spin.setRange(10, 36)
        form.addRow("Tamanho da fonte do leitor:", self._font_spin)
        return w

    def _build_translation_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._backend_combo = QComboBox()
        for _key, label in _BACKENDS:
            self._backend_combo.addItem(label)
        form.addRow("Backend de tradução:", self._backend_combo)
        self._lang_edit = QLineEdit()
        self._lang_edit.setPlaceholderText("ex.: pt, en, es")
        form.addRow("Idioma alvo:", self._lang_edit)
        return w

    def _build_topics_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Tópicos de interesse (um por linha) — reforçam o perfil compartilhado:"))
        self._topics_edit = QPlainTextEdit()
        self._topics_edit.setObjectName("settings_topics")
        lay.addWidget(self._topics_edit)
        return w

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
