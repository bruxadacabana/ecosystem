# AKASHA — TODO

> Criado: 2026-04-15

Buscador pessoal local. Agrega resultados da web e do ecossistema numa interface única,
com downloads genéricos e integração com qBittorrent.
Stack: FastAPI + HTMX + Jinja2 + SQLite (aiosqlite) + uv · Porta 7070.

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
      idêntico ao KOSMOS (`title`, `source`, `date`, `author`, `url`);
      salva em `{archive_path}/Web/{YYYY-MM-DD}_{slug}.md`; slug max 60 chars
- [x] `routers/search.py` — `POST /archive` (body form: `url`):
      chama archiver, retorna 200 OK ou 400 se `kosmos_archive` não configurado
- [x] Botão "arquivar" em cada card de resultado `WEB` (HTMX `hx-post`, toast de confirmação)
- [x] Fallback: se `kosmos_archive` não configurado, retornar erro 400 com mensagem clara
      orientando a configurar o caminho em `/settings`

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

- [ ] Migration v5: tabelas `library_urls` (url, title, snippet, content_md, content_hash,
      language, word_count, tags_json, notes, check_interval_days, last_checked_at, status)
      + `library_diffs` (url_id, diff_text, scraped_at) + FTS5 `library_fts`
- [ ] `services/library.py` — `add_url()`, `scrape_and_store()` (trafilatura + metadados:
      language, word_count); `check_overdue()`; `compute_diff()` via `difflib.unified_diff()`
- [ ] `routers/library.py` — `GET /library?tag=&lang=`; `POST /library/add`
      (body: `{url, interval_days, tags?, notes?}`); `PATCH /library/{id}`;
      `POST /library/refresh/{id}`; `DELETE /library/{id}`
- [ ] `templates/library.html` — cards com título, snippet, idioma, contagem de palavras,
      tags, data do último scrape, badge de intervalo, campo de notas inline (HTMX `hx-patch`),
      badge "mudou" se diff recente; filtro por tag e idioma no topo
- [ ] Background task no lifespan: acorda a cada hora, re-scrape URLs vencidas silenciosamente
- [ ] Busca local `/search?sources=local` inclui conteúdo da `library_fts`

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
      pasta padrão de download, host/porta qBittorrent
- [ ] Nav: adicionar aba "Biblioteca" e "Histórico" na topbar
- [ ] `README.md` — atualizar seção "Estado" para "Implementado — Fase 9"

---

*Atualizado em: 2026-04-16 — Fases 1, 2, 3 e 5 concluídas. Escopo revisado: +Biblioteca de URLs, +Histórico, seções separadas web/local.*
