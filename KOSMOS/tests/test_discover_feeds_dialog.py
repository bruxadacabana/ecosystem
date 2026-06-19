"""
Testes do DiscoverFeedsDialog — diálogo "Descobrir feeds de um site".

Cobre as partes não-threaded (testáveis): _populate mostra os candidatos / status de
vazio; _on_add grava via feeds_admin.add_feed e emite feeds_changed; a linha de
candidato emite add_requested ao clicar.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.feed_discovery import FeedCandidate
from app.ui.dialogs.discover_feeds_dialog import DiscoverFeedsDialog, _CandidateRow


def test_populate_shows_candidates(qapp):
    dlg = DiscoverFeedsDialog()
    dlg._populate([FeedCandidate("http://a/feed", "A"), FeedCandidate("http://b/feed", "B")])
    rows = dlg._results.findChildren(_CandidateRow)
    assert len(rows) == 2
    assert "2 feed(s)" in dlg._status.text()


def test_populate_empty_sets_status(qapp):
    dlg = DiscoverFeedsDialog()
    dlg._populate([])
    assert "Nenhum feed" in dlg._status.text()
    assert dlg._results.findChildren(_CandidateRow) == []


def test_on_add_calls_add_feed_and_emits(qapp):
    dlg = DiscoverFeedsDialog()
    got = []
    dlg.feeds_changed.connect(lambda: got.append(1))
    with patch("app.ui.dialogs.discover_feeds_dialog.add_feed", return_value=9) as madd:
        dlg._on_add("http://a/feed", "A")
    madd.assert_called_once_with("http://a/feed", "A", "Sem categoria")
    assert got == [1]


def test_on_add_failure_does_not_emit(qapp):
    dlg = DiscoverFeedsDialog()
    got = []
    dlg.feeds_changed.connect(lambda: got.append(1))
    with patch("app.ui.dialogs.discover_feeds_dialog.add_feed", return_value=None):
        dlg._on_add("http://a/feed", "A")
    assert got == []


def test_candidate_row_emits_add(qapp):
    row = _CandidateRow(FeedCandidate("http://a/feed", "A"))
    got = []
    row.add_requested.connect(lambda u, t: got.append((u, t)))
    row._add_btn.click()
    assert got == [("http://a/feed", "A")]
    row.mark_added()
    assert not row._add_btn.isEnabled()
