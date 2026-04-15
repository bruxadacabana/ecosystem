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

- [ ] `pyproject.toml` — dependências uv: `fastapi`, `uvicorn[standard]`, `aiosqlite`, `httpx`,
      `jinja2`, `python-multipart`, `duckduckgo-search`, `qbittorrent-api`, `trafilatura`
- [ ] `main.py` — FastAPI app + lifespan: inicializa DB, escreve `akasha.base_url`
      em `ecosystem.json` no startup (try/except — nunca bloquear)
- [ ] `config.py` — lê `ecosystem.json` via `ecosystem_client`; expõe `kosmos_archive`,
      `aether_vault`, `mnemosyne_indices`, `qbt_host`, `qbt_port`; fallback silencioso
- [ ] `database.py` — schema SQLite + migrations: tabelas `searches`, `downloads`, `settings`
      (campo `schema_version`); função `init_db()` chamada no startup
- [ ] `static/style.css` — paleta CSS completa (sépia diurna + noturno astronômico via
      `prefers-color-scheme: dark`), tipografia (IM Fell English · Special Elite · Courier Prime),
      componentes: `.btn`, `.btn-ghost`, `.card`, `.input`, `.tag`, `.badge`, `.toast`
- [ ] `templates/base.html` — layout base: topbar (AKASHA itálico 24px, toggle ☽/☀),
      search bar com HTMX (`hx-get="/search" hx-trigger="submit"`), nav tabs (Busca / Downloads / Torrents)
- [ ] `templates/search.html` — extends base: área de resultados com skeleton loader,
      empty state com buscas recentes
- [ ] `iniciar.sh` — detecta `.venv` do ecossistema em `../`; se não existir, cria venv local;
      `uv sync` e executa `uv run python main.py`; `chmod +x`

---

## Fase 2 — Busca Web

> Entrega: busca DuckDuckGo funcional com resultados em cards e histórico persistido.

- [ ] `services/web_search.py` — DuckDuckGo via `duckduckgo-search`; cache em SQLite (TTL 1h);
      deduplicação por URL normalizada; retorna `list[SearchResult]` (Pydantic)
- [ ] `routers/search.py` — `GET /search?q=&sources=web` → renderiza `search.html` com resultados;
      salva query + timestamp em `searches`
- [ ] `templates/search.html` — cards de resultado: título linkado, snippet, badge de fonte,
      data; HTMX `hx-get` no form com indicador de loading
- [ ] Widget "Buscas recentes" no empty state: lista das últimas 10 queries da tabela `searches`
- [ ] Filtro de fonte no UI: radio/toggle Web / Local / Todos (query param `sources=`)

---

## Fase 3 — Busca Local

> Entrega: busca nos arquivos do ecossistema integrada com os resultados web.

- [ ] `services/local_search.py` — ler KOSMOS archive (`{archive_path}/**/*.md`):
      parsear frontmatter YAML simples, indexar título + corpo em FTS5
- [ ] `services/local_search.py` — ler AETHER vault (`{vault_path}/*/chapters/*.md`):
      título e conteúdo dos capítulos; indexar em FTS5
- [ ] FTS5 virtual table `local_index` em SQLite: schema `(path, title, body, source, mtime)`
- [ ] Reindexação automática no startup se `mtime` dos arquivos mudou desde última indexação
- [ ] `services/local_search.py` — query ChromaDB do Mnemosyne se `mnemosyne_indices`
      não vazio (import opcional; graceful fallback se `chromadb` não instalado)
- [ ] `routers/search.py` — fundir resultados web + local: ranking por relevância, deduplicação
- [ ] Badge de fonte em cada card: `WEB` · `KOSMOS` · `AETHER` · `MNEMOSYNE` com cor distinta

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

- [ ] `services/archiver.py` — fetch via `httpx`, extração de conteúdo com `trafilatura`,
      geração de Markdown com frontmatter KOSMOS:
      `title`, `source`, `url`, `date`, `author` (se disponível)
- [ ] `routers/search.py` — `POST /archive` (body: `{url, dest_dir?}`):
      chama archiver, salva em `{kosmos_archive}/{YYYY-MM-DD}_{slug}.md`
- [ ] Botão "📥 Arquivar" em cada card de resultado web (HTMX `hx-post`, swap com toast)
- [ ] Fallback: se `kosmos_archive` não configurado, retornar erro 400 com mensagem clara
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

## Fase 7 — Polimento e Integração Final

> Entrega: app production-ready, integrado no ecossistema, lançável com um comando.

- [ ] `iniciar.sh` — versão final robusta: verificar uv instalado, `uv sync --frozen`,
      tratar erros de porta em uso (sugerir porta alternativa)
- [ ] Escrever `akasha.exe_path` no `ecosystem.json` no startup para o HUB poder lançar o app
- [ ] `templates/settings.html` — página `/settings`: caminhos do ecossistema (somente leitura,
      vindos do `ecosystem.json`), pasta padrão de download (editável), host/porta qBittorrent
- [ ] Modo noturno: toggle manual salvo em cookie `theme=dark|light`; respeitar
      `prefers-color-scheme` como padrão inicial
- [ ] Performance: busca web < 800ms p95; busca local < 200ms para 10k arquivos indexados;
      SSE sem memory leak (fechar generator no disconnect)
- [ ] `README.md` — atualizar seção "Estado" para "Implementado — Fase 7"; instruções
      detalhadas de instalação para CachyOS (Fish + Niri) e Windows 10

---

*Atualizado em: 2026-04-15 — Planejamento concluído. Fase 1 não iniciada.*
