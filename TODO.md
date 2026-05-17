# TODO — Ecossistema

> Consolidado em 2026-04-27. Fonte única de verdade — arquivos individuais removidos.

---

## Padrões Obrigatórios


**HUB é o primeiro app a rodar.** Centraliza todas as configurações comuns do ecossistema e gerencia seu funcionamento.
Os demais apps leem `ecosystem.json` no startup — se não houver valor configurado, usam
defaults locais. Nunca bloquear o startup por falta de configuração do ecosystem.

**Compatibilidade de plataforma: todos os apps devem rodar no Windows 10 e no CachyOS (Linux).**

Isso implica:
- Sem paths hardcoded com separadores Unix — usar APIs de path da linguagem (`Path`, `os.path`, `std::path`)
- Sem dependências exclusivas de uma plataforma (ex.: bibliotecas só-Linux ou só-Windows)
- Testar caminhos com espaços (o diretório de trabalho da própria Jenifer tem espaço no nome)
- Apps Python: empacotar com `uv` ou fornecer instruções explícitas para ambos os SOs
- Apps Tauri/Rust: garantir que `cargo tauri build` funcione nos dois targets

---

**Tratamento de erros com tipagem é prioridade absoluta em todo o ecossistema.**

Isso se aplica a todos os apps existentes e a qualquer código novo:

- **Rust (AETHER/Hub):** toda função falível retorna `Result<T, AppError>`.
  Zero `.unwrap()` ou `.expect()` em produção.
- **TypeScript (OGMA/Hub):** `strict: true` obrigatório. Erros tipados com
  discriminated unions — `{ ok: true; data: T } | { ok: false; error: AppError }`.
  Nunca `any`, nunca `catch (e: any)` sem re-tipar.
- **Python (KOSMOS/Mnemosyne/utilitários):** exceções capturadas com tipos
  explícitos (`except ValueError`, não `except Exception` genérico).
  Funções críticas anotadas com `-> T | None` ou via `Result` pattern.

Nenhuma fase ou feature está completa se o caminho de erro não for tratado
e tipado com a mesma atenção que o caminho feliz.

---


---

## Ecossistema — Integração e Infraestrutura

### FASE 0 — Fundação do ecossistema
> Pré-requisito para todas as fases seguintes.

> **Decisão de caminho (revisada):** O arquivo de contrato foi movido para
> `~/.local/share/ecosystem/ecosystem.json` (Linux) / `%APPDATA%\ecosystem\ecosystem.json` (Windows).
> Motivo: apps Tauri (AETHER) e Electron (OGMA) não conhecem o caminho de `program files/`
> em produção. O caminho XDG/AppData é descoberto automaticamente por todas as linguagens.

- [x] Criar `ecosystem.json` em `~/.local/share/ecosystem/` com caminhos reais do KOSMOS
- [x] Criar `ecosystem_client.py` — utilitário Python compartilhado (KOSMOS, Mnemosyne, Hermes)
      Funções: `ecosystem_path()`, `read_ecosystem()`, `write_section()` com escrita atômica
- [x] Criar `OGMA/src/main/ecosystem.ts` — utilitário TypeScript para OGMA
      Funções: `ecosystemPath()`, `readEcosystem()`, `writeSection()` com escrita atômica
- [x] Criar `AETHER/src-tauri/src/ecosystem.rs` — módulo Rust para AETHER
      Funções: `ecosystem_path()`, `write_section()` usando `dirs::data_dir()`
- [x] Adicionar `dirs = "5"` em `AETHER/src-tauri/Cargo.toml`
- [x] Wiring em `AETHER/src-tauri/src/lib.rs`: escreve `vault_path` no startup (falha silenciosa)
- [x] Documentar o contrato: quem escreve cada campo, quando, formato

#### 0.5 — sync_root: sincronização via Proton Drive (ou qualquer pasta sync)

Objetivo: um campo `sync_root` top-level no ecosystem.json aponta para a pasta do Proton Drive.
O HUB deriva e aplica todos os caminhos de uma vez. Cada app respeita o caminho configurado.

```
ProtonDrive/ecosystem/
├── aether/        ← vault_path
├── kosmos/        ← archive_path
├── mnemosyne/
│   ├── docs/      ← watched_dir
│   └── chroma_db/ ← persist_dir (ChromaDB sincronizado)
├── hermes/        ← output_dir
└── akasha/        ← archive_path
```

- [x] **`ecosystem_client.py`** — adicionar `derive_paths(sync_root)` e campo `sync_root` no schema
- [x] **`Mnemosyne/core/config.py`** — novo campo `chroma_dir`; `persist_dir` usa-o se definido
- [x] **`Mnemosyne/gui/main_window.py`** — campo "Pasta do ChromaDB" na SetupDialog
- [x] **`AKASHA/config.py`** — `ARCHIVE_PATH` lê `akasha.archive_path` do ecosystem.json se disponível
- [x] **`HUB/src-tauri/src/commands/config.rs`** — comando `apply_sync_root(sync_root)`
      Cria subpastas + escreve seções no ecosystem.json via `derive_paths`
- [x] **`HUB/src/views/SetupView.tsx`** — seção "Sincronização": campo sync_root + botão "Aplicar"
      Aviso: "Mova seus arquivos existentes manualmente antes de aplicar"

- [x] Instalar e configurar Proton Drive entre máquinas
      - sync_root aplicado: `C:\Users\USUARIO\Documents\p\My files\backup\ecosystem`
      - Subpastas criadas; ecosystem.json atualizado com todos os caminhos derivados
      - [x] Testar round-trip: arquivar página no AKASHA → aparece no Proton → segunda máquina

#### 0.6 — OGMA: migrar de Turso para Proton Drive (SQLite local)

Motivação: Proton mantém cópias locais em todas as máquinas + nuvem, sem depender de
conta externa. Turso só mantém na nuvem.

- [x] Remover integração Turso do OGMA (`src/main/database.ts` — voltar para SQLite puro local)
      Remover dependências: `@libsql/client`, `dotenv` e o `.env` com token Turso
- [x] Adicionar `ogma/` ao `sync_root` em `apply_sync_root()` (Rust + derive_paths Python)
      `data_path: {sync_root}/ogma/` — inclui `ogma.db`, `uploads/`, `exports/`
- [x] Atualizar `paths.ts` do OGMA para usar `ogma.data_path` do ecosystem.json (fallback local)
- [ ] Testar migração: exportar dados do Turso → importar no SQLite local antes de remover

#### 0.7 — Hermes: usar output_dir do ecosystem.json no startup

Objetivo: Hermes deve ler `hermes.output_dir` do ecosystem.json se `outdir` não estiver
nas prefs locais — o mesmo padrão já aplicado ao `mnemo_dir`. Após `apply_sync_root`,
Hermes passa a usar `{sync_root}/hermes/` automaticamente.

- [x] `Hermes/hermes.py` — `_load_prefs()`: se `outdir` não estiver em prefs, ler
      `hermes.output_dir` do ecosystem.json como fallback

#### 0.8 — AKASHA: integração Hermes + DB no Proton + lista negra + UI

##### 0.8a — AKASHA indexa arquivos do Hermes na busca local
- [x] `AKASHA/config.py` — adicionar `hermes_output: str` lendo `hermes.output_dir` do ecosystem.json
- [x] `AKASHA/services/local_search.py` — adicionar 6ª fonte `HERMES` em `index_local_files()`

##### 0.8b — AKASHA: DB (biblioteca + lista negra) movível para Proton
- [x] `AKASHA/config.py` — `DB_PATH` lê `akasha.data_path` do ecosystem.json se disponível
- [x] `ecosystem_client.py` — `derive_paths()`: adicionar `data_path` à seção `akasha`
- [x] `HUB/src-tauri/src/commands/config.rs` — `apply_sync_root()`: incluir `akasha.data_path`

##### 0.8c — AKASHA: aba "lista negra" no menu
- [x] `AKASHA/database.py` — `get_blocked_domains()` já existia (retorna set[str])
- [x] `AKASHA/routers/domains.py` — adicionar rota `GET /domains` com listagem + template
- [x] `AKASHA/templates/domains.html` — nova página herdando base.html
- [x] `AKASHA/templates/base.html` — adicionar link "lista negra" no nav

#### 0.8d — AKASHA: melhorias de UI nos cards e páginas
- [x] `AKASHA/static/style.css` — adicionar classe `.page-subtitle`
- [x] `AKASHA/templates/library.html` — subtítulo descritivo da Biblioteca
- [x] `AKASHA/templates/sites.html` — subtítulo descritivo de Sites
- [x] `AKASHA/routers/crawler.py` — rota `POST /sites/add-quick` (quick-add sem parâmetros extras)
- [x] `AKASHA/templates/_macros.html` — botão "Adicionar a Sites" nos cards

#### 0.9 — Mnemosyne: caminhos primários do ecosystem.json + pastas extras

Objetivo: Mnemosyne lê `watched_dir`, `vault_dir`, `chroma_dir` do ecosystem.json no
startup (HUB é fonte de verdade). SetupDialog exibe esses caminhos como read-only e
permite adicionar `extra_dirs` para indexação adicional.

- [x] `Mnemosyne/core/config.py` — adicionar `extra_dirs: list[str]`; `load_config()` merge
      ecosystem.json: watched_dir/vault_dir/chroma_dir do ecosystem têm precedência
- [x] `Mnemosyne/gui/main_window.py` — SetupDialog: caminhos principais viram read-only
      (vindos do ecosystem); adicionar QListWidget "Pastas extras" com +/−
- [x] `Mnemosyne/core/` (indexador) — loop sobre `[watched_dir] + extra_dirs`

### EXTRAS — Utilitários e manutenção

#### Script de build de produção
- [x] `buildar.sh` — bash (CachyOS): `cargo tauri build` para AETHER e HUB + `npm run dist:linux` para OGMA; aceita args para buildar só apps específicos
- [x] `buildar.bat` — batch (Windows 10): mesma sequência com `npm run dist:win` para OGMA
- [x] `README.md` — seção "Build de produção" atualizada com os novos scripts

#### Scripts de atualização de dependências
- [x] `atualizar.sh` — bash (CachyOS): git pull + uv sync (AKASHA) + pip install -r (KOSMOS, Mnemosyne, Hermes) + npm install (AETHER, HUB, OGMA)
- [x] `atualizar.bat` — batch (Windows 10): mesma sequência com comandos equivalentes
- [x] `README.md` — seção "Atualizar dependências" adicionada entre "Rodar os apps" e "Build de produção"

### EXTRAS — Bugs e melhorias urgentes

#### HUB — Race condition no ecosystem.json (paths somem às vezes)
- Causa: `write_section` faz read-modify-write do arquivo inteiro sem lock.
  Se HUB e outro app chamam `write_section` ao mesmo tempo (ex: app abrindo
  enquanto HUB salva), o último a escrever apaga as mudanças do outro.
- Solução acordada: **lock file** `.ecosystem.lock` na mesma pasta do JSON.
  Funciona cross-process e cross-language (Python + Rust + futuro TS) sem
  dependência de APIs específicas de plataforma.
- [x] `ecosystem_client.py` — usar `filelock.FileLock` (lib `filelock`) em torno
  do read-modify-write; adicionar `filelock` ao `requirements.txt` de cada app Python
- [x] `HUB/src-tauri/src/ecosystem.rs` — implementar lock file manual:
  `OpenOptions::create + write` em `.ecosystem.lock`, `lock_exclusive` via `fs2`,
  liberar após o `rename`. Adicionar `fs2` ao `Cargo.toml` do HUB.

#### HUB — Caminhos não atualizam nos apps sem reiniciar
- Causa: todos os apps leem ecosystem.json UMA VEZ no startup. Não há watcher.
- Solução acordada: **aviso de reinicialização** após salvar (opção simples).
  File watcher descartado — mudança de paths em runtime exigiria refatoração
  invasiva em todos os módulos que cachêam o valor de Paths.X.
- [x] `HUB/src/views/SetupView.tsx` — exibir mensagem após `handleSave()` bem-sucedido:
  "Configuração salva. Reinicie cada app para aplicar os novos caminhos."
  (mesmo padrão do `syncMsg` já existente para o sync_root)

#### KOSMOS — Stats travando e fechando o app
- Bug: `_reload_charts()` roda na thread principal fazendo k-means (numpy)
  + queries + matplotlib, bloqueando o Qt event loop. Windows marca como "não respondendo".
- [x] `KOSMOS/app/ui/views/stats_view.py` — mover carregamento de dados para `QThread`
  (StatsLoadWorker); widgets são criados na thread principal após o worker terminar

#### KOSMOS — Archive_path ignora ecosystem.json
- Bug: `Paths.ARCHIVE` estava hardcoded como `ROOT/"data"/"archive"`.
  O `archive_path` configurado via HUB (Proton Drive) era ignorado.
- [x] `KOSMOS/app/utils/paths.py` — ler `kosmos.archive_path` do ecosystem.json
  no startup; usar como `ARCHIVE` se disponível (fallback para `DATA/"archive"`)

#### Hermes — "Descarregar" → "Baixar" (português do Brasil)
- "Descarregar" é PT-Portugal. Renomear para "Baixar" no botão e na aba.
- [x] `Hermes/hermes.py` — renomear label do botão, da aba e do comentário de seção

#### Hermes — UX de playlist confusa: qualidade não aparece após carregar lista
- Após carregar a playlist, o usuário não sabe que precisa clicar em um vídeo
  para ver as opções de qualidade. A UI não dá feedback sobre isso.
- [x] `Hermes/hermes.py` — instrução visual atualizada: "Selecione um vídeo acima
  para ver as opções de qualidade e baixar individualmente."
- [x] `Hermes/hermes.py` — auto-seleciona o primeiro vídeo ao carregar playlist
  — flag `_from_playlist_select` mantém a lista visível após selecionar vídeo individual
  — `_on_inspect_done` só esconde o painel de playlist em inspeções fora da playlist

#### Mnemosyne — Indexação trava o computador mesmo com LLM cloud
- Configuração confirmada no Windows 10: LLM = kimi-k2.5:cloud (nuvem, OK), embedding = bge-m3:latest (local, ~570MB)
- Causa raiz: `Chroma.from_documents()` envia TODOS os chunks para o Ollama de uma vez,
  sem pausas. bge-m3 ocupa ~570MB na RAM de GPU/CPU; com muitos arquivos são milhares
  de chamadas consecutivas sem liberar memória → travamento.
- [x] `Mnemosyne/core/indexer.py` — processar chunks em lotes (ex: 50 chunks por vez)
  usando `Chroma.add_documents()` em loop com `time.sleep(0.1)` entre lotes,
  ao invés de `Chroma.from_documents()` com tudo de uma vez
- [x] `Mnemosyne/gui/main_window.py` — deixar mais claro na SetupDialog que
  "Modelo de embedding" roda LOCALMENTE (tooltip: "Usado na indexação — roda na sua máquina via Ollama")

---

#### 0.10 — Arquivos de configuração de todos os apps no Proton Drive

Objetivo: config local de cada app também fica na pasta sincronizada, para que as
preferências se propaguem entre máquinas sem reconfigurar manualmente.

Estrutura confirmada: `{sync_root}/{app}/.config/settings.json` para todos os apps.

```
{sync_root}/
├── ogma/
│   ├── ogma.db          ← banco SQLite (já feito no 0.6)
│   ├── uploads/
│   ├── exports/
│   └── .config/
│       └── settings.json
├── akasha/
│   ├── akasha.db
│   └── .config/
│       └── settings.json
├── hermes/
│   ├── (transcrições .md)
│   └── .config/
│       └── settings.json
├── mnemosyne/
│   ├── docs/
│   ├── chroma_db/
│   └── .config/
│       └── settings.json
├── aether/
│   └── .config/
│       └── settings.json
└── kosmos/
    └── .config/
        └── settings.json
```

Cada app lê `{sync_root}/{app}/.config/settings.json` se `config_path` estiver definido
no ecosystem.json, com fallback para o arquivo local atual.

- [x] **`derive_paths()`** — adicionar `config_path: {sync_root}/{app}/.config` para cada app
- [x] **`apply_sync_root()` (Rust)** — criar subpastas `.config/` + escrever `config_path` no ecosystem.json
- [x] **OGMA** — `SETTINGS` em `paths.ts` usa `{ogma.config_path}/settings.json` se disponível
- [x] **Hermes** — `_load_prefs()` / `_save_prefs()` usa `{hermes.config_path}/settings.json` se disponível
- [x] **KOSMOS** — `Paths.SETTINGS` usa `{kosmos.config_path}/settings.json` se disponível
- [x] **Mnemosyne** — `load_config()` / `save_config()` usa `{mnemosyne.config_path}/settings.json` se disponível
- [ ] **AKASHA** — sem settings.json próprio; config está no akasha.db (sincronizado via 0.8b)
- [ ] **AETHER** — vault config já fica dentro de vault_path (sincronizado); sem settings separado

---

### FASE 1 — Interligação dos apps existentes
> Aproveita o que já existe. Mudanças cirúrgicas, sem novo app.

#### 1.1 — OGMA → AETHER (projetos de escrita)

##### Passo A — Renomear tipo `creative` → `writing` no OGMA
- [x] `src/renderer/types/index.ts`: alterar `ProjectType` union, SUBCATEGORIES,
      PROJECT_TYPE_LABELS ('Escrita'), PROJECT_TYPE_ICONS ('✍️' mantém),
      PROJECT_TYPE_DESCRIPTIONS
- [x] `src/renderer/components/Projects/NewProjectModal.tsx`: atualizar array TYPES
- [x] `src/renderer/views/ProjectDashboard/ProjectLocalDashboard.tsx`:
      renomear case `'creative'` → `'writing'`
- [x] `src/main/ipc.ts`: renomear todas as ocorrências do literal `'creative'`
- [x] `src/main/database.ts`: adicionar migration que faz
      `UPDATE projects SET project_type = 'writing' WHERE project_type = 'creative'`
      (o campo é TEXT sem CHECK constraint — migration simples)

##### Passo B — Integrar projetos de escrita com o AETHER
- [x] `src/main/database.ts`: adicionar coluna `aether_project_id TEXT` na tabela
      `projects` (nova migration)
- [x] OGMA lê `aether.vault_path` do `ecosystem.json` na criação de projeto
- [x] Ao criar projeto com `project_type = 'writing'`, OGMA escreve no vault AETHER:
      - `{vault}/{uuid}/project.json`  (formato Project do AETHER — campos: id, name, project_type, genre, description)
      - `{vault}/{uuid}/{book_uuid}/book.json`  (livro padrão vazio, sem capítulos)
- [x] Salvar `aether_project_id` no banco do OGMA para manter o vínculo
- [x] Botão "Abrir no AETHER" em projetos de escrita (desabilitado se vault não configurado)

#### 1.2 — KOSMOS → Mnemosyne (artigos salvos)
- [x] KOSMOS escreve `archive_path` e `data_path` em `ecosystem.json` na inicialização
      via `ecosystem_client.write_section("kosmos", {...})` em `KOSMOS/main.py`
- [x] Mnemosyne lê `ecosystem.json` e oferece o archive do KOSMOS
      como pasta sugerida na tela de indexação (botão "Sugestões do ecossistema" na SetupDialog)
- [ ] Verificar se o botão "Arquivar" em artigos salvos chama
      `archive_manager` corretamente — garantir que gera `.md` válido

#### 1.3 — AETHER → Mnemosyne (indexar escritos)
- [x] AETHER escreve `vault_path` em `ecosystem.json` na inicialização
      (startup Rust, após carregar vault — `ecosystem::write_section()` em lib.rs)
- [x] Mnemosyne oferece vault AETHER como pasta sugerida (botão "Sugestões do ecossistema")
- [ ] Testar indexação dos `.md` de capítulos pelo Mnemosyne

#### 1.4 — Hermes → Mnemosyne (transcrições indexáveis)
- [x] Adicionar campo "Pasta de saída do Mnemosyne" na aba Transcrever do Hermes
      Lê `mnemosyne.index_paths[0]` do ecosystem como sugestão; desabilitado se vazio
- [x] Adicionar checkbox "Indexar no Mnemosyne após transcrever"
      Salva o `.md` diretamente numa das pastas monitoradas pelo Mnemosyne
- [x] Formato: Markdown limpo com frontmatter mínimo (título, data, fonte/URL, duração)

#### 1.5 — Completar contrato ecosystem.json (seções faltantes)

Cada app deve escrever sua seção completa no startup. Schema alvo:
```json
{
  "aether":    { "vault_path": "...", "exe_path": "..." },
  "ogma":      { "data_path": "...", "exe_path": "..." },
  "kosmos":    { "archive_path": "...", "data_path": "...", "exe_path": "..." },
  "mnemosyne": { "watched_dir": "...", "vault_dir": "...", "index_paths": ["..."], "exe_path": "..." },
  "hermes":    { "output_dir": "...", "exe_path": "..." },
  "akasha":    { "archive_path": "...", "base_url": "...", "exe_path": "..." }
}
```

- [x] **OGMA** — `writeSection("ogma", { data_path, exe_path })` no startup
      (`writeSection` existe em `ecosystem.ts` mas nunca é chamado)
- [x] **Mnemosyne** — `write_section("mnemosyne", { watched_dir, vault_dir, index_paths, exe_path })` no startup
      (paths vêm do `AppConfig`; `persist_dir` = `{watched_dir}/.mnemosyne/chroma_db`)
- [x] **Hermes** — `write_section("hermes", { output_dir, exe_path })` no startup
      (`output_dir` = pasta de downloads/transcrições configurada na UI)
- [x] **AKASHA** — adicionar `archive_path` à seção já escrita por `register_akasha()`

#### 1.6 — Scraper compartilhado: KOSMOS e AKASHA

Objetivo: eliminar a duplicação de código da cascata de extração web.
`ecosystem_scraper.py` (raiz do repo) é o único ponto de manutenção da cascata.

- [x] Criar `ecosystem_scraper.py` — cascata newspaper4k → trafilatura → readability-lxml
      → inscriptis → BeautifulSoup; `extract(html, url, output_format)` sem I/O próprio
- [x] `AKASHA/services/archiver.py` — delegar `_cascade_extract` ao módulo compartilhado
- [x] `AKASHA/services/library.py` — idem para `_fetch_and_extract`
- [x] `KOSMOS/app/core/article_scraper.py` — simplificar para `_cascade_extract(..., output_format="html")`
- [x] `KOSMOS/requirements.txt` — adicionar `inscriptis` e `markdownify`

#### 1.8 — AKASHA: busca local cobre todo o ecossistema

- [x] Indexar `AKASHA/data/archive/` própria no FTS5 (source "AKASHA")
      (`index_local_files()` em `services/local_search.py` — mesmo extractor do KOSMOS)
- [x] Ler `mnemosyne.watched_dir` e `mnemosyne.vault_dir` do ecosystem.json em `config.py`
- [x] Indexar `mnemosyne.watched_dir` no FTS5 (source "MNEMOSYNE")
- [x] Indexar `mnemosyne.vault_dir` no FTS5 (source "OBSIDIAN")
      (depende de 1.5 — Mnemosyne precisa escrever esses caminhos primeiro)

#### 1.9 — Mnemosyne: sugestões do ecossistema cobrindo todos os archives

- [x] Adicionar AKASHA archive (`akasha.archive_path`) nas sugestões da SetupDialog
      (depende de 1.5 — AKASHA precisa escrever `archive_path` primeiro)

---

### FASE 3 — Android (APK)
> ⚠️ **SUSPENSA PARA REPLANEJAMENTO.** O HUB passou a ter papel de LOGOS (orquestrador de IA), mudando seu foco principal.
> A necessidade de acesso ao ecossistema no Android continua existindo, mas a abordagem precisa ser repensada
> — provavelmente um app separado ou solução diferente do HUB. Itens abaixo mantidos como referência histórica.

#### 3.1 — Build Android do hub
- [ ] Configurar ambiente Tauri Android:
      - Android Studio + NDK
      - `cargo install tauri-cli` (já deve estar instalado do AETHER)
- [ ] Adaptar `tauri.conf.json` para Android (permissões de filesystem)
- [ ] Primeiro build de teste no tablet (`cargo tauri android dev`)
- [ ] Resolver incompatibilidades de UI para toque (botões, scroll)
- [ ] Build de release (APK assinado)

#### 3.2 — Sincronização de dados
- [ ] Configurar Syncthing: pastas a sincronizar
      - Vault AETHER completo
      - `kosmos/data/archive/`
      - `hub_read_state.json`
- [ ] Testar round-trip completo:
      - Escrever capítulo no tablet → sync → abrir no AETHER no PC
      - Salvar artigo no KOSMOS → sync → aparecer no hub Android
- [ ] Tratar conflitos de sync (dois dispositivos editam o mesmo arquivo)

#### 3.3 — Acesso remoto (fora da rede local)
- [ ] Instalar Tailscale no PC e no tablet
- [ ] Hub detecta se Ollama está acessível (local ou via Tailscale)
- [ ] Módulo Projetos: acesso ao `ogma.db` via Tailscale quando remoto
- [ ] Fallback gracioso: módulos funcionam offline com dados já sincronizados

---

### FASE 4 — Features extras
> Qualidade de vida. Só após Fase 3 estável.

- [x] Verificar sistema de log em todos os apps e criar onde não existir
      — OGMA: ✅ `createLogger` + `setupGlobalErrorHandlers` em main.ts
      — HUB: ✅ `tauri_plugin_log`, arquivo diário, 7 dias de retenção
      — AETHER: ✅ `tauri_plugin_log`, arquivo diário, 7 dias de retenção
      — KOSMOS: ✅ `setup_logger()` em app/utils/logger.py, arquivo + stderr
      — Mnemosyne: ✅ criado `core/logger.py`, rotação diária, 7 backups
      — Hermes: ✅ criado `_setup_logger()` em hermes.py; `_log()` da UI persiste em arquivo
      — AKASHA: pendente — criar ao iniciar o desenvolvimento
- [ ] Integrar AKASHA aos outros apps do ecossistema:
      — OGMA, AETHER, KOSMOS, Mnemosyne, Hermes: seleção de texto → "Pesquisar no AKASHA"
        (menu de contexto ou botão flutuante que abre `http://localhost:7071/search?q=<texto>`)
      — HUB: botão/atalho na barra lateral para abrir AKASHA no browser
      — Requisito: AKASHA deve estar rodando para receber a requisição
- [ ] Quick capture: widget ou atalho Android para adicionar nota rápida
      ao OGMA sem abrir o app completo
- [ ] Streak AETHER visível no hub (ler `sessions.json` do vault)
- [ ] Notificação Android: novos artigos no archive do KOSMOS
- [ ] Busca cross-módulo: pesquisar em escritos + projetos + artigos
- [ ] stellar-downloader + transcriber integrados (HERMES):
      - Download → transcrição automática → salvar no archive
- [ ] Exportação do hub: capítulo AETHER → PDF/EPUB direto do Android

---

#### Dependências entre fases

  Fase 0 ──► Fase 1 (qualquer sub-item)
  Fase 0 ──► Fase 2.1
  Fase 2.1 ──► Fase 2.2, 2.3, 2.4, 2.5 (paralelas)
  Fase 2 (completa) ──► Fase 3
  Fase 3 ──► Fase 4

---

#### Estado dos apps individuais (pré-condições para integração)

  AETHER        ✅  Fases 0–5 completas. Vault format estável. Sem bloqueios.
  OGMA          ✅  Schema v2 implementado (database.ts:114). IPC usa
                    project_properties + page_prop_values em produção.
                    Itens abertos da Fase 10 (FTS5/Turso, testes offline)
                    são qualidade/teste — não bloqueiam integração.
  KOSMOS        ✅  archive_manager.py funcional. Pronto para integração.
  Mnemosyne     ⚠️  Protótipo incompleto. core/rag.py vazio. Usa HuggingFace
                    em vez de Ollama (inconsistente com o ecossistema).
                    Design diverge do sistema visual. Precisa de
                    desenvolvimento antes de entrar no hub.
  transcriber   ✅  Utilitário funcional. Mudança mínima necessária.
  stellar-dl    ✅  Utilitário funcional. Mudança mínima necessária.

#### Estado das fases do ecossistema

  Fase 0: ✅ Base concluída (0–0.5). Items 0.6–0.9 em andamento (sync + integrações)
  Fase 1: ✅ Concluída — 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 1.9 concluídas
            ⚠️  Item pendente: 1.2 — verificar botão "Arquivar" no KOSMOS
  Fase 2: ✅ Concluída — 2.1, 2.2, 2.3, 2.4, 2.5 e 2.6 concluídas
  Fase 3: ⚠️ suspensa — HUB agora é LOGOS; acesso Android a repensar separadamente
  Fase 4: não iniciada

---

---

## HUB — Dashboard e Painel de Controle

### Fase 2 — Fundação e Módulos
> HUB como dashboard central do ecossistema: lança apps, centraliza configuração, visualiza dados de todos os outros programas e hospeda o LOGOS (proxy de LLM).
> Stack: Tauri 2 + React + TypeScript. Read-only por padrão nos módulos de visualização — não substitui os editores primários.
> Módulos Android originalmente planejados aqui foram movidos para replanejamento separado (ver FASE 3).

### 2.1 — Fundação + Tela de Configuração
- [x] Criar projeto Tauri 2 em `program files/HUB/`
- [x] Copiar design system do AETHER sem modificações:
      `tokens.css`, `animations.css`, `typography.css`, `components.css`
      `CosmosLayer.tsx`, `Toast.tsx`, `ThemeToggle.tsx`
- [x] Splash screen com typewriter + CosmosLayer
- [x] Router interno: `splash → setup | home`
      `type HubView = 'home' | 'writing' | 'reading' | 'projects' | 'questions'`
- [x] Tela de configuração (SetupView): lê/edita/valida caminhos do `ecosystem.json`
      — campos: `aether.vault_path`, `kosmos.archive_path`, `ogma.data_path`
      — ícone ✓/✗ por campo via IPC `validate_path()`
- [x] Dashboard (HomeView): 4 cards com CosmosLayer individual
      — cards desabilitados se caminho não configurado
- [x] Rust: `commands/config.rs` — `read_ecosystem_config`, `validate_path`, `save_ecosystem_config`
      usando `ecosystem.rs` copiado do AETHER

### 2.2 — Módulo Escrita (AETHER vault, read-only)
- [x] Rust `commands/writing.rs`:
      `list_writing_projects(vault_path)` — lê todos `{vault}/*/project.json`
      `list_books(vault_path, project_id)` — lê `{vault}/{proj}/*/book.json`
      `read_chapter(vault_path, project_id, book_id, chapter_id)` — lê `.md`
- [x] `WritingView.tsx` — grade de projetos com CosmosLayer individual
- [x] `BookView.tsx` — árvore livros + capítulos com status e word count
- [x] `ChapterView.tsx` — `react-markdown` renderiza o `.md`
- [x] Tipos `Project`, `Book`, `ChapterMeta` copiados de AETHER

### 2.3 — Módulo Leituras (KOSMOS archive, read-only)
- [x] Rust `commands/reading.rs`:
      `list_articles(archive_path)` — scan `{archive}/**/*.md`, parseia frontmatter
      `read_article(path)` — separa frontmatter do corpo
      `toggle_read(archive_path, article_path)` — lê/escreve `hub_read_state.json`
- [x] `ReadingView.tsx` — lista com filtros (fonte, lido/não lido); badge não lidos
- [x] `ArticleView.tsx` — frontmatter em destaque + `react-markdown`

### 2.4 — Módulo Projetos (OGMA, read-only)
- [x] Adicionar `rusqlite = { version = "0.31", features = ["bundled"] }` ao Cargo.toml
      (`bundled` compila SQLite estático — funciona no Android)
- [x] Rust `commands/projects.rs`:
      `list_ogma_projects(db_path)` — SELECT projects WHERE status != 'archived'
      `list_project_pages(db_path, project_id)` — SELECT pages WHERE is_deleted = 0
- [x] `lib/editorjs-renderer.tsx` — renderiza blocos Editor.js (`paragraph`, `header`,
      `list`, `checklist`, `quote`, `code`, `table`, `delimiter`, `columns`)
- [x] `ProjectsView.tsx` + `PageView.tsx`

### 2.5 — Módulo Perguntas (Ollama, sem Rust)
- [x] `lib/ollama.ts`:
      `listModels()` — GET `localhost:11434/api/tags`
      `streamChat(model, messages)` — POST `/api/chat` com streaming NDJSON
- [x] `QuestionsView.tsx` — seletor de modelo, histórico de sessão, streaming
      banner "Ollama offline" + botão Tentar novamente

### 2.6 — Barra de atalhos para apps externos
> Barra permanente visível em todas as views. Lança os 5 apps e indica se estão rodando.

- [x] Tela de Setup: adicionar campos de executável para cada app
      — `aether.exe_path`, `ogma.exe_path`, `kosmos.exe_path`,
        `mnemosyne.exe_path`, `hermes.exe_path` em `ecosystem.json`
      — auto-descoberta por nome de processo conhecido como fallback
        (ex.: buscar `AETHER.exe` / `aether` no PATH e locais comuns)
      — ícone ✓/✗ por campo (reutilizar `validate_path()` existente)
- [x] Rust `commands/launcher.rs`:
      `launch_app(exe_path: String) -> Result<(), AppError>` — `Command::new(exe_path).spawn()`
      `is_app_running(process_name: String) -> bool` — lista processos do SO
        (Windows: `tasklist`, Linux: `/proc` ou `pgrep`)
      `get_all_app_statuses() -> HashMap<String, bool>` — chama `is_app_running` para os 5 apps
- [x] `AppBar.tsx` — barra lateral esquerda fixa com 5 botões de app
      — cada botão: sigla em IM Fell English itálico + ponto indicador (rodando / parado)
      — clique: chama `launch_app`; se já rodando, apenas pulsa o indicador
      — polling a cada 5s via `get_all_app_statuses` para atualizar status
- [x] Integrar `AppBar` no layout raiz (visível em todas as views, inclusive Home)

---

### HUB: redesign da UI como dashboard do ecossistema

O HUB deixou de ser um companion Android e é agora o **painel de controle central**
do ecossistema. A UI atual (se existente) foi projetada para outra finalidade —
precisa ser reimaginada como um dashboard desktop (Tauri).

#### Arquitetura de navegação
- [x] Sidebar vertical persistente com 4 seções principais:
  — **Home** (dashboard de status dos apps)
  — **LOGOS** (fila de LLM + monitor de VRAM)
  — **Atividade** (feed de eventos cross-app)
  — **Configuração** (ecosystem.json + sync_root)
- [x] Topbar mínima: nome do ecossistema + indicador global de saúde + botão de silêncio

#### Tela Home — status dos apps
- [x] Card por app do ecossistema (AKASHA · KOSMOS · AETHER · Mnemosyne · Hermes · OGMA):
  — status ao vivo (running / stopped / erro) via ping periódico nos `/health` endpoints
  — porta, botão "abrir no browser" (apps web) ou "focar janela" (apps Qt/Tauri)
  — botão de iniciar / encerrar cada app diretamente do HUB
- [ ] Badge de alerta quando app está offline mas deveria estar rodando
- [ ] Mini-resumo por app (última atividade, contagem de arquivos/artigos/etc.)

#### Painel de configuração do ecossistema
- [x] Campo `sync_root` com botão "Aplicar" — chama `apply_sync_root()` e mostra preview
  dos caminhos derivados por app antes de confirmar
- [ ] Aviso de migração: se sync_root muda e dados existem no caminho antigo, exibir
  instrução para mover arquivos (ex.: `akasha.db`, archives) antes de reiniciar
- [ ] Editor visual das seções do `ecosystem.json` (alternativa ao JSON bruto):
  campos por app com labels descritivos e validação de caminhos

#### System tray / always-accessible
- [x] HUB fica na bandeja do sistema ao minimizar (não fecha, não some da taskbar)
- [x] Fechar janela (× ou Alt+F4) → oculta na bandeja em vez de encerrar o processo
- [x] Menu de contexto na bandeja (clique direito): "Abrir HUB" · "Silenciar LOGOS" · "Fechar HUB"
  — "Silenciar LOGOS" chama POST /logos/silence diretamente pelo processo do HUB
  — abrir/fechar apps individuais: acessível via DashboardView (cards da Home)
- [x] Infraestrutura de notificações nativas (tauri-plugin-notification):
  — comando `send_notification(title, body)` disponível para o frontend
  — gatilhos por evento (app offline, VRAM crítica, etc.) dependem do Feed de Atividade
- [ ] Notificações automáticas por evento: depende de `activity.jsonl` por app (ver Feed de Atividade)

#### Design visual
- [x] Seguir DESIGN_BIBLE.txt — tema padrão: "Atlas Astronômico à Meia-Noite" (`#12161E`)
- [x] Dois modos de janela:
  — **Compacto** (~640×440): só cards de status + botões de ação imediata
  — **Expandido** (~1280×800): dashboard completo com sidebar + todas as seções
- [x] Tipografia e paleta consistentes com AETHER/OGMA (tokens compartilhados do ecossistema)

---

### Pendências e Features

### Controle de recursos — extensão do LOGOS

- [x] Painel de VRAM em tempo real + fila de prioridades visível
  — mostrar o que está rodando agora em P1/P2/P3 com estimativa de VRAM ocupada
  — Implementado: `HUB/src/components/LogosPanel.tsx` (polling 5s via Tauri IPC)
  — Posicionado como footer do HomeView
- [x] Botão "Silêncio" — pausa instantânea de todas as tarefas P3 para liberar GPU
  — útil ao iniciar escrita no AETHER ou chat no HUB
  — Implementado: botão "silenciar" no LogosPanel (chama `logos_silence` Tauri command)
- [x] Painel de gerenciamento do Ollama:
  — listar modelos carregados na VRAM com tamanho (GET /logos/models → `logosListModels`)
  — ver qual app está usando o LOGOS no momento (`active_app` no StatusResponse)
  — forçar `keep_alive: 0` por modelo individual (`logosUnloadModel` Tauri command)
- [x] Perfis de workflow com um clique:
  — "Modo Escrita": AETHER/HUB mantêm P1; KOSMOS reader → P2; Mnemosyne RAG → P3
  — "Modo Estudo": Mnemosyne RAG → P1; KOSMOS reader → P2
  — "Modo Consumo" e "Normal": sem override de prioridade
  — perfil persistido em `LogosState.active_profile`; alterado via POST /logos/profile ou `logosSetProfile`
- [x] Modo Sobrevivência (Windows/CPU-only) — ativado automaticamente em builds Windows via `cfg!(target_os = "windows")`:
  — `keep_alive: 0` forçado em todo request (RAM liberada imediatamente)
  — `num_ctx` limitado a 2048 pelo LOGOS independente do que o app pediu
  — modelos >3B rejeitados com 429 ("apenas modelos ≤3B aceitos")
  — requests P3 rejeitados imediatamente (sem análise em background)
  — paralelismo desabilitado (sempre 2 permits, serial mesmo em modelos leves)
  — badge "Modo Sobrevivência — Windows" exibido na LogosView
- [x] Monitoramento de CPU e RAM no painel LOGOS:
  **Motivo:** a barra de VRAM (já implementada via sysfs) só funciona com GPU discreta AMD/NVIDIA.
  No Windows 10 (sem GPU) e no laptop (Intel integrada sem ROCm), o painel fica cego. CPU e RAM
  são os recursos críticos nessas máquinas. Sem esse monitoramento, P3 pode saturar o CPU a 90%
  sem que o LOGOS perceba (bug confirmado com Mnemosyne idle indexer).
  Fonte: crates.io/crates/sysinfo — cross-platform, Linux + Windows.
  **Implementação — Rust (`HUB/src-tauri/src/logos.rs` + `Cargo.toml`):**
  1. Adicionar ao `Cargo.toml`: `sysinfo = { version = "0.32", features = ["cpu"] }`
  2. Adicionar campo `sys: sysinfo::System` ao struct `Inner`, inicializado com `System::new_all()`
     CRÍTICO: manter a mesma instância entre leituras — CPU% é calculado como delta entre
     duas leituras consecutivas. Criar nova instância a cada poll retorna sempre 0%.
  3. No loop de `collect_status()`: chamar `inner.sys.refresh_cpu_all()` e
     `inner.sys.refresh_memory()` antes de ler os valores
  4. Adicionar ao `StatusResponse`:
     `cpu_pct: f32`      — de `sys.global_cpu_usage()`
     `ram_free_mb: u64`  — de `sys.available_memory() / 1_048_576`
  5. Na lógica de bloqueio de P3: adicionar condições — bloquear quando `cpu_pct > 85.0`
     OU `ram_free_mb < 1536` (além do `vram_pct > 0.85` já existente)
  **Implementação — TypeScript (`HUB/src/components/LogosPanel.tsx`):**
  6. Ler `cpu_pct` e `ram_free_mb` do status (já chegam via `logosGetStatus`)
  7. Detectar ausência de GPU: `vramPct === null` → substituir barra de VRAM por barras de CPU e RAM
     CPU: verde se < 70%, amarelo se 70–85%, vermelho se > 85%
     RAM livre: verde se > 4 GB, amarelo se 1.5–4 GB, vermelho se < 1.5 GB
  8. Em máquinas com GPU: exibir CPU% e RAM como texto compacto ao lado da barra de VRAM
  **Tipo do status TS (`HUB/src/types.ts`):**
  9. Adicionar `cpu_pct?: number` e `ram_free_mb?: number` ao tipo `LogosStatus`

- [x] LOGOS: injetar `keep_alive` automaticamente por prioridade no proxy transparente:
  **Motivo:** por padrão o Ollama retém modelos por 5 minutos após ociosidade. Um modelo P3
  (KOSMOS background) fica ocupando VRAM 5 minutos depois de terminar, impedindo P1 de usar
  o hardware. O parâmetro `keep_alive` por-requisição sobrescreve o global `OLLAMA_KEEP_ALIVE`
  e é rastreado por modelo individualmente. Aplicado no proxy, é completamente transparente para
  os apps — nenhum deles precisa saber do LOGOS.
  Fonte: docs.ollama.com/faq; markaicode.com/ollama-keep-alive-memory-management
  **Implementação (`HUB/src-tauri/src/logos.rs` — handler do proxy `/api/chat` e `/api/generate`):**
  1. No handler de proxy, após receber o body JSON do app cliente:
     a. Deserializar: `let mut body: serde_json::Value = serde_json::from_slice(&bytes)?;`
     b. Determinar a prioridade — a partir do header `X-Priority` enviado pelo `ecosystem_client.py`
        ou inferida do `X-App` header (mnemosyne=P2, kosmos=P3, hub=P1)
     c. Injetar conforme prioridade:
        P1 → `body["keep_alive"] = json!(-1)`  (mantém aquecido indefinidamente)
        P2 → `body["keep_alive"] = json!("10m")` (libera após 10 min de inatividade)
        P3 → `body["keep_alive"] = json!("0")`  (descarrega imediatamente após resposta)
     d. Reserializar e repassar ao Ollama na porta 11434
  2. Apps que usam `ecosystem_client.py` → `request_llm()` já envia `X-App`; basta mapear app→prioridade
     no LOGOS (ex: app="mnemosyne" → P2)
  3. Para `/api/embed` (embeddings): sempre P3 → `keep_alive: "0"` (embedding models não precisam ficar quentes)

- [x] LOGOS: configurar variáveis de ambiente do Ollama por perfil de hardware no startup:
  **Motivo:** o Ollama usa configurações globais que não distinguem hardware. Sem `OLLAMA_GPU_OVERHEAD`,
  a RX 6600 pode sofrer OOM ao carregar dois modelos simultaneamente (ex: nomic-embed-text + llama 3).
  `OLLAMA_FLASH_ATTENTION=1` ativa tiling de atenção que reduz uso de VRAM em contextos longos
  (suportado via backend Triton no ROCm para RDNA2/gfx1032 da RX 6600).
  `OLLAMA_MAX_LOADED_MODELS` impede que o Ollama carregue 3 modelos simultâneos (padrão) em máquinas
  onde nem 2 cabem confortavelmente.
  Fonte canônica: github.com/ollama/ollama/blob/main/envconfig/config.go
  **Parâmetros por perfil:**
  | Variável                   | high (RX 6600) | medium (MX150) | low (i5-3470) |
  |---------------------------|----------------|----------------|---------------|
  | OLLAMA_MAX_LOADED_MODELS   | 2              | 1              | 1             |
  | OLLAMA_GPU_OVERHEAD (bytes)| 524 288 000    | 209 715 200    | 0             |
  | OLLAMA_FLASH_ATTENTION     | 1              | 1              | 0 (sem GPU)   |
  | OLLAMA_NUM_PARALLEL        | 2              | 1              | 1             |
  **Implementação (`HUB/src-tauri/src/logos.rs`):**
  1. Opção A — se o LOGOS gerencia o processo Ollama (recomendado):
     Em `Inner::start_ollama()` (ou equivalente), construir o `Command` com `.envs(env_map)`
     onde `env_map` é montado a partir do `HardwareProfile` detectado no startup
  2. Opção B — se o Ollama roda como serviço do sistema:
     Escrever as variáveis em `~/.config/ollama/ollama_env` e instruir o usuário a configurar
     o serviço systemd com `EnvironmentFile=%h/.config/ollama/ollama_env`
     O LOGOS escreve esse arquivo no startup e exibe aviso se o serviço precisar ser reiniciado
  3. Registrar as variáveis ativas no log de startup do LOGOS para debugging

- [x] LOGOS: preempção inteligente de P3 — suspender (não cancelar) ao detectar P1 sem VRAM:
  **Motivo:** o botão "silenciar" atual cancela P3 de forma cega. A literatura científica
  (Priority-Aware Preemptive Scheduling, arxiv 2503.09304; Topology-aware Preemptive Scheduling,
  arxiv 2411.11560) mostra que o correto é:
  a) Calcular se P1 cabe na VRAM disponível ANTES de preemptar — preemptar sem espaço suficiente
     desperdiça VRAM e introduz latência desnecessária.
  b) Suspender P3 (keep_alive: "0" força unload), não cancelar — a fila P3 é mantida e
     retomada quando P1 encerra.
  **Implementação (`HUB/src-tauri/src/logos.rs`):**
  1. Ao receber request P1 via proxy:
     a. Verificar se há request P3 em execução (`active_priority == 3`)
     b. Consultar `/api/tags` para obter `size` estimado do modelo P1 em bytes
     c. Ler VRAM livre atual (sysfs)
     d. Se `vram_livre_mb < modelo_p1_mb + 500` (500 MB de buffer):
        — Enviar `POST /api/chat` com `{"model": modelo_p3, "keep_alive": "0"}` ao Ollama
          (prompt vazio força unload imediato sem gerar resposta)
        — Poll de `/api/ps` até o modelo P3 desaparecer (timeout 10s)
        — Só então encaminhar o request P1 ao Ollama
     e. Se VRAM livre é suficiente: não preemptar, deixar coexistir
  2. Manter `suspended_p3_queue: VecDeque<PendingRequest>` no `Inner`; ao P1 terminar,
     recolocar os P3 suspensos na fila normal
  3. Adicionar ao `StatusResponse`: `suspended_count: u32` para o LogosPanel mostrar

- [x] LOGOS: injetar parâmetros de eficiência por prioridade no body dos requests:
  **Motivo:** `num_thread`, `num_batch` e `num_ctx` são parâmetros por-requisição aceitos pelo
  Ollama no body de `/api/chat` e `/api/generate` (não são variáveis de ambiente). Injetados
  pelo proxy, permitem reduzir impacto de P3 no sistema sem mudar os apps. Evidência empírica:
  num_batch 512→256 reduz VRAM pico em ~20% (eastondev.com/blog/en/posts/ai/ollama-gpu-scheduling).
  `num_thread` controla quantos cores o Ollama usa para computação — limitá-lo em P3 libera CPU
  para o sistema e outros apps (literatura de CPU inference: diminishing returns além de 4 threads
  em modelos pequenos, arxiv 2311.00502).
  **Implementação (`HUB/src-tauri/src/logos.rs` — mesmo middleware do `keep_alive`):**
  Injetar no body antes de repassar ao Ollama, conforme prioridade:
  ```
  P3: num_thread=2, num_batch=256, num_ctx=2048
  P2: num_batch=256 (preservar RAM), num_ctx=null (app decide)
  P1: sem injeção (máxima performance, app decide tudo)
  ```
  Perfil `low` (CPU-only): P1 → num_thread=3 (deixar 1 core livre para o SO)
  Perfil `medium` (MX150): P3 → num_thread=2, num_gpu=0 (forçar CPU-only em background)

- [x] LOGOS: consciência de bateria via UPower/DBus (laptop Lenovo MX150):
  **Motivo:** indexação idle (P3) em bateria esgota carga e aquece o laptop sem benefício
  imediato. UPower é o padrão Linux para gerenciamento de energia (freedesktop.org).
  Pesquisa relevante: PowerLens (arxiv 2603.19584, 2025) demonstrou 38.8% de economia de
  energia via gerenciamento adaptativo de recursos em nível de sistema. Em bateria, a
  prioridade é preservar energia, não maximizar throughput de inferência.
  **Implementação (`HUB/src-tauri/src/logos.rs`):**
  1. Adicionar dependência `battery = "0.7"` ao `Cargo.toml` (cross-platform: Linux + Windows)
     Alternativa Linux-only com mais detalhes: crate `zbus` para ler `org.freedesktop.UPower`
  2. Adicionar campo `on_battery: bool` ao struct `Inner`; atualizar a cada 60s num tokio task
  3. Quando `on_battery = true`, aplicar em cascata:
     — Bloquear todos os requests P3 (retornar 503 com body `{"reason": "on_battery"}`)
     — Injetar `keep_alive: "0"` em P1 e P2 (liberar modelo após cada resposta, economizar VRAM)
     — Injetar `num_thread: 2` em P1 e P2 (reduzir consumo de energia do CPU)
     — Threshold de P2 mais conservador: bloquear se CPU > 60% (vs 85% em AC)
  4. Adicionar ao `StatusResponse`: `on_battery: bool`
  5. Atualizar `LogosStatus` type em `HUB/src/types.ts`
  6. `LogosPanel.tsx`: exibir badge "⚡ Bateria" quando `on_battery=true`; colorir P3 de vermelho
     para indicar bloqueio

### LOGOS — scheduling de processos em nível de SO

- [x] Lançar o processo Ollama com prioridade reduzida via `nice` quando gerenciado pelo LOGOS:
  **Motivo:** `nice` é a ferramenta padrão UNIX para indicar ao scheduler do kernel que um processo
  deve ceder CPU para outros quando há contention. Definir nice=10–15 para o Ollama em P3 garante
  que o sistema continue responsivo sem necessitar de polling ativo do LOGOS. Custo de implementação:
  uma linha. Custo de não implementar: CPU a 90% quando P3 está ativo.
  **Implementação (`HUB/src-tauri/src/logos.rs`):**
  — Linux: `Command::new("nice").args(["-n", "10", "ollama", "serve"])` ao lançar Ollama em P3
    OU usar `renice(2)` via syscall após obter o PID do processo Ollama
  — Windows: `SetPriorityClass(handle, BELOW_NORMAL_PRIORITY_CLASS)` via `windows-sys` crate
  — Ao receber P1: temporariamente aumentar prioridade do Ollama (`renice -5 $pid`) para minimizar
    latência, restaurar após P1 concluir

- [x] Lançar processos de background do Python (KOSMOS idle analysis, Mnemosyne idle indexer)
  com prioridade de SO reduzida:
  **Motivo:** os workers de background Python (`_IndexJobWorker`, `KosmosAnalyzer`) rodam em
  threads PySide6 com `IdlePriority`, mas isso só afeta o scheduler do Python (GIL), não o
  scheduler do OS. O OS ainda aloca CPU para o processo Python normalmente. `os.nice()` afeta
  o processo inteiro — deve ser chamado no worker no início de sua execução.
  **Implementação:**
  — `Mnemosyne/core/idle_indexer.py`, no início de `_IndexJobWorker.run()`:
    ```python
    import os, sys
    if sys.platform != "win32":
        os.nice(15)          # Linux/Mac: nice máximo para background
    else:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(
            ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)  # BELOW_NORMAL
    ```
  — `KOSMOS/app/core/background_worker.py` (ou equivalente): mesma lógica no início do worker
  — Resultado: durante idle indexing, o sistema mantém 30–40% de CPU disponível para apps ativos

- [x] Configurar cgroup para o Ollama no systemd (Linux — máquina principal e laptop):
  **Motivo:** nice afeta prioridade relativa mas não limita CPU absoluto. cgroups v2 (padrão
  no CachyOS/Arch) permitem limitar CPU por quota absoluta (ex: no máximo 50% de um core) e
  memória máxima. O systemd usa cgroups nativamente via diretivas de unit file.
  **Implementação (manual, documentar no README do HUB):**
  Criar/editar `~/.config/systemd/user/ollama.service.d/logos-limits.conf`:
  ```ini
  [Service]
  CPUWeight=20        # vs 100 padrão — Ollama cede CPU quando há contention
  CPUQuota=80%        # nunca exceder 80% de 1 core em P3 (ajustar se multi-GPU)
  MemoryMax=10G       # não exceder 10 GB de RAM (proteger os 6 GB restantes do sistema)
  IOSchedulingClass=idle  # I/O em idle — não compete com apps ativos em disco
  ```
  Reload: `systemctl --user daemon-reload && systemctl --user restart ollama`
  Este arquivo é gerenciado pelo HUB: ao detectar perfil `high` ou `medium`, escreve os valores
  corretos e recarrega o serviço.

### Feed de atividade unificado

- [ ] Painel mostrando eventos recentes de todos os apps em ordem cronológica:
  — KOSMOS: artigos baixados, análises concluídas, erros de scraping
  — Hermes: transcrições iniciadas / concluídas
  — Mnemosyne: indexações e re-indexações
  — AETHER: projetos/capítulos salvos
  — AKASHA: arquivamentos, crawls concluídos
- [ ] Filtro por app e por tipo de evento (sucesso / erro / info)
- [ ] Implementação: cada app escreve eventos num arquivo de log estruturado (JSON Lines)
  em `{sync_root}/{app}/activity.jsonl`; HUB lê e exibe em polling leve

### Busca global via AKASHA (Mapa de Contexto)

- [ ] Campo de busca no HUB que consulta o AKASHA e retorna resultados cruzados de todas as fontes:
  — Mnemosyne (RAG semântico), KOSMOS (artigos), Hermes (transcrições), AETHER (notas/capítulos)
- [ ] Exibir resultados agrupados por fonte com snippet de contexto
- [ ] Depende de: AKASHA implementar API de "Mapa de Contexto" (ver PENDÊNCIAS — ECOSSISTEMA)

### Quick capture / inbox

- [ ] Campo de captura rápida acessível sem abrir nenhum app específico
  — roteamento automático por tipo de conteúdo:
    - URL de vídeo (youtube.com, etc.) → dispara Hermes
    - URL genérica → envia para AKASHA arquivar
    - Texto livre → cria nota rápida no OGMA
  — feedback visual confirmando para onde o conteúdo foi roteado

### Estatísticas cross-app ("diário de atividade polimática")

- [ ] Painel de métricas combinadas por período (dia / semana / mês):
  — artigos lidos (KOSMOS)
  — palavras escritas / sessões de escrita (AETHER)
  — documentos indexados (Mnemosyne)
  — vídeos transcritos e duração total (Hermes)
  — páginas arquivadas (AKASHA)
- [ ] Visualização estilo "mapa de calor" (tipo GitHub contributions) mostrando dias de atividade
- [ ] Implementação: agregar dados dos logs de atividade de cada app (activity.jsonl)

---

> HUB é Tauri. A interface já é web-based mas deve funcionar em janelas menores.

- [ ] **Auditar grid de cards de apps**
  — De 3 colunas → 2 → 1 conforme janela estreita (CSS grid `auto-fill`)
- [ ] **LogosView e painéis de status**
  — Verificar que scrollam corretamente quando a janela é reduzida
- [ ] **Testar em janela 800×600 mínima**

---


### LOGOS — Proxy Inteligente de LLM

### LOGOS: proxy central de LLM (integrado ao HUB)
- [x] Decidir arquitetura final: LOGOS como parte do backend Rust do HUB vs. serviço separado
  — recomendado: integrado ao HUB (evita ter mais um processo rodando; HUB já é o maestro)
- [x] Definir protocolo: `POST /logos/chat { app, priority, model, messages, ... }` → 200 ou 429
- [x] Implementar fila de prioridades (`HUB/src-tauri/src/logos.rs`):
  - P1: aguarda indefinidamente (sem timeout)
  - P2: timeout 60s
  - P3: timeout 30s + 429 imediato se VRAM > 85%
- [x] Hardware Guard: VRAM via Ollama `/api/ps` (sum size_vram) + sysfs Linux para total
  — Linux/CachyOS: `/sys/class/drm/card{n}/device/mem_info_vram_total` (AMD sysfs)
  — Windows: total_vram desconhecido (sem GPU discreta no i5-3470); pct retorna None
- [x] Cancelamento gracioso: `POST /logos/silence` → keep_alive: 0 em todos os modelos carregados
- [x] Failsafe implementado em `ecosystem_client.py`:
  — LOGOS online: request roteado com prioridade
  — LOGOS offline: fallback direto ao Ollama (modo emergência silencioso)
  — LOGOS retorna 429: RuntimeError propagado ao app chamador
- [x] Tauri IPC commands: `logos_get_status`, `logos_silence` (para o frontend HUB)

Arquivos:
  — `HUB/src-tauri/src/logos.rs` — servidor Axum porta 7072
  — `HUB/src-tauri/src/commands/logos.rs` — IPC Tauri
  — `ecosystem_client.py` — `request_llm()`, `logos_status()`, `logos_silence()`

### Gerenciamento de LLM simultâneo (Mnemosyne + KOSMOS)
- [x] Investigar comportamento atual quando os dois apps fazem chamadas simultâneas ao Ollama
  — risco: VRAM saturada → travamento no Windows 10 (8 GB RAM, GPU integrada)

  **Achados:**
  — KOSMOS: `ai_bridge.py` usa `requests.Session` direto ao `/api/generate`, timeout=120s, sem coordenação
  — Mnemosyne: `langchain_ollama` em QThread via `workers.py`, sem coordenação
  — Nenhum dos dois usa `ecosystem_client.request_llm()` → não passam pelo LOGOS
  — No Windows 10 (8 GB RAM, GPU integrada): chamadas simultâneas podem saturar a RAM com dois modelos carregados
  — No CachyOS (RX 6600, 8 GB VRAM): dois modelos 7B simultâneos arriscam overflow de VRAM

  **Solução imediata sem código** — configurar variáveis de ambiente do Ollama:
  ```
  OLLAMA_NUM_PARALLEL=1        # serializa requisições dentro do Ollama
  OLLAMA_MAX_LOADED_MODELS=1   # descarrega modelo anterior antes de carregar novo
  ```
  No Windows: `setx OLLAMA_NUM_PARALLEL 1` + `setx OLLAMA_MAX_LOADED_MODELS 1` (requer reiniciar Ollama)
  No CachyOS: adicionar ao `.env` do serviço systemd do Ollama ou ao `~/.config/fish/config.fish`

- [x] Solução de longo prazo: migrar `KOSMOS/app/core/ai_bridge.py` e `Mnemosyne/core/workers.py`
  para usar `ecosystem_client.request_llm()` → passam pelo LOGOS com controle de prioridade e VRAM

  **Migrado (chamadas síncronas P3):**
  — KOSMOS `ai_bridge.py`: `generate()` usa `request_llm(priority=3)` via LOGOS; `generate_stream()` e `embed()` permanecem diretos (streaming/embeddings não passam pelo LOGOS)
  — Mnemosyne `memory.py`: `compact_session_memory()` usa `request_llm(priority=3)`
  — Mnemosyne `summarizer.py`: fase Map de `iter_summary()` + `prepare_summary()` + `summarize_all()` usam `request_llm(priority=3)`; fase Reduce (streaming) permanece via LangChain `OllamaLLM.stream()`

  **Não migrado (requer suporte a streaming no LOGOS):**
  — Mnemosyne `AskWorker`: `ChatOllama.stream()` — RAG interativo
  — Mnemosyne `SummarizeWorker`/`FaqWorker`/`StudioWorker`/`GuideWorker`: usam `iter_*()` com streaming LangChain

### LOGOS: otimizações de configuração do Ollama

Achados de pesquisa `KOSMOS/pesquisa.txt` (2026-04-25) — LOGOS é responsável por configurar e expor essas variáveis de ambiente ao Ollama:

- [x] Configurar `OLLAMA_KEEP_ALIVE=-1` via injeção automática no proxy
  — LOGOS injeta `keep_alive: -1` em todo request que não o definiu explicitamente
  — elimina cold start de 3–10s; modelo permanece carregado na VRAM entre análises
- [x] Configurar `OLLAMA_KV_CACHE_TYPE=q8_0` no systemd
  — reduz VRAM do KV cache em ~50%; abre espaço para `num_ctx` maior ou NUM_PARALLEL=2
- [x] Configurar concorrência dinâmica baseada no tamanho do modelo
  — LOGOS usa `Semaphore::new(2)` com `acquire_many_owned(permits)`:
    modelos ≤3B adquirem 1 permit → até 2 rodam em paralelo
    modelos >3B adquirem 2 permits → exclusividade total
  — `LogosPanel` exibe badge "leve" / "pesado" do modelo em execução
- [x] Configurar `OLLAMA_NUM_PARALLEL=2` no systemd
  — permite ao Ollama aceitar 2 requests simultâneos; necessário para modelos leves rodarem em paralelo via semáforo do LOGOS

### LOGOS: seleção e especialização de modelos por app

- [x] KOSMOS (análise em background): usar Gemma 2 2B (`gemma2:2b`)
  — default `ai_gen_model` em KOSMOS/app/utils/config.py
- [x] Mnemosyne (RAG): usar Qwen 2.5 7B (`qwen2.5:7b`)
  — default `llm_model` em Mnemosyne/core/config.py
- [x] KOSMOS: `num_ctx=4096` explícito e constante em `_AnalyzeWorker` e `_start_analyze`
  — Mnemosyne AskWorker: `num_ctx=8192`
- [x] KOSMOS: JSON Schema completo no `_AnalyzeWorker` (constrained decoding via XGrammar)
  — `_JSON_SCHEMA` como class constant; `json_schema=` em `ai_bridge.generate()`
- [x] KOSMOS: pré-análise em background — `BackgroundAnalyzer` (QThread + PriorityQueue)
  — HIGH (P0): artigo aberto pelo usuário → single call imediato
  — LOW (P10): novos artigos do feed → enfileirados no startup e em `_on_feed_updated`
  — cache check: artigos com `ai_sentiment IS NOT NULL` são pulados
- [x] KOSMOS: batching de até 5 artigos por call LLM no background
  — schema dinâmico por lote; fallback individual se batch falhar
  — `num_ctx=8192` para batch; análise interativa permanece `num_ctx=4096`

### LOGOS: perfis de hardware com detecção automática por fingerprint de GPU

Objetivo: ao iniciar, o LOGOS identifica em qual máquina está rodando via fingerprint de GPU
e seleciona automaticamente o perfil de modelos adequado — sem configuração manual por máquina.

**Perfis definidos:**

| Máquina | GPU detectada | LLM (Mnemosyne) | LLM (KOSMOS) | Embedding |
|---|---|---|---|---|
| PC principal | RX 6600 (AMD sysfs / `rocm-smi`) | qwen2.5:7b | gemma2:2b | bge-m3 |
| Laptop Ideapad 330 | MX150 via `nvidia-smi` | gemma2:2b | smollm2:1.7b | nomic-embed-text |
| PC de trabalho (Windows) | nenhuma GPU discreta | (CPU only) modelos leves | smollm2:1.7b | all-minilm |

**Lógica de detecção (em ordem):**
1. Tentar `nvidia-smi --query-gpu=name --format=csv,noheader` → se retornar "MX150" → perfil laptop
2. Tentar ler `/sys/class/drm/card*/device/mem_info_vram_total` (AMD sysfs) → se encontrar RX 6600 → perfil principal
3. Fallback → perfil Windows/CPU-only

**Implementação sugerida:**
- `HUB/src-tauri/src/logos.rs`: função `detect_hardware_profile() -> HardwareProfile` rodando no startup
- `HardwareProfile` enum: `MainPc | Laptop | WorkPc`
- Perfil exposto via `GET /logos/profile` → apps lêem e ajustam modelos dinamicamente
- `ecosystem_client.py`: `get_active_profile()` → retorna o perfil atual do LOGOS

- [x] Implementar `detect_hardware_profile()` em `logos.rs` com as 3 etapas de detecção
- [x] Definir `HardwareProfile` enum + struct `ModelProfile { llm_mnemosyne, llm_kosmos, embed }`
- [x] Expor `GET /logos/hardware` no servidor Axum
- [x] `ecosystem_client.py`: `get_active_profile()` + adaptar `request_llm()` para usar modelo do perfil ativo
- [x] KOSMOS e Mnemosyne: ler perfil do LOGOS no startup e usar modelos recomendados mas inclua a possibilidade de haver override manual (tornando o recomendado pelo LOGOS sempre como padrão)
- [x] Criar um botão para "usar recomendado" ao lado da configuração de LLM no KOSMOS e Mnemosyne
- [x] HUB LogosPanel: exibir perfil ativo ("PC Principal · RX 6600", "Laptop · MX150 2 GB", etc.)

### LOGOS: proxy transparente para todas as chamadas ao Ollama (correção arquitetural)

> Contexto: a implementação atual do LOGOS controla apenas chamadas que passam explicitamente
> por `POST /logos/chat`. Embeddings (LangChain/Chroma), streaming (ChatOllama) e qualquer
> outra chamada direta ao Ollama (porta 11434) são invisíveis ao LOGOS — ele não pode gerenciar
> o que não vê. O design original previa um proxy transparente: apps apontam para 7072 (LOGOS)
> em vez de 11434 (Ollama). Enquanto essa correção não for feita, o LOGOS não cumpre seu papel
> central de gerenciador de hardware e prioridades para todo o ecossistema.

- [x] `HUB/src-tauri/src/logos.rs` — implementar rotas de proxy para os endpoints nativos do Ollama:
  — `POST /api/chat` e `POST /api/generate` → proxy com fila P1/P2/P3 (mesma lógica do `/logos/chat`)
  — `POST /api/embeddings` e `POST /api/embed` → proxy com fila (P3 por padrão para embeddings)
  — `GET /api/tags`, `GET /api/ps`, `DELETE /api/delete` → proxy direto sem fila (metadados)
  — identificação do app por header `X-App: <nome>` (ex: `mnemosyne`, `kosmos`)
  — keep_alive injetado automaticamente em todas as chamadas de chat/generate que passam pelo proxy
  — Hardware Guard (VRAM, CPU, RAM) aplicado a todos os requests, não só aos via `/logos/chat`
- [x] `ecosystem_client.py` — `LOGOS_OLLAMA_BASE` aponta para 7072 (LOGOS); `OLLAMA_DIRECT` 11434;
  `get_ollama_url()` retorna 7072 se LOGOS acessível, senão 11434
- [x] `Mnemosyne/core/indexer.py` — `OllamaEmbeddings(base_url="http://localhost:7072")`
- [x] `KOSMOS/app/core/ai_bridge.py` — URL base para 7072; header `X-App: kosmos` em embed e generate_stream
- [x] Auditar todos os apps em busca de `localhost:11434` hardcoded e substituir pela URL do LOGOS
- [ ] Testar integração: chat no Mnemosyne (P1) enquanto KOSMOS analisa em background (P3)
  → KOSMOS deve pausar na fila do LOGOS até o chat terminar

### AKASHA como broker unificado de informação
- [ ] Planejar API de "Mapa de Contexto" no AKASHA:
  — dado um termo, retornar resultados cruzados: Mnemosyne (RAG) + KOSMOS (artigos) + Hermes (transcrições) + AETHER (notas)
- [ ] HUB consumir essa API num botão de busca global cross-app

### Migração Rust/PyO3 para indexação (longo prazo)
- [x] Avaliar substituição do indexador Python do AKASHA por módulo Rust via PyO3

  **Conclusão: não justificada no volume atual — adiar indefinidamente.**

  Análise (2026-04-24):
  - Volume estimado atual: 5k–20k documentos; SQLite FTS5 escala até ~10M sem degradação
  - Startup do indexador é incremental (só mtime diffs) — já roda em < 5s
  - Gargalo real do ecossistema: I/O de rede (crawl BFS) e inferência LLM (Mnemosyne), não indexação local
  - Custo: PyO3 introduz build Rust obrigatório no CI + complexidade de cross-compile (Windows 10 + CachyOS)
  - tantivy compila sem AVX2 (i5-3470 OK), mas o ganho é imperceptível na escala atual

  Gatilhos para reavaliar:
  — volume indexado > 500k documentos **ou** startup time > 30s na máquina alvo
  — buscas FTS retornando em > 2s de forma consistente

---

## AETHER — Forja de Mundos

### Padrões de Desenvolvimento

- **Tratamento de erro com tipagem é prioridade absoluta.**
  - Rust: toda função que pode falhar retorna `Result<T, AppError>`. Nunca usar `.unwrap()` ou `.expect()` em código de produção.
  - TypeScript: `strict: true` sempre. Erros de comandos Tauri tipados com union types (`type Result<T> = { ok: true; data: T } | { ok: false; error: AppError }`).
  - Erros devem ser tratados no ponto onde ocorrem — sem silenciar, sem propagar cegamente.

- **Commit após CADA item individual do todo — não após fases ou grupos.**
  - Mensagem de commit referencia o item exato: `feat(fase-0): 0.6 CosmosLayer component`
  - Atualizar o status do item no todo ([x]) ANTES de fazer o commit.

- **Privacidade é prioridade absoluta.**
  - O AETHER não coleta, transmite nem registra nenhum dado do usuário.
  - Zero telemetria, zero analytics, zero conexões externas não solicitadas.
  - Gerenciamento de arquivos e configurações no estilo Obsidian:
    - Tudo vive na pasta raiz escolhida pelo usuário (o "vault")
    - Configurações ficam em `{pasta-raiz}/.aether/` — nunca em `~/.aether/` global
    - O usuário tem controle total sobre onde seus dados ficam
    - Cada projeto é uma pasta auto-contida e portátil

- **Manter `dev_files/dev_bible.txt` atualizado.**
  - Ao concluir qualquer item que introduza novos arquivos, módulos, commands ou padrões, atualizar o dev_bible.
  - O dev_bible descreve o estado ATUAL do projeto, não o planejado.

- **Sempre atualizar este arquivo ANTES de começar algo que não está listado aqui.**

- **Sempre atualizar o status do item ([ ] → [x]) ao concluí-lo.**

---

### Stack

- Backend: Rust (Tauri)
- Frontend: TypeScript + React + Vite
- Armazenamento: arquivos locais (JSON + Markdown/texto plano)
- Build: Tauri CLI (Windows 10 + CachyOS/Linux)

---

### IDENTIDADE VISUAL

**Nome:** AETHER
**Subtítulo:** FORJA DE MUNDOS
**Ecossistema:** OGMA · KOSMOS · MNEMOSYNE · AETHER

O AETHER segue o design system do ecossistema (definido no OGMA Design Bible):
mesma paleta sépia, mesma tipografia, mesmas regras de sombra, animações e cosmos.

**Diferencial visual do AETHER dentro do ecossistema:**
- Animação `pageFloat` — folhas de papel caem com rotação ao abrir/criar/deletar capítulos
- Efeito typewriter — texto no splash e em loading states digita caractere por caractere
- Cursor de editor como `_` piscante (sublinhado), não `|`
- CosmosLayer com labels mitológicos nas constelações (Órion, Cassiopeia, Perseu...)
- Nebulosas com pulso lento animado (8s) nos headers de projeto — o "éter" do app

---

### Design Bible v2.0 — Audit (2026-04-11)

- [x] tokens.css: modo noturno migrado para paleta "Atlas Astronômico à Meia-Noite"
- [x] tokens.css: `--sidebar-w` corrigido para 224px (era 260px)
- [x] typography.css: hierarquia tipográfica alinhada ao bible (t-body 13px, t-btn 11px, t-label 10px, t-section 9px, t-badge 10px, t-meta 9px)
- [x] components.css: `.btn` corrigido para 11px / 5px 14px
- [x] Splash.tsx: background hardcoded `rgba(26,22,16,0.45)` → `var(--paper)`

---

### FASE 0 — Design System

> Entregável: toda a fundação visual implementada. Nenhum componente de UI é construído sem isso estar pronto.

- [x] 0.1 Variáveis CSS globais (tokens do ecossistema)
  - Paleta completa: `--paper`, `--paper-dark`, `--paper-darker`, `--paper-darkest`
  - Tintas: `--ink`, `--ink-light`, `--ink-faint`, `--ink-ghost`
  - Acento: `--accent` (#b8860b dia / #D4A820 noite), `--cursor-color`
  - Funcionais: `--ribbon`, `--ribbon-light`, `--accent-green`, `--stamp`
  - Linhas: `--rule`, `--margin-line`, `--shadow`
  - Métricas: `--sidebar-w: 260px` (binder mais largo que OGMA), `--topbar-h: 44px`, `--radius: 2px`
  - Transições: `--transition: 140ms ease`

- [x] 0.2 Tipografia — carregar e configurar as três famílias
  - `--font-display`: IM Fell English (Google Fonts) — títulos, editor, itálico como regra
  - `--font-mono`: Special Elite (Google Fonts) — UI geral, botões, labels
  - `--font-code`: Courier Prime (Google Fonts) — blocos de código no editor
  - Hierarquia tipográfica completa (tamanhos, letter-spacing, pesos)
  - Regra de itálico: IM Fell English é SEMPRE itálico em títulos e conteúdo

- [x] 0.3 Animações base (herdadas do ecossistema)
  - `paperFall` — translateY(-14px) + rotate(-0.4deg) → 0, 0.22s ease-out
  - `fadeIn` — opacity 0→1, 0.15–0.25s ease
  - `slideIn` — translateX(-16px) + opacity, para sidebar/drawers
  - `blink` — opacity 1→0→1, 1.2s (loading dots) / 0.6s (editor cursor)
  - `toastIn` — translateY(6px) + opacity, 180ms ease-out

- [x] 0.4 Animações exclusivas do AETHER
  - `pageFloat` — folha retangular cai com rotação suave (±3deg) e translação diagonal
    - Variante entrada: cai de cima com rotação leve, pousa
    - Variante saída (deletar): voa para canto superior direito e desaparece
  - `typewriterReveal` — texto revela caractere por caractere com delay mecânico (30ms/char)
    - Usado no splash e em loading states
  - `etherPulse` — opacity 0.4→0.65→0.4, 8s ease-in-out infinite (nebulosas dos headers)

- [x] 0.5 Textura de papel
  - `body::after` com SVG `feTurbulence` (baseFrequency: 0.65, numOctaves: 4)
  - Opacity: 30%, pointer-events: none, z-index: 0
  - Invisível no modo noturno (intencional)

- [x] 0.6 Componente `<CosmosLayer>`
  - SVG procedural determinístico (seed baseado no ID do projeto)
  - Elementos: nebulosas, estrelas (10 pontas), constelações, cometa, lua crescente
  - **Diferencial AETHER:** labels mitológicos nas constelações (Special Elite, 7px, opacity: 0.35)
  - **Diferencial AETHER:** nebulosas com `etherPulse` animado
  - Densidades: `low` (headers de capítulo), `medium` (headers de livro), `high` (splash, tela inicial)
  - Props: `seed`, `density`, `animated` (boolean — desativa pulso se false)

- [x] 0.7 Linha vermelha de margem
  - `sidebar::before` — 1px vertical em left: 48px (ajustado para binder)
  - Cor: `--margin-line`
  - Replicada no splash em mesma posição

- [x] 0.8 Sistema de sombra flat (sem blur)
  - Botão: `2px 2px 0 var(--rule)`
  - Botão primary: `2px 2px 0 var(--stamp)`
  - Card: `3px 3px 0 var(--paper-darker)`
  - Modal: `6px 6px 0 var(--ink-ghost)`
  - Menu popup: `3px 3px 0 var(--rule)`
  - `:active` em botões e cards: sombra some + `translate(1px, 1px)`

- [x] 0.9 Scrollbar vintage
  - Width: 6px, border-radius: 2px
  - Track: `--paper-dark`, thumb: `--rule`, hover: `--stamp`

- [x] 0.10 Cursor dourado e cursor de editor
  - `caret-color: var(--accent)` em todos os inputs e textareas
  - No editor de capítulo: cursor customizado como `_` piscante (via CSS/JS)

- [x] 0.11 Seleção de texto âmbar
  - `::selection { background: rgba(184,134,11,0.25); }`
  - Editor modo escuro: `rgba(212,168,32,0.2)`

- [x] 0.12 Sistema de temas (dia / noite)
  - Toggle via classe `dark` no `<html>`
  - Persiste em localStorage: `aether_theme`
  - Sem flash de tema errado no carregamento (aplicar antes do render)

- [x] 0.13 Sistema de toasts / notificações
  - Tipos: `success`, `error`, `warning`, `info`
  - Posição: fixed, bottom: 24px, right: 24px
  - Auto-dismiss: error=7s, success=3s, warning=5s, info=4s
  - Cores dentro da paleta sépia (sem branco puro, sem preto puro)
  - Animação: `toastIn`

- [x] 0.14 Splash screen
  - Overlay sépia (rgba(26,22,16,0.85)) com backdrop blur 2px
  - Card 520×340px, border-radius: 2px, sombra flat 8px
  - `<CosmosLayer density="high" animated={true}>`
  - Linha de margem vermelha (left: 48px)
  - "AETHER" em IM Fell English 68px itálico
  - "FORJA DE MUNDOS" em Special Elite 9px uppercase letter-spacing: 0.22em
  - Texto de status com `typewriterReveal`: "Iniciando AETHER..." → "Abrindo projetos..." → "Pronto."
  - Dots de loading: "· · ·" com `blink` 1.2s
  - Versão no canto inferior direito (9px)
  - Fade out após "Pronto." com delay 400ms

- [x] 0.15 Componentes base de UI
  - Botões: `.btn`, `.btn-primary`, `.btn-accent`, `.btn-danger`, `.btn-ghost`, `.btn-sm`, `.btn-icon`
  - Inputs e labels (IM Fell no corpo, Special Elite nos labels)
  - Cards com `paperFall` e sombra flat
  - Modais com overlay sépia e `paperFall`
  - Badges / tags (border-radius: 20px para pills)

---

### FASE 1 — Fundação (projeto abrível e editável)

> Entregável: abrir o AETHER, criar um projeto, criar capítulos e escrever texto. Nada mais — mas isso funciona.

- [x] 1.1 Scaffold do projeto Tauri + React + TypeScript
  - Vite como bundler, `strict: true` no tsconfig
  - Estrutura de pastas: `src-tauri/` (Rust), `src/` (React)

- [x] 1.2 Definir e implementar estrutura de dados em disco
  - Modelo Obsidian: usuário escolhe uma pasta raiz ("vault") na primeira abertura
  - Dois níveis de armazenamento:
    1. **AppData do sistema** (`~/.local/share/aether/` no Linux, `%AppData%\aether\` no Windows)
       - `app.json` — caminho do último vault aberto (apenas isso)
       - Gerenciado pelo Tauri via `tauri::api::path::app_data_dir`
    2. **Dentro do vault** (portátil, controlado pelo usuário)
       - `{vault}/.aether/config.json` — tema, fonte, estado da UI, etc.
       - `{vault}/.aether/` — outros dados internos do app (snapshots, cache, etc.)
       - `{vault}/{projeto}/project.json` — metadados do projeto
       - `{vault}/{projeto}/{livro}/book.json` — metadados do livro
       - `{vault}/{projeto}/{livro}/{capitulo}.md` — conteúdo dos capítulos
  - Tipos Rust: `AppState`, `VaultConfig`, `Project`, `Book`, `Chapter` com `serde` + `serde_json`
  - `AppError` enum cobrindo todos os erros de I/O

- [x] 1.3 Comandos Tauri: gerenciamento de projetos
  - `list_projects() -> Result<Vec<ProjectMeta>, AppError>`
  - `create_project(name) -> Result<ProjectMeta, AppError>`
  - `open_project(id) -> Result<Project, AppError>`
  - `delete_project(id) -> Result<(), AppError>`

- [x] 1.4 Comandos Tauri: livros e capítulos
  - `create_book(project_id, name) -> Result<BookMeta, AppError>`
  - `list_books(project_id) -> Result<Vec<BookMeta>, AppError>`
  - `create_chapter(project_id, book_id, title) -> Result<ChapterMeta, AppError>`
  - `list_chapters(project_id, book_id) -> Result<Vec<ChapterMeta>, AppError>`
  - `read_chapter(project_id, book_id, chapter_id) -> Result<String, AppError>`
  - `save_chapter(project_id, book_id, chapter_id, content) -> Result<(), AppError>`
  - `delete_chapter(...) -> Result<(), AppError>`
  - `reorder_chapters(...) -> Result<(), AppError>`

- [x] 1.5 Tipos TypeScript espelhando os tipos Rust
  - `AppError`, `ProjectMeta`, `BookMeta`, `ChapterMeta` como tipos estritos
  - Wrapper tipado para todos os `invoke()` do Tauri

- [x] 1.6 Tela inicial — lista de projetos
  - Criar novo projeto
  - Abrir projeto existente
  - Remover projeto

- [x] 1.7 Layout principal do projeto
  - Painel binder lateral: árvore Livros > Capítulos
  - Área central: editor de texto
  - Criar/renomear/deletar livros e capítulos pelo binder
  - Reordenar capítulos via drag & drop

- [x] 1.8 Editor de texto WYSIWYG com TipTap
  - Biblioteca: TipTap (ProseMirror) — renderização em tempo real
  - Sem "modo leitura": o texto é SEMPRE renderizado, nunca mostra símbolos Markdown
  - Digitar `**texto**` → imediatamente vira negrito; `_texto_` → itálico; etc.
  - Parágrafos indentados (text-indent na primeira linha, estilo livro impresso)
  - Tipografia: IM Fell English itálico, 16px, line-height 1.75, coluna centralizada
  - Cursor estilo máquina de escrever: `_` piscante via CSS (substituir cursor padrão `|`)
  - Auto-save com debounce 500ms após parar de digitar
  - Indicador de status "Salvando..." / "Salvo" no rodapé do editor
  - Exporta/importa como Markdown puro (compatível com os .md do vault)

---

### FASE 1.5 — Itens pendentes identificados em uso

> Itens que surgiram durante os testes da Fase 1. Devem ser feitos antes da Fase 2.

- [x] 1.9 Tipos de projeto: livro único vs série
  - Ao criar projeto, perguntar: "Livro único" ou "Série"
  - **Livro único**: nome do projeto = nome do livro; livro criado automaticamente; binder oculta a camada "livro" e mostra só capítulos
  - **Série**: nome da série separado do nome dos livros; binder mostra árvore Série > Livros > Capítulos normalmente
  - Armazenar `project_type: "single" | "series"` em project.json
  - Ajustar Binder para renderizar diferente conforme o tipo

- [x] 1.10 Modal de criação de projeto com metadados
  - Substituir o modal simples atual por um wizard/form mais completo
  - Campos: tipo (único/série), título, subtítulo opcional, descrição/sinopse
  - Metadados de livro: gênero, público-alvo, idioma, tags livres
  - Metadados de worldbuilding: sistema de magia (sim/não), nível tecnológico, inspirações
  - Todos os campos opcionais exceto título e tipo
  - Salvar em project.json

- [x] 1.11 Dashboard do projeto
  - Tela inicial ao abrir um projeto (antes de selecionar capítulo)
  - CosmosLayer de fundo com seed do projeto
  - Nome, subtítulo, descrição do projeto
  - Estatísticas: total de palavras, total de capítulos, data de criação
  - Widgets expansíveis no futuro (metas, personagens, etc.)

- [x] 1.12 Sistema de logs em arquivo
  - Logs salvos dentro do vault em `{vault}/.aether/logs/aether-YYYY-MM-DD.log`
  - Rotação diária; manter últimos 7 dias
  - Nível INFO em produção, DEBUG em dev
  - Registrar: abertura/fechamento do vault, erros, saves, operações de CRUD
  - Implementar em Rust via tauri-plugin-log com appender de arquivo

---

### FASE 2 — Experiência de escrita

> Entregável: escrever com conforto. Foco, tipografia, estatísticas básicas.

- [x] 2.1 Temas: claro, escuro, sépia
- [x] 2.2 Tipografia customizável (fonte, tamanho, espaçamento, largura da coluna de texto)
- [x] 2.3 Modo foco / distraction-free (esconde binder e UI, só o texto)
- [x] 2.4 Modo typewriter (cursor sempre centralizado verticalmente)
- [x] 2.5 Tela cheia (F11)
- [x] 2.6 Contagem de palavras e caracteres em tempo real
- [x] 2.7 Status por capítulo (Rascunho / Revisão / Final)
- [x] 2.8 Sinopse por capítulo (campo no binder ou painel lateral)
- [x] 2.9 Localizar e substituir no capítulo atual

---

### FASE 3 — Organização avançada

> Entregável: visões alternativas da estrutura do projeto.

- [x] 3.1 Vista corkboard (cartões de capítulo com título + sinopse)
- [x] 3.2 Vista outline (lista com status, sinopse e contagem de palavras)
- [x] 3.3 Lixeira — capítulos deletados ficam recuperáveis
- [x] 3.4 Scratchpad por capítulo (bloco de notas lateral)
- [x] 3.5 Modo split: editor + scratchpad/notas lado a lado

---

### FASE 4 — Personagens & Worldbuilding

> Entregável: base de lore do projeto, separada da escrita mas sempre acessível.

- [x] 4.1 Fichas de personagem com campos customizáveis
- [x] 4.2 Relacionamentos entre personagens (mapa/grafo simples)
- [x] 4.3 Notas de worldbuilding por categoria (locais, facções, etc.)
- [x] 4.4 Linha do tempo de eventos
- [x] 4.5 Anexar imagens a personagens e locais
- [x] 4.6 Tags — cruzar personagens/locais com capítulos

---

### FASE 5 — Metas & Histórico

> Entregável: acompanhar progresso e proteger o trabalho.

- [x] 5.1 Meta de palavras por capítulo e por livro
- [x] 5.2 Meta de sessão de escrita com timer
- [x] 5.3 Streak diário de escrita
- [x] 5.4 Painel de estatísticas (palavras totais, ritmo, sessões)
- [x] 5.5 Snapshots de capítulo (histórico de versões manual + automático)
- [x] 5.6 Comentários/anotações inline no texto

---

### FASE 6 — Exportação

> Entregável: levar o texto para fora do AETHER.

- [ ] 6.1 Export por capítulo individual
- [ ] 6.2 Export por livro (capítulos concatenados)
- [ ] 6.3 Export do projeto completo
- [ ] 6.4 Formatos: Markdown, texto plano, DOCX, PDF
- [ ] 6.5 Formato EPUB
- [ ] 6.6 Configurações de export (incluir/excluir sinopses, metadados, notas)

---

### FASE 7 — Polimento & Extras

> Entregável: produto refinado.

- [x] 7.0 Botão de excluir visível para projetos, livros e capítulos
      — ProjectCard: hover revela botão ×; confirmação 2 passos; sai do modo confirmação
        ao tirar o mouse. Livros e capítulos: × no hover já estava implementado.
        delete_book está implementado em Rust + frontend.
- [ ] 7.1 Atalhos de teclado customizáveis
- [ ] 7.2 Gerador de nomes
- [ ] 7.3 Projetos recentes na tela inicial com preview
- [ ] 7.4 Onboarding (tela de boas-vindas para primeiro uso)
- [ ] 7.5 Configurações globais (tema padrão, pasta de dados, fonte padrão)
- [ ] 7.6 Build de distribuição — Windows installer + pacote Linux (AppImage/deb)

---

### BACKLOG (futuro, fora do escopo atual)

- Sync opcional com cloud (Google Drive, Dropbox, ou próprio)
- Colaboração em tempo real
- Plugin/extensão system
- Integração com ferramentas de revisão gramatical
- Versão mobile (leitura + notas)


---




### Bug: vault_path não atualiza após mudança no HUB
- [x] Investigar por que o AETHER continua salvando no caminho antigo mesmo após `sync_root` ser atualizado no HUB
  — causa: startup lia app.json local e sobrescrevia o ecosystem.json, ignorando o que o HUB gravou
  — fix: `ecosystem.rs` expõe `read_vault_path()`; `lib.rs` compara ecosystem.json vs local e prefere ecosystem.json
- [ ] Adicionar opção de configurar `vault_path` dentro do próprio AETHER (sem depender exclusivamente do HUB)

### Responsividade — AETHER

> AETHER é Tauri (React + CSS). Responsividade significa: a área de edição deve escalar bem
> em janelas menores sem perder usabilidade.

- [ ] **Auditar sidebar de projetos/capítulos**
  — Em janelas estreitas (~800px) a sidebar pode esconder o editor
  — Fix: `min-width` na sidebar, collapsível com toggle button abaixo de 900px
- [ ] **Barra de ferramentas do editor**
  — Botões de formatação podem overflow em janela estreita
  — Fix: ocultar labels de texto, manter apenas ícones abaixo de 900px; wrapping se necessário
- [ ] **Testar em janela 900×600 mínima**

---

### Verificação de formato de saída

- [ ] Verificar se todos os arquivos gerados pelo AETHER (escrita, fichas, worldbuilding) são salvos como `.md`
  **Motivo:** Markdown garante portabilidade e segurança dos dados — os arquivos devem ser legíveis
  sem o AETHER, sincronizáveis via Proton Drive/git, e compatíveis com outros editores (Obsidian, VSCode).
  Confirmar que nenhum dado fica preso em formato binário ou JSON opaco não-editável pelo usuário.

---

### Pesquisas pendentes

- [ ] **Acesso remoto ao AETHER** — pesquisar abordagens para acessar projetos/vault fora da rede local
  (Tailscale, self-hosted sync, CRDT via websocket). Ver também FASE 3 do HUB (linha ~400 deste arquivo).

- [ ] **Escrita colaborativa em tempo real** — pesquisar como múltiplas pessoas podem escrever simultaneamente
  no mesmo documento remotamente (referências: Ellipsus, Google Docs, Notion).
  Tecnologias relevantes: OT (Operational Transformation), CRDT (Yjs/Automerge), WebSocket multiplex.

- [ ] **Versão Android do AETHER** — pesquisar viabilidade de Tauri Android para o AETHER
  (acesso ao vault, editor de markdown, fichas de personagem/worldbuilding no celular).
  Ver replanejamento da Fase 3 do HUB para contexto sobre o que já foi descartado.

---

## AKASHA — Buscador Pessoal


Buscador pessoal local. Agrega resultados da web e do ecossistema numa interface única,
com downloads genéricos e integração com qBittorrent.
Stack: FastAPI + HTMX + Jinja2 + SQLite (aiosqlite) + uv · Porta 7071.

---

### Padrões de Desenvolvimento

- **Tipagem completa:** Pydantic `BaseModel` em todas as rotas; `-> tipo` em todas as funções
- **Erros explícitos:** `HTTPException` com status code em todos os caminhos de erro
- **I/O nunca silencioso** fora do bloco de integração com `ecosystem.json`
- **`uv` obrigatório:** `pyproject.toml`, nunca `requirements.txt`
- **Commits por item:** um commit git a cada item concluído
- **Atualizar este TODO** antes de implementar qualquer feature não listada
- **SQLite versionado:** tabela `settings` com campo `schema_version`; migrations numeradas
- **HTMX:** todo estado mutável via `hx-swap`; todo ação tem feedback visual (spinner ou toast)

---

### Fase 1 — Fundação

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

### Fase 2 — Busca Web

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

### Fase 3 — Busca Local

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

### Fase 4 — Downloads

> Entrega: baixar arquivos genéricos com progresso em tempo real via SSE.

- [x] `services/downloader.py` — download async via `httpx` com streaming; calcula progresso
      por `Content-Length`; salva em diretório configurável
- [x] `routers/downloads.py` — `POST /download` (body: `{url, dest_dir}`): inicia download
      em background task; `GET /downloads/active` fragmento HTMX; `POST /downloads/{id}/cancel`
- [x] `routers/downloads.py` — `GET /downloads/progress/{id}` (SSE): emite fragmento HTML
      de progresso a cada 0.6s até concluir ou falhar
- [x] `routers/downloads.py` — `GET /downloads` — ativos (polling 3s) + histórico paginado
- [x] Migration: tabela `downloads` já existia no schema; helpers adicionados em `database.py`
- [x] `templates/downloads.html` + `_downloads_active.html` — barras de progresso SSE,
      formulário de novo download, histórico paginado, botão cancelar
- [x] Botão "↓ baixar" nos cards de resultado de busca `WEB` (HTMX `hx-post="/download"`)

---

### Fase 5 — Arquivação Web

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

### Fase 6 — Torrents (busca + qBittorrent)

> Entrega: pesquisar torrents via Prowlarr/Jackett e baixar com qBittorrent diretamente do AKASHA.
> Pré-requisito do usuário: qBittorrent rodando com Web UI ativo (porta 8080);
> Prowlarr (9696) ou Jackett (9117) instalado e com indexadores configurados.

#### 6.1 — Configuração

- [ ] Adicionar campos na tabela `settings` (migration nova):
      `qbt_host` (default: localhost), `qbt_port` (default: 8080),
      `prowlarr_host`, `prowlarr_port` (9696), `prowlarr_apikey`,
      `jackett_host`, `jackett_port` (9117), `jackett_apikey`
- [ ] Adicionar estes campos à página `/settings` existente

#### 6.2 — Cliente qBittorrent

- [ ] `services/qbt_client.py` — usa `httpx` direto (sem dep qbittorrent-api):
      - `_get_session()` → faz POST /auth/login e retorna cookie SID
        (se `LocalHostAuth=false`, pular login)
      - `async def list_torrents(filter="all") -> list[TorrentInfo]`
        (GET /api/v2/torrents/info; campos: name, hash, progress, dlspeed,
        upspeed, eta, state, size, downloaded, num_seeds, num_leechs)
      - `async def add_magnet(magnet: str, save_path: str = "") -> None`
        (POST /api/v2/torrents/add com urls=magnet)
      - `async def add_torrent_file(data: bytes, save_path: str = "") -> None`
      - `async def pause_torrent(info_hash: str) -> None`
      - `async def resume_torrent(info_hash: str) -> None`
      - `async def delete_torrent(info_hash: str, delete_files: bool = False) -> None`
      - Raises `QbtOfflineError(Exception)` se inacessível

#### 6.3 — Busca de Torrents (Prowlarr + Jackett)

- [ ] `services/torrent_search.py`:
      - `async def search_prowlarr(query, apikey, host, port, categories="") -> list[TorrentResult]`
        (GET /api/v1/search, header X-Api-Key, resposta JSON;
        campos: title, seeders, leechers, size, magnetUrl, downloadUrl, indexer, publishDate)
      - `async def search_jackett(query, apikey, host, port, categories="") -> list[TorrentResult]`
        (GET /api/v2.0/indexers/all/results/torznab/api, resposta XML Torznab;
        parse com xml.etree.ElementTree + namespace torznab;
        extrair: title, link/magnet, size, seeders via torznab:attr)
      - `async def search(query, settings) -> list[TorrentResult]`
        (tenta Prowlarr primeiro; fallback para Jackett; raises TorrentSearchOfflineError se ambos falham)
      - Dataclass `TorrentResult`: title, seeders, leechers, size_bytes, size_fmt,
        magnet_url, torrent_url, indexer, pub_date

#### 6.4 — Router

- [ ] `routers/torrents.py`:
      - `GET /torrents` → página principal (formulário de busca + ativos + histórico)
      - `GET /torrents/search?q=&cat=` → HTMX fragment com resultados (hx-get polling)
      - `GET /torrents/active` → HTMX fragment: lista de torrents ativos no qBittorrent
        com polling a cada 5s
      - `POST /torrents/add` (form: magnet= ou file=) → adiciona ao qBittorrent
      - `POST /torrents/{hash}/pause`, `/resume`, `/delete`
      - Todos retornam banner gracioso se `QbtOfflineError` ou `TorrentSearchOfflineError`

#### 6.5 — Templates

- [ ] `templates/torrents.html` — página principal:
      - Formulário de busca (campo q + select de categoria)
      - Div de resultados: `hx-get="/torrents/search"` com `hx-trigger="submit from:#search-form"`
      - Seção "Ativos": `hx-get="/torrents/active" hx-trigger="every 5s"` (polling HTMX)
- [ ] `templates/_torrents_active.html` — fragmento: tabela com nome, progresso (barra),
      velocidade, ETA, estado, botões pausa/resume/delete
- [ ] `templates/_torrent_results.html` — fragmento: cards de resultado com título,
      seeders/leechers, tamanho, indexer, botão "↓ baixar"

#### 6.6 — CSS e nav

- [ ] Adicionar estilos `.torrent-card`, `.torrent-table`, `.seed-count`, `.leech-count`
      a `static/style.css`
- [ ] `_macros.html` WEB cards: não adicionar botão torrent (seria scope creep)

---

### Fase 7 — Biblioteca de URLs ~~(CONCEITO ABANDONADO)~~

> ~~Entrega: biblioteca pessoal de sites com scraping periódico e versionamento por diff.~~
>
> **Conceito original abandonado em 2026-05-05.** O propósito da Biblioteca é ser um buscador
> pessoal sobre domínios curados — o mesmo objetivo da Fase 10 (crawler BFS). A distinção
> entre "URL individual com diff" e "domínio crawleado" foi descartada: a Fase 10 cobre
> o escopo completo. Os itens abaixo foram marcados como `[x]` incorretamente; na prática
> apenas o schema foi criado e nunca populado. Migration v13 (`database.py`) dropa as
> tabelas orphaned (`library_urls`, `library_diffs`, `library_fts`).

- ~~[x] Migration v5: tabelas `library_urls` / `library_diffs` / `library_fts`~~
  **Nunca populadas. Dropadas pela migration v13.**
- ~~[x] `services/library.py` — `add_url()`, `scrape_and_store()`, `check_overdue()`, `compute_diff()`~~
  **Nunca implementado.**
- ~~[x] `routers/library.py` — rotas de monitoramento de URLs individuais~~
  **Nunca implementado. As rotas `/library` existentes são da Fase 10 (crawler BFS).**
- ~~[x] `templates/library.html` — UI de monitoramento com diff e notas~~
  **O template existente é da Fase 10, não deste conceito.**
- ~~[x] Background task: re-scrape periódico de URLs vencidas~~
  **Nunca implementado. O loop horário da Fase 10 cobre re-crawl de domínios.**
- ~~[x] Busca local inclui `library_fts`~~
  **Removido em 2026-05-05 (dead code — tabela nunca populada).**
- ~~[x] Botão `+` para enfileirar URL na biblioteca~~
  **Reaproveitado na Fase 10 como quick-add de domínio (`POST /library/add-quick`).**

---

#### Fase 7.5 — Lista negra de domínios

> Entrega: domínios bloqueados nunca aparecem nos resultados de busca web.

- [x] Migration v6: tabela `blocked_domains` — `id, domain, added_at`
- [x] `services/web_search.py` — filtrar resultados excluindo domínios em `blocked_domains`
      (hostname normalizado sem `www.`); aplicado antes de retornar ao router
- [x] Botão `−` em cada card de resultado `WEB`: `POST /domains/block`, toast de confirmação
- [x] `routers/domains.py` — `POST /domains/block` (extrai domínio da URL);
      `DELETE /domains/block/{domain}` (desbloquear)
- [x] `templates/domains.html` — página `/domains` dedicada: lista de domínios bloqueados
      com botão desbloquear (✕) e formulário para adicionar via URL

---

### Fase 8 — Histórico unificado

> Entrega: página `/history` com timeline de todas as atividades.

- [x] Migration v10: tabela `activity_log` (`id, type, title, url, meta_json, created_at`)
      onde `type` ∈ `search|archive|download`
- [x] `routers/history.py` — `GET /history?type=all|search|archive|download&page=1`
      paginado por data desc
- [x] `templates/history.html` — timeline agrupada por data; ícone por tipo;
      filtros por tipo no topo com HTMX
- [x] Popular `activity_log` nos eventos: `save_search()` e `POST /archive` (sucesso);
      download: pendente até Fase 11 (downloads ainda não implementados)

---

### Fase 9 — Polimento e Integração Final

> Entrega: app production-ready, integrado no ecossistema, lançável com um comando.

- [ ] `iniciar.sh` — versão final robusta: verificar uv instalado, `uv sync --frozen`
- [ ] Escrever `akasha.exe_path` no `ecosystem.json` no startup para o HUB poder lançar
- [ ] `templates/settings.html` — página `/settings`: caminhos do ecossistema (leitura),
      pasta padrão de download, host/porta qBittorrent, profundidade padrão de crawl (default: 2)
- [ ] Nav: adicionar aba "Biblioteca", "Histórico" e "Sites" na topbar
- [ ] `README.md` — atualizar seção "Estado" para "Implementado — Fase 9"

---

### Fase 10 — Buscador de Sites Pessoais

> Entrega: motor de busca próprio sobre domínios curados. O usuário adiciona sites, o AKASHA
> faz crawling BFS respeitando profundidade, indexa em FTS5 e expõe via checkboxes na busca.

### Decisões de design
- **Escopo do crawler**: mesmo domínio + subdomínios selecionados pelo usuário
- **Profundidade default**: 2 (configurável em `/settings`)
- **Re-crawl**: manual (botão) + automático a cada 7 dias (`crawl_pending_sites()` no loop horário)
- **Interface de busca**: checkboxes na barra — `□ Web  □ Ecossistema  □ Sites pessoais`
- **Acesso ao conteúdo**: apenas via busca (ver Planos Futuros para navegação inline)

> **Nota de implementação (2026-05-06):** os routes foram implementados em `/library` em vez de
> `/sites` como planejado aqui. "Sites" e "Biblioteca" foram unificados numa única aba chamada
> Biblioteca (`routers/crawler.py`). O path `/sites` não existe no código — substituir mentalmente
> por `/library` ao ler os itens abaixo.

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

### Fase 10.5 — Navegação inline de páginas crawleadas

> Entrega: reader mode próprio — abrir e ler qualquer `crawl_page` sem sair do AKASHA.

- [x] `database.py` — helpers `get_crawl_page_by_url(url) -> tuple | None` e
      `get_crawl_pages_by_site(site_id, limit, offset) -> list[tuple]`
      (retorna `id, url, title, http_status, crawled_at` sem `content_md` para a lista)
- [x] `routers/crawler.py` — `GET /library/reader?url=` — busca `crawl_page` por URL via
      `get_crawl_page_by_url`, converte `content_md` → HTML com lib `markdown`,
      renderiza `page_reader.html`; 404 se não encontrada
- [x] `routers/crawler.py` — `GET /library/{site_id}/pages?q=&page=1` — lista paginada
      (20/pág) de páginas do site; suporte a filtro por `q` (título/url); retorna fragment
      HTMX `_site_pages.html`
- [x] `templates/page_reader.html` — layout reader mode: cabeçalho com título, URL original
      (link externo ↗), data de crawl, botão "← Voltar"; conteúdo HTML do markdown com
      tipografia IM Fell English; compatível com tema sépia/noturno
- [x] `templates/_site_pages.html` — fragment HTMX: lista de cards de página (título, URL
      abreviada, data, badge de status HTTP); botão "Ler" abre `/library/reader?url=...`;
      paginação "Carregar mais" com `hx-swap="outerHTML"` no load-more li
- [x] `templates/_library_list.html` — botão "ðŸ“„ N páginas" em cada site card que expande
      `_site_pages.html` via HTMX (`htmx.ajax GET /library/{id}/pages`);
      colapsar ao clicar de novo (toggleSitePages em library.html)
- [x] `templates/_macros.html` — nos cards de resultado com `source="SITES"`, adicionar
      botão "Ler" ao lado do link externo que abre `/library/reader?url=...` inline

---

### Fase 11 — Correção de bugs e melhorias

> Entrega: app mais rápido, sem gargalos de I/O e com SQLite bem configurado.

#### Alta prioridade (impacto imediato visível)

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

- ~~[x] **`check_overdue` e `list_entries` sem `content_md`** — `services/library.py`~~
  **Falso positivo — `services/library.py` nunca foi criado (Fase 7 abandonada).**

#### Média prioridade (reduz lock contention no crawler)

- [x] **Crawl com conexão única por sessão** — `services/crawler.py`: `crawl_site` agora
      usa 2 conexões (leitura inicial + sessão BFS completa); `_process_url` captura `db`
      via closure em vez de abrir nova conexão por página.

- [x] **FTS skip em conteúdo idêntico** — `services/crawler.py` → `_upsert_page`:
      consulta `content_hash` atual antes do FTS; pula DELETE + INSERT se hash idêntico.

- [x] **`asyncio.get_event_loop()` → `asyncio.get_running_loop()`** — `routers/crawler.py`
      (3 ocorrências) e `main.py` (1 ocorrência).

#### Baixa prioridade (manutenção a longo prazo)

- [x] **Limpeza periódica do search_cache** — `main.py` → `_monitor_crawler()`:
      ao acordar, executar `DELETE FROM search_cache WHERE created_at < ?` com cutoff
      de 24 h. Sem essa limpeza o cache cresce indefinidamente — cada query única
      adiciona uma linha; após semanas de uso o arquivo SQLite infla.

- [ ] **Monitor de biblioteca com paralelismo controlado** — `main.py` → `_monitor_library()`:
      em vez de re-scrape sequencial das URLs vencidas, usar `asyncio.gather` com
      `asyncio.Semaphore(3)` — máximo 3 scrapes simultâneos. Uma biblioteca com 50+
      URLs vencidas pode travar o event loop por vários minutos em modo sequencial.
      ⚠ **BLOQUEADO**: depende de `services/library.py` e `routers/library.py` (Fase 7
      marcada como concluída no TODO mas nunca implementada).

- [x] **Dependência `markdown`** — `pyproject.toml`: adicionar `markdown>=3.7`
      (necessário para Fase 10.5 — converter `content_md` → HTML no reader mode).
      ⚠ **ADIADO**: adicionar junto com a implementação da Fase 10.5.

---

### Fase 12 — Extensão Firefox (Zen Browser)

> Entrega: extensão Manifest V3 que detecta URLs de vídeo na aba atual e delega o download
> ao Hermes via AKASHA com um clique. Requer Fase 3 do Hermes (mini API HTTP).

#### Estrutura de arquivos
- [ ] `extension/manifest.json` — Manifest V3; permissões: `activeTab`,
      `http://localhost:7071/*`; action com ícones active/inactive;
      background service worker; popup declarado
- [ ] `extension/icons/` — ícone 16/32/48/128px nos dois estados (active e greyscale)
- [ ] `extension/popup/popup.html` + `popup.css` + `popup.js` — UI mínima:
      URL atual, dois botões: "⬇ Baixar vídeo" e "ðŸ“ Transcrever";
      ambos rodam em segundo plano via Hermes; feedback de estado
      (aguardando / na fila / erro Hermes offline / erro AKASHA offline)

#### Background script
- [ ] `extension/background.js` — ao mudar de aba ou navegar, verificar se a URL
      pertence a site de vídeo suportado pelo yt-dlp (YouTube, Vimeo, Twitch,
      Twitter/X, TikTok, Reddit, Dailymotion, Bilibili, Niconico, etc.);
      habilitar/desabilitar ícone da action conforme resultado
- [ ] `extension/background.js` — ao receber mensagem `{action: "download"|"transcribe", url}`
      do popup, fazer `POST http://localhost:7071/api/hermes/download` com `{url, mode}`;
      retornar `{ok, error?}` ao popup; fechar popup após confirmação (roda em bg)

#### Backend AKASHA
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

#### Instalação (desenvolvimento)
- [ ] `extension/README.md` — instruções: `about:debugging` → "Este Firefox" →
      "Carregar extensão temporária" → selecionar `extension/manifest.json`

---

#### Fase 12.5 — Aba "Ver Mais Tarde"

> Lista interna de URLs para retomar depois, sem arquivar nem monitorar.
> Visível apenas no AKASHA — não indexada no `local_fts` nem exportada para o ecossistema.
> Resultados aparecem na busca global como seção separada "Salvo para depois".

#### Banco de dados

- [x] Migration v9: tabela `watch_later` —
      `id, url (UNIQUE), title, snippet, notes, added_at`
- [x] Migration v9: FTS5 `watch_later_fts` — `(id UNINDEXED, url UNINDEXED, title, notes)`
      sincronizada manualmente nos helpers

#### Backend

- [x] `database.py` — helpers: `add_watch_later(url, title, snippet) -> int`;
      `get_all_watch_later() -> list[tuple]`; `delete_watch_later(id) -> None`;
      `search_watch_later(query, limit) -> list[tuple]`
- [x] `services/local_search.py` — função `search_watch_later(query, max_results)`
      que consulta `watch_later_fts`; retorna `list[SearchResult]` com `source="DEPOIS"`;
      NÃO adiciona ao `local_fts` (não visível para o ecossistema)
- [x] `routers/watch_later.py` — `GET /watch-later` (página da lista);
      `POST /watch-later/add` (form: url, title?, snippet?; retorna 200);
      `DELETE /watch-later/{id}` (retorna 200)

#### Templates

- [x] `templates/watch_later.html` — lista de itens salvos: título, URL, data,
      campo notes inline editável, botão "remover"; empty state com hint
- [x] `templates/_macros.html` — botão `☆ ver depois` (`hx-post="/watch-later/add"`)
      nos cards de resultado `WEB`, junto com os outros botões de ação
- [x] `templates/base.html` — aba "ver depois" na nav entre "sites" e "downloads"
- [x] `templates/search.html` — seção "Salvo para depois" (após seção Sites,
      antes do empty state); aparece sempre que há matches no `watch_later_fts`

#### Integração com busca

- [x] `routers/search.py` — incluir `search_watch_later(q)` no `asyncio.gather`;
      passa `watch_later_results` para o template; seção visível
      independente dos checkboxes (sempre busca se há query)

#### TODO update

- [x] Atualizar `AKASHA/TODO.md` ao concluir: marcar itens e atualizar data

---

### Fase 13 — API de Pesquisa Profunda (integração com Mnemosyne)

> Entrega: endpoint JSON que o Mnemosyne pode chamar para buscar + scraping on-demand,
> permitindo "Modo de Pesquisa Profunda" que combina biblioteca local com conteúdo web atual.

#### Novos endpoints

- [x] `GET /search/json?q={query}&sources=web,sites&max={n}` — retorna resultados de busca
      como JSON puro (`list[SearchResult]`) em vez de HTML; reutiliza a lógica de
      `routers/search.py` mas com `Response` JSON; usado pelo Mnemosyne para obter URLs relevantes
      sem scraping ainda

- [x] `POST /fetch` (body: `{url: str, max_words: int = 2000}`) — fetch + scraping
      completo de uma URL usando a cascata do `ecosystem_scraper` + fallback Jina Reader;
      retorna `{url, title, content_md, word_count, error?}`; não persiste nada — resposta
      efêmera para uso imediato pelo Mnemosyne; timeout 30s

#### Notas de implementação

- Ambos os endpoints são somente-leitura — não alteram estado do AKASHA
- `GET /search/json` pode ser implementado extraindo a lógica de busca de `routers/search.py`
  para uma função pura e reutilizando em ambos os handlers (HTML e JSON)
- `POST /fetch` reutiliza `ecosystem_scraper.extract()` + a lógica de Jina já em `archiver.py`
- Latência esperada: `/search/json` ~400ms (DDG cache hit) / ~1.5s (miss); `/fetch` ~2–8s por URL

---

### Fase 14 — Integração KOSMOS nos cards de resultado

> Botão nos cards de resultado web para adicionar a URL à lista de fontes do KOSMOS.

- [x] `templates/_macros.html` — botão "K" nos cards `WEB`:
      `hx-post="/kosmos/add-source"` com `{"url": "...", "name": "..."}`;
      usa `detect_feed_type()` do KOSMOS para inferir tipo (youtube/rss/etc.)
- [x] KOSMOS expõe `POST /add-source` via `http.server` em thread daemon (porta 8965 por padrão)
- [x] `routers/kosmos_bridge.py` — lê porta do ecosystem.json, encaminha para KOSMOS; 503 se KOSMOS offline

---

### Fase 15 — Qualidade de Busca e Crawl (pesquisa 2026-04-24)

> Melhorias derivadas de pesquisa sobre arquitetura de buscadores, otimização de índice invertido
> e deduplicação. Organizadas por prioridade.

#### Alta prioridade

- [x] **[A] BM25 com pesos por campo** — usar `bm25(crawl_fts, 10, 1)` na consulta FTS5
      para dar peso 10× ao título vs. corpo; melhora ranking sem custo computacional
      (`database.py` / `services/local_search.py`)

- [x] **[B] Normalização de URL antes de inserir no crawl** — remover parâmetros de tracking
      (`utm_*`, `fbclid`, `ref`, etc.) antes de `INSERT` em `crawl_pages`; evita duplicatas
      por variação de URL (`services/crawler.py` + helper em `database.py`)

- [x] **[C] FTS5 optimize periódico pós-crawl** — executar
      `INSERT INTO crawl_fts(crawl_fts) VALUES('optimize')` após crawls com > 200 páginas
      novas; mescla segmentos fragmentados e mantém performance de busca estável
      (`services/crawler.py` ou job agendado em `main.py`)

- [x] **[D] Cache de robots.txt por domínio (TTL 24h)** — armazenar regras de robots.txt
      em memória por domínio com expiração de 24h; evita fetch redundante a cada URL
      (`services/crawler.py`)

#### Média prioridade

- [x] **[E] Rate limiting por domínio com fila de prioridade** — limitar requisições por
      domínio (ex: 1 req/s) usando `asyncio.Queue` + semáforo por host; evita banimento
      e respeita servidores (`services/crawler.py`)

- [x] **[F] SimHash para detecção de near-duplicatas** — calcular SimHash do conteúdo
      extraído; rejeitar páginas com distância Hamming < 3 de páginas já indexadas;
      `pip install simhash`; reduz ruído no índice sem hashing exato
      (`services/crawler.py` + `database.py`)

- [x] **[G] Índice de prefixo FTS5** — adicionar `prefix="2,3"` na criação de `crawl_fts`
      para acelerar buscas com autocompletar e queries de prefixo parcial
      (`database.py` — migration necessária)

- [x] **[H] `favor_recall=True` no trafilatura antes do fallback Jina** — passar
      `favor_recall=True` no `ecosystem_scraper` / extração local para aumentar cobertura
      de conteúdo antes de recorrer ao Jina Reader externo
      (`ecosystem_scraper.py` ou `services/archiver.py`)

#### Baixa prioridade

- [ ] **[I] Campo separado para headings no FTS5** — extrair headings (h1–h3) do HTML
      e indexar em coluna dedicada com peso ~50×; melhora recall para queries de conceito
      (`database.py` + `services/crawler.py` — migration necessária)

- [ ] **[J] Meilisearch como backend alternativo para corpus grande** — avaliar substituição
      do FTS5 pelo Meilisearch self-hosted quando o corpus ultrapassar ~100k páginas;
      oferece typo-tolerance, facetas e ranking configurável nativo; requer processo separado

---

### Fase 16 — Correção de Bugs (auditoria 2026-04-24)

> Bugs encontrados por inspeção de código. Nenhum requer migration de schema.

#### Alta prioridade (funcionalidade quebrada)

- [x] **[BUG-1] `/domains` — bloquear/desbloquear não atualiza a lista na UI**
      `routers/domains.py` + `templates/domains.html`: os endpoints `POST /domains/block` e
      `DELETE /domains/block/{domain}` retornam `Response(status_code=200)` com body vazio,
      mas o template usa `hx-select="#domains-list"` esperando receber esse elemento na resposta.
      HTMX não encontra o seletor → lista não atualiza; usuária precisa recarregar a página.
      **Fix:** retornar a lista atualizada como fragment HTML em ambos os endpoints, ou
      mudar para `hx-get="/domains" hx-trigger="revealed"` como follow-up.

- [x] **[BUG-2] `search.html` — link "Adicionar sites" aponta para `/sites` que não existe**
      `templates/search.html:18`: `<a href="/sites">Adicionar sites →</a>` causa 404.
      O gerenciamento dos sites crawleados está em `/library`.
      **Fix:** corrigir para `href="/library"`.

- [x] **[BUG-3] `crawl_site` — status travado em `'crawling'` quando ocorre exceção**
      `services/crawler.py`: o status é definido como `'crawling'` antes do BFS, mas só
      resetado para `'idle'` no final bem-sucedido. Se qualquer exceção ocorrer (HTTP, DB,
      timeout), o site fica com `status='crawling'` para sempre. `crawl_pending_sites()`
      filtra por `status='idle'`, logo o site nunca mais é re-crawlado automaticamente.
      **Fix:** envolver o BFS em `try/finally` e garantir `UPDATE status='idle'` no `finally`.

#### Média prioridade (inconsistência / UX)

- [x] **[BUG-4] `main.py` `index()` — contexto incompleto para `search.html`**
      `main.py:101`: o handler da rota `/` não passa `site_results`, `has_sites` e
      `has_more_web` para o template. O Jinja2 não crasha (trata `undefined` como falsy),
      mas o comportamento é inconsistente com o handler `/search`.
      **Fix:** adicionar as chaves faltantes com valores padrão (`site_results=[]`,
      `has_sites=False`, `has_more_web=False`, `src_web=True`, `src_eco=True`, `src_sites=False`).

- [x] **[BUG-5] `search.html` — aviso "nenhum site cadastrado" dentro do bloco `{% if error %}`**
      `templates/search.html`: o bloco `{% if src_sites and not has_sites and query %}` está
      aninhado dentro de `{% if error %}`, então o aviso só aparece quando há erro de busca.
      Deveria aparecer independentemente, como estado informativo separado.
      **Fix:** mover o bloco de aviso para fora do `{% if error %}`, antes ou logo após o
      bloco principal de resultados.

- [x] **[BUG-6] `routers/system.py` — `/open-file` nunca reporta erro ao abrir arquivo local**
      `subprocess.Popen(["xdg-open", path])` é fire-and-forget: sempre retorna HTTP 200 mesmo
      que o xdg-open falhe silenciosamente (comum no CachyOS/Niri/Wayland quando
      `DBUS_SESSION_BUS_ADDRESS` não está disponível no processo filho). O toast mostra
      "Abrindo arquivo…" mesmo que nada abra.
      **Fix:** usar `asyncio.create_subprocess_exec` para capturar o código de retorno;
      tentar `gio open` como fallback se xdg-open falhar; retornar HTTP 500 com mensagem
      legível se ambos falharem.

---

### Busca Local Avançada — Pendências Técnicas


- [x] Bug: `_search_chroma()` cria novo `PersistentClient` a cada query — cachear como singleton:
  **Motivo:** `AKASHA/services/local_search.py` linha ~247 faz
  `client = _chromadb.PersistentClient(path=index_path)` dentro da função de busca.
  Abrir um PersistentClient abre o SQLite subjacente do ChromaDB e carrega metadados — custo
  de I/O repetido desnecessariamente a cada busca interativa.
  **Implementação (`AKASHA/services/local_search.py`):**
  ```python
  _chroma_clients: dict[str, Any] = {}   # module-level cache

  def _get_chroma_client(index_path: str):
      if index_path not in _chroma_clients:
          _chroma_clients[index_path] = _chromadb.PersistentClient(path=index_path)
      return _chroma_clients[index_path]
  ```
  Substituir `client = _chromadb.PersistentClient(path=index_path)` por
  `client = _get_chroma_client(index_path)` em `_search_chroma()`.
  Resultado: latência de busca local reduzida; sem impacto em corretude.

- [x] AKASHA: substituir `rank_combined()` por Reciprocal Rank Fusion (RRF):
  **Motivo:** `rank_combined()` usa `_score()` — contagem simples de keywords nos campos title e
  snippet. Isso descarta os scores de relevância reais de cada método:
  - FTS5 retorna resultados já ordenados por bm25() (score real de relevância lexical)
  - ChromaDB retorna resultados ordenados por distância euclidiana no espaço de embeddings
  Ignorar essas ordenações e usar contagem de termos é inferior ao RRF, que considera a posição
  relativa de cada resultado em cada lista sem precisar dos scores absolutos.
  A pesquisa confirma: RRF sem parâmetros supera linear combination com alpha tuning manual
  na maioria dos benchmarks (arxiv 2604.01733).
  **Implementação (`AKASHA/services/local_search.py`):**
  ```python
  def _rrf(rankings: list[list[SearchResult]], k: int = 60) -> list[SearchResult]:
      """Reciprocal Rank Fusion — funde múltiplas listas rankeadas."""
      scores: dict[str, float]       = {}
      by_url: dict[str, SearchResult] = {}
      for ranking in rankings:
          for rank, result in enumerate(ranking):
              key = result.url.lower().rstrip("/")
              scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
              by_url[key] = result
      ordered = sorted(scores, key=scores.__getitem__, reverse=True)
      return [by_url[key] for key in ordered]
  ```
  Substituir a chamada a `rank_combined()` por `_rrf([fts_results, chroma_results])` em
  `search_local()`. A função `rank_combined()` pode ser mantida como fallback para resultados
  de fontes sem ranking explícito (web results, etc.).

- [x] AKASHA: FTS5 com tokenizer `unicode61 remove_diacritics=2` para busca acentuada:
  **Motivo:** a tabela `local_fts` usa o tokenizer padrão do FTS5 (`unicode61`), que por padrão
  trata "açaí" diferente de "acai". Com `remove_diacritics=2`, "cafe" encontra "café" e
  "musica" encontra "música" — essencial para corpus em português.
  **Implementação (`AKASHA/database.py` — migration):**
  Recriar a tabela FTS com o tokenizer correto. As migrations existentes já têm padrão — adicionar:
  ```sql
  CREATE VIRTUAL TABLE IF NOT EXISTS local_fts USING fts5(
      path UNINDEXED,
      title,
      body,
      source UNINDEXED,
      tokenize = 'unicode61 remove_diacritics 2'
  );
  ```
  Como é uma virtual table, recriar exige reindexar — executar `index_local_files()` no próximo startup.

- [x] AKASHA: deduplicação de conteúdo crawlado por hash SHA-256:
  **Motivo:** o crawler normaliza URLs mas não detecta conteúdo duplicado entre URLs diferentes
  (syndication, mirrors, redirects resolvidos). Dois artigos com mesmo conteúdo são indexados
  e buscados duplicadamente, poluindo os resultados.
  Mesma técnica do KOSMOS: SHA-256 do conteúdo extraído como guarda de deduplicação.
  **Implementação (`AKASHA/services/crawler.py` + `database.py`):**
  1. Adicionar coluna `content_hash TEXT` à tabela que armazena páginas crawladas
  2. Antes de persistir uma página: calcular `hashlib.sha256(content.encode()).hexdigest()`
  3. `SELECT id FROM crawled_pages WHERE content_hash = ?` — se existir: ignorar URL, não re-indexar
  4. Adicionar index em `content_hash` para a query ser O(1)

- [x] AKASHA: ETag/Last-Modified no crawler para não re-crawlar páginas sem mudança:
  **Motivo:** o crawler re-crawla todas as URLs a cada ciclo, mesmo que o conteúdo não tenha
  mudado. Servidores que suportam cache HTTP retornam 304 Not Modified com ETag/Last-Modified,
  evitando download e parsing do HTML inteiro.
  **Implementação (`AKASHA/services/crawler.py`):**
  1. Armazenar `etag` e `last_modified` junto a cada URL crawlada na tabela do banco
  2. No re-crawl, passar os headers condicionais:
     ```python
     headers = {}
     if stored_etag:    headers["If-None-Match"]     = stored_etag
     if stored_lm:      headers["If-Modified-Since"] = stored_lm
     resp = await client.get(url, headers=headers)
     if resp.status_code == 304:
         return  # sem mudança — ignorar
     # senão: processar normalmente e salvar novos etag/last-modified
     etag = resp.headers.get("ETag")
     lm   = resp.headers.get("Last-Modified")
     ```

- [x] AKASHA: throttle adaptativo no crawler baseado em tempo de resposta do servidor:
  **Motivo:** `_CRAWL_CONCURRENCY = 4` é fixo e não reflete a capacidade real do servidor alvo.
  Servidores lentos (resposta > 2s) ficam sobrecarregados; servidores rápidos são sub-utilizados.
  Scrapy AutoThrottle usa `delay = response_time / target_concurrency` como heurística.
  **Implementação (`AKASHA/services/crawler.py`):**
  1. Medir `response_time` de cada request: `t0 = time.monotonic(); resp = await client.get(url); dt = time.monotonic() - t0`
  2. Manter média móvel de response_time por domínio (janela de 5 requests)
  3. Ajustar delay no rate limiter:
     - `dt_avg < 0.5s` → delay mínimo (0.5s) — servidor rápido
     - `0.5s ≤ dt_avg < 2s` → delay = dt_avg (politeness simples)
     - `dt_avg ≥ 2s` → delay = 2× dt_avg, reduzir concorrência para 2
  4. Em 429 (Too Many Requests): backoff exponencial `2^n × delay_base + jitter`

- [x] AKASHA: Trafilatura como primeiro estágio de extração (substituição em ecosystem_scraper.py):
  **Motivo:** idêntico ao KOSMOS — F1=0.945 do Trafilatura vs F1=0.665 do BeautifulSoup.
  Conteúdo mais limpo no índice FTS5 do AKASHA = busca mais precisa, menos falsos positivos.
  Ver item equivalente em PENDÊNCIAS — KOSMOS para implementação detalhada (compartilham
  o `ecosystem_scraper.py`).


---

## KOSMOS — Leitor de Feeds

> **Padrões obrigatórios (toda sessão de desenvolvimento):**
> - Tipagem completa em todos os parâmetros e retornos
> - Erros nunca engolidos silenciosamente — propagar, retornar valor verificável ou dar feedback ao usuário
> - `log.error()` para falhas reais, `log.warning()` só para condições esperadas/recuperáveis
> - Atualizar este arquivo a cada feature implementada ou pedida
> - **Commit git a cada funcionalidade concluída** — mensagem descritiva, nunca acumular para o final

Referência de arquitetura: `KOSMOS_DEV_BIBLE_1.txt`

---

### Design Bible v2.0 — Audit (2026-04-11)

- [x] Modo noturno migrado para paleta "Atlas Astronômico à Meia-Noite" em `night.qss`
- [x] `reader_night.css` atualizado para nova paleta (fundo, bordas, `hr::after`)
- [x] `splash_screen.py` — cores hardcoded noturnas corrigidas

---

### FASE EXTRA — Features de Enriquecimento
> Funcionalidades além do escopo original. Implementar sequencialmente.

- [x] Filtros de palavra-chave (blocklist)
- [x] Feeds de busca (Google News RSS por termo)
- [x] Tags manuais nos artigos — chips no leitor, CRUD em `feed_manager.py`
- [x] Posição de scroll salva — `scroll_pos` via `window.scrollY`, restaurado no `loadFinished`
- [x] Top fontes e tópicos no dashboard — painéis com barras proporcionais
- [x] Deduplicação de artigos similares — `duplicate_of`, `rapidfuzz` (85%, 48h, entre feeds)
- [x] Highlights e anotações no leitor — `highlights` table, JS injection via `_HIGHLIGHT_SETUP_JS`, chips na barra abaixo das tags, anotações via QInputDialog
- [x] Tradução inline no leitor — `deep-translator` (Google Translate), sem dialog extra, menu de idiomas, "Ver original"
- [x] Scraping multilíngue — fallback BS4 para idiomas sem tokenizador
- [x] Fallback de scraping — traduz título para inglês → busca Google News RSS → tenta scraping do resultado
- [x] Filtro de idioma na view unificada — coluna `language` no modelo, detecção via `langdetect` no save
- [x] Título do artigo exibido no leitor (webview) e traduzido junto com o corpo
- [x] Label de idioma original → traduzido na barra inferior do leitor
- [x] Auto-salvar artigo ao criar primeiro destaque
- [x] Tratamento de erros: `log.error` para falhas reais, feedback visível ao usuário (tag, destaque), tipagem completa nos helpers privados

---

### FASE A — Leitor e Arquivo

- [x] Navegação anterior / próximo entre artigos
- [x] Botão "Buscar artigo completo" (com fallback BS4 multilíngue + fallback por título)
- [x] Purgação automática de artigos antigos (`purge_old_articles`)
- [x] `saved_view.py` — view de artigos salvos/favoritados
- [x] `archive_manager.py` — exportar artigo para Markdown em `data/archive/`
- [x] `archive_view.py` — browser do arquivo (lista arquivos .md de `data/archive/`)
- [x] Conversão HTML → Markdown via `html2text`

---

### FASE B — Plataformas Adicionais

**Reddit:**
- [ ] `reddit_fetcher.py` — wrapper praw 7.x
- [ ] `add_reddit_dialog.py` — adicionar subreddit (requer credenciais)
- [ ] Configurações → seção Reddit (client_id, client_secret, testar conexão)
- [ ] Mapeamento de posts para schema de artigos (score, num_comments em `extra_json`)

**YouTube:**
- [ ] Detecção automática de URL YouTube em `add_feed_dialog.py`
- [ ] Extração de `channel_id` de URLs `@handle` via requests + BS4
- [ ] Thumbnail de vídeos nos article cards

**Outras plataformas (RSS puro — feedparser já funciona, falta detecção):**
- [ ] Detecção automática: Tumblr, Substack, Mastodon pela URL
- [ ] `feed_type` correto salvo no banco para cada plataforma

---

### FASE C — Busca Global

- [x] FTS5 virtual table com triggers de sincronização (`database.py`)
- [x] `search.py` — query FTS5, retorna artigos ranqueados por relevância
- [x] Barra de busca global `Ctrl+K` (overlay flutuante)
- [x] Resultados com feed de origem e snippet destacado (mark)
- [x] Clicar no resultado abre o leitor
- [x] Navegação por teclado (↑↓ Enter Esc)

---

### FASE D — Exportação PDF e Estatísticas

**Exportação PDF:**
- [ ] `export_pdf.py` — WeasyPrint + template sépia (`export_template.html`)
- [ ] `export_dialog.py` — seletor de destino (artigo único ou lista de salvos)
- [ ] Botão "Exportar PDF" na toolbar do leitor

**Estatísticas:**
- [x] `read_sessions` — registrar início/fim de leitura por artigo
- [x] `stats.py` — agregação por dia, feed, plataforma, salvos por mês
- [x] `stats_view.py` — gráficos matplotlib, filtro de período
- [x] Botão "Stats" na sidebar

---

### FASE E — Polimento Final

- [ ] Animações: fade-in 150ms nos cards, slide 200ms no leitor, expand/collapse 120ms na sidebar
- [ ] Cursor piscante dourado (`#b8860b`) em campos de texto (QTimer 530ms)
- [ ] Cantos dobrados decorativos (SVG 20×20px)
- [ ] Ícone do app (`.ico` Windows, `.png` Linux)
- [ ] `iniciar.sh` e `iniciar.bat` com setup automático do venv
- [ ] Revisar todos os caminhos com `pathlib.Path` (sem strings hardcoded)
- [ ] Testes em Windows 10 (WeasyPrint + GTK3, QWebEngineView, VC++ Redist)

---

### FASE F — IA Local (Ollama)

> Integração com modelos LLM locais via Ollama (http://localhost:11434).
> Modelos:
> - `qwen2.5:7b` — geração de texto: resumo, extração de tags, análise
> - `nomic-embed-text` — embeddings semânticos: relevância, busca vetorial, similaridade
>
> Toda feature de IA é opcional e degradada graciosamente se o serviço não estiver disponível.
> Implementar sequencialmente — infraestrutura primeiro.

**Infraestrutura:**
- [x] `app/core/ai_bridge.py` — cliente Ollama: verificar disponibilidade (`/api/tags`), gerar texto (`/api/generate` streaming via `qwen2.5:7b`), gerar embeddings (`/api/embed` via `nomic-embed-text`)
- [x] Migration: colunas `ai_summary TEXT`, `ai_tags TEXT` (JSON), `embedding BLOB` (768 floats × 4 bytes), `ai_relevance REAL` em `articles`
- [x] Configurações → seção IA: endpoint (padrão `http://localhost:11434`), modelo de geração, modelo de embeddings, habilitar/desabilitar, botão "Testar conexão"

**Resumo de artigos (`qwen2.5:7b`):**
- [x] Botão "Resumir" na toolbar do leitor — aciona `ai_bridge` com o conteúdo do artigo
- [x] Painel recolhível abaixo da meta bar para exibir o resumo (streaming token a token via sinal PyQt)
- [x] Cache: resumo salvo em `ai_summary`; não regenera se já existir (botão vira "Ver resumo")

**Tags automáticas (`qwen2.5:7b`):**
- [x] Ao abrir artigo sem tags, sugerir tags via `format: "json"` do Ollama
- [x] Chips de sugestão em cor distinta na tags row — aceitar clicando, descartar com ×

**Relevância via embeddings (`nomic-embed-text`):**
- [x] Gerar embedding ao salvar/ler artigo em background — armazenar em `embedding BLOB`
- [x] Perfil de interesses: média dos embeddings dos artigos lidos/salvos (atualizado incrementalmente)
- [x] Score de relevância = cosine similarity(embedding do artigo, perfil) → `ai_relevance REAL`
- [x] Badge de relevância opcional nos article cards (configurável nas Settings)

**Busca semântica (`bge-m3:latest`):**
- [x] Toggle na search overlay para alternar entre FTS5 (palavras-chave) e busca vetorial (semântica)
- [x] Embed a query em tempo real → retorna top-N artigos por cosine similarity

**Análise de viés político (`qwen2.5:7b`):**
- [ ] Migration: colunas `ai_political_economic REAL` (-1.0 esquerda ↔ +1.0 direita) e `ai_political_authority REAL` (-1.0 libertário ↔ +1.0 autoritário) em `articles`
- [ ] Botão "Analisar viés" no leitor — retorna JSON `{economic_axis, authority_axis, confidence, reasoning}`
- [ ] Bússola política (widget 2D) no leitor exibindo a posição do artigo
- [ ] Agregação por feed na `sources_view` — posição média dos artigos analisados de cada fonte

**Detecção de clickbait (`qwen2.5:7b`):**
- [x] Migration: coluna `ai_clickbait REAL` (0.0 sem clickbait ↔ 1.0 clickbait puro) em `articles`
- [x] Score gerado pelo `_AnalyzeWorker` ao abrir artigo; salvo em cache
- [x] Badge `⚠` opcional nos article cards quando `ai_clickbait > 0.6` (configurável nas Settings)
- [x] Indicador `⚠ clickbait N%` na meta bar do leitor quando > 60%
- [ ] Filtro por score de clickbait na unified feed view

**Citação ABNT + análise 5Ws ao salvar artigo:**
- [x] Painel colapsível "Citação & 5Ws" exibido ao salvar artigo (★)
- [x] Citação ABNT gerada dos metadados existentes (autor, título, feed, data, URL, data de acesso)
- [x] 5Ws (Quem/O quê/Quando/Onde/Por quê) via `_FiveWsWorker` com `json_format=True`; cache em `ai_5ws TEXT`
- [x] Autor do artigo exibido em destaque na meta bar do leitor (`QLabel#readerAuthor`)

**Refatoração `_AnalyzeWorker` unificado (`qwen2.5:7b`):**
- [x] Substituir `_TagSuggestWorker` + `_FiveWsWorker` por `_AnalyzeWorker` (JSON único ao abrir artigo)
- [x] JSON de resposta: `{tags, sentiment, clickbait, five_ws}` — um call, quatro campos
- [x] `_SummarizeWorker` mantido separado com streaming (botão "Resumir", inalterado)
- [x] `save_ai_analysis()` em `feed_manager` persiste tudo em uma transação

**Sentimento e Tom (`qwen2.5:7b`):**
- [x] Migration: coluna `ai_sentiment REAL` (-1.0 negativo ↔ +1.0 positivo) em `articles`
- [x] Score gerado pelo `_AnalyzeWorker` ao abrir artigo; salvo em cache
- [x] Borda colorida esquerda nos article cards (verde/vermelho, configurável nas Settings)
- [x] Indicador `● tom positivo/negativo/neutro` na meta bar do leitor
- [ ] Filtro por tom na unified feed view
- [x] Gráfico de tendência de sentimento no `stats_view` (linha colorida por segmento, área preenchida)

**NER — Extração de Entidades (`qwen2.5:7b`):**
- [x] Migration: coluna `ai_entities TEXT` (JSON `{people,orgs,places}`) em `articles`
- [x] Gerado pelo `_AnalyzeWorker` junto com tags/sentiment/clickbait/5ws
- [x] Três mini-charts no `stats_view`: top pessoas, organizações e lugares do período

**Clustering por tópico (embeddings):**
- [x] K-means numpy sobre embeddings `nomic-embed-text` (k adaptativo, 5 reinicializações)
- [x] Rótulo por extração de palavras-chave dos títulos do cluster (sem LLM adicional)
- [x] Cards de tópicos no `stats_view` (últimos 90 dias ou período selecionado)
- [x] Seção "Tópicos em Destaque" no Dashboard — atualizada em tempo real via `analysis_done` signal + debounce 8s; títulos clicáveis abrem o leitor

---

---

### FASE G — Unificar "Salvo" e "Arquivo" em um único conceito: Arquivar

> Objetivo: eliminar o conceito separado de "Salvo" (favorito no banco).
> Clicar em ★ / "Arquivar" faz as duas coisas de uma vez: marca `is_saved=1`
> no banco E exporta o `.md` em `data/archive/`. Um único gesto, um único estado.
> A aba "Salvos" vira "Arquivados" e reflete exatamente o que está no sistema de arquivos.

### G.1 — Renomear ação e botão no leitor

- [x] `reader_view.py` — botão `_save_btn`: texto muda de "☆ Salvar" / "★ Salvo"
      para "☆ Arquivar" / "★ Arquivado"
- [x] `reader_view.py` — `_on_toggle_saved()`: ao marcar como salvo, chamar
      `archive_manager.export_article(article)` junto; ao desmarcar, deletar o `.md`
      correspondente (silenciosamente, com log de erro)
- [x] Remover botão "Exportar" separado da `_toolbar_row2` (ação agora está em Arquivar)

### G.2 — Renomear aba e view "Salvos" → "Arquivados"

- [x] `sidebar.py` — texto do botão de navegação: "Salvos" → "Arquivados"
- [x] `saved_view.py` — título e strings internas: "Salvos" → "Arquivados"
- [x] `unified_feed_view.py` — sem referências visíveis ao usuário (verificado)

### G.3 — Migrar artigos já salvos (sem .md) ao iniciar

- [x] `main_window.py` — `_migrate_saved_to_archive()` no startup: exporta artigos
      com `is_saved=1` que ainda não têm `.md` correspondente

### G.4 — Ajustar ArchiveView

- [x] `archive_view.py` — remover botão "Exportar artigo atual" órfão do header
- [x] `archive_view.py` — mensagem de estado vazio atualizada (sem referência ao botão Exportar)
- [x] `archive_manager.py` — adicionar `get_archive_path()` e `delete_archive()` helpers

---

### FASE H — Indicador de Status do Ollama

> Atualmente não há feedback visual enquanto o Ollama está conectando/processando —
> o usuário não sabe se a requisição está pendente antes do streaming começar.

### H.1 — Indicador na janela de Configurações

- [x] `settings_view.py` → seção IA: `_ollama_conn_lbl` no topo da seção;
      `"● Ollama conectado · qwen2.5:7b"` (verde) ou `"○ Ollama offline"` (vermelho)
- [x] Verificação assíncrona via `_OllamaCheckWorker(QThread)` disparada no `showEvent`;
      não bloqueia a abertura das Configurações

### H.2 — Spinner antes do streaming do Resumo

- [x] `reader_view.py` → painel de resumo: exibe `"⟳  Aguardando Ollama…"` até o primeiro
      token chegar; substituído pelo streaming no `_on_summary_token` com flag `_summary_waiting`

### H.3 — Feedback durante análise em background

- [x] `reader_view.py` → meta bar: `_update_analysis_status("running")` já exibe
      `"⟳  analisando…"` via `_analysis_status_lbl` na indicators row
- [x] Ao término: `"done"` → `"✓  análise concluída"`, `"error"` → `"!  erro na análise"`

### H.4 — Badge de status global (sidebar ou statusbar)

- [x] `_ollama_badge` QLabel como widget permanente no `QStatusBar` (direita):
      `"●  Ollama"` (verde) / `"○  Ollama"` (cinza/vermelho) via object names CSS
- [x] Polling a cada 60s via `_ollama_poll_timer` + `_OllamaPoller(QThread)`;
      verificação inicial 500ms após startup

---

### FASE I — Idioma de exibição e detecção de idioma nos artigos

> Objetivo: o usuário escolhe um idioma de exibição nas Configurações e todos
> os títulos e manchetes são traduzidos automaticamente para esse idioma ao
> serem exibidos. Cada card também indica o idioma original do artigo.
> Usa o mesmo motor de tradução já presente (`deep-translator`).

### I.1 — Detectar e persistir idioma de cada artigo

- [x] `models.py` — coluna `language TEXT` já existe em `Article` (foi adicionada
      na Fase C + migration em `database.py`)
- [x] `feed_manager.py` — `_detect_lang()` via langdetect já existe e é chamado
      em `save_articles()`; artigos sem idioma ficam `None`
- [x] `article_card.py` — `langBadge` QLabel adicionado à meta row: exibe código ISO
      em maiúsculas (ex: `EN`, `PT`, `ZH`); CSS em day.qss e night.qss

### I.2 — Configuração de idioma de exibição

- [x] `config.py` — `"display_language": ""` já existe nos DEFAULTS
- [x] `settings_view.py` — QComboBox "Idioma dos cards" na seção Aparência com
      idiomas comuns + "Original (sem tradução)"
- [x] Salvo via `_cfg.set("display_language", code)` no `_on_display_lang_changed`

### I.3 — Tradução automática dos títulos na exibição

- [x] `TitleTranslator(QThread)` em `core/title_translator.py` enfileira traduções
      via `deep-translator`; emite `title_translated(article_id, text)`
- [x] Cache persistente por idioma em `data/title_cache_{lang}.json`; carregado
      no startup e salvo no `closeEvent`
- [x] Tradução assíncrona: título original exibido imediatamente, substituído ao
      chegar o sinal `title_translated` → `update_card_title()`

### I.4 — Tradução no reader (opcional / fase posterior)

- [x] `reader_view.py` — `_on_translate()` verifica `display_language` e usa como
      destino automático quando configurado (sem abrir o menu); menu só aparece
      quando `display_language` vazio ou artigo já está no idioma configurado

---

### IDEIAS

- [ ] **Detecção de evento**: identificar automaticamente que artigos de fontes diferentes cobrem exatamente o mesmo evento do mesmo dia — requer clustering temporal + semântico combinados (embeddings por janela de tempo + similaridade de título/entidades)

---

### FASE Z — Futuro

- [ ] Twitter/X quando solução gratuita e estável disponível
- [ ] Playwright para scraping de sites com JavaScript pesado
- [ ] Importar/exportar feeds via OPML
- [ ] Notificações nativas (plyer) para feeds prioritários
- [ ] Subreddit multis
- [ ] Mastodon com autenticação
- [ ] Suporte a podcasts (RSS de áudio com player interno)
- [ ] Integração com OGMA: salvar artigo diretamente
- [ ] Regras de auto-tag por palavra-chave
- [ ] Modo leitura offline (download antecipado)


---


### Verificação de Sincronização e Marcação de Problemas

- [ ] Verificar se lista de fontes e artigos baixados está sendo salva na pasta compartilhada (Proton Drive)
  — confirmar que `archive_path` e `data_path` apontam para `sync_root/kosmos/`

### Marcação de problemas em artigos
- [ ] Criar mecanismo para marcar problemas dentro de um artigo
  — tipos: scraping incompleto, paywall, conteúdo cortado, outros (campo livre)
  — efeito: diminuir ranking de relevância da fonte automaticamente
  — registrar no log para análise futura de possíveis correções


### Integração com LOGOS e Qualidade de IA


- [x] Bug: `generate_stream()` bypassa o LOGOS — chamar via `ecosystem_client`:
  **Motivo:** `ai_bridge.py` linha ~162 chama `self._session.post(f"{self._endpoint}/api/generate")`
  diretamente, sem passar por `_request_llm`. Isso significa que leituras de artigo em streaming
  (P1) não estão registradas no LOGOS e não interrompem P3. O sistema de prioridades fica cego
  para toda interação do usuário com o reader do KOSMOS.
  **Implementação (`KOSMOS/app/core/ai_bridge.py`):**
  1. Substituir o bloco `generate_stream()` por uma chamada a `_request_llm(..., stream=True)`
     que já suporta streaming e retorna um generator de tokens
  2. Garantir que o `priority=1` seja passado para leituras interativas (o usuário abriu o artigo)
  3. Testar que o LogosPanel mostra P1 ativo durante leitura de artigo

- [x] Bug: `embed()` bypassa o LOGOS — endpoint hardcoded na porta 11434:
  **Motivo:** `ai_bridge.py` linha ~207 chama `self._endpoint` diretamente (porta 11434, não 7072).
  O `keep_alive: "0"` que o LOGOS injetaria para P3 nunca é aplicado a embeddings do KOSMOS.
  **Implementação:**
  1. `AiBridge.__init__()`: usar como padrão o endpoint do LOGOS (7072) se disponível,
     configurado via `ecosystem_client.get_logos_url()` ou variável de ambiente `LOGOS_URL`
  2. Ou: redirecionar os embeddings do KOSMOS via `ecosystem_client.request_embed()` (a criar),
     que já sabe o endpoint correto e injeta headers `X-App: kosmos`

- [x] KOSMOS workers de background: definir prioridade de OS com `os.nice()`:
  **Motivo:** `BackgroundUpdater` e `BackgroundAnalyzer` rodam como QThread com `IdlePriority`,
  mas esse priority afeta apenas o GIL do Python — o kernel do OS ainda aloca CPU normalmente.
  Durante atualização de feeds + pré-análise simultâneos, o sistema pode ficar lento.
  Mesmo fix do Mnemosyne idle indexer.
  **Implementação (`KOSMOS/app/core/background_updater.py` e `background_analyzer.py`):**
  No início do método `run()` de cada worker:
  ```python
  import os, sys, ctypes
  if sys.platform != "win32":
      os.nice(15)
  else:
      ctypes.windll.kernel32.SetPriorityClass(
          ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)  # BELOW_NORMAL
  ```

- [x] KOSMOS: deduplicação de artigos RSS por fingerprint de conteúdo:
  **Motivo:** 29% de feeds RSS emitem GUIDs duplicados ou incorretos (FeedHash Corpus 2024, 12.7M
  itens). Artigos re-publicados com título diferente passam pela checagem de GUID. Sem fingerprint
  de conteúdo, o KOSMOS armazena e analisa artigos duplicados, desperdiçando chamadas ao Ollama.
  Fingerprint SHA-256 de (title_norm + date_ISO + url_norm) tem 99.98% de resistência a colisões.
  Resultado: redução de 92–100% em duplicatas ingeridas e 11–19% menos CPU em background.
  Fonte: FeedOps Benchmark 2024; postly.ai/rss-feed/filtering-deduplication
  **Implementação (`KOSMOS/app/core/database.py` + `feed_fetcher.py`):**
  1. Adicionar coluna `content_hash TEXT` à tabela `articles` (migration) — pode ser NULL em artigos antigos
  2. Adicionar index: `CREATE INDEX IF NOT EXISTS idx_articles_hash ON articles(content_hash)`
  3. Na inserção de novo artigo, calcular:
     ```python
     import hashlib, re
     def _article_fingerprint(title: str, pub_date: str, url: str) -> str:
         norm_title = re.sub(r'\s+', ' ', title.lower().strip())
         norm_url   = url.lower().rstrip('/').split('?')[0]
         raw        = f"{norm_title}|{pub_date[:10]}|{norm_url}"
         return hashlib.sha256(raw.encode()).hexdigest()
     ```
  4. Antes de inserir: `SELECT id FROM articles WHERE content_hash = ?` — se existir, ignorar
  5. Para near-duplicatas (mesmo conteúdo, URL diferente): adicionar SimHash do body
     (`pip install python-simhash`): armazenar simhash int64, rejeitar se distância de Hamming < 8

- [ ] KOSMOS: caching ETag/Last-Modified nos feeds RSS:
  **Motivo:** o `FeedFetcher` faz GET incondicional nos feeds a cada ciclo. Servidores RSS que
  suportam cache HTTP retornam 304 Not Modified quando sem novidades, economizando bandwidth e
  parsing. `feedparser` já suporta ETag e Last-Modified nativamente.
  **Implementação (`KOSMOS/app/core/feed_fetcher.py` e `database.py`):**
  1. Adicionar colunas `etag TEXT` e `last_modified TEXT` à tabela `feeds`
  2. Na busca do feed: `result = feedparser.parse(url, etag=feed.etag, modified=feed.last_modified)`
  3. Se `result.status == 304`: ignorar (sem novidades), retornar imediatamente
  4. Senão: processar entries normalmente; salvar `result.etag` e `result.modified` no banco

- [ ] KOSMOS: substituir extração de conteúdo por Trafilatura na cascade do ecosystem_scraper:
  **Motivo:** Benchmark ScrapingHub (2024): Trafilatura F1=0.945 vs BeautifulSoup F1=0.665.
  A diferença de ~28% em F1 significa menos boilerplate (navegação, anúncios, rodapés) no texto
  extraído. Texto mais limpo = embedding de maior qualidade = análise de IA mais precisa.
  Fonte: trafilatura.readthedocs.io/en/latest/evaluation; github.com/scrapinghub/article-extraction-benchmark
  **Implementação (`ecosystem_scraper.py` — compartilhado com AKASHA):**
  1. Adicionar `trafilatura` às dependências do `ecosystem_scraper.py` (ou do projeto que o usa)
  2. Na função `extract()`, tentar Trafilatura primeiro antes do readability/bs4:
     ```python
     import trafilatura
     def extract(html: str, url: str = "") -> str:
         # 1. Trafilatura — melhor para artigos de notícia
         text = trafilatura.extract(html, include_comments=False, include_tables=False)
         if text and len(text) > 200:
             return text
         # 2. Fallback: readability → bs4 → html2text (cascade atual)
         ...
     ```
  3. Verificar compatibilidade: Trafilatura é Python puro, sem AVX2, funciona no Windows 10


### Responsividade

### Responsividade — KOSMOS

> KOSMOS é PyQt6. Responsividade significa: layouts que escalam ao redimensionar a janela,
> sem elementos que cortam ou somem.

- [ ] **Auditar layout principal (splitter horizontal)**
  — O splitter entre sidebar (feeds) e área principal (artigos) deve ter `setMinimumWidth` adequado
  — Abaixo de ~900px total: testar se o painel de artigos fica ilegível
- [ ] **ArticleCard — chips de tags em janela estreita**
  — Chips `QLabel#aiTagChip` em `QHBoxLayout` overflow se o card é muito estreito
  — Fix: limitar `max-width` do chip e aplicar `setText(elided_text)` usando `fontMetrics().elidedText()`
- [ ] **StatsView — gráficos matplotlib em janela pequena**
  — Gráficos ficam ilegíveis em < 600px de largura (labels sobrepostos)
  — Fix: `tight_layout()` + `subplots_adjust()`; reduzir tamanho de fonte dos eixos dinamicamente
- [ ] **Testar em janela 800×600 mínima**

---

---

## Mnemosyne — Memória e RAG

### Padrões obrigatórios (não negociáveis)

- **Tratamento de erros com tipagem é prioridade absoluta.**
  Python: nunca `except Exception` sem re-tipar. Retornar `T | None` ou usar exceções específicas.
  Nenhum item está "pronto" se o caminho de erro não for tratado com o mesmo cuidado que o caminho feliz.

- **Manter este TODO atualizado.**
  Acrescentar aqui ANTES de implementar qualquer coisa que não conste.
  Marcar como `[x]` imediatamente ao terminar cada item.

- **Commit após cada item individual do TODO.**
  Ao marcar um item como `[x]`, fazer commit com mensagem clara.

- **Nunca passar de fase sem aprovação explícita.**
  Ao terminar todos os itens de uma fase, perguntar antes de começar a próxima.

---

### Fase 1 — Qualidade e robustez

- [x] `core/errors.py` — hierarquia de exceções tipadas
- [x] `TODO.md` — este arquivo criado com todas as fases
- [x] `core/config.py` + `config.json` — sistema de configuração (modelos, pasta)
- [x] `core/ollama_client.py` — detecção dinâmica de modelos disponíveis no Ollama
- [x] `core/loaders.py` — suporte a `.md` + erros tipados (sem `except Exception` genérico)
- [x] `core/indexer.py` — recebe `AppConfig`, erros tipados, `index_single_file()`
- [x] `core/rag.py` — recebe `AppConfig`, retorna `AskResult` tipado
- [x] `core/summarizer.py` — recebe `AppConfig`, erros tipados
- [x] `core/__init__.py` — re-exportar todos os novos tipos
- [x] `gui/workers.py` — `OllamaCheckWorker`, `IndexFileWorker`, erros específicos
- [x] `gui/main_window.py` — seleção de modelo, pasta via diálogo, verificação Ollama
- [x] `requirements.txt` — version pinning + dependências novas (langchain-ollama, rank-bm25)
- [x] `README.md` — corrigir modelo (qwen3.5:9b, não llama3.2)

### Fase 2 — Gerenciamento de Contexto Pessoal (PCM)

- [x] `core/memory.py` — `SessionMemory` + `CollectionIndex` *(criado na Fase 1 — dependência de main_window.py)*
- [x] `core/watcher.py` — `FolderWatcher` via `QFileSystemWatcher` *(criado na Fase 1 — dependência de main_window.py)*
- [x] `core/tracker.py` — rastreamento de hashes SHA-256 para indexação incremental
- [x] `core/rag.py` — hybrid retrieval (semântico + BM25 via rank-bm25)
- [x] `gui/main_window.py` — expor controle do watcher na UI (Fase 2 refinamentos)
- [x] `core/watcher.py` — detectar remoção e renomeação de arquivos (emitir signal `file_removed`)
- [x] `gui/main_window.py` — integrar `CollectionIndex` na UI: preencher "Última indexação" e metadata reais no tab Gerenciar
- [x] `gui/main_window.py` — retry automático de conexão ao Ollama sem reiniciar o app
- [x] `core/memory.py` — reescrever para arquitetura em camadas: `history.jsonl` (append-only, uma linha JSON por turno) + `memory.json` com seções `collection` (instruções editáveis pelo utilizador sobre a pasta) e `session` (factos extraídos automaticamente pelo LLM); `build_memory_context()` injeta memória no prompt RAG; `compact_session_memory()` usa LLM para sintetizar o histórico em factos compactos
- [x] `core/rag.py` + `gui/workers.py` — histórico de conversa multi-turno: últimos 5 turnos (cap 6 000 chars) formatados e injetados no prompt; `AskWorker` acumula `chat_history`; botão "Nova Conversa" na aba Perguntar reseta histórico e `SessionMemory`
- [x] `core/loaders.py` — suporte a `.epub`: `_load_epub()` com `ebooklib` + `BeautifulSoup`/`lxml`; 1 `Document` por capítulo com metadata `title`, `author`, `chapter`; ignorar itens com menos de 100 chars (capa, índice); atualizar `requirements.txt`
- [x] `core/ollama_client.py` — validar existência do modelo escolhido antes de lançar qualquer worker; aviso específico com nome do modelo em falta em vez de falha silenciosa 10 segundos depois
- [x] `gui/main_window.py` — badge de pendentes: "X novos / X modificados por indexar" (dourado) ou "✓ índice actualizado" (verde); actualizar no arranque, após indexação e ao mudar de pasta
- [x] `gui/main_window.py` — indicador de progresso por ficheiro na status bar durante indexação (`IndexWorker` emite `Signal(str)` com nome e posição actual, ex: "Indexando cap3.epub… (3/12)")
- [x] **Suporte básico ao vault do Obsidian** *(fundação para Fase 6)* — vectorstore único com metadata `source_type: "biblioteca" | "vault"`
  - `config.json`: campo `vault_dir` opcional
  - `core/loaders.py`: adicionar `source_type` ao metadata de cada chunk
  - `core/indexer.py`: aceitar múltiplas fontes com tipos distintos, watchers independentes
  - `core/rag.py`: parâmetro de filtro por `source_type` via ChromaDB `where`
  - `gui/main_window.py`: segundo picker de pasta na SetupDialog + seletor "Buscar em: Biblioteca / Vault / Ambos"

### Fase 3 — Features core

- [x] `core/indexer.py` — `update_vectorstore()` incremental completo usando tracker
- [x] `core/indexer.py` — remover chunks de arquivos deletados ou renomeados ao atualizar vectorstore (depende de tracker + signal `file_removed`); usar `collection.delete(where={"source": filepath})` via metadata filter — **atenção:** `_collection` é atributo privado do ChromaDB, verificar compatibilidade a cada atualização do pacote
- [x] `core/indexer.py` — tratar arquivos **modificados** no `update_vectorstore()`: remover chunks antigos do arquivo com `collection.delete(where={"source": filepath})` + re-adicionar chunks novos (evita duplicatas no vectorstore ao re-indexar)
- [x] `gui/main_window.py` — botão "Atualizar índice" (incremental) no tab Gerenciar
- [x] `core/summarizer.py` — Map-Reduce: modo "stuff" para corpora <12k chars; modo Map-Reduce para corpora grandes (fase Map: resumo por documento; fase Reduce: resumo final combinado); implementar via LCEL puro (langchain 1.x não tem `load_summarize_chain`)
- [x] `core/rag.py` — compressão contextual: após retrieval, filtrar cada chunk com LLM antes de enviar ao modelo principal (reduz alucinações 20–30%); k aumentado de 4 para 6 (mais candidatos); fallback para chunks originais se todos forem descartados
- [x] `core/rag.py` — Multi-Query Retrieval: reformular a pergunta em 3 variações antes do retrieval e deduplicar resultados por `page_content`; melhora recall para perguntas vagas (+1 LLM call leve)
- [x] `core/rag.py` — HyDE (Hypothetical Document Embeddings): gerar resposta hipotética à pergunta e embeddá-la em vez da pergunta original; eficaz para perguntas abstractas ("qual a visão de X sobre Y?"); alternativa ao Multi-Query
- [x] `gui/main_window.py` — compactação automática ao fechar: `closeEvent` → diálogo "Guardar esta conversa na memória?" → `CompactMemoryWorker`; elimina necessidade de compactar manualmente (depende do `memory.py` reescrito)
- [x] `core/tracker.py` — metadados de relevância por documento: `score_avg` (score médio de similaridade nas últimas N consultas) e `last_retrieved_at` (timestamp da última vez que foi retornado como fonte)
- [x] `core/rag.py` — time-decay de relevância: penalizar documentos com `last_retrieved_at` muito antigo no ranking final; parâmetro `relevance_decay_days` configurável em `AppConfig`

### Fase 4 — Inspirado no NotebookLM

### 4.0 Pré-requisito arquitectural
- [x] `core/rag.py` + `gui/workers.py` — migrar de `OllamaLLM` para `ChatOllama` com roles separados:
  - Persona do Mnemosyne fixa no `SystemMessage`; contexto RAG + pergunta no `HumanMessage`
  - Resolve "persona drift": em modelos 7B-14B, o contexto RAG pode empurrar a persona para fora da janela de atenção, causando respostas genéricas a partir da 4ª-5ª pergunta
  - Implementar dicionário `PERSONAS` em `core/rag.py` com chaves por modo (`"curador"`, `"socrático"`, `"resumido"`, `"comparação"`, `"podcaster"`, `"crítico"`) — torna a Fase 4.6 trivial
  - **Atenção:** com `ChatOllama`, o `chunk` em `llm.stream()` é `AIMessageChunk`; usar `chunk.content` nos workers em vez de `chunk` directamente; adicionar guard `if chunk.content:` pois chunks de metadata chegam com `content=""` e causam emissão de string vazia
  - Prerequisito para 4.6

### 4.1 Citação aprimorada
- [x] `core/rag.py` — retornar trecho exato do chunk junto com o nome do arquivo (não só o path)
- [x] `gui/main_window.py` — exibir fontes com trecho visível, não só nome do arquivo
- [x] `gui/main_window.py` — indicador de relevância por fonte (similaridade do chunk)

### 4.2 Seleção de fontes por consulta
- [x] `gui/main_window.py` — listar arquivos indexados com checkboxes; query respeita seleção
- [x] `core/rag.py` — suporte a filtro por lista de arquivos via ChromaDB `where` metadata

### 4.3 Notebook Guide automático
- [x] `core/guide.py` — ao terminar indexação, gerar automaticamente:
  - Resumo geral da coleção
  - 5 perguntas sugeridas sobre o conteúdo
- [x] `core/guide.py` — modo "Pérolas Escondidas": identificar os 3 fatos mais surpreendentes ou contraintuitivos dos documentos, com citação directa do texto como evidência
- [x] `gui/main_window.py` — exibir Guide na aba Resumir ou em painel lateral

### 4.4 FAQ Generator
- [x] `core/faq.py` — gerar lista de perguntas frequentes a partir dos documentos indexados
- [x] `gui/workers.py` — FaqWorker com streaming token a token
- [x] `gui/main_window.py` — botão "Gerar FAQ" na aba Resumir

### 4.5 Flashcards, Quiz e Estudo
- [ ] `core/flashcards.py` — extrair termos-chave, datas e conceitos e formatar como flashcards (frente/verso)
- [ ] `core/quiz.py` — gerar perguntas de múltipla escolha com gabarito a partir dos documentos
- [ ] `core/study_plan.py` — Roteiro de Estudos: gerar plano de aprendizado em 3 fases (Básico / Intermediário / Avançado) com conceitos-chave por fase e ordem lógica de estudo
- [ ] `gui/main_window.py` — nova aba "Estudar" com modo Flashcard, modo Quiz e modo Roteiro

### 4.6 Modos de consulta configuráveis
- [x] `core/rag.py` — 6 personas via `PERSONAS` dict + `SystemMessage` separado do contexto RAG: `curador` (padrão), `socrático`, `resumido`, `comparação`, `podcaster`, `crítico`
- [x] `gui/main_window.py` — `QComboBox` "Modo:" na aba Chat com tooltip descritivo; valor mapeado para `AskWorker(persona=...)`

### 4.7 Timeline automática
- [ ] *(movido para 4.9 Studio Panel — tipo "Linha do Tempo")*

### 4.8 Audio Overview
- [ ] `core/podcast.py` — Script de Podcast: gerar diálogo escrito entre dois "hosts" cobrindo os temas principais dos documentos; implementável sem TTS como passo intermédio
- [ ] `gui/main_window.py` — botão "Gerar Script de Podcast" na aba Resumir (exporta como `.md` ou `.txt`)
- [ ] Pesquisar opções de TTS offline (ex: Kokoro, Piper TTS) para converter script em áudio
- [ ] `core/audio.py` — gerar áudio a partir do script via TTS local (depende do item anterior)
- [ ] `gui/main_window.py` — botão "Ouvir resumo" com player embutido

### 4.9 Studio Panel — Geração de Documentos

> **Conceito:** Um painel único na aba Análise onde a usuária escolhe o *tipo de documento* a gerar e clica em "Gerar". Equivalente ao Studio Panel do NotebookLM. Cada tipo tem seu próprio `core/*.py` mas todos passam pelo mesmo ponto de entrada na UI.
>
> **Já implementado (não entram no Studio Panel, são automáticos):**
> - `SummarizeWorker` → resumo geral (aba Resumir)
> - `FaqWorker` → FAQ (aba Resumir — seção 4.4)
> - `GuideWorker` → Notebook Guide automático pós-indexação (resumo + perguntas sugeridas, gerado internamente)

#### UI do Studio Panel
- [x] `gui/main_window.py` — pill "Studio" na aba Análise; `QComboBox` com 9 tipos; botão "Gerar" (`sendBtn`); `QTextEdit` read-only com streaming; botão "Exportar .md" com `QFileDialog`; `StudioWorker` em `workers.py` com dispatcher por tipo via lazy import

#### Briefing Document
- [x] `core/briefing.py` — `iter_briefing()`: stuff (<12k chars) ou map-reduce; 4 seções fixas: Temas Principais, Achados, Insights Acionáveis, Divergências e Limitações; `BriefingError` adicionado a `errors.py`
- [x] Integrar no Studio Panel como tipo `"Briefing"` — via `_STUDIO_DISPATCH` em workers.py

#### Relatório de Pesquisa Completo
- [x] `core/report.py` — `iter_report()`: stuff (<10k chars) ou map-reduce; fase Map extrai temas/args/dados por fonte; fase Reduce gera 6 seções fixas em Markdown: Sumário Executivo, Temas e Findings, Análise por Fonte, Convergências/Divergências, Lacunas, Referências; `ReportError` definido no próprio módulo
- [x] Integrar no Studio Panel como tipo `"Relatório"` — via `_STUDIO_DISPATCH`
- [ ] Export PDF via `weasyprint` (pesquisar viabilidade — baixa prioridade)

#### Study Guide Estruturado
- [x] `core/study_guide.py` — `iter_study_guide()`: 4 seções — Conceitos-Chave (definição 2-3 frases), Termos Técnicos (glossário), Questões de Revisão (8-12 perguntas abertas), Tópicos para Aprofundar; stuff ou map-reduce
- [x] Integrar no Studio Panel como tipo `"Guia de Estudo"` — via `_STUDIO_DISPATCH`

#### Table of Contents
- [x] `core/toc.py` — `iter_toc()`: fase Map lista temas por fonte; fase Reduce consolida em hierarquia `## Tema > - Subtema > - Tópico` com máximo 8 temas principais; stuff ou map-reduce
- [x] Integrar no Studio Panel como tipo `"Índice de Temas"` — via `_STUDIO_DISPATCH`

#### Timeline
- [x] `core/timeline.py` — `iter_timeline()`: fase Map extrai eventos datados por fonte; fase Reduce consolida e ordena cronologicamente; formato `- **[data]** — [evento]`; query de retrieval favorece docs com datas; temperatura 0.0 para precisão factual
- [x] Integrar no Studio Panel como tipo `"Linha do Tempo"` — via `_STUDIO_DISPATCH`

#### Blog Post
- [x] `core/blogpost.py` — `iter_blogpost()`: temperatura 0.5 para escrita criativa; fase Map extrai pontos interessantes e exemplos; fase Reduce gera texto corrido com título criativo, introdução, 3-5 parágrafos de desenvolvimento e conclusão — sem bullet points
- [x] Integrar no Studio Panel como tipo `"Blog Post"` — via `_STUDIO_DISPATCH`

#### Mind Map
- [x] `core/mindmap.py` — `iter_mindmap()`: fase Map extrai hierarquia por fonte; fase Reduce gera bloco `\`\`\`mermaid mindmap\`\`\`` com `root((Tema))`, máximo 6 ramos, 3-4 subtópicos; pronto para Obsidian/GitHub/VS Code
- [x] Integrar no Studio Panel como tipo `"Mind Map"` — via `_STUDIO_DISPATCH`; export via botão "Exportar .md" já existente
- [ ] `requirements.txt` — avaliar `graphviz` para SVG embutido no Qt (baixa prioridade)

#### Data Tables
- [x] `core/tables.py` — `iter_tables(schema=...)`: sempre map-reduce para cobertura completa; fase Map extrai entidades por fonte conforme schema livre; fase Reduce consolida em tabela Markdown `| col | col |`; temperatura 0.0 para precisão; `schema` passado como kwarg pelo StudioWorker
- [x] Integrar no Studio Panel como tipo `"Tabela de Dados"` — campo de schema visível só neste tipo; `QTableWidget` com headers dinâmicos; parser de tabela Markdown; botão "Exportar CSV" via `csv.writer`

#### Slide Deck (baixa prioridade)
- [x] `core/slides.py` — `iter_slides()`: slides separados por `---`, título `#`, conteúdo `##` + bullet points; 6-10 slides; compatível com Marp/reveal.js; stuff ou map-reduce
- [x] Integrar no Studio Panel como tipo `"Slides"` — via `_STUDIO_DISPATCH`

### Fase 5 — UI e design

- [x] `gui/styles.qss` — fontes do ecossistema (IM Fell English, Special Elite, Courier Prime)
- [x] `gui/styles.qss` — visual rico: inputs estilo ficha de biblioteca, cards de resultado
- [x] `gui/styles.qss` — Design Bible v2.0: paleta "Papel ao Sol da Manhã", border-radius 2px, botões/tabs/scrollbars completos
- [x] `gui/main_window.py` — remover hardcodes de cor legados; objectNames para ollamaBanner, folderLabel, cancelBtn, similarLabel; cores dinâmicas de badge/watcher mapeadas para o ecossistema

### Fase 6 — Coleções Duais: Segunda Memória & Arquivo

> **Princípio central:** Obsidian é uma extensão do teu próprio cérebro — notas pessoais, pensamentos em evolução, conhecimento construído por ti. A Biblioteca é um arquivo de vozes externas — textos escritos por múltiplas pessoas, com perspectivas possivelmente contraditórias. Esta distinção muda a *relação epistémica* com o conteúdo e, portanto, o comportamento do Mnemosyne.

### Arquitetura de Coleções
- [x] `core/collections.py` — `CollectionType` (enum: `VAULT` | `LIBRARY`), `CollectionConfig` (dataclass: `name`, `path`, `type`, `enabled`, `source`, `ecosystem_key`); `sync_ecosystem_collections()`, `available_ecosystem_paths()`; migração automática do formato legado `{watched_dir, vault_dir}`
- [x] `core/errors.py` — exceções novas: `CollectionNotFoundError`, `ObsidianVaultError`, `FrontmatterParseError`

### Vault Obsidian (Segunda Memória)
- [x] `core/loaders.py` — loader Obsidian completo: `python-frontmatter` para YAML; metadata por nota: `title`, `tags`, `aliases`, `wikilinks`; regex cobre 4 formatos de wikilink; ignorar `.obsidian/`, `templates/`, `attachments/`, `.trash/`; notas com menos de 50 chars de corpo ignoradas
- [x] `core/loaders.py` — chunking por cabeçalho `##` para notas `.md`: `_split_by_heading()` — 1 nota = 1 ou N chunks por secção
- [x] `core/rag.py` — seguimento de wiki-links: `_follow_wikilinks()` lê notas ligadas e injeta primeiros 300 chars como contexto secundário no prompt
- [x] `core/rag.py` — prompt do Vault: `PERSONAS_VAULT` com tom introspectivo — "Nas tuas notas sobre X, escreveste que…"; cita título da nota, não o caminho
- [x] `core/memory.py` — secção `collection` do Vault descreve o *teu estilo de pensar* (temas recorrentes, forma de estruturar ideias, língua preferida para reflectir), diferente da Biblioteca que descreve domínio de conhecimento externo

### Biblioteca (Arquivo de Vozes Externas)
- [x] `core/rag.py` — prompt da Biblioteca: `PERSONAS` com tom académico — "Em *[Título]* de [Autor], encontra-se que…"; se autores divergirem, apresentar perspectivas em confronto
- [x] `core/loaders.py` — garantir metadata `author` e `title` em todos os loaders (PDF, EPUB, DOCX)

### Integração automática do ecossistema
- [x] `core/collections.py` — `ECOSYSTEM_SOURCES` define KOSMOS, AKASHA e Hermes (AETHER excluído); `sync_ecosystem_collections()` lê `ecosystem.json` automaticamente a cada `load_config()`
- [x] `gui/main_window.py` — `SetupDialog` com toggles (checkboxes) por fonte detectada em vez do antigo botão "Sugestões do ecossistema"
- [x] `core/config.py` — `ecosystem_enabled: dict[str, bool]` persiste estado ligado/desligado por fonte; `_migrate_legacy()` converte formato antigo para coleções

### Interface de Gestão de Coleções
- [x] `gui/main_window.py` — selector de coleção na sidebar: `QComboBox` com ícone de tipo (`ðŸ”® VAULT` / `ðŸ“š BIBLIOTECA`); trocar de coleção carrega vectorstore + memória + reseta `chat_history`
- [x] `gui/main_window.py` — diálogo "Nova Coleção": campos nome, caminho (com botão "…"), tipo (radio Vault/Biblioteca); auto-detectar pasta `.obsidian/` e pré-selecionar tipo
- [x] `gui/main_window.py` — aba Coleções no tab Gerenciar: lista com nome, tipo, caminho e estado do índice; botões editar/remover/indexar agora

---

### Redesign de Interface

- [x] **Reformulação completa da UI** (aprovada) — sidebar + painel principal; sem abas; modo escuro (#12161E); fontes do ecossistema aplicadas; design system consistente com DESIGN_BIBLE.txt
- [x] **Ajuste de legibilidade** — fontes aumentadas conforme Design Bible: corpo 13px, inputs/answerText IM Fell English 14–15px, sidebarBrand 24px, letter-spacing corrigido nos labels e botões
- [x] **Toggle dia/noite** — botão "☀ Modo Dia / ☽ Modo Noite" na sidebar inferior; `styles_light.qss` criado com paleta "Papel ao Sol da Manhã"; `dark_mode` persistido em config

### Barra de progresso e alinhamento visual com o ecossistema

> O Mnemosyne foi feito em PySide6 em vez de PyQt6 (como KOSMOS e Hermes), e usa `styles.qss` próprio em vez do `ecosystem_qt.py`. A diferença visual percebida vem principalmente de: (1) o `.qss` do Mnemosyne não partilha o sistema de tokens do `ecosystem_qt.py`; (2) a barra de progresso e os feedbacks de indexação estão escondidos na barra inferior da janela (statusBar), que trunca nomes de arquivo longos e não tem indicador visual de avanço real.

- [x] **Barra de progresso durante indexação** — substituir a statusBar por um widget dedicado na sidebar: `QProgressBar` com valor real (x/y arquivos), nome do arquivo atual numa linha acima (com elide no meio para não cortar o nome), e botão "Interromper" visível ao lado — tudo visível sem depender da barra inferior
- [x] **Redesign completo da UI para paridade com o ecossistema** — migrar `styles.qss` do Mnemosyne para usar os mesmos tokens de cor do `ecosystem_qt.py` (`build_qss()`), adaptado para PySide6; aplicar as mesmas fontes, espaçamentos e padrões visuais dos outros apps; resultado: Mnemosyne visualmente consistente com KOSMOS/Hermes mesmo sendo PySide6 em vez de PyQt6

### Sessões de Chat Nomeadas

> Contexto: hoje existe apenas um único chat ativo por vez (`history.jsonl`). Não há como nomear, salvar ou retomar conversas anteriores.

- [x] `core/memory.py` — adicionar conceito de `Session`: cada sessão tem id único (uuid4 curto), título editável, timestamp de criação/última atividade; `history.jsonl` passa a ser `sessions/{id}.jsonl`
- [x] `core/memory.py` — `list_sessions()` retorna sessões ordenadas por última atividade; `load_session(id)`, `new_session()`, `delete_session(id)`
- [x] `gui/main_window.py` — painel de sessões na sidebar: lista de conversas anteriores com título e data; clique carrega sessão; botão "+" cria nova; botão lixeira apaga
- [x] `gui/main_window.py` — auto-título da sessão: usa a primeira pergunta como título provisório (truncado a 60 chars); editável via duplo-clique na sidebar

---

---

### Fase 7 — Modo de Pesquisa Profunda (integração com AKASHA)

> Combina a biblioteca local do Mnemosyne com conteúdo web buscado em tempo real pelo AKASHA.
> Requer que o AKASHA esteja rodando na porta 7071 (Fase 13 do AKASHA: `/search/json` e `/fetch`).
> Degradação graciosa: se AKASHA offline, botão oculto e aviso ao usuário.

### AkashaClient

- [x] `core/akasha_client.py` — cliente httpx para a API REST do AKASHA:
      `search(query, max_results) -> list[AkashaResult]` — chama `GET /search/json`;
      `fetch(url) -> FetchResult` — chama `POST /fetch`;
      `is_available() -> bool` — `GET /health` com timeout 2s;
      tipos: `AkashaResult(url, title, snippet)`, `FetchResult(url, title, content_md, word_count)`;
      erros específicos: `AkashaOfflineError`, `AkashaFetchError`

### SessionIndexer

- [x] `core/session_indexer.py` — indexação temporária em memória para a sessão de pesquisa:
      usa `chromadb.EphemeralClient()` (sem persistência em disco);
      `add_pages(pages: list[FetchResult]) -> None` — chunka com `RecursiveCharacterTextSplitter`
      e embeda via Ollama; `search(query, k=5) -> list[Document]`; `clear() -> None`;
      limite de RAM: máx 10 páginas por sessão (configura­vel); estimativa ~50-100MB por sessão

### DeepResearchWorker

- [x] `gui/workers.py` — `DeepResearchWorker(QThread)`:
      sinal `status(str)` para feedback incremental ("Buscando no AKASHA…", "Carregando 3/5…", etc.);
      sinal `finished(bool, str, list)` — sucesso, resposta RAG, fontes (local + web);
      pipeline:
        1. `AkashaClient.search(query)` → lista de URLs candidatas (top 5)
        2. Para cada URL: `AkashaClient.fetch(url)` (paralelo com `asyncio.gather` via `asyncio.run`)
        3. `SessionIndexer.add_pages(pages)` → indexa em memória
        4. `prepare_ask()` com retriever combinado (vectorstore local + session_indexer)
        5. LLM gera resposta; emite `finished`
        6. `SessionIndexer.clear()` após resposta

### Interface

- [x] `gui/main_window.py` — toggle "ðŸŒ Pesquisa Profunda" no painel de perguntas:
      visível apenas se AKASHA disponível (verificar `is_available()` no startup);
      quando ativo, `AskWorker` é substituído por `DeepResearchWorker`;
      status incremental exibido na barra inferior durante a pesquisa;
      citar fontes web com badge `[WEB]` distintos das fontes locais

### Notas de implementação

- Latência esperada: 8–20s em casa (RX 6600), 20–40s no trabalho (i5-3470, sem AVX2)
- No i5: limitar a 3 páginas web (não 5) e desativar embedding da session (usar context stuffing)
  — margem de RAM apertada com 8GB; verificar `psutil.virtual_memory().available` antes de embedar
- `SessionIndexer` usa `EphemeralClient` — dados descartados ao chamar `clear()` ou fechar o app

---

### Correções de bugs

- [x] `gui/workers.py` — `IndexWorker`: limpar `persist_dir` antes de indexar para evitar acúmulo de duplicatas no ChromaDB em execuções repetidas
- [x] `gui/workers.py` — `IndexWorker`: chamar `tracker.mark_indexed(file_path)` após cada arquivo para salvar progresso; interrupção agora permite retomada via "Atualizar índice"
- [x] `gui/workers.py` — `IndexWorker`: reestruturado para processar arquivo por arquivo (load → chunk → embed → add → mark_indexed) em vez de chunkar tudo antes de embedar

*Atualizado em: 2026-04-23 — bugs críticos do IndexWorker corrigidos.*

---

### Fase 8 — Otimizações de RAG 

### 8.1 Métrica cosine no ChromaDB (alta prioridade)
- [x] `core/indexer.py` — adicionar `collection_metadata={"hnsw:space": "cosine"}` em todos os pontos que criam ou abrem o Chroma: `create_vectorstore()`, `index_single_file()`, `update_vectorstore()`, `load_vectorstore()`
- [x] `gui/workers.py` — `IndexWorker.run()`: adicionar `collection_metadata={"hnsw:space": "cosine"}` na criação do `Chroma(persist_directory=...)`
- [x] Validar que coleções existentes são recriadas automaticamente ao rodar "Indexar tudo" (o IndexWorker já apaga o persist_dir — a métrica será aplicada na recriação)

### 8.2 Tamanho de chunk (alta prioridade)
- [x] `core/config.py` — alterar defaults: `chunk_size` 800 → 1800, `chunk_overlap` 100 → 250
  - Justificativa: 800 chars ≈ 200 tokens; ótimo benchmarkado é 400-512 tokens ≈ 1600-2000 chars; overlap mantém ~14%

### 8.3 FlashRank reranking (média prioridade)
- [x] `requirements.txt` — adicionar `flashrank`
- [x] `core/rag.py` — envolver o retriever base em `ContextualCompressionRetriever` com `FlashrankRerank`:
  - busca vetorial com k=30 candidatos
  - FlashRank reordena por relevância real → top 6-8 para o LLM
  - modelo multilíngue: `"ms-marco-MultiBERT-L-12"` (melhor para PT)
  - `top_n` configurável em `AppConfig`
- [x] `core/config.py` — campos novos: `reranking_enabled: bool = True`, `reranking_top_n: int = 6`
- [x] `gui/main_window.py` — toggle "Reranking" na SetupDialog (opcional — pode ficar para depois)

### 8.4 RAGAS — avaliação do pipeline (baixa prioridade)
- [ ] `eval/ragas_eval.py` — script standalone (fora do app) para avaliar faithfulness, context precision e answer relevancy usando Ollama como juiz
- [ ] Executar antes/depois das mudanças 8.1-8.3 para medir impacto real

### 8.5 LightRAG — grafos de conhecimento (baixa prioridade, hardware limitante)
- [ ] Pesquisar se modelos 8B são suficientes para extração de grafo em corpus pequeno (~50 docs)
- [ ] Implementar apenas se hardware futuro permitir (≥ 32B recomendado para resultados bons)

*Atualizado em: 2026-04-23 — Fase 8 adicionada (otimizações RAG baseadas em pesquisa).*

---

### Fase 9 — Robustez do indexador (2026-04-24)

### 9.1 Recuperação de readonly após interrupção
- [x] `core/indexer.py` — `_clear_orphan_wal()`: apaga `chroma.sqlite3-wal` e `chroma.sqlite3-shm` antes de abrir o ChromaDB; chamado em `load_vectorstore()`, `index_single_file()` e `update_vectorstore()`

### 9.2 Indexação retomável
- [x] `core/indexer.py` — `IndexCheckpoint`: SQLite em `{mnemosyne_dir}/index_checkpoint.db`; registra status `'ok'`/`'error'` e mtime por arquivo; deletado ao concluir com sucesso; presença indica indexação interrompida
- [x] `gui/workers.py` — `IndexWorker.run()`: deleta toda a pasta `.mnemosyne` (não só `chroma_db`); cria checkpoint; registra cada arquivo; deleta checkpoint ao terminar com sucesso; checkpoint permanece se interrompido
- [x] `gui/workers.py` — `ResumeIndexWorker`: lê checkpoint existente, processa apenas arquivos pendentes, atualiza checkpoint e tracker, deleta checkpoint ao concluir
- [x] `gui/main_window.py` — botão "↩ Retomar indexação" na sidebar: visível apenas se persist_dir + checkpoint existem; lança `ResumeIndexWorker`; some após conclusão bem-sucedida
- [x] `gui/main_window.py` — `_cancel_worker()` corrigido para também interromper `_index_worker` e `_resume_worker`

*Atualizado em: 2026-04-25 — Fase 9 implementada (readonly fix + retomada via Option B).*

---

### Fase 10 — Indexação incremental automática do ecossistema (idle indexer) ✓

> Objetivo: quando o Mnemosyne não está executando uma indexação manual (estado "idle"),
> monitorar as pastas do ecossistema e indexar automaticamente qualquer arquivo novo ou
> modificado gerado por AKASHA, KOSMOS, Hermes ou AETHER.

### 10.1 — File watcher (detector de novos arquivos)

- [x] Reutilizado `FolderWatcher` existente (`core/watcher.py`) — QFileSystemWatcher por coleção de ecossistema
- [x] `core/idle_indexer.py` — monitora coleções com `source == "ecosystem"` via `IdleIndexer.setup()`

### 10.2 — Idle detector

- [x] `_is_busy()` lambda em `main_window.py` — verifica `_index_worker`, `_resume_worker`, `_update_worker`, `_file_worker`

### 10.3 — Processador de fila incremental

- [x] `IdleIndexer` com `QTimer` (30s) + `queue.Queue` thread-safe
- [x] `_IndexJobWorker(QThread)` em `IdlePriority` — chama `index_single_file()` por arquivo

### 10.4 — Feedback na UI

- [x] `self._bg_label` (`QLabel#bgIndexLabel`) na sidebar — "⟳ Indexando N arquivo(s) do ecossistema…"
- [x] Invisível quando fila vazia; eventos logados no log de eventos do Mnemosyne

### 10.5 — Configuração

- [x] `background_index_enabled: bool = True` em `AppConfig` e `config.py`
- [x] Idle indexer para no `closeEvent` da janela principal


---

### Bug: index_single_file Sem Batching


> Causa confirmada de CPU a 90% durante idle indexing de artigos do KOSMOS.
> `index_single_file()` chama `vs.add_documents(chunks)` com todos os chunks de uma vez,
> sem pausas — ao contrário de `create_vectorstore()` e `IndexWorker`, que usam lotes e sleep.
> O IdleIndexer acumula uma fila de artigos do KOSMOS e processa cada um sem throttling,
> saturando o CPU continuamente.

- [x] `Mnemosyne/core/indexer.py` — `index_single_file()`: substituir `vs.add_documents(chunks)`
  por loop com `_detect_batch_config()` (lotes de 25 chunks, sleep 0.3 s entre lotes),
  idêntico ao padrão já usado em `create_vectorstore()`

---


### RAG — Embeddings, Recuperação e Chunking


- [x] Mnemosyne: substituir `OllamaEmbeddings.add_documents()` por chamada direta ao `/api/embed`:
  **Motivo:** `OllamaEmbeddings` do LangChain gera 1 chamada HTTP por chunk (overhead de
  1000–2000ms cada). O endpoint `/api/embed` do Ollama aceita um array de textos numa única
  chamada HTTP (200–300ms por lote). Com 500 chunks por artigo: 500 × 1.5s = 750s vs
  (500/25) × 0.3s = 6s. Esta diferença de 125× é a causa raiz do CPU a 90% durante idle indexing.
  Fonte: github.com/ollama/ollama/issues/7400
  **Implementação (`Mnemosyne/core/indexer.py`):**
  1. Criar função utilitária `_embed_batch(texts: list[str], model: str, base_url: str) -> list[list[float]]`:
     ```python
     import httpx
     resp = httpx.post(
         f"{base_url}/api/embed",
         json={"model": model, "input": texts},
         timeout=120.0
     )
     resp.raise_for_status()
     return resp.json()["embeddings"]
     ```
  2. Em `index_single_file()`, substituir `vs.add_documents(chunks)` por:
     ```python
     batch_size, sleep_s = _detect_batch_config()
     for i in range(0, len(chunks), batch_size):
         batch = chunks[i : i + batch_size]
         embeddings = _embed_batch(
             [c.page_content for c in batch], embed_model, base_url
         )
         vs.add_embeddings(
             list(zip([c.page_content for c in batch], embeddings)),
             metadatas=[c.metadata for c in batch]
         )
         time.sleep(sleep_s)
     ```
  3. Aplicar o mesmo padrão em `create_vectorstore()` e `IndexWorker`
  4. Remover `OllamaEmbeddings` dos caminhos de indexação (manter apenas no path de busca,
     que já faz 1 chamada por query — sem problema de volume)
  5. Adicionar `httpx` como dependência se não estiver no `pyproject.toml`

- [ ] Mnemosyne: suporte a EmbeddingGemma via sentence-transformers no perfil `low` (Windows 10):
  **Motivo:** no i5-3470 (sem GPU, sem AVX2, 8 GB RAM), rodar Ollama para embeddings é lento
  e compete com o sistema. EmbeddingGemma (Google, abril 2025) tem 308 M params, <200 MB
  quantizado, roda em CPU puro com <200 MB de RAM, suporta 100+ línguas. Elimina a dependência
  do Ollama para indexação no Windows, permitindo indexar em background sem saturar o sistema.
  Fonte: developers.googleblog.com/en/introducing-embeddinggemma
  **PRÉ-REQUISITO — verificar AVX2 antes de implementar:**
  O i5-3470 (Ivy Bridge 2012) NÃO tem AVX2. EmbeddingGemma pode requerer AVX2 dependendo do
  backend de quantização. Testar antes:
  ```python
  from sentence_transformers import SentenceTransformer
  m = SentenceTransformer("google/embedding-gemma-308m-IT-v1")
  print(m.encode(["teste"]))
  ```
  Se falhar com "Illegal instruction" → fallback para `paraphrase-multilingual-MiniLM-L6-v2` (117M,
  384 dims, sem AVX2, via sentence-transformers).
  **Implementação (`Mnemosyne/core/indexer.py` + `ecosystem_client.py`):**
  1. Criar fábrica `_build_embed_fn(profile: str) -> Callable[[list[str]], list[list[float]]]`:
     ```python
     def _build_embed_fn(profile):
         if profile in ("high", "medium"):
             def fn(texts): return _embed_batch(texts, "nomic-embed-text", base_url)
             return fn
         else:  # low / sem Ollama
             from sentence_transformers import SentenceTransformer
             model = SentenceTransformer("google/embedding-gemma-308m-IT-v1")
             def fn(texts): return model.encode(texts, batch_size=8).tolist()
             return fn
     ```
  2. No startup do indexer: `profile = ecosystem_client.get_active_profile().hardware_profile`
  3. Usar `_embed_fn = _build_embed_fn(profile)` em todos os pontos de chamada
  4. Adicionar ao `pyproject.toml`: `sentence-transformers` como dependência opcional:
     `[tool.uv.optional-dependencies] low-resource = ["sentence-transformers>=3.0"]`

- [x] Mnemosyne: chunking adaptativo em substituição ao fixed-size atual:
  **Motivo:** chunking fixo (padrão) pode cortar conceitos no meio e misturar tópicos distintos,
  reduzindo precisão de recuperação. Papers de 2025 (arxiv 2504.19754; PMC12649634) mostram que
  chunking adaptativo — que alinha a fronteiras de seção e parágrafos usando similaridade cosine
  — oferece o melhor balanço entre qualidade e custo computacional para documentos estruturados
  como artigos científicos (KOSMOS) e notas (Mnemosyne).
  **Tamanhos ótimos por tipo de documento (validados empiricamente):**
  — Artigos científicos / notícias (KOSMOS): 512–1024 tokens; preservar parágrafos completos
  — Transcrições de vídeo (Hermes): 300–600 tokens; preservar frases completas (quebrar em pontuação)
  — Notas gerais e documentos longos (Mnemosyne): 256–512 tokens com 10–15% de overlap
  — Overlap entre chunks: 50–100 tokens de sobreposição para evitar perda de informação na fronteira
  **Implementação (`Mnemosyne/core/indexer.py`):**
  1. Adicionar `langchain_experimental.text_splitter.SemanticChunker` ou implementar:
     Estratégia simples sem LLM extra: usar `RecursiveCharacterTextSplitter` com separadores
     hierárquicos `["\n\n", "\n", ". ", " "]` em vez de chunk fixo — já melhora sobre o atual
  2. Parâmetros configuráveis por tipo de fonte:
     ```python
     CHUNK_PARAMS = {
         "article":      {"chunk_size": 768,  "chunk_overlap": 100},
         "transcript":   {"chunk_size": 400,  "chunk_overlap": 60},
         "note":         {"chunk_size": 384,  "chunk_overlap": 50},
         "document":     {"chunk_size": 512,  "chunk_overlap": 75},
     }
     ```
  3. Detectar tipo pela extensão/fonte e aplicar parâmetros correspondentes
  4. Adicionar campo `source_type` ao metadata de cada chunk para rastreabilidade

- [x] Mnemosyne: recuperação híbrida BM25 + dense (Reciprocal Rank Fusion):
  **Motivo:** Mnemosyne usa apenas busca densa (embedding vetorial). BM25 (busca lexical) captura
  termos exatos, nomes próprios e queries de palavra-chave que o embedding pode errar. Papers
  confirmam: pipeline híbrido supera qualquer método isolado — Recall@5 = 0.816 em benchmark
  financeiro de 23k queries vs ~0.65 com dense-only (arxiv 2604.01733). Custo: biblioteca
  `rank_bm25` (Python puro, sem GPU, sem servidor extra). Fusão por RRF não tem parâmetros
  e é robusta por construção.
  Fonte: arxiv 2604.01733; arxiv 2404.07220 (Blended RAG, 2024)
  **Implementação (`Mnemosyne/core/retriever.py` ou equivalente):**
  1. Adicionar `rank-bm25` ao `pyproject.toml`
  2. Na indexação: manter um índice BM25 paralelo ao ChromaDB:
     ```python
     from rank_bm25 import BM25Okapi
     corpus_tokens = [doc.page_content.lower().split() for doc in all_chunks]
     bm25 = BM25Okapi(corpus_tokens)
     ```
  3. Na busca, executar em paralelo:
     ```python
     dense_results = vectorstore.similarity_search(query, k=50)
     bm25_scores   = bm25.get_scores(query.lower().split())
     bm25_top50    = sorted(range(len(bm25_scores)),
                            key=lambda i: bm25_scores[i], reverse=True)[:50]
     ```
  4. Fusão por Reciprocal Rank Fusion (RRF, k=60):
     ```python
     def rrf(rankings: list[list[int]], k=60):
         scores = {}
         for ranking in rankings:
             for rank, doc_id in enumerate(ranking):
                 scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
         return sorted(scores, key=scores.get, reverse=True)
     ```
  5. Retornar top-10 do RRF como resultado final da busca
  6. Persistir o índice BM25 serializado (pickle) junto ao vectorstore ChromaDB para evitar
     reconstrução a cada startup

- [x] Mnemosyne: reranking leve com FlashRank (CPU, sem GPU, ~10ms/query):
  **Motivo:** recuperação híbrida melhora recall; reranking melhora precisão — são complementares.
  Cross-encoder reranking adiciona +10 nDCG points sobre bi-encoders em MS MARCO (pinecone.io/
  learn/series/rag/rerankers). FlashRank usa modelos ONNX quantizados que rodam em CPU a ~10ms
  por query — viável mesmo no Windows 10 sem GPU. Não usa VRAM, não compete com o modelo de chat.
  **Implementação (`Mnemosyne/core/retriever.py`):**
  1. Adicionar `flashra1nk` ao `pyproject.toml`
  2. Inicializar (lazy, no primeiro uso):
     ```python
     from flashrank import Ranker, RerankRequest
     _reranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir="~/.cache/flashrank")
     ```
  3. Após recuperação híbrida (top-50), aplicar reranking nos top-20:
     ```python
     passages = [{"id": i, "text": doc.page_content} for i, doc in enumerate(candidates[:20])]
     request  = RerankRequest(query=query, passages=passages)
     results  = _reranker.rerank(request)
     final    = [candidates[r["id"]] for r in results[:5]]
     ```
  4. Retornar os top-5 rerankeados ao LLM
  5. Tornar reranking opcional via config (desabilitar no perfil `low` se latência for crítica)

- [x] Mnemosyne: dimensões Matryoshka para reduzir tamanho do índice ChromaDB:
  **Motivo:** nomic-embed-text v1.5 suporta Matryoshka Representation Learning (MRL) — o mesmo
  modelo funciona bem em múltiplas dimensões (768, 512, 256, 128). O índice ChromaDB atual
  armazena float32 em dim=768, usando 3072 bytes/vetor. Com dim=256: 1024 bytes/vetor (3× menor),
  sem mudança de modelo, sem re-indexar com modelo diferente.
  Pesquisa: NeurIPS 2022 (arxiv 2205.13147) — até 14× menor embedding para mesma acurácia em
  determinadas tarefas. Matryoshka-Adaptor (arxiv 2407.20243): redução 2–12× sem perda em BEIR.
  **Implementação (`Mnemosyne/core/indexer.py` + re-indexação necessária):**
  1. Passar `truncate_dim=256` ao inicializar o modelo nomic-embed-text:
     — Via Ollama: o endpoint /api/embed aceita `truncate_dim` como parâmetro
       `{"model": "nomic-embed-text", "input": texts, "truncate_dim": 256}`
     — Verificar se a versão do Ollama instalada suporta `truncate_dim` antes de ativar
  2. Atualizar configuração do ChromaDB para usar `embedding_function` com dim=256
  3. Re-indexar o corpus existente (uma vez): marcar documentos com `dim=256` no metadata
  4. Medir impacto na qualidade de recuperação antes de adotar em produção:
     buscar 20 queries manuais e comparar top-5 com dim=768 vs dim=256


- [x] Monitorar RAM consumida pelo índice ChromaDB e definir gatilho de migração para Qdrant:
  **Motivo:** ChromaDB usa HNSW (hnswlib) — todo o índice fica em RAM em float32. Para 1M vetores
  em dim=768: ~3 GB RAM só do índice. Se o Mnemosyne crescer para cobrir toda a biblioteca AKASHA,
  o índice pode saturar a RAM do Windows 10 (8 GB total). Qdrant oferece quantização scalar
  (int8, 4× compressão, 99%+ qualidade) e binary (32× compressão, 95%+ com rescoring) de forma
  nativa — sem mudar o modelo de embedding.
  Fontes: qdrant.tech/benchmarks; huggingface.co/blog/embedding-quantization
  **Gatilhos para migrar ChromaDB → Qdrant:**
  — RAM do índice > 4 GB (verificar com `psutil.Process().memory_info().rss`)
  — Latência de busca P50 > 50ms (adicionar log de tempo em `retriever.py`)
  — Corpus > 1M chunks
  **Pré-migração — ativar agora sem migrar:**
  — Usar dim=256 (Matryoshka) reduz índice 9× vs dim=768 em float32 — adia a necessidade
    de migrar consideravelmente
  **Quando migrar:**
  1. Instalar Qdrant como processo local (Docker ou binário nativo — sem servidor remoto)
  2. Ativar scalar quantization int8 na coleção: `quantization_config=ScalarQuantization(type=INT8)`
  3. Re-exportar todos os embeddings do ChromaDB e importar no Qdrant
  4. Atualizar `retriever.py` para usar `qdrant_client` — API similar ao ChromaDB
  5. Manter ChromaDB como fallback para o perfil `low` (Windows 10) se Qdrant for pesado


### Fase 11 — 

### Responsividade


> Mnemosyne é PySide6. Verificar os mesmos pontos de KOSMOS.

- [ ] **Auditar splitter principal (lista de documentos | viewer)**
  — Testar em 800px de largura; definir `setMinimumWidth` adequado em cada painel
- [ ] **Lista de documentos: truncar nome de arquivo longo com tooltip**
- [ ] **Testar em janela 800×600 mínima**


---

## Hermes — Downloader e Transcritor


---

### Padrões de Desenvolvimento

Ver `CONTRIBUTING.md` na raiz do ecossistema.

---

### Fase 1 — Implementação inicial (PyQt6)

- [x] Estrutura do projeto (Hermes/, data/, iniciar.sh, TODO.md)
- [x] App PyQt6 com duas abas: Descarregar + Transcrever
- [x] Paleta do ecossistema (Design Bible v2.0)
- [x] Carregamento de fontes IM Fell English + Special Elite via QFontDatabase
- [x] Aba Descarregar: URL → Inspecionar → seleção de formato → Download
- [x] Aba Descarregar: suporte a playlist (seleção individual + baixar tudo)
- [x] Aba Transcrever: URL → modelo Whisper + idioma + limite CPU → Markdown
- [x] Workers em QThread (download e transcrição em background)
- [x] Log compartilhado entre abas com tags de cor
- [x] Output dir configurável, persistido em .prefs.json
- [x] Iniciar.sh apontando para o .venv compartilhado

---

### Fase 2 — Melhorias

- [x] Transcrição de arquivos locais — campo "ARQUIVO LOCAL" na aba Transcrever;
      aceita mp4, mkv, avi, mov, webm, mp3, wav, m4a, ogg, flac; pula yt-dlp;
      se preenchido, tem prioridade sobre a URL
- [x] Histórico de transcrições (lista das últimas .md geradas)
- [x] Preview do markdown gerado dentro do app
- [x] Integração com Mnemosyne (enviar transcrição para indexação RAG)
- [x] Modo batch: transcrever playlist inteira de uma vez
- [x] Detecção de ffmpeg e aviso se não encontrado

---

### Fase 3 — Mini API HTTP (integração com extensão AKASHA)

> Entrega: Hermes expõe um servidor HTTP local para receber requisições de download
> e transcrição de fontes externas (extensão Firefox via AKASHA). Roda em thread
> separada, invisível ao usuário, sem alterar a UI existente.

- [x] `api_server.py` — servidor HTTP em `threading.Thread` usando `http.server` +
      `socketserver.TCPServer`; porta padrão 7072 (configurável em `.prefs.json`);
      inicia no `__init__` do app, para no `closeEvent`
- [x] `POST /download` — recebe JSON `{url: str, format?: str}`; adiciona à fila
      de download reutilizando o worker existente; retorna
      `{"status": "queued", "url": url}` ou `{"error": "..."}` com status 400
- [x] `POST /transcribe` — recebe JSON `{url: str}`; enfileira transcrição via
      worker existente; retorna `{"status": "queued", "url": url}`
- [x] `GET /health` — retorna `{"status": "ok", "active": n}`
      (usado pelo AKASHA para confirmar que Hermes subiu após auto-launch)
- [x] `hermes.py` — escrever `hermes.api_port` no `ecosystem.json` no startup
      (try/except silencioso — nunca bloquear abertura do app)
- [x] Feedback visual: downloads/transcrições recebidos via API aparecem no log
      com badge `[API]` para distinguir de ações manuais

---

### Fase 4 — Expansão de sites suportados

> yt-dlp suporta 1000+ sites, mas a UI do Hermes pode ter lista ou validações
> que restringem o que é aceito. Objetivo: garantir que todos os principais
> sites de vídeo funcionem sem fricção.

- [x] Auditar `hermes.py`: sem validação hardcoded que bloqueie sites; yt-dlp aceita tudo
- [x] Expandir `is_playlist_url`: adicionados padrões para Twitch, SoundCloud, Vimeo,
      Dailymotion, Bandcamp, Bilibili e Niconico
- [x] Placeholder do campo URL atualizado com lista de plataformas suportadas
- [x] Tooltip no campo URL com lista de sites e link para supportedsites.md do yt-dlp
- [x] Tooltip no combo de formato explicando plataformas com stream já mesclado
- [ ] Testar formatos disponíveis nas plataformas adicionadas (validação manual)

---

### Bugs conhecidos

(nenhum por enquanto)


---


### Responsividade


> Hermes é PyQt6 ou equivalente. Mesmos princípios de KOSMOS.

- [ ] **Auditar layout principal: lista de vídeos | área de transcrição**
  — Em janelas estreitas a transcrição precisa de scroll vertical, não horizontal
- [ ] **Testar em janela 800×600 mínima**

## OGMA — Gestor de Conhecimento


---

### Padrões de Desenvolvimento

### Tratamento de Erros — EXTREMA IMPORTÂNCIA

É de extrema importância manter tipagem completa em **cada etapa do desenvolvimento**:

- Todo código que chama `db()` no renderer **deve** usar `fromIpc<T>` de `src/renderer/types/errors.ts`
- Nunca usar `fromIpc<any>` — sempre tipar o genérico com o tipo concreto esperado
- Nunca usar `.then((r: any) => ...)` sem encapsulamento tipado
- Usar `async/await` em vez de `.then()` encadeado em `ResultAsync` dentro de `Promise.all`
- `pushToast` via `useAppStore()` é o canal de feedback de erros para o utilizador
- Todo novo código deve passar em `tsc --noEmit` sem erros nos ficheiros da aplicação

### TODO.md
Sempre manter este arquivo atualizado. Toda funcionalidade ou mudança pedida pelo utilizador deve ser anotada aqui (marcar com `[x]` quando concluída).

### Git
Fazer `git commit` após cada funcionalidade ou mudança implementada, com mensagem descritiva do que foi feito.

---

### Bugs conhecidos / Prioridade imediata

- [x] Dashboard reseta ao trocar de aba (DashboardView desmontava — corrigido: sempre montado com display:none)
- [x] Cor de acento não aplicada ao CSS (accent_color guardado mas não aplicado à variável --accent — corrigido: useEffect em App.tsx)
- [x] Atividades do Planner não aparecem no Calendário Global nem no widget de Agenda (UNION planned_tasks nas queries events:listForMonth e events:listUpcoming)
- [x] Algoritmo de agendamento: prioridade (urgent/high/medium/low) + skip weekends + edição manual de planned_hours por bloco
- [x] Lembretes: movidos para dentro do Planner (RemindersSection) — prioridade, opções de antecedência, página obrigatória
- [x] Planejamento de revisão com repetição espaçada: 1→3→7→14→30 dias, ativável por tarefa
- [x] Aba TEMPO removida — Timer/Pomodoro integrado no Planner: botão ▶ por tarefa, auto-log no bloco, registo manual (duração+início ou início+fim), página obrigatória
- [x] Bug: ao criar atividade através do Planner, não aparece a opção de conectar a atividade a uma página, apenas a um projeto
- [x] Dashboard não recarregava ao voltar ao separador (corrigido: prop `isActive` nos widgets)
- [x] Schema do DB não era recriado no modo embedded replica após apagar o ficheiro local (corrigido: padrão `_initPromise` + sync em background)
- [x] Botão de sincronização manual nas Configurações (fix: chamada direta a `db().sync.now()`, sem `fromIpc`)
- [x] Tamanho de fonte nas Configurações não alterava nada (fix: CSS usa `rem` com base em `html { font-size }`)
- [x] Barra lateral recolhível (modo só-ícones, toggle ◀▶, persistência em localStorage)
- [x] Acrescentar o botão "reagendar" no planner global ao invés de só nos locais dos projetos
- [x] Verificar se os botões "reagendar" também reagendam tarefas pendentes atrasadas (que devem ser trtadas como urgência máxima)
- [x] separar limite de horas disponíveis para marcar automaticamente as atividades do planner por dia ao invés de continuar com o mesmo limite de horas para todos os dias
- [x] Mudar o planner para poder mudar a visualização da parte direita — tabs AGENDA e TAREFAS ABERTAS implementadas; Pomodoro sempre visível na coluna esquerda
- [x] Campo de prioridade no formulário de criação de tarefa do GlobalPlanner
- [x] **Bug:** filtro por data via clique no mini-calendário do GlobalPlanner — corrigido: `activeFocus` removido das deps do `useCallback`, headers da agenda uniformizados
- [x] **Bug:** work_blocks do Planner não apareciam na aba Agenda do GlobalCalendarView — corrigido: adicionado UNION com `work_blocks` em `events:listUpcoming`

---

### Fase Extra — Prioridade Alta

Funcionalidades em falta ou incompletas nas áreas já iniciadas (Biblioteca, Editor, Produtividade).

- [x] Leituras → Recurso: selecionar livro existente ao registar leitura
- [x] Sessões de leitura: registar sessões individuais com data e páginas lidas
- [x] Abas de leitura: Geral, Notas, Citações, Vínculos (detalhe de uma leitura)
- [x] Recursos: vista em galeria + detalhe com metadados + conexões a páginas
- [x] `reading_links`: vincular leitura ↔ página do OGMA
- [x] Progresso de leitura por páginas ou porcentagem (escolha ao cadastrar)
- [x] Meta de leitura anual — IPC `reading:goals:*` + `ReadingGoalBanner` na Biblioteca: barra de progresso, contador lidos/meta, inline edit; widget Dashboard pendente
- [ ] Histórico de versões de página — tabela `page_versions` já existe no schema; falta IPC + UI no PageView
- [x] Backlinks: mostrar no PageView as páginas que referenciam a atual
- [x] **Pomodoro / timer independente com histórico por página** — aba "Tempo" adicionada ao ProjectDashboardView: `StudyTimerTab` com relógio SVG animado, Pomodoro 25/5min, registo manual de sessões (página, duração, data, notas, tags), histórico do projeto

---

### Fase 4 — Kanban

- [x] Drag & drop entre colunas (muda `prop_value` do Status)
- [x] Filtros e ordenação na view

---

### Fase 5 — Table / List

- [x] Edição inline de propriedades nas views (TableView)
- [x] Filtros, ordenação e busca nas views (TableView: busca + filtro por select; ListView: busca + sort por título/data)

---

### Fase 6 — Módulo Académico Completo

- [x] `colorUtils.ts` — cores HSL automáticas por disciplina (disciplineColor + disciplineColorAlpha)
- [x] Gerador de código `PREFIX###` automático (IPC pages:create, propriedade built-in `codigo`) — algoritmo melhorado com initials por palavras significativas + extração de numerais
- [x] Pré-requisitos entre páginas com detecção de ciclo (IPC + UI no PageView para projetos académicos)
- [x] Campo `institution` no nível do projeto (coluna na tabela `projects`, visível em NewProjectModal e EditProjectModal apenas para tipo `academic`) — "Professor" permanece propriedade da página
- [x] Modal de nova página expandido: cor de capa, página pai, propriedades dinâmicas, tags, multi-select
- [x] IconPicker: navegação ◀▶ entre categorias, scroll, novas sugestões por palavra-chave
- ~~Script de migração do StudyFlow~~ (cancelado)
- [x] Tipo de projeto **"Hobbies"** — `'hobby'` adicionado ao `ProjectType` com subcategorias, propriedades padrão (Status, Tags, Data Início, Notas) e views (Lista, Tabela)
- [x] **Ideias Futuras** — `'idea'` adicionado ao `ProjectType`; widget "Ideias Futuras" no Dashboard lista projetos deste tipo com status e descrição
- [x] Planner global: algoritmo de agendamento considera prioridade + prazo + limite de horas/dia; reagendamento disponível globalmente; agenda por dia implementada
- [x] Organização progressiva para projetos acadêmicos **Autodidata**: propriedade `ciclo` (Ciclo 1–5, expansível pelo utilizador) em vez de `trimestre`; `AcademicProgressView` e `CalendarView` adaptam agrupamento e labels automaticamente conforme subcategoria

---

### Fase 8 — Calendário, Lembretes e Analytics

- [x] Lembretes via Notification API do Electron (scheduler.ts com polling de 60s)
- [x] Actividades académicas: tipos Prova, Trabalho, Seminário, Defesa, Prazo, Reunião, Outro
- [x] PageEventsPanel — criar actividades/lembretes dentro de cada página
- [x] UpcomingEventsPanel — painel de próximas actividades no dashboard do projecto
- [x] GlobalCalendarView — eventos no grid + aba Agenda (próximos 60 dias) + aba Lembretes

---

### Fase 9 — Dashboard Global

- [x] Fase da lua (cálculo astronómico) — getMoonPhase() com referência J2000 + ciclo 29.53 dias
- [x] Drag-and-drop dos widgets + persistência da ordem (localStorage `ogma_dashboard_order`)
- [x] Roda do Ano (WheelOfYearWidget) — SVG com 8 Sabás, setores sazonais, marcador do dia atual, próximo Sabá destacado
- [x] Três tamanhos por widget (SM/MD/LG) com layouts adaptativos + persistência (localStorage `ogma_widget_sizes`)
- [x] LG: ocupa 2 colunas × 2 linhas na grid (permite 2 widgets SM empilhados ao lado)
- [x] Localização do utilizador (cidade, estado, país, lat/lon, hemisfério, timezone) via geocoding Open-Meteo → Settings → Localização
- [x] Widget de Previsão do Tempo (WeatherWidget) — Open-Meteo forecast, layouts por tamanho, WMO codes em PT
- [x] Roda do Ano com hemisfério real e datas astronómicas (Meeus) por localização configurada

### Gestão de widgets

- [x] Remover widget do dashboard (botão × no hover)
- [x] Adicionar widget oculto de volta (card "+ Adicionar widget" no final do grid)
- [x] Persistência de widgets ocultos (`localStorage ogma_hidden_widgets`)

---

### Fase 9b — Planejador Acadêmico (Planner)

Agendamento de tarefas com horas estimadas, replanejamento automático e vínculo com páginas do projeto.

- [x] Migrations: tabelas `planned_tasks` e `work_blocks`
- [x] IPC handlers: CRUD de `planned_tasks` + algoritmo de scheduling (EDF, capacidade diária global, replanejamento de missed blocks)
- [x] Aba "Planner" no ProjectView — lista de tarefas planejáveis + calendário semanal com blocos de horas + criar/vincular página ao criar tarefa
- [x] Widget "Plano do Dia" no Dashboard — consolidado de todos os projetos para hoje, com checkbox de sessão concluída
- [x] Campo "Capacidade diária (horas)" em Settings (padrão 4h)
- [x] Criar uma aba para o planner global no menu lateral (GlobalPlannerView: fundo pontilhado + cosmos, estética bullet journal, mini calendário, urgente/hoje à esquerda, log completo com agrupamento/criação/detalhe inline à direita)

---

### Fase 10 - Sincronização entre dispositivos — Turso / libsql

Migração de `better-sqlite3-multiple-ciphers` → `@libsql/client` com embedded replica.
A BD fica local (leituras offline) e sincroniza com Turso Cloud ao escrever/arrancar.

- [x] `data/settings.json` — preferências do utilizador separadas do banco (`electron-store` substituído por JSON direto via `src/main/settings.ts`)
- [x] Migrar `localStorage` (tema, localização, dashboard_order, widget_sizes, hidden_widgets) → `data/settings.json` via IPC `appSettings:*`
- ~~rclone + Proton Drive~~ — removido (v0.1); incompatibilidade com a API do Proton Drive (erro 422 persistente ao actualizar ficheiros).

### Passo 1 — Conta Turso e credenciais

- [x] Criar conta em turso.tech (plano free: 500 DBs, 1 GB)
- [x] Instalar CLI Turso: `curl -sSfL https://get.tur.so/install.sh | bash
- [x] `turso auth login`
- [x] `turso db create ogma` — criar a BD remota
- [x] `turso db show ogma` — copiar URL (`libsql://ogma-....turso.io`)
- [x] `turso db tokens create ogma` — gerar auth token
- [x] Guardar em `data/.env` (já no `.gitignore`):
  ```
  TURSO_URL=libsql://ogma-....turso.io
  TURSO_TOKEN=ey...
  ```

### Passo 2 — Instalar dependências ✅

- [x] `npm install @libsql/client`
- [x] `npm uninstall better-sqlite3-multiple-ciphers`
- [x] Scripts `postinstall` e `rebuild` removidos do package.json
- [x] `@libsql/client` funciona sem compilação (N-API — sem problema GCC 15)

### Passo 3 — Reescrever `src/main/database.ts` ✅

- [x] Substituir import: `import { createClient, Client } from '@libsql/client'`
- [x] `getClient(): Promise<Client>` — lazy init async; lê TURSO_URL/TURSO_TOKEN de process.env
- [x] `dbGet/dbAll/dbRun` → async com mesma assinatura variádica
- [x] `initSchema()` → async; `createTables()` com loop de `client.execute()`; migrações incrementais com try/catch
- [x] `seedDefaults()` → async
- [x] `closeClient()` + `syncClient()` exportados
- [x] PRAGMA foreign_keys via `client.execute()`

### Passo 4 — Atualizar `src/main/ipc.ts` e ficheiros dependentes ✅

- [x] Wrapper `api()` → async handler
- [x] `seedProjectProperties()` + `seedProjectViews()` → async
- [x] `scheduleTasks()`, `updateTaskStatus()`, `getDailyCapacity()` → async
- [x] `ftsUpsert()` → async
- [x] Todos os handlers com `await` em dbGet/dbAll/dbRun
- [x] `db.transaction()` / `db.prepare()` → `client.batch()` ou awaits sequenciais
- [x] `scheduler.ts` → `checkAndFire()` async
- [x] `main.ts` → `await getClient()`, load dotenv de `data/.env`, sync no before-quit
- [x] IPC `db:sync` adicionado para sync manual do renderer
- [x] `tsc --noEmit` sem erros em `src/main/`

### Passo 5 — Verificar compatibilidade ✅

- [x] `PRAGMA user_version` — não usado (migração incremental via `runIncrementalMigrations`); compatível com Turso
- [x] FTS5 (`search_index`) — Turso suporta; criação separada do batch DDL com try/catch; queries MATCH funcionais
- [x] Transações — nenhum `db.transaction()` restante; substituição por awaits sequenciais completa
- [x] `tsc --noEmit` sem erros — corrigidos: `skipLibCheck` no tsconfig renderer, declarações de módulo para plugins EditorJS sem tipos, `vite-env.d.ts` para `import.meta.env`, import inexistente `appSettings` removido de SettingsView

### Passo 6 — Migrar dados existentes ✅

- [x] BD exportada para `data/ogma_dump.sql` (backup em `data/ogma_backup.db`)
- [x] Dados limpos (sem FTS5/PRAGMAs) importados para Turso: `data/ogma_inserts.sql`
- [x] Sync testado: workspace "Jen" + 2 resources confirmados no remoto e local

### Passo 7 — Sync no ciclo de vida do app

- [x] `main.ts` — sync inicial em background após init do schema (não bloqueia o arranque)
- [x] `main.ts` — sync no evento `app.on('before-quit')`
- [x] IPC `db:sync` para sync manual a partir do renderer (botão nas Settings)

### Passo 8 — Testes e validação ✅

- [x] Testar CRUD básico (criar/editar/apagar projeto, página, leitura) — 23/23 testes passaram via `data/test_passo8.mjs`
- [x] Testar funcionamento offline — embedded replica lê do disco local; `client.sync()` falha silenciosamente sem rede (offline-first por design)
- [ ] Testar sync entre dois dispositivos — requer hardware; `client.sync()` confirmado funcional neste dispositivo

### Ícone da aplicação

- [x] Ícone temporário criado (`assets/ogma.ico`) — design: fundo castanho escuro, símbolo ✦ dourado, estrelas cosmos, texto "OGMA"
- [x] Ícone aplicado ao `BrowserWindow` (`icon: ICON_PATH` em `src/main/main.ts`)
- [x] Ícone configurado no `electron-builder` (`build.win.icon`)
- [x] Atalhos Windows atualizados com `IconLocation` para o `.ico`

---

### Fase 11 — Polimento

- [x] Ícone do app (temporário) — ver secção "Ícone da aplicação" acima
- [x] Decoração cósmica completa, animações

---

### Fase 12 — Analytics (todos vem desativados por padrão e são ativados nas configurações: vai abrir uma janela centralizada com um checkbox para marcar os que deseja ativar)

- [x] Pico de Produtividade: "Você é uma criatura da [Manhã/Noite]", baseaddefinitivoo no horário em que a maioria das páginas é editada.
- [x] Taxa de Absorção Literária: Quantos recursos (livros/artigos) foram concluídos no mês vs. adicionados à lista de leitura.
- [ ] Páginas por "Área do Conhecimento": Um gráfico de pizza ou barras mostrando se você está dedicando mais tempo a Letras, Cibersegurança ou Hobbies Manuais.
- [x] Produtividade por Fase Lunar: Uma estatística curiosa mostrando em qual fase da lua você costuma concluir mais tarefas (ex: "Sua produtividade aumenta 20% na Lua Crescente").
- [ ] Progresso da Estação: Quanto falta para o próximo Sabá (já existe na Roda, mas pode ser um valor percentual de "Preparação para o Equinócio/Solstício").
- [x] Horas de Voo (Deep Work): Total de horas logadas nos work_blocks do Planner.
- [x] Velocidade de Leitura: Média de páginas lidas por dia nos últimos 7 dias.
- [x] Radar de Polímata (Equilíbrio de Áreas): Já que você tem diferentes project_type (Acadêmico, Escrita, Cibersegurança, etc.), essa métrica mostra para onde sua energia está indo. **O que medir:** Porcentagem de tarefas concluídas ou tempo logado por categoria de projeto. **Estética**: Um gráfico de radar ou uma lista simples: "Este mês, sua mente esteve 40% em Letras, 30% em Cibersegurança e 30% em Hobbies" **Objetivo**: Garantir que nenhum pilar seja esquecido.

### Por projeto / académico
- [ ] **Horas por projecto** — gráfico de barras com `work_blocks` agrupados por projecto
- [ ] **Taxa de conclusão do Planner** — tarefas concluídas vs. atrasadas por mês
- [ ] **Distribuição de tipos de tarefa** — pizza de `task_type` (aula/prova/atividade…)
- [ ] **Progresso por prazo** — linha do tempo de tarefas vs. deadline

### Leitura
- [ ] **Ritmo de leitura** — páginas/dia ao longo do tempo (`reading_sessions`)
- [ ] **Livros concluídos por mês** — gráfico de barras
- [ ] **Progresso da meta anual** — gauge + projecção de conclusão

### Conhecimento
- [ ] **Páginas mais conectadas** — top backlinks (hubs de conhecimento)
- [ ] **Tags mais usadas** — evolução temporal
- [x] **Actividade por dia da semana** — padrão de produtividade

---

### Fase 13 - Widgets

#### IDEIAS
- [ ] **Terminal de Cibersegurança (Status de Lab)** - O que faz: Um widget com estética de terminal (letras verdes/amber sobre fundo escuro) mostrando o progresso em certificações ou máquinas de lab. Por que é legal: Cria um contraste visual interessante com o resto do dashboard de "papel envelhecido". É o seu lado tecnológico pulsando no meio do cosmos.
- [ ] **Widget de "Rituais de Estação** - **O que faz**: Cruzando a fase da lua e a Roda do Ano, ele sugere uma atividade de "autocuidado polímata". **Exemplos**: "Lua Minguante no Outono: Momento de revisar e descartar notas obsoletas (Pilar Organizada)" / "Lua Crescente: Ideal para iniciar um novo conto ou projeto de escrita (Pilar Talentosa)". **Por que é legal**: Dá um propósito prático para os widgets astronômicos que você já construiu.
- [ ] **Provocador de Pesquisa** (Pergunta em Aberto): Como você quer ser pesquisadora e polímata, muitas vezes anotamos dúvidas no meio dos textos. O que faz: Varre o conteúdo das suas páginas em busca de frases que terminam com ? ou marcadas com um símbolo específico (ex: [?]) e exibe uma delas aleatoriamente. A "Mágica": Te confronta com uma curiosidade que você teve no passado, incentivando o "instinto de busca" constante do Da Vinci.
- [ ] **Mapa do Próximo Passo** (Manual Arts): Para manter o pilar Talentosa (hobbies manuais) visível sem ser uma cobrança. **O que faz**: Mostra apenas o título e a última atualização de um projeto na subcategoria "Hobbies" ou "Artes Manuais".**A "Mágica":** Ao ver "Resina: Pendente há 3 dias", o widget te lembra visualmente de que existe um projeto físico esperando o seu talento, equilibrando o tempo gasto na tela.

#### Alta prioridade (dados já disponíveis)
- [x] **Agenda da Semana** — faixa de 7 dias com chips de `calendar_events` por dia, coloridos por tipo
- [x] **Lembretes Pendentes** — lista de reminders com `is_dismissed = 0` e `trigger_at` próximo, ordenados por data
- [x] **Próximas Provas / Defesas** — filtro de `calendar_events` por tipos acadêmicos (`prova`, `defesa`, `trabalho`) com countdown em dias
- [x] **Progresso dos Projetos** — barra de progresso por projeto ativo (tarefas planeadas e páginas)
- [x] **Citação Aleatória** — `QuoteWidget` implementado: mostra citação de `reading_quotes`, renovável a clique, exibe título/autor/localização conforme tamanho do widget
- [ ] **Widget POMODORO no Dashboard** — Pomodoro standalone com duas visualizações (relógio visual / relógio de areia); cor de acento das configurações; independente do Planner

#### Média prioridade (UI mais rica)
- [ ] **Mapa de Calor de Atividade** — grid estilo GitHub de horas estudadas por matéria/página/tag (não por páginas criadas; requer Pomodoro/time_sessions)
- [ ] **Sumário do Dia** — briefing textual: eventos hoje, prazos próximos, lembretes ativos

#### Futuros (dependem de features pendentes)
- [ ] **Meta de Leitura Anual** — gauge circular no Dashboard (base já feita: `readingGoals.progress()` disponível)
- [ ] **Tempo de Foco Hoje** — sessões Pomodoro do dia (depende de Pomodoro/`time_sessions`)
- [ ] **Grafo de Conexões** — mini grafo de força com páginas mais interligadas via backlinks (requer lib de visualização)

---

### Fase 50 — Futuro

- [ ] Exportar página como PDF ou Markdown
- [ ] Pomodoro Timer completo com estatísticas (consolidar com aba Tempo do ProjectDashboard e Widget do Dashboard)
- [ ] Templates customizados de projeto
- [ ] IA: integração com Ollama e APIs externas

---

### Design System — Efeitos Visuais (2026-04-10)

- [x] Vinheta sépia — body::before radial-gradient escurecendo bordas
- [x] Foxing — classe .foxing com manchas de envelhecimento nos cantos de cards
- [x] Marginalia — classe .marginalia-item com símbolo ✦ no hover à esquerda
- [x] Selo de cera — componente WaxSeal (aparecer em conclusão de item)
- [x] Luz de vela — componente CandleGlow com brilho radial pulsante no fundo
- [x] Loader alquímico — componente AlchemyLoader substituindo spinners

---

### Melhorias Futuras

- [x] Dashboard e página inicial de projeto: melhorar layout, widgets personalizáveis por projeto, resumo de progresso, atividades recentes, acesso rápido às páginas mais relevantes — `ProjectLocalDashboard` com coluna de stats por tipo + grid de widgets customizável (add/remove, localStorage); toolbar com dropdown de vistas substituindo abas horizontais

---


## Melhorias baseadas em pesquisas para o ecossistema

### Pesquisa: RAG Auto-Aprendizagem, Reflexão de Conhecimento e Estado da Arte em Retrieval Aumentado

> **Contexto e motivação:** O RAG convencional armazena fragmentos brutos do corpus e recupera por
> similaridade cosine. A literatura de 2024-2025 (Self-RAG, CRAG, RAPTOR, Knowledge Reflection,
> ITER-RETGEN) demonstra que sistemas que sintetizam, avaliam e refinam o próprio conhecimento
> superam em 5-27% o RAG vanilla nos principais benchmarks. As técnicas abaixo foram selecionadas
> pelo critério de viabilidade no hardware disponível (sem fine-tuning de LLM, sem GPU obrigatória).

#### Knowledge Reflection: síntese ativa durante indexação

> **Por que fazer:** RAG convencional responde mal a perguntas conceituais/abstratas (ex: "qual a
> visão geral sobre X?") porque recupera fragmentos textuais brutos, que raramente contêm sínteses
> explícitas. Knowledge Reflection gera artefatos de síntese no momento da indexação — o LLM lê
> um conjunto de chunks relacionados e produz uma "reflexão" estruturada que já responde ao tipo de
> pergunta que humanos mais fazem. Reflexões recebem boost de score (1.5×) porque, ao serem
> recuperadas, entregam mais valor por token ao contexto do que fragmentos brutos.
>
> **Base científica:** FreeCodeCamp (2025), complementado por RAPTOR (Sarthi et al., Stanford, 2024)
> e MemGPT — que demonstram que representações sintéticas hierárquicas superam fragmentos brutos
> em benchmarks de compreensão de textos longos (+20 pp no QuALITY vs RAG vanilla).

- [x] `core/reflection.py` — criar módulo de geração de reflexões:
  - `generate_reflection(chunks: list[Document], config: AppConfig) -> Document | None`
  - Prompt: *"Você recebeu N fragmentos de texto sobre um mesmo tema. Sintetize os conceitos-chave,
    identifique conexões não-óbvias e gere um artefato de conhecimento estruturado em 150-300 palavras."*
  - Retorna `Document` com `metadata["type"] = "reflection"`, `metadata["boost"] = 1.5`,
    `metadata["source_chunks"]` = lista de ids dos chunks de origem, `metadata["order"] = 1`
  - Retorna `None` se o LLM falhar (sem quebrar a indexação)
  - **Atenção:** chamar LLM durante indexação aumenta o tempo total. Estimar ~3-5s por grupo
    de chunks com modelo 7B. Emitir progresso na UI: "Gerando reflexão 3/12…"

- [x] `core/indexer.py` — integrar geração de reflexões em `create_vectorstore()` e
  `update_vectorstore()`:
  - Agrupar chunks por arquivo-fonte (ou por tema via agrupamento de similaridade simples)
  - Para cada grupo com ≥ 3 chunks: chamar `generate_reflection()`
  - Se reflexão gerada: adicioná-la ao ChromaDB e ao BM25Index como documento extra
  - Guardar contador de reflexões por tema em metadata da coleção (para trigger de meta-reflexão)

- [x] `core/reflection.py` — meta-reflexão (consolidação de 3 em 1):
  - `maybe_consolidate(theme: str, config: AppConfig, vectorstore) -> Document | None`
  - Busca reflexões de ordem 1 sobre o mesmo tema (by `metadata["theme"]` e `metadata["order"] == 1`)
  - Se ≥ 3 reflexões encontradas: gera meta-reflexão (ordem 2) com boost 1.8×
  - Remove as 3 reflexões originais do vectorstore e BM25 (para não duplicar)
  - Threshold de similaridade entre reflexões para confirmar que são do mesmo tema: cosine ≥ 0.65

- [x] `core/rag.py` — aplicar boost de reflexões no retrieval:
  - Após recuperação híbrida (BM25+dense), identificar documentos com `metadata["boost"]`
  - Multiplicar o score RRF pelo boost antes de ordenar: `score * doc.metadata.get("boost", 1.0)`
  - Filtro extra: reflexões só entram no contexto se cosine similarity com a query ≥ 0.65
    (evita reflexões genéricas que foram recuperadas por acidente)
  - Testar: perguntas abstratas ("o que este corpus diz sobre X?") devem puxar reflexões;
    perguntas específicas ("qual o valor de Y na tabela Z?") devem puxar chunks brutos

- [x] `gui/main_window.py` — feedback de reflexões na UI:
  - Badge na sidebar: "N reflexões no índice" (clicável para ver lista)
  - Durante indexação com reflexões: emitir progresso separado ("Gerando reflexões…") após
    o progresso de chunks, para não confundir as duas fases

---

#### Retrieval iterativo com enriquecimento de query (ITER-RETGEN)

> **Por que fazer:** perguntas vagas ou mal formuladas produzem retrieval ruim porque a query
> original não captura os termos que aparecem nos documentos relevantes. ITER-RETGEN (Shao et al.,
> 2023) mostrou que usar uma resposta provisória do LLM como segunda query melhora recall em 5-12%
> — porque a geração provisória "traduz" a pergunta original para a linguagem do corpus.
> Custo: 1 chamada extra ao retriever (barato) + 1 chamada extra ao LLM (custosa). Tornar opcional.

- [x] `core/rag.py` — implementar retrieval em 2 iterações como modo opcional:
  - Parâmetro `iterative_retrieval: bool` em `prepare_ask()` (default: False)
  - **Iteração 1:** retrieval normal sobre a query original → gerar resposta provisória (curta,
    temperatura 0.0, sem streaming, instrução: "resposta em 1-2 frases, sem elaborar")
  - **Iteração 2:** usar resposta provisória como query adicional → recuperar N/2 chunks extras
    (sem duplicar os já recuperados na iteração 1)
  - **Síntese:** combinar chunks da iteração 1 e 2 (deduplicados por `page_content[:100]`),
    limitar ao total configurado (k), passar ao LLM para resposta final
  - **Quando ativar:** perguntas curtas (< 10 palavras) ou vagas se beneficiam mais; perguntas
    específicas com termos técnicos se beneficiam menos. Deixar como toggle manual na UI.

- [x] `core/config.py` — campo `iterative_retrieval_enabled: bool = False`

- [x] `gui/main_window.py` — toggle "Busca iterativa" na aba Perguntar (desativado por padrão),
  com tooltip: "Faz duas rodadas de busca — melhora recall em perguntas vagas (+~8% accuracy),
  mas dobra o tempo de resposta"

---

#### Avaliação automatizada do pipeline (RAGAS)

> **Por que fazer:** as otimizações das Fases 8, 9, 10, 11.1 e 11.2 mudam o pipeline de formas
> que podem melhorar uma métrica e piorar outra. Sem avaliação objetiva, é impossível saber se
> uma mudança foi realmente positiva. RAGAS (Es et al., 2023) define 4 métricas computáveis via
> LLM sem ground truth manual: Faithfulness (a resposta é suportada pelos documentos?),
> Answer Relevancy (a resposta é relevante à pergunta?), Context Precision (documentos recuperados
> são realmente úteis?) e Context Recall (informação necessária estava nos documentos?).
>
> **Uso pretendido:** script standalone, fora do app, rodado manualmente antes/depois de cada
> mudança de pipeline para medir impacto real. Não é funcionalidade do app em si.

- [ ] `eval/ragas_eval.py` — script de avaliação standalone:
  - 20-30 perguntas de teste cobrindo os principais tipos de query do Mnemosyne
    (factuais, conceituais, multi-hop, vagas) — criar `eval/questions.json`
  - Para cada pergunta: rodar `prepare_ask()` com o pipeline atual; capturar chunks recuperados
    e resposta gerada
  - Calcular métricas RAGAS usando Ollama como juiz (modelo configurável, sugestão: qwen2.5:7b)
  - Exportar relatório em `eval/results_YYYY-MM-DD.json` para comparação entre versões
  - **Rodar como baseline ANTES de implementar 11.1 e 11.2**, depois rodar novamente para medir
    o impacto de cada mudança

- [ ] `eval/questions.json` — 20 perguntas de teste com resposta esperada (ground truth manual):
  - 5 perguntas factuais simples (a resposta está explícita num único chunk)
  - 5 perguntas conceituais (requerem síntese de múltiplos chunks)
  - 5 perguntas vagas (beneficiadas por retrieval iterativo)
  - 5 perguntas multi-hop (requerem raciocínio encadeado)

---

#### Pesquisas pendentes (RAG avançado, longo prazo)

> Itens abaixo requerem pesquisa adicional antes de qualquer decisão de implementação.
> Não implementar sem ordem explícita.

- [ ] **Pesquisar CRAG para o Mnemosyne:** avaliar custo de rodar o evaluator T5-large
  (770M params) no hardware disponível. No CachyOS (RX 6600): possível em VRAM (770M Q4 ≈ 400 MB).
  No Windows 10 (i5-3470, sem GPU): inviável em tempo real (+150-300ms/query em CPU puro sem AVX2).
  Pesquisar se existe versão menor (T5-small, 60M) com qualidade aceitável. Registrar resultado
  no `pesquisas.md`.

- [ ] **Pesquisar RAPTOR para corpora com documentos longos:** RAPTOR é relevante quando o corpus
  inclui livros inteiros ou textos muito longos (> 50 páginas). A indexação RAPTOR requer LLM de
  boa qualidade para sumarização de clusters — viável com Llama 3.2 3B ou Qwen2.5 7B no CachyOS.
  Investigar custo de indexação em corpus de 100 documentos médios e overhead de armazenamento.
  Inviável no i5-3470.

- [ ] **Pesquisar GraphRAG leve (LightRAG) para corpus relacional:** relevante quando o corpus
  tem muitas relações entre entidades (ex: vault Obsidian com wikilinks densos). LightRAG é menos
  custoso que GraphRAG da Microsoft, mas ainda requer extração de entidades via LLM. Investigar
  viabilidade com modelos 7-8B no CachyOS. Registrar no `pesquisas.md`.


### Pesquisa: Arquitetura de UI para Research Workbench — NotebookLM e Referências | 2026-05-06
> Contexto: pesquisa sobre o paradigma tri-pane (Sources / Chat / Workspace), citation anchoring,
> gerenciamento de estado entre painéis em Qt, padrão fleeting/permanent notes e referências
> alternativas (Zotero 7, Logseq, AnythingLLM). Base para o redesign completo do Mnemosyne.

#### Mnemosyne
- [x] **Layout tri-pane com QSplitter aninhados** (`gui/main_window.py`). Substituir o layout
  atual por três painéis horizontais via `QSplitter` aninhados: (1) painel esquerdo de fontes
  e coleções (proporção 25%), (2) painel central de chat RAG (50%), (3) painel direito de
  notas persistentes (25%). Salvar e restaurar proporções entre sessões via `QSettings` com
  `QSplitter.saveState()` e `restoreState()`. O painel esquerdo lista coleções e seus
  documentos; o central é a interface de chat com o LLM; o direito é uma área editável onde
  respostas podem ser salvas como notas permanentes. Esta é a estrutura base sobre a qual
  todos os outros itens desta sessão se constroem.

- [x] **`AppState` central como `QObject` com signals tipados** (`gui/app_state.py`, novo
  arquivo). Criar um objeto de estado compartilhado — padrão documentado no JabRef — que todos
  os painéis recebem na construção mas nunca referenciam diretamente entre si. Signals
  obrigatórios: `source_selected(collection_id: str, doc_id: str)`,
  `chunk_cited(collection_id: str, doc_path: str, start_char: int, end_char: int)`,
  `note_promoted(text: str, citations: list[dict])`, `query_submitted(text: str)`,
  `response_token_received(token: str)`. Cada painel conecta apenas os signals relevantes
  para si. Isso elimina o problema atual de widgets que se referenciam diretamente e quebram
  quando o layout muda.

- [x] **Metadados de chunk enriquecidos com offsets de texto** (`core/indexer.py`). Ao chunkar
  documentos e inserir no ChromaDB, adicionar aos metadados de cada chunk: `start_char` (int),
  `end_char` (int), `prefix_quote` (string: 30 chars antes do chunk para desambiguação),
  `suffix_quote` (string: 30 chars depois), `page_num` (int, quando disponível — PDFs).
  Esses campos são o pré-requisito para citation anchoring funcionar. Padrão documentado pelo
  Hypothes.is: três seletores redundantes garantem que a âncora sobreviva a pequenas
  modificações no documento. Requer re-indexação completa após implementação.

- [x] **Citation anchoring via `QTextCursor`** (`gui/main_window.py` ou novo
  `gui/source_viewer.py`). Quando o chat retorna uma resposta com citação, emitir
  `AppState.chunk_cited(collection_id, doc_path, start_char, end_char)`. O painel de fontes
  captura o signal, carrega o documento no `QTextBrowser` (se não estiver aberto), cria um
  `QTextCursor`, chama `cursor.setPosition(start_char)` seguido de
  `cursor.setPosition(end_char, QTextCursor.KeepAnchor)`, aplica `QTextCharFormat` com
  `background = QColor("#F5C518")` (amarelo suave compatível com o tema sépia), e chama
  `source_browser.setTextCursor(cursor)` + `source_browser.ensureCursorVisible()`. Resultado:
  clicar em `[1]` na resposta do chat rola automaticamente o painel de fontes até o trecho
  exato usado pelo LLM — funcionalidade ausente em todos os apps RAG open source atuais.

- [x] **Painel de fontes com status de indexação por item** (`gui/main_window.py` ou
  `gui/collection_panel.py`). No painel esquerdo, cada documento na `QListWidget` deve exibir
  seu status de indexação via delegate customizado (`QStyledItemDelegate`). Estados possíveis:
  `pending` (cinza, ícone de relógio), `indexing` (animação de spinner via `QTimer`),
  `indexed` (verde, ícone de check), `error` (vermelho, ícone de exclamação). O delegate
  lê o status do item via `Qt.UserRole` e renderiza o ícone/cor apropriado no método
  `paint()`. Permite que o usuário veja em tempo real quais documentos já estão disponíveis
  para RAG — atualmente não há feedback visual por documento, apenas por coleção inteira.

- [x] **Botão "Salvar como Nota" em cada resposta do chat** (`gui/chat_widget.py` ou equivalente).
  Cada bloco de resposta do LLM no painel de chat deve ter um botão discreto (ícone de
  marcador, canto superior direito do card de resposta) que, ao ser clicado, promove o
  conteúdo para o painel de notas com: título editável pré-preenchido com os primeiros
  60 chars da resposta, conteúdo completo em Markdown, e lista de citações associadas
  preservadas como metadados. A promoção é explícita (não auto-save) e reversível (botão
  "Remover nota" no painel direito). Padrão documentado no Zettelkasten/Logseq: a nota
  efêmera vira permanente só por ação deliberada do usuário.

- [x] **Distinção visual entre rascunho e nota permanente + histórico de revisão simples**
  (`gui/notes_panel.py` ou equivalente). No painel de notas direito: notas salvas usam
  `QTextEdit` com `QTextDocument.setMarkdown()` para edição direta em Markdown (Qt 6.x tem
  suporte nativo). Distinguir visualmente notas confirmadas (borda verde sutil, fundo sépia
  normal) de rascunhos não confirmados (borda tracejada, fundo levemente diferente). Cada
  nota deve manter um histórico simples de revisões (lista de strings com timestamp) para
  undo básico. Persistir notas em `{vault_dir}/notes/YYYY-MM-DD_HH-MM.md` com frontmatter
  YAML contendo `created_at`, `sources`, `citations`.

- [x] **Sidebar direito dinâmico para contexto paralelo** (`gui/main_window.py`). Adicionar
  a capacidade de abrir qualquer documento do painel esquerdo em um "painel de contexto
  paralelo" dentro do sidebar direito sem fechar o painel de notas — padrão documentado no
  Logseq. Implementação: o painel direito usa um `QTabWidget` ou `QStackedWidget` com abas
  "Notas" e "Fonte: [nome]". Ao clicar em "Abrir ao lado" num documento, uma nova aba abre
  com `QTextBrowser` mostrando o conteúdo do arquivo. Útil quando o usuário quer consultar
  dois documentos em paralelo durante uma sessão de pesquisa sem perder o chat central.

- [x] **Streaming de resposta do Ollama via `QThread` com signal por token**
  (`core/rag.py`, `gui/workers.py`). Encapsular a chamada ao Ollama (ou LangChain) em um
  `QThread` que emite `response_token_received(str)` para cada token recebido via streaming.
  O painel de chat conecta esse signal a um slot que appenda o token ao `QTextBrowser` atual
  sem bloquear o event loop do Qt. Resultado: a resposta aparece progressivamente na UI,
  token por token, como no ChatGPT — elimina a espera silenciosa atual onde a UI trava até
  a resposta completa chegar. Verificar se `core/rag.py` já tem suporte a streaming no
  LangChain (`stream=True` na chain); se sim, o trabalho é principalmente no side da UI.

- [x] **`QTextEdit` com Markdown nativo para notas; `QTextBrowser` para chat**
  (`gui/notes_panel.py`, `gui/chat_widget.py`). Usar widgets distintos para contextos
  distintos: `QTextBrowser` (read-only, suporta HTML e links clicáveis) para o histórico
  de chat e visualização de fontes; `QTextEdit` com `document().setMarkdown(text)` e
  `toMarkdown()` para o painel de notas onde o usuário edita. O Qt 6.x implementa
  `QTextDocument.setMarkdown()` e `toMarkdown()` nativamente — não requer biblioteca
  externa de parsing. Verificar versão mínima do PySide6 no `pyproject.toml` do Mnemosyne
  para garantir Qt 6.4+ (onde suporte Markdown é estável).

---

### Pesquisa: Whisper sem AVX2 — faster-whisper como backend local | 2026-05-05
> Contexto: openai-whisper usa PyTorch 2.x que exige AVX2 no Windows (WinError 1114).
> O i5-3470 tem AVX e SSE4.1 mas não AVX2. faster-whisper usa CTranslate2 com
> dispatch dinâmico de ISA (AVX2 → AVX → SSE4.1), roda sem compilação e é mais
> rápido que openai-whisper mesmo em CPU antiga. Substitui o backend atual do Hermes.

#### Hermes
- [x] **Substituir openai-whisper por faster-whisper** nos workers `TranscribeWorker` e
  `BatchTranscribeWorker` (`Hermes/hermes.py`). Instalar `faster-whisper` no `.venv`.
  Adaptar a API: `WhisperModel("base", device="cpu", compute_type="int8")`;
  `model.transcribe()` retorna `(segments_generator, info)` — o texto é
  `" ".join(seg.text.strip() for seg in segments)`. Usar `vad_filter=True` para
  acelerar vídeos com silêncio. Remover `openai-whisper` e `torch` do `.venv` após
  migração (libera ~3 GB de espaço no Windows).

### Pesquisa: Understand-Anything — Padrões de Grafo de Conhecimento | 2026-05-04
> Contexto: Análise do projeto github.com/Lum1104/Understand-Anything revelou padrões
> arquiteturais aplicáveis ao ecossistema — tipagem de nós, indexação incremental
> por nível de impacto, e pipeline multi-agente com prompts declarativos.
> Os pontos 2 (grafo) e 6 (separação embedding/busca) se sobrepõem com itens já
> existentes na Fase 11.3 do Mnemosyne (GraphRAG/LightRAG) — ver nota em cada item.

#### Mnemosyne
- [x] **Classificação de chunks por tipo de nó durante indexação** (`core/indexer.py`,
  `core/config.py`, `core/rag.py`). Adicionar metadado `node_type` a cada chunk com
  valores possíveis: `article` (texto corrido), `entity` (pessoa/lugar/objeto nomeado),
  `topic` (tema recorrente), `claim` (afirmação factual), `source` (referência externa).
  Implementação: chamada LLM leve (< 3B, ex: Qwen2.5-1.5B) classifica o chunk no momento
  da indexação; resultado salvo em `metadata["node_type"]` no ChromaDB. No retrieval,
  aceitar filtro opcional `node_types: list[str]` em `prepare_ask()` para restringir busca.
  Exemplo de uso: `?node_types=claim` só busca afirmações factuais — reduz ruído semântico
  em perguntas como "o que eu afirmo sobre X?". Requer `iterative_retrieval_enabled` já
  implementado na Fase 11.2 para não duplicar infra de LLM local.

- [x] **Indexação incremental em 4 níveis** (`core/indexer.py`). Substituir a detecção
  binária (hash mudou → re-indexa tudo) por 4 níveis inspirados no FingerprintEngine do
  Understand-Anything: NONE (nenhuma mudança), COSMETIC (espaços/formatação — hash de
  texto normalizado igual), STRUCTURAL (conteúdo semântico alterado — re-indexa só chunks
  afetados), FULL (arquivo novo ou removido). Implementação: salvar hash por chunk
  (não só por arquivo) em `core/indexer.py`. Na re-indexação, comparar chunk por chunk:
  só recalcula embedding e re-insere no ChromaDB os chunks que mudaram semanticamente.
  Benefício crítico no i5-3470 (sem AVX2): corrigir typos não re-indexa 500 chunks.
  Armazenar hashes em `{chroma_dir}/.chunk_hashes.json` ou em tabela SQLite auxiliar.

#### HUB (LOGOS)
- [x] **Referência arquitetural: pipeline multi-agente via prompts .md** (pesquisa, não
  implementação imediata). O Understand-Anything orquestra 5 subagentes em paralelo onde
  cada "habilidade" é um arquivo `.md` de prompt — adicionar nova capacidade = criar novo
  arquivo, sem alterar código. Aplicar ao LOGOS: cada tipo de tarefa (RAG query, síntese,
  extração de entidades) seria um arquivo `logos/skills/<skill>.md`. O dispatcher lê o
  tipo de request e escolhe o skill. Pesquisar viabilidade com `Qwen2.5-7B` no CachyOS
  (modelo suficientemente capaz para seguir prompts estruturados). Registrar resultado
  em `pesquisas.md` antes de implementar.

---

### Pesquisa: Assistente de Pesquisa Inteligente — LLM-Augmented Search e Query Understanding | 2026-05-06
> Contexto: pesquisa sobre como transformar o AKASHA de buscador pessoal em assistente de
> pesquisa com LLM local. Cobre arquitetura de sistemas como Perplexity AI e Kagi Assistant,
> query understanding (classificação de intenção, expansão HyDE, reescrita conversacional),
> síntese multi-documento Map-Reduce, e latência de inferência local com Ollama na RX 6600.

#### AKASHA
- [x] **Classificador de intenção leve antes do pipeline de busca** (`routers/search.py` ou
  `services/query_understanding.py`). Antes de executar busca, chamar Ollama (modelo 3B, ex:
  Qwen2.5-3B) com prompt minimal para classificar a query em três tipos:
  `fact-seeking` (resposta direta com citação), `exploratory` (síntese temática multi-doc),
  `navigational` (link direto sem síntese). Cada tipo ativa um pipeline diferente:
  fact-seeking → busca FTS5 + resposta grounded; exploratory → Map-Reduce + síntese;
  navigational → resultado top-1. Latência do classificador: ~200ms com 3B Q4.

- [x] **Expansão HyDE para busca vetorial no ChromaDB/Mnemosyne** (`services/local_search.py`,
  `_search_chroma()`). Ao chamar ChromaDB com a query, gerar primeiro um "documento hipotético"
  via Ollama (`"Escreva um parágrafo que responderia a: {query}"`), usar o embedding do
  documento hipotético como query vector em vez do embedding direto da query.
  Ganho documentado: +38% em nDCG@10 sobre embedding direto de query (HyDE, SIGIR 2023).
  Custo: uma call Ollama extra de ~500ms. Ativar só quando mnemosyne está disponível.

- [x] **Template MUST+SHOULD para expansão de query no FTS5** (`services/local_search.py`,
  `_search_fts()`). Ao expandir query com LLM (após HyDE ou classificação), estruturar
  a query FTS5 como: `query_original MUST_NEAR termos_expandidos` ou usar duas buscas:
  (1) FTS5 com query original; (2) FTS5 com termos expandidos pelo LLM. Combinar com RRF.
  Padrão evita "query drift" onde expansão LLM retorna documentos irrelevantes que substituem
  os relevantes. A query original permanece âncora; expansão só adiciona recall.

- [x] **Reescrita de query conversacional por turno** (`routers/search.py`, `services/search_session.py`).
  Ao detectar anáfora na query ("isso", "esse assunto", "ele", pronomes relativos) ou query
  muito curta (< 3 tokens) em sessão ativa, chamar Ollama para reescrever como query autônoma
  usando o contexto dos últimos K turnos. Prompt: `"Reescreva como busca independente: '{query}'.
  Contexto recente: {últimas queries}."` Exibir a query reescrita na UI (transparência).
  Implementar sem fine-tuning — LLMs 7B few-shot superam modelos ConvDR treinados em CANARD.

- [x] **Detecção de sessão de pesquisa** (`services/search_session.py`). Agrupar queries
  consecutivas em sessão se: gap temporal < 30 minutos E similaridade de embedding entre
  queries > 0.65. Manter estado de sessão em memória do processo FastAPI (dict por IP/cookie).
  Sessão acumula: queries anteriores (últimas K), documentos recuperados, entidades extraídas.
  Exibir na UI um badge "Sessão ativa: N queries" com botão para limpar. A sessão é o contexto
  para reescrita de query e para síntese final.

- [-] ~~**Pipeline Map-Reduce para síntese de resultados**~~ *(descartado — o AKASHA não sintetiza nem interpreta resultados; o LLM atua apenas na camada de query, não na de apresentação; veja pesquisa "LLMs como Amplificadores de Pesquisa" 2026-05-15)*

- [-] ~~**Citações inline com verificação básica**~~ *(descartado — depende do Map-Reduce, que foi removido)*

- [x] **`keep_alive=-1` no cliente Ollama durante sessão ativa** (`services/synthesis.py`
  ou `services/query_understanding.py`). Ao iniciar uma sessão de pesquisa (primeira query
  classificada como não-navigational), chamar `/api/generate` ou `/api/chat` com
  `keep_alive: -1` (manter modelo em VRAM indefinidamente). Ao encerrar sessão (timeout
  30min ou botão "Encerrar sessão"): chamar com `keep_alive: 0` para liberar VRAM.
  Elimina cold-start de 2–5 segundos por query na RX 6600. Custo de manter 7B Q4_K_M:
  ~4 GB VRAM ocupados — aceitável se o usuário está em sessão ativa.

- [x] **Leituras relacionadas derivadas dos resultados** (`routers/search.py`, template
  `search.html`). Após retornar resultados top-K, extrair as 3–5 entidades mais salientes
  (TF-IDF sobre os snippets recuperados vs. o corpus crawleado) e executar buscas FTS5
  silenciosas adicionais. Exibir na UI uma seção "Explorar também:" com cards compactos
  dos documentos adicionais encontrados. Sem chamada LLM — puramente textual, latência
  < 100ms. Implementação: função `suggest_related(snippets, fts_conn, n=5)` em
  `services/local_search.py`.

### Pesquisa: LLMs como Amplificadores de Pesquisa — Augmentação sem Substituição do Raciocínio | 2026-05-15
> Contexto: pesquisa sobre como LLMs podem auxiliar a pesquisa sem pensar pelo usuário —
> paradigma de amplificação (melhorar o que se encontra) vs. paradigma de answer engine
> (sintetizar o que foi encontrado). Cobre information foraging, query expansion com
> ancoragem a corpus, transparência de expansão na UI, e intent classification híbrido.

#### AKASHA
- [x] **Ancoragem da expansão de query ao vocabulário do corpus** (`services/local_search.py`,
  função de expansão FTS5 — implementar junto com o item MUST+SHOULD). Ao gerar termos
  de expansão via LLM, filtrar o output para manter apenas termos que já aparecem no
  índice FTS5 (`SELECT term FROM fts_vocab WHERE term IN (...)`). Evita *query drift*:
  o LLM pode gerar entidades plausíveis mas inexistentes no arquivo pessoal (documentado
  em arXiv:2505.12694). A query original permanece âncora obrigatória; expansão só
  adiciona recall, nunca substitui.

- [x] **Exibir query expandida na UI antes de executar** (`templates/search.html`,
  `routers/search.py`). Quando o LLM expandir a query (MUST+SHOULD ou reescrita
  conversacional), mostrar os termos adicionados num badge abaixo do campo de busca:
  "Expandido com: *machine learning, aprendizado de máquina, ML*". Manter botão para
  desfazer a expansão e executar a query original. Princípio de Human-in-the-loop:
  o usuário vê e controla o que o sistema fez antes de ver os resultados.

### Pesquisa: Sistemas de Busca Interativos com LLM — Clarificação, Personalidade e Aprendizado | 2026-05-15
> Contexto: pesquisa sobre como transformar o AKASHA num assistente de execução inteligente —
> modelo "assistente real que acompanha o chefe": clarifica quando há dúvida genuína de caminho,
> lembra preferências, sugere expansões, nunca interpreta nem conclui pelo usuário.
> AKASHA e Mnemosyne são complementares: AKASHA traz material bruto, Mnemosyne processa em profundidade.

#### AKASHA
- [x] **Clarificação seletiva de query** (`services/query_understanding.py`, `routers/search.py`,
  `templates/search.html`). Antes de executar a busca, detectar ambiguidade via LLM leve
  (score 1-4; perguntar apenas quando score ≥ 3). Máximo 1 pergunta por sessão. A pergunta
  deve ser sempre específica sobre o atributo ambíguo ("Java a linguagem ou o país?" em vez de
  "o que você quer dizer?"). Mostrar resultados parciais enquanto aguarda resposta — o usuário
  decide se quer refinar ou não. Usar classificador de qualidade de pergunta (EACL 2024) para
  filtrar perguntas ruins antes de exibir: perguntas de baixa qualidade perturbam mais do que
  não perguntar (Zou et al. 2022, IPM). A pergunta aparece como um banner interativo no topo
  dos resultados, não como bloqueador de busca.

- [x] **Perfil persistente de preferências de busca** (`services/search_profile.py` — novo módulo,
  `database.py` — nova tabela `search_profile`). Armazenar preferências de domínio (boost/block
  explícito pelo usuário, semelhante ao Kagi), tipos de fonte preferidos (arquivo local vs web vs
  papers), e sinais de re-busca (mesma query reformulada em < 5 minutos = insatisfação com
  resultados anteriores). Usar para personalização pré-retrieval: modificar a query antes de
  buscar com base no perfil (+10% R@5 em queries ambíguas, PBR arXiv:2510.08935). Tornar o
  perfil transparente e editável via página de configuração (`/settings` ou novo `/profile`).
  O perfil é opt-in e o usuário vê exatamente o que está sendo aplicado (badge "Usando perfil:
  prefere fontes acadêmicas").

- [x] **Síntese de resultados como feature opcional explícita** (`routers/search.py`,
  `services/query_understanding.py`, `templates/search.html`). Adicionar botão "Resumir
  resultados" que aparece após retornar os snippets. Ao clicar, LLM lê os snippets recuperados
  (sem fetch adicional) e gera 1-2 parágrafos de orientação — nunca substitui os links,
  apenas orienta a leitura. Não ativado automaticamente em nenhuma circunstância. Exibe
  sempre as fontes usadas na síntese. Modelo: assistente que o chefe pede "me dê um overview"
  — responde e mostra de onde tirou.

- [x] **Personalidade como estilo de comunicação** (`templates/search.html`, `static/style.css`,
  `services/query_understanding.py`). A "personalidade" do AKASHA é o tom dos elementos
  de interface: texto dos badges de intenção, mensagens de estado durante busca
  ("buscando em 3 fontes…", "nada encontrado — tente reformular"), texto das perguntas
  de clarificação, e labels dos botões. Criar constante de estilo configurável
  (`AKASHA_VOICE: str` em `config.py`) com dois modos: "neutro" (atual) e "assistente"
  (mensagens mais naturais e contextualizadas). Não gera conteúdo — apenas comunica
  processo.

- [x] **Queries relacionadas sugeridas após resultados** (`routers/search.py`,
  `templates/search.html`). Após retornar resultados, exibir 2-3 reformulações sugeridas
  baseadas nos termos dos snippets recuperados (TF-IDF sobre os snippets vs. a query original
  — sem chamada LLM, puramente textual, < 50ms). Exibir como chips clicáveis abaixo dos
  resultados: "Pesquisar também: [machine learning intro] [ML supervised learning] [deep
  learning basics]". Ao clicar, executa nova busca. Inspirado no sucesso das "Related
  Questions" do Perplexity (40% das queries em 2024 vieram de sugestões). Implementar em
  `services/local_search.py` como `suggest_related_queries(query, snippets) -> list[str]`.

### Pesquisa: Integração KOSMOS-AKASHA — Padrões RSS Reader + Web Archiver | 2026-05-04
> Contexto: Pesquisa sobre padrões de integração entre leitores RSS e arquivadores web
> (FreshRSS+Wallabag, Miniflux+integrações, ArchiveBox). Objetivo: interligar KOSMOS
> e AKASHA especialmente nas funções de crawling e indexação, evitando duplicação
> e aproveitando ecosystem_scraper.py já compartilhado.

#### KOSMOS
- [ ] **Botão "Arquivar no AKASHA" no leitor de artigos** (`app/ui/views/reader_view.py`
  ou `app/ui/views/article_view.py`). Padrão FreshRSS+Wallabag: ao clicar, envia
  `POST http://localhost:7071/archive` com `url=<url_do_artigo>` (AKASHA já ouve na
  porta 7071). AKASHA faz fetch completo e salva na biblioteca. Pré-requisito: AKASHA
  precisa ter esse endpoint — ver item correspondente em AKASHA abaixo.
  Mostrar toast "Arquivado no AKASHA" ao receber 200.
  Mostrar erro "AKASHA offline" ao receber falha de conexão (não bloquear leitura).

- [ ] **Auto-arquivar ao salvar artigo** (`app/ui/main_window.py` ou
  `app/ui/views/unified_feed_view.py`). Padrão Miniflux automations: quando o usuário
  clica em "Salvar" (bookmark) no artigo, enviar a URL automaticamente para AKASHA em
  background (fire-and-forget, sem bloquear UI). Adicionar opção `auto_archive_on_save`
  em `app/utils/config.py` (default: False). Na ação de salvar, se configurado, fazer
  `requests.post("http://localhost:7071/archive", data={"url": url}, timeout=3)` em
  thread separada.

- [ ] **Busca unificada KOSMOS + AKASHA** (`app/ui/views/unified_feed_view.py` ou novo
  `SearchView`). Ao pesquisar no KOSMOS, consultar também `GET http://localhost:7071/
  search?q=<termo>` (AKASHA FTS5) e mesclar resultados com indicador de fonte (RSS vs
  AKASHA). Evita abrir dois apps para pesquisar conteúdo relacionado.

#### AKASHA
- [ ] **Endpoint `POST /archive` para receber URLs de outros apps** (`routers/crawler.py`
  ou novo `routers/archive_api.py`). Recebe `{"url": "...", "tags": [...], "notes": ""}`,
  chama `archive_url()` existente, retorna `{"status": "ok", "path": "..."}`.
  Autenticação: nenhuma (local-only, 127.0.0.1). Documentar no `CLAUDE.md` como contrato
  de API. O KOSMOS e potencialmente outros apps do ecossistema usarão esse endpoint.

- [ ] **Crawling incremental a partir dos feeds do KOSMOS** (`services/crawler.py` ou
  novo `services/feed_crawler.py`). Padrão ArchiveBox: ao adicionar um feed ao KOSMOS,
  notificar AKASHA (via `POST /add-source`) com o domínio raiz para crawl periódico.
  AKASHA adiciona o domínio à lista de sites monitorados. Implementação: KOSMOS lê
  `akasha.base_url` do ecosystem.json; ao criar feed, faz `POST /add-source?url=<domínio>
  &name=<nome_feed>`. Evita que artigos de domínios monitorados existam só como resumo
  RSS — a versão completa fica no AKASHA.

- [ ] **Deduplicação entre arquivo AKASHA e artigos KOSMOS** (`services/library.py`).
  Ao arquivar uma URL que já existe no archive do KOSMOS (`kosmos.archive_path`), criar
  symlink ou registro cruzado em vez de duplicar. Consultar `kosmos.archive_path` do
  ecosystem.json. Verificar por URL normalizada (remover parâmetros de rastreamento
  `utm_*`). Se já arquivado pelo KOSMOS, retornar o path existente em vez de re-arquivar.

### Pesquisa: Motores de Busca Pessoais, Ranking de Relevância e Busca Híbrida | 2026-05-04
> Contexto: pesquisa exaustiva sobre SQLite FTS5, ranking além de BM25, motores self-hosted,
> APIs de artigos científicos, extração de snippets, busca híbrida FTS5+vetor, query understanding
> e deduplicação near-duplicate — tudo aplicado ao AKASHA (FastAPI + SQLite FTS5 + ChromaDB).

#### AKASHA
- [x] **Configurar pesos de coluna BM25 persistentes via `INSERT INTO tabela(tabela, rank)`**
  (`database.py` ou função de inicialização do DB). Atualmente os pesos são passados
  explicitamente em cada query (ex: `bm25(local_fts, 0, 10, 1, 0)`). Usar a configuração
  persistente do FTS5: `INSERT INTO local_fts(local_fts, rank) VALUES('rank', 'bm25(0, 10.0, 1.0, 0)')`
  na criação da tabela. Isso permite usar `ORDER BY rank` em vez de repetir os pesos em
  cada query, e facilita ajuste de pesos sem alterar código de busca.

- [x] **Implementar snippets por parágrafo como alternativa ao snippet() FTS5**
  (`services/local_search.py`). A função snippet() FTS5 é limitada a 64 tokens e usa
  heurística simples. Para resultados de melhor qualidade: dividir o body do documento
  em parágrafos, aplicar BM25 (bm25s ou rank_bm25) para rankear parágrafos contra a query,
  retornar o parágrafo mais relevante como snippet. Implementar como opção configurável
  (snippet_mode: 'fts5' | 'paragraph_bm25'). Dependência: pip install bm25s.

- [x] **Adicionar suporte a prefix queries e phrase queries na sanitização FTS5**
  (`services/local_search.py`, função `_sanitize_fts`). Atualmente `_sanitize_fts()` remove
  `*` e `"` da query, perdendo prefix queries (ex: "searc*") e phrase queries (ex: `"machine
  learning"`). Melhorar sanitização para: (a) manter aspas duplas válidas (phrase), (b) manter
  asterisco no final de tokens (prefix), (c) remover apenas chars que causam erros de sintaxe
  FTS5. Adicionar detecção de intenção: se query contém aspas, tratá-la como phrase query.

- [x] **Configurar tokenizer unicode61 com remove_diacritics 2 nas tabelas FTS5**
  (`database.py` na criação das tabelas). Atualmente as tabelas FTS5 usam o tokenizer padrão.
  Adicionar `tokenize='unicode61 remove_diacritics 2'` na criação de local_fts e library_fts.
  Isso garante que buscar "pagina" encontre "página", "cafe" encontre "café", etc.
  Melhoria de recall para PT+EN sem custo adicional.

- [x] **Implementar RRF (Reciprocal Rank Fusion) entre FTS5 e ChromaDB**
  (`services/local_search.py`, função `rank_combined`). O `rank_combined()` atual usa
  re-scoring simples por contagem de termos. Substituir por RRF: (1) FTS5 retorna lista
  ranqueada por BM25; (2) ChromaDB retorna lista por cosine similarity; (3) RRF combina
  com fórmula `score += 1.0 / (60 + rank)`. Resultado: documentos que aparecem em ambos
  os sistemas sobem no ranking sem precisar normalizar scores incompatíveis.
  Implementação: ~15 linhas de Python. Nenhuma nova dependência.

- [x] **Adicionar detecção de idioma + stemming PT/EN na query antes do FTS5**
  (`services/local_search.py`). Integrar langdetect (pip install langdetect) para detectar
  idioma da query. Se PT: aplicar NLTK RSLPStemmer ou SnowballStemmer("portuguese"). Se EN:
  aplicar SnowballStemmer("english"). Expandir query FTS5 com stems via OR: ex, "buscando" →
  `(buscando OR busc*)`. Melhorar recall especialmente para queries PT onde conteúdo pode
  estar em diferentes formas morfológicas. Atenção: unicode61 remove_diacritics já cobre
  variações de acento — stemming é complementar.

- [x] **Implementar deduplicação near-duplicate via SimHash no archiver**
  (`services/archiver.py` ou `services/library.py`). Ao arquivar nova URL, calcular SimHash
  do texto extraído (pip install simhash). Comparar com SimHashes de documentos já indexados
  armazenados em coluna da tabela de metadados (distância Hamming ≤ 3 → near-duplicate).
  Se near-duplicate detectado: não arquivar; retornar URL do documento existente.
  Também normalizar URL antes de inserir (pip install url-normalize) para deduplicação
  de URLs equivalentes (tracking params, HTTP→HTTPS, trailing slash).

- [x] **Re-ranking cross-encoder para top-K resultados de busca**
  (`services/local_search.py`). Após FTS5 retornar resultados, aplicar re-ranking com
  FlashRank (pip install flashrank) nos top-20 resultados. FlashRank usa modelos embutidos
  (~4MB) e funciona puramente em CPU sem GPU. Latência estimada: ~200ms para 20 docs
  em CPU típico — aceitável para busca local. Implementar como opcional (reranking_enabled
  em config): usuario pode desativar se latência for problema. Maior ganho para queries
  ambíguas onde BM25 retorna muitos falsos positivos.

- [x] **sqlite-vec: adicionar busca vetorial nativa no mesmo arquivo .db do FTS5**
  (`database.py`, `services/local_search.py`). Instalar pip install sqlite-vec. Criar
  virtual table `vec_items(rowid, embedding FLOAT[384])` no mesmo arquivo akasha.db.
  No archiver, ao indexar documento, gerar embedding (modelo leve, ex: all-MiniLM-L6-v2
  via sentence-transformers) e inserir em vec_items. Na busca, combinar FTS5 BM25 +
  sqlite-vec KNN via RRF. Vantagem: sem servidor separado; funciona offline; mesmo arquivo.
  Atenção: MX150 tem 2GB VRAM — usar modelo de embedding ≤ 80MB; i5-3470 sem AVX2
  pode ser lento para embeddings, considerar indexar só em CachyOS.

- [x] **Spell correction de queries com symspellpy**
  (`services/local_search.py`, antes da query FTS5). Integrar symspellpy (pip install
  symspellpy) com dicionários de frequência PT+EN pré-compilados. Se query tem ≤ 2 tokens
  com baixo score BM25 (< resultados esperados), tentar corrigir. Mostrar "Mostrando
  resultados para: [query corrigida]" no response. Latência: < 1ms após carga do dicionário
  em memória. Carregar dicionário no startup do app (uma vez).

- [x] **Preset "apenas artigos científicos" na rota de busca**
  (`routers/search.py`, template `search.html`). Aceitar `?mode=papers` na rota `/search`
  que force `src_papers=True` e todos os outros sources desligados. Na UI, adicionar botão
  "Buscar artigos" ao lado do campo de busca principal (ou atalho de teclado). Permite busca
  exclusiva em Semantic Scholar + arXiv sem passar por DDG/FTS5 local/sites. Abre caminho
  para presets futuros (ex: `?mode=local`, `?mode=archive`).

- [x] **OpenAlex como terceira fonte na busca científica**
  (`services/paper_search.py`). Integrar OpenAlex via `pip install pyalex`. OpenAlex cobre
  250M+ artigos (mais abrangente que Semantic Scholar), é gratuito com chave de email,
  retorna abstracts completos e links de acesso aberto. Adicionar ao gather paralelo em
  `paper_search.py` ao lado de Semantic Scholar e arXiv. Usar pyalex: `pya.Works().search(q)`.
  Deduplicar por DOI/arXiv ID antes de retornar resultados. Integrar Unpaywall como
  pós-processamento: dado um DOI, consultar `api.unpaywall.org/v2/{doi}?email=...`
  para obter link PDF de acesso aberto quando disponível.

### Pesquisa: AKASHA como Assistente de Pesquisa — Técnicas Além de LLMs | 2026-05-06
> Contexto: pesquisa sobre PKM (Zotero, DEVONthink, Readwise), workflows reais de pesquisadores
> (Berrypicking, Information Foraging Theory), técnicas de "inteligência" sem LLM (usage-based
> ranking, co-reading, annotation density, TF-IDF local), sistema de anotação web (W3C WADM),
> progressive disclosure e quando LLM faz sentido vs. quando piora. Objetivo: transformar o
> AKASHA em assistente de pesquisa produtivo sem depender de Ollama como fundação.

#### AKASHA
- [x] **Tabela de histórico de acessos** (`database.py`). Criar tabela `doc_accesses(id, url,
  accessed_at DATETIME)` e registrar cada abertura de documento arquivado. Sem UI extra — apenas
  INSERT silencioso ao abrir um documento. Pré-requisito para usage-based ranking, co-reading
  patterns e annotation density. Nenhuma nova dependência.

- [x] **Usage-based ranking** (`services/local_search.py`, função `rank_combined` ou novo
  `services/ranking.py`). Combinar BM25 com frequência de acesso e decaimento temporal:
  `score_final = α × bm25 + (1-α) × (access_count × exp(-λ × days_since_last_access))`.
  Parâmetro `α` configurável em `/settings` (default 0.7 BM25, 0.3 uso). Consultar tabela
  `doc_accesses` com GROUP BY url para obter contagem e último acesso. Sem nova dependência.

- [x] **Tabela de highlights e indexação FTS5 separada** (`database.py`,
  `services/archiver.py`). Criar tabela `highlights(id, url, exact TEXT, prefix TEXT,
  suffix TEXT, note TEXT, created_at DATETIME)` seguindo W3C Web Annotation Data Model
  (TextQuoteSelector: exact = trecho destacado, prefix = 32 chars antes, suffix = 32 chars
  depois). Criar virtual table `highlights_fts(rowid, exact, note)`. Ao buscar, incluir
  resultados de highlights_fts com badge "HIGHLIGHT". Buscas em anotações pessoais retornam
  resultados mais precisos que buscas no corpo completo do documento.

- [x] **Query autocomplete por histórico pessoal** (`routers/search.py` ou via endpoint
  HTMX `GET /search/suggest?q=`). Criar tabela `search_history(query TEXT UNIQUE,
  count INT, last_used DATETIME)` e registrar cada query ao executar busca. Endpoint de
  sugestão: `SELECT query FROM search_history WHERE query LIKE :prefix ORDER BY count DESC,
  last_used DESC LIMIT 10`. Expor como dropdown no campo de busca via HTMX. Sem nova
  dependência — FTS5 puro.

- [x] **Faceted search** (`routers/search.py`, `templates/search.html`). Após executar
  a query FTS5, calcular distribuição dos resultados por: domínio (extrair netloc da URL),
  ano de archivamento, tipo de conteúdo (detectado no archive), idioma. Retornar como
  JSON extra no contexto do template. Exibir como checkboxes de filtro na sidebar dos
  resultados. Segunda query com WHERE adicional quando filtro ativo. Implementação pura
  em SQLite com GROUP BY — sem nova dependência.

- [x] **Co-reading patterns single-user** (`services/local_search.py` ou
  `services/ranking.py`). Ao exibir um documento, consultar `doc_accesses` para encontrar
  outros URLs acessados dentro de uma janela de 2 horas antes e depois. Exibir seção
  "Visto na mesma sessão de pesquisa:" com cards compactos. Captura relações semânticas
  que similaridade de texto não captura (dois documentos sobre temas diferentes mas lidos
  juntos no contexto de uma pesquisa). Implementação: SQL com `ABS(strftime('%s', a1.accessed_at)
  - strftime('%s', a2.accessed_at)) < 7200`. Sem nova dependência.

- [x] **Annotation density como sinal de ranking** (`services/local_search.py`). Ao
  ranquear resultados, incluir contagem de highlights por URL como sinal adicional: documentos
  com mais highlights do usuário sobem no ranking. Consulta: `SELECT COUNT(*) FROM highlights
  WHERE url = :url`. Integrar ao score final como `score += β × log(1 + highlight_count)`,
  com `β` configurável (default 0.1). Pré-requisito: tabela de highlights (item acima).

- [x] **Lenses pessoais** (`database.py`, `routers/search.py`, `templates/base.html`).
  Criar tabela `lenses(id, name TEXT, domains TEXT, tags TEXT, content_types TEXT,
  date_from TEXT, date_to TEXT)`. UI: botão "Lenses" na nav, tela de gestão de lenses
  (criar, editar, deletar). Quando uma lens está ativa, adicionar WHERE clauses à query
  FTS5. Inspirado em Kagi lenses — filtros nomeados que persistem entre sessões e podem
  ser ativados com um clique.

- [x] **TF-IDF local para documentos relacionados** (`services/local_search.py`,
  nova função `find_related(url, n=5)`). Ao exibir um documento arquivado, calcular TF-IDF
  do seu conteúdo contra o corpus indexado no FTS5 (extrair termos discriminantes via
  `SELECT bm25(local_fts) ...`) e fazer nova busca FTS5 com esses termos, excluindo o
  próprio documento. Exibir seção "Documentos relacionados:" com até 5 cards. Sem LLM,
  sem nova dependência — FTS5 puro.

- [x] **Progressive disclosure na UI de resultados** (`templates/search.html`). Estruturar
  cards de resultado em 3 camadas acessíveis progressivamente: (1) título + snippet 30-50
  palavras + ícones de highlights e tags; (2) preview expansível ao clicar "▸" com todos
  os highlights do documento + metadados completos (autor, data, domínio, idioma, word count);
  (3) link "Abrir documento completo" para visualização com modo de anotação. Reduz carga
  cognitiva na lista de resultados sem esconder informação relevante.

- [x] **Citation graph local para papers** (`database.py`, `services/archiver.py`,
  `services/paper_search.py`). Criar tabela `doc_citations(citing_url TEXT, cited_doi TEXT,
  cited_title TEXT)`. Ao arquivar um documento que contém DOIs nas referências (detectar
  por regex `10\.\d{4,}/\S+`), consultar CrossRef REST API (`api.crossref.org/works/{doi}`)
  para enriquecer metadados e salvar em `doc_citations`. Na tela do documento, exibir
  seção "Citado por documentos neste arquivo:" via query de bibliographic coupling. CrossRef
  é gratuito sem autenticação para consultas moderadas.

- [x] **"Mais deste domínio/autor neste período"** (`services/local_search.py`,
  `templates/archive_view.html`). Na tela de visualização de um documento arquivado,
  exibir seção "Mais de [domínio]:" com até 5 documentos do mesmo netloc arquivados
  próximos à mesma data. Implementa o padrão "journal run" de Bates (1989): vasculhar
  o mesmo veículo/autor em busca de contexto. Query SQL: `WHERE url LIKE :domain_pattern
  AND ABS(julianday(archived_at) - julianday(:doc_date)) < 90 LIMIT 5`.

- [x] **Tag co-ocorrência para sugestão** (`services/archiver.py`, `routers/search.py`).
  Ao exibir filtros de tag nos resultados de busca, ordenar tags relacionadas por co-ocorrência
  com a tag selecionada: `SELECT tag_b, COUNT(*) FROM tag_pairs WHERE tag_a = :active GROUP
  BY tag_b ORDER BY COUNT(*) DESC`. Popular tabela `tag_pairs` ao salvar/atualizar tags de
  um documento. Tags que co-ocorrem frequentemente são sugeridas automaticamente ao criar
  novos highlights ou arquivar documentos.

- [x] **Degradação graciosa quando Ollama offline** (`services/local_search.py`,
  `routers/search.py`). Qualquer feature que depende de Ollama (reranking LLM, síntese
  Map-Reduce, HyDE) deve ter um estado funcional alternativo quando `http://localhost:11434`
  não responde. Padrão: verificar Ollama no startup, setar flag `_ollama_available` global.
  Se False: desabilitar features LLM na UI com tooltip "Ollama offline — feature disponível
  quando Ollama estiver rodando". Nunca bloquear a busca FTS5 por falta de LLM.

### Pesquisa: LLMs Locais para Dispatcher/Skill Routing — achados para Mnemosyne e KOSMOS | 2026-05-12
> Contexto: pesquisa sobre arquitetura multi-agente e comparação de LLMs locais para instruction
> following revelou implicações práticas para o Mnemosyne (RAG com citação, janela de contexto,
> ordering de chunks) e para o KOSMOS (modelos mais capazes dentro da mesma limitação de VRAM).

#### Mnemosyne
- [x] **Command R 7B como opção de modelo para RAG** — o Command R 7B (Cohere, via `ollama pull
  command-r`) é o único modelo sub-10B com treinamento explícito para grounded generation com
  citação de fontes (grounding spans). Adicionar como opção de `qa_model` na `SetupDialog` do
  Mnemosyne com tooltip explicando a especialização. Consumo: ~5 GB VRAM Q4_K_M, cabe na RX 6600.
  Para respostas que incluam citações precisas ("conforme [fonte], [trecho]"), esse modelo
  supera Llama/Qwen no critério de fidelidade de atribuição.

- [x] **Reordenação de chunks para mitigar "lost in the middle"** — todos os modelos LLM exibem
  viés posicional em multi-document RAG: chunks no meio do contexto são menos utilizados que
  os do início e do fim. Em `core/rag.py`, ao montar o contexto final, reordenar os N chunks
  recuperados colocando os de maior score RRF alternadamente no início e no final (ex: rank 1
  → posição 0, rank 2 → posição N-1, rank 3 → posição 1, rank 4 → posição N-2). Mudança
  pequena em `_build_context()` com impacto documentado de qualidade de resposta.

- [x] **Nota sobre janela de contexto por modelo** — documentar no `SetupDialog` (tooltip em
  `qa_model`) que Qwen2.5-7B-Instruct suporta 128K tokens de contexto enquanto Llama 3.1 8B
  suporta apenas 16K. Para coleções com documentos longos ou muitos chunks recuperados, o
  Qwen2.5-7B é preferível. Adicionar verificação em `core/rag.py`: se `qa_model` contiver
  "llama" e o contexto montado exceder ~12K tokens, logar aviso "contexto próximo do limite
  do modelo — considere usar Qwen2.5-7B".

#### KOSMOS
- [ ] **Avaliar Phi-4 Mini 3.8B como modelo principal do KOSMOS** — o Phi-4 Mini 3.8B tem MMLU
  equivalente ao Llama 3.1 8B (73%), consome ~3 GB em Q4_K_M e roda a ~60-120 t/s na RX 6600.
  Em CPU puro (i5-3470, Windows 10), cabe em RAM com offload e é significativamente mais capaz
  que o SmolLM2 1.7B atual. Testar: `ollama pull phi4-mini` e avaliar qualidade de respostas
  nas tarefas típicas do KOSMOS (síntese de artigo, extração de conceitos, geração de notas).

- [ ] **Avaliar Gemma 3 4B para hardware limitado (MX150/i5-3470)** — o Gemma 3 4B cabe inteiro
  na MX150 (2 GB VRAM) em Q4_K_M (~2,5 GB) e representa upgrade significativo sobre modelos 1-2B.
  Testar: `ollama pull gemma3:4b`. Candidato a modelo padrão do KOSMOS no laptop e no Windows
  de trabalho onde a MX150 não está disponível mas a RAM permite offload de 4B.

### Pesquisa: LLMs para RAG/Sumarização e Embeddings Multilíngues — Seleção por Hardware | 2026-05-13
> Contexto: pesquisa comparativa de LLMs locais (via Ollama) para RAG multi-doc (Mnemosyne) e sumarização
> de artigos (KOSMOS), e de modelos de embedding para indexação multilíngue pt/en. Hardware real: MainPc
> (RX 6600 8 GB VRAM, ROCm), Laptop (MX150 2 GB CUDA, i7 AVX2), WorkPc (i5-3470 sem AVX2, sem GPU).
> Achados completos em pesquisas.md (sessão 2026-05-13). LLMs recomendados devem aparecer na UI do LOGOS
> com opção de download para modelos não instalados.

#### HUB — LOGOS: botão de download de modelos recomendados
- [x] Adicionar em `LogosView.tsx` (HUB) botão "Baixar" ao lado de cada modelo recomendado que não
  estiver instalado. Usar o endpoint `/api/logos/pull` já existente com streaming NDJSON. O botão deve
  exibir progress bar durante pull e sumir ao concluir. Modelos já instalados mantêm apenas o botão
  "Ativar" existente. Verificar lista de instalados via `logos_list_local_models` (já em `logos.rs`).

#### Mnemosyne — embedding no Laptop: nomic-embed-text é inglês-only
- [x] Substituir `nomic-embed-text` por `bge-m3` (via Ollama) no Laptop. `nomic-embed-text v1.5` é
  treinado exclusivamente em inglês e degrada indexação de conteúdo português — confirmado por benchmarks
  MTEB (arXiv:2402.03216). `bge-m3` (BAAI) suporta 100+ línguas, 1024 dims, 570M params, ~1.3 GB VRAM,
  roda na MX150. **Atenção crítica:** trocar embedding exige reindex completo do ChromaDB (dimensão muda
  de 768 → 1024 dims — coleção incompatível). Limpar a coleção antes de reindexar. Documentar a troca
  no GUIDE.md do Mnemosyne.
- [x] Avaliar `potion-multilingual-128M` (Model2Vec, não via Ollama — pip install model2vec) como
  fallback no WorkPc. Decisão tomada na sessão 2026-05-14: adotar no WorkPc (256 dims, estático,
  27 MB, 500× mais rápido em CPU); índice separado do MainPc/Laptop por incompatibilidade de dims.
  Detalhes e itens de implementação na seção 2026-05-14.

#### Mnemosyne — LLM RAG por máquina: alinhamento com perfis do LOGOS
- [x] **MainPc:** `qwen2.5:7b` confirmado como LLM de RAG primário na sessão 2026-05-14. Perfil
  detalhado com todos os slots (rag/analysis/query/embed) registrado na seção 2026-05-14.
- [ ] **MainPc:** avaliar `command-r7b` (Cohere, 8B, 3,9 GB, 128K ctx) para RAG com citação explícita.
  Único modelo com `grounded generation` nativa — retorna grounding spans exatos do documento. Útil
  quando o Mnemosyne precisar referenciar trechos específicos. Não está no inventário atual — requer
  download antes de testar.
- [x] **Laptop:** `phi3.5:mini` descartado — 2,2 GB excede os 2 GB VRAM da MX150. LLM RAG do Laptop
  é `gemma2:2b` (1,6 GB Q4), conforme corrigido na seção 2026-05-14.

### Pesquisa: LLMs por Funcionalidade e Hardware — Controle de Recursos e Compatibilidade | 2026-05-14
> Contexto: pesquisa sobre (1) modelos ideais por funcionalidade do ecossistema (Mnemosyne-RAG,
> KOSMOS-análise, AKASHA-query) cruzados com cada perfil de hardware real; (2) controle configurável
> de consumo de CPU/VRAM no LOGOS para prevenir travamentos; (3) gerenciamento do ciclo de vida do
> Ollama (iniciar, parar, pausar, interromper); (4) compatibilidade de saídas cross-machine
> (embeddings, JSON estruturado). Achados completos em pesquisas.md (sessão 2026-05-14).
> **ATENÇÃO:** a seção anterior (2026-05-13) contém item incorreto sobre WorkPc ("sem LLM local") —
> o WorkPc TEM smollm2:1.7b e qwen2.5:0.5b funcionais a 2–5 tok/s. Os itens desta seção prevalecem.

#### HUB — LOGOS: corrigir perfis de modelo por funcionalidade e hardware
- [x] Atualizar `HardwareProfile::model_profile()` em `HUB/src-tauri/src/logos.rs` com tabela corrigida
  por funcionalidade. O campo `model_type` deve distinguir entre `llm_rag` (Mnemosyne), `llm_analysis`
  (KOSMOS), `llm_query` (AKASHA — dispatcher leve) e `embed` (embedding):
  - **MainPc** (RX 6600 8 GB): llm_rag=`qwen2.5:7b` (128K ctx, 4,7 GB, IFEval 87,3, multilíngue);
    llm_analysis=`gemma2:2b` (8K ctx, 1,6 GB — permite concorrência simultânea com qwen2.5:7b dentro
    dos 8 GB: 4,7+1,6=6,3 GB < 8 GB); llm_query=`smollm2:1.7b` (1 GB, manter sempre aquecido via
    keep_alive=-1); embed=`bge-m3` (0,6 GB Q4, 1024 dims, 100+ línguas).
  - **Laptop** (MX150 2 GB): llm_rag=`gemma2:2b` (1,6 GB Q4 — único modelo viável na MX150 para RAG,
    8K ctx é suficiente para corpus pequeno); llm_analysis=`smollm2:1.7b` (1 GB, análise básica);
    llm_query=`smollm2:1.7b`; embed=`bge-m3` (0,6 GB Q4 — mesmas 1024 dims do MainPc, índice
    ChromaDB compatível e sincronizável via Proton Drive).
  - **WorkPc** (i5-3470 CPU, sem AVX2): llm_rag=`smollm2:1.7b` (1 GB Q4, 2–5 tok/s — lento mas
    funcional); llm_analysis=`qwen2.5:0.5b` (400 MB Q4, ~5–10 tok/s, para artigos curtos);
    llm_query=`qwen2.5:0.5b` (dispatcher mais leve); embed=`potion-multilingual-128M` (NÃO via
    Ollama — instalado via `pip install model2vec`, estático, 27 MB, 256 dims, 101 línguas, 500×
    mais rápido que bge-m3 em CPU — NÃO usar o mesmo ChromaDB que MainPc/Laptop pois 256≠1024 dims).
- [x] Adicionar campo `slot_label` à struct `ModelSlot` em `logos.rs` para exibir nome amigável na
  UI: `llm_rag` → "RAG/chat (Mnemosyne)", `llm_analysis` → "Análise de artigos (KOSMOS)",
  `llm_query` → "Busca inteligente (AKASHA)", `embed` → "Embedding". Substituir o campo genérico
  `model_type` na exibição da `LogosView.tsx`.
- [x] Adicionar campo `expected_speed_note` à struct `RecommendedModel` para o WorkPc com string
  descritiva (ex: "~3 tok/s — adequado para background, lento em chat interativo"). Exibir na UI
  do LOGOS ao lado dos modelos do WorkPc para que a usuária entenda o comportamento esperado.

#### HUB — LOGOS: controle configurável de VRAM e CPU por percentual
- [x] Implementar controle de percentual máximo de VRAM. O Ollama não tem variável de limite por
  percentagem — a implementação deve ser no LOGOS: (a) `HardwareProfile` já tem `vram_total_mb`;
  (b) calcular `vram_limit_bytes = vram_total_mb * 1024 * 1024 * vram_limit_pct / 100`; (c) antes
  de ativar novo modelo, consultar `GET /api/ps` (retorna modelos carregados com VRAM em bytes por
  modelo); (d) se `vram_em_uso + vram_do_modelo_novo > vram_limit_bytes`, descarregar o modelo com
  menor prioridade (P3 primeiro) via `POST /api/generate { "model": X, "keep_alive": 0 }`; (e)
  persistir `logos.vram_limit_pct` (padrão: 85) no `ecosystem.json`. Expor na UI como slider.
- [x] Ao iniciar o servidor Ollama (subprocesso), injetar no ambiente: `OLLAMA_GPU_OVERHEAD` por
  perfil (MainPc: 838860800 bytes = ~800 MB = 10% de 8 GB; Laptop: 209715200 = ~200 MB = 10% de
  2 GB; WorkPc: 0); `OLLAMA_FLASH_ATTENTION=1` em todos os perfis (reduz KV cache VRAM em 20–40%
  sem custo de qualidade, compatível com ROCm e CUDA); `OLLAMA_MAX_LOADED_MODELS` por perfil
  (MainPc: 3, Laptop: 2, WorkPc: 1); `OLLAMA_KEEP_ALIVE=5m` como padrão global (sobrescrito por
  keep_alive por requisição quando necessário). Usar `std::process::Command::envs(...)` em Rust.
- [x] Implementar controle de `num_thread` de CPU por tipo de tarefa para o WorkPc. O parâmetro
  `num_thread` é passado por requisição individual (não é variável de ambiente). Tarefas P3/batch
  (KOSMOS análise em background): `num_thread=3` (deixa 1 core livre para o SO). Tarefas P2/
  interativas (Mnemosyne RAG): `num_thread=4` (maximiza velocidade de resposta). Adaptar a função
  de geração de requisições no `logos.rs` para incluir `num_thread` baseado na prioridade da tarefa.
- [x] Adicionar painel de configuração de limites na `LogosView.tsx`: slider "Limite de VRAM (%)"
  (padrão 85, range 50–95); campo "Threads CPU" para WorkPc (2/3/4 threads); toggle
  "FlashAttention" (padrão: ligado). Persistir via `save_ecosystem_config()` já existente no HUB.

#### HUB — LOGOS: gerenciamento do ciclo de vida do Ollama (iniciar / parar / abortar)
- [x] Implementar `logos_start_ollama()` Tauri command em `commands/logos.rs`. Lógica: detectar
  se Ollama já está rodando via `GET http://localhost:11434/`; se não, iniciar subprocesso:
  Windows — `Command::new("ollama").arg("serve")` com variáveis de ambiente do perfil (ver item
  acima); Linux — tentar `systemctl start ollama.service` primeiro; se falhar, fallback para
  subprocesso direto. Após spawn, fazer polling em `GET /` a cada 500ms por até 30s; emitir evento
  `logos-ollama-status { running: bool }` quando pronto ou em timeout. Guardar handle do processo
  para uso posterior no stop.
- [x] Implementar `logos_stop_ollama()` com comportamento correto por SO e por contexto de execução:
  - **Windows sem app.exe:** executar `taskkill /IM ollama.exe /F` via `Command`.
  - **Windows com app.exe rodando** (detectável via `tasklist | grep "ollama app.exe"`): retornar
    erro ao frontend com mensagem "O app do Ollama está na bandeja do sistema e irá reiniciar o
    servidor. Feche-o antes de parar." Não tentar matar o processo — seria inútil.
  - **Linux:** `systemctl stop ollama.service` ou `pkill -f "ollama serve"` como fallback.
  - Se o LOGOS foi quem iniciou o processo (handle disponível), usar `child.kill()` em Rust (mais
    limpo que taskkill). Emitir `logos-ollama-status { running: false }` após confirmação.
- [x] Implementar `logos_abort_model_inference()` para cancelar geração em andamento sem descarregar
  o modelo. Mecanismo: manter um `HashMap<String, tokio::task::AbortHandle>` no `LogosState` com
  handle por modelo ativo. Ao chamar abort, acionar `handle.abort()` — o futuro Rust é dropado, a
  conexão HTTP é fechada, e o Ollama para de gerar automaticamente quando detecta cliente
  desconectado. O modelo permanece aquecido em VRAM (comportamento desejado para retomada rápida).
- [x] Documentar limitação de cancelamento de pull na `LogosView.tsx`: quando clicar "Cancelar"
  durante pull em andamento, exibir aviso: "O Ollama continuará o download em background mesmo após
  cancelar aqui. Para interromper de fato, pare o servidor Ollama." Limitação conhecida do Ollama
  (issue #13142 — sem endpoint REST para cancelar pull).

#### HUB — LOGOS: compatibilidade de embeddings e strategy de índice único
- [x] Implementar detecção de mudança de modelo de embedding em `logos.rs`. Se o modelo configurado
  em `embed` do perfil for diferente do que gerou o índice ChromaDB existente (checar via metadados
  salvos na coleção), alertar via evento Tauri: "Trocar embedding de [modelo_antigo] para
  [modelo_novo] exige reindexação completa — os vetores atuais são incompatíveis (dims:
  [antiga] → [nova]). Confirmar?" Bloquear uso do Mnemosyne até reindexação ou reverter a escolha.
- [x] Implementar flag `indexing_enabled` por perfil no `ecosystem.json`. WorkPc deve ter
  `indexing_enabled: false` por padrão — consume o índice bge-m3 sincronizado pelo MainPc via
  Proton Drive, sem gerar índice local com potion-multilingual-128M (dims incompatíveis). O
  Mnemosyne deve verificar essa flag no startup e exibir "Indexação desativada neste computador —
  usando índice sincronizado do computador principal" se `false`.

#### KOSMOS — JSON schema enforcement para análise cross-machine
- [x] Garantir que o prompt de análise do KOSMOS inclua o schema JSON de saída explicitamente para
  todos os campos (5W: quem, o quê, quando, onde, por quê; entidades; resumo; tags) e passe
  `"format": "json"` na requisição Ollama. Para modelos pequenos (smollm2:1.7b no WorkPc e
  qwen2.5:0.5b), adicionar 2–3 pares de exemplos few-shot no system prompt — modelos sub-2B não
  seguem schemas sem exemplos. Implementar pipeline de validação: parsear o JSON retornado; se
  falhar, reenviar ao modelo com mensagem de erro + instrução "Corrija o JSON inválido mantendo os
  mesmos campos". Isso garante que análises de artigos geradas por qualquer máquina tenham formato
  idêntico e possam ser sincronizadas via Proton Drive sem conversão.

### Pesquisa: RAG Multilíngue — Estratégias de Pipeline, Indexação e Geração Cross-lingual | 2026-05-14
> Contexto: pesquisa sobre as melhores abordagens para RAG com corpus em múltiplos idiomas
> (português, inglês e mandarim). Cobre: estratégias de pipeline (tRAG, MultiRAG, CrossRAG,
> QTT-RAG), language drift em geração multilíngue, viés de idioma no reranking, chunking para
> chinês, detecção de idioma por chunk e compatibilidade com bge-m3. Achados completos em
> pesquisas.md (sessão 2026-05-14).

#### Mnemosyne
- [x] **Chunking por contagem de caracteres Unicode** — substituir a contagem de palavras/espaços
  por `len(text)` em caracteres Unicode ao definir `chunk_size` e `overlap` em `core/indexer.py`.
  Razão: chinês não tem espaços entre palavras — um chunker baseado em whitespace cria chunks
  gigantes ou quebra no meio de palavras. Limiar recomendado: ~1000–1200 chars por chunk (equivale
  a ~300–400 words em pt/en e ~500–600 caracteres zh significativos). Manter overlap em ~15% do
  tamanho. Essa mudança melhora qualidade para todos os idiomas, não só zh.
- [x] **Metadado `language` por chunk na indexação** — em `core/loaders.py` ou `core/indexer.py`,
  após carregar cada documento, detectar o idioma do texto via `lingua-py`
  (`pip install lingua-language-detector`) e adicionar `metadata["language"]` com o código ISO
  (ex: `"pt"`, `"en"`, `"zh"`) a cada chunk. Usar `lingua-py` em vez de `langdetect` — superior
  para textos curtos e para distinguir idiomas próximos (pt vs es). Configurar o detector para
  reconhecer pelo menos: `Language.PORTUGUESE`, `Language.ENGLISH`, `Language.CHINESE`. Esse
  metadado habilita filtragem futura, estatísticas do índice e diversidade no reranking.
- [x] **Language instruction no system prompt** — adicionar instrução explícita de idioma de
  resposta ao system prompt em `core/rag.py`: `"Responda sempre em português, independentemente
  do idioma dos documentos recuperados."` Razão: fenômeno de language drift documentado —
  quando os chunks recuperados estão em idioma diferente do esperado (especialmente chinês),
  o LLM tende a responder no idioma do contexto. Chinês é o caso mais severo (consistência
  cai de 92% para 68%). Instrução explícita resolve sem exigir acesso a logits (que o Ollama
  não expõe via API).
- [x] **Diversidade de idioma antes do reranking** — em `core/rag.py`, após recuperação híbrida
  (BM25 + semântica) e antes de passar os chunks ao LLM, garantir que os top-k resultados não
  sejam todos no mesmo idioma. Estratégia simples: se >70% dos chunks recuperados forem em inglês
  e houver candidatos em pt/zh com score ≥ 0.7× do melhor inglês, promovê-los ao top-k
  substituindo duplicatas de baixa margem. Razão: rerankers têm viés documentado (benchmark
  LAURA, arXiv:2604.20199) — colocam >70% dos docs em inglês mesmo em corpus multilíngue.
- [x] **Prefixo do título do documento em cada chunk** — ao montar o chunk para indexação em
  `core/indexer.py`, prefixar o texto com o título do documento fonte (do frontmatter ou do
  nome do arquivo): ex: `"[Título do artigo]\n\n{texto do chunk}"`. Melhora recall no RAG
  porque o título frequentemente contém as palavras-chave da query — sem o prefixo, chunks de
  seções internas de um artigo longo ficam sem âncora léxica ao seu tema principal.
- [x] **Detector de idioma dinâmico com notificação ao usuário** — expandir `_get_lingua_detector()`
  em `core/indexer.py` para usar `from_all_languages()` em vez de lista fixa pt/en/zh. Ao
  indexar, usar `.compute_language_confidence_values()` para obter confiança; se o melhor
  resultado ficar abaixo de ~0.5, gravar `language: "unknown"` no metadata e acumular os
  arquivos afetados. O indexer deve emitir um sinal (ex: `languages_unknown(list[str])`) ao
  final do processo quando houver arquivos não reconhecidos. A UI exibe notificação: *"X arquivos
  em idioma não reconhecido"* com botão para abrir Settings e ajustar a lista `detect_languages`
  do `AppConfig`. O singleton `_lingua_detector_instance` deve ser invalidado e reconstruído
  quando a lista mudar (reindex dos arquivos `unknown`). No WorkPc (i5-3470), o detector de 75
  idiomas pode ser pesado — considerar manter lista configurável por máquina como fallback.

#### KOSMOS
- [x] **Chunking por caractere Unicode ao processar artigos** — aplicar a mesma lógica do item
  Mnemosyne acima ao processamento de artigos do KOSMOS. Se o KOSMOS usa `RecursiveCharacterTextSplitter`
  do LangChain, verificar se o parâmetro `length_function` está como `len` (padrão correto) e
  não como algum tokenizador customizado que ignore caracteres zh. Para artigos em chinês,
  considerar separadores `["。", "！", "？", "\n\n", "\n"]` em vez dos separadores europeus
  (`[". ", "! ", "? "]`) que não existem em chinês.
- [x] **Language instruction no prompt de análise** — adicionar ao system prompt do KOSMOS
  instrução: `"Responda em português. Os campos textuais do JSON devem estar em português,
  mesmo que o artigo original esteja em outro idioma."` Razão: sem instrução, contexto em
  chinês pode causar output em chinês, quebrando o schema e a legibilidade das análises
  sincronizadas entre máquinas.

#### AKASHA
- [x] **Chunking Unicode e detecção de idioma no pipeline de indexação** (`services/local_search.py`,
  funções `_extract_kosmos()` e `_reindex()`). O pipeline já existe — o placeholder anterior
  está resolvido. Hoje `_extract_kosmos()` lê o arquivo inteiro e trunca em 8000 chars com
  `body[:8000]`, sem considerar limites Unicode ou idioma. Implementar: (a) substituir o
  truncamento cru por um chunker por contagem de caracteres Unicode (análogo ao Mnemosyne)
  para não cortar no meio de um caractere multibyte; (b) usar `lingua-py` para detectar
  idioma do chunk e armazenar no índice FTS5 como coluna adicional ou em `local_index_meta`;
  (c) adicionar language instruction no system prompt de qualquer chamada LLM que use o
  conteúdo indexado. O corpus é multilíngue por design (pt + en + zh) — essas práticas
  são obrigatórias, não opcionais. Registrar no `GUIDE.md` do AKASHA.

#### HUB — LOGOS
- [x] **Registrar qwen2.5 como preferido para contexto em chinês nas atribuições de modelo** —
  em `logos.rs`, ao definir os perfis de modelo por funcionalidade e hardware (ver item
  "corrigir perfis" na seção anterior), adicionar campo `language_affinity: Option<Vec<String>>`
  à struct `ModelSlot` indicando para quais idiomas o modelo tem treinamento especializado.
  qwen2.5:7b (MainPc) e qwen2.5:0.5b (WorkPc): `["zh", "en"]`. smollm2:1.7b e gemma2:2b: `["en"]`.
  O LOGOS pode usar isso futuramente para rotear queries com contexto em zh preferencialmente
  para qwen2.5. Por ora, exibir na `LogosView.tsx` como informação ao usuário junto ao modelo.

### Pesquisa: Detecção de Evento em Feeds — Clustering Temporal-Semântico de Artigos | 2026-05-14
> Contexto: pesquisa sobre como identificar automaticamente que artigos de fontes diferentes cobrem
> o mesmo evento do mesmo dia. Cobre: TDT (Topic Detection and Tracking), clustering incremental
> com janela temporal, threshold de similaridade cosseno, SimHash/MinHash para deduplicação prévia,
> NER como filtro adicional, algoritmos DBSCAN/BIRCH, implementações de referência (Feedly, NewSloth)
> e compatibilidade por hardware (MainPc/Laptop/WorkPc). Achados completos em pesquisas.md (sessão 2026-05-14).

#### KOSMOS
- [ ] **Event clustering incremental com janela temporal** — implementar pipeline de dois estágios
  em `app/core/event_clustering.py` (novo módulo). Estágio 1 já existe (deduplicação por
  `content_hash` e `rapidfuzz`). Estágio 2: para cada artigo não-duplicata salvo nas últimas
  48h, calcular embedding do título com `paraphrase-multilingual-MiniLM-L12-v2` (50+ idiomas,
  ~115MB, viável em CPU); comparar com centróides de clusters ativos via similaridade cosseno;
  se cosseno ≥ 0.80 → atribuir ao cluster mais próximo (atualizar centróide como média); se
  nenhum cluster ≥ 0.80 → criar novo cluster. Criar tabela `event_clusters(id, anchor_article_id,
  created_at, last_updated_at)` e campo `event_cluster_id` em `articles`. Processar em background
  thread após cada ciclo de fetch, não em tempo real por artigo. Modelo recomendado para cada
  máquina: MainPc → `bge-m3`; Laptop → `paraphrase-multilingual-MiniLM-L12-v2`; WorkPc →
  fallback léxico (ver próximo item).
- [ ] **Fallback léxico de clustering para WorkPc (sem AVX2, sem GPU)** — quando nenhum modelo
  de embedding estiver disponível (detectável por `sentence-transformers` não instalado ou
  `KOSMOS_EMBEDDING_DISABLED=1`), usar clustering léxico simples como substituto: normalizar
  título (lowercase, remover pontuação e stopwords), calcular Jaccard de bigrams entre títulos
  de artigos publicados no mesmo dia, threshold 0.55. Implementar em `event_clustering.py` como
  `_cluster_lexical(articles)` chamado quando `_cluster_semantic()` não estiver disponível.
  Não é tão preciso quanto o semântico, mas evita artigos completamente avulsos sem agrupamento.
- [ ] **Exibição de cluster na feed list** — após implementação do clustering, agrupar artigos
  do mesmo evento visualmente na `FeedListView`: mostrar o artigo âncora (o mais antigo do
  cluster, ou o que tiver maior completude de conteúdo) com um badge discreto "N fontes"
  ao lado da data. Os demais artigos do cluster ficam recolhidos por padrão e expansíveis
  com clique no badge. Isso reduz a densidade visual da feed em eventos com alta cobertura
  (ex: um lançamento de produto coberto por 15 sites) sem esconder nenhuma perspectiva.

## Melhorias, correções e atualizações

### AKASHA — integração com LOGOS e ecosystem_client | 2026-05-15
> Contexto: o AKASHA chama o Ollama diretamente, sem passar pelo LOGOS. Isso significa que
> o classificador de intenção e o pin_model() ignoram coordenação de VRAM e prioridade com
> os outros apps. Além disso, DEFAULT_LLM_MODEL = "" deixa o pin_model() inoperante.
> Análogo ao que foi corrigido no KOSMOS e Mnemosyne anteriormente.

#### AKASHA
- [x] **Migrar AKASHA para `ecosystem_client.request_llm()`** (`services/query_understanding.py`,
  `services/local_search.py` — função `_expand_query_llm()`). O AKASHA hoje chama o Ollama
  na porta 11434 sem passar pelo LOGOS (porta 7072) em dois lugares: `query_understanding.py`
  (`pin_model`, `release_model`, `classify_intent`) e `local_search._expand_query_llm()`.
  Ambos devem usar `ecosystem_client.get_ollama_url()` como base URL — retorna 7072 se LOGOS
  acessível, 11434 como fallback. Isso garante que todas as chamadas LLM do AKASHA passem
  pelo controle de prioridade (P1/P2/P3), keep_alive automático e Hardware Guard de VRAM.

- [x] **`query_understanding.py` resolver modelo via perfil ativo do LOGOS**
  (`services/query_understanding.py`, `DEFAULT_LLM_MODEL`; `ecosystem_client.py`,
  `_APP_MODEL_KEY`). O valor atual `DEFAULT_LLM_MODEL = ""` torna `pin_model()` um no-op —
  sem nome de modelo, nenhum modelo é fixado em VRAM e o keep_alive=-1 nunca é enviado.
  Correção: (1) adicionar `"akasha": "llm_kosmos"` ao dict `_APP_MODEL_KEY` em
  `ecosystem_client.py` — o AKASHA usa o mesmo modelo leve do KOSMOS, resolvido por máquina
  via perfil LOGOS; (2) em `query_understanding.py`, popular `DEFAULT_LLM_MODEL` no startup
  via `ecosystem_client.get_active_profile()["models"]["llm_kosmos"]` (com fallback
  para `smollm2:1.7b`). Nota: a chave `llm_query` não existe — apps não listados em
  `_APP_MODEL_KEY` já usam `"llm_kosmos"` como fallback automático. Depende do item anterior.

### HUB — desinstalar modelos Ollama pelo LOGOS | 2026-05-15
> Contexto: a LogosView já permite baixar, ativar e descarregar modelos da VRAM, mas não há como
> remover um modelo do disco pelo HUB — a usuária precisa usar a CLI (`ollama rm`). Adicionar
> botão "Remover" para modelos instalados mas não ativos.

#### HUB
- [x] Implementar `logos_delete_model(model: String)` em `commands/logos.rs`. Chama
  `DELETE /api/delete` no Ollama com body `{"name": model}`. Retorna `Ok(())` em sucesso ou
  `Err(String)` com mensagem de erro. Registrar em `lib.rs` e expor em `lib/tauri.ts`.
- [x] Adicionar botão "Remover" na seção "Modelos Ollama" da `LogosView.tsx` para modelos com
  status `available` (não ativos na VRAM). Modelos ativos devem ser descarregados primeiro —
  mostrar mensagem "Descarregue o modelo antes de remover" se o usuário tentar. Confirmar a
  ação com `window.confirm()` antes de chamar o comando. Atualizar a lista após remoção.

### Mnemosyne + AKASHA: tratamento diferenciado por tipo de fonte | 2026-05-06
> Contexto: diferentes fontes têm densidade informacional, perspectiva e objetivo distintos —
> notas pessoais são opinião da usuária, transcrições são linguagem falada informal, artigos
> web são resumos curados, livros são conteúdo desenvolvido, artigos científicos são o mais
> denso e autoritativo. O pipeline de RAG deve refletir essas diferenças em chunking,
> recuperação e apresentação dos resultados.

#### Mnemosyne
- [x] **[P1] Framing por tipo no prompt de RAG (`core/rag.py`)** — quando montar o contexto
  enviado ao LLM, incluir o rótulo legível do `source_type` de cada chunk: "Nota pessoal",
  "Transcrição", "Artigo web", "Livro", "Artigo científico". Notas pessoais devem ser
  explicitamente marcadas como opinião da usuária ("este trecho vem das suas notas pessoais")
  para que o LLM não as trate como fato externo. Científicos como "artigo peer-reviewed".
  Mudança pequena, alto impacto — o LLM passa a raciocinar diferente sobre cada fonte.

- [x] **[P2] Peso por tipo de fonte na recuperação híbrida (`core/rag.py`)** — adicionar dict
  `SOURCE_WEIGHTS: dict[str, float]` (ex: `{"scientific": 1.4, "book": 1.2, "library": 1.0,
  "transcript": 0.9, "vault": 1.0}`). Ao fazer o merge BM25 + semântico, multiplicar o score
  pelo peso da fonte antes do ranking final. Notas pessoais têm peso neutro (1.0) — são
  relevantes quando a pergunta é sobre a opinião da usuária, não quando é sobre fatos.
  Transcrições de YouTube/TikTok pesam menos que livros no mesmo tema.

- [x] **[P3] Separadores de chunk específicos por tipo (`core/indexer.py`)** — em
  `_get_splitter()`, além do `chunk_size`/`overlap`, usar separadores adequados ao conteúdo:
  notas → `["\n## ", "\n\n", "\n"]`; livros → `["\n# ", "\n## ", "\n\n", "\n"]`;
  científicos → `["\n## ", "\n\n", ". ", "\n"]` (seções como Abstract/Métodos/Resultados);
  transcrições → `[". ", "! ", "? ", "\n"]` (sem cabeçalhos markdown, fala é contínua);
  artigos web → `["\n\n", "\n", ". "]`. Atualizar `CHUNK_PARAMS` para incluir `separators`.

- [x] **[P4] Detecção e chunk params de artigo científico** — adicionar tipo `"scientific"` em
  `CHUNK_PARAMS` (chunk_size 400, overlap 80 — denso, precisa de mais overlap para não cortar
  mid-argumento). Em `_chunk_type_for()`, detectar via `is_scientific_paper(file_path)`:
  checar frontmatter por `type: scientific` (adicionado pelo AKASHA — ver item AKASHA abaixo),
  ou por presença de seções `Abstract`, `References`/`Referências`, `DOI:` no corpo.

#### AKASHA
- [x] **[P4] Marcar artigos científicos no frontmatter ao arquivar (`services/crawler.py` ou
  `routers/crawler.py`)** — quando o AKASHA fizer download via arxiv (`aioarxiv`) ou de URL
  com indicadores científicos (domínio `arxiv.org`, `pubmed`, `doi.org`, `scholar`, extensão
  `.pdf` com metadados de autor/abstract), adicionar `type: scientific` no frontmatter YAML
  do arquivo `.md` gerado. Isso permite que o Mnemosyne identifique a fonte sem depender de
  subpasta. Verificar onde o AKASHA gera os arquivos `.md` do archive e adicionar o campo lá.

### AKASHA + Mnemosyne: metadados ricos no frontmatter do archive | 2026-05-06
> Contexto: ao arquivar conteúdo, o AKASHA deve incluir metadados estruturados no frontmatter
> YAML dos arquivos .md gerados. Esses metadados são consumidos pelo Mnemosyne para framing
> no prompt, citação correta nas respostas e futura filtragem por tipo/data/idioma.

#### AKASHA
- [x] **Campos universais em todos os arquivos arquivados** — ao gerar o frontmatter .md no
  archive, sempre incluir: `title`, `author` (quando disponível na página/PDF), `date`
  (data de publicação do conteúdo, não de download — formato `YYYY-MM-DD`), `language`
  (`pt`/`en`/etc. — detectar via `langdetect` já no requirements do KOSMOS, ou pelo
  `Content-Language` do HTTP), `source_url` (URL original de onde foi baixado). Esses campos
  são os mais usados pelo Mnemosyne para framing e citação.

- [x] **Campos específicos para artigos científicos** — quando a fonte for identificada como
  científica (arxiv, DOI, Semantic Scholar, OpenAlex), incluir adicionalmente no frontmatter:
  `doi` (ex: `10.48550/arXiv.1706.03762`), `arxiv_id` (quando aplicável, ex: `1706.03762`),
  `journal` (nome do periódico ou `arXiv preprint`), `abstract` (primeiros 500 chars do
  abstract — indexado separadamente melhora a recuperação pois resume o artigo inteiro),
  `keywords` (lista de palavras-chave quando disponíveis). `doi` e `arxiv_id` também servem
  para deduplicação: antes de baixar, verificar se já existe arquivo com o mesmo DOI no
  archive.

- [x] **Campos específicos para PDFs de livros** — quando processar PDF com `pymupdf4llm`,
  extrair metadados nativos do PDF (já acessíveis via `fitz.open(path).metadata`): `isbn`,
  `publisher`, `year`. Incluir no frontmatter apenas quando não-vazios. `year` complementa
  `date` para livros onde só o ano é conhecido.

#### Hermes
- [x] **Campos adicionais no frontmatter de transcrições** — `build_mnemosyne_markdown()` em
  `hermes.py` já inclui `title`, `date`, `source`, `duration`. Adicionar: `platform`
  (`youtube`/`tiktok`/`podcast`/`local` — inferir da URL ou marcar "local" quando arquivo
  local), `channel` (nome do canal/criador quando disponível via yt-dlp `info["uploader"]`
  ou `info["channel"]`). `platform` permite ao Mnemosyne diferenciar um podcast técnico de
  um vídeo de TikTok na hora de pesar a fonte.

#### Mnemosyne
- [x] **Usar `date`, `author`, `language` do frontmatter na detecção e no framing** — em
  `core/loaders.py`, ao carregar arquivos .md, extrair esses campos do frontmatter e
  propagá-los para `doc.metadata`. Em `core/rag.py`, usar `author` e `date` ao montar o
  rótulo de cada chunk no prompt (ex: "Vaswani et al., 2017 — Artigo científico"). Depende
  dos itens AKASHA acima.

### Mnemosyne: auditoria de funcionalidades atuais | 2026-05-06
> Contexto: antes de redesenhar a UI e adicionar novas features, verificar o estado real
> de cada funcionalidade existente no código — quais funcionam, quais estão incompletas,
> quais estão quebradas. Evita assumir que itens marcados [x] no TODO estão operacionais.

#### Mnemosyne
- [ ] **Auditar cada funcionalidade existente do Mnemosyne contra o código real**
  (`Mnemosyne/` — todos os arquivos). Para cada item marcado `[x]` nas Fases do TODO do
  Mnemosyne, verificar no código se: (a) está implementado, (b) é chamado corretamente,
  (c) funciona no fluxo real do app. Registrar resultado como: ✓ funcional / ⚠ parcial
  (descrever o que falta) / ✗ quebrado / ✗ nunca implementado (falso positivo como na
  Fase 7 do AKASHA). Áreas críticas a checar: indexação (IndexWorker), busca RAG
  (`prepare_ask()`), reranking (FlashRank), relatório, mind map, Deep Research Mode,
  Notebook Guide, Knowledge Reflection, session_memory, detecção dinâmica de modelos
  Ollama. Resultado da auditoria orienta o redesign da UI — inútil redesenhar em torno
  de features que não funcionam.

### Mnemosyne: reestruturação urgente da UI | 2026-05-06
> Contexto: a UI atual do Mnemosyne não está intuitiva nem clara para a usuária.
> A referência de design é o NotebookLM (Google) — paradigma tri-pane (Fontes / Chat / Workspace)
> com ancoragem de citações e estado separado por painel. Requer redesign profundo antes de
> continuar adicionando features ao app. Pesquisa de UI/UX em andamento (ver pesquisas.md).

#### Mnemosyne
- [ ] **[URGENTE] Redesenhar a UI completa do Mnemosyne** seguindo o paradigma tri-pane do
  NotebookLM: (1) painel esquerdo de fontes/coleções com status de indexação por item,
  (2) painel central de chat RAG com citações clicáveis, (3) painel direito de notas
  persistentes onde respostas do chat podem ser "promovidas" para registro permanente.
  Antes de implementar: definir o layout alvo com a usuária. A pesquisa de referência
  está em `pesquisas.md` (seções NotebookLM 2026-04-10 e 2026-04-20, e nova sessão 2026-05-06).

### AKASHA: remoção de dead code da Fase 7 (library_urls) e re-crawl periódico | 2026-05-05
> Contexto: o conceito original de "Biblioteca de URLs" (Fase 7) foi supersedido pelo crawler BFS
> da Fase 10. As tabelas library_urls/library_diffs/library_fts nunca foram populadas mas ainda
> existem no schema e geram uma query morta em toda busca local. Além disso, crawl_pending_sites()
> só crawla sites nunca visitados — não re-crawla sites desatualizados.

#### AKASHA
- [x] Remover query morta de library_fts de `services/local_search.py` — `_search_fts()` fazia
      uma segunda query contra `library_fts` (nunca populada) retornando source="BIBLIOTECA";
      essa query executava em toda busca local sem retornar nada útil.
- [x] Adicionar migration v13 em `database.py`: DROP TABLE library_urls, library_diffs, library_fts
      e DROP INDEX idx_library_diffs_url. Remover os DDL constants e chamadas de init_db().
      SCHEMA_VERSION: 12 → 13.
- [x] Estender `crawl_pending_sites()` em `services/crawler.py` para também re-crawlar sites com
      last_crawled_at anterior a 7 dias — hoje a função só processa sites com last_crawled_at IS NULL.

### Caminhos do Mnemosyne: configuração no HUB + editabilidade no próprio app | 2026-05-04

> Contexto: item 0.9 tornou os caminhos do Mnemosyne (watched_dir, vault_dir, chroma_dir)
> somente-leitura no SetupDialog, mas a configuração equivalente ainda não existe no HUB.
> Resultado: não há como definir ou alterar esses caminhos de lugar nenhum.
> extra_dirs também deve ser persistido no ecosystem.json.

#### HUB
- [x] `src/types/index.ts` — atualizar `EcosystemConfig.mnemosyne` para incluir
      `watched_dir`, `vault_dir`, `chroma_dir` (strings) e `extra_dirs` (string[])
- [x] `src/views/SetupView.tsx` — adicionar campos do Mnemosyne em DATA_FIELDS:
      watched_dir ("Mnemosyne — Biblioteca"), vault_dir ("Mnemosyne — Vault"),
      chroma_dir ("Mnemosyne — ChromaDB"); e lista editável de extra_dirs
      (componente separado com add/remove, abaixo dos campos simples)

#### Mnemosyne
- [x] `gui/main_window.py` — SetupDialog: tornar watched_dir, vault_dir e chroma_dir
      editáveis (QLineEdit + botão de seleção de pasta); ao salvar, chamar
      `write_section("mnemosyne", {watched_dir, vault_dir, chroma_dir, extra_dirs})`
      via ecosystem_client — sobrescreve o ecosystem.json
- [x] `gui/main_window.py` — ao salvar extra_dirs, incluí-las também no ecosystem.json
      (campo `extra_dirs: list[str]`) para que o HUB e outros apps saibam quais pastas
      o Mnemosyne está monitorando

### Auditoria pesquisas.md → itens não registrados no TODO | 2026-05-05
> Contexto: leitura completa de pesquisas.md comparada ao TODO revelou 47 lacunas —
> achados de pesquisas anteriores que nunca foram transcritos como itens acionáveis.

#### Mnemosyne
- [x] **[CRÍTICO] Mudar distância ChromaDB de L2 para cosine em todas as coleções**
  (`core/indexer.py`, todos os pontos onde `Chroma(...)` é criado). Adicionar
  `collection_metadata={"hnsw:space": "cosine"}` em cada criação de coleção.
  Para texto, cosine mede direção semântica — L2 mede distância absoluta, o que é
  incorreto para embeddings normalizados. Impacto documentado: até 10× de melhoria
  na qualidade de recuperação. O IndexWorker já apaga e recria o persist_dir, então
  a correção se aplica automaticamente na próxima reindexação. Custo: ~30 min.

- [x] **[CRÍTICO] Aumentar chunk size de 800 → 1800 chars, overlap 100 → 250**
  (`core/config.py`, `RecursiveCharacterTextSplitter`). O valor atual de 800 chars ≈
  200 tokens está abaixo do range recomendado por benchmarks 2025–2026 (Vecta, NAACL
  2025/Vectara: 400–512 tokens). Trocar para `chunk_size=1800, chunk_overlap=250`.
  Ganho documentado: +20pp de acurácia em RAG geral. Requer re-indexação completa.
  Chunking semântico continua desativado (correto — benchmarks mostram fixed-size
  superior para RAG de propósito geral).

- [x] **FlashRank reranking no `prepare_ask()` — pipeline dois estágios**
  (`core/rag.py` ou `core/indexer.py`). Substituir recuperador único por:
  (1) recuperar top-30 por híbrido BM25+cosine; (2) re-rankear com
  `FlashrankRerank(model="ms-marco-MultiBERT-L-12", top_n=5)` de
  `langchain_community.document_compressors`. `pip install flashrank`. Modelo ONNX
  de ~4MB, sem PyTorch, 15–30ms em CPU. Reduz alucinações garantindo que o LLM
  recebe os 5 documentos genuinamente mais relevantes em vez dos 5 melhores por
  similaridade vetorial pura.

- [x] **Deep Research Mode — integração Mnemosyne + AKASHA**
  (novo `core/akasha_client.py` + `core/session_indexer.py` + `gui/workers.py`).
  Quando corpus local insuficiente para responder a query, expandir para web via
  AKASHA: (A) chamar `GET /search/json?q=&max=5` do AKASHA, (B) buscar conteúdo
  de cada URL via `GET /fetch?url=`, (C) indexar transientemente em ChromaDB
  EphemeralClient, (D) RAG sobre corpus local + web combinados, (E) mostrar badges
  de fonte (local vs web) na resposta. Pré-requisito: endpoints `/search/json` e
  `/fetch` no AKASHA (ver itens AKASHA abaixo). ~450 linhas no total.

- [x] **Notebook Guide — sumário + perguntas sugeridas ao indexar documento**
  (`core/indexer.py`, `gui/` componente de detalhe de documento). Ao finalizar
  indexação de um arquivo, chamar LLM para gerar: (a) sumário de 3–5 frases,
  (b) 3–5 perguntas que o usuário poderia fazer sobre o documento. Armazenar em
  metadata do ChromaDB. Exibir na view de detalhe da coleção. Uma call LLM por
  documento no momento da indexação; resultado cacheado. Inspirado no NotebookLM
  "Notebook Guide".

- [x] **Mermaid como MVP do Mind Map (abrir no browser)**
  (`core/mindmap.py`, botão na UI). LLM gera JSON estruturado de temas → converter
  para sintaxe Mermaid → salvar como `.md` → abrir via `webbrowser.open()`. Sem
  dependência de Qt graphics ou graphviz. Compatível com Obsidian. Graphviz/QGraphicsView
  como melhoria posterior. Esta é a decisão de implementação documentada na pesquisa
  NotebookLM — o TODO tem "mind map" mas sem especificar o caminho de implementação.

- [x] **Relatório de Pesquisa estruturado em 8 seções**
  > Parcialmente implementado: `core/report.py` existe com 6 seções (faltam "Análise por fonte" e "Convergências/divergências"). Expandir para 8 conforme especificado.
  (`core/report.py`). Implementar relatório Map-Reduce: (1) Título/escopo, (2) Sumário
  executivo, (3) Temas principais, (4) Análise por fonte, (5) Convergências e
  divergências entre fontes, (6) Lacunas identificadas, (7) Recomendações,
  (8) Referências. Abordagem: LLM por seção (Map) → síntese final (Reduce).
  Export para Markdown; PDF opcional via `pandoc` ou `weasyprint`.

- [x] **Knowledge Reflection — gerar e indexar artefatos de síntese durante indexação**
  (`core/indexer.py`). Após indexar chunks de cada documento, chamar LLM para gerar
  uma "reflexão" — síntese dos top-5 chunks. Armazenar no ChromaDB com
  `metadata["type"]="reflection"` e `metadata["boost"]=1.5`. Durante retrieval em
  `prepare_ask()`, aplicar score boost para documentos de reflexão. Meta-reflexões
  (síntese de 3+ reflexões sobre o mesmo tema) recebem boost 1.8×.

- [x] **`index.json` leve por coleção — metadados sempre em memória**
  (`core/indexer.py`, `core/config.py`). Ao lado do ChromaDB, manter
  `{persist_dir}/index.json` com: `name`, `path`, `total_chunks`, `last_indexed`,
  `file_types` (contagens), `summary` (1 frase gerada por LLM). Carregar no startup
  sem acessar ChromaDB. Usado pela UI para mostrar overview da coleção em <1ms.
  Atualizar a cada operação de indexação.

- [x] **Lock de máquina de indexação — desabilitar indexação em máquinas secundárias**
  (`core/config.py`, `gui/main_window.py`). Adicionar campo `indexing_machine: str`
  ao config (preenchido com hostname na primeira indexação bem-sucedida). Na
  inicialização, se `hostname != indexing_machine`: desabilitar botões de indexação
  e exibir mensagem "Índice construído em [outra máquina]. Consultas disponíveis."
  Enforça arquitetura "indexar no CachyOS, consultar no Windows".

- [x] **`potion-multilingual-128M` (model2vec) como fallback de embedding no Windows**
  (`core/config.py`, `core/indexer.py`, `gui/main_window.py`). Expor como terceira
  opção de embedding em Settings ao lado de bge-m3 e qwen3-embedding:0.6b.
  `pip install model2vec langchain-community`. Sem dependência de Ollama, sem AVX2,
  ~50ms por chunk. MTEB 47.31 — suficiente para RAG pessoal. Útil quando Ollama
  não está disponível no Windows de trabalho.

- [x] **`qwen3-embedding:0.6b` como opção intermediária de embedding**
  (`core/config.py`, `gui/main_window.py`). Adicionar `qwen3-embedding:0.6b`
  (639MB, Q8_0, multilíngue, MTEB ~50–60) como opção selecionável entre bge-m3
  (qualidade) e potion-multilingual-128M (velocidade). Útil no laptop MX150 onde
  bge-m3 cabe em 2GB VRAM mas não deixa espaço para contexto. `ollama pull
  qwen3-embedding:0.6b`, depois `OllamaEmbeddings(model="qwen3-embedding:0.6b")`.

- [x] **`num_thread` por requisição no OllamaEmbeddings (workaround OLLAMA_NUM_THREAD)**
  (`core/indexer.py`). `OLLAMA_NUM_THREAD` é ignorado no Ollama 0.6.6+ (issue #10476).
  Usar parâmetro por requisição: `OllamaEmbeddings(model=..., num_thread=2)` no
  IndexWorker da máquina Windows. Combinado com `QThread.Priority.IdlePriority`.
  Workaround documentado até correção oficial no Ollama.

- [x] **Detecção dinâmica de modelos Ollama no startup (`GET /api/tags`)**
  (`gui/main_window.py`, SetupDialog). Ao iniciar, chamar
  `GET http://localhost:11434/api/tags` (ou via LOGOS se disponível) para listar
  modelos locais. Filtrar em candidatos de embedding (nomic-embed-text*, bge-m3,
  qwen3-embedding*) e chat (llama*, qwen*, mistral*, gemma*). Apresentar listas
  filtradas nos dropdowns de Settings em vez de campos de texto livre. Se Ollama
  não estiver rodando: mostrar aviso e desabilitar features de IA graciosamente.

- [x] **`session_memory.json` — histórico de queries e documentos úteis por coleção**
  > Parcialmente implementado: `core/memory.py` existe mas armazena apenas histórico de conversa (mensagens user/assistant), não rastreia documentos recuperados nem utilidade. Implementar o rastreamento de documentos e score de relevância conforme especificado.
  (`core/memory.py` ou novo `core/session_memory.py`). Armazenar por coleção as
  últimas N queries, quais documentos foram recuperados e se a resposta foi útil.
  Mostrar na UI "Você perguntou algo parecido antes…". Campos por documento:
  `score_relevância_médio` das últimas N queries, `última_vez_retornado`. Implementa
  "Camada 2" da arquitetura de memória de 3 níveis documentada na pesquisa.

- [ ] **Slide deck export (PPTX) a partir de coleção**
  (`core/slidemaker.py`). LLM gera outline (título + 5–7 bullet points por slide
  para cada tema principal) → `python-pptx` monta o arquivo .pptx. `pip install
  python-pptx`. Exportar via botão na área de Relatórios.

- [ ] **FAIR-RAG: feedback implícito — boost/penalizar documentos por utilidade da resposta**
  (`core/rag.py`, `gui/` botão de feedback). Após cada resposta RAG, permitir ao
  usuário marcar como útil/inútil. Se útil: aumentar score de recuperação dos
  documentos usados (média móvel exponencial). Se inútil: penalizar. Armazenar
  ajustes por documento em metadata. O índice melhora gradualmente com o uso.

#### AKASHA
- [ ] **Endpoint `GET /fetch?url=` — busca transiente sem salvar em disco**
  > Parcialmente implementado: existe `POST /fetch` (com body JSON), não `GET /fetch?url=`. Adicionar a variante GET com query param para compatibilidade com clientes simples.
  (`routers/search.py` ou novo `routers/fetch.py`). Buscar e extrair conteúdo de
  uma URL como Markdown e retornar em JSON sem salvar no archive. Equivale ao
  `archiver.py` sem o `dest_path.write_text()`. ~30 linhas. Necessário para o
  Deep Research Mode do Mnemosyne e para qualquer consumidor programático que
  precise do conteúdo sem poluir o archive.

- [x] **Endpoint `GET /search/json?q=&max=` — busca retornando JSON estruturado**
  (`routers/search.py`). A rota `/search` atual retorna HTML (Jinja2). Adicionar
  rota `/search/json` que retorna `[{title, url, snippet, source, date}]` como JSON,
  reutilizando a lógica existente de `search_web()` e `search_local()`. ~20 linhas.
  Necessário para integração com Mnemosyne (Deep Research Mode) e KOSMOS.

- [x] **Propagação de tags do feed para o archive ao auto-arquivar do KOSMOS**
  (`routers/search.py`, endpoint `POST /archive`). Ao receber requisição de
  auto-arquivamento do KOSMOS, aceitar campo `tags: list[str]` no body. KOSMOS
  deve incluir a categoria do feed como tag. Armazenar no frontmatter do arquivo
  Markdown arquivado. Complemento ao item `POST /archive` já rastreado no TODO.

- [ ] **URL normalization antes de inserir no crawl_pages e archive**
  > Parcialmente implementado: `services/crawler.py` já normaliza URLs (lowercase, remove trailing slash). `services/archiver.py` não normaliza — é onde a deduplicação por tracking params faz mais diferença. Implementar em `archiver.py` com remoção de `utm_*`, `fbclid`, `gclid`, `ref`, `source`.
  (`services/archiver.py`, `services/crawler.py`). Normalizar URL com
  `pip install url-normalize` antes de inserir: lowercase scheme+host, remover
  default ports, remover parâmetros de rastreamento (`utm_*`, `fbclid`, `gclid`,
  `ref`, `source`), ordenar query params. Evita arquivar a mesma página com
  tracking params diferentes como documentos separados.

#### KOSMOS
- [ ] **Streaming JSON parcial com field-order optimization (json-stream / ijson)**
  (`app/ui/workers.py`, `_AnalyzeWorker`). Usar `stream=True` com o cliente Ollama
  e parsear a resposta com `pip install json-stream`. Reordenar campos do schema
  para que campos rápidos (tags, sentiment, clickbait_score) venham antes dos lentos
  (entities, five_ws) — XGrammar/Outlines segue a ordem de declaração. A UI pode
  exibir campos rápidos em 0.5–1.5s, antes do JSON completo. Melhor custo-benefício
  que split de calls para este caso.

- [ ] **SpaCy para extração de entidades em vez de LLM (pt_core_news_lg)**
  (`app/core/analyzer.py` ou equivalente). Para o campo `entities`, substituir ou
  complementar a call LLM com SpaCy `pt_core_news_lg` (~250MB). Roda totalmente em
  CPU, trata PER/ORG/LOC/MISC em português, dramaticamente mais rápido que LLM para
  NER. O LLM mantém responsabilidade sobre semantic classification (sentiment, tags,
  clickbait). Resolve a perda de fidelidade de 3–8% documentada em modelos Q4 para
  tarefas de cópia de span como NER. `pip install spacy` +
  `python -m spacy download pt_core_news_lg`.

- [ ] **Heartbeat timeout para análises travadas (`analysis_started_at` + reset no startup)**
  (`app/utils/db.py` ou equivalente). Adicionar coluna `analysis_started_at DATETIME`
  na tabela de artigos. No startup, resetar para `pending` todos os artigos com
  `status = 'in_progress'` e `analysis_started_at < now - 5 minutes`. Evita artigos
  eternamente presos em `in_progress` após kill do processo ou crash.

- [x] **Deduplicação de análise por content hash (SHA-256 de texto normalizado)**
  (`app/core/analyzer.py`, `app/utils/db.py`). Antes de chamar LLM para análise,
  calcular SHA-256 do conteúdo normalizado (minúsculas, sem pontuação/espaços extras).
  Checar se outro artigo tem o mesmo hash — se sim, copiar campos `ai_*` existentes
  em vez de re-chamar o LLM. Adicionar coluna `content_hash TEXT` com índice UNIQUE
  parcial. Economiza calls LLM para artigos cross-posted/espelhados.

- [ ] **Índice parcial SQLite para fila de análise pendente**
  (`app/utils/db.py`, na criação do schema). Adicionar:
  `CREATE INDEX idx_pending_analysis ON articles(feed_id, published_at DESC)
  WHERE analysis_status IN ('pending', 'failed')`.
  SQLite suporta partial indexes desde 3.8.0. Para tabela com 10k artigos onde 95%
  estão analisados, o índice cobre ~500 linhas — query da fila de background passa
  de O(log 10000) para O(log 500).

- [ ] **TTL de campos pesados: nullar five_ws e entities para artigos > 6 meses**
  (`app/core/maintenance.py` ou job periódico). Query mensal:
  `UPDATE articles SET ai_five_ws = NULL, ai_entities = NULL
  WHERE published_at < date('now', '-6 months') AND ai_five_ws IS NOT NULL`.
  Manter ai_tags e ai_sentiment (úteis para filtragem histórica). Seguido de
  `VACUUM` + `ANALYZE`. Mantém o DB SQLite em tamanho gerenciável conforme
  artigos acumulam na casa dos milhares.

- [ ] **Politeness: delay mínimo de 2s por domínio no scraping de artigos**
  > Coberto pelos dois itens `ecosystem_scraper.py` desta seção (throttle adaptativo +
  > HTTP 429), que se aplicam ao KOSMOS ArticleScraper via módulo compartilhado.
  > Implementar apenas se `ArticleScraper` não usar `ecosystem_scraper.py` diretamente.
  (`app/core/scraper.py` ou `ArticleScraper`). Manter dict
  `{domain: last_access_time}` e impor delay de 2s entre requisições ao mesmo
  domínio durante scraping em background. Tratar HTTP 429 com backoff exponencial
  (`base * 2^attempt`, max 60s, ±50% jitter). Sem isso, scraping de 10 artigos do
  mesmo blog em sequência rápida pode disparar bloqueio de IP.

- [ ] **`analysis_schema_version` para invalidação de cache de análise LLM**
  (`app/utils/db.py`, `app/core/analyzer.py`). Adicionar coluna
  `analysis_schema_version INTEGER DEFAULT 0` na tabela de artigos. Definir
  constante `ANALYSIS_VERSION = 1` no código. Incrementar ao mudar prompts ou
  schema. No startup, enfileirar para re-análise todos os artigos com
  `analysis_schema_version < ANALYSIS_VERSION`. Invalida cache sistematicamente
  sem precisar de processo manual.

#### LOGOS / HUB
- [ ] **`OLLAMA_GPU_OVERHEAD=0` no perfil RX 6600 com ROCm**
  > Parcialmente implementado: `OLLAMA_GPU_OVERHEAD` já está definido em `logos.rs` mas com valor 524288000 (524MB), não 0. Avaliar se o OOM handler do ROCm é suficientemente confiável para usar 0, ou se o valor atual é intencional.
  (`HUB/src-tauri/src/logos.rs` ou arquivo de configuração de perfil de hardware).
  Com ROCm na RX 6600, `OLLAMA_GPU_OVERHEAD=524288000` (500MB padrão) pode fazer
  o Ollama recusar carregar modelos que caberiam na VRAM. Definir
  `OLLAMA_GPU_OVERHEAD=0` para o perfil `main_pc` — deixar o OOM handler do ROCm
  atuar em vez da estimativa conservadora do Ollama.

- [ ] **Política de bateria em 3 níveis no LOGOS (Normal / Economia / Crítico)**
  > Parcialmente implementado: lógica de bateria existe mas é binária (AC vs bateria) — sem distinção entre Economia e Crítico. Expandir para 3 níveis com os thresholds documentados.
  (`HUB/src-tauri/src/logos.rs`, módulo de monitoramento de bateria). O TODO tem
  suspensão de P3 em bateria, mas a pesquisa documenta 3 níveis:
  Normal (AC ou bateria >80%): P3 ativo, comportamento padrão.
  Economia (bateria 30–80% ou TimeToEmpty <120min): P3 suspenso, batch P2
  reduzido 64→16, keep_alive P2 "10m"→"2m".
  Crítico (bateria <30% ou TimeToEmpty <60min): P2 também suspenso, apenas P1,
  num_thread=2. Polling UPower a cada 30 segundos.

- [ ] **Detecção de AVX2 no perfil de hardware (i5-3470 sem AVX2)**
  (`HUB/src-tauri/src/logos.rs`, detecção de hardware no startup). Checar presença
  de AVX2 via `/proc/cpuinfo` (Linux) ou cpuid (Windows). Se ausente: forçar perfil
  low com `num_ctx=512`, `num_batch=128`, `num_thread=2`. O i5-3470 é 30–50% mais
  lento que CPUs com AVX2 em inferência INT4 — o perfil deve refletir isso
  explicitamente.

- [ ] **Microbenchmark de startup (20 tokens) para medir t/s real do hardware**
  (`HUB/src-tauri/src/logos.rs`, inicialização do LOGOS). Em vez de inferir
  capacidade do hardware por specs, executar geração de 20 tokens com SmolLM2 1.7B
  no startup. Leva <5 segundos, produz medição direta de tokens/segundo para seleção
  de perfil. Armazenar resultado em config para evitar repetir a cada startup.

- [ ] **Proteção contra thermal throttling da RX 6600 (pausar P3 acima de 85°C)**
  (`HUB/src-tauri/src/logos.rs`). Durante workloads P3 longos, monitorar temperatura
  da GPU via `sysinfo` crate (campo `gpu_temperature` disponível no sysinfo 0.30+).
  Se temperatura > 85°C: pausar P3 automaticamente. Evita depender exclusivamente
  do throttling do driver a 95°C.

- [ ] **`num_gpu` dinâmico por requisição no perfil MX150 (baseado em tamanho do contexto)**
  > Parcialmente implementado: `num_gpu` está definido no perfil MX150 mas como valor estático. Adicionar lógica de seleção por tamanho de contexto conforme documentado.
  (`HUB/src-tauri/src/logos.rs`, dispatch de requisições P1). Para o laptop MX150
  (2GB VRAM), ajustar `num_gpu` dinamicamente: `num_gpu=16–20` para contextos curtos
  (<2048 tokens), `num_gpu=10–12` para contextos longos. LOGOS injeta este parâmetro
  por requisição em vez de usar valor fixo do perfil.

- [ ] **Badge "performance reduzida pelo SO" quando ppd está em power-saver**
  (`HUB/src/` componente LogosPanel). Detectar perfil ativo do Power Profiles Daemon
  (`ppd`). Se `power-saver` ativo: exibir badge no LogosPanel explicando que a
  resposta lenta do LLM é causada pelo modo de economia do sistema operacional, não
  por bug. Evita confusão do usuário quando o laptop está limitado pelo SO.

#### ecosystem_scraper.py
- [ ] **Throttle adaptativo por domínio — delay mínimo de 2s entre requisições**
  (`ecosystem_scraper.py`). Adicionar dict de módulo `{domain: last_request_time}`
  e impor delay configurável (padrão 2s) entre requisições ao mesmo domínio.
  Constante `CRAWL_DELAY` exportável. Como AKASHA archiver e KOSMOS ArticleScraper
  usam este módulo, a politeness é adicionada uma vez e aplica-se a ambos.

- [ ] **HTTP 429 com backoff exponencial + leitura do header Retry-After**
  (`ecosystem_scraper.py`). Detectar resposta HTTP 429 → ler header `Retry-After`
  → backoff `max(Retry-After, min(base * 2^attempt, 60))` com ±50% de jitter
  multiplicativo → retry até `max_retries=3`. Atualmente o módulo não trata 429 —
  retornaria vazio ou lançaria exceção.

#### Hermes
- [ ] **Parâmetros otimizados do faster-whisper: `vad_filter=True`, `beam_size=1`, `language="pt"`**
  > Parcialmente implementado: `vad_filter=True` e `beam_size=1` já estão configurados em `TranscribeWorker`. Falta `language="pt"` — ainda usa detecção automática. Adicionar `language="pt"` como default para eliminar ~1s de overhead por segmento.
  (`hermes.py` ou `TranscribeWorker`). A migração para faster-whisper está concluída
  (`[x]`), mas os parâmetros de otimização não foram registrados: `vad_filter=True`
  filtra silêncio antes da transcrição (grande melhoria de velocidade para vídeos
  com pausas), `beam_size=1` reduz memória e tempo (padrão é 5), `language="pt"`
  elimina overhead de detecção de idioma (~1s por segmento). Definir como defaults
  em `TranscribeWorker`.

- [ ] **Cache do `WhisperModel` entre transcrições (instanciar uma vez por sessão)**
  > Parcialmente implementado: `WhisperModel` é cacheado por instância de `TranscribeWorker`, mas cada nova transcrição cria um novo Worker (e um novo modelo). Mover o cache para nível de módulo ou singleton para compartilhar entre Workers.
  (`hermes.py`). O `WhisperModel` pode ser instanciado uma vez e reutilizado entre
  transcrições (diferente do openai-whisper que recarregava por chamada). Armazenar
  como atributo de classe ou singleton de módulo. Economiza 5–15s de carregamento
  de modelo a cada nova transcrição.
### Infraestrutura: config por dispositivo e sync do ecossistema | 2026-05-06
> Contexto: ecosystem.json é sincronizado via Proton Drive entre máquinas, mas contém
> paths absolutos que diferem entre Windows e Linux. A solução é separar preferências
> (compartilhadas) de paths (locais por máquina).

#### HUB
- [x] **Dividir ecosystem.json em duas camadas: compartilhada e local por máquina**
  Separar o `ecosystem.json` atual em dois arquivos:
  - `ecosystem.json` — preferências e flags (sem paths absolutos); sincronizado via Proton Drive entre máquinas.
  - `ecosystem.local.json` — paths absolutos específicos da máquina (ex: `kosmos_archive`, `hermes_output`, `mnemosyne_watched`); **não sincronizado**, fica só na máquina local.
  Na leitura de configuração, mesclar os dois: `.local.json` tem precedência sobre `.json`.
  Adicionar `ecosystem.local.json` ao `.gitignore` e ao `.stignore` do Syncthing.
  Arquivo `.local.json` de exemplo (com paths comentados) pode ser versionado para documentação.

- [x] **Migrar sync de SQLite (banco do HUB e bancos dos apps) para Syncthing**
  O Proton Drive conflita com SQLite (lock de arquivo / WAL). Usar Syncthing com `.stignore`
  excluindo `*.db`, `*.db-wal`, `*.db-shm`. Syncthing cuida de Markdown, JSON de config,
  pesquisas.md, TODO.md e outros arquivos de texto. Bancos ficam locais por máquina.
  Instalar como serviço ou daemon; configurar par de dispositivos (Windows ↔ CachyOS).

### LOGOS: arquitetura de skill routing multi-agente via arquivos .md | 2026-05-12
> Contexto: pesquisa sobre o padrão Agent Skills Specification (Anthropic, out/2025) e
> arquitetura two-model router (RouteLLM, arXiv:2406.18665) revelou um caminho viável para
> o LOGOS orquestrar tarefas por tipo usando arquivos .md como definição de habilidades.
> Dispatcher pequeno (3B, sempre aquecido) + executor maior (7B+) por skill.

#### LOGOS
- [x] **Estrutura `logos/skills/` com SKILL.md por tipo de tarefa** — criar diretório
  `logos/skills/` no HUB. Cada skill é um arquivo `<nome>.md` com frontmatter YAML obrigatório:
  `name` (slug, max 64 chars) e `description` (max 1024 chars — descreve QUANDO usar o skill,
  não apenas o que faz; é o único campo lido pelo dispatcher na fase de seleção). Corpo Markdown
  com: (a) instruções completas de execução; (b) 2-4 pares few-shot input→output; (c) output
  format especificado explicitamente com exemplo de JSON; (d) instrução final "responda APENAS
  no formato especificado". Skills iniciais: `rag-query.md`, `synthesis.md`,
  `entity-extraction.md`, `chunk-classification.md`. Padrão diretamente compatível com
  Agent Skills Specification (agentskills.io).

- [x] **Dispatcher com dois modelos** — implementar `logos/dispatcher.py`: modelo router 3B
  (ex: Llama 3.2 3B Instruct) sempre aquecido em memória (`keep_alive: -1` via Ollama) recebe
  o request e retorna JSON `{"skill": "<nome>", "confidence": 0.0-1.0}`. Usar Pydantic +
  `format=SkillSelection.model_json_schema()` no Ollama Python SDK para forçar enum de skill
  names válidos e garantir JSON válido. Fallback para skill genérico se `confidence < 0.7`.
  Modelo executor 7B+ carregado sob demanda com `keep_alive` curto conforme prioridade LOGOS
  (P1/P2/P3). Overhead do dispatcher: 200–600 ms; latência total com modelos aquecidos: 1–3 s.
  Basear na arquitetura RouteLLM (arXiv:2406.18665, ICLR 2025).

- [x] **Routing 3-tier para minimizar overhead de LLM** — antes de acionar o dispatcher LLM,
  implementar dois filtros mais rápidos: (1) regex/keyword matching para requests triviais e
  repetitivos (~80% dos casos, latência ~0 ms — ex: "resuma esse texto" → sempre `synthesis`);
  (2) embedding similarity contra embeddings pré-computados dos campos `description` de cada
  skill (para requests ambíguos mas estruturados, latência ~50 ms); (3) LLM dispatcher apenas
  para casos que passem pelos dois filtros anteriores. Essa cadeia elimina o overhead do LLM
  para a maioria dos requests, reduzindo latência média do sistema.

- [x] **Command R 7B como executor do skill `rag-query`** — o Command R 7B (Cohere) é o único
  modelo sub-10B com treinamento explícito para grounded generation com citação de fontes
  (grounding spans). Configurar o LOGOS para usar Command R 7B especificamente quando o
  dispatcher selecionar o skill `rag-query`, em vez do modelo executor padrão. Requer que
  o Command R 7B esteja disponível via Ollama (`ollama pull command-r`). Consumo: ~5 GB VRAM
  em Q4_K_M — cabe na RX 6600 com margem.

### AKASHA: responsividade CSS e frontmatter enriquecido | 2026-05-12
> Contexto: o AKASHA usava apenas breakpoints de pixels fixos no CSS — comportamento quebrando em janelas de tamanhos intermediários não convencionais. Além disso, o frontmatter gerado nos arquivos arquivados carecia de campos essenciais para citação (data de publicação real, idioma, campos científicos completos, metadados de PDF).

#### AKASHA
- [x] **Responsividade CSS universal** — substituir breakpoints de largura fixa (`max-width: Xpx`) por layout fluido usando `clamp()`, `min()`, percentagens e `flex-wrap` natural. Containers (`search-wrapper`, `container`, `lenses-page`, `history-container`) devem usar `min()` com percentagem + max fixo em vez de `max-width: Npx` rígido. `topbar-search` deve ter `min-width` em percentagem. Eliminar saltos visuais entre breakpoints: o layout deve degradar suavemente em qualquer largura de janela, não só em 3-4 tamanhos canônicos.

- [x] **Frontmatter: acrescentar `description`, `sitename`, `tags` da página** — em `archive_url()`, extrair via trafilatura `metadata.description` (meta description / OpenGraph), `metadata.sitename` (nome legível do site, ex: "The Verge") e `metadata.tags`/`metadata.categories` (tags nativas da página); mesclar tags nativas com as tags do usuário (usuário vem primeiro, depois tags da página não duplicadas). Adicionar `description` e `sitename` como campos novos no frontmatter.
- [x] **Campos universais em todos os arquivos arquivados** — em `archive_url()` em `archiver.py`, renomear `url` para `source_url` no frontmatter, mudar `date` para data de publicação real do conteúdo (trafilatura `metadata.date`, formato `YYYY-MM-DD`) e adicionar campo separado `archived_at` com a data de download. Garantir que `author` e `language` sempre presentes (mesmo que vazios). Em `archive_pdf()`, mesma lógica: `source_url` em vez de `url`, `archived_at` para data de download, `language` detectado via `langdetect.detect(content_md[:2000])`.

- [x] **Campos específicos para artigos científicos** — em `archive_url()`, quando `is_scientific=True`, incluir no frontmatter: `doi`, `arxiv_id`, `journal`, `abstract` (primeiros 500 chars do abstract extraído), `keywords` (lista quando disponíveis via trafilatura ou metadados OpenGraph). Deduplicação antes de baixar: verificar via `database.get_archived_by_doi(doi)` se já existe arquivo com mesmo DOI; se sim, retornar sem baixar novamente.

- [x] **Campos específicos para PDFs de livros** — em `archive_pdf()`, usar `fitz.open(path).metadata` (já disponível via pymupdf4llm) para extrair `isbn`, `publisher`, `year`; incluir no frontmatter apenas quando não-vazios. `year` complementa `date` para livros onde só o ano de publicação é conhecido.

### Mnemosyne: novos formatos de entrada — Kindle e imagens | 2026-05-06
> Contexto: pesquisa sobre eBook Kindle (AZW/AZW3/MOBI) e leitura de imagens em pipeline RAG
> revelou opções viáveis sem dependências pesadas. AZW/MOBI via `mobi` (PyPI, sem nativas);
> imagens via Tesseract local + fallback Ollama vision.

#### Mnemosyne
- [x] **Suporte a `.azw`, `.azw3`, `.mobi` em `core/loaders.py`** — adicionar função `_load_mobi()`
  que usa `mobi.extract(file_path, tmpdir)` num `tempfile.TemporaryDirectory`. A saída pode ser:
  HTML (MOBI) → BeautifulSoup como no EPUB; EPUB (AZW3) → reutilizar `_load_epub()`; PDF
  (AZW Print Replica) → reutilizar `PyPDFLoader`. Adicionar `.azw`, `.azw3`, `.mobi` em
  `_SUPPORTED_EXTENSIONS`. Em caso de DRM detectado (output vazio ou corrompido), retornar
  `DocumentLoadError` com mensagem "arquivo com DRM — não é possível indexar". Dependência:
  `pip install mobi`.

- [x] **Suporte a imagens (`.jpg`, `.jpeg`, `.png`, `.webp`) em `core/loaders.py`** — adicionar
  função `_load_image()` com duas camadas: (1) Tesseract via `pytesseract` + `Pillow` como
  caminho principal (rápido, sem GPU, compatível com i5-3470); (2) fallback para Ollama vision
  (`/api/generate` com `images: [base64]`) usando o modelo configurado em `config.image_ocr_model`
  (default vazio = Tesseract only). Texto extraído vira um `Document` com metadata `source`,
  `source_type` e `ocr_engine` ("tesseract" ou "ollama:{model}"). Adicionar `.jpg`, `.jpeg`,
  `.png`, `.webp` em `_SUPPORTED_EXTENSIONS`. Dependência: `pip install pytesseract Pillow`
  + Tesseract instalado no sistema (instrução no README). Campo `image_ocr_model` em
  `AppConfig` e `SetupDialog` (QLineEdit, opcional, placeholder "ex: moondream2").

### LOGOS: pull de modelo recomendado direto do HUB | 2026-05-13
> Contexto: o LOGOS detecta hardware e recomenda modelos (via /logos/hardware), mas não
> oferece forma de baixar o modelo caso ele ainda não esteja instalado no Ollama local.

#### HUB
- [x] **Comando Tauri pull_model(model_name) em src-tauri/src/logos.rs** — executar
  ollama pull <model> como processo filho e emitir evento Tauri pull_progress com
  cada linha de stdout (progresso em tempo real). Retornar erro tipado se Ollama não
  estiver rodando ou se o nome do modelo for inválido.

- [x] **Botão "Baixar modelo" na LogosView** — quando o LOGOS recomendar um modelo via
  /logos/hardware que não constar em GET /api/tags do Ollama local, exibir botão
  "⬇ Baixar [nome]" ao lado da recomendação. Ao clicar: invocar pull_model, exibir
  barra de progresso com texto da linha atual do ollama pull, desabilitar o botão
  durante o download.
### HUB: botão Iniciar Ollama com flags de hardware | 2026-05-13
> Contexto: o LOGOS já gerencia o Ollama após iniciado, mas o usuário precisa iniciar o processo manualmente antes de usar o ecossistema. O HUB deve detectar o hardware e lançar o Ollama com as variáveis de ambiente corretas por plataforma — AMD ROCm no CachyOS, CUDA/sem flags no laptop NVIDIA e no Windows CPU-only.

#### HUB
- [x] **`launch_ollama()` em `commands/launcher.rs`** — comando Tauri assíncrono que: (1) verifica se o Ollama já responde em `localhost:11434/api/tags` (reqwest, timeout 500ms); se sim, retorna `"already_running"`. (2) Constrói o `Command` com as flags de hardware: Windows → `ollama serve` (sem flags); Linux com `/dev/kfd` presente (AMD ROCm) → `ollama serve` com `env("HSA_OVERRIDE_GFX_VERSION", valor_da_env_ou_"10.3.0")`; Linux sem `/dev/kfd` (NVIDIA ou CPU) → `ollama serve` sem flags. (3) Spawn sem janela (`CREATE_NO_WINDOW` no Windows). Retorna `"launched"` ou `AppError::Io`.
- [x] **Registrar `launch_ollama` em `lib.rs`** — adicionar ao `tauri::generate_handler![]`.
- [x] **`launchOllama()` em `src/lib/tauri.ts`** — wrapper tipado: `call<string>('launch_ollama')`.
- [x] **Botão na `LogosView.tsx`** — adicionar estado `ollamaOnline: boolean | null` (derivado de polling direto a `localhost:11434/api/tags` via `listModels()` do `ollama.ts`, a cada 4s); estado `launchStatus: 'idle' | 'starting' | 'error'`. Renderizar botão "Iniciar Ollama" visível apenas quando `ollamaOnline === false`; durante `starting` mostra "Iniciando…" e fica desabilitado; erro volta para "Iniciar Ollama" após 3s. Posicionar na seção "Ações" ao lado do botão "Silenciar Ollama".

### CODEX — Leitor centralizado do ecossistema | 2026-05-13
> Contexto: leitor read-only centralizado que suporta todos os formatos do ecossistema e centraliza highlights, notas e citações em markdown. Inspirado no leitor do KOSMOS, mas KOSMOS mantém seu próprio leitor. Apps como AKASHA e Mnemosyne podem abrir arquivos diretamente no CODEX. Deve ter versão Android no futuro — por isso a stack é **Tauri v2 + React + Rust** (mesma do HUB, toolchain já disponível). Sem edição de texto — apenas leitura, comentários, highlights e exportação de citações em MD.

#### CODEX — Fase 0: scaffold e design system
- [ ] **Criar projeto Tauri v2 em `CODEX/`** — `cargo tauri init` dentro da pasta do projeto; estrutura: `CODEX/src/` (React + TypeScript), `CODEX/src-tauri/` (Rust). `strict: true` no tsconfig. Copiar design system do AETHER/HUB sem modificações: `tokens.css`, `animations.css`, `typography.css`, `components.css`, `CosmosLayer.tsx`, `Toast.tsx`, `ThemeToggle.tsx`.
- [ ] **Pasta sincronizada no Proton Drive** — `{sync_root}/codex/` com: `annotations.db` (SQLite com highlights, notas, citações vinculadas ao path do arquivo), `exports/` (citações exportadas em MD). Apenas anotações são sincronizadas — o conteúdo dos arquivos permanece onde está. No `ecosystem.json`, adicionar seção `codex: { exe_path, sync_dir }`. O HUB deve incluir CODEX na barra de apps.
- [ ] **Registrar CODEX no ecosystem.json** — escrever `write_section("codex", { exe_path, sync_dir })` no startup. Adicionar `"codex"` ao `auto_discover_all_exe_paths()` no `launcher.rs` do HUB.

#### CODEX — Fase 1: abertura de arquivos e formatos
- [ ] **Suporte a MD e TXT** — leitura nativa em Rust via `std::fs::read_to_string`. MD renderizado como HTML no frontend via `react-markdown`. TXT exibido como texto pré-formatado.
- [ ] **Suporte a PDF** — usar crate `pdf-extract` (`pdf-extract = "0.7"` no Cargo.toml) para extração de texto por página. Renderização no frontend como HTML paginado. Alternativa para PDFs com layout complexo: PDF.js via `<webview>` ou iframe — avaliar conforme qualidade de extração.
- [ ] **Suporte a EPUB** — usar crate `epub` (`epub = "2"`) para iterar capítulos como HTML. Renderizar cada capítulo como seção navegável no frontend. Preservar imagens internas via data URI.
- [ ] **Suporte a DOCX** — usar crate `docx-rs` (`docx-rs = "0.4"`) para extração de parágrafos e estilos básicos (negrito, itálico, cabeçalhos). Converter para HTML estruturado antes de enviar ao frontend.
- [ ] **Suporte a HTML** — para arquivos do archive do AKASHA (`.html`): renderizar diretamente na webview do Tauri (CSP permissiva para arquivos locais). Sanitizar links externos para não abrir no leitor.
- [ ] **Seletor de arquivo** — janela principal com `tauri-plugin-dialog` para abrir arquivo, filtrado por extensão suportada. Estado inicial exibe tela de boas-vindas com drag-and-drop.

#### CODEX — Fase 2: anotações e highlights
- [ ] **SQLite para anotações** — `rusqlite` com tabelas: `highlights(id, file_path, start_char, end_char, color, created_at)`, `notes(id, file_path, start_char, text, created_at)`, `citations(id, file_path, start_char, end_char, excerpt, note, created_at)`. Path do DB: `{sync_dir}/annotations.db`. Schema migrations versionadas.
- [ ] **Seleção de texto e menu de contexto** — no frontend, capturar `mouseup` para detectar seleção de texto; exibir mini-toolbar com opções: "Highlight", "Nota", "Citar". Highlight aplica `<mark>` com cor configurável; Nota abre textarea inline; Citar abre modal de citação.
- [ ] **Paleta de cores para highlights** — 5 cores fixas alinhadas ao design system: âmbar (`#F5C518`), verde (`var(--accent-green)`), azul (`var(--accent)`), rosa (`var(--ribbon)`), cinza (`var(--rule)`). Seleção via mini-toolbar.
- [ ] **Persistir e restaurar highlights** — ao abrir arquivo, consultar `annotations.db` por `file_path` e reinjetar highlights via `document.execCommand` ou substituição de HTML. Para MD/TXT (offsets de char), usar `start_char`/`end_char`. Para PDF (offsets por página), usar `page_num + start_char`.

#### CODEX — Fase 3: exportação e integração
- [ ] **Exportar citação como MD** — botão "Exportar citação" em cada anotação; gera arquivo `.md` em `{sync_dir}/exports/` com frontmatter: `source_path`, `source_title`, `page` (se PDF), `date_cited`. Corpo: trecho entre aspas duplas + nota do usuário abaixo. Um arquivo por sessão de citação (agregado por data).
- [ ] **Mecanismo "abrir no CODEX"** — CODEX lê `ecosystem.json` em `codex.open_request: { path, start_char? }` no startup e ao ganhar foco. Após abrir, limpa o campo com `write_section("codex", { open_request: null })`. Outros apps escrevem nesse campo para solicitar abertura. Também aceitar CLI arg `--open <path>` para lançamento direto.
- [ ] **Botão "Abrir no CODEX" no AKASHA** — no frontend do AKASHA (`archive_detail.html` ou equivalente), adicionar botão que escreve no `ecosystem.json` e depois faz `fetch` para lançar o CODEX via endpoint do HUB ou diretamente via `open` shell.
- [ ] **Botão "Abrir no CODEX" no Mnemosyne** — no `_source_viewer` do Mnemosyne (`gui/main_window.py`), adicionar botão que escreve no `ecosystem.json` e lança o CODEX com `subprocess.Popen`.
- [ ] **KOSMOS: CODEX como leitor externo** — em KOSMOS `gui/reader_window.py` (ou equivalente), adicionar opção "Abrir no CODEX" no menu do artigo aberto que usa o mesmo mecanismo de `open_request`.

#### CODEX — Fase 4: Android (futuro)
- [ ] **Configurar ambiente Tauri Android** — Android Studio + NDK + `cargo tauri android init`. O Tauri v2 já suporta Android nativamente; a UI React é a mesma.
- [ ] **Adaptar UI para toque** — aumentar áreas de toque (mínimo 44×44px), toolbar de anotação acessível por toque longo, scroll suave. Avaliar gestos: swipe para trocar capítulos (EPUB), pinch-to-zoom.
- [ ] **Sync de anotações via Syncthing** — `annotations.db` em pasta monitorada pelo Syncthing; resolver conflitos por timestamp (mais recente vence).
- [ ] **Build APK de release** — `cargo tauri android build`; testar no dispositivo alvo.

### HUB LOGOS: modelos disponíveis + parar Ollama + prioridade baixa no Windows | 2026-05-13
> Contexto: a lista de modelos no LOGOS mostrava apenas os carregados na VRAM. O usuário quer ver todos os modelos instalados com indicador de status por cor (verde = ativo na VRAM, amarelo = disponível mas não carregado), poder parar o Ollama pelo LOGOS, e no Windows lançar o Ollama com prioridade de CPU abaixo do normal automaticamente.

#### HUB
- [x] **`OllamaModelEntry` em `logos.rs`** — novo struct serializável com campos: `name: String`, `status: String` ("active" | "available"), `size_vram_mb: u64` (VRAM usada; 0 se não carregado), `size_disk_mb: u64` (tamanho em disco da `/api/tags`).
- [x] **`do_list_all_models()` em `logos.rs`** — faz duas chamadas ao Ollama: (1) `GET /api/ps` para modelos carregados → mapa `name → size_vram`; (2) `GET /api/tags` para todos os instalados → lista completa. Mescla: se o modelo está em `/api/ps` → status "active"; se só em `/api/tags` → status "available". Retorna `Vec<OllamaModelEntry>`.
- [x] **`logos_list_all_models` em `commands/logos.rs`** — comando Tauri que chama `do_list_all_models`.
- [x] **`stop_ollama()` em `commands/launcher.rs`** — mata o processo Ollama: Windows → `taskkill /F /IM ollama.exe /T` (com `CREATE_NO_WINDOW`); Linux → `pkill -f "ollama serve"`. Retorna `Ok(())` se o comando foi executado (mesmo que Ollama não estivesse rodando).
- [x] **Prioridade baixa no Windows em `build_ollama_serve_command()`** — substituir `Command::new("ollama").arg("serve")` na branch Windows por `cmd /C start "" /belownormal /B ollama serve`, que instrui o Windows a lançar o processo já com `BELOW_NORMAL_PRIORITY_CLASS` sem necessidade de `windows-sys`.
- [x] **Registrar novos comandos em `lib.rs`** — adicionar `logos_list_all_models` e `stop_ollama` ao `generate_handler![]`.
- [x] **`OllamaModelEntry` em `types/index.ts`** — interface TypeScript espelhando o struct Rust.
- [x] **`logosListAllModels()` e `stopOllama()` em `lib/tauri.ts`** — wrappers tipados.
- [x] **LogosView.tsx: lista de todos os modelos com bolinha colorida** — substituir a seção "Modelos na memória" por "Modelos Ollama" que usa `logosListAllModels()` (polling a cada 4s). Cada linha: `●` colorido (verde `var(--accent-green)` se "active", amarelo `var(--accent)` se "available") + nome + tamanho em disco + VRAM usada se "active". Botão "descarregar" mantido para modelos "active".
- [ ] **LogosView.tsx: botão "Parar Ollama"** — visível apenas quando `ollamaOnline === true`. Clique chama `stopOllama()`, aguarda 1s e atualiza `checkOllama()`. Colocar na seção Ações junto ao "Iniciar Ollama".


### HUB LOGOS: configuração de modelos por app com recomendação de hardware | 2026-05-13
> Contexto: o LOGOS já detecta o hardware e define perfis de modelo padrão (ex: qwen2.5:7b para Mnemosyne no PC principal). Mas não há UI para a usuária sobrescrever essas escolhas diretamente no LOGOS, nem indicador de "compatibilidade" entre o modelo escolhido e o hardware disponível. A usuária quer poder ver e editar os modelos de cada app no LOGOS, com o recomendado como padrão, e o LOGOS deve calcular se o modelo escolhido cabe no hardware atual.

#### HUB — Backend Rust
- [x] **Struct `ModelAssignment` em `logos.rs`** — campos: `app: String`, `model: String`, `model_type: String` ("llm" | "embed"), `recommended: String` (modelo recomendado pelo perfil), `is_custom: bool` (true se a usuária substituiu o recomendado), `fits_hardware: bool` (calculado), `vram_required_mb: u64` (estimado), `vram_available_mb: u64` (do hardware atual). Serializado para o frontend.
- [x] **Endpoint `GET /logos/model-assignments` no servidor Axum** — retorna `Vec<ModelAssignment>` com todas as atribuições atuais (LLM e embedding de cada app). Calcula `fits_hardware` comparando o tamanho em disco do modelo (de `/api/tags`) com a VRAM disponível (de `vram_usage()`), usando a heurística: VRAM_necessária ≈ size_disk_mb × 0.6 para Q4 (índice de compressão típico). `fits_hardware = vram_required_mb <= vram_available_mb - 500` (500 MB de buffer).
- [x] **Endpoint `POST /logos/model-assignments` no servidor Axum** — recebe `{ app, model_type, model }` e sobrescreve a atribuição para aquele app. Persiste em `ecosystem.json` na seção `logos.model_overrides: { [app_model_type]: model }` (ex: `mnemosyne_llm`, `kosmos_embed`). Se o modelo recebido for igual ao recomendado, remove o override (volta ao padrão).
- [x] **Tauri commands `logos_get_model_assignments` e `logos_set_model_assignment`** — wrappers IPC que chamam os endpoints do servidor Axum (ou acessam o estado interno diretamente, sem HTTP).
- [x] **Registrar comandos em `lib.rs`**.

#### HUB — Frontend TypeScript
- [x] **Interface `ModelAssignment` em `types/index.ts`** — espelha o struct Rust.
- [x] **Wrappers `logosGetModelAssignments` e `logosSetModelAssignment` em `lib/tauri.ts`**.
- [x] **Seção "Modelos por app" na `LogosView.tsx`** — lista cada app (Mnemosyne LLM, Mnemosyne Embedding, KOSMOS LLM, KOSMOS Embedding) com: nome do modelo atual + badge "recomendado" se `!is_custom`; indicador de compatibilidade (✓ verde se `fits_hardware`, ✗ vermelho com tooltip de VRAM necessária vs disponível se não couber); botão "editar" que abre um `<select>` com todos os modelos instalados (de `logosListAllModels()`); botão "usar recomendado" visível apenas quando `is_custom === true`.


### LOGOS: pesquisa de LLMs por funcionalidade e hardware | 2026-05-13
> Contexto: os modelos recomendados no LOGOS devem ser escolhidos com base no que
> cada funcionalidade precisa (RAG multi-doc no Mnemosyne, analise de artigos no KOSMOS,
> extracao de conteudo no AKASHA, embedding multilingue) e no que o hardware suporta,
> garantindo que o mesmo app funcione bem em todos os computadores com modelos compativeis.
> Antes de pesquisar, catalogar os modelos instalados em cada maquina.

#### HUB
- [x] **Inventario Windows 10 (WorkPc):** all-minilm:latest (45 MB), smollm2:1.7b (1.8 GB), qwen2.5:0.5b (397 MB)
- [x] **Inventario CachyOS principal (MainPc):** phi3.5:latest (2.2 GB), gemma2:2b (1.6 GB), qwen2.5:7b (4.7 GB), llama3.1:8b (4.9 GB), bge-m3:latest (1.2 GB)
- [x] **Inventario Laptop (i7-8550U, MX150 2GB):** nomic-embed-text:latest (274 MB), SmolLM2:1.7B (1.8 GB), gemma2:2b (1.6 GB)
- [x] **Pesquisar LLMs para RAG (Mnemosyne)** -- sintese multi-doc, context window, portugues;
  garantir que os modelos escolhidos por hardware sejam compativeis (mesma familia ou instruction format)
- [x] **Pesquisar LLMs para analise/sumarizacao (KOSMOS e AKASHA)** -- artigos longos, velocidade
  de streaming; no MainPc o modelo KOSMOS pode ser diferente do Mnemosyne para rodar simultaneamente
- [x] **Pesquisar modelos de embedding multilingues** -- qualidade pt/en, velocidade por hardware;
  bge-m3 vs nomic-embed-text vs all-minilm vs potion-multilingual-128M
- [x] **Pesquisar LLMs para extração de conteúdo (AKASHA)** — AKASHA não tem slot LLM ainda;
  avaliar se precisa e qual seria o modelo (extração de metadados, resumo de página web).
  A pesquisa de sumarização acima cobre parcialmente — registrar decisão explícita de
  incluir ou não um slot AKASHA nos perfis do LOGOS.
- [x] **Atualizar perfis em `logos.rs`** após pesquisa — `rationale_for_model()`; possivelmente
  adicionar slot AKASHA; garantir que modelos escolhidos para o mesmo app em diferentes
  hardwares sejam da mesma família ou arquitetura compatível (ex: todos Qwen, todos Gemma,
  ou todos instruction-tuned com mesmo prompt format)

### KOSMOS: análise em background não atualiza cards + bugs de silêncio | 2026-05-14
> Contexto: usuária deixou KOSMOS aberto por horas e nenhum card exibiu resultado de análise.
> Investigação revelou dois bugs estruturais e um comportamento de retry ausente.

#### KOSMOS
- [x] **Conectar sinal `article_analyzed` na MainWindow** — o `BackgroundAnalyzer` emite
  `article_analyzed(article_id, data)` após cada análise bem-sucedida, mas o sinal nunca foi
  conectado a nada. Cards nunca se atualizam em tempo real. Fix: em `main_window.py`, após
  `_bg_analyzer.start()`, conectar `_bg_analyzer.article_analyzed` a um handler que chame
  `_feed_list.update_card_analysis(article_id, data)` e
  `_unified_feed.update_card_analysis(article_id, data)`. Ambas as views precisam do método
  `update_card_analysis()` que encontra o card pelo ID e chama `card.update_analysis()`.
  O `ArticleCard` precisa dos métodos `update_analysis(sentiment, clickbait, relevance, tags)`
  e `update_title(text)` para atualizar badges/estilo sem reconstruir o widget.
- [x] **Mudar `log.debug()` para `log.warning()` nas falhas de análise** — em
  `background_analyzer.py` linhas 159 e 264, erros de análise (Ollama offline, JSON inválido,
  timeout) são registrados como DEBUG. Se o nível de log for INFO ou superior (padrão comum),
  nenhuma falha aparece. Mudar para `log.warning()` para que falhas fiquem visíveis no log.
- [x] **Retry periódico de artigos não analisados** — `get_unanalyzed_article_ids()` só é
  chamado no startup e em `feed_updated`. Se Ollama estava offline no startup e voltou depois,
  os artigos ficam pendentes para sempre. Fix: adicionar `QTimer` em `main_window.py` que
  dispara a cada 5 minutos, chama `get_unanalyzed_article_ids(limit=50)` e enfileira no
  `_bg_analyzer` se houver pendentes e IA estiver habilitada.

### KOSMOS: barra de status, persistência de traduções e integração com novos downloads | 2026-05-14
> Contexto: melhorias de UX e robustez no fluxo de análise e tradução em background do KOSMOS,
> identificadas durante a implementação dos fixes de análise e I.3.

#### KOSMOS
- [x] **Barra de status no rodapé do KOSMOS** — adicionar `QStatusBar` ou widget fixo no rodapé
  da `MainWindow` para exibir progresso e erros. Deve mostrar: "Analisando X artigos…" durante
  análise em background; "Traduzindo títulos…" durante tradução; erros de Ollama como
  "⚠ Falha ao analisar artigo 42: conexão recusada" (com timestamp); "✓ N artigos analisados"
  ao concluir lote. O `BackgroundAnalyzer` deve emitir sinais de progresso (`progress(int, int)`
  para atual/total) além do `article_analyzed`. O `TitleTranslator` idem. A barra some após
  alguns segundos de inatividade (QTimer de 5s para limpar mensagens de conclusão).
- [x] **Persistência das traduções de títulos** — salvar `dict[article_id, translated_title]`
  em `data/title_cache_{lang}.json` ao fechar o app (serializar `TitleTranslator._cache`).
  Carregar no startup em `TitleTranslator.__init__()`. Assim traduções já feitas não repetem
  chamadas à API ao reabrir o KOSMOS. Invalidar entradas para artigos deletados periodicamente
  (cruzar com IDs da DB a cada startup).
- [x] **Pausar tradução ao abrir artigo, retomar ao fechar** — em `MainWindow`, ao navegar
  para o reader (`_on_article_clicked`, `_on_unified_article_clicked`, etc.), chamar
  `self._title_translator.pause()`; ao voltar (`_on_reader_back`), chamar
  `self._title_translator.resume()`. Isso libera recursos de rede enquanto o reader está ativo.
- [x] **Enfileirar tradução e análise de novos artigos baixados** — em `_on_feed_updated()`,
  além de enfileirar análise (já feito), também enfileirar tradução dos novos artigos:
  buscar os artigos recém-baixados pelo feed_id, construir a lista de `(id, title, language)`
  e chamar `_on_translation_requested()` diretamente (sem depender de `_populate_cards` ser
  chamado, pois a view pode não estar visível no momento).

### KOSMOS: I.3 — Tradução automática dos títulos nos cards | 2026-05-14
> Contexto: implementação da funcionalidade de tradução de títulos dos cards conforme TODO I.3.
> Cards devem mostrar títulos no idioma configurado em `display_language`; tradução ocorre
> em background ao abrir o feed, sem bloquear a UI.

#### KOSMOS
- [x] **Adicionar campo `display_language: ""` ao `config.py`** — string vazia significa sem
  tradução; qualquer código ISO (ex: `"pt"`, `"en"`) ativa a tradução dos títulos dos cards
  para aquele idioma. Distinto de `default_translation_lang` que é do reader.
- [x] **Criar `app/core/title_translator.py`** — `TitleTranslator(QThread)` com fila e cache
  em memória (`dict[article_id, translated_title]`). Emite `title_translated(int, str)`.
  Ao mudar `target_lang`, limpa o cache. Roda com prioridade BELOW_NORMAL. Se artigo já está
  no idioma alvo (detectado via `article.language` do frontmatter ou código do feed), emite
  o título original sem chamar a API.
- [x] **Adicionar seletor de `display_language` na `settings_view.py`** — combo com opções:
  "Original (sem tradução)" + idiomas de `TARGET_LANGUAGE_NAMES` do `translator.py`. Persiste
  em `config.set("display_language", code)`.
- [x] **Atualizar cards em tempo real durante tradução** — `ArticleCard.update_title(text)`
  atualiza `self._title_lbl.setText(text)`. Views (`feed_list_view`, `unified_feed_view`)
  expõem `update_card_title(article_id, translated)` para o handler do sinal.
- [x] **Iniciar tradução ao carregar cards** — em `_populate_cards()` de ambas as views,
  após criar os cards, emitir sinal `translation_requested(list[tuple[int,str,str|None]])`
  com `(article_id, title, article.language)` de cada artigo. MainWindow conecta esse sinal
  ao `TitleTranslator.enqueue_batch()`.

### Mnemosyne: multi-coleção com query unificada | 2026-05-14
> Contexto: o modelo atual de "coleção ativa" faz o RAG consultar apenas uma fonte por vez.
> O comportamento correto é consultar todas as coleções habilitadas simultaneamente e rankear
> os resultados pelos pesos de source_type já existentes (scientific > book > library > transcript).

#### Mnemosyne
- [x] **`core/indexer.py` — `load_all_vectorstores(config)`** — nova função que retorna
  `list[tuple[Chroma, CollectionConfig]]` para todas as coleções habilitadas (`coll.enabled`
  e `coll.exists`). Substituir o uso de `load_vectorstore(config)` (single-active) por esta
  função nos workers de query. Manter `load_vectorstore` para compatibilidade com indexação.

- [x] **`core/rag.py` — retrieval multi-vectorstore** — modificar `query_rag()` e as funções
  internas `_hybrid_retrieve`, `_multi_query_retrieve`, `_hyde_retrieve`, `_iterative_retrieve`
  para aceitar `vectorstores: list[tuple[Chroma, CollectionConfig]]` em vez de um único `Chroma`.
  Lógica: rodar retrieval em cada vectorstore separadamente, juntar os candidatos, deduplicar
  por conteúdo idêntico (`doc.page_content`), aplicar os pesos de `SOURCE_WEIGHTS` existentes
  no ranking final. BM25 continua sendo um índice único por coleção — agregar scores ponderados.

- [x] **`gui/main_window.py` — carregar todos os vectorstores no init** — em `_post_config_init`,
  substituir `load_vectorstore(config)` por `load_all_vectorstores(config)` e armazenar em
  `self.vectorstores: list[tuple[Chroma, CollectionConfig]]`. Passar a lista para todos os
  workers de query (AskWorker, SummaryWorker, FAQWorker etc.).

- [x] **`gui/main_window.py` — "Indexar tudo"** — o botão deve: (1) iterar sobre todas as
  coleções habilitadas, (2) deletar o `chroma_db` de cada uma (`shutil.rmtree(coll.persist_dir,
  ignore_errors=True)`), (3) re-indexar cada uma sequencialmente chamando `build_vectorstore`
  para cada coleção com seu `watched_dir` e `persist_dir` respectivos.

- [x] **`gui/main_window.py` — botão "Ativar" → "Habilitar/Desabilitar"** — renomear e mudar
  comportamento: em vez de setar `active_collection`, faz toggle em `coll.enabled` e salva
  config. Coleções desabilitadas são excluídas da query unificada. Remover toda lógica de
  `active_collection` da query (manter apenas para fallback de indexação).

- [x] **`core/watcher.py` / `core/idle_indexer.py` — watcher multi-coleção** — o watcher atual
  monitora só `config.watched_dir` (coleção ativa). Atualizar para monitorar os paths de
  todas as coleções habilitadas. Cada arquivo novo recebe `source_type` da sua coleção.

### Pesquisa: Extração de Temas, Visualização Interativa, Perguntas Follow-up e Persona RAG | 2026-05-14
> Contexto: funcionalidades de descoberta de conhecimento e experiência de usuário para o Mnemosyne:
> (1) extrair temas dos documentos indexados e exibi-los como nuvem de palavras e mapa mental
> interativo clicável; (2) sugerir perguntas de follow-up após cada resposta; (3) mecanismos de
> aprendizado além do Knowledge Reflection existente; (4) persona de bibliotecária especialista.

#### Mnemosyne

- [x] **`core/topic_extractor.py` — extração de temas com BERTopic + KeyBERT** — criar módulo
  `TopicExtractor` que recupera embeddings e textos do ChromaDB via
  `collection.get(include=["embeddings","documents","metadatas"])` (reutilizando os vetores já
  calculados, sem reprocessar arquivos), aplica UMAP + HDBSCAN + c-TF-IDF (pipeline BERTopic)
  para extrair tópicos do corpus inteiro, e KeyBERT por documento para keywords individuais.
  Para corpora < 30 documentos, usar só c-TF-IDF sem clustering (mais estável). Parâmetro
  `min_cluster_size = max(2, len(docs)//50)`. Salvar resultado em
  `{coll.mnemosyne_dir}/topics.json` com: lista de tópicos (top-10 palavras + scores), mapeamento
  `doc_id → topic_id`, e keywords por documento. Dependências: `bertopic`, `keybert[base]`
  (Model2Vec, sem PyTorch), `umap-learn`, `hdbscan`. Disparar após indexação completa e ao
  clicar em botão "Atualizar temas" na aba Temas.

- [x] **`gui/topics_view.py` — aba "Temas" com nuvem de palavras clicável** — nova aba no
  `QStackedWidget` principal. Sub-modo "Nuvem": gera imagem via `wordcloud.WordCloud
  .generate_from_frequencies(freq_dict).to_image()`, converte para `QPixmap` e exibe em
  `QLabel`. Overlay de clique: usar `WordCloud.layout_` para mapear coordenadas de cada
  palavra na imagem, sobrepor `QGraphicsScene` transparente com `QGraphicsRectItem` invisíveis
  nas bounding boxes; `mousePressEvent` detecta qual palavra foi clicada e emite sinal
  `theme_clicked(str)`. A `MainWindow` conecta `theme_clicked` → disparar query no chat
  "Fale sobre [tema]: o que os documentos do acervo dizem?".

- [x] **`gui/topics_view.py` — mapa mental interativo com QGraphicsScene + NetworkX** — sub-modo
  "Mapa" na mesma aba: construir grafo NetworkX com nós de tópico (cor azul) e nós de documento
  (cor cinza), arestas indicando pertencimento ao cluster. Calcular posições via
  `nx.kamada_kawai_layout()`. Renderizar no `QGraphicsScene`: nós como `QGraphicsEllipseItem`
  com label `QGraphicsTextItem`, arestas como `QGraphicsLineItem`. Nós respondem a clique via
  `mousePressEvent` em subclasse de `QGraphicsEllipseItem`: nós de tópico → disparam query
  no chat; nós de documento → abrem o arquivo no gerenciador de arquivos (`os.startfile` no
  Windows, `xdg-open` no Linux). Não usar pyvis/WebEngine para evitar dependência extra de
  ~100 MB. Usar `QGraphicsView` com zoom via `wheelEvent` (fator 1.15×) e pan via drag com
  botão do meio.

- [x] **`gui/workers.py` — `SuggestQuestionsWorker(QThread)` para perguntas follow-up** — worker
  separado que inicia logo após o `AskWorker` terminar (conectar ao sinal `finished` do
  AskWorker no `main_window.py`). Recebe: pergunta do usuário, resposta gerada, e os 3
  primeiros chunks recuperados (contexto). Monta prompt pedindo 3 perguntas de aprofundamento
  que: explorem aspectos não cobertos, conectem com outros documentos, ou peçam exemplos.
  Temperatura 0.9. Emite `questions_ready(list[str])`. Só executa se `suggest_questions: bool`
  estiver True na config.

- [x] **`gui/main_window.py` — exibir chips de perguntas sugeridas no chat** — ao receber
  `questions_ready(list[str])`, criar 3 `QPushButton` compactos com `setObjectName("chip")`
  e CSS rounded (border-radius 12px, padding 4px 10px) logo abaixo da última resposta no
  `QScrollArea` do chat. Ao clicar, inserir texto no campo de input e submeter. Os chips são
  **persistentes** — não têm timer e não somem automaticamente; são removidos apenas quando
  o usuário envia uma nova mensagem manualmente (o `QWidget` dos chips da mensagem anterior
  é destruído quando a próxima resposta chega). Comportamento idêntico ao NotebookLM. Adicionar
  toggle `suggest_questions` nas Settings (padrão: False — opt-in).

- [x] **`core/knowledge_graph.py` — grafo de conhecimento inter-documentos** — módulo
  `KnowledgeGraph` que extrai entidades de cada chunk indexado usando KeyBERT (top-5 keywords
  por chunk) e constrói um grafo de co-ocorrência com NetworkX: nós são entidades/keywords,
  arestas são documentos que compartilham a mesma entidade com peso = número de documentos
  em comum. Persistir em `{coll.mnemosyne_dir}/knowledge_graph.json` (nodes + edges como
  JSON serializable). Método `KnowledgeGraph.score(query_keywords, docs)` re-ranqueia
  candidatos do retrieval somando grau de conectividade das entidades da query com cada
  documento — documentos mais "centrais" na rede de conhecimento recebem boost. Método
  `KnowledgeGraph.get_neighbors(entity)` retorna documentos e entidades relacionadas (para
  o mapa mental). Disparar `KnowledgeGraph.update(new_chunks)` no `_on_index_finished`.

- [x] **`core/config.py` — campo `persona_prompt: str` com persona Mnemosyne** — adicionar
  campo ao `AppConfig` com default sendo o prompt completo da assistente Mnemosyne (ver texto
  na pesquisa em `pesquisas.md` — sessão "Extração de Temas..." de 2026-05-14, seção 5.2).
  O nome da assistente é **Mnemosyne** (não "Mnemê"). Persistir em `local_config.json`. Em
  `core/rag.py`, injetar `config.persona_prompt` como primeira seção do system message em
  todos os chains (`AskWorker`, `SummarizeWorker`, `FAQWorker`, `GuideWorker`). A seção de
  persona precede a instrução de formato e o contexto RAG — nunca sobrescrever instruções de
  formato com a persona.

- [x] **`gui/settings_view.py` — editor de persona nas Settings** — adicionar `QTextEdit`
  expansível (min 120px height) com label "Personalidade do assistente" na seção de
  configurações LLM. Botão "Restaurar padrão" restaura o prompt da Mnemosyne. A edição
  é salva imediatamente em `local_config.json` via `config.set("persona_prompt", text)`.
  Exibir preview: ao clicar "Testar persona", disparar uma query de teste ("Olá, apresente-se")
  e exibir a resposta numa caixa de diálogo.

### Pesquisa: NotebookLM — Funcionalidades e Evolução 2025–2026 | 2026-05-14
> Contexto: pesquisa do NotebookLM revelou três problemas no Mnemosyne: (1) Studio volátil —
> outputs sobrescrevem uns aos outros e somem ao fechar; (2) fragmentação — Resumo/FAQ/Guide
> são sub-páginas separadas mas são todos outputs gerados por LLM, deveriam ser tipos do Studio;
> (3) chat sem persistência — conversas se perdem ao fechar o app. Decisão arquitetural:
> chat = notebook, sempre salvo. Studio outputs = arquivos independentes com metadados de
> autoria (Mnemosyne os trata como "reflexões próprias" e o ecossistema pode indexá-los).

#### Mnemosyne

- [x] **`core/studio_output.py` — dataclass `StudioOutput` com persistência como arquivo** —
  criar dataclass com campos: `id: str` (UUID4), `type: str` (Briefing/FAQ/Guide/Flashcards/etc.),
  `title: str` (gerado ou editável), `content: str`, `table_data: list[list[str]] | None`,
  `created_at: str` (ISO 8601), `collection_name: str`, `notebook_id: str | None`. Método
  `to_markdown_file(path)` salva em `{coll.mnemosyne_dir}/studio/{id}.md` com frontmatter YAML:
  `source: mnemosyne_studio`, `type: studio_output`, `studio_type: {type}`, `collection: {name}`,
  `created_at: {dt}`, `notebook_id: {id}`. O frontmatter marca o arquivo como gerado pela própria
  Mnemosyne — o indexador deve reconhecer `source: mnemosyne_studio` e atribuir `source_type`
  especial (ex: `"thought"`) com weight próprio em `SOURCE_WEIGHTS`, para que a Mnemosyne saiba
  que está consultando seus próprios "pensamentos" e não uma fonte externa.

- [x] **`core/studio_store.py` — camada de persistência dos outputs do Studio** — `StudioStore`
  com métodos: `save(output: StudioOutput)`, `load_all(collection_name) → list[StudioOutput]`,
  `delete(id)`, `get(id) → StudioOutput`. Lê/escreve de `{coll.mnemosyne_dir}/studio/`. Ao
  carregar, lê os arquivos `.md` e faz parse do frontmatter YAML. O diretório é criado
  automaticamente se não existir. `load_all` retorna lista ordenada por `created_at` decrescente.

- [x] **`gui/studio_tile_widget.py` — card de output do Studio** — `StudioTileWidget(QWidget)`
  exibindo: badge colorido com o tipo (cor diferente por tipo — Briefing azul, FAQ verde,
  Guide roxo, Flashcards laranja, etc.), título truncado em 1 linha, preview das primeiras
  80 chars do conteúdo, data/hora. Dois botões no hover: ✏ abrir output completo (abre
  `StudioOutputDialog`), 🗑 deletar (confirmação). Emite `output_opened(StudioOutput)` e
  `output_deleted(str)`.

- [x] **`gui/main_window.py` — Studio tab redesenhado como galeria de tiles** — substituir o
  `studio_result_text` (`QTextEdit` único) por um `QScrollArea` com `QFlowLayout` (ou
  `QVBoxLayout`) de `StudioTileWidget`. Os controles de geração (combo tipo + botão Gerar)
  permanecem no topo. Ao clicar "Gerar": (1) executa `StudioWorker` como antes; (2) ao
  terminar, cria `StudioOutput`, persiste via `StudioStore`, adiciona novo tile no topo
  da galeria. Ao inicializar, carrega tiles existentes via `StudioStore.load_all()`. Remover
  os botões "Exportar .md" e "Exportar CSV" da area central — movê-los para o `StudioOutputDialog`.

- [x] **`gui/main_window.py` — unificar Resumo e FAQ como tipos do Studio** — mover as
  sub-páginas "Resumo" e "FAQ" da aba Análise para dentro do Studio como tipos no combo:
  adicionar "Resumo" e "FAQ" ao `studio_type_combo`. Remover as sub-páginas separadas
  `_pill_summary` e `_pill_faq` e seus respectivos `QTextEdit`. O conteúdo gerado passa
  a persistir como `StudioOutput` como qualquer outro tipo. A sub-página "Guide" permanece
  separada por ter comportamento interativo próprio (perguntas clicáveis + pérolas
  escondidas), mas ganha também um botão "Salvar no Studio" que cria um `StudioOutput`
  do tipo Guide com o conteúdo gerado.

- [x] **`core/rag.py` / `core/indexer.py` — reconhecer outputs do Studio como fonte especial** —
  adicionar `"thought"` a `SOURCE_WEIGHTS` (ex: 1.3 — acima de transcript, abaixo de book)
  e ao fallback de `source_type` no loader. No `MnemosyneLoaders`, arquivos com frontmatter
  `source: mnemosyne_studio` recebem `metadata["source_type"] = "thought"` automaticamente.
  Isso permite que respostas do RAG possam citar "Conforme anotado na análise anterior…"
  ao recuperar um output do Studio — a Mnemosyne fica "ciente" de seus próprios pensamentos.

- [x] **`gui/main_window.py` — botão "Salvar no Studio" nas respostas do chat** — cada bloco
  de resposta da Mnemosyne no `QScrollArea` do chat recebe um botão compacto "⊕ Studio" no
  canto inferior direito. Ao clicar, abre diálogo com combo de tipo (Análise, Citação,
  Anotação) e campo de título editável. Confirmar cria `StudioOutput` com o texto da resposta
  e salva via `StudioStore`. O tile aparece imediatamente na galeria do Studio.

- [x] **`gui/main_window.py` — Flashcards como tipo do Studio com progresso** — adicionar
  "Flashcards" ao `studio_type_combo`. O `StudioWorker` para tipo Flashcards manda prompt
  ao LLM pedindo 10-15 pares pergunta/resposta sobre os documentos indexados (formato JSON).
  O `StudioOutput` para Flashcards guarda `content` como JSON de cards e `table_data` como
  `progress: {card_id: "correct"|"wrong"|"unseen"}`. Ao abrir um tile de Flashcards, exibe
  `FlashcardsDialog`: cards um por vez com `QStackedWidget` (frente = pergunta, verso =
  resposta), botões "Acertei ✓" e "Errei ✗" que atualizam o progresso e salvam via
  `StudioStore.save()`, shuffle do deck, filtro "Só erros". Progresso persiste entre sessões.

- [x] **`gui/main_window.py` — Guide como tipo do Studio** — adicionar "Guide" ao
  `studio_type_combo` (além de manter a sub-página Guide da Análise). Ao gerar, cria
  `StudioOutput` do tipo Guide com o conteúdo completo (resumo + perguntas + pérolas).
  O tile do Guide, ao ser aberto, exibe as perguntas como chips clicáveis que disparam
  query no chat — mesma interatividade da sub-página Guide, mas agora persistindo o
  conteúdo entre sessões.

- [x] **`core/notebook_store.py` + `core/notebook.py` — notebooks temáticos persistentes** —
  Decisão arquitetural: **chat = notebook**. Cada notebook é uma conversa temática salva.
  Dataclass `Notebook`: `id: str` (UUID4), `name: str`, `created_at: str`, `updated_at: str`,
  `collection_names: list[str]` (coleções que este notebook consulta; vazio = todas habilitadas),
  `description: str`. Cada notebook tem diretório próprio em
  `{data_dir}/notebooks/{id}/` com: `metadata.json`, `history.jsonl` (mensagens), `memory.json`
  (contexto de sessão). Os outputs do Studio de um notebook ficam em
  `{data_dir}/notebooks/{id}/studio/`. `NotebookStore` com: `create(name, collections) → Notebook`,
  `list_all() → list[Notebook]`, `load(id) → Notebook`, `save(notebook)`, `delete(id)`.

- [x] **`gui/notebooks_panel.py` — painel de notebooks na sidebar** — `NotebooksPanel(QWidget)`
  exibido na parte superior (ou como seção colapsável) da sidebar esquerda. Mostra lista de
  notebooks como itens clicáveis com nome + data da última mensagem. Botão "+" cria novo
  notebook (pede nome; default "Notebook {data}"). Clique num notebook: `MainWindow` carrega
  o notebook selecionado (muda histórico do chat, memória, tiles do Studio). Ícone de lixeira
  por item (com confirmação). O notebook ativo fica destacado com cor de seleção.

- [x] **`gui/main_window.py` — carregar/salvar histórico do chat por notebook** — ao trocar de
  notebook: (1) salvar `history.jsonl` e `memory.json` do notebook atual antes de trocar;
  (2) carregar `history.jsonl` do novo notebook e renderizar as mensagens no `QScrollArea`
  do chat; (3) carregar `memory.json` e repassar ao contexto de memória do RAG; (4) recarregar
  tiles do Studio do notebook novo. A cada nova mensagem enviada/recebida, acrescentar linha
  ao `history.jsonl` do notebook ativo (append-only, nunca sobrescrever). Ao fechar o app
  (`closeEvent`), salvar estado final.

- [x] **`gui/main_window.py` — painel de histórico navegável** — botão "Histórico" ou ícone
  no chat que abre um `QDialog` listando todas as mensagens do notebook atual agrupadas por
  data. Filtro de busca por texto. Clicar numa mensagem rola o `QScrollArea` do chat até
  aquela mensagem (scroll to anchor). Não é necessário "restaurar" sessões antigas — o
  histórico inteiro já está no scroll do chat.

- [x] **`core/loaders.py` — suporte a EPUB** — adicionar `EpubLoader` usando a biblioteca
  `ebooklib`. Extrai capítulos como documentos separados (um `Document` por capítulo) com
  metadados de frontmatter: `title` (livro), `chapter` (nome do capítulo), `author`,
  `source_type: "book"`. HTML de cada capítulo é limpo via BeautifulSoup antes de chunking.
  Registrar `.epub` na lista de extensões suportadas em `loaders.py` e no `IndexWorker`.
  Dependências: `ebooklib`, `beautifulsoup4` (já deve estar instalado).

- [x] **Studio — tipo "Infográfico" (estruturado)** — adicionar "Infográfico" ao
  `studio_type_combo`. O `StudioWorker` para tipo Infográfico manda prompt ao LLM pedindo
  extração estruturada dos dados principais em formato adequado para visualização: estatísticas
  chave, lista de entidades com atributos, relações causais, linha do tempo. O output é
  renderizado como HTML estático (template com CSS grid/flexbox) e salvo como `StudioOutput`
  com `content` = HTML. Ao abrir o tile, exibe o HTML num `QWebEngineView` dentro do
  `StudioOutputDialog`. Exporta como `.html`. Não depende de modelos de geração de imagem —
  é puramente texto estruturado + CSS visual.

### HERMES: extrator de receitas de vídeo | 2026-05-14
> Contexto: nova aba no HERMES para extrair receitas estruturadas de vídeos online (YouTube
> e outros sites suportados pelo yt-dlp). Fluxo: URL → yt-dlp (info + legendas ou áudio) →
> Whisper como fallback de transcrição → LLM extrai ingredientes/preparo/dicas → salva como
> Markdown com frontmatter YAML incluindo `type: recipe` para identificação pelo ecossistema.

#### HERMES

- [x] **`services/recipe_extractor.py` — pipeline de extração** — criar módulo com função
  `extract_recipe(url: str, config: AppConfig) → RecipeResult`. Passo 1: chamar yt-dlp
  (`yt_dlp.YoutubeDL`) para extrair metadados do vídeo (título, channel, duration, upload_date,
  thumbnail, webpage_url, extractor_key) e tentar baixar legendas automáticas/manuais
  (`writesubtitles=True, writeautomaticsub=True, subtitleslangs=["pt","en","*"]`) sem baixar
  o vídeo (`skip_download=True`). Passo 2: se legenda encontrada, usar como transcrição direta;
  se não, baixar áudio (`format="bestaudio"`) e transcrever com `WhisperModel` (reuso do
  modelo já instanciado no HERMES — singleton de módulo, conforme item de cache já no TODO).
  Passo 3: chamar LLM via Ollama com prompt de extração estruturada (JSON schema:
  `{ingredients: list[str], steps: list[str], tips: list[str], recipe_name: str}`).
  Temperatura 0.2 para minimizar alucinações. Passo 4: montar `RecipeResult` com todos os
  campos. Tratar `except DownloadError` e `except json.JSONDecodeError` com tipagem explícita.

- [x] **`services/recipe_extractor.py` — suporte a playlists** — `RecipePlaylistExtractor`
  que usa `yt_dlp.YoutubeDL` com `extract_flat=True` para listar entradas da playlist sem
  baixar. Retorna `list[str]` de URLs individuais. O worker GUI itera sobre elas chamando
  `extract_recipe()` por item, emitindo `progress(current, total, current_title)` a cada
  conclusão. Falhas por item são registradas como `RecipeResult(error=str)` e não abortam
  o lote — todos os vídeos são processados independentemente.

- [x] **Output Markdown com frontmatter `type: recipe`** — o `RecipeResult` é serializado
  por função `to_markdown(result) → str`. Frontmatter YAML obrigatório:
  `type: recipe` (identificador para o ecossistema), `title`, `source_url`, `source_platform`
  (valor de `extractor_key` do yt-dlp, ex: `"youtube"`), `channel`, `duration_seconds`,
  `language` (idioma detectado na transcrição), `published_date` (formato `YYYY-MM-DD` do
  `upload_date` do yt-dlp), `thumbnail`, `extracted_at` (data ISO 8601 local).
  Corpo Markdown com seções: `## Ingredientes` (lista `- item`), `## Modo de Preparo`
  (lista numerada `1. passo`), `## Dicas` (lista `- dica`, omitida se vazia).
  Arquivo salvo como `{slug-do-titulo}-{YYYYMMDD}.md` em `config.recipes_dir`.

- [x] **`gui/recipe_tab.py` — aba "Receitas" no HERMES** — nova `QWidget` adicionada ao
  `QTabWidget` principal do HERMES. Componentes: `QLineEdit` para URL com placeholder
  "Cole a URL do vídeo ou playlist…" + botão "Extrair"; label de status que aparece após
  colar URL ("YouTube · Identificado: [Título]" ou "Playlist: N vídeos detectados") via
  chamada prévia ao yt-dlp com `extract_flat=True` e timeout 5s; `QProgressBar` visível
  durante extração (modo indeterminado para vídeo único, determinado para playlist com
  current/total); `QTextEdit` read-only com preview do Markdown gerado após conclusão;
  botão "Salvar" ativo após extração bem-sucedida (salva em `config.recipes_dir`); botão
  "Limpar" reseta tudo. Para playlists, exibir lista de resultados com status por item
  (✓ / ✗) num `QListWidget` acima do preview.

- [x] **`gui/workers.py` — `RecipeExtractWorker(QThread)`** — worker que encapsula
  `extract_recipe()` (vídeo único) ou `RecipePlaylistExtractor` (playlist). Sinais:
  `progress(int, int, str)` (atual, total, título), `recipe_ready(RecipeResult)` (por
  item concluído), `finished()`, `error(str)`. Rodando com `QThread.Priority.LowPriority`
  para não bloquear a UI. Conectar `started` e `finished` aos botões da aba
  (desabilitar "Extrair" durante processamento).

- [x] **`core/config.py` — campo `recipes_dir: str`** — adicionar ao `AppConfig` com
  default `str(Path.home() / "hermes_recipes")`. Expor no `SetupDialog` do HERMES como
  campo editável com botão de seleção de pasta. Também registrar em `ecosystem.json`
  na seção `hermes` para que outros apps saibam onde estão as receitas.

#### HUB
- [x] **`src/views/SetupView.tsx` — campo "HERMES — Pasta de Receitas"** — adicionar
  `hermes.recipes_dir` ao `DATA_FIELDS` do SetupView, label "HERMES — Receitas",
  tipo `path`. Segue o mesmo padrão dos outros campos de path do Hermes já presentes.

### AKASHA + KOSMOS: dados configurados pelo usuário em JSON (resilência a crash do DB) | 2026-05-14
> Contexto: quando o banco SQLite corrompe, o usuário perde toda a lista de sites, favoritos,
> lista negra e fontes do KOSMOS — dados insubstituíveis que precisariam ser recadastrados
> manualmente. Solução: separar "dados configurados pelo usuário" (imutáveis, preciosos) de
> "dados derivados" (indexados, crawleados, analisados — podem ser reconstruídos). Os dados
> configurados vivem em arquivos JSON versionados pelo Syncthing/Proton Drive; o banco é
> populado a partir deles no startup e funciona como cache de trabalho.

#### AKASHA

- [x] **`services/user_data.py` — camada de persistência JSON para dados configurados** —
  criar módulo com classe `UserData` responsável por ler e escrever os 5 arquivos JSON de
  dados do usuário em `{data_dir}/`:
  `sites.json` (lista de sites da Biblioteca — campos de `crawl_sites`: `base_url`, `label`,
  `crawl_depth`, `subdomains`, `created_at`),
  `blocked_domains.json` (lista negra — campo `domain` com `added_at`),
  `favorites.json` (domínios favoritos — campo `domain` com `added_at`),
  `lenses.json` (lentes de busca configuradas — campos `name`, `description`, `filters_json`),
  `watch_later.json` (lista de URLs para ler depois — campos `url`, `title`, `added_at`).
  Cada arquivo é um array JSON raiz. Métodos `load_{entity}() → list[dict]` e
  `save_{entity}(items: list[dict])` para cada tipo. Escrita atômica: escrever em `.tmp`,
  depois `os.replace()` para evitar corrupção parcial. `save_*` é chamado sempre que o
  usuário adiciona, edita ou remove um item — antes de qualquer operação no banco.

- [x] **`database.py` — `populate_from_user_data()` no startup** — nova função assíncrona
  chamada em `init_db()` após criar as tabelas. Carrega cada JSON via `UserData.load_*()` e
  faz `INSERT OR IGNORE` (por `base_url`/`domain`/`name` como chave de unicidade) em
  `crawl_sites`, `blocked_domains`, `favorite_domains`, `lenses` e `watch_later`.
  Direção única: JSON → DB (o banco nunca sobrescreve o JSON no startup). Isso garante que
  mesmo após deletar o banco, todos os dados configurados pelo usuário ressurgem na próxima
  abertura.

- [x] **`routers/crawler.py` e `routers/library.py` — escrever JSON em toda mutação** —
  em cada endpoint que adiciona, edita ou remove sites (`POST /library/sites`,
  `DELETE /library/sites/{id}`, `PATCH /library/sites/{id}`), chamar
  `await UserData.save_sites(await get_all_sites_as_dicts())` após a operação no banco.
  Mesma lógica para endpoints de blacklist (`/settings/blocked`), favoritos
  (`/settings/favorites`), lentes (`/lenses`) e watch_later (`/watch-later`).
  Padrão: banco é atualizado primeiro; se sucesso, JSON é atualizado; se JSON falhar,
  logar warning mas não reverter a operação do banco (o banco é a fonte de verdade em runtime).

- [x] **Migração única: exportar DB existente para JSON na primeira abertura** — em
  `populate_from_user_data()`, verificar se cada arquivo JSON já existe; se **não** existir
  e a tabela correspondente tiver dados no banco, exportar para JSON (sensu inverso). Isso
  garante que usuários com banco funcional não percam dados na transição — os JSONs são
  criados automaticamente na primeira abertura com a nova versão do código.

#### KOSMOS

- [x] **`app/core/feed_store.py` — persistência JSON para feeds e categorias** — criar módulo
  `FeedStore` com dois arquivos JSON em `{data_dir}/`:
  `feeds.json` (array de objetos com campos: `url`, `title`, `category_name`, `update_interval`,
  `enabled`, `added_at`),
  `categories.json` (array de objetos com: `name`, `color`, `order`).
  Métodos: `load_feeds() → list[dict]`, `save_feeds(feeds: list[dict])`,
  `load_categories() → list[dict]`, `save_categories(cats: list[dict])`.
  Escrita atômica via `.tmp` + `os.replace()`. `save_feeds` é chamado após toda operação de
  adicionar/editar/remover feed; `save_categories` idem para categorias.

- [x] **`app/core/database.py` — `populate_feeds_from_store()` no startup** — após
  `Base.metadata.create_all()`, chamar função que lê `FeedStore.load_feeds()` e
  `FeedStore.load_categories()` e faz `INSERT OR IGNORE` (por `url` como chave única para
  feeds, `name` para categorias) nas tabelas ORM correspondentes. Garante que feeds
  sobrevivem a qualquer corrupção ou deleção do banco SQLite.

- [x] **`app/core/feed_manager.py` — escrever JSON em toda mutação de feed** — em cada
  método que adiciona, edita ou remove feeds (`add_feed()`, `remove_feed()`,
  `update_feed()`) e categorias (`add_category()`, `remove_category()`), chamar
  `FeedStore.save_feeds()` / `FeedStore.save_categories()` após a operação no banco.
  Mesmo padrão do AKASHA: banco primeiro, JSON depois.

### AKASHA + Mnemosyne: inteligência evolutiva e diálogo inter-app | 2026-05-16
> Contexto: o AKASHA aprende com o conteúdo que indexa e constrói uma persona interna; a
> Mnemosyne idem com o vault. Ambos expõem essa inteligência num "diálogo visível" (estilo
> chain-of-thought) quando a usuária pedir — o AKASHA pensa em voz alta sobre o que encontrou,
> a Mnemosyne interpola com o vault, o stream aparece em tempo real na UI da Mnemosyne.

#### AKASHA

- [x] **SOURCE_WEIGHTS — sistema de pesos por fonte** (`services/local_search.py`). Adicionar
  dict `SOURCE_WEIGHTS: dict[str, float]` com: PAPER=2.0, HIGHLIGHT=1.6, AKASHA=1.4,
  KOSMOS=1.2, OBSIDIAN=1.2, MNEMOSYNE=1.1, HERMES=1.0, DEPOIS=1.0. Modificar `_rrf()` para
  receber `weight_fn: Callable[[SearchResult], float]` e multiplicar o score RRF acumulado
  pelo peso da fonte antes de ordenar. `search_local()` passa
  `weight_fn=lambda r: SOURCE_WEIGHTS.get(r.source, 1.0)`. Artigos científicos (PAPER)
  têm o peso máximo porque são fontes primárias com maior densidade informacional.

- [x] **KnowledgeWorker — inteligência passiva em background** (`services/knowledge_worker.py`
  novo; `database.py` SCHEMA_VERSION 30; `main.py`; `routers/crawler.py`;
  `routers/search.py`; `services/local_search.py`).
  Novas tabelas: `page_knowledge (url PK, title, summary, topics JSON, entities JSON,
  source_type, processed_at)` e `topic_interest_profile (topic PK, score REAL, query_count,
  last_updated)`. Módulo `knowledge_worker.py`: `KnowledgeQueue` (`asyncio.Queue maxsize=200`);
  `schedule_page(url, title, content, source_type)` enfileira sem bloquear; `process_queue()`
  loop background (P3 — pausa se Ollama ocupado) que chama Ollama com prompt estruturado
  `{"summary": "1-2 frases", "topics": [...], "entities": [...]}` e armazena em
  `page_knowledge`; `_update_interest_profile(topics)` incrementa scores com TF-IDF simples;
  `schedule_search_update(query, snippets)` extrai tópicos da busca sem LLM e atualiza perfil;
  `apply_knowledge_boost(results, query)` boost de resultados cujos tópicos em `page_knowledge`
  se sobrepõem à query (multiplicador sobre score existente). Integrações: `crawler.py`
  chama `schedule_page()` pós-crawl; `search.py` chama `schedule_page()` pós-archive e
  `schedule_search_update()` pós-busca; `search_local()` chama `apply_knowledge_boost()` após
  RRF + usage boost. `main.py`: `asyncio.create_task(process_queue())` no lifespan.

- [x] **Persona persistente — AKASHA** (`services/persona.py` novo; `database.py`
  SCHEMA_VERSION 31; `services/local_search.py`). Tabela `persona (key PK, value, updated_at)`.
  Dataclass `AppPersona(self_description: str, expertise_topics: list[str],
  interaction_style: str, formed_at: str)`. Job diário (`_rebuild_persona()`) que lê
  `topic_interest_profile` top-10 e chama Ollama com prompt: "Com base nesses tópicos e
  frequências, descreva em 3 frases quem você é como sistema de busca, em primeira pessoa."
  — resultado armazenado como `self_description`. `get_persona() -> AppPersona` expõe o
  estado atual. Injetar persona no prompt de `_expand_query_llm()` como prefixo: "Contexto:
  {self_description}. " — apenas quando persona estiver formada (não vazia).

- [x] **Endpoint de diálogo** (`routers/dialogue.py` novo; registrar em `main.py`).
  `POST /dialogue/turn` recebe `{question: str, context: list[str], turn_index: int}` da
  Mnemosyne via `ecosystem_client`. Executa: FTS5 search na query + lookup em `page_knowledge`
  pelos tópicos relevantes + carrega persona. Gera stream SSE de "thought fragments" curtos
  (1-3 frases cada) via Ollama — o AKASHA "pensa em voz alta" sobre o que encontrou, sempre
  ancorando em fontes reais. Retorna também `sources: list[{url, title}]` junto com o stream.
  Exceção controlada ao princípio de amplificador: o AKASHA gera texto neste endpoint, mas
  para a Mnemosyne (não para a usuária diretamente); todo texto é ancorado em snippets reais
  do índice, sem especulação. Comentário explícito no código documenta essa exceção.

#### Mnemosyne

- [x] **Persona persistente — Mnemosyne** (`core/persona.py` novo; banco de dados da
  Mnemosyne). Mesmo padrão do AKASHA: tabela `persona`, dataclass `AppPersona`. Job que
  roda após cada lote de Knowledge Reflection — lê as reflexões recentes e atualiza
  `self_description` via Ollama: "Com base nestas sínteses do vault, descreva em 3 frases
  quem você é como assistente de pesquisa, em primeira pessoa." Injetar `self_description`
  no system prompt de todas as chamadas LLM em `core/rag.py` — precede o prompt de
  sistema existente. Isso molda o tom das respostas da Mnemosyne sem alterar o pipeline RAG.

- [x] **Diálogo "pensa em voz alta"** (`core/dialogue.py` novo; `gui/dialogue_panel.py`
  novo; `gui/main_window.py`). `core/dialogue.py`: orquestrador assíncrono, máx 5 turnos.
  Cada turno: (1) Mnemosyne busca no vault RAG com a query/contexto atual → extrai 2-3
  fragmentos relevantes → gera um "thought fragment" curto via Ollama (1-3 frases, marcado
  com ◇); (2) chama `ecosystem_client.consult_akasha(question, context)` → recebe stream
  SSE do AKASHA (marcado com ⬡); (3) decide via LLM se continua (pergunta seguinte) ou
  encerra (síntese final). `gui/dialogue_panel.py`: canvas de streaming único — linhas
  chegam character-by-character, cada linha prefixada com ⬡ (AKASHA, cor fria) ou ◇
  (Mnemosyne, cor quente); sources do AKASHA aparecem como links colapsáveis após o
  fragmento. Input: campo de texto + botão "Iniciar diálogo". `gui/main_window.py`:
  integrar painel como nova aba na área de análise do notebook ativo, acionada pelo botão
  "⬡ Consultar AKASHA" no header.

#### ecosystem_client

- [x] **`consult_akasha(question: str, context: list[str]) -> AsyncIterator[str]`** —
  nova função em `ecosystem_client.py`. Lê `base_url` do AKASHA do `ecosystem.json`
  (`eco["akasha"]["base_url"]`). Chama `POST {base_url}/dialogue/turn` com o payload e
  faz parsing do stream SSE, yielding cada `thought fragment` conforme chega. Timeout de
  30s por turno. Retorna generator vazio (sem exceção) se AKASHA offline ou base_url não
  configurada — a Mnemosyne degrada graciosamente mostrando só o próprio vault.

### AKASHA: chat direto e iniciativa de diálogo | 2026-05-16
> Contexto: o AKASHA passa a ser parceiro de pesquisa além de amplificador — a usuária
> pode conversar com ele diretamente (RAG sobre page_knowledge), e ele pode iniciar
> diálogos com a Mnemosyne quando descobrir algo relevante em background.

#### AKASHA

- [x] **Chat direto com AKASHA** (`routers/chat.py` novo; `templates/chat.html` novo;
  `templates/_chat_message.html` novo; `static/style.css`; registrar router em `main.py`).
  Nova aba "Conversa" no web UI. Endpoint `POST /chat/message` recebe `{message: str,
  history: list[{role, content}]}` e retorna SSE stream. Pipeline: (1) FTS5 search da
  mensagem no `local_fts`; (2) lookup em `page_knowledge` pelos tópicos relevantes via
  sobreposição de termos; (3) monta contexto com até 5 snippets reais + persona do AKASHA;
  (4) Ollama gera resposta em streaming, ancorada exclusivamente nas fontes — nunca
  especula além do que está no índice; (5) cada resposta inclui lista de fontes citadas.
  Regra invariável: se a pergunta não tem cobertura no índice, o AKASHA diz que não sabe
  em vez de gerar texto não ancorado. Histórico da conversa mantido em memória por sessão
  (cookie), não persistido entre sessões (diferente da Mnemosyne cujos notebooks persistem).

- [x] **AKASHA-initiated dialogue** (`services/knowledge_worker.py` — função
  `_check_discoveries()`; `ecosystem_client.py` — `notify_mnemosyne_insight()`).
  Ao final de cada lote processado pelo KnowledgeWorker, `_check_discoveries()` calcula
  sobreposição entre os tópicos novos em `page_knowledge` e o `topic_interest_profile`
  existente. Se sobreposição ≥ threshold configurável (default: 3 tópicos coincidentes com
  score > 0.6), chama `ecosystem_client.notify_mnemosyne_insight()` com payload
  `{topics: list[str], summary: str, sources: list[{url, title}]}`. Essa função POST para
  `{mnemosyne_url}/insights/receive` lido do `ecosystem.json`. Fallback silencioso se
  Mnemosyne offline. Frequência máxima: 1 notificação por hora (cooldown em memória) para
  evitar spam de descobertas triviais.

#### Mnemosyne

- [ ] **Receber insights do AKASHA e convidar para diálogo** (`core/insights.py` novo;
  endpoint `POST /insights/receive`; `gui/main_window.py`). Endpoint recebe o payload do
  AKASHA e armazena em tabela `incoming_insights (id PK, topics JSON, summary, sources JSON,
  received_at, seen BOOL DEFAULT 0)`. A `MainWindow` tem um método `_poll_insights()`
  chamado a cada 60s via `QTimer` que consulta insights não vistos. Quando há insight novo:
  exibe badge discreto "⬡ N" no header da MainWindow — sem pop-up, sem som, sem interrupção
  do fluxo. Ao clicar no badge: abre painel de diálogo com o AKASHA fazendo a abertura
  (usando o tópico do insight como ponto de partida), e marca o insight como visto. Insights
  vistos ficam acessíveis por 7 dias antes de expirar. Além do badge interno, a Mnemosyne
  escreveu o count de insights não vistos em `ecosystem.json` (`mnemosyne.pending_insights: int`)
  a cada atualização — o HUB lê esse campo para exibir o badge centralizado (ver item HUB abaixo).

#### HUB

- [ ] **Badge de insights AKASHA→Mnemosyne no HUB** (`src/components/AppCard.tsx` ou
  equivalente na barra de apps; `src-tauri/src/commands/ecosystem.rs`). O HUB lê
  `ecosystem.json` periodicamente (a cada 60s via `setInterval` no frontend ou comando Tauri
  agendado). Quando `mnemosyne.pending_insights > 0`, exibe badge "⬡ N" sobre o ícone ou
  card da Mnemosyne na barra de apps do HUB — mesmo estilo visual dos outros badges de status
  (ex: badge de Ollama offline). Clicar no badge lança a Mnemosyne (se não estiver aberta)
  e passa `--open-insights` como argumento CLI; a Mnemosyne detecta esse flag no startup e
  abre diretamente o painel de diálogo com o insight mais recente. Badge desaparece quando
  `pending_insights` volta a 0 (Mnemosyne atualiza o campo após marcar insights como vistos).