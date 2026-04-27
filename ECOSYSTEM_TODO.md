# ECOSYSTEM — Roadmap de Integração
# OGMA · KOSMOS · AETHER · MNEMOSYNE · HUB

Objetivo: ser o Maestro que harmoniza o desejo de conhecimento infinito (Polimatia) com as limitações físicas do seu hardware (RX 6600). Ele não apenas exibe dados; ele gerencia a existência das outras ferramentas.
Desenvolvimento em fases progressivas — cada fase entrega algo utilizável antes de avançar para a próxima.

O HUB é o **dashboard e painel de controle do ecossistema** — a interface central a partir da qual todos os outros apps são lançados, monitorados e configurados. Ele incorpora o **LOGOS**: proxy inteligente de LLM que monitora a VRAM da GPU e dita a hierarquia de execução da IA, garantindo que tarefas pesadas de fundo (análises do KOSMOS, transcrições do Hermes) cedam imediatamente à prioridade de atividades interativas (chat do HUB, escrita no AETHER). Centraliza lançamentos, perfis de energia e coordenação de recursos numa "Consola de Alquimista" — eliminando o atrito técnico e mantendo a ordem sistêmica do ecossistema.

## ONDE PARAMOS
> Itens processados e organizados nas seções **PENDÊNCIAS — AKASHA / KOSMOS / AETHER / ECOSSISTEMA** ao final deste arquivo.
> Esta seção mantida como rascunho/referência de contexto.

Não implemente nada do que vou pedir em seguida. Faça pesquisas necessárias e acrescente os passos necessários ao TODO respectivo.
- AKASHA: há alguma forma de priorizar resultados de sites e artigos acadêmicos e blogs? Talvez criar uma lista de "favoritos".
- AKASHA: quero também uma forma melhor de baixar/arquivar sites em md. Preciso que inclua mais sites, como o medium e SUbstack. O Medium da erro mesmo quando consigo acessar gratuitamente. Também quero que seja possível piorizar certos sites nas buscas mesmo sem clawlea-los.
- KOSMOS: não consegue fazer o scrapping de artigos do Medium. Pesquisa alternativas.
- AKASHA: talvez devessemos criar níveis de prioridade de pesquisa online para definirmos a ordem dos resultados. Pense na biblioteca/sites crawleados como prioridade 1, sites prioritários/favoritos como prioridade 2 e outros resultados como prioridade 3. Crie uma segunda coluna para exibir os resultados locais.
- AKASHA: quero poder pesquisar formatos específicos e o AKASHA pesquisar na internet arquivos que estão públicos para o acesso e dê a opção de baixar
- KOSMOS: quero que as tags no feed incluam tags que eu selecionei que foram criadas pela IA com base na análise do artigo. ALém disso, crie uma opção de estatística que exiba as tags de artigos que li com mais frequencia. 
- KOSMOS: verifique o que desencadeia a análise no KOSMOS (deve ser assim que um artigo é aberto  — mas também deve ser feita uma pré-análise nos artigos recebidos para detectar clickbait, tags, sentimento, relevância e política. Quero inclut a análise dos 5w nessa pré análise.). Ele está demorando a começar e a ser concluido, deve ter uma forma de melhorar e otimizar esse processo. Pesquise, crie um KOSMOS/pesquisa.txt e siga as regras do CLAUDE.md.
- KOSMOS: gosto das estatísticas que incluiem os 5w, mas talvez pudéssemos aumentar os gráficos e detalhá-los. Acho que serão informações importantes. 
- KOSMOS: talvez pudessemos criar uma forma do HUB fazer o KOSMOS começar a rodar em segundo plano, carregando apenas o necessário para baixar os artigos e fazer a pré análise
- KOSMOS: crie um aviso de status ao abrir um artigo para informar em que estado a análise do artigo se encontra, quer esteja em andamento, tenha havido um erro ou o que seja. Atualmente o aviso de análise só aparece quando arquivo um artigo, preciso que isso apareça independentemente.
- KOSMOS: verifique se a lista de fontes e artigos baixados já está sendo salva na pasta compartilhada do ecossistema para que eu possa manter sincronizado entre os dispositivos
- KOSMOS: crie uma forma de eu poder marcar dentro do artigo se eu tiver algum problema (texto incompleto, falha no scrapping e outros que você pensar) e faça isso diminuir o ranking de relevância daquela fonte. Mas também faça isso aparecer no log para podermos pesquisar possibilidades para resolver isso no futuro.
- ECOSSISTEMA: Interoperabilidade Silenciosa: O AKASHA poderia servir como o "indexador de fundo" para o ecossistema. Quando você buscar por um conceito, ele não apenas mostra o trecho do livro no Mnemosyne, mas também os artigos relacionados no KOSMOS e os vídeos transcritos no Hermes.
- ECOSSISTEMA: Transição de partes críticas do Python para módulos em Rust (via PyO3) nas ferramentas de busca (AKASHA) pode aumentar a velocidade de indexação do ChromaDB conforme seu vault cresce para a escala de terabytes.
  - Tantivy como Motor: Em vez de depender apenas do FTS5 do SQLite, você pode integrar a crate tantivy (uma alternativa em Rust ao Lucene/Elasticsearch). Ela é incrivelmente rápida e permite buscas complexas (booleana, fuzzy, facetada) em milissegundos, mesmo com milhões de documentos.
  - Processamento em Paralelo: Com a crate rayon, o Rust pode percorrer seu sistema de arquivos (usando walkdir) e processar arquivos Markdown, PDFs e transcrições em todas as threads disponíveis do seu processador, algo que o Python teria dificuldade devido ao GIL.
  - Embeddings no Core: O módulo em Rust pode gerenciar a fila de geração de vetores para o Mnemosyne. Ele detecta o novo arquivo, extrai o texto em Rust e apenas envia o "payload" limpo para o Python/Ollama gerar o embedding, mantendo a memória sob controle.
- ECOSSISTEMA: a idéia aqui é o AKASHA atuar como um Broker de Informação. Imagine a seguinte cena: você busca por um termo de Cibersegurança que estudou meses atrás. A Resposta Unificada: O AKASHA não retorna apenas links. Ele retorna um "Mapa de Contexto": Mnemosyne: Traz um resumo semântico (via RAG) de um PDF técnico denso. KOSMOS: Mostra 3 artigos de feeds RSS que você favoritou sobre o tema. Hermes: Apresenta o trecho exato de uma transcrição de vídeo do YouTube onde o conceito foi explicado. AETHER: Exibe uma nota de worldbuilding onde você aplicou esse conceito em uma narrativa. Isso é "silencioso" porque você não precisou abrir cada app. O HUB apenas consome essa API rica do AKASHA.
- ECOSSISTEMA: ao pesquisar por um conceito complexo de Cibersegurança, o AKASHA pode usar o vectorstore da Mnemosyne para encontrar parágrafos específicos dentro de PDFs técnicos, cruzar com uma transcrição do Hermes e sugerir um capítulo em rascunho no AETHER que trate de um tema similar. Contexto unificado: Isso remove o "atrito de alternância". Você não precisa lembrar onde guardou a informação; basta saber que ela existe no tecido do ecossistema.
- ECOSSISTEMA: o ideal é que as chamadas de IA passem por um serviço centralizado (ou um padrão de fila) que gerencie as prioridades, evitando que a pré-análise de segundo plano do KOSMOS "mate" a interatividade do chat no Mnemosyne.
- ECOSSISTEMA: [IMPORTANTE] como funciona o uso e gerenciamento do LLM local quando o Mnemosyne e o KOSMOS estão rodando ao mesmo tempo?
- o AKASHA não abriu no Windows. Terminal:
[AKASHA] Sincronizando dependencias...
[AKASHA] Iniciando servidor na porta 7070...
[AKASHA] Abrindo http://localhost:7070 no navegador...
D:\windows\ProgramFiles\ecosystem\ecosystem_client.py:22: UserWarning: filelock não instalado — write_section sem proteção contra race condition. Instale com: pip install filelock
  warnings.warn(
INFO:     Started server process [1512]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:7071 (Press CTRL+C to quit)
- AETHER: apesar de eu ter atualizado o endereço onde os arquivos deveriam ser salvos no HUB, ele continua salvando na pasta antiga e não encontro opção para configurar isso dentro do AETHER. Terminal:
[AETHER] Binario de release nao encontrado. Compilando agora...
[AETHER] Execute "cargo tauri build --no-bundle" para agilizar aberturas futuras.
     Running BeforeDevCommand (`npm run dev`)

> aether-scaffold@0.0.0 dev
> vite


  VITE v8.0.8  ready in 497 ms

  ➜  Local:   http://localhost:5174/
  ➜  Network: use --host to expose
     Running DevCommand (`cargo  run --no-default-features --color always --`)
        Info Watching D:\windows\ProgramFiles\ecosystem\AETHER\src-tauri for changes...
warning: hard linking files in the incremental compilation cache failed. copying files instead. consider moving the cache directory to a file system which supports hard linking in session dir `\\?\D:\windows\ProgramFiles\ecosystem\AETHER\src-tauri\target\debug\incremental\app_lib-1s5tgmff81ury\s-hho1uh6c1t-0rusvsq-working`

warning: constant `VAULT_CONFIG_FILE` is never used
  --> src\storage.rs:23:7
   |
23 | const VAULT_CONFIG_FILE: &str = "config.json";
   |       ^^^^^^^^^^^^^^^^^
   |
   = note: `#[warn(dead_code)]` (part of `#[warn(unused)]`) on by default

warning: function `load_vault_config` is never used
  --> src\storage.rs:83:8
   |
83 | pub fn load_vault_config(vault_path: &Path) -> Result<VaultConfig, AppError> {
   |        ^^^^^^^^^^^^^^^^^

warning: function `save_vault_config` is never used
  --> src\storage.rs:91:8
   |
91 | pub fn save_vault_config(vault_path: &Path, config: &VaultConfig) -> Result<(), AppError> {
   |        ^^^^^^^^^^^^^^^^^

warning: `app` (lib) generated 4 warnings
warning: hard linking files in the incremental compilation cache failed. copying files instead. consider moving the cache directory to a file system which supports hard linking in session dir `\\?\D:\windows\ProgramFiles\ecosystem\AETHER\src-tauri\target\debug\incremental\app-0ngj3dag8bu6w\s-hho1xceeuj-0wbbjal-working`

warning: `app` (bin "app") generated 1 warning
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 1m 15s
     Running `target\debug\app.exe`
[2026-04-24][18:19:14][app_lib][INFO] AETHER iniciado. Vault: Some("C:\\Users\\USUARIO\\Documents\\p\\My files\\backup\\notebook\\02_Areas\\escrita")
[2026-04-24][19:23:03][app_lib::commands::project][INFO] Projeto criado: 'Baldur's Gate 3' (f59919a4-9a67-4db3-8390-0fd4decb2114)
[2026-04-24][19:23:23][app_lib::commands::project][INFO] Projeto criado: 'Crepúsculo' (479f4237-359c-4b78-a472-ebfc278d7f99)

### LOGOS

A ideia é que nenhum app fale diretamente com o Ollama. Todos falam com o **LOGOS**, e ele decide o que fazer.

!!! pensar se é melhor mesmo mantê-lo independente ou integrá-lo ao HUB. Talvez seja interessante repensar o HUB, tornando a função principal dele gerenciar os outros programas. Já faz parte do workflow do ecossistema o HUB ser o centro de tudo e os outros programas serem sempre abertos e ter suas pastas configuradas pelo HUB.

### As 4 Funções do LOGOS

1.  **Interceptação de Requisições (O Proxy):**
    * Em vez de apontar o HUB/Mnemosyne para o `localhost:11434`, você os aponta para o `localhost:7072` (LOGOS).
    * O LOGOS olha para a requisição e vê: "Ah, o KOSMOS quer resumir um artigo, mas a prioridade dele é baixa".

2.  **Gerenciador de Prioridades (Fila Dinâmica):**
    * **Prioridade 1 (Crítica):** Chat interativo do HUB e escrita ativa no AETHER. O LOGOS suspende qualquer outra tarefa de IA para dar vazão imediata a estas.
    * **Prioridade 2 (Importante):** Buscas RAG no Mnemosyne.
    * **Prioridade 3 (Background):** Pré-análise de artigos no KOSMOS e transcrições no Hermes. Rodam apenas quando a GPU está ociosa.

3.  **Hardware Guard (O Escudo da GPU):**
    * O LOGOS monitora a VRAM da sua **RX 6600** em tempo real.
    * Se a VRAM passar de 85%, ele pausa as tarefas de Prioridade 3 e limpa o cache do Ollama (usando `keep_alive: 0`).
    * Ele injeta automaticamente parâmetros como `num_gpu` e `num_ctx` menores em tarefas de segundo plano para garantir que o sistema não trave.

4.  **Otimização de Contexto:**
    * Se o KOSMOS pede um resumo, o LOGOS pode "podar" o contexto para 2048 tokens antes de enviar ao Ollama, economizando memória preciosa.

---

### 💡 Próximos Passos para o Desenvolvimento

1.  **Defina os Perfis de Hardware:** Crie no `ecosystem.json` perfis como "Modo Trabalho" (Prioriza Mnemosyne/AETHER) e "Modo Consumo" (Prioriza KOSMOS/HUB).
2.  **Módulo de Monitoramento:** Use uma biblioteca como `pyadl` ou execute comandos `rocm-smi` (no Arch) e `nvidia-smi/WMIC` (no Windows) dentro do LOGOS para saber quanto de VRAM resta antes de aceitar uma nova tarefa.
3.  **A "Interrupção Graciosa":** Implemente uma forma de o LOGOS enviar um sinal para o KOSMOS pausar um scrapping se você começar a digitar no chat do HUB.
4.  Tratamento de Erros: Rust garante que se o LOGOS falhar ao detectar a VRAM, o erro seja tratado antes de causar um kernel panic ou travar o driver da AMD.
5.  No HUB, você pode ter widgets em tempo real:
    1.  Um pequeno indicador estelar (seguindo sua estética) que brilha mais forte quando a GPU está livre e fica vermelho/denso quando o KOSMOS está processando.
    2.  Um botão de "Pânico/Silêncio" que suspende todas as IAs de fundo instantaneamente para você focar na escrita no AETHER.
6. O HUB já tem a função de lançar os apps. Com o LOGOS dentro dele: O HUB pode decidir não abrir o Mnemosyne se detectar que o Hermes está usando 90% da VRAM em uma transcrição, avisando você com um toast elegante.

### Como o LOGOS operaria dentro do HUB

Ao centralizar no HUB, o fluxo de comunicação mudaria para um modelo de Autoridade Central:

    Apps (Clientes): KOSMOS, Mnemosyne e Hermes não perguntariam ao Ollama "Você está livre?". Eles enviariam um evento via WebSocket ou HTTP local para o HUB: LOGOS, preciso de 2GB de VRAM para um resumo.

    Decisão do LOGOS (Rust): O backend do HUB verifica o estado da RX 6600. Se houver espaço, ele retorna o "ticket" de autorização.

    Execução: O app prossegue. Se o HUB detectar que você abriu a aba de "Perguntas" (Chat interativo), ele revoga os tickets de baixa prioridade.

    Ponto de Candura: O único desafio dessa abordagem é que, para o KOSMOS ou o Hermes continuarem sendo otimizados em segundo plano, o HUB precisará estar sempre aberto (mesmo que minimizado na tray). Se você fechar o HUB, o maestro sai do palco e os outros apps perdem a coordenação do hardware.


### Anotações

#### 1. Refinamento do Protocolo de "Ticket" (Comunicação)
Como o HUB (Rust/Tauri) será o servidor do LOGOS, o Claude precisará saber como os outros apps (Python) devem se comportar.
* **Sugestão:** Adicione que o LOGOS deve expor uma **API REST ou WebSocket interna** (ex: porta 7072).
* **O fluxo:** O app envia um `POST /request_ticket { "app": "KOSMOS", "priority": 3, "estimated_vram": "2GB" }`. O LOGOS responde com um `201 Created` (Autorizado) ou `429 Too Many Requests` (Fila/Pausa).

#### 2. Especificidade da GPU (AMD/ROCm)
Como você usa uma **RX 6600** no CachyOS, o monitoramento de VRAM é diferente de placas NVIDIA.
* **Nota para o Claude:** Lembre-o de que no Linux a ferramenta primária é o `rocm-smi`, e no Windows o monitoramento deve ser via `pyadl` ou consultas ao driver AMD. O Rust (backend do HUB) pode usar crates como `sysinfo`, mas para VRAM de AMD específica, chamadas de sistema podem ser necessárias.

#### 3. Gerenciamento de Estado do Ollama
O Ollama já possui uma fila interna, mas ele não sabe das suas prioridades pessoais.
* **Logística:** Informe ao Claude que o LOGOS deve ser capaz de enviar um sinal de "CANCEL" ou limpar o contexto do Ollama via API (`/api/generate` com `keep_alive: 0`) para forçar a liberação de VRAM quando uma tarefa de Prioridade 1 (Escrita no AETHER) surgir.

#### 4. O Cenário de "Failsafe" (Plano B)
O que acontece se o HUB for fechado acidentalmente?
* **Definição:** Decida se os apps devem "travar" (esperando o maestro) ou se devem ter um modo de "emergência" onde tentam falar diretamente com o Ollama com configurações mínimas de segurança.

---

## PRINCÍPIOS INEGOCIÁVEIS

**HUB é o primeiro app a rodar.** Centraliza todas as configurações comuns do ecossistema.
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

## FASE 0 — Fundação do ecossistema
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

### 0.5 — sync_root: sincronização via Proton Drive (ou qualquer pasta sync)

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

### 0.6 — OGMA: migrar de Turso para Proton Drive (SQLite local)

Motivação: Proton mantém cópias locais em todas as máquinas + nuvem, sem depender de
conta externa. Turso só mantém na nuvem.

- [x] Remover integração Turso do OGMA (`src/main/database.ts` — voltar para SQLite puro local)
      Remover dependências: `@libsql/client`, `dotenv` e o `.env` com token Turso
- [x] Adicionar `ogma/` ao `sync_root` em `apply_sync_root()` (Rust + derive_paths Python)
      `data_path: {sync_root}/ogma/` — inclui `ogma.db`, `uploads/`, `exports/`
- [x] Atualizar `paths.ts` do OGMA para usar `ogma.data_path` do ecosystem.json (fallback local)
- [ ] Testar migração: exportar dados do Turso → importar no SQLite local antes de remover

### 0.7 — Hermes: usar output_dir do ecosystem.json no startup

Objetivo: Hermes deve ler `hermes.output_dir` do ecosystem.json se `outdir` não estiver
nas prefs locais — o mesmo padrão já aplicado ao `mnemo_dir`. Após `apply_sync_root`,
Hermes passa a usar `{sync_root}/hermes/` automaticamente.

- [x] `Hermes/hermes.py` — `_load_prefs()`: se `outdir` não estiver em prefs, ler
      `hermes.output_dir` do ecosystem.json como fallback

### 0.8 — AKASHA: integração Hermes + DB no Proton + lista negra + UI

#### 0.8a — AKASHA indexa arquivos do Hermes na busca local
- [x] `AKASHA/config.py` — adicionar `hermes_output: str` lendo `hermes.output_dir` do ecosystem.json
- [x] `AKASHA/services/local_search.py` — adicionar 6ª fonte `HERMES` em `index_local_files()`

#### 0.8b — AKASHA: DB (biblioteca + lista negra) movível para Proton
- [x] `AKASHA/config.py` — `DB_PATH` lê `akasha.data_path` do ecosystem.json se disponível
- [x] `ecosystem_client.py` — `derive_paths()`: adicionar `data_path` à seção `akasha`
- [x] `HUB/src-tauri/src/commands/config.rs` — `apply_sync_root()`: incluir `akasha.data_path`

#### 0.8c — AKASHA: aba "lista negra" no menu
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

### 0.9 — Mnemosyne: caminhos primários do ecosystem.json + pastas extras

Objetivo: Mnemosyne lê `watched_dir`, `vault_dir`, `chroma_dir` do ecosystem.json no
startup (HUB é fonte de verdade). SetupDialog exibe esses caminhos como read-only e
permite adicionar `extra_dirs` para indexação adicional.

- [ ] `Mnemosyne/core/config.py` — adicionar `extra_dirs: list[str]`; `load_config()` merge
      ecosystem.json: watched_dir/vault_dir/chroma_dir do ecosystem têm precedência
- [ ] `Mnemosyne/gui/main_window.py` — SetupDialog: caminhos principais viram read-only
      (vindos do ecosystem); adicionar QListWidget "Pastas extras" com +/−
- [ ] `Mnemosyne/core/` (indexador) — loop sobre `[watched_dir] + extra_dirs`

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

### 0.10 — Arquivos de configuração de todos os apps no Proton Drive

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

## FASE 1 — Interligação dos apps existentes
> Aproveita o que já existe. Mudanças cirúrgicas, sem novo app.

### 1.1 — OGMA → AETHER (projetos de escrita)

#### Passo A — Renomear tipo `creative` → `writing` no OGMA
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

#### Passo B — Integrar projetos de escrita com o AETHER
- [x] `src/main/database.ts`: adicionar coluna `aether_project_id TEXT` na tabela
      `projects` (nova migration)
- [x] OGMA lê `aether.vault_path` do `ecosystem.json` na criação de projeto
- [x] Ao criar projeto com `project_type = 'writing'`, OGMA escreve no vault AETHER:
      - `{vault}/{uuid}/project.json`  (formato Project do AETHER — campos: id, name, project_type, genre, description)
      - `{vault}/{uuid}/{book_uuid}/book.json`  (livro padrão vazio, sem capítulos)
- [x] Salvar `aether_project_id` no banco do OGMA para manter o vínculo
- [x] Botão "Abrir no AETHER" em projetos de escrita (desabilitado se vault não configurado)

### 1.2 — KOSMOS → Mnemosyne (artigos salvos)
- [x] KOSMOS escreve `archive_path` e `data_path` em `ecosystem.json` na inicialização
      via `ecosystem_client.write_section("kosmos", {...})` em `KOSMOS/main.py`
- [x] Mnemosyne lê `ecosystem.json` e oferece o archive do KOSMOS
      como pasta sugerida na tela de indexação (botão "Sugestões do ecossistema" na SetupDialog)
- [ ] Verificar se o botão "Arquivar" em artigos salvos chama
      `archive_manager` corretamente — garantir que gera `.md` válido

### 1.3 — AETHER → Mnemosyne (indexar escritos)
- [x] AETHER escreve `vault_path` em `ecosystem.json` na inicialização
      (startup Rust, após carregar vault — `ecosystem::write_section()` em lib.rs)
- [x] Mnemosyne oferece vault AETHER como pasta sugerida (botão "Sugestões do ecossistema")
- [ ] Testar indexação dos `.md` de capítulos pelo Mnemosyne

### 1.4 — Hermes → Mnemosyne (transcrições indexáveis)
- [x] Adicionar campo "Pasta de saída do Mnemosyne" na aba Transcrever do Hermes
      Lê `mnemosyne.index_paths[0]` do ecosystem como sugestão; desabilitado se vazio
- [x] Adicionar checkbox "Indexar no Mnemosyne após transcrever"
      Salva o `.md` diretamente numa das pastas monitoradas pelo Mnemosyne
- [x] Formato: Markdown limpo com frontmatter mínimo (título, data, fonte/URL, duração)

### 1.5 — Completar contrato ecosystem.json (seções faltantes)

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

### 1.6 — Scraper compartilhado: KOSMOS e AKASHA

Objetivo: eliminar a duplicação de código da cascata de extração web.
`ecosystem_scraper.py` (raiz do repo) é o único ponto de manutenção da cascata.

- [x] Criar `ecosystem_scraper.py` — cascata newspaper4k → trafilatura → readability-lxml
      → inscriptis → BeautifulSoup; `extract(html, url, output_format)` sem I/O próprio
- [x] `AKASHA/services/archiver.py` — delegar `_cascade_extract` ao módulo compartilhado
- [x] `AKASHA/services/library.py` — idem para `_fetch_and_extract`
- [x] `KOSMOS/app/core/article_scraper.py` — simplificar para `_cascade_extract(..., output_format="html")`
- [x] `KOSMOS/requirements.txt` — adicionar `inscriptis` e `markdownify`

### 1.8 — AKASHA: busca local cobre todo o ecossistema

- [x] Indexar `AKASHA/data/archive/` própria no FTS5 (source "AKASHA")
      (`index_local_files()` em `services/local_search.py` — mesmo extractor do KOSMOS)
- [x] Ler `mnemosyne.watched_dir` e `mnemosyne.vault_dir` do ecosystem.json em `config.py`
- [x] Indexar `mnemosyne.watched_dir` no FTS5 (source "MNEMOSYNE")
- [x] Indexar `mnemosyne.vault_dir` no FTS5 (source "OBSIDIAN")
      (depende de 1.5 — Mnemosyne precisa escrever esses caminhos primeiro)

### 1.9 — Mnemosyne: sugestões do ecossistema cobrindo todos os archives

- [x] Adicionar AKASHA archive (`akasha.archive_path`) nas sugestões da SetupDialog
      (depende de 1.5 — AKASHA precisa escrever `archive_path` primeiro)

---

## FASE 2 — App Hub (dashboard e painel de controle)
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

## FASE 3 — Android (APK)
> ⚠️ **SUSPENSA PARA REPLANEJAMENTO.** O HUB passou a ter papel de LOGOS (orquestrador de IA), mudando seu foco principal.
> A necessidade de acesso ao ecossistema no Android continua existindo, mas a abordagem precisa ser repensada
> — provavelmente um app separado ou solução diferente do HUB. Itens abaixo mantidos como referência histórica.

### 3.1 — Build Android do hub
- [ ] Configurar ambiente Tauri Android:
      - Android Studio + NDK
      - `cargo install tauri-cli` (já deve estar instalado do AETHER)
- [ ] Adaptar `tauri.conf.json` para Android (permissões de filesystem)
- [ ] Primeiro build de teste no tablet (`cargo tauri android dev`)
- [ ] Resolver incompatibilidades de UI para toque (botões, scroll)
- [ ] Build de release (APK assinado)

### 3.2 — Sincronização de dados
- [ ] Configurar Syncthing: pastas a sincronizar
      - Vault AETHER completo
      - `kosmos/data/archive/`
      - `hub_read_state.json`
- [ ] Testar round-trip completo:
      - Escrever capítulo no tablet → sync → abrir no AETHER no PC
      - Salvar artigo no KOSMOS → sync → aparecer no hub Android
- [ ] Tratar conflitos de sync (dois dispositivos editam o mesmo arquivo)

### 3.3 — Acesso remoto (fora da rede local)
- [ ] Instalar Tailscale no PC e no tablet
- [ ] Hub detecta se Ollama está acessível (local ou via Tailscale)
- [ ] Módulo Projetos: acesso ao `ogma.db` via Tailscale quando remoto
- [ ] Fallback gracioso: módulos funcionam offline com dados já sincronizados

---

## FASE 4 — Polimento e features extras
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

## Dependências entre fases

  Fase 0 ──► Fase 1 (qualquer sub-item)
  Fase 0 ──► Fase 2.1
  Fase 2.1 ──► Fase 2.2, 2.3, 2.4, 2.5 (paralelas)
  Fase 2 (completa) ──► Fase 3
  Fase 3 ──► Fase 4

---

## Estado dos apps individuais (pré-condições para integração)

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

## Estado das fases do ecossistema

  Fase 0: ✅ Base concluída (0–0.5). Items 0.6–0.9 em andamento (sync + integrações)
  Fase 1: ✅ Concluída — 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 1.9 concluídas
            ⚠️  Item pendente: 1.2 — verificar botão "Arquivar" no KOSMOS
  Fase 2: ✅ Concluída — 2.1, 2.2, 2.3, 2.4, 2.5 e 2.6 concluídas
  Fase 3: ⚠️ suspensa — HUB agora é LOGOS; acesso Android a repensar separadamente
  Fase 4: não iniciada

---

## PENDÊNCIAS — AKASHA

### Bug: porta errada no iniciar.bat/sh
- [x] `iniciar.bat` / `iniciar.sh` — corrigir porta: uvicorn sobe em 7071 mas o script abre `http://localhost:7070`

### Lista de favoritos (domínios prioritários)
- [x] `AKASHA/database.py` — tabela `favorite_domains` + migration 12
      Funções: `add_favorite_domain`, `remove_favorite_domain`, `list_favorite_domains`, `get_favorite_domains`
- [x] `AKASHA/routers/favorites.py` — CRUD completo (add, delete, to-blacklist, to-library)
- [x] `AKASHA/templates/favorites.html` + `_favorites_list.html` — página + partial HTMX
- [x] `AKASHA/templates/base.html` — link "favoritos" no nav
- [x] `AKASHA/main.py` — router registrado
- [x] Resultados de domínios favoritos sobem para P2 automaticamente na ordenação

### Busca: priorização e segunda coluna
- [x] Definir 3 níveis de prioridade nos resultados de busca:
  - P1: conteúdo local indexado (arquivos do ecossistema + biblioteca/sites crawleados)
  - P2: domínios favoritos/prioritários — web_results separados em fav_results antes de renderizar
  - P3: resultados web gerais
- [x] Criar segunda coluna (ou painel lateral) para exibir resultados locais separados dos web
      Coluna esquerda (principal): resultados web + biblioteca + ver depois
      Coluna direita (sidebar): resultados do ecossistema local (arquivos indexados)

### Extração: Medium e Substack
- [x] Pesquisar alternativas de scraping para Medium (falha mesmo em artigos gratuitos)
  — solução: Freedium proxy (freedium.cfd) em get_fetch_url() no ecosystem_scraper.py
  — pesquisa salva em `AKASHA/pesquisa.txt`
- [x] Pesquisar e corrigir extração do Substack (padrão HTML diferente do Medium)
  — fix: seletores .available-content e .post-content adicionados ao _ext_bs4

### Busca de arquivos públicos por formato
- [x] Adicionar opção de pesquisar arquivos públicos (PDF, epub, etc.) na busca web
  — usar operadores de busca (`filetype:pdf site:...`) via engine configurada
  — exibir opção de download direto quando o arquivo for acessível publicamente

### Busca e download de artigos científicos
Pesquisa salva em `AKASHA/pesquisa.txt` — APIs, download, extração de PDF.

- [x] `AKASHA/services/paper_search.py` — busca paralela em Semantic Scholar + arXiv (`aioarxiv`)
  — Semantic Scholar: sem key necessária para uso básico, 200M+ papers, campo `openAccessPdf.url`
  — arXiv: `aioarxiv` (async nativo), PDFs sempre gratuitos em arxiv.org/pdf/{id}
  — retorna `list[PaperResult(SearchResult)]` com source="PAPER" e campos extras (DOI, ano, autores)
- [x] `AKASHA/services/paper_download.py` — download de PDF open access por resultado de busca
  — fluxo: URL direta → arXiv direto → Unpaywall REST (sem lib) via httpx
  — extração PDF → Markdown via `pymupdf4llm` (CPU-only); fallback `pypdf`
- [x] `AKASHA/services/archiver.py` — nova função `archive_pdf(content_md, metadata)` 
  — salva em `data/archive/Papers/` com frontmatter YAML (mesmo padrão do `Web/`)
  — indexado automaticamente pelo Mnemosyne via `watched_dir` sem nenhuma mudança no Mnemosyne
- [x] `AKASHA/routers/search.py` — fonte `src_papers` no `GET /search` + gather paralelo
- [x] `AKASHA/routers/papers.py` — rota `POST /papers/download` (novo router)
- [x] `AKASHA/templates/search.html` — seção de resultados acadêmicos
  — campos específicos: DOI, ano, autores, badge "PDF disponível"
- [x] `AKASHA/templates/base.html` — checkbox `src_papers` nos filtros de busca
- [x] `AKASHA/templates/_macros.html` — macro `paper_card(r)` com botão arquivar
- [x] Dependências novas: `aioarxiv`, `pymupdf4llm` (unpaywall: chamada REST direta)

### Abrir arquivos locais / leitor do ecossistema
- [x] `/open-file` com xdg-open já implementado (com fallback `gio open` e detecção de erro — BUG-6 corrigido)
- [ ] **Leitor próprio do ecossistema** — criar leitor de artigos/documentos integrado, inspirado no reader mode do KOSMOS; prioridade baixa, fazer após o xdg-open estar estável

### AKASHA — busca local e fusão de resultados

- [ ] Bug: `_search_chroma()` cria novo `PersistentClient` a cada query — cachear como singleton:
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

- [ ] AKASHA: substituir `rank_combined()` por Reciprocal Rank Fusion (RRF):
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

- [ ] AKASHA: FTS5 com tokenizer `unicode61 remove_diacritics=2` para busca acentuada:
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

- [ ] AKASHA: deduplicação de conteúdo crawlado por hash SHA-256:
  **Motivo:** o crawler normaliza URLs mas não detecta conteúdo duplicado entre URLs diferentes
  (syndication, mirrors, redirects resolvidos). Dois artigos com mesmo conteúdo são indexados
  e buscados duplicadamente, poluindo os resultados.
  Mesma técnica do KOSMOS: SHA-256 do conteúdo extraído como guarda de deduplicação.
  **Implementação (`AKASHA/services/crawler.py` + `database.py`):**
  1. Adicionar coluna `content_hash TEXT` à tabela que armazena páginas crawladas
  2. Antes de persistir uma página: calcular `hashlib.sha256(content.encode()).hexdigest()`
  3. `SELECT id FROM crawled_pages WHERE content_hash = ?` — se existir: ignorar URL, não re-indexar
  4. Adicionar index em `content_hash` para a query ser O(1)

- [ ] AKASHA: ETag/Last-Modified no crawler para não re-crawlar páginas sem mudança:
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

- [ ] AKASHA: throttle adaptativo no crawler baseado em tempo de resposta do servidor:
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

- [ ] AKASHA: Trafilatura como primeiro estágio de extração (substituição em ecosystem_scraper.py):
  **Motivo:** idêntico ao KOSMOS — F1=0.945 do Trafilatura vs F1=0.665 do BeautifulSoup.
  Conteúdo mais limpo no índice FTS5 do AKASHA = busca mais precisa, menos falsos positivos.
  Ver item equivalente em PENDÊNCIAS — KOSMOS para implementação detalhada (compartilham
  o `ecosystem_scraper.py`).

### Responsividade — AKASHA (prioridade alta)

> Contexto: AKASHA é usado frequentemente em janela não-cheia. O CSS já tem breakpoints
> em 900px (colunas de busca) e 860px (topbar), mas várias seções ainda quebram em janelas médias.

- [x] **Cards de resultado — ações em janela estreita**
  — `.result-actions` overflow em janelas ~600–800px: botões saem do card ou ficam comprimidos
  — Fix: `flex-wrap: wrap` + `justify-content: flex-end` nas ações; máx 2 ações por linha em < 700px
  — Botões de ação: reduzir para ícone (sem texto) abaixo de 680px com `title` tooltip
- [x] **Tabela de downloads (`dl-table`) — responsividade**
  — Em janelas estreitas a tabela quebra (coluna URL muito longa, coluna data sobreposta)
  — Fix: ocultar coluna "Concluído" abaixo de 700px; truncar URL com `max-width` + `text-overflow`
  — Abaixo de 520px: substituir tabela por cards empilhados (cada download = 1 card compacto)
- [x] **Formulário de download em linha (`dl-form`)**
  — Em janelas estreitas os 3 campos ficam espremidos
  — Fix: `flex-direction: column` abaixo de 580px; cada campo ocupa 100% da largura
- [x] **Página de biblioteca (`/library`) — grid de cards**
  — Cards da biblioteca usam grid mas não têm breakpoint explícito abaixo de 700px
  — Auditado: layout é flex coluna única (não grid); inline styles extraídos para classes CSS
  — lib-site-row/info/actions: @media 640px → coluna; lib-discover-form: flex-wrap
- [x] **Topbar — links de navegação em janela ~700px**
  — Entre 540px e 860px os links de nav ficam em segunda linha mas com espaçamento irregular
  — Fix: column-gap/row-gap separados (row-gap: 0); nav controla espaço via margin-top: 4px
- [x] **Página watch-later, history, favorites**
  — Auditadas e corrigidas: lib-entries/meta-row/notes-row (CSS ausente), btn-label + title nos botões,
    history inline styles → classes CSS, lib-add-row flex-wrap, domains-actions flex-wrap
- [x] **Testar em janelas representativas:** 800×600, 1024×600, 1280×720 (não apenas mobile)
  — Servidor iniciado: todas as 6 páginas retornam HTTP 200 sem erros
  — CSS auditado: regra duplicada .domains-actions consolidada; breakpoints verificados (680/580/520/480/640/860/540/700px)
  — Teste visual manual recomendado no browser a 800px e 650px

---

## PENDÊNCIAS — KOSMOS

### Bug: scraping do Medium falha
- [x] Pesquisar alternativas ao scraping do Medium
  — pesquisa salva em `KOSMOS/pesquisa.txt`
  — fix compartilhado via ecosystem_scraper.py (get_fetch_url → Freedium proxy)

### Tags geradas por IA nos cards do feed
- [x] Exibir tags geradas pela análise de IA diretamente nos cards do feed
  — tags aprovadas pelo usuário (article_tags) exibidas como chips nos cards do feed
  — `FeedManager.get_tags_for_articles()` busca em batch para evitar N queries
  — `ArticleCard`: novo param `user_tags`, chips com objeto `QLabel#aiTagChip`
  — estilos `aiTagChip` adicionados em day.qss e night.qss
- [x] Estatística de tags: exibir na view de stats as tags mais frequentes nos artigos lidos
  — `get_top_ai_tags_read(days, limit)` em stats.py: conta tags de `ai_tags` JSON nos artigos lidos
  — `StatsView._build_ai_tags_chart()`: gráfico horizontal exibido abaixo do sentimento

### Pré-análise em background (requer pesquisa prévia)
- [x] Criar `KOSMOS/pesquisa.txt` — pesquisar otimizações para o pipeline de análise (obrigatório per CLAUDE.md)
  — verificar quando e como a análise é disparada: atualmente apenas ao abrir o artigo
  — objetivo: pré-análise ao receber novos artigos (clickbait, tags, sentimento, relevância, 5Ws)
  — investigar causas da lentidão (tempo de início + tempo de conclusão)
- [x] Após pesquisa: implementar pré-análise em background para artigos recém-recebidos
  — `BackgroundAnalyzer` (QThread + PriorityQueue): HIGH=artigo aberto, LOW=pré-análise silenciosa
  — enfileira artigos sem análise no startup + a cada `feed_updated`; lotes de até 5 artigos/call
  — integrado no MainWindow; sinal `article_analyzed` propagado para atualizar badges na UI
- [x] Incluir análise dos 5Ws na pré-análise
  — campo `five_ws` incluído no JSON Schema tanto do `_AnalyzeWorker` quanto do `BackgroundAnalyzer`
  — batch schema com schema dinâmico por lote; fallback individual em caso de falha

### Estatísticas expandidas
- [ ] Ampliar gráficos de estatísticas com detalhamento dos 5Ws
  — mais granularidade, mais gráficos por período e por fonte

### Status de análise visível ao abrir artigo
- [x] Criar indicador de status da análise ao abrir qualquer artigo
  — estados: "analisando…", "análise concluída", "erro na análise", "não analisado"
  — atualmente o indicador só aparece ao arquivar; deve ser independente dessa ação

### Verificação de sincronização
- [ ] Verificar se lista de fontes e artigos baixados está sendo salva na pasta compartilhada (Proton Drive)
  — confirmar que `archive_path` e `data_path` apontam para `sync_root/kosmos/`

### Marcação de problemas em artigos
- [ ] Criar mecanismo para marcar problemas dentro de um artigo
  — tipos: scraping incompleto, paywall, conteúdo cortado, outros (campo livre)
  — efeito: diminuir ranking de relevância da fonte automaticamente
  — registrar no log para análise futura de possíveis correções

### KOSMOS — qualidade de IA e integração com LOGOS

- [ ] Bug: `generate_stream()` bypassa o LOGOS — chamar via `ecosystem_client`:
  **Motivo:** `ai_bridge.py` linha ~162 chama `self._session.post(f"{self._endpoint}/api/generate")`
  diretamente, sem passar por `_request_llm`. Isso significa que leituras de artigo em streaming
  (P1) não estão registradas no LOGOS e não interrompem P3. O sistema de prioridades fica cego
  para toda interação do usuário com o reader do KOSMOS.
  **Implementação (`KOSMOS/app/core/ai_bridge.py`):**
  1. Substituir o bloco `generate_stream()` por uma chamada a `_request_llm(..., stream=True)`
     que já suporta streaming e retorna um generator de tokens
  2. Garantir que o `priority=1` seja passado para leituras interativas (o usuário abriu o artigo)
  3. Testar que o LogosPanel mostra P1 ativo durante leitura de artigo

- [ ] Bug: `embed()` bypassa o LOGOS — endpoint hardcoded na porta 11434:
  **Motivo:** `ai_bridge.py` linha ~207 chama `self._endpoint` diretamente (porta 11434, não 7072).
  O `keep_alive: "0"` que o LOGOS injetaria para P3 nunca é aplicado a embeddings do KOSMOS.
  **Implementação:**
  1. `AiBridge.__init__()`: usar como padrão o endpoint do LOGOS (7072) se disponível,
     configurado via `ecosystem_client.get_logos_url()` ou variável de ambiente `LOGOS_URL`
  2. Ou: redirecionar os embeddings do KOSMOS via `ecosystem_client.request_embed()` (a criar),
     que já sabe o endpoint correto e injeta headers `X-App: kosmos`

- [ ] KOSMOS workers de background: definir prioridade de OS com `os.nice()`:
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

- [ ] KOSMOS: deduplicação de artigos RSS por fingerprint de conteúdo:
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

## PENDÊNCIAS — AETHER

### Bug: vault_path não atualiza após mudança no HUB
- [ ] Investigar por que o AETHER continua salvando no caminho antigo mesmo após `sync_root` ser atualizado no HUB
  — log no startup mostra: `Vault: Some("C:\\Users\\USUARIO\\Documents\\p\\My files\\backup\\notebook\\02_Areas\\escrita")`
  — verificar `AETHER/src-tauri/src/lib.rs`: se a leitura do ecosystem.json acontece antes ou depois da gravação do vault_path local
  — verificar `AETHER/src-tauri/src/ecosystem.rs`: se `read_ecosystem` está lendo o arquivo atualizado
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

### Responsividade — Mnemosyne

> Mnemosyne é PySide6. Verificar os mesmos pontos de KOSMOS.

- [ ] **Auditar splitter principal (lista de documentos | viewer)**
  — Testar em 800px de largura; definir `setMinimumWidth` adequado em cada painel
- [ ] **Lista de documentos: truncar nome de arquivo longo com tooltip**
- [ ] **Testar em janela 800×600 mínima**

### Responsividade — Hermes

> Hermes é PyQt6 ou equivalente. Mesmos princípios de KOSMOS.

- [ ] **Auditar layout principal: lista de vídeos | área de transcrição**
  — Em janelas estreitas a transcrição precisa de scroll vertical, não horizontal
- [ ] **Testar em janela 800×600 mínima**

### Responsividade — HUB

> HUB é Tauri. A interface já é web-based mas deve funcionar em janelas menores.

- [ ] **Auditar grid de cards de apps**
  — De 3 colunas → 2 → 1 conforme janela estreita (CSS grid `auto-fill`)
- [ ] **LogosView e painéis de status**
  — Verificar que scrollam corretamente quando a janela é reduzida
- [ ] **Testar em janela 800×600 mínima**

---

## PENDÊNCIAS — ECOSSISTEMA

> Ver notas de design detalhadas em `## ONDE PARAMOS → LOGOS` neste arquivo.

### Mnemosyne: indexação automática em idle (Fase 10)

- [x] Quando o Mnemosyne não está indexando ativamente, monitorar as pastas do ecossistema
  e indexar automaticamente arquivos novos/modificados gerados por AKASHA, KOSMOS, Hermes e AETHER
  — pastas monitoradas: coleções `source == "ecosystem"` do `collections.py` (KOSMOS, AKASHA, Hermes)
  — implementação: `FolderWatcher` por coleção + `queue.Queue` + `_IndexJobWorker` (QTimer 30s, IdlePriority)
  — idle = nenhum IndexWorker/ResumeIndexWorker/UpdateIndexWorker/IndexFileWorker ativo
  — UI discreta: "⟳ Indexando N arquivo(s) do ecossistema…" na sidebar, silencioso quando fila vazia
  — ver detalhamento completo em `Mnemosyne/TODO.md — Fase 10`

### Bug: Mnemosyne `index_single_file` sem batching

> Causa confirmada de CPU a 90% durante idle indexing de artigos do KOSMOS.
> `index_single_file()` chama `vs.add_documents(chunks)` com todos os chunks de uma vez,
> sem pausas — ao contrário de `create_vectorstore()` e `IndexWorker`, que usam lotes e sleep.
> O IdleIndexer acumula uma fila de artigos do KOSMOS e processa cada um sem throttling,
> saturando o CPU continuamente.

- [ ] `Mnemosyne/core/indexer.py` — `index_single_file()`: substituir `vs.add_documents(chunks)`
  por loop com `_detect_batch_config()` (lotes de 25 chunks, sleep 0.3 s entre lotes),
  idêntico ao padrão já usado em `create_vectorstore()`

---

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

- [ ] `HUB/src-tauri/src/logos.rs` — implementar rotas de proxy para os endpoints nativos do Ollama:
  — `POST /api/chat` e `POST /api/generate` → proxy com fila P1/P2/P3 (mesma lógica do `/logos/chat`)
  — `POST /api/embeddings` e `POST /api/embed` → proxy com fila (P3 por padrão para embeddings)
  — `GET /api/tags`, `GET /api/ps`, `DELETE /api/delete` → proxy direto sem fila (metadados)
  — identificação do app por header `X-App: <nome>` (ex: `mnemosyne`, `kosmos`)
  — keep_alive: -1 injetado automaticamente em todas as chamadas de chat/generate que passam pelo proxy
  — Hardware Guard (VRAM, CPU, RAM) aplicado a todos os requests, não só aos via `/logos/chat`
- [ ] `ecosystem_client.py` — `OLLAMA_BASE_URL` aponta para 7072 (LOGOS) em vez de 11434;
  fallback para 11434 se LOGOS offline (modo emergência já existente)
- [ ] `Mnemosyne/core/indexer.py` e `workers.py` — `OllamaEmbeddings(base_url="http://localhost:7072")`,
  `ChatOllama(base_url="http://localhost:7072")`; header `X-App: mnemosyne` via parâmetro `headers`
- [ ] `KOSMOS/app/core/ai_bridge.py` — URL base para 7072; header `X-App: kosmos`
- [ ] Auditar todos os apps em busca de `localhost:11434` hardcoded e substituir pela URL do LOGOS
- [ ] Testar integração: chat no Mnemosyne (P1) enquanto KOSMOS analisa em background (P3)
  → KOSMOS deve pausar na fila do LOGOS até o chat terminar

### AKASHA como broker unificado de informação
- [ ] Planejar API de "Mapa de Contexto" no AKASHA:
  — dado um termo, retornar resultados cruzados: Mnemosyne (RAG) + KOSMOS (artigos) + Hermes (transcrições) + AETHER (notas)
- [ ] HUB consumir essa API num botão de busca global cross-app

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

## PENDÊNCIAS — HUB (dashboard e painel de controle)

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
- [ ] Monitoramento de CPU e RAM no painel LOGOS:
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

- [ ] LOGOS: injetar `keep_alive` automaticamente por prioridade no proxy transparente:
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

- [ ] LOGOS: configurar variáveis de ambiente do Ollama por perfil de hardware no startup:
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

- [ ] LOGOS: preempção inteligente de P3 — suspender (não cancelar) ao detectar P1 sem VRAM:
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

- [ ] LOGOS: injetar parâmetros de eficiência por prioridade no body dos requests:
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

- [ ] LOGOS: consciência de bateria via UPower/DBus (laptop Lenovo MX150):
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

- [ ] Lançar o processo Ollama com prioridade reduzida via `nice` quando gerenciado pelo LOGOS:
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

- [ ] Lançar processos de background do Python (KOSMOS idle analysis, Mnemosyne idle indexer)
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

- [ ] Configurar cgroup para o Ollama no systemd (Linux — máquina principal e laptop):
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

### Mnemosyne — RAG, chunking e recuperação melhorados

- [ ] Mnemosyne: substituir `OllamaEmbeddings.add_documents()` por chamada direta ao `/api/embed`:
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

- [ ] Mnemosyne: chunking adaptativo em substituição ao fixed-size atual:
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

- [ ] Mnemosyne: recuperação híbrida BM25 + dense (Reciprocal Rank Fusion):
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

- [ ] Mnemosyne: reranking leve com FlashRank (CPU, sem GPU, ~10ms/query):
  **Motivo:** recuperação híbrida melhora recall; reranking melhora precisão — são complementares.
  Cross-encoder reranking adiciona +10 nDCG points sobre bi-encoders em MS MARCO (pinecone.io/
  learn/series/rag/rerankers). FlashRank usa modelos ONNX quantizados que rodam em CPU a ~10ms
  por query — viável mesmo no Windows 10 sem GPU. Não usa VRAM, não compete com o modelo de chat.
  **Implementação (`Mnemosyne/core/retriever.py`):**
  1. Adicionar `flashrank` ao `pyproject.toml`
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

- [ ] Mnemosyne: dimensões Matryoshka para reduzir tamanho do índice ChromaDB:
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

### Mnemosyne — índice vetorial e quantização futura

- [ ] Monitorar RAM consumida pelo índice ChromaDB e definir gatilho de migração para Qdrant:
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

### Tecnologias a monitorar — não implementar agora

- [ ] Speculative decoding — monitorar suporte no Ollama:
  **O que é:** um draft model pequeno (ex: SmolLM2 1.7B) gera N tokens em rascunho; o modelo
  alvo (ex: Llama 3 8B) verifica o rascunho em um único forward pass. Se correto, todos N tokens
  são aceitos. Speedup típico: 2–3× sem nenhuma perda de qualidade (verificação garante equivalência
  exata ao modelo original). Fonte: arxiv 2402.01528; arxiv 2504.06419.
  **Estado atual (2026-04):** llama.cpp suporta via `--draft-model`. Ollama não suporta nativamente.
  **Ação:** verificar trimestralmente as release notes do Ollama. Quando disponível:
  — Perfil `high` (RX 6600): draft=SmolLM2 1.7B, target=Llama 3 8B → estimativa de 2× speedup no P1
  — Não aplicar em P3 (draft model ocupa VRAM adicional; não vale para background)

- [ ] LMCache — reuso de KV cache entre turns de conversa:
  **O que é:** sistema que armazena o KV cache em múltiplos tiers (GPU VRAM → CPU DRAM → disco)
  e reutiliza entre requisições com prefixo compartilhado. Para Mnemosyne RAG com documento fixo
  como contexto, o KV cache do contexto não precisa ser recalculado a cada query.
  Speedup: NVIDIA reporta 14× TTFT mais rápido para sequências longas.
  Fonte: arxiv 2510.09665 (LMCache, 2024).
  **Estado atual (2026-04):** não integrado ao Ollama. Requer vLLM ou llama.cpp com modificações.
  **Ação:** monitorar integração no Ollama. Quando disponível, beneficia especialmente
  o Mnemosyne em sessões longas de leitura (contexto do documento = prefixo fixo = 100% cache hit).

- [ ] KVSwap — disk offload do KV cache para NVMe (MX150 2 GB VRAM):
  **O que é:** sistema projetado para dispositivos com VRAM muito limitada (como o MX150) que
  move o KV cache de conversas longas para o NVMe SSD em vez de truncar o contexto.
  Fonte: arxiv 2511.11907 (KVSwap, novembro 2024).
  **Pré-condição:** NVMe rápido (PCIe 3.0×4, ≥1500 MB/s leitura). Com SSD SATA: impraticável.
  **Ação:** verificar spec do SSD do laptop antes de avaliar. Monitorar integração no Ollama.

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