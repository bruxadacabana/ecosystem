# Vendor — SearXNG (versão congelada)

SearXNG empacotado no repositório para servir como **3ª alternativa de busca web** do
AKASHA (ver TODO "SearXNG vendorizado (Windows, sem Docker)"). Roda **nativo em Python,
sem Docker**, inclusive no Windows 10.

## Versão congelada

- **Fonte:** https://github.com/searxng/searxng
- **Commit:** `502c820a25bfd9e7a7175671c9d7dc96cf8afbdf`
- **Data do commit:** 2026-06-16
- **Versão SearXNG:** `2026.6.16+502c820` (ver `searx/version_frozen.py`)
- **Vendorizado em:** 2026-06-16
- **Licença:** AGPL-3.0-or-later (ver `searxng/LICENSE`) — uso pessoal/local.

Atualizar = trocar deliberadamente por uma versão nova (re-vendorizar). Congelar protege
contra quebra de código por update; em troca, os engines (Google/Bing) degradam com o
tempo e o conserto vem de um update deliberado.

## Modificações aplicadas ao vendorizar

1. **Arquivos `:socket` removidos** — `utils/templates/etc/.../*.conf:socket` e
   `*.ini:socket` (4 arquivos) têm `:` no nome, proibido no Windows/NTFS; impediam o
   checkout do repo no Windows. São templates de deploy (nginx/uwsgi/httpd), inúteis para
   rodar. (Na prática nem existiam em disco — o checkout do clone já falhava neles.)
2. **`searx/version_frozen.py` adicionado** — congela a versão sem depender de `.git`
   (gerado por `python -m searx.version freeze`). Sem ele, `searx/version.py` loga erro e
   cai para "1.0.0".
3. **`_winshim/pwd.py`** — stub do módulo POSIX-only `pwd`, plantado no PYTHONPATH apenas
   no Windows (pelo HUB/setup) para satisfazer o `import pwd` em `searx/valkeydb.py`.
4. **`settings.base.yml`** — template de configuração (limiter off, formato json, porta
   8889, engines curados). O setup gera o `settings.yml` real substituindo `__SECRET_KEY__`.
5. **`.gitignore` ajustado** — passou a versionar `searx/version_frozen.py` e a ignorar o
   `/.venv/` e o `settings.yml` gerado.

## Como rodar (resumo — detalhes no setup do HUB)

```
# 1. venv + deps (Python 3.13)
uv venv --python 3.13 .venv
uv pip install --python .venv/<bin>/python -r requirements.txt

# 2. gerar settings.yml a partir do template (substituindo __SECRET_KEY__)

# 3. rodar (no Windows, PYTHONPATH inclui o stub pwd)
SEARXNG_SETTINGS_PATH=.../settings.yml  PYTHONPATH=.../_winshim  python -m searx.webapp
```
