# AKASHA — Registros do Universo

> *ākāśa* (आकाश) — "espaço luminoso". O substrato invisível onde tudo existe, ressoa e persiste.  
> Os *Registros Akáshicos*: a biblioteca cósmica onde cada pensamento, palavra e ação está eternamente gravada.

Buscador pessoal local. Agrega resultados da web e do próprio ecossistema numa interface única, com biblioteca de URLs monitorada e arquivação de páginas. Roda como servidor Python acessado via browser — sem conta, sem nuvem, sem telemetria.

**Porta:** `7070`  
**Plataformas:** Windows 10 · CachyOS (Arch Linux)

---

## O que faz

### Busca web
- DuckDuckGo sem API key; cache local de 1h em SQLite
- Deduplicação por URL normalizada
- Histórico de buscas persistido

### Busca local
- Archive do KOSMOS (`archive_path/**/*.md`) — artigos salvos com frontmatter
- Vault do AETHER (`vault_path/*/chapters/*.md`) — capítulos escritos
- Index do Mnemosyne (ChromaDB) — documentos indexados, quando disponível
- Biblioteca de URLs (ver abaixo) — conteúdo scrapeado e versionado
- Resultados web e locais em **seções separadas** na mesma interface

### Arquivação de páginas
- Salva qualquer página como `.md` em `{archive_path}/Web/{YYYY-MM-DD}_{slug}.md`
- Frontmatter estendido: `title`, `source`, `date`, `author`, `url`, `language`, `word_count`, `tags`, `notes`
- Extração via `trafilatura`

### Biblioteca de URLs
- Adicione sites para monitoramento periódico (diário / semanal / mensal)
- Diff automático por `difflib.unified_diff` — só armazena o que mudou
- Metadados por entrada: idioma detectado, contagem de palavras, tags, notas editáveis inline
- Badge "mudou" quando há diff nos últimos 7 dias
- Background task: re-scrape automático a cada hora para URLs vencidas
- Conteúdo da biblioteca incluído na busca local (FTS5)

### Integração com o ecossistema
- Lê `ecosystem.json` para descobrir caminhos do KOSMOS, AETHER e Mnemosyne automaticamente
- Escreve `akasha.base_url` e `akasha.exe_path` em `ecosystem.json` no startup
- Páginas arquivadas vão direto para o archive do KOSMOS

---

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python + FastAPI (async) |
| Frontend | HTMX + Jinja2 (sem build step) |
| Banco local | SQLite via `aiosqlite` |
| Package manager | `uv` |
| Busca web | `duckduckgo-search` (AsyncDDGS) |
| Extração de conteúdo | `trafilatura` |
| Busca local | FTS5 (SQLite virtual table) + ChromaDB (opcional) |

---

## Estrutura

```
AKASHA/
├── main.py                  # FastAPI app + lifespan (init DB, registra no ecossistema, background task)
├── pyproject.toml           # dependências uv
├── config.py                # lê ecosystem.json; expõe kosmos_archive, aether_vault, etc.
├── database.py              # schema SQLite v5 + migrations
├── iniciar.sh               # script de inicialização (uv sync + uv run)
├── routers/
│   ├── search.py            # GET /search · POST /archive
│   └── library.py           # GET /library · POST /library/add · PATCH · DELETE · POST /refresh
├── services/
│   ├── web_search.py        # DuckDuckGo + cache SQLite
│   ├── local_search.py      # FTS5 (local_fts + library_fts) + ChromaDB opcional
│   ├── archiver.py          # fetch + trafilatura + frontmatter KOSMOS estendido
│   └── library.py           # add_url, scrape_and_store, check_overdue, compute_diff
├── templates/
│   ├── base.html            # topbar (busca HTMX, filtros web/local, nav, toggle tema)
│   ├── search.html          # resultados em seções separadas (web / ecossistema)
│   └── library.html         # biblioteca de URLs com filtros tag/idioma
└── static/
    └── style.css            # paleta "Atlas Astronômico à Meia-Noite" (#12161E)
```

---

## Design

Segue o design system do ecossistema definido em `DESIGN_BIBLE.txt`:

- **Paleta:** sépia diurna / "Atlas Astronômico à Meia-Noite" (`#12161E` base) para modo escuro
- **Tipografia:** IM Fell English (títulos, sempre itálico) · Special Elite (corpo, botões) · Courier Prime (código)
- **Border-radius:** 2px · sombras flat sem blur · animações máximo 300ms

---

## Rodar

```bash
# CachyOS / Linux
bash iniciar.sh
# acesse http://localhost:7070

# ou via função fish
akasha
```

```powershell
# Windows
bash iniciar.sh
# acesse http://localhost:7070
```

O script detecta o `.venv` compartilhado do ecossistema em `../`; se não existir, cria um local. Roda `uv sync` e inicia com `uv run python main.py`.

---

## Estado

**Implementado — Fases 1, 2, 3, 5 e 7.**

| Fase | Descrição | Estado |
|---|---|---|
| 1 | Fundação: servidor, design system, página de busca | ✅ |
| 2 | Busca web (DuckDuckGo + cache + histórico) | ✅ |
| 3 | Busca local (FTS5: KOSMOS + AETHER + ChromaDB opcional) | ✅ |
| 4 | Downloads com SSE | Não iniciada |
| 5 | Arquivação web (formato KOSMOS estendido) | ✅ |
| 6 | qBittorrent | Não iniciada |
| 7 | Biblioteca de URLs (scraping periódico + diff + FTS5) | ✅ |
| 8 | Histórico unificado (`/history`) | Não iniciada |
| 9 | Polimento e integração final | Não iniciada |

Ver [TODO.md](TODO.md) para o roadmap detalhado.
