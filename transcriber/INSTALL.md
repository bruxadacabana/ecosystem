# Video Transcriber — Guia de Instalação

Transcreve vídeos do **YouTube** e **TikTok** para arquivos **Markdown**, com timestamps, usando Whisper (OpenAI) localmente — sem custos de API.

---

## ▶ Windows — Instalação zero (automática)

**Não é necessário instalar nada manualmente.**

1. Extraia o ZIP em qualquer pasta
2. Clique duas vezes em **`iniciar_windows.bat`**
3. Na primeira execução, uma janela de progresso aparecerá e instalará automaticamente:
   - Python 3.11 portátil
   - FFmpeg portátil
   - yt-dlp e openai-whisper
4. Nas próximas execuções, o app abre diretamente

> ⚠ **Requisitos mínimos Windows:**
> - Windows 10 ou 11 (64-bit)
> - Conexão com internet (apenas na primeira execução, ~500 MB a 2 GB)
> - PowerShell (já vem no Windows — não precisa instalar)

Todos os arquivos são instalados dentro da pasta `_portable/`, **sem afetar o sistema**.  
Para desinstalar completamente, basta apagar a pasta do programa.

---

## 🐧 Pop!_OS / Linux

Instale as dependências manualmente (uma única vez):

```bash
# Dependências do sistema
sudo apt install python3 python3-pip ffmpeg

# Dependências Python
pip install yt-dlp openai-whisper --break-system-packages
```

> Ou com ambiente virtual:
> ```bash
> python3 -m venv venv
> source venv/bin/activate
> pip install yt-dlp openai-whisper
> ```

Execute:
```bash
chmod +x iniciar_linux.sh
./iniciar_linux.sh
```

---

## Uso

1. Cole a URL do YouTube ou TikTok no campo de entrada
2. Escolha o modelo Whisper:
   - `tiny` — mais rápido, menos preciso (~1 GB RAM)
   - `base` — equilíbrio rápido (~1 GB RAM)
   - `small` — **recomendado** (~2 GB RAM)
   - `medium` — boa precisão (~5 GB RAM)
   - `large` — máxima precisão (~10 GB RAM)
3. Escolha a pasta de saída
4. Clique em **▶ Transcrever**

O arquivo `.md` gerado conterá:
- Metadados (título, canal, duração, idioma)
- Transcrição com timestamps `[MM:SS]`

---

## Estrutura do Markdown gerado

```markdown
# Título do vídeo

> **Fonte:** https://...
> **Canal:** Nome do canal
> **Duração:** 12m 34s
> **Idioma detectado:** PT
> **Gerado em:** 2024-01-15 14:30

---

## Transcrição

**[00:00]** Olá, bem-vindos ao canal…

**[00:12]** Hoje vamos falar sobre…
```

---

## Solução de problemas

| Problema | Solução |
|----------|---------|
| `ModuleNotFoundError: yt_dlp` | `pip install yt-dlp` |
| `ModuleNotFoundError: whisper` | `pip install openai-whisper` |
| FFmpeg não encontrado | Instale o FFmpeg e adicione ao PATH |
| Erro de download TikTok | Atualize o yt-dlp: `pip install -U yt-dlp` |
| Lento demais | Use modelo `tiny` ou `base` |

---

## Dependências utilizadas

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — download de vídeos
- [openai-whisper](https://github.com/openai/whisper) — transcrição offline
- [tkinter](https://docs.python.org/3/library/tkinter.html) — interface gráfica (incluso no Python)
- [FFmpeg](https://ffmpeg.org/) — conversão de áudio
