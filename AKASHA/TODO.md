# AKASHA — TODO

> Criado: 2026-04-15

Buscador pessoal local. Agrega resultados da web e do ecossistema numa interface única,
com downloads genéricos e integração com qBittorrent.
Stack: FastAPI + HTMX + Jinja2 + SQLite (aiosqlite) + uv · Porta 7071.

---

## ⚠ Padrões Obrigatórios

- **Tipagem completa:** Pydantic `BaseModel` em todas as rotas; `-> tipo` em todas as funções
- **Erros explícitos:** `HTTPException` com status code em todos os caminhos de erro
- **I/O nunca silencioso** fora do bloco de integração com `ecosystem.json`
- **`uv` obrigatório:** `pyproject.toml`, nunca `requirements.txt`
- **Commits por item:** um commit git a cada item concluído
- **Atualizar este TODO** antes de implementar qualquer feature não listada
- **SQLite versionado:** tabela `settings` com campo `schema_version`; migrations numeradas
- **HTMX:** todo estado mutável via `hx-swap`; todo ação tem feedback visual (spinner ou toast)

---

## Fase 1 — Fundação

> Entrega: servidor sobe na porta 7070, design system completo, página de busca vazia funcional.

- [x] `pyproject.toml` — dependências uv: `fastapi`, `uvicorn[standard]`, `aiosqlite`, `httpx`,
      `jinja2`, `python-multipart`, `duckduckgo-search`, `qbittorrent-api`, `trafilatura`
- [x] `main.py` — FastAPI app + lifespan: inicializa DB, escreve `akasha.base_url`
      em `ecosystem.json` no startup (try/except — nunca bloquear)
- [x] `config.py` — lê `ecosystem.json` via `ecosystem_client`; expõe `kosmos_archive`,
      `aether_vault`, `mnemosyne_indices`, `qbt_host`, `qbt_port`; fallback silencioso
- [x] `database.py` — schema SQLite + migrations: tabelas `searches`, `downloads`, `settings`
      (campo `schema_version`); função `init_db()` chamada no startup
- [x] `static/style.css` — paleta CSS completa (sépia diurna + noturno astronômico via
      `prefers-color-scheme: dark`), tipografia (IM Fell English · Special Elite · Courier Prime),
      componentes: `.btn`, `.btn-ghost`, `.card`, `.input`, `.tag`, `.badge`, `.toast`
- [x] `templates/base.html` — layout base: topbar (AKASHA itálico 24px, toggle ☽/☀),
      search bar com HTMX (`hx-get="/search" hx-trigger="submit"`), nav tabs (Busca / Downloads / Torrents)
- [x] `templates/search.html` — extends base: área de resultados com skeleton loader,
      empty state com buscas recentes
- [x] `iniciar.sh` — detecta `.venv` do ecossistema em `../`; se não existir, cria venv local;
      `uv sync` e executa `uv run python main.py`; `chmod +x`

---

## Fase 2 — Busca Web

> Entrega: busca DuckDuckGo funcional com resultados em cards e histórico persistido.

- [x] `services/web_search.py` — DuckDuckGo via `duckduckgo-search`; cache em SQLite (TTL 1h);
      deduplicação por URL normalizada; retorna `list[SearchResult]` (Pydantic)
- [x] `routers/search.py` — `GET /search?q=&sources=web` → renderiza `search.html` com resultados;
      salva query + timestamp em `searches`
- [x] `templates/search.html` — cards de resultado: título linkado, snippet, badge de fonte,
      data; HTMX `hx-get` no form com indicador de loading
- [x] Widget "Buscas recentes" no empty state: lista das últimas 10 queries da tabela `searches`
- [x] Filtro de fonte no UI: radio/toggle Web / Local / Todos (query param `sources=`)
- [x] Botão "Carregar mais" abaixo dos cards de resultado: busca a próxima página via `offset`
      do DuckDuckGo e acrescenta os cards ao final (HTMX `hx-swap="beforeend"`)

---

## Fase 3 — Busca Local

> Entrega: busca nos arquivos do ecossistema integrada com os resultados web.

- [x] `services/local_search.py` — ler KOSMOS archive (`{archive_path}/**/*.md`):
      parsear frontmatter YAML simples, indexar título + corpo em FTS5
- [x] `services/local_search.py` — ler AETHER vault (`{vault_path}/*/chapters/*.md`):
      título e conteúdo dos capítulos; indexar em FTS5
- [x] FTS5 virtual table `local_index` em SQLite: schema `(path, title, body, source, mtime)`
- [x] Reindexação automática no startup se `mtime` dos arquivos mudou desde última indexação
- [x] `services/local_search.py` — query ChromaDB do Mnemosyne se `mnemosyne_indices`
      não vazio (import opcional; graceful fallback se `chromadb` não instalado)
- [x] Badge de fonte em cada card: `WEB` · `KOSMOS` · `AETHER` · `MNEMOSYNE` com cor distinta
- [x] **Correção:** `routers/search.py` — retornar `web_results` e `local_results` separados no contexto
- [x] **Correção:** `templates/search.html` — seções separadas quando `sources=all`: "Resultados web" + "No meu ecossistema"

---

## Fase 4 — Downloads

> Entrega: baixar arquivos genéricos com progresso em tempo real via SSE.

- [ ] `services/downloader.py` — download async via `httpx` com streaming; calcula progresso
      por `Content-Length`; salva em diretório configurável; retorna `DownloadInfo` (Pydantic)
- [ ] `routers/downloads.py` — `POST /download` (body: `{url, dest_dir}`): inicia download
      em background task, retorna `download_id`
- [ ] `routers/downloads.py` — `GET /downloads/progress/{id}` (SSE): emite
      `data: {percent, speed_kbps, eta_s, status}` até concluir ou falhar
- [ ] `routers/downloads.py` — `GET /downloads` — fila ativa + histórico (paginado, 20/página)
- [ ] Migration: tabela `downloads` — id, url, filename, dest_dir, size_bytes,
      downloaded_bytes, status (`queued`/`active`/`done`/`error`), started_at, finished_at
- [ ] `templates/downloads.html` — aba Downloads: barras de progresso com HTMX SSE
      (`hx-ext="sse"`), histórico colapsável; botão cancelar
- [ ] Botão "↓ Baixar" nos cards de resultado de busca (HTMX `hx-post="/download"`)

---

## Fase 5 — Arquivação Web

> Entrega: salvar qualquer página como `.md` no formato KOSMOS direto da busca.

- [x] `services/archiver.py` — fetch via `httpx`, extração com `trafilatura`; frontmatter
      KOSMOS estendido: `title`, `source`, `date`, `author`, `url` + `language` (auto),
      `word_count` (auto), `tags` (lista), `notes` (texto livre);
      salva em `{archive_path}/Web/{YYYY-MM-DD}_{slug}.md`; slug max 60 chars
- [x] `routers/search.py` — `POST /archive` (body form: `url`, `tags?`, `notes?`):
      chama archiver, retorna 200 OK ou 400 se `kosmos_archive` não configurado
- [x] Botão "arquivar" em cada card de resultado `WEB` (HTMX `hx-post`, toast de confirmação)
- [x] Fallback: se `kosmos_archive` não configurado, retornar erro 400 com mensagem clara
      orientando a configurar o caminho em `/settings`
- [x] **Melhorar extração de conteúdo:** cascata de extratores em `services/archiver.py`;
      HTML baixado uma vez, primeiro a retornar ≥ 100 palavras vence; fallback = mais longo.
      Cascata implementada (newspaper4k e readability-lxml opcionais — lxml 6.x não tem wheel
      para Python 3.14 no PyPI, mas o import é silenciado):
        1. `newspaper4k`     — opcional (ImportError silenciado)
        2. `trafilatura`     — markdown nativo, instalado
        3. `readability-lxml`— opcional (ImportError silenciado)
        4. `inscriptis`      — texto estruturado, instalado
        5. `BeautifulSoup`   — fallback html.parser + markdownify, instalado

---

## Fase 6 — qBittorrent

> Entrega: gerenciar torrents locais direto da interface.

- [ ] `services/qbt_client.py` — wrapper `qbittorrent-api`: `list_torrents() -> list[TorrentInfo]`,
      `add_magnet(url: str) -> None`, `add_file(data: bytes) -> None`; raises `QbtOfflineError`
      se inacessível
- [ ] `routers/qbittorrent.py` — `GET /torrents` → lista ativa (nome, progresso %, velocidade,
      ETA, estado); renderiza fragmento HTMX para polling
- [ ] `routers/qbittorrent.py` — `POST /torrents/add` — aceita magnet link (form field)
      ou upload de arquivo `.torrent` (`multipart/form-data`)
- [ ] `templates/downloads.html` — aba "Torrents": tabela com polling a cada 5s
      (`hx-trigger="every 5s" hx-get="/torrents"`)
- [ ] Configuração em `/settings`: `qbt_host` e `qbt_port` (defaults: `localhost`, `8080`);
      salvos em `settings` SQLite
- [ ] Banner "qBittorrent offline" quando `QbtOfflineError` — sem quebrar o resto da página

---

## Fase 7 — Biblioteca de URLs

> Entrega: biblioteca pessoal de sites com scraping periódico e versionamento por diff.

- [x] Migration v5: tabelas `library_urls` (url, title, snippet, content_md, content_hash,
      language, word_count, tags_json, notes, check_interval_days, last_checked_at, status)
      + `library_diffs` (url_id, diff_text, scraped_at) + FTS5 `library_fts`
- [x] `services/library.py` — `add_url()`, `scrape_and_store()` (trafilatura + metadados:
      language, word_count); `check_overdue()`; `compute_diff()` via `difflib.unified_diff()`
- [x] `routers/library.py` — `GET /library?tag=&lang=`; `POST /library/add`
      (body: `{url, interval_days, tags?, notes?}`); `PATCH /library/{id}`;
      `POST /library/refresh/{id}`; `DELETE /library/{id}`
- [x] `templates/library.html` — cards com título, snippet, idioma, contagem de palavras,
      tags, data do último scrape, badge de intervalo, campo de notas inline (HTMX `hx-patch`),
      badge "mudou" se diff recente; filtro por tag e idioma no topo
- [x] Background task no lifespan: acorda a cada hora, re-scrape URLs vencidas silenciosamente
- [x] Busca local `/search?sources=local` inclui conteúdo da `library_fts`
- [x] Botão `+` em cada card de resultado `WEB`: enfileira URL na biblioteca via `POST /library/add-quick`
      (sem scrape imediato — status='pending', loop horário faz o scrape); toast de confirmação

---

## Fase 7.5 — Lista negra de domínios

> Entrega: domínios bloqueados nunca aparecem nos resultados de busca web.

- [x] Migration v6: tabela `blocked_domains` — `id, domain, added_at`
- [x] `services/web_search.py` — filtrar resultados excluindo domínios em `blocked_domains`
      (hostname normalizado sem `www.`); aplicado antes de retornar ao router
- [x] Botão `−` em cada card de resultado `WEB`: `POST /domains/block`, toast de confirmação
- [x] `routers/domains.py` — `POST /domains/block` (extrai domínio da URL);
      `DELETE /domains/block/{domain}` (desbloquear)
- [ ] `templates/settings.html` — seção "Domínios bloqueados": lista com botão desbloquear

---

## Fase 8 — Histórico unificado

> Entrega: página `/history` com timeline de todas as atividades.

- [ ] Migration v4: tabela `activity_log` (`id, type, title, url, meta_json, created_at`)
      onde `type` ∈ `search|archive|download`
- [ ] `routers/history.py` — `GET /history?type=all|search|archive|download&page=1`
      paginado por data desc
- [ ] `templates/history.html` — timeline agrupada por data; ícone por tipo;
      filtros por tipo no topo com HTMX
- [ ] Popular `activity_log` nos eventos: `save_search()`, `POST /archive` (sucesso),
      download concluído (status → `done`)

---

## Fase 9 — Polimento e Integração Final

> Entrega: app production-ready, integrado no ecossistema, lançável com um comando.

- [ ] `iniciar.sh` — versão final robusta: verificar uv instalado, `uv sync --frozen`
- [ ] Escrever `akasha.exe_path` no `ecosystem.json` no startup para o HUB poder lançar
- [ ] `templates/settings.html` — página `/settings`: caminhos do ecossistema (leitura),
      pasta padrão de download, host/porta qBittorrent, profundidade padrão de crawl (default: 2)
- [ ] Nav: adicionar aba "Biblioteca", "Histórico" e "Sites" na topbar
- [ ] `README.md` — atualizar seção "Estado" para "Implementado — Fase 9"

---

## Fase 10 — Buscador de Sites Pessoais

> Entrega: motor de busca próprio sobre domínios curados. O usuário adiciona sites, o AKASHA
> faz crawling BFS respeitando profundidade, indexa em FTS5 e expõe via checkboxes na busca.

### Decisões de design
- **Escopo do crawler**: mesmo domínio + subdomínios selecionados pelo usuário
- **Profundidade default**: 2 (configurável em `/settings`)
- **Re-crawl**: manual (botão) + automático junto ao monitoramento da biblioteca (loop horário)
- **Interface de busca**: checkboxes na barra — `□ Web  □ Ecossistema  □ Sites pessoais`
- **Acesso ao conteúdo**: apenas via busca (ver Planos Futuros para navegação inline)

### Banco de dados

- [x] Migration v7: tabela `crawl_sites` —
      `id, base_url, label, crawl_depth, subdomains_json, page_count,
       last_crawled_at, status (idle|crawling|error), created_at`
- [x] Migration v7: tabela `crawl_pages` —
      `id, site_id, url, title, content_md, content_hash, http_status, crawled_at`
- [x] Migration v7: FTS5 `crawl_fts` — `(site_id UNINDEXED, url UNINDEXED, title, content_md)`
      sincronização manual em Python (sem triggers SQL no FTS5)
- [x] `database.py` — helpers: `get_all_crawl_sites()`, `get_crawl_site(id)`

### Services

- [x] `services/crawler.py` — `extract_links(html, base_url) -> list[str]`:
      extrai links normalizados; descarta âncoras, assets, esquemas não-http
- [x] `services/crawler.py` — `discover_subdomains(base_url) -> list[str]`:
      GET homepage + tenta sitemap.xml; filtra subdomínios do mesmo domínio-raiz
- [x] `services/crawler.py` — `crawl_site(site_id) -> int`:
      BFS async com httpx; delega extração ao ecosystem_scraper; atualiza crawl_pages + crawl_fts
- [x] `services/crawler.py` — `search_sites(query) -> list[SearchResult]`:
      busca FTS5 em crawl_fts; retorna SearchResult com source="SITES"
- [x] `services/crawler.py` — `crawl_pending_sites()`:
      crawls sites com last_crawled_at IS NULL; chamado pelo loop horário
- [x] Integrar `crawl_pending_sites()` no loop horário do lifespan (`_monitor_library`)

### Routers

- [x] `routers/crawler.py` — `POST /sites/discover` (body: `{url}`):
      chama `discover_subdomains()`, retorna `{base_url, subdomains: list[str]}`
      para o front perguntar quais incluir (resposta HTMX com checkboxes)
- [x] `routers/crawler.py` — `POST /sites` (body: `{url, label, crawl_depth, subdomains}`):
      cria entrada em `crawl_sites`, dispara `crawl_site()` em background task
- [x] `routers/crawler.py` — `GET /sites` → lista de sites com `page_count`,
      `last_crawled_at`, `status`
- [x] `routers/crawler.py` — `DELETE /sites/{id}` — remove site e todas as `crawl_pages`
- [x] `routers/crawler.py` — `POST /sites/{id}/crawl` — re-crawl manual; retorna toast via HTMX

### Integração com busca

- [x] `routers/search.py` — novo source `sites`: busca em `crawl_fts`;
      retorna `list[SearchResult]` com `source="SITES"` e badge dourado
- [x] `templates/search.html` — substituir radio de fonte por checkboxes:
      `□ Web  □ Ecossistema  □ Sites pessoais`; persistir escolha em `localStorage`;
      quando "Sites pessoais" marcado e sem sites cadastrados, exibir link para `/sites`
- [x] `templates/search.html` — terceira seção de resultados "Nos meus sites" quando
      checkbox marcado e há resultados

### Interface de gerenciamento

- [x] `templates/sites.html` — lista de sites cadastrados; cada card mostra:
      label, domínio, contagem de páginas, data do último crawl, badge de status,
      subdomínios incluídos; botão "Re-crawl" e "Remover"
- [x] `templates/sites.html` — formulário "Adicionar site": campo URL → botão "Detectar subdomínios"
      → HTMX retorna checkboxes dos subdomínios encontrados → campo profundidade → "Adicionar"
- [ ] Nav: aba "Sites" na topbar

---

## Planos Futuros

> Funcionalidades adiadas por complexidade ou baixa prioridade imediata.

- **Navegação inline de páginas crawleadas** — permitir abrir e ler o conteúdo de uma `crawl_page`
  diretamente na interface do AKASHA, sem sair para o navegador (reader mode próprio)

---

*Atualizado em: 2026-04-16 — Fases 1, 2, 3, 5 e 7 concluídas. Escopo revisado: +Biblioteca de URLs, +Histórico, seções separadas web/local, +Buscador de Sites (Fase 10).*
