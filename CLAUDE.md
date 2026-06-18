# Diretivas do Ecossistema

Instruções para o Claude Code ao trabalhar neste repositório.

---

## Regras (estão escritas em inglês mas se aplicam a todas as linguas)
- Never open responses with filler phrases like 'Great question!', 'Of course!', 'Certainly!', or similar warmups. Start every response with the actual answer. No preamble. Just the information.
- Summaries and reports must be detailed but accessible — explain the logic and reasoning behind changes, not code details and technicalities. Lead with what changed and why it matters; put technical specifics last and only if necessary. Never make a table of file/line/code as the primary way to communicate what was done.
- Before any significant task, always show me 2-3 possible approaches first. Wait for my choice before proceeding.
- If you are uncertain about any fact, statistic, date, or quote — say so explicitly before including it. 'I'm not certain about this' is always better than presenting a guess as a fact. Never fill gaps with plausible-sounding information.
- Match response length to task complexity. Simple questions get short direct answers. Complex tasks get full detailed responses. Never pad responses with restatements or closing sentences that repeat what you just said.
- Before making any change that significantly alters content I've already created — stop completely. Describe exactly what you're about to change and why. Wait for my confirmation before proceeding. 'I think this would be better' is not permission to change it.
- Only change what I specifically asked you to change. Do not rewrite, rephrase, or 'improve' anything I didn't ask about — even if you think it would be better. If you notice something worth improving elsewhere, mention it at the end. Do not touch it unless I explicitly ask.
- After completing any coding task, always end with: Files changed. What was modified — one line per file. Files intentionally not touched. Follow-up needed. Keep it short — this is a status update, not a recap.
- Ask, don't assume — if something is unclear, ask before writing a single line. Never make silent assumptions.
-  Simplest solution first — always implement the simplest thing that could work. Don't add abstractions that weren't requested.
-  Don't touch unrelated code — if a file is not directly part of the current task, do not modify it. Ever.
-  Flag uncertainty explicitly — if you're not confident about an approach, say so before proceeding. Confidence without certainty causes more damage than admitting a gap.

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

### Hardware — Servidor Dell PowerEdge T410 (Fedora Server 44) — confirmado 2026-06-02

Servidor tower antigo (~2010) reaproveitado para serviços leves — **NÃO para IA** (CPU sem AVX, confirmado).

- Modelo: Dell PowerEdge T410 (HW A07) · BIOS 1.11.0 (2012) · OS: Fedora Linux 44 Server, kernel 7.0.10
- CPU: 1× Intel Xeon **E5620** (Westmere, 2010), 4c/8t @ 2.40 GHz, 1 socket populado (suporta 2). Flags só até **sse4_2 — SEM AVX/AVX2** → llama.cpp inviável.
- RAM: **16 GB DDR3 ECC 1333** (2× 8 GB, slots A1/A2; A3/A4 livres) · GPU: Matrox G200eW (iDRAC, inútil p/ ML)
- Disco: 1× WD 500 GB **7200rpm mecânico** (SATA via SAS), sem redundância; **fedora-root só 15 GB, ~448 GB livres no VG** · HBA LSI SAS1068E (não-PERC) · Rede: 2× gigabit Broadcom

Implicações: fora do pipeline de IA. Bom host always-on para serviços CPU/rede (SearXNG, sync, armazenamento, containers). Ressalvas: disco único (backup importa); consumo elétrico alto (~100W+ ocioso, aprox.).

LVM (2026-06-02): root (`/dev/fedora/root`, VG `fedora`, XFS) estendido de 15 GB → ~463 GB. **Quirk:** o `system.devices` listava o disco por um WWID da controladora LSI SAS1068E que mudou; `pvs/vgs/lvs` vinham vazios apesar do root montado — resolvido com `sudo vgimportdevices --all`. Risco de recorrer após reboot (WWID instável → LVM perde a VG → emergency mode). Conserto definitivo **aplicado 2026-06-02**: `use_devicesfile = 0` em `/etc/lvm/lvm.conf` + `dracut -f` (LVM escaneia todos os discos sempre). Reboots devem ser seguros.

**Decisão (2026-05-24):** o laptop usa o **mesmo modelo de embedding do PC principal** (padronização). Como 2 GB de VRAM não comportam embedding model + LLM simultaneamente, o LOGOS deve suportar **modo CPU para inferência LLM** no laptop: quando a VRAM estiver ocupada pelo embedding, o LLM roda via llama-server com `--n-gpu-layers 0`. O LOGOS continua sendo o único ponto de acesso à IA — não há fallback de serviço, apenas alternância de backend de execução (GPU → CPU) gerenciada internamente pelo LOGOS.

---

## Testes obrigatórios

**Toda implementação nova deve vir acompanhada de testes — estabelecido em 2026-05-22.**

- Toda feature, endpoint, módulo ou função nova: escrever os testes na mesma resposta.
- Toda correção de bug: adicionar teste que cobre o caso corrigido **e sempre expandir para cobrir casos adjacentes, branches relacionadas e edge cases da função/módulo inteiro** — nunca limitar ao caso específico do bug.
- Nunca reportar um item como concluído sem que os testes correspondentes existam e passem.

**Ambientes Python por app (CachyOS principal) — onde rodar pytest:**
- **Mnemosyne** usa o **venv compartilhado da raiz**: `program files/.venv` (o `Mnemosyne/iniciar.sh` aponta para `../.venv`). Rodar: `"program files/.venv/bin/python" -m pytest …` de dentro de `Mnemosyne/`.
- **AKASHA** tem o **próprio venv**: `AKASHA/.venv` (Python **3.13**). Separado porque o `pyproject.toml` da AKASHA declara `requires-python = ">=3.11,<3.14"` — o venv da raiz é Python **3.14** e viola esse limite, então a AKASHA não pode usar o compartilhado. A AKASHA é gerenciada por `uv` (auto-sync no `iniciar.sh`); o Mnemosyne usa venv manual compartilhado.
- `python`/`python3` do sistema NÃO têm as dependências — sempre usar o venv correto. Erro a evitar: procurar `.venv` só dentro de `Mnemosyne/` e concluir que o ambiente não existe; ele está um nível acima, compartilhado.
- **Para instalar/atualizar dependências, a usuária usa `atualizar.sh` (CachyOS) / `atualizar.bat` (Windows)** — esse é o ponto de entrada oficial de setup de ambiente. Verificar esse script antes de assumir como os venvs são criados. O `atualizar.sh` faz: AKASHA via `uv sync` (venv próprio); venv compartilhado da raiz (KOSMOS, Mnemosyne, Hermes) criado com `python3 -m venv`.
- **Risco latente (sinalizado 2026-06-02, NÃO corrigido):** o `.venv` compartilhado nasce de `python3 -m venv` e herda o Python default do sistema (hoje 3.14). Em 3.14, langchain emite warning de incompatibilidade do pydantic v1 (visto nos testes do Mnemosyne) — só warning por ora, testes passam, mas pode quebrar numa futura atualização de langchain/pydantic. Mitigação possível (não aplicada, decisão da usuária): fixar `python3.13 -m venv` no `atualizar.sh`. Não implementar sem ordem explícita.

---

## Bugs detectados durante o trabalho

**Todo bug ou erro detectado deve ser reportado — nunca ignorado silenciosamente.**

- Se puder corrigir imediatamente → corrigir e reportar na mesma resposta.
- Se não puder corrigir imediatamente → anotar no TODO (seção `#### <App>` dentro do `### Bugs e investigações reportados após uso real`) **e avisar a usuária explicitamente** na mesma resposta.
- **Em ambos os casos:** registrar no `BUGS.md` (raiz do ecossistema) seguindo o template do arquivo — campos obrigatórios: identificação, ambiente, pré-condição, sintoma, logs, causa raiz, impacto, fix, teste de regressão. Acrescentar sempre no final (ordem cronológica crescente) e atualizar o índice no topo do arquivo.

---

## Princípio de erros

**Tratamento de erros com tipagem é prioridade absoluta em todo o ecossistema.**

- **Rust (AETHER):** toda função falível retorna `Result<T, AppError>`. Zero `.unwrap()` em produção.
- **TypeScript (OGMA):** `strict: true`. Erros tipados com discriminated unions. Nunca `any`.
- **Python (KOSMOS · Mnemosyne · Hermes):** `except ValueError` (específico), nunca `except Exception` genérico sem re-tipar.

---

## Princípio de observabilidade — TUDO gera logs (estabelecido 2026-06-03)

**Absolutamente tudo no ecossistema deve gerar logs. Sem exceção, em todos os apps.**

- Toda operação, processo, job de background, requisição, chamada externa (rede/LLM/DB), transição de estado relevante, ação da usuária e **todo caminho de erro** emite log pelo logger do app (`logging` em Python, `log::` em Rust, logger equivalente em TS).
- **Proibido caminho silencioso:** nenhum `except/catch` pode engolir um erro sem logar. `except: pass` e `.ok()`/`unwrap_or` que descartam erro sem registro são violação direta desta diretiva — sempre logar antes de seguir.
- **Níveis apropriados** (para a observabilidade não virar ruído): `debug` para detalhe fino/fluxo interno; `info` para operações e marcos; `warning` para degradação/fallback; `error` para falha real. O critério é "tudo é registrado", não "tudo em info".
- Vale para **código novo e existente**: todo código novo já nasce instrumentado; código existente é trazido a esse padrão quando tocado (ou em auditoria dedicada, se solicitada).
- Reforça e eleva o passo 2 do workflow de implementação ("criar logs para todo processo envolvendo a nova feature") para um princípio absoluto que cobre o ecossistema inteiro, não só features novas.

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

**SearXNG (backend de busca) — hospedado no servidor T410 (2026-06-02):** roda em `http://192.168.0.252:8080` (**HTTP, sem TLS**), stack oficial searxng-docker (containers `searxng-core` + `searxng-valkey`), gerenciado via Docker (sem unit systemd; reiniciar com `sudo docker restart searxng-core`). `settings.yml` em `/home/spacewitch/searxng/core-config/settings.yml`. `limiter: false`. Para a AKASHA consumir JSON, `search.formats` precisa incluir `json` (default só tinha `html` → 403) — **habilitado e confirmado 2026-06-02** (retorna 200 JSON). **Curadoria de engines (2026-06-02):** ativos = google+bing+startpage (geral) + arxiv/semantic scholar; desabilitados ddg/brave/wikipedia/wikidata/qwant; mojeek habilitado mas bloqueia o IP do servidor. O `settings.yml` curado original do PC principal sobrevive em `~/.config/searxng/settings.yml`. O filtro anti-spam fica no código da AKASHA (`web_search.py`), não no SearXNG. Porta 9090 desse servidor é o Cockpit, não o SearXNG. Instância anterior do PC principal (AUR, 8888) foi **desinstalada 2026-06-02** — o servidor T410 é agora a única instância; não assumir SearXNG local em `localhost:8888`. A AKASHA já usa o servidor: `akasha.web_search_backend` no `ecosystem.json` = `http://192.168.0.252:8080` (lido em runtime por `web_search.py:_get_searxng_url()`; editável no painel Busca do HUB).

**Intenção primária da AKASHA (decisão 2026-06-01): buscador independente via índice local.**
O índice local — construído a partir de crawling de domínios confiáveis, archivamento de páginas lidas e embeddings semânticos — é o núcleo e diferencial da AKASHA. Engines externos (SearXNG, DDG) existem como complemento secundário, não como núcleo. Ao sugerir ou implementar melhorias na AKASHA, priorizar sempre o pipeline de indexação local sobre qualidade de engines externos.

**Necessidade/objetivo da usuária (reforçado 2026-06-02):** usar a AKASHA como **substituto principal do Google**, com o **máximo de resultados possível** por busca (alvo do plano: 100–400; hoje ~8–62, baixo). Em qualquer trabalho de busca, o norte é maximizar volume **e** qualidade. Causas de volume baixo conhecidas: classificador de intenção que corta listas; só 3 engines mainstream sobrepostos (faltam engines independentes: Marginalia, mwmbl, Stract); BUG-025 (cache ignorava n_pages — corrigido 2026-06-02).

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

**O conteúdo do vault do AETHER não deve ser indexado por nenhuma IA do ecossistema.**
O vault contém escrita criativa pessoal. A regra é sobre indexação/RAG — nunca incluir `aether_vault` como fonte de indexação em AKASHA (`local_search.py`), Mnemosyne (`watched_dir`), KOSMOS ou qualquer outro app com pipeline de IA.
Apps que apenas leem os arquivos (sem indexar) podem ter acesso autorizado: OGMA (editor) e futuramente CODEX (leitor/revisor mobile). Acesso de leitura ≠ indexação.

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
- **P1 (crítica):** KOSMOS — usuária abriu artigo e a análise LLM está sendo exibida (usuária esperando)
- **P2 (importante):** buscas RAG no Mnemosyne; KOSMOS sync/análise de feed (não urgente)
- **P3 (background):** knowledge_worker AKASHA, reflexões/indexação Mnemosyne, análise background KOSMOS — **P3 nunca é bloqueado, apenas atrasado** (delay loop, não hard-reject)
- **AETHER não chama o LOGOS** — é apenas editor de texto, sem integração com LLM.

**KOSMOS — estado atual e futuro:**
O KOSMOS v3 foi replanejado do zero em 2026-06-01 como ferramenta para jornalistas, estudantes e ativistas. Stack: PySide6, SQLite sincronizado via Syncthing, LOGOS para análise AI. Análise em 2 calls: Call A rápido (tags, sentimento, clickbait) em P3 background; Call B rico (cinco Ws, entidades, viés político) em P1 ao abrir artigo. Cards atualizam em tempo real conforme análise chega. Quando chamar o LOGOS, usará `llm_analysis` (ex: gemma2:2b) com `ServerTarget::Kosmos` na porta 8084. CPU fallback automático quando VRAM ocupada por AKASHA (8081) + Mnemosyne (8083). P3 nunca é bloqueado pelo LOGOS — apenas atrasado. Implementação por fases: base silenciosa → leitor funcional → scraping → análise AI → archivamento → tradução → ferramentas de investigação → stats e highlights.

Monitora VRAM da RX 6600 e pausa tarefas P3 quando VRAM > 85%. O HUB **não é** um app Android — a Fase 3 (Android APK do HUB) está suspensa. **Acesso mobile será via CODEX** (Tauri v2 + React + Rust, mobile stack TBD na Fase 6). O CODEX não é apenas leitor — é editor de AETHER e OGMA no celular/tablet, e ponto de acesso remoto a AKASHA, Mnemosyne e KOSMOS via **SSH tunnel gerenciado internamente pelo app** (configurado uma vez nas settings; mDNS na rede local, SSH quando remoto). AETHER e OGMA são acessados via Syncthing (offline-first). Dispositivo alvo: Samsung Tab S9 FE com S Pen. Fase 7 inclui canvas manuscrito com Excalidraw (arquivos `.excalidraw` no Syncthing — sem lock-in).

**Embed-server roda SEMPRE em CPU — diretiva (2026-06-03, já implementada):** modelos de embedding rodam em CPU em **todas as máquinas** (PC principal, laptop, trabalho), **independente do que está ou não carregado na VRAM**. `logos.embed_n_gpu_layers = 0`, fixo — **não** é ajustável para GPU. Esta diretiva **supersede** a redação anterior do BUG-028 que tratava o CPU como "default configurável por máquina (-1 para forçar GPU)". O embed-server (bge-m3 Q8, ~567 MB / ~0,6 GB VRAM) é leve e roda em CPU sem disputar VRAM com os LLMs de chat de AKASHA+Mnemosyne (no PC principal os dois LLMs juntos já passam de 80% da VRAM da RX 6600). Manter o embedding fora da VRAM elimina pela raiz o BUG-028 (watchdog de VRAM matava o embed-server P3 ao passar do limite, e o watchdog do embed-server o ressuscitava → loop de restart → Mnemosyne dava timeout e não indexava). No laptop (MX150, 2 GB), embedding em CPU também libera a VRAM inteira para o LLM. **Nunca** trocar `embed_n_gpu_layers` para -1/GPU em nenhuma máquina.

**Embedding é bge-m3 via LOGOS em TODAS as máquinas, inclusive o work_pc (BUG-031, 2026-06-04).** O modelo `potion-multilingual-128M` (model2vec) foi **removido** do Mnemosyne. Motivo: o banco vetorial é sincronizado via Syncthing, e vetores de modelos diferentes são incompatíveis — o work_pc embedava queries com POTION (128 dim) contra o índice bge-m3 (1024 dim), **quebrando a busca**. Como o work_pc **não indexa** (só consulta o índice sincronizado), bge-m3 em CPU lá embeda só 1 query por vez (leve). Regra: **todas as máquinas que compartilham um índice DEVEM usar o mesmo modelo de embedding** — nunca misturar. O perfil `work_pc` no `logos.rs` agora usa `embed: "bge-m3"`. **Sentimento (valence/arousal) também saiu do HF:** o modelo `cardiffnlp` foi removido; o valor autoritativo é **derivado do vetor Plutchik computado pelo LOGOS** (`_plutchik_to_va`), com léxicos NRC-VAD/VADER (tabelas de palavras, não IA) só como proxy rápido. **Nenhuma IA do Mnemosyne roda fora do LOGOS.**

**Questão correlata em aberto (BUG-028, não corrigida):** o watchdog de VRAM chama `do_silence()` (mata modelos P3) já no limiar normal de 85%, o que viola a diretiva "P3 nunca é bloqueado, apenas atrasado, exceto em situação extrema"; o threshold acordado é 93–95% (o caso padrão dual-server já usa >80%), e o bump condicional 85→93 existente não conta o embed-server. Ver itens no TODO.

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

## Regras de comportamento aprendidas

**Reler arquivo quando instruída (2026-05-31):**
Quando a usuária diz "leia X" ou "releia X", usar a ferramenta Read para ler o arquivo naquele momento. Sem exceção — não importa que o conteúdo está no contexto da sessão ou que "já sei o que está lá". Se ela disse para ler, lê. Nunca substituir por memória da sessão.

**GUI obrigatório para toda feature de usuário (2026-05-31):**
Toda feature de backend que o usuário precisa controlar DEVE ter um elemento de GUI visível e acessível. Parâmetros de URL como `?lang=`, `?diversity=N`, `?web_pages=N` existem como overrides programáticos — nunca são o único ponto de controle. O controle principal é sempre via elemento visível: campo em Settings, chip na página de busca, botão na interface de chat. Ao escrever itens de TODO que expõem opções ao usuário: se tem parâmetro de API → incluir o elemento de UI no mesmo item ou verificar que Config 2/settings.html o inclui explicitamente.

**Toda configuração deve estar na UI (2026-06-02):** "toda configuração de todos os programas do ecossistema deve ser exibida na UI". Nenhum valor de config pode ser editável **apenas** via JSON — cada chave precisa de controle de UI em algum lugar (UI própria do app OU HUB). Estado de runtime (`bg_processing.*`, `pending_insights`, `last_git_head`) e plumbing interno (paths derivados, ports internos) não contam como configuração do usuário. Item no TODO raiz (seção "Painel de configuração do ecossistema") cobre um **editor visual das seções do `ecosystem.json` no HUB**. Hoje a maioria das configs já tem UI (settings da AKASHA em `AKASHA/templates/settings.html`; LOGOS no HUB via assignment de modelos/limites; sync_root no SyncSetup), mas falta o editor centralizado cobrindo todas.

**Nenhuma informação pessoal hardcoded (2026-06-16):**
NENHUMA informação pessoal (e-mail, nome, cidade, tokens, caminhos pessoais, etc.) pode ser hardcoded no código do ecossistema. Esse tipo de valor deve sempre vir de configuração editável na UI (campo em Settings do app ou no HUB), lida em runtime, com default vazio e degradação graciosa quando não preenchido. Motivo: dado pessoal hardcoded vaza no repositório versionado/sincronizado, não é editável pela usuária e viola a diretiva "toda configuração deve estar na UI". Exemplo detectado: `AKASHA/services/paper_search.py` tinha um e-mail hardcoded para a API do Unpaywall (e `paper_download.py` lia de env var) em vez de um campo `akasha.unpaywall_email` na UI.

**Workflow de implementação não precisa ser relembrado (2026-06-02):**
A sequência completa de implementação deve ser seguida automaticamente em toda e qualquer implementação, atualização ou modificação — sem precisar ser repetida pela usuária a cada sessão. Sequência obrigatória para cada item do TODO: (1) implementar; (2) criar logs para todo processo envolvendo a nova feature; (3) escrever testes unitários e de integração na mesma resposta, cobrindo caso principal + adjacentes + edge cases; (4) executar a suite completa; (5) marcar `[x]` no TODO; (6) verificar e atualizar README e GUIDE; (7) commit; (8) resumir no chat (detalhado mas acessível — lógica e raciocínio, não código e tecnicidades); (9) parar e aguardar permissão. Um item por vez. Sem exceções de tamanho ou tipo de mudança.

**Pop-up/notificação é sempre sobre o momento atual (2026-06-17):**
Pop-up/notificação (da Akasha e do ecossistema) é **sempre a respeito do que está sendo visto/feito no momento** — a página ou busca atual — **nunca** sobre histórico, janela passada (ex.: "últimos 7 dias") ou atividade de outra máquina. Motivo: a notificação existe para cutucar no contexto presente; reagir a algo de dias atrás ou de outro dispositivo tira o pop-up de contexto e confunde. Aplicação: gatilhos de pop-up/overlay usam o contexto do agora; dados históricos e cross-device (ex.: `shared_history`) alimentam a **análise/reflexão** da assistente, nunca os pop-ups.

**Pendência nunca dentro de item TODO completado (2026-06-17):**
Nunca anotar trabalho pendente DENTRO de um item de TODO marcado `[x]` — item completo não é revisitado, então a pendência ali enterrada se perde (é inútil). Ao desmembrar/dividir uma tarefa: (1) avisar a usuária explicitamente; e (2) criar um **novo item `- [ ]` separado, logo em seguida ao item completado**, descrevendo o trabalho restante com contexto suficiente para ser implementado sozinho.

---

## Design

O sistema visual é definido no `DESIGN_BIBLE.txt` (raiz). A paleta canônica está em:
- `AETHER/src/styles/tokens.css` (web)
- `ecosystem_qt.py` → `build_qss()` (PyQt6: Hermes)
- `KOSMOS/app/theme/night.qss` (PySide6: KOSMOS)
- `Mnemosyne/gui/styles.qss` (PySide6)

Modo noturno: "Atlas Astronômico à Meia-Noite" (`#12161E` base).
