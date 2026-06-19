"""
Testes de app/core/feed_discovery.py — descoberta e validação de feeds.

Toda a rede passa por `_get`, que é patchado com respostas falsas. Cobre:
validate_feed (válido/ inválido/ erro de rede/ vazio) e discover_feeds (feed
anunciado via <link>, normalização da URL, atom, e o fallback por caminhos comuns).
"""
from __future__ import annotations

from unittest.mock import patch

import requests

import app.core.feed_discovery as fd
from app.core.feed_discovery import FeedCandidate  # noqa: F401

_RSS = ('<?xml version="1.0"?><rss version="2.0"><channel><title>Meu Blog</title>'
        '<item><title>Post</title><link>http://x/p</link></item></channel></rss>')


class _FakeResp:
    def __init__(self, text: str) -> None:
        self.text = text
        self.content = text.encode("utf-8")

    def raise_for_status(self) -> None:
        pass


# ── validate_feed ──────────────────────────────────────────────────────────

def test_validate_feed_valid():
    with patch.object(fd, "_get", return_value=_FakeResp(_RSS)):
        ok, title = fd.validate_feed("http://x/feed")
    assert ok is True and title == "Meu Blog"


def test_validate_feed_invalid_content():
    with patch.object(fd, "_get", return_value=_FakeResp("<html>não é feed</html>")):
        ok, _ = fd.validate_feed("http://x")
    assert ok is False


def test_validate_feed_network_error():
    with patch.object(fd, "_get", side_effect=requests.RequestException("boom")):
        ok, msg = fd.validate_feed("http://x")
    assert ok is False and "acessar" in msg.lower()


def test_validate_feed_empty():
    ok, _ = fd.validate_feed("")
    assert ok is False


# ── discover_feeds ─────────────────────────────────────────────────────────

def test_discover_finds_announced_feed_and_normalizes():
    html = ('<html><head><link rel="alternate" type="application/rss+xml" '
            'href="/feed.xml" title="Blog"></head></html>')
    with patch.object(fd, "_get", return_value=_FakeResp(html)):
        cands = fd.discover_feeds("exemplo.com")        # sem esquema → normaliza p/ https
    assert len(cands) == 1
    assert cands[0].url == "https://exemplo.com/feed.xml"
    assert cands[0].title == "Blog" and cands[0].kind == "rss"


def test_discover_detects_atom():
    html = '<link rel="alternate" type="application/atom+xml" href="https://x.com/atom" title="Atom">'
    with patch.object(fd, "_get", return_value=_FakeResp(html)):
        cands = fd.discover_feeds("http://exemplo.com")
    assert cands[0].kind == "atom" and cands[0].url == "https://x.com/atom"


def test_discover_empty_when_no_feeds():
    page = _FakeResp("<html><head></head></html>")

    def fake_get(url, timeout=12):
        return page   # base sem <link>; todos os caminhos comuns inválidos

    with patch.object(fd, "_get", side_effect=fake_get):
        assert fd.discover_feeds("exemplo.com") == []


def test_discover_fallback_to_common_path():
    page = _FakeResp("<html><head></head></html>")

    def fake_get(url, timeout=12):
        if url.rstrip("/").endswith("/feed"):
            return _FakeResp(_RSS)     # /feed responde como feed válido
        return page                    # base e outros caminhos: sem feed

    with patch.object(fd, "_get", side_effect=fake_get):
        cands = fd.discover_feeds("exemplo.com")
    assert any(c.url.endswith("/feed") for c in cands)
    assert cands[0].title == "Meu Blog"
