from pathlib import Path
import re

SRC = Path(r"d:\windows\ProgramFiles\ecosystem\pesquisas.md")
lines = SRC.read_text(encoding="utf-8").splitlines()

def block(lo, hi):
    return lines[lo-1:hi]

def find_content_start(blk, is_hub=False):
    if is_hub:
        for i, ln in enumerate(blk):
            if re.match(r'^## \d+\.', ln):
                return i
        return 0
    last_eq = -1
    for i, ln in enumerate(blk[:12]):
        if re.match(r'^={5,}\s*$', ln):
            last_eq = i
    start = last_eq + 1 if last_eq >= 0 else 0
    extra_skip = ('# Pesquisa', 'DEEPSEEK:', 'Referencia: app', 'Hardware da usuaria',
                  'Tema: ', 'PESQUISA PARA', '4. NOTEBOOKLM', '5. DEEP RESEARCH',
                  '6. INTEGRACAO MNEMOSYNE', 'Fontes consultadas:', 'Hardware de trabalho')
    while start < len(blk):
        s = blk[start].strip()
        if s == '' or re.match(r'^[-=]{3,}\s*$', s):
            start += 1
            continue
        # Check extra skip using lowercase comparison for accented chars
        sl = s.lower()
        if any(p.lower() in sl[:30] for p in ('# pesquisa', 'deepseek:', 'tema: ',
               'pesquisa para', '4. notebooklm', '5. deep research',
               '6. integra', 'fontes consultadas:', 'hardware de trabalho',
               'referencia: app', 'hardware da')):
            start += 1
            continue
        break
    return start

_FONTES_RE = re.compile(
    r'^(?:\d+\.\s+)?(?:fontes?(?:\s+adicionais)?(?:\s*[:\-—].*)?|'
    r'referencias?:?)\s*$',
    re.IGNORECASE
)

def _is_fontes(s):
    return bool(_FONTES_RE.match(s.strip()))

def transform(blk, is_hub=False, is_mnemo_markdown=False):
    out = []
    i = 0
    while i < len(blk):
        ln = blk[i]
        stripped = ln.strip()

        # FONTES check (must come before generic title handlers)
        if _is_fontes(stripped):
            out.append('### Fontes')
            if i+1 < len(blk) and re.match(r'^[-=]{2,}\s*$', blk[i+1]):
                i += 2
            else:
                i += 1
            continue

        # === lines: FIM, sandwich, orphan
        if re.match(r'^={5,}\s*$', ln):
            nxt = blk[i+1].strip() if i+1 < len(blk) else ''
            if nxt.upper().startswith('FIM DA') or nxt.upper().startswith('FIM '):
                i += 1
                while i < len(blk) and (blk[i].strip().upper().startswith('FIM')
                                         or re.match(r'^={5,}\s*$', blk[i])):
                    i += 1
                continue
            # Sandwich: ===\nTITLE\n===
            if i+2 < len(blk) and re.match(r'^={5,}\s*$', blk[i+2]):
                title = blk[i+1].strip()
                if title and not title.startswith('='):
                    heading = 'Fontes' if _is_fontes(title) else title
                    out.append('### ' + heading)
                    i += 3
                    while i < len(blk) and blk[i].strip() == '':
                        i += 1
                    continue
            i += 1
            continue

        # TITLE\n====== (title before equals underline)
        if (i+1 < len(blk) and re.match(r'^={4,}\s*$', blk[i+1])
                and stripped and not re.match(r'^[=#]', ln)):
            heading = 'Fontes' if _is_fontes(stripped) else stripped
            out.append('### ' + heading)
            i += 2
            continue

        # TITLE\n------ (title before dashes, 4+ dashes)
        if (i+1 < len(blk) and re.match(r'^-{4,}\s*$', blk[i+1])
                and stripped and not ln.startswith('-') and not ln.startswith('#')):
            heading = 'Fontes' if _is_fontes(stripped) else stripped
            out.append('### ' + heading)
            i += 2
            continue

        # HUB: ## N. -> ### N.
        if is_hub and re.match(r'^## ', ln):
            out.append('### ' + ln[3:])
            i += 1
            continue

        # Mnemosyne markdown sessions: ## -> ###
        if is_mnemo_markdown and re.match(r'^## ', ln):
            out.append('### ' + ln[3:])
            i += 1
            continue

        out.append(ln)
        i += 1
    return out

SESSIONS = [
    ("2026-03-31","Personal Context Management para LLMs",["Mnemosyne"],1929,2250,False,True),
    ("2026-04-09","Personal Context Management — Conceitos e Protocolos",["Mnemosyne"],2251,2303,False,False),
    ("2026-04-10","Modelos LLM para RAG Local — RX 6600 e ROCm",["Mnemosyne"],2304,2645,False,False),
    ("2026-04-10","NotebookLM — Funcionalidades e Estrutura",["Mnemosyne"],2646,2790,False,False),
    ("2026-04-10","LLMs Ideais para RAG Local — Benchmarks e Configuracao",["Mnemosyne"],2791,2933,False,False),
    ("2026-04-10","Wikilinks do Obsidian — Regex de Extracao",["Mnemosyne"],2935,2960,False,False),
    ("2026-04-10","NotebookLM Local — Infraestrutura RAG e Templates de Prompt",["Mnemosyne"],2962,3267,False,False),
    ("2026-04-17","Performance de Indexacao em Hardware Limitado",["Mnemosyne","HUB"],3268,3523,False,False),
    ("2026-04-17","Modelos de Embedding Leves e Ollama CPU Tuning",["Mnemosyne","HUB"],3525,3736,False,False),
    ("2026-04-20","NotebookLM — Funcionalidades Avancadas (Studio Panel)",["Mnemosyne"],3737,3852,False,False),
    ("2026-04-21","Deep Research Agents — Estado da Arte e Replicacao Offline",["Mnemosyne"],3855,4066,False,False),
    ("2026-04-21","Integracao Mnemosyne + AKASHA — Modo de Pesquisa Profunda",["Mnemosyne","AKASHA"],4068,4405,False,False),
    ("2026-04-23","Otimizacao de RAG — Chunking, Reranking e Avaliacao",["Mnemosyne"],4407,4671,False,False),
    ("2026-04-24","Arquitetura de Buscadores — Indexacao, FTS e Otimizacao de Queries",["AKASHA"],819,1170,False,False),
    ("2026-04-24","Artigos Cientificos — Busca, Download e Extracao de PDFs",["AKASHA","Mnemosyne"],1171,1298,False,False),
    ("2026-04-24","Medium e Substack — Scraping e Extracao de Conteudo",["AKASHA","KOSMOS"],1299,1382,False,False),
    ("2026-04-24","Medium e Substack — Extracao no Leitor de Feeds",["KOSMOS"],1877,1927,False,False),
    ("2026-04-25","Torrents — Prowlarr, Jackett e qBittorrent",["AKASHA"],1383,1590,False,False),
    ("2026-04-25","Pipeline LLM Local para Analise de Artigos no KOSMOS",["KOSMOS"],1592,1876,False,False),
    ("2026-04-26","Otimizacao e Gerenciamento de Recursos do Ecossistema",["HUB","LOGOS","Mnemosyne","KOSMOS","Hermes"],7,817,True,False),
]

# Use proper UTF-8 titles
TITLES_UTF8 = [
    "Personal Context Management para LLMs",
    "Personal Context Management — Conceitos e Protocolos",
    "Modelos LLM para RAG Local — RX 6600 e ROCm",
    "NotebookLM — Funcionalidades e Estrutura",
    "LLMs Ideais para RAG Local — Benchmarks e Configuração",
    "Wikilinks do Obsidian — Regex de Extração",
    "NotebookLM Local — Infraestrutura RAG e Templates de Prompt",
    "Performance de Indexação em Hardware Limitado",
    "Modelos de Embedding Leves e Ollama CPU Tuning",
    "NotebookLM — Funcionalidades Avançadas (Studio Panel)",
    "Deep Research Agents — Estado da Arte e Replicação Offline",
    "Integração Mnemosyne + AKASHA — Modo de Pesquisa Profunda",
    "Otimização de RAG — Chunking, Reranking e Avaliação",
    "Arquitetura de Buscadores — Indexação, FTS e Otimização de Queries",
    "Artigos Científicos — Busca, Download e Extração de PDFs",
    "Medium e Substack — Scraping e Extração de Conteúdo",
    "Medium e Substack — Extração no Leitor de Feeds",
    "Torrents — Prowlarr, Jackett e qBittorrent",
    "Pipeline LLM Local para Análise de Artigos no KOSMOS",
    "Otimização e Gerenciamento de Recursos do Ecossistema",
]

parts = [
    "# Pesquisas do Ecossistema\n\n",
    "> Última atualização: 2026-04-27  \n",
    "> Ordem: cronológica crescente — novas pesquisas sempre ao final.\n\n",
    "---\n",
]

for idx, (date, _title_ascii, progs, lo, hi, is_hub, is_mnemo_mk) in enumerate(SESSIONS):
    title = TITLES_UTF8[idx]
    blk = block(lo, hi)
    cs = find_content_start(blk, is_hub)
    content_blk = blk[cs:]
    processed = transform(content_blk, is_hub, is_mnemo_mk)
    cleaned = re.sub(r'\n{3,}', '\n\n', '\n'.join(processed))
    prog_str = ', '.join(progs)
    header = f"\n## {title}\n> Programas: {prog_str} | Data: {date}\n"
    parts.append(header + '\n' + cleaned.strip() + '\n\n---\n')

result = ''.join(parts)
OUT = Path(r"d:\windows\ProgramFiles\ecosystem\pesquisas_new.md")
OUT.write_text(result, encoding="utf-8")
new_lines = result.splitlines()
print(f"Written {len(new_lines)} lines")

# Spot checks
print("\nSession 1 first 10 lines:")
for ln in new_lines[7:17]:
    print(f"  {repr(ln[:70])}")

print("\n### Fontes occurrences:")
for i, ln in enumerate(new_lines):
    if '### Fontes' in ln or '### FONTES' in ln:
        print(f"  L{i+1}: {repr(ln)}")

print("\nLeftover old-style headers:")
for i, ln in enumerate(new_lines):
    if re.match(r'^(## (HUB|AKASHA|KOSMOS|Mnemosyne)\b|# Pesquisa:)', ln):
        print(f"  L{i+1}: {repr(ln[:60])}")

print(f"\n## headings: {sum(1 for ln in new_lines if ln.startswith('## '))}")
print(f"### headings: {sum(1 for ln in new_lines if ln.startswith('### '))}")
