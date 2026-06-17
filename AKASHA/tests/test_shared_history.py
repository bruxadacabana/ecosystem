"""
Testes do store de histórico compartilhado (`shared_history`, raiz do ecossistema).

Cobre: roundtrip (search/click/visit) com máquina de origem; ignora entradas
vazias; top_domains; backup JSON + auto-recria de banco corrompido.
"""
from __future__ import annotations

import pytest

import config  # noqa: F401 — insere a raiz do ecossistema no sys.path (p/ shared_history)


@pytest.fixture
def hist(tmp_path, monkeypatch):
    import ecosystem_client
    monkeypatch.setattr(ecosystem_client, "get_sync_root", lambda: tmp_path)
    import shared_history
    return shared_history, tmp_path


def test_roundtrip_records_with_machine(hist):
    sh, root = hist
    sh.record_search("crochê amigurumi", "web", 12)
    sh.record_click("https://a.com/x", "crochê amigurumi", 1)
    sh.record_visit("https://blog.example/post", "Post")

    assert sh.counts() == {"searches": 1, "clicks": 1, "visits": 1}

    s = sh.recent_searches()[0]
    assert s["query"] == "crochê amigurumi"
    assert s["result_count"] == 12
    assert s["machine"]  # hostname não vazio
    assert s["created_at"]

    assert sh.recent_clicks()[0]["url"] == "https://a.com/x"
    assert sh.recent_visits()[0]["title"] == "Post"

    assert (root / "akasha_history.db").exists()
    assert (root / "akasha_history.json").exists()


def test_empty_entries_ignored(hist):
    sh, _ = hist
    sh.record_search("   ")
    sh.record_click("")
    sh.record_visit("")
    assert sh.counts() == {"searches": 0, "clicks": 0, "visits": 0}


def test_top_domains(hist):
    sh, _ = hist
    sh.record_visit("https://a.com/1")
    sh.record_visit("https://a.com/2")
    sh.record_visit("https://b.com/1")
    td = dict(sh.top_domains())
    assert td.get("a.com") == 2
    assert td.get("b.com") == 1


def test_backup_and_recover_from_corruption(hist):
    sh, root = hist
    sh.record_search("x", "web", 1)
    sh.record_visit("https://v.com/p", "t")
    assert (root / "akasha_history.json").exists()

    # Corrompe o banco
    (root / "akasha_history.db").write_text("isto nao eh um banco sqlite", encoding="utf-8")

    # Próxima escrita detecta a corrupção, recria do backup JSON e insere a nova linha
    sh.record_visit("https://v2.com/p", "t2")

    c = sh.counts()
    assert c["searches"] == 1, "search do backup deve ter sido restaurada"
    assert c["visits"] == 2, "visita do backup + a nova"
