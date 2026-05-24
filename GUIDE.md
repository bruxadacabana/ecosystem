<!-- Última atualização: 2026-05-23 — documento criado do zero -->

# Guia de Desenvolvimento do Ecossistema

Este guia é a bússola do projeto. Se você acabou de clonar o repositório, ou voltou após meses afastada, ou quer entender por que uma decisão foi tomada — comece aqui.

**Pré-requisito assumido:** você sabe o que são funções, classes e ambientes virtuais em Python, e se vira bem no terminal. Conceitos mais avançados serão explicados no caminho.

---

## Sumário

1. [Visão Geral do Ecossistema](#1-visão-geral-do-ecossistema)
2. [Pré-requisitos e Setup Inicial](#2-pré-requisitos-e-setup-inicial)
3. [Estrutura de Pastas do Projeto](#3-estrutura-de-pastas-do-projeto)
4. [Setup de Desenvolvimento por App](#4-setup-de-desenvolvimento-por-app)
5. [Dependências Completas por App](#5-dependências-completas-por-app)
6. [Arquitetura de Dados](#6-arquitetura-de-dados)
7. [Pipeline de Busca (AKASHA)](#7-pipeline-de-busca-akasha)
8. [Infraestrutura de LLMs Locais e Treinamento](#8-infraestrutura-de-llms-locais-e-treinamento)
9. [Conceitos Importantes Explicados](#9-conceitos-importantes-explicados)
10. [Convenções de Código](#10-convenções-de-código)
11. [Como Adicionar uma Feature Nova](#11-como-adicionar-uma-feature-nova)
12. [Debugging e Solução de Problemas](#12-debugging-e-solução-de-problemas)
13. [Glossário](#13-glossário)
14. [Referências e Links Úteis](#14-referências-e-links-úteis)

---

## 1. Visão Geral do Ecossistema

### O que é isso e por que existe?

Este é um ecossistema de aplicativos pessoais, completamente **locais**. Sem conta, sem nuvem, sem telemetria. Cada byte de dado fica na sua máquina.

O problema central que ele resolve: **informação pessoal fragmentada**. Notas espalhadas em dez aplicativos diferentes. PDFs que você "vai ler depois" e nunca mais acha. Pesquisas que você refaz porque não lembrava que já tinha feito. Áudio de reunião que ficou sem transcrição. Escrita criativa misturada com anotações de trabalho.

O ecossistema resolve isso com sete programas especializados que se comunicam entre si — e **nenhum deles depende de serviço externo** para funcionar.

---

### A distinção mais importante: AKASHA vs. Akasha

Este é o conceito que você precisa entender antes de qualquer outra coisa:

> **AKASHA** (todas as letras maiúsculas) é a **ferramenta de busca**. Funciona 100% sem IA generativa. Indexa, rastreia, ranqueia, recupera. Nunca sintetiza, nunca interpreta, nunca gera texto como resposta.

> **Akasha** (inicial maiúscula) é o **assistente inteligente de pesquisa**. Uma IA com personalidade, memória e reflexões próprias. Usa modelos de linguagem quando disponíveis, mas falha graciosamente quando não estão.

As duas camadas **rodam em paralelo e de forma completamente independente**. O AKASHA nunca espera pelo Akasha para entregar resultados. Se o modelo de linguagem estiver offline ou ocupado, o buscador continua funcionando normalmente — você perde apenas as funcionalidades de IA, não a busca em si.

Por que essa separação? Porque misturar IA no caminho crítico de busca é um erro de arquitetura. Busca precisa ser rápida, determinista e sempre disponível. IA precisa ser opcional, assíncrona e com fallback gracioso.

---

### Os sete programas

| Programa | Stack | Função |
|----------|-------|--------|
| 🖥️ **HUB** | Tauri 2 + React + Rust | Dashboard central: lança todos os outros apps, hospeda o LOGOS (proxy de LLM), monitora o ecossistema |
| ✍️ **AETHER** | Tauri 2 + React + Rust | Editor de escrita criativa com vault local de capítulos e cenas |
| 📝 **OGMA** | Electron + EditorJS | Editor de notas em blocos com busca full-text local |
| 🔍 **AKASHA** | FastAPI + Python + SQLite | Buscador e indexador pessoal; o Akasha (assistente) vive aqui também |
| 🧠 **Mnemosyne** | PySide6 + Python + ChromaDB | Assistente RAG com notebooks temáticos — conversa com seus documentos |
| 👁️ **KOSMOS** | PyQt6 + Python | Análise de imagens, OCR e visão computacional local |
| 🎙️ **Hermes** | Python + GUI | Transcrição e processamento de áudio local |

**Relação com o Akasha (assistente):** O AKASHA é a casa do Akasha. O assistente reside em `AKASHA/services/` e usa os dados de busca como substrato para suas reflexões — mas nunca bloqueia a ferramenta de busca para isso.

---

### Arquitetura geral

```
┌──────────────────────────────────────────────────────────────────────┐
│                               HUB                                    │
│         Dashboard · Lançador · Configuração central                  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                          LOGOS                               │    │
│  │  Proxy de LLM com fila de prioridades (P1 > P2 > P3)        │    │
│  │  P1: chat HUB + escrita AETHER                               │    │
│  │  P2: RAG Mnemosyne                                           │    │
│  │  P3: análise KOSMOS + transcrição Hermes + treino logos/     │    │
│  │                                                              │    │
│  │  ← llama-server (llama-cpp) em :8080 ← modelos GGUF        │    │
│  │     API OpenAI-compatível em :7072                           │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
    ┌─────────┐   ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ AETHER  │   │  AKASHA  │  │Mnemosyne │  │  KOSMOS  │
    │ :5174   │   │  :7071   │  │(desktop) │  │(desktop) │
    │(Tauri)  │   │(FastAPI) │  │(PySide6) │  │(PyQt6)   │
    └─────────┘   └──────────┘  └──────────┘  └──────────┘
                       │
              ┌────────┴────────┐
              ▼                 ▼
         AKASHA               Akasha
       (ferramenta)         (assistente)
    SQLite FTS5 +         personalidade +
    embeddings vetoriais  memória + reflexões
    sem LLM no crítico   usa LLM (P3, async)

         │              │
         ▼              ▼
    ┌─────────┐   ┌──────────┐
    │  OGMA   │   │  Hermes  │
    │ :5175   │   │(desktop) │
    │(Electron│   │(Python)  │
    └─────────┘   └──────────┘

Sync entre máquinas: Syncthing → sync_root
Dados privados de IA: personal_memory (isolado, nunca indexado)
Fine-tuning local: logos/ (QLoRA, P3, async)
```

**Fluxo de uma pesquisa no AKASHA:**
```
Usuária digita query
       ↓
query_understanding.py   ← [Akasha] classifica intenção (web? local? ambos?)
       ↓
query_expansion.py       ← [Akasha] expande termos, gera variações
       ↓
     ┌──────────────────────────────┐
     │  AKASHA (ferramenta)         │
     │  ├─ local_search.py          │
     │  │    FTS5 (BM25) + vetorial │
     │  └─ web_search.py            │
     │       DDG / SearXNG / arXiv  │
     └──────────────────────────────┘
       ↓
RRF + pagerank + freshness + domain_boost
       ↓
Renderização → links, trechos, cards
(nunca síntese ou resposta gerada)

Em paralelo (async, sem bloquear):
reflection_loop.py   ← [Akasha] reflete sobre a sessão
session_insight.py   ← [Akasha] gera insights para Mnemosyne
```

---

### Como os apps se comunicam

Existem três mecanismos de comunicação entre os apps:

**1. `ecosystem.json` — configuração compartilhada**

Um único arquivo JSON gerenciado pelo HUB. Todos os apps leem dele os caminhos de dados, modelos LLM ativos e configurações globais. Nenhum app configura por conta própria — o HUB é a fonte de verdade.

Localização:
- Linux: `~/.local/share/ecosystem/ecosystem.json`
- Windows: `%APPDATA%\ecosystem\ecosystem.json`

O arquivo é lido via `ecosystem_client.py` (biblioteca Python compartilhada na raiz do projeto). Apps Rust e TypeScript fazem a leitura diretamente via parsing JSON.

**2. HTTP local — comunicação em tempo real**

O AKASHA expõe uma API REST em `localhost:7071`. Outros apps podem consultar resultados de busca, status do indexador, e enviar insights via `POST /friendship/insight`. O LOGOS expõe API OpenAI-compatível em `localhost:7072`.

**3. Syncthing — sincronização entre máquinas**

O diretório `sync_root` é sincronizado entre as máquinas via Syncthing. Os dados persistentes dos apps (bancos SQLite, vectorstores, arquivos de configuração) ficam dentro do `sync_root`. Dados efêmeros (logs, cache) ficam locais.

---

### O `ecosystem.json` em detalhes

```json
{
  "sync_root": "/home/spacewitch/Documents/ecosystem_root",
  // ^ Pasta raiz sincronizada via Syncthing. Todos os dados persistentes
  //   dos apps vivem em subpastas aqui. derive_paths() em ecosystem_client.py
  //   deriva os caminhos de cada app a partir daqui automaticamente.

  "logos": {
    "llama_server_url": "http://localhost:8080"
    // ^ URL do llama-server direto. Usada como fallback quando o LOGOS (proxy)
    //   em :7072 não estiver disponível.
  },

  "aether": {
    "vault_path": "/home/.../ecosystem_root/aether",
    // ^ Onde o AETHER salva capítulos e cenas. Privado — nunca indexado por
    //   AKASHA ou Mnemosyne. Apenas o OGMA pode acessar.
    "config_path": ""
  },

  "akasha": {
    "archive_path": "/home/.../ecosystem_root/akasha",
    // ^ Arquivos indexados permanentemente (PDFs, documentos)
    "data_path": "/home/.../ecosystem_root/akasha",
    // ^ Banco SQLite principal (akasha.db)
    "base_url": "",
    // ^ URL pública do AKASHA se exposto em rede local (opcional)
    "config_path": ""
  },

  "mnemosyne": {
    "index_paths": ["/home/spacewitch/Documents"],
    // ^ Pastas que a Mnemosyne monitora e indexa (array — pode ser várias)
    "config_path": ""
  },

  "kosmos": {
    "archive_path": "/home/.../ecosystem_root/kosmos",
    "data_path": "",
    "config_path": "",
    "http_port": 8965
    // ^ Porta do servidor HTTP interno do KOSMOS (não exposto publicamente)
  },

  "hermes": {
    "output_dir": "/home/.../ecosystem_root/hermes",
    // ^ Onde o Hermes salva transcrições e arquivos processados
    "config_path": ""
  },

  "ogma": {
    "data_path": "/home/.../ecosystem_root/ogma"
    // ^ Banco SQLite do OGMA (notas)
  },

  "hub": {
    "data_path": ""
  }
}
```

**Quem lê/escreve cada campo:**

| Campo | Quem escreve | Quem lê |
|-------|-------------|---------|
| `sync_root` | HUB (setup inicial) | Todos (via `derive_paths()`) |
| `logos.*` | HUB | `ecosystem_client.get_inference_url()` |
| `aether.*` | HUB | AETHER, OGMA |
| `akasha.*` | HUB | AKASHA, Akasha (serviços internos) |
| `mnemosyne.*` | HUB | Mnemosyne |
| `kosmos.*` | HUB | KOSMOS |
| `hermes.*` | HUB | Hermes |
| `ogma.*` | HUB | OGMA |

**Regra fundamental:** nenhum app escreve no `ecosystem.json` além do HUB. Apps apenas leem.

---

### Tabela de portas reservadas

| Porta | Serviço | Notas |
|-------|---------|-------|
| 5173 | HUB — Vite dev server | Apenas em modo de desenvolvimento |
| 5174 | AETHER — Vite dev server | Apenas em modo de desenvolvimento |
| 5175 | OGMA — Electron dev | Apenas em modo de desenvolvimento |
| 7071 | AKASHA — FastAPI | Sempre ativo quando o AKASHA está rodando |
| 7072 | LOGOS — proxy LLM | HUB gerencia; fila P1/P2/P3 |
| 8080 | llama-server (direto) | Fallback quando LOGOS não está disponível |
| 8384 | Syncthing (interface web) | Interface de administração do Syncthing |
| 8965 | KOSMOS — HTTP interno | Comunicação interna entre KOSMOS e AKASHA |

---

---

## 2. Pré-requisitos e Setup Inicial

Esta seção lista **tudo** que precisa estar instalado antes de rodar qualquer app do ecossistema. Siga na ordem apresentada — algumas ferramentas dependem de outras.

> 💡 **Dica:** Se você só quer rodar um app específico, veja a Seção 4 (Setup por App) para saber quais pré-requisitos são obrigatórios para ele.

---

### 2.1. Visão rápida — o que cada ferramenta faz aqui

| Ferramenta | Para que serve no ecossistema |
|------------|-------------------------------|
| **Python 3.11+** | AKASHA, KOSMOS, Mnemosyne, Hermes, logos/ |
| **uv** | Gerenciador de ambientes e pacotes Python (substitui pip + venv) |
| **Node.js 22+** | HUB, AETHER, OGMA |
| **npm** | Instalação de dependências JS (vem junto com o Node) |
| **Rust + Cargo** | Compilação de HUB e AETHER (Tauri) |
| **cargo-tauri** | CLI do Tauri para build e dev |
| **llama-server** | Backend de inferência LLM (compilado do llama.cpp) |
| **Unsloth + bitsandbytes** | Fine-tuning QLoRA local (opcional — só para treino) |
| **ROCm / CUDA** | Aceleração GPU (opcional — CPU funciona, só mais lento) |

---

### 2.2. Python 3.11+

O ecossistema exige Python **≥ 3.11** e **< 3.14**. Python 3.12 é a versão recomendada.

**Verificar versão instalada:**
```bash
python3 --version
```

**Instalar se necessário:**

```bash
# CachyOS / Arch Linux
sudo pacman -S python

# Fedora
sudo dnf install python3.12

# Windows 10
# Baixar em: https://python.org/downloads/
# ⚠️ Marcar "Add Python to PATH" durante a instalação
```

> ⚠️ No Windows, o executável pode se chamar `python` (sem o `3`). Verifique com `python --version`.

---

### 2.3. uv — gerenciador de Python moderno

O `uv` é usado para criar ambientes virtuais e instalar dependências dos apps que têm `pyproject.toml` (AKASHA e KOSMOS). É muito mais rápido que o pip padrão e garante que as versões travadas em `uv.lock` sejam respeitadas.

**Instalar:**

```bash
# Linux (CachyOS, Fedora) e macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Adicionar ao PATH (se necessário):**

```bash
# bash/zsh — adicionar ao .bashrc ou .zshrc:
export PATH="$HOME/.local/bin:$PATH"

# Fish shell — adicionar ao config.fish:
fish_add_path ~/.local/bin

# Windows: o instalador adiciona automaticamente; abrir novo terminal.
```

**Verificar:**
```bash
uv --version
# Deve mostrar: uv 0.4.x ou superior
```

---

### 2.4. Node.js 22+ e npm

Necessário para HUB, AETHER e OGMA.

**Instalar via fnm (recomendado — funciona em bash, zsh e Fish):**

```bash
# Instalar fnm
curl -fsSL https://fnm.vercel.app/install | bash

# Abrir novo terminal, depois:
fnm install 22
fnm use 22
fnm default 22
```

> 🐟 **Fish shell:** o instalador do fnm detecta Fish automaticamente e configura `~/.config/fish/conf.d/fnm.fish`. Basta abrir um novo terminal.

**Instalar diretamente (alternativa sem gerenciador de versões):**

```bash
# CachyOS / Arch
sudo pacman -S nodejs npm

# Fedora
sudo dnf install nodejs22

# Windows 10
# Baixar LTS v22 em: https://nodejs.org
# Marcar "Automatically install necessary tools" durante instalação
```

**Verificar:**
```bash
node --version   # v22.x.x
npm --version    # 10.x.x ou superior
```

> ⚠️ **nvm NÃO funciona em Fish shell.** Use fnm ou instale o Node diretamente.

---

### 2.5. Rust e Cargo

Necessário para compilar HUB e AETHER (Tauri 2).

**Instalar via rustup (recomendado — instala Rust, Cargo e toolchain):**

```bash
# Linux e macOS
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Após instalar, recarregar o shell:
source "$HOME/.cargo/env"          # bash/zsh
fish_add_path ~/.cargo/bin         # Fish (ou abrir novo terminal)

# Windows
# Baixar e executar rustup-init.exe em: https://rustup.rs
# Selecionar opção 1 (default) — instala o toolchain MSVC automaticamente
```

**Verificar:**
```bash
rustc --version    # rustc 1.77.x ou superior
cargo --version
```

**Instalar o Tauri CLI:**
```bash
cargo install tauri-cli --version "^2"

# Verificar:
cargo tauri --version   # tauri-cli 2.x.x
```

> ⏱️ A primeira compilação do Tauri CLI demora 10–20 minutos — está compilando do zero. Compilações subsequentes usam cache e são muito mais rápidas.

---

### 2.6. Dependências de sistema (Linux)

Necessárias para o Tauri funcionar. Sem elas, `cargo tauri dev` falha com erros de linker.

```bash
# CachyOS / Arch Linux
sudo pacman -S base-devel cmake pkg-config openssl git \
               webkit2gtk-4.1 libayatana-appindicator \
               xdotool sqlite

# Fedora
sudo dnf group install development-tools c-development
sudo dnf install cmake pkg-config openssl-devel git \
                 webkit2gtk4.1-devel libappindicator-gtk3-devel \
                 python3-devel xdotool sqlite sqlite-devel
```

**Windows 10:** instalar o **Visual Studio Build Tools 2022** antes de qualquer coisa:
- Baixar em: https://visualstudio.microsoft.com/visual-cpp-build-tools/
- Marcar: "Desenvolvimento para desktop com C++"
- Instalar também o **WebView2 Runtime** (geralmente já presente no Windows 10 atualizado)

---

### 2.7. llama-server (llama.cpp)

O backend de inferência LLM do ecossistema. **Substitui o Ollama** — todo o código do ecossistema faz chamadas à API OpenAI-compatível exposta pelo llama-server.

> 📖 Instruções completas de compilação e uso estão na Seção 8 e no `README.md`. Aqui está o resumo rápido para verificar se está funcional.

**Verificar se está rodando:**
```bash
curl http://localhost:8080/health
# Resposta esperada: {"status":"ok"}

curl http://localhost:8080/v1/models
# Resposta esperada: {"data": [...]}
```

**Iniciar manualmente (CachyOS, com ROCm):**
```bash
HSA_OVERRIDE_GFX_VERSION=10.3.0 \
  ./llama-server \
  --model ~/models/qwen2.5-7b-q4_k_m.gguf \
  --host 127.0.0.1 --port 8080 \
  --n-gpu-layers 999
```

---

### 2.8. Ferramentas de fine-tuning (opcional)

Usadas apenas pelos scripts em `logos/` (treinamento QLoRA local). **Não são necessárias para rodar os apps do ecossistema** — só para treinar modelos.

> ⚠️ Estas ferramentas **não estão no venv base do ecossistema**. São instaladas separadamente quando você quer fazer fine-tuning.

```bash
# Criar um venv separado para treinamento (recomendado)
python3 -m venv ~/.venvs/training
source ~/.venvs/training/bin/activate   # bash/zsh
# OU: ~/.venvs/training/bin/activate.fish  (Fish)

# PyTorch com ROCm (AMD RX 6600 — CachyOS)
pip install torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/rocm6.2

# PyTorch com CUDA (NVIDIA MX150 — Fedora laptop)
pip install torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/cu124

# PyTorch CPU puro (Windows / sem GPU)
pip install torch torchvision torchaudio

# Unsloth — wrapper eficiente para QLoRA
# AMD (RX 6600):
pip install "unsloth[amd]"
# NVIDIA:
pip install "unsloth[cu124-torch250]"

# bitsandbytes AMD (build especial — versão pré-release)
pip install --force-reinstall --no-cache-dir --no-deps \
  "https://github.com/bitsandbytes-foundation/bitsandbytes/releases/download/continuous-release_main/bitsandbytes-1.33.7.preview-py3-none-manylinux_2_24_x86_64.whl"

# Transformers, TRL, PEFT, Datasets
pip install transformers trl peft datasets accelerate
```

**Verificar instalação do ambiente de treinamento:**
```bash
python -c "
from logos.qlora_trainer import check_training_deps
print(check_training_deps())
"
# Saída esperada: {'unsloth': True, 'bitsandbytes': True, 'transformers': True, ...}
```

---

### 2.9. Fontes (interface)

As fontes abaixo são usadas na UI dos apps. Sem elas, a interface usa fallbacks do sistema — funciona, mas fica visualmente diferente.

```bash
# CachyOS / Arch
sudo pacman -S ttf-nerd-fonts-symbols ttf-liberation noto-fonts

# Fedora
sudo dnf install liberation-fonts google-noto-fonts-common
# Nerd Fonts: baixar manualmente em https://www.nerdfonts.com/font-downloads
# Extrair para ~/.local/share/fonts/ e rodar: fc-cache -fv

# Windows
# Nerd Fonts: https://www.nerdfonts.com/font-downloads
# Liberation Fonts: https://github.com/liberationfonts/liberation-fonts/releases
# Selecionar os .ttf, botão direito → Instalar para todos os usuários
```

---

### 2.10. Variáveis de ambiente importantes

Estas variáveis não são obrigatórias para rodar, mas afetam comportamento:

```bash
# CachyOS — habilitar GPU AMD RX 6600 para ROCm
# Adicionar ao ~/.config/fish/config.fish (Fish) ou ~/.bashrc (bash):
set -x HSA_OVERRIDE_GFX_VERSION 10.3.0   # Fish
export HSA_OVERRIDE_GFX_VERSION=10.3.0   # bash

# Fedora — selecionar GPU NVIDIA se Optimus causar problemas
export CUDA_VISIBLE_DEVICES=0

# Qualquer máquina — forçar caminho do ecosystem.json (raramente necessário)
# Por padrão o ecosystem_client.py encontra automaticamente via XDG/AppData
export ECOSYSTEM_CONFIG=/caminho/customizado/ecosystem.json
```

---

### 2.11. Setup completo em uma máquina nova

Sequência recomendada do zero:

```bash
# 1. Dependências de sistema (ver 2.6)
# 2. Python 3.11+       (ver 2.2)
# 3. uv                 (ver 2.3)
# 4. Node.js 22+ / npm  (ver 2.4)
# 5. Rust + cargo-tauri (ver 2.5)
# 6. Clonar o repositório
git clone <url-do-repo> "program files"
cd "program files"

# 7. Instalar todas as dependências de uma vez
bash atualizar.sh     # Linux
.\atualizar.bat       # Windows

# 8. Configurar o ecosystem.json
# O HUB cria automaticamente na primeira execução.
# Ou copiar e editar manualmente:
cp ecosystem.local.example.json ~/.local/share/ecosystem/ecosystem.json
# Editar os caminhos com seu editor preferido

# 9. Baixar e iniciar o llama-server (ver Seção 8)

# 10. Iniciar o HUB
cd HUB && npm run tauri dev
```

---

### 2.12. Checklist de verificação

Rode estes comandos depois do setup para confirmar que tudo está funcional:

```bash
# Runtime tools
rustc --version          # rustc 1.77+
cargo tauri --version    # tauri-cli 2.x
node --version           # v22.x.x
npm --version            # 10.x+
python3 --version        # 3.11+ (e < 3.14)
uv --version             # 0.4+

# llama-server
curl -s http://localhost:8080/health | python3 -m json.tool
# Esperado: { "status": "ok" }

# AKASHA (depois de iniciar)
curl -s http://localhost:7071/health
# Esperado: { "status": "ok", "version": "..." }

# Sistema (Linux)
pkg-config --modversion webkit2gtk-4.1   # deve retornar versão
```

---

---

## 3. Estrutura de Pastas do Projeto

O repositório é um **monorepo**: todos os apps vivem juntos numa única pasta raiz chamada `program files/`. Isso facilita o compartilhamento de código (a biblioteca `ecosystem_client.py` é usada por múltiplos apps) e garante que um único `git pull` atualiza tudo.

> 💡 **Pastas omitidas nesta árvore:** `node_modules/`, `__pycache__/`, `.venv/`, `target/` (Rust), `dist/` (builds) — são geradas automaticamente e não fazem parte do código-fonte.

---

### 3.1. Visão geral da raiz

```
program files/
├── 📁 AETHER/          → Editor de escrita criativa (Tauri 2 + React)
├── 📁 AKASHA/          → Buscador pessoal (FastAPI + Python)
├── 📁 Hermes/          → Transcrição de áudio (Python + PyQt6)
├── 📁 HUB/             → Dashboard central e LOGOS (Tauri 2 + React)
├── 📁 KOSMOS/          → Análise de feeds e imagens (Python + PySide6)
├── 📁 logos/           → Scripts de fine-tuning de LLMs (Python puro)
├── 📁 Mnemosyne/       → Assistente RAG com notebooks (Python + PySide6)
├── 📁 OGMA/            → Editor de notas (Electron + EditorJS)
├── 📁 tests/           → Testes de integração do ecossistema (ecosystem_client)
│
│   ── Biblioteca compartilhada Python ──
├── ecosystem_client.py         → Lê/escreve ecosystem.json; get_inference_url(), etc.
├── ecosystem_logging.py        → Configuração de logging padronizado
├── ecosystem_qt.py             → Tema Qt (QSS) compartilhado entre KOSMOS, Mnemosyne, Hermes
├── ecosystem_scraper.py        → Utilitário de scraping compartilhado
├── hardware_probe.py           → Detecta GPU, VRAM e capacidades da máquina
├── logits_worker.py            → Worker de inferência para logits (logos/)
├── shared_topic_profile.py     → Perfil de tópicos compartilhado entre AKASHA e Mnemosyne
├── vram_monitor.py             → Monitora VRAM em tempo real (para pausar P3)
│
│   ── Scripts de automação ──
├── atualizar.sh / atualizar.bat   → Instala/atualiza deps de todos os apps
├── buildar.sh / buildar.bat       → Builda AETHER, HUB e OGMA para produção
│
│   ── Documentação e configuração ──
├── CLAUDE.md                   → Instruções para o Claude Code (este projeto)
├── CONTRIBUTING.md             → Guia de contribuição
├── GUIDE.md                    → Este arquivo
├── README.md                   → Documentação de instalação e visão geral
├── SETUP.txt                   → Setup legado (substituído pelo README.md)
├── ecosystem.local.example.json → Modelo de configuração local (ver Seção 6)
├── notes.md                    → Notas pessoais da usuária — nunca editar
```

---

### 3.2. AKASHA — buscador e assistente

```
AKASHA/
├── main.py                 → Ponto de entrada FastAPI + lifespan (init DB, registra no ecossistema)
├── config.py               → Configuração lida do ecosystem.json
├── database.py             → Schema SQLite, migrations, connection pool
├── pyproject.toml          → Dependências (gerenciado por uv)
├── uv.lock                 → Versões travadas (commitar sempre)
│
├── 📁 routers/             → Endpoints FastAPI (um arquivo por "área")
│   ├── search.py           → GET /search — busca principal
│   ├── crawler.py          → /library — gerencia domínios e biblioteca
│   ├── chat.py             → /chat — conversa com o Akasha (assistente)
│   ├── dialogue.py         → /dialogue — modo conversacional contínuo
│   ├── domains.py          → /domains — CRUD de domínios
│   ├── favorites.py        → /favorites — itens salvos
│   ├── graph.py            → /graph — grafo de conhecimento
│   ├── highlights.py       → /highlights — trechos marcados
│   ├── history.py          → /history — histórico de buscas
│   ├── interests.py        → /interests — perfil de interesses
│   ├── kosmos_bridge.py    → /kosmos — ponte com o KOSMOS (busca de imagens)
│   ├── lenses.py           → /lenses — filtros de busca (lentes)
│   ├── memory.py           → /memory — memória pessoal do Akasha
│   ├── papers.py           → /papers — busca e download de artigos científicos
│   ├── suggestions.py      → /suggestions — sugestões de busca
│   ├── system.py           → /health, /logs — status e diagnóstico
│   └── watch_later.py      → /watch-later — fila de vídeos
│
├── 📁 services/            → Lógica de negócio (sem HTTP, sem templates)
│   │
│   │   ── AKASHA (ferramenta — sem LLM no crítico) ──
│   ├── crawler.py          → Baixa e processa páginas web
│   ├── crawler_scheduler.py→ Agenda re-crawls automáticos
│   ├── local_search.py     → Busca local: FTS5 + vetorial + BM25
│   ├── web_search.py       → Busca web: DDG, SearXNG, Wikipedia, arXiv
│   ├── pagerank.py         → Calcula PageRank dos domínios indexados
│   ├── freshness.py        → Pontuação de frescor dos resultados
│   ├── image_indexer.py    → Indexa imagens com pHash + vetorial
│   ├── archiver.py         → Arquiva páginas em formato longo
│   ├── paper_search.py     → Busca em arXiv e repositórios científicos
│   ├── paper_download.py   → Download de PDFs de artigos
│   ├── downloader.py       → Fila de downloads gerais
│   ├── click_log.py        → Registra cliques para aprendizado de ranking
│   ├── search_session.py   → Gerencia sessões de busca (contexto multi-query)
│   ├── search_profile.py   → Perfil de busca (pesos, preferências)
│   ├── invidious.py        → Busca de vídeos via Invidious (YouTube sem Google)
│   ├── translation_card.py → Card de tradução contextual
│   ├── weather_widget.py   → Card de clima (Open-Meteo)
│   ├── wiki_card.py        → Card de Wikipedia
│   ├── kosmos_search.py    → Busca de imagens via KOSMOS
│   ├── list_sync.py        → Sincroniza listas (watch-later, favoritos) entre máquinas
│   ├── log_buffer.py       → Buffer circular de logs para /system/logs
│   └── realtime_context.py → Contexto em tempo real (hora, localização, clima)
│   │
│   │   ── Akasha (assistente — usa LLM, P3, async) ──
│   ├── persona.py          → Personalidade e prompt base do Akasha
│   ├── personal_memory.py  → Lê/escreve memória pessoal (tabela isolada)
│   ├── reflection_loop.py  → Reflexões periódicas sobre sessões de busca
│   ├── session_memory.py   → Sumariza e persiste memória de sessão
│   ├── session_insight.py  → Gera insights a partir das sessões
│   ├── knowledge_worker.py → Analisa corpus local para extrair conhecimento
│   ├── query_understanding.py → Classifica intenção da query (LLM leve)
│   ├── query_expansion.py  → Expande termos de busca (sinônimos, variações)
│   ├── affective_state.py  → Estado afetivo do Akasha (curiosidade, fadiga, etc.)
│   ├── suggester.py        → Sugere buscas relacionadas
│   ├── friendship_receiver.py → Recebe insights da Mnemosyne (POST /friendship/insight)
│   └── user_data.py        → Dados do perfil da usuária
│
├── 📁 templates/           → Templates Jinja2 (HTML renderizado no servidor)
│   ├── base.html           → Layout base com navegação
│   ├── search.html         → Página de resultados de busca
│   ├── library.html        → Biblioteca de domínios e documentos
│   ├── chat.html           → Interface de chat com o Akasha
│   └── ...                 → Um template por rota
│
├── 📁 static/              → CSS, JS, imagens estáticas
│   └── style.css           → Estilos globais
│
├── 📁 extension/           → Extensão de browser (Chrome/Firefox)
│   ├── manifest.json       → Manifesto da extensão (v3)
│   ├── background.js       → Service worker da extensão
│   ├── content.js          → Script injetado nas páginas
│   └── popup/              → Interface do popup da extensão
│
├── 📁 data/                → Dados locais (não sincronizados)
│   └── archive/            → Páginas arquivadas localmente
│
└── 📁 tests/               → Testes unitários (pytest + pytest-asyncio)
    ├── conftest.py          → Fixtures compartilhadas
    ├── test_local_search_smoke.py
    ├── test_query_understanding.py
    ├── test_friendship_receiver.py
    └── integration/        → Testes de integração (exigem serviços rodando)
```

---

### 3.3. HUB — dashboard central

```
HUB/
├── index.html              → Ponto de entrada do Vite
├── package.json            → Dependências JS
├── vite.config.ts          → Configuração do Vite (build)
├── vitest.config.ts        → Configuração de testes
│
├── 📁 src/                 → Código-fonte React + TypeScript
│   ├── App.tsx             → Componente raiz com roteamento
│   ├── main.tsx            → Bootstrap do React
│   ├── 📁 components/      → Componentes reutilizáveis
│   ├── 📁 views/           → Páginas/abas do HUB
│   ├── 📁 lib/             → Utilitários, API clients, store
│   ├── 📁 styles/          → CSS e tokens de design
│   └── 📁 types/           → Tipos TypeScript compartilhados
│
├── 📁 src-tauri/           → Backend Rust (Tauri)
│   ├── Cargo.toml          → Dependências Rust
│   ├── tauri.conf.json     → Configuração do Tauri (janela, permissões)
│   ├── 📁 src/             → Código Rust
│   │   ├── main.rs         → Ponto de entrada
│   │   ├── logos.rs        → LOGOS: proxy LLM com fila de prioridade
│   │   └── 📁 commands/    → Comandos Tauri invocáveis do frontend
│   │       ├── launcher.rs → Lança/para apps do ecossistema
│   │       ├── logos.rs    → Comandos do LOGOS (modelos, inferência)
│   │       └── ...
│   └── 📁 capabilities/    → Permissões de segurança do Tauri
│
└── 📁 tests/               → Testes TypeScript (Vitest)
```

---

### 3.4. AETHER — editor de escrita

```
AETHER/
├── src/                    → Código React + TypeScript (estrutura similar ao HUB)
│   ├── components/         → Editor, painel de capítulos, barra de ferramentas
│   └── lib/                → API Tauri, gerenciamento de vault
├── src-tauri/              → Backend Rust
│   └── src/                → Comandos de leitura/escrita de arquivos do vault
└── dev_files/              → Notas de design internas
```

---

### 3.5. Mnemosyne — assistente RAG

```
Mnemosyne/
├── main.py                 → Ponto de entrada (PySide6 QApplication)
├── requirements.txt        → Dependências (pip — venv compartilhado)
├── config.example.json     → Modelo de configuração
│
├── 📁 core/                → Lógica de negócio (sem GUI)
│   ├── indexer.py          → Indexação de documentos: chunking + embeddings
│   ├── rag.py              → Motor RAG: LangChain + ChatOpenAI + ChromaDB
│   ├── loaders.py          → Carregadores de arquivo (PDF, EPUB, MD, imagens via visão)
│   ├── notebook.py         → Modelo de notebook (tema, histórico, memória)
│   ├── notebook_store.py   → Persistência de notebooks (CRUD)
│   ├── collections.py      → Gerenciamento de coleções ChromaDB
│   ├── bm25_index.py       → Índice BM25 complementar ao vetorial
│   ├── raptor_index.py     → RAPTOR: sumarização hierárquica para docs longos
│   ├── session_indexer.py  → Índice in-memory efêmero (páginas web por sessão)
│   ├── personal_memory.py  → Memória pessoal da Mnemosyne (isolada do RAG)
│   ├── persona.py          → Personalidade e prompt base
│   ├── insight_scheduler.py→ Agenda pop-ups de insights
│   ├── insights.py         → Gera insights a partir do corpus
│   ├── dialogue.py         → Motor de diálogo (chain RAG)
│   ├── affective_state.py  → Estado afetivo da Mnemosyne
│   ├── ollama_client.py    → Cliente de inferência (nome legado — usa llama-server)
│   ├── knowledge_graph.py  → Grafo de conhecimento extraído dos documentos
│   ├── lightrag_graph.py   → Integração com LightRAG (grafo + RAG híbrido)
│   ├── idle_indexer.py     → Indexa em background quando sistema está ocioso
│   ├── memory.py           → Memória de contexto por notebook
│   ├── config.py           → Lê configuração do ecosystem.json
│   ├── akasha_client.py    → Cliente HTTP para busca web via AKASHA
│   ├── errors.py           → Hierarquia de exceções tipadas
│   └── logger.py           → Configuração de logging
│   │
│   │   ── Studio (geração de outputs) ──
│   ├── summarizer.py / faq.py / mindmap.py / flashcards.py
│   ├── infographic.py / blogpost.py / report.py / toc.py
│   ├── slides.py / guide.py / briefing.py / timeline.py
│   └── tables.py           → Cada arquivo gera um tipo de Studio output
│
├── 📁 gui/                 → Interface PySide6
│   ├── main_window.py      → Janela principal com abas
│   ├── notebooks_panel.py  → Painel de notebooks (lista + chat)
│   ├── dialogue_panel.py   → Painel de conversa RAG
│   ├── topics_view.py      → Visualização de tópicos do corpus
│   ├── studio_tile_widget.py → Tile persistente de Studio output
│   ├── insight_popup.py    → Pop-up de insight proativo
│   ├── flashcards_dialog.py→ Dialog de flashcards
│   ├── app_state.py        → Estado global da aplicação (singleton)
│   ├── workers.py          → QThread workers (indexação, RAG, Studio — async)
│   ├── styles.qss          → Tema Qt (modo noturno)
│   ├── styles_light.qss    → Tema Qt (modo claro)
│   └── fonts/              → Fontes embutidas (CourierPrime, IMFell, SpecialElite)
│
├── 📁 logs/                → Logs rotativos da Mnemosyne
└── 📁 tests/               → Testes pytest
    └── integration/        → Testes que precisam de ChromaDB e modelos reais
```

---

### 3.6. OGMA — editor de notas

```
OGMA/
├── src/                    → Código Electron (main process + renderer)
│   ├── main/               → Processo principal Electron (Node.js)
│   └── renderer/           → Interface (HTML + EditorJS)
├── data/                   → Dados locais (banco SQLite, logs, exports)
│   ├── ogma.db             → Banco principal (SQLite, WAL mode)
│   ├── settings.json       → Preferências locais
│   └── logs/               → Logs diários (YYYY-MM-DD.log)
├── assets/                 → Ícones da aplicação
└── dev_files/              → Documentos de design internos
```

---

### 3.7. KOSMOS — análise de feeds e imagens

```
KOSMOS/
├── main.py                 → Ponto de entrada PyQt6
├── pyproject.toml          → Dependências (gerenciado por uv)
└── app/
    ├── core/               → Feed parser, download de artigos, análise
    ├── ui/                 → Widgets e janelas PyQt6
    ├── theme/              → Estilos e tema visual
    └── utils/              → Utilitários compartilhados
```

---

### 3.8. Hermes — transcrição de áudio

```
Hermes/
├── hermes.py               → Ponto de entrada e janela principal
├── api_server.py           → Servidor HTTP local (integração com outros apps)
├── requirements.txt        → Deps: PyQt6, faster-whisper, yt-dlp
├── gui/
│   ├── workers.py          → QThread: transcrição, download de áudio
│   └── recipe_tab.py       → Aba de extração de receitas
└── services/
    └── recipe_extractor.py → Extrai receitas estruturadas de transcrições via LLM
```

---

### 3.9. logos/ — scripts de fine-tuning

```
logos/
├── qlora_trainer.py        → Treino QLoRA local (Unsloth + bitsandbytes AMD)
├── training_data_generator.py → Gera pares Q&A a partir do corpus da Mnemosyne
├── finetune_scheduler.py   → Agenda execuções de fine-tuning (P3)
├── dispatcher.py           → Despacha tarefas de treinamento para a fila P3
├── gguf_converter.py       → Converte modelos treinados para GGUF (llama.cpp)
└── skills/                 → Prompts estruturados reutilizáveis (Markdown)
    ├── chunk-classification.md
    ├── entity-extraction.md
    ├── rag-query.md
    └── synthesis.md
```

---

### 3.10. Biblioteca compartilhada (raiz)

Estes arquivos na raiz são importados diretamente pelos apps Python (não são um pacote instalável — estão no `sys.path` por convenção de diretório de trabalho):

| Arquivo | O que faz | Quem usa |
|---------|-----------|---------|
| `ecosystem_client.py` | Lê/escreve `ecosystem.json`; `get_inference_url()`, `request_llm()`, `request_llm_stream()` | AKASHA, Mnemosyne, KOSMOS, Hermes, logos/ |
| `ecosystem_logging.py` | Logger padronizado com arquivo rotativo | Todos os apps Python |
| `ecosystem_qt.py` | Gera QSS do tema "Atlas Astronômico à Meia-Noite" para Qt | KOSMOS, Hermes |
| `ecosystem_scraper.py` | Scraping respeitoso (robots.txt, rate limiting, trafilatura) | AKASHA, Mnemosyne |
| `hardware_probe.py` | Detecta GPU/VRAM/AVX2 (usado pelo HUB para escolher modelos) | HUB, logos/ |
| `logits_worker.py` | Worker de logits para inferência especulativa | logos/ |
| `shared_topic_profile.py` | Perfil de tópicos compartilhado AKASHA↔Mnemosyne | AKASHA, Mnemosyne |
| `vram_monitor.py` | Monitora VRAM em tempo real (pausa P3 quando > 85%) | logos/, HUB |

---

### 3.11. Onde ficam os dados em runtime

Os dados gerados em runtime **não ficam no repositório** — ficam em `sync_root` (Syncthing) ou em caminhos locais da máquina:

```
sync_root/                   → Sincronizado via Syncthing entre máquinas
├── aether/                  → Vault: capítulos e cenas do AETHER
├── akasha/                  → Banco SQLite principal (akasha.db)
├── mnemosyne/
│   ├── docs/                → Documentos monitorados pela Mnemosyne
│   └── chroma_db/           → Vectorstore ChromaDB persistente
├── kosmos/                  → Arquivos processados pelo KOSMOS
├── hermes/                  → Transcrições e outputs do Hermes
├── ogma/                    → Banco SQLite do OGMA
├── logos/
│   ├── training_data/       → JSONL de pares Q&A (data gerada)
│   └── checkpoints/         → Checkpoints de modelos treinados
└── .ai_private/             → Memória pessoal das IAs (nunca indexada)

~/.local/share/ecosystem/    → Configuração local (Linux)
%APPDATA%\ecosystem\         → Configuração local (Windows)
└── ecosystem.json           → Fonte de verdade do ecossistema

Mnemosyne/logs/              → Logs rotativos (ficam no repo, em .gitignore)
OGMA/data/logs/              → Logs diários do OGMA
AKASHA/data/                 → Cache local de páginas arquivadas
```

> ⚠️ **Nunca commitar** `ecosystem.json`, bancos SQLite (`.db`), vectorstores ou checkpoints de modelos. O `.gitignore` já cuida disso, mas vale saber.

---

---

## 4. Setup de Desenvolvimento por App

Esta seção traz o passo a passo completo para rodar cada app em modo de desenvolvimento. "Modo dev" significa que você vê erros no terminal, o servidor recarrega automaticamente ao salvar arquivos e nenhum build de produção é necessário.

> 💡 **Antes de qualquer coisa:** rode `bash atualizar.sh` na raiz. Isso instala as dependências de todos os apps de uma vez. Os passos abaixo são para quando você quer trabalhar em um app específico ou entender o que o `atualizar.sh` faz por baixo.

---

### 4.1. AKASHA

**Stack:** FastAPI + Python 3.12 + SQLite  
**Venv:** gerenciado pelo `uv`, localizado em `AKASHA/.venv`  
**Porta:** 7071

```bash
cd AKASHA

# Instalar / atualizar dependências
uv sync

# Rodar em modo dev (reinicia automaticamente ao salvar com uvicorn --reload)
uv run python main.py
# O browser abre automaticamente em http://localhost:7071

# Alternativa: recarregamento automático via uvicorn direto
uv run uvicorn main:app --reload --port 7071 --host 0.0.0.0
```

> 🔄 O `main.py` já usa `uvicorn` internamente com `reload=True` em modo dev. Se quiser mais controle sobre o recarregamento, use a invocação direta do uvicorn acima.

**Rodar testes:**
```bash
cd AKASHA

# Testes unitários (rápido, sem dependências externas)
uv run pytest tests/ -v --ignore=tests/integration

# Testes de integração (exigem AKASHA rodando + banco populado)
uv run pytest tests/integration/ -v

# Um teste específico
uv run pytest tests/test_local_search_smoke.py -v

# Com cobertura
uv run pytest tests/ --cov=. --cov-report=term-missing --ignore=tests/integration
```

**Variáveis de ambiente relevantes:**
```bash
# Nenhuma obrigatória — AKASHA lê tudo do ecosystem.json via config.py
# Opcional: forçar caminho do banco (raramente necessário)
AKASHA_DB_PATH=/caminho/customizado/akasha.db uv run python main.py
```

**O que acontece no startup:**
1. `config.py` lê o `ecosystem.json` e resolve caminhos
2. `database.py` inicializa o SQLite: aplica migrations, habilita WAL e FTS5
3. `main.py` registra a URL do AKASHA no `ecosystem.json` (campo `akasha.base_url`)
4. Todos os routers são montados
5. O `reflection_loop` e o `friendship_receiver` sobem como tasks async em background

---

### 4.2. Mnemosyne

**Stack:** PySide6 + Python 3.11+ + ChromaDB + LangChain  
**Venv:** compartilhado em `program files/.venv` (raiz do monorepo)  
**Porta:** nenhuma (app desktop)

```bash
# A partir da raiz do monorepo:
# Criar o venv compartilhado (se não existir)
python3 -m venv .venv

# Ativar o venv
source .venv/bin/activate      # bash/zsh
source .venv/bin/activate.fish # Fish
.venv\Scripts\activate         # Windows

# Instalar dependências da Mnemosyne
pip install -r Mnemosyne/requirements.txt

# Rodar a Mnemosyne
cd Mnemosyne
python main.py
# ou, pela raiz:
bash Mnemosyne/iniciar.sh
```

> ⚠️ **Importante:** a Mnemosyne usa o `.venv` da **raiz do monorepo**, não um venv próprio. O `iniciar.sh` já resolve o caminho relativo corretamente (`../. venv`).

**Rodar testes:**
```bash
# Com o venv ativado
cd Mnemosyne
python -m pytest tests/ -v

# Ignorar testes de integração (que precisam de ChromaDB e modelos reais)
python -m pytest tests/ -v --ignore=tests/integration

# Teste específico
python -m pytest tests/test_affective_state_db.py -v
```

**O que acontece no startup:**
1. `core/config.py` lê `ecosystem.json` e resolve `chroma_dir`, `watched_dir`, etc.
2. ChromaDB é iniciado (conecta ao diretório persistente ou cria se não existir)
3. BM25 index é carregado do disco
4. `InsightScheduler` sobe em thread separada (pop-ups proativos)
5. Janela PySide6 é exibida com os notebooks persistidos

---

### 4.3. KOSMOS

**Stack:** PySide6 + Python 3.11+ + feedparser  
**Venv:** gerenciado pelo `uv`, localizado em `KOSMOS/.venv`  
**Porta:** 8965 (HTTP interno — comunicação com AKASHA, não exposta publicamente)

```bash
cd KOSMOS

# Instalar dependências
uv sync

# Rodar
uv run main.py
# ou
bash iniciar.sh
```

**Rodar testes:**
```bash
cd KOSMOS
uv run pytest tests/ -v
uv run pytest tests/test_config.py -v     # testa leitura do ecosystem.json
uv run pytest tests/test_database.py -v  # testa schema SQLite
```

---

### 4.4. Hermes

**Stack:** PyQt6 + Python 3.11+ + faster-whisper + yt-dlp  
**Venv:** compartilhado em `program files/.venv` (mesmo venv da Mnemosyne)  
**Porta:** nenhuma (app desktop)

```bash
# Com o venv compartilhado ativado (ver 4.2 para ativar):
cd Hermes
python hermes.py
# ou, pela raiz:
bash Hermes/iniciar.sh
```

> 💡 O Hermes e a Mnemosyne compartilham o mesmo venv por compatibilidade: ambos usam `pip install -r requirements.txt` e têm dependências que se complementam (ex: `PySide6` e `PyQt6` coexistem no mesmo ambiente).

**Rodar testes:**
```bash
cd Hermes
# Com o .venv ativado:
python -m pytest tests/ -v
python -m pytest tests/test_recipe_extractor.py -v
```

---

### 4.5. HUB

**Stack:** Tauri 2 + React + TypeScript + Rust  
**Porta:** 5173 (Vite dev server, apenas em dev mode)

```bash
cd HUB

# Instalar dependências JS
npm install

# Rodar em modo dev (Vite hot-reload + janela Tauri nativa)
npm run tauri dev

# Apenas o frontend (sem a janela Tauri nativa — útil para UI pura)
npm run dev
```

> 🦀 **Na primeira execução**, o Cargo vai compilar o backend Rust — isso leva 5–15 minutos dependendo da máquina. Compilações subsequentes usam cache e são muito mais rápidas (~30 segundos).

**Rodar testes:**
```bash
cd HUB

# Testes TypeScript (Vitest)
npm test

# Em modo watch (re-executa ao salvar)
npm run test -- --watch

# Com cobertura
npm run test -- --coverage
```

**Variáveis de ambiente (frontend):**  
Definidas em `HUB/.env` (não commitado). Para dev, os valores padrão no código funcionam sem arquivo `.env`.

```bash
# Exemplo de HUB/.env (opcional)
VITE_AKASHA_URL=http://localhost:7071
VITE_LOGOS_URL=http://localhost:7072
```

**Build de produção:**
```bash
npm run tauri build
# Output: src-tauri/target/release/bundle/
```

---

### 4.6. AETHER

**Stack:** Tauri 2 + React + TypeScript + Rust  
**Porta:** 5174 (Vite dev server, apenas em dev mode)

```bash
cd AETHER

npm install

# Dev mode
npm run tauri dev

# Apenas frontend
npm run dev

# Testes (se houver)
npm test

# Build
npm run tauri build
```

> 📝 O vault do AETHER é privado — nunca indexar essa pasta em AKASHA ou Mnemosyne. Veja a Seção 6 para entender o isolamento de dados.

---

### 4.7. OGMA

**Stack:** Electron + EditorJS + better-sqlite3 + TypeScript  
**Porta:** 5175 (Vite dev, interno ao Electron)

```bash
cd OGMA

npm install

# Dev mode (roda Vite + Electron simultaneamente via concurrently)
npm run dev

# Build de produção
npm run build
```

> ⚠️ **OGMA é Electron, não Tauri.** Isso significa que não há processo Rust — o backend é Node.js puro, com acesso ao sistema de arquivos via APIs nativas do Node. O banco SQLite é acessado via `better-sqlite3` (binding nativo).

O banco `OGMA/data/ogma.db` é criado automaticamente na primeira execução. Logs ficam em `OGMA/data/logs/YYYY-MM-DD.log`.

---

### 4.8. logos/ — ambiente de fine-tuning

O diretório `logos/` não é um app com interface — é uma coleção de scripts Python que rodam como **tarefas P3** (background de baixa prioridade, pausadas quando VRAM > 85%). Eles são invocados programaticamente ou via linha de comando.

**Pré-requisito:** venv de treinamento separado (ver Seção 2.8).

```bash
# Ativar o venv de treinamento
source ~/.venvs/training/bin/activate  # ou o caminho que você escolheu

# A partir da raiz do monorepo:

# 1. Gerar dados de treinamento (Q&A do corpus da Mnemosyne)
python -m logos.training_data_generator
# Saída: {sync_root}/logos/training_data/YYYY-MM-DD.jsonl

# 2. Verificar dependências de treinamento
python -c "from logos.qlora_trainer import check_training_deps; print(check_training_deps())"

# 3. Treinar (QLoRA — exige Unsloth + bitsandbytes instalados)
python -c "
from logos.qlora_trainer import train, TrainerConfig
cfg = TrainerConfig()
result = train(cfg)
print(result)
"

# 4. Converter checkpoint para GGUF (para usar no llama-server)
python -m logos.gguf_converter \
  --input {sync_root}/logos/checkpoints/ultimo/ \
  --output ~/models/meu_modelo.gguf
```

**Ciclo de treinamento completo:**

```
Corpus Mnemosyne (ChromaDB)
         ↓
training_data_generator.py    → pares Q&A em JSONL + âncoras Alpaca/Dolly
         ↓
qlora_trainer.py              → QLoRA r=16/α=16 sobre SmolLM2 1.7B base
  (VramPauseCallback pausa quando VRAM > 85% — libera para P1/P2)
         ↓
checkpoints/ em sync_root     → adapter LoRA salvo a cada N steps
         ↓
gguf_converter.py             → merge LoRA + base → GGUF quantizado
         ↓
llama-server --model meu_modelo.gguf  → modelo disponível via LOGOS
```

**Rodar testes do logos/:**
```bash
# Com o venv de treinamento ativado:
python -m pytest logos/tests/ -v
python -m pytest logos/tests/test_gguf_converter.py -v
```

---

### 4.9. Resumo rápido — comandos por app

| App | Instalar | Rodar (dev) | Testar |
|-----|----------|-------------|--------|
| AKASHA | `cd AKASHA && uv sync` | `uv run python main.py` | `uv run pytest tests/ -v --ignore=tests/integration` |
| Mnemosyne | `pip install -r Mnemosyne/requirements.txt` | `bash Mnemosyne/iniciar.sh` | `python -m pytest Mnemosyne/tests/ -v` |
| KOSMOS | `cd KOSMOS && uv sync` | `uv run main.py` | `uv run pytest tests/ -v` |
| Hermes | `pip install -r Hermes/requirements.txt` | `bash Hermes/iniciar.sh` | `python -m pytest Hermes/tests/ -v` |
| HUB | `cd HUB && npm install` | `npm run tauri dev` | `npm test` |
| AETHER | `cd AETHER && npm install` | `npm run tauri dev` | `npm test` |
| OGMA | `cd OGMA && npm install` | `npm run dev` | `npm test` |
| logos/ | `pip install unsloth trl peft ...` | invocação direta | `python -m pytest logos/tests/ -v` |

> 📦 Para instalar tudo de uma vez: `bash atualizar.sh` na raiz. Ele faz exatamente esses passos na ordem certa.

---

---

## 5. Dependências Completas por App

Esta seção documenta **por que** cada biblioteca foi escolhida, não apenas o que é. Se você precisar trocar uma dependência ou entender o que remover com segurança, este é o lugar certo.

---

### 5.1. AKASHA — dependências Python

Arquivo: `AKASHA/pyproject.toml`

| Biblioteca | Versão mín. | Tipo | Por que foi escolhida |
|-----------|------------|------|----------------------|
| `fastapi` | 0.115 | runtime | Framework web assíncrono; auto-gera documentação OpenAPI; suporte nativo a `asyncio` |
| `uvicorn[standard]` | 0.32 | runtime | Servidor ASGI rápido; `[standard]` inclui `uvloop` e `httptools` para maior throughput |
| `aiosqlite` | 0.20 | runtime | Wrapper assíncrono para SQLite; permite queries sem bloquear o event loop do FastAPI |
| `httpx` | 0.27 | runtime | Cliente HTTP assíncrono para chamadas ao LOGOS, SearXNG, APIs externas |
| `jinja2` | 3.1.x | runtime | Templates HTML server-side; o AKASHA entrega HTML renderizado (não SPA) |
| `python-multipart` | 0.0.12 | runtime | Upload de arquivos nos endpoints FastAPI |
| `ddgs` | 1.0 | runtime | Cliente DuckDuckGo Search — sem API key, acesso web via scraping controlado |
| `qbittorrent-api` | 2024.1 | runtime | Integração com qBittorrent para gerenciar downloads de papers e arquivos |
| `trafilatura` | 1.12 | runtime | Extração de texto limpo de páginas HTML — remove menus, ads, boilerplate |
| `inscriptis` | 2.3 | runtime | Conversor HTML→texto alternativo ao trafilatura (fallback) |
| `markdownify` | 0.13 | runtime | Converte HTML para Markdown para armazenamento e indexação |
| `beautifulsoup4` | 4.12 | runtime | Parse HTML para crawling e extração de metadados |
| `markdown` | 3.7 | runtime | Converte Markdown em HTML para renderização nas templates |
| `aioarxiv` | 0.2 | runtime | Cliente assíncrono para API do arXiv — busca papers científicos |
| `pymupdf4llm` | 0.0.17 | runtime | Extração de texto de PDFs com preservação de estrutura para LLMs |
| `filelock` | 3.13 | runtime | Mutex de arquivo — evita race conditions ao escrever `ecosystem.json` |
| `bm25s` | 0.2 | runtime | Implementação eficiente de BM25 (variante Okapi) para ranking de busca local |
| `langdetect` | 1.0 | runtime | Detecção de idioma dos documentos indexados |
| `nltk` | 3.8 | runtime | Tokenização, stemming e stopwords para preprocessamento de queries |
| `simhash` | 2.1 | runtime | Detecção de páginas duplicadas ou quase-duplicadas por hash de conteúdo |
| `url-normalize` | 1.4 | runtime | Canonicalização de URLs — evita indexar a mesma página com URLs diferentes |
| `flashrank` | 0.2 | runtime | Re-ranker cross-encoder leve — melhora qualidade do top-k sem custo de LLM |
| `sqlite-vec` | 0.1 | runtime | Extensão SQLite para busca vetorial diretamente no banco (sem ChromaDB externo) |
| `sentence-transformers` | 3.0 | runtime | Gera embeddings locais para indexação vetorial (usa modelo via llama-server ou local) |
| `symspellpy` | 6.7 | runtime | Correção ortográfica de queries com dicionário local — melhora recall |
| `imagehash` | 4.3 | runtime | pHash e outros hashes perceptuais para detecção de imagens duplicadas |
| `pybktree` | 1.1 | runtime | Estrutura BK-tree para busca eficiente de imagens similares por distância de Hamming |
| `Pillow` | 10.0 | runtime | Processamento de imagens (redimensionar, converter formatos) |
| `networkx` | 3.0 | runtime | Grafo de conhecimento: PageRank, centralidade, componentes conectados |
| `argostranslate` | 1.11 | runtime | Tradução offline local (sem API key, sem chamada de rede) |

**Dependências de desenvolvimento:**

| Biblioteca | Por que |
|-----------|---------|
| `httpx` | Mock de requisições HTTP nos testes (já é runtime, duplicado no dev) |
| `pytest` | Framework de testes |
| `pytest-asyncio` | Suporte a testes de corrotinas `async def` |

---

### 5.2. Mnemosyne — dependências Python

Arquivo: `Mnemosyne/requirements.txt`

| Biblioteca | Tipo | Por que foi escolhida |
|-----------|------|----------------------|
| `langchain` + `langchain-community` | runtime | Orquestração de chains RAG: recuperação → prompt → LLM → resposta |
| `langchain-chroma` | runtime | Integração LangChain ↔ ChromaDB (vectorstore persistente) |
| `langchain-openai` | runtime | `ChatOpenAI` aponta para LOGOS/llama-server (API OpenAI-compatível local) |
| `langchain-experimental` | runtime | RAPTOR, experimentos de indexação hierárquica |
| `chromadb` | runtime | Vectorstore principal — persiste embeddings em disco, suporta filtros por metadado |
| `pypdf` | runtime | Extração de texto de PDFs |
| `python-docx` | runtime | Leitura de arquivos `.docx` (Word) |
| `ebooklib` | runtime | Leitura de EPUBs |
| `tiktoken` | runtime | Contagem de tokens antes de enviar ao LLM (evita overflow de contexto) |
| `PySide6` | runtime | Framework GUI — Qt6 para Python; escolhido sobre PyQt6 por licença LGPL |
| `rank-bm25` | runtime | BM25 para busca híbrida complementar ao vetorial |
| `beautifulsoup4` + `lxml` | runtime | Parse HTML de páginas web indexadas por sessão |
| `filelock` | runtime | Mutex de arquivo ao escrever `ecosystem.json` |
| `psutil` | runtime | Monitoramento de memória/CPU durante indexação |
| `python-frontmatter` | runtime | Lê metadados YAML dos arquivos `.md` (incluindo Studio outputs) |
| `flashrank` | runtime | Re-ranker cross-encoder para melhorar qualidade dos resultados RAG |
| `httpx` | runtime | Cliente HTTP para `akasha_client.py` (busca web via AKASHA) |
| `bertopic` | runtime | Modelagem de tópicos do corpus (agrupa documentos por tema) |
| `umap-learn` | runtime | Redução dimensional — usado internamente pelo BERTopic |
| `hdbscan` | runtime | Clustering hierárquico — usado internamente pelo BERTopic |
| `scikit-learn` | runtime | Vetorização TF-IDF e utilidades de ML gerais |
| `wordcloud` | runtime | Nuvem de palavras dos tópicos (visualização) |
| `numpy` | runtime | Operações matriciais para embeddings e scores |
| `networkx` | runtime | Grafo de conhecimento extraído dos documentos |
| `lingua-language-detector` | runtime | Detecção de idioma mais precisa que `langdetect` para textos curtos |
| `lightrag-hku` | runtime | LightRAG: combina grafo de conhecimento + RAG vetorial para queries complexas |

---

### 5.3. KOSMOS — dependências Python

Arquivo: `KOSMOS/pyproject.toml`

| Biblioteca | Por que |
|-----------|---------|
| `PySide6` | GUI Qt6 |
| `feedparser` | Parse de feeds RSS e Atom (função principal do KOSMOS) |
| `trafilatura` | Extração de texto completo de artigos referenciados nos feeds |
| `requests` | HTTP síncrono para download de imagens e conteúdo |
| `argostranslate` | Tradução offline de artigos |
| `matplotlib` | Gráficos e visualizações dentro da interface |
| `filelock` | Mutex para `ecosystem.json` |
| `Pillow` | Processamento de imagens dos artigos |
| `html2text` | Conversão HTML → Markdown para armazenamento |

---

### 5.4. Hermes — dependências Python

Arquivo: `Hermes/requirements.txt`

| Biblioteca | Por que |
|-----------|---------|
| `PyQt6` | GUI Qt6 (diferente do PySide6 da Mnemosyne — coexistem no mesmo venv) |
| `yt-dlp` | Download de áudio de YouTube e outros sites para transcrição |
| `faster-whisper` | Transcrição de áudio via Whisper quantizado (CTranslate2) — muito mais rápido que o Whisper original |
| `psutil` | Monitoramento de recursos durante transcrição |

> 💡 **Por que `faster-whisper` e não o Whisper original?** O `faster-whisper` usa CTranslate2, que é 2–4× mais rápido e usa menos memória. Em CPU (Windows), a diferença é ainda maior.

---

### 5.5. HUB — dependências JavaScript e Rust

**Frontend (React + TypeScript):**

| Pacote | Tipo | Por que |
|--------|------|---------|
| `react` + `react-dom` | runtime | UI declarativa; componentes reutilizáveis |
| `react-markdown` | runtime | Renderiza Markdown nos cards do dashboard |
| `@tauri-apps/api` | runtime | Invoca comandos Rust do frontend via `invoke()` |
| `@tauri-apps/plugin-dialog` | runtime | Diálogos nativos de arquivo (open/save) |
| `vite` | dev | Bundler ultrarápido com hot-reload |
| `vitest` | dev | Framework de testes compatível com Vite |
| `typescript` | dev | Tipagem estática — `strict: true` em todo o projeto |

**Backend Rust (src-tauri/):**

| Crate | Por que |
|-------|---------|
| `tauri` | Framework da janela nativa + bridge JS↔Rust |
| `axum` | Servidor HTTP interno (LOGOS proxy) — async, ergonômico |
| `tokio` | Runtime assíncrono Rust (multi-thread) |
| `reqwest` | Cliente HTTP para chamadas ao llama-server |
| `rusqlite` | SQLite em Rust para persistência de configurações |
| `sysinfo` | Leitura de VRAM, CPU, memória do sistema |
| `serde` + `serde_json` | Serialização/deserialização de JSON |
| `thiserror` | Definição ergonômica de erros tipados |
| `chrono` | Data e hora (logs, timestamps) |
| `dirs` | Caminhos de dados do usuário (XDG, AppData) cross-platform |
| `sha2` | Hash SHA-256 para integridade de arquivos |
| `which` | Localiza executáveis no PATH (llama-server, apps do ecossistema) |

---

### 5.6. OGMA — dependências JavaScript

**Runtime:**

| Pacote | Por que |
|--------|---------|
| `@editorjs/editorjs` | Core do editor em blocos |
| `@editorjs/header`, `list`, `code`, `quote`, `table` | Blocos de conteúdo básicos |
| `@editorjs/image`, `marker`, `inline-code`, `delimiter` | Blocos ricos |
| `@editorjs/checklist` | Listas de tarefas |
| `editorjs-drag-drop` | Drag & drop entre blocos |
| `editorjs-toggle-block` | Blocos colapsáveis (acordeão) |
| `better-sqlite3` | SQLite síncrono nativo para Node.js — performance máxima para notas |
| `electron-store` | Persistência de configurações simples (JSON) |
| `neverthrow` | Tipo `Result<T, E>` para tratamento de erros sem exceções |

**Dev:**

| Pacote | Por que |
|--------|---------|
| `electron` | Framework da janela desktop |
| `electron-builder` | Empacota o app para distribuição |
| `concurrently` | Roda Vite + Electron juntos em dev mode |
| `wait-on` | Aguarda o Vite estar pronto antes de abrir o Electron |
| `zustand` | Gerenciamento de estado global no renderer process |

---

### 5.7. logos/ — dependências de treinamento

> ⚠️ Estas dependências **não estão nos venvs do ecossistema** — requerem instalação separada. Ver Seção 2.8 para instruções completas.

| Biblioteca | Por que é necessária no pipeline de fine-tuning |
|-----------|------------------------------------------------|
| `torch` | Framework de deep learning; base para todos os outros |
| `unsloth` | Wrapper para QLoRA otimizado — reduz uso de VRAM em 60–70% via kernels especializados (Flash Attention 2, gradient checkpointing agressivo) |
| `bitsandbytes` | Quantização NF4/INT8 — carrega modelo em 4-bit, multiplica por 8 o tamanho máximo de modelo na VRAM disponível |
| `transformers` | Carrega modelos HuggingFace (SmolLM2, Qwen, Llama) e gerencia tokenização |
| `trl` | Contém o `SFTTrainer` (Supervised Fine-Tuning) — abstrai o loop de treinamento |
| `peft` | Gerencia os adapters LoRA — salva/carrega os pesos delta sem duplicar o modelo base |
| `datasets` | Carrega JSONL de pares Q&A, aplica formatting de chat templates, shuffle/split |
| `accelerate` | Gerencia device placement (GPU/CPU), mixed precision, gradient accumulation |

**Por que QLoRA e não full fine-tuning?**

Full fine-tuning de um modelo 7B requer ~28 GB de VRAM (pesos em fp16 + gradientes + optimizer states). A RX 6600 tem 8 GB. QLoRA resolve isso em três camadas:

1. O modelo base é carregado em NF4 (4-bit) → ~2–3 GB VRAM
2. Apenas os adapters LoRA são treinados em bf16 → ~0.5–1 GB VRAM
3. Gradient checkpointing recomputa ativações on-demand → reduz pico de memória

Trade-off: treinamento ~2× mais lento que bf16, mas viável em hardware de consumo.

---

### 5.8. Biblioteca compartilhada (raiz)

Arquivos na raiz importados por múltiplos apps — sem dependências adicionais além do que cada app já tem instalado:

| Arquivo | Dependências externas usadas |
|---------|------------------------------|
| `ecosystem_client.py` | `filelock` (opcional) — funciona sem ele com aviso |
| `ecosystem_logging.py` | stdlib apenas (`logging`, `pathlib`) |
| `ecosystem_qt.py` | nenhuma — gera QSS como string pura |
| `ecosystem_scraper.py` | `trafilatura`, `httpx` |
| `hardware_probe.py` | `subprocess`, `pathlib` — sem dependências externas |
| `vram_monitor.py` | `subprocess` (lê `rocm-smi` ou `nvidia-smi`) |
| `shared_topic_profile.py` | stdlib apenas |

---

### 5.9. APIs externas usadas pelo AKASHA

O AKASHA acessa APIs externas para busca web e cards informativos. **Nenhuma requer chave de API** — todas são gratuitas ou auto-hospedadas.

| Serviço | URL base | Chave? | Rate limit | Fallback | Como configurar |
|---------|----------|--------|-----------|---------|----------------|
| **DuckDuckGo** | `ddgs` (lib) | Não | ~1 req/s por IP | SearXNG | Automático — primária |
| **SearXNG** | configurável | Não | dependente da instância | DDG | `akasha.searxng_url` no `ecosystem.json` |
| **arXiv** | `export.arxiv.org` | Não | ~3 req/s | — | `aioarxiv` — automático |
| **Wikipedia** | `*.wikipedia.org/w/api.php` | Não | gentil | — | Automático |
| **Open-Meteo** | `api.open-meteo.com` | Não | 10k req/dia | — | Automático |
| **Nominatim** | `nominatim.openstreetmap.org` | Não | **1 req/s** (rigoroso) | — | Automático; User-Agent obrigatório |
| **Invidious** | configurável | Não | dependente da instância | — | `akasha.invidious_instance` no `ecosystem.json` |
| **LibreTranslate** | `libretranslate.com` | Público gratuito | limitado | argostranslate local | Fallback automático |
| **argostranslate** | local (offline) | Não | ilimitado | — | Primária para tradução |
| **Hugging Face Hub** | `huggingface.co` | Não (modelos públicos) | generoso | — | Download manual de modelos |

> ⚠️ **Nominatim tem rate limit rigoroso de 1 req/s** e exige `User-Agent` identificando o app. Violações resultam em bloqueio de IP. O `weather_widget.py` já respeita isso com throttling.

> 🔒 **Privacidade:** DuckDuckGo e SearXNG não rastreiam. Wikipedia é read-only. Open-Meteo não coleta dados do usuário. A query enviada a qualquer API nunca inclui dados pessoais do índice local.

---

---

## 6. Arquitetura de Dados

Esta seção descreve onde cada dado vive, em qual formato, e como flui entre os apps. Se você precisar fazer backup, migrar entre máquinas, ou entender por que um dado sumiu, comece aqui.

---

### 6.1. Mapa geral dos dados

```
┌─────────────────────────────────────────────────────────────────┐
│                       sync_root/ (Syncthing)                    │
│  Dados persistentes compartilhados entre máquinas               │
│                                                                 │
│  akasha/akasha.db        ← banco principal do AKASHA            │
│  mnemosyne/chroma_db/    ← vectorstore ChromaDB                 │
│  mnemosyne/docs/         ← documentos monitorados               │
│  mnemosyne/notebooks/    ← notebooks (metadata, histórico)      │
│  aether/                 ← vault de escrita                     │
│  ogma/ogma.db            ← notas do OGMA                        │
│  hermes/                 ← transcrições                         │
│  logos/training_data/    ← JSONL de pares Q&A                   │
│  logos/checkpoints/      ← checkpoints de modelos treinados     │
│  .ai_private/            ← memória pessoal das IAs (privado)    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│               ~/.local/share/ecosystem/ (local por máquina)     │
│                                                                 │
│  ecosystem.json          ← fonte de verdade do ecossistema      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      Dados efêmeros (locais)                    │
│                                                                 │
│  Mnemosyne/logs/         ← logs rotativos                       │
│  OGMA/data/logs/         ← logs diários                         │
│  AKASHA/data/archive/    ← cache de páginas arquivadas          │
│  AKASHA/.venv/           ← ambiente virtual (nunca commitar)    │
│  HUB/src-tauri/target/   ← build Rust (nunca commitar)         │
└─────────────────────────────────────────────────────────────────┘
```

---

### 6.2. Banco de dados principal: `akasha.db`

O AKASHA usa um único banco SQLite para tudo — crawl, busca, memória do assistente, cache, perfil de interesses. O banco fica em `{akasha.data_path}/akasha.db` (configurado via `ecosystem.json`).

**Configuração PRAGMA (definida em `database.py:init_db()`):**

```sql
PRAGMA journal_mode=WAL;      -- leituras não bloqueiam escritas (crítico para crawl + busca simultâneos)
PRAGMA synchronous=NORMAL;    -- seguro contra crash, 3x mais rápido que FULL
PRAGMA cache_size=-8000;      -- 8 MB de page cache em memória
PRAGMA mmap_size=67108864;    -- 64 MB de mmap para leituras sequenciais rápidas
```

**Tabelas agrupadas por função:**

**Busca e cache:**

| Tabela | Descrição |
|--------|-----------|
| `searches` | Histórico de queries executadas (query, sources, result_count, created_at) |
| `search_history` | Histórico persistente de busca com frequência e last_used |
| `search_cache` | Cache dois níveis: TTL 24h para queries frequentes, 1h para esporádicas. Indexado por `query_hash` (SHA-256) |
| `search_profile` | Preferências de busca da usuária (pesos, filtros, modelos preferidos) |

**Índice local (documentos da máquina):**

| Tabela | Descrição |
|--------|-----------|
| `local_fts` | Tabela FTS5 virtual — busca full-text em arquivos locais. Tokenizador `unicode61 remove_diacritics 2` |
| `local_index_meta` | Metadados dos arquivos indexados: path, mtime, source, lang, deleted |
| `local_vec_paths` | Paths cujos embeddings vetoriais foram gerados (complementa `local_fts`) |
| `archive_simhashes` | SimHash de conteúdo — detecta duplicatas quase-idênticas antes de indexar |
| `archive_dois` | DOIs de artigos científicos indexados |
| `doc_accesses` | Acesso por URL (frequência + timestamp) — alimenta scoring de relevância |
| `highlights` | Trechos marcados pela usuária + FTS5 `highlights_fts` |
| `doc_citations` | Relações de citação entre documentos (DOI citing → DOI cited) |

**Crawler e biblioteca (sites):**

| Tabela | Descrição |
|--------|-----------|
| `crawl_sites` | Sites monitorados: URL base, profundidade, intervalo, status, próximo crawl |
| `crawl_pages` | Páginas baixadas: URL, título, conteúdo em Markdown, hash, ETag, timestamps |
| `crawl_fts` | Tabela FTS5 virtual para busca full-text no conteúdo crawleado |
| `page_images` | Imagens das páginas: URL, alt text, pHash para deduplicação |
| `page_images_fts` | FTS5 no alt text das imagens |
| `page_links` | Grafo de links: source_url → target_url (para PageRank) |
| `page_rank` | Scores de PageRank pré-calculados por domínio |
| `site_suggestions` | Sites sugeridos para adicionar à biblioteca |
| `blocked_domains` | Domínios bloqueados (nunca rastrear, nunca mostrar) |
| `favorite_domains` | Domínios favoritos com score de prioridade manual |
| `domain_boosts` | Boosts de ranking manual por domínio |
| `wiki_citation_counts` | Quantas vezes um domínio é citado em artigos da Wikipedia relevantes |

**Downloads e vídeos:**

| Tabela | Descrição |
|--------|-----------|
| `downloads` | Fila de downloads: URL, destino, tamanho, status, progresso |
| `watch_later` | Vídeos salvos para ver depois + FTS5 `watch_later_fts` |

**Aprendizado e personalização:**

| Tabela | Descrição |
|--------|-----------|
| `click_log` | Cliques da usuária em resultados (URL, query, posição, timestamp) |
| `topic_interest_profile` | Perfil de interesses por tópico (score de afinidade acumulado) |
| `entity_graph` | Entidades extraídas e suas relações (Akasha) |
| `tag_pairs` | Pares de tags co-ocorrentes (para expansão de query) |
| `lenses` | Filtros de busca salvos (combinação de fontes, domínios, tipos) |
| `activity_log` | Log geral de atividade (crawl, indexação, eventos do assistente) |

**Memória privada do Akasha:**

```sql
CREATE TABLE personal_memory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    type       TEXT    NOT NULL,   -- 'observation' | 'reflection' | 'insight' | 'akasha_insight'
    content    TEXT    NOT NULL,
    tags       TEXT    NOT NULL DEFAULT '[]',  -- JSON array de strings
    feedback   TEXT    DEFAULT NULL            -- feedback da usuária nos pop-ups
);
```

> ⚠️ `personal_memory` está no mesmo `akasha.db`, mas é **logicamente isolada** — nunca é lida pelo FTS5, nunca aparece nos resultados de busca, nunca é exposta via API pública.

**Caches auxiliares:**

| Tabela | TTL | O que armazena |
|--------|-----|----------------|
| `wiki_cache` | variável | Cards da Wikipedia (hash de query → JSON) |
| `geo_cache` | permanente | Coordenadas de cidades (Nominatim) |
| `settings` | permanente | Configurações chave-valor (qBittorrent host/port, preferências) |

---

### 6.3. Vectorstore do AKASHA: `sqlite-vec`

Além do FTS5, o AKASHA mantém um índice vetorial diretamente no SQLite usando a extensão `sqlite-vec`. Os embeddings ficam na mesma `akasha.db` — sem banco separado.

```
akasha.db
  ├── local_fts      (FTS5 — busca por palavras)
  ├── crawl_fts      (FTS5 — busca por palavras)
  └── [vec tables]   (sqlite-vec — busca semântica)
```

Vantagem: uma única conexão, um único arquivo de backup, transações ACID cobrindo ambos os índices simultaneamente.

---

### 6.4. Dados da Mnemosyne

A Mnemosyne usa **três tipos de armazenamento independentes**, cada um com um propósito:

**A. ChromaDB (vectorstore persistente)**

Localização: `{mnemosyne.chroma_dir}` → `sync_root/mnemosyne/chroma_db/`

Armazena os embeddings dos documentos indexados pela usuária (PDFs, EPUBs, Markdown, web). Cada coleção é um "assunto" separado — livros, artigos, notas pessoais, etc. Consultado via LangChain durante o RAG.

```
chroma_db/
├── [collection-uuid]/          → uma coleção = um tema
│   ├── chroma.sqlite3          → metadados internos do Chroma
│   └── data_level0.bin         → vetores de embedding (HNSW)
└── ...
```

**B. Notebooks (sistema de arquivos)**

Localização: `{mnemosyne.data_dir}/notebooks/{uuid}/`

Cada notebook é um diretório com quatro arquivos fixos:

```
notebooks/
└── a3f7e2b1-...-notebook-uuid/
    ├── metadata.json       → campos do dataclass Notebook
    ├── history.jsonl       → mensagens da conversa (append-only)
    ├── memory.json         → contexto RAG comprimido da sessão
    └── studio/             → outputs do Studio (arquivos .md)
        ├── 2026-05-10_resumo.md
        ├── 2026-05-11_mapa_mental.md
        └── ...
```

**`metadata.json`** — exemplo:
```json
{
  "id": "a3f7e2b1-...",
  "name": "Filosofia da Mente",
  "created_at": "2026-05-01T14:32:10",
  "updated_at": "2026-05-23T09:15:44",
  "collection_names": ["filosofia", "cognicao"],
  "description": "Notas sobre consciência e computação",
  "themes": ["mente", "computação", "fenomenologia"],
  "keywords": ["qualia", "intentionality", "functionalism"]
}
```

**`history.jsonl`** — uma mensagem por linha (append-only):
```jsonl
{"role": "user", "content": "O que é qualia?", "ts": "2026-05-23T09:10:00"}
{"role": "assistant", "content": "Qualia são...", "ts": "2026-05-23T09:10:04", "sources": ["filosofia/chalmers.pdf"]}
```

**Studio outputs** — arquivos `.md` com frontmatter:
```markdown
---
source: mnemosyne_studio
type: resumo
notebook_id: a3f7e2b1-...
created_at: 2026-05-23T09:15:44
---

# Resumo: Filosofia da Mente

...
```

> O campo `source: mnemosyne_studio` faz o indexador atribuir `source_type = "thought"` com peso próprio no RAG — sinalizando que é uma análise gerada pela própria Mnemosyne, não uma fonte externa.

**C. Memória pessoal (`personal_memory.db`)**

Localização: `{mnemosyne.data_dir}/personal_memory.db`

SQLite separado do ChromaDB e dos notebooks. Contém reflexões, observações e insights da Mnemosyne — nunca indexados no RAG, nunca expostos à busca.

Categories:
- `"friendship"` — memórias trocadas com o Akasha
- `"about_user"` — observações sobre a usuária e seu modo de trabalhar
- `"interests"` — tópicos marcantes na indexação
- `"reflections"` — pensamentos da Mnemosyne sobre o próprio conhecimento
- `"world"` — observações gerais

---

### 6.5. Dados de treinamento (logos/)

**Formato:** JSONL, ChatML

Cada linha é um exemplo de treinamento completo:

```jsonl
{"messages": [{"role": "system", "content": "You are a knowledgeable assistant..."}, {"role": "user", "content": "O que é atenção em transformers?"}, {"role": "assistant", "content": "Atenção é o mecanismo que..."}]}
```

**Âncoras (10–15% do dataset):** exemplos do Alpaca/Dolly para preservar capacidade geral do modelo. Sem elas, o fine-tuning "colapsa" o modelo para o domínio do corpus (esquece tudo que não está nos seus documentos).

**Localização:** `sync_root/logos/training_data/YYYY-MM-DD.jsonl`

**Checkpoints:** `sync_root/logos/checkpoints/` — adapter LoRA salvo a cada N steps. Cada checkpoint é um diretório com `adapter_model.safetensors` e `adapter_config.json`.

---

### 6.6. Fluxo de dados entre apps

**AKASHA → Mnemosyne (insights do assistente):**
```python
# Em AKASHA/services/session_insight.py:
ecosystem_client.send_insight_to_akasha(insight_text)
# → POST http://mnemosyne-host/friendship/insight
# → AKASHA/services/friendship_receiver.py processa e salva em personal_memory
```

**Mnemosyne → AKASHA (busca web):**
```python
# Em Mnemosyne/core/akasha_client.py:
results = akasha_client.search(query)
# → GET http://localhost:7071/search?q={query}&sources=web
# → usado durante RAG de sessão para enriquecer contexto com web
```

**HUB → todos os apps (configuração):**
```
HUB escreve ecosystem.json
  ↓
ecosystem_client.read_ecosystem() — chamado em startup de cada app
  ↓
Cada app lê seus próprios caminhos e configurações
```

**Apps → LOGOS (inferência LLM):**
```python
# Via ecosystem_client:
response = ecosystem_client.request_llm(model, messages, app="mnemosyne", priority=2)
# → POST http://localhost:7072/v1/chat/completions
# → LOGOS coloca na fila com prioridade P1/P2/P3
# → encaminha ao llama-server em :8080
```

---

### 6.7. Convenções de formato e nomenclatura

**Timestamps:** sempre ISO 8601 em UTC ou local com offset — `"2026-05-23T09:15:44"`. SQLite armazena como TEXT.

**JSON arrays em SQLite:** campos como `tags`, `subdomains_json` armazenam JSON como TEXT. Sempre serializar com `json.dumps()` e deserializar com `json.loads()` — nunca concatenar strings.

**Markdown como formato de armazenamento:** conteúdo de páginas crawleadas é armazenado em Markdown (`content_md`) — não HTML bruto. Isso comprime melhor, é mais legível para debugging e é consumido diretamente pelo LLM sem preprocessamento.

**IDs de notebooks:** UUID4 gerado na criação. Servem também de nome de diretório — `Path(data_dir) / "notebooks" / notebook.id`.

**Nomes de arquivos de treinamento:** `YYYY-MM-DD.jsonl` — data de geração. O trainer sempre lê o mais recente via `sorted(glob("*.jsonl"))[-1]`.

---

### 6.8. O que nunca deve ser commitado

O `.gitignore` já cobre esses casos, mas é importante entender o porquê:

| Tipo | Por quê não commitar |
|------|---------------------|
| `akasha.db` | Contém dados pessoais de navegação e memória da IA |
| `personal_memory.db` | Memória pessoal — totalmente privada |
| `chroma_db/` | Centenas de MB; gerado a partir dos documentos da usuária |
| `checkpoints/` | Dezenas de GB; derivados do treinamento |
| `ecosystem.json` | Caminhos específicos da máquina; nunca iguais entre máquinas |
| `*.jsonl` (training_data) | Dados gerados a partir do corpus pessoal |
| `.venv/`, `target/`, `node_modules/` | Gerados automaticamente pelo instalador |

---

---

## 7. Pipeline de Busca (AKASHA)

Esta seção descreve a jornada completa de uma query desde o momento em que a usuária pressiona Enter até a página de resultados ser renderizada — com o arquivo e a função exatos em cada etapa.

> 🔑 **Lembre-se:** o LLM (Akasha, assistente) age **apenas** nas etapas de classificação de intenção e expansão de query — e mesmo assim de forma opcional, com fallback lexical. O ranqueamento, a busca e a renderização são puramente deterministas, sem IA generativa no caminho crítico.

---

### 7.1. Mapa do pipeline

```
Usuária digita query e pressiona Enter
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  routers/search.py — GET /search?q={query}&sources={all|web|local}
│                                                                 │
│  1. Registra a query (record_search_query)                      │
│  2. Correção ortográfica (correct_query) — opcional             │
│  3. Classificação lexical de intenção (classify_intent_lexical) │
│  4. Classificação LLM de intenção (classify_intent) — opcional  │
│  5. Verifica necessidade de reescrita (needs_rewrite)           │
│  6. Reescrita conversacional (rewrite_query) — se necessário    │
│  7. Roteamento para widgets/abas (_get_intent_routing)          │
└────────────────────────┬────────────────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
    ┌──────────────────┐  ┌──────────────────────────┐
    │  Busca LOCAL     │  │  Busca WEB               │
    │  (ferramenta)    │  │  (ferramenta)             │
    │                  │  │                          │
    │  FTS5 local      │  │  cache L1: memória LRU   │
    │  FTS5 crawl      │  │  cache L2: SQLite TTL    │
    │  sqlite-vec      │  │  SearXNG (se configurado)│
    │  ChromaDB        │  │  DDG (fallback)           │
    │  highlights      │  │  arXiv (papers)           │
    │       ↓          │  │  Invidious (vídeos)       │
    │      RRF         │  │         ↓                │
    │  PageRank boost  │  │  filter blocked domains  │
    │  Domain boost    │  └──────────────────────────┘
    │  Freshness decay │
    │  Usage boost     │
    │  Annotation dens.│
    │  Re-ranking opt. │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │  Fusão final     │
    │  (resultados     │
    │   web + local)   │
    │  diversificação  │
    │  por domínio     │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │  Jinja2 render   │
    │  templates/      │
    │  search.html     │
    └──────────────────┘
             │
             ▼
   Página de resultados
   (links, trechos, cards)
   — NUNCA síntese ou resposta gerada —
```

---

### 7.2. Etapa 1 — Recebimento e registro

**Arquivo:** `routers/search.py`  
**Função:** handler do `GET /search`

A query chega via parâmetro `q` na URL. O parâmetro `sources` controla quais fontes são consultadas: `all` (padrão), `web`, `local`.

```python
# routers/search.py — simplificado
@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = "", sources: str = "all"):
    query = q.strip()
    await record_search_query(query, sources)  # registra em searches + search_history
    ...
```

O perfil de busca da usuária é carregado via `load_profile()` e pode ajustar quais fontes têm prioridade com base em preferências salvas.

---

### 7.3. Etapa 2 — Correção ortográfica (opcional)

**Arquivo:** `services/local_search.py`  
**Função:** `correct_query(query: str) -> str | None`

Se habilitado (`SPELLCHECK_ENABLED = False` por padrão), usa `symspellpy` com dicionário local para sugerir correção. Retorna `None` se a query parece correta — nunca altera a query original automaticamente. A sugestão é exibida como "Você quis dizer: X?" na interface.

> Por padrão desabilitado em produção porque o dicionário padrão do symspellpy é em inglês. Habilitar apenas com dicionário em português configurado.

---

### 7.4. Etapa 3 — Classificação lexical de intenção (sem LLM)

**Arquivo:** `services/query_understanding.py`  
**Função:** `classify_intent_lexical(query: str) -> IntentTypeLexical`

Classifica a query em um dos tipos abaixo usando apenas regras e listas de palavras-chave — zero chamada de LLM, zero latência de rede:

| Tipo | Descrição | Exemplos |
|------|-----------|---------|
| `navigational` | Query é uma URL ou nome de site | `github.com`, `wikipedia` |
| `informational` | Pergunta factual (o que é, como funciona) | `o que é atenção em transformers` |
| `exploratory` | Pesquisa aberta, exploratória | `machine learning aplicações` |
| `visual` | Imagens, fotos, logos | `foto do telescópio james webb` |
| `weather` | Clima e previsão do tempo | `tempo em porto alegre amanhã` |
| `translation` | Tradução de texto | `traduzir "hello" para português` |
| `video` | Vídeos | `tutorial python asyncio` |

**Como funciona:** verifica prefixos informativos (`"o que é"`, `"how to"`), tokens visuais (`"foto"`, `"image"`), padrões de clima, termos de tradução, e presença de TLDs para navegacional. Ordem de verificação importa — `translation` é verificada antes de `informational` porque algumas frases de tradução começam com prefixos informativos.

O resultado alimenta `_get_intent_routing()` que decide quais **widgets** aparecer na interface (card da Wikipedia, card de clima, card de tradução, etc.):

```python
# routers/search.py
def _get_intent_routing(lexical_intent, query):
    return {
        "wiki":        lexical_intent == "informational" and len(query.split()) >= 2,
        "images":      lexical_intent == "visual",
        "weather":     lexical_intent == "weather",
        "translation": lexical_intent == "translation",
        "video":       lexical_intent == "video",
    }
```

---

### 7.5. Etapa 4 — Classificação LLM de intenção (Akasha, opcional)

**Arquivo:** `services/query_understanding.py`  
**Função:** `classify_intent(query: str, model: str = "") -> IntentType`

Quando o assistente Akasha está disponível (modelo leve ~3B em VRAM), classifica a intenção em três categorias mais ricas:

- `fact-seeking` — quer um fato específico e verificável
- `exploratory` — quer explorar um tema sem pergunta definida
- `navigational` — quer chegar em um lugar específico

Essa classificação de segundo nível informa **como** os resultados são ranqueados: queries `fact-seeking` priorizam fontes primárias (PAPER, AKASHA); queries `exploratory` priorizam diversidade de domínios.

> O modelo é mantido em VRAM durante uma sessão via `pin_model()` / `release_model()`, evitando o cold-start de 2–5s a cada query. Liberado automaticamente após inatividade via timer (`SESSION_IDLE_S`).

---

### 7.6. Etapa 5 — Reescrita de query (Akasha, opcional)

**Arquivo:** `services/query_understanding.py`  
**Funções:** `needs_rewrite(query)`, `rewrite_query(query, context, model)`

`needs_rewrite()` verifica lexicalmente se a query contém pronomes anafóricos ("ele", "isso", "esse tema") que só fazem sentido em contexto de conversa. Se sim, `rewrite_query()` usa o LLM para substituir as referências pelo conteúdo explícito com base nas últimas queries da sessão.

**Exemplo:**
```
query 1: "transformers em NLP"
query 2: "como ele funciona internamente"  ← needs_rewrite = True
→ rewrite: "como o transformer em NLP funciona internamente"
```

A query reescrita é usada para a busca; a original é preservada para exibição na interface.

---

### 7.7. Etapa 6 — Busca local

**Arquivo:** `services/local_search.py`  
**Função:** `search_local(query, k, sources, db) -> list[SearchResult]`

A busca local consulta **cinco fontes em paralelo** e combina os resultados via RRF:

| Fonte | Como funciona | Peso |
|-------|--------------|------|
| `local_fts` | FTS5 em arquivos locais (Mnemosyne, KOSMOS, AETHER, Hermes) | varia por source |
| `crawl_fts` | FTS5 em páginas crawleadas | AKASHA: 1.4 |
| `sqlite-vec` | Busca KNN por embedding (desativado por padrão) | — |
| ChromaDB | Busca semântica vetorial (Mnemosyne) | MNEMOSYNE: 1.1 |
| `highlights` | Trechos marcados explicitamente | HIGHLIGHT: 1.6 |

**Pesos por tipo de fonte (`SOURCE_WEIGHTS`):**

```python
SOURCE_WEIGHTS = {
    "PAPER":     2.0,   # artigos científicos — máxima densidade informacional
    "HIGHLIGHT": 1.6,   # marcações explícitas da usuária
    "AKASHA":    1.4,   # páginas arquivadas intencionalmente
    "KOSMOS":    1.2,   # arquivo pessoal
    "OBSIDIAN":  1.2,   # vault Obsidian / Mnemosyne
    "MNEMOSYNE": 1.1,   # busca semântica ChromaDB
    "HERMES":    1.0,   # transcrições automáticas
    "DEPOIS":    1.0,   # salvo para ler depois
}
```

---

### 7.8. O algoritmo RRF

**Arquivo:** `services/local_search.py`  
**Função:** `_rrf(rankings, k=60, weight_fn=None) -> list[SearchResult]`

Reciprocal Rank Fusion combina múltiplas listas de resultados em uma única lista ranqueada sem precisar de scores normalizados entre as fontes:

```
score_rrf(documento d) = Σ  1 / (k + rank_em_lista_i(d))
                        para cada lista i que contém d
```

Com k=60 (constante de suavização): um documento que aparece em primeiro lugar em todas as listas acumula score alto; um que aparece só em uma lista tem score baixo. O k=60 evita que o primeiro lugar domine demais — diferença entre rank 1 e rank 10 é pequena em termos absolutos.

Após o RRF, o `weight_fn` multiplica o score pelo peso da fonte (`SOURCE_WEIGHTS`), priorizando artigos científicos e highlights sobre transcrições automáticas.

---

### 7.9. Etapa 7 — Pós-ranqueamento

Após o RRF, quatro sinais adicionais ajustam o ranking final:

**A. PageRank boost** (`local_search.py:_apply_pagerank_boost()`)

Domínios com maior PageRank interno (calculado a partir do grafo de links em `page_links`) sobem no ranking. Formula: `score_final = score_rrf × (1 + pagerank_normalizado)`.

**B. Domain boost por cliques** (`local_search.py:_apply_domain_boost()`)

Domínios em que a usuária clicou com frequência recebem boost proporcional à taxa de cliques histórica. Aprende implicitamente as preferências sem configuração explícita.

**C. Freshness decay** (`services/freshness.py:apply_freshness_rerank()`)

Ativado **apenas se** `is_temporal_query(query) == True` (a query contém termos temporais como "hoje", "recente", "2026", "últimos"). Documentos mais antigos recebem penalidade exponencial — `score × e^(-λt)` onde t é a idade em dias e λ é a taxa de decaimento.

**D. Usage boost + annotation density** (`local_search.py`)

Dois sinais personalizados:
- **Usage**: documentos acessados frequentemente sobem (`USAGE_RANKING_ALPHA = 0.7`)
- **Annotation density**: documentos com mais highlights pessoais sobem modestamente (`β × log(1 + highlight_count)`, `ANNOTATION_DENSITY_BETA = 0.1`)

**E. Re-ranking cross-encoder (opcional)** — `RERANKING_ENABLED = False`

FlashRank com modelo `ms-marco-TinyBERT-L-2-v2` (~4MB) re-ordena os top-30 resultados por relevância semântica real (não apenas por palavras-chave). Desativado por padrão porque adiciona ~200ms de latência e pode ser lento em máquinas sem AVX2.

---

### 7.10. Etapa 8 — Busca web com cache dois níveis

**Arquivo:** `services/web_search.py`  
**Função:** `search_web(query, max_results, db) -> list[SearchResult]`

```
query
  │
  ▼
L1: _MemCache (LRU, max 100, TTL por entrada)
  │ cache hit → retorna imediatamente
  ▼ cache miss
L2: SQLite search_cache (TTL 1h padrão, 24h para queries frequentes)
  │ cache hit → retorna e atualiza L1
  ▼ cache miss
SearXNG (se akasha.searxng_url configurado no ecosystem.json)
  │ falha ou não configurado
  ▼
DuckDuckGo (via biblioteca ddgs)
  │
  ▼
filter blocked domains
  │
  ▼
_set_db_cache + _mem_cache.set
  │
  ▼
retorna list[SearchResult]
```

**TTL adaptativo:** `_get_ttl_hours()` consulta `searches` dos últimos 7 dias — se a query foi feita ≥3 vezes, TTL = 24h (query popular, cache mais duradouro). Caso contrário, TTL = 1h.

---

### 7.11. Etapa 9 — Diversificação e fusão final

**Arquivo:** `routers/search.py`  
**Função:** `_diversify_by_domain(results, max_per_domain=2)`

Antes de renderizar, os resultados combinados passam pela diversificação: no máximo 2 resultados por domínio são mantidos. Isso evita que um único site domine a primeira página de resultados em queries exploratórias.

---

### 7.12. Etapa 10 — Renderização

**Arquivo:** `templates/search.html` (e partials em `_*.html`)  
**Motor:** Jinja2 server-side

O template recebe:
- `results`: lista de `SearchResult` ranqueados
- `routing`: dict de flags para widgets (wiki, images, weather, etc.)
- `query`: query original (e reescrita, se houver)
- `sources`: fontes consultadas

Cada widget (card da Wikipedia, card de clima, card de tradução) é renderizado **apenas se** a flag correspondente em `routing` for `True`. Isso evita chamadas desnecessárias a APIs externas.

> 🚫 **Nenhuma síntese é gerada aqui.** O template exibe links, títulos e trechos — nunca texto gerado pelo LLM como "resposta" à query. O princípio arquitetural do AKASHA: devolver fontes, não criar conteúdo.

---

### 7.13. O crawler — como as páginas chegam ao índice local

**Arquivo:** `services/crawler.py`

O crawler popula as tabelas `crawl_sites` e `crawl_pages` de forma assíncrona e independente da busca. Funciona em background — nunca bloqueia uma query em andamento.

**Ciclo de vida de um site:**
```
Usuária adiciona domínio via /library
  ↓
crawl_sites inserido com status='idle'
  ↓
crawler_scheduler.py detecta sites com next_crawl_at <= now
  ↓
crawler.py:crawl_site(site_id)
  ├── lê robots.txt do domínio
  ├── para cada URL (BFS até crawl_depth):
  │   ├── _rate_limit(domain) → aguarda delay adaptativo
  │   ├── baixa o HTML via httpx
  │   ├── extrai texto com trafilatura → content_md
  │   ├── calcula content_hash (SHA-256)
  │   ├── verifica duplicata via simhash
  │   ├── insere/atualiza crawl_pages
  │   └── atualiza crawl_fts
  └── atualiza next_crawl_at = now + crawl_interval_days
```

**Politeness (comportamento respeitoso):**

| Mecanismo | Implementação |
|-----------|--------------|
| `robots.txt` | Lido e cacheado por domínio; paths disallowed são ignorados |
| Delay adaptativo | Mín. 0.5s, máx. 30s; ajustado pela média do response time do servidor |
| Backoff em 429 | Delay aumenta para `_MAX_DELAY` (30s) ao receber "Too Many Requests" |
| User-Agent declarado | `"Mozilla/5.0 (compatible; AKASHA-crawler/1.0)"` |
| ETag/Last-Modified | Verifica se conteúdo mudou antes de re-baixar |

---

### 7.14. Expansão de query por PRF (opcional)

**Arquivo:** `services/query_expansion.py`  
**Ativado via:** `PRF_ENABLED` flag em `local_search.py`

Pseudo-Relevance Feedback: pega os top-3 resultados do primeiro round de busca, extrai os termos mais relevantes, e executa uma segunda busca com a query expandida. Os dois rankings são fundidos via RRF, mantendo a query original como âncora.

```
query: "atenção em transformers"
  ↓ busca inicial → top-3: ["self-attention", "query key value", "scaled dot-product"]
  ↓ expansão: "atenção em transformers self-attention query key value"
  ↓ segunda busca → resultados adicionais
  ↓ RRF das duas listas → lista final
```

---

Seção 7 concluída. Aguardando confirmação para a próxima.

---

## 🤖 Seção 8: Infraestrutura de LLMs Locais e Treinamento (Akasha)

Esta seção descreve como o ecossistema gerencia modelos de linguagem localmente — desde o proxy que serializa as chamadas até o pipeline completo de fine-tuning que personaliza os modelos com o corpus da usuária.

> ⚠️ **Distinção importante:** aqui estamos na camada de infraestrutura compartilhada por todos os apps. O LOGOS não é uma IA — é um gerenciador de recursos. A Akasha (o assistente com personalidade) é uma das entidades que usa essa infraestrutura, mas o LOGOS serve igualmente a Mnemosyne, KOSMOS, e Hermes.

---

### 8.1. O que é o LOGOS e por que ele existe

Sem um proxy central, vários apps tentariam usar o LLM ao mesmo tempo. O resultado seria:
- O modelo sendo descarregado e recarregado a cada troca de app (cada carregamento leva 2–10 segundos)
- VRAM esgotada por dois modelos simultâneos (ex: Mnemosyne RAG + KOSMOS análise)
- Tarefas de background (indexação) competindo com o chat interativo

O LOGOS (`HUB/src-tauri/src/logos.rs`) resolve isso expondo um servidor HTTP em `127.0.0.1:7072` que:
1. **Serializa** todas as chamadas de inferência numa **fila de prioridades** (P1 > P2 > P3)
2. **Protege** recursos de hardware com guards automáticos (VRAM, CPU, RAM, bateria)
3. **Gerencia** o processo `llama-server` diretamente — inicia, monitora e descarrega modelos
4. **Traduz** entre formatos de API (Ollama legado ↔ OpenAI-compatível ↔ llama-server)

O LOGOS é implementado em Rust com `axum` + `tokio` — assíncrono, de baixo overhead, rodando dentro do processo HUB.

---

### 8.2. Fila de prioridades — como funciona

O LOGOS usa um semáforo com **2 permits** e três níveis de prioridade:

| Prioridade | Quem usa | Timeout na fila | Efeito |
|---|---|---|---|
| **P1 — Crítica** | Chat interativo (HUB), escrita no AETHER | Sem timeout (espera para sempre) | keep_alive = -1 (modelo permanece na VRAM) |
| **P2 — Importante** | RAG da Mnemosyne | 60 segundos | keep_alive = "10m" |
| **P3 — Background** | Análise KOSMOS, embeddings, reflexão Akasha, geração de dados de treino | 30 segundos | keep_alive = 0 (descarrega após resposta) |

**Modelos leves (≤3B parâmetros)** adquirem 1 permit → até 2 rodam em paralelo.  
**Modelos pesados (>3B parâmetros)** adquirem 2 permits → exclusividade total.

**Preempção inteligente:** quando uma requisição P1 chega e a VRAM está saturada por tarefas P3 ativas, o LOGOS aborta imediatamente as inferências P3 em andamento (sem descarregar o modelo) para abrir espaço.

**Os apps não precisam saber nada disso.** Eles enviam os headers `X-App: mnemosyne` e `X-Priority: 2` — o LOGOS cuida do resto.

**Código relevante:** `HUB/src-tauri/src/logos.rs` função `queue_and_forward()` — onde toda a lógica de fila, guards e encaminhamento acontece.

---

### 8.3. Guards de hardware — proteção automática

O LOGOS detecta o hardware em runtime (`detect_hardware_profile()`) e aplica políticas diferentes por perfil:

**PC Principal (RX 6600, CachyOS):** modo normal
- VRAM monitorada via sysfs AMD (`/sys/class/drm/card0/device/mem_info_vram_used`)
- P3 bloqueado se VRAM > 85% (histerese: retoma quando cai abaixo de 70%)
- P3 bloqueado se CPU > 85% ou RAM livre < 1.5 GB

**Laptop (MX150, 2 GB VRAM):**
- Contexto máximo limitado a 2048 tokens (KV cache >2048 esgota a VRAM)
- Offload parcial de layers para GPU: `--n-gpu-layers 17` para gemma2:2b

**PC de trabalho (i5-3470, Windows 10):** modo sobrevivência
- Modelos pesados (>3B) bloqueados completamente
- Embeddings desabilitados
- Contexto máximo: 2048 tokens

**Em bateria:**
- P3 completamente desabilitado
- Embeddings desabilitados
- P2 bloqueado se CPU > 60%

---

### 8.4. Backend de inferência — llama-server vs Ollama

O LOGOS suporta dois backends, selecionados automaticamente no startup:

**llama-server (preferido):**
```
logos.rs:find_llama_server_bin() busca em:
  /usr/bin/llama-server
  /usr/local/bin/llama-server
  /opt/llama.cpp/llama-server
```
Quando encontrado, o LOGOS inicia um processo `llama-server` sob demanda para cada modelo solicitado. O servidor roda na porta **8081** (interna, não exposta aos apps).

O LOGOS resolve o arquivo GGUF em duas etapas:
1. Registry próprio: `{hub_data_path}/logos/models/registry.json`
2. Blob store do Ollama: `~/.ollama/models/blobs/` (reutiliza downloads existentes)

**Ollama (fallback):** usado quando `llama-server` não é encontrado. O LOGOS atua como proxy transparente para `http://localhost:11434`.

**Tradução de formato:** o LOGOS traduz automaticamente entre APIs. Os apps Python usam formato OpenAI-compatível — o LOGOS converte para o backend ativo:

```
App Python                LOGOS                     Backend
POST /v1/chat/completions ──────────────────────►   llama-server :8081/v1/chat/completions
POST /api/chat (legado)   → traduz para OpenAI ──►   llama-server :8081/v1/chat/completions
                                ↓ ou
                          → repassa para Ollama ──►   Ollama :11434/api/chat
```

---

### 8.5. Rotas expostas pelo LOGOS

O LOGOS expõe dois grupos de rotas em `127.0.0.1:7072`:

**API própria do LOGOS:**
```
GET  /logos/status           → fila atual, VRAM%, hardware, perfil ativo
GET  /logos/vram             → snapshot de VRAM/RAM
GET  /logos/metrics/stream   → SSE com métricas a cada 1s (usado pelo LogosPanel no HUB)
GET  /logos/hardware         → modelos recomendados para o hardware detectado
GET  /logos/models           → lista de modelos instalados com status de carregamento
POST /logos/models/load      → carrega um modelo específico
POST /logos/models/unload    → descarrega o modelo ativo
POST /logos/models/download  → inicia download de GGUF do HuggingFace
GET  /logos/models/registry  → lista o registry.json local
POST /logos/silence          → descarrega todos os modelos carregados (libera VRAM)
POST /logos/profile          → muda o perfil de workflow ativo
```

**Proxy transparente (OpenAI-compatível — usado pelos apps Python):**
```
POST /v1/chat/completions    → inferência com fila de prioridades
POST /v1/embeddings          → embeddings (sempre P3)
GET  /v1/models              → lista modelos disponíveis
GET  /health                 → health check do llama-server
```

**Proxy legado (Ollama — mantido para compatibilidade):**
```
POST /api/chat, /api/generate, /api/embed → fila de prioridades
GET  /api/tags, /api/ps                   → passthrough direto
```

---

### 8.6. Como os apps Python se comunicam com o LOGOS

Todos os apps usam `ecosystem_client.py` como intermediário. Nunca chamam o LOGOS diretamente.

**Inferência de texto:**
```python
import ecosystem_client as ec

# Chamada simples (não-streaming)
resposta = ec.request_llm(
    messages=[
        {"role": "system", "content": "Você é um assistente..."},
        {"role": "user", "content": "Explique transformers"},
    ],
    app="mnemosyne",
    priority=2,
)
conteudo = resposta["choices"][0]["message"]["content"]

# Streaming (SSE)
for token in ec.request_llm_stream(messages, app="hub", priority=1):
    print(token, end="", flush=True)
```

**URL do LOGOS:** `ec.get_inference_url()` → retorna `http://127.0.0.1:7072` (primário) ou `http://localhost:8080` (llama-server direto como fallback se LOGOS offline).

---

### 8.7. Perfis de modelos por hardware

O LOGOS sabe em qual máquina está rodando e define automaticamente qual modelo usar em cada slot. Esse perfil é lido pelos apps Python via `GET /logos/hardware` no startup.

| Slot | PC Principal (RX 6600) | Laptop (MX150 2GB) | PC Trabalho (CPU-only) |
|---|---|---|---|
| `llm_rag` (Mnemosyne RAG) | qwen2.5:7b | gemma2:2b | smollm2:1.7b |
| `llm_analysis` (KOSMOS) | gemma2:2b | smollm2:1.7b | qwen2.5:0.5b |
| `llm_query` (AKASHA) | qwen2.5:3b | smollm2:1.7b | qwen2.5:0.5b |
| `embed` (todos) | bge-m3 | bge-m3 | potion-multilingual-128M |
| `image_ocr` | moondream | moondream | *(não disponível)* |

**Por que esses modelos?**
- **qwen2.5:7b** — melhor balanço qualidade/VRAM para RAG longo (4.7 GB Q4, contexto longo)
- **gemma2:2b** — extração JSON confiável; coexiste com qwen2.5:7b na VRAM (1.6 GB)
- **qwen2.5:3b** — latência baixa para queries (~1.9 GB, bom JSON, coexiste com 7b)
- **bge-m3** — multilíngue, compatível entre máquinas via Syncthing (670 MB)
- **potion-multilingual-128M** — embedding estático (sem GPU), para o PC de trabalho sem AVX2
- **smollm2:1.7b** — modelo-teto do laptop (1.7B cabe inteiro na MX150 de 2 GB)
- **moondream** — ~1.7 GB VRAM; LOGOS descarrega bge-m3 antes de carregar (swap explícito)

A usuária pode sobrescrever qualquer slot via HUB (campo `model_overrides` persistido em `ecosystem.json`).

---

### 8.8. Dispatcher de skills (logos/dispatcher.py)

O dispatcher é usado pela Akasha quando precisa escolher qual "habilidade" aplicar a uma requisição — síntese, extração de entidades, RAG, classificação de chunk. Funciona em **3 tiers**, do mais rápido ao mais preciso:

**Tier 1 — Regex/keyword (~0ms, cobre ~80% dos casos)**

Testa padrões regex compilados em ordem de especificidade. Se qualquer padrão casar → retorna `SkillSelection(confidence=1.0, tier="keyword")` imediatamente.

```
entity-extraction : "extraia as organizações mencionadas no texto"
chunk-classification: "classifique este trecho como técnico ou literário"
rag-query         : "nos meus documentos, o que diz sobre atenção?"
synthesis         : "resuma o artigo sobre transformers"
```

**Tier 2 — Embedding similarity (~50ms)**

Calcula o embedding do request e compara com embeddings pré-calculados das *descriptions* de cada skill. Se similaridade de cosseno > 0.75 → retorna o skill mais próximo. Os embeddings de skill são cacheados na memória após a primeira chamada.

**Tier 3 — LLM router 3B (~200ms)**

Usa `llama3.2:3b` via `/v1/chat/completions` com `response_format: json_object`. Só acionado quando os dois filtros anteriores não resolveram. Se confidence < 0.7 → fallback para skill `synthesis`.

**Skills disponíveis** (arquivos `.md` em `logos/skills/`):

| Skill | Executor especial | Descrição |
|---|---|---|
| `synthesis` | modelo padrão | Resumo e síntese de texto |
| `rag-query` | `command-r:7b` | Busca com citação de fontes (único <10B com grounded generation) |
| `entity-extraction` | modelo padrão | Extração estruturada de entidades |
| `chunk-classification` | modelo padrão | Classificação de fragmentos de texto |

Cada skill `.md` tem frontmatter YAML (`name`, `description`) e corpo Markdown como system prompt. Adicionar um novo skill é simples: criar o arquivo `.md` em `logos/skills/` e reiniciar.

---

### 8.9. Pipeline de fine-tuning — visão geral

O ecossistema inclui um pipeline completo de QLoRA para personalizar modelos com o corpus da usuária. O objetivo é que a Mnemosyne (e futuramente a Akasha) possa responder com estilo e conhecimento adaptados ao conteúdo que a usuária indexou.

```
ChromaDB da Mnemosyne
  (chunks de PDFs, artigos, highlights)
         │
         ▼
training_data_generator.py
  (gera pares Q&A via LLM local, P3)
  (intercala âncoras Alpaca/Dolly 12%)
         │
         ▼ JSONL ChatML
qlora_trainer.py
  (SmolLM2 1.7B base em NF4 4-bit)
  (LoRA r=16/alpha=16, SFTTrainer)
  (VramPauseCallback: pausa se VRAM > 85%)
         │
         ▼ checkpoint LoRA
gguf_converter.py
  (merge adapter → merge_and_unload)
  (convert_hf_to_gguf.py → F16)
  (llama-quantize → Q4_K_M)
  (registra em registry.json)
  (atualiza ecosystem.json)
         │
         ▼
LOGOS registry → modelo disponível no HUB
```

Todo o ciclo é orquestrado pelo `finetune_scheduler.py`, que roda em background thread e persiste o estado em `{sync_root}/logos/finetune_state.json`.

---

### 8.10. Etapa 1 — Coleta e geração de dados de treinamento

**Arquivo:** `logos/training_data_generator.py`

O gerador itera **todos** os chunks do ChromaDB da Mnemosyne, filtra por qualidade, e usa o LLM local para gerar pares pergunta-resposta.

**Filtros de qualidade de chunk:**
- Mínimo de 200 caracteres de texto
- Rejeita chunks majoritariamente código (>50% das linhas com indentação ou ```)

**Formato de saída — ChatML (JSONL):**
```json
{"messages": [
  {"role": "system",    "content": "You are a knowledgeable assistant..."},
  {"role": "user",      "content": "Qual é a diferença entre...?"},
  {"role": "assistant", "content": "A diferença é..."}
]}
```

**Âncoras anti-colapso de domínio (12% do total):**
Sem âncoras, o modelo fine-tuned "esquece" como responder a perguntas gerais e só sabe falar sobre o corpus. Para evitar esse colapso, 12% dos exemplos são retirados de um pool fixo de pares Alpaca-style (perguntas gerais de conhecimento, programação, conversão de unidades, etc.), misturados aleatoriamente no JSONL final.

**Saída:** `{sync_root}/logos/training_data/YYYY-MM-DD.jsonl`

---

### 8.11. Etapa 2 — Fine-tuning QLoRA

**Arquivo:** `logos/qlora_trainer.py`

**Dependências extras** (não incluídas no venv base — instalar separadamente no PC principal):
```bash
# bitsandbytes AMD (pré-release com suporte ROCm)
pip install --force-reinstall --no-cache-dir --no-deps \
  "https://github.com/bitsandbytes-foundation/bitsandbytes/releases/download/\
continuous-release_main/bitsandbytes-1.33.7.preview-py3-none-manylinux_2_24_x86_64.whl"

# Unsloth com suporte AMD
uv pip install "unsloth[amd]"
```

**Configuração padrão (`TrainerConfig`):**

| Parâmetro | Valor padrão | Por que |
|---|---|---|
| Modelo base | SmolLM2 1.7B | Cabe na RX 6600 com QLoRA (~2-3 GB VRAM) |
| Quantização base | NF4 4-bit | Reduz VRAM ~4× com perda mínima de qualidade |
| LoRA rank (r) | 16 | Balanço capacidade/parâmetros treináveis |
| LoRA alpha | 16 | Alpha = r → escala neutra (learning rate efetivo padrão) |
| LoRA dropout | 0.0 | Dropout zero com gradient checkpointing é mais estável |
| `target_modules` | "all-linear" | LoRA em todas as camadas lineares |
| Batch size | 2 | Pequeno para não saturar VRAM |
| Gradient accumulation | 4 | Batch efetivo = 8 |
| Learning rate | 2e-4 | Padrão recomendado para LoRA |
| Epochs | 2 | Corpus pessoal é pequeno — mais epochs = overfitting |
| Seq length | 512 tokens | Pares Q&A raramente ultrapassam esse limite |
| `gradient_checkpointing` | True (modo "unsloth") | Reduz uso de VRAM em ~30% |

**VramPauseCallback — coexistência com o resto do ecossistema:**

Este callback verifica a VRAM antes de cada step de treinamento. Se VRAM > 85%, pausa o loop (sleep de 10 segundos por ciclo) e aguarda até liberar (timeout de 600 segundos). Assim, uma sessão de chat P1 que chegar durante o treinamento terá VRAM disponível imediatamente.

```python
def on_step_begin(self, args, state, control, **kwargs):
    info = vm.get_vram_info()
    if info.used_pct > threshold_pct:  # default: 85%
        deadline = time.monotonic() + 600.0
        while time.monotonic() < deadline:
            time.sleep(10.0)
            if vm.get_vram_info().used_pct <= threshold_pct:
                return  # retoma o step normalmente
        # timeout: continua mesmo assim com VRAM alta
```

**Saída:** diretório de checkpoint nomeado `smollm2-qlora-YYYYMMDD-HHMMSS/` em `{sync_root}/logos/checkpoints/`.

---

### 8.12. Etapa 3 — Conversão para GGUF e registro

**Arquivo:** `logos/gguf_converter.py`

Após o treinamento, o adapter LoRA precisa ser fundido ao modelo base e convertido para o formato que o `llama-server` entende:

```
checkpoint LoRA
  ↓ PeftModel.from_pretrained() + merge_and_unload()
modelo HuggingFace completo (pasta temporária)
  ↓ convert_hf_to_gguf.py (script do llama.cpp)
mnemosyne-ft-vN-f16.gguf
  ↓ llama-quantize Q4_K_M
mnemosyne-ft-vN-q4km.gguf  ← arquivo final (~900 MB)
  ↓ registry.json atualizado (SHA256 + caminho)
  ↓ ecosystem.json atualizado (logos.finetuned_rag_model = "mnemosyne-ft-vN")
LOGOS pode usar imediatamente via /logos/models/load
```

O LOGOS mantém sempre o modelo anterior como fallback (`finetuned_rag_model_prev`). Se o novo modelo apresentar problemas, basta apontar o `ecosystem.json` de volta para a versão anterior.

**Pré-requisito:** `llama-quantize` compilado e no PATH (parte do llama.cpp). O `convert_hf_to_gguf.py` é buscado no `llama_cpp_dir` configurado ou via `llama-cpp-python` instalado.

---

### 8.13. Orquestração via scheduler

**Arquivo:** `logos/finetune_scheduler.py`

O scheduler coordena o ciclo completo e pode ser disparado de duas formas:

**Disparo manual (via HUB):**
```python
from logos.finetune_scheduler import trigger_manual
trigger_manual()  # retorna imediatamente; ciclo roda em thread daemon
```

**Disparo automático** — o corpus cresceu mais de 20% desde o último treino:
```python
from logos.finetune_scheduler import should_auto_trigger
if should_auto_trigger():
    trigger_manual()
```

O estado é persistido em `{sync_root}/logos/finetune_state.json` e lido pelo painel LOGOS no HUB para exibir o progresso. O campo `current_step` indica a etapa em andamento: `"gerando_dados"` → `"treinando"` → `"convertendo"` → `""` (concluído).

**Proteção contra execuções simultâneas:** lock file atômico via `O_CREAT | O_EXCL` — o SO garante que apenas um processo cria o arquivo.

---

### 8.14. Como testar o pipeline de treinamento

**Verificar se as dependências estão instaladas:**
```bash
cd "program files"
python -c "from logos.qlora_trainer import check_prerequisites; print(check_prerequisites())"
# {'unsloth': True, 'bitsandbytes': True, 'transformers': True, 'trl': True, 'peft': True, 'datasets': True}
```

**Gerar dados de treinamento apenas (sem treinar):**
```bash
python -m logos.training_data_generator
# Stats: chunks_seen=850, processed=720, pairs=2400, anchors=320
# Saída em: {sync_root}/logos/training_data/2026-05-24.jsonl
```

**Inspecionar o JSONL gerado:**
```bash
head -n 1 "{sync_root}/logos/training_data/2026-05-24.jsonl" | python -m json.tool
# Verifica formato ChatML e presença de âncoras misturadas
```

**Executar ciclo completo via CLI:**
```bash
python -m logos.finetune_scheduler --trigger
# Roda: gera dados → treina → converte → registra
# Logs em: {sync_root}/logos/logos.log
```

**Verificar status do auto-trigger:**
```bash
python -m logos.finetune_scheduler --check
# "true" se corpus cresceu >20% desde o último ciclo
```

**Testar o modelo fine-tuned diretamente:**
```bash
# Após registro, o modelo aparece no painel LOGOS do HUB
# Teste rápido via llama-server standalone:
llama-server \
  --model "{sync_root}/logos/models/mnemosyne-ft-v1-q4km.gguf" \
  --port 9999 &

curl http://localhost:9999/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"mnemosyne-ft-v1","messages":[{"role":"user","content":"O que é atenção?"}],"stream":false}'
```

---

### 8.15. Boas práticas de privacidade e eficiência

**Privacidade — 100% local:**
- Nenhum dado do corpus, conversa ou modelo treinado sai da máquina
- Os dados de treinamento vêm do ChromaDB da Mnemosyne — apenas o que a usuária indexou explicitamente
- `finetune_state.json` fica no `sync_root` (Syncthing) — sincronizado entre as máquinas da usuária, nunca para fora

**Eficiência — quantização:**
- SmolLM2 1.7B em FP16 ocupa ~3.4 GB; em NF4 4-bit ocupa ~900 MB durante treino
- O GGUF Q4_K_M final ocupa ~900 MB em disco e ~1 GB de VRAM ao rodar
- Q4_K_M é o sweet spot para modelos pequenos: qualidade próxima de Q8 com metade do tamanho

**Eficiência — gradient checkpointing:**
- Modo "unsloth" reduz uso de VRAM ~30% com overhead de tempo mínimo (~10%)
- Essencial para rodar batch_size=2 com seq_len=512 no SmolLM2 1.7B sem OOM na RX 6600

**Quando não treinar (hardware incompatível):**
- **PC de trabalho** (i5-3470, Windows 10): CPU sem AVX2, sem GPU discreta — treinamento impraticável
- **Laptop** (MX150 2 GB VRAM): insuficiente para QLoRA mesmo em SmolLM2 — treinar apenas no PC principal
- **Em bateria** (qualquer máquina): P3 desabilitado pelo LOGOS → scheduler não dispara automaticamente

---

Seção 8 concluída. Aguardando confirmação para a próxima.

---

## 📚 Seção 9: Conceitos Importantes Explicados

Esta seção existe para que você possa entender *por que* o ecossistema funciona do jeito que funciona — não apenas *como*. Cada conceito é explicado em linguagem simples, com exemplos práticos e referências ao código real onde ele é aplicado.

---

### 9.1. Índice invertido e FTS5

**O problema:** você tem 50.000 documentos. Como encontrar todos que contêm a palavra "atenção" em menos de um segundo?

A resposta ingênua é passar por todos os documentos um a um. Isso é lento demais. A solução é construir um **índice invertido** — uma estrutura de dados que mapeia cada palavra para a lista de documentos onde ela aparece:

```
"atenção"   → [doc_42, doc_107, doc_891, ...]
"transformer" → [doc_42, doc_93, doc_107, ...]
"redes"     → [doc_93, doc_442, ...]
```

Quando você busca "atenção transformer", o banco intersecciona as duas listas e retorna apenas os documentos que contêm ambas as palavras. Isso é ordens de magnitude mais rápido do que varrer o texto completo.

**FTS5 (Full-Text Search 5)** é o módulo de busca textual embutido no SQLite que implementa exatamente isso. Ele constrói e mantém o índice invertido automaticamente, suporta operadores como `AND`, `OR`, `NOT`, busca de frases com aspas, e prefixos com `*`.

**No ecossistema:** o AKASHA usa FTS5 para busca local. A tabela virtual é criada assim:

```sql
-- AKASHA/database.py
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    title, content, tags, url UNINDEXED,
    content='pages', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
```

O `tokenize='unicode61 remove_diacritics 2'` remove acentos antes de indexar — assim "atenção" e "atencao" são tratados como a mesma palavra.

---

### 9.2. BM25 e TF-IDF

**O problema:** todos os documentos que contêm "atenção" foram encontrados, mas em que ordem exibi-los? Um documento que menciona "atenção" 50 vezes é necessariamente mais relevante do que um que menciona 2 vezes?

**TF-IDF (Term Frequency — Inverse Document Frequency)** é a fórmula clássica para pontuar relevância:

```
TF(termo, doc)  = frequência do termo no documento
IDF(termo)      = log(total de docs / docs que contêm o termo)

score(termo, doc) = TF × IDF
```

O IDF é o detalhe mais importante: ele penaliza palavras que aparecem em muitos documentos (como "de", "a", "o") e premia palavras raras. "Transformer" em um corpus de artigos gerais é muito mais informativo do que "pesquisa".

**BM25 (Best Match 25)** é a evolução do TF-IDF, com dois refinamentos práticos:

1. **Saturação de frequência:** o score para de crescer quando o termo aparece muitas vezes. Um documento com 20 ocorrências não é necessariamente 10× mais relevante que um com 2 — há um teto.
2. **Normalização por comprimento:** documentos longos naturalmente contêm mais palavras. BM25 penaliza documentos muito longos proporcionalmente.

```
BM25 = IDF × (TF × (k1 + 1)) / (TF + k1 × (1 - b + b × (len/avglen)))

k1 ≈ 1.2–2.0  → controla saturação de frequência
b  ≈ 0.75     → controla penalidade de comprimento
```

**No ecossistema:** o SQLite FTS5 calcula BM25 automaticamente via função `bm25()`. O AKASHA usa `ORDER BY bm25(pages_fts)` em `services/local_search.py` para ranquear os resultados textuais.

---

### 9.3. Busca vetorial e embeddings

**O problema:** a usuária busca "mecanismo de atenção em redes neurais". Um documento relevante usa a frase "self-attention in deep learning". BM25 não encontra nada — nenhuma palavra em comum.

A solução é representar o significado de um texto como um **vetor numérico** (embedding) num espaço de alta dimensão — tipicamente 768 ou 1024 dimensões. Textos semanticamente similares ficam geometricamente próximos nesse espaço, mesmo que usem palavras completamente diferentes.

```
embedding("mecanismo de atenção em redes neurais")
  → [0.12, -0.34, 0.87, 0.05, ..., -0.21]  (768 números)

embedding("self-attention in deep learning")
  → [0.11, -0.31, 0.85, 0.07, ..., -0.19]  (similaridade alta!)

embedding("receita de bolo de cenoura")
  → [-0.45, 0.78, -0.12, 0.33, ..., 0.62]  (distante dos anteriores)
```

A **similaridade de cosseno** mede o ângulo entre dois vetores: 1.0 = idênticos, 0.0 = sem relação, -1.0 = opostos. Na prática, dois textos relacionados ficam entre 0.7 e 0.95.

**O modelo de embedding** é uma rede neural treinada especificamente para essa tarefa — no ecossistema, `bge-m3` (multilíngue, 670 MB) para o PC principal e laptop, e `potion-multilingual-128M` (estático, sem GPU) para o PC de trabalho.

**Onde os vetores são armazenados:**
- Mnemosyne usa **ChromaDB** (banco de vetores) em `{sync_root}/mnemosyne/chroma/`
- AKASHA usa **sqlite-vec** (extensão do SQLite) — vetores direto no mesmo banco que o FTS5

**No ecossistema:** a Mnemosyne indexa documentos via `core/indexer.py:_embed_batch()`, que chama `POST /v1/embeddings` no LOGOS. O ChromaDB armazena e busca os vetores aproximados com HNSW.

---

### 9.4. Reciprocal Rank Fusion (RRF)

**O problema:** você tem quatro listas de resultados para a mesma query:
- Lista FTS5 (busca textual)
- Lista ChromaDB (busca vetorial)
- Lista sqlite-vec (outra busca vetorial)
- Lista de highlights (anotações da usuária)

Como combiná-las num ranking único sem perder os pontos fortes de cada uma?

**RRF** é uma fórmula elegantemente simples:

```
score_rrf(documento) = Σ 1 / (k + posição_na_lista_i)
```

Para cada lista em que o documento aparece, soma-se `1 / (k + posição)`. O `k = 60` é um parâmetro de amortecimento que evita que posições altas dominem demais.

**Exemplo:**
```
Doc A: posição 1 na FTS5, posição 3 no vetorial
  score = 1/(60+1) + 1/(60+3) = 0.01639 + 0.01587 = 0.03226

Doc B: posição 2 na FTS5, posição 1 no vetorial
  score = 1/(60+2) + 1/(60+1) = 0.01613 + 0.01639 = 0.03252

Doc C: posição 1 apenas no FTS5 (não aparece no vetorial)
  score = 1/(60+1) = 0.01639
```

Doc B vence por ter consistência em ambas as listas. Doc A fica em segundo. Doc C fica em terceiro, mesmo sendo o melhor da busca textual isolada.

A grande vantagem do RRF é que **não precisa normalizar scores** entre sistemas diferentes — usa apenas a posição relativa, não a pontuação absoluta.

**No ecossistema:** `AKASHA/services/local_search.py:_rrf()` implementa exatamente isso, com um multiplicador de `SOURCE_WEIGHTS` aplicado depois para dar mais peso a PDFs acadêmicos (2.0×) do que a páginas genéricas (1.0×). Veja a Seção 7 para detalhes completos.

---

### 9.5. PageRank

**O problema:** dois documentos têm score RRF idêntico. Como desempatar? Um deles é o artigo original do Google (citado por 10.000 papers). O outro é um blog post obscuro. Deveriam ter o mesmo peso?

**PageRank** é o algoritmo que o Google usou para ranquear páginas web pela importância — medida pelo número e qualidade das páginas que apontam para ela. A ideia central: uma página importante é apontada por muitas páginas importantes.

```
PR(A) = (1 - d) + d × Σ (PR(B) / links_saída(B))
            para todo B que aponta para A

d = 0.85  → fator de amortecimento (probabilidade de seguir um link)
```

O algoritmo é iterativo: começa com todos os nós com PR = 1.0 e itera até convergir.

**No ecossistema:** o AKASHA calcula PageRank localmente sobre o grafo de links rastreados (tabela `links` no SQLite). O valor é armazenado na tabela `pages` e aplicado como boost pós-RRF em `local_search.py:_apply_pagerank_boost()`. Um artigo muito citado pelos outros documentos indexados sobe no ranking.

---

### 9.6. Pseudo-Relevance Feedback (PRF)

**O problema:** a usuária busca "atenção". Sem mais contexto, o sistema não sabe se é "atenção" no sentido de machine learning ou no sentido de "prestar atenção". Como refinar a busca automaticamente?

**PRF** assume que os primeiros resultados de uma busca são provavelmente relevantes (daí "pseudo") e usa esses documentos para expandir a query original com termos adicionais que apareceram neles.

```
query original: "atenção"
  ↓ busca inicial
top-3 resultados: ["self-attention", "transformer", "query key value"]
  ↓ extrai termos mais relevantes dos top-3
query expandida: "atenção self-attention transformer query key value"
  ↓ segunda busca com query expandida
  ↓ RRF entre busca original + busca expandida
resultado final mais rico
```

O risco do PRF é **query drift**: se os primeiros resultados não forem relevantes, a expansão piora a busca em vez de melhorá-la. Por isso, o PRF está implementado no AKASHA (`services/query_expansion.py`) mas controlado pela flag `PRF_ENABLED` em `local_search.py` — pode ser ativado e desativado sem tocar na lógica.

---

### 9.7. pHash e distância de Hamming

**O problema:** você baixou a mesma imagem duas vezes — uma versão original e uma levemente redimensionada. Como detectar que são a mesma imagem sem comparar pixel a pixel?

**pHash (Perceptual Hash)** reduz uma imagem a uma sequência de 64 bits que representa sua "impressão digital visual". A ideia é aplicar uma Transformada de Cosseno Discreta (DCT) sobre a imagem reduzida e codificar se cada frequência está acima ou abaixo da média.

```
imagem 300×200px
  ↓ reduz para 32×32 escala de cinza
  ↓ aplica DCT 2D
  ↓ pega os 64 coeficientes de baixa frequência (8×8 bloco superior esquerdo)
  ↓ bit 1 se coeficiente > média, bit 0 caso contrário
hash: 1011010001110010...  (64 bits)
```

Duas versões da mesma imagem (redimensionada, comprimida, levemente recortada) terão hashes muito similares. A **distância de Hamming** entre dois hashes é o número de bits que diferem:

```
hash_A: 1011010001110010...
hash_B: 1011010001110110...  ← apenas 1 bit diferente
distância de Hamming = 1  → mesma imagem (< 8: provavelmente duplicata)
```

**No ecossistema:** a Mnemosyne usa pHash para deduplicação de imagens no pipeline de indexação. Evita reindexar a mesma figura que aparece em múltiplos formatos ou tamanhos.

---

### 9.8. WAL mode no SQLite

**O problema:** o AKASHA está rastreando páginas e escrevendo no banco ao mesmo tempo que a usuária faz uma busca. Se o escritor bloquear o banco durante a escrita, a busca trava e a interface congela.

**WAL (Write-Ahead Log)** é um modo de journaling do SQLite que resolve isso. Em vez de escrever diretamente nas páginas do banco, as mudanças são primeiro escritas num arquivo de log separado (`.wal`). O banco principal só é atualizado quando o log é "checkpointed".

O resultado prático: **leitores e escritores nunca se bloqueiam mutuamente**. Uma busca pode ler o banco enquanto o crawler está escrevendo — a leitura vê o estado consistente mais recente.

```
# AKASHA/database.py — aplicado no init
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;    # mais rápido que FULL, seguro com WAL
PRAGMA cache_size=-8000;      # 8 MB de cache em memória
PRAGMA mmap_size=67108864;    # 64 MB mapeados em memória (acesso mais rápido)
```

O modo WAL é especialmente importante no ecossistema porque o crawl, a indexação e a busca rodam em paralelo — é uma premissa arquitetural, não um caso especial.

---

### 9.9. RAG — e por que o AKASHA não gera respostas

**RAG (Retrieval-Augmented Generation)** é um padrão onde, antes de um LLM gerar uma resposta, o sistema primeiro busca documentos relevantes e os passa como contexto para o modelo:

```
query da usuária
  ↓ busca nos documentos indexados
top-K documentos relevantes
  ↓ incluídos no prompt do LLM como contexto
LLM gera resposta baseada nos documentos
```

A Mnemosyne usa RAG: faz busca vetorial + FTS5, pega os top-K chunks, e o LLM sintetiza uma resposta citando as fontes.

**O AKASHA não usa RAG — e isso é uma decisão arquitetural deliberada.**

O AKASHA é uma **ferramenta de busca**, não um assistente. O LLM entra apenas nas camadas auxiliares:
- `query_understanding.py` — classificar intenção e reescrever a query
- `services/persona.py` — reflexão e pensamentos da Akasha (assistente)

Nunca na síntese de resultados. O AKASHA devolve links, trechos e documentos — a usuária lê e pensa. O motivo:

1. **Velocidade:** RAG adiciona 1–3 segundos de latência do LLM em cada busca
2. **Fidelidade:** o LLM pode alucinar ou distorcer o conteúdo dos documentos
3. **Transparência:** a usuária vê as fontes diretamente, sem intermediação
4. **Funciona offline:** busca local funciona 100% sem LLM

Esta decisão está documentada no CLAUDE.md como "princípio arquitetural do AKASHA: amplificador de pesquisa, não respondedor."

---

### 9.10. LoRA e fine-tuning

**O problema:** você quer que um LLM de 1.7 bilhões de parâmetros responda com o estilo e o conhecimento do corpus que você indexou. Treinar o modelo inteiro do zero exigiria semanas de GPU e terabytes de dados. Há uma forma mais eficiente?

**LoRA (Low-Rank Adaptation)** é a resposta. A intuição matemática: as mudanças de peso necessárias para adaptar um modelo a uma tarefa específica formam uma **matriz de posto baixo** — ou seja, podem ser aproximadas pelo produto de duas matrizes muito menores.

```
Peso original W (4096 × 4096 = ~16M parâmetros)
  ≈ W + ΔW
    onde ΔW = A × B
    A: (4096 × r)
    B: (r × 4096)
    r = 16  → 4096×16 + 16×4096 = ~131K parâmetros (apenas 0.8% do original)
```

Durante o fine-tuning, o modelo base (W) permanece **congelado**. Apenas as matrizes A e B são treinadas. No final, ΔW pode ser mesclado ao W original (`merge_and_unload()`) para gerar um modelo completo sem overhead de inferência.

**QLoRA** adiciona um passo: o modelo base é carregado em **quantização NF4 (4-bit)**, reduzindo o uso de VRAM de ~3.4 GB (FP16) para ~900 MB. As matrizes LoRA continuam em FP32 ou BF16 — só o modelo base é comprimido.

```
SmolLM2 1.7B em NF4   → ~900 MB VRAM
+ matrizes LoRA (r=16) → ~130 MB VRAM
+ KV cache (seq=512)   → ~200 MB VRAM
Total:                 → ~1.2 GB VRAM (cabe na RX 6600 junto com outros modelos)
```

**No ecossistema:** `logos/qlora_trainer.py` usa Unsloth + bitsandbytes AMD + TRL SFTTrainer para o pipeline QLoRA. Veja a Seção 8 para detalhes completos.

---

### 9.11. Embeddings para treinamento vs. embeddings para busca

São o mesmo conceito, mas com propósitos diferentes — vale distinguir:

**Embeddings para busca** (bge-m3, potion):
- Gerados por modelos especializados em similarity search
- Treinados para que textos semanticamente similares fiquem próximos no espaço vetorial
- Usados em runtime para indexar e buscar documentos
- **Imutáveis:** não são fine-tunados no ecossistema

**Embeddings para treinamento** (no contexto do fine-tuning):
- São as representações internas do LLM que está sendo fine-tunado
- O LoRA modifica as camadas que produzem essas representações
- O resultado é que o modelo "aprende" a associar padrões do corpus com respostas adequadas
- **Mutable:** são exatamente o que o fine-tuning altera

A distinção prática: quando o `training_data_generator.py` chama o LOGOS para gerar pares Q&A, ele está usando o **LLM como gerador** (inferência). Quando o `qlora_trainer.py` treina, ele está ajustando os **pesos internos** do modelo — mudando como ele processa e representa texto.

---

### 9.12. Crawling respeitoso

**O problema:** um crawler que baixa páginas o mais rápido possível pode sobrecarregar servidores pequenos, fazer o IP ser bloqueado, e violar os termos de uso dos sites.

**robots.txt** é um arquivo de texto que os sites disponibilizam em `https://exemplo.com/robots.txt` descrevendo quais caminhos crawlers são (ou não são) permitidos de acessar:

```
User-agent: *
Disallow: /admin/
Disallow: /private/
Crawl-delay: 5
```

Um crawler respeitoso **lê e obedece esse arquivo** antes de fazer qualquer requisição. O AKASHA cacheia o robots.txt por domínio para não precisar baixá-lo a cada visita.

**Delay adaptativo:** ao invés de um delay fixo, o AKASHA ajusta o tempo de espera baseado na velocidade de resposta do servidor:

```python
# AKASHA/services/crawler.py
_MIN_DELAY = 0.5   # segundos mínimos entre requisições ao mesmo domínio
_MAX_DELAY = 30.0  # máximo (quando o servidor está lento)
```

Se o servidor demorar 3 segundos para responder, o delay aumenta proporcionalmente. Se responder em 200ms, o delay se mantém próximo do mínimo.

**ETag e Last-Modified:** antes de baixar uma página novamente, o AKASHA envia os cabeçalhos de cache HTTP. Se o servidor responder com `304 Not Modified`, a página não é re-baixada — economiza banda e reduz carga no servidor.

**User-Agent declarado:** o crawler se identifica com uma string transparente, não tenta se passar por navegador humano.

Essas práticas não são apenas éticas — são pragmáticas. Sites que detectam crawlers agressivos bloqueiam IPs, tornam o acesso futuro impossível.

---

### 9.13. Resumo rápido — qual técnica resolve qual problema

| Problema | Técnica | Onde no ecossistema |
|---|---|---|
| Busca por palavra-chave rápida | Índice invertido + FTS5 | `AKASHA/database.py`, `local_search.py` |
| Ranquear resultados por relevância | BM25 | SQLite FTS5 `bm25()` |
| Busca por significado (não palavras) | Embeddings + similaridade de cosseno | Mnemosyne (ChromaDB), AKASHA (sqlite-vec) |
| Combinar múltiplos rankings | RRF (Reciprocal Rank Fusion) | `AKASHA/services/local_search.py:_rrf()` |
| Desempatar por autoridade/importância | PageRank | `local_search.py:_apply_pagerank_boost()` |
| Expandir query automaticamente | PRF | `services/query_expansion.py` (flag `PRF_ENABLED`) |
| Deduplicar imagens | pHash + distância de Hamming | Mnemosyne (indexação de imagens) |
| Leituras e escritas simultâneas | WAL mode SQLite | `AKASHA/database.py:init_db()` |
| Adaptar LLM com dados pessoais | QLoRA (LoRA + quantização NF4) | `logos/qlora_trainer.py` |
| Não sobrecarregar servidores | Delay adaptativo + robots.txt | `AKASHA/services/crawler.py` |

---

Seção 9 concluída. Aguardando confirmação para a próxima.

---

## 🧑‍💻 Seção 10: Convenções de Código

Esta seção descreve os padrões que o ecossistema segue. Código consistente é mais fácil de ler, debugar e dar continuidade — especialmente num projeto de longa duração como este.

---

### 10.1. Formatação e linting Python

O ecossistema usa **Ruff** como linter (encontrado como dependência de dev em `KOSMOS/pyproject.toml` e esperado nos demais). Não há Black ou isort separados — o Ruff substitui ambos com velocidade muito maior.

**Instalação (dev):**
```bash
# Como dependência de dev no pyproject.toml:
[dependency-groups]
dev = ["ruff>=0.4", "pytest>=9.0"]

# Ou diretamente:
uv pip install ruff
```

**Rodar:**
```bash
ruff check .          # lista problemas
ruff check --fix .    # corrige automaticamente o que for possível
ruff format .         # formata o código (substitui Black)
```

**Regras gerais seguidas pelo Ruff/PEP 8:**
- Indentação: **4 espaços** (nunca tabs)
- Comprimento máximo de linha: **100 caracteres** (mais permissivo que PEP 8 padrão de 79)
- Aspas: **aspas duplas** para strings (padrão do Ruff formatter)
- Espaços ao redor de operadores: `x = a + b`, não `x=a+b`
- Linha em branco entre funções de nível de módulo; duas linhas antes de classes

**TypeScript (HUB, OGMA):** não há eslint configurado explicitamente, mas o compilador TypeScript com `strict: true` (ver `tsconfig.json`) já captura a maioria dos problemas.

**Rust (HUB src-tauri):** `cargo fmt` e `cargo clippy` são os padrões. Clippy warnings são tratados como erros em CI.

---

### 10.2. Nomenclatura

**Python:**

| Tipo | Convenção | Exemplo |
|---|---|---|
| Arquivos/módulos | `snake_case` | `query_understanding.py`, `local_search.py` |
| Funções | `snake_case` | `classify_intent()`, `_rrf()` |
| Variáveis | `snake_case` | `base_url`, `chunk_text` |
| Classes | `PascalCase` | `SearchResult`, `TrainerConfig`, `FinetuneState` |
| Constantes | `SCREAMING_SNAKE_CASE` | `SOURCE_WEIGHTS`, `_MIN_DELAY`, `LOGOS_PORT` |
| "Privado" (módulo) | prefixo `_` | `_embed_batch()`, `_TEMPORAL_TERMS`, `_rrf()` |
| "Privado" (forte) | prefixo `__` | raro — só para evitar conflito em subclasses |

**Convenção `_` de privacidade:**
O Python não tem verdadeiro controlo de acesso. O prefixo `_` é uma convenção que diz "não use isso diretamente de fora do módulo". Funções internas de um serviço sempre têm `_`. A API pública de um módulo são as funções sem prefixo.

```python
# services/freshness.py
_TEMPORAL_TERMS = frozenset({...})   # constante interna — não importar de fora
_days_since(date_str)                # helper interno
freshness_factor(days)               # API pública — pode importar
apply_freshness_rerank(...)          # API pública — pode importar
```

**Rust:**

| Tipo | Convenção |
|---|---|
| Funções | `snake_case` |
| Structs/Enums | `PascalCase` |
| Constantes | `SCREAMING_SNAKE_CASE` |
| Módulos | `snake_case` |

**TypeScript:**

| Tipo | Convenção |
|---|---|
| Funções/variáveis | `camelCase` |
| Componentes React | `PascalCase` |
| Interfaces/tipos | `PascalCase` |
| Constantes de módulo | `SCREAMING_SNAKE_CASE` |

---

### 10.3. Convenção de commits

O ecossistema usa **Conventional Commits** — formato `tipo(escopo): descrição`:

```
feat(AKASHA): adicionar busca por data de publicação
fix(Mnemosyne): corrigir crash ao abrir notebook sem histórico
docs(GUIDE): adicionar Seção 10 — convenções de código
test(AKASHA): adicionar testes para freshness rerank
refactor(logos): extrair detect_hardware_profile para função separada
chore(notes): commit notas pendentes
```

**Tipos válidos:**

| Tipo | Quando usar |
|---|---|
| `feat` | Nova funcionalidade visível para o usuário |
| `fix` | Correção de bug |
| `docs` | Documentação (README, GUIDE, comentários) |
| `test` | Adicionar ou corrigir testes |
| `refactor` | Mudança de código que não é feat nem fix |
| `chore` | Tarefas de manutenção (atualizar deps, commitar notes.md, etc.) |
| `perf` | Melhoria de performance |
| `style` | Formatação pura (sem mudança de lógica) |

**Regras:**
- Descrição em **português ou inglês** — o projeto mistura os dois, mas seja consistente no mesmo commit
- Imperativo: "adicionar", não "adicionado" ou "adicionando"
- Escopo em PascalCase para apps (`AKASHA`, `Mnemosyne`, `HUB`), ou snake_case para módulos (`logos`, `ecosystem_client`)
- Sem ponto final na linha de título

---

### 10.4. Docstrings e comentários

**Regra geral:** o CLAUDE.md estabelece que **comentários só são escritos quando o "por que" não é óbvio**. Nomes bem escolhidos já documentam o "o quê".

**Docstring de módulo** — obrigatória em todo arquivo `.py` com mais de uma função:

```python
"""
AKASHA — Freshness decay como sinal de ranking

Aplica desconto de antiguidade somente em queries com termos temporais explícitos.
Fórmula: freshness = 1.0 / (1.0 + ln(1 + dias_desde_publicacao))
  - Documento de hoje → fator ≈ 1.0
  - Documento de 1 ano → fator ≈ 0.145
  - Documento sem data → fator 1.0 (neutro)
"""
```

A docstring de módulo deve responder: o que este módulo faz, qual a fórmula/algoritmo principal, e quais são os limites esperados. Não precisa listar todas as funções — isso é papel do código.

**Docstring de função** — só quando a assinatura + nome não são suficientes:

```python
def freshness_factor(days: float | None) -> float:
    """Sem data → fator neutro 1.0."""  # uma linha, ponto final

def _rrf(rankings, k=60, weight_fn=None):
    """Funde N rankings via RRF. k=60 é o parâmetro de amortecimento padrão."""
```

**Nunca escrever:**
```python
def get_url(page):
    """Retorna a URL da página."""  # óbvio pelo nome — não adiciona valor
    return page.url
```

**Comentários inline** — apenas para invariantes não-óbvios, workarounds ou restrições de hardware:

```python
# RX 6600 8 GB — todos os modelos na GPU total
llm_rag_gpu_layers: -1

# Etapa 1b (aplicada após verificar AMD): NVIDIA presente sem AMD ≥ 4 GiB → Laptop
if has_nvidia_sysfs:
    return HardwareProfile.Laptop

# O_CREAT | O_EXCL é atômico — falha se já existir
fd = os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
```

---

### 10.5. Importações

**Ordem obrigatória (PEP 8 + isort/Ruff):**

```python
from __future__ import annotations  # sempre primeiro, quando usado

# 1. Biblioteca padrão
import json
import logging
import time
from pathlib import Path
from typing import Iterator

# 2. Bibliotecas de terceiros
import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel

# 3. Módulos internos do app
import config
import database
from services.freshness import apply_freshness_rerank
from services.web_search import SearchResult, search_web
```

**`from __future__ import annotations`** aparece em todos os módulos Python do ecossistema. Ele faz com que as anotações de tipo sejam avaliadas de forma lazy (como strings), permitindo referências circulares e melhorando performance de importação.

**Importações dentro de funções** — usadas intencionalmente em dois casos:
1. Dependências opcionais pesadas (ML libs que podem não estar instaladas):
   ```python
   def train(cfg):
       from unsloth import FastLanguageModel  # só importa quando train() é chamada
       from trl import SFTTrainer
   ```
2. Evitar importações circulares entre módulos.

---

### 10.6. Tipagem

Todo o código Python novo usa **type hints**. O ecossistema não usa `mypy` em CI, mas as anotações servem como documentação viva e são verificadas pelo Ruff.

```python
# Correto
def classify_intent(query: str, model: str = "qwen2.5:3b") -> str: ...
def _rrf(rankings: list[list[SearchResult]], k: int = 60) -> list[SearchResult]: ...
def read_state(sync_root: str = "") -> FinetuneState: ...

# Para tipos complexos
from typing import Iterator
def _iter_chroma_chunks(chroma_dir: str) -> Iterator[dict]: ...

# Union types (Python 3.10+)
def find_latest(data_dir: str) -> Path | None: ...
def vram_pct() -> float | None: ...
```

**`from __future__ import annotations`** permite escrever `list[str]` em vez de `List[str]` mesmo em Python 3.9, e `X | Y` em vez de `Optional[X]` ou `Union[X, Y]`.

**Tratamento de erros tipado** (regra do CLAUDE.md):
```python
# ✓ Específico — captura só o que espera
except ValueError as exc:
    log.warning("JSON inválido: %s", exc)
    return []

# ✗ Genérico demais — nunca em produção sem re-tipar
except Exception:
    pass
```

---

### 10.7. Logging

O ecossistema usa o módulo padrão `logging` (não `print`, não `loguru`). Cada módulo cria seu próprio logger com o nome hierárquico do módulo:

```python
import logging
log = logging.getLogger(__name__)
# ou com namespace explícito do ecossistema:
log = logging.getLogger("ecosystem.logos.qlora_trainer")
```

**Níveis de uso:**

| Nível | Quando usar |
|---|---|
| `log.debug(...)` | Informações de trace interno — desabilitado em produção |
| `log.info(...)` | Progresso de operações importantes (início/fim de ciclos, modelos carregados) |
| `log.warning(...)` | Algo inesperado mas recuperável (timeout, fallback ativado, arquivo ausente) |
| `log.error(...)` | Falha de uma etapa — operação não concluída, mas o processo continua |

**Formatação:**
```python
# ✓ Lazy formatting — string só é formatada se o nível estiver ativo
log.info("Dataset: %d exemplos de %s", len(records), latest.name)
log.warning("Skill desconhecido: %r — usando fallback", v)

# ✗ Eager — sempre formata, mesmo se logging.DEBUG estiver desabilitado
log.debug(f"Chunk {chunk_id}: {len(pairs)} par(es) gerados")  # evitar f-string aqui
```

---

### 10.8. Caminhos de arquivo

**Sempre `pathlib.Path`**, nunca `os.path`:

```python
# ✓ Correto
from pathlib import Path
checkpoint = Path(cfg.checkpoint_dir) / f"smollm2-qlora-{timestamp}"
checkpoint.mkdir(parents=True, exist_ok=True)
text = (Path(data_dir) / "registry.json").read_text(encoding="utf-8")

# ✗ Evitar
import os
checkpoint = os.path.join(cfg.checkpoint_dir, f"smollm2-qlora-{timestamp}")
os.makedirs(checkpoint, exist_ok=True)
```

`pathlib.Path` funciona em Windows e Linux sem ajustes — resolve o separador automaticamente. É a razão pela qual o ecossistema roda nos dois sistemas sem `if sys.platform`.

**Encoding explícito:** sempre `encoding="utf-8"` em `open()`, `read_text()`, `write_text()`. Nunca depender do encoding padrão do sistema (que no Windows pode ser cp1252).

---

### 10.9. Testes

**Framework:** `pytest` em todos os apps Python. Sem `unittest` puro.

**Estrutura de arquivos:**
```
AKASHA/
  tests/
    __init__.py
    conftest.py          # fixtures compartilhadas (DB setup, monkeypatches)
    test_freshness.py    # um arquivo por módulo testado
    test_query_understanding.py
    integration/         # testes que precisam de serviços externos (opcionais)
```

**Convenções de nomenclatura dos testes:**
- Arquivo: `test_<nome_do_módulo>.py`
- Função: `test_<o_que_testa>_<condição>()` — descritivo o suficiente para ser lido como documentação

```python
def test_temporal_query_hoje():           # ✓ — clara o que testa
def test_non_temporal_query_definition(): # ✓ — o caso negativo também nomeado
def test_1():                             # ✗ — não diz nada
```

**Classes de teste** para agrupar casos relacionados:
```python
class TestNeedsRewrite:
    """needs_rewrite retorna True para queries curtas ou com anáforas."""

    def _check(self, q):
        from services.query_understanding import needs_rewrite
        return needs_rewrite(q)

    def test_single_word_needs_rewrite(self):
        assert self._check("isso")

    def test_specific_query_no_rewrite(self):
        assert not self._check("aprendizado de máquina federado privacidade")
```

**Importações dentro dos testes** — preferido para evitar efeitos colaterais no nível de módulo:
```python
def test_freshness_factor_none():
    from services.freshness import freshness_factor  # importa aqui, não no topo
    assert freshness_factor(None) == pytest.approx(1.0)
```

**Fixtures para banco de dados:**
```python
@pytest.fixture()
def db_paths(tmp_path):
    import database as _db
    main_path = tmp_path / "akasha.db"
    # patch o caminho original, roda init, yield, restaura
    orig = _db.DB_PATH
    _db.DB_PATH = main_path
    asyncio.run(_db.init_db())
    yield main_path
    _db.DB_PATH = orig
```

`tmp_path` é uma fixture embutida do pytest que cria um diretório temporário único por teste — nunca interferem entre si.

**Async:** funções assíncronas são testadas com `asyncio.run()` via helper local:
```python
def run(coro):
    return asyncio.run(coro)

def test_get_dates_http_url(patched_db):
    result = run(_run_async_function())
    assert ...
```

**Regra do CLAUDE.md:** toda feature nova e toda correção de bug deve vir acompanhada de testes na mesma resposta. Nunca reportar um item como concluído sem que os testes existam e passem.

---

### 10.10. Estrutura de módulos por app

**AKASHA (FastAPI):**
```
AKASHA/
  main.py              # startup: registra routers, inicia serviços
  config.py            # constantes, leitura de ecosystem.json
  database.py          # schema SQLite, init_db(), helpers de query
  routers/             # endpoints FastAPI (um arquivo por domínio)
    search.py          # GET /search
    chat.py            # POST /chat
    crawler.py         # GET/POST /library
  services/            # lógica de negócio (sem HTTP, sem DB direto)
    local_search.py    # _rrf(), search_local(), SOURCE_WEIGHTS
    web_search.py      # search_web(), cache dois níveis
    query_understanding.py
    freshness.py
  templates/           # Jinja2 HTML
  tests/
```

**Mnemosyne (PySide6):**
```
Mnemosyne/
  main.py              # QApplication, MainWindow
  core/                # lógica pura (sem GUI)
    notebook.py        # dataclass Notebook
    notebook_store.py  # persistência em disco
    indexer.py         # embeddings, ChromaDB
    rag.py             # LangChain ChatOpenAI
    personal_memory.py
  gui/                 # widgets QT
    workers.py         # QThread workers para operações async
    styles.qss         # estilos PySide6
  tests/
```

**HUB (Tauri + React):**
```
HUB/
  src/                 # frontend React (TypeScript)
    components/        # componentes React
    lib/               # helpers (ecosystem.ts, ollama.ts)
    pages/             # rotas do app
  src-tauri/           # backend Rust
    src/
      main.rs          # entry point
      lib.rs           # registro de comandos Tauri
      logos.rs         # servidor LOGOS (axum)
      ecosystem.rs     # leitura do ecosystem.json
      commands/        # comandos Tauri expostos ao frontend
        launcher.rs
        logos.rs
        config.rs
```

**Princípio geral:** a lógica de negócio fica em `services/` (ou `core/`), nunca misturada com routers, handlers ou widgets. Um router chama um service; um service não importa de routers.

---

### 10.11. Checklist antes de commitar

```
[ ] O código passa em `ruff check .` sem warnings?
[ ] Os testes novos existem e passam com `pytest tests/ -v`?
[ ] Nomes de funções/variáveis são descritivos sem precisar de comentário?
[ ] Caminhos usam pathlib.Path e encoding="utf-8" explícito?
[ ] Erros são capturados com except específico (não except Exception: pass)?
[ ] Se é um serviço: a lógica está em services/, não no router?
[ ] README.md e GUIDE.md foram verificados e atualizados se necessário?
[ ] O commit segue o formato tipo(escopo): descrição?
```

---

Seção 10 concluída. Aguardando confirmação para a próxima.
