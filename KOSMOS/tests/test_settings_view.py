"""
Testes de app/ui/views/settings_view.py — página de Configurações (design antigo).

Cobre: carregar config nos widgets; lista de fontes; add/remove chamam feeds_admin e
emitem feeds_changed; salvar grava config + reaplica tema + emite config_saved.
As funções de feed/config são mockadas (sem DB nem sync_root).
"""
from __future__ import annotations

from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest

from app.utils.config import KosmosConfig
from app.ui.views.settings_view import SettingsView


def _cfg():
    return KosmosConfig(theme="day", reader_font_size=20, translation_backend="argos",
                        default_translation_lang="pt", manual_topics=["a", "b"], config_path="/tmp/x")


def _view(qapp, feeds=None):
    with patch("app.ui.views.settings_view.list_feeds", return_value=feeds or []):
        return SettingsView(_cfg())


def test_loads_config(qapp):
    v = _view(qapp)
    assert v._theme_combo.currentIndex() == 0          # day
    assert v._lang_edit.text() == "pt"
    assert v._backend_combo.currentIndex() == 0        # argos
    assert v._topics_edit.toPlainText() == "a\nb"


def test_reload_feeds_populates(qapp):
    feeds = [{"id": 1, "url": "http://a", "title": "Feed A", "category": "Geral", "enabled": 1}]
    v = _view(qapp, feeds)
    assert v._feed_list.count() == 1
    assert "Feed A" in v._feed_list.item(0).text() and "Geral" in v._feed_list.item(0).text()


def test_add_feed_calls_and_emits(qapp):
    v = _view(qapp)
    got = []
    v.feeds_changed.connect(lambda: got.append(1))
    v._url_edit.setText("http://new.com/rss")
    v._cat_edit.setText("Tech")
    with patch("app.ui.views.settings_view.add_feed", return_value=5) as madd, \
         patch("app.ui.views.settings_view.list_feeds", return_value=[]):
        v._on_add_feed()
    madd.assert_called_once_with("http://new.com/rss", "", "Tech")
    assert got == [1]
    assert v._url_edit.text() == ""        # campos limpos


def test_add_feed_ignores_empty_url(qapp):
    v = _view(qapp)
    with patch("app.ui.views.settings_view.add_feed") as madd:
        v._on_add_feed()                    # url vazia
    madd.assert_not_called()


def test_remove_feed_calls(qapp):
    feeds = [{"id": 7, "url": "http://a", "title": "A", "category": "G", "enabled": 1}]
    v = _view(qapp, feeds)
    v._feed_list.setCurrentRow(0)
    with patch("app.ui.views.settings_view.delete_feed") as mdel, \
         patch("app.ui.views.settings_view.list_feeds", return_value=[]):
        v._on_remove_feed()
    mdel.assert_called_once_with(7)


def test_save_roundtrip(qapp):
    v = _view(qapp)
    v._theme_combo.setCurrentIndex(1)       # night
    v._lang_edit.setText("en")
    v._backend_combo.setCurrentIndex(1)     # logos
    v._font_spin.setValue(24)
    v._topics_edit.setPlainText("x\n\n  y  ")   # linhas vazias/espaços ignoradas
    emitted = []
    v.config_saved.connect(lambda: emitted.append(1))
    with patch("app.ui.views.settings_view.save_config") as msave, \
         patch("app.ui.views.settings_view.apply_theme") as mtheme, \
         patch("app.ui.views.settings_view.apply_manual_topics") as mtopics:
        v._on_save()
    assert v.config.theme == "night"
    assert v.config.default_translation_lang == "en"
    assert v.config.translation_backend == "logos"
    assert v.config.reader_font_size == 24
    assert v.config.manual_topics == ["x", "y"]
    msave.assert_called_once()
    mtheme.assert_called_once()
    mtopics.assert_called_once_with(["x", "y"])
    assert emitted == [1]
