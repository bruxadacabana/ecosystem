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
- [ ] `AKASHA/config.py` — `DB_PATH` lê `akasha.data_path` do ecosystem.json se disponível
- [ ] `ecosystem_client.py` — `derive_paths()`: adicionar `data_path` à seção `akasha`
- [ ] `HUB/src-tauri/src/commands/config.rs` — `apply_sync_root()`: incluir `akasha.data_path`

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
- [ ] `Hermes/hermes.py` — renomear label do botão e da aba

#### Hermes — UX de playlist confusa: qualidade não aparece após carregar lista
- Após carregar a playlist, o usuário não sabe que precisa clicar em um vídeo
  para ver as opções de qualidade. A UI não dá feedback sobre isso.
- [ ] `Hermes/hermes.py` — adicionar instrução visual (label) após carregar playlist:
  "Selecione um vídeo acima para escolher a qualidade e baixar"
- [ ] `Hermes/hermes.py` — auto-selecionar o primeiro vídeo da lista após carregar

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
- [ ] `AKASHA/database.py` — adicionar tabela `favorite_domains (id, domain UNIQUE, label, priority_score, added_at)`
      e migration para `SCHEMA_VERSION = 12`
      Funções: `add_favorite_domain(domain, label, priority_score)`, `remove_favorite_domain(domain)`,
      `list_favorite_domains() -> list[tuple]`, `get_favorite_domains() -> set[str]`
- [ ] `AKASHA/routers/favorites.py` — novo router com rotas:
      `GET  /favorites`                       → página com lista + formulário de adição
      `POST /favorites/add`                   → adiciona domínio (extrai de URL ou aceita domínio direto)
      `DELETE /favorites/{domain}`            → remove favorito
      `POST /favorites/{domain}/to-blacklist` → move para lista negra (add_blocked + remove_favorite)
      `POST /favorites/{domain}/to-library`   → move para biblioteca (add watch-later com URL base)
- [ ] `AKASHA/templates/favorites.html` — página principal herdando `base.html`
      Subtítulo: "Domínios prioritários — resultados destes sites aparecem antes dos demais na busca."
      Formulário de adição (URL ou domínio direto + campo label opcional)
      Inclui partial `_favorites_list.html`
- [ ] `AKASHA/templates/_favorites_list.html` — partial HTMX com a lista de favoritos
      Cada item: domínio + label + data de adição + botões:
      [✕ remover] [→ lista negra] [→ biblioteca]
- [ ] `AKASHA/templates/base.html` — adicionar link "favoritos" no nav (entre "lista negra" e fim)
- [ ] `AKASHA/main.py` — registrar `favorites.router`
- [ ] Resultados de domínios favoritos sobem para P2 automaticamente na ordenação (implementar junto com o item de priorização de busca)

### Busca: priorização e segunda coluna
- [ ] Definir 3 níveis de prioridade nos resultados de busca:
  - P1: conteúdo local indexado (arquivos do ecossistema, biblioteca e sites crawleados)
  - P2: domínios favoritos/prioritários (ver seção acima)
  - P3: resultados web gerais
- [ ] Criar segunda coluna (ou painel lateral) para exibir resultados locais separados dos web

### Extração: Medium e Substack
- [ ] Pesquisar alternativas de scraping para Medium (falha mesmo em artigos gratuitos)
  — opções: trafilatura com configs avançadas, readability-lxml, puppeteer headless
  — salvar achados em `AKASHA/pesquisa.txt` antes de implementar (obrigatório per CLAUDE.md)
- [ ] Pesquisar e corrigir extração do Substack (padrão HTML diferente do Medium)

### Busca de arquivos públicos por formato
- [ ] Adicionar opção de pesquisar arquivos públicos (PDF, epub, etc.) na busca web
  — usar operadores de busca (`filetype:pdf site:...`) via engine configurada
  — exibir opção de download direto quando o arquivo for acessível publicamente

---

## PENDÊNCIAS — KOSMOS

### Bug: scraping do Medium falha
- [ ] Pesquisar alternativas ao scraping do Medium
  — criar `KOSMOS/pesquisa.txt` com achados antes de implementar (obrigatório per CLAUDE.md)
  — coordenar com solução do AKASHA (mesma causa, pode compartilhar fix via `ecosystem_scraper.py`)

### Tags geradas por IA nos cards do feed
- [ ] Exibir tags geradas pela análise de IA diretamente nos cards do feed
  — apenas tags previamente aprovadas/selecionadas pelo usuário
- [ ] Estatística de tags: exibir na view de stats as tags mais frequentes nos artigos lidos
  — gráfico de frequência de tags por período

### Pré-análise em background (requer pesquisa prévia)
- [ ] Criar `KOSMOS/pesquisa.txt` — pesquisar otimizações para o pipeline de análise (obrigatório per CLAUDE.md)
  — verificar quando e como a análise é disparada: atualmente apenas ao abrir o artigo
  — objetivo: pré-análise ao receber novos artigos (clickbait, tags, sentimento, relevância, 5Ws)
  — investigar causas da lentidão (tempo de início + tempo de conclusão)
- [ ] Após pesquisa: implementar pré-análise em background para artigos recém-recebidos
- [ ] Incluir análise dos 5Ws na pré-análise

### Estatísticas expandidas
- [ ] Ampliar gráficos de estatísticas com detalhamento dos 5Ws
  — mais granularidade, mais gráficos por período e por fonte

### Status de análise visível ao abrir artigo
- [ ] Criar indicador de status da análise ao abrir qualquer artigo
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

---

## PENDÊNCIAS — AETHER

### Bug: vault_path não atualiza após mudança no HUB
- [ ] Investigar por que o AETHER continua salvando no caminho antigo mesmo após `sync_root` ser atualizado no HUB
  — log no startup mostra: `Vault: Some("C:\\Users\\USUARIO\\Documents\\p\\My files\\backup\\notebook\\02_Areas\\escrita")`
  — verificar `AETHER/src-tauri/src/lib.rs`: se a leitura do ecosystem.json acontece antes ou depois da gravação do vault_path local
  — verificar `AETHER/src-tauri/src/ecosystem.rs`: se `read_ecosystem` está lendo o arquivo atualizado
- [ ] Adicionar opção de configurar `vault_path` dentro do próprio AETHER (sem depender exclusivamente do HUB)

---

## PENDÊNCIAS — ECOSSISTEMA / LOGOS

> Ver notas de design detalhadas em `## ONDE PARAMOS → LOGOS` neste arquivo.

### LOGOS: proxy central de LLM (integrado ao HUB)
- [ ] Decidir arquitetura final: LOGOS como parte do backend Rust do HUB vs. serviço separado
  — recomendado: integrado ao HUB (evita ter mais um processo rodando; HUB já é o maestro)
- [ ] Definir protocolo de ticket: `POST /request_ticket { app, priority, estimated_vram }` → 201 ou 429
- [ ] Implementar fila de prioridades no HUB:
  - P1 (crítica): chat interativo HUB + escrita ativa no AETHER
  - P2 (importante): buscas RAG no Mnemosyne
  - P3 (background): pré-análise KOSMOS + transcrições Hermes
- [ ] Hardware Guard: monitorar VRAM da RX 6600
  — Linux/CachyOS: `rocm-smi`
  — Windows: `pyadl` ou consultas ao driver AMD via `sysinfo` crate
  — pausar tarefas P3 quando VRAM > 85%; injetar `num_gpu`/`num_ctx` menores em P3
- [ ] Cancelamento gracioso: enviar `keep_alive: 0` ao Ollama para liberar VRAM quando P1 chegar
- [ ] Definir failsafe: comportamento dos apps quando HUB/LOGOS não estiver rodando
  — opção A: apps "travam" esperando o maestro (mais seguro)
  — opção B: modo emergência — falam direto com Ollama com configurações mínimas conservadoras

### Gerenciamento de LLM simultâneo (Mnemosyne + KOSMOS)
- [ ] Investigar comportamento atual quando os dois apps fazem chamadas simultâneas ao Ollama
  — risco: VRAM saturada → travamento no Windows 10 (8 GB RAM, GPU integrada)
- [ ] Solução de curto prazo (pré-LOGOS): semáforo/lock global no `ecosystem_client.py` para serializar chamadas

### AKASHA como broker unificado de informação
- [ ] Planejar API de "Mapa de Contexto" no AKASHA:
  — dado um termo, retornar resultados cruzados: Mnemosyne (RAG) + KOSMOS (artigos) + Hermes (transcrições) + AETHER (notas)
- [ ] HUB consumir essa API num botão de busca global cross-app

### Migração Rust/PyO3 para indexação (longo prazo)
- [ ] Avaliar substituição do indexador Python do AKASHA por módulo Rust via PyO3
  — tantivy como motor FTS (alternativa ao SQLite FTS5, muito mais rápido em escala)
  — rayon para processamento paralelo (sem GIL)
  — walkdir para traversal eficiente do filesystem
  — prioridade: baixa — reavaliar quando o volume de dados justificar

---

## PENDÊNCIAS — HUB (dashboard e painel de controle)

### Controle de recursos — extensão do LOGOS

- [ ] Painel de VRAM em tempo real + fila de prioridades visível
  — mostrar o que está rodando agora em P1/P2/P3 com estimativa de VRAM ocupada
- [ ] Botão "Silêncio" — pausa instantânea de todas as tarefas P3 para liberar GPU
  — útil ao iniciar escrita no AETHER ou chat no HUB
- [ ] Painel de gerenciamento do Ollama:
  — listar modelos instalados com tamanho e estado (carregado/descarregado)
  — ver qual app está usando qual modelo no momento
  — forçar `keep_alive: 0` para liberar VRAM manualmente
- [ ] Perfis de workflow com um clique:
  — "Modo Escrita": AETHER P1, tudo mais P3; silenciar notificações de background
  — "Modo Estudo": KOSMOS + Mnemosyne P1, AETHER P2
  — "Modo Consumo": KOSMOS P1, Hermes permitido, Mnemosyne background
  — perfil altera automaticamente as prioridades do LOGOS

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