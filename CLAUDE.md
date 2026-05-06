# Diretivas do Ecossistema

Instruções para o Claude Code ao trabalhar neste repositório.

---

## Plataformas alvo

**Todos os apps devem rodar no Windows 10 e no CachyOS (Linux).**

- Usar APIs de path da linguagem, nunca separadores hardcoded (`/` ou `\`)
- O diretório de trabalho da usuária contém espaços no nome — testar caminhos com espaços
- Sem dependências exclusivas de uma plataforma
- Apps Python: compatível com `uv` em ambos os SOs
- Apps Tauri: `cargo tauri build` deve funcionar nos dois targets

### Hardware — Computador de trabalho (Windows 10)

- CPU: Intel Core i5-3470, Ivy Bridge 2012, 4 cores/4 threads, 3.2 GHz — **sem AVX2**
- RAM: 8 GB
- GPU: Intel HD Graphics integrada (32 MB dedicados — inútil para ML)
- OS: Windows 10 x64

Implicações: modelos de embedding pesados (ex: bge-m3) saturam o CPU e travam o sistema.
Soluções: indexar só na máquina de casa e sincronizar vectorstore; ou usar embedding estático leve.

### Hardware — Computador principal (CachyOS)

- CPU: AMD Ryzen 5 4600G
- RAM: 16 GB
- GPU: AMD Radeon RX 6600, RDNA2, 8 GB VRAM (gfx1032) — ROCm com `HSA_OVERRIDE_GFX_VERSION=10.3.0`
- OS: CachyOS (Arch Linux), Niri + Fish shell
- Armazenamento: ~2 TB (3 SSDs)

### Hardware — Laptop — Lenovo Ideapad 330-15IKB, modelo 81FE (CachyOS)

- CPU: Intel Core i7-8550U (8 threads) @ 4.00 GHz — **tem AVX2**
- RAM: 11.58 GiB
- GPU 1 (discreta): **NVIDIA GeForce MX150, 2048 MiB VRAM (2 GB — confirmado)**
- GPU 2 (integrada): Intel UHD Graphics 620 @ 1.15 GHz (Optimus/híbrido)
- Disco: 443 GB btrfs
- Tela: 1920×1080, 15", 60 Hz
- OS: CachyOS x86_64, kernel 7.0.1-1-cachyos, Niri 26.04 (Wayland), Fish 4.6.0
- Bateria: L17M2PB7 (monitorável — relevante para LOGOS)

Implicações: CUDA via MX150 (sem `HSA_OVERRIDE` — isso é só AMD/ROCm). VRAM = 2 GB: modelos-teto são SmolLM2 1.7B (KOSMOS, ~1 GB Q4) e Gemma 2B Q4 (Mnemosyne, ~1.5 GB). Phi-3 mini e Llama 8B → offload para CPU → aquecimento, evitar. Em bateria: LOGOS deve reduzir indexação.

---

## Princípio de erros

**Tratamento de erros com tipagem é prioridade absoluta em todo o ecossistema.**

- **Rust (AETHER):** toda função falível retorna `Result<T, AppError>`. Zero `.unwrap()` em produção.
- **TypeScript (OGMA):** `strict: true`. Erros tipados com discriminated unions. Nunca `any`.
- **Python (KOSMOS · Mnemosyne · Hermes):** `except ValueError` (específico), nunca `except Exception` genérico sem re-tipar.

---

## Memória entre máquinas

O Claude Code mantém memória local em `~/.claude/projects/.../memory/`. Essa memória **não é sincronizada** entre o computador de trabalho (Windows 10) e o computador principal (CachyOS) — cada instância tem sua própria memória local.

**Regra obrigatória:** toda vez que uma informação for salva ou atualizada na memória local (`~/.claude/projects/.../memory/`), o mesmo conteúdo deve ser registrado no `CLAUDE.md` (este arquivo) **na mesma resposta**, sem esperar o fim da sessão. O `CLAUDE.md` é versionado e sincronizado via Proton Drive entre as máquinas.

Isso garante que ambas as instâncias do Claude Code estejam na mesma página sobre contexto do projeto, preferências da usuária e decisões de arquitetura.

---

## Contexto do projeto

### AKASHA

- `/library` = crawler de domínios — "Sites" e "Biblioteca" foram **unificados** numa única seção chamada Biblioteca
- Porta real do servidor: **7071** (não 7070)
- Router principal: `AKASHA/routers/crawler.py` (gerencia `/library`)

### HUB / LOGOS

**O HUB ESTÁ SEMPRE ABERTO.** É o centro do ecossistema: gerencia o funcionamento de todos os outros apps, é através dele que os demais programas são abertos e monitorados. Nunca listar "exige HUB rodando" como desvantagem — isso é uma premissa arquitetural, não uma restrição.

O HUB é o **dashboard e painel de controle do ecossistema**: lança apps, centraliza configuração, visualiza dados de todos os programas e hospeda o **LOGOS** (proxy inteligente de LLM).

O LOGOS gerencia prioridades de execução de IA:
- **P1 (crítica):** chat interativo do HUB + escrita ativa no AETHER
- **P2 (importante):** buscas RAG no Mnemosyne
- **P3 (background):** pré-análise KOSMOS + transcrições Hermes

Monitora VRAM da RX 6600 e pausa tarefas P3 quando VRAM > 85%. O HUB **não é** um app Android — a Fase 3 (Android APK) está suspensa para replanejamento.

---

## Workflow

- Manter o `TODO.md` / `ROADMAP.md` / `dev_files/todo` de cada app atualizado.
- **Marcar item como `[x]` no TODO imediatamente após concluí-lo** — não acumular para marcar depois, não esperar o fim da sessão.
- **Antes de implementar qualquer coisa que não esteja no TODO: primeiro acrescentar o item ao TODO (com descrição), depois implementar.** Nunca implementar algo não registrado.
- Commit por item individual concluído
- **Nunca começar a implementar nada sem ordem explícita da usuária.** Discussão, planejamento e anotação no TODO não são ordens de implementação.
- **Nunca avançar de um item para o próximo no TODO sem ordem explícita.** "Continue" sem especificar o quê não é autorização para implementar.
- **Após concluir cada item: parar, resumir o que foi feito, e aguardar permissão explícita para prosseguir.** Implementar vários itens seguidos numa mesma resposta só é permitido se a usuária disser explicitamente "faça o bloco inteiro" ou equivalente.
- **Pesquisas:** regras obrigatórias ao realizar qualquer pesquisa (WebSearch, WebFetch, Agent):
  1. **Reler o `pesquisas.md`** (raiz do ecossistema) antes de iniciar, para não duplicar pesquisa já feita.
  2. **Salvar em `pesquisas.md`** (raiz) em **ordem cronológica crescente** — novas sessões sempre no final do arquivo, sem seções por app. Formato: bloco com cabeçalho `PESQUISA — <Título>` + `Data: YYYY-MM-DD`, conteúdo completo e detalhado cobrindo todos os aspectos do tema — mesmo os não imediatamente aplicáveis — com exemplos, métricas, benchmarks e **fontes em formato ABNT** ao final. O conteúdo não deve ser filtrado pela relevância atual para o ecossistema. **Nunca incluir sugestões ou melhorias.**
     **Estilo obrigatório:** tom acadêmico, semelhante a pesquisa de faculdade — parágrafos explicativos e bem estruturados, não bullet points secos; contextualizar cada conceito antes de detalhar; interpretar os achados; anotar limitações e comparações; não truncar para brevidade. O objetivo é um documento de referência consultável, não notas rápidas.
  3. **Manter o índice atualizado** — adicionar entrada para a nova sessão no índice do início do arquivo.
  4. **Ordem cronológica crescente** — novas sessões sempre no final do arquivo.
  5. **Apresentar no chat** um resumo médio-detalhado (1–2 minutos de leitura) cobrindo achados principais e implicações práticas, **seguido de lista separada de mudanças/melhorias sugeridas**.
  6. Sugestões e melhorias vão no **chat e no TODO**, nunca no `pesquisas.md`.
  7. **Nunca usar "HUB/LOGOS"** — HUB é o programa, LOGOS é apenas um subprograma dele.
- **Estrutura obrigatória do TODO.md para melhorias:**
  Existem duas seções fixas no `TODO.md` raiz. Cada sessão de trabalho (pesquisa, correção, conjunto de melhorias) cria um **novo `###` header** dentro da seção correta — nunca acrescenta itens em headers de sessões anteriores.

  **Seção 1 — oriundas de pesquisa externa:**
  ```
  ## Melhorias baseadas em pesquisas para o ecossistema

  ### Pesquisa: <título da pesquisa> | <data YYYY-MM-DD>
  > Contexto: <1-2 frases explicando o que foi pesquisado e por que é relevante>
  #### <Nome do App 1>
  - [ ] <item com explicação do que fazer e por que>
  #### <Nome do App 2>
  - [ ] <item com explicação>
  ```

  **Seção 2 — melhorias, correções e atualizações internas:**
  ```
  ## Melhorias, correções e atualizações

  ### <Título descritivo> | <data YYYY-MM-DD>
  > Contexto: <1-2 frases explicando a motivação>
  #### <Nome do App 1>
  - [ ] <item com explicação do que fazer e por que>
  #### <Nome do App 2>
  - [ ] <item com explicação>
  ```

  **Regras adicionais:**
  - Cada item `- [ ]` deve conter instrução suficiente para ser implementado sem contexto da conversa original (Claude futuro não tem memória da sessão).
  - Nunca fundir itens de sessões diferentes num mesmo `###`.
  - As seções `##` devem existir no arquivo mesmo que estejam vazias — nunca removê-las.

---

## Design

O sistema visual é definido no `DESIGN_BIBLE.txt` (raiz). A paleta canônica está em:
- `AETHER/src/styles/tokens.css` (web)
- `ecosystem_qt.py` → `build_qss()` (PyQt6: KOSMOS, Hermes)
- `Mnemosyne/gui/styles.qss` (PySide6)

Modo noturno: "Atlas Astronômico à Meia-Noite" (`#12161E` base).
