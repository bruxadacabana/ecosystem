"""
Testes para app/core/feed_fetcher.py (KOSMOS v3).

Cobre: throttle por domínio, estimativa de leitura, detecção de idioma,
inferência de tipo de artigo, normalização de entries RSS/Atom, fetch com
mock HTTP, persistência (insert, dedup, update_feed_meta, record_error) e
o pipeline fetch_and_save completo.

Todos os testes de persistência usam banco SQLite em tmp_path.
Todos os testes de fetch mockam requests.get — sem I/O real de rede.
O _domain_last_fetch é limpo antes de cada teste para isolamento do throttle.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import feedparser
import pytest

# ---------------------------------------------------------------------------
# Fixture: XML de feed para testes
# ---------------------------------------------------------------------------

RSS_2_0_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Jornal Teste</title>
    <link>https://example.com</link>
    <description>Feed de teste</description>
    <language>pt</language>
    <item>
      <title>Governo anuncia novo plano econômico</title>
      <link>https://example.com/politica/plano-economico</link>
      <description>O governo federal anunciou nesta segunda-feira um novo plano econômico que visa reduzir a inflação e gerar empregos para a população mais vulnerável do país.</description>
      <author>Maria Silva</author>
      <pubDate>Mon, 01 Jun 2026 10:00:00 +0000</pubDate>
      <category>economia</category>
      <category>política</category>
    </item>
    <item>
      <title>Opinião: A crise da educação pública</title>
      <link>https://example.com/opiniao/crise-educacao</link>
      <description>Uma reflexão sobre os problemas estruturais que afetam a educação pública e as possíveis saídas.</description>
      <author>João Santos</author>
      <pubDate>Mon, 01 Jun 2026 14:00:00 +0000</pubDate>
      <category>opinião</category>
    </item>
  </channel>
</rss>
"""

ATOM_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Tech News Feed</title>
  <link href="https://tech-example.com"/>
  <id>urn:test:tech-feed</id>
  <entry>
    <title>New AI Model Released</title>
    <link href="https://tech-example.com/ai-model-2026"/>
    <id>urn:test:ai-model-entry</id>
    <summary>Researchers have released a new open-source AI model that achieves state-of-the-art results on several benchmarks while being much more efficient than previous models.</summary>
    <updated>2026-06-01T10:00:00Z</updated>
    <author><name>Jane Doe</name></author>
    <category term="technology"/>
  </entry>
</feed>
"""

MALFORMED_XML = b"this is not xml at all <definitely broken"


# ---------------------------------------------------------------------------
# Fixtures de banco
# ---------------------------------------------------------------------------

def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _init_db_at(path: Path) -> None:
    import app.core.database as db_module
    with patch.object(db_module, "DB_PATH", path):
        db_module.init_db()


def _insert_feed(conn: sqlite3.Connection, url: str = "https://example.com/feed.rss") -> int:
    cur = conn.execute(
        "INSERT INTO feeds (url, title) VALUES (?, ?)", (url, "Test Feed")
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def db(tmp_path):
    """Banco inicializado em tmp_path com uma linha de feed inserida."""
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    feed_id = _insert_feed(conn)
    yield db_file, conn, feed_id
    conn.close()


# ---------------------------------------------------------------------------
# Fixture: isola estado de throttle entre testes
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_throttle():
    import app.core.feed_fetcher as ff
    ff._domain_last_fetch.clear()
    yield
    ff._domain_last_fetch.clear()


# ---------------------------------------------------------------------------
# TestThrottle
# ---------------------------------------------------------------------------

class TestThrottle:
    def test_first_fetch_no_wait(self):
        """Primeiro fetch de um domínio não espera."""
        import app.core.feed_fetcher as ff
        with patch("app.core.feed_fetcher.time.sleep") as mock_sleep:
            ff._throttle("https://example.com/feed")
        mock_sleep.assert_not_called()

    def test_same_domain_second_call_waits(self):
        """Segunda chamada imediata para o mesmo domínio deve dormir."""
        import app.core.feed_fetcher as ff
        # Simula que o último fetch foi agora (monotonic retorna valor alto)
        ff._domain_last_fetch["example.com"] = time.monotonic()
        with patch("app.core.feed_fetcher.time.sleep") as mock_sleep:
            ff._throttle("https://example.com/outro")
        mock_sleep.assert_called_once()
        waited = mock_sleep.call_args[0][0]
        assert 0 < waited <= ff.THROTTLE_DELAY

    def test_different_domains_no_wait(self):
        """Domínios diferentes não compartilham throttle."""
        import app.core.feed_fetcher as ff
        ff._domain_last_fetch["example.com"] = time.monotonic()
        with patch("app.core.feed_fetcher.time.sleep") as mock_sleep:
            ff._throttle("https://other-domain.com/feed")
        mock_sleep.assert_not_called()

    def test_after_delay_no_wait(self):
        """Depois do delay ter passado, nova chamada não espera."""
        import app.core.feed_fetcher as ff
        # Simula último fetch muito no passado (> THROTTLE_DELAY atrás)
        ff._domain_last_fetch["example.com"] = time.monotonic() - ff.THROTTLE_DELAY - 1
        with patch("app.core.feed_fetcher.time.sleep") as mock_sleep:
            ff._throttle("https://example.com/feed")
        mock_sleep.assert_not_called()

    def test_updates_timestamp_after_call(self):
        """Após throttle, timestamp do domínio é atualizado."""
        import app.core.feed_fetcher as ff
        before = time.monotonic()
        with patch("app.core.feed_fetcher.time.sleep"):
            ff._throttle("https://example.com/feed")
        assert ff._domain_last_fetch.get("example.com", 0) >= before


# ---------------------------------------------------------------------------
# TestEstimateReadingMin
# ---------------------------------------------------------------------------

class TestEstimateReadingMin:
    def test_200_words_is_1_min(self):
        from app.core.feed_fetcher import estimate_reading_min
        text = " ".join(["word"] * 200)
        assert estimate_reading_min(text) == 1

    def test_400_words_is_2_min(self):
        from app.core.feed_fetcher import estimate_reading_min
        text = " ".join(["word"] * 400)
        assert estimate_reading_min(text) == 2

    def test_empty_is_1_min(self):
        from app.core.feed_fetcher import estimate_reading_min
        assert estimate_reading_min("") == 1

    def test_single_word_is_1_min(self):
        from app.core.feed_fetcher import estimate_reading_min
        assert estimate_reading_min("hello") == 1

    def test_100_words_rounds_to_1(self):
        from app.core.feed_fetcher import estimate_reading_min
        text = " ".join(["word"] * 100)
        assert estimate_reading_min(text) == 1

    def test_300_words_rounds_to_2(self):
        from app.core.feed_fetcher import estimate_reading_min
        text = " ".join(["word"] * 300)
        # 300 / 200 = 1.5, round() → 2
        assert estimate_reading_min(text) == 2

    def test_strips_extra_whitespace(self):
        from app.core.feed_fetcher import estimate_reading_min
        text = "  hello   world  "
        assert estimate_reading_min(text) == 1


# ---------------------------------------------------------------------------
# TestDetectLanguage
# ---------------------------------------------------------------------------

class TestDetectLanguage:
    def test_portuguese(self):
        from app.core.feed_fetcher import detect_language
        text = "O governo federal anunciou nesta segunda-feira um novo plano para reduzir a inflação e gerar empregos para a população."
        assert detect_language(text) == "pt"

    def test_english(self):
        from app.core.feed_fetcher import detect_language
        text = "Researchers have released a new open-source model that achieves state-of-the-art results on several benchmarks."
        assert detect_language(text) == "en"

    def test_spanish(self):
        from app.core.feed_fetcher import detect_language
        text = "El gobierno ha anunciado un nuevo plan económico que busca reducir la inflación y generar empleo para los ciudadanos."
        assert detect_language(text) == "es"

    def test_french(self):
        from app.core.feed_fetcher import detect_language
        text = "Le gouvernement a annoncé un nouveau plan économique pour réduire l'inflation et créer des emplois dans le pays."
        assert detect_language(text) == "fr"

    def test_empty_returns_empty(self):
        from app.core.feed_fetcher import detect_language
        assert detect_language("") == ""

    def test_strips_html_before_analysis(self):
        from app.core.feed_fetcher import detect_language
        text = "<p>O governo federal anunciou <strong>nesta segunda-feira</strong> um novo plano para reduzir a inflação.</p>"
        assert detect_language(text) == "pt"

    def test_below_threshold_returns_empty(self):
        from app.core.feed_fetcher import detect_language
        # Texto muito curto / palavras desconhecidas — score insuficiente
        assert detect_language("xyz abc 123") == ""


# ---------------------------------------------------------------------------
# TestGuessArticleType
# ---------------------------------------------------------------------------

class TestGuessArticleType:
    def test_opinion_in_category(self):
        from app.core.feed_fetcher import guess_article_type
        assert guess_article_type("Título", ["opinião", "política"], "https://x.com") == "opinion"

    def test_opinion_in_title(self):
        from app.core.feed_fetcher import guess_article_type
        assert guess_article_type("Opinião: O futuro da democracia", [], "https://x.com") == "opinion"

    def test_opinion_in_url(self):
        from app.core.feed_fetcher import guess_article_type
        assert guess_article_type("Título", [], "https://x.com/editorial/democracia") == "opinion"

    def test_analysis_in_title(self):
        from app.core.feed_fetcher import guess_article_type
        assert guess_article_type("Análise: Por que a economia cresceu?", [], "https://x.com") == "analysis"

    def test_analysis_in_url(self):
        from app.core.feed_fetcher import guess_article_type
        assert guess_article_type("Título", [], "https://x.com/especial/investigacao") == "analysis"

    def test_default_is_news(self):
        from app.core.feed_fetcher import guess_article_type
        assert guess_article_type("Resultado do jogo ontem", ["esportes"], "https://x.com/esportes/futebol") == "news"

    def test_opinion_wins_over_analysis(self):
        """Quando os dois padrões batem, opinion tem precedência (match primeiro)."""
        from app.core.feed_fetcher import guess_article_type
        result = guess_article_type("Opinião e análise do cenário", [], "https://x.com")
        assert result == "opinion"

    def test_case_insensitive(self):
        from app.core.feed_fetcher import guess_article_type
        assert guess_article_type("EDITORIAL: reforma tributária", [], "https://x.com") == "opinion"


# ---------------------------------------------------------------------------
# TestNormalizeEntry (via feedparser real)
# ---------------------------------------------------------------------------

class TestNormalizeEntry:
    """Testa _normalize_entry via entries reais parseadas pelo feedparser."""

    def _parse_rss_entry(self, xml: str, index: int = 0) -> Any:
        return feedparser.parse(xml.encode()).entries[index]

    def test_rss_title_extracted(self):
        import app.core.feed_fetcher as ff
        entry = self._parse_rss_entry(RSS_2_0_XML, 0)
        result = ff._normalize_entry(entry, "pt")
        assert result["title"] == "Governo anuncia novo plano econômico"

    def test_rss_url_extracted(self):
        import app.core.feed_fetcher as ff
        entry = self._parse_rss_entry(RSS_2_0_XML, 0)
        result = ff._normalize_entry(entry, "pt")
        assert result["url"] == "https://example.com/politica/plano-economico"

    def test_rss_author_extracted(self):
        import app.core.feed_fetcher as ff
        entry = self._parse_rss_entry(RSS_2_0_XML, 0)
        result = ff._normalize_entry(entry, "pt")
        assert result["author"] == "Maria Silva"

    def test_rss_excerpt_extracted_and_no_html(self):
        import app.core.feed_fetcher as ff
        entry = self._parse_rss_entry(RSS_2_0_XML, 0)
        result = ff._normalize_entry(entry, "pt")
        assert result["content_excerpt"] is not None
        assert "<" not in result["content_excerpt"]

    def test_rss_published_at_iso8601(self):
        import app.core.feed_fetcher as ff
        entry = self._parse_rss_entry(RSS_2_0_XML, 0)
        result = ff._normalize_entry(entry, "pt")
        pub = result["published_at"]
        assert pub is not None
        assert "2026-06-01" in pub
        assert pub.endswith("Z")

    def test_rss_estimated_reading_positive(self):
        import app.core.feed_fetcher as ff
        entry = self._parse_rss_entry(RSS_2_0_XML, 0)
        result = ff._normalize_entry(entry, "pt")
        assert result["estimated_reading_min"] is not None
        assert result["estimated_reading_min"] >= 1

    def test_rss_opinion_type_from_category(self):
        import app.core.feed_fetcher as ff
        entry = self._parse_rss_entry(RSS_2_0_XML, 1)  # second entry has "opinião" category
        result = ff._normalize_entry(entry, "pt")
        assert result["article_type"] == "opinion"

    def test_rss_language_from_feed(self):
        import app.core.feed_fetcher as ff
        entry = self._parse_rss_entry(RSS_2_0_XML, 0)
        result = ff._normalize_entry(entry, "pt")
        assert result["language_detected"] == "pt"

    def test_atom_entry_author_from_detail(self):
        import app.core.feed_fetcher as ff
        entry = feedparser.parse(ATOM_XML.encode()).entries[0]
        result = ff._normalize_entry(entry, "")
        assert result["author"] == "Jane Doe"

    def test_atom_entry_english_detected(self):
        import app.core.feed_fetcher as ff
        entry = feedparser.parse(ATOM_XML.encode()).entries[0]
        result = ff._normalize_entry(entry, "")
        assert result["language_detected"] == "en"

    def test_atom_entry_date(self):
        import app.core.feed_fetcher as ff
        entry = feedparser.parse(ATOM_XML.encode()).entries[0]
        result = ff._normalize_entry(entry, "")
        assert result["published_at"] == "2026-06-01T10:00:00Z"

    def test_no_excerpt_reading_is_none(self):
        import app.core.feed_fetcher as ff
        no_summary_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>T</title><link>https://x.com</link>
  <item><title>Sem resumo</title><link>https://x.com/s</link></item>
</channel></rss>"""
        entry = feedparser.parse(no_summary_xml.encode()).entries[0]
        result = ff._normalize_entry(entry, "")
        assert result["content_excerpt"] is None
        assert result["estimated_reading_min"] is None

    def test_excerpt_truncated_at_2000_chars(self):
        import app.core.feed_fetcher as ff
        long_text = "palavra " * 1000  # ~8000 chars
        long_xml = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>T</title><link>https://x.com</link>
  <item><title>Longo</title><link>https://x.com/l</link>
    <description>{long_text}</description>
  </item>
</channel></rss>"""
        entry = feedparser.parse(long_xml.encode()).entries[0]
        result = ff._normalize_entry(entry, "")
        assert result["content_excerpt"] is not None
        assert len(result["content_excerpt"]) <= 2000


# ---------------------------------------------------------------------------
# TestFetchFeed (requests mockado)
# ---------------------------------------------------------------------------

def _make_mock_response(content: bytes, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.status_code = status_code
    if status_code >= 400:
        resp.raise_for_status.side_effect = __import__("requests").HTTPError(
            response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


class TestFetchFeed:
    @patch("app.core.feed_fetcher.requests.get")
    def test_rss_returns_correct_entry_count(self, mock_get):
        mock_get.return_value = _make_mock_response(RSS_2_0_XML.encode())
        from app.core.feed_fetcher import fetch_feed
        _, entries = fetch_feed("https://example.com/feed.rss")
        assert len(entries) == 2

    @patch("app.core.feed_fetcher.requests.get")
    def test_atom_returns_correct_entry_count(self, mock_get):
        mock_get.return_value = _make_mock_response(ATOM_XML.encode())
        from app.core.feed_fetcher import fetch_feed
        _, entries = fetch_feed("https://tech-example.com/feed.atom")
        assert len(entries) == 1

    @patch("app.core.feed_fetcher.requests.get")
    def test_feed_obj_has_title(self, mock_get):
        mock_get.return_value = _make_mock_response(RSS_2_0_XML.encode())
        from app.core.feed_fetcher import fetch_feed
        feed_obj, _ = fetch_feed("https://example.com/feed.rss")
        assert feed_obj.title == "Jornal Teste"

    @patch("app.core.feed_fetcher.requests.get")
    def test_network_error_raises(self, mock_get):
        import requests as req
        mock_get.side_effect = req.ConnectionError("timeout")
        from app.core.feed_fetcher import fetch_feed
        with pytest.raises(req.RequestException):
            fetch_feed("https://example.com/feed.rss")

    @patch("app.core.feed_fetcher.requests.get")
    def test_http_error_raises(self, mock_get):
        mock_get.return_value = _make_mock_response(b"", status_code=404)
        from app.core.feed_fetcher import fetch_feed
        import requests as req
        with pytest.raises(req.RequestException):
            fetch_feed("https://example.com/feed.rss")

    @patch("app.core.feed_fetcher.requests.get")
    def test_invalid_feed_raises_value_error(self, mock_get):
        mock_get.return_value = _make_mock_response(MALFORMED_XML)
        from app.core.feed_fetcher import fetch_feed
        with pytest.raises(ValueError):
            fetch_feed("https://example.com/feed.rss")

    @patch("app.core.feed_fetcher.requests.get")
    def test_entries_have_required_fields(self, mock_get):
        mock_get.return_value = _make_mock_response(RSS_2_0_XML.encode())
        from app.core.feed_fetcher import fetch_feed
        _, entries = fetch_feed("https://example.com/feed.rss")
        for entry in entries:
            assert "title" in entry
            assert "url" in entry
            assert "article_type" in entry

    @patch("app.core.feed_fetcher.requests.get")
    def test_throttle_called_with_url(self, mock_get):
        """fetch_feed deve chamar _throttle antes do requests.get."""
        mock_get.return_value = _make_mock_response(RSS_2_0_XML.encode())
        import app.core.feed_fetcher as ff
        with patch.object(ff, "_throttle") as mock_throttle:
            ff.fetch_feed("https://example.com/feed.rss")
        mock_throttle.assert_called_once_with("https://example.com/feed.rss")


# ---------------------------------------------------------------------------
# TestSaveNewArticles
# ---------------------------------------------------------------------------

class TestSaveNewArticles:
    def test_inserts_new_articles(self, db):
        _, conn, feed_id = db
        from app.core.feed_fetcher import save_new_articles
        entries = [
            {"title": "A", "url": "https://x.com/a", "article_type": "news",
             "author": None, "content_excerpt": None, "published_at": None,
             "estimated_reading_min": None, "language_detected": None},
            {"title": "B", "url": "https://x.com/b", "article_type": "news",
             "author": None, "content_excerpt": None, "published_at": None,
             "estimated_reading_min": None, "language_detected": None},
        ]
        count = save_new_articles(feed_id, entries, conn)
        assert count == 2

    def test_ignores_duplicate_url(self, db):
        _, conn, feed_id = db
        from app.core.feed_fetcher import save_new_articles
        entry = {"title": "X", "url": "https://x.com/dup", "article_type": "news",
                 "author": None, "content_excerpt": None, "published_at": None,
                 "estimated_reading_min": None, "language_detected": None}
        first  = save_new_articles(feed_id, [entry], conn)
        second = save_new_articles(feed_id, [entry], conn)
        assert first == 1
        assert second == 0

    def test_skips_entry_without_url(self, db):
        _, conn, feed_id = db
        from app.core.feed_fetcher import save_new_articles
        entries = [{"title": "No URL", "url": "", "article_type": "news",
                    "author": None, "content_excerpt": None, "published_at": None,
                    "estimated_reading_min": None, "language_detected": None}]
        count = save_new_articles(feed_id, entries, conn)
        assert count == 0

    def test_skips_entry_without_title(self, db):
        _, conn, feed_id = db
        from app.core.feed_fetcher import save_new_articles
        entries = [{"title": "", "url": "https://x.com/notitle", "article_type": "news",
                    "author": None, "content_excerpt": None, "published_at": None,
                    "estimated_reading_min": None, "language_detected": None}]
        count = save_new_articles(feed_id, entries, conn)
        assert count == 0

    def test_all_metadata_fields_saved(self, db):
        _, conn, feed_id = db
        from app.core.feed_fetcher import save_new_articles
        entry = {
            "title":                 "Artigo completo",
            "url":                   "https://x.com/completo",
            "author":                "Autor Teste",
            "content_excerpt":       "Resumo do artigo.",
            "published_at":          "2026-06-01T10:00:00Z",
            "estimated_reading_min": 3,
            "article_type":          "opinion",
            "language_detected":     "pt",
        }
        save_new_articles(feed_id, [entry], conn)
        row = conn.execute(
            "SELECT * FROM articles WHERE url = ?", ("https://x.com/completo",)
        ).fetchone()
        assert row["author"] == "Autor Teste"
        assert row["content_excerpt"] == "Resumo do artigo."
        assert row["published_at"] == "2026-06-01T10:00:00Z"
        assert row["estimated_reading_min"] == 3
        assert row["article_type"] == "opinion"
        assert row["language_detected"] == "pt"

    def test_returns_correct_count_mixed(self, db):
        _, conn, feed_id = db
        from app.core.feed_fetcher import save_new_articles
        entries = [
            {"title": "N", "url": "https://x.com/new", "article_type": "news",
             "author": None, "content_excerpt": None, "published_at": None,
             "estimated_reading_min": None, "language_detected": None},
        ]
        save_new_articles(feed_id, entries, conn)
        # Insert same + new
        more = entries + [
            {"title": "M", "url": "https://x.com/more", "article_type": "news",
             "author": None, "content_excerpt": None, "published_at": None,
             "estimated_reading_min": None, "language_detected": None},
        ]
        count = save_new_articles(feed_id, more, conn)
        assert count == 1  # só o novo


# ---------------------------------------------------------------------------
# TestUpdateFeedMeta
# ---------------------------------------------------------------------------

class TestUpdateFeedMeta:
    def _make_feed_obj(self, title: str = "Novo Título", link: str = "https://site.com") -> Any:
        """Cria objeto simples imitando feedparser FeedParserDict.feed."""
        class FakeFeed:
            pass
        f = FakeFeed()
        f.title = title
        f.link  = link
        return f

    def test_updates_title_and_site_url(self, db):
        _, conn, feed_id = db
        from app.core.feed_fetcher import update_feed_meta
        feed_obj = self._make_feed_obj("Feed Atualizado", "https://newsite.com")
        update_feed_meta(feed_id, feed_obj, conn)
        row = conn.execute("SELECT title, site_url FROM feeds WHERE id = ?", (feed_id,)).fetchone()
        assert row["title"] == "Feed Atualizado"
        assert row["site_url"] == "https://newsite.com"

    def test_updates_last_fetched_at(self, db):
        _, conn, feed_id = db
        from app.core.feed_fetcher import update_feed_meta
        feed_obj = self._make_feed_obj()
        update_feed_meta(feed_id, feed_obj, conn)
        row = conn.execute("SELECT last_fetched_at FROM feeds WHERE id = ?", (feed_id,)).fetchone()
        assert row["last_fetched_at"] is not None

    def test_resets_error_count_and_last_error(self, db):
        _, conn, feed_id = db
        conn.execute("UPDATE feeds SET error_count=3, last_error='err' WHERE id=?", (feed_id,))
        conn.commit()
        from app.core.feed_fetcher import update_feed_meta
        update_feed_meta(feed_id, self._make_feed_obj(), conn)
        row = conn.execute("SELECT error_count, last_error FROM feeds WHERE id=?", (feed_id,)).fetchone()
        assert row["error_count"] == 0
        assert row["last_error"] is None

    def test_does_not_overwrite_existing_title_with_none(self, db):
        _, conn, feed_id = db
        conn.execute("UPDATE feeds SET title='Título Original' WHERE id=?", (feed_id,))
        conn.commit()

        class NoTitleFeed:
            title = ""
            link  = ""
        from app.core.feed_fetcher import update_feed_meta
        update_feed_meta(feed_id, NoTitleFeed(), conn)
        row = conn.execute("SELECT title FROM feeds WHERE id=?", (feed_id,)).fetchone()
        assert row["title"] == "Título Original"


# ---------------------------------------------------------------------------
# TestRecordFeedError
# ---------------------------------------------------------------------------

class TestRecordFeedError:
    def test_increments_error_count(self, db):
        _, conn, feed_id = db
        from app.core.feed_fetcher import record_feed_error
        record_feed_error(feed_id, "timeout", conn)
        record_feed_error(feed_id, "timeout", conn)
        row = conn.execute("SELECT error_count FROM feeds WHERE id=?", (feed_id,)).fetchone()
        assert row["error_count"] == 2

    def test_saves_error_message(self, db):
        _, conn, feed_id = db
        from app.core.feed_fetcher import record_feed_error
        record_feed_error(feed_id, "HTTP 404 Not Found", conn)
        row = conn.execute("SELECT last_error FROM feeds WHERE id=?", (feed_id,)).fetchone()
        assert row["last_error"] == "HTTP 404 Not Found"

    def test_truncates_long_error_message(self, db):
        _, conn, feed_id = db
        from app.core.feed_fetcher import record_feed_error
        long_msg = "x" * 1000
        record_feed_error(feed_id, long_msg, conn)
        row = conn.execute("SELECT last_error FROM feeds WHERE id=?", (feed_id,)).fetchone()
        assert len(row["last_error"]) <= 500


# ---------------------------------------------------------------------------
# TestFetchAndSave (pipeline completo)
# ---------------------------------------------------------------------------

class TestFetchAndSave:
    @patch("app.core.feed_fetcher.requests.get")
    def test_success_returns_inserted_count(self, mock_get, db):
        db_file, conn, feed_id = db
        mock_get.return_value = _make_mock_response(RSS_2_0_XML.encode())
        import app.core.feed_fetcher as ff
        import app.core.database as db_module
        conn.close()  # fetch_and_save abre sua própria conn
        with patch.object(db_module, "DB_PATH", db_file):
            count = ff.fetch_and_save(feed_id, "https://example.com/feed.rss")
        assert count == 2

    @patch("app.core.feed_fetcher.requests.get")
    def test_network_error_records_and_returns_minus_one(self, mock_get, db):
        db_file, conn, feed_id = db
        import requests as req
        mock_get.side_effect = req.ConnectionError("timeout")
        import app.core.feed_fetcher as ff
        import app.core.database as db_module
        with patch.object(db_module, "DB_PATH", db_file):
            result = ff.fetch_and_save(feed_id, "https://example.com/feed.rss")
        assert result == -1
        row = conn.execute("SELECT error_count FROM feeds WHERE id=?", (feed_id,)).fetchone()
        assert row["error_count"] >= 1

    @patch("app.core.feed_fetcher.requests.get")
    def test_invalid_feed_records_and_returns_minus_one(self, mock_get, db):
        db_file, conn, feed_id = db
        mock_get.return_value = _make_mock_response(MALFORMED_XML)
        import app.core.feed_fetcher as ff
        import app.core.database as db_module
        with patch.object(db_module, "DB_PATH", db_file):
            result = ff.fetch_and_save(feed_id, "https://example.com/feed.rss")
        assert result == -1
        row = conn.execute("SELECT error_count FROM feeds WHERE id=?", (feed_id,)).fetchone()
        assert row["error_count"] >= 1

    @patch("app.core.feed_fetcher.requests.get")
    def test_idempotent_second_run_inserts_zero(self, mock_get, db):
        """Rodar fetch_and_save duas vezes no mesmo feed deve inserir 0 na segunda."""
        db_file, conn, feed_id = db
        mock_get.return_value = _make_mock_response(RSS_2_0_XML.encode())
        import app.core.feed_fetcher as ff
        import app.core.database as db_module
        conn.close()
        with patch.object(db_module, "DB_PATH", db_file):
            ff.fetch_and_save(feed_id, "https://example.com/feed.rss")
            mock_get.return_value = _make_mock_response(RSS_2_0_XML.encode())
            count = ff.fetch_and_save(feed_id, "https://example.com/feed.rss")
        assert count == 0

    @patch("app.core.feed_fetcher.requests.get")
    def test_feed_meta_updated_on_success(self, mock_get, db):
        """Após fetch bem-sucedido, o feed deve ter last_fetched_at preenchido."""
        db_file, conn, feed_id = db
        mock_get.return_value = _make_mock_response(RSS_2_0_XML.encode())
        import app.core.feed_fetcher as ff
        import app.core.database as db_module
        with patch.object(db_module, "DB_PATH", db_file):
            ff.fetch_and_save(feed_id, "https://example.com/feed.rss")
        row = conn.execute(
            "SELECT last_fetched_at, title FROM feeds WHERE id=?", (feed_id,)
        ).fetchone()
        assert row["last_fetched_at"] is not None
        assert row["title"] == "Jornal Teste"  # atualizado pelo feed XML
