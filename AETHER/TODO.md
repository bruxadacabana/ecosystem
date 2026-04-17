# AETHER — TODO & Roadmap

---

## PADRÃO OBRIGATÓRIO (não negociável em nenhum item)

- **Tratamento de erro com tipagem é prioridade absoluta.**
  - Rust: toda função que pode falhar retorna `Result<T, AppError>`. Nunca usar `.unwrap()` ou `.expect()` em código de produção.
  - TypeScript: `strict: true` sempre. Erros de comandos Tauri tipados com union types (`type Result<T> = { ok: true; data: T } | { ok: false; error: AppError }`).
  - Erros devem ser tratados no ponto onde ocorrem — sem silenciar, sem propagar cegamente.

- **Commit após CADA item individual do todo — não após fases ou grupos.**
  - Mensagem de commit referencia o item exato: `feat(fase-0): 0.6 CosmosLayer component`
  - Atualizar o status do item no todo ([x]) ANTES de fazer o commit.

- **Privacidade é prioridade absoluta.**
  - O AETHER não coleta, transmite nem registra nenhum dado do usuário.
  - Zero telemetria, zero analytics, zero conexões externas não solicitadas.
  - Gerenciamento de arquivos e configurações no estilo Obsidian:
    - Tudo vive na pasta raiz escolhida pelo usuário (o "vault")
    - Configurações ficam em `{pasta-raiz}/.aether/` — nunca em `~/.aether/` global
    - O usuário tem controle total sobre onde seus dados ficam
    - Cada projeto é uma pasta auto-contida e portátil

- **Manter `dev_files/dev_bible.txt` atualizado.**
  - Ao concluir qualquer item que introduza novos arquivos, módulos, commands ou padrões, atualizar o dev_bible.
  - O dev_bible descreve o estado ATUAL do projeto, não o planejado.

- **Sempre atualizar este arquivo ANTES de começar algo que não está listado aqui.**

- **Sempre atualizar o status do item ([ ] → [x]) ao concluí-lo.**

---

## Stack

- Backend: Rust (Tauri)
- Frontend: TypeScript + React + Vite
- Armazenamento: arquivos locais (JSON + Markdown/texto plano)
- Build: Tauri CLI (Windows 10 + CachyOS/Linux)

---

## IDENTIDADE VISUAL

**Nome:** AETHER
**Subtítulo:** FORJA DE MUNDOS
**Ecossistema:** OGMA · KOSMOS · MNEMOSYNE · AETHER

O AETHER segue o design system do ecossistema (definido no OGMA Design Bible):
mesma paleta sépia, mesma tipografia, mesmas regras de sombra, animações e cosmos.

**Diferencial visual do AETHER dentro do ecossistema:**
- Animação `pageFloat` — folhas de papel caem com rotação ao abrir/criar/deletar capítulos
- Efeito typewriter — texto no splash e em loading states digita caractere por caractere
- Cursor de editor como `_` piscante (sublinhado), não `|`
- CosmosLayer com labels mitológicos nas constelações (Órion, Cassiopeia, Perseu...)
- Nebulosas com pulso lento animado (8s) nos headers de projeto — o "éter" do app

---

## Design Bible v2.0 — Audit (2026-04-11)

- [x] tokens.css: modo noturno migrado para paleta "Atlas Astronômico à Meia-Noite"
- [x] tokens.css: `--sidebar-w` corrigido para 224px (era 260px)
- [x] typography.css: hierarquia tipográfica alinhada ao bible (t-body 13px, t-btn 11px, t-label 10px, t-section 9px, t-badge 10px, t-meta 9px)
- [x] components.css: `.btn` corrigido para 11px / 5px 14px
- [x] Splash.tsx: background hardcoded `rgba(26,22,16,0.45)` → `var(--paper)`

---

## FASE 0 — Design System

> Entregável: toda a fundação visual implementada. Nenhum componente de UI é construído sem isso estar pronto.

- [x] 0.1 Variáveis CSS globais (tokens do ecossistema)
  - Paleta completa: `--paper`, `--paper-dark`, `--paper-darker`, `--paper-darkest`
  - Tintas: `--ink`, `--ink-light`, `--ink-faint`, `--ink-ghost`
  - Acento: `--accent` (#b8860b dia / #D4A820 noite), `--cursor-color`
  - Funcionais: `--ribbon`, `--ribbon-light`, `--accent-green`, `--stamp`
  - Linhas: `--rule`, `--margin-line`, `--shadow`
  - Métricas: `--sidebar-w: 260px` (binder mais largo que OGMA), `--topbar-h: 44px`, `--radius: 2px`
  - Transições: `--transition: 140ms ease`

- [x] 0.2 Tipografia — carregar e configurar as três famílias
  - `--font-display`: IM Fell English (Google Fonts) — títulos, editor, itálico como regra
  - `--font-mono`: Special Elite (Google Fonts) — UI geral, botões, labels
  - `--font-code`: Courier Prime (Google Fonts) — blocos de código no editor
  - Hierarquia tipográfica completa (tamanhos, letter-spacing, pesos)
  - Regra de itálico: IM Fell English é SEMPRE itálico em títulos e conteúdo

- [x] 0.3 Animações base (herdadas do ecossistema)
  - `paperFall` — translateY(-14px) + rotate(-0.4deg) → 0, 0.22s ease-out
  - `fadeIn` — opacity 0→1, 0.15–0.25s ease
  - `slideIn` — translateX(-16px) + opacity, para sidebar/drawers
  - `blink` — opacity 1→0→1, 1.2s (loading dots) / 0.6s (editor cursor)
  - `toastIn` — translateY(6px) + opacity, 180ms ease-out

- [x] 0.4 Animações exclusivas do AETHER
  - `pageFloat` — folha retangular cai com rotação suave (±3deg) e translação diagonal
    - Variante entrada: cai de cima com rotação leve, pousa
    - Variante saída (deletar): voa para canto superior direito e desaparece
  - `typewriterReveal` — texto revela caractere por caractere com delay mecânico (30ms/char)
    - Usado no splash e em loading states
  - `etherPulse` — opacity 0.4→0.65→0.4, 8s ease-in-out infinite (nebulosas dos headers)

- [x] 0.5 Textura de papel
  - `body::after` com SVG `feTurbulence` (baseFrequency: 0.65, numOctaves: 4)
  - Opacity: 30%, pointer-events: none, z-index: 0
  - Invisível no modo noturno (intencional)

- [x] 0.6 Componente `<CosmosLayer>`
  - SVG procedural determinístico (seed baseado no ID do projeto)
  - Elementos: nebulosas, estrelas (10 pontas), constelações, cometa, lua crescente
  - **Diferencial AETHER:** labels mitológicos nas constelações (Special Elite, 7px, opacity: 0.35)
  - **Diferencial AETHER:** nebulosas com `etherPulse` animado
  - Densidades: `low` (headers de capítulo), `medium` (headers de livro), `high` (splash, tela inicial)
  - Props: `seed`, `density`, `animated` (boolean — desativa pulso se false)

- [x] 0.7 Linha vermelha de margem
  - `sidebar::before` — 1px vertical em left: 48px (ajustado para binder)
  - Cor: `--margin-line`
  - Replicada no splash em mesma posição

- [x] 0.8 Sistema de sombra flat (sem blur)
  - Botão: `2px 2px 0 var(--rule)`
  - Botão primary: `2px 2px 0 var(--stamp)`
  - Card: `3px 3px 0 var(--paper-darker)`
  - Modal: `6px 6px 0 var(--ink-ghost)`
  - Menu popup: `3px 3px 0 var(--rule)`
  - `:active` em botões e cards: sombra some + `translate(1px, 1px)`

- [x] 0.9 Scrollbar vintage
  - Width: 6px, border-radius: 2px
  - Track: `--paper-dark`, thumb: `--rule`, hover: `--stamp`

- [x] 0.10 Cursor dourado e cursor de editor
  - `caret-color: var(--accent)` em todos os inputs e textareas
  - No editor de capítulo: cursor customizado como `_` piscante (via CSS/JS)

- [x] 0.11 Seleção de texto âmbar
  - `::selection { background: rgba(184,134,11,0.25); }`
  - Editor modo escuro: `rgba(212,168,32,0.2)`

- [x] 0.12 Sistema de temas (dia / noite)
  - Toggle via classe `dark` no `<html>`
  - Persiste em localStorage: `aether_theme`
  - Sem flash de tema errado no carregamento (aplicar antes do render)

- [x] 0.13 Sistema de toasts / notificações
  - Tipos: `success`, `error`, `warning`, `info`
  - Posição: fixed, bottom: 24px, right: 24px
  - Auto-dismiss: error=7s, success=3s, warning=5s, info=4s
  - Cores dentro da paleta sépia (sem branco puro, sem preto puro)
  - Animação: `toastIn`

- [x] 0.14 Splash screen
  - Overlay sépia (rgba(26,22,16,0.85)) com backdrop blur 2px
  - Card 520×340px, border-radius: 2px, sombra flat 8px
  - `<CosmosLayer density="high" animated={true}>`
  - Linha de margem vermelha (left: 48px)
  - "AETHER" em IM Fell English 68px itálico
  - "FORJA DE MUNDOS" em Special Elite 9px uppercase letter-spacing: 0.22em
  - Texto de status com `typewriterReveal`: "Iniciando AETHER..." → "Abrindo projetos..." → "Pronto."
  - Dots de loading: "· · ·" com `blink` 1.2s
  - Versão no canto inferior direito (9px)
  - Fade out após "Pronto." com delay 400ms

- [x] 0.15 Componentes base de UI
  - Botões: `.btn`, `.btn-primary`, `.btn-accent`, `.btn-danger`, `.btn-ghost`, `.btn-sm`, `.btn-icon`
  - Inputs e labels (IM Fell no corpo, Special Elite nos labels)
  - Cards com `paperFall` e sombra flat
  - Modais com overlay sépia e `paperFall`
  - Badges / tags (border-radius: 20px para pills)

---

## FASE 1 — Fundação (projeto abrível e editável)

> Entregável: abrir o AETHER, criar um projeto, criar capítulos e escrever texto. Nada mais — mas isso funciona.

- [x] 1.1 Scaffold do projeto Tauri + React + TypeScript
  - Vite como bundler, `strict: true` no tsconfig
  - Estrutura de pastas: `src-tauri/` (Rust), `src/` (React)

- [x] 1.2 Definir e implementar estrutura de dados em disco
  - Modelo Obsidian: usuário escolhe uma pasta raiz ("vault") na primeira abertura
  - Dois níveis de armazenamento:
    1. **AppData do sistema** (`~/.local/share/aether/` no Linux, `%AppData%\aether\` no Windows)
       - `app.json` — caminho do último vault aberto (apenas isso)
       - Gerenciado pelo Tauri via `tauri::api::path::app_data_dir`
    2. **Dentro do vault** (portátil, controlado pelo usuário)
       - `{vault}/.aether/config.json` — tema, fonte, estado da UI, etc.
       - `{vault}/.aether/` — outros dados internos do app (snapshots, cache, etc.)
       - `{vault}/{projeto}/project.json` — metadados do projeto
       - `{vault}/{projeto}/{livro}/book.json` — metadados do livro
       - `{vault}/{projeto}/{livro}/{capitulo}.md` — conteúdo dos capítulos
  - Tipos Rust: `AppState`, `VaultConfig`, `Project`, `Book`, `Chapter` com `serde` + `serde_json`
  - `AppError` enum cobrindo todos os erros de I/O

- [x] 1.3 Comandos Tauri: gerenciamento de projetos
  - `list_projects() -> Result<Vec<ProjectMeta>, AppError>`
  - `create_project(name) -> Result<ProjectMeta, AppError>`
  - `open_project(id) -> Result<Project, AppError>`
  - `delete_project(id) -> Result<(), AppError>`

- [x] 1.4 Comandos Tauri: livros e capítulos
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

- [x] 1.6 Tela inicial — lista de projetos
  - Criar novo projeto
  - Abrir projeto existente
  - Remover projeto

- [x] 1.7 Layout principal do projeto
  - Painel binder lateral: árvore Livros > Capítulos
  - Área central: editor de texto
  - Criar/renomear/deletar livros e capítulos pelo binder
  - Reordenar capítulos via drag & drop

- [x] 1.8 Editor de texto WYSIWYG com TipTap
  - Biblioteca: TipTap (ProseMirror) — renderização em tempo real
  - Sem "modo leitura": o texto é SEMPRE renderizado, nunca mostra símbolos Markdown
  - Digitar `**texto**` → imediatamente vira negrito; `_texto_` → itálico; etc.
  - Parágrafos indentados (text-indent na primeira linha, estilo livro impresso)
  - Tipografia: IM Fell English itálico, 16px, line-height 1.75, coluna centralizada
  - Cursor estilo máquina de escrever: `_` piscante via CSS (substituir cursor padrão `|`)
  - Auto-save com debounce 500ms após parar de digitar
  - Indicador de status "Salvando..." / "Salvo" no rodapé do editor
  - Exporta/importa como Markdown puro (compatível com os .md do vault)

---

## FASE 1.5 — Itens pendentes identificados em uso

> Itens que surgiram durante os testes da Fase 1. Devem ser feitos antes da Fase 2.

- [x] 1.9 Tipos de projeto: livro único vs série
  - Ao criar projeto, perguntar: "Livro único" ou "Série"
  - **Livro único**: nome do projeto = nome do livro; livro criado automaticamente; binder oculta a camada "livro" e mostra só capítulos
  - **Série**: nome da série separado do nome dos livros; binder mostra árvore Série > Livros > Capítulos normalmente
  - Armazenar `project_type: "single" | "series"` em project.json
  - Ajustar Binder para renderizar diferente conforme o tipo

- [x] 1.10 Modal de criação de projeto com metadados
  - Substituir o modal simples atual por um wizard/form mais completo
  - Campos: tipo (único/série), título, subtítulo opcional, descrição/sinopse
  - Metadados de livro: gênero, público-alvo, idioma, tags livres
  - Metadados de worldbuilding: sistema de magia (sim/não), nível tecnológico, inspirações
  - Todos os campos opcionais exceto título e tipo
  - Salvar em project.json

- [x] 1.11 Dashboard do projeto
  - Tela inicial ao abrir um projeto (antes de selecionar capítulo)
  - CosmosLayer de fundo com seed do projeto
  - Nome, subtítulo, descrição do projeto
  - Estatísticas: total de palavras, total de capítulos, data de criação
  - Widgets expansíveis no futuro (metas, personagens, etc.)

- [x] 1.12 Sistema de logs em arquivo
  - Logs salvos dentro do vault em `{vault}/.aether/logs/aether-YYYY-MM-DD.log`
  - Rotação diária; manter últimos 7 dias
  - Nível INFO em produção, DEBUG em dev
  - Registrar: abertura/fechamento do vault, erros, saves, operações de CRUD
  - Implementar em Rust via tauri-plugin-log com appender de arquivo

---

## FASE 2 — Experiência de escrita

> Entregável: escrever com conforto. Foco, tipografia, estatísticas básicas.

- [x] 2.1 Temas: claro, escuro, sépia
- [x] 2.2 Tipografia customizável (fonte, tamanho, espaçamento, largura da coluna de texto)
- [x] 2.3 Modo foco / distraction-free (esconde binder e UI, só o texto)
- [x] 2.4 Modo typewriter (cursor sempre centralizado verticalmente)
- [x] 2.5 Tela cheia (F11)
- [x] 2.6 Contagem de palavras e caracteres em tempo real
- [x] 2.7 Status por capítulo (Rascunho / Revisão / Final)
- [x] 2.8 Sinopse por capítulo (campo no binder ou painel lateral)
- [x] 2.9 Localizar e substituir no capítulo atual

---

## FASE 3 — Organização avançada

> Entregável: visões alternativas da estrutura do projeto.

- [x] 3.1 Vista corkboard (cartões de capítulo com título + sinopse)
- [x] 3.2 Vista outline (lista com status, sinopse e contagem de palavras)
- [x] 3.3 Lixeira — capítulos deletados ficam recuperáveis
- [x] 3.4 Scratchpad por capítulo (bloco de notas lateral)
- [x] 3.5 Modo split: editor + scratchpad/notas lado a lado

---

## FASE 4 — Personagens & Worldbuilding

> Entregável: base de lore do projeto, separada da escrita mas sempre acessível.

- [x] 4.1 Fichas de personagem com campos customizáveis
- [x] 4.2 Relacionamentos entre personagens (mapa/grafo simples)
- [x] 4.3 Notas de worldbuilding por categoria (locais, facções, etc.)
- [x] 4.4 Linha do tempo de eventos
- [x] 4.5 Anexar imagens a personagens e locais
- [x] 4.6 Tags — cruzar personagens/locais com capítulos

---

## FASE 5 — Metas & Histórico

> Entregável: acompanhar progresso e proteger o trabalho.

- [x] 5.1 Meta de palavras por capítulo e por livro
- [x] 5.2 Meta de sessão de escrita com timer
- [x] 5.3 Streak diário de escrita
- [x] 5.4 Painel de estatísticas (palavras totais, ritmo, sessões)
- [x] 5.5 Snapshots de capítulo (histórico de versões manual + automático)
- [x] 5.6 Comentários/anotações inline no texto

---

## FASE 6 — Exportação

> Entregável: levar o texto para fora do AETHER.

- [ ] 6.1 Export por capítulo individual
- [ ] 6.2 Export por livro (capítulos concatenados)
- [ ] 6.3 Export do projeto completo
- [ ] 6.4 Formatos: Markdown, texto plano, DOCX, PDF
- [ ] 6.5 Formato EPUB
- [ ] 6.6 Configurações de export (incluir/excluir sinopses, metadados, notas)

---

## FASE 7 — Polimento & Extras

> Entregável: produto refinado.

- [ ] 7.0 Botão de excluir visível para projetos, livros e capítulos
      — usuária não encontrou a ação na UI; verificar se `delete_book` está implementado
        (1.4 lista `delete_chapter` mas não `delete_book`); tornar todos os deletes
        descobertos: botão visível no hover ou menu de contexto claro
- [ ] 7.1 Atalhos de teclado customizáveis
- [ ] 7.2 Gerador de nomes
- [ ] 7.3 Projetos recentes na tela inicial com preview
- [ ] 7.4 Onboarding (tela de boas-vindas para primeiro uso)
- [ ] 7.5 Configurações globais (tema padrão, pasta de dados, fonte padrão)
- [ ] 7.6 Build de distribuição — Windows installer + pacote Linux (AppImage/deb)

---

## BACKLOG (futuro, fora do escopo atual)

- Sync opcional com cloud (Google Drive, Dropbox, ou próprio)
- Colaboração em tempo real
- Plugin/extensão system
- Integração com ferramentas de revisão gramatical
- Versão mobile (leitura + notas)
