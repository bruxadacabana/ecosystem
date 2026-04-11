# Video Transcriber

Transcreve videos do YouTube e TikTok para Markdown usando Whisper localmente.

## Instalacao rapida (recomendado)

### Com uv

```bash
# Instala o uv (caso nao tenha)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Instala dependencias do sistema (FFmpeg + tkinter)
# Pop!_OS / Ubuntu:
sudo apt install ffmpeg python3-tk -y

# Arch / Manjaro:
yay -S ffmpeg tk

# Clona ou extrai o projeto e rode:
uv run transcriber.py
```

O `uv` cria e gerencia o ambiente virtual automaticamente na primeira execucao.

### Com venv tradicional

```bash
python3 -m venv venv
source venv/bin/activate
pip install yt-dlp openai-whisper
python3 transcriber.py
```

## Uso

```bash
# Com uv (qualquer plataforma):
uv run transcriber.py

# Ou pelo launcher:
./iniciar_linux.sh
```

## Dependencias

| Pacote | Funcao |
|--------|--------|
| yt-dlp | Download de audio do YouTube/TikTok |
| openai-whisper | Transcricao de audio (local, sem API) |
| ffmpeg | Conversao de audio (instalar via apt/pacman) |
| tkinter | Interface grafica (incluido no Python) |

## Windows

Clique duas vezes em `iniciar_windows.bat` — instala tudo automaticamente.
