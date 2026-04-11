"""Semeia feeds padrão internacionais na primeira execução do KOSMOS."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.feed_manager import FeedManager

log = logging.getLogger("kosmos.seeder")

# ---------------------------------------------------------------------------
# Catálogo de feeds padrão organizados por continente / tema
# Formato: (nome, url, feed_type)
# ---------------------------------------------------------------------------
_DEFAULT_FEEDS: dict[str, list[tuple[str, str, str]]] = {
    "Américas": [
        ("BBC News Brasil",       "https://feeds.bbci.co.uk/portuguese/rss.xml",                          "rss"),
        ("NPR World News",        "https://feeds.npr.org/1004/rss.xml",                                   "rss"),
        ("AP News",               "https://apnews.com/hub/world-news/feed",                               "rss"),
        ("Folha de S.Paulo",      "https://feeds.folha.uol.com.br/mundo/rss091.xml",                      "rss"),
        ("La Nación (Argentina)", "https://www.lanacion.com.ar/arc/outboundfeeds/rss/",                   "rss"),
    ],
    "Europa": [
        ("BBC News World",        "http://feeds.bbci.co.uk/news/world/rss.xml",                           "rss"),
        ("The Guardian World",    "https://www.theguardian.com/world/rss",                                "rss"),
        ("Deutsche Welle",        "https://rss.dw.com/rdf/rss-en-all",                                   "rss"),
        ("Le Monde",              "https://www.lemonde.fr/rss/une.xml",                                   "rss"),
        ("El País",               "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",     "rss"),
    ],
    "Ásia & Oriente Médio": [
        ("Al Jazeera English",    "https://www.aljazeera.com/xml/rss/all.xml",                            "rss"),
        ("NHK World",             "https://www3.nhk.or.jp/rss/news/cat0.xml",                             "rss"),
        ("The Hindu",             "https://www.thehindu.com/news/international/feeder/default.rss",        "rss"),
        ("Haaretz",               "https://www.haaretz.com/cmlink/1.628764",                              "rss"),
    ],
    "África": [
        ("Daily Maverick",        "https://www.dailymaverick.co.za/feed/",                                "rss"),
        ("The East African",      "https://www.theeastafrican.co.ke/tea/rss",                             "rss"),
        ("Jeune Afrique",         "https://www.jeuneafrique.com/feed/",                                   "rss"),
    ],
    "Oceania": [
        ("ABC News Australia",    "https://www.abc.net.au/news/feed/51120/rss.xml",                       "rss"),
        ("NZ Herald",             "https://www.nzherald.co.nz/arc/outboundfeeds/rss/section/world/",      "rss"),
    ],
    "Ciência & Tecnologia": [
        ("Hacker News",           "https://news.ycombinator.com/rss",                                     "rss"),
        ("Ars Technica",          "https://feeds.arstechnica.com/arstechnica/index",                      "rss"),
        ("The Verge",             "https://www.theverge.com/rss/index.xml",                               "rss"),
        ("Nature News",           "https://www.nature.com/nature.rss",                                    "rss"),
        ("Science Daily",         "https://www.sciencedaily.com/rss/top/science.xml",                     "rss"),
    ],
}


def seed_default_feeds(fm: "FeedManager") -> None:
    """Adiciona feeds padrão ao banco se ainda não houver nenhum feed.

    Idempotente — não faz nada se já existem feeds cadastrados.
    """
    existing = fm.get_feeds()
    if existing:
        log.debug("Banco já contém %d feed(s) — seed ignorado.", len(existing))
        return

    log.info("Primeiro uso detectado — adicionando feeds padrão internacionais.")
    total = 0

    for category_name, feeds in _DEFAULT_FEEDS.items():
        try:
            cat = fm.add_category(category_name)
        except Exception as exc:
            log.warning("Erro ao criar categoria %r: %s", category_name, exc)
            continue

        for name, url, feed_type in feeds:
            try:
                fm.add_feed(url=url, name=name, feed_type=feed_type, category_id=cat.id)
                total += 1
            except Exception as exc:
                log.warning("Erro ao adicionar feed %r: %s", name, exc)

    log.info("Seed concluído: %d feed(s) adicionados em %d categorias.", total, len(_DEFAULT_FEEDS))
