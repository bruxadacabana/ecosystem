# AKASHA — Registros do Universo

> *ākāśa* (आकाश) — "espaço luminoso". O substrato invisível onde tudo existe, ressoa e persiste.  
> Os *Registros Akáshicos*: a biblioteca cósmica onde cada pensamento, palavra e ação está eternamente gravada.

Buscador pessoal local com camada de assistente de IA. Dois sistemas independentes no mesmo processo: a **ferramenta** (busca, crawling, indexação, arquivamento) e a **assistente Akasha** (memória, reflexão, personalidade). A ferramenta funciona 100% sem IA — a assistente usa o LOGOS quando disponível.

**Porta:** `7071` · **Plataformas:** CachyOS (Linux) · Windows 10

---

## Arquitetura

```
AKASHA (ferramenta)              AKASHA (assistente — Akasha)
──────────────────────────       ─────────────────────────────────
Busca FTS5 + web (SearXNG)       Memória pessoal (personal_memory)
Crawling de sites                Loop de reflexão periódico (24h)
Indexação de páginas             Insights proativos (overlay)
Arquivamento em ecosystem_root   Estado afetivo (appraisal)
Download de papers (Unpaywall)   Análise de padrões de uso
Watch later / highlights         Personalidade configurável via HUB
Histórico de atividade           Comunicação com Mnemosyne
```

As duas camadas correm em paralelo. Lentidão ou falha na IA não afeta a ferramenta.

**Banco principal:** `akasha.db` (ferramenta + memória pessoal da assistente)  
**Banco de conhecimento:** `akasha_knowledge.db` (extração LLM de tópicos e entidades)  
**Arquivos salvos:** `{ecosystem_root}/akasha/Web/` (páginas arquivadas) · `{ecosystem_root}/akasha/Papers/` (PDFs)

---

## Funcionalidades

### Busca

- **FTS5** sobre páginas crawleadas (`crawl_fts`) e arquivos locais do ecossistema (`local_fts`)
- **Web search** via SearXNG — fallback quando a cobertura local é insuficiente
- **Classificação de intenção** automática: `navigational` / `fact-seeking` / `exploratory`  
  Roteia a busca para fontes locais, web ou ambas conforme o tipo detectado
- **Expansão de query** com sinônimos e termos relacionados (lexical, sem LLM)
- **Prioridade local**: quando há resultados locais suficientes, a busca web é adiada
- **Diversificação por domínio**: máx 2 resultados por domínio para não monopolizar a lista
- **Boost de citações Wikipedia**: páginas que citam artigos conhecidos sobem no ranking
- **Cache de resultados web**: evita buscas repetidas para queries idênticas na mesma sessão
- **Histórico de buscas**: toda query é salva e alimenta a análise de interesses da Akasha

### Lentes

Conjuntos de filtros salvos em `/lenses`. Permitem criar visões específicas da busca (ex: "só papers", "só sites em inglês", "só resultados locais"). Cada lente tem nome, filtros de fonte e palavras-chave obrigatórias.

### Biblioteca (crawling de sites)

- Adicionar domínios para rastreamento em `/library`
- Crawl agendado automático ou manual por site
- Configurar profundidade de links e intervalo de recrawl (diário / semanal / mensal)
- Ver e navegar páginas indexadas de cada site com leitor interno
- Descoberta recursiva de links internos a partir das páginas já crawleadas
- Pausar/retomar o crawler global ou por site individual
- Adicionar site rápido pelo popup da extensão ("Rastrear site")

### Arquivamento

- Salvar página completa localmente: `{ecosystem_root}/akasha/Web/{slug}.md`
- Extração de conteúdo via `trafilatura`
- Via interface, popup da extensão ou barra de ação da extensão
- Detecção de duplicatas (HTTP 409 se já arquivada)
- Tags e notas por arquivo

### Watch later

- Lista de páginas para ler depois em `/watch-later`
- Adicionar via popup da extensão ou interface
- Notas editáveis por item
- Busca FTS5 dentro da lista

### Highlights

- Salvar trechos selecionados de páginas via extensão
- Associados à URL de origem, pesquisáveis

### Papers

- Download de PDFs acadêmicos via **Unpaywall** (requer `unpaywall_email` no `ecosystem.json`)
- Salvo em `{ecosystem_root}/akasha/Papers/`
- Integração com **qBittorrent** para downloads via torrent

### Histórico de atividade

Registro unificado em `/history`, filtrável e paginado:

| Tipo | Quando é gerado |
|------|----------------|
| `search` | Toda busca realizada |
| `archive` | Toda página arquivada |
| `download` | Todo paper ou torrent baixado |
| `visit` | Site aberto a partir de resultado do AKASHA (via extensão) |

Cada visita é registrada com deduplicação por URL dentro de uma janela de 1h — a mesma página não aparece 20 vezes por uma única sessão de leitura.

### Domínios e favoritos

- Lista de todos os domínios rastreados com status (ativo/pausado, data da última crawl)
- Favoritos: domínios marcados como referência frequente
- Mover domínio de favoritos → biblioteca ou → blacklist em um clique

---

## Assistente — Akasha

### Princípio

O LLM no AKASHA age **apenas** na camada de análise interna (reflexão, insight, entendimento de query). Nunca sintetiza ou interpreta resultados de busca. O AKASHA devolve links, trechos e documentos — a usuária pensa, o sistema amplifica o alcance da busca.

### Memória pessoal

- Store isolado na tabela `personal_memory` (separado do índice público)
- Tipos de memória: `reading` (leituras longas), `reflection` (reflexões do loop), `insight` (enviados para overlay)
- Feedback da usuária (✓ / ✗ + motivo) molda o peso das memórias futuras
- Nunca exposta ao RAG de outros apps, nunca indexada pelo ecossistema

### Loop de reflexão (a cada 24h)

Quando LOGOS está disponível, a Akasha lê os seguintes dados para gerar uma reflexão:

| Dado | Fonte | Quantidade |
|------|-------|-----------|
| Tópicos de maior interesse (por score) | `topic_scores` | top 8 |
| Buscas realizadas recentemente | `search_history` | últimas 20 |
| Sites abertos via AKASHA (extensão) | `activity_log` tipo `visit` | últimas 20 |
| Domínios mais frequentados | `activity_log` agregado | top 8 com contagem |
| Páginas indexadas recentemente | `page_knowledge` | últimas 10 |
| Memórias anteriores (confirmadas e neutras) | `personal_memory` | até 5 |

Com esse contexto, gera uma reflexão em uma frase — uma conexão, padrão de comportamento ou observação genuína. Respostas genéricas, muito curtas ou vazias são descartadas automaticamente.

### Insights proativos

- Gerados pelo `InsightScheduler` a partir da memória acumulada
- A extensão do browser faz polling em `/insight/current` a cada 60s
- Enviados como overlay no canto inferior direito da página ativa
- Não aparecem em páginas do próprio AKASHA
- Feedback direto no overlay (✓ / ✗ / motivo detalhado)

### Estado afetivo

- Appraisals automáticos ao abrir páginas sobre tópicos conhecidos (via extensão)
- Dimensões: `novelty`, `pleasantness`, `goal_relevance`, `coping_potential`
- Boost logarítmico por tempo de leitura (satura em ~3.0 após 20 min)
- Influencia tom e urgência dos insights futuros

### Análise de interesses

Cada ação da usuária incrementa scores de tópicos:

| Ação | Delta de score |
|------|---------------|
| Busca sobre o tópico | +0.5 por tópico |
| Abrir página com esses tópicos (extensão) | +0.3 por tópico |
| Tempo de leitura (logarítmico) | +delta (0.05–3.0) por tópico |

Os scores alimentam a reflexão periódica, os insights e a ordenação de recomendações.

### Comunicação com a Mnemosyne

- **AKASHA → Mnemosyne**: envia insights via `ecosystem_client.send_insight_to_akasha()`
- **Mnemosyne → AKASHA**: recebe insights em `POST /friendship/insight` (task em background)
- A troca é sempre explícita — nunca indexação cruzada

---

## Extensão do browser

**Manifest V3 · Firefox (Gecko, mín. 109.0)**  
Atalho padrão: `Ctrl+Shift+S`

### Instalação

1. Abrir `about:debugging` no Firefox
2. "Este Firefox" → "Carregar extensão temporária"
3. Selecionar `extension/manifest.json`

A extensão é temporária (desaparece ao fechar o Firefox). Para permanente, precisaria ser assinada via AMO.

### Popup (qualquer aba)

Abre pelo ícone ou por `Ctrl+Shift+S`. Funciona em qualquer página — não exige que tenha sido aberta via AKASHA.

- URL e título da aba atual
- Ponto de status: verde (AKASHA online) / cinza (offline)
- Badges de estado da página atual:
  - `arquivada ✓` — já salva localmente
  - `biblioteca ✓` — domínio está sendo rastreado
  - `N relacionados` — páginas com tópicos em comum no índice
  - `não catalogada` — sem registro no AKASHA
- Três ações:
  - **Arquivar** → `POST /archive`
  - **Ver depois** → `POST /watch-later/add`
  - **Rastrear site** → `POST /library/add-quick`

### Barra de ação (abas abertas via AKASHA)

Aparece na parte inferior da página quando a aba foi aberta a partir de um resultado do AKASHA. Mesmas três ações do popup + botão de fechar. Implementada via Shadow DOM — não interfere com o CSS da página.

### Rastreamento de contexto (abas do AKASHA)

Para abas abertas a partir de resultados do AKASHA, ao carregar a página:

1. Envia `POST /context/push` com URL, título e primeiros 3.000 chars do texto
2. **Registra a visita em `activity_log` (tipo `visit`, dedup de 1h por URL)**
3. Se a página já está indexada: appraisal de leitura ativa + boost nos tópicos relevantes
4. Se não está indexada: agenda extração de conhecimento em background (pipeline LLM opcional)
5. Inicia timer de visibilidade — ao sair da aba envia `POST /context/time`

Efeitos do tempo de leitura (via `context/time`):
- ≥ 5s: contabilizado
- ≥ 2s de delta logarítmico: boost nos tópicos
- ≥ 2 min: Akasha salva memória de leitura engajada

### Overlay de insight

Quando a Akasha tem algo para mostrar (polling `/insight/current` a cada 60s):

- Card no canto inferior direito com texto do insight
- Botão ✓ confirmar → salva feedback positivo na memória
- Botão ✗ dispensar → salva feedback negativo e pode abrir painel de motivo
- Painel de motivo: opções "já sabia disso / irrelevante agora / incorreto / outro" + campo livre
- Feedback é enviado para a Akasha e molda reflexões futuras
- **Não aparece em páginas do próprio AKASHA**

### Saúde e ícone

- Poll a cada 30s: `GET /health`
- Ícone amarelo (`icon*.png`) quando AKASHA online
- Ícone cinza (`icon_inactive*.png`) quando offline

### Permissões

| Permissão | Uso |
|-----------|-----|
| `tabs` | Detectar aba opener (para rastrear abas do AKASHA); abrir popup via teclado |
| `activeTab` | Ler URL e título da aba atual no popup |
| `storage` | Reservada para uso futuro |
| `http://localhost:7071/*` | Comunicação com o servidor AKASHA |

---

## Endpoints principais

```
GET  /                            Interface principal (busca)
GET  /search?q=...&sources=...    Busca (local|web|all)
POST /archive                     Arquivar página
POST /context/push                Extensão: registrar página visitada + logar visita
POST /context/time                Extensão: reportar tempo de leitura
GET  /context/status?url=...      Estado de uma URL no AKASHA

GET  /library                     Lista de sites rastreados
POST /library                     Adicionar site com configuração completa
POST /library/add-quick           Adicionar site rápido (só URL)
GET  /library/{id}/pages          Ver páginas indexadas de um site
POST /library/{id}/crawl          Crawl manual de um site
POST /library/{id}/pages/{pid}/archive  Arquivar página da biblioteca
GET  /library/crawl/status        Status do crawler global
POST /library/crawl/pause         Pausar crawler
POST /library/crawl/resume        Retomar crawler

GET  /history?type=...&page=N     Histórico (all|search|archive|download|visit)
GET  /watch-later                 Lista de ver depois
POST /watch-later/add             Adicionar à lista
GET  /favorites                   Domínios favoritos
GET  /lenses                      Lentes de busca salvas
POST /lenses                      Criar lente
GET  /downloads                   Fila de downloads
POST /download                    Iniciar download

POST /friendship/insight          Receber insight da Mnemosyne
GET  /insight/current             Extensão: polling de insight da Akasha
POST /insight/feedback            Registrar feedback de insight
POST /insight/feedback_reason     Registrar motivo de rejeição

GET  /topics                      Tópicos de interesse com scores
GET  /health                      Status do servidor
```

---

## Configuração

Lida de `ecosystem.json` via `ecosystem_client` no startup:

```json
{
  "akasha": {
    "base_url": "http://127.0.0.1:7071",
    "exe_path": "...",
    "unpaywall_email": "seu@email.com",
    "personality_prompt": "...",
    "interest_seeds": ["tecnologia", "filosofia"]
  }
}
```

O HUB é a fonte de verdade — não editar `ecosystem.json` diretamente. O prompt de personalidade e as seeds de interesse são editáveis via HUB (aba Configurações).

---

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.13 + FastAPI (async) |
| Frontend | HTMX + Jinja2 (sem build step) |
| Banco local | SQLite via `aiosqlite` + FTS5 |
| Package manager | `uv` |
| Busca web | SearXNG |
| Extração de conteúdo | `trafilatura` |
| Inferência LLM | LOGOS (llama-server) via `ecosystem_client` |
| Comunicação inter-apps | `ecosystem_client` (HTTP) |

---

## Estrutura

```
AKASHA/
├── main.py                     FastAPI app + lifespan
├── config.py                   Lê ecosystem.json; constantes globais
├── database.py                 Schema SQLite + todas as funções de acesso
├── routers/
│   ├── search.py               GET /search · POST /archive
│   ├── crawler.py              GET|POST /library · crawl management
│   ├── context.py              POST /context/push|time · GET /context/status
│   ├── history.py              GET /history
│   ├── watch_later.py          GET|POST /watch-later
│   ├── favorites.py            GET|POST /favorites
│   ├── highlights.py           POST|GET|DELETE /highlights
│   ├── lenses.py               GET|POST|PUT|DELETE /lenses
│   ├── papers.py               POST /papers/download
│   ├── downloads.py            GET|POST /downloads
│   ├── interests.py            GET /topics · POST /refresh
│   ├── memory.py               GET|DELETE|PATCH /memory/*
│   ├── domains.py              GET /domains (lista unificada de fontes)
│   ├── graph.py                GET /graph (grafo de links entre páginas)
│   ├── dialogue.py             POST /dialogue (chat session)
│   ├── chat.py                 GET|POST /chat (chat com Akasha)
│   └── suggestions.py          GET /suggestions (sugestões de busca)
├── services/
│   ├── crawler.py              Spider assíncrono + extração de links
│   ├── crawler_scheduler.py    Agendamento de recrawl por site
│   ├── knowledge_worker.py     Pipeline LLM: tópicos + entidades de páginas visitadas
│   ├── reflection_loop.py      Loop de reflexão periódica da Akasha (24h)
│   ├── session_insight.py      Geração de insights a partir da memória
│   ├── personal_memory.py      Store isolado de memória da Akasha
│   ├── affective_state.py      Appraisals + estado emocional
│   ├── local_search.py         FTS5 + ranking local
│   ├── web_search.py           SearXNG + cache
│   ├── query_expansion.py      Expansão lexical de queries
│   ├── query_understanding.py  Classificação de intenção
│   ├── search_profile.py       Perfil de busca por tópico
│   ├── archiver.py             Fetch + trafilatura + salvar em Web/
│   ├── paper_download.py       Unpaywall + download de PDFs
│   ├── friendship_receiver.py  Recebe insights da Mnemosyne (background task)
│   └── realtime_context.py     Estado em memória da aba atual
├── extension/
│   ├── manifest.json           Manifest V3 (Firefox)
│   ├── background.js           Service worker: rastreia abas, saúde, polling de insight
│   ├── content.js              Barra de ação + overlay de insight + contexto/tempo
│   └── popup/
│       ├── popup.html
│       ├── popup.js            Popup: status, badges, ações
│       └── popup.css
└── templates/                  Jinja2 (HTMX)
```

---

## Dependências externas opcionais

| Serviço | Uso | Como configurar |
|---------|-----|----------------|
| LOGOS (llama-server) | Reflexão, insights, extração de tópicos, expansão de query | Automático via `ecosystem_client` |
| SearXNG | Busca web | `SEARXNG_URL` em `config.py` |
| Unpaywall | Download de papers acadêmicos | `akasha.unpaywall_email` no `ecosystem.json` |
| qBittorrent | Downloads via torrent | `akasha.qbt_*` no `ecosystem.json` |

Sem nenhum desses serviços, o AKASHA funciona normalmente como buscador local puro.

---

## Rodar

```bash
# CachyOS / Linux
bash iniciar.sh
# acesse http://localhost:7071
```

O script roda `uv sync` e inicia com `uv run python main.py`. O servidor registra automaticamente seu endereço no `ecosystem.json`.
