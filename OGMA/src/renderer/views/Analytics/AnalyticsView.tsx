import React, { useEffect, useState } from 'react'
import { fromIpc } from '../../types/errors'
import { PROJECT_TYPE_LABELS } from '../../types'
import { AlchemyLoader } from '../../components/UI/AlchemyLoader'
import './AnalyticsView.css'

const db = () => (window as any).db

// ── Tipos ─────────────────────────────────────────────────────────────────────

interface AnalyticsData {
  heatmap:            { day: string; minutes: number }[]
  hours_by_project:   { id: number; name: string; color: string; icon: string; project_type: string; hours: number }[]
  hours_by_type:      { project_type: string; hours: number }[]
  books_by_month:     { month: string; count: number }[]
  deep_work_hours:    number
  peak_hour:          number | null
  tasks_done:         number
  tasks_total:        number
  reading_goal:       { target: number; done: number; year: number } | null
  reading_absorption: { month: string; added: number; completed: number }[]
  reading_speed:      { date: string; pages: number }[]
  activity_by_dow:    { dow: number; minutes: number }[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtHour(h: number | null): string {
  if (h === null) return '—'
  if (h < 6)  return 'Madrugada'
  if (h < 12) return 'Manhã'
  if (h < 18) return 'Tarde'
  return 'Noite'
}

function fmtHourDetail(h: number | null): string {
  if (h === null) return ''
  return `${String(h).padStart(2, '0')}h–${String(h + 1).padStart(2, '0')}h`
}

function fmtMonth(ym: string): string {
  const [y, m] = ym.split('-')
  const months = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
  return `${months[parseInt(m) - 1]} ${y.slice(2)}`
}

// fill last 12 months even if no data
function fillMonths(raw: { month: string; count: number }[]): { month: string; count: number }[] {
  const map = new Map(raw.map(r => [r.month, r.count]))
  const result: { month: string; count: number }[] = []
  const now = new Date()
  for (let i = 11; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    result.push({ month: key, count: map.get(key) ?? 0 })
  }
  return result
}

// fill last 12 months for absorption (added vs completed)
function fillAbsorptionMonths(
  raw: { month: string; added: number; completed: number }[]
): { month: string; added: number; completed: number }[] {
  const map = new Map(raw.map(r => [r.month, r]))
  const result: { month: string; added: number; completed: number }[] = []
  const now = new Date()
  for (let i = 11; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    const row = map.get(key)
    result.push({ month: key, added: row?.added ?? 0, completed: row?.completed ?? 0 })
  }
  return result
}

// Moon phase from julian date (simplified Meeus)
function moonPhaseLabel(dateStr: string): string {
  const date = new Date(dateStr)
  const jd = date.getTime() / 86400000 + 2440587.5
  const cycle = 29.53058868
  const ref = 2451550.1 // known new moon (Jan 6 2000)
  const age = ((jd - ref) % cycle + cycle) % cycle
  if (age < 3.7)  return 'Lua Nova'
  if (age < 11.1) return 'Lua Crescente'
  if (age < 18.5) return 'Lua Cheia'
  if (age < 25.9) return 'Lua Minguante'
  return 'Lua Nova'
}

// fill last 365 days for heatmap
function buildHeatmapGrid(raw: { day: string; minutes: number }[]): {
  weeks: { date: string; minutes: number }[][]
} {
  const map = new Map(raw.map(r => [r.day, r.minutes]))
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  // go back to the most recent Monday that gives us 52 full weeks
  const start = new Date(today)
  start.setDate(start.getDate() - 364)
  // align to Monday
  const dow = (start.getDay() + 6) % 7 // Mon=0
  start.setDate(start.getDate() - dow)

  const weeks: { date: string; minutes: number }[][] = []
  let cur = new Date(start)
  while (cur <= today) {
    const week: { date: string; minutes: number }[] = []
    for (let d = 0; d < 7; d++) {
      if (cur > today) {
        week.push({ date: '', minutes: -1 }) // future cell
      } else {
        const key = cur.toISOString().slice(0, 10)
        week.push({ date: key, minutes: map.get(key) ?? 0 })
      }
      cur.setDate(cur.getDate() + 1)
    }
    weeks.push(week)
  }
  return { weeks }
}

// ── SVG Grouped Bar Chart (2 series) ─────────────────────────────────────────

function GroupedBarChart({ data, dark, labelA, labelB, colorA, colorB }: {
  data: { label: string; a: number; b: number }[]
  dark: boolean
  labelA: string
  labelB: string
  colorA: string
  colorB: string
}) {
  const ink2 = dark ? '#8A7A62' : '#9C8E7A'
  const W = 400; const H = 130
  const padL = 8; const padB = 28; const padT = 8
  const chartH = H - padB - padT
  const chartW = W - padL

  if (data.length === 0) return <p className="analytics-empty">Sem dados ainda.</p>

  const max = Math.max(...data.flatMap(d => [d.a, d.b]), 0.1)
  const groupW = chartW / data.length
  const barW = Math.min(14, (groupW - 6) / 2)
  const gap = 2

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: H }}>
        <line x1={padL} y1={padT} x2={padL} y2={H - padB} stroke={ink2} strokeWidth={0.5} opacity={0.3} />
        <line x1={padL} y1={H - padB} x2={W} y2={H - padB} stroke={ink2} strokeWidth={0.5} opacity={0.3} />
        {data.map((d, i) => {
          const gx = padL + i * groupW + groupW / 2
          const hA = (d.a / max) * chartH
          const hB = (d.b / max) * chartH
          const xA = gx - barW - gap / 2
          const xB = gx + gap / 2
          return (
            <g key={i}>
              <rect x={xA} y={padT + chartH - hA} width={barW} height={hA} fill={colorA} opacity={0.8} rx={1} />
              <rect x={xB} y={padT + chartH - hB} width={barW} height={hB} fill={colorB} opacity={0.8} rx={1} />
              <text x={gx} y={H - padB + 12} textAnchor="middle"
                fontFamily="var(--font-mono)" fontSize={7} fill={ink2}>
                {d.label.length > 5 ? d.label.slice(0, 5) : d.label}
              </text>
            </g>
          )
        })}
      </svg>
      <div style={{ display: 'flex', gap: 16, marginTop: 8, fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <div style={{ width: 10, height: 10, background: colorA, borderRadius: 1, opacity: 0.8 }} />
          {labelA}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <div style={{ width: 10, height: 10, background: colorB, borderRadius: 1, opacity: 0.8 }} />
          {labelB}
        </div>
      </div>
    </div>
  )
}

// ── SVG Bar Chart ─────────────────────────────────────────────────────────────

function BarChart({ data, dark, valueLabel }: {
  data: { label: string; value: number; color?: string }[]
  dark: boolean
  valueLabel?: (v: number) => string
}) {
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const W = 400
  const H = 130
  const padL = 8
  const padB = 28
  const padT = 8
  const chartH = H - padB - padT
  const chartW = W - padL

  if (data.length === 0) return (
    <p className="analytics-empty">Sem dados ainda.</p>
  )

  const max = Math.max(...data.map(d => d.value), 0.1)
  const barW = Math.min(36, (chartW / data.length) - 4)
  const gap  = (chartW - barW * data.length) / (data.length + 1)

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: H }} className="analytics-bar-chart">
      {/* guide line */}
      <line x1={padL} y1={padT} x2={padL} y2={H - padB}
        stroke={ink2} strokeWidth={0.5} opacity={0.3} />
      <line x1={padL} y1={H - padB} x2={W} y2={H - padB}
        stroke={ink2} strokeWidth={0.5} opacity={0.3} />

      {data.map((d, i) => {
        const barH = (d.value / max) * chartH
        const x    = padL + gap + i * (barW + gap)
        const y    = padT + chartH - barH
        const col  = d.color ?? accent
        const fmtV = valueLabel ? valueLabel(d.value) : String(d.value)
        return (
          <g key={i}>
            <rect x={x} y={y} width={barW} height={barH}
              fill={col} opacity={0.8} rx={1} />
            {barH > 14 && (
              <text x={x + barW / 2} y={y + 10}
                textAnchor="middle"
                fontFamily="var(--font-mono)" fontSize={8}
                fill={dark ? '#1A1610' : '#F5F0E8'} opacity={0.9}>
                {fmtV}
              </text>
            )}
            <text x={x + barW / 2} y={H - padB + 12}
              textAnchor="middle"
              fontFamily="var(--font-mono)" fontSize={8}
              fill={ink2}>
              {d.label.length > 6 ? d.label.slice(0, 6) : d.label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

// ── SVG Radar (polígono) ──────────────────────────────────────────────────────

function RadarChart({ data, dark }: {
  data: { label: string; value: number; color: string }[]
  dark: boolean
}) {
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const CX = 90; const CY = 90; const R = 75
  const n = data.length
  if (n < 2) return <p className="analytics-empty">Dados insuficientes.</p>

  const max = Math.max(...data.map(d => d.value), 0.1)

  const angle = (i: number) => (i / n) * Math.PI * 2 - Math.PI / 2
  const pt    = (i: number, r: number) => ({
    x: CX + r * Math.cos(angle(i)),
    y: CY + r * Math.sin(angle(i)),
  })

  // grid rings
  const rings = [0.25, 0.5, 0.75, 1].map(f => {
    const pts = Array.from({ length: n }, (_, i) => pt(i, R * f))
    return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ') + ' Z'
  })

  // data polygon
  const dataPts = data.map((d, i) => pt(i, (d.value / max) * R))
  const dataPath = dataPts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ') + ' Z'

  return (
    <div className="analytics-radar-wrap">
      <svg viewBox="0 0 180 180" style={{ width: 180, height: 180, flexShrink: 0 }}>
        {/* spokes */}
        {Array.from({ length: n }, (_, i) => {
          const end = pt(i, R)
          return <line key={i} x1={CX} y1={CY} x2={end.x} y2={end.y}
            stroke={ink2} strokeWidth={0.5} opacity={0.3} />
        })}
        {/* rings */}
        {rings.map((d, i) => (
          <path key={i} d={d} fill="none" stroke={ink2}
            strokeWidth={0.5} opacity={0.2} />
        ))}
        {/* data */}
        <path d={dataPath} fill={accent} fillOpacity={0.18}
          stroke={accent} strokeWidth={1.5} />
        {/* dots */}
        {dataPts.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={3}
            fill={accent} opacity={0.8} />
        ))}
      </svg>
      <div className="analytics-radar-legend">
        {data.map((d, i) => (
          <div key={i} className="analytics-radar-legend-item">
            <div style={{
              width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
              background: accent, opacity: 0.15 + 0.85 * (d.value / max),
            }} />
            <span style={{ color: ink2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {(PROJECT_TYPE_LABELS as Record<string, string>)[d.label] ?? d.label}
            </span>
            <span style={{ color: dark ? '#E8DFC8' : '#2C2416', marginLeft: 'auto', flexShrink: 0 }}>
              {d.value.toFixed(1)}h
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Heatmap ───────────────────────────────────────────────────────────────────

function ActivityHeatmap({ data, dark }: {
  data: { day: string; minutes: number }[]
  dark: boolean
}) {
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const base   = dark ? '#2A2418' : '#D8D0C0'
  const CELL = 11
  const GAP  = 2
  const { weeks } = buildHeatmapGrid(data)

  const intensity = (min: number): string => {
    if (min <= 0)  return base
    if (min < 30)  return accent + '44'
    if (min < 60)  return accent + '88'
    if (min < 120) return accent + 'BB'
    return accent
  }

  const DAYS = ['S','T','Q','Q','S','S','D']
  const totalW = weeks.length * (CELL + GAP) - GAP
  const totalH = 7 * (CELL + GAP) - GAP + 18

  return (
    <div className="analytics-heatmap-scroll">
      <svg viewBox={`0 0 ${totalW + 20} ${totalH}`}
        style={{ width: Math.max(400, totalW + 20), height: totalH, display: 'block' }}>
        {/* Day labels */}
        {[0, 2, 4].map(d => (
          <text key={d} x={0} y={18 + d * (CELL + GAP) + CELL * 0.75}
            fontFamily="var(--font-mono)" fontSize={7} fill={ink2} opacity={0.6}>
            {DAYS[d]}
          </text>
        ))}
        {/* Month labels */}
        {weeks.map((week, wi) => {
          const firstDay = week.find(c => c.date)?.date
          if (!firstDay || firstDay.slice(8) !== '01') return null
          const [, m] = firstDay.split('-')
          const months = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
          return (
            <text key={wi}
              x={14 + wi * (CELL + GAP)} y={9}
              fontFamily="var(--font-mono)" fontSize={7} fill={ink2} opacity={0.6}>
              {months[parseInt(m) - 1]}
            </text>
          )
        })}
        {/* Cells */}
        {weeks.map((week, wi) =>
          week.map((cell, di) => {
            if (!cell.date) return null
            const x = 14 + wi * (CELL + GAP)
            const y = 12 + di * (CELL + GAP)
            return (
              <rect key={`${wi}-${di}`}
                x={x} y={y} width={CELL} height={CELL}
                rx={1} fill={intensity(cell.minutes)}>
                <title>{cell.date}: {cell.minutes}min</title>
              </rect>
            )
          })
        )}
      </svg>
      <div className="analytics-heatmap-legend">
        <span>Menos</span>
        {['00', '44', '88', 'BB', 'FF'].map(a => (
          <div key={a} style={{
            width: CELL, height: CELL, borderRadius: 1,
            background: a === '00' ? base : accent + a,
          }} />
        ))}
        <span>Mais</span>
      </div>
    </div>
  )
}

// ── Componente principal ───────────────────────────────────────────────────────

export function AnalyticsView({ dark }: { dark: boolean }) {
  const [data,    setData]    = useState<AnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'

  useEffect(() => {
    fromIpc<AnalyticsData>(() => db().analytics.global(), 'analyticsGlobal')
      .then(r => {
        r.match(d => setData(d), _e => {})
        setLoading(false)
      })
  }, [])

  const completionPct = data && data.tasks_total > 0
    ? Math.round((data.tasks_done / data.tasks_total) * 100)
    : null

  const booksMonths = data ? fillMonths(data.books_by_month) : []
  const radarData = data
    ? data.hours_by_type.map(t => ({ label: t.project_type, value: t.hours, color: accent }))
    : []

  // Reading absorption: last 12 months filled
  const absorptionMonths = data ? fillAbsorptionMonths(data.reading_absorption) : []

  // Reading speed: avg pages/day last 7 days
  const avgPagesPerDay = data && data.reading_speed.length > 0
    ? Math.round(data.reading_speed.reduce((s, r) => s + r.pages, 0) / 7)
    : null

  // Activity by day of week: Sun=0 → Sat=6, reorder to Mon–Sun
  const DOW_LABELS = ['Seg','Ter','Qua','Qui','Sex','Sáb','Dom']
  const dowMap = new Map((data?.activity_by_dow ?? []).map(r => [r.dow, r.minutes]))
  // JS strftime('%w'): 0=Sun, 1=Mon...6=Sat → reorder to Mon(1)…Sun(0)
  const dowData = [1,2,3,4,5,6,0].map((d, i) => ({
    label: DOW_LABELS[i],
    value: Math.round((dowMap.get(d) ?? 0) / 60 * 10) / 10,
  }))

  // Produtividade por Fase Lunar: group heatmap days by moon phase
  const lunarMap = new Map<string, number>()
  if (data) {
    for (const { day, minutes } of data.heatmap) {
      const phase = moonPhaseLabel(day)
      lunarMap.set(phase, (lunarMap.get(phase) ?? 0) + minutes)
    }
  }
  const LUNAR_ORDER = ['Lua Nova', 'Lua Crescente', 'Lua Cheia', 'Lua Minguante']
  const lunarData = LUNAR_ORDER.map(phase => ({
    label: phase.replace('Lua ', ''),
    value: Math.round((lunarMap.get(phase) ?? 0) / 60 * 10) / 10,
  }))

  return (
    <div className="analytics-root">
      {/* ── Title ──────────────────────────────────────────────────────────── */}
      <div>
        <h1 style={{
          fontFamily: 'var(--font-display)', fontSize: 22, fontStyle: 'italic',
          fontWeight: 'normal', color: ink, margin: 0,
        }}>
          Analytics
        </h1>
        <p style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2,
          letterSpacing: '0.1em', marginTop: 4,
        }}>
          ÚLTIMOS 30 DIAS · {new Date().getFullYear()}
        </p>
      </div>

      {loading ? (
        <div style={{ padding: '60px 0', textAlign: 'center', opacity: 0.6 }}>
          <AlchemyLoader symbol="☿" size="lg" />
        </div>
      ) : !data ? (
        <div style={{ color: ink2, fontFamily: 'var(--font-display)', fontStyle: 'italic',
          fontSize: 14, textAlign: 'center', padding: '60px 0' }}>
          Sem dados disponíveis ainda.
        </div>
      ) : (<>

        {/* ── Stat cards ─────────────────────────────────────────────────── */}
        <div className="analytics-stat-row">
          <div className="analytics-stat-card" style={{ animationDelay: '0ms' }}>
            <span className="analytics-stat-label">Deep Work</span>
            <span className="analytics-stat-value">{data.deep_work_hours}</span>
            <span className="analytics-stat-sub">horas (últimos 30 dias)</span>
          </div>
          <div className="analytics-stat-card" style={{ animationDelay: '40ms' }}>
            <span className="analytics-stat-label">Pico de Foco</span>
            <span className="analytics-stat-value" style={{ fontSize: 20 }}>
              {fmtHour(data.peak_hour)}
            </span>
            <span className="analytics-stat-sub">{fmtHourDetail(data.peak_hour)}</span>
          </div>
          <div className="analytics-stat-card" style={{ animationDelay: '80ms' }}>
            <span className="analytics-stat-label">Tarefas Concluídas</span>
            <span className="analytics-stat-value">
              {completionPct !== null ? `${completionPct}%` : '—'}
            </span>
            <span className="analytics-stat-sub">
              {data.tasks_done} de {data.tasks_total} (30 dias)
            </span>
          </div>
          {data.reading_goal ? (
            <div className="analytics-stat-card" style={{ animationDelay: '120ms' }}>
              <span className="analytics-stat-label">Meta de Leitura {data.reading_goal.year}</span>
              <span className="analytics-stat-value">
                {data.reading_goal.done}
                <span style={{ fontSize: 14, color: ink2 }}> / {data.reading_goal.target}</span>
              </span>
              <span className="analytics-stat-sub">
                {data.reading_goal.target > 0
                  ? `${Math.round((data.reading_goal.done / data.reading_goal.target) * 100)}% da meta`
                  : 'livros concluídos'}
              </span>
            </div>
          ) : (
            <div className="analytics-stat-card" style={{ animationDelay: '120ms' }}>
              <span className="analytics-stat-label">Livros (ano)</span>
              <span className="analytics-stat-value">
                {booksMonths.reduce((s, m) => s + m.count, 0)}
              </span>
              <span className="analytics-stat-sub">concluídos em {new Date().getFullYear()}</span>
            </div>
          )}
        </div>

        {/* ── Activity Heatmap ───────────────────────────────────────────── */}
        <div className="analytics-card">
          <div className="analytics-card-title">Mapa de Atividade — Últimas 52 Semanas</div>
          {data.heatmap.length === 0 ? (
            <p className="analytics-empty">
              Registe sessões de foco na aba Tempo de qualquer projeto para ver o mapa.
            </p>
          ) : (
            <ActivityHeatmap data={data.heatmap} dark={dark} />
          )}
        </div>

        {/* ── Row: Horas por Projeto + Radar Polímata ────────────────────── */}
        <div className="analytics-grid-2">
          <div className="analytics-card">
            <div className="analytics-card-title">Horas por Projeto — Últimos 30 dias</div>
            {data.hours_by_project.length === 0 ? (
              <p className="analytics-empty">Sem sessões de foco registadas.</p>
            ) : (
              <BarChart
                dark={dark}
                data={data.hours_by_project.map(p => ({
                  label: p.name,
                  value: p.hours,
                  color: p.color,
                }))}
                valueLabel={v => `${v}h`}
              />
            )}
            {data.hours_by_project.length > 0 && (
              <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 4 }}>
                {data.hours_by_project.map(p => (
                  <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{
                      width: 8, height: 8, borderRadius: 1, flexShrink: 0,
                      background: p.color ?? accent,
                    }} />
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2,
                      flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>{p.icon} {p.name}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink, flexShrink: 0 }}>
                      {p.hours}h
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="analytics-card">
            <div className="analytics-card-title">Radar Polímata — Distribuição por Tipo</div>
            {radarData.length === 0 ? (
              <p className="analytics-empty">Sem dados de foco por tipo de projeto.</p>
            ) : (
              <RadarChart data={radarData} dark={dark} />
            )}
          </div>
        </div>

        {/* ── Row: Livros por Mês + Tarefas ─────────────────────────────── */}
        <div className="analytics-grid-2">
          <div className="analytics-card">
            <div className="analytics-card-title">Livros Concluídos — Últimos 12 meses</div>
            {booksMonths.every(m => m.count === 0) ? (
              <p className="analytics-empty">
                Marque leituras como "Lido" na Biblioteca para ver o histórico.
              </p>
            ) : (
              <BarChart
                dark={dark}
                data={booksMonths.map(m => ({
                  label: fmtMonth(m.month),
                  value: m.count,
                }))}
              />
            )}
          </div>

          <div className="analytics-card">
            <div className="analytics-card-title">Tarefas do Planner — Últimos 30 dias</div>
            {data.tasks_total === 0 ? (
              <p className="analytics-empty">Sem tarefas no Planner ainda.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '8px 0' }}>
                {/* Donut-like arc */}
                <div style={{ display: 'flex', justifyContent: 'center' }}>
                  <svg viewBox="0 0 120 120" style={{ width: 120, height: 120 }}>
                    {(() => {
                      const pct  = data.tasks_done / data.tasks_total
                      const R    = 48
                      const circ = 2 * Math.PI * R
                      const off  = circ * (1 - pct)
                      const trackC = dark ? '#2A2418' : '#D8D0C0'
                      return (<>
                        <circle cx={60} cy={60} r={R} fill="none"
                          stroke={trackC} strokeWidth={10} />
                        <circle cx={60} cy={60} r={R} fill="none"
                          stroke={accent} strokeWidth={10}
                          strokeLinecap="round"
                          strokeDasharray={circ}
                          strokeDashoffset={off}
                          transform="rotate(-90 60 60)"
                          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
                        />
                        <text x={60} y={56} textAnchor="middle"
                          fontFamily="var(--font-mono)" fontSize={20}
                          fill={accent} fontWeight={300}>
                          {completionPct}%
                        </text>
                        <text x={60} y={70} textAnchor="middle"
                          fontFamily="var(--font-mono)" fontSize={8}
                          fill={ink2} letterSpacing={1}>
                          CONCLUÍDO
                        </text>
                      </>)
                    })()}
                  </svg>
                </div>
                <div style={{ display: 'flex', justifyContent: 'center', gap: 24 }}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, color: accent }}>
                      {data.tasks_done}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, letterSpacing: '0.1em' }}>
                      CONCLUÍDAS
                    </div>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, color: ink }}>
                      {data.tasks_total - data.tasks_done}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, letterSpacing: '0.1em' }}>
                      PENDENTES
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Row: Absorção Literária + Velocidade de Leitura ───────────── */}
        <div className="analytics-grid-2">
          <div className="analytics-card">
            <div className="analytics-card-title">Taxa de Absorção Literária — Últimos 12 meses</div>
            {absorptionMonths.every(m => m.added === 0 && m.completed === 0) ? (
              <p className="analytics-empty">Adicione leituras à Biblioteca para ver a absorção.</p>
            ) : (
              <GroupedBarChart
                dark={dark}
                data={absorptionMonths.map(m => ({
                  label: fmtMonth(m.month).slice(0, 3),
                  a: m.added,
                  b: m.completed,
                }))}
                labelA="Adicionados"
                labelB="Concluídos"
                colorA={dark ? '#6B8E6B' : '#5A7A5A'}
                colorB={accent}
              />
            )}
            {!absorptionMonths.every(m => m.added === 0 && m.completed === 0) && (() => {
              const totalAdded = absorptionMonths.reduce((s, m) => s + m.added, 0)
              const totalDone  = absorptionMonths.reduce((s, m) => s + m.completed, 0)
              const ratio = totalAdded > 0 ? Math.round((totalDone / totalAdded) * 100) : null
              return (
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, marginTop: 10 }}>
                  {totalDone} concluídos de {totalAdded} adicionados
                  {ratio !== null && ` · ${ratio}% absorvidos`}
                </p>
              )
            })()}
          </div>

          <div className="analytics-card">
            <div className="analytics-card-title">Velocidade de Leitura — Últimos 7 dias</div>
            {data!.reading_speed.length === 0 ? (
              <p className="analytics-empty">Registe sessões de leitura na Biblioteca para ver o ritmo.</p>
            ) : (<>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 14 }}>
                <span style={{ fontFamily: 'var(--font-display)', fontSize: 36, color: accent, lineHeight: 1 }}>
                  {avgPagesPerDay ?? '—'}
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2 }}>pág/dia (média)</span>
              </div>
              {/* Sparkline: pages per day */}
              {(() => {
                const days = Array.from({ length: 7 }, (_, i) => {
                  const d = new Date()
                  d.setDate(d.getDate() - (6 - i))
                  const key = d.toISOString().slice(0, 10)
                  const found = data!.reading_speed.find(r => r.date === key)
                  return { label: ['D-6','D-5','D-4','D-3','D-2','Ont.','Hoje'][i], value: found?.pages ?? 0 }
                })
                return (
                  <BarChart
                    dark={dark}
                    data={days.map(d => ({ label: d.label, value: d.value }))}
                    valueLabel={v => v > 0 ? String(v) : ''}
                  />
                )
              })()}
            </>)}
          </div>
        </div>

        {/* ── Row: Actividade por Dia da Semana + Fase Lunar ─────────────── */}
        <div className="analytics-grid-2">
          <div className="analytics-card">
            <div className="analytics-card-title">Actividade por Dia da Semana — Últimos 90 dias</div>
            {dowData.every(d => d.value === 0) ? (
              <p className="analytics-empty">Sem sessões de foco registadas.</p>
            ) : (
              <BarChart
                dark={dark}
                data={dowData}
                valueLabel={v => `${v}h`}
              />
            )}
            {!dowData.every(d => d.value === 0) && (() => {
              const best = dowData.reduce((a, b) => b.value > a.value ? b : a)
              return (
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, marginTop: 10 }}>
                  Dia mais produtivo: <span style={{ color: accent }}>{best.label}</span> ({best.value}h registadas)
                </p>
              )
            })()}
          </div>

          <div className="analytics-card">
            <div className="analytics-card-title">Produtividade por Fase Lunar</div>
            {lunarData.every(d => d.value === 0) ? (
              <p className="analytics-empty">
                Sem sessões de foco registadas. As fases serão calculadas automaticamente.
              </p>
            ) : (<>
              <BarChart
                dark={dark}
                data={lunarData.map(d => ({ label: d.label, value: d.value }))}
                valueLabel={v => `${v}h`}
              />
              {(() => {
                const best = lunarData.reduce((a, b) => b.value > a.value ? b : a)
                const phaseEmoji: Record<string, string> = {
                  'Nova': '🌑', 'Crescente': '🌒', 'Cheia': '🌕', 'Minguante': '🌘'
                }
                return (
                  <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, marginTop: 10 }}>
                    {phaseEmoji[best.label] ?? '●'} Pico na <span style={{ color: accent }}>Lua {best.label}</span> — {best.value}h registadas
                  </p>
                )
              })()}
            </>)}
          </div>
        </div>

      </>)}
    </div>
  )
}
