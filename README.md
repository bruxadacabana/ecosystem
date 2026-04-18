# Ecossistema

Conjunto de aplicativos pessoais, completamente locais, sem conta, sem nuvem, sem telemetria.
Desenvolvidos para CachyOS (Arch Linux) e Windows 10.

---

## Os apps

Cada app tem nome derivado de mitologia, línguas antigas ou conceitos esotéricos e cósmicos — essa etimologia é a alma de cada ferramenta.

---

### AETHER — Forja de Mundos
*pronuncia-se: ay-ther · αἰθήρ (grego) — "brilhar com luz própria"*

O quinto elemento da cosmologia grega — além da terra, água, fogo e ar. A substância pura e luminosa dos céus, o que os deuses respiravam, o meio pelo qual a luz viajava. Eterno e imutável, a quintessência que preenche o espaço além da esfera lunar. Aristóteles o descreveu como o material de que as estrelas são feitas.

Editor de escrita criativa para narrativas longas — livros, séries, fanfiction, worldbuilding.
Inspirado no Scrivener e no Ellipsus, mas completamente local.

- Vault portátil (pasta escolhida pelo usuário, formato JSON + Markdown)
- Binder com árvore Livros > Capítulos, CRUD, reordenação
- Editor WYSIWYG com auto-save, modo foco, modo typewriter
- Fichas de personagem, worldbuilding, linha do tempo
- Metas de palavras, sessões de escrita, streak diário, snapshots de capítulo

**Stack:** Rust (Tauri v2) · TypeScript + React + Vite  
**Estado:** Fases 0–5 completas. Vault format estável.

---

### HUB — Central do Ecossistema

App unificado para ler e navegar o conteúdo de todos os outros apps numa interface única.
Projetado para rodar também como APK Android (via Tauri 2) numa fase futura.

- **Módulo Escrita:** navega projetos, livros e capítulos do vault AETHER; renderiza Markdown
- **Módulo Leituras:** lista e lê artigos do archive do KOSMOS; marca como lido
- **Módulo Projetos:** lista projetos e páginas do OGMA (read-only)
- **Módulo Perguntas:** chat local com qualquer modelo Ollama, streaming token a token
- Barra de atalhos: lança os 6 apps e indica visualmente se cada um está rodando
- Read-only por padrão — não substitui os editores primários de cada app

**Stack:** Rust (Tauri v2) · TypeScript + React + Vite  
**Estado:** Fases 2.1–2.6 completas. Todos os módulos implementados.

---

### OGMA — Grimório de Projetos
*pronuncia-se: og-mah · Ogma (irlandês antigo) — deus da eloquência e das letras*

Divindade irlandesa criadora do Ogham — o alfabeto mais antigo da Irlanda, entalhado em bordas de pedra. Representado com uma corrente dourada saindo da língua, presa às línguas de todos que o seguiam: o poder da linguagem de conectar e conduzir.

Gerenciador unificado de projetos, estudos e leituras. Cada projeto tem páginas com editor de blocos rico e propriedades customizáveis. Banco SQLite local sincronizado via Proton Drive.

- Projetos do tipo criativo, técnico, estudo, leitura
- Editor de blocos com imagens, tabelas, checklists, código
- Tags, filtros, busca por texto
- Offline-first: 100% local, sem conta externa

**Stack:** Electron · TypeScript + React + Vite  
**Estado:** Schema v2 em produção.

---

### KOSMOS — Ordem do Universo
*pronuncia-se: koz-mos · κόσμος (grego) — ordem, harmonia, totalidade*

Oposto semântico ao Caos primordial. Para os gregos, o cosmos era a prova de que o universo tem sentido — uma ordem inteligível subjacente a tudo. Pitágoras foi o primeiro a usá-lo para descrever o universo como totalidade harmônica. Implica que tudo tem seu lugar, sua relação, sua proporção.

Leitor e agregador de feeds RSS local. Suporta RSS genérico, YouTube, Tumblr, Substack, Mastodon e Reddit. Lê artigos, salva no archive em Markdown, exporta como PDF.

- Múltiplos tipos de feed com parsers dedicados
- Painel de leitura com WebEngine
- Archive de artigos em Markdown (`data/archive/`)
- Tradução offline opcional via Argos Translate

**Stack:** Python + PyQt6  
**Estado:** Funcional. Pronto para integração.

---

### Mnemosyne — Guardiã da Memória
*pronuncia-se: nem-oz-ih-nee · Μνημοσύνη (grego) — personificação da Memória*

Titânide filha de Urano e Gaia, mãe das nove Musas — todas as artes nascem da memória. No submundo, guardava o rio Mnemosyne, oposto ao Letes (esquecimento). Quem bebia de suas águas antes de reencarnar lembrava de tudo que havia vivido. A memória como identidade e como poder.

Assistente local de documentos com RAG. Indexa uma pasta de arquivos (`.pdf`, `.docx`, `.txt`, `.md`), responde perguntas e gera resumos com modelos do Ollama — sem nenhum dado sair da máquina.

- Vectorstore local via ChromaDB (índice em `<pasta>/.mnemosyne/`)
- Seleção dinâmica de modelos detectados no Ollama
- Watcher de pasta: indexa novos arquivos automaticamente
- Hybrid retrieval BM25 + semântico

**Stack:** Python + PySide6 · LangChain · ChromaDB · Ollama  
**Estado:** Em desenvolvimento ativo.

---

### Hermes — Mensageiro
*pronuncia-se: her-meez · Ἑρμῆς (grego) — mensageiro dos deuses, guia entre mundos*

O único olímpico que transitava livremente entre o Olimpo, o mundo dos vivos e o Hades — mediador por excelência. Inventor da lira, da flauta e do alfabeto. Seu símbolo, o caduceu (duas serpentes entrelaçadas), representa o movimento entre opostos.

Utilitário de download e transcrição de vídeos. Baixa qualquer URL suportada pelo yt-dlp e transcreve o áudio em Markdown via Whisper.

- Aba Descarregar: inspeciona URL, lista formatos, suporta playlists
- Aba Transcrever: modelo Whisper configurável, idioma, limite de CPU
- Output salvo em pasta configurável; histórico de transcrições
- Workers em thread separada, log colorido em tempo real

**Stack:** Python + PyQt6 · yt-dlp · openai-whisper  
**Estado:** Fase 1 completa.

---

### AKASHA — Registros do Universo
*pronuncia-se: ah-kah-shah · ākāśa (sânscrito) — "espaço luminoso", o substrato invisível onde tudo existe*

Na cosmologia hindu/vedanta, o quinto elemento — o espaço onde tudo existe, ressoa e persiste. No esoterismo ocidental, os *Registros Akáshicos* são a biblioteca cósmica imaterial onde cada pensamento, palavra e ação está eternamente gravada no tecido do universo. Consultar os Registros é acessar o conhecimento total.

Buscador pessoal local. Agrega resultados da web e do próprio ecossistema numa interface única, com biblioteca de URLs monitorada e arquivação de páginas. Roda como servidor Python acessado via browser — sem conta, sem nuvem, sem telemetria.

- Busca web: DuckDuckGo sem API key; cache local de 1h; histórico persistido
- Busca local: lê `ecosystem.json` para descobrir os caminhos — `kosmos.archive_path` (`**/*.md`), `aether.vault_dir` (`*/chapters/*.md`) e `mnemosyne.indices` (ChromaDB, opcional); fontes não configuradas são silenciosamente ignoradas
- Arquivação: salva qualquer página como `.md` em `AKASHA/data/archive/{YYYY-MM-DD}_{slug}.md` (pasta própria, sem dependências externas)
- Biblioteca de URLs: monitoramento periódico com diff automático e busca FTS5
- Integração com ecossistema: lê `ecosystem.json`; delega vídeo/áudio ao Hermes

**Stack:** Python + FastAPI · HTMX + Jinja2 · SQLite · uv  
**Estado:** Fases 1–3, 5 e 7 concluídas. Busca web + local + biblioteca de URLs funcionais.  
**Porta:** 7071

---

## Guia de instalação e uso

Este guia assume que você está configurando tudo do zero. Se alguns requisitos já estiverem instalados, pule os passos correspondentes.

Os apps se dividem em três grupos por tecnologia:

| Grupo | Apps | Tecnologia |
|---|---|---|
| Tauri (Rust + Node) | AETHER, HUB | Rust, Node.js, cargo-tauri |
| Electron (Node) | OGMA | Node.js |
| Python | KOSMOS, Mnemosyne, Hermes | Python 3, venv compartilhado |

---

## CachyOS (Arch Linux) — Niri + Fish

As instruções abaixo assumem o shell **Fish** e o compositor Wayland **Niri**, que é o ambiente padrão nesta instalação.

Todos os comandos devem ser digitados em um terminal com Fish (ex.: Foot, Alacritty, ou qualquer emulador configurado no Niri).

### Passo 1 — Rust

O Rust é a linguagem de programação usada pelo AETHER e pelo HUB. É necessário instalá-lo via `rustup` (o instalador oficial) — **não use o pacote do sistema**, pois ele pode estar desatualizado.

Abra um terminal e execute:

```fish
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

O instalador vai perguntar qual tipo de instalação fazer. Pressione **Enter** para aceitar o padrão (opção 1).

No Fish, o `cargo` já fica disponível nas próximas sessões se `~/.cargo/bin` estiver no PATH. Para ativá-lo na sessão atual sem fechar o terminal:

```fish
fish_add_path ~/.cargo/bin
```

Verifique se a instalação funcionou:

```fish
rustc --version
# deve mostrar algo como: rustc 1.x.x (...)
```

---

### Passo 2 — Tauri CLI

O `cargo-tauri` é a ferramenta de linha de comando que compila e roda os apps AETHER e HUB. Instale com:

```fish
cargo install tauri-cli
```

> Isso vai levar alguns minutos na primeira vez — o Cargo precisa compilar a ferramenta. Nas próximas vezes, o comando `cargo tauri dev` é rápido.

Verifique:

```fish
cargo tauri --version
# deve mostrar: tauri-cli x.x.x
```

---

### Passo 3 — Dependências de sistema para Tauri

O Tauri usa o motor web do sistema (webkit2gtk). No CachyOS, instale:

```fish
sudo pacman -S webkit2gtk-4.1 libayatana-appindicator
```

---

### Passo 4 — Node.js

O Node.js é necessário para AETHER, HUB e OGMA. A forma recomendada é via `nvm` (o arquivo `nvm.fish` já deve estar configurado se você usa o plugin nvm para fish):

```fish
nvm install 22
nvm use 22
```

Se ainda não tiver o nvm, instale o plugin via Fisher:

```fish
fisher install jorgebucaran/nvm.fish
nvm install 22
```

Ou, se preferir o pacote do sistema sem gerenciador de versões:

```fish
sudo pacman -S nodejs npm
```

Verifique:

```fish
node --version   # deve mostrar v18 ou superior
npm --version
```

---

### Passo 5 — Python e o ambiente virtual compartilhado

Os apps KOSMOS, Mnemosyne e Hermes compartilham um único ambiente virtual Python localizado em `.venv/` na raiz do ecossistema. Isso evita conflitos entre versões de bibliotecas.

O Python 3 já vem instalado no CachyOS. Verifique:

```fish
python3 --version
# deve mostrar Python 3.11 ou superior
```

Crie o ambiente virtual e instale as dependências de todos os apps Python de uma vez:

```fish
# Vá para a pasta raiz do ecossistema
cd "/home/spacewitch/Documents/program files"

# Crie o ambiente virtual
python3 -m venv .venv

# Ative-o (no Fish, o prompt muda para mostrar "(.venv)")
source .venv/bin/activate.fish

# Atualize o pip
pip install --upgrade pip

# Instale as dependências do KOSMOS
pip install -r KOSMOS/requirements.txt

# Instale as dependências do Mnemosyne
pip install -r Mnemosyne/requirements.txt

# Instale as dependências do Hermes
pip install yt-dlp openai-whisper

# Desative o ambiente virtual quando terminar
deactivate
```

> **Atenção:** o passo acima precisa ser feito apenas **uma vez**. Depois, os scripts `iniciar.sh` de cada app ativam o venv automaticamente (os scripts usam bash internamente, o que funciona normalmente no Niri/Wayland).

---

### Passo 6 — Ollama (opcional — necessário para Mnemosyne e módulo Perguntas do HUB)

O Ollama é um servidor local de modelos de linguagem (LLMs). O Mnemosyne e o módulo Perguntas do HUB precisam dele para funcionar.

```fish
# Instalar o Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Baixar um modelo (escolha conforme o seu hardware)
ollama pull llama3        # recomendado — bom equilíbrio tamanho/qualidade (~4,7GB)
ollama pull phi3          # menor e mais rápido (~2,3GB)
ollama pull mistral       # alternativa popular (~4,1GB)
```

Verifique se o Ollama está rodando:

```fish
ollama list
# deve listar os modelos baixados
```

O Ollama inicia automaticamente como serviço de sistema após a instalação. Se não estiver ativo, inicie manualmente com `ollama serve`.

---

### Passo 7 — Instalar dependências Node dos apps Tauri e Electron

Este passo baixa as bibliotecas JavaScript necessárias para AETHER, HUB e OGMA. Precisa ser feito apenas **uma vez** por app (e de novo se o `package.json` mudar).

```fish
cd "/home/spacewitch/Documents/program files/AETHER"
npm install

cd "/home/spacewitch/Documents/program files/HUB"
npm install

cd "/home/spacewitch/Documents/program files/OGMA"
npm install
```

---

### Rodar os apps no CachyOS

Todos os apps têm um atalho configurado como **função fish**. Basta digitar o nome em qualquer terminal:

#### AETHER

```fish
aether
```

O que acontece internamente: `cd .../AETHER && cargo tauri dev`

Na **primeira execução**, o Rust compila todas as dependências — pode levar de 5 a 15 minutos. As próximas aberturas são quase instantâneas (apenas o código modificado é recompilado). Enquanto compila, você vai ver linhas `Compiling ...` no terminal — isso é normal.

#### HUB

```fish
hub
```

Mesmo comportamento do AETHER — compilação longa apenas na primeira vez.

#### OGMA

```fish
ogma
```

O OGMA é um app Electron. O `iniciar.sh` detecta automaticamente que você está numa sessão Wayland (Niri) e força o modo de compatibilidade X11/XWayland — isso é necessário para o Electron funcionar no Niri. Você não precisa fazer nada especial.

O log de execução fica em `/tmp/ogma.log` — abra com `cat /tmp/ogma.log` se algo der errado.

#### KOSMOS

```fish
kosmos
```

Abre em background — o terminal fica livre para outros comandos.

#### Mnemosyne

```fish
mnemosyne
```

Abre em background. Para responder perguntas, o Ollama precisa estar rodando (`ollama serve` ou como serviço de sistema).

#### Hermes

```fish
hermes
```

Abre em background.

---

### Atalhos fish — configuração manual (se necessário)

Se as funções fish não estiverem configuradas (por exemplo, em uma nova instalação), crie os arquivos manualmente. Cada app tem um arquivo em `~/.config/fish/functions/` — o Fish carrega automaticamente qualquer arquivo `.fish` nessa pasta:

**AETHER** — `~/.config/fish/functions/aether.fish`:
```fish
function aether --description "Rodar AETHER em modo desenvolvimento"
    set -l dir "/home/spacewitch/Documents/program files/AETHER"
    echo "→ AETHER dev  ($dir)"
    cd $dir && cargo tauri dev
end
```

**HUB** — `~/.config/fish/functions/hub.fish`:
```fish
function hub --description "Rodar HUB em modo desenvolvimento"
    set -l dir "/home/spacewitch/Documents/program files/HUB"
    echo "→ HUB dev  ($dir)"
    cd $dir && cargo tauri dev
end
```

**OGMA** — `~/.config/fish/functions/ogma.fish`:
```fish
function ogma --description "Rodar OGMA (Electron)"
    set -l dir "/home/spacewitch/Documents/program files/OGMA"
    echo "→ OGMA  (log em /tmp/ogma.log)"
    bash "$dir/iniciar.sh"
end
```

**KOSMOS** — `~/.config/fish/functions/kosmos.fish`:
```fish
function kosmos --description "Rodar KOSMOS (leitor RSS)"
    set -l dir "/home/spacewitch/Documents/program files/KOSMOS"
    set -l python "/home/spacewitch/Documents/program files/.venv/bin/python"
    echo "→ KOSMOS"
    cd $dir && $python main.py &
    disown
end
```

**Mnemosyne** — `~/.config/fish/functions/mnemosyne.fish`:
```fish
function mnemosyne --description "Rodar Mnemosyne (RAG local)"
    set -l dir "/home/spacewitch/Documents/program files/Mnemosyne"
    set -l python "/home/spacewitch/Documents/program files/.venv/bin/python"
    echo "→ Mnemosyne"
    cd $dir && $python main.py &
    disown
end
```

**Hermes** — `~/.config/fish/functions/hermes.fish`:
```fish
function hermes --description "Rodar Hermes (downloader + transcritor)"
    set -l dir "/home/spacewitch/Documents/program files/Hermes"
    echo "→ Hermes"
    bash "$dir/iniciar.sh" &
    disown
end
```

**AKASHA** — `~/.config/fish/functions/akasha.fish`:
```fish
function akasha --description "Rodar AKASHA (buscador pessoal, porta 7071)"
    set -l dir "/home/spacewitch/Documents/program files/AKASHA"
    echo "→ AKASHA  (http://localhost:7071)"
    bash "$dir/iniciar.sh" &
    disown
end
```

---

## Windows 10

### Passo 1 — Rust

1. Acesse [rustup.rs](https://rustup.rs) e clique em **"Download rustup-init.exe (64-bit)"**
2. Execute o arquivo baixado
3. O instalador vai avisar se as **Visual Studio Build Tools** não estiverem instaladas — se avisar, clique em "Yes" para instalar. Isso baixa o compilador C++ necessário (pode levar vários minutos)
4. Quando retornar para a tela do rustup, pressione **Enter** para aceitar a instalação padrão (opção 1)
5. Abra um novo **Prompt de Comando** (CMD) ou **PowerShell** — o anterior não vai reconhecer os comandos ainda

Verifique (no novo terminal):

```powershell
rustc --version
cargo --version
```

Se aparecer "não reconhecido como comando", feche e abra o terminal novamente.

---

### Passo 2 — Tauri CLI

No PowerShell ou CMD:

```powershell
cargo install tauri-cli
```

Vai levar alguns minutos. Ao final:

```powershell
cargo tauri --version
```

---

### Passo 3 — WebView2

O Tauri usa o WebView2 do Windows como motor web. No Windows 10 com atualizações recentes, ele **já vem instalado**. Para verificar, abra o Painel de Controle > Programas e procure por "Microsoft Edge WebView2 Runtime".

Se não estiver instalado, baixe em: https://developer.microsoft.com/microsoft-edge/webview2/ (clique em "Download Evergreen Bootstrapper").

---

### Passo 4 — Node.js

1. Acesse [nodejs.org](https://nodejs.org)
2. Baixe a versão **LTS** (Long Term Support) — a que aparece à esquerda
3. Execute o instalador e aceite todas as opções padrão
4. Na tela "Tools for Native Modules", **marque a caixa** "Automatically install the necessary tools" — isso instala ferramentas adicionais que o OGMA precisa

Verifique (novo terminal):

```powershell
node --version    # deve mostrar v18 ou superior
npm --version
```

---

### Passo 5 — Python

1. Acesse [python.org/downloads](https://www.python.org/downloads/)
2. Baixe a versão mais recente do **Python 3** (ex.: Python 3.12.x)
3. Execute o instalador — **IMPORTANTE:** na primeira tela, marque **"Add Python to PATH"** antes de clicar em Install Now
4. Clique em "Install Now"

Verifique (novo terminal):

```powershell
python --version    # deve mostrar Python 3.x.x
pip --version
```

---

### Passo 6 — Ambiente virtual Python compartilhado

Abra o PowerShell e execute:

```powershell
# Se a política de execução bloquear scripts, execute isso primeiro (uma vez):
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# Vá para a pasta raiz do ecossistema (ajuste o caminho se necessário)
cd "C:\caminho\para\program files"

# Crie o ambiente virtual
python -m venv .venv

# Ative-o
.\.venv\Scripts\Activate.ps1
# O prompt vai mudar para mostrar "(.venv)"

# Atualize o pip
pip install --upgrade pip

# Instale as dependências de cada app
pip install -r KOSMOS\requirements.txt
pip install -r Mnemosyne\requirements.txt
pip install yt-dlp openai-whisper

# Desative quando terminar
deactivate
```

> **Nota:** o PyQt6-WebEngine do KOSMOS requer as Visual C++ Redistributable 2019+. Se aparecer erro de DLL, baixe e instale em: https://aka.ms/vs/17/release/vc_redist.x64.exe

---

### Passo 7 — Dependências Node

No PowerShell:

```powershell
cd "program files\AETHER" && npm install
cd "..\HUB"               && npm install
cd "..\OGMA"              && npm install
```

---

### Passo 8 — Ollama (opcional)

1. Acesse [ollama.com/download](https://ollama.com/download) e baixe o instalador para Windows
2. Execute e siga o instalador
3. Após instalar, abra o CMD e baixe um modelo:

```powershell
ollama pull llama3
```

---

### Rodar os apps no Windows 10

#### AETHER e HUB

Abra o PowerShell na pasta do app e execute:

```powershell
# AETHER:
cd "program files\AETHER"
cargo tauri dev

# HUB:
cd "program files\HUB"
cargo tauri dev
```

> **Na primeira execução**, o Rust compila tudo — pode levar de 5 a 15 minutos. Seja paciente; as próximas aberturas são quase instantâneas.

#### OGMA

Clique duas vezes em `iniciar.bat` dentro da pasta OGMA, ou no PowerShell:

```powershell
cd "program files\OGMA"
.\iniciar.bat
```

#### KOSMOS, Mnemosyne e Hermes

Ative o venv e rode diretamente:

```powershell
# Ative o venv (necessário cada vez que abrir um novo terminal)
cd "program files"
.\.venv\Scripts\Activate.ps1

# KOSMOS:
cd KOSMOS
python main.py

# Mnemosyne (abra outro terminal com o venv ativado):
cd Mnemosyne
python main.py

# Hermes (abra outro terminal com o venv ativado):
cd Hermes
python hermes.py
```

---

## Build de produção (opcional)

Se quiser gerar executáveis para distribuição ou atalhos sem o terminal:

#### AETHER e HUB

```bash
# CachyOS — gera .AppImage e .deb em src-tauri/target/release/bundle/
cd AETHER && cargo tauri build

# Windows — gera .msi em src-tauri\target\release\bundle\msi\
cd AETHER && cargo tauri build
```

#### OGMA

```bash
# CachyOS
cd OGMA && npm run dist:linux

# Windows
cd OGMA && npm run dist:win
```

#### Apps Python

Sem build padrão configurado — rodam do source com o venv ativado.

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

O roteiro completo de integração dos apps — incluindo o HUB unificado e suporte Android — está em [ECOSYSTEM_TODO.md](ECOSYSTEM_TODO.md).

### Contrato compartilhado — `ecosystem.json`

Os apps se comunicam via um arquivo JSON descoberto automaticamente:

- **Linux:** `~/.local/share/ecosystem/ecosystem.json` (respeita `$XDG_DATA_HOME`)
- **Windows:** `%APPDATA%\ecosystem\ecosystem.json`

Cada app escreve apenas a sua própria seção; as demais são preservadas. Escrita atômica em todos (arquivo temporário + rename). Falha silenciosa — nunca bloqueia o startup.

```json
{
  "sync_root":  "/caminho/proton-drive/ecosystem",
  "aether":    { "vault_path": "...", "exe_path": "..." },
  "kosmos":    { "archive_path": "...", "data_path": "...", "exe_path": "..." },
  "ogma":      { "data_path": "...", "exe_path": "..." },
  "mnemosyne": { "watched_dir": "...", "vault_dir": "...", "chroma_dir": "...", "index_paths": [], "exe_path": "..." },
  "hermes":    { "output_dir": "...", "exe_path": "..." },
  "akasha":    { "archive_path": "...", "base_url": "...", "exe_path": "..." }
}
```

#### Contrato por campo

| Campo | Escrito por | Quando | Lido por | Formato |
|---|---|---|---|---|
| `sync_root` | HUB | ação do usuário (SetupView → Aplicar) | HUB (SetupView) | string — caminho absoluto |
| `aether.vault_path` | AETHER · HUB | startup · `apply_sync_root` | AKASHA (busca local) | string — caminho absoluto |
| `aether.exe_path` | AETHER | startup | HUB (detecção de apps) | string — `iniciar.bat` ou `iniciar.sh` |
| `kosmos.archive_path` | KOSMOS · HUB | startup · `apply_sync_root` | AKASHA (busca local), Mnemosyne (sugestões) | string — caminho absoluto |
| `kosmos.data_path` | KOSMOS | startup | HUB | string — caminho absoluto |
| `kosmos.exe_path` | KOSMOS | startup | HUB (detecção de apps) | string — `iniciar.bat` ou `iniciar.sh` |
| `ogma.data_path` | OGMA | startup | HUB | string — caminho absoluto |
| `ogma.exe_path` | OGMA | startup | HUB (detecção de apps) | string — `iniciar.bat` ou `iniciar.sh` |
| `mnemosyne.watched_dir` | Mnemosyne · HUB | startup (se configurado) · `apply_sync_root` | AKASHA (busca local), Mnemosyne (sugestões) | string — caminho absoluto |
| `mnemosyne.vault_dir` | Mnemosyne | startup (se configurado) | AKASHA (busca local), Mnemosyne (sugestões) | string — caminho absoluto |
| `mnemosyne.chroma_dir` | HUB | `apply_sync_root` | Mnemosyne (`persist_dir`) | string — caminho absoluto |
| `mnemosyne.index_paths` | Mnemosyne | startup (se `persist_dir` configurado) | — reservado para uso futuro | array de strings |
| `mnemosyne.exe_path` | Mnemosyne | startup | HUB (detecção de apps) | string — `iniciar.bat` ou `iniciar.sh` |
| `hermes.output_dir` | Hermes · HUB | startup · `apply_sync_root` | HUB | string — caminho absoluto |
| `hermes.exe_path` | Hermes | startup | HUB (detecção de apps) | string — `iniciar.bat` ou `iniciar.sh` |
| `akasha.archive_path` | HUB | `apply_sync_root` | AKASHA (arquivação e busca local) | string — caminho absoluto |
| `akasha.base_url` | AKASHA | startup | HUB (link para o app) | string — URL base (ex: `http://localhost:7071`) |
| `akasha.exe_path` | AKASHA | startup | HUB (detecção de apps) | string — `iniciar.bat` ou `iniciar.sh` |

**Regras de escrita:** cada app usa `write_section(app, {...})` — merge atômico que preserva todos os campos da seção que não estão no payload. O HUB é o único que escreve campos de múltiplos apps (via `apply_sync_root`). Nunca sobrescrever `exe_path` de outro app.

### Estrutura de sincronização (Proton Drive)

O campo `sync_root` aponta para a pasta raiz do ecossistema no Proton Drive. O HUB deriva e aplica todos os subcaminhos de uma vez via `apply_sync_root`. Cada app lê o seu caminho do ecosystem.json no startup, com fallback para o caminho local.

```
{sync_root}/
├── ogma/
│   ├── ogma.db              ← banco SQLite
│   ├── uploads/
│   ├── exports/
│   └── .config/
│       └── settings.json    ← preferências sincronizadas
├── kosmos/
│   ├── (artigos arquivados .md)
│   └── .config/
│       └── settings.json
├── hermes/
│   ├── (transcrições .md)
│   └── .config/
│       └── settings.json
├── mnemosyne/
│   ├── docs/
│   ├── chroma_db/
│   └── .config/
│       └── settings.json
├── aether/
│   └── .config/
│       └── settings.json
└── akasha/
    ├── akasha.db
    └── .config/
        └── settings.json
```

Cada app lê `{sync_root}/{app}/.config/settings.json` se `config_path` estiver definido no ecosystem.json, com fallback para o arquivo de configuração local. O banco do KOSMOS (`kosmos.db`) é mantido local por ser metadados de feeds — somente o archive de artigos é sincronizado.

### Portas reservadas (modo desenvolvimento)

Cada app que roda um servidor Vite ou web usa uma porta fixa com `strictPort: true`.
**Não altere essas portas** — elas estão hardcoded em múltiplos arquivos de configuração.

| App | Porta | Arquivo de referência |
|---|---|---|
| HUB | 5173 | `HUB/vite.config.ts` · `HUB/src-tauri/tauri.conf.json` |
| AETHER | 5174 | `AETHER/vite.config.ts` · `AETHER/src-tauri/tauri.conf.json` |
| OGMA | 5175 | `OGMA/vite.config.ts` · `OGMA/package.json` · `OGMA/src/main/main.ts` |
| AKASHA | 7071 | `AKASHA/config.py` |

KOSMOS, Mnemosyne e Hermes são apps desktop (PyQt6/PySide6) — não expõem portas de rede.

---

**Utilitários de integração:**

| Arquivo | Stack | Usado por |
|---|---|---|
| [`ecosystem_client.py`](ecosystem_client.py) | Python | KOSMOS, Mnemosyne, Hermes |
| [`OGMA/src/main/ecosystem.ts`](OGMA/src/main/ecosystem.ts) | TypeScript | OGMA |
| [`AETHER/src-tauri/src/ecosystem.rs`](AETHER/src-tauri/src/ecosystem.rs) | Rust | AETHER, HUB |

**Estado atual das fases:**

| Fase | Descrição | Estado |
|---|---|---|
| 0 | Fundação: `ecosystem.json` + utilitários Python/TS/Rust | ✅ Concluída |
| 1 | Interligação dos apps existentes | ✅ Concluída — 1.1, 1.2, 1.3, 1.4 |
| 2 | App Hub desktop (Tauri 2 + React) | ✅ Concluída — 2.1–2.6 |
| 3 | Android (APK via Tauri 2) | Não iniciada |
| 4 | Polimento e features extras | Não iniciada |

**Integrações ativas:**
- AETHER escreve `vault_path` e `exe_path` no startup
- KOSMOS escreve `archive_path`, `data_path` e `exe_path` no startup
- OGMA escreve `data_path` e `exe_path` no startup
- Mnemosyne escreve `watched_dir`, `vault_dir` (se configurado), `index_paths` e `exe_path` no startup; botão "Sugestões do ecossistema" preenche campos com caminhos do KOSMOS/AKASHA/AETHER
- Hermes escreve `output_dir` e `exe_path` no startup
- AKASHA escreve `base_url` e `exe_path` no startup; lê `archive_path` configurado pelo HUB
- HUB: lê `ecosystem.json` para descobrir dados de todos os apps; `apply_sync_root()` escreve `sync_root` + todos os caminhos de pasta de uma vez (preservando `exe_path` e demais campos)

---

## Padrões de desenvolvimento

Ver [CONTRIBUTING.md](CONTRIBUTING.md) para as regras completas: workflow de commits, convenções de erro, design system e nomenclatura de apps.

**Venv Python compartilhado:** `.venv/` na raiz do ecossistema — KOSMOS, Mnemosyne e Hermes apontam para ele nos scripts `iniciar.sh` / `hermes.py`.
