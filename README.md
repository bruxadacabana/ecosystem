# Ecossistema — Documentação Completa

Conjunto de aplicativos pessoais, completamente locais, sem conta, sem nuvem, sem telemetria.
Desenvolvidos para CachyOS (Arch Linux), Fedora e Windows 10.

> **Última atualização:** 2026-05-31
> Para manter este arquivo atualizado: toda mudança significativa de arquitetura, dependência ou funcionalidade deve ser refletida aqui na mesma resposta que implementa a mudança.

---

## Índice

1. [Visão geral](#1-visão-geral)
2. [Mapa do ecossistema](#2-mapa-do-ecossistema)
3. [Funcionalidades por programa](#3-funcionalidades-por-programa)
4. [Hardware e implicações](#4-hardware-e-implicações)
5. [Instalação do zero — CachyOS](#5-instalação-do-zero--cachyos)
6. [Instalação do zero — Fedora](#6-instalação-do-zero--fedora)
7. [Instalação do zero — Windows 10](#7-instalação-do-zero--windows-10)
8. [llama-cpp e llama-server](#8-llama-cpp-e-llama-server)
9. [Modelos recomendados por máquina](#9-modelos-recomendados-por-máquina)
10. [Configurar ecosystem.json](#10-configurar-ecosystemjson)
11. [Atualizar e rodar](#11-atualizar-e-rodar)
12. [Portas e serviços](#12-portas-e-serviços)
13. [Checklist de verificação](#13-checklist-de-verificação)

---

## 1. Visão geral

```
┌─────────────────────────────────────────────────────────────────┐
│                            HUB                                  │
│          Dashboard central · lança todos os outros apps         │
│                    porta 5173 (dev)                             │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                        LOGOS                            │   │
│   │   Proxy inteligente de LLM · gerencia prioridades P1/2/3│   │
│   │   ↕ llama-server (llama-cpp)  porta 7072 (proxy)        │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         │           │           │           │
         ▼           ▼           ▼           ▼
     AETHER       AKASHA     Mnemosyne    KOSMOS
   (escrita)    (pesquisa)  (notebook IA) (análise)
   Tauri/SvK    FastAPI/Py  PySide6/Py   PyQt6/Py
   porta 5174   porta 7071  (desktop)    (desktop)

         │           │
         ▼           ▼
       OGMA        Hermes
   (editor notas) (transcrição)
   Electron       Python+GUI
   porta 5175     (desktop)

Sync entre máquinas: Syncthing → sync_root
Inferência LLM: dois llama-servers paralelos — AKASHA :8081, Mnemosyne :8083 (internos, gerenciados pelo LOGOS) / 7072 (LOGOS proxy)
```

**Princípio fundamental:** tudo local. Nenhum dado sai da máquina. Nenhum serviço externo. Nenhuma conta.

---

## 2. Mapa do ecossistema

| Programa | Stack | Tipo | Porta | Função principal |
|----------|-------|------|-------|-----------------|
| **HUB** | Tauri 2 + SvelteKit + Rust | App desktop | 5173 (dev) | Dashboard central, LOGOS, lançador |
| **AETHER** | Tauri 2 + SvelteKit + Rust | App desktop | 5174 (dev) | Editor de escrita criativa e vault |
| **OGMA** | Electron + EditorJS | App desktop | 5175 (dev) | Editor de notas e documentos |
| **AKASHA** | FastAPI + Python + SQLite | Servidor HTTP | 7071 | Buscador e indexador de pesquisa |
| **Mnemosyne** | PySide6 + Python + ChromaDB | App desktop | — | Assistente RAG com notebooks |
| **KOSMOS** | PyQt6 + Python | App desktop | — | Análise de imagens, OCR, visão |
| **Hermes** | Python + GUI | App desktop | — | Transcrição e processamento de áudio |

---

## 3. Funcionalidades por programa

### HUB

O HUB está sempre aberto — é o centro do ecossistema. Nenhum outro app é iniciado diretamente; todos são lançados e monitorados pelo HUB.

**LOGOS (subprograma do HUB):**
- Proxy inteligente de LLM sobre o llama-server (llama-cpp) — expõe API OpenAI-compatível em porta 7072
- Sistema de filas com três prioridades e timeouts:
  - P1 (crítica, 120s timeout): chat interativo do HUB + escrita ativa no AETHER
  - P2 (importante, 60s timeout): buscas RAG no Mnemosyne
  - P3 (background, 30s timeout): pré-análise KOSMOS + transcrições Hermes
- Monitora VRAM da GPU e pausa tarefas P3 quando VRAM > 85%
- CPU/RAM guards: rejeita P3 quando CPU > 85% ou RAM livre < 1.5 GB
- Watchdog de processo: detecta crashes do llama-server e reinicia automaticamente (até 3x com backoff 10s/30s/60s); desabilita após 3 falhas consecutivas
- Captura stderr do chat-server em `log::warn!` + arquivo `logos_chat.log` com timestamp ISO
- Captura stderr do embed-server em `log::info!` + arquivo `logos_embed.log` com timestamp ISO
- Endpoints de diagnóstico: `GET /logos/logs/chat` e `GET /logos/logs/embed` (últimas 500 linhas, text/plain)
- OOM fallback: se modelo não carrega na GPU (timeout + exit prematuro), retenta com CPU only (`--n-gpu-layers 0`)
- Eventos críticos para frontend: `logos-alert` (nivel error/warn), `logos-llama-crashed`, `logos-llama-unavailable`
- Endpoint `POST /logos/log-level` para ajuste de verbosidade em runtime (debug/info/warn)
- Rotas: `/v1/chat/completions`, `/v1/embeddings`, `/v1/models` (OpenAI-compatível) e legado `/api/*`
- Logs archivados em `logs/archive/` após 7 dias; mantidos por 30 dias

**Painel de controle:**
- Lança, monitora e encerra todos os outros apps do ecossistema
- Gerencia o `ecosystem.json` — fonte de verdade para caminhos, modelos e configurações
- Painel Syncthing: visualiza estado da sincronização entre máquinas
- Monitor de VRAM / GPU em tempo real
- Gerenciador de perfis LLM: define qual modelo usar para chat, RAG, análise e embedding
- Chat direto com LLM (via LOGOS, P1)

**Lançador de modelos:**
- Inicia/para o llama-server com o modelo selecionado
- Verifica saúde via `GET /health`
- Lista modelos disponíveis via `GET /v1/models`

---

### AETHER

Editor de escrita criativa com vault local de capítulos e cenas.

**Funcionalidades:**
- Editor de texto rico focado em escrita narrativa (capítulos, cenas, personagens)
- Vault local organizado por projeto/capítulo/cena
- Modo de foco com minimização de distrações
- Histórico de versões local (por arquivo)
- Exportação para formatos comuns
- Integração com LOGOS (P1) para assistência à escrita — sugestões, continuações, reformulações
- Sincronizado via Syncthing entre máquinas

**Isolamento de dados:**
O vault do AETHER é privado — nunca indexado pelo AKASHA ou Mnemosyne. Apenas o OGMA pode acessar esses dados quando necessário.

---

### OGMA

Editor de notas e documentos com suporte a blocos ricos (EditorJS).

**Funcionalidades:**
- Editor baseado em blocos (EditorJS): texto, cabeçalhos, listas, código, imagens, tabelas
- Notas locais em SQLite via `better-sqlite3`
- Busca full-text nas notas
- Foco automático de janela (via `xdotool` no Linux)
- Organização por tags e coleções
- Exportação para Markdown

**Stack:** Electron (não Tauri) — usa Node.js nativo para acesso ao sistema de arquivos.

---

### AKASHA

Buscador e amplificador de pesquisa. O LLM age **apenas** na camada de query — nunca sintetiza nem gera resposta. O AKASHA devolve links, trechos e documentos; a usuária pensa.

**Duas camadas independentes:**

*AKASHA (ferramenta)* — funciona 100% sem LLM:
- Indexação de páginas web e documentos locais (SQLite FTS5 + embeddings)
- Crawler de domínios com agendamento e atualização (freshness)
- Biblioteca unificada: gerencia sites e documentos numa única seção
- Busca híbrida: FTS5 (BM25) + busca vetorial via LOGOS (`embed_and_index` em `services/local_search.py` — gera embedding pelo LOGOS `/v1/embeddings` e insere em sqlite-vec)
- Busca web via SearXNG self-hosted (agrega Google, Bing, Brave, DDG, Startpage) com fallback DDG; fetch paralelo de múltiplas páginas (padrão 4 × 25 resultados); script de instalação em `AKASHA/scripts/setup_searxng.sh`
- Classificador de intenção afeta **apresentação** dos resultados, nunca a quantidade
- Diversificação por domínio configurável (`max_per_domain`, padrão 5); filtragem de páginas vazias (`word_count < 50`)
- Qualidade de extração: fallback newspaper4k, pré-filtro de páginas de navegação (razão texto-link), detecção de paywall, sinalização de SPAs (`requires_js`)
- Busca semântica com fallback de latência para hardware sem AVX2 (i5-3470): `_vector_too_slow` desativa KNN automáticamente
- Cache de resultados, facetas, ranking
- Extensão de browser para pesquisa contextual

*Akasha (assistente)* — usa LLM quando disponível, falha gracefully se offline:
- Personalidade e memória próprias (tabela `personal_memory` isolada em `akasha.db`)
- Query understanding: classificação de intenção, expansão de termos, reescrita conversacional, expansão multilíngue via LOGOS (`?lang=auto|pt|en|…`; chips de idioma na UI; seletor integrado a SearXNG)
- Reflection loop: reflexões periódicas sobre sessões de pesquisa
- Geração de insights a partir do padrão de uso
- Envio de insights para a Mnemosyne via protocolo `friendship` (comunicação bidirecional)
- **`GET /search/structured`** — schema JSON padronizado para handoff com a Mnemosyne (Collab 2): retorna `url`, `title`, `snippet`, `domain`, `date`, `relevance_score` (0–1), `source_type` ("web"|"library"|"paper"|"local"); a Mnemosyne usa esse endpoint no fallback automático de RAG
- **Deep Research com critério de novidade** — `/chat` em modo deep usa dois rounds de busca; round 2 (expansão) só é incluído se a fração de URLs novas ≥ `novelty_threshold` (padrão 20%); saturação é logada e round 2 descartado automaticamente quando o corpus já é diverso o suficiente

**Porta:** 7071 (FastAPI)

---

### Mnemosyne

Assistente RAG pessoal organizada em **notebooks** temáticos. Cada conversa é um notebook — sempre salvo automaticamente, persistente entre sessões.

**Notebooks:**
- Cada notebook tem tema e pode filtrar quais coleções de documentos consulta
- Histórico em `history.jsonl` (append-only), metadados em `metadata.json`
- Memória de contexto RAG por notebook em `memory.json`
- Studio outputs (análises geradas) salvos como `.md` com `source: mnemosyne_studio`

**RAG multi-coleção:**
- Consulta todas as coleções habilitadas simultaneamente via `MultiVectorstore` (ChromaDB)
- Indexação de documentos locais: PDF, EPUB, Markdown, texto, imagens (via OCR/visão)
- Indexação de páginas web por sessão (`SessionIndexer` — in-memory, efêmero)
- RAPTOR index para documentos longos (sumarização hierárquica)
- BM25 (Okapi) + embeddings vetoriais — busca híbrida com re-ranking

**Studio (aba Análise):**
- Galeria de tiles persistentes (outputs anteriores sempre visíveis)
- Tipos: Resumo, FAQ, Mapa Mental, Guia de Estudos, Infográfico, Flashcards, Slides, Relatório, Cronograma, Briefing, Tabelas, Sumário (TOC), Blogpost, Guide
- Gerados via `ChatOpenAI` com `base_url` apontando ao LOGOS

**Sistema de personalidade e pop-ups:**
- Personalidade e memória pessoal em `personal_memory.db` (isolado do RAG)
- `InsightScheduler` + `InsightPopup`: pop-ups proativos no canto da tela, sem timeout de fechamento
- Feedback nos pop-ups (✓ / ✗ / comentário) — molda comportamento futuro
- Recebe insights da AKASHA via `friendship_receiver` (endpoint `POST /friendship/insight`)

**LLM:** via `ChatOpenAI` → LOGOS (`base_url=http://127.0.0.1:7072/v1`, `api_key="logos"`)
**Embeddings:** via `_InferenceEmbeddings` → `/v1/embeddings`

---

### KOSMOS

Análise de imagens com visão computacional e OCR local.

**Funcionalidades:**
- OCR de imagens e PDFs (via llama-server com modelo de visão)
- Análise de conteúdo visual (descrever, classificar, extrair texto estruturado)
- Processamento em lote (queue de imagens)
- Pré-análise em background (P3 no LOGOS) — não bloqueia interface
- Exportação de resultados

**LLM de visão:** envia imagens em base64 via API OpenAI multimodal (`/v1/chat/completions` com `content` como array de objetos `text` + `image_url`)

---

### Hermes

Transcrição e processamento de áudio local.

**Funcionalidades:**
- Transcrição de arquivos de áudio (MP3, WAV, M4A, OGG...)
- Transcrição em tempo real (microfone)
- Identificação de falantes (diarização)
- Extração de receitas e informações estruturadas de áudio (via LLM)
- Exportação de transcrições em texto e SRT
- Output salvo em `hermes.output_dir` (configurável via `ecosystem.json`)

---

### logos/ (scripts de fine-tuning)

Scripts para geração de dados de treino e fine-tuning local (diretório `logos/`, não confundir com o LOGOS do HUB).

- `training_data_generator.py`: gera pares Q&A via LLM para datasets de fine-tuning
- `finetune_scheduler.py`: agendador de execuções de fine-tuning
- `gguf_converter.py`: converte modelos para formato GGUF (llama.cpp)

---

## 4. Hardware e implicações

### CachyOS — computador principal

| Item | Especificação |
|------|---------------|
| CPU | AMD Ryzen 5 4600G |
| RAM | 16 GB |
| GPU | AMD Radeon RX 6600, RDNA2, 8 GB VRAM (gfx1032) |
| OS | CachyOS (Arch Linux), Niri + Fish shell |
| Armazenamento | ~2 TB (3 SSDs) |

**Implicações:**
- GPU AMD requer ROCm com `HSA_OVERRIDE_GFX_VERSION=10.3.0` para inferência em GPU
- 8 GB VRAM suporta modelos até ~7B em Q4 com conforto, ou ~13B com offload parcial
- llama-server com ROCm: compilar com `-DGGML_ROCM=ON` ou usar build pré-compilado ROCm
- Fish shell: usar `set -x VAR valor` em vez de `export VAR=valor`

### Fedora — laptop (Lenovo Ideapad 330-15IKB)

| Item | Especificação |
|------|---------------|
| CPU | Intel Core i7-8550U (8 threads, 4.00 GHz) — **tem AVX2** |
| RAM | 11.58 GiB |
| GPU discreta | NVIDIA GeForce MX150, 2 GB VRAM |
| GPU integrada | Intel UHD Graphics 620 (Optimus/híbrido) |
| OS | Fedora 44, kernel 7.0.9, Niri + Fish shell |
| Tela | 1920×1080, 15", 60 Hz |

**Implicações:**
- CUDA via MX150 — não usar `HSA_OVERRIDE_GFX_VERSION` (isso é só AMD/ROCm)
- VRAM = 2 GB: limite real de modelos
  - Viável: SmolLM2 1.7B Q4 (~1 GB), Gemma 2B Q4 (~1.5 GB)
  - Inviável em GPU: Phi-3 mini 4B, Llama 8B → usam CPU (aquecimento elevado)
- llama-cpp com CUDA: compilar com `-DGGML_CUDA=ON`
- Em bateria: LOGOS deve reduzir indexação (a implementar)
- AVX2 disponível — builds padrão do llama-cpp funcionam

### Windows 10 — computador de trabalho

| Item | Especificação |
|------|---------------|
| CPU | Intel Core i5-3470, Ivy Bridge 2012, 4 cores/4 threads, 3.2 GHz — **sem AVX2** |
| RAM | 8 GB |
| GPU | Intel HD Graphics integrada (32 MB dedicados — inútil para ML) |
| OS | Windows 10 x64 |

**Implicações:**
- **Sem AVX2** — builds padrão do llama-cpp vão crashar com SIGILL
  - Obrigatório: compilar com `-DLLAMA_AVX2=OFF -DLLAMA_AVX=ON -DLLAMA_F16C=OFF -DLLAMA_FMA=OFF`
  - Ou baixar build pré-compilado "noavx" do llama.cpp releases
- Sem GPU útil para ML — toda inferência no CPU, muito lento
- 8 GB RAM: modelos viáveis ≤ 3B em Q4 (~2-3 GB)
- Recomendado: usar apenas para embedding leve (ex: nomic-embed-text)
- Indexação pesada: fazer no CachyOS e sincronizar vectorstore via Syncthing
- Modelos de embedding pesados (ex: bge-m3) saturam o CPU e travam o sistema

---

## 5. Instalação do zero — CachyOS

### 5.1. Dependências de sistema

```bash
# Base + compiladores
sudo pacman -S base-devel cmake pkg-config openssl git

# Tauri (obrigatório para HUB e AETHER)
sudo pacman -S webkit2gtk-4.1 libayatana-appindicator

# SearXNG (backend de busca do AKASHA — opcional mas recomendado)
# Instalação automatizada via script (requer git e uv):
bash AKASHA/scripts/setup_searxng.sh
# Instala em ~/.local/share/searxng, configura ~/.config/searxng/settings.yml,
# cria serviço systemd --user e inicia na porta 8888.
# Configurar no AKASHA: ecosystem.json["akasha"]["web_search_backend"] = "http://localhost:8888"

# Python
sudo pacman -S python python-pip

# Utilitários
sudo pacman -S xdotool sqlite

# ROCm (para llama-server com GPU AMD)
sudo pacman -S rocm-hip-sdk rocm-opencl-sdk
# Ou via AUR: paru -S rocm-llvm rocm-hip-sdk
```

### 5.2. Rust

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Fish shell: adicionar ao PATH
fish_add_path ~/.cargo/bin
# (ou abrir novo terminal)

# Verificar
rustc --version    # 1.77+
cargo --version

# Tauri CLI
cargo install tauri-cli --version "^2"
cargo tauri --version
```

### 5.3. Node.js 22+

```bash
# Via fnm (recomendado — funciona em Fish)
curl -fsSL https://fnm.vercel.app/install | bash
# Abrir novo terminal, depois:
fnm install 22
fnm use 22
fnm default 22

# Verificar
node --version    # v22.x.x
npm --version

# Alternativa direta
sudo pacman -S nodejs npm
```

### 5.4. Python + uv

```bash
# uv (gerenciador de ambientes Python moderno)
curl -LsSf https://astral.sh/uv/install.sh | sh
# Abrir novo terminal ou:
fish_add_path ~/.local/bin

uv --version

# Python (geralmente já instalado no CachyOS)
python3 --version    # 3.11+
```

### 5.5. Fontes

```bash
# Nerd Fonts (ícones usados na UI)
sudo pacman -S ttf-nerd-fonts-symbols
# Ou instalar via AUR a família específica (ex: JetBrainsMono Nerd Font):
paru -S ttf-jetbrains-mono-nerd

# Fontes sans-serif usadas no ecossistema
sudo pacman -S ttf-liberation noto-fonts
```

### 5.6. llama-server com ROCm (GPU AMD RX 6600)

Ver seção [8. llama-cpp e llama-server](#8-llama-cpp-e-llama-server).

```bash
# Variável obrigatória para RX 6600 (gfx1032)
set -x HSA_OVERRIDE_GFX_VERSION 10.3.0   # Fish
# export HSA_OVERRIDE_GFX_VERSION=10.3.0  # bash

# Adicionar ao config do Fish para persistir:
echo 'set -x HSA_OVERRIDE_GFX_VERSION 10.3.0' >> ~/.config/fish/config.fish
```

### 5.7. Clonar e instalar

```bash
git clone <url-do-repo> "program files"
cd "program files"

# Instalar todas as dependências
bash atualizar.sh
```

---

## 6. Instalação do zero — Fedora

### 6.1. Dependências de sistema

```bash
# Compiladores e ferramentas base
sudo dnf group install development-tools c-development
sudo dnf install cmake pkg-config openssl-devel git

# Tauri (obrigatório para HUB e AETHER)
sudo dnf install webkit2gtk4.1-devel libappindicator-gtk3-devel

# Python build deps
sudo dnf install python3-devel

# Utilitários
sudo dnf install xdotool sqlite sqlite-devel

# SearXNG (backend de busca do AKASHA — opcional mas recomendado)
# Instalar via pip em virtualenv, ou clonar o repositório:
#   git clone https://github.com/searxng/searxng && cd searxng && pip install -e .
# Iniciar: python -m searxng.webapp (porta padrão 8888)
# Configurar no AKASHA: ecosystem.json["akasha"]["web_search_backend"] = "http://localhost:8888"

# CUDA (para llama-server com GPU MX150)
# Via repositório RPM Fusion ou instalador NVIDIA:
sudo dnf install https://developer.download.nvidia.com/compute/cuda/repos/fedora$(rpm -E %fedora)/x86_64/cuda-repo-fedora$(rpm -E %fedora)-12-x86_64.rpm
sudo dnf install cuda-toolkit
```

### 6.2. Rust

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

rustc --version
cargo --version

cargo install tauri-cli --version "^2"
cargo tauri --version
```

### 6.3. Node.js 22+

```bash
# Via fnm (recomendado)
curl -fsSL https://fnm.vercel.app/install | bash
# Novo terminal, depois:
fnm install 22
fnm use 22
fnm default 22

node --version
npm --version

# Alternativa direta
sudo dnf install nodejs22
```

### 6.4. Python + uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env    # ou abrir novo terminal

uv --version
python3 --version    # 3.11+
```

### 6.5. Fontes

```bash
# RPM Fusion free (necessário para muitas fontes)
sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm

# Fontes base
sudo dnf install liberation-fonts google-noto-fonts-common

# Nerd Fonts: baixar manualmente em https://www.nerdfonts.com/font-downloads
# Extrair para ~/.local/share/fonts/ e rodar: fc-cache -fv
```

### 6.6. llama-server com CUDA (GPU MX150 2 GB)

Ver seção [8. llama-cpp e llama-server](#8-llama-cpp-e-llama-server).

```bash
# CUDA_VISIBLE_DEVICES=0 para selecionar MX150 se Optimus causar problemas
export CUDA_VISIBLE_DEVICES=0
```

### 6.7. Clonar e instalar

```bash
git clone <url-do-repo> "program files"
cd "program files"
bash atualizar.sh
```

---

## 7. Instalação do zero — Windows 10

### 7.1. Pré-requisitos de sistema

```
1. Visual Studio Build Tools 2022
   → https://visualstudio.microsoft.com/visual-cpp-build-tools/
   → Marcar: "Desenvolvimento para desktop com C++"

2. Visual C++ Redistributable 2022
   → https://aka.ms/vs/17/release/vc_redist.x64.exe

3. Git para Windows
   → https://git-scm.com/download/win
   → Marcar "Add Git to PATH" durante instalação

4. WebView2 Runtime (para Tauri)
   → Geralmente já instalado no Windows 10 atualizado
   → Se não: https://developer.microsoft.com/microsoft-edge/webview2/

5. SearXNG (opcional — backend de busca do AKASHA)
   → Requer Python 3.11+. Instalar via: pip install searxng
   → Ou clonar: git clone https://github.com/searxng/searxng
   → Iniciar: python -m searxng.webapp (porta 8888)
   → Nota: no Windows 10 com 8 GB RAM, rodar SearXNG pode consumir ~300–500 MB.
     Alternativa: usar DDG como fallback (padrão quando web_search_backend está vazio).
```

### 7.2. Rust

```powershell
# Baixar e executar rustup-init.exe
# → https://rustup.rs
# Selecionar opção 1 (default)

# Abrir novo terminal, verificar:
rustc --version
cargo --version

# Tauri CLI
cargo install tauri-cli --version "^2"
cargo tauri --version
```

### 7.3. Node.js 22+

```
Baixar instalador LTS v22 em: https://nodejs.org
Marcar "Automatically install necessary tools" durante a instalação.

Verificar (no PowerShell ou cmd):
node --version    → v22.x.x
npm --version
```

### 7.4. Python + uv

```powershell
# Python — se não estiver instalado
# → https://python.org → Download Python 3.12
# → Marcar "Add Python to PATH" durante instalação
python --version    # 3.11+

# uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# Abrir novo terminal:
uv --version
```

### 7.5. Fontes

```
Nerd Fonts: https://www.nerdfonts.com/font-downloads
→ Baixar família desejada (ex: JetBrainsMono)
→ Extrair, selecionar todos os .ttf, botão direito → Instalar para todos os usuários

Liberation Fonts: https://github.com/liberationfonts/liberation-fonts/releases
→ Baixar o .zip, extrair e instalar os .ttf
```

### 7.6. llama-server sem AVX2 (i5-3470)

Ver seção [8. llama-cpp e llama-server](#8-llama-cpp-e-llama-server).

**ATENÇÃO:** O i5-3470 (Ivy Bridge, 2012) não suporta AVX2. Binários padrão vão crashar.

```
Opção A — build pré-compilado "noavx":
→ https://github.com/ggml-org/llama.cpp/releases
→ Procurar "llama-*-bin-win-noavx-x64.zip"
→ Extrair, usar llama-server.exe diretamente

Opção B — compilar manualmente:
No Developer Command Prompt (Visual Studio):
cmake .. -DLLAMA_AVX2=OFF -DLLAMA_AVX=ON -DLLAMA_F16C=OFF -DLLAMA_FMA=OFF
cmake --build . --config Release
```

### 7.7. Clonar e instalar

```powershell
git clone <url-do-repo> "program files"
cd "program files"

# Rodar o instalador
.\atualizar.bat
```

### 7.8. Variáveis de ambiente no Windows

```
Painel de Controle → Sistema → Configurações avançadas do sistema
→ Variáveis de Ambiente

Adicionar (usuário):
ECOSYSTEM_ROOT    C:\caminho\para\sync_root
```

---

## 8. llama-cpp e llama-server

O llama-server é o backend de inferência LLM de todo o ecossistema. Substitui o Ollama. Expõe API OpenAI-compatível.

**Endpoints expostos:**
- `GET  /health` — verificação de saúde
- `POST /v1/chat/completions` — geração de texto (stream SSE ou completo)
- `POST /v1/embeddings` — embeddings vetoriais
- `GET  /v1/models` — lista modelos carregados

**Portas:**
- `8081` — llama-server AKASHA (gerenciado pelo LOGOS, porta interna)
- `8083` — llama-server Mnemosyne (gerenciado pelo LOGOS, porta interna)
- `7072` — via LOGOS (proxy com fila de prioridades)

### Compilar do zero

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
mkdir build && cd build

# CachyOS com ROCm (AMD RX 6600):
cmake .. -DGGML_ROCM=ON -DCMAKE_HIP_COMPILER=$(hipconfig --hipclangpath)/clang++
cmake --build . --config Release -j$(nproc)

# Fedora com CUDA (NVIDIA MX150):
cmake .. -DGGML_CUDA=ON
cmake --build . --config Release -j$(nproc)

# CPU puro com AVX2 (qualquer Linux com AVX2):
cmake ..
cmake --build . --config Release -j$(nproc)

# CPU sem AVX2 (Windows i5-3470 / máquinas antigas):
cmake .. -DLLAMA_AVX2=OFF -DLLAMA_AVX=ON -DLLAMA_F16C=OFF -DLLAMA_FMA=OFF
cmake --build . --config Release
```

### Iniciar o llama-server

```bash
# CachyOS — com ROCm
HSA_OVERRIDE_GFX_VERSION=10.3.0 ./build/bin/llama-server \
  --model /path/to/model.gguf \
  --host 127.0.0.1 --port 8081 \
  --n-gpu-layers 999 \
  --ctx-size 4096

# Fedora — com CUDA
./build/bin/llama-server \
  --model /path/to/model.gguf \
  --host 127.0.0.1 --port 8081 \
  --n-gpu-layers 999 \
  --ctx-size 2048    # MX150 tem só 2 GB

# Windows — CPU puro (noavx)
.\llama-server.exe \
  --model C:\models\model.gguf \
  --host 127.0.0.1 --port 8081 \
  --n-gpu-layers 0 \
  --ctx-size 2048

# Nota: o LOGOS gerencia o processo llama-server automaticamente.
# Iniciar manualmente só é necessário para debug sem o HUB.
```

### Gerenciar arquivos GGUF

```bash
# Baixar modelos via Hugging Face CLI
pip install huggingface_hub
huggingface-cli download \
  bartowski/Qwen2.5-7B-Instruct-GGUF \
  Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  --local-dir ~/models/

# Verificar se carregou corretamente:
curl http://localhost:8081/v1/models
```

---

## 9. Modelos recomendados por máquina

### CachyOS — RX 6600 8 GB VRAM

| Função | Modelo | Tamanho | VRAM |
|--------|--------|---------|------|
| Chat/RAG | Qwen2.5-7B-Instruct Q4_K_M | ~4.4 GB | ~5 GB |
| Embedding | nomic-embed-text-v1.5 Q8 | ~274 MB | ~0.3 GB |
| Embedding pesado | bge-m3 Q8 | ~567 MB | ~0.6 GB |
| Visão/OCR | Qwen2-VL-7B-Instruct Q4_K_M | ~4.5 GB | ~5 GB |
| Análise longa | Llama-3.1-8B-Instruct Q4_K_M | ~4.7 GB | ~5.5 GB |

### Fedora — MX150 2 GB VRAM

| Função | Modelo | Tamanho | VRAM |
|--------|--------|---------|------|
| Chat (GPU) | SmolLM2-1.7B-Instruct Q4_K_M | ~1.0 GB | ~1.2 GB |
| Chat (GPU) | Gemma-2-2B-Instruct Q4_K_M | ~1.5 GB | ~1.8 GB |
| Embedding | nomic-embed-text-v1.5 Q4 | ~135 MB | ~0.2 GB |
| Chat maior (CPU) | Qwen2.5-3B-Instruct Q4_K_M | ~1.9 GB | CPU |

### Windows 10 — i5-3470, sem GPU (CPU puro)

| Função | Modelo | Tamanho | Notas |
|--------|--------|---------|-------|
| Embedding | nomic-embed-text-v1.5 Q4 | ~135 MB | Leve, viável |
| Embedding | all-minilm-l6-v2 | ~22 MB | Muito leve |
| Chat (lento) | SmolLM2-1.7B-Instruct Q4_K_M | ~1.0 GB | Funciona, lento |
| Chat (evitar) | Qualquer 7B+ | — | Trava a máquina |

**Recomendação para Windows 10:** Usar apenas para embeddings. Fazer indexação e inferência pesada no CachyOS e sincronizar via Syncthing.

---

## 10. Configurar ecosystem.json

O HUB cria e gerencia o `ecosystem.json` automaticamente na primeira execução. Se precisar criar manualmente:

```bash
# Linux
cp ecosystem.local.example.json ~/.local/share/ecosystem/ecosystem.json

# Windows
copy ecosystem.local.example.json %APPDATA%\ecosystem\ecosystem.json
```

### Exemplo de ecosystem.json

```json
{
  "sync_root": "/home/spacewitch/Documents/ecosystem_root",
  "logos": {
    "port": 7072,
    "llama_server_url": "http://localhost:8081",
    "active_profile": "default"
  },
  "profiles": {
    "default": {
      "llm_chat": "qwen2.5-7b-instruct",
      "llm_rag": "qwen2.5-7b-instruct",
      "llm_analysis": "qwen2.5-7b-instruct",
      "llm_query": "qwen2.5-7b-instruct",
      "embed": "nomic-embed-text-v1.5"
    }
  },
  "aether": {
    "vault_dir": "/home/spacewitch/Documents/ecosystem_root/aether"
  },
  "akasha": {
    "personality_prompt": "...",
    "data_dir": "/home/spacewitch/.local/share/akasha"
  },
  "mnemosyne": {
    "watched_dir": "/home/spacewitch/Documents",
    "data_dir": "/home/spacewitch/.local/share/mnemosyne",
    "personality_prompt": "..."
  },
  "hermes": {
    "output_dir": "/home/spacewitch/Documents/ecosystem_root/hermes"
  },
  "ogma": {
    "data_dir": "/home/spacewitch/.local/share/ogma"
  }
}
```

**Campos importantes:**
- `sync_root` — pasta raiz do Syncthing (compartilhada entre máquinas)
- `logos.llama_server_url` — URL do llama-server direto (fallback se LOGOS cair)
- `profiles.*.llm_*` — modelo a usar por função (lido em runtime por cada app)
- `profiles.*.embed` — modelo de embedding (lido em runtime)
- Nunca hardcodar caminhos ou URLs nos apps — sempre via `ecosystem_client`

**Caminhos do sync_root por máquina:**
- CachyOS: `/home/spacewitch/Documents/ecosystem_root`
- Windows 10: a definir após configuração do Syncthing
- Fedora/laptop: a definir após configuração do Syncthing

---

## 11. Atualizar e rodar

### Atualizar tudo (após clonar ou após pull)

```bash
# Linux
bash atualizar.sh

# Windows
.\atualizar.bat
```

O que o script faz:
- `git pull`
- `uv sync` (AKASHA, KOSMOS)
- cria `.venv` compartilhado e instala Mnemosyne + Hermes
- `npm install` (AETHER, HUB, OGMA)

### Iniciar apps individualmente

```bash
# AKASHA (servidor FastAPI)
cd AKASHA && bash iniciar.sh   # Linux
cd AKASHA && iniciar.bat       # Windows

# Mnemosyne (app desktop PySide6)
cd Mnemosyne && bash iniciar.sh

# HUB (dev mode — Tauri + Vite)
cd HUB && npm run tauri dev

# AETHER (dev mode)
cd AETHER && npm run tauri dev

# OGMA (Electron dev)
cd OGMA && npm run dev

# KOSMOS (PyQt6)
cd KOSMOS && bash iniciar.sh

# Hermes (Python)
cd Hermes && bash iniciar.sh
```

### Buildar para produção

```bash
# Buildar tudo
bash buildar.sh

# Buildar app específico
bash buildar.sh hub
bash buildar.sh aether
bash buildar.sh ogma

# Outputs:
# AETHER/src-tauri/target/release/bundle/appimage/   (.AppImage Linux)
# AETHER/src-tauri/target/release/bundle/deb/        (.deb)
# HUB/src-tauri/target/release/bundle/appimage/
# OGMA/dist/
```

### Rodar testes

```bash
# AKASHA (venv próprio — aiosqlite + FastAPI)
cd AKASHA && uv run pytest tests/ -v

# Mnemosyne (venv compartilhado em program files/.venv)
.venv/bin/pytest Mnemosyne/tests/ -v

# Ecosystem cross-app (ecosystem_client, contrato LOGOS /v1/embeddings)
.venv/bin/pytest tests/ -v

# HUB (Rust)
cd HUB/src-tauri && cargo test
```

**Cobertura por módulo:**
- AKASHA: FTS5/RRF, embeddings, API, recovery (degradação graciosa), amizade AKASHA↔Mnemosyne
- Mnemosyne: bootstrap, embeddings LOGOS, sync AKASHA, limpeza pré-indexação
- HUB/Rust: toggle_inference, models_dir fallback, spawn flags, apply_sync_root, ecosystem.json write/read
- Cross-app: contrato /v1/embeddings, get_inference_url, recovery E2E LOGOS offline

---

## 12. Portas e serviços

| Porta | Serviço | Notas |
|-------|---------|-------|
| 5173 | HUB (Vite dev) | Apenas em dev mode |
| 5174 | AETHER (Vite dev) | Apenas em dev mode |
| 5175 | OGMA (Electron dev) | Apenas em dev mode |
| 7071 | AKASHA (FastAPI) | Sempre ativo quando AKASHA roda |
| 7072 | LOGOS (proxy LLM) | HUB gerencia; fila de prioridades P1/P2/P3 |
| 8081 | llama-server AKASHA (interno) | Gerenciado pelo LOGOS; modelo llm_query; AKASHA, KOSMOS, HUB |
| 8083 | llama-server Mnemosyne (interno) | Gerenciado pelo LOGOS; modelo llm_rag; Mnemosyne |
| 8888 | SearXNG (self-hosted, opcional) | Backend de busca web do AKASHA; configura via `web_search_backend` no ecosystem.json |

**Syncthing:** gerenciado via painel no HUB; porta padrão 8384 (interface web local do Syncthing).

---

## 13. Checklist de verificação

### Pré-requisitos

```
[ ] rustc --version          → 1.77+
[ ] cargo tauri --version    → 2.x
[ ] node --version           → v22.x.x
[ ] npm --version            → 10.x+
[ ] python3 --version        → 3.11+
[ ] uv --version             → 0.4+
[ ] webkit2gtk-4.1           → instalado (Linux)
```

### llama-server

```
[ ] llama-server --version   → compilado corretamente
[ ] curl http://localhost:8081/health  → {"status":"ok"}
[ ] curl http://localhost:8081/v1/models → lista modelos
[ ] Modelo de chat carregado
[ ] Modelo de embedding carregado
```

### Ecossistema

```
[ ] bash atualizar.sh        → sem erros vermelhos
[ ] ecosystem.json configurado com os caminhos corretos
[ ] sync_root acessível
[ ] AKASHA respondendo: curl http://localhost:7071/health
[ ] HUB iniciando: npm run tauri dev (sem erros de compilação Rust)
[ ] LOGOS respondendo: curl http://localhost:7072/health
```

### Hardware específico

```
CachyOS:
[ ] HSA_OVERRIDE_GFX_VERSION=10.3.0 no config.fish
[ ] llama-server compilado com -DGGML_ROCM=ON
[ ] GPU detectada: rocminfo | grep "gfx1032"
[ ] (opcional) SearXNG rodando: curl http://localhost:8888/healthz → OK
[ ] (opcional) ecosystem.json com web_search_backend configurado

Fedora (laptop):
[ ] CUDA toolkit instalado
[ ] llama-server compilado com -DGGML_CUDA=ON
[ ] nvidia-smi funcionando
[ ] (opcional) SearXNG rodando: curl http://localhost:8888/healthz → OK

Windows 10:
[ ] Build do llama-server usa flags noavx (-DLLAMA_AVX2=OFF)
[ ] Testar com modelo pequeno antes de carregar modelo grande
[ ] (opcional) SearXNG rodando — ou deixar web_search_backend vazio para usar DDG
```
