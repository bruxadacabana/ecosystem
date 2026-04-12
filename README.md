# Ecossistema — program files/

Conjunto de aplicativos pessoais, completamente locais, sem conta, sem nuvem, sem telemetria.
Desenvolvidos para CachyOS (Arch Linux) e Windows 10.

---

## Os apps

### AETHER — Forja de Mundos

Editor de escrita criativa para narrativas longas — livros, séries, fanfiction, worldbuilding.
Inspirado no Scrivener e no Ellipsus, mas completamente local.

- Vault portátil (pasta escolhida pelo usuário, formato JSON + Markdown)
- Binder com árvore Livros > Capítulos, CRUD, reordenação
- Editor WYSIWYG com auto-save, modo foco, modo typewriter
- Fichas de personagem, worldbuilding, linha do tempo
- Metas de palavras, sessões de escrita, streak diário, snapshots de capítulo
- Constelações animadas, folhas de papel caindo, tipografia do ecossistema

**Stack:** Rust (Tauri v2) · TypeScript + React + Vite  
**Estado:** Fases 0–5 completas. Vault format estável.

---

### OGMA — Grimório de Projetos

Gerenciador unificado de projetos, estudos e leituras. Cada projeto tem páginas com editor de blocos rico, propriedades customizáveis e um banco local que sincroniza opcionalmente com o Turso.

- Projetos do tipo criativo, técnico, estudo, leitura
- Editor de blocos com imagens, tabelas, checklists, código
- Tags, filtros, busca por texto
- Offline-first: funciona 100% local; Turso é opt-in

**Stack:** Electron · TypeScript + React + Vite · @libsql/client (Turso)  
**Estado:** Schema v2 em produção.

---

### KOSMOS — Ordem do Universo

Leitor e agregador de feeds RSS local. Suporta RSS genérico, YouTube, Tumblr, Substack, Mastodon e Reddit. Lê artigos, salva no archive em Markdown, exporta como PDF.

- Múltiplos tipos de feed com parsers dedicados
- Painel de leitura com WebEngine
- Archive de artigos em Markdown (`data/archive/`)
- Tradução offline opcional via Argos Translate

**Stack:** Python + PyQt6  
**Estado:** Funcional. Pronto para integração.

---

### Mnemosyne — Guardiã da Memória

Assistente local de documentos com RAG. Indexa uma pasta de arquivos (`.pdf`, `.docx`, `.txt`, `.md`), responde perguntas e gera resumos com modelos do Ollama — sem nenhum dado sair da máquina.

- Vectorstore local via ChromaDB (índice em `<pasta>/.mnemosyne/`)
- Seleção dinâmica de modelos detectados no Ollama
- Watcher de pasta: indexa novos arquivos automaticamente
- Hybrid retrieval BM25 + semântico

**Stack:** Python + PySide6 · LangChain · ChromaDB · Ollama  
**Estado:** Em desenvolvimento ativo.

---

### Hermes — Mensageiro

Utilitário de download e transcrição de vídeos. Baixa qualquer URL suportada pelo yt-dlp e transcreve o áudio em Markdown via Whisper.

- Aba Descarregar: inspeciona URL, lista formatos, suporta playlists
- Aba Transcrever: modelo Whisper configurável, idioma, limite de CPU
- Output salvo em pasta configurável; histórico de transcrições
- Workers em thread separada, log colorido em tempo real

**Stack:** Python + PyQt6 · yt-dlp · faster-whisper  
**Estado:** Fase 1 completa.

---

## Design

Todos os apps compartilham a mesma identidade visual, definida no [DESIGN_BIBLE.txt](DESIGN_BIBLE.txt).

**Metáfora:** biblioteca medieval de alquimia modernizada por um cartógrafo do século XIX que descobriu a astronomia. Papel envelhecido, tinta, mapas estelares, luminosidade dourada de vela.

**Paleta:** sépia diurna / "Atlas Astronômico à Meia-Noite" (`#12161E` base) para modo escuro. Nunca branco puro, nunca preto puro, nunca cores vibrantes.

**Tipografia — exatamente três fontes:**

| Fonte | Uso |
|---|---|
| IM Fell English | Títulos, conteúdo do editor, sempre itálico |
| Special Elite | Corpo, botões, labels, nunca itálico |
| Courier Prime | Código exclusivamente |

**Componentes:** `border-radius: 2px`, sombra flat sem blur, animações máximo 300ms.

---

## Princípios

**Local-first.** Nenhum app conecta a servidores externos sem ação explícita do usuário. Toda sincronização é opt-in.

**Tratamento de erros com tipagem é prioridade absoluta.**
- Rust: toda função falível retorna `Result<T, AppError>`. Zero `.unwrap()` em produção.
- TypeScript: `strict: true`. Erros tipados com discriminated unions. Nunca `any`.
- Python: `except ValueError` (específico), nunca `except Exception` genérico sem re-tipar.

**Cross-platform.** Todos os apps rodam em CachyOS e Windows 10. Paths via API da linguagem, nunca separadores hardcoded.

---

## Integração

O roteiro de integração dos apps — incluindo o HUB unificado e suporte Android — está em [ECOSYSTEM_TODO.md](ECOSYSTEM_TODO.md).

**Estado atual das fases:**

| Fase | Descrição | Estado |
|---|---|---|
| 0 | Fundação: `.ecosystem.json` + Syncthing | Não iniciada |
| 1 | Interligação dos apps existentes | Não iniciada |
| 2 | App Hub desktop (Tauri 2 + React) | Não iniciada |
| 3 | Android (APK via Tauri 2) | Não iniciada |
| 4 | Polimento e features extras | Não iniciada |

---

## Padrões de desenvolvimento

Ver [CONTRIBUTING.md](CONTRIBUTING.md) para as regras completas: workflow de commits, convenções de erro, design system e nomenclatura de apps.

**Venv Python compartilhado:** `.venv/` na raiz do ecossistema — os scripts `iniciar.sh` de cada app apontam para ele.
