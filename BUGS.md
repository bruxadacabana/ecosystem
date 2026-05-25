# Histórico de Bugs — Ecossistema

Bugs detectados durante desenvolvimento e uso real. Inclui contexto de ambiente, sintomas, causa raiz e fix aplicado.

Formato de status: `[FIXED]` · `[OPEN]` · `[INVESTIGATING]`

---

## BUG-005 · [FIXED] · STATUS_ENTRYPOINT_NOT_FOUND ao iniciar testes Rust do HUB no Windows

**Data:** 2026-05-25  
**App:** HUB (src-tauri — testes unitários Rust)  
**Ambiente:** Windows 10 Pro 22H2, i5-3470, sem AVX2 — WorkPC  
**Commit do fix:** `6dc763f`

**Sintoma:**  
`cargo test --lib` encerrava imediatamente com código de saída `0xC0000139 STATUS_ENTRYPOINT_NOT_FOUND` antes de qualquer saída. Nenhum teste chegava a executar.

**Causa raiz:**  
O PE loader do Windows resolve a tabela de imports do binário antes de `main()` executar. `tauri-plugin-dialog` importa `TaskDialogIndirect` de `comctl32.dll`. O Windows carrega `comctl32` v5.82 por padrão (sem manifest de ativação). A v5.82 não exporta `TaskDialogIndirect` — essa função só existe na v6. O loader falha e aborta o processo.

O `hub.exe` não tem esse problema porque o Tauri embute um manifest RT_MANIFEST no binário (via `resource.lib` + `cargo:rustc-link-arg-bins`) que declara `Microsoft.Windows.Common-Controls v6.0.0.0`, ativando a v6 antes de qualquer código executar. O binário de testes não tem esse manifest.

**Fix:**  
`HUB/src-tauri/build.rs` emite `/DELAYLOAD:comctl32.dll` + `delayimp.lib` para **todos** os targets (via `cargo:rustc-link-arg`). O delay-loading move a resolução de `comctl32` da tabela de imports estática para resolução lazy no primeiro uso real — que nunca ocorre em testes (nenhum teste chama funções de diálogo).

**Tentativas que não funcionaram:**  
- `cargo:rustc-link-arg-tests` — documentado como aplicando a "todos os binários de teste", mas na prática só se aplica a targets `[[test]]` explícitos no Cargo.toml, não a unit tests de `[lib]`. Confirmado com `llvm-readobj --coff-imports`.
- Embed de manifest via `.rc` + `.res` + `cargo:rustc-link-arg-tests` — mesmo problema acima; além disso, teria conflito de recurso duplicado com o manifest do `hub.exe` se aplicado globalmente.

**Diagnóstico usado:**  
```
llvm-readobj --coff-imports target\debug\deps\hub_lib-*.exe | findstr comctl32
```
Confirmou que `TaskDialogIndirect` constava na tabela de imports estática.

---

## BUG-004 · [FIXED] · llama-server órfão bloqueia reinício via toggle_inference

**Data:** 2026-05-25  
**App:** HUB / LOGOS  
**Ambiente:** Windows 10 Pro 22H2 e CachyOS (reproduzível em ambos)  
**Commit do fix:** `f7abf5f`

**Sintoma:**  
Ao clicar "Ligar IA" após o llama-server ter sido iniciado fora do HUB (ex: processo residual de sessão anterior), `toggle_inference(true)` retornava `"already_running"` imediatamente sem iniciar o modelo. A UI ficava sem resposta de progresso e sem erro visível.

**Causa raiz:**  
`toggle_inference` verificava `llama_server_responding()` (ping HTTP ao endpoint) para decidir se havia servidor rodando. Se havia resposta, assumia que o processo já estava rastreado (`llama_proc`) e retornava `"already_running"`. Mas um servidor órfão responde ao ping sem ter sido registrado no `llama_proc` do HUB — a condição `llama_proc_active()` era `false` mas o código nunca chegava a verificar isso antes de retornar.

**Fix:**  
`do_toggle_inference` passa `server_responding` como parâmetro separado. Quando `enable=true` e servidor está respondendo, verifica `llama_proc_active()` antes de retornar `"already_running"`. Se o proc não está ativo, chama `kill_orphaned_llama_server()` para matar o órfão e então inicia o próprio processo rastreado.

---

## BUG-003 · [FIXED] · llama-server não usa GPU (roda em CPU por padrão sem --n-gpu-layers)

**Data:** 2026-05-25  
**App:** HUB / LOGOS  
**Ambiente:** CachyOS, RX 6600 8 GB VRAM  
**Commit do fix:** `aa23ec3`

**Sintoma:**  
Após ligar o LOGOS, o llama-server saturava a RAM do sistema e rodava lentamente. Monitoramento de VRAM mostrava 0% de uso GPU.

**Causa raiz:**  
O llama-server não usa GPU por padrão — requer `--n-gpu-layers N` explícito. O código interno usava `-1` para representar "offload total", mas a condição de geração da flag era `n_gpu > 0` — o caso `-1` não gerava nenhuma flag, resultando em modo CPU.

**Fix:**  
Adicionado branch `else` para `n_gpu == -1`: gera `--n-gpu-layers 9999` (offload máximo — o llama-server usa o que couber na VRAM e o restante vai para CPU).

---

## BUG-002 · [FIXED] · /v1/embeddings retorna 501 Not Implemented no llama-server

**Data:** 2026-05-25  
**App:** HUB / LOGOS + Mnemosyne  
**Ambiente:** CachyOS  
**Commit do fix:** `da15c62`

**Sintoma:**  
Mnemosyne retornava erro `501 Not Implemented` ao chamar `POST /v1/embeddings` no LOGOS. Indexação falhava completamente.

**Causa raiz:**  
O llama-server requer a flag `--pooling mean` (ou `cls`/`last`) para habilitar o endpoint `/v1/embeddings`. Sem ela, o endpoint existe na rota mas retorna 501. A flag não estava sendo passada no spawn do processo.

**Fix:**  
Adicionado `.arg("--pooling").arg("mean")` no `spawn_llama_server_proc` em `logos.rs`.

**Nota:** Este bug bloqueou completamente a indexação da Mnemosyne e foi descoberto durante tentativa de primeiro uso real após migração Ollama → llama-server.

---

## BUG-001 · [FIXED] · models_dir do LOGOS retorna lista vazia em dev (CWD/logos/models ignorado)

**Data:** 2026-05-25  
**App:** HUB / LOGOS  
**Ambiente:** Windows 10 Pro 22H2 (dev mode, `cargo tauri dev`)  
**Commit do fix:** `f7abf5f`

**Sintoma:**  
Ao clicar "Ligar IA" no HUB em modo dev, a lista de modelos aparecia vazia mesmo com modelos instalados em `HUB/src-tauri/logos/models/`.

**Causa raiz:**  
Em `cargo tauri dev`, o CWD é `HUB/src-tauri/`. Os modelos baixados via HUB ficam em `CWD/logos/models/`. Mas `LogosState::new()` calculava o `models_dir` usando apenas `dirs::data_local_dir()` (caminho XDG), que não tinha `registry.json` na máquina de desenvolvimento. O fallback para CWD só existia parcialmente no código e não estava sendo ativado corretamente.

**Fix:**  
Lógica extraída para `pick_models_dir(xdg, cwd_logos_models)`: se XDG não tem `registry.json` mas CWD tem, usa CWD. Função pura testável com 3 testes determinísticos via `tempfile::tempdir`.
