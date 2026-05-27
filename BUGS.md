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

### BUG-009 · [OPEN] · embed-server em loop de reinicialização — bge-m3-Q4_K_M.gguf corrompido (download incompleto)

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
