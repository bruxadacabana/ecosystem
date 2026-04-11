# ECOSSISTEMA — Padrões e Regras Obrigatórias

Regras inegociáveis que se aplicam a **todos** os apps.
Nenhum item está concluído se estas regras não forem seguidas.

---

## 1. Tratamento de Erros com Tipagem

**Prioridade absoluta em todo o ecossistema, em todas as stacks.**

O caminho de erro recebe o mesmo cuidado que o caminho feliz.
Nenhuma feature está "pronta" se os erros forem silenciados, genéricos ou sem tipo.

### Rust (AETHER, HUB)
- Toda função que pode falhar retorna `Result<T, AppError>`
- Zero `.unwrap()` ou `.expect()` em código de produção
- `AppError` enum cobre todos os casos de falha relevantes

### TypeScript (OGMA, HUB)
- `strict: true` obrigatório em todos os `tsconfig.json`
- Erros tipados com discriminated unions:
  `{ ok: true; data: T } | { ok: false; error: AppError }`
- Nunca `any`, nunca `catch (e: any)` sem re-tipar
- Nunca `.then((r: any) => ...)` sem encapsulamento tipado
- `async/await` preferido sobre `.then()` encadeado

### Python (KOSMOS, Mnemosyne, utilitários)
- Nunca `except Exception` sem re-tipar para tipo específico
- Capturar com tipos explícitos: `except ValueError`, `except IOError`, etc.
- Funções críticas anotadas: `-> T | None` ou via padrão `Result`
- `log.error()` para falhas reais; `log.warning()` só para condições recuperáveis
- Erros nunca engolidos silenciosamente — propagar, retornar valor verificável
  ou dar feedback visível ao usuário

---

## 2. Workflow de Desenvolvimento

### TODO.md por app
- Toda funcionalidade ou mudança pedida deve ser anotada no `TODO.md` do app
  **antes** de ser implementada
- Marcar como `[x]` imediatamente ao concluir cada item
- Nunca acumular itens sem marcar

### Commits
- Fazer commit **após cada item individual** do TODO
- Mensagem descritiva do que foi feito (não do que vai ser feito)
- Nunca acumular múltiplos itens em um commit
- Nunca commitar sem que o item esteja marcado como `[x]` no TODO

### Fases
- Nunca passar de uma fase para a próxima sem **aprovação explícita**
- Ao terminar o último item de uma fase, notificar e aguardar instrução
- Não implementar itens de fase futura enquanto a atual estiver incompleta

---

## 3. Privacidade — Local-First

- Nenhum app coleta, transmite ou registra dados do usuário sem solicitação explícita
- Zero telemetria, zero analytics, zero conexões externas não solicitadas
- Dados ficam na máquina do usuário — nunca em servidores de terceiros por padrão
- Toda conexão externa (API, sync, Ollama) é opt-in e configurável

---

## 4. Design System

Todos os apps seguem o `DESIGN_BIBLE.txt` na raiz do ecossistema.

### Fontes — exatamente três, nenhuma outra
- `IM Fell English` — títulos, conteúdo de editor, sempre itálico
- `Special Elite` — corpo do app, botões, labels, nunca itálico
- `Courier Prime` — código exclusivamente

### Paleta — sépia, nunca cores vibrantes
- Usar as variáveis CSS definidas na bible (`--paper`, `--ink`, `--accent`, etc.)
- Nunca `#000` puro ou `#FFF` puro
- Cores dessaturadas como pigmentos envelhecidos

### Componentes
- `border-radius: 2px` em tudo (exceto pills: `20px`)
- Sombra flat sem blur: `X Y 0px var(--cor)` — nunca blur
- Animações máximo 300ms
- Todo hover tem feedback visual; todo clique tem transform

---

## 5. Nomenclatura dos Apps

Novos apps devem ter nome derivado de:
- Mitologia (grega, nórdica, celta, egípcia, etc.)
- Língua antiga (latim, grego, sânscrito, irlandês antigo, etc.)
- Conceito hermético, alquímico ou astronômico

O nome é o primeiro símbolo do app — deve carregar significado.
Nunca nomes genéricos ou descritivos modernos.

---

## 6. Estrutura do Repositório

- Um único repositório git para todo o ecossistema (`program files/`)
- `.venv/` compartilhado na raiz para todos os apps Python
- `.gitignore` na raiz cobre dados de runtime, builds e ambientes
- Arquivos compartilhados na raiz: `DESIGN_BIBLE.txt`, `ECOSYSTEM_TODO.md`, `CONTRIBUTING.md`
- Cada app mantém seu próprio `TODO.md` interno

---

## 7. Venv Python Compartilhado

O ambiente virtual fica em `program files/.venv/` — **um nível acima** de cada app.

Scripts de inicialização devem apontar para:
```bash
VENV_DIR="$(dirname "$0")/../.venv"
source "$VENV_DIR/bin/activate"
```

Nunca criar `venv/` local dentro da pasta do app.
