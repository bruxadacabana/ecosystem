# Ecossistema — TODO

> Arquivo único consolidando os TODOs de todos os apps e o roadmap de integração.
> Atualizado em: 2026-04-27

---

## Padrões Obrigatórios do Ecossistema

### Tipagem e erros (todas as stacks)

- **Rust (AETHER · HUB):** toda função falível retorna `Result<T, AppError>`. Zero `.unwrap()` ou `.expect()` em produção.
- **TypeScript (OGMA · HUB):** `strict: true` obrigatório. Erros tipados com discriminated unions — `{ ok: true; data: T } | { ok: false; error: AppError }`. Nunca `any`, nunca `catch (e: any)` sem re-tipar.
- **Python (KOSMOS · Mnemosyne · Hermes · AKASHA):** `except ValueError` (específico), nunca `except Exception` genérico sem re-tipar. Funções críticas anotadas com `-> T | None` ou via `Result` pattern.
- Nenhum item está "pronto" se o caminho de erro não for tratado com a mesma atenção que o caminho feliz.

### Workflow de desenvolvimento

- Commit após CADA item individual do TODO — não após fases ou grupos.
- Manter cada TODO de app atualizado. Acrescentar ANTES de implementar qualquer coisa não listada.
- Nunca começar a implementar nada sem ordem explícita. Discussão e planejamento não são ordens.
- Nunca avançar de um item para o próximo sem aprovação explícita.
- Após concluir cada item: parar, resumir o que foi feito, aguardar permissão para prosseguir.
- **Compatibilidade:** todos os apps devem rodar no Windows 10 e no CachyOS (Linux). Sem paths hardcoded. Testar caminhos com espaços.

---

## Ecossistema — Integração e Infraestrutura

### Fase 0 — Fundação do ecossistema

> Pré-requisito para todas as fases seguintes.
> Arquivo de contrato em `~/.local/share/ecosystem/ecosystem.json` (Linux) / `%APPDATA%\ecosystem\ecosystem.json` (Windows).

- [x] Criar `ecosystem.json` em `~/.local/share/ecosystem/` com caminhos reais do KOSMOS
- [x] Criar `ecosystem_client.py` — utilitário Python compartilhado (KOSMOS, Mnemosyne, Hermes). Funções: `ecosystem_path()`, `read_ecosystem()`, `write_section()` com escrita atômica
- [x] Criar `OGMA/src/main/ecosystem.ts` — utilitário TypeScript para OGMA
- [x] Criar `AETHER/src-tauri/src/ecosystem.rs` — módulo Rust para AETHER
- [x] Adicionar `dirs = "5"` em `AETHER/src-tauri/Cargo.toml`
- [x] Wiring em `AETHER/src-tauri/src/lib.rs`: escreve `vault_path` no startup (falha silenciosa)
- [x] Documentar o contrato: quem escreve cada campo, quando, formato

#### 0.5 — sync_root: sincronização via Proton Drive

- [x] `ecosystem_client.py` — `derive_paths(sync_root)` e campo `sync_root` no schema
- [x] `Mnemosyne/core/config.py` — campo `chroma_dir`; `persist_dir` usa-o se definido
- [x] `Mnemosyne/gui/main_window.py` — campo "Pasta do ChromaDB" na SetupDialog
- [x] `AKASHA/config.py` — `ARCHIVE_PATH` lê `akasha.archive_path` do ecosystem.json se disponível
- [x] `HUB/src-tauri/src/commands/config.rs` — comando `apply_sync_root(sync_root)`. Cria subpastas + escreve seções no ecosystem.json via `derive_paths`
- [x] `HUB/src/views/SetupView.tsx` — seção "Sincronização": campo sync_root + botão "Aplicar"
- [x] Instalar e configurar Proton Drive entre máquinas. sync_root aplicado: `C:\Users\USUARIO\Documents\p\My files\backup\ecosystem`. Subpastas criadas; ecosystem.json atualizado.
- [x] Testar round-trip: arquivar página no AKASHA → aparece no Proton → segunda máquina

#### 0.6 — OGMA: migrar de Turso para Proton Drive (SQLite local)

- [x] Remover integração Turso do OGMA (`src/main/database.ts` — voltar para SQLite puro local). Remover `@libsql/client`, `dotenv` e o `.env` com token Turso
- [x] Adicionar `ogma/` ao `sync_root` em `apply_sync_root()` (Rust + derive_paths Python)
- [x] Atualizar `paths.ts` do OGMA para usar `ogma.data_path` do ecosystem.json (fallback local)
- [ ] Testar migração: exportar dados do Turso → importar no SQLite local antes de remover

#### 0.7 — Hermes: usar output_dir do ecosystem.json no startup

- [x] `Hermes/hermes.py` — `_load_prefs()`: se `outdir` não estiver em prefs, ler `hermes.output_dir` do ecosystem.json como fallback

#### 0.8 — AKASHA: integração Hermes + DB no Proton + lista negra + UI

##### 0.8a — AKASHA indexa arquivos do Hermes na busca local

- [x] `AKASHA/config.py` — adicionar `hermes_output: str` lendo `hermes.output_dir` do ecosystem.json
- [x] `AKASHA/services/local_search.py` — adicionar fonte `HERMES` em `index_local_files()`

##### 0.8b — AKASHA: DB movível para Proton

- [x] `AKASHA/config.py` — `DB_PATH` lê `akasha.data_path` do ecosystem.json se disponível
- [x] `ecosystem_client.py` — `derive_paths()`: adicionar `data_path` à seção `akasha`
- [x] `HUB/src-tauri/src/commands/config.rs` — `apply_sync_root()`: incluir `akasha.data_path`

##### 0.8c — AKASHA: aba "lista negra" no menu

- [x] `AKASHA/database.py` — `get_blocked_domains()` já existia
- [x] `AKASHA/routers/domains.py` — rota `GET /domains` com listagem + template
- [x] `AKASHA/templates/domains.html` — nova página herdando base.html
- [x] `AKASHA/templates/base.html` — adicionar link "lista negra" no nav

##### 0.8d — AKASHA: melhorias de UI

- [x] `AKASHA/static/style.css` — classe `.page-subtitle`
- [x] `AKASHA/templates/library.html` e `sites.html` — subtítulos descritivos
- [x] `AKASHA/routers/crawler.py` — rota `POST /sites/add-quick`
- [x] `AKASHA/templates/_macros.html` — botão "Adicionar a Sites" nos cards

#### 0.9 — Mnemosyne: caminhos primários do ecosystem.json

- [ ] `Mnemosyne/core/config.py` — adicionar `extra_dirs: list[str]`; `load_config()` merge ecosystem.json (watched_dir/vault_dir/chroma_dir têm precedência)
- [ ] `Mnemosyne/gui/main_window.py` — SetupDialog: caminhos principais viram read-only (vindos do ecosystem); adicionar QListWidget "Pastas extras" com +/−
- [ ] `Mnemosyne/core/` (indexador) — loop sobre `[watched_dir] + extra_dirs`

#### 0.10 — Arquivos de configuração no Proton Drive

Cada app lê `{sync_root}/{app}/.config/settings.json` com fallback para o arquivo local.

- [x] `derive_paths()` — adicionar `config_path: {sync_root}/{app}/.config` para cada app
- [x] `apply_sync_root()` (Rust) — criar subpastas `.config/` + escrever `config_path` no ecosystem.json
- [x] OGMA — `SETTINGS` em `paths.ts` usa `{ogma.config_path}/settings.json` se disponível
- [x] Hermes — `_load_prefs()` / `_save_prefs()` usa `{hermes.config_path}/settings.json` se disponível
- [x] KOSMOS — `Paths.SETTINGS` usa `{kosmos.config_path}/settings.json` se disponível
- [x] Mnemosyne — `load_config()` / `save_config()` usa `{mnemosyne.config_path}/settings.json` se disponível
- [ ] AKASHA — sem settings.json próprio; config está no akasha.db (sincronizado via 0.8b)
- [ ] AETHER — vault config já fica dentro de vault_path (sincronizado); sem settings separado

#### Extras — Utilitários e manutenção

- [x] `buildar.sh` / `buildar.bat` — scripts de build de produção para todos os apps
- [x] `atualizar.sh` / `atualizar.bat` — git pull + sync de dependências de todos os apps
- [x] `README.md` — seções "Build de produção" e "Atualizar dependências"

#### Extras — Bugs e melhorias urgentes (ecosystem)

- [x] **Race condition no ecosystem.json** — `ecosystem_client.py`: usar `filelock.FileLock` em torno do read-modify-write. `HUB/src-tauri/src/ecosystem.rs`: lock file manual via `fs2`.
- [x] **Caminhos não atualizam nos apps sem reiniciar** — `HUB/src/views/SetupView.tsx`: exibir mensagem após salvar: "Reinicie cada app para aplicar os novos caminhos."
- [x] **KOSMOS — Stats travando e fechando o app** — `stats_view.py`: mover carregamento de dados para `QThread` (StatsLoadWorker)
- [x] **KOSMOS — Archive_path ignora ecosystem.json** — `KOSMOS/app/utils/paths.py`: ler `kosmos.archive_path` do ecosystem.json no startup
- [x] **Hermes — "Descarregar" → "Baixar"** — renomear label do botão, aba e comentário
- [x] **Hermes — UX de playlist confusa** — instrução visual atualizada; auto-seleciona primeiro vídeo ao carregar playlist
- [x] **Mnemosyne — Indexação trava o computador** — `core/indexer.py`: processar chunks em lotes (50 chunks por vez) com `time.sleep(0.1)` entre lotes

---

### Fase 1 — Interligação dos apps existentes

#### 1.1 — OGMA → AETHER (projetos de escrita)

##### Passo A — Renomear tipo `creative` → `writing` no OGMA

- [x] `src/renderer/types/index.ts`: alterar `ProjectType` union e labels
- [x] `src/renderer/components/Projects/NewProjectModal.tsx`: atualizar array TYPES
- [x] `src/main/ipc.ts`: renomear todas as ocorrências do literal `'creative'`
- [x] `src/main/database.ts`: migration `UPDATE projects SET project_type = 'writing' WHERE project_type = 'creative'`

##### Passo B — Integrar projetos de escrita com AETHER

- [x] `src/main/database.ts`: coluna `aether_project_id TEXT` na tabela `projects`
- [x] OGMA lê `aether.vault_path` do ecosystem.json na criação de projeto
- [x] Ao criar projeto `project_type = 'writing'`: OGMA escreve `{vault}/{uuid}/project.json` e livro padrão vazio
- [x] Salvar `aether_project_id` no banco do OGMA
- [x] Botão "Abrir no AETHER" em projetos de escrita

#### 1.2 — KOSMOS → Mnemosyne (artigos salvos)

- [x] KOSMOS escreve `archive_path` e `data_path` em `ecosystem.json` na inicialização
- [x] Mnemosyne oferece archive do KOSMOS como pasta sugerida (botão "Sugestões do ecossistema")
- [ ] Verificar se botão "Arquivar" em artigos salvos chama `archive_manager` corretamente — garantir `.md` válido

#### 1.3 — AETHER → Mnemosyne (indexar escritos)

- [x] AETHER escreve `vault_path` em `ecosystem.json` na inicialização
- [x] Mnemosyne oferece vault AETHER como pasta sugerida
- [ ] Testar indexação dos `.md` de capítulos pelo Mnemosyne

#### 1.4 — Hermes → Mnemosyne (transcrições indexáveis)

- [x] Campo "Pasta de saída do Mnemosyne" na aba Transcrever do Hermes
- [x] Checkbox "Indexar no Mnemosyne após transcrever"
- [x] Formato: Markdown com frontmatter mínimo (título, data, fonte/URL, duração)

#### 1.5 — Completar contrato ecosystem.json

- [x] OGMA — `writeSection("ogma", { data_path, exe_path })` no startup
- [x] Mnemosyne — `write_section("mnemosyne", { watched_dir, vault_dir, index_paths, exe_path })` no startup
- [x] Hermes — `write_section("hermes", { output_dir, exe_path })` no startup
- [x] AKASHA — adicionar `archive_path` à seção já escrita por `register_akasha()`

#### 1.6 — Scraper compartilhado: KOSMOS e AKASHA

- [x] Criar `ecosystem_scraper.py` — cascata newspaper4k → trafilatura → readability-lxml → inscriptis → BeautifulSoup
- [x] `AKASHA/services/archiver.py` — delegar `_cascade_extract` ao módulo compartilhado
- [x] `AKASHA/services/library.py` — idem para `_fetch_and_extract`
- [x] `KOSMOS/app/core/article_scraper.py` — simplificar para usar `ecosystem_scraper.py`
- [x] `KOSMOS/requirements.txt` — adicionar `inscriptis` e `markdownify`

#### 1.8 — AKASHA: busca local cobre todo o ecossistema

- [x] Indexar `AKASHA/data/archive/` própria no FTS5 (source "AKASHA")
- [x] Ler `mnemosyne.watched_dir` e `mnemosyne.vault_dir` do ecosystem.json em `config.py`
- [x] Indexar `mnemosyne.watched_dir` no FTS5 (source "MNEMOSYNE")
- [x] Indexar `mnemosyne.vault_dir` no FTS5 (source "OBSIDIAN")

#### 1.9 — Mnemosyne: sugestões do ecossistema cobrindo todos os archives

- [x] Adicionar AKASHA archive nas sugestões da SetupDialog

---

### Fase 4 — Polimento e features extras (cross-app)

- [x] Verificar sistema de log em todos os apps e criar onde não existir
- [ ] Integrar AKASHA aos outros apps: seleção de texto → "Pesquisar no AKASHA" (menu de contexto ou botão flutuante abrindo `http://localhost:7071/search?q=<texto>`)
- [ ] Quick capture: widget ou atalho para adicionar nota rápida ao OGMA sem abrir o app
- [ ] Streak AETHER visível no HUB (ler `sessions.json` do vault)
- [ ] Busca cross-módulo: pesquisar em escritos + projetos + artigos

---

### Pendências do Ecossistema

#### Mnemosyne: batching no `index_single_file` (CPU a 90% no idle indexer)

- [ ] `Mnemosyne/core/indexer.py` — `index_single_file()`: substituir `vs.add_documents(chunks)` por loop com `_detect_batch_config()` (lotes de 25 chunks, sleep 0.3 s entre lotes), idêntico ao padrão de `create_vectorstore()`

#### AKASHA como broker unificado de informação

- [ ] Planejar API de "Mapa de Contexto" no AKASHA: dado um termo, retornar resultados cruzados — Mnemosyne (RAG) + KOSMOS (artigos) + Hermes (transcrições) + AETHER (notas)
- [ ] HUB consumir essa API num botão de busca global cross-app

#### Migração Rust/PyO3 para indexação (longo prazo)

- [x] Avaliar substituição do indexador Python do AKASHA por módulo Rust via PyO3 — **Conclusão: não justificada no volume atual (5k–20k docs). Adiar indefinidamente. Gatilhos: volume > 500k docs ou startup time > 30s.**

---

## HUB

### Fase 2 — Dashboard e painel de controle

#### 2.1 — Fundação + Tela de Configuração

- [x] Criar projeto Tauri 2 em `program files/HUB/`
- [x] Copiar design system do AETHER (tokens.css, animations.css, typography.css, components.css, CosmosLayer.tsx, Toast.tsx, ThemeToggle.tsx)
- [x] Splash screen com typewriter + CosmosLayer
- [x] Router interno: `splash → setup | home`
- [x] Tela de configuração (SetupView): lê/edita/valida caminhos do ecosystem.json
- [x] Dashboard (HomeView): 4 cards com CosmosLayer individual
- [x] Rust: `commands/config.rs` — `read_ecosystem_config`, `validate_path`, `save_ecosystem_config`

#### 2.2 — Módulo Escrita (AETHER vault, read-only)

- [x] Rust `commands/writing.rs`: `list_writing_projects`, `list_books`, `read_chapter`
- [x] `WritingView.tsx`, `BookView.tsx`, `ChapterView.tsx`

#### 2.3 — Módulo Leituras (KOSMOS archive, read-only)

- [x] Rust `commands/reading.rs`: `list_articles`, `read_article`, `toggle_read`
- [x] `ReadingView.tsx`, `ArticleView.tsx`

#### 2.4 — Módulo Projetos (OGMA, read-only)

- [x] `rusqlite = { version = "0.31", features = ["bundled"] }` ao Cargo.toml
- [x] Rust `commands/projects.rs`: `list_ogma_projects`, `list_project_pages`
- [x] `lib/editorjs-renderer.tsx`, `ProjectsView.tsx`, `PageView.tsx`

#### 2.5 — Módulo Perguntas (Ollama)

- [x] `lib/ollama.ts`: `listModels()`, `streamChat(model, messages)`
- [x] `QuestionsView.tsx` — seletor de modelo, histórico de sessão, streaming

#### 2.6 — Barra de atalhos para apps externos

- [x] Tela de Setup: campos de executável para cada app
- [x] Rust `commands/launcher.rs`: `launch_app`, `is_app_running`, `get_all_app_statuses`
- [x] `AppBar.tsx` — barra lateral com status ao vivo (polling 5s)

#### HUB — Redesign como dashboard do ecossistema

##### Arquitetura de navegação

- [x] Sidebar vertical persistente: Home · LOGOS · Atividade · Configuração
- [x] Topbar mínima: nome do ecossistema + indicador global + botão silêncio

##### Tela Home — status dos apps

- [x] Card por app (AKASHA · KOSMOS · AETHER · Mnemosyne · Hermes · OGMA): status ao vivo via ping periódico nos `/health` endpoints, porta, botão de iniciar/encerrar
- [ ] Badge de alerta quando app está offline mas deveria estar rodando
- [ ] Mini-resumo por app (última atividade, contagem de arquivos/artigos/etc.)

##### Painel de configuração do ecossistema

- [x] Campo `sync_root` com botão "Aplicar" — preview dos caminhos derivados antes de confirmar
- [ ] Aviso de migração: se sync_root muda e dados existem no caminho antigo, exibir instrução para mover arquivos
- [ ] Editor visual das seções do ecosystem.json com labels descritivos e validação de caminhos

##### System tray / always-accessible

- [x] HUB fica na bandeja ao minimizar (não fecha)
- [x] Fechar janela → oculta na bandeja em vez de encerrar o processo
- [x] Menu de contexto na bandeja: "Abrir HUB" · "Silenciar LOGOS" · "Fechar HUB"
- [x] Infraestrutura de notificações nativas (`tauri-plugin-notification`)
- [ ] Notificações automáticas por evento (app offline, VRAM crítica) — depende de `activity.jsonl` por app

##### Design visual

- [x] Tema padrão: "Atlas Astronômico à Meia-Noite" (`#12161E`)
- [x] Dois modos de janela: Compacto (~640×440) e Expandido (~1280×800)
- [x] Tipografia e paleta consistentes com AETHER/OGMA

---

### LOGOS — Proxy central de LLM

> LOGOS é subprograma do HUB, integrado ao seu backend Rust. Todos os apps falam com o LOGOS (porta 7072) em vez de diretamente com o Ollama (porta 11434).

#### Implementação base

- [x] Decidir arquitetura: LOGOS integrado ao HUB (evita processo extra; HUB já é o maestro)
- [x] Definir protocolo: `POST /logos/chat { app, priority, model, messages, ... }` → 200 ou 429
- [x] Implementar fila de prioridades (`HUB/src-tauri/src/logos.rs`): P1 aguarda indefinidamente, P2 timeout 60s, P3 timeout 30s + 429 imediato se VRAM > 85%
- [x] Hardware Guard: VRAM via Ollama `/api/ps` (sum size_vram) + sysfs Linux para total. Linux/CachyOS: `/sys/class/drm/card{n}/device/mem_info_vram_total`. Windows: pct retorna None.
- [x] Cancelamento gracioso: `POST /logos/silence` → keep_alive: 0 em todos os modelos carregados
- [x] Failsafe em `ecosystem_client.py`: LOGOS online → request roteado; LOGOS offline → fallback direto ao Ollama; LOGOS retorna 429 → RuntimeError propagado
- [x] Tauri IPC commands: `logos_get_status`, `logos_silence`

Arquivos: `HUB/src-tauri/src/logos.rs`, `HUB/src-tauri/src/commands/logos.rs`, `ecosystem_client.py`

#### Otimizações de configuração do Ollama

- [x] Configurar `OLLAMA_KEEP_ALIVE=-1` via injeção automática no proxy (elimina cold start de 3–10s)
- [x] Configurar `OLLAMA_KV_CACHE_TYPE=q8_0` no systemd (reduz VRAM do KV cache ~50%)
- [x] Concorrência dinâmica: `Semaphore::new(2)` — modelos ≤3B adquirem 1 permit (até 2 paralelos), modelos >3B adquirem 2 permits (exclusividade total)
- [x] `OLLAMA_NUM_PARALLEL=2` no systemd
- [x] `LogosPanel` exibe badge "leve" / "pesado" do modelo em execução

#### Seleção e especialização de modelos por app

- [x] KOSMOS (análise em background): usar `gemma2:2b` como default
- [x] Mnemosyne (RAG): usar `qwen2.5:7b` como default
- [x] KOSMOS: `num_ctx=4096` explícito e constante
- [x] Mnemosyne AskWorker: `num_ctx=8192`
- [x] KOSMOS: JSON Schema completo no `_AnalyzeWorker` (constrained decoding via XGrammar)
- [x] KOSMOS: `BackgroundAnalyzer` (QThread + PriorityQueue) — HIGH: artigo aberto, LOW: novos artigos do feed
- [x] KOSMOS: batching de até 5 artigos por call LLM no background

#### Perfis de hardware com detecção automática

| Máquina | GPU detectada | LLM (Mnemosyne) | LLM (KOSMOS) | Embedding |
|---|---|---|---|---|
| PC principal | RX 6600 (AMD sysfs) | qwen2.5:7b | gemma2:2b | bge-m3 |
| Laptop Ideapad 330 | MX150 via nvidia-smi | gemma2:2b | smollm2:1.7b | nomic-embed-text |
| PC de trabalho (Windows) | nenhuma GPU discreta | (CPU only) modelos leves | smollm2:1.7b | all-minilm |

- [x] `detect_hardware_profile()` em `logos.rs` com as 3 etapas de detecção
- [x] `HardwareProfile` enum + struct `ModelProfile { llm_mnemosyne, llm_kosmos, embed }`
- [x] `GET /logos/hardware` no servidor Axum
- [x] `ecosystem_client.py`: `get_active_profile()` + `request_llm()` usa modelo do perfil ativo
- [x] KOSMOS e Mnemosyne: ler perfil do LOGOS no startup como padrão (com override manual possível)
- [x] Botão "usar recomendado" ao lado da configuração de LLM no KOSMOS e Mnemosyne
- [x] HUB LogosPanel: exibir perfil ativo ("PC Principal · RX 6600", "Laptop · MX150 2 GB", etc.)

#### LOGOS: proxy transparente para todas as chamadas ao Ollama (pendente — correção arquitetural)

> Contexto: a implementação atual controla apenas chamadas via `POST /logos/chat`. Embeddings (LangChain/Chroma), streaming (ChatOllama) e chamadas diretas ao Ollama (porta 11434) são invisíveis ao LOGOS.

- [ ] `HUB/src-tauri/src/logos.rs` — rotas de proxy para endpoints nativos do Ollama: `POST /api/chat` e `/api/generate` (com fila P1/P2/P3), `POST /api/embeddings` e `/api/embed` (P3 por padrão), `GET /api/tags`, `/api/ps`, `DELETE /api/delete` (proxy direto sem fila). Identificação do app por header `X-App: <nome>`. `keep_alive: -1` injetado automaticamente. Hardware Guard aplicado a todos os requests.
- [ ] `ecosystem_client.py` — `OLLAMA_BASE_URL` aponta para 7072 (LOGOS) com fallback para 11434 se offline
- [ ] `Mnemosyne/core/indexer.py` e `workers.py` — `OllamaEmbeddings(base_url="http://localhost:7072")`, `ChatOllama(base_url="http://localhost:7072")`; header `X-App: mnemosyne`
- [ ] `KOSMOS/app/core/ai_bridge.py` — URL base para 7072; header `X-App: kosmos`
- [ ] Auditar todos os apps em busca de `localhost:11434` hardcoded e substituir pela URL do LOGOS
- [ ] Testar integração: chat no Mnemosyne (P1) enquanto KOSMOS analisa em background (P3) → KOSMOS deve pausar na fila até o chat terminar

---

### Fase 3 — Android (APK) ⚠️ Suspensa para replanejamento

> HUB passou a ter papel de LOGOS (orquestrador de IA), mudando seu foco. A necessidade de acesso Android continua existindo mas precisa ser repensada — provavelmente um app separado.

- [ ] Configurar ambiente Tauri Android (Android Studio + NDK)
- [ ] Adaptar `tauri.conf.json` para Android (permissões de filesystem)
- [ ] Primeiro build de teste no tablet
- [ ] Resolver incompatibilidades de UI para toque
- [ ] Configurar Syncthing: vault AETHER, kosmos/data/archive/, hub_read_state.json
- [ ] Instalar Tailscale no PC e no tablet; acesso remoto ao ogma.db
- [ ] Fallback gracioso offline

### Pendências — HUB Responsividade

- [ ] Auditar grid de cards de apps — de 3 colunas → 2 → 1 conforme janela estreita (CSS grid `auto-fill`)
- [ ] LogosView e painéis de status — verificar scroll correto em janela reduzida
- [ ] Testar em janela 800×600 mínima

---

## AETHER

### Padrões Obrigatórios

- **Tratamento de erro:** toda função falível retorna `Result<T, AppError>`. Zero `.unwrap()` em produção. Erros no ponto de ocorrência.
- **Commit por item individual** — mensagem referencia o item exato: `feat(fase-0): 0.6 CosmosLayer component`
- **Privacidade:** zero telemetria, zero analytics, zero conexões externas não solicitadas. Gerenciamento no estilo Obsidian (vault como pasta raiz controlada pelo usuário).
- **Manter `dev_files/dev_bible.txt` atualizado** ao concluir qualquer item que introduza novos arquivos, módulos, commands ou padrões.

### Stack

- Backend: Rust (Tauri)
- Frontend: TypeScript + React + Vite
- Armazenamento: arquivos locais (JSON + Markdown/texto plano)
- Build: Tauri CLI (Windows 10 + CachyOS/Linux)

### Identidade Visual

**Nome:** AETHER | **Subtítulo:** FORJA DE MUNDOS

Diferencial visual: animação `pageFloat`, efeito typewriter, cursor `_` piscante, CosmosLayer com labels mitológicos nas constelações, nebulosas com pulso lento (8s).

### Design Bible v2.0 — Audit (2026-04-11)

- [x] tokens.css: modo noturno migrado para paleta "Atlas Astronômico à Meia-Noite"
- [x] tokens.css: `--sidebar-w` corrigido para 224px
- [x] typography.css: hierarquia tipográfica alinhada ao bible
- [x] components.css: `.btn` corrigido para 11px / 5px 14px
- [x] Splash.tsx: background hardcoded → `var(--paper)`

### Fase 0 — Design System

- [x] 0.1 Variáveis CSS globais (tokens do ecossistema)
- [x] 0.2 Tipografia (IM Fell English · Special Elite · Courier Prime)
- [x] 0.3 Animações base (`paperFall`, `fadeIn`, `slideIn`, `blink`, `toastIn`)
- [x] 0.4 Animações exclusivas (`pageFloat`, `typewriterReveal`, `etherPulse`)
- [x] 0.5 Textura de papel (SVG `feTurbulence`)
- [x] 0.6 Componente `<CosmosLayer>` (SVG procedural determinístico com labels mitológicos)
- [x] 0.7 Linha vermelha de margem
- [x] 0.8 Sistema de sombra flat (sem blur)
- [x] 0.9 Scrollbar vintage
- [x] 0.10 Cursor dourado e cursor de editor (`_` piscante)
- [x] 0.11 Seleção de texto âmbar
- [x] 0.12 Sistema de temas (dia / noite) com persistência em localStorage
- [x] 0.13 Sistema de toasts / notificações (success/error/warning/info)
- [x] 0.14 Splash screen (CosmosLayer + typewriterReveal)
- [x] 0.15 Componentes base de UI (botões, inputs, cards, modais, badges)

### Fase 1 — Fundação

- [x] 1.1 Scaffold Tauri + React + TypeScript
- [x] 1.2 Estrutura de dados em disco (modelo Obsidian — vault, AppData, project.json, book.json, capítulos .md)
- [x] 1.3 Comandos Tauri: gerenciamento de projetos (list, create, open, delete)
- [x] 1.4 Comandos Tauri: livros e capítulos (create, list, read, save, delete, reorder)
- [x] 1.5 Tipos TypeScript espelhando os tipos Rust
- [x] 1.6 Tela inicial — lista de projetos
- [x] 1.7 Layout principal do projeto (binder lateral + editor central + drag & drop)
- [x] 1.8 Editor de texto WYSIWYG com TipTap (auto-save 500ms, IM Fell English itálico, cursor `_`)

### Fase 1.5 — Itens pendentes identificados em uso

- [x] 1.9 Tipos de projeto: livro único vs série (`project_type: "single" | "series"`)
- [x] 1.10 Modal de criação de projeto com metadados (wizard, gênero, público, worldbuilding)
- [x] 1.11 Dashboard do projeto (CosmosLayer, stats, widgets)
- [x] 1.12 Sistema de logs em arquivo (`{vault}/.aether/logs/aether-YYYY-MM-DD.log`, 7 dias de retenção)

### Fase 2 — Experiência de escrita

- [x] 2.1 Temas: claro, escuro, sépia
- [x] 2.2 Tipografia customizável
- [x] 2.3 Modo foco / distraction-free
- [x] 2.4 Modo typewriter (cursor sempre centralizado verticalmente)
- [x] 2.5 Tela cheia (F11)
- [x] 2.6 Contagem de palavras e caracteres em tempo real
- [x] 2.7 Status por capítulo (Rascunho / Revisão / Final)
- [x] 2.8 Sinopse por capítulo
- [x] 2.9 Localizar e substituir no capítulo atual

### Fase 3 — Organização avançada

- [x] 3.1 Vista corkboard (cartões de capítulo com título + sinopse)
- [x] 3.2 Vista outline (lista com status, sinopse e contagem de palavras)
- [x] 3.3 Lixeira — capítulos deletados recuperáveis
- [x] 3.4 Scratchpad por capítulo (bloco de notas lateral)
- [x] 3.5 Modo split: editor + scratchpad/notas lado a lado

### Fase 4 — Personagens & Worldbuilding

- [x] 4.1 Fichas de personagem com campos customizáveis
- [x] 4.2 Relacionamentos entre personagens (mapa/grafo simples)
- [x] 4.3 Notas de worldbuilding por categoria (locais, facções, etc.)
- [x] 4.4 Linha do tempo de eventos
- [x] 4.5 Anexar imagens a personagens e locais
- [x] 4.6 Tags — cruzar personagens/locais com capítulos

### Fase 5 — Metas & Histórico

- [x] 5.1 Meta de palavras por capítulo e por livro
- [x] 5.2 Meta de sessão de escrita com timer
- [x] 5.3 Streak diário de escrita
- [x] 5.4 Painel de estatísticas (palavras totais, ritmo, sessões)
- [x] 5.5 Snapshots de capítulo (histórico de versões manual + automático)
- [x] 5.6 Comentários/anotações inline no texto

### Fase 6 — Exportação

- [ ] 6.1 Export por capítulo individual
- [ ] 6.2 Export por livro (capítulos concatenados)
- [ ] 6.3 Export do projeto completo
- [ ] 6.4 Formatos: Markdown, texto plano, DOCX, PDF
- [ ] 6.5 Formato EPUB
- [ ] 6.6 Configurações de export (incluir/excluir sinopses, metadados, notas)

### Fase 7 — Polimento & Extras

- [x] 7.0 Botão de excluir visível para projetos, livros e capítulos (hover revela ×, confirmação 2 passos)
- [ ] 7.1 Atalhos de teclado customizáveis
- [ ] 7.2 Gerador de nomes
- [ ] 7.3 Projetos recentes na tela inicial com preview
- [ ] 7.4 Onboarding (tela de boas-vindas para primeiro uso)
- [ ] 7.5 Configurações globais (tema padrão, pasta de dados, fonte padrão)
- [ ] 7.6 Build de distribuição — Windows installer + pacote Linux (AppImage/deb)

### Backlog (futuro)

- [ ] Sync opcional com cloud
- [ ] Colaboração em tempo real
- [ ] Plugin/extensão system
- [ ] Integração com ferramentas de revisão gramatical
- [ ] Versão mobile (leitura + notas)

### Pendências — Bugs e Responsividade

#### Bug: vault_path não atualiza após mudança no HUB

- [ ] Investigar por que AETHER continua salvando no caminho antigo após `sync_root` ser atualizado no HUB — verificar `lib.rs` e `ecosystem.rs`
- [ ] Adicionar opção de configurar `vault_path` dentro do próprio AETHER (sem depender exclusivamente do HUB)

#### Responsividade

- [ ] Auditar sidebar de projetos/capítulos — em janelas ~800px verificar se esconde o editor; adicionar collapsível com toggle abaixo de 900px
- [ ] Barra de ferramentas do editor — overflow em janela estreita: ocultar labels, manter ícones abaixo de 900px
- [ ] Testar em janela 900×600 mínima

---

## AKASHA

> Buscador pessoal local. Agrega resultados da web e do ecossistema, com downloads e integração com qBittorrent.
> Stack: FastAPI + HTMX + Jinja2 + SQLite (aiosqlite) + uv · Porta 7071.

### Padrões Obrigatórios

- Tipagem completa: Pydantic `BaseModel` em todas as rotas; `-> tipo` em todas as funções
- Erros explícitos: `HTTPException` com status code em todos os caminhos de erro
- `uv` obrigatório: `pyproject.toml`, nunca `requirements.txt`
- Commits por item; atualizar este TODO antes de implementar qualquer feature não listada
- SQLite versionado: tabela `settings` com campo `schema_version`; migrations numeradas
- HTMX: todo estado mutável via `hx-swap`; toda ação tem feedback visual

### Fase 1 — Fundação

- [x] `pyproject.toml` — dependências uv
- [x] `main.py` — FastAPI app + lifespan
- [x] `config.py` — lê `ecosystem.json` via `ecosystem_client`
- [x] `database.py` — schema SQLite + migrations (tabelas `searches`, `downloads`, `settings`)
- [x] `static/style.css` — paleta completa (sépia + noturno astronômico)
- [x] `templates/base.html` — layout base com topbar e nav
- [x] `templates/search.html` — área de resultados com skeleton loader
- [x] `iniciar.sh` — detecta venv, `uv sync`, executa app

### Fase 2 — Busca Web

- [x] `services/web_search.py` — DuckDuckGo com cache SQLite (TTL 1h) e deduplicação por URL
- [x] `routers/search.py` — `GET /search?q=&sources=web`
- [x] Cards de resultado com snippet, badge de fonte, data
- [x] Widget "Buscas recentes" (últimas 10 queries)
- [x] Filtro de fonte: radio/toggle Web / Local / Todos
- [x] Botão "Carregar mais" (HTMX `hx-swap="beforeend"`)

### Fase 3 — Busca Local

- [x] `services/local_search.py` — indexar KOSMOS archive + AETHER vault em FTS5
- [x] FTS5 virtual table `local_index` em SQLite
- [x] Reindexação automática no startup se mtime mudou
- [x] Query ChromaDB do Mnemosyne (import opcional, graceful fallback)
- [x] Badge de fonte por card: `WEB` · `KOSMOS` · `AETHER` · `MNEMOSYNE`

### Fase 4 — Downloads

- [x] `services/downloader.py` — download async via `httpx` com streaming e progresso
- [x] `routers/downloads.py` — POST/GET/SSE para downloads com background tasks
- [x] Templates de downloads com barras de progresso SSE e histórico paginado

### Fase 5 — Arquivação Web

- [x] `services/archiver.py` — cascata de extratores (trafilatura + inscriptis + BS4 + Jina fallback); salva em `{archive_path}/Web/YYYY-MM-DD_{slug}.md`
- [x] `POST /archive` — chama archiver, retorna toast de confirmação
- [x] Botão "arquivar" em cada card WEB

### Fase 6 — Torrents (busca + qBittorrent)

> Pré-requisito: qBittorrent rodando com Web UI ativo (porta 8080); Prowlarr (9696) ou Jackett (9117) configurados.

#### 6.1 — Configuração

- [ ] Adicionar campos na tabela `settings` (migration): qbt_host, qbt_port, prowlarr_host/port/apikey, jackett_host/port/apikey
- [ ] Adicionar estes campos à página `/settings`

#### 6.2 — Cliente qBittorrent

- [ ] `services/qbt_client.py` — `_get_session()`, `list_torrents`, `add_magnet`, `add_torrent_file`, `pause_torrent`, `resume_torrent`, `delete_torrent`. Raises `QbtOfflineError` se inacessível.

#### 6.3 — Busca de Torrents (Prowlarr + Jackett)

- [ ] `services/torrent_search.py` — `search_prowlarr()`, `search_jackett()` (XML Torznab), `search()` com fallback entre indexadores
- [ ] Dataclass `TorrentResult`: title, seeders, leechers, size_bytes, size_fmt, magnet_url, torrent_url, indexer, pub_date

#### 6.4 — Router

- [ ] `routers/torrents.py` — `GET /torrents`, `GET /torrents/search`, `GET /torrents/active` (polling 5s), `POST /torrents/add`, `/pause`, `/resume`, `/delete`

#### 6.5 — Templates

- [ ] `templates/torrents.html` — formulário de busca + ativos + polling HTMX
- [ ] `templates/_torrents_active.html` — tabela com progresso, velocidade, ETA, botões
- [ ] `templates/_torrent_results.html` — cards de resultado com botão "↓ baixar"

#### 6.6 — CSS e nav

- [ ] `.torrent-card`, `.torrent-table`, `.seed-count`, `.leech-count` em `static/style.css`

### Fase 7 — Biblioteca de URLs

- [x] Migration v5: tabelas `library_urls` + `library_diffs` + FTS5 `library_fts`
- [x] `services/library.py` — `add_url()`, `scrape_and_store()`, `check_overdue()`, `compute_diff()`
- [x] `routers/library.py` — GET/POST/PATCH/DELETE + refresh
- [x] `templates/library.html` — cards com snippet, idioma, word count, tags, diffs, filtros
- [x] Background task no lifespan: re-scrape URLs vencidas a cada hora
- [x] Busca local `/search?sources=local` inclui `library_fts`
- [x] Botão `+` em cards WEB → enfileira URL na biblioteca via `POST /library/add-quick`

### Fase 7.5 — Lista negra de domínios

- [x] Migration v6: tabela `blocked_domains`
- [x] `services/web_search.py` — filtrar resultados excluindo domínios bloqueados
- [x] Botão `−` em cards WEB: `POST /domains/block`, toast de confirmação
- [x] `routers/domains.py` — `POST /domains/block`, `DELETE /domains/block/{domain}`
- [x] `templates/domains.html` — lista de domínios bloqueados com botão desbloquear e formulário

### Fase 8 — Histórico unificado

- [x] Migration v10: tabela `activity_log` (`type` ∈ `search|archive|download`)
- [x] `routers/history.py` — `GET /history?type=all|search|archive|download&page=1`
- [x] `templates/history.html` — timeline agrupada por data; ícone por tipo; filtros HTMX

### Fase 9 — Polimento e Integração Final

- [ ] `iniciar.sh` — versão final robusta: verificar uv instalado, `uv sync --frozen`
- [ ] Escrever `akasha.exe_path` no `ecosystem.json` no startup
- [ ] `templates/settings.html` — página `/settings`: caminhos do ecossistema, pasta de download, host/porta qBittorrent
- [ ] Nav: adicionar abas "Biblioteca", "Histórico" e "Sites" na topbar
- [ ] `README.md` — atualizar seção "Estado" para "Implementado — Fase 9"

### Fase 10 — Buscador de Sites Pessoais

#### Banco de dados

- [x] Migration v7: tabela `crawl_sites` e `crawl_pages`
- [x] Migration v7: FTS5 `crawl_fts`
- [x] `database.py` — helpers: `get_all_crawl_sites()`, `get_crawl_site(id)`

#### Services

- [x] `services/crawler.py` — `extract_links()`, `discover_subdomains()`, `crawl_site()` (BFS async), `search_sites()`, `crawl_pending_sites()`
- [x] Integrar `crawl_pending_sites()` no loop horário do lifespan

#### Routers

- [x] `routers/crawler.py` — `POST /sites/discover`, `POST /sites`, `GET /sites`, `DELETE /sites/{id}`, `POST /sites/{id}/crawl`

#### Integração com busca

- [x] `routers/search.py` — source `sites` com badge dourado
- [x] `templates/search.html` — checkboxes `□ Web  □ Ecossistema  □ Sites pessoais`

#### Interface de gerenciamento

- [x] `templates/sites.html` — lista de sites com status, subdomínios; formulário "Adicionar site" com detecção de subdomínios

### Fase 10.5 — Navegação inline de páginas crawleadas

- [x] `database.py` — helpers `get_crawl_page_by_url()` e `get_crawl_pages_by_site()`
- [x] `routers/crawler.py` — `GET /library/reader?url=` (reader mode) e `GET /library/{site_id}/pages`
- [x] `templates/page_reader.html` — layout reader mode com tipografia IM Fell English
- [x] `templates/_site_pages.html` — fragment HTMX: lista paginada de páginas com botão "Ler"
- [x] `templates/_library_list.html` — botão "📄 N páginas" em cada site card (expande via HTMX)
- [x] `templates/_macros.html` — botão "Ler" nos cards `source="SITES"`

### Fase 11 — Performance e Robustez

#### Alta prioridade

- [x] SQLite WAL mode + pragmas em `init_db()`: `journal_mode=WAL`, `synchronous=NORMAL`, `cache_size=-8000`, `mmap_size=67108864`
- [x] Índices ausentes (migration v8): `idx_crawl_pages_site`, `idx_library_diffs_url`
- [x] Busca paralela via `asyncio.gather()` com filtro condicional por source

#### Média prioridade

- [x] `services/library.py` — `_LIST_COLS` sem `content_md`; `scrape_and_store` usa `SELECT *`
- [x] `services/crawler.py` — `crawl_site` com 2 conexões (leitura inicial + sessão BFS)
- [x] FTS skip em conteúdo idêntico (`_upsert_page`: consulta `content_hash` antes do FTS)
- [x] `asyncio.get_event_loop()` → `asyncio.get_running_loop()` (3× em `routers/crawler.py`, 1× em `main.py`)

#### Baixa prioridade

- [x] Limpeza periódica do search_cache (DELETE FROM search_cache com cutoff 24h)
- [ ] Monitor de biblioteca com paralelismo controlado — `asyncio.gather` com `asyncio.Semaphore(3)` para re-scrapes simultâneos. ⚠️ BLOQUEADO: depende de `services/library.py` e `routers/library.py` (verificar se Fase 7 está totalmente implementada)

### Fase 12 — Extensão Firefox (Zen Browser)

> Requer Fase 3 do Hermes (mini API HTTP) — já implementada.

#### Estrutura de arquivos

- [ ] `extension/manifest.json` — Manifest V3; permissões: `activeTab`, `http://localhost:7071/*`
- [ ] `extension/icons/` — ícone 16/32/48/128px (active e greyscale)
- [ ] `extension/popup/popup.html` + `popup.css` + `popup.js` — URL atual, botões "⬇ Baixar vídeo" e "📝 Transcrever"

#### Background script

- [ ] `extension/background.js` — detectar URL de vídeo suportado pelo yt-dlp; habilitar/desabilitar ícone da action
- [ ] `extension/background.js` — ao receber mensagem do popup, `POST http://localhost:7071/api/hermes/download`

#### Backend AKASHA

- [ ] `routers/hermes_bridge.py` — `POST /api/hermes/download` (body: url, mode, format?): verifica Hermes online via `/health`, auto-lança se offline (polling 30s), delega via `httpx.AsyncClient`
- [ ] Registrar `hermes_bridge` router em `main.py`

#### Instalação

- [ ] `extension/README.md` — instruções `about:debugging`

### Fase 12.5 — Aba "Ver Mais Tarde"

- [x] Migration v9: tabela `watch_later` + FTS5 `watch_later_fts`
- [x] `database.py` — helpers: `add_watch_later`, `get_all_watch_later`, `delete_watch_later`, `search_watch_later`
- [x] `services/local_search.py` — `search_watch_later()` com `source="DEPOIS"` (não indexado no `local_fts`)
- [x] `routers/watch_later.py` — GET/POST/DELETE
- [x] `templates/watch_later.html` — lista com campo notes inline editável
- [x] `templates/_macros.html` — botão `☆ ver depois` nos cards WEB
- [x] `templates/base.html` — aba "ver depois" no nav
- [x] `templates/search.html` — seção "Salvo para depois"
- [x] `routers/search.py` — incluir `search_watch_later(q)` no `asyncio.gather`

### Fase 13 — API de Pesquisa Profunda (integração com Mnemosyne)

- [x] `GET /search/json?q={query}&sources=web,sites&max={n}` — retorna `list[SearchResult]` como JSON puro
- [x] `POST /fetch` (body: `{url, max_words}`) — fetch + scraping completo de uma URL; resposta efêmera; timeout 30s

### Fase 14 — Integração KOSMOS nos cards de resultado

- [x] `templates/_macros.html` — botão "K" nos cards WEB: `hx-post="/kosmos/add-source"`
- [x] KOSMOS expõe `POST /add-source` via `http.server` em thread daemon (porta 8965)
- [x] `routers/kosmos_bridge.py` — lê porta do ecosystem.json, encaminha para KOSMOS; 503 se offline

### Fase 15 — Qualidade de Busca e Crawl (pesquisa 2026-04-24)

#### Alta prioridade

- [x] **[A] BM25 com pesos por campo** — `bm25(crawl_fts, 10, 1)` na consulta FTS5 (título 10× vs. corpo)
- [x] **[B] Normalização de URL antes de inserir no crawl** — remover parâmetros de tracking (`utm_*`, `fbclid`, `ref`)
- [x] **[C] FTS5 optimize periódico pós-crawl** — `INSERT INTO crawl_fts(crawl_fts) VALUES('optimize')` após crawls com > 200 páginas novas
- [x] **[D] Cache de robots.txt por domínio (TTL 24h)**

#### Média prioridade

- [x] **[E] Rate limiting por domínio com fila de prioridade** — `asyncio.Queue` + semáforo por host (1 req/s)
- [x] **[F] SimHash para detecção de near-duplicatas** — `pip install simhash`; rejeitar distância Hamming < 3
- [x] **[G] Índice de prefixo FTS5** — `prefix="2,3"` na criação de `crawl_fts`
- [x] **[H] `favor_recall=True` no trafilatura** antes do fallback Jina

#### Baixa prioridade

- [ ] **[I] Campo separado para headings no FTS5** — extrair h1–h3, indexar em coluna dedicada com peso ~50×
- [ ] **[J] Meilisearch como backend alternativo** — avaliar quando corpus ultrapassar ~100k páginas

### Fase 16 — Correção de Bugs (auditoria 2026-04-24)

#### Alta prioridade

- [x] **[BUG-1] `/domains` — bloquear/desbloquear não atualiza lista na UI** — retornar fragment HTML atualizado nos endpoints POST/DELETE
- [x] **[BUG-2] `search.html` — link "Adicionar sites" apontava para `/sites` (404)** — corrigido para `/library`
- [x] **[BUG-3] `crawl_site` — status travado em `'crawling'` quando ocorre exceção** — envolver BFS em `try/finally`, garantir `UPDATE status='idle'` no `finally`

#### Média prioridade

- [x] **[BUG-4] `main.py` `index()` — contexto incompleto para `search.html`** — adicionar chaves faltantes com valores padrão
- [x] **[BUG-5] `search.html` — aviso "nenhum site cadastrado" dentro de `{% if error %}`** — mover bloco para fora
- [x] **[BUG-6] `/open-file` nunca reporta erro** — usar `asyncio.create_subprocess_exec`, tentar `gio open` como fallback, retornar HTTP 500 se ambos falharem

### Planos Futuros

> Funcionalidades adiadas por complexidade ou baixa prioridade imediata.

### Pendências adicionais (derivadas do planejamento de ecossistema)

#### Bug: porta errada no iniciar.bat/sh

- [x] `iniciar.bat` / `iniciar.sh` — corrigir porta: uvicorn sobe em 7071 mas script abria `http://localhost:7070`

#### Lista de favoritos (domínios prioritários)

- [x] `database.py` — tabela `favorite_domains` (migration 12) + CRUD
- [x] `routers/favorites.py` — CRUD completo (add, delete, to-blacklist, to-library)
- [x] `templates/favorites.html` + `_favorites_list.html`
- [x] Resultados de domínios favoritos sobem para P2 na ordenação

#### Busca: priorização e segunda coluna

- [x] 3 níveis: P1 (ecossistema local), P2 (domínios favoritos), P3 (web geral)
- [x] Segunda coluna/sidebar: ecossistema local separado dos web

#### Extração: Medium e Substack

- [x] Medium: Freedium proxy (`freedium.cfd`) em `get_fetch_url()` no `ecosystem_scraper.py`
- [x] Substack: seletores `.available-content` e `.post-content` adicionados ao `_ext_bs4`

#### Busca e download de artigos científicos

- [x] `services/paper_search.py` — busca paralela em Semantic Scholar + arXiv (`aioarxiv`)
- [x] `services/paper_download.py` — download PDF open access; extração via `pymupdf4llm`; fallback `pypdf`
- [x] `services/archiver.py` — `archive_pdf()` salvando em `data/archive/Papers/`
- [x] `routers/papers.py` — `POST /papers/download`
- [x] Templates e filtros de busca para resultados acadêmicos

#### Abrir arquivos locais / leitor do ecossistema

- [x] `/open-file` com `xdg-open` + fallback `gio open` implementado (BUG-6 corrigido)
- [ ] Leitor próprio do ecossistema — reader mode integrado inspirado no KOSMOS; prioridade baixa

#### Busca local e fusão de resultados

- [ ] **Bug: `_search_chroma()` cria novo `PersistentClient` a cada query** — cachear como singleton em `_chroma_clients: dict[str, Any]` (module-level)
- [ ] **Substituir `rank_combined()` por Reciprocal Rank Fusion (RRF)** — considera posição relativa de cada resultado em vez de contagem de keywords
- [ ] **FTS5 com tokenizer `unicode61 remove_diacritics=2`** — "musica" encontra "música" — recriar `local_fts` com tokenizer correto (requer reindexação)
- [ ] **Deduplicação de conteúdo crawlado por hash SHA-256** — coluna `content_hash TEXT` em `crawl_pages`; SELECT antes de inserir
- [ ] **ETag/Last-Modified no crawler** — armazenar `etag` e `last_modified` por URL; passar headers condicionais no re-crawl; ignorar 304 Not Modified
- [ ] **Throttle adaptativo baseado em tempo de resposta do servidor** — média móvel por domínio (janela 5 requests); ajustar delay dinamicamente; backoff exponencial em 429
- [ ] **Trafilatura como primeiro estágio de extração** — em `ecosystem_scraper.py`, tentar Trafilatura antes de readability/bs4 (F1=0.945 vs F1=0.665 do BS4)

#### Responsividade

- [x] Cards de resultado — ações em janela estreita: `flex-wrap: wrap` nas ações; botões ícone-only abaixo de 680px
- [x] Tabela de downloads — ocultar coluna "Concluído" abaixo de 700px; substituir por cards abaixo de 520px
- [x] Formulário de download — `flex-direction: column` abaixo de 580px
- [x] Página de biblioteca — breakpoints auditados e corrigidos
- [x] Topbar — `column-gap/row-gap` separados; `nav margin-top: 4px`
- [x] Páginas watch-later, history, favorites — auditadas e corrigidas
- [x] Testar em 800×600, 1024×600, 1280×720 — servidor iniciado, todas as páginas retornam HTTP 200

---

## KOSMOS

> Leitor de feeds RSS/YouTube/Reddit com IA local. Stack: PyQt6 · Python · SQLite · Ollama.

### Padrões obrigatórios

- Tipagem completa em todos os parâmetros e retornos
- Erros nunca engolidos silenciosamente — propagar, retornar valor verificável ou dar feedback ao usuário
- `log.error()` para falhas reais, `log.warning()` só para condições esperadas/recuperáveis
- Atualizar TODO a cada feature implementada; commit a cada funcionalidade concluída

### Design Bible v2.0 — Audit (2026-04-11)

- [x] Modo noturno migrado para paleta "Atlas Astronômico à Meia-Noite" em `night.qss`
- [x] `reader_night.css` atualizado para nova paleta
- [x] `splash_screen.py` — cores hardcoded noturnas corrigidas

### Fase Extra — Features de Enriquecimento

- [x] Filtros de palavra-chave (blocklist)
- [x] Feeds de busca (Google News RSS por termo)
- [x] Tags manuais nos artigos — chips no leitor, CRUD em `feed_manager.py`
- [x] Posição de scroll salva (`scroll_pos` via `window.scrollY`, restaurado no `loadFinished`)
- [x] Top fontes e tópicos no dashboard — painéis com barras proporcionais
- [x] Deduplicação de artigos similares — `duplicate_of`, `rapidfuzz` (85%, 48h, entre feeds)
- [x] Highlights e anotações no leitor — `highlights` table, JS injection, chips abaixo das tags
- [x] Tradução inline no leitor — `deep-translator` (Google Translate), menu de idiomas, "Ver original"
- [x] Scraping multilíngue — fallback BS4 para idiomas sem tokenizador
- [x] Fallback de scraping — traduz título para inglês → busca Google News RSS → tenta scraping
- [x] Filtro de idioma na view unificada — coluna `language`, detecção via `langdetect`
- [x] Título do artigo exibido no leitor e traduzido junto com o corpo
- [x] Label de idioma original → traduzido na barra inferior do leitor
- [x] Auto-salvar artigo ao criar primeiro destaque
- [x] Tratamento de erros: `log.error` para falhas reais, feedback visível, tipagem completa

### Fase A — Leitor e Arquivo

- [x] Navegação anterior / próximo entre artigos
- [x] Botão "Buscar artigo completo" (com fallback BS4 multilíngue + fallback por título)
- [x] Purgação automática de artigos antigos (`purge_old_articles`)
- [x] `saved_view.py` — view de artigos salvos/favoritados
- [x] `archive_manager.py` — exportar artigo para Markdown em `data/archive/`
- [x] `archive_view.py` — browser do arquivo
- [x] Conversão HTML → Markdown via `html2text`

### Fase B — Plataformas Adicionais

**Reddit:**
- [ ] `reddit_fetcher.py` — wrapper praw 7.x
- [ ] `add_reddit_dialog.py` — adicionar subreddit (requer credenciais)
- [ ] Configurações → seção Reddit
- [ ] Mapeamento de posts para schema de artigos

**YouTube:**
- [ ] Detecção automática de URL YouTube em `add_feed_dialog.py`
- [ ] Extração de `channel_id` de URLs `@handle`
- [ ] Thumbnail de vídeos nos article cards

**Outras plataformas (RSS puro):**
- [ ] Detecção automática: Tumblr, Substack, Mastodon pela URL

### Fase C — Busca Global

- [x] FTS5 virtual table com triggers de sincronização
- [x] `search.py` — query FTS5, retorna artigos ranqueados por relevância
- [x] Barra de busca global `Ctrl+K` (overlay flutuante)
- [x] Resultados com feed de origem e snippet destacado
- [x] Navegação por teclado (↑↓ Enter Esc)

### Fase D — Exportação PDF e Estatísticas

**Exportação PDF:**
- [ ] `export_pdf.py` — WeasyPrint + template sépia
- [ ] `export_dialog.py` — seletor de destino
- [ ] Botão "Exportar PDF" na toolbar do leitor

**Estatísticas:**
- [x] `read_sessions` — registrar início/fim de leitura por artigo
- [x] `stats.py` — agregação por dia, feed, plataforma
- [x] `stats_view.py` — gráficos matplotlib, filtro de período
- [x] Botão "Stats" na sidebar

### Fase E — Polimento Final

- [ ] Animações: fade-in 150ms nos cards, slide 200ms no leitor
- [ ] Cursor piscante dourado (`#b8860b`) em campos de texto
- [ ] Cantos dobrados decorativos (SVG 20×20px)
- [ ] Ícone do app
- [ ] `iniciar.sh` e `iniciar.bat` com setup automático do venv
- [ ] Revisar todos os caminhos com `pathlib.Path`
- [ ] Testes em Windows 10

### Fase F — IA Local (Ollama)

**Infraestrutura:**
- [x] `app/core/ai_bridge.py` — cliente Ollama: verificar disponibilidade, gerar texto, gerar embeddings
- [x] Migration: colunas `ai_summary`, `ai_tags`, `embedding BLOB`, `ai_relevance`
- [x] Configurações → seção IA: endpoint, modelo de geração, modelo de embeddings, botão "Testar conexão"

**Resumo:**
- [x] Botão "Resumir" na toolbar do leitor — streaming token a token via sinal PyQt
- [x] Cache: resumo salvo em `ai_summary`; não regenera se já existir

**Tags automáticas:**
- [x] Sugerir tags via `format: "json"` ao abrir artigo sem tags
- [x] Chips de sugestão em cor distinta

**Relevância via embeddings:**
- [x] Gerar embedding ao salvar/ler artigo em background
- [x] Perfil de interesses: média dos embeddings dos artigos lidos/salvos
- [x] Score de relevância = cosine similarity

**Busca semântica:**
- [x] Toggle FTS5 (palavras-chave) ↔ busca vetorial (semântica) na search overlay
- [x] Embed a query em tempo real → retorna top-N artigos por cosine similarity

**Análise de viés político:**
- [ ] Migration: colunas `ai_political_economic` e `ai_political_authority`
- [ ] Botão "Analisar viés" no leitor — bússola política 2D
- [ ] Agregação por feed na `sources_view`

**Detecção de clickbait:**
- [x] Migration: coluna `ai_clickbait REAL`
- [x] Score gerado pelo `_AnalyzeWorker`; badge `⚠` opcional nos cards quando > 0.6
- [x] Indicador `⚠ clickbait N%` na meta bar do leitor
- [ ] Filtro por score de clickbait na unified feed view

**Citação ABNT + análise 5Ws:**
- [x] Painel colapsível "Citação & 5Ws" ao salvar artigo
- [x] Citação ABNT gerada dos metadados
- [x] 5Ws via `_FiveWsWorker`; cache em `ai_5ws TEXT`

**`_AnalyzeWorker` unificado:**
- [x] Substituir `_TagSuggestWorker` + `_FiveWsWorker` por `_AnalyzeWorker` (JSON único: `{tags, sentiment, clickbait, five_ws}`)
- [x] `_SummarizeWorker` mantido separado com streaming

**Sentimento e Tom:**
- [x] Migration: coluna `ai_sentiment REAL`
- [x] Score gerado pelo `_AnalyzeWorker`; borda colorida nos cards (configurável)
- [x] Indicador `● tom positivo/negativo/neutro` na meta bar
- [ ] Filtro por tom na unified feed view
- [x] Gráfico de tendência de sentimento no `stats_view`

**NER — Extração de Entidades:**
- [x] Migration: coluna `ai_entities TEXT` (JSON `{people,orgs,places}`)
- [x] Gerado pelo `_AnalyzeWorker`
- [x] Três mini-charts no `stats_view`: top pessoas, organizações e lugares

**Clustering por tópico:**
- [x] K-means numpy sobre embeddings `nomic-embed-text`
- [x] Rótulo por extração de palavras-chave dos títulos do cluster
- [x] Cards de tópicos no `stats_view`
- [x] Seção "Tópicos em Destaque" no Dashboard — atualizada em tempo real via `analysis_done` + debounce 8s

### Fase G — Unificar "Salvo" e "Arquivo" em Arquivar

- [x] G.1 — `reader_view.py`: botão "★ Arquivar" + ao marcar, chamar `archive_manager.export_article()` junto; ao desmarcar, deletar `.md`
- [x] G.2 — Renomear aba e view "Salvos" → "Arquivados"
- [x] G.3 — `main_window.py`: `_migrate_saved_to_archive()` no startup para artigos já salvos sem `.md`
- [x] G.4 — `archive_view.py`: remover botão "Exportar" órfão; `archive_manager.py`: `get_archive_path()` e `delete_archive()`

### Fase H — Indicador de Status do Ollama

- [ ] H.1 — `settings_dialog.py` → seção IA: label de status persistente que atualiza ao abrir ("● Ollama conectado — qwen2.5:7b" ou "○ Ollama offline"); verificação assíncrona via `ai_bridge.is_available()`
- [ ] H.2 — `reader_view.py` → painel de resumo: exibir "⟳ Aguardando Ollama…" entre clique e primeiro token
- [ ] H.3 — `reader_view.py` → meta bar: exibir "⟳ analisando…" enquanto `_AnalyzeWorker` roda; substituir por resultado ou "IA indisponível" ao terminar
- [ ] H.4 — Indicador global discreto (ponto colorido na sidebar ou `QStatusBar`): polling leve a cada 60s via `QTimer`

### Fase I — Idioma de exibição e detecção de idioma

- [ ] I.1 — `models.py`: verificar/adicionar coluna `language`; `feed_manager.py`: garantir detecção via `langdetect`; `article_card.py`: badge com idioma original (`EN`, `PT`, etc.)
- [ ] I.2 — `config.py`: campo `display_language: str = ""`; `settings_view.py`: QComboBox com idiomas + "Original (sem tradução)"
- [ ] I.3 — `article_card.py`: tradução assíncrona dos títulos se `display_language` configurado; cache em memória
- [ ] I.4 — Verificar se botão "Traduzir" no leitor usa `display_language` como destino automático

### IDEIAS

- [ ] Detecção de evento: identificar que artigos de fontes diferentes cobrem o mesmo evento — clustering temporal + semântico combinados

### Fase Z — Futuro

- [ ] Twitter/X quando solução gratuita e estável disponível
- [ ] Playwright para scraping de sites com JavaScript pesado
- [ ] Importar/exportar feeds via OPML
- [ ] Notificações nativas (plyer) para feeds prioritários
- [ ] Sureddit multis e Mastodon com autenticação
- [ ] Suporte a podcasts (RSS de áudio com player interno)
- [ ] Integração com OGMA: salvar artigo diretamente
- [ ] Regras de auto-tag por palavra-chave
- [ ] Modo leitura offline

### Pendências adicionais — KOSMOS

#### Tags geradas por IA nos cards do feed

- [x] Tags aprovadas exibidas como chips nos cards do feed via `FeedManager.get_tags_for_articles()`
- [x] Estatística de tags: `get_top_ai_tags_read()` + gráfico horizontal em `StatsView`

#### Pré-análise em background

- [x] `BackgroundAnalyzer` (QThread + PriorityQueue): HIGH=artigo aberto (P0), LOW=novos artigos do feed (P10)
- [x] Cache check: artigos com `ai_sentiment IS NOT NULL` são pulados
- [x] Batching de até 5 artigos por call LLM; schema dinâmico por lote; fallback individual
- [x] Incluir análise dos 5Ws na pré-análise (campo `five_ws` no JSON Schema do batch)

#### Status de análise visível ao abrir artigo

- [x] Indicador de status independente do arquivamento: "analisando…", "concluída", "erro", "não analisado"

#### Estatísticas expandidas

- [ ] Ampliar gráficos com detalhamento dos 5Ws — mais granularidade, mais gráficos por período e por fonte

#### Verificação de sincronização

- [ ] Confirmar que `archive_path` e `data_path` apontam para `sync_root/kosmos/`

#### Marcação de problemas em artigos

- [ ] Criar mecanismo para marcar problemas (scraping incompleto, paywall, conteúdo cortado, campo livre). Efeito: diminuir ranking de relevância da fonte. Registrar no log para análise futura.

#### Qualidade de IA e integração com LOGOS

- [ ] **Bug: `generate_stream()` bypassa o LOGOS** — substituir por chamada a `_request_llm(..., stream=True)` com `priority=1` para leituras interativas
- [ ] **Bug: `embed()` bypassa o LOGOS** — endpoint hardcoded na porta 11434; usar endpoint do LOGOS (7072) como padrão via `ecosystem_client.get_logos_url()` ou `LOGOS_URL`
- [ ] **Workers de background: definir prioridade de OS com `os.nice(15)`** — no início do método `run()` de `BackgroundUpdater` e `BackgroundAnalyzer` (Linux); `SetPriorityClass(BELOW_NORMAL)` no Windows
- [ ] **Deduplicação de artigos RSS por fingerprint de conteúdo** — coluna `content_hash TEXT` + index em `articles`; fingerprint SHA-256 de (title_norm + date_ISO + url_norm); SimHash para near-duplicatas
- [ ] **Caching ETag/Last-Modified nos feeds RSS** — colunas `etag TEXT` e `last_modified TEXT` em `feeds`; `feedparser.parse(url, etag=..., modified=...)` com 304 Not Modified como early return

#### Responsividade

- [ ] Auditar layout principal (splitter horizontal) — `setMinimumWidth` adequado em cada painel
- [ ] ArticleCard — chips de tags em janela estreita: `fontMetrics().elidedText()` para evitar overflow
- [ ] StatsView — gráficos matplotlib em janela pequena: `tight_layout()` + tamanho de fonte dinâmico
- [ ] Testar em janela 800×600 mínima

---

## Mnemosyne

> RAG pessoal local. Indexa biblioteca de documentos e vault Obsidian para perguntas via LLM.
> Stack: PySide6 · Python · ChromaDB · LangChain · Ollama.

### Padrões obrigatórios

- **Tratamento de erros com tipagem é prioridade absoluta.** Nunca `except Exception` sem re-tipar. Retornar `T | None` ou usar exceções específicas.
- Manter este TODO atualizado. Acrescentar ANTES de implementar qualquer coisa.
- Commit após cada item individual. Nunca passar de fase sem aprovação explícita.

### Fase 1 — Qualidade e robustez

- [x] `core/errors.py` — hierarquia de exceções tipadas
- [x] `core/config.py` + `config.json` — sistema de configuração (modelos, pasta)
- [x] `core/ollama_client.py` — detecção dinâmica de modelos disponíveis
- [x] `core/loaders.py` — suporte a `.md` + erros tipados
- [x] `core/indexer.py` — recebe `AppConfig`, erros tipados, `index_single_file()`
- [x] `core/rag.py` — recebe `AppConfig`, retorna `AskResult` tipado
- [x] `core/summarizer.py` — recebe `AppConfig`, erros tipados
- [x] `gui/workers.py` — `OllamaCheckWorker`, `IndexFileWorker`
- [x] `gui/main_window.py` — seleção de modelo, pasta via diálogo, verificação Ollama

### Fase 2 — Gerenciamento de Contexto Pessoal (PCM)

- [x] `core/memory.py` — `SessionMemory` + `CollectionIndex`
- [x] `core/watcher.py` — `FolderWatcher` via `QFileSystemWatcher`
- [x] `core/tracker.py` — rastreamento de hashes SHA-256
- [x] `core/rag.py` — hybrid retrieval (semântico + BM25 via rank-bm25)
- [x] `core/memory.py` — arquitetura em camadas: `history.jsonl` (append-only) + `memory.json` (`collection` + `session`); `build_memory_context()`; `compact_session_memory()`
- [x] `core/rag.py` + `gui/workers.py` — histórico multi-turno (últimos 5 turnos, cap 6000 chars); botão "Nova Conversa"
- [x] `core/loaders.py` — suporte a `.epub` com `ebooklib` + BeautifulSoup; 1 Document por capítulo
- [x] `core/ollama_client.py` — validar existência do modelo antes de lançar worker
- [x] `gui/main_window.py` — badge de pendentes + indicador de progresso por ficheiro

### Fase 3 — Features core

- [x] `core/indexer.py` — `update_vectorstore()` incremental completo usando tracker
- [x] `core/indexer.py` — remover chunks de arquivos deletados/renomeados ao atualizar vectorstore
- [x] `core/indexer.py` — tratar arquivos modificados: remover chunks antigos + re-adicionar novos
- [x] `gui/main_window.py` — botão "Atualizar índice" (incremental)
- [x] `core/summarizer.py` — Map-Reduce: modo "stuff" para corpora <12k chars; Map-Reduce para corpora grandes
- [x] `core/rag.py` — compressão contextual, Multi-Query Retrieval, HyDE (Hypothetical Document Embeddings)
- [x] `gui/main_window.py` — compactação automática ao fechar: `closeEvent` → diálogo "Guardar esta conversa?"
- [x] `core/tracker.py` — metadados de relevância por documento (`score_avg`, `last_retrieved_at`)
- [x] `core/rag.py` — time-decay de relevância com `relevance_decay_days` configurável

### Fase 4 — Inspirado no NotebookLM

#### 4.0 Pré-requisito arquitectural

- [x] Migrar de `OllamaLLM` para `ChatOllama` com roles separados (persona fixa no `SystemMessage`, contexto RAG + pergunta no `HumanMessage`). Dicionário `PERSONAS` com 6 modos.

#### 4.1 Citação aprimorada

- [x] `core/rag.py` — retornar trecho exato do chunk junto com nome do arquivo
- [x] `gui/main_window.py` — fontes com trecho visível e indicador de relevância

#### 4.2 Seleção de fontes por consulta

- [x] Listar arquivos indexados com checkboxes; filtro por lista de arquivos via ChromaDB `where` metadata

#### 4.3 Notebook Guide automático

- [x] `core/guide.py` — resumo geral da coleção + 5 perguntas sugeridas + "Pérolas Escondidas" (3 fatos surpreendentes)
- [x] `gui/main_window.py` — exibir Guide na aba Resumir ou painel lateral

#### 4.4 FAQ Generator

- [x] `core/faq.py` — gerar lista de perguntas frequentes
- [x] `gui/workers.py` — FaqWorker com streaming
- [x] `gui/main_window.py` — botão "Gerar FAQ"

#### 4.5 Flashcards, Quiz e Estudo

- [ ] `core/flashcards.py` — extrair termos-chave, datas e conceitos como flashcards
- [ ] `core/quiz.py` — perguntas de múltipla escolha com gabarito
- [ ] `core/study_plan.py` — Roteiro de Estudos: Básico / Intermediário / Avançado
- [ ] `gui/main_window.py` — nova aba "Estudar" com modos Flashcard, Quiz e Roteiro

#### 4.6 Modos de consulta configuráveis

- [x] 6 personas via `PERSONAS` dict + `SystemMessage`: `curador`, `socrático`, `resumido`, `comparação`, `podcaster`, `crítico`
- [x] `gui/main_window.py` — `QComboBox` "Modo:" na aba Chat

#### 4.8 Audio Overview

- [ ] `core/podcast.py` — Script de Podcast: diálogo escrito entre dois "hosts" em Markdown
- [ ] `gui/main_window.py` — botão "Gerar Script de Podcast"
- [ ] Pesquisar TTS offline (Kokoro, Piper TTS) para converter script em áudio
- [ ] `core/audio.py` — gerar áudio via TTS local
- [ ] Player embutido no `gui/main_window.py`

#### 4.9 Studio Panel — Geração de Documentos

**UI do Studio Panel:**
- [x] `gui/main_window.py` — pill "Studio" na aba Análise; `QComboBox` com 9 tipos; botão "Gerar"; `QTextEdit` read-only com streaming; botão "Exportar .md"

**Implementados:**
- [x] `core/briefing.py` — `iter_briefing()`: 4 seções (Temas Principais, Achados, Insights, Divergências)
- [x] `core/report.py` — `iter_report()`: 6 seções em Markdown (Sumário Executivo, Temas, Análise, Convergências, Lacunas, Referências)
- [x] `core/study_guide.py` — `iter_study_guide()`: Conceitos-Chave, Termos Técnicos, Questões, Tópicos para Aprofundar
- [x] `core/toc.py` — `iter_toc()`: hierarquia `## Tema > - Subtema` com máximo 8 temas
- [x] `core/timeline.py` — `iter_timeline()`: eventos datados ordenados cronologicamente; temperatura 0.0
- [x] `core/blogpost.py` — `iter_blogpost()`: temperatura 0.5; título criativo + 3-5 parágrafos
- [x] `core/mindmap.py` — `iter_mindmap()`: bloco `mermaid mindmap`; máximo 6 ramos
- [x] `core/tables.py` — `iter_tables(schema=...)`: tabela Markdown; botão "Exportar CSV"
- [x] `core/slides.py` — `iter_slides()`: slides `---`-separados, compatíveis com Marp/reveal.js

**Pendente:**
- [ ] Export PDF via `weasyprint` (pesquisar viabilidade — baixa prioridade)
- [ ] `requirements.txt` — avaliar `graphviz` para SVG embutido no Qt (baixa prioridade)

### Fase 5 — UI e design

- [x] `gui/styles.qss` — fontes do ecossistema (IM Fell English, Special Elite, Courier Prime)
- [x] `gui/styles.qss` — Design Bible v2.0: paleta "Papel ao Sol da Manhã", border-radius 2px
- [x] `gui/main_window.py` — remover hardcodes de cor legados; objectNames para ollamaBanner, folderLabel, etc.

### Fase 6 — Coleções Duais: Segunda Memória & Arquivo

#### Arquitetura de Coleções

- [x] `core/collections.py` — `CollectionType` (VAULT | LIBRARY), `CollectionConfig`; `sync_ecosystem_collections()`, `available_ecosystem_paths()`; migração do formato legado

#### Vault Obsidian (Segunda Memória)

- [x] `core/loaders.py` — loader Obsidian: `python-frontmatter`; metadata por nota (title, tags, aliases, wikilinks); ignorar `.obsidian/`, `templates/`, `attachments/`, `.trash/`
- [x] `core/loaders.py` — chunking por cabeçalho `##` para notas `.md`
- [x] `core/rag.py` — seguimento de wiki-links; prompt do Vault com tom introspectivo
- [x] `core/memory.py` — seção `collection` do Vault descreve o estilo de pensar da usuária

#### Biblioteca

- [x] `core/rag.py` — prompt da Biblioteca com tom acadêmico; perspectivas em confronto se autores divergirem
- [x] `core/loaders.py` — metadata `author` e `title` em todos os loaders (PDF, EPUB, DOCX)

#### Integração automática do ecossistema

- [x] `core/collections.py` — `ECOSYSTEM_SOURCES` define KOSMOS, AKASHA e Hermes (AETHER excluído); `sync_ecosystem_collections()` lê `ecosystem.json` automaticamente
- [x] `gui/main_window.py` — `SetupDialog` com toggles por fonte detectada
- [x] `core/config.py` — `ecosystem_enabled: dict[str, bool]` persiste estado ligado/desligado

#### Interface de Gestão de Coleções

- [x] `gui/main_window.py` — selector de coleção na sidebar: `QComboBox` com ícone de tipo; trocar de coleção carrega vectorstore + memória + reseta `chat_history`
- [x] Diálogo "Nova Coleção": campos nome, caminho, tipo (Vault/Biblioteca); auto-detectar `.obsidian/`
- [x] Aba Coleções no tab Gerenciar: lista com nome, tipo, caminho, estado; botões editar/remover/indexar

#### Redesign de Interface

- [x] Reformulação completa da UI — sidebar + painel principal; sem abas; modo escuro (#12161E)
- [x] Ajuste de legibilidade — corpo 13px, inputs 14–15px, sidebarBrand 24px
- [x] Toggle dia/noite — `styles_light.qss` + `dark_mode` persistido em config

#### Barra de progresso e alinhamento visual

- [x] Barra de progresso durante indexação — `QProgressBar` com valor real (x/y arquivos), nome do arquivo com elide, botão "Interromper"
- [x] Redesign completo para paridade com o ecossistema — `styles.qss` usa tokens do `ecosystem_qt.py` adaptados para PySide6

#### Sessões de Chat Nomeadas

- [x] `core/memory.py` — `Session` com id único, título editável, timestamp; `history.jsonl` → `sessions/{id}.jsonl`
- [x] `core/memory.py` — `list_sessions()`, `load_session(id)`, `new_session()`, `delete_session(id)`
- [x] `gui/main_window.py` — painel de sessões na sidebar; auto-título via primeira pergunta (60 chars); editável por duplo-clique

### Fase 7 — Modo de Pesquisa Profunda (integração com AKASHA)

> Requer AKASHA rodando na porta 7071 com `/search/json` e `/fetch` (Fase 13 do AKASHA).

- [x] `core/akasha_client.py` — cliente httpx: `search()`, `fetch()`, `is_available()`. Tipos: `AkashaResult`, `FetchResult`. Erros: `AkashaOfflineError`, `AkashaFetchError`
- [x] `core/session_indexer.py` — indexação temporária em memória via `chromadb.EphemeralClient()`; máx 10 páginas por sessão
- [x] `gui/workers.py` — `DeepResearchWorker`: pipeline 6 passos (busca → fetch paralelo → indexação → RAG combinado → resposta → clear)
- [x] `gui/main_window.py` — toggle "🌐 Pesquisa Profunda"; visível apenas se AKASHA disponível; fontes web com badge `[WEB]`

### Correções de bugs

- [x] `gui/workers.py` — `IndexWorker`: limpar `persist_dir` antes de indexar; `tracker.mark_indexed(file_path)` após cada arquivo
- [x] `gui/workers.py` — `IndexWorker`: reestruturado para processar arquivo por arquivo

### Fase 8 — Otimizações de RAG (pesquisa 2026-04-23)

- [x] 8.1 Métrica cosine no ChromaDB — `collection_metadata={"hnsw:space": "cosine"}` em todos os pontos de criação/abertura do Chroma
- [x] 8.2 Tamanho de chunk — `chunk_size` 800 → 1800, `chunk_overlap` 100 → 250
- [x] 8.3 FlashRank reranking — `ContextualCompressionRetriever` com `FlashrankRerank`; k=30 candidatos → top 6-8; modelo `"ms-marco-MultiBERT-L-12"`; campos em `AppConfig`
- [ ] 8.4 RAGAS — `eval/ragas_eval.py` standalone para avaliar faithfulness, context precision e answer relevancy
- [ ] 8.5 LightRAG — grafos de conhecimento (pesquisar se modelos 8B são suficientes; hardware limitante)

### Fase 9 — Robustez do indexador (2026-04-24)

- [x] 9.1 `core/indexer.py` — `_clear_orphan_wal()`: apaga `chroma.sqlite3-wal` e `chroma.sqlite3-shm` antes de abrir ChromaDB
- [x] 9.2 `core/indexer.py` — `IndexCheckpoint`: SQLite em `{mnemosyne_dir}/index_checkpoint.db`; status `'ok'`/`'error'` por arquivo; deletado ao concluir com sucesso
- [x] 9.2 `gui/workers.py` — `IndexWorker.run()`: deleta `.mnemosyne`; cria checkpoint; checkpoint permanece se interrompido
- [x] 9.2 `gui/workers.py` — `ResumeIndexWorker`: lê checkpoint, processa apenas pendentes
- [x] 9.2 `gui/main_window.py` — botão "↩ Retomar indexação" visível apenas se persist_dir + checkpoint existem
- [x] 9.2 `gui/main_window.py` — `_cancel_worker()` corrigido para interromper `_index_worker` e `_resume_worker`

### Fase 10 — Indexação incremental automática do ecossistema (idle indexer) ✓

- [x] 10.1 Reutilizar `FolderWatcher` por coleção de ecossistema
- [x] 10.1 `core/idle_indexer.py` — monitora coleções com `source == "ecosystem"` via `IdleIndexer.setup()`
- [x] 10.2 `_is_busy()` lambda em `main_window.py` — verifica `_index_worker`, `_resume_worker`, `_update_worker`, `_file_worker`
- [x] 10.3 `IdleIndexer` com `QTimer` (30s) + `queue.Queue` thread-safe; `_IndexJobWorker(QThread)` em `IdlePriority`
- [x] 10.4 `self._bg_label` (`QLabel#bgIndexLabel`) — "⟳ Indexando N arquivo(s) do ecossistema…" quando fila não vazia
- [x] 10.5 `background_index_enabled: bool = True` em `AppConfig`; idle indexer para no `closeEvent`

### Pendências — Responsividade

- [ ] Auditar splitter principal (lista de documentos | viewer) — `setMinimumWidth` adequado em cada painel
- [ ] Lista de documentos: truncar nome de arquivo longo com tooltip
- [ ] Testar em janela 800×600 mínima

---

## Hermes

> Downloader e transcritor de vídeos. Stack: PyQt6 · Python · yt-dlp · Whisper.

### Fase 1 — Implementação inicial (PyQt6)

- [x] Estrutura do projeto (Hermes/, data/, iniciar.sh, TODO.md)
- [x] App PyQt6 com duas abas: Baixar + Transcrever
- [x] Paleta do ecossistema (Design Bible v2.0)
- [x] Carregamento de fontes IM Fell English + Special Elite via QFontDatabase
- [x] Aba Baixar: URL → Inspecionar → seleção de formato → Download
- [x] Aba Baixar: suporte a playlist (seleção individual + baixar tudo)
- [x] Aba Transcrever: URL → modelo Whisper + idioma + limite CPU → Markdown
- [x] Workers em QThread (download e transcrição em background)
- [x] Log compartilhado entre abas com tags de cor
- [x] Output dir configurável, persistido em .prefs.json
- [x] iniciar.sh apontando para o .venv compartilhado

### Fase 2 — Melhorias

- [x] Transcrição de arquivos locais — aceita mp4, mkv, avi, mov, webm, mp3, wav, m4a, ogg, flac
- [x] Histórico de transcrições (lista das últimas .md geradas)
- [x] Preview do markdown gerado dentro do app
- [x] Integração com Mnemosyne (enviar transcrição para indexação RAG)
- [x] Modo batch: transcrever playlist inteira de uma vez
- [x] Detecção de ffmpeg e aviso se não encontrado

### Fase 3 — Mini API HTTP (integração com extensão AKASHA)

- [x] `api_server.py` — servidor HTTP em `threading.Thread` via `http.server`; porta padrão 7072 (configurável em `.prefs.json`)
- [x] `POST /download` — recebe JSON `{url, format?}`; retorna `{"status": "queued", "url": url}`
- [x] `POST /transcribe` — recebe JSON `{url}`; enfileira transcrição
- [x] `GET /health` — retorna `{"status": "ok", "active": n}`
- [x] `hermes.py` — escreve `hermes.api_port` no `ecosystem.json` no startup (try/except silencioso)
- [x] Feedback visual: downloads/transcrições via API aparecem no log com badge `[API]`

### Fase 4 — Expansão de sites suportados

- [x] Auditar `hermes.py`: sem validação hardcoded que bloqueie sites
- [x] Expandir `is_playlist_url`: padrões para Twitch, SoundCloud, Vimeo, Dailymotion, Bandcamp, Bilibili e Niconico
- [x] Placeholder do campo URL atualizado com lista de plataformas
- [x] Tooltips com lista de sites e link para supportedsites.md do yt-dlp
- [ ] Testar formatos disponíveis nas plataformas adicionadas (validação manual)

### Bugs conhecidos

(nenhum por enquanto)

### Pendências — Responsividade

- [ ] Auditar layout principal: lista de vídeos | área de transcrição — em janelas estreitas a transcrição precisa de scroll vertical
- [ ] Testar em janela 800×600 mínima

---

## OGMA

> Gestor de conhecimento pessoal, notas e produtividade. Stack: Electron · React · TypeScript · SQLite local.

### Padrões Obrigatórios

- Todo código que chama `db()` no renderer **deve** usar `fromIpc<T>` de `src/renderer/types/errors.ts`
- Nunca `fromIpc<any>` — sempre tipar o genérico com o tipo concreto esperado
- `async/await` em vez de `.then()` encadeado em `ResultAsync` dentro de `Promise.all`
- `pushToast` via `useAppStore()` é o canal de feedback de erros
- Todo código deve passar em `tsc --noEmit` sem erros
- Manter TODO atualizado; commit após cada funcionalidade ou mudança

### Bugs conhecidos / Prioridade imediata

- [x] Dashboard reseta ao trocar de aba — corrigido: sempre montado com `display:none`
- [x] Cor de acento não aplicada ao CSS — corrigido: `useEffect` em App.tsx
- [x] Atividades do Planner não aparecem no Calendário Global — corrigido: UNION `planned_tasks` nas queries
- [x] Algoritmo de agendamento: prioridade + skip weekends + edição manual de `planned_hours`
- [x] Lembretes movidos para dentro do Planner (RemindersSection)
- [x] Planejamento de revisão com repetição espaçada: 1→3→7→14→30 dias
- [x] Timer/Pomodoro integrado no Planner: botão ▶ por tarefa, auto-log, registo manual
- [x] Bug: ao criar atividade pelo Planner, não aparecia opção de conectar a uma página
- [x] Dashboard não recarregava ao voltar ao separador — corrigido: prop `isActive` nos widgets
- [x] Schema do DB não era recriado no modo embedded replica após apagar ficheiro local
- [x] Botão de sincronização manual nas Configurações
- [x] Tamanho de fonte nas Configurações não alterava nada — fix: CSS usa `rem` com base em `html { font-size }`
- [x] Barra lateral recolhível (modo só-ícones, toggle ◀▶, persistência em localStorage)
- [x] Botão "reagendar" no planner global
- [x] Verificar se "reagendar" reage a tarefas pendentes atrasadas (urgência máxima)
- [x] Separar limite de horas por dia no planner (não mais fixo para todos os dias)
- [x] Planner com visualização alternável — tabs AGENDA e TAREFAS ABERTAS; Pomodoro sempre visível
- [x] Campo de prioridade no formulário de criação de tarefa do GlobalPlanner
- [x] Bug: filtro por data via clique no mini-calendário do GlobalPlanner — corrigido: `activeFocus` removido das deps
- [x] Bug: work_blocks do Planner não apareciam na aba Agenda do GlobalCalendarView — corrigido: UNION com `work_blocks`

### Fase Extra — Prioridade Alta

- [x] Leituras → Recurso: selecionar livro existente ao registar leitura
- [x] Sessões de leitura: registar sessões individuais com data e páginas lidas
- [x] Abas de leitura: Geral, Notas, Citações, Vínculos
- [x] Recursos: vista em galeria + detalhe com metadados + conexões a páginas
- [x] `reading_links`: vincular leitura ↔ página do OGMA
- [x] Progresso de leitura por páginas ou porcentagem
- [x] Meta de leitura anual — IPC `reading:goals:*` + `ReadingGoalBanner` com barra de progresso
- [ ] Histórico de versões de página — tabela `page_versions` existe no schema; falta IPC + UI no PageView
- [x] Backlinks: mostrar no PageView as páginas que referenciam a atual
- [x] Pomodoro / timer independente com histórico por página — `StudyTimerTab` com relógio SVG animado, registo manual de sessões

### Fase 4 — Kanban

- [x] Drag & drop entre colunas (muda `prop_value` do Status)
- [x] Filtros e ordenação na view

### Fase 5 — Table / List

- [x] Edição inline de propriedades nas views (TableView)
- [x] Filtros, ordenação e busca nas views

### Fase 6 — Módulo Académico Completo

- [x] `colorUtils.ts` — cores HSL automáticas por disciplina
- [x] Gerador de código `PREFIX###` automático (initials + numerais)
- [x] Pré-requisitos entre páginas com detecção de ciclo (IPC + UI no PageView)
- [x] Campo `institution` no nível do projeto (tipo `academic`)
- [x] Modal de nova página expandido: cor de capa, página pai, propriedades, tags, multi-select
- [x] IconPicker: navegação entre categorias, scroll, sugestões por palavra-chave
- [x] Tipo de projeto **"Hobbies"** — subcategorias, propriedades padrão, views (Lista, Tabela)
- [x] **Ideias Futuras** — `'idea'` adicionado ao `ProjectType`; widget no Dashboard
- [x] Planner global: algoritmo com prioridade + prazo + limite de horas/dia; reagendamento global
- [x] Organização progressiva para projetos acadêmicos Autodidata: propriedade `ciclo` (Ciclo 1–5)

### Fase 8 — Calendário, Lembretes e Analytics

- [x] Lembretes via Notification API do Electron (scheduler.ts com polling de 60s)
- [x] Atividades acadêmicas: tipos Prova, Trabalho, Seminário, Defesa, Prazo, Reunião, Outro
- [x] PageEventsPanel — criar atividades/lembretes dentro de cada página
- [x] UpcomingEventsPanel — painel de próximas atividades no dashboard do projeto
- [x] GlobalCalendarView — eventos no grid + aba Agenda + aba Lembretes

### Fase 9 — Dashboard Global

- [x] Fase da lua (cálculo astronômico) — `getMoonPhase()` com referência J2000 + ciclo 29.53 dias
- [x] Drag-and-drop dos widgets + persistência da ordem
- [x] Roda do Ano (WheelOfYearWidget) — SVG com 8 Sabás, setores sazonais, próximo Sabá destacado
- [x] Três tamanhos por widget (SM/MD/LG) com layouts adaptativos + persistência
- [x] Localização do utilizador (cidade, lat/lon, hemisfério, timezone) via geocoding Open-Meteo
- [x] Widget de Previsão do Tempo (WeatherWidget) — Open-Meteo forecast, WMO codes em PT
- [x] Roda do Ano com hemisfério real e datas astronômicas (Meeus) por localização configurada

#### Gestão de widgets

- [x] Remover widget do dashboard (botão × no hover)
- [x] Adicionar widget oculto de volta (card "+ Adicionar widget")
- [x] Persistência de widgets ocultos

### Fase 9b — Planejador Acadêmico (Planner)

- [x] Migrations: tabelas `planned_tasks` e `work_blocks`
- [x] IPC handlers: CRUD de `planned_tasks` + algoritmo de scheduling (EDF, capacidade diária)
- [x] Aba "Planner" no ProjectView
- [x] Widget "Plano do Dia" no Dashboard
- [x] Campo "Capacidade diária (horas)" em Settings (padrão 4h)
- [x] GlobalPlannerView com mini calendário e estética bullet journal

### Fase 10 — Sincronização entre dispositivos — Turso / libsql (migrado para Proton Drive)

- [x] `data/settings.json` — preferências do utilizador separadas do banco
- [x] Migrar `localStorage` → `data/settings.json` via IPC `appSettings:*`
- [x] Migração completa de Turso → SQLite local (Fase 0.6 do ecossistema)
- [x] Todos os passos de setup, dependências, reescrita de `database.ts`, handlers IPC, testes e validação
- [ ] Testar sync entre dois dispositivos — requer hardware; `client.sync()` confirmado funcional

### Ícone da aplicação

- [x] Ícone temporário (`assets/ogma.ico`) — fundo castanho escuro, símbolo ✦ dourado
- [x] Ícone aplicado ao `BrowserWindow` e configurado no `electron-builder`
- [x] Atalhos Windows atualizados com `IconLocation`

### Fase 11 — Polimento

- [x] Ícone do app (temporário)
- [x] Decoração cósmica completa, animações

### Fase 12 — Analytics

> Todos os analytics vêm desativados por padrão e são ativados nas Configurações.

- [x] Pico de Produtividade: "Você é uma criatura da Manhã/Noite"
- [x] Taxa de Absorção Literária: recursos concluídos vs. adicionados no mês
- [ ] Páginas por "Área do Conhecimento": gráfico de pizza/barras por categoria
- [x] Produtividade por Fase Lunar: fase lunar no momento de conclusão de tarefas
- [ ] Progresso da Estação: percentual de "Preparação para o Equinócio/Solstício"
- [x] Horas de Voo (Deep Work): total de horas nos work_blocks do Planner
- [x] Velocidade de Leitura: média de páginas/dia nos últimos 7 dias
- [x] Radar de Polímata (Equilíbrio de Áreas): porcentagem de tarefas concluídas ou tempo por categoria

#### Por projeto / académico

- [ ] Horas por projecto — gráfico de barras com `work_blocks` por projeto
- [ ] Taxa de conclusão do Planner — tarefas concluídas vs. atrasadas por mês
- [ ] Distribuição de tipos de tarefa — pizza de `task_type`
- [ ] Progresso por prazo — linha do tempo de tarefas vs. deadline

#### Leitura

- [ ] Ritmo de leitura — páginas/dia ao longo do tempo (`reading_sessions`)
- [ ] Livros concluídos por mês — gráfico de barras
- [ ] Progresso da meta anual — gauge + projeção de conclusão

#### Conhecimento

- [ ] Páginas mais conectadas — top backlinks (hubs de conhecimento)
- [ ] Tags mais usadas — evolução temporal
- [x] Atividade por dia da semana — padrão de produtividade

### Fase 13 — Widgets

#### IDEIAS

- [ ] Terminal de Cibersegurança (Status de Lab) — estética de terminal com progresso em certificações/máquinas de lab
- [ ] Widget de "Rituais de Estação" — cruzar fase da lua + Roda do Ano para sugerir atividade de autocuidado
- [ ] Provocador de Pesquisa (Pergunta em Aberto) — varrer páginas em busca de `?` ou `[?]` e exibir uma aleatoriamente
- [ ] Mapa do Próximo Passo (Manual Arts) — último projeto de Hobbies/Artes Manuais com última atualização

#### Alta prioridade (dados já disponíveis)

- [x] Agenda da Semana — faixa de 7 dias com chips de `calendar_events` por dia
- [x] Lembretes Pendentes — lista de reminders com `is_dismissed = 0` e `trigger_at` próximo
- [x] Próximas Provas / Defesas — filtro de `calendar_events` por tipos acadêmicos com countdown
- [x] Progresso dos Projetos — barra de progresso por projeto ativo
- [x] Citação Aleatória — `QuoteWidget` com citação de `reading_quotes`, renovável a clique
- [ ] Widget POMODORO no Dashboard — Pomodoro standalone com relógio visual / relógio de areia

#### Média prioridade

- [ ] Mapa de Calor de Atividade — grid estilo GitHub de horas estudadas (requer `time_sessions`)
- [ ] Sumário do Dia — briefing textual com eventos, prazos, lembretes

#### Futuros

- [ ] Meta de Leitura Anual — gauge circular no Dashboard
- [ ] Tempo de Foco Hoje — sessões Pomodoro do dia (depende de `time_sessions`)
- [ ] Grafo de Conexões — mini grafo com páginas interligadas via backlinks

### Design System — Efeitos Visuais (2026-04-10)

- [x] Vinheta sépia — `body::before` radial-gradient escurecendo bordas
- [x] Foxing — classe `.foxing` com manchas de envelhecimento nos cantos de cards
- [x] Marginalia — classe `.marginalia-item` com símbolo ✦ no hover à esquerda
- [x] Selo de cera — componente WaxSeal (ao concluir item)
- [x] Luz de vela — componente CandleGlow com brilho radial pulsante
- [x] Loader alquímico — componente AlchemyLoader substituindo spinners

### Melhorias Futuras

- [x] Dashboard e página inicial de projeto: `ProjectLocalDashboard` com coluna de stats + grid de widgets customizável; toolbar com dropdown de vistas

### Fase 50 — Futuro

- [ ] Exportar página como PDF ou Markdown
- [ ] Pomodoro Timer completo com estatísticas (consolidar com aba Tempo + Widget do Dashboard)
- [ ] Templates customizados de projeto
- [ ] IA: integração com Ollama e APIs externas