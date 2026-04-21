# Hermes — TODO

> Criado: 2026-04-11

---

## ⚠ Padrões Obrigatórios

Ver `CONTRIBUTING.md` na raiz do ecossistema.

---

## Fase 1 — Implementação inicial (PyQt6)

- [x] Estrutura do projeto (Hermes/, data/, iniciar.sh, TODO.md)
- [x] App PyQt6 com duas abas: Descarregar + Transcrever
- [x] Paleta do ecossistema (Design Bible v2.0)
- [x] Carregamento de fontes IM Fell English + Special Elite via QFontDatabase
- [x] Aba Descarregar: URL → Inspecionar → seleção de formato → Download
- [x] Aba Descarregar: suporte a playlist (seleção individual + baixar tudo)
- [x] Aba Transcrever: URL → modelo Whisper + idioma + limite CPU → Markdown
- [x] Workers em QThread (download e transcrição em background)
- [x] Log compartilhado entre abas com tags de cor
- [x] Output dir configurável, persistido em .prefs.json
- [x] Iniciar.sh apontando para o .venv compartilhado

---

## Fase 2 — Melhorias

- [x] Transcrição de arquivos locais — campo "ARQUIVO LOCAL" na aba Transcrever;
      aceita mp4, mkv, avi, mov, webm, mp3, wav, m4a, ogg, flac; pula yt-dlp;
      se preenchido, tem prioridade sobre a URL
- [x] Histórico de transcrições (lista das últimas .md geradas)
- [x] Preview do markdown gerado dentro do app
- [x] Integração com Mnemosyne (enviar transcrição para indexação RAG)
- [ ] Modo batch: transcrever playlist inteira de uma vez
- [x] Detecção de ffmpeg e aviso se não encontrado

---

## Fase 3 — Mini API HTTP (integração com extensão AKASHA)

> Entrega: Hermes expõe um servidor HTTP local para receber requisições de download
> e transcrição de fontes externas (extensão Firefox via AKASHA). Roda em thread
> separada, invisível ao usuário, sem alterar a UI existente.

- [ ] `api_server.py` — servidor HTTP em `threading.Thread` usando `http.server` +
      `socketserver.TCPServer`; porta padrão 7072 (configurável em `.prefs.json`);
      inicia no `__init__` do app, para no `closeEvent`
- [ ] `POST /download` — recebe JSON `{url: str, format?: str}`; adiciona à fila
      de download reutilizando o worker existente; retorna
      `{"status": "queued", "url": url}` ou `{"error": "..."}` com status 400
- [ ] `POST /transcribe` — recebe JSON `{url: str}`; enfileira transcrição via
      worker existente; retorna `{"status": "queued", "url": url}`
- [ ] `GET /health` — retorna `{"status": "ok", "queue_size": n}`
- [ ] `hermes.py` — escrever `hermes.api_port` no `ecosystem.json` no startup
      (try/except silencioso — nunca bloquear abertura do app)
- [ ] Feedback visual: downloads/transcrições recebidos via API aparecem no log
      com badge `[API]` para distinguir de ações manuais

---

## Fase 4 — Expansão de sites suportados

> yt-dlp suporta 1000+ sites, mas a UI do Hermes pode ter lista ou validações
> que restringem o que é aceito. Objetivo: garantir que todos os principais
> sites de vídeo funcionem sem fricção.

- [ ] Auditar `hermes.py`: verificar se há lista de sites hardcoded ou validação
      de URL que limite os sites aceitos; remover restrições desnecessárias
- [ ] Testar e garantir suporte explícito a: YouTube, Vimeo, Twitch, Twitter/X,
      TikTok, Reddit (video), Instagram, Dailymotion, Bilibili, Niconico
- [ ] Testar formatos disponíveis por plataforma (algumas não separam vídeo+áudio)
- [ ] Adicionar tooltip ou link na UI apontando para lista oficial de sites do yt-dlp

---

## Bugs conhecidos

(nenhum por enquanto)
