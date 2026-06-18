"""
Testes de app/ui/nav_rail.py — barra de navegação por páginas (design antigo).

Cobre: clique em item emite nav_requested e marca como ativo; Configurações emite
settings_requested sem trocar a página; ↻ e + emitem seus sinais; set_active não
emite; só um item ativo por vez.
"""
from __future__ import annotations

from PySide6.QtWidgets import QPushButton

from app.ui.nav_rail import NavRail


def test_nav_emits_view_on_click(qapp):
    rail = NavRail(theme="day")
    got: list[str] = []
    rail.nav_requested.connect(got.append)
    rail._buttons["analise"].click()
    assert got == ["analise"]
    assert rail._buttons["analise"].isChecked()


def test_settings_item_emits_nav(qapp):
    rail = NavRail(theme="day")
    navs: list[str] = []
    rail.nav_requested.connect(navs.append)
    rail._buttons["settings"].click()
    assert navs == ["settings"]                    # Configurações é uma página normal
    assert rail._buttons["settings"].isChecked()


def test_refresh_and_add_buttons_emit(qapp):
    rail = NavRail(theme="night")
    r: list[int] = []
    a: list[int] = []
    rail.refresh_requested.connect(lambda: r.append(1))
    rail.add_feed_requested.connect(lambda: a.append(1))
    icon_btns = [b for b in rail.findChildren(QPushButton) if b.objectName() == "navIconBtn"]
    assert len(icon_btns) == 2                          # ↻ e +
    for b in icon_btns:
        b.click()
    assert r == [1] and a == [1]


def test_set_active_does_not_emit(qapp):
    rail = NavRail(theme="day")
    got: list[str] = []
    rail.nav_requested.connect(got.append)
    rail.set_active("analise")
    assert got == []                                   # set_active é silencioso
    assert rail._buttons["analise"].isChecked()


def test_single_active_button(qapp):
    rail = NavRail(theme="day")
    rail._buttons["leitura"].click()
    rail._buttons["analise"].click()
    assert rail._buttons["analise"].isChecked()
    assert not rail._buttons["leitura"].isChecked()    # só um ativo por vez


def test_title_click_selects_dashboard(qapp):
    rail = NavRail(theme="day")
    got: list[str] = []
    rail.nav_requested.connect(got.append)
    titles = [b for b in rail.findChildren(QPushButton) if b.objectName() == "navRailTitle"]
    assert len(titles) == 1
    titles[0].click()
    assert got == ["dashboard"]   # título KOSMOS → tela inicial (Dashboard)
