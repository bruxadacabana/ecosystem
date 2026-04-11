# KOSMOS — TODO
Atualizado em: 2026-03-22

> **Padrões obrigatórios (toda sessão de desenvolvimento):**
> - Tipagem completa em todos os parâmetros e retornos
> - Erros nunca engolidos silenciosamente — propagar, retornar valor verificável ou dar feedback ao usuário
> - `log.error()` para falhas reais, `log.warning()` só para condições esperadas/recuperáveis
> - Atualizar este arquivo a cada feature implementada ou pedida
> - **Commit git a cada funcionalidade concluída** — mensagem descritiva, nunca acumular para o final

Referência de arquitetura: `KOSMOS_DEV_BIBLE_1.txt`

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

**Busca semântica (`nomic-embed-text`):**
- [ ] Toggle na search overlay para alternar entre FTS5 (palavras-chave) e busca vetorial (semântica)
- [ ] Embed a query em tempo real → retorna top-N artigos por cosine similarity

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
