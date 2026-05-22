"""
AKASHA — Personalized PageRank sobre o grafo local de links.

Pipeline:
  1. extract_links()     — extrai hrefs de HTML (sem rede), normaliza URLs
  2. store_page_links()  — grava arestas source→target em page_links
  3. compute_pagerank()  — job semanal: lê page_links, calcula PPR via networkx
                           (ou power-iteration manual), normaliza para 0.8–1.2,
                           grava em page_rank
  4. get_page_rank_scores() — lookup em lote, padrão 1.0 para URLs desconhecidas
"""
from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

if TYPE_CHECKING:
    import aiosqlite

log = logging.getLogger("akasha.pagerank")

# ---------------------------------------------------------------------------
# Extração de links de HTML (pura, sem I/O)
# ---------------------------------------------------------------------------

_SKIP_SCHEMES = re.compile(r"^(mailto|javascript|data|tel|ftp):", re.IGNORECASE)


def extract_links(html: str, base_url: str, known_domains: frozenset[str] | None = None) -> list[str]:
    """Extrai hrefs de <a> tags de HTML e normaliza como URLs absolutas.

    known_domains: se fornecido, retorna apenas links cujo netloc está no conjunto.
    Exclui fragmentos puros (#), links de esquemas não-HTTP e URLs inválidas.
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        log.debug("extract_links: BeautifulSoup error: %s", exc)
        return []

    seen: set[str] = set()
    results: list[str] = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#"):
            continue
        if _SKIP_SCHEMES.match(href):
            continue

        url = urljoin(base_url, href)
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            continue

        # Normaliza: remove fragmento, canonicaliza trailing slash
        clean = parsed._replace(fragment="").geturl().rstrip("/")
        if not clean or clean in seen:
            continue

        if known_domains is not None and parsed.netloc not in known_domains:
            continue

        # Exclui self-links (URL igual à base normalizada)
        base_clean = base_url.rstrip("/").split("#")[0]
        if clean == base_clean:
            continue

        seen.add(clean)
        results.append(clean)

    return results


# ---------------------------------------------------------------------------
# Persistência de arestas no DB
# ---------------------------------------------------------------------------

async def store_page_links(
    db: "aiosqlite.Connection",
    source_url: str,
    target_urls: list[str],
) -> None:
    """Grava arestas source → target em page_links (sem commit — caller responsável)."""
    if not target_urls:
        return
    source = source_url.rstrip("/")
    await db.executemany(
        "INSERT OR IGNORE INTO page_links (source_url, target_url) VALUES (?, ?)",
        [(source, t) for t in target_urls if t != source],
    )


# ---------------------------------------------------------------------------
# Cálculo de Personalized PageRank
# ---------------------------------------------------------------------------

def _power_iteration(
    graph: dict[str, list[str]],
    all_nodes: list[str],
    personalization: dict[str, float],
    damping: float,
    iterations: int,
) -> dict[str, float]:
    """PageRank por power-iteration manual (fallback sem networkx)."""
    n = len(all_nodes)
    if n == 0:
        return {}
    idx = {url: i for i, url in enumerate(all_nodes)}
    rank = {url: 1.0 / n for url in all_nodes}
    total_pers = sum(personalization.values()) or 1.0
    pers = {url: personalization.get(url, 0.0) / total_pers for url in all_nodes}

    for _ in range(iterations):
        new_rank: dict[str, float] = {url: 0.0 for url in all_nodes}
        for src, targets in graph.items():
            if not targets:
                # dangling node: distribui para todos
                share = rank[src] / n
                for url in all_nodes:
                    new_rank[url] += share
            else:
                share = rank[src] / len(targets)
                for tgt in targets:
                    if tgt in new_rank:
                        new_rank[tgt] += share
        rank = {
            url: damping * new_rank[url] + (1.0 - damping) * pers[url]
            for url in all_nodes
        }
    return rank


async def compute_pagerank(
    db: "aiosqlite.Connection",
    iterations: int = 20,
    damping: float = 0.85,
) -> int:
    """Calcula Personalized PageRank e grava os scores em page_rank.

    Seeds de personalização: top-10 domínios de domain_boosts (tabela criada no
    item de log de cliques). Se a tabela não existir ainda, usa PageRank uniforme.
    Scores normalizados para 0.8–1.2 (padrão 1.0 para URLs sem dado).
    Retorna número de URLs com score calculado.
    """
    # Carrega todas as arestas da tabela page_links
    rows = await (await db.execute(
        "SELECT source_url, target_url FROM page_links"
    )).fetchall()
    if not rows:
        log.debug("compute_pagerank: page_links vazia, nada a calcular")
        return 0

    # Constrói grafo em memória
    graph: dict[str, list[str]] = {}
    all_nodes_set: set[str] = set()
    for src, tgt in rows:
        all_nodes_set.add(src)
        all_nodes_set.add(tgt)
        if src not in graph:
            graph[src] = []
        graph[src].append(tgt)
    # Nós destino sem saída ficam como dangling nodes
    for node in all_nodes_set:
        graph.setdefault(node, [])

    all_nodes = list(all_nodes_set)

    # Sementes de personalização (domínios com maior boost de cliques)
    personalization: dict[str, float] = {}
    try:
        seed_rows = await (await db.execute(
            """SELECT domain, boost FROM domain_boosts
               ORDER BY boost DESC LIMIT 10"""
        )).fetchall()
        if seed_rows:
            # Distribui peso de personalização para todas as URLs cujo domínio é semente
            seed_domains = {row[0]: row[1] for row in seed_rows}
            for url in all_nodes:
                netloc = urlparse(url).netloc
                if netloc in seed_domains:
                    personalization[url] = seed_domains[netloc]
    except Exception:
        pass  # tabela domain_boosts ainda não existe

    if not personalization:
        # Sem seeds: PageRank uniforme (equivalente ao clássico)
        personalization = {url: 1.0 for url in all_nodes}

    # Calcula PageRank
    try:
        import networkx as nx
        G = nx.DiGraph()
        G.add_nodes_from(all_nodes)
        for src, targets in graph.items():
            for tgt in targets:
                G.add_edge(src, tgt)
        total_pers = sum(personalization.values())
        pers_norm = {url: v / total_pers for url, v in personalization.items()}
        try:
            scores = nx.pagerank(
                G,
                alpha=damping,
                personalization=pers_norm,
                max_iter=max(iterations, 100),
                tol=1e-4,
            )
        except nx.PowerIterationFailedConvergence:
            log.debug("networkx não convergiu, usando power-iteration manual")
            scores = _power_iteration(graph, all_nodes, personalization, damping, max(iterations, 50))
    except ImportError:
        log.debug("networkx não disponível, usando power-iteration manual")
        scores = _power_iteration(graph, all_nodes, personalization, damping, iterations)
    except Exception as exc:
        log.warning("compute_pagerank error: %s", exc)
        return 0

    if not scores:
        return 0

    # Normaliza para 0.8–1.2
    min_s = min(scores.values())
    max_s = max(scores.values())
    span = max_s - min_s
    if span > 0:
        normalized = {
            url: 0.8 + 0.4 * (s - min_s) / span
            for url, s in scores.items()
        }
    else:
        normalized = {url: 1.0 for url in scores}

    # Grava no DB
    now = int(time.time())
    await db.executemany(
        "INSERT OR REPLACE INTO page_rank (url, score, updated_at) VALUES (?, ?, ?)",
        [(url, score, now) for url, score in normalized.items()],
    )
    log.info("compute_pagerank: %d URLs com score calculado", len(normalized))
    return len(normalized)


# ---------------------------------------------------------------------------
# Lookup de scores (pipeline de busca)
# ---------------------------------------------------------------------------

async def get_page_rank_scores(
    db: "aiosqlite.Connection",
    urls: list[str],
) -> dict[str, float]:
    """Retorna scores de PageRank para uma lista de URLs.

    URLs sem entrada em page_rank recebem score padrão 1.0.
    """
    if not urls:
        return {}
    placeholders = ",".join("?" * len(urls))
    rows = await (await db.execute(
        f"SELECT url, score FROM page_rank WHERE url IN ({placeholders})",
        [u.rstrip("/") for u in urls],
    )).fetchall()
    result = {url: 1.0 for url in urls}
    for url, score in rows:
        result[url] = score
    return result
