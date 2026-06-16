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

O AKASHA funciona como um mecanismo de busca pessoal que combina duas fontes: o seu próprio acervo local (sites que você rastreou, páginas que você arquivou) e a web aberta via SearXNG (meta-buscador sem rastreamento) somada à Marginalia (índice independente de web indie/nicho). As fontes são consultadas em paralelo e os resultados aparecem em seções separadas na mesma interface.

**Como a busca decide o que fazer com a sua query:**

Toda query passa por um classificador de intenção antes de ser executada:

- `navigational` — você quer ir a um site específico (ex: "github fastapi"). O AKASHA prioriza resultados locais e evita busca web redundante.
- `fact-seeking` — você quer uma resposta direta (ex: "o que é FTS5"). Consulta local e web em paralelo, destaca snippets relevantes.
- `exploratory` — você está descobrindo um tema (ex: "técnicas de crawling ético"). Expande a query com termos relacionados, diversifica as fontes.

**Mecanismos de qualidade nos resultados:**

- **FTS5** (Full-Text Search 5 do SQLite): índice invertido sobre todo o conteúdo crawleado e arquivado. Suporta busca por campo (título tem peso 10×, corpo tem peso 1×) — encontrar a palavra no título de uma página vale muito mais que encontrá-la enterrada no meio do texto.
- **Classificador de intenção**: toda query é classificada (`navigational`, `fact-seeking`, `exploratory`, `informational`, etc.) para determinar a **apresentação** dos resultados — nunca a quantidade. Resultados não são truncados por intenção.
- **Busca web multi-página**: com SearXNG configurado, o AKASHA busca até N páginas em paralelo (padrão 4 × 25 = 100 resultados). Configurável em `ecosystem.json["akasha"]["web_pages"]` ou por `?web_pages=N` na URL. Sem SearXNG, usa DDG como fallback.
- **Marginalia (web indie/nicho)**: em paralelo ao SearXNG, o AKASHA consulta a [Marginalia](https://marginalia-search.com) — um índice independente focado em "a web pequena, antiga e estranha" (blogs pessoais, zines, ativismo, documentação sem SEO). Traz domínios que Google/Bing não cobrem, somando volume e diversidade. Funciona **sem chave** (API pública, rate limit compartilhado). Para um rate limit próprio, peça uma chave gratuita por e-mail a `contact@marginalia-search.com` e cole em **Settings → Marginalia API key** (campo `akasha.marginalia_api_key`). As fontes web são fundidas via Reciprocal Rank Fusion (RRF), deduplicando por URL.
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

Download de artigos acadêmicos em PDF diretamente pela interface. O AKASHA usa o **Unpaywall** (serviço gratuito que agrega versões abertas de papers científicos) para encontrar o PDF sem paywall. Requer um e-mail válido (exigência da API), configurado em **Settings → E-mail Unpaywall** (campo `akasha.unpaywall_email`). Sem e-mail configurado, o download via Unpaywall fica indisponível (degrada graciosamente).

Papers baixados ficam em `{ecosystem_root}/akasha/Papers/`. O download é HTTP direto (URL → arXiv → Unpaywall), acompanhado na fila de downloads. *(Download via torrent/qBittorrent é planejado — não implementado hoje.)*

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

### Conversa (/chat)

A aba Conversa é o ponto de acesso ao RAG da Akasha: ela busca no índice pessoal e responde com base no que encontrou, citando as fontes.

**O que o /chat busca:**
- Arquivos locais (KOSMOS, páginas arquivadas, Mnemosyne, transcrições Hermes) — FTS5 + semântico via LOGOS
- **Biblioteca inteira** (todos os sites rastreados) — FTS5 em `crawl_fts` (`include_crawl=True`)
- Vetores LOGOS de arquivos locais e crawl — quando ≥ 10 embeddings disponíveis

**Voz própria:** a Akasha cita as fontes com `[N]` e pode adicionar conexões entre fontes, apontar contradições ou lacunas. Não dá aulas nem parafraseia sem citar. O tom muda com o estado afetivo: valência positiva → exploratório e especulativo; valência negativa → analítico e crítico.

**Fontes:** aparecem como lista colapsável abaixo de cada resposta, com link clicável e trecho do conteúdo — mesmo que a resposta não contenha citações `[N]`.

**Pesquisa Profunda (Deep Research):** botão "🔍" na interface de chat. Quando ativo (ou quando a heurística detecta uma pergunta complexa), o AKASHA:
1. Gera 3-5 reformulações da pergunta e busca todas em paralelo
2. Busca o conteúdo completo dos top 8 documentos (configurável em Settings)
3. Usa um prompt de síntese integrativa: encontrar conexões, contradições, lacunas
4. Resposta mais longa com `max_tokens=800` e timeout de 120s

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

Toda a configuração vive na seção `akasha` do `ecosystem.json` e é lida via `ecosystem_client`. **O HUB é a fonte de verdade** — não editar o `ecosystem.json` à mão com o HUB rodando.

**Onde editar (toda config tem UI):**
- **AKASHA → Settings (`/settings`)**: parâmetros de busca, fontes, IA, histórico (a maioria das chaves abaixo).
- **HUB**: caminhos de dados (`data_path`, `archive_path`), prompt de personalidade e seeds de interesse da assistente.

Exemplo (seção `akasha` do `ecosystem.json`):

```json
{
  "akasha": {
    "base_url": "http://127.0.0.1:7071",
    "exe_path": "...",
    "data_path": "{ecosystem_root}/akasha",
    "archive_path": "{ecosystem_root}/akasha",
    "personality_prompt": "...",
    "interest_seeds": ["tecnologia", "filosofia"],

    "web_search_backend": "http://localhost:8888",
    "marginalia_api_key": "",
    "unpaywall_email": "seu@email.com",
    "invidious_instance": "",
    "max_per_domain": 5,
    "web_pages": 4,
    "search_languages": [],
    "default_city": "",

    "src_web": true, "src_local": true, "src_sites": true,
    "src_papers": false, "src_videos": false, "src_images": false,

    "semantic_search": true,
    "reranking": false,
    "llm_query_expansion": true,
    "deep_research_max_docs": 8,

    "save_search_history": true,
    "save_clicks": true,
    "interest_consolidate_interval_min": 30
  }
}
```

**Dados e identidade (HUB / auto):**

| Campo | Padrão | Onde | Descrição |
|-------|--------|------|-----------|
| `base_url` | auto | auto | URL onde o servidor se registra (escrito no startup). |
| `exe_path` | auto | auto | Caminho do `iniciar.sh`/`iniciar.bat` (escrito no startup). |
| `data_path` | pasta local | HUB | Diretório do banco `akasha.db`. Vazio = `AKASHA/akasha.db`. |
| `archive_path` | pasta local | HUB | Diretório dos arquivos salvos (`Web/`, `Papers/`). |
| `personality_prompt` | default interno | HUB | Prompt-base de personalidade da assistente Akasha. |
| `interest_seeds` | `[]` | HUB | Sementes de interesse iniciais da assistente. |

**Busca web e fontes externas (Settings):**

| Campo | Padrão | Descrição |
|-------|--------|-----------|
| `web_search_backend` | `""` (DDG) | URL base do SearXNG. Vazio = usa DuckDuckGo. Ver [Rodando o SearXNG](#rodando-o-searxng-fedora--cachyos--windows-10). |
| `marginalia_api_key` | `""` (public) | Chave da Marginalia (web indie/nicho). Vazio = chave pública (funciona; rate limit compartilhado). Chave própria via `contact@marginalia-search.com`. |
| `unpaywall_email` | `""` | E-mail exigido pela API do Unpaywall/OpenAlex para baixar PDFs abertos. Vazio = Unpaywall indisponível. |
| `invidious_instance` | `""` | URL de instância Invidious (vídeos do YouTube sem rastreamento). |

**Apresentação e idioma da busca (Settings):**

| Campo | Padrão | Descrição |
|-------|--------|-----------|
| `max_per_domain` | `5` | Máximo de resultados por domínio (0 = sem limite). Override: `?diversity=N`. |
| `web_pages` | `4` | Páginas de resultados web a buscar em paralelo (1–10). Override: `?web_pages=N`. |
| `search_languages` | `[]` | Idiomas de resultado. Vazio = todos (recomendado). |
| `default_city` | `""` | Cidade padrão do widget de previsão do tempo. |

**Fontes ligadas por padrão (Settings):**

| Campo | Padrão | Descrição |
|-------|--------|-----------|
| `src_web` | `true` | Incluir resultados da web por padrão. |
| `src_local` | `true` | Incluir o acervo local (arquivos) por padrão. |
| `src_sites` | `true` | Incluir a biblioteca (sites rastreados) por padrão. |
| `src_papers` | `false` | Incluir papers acadêmicos por padrão. |
| `src_videos` | `false` | Incluir vídeos (via Invidious) por padrão. |
| `src_images` | `false` | Incluir imagens por padrão. |

**IA / busca semântica (Settings):**

| Campo | Padrão | Descrição |
|-------|--------|-----------|
| `semantic_search` | `true` | Busca vetorial (embeddings via LOGOS) além do FTS5. Embeddings gerados ao indexar (fire-and-forget); backfill no startup (até 50/vez, Semáforo 2, P3); ativa com ≥ 10 embeddings e LOGOS disponível — senão fallback silencioso só FTS5. |
| `reranking` | `false` | Reordena resultados com reranker local (`flashrank` — modelo baixado no 1º uso). |
| `llm_query_expansion` | `true` | Expansão de query via LLM (LOGOS) quando disponível; senão, expansão lexical. |
| `deep_research_max_docs` | `8` | Nº de documentos cujo conteúdo completo é buscado na Pesquisa Profunda (1–20). |

**Histórico e interesses (Settings):**

| Campo | Padrão | Descrição |
|-------|--------|-----------|
| `save_search_history` | `true` | Registra cada busca (alimenta interesses da Akasha). |
| `save_clicks` | `true` | Registra cliques em resultados. |
| `interest_consolidate_interval_min` | `30` | Intervalo (min) de consolidação dos scores de interesse (5–1440). |

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

## Serviços externos

### SearXNG — backend de busca web (necessário)

O SearXNG **não é opcional** no uso pretendido: é o backend que agrega Google/Bing/Startpage/etc. em paralelo (~100 resultados/busca). Sem ele o AKASHA degrada para o **DuckDuckGo** (~20–50 resultados) como último recurso — funciona, mas é o modo reduzido, não o pretendido.

- **Instalação (por SO):** ver **[Rodando o SearXNG](#rodando-o-searxng-fedora--cachyos--windows-10)** (Fedora/Docker, CachyOS, Windows).
- **Configuração:** `akasha.web_search_backend` no `ecosystem.json` — editável no painel **Busca** do HUB. Pré-requisitos do `settings.yml` (formato `json`, `limiter: false`) e curadoria de engines documentados na mesma seção.

### LOGOS — inferência de IA (opcional; necessário só para a assistente)

Reflexão, insights, extração de tópicos/entidades, expansão de query e busca semântica vetorial. A **ferramenta** de busca funciona 100% sem ele; só a **assistente Akasha** fica inativa sem ele.

- **Instalação:** faz parte do HUB — nada a instalar à parte. Basta o HUB estar rodando (premissa do ecossistema).
- **Configuração:** automática via `ecosystem_client` (a URL de inferência vem do HUB). Os modelos por função são atribuídos no painel **LOGOS** do HUB; nada a configurar no `ecosystem.json` da AKASHA.

### Unpaywall — PDFs de acesso aberto (opcional)

Encontra a versão aberta de papers científicos por DOI (exige um e-mail, regra da API).

- **Instalação:** nada (API pública gratuita).
- **Configuração:** campo **Settings → E-mail Unpaywall** (`akasha.unpaywall_email`), lido em runtime por `config.get_unpaywall_email()`. Usado no download (`paper_download.py`) e no enriquecimento da busca de papers (`paper_search.py`). Vazio = Unpaywall indisponível (degrada graciosamente). O mesmo e-mail vai no "polite pool" da OpenAlex.

### qBittorrent — download via torrent (não implementado)

⚠️ A dependência `qbittorrent-api` está declarada e há defaults de host/porta em `config.py`, mas **nenhum código atual usa o qBittorrent**: os downloads são HTTP direto (`services/downloader.py`). Tratar como **planejado**, não funcional hoje.

Sem os serviços **opcionais**, o AKASHA continua funcionando como buscador (acervo local + web). Sem o **SearXNG**, a busca web cai para o DuckDuckGo (modo reduzido). Sem o **LOGOS**, só a assistente Akasha (reflexão/insights/chat) fica inativa.

---

## Rodando o SearXNG (Fedora · CachyOS · Windows 10)

O SearXNG é o backend **recomendado** para a busca web (agrega Google/Bing/Startpage/Marginalia/etc. em paralelo, sem rate limit e sem rastreamento). O AKASHA aponta para uma instância via `akasha.web_search_backend` no `ecosystem.json` — editável no **painel Busca do HUB**. Se o campo estiver vazio ou a instância offline, o AKASHA cai para o **DuckDuckGo** automaticamente.

> **Modelo de deployment.** O jeito mais simples é ter **uma** instância SearXNG na rede (num servidor sempre ligado) e todas as máquinas (Windows, CachyOS, laptop) apontarem para ela. É assim que o ecossistema roda hoje: uma instância no servidor Fedora (Dell T410) em `http://192.168.0.252:8080`, e cada app usa essa URL.
>
> **Fallback local:** rodar uma instância SearXNG **local** em cada máquina como fallback automático do servidor remoto está **planejado** (ver "AKASHA — SearXNG primário+fallback" no `TODO.md`), mas **ainda não implementado** — hoje o AKASHA usa **uma** URL (`web_search_backend`). Você pode apontá-la para o servidor remoto **ou** para uma instância local; as instruções por SO abaixo servem para os dois casos.

### Pré-requisitos comuns (qualquer instância)

Para o AKASHA consumir o SearXNG, o `settings.yml` da instância precisa de:

```yaml
search:
  formats:
    - html
    - json        # OBRIGATÓRIO — sem 'json' o AKASHA recebe HTTP 403
server:
  limiter: false  # evita bloqueio das requisições do AKASHA
  bind_address: "0.0.0.0"   # só se outras máquinas forem acessar (servidor de rede)
```

Depois, configure o AKASHA (painel **Busca** do HUB, ou direto no `ecosystem.json`):

```jsonc
"akasha": { "web_search_backend": "http://192.168.0.252:8080" }   // ou http://localhost:8080
```

Teste rápido (deve retornar JSON, não 403):
`curl "http://SEU_HOST:PORTA/search?q=teste&format=json"`

### Fedora (e Fedora Server — método recomendado: Docker)

É o método do servidor T410. Usa a stack oficial `searxng-docker` (SearXNG + Valkey/Redis):

```bash
sudo dnf install -y docker docker-compose-plugin
sudo systemctl enable --now docker
git clone https://github.com/searxng/searxng-docker.git ~/searxng && cd ~/searxng
# Edite searxng/settings.yml: gere um 'secret_key', adicione 'json' em search.formats,
# ponha server.limiter: false e (se for servir a rede) bind_address 0.0.0.0.
sudo docker compose up -d
```
A instância sobe na porta definida no compose (no T410: **8080**, HTTP, sem TLS). Reiniciar após editar config: `sudo docker restart searxng-core`. Settings de referência do T410: `core-config/settings.yml`.

### CachyOS / Arch

Duas opções:

- **Docker** (igual ao Fedora — recomendado p/ consistência): `sudo pacman -S docker docker-compose` e siga os passos do `searxng-docker` acima.
- **Script do projeto (sem Docker)**: `bash AKASHA/scripts/setup_searxng.sh` — clona o SearXNG, cria venv via `uv`, aplica `AKASHA/scripts/searxng_settings.yml`, registra um serviço **systemd --user** e sobe na porta **8888** (`http://localhost:8888`). Requer `git`, `uv` e systemd de usuário. *(A instalação antiga via `yay -S searxng-git` foi descontinuada.)*

### Windows 10 (via Docker Desktop)

O SearXNG não tem build nativo de Windows — roda em contêiner. Use o **Docker Desktop** (backend WSL2):

1. Instale o [Docker Desktop](https://www.docker.com/products/docker-desktop/) e habilite a integração WSL2.
2. No WSL2 (ou no PowerShell, com Docker no PATH):
   ```bash
   git clone https://github.com/searxng/searxng-docker.git && cd searxng-docker
   # edite searxng/settings.yml (secret_key, formats: + json, limiter: false)
   docker compose up -d
   ```
3. Aponte o AKASHA para `http://localhost:8080`.

> Na prática, no Windows costuma ser mais simples **apontar para o servidor SearXNG da rede** (`http://192.168.0.252:8080`) do que manter o Docker Desktop rodando localmente.

> ⚠️ As instruções de Docker acima seguem o fluxo padrão do `searxng-docker`; os passos exatos (nomes de arquivo/serviço, porta) podem variar conforme a versão — consulte o README do [searxng-docker](https://github.com/searxng/searxng-docker) se algo divergir.

### Fontes de busca (engines): quais habilitar e como

Nem todo engine do SearXNG funciona bem em uso automatizado — vários bloqueiam bots, retornam spam ou nada. A curadoria abaixo foi **validada por teste** (ver tabela completa no `GUIDE.md`). Os engines vivem em `settings.yml`, na seção `engines:`; cada um tem `disabled: true|false`:

```yaml
engines:
  - name: startpage
    disabled: false
  - name: duckduckgo
    disabled: true     # CAPTCHA permanente em automação
```

**Habilitar (validados, contribuem resultados):**

| Engine | Categoria | Por quê |
|--------|-----------|---------|
| **Startpage** | geral | Mais confiável; proxy do Google sem tracking |
| **Bing** | geral | Confiável; índice Microsoft |
| **Google** | geral | Bom volume (às vezes timeout/CAPTCHA sob uso intenso) |
| **mwmbl** | geral/indie | Índice **independente** (~500M URLs); não bloqueia o IP; traz resultados únicos que ~dobram a contagem em queries de nicho |
| **arXiv** | acadêmico | Artigos científicos |
| **Semantic Scholar** | acadêmico | Artigos acadêmicos |

**Desabilitar (não funcionam bem em automação):**

| Engine | Motivo |
|--------|--------|
| **DuckDuckGo** | CAPTCHA permanente / bloqueio por IP (`SearxEngineCaptchaException`). *(Ainda usado pelo AKASHA como **fallback final** via biblioteca própria — fora do SearXNG.)* |
| **Brave** | Rate limit agressivo (suspensão de ~180s) |
| **Qwant** | SEO spam em queries de nicho |
| **Yahoo** | Wrapper do Bing (redundante) + seletores instáveis |
| **Wikipedia / Wikidata** | 0 resultados nas queries testadas |
| **Mojeek** | Depende da rede: funciona em algumas, mas "access denied" para o IP do servidor T410 — deixe habilitado e veja se contribui; se vier 0, desabilite |

Após editar `settings.yml`, reinicie a instância (Docker: `docker restart searxng-core`).

### Marginalia (web indie/nicho) — configurada **direto no AKASHA**, não no SearXNG

A [Marginalia](https://marginalia-search.com) é o melhor engine para a "web pequena" (blogs, zines, ativismo, crafts — conteúdo sem SEO pesado), mas **não** dá para habilitar pelo SearXNG do servidor (lá ela está inativa e exige chave). O AKASHA a consulta **diretamente**, em paralelo ao SearXNG, mesclando via RRF.

- **Funciona sem chave:** usa a API pública (rate limit compartilhado; sob saturação retorna vazio sem quebrar a busca). Nada a fazer.
- **Chave própria (recomendado p/ uso frequente):** rate limit separado. Peça uma chave gratuita por e-mail a `contact@marginalia-search.com` e cole em **Settings → Marginalia API key** (campo `akasha.marginalia_api_key` no `ecosystem.json`). Vazio = usa a chave pública.

### Resumo do pipeline web

Por busca, o AKASHA consulta em paralelo: **SearXNG** (engines curados acima) **+ Marginalia** (direto) **+ mwmbl** (quando os outros vêm escassos), funde tudo via RRF e deduplica por URL. Se **nada** disso responder, cai para o **DuckDuckGo** (biblioteca `ddgs`) como último recurso. O **Stract** foi avaliado mas a API pública dele saiu do ar (2026-06-05) — não está em uso.

---

## Instalação e execução

### Pré-requisito: `uv`

O AKASHA usa o **`uv`** como gerenciador de pacotes — ele cria e mantém o venv próprio do AKASHA (`AKASHA/.venv`, Python 3.13) a partir do `pyproject.toml`. Instale o `uv` primeiro:

```bash
# Linux / CachyOS / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```
(Documentação: <https://docs.astral.sh/uv/getting-started/installation/>)

> **O AKASHA não roda isolado.** Ele importa o `ecosystem_client` da **raiz do ecossistema** (via `sys.path`, em `config.py` e outros). A pasta `AKASHA/` precisa permanecer **dentro do repositório do ecossistema** — não a mova para fora, ou o startup falha ao resolver `ecosystem_client`.

### Setup do ambiente (instalar dependências)

O ponto de entrada **oficial** de setup é o script `atualizar` na raiz do ecossistema, que roda `uv sync` para o AKASHA (e prepara os demais apps):

```bash
# Linux / CachyOS
bash atualizar.sh

# Windows
atualizar.bat
```
Alternativa só-AKASHA (dentro de `AKASHA/`): `uv sync --python 3.13`.

### Rodar

```bash
# Linux / CachyOS
bash iniciar.sh

# Windows (terminal ou duplo-clique no arquivo)
iniciar.bat
```
Os dois scripts rodam `uv sync` e sobem o servidor com `uv run python main.py`, abrindo `http://localhost:7071`. O servidor registra seu endereço no `ecosystem.json` automaticamente.

### Downloads de primeiro uso (exigem rede)

Algumas dependências baixam dados/modelos **na primeira vez que são usadas** — o `uv sync` instala o pacote, mas não esses recursos. Todos degradam graciosamente se faltarem (em uso offline, ficam indisponíveis até a primeira execução com rede):

- **NLTK `vader_lexicon`** — baixado automaticamente na primeira análise de sentimento (assistente Akasha).
- **Modelos locais de reranking (`flashrank`) e de embeddings (`sentence-transformers`)** — baixados do HuggingFace na primeira busca semântica/rerank local. *(São caminho de fallback: a busca semântica primária usa o LOGOS.)*
- **Pacotes de idioma do `argostranslate`** — necessários para tradução inline offline; sem eles, a tradução cai para o LibreTranslate (online).
