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

O AKASHA funciona como um mecanismo de busca pessoal que combina duas fontes: o seu próprio acervo local (sites que você rastreou, páginas que você arquivou) e a web aberta via SearXNG (instância local do meta-buscador, sem rastreamento). As duas fontes são consultadas em paralelo e os resultados aparecem em seções separadas na mesma interface.

**Como a busca decide o que fazer com a sua query:**

Toda query passa por um classificador de intenção antes de ser executada:

- `navigational` — você quer ir a um site específico (ex: "github fastapi"). O AKASHA prioriza resultados locais e evita busca web redundante.
- `fact-seeking` — você quer uma resposta direta (ex: "o que é FTS5"). Consulta local e web em paralelo, destaca snippets relevantes.
- `exploratory` — você está descobrindo um tema (ex: "técnicas de crawling ético"). Expande a query com termos relacionados, diversifica as fontes.

**Mecanismos de qualidade nos resultados:**

- **FTS5** (Full-Text Search 5 do SQLite): índice invertido sobre todo o conteúdo crawleado e arquivado. Suporta busca por campo (título tem peso 10×, corpo tem peso 1×) — encontrar a palavra no título de uma página vale muito mais que encontrá-la enterrada no meio do texto.
- **Classificador de intenção**: toda query é classificada (`navigational`, `fact-seeking`, `exploratory`, `informational`, etc.) para determinar a **apresentação** dos resultados — nunca a quantidade. Resultados não são truncados por intenção.
- **Busca web multi-página**: com SearXNG configurado, o AKASHA busca até N páginas em paralelo (padrão 4 × 25 = 100 resultados). Configurável em `ecosystem.json["akasha"]["web_pages"]` ou por `?web_pages=N` na URL. Sem SearXNG, usa DDG como fallback.
- **Expansão de query**: antes de buscar, o AKASHA adiciona sinônimos e termos relacionados lexicalmente (sem LLM). Buscar "machine learning" também encontra "aprendizado de máquina".
- **Prioridade local**: se há pelo menos N resultados locais com pontuação alta, a busca web é adiada — você não é forçada a esperar a web quando o seu acervo já cobre o tema.
- **Diversificação por domínio**: padrão de 5 resultados por domínio na lista final (configurável em Settings → `max_per_domain`; 0 = sem limite; `?diversity=N` como override por busca). Evita que um único site domine os resultados.
- **Filtragem de conteúdo vazio**: páginas com menos de 50 palavras são descartadas antes de indexar — evita poluir o banco com páginas de navegação, login ou redirecionamentos. `scripts/backfill_word_count.py` limpa entradas anteriores.
- **Boost de citações Wikipedia**: páginas que citam artigos da Wikipedia recebem pontuação extra — heurística de confiabilidade baseada em links de autoridade.
- **Cache de resultados web**: resultados da busca web são cacheados em dois níveis (memória LRU + SQLite). A mesma query não dispara duas requisições ao SearXNG/DDG.
- **Histórico de buscas**: toda query fica registrada e alimenta continuamente o sistema de interesses da Akasha (assistente), que aprende quais temas você explora com frequência.

### Lentes

Uma lente é um conjunto de filtros salvo com nome, que você pode ativar na interface de busca. Em vez de re-selecionar filtros toda vez, você cria uma lente uma vez e reutiliza.

Exemplos de uso:
- **"Só papers"**: filtra resultados para arquivos `.pdf` e fontes acadêmicas
- **"Só biblioteca"**: busca apenas no conteúdo que você rastreou, sem web
- **"Física quântica"**: busca com termos obrigatórios pré-configurados num domínio específico

Cada lente tem nome, filtros de fonte (`local`, `web`, `all`) e palavras-chave obrigatórias. Gerenciadas em `/lenses`.

### Biblioteca (crawling de sites)

A Biblioteca é o coração do acervo local do AKASHA. Você adiciona domínios que quer monitorar — blogs, wikis, fóruns, sites de pesquisa, qualquer coisa pública — e o AKASHA os rastreia automaticamente, baixando e indexando o conteúdo para busca offline.

**O que acontece quando você adiciona um site:**

1. O AKASHA visita a URL inicial e extrai todo o texto via `trafilatura` (remove menus, rodapés, propagandas — fica só o conteúdo)
2. Descobre links internos e os adiciona à fila de crawl (configurável: profundidade 1, 2 ou 3 níveis)
3. Indexa o conteúdo em FTS5 (`crawl_fts`) — fica disponível para busca imediatamente
4. Agenda re-crawl automático (diário / semanal / mensal) para manter o conteúdo atualizado

**Controles disponíveis:**
- Pausar/retomar o crawler global sem perder a fila
- Pausar/retomar site por site
- Disparar crawl manual imediato em qualquer site
- Navegar as páginas indexadas de um site com leitor interno (texto limpo, sem CSS da página original)
- Arquivar qualquer página indexada diretamente pelo leitor

Adicionar um site rápido também é possível via popup da extensão ("Rastrear site") — sem precisar abrir a interface.

### Arquivamento

Arquivar é diferente de marcar como favorito: o AKASHA baixa e salva o **conteúdo completo** da página localmente, em formato Markdown. Se o site sair do ar amanhã, o seu arquivo continua disponível.

O arquivo fica em `{ecosystem_root}/akasha/Web/{slug}.md` com metadados completos no frontmatter (título, URL de origem, data, tags, notas). O conteúdo é extraído via `trafilatura` — só o texto principal, sem ruído.

Pode arquivar de três formas:
- Pelo botão "Arquivar" na interface de busca (em qualquer resultado)
- Pelo popup da extensão (em qualquer aba aberta no browser)
- Pela barra de ação (em abas abertas a partir de resultados do AKASHA)

Se você tentar arquivar uma página que já foi arquivada, recebe HTTP 409 — sem duplicatas.

### Watch later

Lista de páginas que você quer ler depois mas não quer arquivar agora. Adicione via popup da extensão ou pela interface, com uma nota opcional explicando por que quer ver. A lista tem busca FTS5 — você encontra itens por palavra no título ou na nota, não precisa lembrar exatamente o que salvou.

Quando terminar de ler, marque como lido ou archive a página direto da lista.

### Highlights

Trechos de texto salvos de páginas que você estava lendo. A extensão captura o texto selecionado e associa ao URL da página de origem. Útil para guardar citações ou trechos específicos sem arquivar a página inteira.

Os highlights são pesquisáveis e ficam vinculados à URL — se você arquivar a página depois, o contexto se conecta automaticamente.

### Papers

Download de artigos acadêmicos em PDF diretamente pela interface. O AKASHA usa o **Unpaywall** (serviço gratuito que agrega versões abertas de papers científicos) para encontrar o PDF sem paywall. Requer um endereço de e-mail válido configurado em `ecosystem.json` → `akasha.unpaywall_email` (exigência da API do Unpaywall).

Papers baixados ficam em `{ecosystem_root}/akasha/Papers/`. Para papers que só existem via torrent, há integração com qBittorrent — o download é disparado pela interface e acompanhado na fila de downloads.

### Histórico de atividade

Registro cronológico de tudo que aconteceu no AKASHA, acessível em `/history`. Filtrável por tipo e paginado.

| Tipo | O que registra |
|------|----------------|
| `search` | Cada busca realizada, com a query e número de resultados |
| `archive` | Cada página arquivada, com URL e tags |
| `download` | Cada paper ou torrent iniciado |
| `visit` | Cada site aberto a partir de um resultado do AKASHA (via extensão) |

As visitas têm deduplicação por janela de 1 hora por URL — se você recarregar a mesma página várias vezes numa sessão, ela aparece uma vez no histórico, não trinta.

Esse histórico é mais do que um log: ele alimenta o sistema de análise de interesses da Akasha. A frequência com que você abre sites de um certo domínio, os tópicos das páginas que você visita, o tempo que passa lendo — tudo isso informa o que a Akasha aprende sobre você ao longo do tempo.

### Domínios e favoritos

**Biblioteca** (`/library`): todos os domínios que você adicionou para rastreamento, com status de cada um (ativo, pausado, última crawl, número de páginas indexadas).

**Favoritos** (`/favorites`): domínios que você sinalizou como referência frequente — aparecem destacados e podem ser convertidos em sites da biblioteca ou movidos para a blacklist (domínios que nunca devem aparecer nos resultados) com um clique. Útil para marcar fontes confiáveis sem necessariamente rastrear o site inteiro.

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

#### Temporária (desenvolvimento / teste rápido)

1. Abrir `about:debugging` no Firefox
2. "Este Firefox" → "Carregar extensão temporária"
3. Selecionar `extension/manifest.json`

A extensão desaparece ao fechar o Firefox. Para uso permanente, use uma das opções abaixo.

---

#### Permanente — Opção A: `web-ext sign` (qualquer Firefox, qualquer SO)

Requer uma conta gratuita em [addons.mozilla.org](https://addons.mozilla.org).

**1. Gerar API key**

Entre em `addons.mozilla.org` → sua conta → **Gerenciar chaves de API** → crie um par JWT (anote `api_key` e `api_secret`).

**2. Instalar `web-ext`**

```bash
# Linux / macOS
npm install -g web-ext

# Windows (PowerShell como administrador)
npm install -g web-ext
```

**3. Assinar e empacotar**

```bash
# Linux / macOS
cd /caminho/para/AKASHA/extension
web-ext sign --api-key=SEU_API_KEY --api-secret=SEU_API_SECRET --channel=unlisted

# Windows (PowerShell)
cd C:\caminho\para\AKASHA\extension
web-ext sign --api-key=SEU_API_KEY --api-secret=SEU_API_SECRET --channel=unlisted
```

O comando gera um `.xpi` em `web-ext-artifacts/`.

**4. Instalar o `.xpi`**

No Firefox: `about:addons` → ⚙ → **Instalar Add-on de Arquivo** → selecionar o `.xpi` gerado.

A extensão fica instalada permanentemente como qualquer outra — sobrevive a reinicializações e atualizações do Firefox.

> `--channel=unlisted` assina para auto-distribuição sem passar pelo processo de revisão da AMO. O `.xpi` gerado é pessoal e não é listado publicamente.

---

#### Permanente — Opção B: Firefox Developer Edition ou Nightly (sem conta AMO)

Funciona apenas no **Firefox Developer Edition** ou **Firefox Nightly** — o Firefox regular não permite extensões não assinadas permanentes mesmo com a configuração abaixo.

**1. Empacotar a extensão como `.xpi`**

```bash
# Linux / macOS
cd /caminho/para/AKASHA/extension
zip -r ../akasha_extension.xpi .

# Windows (PowerShell)
cd C:\caminho\para\AKASHA\extension
Compress-Archive -Path * -DestinationPath ..\akasha_extension.zip
# Renomear o .zip para .xpi
Rename-Item ..\akasha_extension.zip akasha_extension.xpi
```

**2. Desabilitar verificação de assinatura**

No Firefox Developer Edition / Nightly, abrir `about:config` e setar:

```
xpinstall.signatures.required = false
```

**3. Instalar**

`about:addons` → ⚙ → **Instalar Add-on de Arquivo** → selecionar `akasha_extension.xpi`.

A extensão fica permanente enquanto a configuração `xpinstall.signatures.required = false` estiver ativa.

---

> **Recomendação:** use a Opção A com `web-ext sign` se quiser continuar usando o Firefox regular. A Opção B é mais simples mas exige trocar de versão do browser.

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
    "interest_seeds": ["tecnologia", "filosofia"],
    "web_search_backend": "http://localhost:8888",
    "max_per_domain": 5,
    "web_pages": 4,
    "search_languages": [],
    "semantic_search": true,
    "default_city": ""
  }
}
```

| Campo | Padrão | Descrição |
|-------|--------|-----------|
| `web_search_backend` | `""` (DDG) | URL base do SearXNG self-hosted. Vazio = usa DuckDuckGo. |
| `max_per_domain` | `5` | Máximo de resultados por domínio (0 = sem limite). Override: `?diversity=N`. |
| `web_pages` | `4` | Páginas de resultados a buscar em paralelo (1–10). Override: `?web_pages=N`. |
| `search_languages` | `[]` | Lista de idiomas de resultado. Vazio = todos os idiomas (recomendado). |
| `semantic_search` | `true` | Habilita busca vetorial (embeddings via LOGOS) além do FTS5. |
| `default_city` | `""` | Cidade padrão para widget de previsão do tempo. |

O HUB é a fonte de verdade — não editar `ecosystem.json` diretamente quando o HUB estiver rodando. O prompt de personalidade e as seeds de interesse são editáveis via HUB.

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
| SearXNG (self-hosted) | Busca web com múltiplos engines (recomendado) | `akasha.web_search_backend` no `ecosystem.json`; instalar via `yay -S searxng-git` no CachyOS; porta padrão 8888 |
| Unpaywall | Download de papers acadêmicos | `akasha.unpaywall_email` no `ecosystem.json` |
| qBittorrent | Downloads via torrent | `akasha.qbt_*` no `ecosystem.json` |

**SearXNG vs DuckDuckGo:** sem SearXNG configurado, o AKASHA usa DDG como fallback (~20–50 resultados por query). Com SearXNG, agrega múltiplos engines em paralelo (~100 resultados) sem comprometer privacidade (tráfego passa pelo servidor local). Consultar `### AKASHA — SearXNG self-hosted como backend de busca` no `TODO.md` para instruções de instalação.

Sem nenhum desses serviços, o AKASHA funciona normalmente como buscador local puro.

---

## Rodar

```bash
# CachyOS / Linux
bash iniciar.sh
# acesse http://localhost:7071
```

O script roda `uv sync` e inicia com `uv run python main.py`. O servidor registra automaticamente seu endereço no `ecosystem.json`.
