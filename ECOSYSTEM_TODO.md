# ECOSYSTEM — Roadmap de Integração
# OGMA · KOSMOS · AETHER · MNEMOSYNE · HUB

Objetivo: interligar os apps existentes e criar um app hub
unificado que rode no Android (APK via Tauri 2).

Desenvolvimento em fases progressivas — cada fase entrega algo
utilizável antes de avançar para a próxima.

---

## PRINCÍPIOS INEGOCIÁVEIS

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
- [ ] Documentar o contrato: quem escreve cada campo, quando, formato
- [ ] Instalar e configurar Syncthing entre PC e tablet
      - Definir quais pastas sincronizar (vault AETHER + archive KOSMOS)
      - Testar round-trip: criar arquivo no PC → aparece no Android

---

## FASE 1 — Interligação dos apps existentes
> Aproveita o que já existe. Mudanças cirúrgicas, sem novo app.

### 1.1 — OGMA → AETHER (criar projeto criativo)
- [ ] Adicionar coluna `aether_project_id TEXT` na tabela `projects`
      do OGMA (schema v2, arquivo `src/main/database.ts`)
- [ ] OGMA lê vault path de `.ecosystem.json` na criação de projeto
- [ ] Ao criar projeto com `project_type = 'creative'`, OGMA escreve
      no vault AETHER:
      - `{vault}/{uuid}/project.json`  (formato Project do AETHER)
      - `{vault}/{uuid}/{book_uuid}/book.json`  (livro padrão vazio)
- [ ] Salvar `aether_project_id` no banco do OGMA para manter o vínculo
- [ ] Botão "Abrir no AETHER" em projetos criativos do OGMA

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

### 1.4 — Hermes → archive do KOSMOS (transcrições)
- [ ] Adicionar checkbox "Salvar também no arquivo do KOSMOS" na aba Transcrever do Hermes
      Lê `kosmos.archive_path` do ecosystem; desabilitado se vazio
- [ ] Salvar transcrição como `.md` em `archive/hermes/` com frontmatter KOSMOS-compatível
- [ ] Formato: mesmo padrão Markdown do `archive_manager.py` do KOSMOS

---

## FASE 2 — App Hub (desktop/web)
> Novo programa. Roda no PC como web app antes de ir para Android.
> Stack: Tauri 2 + React + TypeScript (mesma do AETHER).

### 2.1 — Estrutura base do hub
- [ ] Criar projeto Tauri 2 em `program files/HUB/`
- [ ] Importar design system dos apps existentes:
      - `tokens.css`, `animations.css`, `typography.css`
      - Fontes: IM Fell English · Special Elite · Courier Prime
- [ ] Roteador de módulos (Escrita / Projetos / Leituras / Perguntas)
- [ ] Tela de configuração inicial: lê `.ecosystem.json`, valida caminhos
- [ ] CosmosLayer compartilhado (copiar do AETHER ou do OGMA)

### 2.2 — Módulo Escrita (compatível com AETHER)
- [ ] Listar projetos do vault AETHER (lê `project.json` de cada pasta)
- [ ] Navegar livros e capítulos (lê `book.json`)
- [ ] Abrir e editar capítulo (lê/salva `{cap_id}.md`)
      - Editor TipTap reutilizado do AETHER
      - Auto-save com debounce
- [ ] Criar projeto, livro e capítulo novos (compatível com o formato AETHER)
- [ ] Contagem de palavras em tempo real

### 2.3 — Módulo Projetos (compatível com OGMA)
- [ ] Leitura do `ogma.db` via @libsql/client ou better-sqlite3
- [ ] Listar projetos e páginas (somente leitura inicialmente)
- [ ] Captura rápida: adicionar página/nota a um projeto existente
- [ ] Visualizar corpo da página (Editor.js JSON → renderização simples)

### 2.4 — Módulo Leituras (compatível com KOSMOS)
- [ ] Listar arquivos `.md` de `kosmos/data/archive/`
- [ ] Renderizar artigo (Markdown → HTML)
- [ ] Marcar como lido (arquivo de estado `hub_read_state.json` no archive)

### 2.5 — Módulo Perguntas (compatível com Mnemosyne)
- [ ] Interface de chat simples
- [ ] Conectar ao Ollama via HTTP (`localhost:11434`)
- [ ] Usar ChromaDB do Mnemosyne como fonte (ou reindexar localmente)
- [ ] Fallback quando Ollama não está rodando

---

## FASE 3 — Android (APK)
> Hub roda no tablet. Requer Fase 2 completa.

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

- [ ] Quick capture: widget ou atalho Android para adicionar nota rápida
      ao OGMA sem abrir o app completo
- [ ] Streak AETHER visível no hub (ler `sessions.json` do vault)
- [ ] Notificação Android: novos artigos no archive do KOSMOS
- [ ] Busca cross-módulo: pesquisar em escritos + projetos + artigos
- [ ] stellar-downloader + transcriber integrados:
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

  Fase 0: ✅ Fundação concluída (ecosystem_client.py, ecosystem.ts, ecosystem.rs, ecosystem.json)
  Fase 1: 🔄 Em progresso — 1.3 AETHER-side concluída; 1.1, 1.2, 1.4 pendentes
  Fase 2: não iniciada
  Fase 3: não iniciada
  Fase 4: não iniciada
