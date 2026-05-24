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

### Hardware — Laptop — Lenovo Ideapad 330-15IKB, modelo 81FE (Fedora)

- CPU: Intel Core i7-8550U (8 threads) @ 4.00 GHz — **tem AVX2**
- RAM: 11.58 GiB
- GPU 1 (discreta): **NVIDIA GeForce MX150, 2048 MiB VRAM (2 GB — confirmado)**
- GPU 2 (integrada): Intel UHD Graphics 620 @ 1.15 GHz (Optimus/híbrido)
- Disco: 443 GB btrfs
- Tela: 1920×1080, 15", 60 Hz
- OS: Fedora Linux 44 (Workstation Edition), kernel 7.0.9-204.fc44.x86_64, Niri 26.04 (Wayland), Fish 4.6.0
- Bateria: L17M2PB7 (monitorável — relevante para LOGOS)

Implicações: CUDA via MX150 (sem `HSA_OVERRIDE` — isso é só AMD/ROCm). VRAM = 2 GB: modelos-teto são SmolLM2 1.7B (KOSMOS, ~1 GB Q4) e Gemma 2B Q4 (Mnemosyne, ~1.5 GB). Phi-3 mini e Llama 8B → offload para CPU → aquecimento, evitar. Em bateria: LOGOS deve reduzir indexação.

**Decisão (2026-05-24):** o laptop usa o **mesmo modelo de embedding do PC principal** (padronização). Como 2 GB de VRAM não comportam embedding model + LLM simultaneamente, o LOGOS deve suportar **modo CPU para inferência LLM** no laptop: quando a VRAM estiver ocupada pelo embedding, o LLM roda via llama-server com `--n-gpu-layers 0`. O LOGOS continua sendo o único ponto de acesso à IA — não há fallback de serviço, apenas alternância de backend de execução (GPU → CPU) gerenciada internamente pelo LOGOS.

---

## Testes obrigatórios

**Toda implementação nova deve vir acompanhada de testes — estabelecido em 2026-05-22.**

- Toda feature, endpoint, módulo ou função nova: escrever os testes na mesma resposta.
- Toda correção de bug: adicionar teste que cobre o caso corrigido.
- Nunca reportar um item como concluído sem que os testes correspondentes existam e passem.

---

## Bugs detectados durante o trabalho

**Todo bug ou erro detectado deve ser reportado — nunca ignorado silenciosamente.**

- Se puder corrigir imediatamente → corrigir e reportar na mesma resposta.
- Se não puder corrigir imediatamente → anotar no TODO (seção `#### <App>` dentro do `### Bugs e investigações reportados após uso real`) **e avisar a usuária explicitamente** na mesma resposta.

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

### Mnemosyne

**Chat = Notebook — decisão arquitetural definitiva (2026-05-14).**
No Mnemosyne, cada conversa se chama **notebook**, não "chat". Notebooks são temáticos, sempre salvos automaticamente e persistem entre sessões. Nunca chamar de "chat", "sessão" ou "conversa" no código, UI ou documentação — o termo correto é **notebook**.

Cada notebook tem diretório próprio em `{data_dir}/notebooks/{id}/` com `metadata.json`, `history.jsonl` (mensagens append-only), `memory.json` (contexto RAG) e `studio/` (outputs do Studio do notebook). Um notebook pode filtrar quais coleções consulta — se a lista `collection_names` estiver vazia, usa todas as coleções habilitadas.

**Studio outputs = "pensamentos" da Mnemosyne.**
Outputs gerados pelo Studio são salvos como arquivos `.md` com frontmatter `source: mnemosyne_studio`. O indexador reconhece esse metadado e atribui `source_type = "thought"` com peso próprio em `SOURCE_WEIGHTS`, para que o RAG saiba que está citando análises feitas pela própria Mnemosyne — e não uma fonte externa.

**Aba Análise — estrutura atual (redesenhada em 2026-05-14):**
A aba tem 2 pills: **Guide** (index 0) e **Studio** (index 1). Resumo e FAQ foram unificados como tipos do combo `studio_type_combo` — gerados via `StudioWorker` como qualquer outro tipo e persistidos como `StudioOutput`. O Studio é agora uma galeria de tiles persistentes (`StudioTileWidget`) em `QScrollArea`. Não existe mais `summary_btn`, `faq_btn`, `studio_result_text` ou `studio_table` separados.

**Query multi-coleção (implementado 2026-05-14):**
O Mnemosyne consulta **todas** as coleções habilitadas simultaneamente via `MultiVectorstore` (proxy Chroma). Nunca há "coleção ativa" para queries — apenas `coll.enabled` controla inclusão/exclusão. O botão "Ativar" foi renomeado para "Habilitar/Desabilitar".

**Pop-up espontâneo da Mnemosyne + sistema de feedback (implementado 2026-05-19):**
A Mnemosyne cria pop-ups proativos via `InsightPopup` (PySide6 `QDialog`) acionado pelo `InsightScheduler`. O pop-up aparece no canto da tela com o texto do insight, botões de feedback (✓ / ✗ / ✎ comentário) e **permanece aberto até a usuária interagir** — sem timeout de fechamento automático (removido intencionalmente). O feedback é salvo na `personal_memory` com campo `feedback` e molda interesses futuros. O campo `shown_as_popup` em `personal_memory` evita re-exibir o mesmo insight. Insights recebidos da AKASHA via `friendship_receiver` também podem gerar pop-up. Escopo futuro: extensão de browser. **Não confundir** com o `notify_mnemosyne_insight()` (fluxo AKASHA → Mnemosyne badge) — o pop-up é Mnemosyne → usuária, proativo.

### AKASHA

- `/library` = crawler de domínios — "Sites" e "Biblioteca" foram **unificados** numa única seção chamada Biblioteca
- Porta real do servidor: **7071** (não 7070)
- Router principal: `AKASHA/routers/crawler.py` (gerencia `/library`)

**Princípio arquitetural do AKASHA: amplificador de pesquisa, não respondedor.**
O LLM no AKASHA age APENAS na camada de query (classificação de intenção, expansão de termos, reescrita conversacional). Nunca sintetiza, interpreta ou gera texto como resultado. O AKASHA devolve links, trechos e documentos — a usuária pensa, o sistema amplifica o alcance da busca. Isso descartou o Map-Reduce/síntese permanentemente. Todo código de query understanding deve respeitar esse princípio.

**AKASHA tem duas camadas lógicas que rodam em paralelo e de forma independente:**

- **AKASHA (ferramenta)** — o buscador: indexação, crawling, FTS5, ranking, cache, freshness, facetas. Funciona 100% sem LLM. Banco: `akasha.db`. Todo o bloco "Funcionalidades Core da AKASHA" no TODO é sobre esta camada.
- **Akasha (assistente)** — a IA com personalidade: memória, pensamentos, reflexões, persona, insights. Usa Ollama/LOGOS quando disponível; se offline, a ferramenta continua normalmente. Banco: tabela `personal_memory` isolada em `akasha.db`.

Regras de implementação:
1. A ferramenta **nunca bloqueia, espera ou falha** por causa da assistente estar offline.
2. As duas filas/processos correm em paralelo — ex: crawl + reflection loop simultâneos, sem um pausar o outro.
3. Bancos separados garantem que lentidão/corrupção num lado não afeta o outro.
4. Código da ferramenta = sem LLM no caminho crítico. Código da assistente = pode usar LLM, mas com fallback graceful.

**Contraste com Mnemosyne:** Mnemosyne não tem essa separação — ferramenta e assistente são a mesma entidade. Quando faz RAG, a personalidade já está no loop. AKASHA optou pela separação por ser primariamente uma ferramenta de busca.

### Isolamento de dados do AETHER

**Os dados do AETHER não devem ser lidos por nenhum app do ecossistema exceto o OGMA.**
O vault do AETHER contém escrita criativa pessoal. Nunca incluir `aether_vault` como fonte de indexação em AKASHA (`local_search.py`), Mnemosyne (`watched_dir`), ou qualquer outro app.
OGMA é o único com acesso autorizado aos dados do AETHER.

### Isolamento da memória pessoal das IAs

**A memória pessoal, pensamentos e vida interior de cada IA são privados — nunca indexados, nunca lidos por outras apps.**

Arquitetura de duas camadas:
- **Conhecimento** (impessoal): indexação, RAG, crawling, embeddings — sem personalidade, sem interpretação. Compartilhável via protocolo explícito (ex: `notify_mnemosyne_insight`).
- **Personalidade + memória** (privada): o que cada IA pensa e lembra a partir do conhecimento. Armazenado em store isolado (tabela/arquivo separado), nunca exposto ao RAG de coleções, nunca lido por outra app.

AKASHA: store em tabela `personal_memory` no SQLite próprio. Mnemosyne: store em `personal_memory.db` separado do Chroma/BM25.
O prompt base de personalidade de cada IA fica em `ecosystem.json` (`akasha.personality_prompt`, `mnemosyne.personality_prompt`), editável via HUB.
"Reiniciar" apaga a memória acumulada mas preserva o prompt base de personalidade.
Comunicação entre AKASHA e Mnemosyne pode incluir pensamento próprio junto ao dado bruto — mas continua sendo troca explícita, não indexação cruzada.

**Comunicação bidirecional AKASHA↔Mnemosyne ("amizade") — implementada 2026-05-19:**
- Mnemosyne → AKASHA: via `ecosystem_client.send_insight_to_akasha()` — envia insight gerado ao `InsightScheduler` da AKASHA para possível exibição no overlay do browser.
- AKASHA → Mnemosyne: via `friendship_receiver.py` (task background no `main.py`) — recebe insights da AKASHA, salva na `personal_memory` da Mnemosyne com `role="akasha_insight"`, pode gerar pop-up se relevante. Endpoint: `POST /friendship/insight`.
A troca é sempre explícita (protocolo definido) — nunca indexação cruzada do RAG.

### Sync do ecossistema — Syncthing

O `sync_root` do ecossistema foi migrado do Proton Drive para o **Syncthing** em 2026-05-18. O Syncthing é iniciado manualmente e gerenciado via painel no HUB.

**Caminho do `sync_root` por máquina:**
- **CachyOS principal:** `/home/spacewitch/Documents/ecosystem_root`
- **Windows 10:** (a definir após configuração do Syncthing)
- **Laptop:** (a definir após configuração do Syncthing)

O `sync_root` é lido em runtime por todos os apps via `ecosystem_client` — nunca hardcodar esse caminho. O HUB gerencia o `ecosystem.json` que contém esse campo. Caminho antigo (Proton Drive, inválido): `/mnt/archive1/proton/backup/ecosystem`.

### HUB / LOGOS

**O HUB ESTÁ SEMPRE ABERTO.** É o centro do ecossistema: gerencia o funcionamento de todos os outros apps, é através dele que os demais programas são abertos e monitorados. Nunca listar "exige HUB rodando" como desvantagem — isso é uma premissa arquitetural, não uma restrição.

O HUB é o **dashboard e painel de controle do ecossistema**: lança apps, centraliza configuração, visualiza dados de todos os programas e hospeda o **LOGOS** (proxy inteligente de LLM).

O LOGOS gerencia prioridades de execução de IA:
- **P1 (crítica):** chat interativo do HUB + escrita ativa no AETHER
- **P2 (importante):** buscas RAG no Mnemosyne
- **P3 (background):** pré-análise KOSMOS + transcrições Hermes

Monitora VRAM da RX 6600 e pausa tarefas P3 quando VRAM > 85%. O HUB **não é** um app Android — a Fase 3 (Android APK) está suspensa para replanejamento.

**O HUB é a fonte de verdade para todos os apps.** Nenhum app deve configurar ou consultar por conta própria:
- **Caminhos de dados**: lidos via `ecosystem.json` / `ecosystem_client`
- **Qual LLM usar**: campo específico por função no perfil ativo do LOGOS — `llm_rag` (Mnemosyne), `llm_analysis` (KOSMOS), `llm_query` (AKASHA), `embed` (embeddings). Lido via `ecosystem_client.get_active_profile()` em **runtime**, nunca em import time.
- **Qual embedding usar**: idem — nunca hardcoded no app
- **Inferência de LLM**: gerenciada diretamente pelo LOGOS via llama-cpp — **Ollama não é mais usado**. Todo o código legado que referencia Ollama (porta 11434, `get_ollama_url()`, `ollama_client.py`) será migrado para `ecosystem_client.get_inference_url()` apontando ao LOGOS. Nunca hardcodar porta ou URL de inferência.

---

## Workflow

- **`DESIGN_BIBLE.md` e `pesquisas.md` ficam no repositório `notebook`** (repositório Git separado, sincronizado via Proton Drive). Os caminhos por máquina estão abaixo — usar esses caminhos ao ler ou editar. **Após editar qualquer um desses arquivos, commitar o repositório `notebook` na mesma resposta** — `cd` para a raiz do repo e `git commit`. O `git add` só é necessário para arquivos não rastreados.
  - **Windows 10:** `D:\windows\documentos\notebook\` (raiz do repo); arquivos em `inbox\ecosystem_notes\`
  - **CachyOS principal:** `/home/spacewitch/Documents/notebook/` (raiz do repo); arquivos em `inbox/ecosystem_notes/`
  - **Laptop:** `/home/spacewitch/Documents/proton/notebook/` (raiz do repo); arquivos em `01_Projetos/ecosystem/` (a confirmar)
- **`GUIDE.md` fica na raiz do ecossistema (`program files/GUIDE.md`)**, versionado no repo do ecossistema (não no notebook). Commitar após cada edição no mesmo repo.
- **`DESIGN_BIBLE.md` deve ser mantido atualizado como prioridade permanente.**

### Regra permanente — documentação sempre atualizada

**Toda implementação (código, dependência, arquitetura, funcionalidade, endpoint, porta, modelo, novo módulo, etc.) deve terminar com atualização de documentação.** A documentação é tão importante quanto o código. Como etapa final de qualquer tarefa:

1. Verificar se `README.md` precisa ser atualizado — seções: mapa do ecossistema, funcionalidades, hardware, instalação, portas, dependências, modelos recomendados.
2. Verificar se `GUIDE.md` precisa ser atualizado — seções correspondentes à mudança (setup, dependências, arquitetura de dados, pipeline de busca, LLMs, etc.).
3. Fazer as edições necessárias com informações precisas.
4. Informar na resposta que a documentação foi atualizada e em quais seções.

Nunca deixar uma mudança sem reflexo nos dois arquivos. Commitar `README.md` e `GUIDE.md` junto ao código no mesmo commit (ou em commit imediatamente seguinte).
- Manter o `TODO.md` / `ROADMAP.md` / `dev_files/todo` de cada app atualizado.
- **`notes.md` é arquivo de organização pessoal da usuária — nunca editá-lo.** Apenas lê-lo quando necessário para entender o contexto. Todo rastreamento de progresso vai no `TODO.md`. **Sempre commitar o `notes.md` quando houver mudanças não commitadas** — verificar `git status notes.md` proativamente a cada sessão.
- **Marcar item como `[x]` no TODO imediatamente após concluí-lo** — não acumular para marcar depois, não esperar o fim da sessão.
- **Antes de implementar qualquer coisa que não esteja no TODO: primeiro acrescentar o item ao TODO (com descrição), depois implementar.** Nunca implementar algo não registrado.
- Commit por item individual concluído
- **Nunca começar a implementar nada sem ordem explícita da usuária.** Discussão, planejamento e anotação no TODO não são ordens de implementação.
- **Nunca avançar de um item para o próximo no TODO sem ordem explícita.** "Continue" sem especificar o quê não é autorização para implementar.
- **Após concluir cada item: parar, resumir o que foi feito, e aguardar permissão explícita para prosseguir.** Implementar vários itens seguidos numa mesma resposta só é permitido se a usuária disser explicitamente "faça o bloco inteiro" ou equivalente.
- **Pesquisas:** regras obrigatórias ao realizar qualquer pesquisa (WebSearch, WebFetch, Agent):
  1. **Reler o `pesquisas.md`** (ver caminho por máquina na seção Workflow acima) antes de iniciar, para não duplicar pesquisa já feita.
  2. **Salvar em `pesquisas.md`** (ver caminho por máquina) em **ordem cronológica crescente** — novas sessões sempre no final do arquivo (append), sem seções por app. Nunca inserir no meio do arquivo mesmo que a data seja anterior à última entrada. Formato: bloco com cabeçalho `PESQUISA — <Título>` + `Data: YYYY-MM-DD`, conteúdo completo e detalhado cobrindo todos os aspectos do tema — mesmo os não imediatamente aplicáveis — com exemplos, métricas, benchmarks e **fontes em formato ABNT** ao final. O conteúdo não deve ser filtrado pela relevância atual para o ecossistema. **Nunca incluir sugestões ou melhorias.**
     **Estilo obrigatório e profundidade mínima:** tom acadêmico, semelhante a artigo de revisão de faculdade — parágrafos explicativos e densos, não bullet points secos; contextualizar cada conceito antes de detalhar; explicar o que é, por que existe, qual problema resolve; comparações com trade-offs reais; métricas com contexto (dataset, baseline, condições); limitações explicitadas; interpretar os achados. **Extensão mínima: equivalente a 4-6 páginas A4 de texto corrido por sessão.** Nunca truncar por brevidade — se o tema tem 10 subtópicos, cobrir os 10.
  3. **Manter o índice atualizado** — adicionar entrada para a nova sessão no índice do início do arquivo.
  4. **Ordem cronológica crescente** — novas sessões sempre no final do arquivo (append).
  5. **Apresentar no chat** um resumo médio-detalhado (1–2 minutos de leitura) cobrindo achados principais e implicações práticas, **seguido de lista separada de mudanças/melhorias sugeridas**.
  6. **Pedir permissão** antes de adicionar qualquer sugestão ao TODO — a usuária decide o rumo do projeto, não o Claude. Nunca adicionar ao TODO por iniciativa própria.
  7. Sugestões aprovadas vão no **TODO**, nunca no `pesquisas.md`.
  8. **Nunca usar "HUB/LOGOS"** — HUB é o programa, LOGOS é apenas um subprograma dele.
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
