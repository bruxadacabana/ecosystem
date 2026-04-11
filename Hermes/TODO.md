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

- [ ] Histórico de transcrições (lista das últimas .md geradas)
- [ ] Preview do markdown gerado dentro do app
- [ ] Integração com Mnemosyne (enviar transcrição para indexação RAG)
- [ ] Modo batch: transcrever playlist inteira de uma vez
- [ ] Detecção de ffmpeg e aviso se não encontrado

---

## Bugs conhecidos

(nenhum por enquanto)
