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
- [ ] `gui/main_window.py` — painel "Gerar Documento" na aba Análise: `QComboBox` com todos os tipos abaixo; botão "Gerar"; área de resultado com `QTextEdit` read-only; botão "Exportar .md"; o tipo selecionado determina qual `core/*.py` é chamado

#### Briefing Document
- [ ] `core/briefing.py` — sumário executivo para papers/relatórios técnicos: temas principais, achados, insights acionáveis e divergências entre fontes; mais denso e estruturado que o resumo geral; retorna Markdown com seções fixas
- [ ] Integrar no Studio Panel como tipo `"Briefing"`

#### Relatório de Pesquisa Completo
- [ ] `core/report.py` — `ReportGenerator` via Map-Reduce (necessário para coleções grandes): seções fixas — (1) sumário executivo, (2) principais temas com findings, (3) análise por fonte, (4) convergências e divergências entre fontes, (5) lacunas identificadas, (6) referências com trechos; retorna Markdown estruturado
- [ ] Integrar no Studio Panel como tipo `"Relatório"`; opcional: export PDF via `weasyprint` (pesquisar viabilidade)

#### Study Guide Estruturado
- [ ] `core/study_guide.py` — guia de estudo completo: (1) conceitos-chave com definição de 2-3 frases, (2) termos técnicos com explicação, (3) questões de revisão (abertas, não múltipla escolha — isso é do Quiz/4.5), (4) tópicos para aprofundar; diferente do NotebookGuide automático que é só intro; retorna Markdown
- [ ] Integrar no Studio Panel como tipo `"Guia de Estudo"`

#### Table of Contents
- [ ] `core/toc.py` — índice temático navegável: LLM identifica os temas e subtemas cobertos pelos documentos e os organiza em hierarquia com links de âncora Markdown; útil para coleções grandes onde o usuário não sabe o que está indexado; retorna Markdown com `## Tema > ### Subtema`
- [ ] Integrar no Studio Panel como tipo `"Índice de Temas"`

#### Timeline
- [ ] `core/timeline.py` — extrair eventos com data/período dos documentos; ordenar cronologicamente; formato: lista de itens `[data] — [evento] — [fonte]`; útil para documentos históricos, biográficos, projetos com marcos
- [ ] Integrar no Studio Panel como tipo `"Linha do Tempo"`
- [ ] *(remove o item de 4.7 que listava isso como botão separado na aba Resumir — passa a ser Studio Panel)*

#### Blog Post
- [ ] `core/blogpost.py` — texto corrido narrativo sobre o conteúdo das fontes: introdução cativante, desenvolvimento em parágrafos fluidos (sem bullet points), conclusão; tom acessível, não acadêmico; útil para comunicar conteúdo técnico para não-especialistas; retorna Markdown
- [ ] Integrar no Studio Panel como tipo `"Blog Post"`

#### Mind Map
- [ ] `core/mindmap.py` — `MindMapBuilder`: LLM gera estrutura hierárquica como JSON `{central, branches: [{label, children[], source}]}`; exportar como (a) Mermaid mindmap syntax para abrir no Obsidian/browser, (b) `.mm` XML compatível com FreeMind/XMind
- [ ] Integrar no Studio Panel como tipo `"Mind Map"`; botão de export abre Mermaid no browser via `webbrowser.open()` ou salva `.mm`
- [ ] `requirements.txt` — avaliar `graphviz` para SVG embutido; alternativa: só export externo

#### Data Tables
- [ ] `core/tables.py` — LLM extrai entidades e relações conforme schema definido pela usuária; retorna lista de dicts; campo livre para especificar colunas (ex: "Nome, Data, Valor, Fonte")
- [ ] Integrar no Studio Panel como tipo `"Tabela de Dados"`; visualização em `QTableWidget`; export CSV/JSON

#### Slide Deck (baixa prioridade)
- [ ] `core/slides.py` — gerar apresentação em Markdown de slides (compatível com Marp/reveal.js); cada slide = seção do briefing; export como `.md`
- [ ] Integrar no Studio Panel como tipo `"Slides"`

## Fase 5 — UI e design

- [x] `gui/styles.qss` — fontes do ecossistema (IM Fell English, Special Elite, Courier Prime)
- [x] `gui/styles.qss` — visual rico: inputs estilo ficha de biblioteca, cards de resultado
- [x] `gui/styles.qss` — Design Bible v2.0: paleta "Papel ao Sol da Manhã", border-radius 2px, botões/tabs/scrollbars completos
- [x] `gui/main_window.py` — remover hardcodes de cor legados; objectNames para ollamaBanner, folderLabel, cancelBtn, similarLabel; cores dinâmicas de badge/watcher mapeadas para o ecossistema

## Fase 6 — Coleções Duais: Segunda Memória & Arquivo

> **Princípio central:** Obsidian é uma extensão do teu próprio cérebro — notas pessoais, pensamentos em evolução, conhecimento construído por ti. A Biblioteca é um arquivo de vozes externas — textos escritos por múltiplas pessoas, com perspectivas possivelmente contraditórias. Esta distinção muda a *relação epistémica* com o conteúdo e, portanto, o comportamento do Mnemosyne.

### Arquitetura de Coleções
- [ ] `core/collections.py` — `CollectionType` (enum: `VAULT` | `LIBRARY`), `CollectionConfig` (TypedDict: `name`, `path`, `type`), `load_collections()`, `save_collections()`, `add_collection()`, `remove_collection()`; migrar `config.json` de `{"watched_dir": "..."}` para `{"collections": [...], "last_active": "nome"}` com retrocompatibilidade
- [ ] `core/errors.py` — exceções novas: `CollectionNotFoundError`, `ObsidianVaultError`, `FrontmatterParseError`

### Vault Obsidian (Segunda Memória)
- [ ] `core/loaders.py` — loader Obsidian completo: `python-frontmatter` para YAML; metadata por nota: `title`, `tags`, `aliases`, `links` (wikilinks extraídos com regex `r'\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]'` — cobre os 4 formatos: `[[nota]]`, `[[nota|alias]]`, `[[nota#secção]]`, `[[nota#secção|alias]]`); ignorar `.obsidian/`, `templates/`, `attachments/`, notas com menos de 50 chars de corpo
- [ ] `core/loaders.py` — chunking por cabeçalho `##` para notas `.md`: 1 nota = 1 ou N chunks por secção, nunca partido a meio de parágrafo
- [ ] `core/rag.py` — seguimento de wiki-links: ao recuperar uma nota, incluir resumo (primeiros 300 chars) das notas linkadas como contexto secundário no prompt
- [ ] `core/rag.py` — prompt do Vault: tom introspectivo — "Nas tuas notas sobre X, escreveste que…"; citar título da nota, não o caminho do ficheiro
- [ ] `core/memory.py` — secção `collection` do Vault descreve o *teu estilo de pensar* (temas recorrentes, forma de estruturar ideias, língua preferida para reflectir), diferente da Biblioteca que descreve domínio de conhecimento externo

### Biblioteca (Arquivo de Vozes Externas)
- [ ] `core/rag.py` — prompt da Biblioteca: tom académico — "Em *[Título]* de [Autor], encontra-se que…"; se autores divergirem, apresentar perspectivas em confronto
- [ ] `core/loaders.py` — garantir metadata `author` e `title` em todos os loaders (PDF, EPUB, DOCX) para uso como chave de citação nas respostas

### Interface de Gestão de Coleções
- [ ] `gui/main_window.py` — selector de coleção no cabeçalho: `QComboBox` com ícone de tipo (`🔮 VAULT` / `📚 BIBLIOTECA`); trocar de coleção carrega vectorstore + memória + reseta `chat_history`
- [ ] `gui/main_window.py` — diálogo "Nova Coleção": campos nome, caminho (com botão "…"), tipo (radio Vault/Biblioteca); auto-detectar pasta `.obsidian/` e pré-selecionar tipo
- [ ] `gui/main_window.py` — aba Coleções no tab Gerenciar: lista com nome, tipo, caminho e estado do índice; botões editar/remover/indexar agora

---

### Redesign de Interface

- [ ] **Pesquisar UI do NotebookLM** como referência de design para RAG pessoal — anotar o que faz sentido adaptar para uso offline/local
- [x] **Reformulação completa da UI** (aprovada) — sidebar + painel principal; sem abas; modo escuro (#12161E); fontes do ecossistema aplicadas; design system consistente com DESIGN_BIBLE.txt
- [x] **Ajuste de legibilidade** — fontes aumentadas conforme Design Bible: corpo 13px, inputs/answerText IM Fell English 14–15px, sidebarBrand 24px, letter-spacing corrigido nos labels e botões
- [x] **Toggle dia/noite** — botão "☀ Modo Dia / ☽ Modo Noite" na sidebar inferior; `styles_light.qss` criado com paleta "Papel ao Sol da Manhã"; `dark_mode` persistido em config

### Sessões de Chat Nomeadas

> Contexto: hoje existe apenas um único chat ativo por vez (`history.jsonl`). Não há como nomear, salvar ou retomar conversas anteriores.

- [x] `core/memory.py` — adicionar conceito de `Session`: cada sessão tem id único (uuid4 curto), título editável, timestamp de criação/última atividade; `history.jsonl` passa a ser `sessions/{id}.jsonl`
- [x] `core/memory.py` — `list_sessions()` retorna sessões ordenadas por última atividade; `load_session(id)`, `new_session()`, `delete_session(id)`
- [x] `gui/main_window.py` — painel de sessões na sidebar: lista de conversas anteriores com título e data; clique carrega sessão; botão "+" cria nova; botão lixeira apaga
- [x] `gui/main_window.py` — auto-título da sessão: usa a primeira pergunta como título provisório (truncado a 60 chars); editável via duplo-clique na sidebar

---

*Atualizado em: 2026-04-20 — 4.9 reorganizado como Studio Panel com 9 tipos de documento (Briefing, Relatório, Study Guide, Table of Contents, Timeline, Blog Post, Mind Map, Data Tables, Slides); 4.7 consolidado em 4.9.*
