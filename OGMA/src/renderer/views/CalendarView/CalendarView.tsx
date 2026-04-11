import React, { useState } from 'react'
import { ViewRendererProps } from '../ProjectDashboard/ViewRenderer'
import { CosmosLayer } from '../../components/Cosmos/CosmosLayer'

const MONTH_NAMES = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                     'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
const DAY_NAMES   = ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb']

function pad(n: number) { return String(n).padStart(2, '0') }

// Trimestre: meses 0-2 = .1 ; 3-5 = .2 ; 6-8 = .3 ; 9-11 = .4
function trimesterLabel(year: number, month: number): string {
  return `${year}.${Math.floor(month / 3) + 1}`
}

export const CalendarView: React.FC<ViewRendererProps> = ({
  view, project, pages, properties, dark, onPageOpen,
}) => {
  const [year,  setYear]  = useState(new Date().getFullYear())
  const [month, setMonth] = useState(new Date().getMonth())

  const color  = project.color ?? '#8B7355'
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const bg     = dark ? '#1A1610' : '#F5F0E8'

  const prevMonth = () => {
    if (month === 0) { setYear(y => y - 1); setMonth(11) }
    else setMonth(m => m - 1)
  }
  const nextMonth = () => {
    if (month === 11) { setYear(y => y + 1); setMonth(0) }
    else setMonth(m => m + 1)
  }
  const goToday = () => {
    setMonth(new Date().getMonth())
    setYear(new Date().getFullYear())
  }

  const dateProp     = properties.find(p => p.id === view.date_property_id)
  const trimestreProp = project.project_type === 'academic'
    ? (properties.find(p => p.prop_key === 'trimestre') ?? properties.find(p => p.prop_key === 'ciclo'))
    : undefined
  const triLabel = trimestreProp?.prop_key === 'ciclo' ? 'Ciclo' : 'Tri.'

  // Trimestre do mês exibido (ex: "2025.2") — só relevante para projetos não-autodidata
  const currentTri = trimesterLabel(year, month)

  // Filtro por trimestre: null = todos
  const [triFilter, setTriFilter] = useState<string | null>(null)

  if (!dateProp) {
    return (
      <div style={{ padding: '40px 32px', color: ink2, fontStyle: 'italic', fontSize: 13,
        position: 'relative', minHeight: 140 }}>
        <CosmosLayer width={480} height={140} seed="cal_nodate" density="low" dark={dark}
          style={{ opacity: dark ? 0.2 : 0.09 }} />
        <p>Esta vista não tem uma propriedade de data configurada.</p>
        <p style={{ fontSize: 11, marginTop: 6 }}>
          Cria uma nova vista e define "Agrupar por data" — ou edita esta vista diretamente na base de dados.
        </p>
      </div>
    )
  }

  // Group pages by YYYY-MM-DD key (respeitando filtro de trimestre)
  const pagesByDate: Record<string, typeof pages> = {}
  pages.forEach(page => {
    const pv = page.prop_values?.find(v => v.property_id === dateProp.id)
    if (!pv?.value_date) return
    if (triFilter) {
      const pageTri = page.prop_values?.find(v => v.prop_key === trimestreProp?.prop_key)?.value_text
      if (pageTri !== triFilter) return
    }
    const key = pv.value_date.slice(0, 10)
    if (!pagesByDate[key]) pagesByDate[key] = []
    pagesByDate[key].push(page)
  })

  // Trimestres únicos presentes nas páginas (para botões de filtro)
  const availableTris = trimestreProp
    ? [...new Set(
        pages
          .map(p => p.prop_values?.find(v => v.prop_key === trimestreProp.prop_key)?.value_text)
          .filter(Boolean) as string[]
      )].sort()
    : []

  // Build 42-cell grid
  const firstWeekday  = new Date(year, month, 1).getDay()
  const daysInMonth   = new Date(year, month + 1, 0).getDate()
  const daysInPrevMon = new Date(year, month, 0).getDate()
  const todayStr      = new Date().toISOString().slice(0, 10)

  const cells: { dateStr: string; day: number; current: boolean }[] = []

  for (let i = firstWeekday - 1; i >= 0; i--) {
    const d = daysInPrevMon - i
    const m = month === 0 ? 11 : month - 1
    const y = month === 0 ? year - 1 : year
    cells.push({ dateStr: `${y}-${pad(m + 1)}-${pad(d)}`, day: d, current: false })
  }
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({ dateStr: `${year}-${pad(month + 1)}-${pad(d)}`, day: d, current: true })
  }
  const remaining = 42 - cells.length
  for (let d = 1; d <= remaining; d++) {
    const m = month === 11 ? 0 : month + 1
    const y = month === 11 ? year + 1 : year
    cells.push({ dateStr: `${y}-${pad(m + 1)}-${pad(d)}`, day: d, current: false })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

      {/* Navigation */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '8px 16px', borderBottom: `1px solid ${border}`, flexShrink: 0,
        background: bg, flexWrap: 'wrap', position: 'relative',
      }}>
        <CosmosLayer width={700} height={52} seed={`cal_nav_${project.id}`} density="low" dark={dark}
          style={{ opacity: dark ? 0.14 : 0.07 }} />
        <button className="btn btn-ghost btn-sm" onClick={prevMonth} style={{ color: ink2, fontSize: 16 }}>‹</button>
        <h3 style={{
          fontFamily: 'var(--font-display)', fontSize: 16, fontStyle: 'italic',
          color: ink, flex: 1, textAlign: 'center', fontWeight: 'normal', margin: 0,
        }}>
          {MONTH_NAMES[month]} {year}
        </h3>
        <button className="btn btn-ghost btn-sm" onClick={nextMonth} style={{ color: ink2, fontSize: 16 }}>›</button>
        <button className="btn btn-ghost btn-sm" onClick={goToday}
          style={{ color: ink2, fontFamily: 'var(--font-mono)', fontSize: 10 }}>
          hoje
        </button>

        {/* Indicador de período (projetos acadêmicos) */}
        {trimestreProp && trimestreProp.prop_key !== 'ciclo' && (
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, color: accent,
            letterSpacing: '0.06em', borderLeft: `1px solid ${border}`, paddingLeft: 10,
          }}>
            ◗ {currentTri}
          </span>
        )}

        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2,
          letterSpacing: '0.06em', borderLeft: `1px solid ${border}`, paddingLeft: 10,
        }}>
          via {dateProp.name}
        </span>
      </div>

      {/* Filtros de trimestre */}
      {trimestreProp && availableTris.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 5, flexShrink: 0,
          padding: '4px 16px', borderBottom: `1px solid ${border}`, background: bg,
          flexWrap: 'wrap',
        }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, letterSpacing: '0.08em' }}>
            {triLabel.toUpperCase()}
          </span>
          <button
            onClick={() => setTriFilter(null)}
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 9, padding: '1px 7px',
              borderRadius: 2, cursor: 'pointer', letterSpacing: '0.04em',
              border: `1px solid ${triFilter === null ? accent : border}`,
              background: triFilter === null ? accent + '22' : 'transparent',
              color: triFilter === null ? accent : ink2,
            }}
          >
            todos
          </button>
          {availableTris.map(tri => (
            <button
              key={tri}
              onClick={() => setTriFilter(tri === triFilter ? null : tri)}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 9, padding: '1px 7px',
                borderRadius: 2, cursor: 'pointer', letterSpacing: '0.04em',
                border: `1px solid ${triFilter === tri ? accent : border}`,
                background: triFilter === tri ? accent + '22' : 'transparent',
                color: triFilter === tri ? accent : ink2,
              }}
            >
              {tri}
            </button>
          ))}
        </div>
      )}

      {/* Day-of-week header */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)',
        borderBottom: `1px solid ${border}`, flexShrink: 0, background: bg,
      }}>
        {DAY_NAMES.map(d => (
          <div key={d} style={{
            padding: '5px 8px', textAlign: 'center',
            fontFamily: 'var(--font-mono)', fontSize: 9,
            letterSpacing: '0.1em', color: ink2,
          }}>
            {d}
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(7, 1fr)',
        gridAutoRows: 'minmax(88px, 1fr)',
        flex: 1, overflow: 'auto',
      }}>
        {cells.map((cell, i) => {
          const cellPages = pagesByDate[cell.dateStr] ?? []
          const isToday   = cell.dateStr === todayStr
          const isSunday  = i % 7 === 0
          return (
            <div key={i} style={{
              borderRight:  `1px solid ${border}`,
              borderBottom: `1px solid ${border}`,
              padding: '4px 5px',
              background: isToday
                ? (dark ? 'rgba(212,168,32,0.07)' : 'rgba(184,134,11,0.05)')
                : 'transparent',
              opacity: cell.current ? 1 : 0.38,
              overflow: 'hidden',
            }}>
              {/* Day number */}
              <div style={{ marginBottom: 3 }}>
                {isToday ? (
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 'bold',
                    background: accent, color: dark ? '#1A1610' : '#F5F0E8',
                    borderRadius: 2, padding: '0 4px',
                  }}>
                    {cell.day}
                  </span>
                ) : (
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: 10,
                    color: isSunday ? (dark ? '#C45A40' : '#8B3A2A') : ink2,
                  }}>
                    {cell.day}
                  </span>
                )}
              </div>

              {/* Page chips */}
              {cellPages.slice(0, 3).map(page => {
                const pageTri = trimestreProp
                  ? page.prop_values?.find(v => v.prop_key === trimestreProp.prop_key)?.value_text
                  : undefined
                return (
                  <button key={page.id} onClick={() => onPageOpen(page)} style={{
                    display: 'block', width: '100%',
                    background: color + '22', border: `1px solid ${color}44`,
                    borderRadius: 2, padding: '1px 5px', marginBottom: 2,
                    cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 9,
                    color: ink, textAlign: 'left',
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                    transition: 'background 80ms',
                  }}
                    title={pageTri ? `[${pageTri}] ${page.title}` : page.title}
                    onMouseEnter={e => (e.currentTarget.style.background = color + '44')}
                    onMouseLeave={e => (e.currentTarget.style.background = color + '22')}
                  >
                    {pageTri && (
                      <span style={{ color: accent, opacity: 0.8, marginRight: 3 }}>{pageTri}</span>
                    )}
                    {page.icon ?? '📄'} {page.title}
                  </button>
                )
              })}
              {cellPages.length > 3 && (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
                  +{cellPages.length - 3}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
