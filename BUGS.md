# Histórico de Bugs — Ecossistema

Registro permanente de bugs detectados durante desenvolvimento e uso real.
Ordenado por data crescente — novos bugs sempre acrescentados no final do arquivo.

**Status:** `[FIXED]` · `[OPEN]` · `[INVESTIGATING]`  
**Descoberta:** `uso-real` · `teste-automatizado` · `revisão-de-código` · `tentativa-de-feature`

---

## Template para novos registros

```
### BUG-NNN · [STATUS] · Título curto descritivo

#### Identificação
- **Data:** YYYY-MM-DD
- **App(s):** nome dos apps envolvidos
- **Componente:** arquivo ou módulo específico
- **Commit do fix:** `hash` (ou "pendente")
- **Descoberta via:** uso-real | teste-automatizado | revisão-de-código | tentativa-de-feature
- **Tempo de diagnóstico:** estimativa

#### Ambiente
- **Máquina(s) afetadas:** WorkPC / MainPC / Laptop / todas
- **OS:** Windows 10 / CachyOS / Fedora
- **Hardware relevante:** CPU, GPU, VRAM se aplicável
- **Modo:** dev (cargo tauri dev / uv run) | produção | teste (cargo test)
- **Reproduzível em:** lista de ambientes onde foi confirmado

#### Pré-condição para reproduzir
Passos mínimos ou estado necessário para o bug aparecer.

#### Sintoma observado
O que aparece para o usuário ou no terminal — comportamento visível.

#### Logs
```
colar trecho exato de stderr/stdout aqui
```

#### Causa raiz
Explicação técnica detalhada do que estava errado e por quê.

#### Impacto
O que parou de funcionar. Classificar: bloqueante / degradação / cosmético.

#### Tentativas anteriores (opcional)
Abordagens que foram tentadas e por que não funcionaram.

#### Fix aplicado
O que foi mudado, em qual arquivo, e por que resolve.

#### Teste de regressão
Qual teste cobre o caso agora, ou por que não existe um.
```

---

## Índice

| ID | Status | Data | App | Título resumido |
|---|---|---|---|---|
| [BUG-001](#bug-001) | FIXED | 2026-05-25 | HUB/LOGOS | models_dir retorna lista vazia em dev (CWD ignorado) |
| [BUG-002](#bug-002) | FIXED | 2026-05-25 | HUB/LOGOS + Mnemosyne | /v1/embeddings retorna 501 sem --pooling mean |
| [BUG-003](#bug-003) | FIXED | 2026-05-25 | HUB/LOGOS | llama-server roda em CPU por falta de --n-gpu-layers |
| [BUG-004](#bug-004) | FIXED | 2026-05-25 | HUB/LOGOS | Servidor llama-server órfão bloqueia toggle_inference |
| [BUG-005](#bug-005) | FIXED | 2026-05-25 | HUB | STATUS_ENTRYPOINT_NOT_FOUND nos testes Rust no Windows |
| [BUG-006](#bug-006) | FIXED | 2026-05-26 | HUB/LOGOS | Download smollm2:1.7b falha com 404 — filename errado no HuggingFace |
| [BUG-007](#bug-007) | FIXED | 2026-05-26 | HUB/LOGOS | CPU usage sempre 0% no Windows — refresh e leitura no mesmo tick |
| [BUG-008](#bug-008) | FIXED | 2026-05-26 | HUB/LOGOS | embed-server não inicia — name no registry não corresponde ao embed_model |
| [BUG-009](#bug-009) | FIXED | 2026-05-27 | HUB/LOGOS | embed-server em loop — bge-m3-Q4_K_M.gguf corrompido (download incompleto) |
| [BUG-010](#bug-010) | FIXED | 2026-05-27 | Mnemosyne | SQLITE_READONLY_DBMOVED ao reindexar — ChromaDB SharedSystem com conexão stale |
| [BUG-011](#bug-011) | FIXED | 2026-05-27 | Ecossistema | shared_topic_profile.db corrompido — "database disk image is malformed" sem recuperação |
| [BUG-012](#bug-012) | FIXED | 2026-05-30 | AKASHA | Race condition em insight/current: overlay duplicado + feedback "sem resposta" no HUB |
| [BUG-013](#bug-013) | FIXED | 2026-05-30 | HUB/LOGOS | proxy_openai_to_llama sem lazy loading — knowledge_worker recebia 502 Bad Gateway |
| [BUG-014](#bug-014) | FIXED | 2026-05-30 | HUB/LOGOS | lazy loading ignorava perfil de hardware — carregava 7B em vez de 3B para AKASHA |
| [BUG-015](#bug-015) | FIXED | 2026-05-30 | HUB/LOGOS | proxy_openai_to_llama sem hardware guards, model switching ou active state tracking |
| [BUG-016](#bug-016) | FIXED | 2026-05-30 | HUB/LOGOS | embed-server sem lazy loading — Mnemosyne recebia 503 em /v1/embeddings |
| [BUG-017](#bug-017) | FIXED | 2026-05-31 | AKASHA | db.run_sync() inexistente em aiosqlite 0.22.x — código morto em _reindex e init_vec_index |
| [BUG-018](#bug-018) | FIXED | 2026-06-01 | AKASHA | knowledge_worker deadlock — fila baixa com >50 itens nunca drena |
| [BUG-019](#bug-019) | FIXED | 2026-06-02 | AKASHA | page_count em crawl_sites desincronizado com crawl_pages — 14/16 domínios sem páginas reais |
| [BUG-020](#bug-020) | FIXED | 2026-06-02 | HUB/LOGOS + AKASHA + Mnemosyne | embed-server retorna HTTP 500 com requisições concorrentes de múltiplos apps |
| [BUG-021](#bug-021) | FIXED | 2026-06-02 | AKASHA (base.html) | feedbackInsight() sempre retorna cedo — feedback de insight nunca chega ao servidor |
| [BUG-022](#bug-022) | FIXED | 2026-06-02 | AKASHA (extension/background.js) | extensão consome slot de insight sem exibir quando aba ativa é o próprio AKASHA |
| [BUG-023](#bug-023) | FIXED | 2026-06-02 | AKASHA (tests/test_domain_suggester.py) | teste usa domínio-semente (ravelry.com) como exemplo de domínio não-indexado |
| [BUG-024](#bug-024) | FIXED | 2026-06-02 | AKASHA (routers/search.py) | `from services.crawler import _bg_crawl` falha silenciosamente — confirmar domain_suggestion nunca dispara o crawl |
| [BUG-025](#bug-025) | FIXED | 2026-06-02 | AKASHA (services/web_search.py) | Chave de cache de busca web ignora `n_pages` — buscas leves envenenam o volume das reais |
| [BUG-026](#bug-026) | FIXED | 2026-06-03 | HUB (commands/searxng.rs) | "Testar conexão" do SearXNG falha para instância remota (healthcheck gateado por systemd local) |

---

## Bugs

---

### BUG-001 · [FIXED] · models_dir retorna lista vazia em modo dev (CWD/logos/models ignorado)

#### Identificação
- **Data:** 2026-05-25
- **App(s):** HUB, LOGOS
- **Componente:** `HUB/src-tauri/src/logos.rs` — `LogosState::new()`, cálculo de `models_dir`
- **Commit do fix:** `f7abf5f` (lógica), `39ea82b` (extração + testes)
- **Descoberta via:** uso-real (lista de modelos vazia ao ligar IA em dev)
- **Tempo de diagnóstico:** ~10 minutos

#### Ambiente
- **Máquina(s) afetadas:** WorkPC (Windows 10) em modo dev — possivelmente também Laptop em dev
- **OS:** Windows 10 Pro 22H2
- **Hardware relevante:** N/A
- **Modo:** dev (`cargo tauri dev` / `npm run tauri dev`)
- **Reproduzível em:** qualquer máquina onde `data_local_dir/ecosystem/hub/logos/models/registry.json` não existe (setup inicial de desenvolvimento)

#### Pré-condição para reproduzir
1. `cargo tauri dev` rodando (CWD = `HUB/src-tauri/`)
2. Modelos instalados em `HUB/src-tauri/logos/models/` (com `registry.json`)
3. `%LOCALAPPDATA%\ecosystem\hub\logos\models\registry.json` **não existe** (máquina de desenvolvimento sem dados de produção)

#### Sintoma observado
Ao clicar "Ligar IA" no HUB em dev, o dropdown de modelos aparecia vazio. O comando `logos_list_models` retornava lista vazia.

#### Logs
```
# Backend (RUST_LOG=info):
[INFO logos] LOGOS: models_dir = C:\Users\USUARIO\AppData\Local\ecosystem\hub\logos\models
# → sem "fallback para CWD" → nenhum modelo encontrado

# O CWD real tinha os modelos:
# HUB/src-tauri/logos/models/registry.json  ← ignorado
```

#### Causa raiz
`LogosState::new()` calculava `models_dir` a partir de `dirs::data_local_dir()` (caminho XDG/AppData). Em desenvolvimento, esse diretório não tem `registry.json` — os modelos ficam em `CWD/logos/models/` porque é onde o HUB os baixa durante `cargo tauri dev`.

O fallback para CWD existia no código mas estava implementado incorretamente: verificava `!xdg_dir.join("registry.json").exists()` mas não logava nem ativava o caminho CWD consistentemente.

#### Impacto
**Bloqueante em dev.** Impossível testar o fluxo de carregamento de modelos sem simular o ambiente de produção (copiar `registry.json` para AppData manualmente).

#### Fix aplicado
Lógica extraída para `pub(crate) fn pick_models_dir(xdg: PathBuf, cwd_logos_models: PathBuf) -> PathBuf`:

```rust
pub(crate) fn pick_models_dir(xdg: PathBuf, cwd_logos_models: PathBuf) -> PathBuf {
    if xdg.join("registry.json").exists() { return xdg; }
    if cwd_logos_models.join("registry.json").exists() {
        log::info!("LOGOS: models_dir fallback para CWD: {}", cwd_logos_models.display());
        return cwd_logos_models;
    }
    xdg
}
```

`LogosState::new()` agora chama `pick_models_dir(xdg_dir, cwd_dir)` em vez do bloco inline.

#### Teste de regressão
3 testes determinísticos com `tempfile::tempdir` em `logos::tests`:
- `pick_models_dir_prefers_xdg_when_xdg_has_registry`
- `pick_models_dir_falls_back_to_cwd_when_only_cwd_has_registry`
- `pick_models_dir_uses_xdg_when_neither_has_registry`

Substitui o teste condicional anterior que só validava algo se o ambiente real fosse dev.

---

### BUG-002 · [FIXED] · /v1/embeddings retorna 501 Not Implemented no llama-server

#### Identificação
- **Data:** 2026-05-25
- **App(s):** HUB / LOGOS, Mnemosyne
- **Componente:** `HUB/src-tauri/src/logos.rs` — `spawn_llama_server_proc`; `Mnemosyne/core/vectorstore.py` — chamada ao endpoint
- **Commit do fix:** `da15c62`
- **Descoberta via:** uso-real (primeira tentativa de indexar documentos após migração Ollama → llama-server)
- **Tempo de diagnóstico:** ~20 minutos

#### Ambiente
- **Máquina(s) afetadas:** MainPC (CachyOS) — não testado no Windows nesta data
- **OS:** CachyOS
- **Hardware relevante:** RX 6600 8 GB VRAM
- **Modo:** produção
- **Reproduzível em:** qualquer máquina com llama-server sem `--pooling mean`

#### Pré-condição para reproduzir
1. llama-server rodando sem `--pooling mean`
2. Mnemosyne tenta indexar qualquer coleção
3. `POST http://localhost:8081/v1/embeddings` é chamado

#### Sintoma observado
Ao clicar "Indexar tudo" na Mnemosyne, a indexação falhava imediatamente. Nenhum arquivo era indexado. Barra de progresso não avançava.

#### Logs
```
# Mnemosyne (stderr):
ERROR - Embeddings request failed: 501 Not Implemented
POST http://localhost:8081/v1/embeddings → 501
{"error": {"code": 501, "message": "This server does not support embeddings", "type": "not_implemented_error"}}

# llama-server stdout:
[Warning] Pooling type not specified. Using no pooling.
```

#### Causa raiz
O endpoint `/v1/embeddings` do llama-server requer que um modo de pooling seja especificado via flag `--pooling <tipo>` no startup (valores válidos: `mean`, `cls`, `last`, `rank`). Sem a flag, o servidor ativa `PoolingType::None` e o endpoint retorna 501 para qualquer requisição.

A flag não estava sendo incluída no spawn do processo em `spawn_llama_server_proc`.

#### Impacto
**Bloqueante.** Toda a indexação da Mnemosyne parava. RAG inoperante. Bug bloqueou o primeiro uso real após a migração completa de Ollama para llama-server — a migração havia sido concluída mas nunca testada end-to-end.

#### Fix aplicado
```rust
cmd.arg("--pooling").arg("mean");
```
Adicionado ao bloco de args em `spawn_llama_server_proc`, junto com `--cont-batching`.

`mean` é o modo recomendado para modelos de embedding e de chat usados para embeddings (faz média dos token embeddings como representação da sequência).

#### Teste de regressão
Pendente — cobre o mesmo cenário do item `logos.rs — teste de spawn_llama_server_proc com flags obrigatórias` no TODO. Um teste que inspeciona os args do processo spawned cobriria `--pooling mean`, `--n-gpu-layers` e `--port` simultaneamente.

---

### BUG-003 · [FIXED] · llama-server roda em CPU por padrão sem --n-gpu-layers

#### Identificação
- **Data:** 2026-05-25
- **App(s):** HUB, LOGOS
- **Componente:** `HUB/src-tauri/src/logos.rs` — função `spawn_llama_server_proc`
- **Commit do fix:** `aa23ec3`
- **Descoberta via:** uso-real (monitoramento de VRAM no HUB mostrava 0%)
- **Tempo de diagnóstico:** ~15 minutos

#### Ambiente
- **Máquina(s) afetadas:** MainPC (CachyOS, RX 6600)
- **OS:** CachyOS (Arch Linux)
- **Hardware relevante:** AMD Radeon RX 6600, 8 GB VRAM, ROCm com `HSA_OVERRIDE_GFX_VERSION=10.3.0`
- **Modo:** produção
- **Reproduzível em:** qualquer máquina com GPU onde `n_gpu_layers = -1` (offload total) estava configurado

#### Pré-condição para reproduzir
1. Perfil LOGOS com `n_gpu_layers = -1` (valor padrão para "offload tudo para GPU")
2. Ligar a IA via HUB
3. Observar uso de VRAM / velocidade de inferência

#### Sintoma observado
Após ligar a IA, a inferência era extremamente lenta (~0.5 tok/s em vez de ~15 tok/s). O monitor de VRAM no HUB mostrava 0 MB de uso. O sistema ficava com ~6 GB de RAM ocupada pelo llama-server.

#### Logs
```bash
# Processo spawned sem --n-gpu-layers:
llama-server --model /path/model.gguf --ctx-size 4096 --parallel 2 --cont-batching \
  --pooling mean --port 8081

# Correto (após fix):
llama-server --model /path/model.gguf --ctx-size 4096 --parallel 2 --cont-batching \
  --pooling mean --n-gpu-layers 9999 --port 8081
```

```
# llama-server stdout sem a flag:
llm_load_tensors: offloaded 0/33 layers to GPU
```

#### Causa raiz
O llama-server **não usa GPU por padrão** — requer `--n-gpu-layers N` explícito. Sem a flag, todos os layers rodam em CPU.

O código usava `-1` como valor sentinela para "offload máximo". A condição de geração da flag era:

```rust
if n_gpu == 0 {
    cmd.arg("--n-gpu-layers").arg("0");
} else if n_gpu > 0 {
    cmd.arg("--n-gpu-layers").arg(n_gpu.to_string());
}
// n_gpu == -1 não entrava em nenhum branch → sem flag → CPU
```

#### Impacto
**Degradação severa de performance.** Inferência 30× mais lenta. RAM saturada. Em máquinas com pouca RAM (WorkPC, 8 GB), poderia travar o sistema.

#### Fix aplicado
Adicionado branch `else` para o caso `-1`:

```rust
} else {
    // n_gpu == -1: offload total — llama-server não usa GPU sem esta flag
    cmd.arg("--n-gpu-layers").arg("9999");
}
```

O valor `9999` é a convenção do llama-server para "offload máximo possível" — ele ajusta automaticamente para o número real de layers do modelo.

#### Teste de regressão
Não há teste automatizado cobrindo os args de GPU (requer mock de processo ou inspeção de `Command` antes do spawn). Pendente: BUG-003 motivou o item `logos.rs — teste de spawn_llama_server_proc com flags obrigatórias` no TODO de auditoria.

---

### BUG-004 · [FIXED] · Servidor llama-server órfão bloqueia toggle_inference

#### Identificação
- **Data:** 2026-05-25
- **App(s):** HUB, LOGOS
- **Componente:** `HUB/src-tauri/src/commands/launcher.rs` — função `toggle_inference`
- **Commit do fix:** `f7abf5f`
- **Descoberta via:** uso-real (tentativa de ligar a IA após crash/reinício do HUB)
- **Tempo de diagnóstico:** ~30 minutos

#### Ambiente
- **Máquina(s) afetadas:** todas (reproduzível em qualquer máquina)
- **OS:** Windows 10 e CachyOS (confirmado em ambos)
- **Hardware relevante:** N/A
- **Modo:** produção / dev
- **Reproduzível em:** qualquer sessão onde o llama-server ficou rodando após o HUB fechar

#### Pré-condição para reproduzir
1. Iniciar o HUB e ligar a IA (llama-server sobe)
2. Fechar o HUB abruptamente (sem clicar "Desligar IA") — o llama-server continua rodando como órfão
3. Reiniciar o HUB
4. Clicar "Ligar IA"

#### Sintoma observado
O botão "Ligar IA" retornava instantaneamente sem progresso visível. A UI não mostrava erro nem barra de carregamento. O modelo nunca era carregado. Clicar repetidamente não resolvia.

#### Logs
```
# No frontend (DevTools console):
toggle_inference result: "already_running"

# No backend (RUST_LOG=debug):
[LOGOS] toggle_inference: server responding=true, llama_proc_active=false
# → código retornava "already_running" sem verificar llama_proc_active
```

#### Causa raiz
`toggle_inference(enable=true)` verificava `llama_server_responding()` (ping HTTP a `localhost:8081/health`) para detectar servidor ativo. Se o ping respondia, assumia que o servidor era gerenciado pelo HUB e retornava `"already_running"` imediatamente.

Um servidor órfão (processo vivo mas sem `llama_proc` registrado no `LogosState`) responde ao ping normalmente. A função nunca chegava a verificar `llama_proc_active()`. Resultado: HUB incapaz de iniciar a IA enquanto o órfão existisse.

#### Impacto
**Bloqueante para uso da IA.** O único workaround era matar o processo manualmente via gerenciador de tarefas antes de abrir o HUB.

#### Fix aplicado
Lógica extraída para `do_toggle_inference(state, enable, server_responding)`. Quando `enable=true` e `server_responding=true`, verifica `llama_proc_active()`:
- Se ativo → retorna `"already_running"` (comportamento correto)
- Se não ativo → chama `kill_orphaned_llama_server()` para matar o órfão, depois inicia processo próprio

```rust
if server_responding {
    if state.llama_proc_active().await {
        return Ok("already_running".into());
    }
    kill_orphaned_llama_server().await; // mata o órfão
}
// continua para iniciar processo rastreado
```

Além disso, `process_group(0)` foi removido do spawn do llama-server no Linux: antes, o processo ficava num group separado e sobrevivia ao HUB. Agora herda o group do HUB e morre junto.

#### Teste de regressão
`toggle_enable_server_responding_proc_active_returns_already_running` (unix-only) em `commands/launcher.rs` — cobre o caso onde servidor responde E proc está ativo → deve retornar `already_running` sem spawnar novo processo.

O caso "servidor órfão" (server_responding=true, proc_active=false) → mata e reinicia — coberto implicitamente pelo fluxo do `do_toggle_inference`, mas sem teste isolado ainda (requer mock de processo HTTP).

---

### BUG-005 · [FIXED] · STATUS_ENTRYPOINT_NOT_FOUND ao iniciar testes Rust do HUB no Windows

#### Identificação
- **Data:** 2026-05-25
- **App(s):** HUB
- **Componente:** `HUB/src-tauri/` — binário de testes unitários (`cargo test --lib`)
- **Commit do fix:** `6dc763f`
- **Descoberta via:** tentativa-de-feature (escrever os primeiros testes unitários do backend Rust)
- **Tempo de diagnóstico:** ~4 horas (causa raiz não óbvia — processo aborta antes de qualquer output Rust)

#### Ambiente
- **Máquina(s) afetadas:** WorkPC (Windows 10) — não ocorre no CachyOS nem no Laptop
- **OS:** Windows 10 Pro 22H2 (build 19045)
- **Hardware relevante:** Intel i5-3470, sem AVX2, sem GPU dedicada
- **Modo:** teste (`cargo test --lib`)
- **Reproduzível em:** qualquer máquina Windows 10/11 sem manifest ComCtl32 v6 no binário de testes

#### Pré-condição para reproduzir
1. Windows 10 ou 11
2. `HUB/src-tauri/` com `tauri-plugin-dialog` como dependência
3. Rodar `cargo test --lib` (não `cargo build`, não `npm run tauri dev`)

#### Sintoma observado
`cargo test --lib` encerrava imediatamente, antes de imprimir qualquer linha de output. Código de saída: `0xC0000139`. Nenhum teste chegava a executar. O Cargo reportava apenas "Finished" e em seguida o processo filho morria.

#### Logs
```
Finished `test` profile [unoptimized + debuginfo] target(s) in Xm Xs
Running unittests src\lib.rs (target\debug\deps\hub_lib-2f627c204cbd413e.exe)
error: test failed, to rerun pass `--lib`

Caused by:
  process didn't exit successfully: `...\hub_lib-2f627c204cbd413e.exe`
  (exit code: 0xc0000139, STATUS_ENTRYPOINT_NOT_FOUND)
```

Diagnóstico com `llvm-readobj`:
```
llvm-readobj --coff-imports target\debug\deps\hub_lib-*.exe | findstr -i comctl32
# output: Import { Name: comctl32.dll }
# seguido de: TaskDialogIndirect
```

Verificação da DLL carregada via PowerShell:
```powershell
$dll = [System.Runtime.InteropServices.NativeLibrary]::Load("comctl32.dll")
$fn  = [System.Runtime.InteropServices.NativeLibrary]::GetExport($dll, "TaskDialogIndirect")
# $fn == 0 → função não existe na versão carregada (v5.82)
```

#### Causa raiz
O PE loader do Windows resolve a tabela de imports estática do binário **antes de `main()` executar**. `tauri-plugin-dialog` (dependência do HUB) importa `TaskDialogIndirect` de `comctl32.dll`.

O Windows carrega `comctl32` v5.82 por padrão quando o binário não tem um manifest ativando `Microsoft.Windows.Common-Controls v6.0.0.0`. A v5.82 não exporta `TaskDialogIndirect` — essa função existe apenas na v6 (que fica em `C:\Windows\WinSxS\`). O loader não encontra o símbolo, emite `STATUS_ENTRYPOINT_NOT_FOUND` e aborta o processo.

O `hub.exe` não sofre o problema porque o Tauri embute um manifest `RT_MANIFEST` no executável via `resource.lib` (compilado de `.rc` e linkado via `cargo:rustc-link-arg-bins`). Esse manifest declara a v6 e o Windows a carrega antes de qualquer código executar. O binário de testes é gerado pelo Rust sem esse manifest.

#### Impacto
**Bloqueante.** Impossível rodar qualquer teste unitário do backend Rust no Windows. Toda a auditoria de cobertura de testes do HUB estava bloqueada por este bug.

#### Tentativas anteriores

**1. `cargo:rustc-link-arg-tests` com manifest `.rc`**  
Criar `test_manifest.rc` + compilar para `.res` + emitir via `cargo:rustc-link-arg-tests`. Não funcionou: apesar da documentação do Cargo afirmar que a instrução aplica a "todos os binários de teste incluindo os de `#[test]` em arquivos de biblioteca" (desde Rust 1.56), na prática só se aplica a targets `[[test]]` explícitos no `Cargo.toml`, não a unit tests compilados do `[lib]`. Confirmado via `llvm-readobj --coff-resources` — seção de resources permanecia vazia.

**2. `/MANIFEST:EMBED` via `cargo:rustc-link-arg`**  
Tentar embedar manifest via flag do linker MSVC globalmente. Causou `CVTRES: recurso duplicado` no `hub.exe`, que já tem manifest via `resource.lib` do Tauri. Targets `bin` e testes recebem o mesmo `cargo:rustc-link-arg`.

#### Fix aplicado
`HUB/src-tauri/build.rs` emite `/DELAYLOAD:comctl32.dll` e `delayimp.lib` via `cargo:rustc-link-arg` (aplica a todos os targets):

```rust
if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
    println!("cargo:rustc-link-arg=/DELAYLOAD:comctl32.dll");
    println!("cargo:rustc-link-arg=delayimp.lib");
}
```

O delay-loading move a resolução de `comctl32` da tabela de imports estática para uma tabela de imports lazy — a DLL só é carregada no primeiro uso real da função. Como testes nunca chamam funções de diálogo (`TaskDialogIndirect`, `TaskDialog`), a DLL nunca é carregada e o símbolo nunca é resolvido.

O `hub.exe` não é afetado: o manifest do Tauri ativa comctl32 v6 antes de qualquer diálogo ser chamado, então o delay-loading é seguro também em produção.

#### Teste de regressão
Não há teste automatizado para este fix (seria necessário um teste de processo que verifica o código de saída do binário de testes em si). O fix é verificado indiretamente: se regredir, **todos** os 126 testes unitários falharão antes de executar no Windows.

---

### BUG-006 · [FIXED] · Expansão morfológica gera query FTS5 inválida em buscas multi-palavra

#### Identificação
- **Data:** 2026-05-25
- **App(s):** AKASHA
- **Componente:** `AKASHA/services/local_search.py` — função `_expand_query_stems`
- **Commit do fix:** pendente
- **Descoberta via:** teste-automatizado (ao escrever `test_search_integration.py`)
- **Tempo de diagnóstico:** ~30 minutos

#### Ambiente
- **Máquina(s) afetadas:** todas (qualquer máquina com langdetect + NLTK instalados no venv)
- **OS:** Windows 10 (confirmado); CachyOS provavelmente afetado também
- **Hardware relevante:** não aplicável
- **Modo:** produção + testes
- **Reproduzível em:** qualquer ambiente onde langdetect e nltk estejam instalados no venv AKASHA

#### Pré-condição para reproduzir
1. Venv AKASHA com `langdetect` e `nltk` instalados (ambos presentes no `pyproject.toml`)
2. Query de dois ou mais tokens em português ou inglês (ex: `"python recente"`)
3. Pelo menos um token stem-expansível (ex: "recente" → stem "recent")

#### Sintoma observado
Busca local (`search_local("python recente")`) retorna `[]` silenciosamente, mesmo com documentos indexados que contêm os termos. Queries de palavra única ("python") funcionam normalmente.

#### Logs
```python
# Expansão gerada (ERRADA):
_expand_query_stems("python recente", "python recente")
# → 'python (recente OR recent*)'

# SQLite FTS5:
conn.execute("SELECT * FROM local_fts WHERE local_fts MATCH 'python (recente OR recent*)'")
# → sqlite3.OperationalError: fts5: syntax error near "OR"

# Erro silenciado por:
try:
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute(...)  # query explode aqui
        ...
except Exception:
    pass  # ← retorna [] sem avisar
```

#### Causa raiz
`_expand_query_stems` expande cada token de `"python recente"` individualmente:
- `"python"` → `"python"` (stem igual ao token, sem expansão)
- `"recente"` → `"(recente OR recent*)"` (stem "recent" ≠ token "recente")

E então junta as partes com `" ".join(parts)`, produzindo `"python (recente OR recent*)"`.

O FTS5 do SQLite interpreta espaço como AND implícito. A sequência `token (A OR B)` é **sintaxe inválida** porque o FTS5 não aceita AND implícito entre um token simples e um grupo `(...)` contendo `OR`. O error code é `fts5: syntax error near "OR"`.

Essa restrição está documentada no SQLite: tokens simples podem ser combinados com AND implícito entre si, mas parênteses com OR dentro exigem `AND` explícito do token anterior.

#### Impacto
**Silencioso e severo.** Qualquer query de 2+ palavras em PT ou EN com NLTK instalado retornava `[]` sem aviso. A usuária nunca veria resultados de busca local multi-palavra (a situação mais comum em uso real). O erro era mascarado pelo `except Exception: pass` em `_search_fts`.

#### Tentativas anteriores
Nenhuma — bug descoberto diretamente durante a escrita dos testes.

#### Fix aplicado
`_expand_query_stems` em `AKASHA/services/local_search.py` — mudança de `" ".join(parts)` para `" AND ".join(parts)`:

```python
# Antes (ERRADO):
return " ".join(parts)
# Produzia: 'python (recente OR recent*)'  ← FTS5 syntax error

# Depois (CORRETO):
return " AND ".join(parts)
# Produz: 'python AND (recente OR recent*)'  ← válido
# Também correto para tokens sem expansão:
# 'python AND recente' ≡ 'python recente' (AND implícito e explícito são equivalentes)
```

O `AND` explícito é semanticamente equivalente ao AND implícito para tokens simples, e resolve o syntax error para tokens expandidos com `(A OR B)`.

O docstring foi atualizado para refletir a saída correta: `(buscando OR busc*) AND (artigos OR artig*)`.

#### Teste de regressão
`AKASHA/tests/test_search_integration.py::TestConflictingBoosts::test_conflicting_pagerank_and_freshness_preserves_all_results` — verifica que buscas multi-palavra com query temporal encontram documentos indexados. Antes do fix, retornava `[]`.

---

### BUG-006 · [FIXED] · Download smollm2:1.7b falha com 404 — filename errado no HuggingFace

#### Identificação
- **Data:** 2026-05-26
- **App(s):** HUB, LOGOS
- **Componente:** `HUB/src-tauri/src/commands/logos.rs` — `model_hf_table()`
- **Commit do fix:** `b4b1550`
- **Descoberta via:** uso-real (tentativa de download pelo painel LOGOS)
- **Tempo de diagnóstico:** ~5 minutos

#### Ambiente
- **Máquina(s) afetadas:** WorkPC (Windows 10) — qualquer máquina ao tentar baixar smollm2:1.7b
- **OS:** Windows 10 Pro
- **Hardware relevante:** N/A (erro de rede, não de hardware)
- **Modo:** dev e produção
- **Reproduzível em:** qualquer máquina com acesso ao HuggingFace

#### Pré-condição para reproduzir
Tentar baixar o modelo `smollm2:1.7b` pelo painel LOGOS ("Baixar modelo").

#### Sintoma observado
Erro `HuggingFace retornou 404 Not Found` ao tentar fazer download de smollm2:1.7b.
O modelo qwen2.5:0.5b baixava normalmente (filename correto).

#### Logs
```
HuggingFace retornou 404 Not Found
URL: https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B-Instruct-GGUF/resolve/main/SmolLM2-1.7B-Instruct-Q4_K_M.gguf
```

#### Causa raiz
O filename mapeado em `model_hf_table` estava em CamelCase (`SmolLM2-1.7B-Instruct-Q4_K_M.gguf`), mas o arquivo real no repo HuggingFaceTB/SmolLM2-1.7B-Instruct-GGUF é todo em letras minúsculas (`smollm2-1.7b-instruct-q4_k_m.gguf`). HuggingFace trata URLs de download como case-sensitive — o servidor retorna 404 para qualquer divergência de capitalização.

#### Impacto
**Bloqueante** para download de smollm2:1.7b. Modelos com filename correto (qwen, gemma, bge-m3) não são afetados.

#### Fix aplicado
Corrigido o filename em `model_hf_table` para `smollm2-1.7b-instruct-q4_k_m.gguf` (tudo minúsculo).
Adicionado teste de regressão `hf_table_smollm2_filename_is_lowercase` que verifica o valor exato.

#### Teste de regressão
`commands::logos::tests::hf_table_smollm2_filename_is_lowercase` — verifica que o filename mapeado é `smollm2-1.7b-instruct-q4_k_m.gguf` (minúsculo). Falha imediatamente se o filename for revertido para CamelCase.

---

### BUG-007 · [FIXED] · CPU usage sempre 0% no Windows — refresh e leitura no mesmo tick

#### Identificação
- **Data:** 2026-05-26
- **App(s):** HUB, LOGOS
- **Componente:** `HUB/src-tauri/src/logos.rs` — `cpu_ram_usage()`, `metrics_stream_handler`, `collect_status`
- **Commit do fix:** (nesta sessão)
- **Descoberta via:** uso-real (painel LOGOS exibindo 0% de CPU no WorkPC Windows 10)
- **Tempo de diagnóstico:** ~15 minutos (análise de chamadas concorrentes)

#### Ambiente
- **Máquina(s) afetadas:** WorkPC (Windows 10) — confirmado; possivelmente laptop (Windows com PDH)
- **OS:** Windows 10 Pro
- **Hardware relevante:** CPU Intel i5-3470 (sem AVX2)
- **Modo:** dev e produção
- **Reproduzível em:** Windows — Linux usa /proc/stat com resolução mais alta, menos afetado

#### Pré-condição para reproduzir
Abrir painel LOGOS no HUB com o SSE stream de métricas ativo (qualquer uso normal).

#### Sintoma observado
Barra/valor de CPU no painel LOGOS exibe permanentemente 0% no Windows. RAM e VRAM exibem corretamente.

#### Logs
```
# Nenhum log de erro — o valor simplesmente retorna 0.0 silenciosamente
```

#### Causa raiz
`cpu_ram_usage()` chamava `sys.refresh_cpu_all()` imediatamente seguido de `sys.global_cpu_usage()` na mesma função. O valor de CPU% em sysinfo é calculado como delta entre duas chamadas consecutivas de `refresh_cpu_all()`. Dois callers concorrentes usavam o mesmo `Mutex<System>`:

1. `metrics_stream_handler` — loop SSE, chama a cada 1s
2. `collect_status` — chamado a cada 4s pelo frontend

Quando `collect_status` adquiria o mutex logo após `metrics_stream_handler` (poucos ms de diferença), o delta de tempo entre os dois `refresh_cpu_all()` era < 15ms. No Windows (PDH — Performance Data Helper), o acumulador de tempo de CPU só atualiza a cada ~15ms (quantum do scheduler). Com delta < 1 quantum → Δ idle = Δ kernel = Δ user = 0 → CPU% = 0.

No Linux, `/proc/stat` tem resolução de clock ticks (~10ms) e o problema era menos severo; no Windows é reproduzível consistentemente.

#### Impacto
**Cosmético** (o guard de CPU ainda funciona, mas usa a leitura inline dentro do guard — que também pode ser 0). Os guards de CPU para P3 (`CPU_P3_BLOCK = 85%`) liam o mesmo valor e potencialmente nunca bloqueavam mesmo com CPU saturada.

#### Fix aplicado
1. Removido `s.refresh_cpu_all()` de `cpu_ram_usage()` — a função passou a apenas ler `global_cpu_usage()` (último valor computado) e `refresh_memory()`.
2. Adicionado `cpu_watchdog` background task em `start_server()`: faz `refresh_cpu_all()` exclusivamente, a cada 1s, com sleep de 200ms antes da primeira leitura para garantir baseline não-zero no Windows.
3. O watchdog é o único caller de `refresh_cpu_all()` — sem contention, sem delta zero.

#### Teste de regressão
`logos::tests::cpu_watchdog_is_sole_caller_of_refresh_cpu_all` — verifica que `cpu_ram_usage` não chama `refresh_cpu_all` (análise estática via grep do código compilado seria ideal, mas o teste verifica indiretamente via snapshot de `global_cpu_usage` entre chamadas sem refresh). Complementado por teste de integração manual no Windows.

---

### BUG-008 · [FIXED] · embed-server não inicia — name no registry não corresponde ao embed_model do ecosystem.json

#### Identificação
- **Data:** 2026-05-26
- **App(s):** HUB (LOGOS)
- **Componente:** `logos.rs::ensure_embed_server_started`, `logos/models/registry.json`, `ecosystem.json`
- **Commit do fix:** (ver commit fix/BUG-008)
- **Descoberta via:** uso-real (Mnemosyne retornou 503 ao tentar indexar)
- **Tempo de diagnóstico:** ~15 min

#### Ambiente
- **Máquina(s) afetadas:** MainPC (CachyOS)
- **OS:** CachyOS
- **Hardware relevante:** RX 6600 8GB VRAM
- **Modo:** dev (cargo tauri dev)
- **Reproduzível em:** qualquer máquina onde registry.json tem o nome de quantização em vez do nome canônico

#### Pré-condição
- bge-m3-Q4_K_M.gguf presente em `logos/models/`
- `ecosystem.json["logos"]["embed_model"]` ausente (valor default do código: `"bge-m3"`)
- `registry.json` com entry `name = "bge-m3-Q4_K_M"` (nome gerado automaticamente no download)

#### Sintoma
```
httpx.HTTPStatusError: Server error '503 Service Unavailable'
for url 'http://127.0.0.1:7072/v1/embeddings'
```
No HUB: "servidor de embedding offline". Log interno: `"LOGOS embed: modelo 'bge-m3' não encontrado no registry"`.

#### Causa raiz
`ensure_embed_server_started()` chama `resolve_gguf_path(embed_model, models_dir)`. A função busca o modelo por:
1. `entry.name == "bge-m3"` → FALSE (entry.name era "bge-m3-Q4_K_M")
2. `entry.filename == "bge-m3"` → FALSE
3. `entry.filename.trim_end_matches(".gguf") == "bge-m3"` → FALSE ("bge-m3-Q4_K_M" ≠ "bge-m3")

Nenhuma correspondência → `None` → embed-server não sobe.

Causa secundária: `ecosystem.json` não tinha o campo `logos.embed_model` explícito → código usava default `"bge-m3"`, que deveria funcionar **se** o registry estivesse correto.

Causa terciária: `ensure_embed_server_started` só logava `log::warn!` ao falhar, sem alerta visível na UI — o usuário via apenas "offline" sem explicação.

#### Impacto
- Mnemosyne e qualquer app que use `/v1/embeddings` recebe 503 permanentemente
- Nenhuma indexação possível enquanto embed_model não for encontrado no registry

#### Fix
1. `registry.json`: renomear entry `"bge-m3-Q4_K_M"` → `"bge-m3"` + adicionar `"model_type": "embed"` em todas as entradas
2. `ecosystem.json`: definir `logos.embed_model = "bge-m3"` e `logos.embed_port = 8082` explicitamente
3. `logos.rs::ensure_embed_server_started`: chamar `emit_alert("warn", msg)` quando modelo não encontrado no registry — erro aparece na UI do HUB

#### Testes de regressão
- `logos::tests::resolve_gguf_path_finds_bge_m3_by_canonical_name` — registry com `name="bge-m3"` → `resolve_gguf_path("bge-m3")` retorna `Some`
- `logos::tests::resolve_gguf_path_does_not_find_bge_m3_when_registry_name_has_quantization_suffix` — registry com `name="bge-m3-Q4_K_M"` → `resolve_gguf_path("bge-m3")` retorna `None` (confirma que a busca é por nome exato)

---

### BUG-009 · [FIXED] · embed-server em loop de reinicialização — bge-m3-Q4_K_M.gguf corrompido (download incompleto)

#### Identificação
- **Data:** 2026-05-26
- **App(s):** HUB (LOGOS), Mnemosyne
- **Componente:** `logos/models/bge-m3-Q4_K_M.gguf`, `logos.rs::embed_watchdog`
- **Commit do fix:** pendente
- **Descoberta via:** uso-real (Mnemosyne retornou 502 ao tentar indexar, após fix do BUG-008)
- **Tempo de diagnóstico:** ~5 min

#### Ambiente
- **Máquina(s) afetadas:** MainPC (CachyOS)
- **OS:** CachyOS
- **Hardware relevante:** RX 6600 8 GB VRAM
- **Modo:** dev (cargo tauri dev)
- **Reproduzível em:** qualquer máquina com o mesmo arquivo truncado

#### Pré-condição
- BUG-008 corrigido (registry name = "bge-m3", ecosystem.json atualizado)
- `bge-m3-Q4_K_M.gguf` presente mas com apenas **32 MB** dos **417 MB** esperados (download interrompido)

#### Sintoma
```
httpx.HTTPStatusError: Server error '502 Bad Gateway' for url 'http://127.0.0.1:7072/v1/embeddings'
```
Log do LOGOS:
```
E llama_model_load: error loading model: tensor 'token_embd.weight' data is not within the file bounds, model is corrupted or incomplete
E srv  llama_server: exiting due to model loading error
ERROR LOGOS embed-watchdog: embed-server saiu inesperadamente (modelo='bge-m3', status=ExitStatus(unix_wait_status(256)))
WARN  LOGOS embed-watchdog: tentando reiniciar 'bge-m3'
[... loop a cada ~10 segundos indefinidamente ...]
```

#### Causa raiz
Dois problemas independentes:
1. **Arquivo GGUF truncado:** o download do `bge-m3-Q4_K_M.gguf` foi interrompido com apenas 32 MB (7,3% do arquivo). O llama-server lê o cabeçalho GGUF com sucesso, mas os dados do tensor `token_embd.weight` ficam fora dos limites do arquivo.
2. **Watchdog sem circuit breaker:** `embed_watchdog` detecta que o processo morreu e tenta 1 restart via `ensure_embed_server_started`. O servidor reinicia, falha imediatamente pelo mesmo motivo, morre novamente, e o ciclo se repete a cada 10 segundos sem limite de tentativas para falhas permanentes.

#### Impacto
- Mnemosyne e qualquer app que use `/v1/embeddings` recebe 502 permanentemente
- CPU e I/O consumidos pelo loop de restart a cada 10 segundos

#### Fix
**Arquivo corrompido (operação imediata):**
1. Deletar `logos/models/bge-m3-Q4_K_M.gguf` (32 MB, inválido)
2. Atualizar `registry.json`: remover ou marcar a entry como inválida
3. Re-baixar o modelo via downloader do HUB (`logos_download_model`)

**Código — circuit breaker no watchdog (previne loops futuros):**
- Rastrear `consecutive_fast_fails: u8` no embed watchdog
- "Fast fail" = servidor sai em < 3 segundos após spawn
- Após 2 fast fails consecutivos: parar de reiniciar, chamar `emit_alert("error", ...)`, aguardar intervenção manual
- Reset do contador quando servidor fica ativo por ≥ 30 segundos

#### Testes de regressão
- `logos::tests::embed_watchdog_stops_after_consecutive_fast_fails` — mock de processo que sai imediatamente → watchdog deve parar após N tentativas e não reiniciar indefinidamente

---

### BUG-011 · [FIXED] · shared_topic_profile.db corrompido sem recuperação automática

#### Identificação
- **Data:** 2026-05-27
- **App(s):** Ecossistema (shared_topic_profile.py — usado por AKASHA, Mnemosyne, KOSMOS)
- **Componente:** `shared_topic_profile.py` — `_ensure_db()`, `update_scores()`
- **Commit do fix:** `d9d7a33`
- **Descoberta via:** uso-real
- **Tempo de diagnóstico:** ~10 minutos

#### Ambiente
- **Máquina(s) afetadas:** MainPC (CachyOS)
- **OS:** CachyOS (Arch Linux)
- **Reproduzível em:** qualquer máquina onde o DB seja corrompido

#### Pré-condição
`shared_topic_profile.db` está com estrutura SQLite inválida — causada provavelmente por escrita interrompida ou Syncthing sobrescrevendo o arquivo durante WAL.

#### Sintoma
```
WARNING ecosystem.shared_topic_profile: shared_topic_profile.update_scores falhou: database disk image is malformed
```
Erro repetido a cada chamada de `update_scores`. O banco permanece corrompido indefinidamente — não havia mecanismo de recuperação.

#### Causa raiz
`_ensure_db` fazia `con.executescript(_DDL)` sem capturar `sqlite3.DatabaseError`. Quando o banco estava corrompido, a exceção propagava para `update_scores`, que a capturava como `Exception` e logava como WARNING — mas o banco continuava corrompido para todas as chamadas subsequentes. Backup JSON era gerado a cada escrita mas nunca usado para recuperação.

#### Impacto
- Perfil de interesses do ecossistema não é atualizado enquanto corrompido
- Aba "Interesses" no HUB mostra dados desatualizados
- Não afeta outras funcionalidades (erro é não-fatal)

#### Fix
1. `_recreate_from_backup(path)`: apaga o banco corrompido + WAL/SHM sidecars, recria schema limpo, restaura dados do backup JSON se disponível.
2. `_ensure_db`: captura `sqlite3.DatabaseError` com mensagens "malformed", "corrupt" ou "not a database" → chama `_recreate_from_backup`. Outros `DatabaseError` propagam normalmente.
3. Recuperação imediata manual via `_recreate_from_backup` — 4600 tópicos restaurados do JSON.

#### Teste de regressão
Arquivo: `tests/test_shared_topic_profile_db.py` — 6 novos testes (`TestCorruptionRecovery`):
- `test_ensure_db_recovers_from_corrupt_db_without_backup` — corrupção sem backup → banco vazio, sem crash
- `test_ensure_db_restores_data_from_backup_json` — corrupção com JSON → dados restaurados
- `test_update_scores_transparent_recovery` — update_scores funciona normalmente após recuperação
- `test_recreate_removes_wal_and_shm` — sidecars antigos são removidos
- `test_ensure_db_does_not_swallow_non_corrupt_errors` — DatabaseError não-corrupção propaga
- `test_recreate_backup_json_malformed_does_not_crash` — JSON inválido → banco vazio, sem crash

### BUG-010 · [FIXED] · SQLITE_READONLY_DBMOVED ao reindexar — ChromaDB SharedSystem com conexão stale

#### Identificação
- **Data:** 2026-05-27
- **App(s):** Mnemosyne
- **Componente:** `Mnemosyne/core/indexer.py` — `load_all_vectorstores()`; `Mnemosyne/gui/main_window.py` — `_release_vectorstore()`
- **Commit do fix:** pendente
- **Descoberta via:** uso-real
- **Tempo de diagnóstico:** ~45 minutos

#### Ambiente
- **Máquina(s) afetadas:** MainPC (CachyOS)
- **OS:** CachyOS (Arch Linux)
- **Hardware relevante:** n/a
- **Modo:** produção
- **Reproduzível em:** qualquer máquina com chromadb ≥ 1.5.x

#### Pré-condição
1. Mnemosyne abre com `ecosystem_chroma_dir` configurado
2. `chroma_db` existe no disco mas está vazio (count == 0) — ex: após falha anterior ou Syncthing mover o conteúdo
3. Usuária clica em "Indexar tudo"

#### Sintoma
```
chromadb.errors.InternalError: Error updating collection:
Database error: error returned from database: (code: 1032)
attempt to write a readonly database
```
Erro ocorre em `workers.py:249` na primeira chamada `vs._collection.add()` do IndexWorker.

#### Logs
```
2026-05-27 06:45:15,428 [INFO] gui.workers: IndexWorker: 30 arquivos a indexar
2026-05-27 06:45:25,449 [ERROR] gui.workers: IndexWorker: erro fatal no probe de embedding
...
chromadb.errors.InternalError: Error updating collection: Database error: error returned from database: (code: 1032) attempt to write a readonly database
```

#### Causa raiz
**SQLite error 1032 = `SQLITE_READONLY_DBMOVED`:** ocorre quando SQLite detecta que o arquivo do banco de dados foi movido/substituído após a conexão ser aberta (inode antigo ≠ inode atual no mesmo path).

**Cadeia de eventos:**
1. Mnemosyne inicia → `load_all_vectorstores()` → `load_vectorstore()` abre `Chroma(persist_directory=eco_chroma_dir)`
2. `vs._collection.count() == 0` → `load_all_vectorstores` retorna `[]` **sem chamar `vs._client.close()`**
3. `langchain_chroma.Chroma` não implementa `__del__` com `close()` (confirmado no comment de `_release_vectorstore` em `main_window.py:1524`)
4. `SharedSystemClient` do chromadb mantém a conexão SQLite aberta para o path `eco_chroma_dir` com refcount > 0
5. Usuária clica "Indexar tudo" → `_release_vectorstore()` → fecha `self.vectorstore.stores` (que está vazio) → sem efeito na conexão stale
6. `shutil.rmtree(eco_chroma_dir)` apaga o diretório incluindo `chroma.sqlite3` (inode X)
7. `os.makedirs(persist_dir)` recria o diretório vazio
8. `IndexWorker` → `Chroma(persist_directory=same_path)` → ChromaDB SharedSystem ainda tem entrada para o path → tenta reutilizar a conexão stale (inode X)
9. IndexWorker tenta escrever → SQLite compara inode no path atual (inode Y) com o inode registrado na conexão (X) → `SQLITE_READONLY_DBMOVED`

**`_release_vectorstore()` também não parava `IndexReflectionWorker`**, que cria seu próprio `Chroma()` interno não rastreado por `self.vectorstore.stores`.

#### Impacto
- Indexação completamente bloqueada — toda tentativa de "Indexar tudo" falha
- Usuária fica sem acesso ao RAG da Mnemosyne
- Não afeta o chat (LLM continua funcionando sem RAG)

#### Fix
**`indexer.py` — `load_all_vectorstores` (fix primário):**
```python
if vs._collection.count() == 0:
    try:
        vs._client.close()  # ← ADICIONADO — evita conexão stale no SharedSystem
    except Exception:
        pass
    return []
```

**`main_window.py` — `_release_vectorstore` (fix de segurança):**
1. Adicionar `_index_reflection_worker` à lista de workers a parar (usava `requestInterruption()` em vez de `quit()`)
2. Ao final, chamar `SharedSystemClient.clear_system_cache()` para garantir limpeza total do SharedSystem

#### Teste de regressão
Arquivo: `Mnemosyne/tests/test_index_clear.py` — 6 novos testes (8–13):
- `test_load_all_vectorstores_closes_connection_when_empty` — close() explícito antes de retornar [] previne stale
- `test_clear_system_cache_empties_registry` — `clear_system_cache()` zera `_identifier_to_system` e `_identifier_to_refcount`
- `test_reindex_after_empty_vectorstore_no_dbmoved` — cenário completo do BUG-010: abre vazio → close → clear → apaga dir → recria → escreve sem erro
- `test_multiple_opens_accumulate_refcount` — refcount cresce com múltiplas instâncias no mesmo path
- `test_close_decrements_refcount_to_zero` — close() libera refcount corretamente
- `test_clear_system_cache_works_with_pending_references` — clear_system_cache() funciona mesmo com conexões não-fechadas

---

### BUG-012 · [FIXED] · Race condition em /insight/current: overlay duplicado + feedback "sem resposta"

**Identificação:** BUG-012
**Data:** 2026-05-30
**App:** AKASHA — `routers/search.py` + `services/session_insight.py` + `services/personal_memory.py`
**Status:** FIXED

#### Ambiente
- CachyOS principal, AKASHA rodando com extensão de browser ativa + interface web AKASHA aberta simultaneamente

#### Pré-condição
- Usuária com AKASHA aberto na interface web E extensão de browser instalada
- Ambos polam `GET /insight/current` a cada ~10 segundos

#### Sintoma
1. **Overlay duplicado:** mesmo insight aparece uma vez na interface AKASHA e uma segunda vez pelo overlay da extensão
2. **"Sem resposta" no HUB:** na aba Comms, a entrada correspondente aparece com `feedback=NULL` mesmo após a usuária ter dado OK no overlay

#### Logs / comportamento observado
- Usuária clica OK no overlay da extensão
- Em `/communicacoes` (aba Comms do HUB) o insight aparece mas sem feedback registrado
- O overlay reaparece ou aparece simultaneamente em dois lugares

#### Causa raiz
Race condition em `GET /insight/current`:

```
UI poll:  lê _pm_current=None ──────────────────────►──────►  set_pm_current(c) → _pm_shown_by={}
                                                              ↓
Ext poll: lê _pm_current=None ──►  await get_next_overlay  ──►  set_pm_current(c) → _pm_shown_by={}  ← RESET!
```

Como `get_next_for_overlay` e `mark_shown_as_overlay` têm `await`, duas coroutines (UI + extensão) liam `_pm_current=None` antes que qualquer uma o populasse. Ambas chamavam `mark_shown_as_overlay(mesmo_id)` → criavam **duas linhas** em `communication_history`. O `set_pm_current` subsequente resetava `_pm_shown_by=set()`, destruindo a guarda anti-duplicata.

Resultado: ambas retornavam o insight (duplicata), e quando o feedback chegava, só atualizava o `comm_id` mais recente em `personal_memory` — a entrada mais antiga em `communication_history` ficava com `feedback=NULL`.

#### Impacto
- Usuária vê o mesmo insight duas vezes por sessão
- Linha orphã em `communication_history` com `feedback=NULL` permanece para sempre
- A reflexão de feedback (`_reflect_on_feedback`) pode ser disparada duas vezes

#### Fix
**`services/session_insight.py`:** adicionado `pm_load_lock: asyncio.Lock()` global.

**`routers/search.py`:** bloco "carregar próxima entrada de PM" envolvido com `async with _si.pm_load_lock:` + double-check após adquirir o lock (padrão check-lock-recheck).

**`services/personal_memory.py`:** guarda de idempotência em `mark_shown_as_overlay`: se `shown_as_overlay=1` e `comm_id IS NOT NULL`, retorna sem criar segunda linha em `communication_history`.

#### Teste de regressão
- Verificar que dois polls simultâneos de `GET /insight/current` produzem exatamente **uma** entrada em `communication_history` (não duas)
- Verificar que após feedback em um consumidor, a entrada em comms aparece com feedback preenchido

---

### BUG-013 · [FIXED] · proxy_openai_to_llama sem lazy loading — knowledge_worker recebia 502

#### Identificação
- **Data:** 2026-05-30
- **App(s):** HUB/LOGOS, AKASHA
- **Componente:** `HUB/src-tauri/src/logos.rs` — `proxy_openai_to_llama`, `v1_chat_completions_proxy`
- **Commit do fix:** `d785667`
- **Descoberta via:** uso-real (log do AKASHA: `knowledge_worker: inferência falhou na extração: Server error '502 Bad Gateway' for url 'http://127.0.0.1:7072/v1/chat/completions'`)
- **Tempo de diagnóstico:** ~15 minutos

#### Ambiente
- **Máquina(s) afetadas:** CachyOS principal
- **OS:** CachyOS (Arch Linux)
- **Hardware relevante:** RX 6600 8 GB VRAM
- **Modo:** produção (HUB rodando, IA ligada)

#### Pré-condição para reproduzir
1. LOGOS rodando com `inference_enabled=true` (IA ligada no HUB)
2. Nenhum modelo carregado ainda (lazy loading pendente — nenhuma requisição anterior)
3. AKASHA knowledge_worker chama `POST /v1/chat/completions`

#### Sintoma
AKASHA knowledge_worker recebia `502 Bad Gateway` em toda tentativa de extração LLM, mesmo com a IA ligada no HUB.

#### Logs
```
akasha.knowledge_worker: knowledge_worker: inferência falhou na extração:
Server error '502 Bad Gateway' for url 'http://127.0.0.1:7072/v1/chat/completions'
```

#### Causa raiz
O lazy loading (carregar modelo na primeira requisição real) foi implementado em `queue_and_forward` — que serve as rotas Ollama-style (`/api/chat`, `/api/generate`). A rota OpenAI-compatible `POST /v1/chat/completions`, servida por `proxy_openai_to_llama`, não tinha o mesmo mecanismo.

`proxy_openai_to_llama` ia direto ao proxy sem verificar se o llama-server estava rodando. Resultado: connection refused ao llama-server (porta 8081) → `reqwest` reportava como 502.

O AKASHA knowledge_worker usa exclusivamente a rota `/v1/chat/completions` (OpenAI-compatible), nunca `/api/chat` (Ollama-style).

#### Impacto
Bloqueante: AKASHA não conseguia extrair tópicos, entidades nem gerar reflexões de nenhuma página crawleada. Análise de conhecimento completamente inoperante.

#### Fix
`proxy_openai_to_llama`: adicionado gate de `inference_enabled` + bloco de lazy loading idêntico ao de `queue_and_forward`, com chamada a `model_for_app` e `ensure_llama_model_loaded`.

#### Teste de regressão
Testes existentes: `lazy_load_no_models_returns_503_no_models`, `lazy_load_first_request_triggers_load`, `inference_enabled_false_rejects_requests` (cobrem `queue_and_forward`). O gate de `inference_enabled` na rota OpenAI é coberto pela lógica compartilhada — não há teste isolado de `proxy_openai_to_llama` por limitação de setup (não tem servidor HTTP real em testes unitários).

---

### BUG-014 · [FIXED] · lazy loading ignorava perfil de hardware — carregava modelo errado

#### Identificação
- **Data:** 2026-05-30
- **App(s):** HUB/LOGOS
- **Componente:** `HUB/src-tauri/src/logos.rs` — `queue_and_forward`, `proxy_openai_to_llama` (após BUG-013)
- **Commit do fix:** `bf5a0ce`
- **Descoberta via:** uso-real (HUB mostrava qwen2.5:7b carregado quando recomendado para AKASHA é qwen2.5:3b)
- **Tempo de diagnóstico:** ~20 minutos

#### Ambiente
- **Máquina(s) afetadas:** CachyOS principal (MainPc — perfil com llm_query=qwen2.5:3b, llm_rag=qwen2.5:7b)
- **OS:** CachyOS (Arch Linux)
- **Modo:** produção

#### Pré-condição para reproduzir
1. Dois ou mais modelos LLM instalados no registry do LOGOS
2. O modelo configurado para o app solicitante (`llm_query` para AKASHA) não é o primeiro da lista
3. AKASHA knowledge_worker faz requisição (lazy loading ativado)

#### Sintoma
O LOGOS carregava o primeiro modelo LLM instalado (qwen2.5:7b) em vez do modelo configurado para AKASHA (qwen2.5:3b via `llm_query` no perfil MainPc).

#### Causa raiz
O lazy loading usava `select_model_to_load_llm(&names)` — função que retorna o **primeiro modelo instalado** que não seja embedding. Não consultava:
- `model_overrides` (overrides da usuária por app)
- `hardware_profile.model_profile()` (llm_query / llm_rag / llm_analysis por hardware)

O perfil do LOGOS tem campos separados por app+função: `llm_query` (AKASHA), `llm_rag` (Mnemosyne), `llm_analysis` (KOSMOS). Esses campos eram ignorados completamente no lazy loading.

#### Impacto
Degradação funcional: AKASHA recebia respostas de um modelo maior/diferente do esperado, consumindo mais VRAM e potencialmente dando respostas fora do esperado para o perfil de uso. Todo o gerenciamento de hardware (VRAM pre-check, GPU layers, CPU fallback) era calculado para o modelo errado.

#### Fix
Nova função `model_for_app(s: &LogosState, app_name: &str) -> Option<String>`:
- Mapeia `app_name` → slot de modelo (`akasha`→`llm_query`, `mnemosyne`→`llm_rag`, `kosmos`→`llm_analysis`)
- Respeita overrides da usuária (`model_overrides["akasha_llm_query"]`)
- Fallback: modelo recomendado do perfil de hardware → primeiro LLM instalado (se não instalado)
- Ambos `queue_and_forward` e `proxy_openai_to_llama` passaram a usar `model_for_app`

#### Teste de regressão
6 novos testes unitários: `model_for_app_akasha_uses_llm_query_from_profile`, `model_for_app_mnemosyne_uses_llm_rag_from_profile`, `model_for_app_override_takes_priority_over_profile`, `model_for_app_falls_back_when_configured_not_installed`, `model_for_app_unknown_app_uses_first_llm`, `model_for_app_no_models_installed_returns_none`.

---

### BUG-015 · [FIXED] · proxy_openai_to_llama sem hardware guards, model switching ou active state

#### Identificação
- **Data:** 2026-05-30
- **App(s):** HUB/LOGOS
- **Componente:** `HUB/src-tauri/src/logos.rs` — `proxy_openai_to_llama`
- **Commit do fix:** `1d5eaa8`
- **Descoberta via:** revisão-de-código (auditoria do LOGOS após BUG-013 e BUG-014)
- **Tempo de diagnóstico:** ~30 minutos

#### Ambiente
- **Máquina(s) afetadas:** todas (guards são especialmente críticos no Laptop MX150 2GB e WorkPc i5)

#### Pré-condição para reproduzir
Qualquer requisição via `POST /v1/chat/completions` (AKASHA knowledge_worker) em condições de pressão de recursos.

#### Sintoma
Múltiplas ausências em relação à rota Ollama (`queue_and_forward`):
1. AKASHA knowledge_worker continuava enviando LLM requests mesmo com VRAM > 85%, CPU saturada ou em modo bateria
2. Se Mnemosyne carregava o 7B (via `/api/chat`), AKASHA recebia respostas do 7B em vez do 3B configurado
3. Após 3 crashes do llama-server (`llama_disabled=true`), requests ainda eram tentados pela rota OpenAI
4. UI/métricas do HUB não mostravam que AKASHA estava usando o LOGOS (active_priority/app/model_class permaneciam None)
5. P1 (HUB chat) não conseguia preemptar P3 (AKASHA knowledge_worker) pela rota OpenAI

#### Causa raiz
`proxy_openai_to_llama` foi adicionada como rota simplificada, sem as proteções que `queue_and_forward` acumulou ao longo do tempo:
- Sem gate de `llama_disabled`
- Sem hardware guards P3 (VRAM watchdog, VRAM per-request, CPU/RAM, bateria)
- Sem hardware guards P2 (CPU em bateria)
- Sem model switching (model switching só acontecia no lazy loading — quando proc não estava ativo)
- Sem active state tracking (active_priority, active_app, active_model_class)
- Sem P1 preemption

Adicionalmente: `knowledge_worker.py` faz chamadas httpx diretas **sem `X-App` header**, então `app_name=""` e `model_for_app` caía no fallback (primeiro LLM). O campo `"model"` do body JSON (que contém o modelo correto via `_get_llm_query_model()`) não era usado como source of truth.

#### Impacto
- Degradação funcional em condições de pressão de recursos: AKASHA não era throttleado, podendo causar freeze no sistema (especialmente Laptop e WorkPc)
- Modelo errado servindo requisições AKASHA quando outro modelo estava carregado
- Métricas do HUB imprecisas (não refletiam atividade OpenAI-route)
- llama_disabled não respeitado na rota OpenAI

#### Fix
`proxy_openai_to_llama` reescrita com paridade completa ao `queue_and_forward`:
- Gate de `llama_disabled`
- Hardware guards P3 (bateria, p3_vram_blocked, VRAM per-request, CPU/RAM com limites survival vs normal)
- Hardware guards P2 (CPU em bateria)
- Model switching: `ensure_llama_model_loaded` chamado sempre (fast path se modelo correto já carregado)
- Active state tracking: set antes do proxy, clear após
- P1 preemption via `try_preempt_p3`
- Seleção de modelo: body `"model"` field tem prioridade sobre `model_for_app` (suporte a chamadas sem X-App header)

#### Teste de regressão
Sem testes isolados para `proxy_openai_to_llama` (requer servidor HTTP mock completo). Os guards individuais são cobertos pelos testes de `queue_and_forward` e pelos novos testes de `model_for_app`. Regressão verificada via `cargo test` — 295+ testes passando.

---

### BUG-016 · [FIXED] · embed-server sem lazy loading — Mnemosyne recebia 503 em /v1/embeddings

#### Identificação
- **Data:** 2026-05-30
- **App(s):** HUB/LOGOS, Mnemosyne
- **Componente:** `HUB/src-tauri/src/logos.rs` — `v1_embeddings_proxy`, `queue_and_forward`, `proxy_openai_to_llama`
- **Commit do fix:** (próximo commit)
- **Descoberta via:** uso-real (`httpx.HTTPStatusError: Server error '503 Service Unavailable' for url 'http://127.0.0.1:7072/v1/embeddings'` no indexer da Mnemosyne)
- **Tempo de diagnóstico:** ~10 minutos

#### Ambiente
- **Máquina(s) afetadas:** CachyOS principal
- **OS:** CachyOS (Arch Linux)
- **Modo:** produção (HUB rodando, IA ligada)

#### Pré-condição para reproduzir
1. LOGOS com `inference_enabled=true` (IA ligada)
2. Embed-server não iniciado ainda (nenhuma requisição anterior ou após idle unload)
3. Mnemosyne indexer chama `POST /v1/embeddings`

#### Sintoma
```
httpx.HTTPStatusError: Server error '503 Service Unavailable'
for url 'http://127.0.0.1:7072/v1/embeddings'
```
Toda tentativa de indexação da Mnemosyne falhava silenciosamente (ou com erro) — nenhum embedding gerado.

#### Causa raiz
Três problemas relacionados:

1. **`v1_embeddings_proxy` sem lazy loading:** o handler verificava se o embed-server estava ativo e retornava 503 imediatamente se não. Não havia nenhuma tentativa de iniciá-lo. O embed-server só subia via `do_load_model` (toggle explícito), que não é mais chamado com lazy loading.

2. **`queue_and_forward` lazy load não iniciava embed-server:** após `ensure_llama_model_loaded` bem-sucedido, não havia chamada a `ensure_embed_server_started`. O fluxo `do_load_model` (que chama ambos) foi substituído pelo lazy load que só chama um.

3. **`v1_embeddings_proxy` sem gate de `inference_enabled`:** o handler não verificava se a IA estava ligada, tratando o embed-server como sempre disponível.

#### Impacto
Bloqueante: Mnemosyne não conseguia indexar nenhum documento nem fazer RAG depois que o LOGOS migrou para lazy loading. O embed-server nunca subia automaticamente.

#### Fix
- **`v1_embeddings_proxy`:** substituído o 503 imediato por lazy loading: chama `ensure_embed_server_started(&s)`, verifica se subiu, retorna 503 apenas se falhar. Adicionado gate de `inference_enabled`.
- **`queue_and_forward`:** adicionado `ensure_embed_server_started(&s).await` após `ensure_llama_model_loaded` bem-sucedido no bloco de lazy load.
- **`proxy_openai_to_llama`:** idem — adicionado `ensure_embed_server_started(s).await` após lazy load bem-sucedido.

#### Teste de regressão
`ensure_embed_server_started` tem fast path (noop se já ativo) — chamadas redundantes são seguras. Sem teste isolado de `v1_embeddings_proxy` (requer servidor HTTP mock). Regressão verificada via `cargo test`.

---

### BUG-017 · [FIXED] · db.run_sync() inexistente em aiosqlite 0.22.x — código morto em _reindex e init_vec_index

#### Identificação
- **Data:** 2026-05-31
- **App(s):** AKASHA
- **Componente:** `AKASHA/services/local_search.py` — `_reindex()`, `init_vec_index()`
- **Commit do fix:** `5d90459`
- **Descoberta via:** tentativa-de-feature (ao implementar `embed_and_index`, o teste revelou AttributeError ao tentar `db.run_sync()`)
- **Tempo de diagnóstico:** ~15 minutos

#### Ambiente
- **Máquina(s) afetadas:** todas (aiosqlite 0.22.x instalada via pyproject.toml)
- **OS:** CachyOS
- **Modo:** desenvolvimento
- **Reproduzível em:** qualquer ambiente com aiosqlite 0.22.x

#### Pré-condição para reproduzir
1. `VECTOR_SEARCH_ENABLED = True` em `services/local_search.py`
2. Chamar `init_vec_index()` ou `_reindex()` com embedding não-nulo

#### Sintoma observado
```
AttributeError: 'Connection' object has no attribute 'run_sync'
```
Seguido de retorno silencioso False (o except genérico engolia o erro).

#### Logs
```
DEBUG:akasha.local_search:embed_and_index: erro ao salvar embedding para '/test/file.md': 'Connection' object has no attribute 'run_sync'
```

#### Causa raiz
`db.run_sync(fn)` era usado para carregar a extensão sqlite-vec na conexão aiosqlite:
```python
await db.run_sync(_load_vec_ext)  # _load_vec_ext(conn): _sqlite_vec.load(conn)
```
O método `run_sync` foi removido ou nunca existiu na versão 0.22.x do aiosqlite instalada
no ecossistema. Como `VECTOR_SEARCH_ENABLED = False` por padrão, o código nunca executava
em produção e o bug ficou latente.

#### Impacto
Código morto: `_reindex()` e `init_vec_index()` falhariam silenciosamente ao tentar
carregar a extensão sqlite-vec se `VECTOR_SEARCH_ENABLED` fosse habilitado. A indexação
vetorial local ficaria inoperante sem nenhum aviso visível.

#### Fix aplicado
Substituído `await db.run_sync(_load_vec_ext)` pelo equivalente correto em aiosqlite 0.22.x:
```python
await db.enable_load_extension(True)
await db.load_extension(_sqlite_vec.loadable_path())
```
A função `sqlite_vec.loadable_path()` retorna o caminho portável para o .so da extensão,
sem depender da função `_sqlite_vec.load(conn)` que exigia acesso à conexão raw sqlite3.
Alterado em: `_reindex()`, `init_vec_index()`, e a nova `embed_and_index()`.

#### Teste de regressão
`test_embed_and_index.py` → `TestEmbedAndIndexSuccess::test_returns_true_on_success`:
usa banco temporário com a extensão real e confirma que a inserção funciona end-to-end.
O `_load_vec_ext` pode ser removido futuramente; por ora permanece como dead code para
não quebrar imports externos que possam referenciá-lo.

---

### BUG-018 · [FIXED] · knowledge_worker deadlock — fila baixa com >50 itens nunca drena

#### Identificação
- **Data:** 2026-06-01
- **App(s):** AKASHA
- **Componente:** `services/knowledge_worker.py` → `process_queue()`
- **Commit do fix:** pendente
- **Descoberta via:** uso-real
- **Tempo de diagnóstico:** ~30 min

#### Ambiente
- **Máquina(s) afetadas:** CachyOS principal
- **OS:** CachyOS
- **Modo:** produção (AKASHA rodando com LOGOS ativo)
- **Reproduzível em:** qualquer ambiente com >50 itens no backfill

#### Pré-condição
AKASHA rodando com backfill de knowledge ativo. `_queue_low` acumula >50 itens durante indexação inicial (arquivos archived + crawl_pages).

#### Sintoma
Warning `knowledge_worker: fila baixa com 51 itens — pausando backfill` repetindo a cada 20 segundos indefinidamente. Fila nunca drena. LOGOS online, itens não processados.

#### Logs
```
23:04:39 [WARNING] akasha.knowledge_worker: knowledge_worker: fila baixa com 51 itens — pausando backfill
23:04:59 [WARNING] akasha.knowledge_worker: knowledge_worker: fila baixa com 51 itens — pausando backfill
(repetindo a cada 20s sem mudança no contador)
```

#### Causa raiz
Deadlock entre dois mecanismos de throttle redundantes:

1. `backfill_knowledge._wait_queue_drain()` (linha ~1346): pausa corretamente antes de enfileirar novos itens quando `_queue_low.qsize() > 50`. Aguarda com `asyncio.sleep(5)` até drenar.

2. `process_queue()` (linhas 518-524, **bug**): quando `_queue_low.qsize() > _LOW_QUEUE_PAUSE_THRESHOLD`, dormia 20s e fazia `continue` sem consumir nenhum item. Isso impedia a fila de drenar, perpetuando o estado de bloqueio do `backfill_knowledge`.

Resultado: `backfill_knowledge` esperava a fila drenar → `process_queue` não drenava porque a fila era >50 → deadlock perfeito.

#### Impacto
Knowledge extraction completamente parada em qualquer sessão com backfill não concluído. Extração de tópicos, entidades e perfil de interesse paralisados indefinidamente até reiniciar o AKASHA.

#### Fix
Removido o bloco de threshold de `process_queue()`. O throttling já existia no lugar correto (`backfill_knowledge._wait_queue_drain()`). `process_queue` agora drena a fila normalmente independente do tamanho.

#### Teste de regressão
`tests/test_paralelo1_priority_queue.py` → `TestQueueThresholdRegression`:
- `test_low_queue_above_threshold_is_still_accessible`: fila com >50 itens ainda pode ser lida
- `test_process_queue_has_no_threshold_check`: verifica via source inspection que "pausando backfill" não está em `process_queue`
- `test_wait_queue_drain_in_backfill_still_throttles`: confirma que o throttle correto existe em `backfill_knowledge`

---

### BUG-019 · [FIXED] · `page_count` em `crawl_sites` desincronizado com `crawl_pages` — 14 de 16 domínios aparentam ter páginas indexadas mas o banco está vazio

#### Identificação
- **Data:** 2026-06-02
- **App(s):** AKASHA
- **Componente:** tabela `crawl_sites` (coluna `page_count`) vs. tabela `crawl_pages`
- **Commit do fix:** migration 51 em `database.py` (ver abaixo)
- **Descoberta via:** auditoria manual da Biblioteca durante item "Crescer índice local"
- **Tempo de diagnóstico:** ~15 min

#### Ambiente
- **Máquina(s) afetadas:** CachyOS principal
- **OS:** CachyOS
- **Modo:** produção (banco `/home/spacewitch/Documents/ecosystem_root/akasha/akasha.db`)

#### Pré-condição
16 domínios cadastrados na Biblioteca (tabela `crawl_sites`). A instância AKASHA foi usada em sessões de desenvolvimento onde resets de banco ou migrações podem ter ocorrido.

#### Sintoma
14 de 16 domínios mostram `page_count > 0` na coluna `crawl_sites.page_count` (ex: allfreecrafts.com = 1225, pagangrimoire.com = 306), mas `SELECT COUNT(*) FROM crawl_pages WHERE site_id = ?` retorna 0 para todos esses domínios. Apenas studybuddhism.com (68 páginas) e buddhism.net (21 páginas) têm conteúdo real em `crawl_pages`.

Total geral: `crawl_pages` tem 89 linhas; a soma de `page_count` em `crawl_sites` seria ~2.000+.

#### Logs
Confirmado via SQL direto no banco de produção:
```sql
SELECT base_url, page_count, (SELECT COUNT(*) FROM crawl_pages cp WHERE cp.site_id = cs.id) as real_count
FROM crawl_sites cs WHERE deleted = 0;
-- Resultado: allfreecrafts.com: page_count=1225, real_count=0
--            pagangrimoire.com: page_count=306, real_count=0
--            studybuddhism.com: page_count=68, real_count=68 (ok)
```

#### Causa raiz
Provavelmente um reset de tabela (`crawl_pages`) durante desenvolvimento ou migração de schema, sem atualizar o contador `page_count` em `crawl_sites`. O contador ficou com os valores do crawl anterior enquanto as páginas foram deletadas.

#### Impacto
A Biblioteca aparenta ter um índice local rico (~2.000 páginas), mas na prática tem 89 páginas de 2 domínios. Buscas locais via FTS5 e busca semântica têm cobertura mínima. O conhecimento de domínios como allfreecrafts.com, pagangrimoire.com, ravelry.com, quantamagazine.org, etc. está perdido.

#### Fix
Migration 51 em `database.py` (`_migrate`, `SCHEMA_VERSION = 51`), idempotente e em 3 passos:
1. **Re-crawl forçado:** `UPDATE crawl_sites SET last_crawled_at = NULL WHERE page_count > 0 AND (SELECT COUNT(*) FROM crawl_pages WHERE site_id = crawl_sites.id) = 0` — os sites que perderam dados voltam à fila de `crawl_pending_sites()` no próximo startup (que crawla sites com `last_crawled_at IS NULL`).
2. **Sincronização:** `UPDATE crawl_sites SET page_count = (SELECT COUNT(*) FROM crawl_pages WHERE site_id = crawl_sites.id)` — corrige o contador para o valor real.
3. **Trigger preventivo:** `CREATE TRIGGER trg_crawl_pages_dec_count AFTER DELETE ON crawl_pages` decrementa `page_count` (com piso em 0 via `MAX(0, ...)`) sempre que uma página é deletada individualmente — evita futura dessincronia.

Aplicado também diretamente no banco de produção (`ecosystem_root/akasha/akasha.db`) via SQL idêntico + `schema_version = 51`, já que a migration só roda no startup. Resultado verificado: 9 sites marcados para re-crawl, `SUM(page_count) = COUNT(crawl_pages) = 89`.

#### Teste de regressão
`tests/test_page_count_sync.py` — 10 testes: migration sincroniza page_count para 0 (stale), reseta last_crawled_at de sites stale, preserva sites com páginas reais, não toca sites nunca-crawleados, sincroniza mismatch parcial; trigger decrementa ao deletar, não fica negativo, decrementa N vezes, sobrevive a CASCADE delete, existe após init_db.

#### Observação secundária (não faz parte deste bug)
5 domínios (positivepsychology.com, covencrafts.co.uk, yarnspirations.com, marxismo.org.br, freevintagecrochet.com) foram crawleados recentemente e retornaram 0 páginas reais — `page_count=0` é correto aqui, mas sugere que esses crawls falharam ou todas as páginas caíram no filtro `word_count >= 50`. Investigação separada recomendada (possível conteúdo JS-heavy ou bloqueio).

---

### BUG-020 · [FIXED] · embed-server retorna HTTP 500 com requisições concorrentes de múltiplos apps

#### Identificação
- **Data:** 2026-06-02
- **App(s):** HUB/LOGOS, AKASHA, Mnemosyne
- **Componente:** `HUB/src-tauri/src/logos.rs` — `do_embed_proxy()` (linha ~2917) e `v1_embeddings_proxy()` (linha ~3357)
- **Commit do fix:** (próximo commit)
- **Descoberta via:** uso-real (indexação simultânea de AKASHA e Mnemosyne no PC principal)
- **Tempo de diagnóstico:** ~15 minutos

#### Ambiente
- **Máquina(s) afetadas:** MainPC (CachyOS) — Windows 10 não indexa, logo não reproduz
- **OS:** CachyOS (Arch Linux)
- **Hardware relevante:** AMD Ryzen 5 4600G, RX 6600 8 GB VRAM
- **Modo:** produção (LOGOS rodando, embed-server ativo na porta 8082)
- **Reproduzível em:** qualquer máquina onde dois apps embedam simultaneamente

#### Pré-condição para reproduzir
AKASHA (`knowledge_worker`) e Mnemosyne (`IndexWorker`) rodando indexação/backfill em paralelo, ambos chamando o endpoint de embedding do LOGOS (porta 7072) ao mesmo tempo.

#### Sintoma observado
Mnemosyne loga `WARNING: IndexWorker: erro ao embedar 'arquivo.pdf': Server error '500 Internal Server Error' for url 'http://127.0.0.1:7072/v1/embeddings'`. O arquivo não é indexado naquela sessão. AKASHA pode sofrer falha simétrica (não confirmado nos logs vistos).

#### Logs
```
07:17:32,377 [WARNING] gui.workers: IndexWorker: erro ao embedar 'Bokar-Rimpoche-Tara-o-Divino-Feminino.pdf': Server error '500 Internal Server Error' for url 'http://127.0.0.1:7072/v1/embeddings'
07:20:00,235 [WARNING] gui.workers: IndexWorker: erro ao embedar 'Buddhist Epistemology (...).pdf': Server error '500 Internal Server Error' for url 'http://127.0.0.1:7072/v1/embeddings'
```

#### Causa raiz
Os dois proxies de embedding em `logos.rs` — `do_embed_proxy()` (rota Ollama `api/embed`, linha ~2917) e `v1_embeddings_proxy()` (rota OpenAI `v1/embeddings`, linha ~3357, que é o caminho real usado por AKASHA e Mnemosyne) — usavam `akasha_semaphore` (capacidade 2), o mesmo semáforo das chamadas LLM do AKASHA. Com dois apps clientes (AKASHA e Mnemosyne), cada um adquire 1 permit do semáforo de capacidade 2 e ambos encaminham a requisição ao embed-server (llama-server, porta 8082) simultaneamente. O llama-server em modo embedding não processa requisições concorrentes e retorna HTTP 500.

#### Impacto
Degradação: arquivos deixam de ser indexados silenciosamente quando dois apps embedam ao mesmo tempo. Não é bloqueante (os apps continuam rodando), mas o vectorstore fica incompleto.

#### Fix aplicado
Fix em duas camadas:
1. **Fix definitivo no LOGOS** (`HUB/src-tauri/src/logos.rs`): adicionado `embed_semaphore: Arc<Semaphore>` dedicado, capacidade **1**, inicializado nos 3 construtores (`new`, `for_testing`, `make_test_state`). Ambos os proxies de embed (`do_embed_proxy` e `v1_embeddings_proxy`) passaram a usar `embed_semaphore` em vez de `akasha_semaphore`. Como a capacidade é 1, o `v1_embeddings_proxy` deixou de pedir 2 permits para prioridade alta (pedir 2 numa capacidade-1 nunca seria concedido) e passou a sempre adquirir 1 — cada requisição de embedding já obtém exclusividade. `log::debug!` quando uma requisição entra na fila de espera. Resultado: AKASHA e Mnemosyne nunca mais batem no embed-server ao mesmo tempo, e o semáforo de chat (`akasha_semaphore`) não é mais consumido por embeddings.
2. **Safety net nos clientes** (retry para falhas transientes residuais):
   - **AKASHA** (`services/semantic_search.py`): `embed_text()` re-tenta em HTTP 500/503 até 3 vezes com backoff exponencial (1s/2s), logando `log.warning` por falha; esgotadas as tentativas retorna `None` (mantém contrato fire-and-forget). O retry foi colocado em `embed_text` — e não em `embed_and_store` como o TODO sugeria — porque é em `embed_text` que o status HTTP 500/503 é observável (`embed_and_store` só recebe `None`). O semáforo do backfill em `knowledge_worker.py` foi reduzido de 2 para 1 (o LOGOS já serializa).
   - **Mnemosyne** (`core/indexer.py`): `_embed_batch()` já tinha loop de retry com backoff para timeout/429; 500/503 foram adicionados à mesma branch transiente (`_EMBED_RETRY_STATUS = {429, 500, 503}`), com `log.warning` por tentativa. Optou-se por estender o loop existente em vez de criar um segundo loop com backoff 1s/2s/4s (evita duplicar mecanismo já afinado) — os waits permanecem os do módulo (30s/60s), aceitáveis para um safety net raro.

#### Teste de regressão
- **LOGOS** (`logos.rs`, módulo de testes): `embed_semaphore_tem_capacidade_um`, `embed_semaphore_serializa_duas_requisicoes` (segunda requisição aguarda enquanto a primeira segura o permit), `embed_semaphore_nao_afeta_akasha_semaphore` (chat semaphore intacto). 3 passando.
- **AKASHA** (`tests/test_embed_text_retry.py`, 8 testes): sucesso sem retry; 500×2 depois 200 → sucede; 500 sempre → None + 3 warnings; 503 dispara retry; 4xx não re-tenta; offline não re-tenta; texto vazio sem HTTP. Todos passando.
- **Mnemosyne** (`tests/test_logos_embeddings.py`, +5 testes espelhando os de 429): 500/503 retry→sucesso; 500 sempre→`EmbedTimeoutError` após 3 tentativas; warning por tentativa; sucesso na 1ª sem sleep. **15 passando** (10 existentes + 5 novos) via venv compartilhado da raiz (`program files/.venv`).

---

### BUG-021 · [FIXED] · `feedbackInsight()` sempre retorna cedo — feedback de insight nunca chega ao servidor

#### Identificação
- **Data:** 2026-06-02
- **App(s):** AKASHA
- **Componente:** `AKASHA/templates/base.html` — função `feedbackInsight()`
- **Commit do fix:** (próximo commit)
- **Descoberta via:** uso-real (usuária relatou que feedback ✓/✗ no overlay não parece ser salvo)
- **Tempo de diagnóstico:** ~5 minutos

#### Ambiente
- **Máquina(s) afetadas:** todas (bug no JavaScript da interface web)
- **OS:** qualquer
- **Modo:** produção e dev
- **Reproduzível em:** qualquer browser com a interface AKASHA aberta

#### Pré-condição para reproduzir
Overlay de insight visível na interface AKASHA. Clicar no botão ✓ (confirmado) ou ✗ (dispensar).

#### Sintoma observado
Overlay fecha visualmente mas o servidor nunca recebe o POST para `/insight/feedback`. O campo `feedback` na `personal_memory` permanece NULL. `_pm_current` no servidor não é limpo (porque `set_pm_current(None)` depende do POST que nunca chega), mantendo o insight como "atual" indefinidamente até reinício do servidor.

#### Logs
Nenhum — o bug é silencioso. No DevTools: nenhuma requisição POST para `/insight/feedback` ao clicar os botões.

#### Causa raiz
```javascript
function feedbackInsight(feedback) {
    hideOverlay();           // ← zera _memoryId = null
    if (_memoryId === null) return;  // ← guard verifica _memoryId DEPOIS de anulá-lo
    fetch('/insight/feedback', ...)  // ← nunca executa
}
```
`hideOverlay()` seta `_memoryId = null` como parte do cleanup. O guard logo em seguida sempre encontra `_memoryId === null` e retorna antes do `fetch`. Ambos os POSTs (feedback e dismiss) ficam bloqueados.

#### Impacto
Feedback da usuária nunca é persistido. A Akasha não aprende com confirmações/dispensas feitas via interface web (apenas via extensão, onde o bug não existe). `_pm_current` fica preso no servidor, impedindo novos insights de serem carregados para qualquer consumidor até reinício.

#### Fix aplicado
Capturar `_memoryId` em variável local antes de chamar `hideOverlay()`:
```javascript
function feedbackInsight(feedback) {
    var mid = _memoryId;   // captura antes de hideOverlay() zerar _memoryId
    hideOverlay();
    if (mid === null) return;
    fetch('/insight/feedback', { ..., body: JSON.stringify({memory_id: mid, feedback}) })
    ...
}
```

#### Teste de regressão
Manual: clicar ✓ ou ✗ no overlay → verificar no DevTools que POST para `/insight/feedback` é enviado com `memory_id` correto → verificar no DB que `feedback` da entrada foi atualizado.

---

### BUG-022 · [FIXED] · Extensão consome slot de insight sem exibir quando aba ativa é o próprio AKASHA

#### Identificação
- **Data:** 2026-06-02
- **App(s):** AKASHA (extensão do browser)
- **Componente:** `AKASHA/extension/background.js` — `pollInsight()`
- **Commit do fix:** (próximo commit)
- **Descoberta via:** revisão-de-código (investigação do BUG-021)
- **Tempo de diagnóstico:** ~15 minutos

#### Ambiente
- **Máquina(s) afetadas:** todas
- **OS:** qualquer (extensão Firefox/Chrome)
- **Modo:** produção
- **Reproduzível em:** qualquer sessão com a extensão instalada e a interface AKASHA aberta

#### Pré-condição para reproduzir
Extensão instalada e ativa. Interface AKASHA aberta como aba ativa no browser. Servidor tem entrada de `personal_memory` disponível para exibição (`shown_as_overlay = 0`).

#### Sintoma observado
A extensão, ao fazer poll de `/insight/current`, consome o slot da entrada (servidor registra `consumer="ext"` em `_pm_shown_by`), mas não injeta o overlay (porque detecta que a aba ativa é o próprio AKASHA e faz early return). A interface AKASHA então recebe `text: None` (porque "ext" já consumiu) e também não exibe. O insight desaparece sem ser visto.

Efeito secundário: quando a usuária navega para outra aba, a extensão pode tentar exibir o mesmo insight novamente (porque `pm_already_shown_by("ext")` é False depois que a entrada foi carregada para outra sessão), causando a aparência de pop-up repetido.

#### Logs
Nenhum — o bug é silencioso.

#### Causa raiz
Em `background.js`, a verificação `if (activeTab.url?.startsWith(AKASHA_ORIGIN)) return` ocorria DEPOIS do `fetch` para `/insight/current`. O servidor já tinha processado a requisição e marcado `"ext"` como consumidor antes do early return da extensão.

#### Impacto
Insights de `personal_memory` nunca aparecem quando a interface AKASHA está aberta. Quando a usuária troca de aba, a extensão pode re-exibir o insight com aparência de duplicata.

#### Fix aplicado
Verificar a aba ativa ANTES de fazer o fetch. A extensão não chama `/insight/current` se a aba for o AKASHA — o overlay nativo da interface cuida disso:
```javascript
async function pollInsight() {
  // verifica aba ANTES do fetch para não consumir o slot sem exibir
  let activeTab = ...;
  if (activeTab.url?.startsWith(AKASHA_ORIGIN)) return;
  
  const res = await fetch(`${AKASHA_ORIGIN}/insight/current`, ...);
  ...
}
```

#### Teste de regressão
Manual: abrir AKASHA como aba ativa → aguardar 60s → verificar no DevTools da extensão que `pollInsight` retorna sem fazer fetch para `/insight/current` → navegar para outra aba → insight aparece corretamente via extensão (sem ter sido "consumido" silenciosamente).

---

### BUG-023 · [FIXED] · Teste usa domínio-semente (`ravelry.com`) como exemplo de domínio não-indexado

#### Identificação
- **Data:** 2026-06-02
- **App(s):** AKASHA
- **Componente:** `AKASHA/tests/test_domain_suggester.py::test_creates_multiple_suggestions`
- **Commit do fix:** pendente
- **Descoberta via:** teste-automatizado (durante implementação da reputação de domínio)
- **Tempo de diagnóstico:** ~10 min

#### Ambiente
- **Máquina(s) afetadas:** todas
- **OS:** Windows 10 (confirmado), independente de plataforma
- **Modo:** teste (`uv run python -m pytest`)
- **Reproduzível em:** qualquer ambiente — falha determinística

#### Pré-condição para reproduzir
Rodar a suíte do `test_domain_suggester.py`. O `dbs` fixture chama `init_db()`, que por sua vez chama `populate_from_user_data()` e semeia a tabela `crawl_sites` com a lista de sites padrão da usuária.

#### Sintoma observado
```
assert 1 == 2
tests\test_domain_suggester.py:183: AssertionError
```
O teste esperava 2 sugestões de domínio, mas apenas 1 era criada.

#### Logs
```
candidates: [('craftivism.com', 4)]
created: 1
```
`ravelry.com` desaparecia da lista de candidatos mesmo tendo 4 cliques registrados.

#### Causa raiz
O teste usava `ravelry.com` como um dos dois domínios "frequentes não indexados". Porém `https://www.ravelry.com` faz parte dos sites-semente da Biblioteca, inseridos em `crawl_sites` durante `init_db` → `populate_from_user_data`. A função `get_unindexed_frequent_domains` **corretamente** filtra domínios já indexados, então `ravelry.com` era removido dos candidatos. O código de produção estava certo; o dado do teste é que era inválido — escolheu um domínio que coincide com um seed real.

#### Impacto
Cosmético/teste — nenhum impacto em produção. A função de sugestão de domínio sempre funcionou como projetado. O falso negativo do teste mascarava a confiança na suíte.

#### Fix aplicado
Em `test_creates_multiple_suggestions`, trocar `ravelry.com` por `knittinghelp.example` (TLD reservado `.example`, garantidamente fora de qualquer lista de seeds). Adicionado comentário no docstring do teste alertando que domínios de teste não podem coincidir com os sites-semente.

#### Teste de regressão
O próprio `test_creates_multiple_suggestions` agora passa de forma determinística, e a escolha de um domínio `.example` evita colisão futura com seeds reais. Suíte completa de `test_domain_suggester.py` (10 testes) + `test_domain_quality.py` (24 testes) verde.

---

### BUG-024 · [FIXED] · `from services.crawler import _bg_crawl` falha silenciosamente — confirmar `domain_suggestion` nunca dispara o crawl

#### Identificação
- **Data:** 2026-06-02
- **App(s):** AKASHA
- **Componente:** `AKASHA/routers/search.py` (`insight_feedback`, ação de confirmação de `domain_suggestion`)
- **Commit do fix:** pendente
- **Descoberta via:** revisão-de-código (durante implementação dos pop-ups proativos adicionais)
- **Tempo de diagnóstico:** ~5 min

#### Ambiente
- **Máquina(s) afetadas:** todas
- **OS:** independente de plataforma
- **Modo:** produção (runtime do servidor AKASHA)
- **Reproduzível em:** qualquer ambiente

#### Pré-condição para reproduzir
Receber um pop-up de sugestão de domínio (`domain_suggestion`) e clicar em "Indexar" (confirmar).

#### Sintoma observado
Nenhum erro visível. O domínio era adicionado à Biblioteca (`add_crawl_site`), mas o crawl inicial **nunca era disparado** — o site ficava com `page_count = 0` indefinidamente até o ciclo horário de `crawl_pending_sites` eventualmente pegá-lo (ou nunca, dependendo de `next_crawl_at`).

#### Logs
Nenhum — a exceção era suprimida pelo `try/except` que envolvia o bloco.

#### Causa raiz
A função `_bg_crawl` (wrapper que chama `crawl_site` em background) está definida em `routers/crawler.py`, **não** em `services/crawler.py`. O código fazia `from services.crawler import _bg_crawl`, que levanta `ImportError`. Como o bloco inteiro estava dentro de um `try/except Exception` (para tolerar falhas de rede do crawl), o `ImportError` era engolido silenciosamente: o `add_crawl_site` (que vinha antes) executava, mas o agendamento do crawl nunca acontecia.

#### Impacto
Degradação silenciosa: a ação de confirmação parecia funcionar (domínio entrava na Biblioteca) mas a metade mais importante — começar a indexar — falhava sem aviso. Afetava o pop-up `domain_suggestion` desde sua introdução.

#### Fix aplicado
Criado helper local `_bg_crawl_site(site_id)` em `routers/search.py` que importa `crawl_site` de `services.crawler` (onde ele realmente existe) e o executa com tratamento de erro próprio. A lógica de confirmação foi refatorada para um dispatcher `_apply_insight_confirmation_action(entry)` que usa `_add_domain_to_library()` → `_bg_crawl_site()`. O import incorreto foi eliminado.

#### Teste de regressão
`tests/test_observer_popups.py::test_confirm_adds_domains_to_library` verifica que confirmar uma sugestão adiciona os domínios a `crawl_sites` (com `_bg_crawl_site` mockado para não fazer rede). Os testes de `domain_suggestion` (`test_domain_suggester.py`, `test_inline_domain_suggest.py`) continuam verdes após a refatoração.

---

### BUG-025 · [FIXED] · Chave de cache de busca web ignora `n_pages` — buscas leves envenenam o volume das buscas reais

#### Identificação
- **Data:** 2026-06-02
- **App(s):** AKASHA
- **Componente:** `AKASHA/services/web_search.py` — `search_web()` (montagem de `cache_key`)
- **Commit do fix:** (este commit)
- **Descoberta via:** investigação após a usuária estranhar o baixo número de resultados ("não parece pouco?")
- **Tempo de diagnóstico:** ~20 minutos

#### Ambiente
- **Máquina(s) afetadas:** todas
- **Modo:** produção
- **Reproduzível em:** qualquer ambiente — independe de rede (é lógica de cache)

#### Pré-condição para reproduzir
Buscar uma query com poucas páginas (`n_pages=1`) e depois a mesma query com muitas (`n_pages=10`) — ou vice-versa — dentro da janela de TTL do cache.

#### Sintoma observado
A segunda busca devolve o volume da primeira. Ex.: `search_web("craftivism", n_pages=1)` → 12 resultados; em seguida `search_web("craftivism", n_pages=10)` → ainda 12 (deveria ser ~100+). Em produção, qualquer busca interna leve (ex.: o pop-up observador `_get_domain_suggestions_for_query`, que chama `search_web` com o default `n_pages=1`) cacheava ~1 página sob a query, e a busca real do usuário (10 páginas, via router) acertava esse cache pequeno — fazendo a busca "parecer poucos resultados".

#### Logs
Sem erro — degradação silenciosa. Visível só medindo o funil: `_fetch_web(q, n_pages=10)` cru retornava 183 resultados para "craftivism", mas `search_web` devolvia 12 ao reusar o cache de `n_pages=1`.

#### Causa raiz
`cache_key = f"{effective_query}::lang={lang}" if lang else effective_query` — **não incluía `n_pages`**. Como o número de páginas determina o volume buscado (`_fetch_max = n_pages × _FETCH_PAGE_SIZE`), buscas com `n_pages` diferentes têm resultados diferentes, mas compartilhavam a mesma entrada de cache (memória + SQLite).

#### Impacto
Degradação de qualidade: o usuário recebia uma fração dos resultados sempre que uma busca leve interna (pop-ups, sugestões) tocava a mesma query antes. Atinge diretamente o objetivo de "máximo de resultados / substituto do Google".

#### Fix aplicado
`cache_key` passou a incluir sempre `lang` e `n_pages`: `f"{effective_query}::lang={lang}::p={n_pages}"`. Buscas com nº de páginas distinto não compartilham mais cache. Entradas antigas (chave sem `::p=`) simplesmente viram cache-miss (inofensivo).

#### Teste de regressão
`tests/test_search_cache.py`: `test_cache_separates_by_n_pages` (n_pages 1 e 10 re-buscam, volumes 1 e 10), `test_cache_n_pages_one_does_not_poison_ten` (reproduz o bug: leve antes não limita a real), `test_cache_same_n_pages_hits_cache` (mesmo n_pages ainda usa cache), `test_cache_separates_by_lang` (lang continua separando). 18/18 testes do arquivo passando.

---

### BUG-026 · [FIXED] · "Testar conexão" do SearXNG no HUB sempre falha para instância remota (healthcheck gateado por systemd local)

#### Identificação
- **Data:** 2026-06-03
- **App(s):** HUB
- **Componente:** `HUB/src-tauri/src/commands/searxng.rs` — `searxng_status()`
- **Commit do fix:** (este commit)
- **Descoberta via:** uso-real (usuária: URL correta `http://192.168.0.252:8080/`, mas "Testar conexão" diz "✗ SearXNG não respondeu")
- **Tempo de diagnóstico:** ~5 minutos

#### Ambiente
- **Máquina(s) afetadas:** qualquer máquina cujo SearXNG seja **remoto** (não um serviço systemd local)
- **Modo:** produção
- **Reproduzível em:** SearXNG no servidor T410 (Docker) com a URL configurada no HUB

#### Pré-condição para reproduzir
`akasha.web_search_backend` aponta para um SearXNG remoto (ex.: servidor T410) e não existe um serviço systemd `searxng` local na máquina do HUB.

#### Sintoma observado
O painel Busca do HUB mostra "✗ SearXNG não respondeu — verifique se está rodando e a URL está correta" ao clicar em "Testar conexão", mesmo o servidor respondendo `GET /healthz → 200` quando testado por `curl` da mesma máquina.

#### Causa raiz
Em `searxng_status()`, o healthcheck HTTP estava **gateado por `active`** (`let reachable = if active { GET /healthz } else { false }`), e `active = service_is_active()` checa `systemctl is-active searxng` — um serviço **systemd local**. Com o SearXNG remoto (Docker no servidor), não há serviço local → `active=false` → o código **nem tentava** o `/healthz` e cravava `reachable=false`. Suposição embutida de quando o SearXNG era instalado localmente via AUR.

#### Impacto
Cosmético/diagnóstico: a busca funcionava normalmente (a AKASHA consome o SearXNG remoto direto), mas o HUB reportava falsamente que o SearXNG estava inacessível, confundindo a usuária.

#### Fix aplicado
Extraída a função `healthcheck(url)` (GET `{url}/healthz`, trim de barra final, timeout 3s) e chamada **incondicionalmente** em `searxng_status()` — independente de `service_is_active()`. `active` continua exposto (informativo, para instalações locais), mas não gateia mais `reachable`. Limitação remanescente conhecida: os botões iniciar/parar usam `systemctl` local e não controlam um container remoto (anotado como follow-up — para o servidor, gerenciar via Docker no próprio servidor).

#### Teste de regressão
`searxng.rs` (módulo de testes): `healthcheck_empty_url_is_false`, `healthcheck_unreachable_is_false` (porta fechada → false), `healthcheck_200_is_true` (listener local responde 200 → true, prova o caminho remoto sem systemd), `healthcheck_trailing_slash_ok` (barra final não quebra). 7/7 testes do módulo passando.
