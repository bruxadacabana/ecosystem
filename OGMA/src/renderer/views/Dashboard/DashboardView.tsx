import React, { useEffect, useRef, useState } from 'react'
import { CosmosLayer } from '../../components/Cosmos/CosmosLayer'
import { useAppStore } from '../../store/useAppStore'
import { PROJECT_TYPE_ICONS, AppSettings, StoredLocation, Project } from '../../types'
import { fromIpc } from '../../types/errors'

const db = () => (window as any).db

// ── Tipos ─────────────────────────────────────────────────────────────────────

export type WidgetSize = 'sm' | 'md' | 'lg'
type WidgetId =
  | 'stats' | 'projects' | 'recent' | 'prazos' | 'cosmos' | 'wheel' | 'weather' | 'planner'
  | 'agenda' | 'reminders' | 'provas' | 'proj_progress' | 'quote' | 'ideas'
  | 'reading_goal' | 'heatmap' | 'pomodoro'

const DEFAULT_ORDER: WidgetId[] = [
  'stats', 'projects', 'recent', 'prazos', 'cosmos', 'wheel', 'weather', 'planner',
  'agenda', 'reminders', 'provas', 'proj_progress', 'quote', 'ideas',
  'reading_goal', 'heatmap', 'pomodoro',
]

const WIDGET_LABELS: Record<WidgetId, string> = {
  stats:        'Estatísticas',
  projects:     'Projetos',
  recent:       'Páginas Recentes',
  prazos:       'Próximas Páginas',
  cosmos:       'Cosmos',
  wheel:        'Roda do Ano',
  weather:      'Previsão do Tempo',
  planner:      'Plano do Dia',
  agenda:       'Agenda da Semana',
  reminders:    'Lembretes Pendentes',
  provas:       'Próximas Provas',
  proj_progress:'Progresso dos Projetos',
  quote:        'Citação Aleatória',
  ideas:        'Ideias Futuras',
  reading_goal: 'Meta de Leitura',
  heatmap:      'Mapa de Atividade',
  pomodoro:     'Pomodoro',
}
const DEFAULT_SIZES: Record<WidgetId, WidgetSize> = {
  stats: 'md', projects: 'md', recent: 'md', prazos: 'md',
  cosmos: 'md', wheel: 'md', weather: 'md', planner: 'md',
  agenda: 'lg', reminders: 'md', provas: 'md', proj_progress: 'md', quote: 'md',
  ideas: 'md', reading_goal: 'md', heatmap: 'lg', pomodoro: 'md',
}

interface Props {
  dark:            boolean
  isActive:        boolean
  onProjectOpen:   (id: number) => void
  onPageOpen:      (projectId: number, pageId: number) => void
  initialSettings: AppSettings
}

// ── Helpers de tempo ─────────────────────────────────────────────────────────

function formatTime(): string {
  return new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatDateLong(): string {
  const now   = new Date()
  const dias  = ['Domingo','Segunda-feira','Terça-feira','Quarta-feira','Quinta-feira','Sexta-feira','Sábado']
  const meses = ['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro']
  return `${dias[now.getDay()]}, ${now.getDate()} de ${meses[now.getMonth()]} de ${now.getFullYear()}`
}

function timeAgo(iso: string): string {
  try {
    const ms  = Date.now() - new Date(iso).getTime()
    const min = Math.floor(ms / 60000)
    const h   = Math.floor(min / 60)
    const d   = Math.floor(h / 24)
    if (d > 0)   return `há ${d}d`
    if (h > 0)   return `há ${h}h`
    if (min > 0) return `há ${min}min`
    return 'agora'
  } catch { return '' }
}

function formatUpcomingDate(iso: string): string {
  try {
    const d    = new Date(iso + 'T00:00:00')
    const now  = new Date(); now.setHours(0, 0, 0, 0)
    const diff = Math.round((d.getTime() - now.getTime()) / 86400000)
    if (diff === 0) return 'hoje'
    if (diff === 1) return 'amanhã'
    if (diff <= 6)  return `em ${diff} dias`
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })
  } catch { return iso }
}

// ── Astronomia — Lua ──────────────────────────────────────────────────────────

const KNOWN_NEW = new Date('2000-01-06T18:14:00Z').getTime()
const CYCLE_MS  = 29.530588853 * 86400000
const MESES_ABR = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez']

function getMoonPhase() {
  const phase  = ((Date.now() - KNOWN_NEW) % CYCLE_MS) / CYCLE_MS
  const idx    = Math.floor(phase * 8) % 8
  const emojis = ['🌑','🌒','🌓','🌔','🌕','🌖','🌗','🌘']
  const names  = ['Lua Nova','Crescente','Quarto Crescente','Gibosa Crescente',
                  'Lua Cheia','Gibosa Minguante','Quarto Minguante','Minguante']
  return { emoji: emojis[idx], name: names[idx], pct: Math.round(phase * 100), raw: phase }
}

function getNextFullMoon() {
  const phase  = ((Date.now() - KNOWN_NEW) % CYCLE_MS) / CYCLE_MS
  const daysTo = phase < 0.5
    ? (0.5 - phase) * 29.530588853
    : (1.5 - phase) * 29.530588853
  const d = new Date(Date.now() + daysTo * 86400000)
  return { days: Math.round(daysTo), dateStr: `${d.getDate()} ${MESES_ABR[d.getMonth()]}` }
}

function getNextQuarter() {
  const phase    = ((Date.now() - KNOWN_NEW) % CYCLE_MS) / CYCLE_MS
  const quarters = [
    { pct: 0.25, name: 'Quarto Crescente' },
    { pct: 0.50, name: 'Lua Cheia'        },
    { pct: 0.75, name: 'Quarto Minguante' },
    { pct: 1.00, name: 'Lua Nova'         },
  ]
  const next   = quarters.find(q => q.pct > phase) ?? quarters[0]
  const daysTo = (next.pct - phase) * 29.530588853
  return { name: next.name, days: Math.ceil(daysTo) }
}

// ── Astronomia — Roda do Ano ──────────────────────────────────────────────────

interface ComputedSabbat {
  name:    string
  symbol:  string
  date:    Date
  day:     number   // dia do ano (1-365)
  dateStr: string   // "21 dez"
  season:  string   // "Solstício de Inverno"
}

/** Solstícios e equinócios via algoritmo de Meeus (precisão ~1 dia) */
function computeEquinoxSolstice(year: number, event: 0|1|2|3): Date {
  const Y   = (year - 2000) / 1000
  const JDE = [
    2451623.80984 + 365242.37404*Y + 0.05169*Y*Y - 0.00411*Y*Y*Y - 0.00057*Y*Y*Y*Y,
    2451716.56767 + 365241.62603*Y + 0.00325*Y*Y + 0.00888*Y*Y*Y - 0.00030*Y*Y*Y*Y,
    2451810.21715 + 365242.01767*Y - 0.11575*Y*Y + 0.00337*Y*Y*Y + 0.00078*Y*Y*Y*Y,
    2451900.05952 + 365242.74049*Y - 0.06223*Y*Y - 0.00823*Y*Y*Y + 0.00032*Y*Y*Y*Y,
  ][event]
  return new Date((JDE - 2440587.5) * 86400000)
}

function getDayOfYear(d: Date): number {
  return Math.floor((d.getTime() - new Date(d.getFullYear(), 0, 1).getTime()) / 86400000) + 1
}

function midDate(a: Date, b: Date): Date {
  return new Date((a.getTime() + b.getTime()) / 2)
}

function fmtDate(d: Date): string {
  return `${d.getDate()} ${MESES_ABR[d.getMonth()]}`
}

function buildWheelSabbats(year: number, hemisphere: 'north' | 'south'): ComputedSabbat[] {
  // Solstícios e equinócios: cálculo astronómico (Meeus) — variam ligeiramente por ano
  const march = computeEquinoxSolstice(year, 0)
  const june  = computeEquinoxSolstice(year, 1)
  const sep   = computeEquinoxSolstice(year, 2)
  const dec   = computeEquinoxSolstice(year, 3)

  // Cross-quarter sabbats: datas fixas tradicionais (não dependem do hemisfério)
  const fix = (month: number, day: number) => new Date(year, month, day)

  const mk = (name: string, symbol: string, date: Date, season: string): ComputedSabbat => ({
    name, symbol, date, day: getDayOfYear(date), dateStr: fmtDate(date), season,
  })

  const raw = hemisphere === 'north' ? [
    mk('Imbolc',     '✧', fix(1, 2),  'Início da Primavera'),   // 2 fev — fixo
    mk('Ostara',     '◉', march,      'Equinócio de Primavera'), // astronómico
    mk('Beltane',    '✦', fix(4, 1),  'Início do Verão'),        // 1 mai — fixo
    mk('Litha',      '⊙', june,       'Solstício de Verão'),      // astronómico
    mk('Lughnasadh', '✤', fix(7, 1),  'Início do Outono'),       // 1 ago — fixo
    mk('Mabon',      '◈', sep,        'Equinócio de Outono'),     // astronómico
    mk('Samhain',    '☽', fix(9, 31), 'Início do Inverno'),      // 31 out — fixo
    mk('Yule',       '✶', dec,        'Solstício de Inverno'),    // astronómico
  ] : [
    // Hemisfério Sul — estações invertidas; cross-quarters com datas fixas
    mk('Lughnasadh', '✤', fix(1, 2),  'Início do Outono'),       // 2 fev — fixo
    mk('Mabon',      '◈', march,      'Equinócio de Outono'),     // astronómico
    mk('Samhain',    '☽', fix(4, 1),  'Início do Inverno'),      // 1 mai — fixo
    mk('Yule',       '✶', june,       'Solstício de Inverno'),    // astronómico
    mk('Imbolc',     '✧', fix(7, 1),  'Início da Primavera'),    // 1 ago — fixo
    mk('Ostara',     '◉', sep,        'Equinócio de Primavera'), // astronómico
    mk('Beltane',    '✦', fix(9, 31), 'Início do Verão'),        // 31 out — fixo
    mk('Litha',      '⊙', dec,        'Solstício de Verão'),      // astronómico
  ]

  return raw.sort((a, b) => a.day - b.day)
}

// ── Clima — WMO codes ────────────────────────────────────────────────────────

function wmoIcon(code: number): string {
  if (code === 0)              return '☀'
  if (code === 1)              return '🌤'
  if (code === 2)              return '⛅'
  if (code === 3)              return '☁'
  if (code <= 49)              return '🌫'
  if (code <= 59)              return '🌦'
  if (code <= 69)              return '🌧'
  if (code <= 79)              return '🌨'
  if (code <= 84)              return '🌦'
  if (code <= 99)              return '⛈'
  return '🌡'
}

function wmoLabel(code: number): string {
  if (code === 0)  return 'Céu limpo'
  if (code === 1)  return 'Maiormente limpo'
  if (code === 2)  return 'Parcialmente nublado'
  if (code === 3)  return 'Nublado'
  if (code <= 49)  return 'Névoa'
  if (code <= 55)  return 'Garoa'
  if (code <= 59)  return 'Garoa com geada'
  if (code <= 65)  return 'Chuva'
  if (code <= 69)  return 'Chuva com geada'
  if (code <= 75)  return 'Neve'
  if (code <= 77)  return 'Granizo'
  if (code <= 82)  return 'Pancadas de chuva'
  if (code <= 86)  return 'Neve com rajadas'
  if (code <= 99)  return 'Tempestade'
  return 'Condição desconhecida'
}

const DIAS_SEM = ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb']

function dayLabel(iso: string): string {
  const d    = new Date(iso + 'T12:00:00')
  const now  = new Date(); now.setHours(0, 0, 0, 0)
  const diff = Math.round((new Date(iso + 'T00:00:00').getTime() - now.getTime()) / 86400000)
  if (diff === 0) return 'Hoje'
  if (diff === 1) return 'Amanhã'
  return DIAS_SEM[d.getDay()]
}

// ── Helpers de inicialização a partir de AppSettings ──────────────────────────

function parseHidden(raw: string[] | undefined): Set<WidgetId> {
  if (raw) return new Set(raw.filter(id => DEFAULT_ORDER.includes(id as WidgetId)) as WidgetId[])
  return new Set()
}

function parseOrder(raw: string[] | undefined, hidden: Set<WidgetId>): WidgetId[] {
  if (raw) {
    const valid = raw.filter(id => DEFAULT_ORDER.includes(id as WidgetId)) as WidgetId[]
    DEFAULT_ORDER.forEach(id => { if (!valid.includes(id) && !hidden.has(id)) valid.push(id) })
    return valid
  }
  return DEFAULT_ORDER.filter(id => !hidden.has(id))
}

function parseSizes(raw: Record<string, string> | undefined): Record<WidgetId, WidgetSize> {
  const valid = { ...DEFAULT_SIZES }
  if (raw) {
    for (const [k, v] of Object.entries(raw)) {
      if (DEFAULT_ORDER.includes(k as WidgetId) && ['sm', 'md', 'lg'].includes(v))
        valid[k as WidgetId] = v as WidgetSize
    }
  }
  return valid
}

// ── WidgetWrapper ─────────────────────────────────────────────────────────────

interface WrapperProps {
  id: WidgetId; size: WidgetSize; dark: boolean; isDragging: boolean
  onDragStart: () => void; onDragEnter: () => void; onDrop: () => void; onDragEnd: () => void
  onSizeChange: (s: WidgetSize) => void; onRemove: () => void; children: React.ReactNode
}

function WidgetWrapper({ id, size, dark, isDragging, onDragStart, onDragEnter, onDrop, onDragEnd, onSizeChange, onRemove, children }: WrapperProps) {
  const [hovered, setHovered] = useState(false)
  const counterRef = useRef(0)

  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  return (
    <div
      style={{
        gridColumn: size === 'lg' ? 'span 2' : 'span 1',
        gridRow:    size === 'lg' ? 'span 2' : 'span 1',
        position: 'relative',
        opacity: isDragging ? 0.35 : 1,
        transition: 'opacity 120ms',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onDragEnter={() => { counterRef.current++; if (counterRef.current === 1) onDragEnter() }}
      onDragLeave={() => { counterRef.current-- }}
      onDragOver={e => e.preventDefault()}
      onDrop={() => { counterRef.current = 0; onDrop() }}
    >
      <div style={{
        position: 'absolute', top: 8, right: 10, zIndex: 20,
        display: 'flex', alignItems: 'center', gap: 4,
        opacity: hovered ? 1 : 0, transition: 'opacity 150ms',
        pointerEvents: hovered ? 'auto' : 'none',
      }}>
        {(['sm','md','lg'] as WidgetSize[]).map(s => (
          <button key={s} onClick={() => onSizeChange(s)} style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.08em',
            padding: '2px 6px', border: `1px solid ${size === s ? accent : border}`,
            borderRadius: 2, background: size === s ? accent + '25' : cardBg,
            color: size === s ? accent : ink2, cursor: 'pointer', userSelect: 'none',
          }}>
            {s.toUpperCase()}
          </button>
        ))}
        <div
          draggable
          onDragStart={e => { e.stopPropagation(); onDragStart() }}
          onDragEnd={onDragEnd}
          style={{ cursor: 'grab', color: ink2, fontSize: 14, padding: '1px 4px',
            userSelect: 'none', lineHeight: 1, marginLeft: 2 }}
          title="Arrastar para reordenar"
        >⠿</div>
        <button
          onClick={onRemove}
          title="Remover widget"
          style={{
            fontFamily: 'var(--font-mono)', fontSize: 13, lineHeight: 1,
            padding: '1px 5px', border: `1px solid ${border}`,
            borderRadius: 2, background: cardBg, color: ink2,
            cursor: 'pointer', userSelect: 'none', marginLeft: 2,
          }}
        >×</button>
      </div>
      {children}
    </div>
  )
}

// ── Widget: Boas-vindas ───────────────────────────────────────────────────────

function WelcomeWidget({ dark }: { dark: boolean }) {
  const [time, setTime] = useState(formatTime())
  const workspace = useAppStore(s => s.workspace)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  const phrases = [
    'A lua e os astros aguardam sua jornada.',
    'O conhecimento é a mais antiga das magias.',
    'Cada projeto é um cosmos por explorar.',
    'Que as páginas em branco se encham de descobertas.',
    'O saber é o mapa; a curiosidade, a bússola.',
  ]
  const phrase   = phrases[new Date().getDate() % phrases.length]
  const hour     = new Date().getHours()
  const greeting = hour < 12 ? 'Bom dia' : hour < 18 ? 'Boa tarde' : 'Boa noite'

  useEffect(() => {
    const t = setInterval(() => setTime(formatTime()), 1000)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="card" style={{
      background: cardBg, borderColor: border,
      position: 'relative', overflow: 'hidden', minHeight: 100, gridColumn: '1 / -1',
    }}>
      <CosmosLayer width={600} height={100} seed="dash_welcome" density="low" dark={dark}
        style={{ opacity: 0.45, left: 'auto', right: 0, width: 300 }} />
      <div style={{ position: 'relative', zIndex: 2 }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 24,
          fontStyle: 'italic', color: ink, fontWeight: 'normal', marginBottom: 4 }}>
          {greeting}, {workspace?.name ?? 'Viajante'}
        </h1>
        <p style={{ fontSize: 12, color: ink2, fontStyle: 'italic', marginBottom: 8 }}>{phrase}</p>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: accent, letterSpacing: '0.08em' }}>
          {formatDateLong()}  ·  {time}
        </p>
      </div>
    </div>
  )
}

// ── Widget: Estatísticas ──────────────────────────────────────────────────────

interface StatsData {
  total_pages: number; pages_this_week: number; active_projects: number; total_projects: number
}

function StatsWidget({ dark, size, isActive }: { dark: boolean; size: WidgetSize; isActive: boolean }) {
  const [stats, setStats] = useState<StatsData | null>(null)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  useEffect(() => {
    if (isActive) {
      fromIpc<StatsData>(() => db().dashboard.stats(), 'dashboardStats')
        .then(r => r.match(data => setStats(data), _e => {}))
    }
  }, [isActive])

  const label = (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.2em',
      color: ink2, textTransform: 'uppercase', marginBottom: 12 }}>◈ Estatísticas</div>
  )

  if (!stats) return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>
      {label}
      <p style={{ fontSize: 11, color: ink2, fontStyle: 'italic' }}>A carregar…</p>
    </div>
  )

  if (size === 'sm') return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>
      {label}
      <div style={{ display: 'flex', gap: 20 }}>
        {[
          { v: stats.total_pages,     l: 'Páginas'  },
          { v: stats.active_projects, l: 'Projetos' },
        ].map(({ v, l }) => (
          <div key={l}>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 28,
              fontStyle: 'italic', color: accent, lineHeight: 1 }}>{v}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, marginTop: 2 }}>{l}</div>
          </div>
        ))}
      </div>
    </div>
  )

  const items = size === 'lg'
    ? [
        { label: 'Páginas',           value: stats.total_pages,     sub: `+${stats.pages_this_week} esta semana` },
        { label: 'Esta semana',       value: stats.pages_this_week, sub: 'páginas criadas'                       },
        { label: 'Projetos ativos',   value: stats.active_projects, sub: `${stats.total_projects} no total`      },
        { label: 'Total de projetos', value: stats.total_projects,  sub: 'incluindo inativos'                    },
      ]
    : [
        { label: 'Páginas',         value: stats.total_pages,     sub: `+${stats.pages_this_week} esta semana` },
        { label: 'Projetos ativos', value: stats.active_projects, sub: `${stats.total_projects} no total`      },
      ]

  return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>
      {label}
      <div style={{ display: 'flex', gap: 0 }}>
        {items.map((item, i) => (
          <div key={item.label} style={{
            flex: 1,
            paddingRight: i < items.length - 1 ? 16 : 0,
            marginRight:  i < items.length - 1 ? 16 : 0,
            borderRight:  i < items.length - 1 ? `1px solid ${border}` : 'none',
          }}>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: size === 'lg' ? 40 : 36,
              fontStyle: 'italic', color: accent, lineHeight: 1, marginBottom: 4 }}>{item.value}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink, letterSpacing: '0.08em' }}>{item.label}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, marginTop: 2 }}>{item.sub}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Widget: Projetos Ativos ───────────────────────────────────────────────────

function ProjectsWidget({ dark, size, onProjectOpen, isActive }: { dark: boolean; size: WidgetSize; onProjectOpen: (id: number) => void; isActive: boolean }) {
  const projects   = useAppStore(s => s.projects)
  const [counts, setCounts] = useState<Record<number, number>>({})

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  useEffect(() => {
    if (isActive) {
      fromIpc<StatsData & { page_counts?: { project_id: number; count: number }[] }>(
        () => db().dashboard.stats(), 'dashboardStatsProjects'
      ).then(r => r.match(data => {
        const map: Record<number, number> = {}
        for (const { project_id, count } of (data.page_counts ?? [])) map[project_id] = count
        setCounts(map)
      }, _e => {}))
    }
  }, [isActive])

  const active = projects.filter(p => p.status === 'active')
  const limit  = size === 'sm' ? 3 : size === 'md' ? 6 : 10
  const shown  = active.slice(0, limit)

  const label = (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.2em',
      color: ink2, textTransform: 'uppercase', marginBottom: 10 }}>✦ Projetos Ativos</div>
  )

  const Row = ({ p, compact }: { p: typeof shown[0]; compact?: boolean }) => {
    const color = p.color ?? '#8B7355'
    return (
      <button onClick={() => onProjectOpen(p.id)} style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: compact ? '4px 6px' : '6px 8px',
        border: `1px solid ${border}`, borderLeft: `3px solid ${color}`,
        borderRadius: 2, background: 'transparent', cursor: 'pointer', textAlign: 'left',
        transition: 'background 100ms', width: '100%',
      }}
        onMouseEnter={e => (e.currentTarget.style.background = dark ? 'rgba(232,223,200,0.05)' : 'rgba(44,36,22,0.04)')}
        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
      >
        <span style={{ fontSize: compact ? 13 : 16, flexShrink: 0 }}>{p.icon ?? PROJECT_TYPE_ICONS[p.project_type]}</span>
        <span style={{ flex: 1, fontFamily: 'var(--font-display)', fontSize: compact ? 12 : 13,
          fontStyle: 'italic', color: ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {p.name}
        </span>
        {!compact && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, flexShrink: 0 }}>
            {counts[p.id] ?? 0} págs
          </span>
        )}
      </button>
    )
  }

  return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>
      {label}
      {shown.length === 0
        ? <p style={{ fontSize: 11, color: ink2, fontStyle: 'italic' }}>Nenhum projeto ativo.</p>
        : (
          <div style={{
            display: size === 'lg' ? 'grid' : 'flex',
            gridTemplateColumns: size === 'lg' ? '1fr 1fr' : undefined,
            flexDirection: size === 'lg' ? undefined : 'column',
            gap: 5,
          }}>
            {shown.map(p => <Row key={p.id} p={p} compact={size === 'sm'} />)}
          </div>
        )
      }
      {active.length > limit && (
        <p style={{ fontSize: 10, color: ink2, fontStyle: 'italic', textAlign: 'right', marginTop: 6 }}>
          +{active.length - limit} mais
        </p>
      )}
    </div>
  )
}

// ── Widget: Atividade Recente ─────────────────────────────────────────────────

function RecentWidget({ dark, size, onPageOpen, isActive }: { dark: boolean; size: WidgetSize; onPageOpen: (projectId: number, pageId: number) => void; isActive: boolean }) {
  const [pages, setPages] = useState<any[]>([])
  const limit = size === 'sm' ? 4 : size === 'md' ? 8 : 12

  useEffect(() => {
    if (isActive) {
      fromIpc<any[]>(() => db().pages.listRecent(limit), 'listRecent')
        .then(r => r.match(data => setPages(data), _e => {}))
    }
  }, [limit, isActive]) // <-- limit e isActive como dependências

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  const label = (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.2em',
      color: ink2, textTransform: 'uppercase', marginBottom: 10 }}>⊛ Atividade Recente</div>
  )

  const Row = ({ p, i, total, compact }: { p: any; i: number; total: number; compact?: boolean }) => (
    <button onClick={() => onPageOpen(p.project_id, p.id)} style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '6px 4px', background: 'transparent', border: 'none',
      borderBottom: i < total - 1 ? `1px solid ${border}` : 'none',
      cursor: 'pointer', textAlign: 'left', width: '100%', transition: 'background 100ms',
    }}
      onMouseEnter={e => (e.currentTarget.style.background = dark ? 'rgba(232,223,200,0.05)' : 'rgba(44,36,22,0.04)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
    >
      <span style={{ fontSize: 13, flexShrink: 0 }}>{p.icon ?? '◦'}</span>
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <div style={{ fontSize: 12, color: ink, fontFamily: 'var(--font-display)',
          fontStyle: 'italic', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {p.title}
        </div>
        {!compact && (
          <div style={{ fontSize: 10, color: ink2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {p.project_name}
          </div>
        )}
      </div>
      {!compact && (
        <span style={{ fontSize: 10, color: ink2, flexShrink: 0, fontFamily: 'var(--font-mono)' }}>
          {timeAgo(p.updated_at)}
        </span>
      )}
    </button>
  )

  return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>
      {label}
      {pages.length === 0
        ? <p style={{ fontSize: 11, color: ink2, fontStyle: 'italic' }}>Nenhuma atividade ainda.</p>
        : size === 'lg'
          ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
              {pages.map((p, i) => <Row key={p.id} p={p} i={i % Math.ceil(pages.length / 2)} total={Math.ceil(pages.length / 2)} />)}
            </div>
          )
          : (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {pages.map((p, i) => <Row key={p.id} p={p} i={i} total={pages.length} compact={size === 'sm'} />)}
            </div>
          )
      }
    </div>
  )
}

// ── Widget: Prazos Próximos ───────────────────────────────────────────────────

function PrazosWidget({ dark, size, onPageOpen, isActive }: { dark: boolean; size: WidgetSize; onPageOpen: (projectId: number, pageId: number) => void; isActive: boolean }) {
  const [items, setItems] = useState<any[]>([])
  const days = size === 'lg' ? 30 : size === 'sm' ? 7 : 14

  useEffect(() => {
    if (isActive) {
      fromIpc<any[]>(() => db().pages.listUpcoming(days), 'listUpcoming')
        .then(r => r.match(data => setItems(data), _e => {}))
    }
  }, [days, isActive]) // <-- days e isActive como dependências

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const ribbon = dark ? '#C45A40' : '#8B3A2A'

  const label = (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.2em',
      color: ink2, textTransform: 'uppercase', marginBottom: 10 }}>
      ⚑ Prazos Próximos {size !== 'md' && <span style={{ opacity: 0.6 }}>({days} dias)</span>}
    </div>
  )

  const Row = ({ item, compact }: { item: any; compact?: boolean }) => {
    const color     = item.project_color ?? '#8B7355'
    const dateLabel = formatUpcomingDate(item.value_date)
    const isUrgent  = dateLabel === 'hoje' || dateLabel === 'amanhã'
    return (
      <button onClick={() => onPageOpen(item.project_id, item.id)} style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: compact ? '4px 6px' : '5px 8px',
        border: `1px solid ${border}`, borderLeft: `3px solid ${isUrgent ? ribbon : color}`,
        borderRadius: 2, background: 'transparent', cursor: 'pointer', textAlign: 'left',
        transition: 'background 100ms', width: '100%',
      }}
        onMouseEnter={e => (e.currentTarget.style.background = dark ? 'rgba(232,223,200,0.05)' : 'rgba(44,36,22,0.04)')}
        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
      >
        <span style={{ fontSize: 13, flexShrink: 0 }}>{item.icon ?? '◦'}</span>
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <div style={{ fontSize: 12, color: ink, fontFamily: 'var(--font-display)',
            fontStyle: 'italic', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {item.title}
          </div>
          {!compact && <div style={{ fontSize: 10, color: ink2 }}>{item.project_name} · {item.prop_name}</div>}
        </div>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, flexShrink: 0,
          color: isUrgent ? ribbon : ink2, fontWeight: isUrgent ? 'bold' : 'normal' }}>
          {dateLabel}
        </span>
      </button>
    )
  }

  return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>
      {label}
      {items.length === 0
        ? <p style={{ fontSize: 11, color: ink2, fontStyle: 'italic' }}>Nenhum prazo nos próximos {days} dias.</p>
        : size === 'lg'
          ? <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '5px 16px' }}>
              {items.map((item, i) => <Row key={`${item.id}_${i}`} item={item} />)}
            </div>
          : <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {items.map((item, i) => <Row key={`${item.id}_${i}`} item={item} compact={size === 'sm'} />)}
            </div>
      }
    </div>
  )
}

// ── Widget: Cosmos (Lua) ──────────────────────────────────────────────────────

function CosmosWidget({ dark, size }: { dark: boolean; size: WidgetSize }) {
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  const moon     = getMoonPhase()
  const fullMoon = size === 'lg' ? getNextFullMoon() : null
  const nextQ    = size === 'lg' ? getNextQuarter()  : null

  const label = (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.2em',
      color: ink2, textTransform: 'uppercase', marginBottom: 8 }}>☽ Fase da Lua</div>
  )

  if (size === 'sm') return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>
      {label}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 36, lineHeight: 1 }}>{moon.emoji}</span>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 13, fontStyle: 'italic', color: ink }}>{moon.name}</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: accent, marginTop: 2 }}>{moon.pct}% do ciclo</div>
        </div>
      </div>
    </div>
  )

  const arcR  = size === 'lg' ? 48 : 36
  const arcCx = size === 'lg' ? 60 : 50
  const arcCy = size === 'lg' ? 60 : 50
  const svgSz = size === 'lg' ? 120 : 100
  const endAngle = moon.raw * 2 * Math.PI - Math.PI / 2
  const arcX = arcCx + arcR * Math.cos(endAngle)
  const arcY = arcCy + arcR * Math.sin(endAngle)
  const lrg  = moon.raw > 0.5 ? 1 : 0
  const sw   = size === 'lg' ? 7 : 6

  const arcSvg = (
    <svg width={svgSz} height={svgSz} viewBox={`0 0 ${svgSz} ${svgSz}`} style={{ flexShrink: 0 }}>
      <circle cx={arcCx} cy={arcCy} r={arcR} fill="none" stroke={border} strokeWidth={sw} />
      {moon.raw > 0 && moon.raw < 1 && (
        <path d={`M ${arcCx} ${arcCy - arcR} A ${arcR} ${arcR} 0 ${lrg} 1 ${arcX.toFixed(1)} ${arcY.toFixed(1)}`}
          fill="none" stroke={accent} strokeWidth={sw} strokeLinecap="round" />
      )}
      {moon.raw >= 1 && <circle cx={arcCx} cy={arcCy} r={arcR} fill="none" stroke={accent} strokeWidth={sw} />}
      <text x={arcCx} y={arcCy} textAnchor="middle" dominantBaseline="middle"
        fontSize={size === 'lg' ? 28 : 22}>{moon.emoji}</text>
    </svg>
  )

  if (size === 'md') return (
    <div className="card" style={{ background: cardBg, borderColor: border, position: 'relative', overflow: 'hidden' }}>
      <CosmosLayer width={260} height={120} seed="dash_cosmos" density="medium" dark={dark} style={{ opacity: 0.4 }} />
      <div style={{ position: 'relative', zIndex: 2, display: 'flex', gap: 20, alignItems: 'center' }}>
        <div style={{ flex: 1 }}>
          {label}
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 13, fontStyle: 'italic', color: ink, marginBottom: 2 }}>{moon.name}</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2 }}>{moon.pct}% do ciclo</div>
        </div>
        <div style={{ width: 1, background: border, alignSelf: 'stretch' }} />
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
          {arcSvg}
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: accent, letterSpacing: '0.08em' }}>{moon.pct}%</div>
        </div>
      </div>
    </div>
  )

  return (
    <div className="card" style={{ background: cardBg, borderColor: border, position: 'relative', overflow: 'hidden' }}>
      <CosmosLayer width={600} height={160} seed="dash_cosmos_lg" density="medium" dark={dark} style={{ opacity: 0.3 }} />
      <div style={{ position: 'relative', zIndex: 2, display: 'flex', gap: 28, alignItems: 'center' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, flexShrink: 0 }}>
          {label}
          {arcSvg}
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: accent, letterSpacing: '0.08em' }}>{moon.pct}%</div>
        </div>
        <div style={{ width: 1, background: border, alignSelf: 'stretch' }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.15em',
            color: ink2, textTransform: 'uppercase', marginBottom: 4 }}>Fase Atual</div>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontStyle: 'italic', color: ink, marginBottom: 2 }}>{moon.name}</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, marginBottom: 12 }}>{moon.pct}% do ciclo sinódico</div>
          <div style={{ display: 'flex', gap: 20 }}>
            {fullMoon && (
              <div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.15em',
                  color: ink2, textTransform: 'uppercase', marginBottom: 3 }}>Próxima Lua Cheia</div>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 14, fontStyle: 'italic', color: ink }}>{fullMoon.dateStr}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: accent, marginTop: 1 }}>
                  {fullMoon.days === 0 ? 'hoje' : fullMoon.days === 1 ? 'amanhã' : `em ${fullMoon.days} dias`}
                </div>
              </div>
            )}
            {nextQ && (
              <div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.15em',
                  color: ink2, textTransform: 'uppercase', marginBottom: 3 }}>Próxima Fase</div>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 14, fontStyle: 'italic', color: ink }}>{nextQ.name}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: accent, marginTop: 1 }}>
                  {nextQ.days === 0 ? 'hoje' : nextQ.days === 1 ? 'amanhã' : `em ${nextQ.days} dias`}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Widget: Roda do Ano (astronómica + hemisfério) ────────────────────────────

function WheelOfYearWidget({ dark, size, location }: { dark: boolean; size: WidgetSize; location: StoredLocation | null | undefined }) {
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const ink    = dark ? '#E8DFC8' : '#2C2416'

  const hemisphere = location?.hemisphere ?? null

  const now      = new Date()
  const year     = now.getFullYear()
  const todayDoy = getDayOfYear(now)

  const label = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.2em',
        color: ink2, textTransform: 'uppercase' }}>✦ Roda do Ano</span>
      {hemisphere !== null && (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: ink2, opacity: 0.65 }}>
          · {hemisphere === 'north' ? 'NORTE' : 'SUL'}
        </span>
      )}
    </div>
  )

  const NoLocation = () => (
    <p style={{ fontSize: 11, color: ink2, fontStyle: 'italic' }}>
      Configure sua localização em <strong>Ajustes → Localização</strong> para ver a Roda correta para seu hemisfério e datas astronómicas precisas.
    </p>
  )

  if (size === 'sm') {
    if (!hemisphere) return (
      <div className="card" style={{ background: cardBg, borderColor: border }}>{label}<NoLocation /></div>
    )
    const sabbats    = buildWheelSabbats(year, hemisphere)
    const nextSabbat = sabbats.find(s => s.day >= todayDoy) ?? sabbats[0]
    const daysLeft   = nextSabbat.day - todayDoy
    const daysUntil  = daysLeft >= 0 ? daysLeft : 365 - todayDoy + nextSabbat.day
    const dl = daysUntil === 0 ? 'hoje' : daysUntil === 1 ? 'amanhã' : `em ${daysUntil} dias`
    return (
      <div className="card" style={{ background: cardBg, borderColor: border }}>
        {label}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 36, lineHeight: 1, fontFamily: 'var(--font-mono)', color: accent }}>{nextSabbat.symbol}</span>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 14, fontStyle: 'italic', color: ink }}>{nextSabbat.name}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: accent, marginTop: 2 }}>{dl}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, marginTop: 1 }}>{nextSabbat.dateStr} · {nextSabbat.season}</div>
            <div style={{ height: 3, background: border, borderRadius: 2, marginTop: 6, width: 80, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${Math.round(todayDoy / 365 * 100)}%`, background: accent, borderRadius: 2 }} />
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (!hemisphere) return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>{label}<NoLocation /></div>
  )

  const sabbats    = buildWheelSabbats(year, hemisphere)
  const nextSabbat = sabbats.find(s => s.day >= todayDoy) ?? sabbats[0]
  const daysLeft   = nextSabbat.day - todayDoy
  const daysUntil  = daysLeft >= 0 ? daysLeft : 365 - todayDoy + nextSabbat.day
  const dl         = daysUntil === 0 ? 'hoje' : daysUntil === 1 ? 'amanhã' : `em ${daysUntil} dias`

  const svgSize    = size === 'lg' ? 260 : 210
  const cx = svgSize / 2, cy = svgSize / 2
  const outerRim   = size === 'lg' ? 124 : 100
  const nameR      = size === 'lg' ? 111 : 88
  const dateR      = size === 'lg' ? 96  : 75
  const symbolR    = size === 'lg' ? 79  : 62
  const sectorOuter = size === 'lg' ? 62  : 48
  const innerR     = size === 'lg' ? 20  : 15

  const f      = (n: number) => n.toFixed(1)
  const toRad  = (day: number) => (day / 365 * 360 - 90) * Math.PI / 180
  const pt     = (day: number, r: number) => ({ x: cx + r * Math.cos(toRad(day)), y: cy + r * Math.sin(toRad(day)) })
  const textRot = (day: number) => {
    const a = day / 365 * 360 - 90
    return (a > 90 && a <= 270) ? a + 180 : a
  }
  const seasonFill = (season: string): string => {
    if (season.includes('Outono'))    return dark ? 'rgba(180,100,30,0.25)'  : 'rgba(160,85,25,0.22)'
    if (season.includes('Inverno'))   return dark ? 'rgba(70,110,160,0.22)'  : 'rgba(75,105,150,0.18)'
    if (season.includes('Primavera')) return dark ? 'rgba(80,148,70,0.24)'   : 'rgba(85,135,65,0.20)'
    return dark ? 'rgba(200,150,30,0.28)' : 'rgba(190,130,25,0.22)'  // Verão
  }
  const sector8 = (startDay: number, endDay: number, fill: string, key: string) => {
    const eff = startDay > endDay ? endDay + 365 : endDay
    const a1 = toRad(startDay), a2 = toRad(eff)
    const ox1 = cx + sectorOuter * Math.cos(a1), oy1 = cy + sectorOuter * Math.sin(a1)
    const ox2 = cx + sectorOuter * Math.cos(a2), oy2 = cy + sectorOuter * Math.sin(a2)
    const ix1 = cx + innerR * Math.cos(a1), iy1 = cy + innerR * Math.sin(a1)
    const ix2 = cx + innerR * Math.cos(a2), iy2 = cy + innerR * Math.sin(a2)
    const span = eff - startDay
    const large = span > 182 ? 1 : 0
    return (
      <path key={key} fill={fill} stroke="none" d={
        `M ${f(ix1)} ${f(iy1)} L ${f(ox1)} ${f(oy1)} A ${sectorOuter} ${sectorOuter} 0 ${large} 1 ${f(ox2)} ${f(oy2)} L ${f(ix2)} ${f(iy2)} A ${innerR} ${innerR} 0 ${large} 0 ${f(ix1)} ${f(iy1)} Z`
      } />
    )
  }

  const wheel = (
    <svg width={svgSize} height={svgSize} viewBox={`0 0 ${svgSize} ${svgSize}`} style={{ flexShrink: 0 }}>
      {/* 8 season sectors */}
      {sabbats.map((s, i) => {
        const next = sabbats[(i + 1) % sabbats.length]
        return sector8(s.day, next.day, seasonFill(s.season), `sect${i}`)
      })}

      {/* Ring borders */}
      <circle cx={cx} cy={cy} r={outerRim}    fill="none" stroke={border} strokeWidth={1.5} />
      <circle cx={cx} cy={cy} r={sectorOuter} fill="none" stroke={border} strokeWidth={0.6} opacity={0.5} />
      <circle cx={cx} cy={cy} r={innerR}      fill={cardBg} stroke={border} strokeWidth={1} />

      {/* Radial dividers */}
      {sabbats.map(s => {
        const o = pt(s.day, innerR), e = pt(s.day, outerRim)
        return <line key={s.name+'r'} x1={f(o.x)} y1={f(o.y)} x2={f(e.x)} y2={f(e.y)} stroke={border} strokeWidth={0.7} opacity={0.45} />
      })}

      {/* Symbols */}
      {sabbats.map(s => {
        const p = pt(s.day, symbolR)
        const isNext = s === nextSabbat
        return (
          <text key={s.name+'sym'} x={f(p.x)} y={f(p.y)}
            textAnchor="middle" dominantBaseline="middle"
            fontSize={isNext ? (size === 'lg' ? 18 : 14) : (size === 'lg' ? 13 : 10)}
            fill={isNext ? accent : ink2} opacity={isNext ? 1 : 0.55}
            fontFamily="var(--font-mono)"
          >{s.symbol}</text>
        )
      })}

      {/* Sabbat name labels (rotated, outer ring) */}
      {sabbats.map(s => {
        const p   = pt(s.day, nameR)
        const rot = textRot(s.day)
        const isNext = s === nextSabbat
        return (
          <text key={s.name+'n'} x={f(p.x)} y={f(p.y)}
            textAnchor="middle" dominantBaseline="middle"
            fontSize={size === 'lg' ? 8 : 6.5}
            fontFamily="var(--font-mono)" letterSpacing="0.06em"
            fill={isNext ? accent : ink2}
            opacity={isNext ? 1 : 0.65}
            fontWeight={isNext ? '700' : '400'}
            transform={`rotate(${f(rot)}, ${f(p.x)}, ${f(p.y)})`}
          >{s.name.toUpperCase()}</text>
        )
      })}

      {/* Date labels */}
      {sabbats.map(s => {
        const p   = pt(s.day, dateR)
        const rot = textRot(s.day)
        return (
          <text key={s.name+'dt'} x={f(p.x)} y={f(p.y)}
            textAnchor="middle" dominantBaseline="middle"
            fontSize={size === 'lg' ? 6 : 5}
            fontFamily="var(--font-mono)"
            fill={ink2} opacity={0.5}
            transform={`rotate(${f(rot)}, ${f(p.x)}, ${f(p.y)})`}
          >{s.dateStr}</text>
        )
      })}

      {/* Today marker */}
      {(() => {
        const p = pt(todayDoy, outerRim)
        return <>
          <circle cx={f(p.x)} cy={f(p.y)} r={size === 'lg' ? 6.5 : 5} fill={cardBg} stroke={accent} strokeWidth={1.5} opacity={0.4} />
          <circle cx={f(p.x)} cy={f(p.y)} r={size === 'lg' ? 3.5 : 2.8} fill={accent} />
        </>
      })()}

      {/* Center symbol */}
      <text x={cx} y={cy} textAnchor="middle" dominantBaseline="middle"
        fontSize={size === 'lg' ? 14 : 11} fill={accent} fontFamily="var(--font-mono)">✦</text>
    </svg>
  )

  const legend = (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.15em',
          color: ink2, textTransform: 'uppercase', marginBottom: 6 }}>Próximo Sabá</div>
        <div style={{ fontSize: 30, marginBottom: 4, fontFamily: 'var(--font-mono)', color: accent }}>{nextSabbat.symbol}</div>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontStyle: 'italic', color: ink }}>{nextSabbat.name}</div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: accent, marginTop: 2 }}>{dl}</div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, marginTop: 1 }}>{nextSabbat.season} · {nextSabbat.dateStr}</div>
      </div>
      <div style={{ borderTop: `1px solid ${border}`, paddingTop: 10 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.15em',
          color: ink2, textTransform: 'uppercase', marginBottom: 6 }}>Posição no Ano</div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink, marginBottom: 6 }}>
          Dia {todayDoy} · {Math.round(todayDoy / 365 * 100)}%
        </div>
        <div style={{ height: 3, background: border, borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${Math.round(todayDoy / 365 * 100)}%`, background: accent, borderRadius: 2 }} />
        </div>
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {sabbats.filter(s => s.day >= todayDoy).slice(0, 3).map(s => (
            <div key={s.name} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ fontSize: 13, fontFamily: 'var(--font-mono)', color: s === nextSabbat ? accent : ink2 }}>{s.symbol}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: s === nextSabbat ? accent : ink2 }}>
                {s.name} · {s.dateStr}{s === nextSabbat && ' ←'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  if (size === 'md') return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>
      {label}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>{wheel}{legend}</div>
    </div>
  )

  // LG
  return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>
      {label}
      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {wheel}
        <div style={{ flex: 1 }}>
          <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 42, fontFamily: 'var(--font-mono)', color: accent }}>{nextSabbat.symbol}</span>
            <div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.15em',
                color: ink2, textTransform: 'uppercase', marginBottom: 2 }}>Próximo Sabá</div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontStyle: 'italic', color: ink }}>{nextSabbat.name}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: accent, marginTop: 2 }}>{dl} · {nextSabbat.dateStr}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, marginTop: 1 }}>{nextSabbat.season}</div>
            </div>
          </div>
          <div style={{ marginBottom: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>Dia {todayDoy} de 365</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: accent }}>{Math.round(todayDoy / 365 * 100)}%</span>
            </div>
            <div style={{ height: 3, background: border, borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${Math.round(todayDoy / 365 * 100)}%`, background: accent, borderRadius: 2 }} />
            </div>
          </div>
          <div style={{ borderTop: `1px solid ${border}`, paddingTop: 12 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.15em',
              color: ink2, textTransform: 'uppercase', marginBottom: 8 }}>Roda Completa</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 16px' }}>
              {sabbats.map(s => {
                const isPast = s.day < todayDoy, isNext = s === nextSabbat
                return (
                  <div key={s.name} style={{
                    display: 'flex', alignItems: 'center', gap: 6, padding: '3px 6px',
                    background: isNext ? accent + '18' : 'transparent',
                    border: isNext ? `1px solid ${accent}40` : '1px solid transparent',
                    borderRadius: 2,
                  }}>
                    <span style={{ fontSize: 15, fontFamily: 'var(--font-mono)', color: isNext ? accent : ink2, opacity: isPast ? 0.45 : 1 }}>{s.symbol}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontFamily: 'var(--font-display)', fontSize: 11, fontStyle: 'italic',
                        color: isPast ? ink2 : ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {s.name}
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
                        {s.dateStr} · {s.season}
                      </div>
                    </div>
                    {isNext && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: accent, flexShrink: 0 }}>←</span>}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Widget: Previsão do Tempo ─────────────────────────────────────────────────

interface WeatherData {
  current: {
    temperature_2m:       number
    apparent_temperature: number
    weather_code:         number
    wind_speed_10m:       number
    relative_humidity_2m: number
  }
  daily: {
    time:                          string[]
    temperature_2m_max:            number[]
    temperature_2m_min:            number[]
    weather_code:                  number[]
    precipitation_probability_max: number[]
  }
}

// ── AgendaWidget ──────────────────────────────────────────────────────────────

const EVENT_TYPE_ICONS: Record<string, string> = {
  prova: '📝', trabalho: '📋', seminario: '🎙', defesa: '🎓',
  prazo: '⏰', reuniao: '👥', outro: '◦',
}
const EVENT_TYPE_COLORS: Record<string, string> = {
  prova: '#8B3A2A', trabalho: '#2C5F8A', seminario: '#6B4F72',
  defesa: '#b8860b', prazo: '#7A5C2E', reuniao: '#4A6741', outro: '#8B7355',
}

function AgendaWidget({ dark, size, isActive }: { dark: boolean; size: WidgetSize; isActive: boolean }) {
  const [events,  setEvents]  = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const accent = dark ? '#D4A820' : '#b8860b'
  const today  = new Date().toISOString().slice(0, 10)

  useEffect(() => {
    if (!isActive) return
    fromIpc<any[]>(() => db().events.listUpcoming(14), 'agendaEvents')
      .then(r => { if (r.isOk()) setEvents(r.value); setLoading(false) })
  }, [isActive])

  // Dias a mostrar: sm=3, md=7, lg=14
  const days = size === 'sm' ? 3 : size === 'lg' ? 14 : 7
  const dates: string[] = Array.from({ length: days }, (_, i) => {
    const d = new Date(); d.setDate(d.getDate() + i)
    return d.toISOString().slice(0, 10)
  })

  const DAY_SHORT = ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb']
  const MONTH_SHORT = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez']

  const eventsByDate: Record<string, any[]> = {}
  for (const ev of events) {
    const d = ev.start_dt?.slice(0, 10)
    if (d) { if (!eventsByDate[d]) eventsByDate[d] = []; eventsByDate[d].push(ev) }
  }

  return (
    <div style={{ padding: size === 'sm' ? '10px 12px' : '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em', color: ink2 }}>
        AGENDA DA SEMANA
      </span>
      {loading ? (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: ink2 }}>…</span>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: size === 'sm' ? 'repeat(3,1fr)' : size === 'lg' ? 'repeat(7,1fr)' : 'repeat(7,1fr)',
          gap: 4,
        }}>
          {dates.map(date => {
            const d       = new Date(date + 'T12:00:00')
            const isToday = date === today
            const evs     = eventsByDate[date] ?? []
            return (
              <div key={date} style={{
                display: 'flex', flexDirection: 'column', gap: 2,
                background: isToday ? (dark ? '#251F14' : '#EAE2CC') : cardBg,
                border: `1px solid ${isToday ? accent + '66' : border}`,
                borderRadius: 3, padding: '5px 5px 6px', minHeight: 60,
              }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginBottom: 3 }}>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: 8,
                    color: isToday ? accent : ink2, letterSpacing: '0.08em',
                  }}>
                    {DAY_SHORT[d.getDay()]}
                  </span>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: isToday ? 700 : 400,
                    color: isToday ? accent : ink, lineHeight: 1.2,
                  }}>
                    {d.getDate()}
                  </span>
                  {size === 'lg' && (
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 7, color: ink2 }}>
                      {MONTH_SHORT[d.getMonth()]}
                    </span>
                  )}
                </div>
                {evs.slice(0, size === 'sm' ? 2 : 4).map((ev: any) => {
                  const color = EVENT_TYPE_COLORS[ev.event_type ?? 'outro'] ?? '#8B7355'
                  return (
                    <div key={`${ev.source ?? 'c'}_${ev.id}`} title={ev.title} style={{
                      background: color + '22', borderLeft: `2px solid ${color}`,
                      borderRadius: 1, padding: '1px 3px',
                      fontFamily: 'var(--font-mono)', fontSize: 8, color: ink,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {EVENT_TYPE_ICONS[ev.event_type ?? 'outro']} {ev.title}
                    </div>
                  )
                })}
                {evs.length > (size === 'sm' ? 2 : 4) && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 7, color: ink2 }}>
                    +{evs.length - (size === 'sm' ? 2 : 4)}
                  </span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── RemindersWidget ───────────────────────────────────────────────────────────

function RemindersWidget({ dark, size, isActive }: { dark: boolean; size: WidgetSize; isActive: boolean }) {
  const [reminders, setReminders] = useState<any[]>([])
  const [loading,   setLoading]   = useState(true)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const accent = dark ? '#D4A820' : '#b8860b'

  const load = () => {
    fromIpc<any[]>(() => db().reminders.list(false), 'remindersList')
      .then(r => { if (r.isOk()) setReminders(r.value); setLoading(false) })
  }
  useEffect(() => { if (isActive) load() }, [isActive])

  const dismiss = async (id: number) => {
    await fromIpc(() => db().reminders.dismiss(id), 'dismissReminder')
    setReminders(prev => prev.filter(r => r.id !== id))
  }

  const limit  = size === 'sm' ? 3 : size === 'lg' ? 12 : 6
  const shown  = reminders.slice(0, limit)
  const now    = Date.now()

  function relTime(iso: string): { label: string; urgent: boolean } {
    const ms   = new Date(iso).getTime() - now
    const mins = Math.round(ms / 60000)
    const h    = Math.round(ms / 3600000)
    const d    = Math.round(ms / 86400000)
    if (ms < 0)       return { label: 'atrasado', urgent: true }
    if (mins < 60)    return { label: `em ${mins}min`, urgent: mins < 30 }
    if (h < 24)       return { label: `em ${h}h`, urgent: h < 2 }
    if (d === 1)      return { label: 'amanhã', urgent: false }
    return { label: `em ${d}d`, urgent: false }
  }

  return (
    <div style={{ padding: size === 'sm' ? '10px 12px' : '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em', color: ink2 }}>
          LEMBRETES
        </span>
        {reminders.length > 0 && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: accent }}>
            {reminders.length}
          </span>
        )}
      </div>
      {loading ? (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: ink2 }}>…</span>
      ) : shown.length === 0 ? (
        <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 13, color: ink2 }}>
          Nenhum lembrete pendente.
        </span>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {shown.map(r => {
            const { label, urgent } = relTime(r.trigger_at)
            return (
              <div key={r.id} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                background: cardBg, border: `1px solid ${urgent ? '#8B3A2A44' : border}`,
                borderLeft: `3px solid ${urgent ? '#8B3A2A' : accent}`,
                borderRadius: 2, padding: '6px 10px',
              }}>
                <span style={{ fontSize: 14, flexShrink: 0 }}>🔔</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontFamily: 'var(--font-body)', fontSize: 12, color: ink,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {r.title}
                  </div>
                  {size !== 'sm' && r.event_type && (
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
                      {EVENT_TYPE_ICONS[r.event_type]} {r.event_type}
                    </div>
                  )}
                </div>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 9, flexShrink: 0,
                  color: urgent ? '#8B3A2A' : ink2,
                }}>
                  {label}
                </span>
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ padding: '1px 5px', fontSize: 10, color: ink2, flexShrink: 0 }}
                  onClick={() => dismiss(r.id)}
                  title="Dispensar"
                >✕</button>
              </div>
            )
          })}
          {reminders.length > limit && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, textAlign: 'center' }}>
              +{reminders.length - limit} mais
            </span>
          )}
        </div>
      )}
    </div>
  )
}

// ── ProvasWidget ──────────────────────────────────────────────────────────────

const ACADEMIC_TYPES = ['prova', 'trabalho', 'seminario', 'defesa', 'prazo']

function ProvasWidget({ dark, size, isActive }: { dark: boolean; size: WidgetSize; isActive: boolean }) {
  const [events,  setEvents]  = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  useEffect(() => {
    if (!isActive) return
    fromIpc<any[]>(() => db().events.listUpcoming(60), 'provasEvents')
      .then(r => {
        if (r.isOk()) {
          setEvents(r.value.filter((e: any) => ACADEMIC_TYPES.includes(e.event_type ?? '')))
        }
        setLoading(false)
      })
  }, [isActive])

  const limit  = size === 'sm' ? 3 : size === 'lg' ? 10 : 5
  const shown  = events.slice(0, limit)
  const today  = new Date(); today.setHours(0,0,0,0)

  function daysUntil(iso: string): number {
    const d = new Date(iso.slice(0,10) + 'T12:00:00'); d.setHours(0,0,0,0)
    return Math.round((d.getTime() - today.getTime()) / 86400000)
  }

  return (
    <div style={{ padding: size === 'sm' ? '10px 12px' : '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em', color: ink2 }}>
        PRÓXIMAS PROVAS
      </span>
      {loading ? (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: ink2 }}>…</span>
      ) : shown.length === 0 ? (
        <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 13, color: ink2 }}>
          Sem provas ou prazos próximos.
        </span>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {shown.map(ev => {
            const d      = daysUntil(ev.start_dt)
            const color  = EVENT_TYPE_COLORS[ev.event_type ?? 'outro'] ?? '#8B7355'
            const urgent = d <= 3
            const dtFmt  = new Date(ev.start_dt.slice(0,10) + 'T12:00:00')
              .toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })
            return (
              <div key={ev.id} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                background: cardBg,
                border: `1px solid ${urgent ? color + '55' : border}`,
                borderLeft: `3px solid ${color}`,
                borderRadius: 2, padding: '6px 10px',
              }}>
                <span style={{ fontSize: 14, flexShrink: 0 }}>{EVENT_TYPE_ICONS[ev.event_type ?? 'outro']}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontFamily: 'var(--font-body)', fontSize: 12, color: ink,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {ev.title}
                  </div>
                  {size !== 'sm' && ev.description && (
                    <div style={{
                      fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {ev.description}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', flexShrink: 0 }}>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700,
                    color: urgent ? color : ink2,
                  }}>
                    {d === 0 ? 'Hoje' : d === 1 ? 'Amanhã' : `${d}d`}
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: ink2 }}>{dtFmt}</span>
                </div>
              </div>
            )
          })}
          {events.length > limit && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, textAlign: 'center' }}>
              +{events.length - limit} mais
            </span>
          )}
        </div>
      )}
    </div>
  )
}

// ── ProjProgressWidget ────────────────────────────────────────────────────────

interface ProjProgress {
  id: number; name: string; color: string; icon: string; project_type: string
  total_pages: number; done_pages: number; total_tasks: number; done_tasks: number
}

function ProjProgressWidget({ dark, size, isActive }: { dark: boolean; size: WidgetSize; isActive: boolean }) {
  const [projects, setProjects] = useState<ProjProgress[]>([])
  const [loading,  setLoading]  = useState(true)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  useEffect(() => {
    if (!isActive) return
    fromIpc<ProjProgress[]>(() => db().dashboardExtra.projectsProgress(), 'projectsProgress')
      .then(r => { if (r.isOk()) setProjects(r.value); setLoading(false) })
  }, [isActive])

  const limit = size === 'sm' ? 3 : size === 'lg' ? 8 : 5
  const shown = projects.slice(0, limit)

  function calcPct(p: ProjProgress): number {
    if (p.total_tasks > 0) return Math.round((p.done_tasks / p.total_tasks) * 100)
    if (p.total_pages > 0) return Math.round((p.done_pages / p.total_pages) * 100)
    return 0
  }
  function calcLabel(p: ProjProgress): string {
    if (p.total_tasks > 0) return `${p.done_tasks}/${p.total_tasks} tarefas`
    return `${p.done_pages}/${p.total_pages} páginas`
  }

  return (
    <div style={{ padding: size === 'sm' ? '10px 12px' : '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em', color: ink2 }}>
        PROGRESSO DOS PROJETOS
      </span>
      {loading ? (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: ink2 }}>…</span>
      ) : shown.length === 0 ? (
        <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 13, color: ink2 }}>
          Nenhum projeto ativo.
        </span>
      ) : (
        <div style={{
          display: size === 'lg' ? 'grid' : 'flex',
          gridTemplateColumns: size === 'lg' ? '1fr 1fr' : undefined,
          flexDirection: size !== 'lg' ? 'column' : undefined,
          gap: 6,
        }}>
          {shown.map(p => {
            const pct   = calcPct(p)
            const color = p.color ?? '#8B7355'
            return (
              <div key={p.id} style={{
                display: 'flex', flexDirection: 'column', gap: 4,
                background: cardBg, border: `1px solid ${border}`,
                borderRadius: 3, padding: '7px 10px',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: 13, flexShrink: 0 }}>{p.icon ?? '◦'}</span>
                  <span style={{
                    fontFamily: 'var(--font-body)', fontSize: 12, color: ink,
                    flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {p.name}
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color, flexShrink: 0 }}>
                    {pct}%
                  </span>
                </div>
                <div style={{ height: 4, background: border, borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{
                    width: `${pct}%`, height: '100%', background: color,
                    borderRadius: 2, transition: 'width 600ms',
                  }} />
                </div>
                {size !== 'sm' && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: ink2 }}>
                    {calcLabel(p)}
                  </span>
                )}
              </div>
            )
          })}
        </div>
      )}
      {projects.length > limit && (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, textAlign: 'center' }}>
          +{projects.length - limit} mais
        </span>
      )}
    </div>
  )
}

// ── QuoteWidget ───────────────────────────────────────────────────────────────

function QuoteWidget({ dark, size }: { dark: boolean; size: WidgetSize }) {
  const [quote,   setQuote]   = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const accent = dark ? '#D4A820' : '#b8860b'

  const load = () => {
    setLoading(true)
    fromIpc<any>(() => db().dashboardExtra.randomQuote(), 'randomQuote')
      .then(r => { if (r.isOk()) setQuote(r.value); setLoading(false) })
  }
  useEffect(() => { load() }, [])

  return (
    <div className="card" style={{ background: dark ? '#211D16' : '#EDE7D9', borderColor: dark ? '#3A3020' : '#C4B9A8' }}>
      <div style={{
        padding: size === 'sm' ? '10px 12px' : '16px 18px',
        display: 'flex', flexDirection: 'column', gap: 10,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em', color: ink2 }}>
            CITAÇÃO
          </span>
          <button
            className="btn btn-ghost btn-sm"
            style={{ color: ink2, padding: '1px 5px', fontSize: 11 }}
            onClick={load}
            title="Nova citação"
          >↻</button>
        </div>
        {loading ? (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: ink2 }}>…</span>
        ) : !quote ? (
          <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 13, color: ink2 }}>
            Nenhuma citação guardada ainda.
          </span>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ borderLeft: `3px solid ${accent}`, paddingLeft: 12 }}>
              <p style={{
                fontFamily: 'var(--font-display)', fontStyle: 'italic',
                fontSize: size === 'sm' ? 13 : 15,
                color: ink, margin: 0, lineHeight: 1.6,
                display: '-webkit-box', WebkitBoxOrient: 'vertical',
                WebkitLineClamp: size === 'sm' ? 3 : size === 'md' ? 6 : undefined,
                overflow: size !== 'lg' ? 'hidden' : undefined,
              }}>
                "{quote.text}"
              </p>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: accent }}>
                — {quote.reading_title}
              </span>
              {quote.author && size !== 'sm' && (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
                  {quote.author}
                </span>
              )}
              {quote.location && size === 'lg' && (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, fontStyle: 'italic' }}>
                  {quote.location}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── IdeasWidget ───────────────────────────────────────────────────────────────

function IdeasWidget({ dark, size, onProjectOpen }: { dark: boolean; size: WidgetSize; onProjectOpen: (id: number) => void }) {
  const [ideas,   setIdeas]   = useState<Project[]>([])
  const [loading, setLoading] = useState(true)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'

  useEffect(() => {
    fromIpc<Project[]>(() => db().projects.list(), 'projects:list')
      .then(r => {
        if (r.isOk()) setIdeas(r.value.filter(p => p.project_type === 'idea'))
        setLoading(false)
      })
  }, [])

  const STATUS_COLORS: Record<string, string> = {
    active:    accent,
    paused:    dark ? '#8A7A62' : '#9C8E7A',
    completed: '#4A6741',
    archived:  dark ? '#5A4A3A' : '#B0A090',
  }
  const STATUS_LABELS: Record<string, string> = {
    active: 'Ativa', paused: 'Pausada', completed: 'Concluída', archived: 'Arquivada',
  }

  const maxVisible = size === 'sm' ? 3 : size === 'md' ? 5 : 10

  return (
    <div className="card" style={{ background: dark ? '#211D16' : '#EDE7D9', borderColor: dark ? '#3A3020' : '#C4B9A8' }}>
      <div style={{ padding: size === 'sm' ? '10px 12px' : '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em', color: ink2 }}>
            IDEIAS FUTURAS
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2 }}>
            {ideas.length} {ideas.length === 1 ? 'ideia' : 'ideias'}
          </span>
        </div>
        {loading ? (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: ink2 }}>…</span>
        ) : ideas.length === 0 ? (
          <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 13, color: ink2 }}>
            Nenhuma ideia ainda. Crie um projeto do tipo "Ideia Futura".
          </span>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {ideas.slice(0, maxVisible).map(idea => (
              <button
                key={idea.id}
                onClick={() => onProjectOpen(idea.id)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer', padding: '6px 8px',
                  borderRadius: 4, textAlign: 'left', display: 'flex', alignItems: 'center', gap: 8,
                  borderLeft: `3px solid ${idea.color ?? accent}`,
                }}
                onMouseEnter={e => (e.currentTarget.style.background = dark ? '#2A2418' : '#E4DDD0')}
                onMouseLeave={e => (e.currentTarget.style.background = 'none')}
              >
                <span style={{ fontSize: 14 }}>{idea.icon ?? '💡'}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontFamily: 'var(--font-display)', fontSize: 13, color: ink,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>
                    {idea.name}
                  </div>
                  {idea.description && size !== 'sm' && (
                    <div style={{
                      fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2,
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                    }}>
                      {idea.description}
                    </div>
                  )}
                </div>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 9, color: STATUS_COLORS[idea.status] ?? ink2,
                  flexShrink: 0,
                }}>
                  {STATUS_LABELS[idea.status] ?? idea.status}
                </span>
              </button>
            ))}
            {ideas.length > maxVisible && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, paddingLeft: 8 }}>
                + {ideas.length - maxVisible} mais
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── ReadingGoalWidget ─────────────────────────────────────────────────────────

function ReadingGoalWidget({ dark, size }: { dark: boolean; size: WidgetSize }) {
  const [progress, setProgress] = useState<{ target: number | null; done: number } | null>(null)
  const [wsId,     setWsId]     = useState<number | null>(null)
  const year = new Date().getFullYear()

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'

  useEffect(() => {
    fromIpc<any>(() => db().workspace.get(), 'getWsForGoal')
      .then(r => r.match(ws => setWsId(ws.id), _e => {}))
  }, [])

  useEffect(() => {
    if (!wsId) return
    fromIpc<any>(() => db().readingGoals.progress(wsId, year), 'readingGoalWidget')
      .then(r => r.match(d => setProgress(d), _e => {}))
  }, [wsId, year])

  const target = progress?.target ?? null
  const done   = progress?.done ?? 0
  const pct    = target && target > 0 ? Math.min(1, done / target) : 0

  // SVG arc gauge
  const R = 54; const CX = 70; const CY = 70
  const circ = 2 * Math.PI * R
  const trackC = dark ? '#2A2418' : '#D8D0C0'

  return (
    <div className="card" style={{ background: dark ? '#211D16' : '#EDE7D9', borderColor: dark ? '#3A3020' : '#C4B9A8' }}>
      <div style={{ padding: size === 'sm' ? '10px 12px' : '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em', color: ink2 }}>
          META DE LEITURA {year}
        </span>
        {!target ? (
          <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 13, color: ink2 }}>
            Defina uma meta na Biblioteca para ver o progresso.
          </span>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {/* Gauge SVG */}
            <svg viewBox="0 0 140 140" style={{ width: 100, height: 100, flexShrink: 0 }}>
              <circle cx={CX} cy={CY} r={R} fill="none" stroke={trackC} strokeWidth={9} />
              <circle cx={CX} cy={CY} r={R} fill="none"
                stroke={pct >= 1 ? '#4A6741' : accent}
                strokeWidth={9}
                strokeLinecap="round"
                strokeDasharray={circ}
                strokeDashoffset={circ * (1 - pct)}
                transform={`rotate(-90 ${CX} ${CY})`}
                style={{ transition: 'stroke-dashoffset 0.6s ease' }}
              />
              <text x={CX} y={CY - 4} textAnchor="middle"
                fontFamily="var(--font-mono)" fontSize={22} fontWeight={300}
                fill={pct >= 1 ? '#4A6741' : accent}>
                {done}
              </text>
              <text x={CX} y={CY + 12} textAnchor="middle"
                fontFamily="var(--font-mono)" fontSize={9} fill={ink2} letterSpacing={0}>
                de {target}
              </text>
            </svg>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 18,
                color: pct >= 1 ? '#4A6741' : accent }}>
                {Math.round(pct * 100)}%
              </span>
              {pct >= 1 ? (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#4A6741' }}>
                  ✓ Meta atingida!
                </span>
              ) : (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2 }}>
                  {target - done} livro{target - done !== 1 ? 's' : ''} restante{target - done !== 1 ? 's' : ''}
                </span>
              )}
              {target > 0 && size !== 'sm' && (() => {
                const now = new Date()
                const dayOfYear = Math.floor((now.getTime() - new Date(now.getFullYear(), 0, 0).getTime()) / 86400000)
                const expected  = Math.round((dayOfYear / 365) * target)
                const diff = done - expected
                return (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9,
                    color: diff >= 0 ? '#4A6741' : dark ? '#C45A40' : '#8B3A2A' }}>
                    {diff >= 0 ? `+${diff}` : diff} vs. esperado
                  </span>
                )
              })()}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── HeatmapWidget ─────────────────────────────────────────────────────────────

function HeatmapWidget({ dark, size, isActive }: { dark: boolean; size: WidgetSize; isActive: boolean }) {
  const [heatmap, setHeatmap] = useState<{ day: string; minutes: number }[]>([])
  const [loaded,  setLoaded]  = useState(false)

  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const base   = dark ? '#2A2418' : '#D8D0C0'

  useEffect(() => {
    if (!isActive || loaded) return
    fromIpc<any>(() => db().analytics.global(), 'heatmapWidget')
      .then(r => {
        r.match(d => setHeatmap(d.heatmap ?? []), _e => {})
        setLoaded(true)
      })
  }, [isActive, loaded])

  // build compact grid: last N weeks depending on size
  const weeks = size === 'sm' ? 12 : size === 'md' ? 26 : 52
  const CELL  = size === 'sm' ? 9  : 10
  const GAP   = 2

  const map = new Map(heatmap.map(r => [r.day, r.minutes]))
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const start = new Date(today)
  start.setDate(start.getDate() - weeks * 7 + 1)
  const dow = (start.getDay() + 6) % 7
  start.setDate(start.getDate() - dow)

  const grid: { date: string; minutes: number }[][] = []
  const cur = new Date(start)
  while (cur <= today) {
    const week: { date: string; minutes: number }[] = []
    for (let d = 0; d < 7; d++) {
      const key = cur <= today ? cur.toISOString().slice(0, 10) : ''
      week.push({ date: key, minutes: key ? (map.get(key) ?? 0) : -1 })
      cur.setDate(cur.getDate() + 1)
    }
    grid.push(week)
  }

  const intensity = (min: number) => {
    if (min < 0)   return 'transparent'
    if (min === 0) return base
    if (min < 30)  return accent + '44'
    if (min < 60)  return accent + '88'
    if (min < 120) return accent + 'BB'
    return accent
  }

  const totalMins = heatmap
    .filter(r => r.day >= new Date(today.getFullYear(), today.getMonth() - 1, today.getDate()).toISOString().slice(0, 10))
    .reduce((s, r) => s + r.minutes, 0)

  return (
    <div className="card" style={{ background: dark ? '#211D16' : '#EDE7D9', borderColor: dark ? '#3A3020' : '#C4B9A8' }}>
      <div style={{ padding: size === 'sm' ? '10px 12px' : '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em', color: ink2 }}>
            MAPA DE ATIVIDADE
          </span>
          {totalMins > 0 && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: accent }}>
              {Math.round(totalMins / 60)}h este mês
            </span>
          )}
        </div>
        <div style={{ overflowX: 'auto' }}>
          <svg
            viewBox={`0 0 ${grid.length * (CELL + GAP)} ${7 * (CELL + GAP)}`}
            style={{ width: grid.length * (CELL + GAP), height: 7 * (CELL + GAP), display: 'block' }}>
            {grid.map((week, wi) =>
              week.map((cell, di) => {
                if (!cell.date) return null
                return (
                  <rect key={`${wi}-${di}`}
                    x={wi * (CELL + GAP)} y={di * (CELL + GAP)}
                    width={CELL} height={CELL} rx={1}
                    fill={intensity(cell.minutes)}>
                    <title>{cell.date}: {cell.minutes}min de foco</title>
                  </rect>
                )
              })
            )}
          </svg>
        </div>
        {heatmap.length === 0 && (
          <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 12, color: ink2 }}>
            Registe sessões de foco para ver o mapa.
          </span>
        )}
      </div>
    </div>
  )
}

// ── PomodoroWidget ────────────────────────────────────────────────────────────

function PomodoroWidget({ dark, size }: { dark: boolean; size: WidgetSize }) {
  const { workspace, pushToast } = useAppStore()

  type TimerMode   = 'focus' | 'break'
  type TimerStatus = 'idle' | 'running' | 'paused'
  const FOCUS_MIN = 25
  const BREAK_MIN = 5

  const [mode,         setMode]         = useState<TimerMode>('focus')
  const [status,       setStatus]       = useState<TimerStatus>('idle')
  const [remainSecs,   setRemainSecs]   = useState(FOCUS_MIN * 60)
  const [totalSecs,    setTotalSecs]    = useState(FOCUS_MIN * 60)
  const [sessionStart, setSessionStart] = useState<Date | null>(null)
  const [todayMins,    setTodayMins]    = useState(0)

  const intervalRef = React.useRef<ReturnType<typeof setInterval> | null>(null)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = mode === 'focus'
    ? (dark ? '#D4A820' : '#b8860b')
    : (dark ? '#4A8A60' : '#3D7A52')
  const trackC = dark ? '#2A2418' : '#D8D0C0'

  // Load today's focus
  useEffect(() => {
    fromIpc<{ minutes: number }>(() => db().analytics.todayFocus(), 'pomodoroToday')
      .then(r => r.match(d => setTodayMins(d.minutes), _e => {}))
  }, [])

  const stopInterval = () => {
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null }
  }
  useEffect(() => () => stopInterval(), [])

  useEffect(() => {
    if (remainSecs === 0 && status === 'running') {
      stopInterval()
      setStatus('idle')
      if (mode === 'focus' && sessionStart) {
        saveSession(FOCUS_MIN, sessionStart)
        setMode('break'); setRemainSecs(BREAK_MIN * 60); setTotalSecs(BREAK_MIN * 60)
        pushToast({ kind: 'success', title: 'Pomodoro concluído! ☕', detail: `Pausa de ${BREAK_MIN} min.` })
      } else if (mode === 'break') {
        setMode('focus'); setRemainSecs(FOCUS_MIN * 60); setTotalSecs(FOCUS_MIN * 60)
        pushToast({ kind: 'info', title: 'Pausa terminada!', detail: 'Próximo Pomodoro.' })
      }
      setSessionStart(null)
    }
  }, [remainSecs, status])

  const saveSession = async (durationMin: number, start: Date) => {
    if (!workspace) return
    await fromIpc<any>(() => db().time.create({
      workspace_id: workspace.id,
      project_id:   null,
      page_id:      null,
      duration_min: durationMin,
      session_type: 'pomodoro',
      notes:        'Dashboard Pomodoro',
      tags:         null,
      started_at:   start.toISOString(),
      ended_at:     new Date().toISOString(),
    }), 'pomodoroSave')
    setTodayMins(prev => prev + durationMin)
  }

  const start = () => {
    setSessionStart(new Date())
    setStatus('running')
    intervalRef.current = setInterval(() => setRemainSecs(p => p <= 1 ? 0 : p - 1), 1000)
  }
  const pause = () => { stopInterval(); setStatus('paused') }
  const resume = () => {
    setStatus('running')
    intervalRef.current = setInterval(() => setRemainSecs(p => p <= 1 ? 0 : p - 1), 1000)
  }
  const reset = () => {
    stopInterval(); setStatus('idle'); setSessionStart(null)
    const s = (mode === 'focus' ? FOCUS_MIN : BREAK_MIN) * 60
    setRemainSecs(s); setTotalSecs(s)
  }
  const finishEarly = async () => {
    if (!sessionStart || mode !== 'focus') return
    stopInterval(); setStatus('idle')
    const elapsed = Math.round((Date.now() - sessionStart.getTime()) / 60000)
    if (elapsed >= 1) { await saveSession(elapsed, sessionStart) }
    setSessionStart(null); setMode('focus')
    setRemainSecs(FOCUS_MIN * 60); setTotalSecs(FOCUS_MIN * 60)
  }

  const mm = String(Math.floor(remainSecs / 60)).padStart(2, '0')
  const ss = String(remainSecs % 60).padStart(2, '0')
  const R  = 54; const CX = 70; const CY = 70
  const circ = 2 * Math.PI * R
  const dashOff = circ * (1 - (totalSecs > 0 ? remainSecs / totalSecs : 1))

  const compact = size === 'sm'

  return (
    <div className="card" style={{ background: dark ? '#211D16' : '#EDE7D9', borderColor: dark ? '#3A3020' : '#C4B9A8' }}>
      <div style={{
        padding: compact ? '10px 12px' : '14px 16px',
        display: 'flex',
        flexDirection: compact ? 'row' : 'column',
        alignItems: 'center',
        gap: compact ? 12 : 10,
      }}>
        {/* Header */}
        {!compact && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em', color: ink2 }}>
              POMODORO
            </span>
            {todayMins > 0 && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: accent }}>
                {Math.floor(todayMins / 60) > 0 ? `${Math.floor(todayMins / 60)}h ` : ''}{todayMins % 60}min hoje
              </span>
            )}
          </div>
        )}

        {/* Clock SVG */}
        <svg viewBox="0 0 140 140"
          style={{ width: compact ? 80 : 120, height: compact ? 80 : 120, flexShrink: 0 }}>
          <circle cx={CX} cy={CY} r={R} fill="none" stroke={trackC} strokeWidth={8} />
          <circle cx={CX} cy={CY} r={R} fill="none"
            stroke={accent} strokeWidth={8}
            strokeLinecap="round"
            strokeDasharray={circ}
            strokeDashoffset={dashOff}
            transform={`rotate(-90 ${CX} ${CY})`}
            style={{ transition: status === 'running' ? 'stroke-dashoffset 1s linear' : 'stroke-dashoffset 0.3s ease',
              filter: status === 'running' ? `drop-shadow(0 0 4px ${accent}88)` : 'none' }}
          />
          <circle cx={CX} cy={CY} r={R - 12} fill={dark ? '#1A160E' : '#F5F0E8'} />
          <text x={CX} y={CY - 8} textAnchor="middle"
            fontFamily="var(--font-mono)" fontSize={compact ? 6 : 8}
            letterSpacing={2} fill={accent} opacity={0.8}>
            {mode === 'focus' ? 'FOCO' : 'PAUSA'}
          </text>
          <text x={CX} y={CY + 8} textAnchor="middle"
            fontFamily="var(--font-mono)" fontSize={compact ? 16 : 22}
            fontWeight={300} fill={ink} style={{ letterSpacing: '-0.5px' }}>
            {mm}:{ss}
          </text>
          {status === 'running' && (
            <circle cx={CX} cy={CY + 20} r={2.5} fill={accent}>
              <animate attributeName="opacity" values="1;0.3;1" dur="1.2s" repeatCount="indefinite" />
            </circle>
          )}
        </svg>

        {/* Controls */}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'center', alignItems: 'center' }}>
          {status === 'idle' && (
            <button className="btn btn-sm" style={{ borderColor: accent, color: accent }}
              onClick={start}>▶ Iniciar</button>
          )}
          {status === 'running' && (<>
            <button className="btn btn-sm" style={{ borderColor: dark ? '#3A3020' : '#C4B9A8', color: ink2 }}
              onClick={pause}>⏸ Pausar</button>
            {mode === 'focus' && (
              <button className="btn btn-sm" style={{ borderColor: dark ? '#3A3020' : '#C4B9A8', color: ink2 }}
                onClick={finishEarly}>✓</button>
            )}
          </>)}
          {status === 'paused' && (<>
            <button className="btn btn-sm" style={{ borderColor: accent, color: accent }}
              onClick={resume}>▶ Retomar</button>
            {mode === 'focus' && (
              <button className="btn btn-sm" style={{ borderColor: dark ? '#3A3020' : '#C4B9A8', color: ink2 }}
                onClick={finishEarly}>✓</button>
            )}
          </>)}
          <button className="btn btn-ghost btn-sm" style={{ color: ink2 }} onClick={reset}>↺</button>
        </div>
      </div>
    </div>
  )
}

// ── DayPlanWidget ─────────────────────────────────────────────────────────────

interface TodayBlock {
  id:            number
  task_id:       number
  date:          string
  planned_hours: number
  logged_hours:  number
  status:        string
  task_title:    string
  task_type:     string
  due_date:      string
  project_name:  string
  project_color: string
  project_icon:  string
}

const TASK_TYPE_ICONS: Record<string, string> = {
  aula: '📚', atividade: '📋', prova: '📝', leitura: '📖', outro: '◦',
}

function DayPlanWidget({ dark, size, isActive }: { dark: boolean; size: WidgetSize; isActive: boolean }) {
  const [blocks,  setBlocks]  = useState<TodayBlock[]>([])
  const [loading, setLoading] = useState(true)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const bg     = dark ? '#1A1610' : '#F5F0E8'
  const accent = dark ? '#D4A820' : '#b8860b'

  const load = async () => {
    setLoading(true)
    const r = await fromIpc<TodayBlock[]>(() => db().planner.todayBlocks(), 'todayBlocks')
    if (r.isOk()) setBlocks(r.value)
    setLoading(false)
  }

  useEffect(() => { if (isActive) load() }, [isActive])

  const handleLog = async (block: TodayBlock, hours: number) => {
    const r = await fromIpc<any>(() => db().planner.logBlock(block.id, hours), 'logBlock')
    if (r.isOk()) setBlocks(prev => prev.map(b => b.id === block.id ? { ...b, ...r.value } : b))
  }

  const totalPlanned = blocks.reduce((s, b) => s + b.planned_hours, 0)
  const totalDone    = blocks.filter(b => b.status === 'done').reduce((s, b) => s + b.planned_hours, 0)

  return (
    <div style={{ padding: size === 'sm' ? '10px 12px' : '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Cabeçalho */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em', color: ink2,
        }}>
          PLANO DO DIA
        </span>
        {totalPlanned > 0 && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: accent }}>
            {totalDone.toFixed(1)}/{totalPlanned.toFixed(1)}h
          </span>
        )}
      </div>

      {loading ? (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: ink2 }}>…</span>
      ) : blocks.length === 0 ? (
        <span style={{
          fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 13, color: ink2,
        }}>
          Nenhuma tarefa para hoje.
        </span>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {blocks.map(block => {
            const isDone = block.status === 'done'
            const color  = block.project_color ?? '#8B7355'
            return (
              <div key={block.id} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                background: dark ? '#211D16' : '#EDE7D9',
                border: `1px solid ${border}`,
                borderLeft: `3px solid ${isDone ? '#4A6741' : color}`,
                borderRadius: 2, padding: '6px 10px',
                opacity: isDone ? 0.65 : 1,
              }}>
                <span style={{ fontSize: 14, flexShrink: 0 }}>
                  {TASK_TYPE_ICONS[block.task_type] ?? '◦'}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontFamily: 'var(--font-body)', fontSize: 12, color: ink,
                    textDecoration: isDone ? 'line-through' : 'none',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {block.task_title}
                  </div>
                  {size !== 'sm' && (
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
                      {block.project_icon ?? '◦'} {block.project_name}
                    </div>
                  )}
                </div>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: isDone ? '#4A6741' : ink2, flexShrink: 0 }}>
                  {isDone ? `✓ ${block.planned_hours}h` : `${block.planned_hours}h`}
                </span>
                {!isDone && (
                  <button
                    className="btn btn-ghost btn-sm"
                    style={{ padding: '1px 5px', fontSize: 10, color: accent, flexShrink: 0 }}
                    onClick={() => handleLog(block, block.planned_hours)}
                    title="Marcar como concluído"
                  >
                    ✓
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}

      {size === 'lg' && totalPlanned > 0 && (
        <div style={{
          marginTop: 4, height: 4, background: border, borderRadius: 2, overflow: 'hidden',
        }}>
          <div style={{
            width: `${Math.min(100, (totalDone / totalPlanned) * 100)}%`,
            height: '100%', background: accent, borderRadius: 2, transition: 'width 400ms',
          }} />
        </div>
      )}
    </div>
  )
}

function WeatherWidget({ dark, size, location }: { dark: boolean; size: WidgetSize; location: StoredLocation | null | undefined }) {
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const ink    = dark ? '#E8DFC8' : '#2C2416'

  const [weather,  setWeather]  = useState<WeatherData | null>(null)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState<string | null>(null)

  const label = (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.2em',
      color: ink2, textTransform: 'uppercase', marginBottom: 8 }}>
      ◌ Previsão do Tempo{location && (
        <span style={{ opacity: 0.65 }}> · {location.city}</span>
      )}
    </div>
  )

  useEffect(() => {
    if (!location) return
    setLoading(true)
    setError(null)
    const days = size === 'lg' ? 4 : 3
    fetch(
      `https://api.open-meteo.com/v1/forecast?latitude=${location.latitude}&longitude=${location.longitude}` +
      `&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m` +
      `&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max` +
      `&timezone=${encodeURIComponent(location.timezone)}&forecast_days=${days}`
    )
      .then(r => r.json())
      .then((data: WeatherData) => { setWeather(data); setLoading(false) })
      .catch(() => { setError('Não foi possível obter a previsão.'); setLoading(false) })
  }, [location?.latitude, location?.longitude, size])

  if (!location) return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>
      {label}
      <p style={{ fontSize: 11, color: ink2, fontStyle: 'italic' }}>
        Configure sua localização em <strong>Ajustes → Localização</strong> para ver a previsão do tempo.
      </p>
    </div>
  )

  if (loading) return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>
      {label}
      <p style={{ fontSize: 11, color: ink2, fontStyle: 'italic' }}>A carregar…</p>
    </div>
  )

  if (error || !weather) return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>
      {label}
      <p style={{ fontSize: 11, color: ink2, fontStyle: 'italic' }}>{error ?? 'Sem dados.'}</p>
    </div>
  )

  const cur   = weather.current
  const daily = weather.daily

  // SM: ícone + temperatura + descrição
  if (size === 'sm') return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>
      {label}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <span style={{ fontSize: 38, lineHeight: 1 }}>{wmoIcon(cur.weather_code)}</span>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 28,
            fontStyle: 'italic', color: ink, lineHeight: 1 }}>
            {Math.round(cur.temperature_2m)}°
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, marginTop: 3 }}>
            {wmoLabel(cur.weather_code)}
          </div>
        </div>
      </div>
    </div>
  )

  // MD: atual completo + min/max de hoje
  if (size === 'md') return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>
      {label}
      <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
        {/* Atual */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1 }}>
          <span style={{ fontSize: 44, lineHeight: 1 }}>{wmoIcon(cur.weather_code)}</span>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 36,
              fontStyle: 'italic', color: ink, lineHeight: 1 }}>
              {Math.round(cur.temperature_2m)}°
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, marginTop: 3 }}>
              {wmoLabel(cur.weather_code)}
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, marginTop: 2 }}>
              Sensação {Math.round(cur.apparent_temperature)}°
            </div>
          </div>
        </div>

        <div style={{ width: 1, background: border, alignSelf: 'stretch' }} />

        {/* Detalhes + min/max */}
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 8 }}>
            {[
              ['Umidade',   `${cur.relative_humidity_2m}%`],
              ['Vento',     `${Math.round(cur.wind_speed_10m)} km/h`],
            ].map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2 }}>{k}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink }}>{v}</span>
              </div>
            ))}
          </div>
          <div style={{ borderTop: `1px solid ${border}`, paddingTop: 8,
            display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2 }}>Hoje</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink }}>
              {Math.round(daily.temperature_2m_min[0])}° / {Math.round(daily.temperature_2m_max[0])}°
            </span>
          </div>
        </div>
      </div>
    </div>
  )

  // LG: atual + previsão dos próximos dias
  return (
    <div className="card" style={{ background: cardBg, borderColor: border }}>
      {label}
      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* Atual */}
        <div style={{ flexShrink: 0, minWidth: 160 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
            <span style={{ fontSize: 52, lineHeight: 1 }}>{wmoIcon(cur.weather_code)}</span>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 44,
                fontStyle: 'italic', color: ink, lineHeight: 1 }}>
                {Math.round(cur.temperature_2m)}°
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: accent }}>
                Sensação {Math.round(cur.apparent_temperature)}°
              </div>
            </div>
          </div>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 14,
            fontStyle: 'italic', color: ink, marginBottom: 8 }}>
            {wmoLabel(cur.weather_code)}
          </div>
          {[
            ['Umidade', `${cur.relative_humidity_2m}%`],
            ['Vento',   `${Math.round(cur.wind_speed_10m)} km/h`],
          ].map(([k, v]) => (
            <div key={k} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2 }}>{k}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink }}>{v}</span>
            </div>
          ))}
        </div>

        <div style={{ width: 1, background: border, alignSelf: 'stretch' }} />

        {/* Previsão diária */}
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: `repeat(${daily.time.length}, 1fr)`, gap: 8 }}>
          {daily.time.map((date, i) => {
            const precip = daily.precipitation_probability_max[i]
            return (
              <div key={date} style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                padding: '8px 4px', borderRadius: 2,
                background: i === 0 ? accent + '14' : 'transparent',
                border: i === 0 ? `1px solid ${accent}35` : '1px solid transparent',
              }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: i === 0 ? accent : ink2,
                  textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                  {dayLabel(date)}
                </div>
                <div style={{ fontSize: 26 }}>{wmoIcon(daily.weather_code[i])}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: ink }}>
                  {Math.round(daily.temperature_2m_max[i])}°
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2 }}>
                  {Math.round(daily.temperature_2m_min[i])}°
                </div>
                {precip > 0 && (
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
                    💧 {precip}%
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── AddWidgetCard ─────────────────────────────────────────────────────────────

function AddWidgetCard({ dark, hiddenWidgets, onAdd }: {
  dark: boolean; hiddenWidgets: WidgetId[]; onAdd: (id: WidgetId) => void
}) {
  const [open, setOpen] = useState(false)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const rowHover = dark ? '#2A2318' : '#E5DDD0'

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', minHeight: 80,
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          background: cardBg, border: `1px dashed ${border}`,
          borderRadius: 4, cursor: 'pointer', color: ink2,
          fontFamily: 'var(--font-mono)', fontSize: 12, letterSpacing: '0.06em',
          transition: 'border-color 150ms, color 150ms',
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = accent; (e.currentTarget as HTMLButtonElement).style.color = accent }}
        onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = border; (e.currentTarget as HTMLButtonElement).style.color = ink2 }}
      >
        <span style={{ fontSize: 20, lineHeight: 1 }}>+</span>
        Adicionar widget
      </button>

      {open && (
        <div style={{
          position: 'absolute', bottom: 'calc(100% + 6px)', left: 0, zIndex: 50,
          background: cardBg, border: `1px solid ${border}`, borderRadius: 4,
          boxShadow: '0 4px 16px rgba(0,0,0,0.18)', minWidth: 220, overflow: 'hidden',
        }}>
          <div style={{ padding: '8px 12px 6px', fontFamily: 'var(--font-mono)', fontSize: 10,
            color: ink2, letterSpacing: '0.1em', textTransform: 'uppercase', borderBottom: `1px solid ${border}` }}>
            Widgets ocultos
          </div>
          {hiddenWidgets.map(id => (
            <button key={id} onClick={() => { onAdd(id); setOpen(false) }} style={{
              width: '100%', textAlign: 'left', padding: '8px 14px',
              background: 'transparent', border: 'none', cursor: 'pointer',
              fontFamily: 'var(--font-mono)', fontSize: 12, color: ink,
              display: 'flex', alignItems: 'center', gap: 8, transition: 'background 100ms',
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = rowHover }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent' }}
            >
              <span style={{ color: accent, fontSize: 14, lineHeight: 1 }}>+</span>
              {WIDGET_LABELS[id]}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Dashboard principal ───────────────────────────────────────────────────────

export const DashboardView: React.FC<Props> = ({ dark, isActive, onProjectOpen, onPageOpen, initialSettings }) => {
  const initHidden = parseHidden(initialSettings.hidden_widgets)
  const [order,    setOrder]    = useState<WidgetId[]>(() => parseOrder(initialSettings.dashboard_order, initHidden))
  const [sizes,    setSizes]    = useState<Record<WidgetId, WidgetSize>>(() => parseSizes(initialSettings.widget_sizes))
  const [hidden,   setHidden]   = useState<Set<WidgetId>>(initHidden)
  const [dragging, setDragging] = useState<WidgetId | null>(null)
  
  const [location, setLocation] = useState<StoredLocation | null | undefined>(initialSettings.location)

  // Pegamos o workspace para ter o ID do banco
  const workspace = useAppStore(s => s.workspace)

  // 1. RECARREGAR LOCALIZAÇÃO QUANDO A ABA FICAR ATIVA
  useEffect(() => {
    if (isActive) {
      fromIpc<any>(() => db().config.get('user_location'), 'getLocation').then(r => {
        if (r.isOk() && r.value) {
          try { setLocation(JSON.parse(r.value)) } catch {}
        } else {
          setLocation(null)
        }
      })
    }
  }, [isActive])

  // 2. FUNÇÃO PARA SALVAR NO TURSO (Banco de Dados)
  const persistLayout = async (newOrder: WidgetId[], newSizes: any, newHidden: Set<WidgetId>) => {
    if (!workspace) return
    const dashboard_settings = JSON.stringify({
      order: newOrder,
      sizes: newSizes,
      hidden: Array.from(newHidden)
    })
    
    await fromIpc(() => db().workspace.updateSettings({ 
      id: workspace.id, 
      dashboard_settings 
    }), 'updateLayout')
  }

  // 3. HANDLERS DE DRAG & DROP E REDIMENSIONAMENTO
  const handleDragStart = (id: WidgetId) => setDragging(id)

  const handleDragEnter = (id: WidgetId) => {
    if (!dragging || dragging === id) return
    setOrder(prev => {
      const arr = [...prev], from = arr.indexOf(dragging), to = arr.indexOf(id)
      arr.splice(from, 1); arr.splice(to, 0, dragging)
      return arr
    })
  }

  const handleDrop = () => {
    persistLayout(order, sizes, hidden)
    setDragging(null)
  }

  const handleSizeChange = (id: WidgetId, s: WidgetSize) => {
    setSizes(prev => {
      const next = { ...prev, [id]: s }
      persistLayout(order, next, hidden)
      return next
    })
  }

  const handleRemove = (id: WidgetId) => {
    setHidden(prev => {
      const nextHidden = new Set(prev); 
      nextHidden.add(id)
      const nextOrder = order.filter(w => w !== id)
      setOrder(nextOrder)
      persistLayout(nextOrder, sizes, nextHidden)
      return nextHidden
    })
  }

  const handleAdd = (id: WidgetId) => {
    setHidden(prev => {
      const nextHidden = new Set(prev); 
      nextHidden.delete(id)
      if (!order.includes(id)) {
        const nextOrder = [...order, id]
        setOrder(nextOrder)
        persistLayout(nextOrder, sizes, nextHidden)
      } else {
        persistLayout(order, sizes, nextHidden)
      }
      return nextHidden
    })
  }

  // 4. RENDERIZAÇÃO DOS WIDGETS
  // 4. RENDERIZAÇÃO DOS WIDGETS
  const renderWidget = (id: WidgetId, size: WidgetSize): React.ReactNode => {
    switch (id) {
      // Já atualizados e exigem o isActive:
      case 'stats':         return <StatsWidget        dark={dark} size={size} isActive={isActive} />
      case 'projects':      return <ProjectsWidget     dark={dark} size={size} onProjectOpen={onProjectOpen} isActive={isActive} />
      case 'recent':        return <RecentWidget       dark={dark} size={size} onPageOpen={onPageOpen} isActive={isActive} />
      case 'prazos':        return <PrazosWidget       dark={dark} size={size} onPageOpen={onPageOpen} isActive={isActive} />
      
      // Estáticos (Não buscam dados contínuos do banco, não precisam de isActive):
      case 'cosmos':        return <CosmosWidget       dark={dark} size={size} />
      case 'wheel':         return <WheelOfYearWidget  dark={dark} size={size} location={location} />
      case 'weather':       return <WeatherWidget      dark={dark} size={size} location={location} />
      case 'quote':         return <QuoteWidget        dark={dark} size={size} />

      case 'planner':       return <DayPlanWidget      dark={dark} size={size} isActive={isActive} />
      case 'agenda':        return <AgendaWidget       dark={dark} size={size} isActive={isActive} />
      case 'reminders':     return <RemindersWidget    dark={dark} size={size} isActive={isActive} />
      case 'provas':        return <ProvasWidget       dark={dark} size={size} isActive={isActive} />
      case 'proj_progress': return <ProjProgressWidget dark={dark} size={size} isActive={isActive} />
      case 'ideas':         return <IdeasWidget        dark={dark} size={size} onProjectOpen={onProjectOpen} />
      case 'reading_goal':  return <ReadingGoalWidget  dark={dark} size={size} />
      case 'heatmap':       return <HeatmapWidget      dark={dark} size={size} isActive={isActive} />
      case 'pomodoro':      return <PomodoroWidget     dark={dark} size={size} />
    }
  }

  const hiddenList = DEFAULT_ORDER.filter(id => hidden.has(id))

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '28px 32px 40px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: 16, gridAutoFlow: 'dense', gridAutoRows: 'minmax(180px, auto)' }}>
        <WelcomeWidget dark={dark} />
        {order.filter(id => !hidden.has(id)).map(id => (
          <WidgetWrapper
            key={id} id={id} size={sizes[id]} dark={dark} isDragging={dragging === id}
            onDragStart={() => handleDragStart(id)}
            onDragEnter={() => handleDragEnter(id)}
            onDrop={handleDrop}
            onDragEnd={() => setDragging(null)}
            onSizeChange={s => handleSizeChange(id, s)}
            onRemove={() => handleRemove(id)}
          >
            {renderWidget(id, sizes[id])}
          </WidgetWrapper>
        ))}
        {hiddenList.length > 0 && (
          <AddWidgetCard dark={dark} hiddenWidgets={hiddenList} onAdd={handleAdd} />
        )}
      </div>
    </div>
  )
}