# AKASHA — Registros do Universo

> *ākāśa* (आकाश) — "espaço luminoso". O substrato invisível onde tudo existe, ressoa e persiste.  
> Os *Registros Akáshicos*: a biblioteca cósmica onde cada pensamento, palavra e ação está eternamente gravada.

Buscador pessoal local. Agrega resultados da web e do próprio ecossistema numa interface única, com suporte a downloads genéricos e integração com qBittorrent. Roda como servidor Python acessado via browser — sem conta, sem nuvem, sem telemetria.

---

## O que faz

### Busca web
- Agrega resultados de múltiplos providers (DuckDuckGo por padrão, sem API key)
- Deduplicação e ranking unificado
- Providers adicionais opcionais: Google Custom Search, Bing (requerem chave)

### Busca local
- Archive do KOSMOS (`data/archive/*.md`) — artigos salvos com frontmatter
- Vault do AETHER (`{vault}/*/chapters/*.md`) — capítulos escritos
- Index do Mnemosyne (ChromaDB) — documentos indexados, quando disponível
- Busca unificada: web + local na mesma interface

### Downloads
- Arquivos genéricos: PDF, imagens, ZIPs, documentos — via `httpx` com barra de progresso em tempo real (SSE)
- Arquivar página web: salva como `.md` com frontmatter no formato do KOSMOS archive
- Vídeo/áudio: delega ao Hermes (não duplica o yt-dlp)
- Fila de downloads com histórico no SQLite local

### qBittorrent
- Conecta na instância local via `qbittorrent-api`
- Adicionar torrent por arquivo `.torrent` ou link magnet diretamente da interface
- Visualizar fila ativa: nome, progresso, velocidade de download/upload, ETA
- Configuração de host/porta na tela de setup (padrão: `localhost:8080`)

### Integração com o ecossistema
- Lê `ecosystem.json` para descobrir caminhos do KOSMOS, AETHER e Mnemosyne automaticamente
- Escreve `akasha.base_url` em `ecosystem.json` para que o HUB possa linkar
- Página arquivada → salva direto no archive do KOSMOS

---

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python + FastAPI (async) |
| Frontend | HTMX + Jinja2 (sem build step) |
| Banco local | SQLite via `aiosqlite` (histórico de buscas, fila de downloads) |
| Package manager | `uv` |
| Busca web | `duckduckgo-search` |
| Downloads | `httpx` |
| qBittorrent | `qbittorrent-api` |

**Porta padrão:** `7070`  
**Plataformas:** Windows 10 · CachyOS (Arch Linux)

---

## Estrutura planejada

```
AKASHA/
├── main.py                  # FastAPI app + startup
├── pyproject.toml           # dependências uv
├── config.py                # lê ecosystem.json
├── routers/
│   ├── search.py            # GET /search?q=...&sources=web,local
│   ├── downloads.py         # POST /download · GET /downloads (fila + SSE progresso)
│   └── qbittorrent.py       # GET /torrents · POST /torrents/add
├── services/
│   ├── web_search.py        # DuckDuckGo + providers opcionais
│   ├── local_search.py      # KOSMOS archive + AETHER vault + Mnemosyne
│   ├── downloader.py        # httpx com progresso via SSE
│   └── qbt_client.py        # wrapper qbittorrent-api
├── templates/
│   ├── base.html            # layout + design system do ecossistema
│   ├── search.html          # página de resultados unificados
│   └── downloads.html       # fila de downloads + histórico
└── static/
    ├── style.css            # paleta "Atlas Astronômico à Meia-Noite" (#12161E)
    └── app.js               # HTMX behaviors
```

---

## Design

Segue o design system do ecossistema definido em `DESIGN_BIBLE.txt`:

- **Paleta:** sépia diurna / "Atlas Astronômico à Meia-Noite" (`#12161E` base) para modo escuro
- **Tipografia:** IM Fell English (títulos, sempre itálico) · Special Elite (corpo, botões) · Courier Prime (código)
- **Border-radius:** 2px · sombras flat sem blur · animações máximo 300ms

---

## Integração no ecossistema

```json
{
  "akasha": {
    "base_url": "http://localhost:7070"
  }
}
```

O HUB pode usar `akasha.base_url` para abrir o AKASHA no browser padrão via `launch_app`.

---

## Estado

**Fase atual:** Planejamento — não iniciado.

Definições acordadas:
- [x] Nome: AKASHA
- [x] Stack: FastAPI + HTMX + SQLite + uv
- [x] Módulos: busca web, busca local, downloads, qBittorrent, integração ecossistema
- [x] Interface: app web local na porta 7070
- [ ] Implementação

---

## Rodar (quando implementado)

```bash
# CachyOS / Linux
cd AKASHA
uv run main.py
# acesse http://localhost:7070

# Windows
cd AKASHA
uv run main.py
```
