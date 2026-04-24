# KOSMOS — TODO
Atualizado em: 2026-04-11

> **Padrões obrigatórios (toda sessão de desenvolvimento):**
> - Tipagem completa em todos os parâmetros e retornos
> - Erros nunca engolidos silenciosamente — propagar, retornar valor verificável ou dar feedback ao usuário
> - `log.error()` para falhas reais, `log.warning()` só para condições esperadas/recuperáveis
> - Atualizar este arquivo a cada feature implementada ou pedida
> - **Commit git a cada funcionalidade concluída** — mensagem descritiva, nunca acumular para o final

Referência de arquitetura: `KOSMOS_DEV_BIBLE_1.txt`

---

## Design Bible v2.0 — Audit (2026-04-11)

- [x] Modo noturno migrado para paleta "Atlas Astronômico à Meia-Noite" em `night.qss`
- [x] `reader_night.css` atualizado para nova paleta (fundo, bordas, `hr::after`)
- [x] `splash_screen.py` — cores hardcoded noturnas corrigidas

---

## FASE EXTRA — Features de Enriquecimento
> Funcionalidades além do escopo original. Implementar sequencialmente.

- [x] Filtros de palavra-chave (blocklist)
- [x] Feeds de busca (Google News RSS por termo)
- [x] Tags manuais nos artigos — chips no leitor, CRUD em `feed_manager.py`
- [x] Posição de scroll salva — `scroll_pos` via `window.scrollY`, restaurado no `loadFinished`
- [x] Top fontes e tópicos no dashboard — painéis com barras proporcionais
- [x] Deduplicação de artigos similares — `duplicate_of`, `rapidfuzz` (85%, 48h, entre feeds)
- [x] Highlights e anotações no leitor — `highlights` table, JS injection via `_HIGHLIGHT_SETUP_JS`, chips na barra abaixo das tags, anotações via QInputDialog
- [x] Tradução inline no leitor — `deep-translator` (Google Translate), sem dialog extra, menu de idiomas, "Ver original"
- [x] Scraping multilíngue — fallback BS4 para idiomas sem tokenizador
- [x] Fallback de scraping — traduz título para inglês → busca Google News RSS → tenta scraping do resultado
- [x] Filtro de idioma na view unificada — coluna `language` no modelo, detecção via `langdetect` no save
- [x] Título do artigo exibido no leitor (webview) e traduzido junto com o corpo
- [x] Label de idioma original → traduzido na barra inferior do leitor
- [x] Auto-salvar artigo ao criar primeiro destaque
- [x] Tratamento de erros: `log.error` para falhas reais, feedback visível ao usuário (tag, destaque), tipagem completa nos helpers privados

---

## FASE A — Leitor e Arquivo

- [x] Navegação anterior / próximo entre artigos
- [x] Botão "Buscar artigo completo" (com fallback BS4 multilíngue + fallback por título)
- [x] Purgação automática de artigos antigos (`purge_old_articles`)
- [x] `saved_view.py` — view de artigos salvos/favoritados
- [x] `archive_manager.py` — exportar artigo para Markdown em `data/archive/`
- [x] `archive_view.py` — browser do arquivo (lista arquivos .md de `data/archive/`)
- [x] Conversão HTML → Markdown via `html2text`

---

## FASE B — Plataformas Adicionais

**Reddit:**
- [ ] `reddit_fetcher.py` — wrapper praw 7.x
- [ ] `add_reddit_dialog.py` — adicionar subreddit (requer credenciais)
- [ ] Configurações → seção Reddit (client_id, client_secret, testar conexão)
- [ ] Mapeamento de posts para schema de artigos (score, num_comments em `extra_json`)

**YouTube:**
- [ ] Detecção automática de URL YouTube em `add_feed_dialog.py`
- [ ] Extração de `channel_id` de URLs `@handle` via requests + BS4
- [ ] Thumbnail de vídeos nos article cards

**Outras plataformas (RSS puro — feedparser já funciona, falta detecção):**
- [ ] Detecção automática: Tumblr, Substack, Mastodon pela URL
- [ ] `feed_type` correto salvo no banco para cada plataforma

---

## FASE C — Busca Global

- [x] FTS5 virtual table com triggers de sincronização (`database.py`)
- [x] `search.py` — query FTS5, retorna artigos ranqueados por relevância
- [x] Barra de busca global `Ctrl+K` (overlay flutuante)
- [x] Resultados com feed de origem e snippet destacado (mark)
- [x] Clicar no resultado abre o leitor
- [x] Navegação por teclado (↑↓ Enter Esc)

---

## FASE D — Exportação PDF e Estatísticas

**Exportação PDF:**
- [ ] `export_pdf.py` — WeasyPrint + template sépia (`export_template.html`)
- [ ] `export_dialog.py` — seletor de destino (artigo único ou lista de salvos)
- [ ] Botão "Exportar PDF" na toolbar do leitor

**Estatísticas:**
- [x] `read_sessions` — registrar início/fim de leitura por artigo
- [x] `stats.py` — agregação por dia, feed, plataforma, salvos por mês
- [x] `stats_view.py` — gráficos matplotlib, filtro de período
- [x] Botão "Stats" na sidebar

---

## FASE E — Polimento Final

- [ ] Animações: fade-in 150ms nos cards, slide 200ms no leitor, expand/collapse 120ms na sidebar
- [ ] Cursor piscante dourado (`#b8860b`) em campos de texto (QTimer 530ms)
- [ ] Cantos dobrados decorativos (SVG 20×20px)
- [ ] Ícone do app (`.ico` Windows, `.png` Linux)
- [ ] `iniciar.sh` e `iniciar.bat` com setup automático do venv
- [ ] Revisar todos os caminhos com `pathlib.Path` (sem strings hardcoded)
- [ ] Testes em Windows 10 (WeasyPrint + GTK3, QWebEngineView, VC++ Redist)

---

## FASE F — IA Local (Ollama)

> Integração com modelos LLM locais via Ollama (http://localhost:11434).
> Modelos:
> - `qwen2.5:7b` — geração de texto: resumo, extração de tags, análise
> - `nomic-embed-text` — embeddings semânticos: relevância, busca vetorial, similaridade
>
> Toda feature de IA é opcional e degradada graciosamente se o serviço não estiver disponível.
> Implementar sequencialmente — infraestrutura primeiro.

**Infraestrutura:**
- [x] `app/core/ai_bridge.py` — cliente Ollama: verificar disponibilidade (`/api/tags`), gerar texto (`/api/generate` streaming via `qwen2.5:7b`), gerar embeddings (`/api/embed` via `nomic-embed-text`)
- [x] Migration: colunas `ai_summary TEXT`, `ai_tags TEXT` (JSON), `embedding BLOB` (768 floats × 4 bytes), `ai_relevance REAL` em `articles`
- [x] Configurações → seção IA: endpoint (padrão `http://localhost:11434`), modelo de geração, modelo de embeddings, habilitar/desabilitar, botão "Testar conexão"

**Resumo de artigos (`qwen2.5:7b`):**
- [x] Botão "Resumir" na toolbar do leitor — aciona `ai_bridge` com o conteúdo do artigo
- [x] Painel recolhível abaixo da meta bar para exibir o resumo (streaming token a token via sinal PyQt)
- [x] Cache: resumo salvo em `ai_summary`; não regenera se já existir (botão vira "Ver resumo")

**Tags automáticas (`qwen2.5:7b`):**
- [x] Ao abrir artigo sem tags, sugerir tags via `format: "json"` do Ollama
- [x] Chips de sugestão em cor distinta na tags row — aceitar clicando, descartar com ×

**Relevância via embeddings (`nomic-embed-text`):**
- [x] Gerar embedding ao salvar/ler artigo em background — armazenar em `embedding BLOB`
- [x] Perfil de interesses: média dos embeddings dos artigos lidos/salvos (atualizado incrementalmente)
- [x] Score de relevância = cosine similarity(embedding do artigo, perfil) → `ai_relevance REAL`
- [x] Badge de relevância opcional nos article cards (configurável nas Settings)

**Busca semântica (`bge-m3:latest`):**
- [x] Toggle na search overlay para alternar entre FTS5 (palavras-chave) e busca vetorial (semântica)
- [x] Embed a query em tempo real → retorna top-N artigos por cosine similarity

**Análise de viés político (`qwen2.5:7b`):**
- [ ] Migration: colunas `ai_political_economic REAL` (-1.0 esquerda ↔ +1.0 direita) e `ai_political_authority REAL` (-1.0 libertário ↔ +1.0 autoritário) em `articles`
- [ ] Botão "Analisar viés" no leitor — retorna JSON `{economic_axis, authority_axis, confidence, reasoning}`
- [ ] Bússola política (widget 2D) no leitor exibindo a posição do artigo
- [ ] Agregação por feed na `sources_view` — posição média dos artigos analisados de cada fonte

**Detecção de clickbait (`qwen2.5:7b`):**
- [x] Migration: coluna `ai_clickbait REAL` (0.0 sem clickbait ↔ 1.0 clickbait puro) em `articles`
- [x] Score gerado pelo `_AnalyzeWorker` ao abrir artigo; salvo em cache
- [x] Badge `⚠` opcional nos article cards quando `ai_clickbait > 0.6` (configurável nas Settings)
- [x] Indicador `⚠ clickbait N%` na meta bar do leitor quando > 60%
- [ ] Filtro por score de clickbait na unified feed view

**Citação ABNT + análise 5Ws ao salvar artigo:**
- [x] Painel colapsível "Citação & 5Ws" exibido ao salvar artigo (★)
- [x] Citação ABNT gerada dos metadados existentes (autor, título, feed, data, URL, data de acesso)
- [x] 5Ws (Quem/O quê/Quando/Onde/Por quê) via `_FiveWsWorker` com `json_format=True`; cache em `ai_5ws TEXT`
- [x] Autor do artigo exibido em destaque na meta bar do leitor (`QLabel#readerAuthor`)

**Refatoração `_AnalyzeWorker` unificado (`qwen2.5:7b`):**
- [x] Substituir `_TagSuggestWorker` + `_FiveWsWorker` por `_AnalyzeWorker` (JSON único ao abrir artigo)
- [x] JSON de resposta: `{tags, sentiment, clickbait, five_ws}` — um call, quatro campos
- [x] `_SummarizeWorker` mantido separado com streaming (botão "Resumir", inalterado)
- [x] `save_ai_analysis()` em `feed_manager` persiste tudo em uma transação

**Sentimento e Tom (`qwen2.5:7b`):**
- [x] Migration: coluna `ai_sentiment REAL` (-1.0 negativo ↔ +1.0 positivo) em `articles`
- [x] Score gerado pelo `_AnalyzeWorker` ao abrir artigo; salvo em cache
- [x] Borda colorida esquerda nos article cards (verde/vermelho, configurável nas Settings)
- [x] Indicador `● tom positivo/negativo/neutro` na meta bar do leitor
- [ ] Filtro por tom na unified feed view
- [x] Gráfico de tendência de sentimento no `stats_view` (linha colorida por segmento, área preenchida)

**NER — Extração de Entidades (`qwen2.5:7b`):**
- [x] Migration: coluna `ai_entities TEXT` (JSON `{people,orgs,places}`) em `articles`
- [x] Gerado pelo `_AnalyzeWorker` junto com tags/sentiment/clickbait/5ws
- [x] Três mini-charts no `stats_view`: top pessoas, organizações e lugares do período

**Clustering por tópico (embeddings):**
- [x] K-means numpy sobre embeddings `nomic-embed-text` (k adaptativo, 5 reinicializações)
- [x] Rótulo por extração de palavras-chave dos títulos do cluster (sem LLM adicional)
- [x] Cards de tópicos no `stats_view` (últimos 90 dias ou período selecionado)
- [x] Seção "Tópicos em Destaque" no Dashboard — atualizada em tempo real via `analysis_done` signal + debounce 8s; títulos clicáveis abrem o leitor

---

---

## FASE G — Unificar "Salvo" e "Arquivo" em um único conceito: Arquivar

> Objetivo: eliminar o conceito separado de "Salvo" (favorito no banco).
> Clicar em ★ / "Arquivar" faz as duas coisas de uma vez: marca `is_saved=1`
> no banco E exporta o `.md` em `data/archive/`. Um único gesto, um único estado.
> A aba "Salvos" vira "Arquivados" e reflete exatamente o que está no sistema de arquivos.

### G.1 — Renomear ação e botão no leitor

- [x] `reader_view.py` — botão `_save_btn`: texto muda de "☆ Salvar" / "★ Salvo"
      para "☆ Arquivar" / "★ Arquivado"
- [x] `reader_view.py` — `_on_toggle_saved()`: ao marcar como salvo, chamar
      `archive_manager.export_article(article)` junto; ao desmarcar, deletar o `.md`
      correspondente (silenciosamente, com log de erro)
- [x] Remover botão "Exportar" separado da `_toolbar_row2` (ação agora está em Arquivar)

### G.2 — Renomear aba e view "Salvos" → "Arquivados"

- [x] `sidebar.py` — texto do botão de navegação: "Salvos" → "Arquivados"
- [x] `saved_view.py` — título e strings internas: "Salvos" → "Arquivados"
- [x] `unified_feed_view.py` — sem referências visíveis ao usuário (verificado)

### G.3 — Migrar artigos já salvos (sem .md) ao iniciar

- [x] `main_window.py` — `_migrate_saved_to_archive()` no startup: exporta artigos
      com `is_saved=1` que ainda não têm `.md` correspondente

### G.4 — Ajustar ArchiveView

- [x] `archive_view.py` — remover botão "Exportar artigo atual" órfão do header
- [x] `archive_view.py` — mensagem de estado vazio atualizada (sem referência ao botão Exportar)
- [x] `archive_manager.py` — adicionar `get_archive_path()` e `delete_archive()` helpers

---

## FASE H — Indicador de Status do Ollama

> Atualmente não há feedback visual enquanto o Ollama está conectando/processando —
> o usuário não sabe se a requisição está pendente antes do streaming começar.

### H.1 — Indicador na janela de Configurações

- [ ] `settings_dialog.py` → seção IA: substituir ou complementar o botão "Testar conexão"
      por um label de status persistente que atualiza ao abrir a seção:
      `"● Ollama conectado — qwen2.5:7b"` (verde) ou `"○ Ollama offline"` (vermelho)
- [ ] Verificação assíncrona via `ai_bridge.is_available()` ao exibir a seção de IA;
      não bloquear a abertura das Configurações

### H.2 — Spinner antes do streaming do Resumo

- [ ] `reader_view.py` → painel de resumo: exibir `"⟳ Aguardando Ollama…"` (label + spinner animado)
      entre o clique do botão "Resumir" e o primeiro token recebido;
      substituído pelo streaming assim que o primeiro token chega

### H.3 — Feedback durante análise em background

- [ ] `reader_view.py` → meta bar: exibir `"⟳ analisando…"` como placeholder
      na seção de tags e/ou 5Ws enquanto `_AnalyzeWorker` está rodando;
      hoje essa seção fica vazia e silenciosa até o resultado chegar
- [ ] Ao término (sucesso ou erro), substituir pelo resultado ou por mensagem de erro
      discreta (`"IA indisponível"`) sem bloquear a leitura

### H.4 — Badge de status global (sidebar ou statusbar)

- [ ] Adicionar indicador global discreto (ex: ponto colorido na sidebar ou
      `QStatusBar` no rodapé da janela principal): verde quando Ollama disponível,
      cinza quando não verificado, vermelho quando offline
- [ ] Polling leve a cada 60s via `QTimer` usando `ai_bridge.is_available()`;
      nenhum retry automático — apenas atualiza o indicador

---

## FASE I — Idioma de exibição e detecção de idioma nos artigos

> Objetivo: o usuário escolhe um idioma de exibição nas Configurações e todos
> os títulos e manchetes são traduzidos automaticamente para esse idioma ao
> serem exibidos. Cada card também indica o idioma original do artigo.
> Usa o mesmo motor de tradução já presente (`deep-translator`).

### I.1 — Detectar e persistir idioma de cada artigo

- [ ] `models.py` — verificar se coluna `language` já existe em `Article`
      (foi adicionada no filtro de idioma da Fase C); se não, adicionar migration
- [ ] `feed_manager.py` / `scraper.py` — garantir que `language` é detectado via
      `langdetect` no momento do save e persistido; artigos sem idioma ficam como `None`
- [ ] `article_card.py` — exibir badge pequeno com o idioma original do artigo
      (ex: `EN`, `PT`, `ES`) na meta row, visível em todas as views de lista

### I.2 — Configuração de idioma de exibição

- [ ] `config.py` — adicionar campo `display_language: str = ""` (vazio = sem tradução)
- [ ] `settings_view.py` — seção "Idioma de exibição": QComboBox com idiomas comuns
      (Português, English, Español, Français, Deutsch, 中文, …) + opção "Original (sem tradução)"
- [ ] Ao mudar, salvar em `settings.json` via `_cfg.set("display_language", code)`

### I.3 — Tradução automática dos títulos na exibição

- [ ] `article_card.py` — se `display_language` configurado e `article.language != display_language`,
      chamar `deep-translator` para traduzir o título antes de exibir no card
- [ ] Cache de traduções em memória (dict `{article_id: translated_title}`) para evitar
      re-traduzir ao rolar a lista; cache descartado ao mudar o idioma de exibição
- [ ] Tradução assíncrona: mostrar título original enquanto traduz, substituir ao concluir
      (para não travar o scroll); usar `QThread` ou `asyncio` conforme o contexto

### I.4 — Tradução no reader (opcional / fase posterior)

- [ ] Botão "Traduzir" na toolbar do leitor já existe — verificar se usa `display_language`
      como destino automático ao invés de pedir confirmação; ajustar se necessário

---

## IDEIAS

- [ ] **Detecção de evento**: identificar automaticamente que artigos de fontes diferentes cobrem exatamente o mesmo evento do mesmo dia — requer clustering temporal + semântico combinados (embeddings por janela de tempo + similaridade de título/entidades)

---

## FASE Z — Futuro

- [ ] Twitter/X quando solução gratuita e estável disponível
- [ ] Playwright para scraping de sites com JavaScript pesado
- [ ] Importar/exportar feeds via OPML
- [ ] Notificações nativas (plyer) para feeds prioritários
- [ ] Subreddit multis
- [ ] Mastodon com autenticação
- [ ] Suporte a podcasts (RSS de áudio com player interno)
- [ ] Integração com OGMA: salvar artigo diretamente
- [ ] Regras de auto-tag por palavra-chave
- [ ] Modo leitura offline (download antecipado)
