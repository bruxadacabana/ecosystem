# 📖 Mnemosyne — Seu Bibliotecário Celeste

> *Guardião silencioso dos seus arquivos, onde a memória encontra o cosmos.*

Mnemosyne é um assistente de aprendizado local que organiza, resume e responde perguntas sobre seus documentos pessoais. Totalmente offline, ele usa RAG (Retrieval-Augmented Generation) com modelos locais via Ollama para transformar sua pasta de arquivos em uma biblioteca inteligente.

## 🌌 Por que Mnemosyne?

Na mitologia grega, **Mnemosyne** é a Titã da memória e mãe das musas. Seu nome significa "memória" e ela representa a fonte de todo conhecimento. Este programa leva seu nome para simbolizar a preservação e recuperação da sua informação pessoal, de forma ordenada e eterna.

Mnemosyne completa a tríade de ferramentas que desenvolvo:

- **OGMA** — gerenciador de projetos, estudos e leitura (a palavra em ação)
- **KOSMOS** — gerenciador de notícias (a ordem do mundo)
- **MNEMOSYNE** — assistente de arquivos locais (a memória pessoal)

Juntos, eles formam um ecossistema de conhecimento: o que você faz, o que acontece lá fora e o que você guarda.

---

## ✨ Funcionalidades

- **Indexação de documentos** — lê arquivos de uma pasta (e subpastas) e cria um índice vetorial local.
- **Respostas baseadas em RAG** — faça perguntas e receba respostas fundamentadas nos seus documentos.
- **Resumos automáticos** — gere resumos da coleção inteira.
- **Watcher de pasta** — monitora a pasta em tempo real e indexa automaticamente arquivos novos.
- **Seleção dinâmica de modelos** — detecta os modelos instalados no Ollama e apresenta para escolha na UI.
- **Interface gráfica nativa** — construída com PySide6 (Qt), sem necessidade de navegador.
- **Totalmente offline** — após baixar os modelos, todos os dados permanecem no seu computador.
- **Multi‑formato** — suporte a `.txt`, `.pdf`, `.docx`, `.md`.

---

## 🎨 Estética e Filosofia de Design

Mnemosyne foi projetada para ser uma experiência visual que une o acolhedor de uma biblioteca antiga com o infinito do cosmos.

- **Paleta de cores**:
  - Off‑white (`#FDF8F0`) como base, evocando papel envelhecido.
  - Marrom‑sépia (`#D4C4B0`) e ouro queimado (`#C9A87C`) para detalhes.
  - Azul‑meia‑noite (`#1E2A3E`) para elementos de destaque, como o céu estrelado.
- **Tipografia**:
  - Títulos em *Playfair Display* (serifada elegante, remetendo a livros antigos).
  - Corpo e respostas em *Cormorant Garamond* ou *Courier Prime* (estilo máquina de escrever).
- **Elementos visuais**:
  - Fundo com textura sutil de papel envelhecido.
  - Constelações discretas aparecem em cantos ou como sublinhados.
  - Botões com bordas de "fita datilográfica" e ícones dourados.
  - Animações suaves durante indexação e recuperação (estrelas cadentes, espirais de luz).
- **Metáfora central**: **"O Arquivo Celeste"** — um fichário infinito onde cada documento é uma estrela, e a busca traça constelações entre eles.

Essa identidade visual dialoga com OGMA e KOSMOS, mas dá a Mnemosyne uma personalidade própria: a guardiã silenciosa e organizada, entre o bibliotecário antiquário e o astrônomo místico.

---

## 📦 Requisitos

- **Python 3.10 ou superior**
- **Ollama** instalado e em execução (https://ollama.com/)
- Pelo menos um modelo de chat e um de embedding instalados no Ollama.
- **Dependências Python** (listadas no `requirements.txt`):
  - `PySide6` — interface gráfica
  - `langchain`, `langchain-chroma`, `langchain-ollama` — cadeia RAG
  - `chromadb` — vectorstore local
  - `pypdf`, `python-docx` — leitura de PDF e DOCX
  - `tiktoken` — tokenização
  - `rank-bm25` — hybrid retrieval

### Modelos recomendados

O app detecta automaticamente qualquer modelo instalado no Ollama. Recomendações testadas para hardware com **GPU AMD (RX 6600 / 8 GB VRAM)**:

| Uso | Modelo | VRAM (Q4_K_M) | Velocidade |
|---|---|---|---|
| Chat/QA ⭐ | `qwen3:8b-q4_K_M` | ~4.6 GB | ~30–45 t/s |
| Chat leve | `gemma3:4b-q4_K_M` | ~3.0 GB | ~50–70 t/s |
| Chat alta qualidade | `gemma3:12b-q4_K_M` | ~6.7 GB | ~15–25 t/s |
| Embedding ⭐ | `bge-m3` | ~0.6 GB | — |
| Embedding alternativo | `nomic-embed-text-v2-moe` | ~0.4 GB | — |

```bash
ollama pull qwen3:8b-q4_K_M
ollama pull bge-m3
```

> **GPU AMD (Linux):** o RX 6600 (gfx1032, RDNA2) não está na lista oficial do ROCm. No Linux, o workaround estável é definir antes de subir o Ollama:
> ```fish
> set -x HSA_OVERRIDE_GFX_VERSION 10.3.0
> ```
> Adicione a `~/.config/fish/config.fish` (ou equivalente no seu shell). Sem isso, o Ollama usa CPU.
> **Atenção:** o workaround **não funciona via WSL2 no Windows** — no Windows 10, o Ollama roda na CPU independentemente.

> **Embedding e português:** `nomic-embed-text v1` e `mxbai-embed-large` têm recall muito baixo em textos em português. Prefira `bge-m3`. O `nomic-embed-text-v2-moe` é uma alternativa multilíngue mais leve, muito superior ao v1.

---

## 🚀 Instalação

1. **Clone ou crie o projeto**:

```bash
git clone https://github.com/seu-usuario/mnemosyne.git
cd mnemosyne
```

2. **Crie e ative um ambiente virtual**:

```bash
python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows
```

3. **Instale as dependências**:

```bash
pip install -r requirements.txt
```

4. **Certifique‑se de que o Ollama está rodando**:

```bash
ollama serve
```

---

## ▶️ Como usar

1. **Execute o programa**:

```bash
python main.py
```

2. **Na primeira execução**, o app verifica o Ollama e abre o diálogo de configuração:
   - **Pasta monitorada** — selecione a pasta com seus documentos (caminho absoluto).
   - **Modelo LLM** — escolha entre os modelos de chat detectados no Ollama.
   - **Modelo de embedding** — escolha o modelo de embedding detectado.
   - O índice fica salvo em `<pasta>/.mnemosyne/chroma_db` (junto dos seus documentos).

3. **Na interface**:
   - Clique em **Indexar tudo** para criar o índice inicial.
   - A pasta é monitorada automaticamente: novos arquivos são indexados sem intervenção.
   - Aba **Perguntar** — escreva sua pergunta e pressione Enter.
   - Aba **Resumir** — gera síntese de todos os documentos indexados.
   - Aba **Gerenciar** — mostra status da pasta, watcher e log de eventos.

---

## 🧩 Estrutura do Projeto

```
mnemosyne/
├── main.py                 # ponto de entrada
├── config.json             # configuração do usuário (gerada pelo app)
├── gui/
│   ├── main_window.py      # janela principal + diálogo de configuração
│   ├── workers.py          # QThread para indexação, consulta, resumo
│   └── styles.qss          # folha de estilo Qt
├── core/
│   ├── errors.py           # hierarquia de exceções tipadas
│   ├── config.py           # AppConfig dataclass + load/save
│   ├── ollama_client.py    # detecção dinâmica de modelos Ollama
│   ├── loaders.py          # carregadores PDF/DOCX/TXT/MD
│   ├── indexer.py          # criação/carga/atualização do vectorstore
│   ├── rag.py              # cadeia RAG + AskResult
│   ├── summarizer.py       # geração de resumos
│   ├── memory.py           # SessionMemory + CollectionIndex
│   └── watcher.py          # FolderWatcher (QFileSystemWatcher)
├── requirements.txt
└── TODO.md                 # roadmap de desenvolvimento
```

O índice vetorial é criado em `<pasta_monitorada>/.mnemosyne/chroma_db` — fica junto dos seus documentos e é portável.

---

## ⚙️ Personalização

### Modelos do Ollama

Os modelos são selecionados na interface — clique em **Configurar** a qualquer momento para trocar. A configuração é salva em `config.json`. Qualquer modelo instalado no Ollama aparece automaticamente na lista.

### Estilo visual

Edite `gui/styles.qss` para modificar cores, fontes e outros aspectos. Para adicionar uma imagem de fundo com constelações, você pode usar:

```css
QMainWindow {
    background-image: url(:/images/constellations.png);
    background-repeat: no-repeat;
    background-position: bottom right;
}
```

(É necessário adicionar o arquivo de recurso no Qt.)

---

## 🛠️ Solução de problemas

- **"Ollama não encontrado"** (banner amarelo)  
  Inicie o servidor com `ollama serve` em um terminal separado. O app detecta automaticamente quando voltar a ficar disponível ao reiniciar.

- **Nenhum modelo aparece no diálogo de configuração**  
  Verifique se há modelos instalados com `ollama list`. Instale com `ollama pull qwen3.5:9b` e `ollama pull nomic-embed-text` (ou qualquer outro de sua preferência).

- **A interface fica congelada**  
  As operações demoradas rodam em threads separadas. Se mesmo assim travar, pode ser um problema de recursos. Tente reduzir o `chunk_size` ou o número de documentos.

- **Arquivos não são carregados**  
  Formatos suportados: `.pdf`, `.docx`, `.txt`, `.md`. Arquivos dentro de `.mnemosyne/` são ignorados automaticamente.

---

## 🗺️ Próximos passos (ver TODO.md)

- `core/tracker.py` — indexação incremental por hash SHA-256
- Hybrid retrieval (BM25 + semântico) para respostas mais precisas
- UI com fontes do ecossistema (IM Fell English, Special Elite, Courier Prime)

---

## 📜 Licença

Este projeto está sob a licença MIT. Sinta‑se livre para usar, modificar e distribuir.

---

## 🌠 Créditos

- Ícones e design inspirados em **papel envelhecido** e **mapas estelares antigos**.
- Construído com [PySide6](https://doc.qt.io/qtforpython-6/), [LangChain](https://www.langchain.com/) e [Ollama](https://ollama.com/).

---

*Que sua memória seja tão vasta quanto o céu.*