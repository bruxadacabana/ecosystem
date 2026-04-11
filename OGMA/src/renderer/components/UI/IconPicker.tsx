import React, { useState, useRef, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'

// ── Catálogo de ícones ────────────────────────────────────────────────────────

const CATEGORIES: { label: string; icons: string[] }[] = [
  {
    label: 'Académico',
    icons: [
      '📚','📖','📝','📋','📄','📃','🎓','🏫','✏️','📐','📏','📌','📍',
      '🗂️','🗃️','📎','🖇️','📑','🗒️','📊','📈','📉','🗺️','🔖','📔',
      '📕','📗','📘','📙','🗓️','📆','📅','🏷️',
    ],
  },
  {
    label: 'Ciências',
    icons: [
      '🔬','🔭','⚗️','🧪','🧬','🧮','⚛️','🧲','💡','🔋','📡','🌍',
      '🌐','⚙️','🔩','🌡️','🧫','🦠','🧿','🫁','🧠','🫀','🔌','💊',
      '🩺','🩻','⚕️','🔦','🪐','🌌','☄️','🌊','🌋','🗻',
    ],
  },
  {
    label: 'Tecnologia',
    icons: [
      '💻','🖥️','🖱️','⌨️','📱','🔧','🛠️','🤖','🖨️','💾','💿','📀',
      '🖲️','🕹️','📟','📠','🔐','🔑','🗝️','🛡️','⚡','🔌','📲','🖊️',
      '💬','📶','🛰️','🔭','🕸️','⌚','🎮',
    ],
  },
  {
    label: 'Criativo',
    icons: [
      '✍️','🖊️','🖋️','🎨','🖌️','🖼️','🎭','🎬','🎵','🎶','🎤','📸',
      '🎙️','🎞️','🎲','🎯','🎪','🎠','🎡','🎢','🪄','🎸','🎹','🎺',
      '🥁','🪗','🎻','🎷','🪘','🎃','🎑','🎆','🎇',
    ],
  },
  {
    label: 'Saúde',
    icons: [
      '🌿','🍃','💊','🏋️','🧘','🍎','💪','🌱','🫀','🧠','🏃','🚴',
      '🧗','⚽','🏊','🎽','🥗','💧','🥦','🏥','🩺','🩹','🧬','🧪',
      '🥤','🍵','☕','🛌','🧖','🧘','🫧','🌬️',
    ],
  },
  {
    label: 'Pesquisa',
    icons: [
      '🔍','🔎','📰','🗞️','📜','🗺️','🌐','📡','🧐','🕵️','📂','🗄️',
      '🔐','🔑','🗝️','📋','✔️','🔗','📊','📈','🧩','💭','❓','❕',
      '💡','🔬','📐','🗃️','🗂️','🔖','📑','📌',
    ],
  },
  {
    label: 'Produtividade',
    icons: [
      '✅','☑️','🏆','🥇','🎯','⏰','📅','📆','🗓️','⌛','⏱️','🚀',
      '💼','🗳️','📩','📨','📬','📭','🔔','📢','⚡','🔥','💎','🏅',
      '🎖️','🏵️','🎗️','📊','📈','💰','💸','🪙',
    ],
  },
  {
    label: 'Natureza',
    icons: [
      '✦','☀️','🌙','⭐','🌟','💫','⚡','🌊','🔥','❄️','🌸','🌺',
      '🍀','🌳','🌲','🦋','🦉','🐉','🌈','⛅','🌤️','🌧️','❄️','🌩️',
      '🍂','🍁','🌾','🌵','🪴','🌻','🌹','🌷','🍄','🌿','🌱','🪸',
    ],
  },
  {
    label: 'Símbolos',
    icons: [
      '◉','✶','◈','◇','◎','∿','⊛','●','○','◆','▲','▼','▸','▾',
      '◐','◑','◒','◓','⬟','⬡','❖','✦','✧','⚜','♾️','⚡','♦','♠',
      '♣','♥','☯️','☮️','✡️','⚕️','⚖️','🔱','⚜','🌀','🔰','♻️',
    ],
  },
  {
    label: 'Pessoas',
    icons: [
      '👤','👥','🧑','👩','👨','🧑‍💻','👩‍🎓','👨‍🎓','👩‍🏫','👨‍🏫','👩‍🔬','👨‍🔬',
      '👩‍⚕️','👨‍⚕️','🧑‍🎨','🧑‍🍳','🧑‍🌾','👷','🕵️','🧙','🤝','👋','🫶','❤️',
    ],
  },
  {
    label: 'Lugares',
    icons: [
      '🏠','🏡','🏢','🏣','🏤','🏥','🏦','🏨','🏩','🏫','🏛️','⛪',
      '🕌','🗼','🗽','⛩️','🏰','🏯','🌁','🌃','🌆','🌇','🌉','🏔️',
      '⛰️','🗻','🏕️','🏖️','🏝️','🌋','🗺️','🧭',
    ],
  },
  {
    label: 'Objetos',
    icons: [
      '💡','🔦','🕯️','🪔','🔑','🗝️','🔓','🔒','🧰','🪛','🔨','⚒️',
      '🛠️','⛏️','🪚','🔧','🔩','🗜️','⚙️','🪤','🧲','🔭','🔬','🩺',
      '💉','🧲','🎁','📦','🪣','🧴','🪞','🚪','🪟','🛏️','🪑',
    ],
  },
]

// ── Mapeamento palavra-chave → ícones ─────────────────────────────────────────

function normalize(s: string): string {
  return s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim()
}

const KEYWORD_MAP: [string[], string[]][] = [
  // Matemática
  [['matematica','calculo','algebra','geometria','trigonometria','estatistica','numero','equacao','funcao'],
   ['📐','📏','🔢','📊','📈','📉','🧮','∑','π','∫','∞']],
  // Física
  [['fisica','mecanica','termodinamica','optica','eletromagnetismo','quantica','relatividade'],
   ['⚛️','⚡','🔭','🧲','🌡️','💡','🔬','🌊','🔌','⚙️','🔩']],
  // Química
  [['quimica','organica','inorganica','bioquimica','laboratorio','reacao','molecula','atomo'],
   ['⚗️','🧪','🧬','🔬','🧫','💊','🧲','⚛️','🌡️']],
  // Biologia
  [['biologia','genetica','ecologia','botanica','zoologia','anatomia','microbiologia','evolucao','celula'],
   ['🧬','🔬','🌿','🦠','🫀','🧠','🫁','🧪','🌱','🦋','🐉','🌲']],
  // História
  [['historia','historico','guerra','revolucao','imperio','antiguidade','medieval','moderno'],
   ['📜','🏛️','⚔️','🗺️','🏰','🗡️','👑','🎭','📖','🕰️']],
  // Geografia
  [['geografia','cartografia','mapa','territorio','clima','relevo','hidrografia','pais','continente'],
   ['🗺️','🌍','🌐','🧭','⛰️','🌋','🌊','🏔️','🌏','🌎']],
  // Filosofia
  [['filosofia','etica','logica','metafisica','epistemologia','politica','ontologia'],
   ['🤔','💭','📜','🏛️','🧿','☯️','⚖️','🔮','💡','🧠']],
  // Literatura / Letras / Língua
  [['literatura','letras','lingua','linguistica','portugues','ingles','espanhol','redacao','texto','poesia'],
   ['📖','📚','✍️','🖊️','🖋️','📝','📜','🎭','💬','🗣️']],
  // Sociologia / Ciências Sociais
  [['sociologia','antropologia','ciencias sociais','politica','sociedade','cultura'],
   ['👥','🤝','🌍','📊','🏛️','🗳️','📢','❤️','🫶']],
  // Psicologia
  [['psicologia','comportamento','terapia','cognitiva','emocao','mente','consciencia'],
   ['🧠','💭','❤️','🧘','😊','🫀','🪞','💊','📊']],
  // Economia / Administração / Negócios
  [['economia','administracao','negocios','financas','contabilidade','marketing','gestao'],
   ['💰','📊','📈','💼','🏦','💸','🪙','🤝','📋','🎯']],
  // Direito
  [['direito','lei','juridico','constitucional','penal','civil','processo'],
   ['⚖️','📜','🏛️','🔐','🗝️','📋','👨‍⚖️','🔒','🎓']],
  // Medicina / Saúde
  [['medicina','saude','enfermagem','anatomia','fisiologia','patologia','farmacia','hospital'],
   ['🩺','💊','🏥','🩻','🧬','🫀','🧠','⚕️','💉','🩹']],
  // Engenharia
  [['engenharia','civil','mecanica','eletrica','quimica','software','arquitetura','estrutura'],
   ['🛠️','⚙️','🔩','🔧','🏗️','📐','💡','🔌','🖥️','🏛️']],
  // Computação / TI
  [['computacao','programacao','desenvolvimento','software','algoritmo','dados','redes','seguranca','web'],
   ['💻','🖥️','⌨️','🤖','🔧','🛠️','🔐','🕸️','📡','🎮','⚡']],
  // Astronomia
  [['astronomia','astrofisica','cosmo','espaco','universo','planeta','estrela','galaxia'],
   ['🔭','🪐','⭐','🌟','💫','☀️','🌙','☄️','🌌','🛸']],
  // Arte / Design
  [['arte','design','desenho','pintura','escultura','fotografia','cinema','animacao'],
   ['🎨','🖌️','🖼️','📸','🎭','🎬','✍️','🖊️','🖋️','🎞️']],
  // Música
  [['musica','teoria musical','harmonia','composicao','instrumento','canto','audio'],
   ['🎵','🎶','🎸','🎹','🎤','🎙️','🥁','🎺','🎻','🎷','🎼']],
  // Educação Física / Esportes
  [['educacao fisica','esporte','futebol','basquete','natacao','atletismo','ginastica','treino'],
   ['🏋️','🏃','⚽','🏊','🏀','⚡','🎽','🥇','🏆','💪']],
  // Nutrição / Alimentação
  [['nutricao','alimentacao','dieta','comida','cozinha','gastronomia'],
   ['🥗','🍎','🥦','💧','🫐','🍵','🥤','🧬','🌿','🍽️']],
  // Projeto / Trabalho Genérico
  [['projeto','trabalho','tarefa','atividade','estudo','pesquisa','relatorio','apresentacao','tcc','monografia','dissertacao','tese'],
   ['📋','🎯','📊','📝','🔍','💼','📌','🗂️','📑','🏆']],
  // Leitura
  [['leitura','livro','artigo','revisao','fichamento','resumo','resenha'],
   ['📚','📖','📕','📗','📘','📙','🔖','✍️','📝','💡']],
  // Anotações / Notas
  [['anotacao','nota','diario','journal','bullet','caderno','agenda'],
   ['📓','📒','📔','📝','✏️','🖊️','🗒️','📅','🗓️','🔖']],
  // Idiomas / Línguas estrangeiras
  [['idioma','frances','alemao','japones','chines','russo','italiano','arabe'],
   ['🗣️','💬','🌐','📖','✍️','🎧','🗺️','🏳️']],
  // Finanças pessoais
  [['financas','orcamento','investimento','poupanca','renda','despesa','planilha'],
   ['💰','📊','💸','🪙','💳','🏦','📈','📉','💼']],
  // Gestão de tempo
  [['tempo','agenda','horario','cronograma','prazo','deadline','planejamento','calendario'],
   ['⏰','📅','🗓️','⌛','⏱️','🎯','📋','✅','🔔']],
  // Módulos / Unidades / Aulas
  [['modulo','unidade','aula','tema','capitulo','topico','licao','sessao'],
   ['📚','📖','📝','🗂️','📋','📌','🔖','📓','📒','📔','🗒️','✏️']],
  // Fundamentos / Introdução / Bases
  [['fundamentos','introducao','bases','principios','nocoes','conceitos','teoria'],
   ['📖','🏛️','💡','🔭','📐','🧩','⚙️','📜','🌱','🌟']],
  // Seminário / Apresentação / Trabalho acadêmico
  [['seminario','apresentacao','palestra','conferencia','simpósio','workshop'],
   ['🎤','🎙️','🎭','🗣️','📊','📋','🏆','🎓','👥']],
  // Exercício / Prática / Lista
  [['exercicio','pratica','lista','atividade','tarefa','problema','questao'],
   ['✏️','📝','🔧','💪','🎯','✅','📋','🗒️','⚡']],
  // Resumo / Revisão / Fichamento
  [['resumo','revisao','sintese','fichamento','esquema','mapa','mapa mental'],
   ['🗺️','📊','🧩','📝','✍️','🔍','📌','📑','💡']],
  // Prova / Avaliação / Exame
  [['prova','avaliacao','exame','teste','quiz','simulado','gabarito'],
   ['📋','✏️','🎓','⏰','🏆','❓','📊','🎯']],
]

function suggestFromText(text: string): string[] {
  if (!text.trim()) return []
  const norm = normalize(text)
  const found = new Map<string, number>() // icon → score
  for (const [keywords, icons] of KEYWORD_MAP) {
    for (const kw of keywords) {
      if (norm.includes(kw) || kw.includes(norm)) {
        const score = norm === kw ? 3 : norm.includes(kw) ? 2 : 1
        icons.forEach(ic => found.set(ic, Math.max(found.get(ic) ?? 0, score)))
      }
    }
  }
  return [...found.entries()].sort((a, b) => b[1] - a[1]).map(([ic]) => ic).slice(0, 16)
}

// ── Componente ────────────────────────────────────────────────────────────────

interface Props {
  value:       string
  onChange:    (icon: string) => void
  dark:        boolean
  size?:       number   // fontSize do botão trigger (default 24)
  suggestFor?: string   // nome do projecto/página para sugestões automáticas
}

export function IconPicker({ value, onChange, dark, size = 24, suggestFor }: Props) {
  const [open,     setOpen]     = useState(false)
  const [search,   setSearch]   = useState('')
  const [catIdx,   setCatIdx]   = useState(0)
  const [panelPos, setPanelPos] = useState({ top: 0, left: 0 })
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef   = useRef<HTMLDivElement>(null)
  const tabsRef    = useRef<HTMLDivElement>(null)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const bg     = dark ? '#211D16' : '#F5F0E8'
  const cardBg = dark ? '#1A1710' : '#EDE7D9'
  const accent = dark ? '#D4A820' : '#b8860b'

  const PANEL_W = 320
  const PANEL_H = 400

  const scrollTabs = (dir: number) => {
    tabsRef.current?.scrollBy({ left: dir * 120, behavior: 'smooth' })
  }

  const prevCat = (e: React.MouseEvent) => {
    e.stopPropagation()
    setCatIdx(i => (i - 1 + CATEGORIES.length) % CATEGORIES.length)
  }
  const nextCat = (e: React.MouseEvent) => {
    e.stopPropagation()
    setCatIdx(i => (i + 1) % CATEGORIES.length)
  }

  const openPanel = useCallback(() => {
    if (!triggerRef.current) return
    const rect = triggerRef.current.getBoundingClientRect()
    const vw   = window.innerWidth
    const vh   = window.innerHeight
    const top  = rect.bottom + 6 + PANEL_H > vh ? rect.top - PANEL_H - 4 : rect.bottom + 6
    const left = rect.left + PANEL_W > vw ? rect.right - PANEL_W : rect.left
    setPanelPos({ top, left })
    setOpen(true)
  }, [])

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      const t = e.target as Node
      if (
        panelRef.current && !panelRef.current.contains(t) &&
        triggerRef.current && !triggerRef.current.contains(t)
      ) { setOpen(false); setSearch('') }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  useEffect(() => {
    if (!open) return
    const close = () => { setOpen(false); setSearch('') }
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => { window.removeEventListener('scroll', close, true); window.removeEventListener('resize', close) }
  }, [open])

  // Scroll active tab into view when category changes
  useEffect(() => {
    if (!tabsRef.current) return
    const btn = tabsRef.current.children[catIdx] as HTMLElement | undefined
    btn?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
  }, [catIdx])

  const handleSelect = (icon: string) => { onChange(icon); setOpen(false); setSearch('') }

  // Ícones a mostrar
  const suggestions  = suggestFor ? suggestFromText(suggestFor) : []
  const searchResult = search.trim()
    ? (() => {
        const norm     = normalize(search)
        // 1) match directo por emoji
        const byEmoji  = CATEGORIES.flatMap(c => c.icons).filter(ic => ic.startsWith(search) || ic === search)
        // 2) match por keyword
        const byKw     = suggestFromText(search)
        // união, emoji directo primeiro
        return [...new Set([...byEmoji, ...byKw])]
      })()
    : null

  const panel = open && createPortal(
    <div
      ref={panelRef}
      style={{
        position: 'fixed', top: panelPos.top, left: panelPos.left, zIndex: 9999,
        background: bg, border: `1px solid ${border}`, borderRadius: 4,
        boxShadow: `4px 4px 0 ${border}`,
        width: PANEL_W, maxHeight: PANEL_H,
        display: 'flex', flexDirection: 'column',
      }}
    >
      {/* Busca */}
      <div style={{ padding: '8px 10px 6px', borderBottom: `1px solid ${border}`, flexShrink: 0 }}>
        <input
          autoFocus
          type="text"
          placeholder="Buscar por nome (ex: biologia, música…)"
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && search.trim()) {
              const res = searchResult
              if (res && res.length > 0) handleSelect(res[0])
              else handleSelect(search.trim())
            }
            if (e.key === 'Escape') { setOpen(false); setSearch('') }
          }}
          style={{
            width: '100%', background: cardBg, border: `1px solid ${border}`,
            borderRadius: 2, padding: '4px 8px', fontSize: 12,
            color: ink, outline: 'none', fontFamily: 'var(--font-mono)',
            boxSizing: 'border-box',
          }}
        />
      </div>

      {/* Sugestões baseadas no nome do projecto/página */}
      {!search && suggestions.length > 0 && (
        <div style={{ padding: '6px 8px 4px', borderBottom: `1px solid ${border}`, flexShrink: 0 }}>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 8, letterSpacing: '0.12em',
            color: accent, marginBottom: 4,
          }}>
            SUGESTÕES
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
            {suggestions.map(icon => (
              <button key={icon} onClick={() => handleSelect(icon)} title={icon} style={{
                fontSize: 20, lineHeight: 1, padding: '4px 3px', border: 'none', borderRadius: 3,
                cursor: 'pointer', background: icon === value ? accent + '30' : accent + '10',
                transition: 'background 80ms',
              }}
                onMouseEnter={e => (e.currentTarget.style.background = ink + '15')}
                onMouseLeave={e => (e.currentTarget.style.background = icon === value ? accent + '30' : accent + '10')}
              >{icon}</button>
            ))}
          </div>
        </div>
      )}

      {/* Tabs de categoria (só quando sem busca) */}
      {!search && (
        <div style={{
          display: 'flex', alignItems: 'stretch',
          borderBottom: `1px solid ${border}`, flexShrink: 0,
        }}>
          {/* Botão anterior */}
          <button
            onMouseDown={e => e.preventDefault()}
            onClick={prevCat}
            style={{
              flexShrink: 0, width: 22, border: 'none',
              borderRight: `1px solid ${border}`,
              background: 'transparent', cursor: 'pointer',
              color: ink2, fontSize: 10, padding: 0,
            }}
            title="Categoria anterior"
          >◀</button>

          {/* Lista de tabs com scroll */}
          <div
            ref={tabsRef}
            style={{
              flex: 1, display: 'flex', gap: 2, padding: '4px 6px 0',
              overflowX: 'auto', scrollbarWidth: 'none',
            }}
          >
            {CATEGORIES.map((cat, i) => (
              <button key={cat.label} onClick={() => setCatIdx(i)} style={{
                fontFamily: 'var(--font-mono)', fontSize: 8, letterSpacing: '0.06em',
                padding: '3px 7px', border: 'none', borderRadius: '2px 2px 0 0',
                cursor: 'pointer', flexShrink: 0, whiteSpace: 'nowrap',
                background: catIdx === i ? cardBg : 'transparent',
                color: catIdx === i ? accent : ink2,
                borderBottom: catIdx === i ? `2px solid ${accent}` : '2px solid transparent',
              }}>
                {cat.label}
              </button>
            ))}
          </div>

          {/* Botão próximo */}
          <button
            onMouseDown={e => e.preventDefault()}
            onClick={nextCat}
            style={{
              flexShrink: 0, width: 22, border: 'none',
              borderLeft: `1px solid ${border}`,
              background: 'transparent', cursor: 'pointer',
              color: ink2, fontSize: 10, padding: 0,
            }}
            title="Próxima categoria"
          >▶</button>
        </div>
      )}

      {/* Grade de ícones */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '8px',
        display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)',
        gap: 2, alignContent: 'start',
      }}>
        {(searchResult ?? CATEGORIES[catIdx].icons).map(icon => (
          <button
            key={icon}
            onClick={() => handleSelect(icon)}
            title={icon}
            style={{
              fontSize: 20, lineHeight: 1,
              padding: '5px 3px', border: 'none', borderRadius: 3,
              cursor: 'pointer', background: icon === value ? accent + '30' : 'transparent',
              transition: 'background 80ms',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = ink + '15')}
            onMouseLeave={e => (e.currentTarget.style.background = icon === value ? accent + '30' : 'transparent')}
          >
            {icon}
          </button>
        ))}
        {searchResult && searchResult.length === 0 && (
          <span style={{
            gridColumn: '1 / -1', fontFamily: 'var(--font-mono)', fontSize: 10,
            color: ink2, fontStyle: 'italic', padding: '8px 0',
          }}>
            Nenhum resultado. Pressione Enter para usar "{search}" directamente.
          </span>
        )}
      </div>
    </div>,
    document.body
  )

  return (
    <div style={{ display: 'inline-flex' }}>
      <button
        ref={triggerRef}
        style={{
          fontSize: size, lineHeight: 1, cursor: 'pointer',
          background: 'none', border: 'none', padding: 0,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}
        onClick={() => open ? (setOpen(false), setSearch('')) : openPanel()}
        title="Escolher ícone"
        type="button"
      >
        {value || '◦'}
      </button>
      {panel}
    </div>
  )
}
