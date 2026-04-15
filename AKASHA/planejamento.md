# AKASHA — Planejamento

> Documento de decisões arquiteturais e contexto de design.
> Criado: 2026-04-15

---

## Contexto

AKASHA é um buscador pessoal local — agrega resultados da web e do próprio ecossistema
numa interface única, com downloads genéricos e integração com qBittorrent. Roda como
servidor Python acessado via browser, na porta 7070.

Ainda não tem nenhum arquivo de código além do README.md de especificação.

---

## Stack e Decisões

| Camada | Tecnologia | Motivo |
|---|---|---|
| Backend | FastAPI (async) | Performance, tipagem nativa, SSE simples |
| Frontend | HTMX + Jinja2 | Sem build step; hypermedia puro; compatível com o ecossistema |
| Banco local | SQLite via `aiosqlite` | Leve, sem servidor, async com FastAPI |
| Package manager | `uv` | Padrão do ecossistema (substitui pip/venv) |
| Busca web | `duckduckgo-search` | Sem API key; fallback para outros providers opcional |
| Downloads | `httpx` | Async, streaming com progresso real |
| qBittorrent | `qbittorrent-api` | Wrapper oficial da API Web do qBittorrent |
| Extração web | `trafilatura` | Extrai conteúdo principal de páginas para arquivação |

**Porta padrão:** `7070`
**Plataformas:** Windows 10 · CachyOS (Arch Linux, compositor Niri + Fish)

---

## Integração com o Ecossistema

### ecosystem.json

O AKASHA lê e escreve em `~/.local/share/ecosystem/ecosystem.json` (Linux) /
`%APPDATA%\ecosystem\ecosystem.json` (Windows) via `ecosystem_client.py` (raiz do repo).

**Leitura** (caminhos descobertos automaticamente):
```python
eco = read_ecosystem()
kosmos_archive  = eco.get("kosmos", {}).get("archive_path", "")
aether_vault    = eco.get("aether", {}).get("vault_path", "")
mnemosyne_paths = eco.get("mnemosyne", {}).get("index_paths", [])
```

**Escrita** (no startup):
```python
write_section("akasha", {
    "base_url":  "http://localhost:7070",
    "exe_path":  str(Path(__file__).parent / "iniciar.sh"),
})
```

**Regra crítica:** toda integração com ecosystem.json em `try/except Exception: pass`
— nunca bloquear o startup do servidor.

### Seção no ecosystem.json

```json
{
  "akasha": {
    "base_url": "http://localhost:7070",
    "exe_path": "/home/spacewitch/Documents/program files/AKASHA/iniciar.sh"
  }
}
```

O HUB pode usar `akasha.base_url` para abrir o AKASHA no browser via `launch_app`.

---

## Design System

Segue o `DESIGN_BIBLE.txt` da raiz do ecossistema.

### Paleta

**Modo diurno — "Papel ao Sol da Manhã":**
```css
--paper:        #F5F0E8;   /* fundo principal */
--paper-dark:   #EDE7D9;   /* cards, sidebar */
--paper-darker: #E0D8C8;   /* sombras flat */
--ink:          #2C2416;   /* texto principal */
--ink-light:    #5C4E3A;   /* texto secundário */
--ink-ghost:    #8C7B6A;   /* texto terciário, placeholders */
--accent:       #b8860b;   /* dourado — botões, links, destaques */
--ribbon:       #8B3A2A;   /* vermelho — erros, perigo */
--accent-green: #4A6741;   /* verde — sucesso, confirmação */
--rule:         #D4C9B0;   /* bordas, divisores */
```

**Modo noturno — "Atlas Astronômico à Meia-Noite":**
```css
--paper:        #12161E;   /* fundo azul-noite */
--paper-dark:   #181D28;
--paper-darker: #1E2433;
--ink:          #E8DFC8;   /* pergaminho claro */
--ink-light:    #BFB49A;
--ink-ghost:    #7A7060;
--accent:       #D4A820;   /* dourado brilhante */
--ribbon:       #C45A40;   /* brasa */
--accent-green: #6A9B60;
--rule:         #2E3445;
```

### Tipografia

```css
--font-display: 'IM Fell English', Georgia, serif;   /* títulos, sempre itálico */
--font-mono:    'Special Elite', monospace;           /* corpo, botões, labels */
--font-code:    'Courier Prime', 'Courier New', monospace; /* código */
```

Carregadas via Google Fonts no `<head>` do `base.html`.

### Componentes

- **border-radius:** 2px padrão; pills (badges, tags): 20px
- **Sombras:** flat, sem blur — `box-shadow: 3px 3px 0 var(--paper-darker)`
- **Animações:** máximo 300ms, `ease-out`; `paperFall` para cards novos
- **Ícones:** Unicode puro — sem FontAwesome (`☽` `☀` `✓` `✕` `↗` `↓` `⚙`)

---

## Estrutura de Arquivos

```
AKASHA/
├── main.py                  # FastAPI app + lifespan
├── config.py                # lê ecosystem.json, expõe caminhos
├── database.py              # schema SQLite + migrations
├── pyproject.toml           # dependências uv
├── iniciar.sh               # script de inicialização (bash)
├── planejamento.md          # este arquivo
├── TODO.md                  # fases de implementação
├── README.md                # documentação pública
├── routers/
│   ├── __init__.py
│   ├── search.py            # GET /search, POST /archive
│   ├── downloads.py         # POST /download, GET /downloads, SSE progress
│   └── qbittorrent.py       # GET /torrents, POST /torrents/add
├── services/
│   ├── __init__.py
│   ├── web_search.py        # DuckDuckGo + cache SQLite
│   ├── local_search.py      # KOSMOS + AETHER + Mnemosyne (FTS5)
│   ├── downloader.py        # httpx async com progresso
│   ├── archiver.py          # fetch + trafilatura → .md KOSMOS format
│   └── qbt_client.py        # wrapper qbittorrent-api
├── templates/
│   ├── base.html            # layout + topbar + nav
│   ├── search.html          # página de resultados
│   ├── downloads.html       # fila de downloads + aba Torrents
│   └── settings.html        # configurações
└── static/
    ├── style.css            # design system completo
    └── app.js               # behaviors HTMX extras (mínimo)
```

---

## Fases de Implementação (resumo)

| Fase | Nome | Entrega |
|---|---|---|
| 1 | Fundação | Servidor na porta 7070, design system, busca vazia |
| 2 | Busca Web | DuckDuckGo funcional, cards, histórico |
| 3 | Busca Local | KOSMOS + AETHER + Mnemosyne integrados |
| 4 | Downloads | httpx async, barra de progresso SSE |
| 5 | Arquivação Web | Página → .md no format KOSMOS |
| 6 | qBittorrent | Fila de torrents gerenciável |
| 7 | Polimento | Production-ready, integrado no ecossistema |

Ver `TODO.md` para itens detalhados por fase.

---

## Aprovação prévia necessária

Conforme `CLAUDE.md` do ecossistema: nunca avançar para a próxima fase sem aprovação
explícita. Cada fase deve ser demonstrável antes de começar a seguinte.
