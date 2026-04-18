# Diretivas do Ecossistema — program files/

Instruções para o Claude Code ao trabalhar neste repositório.

---

## Plataformas alvo

**Todos os apps devem rodar no Windows 10 e no CachyOS (Linux).**

- Usar APIs de path da linguagem, nunca separadores hardcoded (`/` ou `\`)
- O diretório de trabalho da usuária contém espaços no nome — testar caminhos com espaços
- Sem dependências exclusivas de uma plataforma
- Apps Python: compatível com `uv` em ambos os SOs
- Apps Tauri: `cargo tauri build` deve funcionar nos dois targets

### Hardware — Computador de trabalho (Windows 10)

- CPU: Intel Core i5-3470, Ivy Bridge 2012, 4 cores/4 threads, 3.2 GHz — **sem AVX2**
- RAM: 8 GB
- GPU: Intel HD Graphics integrada (32 MB dedicados — inútil para ML)
- OS: Windows 10 x64

Implicações: modelos de embedding pesados (ex: bge-m3) saturam o CPU e travam o sistema.
Soluções: indexar só na máquina de casa e sincronizar vectorstore; ou usar embedding estático leve.

### Hardware — Computador principal (CachyOS)

- CPU: não especificado
- RAM: 16 GB
- GPU: AMD Radeon RX 6600, RDNA2, 8 GB VRAM (gfx1032) — ROCm com `HSA_OVERRIDE_GFX_VERSION=10.3.0`
- OS: CachyOS (Arch Linux), Niri + Fish shell
- Armazenamento: ~2 TB (3 SSDs)

---

## Princípio de erros

**Tratamento de erros com tipagem é prioridade absoluta em todo o ecossistema.**

- **Rust (AETHER):** toda função falível retorna `Result<T, AppError>`. Zero `.unwrap()` em produção.
- **TypeScript (OGMA):** `strict: true`. Erros tipados com discriminated unions. Nunca `any`.
- **Python (KOSMOS · Mnemosyne · Hermes):** `except ValueError` (específico), nunca `except Exception` genérico sem re-tipar.

---

## Workflow

- Manter o `TODO.md` / `ROADMAP.md` / `dev_files/todo` de cada app atualizado (sempre acrescentar itens que não constam nele antes de começar a implementação e marcar como concluido após)
- Commit por item individual concluído
- **Nunca começar a implementar nada sem ordem explícita da usuária.** Discussão, planejamento e anotação no TODO não são ordens de implementação.
- **Nunca avançar de um item para o próximo no TODO sem ordem explícita.** "Continue" sem especificar o quê não é autorização para implementar.
- Toda pesquisa do Mnemosyne vai para `Mnemosyne/pesquisa.txt`

---

## Design

O sistema visual é definido no `DESIGN_BIBLE.txt` (raiz). A paleta canônica está em:
- `AETHER/src/styles/tokens.css` (web)
- `ecosystem_qt.py` → `build_qss()` (PyQt6: KOSMOS, Hermes)
- `Mnemosyne/gui/styles.qss` (PySide6)

Modo noturno: "Atlas Astronômico à Meia-Noite" (`#12161E` base).
