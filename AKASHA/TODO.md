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
      Cascata implementada (newspaper4k e readability-lxml bloqueados — lxml 5.x não compila
      em Python 3.14; lxml 6.x não é compatível com essas libs):
        1. `newspaper4k`     — BLOQUEADO (lxml 5.x / Python 3.14)
        2. `trafilatura`     — markdown nativo, instalado ✓
        3. `readability-lxml`— BLOQUEADO (lxml 5.x / Python 3.14)
        4. `inscriptis`      — texto estruturado, instalado ✓
        5. `BeautifulSoup`   — fallback html.parser + markdownify, instalado ✓
        6. `Jina Reader API` — fallback remoto: r.jina.ai/{url} se cascata < 100 palavras ✓

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
- [x] Nav: aba "Sites" na topbar

---

## Fase 10.5 — Navegação inline de páginas crawleadas

> Entrega: reader mode próprio — abrir e ler qualquer `crawl_page` sem sair do AKASHA.

- [ ] `database.py` — helpers `get_crawl_page_by_url(url) -> tuple | None` e
      `get_crawl_pages_by_site(site_id, limit, offset) -> list[tuple]`
      (retorna `id, url, title, http_status, crawled_at` sem `content_md` para a lista)
- [ ] `routers/crawler.py` — `GET /sites/reader?url=` — busca `crawl_page` por URL via
      `get_crawl_page_by_url`, converte `content_md` → HTML com lib `markdown`,
      renderiza `page_reader.html`; 404 se não encontrada
- [ ] `routers/crawler.py` — `GET /sites/{site_id}/pages?q=&page=1` — lista paginada
      (20/pág) de páginas do site; suporte a filtro por `q` (título/url); retorna fragment
      HTMX `_site_pages.html`
- [ ] `templates/page_reader.html` — layout reader mode: cabeçalho com título, URL original
      (link externo ↗), data de crawl, botão "← Voltar"; conteúdo HTML do markdown com
      tipografia IM Fell English; compatível com tema sépia/noturno
- [ ] `templates/_site_pages.html` — fragment HTMX: lista de cards de página (título, URL
      abreviada, data, badge de status HTTP); botão "Ler" abre `/sites/reader?url=...`;
      paginação "Carregar mais" com `hx-swap="beforeend"`
- [ ] `templates/sites.html` — botão "📄 N páginas" em cada site card que expande
      `_site_pages.html` via HTMX (`hx-get="/sites/{id}/pages" hx-swap="innerHTML"`);
      colapsar ao clicar de novo
- [ ] `templates/_macros.html` — nos cards de resultado com `source="SITES"`, adicionar
      botão "Ler" ao lado do link externo que abre `/sites/reader?url=...` inline

---

## Fase 11 — Performance e Robustez

> Entrega: app mais rápido, sem gargalos de I/O e com SQLite bem configurado.

### Alta prioridade (impacto imediato visível)

- [x] **SQLite WAL mode + pragmas** — `database.py`: na função `init_db()`, após conectar,
      executar `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`,
      `PRAGMA cache_size=-8000` (8 MB), `PRAGMA mmap_size=67108864` (64 MB).
      WAL elimina lock de leitura durante writes — crítico para crawl + busca simultâneos.
      Hoje reads e writes se bloqueiam mutuamente porque o modo padrão é DELETE.

- [x] **Índices ausentes** — `database.py`: migration v8:
      `CREATE INDEX IF NOT EXISTS idx_crawl_pages_site ON crawl_pages(site_id)` e
      `CREATE INDEX IF NOT EXISTS idx_library_diffs_url ON library_diffs(url_id)`.
      Sem eles, `get_crawl_pages_by_site` e `_recent_diff_ids` fazem full-table scan.

- [x] **Busca paralela** — `routers/search.py`: `asyncio.gather()` com filtro
      condicional — se `src_web` está off, passa `asyncio.sleep(0, result=[])` no slot.
      Reduz latência de ~1 s para ~400 ms.

- [x] **`check_overdue` e `list_entries` sem `content_md`** — `services/library.py`:
      `_LIST_COLS` sem `content_md`; `_row_to_entry` aceita rows de 13 ou 14 colunas.
      `scrape_and_store` mantém `SELECT *` pois precisa do conteúdo para calcular diff.

### Média prioridade (reduz lock contention no crawler)

- [x] **Crawl com conexão única por sessão** — `services/crawler.py`: `crawl_site` agora
      usa 2 conexões (leitura inicial + sessão BFS completa); `_process_url` captura `db`
      via closure em vez de abrir nova conexão por página.

- [x] **FTS skip em conteúdo idêntico** — `services/crawler.py` → `_upsert_page`:
      consulta `content_hash` atual antes do FTS; pula DELETE + INSERT se hash idêntico.

- [x] **`asyncio.get_event_loop()` → `asyncio.get_running_loop()`** — `routers/crawler.py`
      (3 ocorrências) e `main.py` (1 ocorrência).

### Baixa prioridade (manutenção a longo prazo)

- [ ] **Limpeza periódica do search_cache** — `main.py` → `_monitor_library()`:
      ao acordar, executar `DELETE FROM search_cache WHERE created_at < ?` com cutoff
      de 24 h. Sem essa limpeza o cache cresce indefinidamente — cada query única
      adiciona uma linha; após semanas de uso o arquivo SQLite infla.

- [ ] **Monitor de biblioteca com paralelismo controlado** — `main.py` → `_monitor_library()`:
      em vez de re-scrape sequencial das URLs vencidas, usar `asyncio.gather` com
      `asyncio.Semaphore(3)` — máximo 3 scrapes simultâneos. Uma biblioteca com 50+
      URLs vencidas pode travar o event loop por vários minutos em modo sequencial.

- [ ] **Dependência `markdown`** — `pyproject.toml`: adicionar `markdown>=3.7`
      (necessário para Fase 10.5 — converter `content_md` → HTML no reader mode).

---

## Fase 12 — Extensão Firefox (Zen Browser)

> Entrega: extensão Manifest V3 que detecta URLs de vídeo na aba atual e delega o download
> ao Hermes via AKASHA com um clique. Requer Fase 3 do Hermes (mini API HTTP).

### Estrutura de arquivos
- [ ] `extension/manifest.json` — Manifest V3; permissões: `activeTab`,
      `http://localhost:7071/*`; action com ícones active/inactive;
      background service worker; popup declarado
- [ ] `extension/icons/` — ícone 16/32/48/128px nos dois estados (active e greyscale)
- [ ] `extension/popup/popup.html` + `popup.css` + `popup.js` — UI mínima:
      URL atual, dois botões: "⬇ Baixar vídeo" e "📝 Transcrever";
      ambos rodam em segundo plano via Hermes; feedback de estado
      (aguardando / na fila / erro Hermes offline / erro AKASHA offline)

### Background script
- [ ] `extension/background.js` — ao mudar de aba ou navegar, verificar se a URL
      pertence a site de vídeo suportado pelo yt-dlp (YouTube, Vimeo, Twitch,
      Twitter/X, TikTok, Reddit, Dailymotion, Bilibili, Niconico, etc.);
      habilitar/desabilitar ícone da action conforme resultado
- [ ] `extension/background.js` — ao receber mensagem `{action: "download"|"transcribe", url}`
      do popup, fazer `POST http://localhost:7071/api/hermes/download` com `{url, mode}`;
      retornar `{ok, error?}` ao popup; fechar popup após confirmação (roda em bg)

### Backend AKASHA
- [ ] `routers/hermes_bridge.py` — `POST /api/hermes/download`
      (body Pydantic: `url: str`, `mode: Literal["download","transcribe"] = "download"`,
      `format: str | None = None`):
      1. Lê `hermes.api_port` do ecosystem.json
      2. Tenta `GET /health` no Hermes — se falhar (offline):
         a. Lê `hermes.exe_path` do ecosystem.json
         b. Verifica via `psutil` se processo Hermes está rodando
         c. Se não estiver, dispara `subprocess.Popen(exe_path)`
         d. Aguarda `/health` responder com polling (timeout 30s, intervalo 1s)
         e. Se não subir no timeout, retorna 503 com mensagem clara
      3. Delega via `httpx.AsyncClient` para `/download` ou `/transcribe`
      Adicionar `psutil` ao `pyproject.toml` se não presente
- [ ] Registrar `hermes_bridge` router em `main.py`

### Instalação (desenvolvimento)
- [ ] `extension/README.md` — instruções: `about:debugging` → "Este Firefox" →
      "Carregar extensão temporária" → selecionar `extension/manifest.json`

---

## Fase 12.5 — Aba "Ver Mais Tarde"

> Lista interna de URLs para retomar depois, sem arquivar nem monitorar.
> Visível apenas no AKASHA — não indexada no `local_fts` nem exportada para o ecossistema.
> Resultados aparecem na busca global como seção separada "Salvo para depois".

### Banco de dados

- [x] Migration v9: tabela `watch_later` —
      `id, url (UNIQUE), title, snippet, notes, added_at`
- [x] Migration v9: FTS5 `watch_later_fts` — `(id UNINDEXED, url UNINDEXED, title, notes)`
      sincronizada manualmente nos helpers

### Backend

- [x] `database.py` — helpers: `add_watch_later(url, title, snippet) -> int`;
      `get_all_watch_later() -> list[tuple]`; `delete_watch_later(id) -> None`;
      `search_watch_later(query, limit) -> list[tuple]`
- [x] `services/local_search.py` — função `search_watch_later(query, max_results)`
      que consulta `watch_later_fts`; retorna `list[SearchResult]` com `source="DEPOIS"`;
      NÃO adiciona ao `local_fts` (não visível para o ecossistema)
- [x] `routers/watch_later.py` — `GET /watch-later` (página da lista);
      `POST /watch-later/add` (form: url, title?, snippet?; retorna 200);
      `DELETE /watch-later/{id}` (retorna 200)

### Templates

- [x] `templates/watch_later.html` — lista de itens salvos: título, URL, data,
      campo notes inline editável, botão "remover"; empty state com hint
- [x] `templates/_macros.html` — botão `☆ ver depois` (`hx-post="/watch-later/add"`)
      nos cards de resultado `WEB`, junto com os outros botões de ação
- [x] `templates/base.html` — aba "ver depois" na nav entre "sites" e "downloads"
- [x] `templates/search.html` — seção "Salvo para depois" (após seção Sites,
      antes do empty state); aparece sempre que há matches no `watch_later_fts`

### Integração com busca

- [x] `routers/search.py` — incluir `search_watch_later(q)` no `asyncio.gather`;
      passa `watch_later_results` para o template; seção visível
      independente dos checkboxes (sempre busca se há query)

### TODO update

- [x] Atualizar `AKASHA/TODO.md` ao concluir: marcar itens e atualizar data

---

## Fase 13 — API de Pesquisa Profunda (integração com Mnemosyne)

> Entrega: endpoint JSON que o Mnemosyne pode chamar para buscar + scraping on-demand,
> permitindo "Modo de Pesquisa Profunda" que combina biblioteca local com conteúdo web atual.

### Novos endpoints

- [ ] `GET /search/json?q={query}&sources=web,sites&max={n}` — retorna resultados de busca
      como JSON puro (`list[SearchResult]`) em vez de HTML; reutiliza a lógica de
      `routers/search.py` mas com `Response` JSON; usado pelo Mnemosyne para obter URLs relevantes
      sem scraping ainda

- [ ] `POST /fetch` (body: `{url: str, max_words: int = 2000}`) — fetch + scraping
      completo de uma URL usando a cascata do `ecosystem_scraper` + fallback Jina Reader;
      retorna `{url, title, content_md, word_count, error?}`; não persiste nada — resposta
      efêmera para uso imediato pelo Mnemosyne; timeout 30s

### Notas de implementação

- Ambos os endpoints são somente-leitura — não alteram estado do AKASHA
- `GET /search/json` pode ser implementado extraindo a lógica de busca de `routers/search.py`
  para uma função pura e reutilizando em ambos os handlers (HTML e JSON)
- `POST /fetch` reutiliza `ecosystem_scraper.extract()` + a lógica de Jina já em `archiver.py`
- Latência esperada: `/search/json` ~400ms (DDG cache hit) / ~1.5s (miss); `/fetch` ~2–8s por URL

---

## Fase 14 — Integração KOSMOS nos cards de resultado

> Botão nos cards de resultado web para adicionar a URL à lista de fontes do KOSMOS.

- [x] `templates/_macros.html` — botão "K" nos cards `WEB`:
      `hx-post="/kosmos/add-source"` com `{"url": "...", "name": "..."}`;
      usa `detect_feed_type()` do KOSMOS para inferir tipo (youtube/rss/etc.)
- [x] KOSMOS expõe `POST /add-source` via `http.server` em thread daemon (porta 8965 por padrão)
- [x] `routers/kosmos_bridge.py` — lê porta do ecosystem.json, encaminha para KOSMOS; 503 se KOSMOS offline

---

## Planos Futuros

> Funcionalidades adiadas por complexidade ou baixa prioridade imediata.

---

*Atualizado em: 2026-04-21 — Fase 12 (extensão Firefox + integração Hermes) adicionada; Fase 13 (API de Pesquisa Profunda) adicionada; Fase 14 (integração KOSMOS nos cards) adicionada.*
