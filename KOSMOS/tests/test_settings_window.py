"""
Testes de app/ui/views/settings_window.py — janela de Configurações (Fase Config).

Cobre: carregar config nos widgets; lista de feeds; add/remove chamam feeds_admin e
emitem feeds_changed; salvar grava config + reaplica tema + emite config_saved.
As funções de feed/config são mockadas (sem DB nem sync_root).
"""
from __future__ import annotations

from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest

from app.utils.config import KosmosConfig
from app.ui.views.settings_window import SettingsDialog


def _cfg():
    return KosmosConfig(theme="day", reader_font_size=20, translation_backend="argos",
                        default_translation_lang="pt", manual_topics=["a", "b"], config_path="/tmp/x")


def _dialog(qapp, feeds=None):
    with patch("app.ui.views.settings_window.list_feeds", return_value=feeds or []):
        return SettingsDialog(_cfg())


def test_loads_config(qapp):
    dlg = _dialog(qapp)
    assert dlg._theme_combo.currentIndex() == 0          # day
    assert dlg._lang_edit.text() == "pt"
    assert dlg._backend_combo.currentIndex() == 0        # argos
    assert dlg._topics_edit.toPlainText() == "a\nb"


def test_reload_feeds_populates(qapp):
    feeds = [{"id": 1, "url": "http://a", "title": "Feed A", "category": "Geral", "enabled": 1}]
    dlg = _dialog(qapp, feeds)
    assert dlg._feed_list.count() == 1
    assert "Feed A" in dlg._feed_list.item(0).text() and "Geral" in dlg._feed_list.item(0).text()


def test_add_feed_calls_and_emits(qapp):
    dlg = _dialog(qapp)
    got = []
    dlg.feeds_changed.connect(lambda: got.append(1))
    dlg._url_edit.setText("http://new.com/rss")
    dlg._cat_edit.setText("Tech")
    with patch("app.ui.views.settings_window.add_feed", return_value=5) as madd, \
         patch("app.ui.views.settings_window.list_feeds", return_value=[]):
        dlg._on_add_feed()
    madd.assert_called_once_with("http://new.com/rss", "", "Tech")
    assert got == [1]
    assert dlg._url_edit.text() == ""        # campos limpos


def test_add_feed_ignores_empty_url(qapp):
    dlg = _dialog(qapp)
    with patch("app.ui.views.settings_window.add_feed") as madd:
        dlg._on_add_feed()                    # url vazia
    madd.assert_not_called()


def test_remove_feed_calls(qapp):
    feeds = [{"id": 7, "url": "http://a", "title": "A", "category": "G", "enabled": 1}]
    dlg = _dialog(qapp, feeds)
    dlg._feed_list.setCurrentRow(0)
    with patch("app.ui.views.settings_window.delete_feed") as mdel, \
         patch("app.ui.views.settings_window.list_feeds", return_value=[]):
        dlg._on_remove_feed()
    mdel.assert_called_once_with(7)


def test_save_roundtrip(qapp):
    dlg = _dialog(qapp)
    dlg._theme_combo.setCurrentIndex(1)       # night
    dlg._lang_edit.setText("en")
    dlg._backend_combo.setCurrentIndex(1)     # logos
    dlg._font_spin.setValue(24)
    dlg._topics_edit.setPlainText("x\n\n  y  ")   # linhas vazias/espaços ignoradas
    emitted = []
    dlg.config_saved.connect(lambda: emitted.append(1))
    with patch("app.ui.views.settings_window.save_config") as msave, \
         patch("app.ui.views.settings_window.apply_theme") as mtheme, \
         patch("app.ui.views.settings_window.apply_manual_topics") as mtopics:
        dlg._on_save()
    assert dlg.config.theme == "night"
    assert dlg.config.default_translation_lang == "en"
    assert dlg.config.translation_backend == "logos"
    assert dlg.config.reader_font_size == 24
    assert dlg.config.manual_topics == ["x", "y"]
    msave.assert_called_once()
    mtheme.assert_called_once()
    mtopics.assert_called_once_with(["x", "y"])
    assert emitted == [1]
