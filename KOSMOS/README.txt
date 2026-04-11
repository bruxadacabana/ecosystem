================================================================================
  KOSMOS — Leitor, Agregador e Gerenciador de Notícias e Feeds
  Versão 0.1
================================================================================

KOSMOS é um leitor de feeds RSS local. Suporta RSS genérico, YouTube, Tumblr,
Substack, Mastodon e Reddit. Todos os dados ficam no seu computador — sem
conta, sem sincronização, sem telemetria.

================================================================================
ÍNDICE
================================================================================

  1. Pré-requisitos — CachyOS / Arch Linux
  2. Instalação — CachyOS / Arch Linux
  3. Pré-requisitos — Windows 10
  4. Instalação — Windows 10
  5. Fontes (obrigatório para a aparência correta)
  6. Configurar feeds do Reddit (opcional)
  7. Onde ficam os dados
  8. Solução de problemas

================================================================================
1. PRÉ-REQUISITOS — CachyOS / Arch Linux
================================================================================

Instale os pacotes do sistema antes de criar o ambiente virtual:

  sudo pacman -S python python-pip
  sudo pacman -S gtk3 cairo pango gdk-pixbuf2

  Python necessário: 3.11 ou superior (incluindo 3.13 e 3.14)
  Verifique com: python --version

  Nota sobre Python 3.14+:
    O código do KOSMOS é compatível com qualquer versão 3.11+. Em versões
    muito recentes (3.14+), alguns pacotes com extensões C podem não ter
    wheels pré-compiladas disponíveis e precisarão ser compilados na
    instalação — o que requer os pacotes de build do sistema:

      sudo pacman -S base-devel

    Se um pacote específico falhar (ex: argostranslate ou ctranslate2),
    o KOSMOS ainda funciona normalmente — apenas aquela funcionalidade
    ficará indisponível até o pacote ter suporte oficial à sua versão.

================================================================================
2. INSTALAÇÃO — CachyOS / Arch Linux
================================================================================

  OPÇÃO A — Script automático (recomendado):

    Abra um terminal na pasta do projeto e execute:

      chmod +x iniciar.sh
      ./iniciar.sh

    O script cria o ambiente virtual, instala as dependências e inicia o KOSMOS.
    Nas próximas vezes, basta rodar ./iniciar.sh novamente.

  ──────────────────────────────────────────────────────────────────────────

  OPÇÃO B — Manual:

    1. Criar o ambiente virtual:

         python -m venv venv

    2. Ativar o ambiente:

         source venv/bin/activate

    3. Instalar dependências:

         pip install -r requirements.txt

    4. Iniciar o KOSMOS:

         python main.py

    Para iniciar nas próximas vezes:

         source venv/bin/activate
         python main.py

================================================================================
3. PRÉ-REQUISITOS — Windows 10
================================================================================

Instale NESTA ORDEM exata. A ordem importa.

  PASSO 1 — GTK3 Runtime (obrigatório para exportação PDF):

    Baixe e execute o instalador em:
    https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer

    Marque "Add to PATH" durante a instalação.
    REINICIE o computador após instalar.

  PASSO 2 — Python 3.11 ou superior:

    Baixe em: https://www.python.org/downloads/
    Durante a instalação, marque a opção "Add Python to PATH".

    O código do KOSMOS é compatível com Python 3.11+. Em versões muito
    recentes (3.14+), alguns pacotes podem precisar ser compilados durante
    a instalação — por isso o Visual C++ Build Tools (passo 3) é essencial.

    Verifique após instalar:
      Abra o Prompt de Comando (cmd) e execute:
        python --version

  PASSO 3 — Visual C++ Build Tools:

    Necessário para compilar extensões nativas (lxml, Pillow, etc.).
    Baixe em: https://visualstudio.microsoft.com/visual-cpp-build-tools/

    Selecione "Desenvolvimento para área de trabalho com C++" e instale.

  PASSO 4 — Visual C++ Redistributable (se ainda não tiver):

    Baixe em: https://aka.ms/vs/17/release/vc_redist.x64.exe
    Necessário para o painel de leitura (QWebEngineView) funcionar.

================================================================================
4. INSTALAÇÃO — Windows 10
================================================================================

  OPÇÃO A — Script automático (recomendado):

    Clique duas vezes no arquivo iniciar.bat
    (ou execute no Prompt de Comando: iniciar.bat)

    O script cria o ambiente virtual, instala as dependências e inicia
    o KOSMOS. Nas próximas vezes, basta dar duplo clique em iniciar.bat.

  ──────────────────────────────────────────────────────────────────────────

  OPÇÃO B — Manual via Prompt de Comando:

    Abra o Prompt de Comando na pasta do projeto.

    1. Criar o ambiente virtual:

         python -m venv venv

    2. Ativar o ambiente:

         venv\Scripts\activate

    3. Instalar dependências:

         pip install -r requirements.txt

    4. Iniciar o KOSMOS:

         python main.py

    Para iniciar nas próximas vezes:

         venv\Scripts\activate
         python main.py

================================================================================
5. FONTES (obrigatório para a aparência correta)
================================================================================

O KOSMOS usa três fontes que precisam ser baixadas manualmente do Google Fonts
e colocadas na pasta  app/theme/fonts/  antes de iniciar o programa.

Se as fontes não estiverem presentes, o programa funciona normalmente mas
usa as fontes do sistema como substituto, e a aparência será diferente.

  IM Fell English (corpo do texto dos artigos):
    https://fonts.google.com/specimen/IM+Fell+English
    Arquivos necessários:
      IMFellEnglish-Regular.ttf
      IMFellEnglish-Italic.ttf

  Special Elite (títulos e cabeçalhos):
    https://fonts.google.com/specimen/Special+Elite
    Arquivo necessário:
      SpecialElite-Regular.ttf

  Courier Prime (metadados, labels, timestamps):
    https://fonts.google.com/specimen/Courier+Prime
    Arquivos necessários:
      CourierPrime-Regular.ttf
      CourierPrime-Bold.ttf
      CourierPrime-Italic.ttf

  Como baixar:
    1. Acesse cada link acima no navegador.
    2. Clique em "Download family" (botão no canto superior direito).
    3. Extraia o .zip e copie os arquivos .ttf listados acima para:
         app/theme/fonts/

  Após colocar as fontes, a pasta deve ficar assim:

    app/theme/fonts/
      IMFellEnglish-Regular.ttf
      IMFellEnglish-Italic.ttf
      SpecialElite-Regular.ttf
      CourierPrime-Regular.ttf
      CourierPrime-Bold.ttf
      CourierPrime-Italic.ttf

================================================================================
6. CONFIGURAR FEEDS DO REDDIT (opcional)
================================================================================

Para adicionar subreddits, você precisa de credenciais gratuitas da API do
Reddit (não requer conta paga — qualquer conta do Reddit serve).

  PASSO 1 — Criar um app no Reddit:

    1. Acesse https://www.reddit.com/prefs/apps (faça login se necessário).
    2. Role até o final e clique em "create another app..."
    3. Preencha:
         Nome:         KOSMOS  (pode ser qualquer nome)
         Tipo:         script   (marque esta opção)
         redirect uri: http://localhost:8080
    4. Clique em "create app".
    5. Anote:
         client_id:     o código curto abaixo do nome do app
         client_secret: o campo "secret"

  PASSO 2 — Inserir no KOSMOS:

    No KOSMOS, acesse Configurações → Reddit e insira o client_id e
    o client_secret. Clique em "Testar conexão" para verificar.

================================================================================
7. ONDE FICAM OS DADOS
================================================================================

Todos os dados gerados pelo KOSMOS ficam dentro da pasta  data/  do projeto:

  data/kosmos.db          banco de dados (feeds, artigos, tags)
  data/settings.json      configurações do usuário
  data/logs/kosmos.log    log de erros e eventos
  data/cache/             imagens e favicons em cache
  data/archive/           artigos exportados em Markdown
  data/exports/           PDFs exportados
  data/argos_models/      modelos de tradução offline

Para fazer backup do KOSMOS, basta copiar a pasta  data/.
Para reinstalar do zero, delete a pasta  data/  e  venv/.

================================================================================
8. SOLUÇÃO DE PROBLEMAS
================================================================================

  Tela branca no painel de leitura (Windows):
    → Instale o Visual C++ Redistributable (x64):
      https://aka.ms/vs/17/release/vc_redist.x64.exe
    → Certifique-se de que PyQt6 e PyQt6-WebEngine têm a mesma versão.
      Execute: pip show PyQt6 PyQt6-WebEngine

  Exportação de PDF não funciona (Windows):
    → GTK3 não está instalado ou não está no PATH.
    → Reinstale o GTK3 runtime e reinicie o computador.

  Erro "lxml não instalado" ou falha na instalação do lxml (Windows):
    → Execute: pip install lxml --only-binary=:all:

  Erro ao instalar newspaper4k (Windows):
    → Certifique-se de que o Visual C++ Build Tools está instalado
      (passo 3 da seção de pré-requisitos do Windows).

  O KOSMOS abre mas as fontes parecem erradas:
    → As fontes não foram instaladas em app/theme/fonts/
    → Siga as instruções da seção 5 deste arquivo.

  Feeds do Reddit retornam "não disponível":
    → Esta funcionalidade exige credenciais da API do Reddit.
    → Siga as instruções da seção 6 deste arquivo.

  Logs de erro:
    → O arquivo  data/logs/kosmos.log  contém o histórico completo de erros.

================================================================================
  KOSMOS v0.1 — dados armazenados localmente, sem conta, sem telemetria.
================================================================================
