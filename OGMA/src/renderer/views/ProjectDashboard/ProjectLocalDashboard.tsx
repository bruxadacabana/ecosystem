import React, { useState, useEffect } from 'react'
import { Project, Page } from '../../types'
import { fromIpc } from '../../types/errors'

const db = () => (window as any).db

// ── Tipos ─────────────────────────────────────────────────────────────────────

interface ProjectAnalytics {
  pages_count:     number
  tasks_total:     number
  tasks_done:      number
  tasks_overdue:   number
  focus_hours:     number
  focus_hours_30d: number
  last_session:    string | null
  next_deadline:   { title: string; deadline: string } | null
  heatmap:         { day: string; minutes: number }[]
  recent_pages:    { id: number; title: string; icon: string; updated_at: string }[]
  upcoming_tasks:  { id: number; title: string; deadline: string | null; priority: string; status: string; estimated_hours: number | null }[]
  upcoming_events: { id: number; title: string; event_type: string; start_at: string }[]
  backlinks_count: number
  tags_count:      number
  recent_sessions: { id: number; started_at: string; duration_min: number; label: string }[]
}

type ProjWidgetId = 'tasks' | 'recent_pages' | 'heatmap' | 'events' | 'progress' | 'readings' | 'sessions'

// ── Constantes de widgets ─────────────────────────────────────────────────────

const WIDGET_LABELS: Record<ProjWidgetId, string> = {
  tasks:        'Próximas Tarefas',
  recent_pages: 'Páginas Recentes',
  heatmap:      'Actividade de Foco',
  events:       'Próximas Actividades',
  progress:     'Progresso do Projecto',
  readings:     'Leituras Vinculadas',
  sessions:     'Sessões Recentes',
}

const WIDE_WIDGETS: Set<ProjWidgetId> = new Set(['heatmap', 'readings'])

const ALL_WIDGETS: ProjWidgetId[] = [
  'tasks', 'recent_pages', 'heatmap', 'events', 'progress', 'readings', 'sessions',
]

const DEFAULT_WIDGETS: Record<string, ProjWidgetId[]> = {
  academic: ['tasks', 'events', 'recent_pages', 'heatmap', 'progress'],
  creative: ['recent_pages', 'tasks',            'heatmap', 'progress'],
  research: ['recent_pages', 'tasks',            'heatmap', 'readings'],
  software: ['tasks',        'recent_pages',     'progress','heatmap'],
  health:   ['sessions',     'heatmap',          'tasks',   'recent_pages'],
  hobby:    ['sessions',     'heatmap',          'recent_pages', 'tasks'],
  idea:     ['recent_pages', 'tasks',            'heatmap'],
  custom:   ['tasks',        'recent_pages',     'heatmap', 'progress'],
}

function getWidgets(projectId: number, type: string): ProjWidgetId[] {
  const raw = localStorage.getItem(`ogma_proj_widgets_${projectId}`)
  if (raw) { try { return JSON.parse(raw) } catch {} }
  return DEFAULT_WIDGETS[type] ?? DEFAULT_WIDGETS.custom
}

function getHidden(projectId: number, type: string): ProjWidgetId[] {
  const raw = localStorage.getItem(`ogma_proj_hidden_${projectId}`)
  if (raw) { try { return JSON.parse(raw) } catch {} }
  const defaults = DEFAULT_WIDGETS[type] ?? DEFAULT_WIDGETS.custom
  return ALL_WIDGETS.filter(w => !defaults.includes(w))
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtRelDate(dateStr: string): string {
  if (!dateStr) return '—'
  const d    = new Date(dateStr)
  const now  = new Date()
  const diff = Math.floor((now.getTime() - d.getTime()) / 86400000)
  if (diff === 0)  return 'hoje'
  if (diff === 1)  return 'ontem'
  if (diff < 7)    return `${diff}d atrás`
  if (diff < 30)   return `${Math.floor(diff / 7)}sem atrás`
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })
}

function fmtDuration(min: number): string {
  if (min < 60) return `${min}min`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m > 0 ? `${h}h ${m}min` : `${h}h`
}

function fmtDeadline(dateStr: string): { label: string; overdue: boolean } {
  const d    = new Date(dateStr + 'T12:00:00')
  const now  = new Date()
  now.setHours(0, 0, 0, 0)
  const diff = Math.floor((d.getTime() - now.getTime()) / 86400000)
  if (diff < 0) return { label: `${Math.abs(diff)}d atrasado`, overdue: true }
  if (diff === 0) return { label: 'hoje', overdue: false }
  if (diff === 1) return { label: 'amanhã', overdue: false }
  if (diff < 7)   return { label: `em ${diff}d`, overdue: false }
  return { label: d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }), overdue: false }
}

// ── Mini Heatmap SVG ─────────────────────────────────────────────────────────

function MiniHeatmap({ data, dark, accent, projectId }: {
  data: { day: string; minutes: number }[]
  dark: boolean
  accent: string
  projectId: number
}) {
  const ink2 = dark ? '#8A7A62' : '#9C8E7A'
  const base = dark ? '#2A2418' : '#D8D0C0'
  const CELL = 10; const GAP = 2
  const WEEKS = 8

  const map = new Map(data.map(r => [r.day, r.minutes]))
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const start = new Date(today)
  start.setDate(start.getDate() - (WEEKS * 7 - 1))
  const dow = (start.getDay() + 6) % 7
  start.setDate(start.getDate() - dow)

  const weeks: { date: string; minutes: number }[][] = []
  let cur = new Date(start)
  while (cur <= today) {
    const week: { date: string; minutes: number }[] = []
    for (let d = 0; d < 7; d++) {
      if (cur > today) { week.push({ date: '', minutes: -1 }) }
      else {
        const key = cur.toISOString().slice(0, 10)
        week.push({ date: key, minutes: map.get(key) ?? 0 })
      }
      cur.setDate(cur.getDate() + 1)
    }
    weeks.push(week)
  }

  const intensity = (min: number) => {
    if (min <= 0)  return base
    if (min < 30)  return accent + '44'
    if (min < 60)  return accent + '88'
    if (min < 120) return accent + 'BB'
    return accent
  }

  const totalH = 7 * (CELL + GAP) - GAP
  const totalW = weeks.length * (CELL + GAP) - GAP
  const totalMin = data.reduce((s, r) => s + r.minutes, 0)

  return (
    <div>
      <svg viewBox={`0 0 ${totalW} ${totalH}`}
        style={{ width: totalW, height: totalH, display: 'block' }}>
        {weeks.map((week, wi) =>
          week.map((cell, di) => {
            if (!cell.date) return null
            return (
              <rect key={`${wi}-${di}`}
                x={wi * (CELL + GAP)} y={di * (CELL + GAP)}
                width={CELL} height={CELL} rx={1}
                fill={intensity(cell.minutes)}>
                <title>{cell.date}: {fmtDuration(cell.minutes)}</title>
              </rect>
            )
          })
        )}
      </svg>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2,
        marginTop: 8, display: 'flex', justifyContent: 'space-between',
      }}>
        <span>Últimas {WEEKS} semanas</span>
        <span style={{ color: accent }}>{fmtDuration(totalMin)} registadas</span>
      </div>
    </div>
  )
}

// ── Coluna de Stats ───────────────────────────────────────────────────────────

interface StatItem { label: string; value: string; sub?: string; accent?: boolean }

function getStats(project: Project, data: ProjectAnalytics): StatItem[] {
  const type = project.project_type
  const taskPct = data.tasks_total > 0
    ? `${Math.round((data.tasks_done / data.tasks_total) * 100)}%`
    : '—'

  const lastSess = data.last_session ? fmtRelDate(data.last_session) : 'nunca'
  const nextDL = data.next_deadline
    ? fmtDeadline(data.next_deadline.deadline).label
    : 'nenhum'

  const focusSub = `${data.focus_hours}h no total`

  switch (type) {
    case 'academic':
      return [
        { label: 'Páginas',      value: String(data.pages_count) },
        { label: 'Tarefas',      value: taskPct,                  sub: `${data.tasks_done}/${data.tasks_total} concluídas` },
        { label: 'Foco (30d)',   value: `${data.focus_hours_30d}h`, sub: focusSub },
        { label: 'Próx. Prazo',  value: nextDL,                   accent: !!data.next_deadline },
      ]
    case 'creative':
      return [
        { label: 'Páginas',      value: String(data.pages_count) },
        { label: 'Última Sessão',value: lastSess },
        { label: 'Foco Total',   value: `${data.focus_hours}h`,   sub: `${data.focus_hours_30d}h este mês` },
        { label: 'Tarefas Abertas', value: String(data.tasks_total - data.tasks_done) },
      ]
    case 'research':
      return [
        { label: 'Páginas',      value: String(data.pages_count) },
        { label: 'Backlinks',    value: String(data.backlinks_count) },
        { label: 'Tags',         value: String(data.tags_count) },
        { label: 'Foco (30d)',   value: `${data.focus_hours_30d}h`, sub: focusSub },
      ]
    case 'software':
      return [
        { label: 'Tarefas',      value: taskPct,                   sub: `${data.tasks_done}/${data.tasks_total}` },
        { label: 'Atrasadas',    value: String(data.tasks_overdue), accent: data.tasks_overdue > 0 },
        { label: 'Foco (30d)',   value: `${data.focus_hours_30d}h`, sub: focusSub },
        { label: 'Páginas',      value: String(data.pages_count) },
      ]
    case 'health':
    case 'hobby':
      return [
        { label: 'Sessões',      value: String(data.recent_sessions.length), sub: 'registadas' },
        { label: 'Foco Total',   value: `${data.focus_hours}h` },
        { label: 'Última Sessão',value: lastSess },
        { label: 'Tarefas',      value: taskPct, sub: `${data.tasks_done}/${data.tasks_total}` },
      ]
    case 'idea':
      return [
        { label: 'Páginas',      value: String(data.pages_count) },
        { label: 'Tarefas',      value: String(data.tasks_total - data.tasks_done), sub: 'em aberto' },
        { label: 'Última Edição',value: data.recent_pages[0] ? fmtRelDate(data.recent_pages[0].updated_at) : '—' },
        { label: 'Status',       value: project.status === 'active' ? 'Ativo' : project.status === 'paused' ? 'Pausado' : 'Concluído' },
      ]
    default:
      return [
        { label: 'Páginas',      value: String(data.pages_count) },
        { label: 'Tarefas',      value: taskPct, sub: `${data.tasks_done}/${data.tasks_total}` },
        { label: 'Foco (30d)',   value: `${data.focus_hours_30d}h`, sub: focusSub },
        { label: 'Última Sessão',value: lastSess },
      ]
  }
}

function StatsColumn({ project, data, dark }: {
  project: Project; data: ProjectAnalytics; dark: boolean
}) {
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const accent = dark ? '#D4A820' : '#b8860b'
  const color  = project.color ?? accent
  const stats  = getStats(project, data)

  return (
    <div className="proj-local-stats">
      {stats.map((s, i) => (
        <div key={i} className="proj-local-stat-card" style={{ borderColor: border }}>
          <span className="proj-local-stat-label" style={{ color: ink2 }}>{s.label}</span>
          <span className="proj-local-stat-value" style={{ color: s.accent ? color : ink }}>
            {s.value}
          </span>
          {s.sub && (
            <span className="proj-local-stat-sub" style={{ color: ink2 }}>{s.sub}</span>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Widgets ───────────────────────────────────────────────────────────────────

const EVENT_ICONS: Record<string, string> = {
  prova: '📝', trabalho: '📋', seminario: '🎙', defesa: '🎓',
  prazo: '⏰', reuniao: '👥', outro: '◦',
}
const EVENT_COLORS: Record<string, string> = {
  prova: '#8B3A2A', trabalho: '#2C5F8A', seminario: '#6B4F72',
  defesa: '#b8860b', prazo: '#7A5C2E', reuniao: '#4A6741', outro: '#8B7355',
}
const PRIORITY_COLORS: Record<string, string> = {
  urgent: '#8B3A2A', high: '#7A5C2E', medium: '#b8860b', low: '#4A6741',
}

function TasksWidget({ data, dark, onOpenPlanner }: {
  data: ProjectAnalytics; dark: boolean; onOpenPlanner: () => void
}) {
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const accent = dark ? '#D4A820' : '#b8860b'

  if (data.upcoming_tasks.length === 0) {
    return (
      <div style={{ padding: '16px 0', textAlign: 'center' }}>
        <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 13, color: ink2, opacity: 0.6 }}>
          Sem tarefas em aberto.
        </span>
        <br />
        <button className="btn btn-ghost btn-sm" onClick={onOpenPlanner}
          style={{ marginTop: 8, color: accent, fontSize: 10 }}>
          + Ir ao Planner
        </button>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {data.upcoming_tasks.map(t => {
        const dl = t.deadline ? fmtDeadline(t.deadline) : null
        return (
          <div key={t.id} style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '5px 8px', border: `1px solid ${border}`, borderRadius: 2,
            borderLeft: `3px solid ${PRIORITY_COLORS[t.priority] ?? border}`,
          }}>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 10, color: ink,
              flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {t.title}
            </span>
            {dl && (
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 9,
                color: dl.overdue ? '#8B3A2A' : ink2, flexShrink: 0,
              }}>
                {dl.label}
              </span>
            )}
          </div>
        )
      })}
      {data.tasks_total > data.upcoming_tasks.length && (
        <button className="btn btn-ghost btn-sm" onClick={onOpenPlanner}
          style={{ color: ink2, fontSize: 9, marginTop: 4, alignSelf: 'flex-end' }}>
          Ver todas ({data.tasks_total - data.tasks_done} abertas)
        </button>
      )}
    </div>
  )
}

function RecentPagesWidget({ data, dark, onPageOpen }: {
  data: ProjectAnalytics; dark: boolean; onPageOpen: (page: any) => void
}) {
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const bg     = dark ? '#1E1A12' : '#F0EBE0'

  if (data.recent_pages.length === 0) {
    return (
      <p style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 13, color: ink2, opacity: 0.6 }}>
        Nenhuma página ainda.
      </p>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {data.recent_pages.map(p => (
        <button key={p.id}
          onClick={() => onPageOpen({ id: p.id })}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '5px 8px', border: `1px solid ${border}`, borderRadius: 2,
            background: 'transparent', cursor: 'pointer', textAlign: 'left', width: '100%',
          }}
          onMouseEnter={e => (e.currentTarget.style.background = bg)}
          onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
        >
          <span style={{ fontSize: 14, flexShrink: 0 }}>{p.icon ?? '📄'}</span>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, color: ink,
            flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {p.title}
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, flexShrink: 0 }}>
            {fmtRelDate(p.updated_at)}
          </span>
        </button>
      ))}
    </div>
  )
}

function EventsWidget({ data, dark }: {
  data: ProjectAnalytics; dark: boolean
}) {
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'

  if (data.upcoming_events.length === 0) {
    return (
      <p style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 13, color: ink2, opacity: 0.6 }}>
        Sem actividades próximas.
      </p>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {data.upcoming_events.map(ev => {
        const color = EVENT_COLORS[ev.event_type ?? 'outro'] ?? '#8B7355'
        const dt    = ev.start_at?.slice(0, 10) ?? ''
        const dl    = dt ? fmtDeadline(dt) : null
        return (
          <div key={ev.id} style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '5px 8px', border: `1px solid ${color}44`,
            borderLeft: `3px solid ${color}`, borderRadius: 2,
          }}>
            <span>{EVENT_ICONS[ev.event_type ?? 'outro']}</span>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 10, color: ink,
              flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {ev.title}
            </span>
            {dl && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color, flexShrink: 0 }}>
                {dl.label}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

function ProgressWidget({ data, dark, color }: {
  data: ProjectAnalytics; dark: boolean; color: string
}) {
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const track  = dark ? '#2A2418' : '#D8D0C0'

  const taskPct   = data.tasks_total > 0 ? data.tasks_done / data.tasks_total : 0
  const taskLabel = `${Math.round(taskPct * 100)}%`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Donut */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <svg viewBox="0 0 80 80" style={{ width: 80, height: 80, flexShrink: 0 }}>
          {(() => {
            const R = 32; const circ = 2 * Math.PI * R
            const off = circ * (1 - taskPct)
            return (<>
              <circle cx={40} cy={40} r={R} fill="none" stroke={track} strokeWidth={8} />
              <circle cx={40} cy={40} r={R} fill="none" stroke={color} strokeWidth={8}
                strokeLinecap="round"
                strokeDasharray={circ} strokeDashoffset={off}
                transform="rotate(-90 40 40)"
                style={{ transition: 'stroke-dashoffset 0.5s ease' }}
              />
              <text x={40} y={36} textAnchor="middle"
                fontFamily="var(--font-mono)" fontSize={15} fill={color}>{taskLabel}</text>
              <text x={40} y={48} textAnchor="middle"
                fontFamily="var(--font-mono)" fontSize={7} fill={ink2} letterSpacing={1}>TAREFAS</text>
            </>)
          })()}
        </svg>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, letterSpacing: '0.1em' }}>
              CONCLUÍDAS
            </div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, color: ink }}>
              {data.tasks_done}
            </div>
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, letterSpacing: '0.1em' }}>
              ATRASADAS
            </div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, color: data.tasks_overdue > 0 ? '#8B3A2A' : ink }}>
              {data.tasks_overdue}
            </div>
          </div>
        </div>
      </div>
      {/* Pages bar */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>PÁGINAS</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink }}>{data.pages_count}</span>
        </div>
        <div style={{ height: 4, background: track, borderRadius: 2 }}>
          <div style={{
            height: '100%', width: `${Math.min(100, (data.pages_count / Math.max(data.pages_count, 10)) * 100)}%`,
            background: color, borderRadius: 2, transition: 'width 0.4s ease',
          }} />
        </div>
      </div>
    </div>
  )
}

function SessionsWidget({ data, dark }: {
  data: ProjectAnalytics; dark: boolean
}) {
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const accent = dark ? '#D4A820' : '#b8860b'

  if (data.recent_sessions.length === 0) {
    return (
      <p style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 13, color: ink2, opacity: 0.6 }}>
        Nenhuma sessão registada. Use a aba Tempo para registar.
      </p>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {data.recent_sessions.map(s => (
        <div key={s.id} style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '4px 8px', border: `1px solid ${border}`, borderRadius: 2,
        }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, flexShrink: 0 }}>
            {s.started_at?.slice(0, 10) ?? '—'}
          </span>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, color: ink,
            flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {s.label || 'Sessão de foco'}
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: accent, flexShrink: 0 }}>
            {fmtDuration(s.duration_min)}
          </span>
        </div>
      ))}
    </div>
  )
}

function ReadingsWidget({ projectId, dark, pages, onPageOpen }: {
  projectId: number; dark: boolean; pages: Page[]; onPageOpen: (page: any) => void
}) {
  const [readings, setReadings] = useState<any[]>([])
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const bg     = dark ? '#211D16' : '#EDE7D9'

  const STATUS_LABELS: Record<string, string> = {
    want: 'Quer ler', reading: 'Lendo', done: 'Lido', abandoned: 'Abandonado',
  }
  const STATUS_COLORS: Record<string, string> = {
    want: '#8B7355', reading: '#b8860b', done: '#4A6741', abandoned: '#8B3A2A',
  }

  useEffect(() => {
    fromIpc<any[]>(() => db().readingLinks.listForProject(projectId), 'readingsWidget')
      .then(r => r.match(d => setReadings(d), _e => {}))
  }, [projectId])

  if (readings.length === 0) {
    return (
      <p style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 13, color: ink2, opacity: 0.6 }}>
        Nenhuma leitura vinculada a este projecto.
      </p>
    )
  }

  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      {readings.map((r: any) => {
        let meta: any = {}
        try { if (r.metadata_json) meta = JSON.parse(r.metadata_json) } catch {}
        const cover    = r.cover_path || meta.cover_url || meta.cover_url_m
        const progress = r.progress_type === 'percent'
          ? (r.progress_percent ?? null)
          : (r.total_pages > 0 ? Math.round((r.current_page / r.total_pages) * 100) : null)
        const statusColor = STATUS_COLORS[r.status] ?? ink2
        const page = pages.find((p: any) => p.id === r.page_id)

        return (
          <button key={`${r.id}-${r.page_id}`}
            onClick={() => page && onPageOpen(page)}
            style={{
              display: 'flex', flexDirection: 'column', gap: 4,
              background: bg, border: `1px solid ${border}`, borderRadius: 3,
              padding: '6px 8px', cursor: page ? 'pointer' : 'default',
              width: 120, textAlign: 'left',
            }}
            onMouseEnter={e => { if (page) (e.currentTarget as any).style.borderColor = statusColor }}
            onMouseLeave={e => { if (page) (e.currentTarget as any).style.borderColor = border }}
          >
            <div style={{ display: 'flex', gap: 6 }}>
              {cover ? (
                <img src={cover} alt="" style={{ width: 28, height: 40, objectFit: 'cover', borderRadius: 1 }} />
              ) : (
                <div style={{ width: 28, height: 40, background: statusColor + '22', border: `1px solid ${statusColor}44`, borderRadius: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14 }}>
                  {r.reading_type === 'article' ? '📄' : '📖'}
                </div>
              )}
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 11, color: ink, lineHeight: 1.3, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                  {r.title}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: statusColor, marginTop: 2 }}>
                  {STATUS_LABELS[r.status] ?? r.status}
                </div>
              </div>
            </div>
            {progress !== null && (
              <div style={{ width: '100%', height: 2, background: border, borderRadius: 1 }}>
                <div style={{ width: `${progress}%`, height: '100%', background: statusColor, borderRadius: 1 }} />
              </div>
            )}
          </button>
        )
      })}
    </div>
  )
}

// ── Widget Card wrapper ───────────────────────────────────────────────────────

function WidgetCard({ id, dark, onHide, wide, children }: {
  id: ProjWidgetId; dark: boolean; onHide: (id: ProjWidgetId) => void
  wide?: boolean; children: React.ReactNode
}) {
  const [hover, setHover] = useState(false)
  const border = dark ? '#3A3020' : '#C4B9A8'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const bg     = dark ? '#211D16' : '#EDE7D9'

  return (
    <div
      className={wide ? 'proj-local-widget proj-local-widget--wide' : 'proj-local-widget'}
      style={{ borderColor: border, background: bg, position: 'relative' }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
        <span className="proj-local-widget-title" style={{ color: ink2, flex: 1 }}>
          {WIDGET_LABELS[id]}
        </span>
        {hover && (
          <button
            onClick={() => onHide(id)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: ink2, fontSize: 12, padding: '0 2px', lineHeight: 1,
              opacity: 0.6,
            }}
            title="Remover widget"
          >
            ×
          </button>
        )}
      </div>
      {children}
    </div>
  )
}

// ── Componente principal ──────────────────────────────────────────────────────

interface Props {
  project:      Project
  dark:         boolean
  pages:        Page[]
  onPageOpen:   (page: any) => void
  onOpenPlanner: () => void
}

export function ProjectLocalDashboard({ project, dark, pages, onPageOpen, onOpenPlanner }: Props) {
  const [data,    setData]    = useState<ProjectAnalytics | null>(null)
  const [loading, setLoading] = useState(true)
  const [widgets, setWidgets] = useState<ProjWidgetId[]>(() =>
    getWidgets(project.id, project.project_type)
  )
  const [hidden,  setHidden]  = useState<ProjWidgetId[]>(() =>
    getHidden(project.id, project.project_type)
  )

  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const accent = dark ? '#D4A820' : '#b8860b'
  const bg     = dark ? '#211D16' : '#EDE7D9'
  const color  = project.color ?? accent

  useEffect(() => {
    fromIpc<ProjectAnalytics>(
      () => db().analytics.project(project.id),
      'analyticsProject'
    ).then(r => {
      r.match(d => setData(d), _e => {})
      setLoading(false)
    })
  }, [project.id])

  const hideWidget = (id: ProjWidgetId) => {
    const next    = widgets.filter(w => w !== id)
    const nextH   = [...hidden, id]
    setWidgets(next)
    setHidden(nextH)
    localStorage.setItem(`ogma_proj_widgets_${project.id}`, JSON.stringify(next))
    localStorage.setItem(`ogma_proj_hidden_${project.id}`,  JSON.stringify(nextH))
  }

  const addWidget = (id: ProjWidgetId) => {
    const next  = [...widgets, id]
    const nextH = hidden.filter(w => w !== id)
    setWidgets(next)
    setHidden(nextH)
    localStorage.setItem(`ogma_proj_widgets_${project.id}`, JSON.stringify(next))
    localStorage.setItem(`ogma_proj_hidden_${project.id}`,  JSON.stringify(nextH))
  }

  if (loading) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flex: 1, color: ink2, fontFamily: 'var(--font-mono)', fontSize: 11, opacity: 0.5,
      }}>
        A carregar…
      </div>
    )
  }

  if (!data) return null

  const renderWidget = (id: ProjWidgetId) => {
    switch (id) {
      case 'tasks':
        return (
          <WidgetCard key={id} id={id} dark={dark} onHide={hideWidget}>
            <TasksWidget data={data} dark={dark} onOpenPlanner={onOpenPlanner} />
          </WidgetCard>
        )
      case 'recent_pages':
        return (
          <WidgetCard key={id} id={id} dark={dark} onHide={hideWidget}>
            <RecentPagesWidget data={data} dark={dark} onPageOpen={onPageOpen} />
          </WidgetCard>
        )
      case 'heatmap':
        return (
          <WidgetCard key={id} id={id} dark={dark} onHide={hideWidget} wide>
            <MiniHeatmap data={data.heatmap} dark={dark} accent={color} projectId={project.id} />
          </WidgetCard>
        )
      case 'events':
        return (
          <WidgetCard key={id} id={id} dark={dark} onHide={hideWidget}>
            <EventsWidget data={data} dark={dark} />
          </WidgetCard>
        )
      case 'progress':
        return (
          <WidgetCard key={id} id={id} dark={dark} onHide={hideWidget}>
            <ProgressWidget data={data} dark={dark} color={color} />
          </WidgetCard>
        )
      case 'readings':
        return (
          <WidgetCard key={id} id={id} dark={dark} onHide={hideWidget} wide>
            <ReadingsWidget projectId={project.id} dark={dark} pages={pages} onPageOpen={onPageOpen} />
          </WidgetCard>
        )
      case 'sessions':
        return (
          <WidgetCard key={id} id={id} dark={dark} onHide={hideWidget}>
            <SessionsWidget data={data} dark={dark} />
          </WidgetCard>
        )
      default:
        return null
    }
  }

  return (
    <div className="proj-local-dashboard">
      {/* Stats column */}
      <StatsColumn project={project} data={data} dark={dark} />

      {/* Widget grid */}
      <div className="proj-local-widgets">
        {widgets.map(id => renderWidget(id))}

        {/* + Adicionar widget */}
        {hidden.length > 0 && (
          <div className="proj-local-widget proj-local-widget--add" style={{ borderColor: border }}>
            <span className="proj-local-widget-title" style={{ color: ink2, marginBottom: 10, display: 'block' }}>
              + Adicionar widget
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {hidden.map(id => (
                <button key={id}
                  onClick={() => addWidget(id)}
                  className="btn btn-ghost btn-sm"
                  style={{ color: ink2, fontSize: 10, justifyContent: 'flex-start' }}
                >
                  + {WIDGET_LABELS[id]}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
