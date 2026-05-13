﻿﻿﻿# TODO â€” Ecossistema

> Consolidado em 2026-04-27. Fonte Ãºnica de verdade â€” arquivos individuais removidos.

---

## PadrÃµes ObrigatÃ³rios


**HUB Ã© o primeiro app a rodar.** Centraliza todas as configuraÃ§Ãµes comuns do ecossistema e gerencia seu funcionamento.
Os demais apps leem `ecosystem.json` no startup â€” se nÃ£o houver valor configurado, usam
defaults locais. Nunca bloquear o startup por falta de configuraÃ§Ã£o do ecosystem.

**Compatibilidade de plataforma: todos os apps devem rodar no Windows 10 e no CachyOS (Linux).**

Isso implica:
- Sem paths hardcoded com separadores Unix â€” usar APIs de path da linguagem (`Path`, `os.path`, `std::path`)
- Sem dependÃªncias exclusivas de uma plataforma (ex.: bibliotecas sÃ³-Linux ou sÃ³-Windows)
- Testar caminhos com espaÃ§os (o diretÃ³rio de trabalho da prÃ³pria Jenifer tem espaÃ§o no nome)
- Apps Python: empacotar com `uv` ou fornecer instruÃ§Ãµes explÃ­citas para ambos os SOs
- Apps Tauri/Rust: garantir que `cargo tauri build` funcione nos dois targets

---

**Tratamento de erros com tipagem Ã© prioridade absoluta em todo o ecossistema.**

Isso se aplica a todos os apps existentes e a qualquer cÃ³digo novo:

- **Rust (AETHER/Hub):** toda funÃ§Ã£o falÃ­vel retorna `Result<T, AppError>`.
  Zero `.unwrap()` ou `.expect()` em produÃ§Ã£o.
- **TypeScript (OGMA/Hub):** `strict: true` obrigatÃ³rio. Erros tipados com
  discriminated unions â€” `{ ok: true; data: T } | { ok: false; error: AppError }`.
  Nunca `any`, nunca `catch (e: any)` sem re-tipar.
- **Python (KOSMOS/Mnemosyne/utilitÃ¡rios):** exceÃ§Ãµes capturadas com tipos
  explÃ­citos (`except ValueError`, nÃ£o `except Exception` genÃ©rico).
  FunÃ§Ãµes crÃ­ticas anotadas com `-> T | None` ou via `Result` pattern.

Nenhuma fase ou feature estÃ¡ completa se o caminho de erro nÃ£o for tratado
e tipado com a mesma atenÃ§Ã£o que o caminho feliz.

---


---

## Ecossistema â€” IntegraÃ§Ã£o e Infraestrutura

### FASE 0 â€” FundaÃ§Ã£o do ecossistema
> PrÃ©-requisito para todas as fases seguintes.

> **DecisÃ£o de caminho (revisada):** O arquivo de contrato foi movido para
> `~/.local/share/ecosystem/ecosystem.json` (Linux) / `%APPDATA%\ecosystem\ecosystem.json` (Windows).
> Motivo: apps Tauri (AETHER) e Electron (OGMA) nÃ£o conhecem o caminho de `program files/`
> em produÃ§Ã£o. O caminho XDG/AppData Ã© descoberto automaticamente por todas as linguagens.

- [x] Criar `ecosystem.json` em `~/.local/share/ecosystem/` com caminhos reais do KOSMOS
- [x] Criar `ecosystem_client.py` â€” utilitÃ¡rio Python compartilhado (KOSMOS, Mnemosyne, Hermes)
      FunÃ§Ãµes: `ecosystem_path()`, `read_ecosystem()`, `write_section()` com escrita atÃ´mica
- [x] Criar `OGMA/src/main/ecosystem.ts` â€” utilitÃ¡rio TypeScript para OGMA
      FunÃ§Ãµes: `ecosystemPath()`, `readEcosystem()`, `writeSection()` com escrita atÃ´mica
- [x] Criar `AETHER/src-tauri/src/ecosystem.rs` â€” mÃ³dulo Rust para AETHER
      FunÃ§Ãµes: `ecosystem_path()`, `write_section()` usando `dirs::data_dir()`
- [x] Adicionar `dirs = "5"` em `AETHER/src-tauri/Cargo.toml`
- [x] Wiring em `AETHER/src-tauri/src/lib.rs`: escreve `vault_path` no startup (falha silenciosa)
- [x] Documentar o contrato: quem escreve cada campo, quando, formato

#### 0.5 â€” sync_root: sincronizaÃ§Ã£o via Proton Drive (ou qualquer pasta sync)

Objetivo: um campo `sync_root` top-level no ecosystem.json aponta para a pasta do Proton Drive.
O HUB deriva e aplica todos os caminhos de uma vez. Cada app respeita o caminho configurado.

```
ProtonDrive/ecosystem/
â”œâ”€â”€ aether/        â† vault_path
â”œâ”€â”€ kosmos/        â† archive_path
â”œâ”€â”€ mnemosyne/
â”‚   â”œâ”€â”€ docs/      â† watched_dir
â”‚   â””â”€â”€ chroma_db/ â† persist_dir (ChromaDB sincronizado)
â”œâ”€â”€ hermes/        â† output_dir
â””â”€â”€ akasha/        â† archive_path
```

- [x] **`ecosystem_client.py`** â€” adicionar `derive_paths(sync_root)` e campo `sync_root` no schema
- [x] **`Mnemosyne/core/config.py`** â€” novo campo `chroma_dir`; `persist_dir` usa-o se definido
- [x] **`Mnemosyne/gui/main_window.py`** â€” campo "Pasta do ChromaDB" na SetupDialog
- [x] **`AKASHA/config.py`** â€” `ARCHIVE_PATH` lÃª `akasha.archive_path` do ecosystem.json se disponÃ­vel
- [x] **`HUB/src-tauri/src/commands/config.rs`** â€” comando `apply_sync_root(sync_root)`
      Cria subpastas + escreve seÃ§Ãµes no ecosystem.json via `derive_paths`
- [x] **`HUB/src/views/SetupView.tsx`** â€” seÃ§Ã£o "SincronizaÃ§Ã£o": campo sync_root + botÃ£o "Aplicar"
      Aviso: "Mova seus arquivos existentes manualmente antes de aplicar"

- [x] Instalar e configurar Proton Drive entre mÃ¡quinas
      - sync_root aplicado: `C:\Users\USUARIO\Documents\p\My files\backup\ecosystem`
      - Subpastas criadas; ecosystem.json atualizado com todos os caminhos derivados
      - [x] Testar round-trip: arquivar pÃ¡gina no AKASHA â†’ aparece no Proton â†’ segunda mÃ¡quina

#### 0.6 â€” OGMA: migrar de Turso para Proton Drive (SQLite local)

MotivaÃ§Ã£o: Proton mantÃ©m cÃ³pias locais em todas as mÃ¡quinas + nuvem, sem depender de
conta externa. Turso sÃ³ mantÃ©m na nuvem.

- [x] Remover integraÃ§Ã£o Turso do OGMA (`src/main/database.ts` â€” voltar para SQLite puro local)
      Remover dependÃªncias: `@libsql/client`, `dotenv` e o `.env` com token Turso
- [x] Adicionar `ogma/` ao `sync_root` em `apply_sync_root()` (Rust + derive_paths Python)
      `data_path: {sync_root}/ogma/` â€” inclui `ogma.db`, `uploads/`, `exports/`
- [x] Atualizar `paths.ts` do OGMA para usar `ogma.data_path` do ecosystem.json (fallback local)
- [ ] Testar migraÃ§Ã£o: exportar dados do Turso â†’ importar no SQLite local antes de remover

#### 0.7 â€” Hermes: usar output_dir do ecosystem.json no startup

Objetivo: Hermes deve ler `hermes.output_dir` do ecosystem.json se `outdir` nÃ£o estiver
nas prefs locais â€” o mesmo padrÃ£o jÃ¡ aplicado ao `mnemo_dir`. ApÃ³s `apply_sync_root`,
Hermes passa a usar `{sync_root}/hermes/` automaticamente.

- [x] `Hermes/hermes.py` â€” `_load_prefs()`: se `outdir` nÃ£o estiver em prefs, ler
      `hermes.output_dir` do ecosystem.json como fallback

#### 0.8 â€” AKASHA: integraÃ§Ã£o Hermes + DB no Proton + lista negra + UI

##### 0.8a â€” AKASHA indexa arquivos do Hermes na busca local
- [x] `AKASHA/config.py` â€” adicionar `hermes_output: str` lendo `hermes.output_dir` do ecosystem.json
- [x] `AKASHA/services/local_search.py` â€” adicionar 6Âª fonte `HERMES` em `index_local_files()`

##### 0.8b â€” AKASHA: DB (biblioteca + lista negra) movÃ­vel para Proton
- [x] `AKASHA/config.py` â€” `DB_PATH` lÃª `akasha.data_path` do ecosystem.json se disponÃ­vel
- [x] `ecosystem_client.py` â€” `derive_paths()`: adicionar `data_path` Ã  seÃ§Ã£o `akasha`
- [x] `HUB/src-tauri/src/commands/config.rs` â€” `apply_sync_root()`: incluir `akasha.data_path`

##### 0.8c â€” AKASHA: aba "lista negra" no menu
- [x] `AKASHA/database.py` â€” `get_blocked_domains()` jÃ¡ existia (retorna set[str])
- [x] `AKASHA/routers/domains.py` â€” adicionar rota `GET /domains` com listagem + template
- [x] `AKASHA/templates/domains.html` â€” nova pÃ¡gina herdando base.html
- [x] `AKASHA/templates/base.html` â€” adicionar link "lista negra" no nav

#### 0.8d â€” AKASHA: melhorias de UI nos cards e pÃ¡ginas
- [x] `AKASHA/static/style.css` â€” adicionar classe `.page-subtitle`
- [x] `AKASHA/templates/library.html` â€” subtÃ­tulo descritivo da Biblioteca
- [x] `AKASHA/templates/sites.html` â€” subtÃ­tulo descritivo de Sites
- [x] `AKASHA/routers/crawler.py` â€” rota `POST /sites/add-quick` (quick-add sem parÃ¢metros extras)
- [x] `AKASHA/templates/_macros.html` â€” botÃ£o "Adicionar a Sites" nos cards

#### 0.9 â€” Mnemosyne: caminhos primÃ¡rios do ecosystem.json + pastas extras

Objetivo: Mnemosyne lÃª `watched_dir`, `vault_dir`, `chroma_dir` do ecosystem.json no
startup (HUB Ã© fonte de verdade). SetupDialog exibe esses caminhos como read-only e
permite adicionar `extra_dirs` para indexaÃ§Ã£o adicional.

- [x] `Mnemosyne/core/config.py` â€” adicionar `extra_dirs: list[str]`; `load_config()` merge
      ecosystem.json: watched_dir/vault_dir/chroma_dir do ecosystem tÃªm precedÃªncia
- [x] `Mnemosyne/gui/main_window.py` â€” SetupDialog: caminhos principais viram read-only
      (vindos do ecosystem); adicionar QListWidget "Pastas extras" com +/âˆ’
- [x] `Mnemosyne/core/` (indexador) â€” loop sobre `[watched_dir] + extra_dirs`

### EXTRAS â€” UtilitÃ¡rios e manutenÃ§Ã£o

#### Script de build de produÃ§Ã£o
- [x] `buildar.sh` â€” bash (CachyOS): `cargo tauri build` para AETHER e HUB + `npm run dist:linux` para OGMA; aceita args para buildar sÃ³ apps especÃ­ficos
- [x] `buildar.bat` â€” batch (Windows 10): mesma sequÃªncia com `npm run dist:win` para OGMA
- [x] `README.md` â€” seÃ§Ã£o "Build de produÃ§Ã£o" atualizada com os novos scripts

#### Scripts de atualizaÃ§Ã£o de dependÃªncias
- [x] `atualizar.sh` â€” bash (CachyOS): git pull + uv sync (AKASHA) + pip install -r (KOSMOS, Mnemosyne, Hermes) + npm install (AETHER, HUB, OGMA)
- [x] `atualizar.bat` â€” batch (Windows 10): mesma sequÃªncia com comandos equivalentes
- [x] `README.md` â€” seÃ§Ã£o "Atualizar dependÃªncias" adicionada entre "Rodar os apps" e "Build de produÃ§Ã£o"

### EXTRAS â€” Bugs e melhorias urgentes

#### HUB â€” Race condition no ecosystem.json (paths somem Ã s vezes)
- Causa: `write_section` faz read-modify-write do arquivo inteiro sem lock.
  Se HUB e outro app chamam `write_section` ao mesmo tempo (ex: app abrindo
  enquanto HUB salva), o Ãºltimo a escrever apaga as mudanÃ§as do outro.
- SoluÃ§Ã£o acordada: **lock file** `.ecosystem.lock` na mesma pasta do JSON.
  Funciona cross-process e cross-language (Python + Rust + futuro TS) sem
  dependÃªncia de APIs especÃ­ficas de plataforma.
- [x] `ecosystem_client.py` â€” usar `filelock.FileLock` (lib `filelock`) em torno
  do read-modify-write; adicionar `filelock` ao `requirements.txt` de cada app Python
- [x] `HUB/src-tauri/src/ecosystem.rs` â€” implementar lock file manual:
  `OpenOptions::create + write` em `.ecosystem.lock`, `lock_exclusive` via `fs2`,
  liberar apÃ³s o `rename`. Adicionar `fs2` ao `Cargo.toml` do HUB.

#### HUB â€” Caminhos nÃ£o atualizam nos apps sem reiniciar
- Causa: todos os apps leem ecosystem.json UMA VEZ no startup. NÃ£o hÃ¡ watcher.
- SoluÃ§Ã£o acordada: **aviso de reinicializaÃ§Ã£o** apÃ³s salvar (opÃ§Ã£o simples).
  File watcher descartado â€” mudanÃ§a de paths em runtime exigiria refatoraÃ§Ã£o
  invasiva em todos os mÃ³dulos que cachÃªam o valor de Paths.X.
- [x] `HUB/src/views/SetupView.tsx` â€” exibir mensagem apÃ³s `handleSave()` bem-sucedido:
  "ConfiguraÃ§Ã£o salva. Reinicie cada app para aplicar os novos caminhos."
  (mesmo padrÃ£o do `syncMsg` jÃ¡ existente para o sync_root)

#### KOSMOS â€” Stats travando e fechando o app
- Bug: `_reload_charts()` roda na thread principal fazendo k-means (numpy)
  + queries + matplotlib, bloqueando o Qt event loop. Windows marca como "nÃ£o respondendo".
- [x] `KOSMOS/app/ui/views/stats_view.py` â€” mover carregamento de dados para `QThread`
  (StatsLoadWorker); widgets sÃ£o criados na thread principal apÃ³s o worker terminar

#### KOSMOS â€” Archive_path ignora ecosystem.json
- Bug: `Paths.ARCHIVE` estava hardcoded como `ROOT/"data"/"archive"`.
  O `archive_path` configurado via HUB (Proton Drive) era ignorado.
- [x] `KOSMOS/app/utils/paths.py` â€” ler `kosmos.archive_path` do ecosystem.json
  no startup; usar como `ARCHIVE` se disponÃ­vel (fallback para `DATA/"archive"`)

#### Hermes â€” "Descarregar" â†’ "Baixar" (portuguÃªs do Brasil)
- "Descarregar" Ã© PT-Portugal. Renomear para "Baixar" no botÃ£o e na aba.
- [x] `Hermes/hermes.py` â€” renomear label do botÃ£o, da aba e do comentÃ¡rio de seÃ§Ã£o

#### Hermes â€” UX de playlist confusa: qualidade nÃ£o aparece apÃ³s carregar lista
- ApÃ³s carregar a playlist, o usuÃ¡rio nÃ£o sabe que precisa clicar em um vÃ­deo
  para ver as opÃ§Ãµes de qualidade. A UI nÃ£o dÃ¡ feedback sobre isso.
- [x] `Hermes/hermes.py` â€” instruÃ§Ã£o visual atualizada: "Selecione um vÃ­deo acima
  para ver as opÃ§Ãµes de qualidade e baixar individualmente."
- [x] `Hermes/hermes.py` â€” auto-seleciona o primeiro vÃ­deo ao carregar playlist
  â€” flag `_from_playlist_select` mantÃ©m a lista visÃ­vel apÃ³s selecionar vÃ­deo individual
  â€” `_on_inspect_done` sÃ³ esconde o painel de playlist em inspeÃ§Ãµes fora da playlist

#### Mnemosyne â€” IndexaÃ§Ã£o trava o computador mesmo com LLM cloud
- ConfiguraÃ§Ã£o confirmada no Windows 10: LLM = kimi-k2.5:cloud (nuvem, OK), embedding = bge-m3:latest (local, ~570MB)
- Causa raiz: `Chroma.from_documents()` envia TODOS os chunks para o Ollama de uma vez,
  sem pausas. bge-m3 ocupa ~570MB na RAM de GPU/CPU; com muitos arquivos sÃ£o milhares
  de chamadas consecutivas sem liberar memÃ³ria â†’ travamento.
- [x] `Mnemosyne/core/indexer.py` â€” processar chunks em lotes (ex: 50 chunks por vez)
  usando `Chroma.add_documents()` em loop com `time.sleep(0.1)` entre lotes,
  ao invÃ©s de `Chroma.from_documents()` com tudo de uma vez
- [x] `Mnemosyne/gui/main_window.py` â€” deixar mais claro na SetupDialog que
  "Modelo de embedding" roda LOCALMENTE (tooltip: "Usado na indexaÃ§Ã£o â€” roda na sua mÃ¡quina via Ollama")

---

#### 0.10 â€” Arquivos de configuraÃ§Ã£o de todos os apps no Proton Drive

Objetivo: config local de cada app tambÃ©m fica na pasta sincronizada, para que as
preferÃªncias se propaguem entre mÃ¡quinas sem reconfigurar manualmente.

Estrutura confirmada: `{sync_root}/{app}/.config/settings.json` para todos os apps.

```
{sync_root}/
â”œâ”€â”€ ogma/
â”‚   â”œâ”€â”€ ogma.db          â† banco SQLite (jÃ¡ feito no 0.6)
â”‚   â”œâ”€â”€ uploads/
â”‚   â”œâ”€â”€ exports/
â”‚   â””â”€â”€ .config/
â”‚       â””â”€â”€ settings.json
â”œâ”€â”€ akasha/
â”‚   â”œâ”€â”€ akasha.db
â”‚   â””â”€â”€ .config/
â”‚       â””â”€â”€ settings.json
â”œâ”€â”€ hermes/
â”‚   â”œâ”€â”€ (transcriÃ§Ãµes .md)
â”‚   â””â”€â”€ .config/
â”‚       â””â”€â”€ settings.json
â”œâ”€â”€ mnemosyne/
â”‚   â”œâ”€â”€ docs/
â”‚   â”œâ”€â”€ chroma_db/
â”‚   â””â”€â”€ .config/
â”‚       â””â”€â”€ settings.json
â”œâ”€â”€ aether/
â”‚   â””â”€â”€ .config/
â”‚       â””â”€â”€ settings.json
â””â”€â”€ kosmos/
    â””â”€â”€ .config/
        â””â”€â”€ settings.json
```

Cada app lÃª `{sync_root}/{app}/.config/settings.json` se `config_path` estiver definido
no ecosystem.json, com fallback para o arquivo local atual.

- [x] **`derive_paths()`** â€” adicionar `config_path: {sync_root}/{app}/.config` para cada app
- [x] **`apply_sync_root()` (Rust)** â€” criar subpastas `.config/` + escrever `config_path` no ecosystem.json
- [x] **OGMA** â€” `SETTINGS` em `paths.ts` usa `{ogma.config_path}/settings.json` se disponÃ­vel
- [x] **Hermes** â€” `_load_prefs()` / `_save_prefs()` usa `{hermes.config_path}/settings.json` se disponÃ­vel
- [x] **KOSMOS** â€” `Paths.SETTINGS` usa `{kosmos.config_path}/settings.json` se disponÃ­vel
- [x] **Mnemosyne** â€” `load_config()` / `save_config()` usa `{mnemosyne.config_path}/settings.json` se disponÃ­vel
- [ ] **AKASHA** â€” sem settings.json prÃ³prio; config estÃ¡ no akasha.db (sincronizado via 0.8b)
- [ ] **AETHER** â€” vault config jÃ¡ fica dentro de vault_path (sincronizado); sem settings separado

---

### FASE 1 â€” InterligaÃ§Ã£o dos apps existentes
> Aproveita o que jÃ¡ existe. MudanÃ§as cirÃºrgicas, sem novo app.

#### 1.1 â€” OGMA â†’ AETHER (projetos de escrita)

##### Passo A â€” Renomear tipo `creative` â†’ `writing` no OGMA
- [x] `src/renderer/types/index.ts`: alterar `ProjectType` union, SUBCATEGORIES,
      PROJECT_TYPE_LABELS ('Escrita'), PROJECT_TYPE_ICONS ('âœï¸' mantÃ©m),
      PROJECT_TYPE_DESCRIPTIONS
- [x] `src/renderer/components/Projects/NewProjectModal.tsx`: atualizar array TYPES
- [x] `src/renderer/views/ProjectDashboard/ProjectLocalDashboard.tsx`:
      renomear case `'creative'` â†’ `'writing'`
- [x] `src/main/ipc.ts`: renomear todas as ocorrÃªncias do literal `'creative'`
- [x] `src/main/database.ts`: adicionar migration que faz
      `UPDATE projects SET project_type = 'writing' WHERE project_type = 'creative'`
      (o campo Ã© TEXT sem CHECK constraint â€” migration simples)

##### Passo B â€” Integrar projetos de escrita com o AETHER
- [x] `src/main/database.ts`: adicionar coluna `aether_project_id TEXT` na tabela
      `projects` (nova migration)
- [x] OGMA lÃª `aether.vault_path` do `ecosystem.json` na criaÃ§Ã£o de projeto
- [x] Ao criar projeto com `project_type = 'writing'`, OGMA escreve no vault AETHER:
      - `{vault}/{uuid}/project.json`  (formato Project do AETHER â€” campos: id, name, project_type, genre, description)
      - `{vault}/{uuid}/{book_uuid}/book.json`  (livro padrÃ£o vazio, sem capÃ­tulos)
- [x] Salvar `aether_project_id` no banco do OGMA para manter o vÃ­nculo
- [x] BotÃ£o "Abrir no AETHER" em projetos de escrita (desabilitado se vault nÃ£o configurado)

#### 1.2 â€” KOSMOS â†’ Mnemosyne (artigos salvos)
- [x] KOSMOS escreve `archive_path` e `data_path` em `ecosystem.json` na inicializaÃ§Ã£o
      via `ecosystem_client.write_section("kosmos", {...})` em `KOSMOS/main.py`
- [x] Mnemosyne lÃª `ecosystem.json` e oferece o archive do KOSMOS
      como pasta sugerida na tela de indexaÃ§Ã£o (botÃ£o "SugestÃµes do ecossistema" na SetupDialog)
- [ ] Verificar se o botÃ£o "Arquivar" em artigos salvos chama
      `archive_manager` corretamente â€” garantir que gera `.md` vÃ¡lido

#### 1.3 â€” AETHER â†’ Mnemosyne (indexar escritos)
- [x] AETHER escreve `vault_path` em `ecosystem.json` na inicializaÃ§Ã£o
      (startup Rust, apÃ³s carregar vault â€” `ecosystem::write_section()` em lib.rs)
- [x] Mnemosyne oferece vault AETHER como pasta sugerida (botÃ£o "SugestÃµes do ecossistema")
- [ ] Testar indexaÃ§Ã£o dos `.md` de capÃ­tulos pelo Mnemosyne

#### 1.4 â€” Hermes â†’ Mnemosyne (transcriÃ§Ãµes indexÃ¡veis)
- [x] Adicionar campo "Pasta de saÃ­da do Mnemosyne" na aba Transcrever do Hermes
      LÃª `mnemosyne.index_paths[0]` do ecosystem como sugestÃ£o; desabilitado se vazio
- [x] Adicionar checkbox "Indexar no Mnemosyne apÃ³s transcrever"
      Salva o `.md` diretamente numa das pastas monitoradas pelo Mnemosyne
- [x] Formato: Markdown limpo com frontmatter mÃ­nimo (tÃ­tulo, data, fonte/URL, duraÃ§Ã£o)

#### 1.5 â€” Completar contrato ecosystem.json (seÃ§Ãµes faltantes)

Cada app deve escrever sua seÃ§Ã£o completa no startup. Schema alvo:
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

- [x] **OGMA** â€” `writeSection("ogma", { data_path, exe_path })` no startup
      (`writeSection` existe em `ecosystem.ts` mas nunca Ã© chamado)
- [x] **Mnemosyne** â€” `write_section("mnemosyne", { watched_dir, vault_dir, index_paths, exe_path })` no startup
      (paths vÃªm do `AppConfig`; `persist_dir` = `{watched_dir}/.mnemosyne/chroma_db`)
- [x] **Hermes** â€” `write_section("hermes", { output_dir, exe_path })` no startup
      (`output_dir` = pasta de downloads/transcriÃ§Ãµes configurada na UI)
- [x] **AKASHA** â€” adicionar `archive_path` Ã  seÃ§Ã£o jÃ¡ escrita por `register_akasha()`

#### 1.6 â€” Scraper compartilhado: KOSMOS e AKASHA

Objetivo: eliminar a duplicaÃ§Ã£o de cÃ³digo da cascata de extraÃ§Ã£o web.
`ecosystem_scraper.py` (raiz do repo) Ã© o Ãºnico ponto de manutenÃ§Ã£o da cascata.

- [x] Criar `ecosystem_scraper.py` â€” cascata newspaper4k â†’ trafilatura â†’ readability-lxml
      â†’ inscriptis â†’ BeautifulSoup; `extract(html, url, output_format)` sem I/O prÃ³prio
- [x] `AKASHA/services/archiver.py` â€” delegar `_cascade_extract` ao mÃ³dulo compartilhado
- [x] `AKASHA/services/library.py` â€” idem para `_fetch_and_extract`
- [x] `KOSMOS/app/core/article_scraper.py` â€” simplificar para `_cascade_extract(..., output_format="html")`
- [x] `KOSMOS/requirements.txt` â€” adicionar `inscriptis` e `markdownify`

#### 1.8 â€” AKASHA: busca local cobre todo o ecossistema

- [x] Indexar `AKASHA/data/archive/` prÃ³pria no FTS5 (source "AKASHA")
      (`index_local_files()` em `services/local_search.py` â€” mesmo extractor do KOSMOS)
- [x] Ler `mnemosyne.watched_dir` e `mnemosyne.vault_dir` do ecosystem.json em `config.py`
- [x] Indexar `mnemosyne.watched_dir` no FTS5 (source "MNEMOSYNE")
- [x] Indexar `mnemosyne.vault_dir` no FTS5 (source "OBSIDIAN")
      (depende de 1.5 â€” Mnemosyne precisa escrever esses caminhos primeiro)

#### 1.9 â€” Mnemosyne: sugestÃµes do ecossistema cobrindo todos os archives

- [x] Adicionar AKASHA archive (`akasha.archive_path`) nas sugestÃµes da SetupDialog
      (depende de 1.5 â€” AKASHA precisa escrever `archive_path` primeiro)

---

### FASE 3 â€” Android (APK)
> âš ï¸ **SUSPENSA PARA REPLANEJAMENTO.** O HUB passou a ter papel de LOGOS (orquestrador de IA), mudando seu foco principal.
> A necessidade de acesso ao ecossistema no Android continua existindo, mas a abordagem precisa ser repensada
> â€” provavelmente um app separado ou soluÃ§Ã£o diferente do HUB. Itens abaixo mantidos como referÃªncia histÃ³rica.

#### 3.1 â€” Build Android do hub
- [ ] Configurar ambiente Tauri Android:
      - Android Studio + NDK
      - `cargo install tauri-cli` (jÃ¡ deve estar instalado do AETHER)
- [ ] Adaptar `tauri.conf.json` para Android (permissÃµes de filesystem)
- [ ] Primeiro build de teste no tablet (`cargo tauri android dev`)
- [ ] Resolver incompatibilidades de UI para toque (botÃµes, scroll)
- [ ] Build de release (APK assinado)

#### 3.2 â€” SincronizaÃ§Ã£o de dados
- [ ] Configurar Syncthing: pastas a sincronizar
      - Vault AETHER completo
      - `kosmos/data/archive/`
      - `hub_read_state.json`
- [ ] Testar round-trip completo:
      - Escrever capÃ­tulo no tablet â†’ sync â†’ abrir no AETHER no PC
      - Salvar artigo no KOSMOS â†’ sync â†’ aparecer no hub Android
- [ ] Tratar conflitos de sync (dois dispositivos editam o mesmo arquivo)

#### 3.3 â€” Acesso remoto (fora da rede local)
- [ ] Instalar Tailscale no PC e no tablet
- [ ] Hub detecta se Ollama estÃ¡ acessÃ­vel (local ou via Tailscale)
- [ ] MÃ³dulo Projetos: acesso ao `ogma.db` via Tailscale quando remoto
- [ ] Fallback gracioso: mÃ³dulos funcionam offline com dados jÃ¡ sincronizados

---

### FASE 4 â€” Features extras
> Qualidade de vida. SÃ³ apÃ³s Fase 3 estÃ¡vel.

- [x] Verificar sistema de log em todos os apps e criar onde nÃ£o existir
      â€” OGMA: âœ… `createLogger` + `setupGlobalErrorHandlers` em main.ts
      â€” HUB: âœ… `tauri_plugin_log`, arquivo diÃ¡rio, 7 dias de retenÃ§Ã£o
      â€” AETHER: âœ… `tauri_plugin_log`, arquivo diÃ¡rio, 7 dias de retenÃ§Ã£o
      â€” KOSMOS: âœ… `setup_logger()` em app/utils/logger.py, arquivo + stderr
      â€” Mnemosyne: âœ… criado `core/logger.py`, rotaÃ§Ã£o diÃ¡ria, 7 backups
      â€” Hermes: âœ… criado `_setup_logger()` em hermes.py; `_log()` da UI persiste em arquivo
      â€” AKASHA: pendente â€” criar ao iniciar o desenvolvimento
- [ ] Integrar AKASHA aos outros apps do ecossistema:
      â€” OGMA, AETHER, KOSMOS, Mnemosyne, Hermes: seleÃ§Ã£o de texto â†’ "Pesquisar no AKASHA"
        (menu de contexto ou botÃ£o flutuante que abre `http://localhost:7071/search?q=<texto>`)
      â€” HUB: botÃ£o/atalho na barra lateral para abrir AKASHA no browser
      â€” Requisito: AKASHA deve estar rodando para receber a requisiÃ§Ã£o
- [ ] Quick capture: widget ou atalho Android para adicionar nota rÃ¡pida
      ao OGMA sem abrir o app completo
- [ ] Streak AETHER visÃ­vel no hub (ler `sessions.json` do vault)
- [ ] NotificaÃ§Ã£o Android: novos artigos no archive do KOSMOS
- [ ] Busca cross-mÃ³dulo: pesquisar em escritos + projetos + artigos
- [ ] stellar-downloader + transcriber integrados (HERMES):
      - Download â†’ transcriÃ§Ã£o automÃ¡tica â†’ salvar no archive
- [ ] ExportaÃ§Ã£o do hub: capÃ­tulo AETHER â†’ PDF/EPUB direto do Android

---

#### DependÃªncias entre fases

  Fase 0 â”€â”€â–º Fase 1 (qualquer sub-item)
  Fase 0 â”€â”€â–º Fase 2.1
  Fase 2.1 â”€â”€â–º Fase 2.2, 2.3, 2.4, 2.5 (paralelas)
  Fase 2 (completa) â”€â”€â–º Fase 3
  Fase 3 â”€â”€â–º Fase 4

---

#### Estado dos apps individuais (prÃ©-condiÃ§Ãµes para integraÃ§Ã£o)

  AETHER        âœ…  Fases 0â€“5 completas. Vault format estÃ¡vel. Sem bloqueios.
  OGMA          âœ…  Schema v2 implementado (database.ts:114). IPC usa
                    project_properties + page_prop_values em produÃ§Ã£o.
                    Itens abertos da Fase 10 (FTS5/Turso, testes offline)
                    sÃ£o qualidade/teste â€” nÃ£o bloqueiam integraÃ§Ã£o.
  KOSMOS        âœ…  archive_manager.py funcional. Pronto para integraÃ§Ã£o.
  Mnemosyne     âš ï¸  ProtÃ³tipo incompleto. core/rag.py vazio. Usa HuggingFace
                    em vez de Ollama (inconsistente com o ecossistema).
                    Design diverge do sistema visual. Precisa de
                    desenvolvimento antes de entrar no hub.
  transcriber   âœ…  UtilitÃ¡rio funcional. MudanÃ§a mÃ­nima necessÃ¡ria.
  stellar-dl    âœ…  UtilitÃ¡rio funcional. MudanÃ§a mÃ­nima necessÃ¡ria.

#### Estado das fases do ecossistema

  Fase 0: âœ… Base concluÃ­da (0â€“0.5). Items 0.6â€“0.9 em andamento (sync + integraÃ§Ãµes)
  Fase 1: âœ… ConcluÃ­da â€” 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 1.9 concluÃ­das
            âš ï¸  Item pendente: 1.2 â€” verificar botÃ£o "Arquivar" no KOSMOS
  Fase 2: âœ… ConcluÃ­da â€” 2.1, 2.2, 2.3, 2.4, 2.5 e 2.6 concluÃ­das
  Fase 3: âš ï¸ suspensa â€” HUB agora Ã© LOGOS; acesso Android a repensar separadamente
  Fase 4: nÃ£o iniciada

---

---

## HUB â€” Dashboard e Painel de Controle

### Fase 2 â€” FundaÃ§Ã£o e MÃ³dulos
> HUB como dashboard central do ecossistema: lanÃ§a apps, centraliza configuraÃ§Ã£o, visualiza dados de todos os outros programas e hospeda o LOGOS (proxy de LLM).
> Stack: Tauri 2 + React + TypeScript. Read-only por padrÃ£o nos mÃ³dulos de visualizaÃ§Ã£o â€” nÃ£o substitui os editores primÃ¡rios.
> MÃ³dulos Android originalmente planejados aqui foram movidos para replanejamento separado (ver FASE 3).

### 2.1 â€” FundaÃ§Ã£o + Tela de ConfiguraÃ§Ã£o
- [x] Criar projeto Tauri 2 em `program files/HUB/`
- [x] Copiar design system do AETHER sem modificaÃ§Ãµes:
      `tokens.css`, `animations.css`, `typography.css`, `components.css`
      `CosmosLayer.tsx`, `Toast.tsx`, `ThemeToggle.tsx`
- [x] Splash screen com typewriter + CosmosLayer
- [x] Router interno: `splash â†’ setup | home`
      `type HubView = 'home' | 'writing' | 'reading' | 'projects' | 'questions'`
- [x] Tela de configuraÃ§Ã£o (SetupView): lÃª/edita/valida caminhos do `ecosystem.json`
      â€” campos: `aether.vault_path`, `kosmos.archive_path`, `ogma.data_path`
      â€” Ã­cone âœ“/âœ— por campo via IPC `validate_path()`
- [x] Dashboard (HomeView): 4 cards com CosmosLayer individual
      â€” cards desabilitados se caminho nÃ£o configurado
- [x] Rust: `commands/config.rs` â€” `read_ecosystem_config`, `validate_path`, `save_ecosystem_config`
      usando `ecosystem.rs` copiado do AETHER

### 2.2 â€” MÃ³dulo Escrita (AETHER vault, read-only)
- [x] Rust `commands/writing.rs`:
      `list_writing_projects(vault_path)` â€” lÃª todos `{vault}/*/project.json`
      `list_books(vault_path, project_id)` â€” lÃª `{vault}/{proj}/*/book.json`
      `read_chapter(vault_path, project_id, book_id, chapter_id)` â€” lÃª `.md`
- [x] `WritingView.tsx` â€” grade de projetos com CosmosLayer individual
- [x] `BookView.tsx` â€” Ã¡rvore livros + capÃ­tulos com status e word count
- [x] `ChapterView.tsx` â€” `react-markdown` renderiza o `.md`
- [x] Tipos `Project`, `Book`, `ChapterMeta` copiados de AETHER

### 2.3 â€” MÃ³dulo Leituras (KOSMOS archive, read-only)
- [x] Rust `commands/reading.rs`:
      `list_articles(archive_path)` â€” scan `{archive}/**/*.md`, parseia frontmatter
      `read_article(path)` â€” separa frontmatter do corpo
      `toggle_read(archive_path, article_path)` â€” lÃª/escreve `hub_read_state.json`
- [x] `ReadingView.tsx` â€” lista com filtros (fonte, lido/nÃ£o lido); badge nÃ£o lidos
- [x] `ArticleView.tsx` â€” frontmatter em destaque + `react-markdown`

### 2.4 â€” MÃ³dulo Projetos (OGMA, read-only)
- [x] Adicionar `rusqlite = { version = "0.31", features = ["bundled"] }` ao Cargo.toml
      (`bundled` compila SQLite estÃ¡tico â€” funciona no Android)
- [x] Rust `commands/projects.rs`:
      `list_ogma_projects(db_path)` â€” SELECT projects WHERE status != 'archived'
      `list_project_pages(db_path, project_id)` â€” SELECT pages WHERE is_deleted = 0
- [x] `lib/editorjs-renderer.tsx` â€” renderiza blocos Editor.js (`paragraph`, `header`,
      `list`, `checklist`, `quote`, `code`, `table`, `delimiter`, `columns`)
- [x] `ProjectsView.tsx` + `PageView.tsx`

### 2.5 â€” MÃ³dulo Perguntas (Ollama, sem Rust)
- [x] `lib/ollama.ts`:
      `listModels()` â€” GET `localhost:11434/api/tags`
      `streamChat(model, messages)` â€” POST `/api/chat` com streaming NDJSON
- [x] `QuestionsView.tsx` â€” seletor de modelo, histÃ³rico de sessÃ£o, streaming
      banner "Ollama offline" + botÃ£o Tentar novamente

### 2.6 â€” Barra de atalhos para apps externos
> Barra permanente visÃ­vel em todas as views. LanÃ§a os 5 apps e indica se estÃ£o rodando.

- [x] Tela de Setup: adicionar campos de executÃ¡vel para cada app
      â€” `aether.exe_path`, `ogma.exe_path`, `kosmos.exe_path`,
        `mnemosyne.exe_path`, `hermes.exe_path` em `ecosystem.json`
      â€” auto-descoberta por nome de processo conhecido como fallback
        (ex.: buscar `AETHER.exe` / `aether` no PATH e locais comuns)
      â€” Ã­cone âœ“/âœ— por campo (reutilizar `validate_path()` existente)
- [x] Rust `commands/launcher.rs`:
      `launch_app(exe_path: String) -> Result<(), AppError>` â€” `Command::new(exe_path).spawn()`
      `is_app_running(process_name: String) -> bool` â€” lista processos do SO
        (Windows: `tasklist`, Linux: `/proc` ou `pgrep`)
      `get_all_app_statuses() -> HashMap<String, bool>` â€” chama `is_app_running` para os 5 apps
- [x] `AppBar.tsx` â€” barra lateral esquerda fixa com 5 botÃµes de app
      â€” cada botÃ£o: sigla em IM Fell English itÃ¡lico + ponto indicador (rodando / parado)
      â€” clique: chama `launch_app`; se jÃ¡ rodando, apenas pulsa o indicador
      â€” polling a cada 5s via `get_all_app_statuses` para atualizar status
- [x] Integrar `AppBar` no layout raiz (visÃ­vel em todas as views, inclusive Home)

---

### HUB: redesign da UI como dashboard do ecossistema

O HUB deixou de ser um companion Android e Ã© agora o **painel de controle central**
do ecossistema. A UI atual (se existente) foi projetada para outra finalidade â€”
precisa ser reimaginada como um dashboard desktop (Tauri).

#### Arquitetura de navegaÃ§Ã£o
- [x] Sidebar vertical persistente com 4 seÃ§Ãµes principais:
  â€” **Home** (dashboard de status dos apps)
  â€” **LOGOS** (fila de LLM + monitor de VRAM)
  â€” **Atividade** (feed de eventos cross-app)
  â€” **ConfiguraÃ§Ã£o** (ecosystem.json + sync_root)
- [x] Topbar mÃ­nima: nome do ecossistema + indicador global de saÃºde + botÃ£o de silÃªncio

#### Tela Home â€” status dos apps
- [x] Card por app do ecossistema (AKASHA Â· KOSMOS Â· AETHER Â· Mnemosyne Â· Hermes Â· OGMA):
  â€” status ao vivo (running / stopped / erro) via ping periÃ³dico nos `/health` endpoints
  â€” porta, botÃ£o "abrir no browser" (apps web) ou "focar janela" (apps Qt/Tauri)
  â€” botÃ£o de iniciar / encerrar cada app diretamente do HUB
- [ ] Badge de alerta quando app estÃ¡ offline mas deveria estar rodando
- [ ] Mini-resumo por app (Ãºltima atividade, contagem de arquivos/artigos/etc.)

#### Painel de configuraÃ§Ã£o do ecossistema
- [x] Campo `sync_root` com botÃ£o "Aplicar" â€” chama `apply_sync_root()` e mostra preview
  dos caminhos derivados por app antes de confirmar
- [ ] Aviso de migraÃ§Ã£o: se sync_root muda e dados existem no caminho antigo, exibir
  instruÃ§Ã£o para mover arquivos (ex.: `akasha.db`, archives) antes de reiniciar
- [ ] Editor visual das seÃ§Ãµes do `ecosystem.json` (alternativa ao JSON bruto):
  campos por app com labels descritivos e validaÃ§Ã£o de caminhos

#### System tray / always-accessible
- [x] HUB fica na bandeja do sistema ao minimizar (nÃ£o fecha, nÃ£o some da taskbar)
- [x] Fechar janela (Ã— ou Alt+F4) â†’ oculta na bandeja em vez de encerrar o processo
- [x] Menu de contexto na bandeja (clique direito): "Abrir HUB" Â· "Silenciar LOGOS" Â· "Fechar HUB"
  â€” "Silenciar LOGOS" chama POST /logos/silence diretamente pelo processo do HUB
  â€” abrir/fechar apps individuais: acessÃ­vel via DashboardView (cards da Home)
- [x] Infraestrutura de notificaÃ§Ãµes nativas (tauri-plugin-notification):
  â€” comando `send_notification(title, body)` disponÃ­vel para o frontend
  â€” gatilhos por evento (app offline, VRAM crÃ­tica, etc.) dependem do Feed de Atividade
- [ ] NotificaÃ§Ãµes automÃ¡ticas por evento: depende de `activity.jsonl` por app (ver Feed de Atividade)

#### Design visual
- [x] Seguir DESIGN_BIBLE.txt â€” tema padrÃ£o: "Atlas AstronÃ´mico Ã  Meia-Noite" (`#12161E`)
- [x] Dois modos de janela:
  â€” **Compacto** (~640Ã—440): sÃ³ cards de status + botÃµes de aÃ§Ã£o imediata
  â€” **Expandido** (~1280Ã—800): dashboard completo com sidebar + todas as seÃ§Ãµes
- [x] Tipografia e paleta consistentes com AETHER/OGMA (tokens compartilhados do ecossistema)

---

### PendÃªncias e Features

### Controle de recursos â€” extensÃ£o do LOGOS

- [x] Painel de VRAM em tempo real + fila de prioridades visÃ­vel
  â€” mostrar o que estÃ¡ rodando agora em P1/P2/P3 com estimativa de VRAM ocupada
  â€” Implementado: `HUB/src/components/LogosPanel.tsx` (polling 5s via Tauri IPC)
  â€” Posicionado como footer do HomeView
- [x] BotÃ£o "SilÃªncio" â€” pausa instantÃ¢nea de todas as tarefas P3 para liberar GPU
  â€” Ãºtil ao iniciar escrita no AETHER ou chat no HUB
  â€” Implementado: botÃ£o "silenciar" no LogosPanel (chama `logos_silence` Tauri command)
- [x] Painel de gerenciamento do Ollama:
  â€” listar modelos carregados na VRAM com tamanho (GET /logos/models â†’ `logosListModels`)
  â€” ver qual app estÃ¡ usando o LOGOS no momento (`active_app` no StatusResponse)
  â€” forÃ§ar `keep_alive: 0` por modelo individual (`logosUnloadModel` Tauri command)
- [x] Perfis de workflow com um clique:
  â€” "Modo Escrita": AETHER/HUB mantÃªm P1; KOSMOS reader â†’ P2; Mnemosyne RAG â†’ P3
  â€” "Modo Estudo": Mnemosyne RAG â†’ P1; KOSMOS reader â†’ P2
  â€” "Modo Consumo" e "Normal": sem override de prioridade
  â€” perfil persistido em `LogosState.active_profile`; alterado via POST /logos/profile ou `logosSetProfile`
- [x] Modo SobrevivÃªncia (Windows/CPU-only) â€” ativado automaticamente em builds Windows via `cfg!(target_os = "windows")`:
  â€” `keep_alive: 0` forÃ§ado em todo request (RAM liberada imediatamente)
  â€” `num_ctx` limitado a 2048 pelo LOGOS independente do que o app pediu
  â€” modelos >3B rejeitados com 429 ("apenas modelos â‰¤3B aceitos")
  â€” requests P3 rejeitados imediatamente (sem anÃ¡lise em background)
  â€” paralelismo desabilitado (sempre 2 permits, serial mesmo em modelos leves)
  â€” badge "Modo SobrevivÃªncia â€” Windows" exibido na LogosView
- [x] Monitoramento de CPU e RAM no painel LOGOS:
  **Motivo:** a barra de VRAM (jÃ¡ implementada via sysfs) sÃ³ funciona com GPU discreta AMD/NVIDIA.
  No Windows 10 (sem GPU) e no laptop (Intel integrada sem ROCm), o painel fica cego. CPU e RAM
  sÃ£o os recursos crÃ­ticos nessas mÃ¡quinas. Sem esse monitoramento, P3 pode saturar o CPU a 90%
  sem que o LOGOS perceba (bug confirmado com Mnemosyne idle indexer).
  Fonte: crates.io/crates/sysinfo â€” cross-platform, Linux + Windows.
  **ImplementaÃ§Ã£o â€” Rust (`HUB/src-tauri/src/logos.rs` + `Cargo.toml`):**
  1. Adicionar ao `Cargo.toml`: `sysinfo = { version = "0.32", features = ["cpu"] }`
  2. Adicionar campo `sys: sysinfo::System` ao struct `Inner`, inicializado com `System::new_all()`
     CRÃTICO: manter a mesma instÃ¢ncia entre leituras â€” CPU% Ã© calculado como delta entre
     duas leituras consecutivas. Criar nova instÃ¢ncia a cada poll retorna sempre 0%.
  3. No loop de `collect_status()`: chamar `inner.sys.refresh_cpu_all()` e
     `inner.sys.refresh_memory()` antes de ler os valores
  4. Adicionar ao `StatusResponse`:
     `cpu_pct: f32`      â€” de `sys.global_cpu_usage()`
     `ram_free_mb: u64`  â€” de `sys.available_memory() / 1_048_576`
  5. Na lÃ³gica de bloqueio de P3: adicionar condiÃ§Ãµes â€” bloquear quando `cpu_pct > 85.0`
     OU `ram_free_mb < 1536` (alÃ©m do `vram_pct > 0.85` jÃ¡ existente)
  **ImplementaÃ§Ã£o â€” TypeScript (`HUB/src/components/LogosPanel.tsx`):**
  6. Ler `cpu_pct` e `ram_free_mb` do status (jÃ¡ chegam via `logosGetStatus`)
  7. Detectar ausÃªncia de GPU: `vramPct === null` â†’ substituir barra de VRAM por barras de CPU e RAM
     CPU: verde se < 70%, amarelo se 70â€“85%, vermelho se > 85%
     RAM livre: verde se > 4 GB, amarelo se 1.5â€“4 GB, vermelho se < 1.5 GB
  8. Em mÃ¡quinas com GPU: exibir CPU% e RAM como texto compacto ao lado da barra de VRAM
  **Tipo do status TS (`HUB/src/types.ts`):**
  9. Adicionar `cpu_pct?: number` e `ram_free_mb?: number` ao tipo `LogosStatus`

- [x] LOGOS: injetar `keep_alive` automaticamente por prioridade no proxy transparente:
  **Motivo:** por padrÃ£o o Ollama retÃ©m modelos por 5 minutos apÃ³s ociosidade. Um modelo P3
  (KOSMOS background) fica ocupando VRAM 5 minutos depois de terminar, impedindo P1 de usar
  o hardware. O parÃ¢metro `keep_alive` por-requisiÃ§Ã£o sobrescreve o global `OLLAMA_KEEP_ALIVE`
  e Ã© rastreado por modelo individualmente. Aplicado no proxy, Ã© completamente transparente para
  os apps â€” nenhum deles precisa saber do LOGOS.
  Fonte: docs.ollama.com/faq; markaicode.com/ollama-keep-alive-memory-management
  **ImplementaÃ§Ã£o (`HUB/src-tauri/src/logos.rs` â€” handler do proxy `/api/chat` e `/api/generate`):**
  1. No handler de proxy, apÃ³s receber o body JSON do app cliente:
     a. Deserializar: `let mut body: serde_json::Value = serde_json::from_slice(&bytes)?;`
     b. Determinar a prioridade â€” a partir do header `X-Priority` enviado pelo `ecosystem_client.py`
        ou inferida do `X-App` header (mnemosyne=P2, kosmos=P3, hub=P1)
     c. Injetar conforme prioridade:
        P1 â†’ `body["keep_alive"] = json!(-1)`  (mantÃ©m aquecido indefinidamente)
        P2 â†’ `body["keep_alive"] = json!("10m")` (libera apÃ³s 10 min de inatividade)
        P3 â†’ `body["keep_alive"] = json!("0")`  (descarrega imediatamente apÃ³s resposta)
     d. Reserializar e repassar ao Ollama na porta 11434
  2. Apps que usam `ecosystem_client.py` â†’ `request_llm()` jÃ¡ envia `X-App`; basta mapear appâ†’prioridade
     no LOGOS (ex: app="mnemosyne" â†’ P2)
  3. Para `/api/embed` (embeddings): sempre P3 â†’ `keep_alive: "0"` (embedding models nÃ£o precisam ficar quentes)

- [x] LOGOS: configurar variÃ¡veis de ambiente do Ollama por perfil de hardware no startup:
  **Motivo:** o Ollama usa configuraÃ§Ãµes globais que nÃ£o distinguem hardware. Sem `OLLAMA_GPU_OVERHEAD`,
  a RX 6600 pode sofrer OOM ao carregar dois modelos simultaneamente (ex: nomic-embed-text + llama 3).
  `OLLAMA_FLASH_ATTENTION=1` ativa tiling de atenÃ§Ã£o que reduz uso de VRAM em contextos longos
  (suportado via backend Triton no ROCm para RDNA2/gfx1032 da RX 6600).
  `OLLAMA_MAX_LOADED_MODELS` impede que o Ollama carregue 3 modelos simultÃ¢neos (padrÃ£o) em mÃ¡quinas
  onde nem 2 cabem confortavelmente.
  Fonte canÃ´nica: github.com/ollama/ollama/blob/main/envconfig/config.go
  **ParÃ¢metros por perfil:**
  | VariÃ¡vel                   | high (RX 6600) | medium (MX150) | low (i5-3470) |
  |---------------------------|----------------|----------------|---------------|
  | OLLAMA_MAX_LOADED_MODELS   | 2              | 1              | 1             |
  | OLLAMA_GPU_OVERHEAD (bytes)| 524 288 000    | 209 715 200    | 0             |
  | OLLAMA_FLASH_ATTENTION     | 1              | 1              | 0 (sem GPU)   |
  | OLLAMA_NUM_PARALLEL        | 2              | 1              | 1             |
  **ImplementaÃ§Ã£o (`HUB/src-tauri/src/logos.rs`):**
  1. OpÃ§Ã£o A â€” se o LOGOS gerencia o processo Ollama (recomendado):
     Em `Inner::start_ollama()` (ou equivalente), construir o `Command` com `.envs(env_map)`
     onde `env_map` Ã© montado a partir do `HardwareProfile` detectado no startup
  2. OpÃ§Ã£o B â€” se o Ollama roda como serviÃ§o do sistema:
     Escrever as variÃ¡veis em `~/.config/ollama/ollama_env` e instruir o usuÃ¡rio a configurar
     o serviÃ§o systemd com `EnvironmentFile=%h/.config/ollama/ollama_env`
     O LOGOS escreve esse arquivo no startup e exibe aviso se o serviÃ§o precisar ser reiniciado
  3. Registrar as variÃ¡veis ativas no log de startup do LOGOS para debugging

- [x] LOGOS: preempÃ§Ã£o inteligente de P3 â€” suspender (nÃ£o cancelar) ao detectar P1 sem VRAM:
  **Motivo:** o botÃ£o "silenciar" atual cancela P3 de forma cega. A literatura cientÃ­fica
  (Priority-Aware Preemptive Scheduling, arxiv 2503.09304; Topology-aware Preemptive Scheduling,
  arxiv 2411.11560) mostra que o correto Ã©:
  a) Calcular se P1 cabe na VRAM disponÃ­vel ANTES de preemptar â€” preemptar sem espaÃ§o suficiente
     desperdiÃ§a VRAM e introduz latÃªncia desnecessÃ¡ria.
  b) Suspender P3 (keep_alive: "0" forÃ§a unload), nÃ£o cancelar â€” a fila P3 Ã© mantida e
     retomada quando P1 encerra.
  **ImplementaÃ§Ã£o (`HUB/src-tauri/src/logos.rs`):**
  1. Ao receber request P1 via proxy:
     a. Verificar se hÃ¡ request P3 em execuÃ§Ã£o (`active_priority == 3`)
     b. Consultar `/api/tags` para obter `size` estimado do modelo P1 em bytes
     c. Ler VRAM livre atual (sysfs)
     d. Se `vram_livre_mb < modelo_p1_mb + 500` (500 MB de buffer):
        â€” Enviar `POST /api/chat` com `{"model": modelo_p3, "keep_alive": "0"}` ao Ollama
          (prompt vazio forÃ§a unload imediato sem gerar resposta)
        â€” Poll de `/api/ps` atÃ© o modelo P3 desaparecer (timeout 10s)
        â€” SÃ³ entÃ£o encaminhar o request P1 ao Ollama
     e. Se VRAM livre Ã© suficiente: nÃ£o preemptar, deixar coexistir
  2. Manter `suspended_p3_queue: VecDeque<PendingRequest>` no `Inner`; ao P1 terminar,
     recolocar os P3 suspensos na fila normal
  3. Adicionar ao `StatusResponse`: `suspended_count: u32` para o LogosPanel mostrar

- [x] LOGOS: injetar parÃ¢metros de eficiÃªncia por prioridade no body dos requests:
  **Motivo:** `num_thread`, `num_batch` e `num_ctx` sÃ£o parÃ¢metros por-requisiÃ§Ã£o aceitos pelo
  Ollama no body de `/api/chat` e `/api/generate` (nÃ£o sÃ£o variÃ¡veis de ambiente). Injetados
  pelo proxy, permitem reduzir impacto de P3 no sistema sem mudar os apps. EvidÃªncia empÃ­rica:
  num_batch 512â†’256 reduz VRAM pico em ~20% (eastondev.com/blog/en/posts/ai/ollama-gpu-scheduling).
  `num_thread` controla quantos cores o Ollama usa para computaÃ§Ã£o â€” limitÃ¡-lo em P3 libera CPU
  para o sistema e outros apps (literatura de CPU inference: diminishing returns alÃ©m de 4 threads
  em modelos pequenos, arxiv 2311.00502).
  **ImplementaÃ§Ã£o (`HUB/src-tauri/src/logos.rs` â€” mesmo middleware do `keep_alive`):**
  Injetar no body antes de repassar ao Ollama, conforme prioridade:
  ```
  P3: num_thread=2, num_batch=256, num_ctx=2048
  P2: num_batch=256 (preservar RAM), num_ctx=null (app decide)
  P1: sem injeÃ§Ã£o (mÃ¡xima performance, app decide tudo)
  ```
  Perfil `low` (CPU-only): P1 â†’ num_thread=3 (deixar 1 core livre para o SO)
  Perfil `medium` (MX150): P3 â†’ num_thread=2, num_gpu=0 (forÃ§ar CPU-only em background)

- [x] LOGOS: consciÃªncia de bateria via UPower/DBus (laptop Lenovo MX150):
  **Motivo:** indexaÃ§Ã£o idle (P3) em bateria esgota carga e aquece o laptop sem benefÃ­cio
  imediato. UPower Ã© o padrÃ£o Linux para gerenciamento de energia (freedesktop.org).
  Pesquisa relevante: PowerLens (arxiv 2603.19584, 2025) demonstrou 38.8% de economia de
  energia via gerenciamento adaptativo de recursos em nÃ­vel de sistema. Em bateria, a
  prioridade Ã© preservar energia, nÃ£o maximizar throughput de inferÃªncia.
  **ImplementaÃ§Ã£o (`HUB/src-tauri/src/logos.rs`):**
  1. Adicionar dependÃªncia `battery = "0.7"` ao `Cargo.toml` (cross-platform: Linux + Windows)
     Alternativa Linux-only com mais detalhes: crate `zbus` para ler `org.freedesktop.UPower`
  2. Adicionar campo `on_battery: bool` ao struct `Inner`; atualizar a cada 60s num tokio task
  3. Quando `on_battery = true`, aplicar em cascata:
     â€” Bloquear todos os requests P3 (retornar 503 com body `{"reason": "on_battery"}`)
     â€” Injetar `keep_alive: "0"` em P1 e P2 (liberar modelo apÃ³s cada resposta, economizar VRAM)
     â€” Injetar `num_thread: 2` em P1 e P2 (reduzir consumo de energia do CPU)
     â€” Threshold de P2 mais conservador: bloquear se CPU > 60% (vs 85% em AC)
  4. Adicionar ao `StatusResponse`: `on_battery: bool`
  5. Atualizar `LogosStatus` type em `HUB/src/types.ts`
  6. `LogosPanel.tsx`: exibir badge "âš¡ Bateria" quando `on_battery=true`; colorir P3 de vermelho
     para indicar bloqueio

### LOGOS â€” scheduling de processos em nÃ­vel de SO

- [x] LanÃ§ar o processo Ollama com prioridade reduzida via `nice` quando gerenciado pelo LOGOS:
  **Motivo:** `nice` Ã© a ferramenta padrÃ£o UNIX para indicar ao scheduler do kernel que um processo
  deve ceder CPU para outros quando hÃ¡ contention. Definir nice=10â€“15 para o Ollama em P3 garante
  que o sistema continue responsivo sem necessitar de polling ativo do LOGOS. Custo de implementaÃ§Ã£o:
  uma linha. Custo de nÃ£o implementar: CPU a 90% quando P3 estÃ¡ ativo.
  **ImplementaÃ§Ã£o (`HUB/src-tauri/src/logos.rs`):**
  â€” Linux: `Command::new("nice").args(["-n", "10", "ollama", "serve"])` ao lanÃ§ar Ollama em P3
    OU usar `renice(2)` via syscall apÃ³s obter o PID do processo Ollama
  â€” Windows: `SetPriorityClass(handle, BELOW_NORMAL_PRIORITY_CLASS)` via `windows-sys` crate
  â€” Ao receber P1: temporariamente aumentar prioridade do Ollama (`renice -5 $pid`) para minimizar
    latÃªncia, restaurar apÃ³s P1 concluir

- [x] LanÃ§ar processos de background do Python (KOSMOS idle analysis, Mnemosyne idle indexer)
  com prioridade de SO reduzida:
  **Motivo:** os workers de background Python (`_IndexJobWorker`, `KosmosAnalyzer`) rodam em
  threads PySide6 com `IdlePriority`, mas isso sÃ³ afeta o scheduler do Python (GIL), nÃ£o o
  scheduler do OS. O OS ainda aloca CPU para o processo Python normalmente. `os.nice()` afeta
  o processo inteiro â€” deve ser chamado no worker no inÃ­cio de sua execuÃ§Ã£o.
  **ImplementaÃ§Ã£o:**
  â€” `Mnemosyne/core/idle_indexer.py`, no inÃ­cio de `_IndexJobWorker.run()`:
    ```python
    import os, sys
    if sys.platform != "win32":
        os.nice(15)          # Linux/Mac: nice mÃ¡ximo para background
    else:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(
            ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)  # BELOW_NORMAL
    ```
  â€” `KOSMOS/app/core/background_worker.py` (ou equivalente): mesma lÃ³gica no inÃ­cio do worker
  â€” Resultado: durante idle indexing, o sistema mantÃ©m 30â€“40% de CPU disponÃ­vel para apps ativos

- [x] Configurar cgroup para o Ollama no systemd (Linux â€” mÃ¡quina principal e laptop):
  **Motivo:** nice afeta prioridade relativa mas nÃ£o limita CPU absoluto. cgroups v2 (padrÃ£o
  no CachyOS/Arch) permitem limitar CPU por quota absoluta (ex: no mÃ¡ximo 50% de um core) e
  memÃ³ria mÃ¡xima. O systemd usa cgroups nativamente via diretivas de unit file.
  **ImplementaÃ§Ã£o (manual, documentar no README do HUB):**
  Criar/editar `~/.config/systemd/user/ollama.service.d/logos-limits.conf`:
  ```ini
  [Service]
  CPUWeight=20        # vs 100 padrÃ£o â€” Ollama cede CPU quando hÃ¡ contention
  CPUQuota=80%        # nunca exceder 80% de 1 core em P3 (ajustar se multi-GPU)
  MemoryMax=10G       # nÃ£o exceder 10 GB de RAM (proteger os 6 GB restantes do sistema)
  IOSchedulingClass=idle  # I/O em idle â€” nÃ£o compete com apps ativos em disco
  ```
  Reload: `systemctl --user daemon-reload && systemctl --user restart ollama`
  Este arquivo Ã© gerenciado pelo HUB: ao detectar perfil `high` ou `medium`, escreve os valores
  corretos e recarrega o serviÃ§o.

### Feed de atividade unificado

- [ ] Painel mostrando eventos recentes de todos os apps em ordem cronolÃ³gica:
  â€” KOSMOS: artigos baixados, anÃ¡lises concluÃ­das, erros de scraping
  â€” Hermes: transcriÃ§Ãµes iniciadas / concluÃ­das
  â€” Mnemosyne: indexaÃ§Ãµes e re-indexaÃ§Ãµes
  â€” AETHER: projetos/capÃ­tulos salvos
  â€” AKASHA: arquivamentos, crawls concluÃ­dos
- [ ] Filtro por app e por tipo de evento (sucesso / erro / info)
- [ ] ImplementaÃ§Ã£o: cada app escreve eventos num arquivo de log estruturado (JSON Lines)
  em `{sync_root}/{app}/activity.jsonl`; HUB lÃª e exibe em polling leve

### Busca global via AKASHA (Mapa de Contexto)

- [ ] Campo de busca no HUB que consulta o AKASHA e retorna resultados cruzados de todas as fontes:
  â€” Mnemosyne (RAG semÃ¢ntico), KOSMOS (artigos), Hermes (transcriÃ§Ãµes), AETHER (notas/capÃ­tulos)
- [ ] Exibir resultados agrupados por fonte com snippet de contexto
- [ ] Depende de: AKASHA implementar API de "Mapa de Contexto" (ver PENDÃŠNCIAS â€” ECOSSISTEMA)

### Quick capture / inbox

- [ ] Campo de captura rÃ¡pida acessÃ­vel sem abrir nenhum app especÃ­fico
  â€” roteamento automÃ¡tico por tipo de conteÃºdo:
    - URL de vÃ­deo (youtube.com, etc.) â†’ dispara Hermes
    - URL genÃ©rica â†’ envia para AKASHA arquivar
    - Texto livre â†’ cria nota rÃ¡pida no OGMA
  â€” feedback visual confirmando para onde o conteÃºdo foi roteado

### EstatÃ­sticas cross-app ("diÃ¡rio de atividade polimÃ¡tica")

- [ ] Painel de mÃ©tricas combinadas por perÃ­odo (dia / semana / mÃªs):
  â€” artigos lidos (KOSMOS)
  â€” palavras escritas / sessÃµes de escrita (AETHER)
  â€” documentos indexados (Mnemosyne)
  â€” vÃ­deos transcritos e duraÃ§Ã£o total (Hermes)
  â€” pÃ¡ginas arquivadas (AKASHA)
- [ ] VisualizaÃ§Ã£o estilo "mapa de calor" (tipo GitHub contributions) mostrando dias de atividade
- [ ] ImplementaÃ§Ã£o: agregar dados dos logs de atividade de cada app (activity.jsonl)

---

> HUB Ã© Tauri. A interface jÃ¡ Ã© web-based mas deve funcionar em janelas menores.

- [ ] **Auditar grid de cards de apps**
  â€” De 3 colunas â†’ 2 â†’ 1 conforme janela estreita (CSS grid `auto-fill`)
- [ ] **LogosView e painÃ©is de status**
  â€” Verificar que scrollam corretamente quando a janela Ã© reduzida
- [ ] **Testar em janela 800Ã—600 mÃ­nima**

---


### LOGOS â€” Proxy Inteligente de LLM

### LOGOS: proxy central de LLM (integrado ao HUB)
- [x] Decidir arquitetura final: LOGOS como parte do backend Rust do HUB vs. serviÃ§o separado
  â€” recomendado: integrado ao HUB (evita ter mais um processo rodando; HUB jÃ¡ Ã© o maestro)
- [x] Definir protocolo: `POST /logos/chat { app, priority, model, messages, ... }` â†’ 200 ou 429
- [x] Implementar fila de prioridades (`HUB/src-tauri/src/logos.rs`):
  - P1: aguarda indefinidamente (sem timeout)
  - P2: timeout 60s
  - P3: timeout 30s + 429 imediato se VRAM > 85%
- [x] Hardware Guard: VRAM via Ollama `/api/ps` (sum size_vram) + sysfs Linux para total
  â€” Linux/CachyOS: `/sys/class/drm/card{n}/device/mem_info_vram_total` (AMD sysfs)
  â€” Windows: total_vram desconhecido (sem GPU discreta no i5-3470); pct retorna None
- [x] Cancelamento gracioso: `POST /logos/silence` â†’ keep_alive: 0 em todos os modelos carregados
- [x] Failsafe implementado em `ecosystem_client.py`:
  â€” LOGOS online: request roteado com prioridade
  â€” LOGOS offline: fallback direto ao Ollama (modo emergÃªncia silencioso)
  â€” LOGOS retorna 429: RuntimeError propagado ao app chamador
- [x] Tauri IPC commands: `logos_get_status`, `logos_silence` (para o frontend HUB)

Arquivos:
  â€” `HUB/src-tauri/src/logos.rs` â€” servidor Axum porta 7072
  â€” `HUB/src-tauri/src/commands/logos.rs` â€” IPC Tauri
  â€” `ecosystem_client.py` â€” `request_llm()`, `logos_status()`, `logos_silence()`

### Gerenciamento de LLM simultÃ¢neo (Mnemosyne + KOSMOS)
- [x] Investigar comportamento atual quando os dois apps fazem chamadas simultÃ¢neas ao Ollama
  â€” risco: VRAM saturada â†’ travamento no Windows 10 (8 GB RAM, GPU integrada)

  **Achados:**
  â€” KOSMOS: `ai_bridge.py` usa `requests.Session` direto ao `/api/generate`, timeout=120s, sem coordenaÃ§Ã£o
  â€” Mnemosyne: `langchain_ollama` em QThread via `workers.py`, sem coordenaÃ§Ã£o
  â€” Nenhum dos dois usa `ecosystem_client.request_llm()` â†’ nÃ£o passam pelo LOGOS
  â€” No Windows 10 (8 GB RAM, GPU integrada): chamadas simultÃ¢neas podem saturar a RAM com dois modelos carregados
  â€” No CachyOS (RX 6600, 8 GB VRAM): dois modelos 7B simultÃ¢neos arriscam overflow de VRAM

  **SoluÃ§Ã£o imediata sem cÃ³digo** â€” configurar variÃ¡veis de ambiente do Ollama:
  ```
  OLLAMA_NUM_PARALLEL=1        # serializa requisiÃ§Ãµes dentro do Ollama
  OLLAMA_MAX_LOADED_MODELS=1   # descarrega modelo anterior antes de carregar novo
  ```
  No Windows: `setx OLLAMA_NUM_PARALLEL 1` + `setx OLLAMA_MAX_LOADED_MODELS 1` (requer reiniciar Ollama)
  No CachyOS: adicionar ao `.env` do serviÃ§o systemd do Ollama ou ao `~/.config/fish/config.fish`

- [x] SoluÃ§Ã£o de longo prazo: migrar `KOSMOS/app/core/ai_bridge.py` e `Mnemosyne/core/workers.py`
  para usar `ecosystem_client.request_llm()` â†’ passam pelo LOGOS com controle de prioridade e VRAM

  **Migrado (chamadas sÃ­ncronas P3):**
  â€” KOSMOS `ai_bridge.py`: `generate()` usa `request_llm(priority=3)` via LOGOS; `generate_stream()` e `embed()` permanecem diretos (streaming/embeddings nÃ£o passam pelo LOGOS)
  â€” Mnemosyne `memory.py`: `compact_session_memory()` usa `request_llm(priority=3)`
  â€” Mnemosyne `summarizer.py`: fase Map de `iter_summary()` + `prepare_summary()` + `summarize_all()` usam `request_llm(priority=3)`; fase Reduce (streaming) permanece via LangChain `OllamaLLM.stream()`

  **NÃ£o migrado (requer suporte a streaming no LOGOS):**
  â€” Mnemosyne `AskWorker`: `ChatOllama.stream()` â€” RAG interativo
  â€” Mnemosyne `SummarizeWorker`/`FaqWorker`/`StudioWorker`/`GuideWorker`: usam `iter_*()` com streaming LangChain

### LOGOS: otimizaÃ§Ãµes de configuraÃ§Ã£o do Ollama

Achados de pesquisa `KOSMOS/pesquisa.txt` (2026-04-25) â€” LOGOS Ã© responsÃ¡vel por configurar e expor essas variÃ¡veis de ambiente ao Ollama:

- [x] Configurar `OLLAMA_KEEP_ALIVE=-1` via injeÃ§Ã£o automÃ¡tica no proxy
  â€” LOGOS injeta `keep_alive: -1` em todo request que nÃ£o o definiu explicitamente
  â€” elimina cold start de 3â€“10s; modelo permanece carregado na VRAM entre anÃ¡lises
- [x] Configurar `OLLAMA_KV_CACHE_TYPE=q8_0` no systemd
  â€” reduz VRAM do KV cache em ~50%; abre espaÃ§o para `num_ctx` maior ou NUM_PARALLEL=2
- [x] Configurar concorrÃªncia dinÃ¢mica baseada no tamanho do modelo
  â€” LOGOS usa `Semaphore::new(2)` com `acquire_many_owned(permits)`:
    modelos â‰¤3B adquirem 1 permit â†’ atÃ© 2 rodam em paralelo
    modelos >3B adquirem 2 permits â†’ exclusividade total
  â€” `LogosPanel` exibe badge "leve" / "pesado" do modelo em execuÃ§Ã£o
- [x] Configurar `OLLAMA_NUM_PARALLEL=2` no systemd
  â€” permite ao Ollama aceitar 2 requests simultÃ¢neos; necessÃ¡rio para modelos leves rodarem em paralelo via semÃ¡foro do LOGOS

### LOGOS: seleÃ§Ã£o e especializaÃ§Ã£o de modelos por app

- [x] KOSMOS (anÃ¡lise em background): usar Gemma 2 2B (`gemma2:2b`)
  â€” default `ai_gen_model` em KOSMOS/app/utils/config.py
- [x] Mnemosyne (RAG): usar Qwen 2.5 7B (`qwen2.5:7b`)
  â€” default `llm_model` em Mnemosyne/core/config.py
- [x] KOSMOS: `num_ctx=4096` explÃ­cito e constante em `_AnalyzeWorker` e `_start_analyze`
  â€” Mnemosyne AskWorker: `num_ctx=8192`
- [x] KOSMOS: JSON Schema completo no `_AnalyzeWorker` (constrained decoding via XGrammar)
  â€” `_JSON_SCHEMA` como class constant; `json_schema=` em `ai_bridge.generate()`
- [x] KOSMOS: prÃ©-anÃ¡lise em background â€” `BackgroundAnalyzer` (QThread + PriorityQueue)
  â€” HIGH (P0): artigo aberto pelo usuÃ¡rio â†’ single call imediato
  â€” LOW (P10): novos artigos do feed â†’ enfileirados no startup e em `_on_feed_updated`
  â€” cache check: artigos com `ai_sentiment IS NOT NULL` sÃ£o pulados
- [x] KOSMOS: batching de atÃ© 5 artigos por call LLM no background
  â€” schema dinÃ¢mico por lote; fallback individual se batch falhar
  â€” `num_ctx=8192` para batch; anÃ¡lise interativa permanece `num_ctx=4096`

### LOGOS: perfis de hardware com detecÃ§Ã£o automÃ¡tica por fingerprint de GPU

Objetivo: ao iniciar, o LOGOS identifica em qual mÃ¡quina estÃ¡ rodando via fingerprint de GPU
e seleciona automaticamente o perfil de modelos adequado â€” sem configuraÃ§Ã£o manual por mÃ¡quina.

**Perfis definidos:**

| MÃ¡quina | GPU detectada | LLM (Mnemosyne) | LLM (KOSMOS) | Embedding |
|---|---|---|---|---|
| PC principal | RX 6600 (AMD sysfs / `rocm-smi`) | qwen2.5:7b | gemma2:2b | bge-m3 |
| Laptop Ideapad 330 | MX150 via `nvidia-smi` | gemma2:2b | smollm2:1.7b | nomic-embed-text |
| PC de trabalho (Windows) | nenhuma GPU discreta | (CPU only) modelos leves | smollm2:1.7b | all-minilm |

**LÃ³gica de detecÃ§Ã£o (em ordem):**
1. Tentar `nvidia-smi --query-gpu=name --format=csv,noheader` â†’ se retornar "MX150" â†’ perfil laptop
2. Tentar ler `/sys/class/drm/card*/device/mem_info_vram_total` (AMD sysfs) â†’ se encontrar RX 6600 â†’ perfil principal
3. Fallback â†’ perfil Windows/CPU-only

**ImplementaÃ§Ã£o sugerida:**
- `HUB/src-tauri/src/logos.rs`: funÃ§Ã£o `detect_hardware_profile() -> HardwareProfile` rodando no startup
- `HardwareProfile` enum: `MainPc | Laptop | WorkPc`
- Perfil exposto via `GET /logos/profile` â†’ apps lÃªem e ajustam modelos dinamicamente
- `ecosystem_client.py`: `get_active_profile()` â†’ retorna o perfil atual do LOGOS

- [x] Implementar `detect_hardware_profile()` em `logos.rs` com as 3 etapas de detecÃ§Ã£o
- [x] Definir `HardwareProfile` enum + struct `ModelProfile { llm_mnemosyne, llm_kosmos, embed }`
- [x] Expor `GET /logos/hardware` no servidor Axum
- [x] `ecosystem_client.py`: `get_active_profile()` + adaptar `request_llm()` para usar modelo do perfil ativo
- [x] KOSMOS e Mnemosyne: ler perfil do LOGOS no startup e usar modelos recomendados mas inclua a possibilidade de haver override manual (tornando o recomendado pelo LOGOS sempre como padrÃ£o)
- [x] Criar um botÃ£o para "usar recomendado" ao lado da configuraÃ§Ã£o de LLM no KOSMOS e Mnemosyne
- [x] HUB LogosPanel: exibir perfil ativo ("PC Principal Â· RX 6600", "Laptop Â· MX150 2 GB", etc.)

### LOGOS: proxy transparente para todas as chamadas ao Ollama (correÃ§Ã£o arquitetural)

> Contexto: a implementaÃ§Ã£o atual do LOGOS controla apenas chamadas que passam explicitamente
> por `POST /logos/chat`. Embeddings (LangChain/Chroma), streaming (ChatOllama) e qualquer
> outra chamada direta ao Ollama (porta 11434) sÃ£o invisÃ­veis ao LOGOS â€” ele nÃ£o pode gerenciar
> o que nÃ£o vÃª. O design original previa um proxy transparente: apps apontam para 7072 (LOGOS)
> em vez de 11434 (Ollama). Enquanto essa correÃ§Ã£o nÃ£o for feita, o LOGOS nÃ£o cumpre seu papel
> central de gerenciador de hardware e prioridades para todo o ecossistema.

- [x] `HUB/src-tauri/src/logos.rs` â€” implementar rotas de proxy para os endpoints nativos do Ollama:
  â€” `POST /api/chat` e `POST /api/generate` â†’ proxy com fila P1/P2/P3 (mesma lÃ³gica do `/logos/chat`)
  â€” `POST /api/embeddings` e `POST /api/embed` â†’ proxy com fila (P3 por padrÃ£o para embeddings)
  â€” `GET /api/tags`, `GET /api/ps`, `DELETE /api/delete` â†’ proxy direto sem fila (metadados)
  â€” identificaÃ§Ã£o do app por header `X-App: <nome>` (ex: `mnemosyne`, `kosmos`)
  â€” keep_alive injetado automaticamente em todas as chamadas de chat/generate que passam pelo proxy
  â€” Hardware Guard (VRAM, CPU, RAM) aplicado a todos os requests, nÃ£o sÃ³ aos via `/logos/chat`
- [x] `ecosystem_client.py` â€” `LOGOS_OLLAMA_BASE` aponta para 7072 (LOGOS); `OLLAMA_DIRECT` 11434;
  `get_ollama_url()` retorna 7072 se LOGOS acessÃ­vel, senÃ£o 11434
- [x] `Mnemosyne/core/indexer.py` â€” `OllamaEmbeddings(base_url="http://localhost:7072")`
- [x] `KOSMOS/app/core/ai_bridge.py` â€” URL base para 7072; header `X-App: kosmos` em embed e generate_stream
- [x] Auditar todos os apps em busca de `localhost:11434` hardcoded e substituir pela URL do LOGOS
- [ ] Testar integraÃ§Ã£o: chat no Mnemosyne (P1) enquanto KOSMOS analisa em background (P3)
  â†’ KOSMOS deve pausar na fila do LOGOS atÃ© o chat terminar

### AKASHA como broker unificado de informaÃ§Ã£o
- [ ] Planejar API de "Mapa de Contexto" no AKASHA:
  â€” dado um termo, retornar resultados cruzados: Mnemosyne (RAG) + KOSMOS (artigos) + Hermes (transcriÃ§Ãµes) + AETHER (notas)
- [ ] HUB consumir essa API num botÃ£o de busca global cross-app

### MigraÃ§Ã£o Rust/PyO3 para indexaÃ§Ã£o (longo prazo)
- [x] Avaliar substituiÃ§Ã£o do indexador Python do AKASHA por mÃ³dulo Rust via PyO3

  **ConclusÃ£o: nÃ£o justificada no volume atual â€” adiar indefinidamente.**

  AnÃ¡lise (2026-04-24):
  - Volume estimado atual: 5kâ€“20k documentos; SQLite FTS5 escala atÃ© ~10M sem degradaÃ§Ã£o
  - Startup do indexador Ã© incremental (sÃ³ mtime diffs) â€” jÃ¡ roda em < 5s
  - Gargalo real do ecossistema: I/O de rede (crawl BFS) e inferÃªncia LLM (Mnemosyne), nÃ£o indexaÃ§Ã£o local
  - Custo: PyO3 introduz build Rust obrigatÃ³rio no CI + complexidade de cross-compile (Windows 10 + CachyOS)
  - tantivy compila sem AVX2 (i5-3470 OK), mas o ganho Ã© imperceptÃ­vel na escala atual

  Gatilhos para reavaliar:
  â€” volume indexado > 500k documentos **ou** startup time > 30s na mÃ¡quina alvo
  â€” buscas FTS retornando em > 2s de forma consistente

---

## AETHER â€” Forja de Mundos

### PadrÃµes de Desenvolvimento

- **Tratamento de erro com tipagem Ã© prioridade absoluta.**
  - Rust: toda funÃ§Ã£o que pode falhar retorna `Result<T, AppError>`. Nunca usar `.unwrap()` ou `.expect()` em cÃ³digo de produÃ§Ã£o.
  - TypeScript: `strict: true` sempre. Erros de comandos Tauri tipados com union types (`type Result<T> = { ok: true; data: T } | { ok: false; error: AppError }`).
  - Erros devem ser tratados no ponto onde ocorrem â€” sem silenciar, sem propagar cegamente.

- **Commit apÃ³s CADA item individual do todo â€” nÃ£o apÃ³s fases ou grupos.**
  - Mensagem de commit referencia o item exato: `feat(fase-0): 0.6 CosmosLayer component`
  - Atualizar o status do item no todo ([x]) ANTES de fazer o commit.

- **Privacidade Ã© prioridade absoluta.**
  - O AETHER nÃ£o coleta, transmite nem registra nenhum dado do usuÃ¡rio.
  - Zero telemetria, zero analytics, zero conexÃµes externas nÃ£o solicitadas.
  - Gerenciamento de arquivos e configuraÃ§Ãµes no estilo Obsidian:
    - Tudo vive na pasta raiz escolhida pelo usuÃ¡rio (o "vault")
    - ConfiguraÃ§Ãµes ficam em `{pasta-raiz}/.aether/` â€” nunca em `~/.aether/` global
    - O usuÃ¡rio tem controle total sobre onde seus dados ficam
    - Cada projeto Ã© uma pasta auto-contida e portÃ¡til

- **Manter `dev_files/dev_bible.txt` atualizado.**
  - Ao concluir qualquer item que introduza novos arquivos, mÃ³dulos, commands ou padrÃµes, atualizar o dev_bible.
  - O dev_bible descreve o estado ATUAL do projeto, nÃ£o o planejado.

- **Sempre atualizar este arquivo ANTES de comeÃ§ar algo que nÃ£o estÃ¡ listado aqui.**

- **Sempre atualizar o status do item ([ ] â†’ [x]) ao concluÃ­-lo.**

---

### Stack

- Backend: Rust (Tauri)
- Frontend: TypeScript + React + Vite
- Armazenamento: arquivos locais (JSON + Markdown/texto plano)
- Build: Tauri CLI (Windows 10 + CachyOS/Linux)

---

### IDENTIDADE VISUAL

**Nome:** AETHER
**SubtÃ­tulo:** FORJA DE MUNDOS
**Ecossistema:** OGMA Â· KOSMOS Â· MNEMOSYNE Â· AETHER

O AETHER segue o design system do ecossistema (definido no OGMA Design Bible):
mesma paleta sÃ©pia, mesma tipografia, mesmas regras de sombra, animaÃ§Ãµes e cosmos.

**Diferencial visual do AETHER dentro do ecossistema:**
- AnimaÃ§Ã£o `pageFloat` â€” folhas de papel caem com rotaÃ§Ã£o ao abrir/criar/deletar capÃ­tulos
- Efeito typewriter â€” texto no splash e em loading states digita caractere por caractere
- Cursor de editor como `_` piscante (sublinhado), nÃ£o `|`
- CosmosLayer com labels mitolÃ³gicos nas constelaÃ§Ãµes (Ã“rion, Cassiopeia, Perseu...)
- Nebulosas com pulso lento animado (8s) nos headers de projeto â€” o "Ã©ter" do app

---

### Design Bible v2.0 â€” Audit (2026-04-11)

- [x] tokens.css: modo noturno migrado para paleta "Atlas AstronÃ´mico Ã  Meia-Noite"
- [x] tokens.css: `--sidebar-w` corrigido para 224px (era 260px)
- [x] typography.css: hierarquia tipogrÃ¡fica alinhada ao bible (t-body 13px, t-btn 11px, t-label 10px, t-section 9px, t-badge 10px, t-meta 9px)
- [x] components.css: `.btn` corrigido para 11px / 5px 14px
- [x] Splash.tsx: background hardcoded `rgba(26,22,16,0.45)` â†’ `var(--paper)`

---

### FASE 0 â€” Design System

> EntregÃ¡vel: toda a fundaÃ§Ã£o visual implementada. Nenhum componente de UI Ã© construÃ­do sem isso estar pronto.

- [x] 0.1 VariÃ¡veis CSS globais (tokens do ecossistema)
  - Paleta completa: `--paper`, `--paper-dark`, `--paper-darker`, `--paper-darkest`
  - Tintas: `--ink`, `--ink-light`, `--ink-faint`, `--ink-ghost`
  - Acento: `--accent` (#b8860b dia / #D4A820 noite), `--cursor-color`
  - Funcionais: `--ribbon`, `--ribbon-light`, `--accent-green`, `--stamp`
  - Linhas: `--rule`, `--margin-line`, `--shadow`
  - MÃ©tricas: `--sidebar-w: 260px` (binder mais largo que OGMA), `--topbar-h: 44px`, `--radius: 2px`
  - TransiÃ§Ãµes: `--transition: 140ms ease`

- [x] 0.2 Tipografia â€” carregar e configurar as trÃªs famÃ­lias
  - `--font-display`: IM Fell English (Google Fonts) â€” tÃ­tulos, editor, itÃ¡lico como regra
  - `--font-mono`: Special Elite (Google Fonts) â€” UI geral, botÃµes, labels
  - `--font-code`: Courier Prime (Google Fonts) â€” blocos de cÃ³digo no editor
  - Hierarquia tipogrÃ¡fica completa (tamanhos, letter-spacing, pesos)
  - Regra de itÃ¡lico: IM Fell English Ã© SEMPRE itÃ¡lico em tÃ­tulos e conteÃºdo

- [x] 0.3 AnimaÃ§Ãµes base (herdadas do ecossistema)
  - `paperFall` â€” translateY(-14px) + rotate(-0.4deg) â†’ 0, 0.22s ease-out
  - `fadeIn` â€” opacity 0â†’1, 0.15â€“0.25s ease
  - `slideIn` â€” translateX(-16px) + opacity, para sidebar/drawers
  - `blink` â€” opacity 1â†’0â†’1, 1.2s (loading dots) / 0.6s (editor cursor)
  - `toastIn` â€” translateY(6px) + opacity, 180ms ease-out

- [x] 0.4 AnimaÃ§Ãµes exclusivas do AETHER
  - `pageFloat` â€” folha retangular cai com rotaÃ§Ã£o suave (Â±3deg) e translaÃ§Ã£o diagonal
    - Variante entrada: cai de cima com rotaÃ§Ã£o leve, pousa
    - Variante saÃ­da (deletar): voa para canto superior direito e desaparece
  - `typewriterReveal` â€” texto revela caractere por caractere com delay mecÃ¢nico (30ms/char)
    - Usado no splash e em loading states
  - `etherPulse` â€” opacity 0.4â†’0.65â†’0.4, 8s ease-in-out infinite (nebulosas dos headers)

- [x] 0.5 Textura de papel
  - `body::after` com SVG `feTurbulence` (baseFrequency: 0.65, numOctaves: 4)
  - Opacity: 30%, pointer-events: none, z-index: 0
  - InvisÃ­vel no modo noturno (intencional)

- [x] 0.6 Componente `<CosmosLayer>`
  - SVG procedural determinÃ­stico (seed baseado no ID do projeto)
  - Elementos: nebulosas, estrelas (10 pontas), constelaÃ§Ãµes, cometa, lua crescente
  - **Diferencial AETHER:** labels mitolÃ³gicos nas constelaÃ§Ãµes (Special Elite, 7px, opacity: 0.35)
  - **Diferencial AETHER:** nebulosas com `etherPulse` animado
  - Densidades: `low` (headers de capÃ­tulo), `medium` (headers de livro), `high` (splash, tela inicial)
  - Props: `seed`, `density`, `animated` (boolean â€” desativa pulso se false)

- [x] 0.7 Linha vermelha de margem
  - `sidebar::before` â€” 1px vertical em left: 48px (ajustado para binder)
  - Cor: `--margin-line`
  - Replicada no splash em mesma posiÃ§Ã£o

- [x] 0.8 Sistema de sombra flat (sem blur)
  - BotÃ£o: `2px 2px 0 var(--rule)`
  - BotÃ£o primary: `2px 2px 0 var(--stamp)`
  - Card: `3px 3px 0 var(--paper-darker)`
  - Modal: `6px 6px 0 var(--ink-ghost)`
  - Menu popup: `3px 3px 0 var(--rule)`
  - `:active` em botÃµes e cards: sombra some + `translate(1px, 1px)`

- [x] 0.9 Scrollbar vintage
  - Width: 6px, border-radius: 2px
  - Track: `--paper-dark`, thumb: `--rule`, hover: `--stamp`

- [x] 0.10 Cursor dourado e cursor de editor
  - `caret-color: var(--accent)` em todos os inputs e textareas
  - No editor de capÃ­tulo: cursor customizado como `_` piscante (via CSS/JS)

- [x] 0.11 SeleÃ§Ã£o de texto Ã¢mbar
  - `::selection { background: rgba(184,134,11,0.25); }`
  - Editor modo escuro: `rgba(212,168,32,0.2)`

- [x] 0.12 Sistema de temas (dia / noite)
  - Toggle via classe `dark` no `<html>`
  - Persiste em localStorage: `aether_theme`
  - Sem flash de tema errado no carregamento (aplicar antes do render)

- [x] 0.13 Sistema de toasts / notificaÃ§Ãµes
  - Tipos: `success`, `error`, `warning`, `info`
  - PosiÃ§Ã£o: fixed, bottom: 24px, right: 24px
  - Auto-dismiss: error=7s, success=3s, warning=5s, info=4s
  - Cores dentro da paleta sÃ©pia (sem branco puro, sem preto puro)
  - AnimaÃ§Ã£o: `toastIn`

- [x] 0.14 Splash screen
  - Overlay sÃ©pia (rgba(26,22,16,0.85)) com backdrop blur 2px
  - Card 520Ã—340px, border-radius: 2px, sombra flat 8px
  - `<CosmosLayer density="high" animated={true}>`
  - Linha de margem vermelha (left: 48px)
  - "AETHER" em IM Fell English 68px itÃ¡lico
  - "FORJA DE MUNDOS" em Special Elite 9px uppercase letter-spacing: 0.22em
  - Texto de status com `typewriterReveal`: "Iniciando AETHER..." â†’ "Abrindo projetos..." â†’ "Pronto."
  - Dots de loading: "Â· Â· Â·" com `blink` 1.2s
  - VersÃ£o no canto inferior direito (9px)
  - Fade out apÃ³s "Pronto." com delay 400ms

- [x] 0.15 Componentes base de UI
  - BotÃµes: `.btn`, `.btn-primary`, `.btn-accent`, `.btn-danger`, `.btn-ghost`, `.btn-sm`, `.btn-icon`
  - Inputs e labels (IM Fell no corpo, Special Elite nos labels)
  - Cards com `paperFall` e sombra flat
  - Modais com overlay sÃ©pia e `paperFall`
  - Badges / tags (border-radius: 20px para pills)

---

### FASE 1 â€” FundaÃ§Ã£o (projeto abrÃ­vel e editÃ¡vel)

> EntregÃ¡vel: abrir o AETHER, criar um projeto, criar capÃ­tulos e escrever texto. Nada mais â€” mas isso funciona.

- [x] 1.1 Scaffold do projeto Tauri + React + TypeScript
  - Vite como bundler, `strict: true` no tsconfig
  - Estrutura de pastas: `src-tauri/` (Rust), `src/` (React)

- [x] 1.2 Definir e implementar estrutura de dados em disco
  - Modelo Obsidian: usuÃ¡rio escolhe uma pasta raiz ("vault") na primeira abertura
  - Dois nÃ­veis de armazenamento:
    1. **AppData do sistema** (`~/.local/share/aether/` no Linux, `%AppData%\aether\` no Windows)
       - `app.json` â€” caminho do Ãºltimo vault aberto (apenas isso)
       - Gerenciado pelo Tauri via `tauri::api::path::app_data_dir`
    2. **Dentro do vault** (portÃ¡til, controlado pelo usuÃ¡rio)
       - `{vault}/.aether/config.json` â€” tema, fonte, estado da UI, etc.
       - `{vault}/.aether/` â€” outros dados internos do app (snapshots, cache, etc.)
       - `{vault}/{projeto}/project.json` â€” metadados do projeto
       - `{vault}/{projeto}/{livro}/book.json` â€” metadados do livro
       - `{vault}/{projeto}/{livro}/{capitulo}.md` â€” conteÃºdo dos capÃ­tulos
  - Tipos Rust: `AppState`, `VaultConfig`, `Project`, `Book`, `Chapter` com `serde` + `serde_json`
  - `AppError` enum cobrindo todos os erros de I/O

- [x] 1.3 Comandos Tauri: gerenciamento de projetos
  - `list_projects() -> Result<Vec<ProjectMeta>, AppError>`
  - `create_project(name) -> Result<ProjectMeta, AppError>`
  - `open_project(id) -> Result<Project, AppError>`
  - `delete_project(id) -> Result<(), AppError>`

- [x] 1.4 Comandos Tauri: livros e capÃ­tulos
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

- [x] 1.6 Tela inicial â€” lista de projetos
  - Criar novo projeto
  - Abrir projeto existente
  - Remover projeto

- [x] 1.7 Layout principal do projeto
  - Painel binder lateral: Ã¡rvore Livros > CapÃ­tulos
  - Ãrea central: editor de texto
  - Criar/renomear/deletar livros e capÃ­tulos pelo binder
  - Reordenar capÃ­tulos via drag & drop

- [x] 1.8 Editor de texto WYSIWYG com TipTap
  - Biblioteca: TipTap (ProseMirror) â€” renderizaÃ§Ã£o em tempo real
  - Sem "modo leitura": o texto Ã© SEMPRE renderizado, nunca mostra sÃ­mbolos Markdown
  - Digitar `**texto**` â†’ imediatamente vira negrito; `_texto_` â†’ itÃ¡lico; etc.
  - ParÃ¡grafos indentados (text-indent na primeira linha, estilo livro impresso)
  - Tipografia: IM Fell English itÃ¡lico, 16px, line-height 1.75, coluna centralizada
  - Cursor estilo mÃ¡quina de escrever: `_` piscante via CSS (substituir cursor padrÃ£o `|`)
  - Auto-save com debounce 500ms apÃ³s parar de digitar
  - Indicador de status "Salvando..." / "Salvo" no rodapÃ© do editor
  - Exporta/importa como Markdown puro (compatÃ­vel com os .md do vault)

---

### FASE 1.5 â€” Itens pendentes identificados em uso

> Itens que surgiram durante os testes da Fase 1. Devem ser feitos antes da Fase 2.

- [x] 1.9 Tipos de projeto: livro Ãºnico vs sÃ©rie
  - Ao criar projeto, perguntar: "Livro Ãºnico" ou "SÃ©rie"
  - **Livro Ãºnico**: nome do projeto = nome do livro; livro criado automaticamente; binder oculta a camada "livro" e mostra sÃ³ capÃ­tulos
  - **SÃ©rie**: nome da sÃ©rie separado do nome dos livros; binder mostra Ã¡rvore SÃ©rie > Livros > CapÃ­tulos normalmente
  - Armazenar `project_type: "single" | "series"` em project.json
  - Ajustar Binder para renderizar diferente conforme o tipo

- [x] 1.10 Modal de criaÃ§Ã£o de projeto com metadados
  - Substituir o modal simples atual por um wizard/form mais completo
  - Campos: tipo (Ãºnico/sÃ©rie), tÃ­tulo, subtÃ­tulo opcional, descriÃ§Ã£o/sinopse
  - Metadados de livro: gÃªnero, pÃºblico-alvo, idioma, tags livres
  - Metadados de worldbuilding: sistema de magia (sim/nÃ£o), nÃ­vel tecnolÃ³gico, inspiraÃ§Ãµes
  - Todos os campos opcionais exceto tÃ­tulo e tipo
  - Salvar em project.json

- [x] 1.11 Dashboard do projeto
  - Tela inicial ao abrir um projeto (antes de selecionar capÃ­tulo)
  - CosmosLayer de fundo com seed do projeto
  - Nome, subtÃ­tulo, descriÃ§Ã£o do projeto
  - EstatÃ­sticas: total de palavras, total de capÃ­tulos, data de criaÃ§Ã£o
  - Widgets expansÃ­veis no futuro (metas, personagens, etc.)

- [x] 1.12 Sistema de logs em arquivo
  - Logs salvos dentro do vault em `{vault}/.aether/logs/aether-YYYY-MM-DD.log`
  - RotaÃ§Ã£o diÃ¡ria; manter Ãºltimos 7 dias
  - NÃ­vel INFO em produÃ§Ã£o, DEBUG em dev
  - Registrar: abertura/fechamento do vault, erros, saves, operaÃ§Ãµes de CRUD
  - Implementar em Rust via tauri-plugin-log com appender de arquivo

---

### FASE 2 â€” ExperiÃªncia de escrita

> EntregÃ¡vel: escrever com conforto. Foco, tipografia, estatÃ­sticas bÃ¡sicas.

- [x] 2.1 Temas: claro, escuro, sÃ©pia
- [x] 2.2 Tipografia customizÃ¡vel (fonte, tamanho, espaÃ§amento, largura da coluna de texto)
- [x] 2.3 Modo foco / distraction-free (esconde binder e UI, sÃ³ o texto)
- [x] 2.4 Modo typewriter (cursor sempre centralizado verticalmente)
- [x] 2.5 Tela cheia (F11)
- [x] 2.6 Contagem de palavras e caracteres em tempo real
- [x] 2.7 Status por capÃ­tulo (Rascunho / RevisÃ£o / Final)
- [x] 2.8 Sinopse por capÃ­tulo (campo no binder ou painel lateral)
- [x] 2.9 Localizar e substituir no capÃ­tulo atual

---

### FASE 3 â€” OrganizaÃ§Ã£o avanÃ§ada

> EntregÃ¡vel: visÃµes alternativas da estrutura do projeto.

- [x] 3.1 Vista corkboard (cartÃµes de capÃ­tulo com tÃ­tulo + sinopse)
- [x] 3.2 Vista outline (lista com status, sinopse e contagem de palavras)
- [x] 3.3 Lixeira â€” capÃ­tulos deletados ficam recuperÃ¡veis
- [x] 3.4 Scratchpad por capÃ­tulo (bloco de notas lateral)
- [x] 3.5 Modo split: editor + scratchpad/notas lado a lado

---

### FASE 4 â€” Personagens & Worldbuilding

> EntregÃ¡vel: base de lore do projeto, separada da escrita mas sempre acessÃ­vel.

- [x] 4.1 Fichas de personagem com campos customizÃ¡veis
- [x] 4.2 Relacionamentos entre personagens (mapa/grafo simples)
- [x] 4.3 Notas de worldbuilding por categoria (locais, facÃ§Ãµes, etc.)
- [x] 4.4 Linha do tempo de eventos
- [x] 4.5 Anexar imagens a personagens e locais
- [x] 4.6 Tags â€” cruzar personagens/locais com capÃ­tulos

---

### FASE 5 â€” Metas & HistÃ³rico

> EntregÃ¡vel: acompanhar progresso e proteger o trabalho.

- [x] 5.1 Meta de palavras por capÃ­tulo e por livro
- [x] 5.2 Meta de sessÃ£o de escrita com timer
- [x] 5.3 Streak diÃ¡rio de escrita
- [x] 5.4 Painel de estatÃ­sticas (palavras totais, ritmo, sessÃµes)
- [x] 5.5 Snapshots de capÃ­tulo (histÃ³rico de versÃµes manual + automÃ¡tico)
- [x] 5.6 ComentÃ¡rios/anotaÃ§Ãµes inline no texto

---

### FASE 6 â€” ExportaÃ§Ã£o

> EntregÃ¡vel: levar o texto para fora do AETHER.

- [ ] 6.1 Export por capÃ­tulo individual
- [ ] 6.2 Export por livro (capÃ­tulos concatenados)
- [ ] 6.3 Export do projeto completo
- [ ] 6.4 Formatos: Markdown, texto plano, DOCX, PDF
- [ ] 6.5 Formato EPUB
- [ ] 6.6 ConfiguraÃ§Ãµes de export (incluir/excluir sinopses, metadados, notas)

---

### FASE 7 â€” Polimento & Extras

> EntregÃ¡vel: produto refinado.

- [x] 7.0 BotÃ£o de excluir visÃ­vel para projetos, livros e capÃ­tulos
      â€” ProjectCard: hover revela botÃ£o Ã—; confirmaÃ§Ã£o 2 passos; sai do modo confirmaÃ§Ã£o
        ao tirar o mouse. Livros e capÃ­tulos: Ã— no hover jÃ¡ estava implementado.
        delete_book estÃ¡ implementado em Rust + frontend.
- [ ] 7.1 Atalhos de teclado customizÃ¡veis
- [ ] 7.2 Gerador de nomes
- [ ] 7.3 Projetos recentes na tela inicial com preview
- [ ] 7.4 Onboarding (tela de boas-vindas para primeiro uso)
- [ ] 7.5 ConfiguraÃ§Ãµes globais (tema padrÃ£o, pasta de dados, fonte padrÃ£o)
- [ ] 7.6 Build de distribuiÃ§Ã£o â€” Windows installer + pacote Linux (AppImage/deb)

---

### BACKLOG (futuro, fora do escopo atual)

- Sync opcional com cloud (Google Drive, Dropbox, ou prÃ³prio)
- ColaboraÃ§Ã£o em tempo real
- Plugin/extensÃ£o system
- IntegraÃ§Ã£o com ferramentas de revisÃ£o gramatical
- VersÃ£o mobile (leitura + notas)


---




### Bug: vault_path nÃ£o atualiza apÃ³s mudanÃ§a no HUB
- [x] Investigar por que o AETHER continua salvando no caminho antigo mesmo apÃ³s `sync_root` ser atualizado no HUB
  â€” causa: startup lia app.json local e sobrescrevia o ecosystem.json, ignorando o que o HUB gravou
  â€” fix: `ecosystem.rs` expÃµe `read_vault_path()`; `lib.rs` compara ecosystem.json vs local e prefere ecosystem.json
- [ ] Adicionar opÃ§Ã£o de configurar `vault_path` dentro do prÃ³prio AETHER (sem depender exclusivamente do HUB)

### Responsividade â€” AETHER

> AETHER Ã© Tauri (React + CSS). Responsividade significa: a Ã¡rea de ediÃ§Ã£o deve escalar bem
> em janelas menores sem perder usabilidade.

- [ ] **Auditar sidebar de projetos/capÃ­tulos**
  â€” Em janelas estreitas (~800px) a sidebar pode esconder o editor
  â€” Fix: `min-width` na sidebar, collapsÃ­vel com toggle button abaixo de 900px
- [ ] **Barra de ferramentas do editor**
  â€” BotÃµes de formataÃ§Ã£o podem overflow em janela estreita
  â€” Fix: ocultar labels de texto, manter apenas Ã­cones abaixo de 900px; wrapping se necessÃ¡rio
- [ ] **Testar em janela 900Ã—600 mÃ­nima**

---

### VerificaÃ§Ã£o de formato de saÃ­da

- [ ] Verificar se todos os arquivos gerados pelo AETHER (escrita, fichas, worldbuilding) sÃ£o salvos como `.md`
  **Motivo:** Markdown garante portabilidade e seguranÃ§a dos dados â€” os arquivos devem ser legÃ­veis
  sem o AETHER, sincronizÃ¡veis via Proton Drive/git, e compatÃ­veis com outros editores (Obsidian, VSCode).
  Confirmar que nenhum dado fica preso em formato binÃ¡rio ou JSON opaco nÃ£o-editÃ¡vel pelo usuÃ¡rio.

---

### Pesquisas pendentes

- [ ] **Acesso remoto ao AETHER** â€” pesquisar abordagens para acessar projetos/vault fora da rede local
  (Tailscale, self-hosted sync, CRDT via websocket). Ver tambÃ©m FASE 3 do HUB (linha ~400 deste arquivo).

- [ ] **Escrita colaborativa em tempo real** â€” pesquisar como mÃºltiplas pessoas podem escrever simultaneamente
  no mesmo documento remotamente (referÃªncias: Ellipsus, Google Docs, Notion).
  Tecnologias relevantes: OT (Operational Transformation), CRDT (Yjs/Automerge), WebSocket multiplex.

- [ ] **VersÃ£o Android do AETHER** â€” pesquisar viabilidade de Tauri Android para o AETHER
  (acesso ao vault, editor de markdown, fichas de personagem/worldbuilding no celular).
  Ver replanejamento da Fase 3 do HUB para contexto sobre o que jÃ¡ foi descartado.

---

## AKASHA â€” Buscador Pessoal


Buscador pessoal local. Agrega resultados da web e do ecossistema numa interface Ãºnica,
com downloads genÃ©ricos e integraÃ§Ã£o com qBittorrent.
Stack: FastAPI + HTMX + Jinja2 + SQLite (aiosqlite) + uv Â· Porta 7071.

---

### PadrÃµes de Desenvolvimento

- **Tipagem completa:** Pydantic `BaseModel` em todas as rotas; `-> tipo` em todas as funÃ§Ãµes
- **Erros explÃ­citos:** `HTTPException` com status code em todos os caminhos de erro
- **I/O nunca silencioso** fora do bloco de integraÃ§Ã£o com `ecosystem.json`
- **`uv` obrigatÃ³rio:** `pyproject.toml`, nunca `requirements.txt`
- **Commits por item:** um commit git a cada item concluÃ­do
- **Atualizar este TODO** antes de implementar qualquer feature nÃ£o listada
- **SQLite versionado:** tabela `settings` com campo `schema_version`; migrations numeradas
- **HTMX:** todo estado mutÃ¡vel via `hx-swap`; todo aÃ§Ã£o tem feedback visual (spinner ou toast)

---

### Fase 1 â€” FundaÃ§Ã£o

> Entrega: servidor sobe na porta 7070, design system completo, pÃ¡gina de busca vazia funcional.

- [x] `pyproject.toml` â€” dependÃªncias uv: `fastapi`, `uvicorn[standard]`, `aiosqlite`, `httpx`,
      `jinja2`, `python-multipart`, `duckduckgo-search`, `qbittorrent-api`, `trafilatura`
- [x] `main.py` â€” FastAPI app + lifespan: inicializa DB, escreve `akasha.base_url`
      em `ecosystem.json` no startup (try/except â€” nunca bloquear)
- [x] `config.py` â€” lÃª `ecosystem.json` via `ecosystem_client`; expÃµe `kosmos_archive`,
      `aether_vault`, `mnemosyne_indices`, `qbt_host`, `qbt_port`; fallback silencioso
- [x] `database.py` â€” schema SQLite + migrations: tabelas `searches`, `downloads`, `settings`
      (campo `schema_version`); funÃ§Ã£o `init_db()` chamada no startup
- [x] `static/style.css` â€” paleta CSS completa (sÃ©pia diurna + noturno astronÃ´mico via
      `prefers-color-scheme: dark`), tipografia (IM Fell English Â· Special Elite Â· Courier Prime),
      componentes: `.btn`, `.btn-ghost`, `.card`, `.input`, `.tag`, `.badge`, `.toast`
- [x] `templates/base.html` â€” layout base: topbar (AKASHA itÃ¡lico 24px, toggle â˜½/â˜€),
      search bar com HTMX (`hx-get="/search" hx-trigger="submit"`), nav tabs (Busca / Downloads / Torrents)
- [x] `templates/search.html` â€” extends base: Ã¡rea de resultados com skeleton loader,
      empty state com buscas recentes
- [x] `iniciar.sh` â€” detecta `.venv` do ecossistema em `../`; se nÃ£o existir, cria venv local;
      `uv sync` e executa `uv run python main.py`; `chmod +x`

---

### Fase 2 â€” Busca Web

> Entrega: busca DuckDuckGo funcional com resultados em cards e histÃ³rico persistido.

- [x] `services/web_search.py` â€” DuckDuckGo via `duckduckgo-search`; cache em SQLite (TTL 1h);
      deduplicaÃ§Ã£o por URL normalizada; retorna `list[SearchResult]` (Pydantic)
- [x] `routers/search.py` â€” `GET /search?q=&sources=web` â†’ renderiza `search.html` com resultados;
      salva query + timestamp em `searches`
- [x] `templates/search.html` â€” cards de resultado: tÃ­tulo linkado, snippet, badge de fonte,
      data; HTMX `hx-get` no form com indicador de loading
- [x] Widget "Buscas recentes" no empty state: lista das Ãºltimas 10 queries da tabela `searches`
- [x] Filtro de fonte no UI: radio/toggle Web / Local / Todos (query param `sources=`)
- [x] BotÃ£o "Carregar mais" abaixo dos cards de resultado: busca a prÃ³xima pÃ¡gina via `offset`
      do DuckDuckGo e acrescenta os cards ao final (HTMX `hx-swap="beforeend"`)

---

### Fase 3 â€” Busca Local

> Entrega: busca nos arquivos do ecossistema integrada com os resultados web.

- [x] `services/local_search.py` â€” ler KOSMOS archive (`{archive_path}/**/*.md`):
      parsear frontmatter YAML simples, indexar tÃ­tulo + corpo em FTS5
- [x] `services/local_search.py` â€” ler AETHER vault (`{vault_path}/*/chapters/*.md`):
      tÃ­tulo e conteÃºdo dos capÃ­tulos; indexar em FTS5
- [x] FTS5 virtual table `local_index` em SQLite: schema `(path, title, body, source, mtime)`
- [x] ReindexaÃ§Ã£o automÃ¡tica no startup se `mtime` dos arquivos mudou desde Ãºltima indexaÃ§Ã£o
- [x] `services/local_search.py` â€” query ChromaDB do Mnemosyne se `mnemosyne_indices`
      nÃ£o vazio (import opcional; graceful fallback se `chromadb` nÃ£o instalado)
- [x] Badge de fonte em cada card: `WEB` Â· `KOSMOS` Â· `AETHER` Â· `MNEMOSYNE` com cor distinta
- [x] **CorreÃ§Ã£o:** `routers/search.py` â€” retornar `web_results` e `local_results` separados no contexto
- [x] **CorreÃ§Ã£o:** `templates/search.html` â€” seÃ§Ãµes separadas quando `sources=all`: "Resultados web" + "No meu ecossistema"

---

### Fase 4 â€” Downloads

> Entrega: baixar arquivos genÃ©ricos com progresso em tempo real via SSE.

- [x] `services/downloader.py` â€” download async via `httpx` com streaming; calcula progresso
      por `Content-Length`; salva em diretÃ³rio configurÃ¡vel
- [x] `routers/downloads.py` â€” `POST /download` (body: `{url, dest_dir}`): inicia download
      em background task; `GET /downloads/active` fragmento HTMX; `POST /downloads/{id}/cancel`
- [x] `routers/downloads.py` â€” `GET /downloads/progress/{id}` (SSE): emite fragmento HTML
      de progresso a cada 0.6s atÃ© concluir ou falhar
- [x] `routers/downloads.py` â€” `GET /downloads` â€” ativos (polling 3s) + histÃ³rico paginado
- [x] Migration: tabela `downloads` jÃ¡ existia no schema; helpers adicionados em `database.py`
- [x] `templates/downloads.html` + `_downloads_active.html` â€” barras de progresso SSE,
      formulÃ¡rio de novo download, histÃ³rico paginado, botÃ£o cancelar
- [x] BotÃ£o "â†“ baixar" nos cards de resultado de busca `WEB` (HTMX `hx-post="/download"`)

---

### Fase 5 â€” ArquivaÃ§Ã£o Web

> Entrega: salvar qualquer pÃ¡gina como `.md` no formato KOSMOS direto da busca.

- [x] `services/archiver.py` â€” fetch via `httpx`, extraÃ§Ã£o com `trafilatura`; frontmatter
      KOSMOS estendido: `title`, `source`, `date`, `author`, `url` + `language` (auto),
      `word_count` (auto), `tags` (lista), `notes` (texto livre);
      salva em `{archive_path}/Web/{YYYY-MM-DD}_{slug}.md`; slug max 60 chars
- [x] `routers/search.py` â€” `POST /archive` (body form: `url`, `tags?`, `notes?`):
      chama archiver, retorna 200 OK ou 400 se `kosmos_archive` nÃ£o configurado
- [x] BotÃ£o "arquivar" em cada card de resultado `WEB` (HTMX `hx-post`, toast de confirmaÃ§Ã£o)
- [x] Fallback: se `kosmos_archive` nÃ£o configurado, retornar erro 400 com mensagem clara
      orientando a configurar o caminho em `/settings`
- [x] **Melhorar extraÃ§Ã£o de conteÃºdo:** cascata de extratores em `services/archiver.py`;
      HTML baixado uma vez, primeiro a retornar â‰¥ 100 palavras vence; fallback = mais longo.
      Cascata implementada (newspaper4k e readability-lxml bloqueados â€” lxml 5.x nÃ£o compila
      em Python 3.14; lxml 6.x nÃ£o Ã© compatÃ­vel com essas libs):
        1. `newspaper4k`     â€” BLOQUEADO (lxml 5.x / Python 3.14)
        2. `trafilatura`     â€” markdown nativo, instalado âœ“
        3. `readability-lxml`â€” BLOQUEADO (lxml 5.x / Python 3.14)
        4. `inscriptis`      â€” texto estruturado, instalado âœ“
        5. `BeautifulSoup`   â€” fallback html.parser + markdownify, instalado âœ“
        6. `Jina Reader API` â€” fallback remoto: r.jina.ai/{url} se cascata < 100 palavras âœ“

---

### Fase 6 â€” Torrents (busca + qBittorrent)

> Entrega: pesquisar torrents via Prowlarr/Jackett e baixar com qBittorrent diretamente do AKASHA.
> PrÃ©-requisito do usuÃ¡rio: qBittorrent rodando com Web UI ativo (porta 8080);
> Prowlarr (9696) ou Jackett (9117) instalado e com indexadores configurados.

#### 6.1 â€” ConfiguraÃ§Ã£o

- [ ] Adicionar campos na tabela `settings` (migration nova):
      `qbt_host` (default: localhost), `qbt_port` (default: 8080),
      `prowlarr_host`, `prowlarr_port` (9696), `prowlarr_apikey`,
      `jackett_host`, `jackett_port` (9117), `jackett_apikey`
- [ ] Adicionar estes campos Ã  pÃ¡gina `/settings` existente

#### 6.2 â€” Cliente qBittorrent

- [ ] `services/qbt_client.py` â€” usa `httpx` direto (sem dep qbittorrent-api):
      - `_get_session()` â†’ faz POST /auth/login e retorna cookie SID
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
      - Raises `QbtOfflineError(Exception)` se inacessÃ­vel

#### 6.3 â€” Busca de Torrents (Prowlarr + Jackett)

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

#### 6.4 â€” Router

- [ ] `routers/torrents.py`:
      - `GET /torrents` â†’ pÃ¡gina principal (formulÃ¡rio de busca + ativos + histÃ³rico)
      - `GET /torrents/search?q=&cat=` â†’ HTMX fragment com resultados (hx-get polling)
      - `GET /torrents/active` â†’ HTMX fragment: lista de torrents ativos no qBittorrent
        com polling a cada 5s
      - `POST /torrents/add` (form: magnet= ou file=) â†’ adiciona ao qBittorrent
      - `POST /torrents/{hash}/pause`, `/resume`, `/delete`
      - Todos retornam banner gracioso se `QbtOfflineError` ou `TorrentSearchOfflineError`

#### 6.5 â€” Templates

- [ ] `templates/torrents.html` â€” pÃ¡gina principal:
      - FormulÃ¡rio de busca (campo q + select de categoria)
      - Div de resultados: `hx-get="/torrents/search"` com `hx-trigger="submit from:#search-form"`
      - SeÃ§Ã£o "Ativos": `hx-get="/torrents/active" hx-trigger="every 5s"` (polling HTMX)
- [ ] `templates/_torrents_active.html` â€” fragmento: tabela com nome, progresso (barra),
      velocidade, ETA, estado, botÃµes pausa/resume/delete
- [ ] `templates/_torrent_results.html` â€” fragmento: cards de resultado com tÃ­tulo,
      seeders/leechers, tamanho, indexer, botÃ£o "â†“ baixar"

#### 6.6 â€” CSS e nav

- [ ] Adicionar estilos `.torrent-card`, `.torrent-table`, `.seed-count`, `.leech-count`
      a `static/style.css`
- [ ] `_macros.html` WEB cards: nÃ£o adicionar botÃ£o torrent (seria scope creep)

---

### Fase 7 â€” Biblioteca de URLs ~~(CONCEITO ABANDONADO)~~

> ~~Entrega: biblioteca pessoal de sites com scraping periÃ³dico e versionamento por diff.~~
>
> **Conceito original abandonado em 2026-05-05.** O propÃ³sito da Biblioteca Ã© ser um buscador
> pessoal sobre domÃ­nios curados â€” o mesmo objetivo da Fase 10 (crawler BFS). A distinÃ§Ã£o
> entre "URL individual com diff" e "domÃ­nio crawleado" foi descartada: a Fase 10 cobre
> o escopo completo. Os itens abaixo foram marcados como `[x]` incorretamente; na prÃ¡tica
> apenas o schema foi criado e nunca populado. Migration v13 (`database.py`) dropa as
> tabelas orphaned (`library_urls`, `library_diffs`, `library_fts`).

- ~~[x] Migration v5: tabelas `library_urls` / `library_diffs` / `library_fts`~~
  **Nunca populadas. Dropadas pela migration v13.**
- ~~[x] `services/library.py` â€” `add_url()`, `scrape_and_store()`, `check_overdue()`, `compute_diff()`~~
  **Nunca implementado.**
- ~~[x] `routers/library.py` â€” rotas de monitoramento de URLs individuais~~
  **Nunca implementado. As rotas `/library` existentes sÃ£o da Fase 10 (crawler BFS).**
- ~~[x] `templates/library.html` â€” UI de monitoramento com diff e notas~~
  **O template existente Ã© da Fase 10, nÃ£o deste conceito.**
- ~~[x] Background task: re-scrape periÃ³dico de URLs vencidas~~
  **Nunca implementado. O loop horÃ¡rio da Fase 10 cobre re-crawl de domÃ­nios.**
- ~~[x] Busca local inclui `library_fts`~~
  **Removido em 2026-05-05 (dead code â€” tabela nunca populada).**
- ~~[x] BotÃ£o `+` para enfileirar URL na biblioteca~~
  **Reaproveitado na Fase 10 como quick-add de domÃ­nio (`POST /library/add-quick`).**

---

#### Fase 7.5 â€” Lista negra de domÃ­nios

> Entrega: domÃ­nios bloqueados nunca aparecem nos resultados de busca web.

- [x] Migration v6: tabela `blocked_domains` â€” `id, domain, added_at`
- [x] `services/web_search.py` â€” filtrar resultados excluindo domÃ­nios em `blocked_domains`
      (hostname normalizado sem `www.`); aplicado antes de retornar ao router
- [x] BotÃ£o `âˆ’` em cada card de resultado `WEB`: `POST /domains/block`, toast de confirmaÃ§Ã£o
- [x] `routers/domains.py` â€” `POST /domains/block` (extrai domÃ­nio da URL);
      `DELETE /domains/block/{domain}` (desbloquear)
- [x] `templates/domains.html` â€” pÃ¡gina `/domains` dedicada: lista de domÃ­nios bloqueados
      com botÃ£o desbloquear (âœ•) e formulÃ¡rio para adicionar via URL

---

### Fase 8 â€” HistÃ³rico unificado

> Entrega: pÃ¡gina `/history` com timeline de todas as atividades.

- [x] Migration v10: tabela `activity_log` (`id, type, title, url, meta_json, created_at`)
      onde `type` âˆˆ `search|archive|download`
- [x] `routers/history.py` â€” `GET /history?type=all|search|archive|download&page=1`
      paginado por data desc
- [x] `templates/history.html` â€” timeline agrupada por data; Ã­cone por tipo;
      filtros por tipo no topo com HTMX
- [x] Popular `activity_log` nos eventos: `save_search()` e `POST /archive` (sucesso);
      download: pendente atÃ© Fase 11 (downloads ainda nÃ£o implementados)

---

### Fase 9 â€” Polimento e IntegraÃ§Ã£o Final

> Entrega: app production-ready, integrado no ecossistema, lanÃ§Ã¡vel com um comando.

- [ ] `iniciar.sh` â€” versÃ£o final robusta: verificar uv instalado, `uv sync --frozen`
- [ ] Escrever `akasha.exe_path` no `ecosystem.json` no startup para o HUB poder lanÃ§ar
- [ ] `templates/settings.html` â€” pÃ¡gina `/settings`: caminhos do ecossistema (leitura),
      pasta padrÃ£o de download, host/porta qBittorrent, profundidade padrÃ£o de crawl (default: 2)
- [ ] Nav: adicionar aba "Biblioteca", "HistÃ³rico" e "Sites" na topbar
- [ ] `README.md` â€” atualizar seÃ§Ã£o "Estado" para "Implementado â€” Fase 9"

---

### Fase 10 â€” Buscador de Sites Pessoais

> Entrega: motor de busca prÃ³prio sobre domÃ­nios curados. O usuÃ¡rio adiciona sites, o AKASHA
> faz crawling BFS respeitando profundidade, indexa em FTS5 e expÃµe via checkboxes na busca.

### DecisÃµes de design
- **Escopo do crawler**: mesmo domÃ­nio + subdomÃ­nios selecionados pelo usuÃ¡rio
- **Profundidade default**: 2 (configurÃ¡vel em `/settings`)
- **Re-crawl**: manual (botÃ£o) + automÃ¡tico a cada 7 dias (`crawl_pending_sites()` no loop horÃ¡rio)
- **Interface de busca**: checkboxes na barra â€” `â–¡ Web  â–¡ Ecossistema  â–¡ Sites pessoais`
- **Acesso ao conteÃºdo**: apenas via busca (ver Planos Futuros para navegaÃ§Ã£o inline)

> **Nota de implementaÃ§Ã£o (2026-05-06):** os routes foram implementados em `/library` em vez de
> `/sites` como planejado aqui. "Sites" e "Biblioteca" foram unificados numa Ãºnica aba chamada
> Biblioteca (`routers/crawler.py`). O path `/sites` nÃ£o existe no cÃ³digo â€” substituir mentalmente
> por `/library` ao ler os itens abaixo.

### Banco de dados

- [x] Migration v7: tabela `crawl_sites` â€”
      `id, base_url, label, crawl_depth, subdomains_json, page_count,
       last_crawled_at, status (idle|crawling|error), created_at`
- [x] Migration v7: tabela `crawl_pages` â€”
      `id, site_id, url, title, content_md, content_hash, http_status, crawled_at`
- [x] Migration v7: FTS5 `crawl_fts` â€” `(site_id UNINDEXED, url UNINDEXED, title, content_md)`
      sincronizaÃ§Ã£o manual em Python (sem triggers SQL no FTS5)
- [x] `database.py` â€” helpers: `get_all_crawl_sites()`, `get_crawl_site(id)`

### Services

- [x] `services/crawler.py` â€” `extract_links(html, base_url) -> list[str]`:
      extrai links normalizados; descarta Ã¢ncoras, assets, esquemas nÃ£o-http
- [x] `services/crawler.py` â€” `discover_subdomains(base_url) -> list[str]`:
      GET homepage + tenta sitemap.xml; filtra subdomÃ­nios do mesmo domÃ­nio-raiz
- [x] `services/crawler.py` â€” `crawl_site(site_id) -> int`:
      BFS async com httpx; delega extraÃ§Ã£o ao ecosystem_scraper; atualiza crawl_pages + crawl_fts
- [x] `services/crawler.py` â€” `search_sites(query) -> list[SearchResult]`:
      busca FTS5 em crawl_fts; retorna SearchResult com source="SITES"
- [x] `services/crawler.py` â€” `crawl_pending_sites()`:
      crawls sites com last_crawled_at IS NULL; chamado pelo loop horÃ¡rio
- [x] Integrar `crawl_pending_sites()` no loop horÃ¡rio do lifespan (`_monitor_library`)

### Routers

- [x] `routers/crawler.py` â€” `POST /sites/discover` (body: `{url}`):
      chama `discover_subdomains()`, retorna `{base_url, subdomains: list[str]}`
      para o front perguntar quais incluir (resposta HTMX com checkboxes)
- [x] `routers/crawler.py` â€” `POST /sites` (body: `{url, label, crawl_depth, subdomains}`):
      cria entrada em `crawl_sites`, dispara `crawl_site()` em background task
- [x] `routers/crawler.py` â€” `GET /sites` â†’ lista de sites com `page_count`,
      `last_crawled_at`, `status`
- [x] `routers/crawler.py` â€” `DELETE /sites/{id}` â€” remove site e todas as `crawl_pages`
- [x] `routers/crawler.py` â€” `POST /sites/{id}/crawl` â€” re-crawl manual; retorna toast via HTMX

### IntegraÃ§Ã£o com busca

- [x] `routers/search.py` â€” novo source `sites`: busca em `crawl_fts`;
      retorna `list[SearchResult]` com `source="SITES"` e badge dourado
- [x] `templates/search.html` â€” substituir radio de fonte por checkboxes:
      `â–¡ Web  â–¡ Ecossistema  â–¡ Sites pessoais`; persistir escolha em `localStorage`;
      quando "Sites pessoais" marcado e sem sites cadastrados, exibir link para `/sites`
- [x] `templates/search.html` â€” terceira seÃ§Ã£o de resultados "Nos meus sites" quando
      checkbox marcado e hÃ¡ resultados

### Interface de gerenciamento

- [x] `templates/sites.html` â€” lista de sites cadastrados; cada card mostra:
      label, domÃ­nio, contagem de pÃ¡ginas, data do Ãºltimo crawl, badge de status,
      subdomÃ­nios incluÃ­dos; botÃ£o "Re-crawl" e "Remover"
- [x] `templates/sites.html` â€” formulÃ¡rio "Adicionar site": campo URL â†’ botÃ£o "Detectar subdomÃ­nios"
      â†’ HTMX retorna checkboxes dos subdomÃ­nios encontrados â†’ campo profundidade â†’ "Adicionar"
- [x] Nav: aba "Sites" na topbar

---

### Fase 10.5 â€” NavegaÃ§Ã£o inline de pÃ¡ginas crawleadas

> Entrega: reader mode prÃ³prio â€” abrir e ler qualquer `crawl_page` sem sair do AKASHA.

- [x] `database.py` â€” helpers `get_crawl_page_by_url(url) -> tuple | None` e
      `get_crawl_pages_by_site(site_id, limit, offset) -> list[tuple]`
      (retorna `id, url, title, http_status, crawled_at` sem `content_md` para a lista)
- [x] `routers/crawler.py` â€” `GET /library/reader?url=` â€” busca `crawl_page` por URL via
      `get_crawl_page_by_url`, converte `content_md` â†’ HTML com lib `markdown`,
      renderiza `page_reader.html`; 404 se nÃ£o encontrada
- [x] `routers/crawler.py` â€” `GET /library/{site_id}/pages?q=&page=1` â€” lista paginada
      (20/pÃ¡g) de pÃ¡ginas do site; suporte a filtro por `q` (tÃ­tulo/url); retorna fragment
      HTMX `_site_pages.html`
- [x] `templates/page_reader.html` â€” layout reader mode: cabeÃ§alho com tÃ­tulo, URL original
      (link externo â†—), data de crawl, botÃ£o "â† Voltar"; conteÃºdo HTML do markdown com
      tipografia IM Fell English; compatÃ­vel com tema sÃ©pia/noturno
- [x] `templates/_site_pages.html` â€” fragment HTMX: lista de cards de pÃ¡gina (tÃ­tulo, URL
      abreviada, data, badge de status HTTP); botÃ£o "Ler" abre `/library/reader?url=...`;
      paginaÃ§Ã£o "Carregar mais" com `hx-swap="outerHTML"` no load-more li
- [x] `templates/_library_list.html` â€” botÃ£o "ðŸ“„ N pÃ¡ginas" em cada site card que expande
      `_site_pages.html` via HTMX (`htmx.ajax GET /library/{id}/pages`);
      colapsar ao clicar de novo (toggleSitePages em library.html)
- [x] `templates/_macros.html` â€” nos cards de resultado com `source="SITES"`, adicionar
      botÃ£o "Ler" ao lado do link externo que abre `/library/reader?url=...` inline

---

### Fase 11 â€” CorreÃ§Ã£o de bugs e melhorias

> Entrega: app mais rÃ¡pido, sem gargalos de I/O e com SQLite bem configurado.

#### Alta prioridade (impacto imediato visÃ­vel)

- [x] **SQLite WAL mode + pragmas** â€” `database.py`: na funÃ§Ã£o `init_db()`, apÃ³s conectar,
      executar `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`,
      `PRAGMA cache_size=-8000` (8 MB), `PRAGMA mmap_size=67108864` (64 MB).
      WAL elimina lock de leitura durante writes â€” crÃ­tico para crawl + busca simultÃ¢neos.
      Hoje reads e writes se bloqueiam mutuamente porque o modo padrÃ£o Ã© DELETE.

- [x] **Ãndices ausentes** â€” `database.py`: migration v8:
      `CREATE INDEX IF NOT EXISTS idx_crawl_pages_site ON crawl_pages(site_id)` e
      `CREATE INDEX IF NOT EXISTS idx_library_diffs_url ON library_diffs(url_id)`.
      Sem eles, `get_crawl_pages_by_site` e `_recent_diff_ids` fazem full-table scan.

- [x] **Busca paralela** â€” `routers/search.py`: `asyncio.gather()` com filtro
      condicional â€” se `src_web` estÃ¡ off, passa `asyncio.sleep(0, result=[])` no slot.
      Reduz latÃªncia de ~1 s para ~400 ms.

- ~~[x] **`check_overdue` e `list_entries` sem `content_md`** â€” `services/library.py`~~
  **Falso positivo â€” `services/library.py` nunca foi criado (Fase 7 abandonada).**

#### MÃ©dia prioridade (reduz lock contention no crawler)

- [x] **Crawl com conexÃ£o Ãºnica por sessÃ£o** â€” `services/crawler.py`: `crawl_site` agora
      usa 2 conexÃµes (leitura inicial + sessÃ£o BFS completa); `_process_url` captura `db`
      via closure em vez de abrir nova conexÃ£o por pÃ¡gina.

- [x] **FTS skip em conteÃºdo idÃªntico** â€” `services/crawler.py` â†’ `_upsert_page`:
      consulta `content_hash` atual antes do FTS; pula DELETE + INSERT se hash idÃªntico.

- [x] **`asyncio.get_event_loop()` â†’ `asyncio.get_running_loop()`** â€” `routers/crawler.py`
      (3 ocorrÃªncias) e `main.py` (1 ocorrÃªncia).

#### Baixa prioridade (manutenÃ§Ã£o a longo prazo)

- [x] **Limpeza periÃ³dica do search_cache** â€” `main.py` â†’ `_monitor_crawler()`:
      ao acordar, executar `DELETE FROM search_cache WHERE created_at < ?` com cutoff
      de 24 h. Sem essa limpeza o cache cresce indefinidamente â€” cada query Ãºnica
      adiciona uma linha; apÃ³s semanas de uso o arquivo SQLite infla.

- [ ] **Monitor de biblioteca com paralelismo controlado** â€” `main.py` â†’ `_monitor_library()`:
      em vez de re-scrape sequencial das URLs vencidas, usar `asyncio.gather` com
      `asyncio.Semaphore(3)` â€” mÃ¡ximo 3 scrapes simultÃ¢neos. Uma biblioteca com 50+
      URLs vencidas pode travar o event loop por vÃ¡rios minutos em modo sequencial.
      âš  **BLOQUEADO**: depende de `services/library.py` e `routers/library.py` (Fase 7
      marcada como concluÃ­da no TODO mas nunca implementada).

- [x] **DependÃªncia `markdown`** â€” `pyproject.toml`: adicionar `markdown>=3.7`
      (necessÃ¡rio para Fase 10.5 â€” converter `content_md` â†’ HTML no reader mode).
      âš  **ADIADO**: adicionar junto com a implementaÃ§Ã£o da Fase 10.5.

---

### Fase 12 â€” ExtensÃ£o Firefox (Zen Browser)

> Entrega: extensÃ£o Manifest V3 que detecta URLs de vÃ­deo na aba atual e delega o download
> ao Hermes via AKASHA com um clique. Requer Fase 3 do Hermes (mini API HTTP).

#### Estrutura de arquivos
- [ ] `extension/manifest.json` â€” Manifest V3; permissÃµes: `activeTab`,
      `http://localhost:7071/*`; action com Ã­cones active/inactive;
      background service worker; popup declarado
- [ ] `extension/icons/` â€” Ã­cone 16/32/48/128px nos dois estados (active e greyscale)
- [ ] `extension/popup/popup.html` + `popup.css` + `popup.js` â€” UI mÃ­nima:
      URL atual, dois botÃµes: "â¬‡ Baixar vÃ­deo" e "ðŸ“ Transcrever";
      ambos rodam em segundo plano via Hermes; feedback de estado
      (aguardando / na fila / erro Hermes offline / erro AKASHA offline)

#### Background script
- [ ] `extension/background.js` â€” ao mudar de aba ou navegar, verificar se a URL
      pertence a site de vÃ­deo suportado pelo yt-dlp (YouTube, Vimeo, Twitch,
      Twitter/X, TikTok, Reddit, Dailymotion, Bilibili, Niconico, etc.);
      habilitar/desabilitar Ã­cone da action conforme resultado
- [ ] `extension/background.js` â€” ao receber mensagem `{action: "download"|"transcribe", url}`
      do popup, fazer `POST http://localhost:7071/api/hermes/download` com `{url, mode}`;
      retornar `{ok, error?}` ao popup; fechar popup apÃ³s confirmaÃ§Ã£o (roda em bg)

#### Backend AKASHA
- [ ] `routers/hermes_bridge.py` â€” `POST /api/hermes/download`
      (body Pydantic: `url: str`, `mode: Literal["download","transcribe"] = "download"`,
      `format: str | None = None`):
      1. LÃª `hermes.api_port` do ecosystem.json
      2. Tenta `GET /health` no Hermes â€” se falhar (offline):
         a. LÃª `hermes.exe_path` do ecosystem.json
         b. Verifica via `psutil` se processo Hermes estÃ¡ rodando
         c. Se nÃ£o estiver, dispara `subprocess.Popen(exe_path)`
         d. Aguarda `/health` responder com polling (timeout 30s, intervalo 1s)
         e. Se nÃ£o subir no timeout, retorna 503 com mensagem clara
      3. Delega via `httpx.AsyncClient` para `/download` ou `/transcribe`
      Adicionar `psutil` ao `pyproject.toml` se nÃ£o presente
- [ ] Registrar `hermes_bridge` router em `main.py`

#### InstalaÃ§Ã£o (desenvolvimento)
- [ ] `extension/README.md` â€” instruÃ§Ãµes: `about:debugging` â†’ "Este Firefox" â†’
      "Carregar extensÃ£o temporÃ¡ria" â†’ selecionar `extension/manifest.json`

---

#### Fase 12.5 â€” Aba "Ver Mais Tarde"

> Lista interna de URLs para retomar depois, sem arquivar nem monitorar.
> VisÃ­vel apenas no AKASHA â€” nÃ£o indexada no `local_fts` nem exportada para o ecossistema.
> Resultados aparecem na busca global como seÃ§Ã£o separada "Salvo para depois".

#### Banco de dados

- [x] Migration v9: tabela `watch_later` â€”
      `id, url (UNIQUE), title, snippet, notes, added_at`
- [x] Migration v9: FTS5 `watch_later_fts` â€” `(id UNINDEXED, url UNINDEXED, title, notes)`
      sincronizada manualmente nos helpers

#### Backend

- [x] `database.py` â€” helpers: `add_watch_later(url, title, snippet) -> int`;
      `get_all_watch_later() -> list[tuple]`; `delete_watch_later(id) -> None`;
      `search_watch_later(query, limit) -> list[tuple]`
- [x] `services/local_search.py` â€” funÃ§Ã£o `search_watch_later(query, max_results)`
      que consulta `watch_later_fts`; retorna `list[SearchResult]` com `source="DEPOIS"`;
      NÃƒO adiciona ao `local_fts` (nÃ£o visÃ­vel para o ecossistema)
- [x] `routers/watch_later.py` â€” `GET /watch-later` (pÃ¡gina da lista);
      `POST /watch-later/add` (form: url, title?, snippet?; retorna 200);
      `DELETE /watch-later/{id}` (retorna 200)

#### Templates

- [x] `templates/watch_later.html` â€” lista de itens salvos: tÃ­tulo, URL, data,
      campo notes inline editÃ¡vel, botÃ£o "remover"; empty state com hint
- [x] `templates/_macros.html` â€” botÃ£o `â˜† ver depois` (`hx-post="/watch-later/add"`)
      nos cards de resultado `WEB`, junto com os outros botÃµes de aÃ§Ã£o
- [x] `templates/base.html` â€” aba "ver depois" na nav entre "sites" e "downloads"
- [x] `templates/search.html` â€” seÃ§Ã£o "Salvo para depois" (apÃ³s seÃ§Ã£o Sites,
      antes do empty state); aparece sempre que hÃ¡ matches no `watch_later_fts`

#### IntegraÃ§Ã£o com busca

- [x] `routers/search.py` â€” incluir `search_watch_later(q)` no `asyncio.gather`;
      passa `watch_later_results` para o template; seÃ§Ã£o visÃ­vel
      independente dos checkboxes (sempre busca se hÃ¡ query)

#### TODO update

- [x] Atualizar `AKASHA/TODO.md` ao concluir: marcar itens e atualizar data

---

### Fase 13 â€” API de Pesquisa Profunda (integraÃ§Ã£o com Mnemosyne)

> Entrega: endpoint JSON que o Mnemosyne pode chamar para buscar + scraping on-demand,
> permitindo "Modo de Pesquisa Profunda" que combina biblioteca local com conteÃºdo web atual.

#### Novos endpoints

- [x] `GET /search/json?q={query}&sources=web,sites&max={n}` â€” retorna resultados de busca
      como JSON puro (`list[SearchResult]`) em vez de HTML; reutiliza a lÃ³gica de
      `routers/search.py` mas com `Response` JSON; usado pelo Mnemosyne para obter URLs relevantes
      sem scraping ainda

- [x] `POST /fetch` (body: `{url: str, max_words: int = 2000}`) â€” fetch + scraping
      completo de uma URL usando a cascata do `ecosystem_scraper` + fallback Jina Reader;
      retorna `{url, title, content_md, word_count, error?}`; nÃ£o persiste nada â€” resposta
      efÃªmera para uso imediato pelo Mnemosyne; timeout 30s

#### Notas de implementaÃ§Ã£o

- Ambos os endpoints sÃ£o somente-leitura â€” nÃ£o alteram estado do AKASHA
- `GET /search/json` pode ser implementado extraindo a lÃ³gica de busca de `routers/search.py`
  para uma funÃ§Ã£o pura e reutilizando em ambos os handlers (HTML e JSON)
- `POST /fetch` reutiliza `ecosystem_scraper.extract()` + a lÃ³gica de Jina jÃ¡ em `archiver.py`
- LatÃªncia esperada: `/search/json` ~400ms (DDG cache hit) / ~1.5s (miss); `/fetch` ~2â€“8s por URL

---

### Fase 14 â€” IntegraÃ§Ã£o KOSMOS nos cards de resultado

> BotÃ£o nos cards de resultado web para adicionar a URL Ã  lista de fontes do KOSMOS.

- [x] `templates/_macros.html` â€” botÃ£o "K" nos cards `WEB`:
      `hx-post="/kosmos/add-source"` com `{"url": "...", "name": "..."}`;
      usa `detect_feed_type()` do KOSMOS para inferir tipo (youtube/rss/etc.)
- [x] KOSMOS expÃµe `POST /add-source` via `http.server` em thread daemon (porta 8965 por padrÃ£o)
- [x] `routers/kosmos_bridge.py` â€” lÃª porta do ecosystem.json, encaminha para KOSMOS; 503 se KOSMOS offline

---

### Fase 15 â€” Qualidade de Busca e Crawl (pesquisa 2026-04-24)

> Melhorias derivadas de pesquisa sobre arquitetura de buscadores, otimizaÃ§Ã£o de Ã­ndice invertido
> e deduplicaÃ§Ã£o. Organizadas por prioridade.

#### Alta prioridade

- [x] **[A] BM25 com pesos por campo** â€” usar `bm25(crawl_fts, 10, 1)` na consulta FTS5
      para dar peso 10Ã— ao tÃ­tulo vs. corpo; melhora ranking sem custo computacional
      (`database.py` / `services/local_search.py`)

- [x] **[B] NormalizaÃ§Ã£o de URL antes de inserir no crawl** â€” remover parÃ¢metros de tracking
      (`utm_*`, `fbclid`, `ref`, etc.) antes de `INSERT` em `crawl_pages`; evita duplicatas
      por variaÃ§Ã£o de URL (`services/crawler.py` + helper em `database.py`)

- [x] **[C] FTS5 optimize periÃ³dico pÃ³s-crawl** â€” executar
      `INSERT INTO crawl_fts(crawl_fts) VALUES('optimize')` apÃ³s crawls com > 200 pÃ¡ginas
      novas; mescla segmentos fragmentados e mantÃ©m performance de busca estÃ¡vel
      (`services/crawler.py` ou job agendado em `main.py`)

- [x] **[D] Cache de robots.txt por domÃ­nio (TTL 24h)** â€” armazenar regras de robots.txt
      em memÃ³ria por domÃ­nio com expiraÃ§Ã£o de 24h; evita fetch redundante a cada URL
      (`services/crawler.py`)

#### MÃ©dia prioridade

- [x] **[E] Rate limiting por domÃ­nio com fila de prioridade** â€” limitar requisiÃ§Ãµes por
      domÃ­nio (ex: 1 req/s) usando `asyncio.Queue` + semÃ¡foro por host; evita banimento
      e respeita servidores (`services/crawler.py`)

- [x] **[F] SimHash para detecÃ§Ã£o de near-duplicatas** â€” calcular SimHash do conteÃºdo
      extraÃ­do; rejeitar pÃ¡ginas com distÃ¢ncia Hamming < 3 de pÃ¡ginas jÃ¡ indexadas;
      `pip install simhash`; reduz ruÃ­do no Ã­ndice sem hashing exato
      (`services/crawler.py` + `database.py`)

- [x] **[G] Ãndice de prefixo FTS5** â€” adicionar `prefix="2,3"` na criaÃ§Ã£o de `crawl_fts`
      para acelerar buscas com autocompletar e queries de prefixo parcial
      (`database.py` â€” migration necessÃ¡ria)

- [x] **[H] `favor_recall=True` no trafilatura antes do fallback Jina** â€” passar
      `favor_recall=True` no `ecosystem_scraper` / extraÃ§Ã£o local para aumentar cobertura
      de conteÃºdo antes de recorrer ao Jina Reader externo
      (`ecosystem_scraper.py` ou `services/archiver.py`)

#### Baixa prioridade

- [ ] **[I] Campo separado para headings no FTS5** â€” extrair headings (h1â€“h3) do HTML
      e indexar em coluna dedicada com peso ~50Ã—; melhora recall para queries de conceito
      (`database.py` + `services/crawler.py` â€” migration necessÃ¡ria)

- [ ] **[J] Meilisearch como backend alternativo para corpus grande** â€” avaliar substituiÃ§Ã£o
      do FTS5 pelo Meilisearch self-hosted quando o corpus ultrapassar ~100k pÃ¡ginas;
      oferece typo-tolerance, facetas e ranking configurÃ¡vel nativo; requer processo separado

---

### Fase 16 â€” CorreÃ§Ã£o de Bugs (auditoria 2026-04-24)

> Bugs encontrados por inspeÃ§Ã£o de cÃ³digo. Nenhum requer migration de schema.

#### Alta prioridade (funcionalidade quebrada)

- [x] **[BUG-1] `/domains` â€” bloquear/desbloquear nÃ£o atualiza a lista na UI**
      `routers/domains.py` + `templates/domains.html`: os endpoints `POST /domains/block` e
      `DELETE /domains/block/{domain}` retornam `Response(status_code=200)` com body vazio,
      mas o template usa `hx-select="#domains-list"` esperando receber esse elemento na resposta.
      HTMX nÃ£o encontra o seletor â†’ lista nÃ£o atualiza; usuÃ¡ria precisa recarregar a pÃ¡gina.
      **Fix:** retornar a lista atualizada como fragment HTML em ambos os endpoints, ou
      mudar para `hx-get="/domains" hx-trigger="revealed"` como follow-up.

- [x] **[BUG-2] `search.html` â€” link "Adicionar sites" aponta para `/sites` que nÃ£o existe**
      `templates/search.html:18`: `<a href="/sites">Adicionar sites â†’</a>` causa 404.
      O gerenciamento dos sites crawleados estÃ¡ em `/library`.
      **Fix:** corrigir para `href="/library"`.

- [x] **[BUG-3] `crawl_site` â€” status travado em `'crawling'` quando ocorre exceÃ§Ã£o**
      `services/crawler.py`: o status Ã© definido como `'crawling'` antes do BFS, mas sÃ³
      resetado para `'idle'` no final bem-sucedido. Se qualquer exceÃ§Ã£o ocorrer (HTTP, DB,
      timeout), o site fica com `status='crawling'` para sempre. `crawl_pending_sites()`
      filtra por `status='idle'`, logo o site nunca mais Ã© re-crawlado automaticamente.
      **Fix:** envolver o BFS em `try/finally` e garantir `UPDATE status='idle'` no `finally`.

#### MÃ©dia prioridade (inconsistÃªncia / UX)

- [x] **[BUG-4] `main.py` `index()` â€” contexto incompleto para `search.html`**
      `main.py:101`: o handler da rota `/` nÃ£o passa `site_results`, `has_sites` e
      `has_more_web` para o template. O Jinja2 nÃ£o crasha (trata `undefined` como falsy),
      mas o comportamento Ã© inconsistente com o handler `/search`.
      **Fix:** adicionar as chaves faltantes com valores padrÃ£o (`site_results=[]`,
      `has_sites=False`, `has_more_web=False`, `src_web=True`, `src_eco=True`, `src_sites=False`).

- [x] **[BUG-5] `search.html` â€” aviso "nenhum site cadastrado" dentro do bloco `{% if error %}`**
      `templates/search.html`: o bloco `{% if src_sites and not has_sites and query %}` estÃ¡
      aninhado dentro de `{% if error %}`, entÃ£o o aviso sÃ³ aparece quando hÃ¡ erro de busca.
      Deveria aparecer independentemente, como estado informativo separado.
      **Fix:** mover o bloco de aviso para fora do `{% if error %}`, antes ou logo apÃ³s o
      bloco principal de resultados.

- [x] **[BUG-6] `routers/system.py` â€” `/open-file` nunca reporta erro ao abrir arquivo local**
      `subprocess.Popen(["xdg-open", path])` Ã© fire-and-forget: sempre retorna HTTP 200 mesmo
      que o xdg-open falhe silenciosamente (comum no CachyOS/Niri/Wayland quando
      `DBUS_SESSION_BUS_ADDRESS` nÃ£o estÃ¡ disponÃ­vel no processo filho). O toast mostra
      "Abrindo arquivoâ€¦" mesmo que nada abra.
      **Fix:** usar `asyncio.create_subprocess_exec` para capturar o cÃ³digo de retorno;
      tentar `gio open` como fallback se xdg-open falhar; retornar HTTP 500 com mensagem
      legÃ­vel se ambos falharem.

---

### Busca Local AvanÃ§ada â€” PendÃªncias TÃ©cnicas


- [x] Bug: `_search_chroma()` cria novo `PersistentClient` a cada query â€” cachear como singleton:
  **Motivo:** `AKASHA/services/local_search.py` linha ~247 faz
  `client = _chromadb.PersistentClient(path=index_path)` dentro da funÃ§Ã£o de busca.
  Abrir um PersistentClient abre o SQLite subjacente do ChromaDB e carrega metadados â€” custo
  de I/O repetido desnecessariamente a cada busca interativa.
  **ImplementaÃ§Ã£o (`AKASHA/services/local_search.py`):**
  ```python
  _chroma_clients: dict[str, Any] = {}   # module-level cache

  def _get_chroma_client(index_path: str):
      if index_path not in _chroma_clients:
          _chroma_clients[index_path] = _chromadb.PersistentClient(path=index_path)
      return _chroma_clients[index_path]
  ```
  Substituir `client = _chromadb.PersistentClient(path=index_path)` por
  `client = _get_chroma_client(index_path)` em `_search_chroma()`.
  Resultado: latÃªncia de busca local reduzida; sem impacto em corretude.

- [x] AKASHA: substituir `rank_combined()` por Reciprocal Rank Fusion (RRF):
  **Motivo:** `rank_combined()` usa `_score()` â€” contagem simples de keywords nos campos title e
  snippet. Isso descarta os scores de relevÃ¢ncia reais de cada mÃ©todo:
  - FTS5 retorna resultados jÃ¡ ordenados por bm25() (score real de relevÃ¢ncia lexical)
  - ChromaDB retorna resultados ordenados por distÃ¢ncia euclidiana no espaÃ§o de embeddings
  Ignorar essas ordenaÃ§Ãµes e usar contagem de termos Ã© inferior ao RRF, que considera a posiÃ§Ã£o
  relativa de cada resultado em cada lista sem precisar dos scores absolutos.
  A pesquisa confirma: RRF sem parÃ¢metros supera linear combination com alpha tuning manual
  na maioria dos benchmarks (arxiv 2604.01733).
  **ImplementaÃ§Ã£o (`AKASHA/services/local_search.py`):**
  ```python
  def _rrf(rankings: list[list[SearchResult]], k: int = 60) -> list[SearchResult]:
      """Reciprocal Rank Fusion â€” funde mÃºltiplas listas rankeadas."""
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
  `search_local()`. A funÃ§Ã£o `rank_combined()` pode ser mantida como fallback para resultados
  de fontes sem ranking explÃ­cito (web results, etc.).

- [x] AKASHA: FTS5 com tokenizer `unicode61 remove_diacritics=2` para busca acentuada:
  **Motivo:** a tabela `local_fts` usa o tokenizer padrÃ£o do FTS5 (`unicode61`), que por padrÃ£o
  trata "aÃ§aÃ­" diferente de "acai". Com `remove_diacritics=2`, "cafe" encontra "cafÃ©" e
  "musica" encontra "mÃºsica" â€” essencial para corpus em portuguÃªs.
  **ImplementaÃ§Ã£o (`AKASHA/database.py` â€” migration):**
  Recriar a tabela FTS com o tokenizer correto. As migrations existentes jÃ¡ tÃªm padrÃ£o â€” adicionar:
  ```sql
  CREATE VIRTUAL TABLE IF NOT EXISTS local_fts USING fts5(
      path UNINDEXED,
      title,
      body,
      source UNINDEXED,
      tokenize = 'unicode61 remove_diacritics 2'
  );
  ```
  Como Ã© uma virtual table, recriar exige reindexar â€” executar `index_local_files()` no prÃ³ximo startup.

- [x] AKASHA: deduplicaÃ§Ã£o de conteÃºdo crawlado por hash SHA-256:
  **Motivo:** o crawler normaliza URLs mas nÃ£o detecta conteÃºdo duplicado entre URLs diferentes
  (syndication, mirrors, redirects resolvidos). Dois artigos com mesmo conteÃºdo sÃ£o indexados
  e buscados duplicadamente, poluindo os resultados.
  Mesma tÃ©cnica do KOSMOS: SHA-256 do conteÃºdo extraÃ­do como guarda de deduplicaÃ§Ã£o.
  **ImplementaÃ§Ã£o (`AKASHA/services/crawler.py` + `database.py`):**
  1. Adicionar coluna `content_hash TEXT` Ã  tabela que armazena pÃ¡ginas crawladas
  2. Antes de persistir uma pÃ¡gina: calcular `hashlib.sha256(content.encode()).hexdigest()`
  3. `SELECT id FROM crawled_pages WHERE content_hash = ?` â€” se existir: ignorar URL, nÃ£o re-indexar
  4. Adicionar index em `content_hash` para a query ser O(1)

- [x] AKASHA: ETag/Last-Modified no crawler para nÃ£o re-crawlar pÃ¡ginas sem mudanÃ§a:
  **Motivo:** o crawler re-crawla todas as URLs a cada ciclo, mesmo que o conteÃºdo nÃ£o tenha
  mudado. Servidores que suportam cache HTTP retornam 304 Not Modified com ETag/Last-Modified,
  evitando download e parsing do HTML inteiro.
  **ImplementaÃ§Ã£o (`AKASHA/services/crawler.py`):**
  1. Armazenar `etag` e `last_modified` junto a cada URL crawlada na tabela do banco
  2. No re-crawl, passar os headers condicionais:
     ```python
     headers = {}
     if stored_etag:    headers["If-None-Match"]     = stored_etag
     if stored_lm:      headers["If-Modified-Since"] = stored_lm
     resp = await client.get(url, headers=headers)
     if resp.status_code == 304:
         return  # sem mudanÃ§a â€” ignorar
     # senÃ£o: processar normalmente e salvar novos etag/last-modified
     etag = resp.headers.get("ETag")
     lm   = resp.headers.get("Last-Modified")
     ```

- [x] AKASHA: throttle adaptativo no crawler baseado em tempo de resposta do servidor:
  **Motivo:** `_CRAWL_CONCURRENCY = 4` Ã© fixo e nÃ£o reflete a capacidade real do servidor alvo.
  Servidores lentos (resposta > 2s) ficam sobrecarregados; servidores rÃ¡pidos sÃ£o sub-utilizados.
  Scrapy AutoThrottle usa `delay = response_time / target_concurrency` como heurÃ­stica.
  **ImplementaÃ§Ã£o (`AKASHA/services/crawler.py`):**
  1. Medir `response_time` de cada request: `t0 = time.monotonic(); resp = await client.get(url); dt = time.monotonic() - t0`
  2. Manter mÃ©dia mÃ³vel de response_time por domÃ­nio (janela de 5 requests)
  3. Ajustar delay no rate limiter:
     - `dt_avg < 0.5s` â†’ delay mÃ­nimo (0.5s) â€” servidor rÃ¡pido
     - `0.5s â‰¤ dt_avg < 2s` â†’ delay = dt_avg (politeness simples)
     - `dt_avg â‰¥ 2s` â†’ delay = 2Ã— dt_avg, reduzir concorrÃªncia para 2
  4. Em 429 (Too Many Requests): backoff exponencial `2^n Ã— delay_base + jitter`

- [x] AKASHA: Trafilatura como primeiro estÃ¡gio de extraÃ§Ã£o (substituiÃ§Ã£o em ecosystem_scraper.py):
  **Motivo:** idÃªntico ao KOSMOS â€” F1=0.945 do Trafilatura vs F1=0.665 do BeautifulSoup.
  ConteÃºdo mais limpo no Ã­ndice FTS5 do AKASHA = busca mais precisa, menos falsos positivos.
  Ver item equivalente em PENDÃŠNCIAS â€” KOSMOS para implementaÃ§Ã£o detalhada (compartilham
  o `ecosystem_scraper.py`).


---

## KOSMOS â€” Leitor de Feeds

> **PadrÃµes obrigatÃ³rios (toda sessÃ£o de desenvolvimento):**
> - Tipagem completa em todos os parÃ¢metros e retornos
> - Erros nunca engolidos silenciosamente â€” propagar, retornar valor verificÃ¡vel ou dar feedback ao usuÃ¡rio
> - `log.error()` para falhas reais, `log.warning()` sÃ³ para condiÃ§Ãµes esperadas/recuperÃ¡veis
> - Atualizar este arquivo a cada feature implementada ou pedida
> - **Commit git a cada funcionalidade concluÃ­da** â€” mensagem descritiva, nunca acumular para o final

ReferÃªncia de arquitetura: `KOSMOS_DEV_BIBLE_1.txt`

---

### Design Bible v2.0 â€” Audit (2026-04-11)

- [x] Modo noturno migrado para paleta "Atlas AstronÃ´mico Ã  Meia-Noite" em `night.qss`
- [x] `reader_night.css` atualizado para nova paleta (fundo, bordas, `hr::after`)
- [x] `splash_screen.py` â€” cores hardcoded noturnas corrigidas

---

### FASE EXTRA â€” Features de Enriquecimento
> Funcionalidades alÃ©m do escopo original. Implementar sequencialmente.

- [x] Filtros de palavra-chave (blocklist)
- [x] Feeds de busca (Google News RSS por termo)
- [x] Tags manuais nos artigos â€” chips no leitor, CRUD em `feed_manager.py`
- [x] PosiÃ§Ã£o de scroll salva â€” `scroll_pos` via `window.scrollY`, restaurado no `loadFinished`
- [x] Top fontes e tÃ³picos no dashboard â€” painÃ©is com barras proporcionais
- [x] DeduplicaÃ§Ã£o de artigos similares â€” `duplicate_of`, `rapidfuzz` (85%, 48h, entre feeds)
- [x] Highlights e anotaÃ§Ãµes no leitor â€” `highlights` table, JS injection via `_HIGHLIGHT_SETUP_JS`, chips na barra abaixo das tags, anotaÃ§Ãµes via QInputDialog
- [x] TraduÃ§Ã£o inline no leitor â€” `deep-translator` (Google Translate), sem dialog extra, menu de idiomas, "Ver original"
- [x] Scraping multilÃ­ngue â€” fallback BS4 para idiomas sem tokenizador
- [x] Fallback de scraping â€” traduz tÃ­tulo para inglÃªs â†’ busca Google News RSS â†’ tenta scraping do resultado
- [x] Filtro de idioma na view unificada â€” coluna `language` no modelo, detecÃ§Ã£o via `langdetect` no save
- [x] TÃ­tulo do artigo exibido no leitor (webview) e traduzido junto com o corpo
- [x] Label de idioma original â†’ traduzido na barra inferior do leitor
- [x] Auto-salvar artigo ao criar primeiro destaque
- [x] Tratamento de erros: `log.error` para falhas reais, feedback visÃ­vel ao usuÃ¡rio (tag, destaque), tipagem completa nos helpers privados

---

### FASE A â€” Leitor e Arquivo

- [x] NavegaÃ§Ã£o anterior / prÃ³ximo entre artigos
- [x] BotÃ£o "Buscar artigo completo" (com fallback BS4 multilÃ­ngue + fallback por tÃ­tulo)
- [x] PurgaÃ§Ã£o automÃ¡tica de artigos antigos (`purge_old_articles`)
- [x] `saved_view.py` â€” view de artigos salvos/favoritados
- [x] `archive_manager.py` â€” exportar artigo para Markdown em `data/archive/`
- [x] `archive_view.py` â€” browser do arquivo (lista arquivos .md de `data/archive/`)
- [x] ConversÃ£o HTML â†’ Markdown via `html2text`

---

### FASE B â€” Plataformas Adicionais

**Reddit:**
- [ ] `reddit_fetcher.py` â€” wrapper praw 7.x
- [ ] `add_reddit_dialog.py` â€” adicionar subreddit (requer credenciais)
- [ ] ConfiguraÃ§Ãµes â†’ seÃ§Ã£o Reddit (client_id, client_secret, testar conexÃ£o)
- [ ] Mapeamento de posts para schema de artigos (score, num_comments em `extra_json`)

**YouTube:**
- [ ] DetecÃ§Ã£o automÃ¡tica de URL YouTube em `add_feed_dialog.py`
- [ ] ExtraÃ§Ã£o de `channel_id` de URLs `@handle` via requests + BS4
- [ ] Thumbnail de vÃ­deos nos article cards

**Outras plataformas (RSS puro â€” feedparser jÃ¡ funciona, falta detecÃ§Ã£o):**
- [ ] DetecÃ§Ã£o automÃ¡tica: Tumblr, Substack, Mastodon pela URL
- [ ] `feed_type` correto salvo no banco para cada plataforma

---

### FASE C â€” Busca Global

- [x] FTS5 virtual table com triggers de sincronizaÃ§Ã£o (`database.py`)
- [x] `search.py` â€” query FTS5, retorna artigos ranqueados por relevÃ¢ncia
- [x] Barra de busca global `Ctrl+K` (overlay flutuante)
- [x] Resultados com feed de origem e snippet destacado (mark)
- [x] Clicar no resultado abre o leitor
- [x] NavegaÃ§Ã£o por teclado (â†‘â†“ Enter Esc)

---

### FASE D â€” ExportaÃ§Ã£o PDF e EstatÃ­sticas

**ExportaÃ§Ã£o PDF:**
- [ ] `export_pdf.py` â€” WeasyPrint + template sÃ©pia (`export_template.html`)
- [ ] `export_dialog.py` â€” seletor de destino (artigo Ãºnico ou lista de salvos)
- [ ] BotÃ£o "Exportar PDF" na toolbar do leitor

**EstatÃ­sticas:**
- [x] `read_sessions` â€” registrar inÃ­cio/fim de leitura por artigo
- [x] `stats.py` â€” agregaÃ§Ã£o por dia, feed, plataforma, salvos por mÃªs
- [x] `stats_view.py` â€” grÃ¡ficos matplotlib, filtro de perÃ­odo
- [x] BotÃ£o "Stats" na sidebar

---

### FASE E â€” Polimento Final

- [ ] AnimaÃ§Ãµes: fade-in 150ms nos cards, slide 200ms no leitor, expand/collapse 120ms na sidebar
- [ ] Cursor piscante dourado (`#b8860b`) em campos de texto (QTimer 530ms)
- [ ] Cantos dobrados decorativos (SVG 20Ã—20px)
- [ ] Ãcone do app (`.ico` Windows, `.png` Linux)
- [ ] `iniciar.sh` e `iniciar.bat` com setup automÃ¡tico do venv
- [ ] Revisar todos os caminhos com `pathlib.Path` (sem strings hardcoded)
- [ ] Testes em Windows 10 (WeasyPrint + GTK3, QWebEngineView, VC++ Redist)

---

### FASE F â€” IA Local (Ollama)

> IntegraÃ§Ã£o com modelos LLM locais via Ollama (http://localhost:11434).
> Modelos:
> - `qwen2.5:7b` â€” geraÃ§Ã£o de texto: resumo, extraÃ§Ã£o de tags, anÃ¡lise
> - `nomic-embed-text` â€” embeddings semÃ¢nticos: relevÃ¢ncia, busca vetorial, similaridade
>
> Toda feature de IA Ã© opcional e degradada graciosamente se o serviÃ§o nÃ£o estiver disponÃ­vel.
> Implementar sequencialmente â€” infraestrutura primeiro.

**Infraestrutura:**
- [x] `app/core/ai_bridge.py` â€” cliente Ollama: verificar disponibilidade (`/api/tags`), gerar texto (`/api/generate` streaming via `qwen2.5:7b`), gerar embeddings (`/api/embed` via `nomic-embed-text`)
- [x] Migration: colunas `ai_summary TEXT`, `ai_tags TEXT` (JSON), `embedding BLOB` (768 floats Ã— 4 bytes), `ai_relevance REAL` em `articles`
- [x] ConfiguraÃ§Ãµes â†’ seÃ§Ã£o IA: endpoint (padrÃ£o `http://localhost:11434`), modelo de geraÃ§Ã£o, modelo de embeddings, habilitar/desabilitar, botÃ£o "Testar conexÃ£o"

**Resumo de artigos (`qwen2.5:7b`):**
- [x] BotÃ£o "Resumir" na toolbar do leitor â€” aciona `ai_bridge` com o conteÃºdo do artigo
- [x] Painel recolhÃ­vel abaixo da meta bar para exibir o resumo (streaming token a token via sinal PyQt)
- [x] Cache: resumo salvo em `ai_summary`; nÃ£o regenera se jÃ¡ existir (botÃ£o vira "Ver resumo")

**Tags automÃ¡ticas (`qwen2.5:7b`):**
- [x] Ao abrir artigo sem tags, sugerir tags via `format: "json"` do Ollama
- [x] Chips de sugestÃ£o em cor distinta na tags row â€” aceitar clicando, descartar com Ã—

**RelevÃ¢ncia via embeddings (`nomic-embed-text`):**
- [x] Gerar embedding ao salvar/ler artigo em background â€” armazenar em `embedding BLOB`
- [x] Perfil de interesses: mÃ©dia dos embeddings dos artigos lidos/salvos (atualizado incrementalmente)
- [x] Score de relevÃ¢ncia = cosine similarity(embedding do artigo, perfil) â†’ `ai_relevance REAL`
- [x] Badge de relevÃ¢ncia opcional nos article cards (configurÃ¡vel nas Settings)

**Busca semÃ¢ntica (`bge-m3:latest`):**
- [x] Toggle na search overlay para alternar entre FTS5 (palavras-chave) e busca vetorial (semÃ¢ntica)
- [x] Embed a query em tempo real â†’ retorna top-N artigos por cosine similarity

**AnÃ¡lise de viÃ©s polÃ­tico (`qwen2.5:7b`):**
- [ ] Migration: colunas `ai_political_economic REAL` (-1.0 esquerda â†” +1.0 direita) e `ai_political_authority REAL` (-1.0 libertÃ¡rio â†” +1.0 autoritÃ¡rio) em `articles`
- [ ] BotÃ£o "Analisar viÃ©s" no leitor â€” retorna JSON `{economic_axis, authority_axis, confidence, reasoning}`
- [ ] BÃºssola polÃ­tica (widget 2D) no leitor exibindo a posiÃ§Ã£o do artigo
- [ ] AgregaÃ§Ã£o por feed na `sources_view` â€” posiÃ§Ã£o mÃ©dia dos artigos analisados de cada fonte

**DetecÃ§Ã£o de clickbait (`qwen2.5:7b`):**
- [x] Migration: coluna `ai_clickbait REAL` (0.0 sem clickbait â†” 1.0 clickbait puro) em `articles`
- [x] Score gerado pelo `_AnalyzeWorker` ao abrir artigo; salvo em cache
- [x] Badge `âš ` opcional nos article cards quando `ai_clickbait > 0.6` (configurÃ¡vel nas Settings)
- [x] Indicador `âš  clickbait N%` na meta bar do leitor quando > 60%
- [ ] Filtro por score de clickbait na unified feed view

**CitaÃ§Ã£o ABNT + anÃ¡lise 5Ws ao salvar artigo:**
- [x] Painel colapsÃ­vel "CitaÃ§Ã£o & 5Ws" exibido ao salvar artigo (â˜…)
- [x] CitaÃ§Ã£o ABNT gerada dos metadados existentes (autor, tÃ­tulo, feed, data, URL, data de acesso)
- [x] 5Ws (Quem/O quÃª/Quando/Onde/Por quÃª) via `_FiveWsWorker` com `json_format=True`; cache em `ai_5ws TEXT`
- [x] Autor do artigo exibido em destaque na meta bar do leitor (`QLabel#readerAuthor`)

**RefatoraÃ§Ã£o `_AnalyzeWorker` unificado (`qwen2.5:7b`):**
- [x] Substituir `_TagSuggestWorker` + `_FiveWsWorker` por `_AnalyzeWorker` (JSON Ãºnico ao abrir artigo)
- [x] JSON de resposta: `{tags, sentiment, clickbait, five_ws}` â€” um call, quatro campos
- [x] `_SummarizeWorker` mantido separado com streaming (botÃ£o "Resumir", inalterado)
- [x] `save_ai_analysis()` em `feed_manager` persiste tudo em uma transaÃ§Ã£o

**Sentimento e Tom (`qwen2.5:7b`):**
- [x] Migration: coluna `ai_sentiment REAL` (-1.0 negativo â†” +1.0 positivo) em `articles`
- [x] Score gerado pelo `_AnalyzeWorker` ao abrir artigo; salvo em cache
- [x] Borda colorida esquerda nos article cards (verde/vermelho, configurÃ¡vel nas Settings)
- [x] Indicador `â— tom positivo/negativo/neutro` na meta bar do leitor
- [ ] Filtro por tom na unified feed view
- [x] GrÃ¡fico de tendÃªncia de sentimento no `stats_view` (linha colorida por segmento, Ã¡rea preenchida)

**NER â€” ExtraÃ§Ã£o de Entidades (`qwen2.5:7b`):**
- [x] Migration: coluna `ai_entities TEXT` (JSON `{people,orgs,places}`) em `articles`
- [x] Gerado pelo `_AnalyzeWorker` junto com tags/sentiment/clickbait/5ws
- [x] TrÃªs mini-charts no `stats_view`: top pessoas, organizaÃ§Ãµes e lugares do perÃ­odo

**Clustering por tÃ³pico (embeddings):**
- [x] K-means numpy sobre embeddings `nomic-embed-text` (k adaptativo, 5 reinicializaÃ§Ãµes)
- [x] RÃ³tulo por extraÃ§Ã£o de palavras-chave dos tÃ­tulos do cluster (sem LLM adicional)
- [x] Cards de tÃ³picos no `stats_view` (Ãºltimos 90 dias ou perÃ­odo selecionado)
- [x] SeÃ§Ã£o "TÃ³picos em Destaque" no Dashboard â€” atualizada em tempo real via `analysis_done` signal + debounce 8s; tÃ­tulos clicÃ¡veis abrem o leitor

---

---

### FASE G â€” Unificar "Salvo" e "Arquivo" em um Ãºnico conceito: Arquivar

> Objetivo: eliminar o conceito separado de "Salvo" (favorito no banco).
> Clicar em â˜… / "Arquivar" faz as duas coisas de uma vez: marca `is_saved=1`
> no banco E exporta o `.md` em `data/archive/`. Um Ãºnico gesto, um Ãºnico estado.
> A aba "Salvos" vira "Arquivados" e reflete exatamente o que estÃ¡ no sistema de arquivos.

### G.1 â€” Renomear aÃ§Ã£o e botÃ£o no leitor

- [x] `reader_view.py` â€” botÃ£o `_save_btn`: texto muda de "â˜† Salvar" / "â˜… Salvo"
      para "â˜† Arquivar" / "â˜… Arquivado"
- [x] `reader_view.py` â€” `_on_toggle_saved()`: ao marcar como salvo, chamar
      `archive_manager.export_article(article)` junto; ao desmarcar, deletar o `.md`
      correspondente (silenciosamente, com log de erro)
- [x] Remover botÃ£o "Exportar" separado da `_toolbar_row2` (aÃ§Ã£o agora estÃ¡ em Arquivar)

### G.2 â€” Renomear aba e view "Salvos" â†’ "Arquivados"

- [x] `sidebar.py` â€” texto do botÃ£o de navegaÃ§Ã£o: "Salvos" â†’ "Arquivados"
- [x] `saved_view.py` â€” tÃ­tulo e strings internas: "Salvos" â†’ "Arquivados"
- [x] `unified_feed_view.py` â€” sem referÃªncias visÃ­veis ao usuÃ¡rio (verificado)

### G.3 â€” Migrar artigos jÃ¡ salvos (sem .md) ao iniciar

- [x] `main_window.py` â€” `_migrate_saved_to_archive()` no startup: exporta artigos
      com `is_saved=1` que ainda nÃ£o tÃªm `.md` correspondente

### G.4 â€” Ajustar ArchiveView

- [x] `archive_view.py` â€” remover botÃ£o "Exportar artigo atual" Ã³rfÃ£o do header
- [x] `archive_view.py` â€” mensagem de estado vazio atualizada (sem referÃªncia ao botÃ£o Exportar)
- [x] `archive_manager.py` â€” adicionar `get_archive_path()` e `delete_archive()` helpers

---

### FASE H â€” Indicador de Status do Ollama

> Atualmente nÃ£o hÃ¡ feedback visual enquanto o Ollama estÃ¡ conectando/processando â€”
> o usuÃ¡rio nÃ£o sabe se a requisiÃ§Ã£o estÃ¡ pendente antes do streaming comeÃ§ar.

### H.1 â€” Indicador na janela de ConfiguraÃ§Ãµes

- [ ] `settings_dialog.py` â†’ seÃ§Ã£o IA: substituir ou complementar o botÃ£o "Testar conexÃ£o"
      por um label de status persistente que atualiza ao abrir a seÃ§Ã£o:
      `"â— Ollama conectado â€” qwen2.5:7b"` (verde) ou `"â—‹ Ollama offline"` (vermelho)
- [ ] VerificaÃ§Ã£o assÃ­ncrona via `ai_bridge.is_available()` ao exibir a seÃ§Ã£o de IA;
      nÃ£o bloquear a abertura das ConfiguraÃ§Ãµes

### H.2 â€” Spinner antes do streaming do Resumo

- [ ] `reader_view.py` â†’ painel de resumo: exibir `"âŸ³ Aguardando Ollamaâ€¦"` (label + spinner animado)
      entre o clique do botÃ£o "Resumir" e o primeiro token recebido;
      substituÃ­do pelo streaming assim que o primeiro token chega

### H.3 â€” Feedback durante anÃ¡lise em background

- [ ] `reader_view.py` â†’ meta bar: exibir `"âŸ³ analisandoâ€¦"` como placeholder
      na seÃ§Ã£o de tags e/ou 5Ws enquanto `_AnalyzeWorker` estÃ¡ rodando;
      hoje essa seÃ§Ã£o fica vazia e silenciosa atÃ© o resultado chegar
- [ ] Ao tÃ©rmino (sucesso ou erro), substituir pelo resultado ou por mensagem de erro
      discreta (`"IA indisponÃ­vel"`) sem bloquear a leitura

### H.4 â€” Badge de status global (sidebar ou statusbar)

- [ ] Adicionar indicador global discreto (ex: ponto colorido na sidebar ou
      `QStatusBar` no rodapÃ© da janela principal): verde quando Ollama disponÃ­vel,
      cinza quando nÃ£o verificado, vermelho quando offline
- [ ] Polling leve a cada 60s via `QTimer` usando `ai_bridge.is_available()`;
      nenhum retry automÃ¡tico â€” apenas atualiza o indicador

---

### FASE I â€” Idioma de exibiÃ§Ã£o e detecÃ§Ã£o de idioma nos artigos

> Objetivo: o usuÃ¡rio escolhe um idioma de exibiÃ§Ã£o nas ConfiguraÃ§Ãµes e todos
> os tÃ­tulos e manchetes sÃ£o traduzidos automaticamente para esse idioma ao
> serem exibidos. Cada card tambÃ©m indica o idioma original do artigo.
> Usa o mesmo motor de traduÃ§Ã£o jÃ¡ presente (`deep-translator`).

### I.1 â€” Detectar e persistir idioma de cada artigo

- [ ] `models.py` â€” verificar se coluna `language` jÃ¡ existe em `Article`
      (foi adicionada no filtro de idioma da Fase C); se nÃ£o, adicionar migration
- [ ] `feed_manager.py` / `scraper.py` â€” garantir que `language` Ã© detectado via
      `langdetect` no momento do save e persistido; artigos sem idioma ficam como `None`
- [ ] `article_card.py` â€” exibir badge pequeno com o idioma original do artigo
      (ex: `EN`, `PT`, `ES`) na meta row, visÃ­vel em todas as views de lista

### I.2 â€” ConfiguraÃ§Ã£o de idioma de exibiÃ§Ã£o

- [ ] `config.py` â€” adicionar campo `display_language: str = ""` (vazio = sem traduÃ§Ã£o)
- [ ] `settings_view.py` â€” seÃ§Ã£o "Idioma de exibiÃ§Ã£o": QComboBox com idiomas comuns
      (PortuguÃªs, English, EspaÃ±ol, FranÃ§ais, Deutsch, ä¸­æ–‡, â€¦) + opÃ§Ã£o "Original (sem traduÃ§Ã£o)"
- [ ] Ao mudar, salvar em `settings.json` via `_cfg.set("display_language", code)`

### I.3 â€” TraduÃ§Ã£o automÃ¡tica dos tÃ­tulos na exibiÃ§Ã£o

- [ ] `article_card.py` â€” se `display_language` configurado e `article.language != display_language`,
      chamar `deep-translator` para traduzir o tÃ­tulo antes de exibir no card
- [ ] Cache de traduÃ§Ãµes em memÃ³ria (dict `{article_id: translated_title}`) para evitar
      re-traduzir ao rolar a lista; cache descartado ao mudar o idioma de exibiÃ§Ã£o
- [ ] TraduÃ§Ã£o assÃ­ncrona: mostrar tÃ­tulo original enquanto traduz, substituir ao concluir
      (para nÃ£o travar o scroll); usar `QThread` ou `asyncio` conforme o contexto

### I.4 â€” TraduÃ§Ã£o no reader (opcional / fase posterior)

- [ ] BotÃ£o "Traduzir" na toolbar do leitor jÃ¡ existe â€” verificar se usa `display_language`
      como destino automÃ¡tico ao invÃ©s de pedir confirmaÃ§Ã£o; ajustar se necessÃ¡rio

---

### IDEIAS

- [ ] **DetecÃ§Ã£o de evento**: identificar automaticamente que artigos de fontes diferentes cobrem exatamente o mesmo evento do mesmo dia â€” requer clustering temporal + semÃ¢ntico combinados (embeddings por janela de tempo + similaridade de tÃ­tulo/entidades)

---

### FASE Z â€” Futuro

- [ ] Twitter/X quando soluÃ§Ã£o gratuita e estÃ¡vel disponÃ­vel
- [ ] Playwright para scraping de sites com JavaScript pesado
- [ ] Importar/exportar feeds via OPML
- [ ] NotificaÃ§Ãµes nativas (plyer) para feeds prioritÃ¡rios
- [ ] Subreddit multis
- [ ] Mastodon com autenticaÃ§Ã£o
- [ ] Suporte a podcasts (RSS de Ã¡udio com player interno)
- [ ] IntegraÃ§Ã£o com OGMA: salvar artigo diretamente
- [ ] Regras de auto-tag por palavra-chave
- [ ] Modo leitura offline (download antecipado)


---


### VerificaÃ§Ã£o de SincronizaÃ§Ã£o e MarcaÃ§Ã£o de Problemas

- [ ] Verificar se lista de fontes e artigos baixados estÃ¡ sendo salva na pasta compartilhada (Proton Drive)
  â€” confirmar que `archive_path` e `data_path` apontam para `sync_root/kosmos/`

### MarcaÃ§Ã£o de problemas em artigos
- [ ] Criar mecanismo para marcar problemas dentro de um artigo
  â€” tipos: scraping incompleto, paywall, conteÃºdo cortado, outros (campo livre)
  â€” efeito: diminuir ranking de relevÃ¢ncia da fonte automaticamente
  â€” registrar no log para anÃ¡lise futura de possÃ­veis correÃ§Ãµes


### IntegraÃ§Ã£o com LOGOS e Qualidade de IA


- [x] Bug: `generate_stream()` bypassa o LOGOS â€” chamar via `ecosystem_client`:
  **Motivo:** `ai_bridge.py` linha ~162 chama `self._session.post(f"{self._endpoint}/api/generate")`
  diretamente, sem passar por `_request_llm`. Isso significa que leituras de artigo em streaming
  (P1) nÃ£o estÃ£o registradas no LOGOS e nÃ£o interrompem P3. O sistema de prioridades fica cego
  para toda interaÃ§Ã£o do usuÃ¡rio com o reader do KOSMOS.
  **ImplementaÃ§Ã£o (`KOSMOS/app/core/ai_bridge.py`):**
  1. Substituir o bloco `generate_stream()` por uma chamada a `_request_llm(..., stream=True)`
     que jÃ¡ suporta streaming e retorna um generator de tokens
  2. Garantir que o `priority=1` seja passado para leituras interativas (o usuÃ¡rio abriu o artigo)
  3. Testar que o LogosPanel mostra P1 ativo durante leitura de artigo

- [x] Bug: `embed()` bypassa o LOGOS â€” endpoint hardcoded na porta 11434:
  **Motivo:** `ai_bridge.py` linha ~207 chama `self._endpoint` diretamente (porta 11434, nÃ£o 7072).
  O `keep_alive: "0"` que o LOGOS injetaria para P3 nunca Ã© aplicado a embeddings do KOSMOS.
  **ImplementaÃ§Ã£o:**
  1. `AiBridge.__init__()`: usar como padrÃ£o o endpoint do LOGOS (7072) se disponÃ­vel,
     configurado via `ecosystem_client.get_logos_url()` ou variÃ¡vel de ambiente `LOGOS_URL`
  2. Ou: redirecionar os embeddings do KOSMOS via `ecosystem_client.request_embed()` (a criar),
     que jÃ¡ sabe o endpoint correto e injeta headers `X-App: kosmos`

- [x] KOSMOS workers de background: definir prioridade de OS com `os.nice()`:
  **Motivo:** `BackgroundUpdater` e `BackgroundAnalyzer` rodam como QThread com `IdlePriority`,
  mas esse priority afeta apenas o GIL do Python â€” o kernel do OS ainda aloca CPU normalmente.
  Durante atualizaÃ§Ã£o de feeds + prÃ©-anÃ¡lise simultÃ¢neos, o sistema pode ficar lento.
  Mesmo fix do Mnemosyne idle indexer.
  **ImplementaÃ§Ã£o (`KOSMOS/app/core/background_updater.py` e `background_analyzer.py`):**
  No inÃ­cio do mÃ©todo `run()` de cada worker:
  ```python
  import os, sys, ctypes
  if sys.platform != "win32":
      os.nice(15)
  else:
      ctypes.windll.kernel32.SetPriorityClass(
          ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)  # BELOW_NORMAL
  ```

- [x] KOSMOS: deduplicaÃ§Ã£o de artigos RSS por fingerprint de conteÃºdo:
  **Motivo:** 29% de feeds RSS emitem GUIDs duplicados ou incorretos (FeedHash Corpus 2024, 12.7M
  itens). Artigos re-publicados com tÃ­tulo diferente passam pela checagem de GUID. Sem fingerprint
  de conteÃºdo, o KOSMOS armazena e analisa artigos duplicados, desperdiÃ§ando chamadas ao Ollama.
  Fingerprint SHA-256 de (title_norm + date_ISO + url_norm) tem 99.98% de resistÃªncia a colisÃµes.
  Resultado: reduÃ§Ã£o de 92â€“100% em duplicatas ingeridas e 11â€“19% menos CPU em background.
  Fonte: FeedOps Benchmark 2024; postly.ai/rss-feed/filtering-deduplication
  **ImplementaÃ§Ã£o (`KOSMOS/app/core/database.py` + `feed_fetcher.py`):**
  1. Adicionar coluna `content_hash TEXT` Ã  tabela `articles` (migration) â€” pode ser NULL em artigos antigos
  2. Adicionar index: `CREATE INDEX IF NOT EXISTS idx_articles_hash ON articles(content_hash)`
  3. Na inserÃ§Ã£o de novo artigo, calcular:
     ```python
     import hashlib, re
     def _article_fingerprint(title: str, pub_date: str, url: str) -> str:
         norm_title = re.sub(r'\s+', ' ', title.lower().strip())
         norm_url   = url.lower().rstrip('/').split('?')[0]
         raw        = f"{norm_title}|{pub_date[:10]}|{norm_url}"
         return hashlib.sha256(raw.encode()).hexdigest()
     ```
  4. Antes de inserir: `SELECT id FROM articles WHERE content_hash = ?` â€” se existir, ignorar
  5. Para near-duplicatas (mesmo conteÃºdo, URL diferente): adicionar SimHash do body
     (`pip install python-simhash`): armazenar simhash int64, rejeitar se distÃ¢ncia de Hamming < 8

- [ ] KOSMOS: caching ETag/Last-Modified nos feeds RSS:
  **Motivo:** o `FeedFetcher` faz GET incondicional nos feeds a cada ciclo. Servidores RSS que
  suportam cache HTTP retornam 304 Not Modified quando sem novidades, economizando bandwidth e
  parsing. `feedparser` jÃ¡ suporta ETag e Last-Modified nativamente.
  **ImplementaÃ§Ã£o (`KOSMOS/app/core/feed_fetcher.py` e `database.py`):**
  1. Adicionar colunas `etag TEXT` e `last_modified TEXT` Ã  tabela `feeds`
  2. Na busca do feed: `result = feedparser.parse(url, etag=feed.etag, modified=feed.last_modified)`
  3. Se `result.status == 304`: ignorar (sem novidades), retornar imediatamente
  4. SenÃ£o: processar entries normalmente; salvar `result.etag` e `result.modified` no banco

- [ ] KOSMOS: substituir extraÃ§Ã£o de conteÃºdo por Trafilatura na cascade do ecosystem_scraper:
  **Motivo:** Benchmark ScrapingHub (2024): Trafilatura F1=0.945 vs BeautifulSoup F1=0.665.
  A diferenÃ§a de ~28% em F1 significa menos boilerplate (navegaÃ§Ã£o, anÃºncios, rodapÃ©s) no texto
  extraÃ­do. Texto mais limpo = embedding de maior qualidade = anÃ¡lise de IA mais precisa.
  Fonte: trafilatura.readthedocs.io/en/latest/evaluation; github.com/scrapinghub/article-extraction-benchmark
  **ImplementaÃ§Ã£o (`ecosystem_scraper.py` â€” compartilhado com AKASHA):**
  1. Adicionar `trafilatura` Ã s dependÃªncias do `ecosystem_scraper.py` (ou do projeto que o usa)
  2. Na funÃ§Ã£o `extract()`, tentar Trafilatura primeiro antes do readability/bs4:
     ```python
     import trafilatura
     def extract(html: str, url: str = "") -> str:
         # 1. Trafilatura â€” melhor para artigos de notÃ­cia
         text = trafilatura.extract(html, include_comments=False, include_tables=False)
         if text and len(text) > 200:
             return text
         # 2. Fallback: readability â†’ bs4 â†’ html2text (cascade atual)
         ...
     ```
  3. Verificar compatibilidade: Trafilatura Ã© Python puro, sem AVX2, funciona no Windows 10


### Responsividade

### Responsividade â€” KOSMOS

> KOSMOS Ã© PyQt6. Responsividade significa: layouts que escalam ao redimensionar a janela,
> sem elementos que cortam ou somem.

- [ ] **Auditar layout principal (splitter horizontal)**
  â€” O splitter entre sidebar (feeds) e Ã¡rea principal (artigos) deve ter `setMinimumWidth` adequado
  â€” Abaixo de ~900px total: testar se o painel de artigos fica ilegÃ­vel
- [ ] **ArticleCard â€” chips de tags em janela estreita**
  â€” Chips `QLabel#aiTagChip` em `QHBoxLayout` overflow se o card Ã© muito estreito
  â€” Fix: limitar `max-width` do chip e aplicar `setText(elided_text)` usando `fontMetrics().elidedText()`
- [ ] **StatsView â€” grÃ¡ficos matplotlib em janela pequena**
  â€” GrÃ¡ficos ficam ilegÃ­veis em < 600px de largura (labels sobrepostos)
  â€” Fix: `tight_layout()` + `subplots_adjust()`; reduzir tamanho de fonte dos eixos dinamicamente
- [ ] **Testar em janela 800Ã—600 mÃ­nima**

---

---

## Mnemosyne â€” MemÃ³ria e RAG

### PadrÃµes obrigatÃ³rios (nÃ£o negociÃ¡veis)

- **Tratamento de erros com tipagem Ã© prioridade absoluta.**
  Python: nunca `except Exception` sem re-tipar. Retornar `T | None` ou usar exceÃ§Ãµes especÃ­ficas.
  Nenhum item estÃ¡ "pronto" se o caminho de erro nÃ£o for tratado com o mesmo cuidado que o caminho feliz.

- **Manter este TODO atualizado.**
  Acrescentar aqui ANTES de implementar qualquer coisa que nÃ£o conste.
  Marcar como `[x]` imediatamente ao terminar cada item.

- **Commit apÃ³s cada item individual do TODO.**
  Ao marcar um item como `[x]`, fazer commit com mensagem clara.

- **Nunca passar de fase sem aprovaÃ§Ã£o explÃ­cita.**
  Ao terminar todos os itens de uma fase, perguntar antes de comeÃ§ar a prÃ³xima.

---

### Fase 1 â€” Qualidade e robustez

- [x] `core/errors.py` â€” hierarquia de exceÃ§Ãµes tipadas
- [x] `TODO.md` â€” este arquivo criado com todas as fases
- [x] `core/config.py` + `config.json` â€” sistema de configuraÃ§Ã£o (modelos, pasta)
- [x] `core/ollama_client.py` â€” detecÃ§Ã£o dinÃ¢mica de modelos disponÃ­veis no Ollama
- [x] `core/loaders.py` â€” suporte a `.md` + erros tipados (sem `except Exception` genÃ©rico)
- [x] `core/indexer.py` â€” recebe `AppConfig`, erros tipados, `index_single_file()`
- [x] `core/rag.py` â€” recebe `AppConfig`, retorna `AskResult` tipado
- [x] `core/summarizer.py` â€” recebe `AppConfig`, erros tipados
- [x] `core/__init__.py` â€” re-exportar todos os novos tipos
- [x] `gui/workers.py` â€” `OllamaCheckWorker`, `IndexFileWorker`, erros especÃ­ficos
- [x] `gui/main_window.py` â€” seleÃ§Ã£o de modelo, pasta via diÃ¡logo, verificaÃ§Ã£o Ollama
- [x] `requirements.txt` â€” version pinning + dependÃªncias novas (langchain-ollama, rank-bm25)
- [x] `README.md` â€” corrigir modelo (qwen3.5:9b, nÃ£o llama3.2)

### Fase 2 â€” Gerenciamento de Contexto Pessoal (PCM)

- [x] `core/memory.py` â€” `SessionMemory` + `CollectionIndex` *(criado na Fase 1 â€” dependÃªncia de main_window.py)*
- [x] `core/watcher.py` â€” `FolderWatcher` via `QFileSystemWatcher` *(criado na Fase 1 â€” dependÃªncia de main_window.py)*
- [x] `core/tracker.py` â€” rastreamento de hashes SHA-256 para indexaÃ§Ã£o incremental
- [x] `core/rag.py` â€” hybrid retrieval (semÃ¢ntico + BM25 via rank-bm25)
- [x] `gui/main_window.py` â€” expor controle do watcher na UI (Fase 2 refinamentos)
- [x] `core/watcher.py` â€” detectar remoÃ§Ã£o e renomeaÃ§Ã£o de arquivos (emitir signal `file_removed`)
- [x] `gui/main_window.py` â€” integrar `CollectionIndex` na UI: preencher "Ãšltima indexaÃ§Ã£o" e metadata reais no tab Gerenciar
- [x] `gui/main_window.py` â€” retry automÃ¡tico de conexÃ£o ao Ollama sem reiniciar o app
- [x] `core/memory.py` â€” reescrever para arquitetura em camadas: `history.jsonl` (append-only, uma linha JSON por turno) + `memory.json` com seÃ§Ãµes `collection` (instruÃ§Ãµes editÃ¡veis pelo utilizador sobre a pasta) e `session` (factos extraÃ­dos automaticamente pelo LLM); `build_memory_context()` injeta memÃ³ria no prompt RAG; `compact_session_memory()` usa LLM para sintetizar o histÃ³rico em factos compactos
- [x] `core/rag.py` + `gui/workers.py` â€” histÃ³rico de conversa multi-turno: Ãºltimos 5 turnos (cap 6 000 chars) formatados e injetados no prompt; `AskWorker` acumula `chat_history`; botÃ£o "Nova Conversa" na aba Perguntar reseta histÃ³rico e `SessionMemory`
- [x] `core/loaders.py` â€” suporte a `.epub`: `_load_epub()` com `ebooklib` + `BeautifulSoup`/`lxml`; 1 `Document` por capÃ­tulo com metadata `title`, `author`, `chapter`; ignorar itens com menos de 100 chars (capa, Ã­ndice); atualizar `requirements.txt`
- [x] `core/ollama_client.py` â€” validar existÃªncia do modelo escolhido antes de lanÃ§ar qualquer worker; aviso especÃ­fico com nome do modelo em falta em vez de falha silenciosa 10 segundos depois
- [x] `gui/main_window.py` â€” badge de pendentes: "X novos / X modificados por indexar" (dourado) ou "âœ“ Ã­ndice actualizado" (verde); actualizar no arranque, apÃ³s indexaÃ§Ã£o e ao mudar de pasta
- [x] `gui/main_window.py` â€” indicador de progresso por ficheiro na status bar durante indexaÃ§Ã£o (`IndexWorker` emite `Signal(str)` com nome e posiÃ§Ã£o actual, ex: "Indexando cap3.epubâ€¦ (3/12)")
- [x] **Suporte bÃ¡sico ao vault do Obsidian** *(fundaÃ§Ã£o para Fase 6)* â€” vectorstore Ãºnico com metadata `source_type: "biblioteca" | "vault"`
  - `config.json`: campo `vault_dir` opcional
  - `core/loaders.py`: adicionar `source_type` ao metadata de cada chunk
  - `core/indexer.py`: aceitar mÃºltiplas fontes com tipos distintos, watchers independentes
  - `core/rag.py`: parÃ¢metro de filtro por `source_type` via ChromaDB `where`
  - `gui/main_window.py`: segundo picker de pasta na SetupDialog + seletor "Buscar em: Biblioteca / Vault / Ambos"

### Fase 3 â€” Features core

- [x] `core/indexer.py` â€” `update_vectorstore()` incremental completo usando tracker
- [x] `core/indexer.py` â€” remover chunks de arquivos deletados ou renomeados ao atualizar vectorstore (depende de tracker + signal `file_removed`); usar `collection.delete(where={"source": filepath})` via metadata filter â€” **atenÃ§Ã£o:** `_collection` Ã© atributo privado do ChromaDB, verificar compatibilidade a cada atualizaÃ§Ã£o do pacote
- [x] `core/indexer.py` â€” tratar arquivos **modificados** no `update_vectorstore()`: remover chunks antigos do arquivo com `collection.delete(where={"source": filepath})` + re-adicionar chunks novos (evita duplicatas no vectorstore ao re-indexar)
- [x] `gui/main_window.py` â€” botÃ£o "Atualizar Ã­ndice" (incremental) no tab Gerenciar
- [x] `core/summarizer.py` â€” Map-Reduce: modo "stuff" para corpora <12k chars; modo Map-Reduce para corpora grandes (fase Map: resumo por documento; fase Reduce: resumo final combinado); implementar via LCEL puro (langchain 1.x nÃ£o tem `load_summarize_chain`)
- [x] `core/rag.py` â€” compressÃ£o contextual: apÃ³s retrieval, filtrar cada chunk com LLM antes de enviar ao modelo principal (reduz alucinaÃ§Ãµes 20â€“30%); k aumentado de 4 para 6 (mais candidatos); fallback para chunks originais se todos forem descartados
- [x] `core/rag.py` â€” Multi-Query Retrieval: reformular a pergunta em 3 variaÃ§Ãµes antes do retrieval e deduplicar resultados por `page_content`; melhora recall para perguntas vagas (+1 LLM call leve)
- [x] `core/rag.py` â€” HyDE (Hypothetical Document Embeddings): gerar resposta hipotÃ©tica Ã  pergunta e embeddÃ¡-la em vez da pergunta original; eficaz para perguntas abstractas ("qual a visÃ£o de X sobre Y?"); alternativa ao Multi-Query
- [x] `gui/main_window.py` â€” compactaÃ§Ã£o automÃ¡tica ao fechar: `closeEvent` â†’ diÃ¡logo "Guardar esta conversa na memÃ³ria?" â†’ `CompactMemoryWorker`; elimina necessidade de compactar manualmente (depende do `memory.py` reescrito)
- [x] `core/tracker.py` â€” metadados de relevÃ¢ncia por documento: `score_avg` (score mÃ©dio de similaridade nas Ãºltimas N consultas) e `last_retrieved_at` (timestamp da Ãºltima vez que foi retornado como fonte)
- [x] `core/rag.py` â€” time-decay de relevÃ¢ncia: penalizar documentos com `last_retrieved_at` muito antigo no ranking final; parÃ¢metro `relevance_decay_days` configurÃ¡vel em `AppConfig`

### Fase 4 â€” Inspirado no NotebookLM

### 4.0 PrÃ©-requisito arquitectural
- [x] `core/rag.py` + `gui/workers.py` â€” migrar de `OllamaLLM` para `ChatOllama` com roles separados:
  - Persona do Mnemosyne fixa no `SystemMessage`; contexto RAG + pergunta no `HumanMessage`
  - Resolve "persona drift": em modelos 7B-14B, o contexto RAG pode empurrar a persona para fora da janela de atenÃ§Ã£o, causando respostas genÃ©ricas a partir da 4Âª-5Âª pergunta
  - Implementar dicionÃ¡rio `PERSONAS` em `core/rag.py` com chaves por modo (`"curador"`, `"socrÃ¡tico"`, `"resumido"`, `"comparaÃ§Ã£o"`, `"podcaster"`, `"crÃ­tico"`) â€” torna a Fase 4.6 trivial
  - **AtenÃ§Ã£o:** com `ChatOllama`, o `chunk` em `llm.stream()` Ã© `AIMessageChunk`; usar `chunk.content` nos workers em vez de `chunk` directamente; adicionar guard `if chunk.content:` pois chunks de metadata chegam com `content=""` e causam emissÃ£o de string vazia
  - Prerequisito para 4.6

### 4.1 CitaÃ§Ã£o aprimorada
- [x] `core/rag.py` â€” retornar trecho exato do chunk junto com o nome do arquivo (nÃ£o sÃ³ o path)
- [x] `gui/main_window.py` â€” exibir fontes com trecho visÃ­vel, nÃ£o sÃ³ nome do arquivo
- [x] `gui/main_window.py` â€” indicador de relevÃ¢ncia por fonte (similaridade do chunk)

### 4.2 SeleÃ§Ã£o de fontes por consulta
- [x] `gui/main_window.py` â€” listar arquivos indexados com checkboxes; query respeita seleÃ§Ã£o
- [x] `core/rag.py` â€” suporte a filtro por lista de arquivos via ChromaDB `where` metadata

### 4.3 Notebook Guide automÃ¡tico
- [x] `core/guide.py` â€” ao terminar indexaÃ§Ã£o, gerar automaticamente:
  - Resumo geral da coleÃ§Ã£o
  - 5 perguntas sugeridas sobre o conteÃºdo
- [x] `core/guide.py` â€” modo "PÃ©rolas Escondidas": identificar os 3 fatos mais surpreendentes ou contraintuitivos dos documentos, com citaÃ§Ã£o directa do texto como evidÃªncia
- [x] `gui/main_window.py` â€” exibir Guide na aba Resumir ou em painel lateral

### 4.4 FAQ Generator
- [x] `core/faq.py` â€” gerar lista de perguntas frequentes a partir dos documentos indexados
- [x] `gui/workers.py` â€” FaqWorker com streaming token a token
- [x] `gui/main_window.py` â€” botÃ£o "Gerar FAQ" na aba Resumir

### 4.5 Flashcards, Quiz e Estudo
- [ ] `core/flashcards.py` â€” extrair termos-chave, datas e conceitos e formatar como flashcards (frente/verso)
- [ ] `core/quiz.py` â€” gerar perguntas de mÃºltipla escolha com gabarito a partir dos documentos
- [ ] `core/study_plan.py` â€” Roteiro de Estudos: gerar plano de aprendizado em 3 fases (BÃ¡sico / IntermediÃ¡rio / AvanÃ§ado) com conceitos-chave por fase e ordem lÃ³gica de estudo
- [ ] `gui/main_window.py` â€” nova aba "Estudar" com modo Flashcard, modo Quiz e modo Roteiro

### 4.6 Modos de consulta configurÃ¡veis
- [x] `core/rag.py` â€” 6 personas via `PERSONAS` dict + `SystemMessage` separado do contexto RAG: `curador` (padrÃ£o), `socrÃ¡tico`, `resumido`, `comparaÃ§Ã£o`, `podcaster`, `crÃ­tico`
- [x] `gui/main_window.py` â€” `QComboBox` "Modo:" na aba Chat com tooltip descritivo; valor mapeado para `AskWorker(persona=...)`

### 4.7 Timeline automÃ¡tica
- [ ] *(movido para 4.9 Studio Panel â€” tipo "Linha do Tempo")*

### 4.8 Audio Overview
- [ ] `core/podcast.py` â€” Script de Podcast: gerar diÃ¡logo escrito entre dois "hosts" cobrindo os temas principais dos documentos; implementÃ¡vel sem TTS como passo intermÃ©dio
- [ ] `gui/main_window.py` â€” botÃ£o "Gerar Script de Podcast" na aba Resumir (exporta como `.md` ou `.txt`)
- [ ] Pesquisar opÃ§Ãµes de TTS offline (ex: Kokoro, Piper TTS) para converter script em Ã¡udio
- [ ] `core/audio.py` â€” gerar Ã¡udio a partir do script via TTS local (depende do item anterior)
- [ ] `gui/main_window.py` â€” botÃ£o "Ouvir resumo" com player embutido

### 4.9 Studio Panel â€” GeraÃ§Ã£o de Documentos

> **Conceito:** Um painel Ãºnico na aba AnÃ¡lise onde a usuÃ¡ria escolhe o *tipo de documento* a gerar e clica em "Gerar". Equivalente ao Studio Panel do NotebookLM. Cada tipo tem seu prÃ³prio `core/*.py` mas todos passam pelo mesmo ponto de entrada na UI.
>
> **JÃ¡ implementado (nÃ£o entram no Studio Panel, sÃ£o automÃ¡ticos):**
> - `SummarizeWorker` â†’ resumo geral (aba Resumir)
> - `FaqWorker` â†’ FAQ (aba Resumir â€” seÃ§Ã£o 4.4)
> - `GuideWorker` â†’ Notebook Guide automÃ¡tico pÃ³s-indexaÃ§Ã£o (resumo + perguntas sugeridas, gerado internamente)

#### UI do Studio Panel
- [x] `gui/main_window.py` â€” pill "Studio" na aba AnÃ¡lise; `QComboBox` com 9 tipos; botÃ£o "Gerar" (`sendBtn`); `QTextEdit` read-only com streaming; botÃ£o "Exportar .md" com `QFileDialog`; `StudioWorker` em `workers.py` com dispatcher por tipo via lazy import

#### Briefing Document
- [x] `core/briefing.py` â€” `iter_briefing()`: stuff (<12k chars) ou map-reduce; 4 seÃ§Ãµes fixas: Temas Principais, Achados, Insights AcionÃ¡veis, DivergÃªncias e LimitaÃ§Ãµes; `BriefingError` adicionado a `errors.py`
- [x] Integrar no Studio Panel como tipo `"Briefing"` â€” via `_STUDIO_DISPATCH` em workers.py

#### RelatÃ³rio de Pesquisa Completo
- [x] `core/report.py` â€” `iter_report()`: stuff (<10k chars) ou map-reduce; fase Map extrai temas/args/dados por fonte; fase Reduce gera 6 seÃ§Ãµes fixas em Markdown: SumÃ¡rio Executivo, Temas e Findings, AnÃ¡lise por Fonte, ConvergÃªncias/DivergÃªncias, Lacunas, ReferÃªncias; `ReportError` definido no prÃ³prio mÃ³dulo
- [x] Integrar no Studio Panel como tipo `"RelatÃ³rio"` â€” via `_STUDIO_DISPATCH`
- [ ] Export PDF via `weasyprint` (pesquisar viabilidade â€” baixa prioridade)

#### Study Guide Estruturado
- [x] `core/study_guide.py` â€” `iter_study_guide()`: 4 seÃ§Ãµes â€” Conceitos-Chave (definiÃ§Ã£o 2-3 frases), Termos TÃ©cnicos (glossÃ¡rio), QuestÃµes de RevisÃ£o (8-12 perguntas abertas), TÃ³picos para Aprofundar; stuff ou map-reduce
- [x] Integrar no Studio Panel como tipo `"Guia de Estudo"` â€” via `_STUDIO_DISPATCH`

#### Table of Contents
- [x] `core/toc.py` â€” `iter_toc()`: fase Map lista temas por fonte; fase Reduce consolida em hierarquia `## Tema > - Subtema > - TÃ³pico` com mÃ¡ximo 8 temas principais; stuff ou map-reduce
- [x] Integrar no Studio Panel como tipo `"Ãndice de Temas"` â€” via `_STUDIO_DISPATCH`

#### Timeline
- [x] `core/timeline.py` â€” `iter_timeline()`: fase Map extrai eventos datados por fonte; fase Reduce consolida e ordena cronologicamente; formato `- **[data]** â€” [evento]`; query de retrieval favorece docs com datas; temperatura 0.0 para precisÃ£o factual
- [x] Integrar no Studio Panel como tipo `"Linha do Tempo"` â€” via `_STUDIO_DISPATCH`

#### Blog Post
- [x] `core/blogpost.py` â€” `iter_blogpost()`: temperatura 0.5 para escrita criativa; fase Map extrai pontos interessantes e exemplos; fase Reduce gera texto corrido com tÃ­tulo criativo, introduÃ§Ã£o, 3-5 parÃ¡grafos de desenvolvimento e conclusÃ£o â€” sem bullet points
- [x] Integrar no Studio Panel como tipo `"Blog Post"` â€” via `_STUDIO_DISPATCH`

#### Mind Map
- [x] `core/mindmap.py` â€” `iter_mindmap()`: fase Map extrai hierarquia por fonte; fase Reduce gera bloco `\`\`\`mermaid mindmap\`\`\`` com `root((Tema))`, mÃ¡ximo 6 ramos, 3-4 subtÃ³picos; pronto para Obsidian/GitHub/VS Code
- [x] Integrar no Studio Panel como tipo `"Mind Map"` â€” via `_STUDIO_DISPATCH`; export via botÃ£o "Exportar .md" jÃ¡ existente
- [ ] `requirements.txt` â€” avaliar `graphviz` para SVG embutido no Qt (baixa prioridade)

#### Data Tables
- [x] `core/tables.py` â€” `iter_tables(schema=...)`: sempre map-reduce para cobertura completa; fase Map extrai entidades por fonte conforme schema livre; fase Reduce consolida em tabela Markdown `| col | col |`; temperatura 0.0 para precisÃ£o; `schema` passado como kwarg pelo StudioWorker
- [x] Integrar no Studio Panel como tipo `"Tabela de Dados"` â€” campo de schema visÃ­vel sÃ³ neste tipo; `QTableWidget` com headers dinÃ¢micos; parser de tabela Markdown; botÃ£o "Exportar CSV" via `csv.writer`

#### Slide Deck (baixa prioridade)
- [x] `core/slides.py` â€” `iter_slides()`: slides separados por `---`, tÃ­tulo `#`, conteÃºdo `##` + bullet points; 6-10 slides; compatÃ­vel com Marp/reveal.js; stuff ou map-reduce
- [x] Integrar no Studio Panel como tipo `"Slides"` â€” via `_STUDIO_DISPATCH`

### Fase 5 â€” UI e design

- [x] `gui/styles.qss` â€” fontes do ecossistema (IM Fell English, Special Elite, Courier Prime)
- [x] `gui/styles.qss` â€” visual rico: inputs estilo ficha de biblioteca, cards de resultado
- [x] `gui/styles.qss` â€” Design Bible v2.0: paleta "Papel ao Sol da ManhÃ£", border-radius 2px, botÃµes/tabs/scrollbars completos
- [x] `gui/main_window.py` â€” remover hardcodes de cor legados; objectNames para ollamaBanner, folderLabel, cancelBtn, similarLabel; cores dinÃ¢micas de badge/watcher mapeadas para o ecossistema

### Fase 6 â€” ColeÃ§Ãµes Duais: Segunda MemÃ³ria & Arquivo

> **PrincÃ­pio central:** Obsidian Ã© uma extensÃ£o do teu prÃ³prio cÃ©rebro â€” notas pessoais, pensamentos em evoluÃ§Ã£o, conhecimento construÃ­do por ti. A Biblioteca Ã© um arquivo de vozes externas â€” textos escritos por mÃºltiplas pessoas, com perspectivas possivelmente contraditÃ³rias. Esta distinÃ§Ã£o muda a *relaÃ§Ã£o epistÃ©mica* com o conteÃºdo e, portanto, o comportamento do Mnemosyne.

### Arquitetura de ColeÃ§Ãµes
- [x] `core/collections.py` â€” `CollectionType` (enum: `VAULT` | `LIBRARY`), `CollectionConfig` (dataclass: `name`, `path`, `type`, `enabled`, `source`, `ecosystem_key`); `sync_ecosystem_collections()`, `available_ecosystem_paths()`; migraÃ§Ã£o automÃ¡tica do formato legado `{watched_dir, vault_dir}`
- [x] `core/errors.py` â€” exceÃ§Ãµes novas: `CollectionNotFoundError`, `ObsidianVaultError`, `FrontmatterParseError`

### Vault Obsidian (Segunda MemÃ³ria)
- [x] `core/loaders.py` â€” loader Obsidian completo: `python-frontmatter` para YAML; metadata por nota: `title`, `tags`, `aliases`, `wikilinks`; regex cobre 4 formatos de wikilink; ignorar `.obsidian/`, `templates/`, `attachments/`, `.trash/`; notas com menos de 50 chars de corpo ignoradas
- [x] `core/loaders.py` â€” chunking por cabeÃ§alho `##` para notas `.md`: `_split_by_heading()` â€” 1 nota = 1 ou N chunks por secÃ§Ã£o
- [x] `core/rag.py` â€” seguimento de wiki-links: `_follow_wikilinks()` lÃª notas ligadas e injeta primeiros 300 chars como contexto secundÃ¡rio no prompt
- [x] `core/rag.py` â€” prompt do Vault: `PERSONAS_VAULT` com tom introspectivo â€” "Nas tuas notas sobre X, escreveste queâ€¦"; cita tÃ­tulo da nota, nÃ£o o caminho
- [x] `core/memory.py` â€” secÃ§Ã£o `collection` do Vault descreve o *teu estilo de pensar* (temas recorrentes, forma de estruturar ideias, lÃ­ngua preferida para reflectir), diferente da Biblioteca que descreve domÃ­nio de conhecimento externo

### Biblioteca (Arquivo de Vozes Externas)
- [x] `core/rag.py` â€” prompt da Biblioteca: `PERSONAS` com tom acadÃ©mico â€” "Em *[TÃ­tulo]* de [Autor], encontra-se queâ€¦"; se autores divergirem, apresentar perspectivas em confronto
- [x] `core/loaders.py` â€” garantir metadata `author` e `title` em todos os loaders (PDF, EPUB, DOCX)

### IntegraÃ§Ã£o automÃ¡tica do ecossistema
- [x] `core/collections.py` â€” `ECOSYSTEM_SOURCES` define KOSMOS, AKASHA e Hermes (AETHER excluÃ­do); `sync_ecosystem_collections()` lÃª `ecosystem.json` automaticamente a cada `load_config()`
- [x] `gui/main_window.py` â€” `SetupDialog` com toggles (checkboxes) por fonte detectada em vez do antigo botÃ£o "SugestÃµes do ecossistema"
- [x] `core/config.py` â€” `ecosystem_enabled: dict[str, bool]` persiste estado ligado/desligado por fonte; `_migrate_legacy()` converte formato antigo para coleÃ§Ãµes

### Interface de GestÃ£o de ColeÃ§Ãµes
- [x] `gui/main_window.py` â€” selector de coleÃ§Ã£o na sidebar: `QComboBox` com Ã­cone de tipo (`ðŸ”® VAULT` / `ðŸ“š BIBLIOTECA`); trocar de coleÃ§Ã£o carrega vectorstore + memÃ³ria + reseta `chat_history`
- [x] `gui/main_window.py` â€” diÃ¡logo "Nova ColeÃ§Ã£o": campos nome, caminho (com botÃ£o "â€¦"), tipo (radio Vault/Biblioteca); auto-detectar pasta `.obsidian/` e prÃ©-selecionar tipo
- [x] `gui/main_window.py` â€” aba ColeÃ§Ãµes no tab Gerenciar: lista com nome, tipo, caminho e estado do Ã­ndice; botÃµes editar/remover/indexar agora

---

### Redesign de Interface

- [x] **ReformulaÃ§Ã£o completa da UI** (aprovada) â€” sidebar + painel principal; sem abas; modo escuro (#12161E); fontes do ecossistema aplicadas; design system consistente com DESIGN_BIBLE.txt
- [x] **Ajuste de legibilidade** â€” fontes aumentadas conforme Design Bible: corpo 13px, inputs/answerText IM Fell English 14â€“15px, sidebarBrand 24px, letter-spacing corrigido nos labels e botÃµes
- [x] **Toggle dia/noite** â€” botÃ£o "â˜€ Modo Dia / â˜½ Modo Noite" na sidebar inferior; `styles_light.qss` criado com paleta "Papel ao Sol da ManhÃ£"; `dark_mode` persistido em config

### Barra de progresso e alinhamento visual com o ecossistema

> O Mnemosyne foi feito em PySide6 em vez de PyQt6 (como KOSMOS e Hermes), e usa `styles.qss` prÃ³prio em vez do `ecosystem_qt.py`. A diferenÃ§a visual percebida vem principalmente de: (1) o `.qss` do Mnemosyne nÃ£o partilha o sistema de tokens do `ecosystem_qt.py`; (2) a barra de progresso e os feedbacks de indexaÃ§Ã£o estÃ£o escondidos na barra inferior da janela (statusBar), que trunca nomes de arquivo longos e nÃ£o tem indicador visual de avanÃ§o real.

- [x] **Barra de progresso durante indexaÃ§Ã£o** â€” substituir a statusBar por um widget dedicado na sidebar: `QProgressBar` com valor real (x/y arquivos), nome do arquivo atual numa linha acima (com elide no meio para nÃ£o cortar o nome), e botÃ£o "Interromper" visÃ­vel ao lado â€” tudo visÃ­vel sem depender da barra inferior
- [x] **Redesign completo da UI para paridade com o ecossistema** â€” migrar `styles.qss` do Mnemosyne para usar os mesmos tokens de cor do `ecosystem_qt.py` (`build_qss()`), adaptado para PySide6; aplicar as mesmas fontes, espaÃ§amentos e padrÃµes visuais dos outros apps; resultado: Mnemosyne visualmente consistente com KOSMOS/Hermes mesmo sendo PySide6 em vez de PyQt6

### SessÃµes de Chat Nomeadas

> Contexto: hoje existe apenas um Ãºnico chat ativo por vez (`history.jsonl`). NÃ£o hÃ¡ como nomear, salvar ou retomar conversas anteriores.

- [x] `core/memory.py` â€” adicionar conceito de `Session`: cada sessÃ£o tem id Ãºnico (uuid4 curto), tÃ­tulo editÃ¡vel, timestamp de criaÃ§Ã£o/Ãºltima atividade; `history.jsonl` passa a ser `sessions/{id}.jsonl`
- [x] `core/memory.py` â€” `list_sessions()` retorna sessÃµes ordenadas por Ãºltima atividade; `load_session(id)`, `new_session()`, `delete_session(id)`
- [x] `gui/main_window.py` â€” painel de sessÃµes na sidebar: lista de conversas anteriores com tÃ­tulo e data; clique carrega sessÃ£o; botÃ£o "+" cria nova; botÃ£o lixeira apaga
- [x] `gui/main_window.py` â€” auto-tÃ­tulo da sessÃ£o: usa a primeira pergunta como tÃ­tulo provisÃ³rio (truncado a 60 chars); editÃ¡vel via duplo-clique na sidebar

---

---

### Fase 7 â€” Modo de Pesquisa Profunda (integraÃ§Ã£o com AKASHA)

> Combina a biblioteca local do Mnemosyne com conteÃºdo web buscado em tempo real pelo AKASHA.
> Requer que o AKASHA esteja rodando na porta 7071 (Fase 13 do AKASHA: `/search/json` e `/fetch`).
> DegradaÃ§Ã£o graciosa: se AKASHA offline, botÃ£o oculto e aviso ao usuÃ¡rio.

### AkashaClient

- [x] `core/akasha_client.py` â€” cliente httpx para a API REST do AKASHA:
      `search(query, max_results) -> list[AkashaResult]` â€” chama `GET /search/json`;
      `fetch(url) -> FetchResult` â€” chama `POST /fetch`;
      `is_available() -> bool` â€” `GET /health` com timeout 2s;
      tipos: `AkashaResult(url, title, snippet)`, `FetchResult(url, title, content_md, word_count)`;
      erros especÃ­ficos: `AkashaOfflineError`, `AkashaFetchError`

### SessionIndexer

- [x] `core/session_indexer.py` â€” indexaÃ§Ã£o temporÃ¡ria em memÃ³ria para a sessÃ£o de pesquisa:
      usa `chromadb.EphemeralClient()` (sem persistÃªncia em disco);
      `add_pages(pages: list[FetchResult]) -> None` â€” chunka com `RecursiveCharacterTextSplitter`
      e embeda via Ollama; `search(query, k=5) -> list[Document]`; `clear() -> None`;
      limite de RAM: mÃ¡x 10 pÃ¡ginas por sessÃ£o (configuraÂ­vel); estimativa ~50-100MB por sessÃ£o

### DeepResearchWorker

- [x] `gui/workers.py` â€” `DeepResearchWorker(QThread)`:
      sinal `status(str)` para feedback incremental ("Buscando no AKASHAâ€¦", "Carregando 3/5â€¦", etc.);
      sinal `finished(bool, str, list)` â€” sucesso, resposta RAG, fontes (local + web);
      pipeline:
        1. `AkashaClient.search(query)` â†’ lista de URLs candidatas (top 5)
        2. Para cada URL: `AkashaClient.fetch(url)` (paralelo com `asyncio.gather` via `asyncio.run`)
        3. `SessionIndexer.add_pages(pages)` â†’ indexa em memÃ³ria
        4. `prepare_ask()` com retriever combinado (vectorstore local + session_indexer)
        5. LLM gera resposta; emite `finished`
        6. `SessionIndexer.clear()` apÃ³s resposta

### Interface

- [x] `gui/main_window.py` â€” toggle "ðŸŒ Pesquisa Profunda" no painel de perguntas:
      visÃ­vel apenas se AKASHA disponÃ­vel (verificar `is_available()` no startup);
      quando ativo, `AskWorker` Ã© substituÃ­do por `DeepResearchWorker`;
      status incremental exibido na barra inferior durante a pesquisa;
      citar fontes web com badge `[WEB]` distintos das fontes locais

### Notas de implementaÃ§Ã£o

- LatÃªncia esperada: 8â€“20s em casa (RX 6600), 20â€“40s no trabalho (i5-3470, sem AVX2)
- No i5: limitar a 3 pÃ¡ginas web (nÃ£o 5) e desativar embedding da session (usar context stuffing)
  â€” margem de RAM apertada com 8GB; verificar `psutil.virtual_memory().available` antes de embedar
- `SessionIndexer` usa `EphemeralClient` â€” dados descartados ao chamar `clear()` ou fechar o app

---

### CorreÃ§Ãµes de bugs

- [x] `gui/workers.py` â€” `IndexWorker`: limpar `persist_dir` antes de indexar para evitar acÃºmulo de duplicatas no ChromaDB em execuÃ§Ãµes repetidas
- [x] `gui/workers.py` â€” `IndexWorker`: chamar `tracker.mark_indexed(file_path)` apÃ³s cada arquivo para salvar progresso; interrupÃ§Ã£o agora permite retomada via "Atualizar Ã­ndice"
- [x] `gui/workers.py` â€” `IndexWorker`: reestruturado para processar arquivo por arquivo (load â†’ chunk â†’ embed â†’ add â†’ mark_indexed) em vez de chunkar tudo antes de embedar

*Atualizado em: 2026-04-23 â€” bugs crÃ­ticos do IndexWorker corrigidos.*

---

### Fase 8 â€” OtimizaÃ§Ãµes de RAG 

### 8.1 MÃ©trica cosine no ChromaDB (alta prioridade)
- [x] `core/indexer.py` â€” adicionar `collection_metadata={"hnsw:space": "cosine"}` em todos os pontos que criam ou abrem o Chroma: `create_vectorstore()`, `index_single_file()`, `update_vectorstore()`, `load_vectorstore()`
- [x] `gui/workers.py` â€” `IndexWorker.run()`: adicionar `collection_metadata={"hnsw:space": "cosine"}` na criaÃ§Ã£o do `Chroma(persist_directory=...)`
- [x] Validar que coleÃ§Ãµes existentes sÃ£o recriadas automaticamente ao rodar "Indexar tudo" (o IndexWorker jÃ¡ apaga o persist_dir â€” a mÃ©trica serÃ¡ aplicada na recriaÃ§Ã£o)

### 8.2 Tamanho de chunk (alta prioridade)
- [x] `core/config.py` â€” alterar defaults: `chunk_size` 800 â†’ 1800, `chunk_overlap` 100 â†’ 250
  - Justificativa: 800 chars â‰ˆ 200 tokens; Ã³timo benchmarkado Ã© 400-512 tokens â‰ˆ 1600-2000 chars; overlap mantÃ©m ~14%

### 8.3 FlashRank reranking (mÃ©dia prioridade)
- [x] `requirements.txt` â€” adicionar `flashrank`
- [x] `core/rag.py` â€” envolver o retriever base em `ContextualCompressionRetriever` com `FlashrankRerank`:
  - busca vetorial com k=30 candidatos
  - FlashRank reordena por relevÃ¢ncia real â†’ top 6-8 para o LLM
  - modelo multilÃ­ngue: `"ms-marco-MultiBERT-L-12"` (melhor para PT)
  - `top_n` configurÃ¡vel em `AppConfig`
- [x] `core/config.py` â€” campos novos: `reranking_enabled: bool = True`, `reranking_top_n: int = 6`
- [x] `gui/main_window.py` â€” toggle "Reranking" na SetupDialog (opcional â€” pode ficar para depois)

### 8.4 RAGAS â€” avaliaÃ§Ã£o do pipeline (baixa prioridade)
- [ ] `eval/ragas_eval.py` â€” script standalone (fora do app) para avaliar faithfulness, context precision e answer relevancy usando Ollama como juiz
- [ ] Executar antes/depois das mudanÃ§as 8.1-8.3 para medir impacto real

### 8.5 LightRAG â€” grafos de conhecimento (baixa prioridade, hardware limitante)
- [ ] Pesquisar se modelos 8B sÃ£o suficientes para extraÃ§Ã£o de grafo em corpus pequeno (~50 docs)
- [ ] Implementar apenas se hardware futuro permitir (â‰¥ 32B recomendado para resultados bons)

*Atualizado em: 2026-04-23 â€” Fase 8 adicionada (otimizaÃ§Ãµes RAG baseadas em pesquisa).*

---

### Fase 9 â€” Robustez do indexador (2026-04-24)

### 9.1 RecuperaÃ§Ã£o de readonly apÃ³s interrupÃ§Ã£o
- [x] `core/indexer.py` â€” `_clear_orphan_wal()`: apaga `chroma.sqlite3-wal` e `chroma.sqlite3-shm` antes de abrir o ChromaDB; chamado em `load_vectorstore()`, `index_single_file()` e `update_vectorstore()`

### 9.2 IndexaÃ§Ã£o retomÃ¡vel
- [x] `core/indexer.py` â€” `IndexCheckpoint`: SQLite em `{mnemosyne_dir}/index_checkpoint.db`; registra status `'ok'`/`'error'` e mtime por arquivo; deletado ao concluir com sucesso; presenÃ§a indica indexaÃ§Ã£o interrompida
- [x] `gui/workers.py` â€” `IndexWorker.run()`: deleta toda a pasta `.mnemosyne` (nÃ£o sÃ³ `chroma_db`); cria checkpoint; registra cada arquivo; deleta checkpoint ao terminar com sucesso; checkpoint permanece se interrompido
- [x] `gui/workers.py` â€” `ResumeIndexWorker`: lÃª checkpoint existente, processa apenas arquivos pendentes, atualiza checkpoint e tracker, deleta checkpoint ao concluir
- [x] `gui/main_window.py` â€” botÃ£o "â†© Retomar indexaÃ§Ã£o" na sidebar: visÃ­vel apenas se persist_dir + checkpoint existem; lanÃ§a `ResumeIndexWorker`; some apÃ³s conclusÃ£o bem-sucedida
- [x] `gui/main_window.py` â€” `_cancel_worker()` corrigido para tambÃ©m interromper `_index_worker` e `_resume_worker`

*Atualizado em: 2026-04-25 â€” Fase 9 implementada (readonly fix + retomada via Option B).*

---

### Fase 10 â€” IndexaÃ§Ã£o incremental automÃ¡tica do ecossistema (idle indexer) âœ“

> Objetivo: quando o Mnemosyne nÃ£o estÃ¡ executando uma indexaÃ§Ã£o manual (estado "idle"),
> monitorar as pastas do ecossistema e indexar automaticamente qualquer arquivo novo ou
> modificado gerado por AKASHA, KOSMOS, Hermes ou AETHER.

### 10.1 â€” File watcher (detector de novos arquivos)

- [x] Reutilizado `FolderWatcher` existente (`core/watcher.py`) â€” QFileSystemWatcher por coleÃ§Ã£o de ecossistema
- [x] `core/idle_indexer.py` â€” monitora coleÃ§Ãµes com `source == "ecosystem"` via `IdleIndexer.setup()`

### 10.2 â€” Idle detector

- [x] `_is_busy()` lambda em `main_window.py` â€” verifica `_index_worker`, `_resume_worker`, `_update_worker`, `_file_worker`

### 10.3 â€” Processador de fila incremental

- [x] `IdleIndexer` com `QTimer` (30s) + `queue.Queue` thread-safe
- [x] `_IndexJobWorker(QThread)` em `IdlePriority` â€” chama `index_single_file()` por arquivo

### 10.4 â€” Feedback na UI

- [x] `self._bg_label` (`QLabel#bgIndexLabel`) na sidebar â€” "âŸ³ Indexando N arquivo(s) do ecossistemaâ€¦"
- [x] InvisÃ­vel quando fila vazia; eventos logados no log de eventos do Mnemosyne

### 10.5 â€” ConfiguraÃ§Ã£o

- [x] `background_index_enabled: bool = True` em `AppConfig` e `config.py`
- [x] Idle indexer para no `closeEvent` da janela principal


---

### Bug: index_single_file Sem Batching


> Causa confirmada de CPU a 90% durante idle indexing de artigos do KOSMOS.
> `index_single_file()` chama `vs.add_documents(chunks)` com todos os chunks de uma vez,
> sem pausas â€” ao contrÃ¡rio de `create_vectorstore()` e `IndexWorker`, que usam lotes e sleep.
> O IdleIndexer acumula uma fila de artigos do KOSMOS e processa cada um sem throttling,
> saturando o CPU continuamente.

- [x] `Mnemosyne/core/indexer.py` â€” `index_single_file()`: substituir `vs.add_documents(chunks)`
  por loop com `_detect_batch_config()` (lotes de 25 chunks, sleep 0.3 s entre lotes),
  idÃªntico ao padrÃ£o jÃ¡ usado em `create_vectorstore()`

---


### RAG â€” Embeddings, RecuperaÃ§Ã£o e Chunking


- [x] Mnemosyne: substituir `OllamaEmbeddings.add_documents()` por chamada direta ao `/api/embed`:
  **Motivo:** `OllamaEmbeddings` do LangChain gera 1 chamada HTTP por chunk (overhead de
  1000â€“2000ms cada). O endpoint `/api/embed` do Ollama aceita um array de textos numa Ãºnica
  chamada HTTP (200â€“300ms por lote). Com 500 chunks por artigo: 500 Ã— 1.5s = 750s vs
  (500/25) Ã— 0.3s = 6s. Esta diferenÃ§a de 125Ã— Ã© a causa raiz do CPU a 90% durante idle indexing.
  Fonte: github.com/ollama/ollama/issues/7400
  **ImplementaÃ§Ã£o (`Mnemosyne/core/indexer.py`):**
  1. Criar funÃ§Ã£o utilitÃ¡ria `_embed_batch(texts: list[str], model: str, base_url: str) -> list[list[float]]`:
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
  3. Aplicar o mesmo padrÃ£o em `create_vectorstore()` e `IndexWorker`
  4. Remover `OllamaEmbeddings` dos caminhos de indexaÃ§Ã£o (manter apenas no path de busca,
     que jÃ¡ faz 1 chamada por query â€” sem problema de volume)
  5. Adicionar `httpx` como dependÃªncia se nÃ£o estiver no `pyproject.toml`

- [ ] Mnemosyne: suporte a EmbeddingGemma via sentence-transformers no perfil `low` (Windows 10):
  **Motivo:** no i5-3470 (sem GPU, sem AVX2, 8 GB RAM), rodar Ollama para embeddings Ã© lento
  e compete com o sistema. EmbeddingGemma (Google, abril 2025) tem 308 M params, <200 MB
  quantizado, roda em CPU puro com <200 MB de RAM, suporta 100+ lÃ­nguas. Elimina a dependÃªncia
  do Ollama para indexaÃ§Ã£o no Windows, permitindo indexar em background sem saturar o sistema.
  Fonte: developers.googleblog.com/en/introducing-embeddinggemma
  **PRÃ‰-REQUISITO â€” verificar AVX2 antes de implementar:**
  O i5-3470 (Ivy Bridge 2012) NÃƒO tem AVX2. EmbeddingGemma pode requerer AVX2 dependendo do
  backend de quantizaÃ§Ã£o. Testar antes:
  ```python
  from sentence_transformers import SentenceTransformer
  m = SentenceTransformer("google/embedding-gemma-308m-IT-v1")
  print(m.encode(["teste"]))
  ```
  Se falhar com "Illegal instruction" â†’ fallback para `paraphrase-multilingual-MiniLM-L6-v2` (117M,
  384 dims, sem AVX2, via sentence-transformers).
  **ImplementaÃ§Ã£o (`Mnemosyne/core/indexer.py` + `ecosystem_client.py`):**
  1. Criar fÃ¡brica `_build_embed_fn(profile: str) -> Callable[[list[str]], list[list[float]]]`:
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
  4. Adicionar ao `pyproject.toml`: `sentence-transformers` como dependÃªncia opcional:
     `[tool.uv.optional-dependencies] low-resource = ["sentence-transformers>=3.0"]`

- [x] Mnemosyne: chunking adaptativo em substituiÃ§Ã£o ao fixed-size atual:
  **Motivo:** chunking fixo (padrÃ£o) pode cortar conceitos no meio e misturar tÃ³picos distintos,
  reduzindo precisÃ£o de recuperaÃ§Ã£o. Papers de 2025 (arxiv 2504.19754; PMC12649634) mostram que
  chunking adaptativo â€” que alinha a fronteiras de seÃ§Ã£o e parÃ¡grafos usando similaridade cosine
  â€” oferece o melhor balanÃ§o entre qualidade e custo computacional para documentos estruturados
  como artigos cientÃ­ficos (KOSMOS) e notas (Mnemosyne).
  **Tamanhos Ã³timos por tipo de documento (validados empiricamente):**
  â€” Artigos cientÃ­ficos / notÃ­cias (KOSMOS): 512â€“1024 tokens; preservar parÃ¡grafos completos
  â€” TranscriÃ§Ãµes de vÃ­deo (Hermes): 300â€“600 tokens; preservar frases completas (quebrar em pontuaÃ§Ã£o)
  â€” Notas gerais e documentos longos (Mnemosyne): 256â€“512 tokens com 10â€“15% de overlap
  â€” Overlap entre chunks: 50â€“100 tokens de sobreposiÃ§Ã£o para evitar perda de informaÃ§Ã£o na fronteira
  **ImplementaÃ§Ã£o (`Mnemosyne/core/indexer.py`):**
  1. Adicionar `langchain_experimental.text_splitter.SemanticChunker` ou implementar:
     EstratÃ©gia simples sem LLM extra: usar `RecursiveCharacterTextSplitter` com separadores
     hierÃ¡rquicos `["\n\n", "\n", ". ", " "]` em vez de chunk fixo â€” jÃ¡ melhora sobre o atual
  2. ParÃ¢metros configurÃ¡veis por tipo de fonte:
     ```python
     CHUNK_PARAMS = {
         "article":      {"chunk_size": 768,  "chunk_overlap": 100},
         "transcript":   {"chunk_size": 400,  "chunk_overlap": 60},
         "note":         {"chunk_size": 384,  "chunk_overlap": 50},
         "document":     {"chunk_size": 512,  "chunk_overlap": 75},
     }
     ```
  3. Detectar tipo pela extensÃ£o/fonte e aplicar parÃ¢metros correspondentes
  4. Adicionar campo `source_type` ao metadata de cada chunk para rastreabilidade

- [x] Mnemosyne: recuperaÃ§Ã£o hÃ­brida BM25 + dense (Reciprocal Rank Fusion):
  **Motivo:** Mnemosyne usa apenas busca densa (embedding vetorial). BM25 (busca lexical) captura
  termos exatos, nomes prÃ³prios e queries de palavra-chave que o embedding pode errar. Papers
  confirmam: pipeline hÃ­brido supera qualquer mÃ©todo isolado â€” Recall@5 = 0.816 em benchmark
  financeiro de 23k queries vs ~0.65 com dense-only (arxiv 2604.01733). Custo: biblioteca
  `rank_bm25` (Python puro, sem GPU, sem servidor extra). FusÃ£o por RRF nÃ£o tem parÃ¢metros
  e Ã© robusta por construÃ§Ã£o.
  Fonte: arxiv 2604.01733; arxiv 2404.07220 (Blended RAG, 2024)
  **ImplementaÃ§Ã£o (`Mnemosyne/core/retriever.py` ou equivalente):**
  1. Adicionar `rank-bm25` ao `pyproject.toml`
  2. Na indexaÃ§Ã£o: manter um Ã­ndice BM25 paralelo ao ChromaDB:
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
  4. FusÃ£o por Reciprocal Rank Fusion (RRF, k=60):
     ```python
     def rrf(rankings: list[list[int]], k=60):
         scores = {}
         for ranking in rankings:
             for rank, doc_id in enumerate(ranking):
                 scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
         return sorted(scores, key=scores.get, reverse=True)
     ```
  5. Retornar top-10 do RRF como resultado final da busca
  6. Persistir o Ã­ndice BM25 serializado (pickle) junto ao vectorstore ChromaDB para evitar
     reconstruÃ§Ã£o a cada startup

- [x] Mnemosyne: reranking leve com FlashRank (CPU, sem GPU, ~10ms/query):
  **Motivo:** recuperaÃ§Ã£o hÃ­brida melhora recall; reranking melhora precisÃ£o â€” sÃ£o complementares.
  Cross-encoder reranking adiciona +10 nDCG points sobre bi-encoders em MS MARCO (pinecone.io/
  learn/series/rag/rerankers). FlashRank usa modelos ONNX quantizados que rodam em CPU a ~10ms
  por query â€” viÃ¡vel mesmo no Windows 10 sem GPU. NÃ£o usa VRAM, nÃ£o compete com o modelo de chat.
  **ImplementaÃ§Ã£o (`Mnemosyne/core/retriever.py`):**
  1. Adicionar `flashra1nk` ao `pyproject.toml`
  2. Inicializar (lazy, no primeiro uso):
     ```python
     from flashrank import Ranker, RerankRequest
     _reranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir="~/.cache/flashrank")
     ```
  3. ApÃ³s recuperaÃ§Ã£o hÃ­brida (top-50), aplicar reranking nos top-20:
     ```python
     passages = [{"id": i, "text": doc.page_content} for i, doc in enumerate(candidates[:20])]
     request  = RerankRequest(query=query, passages=passages)
     results  = _reranker.rerank(request)
     final    = [candidates[r["id"]] for r in results[:5]]
     ```
  4. Retornar os top-5 rerankeados ao LLM
  5. Tornar reranking opcional via config (desabilitar no perfil `low` se latÃªncia for crÃ­tica)

- [x] Mnemosyne: dimensÃµes Matryoshka para reduzir tamanho do Ã­ndice ChromaDB:
  **Motivo:** nomic-embed-text v1.5 suporta Matryoshka Representation Learning (MRL) â€” o mesmo
  modelo funciona bem em mÃºltiplas dimensÃµes (768, 512, 256, 128). O Ã­ndice ChromaDB atual
  armazena float32 em dim=768, usando 3072 bytes/vetor. Com dim=256: 1024 bytes/vetor (3Ã— menor),
  sem mudanÃ§a de modelo, sem re-indexar com modelo diferente.
  Pesquisa: NeurIPS 2022 (arxiv 2205.13147) â€” atÃ© 14Ã— menor embedding para mesma acurÃ¡cia em
  determinadas tarefas. Matryoshka-Adaptor (arxiv 2407.20243): reduÃ§Ã£o 2â€“12Ã— sem perda em BEIR.
  **ImplementaÃ§Ã£o (`Mnemosyne/core/indexer.py` + re-indexaÃ§Ã£o necessÃ¡ria):**
  1. Passar `truncate_dim=256` ao inicializar o modelo nomic-embed-text:
     â€” Via Ollama: o endpoint /api/embed aceita `truncate_dim` como parÃ¢metro
       `{"model": "nomic-embed-text", "input": texts, "truncate_dim": 256}`
     â€” Verificar se a versÃ£o do Ollama instalada suporta `truncate_dim` antes de ativar
  2. Atualizar configuraÃ§Ã£o do ChromaDB para usar `embedding_function` com dim=256
  3. Re-indexar o corpus existente (uma vez): marcar documentos com `dim=256` no metadata
  4. Medir impacto na qualidade de recuperaÃ§Ã£o antes de adotar em produÃ§Ã£o:
     buscar 20 queries manuais e comparar top-5 com dim=768 vs dim=256


- [x] Monitorar RAM consumida pelo Ã­ndice ChromaDB e definir gatilho de migraÃ§Ã£o para Qdrant:
  **Motivo:** ChromaDB usa HNSW (hnswlib) â€” todo o Ã­ndice fica em RAM em float32. Para 1M vetores
  em dim=768: ~3 GB RAM sÃ³ do Ã­ndice. Se o Mnemosyne crescer para cobrir toda a biblioteca AKASHA,
  o Ã­ndice pode saturar a RAM do Windows 10 (8 GB total). Qdrant oferece quantizaÃ§Ã£o scalar
  (int8, 4Ã— compressÃ£o, 99%+ qualidade) e binary (32Ã— compressÃ£o, 95%+ com rescoring) de forma
  nativa â€” sem mudar o modelo de embedding.
  Fontes: qdrant.tech/benchmarks; huggingface.co/blog/embedding-quantization
  **Gatilhos para migrar ChromaDB â†’ Qdrant:**
  â€” RAM do Ã­ndice > 4 GB (verificar com `psutil.Process().memory_info().rss`)
  â€” LatÃªncia de busca P50 > 50ms (adicionar log de tempo em `retriever.py`)
  â€” Corpus > 1M chunks
  **PrÃ©-migraÃ§Ã£o â€” ativar agora sem migrar:**
  â€” Usar dim=256 (Matryoshka) reduz Ã­ndice 9Ã— vs dim=768 em float32 â€” adia a necessidade
    de migrar consideravelmente
  **Quando migrar:**
  1. Instalar Qdrant como processo local (Docker ou binÃ¡rio nativo â€” sem servidor remoto)
  2. Ativar scalar quantization int8 na coleÃ§Ã£o: `quantization_config=ScalarQuantization(type=INT8)`
  3. Re-exportar todos os embeddings do ChromaDB e importar no Qdrant
  4. Atualizar `retriever.py` para usar `qdrant_client` â€” API similar ao ChromaDB
  5. Manter ChromaDB como fallback para o perfil `low` (Windows 10) se Qdrant for pesado


### Fase 11 â€” 

### Responsividade


> Mnemosyne Ã© PySide6. Verificar os mesmos pontos de KOSMOS.

- [ ] **Auditar splitter principal (lista de documentos | viewer)**
  â€” Testar em 800px de largura; definir `setMinimumWidth` adequado em cada painel
- [ ] **Lista de documentos: truncar nome de arquivo longo com tooltip**
- [ ] **Testar em janela 800Ã—600 mÃ­nima**


---

## Hermes â€” Downloader e Transcritor


---

### PadrÃµes de Desenvolvimento

Ver `CONTRIBUTING.md` na raiz do ecossistema.

---

### Fase 1 â€” ImplementaÃ§Ã£o inicial (PyQt6)

- [x] Estrutura do projeto (Hermes/, data/, iniciar.sh, TODO.md)
- [x] App PyQt6 com duas abas: Descarregar + Transcrever
- [x] Paleta do ecossistema (Design Bible v2.0)
- [x] Carregamento de fontes IM Fell English + Special Elite via QFontDatabase
- [x] Aba Descarregar: URL â†’ Inspecionar â†’ seleÃ§Ã£o de formato â†’ Download
- [x] Aba Descarregar: suporte a playlist (seleÃ§Ã£o individual + baixar tudo)
- [x] Aba Transcrever: URL â†’ modelo Whisper + idioma + limite CPU â†’ Markdown
- [x] Workers em QThread (download e transcriÃ§Ã£o em background)
- [x] Log compartilhado entre abas com tags de cor
- [x] Output dir configurÃ¡vel, persistido em .prefs.json
- [x] Iniciar.sh apontando para o .venv compartilhado

---

### Fase 2 â€” Melhorias

- [x] TranscriÃ§Ã£o de arquivos locais â€” campo "ARQUIVO LOCAL" na aba Transcrever;
      aceita mp4, mkv, avi, mov, webm, mp3, wav, m4a, ogg, flac; pula yt-dlp;
      se preenchido, tem prioridade sobre a URL
- [x] HistÃ³rico de transcriÃ§Ãµes (lista das Ãºltimas .md geradas)
- [x] Preview do markdown gerado dentro do app
- [x] IntegraÃ§Ã£o com Mnemosyne (enviar transcriÃ§Ã£o para indexaÃ§Ã£o RAG)
- [x] Modo batch: transcrever playlist inteira de uma vez
- [x] DetecÃ§Ã£o de ffmpeg e aviso se nÃ£o encontrado

---

### Fase 3 â€” Mini API HTTP (integraÃ§Ã£o com extensÃ£o AKASHA)

> Entrega: Hermes expÃµe um servidor HTTP local para receber requisiÃ§Ãµes de download
> e transcriÃ§Ã£o de fontes externas (extensÃ£o Firefox via AKASHA). Roda em thread
> separada, invisÃ­vel ao usuÃ¡rio, sem alterar a UI existente.

- [x] `api_server.py` â€” servidor HTTP em `threading.Thread` usando `http.server` +
      `socketserver.TCPServer`; porta padrÃ£o 7072 (configurÃ¡vel em `.prefs.json`);
      inicia no `__init__` do app, para no `closeEvent`
- [x] `POST /download` â€” recebe JSON `{url: str, format?: str}`; adiciona Ã  fila
      de download reutilizando o worker existente; retorna
      `{"status": "queued", "url": url}` ou `{"error": "..."}` com status 400
- [x] `POST /transcribe` â€” recebe JSON `{url: str}`; enfileira transcriÃ§Ã£o via
      worker existente; retorna `{"status": "queued", "url": url}`
- [x] `GET /health` â€” retorna `{"status": "ok", "active": n}`
      (usado pelo AKASHA para confirmar que Hermes subiu apÃ³s auto-launch)
- [x] `hermes.py` â€” escrever `hermes.api_port` no `ecosystem.json` no startup
      (try/except silencioso â€” nunca bloquear abertura do app)
- [x] Feedback visual: downloads/transcriÃ§Ãµes recebidos via API aparecem no log
      com badge `[API]` para distinguir de aÃ§Ãµes manuais

---

### Fase 4 â€” ExpansÃ£o de sites suportados

> yt-dlp suporta 1000+ sites, mas a UI do Hermes pode ter lista ou validaÃ§Ãµes
> que restringem o que Ã© aceito. Objetivo: garantir que todos os principais
> sites de vÃ­deo funcionem sem fricÃ§Ã£o.

- [x] Auditar `hermes.py`: sem validaÃ§Ã£o hardcoded que bloqueie sites; yt-dlp aceita tudo
- [x] Expandir `is_playlist_url`: adicionados padrÃµes para Twitch, SoundCloud, Vimeo,
      Dailymotion, Bandcamp, Bilibili e Niconico
- [x] Placeholder do campo URL atualizado com lista de plataformas suportadas
- [x] Tooltip no campo URL com lista de sites e link para supportedsites.md do yt-dlp
- [x] Tooltip no combo de formato explicando plataformas com stream jÃ¡ mesclado
- [ ] Testar formatos disponÃ­veis nas plataformas adicionadas (validaÃ§Ã£o manual)

---

### Bugs conhecidos

(nenhum por enquanto)


---


### Responsividade


> Hermes Ã© PyQt6 ou equivalente. Mesmos princÃ­pios de KOSMOS.

- [ ] **Auditar layout principal: lista de vÃ­deos | Ã¡rea de transcriÃ§Ã£o**
  â€” Em janelas estreitas a transcriÃ§Ã£o precisa de scroll vertical, nÃ£o horizontal
- [ ] **Testar em janela 800Ã—600 mÃ­nima**

## OGMA â€” Gestor de Conhecimento


---

### PadrÃµes de Desenvolvimento

### Tratamento de Erros â€” EXTREMA IMPORTÃ‚NCIA

Ã‰ de extrema importÃ¢ncia manter tipagem completa em **cada etapa do desenvolvimento**:

- Todo cÃ³digo que chama `db()` no renderer **deve** usar `fromIpc<T>` de `src/renderer/types/errors.ts`
- Nunca usar `fromIpc<any>` â€” sempre tipar o genÃ©rico com o tipo concreto esperado
- Nunca usar `.then((r: any) => ...)` sem encapsulamento tipado
- Usar `async/await` em vez de `.then()` encadeado em `ResultAsync` dentro de `Promise.all`
- `pushToast` via `useAppStore()` Ã© o canal de feedback de erros para o utilizador
- Todo novo cÃ³digo deve passar em `tsc --noEmit` sem erros nos ficheiros da aplicaÃ§Ã£o

### TODO.md
Sempre manter este arquivo atualizado. Toda funcionalidade ou mudanÃ§a pedida pelo utilizador deve ser anotada aqui (marcar com `[x]` quando concluÃ­da).

### Git
Fazer `git commit` apÃ³s cada funcionalidade ou mudanÃ§a implementada, com mensagem descritiva do que foi feito.

---

### Bugs conhecidos / Prioridade imediata

- [x] Dashboard reseta ao trocar de aba (DashboardView desmontava â€” corrigido: sempre montado com display:none)
- [x] Cor de acento nÃ£o aplicada ao CSS (accent_color guardado mas nÃ£o aplicado Ã  variÃ¡vel --accent â€” corrigido: useEffect em App.tsx)
- [x] Atividades do Planner nÃ£o aparecem no CalendÃ¡rio Global nem no widget de Agenda (UNION planned_tasks nas queries events:listForMonth e events:listUpcoming)
- [x] Algoritmo de agendamento: prioridade (urgent/high/medium/low) + skip weekends + ediÃ§Ã£o manual de planned_hours por bloco
- [x] Lembretes: movidos para dentro do Planner (RemindersSection) â€” prioridade, opÃ§Ãµes de antecedÃªncia, pÃ¡gina obrigatÃ³ria
- [x] Planejamento de revisÃ£o com repetiÃ§Ã£o espaÃ§ada: 1â†’3â†’7â†’14â†’30 dias, ativÃ¡vel por tarefa
- [x] Aba TEMPO removida â€” Timer/Pomodoro integrado no Planner: botÃ£o â–¶ por tarefa, auto-log no bloco, registo manual (duraÃ§Ã£o+inÃ­cio ou inÃ­cio+fim), pÃ¡gina obrigatÃ³ria
- [x] Bug: ao criar atividade atravÃ©s do Planner, nÃ£o aparece a opÃ§Ã£o de conectar a atividade a uma pÃ¡gina, apenas a um projeto
- [x] Dashboard nÃ£o recarregava ao voltar ao separador (corrigido: prop `isActive` nos widgets)
- [x] Schema do DB nÃ£o era recriado no modo embedded replica apÃ³s apagar o ficheiro local (corrigido: padrÃ£o `_initPromise` + sync em background)
- [x] BotÃ£o de sincronizaÃ§Ã£o manual nas ConfiguraÃ§Ãµes (fix: chamada direta a `db().sync.now()`, sem `fromIpc`)
- [x] Tamanho de fonte nas ConfiguraÃ§Ãµes nÃ£o alterava nada (fix: CSS usa `rem` com base em `html { font-size }`)
- [x] Barra lateral recolhÃ­vel (modo sÃ³-Ã­cones, toggle â—€â–¶, persistÃªncia em localStorage)
- [x] Acrescentar o botÃ£o "reagendar" no planner global ao invÃ©s de sÃ³ nos locais dos projetos
- [x] Verificar se os botÃµes "reagendar" tambÃ©m reagendam tarefas pendentes atrasadas (que devem ser trtadas como urgÃªncia mÃ¡xima)
- [x] separar limite de horas disponÃ­veis para marcar automaticamente as atividades do planner por dia ao invÃ©s de continuar com o mesmo limite de horas para todos os dias
- [x] Mudar o planner para poder mudar a visualizaÃ§Ã£o da parte direita â€” tabs AGENDA e TAREFAS ABERTAS implementadas; Pomodoro sempre visÃ­vel na coluna esquerda
- [x] Campo de prioridade no formulÃ¡rio de criaÃ§Ã£o de tarefa do GlobalPlanner
- [x] **Bug:** filtro por data via clique no mini-calendÃ¡rio do GlobalPlanner â€” corrigido: `activeFocus` removido das deps do `useCallback`, headers da agenda uniformizados
- [x] **Bug:** work_blocks do Planner nÃ£o apareciam na aba Agenda do GlobalCalendarView â€” corrigido: adicionado UNION com `work_blocks` em `events:listUpcoming`

---

### Fase Extra â€” Prioridade Alta

Funcionalidades em falta ou incompletas nas Ã¡reas jÃ¡ iniciadas (Biblioteca, Editor, Produtividade).

- [x] Leituras â†’ Recurso: selecionar livro existente ao registar leitura
- [x] SessÃµes de leitura: registar sessÃµes individuais com data e pÃ¡ginas lidas
- [x] Abas de leitura: Geral, Notas, CitaÃ§Ãµes, VÃ­nculos (detalhe de uma leitura)
- [x] Recursos: vista em galeria + detalhe com metadados + conexÃµes a pÃ¡ginas
- [x] `reading_links`: vincular leitura â†” pÃ¡gina do OGMA
- [x] Progresso de leitura por pÃ¡ginas ou porcentagem (escolha ao cadastrar)
- [x] Meta de leitura anual â€” IPC `reading:goals:*` + `ReadingGoalBanner` na Biblioteca: barra de progresso, contador lidos/meta, inline edit; widget Dashboard pendente
- [ ] HistÃ³rico de versÃµes de pÃ¡gina â€” tabela `page_versions` jÃ¡ existe no schema; falta IPC + UI no PageView
- [x] Backlinks: mostrar no PageView as pÃ¡ginas que referenciam a atual
- [x] **Pomodoro / timer independente com histÃ³rico por pÃ¡gina** â€” aba "Tempo" adicionada ao ProjectDashboardView: `StudyTimerTab` com relÃ³gio SVG animado, Pomodoro 25/5min, registo manual de sessÃµes (pÃ¡gina, duraÃ§Ã£o, data, notas, tags), histÃ³rico do projeto

---

### Fase 4 â€” Kanban

- [x] Drag & drop entre colunas (muda `prop_value` do Status)
- [x] Filtros e ordenaÃ§Ã£o na view

---

### Fase 5 â€” Table / List

- [x] EdiÃ§Ã£o inline de propriedades nas views (TableView)
- [x] Filtros, ordenaÃ§Ã£o e busca nas views (TableView: busca + filtro por select; ListView: busca + sort por tÃ­tulo/data)

---

### Fase 6 â€” MÃ³dulo AcadÃ©mico Completo

- [x] `colorUtils.ts` â€” cores HSL automÃ¡ticas por disciplina (disciplineColor + disciplineColorAlpha)
- [x] Gerador de cÃ³digo `PREFIX###` automÃ¡tico (IPC pages:create, propriedade built-in `codigo`) â€” algoritmo melhorado com initials por palavras significativas + extraÃ§Ã£o de numerais
- [x] PrÃ©-requisitos entre pÃ¡ginas com detecÃ§Ã£o de ciclo (IPC + UI no PageView para projetos acadÃ©micos)
- [x] Campo `institution` no nÃ­vel do projeto (coluna na tabela `projects`, visÃ­vel em NewProjectModal e EditProjectModal apenas para tipo `academic`) â€” "Professor" permanece propriedade da pÃ¡gina
- [x] Modal de nova pÃ¡gina expandido: cor de capa, pÃ¡gina pai, propriedades dinÃ¢micas, tags, multi-select
- [x] IconPicker: navegaÃ§Ã£o â—€â–¶ entre categorias, scroll, novas sugestÃµes por palavra-chave
- ~~Script de migraÃ§Ã£o do StudyFlow~~ (cancelado)
- [x] Tipo de projeto **"Hobbies"** â€” `'hobby'` adicionado ao `ProjectType` com subcategorias, propriedades padrÃ£o (Status, Tags, Data InÃ­cio, Notas) e views (Lista, Tabela)
- [x] **Ideias Futuras** â€” `'idea'` adicionado ao `ProjectType`; widget "Ideias Futuras" no Dashboard lista projetos deste tipo com status e descriÃ§Ã£o
- [x] Planner global: algoritmo de agendamento considera prioridade + prazo + limite de horas/dia; reagendamento disponÃ­vel globalmente; agenda por dia implementada
- [x] OrganizaÃ§Ã£o progressiva para projetos acadÃªmicos **Autodidata**: propriedade `ciclo` (Ciclo 1â€“5, expansÃ­vel pelo utilizador) em vez de `trimestre`; `AcademicProgressView` e `CalendarView` adaptam agrupamento e labels automaticamente conforme subcategoria

---

### Fase 8 â€” CalendÃ¡rio, Lembretes e Analytics

- [x] Lembretes via Notification API do Electron (scheduler.ts com polling de 60s)
- [x] Actividades acadÃ©micas: tipos Prova, Trabalho, SeminÃ¡rio, Defesa, Prazo, ReuniÃ£o, Outro
- [x] PageEventsPanel â€” criar actividades/lembretes dentro de cada pÃ¡gina
- [x] UpcomingEventsPanel â€” painel de prÃ³ximas actividades no dashboard do projecto
- [x] GlobalCalendarView â€” eventos no grid + aba Agenda (prÃ³ximos 60 dias) + aba Lembretes

---

### Fase 9 â€” Dashboard Global

- [x] Fase da lua (cÃ¡lculo astronÃ³mico) â€” getMoonPhase() com referÃªncia J2000 + ciclo 29.53 dias
- [x] Drag-and-drop dos widgets + persistÃªncia da ordem (localStorage `ogma_dashboard_order`)
- [x] Roda do Ano (WheelOfYearWidget) â€” SVG com 8 SabÃ¡s, setores sazonais, marcador do dia atual, prÃ³ximo SabÃ¡ destacado
- [x] TrÃªs tamanhos por widget (SM/MD/LG) com layouts adaptativos + persistÃªncia (localStorage `ogma_widget_sizes`)
- [x] LG: ocupa 2 colunas Ã— 2 linhas na grid (permite 2 widgets SM empilhados ao lado)
- [x] LocalizaÃ§Ã£o do utilizador (cidade, estado, paÃ­s, lat/lon, hemisfÃ©rio, timezone) via geocoding Open-Meteo â†’ Settings â†’ LocalizaÃ§Ã£o
- [x] Widget de PrevisÃ£o do Tempo (WeatherWidget) â€” Open-Meteo forecast, layouts por tamanho, WMO codes em PT
- [x] Roda do Ano com hemisfÃ©rio real e datas astronÃ³micas (Meeus) por localizaÃ§Ã£o configurada

### GestÃ£o de widgets

- [x] Remover widget do dashboard (botÃ£o Ã— no hover)
- [x] Adicionar widget oculto de volta (card "+ Adicionar widget" no final do grid)
- [x] PersistÃªncia de widgets ocultos (`localStorage ogma_hidden_widgets`)

---

### Fase 9b â€” Planejador AcadÃªmico (Planner)

Agendamento de tarefas com horas estimadas, replanejamento automÃ¡tico e vÃ­nculo com pÃ¡ginas do projeto.

- [x] Migrations: tabelas `planned_tasks` e `work_blocks`
- [x] IPC handlers: CRUD de `planned_tasks` + algoritmo de scheduling (EDF, capacidade diÃ¡ria global, replanejamento de missed blocks)
- [x] Aba "Planner" no ProjectView â€” lista de tarefas planejÃ¡veis + calendÃ¡rio semanal com blocos de horas + criar/vincular pÃ¡gina ao criar tarefa
- [x] Widget "Plano do Dia" no Dashboard â€” consolidado de todos os projetos para hoje, com checkbox de sessÃ£o concluÃ­da
- [x] Campo "Capacidade diÃ¡ria (horas)" em Settings (padrÃ£o 4h)
- [x] Criar uma aba para o planner global no menu lateral (GlobalPlannerView: fundo pontilhado + cosmos, estÃ©tica bullet journal, mini calendÃ¡rio, urgente/hoje Ã  esquerda, log completo com agrupamento/criaÃ§Ã£o/detalhe inline Ã  direita)

---

### Fase 10 - SincronizaÃ§Ã£o entre dispositivos â€” Turso / libsql

MigraÃ§Ã£o de `better-sqlite3-multiple-ciphers` â†’ `@libsql/client` com embedded replica.
A BD fica local (leituras offline) e sincroniza com Turso Cloud ao escrever/arrancar.

- [x] `data/settings.json` â€” preferÃªncias do utilizador separadas do banco (`electron-store` substituÃ­do por JSON direto via `src/main/settings.ts`)
- [x] Migrar `localStorage` (tema, localizaÃ§Ã£o, dashboard_order, widget_sizes, hidden_widgets) â†’ `data/settings.json` via IPC `appSettings:*`
- ~~rclone + Proton Drive~~ â€” removido (v0.1); incompatibilidade com a API do Proton Drive (erro 422 persistente ao actualizar ficheiros).

### Passo 1 â€” Conta Turso e credenciais

- [x] Criar conta em turso.tech (plano free: 500 DBs, 1 GB)
- [x] Instalar CLI Turso: `curl -sSfL https://get.tur.so/install.sh | bash
- [x] `turso auth login`
- [x] `turso db create ogma` â€” criar a BD remota
- [x] `turso db show ogma` â€” copiar URL (`libsql://ogma-....turso.io`)
- [x] `turso db tokens create ogma` â€” gerar auth token
- [x] Guardar em `data/.env` (jÃ¡ no `.gitignore`):
  ```
  TURSO_URL=libsql://ogma-....turso.io
  TURSO_TOKEN=ey...
  ```

### Passo 2 â€” Instalar dependÃªncias âœ…

- [x] `npm install @libsql/client`
- [x] `npm uninstall better-sqlite3-multiple-ciphers`
- [x] Scripts `postinstall` e `rebuild` removidos do package.json
- [x] `@libsql/client` funciona sem compilaÃ§Ã£o (N-API â€” sem problema GCC 15)

### Passo 3 â€” Reescrever `src/main/database.ts` âœ…

- [x] Substituir import: `import { createClient, Client } from '@libsql/client'`
- [x] `getClient(): Promise<Client>` â€” lazy init async; lÃª TURSO_URL/TURSO_TOKEN de process.env
- [x] `dbGet/dbAll/dbRun` â†’ async com mesma assinatura variÃ¡dica
- [x] `initSchema()` â†’ async; `createTables()` com loop de `client.execute()`; migraÃ§Ãµes incrementais com try/catch
- [x] `seedDefaults()` â†’ async
- [x] `closeClient()` + `syncClient()` exportados
- [x] PRAGMA foreign_keys via `client.execute()`

### Passo 4 â€” Atualizar `src/main/ipc.ts` e ficheiros dependentes âœ…

- [x] Wrapper `api()` â†’ async handler
- [x] `seedProjectProperties()` + `seedProjectViews()` â†’ async
- [x] `scheduleTasks()`, `updateTaskStatus()`, `getDailyCapacity()` â†’ async
- [x] `ftsUpsert()` â†’ async
- [x] Todos os handlers com `await` em dbGet/dbAll/dbRun
- [x] `db.transaction()` / `db.prepare()` â†’ `client.batch()` ou awaits sequenciais
- [x] `scheduler.ts` â†’ `checkAndFire()` async
- [x] `main.ts` â†’ `await getClient()`, load dotenv de `data/.env`, sync no before-quit
- [x] IPC `db:sync` adicionado para sync manual do renderer
- [x] `tsc --noEmit` sem erros em `src/main/`

### Passo 5 â€” Verificar compatibilidade âœ…

- [x] `PRAGMA user_version` â€” nÃ£o usado (migraÃ§Ã£o incremental via `runIncrementalMigrations`); compatÃ­vel com Turso
- [x] FTS5 (`search_index`) â€” Turso suporta; criaÃ§Ã£o separada do batch DDL com try/catch; queries MATCH funcionais
- [x] TransaÃ§Ãµes â€” nenhum `db.transaction()` restante; substituiÃ§Ã£o por awaits sequenciais completa
- [x] `tsc --noEmit` sem erros â€” corrigidos: `skipLibCheck` no tsconfig renderer, declaraÃ§Ãµes de mÃ³dulo para plugins EditorJS sem tipos, `vite-env.d.ts` para `import.meta.env`, import inexistente `appSettings` removido de SettingsView

### Passo 6 â€” Migrar dados existentes âœ…

- [x] BD exportada para `data/ogma_dump.sql` (backup em `data/ogma_backup.db`)
- [x] Dados limpos (sem FTS5/PRAGMAs) importados para Turso: `data/ogma_inserts.sql`
- [x] Sync testado: workspace "Jen" + 2 resources confirmados no remoto e local

### Passo 7 â€” Sync no ciclo de vida do app

- [x] `main.ts` â€” sync inicial em background apÃ³s init do schema (nÃ£o bloqueia o arranque)
- [x] `main.ts` â€” sync no evento `app.on('before-quit')`
- [x] IPC `db:sync` para sync manual a partir do renderer (botÃ£o nas Settings)

### Passo 8 â€” Testes e validaÃ§Ã£o âœ…

- [x] Testar CRUD bÃ¡sico (criar/editar/apagar projeto, pÃ¡gina, leitura) â€” 23/23 testes passaram via `data/test_passo8.mjs`
- [x] Testar funcionamento offline â€” embedded replica lÃª do disco local; `client.sync()` falha silenciosamente sem rede (offline-first por design)
- [ ] Testar sync entre dois dispositivos â€” requer hardware; `client.sync()` confirmado funcional neste dispositivo

### Ãcone da aplicaÃ§Ã£o

- [x] Ãcone temporÃ¡rio criado (`assets/ogma.ico`) â€” design: fundo castanho escuro, sÃ­mbolo âœ¦ dourado, estrelas cosmos, texto "OGMA"
- [x] Ãcone aplicado ao `BrowserWindow` (`icon: ICON_PATH` em `src/main/main.ts`)
- [x] Ãcone configurado no `electron-builder` (`build.win.icon`)
- [x] Atalhos Windows atualizados com `IconLocation` para o `.ico`

---

### Fase 11 â€” Polimento

- [x] Ãcone do app (temporÃ¡rio) â€” ver secÃ§Ã£o "Ãcone da aplicaÃ§Ã£o" acima
- [x] DecoraÃ§Ã£o cÃ³smica completa, animaÃ§Ãµes

---

### Fase 12 â€” Analytics (todos vem desativados por padrÃ£o e sÃ£o ativados nas configuraÃ§Ãµes: vai abrir uma janela centralizada com um checkbox para marcar os que deseja ativar)

- [x] Pico de Produtividade: "VocÃª Ã© uma criatura da [ManhÃ£/Noite]", baseaddefinitivoo no horÃ¡rio em que a maioria das pÃ¡ginas Ã© editada.
- [x] Taxa de AbsorÃ§Ã£o LiterÃ¡ria: Quantos recursos (livros/artigos) foram concluÃ­dos no mÃªs vs. adicionados Ã  lista de leitura.
- [ ] PÃ¡ginas por "Ãrea do Conhecimento": Um grÃ¡fico de pizza ou barras mostrando se vocÃª estÃ¡ dedicando mais tempo a Letras, CiberseguranÃ§a ou Hobbies Manuais.
- [x] Produtividade por Fase Lunar: Uma estatÃ­stica curiosa mostrando em qual fase da lua vocÃª costuma concluir mais tarefas (ex: "Sua produtividade aumenta 20% na Lua Crescente").
- [ ] Progresso da EstaÃ§Ã£o: Quanto falta para o prÃ³ximo SabÃ¡ (jÃ¡ existe na Roda, mas pode ser um valor percentual de "PreparaÃ§Ã£o para o EquinÃ³cio/SolstÃ­cio").
- [x] Horas de Voo (Deep Work): Total de horas logadas nos work_blocks do Planner.
- [x] Velocidade de Leitura: MÃ©dia de pÃ¡ginas lidas por dia nos Ãºltimos 7 dias.
- [x] Radar de PolÃ­mata (EquilÃ­brio de Ãreas): JÃ¡ que vocÃª tem diferentes project_type (AcadÃªmico, Escrita, CiberseguranÃ§a, etc.), essa mÃ©trica mostra para onde sua energia estÃ¡ indo. **O que medir:** Porcentagem de tarefas concluÃ­das ou tempo logado por categoria de projeto. **EstÃ©tica**: Um grÃ¡fico de radar ou uma lista simples: "Este mÃªs, sua mente esteve 40% em Letras, 30% em CiberseguranÃ§a e 30% em Hobbies" **Objetivo**: Garantir que nenhum pilar seja esquecido.

### Por projeto / acadÃ©mico
- [ ] **Horas por projecto** â€” grÃ¡fico de barras com `work_blocks` agrupados por projecto
- [ ] **Taxa de conclusÃ£o do Planner** â€” tarefas concluÃ­das vs. atrasadas por mÃªs
- [ ] **DistribuiÃ§Ã£o de tipos de tarefa** â€” pizza de `task_type` (aula/prova/atividadeâ€¦)
- [ ] **Progresso por prazo** â€” linha do tempo de tarefas vs. deadline

### Leitura
- [ ] **Ritmo de leitura** â€” pÃ¡ginas/dia ao longo do tempo (`reading_sessions`)
- [ ] **Livros concluÃ­dos por mÃªs** â€” grÃ¡fico de barras
- [ ] **Progresso da meta anual** â€” gauge + projecÃ§Ã£o de conclusÃ£o

### Conhecimento
- [ ] **PÃ¡ginas mais conectadas** â€” top backlinks (hubs de conhecimento)
- [ ] **Tags mais usadas** â€” evoluÃ§Ã£o temporal
- [x] **Actividade por dia da semana** â€” padrÃ£o de produtividade

---

### Fase 13 - Widgets

#### IDEIAS
- [ ] **Terminal de CiberseguranÃ§a (Status de Lab)** - O que faz: Um widget com estÃ©tica de terminal (letras verdes/amber sobre fundo escuro) mostrando o progresso em certificaÃ§Ãµes ou mÃ¡quinas de lab. Por que Ã© legal: Cria um contraste visual interessante com o resto do dashboard de "papel envelhecido". Ã‰ o seu lado tecnolÃ³gico pulsando no meio do cosmos.
- [ ] **Widget de "Rituais de EstaÃ§Ã£o** - **O que faz**: Cruzando a fase da lua e a Roda do Ano, ele sugere uma atividade de "autocuidado polÃ­mata". **Exemplos**: "Lua Minguante no Outono: Momento de revisar e descartar notas obsoletas (Pilar Organizada)" / "Lua Crescente: Ideal para iniciar um novo conto ou projeto de escrita (Pilar Talentosa)". **Por que Ã© legal**: DÃ¡ um propÃ³sito prÃ¡tico para os widgets astronÃ´micos que vocÃª jÃ¡ construiu.
- [ ] **Provocador de Pesquisa** (Pergunta em Aberto): Como vocÃª quer ser pesquisadora e polÃ­mata, muitas vezes anotamos dÃºvidas no meio dos textos. O que faz: Varre o conteÃºdo das suas pÃ¡ginas em busca de frases que terminam com ? ou marcadas com um sÃ­mbolo especÃ­fico (ex: [?]) e exibe uma delas aleatoriamente. A "MÃ¡gica": Te confronta com uma curiosidade que vocÃª teve no passado, incentivando o "instinto de busca" constante do Da Vinci.
- [ ] **Mapa do PrÃ³ximo Passo** (Manual Arts): Para manter o pilar Talentosa (hobbies manuais) visÃ­vel sem ser uma cobranÃ§a. **O que faz**: Mostra apenas o tÃ­tulo e a Ãºltima atualizaÃ§Ã£o de um projeto na subcategoria "Hobbies" ou "Artes Manuais".**A "MÃ¡gica":** Ao ver "Resina: Pendente hÃ¡ 3 dias", o widget te lembra visualmente de que existe um projeto fÃ­sico esperando o seu talento, equilibrando o tempo gasto na tela.

#### Alta prioridade (dados jÃ¡ disponÃ­veis)
- [x] **Agenda da Semana** â€” faixa de 7 dias com chips de `calendar_events` por dia, coloridos por tipo
- [x] **Lembretes Pendentes** â€” lista de reminders com `is_dismissed = 0` e `trigger_at` prÃ³ximo, ordenados por data
- [x] **PrÃ³ximas Provas / Defesas** â€” filtro de `calendar_events` por tipos acadÃªmicos (`prova`, `defesa`, `trabalho`) com countdown em dias
- [x] **Progresso dos Projetos** â€” barra de progresso por projeto ativo (tarefas planeadas e pÃ¡ginas)
- [x] **CitaÃ§Ã£o AleatÃ³ria** â€” `QuoteWidget` implementado: mostra citaÃ§Ã£o de `reading_quotes`, renovÃ¡vel a clique, exibe tÃ­tulo/autor/localizaÃ§Ã£o conforme tamanho do widget
- [ ] **Widget POMODORO no Dashboard** â€” Pomodoro standalone com duas visualizaÃ§Ãµes (relÃ³gio visual / relÃ³gio de areia); cor de acento das configuraÃ§Ãµes; independente do Planner

#### MÃ©dia prioridade (UI mais rica)
- [ ] **Mapa de Calor de Atividade** â€” grid estilo GitHub de horas estudadas por matÃ©ria/pÃ¡gina/tag (nÃ£o por pÃ¡ginas criadas; requer Pomodoro/time_sessions)
- [ ] **SumÃ¡rio do Dia** â€” briefing textual: eventos hoje, prazos prÃ³ximos, lembretes ativos

#### Futuros (dependem de features pendentes)
- [ ] **Meta de Leitura Anual** â€” gauge circular no Dashboard (base jÃ¡ feita: `readingGoals.progress()` disponÃ­vel)
- [ ] **Tempo de Foco Hoje** â€” sessÃµes Pomodoro do dia (depende de Pomodoro/`time_sessions`)
- [ ] **Grafo de ConexÃµes** â€” mini grafo de forÃ§a com pÃ¡ginas mais interligadas via backlinks (requer lib de visualizaÃ§Ã£o)

---

### Fase 50 â€” Futuro

- [ ] Exportar pÃ¡gina como PDF ou Markdown
- [ ] Pomodoro Timer completo com estatÃ­sticas (consolidar com aba Tempo do ProjectDashboard e Widget do Dashboard)
- [ ] Templates customizados de projeto
- [ ] IA: integraÃ§Ã£o com Ollama e APIs externas

---

### Design System â€” Efeitos Visuais (2026-04-10)

- [x] Vinheta sÃ©pia â€” body::before radial-gradient escurecendo bordas
- [x] Foxing â€” classe .foxing com manchas de envelhecimento nos cantos de cards
- [x] Marginalia â€” classe .marginalia-item com sÃ­mbolo âœ¦ no hover Ã  esquerda
- [x] Selo de cera â€” componente WaxSeal (aparecer em conclusÃ£o de item)
- [x] Luz de vela â€” componente CandleGlow com brilho radial pulsante no fundo
- [x] Loader alquÃ­mico â€” componente AlchemyLoader substituindo spinners

---

### Melhorias Futuras

- [x] Dashboard e pÃ¡gina inicial de projeto: melhorar layout, widgets personalizÃ¡veis por projeto, resumo de progresso, atividades recentes, acesso rÃ¡pido Ã s pÃ¡ginas mais relevantes â€” `ProjectLocalDashboard` com coluna de stats por tipo + grid de widgets customizÃ¡vel (add/remove, localStorage); toolbar com dropdown de vistas substituindo abas horizontais

---


## Melhorias baseadas em pesquisas para o ecossistema

### Pesquisa: RAG Auto-Aprendizagem, ReflexÃ£o de Conhecimento e Estado da Arte em Retrieval Aumentado

> **Contexto e motivaÃ§Ã£o:** O RAG convencional armazena fragmentos brutos do corpus e recupera por
> similaridade cosine. A literatura de 2024-2025 (Self-RAG, CRAG, RAPTOR, Knowledge Reflection,
> ITER-RETGEN) demonstra que sistemas que sintetizam, avaliam e refinam o prÃ³prio conhecimento
> superam em 5-27% o RAG vanilla nos principais benchmarks. As tÃ©cnicas abaixo foram selecionadas
> pelo critÃ©rio de viabilidade no hardware disponÃ­vel (sem fine-tuning de LLM, sem GPU obrigatÃ³ria).

#### Knowledge Reflection: sÃ­ntese ativa durante indexaÃ§Ã£o

> **Por que fazer:** RAG convencional responde mal a perguntas conceituais/abstratas (ex: "qual a
> visÃ£o geral sobre X?") porque recupera fragmentos textuais brutos, que raramente contÃªm sÃ­nteses
> explÃ­citas. Knowledge Reflection gera artefatos de sÃ­ntese no momento da indexaÃ§Ã£o â€” o LLM lÃª
> um conjunto de chunks relacionados e produz uma "reflexÃ£o" estruturada que jÃ¡ responde ao tipo de
> pergunta que humanos mais fazem. ReflexÃµes recebem boost de score (1.5Ã—) porque, ao serem
> recuperadas, entregam mais valor por token ao contexto do que fragmentos brutos.
>
> **Base cientÃ­fica:** FreeCodeCamp (2025), complementado por RAPTOR (Sarthi et al., Stanford, 2024)
> e MemGPT â€” que demonstram que representaÃ§Ãµes sintÃ©ticas hierÃ¡rquicas superam fragmentos brutos
> em benchmarks de compreensÃ£o de textos longos (+20 pp no QuALITY vs RAG vanilla).

- [x] `core/reflection.py` â€” criar mÃ³dulo de geraÃ§Ã£o de reflexÃµes:
  - `generate_reflection(chunks: list[Document], config: AppConfig) -> Document | None`
  - Prompt: *"VocÃª recebeu N fragmentos de texto sobre um mesmo tema. Sintetize os conceitos-chave,
    identifique conexÃµes nÃ£o-Ã³bvias e gere um artefato de conhecimento estruturado em 150-300 palavras."*
  - Retorna `Document` com `metadata["type"] = "reflection"`, `metadata["boost"] = 1.5`,
    `metadata["source_chunks"]` = lista de ids dos chunks de origem, `metadata["order"] = 1`
  - Retorna `None` se o LLM falhar (sem quebrar a indexaÃ§Ã£o)
  - **AtenÃ§Ã£o:** chamar LLM durante indexaÃ§Ã£o aumenta o tempo total. Estimar ~3-5s por grupo
    de chunks com modelo 7B. Emitir progresso na UI: "Gerando reflexÃ£o 3/12â€¦"

- [x] `core/indexer.py` â€” integrar geraÃ§Ã£o de reflexÃµes em `create_vectorstore()` e
  `update_vectorstore()`:
  - Agrupar chunks por arquivo-fonte (ou por tema via agrupamento de similaridade simples)
  - Para cada grupo com â‰¥ 3 chunks: chamar `generate_reflection()`
  - Se reflexÃ£o gerada: adicionÃ¡-la ao ChromaDB e ao BM25Index como documento extra
  - Guardar contador de reflexÃµes por tema em metadata da coleÃ§Ã£o (para trigger de meta-reflexÃ£o)

- [x] `core/reflection.py` â€” meta-reflexÃ£o (consolidaÃ§Ã£o de 3 em 1):
  - `maybe_consolidate(theme: str, config: AppConfig, vectorstore) -> Document | None`
  - Busca reflexÃµes de ordem 1 sobre o mesmo tema (by `metadata["theme"]` e `metadata["order"] == 1`)
  - Se â‰¥ 3 reflexÃµes encontradas: gera meta-reflexÃ£o (ordem 2) com boost 1.8Ã—
  - Remove as 3 reflexÃµes originais do vectorstore e BM25 (para nÃ£o duplicar)
  - Threshold de similaridade entre reflexÃµes para confirmar que sÃ£o do mesmo tema: cosine â‰¥ 0.65

- [x] `core/rag.py` â€” aplicar boost de reflexÃµes no retrieval:
  - ApÃ³s recuperaÃ§Ã£o hÃ­brida (BM25+dense), identificar documentos com `metadata["boost"]`
  - Multiplicar o score RRF pelo boost antes de ordenar: `score * doc.metadata.get("boost", 1.0)`
  - Filtro extra: reflexÃµes sÃ³ entram no contexto se cosine similarity com a query â‰¥ 0.65
    (evita reflexÃµes genÃ©ricas que foram recuperadas por acidente)
  - Testar: perguntas abstratas ("o que este corpus diz sobre X?") devem puxar reflexÃµes;
    perguntas especÃ­ficas ("qual o valor de Y na tabela Z?") devem puxar chunks brutos

- [x] `gui/main_window.py` â€” feedback de reflexÃµes na UI:
  - Badge na sidebar: "N reflexÃµes no Ã­ndice" (clicÃ¡vel para ver lista)
  - Durante indexaÃ§Ã£o com reflexÃµes: emitir progresso separado ("Gerando reflexÃµesâ€¦") apÃ³s
    o progresso de chunks, para nÃ£o confundir as duas fases

---

#### Retrieval iterativo com enriquecimento de query (ITER-RETGEN)

> **Por que fazer:** perguntas vagas ou mal formuladas produzem retrieval ruim porque a query
> original nÃ£o captura os termos que aparecem nos documentos relevantes. ITER-RETGEN (Shao et al.,
> 2023) mostrou que usar uma resposta provisÃ³ria do LLM como segunda query melhora recall em 5-12%
> â€” porque a geraÃ§Ã£o provisÃ³ria "traduz" a pergunta original para a linguagem do corpus.
> Custo: 1 chamada extra ao retriever (barato) + 1 chamada extra ao LLM (custosa). Tornar opcional.

- [x] `core/rag.py` â€” implementar retrieval em 2 iteraÃ§Ãµes como modo opcional:
  - ParÃ¢metro `iterative_retrieval: bool` em `prepare_ask()` (default: False)
  - **IteraÃ§Ã£o 1:** retrieval normal sobre a query original â†’ gerar resposta provisÃ³ria (curta,
    temperatura 0.0, sem streaming, instruÃ§Ã£o: "resposta em 1-2 frases, sem elaborar")
  - **IteraÃ§Ã£o 2:** usar resposta provisÃ³ria como query adicional â†’ recuperar N/2 chunks extras
    (sem duplicar os jÃ¡ recuperados na iteraÃ§Ã£o 1)
  - **SÃ­ntese:** combinar chunks da iteraÃ§Ã£o 1 e 2 (deduplicados por `page_content[:100]`),
    limitar ao total configurado (k), passar ao LLM para resposta final
  - **Quando ativar:** perguntas curtas (< 10 palavras) ou vagas se beneficiam mais; perguntas
    especÃ­ficas com termos tÃ©cnicos se beneficiam menos. Deixar como toggle manual na UI.

- [x] `core/config.py` â€” campo `iterative_retrieval_enabled: bool = False`

- [x] `gui/main_window.py` â€” toggle "Busca iterativa" na aba Perguntar (desativado por padrÃ£o),
  com tooltip: "Faz duas rodadas de busca â€” melhora recall em perguntas vagas (+~8% accuracy),
  mas dobra o tempo de resposta"

---

#### AvaliaÃ§Ã£o automatizada do pipeline (RAGAS)

> **Por que fazer:** as otimizaÃ§Ãµes das Fases 8, 9, 10, 11.1 e 11.2 mudam o pipeline de formas
> que podem melhorar uma mÃ©trica e piorar outra. Sem avaliaÃ§Ã£o objetiva, Ã© impossÃ­vel saber se
> uma mudanÃ§a foi realmente positiva. RAGAS (Es et al., 2023) define 4 mÃ©tricas computÃ¡veis via
> LLM sem ground truth manual: Faithfulness (a resposta Ã© suportada pelos documentos?),
> Answer Relevancy (a resposta Ã© relevante Ã  pergunta?), Context Precision (documentos recuperados
> sÃ£o realmente Ãºteis?) e Context Recall (informaÃ§Ã£o necessÃ¡ria estava nos documentos?).
>
> **Uso pretendido:** script standalone, fora do app, rodado manualmente antes/depois de cada
> mudanÃ§a de pipeline para medir impacto real. NÃ£o Ã© funcionalidade do app em si.

- [ ] `eval/ragas_eval.py` â€” script de avaliaÃ§Ã£o standalone:
  - 20-30 perguntas de teste cobrindo os principais tipos de query do Mnemosyne
    (factuais, conceituais, multi-hop, vagas) â€” criar `eval/questions.json`
  - Para cada pergunta: rodar `prepare_ask()` com o pipeline atual; capturar chunks recuperados
    e resposta gerada
  - Calcular mÃ©tricas RAGAS usando Ollama como juiz (modelo configurÃ¡vel, sugestÃ£o: qwen2.5:7b)
  - Exportar relatÃ³rio em `eval/results_YYYY-MM-DD.json` para comparaÃ§Ã£o entre versÃµes
  - **Rodar como baseline ANTES de implementar 11.1 e 11.2**, depois rodar novamente para medir
    o impacto de cada mudanÃ§a

- [ ] `eval/questions.json` â€” 20 perguntas de teste com resposta esperada (ground truth manual):
  - 5 perguntas factuais simples (a resposta estÃ¡ explÃ­cita num Ãºnico chunk)
  - 5 perguntas conceituais (requerem sÃ­ntese de mÃºltiplos chunks)
  - 5 perguntas vagas (beneficiadas por retrieval iterativo)
  - 5 perguntas multi-hop (requerem raciocÃ­nio encadeado)

---

#### Pesquisas pendentes (RAG avanÃ§ado, longo prazo)

> Itens abaixo requerem pesquisa adicional antes de qualquer decisÃ£o de implementaÃ§Ã£o.
> NÃ£o implementar sem ordem explÃ­cita.

- [ ] **Pesquisar CRAG para o Mnemosyne:** avaliar custo de rodar o evaluator T5-large
  (770M params) no hardware disponÃ­vel. No CachyOS (RX 6600): possÃ­vel em VRAM (770M Q4 â‰ˆ 400 MB).
  No Windows 10 (i5-3470, sem GPU): inviÃ¡vel em tempo real (+150-300ms/query em CPU puro sem AVX2).
  Pesquisar se existe versÃ£o menor (T5-small, 60M) com qualidade aceitÃ¡vel. Registrar resultado
  no `pesquisas.md`.

- [ ] **Pesquisar RAPTOR para corpora com documentos longos:** RAPTOR Ã© relevante quando o corpus
  inclui livros inteiros ou textos muito longos (> 50 pÃ¡ginas). A indexaÃ§Ã£o RAPTOR requer LLM de
  boa qualidade para sumarizaÃ§Ã£o de clusters â€” viÃ¡vel com Llama 3.2 3B ou Qwen2.5 7B no CachyOS.
  Investigar custo de indexaÃ§Ã£o em corpus de 100 documentos mÃ©dios e overhead de armazenamento.
  InviÃ¡vel no i5-3470.

- [ ] **Pesquisar GraphRAG leve (LightRAG) para corpus relacional:** relevante quando o corpus
  tem muitas relaÃ§Ãµes entre entidades (ex: vault Obsidian com wikilinks densos). LightRAG Ã© menos
  custoso que GraphRAG da Microsoft, mas ainda requer extraÃ§Ã£o de entidades via LLM. Investigar
  viabilidade com modelos 7-8B no CachyOS. Registrar no `pesquisas.md`.


### Pesquisa: Arquitetura de UI para Research Workbench â€” NotebookLM e ReferÃªncias | 2026-05-06
> Contexto: pesquisa sobre o paradigma tri-pane (Sources / Chat / Workspace), citation anchoring,
> gerenciamento de estado entre painÃ©is em Qt, padrÃ£o fleeting/permanent notes e referÃªncias
> alternativas (Zotero 7, Logseq, AnythingLLM). Base para o redesign completo do Mnemosyne.

#### Mnemosyne
- [x] **Layout tri-pane com QSplitter aninhados** (`gui/main_window.py`). Substituir o layout
  atual por trÃªs painÃ©is horizontais via `QSplitter` aninhados: (1) painel esquerdo de fontes
  e coleÃ§Ãµes (proporÃ§Ã£o 25%), (2) painel central de chat RAG (50%), (3) painel direito de
  notas persistentes (25%). Salvar e restaurar proporÃ§Ãµes entre sessÃµes via `QSettings` com
  `QSplitter.saveState()` e `restoreState()`. O painel esquerdo lista coleÃ§Ãµes e seus
  documentos; o central Ã© a interface de chat com o LLM; o direito Ã© uma Ã¡rea editÃ¡vel onde
  respostas podem ser salvas como notas permanentes. Esta Ã© a estrutura base sobre a qual
  todos os outros itens desta sessÃ£o se constroem.

- [x] **`AppState` central como `QObject` com signals tipados** (`gui/app_state.py`, novo
  arquivo). Criar um objeto de estado compartilhado â€” padrÃ£o documentado no JabRef â€” que todos
  os painÃ©is recebem na construÃ§Ã£o mas nunca referenciam diretamente entre si. Signals
  obrigatÃ³rios: `source_selected(collection_id: str, doc_id: str)`,
  `chunk_cited(collection_id: str, doc_path: str, start_char: int, end_char: int)`,
  `note_promoted(text: str, citations: list[dict])`, `query_submitted(text: str)`,
  `response_token_received(token: str)`. Cada painel conecta apenas os signals relevantes
  para si. Isso elimina o problema atual de widgets que se referenciam diretamente e quebram
  quando o layout muda.

- [x] **Metadados de chunk enriquecidos com offsets de texto** (`core/indexer.py`). Ao chunkar
  documentos e inserir no ChromaDB, adicionar aos metadados de cada chunk: `start_char` (int),
  `end_char` (int), `prefix_quote` (string: 30 chars antes do chunk para desambiguaÃ§Ã£o),
  `suffix_quote` (string: 30 chars depois), `page_num` (int, quando disponÃ­vel â€” PDFs).
  Esses campos sÃ£o o prÃ©-requisito para citation anchoring funcionar. PadrÃ£o documentado pelo
  Hypothes.is: trÃªs seletores redundantes garantem que a Ã¢ncora sobreviva a pequenas
  modificaÃ§Ãµes no documento. Requer re-indexaÃ§Ã£o completa apÃ³s implementaÃ§Ã£o.

- [x] **Citation anchoring via `QTextCursor`** (`gui/main_window.py` ou novo
  `gui/source_viewer.py`). Quando o chat retorna uma resposta com citaÃ§Ã£o, emitir
  `AppState.chunk_cited(collection_id, doc_path, start_char, end_char)`. O painel de fontes
  captura o signal, carrega o documento no `QTextBrowser` (se nÃ£o estiver aberto), cria um
  `QTextCursor`, chama `cursor.setPosition(start_char)` seguido de
  `cursor.setPosition(end_char, QTextCursor.KeepAnchor)`, aplica `QTextCharFormat` com
  `background = QColor("#F5C518")` (amarelo suave compatÃ­vel com o tema sÃ©pia), e chama
  `source_browser.setTextCursor(cursor)` + `source_browser.ensureCursorVisible()`. Resultado:
  clicar em `[1]` na resposta do chat rola automaticamente o painel de fontes atÃ© o trecho
  exato usado pelo LLM â€” funcionalidade ausente em todos os apps RAG open source atuais.

- [x] **Painel de fontes com status de indexaÃ§Ã£o por item** (`gui/main_window.py` ou
  `gui/collection_panel.py`). No painel esquerdo, cada documento na `QListWidget` deve exibir
  seu status de indexaÃ§Ã£o via delegate customizado (`QStyledItemDelegate`). Estados possÃ­veis:
  `pending` (cinza, Ã­cone de relÃ³gio), `indexing` (animaÃ§Ã£o de spinner via `QTimer`),
  `indexed` (verde, Ã­cone de check), `error` (vermelho, Ã­cone de exclamaÃ§Ã£o). O delegate
  lÃª o status do item via `Qt.UserRole` e renderiza o Ã­cone/cor apropriado no mÃ©todo
  `paint()`. Permite que o usuÃ¡rio veja em tempo real quais documentos jÃ¡ estÃ£o disponÃ­veis
  para RAG â€” atualmente nÃ£o hÃ¡ feedback visual por documento, apenas por coleÃ§Ã£o inteira.

- [x] **Botão "Salvar como Nota" em cada resposta do chat** (`gui/chat_widget.py` ou equivalente).
  Cada bloco de resposta do LLM no painel de chat deve ter um botÃ£o discreto (Ã­cone de
  marcador, canto superior direito do card de resposta) que, ao ser clicado, promove o
  conteÃºdo para o painel de notas com: tÃ­tulo editÃ¡vel prÃ©-preenchido com os primeiros
  60 chars da resposta, conteÃºdo completo em Markdown, e lista de citaÃ§Ãµes associadas
  preservadas como metadados. A promoÃ§Ã£o Ã© explÃ­cita (nÃ£o auto-save) e reversÃ­vel (botÃ£o
  "Remover nota" no painel direito). PadrÃ£o documentado no Zettelkasten/Logseq: a nota
  efÃªmera vira permanente sÃ³ por aÃ§Ã£o deliberada do usuÃ¡rio.

- [x] **Distinção visual entre rascunho e nota permanente + histÃ³rico de revisÃ£o simples**
  (`gui/notes_panel.py` ou equivalente). No painel de notas direito: notas salvas usam
  `QTextEdit` com `QTextDocument.setMarkdown()` para ediÃ§Ã£o direta em Markdown (Qt 6.x tem
  suporte nativo). Distinguir visualmente notas confirmadas (borda verde sutil, fundo sÃ©pia
  normal) de rascunhos nÃ£o confirmados (borda tracejada, fundo levemente diferente). Cada
  nota deve manter um histÃ³rico simples de revisÃµes (lista de strings com timestamp) para
  undo bÃ¡sico. Persistir notas em `{vault_dir}/notes/YYYY-MM-DD_HH-MM.md` com frontmatter
  YAML contendo `created_at`, `sources`, `citations`.

- [x] **Sidebar direito dinÃ¢mico para contexto paralelo** (`gui/main_window.py`). Adicionar
  a capacidade de abrir qualquer documento do painel esquerdo em um "painel de contexto
  paralelo" dentro do sidebar direito sem fechar o painel de notas â€” padrÃ£o documentado no
  Logseq. ImplementaÃ§Ã£o: o painel direito usa um `QTabWidget` ou `QStackedWidget` com abas
  "Notas" e "Fonte: [nome]". Ao clicar em "Abrir ao lado" num documento, uma nova aba abre
  com `QTextBrowser` mostrando o conteÃºdo do arquivo. Ãštil quando o usuÃ¡rio quer consultar
  dois documentos em paralelo durante uma sessÃ£o de pesquisa sem perder o chat central.

- [x] **Streaming de resposta do Ollama via `QThread` com signal por token**
  (`core/rag.py`, `gui/workers.py`). Encapsular a chamada ao Ollama (ou LangChain) em um
  `QThread` que emite `response_token_received(str)` para cada token recebido via streaming.
  O painel de chat conecta esse signal a um slot que appenda o token ao `QTextBrowser` atual
  sem bloquear o event loop do Qt. Resultado: a resposta aparece progressivamente na UI,
  token por token, como no ChatGPT â€” elimina a espera silenciosa atual onde a UI trava atÃ©
  a resposta completa chegar. Verificar se `core/rag.py` jÃ¡ tem suporte a streaming no
  LangChain (`stream=True` na chain); se sim, o trabalho Ã© principalmente no side da UI.

- [x] **`QTextEdit` com Markdown nativo para notas; `QTextBrowser` para chat**
  (`gui/notes_panel.py`, `gui/chat_widget.py`). Usar widgets distintos para contextos
  distintos: `QTextBrowser` (read-only, suporta HTML e links clicÃ¡veis) para o histÃ³rico
  de chat e visualizaÃ§Ã£o de fontes; `QTextEdit` com `document().setMarkdown(text)` e
  `toMarkdown()` para o painel de notas onde o usuÃ¡rio edita. O Qt 6.x implementa
  `QTextDocument.setMarkdown()` e `toMarkdown()` nativamente â€” nÃ£o requer biblioteca
  externa de parsing. Verificar versÃ£o mÃ­nima do PySide6 no `pyproject.toml` do Mnemosyne
  para garantir Qt 6.4+ (onde suporte Markdown Ã© estÃ¡vel).

---

### Pesquisa: Whisper sem AVX2 â€” faster-whisper como backend local | 2026-05-05
> Contexto: openai-whisper usa PyTorch 2.x que exige AVX2 no Windows (WinError 1114).
> O i5-3470 tem AVX e SSE4.1 mas nÃ£o AVX2. faster-whisper usa CTranslate2 com
> dispatch dinÃ¢mico de ISA (AVX2 â†’ AVX â†’ SSE4.1), roda sem compilaÃ§Ã£o e Ã© mais
> rÃ¡pido que openai-whisper mesmo em CPU antiga. Substitui o backend atual do Hermes.

#### Hermes
- [x] **Substituir openai-whisper por faster-whisper** nos workers `TranscribeWorker` e
  `BatchTranscribeWorker` (`Hermes/hermes.py`). Instalar `faster-whisper` no `.venv`.
  Adaptar a API: `WhisperModel("base", device="cpu", compute_type="int8")`;
  `model.transcribe()` retorna `(segments_generator, info)` â€” o texto Ã©
  `" ".join(seg.text.strip() for seg in segments)`. Usar `vad_filter=True` para
  acelerar vÃ­deos com silÃªncio. Remover `openai-whisper` e `torch` do `.venv` apÃ³s
  migraÃ§Ã£o (libera ~3 GB de espaÃ§o no Windows).

### Pesquisa: Understand-Anything â€” PadrÃµes de Grafo de Conhecimento | 2026-05-04
> Contexto: AnÃ¡lise do projeto github.com/Lum1104/Understand-Anything revelou padrÃµes
> arquiteturais aplicÃ¡veis ao ecossistema â€” tipagem de nÃ³s, indexaÃ§Ã£o incremental
> por nÃ­vel de impacto, e pipeline multi-agente com prompts declarativos.
> Os pontos 2 (grafo) e 6 (separaÃ§Ã£o embedding/busca) se sobrepÃµem com itens jÃ¡
> existentes na Fase 11.3 do Mnemosyne (GraphRAG/LightRAG) â€” ver nota em cada item.

#### Mnemosyne
- [x] **ClassificaÃ§Ã£o de chunks por tipo de nÃ³ durante indexaÃ§Ã£o** (`core/indexer.py`,
  `core/config.py`, `core/rag.py`). Adicionar metadado `node_type` a cada chunk com
  valores possÃ­veis: `article` (texto corrido), `entity` (pessoa/lugar/objeto nomeado),
  `topic` (tema recorrente), `claim` (afirmaÃ§Ã£o factual), `source` (referÃªncia externa).
  ImplementaÃ§Ã£o: chamada LLM leve (< 3B, ex: Qwen2.5-1.5B) classifica o chunk no momento
  da indexaÃ§Ã£o; resultado salvo em `metadata["node_type"]` no ChromaDB. No retrieval,
  aceitar filtro opcional `node_types: list[str]` em `prepare_ask()` para restringir busca.
  Exemplo de uso: `?node_types=claim` sÃ³ busca afirmaÃ§Ãµes factuais â€” reduz ruÃ­do semÃ¢ntico
  em perguntas como "o que eu afirmo sobre X?". Requer `iterative_retrieval_enabled` jÃ¡
  implementado na Fase 11.2 para nÃ£o duplicar infra de LLM local.

- [x] **IndexaÃ§Ã£o incremental em 4 nÃ­veis** (`core/indexer.py`). Substituir a detecÃ§Ã£o
  binÃ¡ria (hash mudou â†’ re-indexa tudo) por 4 nÃ­veis inspirados no FingerprintEngine do
  Understand-Anything: NONE (nenhuma mudanÃ§a), COSMETIC (espaÃ§os/formataÃ§Ã£o â€” hash de
  texto normalizado igual), STRUCTURAL (conteÃºdo semÃ¢ntico alterado â€” re-indexa sÃ³ chunks
  afetados), FULL (arquivo novo ou removido). ImplementaÃ§Ã£o: salvar hash por chunk
  (nÃ£o sÃ³ por arquivo) em `core/indexer.py`. Na re-indexaÃ§Ã£o, comparar chunk por chunk:
  sÃ³ recalcula embedding e re-insere no ChromaDB os chunks que mudaram semanticamente.
  BenefÃ­cio crÃ­tico no i5-3470 (sem AVX2): corrigir typos nÃ£o re-indexa 500 chunks.
  Armazenar hashes em `{chroma_dir}/.chunk_hashes.json` ou em tabela SQLite auxiliar.

#### HUB (LOGOS)
- [x] **ReferÃªncia arquitetural: pipeline multi-agente via prompts .md** (pesquisa, nÃ£o
  implementaÃ§Ã£o imediata). O Understand-Anything orquestra 5 subagentes em paralelo onde
  cada "habilidade" Ã© um arquivo `.md` de prompt â€” adicionar nova capacidade = criar novo
  arquivo, sem alterar cÃ³digo. Aplicar ao LOGOS: cada tipo de tarefa (RAG query, sÃ­ntese,
  extraÃ§Ã£o de entidades) seria um arquivo `logos/skills/<skill>.md`. O dispatcher lÃª o
  tipo de request e escolhe o skill. Pesquisar viabilidade com `Qwen2.5-7B` no CachyOS
  (modelo suficientemente capaz para seguir prompts estruturados). Registrar resultado
  em `pesquisas.md` antes de implementar.

---

### Pesquisa: Assistente de Pesquisa Inteligente â€” LLM-Augmented Search e Query Understanding | 2026-05-06
> Contexto: pesquisa sobre como transformar o AKASHA de buscador pessoal em assistente de
> pesquisa com LLM local. Cobre arquitetura de sistemas como Perplexity AI e Kagi Assistant,
> query understanding (classificaÃ§Ã£o de intenÃ§Ã£o, expansÃ£o HyDE, reescrita conversacional),
> sÃ­ntese multi-documento Map-Reduce, e latÃªncia de inferÃªncia local com Ollama na RX 6600.

#### AKASHA
- [ ] **Classificador de intenÃ§Ã£o leve antes do pipeline de busca** (`routers/search.py` ou
  `services/query_understanding.py`). Antes de executar busca, chamar Ollama (modelo 3B, ex:
  Qwen2.5-3B) com prompt minimal para classificar a query em trÃªs tipos:
  `fact-seeking` (resposta direta com citaÃ§Ã£o), `exploratory` (sÃ­ntese temÃ¡tica multi-doc),
  `navigational` (link direto sem sÃ­ntese). Cada tipo ativa um pipeline diferente:
  fact-seeking â†’ busca FTS5 + resposta grounded; exploratory â†’ Map-Reduce + sÃ­ntese;
  navigational â†’ resultado top-1. LatÃªncia do classificador: ~200ms com 3B Q4.

- [ ] **ExpansÃ£o HyDE para busca vetorial no ChromaDB/Mnemosyne** (`services/local_search.py`,
  `_search_chroma()`). Ao chamar ChromaDB com a query, gerar primeiro um "documento hipotÃ©tico"
  via Ollama (`"Escreva um parÃ¡grafo que responderia a: {query}"`), usar o embedding do
  documento hipotÃ©tico como query vector em vez do embedding direto da query.
  Ganho documentado: +38% em nDCG@10 sobre embedding direto de query (HyDE, SIGIR 2023).
  Custo: uma call Ollama extra de ~500ms. Ativar sÃ³ quando mnemosyne estÃ¡ disponÃ­vel.

- [ ] **Template MUST+SHOULD para expansÃ£o de query no FTS5** (`services/local_search.py`,
  `_search_fts()`). Ao expandir query com LLM (apÃ³s HyDE ou classificaÃ§Ã£o), estruturar
  a query FTS5 como: `query_original MUST_NEAR termos_expandidos` ou usar duas buscas:
  (1) FTS5 com query original; (2) FTS5 com termos expandidos pelo LLM. Combinar com RRF.
  PadrÃ£o evita "query drift" onde expansÃ£o LLM retorna documentos irrelevantes que substituem
  os relevantes. A query original permanece Ã¢ncora; expansÃ£o sÃ³ adiciona recall.

- [ ] **Reescrita de query conversacional por turno** (`routers/search.py`, `services/search_session.py`).
  Ao detectar anÃ¡fora na query ("isso", "esse assunto", "ele", pronomes relativos) ou query
  muito curta (< 3 tokens) em sessÃ£o ativa, chamar Ollama para reescrever como query autÃ´noma
  usando o contexto dos Ãºltimos K turnos. Prompt: `"Reescreva como busca independente: '{query}'.
  Contexto recente: {Ãºltimas queries}."` Exibir a query reescrita na UI (transparÃªncia).
  Implementar sem fine-tuning â€” LLMs 7B few-shot superam modelos ConvDR treinados em CANARD.

- [ ] **DetecÃ§Ã£o de sessÃ£o de pesquisa** (`services/search_session.py`). Agrupar queries
  consecutivas em sessÃ£o se: gap temporal < 30 minutos E similaridade de embedding entre
  queries > 0.65. Manter estado de sessÃ£o em memÃ³ria do processo FastAPI (dict por IP/cookie).
  SessÃ£o acumula: queries anteriores (Ãºltimas K), documentos recuperados, entidades extraÃ­das.
  Exibir na UI um badge "SessÃ£o ativa: N queries" com botÃ£o para limpar. A sessÃ£o Ã© o contexto
  para reescrita de query e para sÃ­ntese final.

- [ ] **Pipeline Map-Reduce para sÃ­ntese de resultados** (`services/synthesis.py`).
  Para queries `exploratory`: (1) Map â€” chamar Ollama para sumarizar cada um dos top-5
  documentos recuperados em 2â€“3 frases, com ID de fonte; (2) Reduce â€” chamar Ollama para
  sintetizar os 5 sumÃ¡rios em resposta coerente com marcadores de citaÃ§Ã£o `[1]...[5]`.
  Exibir na UI como bloco colapsÃ¡vel "SÃ­ntese assistida" acima dos cards normais.
  LatÃªncia total com Qwen2.5-7B Q4_K_M na RX 6600: ~4â€“8 segundos. Streaming obrigatÃ³rio.
  Ativar via checkbox "SÃ­ntese" na interface â€” nÃ£o obrigatÃ³rio para todas as buscas.

- [ ] **CitaÃ§Ãµes inline com verificaÃ§Ã£o bÃ¡sica** (`services/synthesis.py`). ApÃ³s gerar sÃ­ntese
  Map-Reduce, verificar cada citaÃ§Ã£o `[N]`: extrair a afirmaÃ§Ã£o adjacente ao marcador,
  checar overlap de unigrams com o documento-fonte citado (threshold: â‰¥ 2 termos comuns).
  Se overlap zero: marcar citaÃ§Ã£o como `[N?]` na UI com tooltip "CitaÃ§Ã£o nÃ£o verificada".
  Mecanismo leve, sem modelo NLI â€” evita os 57% de post-rationalized citations documentados
  na literatura (WHYAITECH, 2025). Custo: string matching puro, < 5ms.

- [ ] **`keep_alive=-1` no cliente Ollama durante sessÃ£o ativa** (`services/synthesis.py`
  ou `services/query_understanding.py`). Ao iniciar uma sessÃ£o de pesquisa (primeira query
  classificada como nÃ£o-navigational), chamar `/api/generate` ou `/api/chat` com
  `keep_alive: -1` (manter modelo em VRAM indefinidamente). Ao encerrar sessÃ£o (timeout
  30min ou botÃ£o "Encerrar sessÃ£o"): chamar com `keep_alive: 0` para liberar VRAM.
  Elimina cold-start de 2â€“5 segundos por query na RX 6600. Custo de manter 7B Q4_K_M:
  ~4 GB VRAM ocupados â€” aceitÃ¡vel se o usuÃ¡rio estÃ¡ em sessÃ£o ativa.

- [ ] **Leituras relacionadas derivadas dos resultados** (`routers/search.py`, template
  `search.html`). ApÃ³s retornar resultados top-K, extrair as 3â€“5 entidades mais salientes
  (TF-IDF sobre os snippets recuperados vs. o corpus crawleado) e executar buscas FTS5
  silenciosas adicionais. Exibir na UI uma seÃ§Ã£o "Explorar tambÃ©m:" com cards compactos
  dos documentos adicionais encontrados. Sem chamada LLM â€” puramente textual, latÃªncia
  < 100ms. ImplementaÃ§Ã£o: funÃ§Ã£o `suggest_related(snippets, fts_conn, n=5)` em
  `services/local_search.py`.

### Pesquisa: IntegraÃ§Ã£o KOSMOS-AKASHA â€” PadrÃµes RSS Reader + Web Archiver | 2026-05-04
> Contexto: Pesquisa sobre padrÃµes de integraÃ§Ã£o entre leitores RSS e arquivadores web
> (FreshRSS+Wallabag, Miniflux+integraÃ§Ãµes, ArchiveBox). Objetivo: interligar KOSMOS
> e AKASHA especialmente nas funÃ§Ãµes de crawling e indexaÃ§Ã£o, evitando duplicaÃ§Ã£o
> e aproveitando ecosystem_scraper.py jÃ¡ compartilhado.

#### KOSMOS
- [ ] **BotÃ£o "Arquivar no AKASHA" no leitor de artigos** (`app/ui/views/reader_view.py`
  ou `app/ui/views/article_view.py`). PadrÃ£o FreshRSS+Wallabag: ao clicar, envia
  `POST http://localhost:7071/archive` com `url=<url_do_artigo>` (AKASHA jÃ¡ ouve na
  porta 7071). AKASHA faz fetch completo e salva na biblioteca. PrÃ©-requisito: AKASHA
  precisa ter esse endpoint â€” ver item correspondente em AKASHA abaixo.
  Mostrar toast "Arquivado no AKASHA" ao receber 200.
  Mostrar erro "AKASHA offline" ao receber falha de conexÃ£o (nÃ£o bloquear leitura).

- [ ] **Auto-arquivar ao salvar artigo** (`app/ui/main_window.py` ou
  `app/ui/views/unified_feed_view.py`). PadrÃ£o Miniflux automations: quando o usuÃ¡rio
  clica em "Salvar" (bookmark) no artigo, enviar a URL automaticamente para AKASHA em
  background (fire-and-forget, sem bloquear UI). Adicionar opÃ§Ã£o `auto_archive_on_save`
  em `app/utils/config.py` (default: False). Na aÃ§Ã£o de salvar, se configurado, fazer
  `requests.post("http://localhost:7071/archive", data={"url": url}, timeout=3)` em
  thread separada.

- [ ] **Busca unificada KOSMOS + AKASHA** (`app/ui/views/unified_feed_view.py` ou novo
  `SearchView`). Ao pesquisar no KOSMOS, consultar tambÃ©m `GET http://localhost:7071/
  search?q=<termo>` (AKASHA FTS5) e mesclar resultados com indicador de fonte (RSS vs
  AKASHA). Evita abrir dois apps para pesquisar conteÃºdo relacionado.

#### AKASHA
- [ ] **Endpoint `POST /archive` para receber URLs de outros apps** (`routers/crawler.py`
  ou novo `routers/archive_api.py`). Recebe `{"url": "...", "tags": [...], "notes": ""}`,
  chama `archive_url()` existente, retorna `{"status": "ok", "path": "..."}`.
  AutenticaÃ§Ã£o: nenhuma (local-only, 127.0.0.1). Documentar no `CLAUDE.md` como contrato
  de API. O KOSMOS e potencialmente outros apps do ecossistema usarÃ£o esse endpoint.

- [ ] **Crawling incremental a partir dos feeds do KOSMOS** (`services/crawler.py` ou
  novo `services/feed_crawler.py`). PadrÃ£o ArchiveBox: ao adicionar um feed ao KOSMOS,
  notificar AKASHA (via `POST /add-source`) com o domÃ­nio raiz para crawl periÃ³dico.
  AKASHA adiciona o domÃ­nio Ã  lista de sites monitorados. ImplementaÃ§Ã£o: KOSMOS lÃª
  `akasha.base_url` do ecosystem.json; ao criar feed, faz `POST /add-source?url=<domÃ­nio>
  &name=<nome_feed>`. Evita que artigos de domÃ­nios monitorados existam sÃ³ como resumo
  RSS â€” a versÃ£o completa fica no AKASHA.

- [ ] **DeduplicaÃ§Ã£o entre arquivo AKASHA e artigos KOSMOS** (`services/library.py`).
  Ao arquivar uma URL que jÃ¡ existe no archive do KOSMOS (`kosmos.archive_path`), criar
  symlink ou registro cruzado em vez de duplicar. Consultar `kosmos.archive_path` do
  ecosystem.json. Verificar por URL normalizada (remover parÃ¢metros de rastreamento
  `utm_*`). Se jÃ¡ arquivado pelo KOSMOS, retornar o path existente em vez de re-arquivar.

### Pesquisa: Motores de Busca Pessoais, Ranking de RelevÃ¢ncia e Busca HÃ­brida | 2026-05-04
> Contexto: pesquisa exaustiva sobre SQLite FTS5, ranking alÃ©m de BM25, motores self-hosted,
> APIs de artigos cientÃ­ficos, extraÃ§Ã£o de snippets, busca hÃ­brida FTS5+vetor, query understanding
> e deduplicaÃ§Ã£o near-duplicate â€” tudo aplicado ao AKASHA (FastAPI + SQLite FTS5 + ChromaDB).

#### AKASHA
- [x] **Configurar pesos de coluna BM25 persistentes via `INSERT INTO tabela(tabela, rank)`**
  (`database.py` ou funÃ§Ã£o de inicializaÃ§Ã£o do DB). Atualmente os pesos sÃ£o passados
  explicitamente em cada query (ex: `bm25(local_fts, 0, 10, 1, 0)`). Usar a configuraÃ§Ã£o
  persistente do FTS5: `INSERT INTO local_fts(local_fts, rank) VALUES('rank', 'bm25(0, 10.0, 1.0, 0)')`
  na criaÃ§Ã£o da tabela. Isso permite usar `ORDER BY rank` em vez de repetir os pesos em
  cada query, e facilita ajuste de pesos sem alterar cÃ³digo de busca.

- [x] **Implementar snippets por parÃ¡grafo como alternativa ao snippet() FTS5**
  (`services/local_search.py`). A funÃ§Ã£o snippet() FTS5 Ã© limitada a 64 tokens e usa
  heurÃ­stica simples. Para resultados de melhor qualidade: dividir o body do documento
  em parÃ¡grafos, aplicar BM25 (bm25s ou rank_bm25) para rankear parÃ¡grafos contra a query,
  retornar o parÃ¡grafo mais relevante como snippet. Implementar como opÃ§Ã£o configurÃ¡vel
  (snippet_mode: 'fts5' | 'paragraph_bm25'). DependÃªncia: pip install bm25s.

- [x] **Adicionar suporte a prefix queries e phrase queries na sanitizaÃ§Ã£o FTS5**
  (`services/local_search.py`, funÃ§Ã£o `_sanitize_fts`). Atualmente `_sanitize_fts()` remove
  `*` e `"` da query, perdendo prefix queries (ex: "searc*") e phrase queries (ex: `"machine
  learning"`). Melhorar sanitizaÃ§Ã£o para: (a) manter aspas duplas vÃ¡lidas (phrase), (b) manter
  asterisco no final de tokens (prefix), (c) remover apenas chars que causam erros de sintaxe
  FTS5. Adicionar detecÃ§Ã£o de intenÃ§Ã£o: se query contÃ©m aspas, tratÃ¡-la como phrase query.

- [x] **Configurar tokenizer unicode61 com remove_diacritics 2 nas tabelas FTS5**
  (`database.py` na criaÃ§Ã£o das tabelas). Atualmente as tabelas FTS5 usam o tokenizer padrÃ£o.
  Adicionar `tokenize='unicode61 remove_diacritics 2'` na criaÃ§Ã£o de local_fts e library_fts.
  Isso garante que buscar "pagina" encontre "pÃ¡gina", "cafe" encontre "cafÃ©", etc.
  Melhoria de recall para PT+EN sem custo adicional.

- [x] **Implementar RRF (Reciprocal Rank Fusion) entre FTS5 e ChromaDB**
  (`services/local_search.py`, funÃ§Ã£o `rank_combined`). O `rank_combined()` atual usa
  re-scoring simples por contagem de termos. Substituir por RRF: (1) FTS5 retorna lista
  ranqueada por BM25; (2) ChromaDB retorna lista por cosine similarity; (3) RRF combina
  com fÃ³rmula `score += 1.0 / (60 + rank)`. Resultado: documentos que aparecem em ambos
  os sistemas sobem no ranking sem precisar normalizar scores incompatÃ­veis.
  ImplementaÃ§Ã£o: ~15 linhas de Python. Nenhuma nova dependÃªncia.

- [x] **Adicionar detecÃ§Ã£o de idioma + stemming PT/EN na query antes do FTS5**
  (`services/local_search.py`). Integrar langdetect (pip install langdetect) para detectar
  idioma da query. Se PT: aplicar NLTK RSLPStemmer ou SnowballStemmer("portuguese"). Se EN:
  aplicar SnowballStemmer("english"). Expandir query FTS5 com stems via OR: ex, "buscando" â†’
  `(buscando OR busc*)`. Melhorar recall especialmente para queries PT onde conteÃºdo pode
  estar em diferentes formas morfolÃ³gicas. AtenÃ§Ã£o: unicode61 remove_diacritics jÃ¡ cobre
  variaÃ§Ãµes de acento â€” stemming Ã© complementar.

- [x] **Implementar deduplicaÃ§Ã£o near-duplicate via SimHash no archiver**
  (`services/archiver.py` ou `services/library.py`). Ao arquivar nova URL, calcular SimHash
  do texto extraÃ­do (pip install simhash). Comparar com SimHashes de documentos jÃ¡ indexados
  armazenados em coluna da tabela de metadados (distÃ¢ncia Hamming â‰¤ 3 â†’ near-duplicate).
  Se near-duplicate detectado: nÃ£o arquivar; retornar URL do documento existente.
  TambÃ©m normalizar URL antes de inserir (pip install url-normalize) para deduplicaÃ§Ã£o
  de URLs equivalentes (tracking params, HTTPâ†’HTTPS, trailing slash).

- [x] **Re-ranking cross-encoder para top-K resultados de busca**
  (`services/local_search.py`). ApÃ³s FTS5 retornar resultados, aplicar re-ranking com
  FlashRank (pip install flashrank) nos top-20 resultados. FlashRank usa modelos embutidos
  (~4MB) e funciona puramente em CPU sem GPU. LatÃªncia estimada: ~200ms para 20 docs
  em CPU tÃ­pico â€” aceitÃ¡vel para busca local. Implementar como opcional (reranking_enabled
  em config): usuario pode desativar se latÃªncia for problema. Maior ganho para queries
  ambÃ­guas onde BM25 retorna muitos falsos positivos.

- [x] **sqlite-vec: adicionar busca vetorial nativa no mesmo arquivo .db do FTS5**
  (`database.py`, `services/local_search.py`). Instalar pip install sqlite-vec. Criar
  virtual table `vec_items(rowid, embedding FLOAT[384])` no mesmo arquivo akasha.db.
  No archiver, ao indexar documento, gerar embedding (modelo leve, ex: all-MiniLM-L6-v2
  via sentence-transformers) e inserir em vec_items. Na busca, combinar FTS5 BM25 +
  sqlite-vec KNN via RRF. Vantagem: sem servidor separado; funciona offline; mesmo arquivo.
  AtenÃ§Ã£o: MX150 tem 2GB VRAM â€” usar modelo de embedding â‰¤ 80MB; i5-3470 sem AVX2
  pode ser lento para embeddings, considerar indexar sÃ³ em CachyOS.

- [x] **Spell correction de queries com symspellpy**
  (`services/local_search.py`, antes da query FTS5). Integrar symspellpy (pip install
  symspellpy) com dicionÃ¡rios de frequÃªncia PT+EN prÃ©-compilados. Se query tem â‰¤ 2 tokens
  com baixo score BM25 (< resultados esperados), tentar corrigir. Mostrar "Mostrando
  resultados para: [query corrigida]" no response. LatÃªncia: < 1ms apÃ³s carga do dicionÃ¡rio
  em memÃ³ria. Carregar dicionÃ¡rio no startup do app (uma vez).

- [x] **Preset "apenas artigos cientÃ­ficos" na rota de busca**
  (`routers/search.py`, template `search.html`). Aceitar `?mode=papers` na rota `/search`
  que force `src_papers=True` e todos os outros sources desligados. Na UI, adicionar botÃ£o
  "Buscar artigos" ao lado do campo de busca principal (ou atalho de teclado). Permite busca
  exclusiva em Semantic Scholar + arXiv sem passar por DDG/FTS5 local/sites. Abre caminho
  para presets futuros (ex: `?mode=local`, `?mode=archive`).

- [x] **OpenAlex como terceira fonte na busca cientÃ­fica**
  (`services/paper_search.py`). Integrar OpenAlex via `pip install pyalex`. OpenAlex cobre
  250M+ artigos (mais abrangente que Semantic Scholar), Ã© gratuito com chave de email,
  retorna abstracts completos e links de acesso aberto. Adicionar ao gather paralelo em
  `paper_search.py` ao lado de Semantic Scholar e arXiv. Usar pyalex: `pya.Works().search(q)`.
  Deduplicar por DOI/arXiv ID antes de retornar resultados. Integrar Unpaywall como
  pÃ³s-processamento: dado um DOI, consultar `api.unpaywall.org/v2/{doi}?email=...`
  para obter link PDF de acesso aberto quando disponÃ­vel.

### Pesquisa: AKASHA como Assistente de Pesquisa â€” TÃ©cnicas AlÃ©m de LLMs | 2026-05-06
> Contexto: pesquisa sobre PKM (Zotero, DEVONthink, Readwise), workflows reais de pesquisadores
> (Berrypicking, Information Foraging Theory), tÃ©cnicas de "inteligÃªncia" sem LLM (usage-based
> ranking, co-reading, annotation density, TF-IDF local), sistema de anotaÃ§Ã£o web (W3C WADM),
> progressive disclosure e quando LLM faz sentido vs. quando piora. Objetivo: transformar o
> AKASHA em assistente de pesquisa produtivo sem depender de Ollama como fundaÃ§Ã£o.

#### AKASHA
- [x] **Tabela de histÃ³rico de acessos** (`database.py`). Criar tabela `doc_accesses(id, url,
  accessed_at DATETIME)` e registrar cada abertura de documento arquivado. Sem UI extra â€” apenas
  INSERT silencioso ao abrir um documento. PrÃ©-requisito para usage-based ranking, co-reading
  patterns e annotation density. Nenhuma nova dependÃªncia.

- [x] **Usage-based ranking** (`services/local_search.py`, funÃ§Ã£o `rank_combined` ou novo
  `services/ranking.py`). Combinar BM25 com frequÃªncia de acesso e decaimento temporal:
  `score_final = Î± Ã— bm25 + (1-Î±) Ã— (access_count Ã— exp(-Î» Ã— days_since_last_access))`.
  ParÃ¢metro `Î±` configurÃ¡vel em `/settings` (default 0.7 BM25, 0.3 uso). Consultar tabela
  `doc_accesses` com GROUP BY url para obter contagem e Ãºltimo acesso. Sem nova dependÃªncia.

- [x] **Tabela de highlights e indexaÃ§Ã£o FTS5 separada** (`database.py`,
  `services/archiver.py`). Criar tabela `highlights(id, url, exact TEXT, prefix TEXT,
  suffix TEXT, note TEXT, created_at DATETIME)` seguindo W3C Web Annotation Data Model
  (TextQuoteSelector: exact = trecho destacado, prefix = 32 chars antes, suffix = 32 chars
  depois). Criar virtual table `highlights_fts(rowid, exact, note)`. Ao buscar, incluir
  resultados de highlights_fts com badge "HIGHLIGHT". Buscas em anotaÃ§Ãµes pessoais retornam
  resultados mais precisos que buscas no corpo completo do documento.

- [x] **Query autocomplete por histÃ³rico pessoal** (`routers/search.py` ou via endpoint
  HTMX `GET /search/suggest?q=`). Criar tabela `search_history(query TEXT UNIQUE,
  count INT, last_used DATETIME)` e registrar cada query ao executar busca. Endpoint de
  sugestÃ£o: `SELECT query FROM search_history WHERE query LIKE :prefix ORDER BY count DESC,
  last_used DESC LIMIT 10`. Expor como dropdown no campo de busca via HTMX. Sem nova
  dependÃªncia â€” FTS5 puro.

- [x] **Faceted search** (`routers/search.py`, `templates/search.html`). ApÃ³s executar
  a query FTS5, calcular distribuiÃ§Ã£o dos resultados por: domÃ­nio (extrair netloc da URL),
  ano de archivamento, tipo de conteÃºdo (detectado no archive), idioma. Retornar como
  JSON extra no contexto do template. Exibir como checkboxes de filtro na sidebar dos
  resultados. Segunda query com WHERE adicional quando filtro ativo. ImplementaÃ§Ã£o pura
  em SQLite com GROUP BY â€” sem nova dependÃªncia.

- [x] **Co-reading patterns single-user** (`services/local_search.py` ou
  `services/ranking.py`). Ao exibir um documento, consultar `doc_accesses` para encontrar
  outros URLs acessados dentro de uma janela de 2 horas antes e depois. Exibir seÃ§Ã£o
  "Visto na mesma sessÃ£o de pesquisa:" com cards compactos. Captura relaÃ§Ãµes semÃ¢nticas
  que similaridade de texto nÃ£o captura (dois documentos sobre temas diferentes mas lidos
  juntos no contexto de uma pesquisa). ImplementaÃ§Ã£o: SQL com `ABS(strftime('%s', a1.accessed_at)
  - strftime('%s', a2.accessed_at)) < 7200`. Sem nova dependÃªncia.

- [x] **Annotation density como sinal de ranking** (`services/local_search.py`). Ao
  ranquear resultados, incluir contagem de highlights por URL como sinal adicional: documentos
  com mais highlights do usuÃ¡rio sobem no ranking. Consulta: `SELECT COUNT(*) FROM highlights
  WHERE url = :url`. Integrar ao score final como `score += Î² Ã— log(1 + highlight_count)`,
  com `Î²` configurÃ¡vel (default 0.1). PrÃ©-requisito: tabela de highlights (item acima).

- [x] **Lenses pessoais** (`database.py`, `routers/search.py`, `templates/base.html`).
  Criar tabela `lenses(id, name TEXT, domains TEXT, tags TEXT, content_types TEXT,
  date_from TEXT, date_to TEXT)`. UI: botÃ£o "Lenses" na nav, tela de gestÃ£o de lenses
  (criar, editar, deletar). Quando uma lens estÃ¡ ativa, adicionar WHERE clauses Ã  query
  FTS5. Inspirado em Kagi lenses â€” filtros nomeados que persistem entre sessÃµes e podem
  ser ativados com um clique.

- [x] **TF-IDF local para documentos relacionados** (`services/local_search.py`,
  nova funÃ§Ã£o `find_related(url, n=5)`). Ao exibir um documento arquivado, calcular TF-IDF
  do seu conteÃºdo contra o corpus indexado no FTS5 (extrair termos discriminantes via
  `SELECT bm25(local_fts) ...`) e fazer nova busca FTS5 com esses termos, excluindo o
  prÃ³prio documento. Exibir seÃ§Ã£o "Documentos relacionados:" com atÃ© 5 cards. Sem LLM,
  sem nova dependÃªncia â€” FTS5 puro.

- [x] **Progressive disclosure na UI de resultados** (`templates/search.html`). Estruturar
  cards de resultado em 3 camadas acessÃ­veis progressivamente: (1) tÃ­tulo + snippet 30-50
  palavras + Ã­cones de highlights e tags; (2) preview expansÃ­vel ao clicar "â–¸" com todos
  os highlights do documento + metadados completos (autor, data, domÃ­nio, idioma, word count);
  (3) link "Abrir documento completo" para visualizaÃ§Ã£o com modo de anotaÃ§Ã£o. Reduz carga
  cognitiva na lista de resultados sem esconder informaÃ§Ã£o relevante.

- [x] **Citation graph local para papers** (`database.py`, `services/archiver.py`,
  `services/paper_search.py`). Criar tabela `doc_citations(citing_url TEXT, cited_doi TEXT,
  cited_title TEXT)`. Ao arquivar um documento que contÃ©m DOIs nas referÃªncias (detectar
  por regex `10\.\d{4,}/\S+`), consultar CrossRef REST API (`api.crossref.org/works/{doi}`)
  para enriquecer metadados e salvar em `doc_citations`. Na tela do documento, exibir
  seÃ§Ã£o "Citado por documentos neste arquivo:" via query de bibliographic coupling. CrossRef
  Ã© gratuito sem autenticaÃ§Ã£o para consultas moderadas.

- [x] **"Mais deste domÃ­nio/autor neste perÃ­odo"** (`services/local_search.py`,
  `templates/archive_view.html`). Na tela de visualizaÃ§Ã£o de um documento arquivado,
  exibir seÃ§Ã£o "Mais de [domÃ­nio]:" com atÃ© 5 documentos do mesmo netloc arquivados
  prÃ³ximos Ã  mesma data. Implementa o padrÃ£o "journal run" de Bates (1989): vasculhar
  o mesmo veÃ­culo/autor em busca de contexto. Query SQL: `WHERE url LIKE :domain_pattern
  AND ABS(julianday(archived_at) - julianday(:doc_date)) < 90 LIMIT 5`.

- [x] **Tag co-ocorrÃªncia para sugestÃ£o** (`services/archiver.py`, `routers/search.py`).
  Ao exibir filtros de tag nos resultados de busca, ordenar tags relacionadas por co-ocorrÃªncia
  com a tag selecionada: `SELECT tag_b, COUNT(*) FROM tag_pairs WHERE tag_a = :active GROUP
  BY tag_b ORDER BY COUNT(*) DESC`. Popular tabela `tag_pairs` ao salvar/atualizar tags de
  um documento. Tags que co-ocorrem frequentemente sÃ£o sugeridas automaticamente ao criar
  novos highlights ou arquivar documentos.

- [x] **DegradaÃ§Ã£o graciosa quando Ollama offline** (`services/local_search.py`,
  `routers/search.py`). Qualquer feature que depende de Ollama (reranking LLM, sÃ­ntese
  Map-Reduce, HyDE) deve ter um estado funcional alternativo quando `http://localhost:11434`
  nÃ£o responde. PadrÃ£o: verificar Ollama no startup, setar flag `_ollama_available` global.
  Se False: desabilitar features LLM na UI com tooltip "Ollama offline â€” feature disponÃ­vel
  quando Ollama estiver rodando". Nunca bloquear a busca FTS5 por falta de LLM.

### Pesquisa: LLMs Locais para Dispatcher/Skill Routing â€” achados para Mnemosyne e KOSMOS | 2026-05-12
> Contexto: pesquisa sobre arquitetura multi-agente e comparaÃ§Ã£o de LLMs locais para instruction
> following revelou implicaÃ§Ãµes prÃ¡ticas para o Mnemosyne (RAG com citaÃ§Ã£o, janela de contexto,
> ordering de chunks) e para o KOSMOS (modelos mais capazes dentro da mesma limitaÃ§Ã£o de VRAM).

#### Mnemosyne
- [x] **Command R 7B como opção de modelo para RAG** â€” o Command R 7B (Cohere, via `ollama pull
  command-r`) Ã© o Ãºnico modelo sub-10B com treinamento explÃ­cito para grounded generation com
  citaÃ§Ã£o de fontes (grounding spans). Adicionar como opÃ§Ã£o de `qa_model` na `SetupDialog` do
  Mnemosyne com tooltip explicando a especializaÃ§Ã£o. Consumo: ~5 GB VRAM Q4_K_M, cabe na RX 6600.
  Para respostas que incluam citaÃ§Ãµes precisas ("conforme [fonte], [trecho]"), esse modelo
  supera Llama/Qwen no critÃ©rio de fidelidade de atribuiÃ§Ã£o.

- [x] **Reordenação de chunks para mitigar "lost in the middle"** â€” todos os modelos LLM exibem
  viÃ©s posicional em multi-document RAG: chunks no meio do contexto sÃ£o menos utilizados que
  os do inÃ­cio e do fim. Em `core/rag.py`, ao montar o contexto final, reordenar os N chunks
  recuperados colocando os de maior score RRF alternadamente no inÃ­cio e no final (ex: rank 1
  â†’ posiÃ§Ã£o 0, rank 2 â†’ posiÃ§Ã£o N-1, rank 3 â†’ posiÃ§Ã£o 1, rank 4 â†’ posiÃ§Ã£o N-2). MudanÃ§a
  pequena em `_build_context()` com impacto documentado de qualidade de resposta.

- [x] **Nota sobre janela de contexto por modelo** â€” documentar no `SetupDialog` (tooltip em
  `qa_model`) que Qwen2.5-7B-Instruct suporta 128K tokens de contexto enquanto Llama 3.1 8B
  suporta apenas 16K. Para coleÃ§Ãµes com documentos longos ou muitos chunks recuperados, o
  Qwen2.5-7B Ã© preferÃ­vel. Adicionar verificaÃ§Ã£o em `core/rag.py`: se `qa_model` contiver
  "llama" e o contexto montado exceder ~12K tokens, logar aviso "contexto prÃ³ximo do limite
  do modelo â€” considere usar Qwen2.5-7B".

#### KOSMOS
- [ ] **Avaliar Phi-4 Mini 3.8B como modelo principal do KOSMOS** â€” o Phi-4 Mini 3.8B tem MMLU
  equivalente ao Llama 3.1 8B (73%), consome ~3 GB em Q4_K_M e roda a ~60-120 t/s na RX 6600.
  Em CPU puro (i5-3470, Windows 10), cabe em RAM com offload e Ã© significativamente mais capaz
  que o SmolLM2 1.7B atual. Testar: `ollama pull phi4-mini` e avaliar qualidade de respostas
  nas tarefas tÃ­picas do KOSMOS (sÃ­ntese de artigo, extraÃ§Ã£o de conceitos, geraÃ§Ã£o de notas).

- [ ] **Avaliar Gemma 3 4B para hardware limitado (MX150/i5-3470)** â€” o Gemma 3 4B cabe inteiro
  na MX150 (2 GB VRAM) em Q4_K_M (~2,5 GB) e representa upgrade significativo sobre modelos 1-2B.
  Testar: `ollama pull gemma3:4b`. Candidato a modelo padrÃ£o do KOSMOS no laptop e no Windows
  de trabalho onde a MX150 nÃ£o estÃ¡ disponÃ­vel mas a RAM permite offload de 4B.

## Melhorias, correÃ§Ãµes e atualizaÃ§Ãµes

### Mnemosyne + AKASHA: tratamento diferenciado por tipo de fonte | 2026-05-06
> Contexto: diferentes fontes tÃªm densidade informacional, perspectiva e objetivo distintos â€”
> notas pessoais sÃ£o opiniÃ£o da usuÃ¡ria, transcriÃ§Ãµes sÃ£o linguagem falada informal, artigos
> web sÃ£o resumos curados, livros sÃ£o conteÃºdo desenvolvido, artigos cientÃ­ficos sÃ£o o mais
> denso e autoritativo. O pipeline de RAG deve refletir essas diferenÃ§as em chunking,
> recuperaÃ§Ã£o e apresentaÃ§Ã£o dos resultados.

#### Mnemosyne
- [x] **[P1] Framing por tipo no prompt de RAG (`core/rag.py`)** â€” quando montar o contexto
  enviado ao LLM, incluir o rÃ³tulo legÃ­vel do `source_type` de cada chunk: "Nota pessoal",
  "TranscriÃ§Ã£o", "Artigo web", "Livro", "Artigo cientÃ­fico". Notas pessoais devem ser
  explicitamente marcadas como opiniÃ£o da usuÃ¡ria ("este trecho vem das suas notas pessoais")
  para que o LLM nÃ£o as trate como fato externo. CientÃ­ficos como "artigo peer-reviewed".
  MudanÃ§a pequena, alto impacto â€” o LLM passa a raciocinar diferente sobre cada fonte.

- [x] **[P2] Peso por tipo de fonte na recuperaÃ§Ã£o hÃ­brida (`core/rag.py`)** â€” adicionar dict
  `SOURCE_WEIGHTS: dict[str, float]` (ex: `{"scientific": 1.4, "book": 1.2, "library": 1.0,
  "transcript": 0.9, "vault": 1.0}`). Ao fazer o merge BM25 + semÃ¢ntico, multiplicar o score
  pelo peso da fonte antes do ranking final. Notas pessoais tÃªm peso neutro (1.0) â€” sÃ£o
  relevantes quando a pergunta Ã© sobre a opiniÃ£o da usuÃ¡ria, nÃ£o quando Ã© sobre fatos.
  TranscriÃ§Ãµes de YouTube/TikTok pesam menos que livros no mesmo tema.

- [x] **[P3] Separadores de chunk especÃ­ficos por tipo (`core/indexer.py`)** â€” em
  `_get_splitter()`, alÃ©m do `chunk_size`/`overlap`, usar separadores adequados ao conteÃºdo:
  notas â†’ `["\n## ", "\n\n", "\n"]`; livros â†’ `["\n# ", "\n## ", "\n\n", "\n"]`;
  cientÃ­ficos â†’ `["\n## ", "\n\n", ". ", "\n"]` (seÃ§Ãµes como Abstract/MÃ©todos/Resultados);
  transcriÃ§Ãµes â†’ `[". ", "! ", "? ", "\n"]` (sem cabeÃ§alhos markdown, fala Ã© contÃ­nua);
  artigos web â†’ `["\n\n", "\n", ". "]`. Atualizar `CHUNK_PARAMS` para incluir `separators`.

- [x] **[P4] DetecÃ§Ã£o e chunk params de artigo cientÃ­fico** â€” adicionar tipo `"scientific"` em
  `CHUNK_PARAMS` (chunk_size 400, overlap 80 â€” denso, precisa de mais overlap para nÃ£o cortar
  mid-argumento). Em `_chunk_type_for()`, detectar via `is_scientific_paper(file_path)`:
  checar frontmatter por `type: scientific` (adicionado pelo AKASHA â€” ver item AKASHA abaixo),
  ou por presenÃ§a de seÃ§Ãµes `Abstract`, `References`/`ReferÃªncias`, `DOI:` no corpo.

#### AKASHA
- [x] **[P4] Marcar artigos cientÃ­ficos no frontmatter ao arquivar (`services/crawler.py` ou
  `routers/crawler.py`)** â€” quando o AKASHA fizer download via arxiv (`aioarxiv`) ou de URL
  com indicadores cientÃ­ficos (domÃ­nio `arxiv.org`, `pubmed`, `doi.org`, `scholar`, extensÃ£o
  `.pdf` com metadados de autor/abstract), adicionar `type: scientific` no frontmatter YAML
  do arquivo `.md` gerado. Isso permite que o Mnemosyne identifique a fonte sem depender de
  subpasta. Verificar onde o AKASHA gera os arquivos `.md` do archive e adicionar o campo lÃ¡.

### AKASHA + Mnemosyne: metadados ricos no frontmatter do archive | 2026-05-06
> Contexto: ao arquivar conteÃºdo, o AKASHA deve incluir metadados estruturados no frontmatter
> YAML dos arquivos .md gerados. Esses metadados sÃ£o consumidos pelo Mnemosyne para framing
> no prompt, citaÃ§Ã£o correta nas respostas e futura filtragem por tipo/data/idioma.

#### AKASHA
- [x] **Campos universais em todos os arquivos arquivados** â€” ao gerar o frontmatter .md no
  archive, sempre incluir: `title`, `author` (quando disponÃ­vel na pÃ¡gina/PDF), `date`
  (data de publicaÃ§Ã£o do conteÃºdo, nÃ£o de download â€” formato `YYYY-MM-DD`), `language`
  (`pt`/`en`/etc. â€” detectar via `langdetect` jÃ¡ no requirements do KOSMOS, ou pelo
  `Content-Language` do HTTP), `source_url` (URL original de onde foi baixado). Esses campos
  sÃ£o os mais usados pelo Mnemosyne para framing e citaÃ§Ã£o.

- [x] **Campos específicos para artigos científicos** â€” quando a fonte for identificada como
  cientÃ­fica (arxiv, DOI, Semantic Scholar, OpenAlex), incluir adicionalmente no frontmatter:
  `doi` (ex: `10.48550/arXiv.1706.03762`), `arxiv_id` (quando aplicÃ¡vel, ex: `1706.03762`),
  `journal` (nome do periÃ³dico ou `arXiv preprint`), `abstract` (primeiros 500 chars do
  abstract â€” indexado separadamente melhora a recuperaÃ§Ã£o pois resume o artigo inteiro),
  `keywords` (lista de palavras-chave quando disponÃ­veis). `doi` e `arxiv_id` tambÃ©m servem
  para deduplicaÃ§Ã£o: antes de baixar, verificar se jÃ¡ existe arquivo com o mesmo DOI no
  archive.

- [x] **Campos específicos para PDFs de livros** â€” quando processar PDF com `pymupdf4llm`,
  extrair metadados nativos do PDF (jÃ¡ acessÃ­veis via `fitz.open(path).metadata`): `isbn`,
  `publisher`, `year`. Incluir no frontmatter apenas quando nÃ£o-vazios. `year` complementa
  `date` para livros onde sÃ³ o ano Ã© conhecido.

#### Hermes
- [x] **Campos adicionais no frontmatter de transcrições** â€” `build_mnemosyne_markdown()` em
  `hermes.py` jÃ¡ inclui `title`, `date`, `source`, `duration`. Adicionar: `platform`
  (`youtube`/`tiktok`/`podcast`/`local` â€” inferir da URL ou marcar "local" quando arquivo
  local), `channel` (nome do canal/criador quando disponÃ­vel via yt-dlp `info["uploader"]`
  ou `info["channel"]`). `platform` permite ao Mnemosyne diferenciar um podcast tÃ©cnico de
  um vÃ­deo de TikTok na hora de pesar a fonte.

#### Mnemosyne
- [x] **Usar `date`, `author`, `language` do frontmatter na detecção e no framing** â€” em
  `core/loaders.py`, ao carregar arquivos .md, extrair esses campos do frontmatter e
  propagÃ¡-los para `doc.metadata`. Em `core/rag.py`, usar `author` e `date` ao montar o
  rÃ³tulo de cada chunk no prompt (ex: "Vaswani et al., 2017 â€” Artigo cientÃ­fico"). Depende
  dos itens AKASHA acima.

### Mnemosyne: auditoria de funcionalidades atuais | 2026-05-06
> Contexto: antes de redesenhar a UI e adicionar novas features, verificar o estado real
> de cada funcionalidade existente no cÃ³digo â€” quais funcionam, quais estÃ£o incompletas,
> quais estÃ£o quebradas. Evita assumir que itens marcados [x] no TODO estÃ£o operacionais.

#### Mnemosyne
- [ ] **Auditar cada funcionalidade existente do Mnemosyne contra o cÃ³digo real**
  (`Mnemosyne/` â€” todos os arquivos). Para cada item marcado `[x]` nas Fases do TODO do
  Mnemosyne, verificar no cÃ³digo se: (a) estÃ¡ implementado, (b) Ã© chamado corretamente,
  (c) funciona no fluxo real do app. Registrar resultado como: âœ“ funcional / âš  parcial
  (descrever o que falta) / âœ— quebrado / âœ— nunca implementado (falso positivo como na
  Fase 7 do AKASHA). Ãreas crÃ­ticas a checar: indexaÃ§Ã£o (IndexWorker), busca RAG
  (`prepare_ask()`), reranking (FlashRank), relatÃ³rio, mind map, Deep Research Mode,
  Notebook Guide, Knowledge Reflection, session_memory, detecÃ§Ã£o dinÃ¢mica de modelos
  Ollama. Resultado da auditoria orienta o redesign da UI â€” inÃºtil redesenhar em torno
  de features que nÃ£o funcionam.

### Mnemosyne: reestruturaÃ§Ã£o urgente da UI | 2026-05-06
> Contexto: a UI atual do Mnemosyne nÃ£o estÃ¡ intuitiva nem clara para a usuÃ¡ria.
> A referÃªncia de design Ã© o NotebookLM (Google) â€” paradigma tri-pane (Fontes / Chat / Workspace)
> com ancoragem de citaÃ§Ãµes e estado separado por painel. Requer redesign profundo antes de
> continuar adicionando features ao app. Pesquisa de UI/UX em andamento (ver pesquisas.md).

#### Mnemosyne
- [ ] **[URGENTE] Redesenhar a UI completa do Mnemosyne** seguindo o paradigma tri-pane do
  NotebookLM: (1) painel esquerdo de fontes/coleÃ§Ãµes com status de indexaÃ§Ã£o por item,
  (2) painel central de chat RAG com citaÃ§Ãµes clicÃ¡veis, (3) painel direito de notas
  persistentes onde respostas do chat podem ser "promovidas" para registro permanente.
  Antes de implementar: definir o layout alvo com a usuÃ¡ria. A pesquisa de referÃªncia
  estÃ¡ em `pesquisas.md` (seÃ§Ãµes NotebookLM 2026-04-10 e 2026-04-20, e nova sessÃ£o 2026-05-06).

### AKASHA: remoÃ§Ã£o de dead code da Fase 7 (library_urls) e re-crawl periÃ³dico | 2026-05-05
> Contexto: o conceito original de "Biblioteca de URLs" (Fase 7) foi supersedido pelo crawler BFS
> da Fase 10. As tabelas library_urls/library_diffs/library_fts nunca foram populadas mas ainda
> existem no schema e geram uma query morta em toda busca local. AlÃ©m disso, crawl_pending_sites()
> sÃ³ crawla sites nunca visitados â€” nÃ£o re-crawla sites desatualizados.

#### AKASHA
- [x] Remover query morta de library_fts de `services/local_search.py` â€” `_search_fts()` fazia
      uma segunda query contra `library_fts` (nunca populada) retornando source="BIBLIOTECA";
      essa query executava em toda busca local sem retornar nada Ãºtil.
- [x] Adicionar migration v13 em `database.py`: DROP TABLE library_urls, library_diffs, library_fts
      e DROP INDEX idx_library_diffs_url. Remover os DDL constants e chamadas de init_db().
      SCHEMA_VERSION: 12 â†’ 13.
- [x] Estender `crawl_pending_sites()` em `services/crawler.py` para tambÃ©m re-crawlar sites com
      last_crawled_at anterior a 7 dias â€” hoje a funÃ§Ã£o sÃ³ processa sites com last_crawled_at IS NULL.

### Caminhos do Mnemosyne: configuraÃ§Ã£o no HUB + editabilidade no prÃ³prio app | 2026-05-04

> Contexto: item 0.9 tornou os caminhos do Mnemosyne (watched_dir, vault_dir, chroma_dir)
> somente-leitura no SetupDialog, mas a configuraÃ§Ã£o equivalente ainda nÃ£o existe no HUB.
> Resultado: nÃ£o hÃ¡ como definir ou alterar esses caminhos de lugar nenhum.
> extra_dirs tambÃ©m deve ser persistido no ecosystem.json.

#### HUB
- [x] `src/types/index.ts` â€” atualizar `EcosystemConfig.mnemosyne` para incluir
      `watched_dir`, `vault_dir`, `chroma_dir` (strings) e `extra_dirs` (string[])
- [x] `src/views/SetupView.tsx` â€” adicionar campos do Mnemosyne em DATA_FIELDS:
      watched_dir ("Mnemosyne â€” Biblioteca"), vault_dir ("Mnemosyne â€” Vault"),
      chroma_dir ("Mnemosyne â€” ChromaDB"); e lista editÃ¡vel de extra_dirs
      (componente separado com add/remove, abaixo dos campos simples)

#### Mnemosyne
- [x] `gui/main_window.py` â€” SetupDialog: tornar watched_dir, vault_dir e chroma_dir
      editÃ¡veis (QLineEdit + botÃ£o de seleÃ§Ã£o de pasta); ao salvar, chamar
      `write_section("mnemosyne", {watched_dir, vault_dir, chroma_dir, extra_dirs})`
      via ecosystem_client â€” sobrescreve o ecosystem.json
- [x] `gui/main_window.py` â€” ao salvar extra_dirs, incluÃ­-las tambÃ©m no ecosystem.json
      (campo `extra_dirs: list[str]`) para que o HUB e outros apps saibam quais pastas
      o Mnemosyne estÃ¡ monitorando

### Auditoria pesquisas.md â†’ itens nÃ£o registrados no TODO | 2026-05-05
> Contexto: leitura completa de pesquisas.md comparada ao TODO revelou 47 lacunas â€”
> achados de pesquisas anteriores que nunca foram transcritos como itens acionÃ¡veis.

#### Mnemosyne
- [x] **[CRÃTICO] Mudar distÃ¢ncia ChromaDB de L2 para cosine em todas as coleÃ§Ãµes**
  (`core/indexer.py`, todos os pontos onde `Chroma(...)` Ã© criado). Adicionar
  `collection_metadata={"hnsw:space": "cosine"}` em cada criaÃ§Ã£o de coleÃ§Ã£o.
  Para texto, cosine mede direÃ§Ã£o semÃ¢ntica â€” L2 mede distÃ¢ncia absoluta, o que Ã©
  incorreto para embeddings normalizados. Impacto documentado: atÃ© 10Ã— de melhoria
  na qualidade de recuperaÃ§Ã£o. O IndexWorker jÃ¡ apaga e recria o persist_dir, entÃ£o
  a correÃ§Ã£o se aplica automaticamente na prÃ³xima reindexaÃ§Ã£o. Custo: ~30 min.

- [x] **[CRÃTICO] Aumentar chunk size de 800 â†’ 1800 chars, overlap 100 â†’ 250**
  (`core/config.py`, `RecursiveCharacterTextSplitter`). O valor atual de 800 chars â‰ˆ
  200 tokens estÃ¡ abaixo do range recomendado por benchmarks 2025â€“2026 (Vecta, NAACL
  2025/Vectara: 400â€“512 tokens). Trocar para `chunk_size=1800, chunk_overlap=250`.
  Ganho documentado: +20pp de acurÃ¡cia em RAG geral. Requer re-indexaÃ§Ã£o completa.
  Chunking semÃ¢ntico continua desativado (correto â€” benchmarks mostram fixed-size
  superior para RAG de propÃ³sito geral).

- [x] **FlashRank reranking no `prepare_ask()` â€” pipeline dois estÃ¡gios**
  (`core/rag.py` ou `core/indexer.py`). Substituir recuperador Ãºnico por:
  (1) recuperar top-30 por hÃ­brido BM25+cosine; (2) re-rankear com
  `FlashrankRerank(model="ms-marco-MultiBERT-L-12", top_n=5)` de
  `langchain_community.document_compressors`. `pip install flashrank`. Modelo ONNX
  de ~4MB, sem PyTorch, 15â€“30ms em CPU. Reduz alucinaÃ§Ãµes garantindo que o LLM
  recebe os 5 documentos genuinamente mais relevantes em vez dos 5 melhores por
  similaridade vetorial pura.

- [x] **Deep Research Mode â€” integraÃ§Ã£o Mnemosyne + AKASHA**
  (novo `core/akasha_client.py` + `core/session_indexer.py` + `gui/workers.py`).
  Quando corpus local insuficiente para responder a query, expandir para web via
  AKASHA: (A) chamar `GET /search/json?q=&max=5` do AKASHA, (B) buscar conteÃºdo
  de cada URL via `GET /fetch?url=`, (C) indexar transientemente em ChromaDB
  EphemeralClient, (D) RAG sobre corpus local + web combinados, (E) mostrar badges
  de fonte (local vs web) na resposta. PrÃ©-requisito: endpoints `/search/json` e
  `/fetch` no AKASHA (ver itens AKASHA abaixo). ~450 linhas no total.

- [x] **Notebook Guide â€” sumÃ¡rio + perguntas sugeridas ao indexar documento**
  (`core/indexer.py`, `gui/` componente de detalhe de documento). Ao finalizar
  indexaÃ§Ã£o de um arquivo, chamar LLM para gerar: (a) sumÃ¡rio de 3â€“5 frases,
  (b) 3â€“5 perguntas que o usuÃ¡rio poderia fazer sobre o documento. Armazenar em
  metadata do ChromaDB. Exibir na view de detalhe da coleÃ§Ã£o. Uma call LLM por
  documento no momento da indexaÃ§Ã£o; resultado cacheado. Inspirado no NotebookLM
  "Notebook Guide".

- [x] **Mermaid como MVP do Mind Map (abrir no browser)**
  (`core/mindmap.py`, botÃ£o na UI). LLM gera JSON estruturado de temas â†’ converter
  para sintaxe Mermaid â†’ salvar como `.md` â†’ abrir via `webbrowser.open()`. Sem
  dependÃªncia de Qt graphics ou graphviz. CompatÃ­vel com Obsidian. Graphviz/QGraphicsView
  como melhoria posterior. Esta Ã© a decisÃ£o de implementaÃ§Ã£o documentada na pesquisa
  NotebookLM â€” o TODO tem "mind map" mas sem especificar o caminho de implementaÃ§Ã£o.

- [x] **RelatÃ³rio de Pesquisa estruturado em 8 seÃ§Ãµes**
  > Parcialmente implementado: `core/report.py` existe com 6 seÃ§Ãµes (faltam "AnÃ¡lise por fonte" e "ConvergÃªncias/divergÃªncias"). Expandir para 8 conforme especificado.
  (`core/report.py`). Implementar relatÃ³rio Map-Reduce: (1) TÃ­tulo/escopo, (2) SumÃ¡rio
  executivo, (3) Temas principais, (4) AnÃ¡lise por fonte, (5) ConvergÃªncias e
  divergÃªncias entre fontes, (6) Lacunas identificadas, (7) RecomendaÃ§Ãµes,
  (8) ReferÃªncias. Abordagem: LLM por seÃ§Ã£o (Map) â†’ sÃ­ntese final (Reduce).
  Export para Markdown; PDF opcional via `pandoc` ou `weasyprint`.

- [x] **Knowledge Reflection â€” gerar e indexar artefatos de sÃ­ntese durante indexaÃ§Ã£o**
  (`core/indexer.py`). ApÃ³s indexar chunks de cada documento, chamar LLM para gerar
  uma "reflexÃ£o" â€” sÃ­ntese dos top-5 chunks. Armazenar no ChromaDB com
  `metadata["type"]="reflection"` e `metadata["boost"]=1.5`. Durante retrieval em
  `prepare_ask()`, aplicar score boost para documentos de reflexÃ£o. Meta-reflexÃµes
  (sÃ­ntese de 3+ reflexÃµes sobre o mesmo tema) recebem boost 1.8Ã—.

- [x] **`index.json` leve por coleÃ§Ã£o â€” metadados sempre em memÃ³ria**
  (`core/indexer.py`, `core/config.py`). Ao lado do ChromaDB, manter
  `{persist_dir}/index.json` com: `name`, `path`, `total_chunks`, `last_indexed`,
  `file_types` (contagens), `summary` (1 frase gerada por LLM). Carregar no startup
  sem acessar ChromaDB. Usado pela UI para mostrar overview da coleÃ§Ã£o em <1ms.
  Atualizar a cada operaÃ§Ã£o de indexaÃ§Ã£o.

- [x] **Lock de mÃ¡quina de indexaÃ§Ã£o â€” desabilitar indexaÃ§Ã£o em mÃ¡quinas secundÃ¡rias**
  (`core/config.py`, `gui/main_window.py`). Adicionar campo `indexing_machine: str`
  ao config (preenchido com hostname na primeira indexaÃ§Ã£o bem-sucedida). Na
  inicializaÃ§Ã£o, se `hostname != indexing_machine`: desabilitar botÃµes de indexaÃ§Ã£o
  e exibir mensagem "Ãndice construÃ­do em [outra mÃ¡quina]. Consultas disponÃ­veis."
  EnforÃ§a arquitetura "indexar no CachyOS, consultar no Windows".

- [x] **`potion-multilingual-128M` (model2vec) como fallback de embedding no Windows**
  (`core/config.py`, `core/indexer.py`, `gui/main_window.py`). Expor como terceira
  opÃ§Ã£o de embedding em Settings ao lado de bge-m3 e qwen3-embedding:0.6b.
  `pip install model2vec langchain-community`. Sem dependÃªncia de Ollama, sem AVX2,
  ~50ms por chunk. MTEB 47.31 â€” suficiente para RAG pessoal. Ãštil quando Ollama
  nÃ£o estÃ¡ disponÃ­vel no Windows de trabalho.

- [x] **`qwen3-embedding:0.6b` como opÃ§Ã£o intermediÃ¡ria de embedding**
  (`core/config.py`, `gui/main_window.py`). Adicionar `qwen3-embedding:0.6b`
  (639MB, Q8_0, multilÃ­ngue, MTEB ~50â€“60) como opÃ§Ã£o selecionÃ¡vel entre bge-m3
  (qualidade) e potion-multilingual-128M (velocidade). Ãštil no laptop MX150 onde
  bge-m3 cabe em 2GB VRAM mas nÃ£o deixa espaÃ§o para contexto. `ollama pull
  qwen3-embedding:0.6b`, depois `OllamaEmbeddings(model="qwen3-embedding:0.6b")`.

- [ ] **`num_thread` por requisiÃ§Ã£o no OllamaEmbeddings (workaround OLLAMA_NUM_THREAD)**
  (`core/indexer.py`). `OLLAMA_NUM_THREAD` Ã© ignorado no Ollama 0.6.6+ (issue #10476).
  Usar parÃ¢metro por requisiÃ§Ã£o: `OllamaEmbeddings(model=..., num_thread=2)` no
  IndexWorker da mÃ¡quina Windows. Combinado com `QThread.Priority.IdlePriority`.
  Workaround documentado atÃ© correÃ§Ã£o oficial no Ollama.

- [x] **DetecÃ§Ã£o dinÃ¢mica de modelos Ollama no startup (`GET /api/tags`)**
  (`gui/main_window.py`, SetupDialog). Ao iniciar, chamar
  `GET http://localhost:11434/api/tags` (ou via LOGOS se disponÃ­vel) para listar
  modelos locais. Filtrar em candidatos de embedding (nomic-embed-text*, bge-m3,
  qwen3-embedding*) e chat (llama*, qwen*, mistral*, gemma*). Apresentar listas
  filtradas nos dropdowns de Settings em vez de campos de texto livre. Se Ollama
  nÃ£o estiver rodando: mostrar aviso e desabilitar features de IA graciosamente.

- [ ] **`session_memory.json` â€” histÃ³rico de queries e documentos Ãºteis por coleÃ§Ã£o**
  > Parcialmente implementado: `core/memory.py` existe mas armazena apenas histÃ³rico de conversa (mensagens user/assistant), nÃ£o rastreia documentos recuperados nem utilidade. Implementar o rastreamento de documentos e score de relevÃ¢ncia conforme especificado.
  (`core/memory.py` ou novo `core/session_memory.py`). Armazenar por coleÃ§Ã£o as
  Ãºltimas N queries, quais documentos foram recuperados e se a resposta foi Ãºtil.
  Mostrar na UI "VocÃª perguntou algo parecido antesâ€¦". Campos por documento:
  `score_relevÃ¢ncia_mÃ©dio` das Ãºltimas N queries, `Ãºltima_vez_retornado`. Implementa
  "Camada 2" da arquitetura de memÃ³ria de 3 nÃ­veis documentada na pesquisa.

- [ ] **Slide deck export (PPTX) a partir de coleÃ§Ã£o**
  (`core/slidemaker.py`). LLM gera outline (tÃ­tulo + 5â€“7 bullet points por slide
  para cada tema principal) â†’ `python-pptx` monta o arquivo .pptx. `pip install
  python-pptx`. Exportar via botÃ£o na Ã¡rea de RelatÃ³rios.

- [ ] **FAIR-RAG: feedback implÃ­cito â€” boost/penalizar documentos por utilidade da resposta**
  (`core/rag.py`, `gui/` botÃ£o de feedback). ApÃ³s cada resposta RAG, permitir ao
  usuÃ¡rio marcar como Ãºtil/inÃºtil. Se Ãºtil: aumentar score de recuperaÃ§Ã£o dos
  documentos usados (mÃ©dia mÃ³vel exponencial). Se inÃºtil: penalizar. Armazenar
  ajustes por documento em metadata. O Ã­ndice melhora gradualmente com o uso.

#### AKASHA
- [ ] **Endpoint `GET /fetch?url=` â€” busca transiente sem salvar em disco**
  > Parcialmente implementado: existe `POST /fetch` (com body JSON), nÃ£o `GET /fetch?url=`. Adicionar a variante GET com query param para compatibilidade com clientes simples.
  (`routers/search.py` ou novo `routers/fetch.py`). Buscar e extrair conteÃºdo de
  uma URL como Markdown e retornar em JSON sem salvar no archive. Equivale ao
  `archiver.py` sem o `dest_path.write_text()`. ~30 linhas. NecessÃ¡rio para o
  Deep Research Mode do Mnemosyne e para qualquer consumidor programÃ¡tico que
  precise do conteÃºdo sem poluir o archive.

- [x] **Endpoint `GET /search/json?q=&max=` â€” busca retornando JSON estruturado**
  (`routers/search.py`). A rota `/search` atual retorna HTML (Jinja2). Adicionar
  rota `/search/json` que retorna `[{title, url, snippet, source, date}]` como JSON,
  reutilizando a lÃ³gica existente de `search_web()` e `search_local()`. ~20 linhas.
  NecessÃ¡rio para integraÃ§Ã£o com Mnemosyne (Deep Research Mode) e KOSMOS.

- [x] **PropagaÃ§Ã£o de tags do feed para o archive ao auto-arquivar do KOSMOS**
  (`routers/search.py`, endpoint `POST /archive`). Ao receber requisiÃ§Ã£o de
  auto-arquivamento do KOSMOS, aceitar campo `tags: list[str]` no body. KOSMOS
  deve incluir a categoria do feed como tag. Armazenar no frontmatter do arquivo
  Markdown arquivado. Complemento ao item `POST /archive` jÃ¡ rastreado no TODO.

- [ ] **URL normalization antes de inserir no crawl_pages e archive**
  > Parcialmente implementado: `services/crawler.py` jÃ¡ normaliza URLs (lowercase, remove trailing slash). `services/archiver.py` nÃ£o normaliza â€” Ã© onde a deduplicaÃ§Ã£o por tracking params faz mais diferenÃ§a. Implementar em `archiver.py` com remoÃ§Ã£o de `utm_*`, `fbclid`, `gclid`, `ref`, `source`.
  (`services/archiver.py`, `services/crawler.py`). Normalizar URL com
  `pip install url-normalize` antes de inserir: lowercase scheme+host, remover
  default ports, remover parÃ¢metros de rastreamento (`utm_*`, `fbclid`, `gclid`,
  `ref`, `source`), ordenar query params. Evita arquivar a mesma pÃ¡gina com
  tracking params diferentes como documentos separados.

#### KOSMOS
- [ ] **Streaming JSON parcial com field-order optimization (json-stream / ijson)**
  (`app/ui/workers.py`, `_AnalyzeWorker`). Usar `stream=True` com o cliente Ollama
  e parsear a resposta com `pip install json-stream`. Reordenar campos do schema
  para que campos rÃ¡pidos (tags, sentiment, clickbait_score) venham antes dos lentos
  (entities, five_ws) â€” XGrammar/Outlines segue a ordem de declaraÃ§Ã£o. A UI pode
  exibir campos rÃ¡pidos em 0.5â€“1.5s, antes do JSON completo. Melhor custo-benefÃ­cio
  que split de calls para este caso.

- [ ] **SpaCy para extraÃ§Ã£o de entidades em vez de LLM (pt_core_news_lg)**
  (`app/core/analyzer.py` ou equivalente). Para o campo `entities`, substituir ou
  complementar a call LLM com SpaCy `pt_core_news_lg` (~250MB). Roda totalmente em
  CPU, trata PER/ORG/LOC/MISC em portuguÃªs, dramaticamente mais rÃ¡pido que LLM para
  NER. O LLM mantÃ©m responsabilidade sobre semantic classification (sentiment, tags,
  clickbait). Resolve a perda de fidelidade de 3â€“8% documentada em modelos Q4 para
  tarefas de cÃ³pia de span como NER. `pip install spacy` +
  `python -m spacy download pt_core_news_lg`.

- [ ] **Heartbeat timeout para anÃ¡lises travadas (`analysis_started_at` + reset no startup)**
  (`app/utils/db.py` ou equivalente). Adicionar coluna `analysis_started_at DATETIME`
  na tabela de artigos. No startup, resetar para `pending` todos os artigos com
  `status = 'in_progress'` e `analysis_started_at < now - 5 minutes`. Evita artigos
  eternamente presos em `in_progress` apÃ³s kill do processo ou crash.

- [x] **DeduplicaÃ§Ã£o de anÃ¡lise por content hash (SHA-256 de texto normalizado)**
  (`app/core/analyzer.py`, `app/utils/db.py`). Antes de chamar LLM para anÃ¡lise,
  calcular SHA-256 do conteÃºdo normalizado (minÃºsculas, sem pontuaÃ§Ã£o/espaÃ§os extras).
  Checar se outro artigo tem o mesmo hash â€” se sim, copiar campos `ai_*` existentes
  em vez de re-chamar o LLM. Adicionar coluna `content_hash TEXT` com Ã­ndice UNIQUE
  parcial. Economiza calls LLM para artigos cross-posted/espelhados.

- [ ] **Ãndice parcial SQLite para fila de anÃ¡lise pendente**
  (`app/utils/db.py`, na criaÃ§Ã£o do schema). Adicionar:
  `CREATE INDEX idx_pending_analysis ON articles(feed_id, published_at DESC)
  WHERE analysis_status IN ('pending', 'failed')`.
  SQLite suporta partial indexes desde 3.8.0. Para tabela com 10k artigos onde 95%
  estÃ£o analisados, o Ã­ndice cobre ~500 linhas â€” query da fila de background passa
  de O(log 10000) para O(log 500).

- [ ] **TTL de campos pesados: nullar five_ws e entities para artigos > 6 meses**
  (`app/core/maintenance.py` ou job periÃ³dico). Query mensal:
  `UPDATE articles SET ai_five_ws = NULL, ai_entities = NULL
  WHERE published_at < date('now', '-6 months') AND ai_five_ws IS NOT NULL`.
  Manter ai_tags e ai_sentiment (Ãºteis para filtragem histÃ³rica). Seguido de
  `VACUUM` + `ANALYZE`. MantÃ©m o DB SQLite em tamanho gerenciÃ¡vel conforme
  artigos acumulam na casa dos milhares.

- [ ] **Politeness: delay mÃ­nimo de 2s por domÃ­nio no scraping de artigos**
  (`app/core/scraper.py` ou `ArticleScraper`). Manter dict
  `{domain: last_access_time}` e impor delay de 2s entre requisiÃ§Ãµes ao mesmo
  domÃ­nio durante scraping em background. Tratar HTTP 429 com backoff exponencial
  (`base * 2^attempt`, max 60s, Â±50% jitter). Sem isso, scraping de 10 artigos do
  mesmo blog em sequÃªncia rÃ¡pida pode disparar bloqueio de IP.

- [ ] **`analysis_schema_version` para invalidaÃ§Ã£o de cache de anÃ¡lise LLM**
  (`app/utils/db.py`, `app/core/analyzer.py`). Adicionar coluna
  `analysis_schema_version INTEGER DEFAULT 0` na tabela de artigos. Definir
  constante `ANALYSIS_VERSION = 1` no cÃ³digo. Incrementar ao mudar prompts ou
  schema. No startup, enfileirar para re-anÃ¡lise todos os artigos com
  `analysis_schema_version < ANALYSIS_VERSION`. Invalida cache sistematicamente
  sem precisar de processo manual.

#### LOGOS / HUB
- [ ] **`OLLAMA_GPU_OVERHEAD=0` no perfil RX 6600 com ROCm**
  > Parcialmente implementado: `OLLAMA_GPU_OVERHEAD` jÃ¡ estÃ¡ definido em `logos.rs` mas com valor 524288000 (524MB), nÃ£o 0. Avaliar se o OOM handler do ROCm Ã© suficientemente confiÃ¡vel para usar 0, ou se o valor atual Ã© intencional.
  (`HUB/src-tauri/src/logos.rs` ou arquivo de configuraÃ§Ã£o de perfil de hardware).
  Com ROCm na RX 6600, `OLLAMA_GPU_OVERHEAD=524288000` (500MB padrÃ£o) pode fazer
  o Ollama recusar carregar modelos que caberiam na VRAM. Definir
  `OLLAMA_GPU_OVERHEAD=0` para o perfil `main_pc` â€” deixar o OOM handler do ROCm
  atuar em vez da estimativa conservadora do Ollama.

- [ ] **PolÃ­tica de bateria em 3 nÃ­veis no LOGOS (Normal / Economia / CrÃ­tico)**
  > Parcialmente implementado: lÃ³gica de bateria existe mas Ã© binÃ¡ria (AC vs bateria) â€” sem distinÃ§Ã£o entre Economia e CrÃ­tico. Expandir para 3 nÃ­veis com os thresholds documentados.
  (`HUB/src-tauri/src/logos.rs`, mÃ³dulo de monitoramento de bateria). O TODO tem
  suspensÃ£o de P3 em bateria, mas a pesquisa documenta 3 nÃ­veis:
  Normal (AC ou bateria >80%): P3 ativo, comportamento padrÃ£o.
  Economia (bateria 30â€“80% ou TimeToEmpty <120min): P3 suspenso, batch P2
  reduzido 64â†’16, keep_alive P2 "10m"â†’"2m".
  CrÃ­tico (bateria <30% ou TimeToEmpty <60min): P2 tambÃ©m suspenso, apenas P1,
  num_thread=2. Polling UPower a cada 30 segundos.

- [ ] **DetecÃ§Ã£o de AVX2 no perfil de hardware (i5-3470 sem AVX2)**
  (`HUB/src-tauri/src/logos.rs`, detecÃ§Ã£o de hardware no startup). Checar presenÃ§a
  de AVX2 via `/proc/cpuinfo` (Linux) ou cpuid (Windows). Se ausente: forÃ§ar perfil
  low com `num_ctx=512`, `num_batch=128`, `num_thread=2`. O i5-3470 Ã© 30â€“50% mais
  lento que CPUs com AVX2 em inferÃªncia INT4 â€” o perfil deve refletir isso
  explicitamente.

- [ ] **Microbenchmark de startup (20 tokens) para medir t/s real do hardware**
  (`HUB/src-tauri/src/logos.rs`, inicializaÃ§Ã£o do LOGOS). Em vez de inferir
  capacidade do hardware por specs, executar geraÃ§Ã£o de 20 tokens com SmolLM2 1.7B
  no startup. Leva <5 segundos, produz mediÃ§Ã£o direta de tokens/segundo para seleÃ§Ã£o
  de perfil. Armazenar resultado em config para evitar repetir a cada startup.

- [ ] **ProteÃ§Ã£o contra thermal throttling da RX 6600 (pausar P3 acima de 85Â°C)**
  (`HUB/src-tauri/src/logos.rs`). Durante workloads P3 longos, monitorar temperatura
  da GPU via `sysinfo` crate (campo `gpu_temperature` disponÃ­vel no sysinfo 0.30+).
  Se temperatura > 85Â°C: pausar P3 automaticamente. Evita depender exclusivamente
  do throttling do driver a 95Â°C.

- [ ] **`num_gpu` dinÃ¢mico por requisiÃ§Ã£o no perfil MX150 (baseado em tamanho do contexto)**
  > Parcialmente implementado: `num_gpu` estÃ¡ definido no perfil MX150 mas como valor estÃ¡tico. Adicionar lÃ³gica de seleÃ§Ã£o por tamanho de contexto conforme documentado.
  (`HUB/src-tauri/src/logos.rs`, dispatch de requisiÃ§Ãµes P1). Para o laptop MX150
  (2GB VRAM), ajustar `num_gpu` dinamicamente: `num_gpu=16â€“20` para contextos curtos
  (<2048 tokens), `num_gpu=10â€“12` para contextos longos. LOGOS injeta este parÃ¢metro
  por requisiÃ§Ã£o em vez de usar valor fixo do perfil.

- [ ] **Badge "performance reduzida pelo SO" quando ppd estÃ¡ em power-saver**
  (`HUB/src/` componente LogosPanel). Detectar perfil ativo do Power Profiles Daemon
  (`ppd`). Se `power-saver` ativo: exibir badge no LogosPanel explicando que a
  resposta lenta do LLM Ã© causada pelo modo de economia do sistema operacional, nÃ£o
  por bug. Evita confusÃ£o do usuÃ¡rio quando o laptop estÃ¡ limitado pelo SO.

#### ecosystem_scraper.py
- [ ] **Throttle adaptativo por domÃ­nio â€” delay mÃ­nimo de 2s entre requisiÃ§Ãµes**
  (`ecosystem_scraper.py`). Adicionar dict de mÃ³dulo `{domain: last_request_time}`
  e impor delay configurÃ¡vel (padrÃ£o 2s) entre requisiÃ§Ãµes ao mesmo domÃ­nio.
  Constante `CRAWL_DELAY` exportÃ¡vel. Como AKASHA archiver e KOSMOS ArticleScraper
  usam este mÃ³dulo, a politeness Ã© adicionada uma vez e aplica-se a ambos.

- [ ] **HTTP 429 com backoff exponencial + leitura do header Retry-After**
  (`ecosystem_scraper.py`). Detectar resposta HTTP 429 â†’ ler header `Retry-After`
  â†’ backoff `max(Retry-After, min(base * 2^attempt, 60))` com Â±50% de jitter
  multiplicativo â†’ retry atÃ© `max_retries=3`. Atualmente o mÃ³dulo nÃ£o trata 429 â€”
  retornaria vazio ou lanÃ§aria exceÃ§Ã£o.

#### Hermes
- [ ] **ParÃ¢metros otimizados do faster-whisper: `vad_filter=True`, `beam_size=1`, `language="pt"`**
  > Parcialmente implementado: `vad_filter=True` e `beam_size=1` jÃ¡ estÃ£o configurados em `TranscribeWorker`. Falta `language="pt"` â€” ainda usa detecÃ§Ã£o automÃ¡tica. Adicionar `language="pt"` como default para eliminar ~1s de overhead por segmento.
  (`hermes.py` ou `TranscribeWorker`). A migraÃ§Ã£o para faster-whisper estÃ¡ concluÃ­da
  (`[x]`), mas os parÃ¢metros de otimizaÃ§Ã£o nÃ£o foram registrados: `vad_filter=True`
  filtra silÃªncio antes da transcriÃ§Ã£o (grande melhoria de velocidade para vÃ­deos
  com pausas), `beam_size=1` reduz memÃ³ria e tempo (padrÃ£o Ã© 5), `language="pt"`
  elimina overhead de detecÃ§Ã£o de idioma (~1s por segmento). Definir como defaults
  em `TranscribeWorker`.

- [ ] **Cache do `WhisperModel` entre transcriÃ§Ãµes (instanciar uma vez por sessÃ£o)**
  > Parcialmente implementado: `WhisperModel` Ã© cacheado por instÃ¢ncia de `TranscribeWorker`, mas cada nova transcriÃ§Ã£o cria um novo Worker (e um novo modelo). Mover o cache para nÃ­vel de mÃ³dulo ou singleton para compartilhar entre Workers.
  (`hermes.py`). O `WhisperModel` pode ser instanciado uma vez e reutilizado entre
  transcriÃ§Ãµes (diferente do openai-whisper que recarregava por chamada). Armazenar
  como atributo de classe ou singleton de mÃ³dulo. Economiza 5â€“15s de carregamento
  de modelo a cada nova transcriÃ§Ã£o.
### Infraestrutura: config por dispositivo e sync do ecossistema | 2026-05-06
> Contexto: ecosystem.json Ã© sincronizado via Proton Drive entre mÃ¡quinas, mas contÃ©m
> paths absolutos que diferem entre Windows e Linux. A soluÃ§Ã£o Ã© separar preferÃªncias
> (compartilhadas) de paths (locais por mÃ¡quina).

#### HUB
- [x] **Dividir ecosystem.json em duas camadas: compartilhada e local por mÃ¡quina**
  Separar o `ecosystem.json` atual em dois arquivos:
  - `ecosystem.json` â€” preferÃªncias e flags (sem paths absolutos); sincronizado via Proton Drive entre mÃ¡quinas.
  - `ecosystem.local.json` â€” paths absolutos especÃ­ficos da mÃ¡quina (ex: `kosmos_archive`, `hermes_output`, `mnemosyne_watched`); **nÃ£o sincronizado**, fica sÃ³ na mÃ¡quina local.
  Na leitura de configuraÃ§Ã£o, mesclar os dois: `.local.json` tem precedÃªncia sobre `.json`.
  Adicionar `ecosystem.local.json` ao `.gitignore` e ao `.stignore` do Syncthing.
  Arquivo `.local.json` de exemplo (com paths comentados) pode ser versionado para documentaÃ§Ã£o.

- [x] **Migrar sync de SQLite (banco do HUB e bancos dos apps) para Syncthing**
  O Proton Drive conflita com SQLite (lock de arquivo / WAL). Usar Syncthing com `.stignore`
  excluindo `*.db`, `*.db-wal`, `*.db-shm`. Syncthing cuida de Markdown, JSON de config,
  pesquisas.md, TODO.md e outros arquivos de texto. Bancos ficam locais por mÃ¡quina.
  Instalar como serviÃ§o ou daemon; configurar par de dispositivos (Windows â†” CachyOS).

### LOGOS: arquitetura de skill routing multi-agente via arquivos .md | 2026-05-12
> Contexto: pesquisa sobre o padrÃ£o Agent Skills Specification (Anthropic, out/2025) e
> arquitetura two-model router (RouteLLM, arXiv:2406.18665) revelou um caminho viÃ¡vel para
> o LOGOS orquestrar tarefas por tipo usando arquivos .md como definiÃ§Ã£o de habilidades.
> Dispatcher pequeno (3B, sempre aquecido) + executor maior (7B+) por skill.

#### LOGOS
- [x] **Estrutura `logos/skills/` com SKILL.md por tipo de tarefa** â€” criar diretÃ³rio
  `logos/skills/` no HUB. Cada skill Ã© um arquivo `<nome>.md` com frontmatter YAML obrigatÃ³rio:
  `name` (slug, max 64 chars) e `description` (max 1024 chars â€” descreve QUANDO usar o skill,
  nÃ£o apenas o que faz; Ã© o Ãºnico campo lido pelo dispatcher na fase de seleÃ§Ã£o). Corpo Markdown
  com: (a) instruÃ§Ãµes completas de execuÃ§Ã£o; (b) 2-4 pares few-shot inputâ†’output; (c) output
  format especificado explicitamente com exemplo de JSON; (d) instruÃ§Ã£o final "responda APENAS
  no formato especificado". Skills iniciais: `rag-query.md`, `synthesis.md`,
  `entity-extraction.md`, `chunk-classification.md`. PadrÃ£o diretamente compatÃ­vel com
  Agent Skills Specification (agentskills.io).

- [x] **Dispatcher com dois modelos** â€” implementar `logos/dispatcher.py`: modelo router 3B
  (ex: Llama 3.2 3B Instruct) sempre aquecido em memÃ³ria (`keep_alive: -1` via Ollama) recebe
  o request e retorna JSON `{"skill": "<nome>", "confidence": 0.0-1.0}`. Usar Pydantic +
  `format=SkillSelection.model_json_schema()` no Ollama Python SDK para forÃ§ar enum de skill
  names vÃ¡lidos e garantir JSON vÃ¡lido. Fallback para skill genÃ©rico se `confidence < 0.7`.
  Modelo executor 7B+ carregado sob demanda com `keep_alive` curto conforme prioridade LOGOS
  (P1/P2/P3). Overhead do dispatcher: 200â€“600 ms; latÃªncia total com modelos aquecidos: 1â€“3 s.
  Basear na arquitetura RouteLLM (arXiv:2406.18665, ICLR 2025).

- [x] **Routing 3-tier para minimizar overhead de LLM** â€” antes de acionar o dispatcher LLM,
  implementar dois filtros mais rÃ¡pidos: (1) regex/keyword matching para requests triviais e
  repetitivos (~80% dos casos, latÃªncia ~0 ms â€” ex: "resuma esse texto" â†’ sempre `synthesis`);
  (2) embedding similarity contra embeddings prÃ©-computados dos campos `description` de cada
  skill (para requests ambÃ­guos mas estruturados, latÃªncia ~50 ms); (3) LLM dispatcher apenas
  para casos que passem pelos dois filtros anteriores. Essa cadeia elimina o overhead do LLM
  para a maioria dos requests, reduzindo latÃªncia mÃ©dia do sistema.

- [x] **Command R 7B como executor do skill `rag-query`** â€” o Command R 7B (Cohere) Ã© o Ãºnico
  modelo sub-10B com treinamento explÃ­cito para grounded generation com citaÃ§Ã£o de fontes
  (grounding spans). Configurar o LOGOS para usar Command R 7B especificamente quando o
  dispatcher selecionar o skill `rag-query`, em vez do modelo executor padrÃ£o. Requer que
  o Command R 7B esteja disponÃ­vel via Ollama (`ollama pull command-r`). Consumo: ~5 GB VRAM
  em Q4_K_M â€” cabe na RX 6600 com margem.

### AKASHA: responsividade CSS e frontmatter enriquecido | 2026-05-12
> Contexto: o AKASHA usava apenas breakpoints de pixels fixos no CSS â€” comportamento quebrando em janelas de tamanhos intermediÃ¡rios nÃ£o convencionais. AlÃ©m disso, o frontmatter gerado nos arquivos arquivados carecia de campos essenciais para citaÃ§Ã£o (data de publicaÃ§Ã£o real, idioma, campos cientÃ­ficos completos, metadados de PDF).

#### AKASHA
- [x] **Responsividade CSS universal** â€” substituir breakpoints de largura fixa (`max-width: Xpx`) por layout fluido usando `clamp()`, `min()`, percentagens e `flex-wrap` natural. Containers (`search-wrapper`, `container`, `lenses-page`, `history-container`) devem usar `min()` com percentagem + max fixo em vez de `max-width: Npx` rÃ­gido. `topbar-search` deve ter `min-width` em percentagem. Eliminar saltos visuais entre breakpoints: o layout deve degradar suavemente em qualquer largura de janela, nÃ£o sÃ³ em 3-4 tamanhos canÃ´nicos.

- [x] **Frontmatter: acrescentar `description`, `sitename`, `tags` da pÃ¡gina** â€” em `archive_url()`, extrair via trafilatura `metadata.description` (meta description / OpenGraph), `metadata.sitename` (nome legÃ­vel do site, ex: "The Verge") e `metadata.tags`/`metadata.categories` (tags nativas da pÃ¡gina); mesclar tags nativas com as tags do usuÃ¡rio (usuÃ¡rio vem primeiro, depois tags da pÃ¡gina nÃ£o duplicadas). Adicionar `description` e `sitename` como campos novos no frontmatter.
- [x] **Campos universais em todos os arquivos arquivados** â€” em `archive_url()` em `archiver.py`, renomear `url` para `source_url` no frontmatter, mudar `date` para data de publicaÃ§Ã£o real do conteÃºdo (trafilatura `metadata.date`, formato `YYYY-MM-DD`) e adicionar campo separado `archived_at` com a data de download. Garantir que `author` e `language` sempre presentes (mesmo que vazios). Em `archive_pdf()`, mesma lÃ³gica: `source_url` em vez de `url`, `archived_at` para data de download, `language` detectado via `langdetect.detect(content_md[:2000])`.

- [x] **Campos especÃ­ficos para artigos cientÃ­ficos** â€” em `archive_url()`, quando `is_scientific=True`, incluir no frontmatter: `doi`, `arxiv_id`, `journal`, `abstract` (primeiros 500 chars do abstract extraÃ­do), `keywords` (lista quando disponÃ­veis via trafilatura ou metadados OpenGraph). DeduplicaÃ§Ã£o antes de baixar: verificar via `database.get_archived_by_doi(doi)` se jÃ¡ existe arquivo com mesmo DOI; se sim, retornar sem baixar novamente.

- [x] **Campos especÃ­ficos para PDFs de livros** â€” em `archive_pdf()`, usar `fitz.open(path).metadata` (jÃ¡ disponÃ­vel via pymupdf4llm) para extrair `isbn`, `publisher`, `year`; incluir no frontmatter apenas quando nÃ£o-vazios. `year` complementa `date` para livros onde sÃ³ o ano de publicaÃ§Ã£o Ã© conhecido.

### Mnemosyne: novos formatos de entrada â€” Kindle e imagens | 2026-05-06
> Contexto: pesquisa sobre eBook Kindle (AZW/AZW3/MOBI) e leitura de imagens em pipeline RAG
> revelou opÃ§Ãµes viÃ¡veis sem dependÃªncias pesadas. AZW/MOBI via `mobi` (PyPI, sem nativas);
> imagens via Tesseract local + fallback Ollama vision.

#### Mnemosyne
- [x] **Suporte a `.azw`, `.azw3`, `.mobi` em `core/loaders.py`** â€” adicionar funÃ§Ã£o `_load_mobi()`
  que usa `mobi.extract(file_path, tmpdir)` num `tempfile.TemporaryDirectory`. A saÃ­da pode ser:
  HTML (MOBI) â†’ BeautifulSoup como no EPUB; EPUB (AZW3) â†’ reutilizar `_load_epub()`; PDF
  (AZW Print Replica) â†’ reutilizar `PyPDFLoader`. Adicionar `.azw`, `.azw3`, `.mobi` em
  `_SUPPORTED_EXTENSIONS`. Em caso de DRM detectado (output vazio ou corrompido), retornar
  `DocumentLoadError` com mensagem "arquivo com DRM â€” nÃ£o Ã© possÃ­vel indexar". DependÃªncia:
  `pip install mobi`.

- [x] **Suporte a imagens (`.jpg`, `.jpeg`, `.png`, `.webp`) em `core/loaders.py`** â€” adicionar
  funÃ§Ã£o `_load_image()` com duas camadas: (1) Tesseract via `pytesseract` + `Pillow` como
  caminho principal (rÃ¡pido, sem GPU, compatÃ­vel com i5-3470); (2) fallback para Ollama vision
  (`/api/generate` com `images: [base64]`) usando o modelo configurado em `config.image_ocr_model`
  (default vazio = Tesseract only). Texto extraÃ­do vira um `Document` com metadata `source`,
  `source_type` e `ocr_engine` ("tesseract" ou "ollama:{model}"). Adicionar `.jpg`, `.jpeg`,
  `.png`, `.webp` em `_SUPPORTED_EXTENSIONS`. DependÃªncia: `pip install pytesseract Pillow`
  + Tesseract instalado no sistema (instruÃ§Ã£o no README). Campo `image_ocr_model` em
  `AppConfig` e `SetupDialog` (QLineEdit, opcional, placeholder "ex: moondream2").

### LOGOS: pull de modelo recomendado direto do HUB | 2026-05-13
> Contexto: o LOGOS detecta hardware e recomenda modelos (via /logos/hardware), mas não
> oferece forma de baixar o modelo caso ele ainda não esteja instalado no Ollama local.

#### HUB
- [ ] **Comando Tauri pull_model(model_name) em src-tauri/src/logos.rs** — executar
  ollama pull <model> como processo filho e emitir evento Tauri pull_progress com
  cada linha de stdout (progresso em tempo real). Retornar erro tipado se Ollama não
  estiver rodando ou se o nome do modelo for inválido.

- [ ] **Botão "Baixar modelo" na LogosView** — quando o LOGOS recomendar um modelo via
  /logos/hardware que não constar em GET /api/tags do Ollama local, exibir botão
  "⬇ Baixar [nome]" ao lado da recomendação. Ao clicar: invocar pull_model, exibir
  barra de progresso com texto da linha atual do ollama pull, desabilitar o botão
  durante o download.
### HUB: botÃ£o Iniciar Ollama com flags de hardware | 2026-05-13
> Contexto: o LOGOS jÃ¡ gerencia o Ollama apÃ³s iniciado, mas o usuÃ¡rio precisa iniciar o processo manualmente antes de usar o ecossistema. O HUB deve detectar o hardware e lanÃ§ar o Ollama com as variÃ¡veis de ambiente corretas por plataforma â€” AMD ROCm no CachyOS, CUDA/sem flags no laptop NVIDIA e no Windows CPU-only.

#### HUB
- [x] **`launch_ollama()` em `commands/launcher.rs`** â€” comando Tauri assÃ­ncrono que: (1) verifica se o Ollama jÃ¡ responde em `localhost:11434/api/tags` (reqwest, timeout 500ms); se sim, retorna `"already_running"`. (2) ConstrÃ³i o `Command` com as flags de hardware: Windows â†’ `ollama serve` (sem flags); Linux com `/dev/kfd` presente (AMD ROCm) â†’ `ollama serve` com `env("HSA_OVERRIDE_GFX_VERSION", valor_da_env_ou_"10.3.0")`; Linux sem `/dev/kfd` (NVIDIA ou CPU) â†’ `ollama serve` sem flags. (3) Spawn sem janela (`CREATE_NO_WINDOW` no Windows). Retorna `"launched"` ou `AppError::Io`.
- [x] **Registrar `launch_ollama` em `lib.rs`** â€” adicionar ao `tauri::generate_handler![]`.
- [x] **`launchOllama()` em `src/lib/tauri.ts`** â€” wrapper tipado: `call<string>('launch_ollama')`.
- [ ] **BotÃ£o na `LogosView.tsx`** â€” adicionar estado `ollamaOnline: boolean | null` (derivado de polling direto a `localhost:11434/api/tags` via `listModels()` do `ollama.ts`, a cada 4s); estado `launchStatus: 'idle' | 'starting' | 'error'`. Renderizar botÃ£o "Iniciar Ollama" visÃ­vel apenas quando `ollamaOnline === false`; durante `starting` mostra "Iniciandoâ€¦" e fica desabilitado; erro volta para "Iniciar Ollama" apÃ³s 3s. Posicionar na seÃ§Ã£o "AÃ§Ãµes" ao lado do botÃ£o "Silenciar Ollama".

### CODEX â€” Leitor centralizado do ecossistema | 2026-05-13
> Contexto: leitor read-only centralizado que suporta todos os formatos do ecossistema e centraliza highlights, notas e citaÃ§Ãµes em markdown. Inspirado no leitor do KOSMOS, mas KOSMOS mantÃ©m seu prÃ³prio leitor. Apps como AKASHA e Mnemosyne podem abrir arquivos diretamente no CODEX. Deve ter versÃ£o Android no futuro â€” por isso a stack Ã© **Tauri v2 + React + Rust** (mesma do HUB, toolchain jÃ¡ disponÃ­vel). Sem ediÃ§Ã£o de texto â€” apenas leitura, comentÃ¡rios, highlights e exportaÃ§Ã£o de citaÃ§Ãµes em MD.

#### CODEX â€” Fase 0: scaffold e design system
- [ ] **Criar projeto Tauri v2 em `CODEX/`** â€” `cargo tauri init` dentro da pasta do projeto; estrutura: `CODEX/src/` (React + TypeScript), `CODEX/src-tauri/` (Rust). `strict: true` no tsconfig. Copiar design system do AETHER/HUB sem modificaÃ§Ãµes: `tokens.css`, `animations.css`, `typography.css`, `components.css`, `CosmosLayer.tsx`, `Toast.tsx`, `ThemeToggle.tsx`.
- [ ] **Pasta sincronizada no Proton Drive** â€” `{sync_root}/codex/` com: `annotations.db` (SQLite com highlights, notas, citaÃ§Ãµes vinculadas ao path do arquivo), `exports/` (citaÃ§Ãµes exportadas em MD). Apenas anotaÃ§Ãµes sÃ£o sincronizadas â€” o conteÃºdo dos arquivos permanece onde estÃ¡. No `ecosystem.json`, adicionar seÃ§Ã£o `codex: { exe_path, sync_dir }`. O HUB deve incluir CODEX na barra de apps.
- [ ] **Registrar CODEX no ecosystem.json** â€” escrever `write_section("codex", { exe_path, sync_dir })` no startup. Adicionar `"codex"` ao `auto_discover_all_exe_paths()` no `launcher.rs` do HUB.

#### CODEX â€” Fase 1: abertura de arquivos e formatos
- [ ] **Suporte a MD e TXT** â€” leitura nativa em Rust via `std::fs::read_to_string`. MD renderizado como HTML no frontend via `react-markdown`. TXT exibido como texto prÃ©-formatado.
- [ ] **Suporte a PDF** â€” usar crate `pdf-extract` (`pdf-extract = "0.7"` no Cargo.toml) para extraÃ§Ã£o de texto por pÃ¡gina. RenderizaÃ§Ã£o no frontend como HTML paginado. Alternativa para PDFs com layout complexo: PDF.js via `<webview>` ou iframe â€” avaliar conforme qualidade de extraÃ§Ã£o.
- [ ] **Suporte a EPUB** â€” usar crate `epub` (`epub = "2"`) para iterar capÃ­tulos como HTML. Renderizar cada capÃ­tulo como seÃ§Ã£o navegÃ¡vel no frontend. Preservar imagens internas via data URI.
- [ ] **Suporte a DOCX** â€” usar crate `docx-rs` (`docx-rs = "0.4"`) para extraÃ§Ã£o de parÃ¡grafos e estilos bÃ¡sicos (negrito, itÃ¡lico, cabeÃ§alhos). Converter para HTML estruturado antes de enviar ao frontend.
- [ ] **Suporte a HTML** â€” para arquivos do archive do AKASHA (`.html`): renderizar diretamente na webview do Tauri (CSP permissiva para arquivos locais). Sanitizar links externos para nÃ£o abrir no leitor.
- [ ] **Seletor de arquivo** â€” janela principal com `tauri-plugin-dialog` para abrir arquivo, filtrado por extensÃ£o suportada. Estado inicial exibe tela de boas-vindas com drag-and-drop.

#### CODEX â€” Fase 2: anotaÃ§Ãµes e highlights
- [ ] **SQLite para anotaÃ§Ãµes** â€” `rusqlite` com tabelas: `highlights(id, file_path, start_char, end_char, color, created_at)`, `notes(id, file_path, start_char, text, created_at)`, `citations(id, file_path, start_char, end_char, excerpt, note, created_at)`. Path do DB: `{sync_dir}/annotations.db`. Schema migrations versionadas.
- [ ] **SeleÃ§Ã£o de texto e menu de contexto** â€” no frontend, capturar `mouseup` para detectar seleÃ§Ã£o de texto; exibir mini-toolbar com opÃ§Ãµes: "Highlight", "Nota", "Citar". Highlight aplica `<mark>` com cor configurÃ¡vel; Nota abre textarea inline; Citar abre modal de citaÃ§Ã£o.
- [ ] **Paleta de cores para highlights** â€” 5 cores fixas alinhadas ao design system: Ã¢mbar (`#F5C518`), verde (`var(--accent-green)`), azul (`var(--accent)`), rosa (`var(--ribbon)`), cinza (`var(--rule)`). SeleÃ§Ã£o via mini-toolbar.
- [ ] **Persistir e restaurar highlights** â€” ao abrir arquivo, consultar `annotations.db` por `file_path` e reinjetar highlights via `document.execCommand` ou substituiÃ§Ã£o de HTML. Para MD/TXT (offsets de char), usar `start_char`/`end_char`. Para PDF (offsets por pÃ¡gina), usar `page_num + start_char`.

#### CODEX â€” Fase 3: exportaÃ§Ã£o e integraÃ§Ã£o
- [ ] **Exportar citaÃ§Ã£o como MD** â€” botÃ£o "Exportar citaÃ§Ã£o" em cada anotaÃ§Ã£o; gera arquivo `.md` em `{sync_dir}/exports/` com frontmatter: `source_path`, `source_title`, `page` (se PDF), `date_cited`. Corpo: trecho entre aspas duplas + nota do usuÃ¡rio abaixo. Um arquivo por sessÃ£o de citaÃ§Ã£o (agregado por data).
- [ ] **Mecanismo "abrir no CODEX"** â€” CODEX lÃª `ecosystem.json` em `codex.open_request: { path, start_char? }` no startup e ao ganhar foco. ApÃ³s abrir, limpa o campo com `write_section("codex", { open_request: null })`. Outros apps escrevem nesse campo para solicitar abertura. TambÃ©m aceitar CLI arg `--open <path>` para lanÃ§amento direto.
- [ ] **BotÃ£o "Abrir no CODEX" no AKASHA** â€” no frontend do AKASHA (`archive_detail.html` ou equivalente), adicionar botÃ£o que escreve no `ecosystem.json` e depois faz `fetch` para lanÃ§ar o CODEX via endpoint do HUB ou diretamente via `open` shell.
- [ ] **BotÃ£o "Abrir no CODEX" no Mnemosyne** â€” no `_source_viewer` do Mnemosyne (`gui/main_window.py`), adicionar botÃ£o que escreve no `ecosystem.json` e lanÃ§a o CODEX com `subprocess.Popen`.
- [ ] **KOSMOS: CODEX como leitor externo** â€” em KOSMOS `gui/reader_window.py` (ou equivalente), adicionar opÃ§Ã£o "Abrir no CODEX" no menu do artigo aberto que usa o mesmo mecanismo de `open_request`.

#### CODEX â€” Fase 4: Android (futuro)
- [ ] **Configurar ambiente Tauri Android** â€” Android Studio + NDK + `cargo tauri android init`. O Tauri v2 jÃ¡ suporta Android nativamente; a UI React Ã© a mesma.
- [ ] **Adaptar UI para toque** â€” aumentar Ã¡reas de toque (mÃ­nimo 44Ã—44px), toolbar de anotaÃ§Ã£o acessÃ­vel por toque longo, scroll suave. Avaliar gestos: swipe para trocar capÃ­tulos (EPUB), pinch-to-zoom.
- [ ] **Sync de anotaÃ§Ãµes via Syncthing** â€” `annotations.db` em pasta monitorada pelo Syncthing; resolver conflitos por timestamp (mais recente vence).
- [ ] **Build APK de release** â€” `cargo tauri android build`; testar no dispositivo alvo.

### HUB LOGOS: modelos disponÃ­veis + parar Ollama + prioridade baixa no Windows | 2026-05-13
> Contexto: a lista de modelos no LOGOS mostrava apenas os carregados na VRAM. O usuÃ¡rio quer ver todos os modelos instalados com indicador de status por cor (verde = ativo na VRAM, amarelo = disponÃ­vel mas nÃ£o carregado), poder parar o Ollama pelo LOGOS, e no Windows lanÃ§ar o Ollama com prioridade de CPU abaixo do normal automaticamente.

#### HUB
- [x] **`OllamaModelEntry` em `logos.rs`** â€” novo struct serializÃ¡vel com campos: `name: String`, `status: String` ("active" | "available"), `size_vram_mb: u64` (VRAM usada; 0 se nÃ£o carregado), `size_disk_mb: u64` (tamanho em disco da `/api/tags`).
- [x] **`do_list_all_models()` em `logos.rs`** â€” faz duas chamadas ao Ollama: (1) `GET /api/ps` para modelos carregados â†’ mapa `name â†’ size_vram`; (2) `GET /api/tags` para todos os instalados â†’ lista completa. Mescla: se o modelo estÃ¡ em `/api/ps` â†’ status "active"; se sÃ³ em `/api/tags` â†’ status "available". Retorna `Vec<OllamaModelEntry>`.
- [x] **`logos_list_all_models` em `commands/logos.rs`** â€” comando Tauri que chama `do_list_all_models`.
- [x] **`stop_ollama()` em `commands/launcher.rs`** â€” mata o processo Ollama: Windows â†’ `taskkill /F /IM ollama.exe /T` (com `CREATE_NO_WINDOW`); Linux â†’ `pkill -f "ollama serve"`. Retorna `Ok(())` se o comando foi executado (mesmo que Ollama nÃ£o estivesse rodando).
- [x] **Prioridade baixa no Windows em `build_ollama_serve_command()`** â€” substituir `Command::new("ollama").arg("serve")` na branch Windows por `cmd /C start "" /belownormal /B ollama serve`, que instrui o Windows a lanÃ§ar o processo jÃ¡ com `BELOW_NORMAL_PRIORITY_CLASS` sem necessidade de `windows-sys`.
- [x] **Registrar novos comandos em `lib.rs`** â€” adicionar `logos_list_all_models` e `stop_ollama` ao `generate_handler![]`.
- [x] **`OllamaModelEntry` em `types/index.ts`** â€” interface TypeScript espelhando o struct Rust.
- [x] **`logosListAllModels()` e `stopOllama()` em `lib/tauri.ts`** â€” wrappers tipados.
- [x] **LogosView.tsx: lista de todos os modelos com bolinha colorida** â€” substituir a seÃ§Ã£o "Modelos na memÃ³ria" por "Modelos Ollama" que usa `logosListAllModels()` (polling a cada 4s). Cada linha: `â—` colorido (verde `var(--accent-green)` se "active", amarelo `var(--accent)` se "available") + nome + tamanho em disco + VRAM usada se "active". BotÃ£o "descarregar" mantido para modelos "active".
- [ ] **LogosView.tsx: botÃ£o "Parar Ollama"** â€” visÃ­vel apenas quando `ollamaOnline === true`. Clique chama `stopOllama()`, aguarda 1s e atualiza `checkOllama()`. Colocar na seÃ§Ã£o AÃ§Ãµes junto ao "Iniciar Ollama".


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
- [ ] **Inventario Windows 10 (WorkPc):** ja catalogado -- all-minilm:latest, smollm2:1.7b, qwen2.5:0.5b
- [ ] **Inventario CachyOS principal (MainPc):** catalogar -- NAME                 ID              SIZE      MODIFIED    
qwen2.5:0.5b         a8b0c5157701    397 MB    6 days ago     
smollm2:1.7b         cef4a1e09247    1.8 GB    7 days ago     
all-minilm:latest    1b226e2802db    45 MB     2 weeks ago     e anotar no contexto da pesquisa
- [ ] **Inventario Laptop:** catalogar -- NAME                 ID              SIZE      MODIFIED    
qwen2.5:0.5b         a8b0c5157701    397 MB    6 days ago     
smollm2:1.7b         cef4a1e09247    1.8 GB    7 days ago     
all-minilm:latest    1b226e2802db    45 MB     2 weeks ago     e anotar no contexto da pesquisa
- [ ] **Pesquisar LLMs para RAG (Mnemosyne)** -- sintese multi-doc, context window, portugues;
  garantir que os modelos escolhidos por hardware sejam compativeis (mesma familia ou instruction format)
- [ ] **Pesquisar LLMs para analise/sumarizacao (KOSMOS e AKASHA)** -- artigos longos, velocidade
  de streaming; no MainPc o modelo KOSMOS pode ser diferente do Mnemosyne para rodar simultaneamente
- [ ] **Pesquisar modelos de embedding multilingues** -- qualidade pt/en, velocidade por hardware;
  bge-m3 vs nomic-embed-text vs all-minilm vs potion-multilingual-128M
- [ ] **Atualizar perfis em ** apos pesquisa -- 
  e ; possivelmente adicionar slot AKASHA
