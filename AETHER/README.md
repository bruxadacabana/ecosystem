# AETHER — Forja de Mundos

Editor de escrita criativa local, focado em narrativa e worldbuilding.  
Parte do ecossistema pessoal: **OGMA · KOSMOS · MNEMOSYNE · AETHER**

---

## O que é

AETHER é um editor de texto desktop para escrita criativa — livros, séries, fanfiction e qualquer narrativa longa. Inspirado no Scrivener e no Ellipsus, mas completamente local, sem conta, sem nuvem, sem telemetria.

A premissa: o ato de escrever importa tanto quanto o conteúdo escrito. A interface foi projetada para ser um objeto com personalidade — papel envelhecido, tinta, cosmos e máquina de escrever — não apenas uma ferramenta neutra.

---

## Funcionalidades

**Implementado**

- Projetos do tipo livro único, série ou fanfiction
- Metadados de projeto: gênero, idioma, público-alvo, tags, worldbuilding
- Dashboard por projeto com estatísticas (palavras, capítulos, data)
- Binder lateral com árvore Livros > Capítulos, CRUD completo, reordenação
- Status por capítulo (Rascunho / Revisão / Final)
- Sinopse por capítulo editável direto no binder
- Editor WYSIWYG por capítulo com auto-save (500ms debounce)
- Temas sépia (padrão), claro e escuro
- Tipografia customizável: tamanho, entrelinhamento, largura da coluna
- Modo foco (distraction-free) — oculta toda a chrome da UI
- Modo typewriter — cursor centralizado verticalmente durante a escrita
- Localizar e substituir (Ctrl+F) com destaques em tempo real
- Tela cheia (F11)
- Contagem de palavras e caracteres em tempo real
- Sistema de logs em arquivo com rotação de 7 dias

- Vista mural (corkboard): cartões de capítulo com título e sinopse
- Vista esboço (outline): tabela com status, sinopse e palavras por capítulo
- Lixeira: capítulos excluídos ficam recuperáveis
- Scratchpad por capítulo (bloco de notas persistido)
- Modo split: editor + notas/vínculos/histórico/anotações lado a lado

- Fichas de personagem com campos livres customizáveis
- Relacionamentos entre personagens (tipo, nota, direção)
- Notas de worldbuilding por categoria (locais, facções, objetos, conceitos)
- Linha do tempo de eventos com vínculos a personagens e notas
- Imagens anexadas a personagens e locais (armazenadas localmente no vault)
- Vínculos capítulo ↔ personagens/locais via painel lateral do editor

- Meta de palavras por capítulo (barra de progresso no editor)
- Meta de palavras por livro (progresso no painel de estatísticas)
- Sessão de escrita com timer automático (início ao abrir capítulo)
- Streak de escrita diária (dias consecutivos com progresso)
- Painel de estatísticas: palavras totais, distribuição de status, gráfico de 14 dias
- Snapshots de capítulo: histórico manual de versões com preview e restauração
- Anotações inline: notas associadas a trechos específicos do capítulo

**Roadmap**

- Exportação: Markdown, texto plano, DOCX, PDF, EPUB

---

## Armazenamento

O AETHER segue o modelo de vault do Obsidian. O usuário escolhe uma pasta raiz e seus dados vivem ali — portáteis, controláveis, versionáveis com git.

**AppData do sistema** — apenas o caminho do último vault aberto:
```
~/.local/share/aether/app.json        (Linux)
%AppData%\aether\app.json             (Windows)
```

**Dentro do vault** — tudo o mais:
```
{vault}/
├── .aether/                  configurações e dados internos do app
│   └── config.json           tema, fonte, estado da UI, etc.
├── {projeto}/
│   ├── project.json          metadados do projeto
│   └── {livro}/
│       ├── book.json         metadados do livro
│       └── {capitulo}.md     conteúdo dos capítulos
```

Mover ou copiar a pasta vault para outro computador preserva tudo. O AppData guarda só o suficiente para reabrir automaticamente na próxima vez.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Backend / I/O | Rust (Tauri v2) |
| Frontend / UI | TypeScript + React + Vite |
| Armazenamento | Arquivos locais (JSON + Markdown) |
| Build | Tauri CLI |

**Princípios de código:**
- Rust: toda função que pode falhar retorna `Result<T, AppError>` — sem `.unwrap()` em produção
- TypeScript: `strict: true`, erros tipados com discriminated unions
- Zero dependências de rede em runtime

---

## Design

O AETHER compartilha o sistema visual do ecossistema (definido no OGMA Design Bible):

- Paleta sépia — papel envelhecido, tinta, dourado
- Tipografia: IM Fell English · Special Elite · Courier Prime
- Sombras flat sem blur, animações curtas (máx. 300ms)

Diferenciais visuais exclusivos do AETHER:
- `pageFloat` — folhas de papel caem ao criar/abrir/deletar capítulos
- `typewriterReveal` — texto revela caractere a caractere no splash
- `etherPulse` — nebulosas animadas nos headers de projeto
- Constelações com labels mitológicos no cosmos de fundo

---

## Como rodar

Pré-requisitos: [Rust](https://rustup.rs) · Node.js 18+ · dependências do Tauri para Linux/Windows

```bash
# Instalar dependências
npm install

# Rodar em modo desenvolvimento
cargo tauri dev

# Build de produção
cargo tauri build
```

---

## Privacidade

O AETHER não coleta, transmite nem registra nenhum dado. Nenhuma conexão externa é feita sem ação explícita do usuário. Todo o processamento acontece localmente.

---

## Roadmap

O desenvolvimento segue fases progressivas — cada fase entrega uma parte utilizável do programa. Ver [dev_files/todo](dev_files/todo) para o estado atual.

| Fase | Entregável | Status |
|---|---|---|
| 0 | Design system completo | ✓ |
| 1 | Criar projetos, capítulos e escrever | ✓ |
| 2 | Experiência de escrita (foco, temas, tipografia) | ✓ |
| 3 | Organização avançada (corkboard, outline, lixeira) | ✓ |
| 4 | Personagens & Worldbuilding | ✓ |
| 5 | Metas, estatísticas e snapshots | ✓ |
| 6 | Exportação | — |
| 7 | Polimento e distribuição | — |
