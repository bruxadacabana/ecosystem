"""
Testes do agendamento da reflexão (relógio) e do bloco cross-device.

- _reflection_due/_last_reflection_at/_mark_reflected: estado persistido por relógio.
- _cross_device_block: lê shared_history, agrupa por máquina, exclui a máquina atual.
"""
from __future__ import annotations

import json
import time

import services.reflection_loop as rl


# ── Agendamento ancorado no relógio ──────────────────────────────

def test_due_when_never_reflected(monkeypatch, tmp_path):
    monkeypatch.setattr(rl, "_state_path", lambda: tmp_path / "s.json")
    assert rl._last_reflection_at() == 0.0
    assert rl._reflection_due() is True


def test_not_due_after_mark(monkeypatch, tmp_path):
    monkeypatch.setattr(rl, "_state_path", lambda: tmp_path / "s.json")
    rl._mark_reflected()
    assert rl._last_reflection_at() > 0
    assert rl._reflection_due() is False


def test_due_again_after_interval(monkeypatch, tmp_path):
    p = tmp_path / "s.json"
    monkeypatch.setattr(rl, "_state_path", lambda: p)
    p.write_text(json.dumps({"last_reflection_at": time.time() - rl._REFLECTION_INTERVAL_S - 10}),
                 encoding="utf-8")
    assert rl._reflection_due() is True


def test_corrupt_state_treated_as_never(monkeypatch, tmp_path):
    p = tmp_path / "s.json"
    monkeypatch.setattr(rl, "_state_path", lambda: p)
    p.write_text("lixo nao-json", encoding="utf-8")
    assert rl._last_reflection_at() == 0.0
    assert rl._reflection_due() is True


# ── Bloco cross-device (atividade em outras máquinas) ────────────

def test_cross_block_groups_and_excludes_current(monkeypatch):
    import shared_history as sh
    monkeypatch.setattr(rl.socket, "gethostname", lambda: "this-pc")
    monkeypatch.setattr(sh, "recent_searches", lambda n=20: [
        {"query": "crochê", "machine": "home-pc"},
        {"query": "kernel", "machine": "lap-top"},
        {"query": "so-aqui", "machine": "this-pc"},
    ])
    monkeypatch.setattr(sh, "recent_visits", lambda n=20: [
        {"url": "http://a", "title": "Blog A", "machine": "home-pc"},
    ])
    block = rl._cross_device_block()
    assert "Atividade em outros dispositivos" in block
    assert "home-pc" in block and "lap-top" in block
    assert "crochê" in block and "Blog A" in block
    assert "this-pc" not in block       # máquina atual excluída
    assert "so-aqui" not in block


def test_cross_block_empty_when_only_current_machine(monkeypatch):
    import shared_history as sh
    monkeypatch.setattr(rl.socket, "gethostname", lambda: "this-pc")
    monkeypatch.setattr(sh, "recent_searches", lambda n=20: [{"query": "x", "machine": "this-pc"}])
    monkeypatch.setattr(sh, "recent_visits", lambda n=20: [])
    assert rl._cross_device_block() == ""


def test_cross_block_empty_when_shared_history_fails(monkeypatch):
    import shared_history as sh

    def _boom(n=20):
        raise RuntimeError("sem sync_root")

    monkeypatch.setattr(sh, "recent_searches", _boom)
    monkeypatch.setattr(sh, "recent_visits", _boom)
    assert rl._cross_device_block() == ""
