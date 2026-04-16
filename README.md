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
**Estado:** Em desenvolvimento ativo (módulos Escrita e Configuração prontos).

---

### OGMA — Grimório de Projetos

Gerenciador unificado de projetos, estudos e leituras. Cada projeto tem páginas com editor de blocos rico, propriedades customizáveis e um banco local que sincroniza opcionalmente com o Turso.

- Projetos do tipo criativo, técnico, estudo, leitura
- Editor de blocos com imagens, tabelas, checklists, código
- Tags, filtros, busca por texto
- Offline-first: funciona 100% local; Turso é opt-in

**Stack:** Electron · TypeScript + React + Vite  
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

**Stack:** Python + PyQt6 · yt-dlp · openai-whisper  
**Estado:** Fase 1 completa.

---

### AKASHA — Registros do Universo

Buscador pessoal local. Agrega resultados da web e do próprio ecossistema numa interface única, com suporte a downloads genéricos e integração com qBittorrent. Roda como servidor local acessado via browser — sem conta, sem nuvem.

- Busca web: agrega DuckDuckGo e outros providers; resultados unificados com deduplicação
- Busca local: pesquisa no archive do KOSMOS, vault do AETHER e index do Mnemosyne
- Downloads: arquivos genéricos (PDF, imagens, ZIPs); arquivar página diretamente no KOSMOS
- qBittorrent: adicionar torrent/magnet, acompanhar fila e progresso
- Integração com ecossistema: delega vídeo/áudio ao Hermes; lê `ecosystem.json` para caminhos

**Stack:** Python + FastAPI · HTMX + Jinja2 · SQLite · uv  
**Estado:** Fases 1–3, 5 e 7 concluídas. Busca web + local + biblioteca de URLs funcionais.  
**Porta:** 7070

---

## Etimologia — A alma dos nomes

Cada app do ecossistema tem nome derivado de mitologia, línguas antigas ou conceitos esotéricos e cósmicos. Essa etimologia não é decorativa — é a alma de cada ferramenta.

---

### AETHER — *pronuncia-se: ay-ther*

**Origem:** Grego antigo *αἰθήρ* (aithḗr), da raiz *aíthō* — "queimar", "brilhar com luz própria".

**O conceito:** O quinto elemento da cosmologia grega — além da terra, água, fogo e ar. A substância pura e luminosa dos céus, o que os deuses respiravam, o meio pelo qual a luz viajava. Diferente do ar mortal: o Aether é eterno, imutável, a quintessência que preenche o espaço além da esfera lunar. Aristóteles o descreveu como o material de que as estrelas são feitas.

**No ecossistema:** o espaço etéreo onde histórias existem antes de se materializarem em palavras.

---

### OGMA — *pronuncia-se: og-mah*

**Origem:** Irlandês antigo *Ogma*, proto-céltico *Ogmios* — intimamente ligado a *ogam*, o alfabeto mais antigo da Irlanda, entalhado em bordas de pedra e osso.

**O conceito:** Divindade irlandesa da eloquência, escrita e letras. Criador do Ogham — o sistema de escrita céltico onde cada letra é uma série de entalhes sobre uma aresta, a escrita como marca física e permanente no mundo. Representado como um ancião de aparência nobre com uma corrente dourada saindo da língua, cujas extremidades se prendiam às línguas de todos que o seguiam: símbolo do poder da linguagem de conectar, conduzir e persuadir.

**No ecossistema:** o deus que dá forma ao pensamento — gerenciador de projetos, estudos e escritas.

---

### KOSMOS — *pronuncia-se: koz-mos*

**Origem:** Grego *κόσμος* (kósmos) — ordem, harmonia, ornamento, universo. A mesma raiz de "cosmético": algo que organiza e embeleza o que era caótico.

**O conceito:** Oposto semântico e filosófico ao Caos primordial. Para os gregos, o cosmos não era apenas o universo físico — era a prova de que o universo *tem sentido*, que há uma ordem inteligível subjacente a tudo. Pitágoras foi o primeiro a usar o termo para descrever o universo como uma totalidade ordenada e harmônica. O Kosmos implica que tudo tem seu lugar, sua relação, sua proporção.

**No ecossistema:** impõe ordem ao fluxo caótico da web — leitor RSS e agregador de feeds.

---

### Mnemosyne — *pronuncia-se: nem-oz-ih-nee*

**Origem:** Grego *Μνημοσύνη* (Mnēmosýnē), da raiz *mnēmē* — "memória", "lembrança". Cognata de *mnemon* (aquele que lembra) e ancestral direta de "mnemônico".

**O conceito:** Titânide grega, filha de Urano e Gaia, personificação da Memória em sua forma mais absoluta. Mãe das nove Musas — todas as artes nascem da memória. No submundo, guardava o rio Mnemosyne, oposto ao Letes (o esquecimento). Almas corajosas que bebessem de Mnemosyne antes de reencarnar lembrariam de tudo que já haviam vivido — saberiam quem eram. A memória como identidade e como poder.

**No ecossistema:** guarda e recupera o conhecimento indexado — assistente RAG local com Ollama.

---

### Hermes — *pronuncia-se: her-meez*

**Origem:** Grego *Ἑρμῆς* (Hermês) — origem pré-grega incerta; associado a *herma*, pilha de pedras usada como marcador de caminhos e fronteiras.

**O conceito:** Mensageiro dos deuses olímpicos, guia das almas entre mundos (*psicopompo*), deus das viagens, comércio e comunicação. O único olímpico que transitava livremente entre o Olimpo, o mundo dos vivos e o Hades — o mediador por excelência. Inventor da lira, da flauta e do alfabeto. Seu símbolo, o caduceu (duas serpentes entrelaçadas), é a representação do movimento entre opostos.

**No ecossistema:** o mensageiro que traz conteúdo de outros domínios — downloader e transcritor de vídeos.

---

### AKASHA — *pronuncia-se: ah-kah-shah*

**Origem:** Sânscrito *ākāśa* (आकाश), da raiz *kāś* — "aparecer", "ser visível", "brilhar". Significado literal: "espaço luminoso", "éter".

**O conceito:** Na cosmologia hindu/vedanta, o quinto elemento — o substrato invisível que permeia e contém todos os outros quatro. Diferente do Aether grego (substância dos céus), Akasha é o próprio espaço onde tudo existe, ressoa e persiste. No esoterismo ocidental (Teosofia, século XIX), os *Registros Akáshicos* são descritos como uma biblioteca cósmica imaterial onde cada pensamento, palavra e ação — passados, presentes e futuros — está eternamente gravada no tecido do universo. Consultar os Registros é acessar o conhecimento total: tudo que já foi pesquisado, descoberto, criado ou dito.

**No ecossistema:** o buscador que consulta os registros universais — web e ecossistema local num só lugar.

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
  "aether":    { "vault_path": "/caminho/para/vault" },
  "kosmos":    { "data_path": "...", "archive_path": "..." },
  "ogma":      { "data_path": "" },
  "mnemosyne": { "index_paths": [] },
  "hub":       { "data_path": "" }
}
```

### Portas reservadas (modo desenvolvimento)

Cada app que roda um servidor Vite ou web usa uma porta fixa com `strictPort: true`.
**Não altere essas portas** — elas estão hardcoded em múltiplos arquivos de configuração.

| App | Porta | Arquivo de referência |
|---|---|---|
| HUB | 5173 | `HUB/vite.config.ts` · `HUB/src-tauri/tauri.conf.json` |
| AETHER | 5174 | `AETHER/vite.config.ts` · `AETHER/src-tauri/tauri.conf.json` |
| OGMA | 5175 | `OGMA/vite.config.ts` · `OGMA/package.json` · `OGMA/src/main/main.ts` |
| AKASHA | 7070 | `AKASHA/config.py` |

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
| 1 | Interligação dos apps existentes | 🔄 Em progresso (1.2, 1.3 prontas) |
| 2 | App Hub desktop (Tauri 2 + React) | 🔄 Em progresso (2.1, 2.2 prontas) |
| 3 | Android (APK via Tauri 2) | Não iniciada |
| 4 | Polimento e features extras | Não iniciada |

**Integrações ativas:**
- AETHER escreve `vault_path` no startup (ao carregar o vault)
- KOSMOS escreve `data_path` e `archive_path` no startup
- Mnemosyne: botão "Sugestões do ecossistema" na tela de indexação preenche campos com caminhos do KOSMOS/AETHER
- HUB: lê `ecosystem.json` para descobrir onde cada app armazena seus dados; permite reconfigurar caminhos via tela de setup

---

## Padrões de desenvolvimento

Ver [CONTRIBUTING.md](CONTRIBUTING.md) para as regras completas: workflow de commits, convenções de erro, design system e nomenclatura de apps.

**Venv Python compartilhado:** `.venv/` na raiz do ecossistema — KOSMOS, Mnemosyne e Hermes apontam para ele nos scripts `iniciar.sh` / `hermes.py`.
