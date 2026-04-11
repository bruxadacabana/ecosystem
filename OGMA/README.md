# OGMA

Gerenciador unificado de projetos, estudos e leituras.
Estética de papel envelhecido · máquina de escrever · cosmos.
Stack: Electron + React + TypeScript + @libsql/client (Turso).

> **Plataformas suportadas:** CachyOS (Arch Linux) e Windows 10.

---

## Pré-requisitos

### Node.js >= 22 LTS (inclui npm)

O `npm` vem junto com o Node.js — não é necessário instalá-lo separadamente.

**CachyOS / Arch Linux** — via `nvm` (recomendado):
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
# Reinicie o terminal, depois:
nvm install 22
nvm use 22
```

**Windows 10** — via `nvm-windows`:
1. Baixe e instale o [nvm-windows](https://github.com/coreybutler/nvm-windows/releases/latest) (`nvm-setup.exe`)
2. Abra um terminal como Administrador e execute:
```powershell
nvm install 22
nvm use 22
```

**Alternativa:** Baixe o instalador diretamente em [nodejs.org](https://nodejs.org) e escolha a versão LTS.

Para verificar se a instalação funcionou:
```bash
node -v   # deve mostrar v22.x.x
npm -v    # deve mostrar 10.x.x ou superior
```

### Git

- **CachyOS:** `sudo pacman -S git`
- **Windows 10:** [git-scm.com/downloads](https://git-scm.com/downloads)

### Dependências adicionais (CachyOS)

O script `iniciar.sh` usa `xdotool` para trazer a janela ao foco se o OGMA já estiver aberto:
```bash
sudo pacman -S xdotool
```
> Opcional — o OGMA funciona normalmente sem ele, apenas o foco automático deixará de funcionar.

---

## Instalação e Execução

```bash
# 1. Clone o repositório
git clone <url-do-repositório>
cd OGMA

# 2. Instale as dependências
npm install

# 3. Inicie em modo desenvolvimento
npm run dev
```

**Atalhos por plataforma:**
- **CachyOS:** `./iniciar.sh` — detecta se já está rodando, trata Wayland/X11, redireciona logs para `/tmp/ogma.log`
- **Windows 10:** `iniciar.bat` ou `iniciar.vbs` (sem janela de terminal)

---

## ☁️ Sincronização com a Nuvem (Turso) — Opcional

O OGMA usa arquitetura *offline-first*: funciona 100% localmente e sincroniza em background com o Turso quando configurado.

> **Uso offline puro:** não configure o arquivo `data/.env`. O OGMA detectará a ausência das credenciais e funcionará só no modo local.

Para ativar a sincronização:

1. Crie uma conta gratuita em [turso.tech](https://turso.tech).
2. Instale a CLI do Turso:
   ```bash
   # CachyOS
   curl -sSfL https://get.tur.so/install.sh | bash
   # Windows 10: use WSL ou siga a documentação oficial em turso.tech
   ```
3. Autentique-se:
   ```bash
   turso auth login
   ```
4. Crie o banco remoto:
   ```bash
   turso db create ogma
   ```
5. Obtenha a URL (começa com `libsql://`):
   ```bash
   turso db show ogma
   ```
6. Gere um token:
   ```bash
   turso db tokens create ogma
   ```
7. Crie o arquivo `data/.env` na raiz do projeto:
   ```env
   TURSO_URL=libsql://sua-url-aqui.turso.io
   TURSO_TOKEN=seu_token_aqui
   ```

---

## 📜 Scripts Disponíveis

| Comando              | Descrição                                       |
|----------------------|-------------------------------------------------|
| `npm run dev`        | Inicia Vite + Electron em modo desenvolvimento  |
| `npm run build`      | Build completo (renderer + main)                |
| `npm run typecheck`  | Verifica tipos TypeScript sem compilar          |
| `npm run dist:linux` | Gera AppImage + .deb                            |
| `npm run dist:win`   | Gera instalador NSIS (.exe)                     |

---

## 📁 Estrutura de Dados Locais

Todos os dados ficam na pasta `data/` na raiz do projeto (modo dev) ou junto ao executável (modo prod).

```text
data/
  ogma.db         ← banco SQLite local (réplica sincronizada com o Turso)
  settings.json   ← preferências do usuário (tema, layout do dashboard, localização)
  .env            ← credenciais de acesso ao Turso (não versionado)
  uploads/        ← imagens e arquivos inseridos no editor
  logs/           ← logs de execução da aplicação
```
