# Guia de Desenvolvimento e Integração do Ecossistema

> **Para quem é este guia:** Para você, quando precisar retomar o desenvolvimento depois de um intervalo e quiser entender o que já foi feito, como as peças se encaixam, e como programar com segurança sem quebrar o que funciona.

---

## Índice

1. [Visão Geral da Arquitetura](#1-visão-geral-da-arquitetura)
2. [Mapeamento de Stacks e Estrutura de Diretórios](#2-mapeamento-de-stacks-e-estrutura-de-diretórios)
3. [Padrões de Código e Boas Práticas](#3-padrões-de-código-e-boas-práticas)
4. [Guia de Leitura de Código](#4-guia-de-leitura-de-código)
5. [Workflow de Desenvolvimento](#5-workflow-de-desenvolvimento)
6. [Anexo — Fundamentos e Mecânica](#anexo--fundamentos-e-mecânica-do-ecossistema)
   - [A.1 — A Razão das Ferramentas (Os "Porquês")](#a1--a-razão-das-ferramentas-os-porquês)
   - [A.2 — Como as Engrenagens Giram (Fluxo de Dados)](#a2--como-as-engrenagens-giram-fluxo-de-dados)
   - [A.3 — Banco de Dados e Persistência](#a3--banco-de-dados-e-persistência)
   - [A.4 — Blueprint de Reconstrução](#a4--o-blueprint-de-reconstrução)

---

## 1. Visão Geral da Arquitetura

### O que é o ecossistema?

São 7 programas independentes que rodam na sua máquina e colaboram entre si. Cada um faz uma coisa bem definida e não depende dos outros para funcionar — mas quando estão todos rodando juntos, formam um ambiente integrado de escrita, pesquisa e gestão de conhecimento.

```
┌─────────────────────────────────────────────────────────────────────┐
│                              HUB                                     │
│         Dashboard central — sempre aberto, lança os outros          │
│         Hospeda o LOGOS (proxy de LLM com fila de prioridade)       │
└───────────┬────────────┬───────────┬───────────┬────────────────────┘
            │            │           │           │
            │ lê arquivos│ lê sqlite │ lê JSON   │ lê arquivos
            ▼            ▼           ▼           ▼
         AETHER        OGMA       KOSMOS       Hermes
     (escrita criativa) (projetos) (RSS/feeds) (downloads)
            │                        │           │
            │                        │           │
            │              ◄─────────┘           │
            │              HTTP /add-source        │
            │                                      │
            └──────────────────────────────────────┘
                    (arquivos gerados indexados por)
                                │
                             AKASHA
                   (mecanismo de busca pessoal)
                                │
                         HTTP + busca
                                │
                           Mnemosyne
                       (assistente RAG local)
```

### O fio que conecta tudo: `ecosystem.json`

Todos os apps leem e escrevem em **um único arquivo JSON** de configuração compartilhada:

- **Linux:** `~/.local/share/ecosystem/ecosystem.json`
- **Windows:** `%APPDATA%\ecosystem\ecosystem.json`

Este arquivo é o "diretório telefônico" do ecossistema. Quando o AKASHA quer saber onde está o arquivo de dados do KOSMOS, ele lê daqui. Quando o HUB quer abrir o AETHER, ele lê o `vault_path` daqui.

**Estrutura completa do arquivo (com todos os campos possíveis):**

```json
{
  "aether":    { "vault_path": "/caminho/para/vault", "config_path": "" },
  "kosmos":    { "data_path": "", "archive_path": "", "http_port": 8965 },
  "ogma":      { "data_path": "/caminho/para/ogma.db", "config_path": "" },
  "mnemosyne": { "index_paths": [], "config_path": "" },
  "hub":       { "data_path": "" },
  "hermes":    { "output_dir": "", "config_path": "" },
  "akasha":    { "archive_path": "", "data_path": "", "base_url": "http://localhost:7071" },
  "logos":     { "ollama_base": "http://localhost:11434" }
}
```

**Quem escreve o quê:**

| Campo | Quem escreve |
|-------|-------------|
| `aether.vault_path` | AETHER (na configuração inicial) |
| `kosmos.archive_path`, `kosmos.http_port` | KOSMOS (no startup) |
| `ogma.data_path` | OGMA (no startup) |
| `akasha.base_url`, `akasha.archive_path` | AKASHA (no startup) |
| `hermes.output_dir`, `hermes.api_port` | Hermes (no startup) |
| `mnemosyne.index_paths` | Mnemosyne (quando indexa) |
| Tudo | HUB (via SetupView — configura os caminhos base) |

**Regra de ouro:** Nenhum app apaga a seção de outro. A escrita é sempre "ler tudo → atualizar só a minha seção → escrever tudo de volta", com um file lock (`.ecosystem.lock` no mesmo diretório) para evitar conflito entre apps que iniciam ao mesmo tempo.

### Mapa de comunicações entre os apps

```
┌─────────────────────────────────────────────────────────────────────┐
│  Tipo de comunicação    │  Quem → Quem              │  Como         │
├─────────────────────────┼───────────────────────────┼───────────────┤
│  ecosystem.json         │  Todos ↔ Todos            │  Arquivo JSON │
│  HTTP API               │  AKASHA → KOSMOS          │  POST :8965   │
│  HTTP LLM               │  Python apps → LOGOS/HUB  │  POST :7072   │
│  HTTP LLM fallback      │  Python apps → Ollama     │  POST :11434  │
│  HTTP busca             │  Mnemosyne → AKASHA        │  GET :7071    │
│  Leitura direta         │  HUB → AETHER/KOSMOS/OGMA │  Rust lê disco│
└─────────────────────────────────────────────────────────────────────┘
```

**Portas reservadas:**

| App | Porta | Modo |
|-----|-------|------|
| HUB (Vite dev) | 5173 | desenvolvimento |
| AETHER (Vite dev) | 5174 | desenvolvimento |
| OGMA (Vite dev) | 5175 | desenvolvimento |
| AKASHA | 7071 | produção (sempre) |
| LOGOS (parte do HUB) | 7072 | produção (sempre) |
| KOSMOS (API interna) | 8965 | produção (sempre) |

### O papel de cada app

| App | Responsabilidade |
|-----|-----------------|
| **HUB** | Dashboard central. Lança e monitora os outros. Hospeda o LOGOS (proxy de LLM). Nunca escreve dados de outros apps — só lê. |
| **AETHER** | Vault de escrita criativa. Projetos > Livros > Capítulos. Dados em JSON + Markdown no disco. Acesso exclusivo pelo HUB e pelo próprio AETHER. |
| **OGMA** | Gerenciador de projetos e notas. Block editor. SQLite local. Pode visualizar projetos do AETHER via `aether_project_id`. |
| **KOSMOS** | Agregador de RSS/feeds com IA. Lê artigos, cria summaries com LLM, permite busca FTS5. Expõe API HTTP mínima para receber feeds do AKASHA. |
| **Mnemosyne** | Assistente RAG local. Indexa documentos (PDF, DOCX, MD) em ChromaDB, faz busca híbrida (semântica + BM25), responde perguntas via Ollama. |
| **Hermes** | Downloader e transcritor. Baixa vídeos/áudio com yt-dlp, transcreve com Whisper, salva Markdown. Expõe API HTTP para receber tarefas. |
| **AKASHA** | Mecanismo de busca pessoal. Busca na web (DuckDuckGo), em arquivos locais (FTS5), em sites crawlados, em papers (arXiv). |

### LOGOS — o proxy de LLM

O LOGOS não é um app separado — é um **módulo do HUB** que roda em background na porta 7072. Ele:

1. Recebe requisições LLM de qualquer app Python via `ecosystem_client.request_llm()`
2. Aplica fila de prioridade (P1 = chat interativo, P2 = RAG, P3 = análise background)
3. Monitora VRAM da GPU e pausa tarefas P3 quando > 85%
4. Se o HUB não estiver rodando, os apps caem direto no Ollama (`:11434`)

---

## 2. Mapeamento de Stacks e Estrutura de Diretórios

### Como usar esta seção

Para cada app, você vai encontrar: a stack, o arquivo de entrada, e um mapa de "onde está o quê". Quando precisar alterar algo, use o mapa para saber onde ir direto.

---

### AKASHA — Mecanismo de Busca Pessoal

**Stack:** Python · FastAPI · aiosqlite (async SQLite) · Jinja2 (templates HTML) · HTMX

**Entrada:** [AKASHA/main.py](AKASHA/main.py) — registra os routers e inicia na porta 7071

**Onde está o quê:**

```
AKASHA/
├── main.py               ← Ponto de entrada. Registra todos os routers, inicializa banco.
├── config.py             ← Caminhos do ecossistema e configurações globais.
├── database.py           ← Schema completo do SQLite (15 migrações versionadas).
├── routers/              ← Cada arquivo = uma funcionalidade exposta via HTTP.
│   ├── search.py         ← GET /search — busca web + local + papers + crawl
│   ├── crawler.py        ← GET/POST /library — gerencia sites crawlados
│   ├── papers.py         ← GET /papers — busca no arXiv
│   ├── kosmos_bridge.py  ← POST /kosmos/add-source — encaminha feed para KOSMOS
│   ├── favorites.py      ← GET /favorites — páginas favoritadas
│   ├── downloads.py      ← GET /downloads — fila do qBittorrent
│   ├── history.py        ← GET /history — log de atividade
│   ├── watch_later.py    ← GET /watch_later — lista "ver depois"
│   ├── domains.py        ← GET /domains — domínios favoritos/bloqueados
│   └── system.py         ← GET /health — health check
├── services/             ← Lógica de negócio (sem HTTP, sem banco direto).
│   ├── web_search.py     ← Integração com DuckDuckGo (DDGS)
│   ├── local_search.py   ← FTS5 em arquivos locais indexados
│   ├── crawler.py        ← BFS crawler com deduplicação por content_hash
│   ├── paper_search.py   ← Integração com aioarxiv (arXiv)
│   ├── archiver.py       ← Arquiva URL com Trafilatura
│   └── downloader.py     ← Gerencia fila de downloads
└── templates/            ← HTML renderizado pelo servidor (Jinja2 + HTMX)
    └── search.html       ← Página de busca
```

**Banco de dados:** SQLite em `{data_path}/akasha.db`. As migrações são aplicadas automaticamente no startup via `database.py`. Para ver o schema completo, leia [AKASHA/database.py](AKASHA/database.py).

Tabelas principais:
- `crawl_pages` — páginas indexadas pelo crawler (com `content_hash` para deduplicação)
- `search_cache` — resultados de busca web cacheados por 24h
- `local_fts` — tabela virtual FTS5 de arquivos locais
- `crawl_fts` — tabela virtual FTS5 do conteúdo crawlado
- `activity_log` — audit trail de todas as ações

---

### KOSMOS — Agregador de RSS com IA

**Stack:** Python · PyQt6 · SQLAlchemy 2.0 (ORM) · feedparser · PyQt6-WebEngine

**Entrada:** [KOSMOS/main.py](KOSMOS/main.py) — inicia o app Qt, banco, HTTP API na porta 8965

**Onde está o quê:**

```
KOSMOS/
├── main.py                       ← Ponto de entrada. Qt app + HTTP daemon thread.
├── app/
│   ├── core/                     ← Toda a lógica de negócio (sem UI).
│   │   ├── models.py             ← 6 modelos SQLAlchemy: Category, Feed, Article, Tag, Highlight, ReadSession
│   │   ├── database.py           ← Inicialização e migrações do SQLAlchemy.
│   │   ├── feed_manager.py       ← CRUD de feeds e artigos (thread-safe).
│   │   ├── background_updater.py ← Thread que busca novos artigos periodicamente.
│   │   ├── feed_fetcher.py       ← Parsing RSS/Atom com feedparser.
│   │   ├── ai_bridge.py          ← Cliente Ollama (via LOGOS). Gera summaries, tags, 5Ws.
│   │   ├── search.py             ← Busca FTS5 nos artigos.
│   │   └── content_filter.py     ← Deduplicação por content_hash.
│   ├── ui/                       ← Componentes visuais PyQt6.
│   │   ├── main_window.py        ← Janela principal.
│   │   ├── views/                ← 8 views (feed list, reader, dashboard, etc.)
│   │   └── dialogs/              ← Diálogos (adicionar feed, traduzir, etc.)
│   └── utils/
│       ├── config.py             ← Configuração (YAML/JSON).
│       └── paths.py              ← Diretórios de dados.
└── app/theme/                    ← Estilos Qt (day.qss, night.qss)
```

**Banco de dados:** SQLite em `{data_path}/kosmos.db` via SQLAlchemy 2.0. Para ver os modelos, leia [KOSMOS/app/core/models.py](KOSMOS/app/core/models.py).

**API HTTP (porta 8965):** Mínima — só dois endpoints:
- `GET /health` — verifica se o KOSMOS está rodando
- `POST /add-source?url=...&name=...` — recebe um feed encaminhado pelo AKASHA

---

### Hermes — Downloader e Transcritor

**Stack:** Python · PyQt6 · yt-dlp · faster-whisper

**Entrada:** [Hermes/hermes.py](Hermes/hermes.py) — app monolítico em ~1500 linhas

**Onde está o quê:**

```
Hermes/
├── hermes.py      ← Tudo: UI, lógica de download, transcription, workers, signals.
├── api_server.py  ← HTTP daemon thread na porta 7072.
│                    Endpoints: GET /health, POST /download, POST /transcribe
└── data/logs/     ← hermes.log (rotação diária)
```

**Banco de dados:** Não tem. Preferências em `.prefs.json`. Histórico em memória, carregado dos arquivos `.md` no diretório de saída.

**Nota importante:** O Hermes não tem uma camada de service separada — toda a lógica está em `hermes.py`. Quando precisar mudar o comportamento de download ou transcrição, é nesse arquivo que você vai.

---

### Mnemosyne — Assistente RAG Local

**Stack:** Python · PySide6 · LangChain · ChromaDB · Ollama

**Entrada:** [Mnemosyne/main.py](Mnemosyne/main.py) — 9 linhas, chama `run()` em `gui/main_window.py`

**Onde está o quê:**

```
Mnemosyne/
├── main.py              ← Ponto de entrada mínimo.
├── core/                ← Toda a lógica de RAG e indexação.
│   ├── config.py        ← AppConfig dataclass. Caminho: ecosystem.json → local config.json.
│   ├── collections.py   ← CollectionConfig: VAULT | LIBRARY, com persist_dir próprio.
│   ├── errors.py        ← 18 classes de exceção específicas (ver Seção 3).
│   ├── indexer.py       ← ChromaDB: carrega, indexa, atualiza. Checkpoint em SQLite.
│   ├── rag.py           ← Chain RAG: recupera chunks → monta prompt → envia ao LLM.
│   ├── bm25_index.py    ← Busca por palavra-chave (complementa o embedding).
│   ├── memory.py        ← Histórico de conversa em history.jsonl + memória em memory.json.
│   ├── loaders.py       ← Parsers: PDF, DOCX, TXT, Markdown com frontmatter.
│   ├── tracker.py       ← Hash de arquivos para indexação incremental.
│   └── watcher.py       ← QFileSystemWatcher — detecta novos arquivos.
└── gui/
    ├── main_window.py   ← Janela principal com abas: Index, Ask, Summarize, Manage.
    ├── workers.py       ← QThread workers: IndexWorker, AskWorker, SummarizeWorker.
    └── styles.qss       ← Estilos Qt (modo noturno por padrão).
```

**Banco de dados:**
- ChromaDB em `{collection_path}/.mnemosyne/chroma_db` — um por collection
- SQLite em `{collection_path}/.mnemosyne/index_checkpoint.db` — rastreia arquivos indexados
- JSON em `{collection_path}/.mnemosyne/memory.json` — memória de sessão

---

### AETHER — Vault de Escrita Criativa

**Stack:** Rust · Tauri 2 · React 19 · TypeScript · Tiptap (editor WYSIWYG)

**Entrada (backend):** [AETHER/src-tauri/src/lib.rs](AETHER/src-tauri/src/lib.rs) — registra 51 comandos Tauri

**Entrada (frontend):** [AETHER/src/main.tsx](AETHER/src/main.tsx) → [AETHER/src/App.tsx](AETHER/src/App.tsx)

**Onde está o quê:**

```
AETHER/
├── src/                      ← Frontend React/TypeScript (roda no Chromium do Tauri)
│   ├── App.tsx               ← Máquina de estados: splash → loading → vault-setup → home → project
│   ├── lib/
│   │   └── tauri.ts          ← Wrapper de todos os 51 comandos. Normaliza erros.
│   ├── components/           ← 12 componentes (Editor, Binder, CorkboardView, etc.)
│   └── styles/
│       └── tokens.css        ← Design system (paleta canônica do ecossistema)
└── src-tauri/                ← Backend Rust
    └── src/
        ├── lib.rs            ← Registra todos os comandos no Tauri builder.
        ├── error.rs          ← AppError enum (ver Seção 3 para o padrão completo).
        ├── types.rs          ← Structs Rust que espelham o TypeScript (Project, Book, Chapter...).
        ├── storage.rs        ← Funções de leitura/escrita de arquivos JSON e Markdown.
        ├── ecosystem.rs      ← Lê/escreve ecosystem.json com lock atômico.
        └── commands/         ← Um arquivo por domínio.
            ├── project.rs    ← list_projects, create_project, delete_project...
            ├── book.rs       ← list_books, create_book, reorder_books...
            ├── chapter.rs    ← read_chapter, save_chapter, trash_chapter...
            ├── character.rs  ← list_characters, save_character, relationships...
            └── world.rs      ← list_world_notes, timeline events...
```

**Banco de dados:** Não tem banco SQL. Tudo em arquivos no vault:
- `{vault}/{projeto_id}/project.json` — metadados do projeto
- `{vault}/{projeto_id}/{livro_id}/book.json` — metadados do livro e lista de capítulos
- `{vault}/{projeto_id}/{livro_id}/{capitulo_id}.md` — conteúdo do capítulo (Markdown puro)
- `{vault}/{projeto_id}/characters/{id}.json` — ficha de personagem
- `{vault}/{projeto_id}/timeline.json` — eventos da linha do tempo

---

### OGMA — Gerenciador de Projetos e Notas

**Stack:** TypeScript · Electron 41 · React 18 · better-sqlite3 · Zustand · EditorJS

**Entrada (backend):** [OGMA/src/main/main.ts](OGMA/src/main/main.ts) — Electron main process

**Entrada (frontend):** [OGMA/src/renderer/main.tsx](OGMA/src/renderer/main.tsx) → [OGMA/src/renderer/App.tsx](OGMA/src/renderer/App.tsx)

**Onde está o quê:**

```
OGMA/
├── src/
│   ├── main/                  ← Processo principal do Electron (Node.js)
│   │   ├── main.ts            ← Cria janela, registra handlers IPC, inicializa banco.
│   │   ├── database.ts        ← Schema SQLite: 12+ tabelas. Abre/cria ogma.db.
│   │   ├── ipc.ts             ← 150+ handlers IPC (toda a API do app).
│   │   ├── ecosystem.ts       ← Lê/escreve ecosystem.json.
│   │   ├── settings.ts        ← Preferências (electron-store).
│   │   └── preload.ts         ← Bridge: expõe window.db e window.electron ao renderer.
│   └── renderer/              ← Interface React (roda no Chromium do Electron)
│       ├── App.tsx            ← Splash → Dashboard/Projects/Page views
│       ├── store/
│       │   └── useAppStore.ts ← Estado global com Zustand. Ações: loadProjects(), selectProject()...
│       ├── views/             ← 8 views principais (Dashboard, ProjectDashboard, PageView...)
│       ├── components/        ← Sidebar, Toast, Modals, etc.
│       └── types/
│           └── index.ts       ← Todos os tipos TypeScript (strict: true)
└── src/editor/web/
    └── editor.html            ← EditorJS com todos os plugins (block editor)
```

**Banco de dados:** SQLite em `{data_path}/ogma.db`. Tabelas principais:
- `projects` — projetos com type, status, icon, cor
- `pages` — páginas hierárquicas (`parent_id` nullable) com `body_json` (blocos EditorJS)
- `project_properties` — campos customizados por projeto (text, number, select, date...)
- `page_prop_values` — valores dos campos (storage polimórfico)
- `project_views` — views configuradas (tabela, kanban, calendário, galeria...)

---

### HUB — Dashboard Central

**Stack:** Rust · Tauri 2 · React 19 · TypeScript

**Entrada (backend):** [HUB/src-tauri/src/lib.rs](HUB/src-tauri/src/lib.rs)

**Entrada (frontend):** [HUB/src/main.tsx](HUB/src/main.tsx) → [HUB/src/App.tsx](HUB/src/App.tsx)

**Onde está o quê:**

```
HUB/
├── src/
│   ├── App.tsx              ← Estado: section (home/logos/activity/setup) + moduleView (writing/reading/projects/questions)
│   ├── lib/
│   │   └── tauri.ts         ← Wrapper dos 35+ comandos. Mesmo padrão TauriResult<T> do AETHER.
│   ├── views/               ← Uma view por módulo/seção.
│   │   ├── WritingView.tsx  ← Visualiza projetos/livros/capítulos do AETHER (só leitura)
│   │   ├── ReadingView.tsx  ← Visualiza artigos do KOSMOS (só leitura)
│   │   ├── ProjectsView.tsx ← Visualiza projetos do OGMA (só leitura)
│   │   ├── QuestionsView.tsx← Chat com Ollama via LOGOS
│   │   ├── LogosView.tsx    ← Status do LOGOS (fila, perfil de hardware, modelos)
│   │   ├── SetupView.tsx    ← Configuração de caminhos do ecossistema
│   │   └── DashboardView.tsx← Painel com todos os módulos
│   └── components/
│       └── Sidebar.tsx      ← Navegação principal
└── src-tauri/src/
    ├── lib.rs               ← Registra todos os comandos.
    ├── error.rs             ← AppError (mesmo padrão do AETHER).
    ├── ecosystem.rs         ← Lê/escreve ecosystem.json com lock.
    └── commands/
        ├── config.rs        ← read_ecosystem_config, save_ecosystem_config, apply_sync_root
        ├── writing.rs       ← list_writing_projects, list_books, read_chapter (lê disco AETHER)
        ├── reading.rs       ← list_articles, read_article (lê disco KOSMOS)
        ├── projects.rs      ← list_ogma_projects, list_project_pages (lê SQLite OGMA)
        └── logos.rs         ← logos_get_status, logos_set_profile, logos_list_models
```

**Banco de dados:** Nenhum. O HUB só lê os dados dos outros apps diretamente do disco via Rust.

---

## 3. Padrões de Código e Boas Práticas

### Convenções de nomenclatura

| Contexto | Convenção | Exemplo |
|----------|-----------|---------|
| Python — funções e variáveis | snake_case | `get_article()`, `base_url` |
| Python — classes | PascalCase | `FeedManager`, `ArticleReader` |
| Python — constantes | UPPER_SNAKE | `AKASHA_PORT = 7071` |
| Python — arquivos de router | nome do domínio | `crawler.py`, `papers.py` |
| Rust — funções | snake_case | `read_chapter()`, `list_books()` |
| Rust — structs e enums | PascalCase | `AppError`, `ChapterMeta` |
| TypeScript — funções e variáveis | camelCase | `readChapter()`, `vaultPath` |
| TypeScript — tipos e interfaces | PascalCase | `TauriResult<T>`, `AppError` |
| Comandos Tauri | módulo_ação | `read_chapter`, `list_books`, `save_chapter` |
| Handlers IPC (OGMA) | módulo:ação | `pages:get`, `projects:create` |

### Tratamento de erros com tipagem — o padrão do ecossistema

Este é o princípio mais importante do projeto. Erros sem tipo são bugs escondidos. Cada stack tem um padrão, e você deve segui-lo rigorosamente.

#### Rust (AETHER e HUB)

Erros são um `enum` centralizado com `thiserror`. A serialização via `serde` envia o erro para o TypeScript como objeto com `kind` e `message`:

```rust
// error.rs (mesmo padrão em AETHER e HUB)
#[derive(Debug, Error, Serialize)]
#[serde(tag = "kind", content = "message")]
pub enum AppError {
    #[error("Erro de I/O: {0}")]
    Io(String),
    #[error("Erro de JSON: {0}")]
    Json(String),
    #[error("Vault não configurado")]
    VaultNotConfigured,
    #[error("Projeto não encontrado: {0}")]
    ProjectNotFound(String),
    // ...
}
```

**Regra:** Toda função que pode falhar retorna `Result<T, AppError>`. **Zero `.unwrap()` em código de produção.** Se precisar de um `.unwrap()` temporário para testar, documente o porquê.

```rust
// Forma correta
pub fn read_chapter(vault: &str, chapter_id: &str) -> Result<String, AppError> {
    let content = fs::read_to_string(path).map_err(|e| AppError::Io(e.to_string()))?;
    Ok(content)
}

// Nunca faça isso em produção
let content = fs::read_to_string(path).unwrap(); // ← PROIBIDO
```

#### TypeScript (AETHER, OGMA, HUB)

O resultado de qualquer comando Tauri ou chamada IPC é sempre um `Result<T, E>` — nunca um valor direto que pode lançar exceção surpresa.

**No AETHER e HUB** (padrão próprio):
```typescript
// lib/tauri.ts — wrapper normalizado
type TauriResult<T> = { ok: true; data: T } | { ok: false; error: AppError }

// Como usar em componentes:
const result = await call<Chapter[]>("list_books", { vaultPath, projectId })
if (!result.ok) {
  showToast(result.error.message) // erro tipado, nunca undefined
  return
}
const books = result.data // TypeScript sabe que é Chapter[] aqui
```

**No OGMA** (usa a biblioteca `neverthrow`):
```typescript
// Mesmo conceito, sintaxe diferente
const result: Result<OgmaProject[], AppError> = await fromIpc("projects:list", {})
result.match(
  (projects) => { /* sucesso */ },
  (error) => { showToast(error.message) } // error.code é ErrorCode (union de strings)
)
```

**Regra:** Nunca use `try/catch` para erros de lógica de negócio em TypeScript aqui — o sistema de tipos já cuida disso. `try/catch` é para erros de I/O inesperados, e mesmo assim o catch deve converter para um tipo conhecido.

#### Python (AKASHA, KOSMOS, Hermes, Mnemosyne)

Cada módulo define suas próprias classes de exceção específicas. Nunca use `except Exception` genérico sem re-tipar:

```python
# Forma correta — módulo-específico
class FeedManagerError(Exception):
    """Erro em operação de feed."""

class OllamaUnavailableError(Exception):
    """Ollama não está acessível."""

def add_feed(url: str) -> Feed:
    try:
        feed = Category(name=url)
        session.add(feed)
        session.commit()
        return feed
    except SQLAlchemyError as exc:
        session.rollback()
        raise FeedManagerError(f"Erro ao criar feed: {exc}") from exc
    #                                                          ^ preserve a causa original

# Hierarquia real do Mnemosyne (core/errors.py):
class MnemosyneError(Exception): ...      # base
class OllamaUnavailableError(MnemosyneError): ...
class ModelNotFoundError(MnemosyneError):
    def __init__(self, model_name: str): ...
class DocumentLoadError(MnemosyneError):
    def __init__(self, path: str, reason: str): ...
# ... 15+ classes específicas
```

**Regra:** Nunca faça `except Exception as e: print(e)` e continue. Ou você relança (`raise`), ou você converte para um tipo específico, ou você loga e encerra graciosamente.

**Em routers FastAPI (AKASHA):**
```python
# As exceções de serviço viram HTTPException no router
@router.get("/search")
async def search(q: str):
    try:
        results = await web_search(q)
        return results
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"HTTP {exc.response.status_code}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
```

### Arquivos utilitários compartilhados

Antes de criar qualquer nova função de utilidade nos apps Python, cheque se já existe nesses arquivos:

| Arquivo | O que contém |
|---------|-------------|
| [ecosystem_client.py](ecosystem_client.py) | `write_section()`, `read_ecosystem()`, `request_llm()`, `logos_status()` |
| [ecosystem_qt.py](ecosystem_qt.py) | `build_qss()`, `load_ecosystem_fonts()`, componentes Qt (spinner, wax seal, candle glow) |
| [ecosystem_scraper.py](ecosystem_scraper.py) | `extract_content(html)` — cascata de extractors (Trafilatura → newspaper4k → BeautifulSoup) |

---

## 4. Guia de Leitura de Código

### Como estudar o que já foi feito

A melhor forma de entender uma feature é seguir o fluxo de uma informação desde o usuário até o banco de dados (e de volta). Abaixo estão roteiros práticos para os fluxos mais comuns.

---

### Roteiro A — Busca no AKASHA: do clique ao resultado

**Situação:** Você quer entender como funciona quando o usuário digita algo no AKASHA e aperta buscar.

**Ordem de leitura:**

1. **[AKASHA/templates/search.html](AKASHA/templates/search.html)** — O formulário HTML com HTMX. Veja o atributo `hx-get` que dispara a busca sem reload de página.

2. **[AKASHA/routers/search.py](AKASHA/routers/search.py)** — O endpoint `GET /search`. Aqui você vê quais parâmetros chegam (`q`, `source`, `page`) e como o resultado é montado para o template.

3. **[AKASHA/services/web_search.py](AKASHA/services/web_search.py)** — A lógica de busca via DuckDuckGo. Aqui está o cache: se a query já foi feita nas últimas 24h, retorna do banco.

4. **[AKASHA/database.py](AKASHA/database.py)** — Procure a tabela `search_cache` para ver como o cache é armazenado, e `local_fts` para entender a busca em arquivos locais.

---

### Roteiro B — Feed do AKASHA para o KOSMOS

**Situação:** Você quer entender como um site encontrado no AKASHA vira um feed no KOSMOS.

**Ordem de leitura:**

1. **[AKASHA/routers/kosmos_bridge.py](AKASHA/routers/kosmos_bridge.py)** — O endpoint `POST /kosmos/add-source` do AKASHA. Veja como ele lê a porta do KOSMOS do `ecosystem.json` e faz uma chamada HTTP.

2. **[AKASHA/services/web_search.py](AKASHA/services/web_search.py)** — Onde o AKASHA detecta se uma URL é um feed RSS antes de encaminhar.

3. **[KOSMOS/main.py](KOSMOS/main.py)** — Procure o servidor HTTP interno. É um daemon thread que roda em paralelo com o Qt.

4. **[KOSMOS/app/core/feed_manager.py](KOSMOS/app/core/feed_manager.py)** — O método `add_feed()` que recebe e persiste o feed no SQLite do KOSMOS.

---

### Roteiro C — HUB lendo um capítulo do AETHER

**Situação:** Você quer entender como o HUB consegue exibir capítulos do AETHER sem chamar nenhuma API HTTP.

**Ordem de leitura:**

1. **[HUB/src/views/WritingView.tsx](HUB/src/views/WritingView.tsx)** — O componente React que mostra a lista de projetos e livros. Veja como ele chama funções do `tauri.ts`.

2. **[HUB/src/lib/tauri.ts](HUB/src/lib/tauri.ts)** — Procure `read_chapter`. É o wrapper que transforma `invoke("read_chapter", {...})` em `TauriResult<string>`.

3. **[HUB/src-tauri/src/commands/writing.rs](HUB/src-tauri/src/commands/writing.rs)** — A função Rust que recebe os parâmetros, monta o caminho do arquivo `.md` e lê do disco.

4. **[AETHER/src-tauri/src/types.rs](AETHER/src-tauri/src/types.rs)** — Os structs Rust que definem o formato de `Project`, `Book`, `ChapterMeta` — o HUB usa os mesmos tipos.

**Insight:** O HUB nunca chama HTTP para o AETHER. O Rust do HUB lê os arquivos JSON e Markdown diretamente do vault. Por isso o AETHER não precisa estar rodando para o HUB mostrar os projetos.

---

### Roteiro D — Mnemosyne respondendo uma pergunta

**Situação:** Você quer entender o caminho completo de uma pergunta RAG: do input do usuário até a resposta do LLM.

**Ordem de leitura:**

1. **[Mnemosyne/gui/main_window.py](Mnemosyne/gui/main_window.py)** — O campo de input da aba "Ask". Quando o usuário confirma, cria um `AskWorker`.

2. **[Mnemosyne/gui/workers.py](Mnemosyne/gui/workers.py)** — `AskWorker(QThread)`: roda em background para não travar a UI. Chama `rag.ask()`.

3. **[Mnemosyne/core/rag.py](Mnemosyne/core/rag.py)** — A função `ask()`: recupera os chunks mais relevantes do ChromaDB (semântico) + BM25 (keyword), monta o prompt com o contexto, e envia ao LLM.

4. **[Mnemosyne/core/ollama_client.py](Mnemosyne/core/ollama_client.py)** → **[ecosystem_client.py](ecosystem_client.py)** — `request_llm()` tenta primeiro o LOGOS (`:7072`), cai no Ollama direto (`:11434`) se o HUB não estiver rodando.

5. **[HUB/src-tauri/src/commands/logos.rs](HUB/src-tauri/src/commands/logos.rs)** — Onde o LOGOS recebe a requisição, aplica a fila de prioridade e encaminha para o Ollama.

---

### Roteiro E — Como adicionar um novo campo ao ecosystem.json

**Situação:** Você quer que um novo app (ou feature) se registre no ecossistema.

**Ordem de leitura:**

1. **[ecosystem_client.py](ecosystem_client.py)** — Veja o dicionário `_DEFAULTS` para entender o schema. A função `write_section(app_name, data_dict)` é o que você vai chamar no startup do app Python.

2. **[AKASHA/main.py](AKASHA/main.py)** — Procure por `write_section` ou `register_akasha()` — um exemplo real de como um app Python se registra.

3. **[AETHER/src-tauri/src/ecosystem.rs](AETHER/src-tauri/src/ecosystem.rs)** — O equivalente em Rust: lê o JSON, atualiza a seção, escreve de volta com lock de arquivo.

4. **[HUB/src-tauri/src/ecosystem.rs](HUB/src-tauri/src/ecosystem.rs)** — Mesmo padrão, para referência.

---

## 5. Workflow de Desenvolvimento

### Pré-requisitos para rodar o ecossistema

Antes de tudo, confirme que você tem instalado:

```bash
# Python — gerenciador de pacotes
uv --version       # apps Python (AKASHA, KOSMOS, Hermes, Mnemosyne)

# Rust + Node — apps Tauri
rustc --version
cargo --version
node --version
npm --version

# LLM local — necessário para KOSMOS AI, Mnemosyne, LOGOS
ollama --version
ollama list        # lista modelos baixados
```

### Como iniciar cada app

**Apps Python (todos têm scripts prontos):**

```bash
# AKASHA
cd AKASHA
uv run main.py
# Ou use o script: bash iniciar.sh (Linux) / iniciar.bat (Windows)

# KOSMOS
cd KOSMOS
python main.py
# (requer .venv com requirements.txt instalado)

# Hermes
cd Hermes
python hermes.py

# Mnemosyne
cd Mnemosyne
python main.py
```

**Apps Tauri (AETHER e HUB):**

```bash
# Modo desenvolvimento (com hot-reload)
cd AETHER
npm run dev      # inicia Vite :5174 + Tauri

cd HUB
npm run dev      # inicia Vite :5173 + Tauri
```

**App Electron (OGMA):**

```bash
cd OGMA
npm run dev      # inicia Vite :5175 + Electron
```

### Ordem recomendada de inicialização

Para ter tudo funcionando junto:

```
1. Ollama (se quiser IA)
2. HUB  ← sempre primeiro; configura o ecosystem.json e o LOGOS
3. AKASHA  ← mecanismo de busca, usado por outros
4. KOSMOS  ← registra sua porta no ecosystem.json
5. Hermes  ← registra output_dir no ecosystem.json
6. Mnemosyne  ← lê os caminhos já registrados
7. AETHER / OGMA  ← independentes, podem iniciar a qualquer momento
```

Na prática, você provavelmente vai rodar só os apps que precisa para a feature que está desenvolvendo. Não é necessário ter todos abertos.

### Como verificar se o ecossistema está conectado

```bash
# Ver o estado atual do ecosystem.json:
cat ~/.local/share/ecosystem/ecosystem.json
# (ou %APPDATA%\ecosystem\ecosystem.json no Windows)

# Checar health dos apps com servidor HTTP:
curl http://localhost:7071/health   # AKASHA
curl http://localhost:8965/health   # KOSMOS
curl http://localhost:7072/health   # Hermes / LOGOS
```

### Passo a passo seguro para adicionar uma feature

Siga esta sequência sempre. Ela existe para garantir que você não perde trabalho e que o projeto permanece navegável.

**1. Anote no TODO.md primeiro**

Antes de escrever qualquer código, abra o [TODO.md](TODO.md) e adicione o item na seção correta. Um item bem escrito deve ter instrução suficiente para ser implementado sem lembrar da conversa original:

```markdown
### Minha feature nova | 2026-05-11
> Contexto: Precisei de X porque Y.
#### AKASHA
- [ ] Adicionar endpoint GET /minha-rota que faz Z, lendo da tabela T
      com parâmetro `q` (string, obrigatório).
```

**2. Identifique qual camada mudar**

Use a estrutura de diretórios desta seção 2 para localizar onde mexer:
- Nova rota HTTP? → `routers/` (Python) ou `commands/` (Rust)
- Nova lógica de negócio? → `services/` ou `core/`
- Novo modelo de dado? → `database.py` (AKASHA) ou `models.py` (KOSMOS) ou `database.ts` (OGMA)
- Nova tela? → `ui/views/` (Python Qt) ou `src/views/` (React)

**3. Implemente seguindo o padrão de erros do stack**

Consulte a Seção 3 para o padrão exato. A regra prática:
- Criou uma função Python? Ela deve declarar qual exceção lança (ou retornar `None` explicitamente).
- Criou uma função Rust? Deve retornar `Result<T, AppError>`.
- Criou uma chamada IPC em TypeScript? Use o wrapper `call<T>()` de `tauri.ts`, não `invoke()` diretamente.

**4. Teste isoladamente antes de integrar**

Para apps com servidor HTTP, teste o endpoint direto:
```bash
curl -X POST http://localhost:7071/minha-rota \
     -H "Content-Type: application/json" \
     -d '{"q": "teste"}'
```

Para apps Qt, rode o app e teste o fluxo visualmente antes de qualquer integração.

**5. Verifique que o ecosystem.json não foi corrompido**

Depois de iniciar o app com a feature nova:
```bash
python -c "import json; json.load(open('~/.local/share/ecosystem/ecosystem.json'))"
# Se retornar sem erro, o JSON está válido.
```

**6. Marque `[x]` no TODO e faça commit**

Um commit por item concluído:
```bash
git add AKASHA/routers/minha_rota.py AKASHA/services/minha_logica.py
git commit -m "feat(AKASHA): adicionar endpoint GET /minha-rota para X"
```

### Quando algo der errado

**O app não inicia:**
- Verifique se o `ecosystem.json` está válido (JSON malformado pode travar o startup)
- Verifique se a porta já está em uso: `ss -tlnp | grep 7071`

**O HUB não está vendo os dados de outro app:**
- Confirme que o outro app iniciou e escreveu no `ecosystem.json`
- Reinicie o HUB (ele lê o `ecosystem.json` só no startup)

**Erro de LLM / Ollama:**
- `curl http://localhost:11434/api/tags` — verifica se Ollama está rodando
- Se o HUB não estiver rodando, LOGOS não está disponível — os apps caem no Ollama direto automaticamente

**ChromaDB não está encontrando documentos:**
- Verifique se o diretório de indexação existe e tem arquivos
- Apague `{collection_path}/.mnemosyne/index_checkpoint.db` para forçar reindexação completa

---

*Este guia foi gerado em 2026-05-11 a partir da exploração completa do código. Se encontrar discrepâncias, o código-fonte é a verdade — atualize este guia.*

---

## Anexo — Fundamentos e Mecânica do Ecossistema

> **Para quem é esta seção:** Para quando você quer entender o *porquê* das escolhas e o *como* das engrenagens — não só onde os arquivos estão, mas o que está acontecendo por baixo dos panos. Leia isso quando sentir que está programando sem entender o que está fazendo.

---

### A.1 — A Razão das Ferramentas (Os "Porquês")

#### Por que Tauri no AETHER e HUB, mas Electron no OGMA?

Primeiro, o que eles têm em comum: os três são **apps desktop feitos com tecnologia web** (React + TypeScript na interface). A diferença está no *motor* que faz o React virar uma janela no seu computador.

**Electron** é o veterano. Ele funciona assim: junto com seu app, ele empacota uma cópia inteira do Chrome e uma cópia inteira do Node.js. O resultado é um binário de ~150-200 MB. A vantagem é que você tem o ecossistema npm inteiro disponível no "backend" do app — qualquer biblioteca JavaScript funciona.

**Tauri** é mais moderno e mais enxuto. Em vez de empacotar o Chrome, ele usa o WebView nativo do sistema operacional (o mesmo que o Windows ou Linux já tem instalado). E em vez de Node.js como backend, usa Rust — uma linguagem compilada, tipada e muito mais eficiente. O resultado é um binário de ~5-15 MB.

**Por que o AETHER e o HUB são Tauri:**
- O AETHER guarda escrita criativa pessoal. Rust tem garantias de segurança de memória em nível de compilação — o compilador força você a tratar erros. Isso importa quando você está manipulando arquivos que a usuária não quer perder.
- O HUB está sempre rodando em background. Um processo de 15 MB que usa 30 MB de RAM é muito diferente de um de 200 MB usando 300 MB.
- As operações do HUB/AETHER são basicamente I/O de arquivos — ler JSON, ler Markdown, escrever de volta. Rust faz isso de forma nativa e eficiente, sem precisar de Node.js.

**Por que o OGMA é Electron:**
O OGMA foi construído em torno de duas dependências que são profundamente Node.js:
- `better-sqlite3`: uma binding nativa de SQLite para Node.js. Não existe equivalente igual para Tauri/Rust (o Rust tem suas próprias bibliotecas SQLite, mas reescrever toda a camada de dados seria um trabalho enorme).
- EditorJS: um editor de blocos rico que roda no navegador e depende do ecossistema npm.

Migrar o OGMA para Tauri exigiria reescrever toda a camada de banco de dados em Rust. O custo não justifica o benefício.

**Diferença prática quando você vai programar:**

| Situação | Em Tauri (AETHER/HUB) | Em Electron (OGMA) |
|---|---|---|
| Criar uma função de backend | Escreve em Rust (`.rs`) | Escreve em TypeScript Node.js (`.ts`) |
| Erros de compilação | O compilador Rust é rigoroso — falha antes de rodar | TypeScript ajuda, mas erros aparecem em runtime |
| Acessar o filesystem | `std::fs` do Rust | `fs` do Node.js |
| Adicionar uma dependência | `Cargo.toml` + `cargo add` | `package.json` + `npm install` |
| Depurar o backend | `println!()` ou `log::debug!()` | `console.log()` normal |

---

#### Por que FastAPI no AKASHA, mas PyQt6 no KOSMOS e no Mnemosyne?

Esta é a distinção mais fundamental: são **categorias diferentes de aplicativo**.

**FastAPI = servidor web.** Você acessa o AKASHA abrindo `http://localhost:7071` no navegador. O FastAPI recebe requisições HTTP, processa, e devolve HTML (via Jinja2 + HTMX) ou JSON. Pense nele como o Django ou o Flask — é um servidor que *serve* conteúdo para um cliente (o browser).

**PyQt/PySide = app desktop com janela própria.** O KOSMOS e o Mnemosyne não têm servidor. Eles criam uma janela do sistema operacional diretamente, com botões, abas, listas — como o VLC ou o LibreOffice.

**Por que o AKASHA usa FastAPI em vez de PyQt?**

O AKASHA é um mecanismo de busca. A metáfora natural é um browser. Você digita uma query, aperta Enter, vê os resultados em HTML, clica num link — isso é exatamente o que browsers fazem. Construir isso com HTMX (que atualiza partes da página sem reload) no FastAPI é mais simples e mais adequado do que criar widgets Qt para simular esse comportamento.

Além disso, o AKASHA pode ser acessado de qualquer lugar da rede local — você pode abrir no celular, em outro computador. Um app Qt está preso na máquina onde roda.

**Por que o KOSMOS e o Mnemosyne usam PyQt em vez de FastAPI?**

Esses apps precisam de comportamentos que são nativos de desktop:
- **Threads em background:** o KOSMOS baixa feeds enquanto você lê artigos. Fazer isso num servidor web exigiria WebSockets ou polling.
- **Notificações do sistema:** um app desktop pode mostrar notificações nativas. Um servidor web não.
- **Persistência de estado entre sessões:** a janela do KOSMOS "lembra" onde você estava. Um servidor web é stateless por natureza.
- **Interface rica:** o leitor de artigos do KOSMOS usa um WebView embutido (Chromium dentro do Qt) para renderizar HTML de forma nativa. Isso não é trivial num app web.

**A regra prática:** Se a "tela" do seu app vai ser um browser, use FastAPI. Se vai ser uma janela do sistema operacional com menus, abas e widgets, use PyQt/PySide.

---

### A.2 — Como as Engrenagens Giram (Fluxo de Dados)

#### IPC — A Ponte entre Frontend (React) e Backend (Rust/Node)

Imagine que seu app desktop tem duas salas:

- **Sala do Frontend (React):** É o Chromium (o browser embutido). Tudo que o usuário vê existe aqui — componentes, botões, estados visuais. **Por segurança, essa sala não tem acesso ao disco, à rede local, nem ao sistema operacional.** Ela vive num sandbox.
- **Sala do Backend (Rust ou Node.js):** É o processo nativo. Tem acesso total ao sistema de arquivos, às configurações, às portas de rede. Mas não tem interface visual.

O IPC (Inter-Process Communication) é o interfone entre as duas salas. Toda vez que o React precisa de um dado do disco ou quer salvar algo, ele *manda uma mensagem* pelo interfone. O backend processa e *responde*.

---

**Como funciona no Tauri (AETHER e HUB):**

O ciclo completo de uma chamada tem 4 etapas:

**Etapa 1 — Escrever a função Rust** (em `src-tauri/src/commands/meu_modulo.rs`):

```rust
use crate::error::AppError;

#[tauri::command]  // ← essa anotação torna a função visível para o React
pub fn ler_arquivo(caminho: String) -> Result<String, AppError> {
    let conteudo = std::fs::read_to_string(&caminho)
        .map_err(|e| AppError::Io(e.to_string()))?;
    Ok(conteudo)
}
```

O `#[tauri::command]` é como colocar um rótulo na função dizendo "esta pode ser chamada pelo frontend". Sem ele, o React não consegue ver a função.

**Etapa 2 — Registrar a função** (em `src-tauri/src/lib.rs`):

```rust
.invoke_handler(tauri::generate_handler![
    commands::meu_modulo::ler_arquivo,
    // ... outros comandos já existentes
])
```

O `generate_handler!` cria uma tabela de roteamento: quando o React chamar `"ler_arquivo"`, o Tauri sabe que deve executar `commands::meu_modulo::ler_arquivo`.

**Etapa 3 — Criar o wrapper TypeScript** (em `src/lib/tauri.ts`):

```typescript
// Adicionar junto dos outros wrappers existentes
export async function lerArquivo(caminho: string): Promise<TauriResult<string>> {
    return call<string>("ler_arquivo", { caminho })
    //    ↑ função genérica que já existe no arquivo e normaliza erros
}
```

O `call<T>()` já existe no arquivo — ele faz o `invoke()` do Tauri e converte o resultado (ou erro) para o padrão `TauriResult<T>` do ecossistema.

**Etapa 4 — Usar no componente React:**

```tsx
import { lerArquivo } from '../lib/tauri'

function MeuComponente() {
    const [conteudo, setConteudo] = useState<string>('')

    async function handleClick() {
        const resultado = await lerArquivo("/caminho/do/arquivo")
        if (!resultado.ok) {
            // mostrar toast de erro — resultado.error.message é tipado
            return
        }
        setConteudo(resultado.data)  // TypeScript sabe que é string aqui
    }

    return <button onClick={handleClick}>Ler arquivo</button>
}
```

---

**Como funciona no Electron (OGMA):**

O Electron tem uma camada extra de segurança chamada `preload.ts`. Ela age como um porteiro: só o que for explicitamente exposto no preload fica acessível ao React. Isso evita que código malicioso no renderer acesse o sistema.

O ciclo tem 4 etapas similares, mas numa estrutura diferente:

**Etapa 1 — Escrever o handler** (em `src/main/ipc.ts`):

```typescript
ipcMain.handle("meuapp:lerArquivo", async (_, { caminho }: { caminho: string }) => {
    const conteudo = fs.readFileSync(caminho, 'utf-8')
    return conteudo
    // Erros não capturados aqui serão pegos pelo fromIpc() no renderer
})
```

**Etapa 2 — Expor no preload** (em `src/main/preload.ts`):

```typescript
// Adicionar dentro do objeto já existente em contextBridge.exposeInMainWorld('db', {...})
meuapp: {
    lerArquivo: (caminho: string) => api('meuapp:lerArquivo', { caminho })
}
```

**Etapa 3 — Tipar no renderer** (em `src/renderer/types/index.ts`, se necessário):

O `window.db.meuapp.lerArquivo(...)` já estará disponível após o preload. O TypeScript pode precisar de declaração de tipo, mas o código funciona.

**Etapa 4 — Usar no componente ou store React:**

```typescript
// No store (useAppStore.ts) ou diretamente no componente:
const resultado = await fromIpc<string>(
    () => (window.db as any).meuapp.lerArquivo(caminho),
    "meuapp:lerArquivo"
)
resultado.match(
    (conteudo) => setConteudo(conteudo),
    (erro)     => pushToast({ kind: 'error', title: erro.message })
)
```

**Diferença essencial:** No Tauri, o "portão" de segurança é o `generate_handler![]` no Rust — só funções registradas ali existem. No Electron, o "portão" é o `preload.ts` — só o que for exposto via `contextBridge` existe no renderer.

---

#### Gerenciamento de Estado no React — Como as informações ficam na tela

**O problema:** React re-renderiza componentes. Toda vez que o componente re-renderiza, variáveis locais são recriadas do zero. Como guardar informações entre renders?

**A solução básica — `useState`:** Um hook que persiste um valor entre renders. Quando você chama `setValor(novoValor)`, o React re-renderiza o componente com o novo valor.

```tsx
const [projetos, setProjetos] = useState<Project[]>([])
// projetos persiste entre renders; setProjetos atualiza e re-renderiza
```

**O problema do estado compartilhado:** Se o componente A e o componente B precisam do mesmo dado, você pode guardar no pai deles e passar via props. Mas quando você tem 4-5 níveis de componentes, passar props por todos os níveis fica tedioso (isso se chama "prop drilling").

**Como o AETHER e o HUB resolvem:** Estado no `App.tsx` (o componente raiz), passado para baixo. Funciona porque a hierarquia de componentes é relativamente simples — poucas telas, poucos dados compartilhados.

```tsx
// App.tsx do HUB — estado centralizado no topo
const [selectedProject, setSelectedProject] = useState<Project | null>(null)
const [selectedBook, setSelectedBook] = useState<Book | null>(null)

// Passado para as views:
<WritingView
    project={selectedProject}
    book={selectedBook}
    onSelectProject={setSelectedProject}
/>
```

**Como o OGMA resolve — Zustand:** Uma "loja" global. Qualquer componente importa o store e acessa diretamente o que precisa, sem receber props.

Pense no Zustand como uma prateleira pública na cozinha. Qualquer pessoa na casa pode pegar ou colocar coisas nela diretamente — sem precisar pedir para alguém passar.

```typescript
// Qualquer componente pode fazer isso, sem receber props:
const { projects, activeProject, selectProject, loadPages } = useAppStore()

// Quando selectProject() é chamado, todos os componentes que usam
// activeProject são atualizados automaticamente.
```

O store do OGMA ([OGMA/src/renderer/store/useAppStore.ts](OGMA/src/renderer/store/useAppStore.ts)) guarda dois tipos de coisas:

1. **Dados:** `workspace`, `projects`, `pages`, `activeProject` — o conteúdo real
2. **Estado de UI:** `dark`, `loading`, `toasts` — como a interface está se comportando
3. **Ações:** `loadProjects()`, `selectProject()`, `createProject()` — funções que modificam os dados

Mutações que precisam de feedback inline (mostrar erro na própria tela) retornam `Result<T, AppError>`. Carregamentos que mostram erros como toast retornam `void`.

**Quando usar Zustand vs props:** Use Zustand quando o mesmo dado é acessado em mais de 2-3 componentes que não têm relação direta de pai-filho. Para dados locais de um componente específico, `useState` é suficiente.

---

#### Concorrência no Python — Por que a interface não trava

**O problema:** Python tem uma restrição fundamental chamada GIL (Global Interpreter Lock) — em geral, apenas uma thread Python executa código de verdade por vez. E o Qt tem outra restrição: **a interface gráfica só pode ser atualizada pela thread principal**.

Se você colocar uma operação lenta (baixar um arquivo de 500 MB, buscar 100 feeds RSS, transcrever um vídeo de 1 hora) na thread principal do Qt, a janela congela. O usuário não consegue nem mover a janela.

**A solução — QThread + Sinais:**

Analogia: imagine um restaurante. O garçom (thread principal Qt) não vai até a cozinha buscar a comida — ele passaria um tempo enorme lá e os outros clientes esperariam. Existe um cozinheiro (QThread) que faz o trabalho pesado. Quando o prato fica pronto, o cozinheiro avisa o garçom pelo interfone (sinal), e o garçom leva ao cliente.

Os sinais (pyqtSignal) são o interfone thread-safe do Qt. São a *única* forma correta de comunicar de uma thread worker para a thread principal.

Aqui está o padrão real do KOSMOS ([KOSMOS/app/core/background_updater.py](KOSMOS/app/core/background_updater.py)):

```python
from PyQt6.QtCore import QThread, pyqtSignal

class BackgroundUpdater(QThread):
    # Declaração dos sinais — tipos dos argumentos entre parênteses
    feed_updated   = pyqtSignal(int, int)   # feed_id, quantidade de novos artigos
    update_error   = pyqtSignal(int, str)   # feed_id, mensagem de erro
    cycle_started  = pyqtSignal()
    cycle_finished = pyqtSignal(int)        # total de novos artigos no ciclo

    def run(self):
        """Este método roda em thread separada. NUNCA toque na UI aqui."""
        self.cycle_started.emit()  # avisa a thread principal: ciclo iniciou

        for feed in self.feed_manager.list_feeds():
            try:
                novos = self._fetch_feed(feed)
                self.feed_updated.emit(feed.id, novos)  # thread-safe
            except Exception as exc:
                self.update_error.emit(feed.id, str(exc))

        self.cycle_finished.emit(total_novos)
```

E na janela principal, conectar os sinais aos métodos da UI:

```python
# Em main_window.py ou main.py:
self.updater = BackgroundUpdater(feed_manager=self.feed_manager)

# Conectar sinais a slots (métodos da UI):
self.updater.feed_updated.connect(self._on_feed_updated)
self.updater.update_error.connect(self._on_update_error)
self.updater.cycle_finished.connect(self._on_cycle_finished)

self.updater.start()  # lança a thread — run() começa a executar em paralelo
```

**Regras que nunca devem ser quebradas:**
1. **Nunca atualizar widgets Qt de dentro de `run()`.** Use `emit()` para avisar a thread principal, e deixe ela atualizar a UI.
2. **Nunca acessar o mesmo objeto de banco de dados de threads diferentes** sem sincronização. O KOSMOS cria sessões SQLAlchemy separadas por thread.
3. **Sempre guardar a referência ao worker.** `self.worker = MeuWorker()` — se você não guardar, o Python apaga o objeto e a thread morre silenciosamente.

**asyncio no AKASHA (diferente de QThread):** O AKASHA usa FastAPI, que é assíncrono. Em vez de threads, usa `async/await` — uma única thread que pode "pausar" enquanto espera I/O (rede, disco) e processar outra coisa nesse intervalo. É mais eficiente para muitas operações de rede simultâneas. Mas só funciona em contextos assíncronos (FastAPI, asyncio) — não misture com Qt.

---

### A.3 — Banco de Dados e Persistência

#### Quando usar arquivos, quando usar SQLite

A decisão certa vem de duas perguntas:

**1. Como você vai acessar esses dados?**
- Vai ler o arquivo inteiro de uma vez? → Arquivo
- Vai filtrar por data, buscar por palavra, ordenar por campo? → SQLite

**2. Os dados têm relacionamentos entre si?**
- Cada item é independente? → Arquivo
- Um artigo tem tags, uma tag tem vários artigos, um artigo tem highlights? → SQLite

Veja as decisões reais do ecossistema:

| App | Onde guarda | Por quê |
|-----|-------------|---------|
| AETHER capítulos | `.md` no vault | Um capítulo = um arquivo. Legível no editor de texto. Portável. Sem consultas. |
| AETHER projetos | `project.json` | Metadados simples que são sempre lidos juntos. |
| AKASHA páginas crawladas | SQLite | Milhares de páginas, precisa de busca full-text (FTS5), filtro por domínio, deduplicação por hash. |
| OGMA páginas | SQLite | Hierarquia (parent_id), propriedades customizadas, múltiplas views configuráveis. |
| KOSMOS artigos | SQLite | Tags M2M, highlights, sessões de leitura — relacionamentos reais. |
| Mnemosyne histórico | `.jsonl` append-only | Log cronológico que só cresce. Nunca precisa buscar por campo. |
| Mnemosyne memória de sessão | `.json` | Pequeno, sempre lido inteiro, reescrito inteiro. |

**A regra mais simples:** Se você vai fazer `SELECT * FROM tabela WHERE campo = ?`, use SQLite. Se vai fazer `with open(arquivo) as f: return f.read()`, use arquivo.

---

#### Como criar uma nova tabela no AKASHA (migrações passo a passo)

O AKASHA usa um sistema de migrações caseiro, simples e eficaz. Entendê-lo te dá autonomia para expandir o banco sem medo.

**Como funciona:** A tabela `settings` guarda um registro `('schema_version', '15')`. No startup, `init_db()` compara esse número com a constante `SCHEMA_VERSION` no topo de `database.py`. Se o banco está desatualizado, `_migrate()` aplica os passos necessários em sequência.

**Para adicionar uma nova tabela:**

**Passo 1 — Definir o schema** (no topo de [AKASHA/database.py](AKASHA/database.py)):

```python
# Adicionar junto das outras constantes _CREATE_*
_CREATE_FAVORITOS_TAGS = """
CREATE TABLE IF NOT EXISTS favoritos_tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    favorite_id INTEGER NOT NULL REFERENCES favorites(id) ON DELETE CASCADE,
    tag         TEXT    NOT NULL,
    criado_em   TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""
```

O `IF NOT EXISTS` é importante: permite rodar o script várias vezes sem erro. `REFERENCES favorites(id) ON DELETE CASCADE` significa que, se o favorito for apagado, as tags associadas também somem — integridade referencial.

**Passo 2 — Chamar no `init_db()`:**

```python
async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        # ... tabelas existentes ...
        await db.execute(_CREATE_FAVORITOS_TAGS)  # ← adicionar aqui
        await db.commit()
```

**Passo 3 — Incrementar a versão:**

```python
# No topo de database.py:
SCHEMA_VERSION = 16  # era 15
```

**Passo 4 — Adicionar o bloco de migração em `_migrate()`:**

```python
async def _migrate(db: aiosqlite.Connection, from_version: int) -> None:
    # ... migrações anteriores ...

    if from_version < 16:
        await db.execute(_CREATE_FAVORITOS_TAGS)
        # Se fosse adicionar uma coluna em tabela existente:
        # await db.execute("ALTER TABLE favorites ADD COLUMN cor TEXT DEFAULT '#b8860b'")
```

**Por que o `_CREATE_FAVORITOS_TAGS` aparece tanto no `init_db()` quanto no `_migrate()`?**

- `init_db()` é chamado sempre no startup. O `IF NOT EXISTS` garante que criar a tabela de novo não causa erro em bancos que já a têm.
- `_migrate()` é o que garante que bancos *antigos* (sem a tabela) recebam a nova estrutura.

**Coisas que você não pode fazer numa migração:**
- `DROP TABLE` sem antes salvar os dados em outra tabela
- `ALTER TABLE` para *remover* uma coluna (SQLite não suporta — você precisa criar uma tabela nova, copiar os dados, apagar a antiga e renomear)
- Alterar o tipo de uma coluna existente (mesma limitação)

Para essas operações complexas, o padrão é: criar tabela nova com o schema desejado → `INSERT INTO nova SELECT ... FROM antiga` → `DROP TABLE antiga` → `ALTER TABLE nova RENAME TO antiga`.

---

### A.4 — O Blueprint de Reconstrução

#### Se o KOSMOS fosse apagado hoje: como recriar do zero

Este exercício existe para você internalizar que um app Python + Qt tem uma estrutura previsível e reproducível. Cada passo tem uma lógica.

---

**Passo 1 — Estrutura de pastas e dependências**

A arquitetura de um app Python + Qt segue sempre a separação: lógica de negócio (`core/`) separada da interface (`ui/`). Isso é importante porque permite testar a lógica sem abrir janelas.

```
KOSMOS/
├── main.py           ← entrada única
├── requirements.txt  ← dependências
├── iniciar.sh        ← script de conveniência para Linux
├── app/
│   ├── core/         ← lógica de negócio (sem Qt, testável)
│   │   ├── __init__.py
│   │   ├── models.py     ← classes de dados
│   │   ├── database.py   ← conexão e schema
│   │   └── errors.py     ← exceções específicas
│   └── ui/           ← interface Qt (depende de core/)
│       ├── __init__.py
│       └── main_window.py
└── app/theme/
    └── style.qss     ← estilos Qt
```

O `requirements.txt` do KOSMOS começa com:
```
PyQt6>=6.7
SQLAlchemy>=2.0
feedparser>=6.0
requests>=2.32
```

---

**Passo 2 — O ponto de entrada (`main.py`)**

Todo app Qt tem a mesma estrutura básica de entrada:

```python
import sys
from PyQt6.QtWidgets import QApplication
from app.ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)      # cria o runtime Qt
    window = MainWindow()             # cria a janela principal
    window.show()                     # torna visível
    sys.exit(app.exec())              # entra no loop de eventos Qt

if __name__ == "__main__":
    main()
```

O `app.exec()` é o coração: é um loop infinito que fica esperando eventos (cliques, teclas, sinais de rede) e os despacha para os componentes certos. Quando `sys.exit()` é chamado, o loop para e o processo encerra.

---

**Passo 3 — A camada de dados (`core/`)**

Aqui você define o *que* o app sabe, sem se preocupar com *como* vai mostrar. Para o KOSMOS, isso são os modelos SQLAlchemy:

```python
# app/core/errors.py — sempre crie as exceções primeiro
class KosmosError(Exception):
    """Base de todos os erros do KOSMOS."""

class FeedError(KosmosError):
    """Erro ao manipular um feed."""

class DatabaseError(KosmosError):
    """Erro de banco de dados."""
```

```python
# app/core/models.py
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Feed(Base):
    __tablename__ = "feeds"
    id      = Column(Integer, primary_key=True)
    url     = Column(String, unique=True, nullable=False)
    nome    = Column(String, nullable=False, default="")
    tipo    = Column(String, nullable=False, default="rss")
```

```python
# app/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

def init_database(db_path: str):
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)  # cria tabelas que não existem
    return sessionmaker(bind=engine)
```

---

**Passo 4 — A interface Qt (`ui/main_window.py`)**

A janela principal herda de `QMainWindow`. Aqui você monta os widgets e conecta sinais às ações da camada `core/`:

```python
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QPushButton
from app.core.database import init_database

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KOSMOS")
        self.setMinimumSize(800, 600)

        # Inicializa o banco de dados
        self.Session = init_database("kosmos.db")

        # Monta a interface
        central = QWidget()
        layout = QVBoxLayout(central)
        self.setCentralWidget(central)

        btn = QPushButton("Adicionar Feed")
        btn.clicked.connect(self._on_adicionar_feed)  # sinal → slot
        layout.addWidget(btn)

    def _on_adicionar_feed(self):
        """Slot chamado quando o botão é clicado."""
        # Aqui você abre um diálogo, pega a URL, chama core/ para salvar
        pass
```

---

**Passo 5 — Registrar no ecossistema**

Esta é a etapa que conecta o novo app ao resto. No final do `main()`, antes de `app.exec()`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))  # acesso à raiz do ecossistema

from ecosystem_client import write_section

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    # Registrar no ecosystem.json — outros apps vão saber que o KOSMOS está rodando
    write_section("kosmos", {
        "data_path":    str(Path.home() / ".local/share/kosmos"),
        "archive_path": str(Path.home() / ".local/share/kosmos/archive"),
        "http_port":    8965,
    })

    sys.exit(app.exec())
```

Após registrar, o HUB vai detectar o KOSMOS, o AKASHA vai saber para onde mandar feeds, e o LOGOS vai saber qual porta usar. O app passa a existir no ecossistema.

---

**O que esses 5 passos te ensinam:**

Todo app Python + Qt que você já construiu ou vai construir segue esta lógica:
1. Definir a estrutura de pastas (core separado de ui)
2. Criar o ponto de entrada com o loop Qt
3. Definir modelos de dados e erros tipados
4. Construir a janela herdando de QMainWindow e conectando sinais
5. Escrever no ecosystem.json no startup

A complexidade do KOSMOS real (BackgroundUpdater, feedparser, artigos, highlights, AI) é apenas a expansão desses 5 passos — não uma mudança de paradigma. Quando você entende os 5 passos, entende o app inteiro.

---

*Anexo gerado em 2026-05-11. Atualizar conforme o ecossistema evolui.*
