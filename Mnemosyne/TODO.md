# Mnemosyne — TODO de Desenvolvimento


## Padrões obrigatórios (não negociáveis)

- **Tratamento de erros com tipagem é prioridade absoluta.**
  Python: nunca `except Exception` sem re-tipar. Retornar `T | None` ou usar exceções específicas.
  Nenhum item está "pronto" se o caminho de erro não for tratado com o mesmo cuidado que o caminho feliz.

- **Manter este TODO atualizado.**
  Acrescentar aqui ANTES de implementar qualquer coisa que não conste.
  Marcar como `[x]` imediatamente ao terminar cada item.

- **Commit após cada item individual do TODO.**
  Ao marcar um item como `[x]`, fazer commit com mensagem clara.

- **Nunca passar de fase sem aprovação explícita.**
  Ao terminar todos os itens de uma fase, perguntar antes de começar a próxima.

---

## Fase 1 — Qualidade e robustez

- [x] `core/errors.py` — hierarquia de exceções tipadas
- [x] `TODO.md` — este arquivo criado com todas as fases
- [x] `core/config.py` + `config.json` — sistema de configuração (modelos, pasta)
- [x] `core/ollama_client.py` — detecção dinâmica de modelos disponíveis no Ollama
- [x] `core/loaders.py` — suporte a `.md` + erros tipados (sem `except Exception` genérico)
- [x] `core/indexer.py` — recebe `AppConfig`, erros tipados, `index_single_file()`
- [x] `core/rag.py` — recebe `AppConfig`, retorna `AskResult` tipado
- [x] `core/summarizer.py` — recebe `AppConfig`, erros tipados
- [x] `core/__init__.py` — re-exportar todos os novos tipos
- [x] `gui/workers.py` — `OllamaCheckWorker`, `IndexFileWorker`, erros específicos
- [x] `gui/main_window.py` — seleção de modelo, pasta via diálogo, verificação Ollama
- [x] `requirements.txt` — version pinning + dependências novas (langchain-ollama, rank-bm25)
- [x] `README.md` — corrigir modelo (qwen3.5:9b, não llama3.2)

## Fase 2 — Gerenciamento de Contexto Pessoal (PCM)

- [x] `core/memory.py` — `SessionMemory` + `CollectionIndex` *(criado na Fase 1 — dependência de main_window.py)*
- [x] `core/watcher.py` — `FolderWatcher` via `QFileSystemWatcher` *(criado na Fase 1 — dependência de main_window.py)*
- [x] `core/tracker.py` — rastreamento de hashes SHA-256 para indexação incremental
- [x] `core/rag.py` — hybrid retrieval (semântico + BM25 via rank-bm25)
- [x] `gui/main_window.py` — expor controle do watcher na UI (Fase 2 refinamentos)
- [x] `core/watcher.py` — detectar remoção e renomeação de arquivos (emitir signal `file_removed`)
- [x] `gui/main_window.py` — integrar `CollectionIndex` na UI: preencher "Última indexação" e metadata reais no tab Gerenciar
- [x] `gui/main_window.py` — retry automático de conexão ao Ollama sem reiniciar o app
- [x] `core/memory.py` — reescrever para arquitetura em camadas: `history.jsonl` (append-only, uma linha JSON por turno) + `memory.json` com seções `collection` (instruções editáveis pelo utilizador sobre a pasta) e `session` (factos extraídos automaticamente pelo LLM); `build_memory_context()` injeta memória no prompt RAG; `compact_session_memory()` usa LLM para sintetizar o histórico em factos compactos
- [x] `core/rag.py` + `gui/workers.py` — histórico de conversa multi-turno: últimos 5 turnos (cap 6 000 chars) formatados e injetados no prompt; `AskWorker` acumula `chat_history`; botão "Nova Conversa" na aba Perguntar reseta histórico e `SessionMemory`
- [x] `core/loaders.py` — suporte a `.epub`: `_load_epub()` com `ebooklib` + `BeautifulSoup`/`lxml`; 1 `Document` por capítulo com metadata `title`, `author`, `chapter`; ignorar itens com menos de 100 chars (capa, índice); atualizar `requirements.txt`
- [x] `core/ollama_client.py` — validar existência do modelo escolhido antes de lançar qualquer worker; aviso específico com nome do modelo em falta em vez de falha silenciosa 10 segundos depois
- [x] `gui/main_window.py` — badge de pendentes: "X novos / X modificados por indexar" (dourado) ou "✓ índice actualizado" (verde); actualizar no arranque, após indexação e ao mudar de pasta
- [x] `gui/main_window.py` — indicador de progresso por ficheiro na status bar durante indexação (`IndexWorker` emite `Signal(str)` com nome e posição actual, ex: "Indexando cap3.epub… (3/12)")
- [x] **Suporte básico ao vault do Obsidian** *(fundação para Fase 6)* — vectorstore único com metadata `source_type: "biblioteca" | "vault"`
  - `config.json`: campo `vault_dir` opcional
  - `core/loaders.py`: adicionar `source_type` ao metadata de cada chunk
  - `core/indexer.py`: aceitar múltiplas fontes com tipos distintos, watchers independentes
  - `core/rag.py`: parâmetro de filtro por `source_type` via ChromaDB `where`
  - `gui/main_window.py`: segundo picker de pasta na SetupDialog + seletor "Buscar em: Biblioteca / Vault / Ambos"

## Fase 3 — Features core

- [x] `core/indexer.py` — `update_vectorstore()` incremental completo usando tracker
- [x] `core/indexer.py` — remover chunks de arquivos deletados ou renomeados ao atualizar vectorstore (depende de tracker + signal `file_removed`); usar `collection.delete(where={"source": filepath})` via metadata filter — **atenção:** `_collection` é atributo privado do ChromaDB, verificar compatibilidade a cada atualização do pacote
- [x] `core/indexer.py` — tratar arquivos **modificados** no `update_vectorstore()`: remover chunks antigos do arquivo com `collection.delete(where={"source": filepath})` + re-adicionar chunks novos (evita duplicatas no vectorstore ao re-indexar)
- [x] `gui/main_window.py` — botão "Atualizar índice" (incremental) no tab Gerenciar
- [x] `core/summarizer.py` — Map-Reduce: modo "stuff" para corpora <12k chars; modo Map-Reduce para corpora grandes (fase Map: resumo por documento; fase Reduce: resumo final combinado); implementar via LCEL puro (langchain 1.x não tem `load_summarize_chain`)
- [x] `core/rag.py` — compressão contextual: após retrieval, filtrar cada chunk com LLM antes de enviar ao modelo principal (reduz alucinações 20–30%); k aumentado de 4 para 6 (mais candidatos); fallback para chunks originais se todos forem descartados
- [x] `core/rag.py` — Multi-Query Retrieval: reformular a pergunta em 3 variações antes do retrieval e deduplicar resultados por `page_content`; melhora recall para perguntas vagas (+1 LLM call leve)
- [x] `core/rag.py` — HyDE (Hypothetical Document Embeddings): gerar resposta hipotética à pergunta e embeddá-la em vez da pergunta original; eficaz para perguntas abstractas ("qual a visão de X sobre Y?"); alternativa ao Multi-Query
- [x] `gui/main_window.py` — compactação automática ao fechar: `closeEvent` → diálogo "Guardar esta conversa na memória?" → `CompactMemoryWorker`; elimina necessidade de compactar manualmente (depende do `memory.py` reescrito)
- [x] `core/tracker.py` — metadados de relevância por documento: `score_avg` (score médio de similaridade nas últimas N consultas) e `last_retrieved_at` (timestamp da última vez que foi retornado como fonte)
- [x] `core/rag.py` — time-decay de relevância: penalizar documentos com `last_retrieved_at` muito antigo no ranking final; parâmetro `relevance_decay_days` configurável em `AppConfig`

## Fase 4 — Inspirado no NotebookLM

### 4.0 Pré-requisito arquitectural
- [x] `core/rag.py` + `gui/workers.py` — migrar de `OllamaLLM` para `ChatOllama` com roles separados:
  - Persona do Mnemosyne fixa no `SystemMessage`; contexto RAG + pergunta no `HumanMessage`
  - Resolve "persona drift": em modelos 7B-14B, o contexto RAG pode empurrar a persona para fora da janela de atenção, causando respostas genéricas a partir da 4ª-5ª pergunta
  - Implementar dicionário `PERSONAS` em `core/rag.py` com chaves por modo (`"curador"`, `"socrático"`, `"resumido"`, `"comparação"`, `"podcaster"`, `"crítico"`) — torna a Fase 4.6 trivial
  - **Atenção:** com `ChatOllama`, o `chunk` em `llm.stream()` é `AIMessageChunk`; usar `chunk.content` nos workers em vez de `chunk` directamente; adicionar guard `if chunk.content:` pois chunks de metadata chegam com `content=""` e causam emissão de string vazia
  - Prerequisito para 4.6

### 4.1 Citação aprimorada
- [x] `core/rag.py` — retornar trecho exato do chunk junto com o nome do arquivo (não só o path)
- [x] `gui/main_window.py` — exibir fontes com trecho visível, não só nome do arquivo
- [x] `gui/main_window.py` — indicador de relevância por fonte (similaridade do chunk)

### 4.2 Seleção de fontes por consulta
- [x] `gui/main_window.py` — listar arquivos indexados com checkboxes; query respeita seleção
- [x] `core/rag.py` — suporte a filtro por lista de arquivos via ChromaDB `where` metadata

### 4.3 Notebook Guide automático
- [x] `core/guide.py` — ao terminar indexação, gerar automaticamente:
  - Resumo geral da coleção
  - 5 perguntas sugeridas sobre o conteúdo
- [x] `core/guide.py` — modo "Pérolas Escondidas": identificar os 3 fatos mais surpreendentes ou contraintuitivos dos documentos, com citação directa do texto como evidência
- [x] `gui/main_window.py` — exibir Guide na aba Resumir ou em painel lateral

### 4.4 FAQ Generator
- [x] `core/faq.py` — gerar lista de perguntas frequentes a partir dos documentos indexados
- [x] `gui/workers.py` — FaqWorker com streaming token a token
- [x] `gui/main_window.py` — botão "Gerar FAQ" na aba Resumir

### 4.5 Flashcards, Quiz e Estudo
- [ ] `core/flashcards.py` — extrair termos-chave, datas e conceitos e formatar como flashcards (frente/verso)
- [ ] `core/quiz.py` — gerar perguntas de múltipla escolha com gabarito a partir dos documentos
- [ ] `core/study_plan.py` — Roteiro de Estudos: gerar plano de aprendizado em 3 fases (Básico / Intermediário / Avançado) com conceitos-chave por fase e ordem lógica de estudo
- [ ] `gui/main_window.py` — nova aba "Estudar" com modo Flashcard, modo Quiz e modo Roteiro

### 4.6 Modos de consulta configuráveis
- [x] `core/rag.py` — 6 personas via `PERSONAS` dict + `SystemMessage` separado do contexto RAG: `curador` (padrão), `socrático`, `resumido`, `comparação`, `podcaster`, `crítico`
- [x] `gui/main_window.py` — `QComboBox` "Modo:" na aba Chat com tooltip descritivo; valor mapeado para `AskWorker(persona=...)`

### 4.7 Timeline automática
- [ ] *(movido para 4.9 Studio Panel — tipo "Linha do Tempo")*

### 4.8 Audio Overview
- [ ] `core/podcast.py` — Script de Podcast: gerar diálogo escrito entre dois "hosts" cobrindo os temas principais dos documentos; implementável sem TTS como passo intermédio
- [ ] `gui/main_window.py` — botão "Gerar Script de Podcast" na aba Resumir (exporta como `.md` ou `.txt`)
- [ ] Pesquisar opções de TTS offline (ex: Kokoro, Piper TTS) para converter script em áudio
- [ ] `core/audio.py` — gerar áudio a partir do script via TTS local (depende do item anterior)
- [ ] `gui/main_window.py` — botão "Ouvir resumo" com player embutido

### 4.9 Studio Panel — Geração de Documentos

> **Conceito:** Um painel único na aba Análise onde a usuária escolhe o *tipo de documento* a gerar e clica em "Gerar". Equivalente ao Studio Panel do NotebookLM. Cada tipo tem seu próprio `core/*.py` mas todos passam pelo mesmo ponto de entrada na UI.
>
> **Já implementado (não entram no Studio Panel, são automáticos):**
> - `SummarizeWorker` → resumo geral (aba Resumir)
> - `FaqWorker` → FAQ (aba Resumir — seção 4.4)
> - `GuideWorker` → Notebook Guide automático pós-indexação (resumo + perguntas sugeridas, gerado internamente)

#### UI do Studio Panel
- [x] `gui/main_window.py` — pill "Studio" na aba Análise; `QComboBox` com 9 tipos; botão "Gerar" (`sendBtn`); `QTextEdit` read-only com streaming; botão "Exportar .md" com `QFileDialog`; `StudioWorker` em `workers.py` com dispatcher por tipo via lazy import

#### Briefing Document
- [x] `core/briefing.py` — `iter_briefing()`: stuff (<12k chars) ou map-reduce; 4 seções fixas: Temas Principais, Achados, Insights Acionáveis, Divergências e Limitações; `BriefingError` adicionado a `errors.py`
- [x] Integrar no Studio Panel como tipo `"Briefing"` — via `_STUDIO_DISPATCH` em workers.py

#### Relatório de Pesquisa Completo
- [x] `core/report.py` — `iter_report()`: stuff (<10k chars) ou map-reduce; fase Map extrai temas/args/dados por fonte; fase Reduce gera 6 seções fixas em Markdown: Sumário Executivo, Temas e Findings, Análise por Fonte, Convergências/Divergências, Lacunas, Referências; `ReportError` definido no próprio módulo
- [x] Integrar no Studio Panel como tipo `"Relatório"` — via `_STUDIO_DISPATCH`
- [ ] Export PDF via `weasyprint` (pesquisar viabilidade — baixa prioridade)

#### Study Guide Estruturado
- [x] `core/study_guide.py` — `iter_study_guide()`: 4 seções — Conceitos-Chave (definição 2-3 frases), Termos Técnicos (glossário), Questões de Revisão (8-12 perguntas abertas), Tópicos para Aprofundar; stuff ou map-reduce
- [x] Integrar no Studio Panel como tipo `"Guia de Estudo"` — via `_STUDIO_DISPATCH`

#### Table of Contents
- [x] `core/toc.py` — `iter_toc()`: fase Map lista temas por fonte; fase Reduce consolida em hierarquia `## Tema > - Subtema > - Tópico` com máximo 8 temas principais; stuff ou map-reduce
- [x] Integrar no Studio Panel como tipo `"Índice de Temas"` — via `_STUDIO_DISPATCH`

#### Timeline
- [x] `core/timeline.py` — `iter_timeline()`: fase Map extrai eventos datados por fonte; fase Reduce consolida e ordena cronologicamente; formato `- **[data]** — [evento]`; query de retrieval favorece docs com datas; temperatura 0.0 para precisão factual
- [x] Integrar no Studio Panel como tipo `"Linha do Tempo"` — via `_STUDIO_DISPATCH`

#### Blog Post
- [x] `core/blogpost.py` — `iter_blogpost()`: temperatura 0.5 para escrita criativa; fase Map extrai pontos interessantes e exemplos; fase Reduce gera texto corrido com título criativo, introdução, 3-5 parágrafos de desenvolvimento e conclusão — sem bullet points
- [x] Integrar no Studio Panel como tipo `"Blog Post"` — via `_STUDIO_DISPATCH`

#### Mind Map
- [x] `core/mindmap.py` — `iter_mindmap()`: fase Map extrai hierarquia por fonte; fase Reduce gera bloco `\`\`\`mermaid mindmap\`\`\`` com `root((Tema))`, máximo 6 ramos, 3-4 subtópicos; pronto para Obsidian/GitHub/VS Code
- [x] Integrar no Studio Panel como tipo `"Mind Map"` — via `_STUDIO_DISPATCH`; export via botão "Exportar .md" já existente
- [ ] `requirements.txt` — avaliar `graphviz` para SVG embutido no Qt (baixa prioridade)

#### Data Tables
- [x] `core/tables.py` — `iter_tables(schema=...)`: sempre map-reduce para cobertura completa; fase Map extrai entidades por fonte conforme schema livre; fase Reduce consolida em tabela Markdown `| col | col |`; temperatura 0.0 para precisão; `schema` passado como kwarg pelo StudioWorker
- [x] Integrar no Studio Panel como tipo `"Tabela de Dados"` — campo de schema visível só neste tipo; `QTableWidget` com headers dinâmicos; parser de tabela Markdown; botão "Exportar CSV" via `csv.writer`

#### Slide Deck (baixa prioridade)
- [x] `core/slides.py` — `iter_slides()`: slides separados por `---`, título `#`, conteúdo `##` + bullet points; 6-10 slides; compatível com Marp/reveal.js; stuff ou map-reduce
- [x] Integrar no Studio Panel como tipo `"Slides"` — via `_STUDIO_DISPATCH`

## Fase 5 — UI e design

- [x] `gui/styles.qss` — fontes do ecossistema (IM Fell English, Special Elite, Courier Prime)
- [x] `gui/styles.qss` — visual rico: inputs estilo ficha de biblioteca, cards de resultado
- [x] `gui/styles.qss` — Design Bible v2.0: paleta "Papel ao Sol da Manhã", border-radius 2px, botões/tabs/scrollbars completos
- [x] `gui/main_window.py` — remover hardcodes de cor legados; objectNames para ollamaBanner, folderLabel, cancelBtn, similarLabel; cores dinâmicas de badge/watcher mapeadas para o ecossistema

## Fase 6 — Coleções Duais: Segunda Memória & Arquivo

> **Princípio central:** Obsidian é uma extensão do teu próprio cérebro — notas pessoais, pensamentos em evolução, conhecimento construído por ti. A Biblioteca é um arquivo de vozes externas — textos escritos por múltiplas pessoas, com perspectivas possivelmente contraditórias. Esta distinção muda a *relação epistémica* com o conteúdo e, portanto, o comportamento do Mnemosyne.

### Arquitetura de Coleções
- [x] `core/collections.py` — `CollectionType` (enum: `VAULT` | `LIBRARY`), `CollectionConfig` (dataclass: `name`, `path`, `type`, `enabled`, `source`, `ecosystem_key`); `sync_ecosystem_collections()`, `available_ecosystem_paths()`; migração automática do formato legado `{watched_dir, vault_dir}`
- [x] `core/errors.py` — exceções novas: `CollectionNotFoundError`, `ObsidianVaultError`, `FrontmatterParseError`

### Vault Obsidian (Segunda Memória)
- [x] `core/loaders.py` — loader Obsidian completo: `python-frontmatter` para YAML; metadata por nota: `title`, `tags`, `aliases`, `wikilinks`; regex cobre 4 formatos de wikilink; ignorar `.obsidian/`, `templates/`, `attachments/`, `.trash/`; notas com menos de 50 chars de corpo ignoradas
- [x] `core/loaders.py` — chunking por cabeçalho `##` para notas `.md`: `_split_by_heading()` — 1 nota = 1 ou N chunks por secção
- [x] `core/rag.py` — seguimento de wiki-links: `_follow_wikilinks()` lê notas ligadas e injeta primeiros 300 chars como contexto secundário no prompt
- [x] `core/rag.py` — prompt do Vault: `PERSONAS_VAULT` com tom introspectivo — "Nas tuas notas sobre X, escreveste que…"; cita título da nota, não o caminho
- [x] `core/memory.py` — secção `collection` do Vault descreve o *teu estilo de pensar* (temas recorrentes, forma de estruturar ideias, língua preferida para reflectir), diferente da Biblioteca que descreve domínio de conhecimento externo

### Biblioteca (Arquivo de Vozes Externas)
- [x] `core/rag.py` — prompt da Biblioteca: `PERSONAS` com tom académico — "Em *[Título]* de [Autor], encontra-se que…"; se autores divergirem, apresentar perspectivas em confronto
- [x] `core/loaders.py` — garantir metadata `author` e `title` em todos os loaders (PDF, EPUB, DOCX)

### Integração automática do ecossistema
- [x] `core/collections.py` — `ECOSYSTEM_SOURCES` define KOSMOS, AKASHA e Hermes (AETHER excluído); `sync_ecosystem_collections()` lê `ecosystem.json` automaticamente a cada `load_config()`
- [x] `gui/main_window.py` — `SetupDialog` com toggles (checkboxes) por fonte detectada em vez do antigo botão "Sugestões do ecossistema"
- [x] `core/config.py` — `ecosystem_enabled: dict[str, bool]` persiste estado ligado/desligado por fonte; `_migrate_legacy()` converte formato antigo para coleções

### Interface de Gestão de Coleções
- [x] `gui/main_window.py` — selector de coleção na sidebar: `QComboBox` com ícone de tipo (`🔮 VAULT` / `📚 BIBLIOTECA`); trocar de coleção carrega vectorstore + memória + reseta `chat_history`
- [x] `gui/main_window.py` — diálogo "Nova Coleção": campos nome, caminho (com botão "…"), tipo (radio Vault/Biblioteca); auto-detectar pasta `.obsidian/` e pré-selecionar tipo
- [x] `gui/main_window.py` — aba Coleções no tab Gerenciar: lista com nome, tipo, caminho e estado do índice; botões editar/remover/indexar agora

---

### Redesign de Interface

- [x] **Reformulação completa da UI** (aprovada) — sidebar + painel principal; sem abas; modo escuro (#12161E); fontes do ecossistema aplicadas; design system consistente com DESIGN_BIBLE.txt
- [x] **Ajuste de legibilidade** — fontes aumentadas conforme Design Bible: corpo 13px, inputs/answerText IM Fell English 14–15px, sidebarBrand 24px, letter-spacing corrigido nos labels e botões
- [x] **Toggle dia/noite** — botão "☀ Modo Dia / ☽ Modo Noite" na sidebar inferior; `styles_light.qss` criado com paleta "Papel ao Sol da Manhã"; `dark_mode` persistido em config

### Barra de progresso e alinhamento visual com o ecossistema

> O Mnemosyne foi feito em PySide6 em vez de PyQt6 (como KOSMOS e Hermes), e usa `styles.qss` próprio em vez do `ecosystem_qt.py`. A diferença visual percebida vem principalmente de: (1) o `.qss` do Mnemosyne não partilha o sistema de tokens do `ecosystem_qt.py`; (2) a barra de progresso e os feedbacks de indexação estão escondidos na barra inferior da janela (statusBar), que trunca nomes de arquivo longos e não tem indicador visual de avanço real.

- [ ] **Barra de progresso durante indexação** — substituir a statusBar por um widget dedicado na sidebar: `QProgressBar` com valor real (x/y arquivos), nome do arquivo atual numa linha acima (com elide no meio para não cortar o nome), e botão "Interromper" visível ao lado — tudo visível sem depender da barra inferior
- [ ] **Redesign completo da UI para paridade com o ecossistema** — migrar `styles.qss` do Mnemosyne para usar os mesmos tokens de cor do `ecosystem_qt.py` (`build_qss()`), adaptado para PySide6; aplicar as mesmas fontes, espaçamentos e padrões visuais dos outros apps; resultado: Mnemosyne visualmente consistente com KOSMOS/Hermes mesmo sendo PySide6 em vez de PyQt6

### Sessões de Chat Nomeadas

> Contexto: hoje existe apenas um único chat ativo por vez (`history.jsonl`). Não há como nomear, salvar ou retomar conversas anteriores.

- [x] `core/memory.py` — adicionar conceito de `Session`: cada sessão tem id único (uuid4 curto), título editável, timestamp de criação/última atividade; `history.jsonl` passa a ser `sessions/{id}.jsonl`
- [x] `core/memory.py` — `list_sessions()` retorna sessões ordenadas por última atividade; `load_session(id)`, `new_session()`, `delete_session(id)`
- [x] `gui/main_window.py` — painel de sessões na sidebar: lista de conversas anteriores com título e data; clique carrega sessão; botão "+" cria nova; botão lixeira apaga
- [x] `gui/main_window.py` — auto-título da sessão: usa a primeira pergunta como título provisório (truncado a 60 chars); editável via duplo-clique na sidebar

---

---

## Fase 7 — Modo de Pesquisa Profunda (integração com AKASHA)

> Combina a biblioteca local do Mnemosyne com conteúdo web buscado em tempo real pelo AKASHA.
> Requer que o AKASHA esteja rodando na porta 7071 (Fase 13 do AKASHA: `/search/json` e `/fetch`).
> Degradação graciosa: se AKASHA offline, botão oculto e aviso ao usuário.

### AkashaClient

- [ ] `core/akasha_client.py` — cliente httpx para a API REST do AKASHA:
      `search(query, max_results) -> list[AkashaResult]` — chama `GET /search/json`;
      `fetch(url) -> FetchResult` — chama `POST /fetch`;
      `is_available() -> bool` — `GET /health` com timeout 2s;
      tipos: `AkashaResult(url, title, snippet)`, `FetchResult(url, title, content_md, word_count)`;
      erros específicos: `AkashaOfflineError`, `AkashaFetchError`

### SessionIndexer

- [ ] `core/session_indexer.py` — indexação temporária em memória para a sessão de pesquisa:
      usa `chromadb.EphemeralClient()` (sem persistência em disco);
      `add_pages(pages: list[FetchResult]) -> None` — chunka com `RecursiveCharacterTextSplitter`
      e embeda via Ollama; `search(query, k=5) -> list[Document]`; `clear() -> None`;
      limite de RAM: máx 10 páginas por sessão (configura­vel); estimativa ~50-100MB por sessão

### DeepResearchWorker

- [ ] `gui/workers.py` — `DeepResearchWorker(QThread)`:
      sinal `status(str)` para feedback incremental ("Buscando no AKASHA…", "Carregando 3/5…", etc.);
      sinal `finished(bool, str, list)` — sucesso, resposta RAG, fontes (local + web);
      pipeline:
        1. `AkashaClient.search(query)` → lista de URLs candidatas (top 5)
        2. Para cada URL: `AkashaClient.fetch(url)` (paralelo com `asyncio.gather` via `asyncio.run`)
        3. `SessionIndexer.add_pages(pages)` → indexa em memória
        4. `prepare_ask()` com retriever combinado (vectorstore local + session_indexer)
        5. LLM gera resposta; emite `finished`
        6. `SessionIndexer.clear()` após resposta

### Interface

- [ ] `gui/main_window.py` — toggle "🌐 Pesquisa Profunda" no painel de perguntas:
      visível apenas se AKASHA disponível (verificar `is_available()` no startup);
      quando ativo, `AskWorker` é substituído por `DeepResearchWorker`;
      status incremental exibido na barra inferior durante a pesquisa;
      citar fontes web com badge `[WEB]` distintos das fontes locais

### Notas de implementação

- Latência esperada: 8–20s em casa (RX 6600), 20–40s no trabalho (i5-3470, sem AVX2)
- No i5: limitar a 3 páginas web (não 5) e desativar embedding da session (usar context stuffing)
  — margem de RAM apertada com 8GB; verificar `psutil.virtual_memory().available` antes de embedar
- `SessionIndexer` usa `EphemeralClient` — dados descartados ao chamar `clear()` ou fechar o app

---

## Correções de bugs

- [x] `gui/workers.py` — `IndexWorker`: limpar `persist_dir` antes de indexar para evitar acúmulo de duplicatas no ChromaDB em execuções repetidas
- [x] `gui/workers.py` — `IndexWorker`: chamar `tracker.mark_indexed(file_path)` após cada arquivo para salvar progresso; interrupção agora permite retomada via "Atualizar índice"
- [x] `gui/workers.py` — `IndexWorker`: reestruturado para processar arquivo por arquivo (load → chunk → embed → add → mark_indexed) em vez de chunkar tudo antes de embedar

*Atualizado em: 2026-04-23 — bugs críticos do IndexWorker corrigidos.*

---

## Fase 8 — Otimizações de RAG (pesquisa 2026-04-23)

### 8.1 Métrica cosine no ChromaDB (alta prioridade)
- [ ] `core/indexer.py` — adicionar `collection_metadata={"hnsw:space": "cosine"}` em todos os pontos que criam ou abrem o Chroma: `create_vectorstore()`, `index_single_file()`, `update_vectorstore()`, `load_vectorstore()`
- [ ] `gui/workers.py` — `IndexWorker.run()`: adicionar `collection_metadata={"hnsw:space": "cosine"}` na criação do `Chroma(persist_directory=...)`
- [ ] Validar que coleções existentes são recriadas automaticamente ao rodar "Indexar tudo" (o IndexWorker já apaga o persist_dir — a métrica será aplicada na recriação)

### 8.2 Tamanho de chunk (alta prioridade)
- [ ] `core/config.py` — alterar defaults: `chunk_size` 800 → 1800, `chunk_overlap` 100 → 250
  - Justificativa: 800 chars ≈ 200 tokens; ótimo benchmarkado é 400-512 tokens ≈ 1600-2000 chars; overlap mantém ~14%

### 8.3 FlashRank reranking (média prioridade)
- [ ] `requirements.txt` — adicionar `flashrank`
- [ ] `core/rag.py` — envolver o retriever base em `ContextualCompressionRetriever` com `FlashrankRerank`:
  - busca vetorial com k=30 candidatos
  - FlashRank reordena por relevância real → top 6-8 para o LLM
  - modelo multilíngue: `"ms-marco-MultiBERT-L-12"` (melhor para PT)
  - `top_n` configurável em `AppConfig`
- [ ] `core/config.py` — campos novos: `reranking_enabled: bool = True`, `reranking_top_n: int = 6`
- [ ] `gui/main_window.py` — toggle "Reranking" na SetupDialog (opcional — pode ficar para depois)

### 8.4 RAGAS — avaliação do pipeline (baixa prioridade)
- [ ] `eval/ragas_eval.py` — script standalone (fora do app) para avaliar faithfulness, context precision e answer relevancy usando Ollama como juiz
- [ ] Executar antes/depois das mudanças 8.1-8.3 para medir impacto real

### 8.5 LightRAG — grafos de conhecimento (baixa prioridade, hardware limitante)
- [ ] Pesquisar se modelos 8B são suficientes para extração de grafo em corpus pequeno (~50 docs)
- [ ] Implementar apenas se hardware futuro permitir (≥ 32B recomendado para resultados bons)

*Atualizado em: 2026-04-23 — Fase 8 adicionada (otimizações RAG baseadas em pesquisa).*
