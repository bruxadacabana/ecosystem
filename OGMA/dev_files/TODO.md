# OGMA — TODO

> Atualizado: 2026-04-03

---

## ⚠ Padrões Obrigatórios

### Tratamento de Erros — EXTREMA IMPORTÂNCIA

É de extrema importância manter tipagem completa em **cada etapa do desenvolvimento**:

- Todo código que chama `db()` no renderer **deve** usar `fromIpc<T>` de `src/renderer/types/errors.ts`
- Nunca usar `fromIpc<any>` — sempre tipar o genérico com o tipo concreto esperado
- Nunca usar `.then((r: any) => ...)` sem encapsulamento tipado
- Usar `async/await` em vez de `.then()` encadeado em `ResultAsync` dentro de `Promise.all`
- `pushToast` via `useAppStore()` é o canal de feedback de erros para o utilizador
- Todo novo código deve passar em `tsc --noEmit` sem erros nos ficheiros da aplicação

### TODO.md
Sempre manter este arquivo atualizado. Toda funcionalidade ou mudança pedida pelo utilizador deve ser anotada aqui (marcar com `[x]` quando concluída).

### Git
Fazer `git commit` após cada funcionalidade ou mudança implementada, com mensagem descritiva do que foi feito.

---

## Bugs conhecidos / Prioridade imediata

- [x] Dashboard reseta ao trocar de aba (DashboardView desmontava — corrigido: sempre montado com display:none)
- [x] Cor de acento não aplicada ao CSS (accent_color guardado mas não aplicado à variável --accent — corrigido: useEffect em App.tsx)
- [x] Atividades do Planner não aparecem no Calendário Global nem no widget de Agenda (UNION planned_tasks nas queries events:listForMonth e events:listUpcoming)
- [x] Algoritmo de agendamento: prioridade (urgent/high/medium/low) + skip weekends + edição manual de planned_hours por bloco
- [x] Lembretes: movidos para dentro do Planner (RemindersSection) — prioridade, opções de antecedência, página obrigatória
- [x] Planejamento de revisão com repetição espaçada: 1→3→7→14→30 dias, ativável por tarefa
- [x] Aba TEMPO removida — Timer/Pomodoro integrado no Planner: botão ▶ por tarefa, auto-log no bloco, registo manual (duração+início ou início+fim), página obrigatória
- [x] Bug: ao criar atividade através do Planner, não aparece a opção de conectar a atividade a uma página, apenas a um projeto
- [x] Dashboard não recarregava ao voltar ao separador (corrigido: prop `isActive` nos widgets)
- [x] Schema do DB não era recriado no modo embedded replica após apagar o ficheiro local (corrigido: padrão `_initPromise` + sync em background)
- [x] Botão de sincronização manual nas Configurações (fix: chamada direta a `db().sync.now()`, sem `fromIpc`)
- [x] Tamanho de fonte nas Configurações não alterava nada (fix: CSS usa `rem` com base em `html { font-size }`)
- [x] Barra lateral recolhível (modo só-ícones, toggle ◀▶, persistência em localStorage)
- [x] Acrescentar o botão "reagendar" no planner global ao invés de só nos locais dos projetos
- [x] Verificar se os botões "reagendar" também reagendam tarefas pendentes atrasadas (que devem ser trtadas como urgência máxima)
- [x] separar limite de horas disponíveis para marcar automaticamente as atividades do planner por dia ao invés de continuar com o mesmo limite de horas para todos os dias
- [x] Mudar o planner para poder mudar a visualização da parte direita — tabs AGENDA e TAREFAS ABERTAS implementadas; Pomodoro sempre visível na coluna esquerda
- [x] Campo de prioridade no formulário de criação de tarefa do GlobalPlanner
- [x] **Bug:** filtro por data via clique no mini-calendário do GlobalPlanner — corrigido: `activeFocus` removido das deps do `useCallback`, headers da agenda uniformizados
- [x] **Bug:** work_blocks do Planner não apareciam na aba Agenda do GlobalCalendarView — corrigido: adicionado UNION com `work_blocks` em `events:listUpcoming`

---

## Fase Extra — Prioridade Alta

Funcionalidades em falta ou incompletas nas áreas já iniciadas (Biblioteca, Editor, Produtividade).

- [x] Leituras → Recurso: selecionar livro existente ao registar leitura
- [x] Sessões de leitura: registar sessões individuais com data e páginas lidas
- [x] Abas de leitura: Geral, Notas, Citações, Vínculos (detalhe de uma leitura)
- [x] Recursos: vista em galeria + detalhe com metadados + conexões a páginas
- [x] `reading_links`: vincular leitura ↔ página do OGMA
- [x] Progresso de leitura por páginas ou porcentagem (escolha ao cadastrar)
- [x] Meta de leitura anual — IPC `reading:goals:*` + `ReadingGoalBanner` na Biblioteca: barra de progresso, contador lidos/meta, inline edit; widget Dashboard pendente
- [ ] Histórico de versões de página — tabela `page_versions` já existe no schema; falta IPC + UI no PageView
- [x] Backlinks: mostrar no PageView as páginas que referenciam a atual
- [x] **Pomodoro / timer independente com histórico por página** — aba "Tempo" adicionada ao ProjectDashboardView: `StudyTimerTab` com relógio SVG animado, Pomodoro 25/5min, registo manual de sessões (página, duração, data, notas, tags), histórico do projeto

---

## Fase 4 — Kanban

- [x] Drag & drop entre colunas (muda `prop_value` do Status)
- [x] Filtros e ordenação na view

---

## Fase 5 — Table / List

- [x] Edição inline de propriedades nas views (TableView)
- [x] Filtros, ordenação e busca nas views (TableView: busca + filtro por select; ListView: busca + sort por título/data)

---

## Fase 6 — Módulo Académico Completo

- [x] `colorUtils.ts` — cores HSL automáticas por disciplina (disciplineColor + disciplineColorAlpha)
- [x] Gerador de código `PREFIX###` automático (IPC pages:create, propriedade built-in `codigo`) — algoritmo melhorado com initials por palavras significativas + extração de numerais
- [x] Pré-requisitos entre páginas com detecção de ciclo (IPC + UI no PageView para projetos académicos)
- [x] Campo `institution` no nível do projeto (coluna na tabela `projects`, visível em NewProjectModal e EditProjectModal apenas para tipo `academic`) — "Professor" permanece propriedade da página
- [x] Modal de nova página expandido: cor de capa, página pai, propriedades dinâmicas, tags, multi-select
- [x] IconPicker: navegação ◀▶ entre categorias, scroll, novas sugestões por palavra-chave
- ~~Script de migração do StudyFlow~~ (cancelado)
- [x] Tipo de projeto **"Hobbies"** — `'hobby'` adicionado ao `ProjectType` com subcategorias, propriedades padrão (Status, Tags, Data Início, Notas) e views (Lista, Tabela)
- [x] **Ideias Futuras** — `'idea'` adicionado ao `ProjectType`; widget "Ideias Futuras" no Dashboard lista projetos deste tipo com status e descrição
- [x] Planner global: algoritmo de agendamento considera prioridade + prazo + limite de horas/dia; reagendamento disponível globalmente; agenda por dia implementada
- [x] Organização progressiva para projetos acadêmicos **Autodidata**: propriedade `ciclo` (Ciclo 1–5, expansível pelo utilizador) em vez de `trimestre`; `AcademicProgressView` e `CalendarView` adaptam agrupamento e labels automaticamente conforme subcategoria

---

## Fase 8 — Calendário, Lembretes e Analytics

- [x] Lembretes via Notification API do Electron (scheduler.ts com polling de 60s)
- [x] Actividades académicas: tipos Prova, Trabalho, Seminário, Defesa, Prazo, Reunião, Outro
- [x] PageEventsPanel — criar actividades/lembretes dentro de cada página
- [x] UpcomingEventsPanel — painel de próximas actividades no dashboard do projecto
- [x] GlobalCalendarView — eventos no grid + aba Agenda (próximos 60 dias) + aba Lembretes

---

## Fase 9 — Dashboard Global

- [x] Fase da lua (cálculo astronómico) — getMoonPhase() com referência J2000 + ciclo 29.53 dias
- [x] Drag-and-drop dos widgets + persistência da ordem (localStorage `ogma_dashboard_order`)
- [x] Roda do Ano (WheelOfYearWidget) — SVG com 8 Sabás, setores sazonais, marcador do dia atual, próximo Sabá destacado
- [x] Três tamanhos por widget (SM/MD/LG) com layouts adaptativos + persistência (localStorage `ogma_widget_sizes`)
- [x] LG: ocupa 2 colunas × 2 linhas na grid (permite 2 widgets SM empilhados ao lado)
- [x] Localização do utilizador (cidade, estado, país, lat/lon, hemisfério, timezone) via geocoding Open-Meteo → Settings → Localização
- [x] Widget de Previsão do Tempo (WeatherWidget) — Open-Meteo forecast, layouts por tamanho, WMO codes em PT
- [x] Roda do Ano com hemisfério real e datas astronómicas (Meeus) por localização configurada

### Gestão de widgets

- [x] Remover widget do dashboard (botão × no hover)
- [x] Adicionar widget oculto de volta (card "+ Adicionar widget" no final do grid)
- [x] Persistência de widgets ocultos (`localStorage ogma_hidden_widgets`)

---

## Fase 9b — Planejador Acadêmico (Planner)

Agendamento de tarefas com horas estimadas, replanejamento automático e vínculo com páginas do projeto.

- [x] Migrations: tabelas `planned_tasks` e `work_blocks`
- [x] IPC handlers: CRUD de `planned_tasks` + algoritmo de scheduling (EDF, capacidade diária global, replanejamento de missed blocks)
- [x] Aba "Planner" no ProjectView — lista de tarefas planejáveis + calendário semanal com blocos de horas + criar/vincular página ao criar tarefa
- [x] Widget "Plano do Dia" no Dashboard — consolidado de todos os projetos para hoje, com checkbox de sessão concluída
- [x] Campo "Capacidade diária (horas)" em Settings (padrão 4h)
- [x] Criar uma aba para o planner global no menu lateral (GlobalPlannerView: fundo pontilhado + cosmos, estética bullet journal, mini calendário, urgente/hoje à esquerda, log completo com agrupamento/criação/detalhe inline à direita)

---

## Fase 10 - Sincronização entre dispositivos — Turso / libsql

Migração de `better-sqlite3-multiple-ciphers` → `@libsql/client` com embedded replica.
A BD fica local (leituras offline) e sincroniza com Turso Cloud ao escrever/arrancar.

- [x] `data/settings.json` — preferências do utilizador separadas do banco (`electron-store` substituído por JSON direto via `src/main/settings.ts`)
- [x] Migrar `localStorage` (tema, localização, dashboard_order, widget_sizes, hidden_widgets) → `data/settings.json` via IPC `appSettings:*`
- ~~rclone + Proton Drive~~ — removido (v0.1); incompatibilidade com a API do Proton Drive (erro 422 persistente ao actualizar ficheiros).

### Passo 1 — Conta Turso e credenciais

- [x] Criar conta em turso.tech (plano free: 500 DBs, 1 GB)
- [x] Instalar CLI Turso: `curl -sSfL https://get.tur.so/install.sh | bash
- [x] `turso auth login`
- [x] `turso db create ogma` — criar a BD remota
- [x] `turso db show ogma` — copiar URL (`libsql://ogma-....turso.io`)
- [x] `turso db tokens create ogma` — gerar auth token
- [x] Guardar em `data/.env` (já no `.gitignore`):
  ```
  TURSO_URL=libsql://ogma-....turso.io
  TURSO_TOKEN=ey...
  ```

### Passo 2 — Instalar dependências ✅

- [x] `npm install @libsql/client`
- [x] `npm uninstall better-sqlite3-multiple-ciphers`
- [x] Scripts `postinstall` e `rebuild` removidos do package.json
- [x] `@libsql/client` funciona sem compilação (N-API — sem problema GCC 15)

### Passo 3 — Reescrever `src/main/database.ts` ✅

- [x] Substituir import: `import { createClient, Client } from '@libsql/client'`
- [x] `getClient(): Promise<Client>` — lazy init async; lê TURSO_URL/TURSO_TOKEN de process.env
- [x] `dbGet/dbAll/dbRun` → async com mesma assinatura variádica
- [x] `initSchema()` → async; `createTables()` com loop de `client.execute()`; migrações incrementais com try/catch
- [x] `seedDefaults()` → async
- [x] `closeClient()` + `syncClient()` exportados
- [x] PRAGMA foreign_keys via `client.execute()`

### Passo 4 — Atualizar `src/main/ipc.ts` e ficheiros dependentes ✅

- [x] Wrapper `api()` → async handler
- [x] `seedProjectProperties()` + `seedProjectViews()` → async
- [x] `scheduleTasks()`, `updateTaskStatus()`, `getDailyCapacity()` → async
- [x] `ftsUpsert()` → async
- [x] Todos os handlers com `await` em dbGet/dbAll/dbRun
- [x] `db.transaction()` / `db.prepare()` → `client.batch()` ou awaits sequenciais
- [x] `scheduler.ts` → `checkAndFire()` async
- [x] `main.ts` → `await getClient()`, load dotenv de `data/.env`, sync no before-quit
- [x] IPC `db:sync` adicionado para sync manual do renderer
- [x] `tsc --noEmit` sem erros em `src/main/`

### Passo 5 — Verificar compatibilidade ✅

- [x] `PRAGMA user_version` — não usado (migração incremental via `runIncrementalMigrations`); compatível com Turso
- [x] FTS5 (`search_index`) — Turso suporta; criação separada do batch DDL com try/catch; queries MATCH funcionais
- [x] Transações — nenhum `db.transaction()` restante; substituição por awaits sequenciais completa
- [x] `tsc --noEmit` sem erros — corrigidos: `skipLibCheck` no tsconfig renderer, declarações de módulo para plugins EditorJS sem tipos, `vite-env.d.ts` para `import.meta.env`, import inexistente `appSettings` removido de SettingsView

### Passo 6 — Migrar dados existentes ✅

- [x] BD exportada para `data/ogma_dump.sql` (backup em `data/ogma_backup.db`)
- [x] Dados limpos (sem FTS5/PRAGMAs) importados para Turso: `data/ogma_inserts.sql`
- [x] Sync testado: workspace "Jen" + 2 resources confirmados no remoto e local

### Passo 7 — Sync no ciclo de vida do app

- [x] `main.ts` — sync inicial em background após init do schema (não bloqueia o arranque)
- [x] `main.ts` — sync no evento `app.on('before-quit')`
- [x] IPC `db:sync` para sync manual a partir do renderer (botão nas Settings)

### Passo 8 — Testes e validação ✅

- [x] Testar CRUD básico (criar/editar/apagar projeto, página, leitura) — 23/23 testes passaram via `data/test_passo8.mjs`
- [x] Testar funcionamento offline — embedded replica lê do disco local; `client.sync()` falha silenciosamente sem rede (offline-first por design)
- [ ] Testar sync entre dois dispositivos — requer hardware; `client.sync()` confirmado funcional neste dispositivo

## Ícone da aplicação

- [x] Ícone temporário criado (`assets/ogma.ico`) — design: fundo castanho escuro, símbolo ✦ dourado, estrelas cosmos, texto "OGMA"
- [x] Ícone aplicado ao `BrowserWindow` (`icon: ICON_PATH` em `src/main/main.ts`)
- [x] Ícone configurado no `electron-builder` (`build.win.icon`)
- [x] Atalhos Windows atualizados com `IconLocation` para o `.ico`

---

## Fase 11 — Polimento

- [x] Ícone do app (temporário) — ver secção "Ícone da aplicação" acima
- [x] Decoração cósmica completa, animações

---

## Fase 12 — Analytics (todos vem desativados por padrão e são ativados nas configurações: vai abrir uma janela centralizada com um checkbox para marcar os que deseja ativar)

- [x] Pico de Produtividade: "Você é uma criatura da [Manhã/Noite]", baseaddefinitivoo no horário em que a maioria das páginas é editada.
- [x] Taxa de Absorção Literária: Quantos recursos (livros/artigos) foram concluídos no mês vs. adicionados à lista de leitura.
- [ ] Páginas por "Área do Conhecimento": Um gráfico de pizza ou barras mostrando se você está dedicando mais tempo a Letras, Cibersegurança ou Hobbies Manuais.
- [x] Produtividade por Fase Lunar: Uma estatística curiosa mostrando em qual fase da lua você costuma concluir mais tarefas (ex: "Sua produtividade aumenta 20% na Lua Crescente").
- [ ] Progresso da Estação: Quanto falta para o próximo Sabá (já existe na Roda, mas pode ser um valor percentual de "Preparação para o Equinócio/Solstício").
- [x] Horas de Voo (Deep Work): Total de horas logadas nos work_blocks do Planner.
- [x] Velocidade de Leitura: Média de páginas lidas por dia nos últimos 7 dias.
- [x] Radar de Polímata (Equilíbrio de Áreas): Já que você tem diferentes project_type (Acadêmico, Escrita, Cibersegurança, etc.), essa métrica mostra para onde sua energia está indo. **O que medir:** Porcentagem de tarefas concluídas ou tempo logado por categoria de projeto. **Estética**: Um gráfico de radar ou uma lista simples: "Este mês, sua mente esteve 40% em Letras, 30% em Cibersegurança e 30% em Hobbies" **Objetivo**: Garantir que nenhum pilar seja esquecido.

### Por projeto / académico
- [ ] **Horas por projecto** — gráfico de barras com `work_blocks` agrupados por projecto
- [ ] **Taxa de conclusão do Planner** — tarefas concluídas vs. atrasadas por mês
- [ ] **Distribuição de tipos de tarefa** — pizza de `task_type` (aula/prova/atividade…)
- [ ] **Progresso por prazo** — linha do tempo de tarefas vs. deadline

### Leitura
- [ ] **Ritmo de leitura** — páginas/dia ao longo do tempo (`reading_sessions`)
- [ ] **Livros concluídos por mês** — gráfico de barras
- [ ] **Progresso da meta anual** — gauge + projecção de conclusão

### Conhecimento
- [ ] **Páginas mais conectadas** — top backlinks (hubs de conhecimento)
- [ ] **Tags mais usadas** — evolução temporal
- [x] **Actividade por dia da semana** — padrão de produtividade

---

## Fase 13 - Widgets

#### IDEIAS
- [ ] **Terminal de Cibersegurança (Status de Lab)** - O que faz: Um widget com estética de terminal (letras verdes/amber sobre fundo escuro) mostrando o progresso em certificações ou máquinas de lab. Por que é legal: Cria um contraste visual interessante com o resto do dashboard de "papel envelhecido". É o seu lado tecnológico pulsando no meio do cosmos.
- [ ] **Widget de "Rituais de Estação** - **O que faz**: Cruzando a fase da lua e a Roda do Ano, ele sugere uma atividade de "autocuidado polímata". **Exemplos**: "Lua Minguante no Outono: Momento de revisar e descartar notas obsoletas (Pilar Organizada)" / "Lua Crescente: Ideal para iniciar um novo conto ou projeto de escrita (Pilar Talentosa)". **Por que é legal**: Dá um propósito prático para os widgets astronômicos que você já construiu.
- [ ] **Provocador de Pesquisa** (Pergunta em Aberto): Como você quer ser pesquisadora e polímata, muitas vezes anotamos dúvidas no meio dos textos. O que faz: Varre o conteúdo das suas páginas em busca de frases que terminam com ? ou marcadas com um símbolo específico (ex: [?]) e exibe uma delas aleatoriamente. A "Mágica": Te confronta com uma curiosidade que você teve no passado, incentivando o "instinto de busca" constante do Da Vinci.
- [ ] **Mapa do Próximo Passo** (Manual Arts): Para manter o pilar Talentosa (hobbies manuais) visível sem ser uma cobrança. **O que faz**: Mostra apenas o título e a última atualização de um projeto na subcategoria "Hobbies" ou "Artes Manuais".**A "Mágica":** Ao ver "Resina: Pendente há 3 dias", o widget te lembra visualmente de que existe um projeto físico esperando o seu talento, equilibrando o tempo gasto na tela.

#### Alta prioridade (dados já disponíveis)
- [x] **Agenda da Semana** — faixa de 7 dias com chips de `calendar_events` por dia, coloridos por tipo
- [x] **Lembretes Pendentes** — lista de reminders com `is_dismissed = 0` e `trigger_at` próximo, ordenados por data
- [x] **Próximas Provas / Defesas** — filtro de `calendar_events` por tipos acadêmicos (`prova`, `defesa`, `trabalho`) com countdown em dias
- [x] **Progresso dos Projetos** — barra de progresso por projeto ativo (tarefas planeadas e páginas)
- [x] **Citação Aleatória** — `QuoteWidget` implementado: mostra citação de `reading_quotes`, renovável a clique, exibe título/autor/localização conforme tamanho do widget
- [ ] **Widget POMODORO no Dashboard** — Pomodoro standalone com duas visualizações (relógio visual / relógio de areia); cor de acento das configurações; independente do Planner

#### Média prioridade (UI mais rica)
- [ ] **Mapa de Calor de Atividade** — grid estilo GitHub de horas estudadas por matéria/página/tag (não por páginas criadas; requer Pomodoro/time_sessions)
- [ ] **Sumário do Dia** — briefing textual: eventos hoje, prazos próximos, lembretes ativos

#### Futuros (dependem de features pendentes)
- [ ] **Meta de Leitura Anual** — gauge circular no Dashboard (base já feita: `readingGoals.progress()` disponível)
- [ ] **Tempo de Foco Hoje** — sessões Pomodoro do dia (depende de Pomodoro/`time_sessions`)
- [ ] **Grafo de Conexões** — mini grafo de força com páginas mais interligadas via backlinks (requer lib de visualização)

---

## Fase 50 — Futuro

- [ ] Exportar página como PDF ou Markdown
- [ ] Pomodoro Timer completo com estatísticas (consolidar com aba Tempo do ProjectDashboard e Widget do Dashboard)
- [ ] Templates customizados de projeto
- [ ] IA: integração com Ollama e APIs externas

---

## Design System — Efeitos Visuais (2026-04-10)

- [x] Vinheta sépia — body::before radial-gradient escurecendo bordas
- [x] Foxing — classe .foxing com manchas de envelhecimento nos cantos de cards
- [x] Marginalia — classe .marginalia-item com símbolo ✦ no hover à esquerda
- [x] Selo de cera — componente WaxSeal (aparecer em conclusão de item)
- [x] Luz de vela — componente CandleGlow com brilho radial pulsante no fundo
- [x] Loader alquímico — componente AlchemyLoader substituindo spinners

---

## Melhorias Futuras

- [x] Dashboard e página inicial de projeto: melhorar layout, widgets personalizáveis por projeto, resumo de progresso, atividades recentes, acesso rápido às páginas mais relevantes — `ProjectLocalDashboard` com coluna de stats por tipo + grid de widgets customizável (add/remove, localStorage); toolbar com dropdown de vistas substituindo abas horizontais

---
