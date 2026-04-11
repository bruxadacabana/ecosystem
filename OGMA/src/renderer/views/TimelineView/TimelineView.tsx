import React, { useRef } from 'react'
import { Page } from '../../types'
import { ViewRendererProps } from '../ProjectDashboard/ViewRenderer'

const DAY_W    = 28   // px per day
const LEFT_W   = 210  // px for the page name column
const ROW_H    = 36   // px per row
const HEADER_H = 40   // px for the month/day header

const MONTH_SHORT = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']

type PageWithDates = Page & { startDate: Date; endDate: Date; isSingle: boolean }

export const TimelineView: React.FC<ViewRendererProps> = ({
  view, project, pages, properties, dark, onPageOpen, onNewPage,
}) => {
  const scrollRef = useRef<HTMLDivElement>(null)
  const headRef   = useRef<HTMLDivElement>(null)

  const color  = project.color ?? '#8B7355'
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const bg     = dark ? '#1A1610' : '#F5F0E8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  const dateProp = properties.find(p => p.id === view.date_property_id)

  // Sync horizontal scroll between header and rows
  const onRowsScroll = (e: React.UIEvent<HTMLDivElement>) => {
    if (headRef.current) headRef.current.scrollLeft = e.currentTarget.scrollLeft
  }

  if (!dateProp) {
    return (
      <div style={{ padding: '40px 32px', color: ink2, fontStyle: 'italic', fontSize: 13 }}>
        <p>Esta vista não tem uma propriedade de data configurada.</p>
        <p style={{ fontSize: 11, marginTop: 6 }}>
          Cria a vista com "Agrupar por data" definido.
        </p>
      </div>
    )
  }

  // Collect pages that have a date value
  const pagesWithDates: PageWithDates[] = []
  pages.forEach(page => {
    const pv = page.prop_values?.find(v => v.property_id === dateProp.id)
    if (!pv?.value_date) return
    const startDate = new Date(pv.value_date + 'T00:00:00')
    const endDate   = pv.value_date2
      ? new Date(pv.value_date2 + 'T00:00:00')
      : startDate
    pagesWithDates.push({ ...page, startDate, endDate, isSingle: !pv.value_date2 })
  })

  // Pages without dates (shown in list at the bottom)
  const pagesNoDate = pages.filter(p =>
    !pagesWithDates.find(pd => pd.id === p.id)
  )

  if (pagesWithDates.length === 0) {
    return (
      <div style={{ padding: '40px 32px', color: ink2, fontStyle: 'italic', fontSize: 13,
        display: 'flex', flexDirection: 'column', gap: 12 }}>
        <p>Nenhuma página com data definida via "{dateProp.name}".</p>
        <button className="btn btn-sm" onClick={onNewPage} style={{ borderColor: color, color, alignSelf: 'flex-start' }}>
          + Nova página
        </button>
      </div>
    )
  }

  // Date range: min/max + 3 days padding each side
  const allDates = pagesWithDates.flatMap(p => [p.startDate.getTime(), p.endDate.getTime()])
  const rangeStart = new Date(Math.min(...allDates)); rangeStart.setDate(rangeStart.getDate() - 3)
  const rangeEnd   = new Date(Math.max(...allDates)); rangeEnd.setDate(rangeEnd.getDate() + 4)

  const totalDays  = Math.ceil((rangeEnd.getTime() - rangeStart.getTime()) / 86400000)
  const totalWidth = totalDays * DAY_W

  const dayOffset = (date: Date) =>
    Math.floor((date.getTime() - rangeStart.getTime()) / 86400000)

  const todayOffset = dayOffset(new Date())

  // Month markers
  const monthMarkers: { left: number; label: string; widthDays: number }[] = []
  let cur = new Date(rangeStart.getFullYear(), rangeStart.getMonth(), 1)
  while (cur < rangeEnd) {
    const startOff  = Math.max(0, dayOffset(cur))
    const nextMonth = new Date(cur.getFullYear(), cur.getMonth() + 1, 1)
    const endOff    = Math.min(totalDays, dayOffset(nextMonth))
    monthMarkers.push({
      left:      startOff * DAY_W,
      label:     `${MONTH_SHORT[cur.getMonth()]} ${cur.getFullYear()}`,
      widthDays: endOff - startOff,
    })
    cur = nextMonth
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

      {/* Sticky header (synced to rows scroll) */}
      <div ref={headRef} style={{
        overflow: 'hidden', flexShrink: 0,
        borderBottom: `2px solid ${border}`, background: bg,
      }}>
        <div style={{ display: 'flex', minWidth: LEFT_W + totalWidth }}>
          {/* Left corner */}
          <div style={{
            width: LEFT_W, flexShrink: 0, padding: '0 16px',
            display: 'flex', alignItems: 'center',
            fontFamily: 'var(--font-mono)', fontSize: 9,
            letterSpacing: '0.12em', color: ink2, textTransform: 'uppercase',
            borderRight: `1px solid ${border}`, height: HEADER_H,
          }}>
            {dateProp.name}
          </div>

          {/* Month labels */}
          <div style={{ position: 'relative', width: totalWidth, height: HEADER_H, flexShrink: 0 }}>
            {monthMarkers.map((m, i) => (
              <div key={i} style={{
                position: 'absolute', left: m.left, top: 0,
                width: m.widthDays * DAY_W,
                height: '100%', borderRight: `1px solid ${border}`,
                display: 'flex', alignItems: 'center', paddingLeft: 6, overflow: 'hidden',
              }}>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 10,
                  color: accent, letterSpacing: '0.06em', whiteSpace: 'nowrap',
                }}>
                  {m.label}
                </span>
              </div>
            ))}
            {/* Today marker */}
            {todayOffset >= 0 && todayOffset <= totalDays && (
              <div style={{
                position: 'absolute', left: todayOffset * DAY_W - 1, top: 0,
                width: 2, height: '100%', background: accent, opacity: 0.7,
                pointerEvents: 'none',
              }} />
            )}
          </div>
        </div>
      </div>

      {/* Rows — scroll both x and y */}
      <div ref={scrollRef} style={{ flex: 1, overflow: 'auto' }} onScroll={onRowsScroll}>
        <div style={{ minWidth: LEFT_W + totalWidth }}>

          {pagesWithDates.map((page, i) => {
            const startOff = dayOffset(page.startDate)
            const endOff   = dayOffset(page.endDate)
            const barLeft  = startOff * DAY_W
            const barWidth = page.isSingle
              ? ROW_H - 12                          // diamond/circle for single date
              : Math.max(DAY_W, (endOff - startOff + 1) * DAY_W)

            return (
              <div key={page.id} style={{
                display: 'flex', alignItems: 'center',
                height: ROW_H, borderBottom: `1px solid ${border}`,
              }}>
                {/* Page name */}
                <div style={{
                  width: LEFT_W, flexShrink: 0, padding: '0 10px 0 14px',
                  display: 'flex', alignItems: 'center', gap: 6,
                  overflow: 'hidden', borderRight: `1px solid ${border}`,
                  height: '100%', background: i % 2 === 0 ? 'transparent' : (dark ? 'rgba(232,223,200,0.015)' : 'rgba(44,36,22,0.015)'),
                }}>
                  <span style={{ fontSize: 12, flexShrink: 0 }}>{page.icon ?? '📄'}</span>
                  <span style={{
                    fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 12,
                    color: ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>
                    {page.title}
                  </span>
                </div>

                {/* Bar area */}
                <div style={{ position: 'relative', width: totalWidth, flexShrink: 0, height: '100%' }}>
                  {/* Subtle row stripe */}
                  {i % 2 !== 0 && (
                    <div style={{ position: 'absolute', inset: 0,
                      background: dark ? 'rgba(232,223,200,0.015)' : 'rgba(44,36,22,0.015)',
                      pointerEvents: 'none' }} />
                  )}
                  {/* Today line */}
                  {todayOffset >= 0 && todayOffset <= totalDays && (
                    <div style={{
                      position: 'absolute', left: todayOffset * DAY_W - 1, top: 0,
                      width: 2, height: '100%', background: accent, opacity: 0.25,
                      pointerEvents: 'none',
                    }} />
                  )}
                  {/* Bar / milestone */}
                  <button onClick={() => onPageOpen(page)} title={page.title} style={{
                    position: 'absolute',
                    left:   barLeft,
                    top:    page.isSingle ? 8 : 8,
                    width:  barWidth,
                    height: ROW_H - 16,
                    background: color + 'CC',
                    border: `1px solid ${color}`,
                    borderRadius: page.isSingle ? '50%' : 3,
                    cursor: 'pointer',
                    display: 'flex', alignItems: 'center',
                    padding: page.isSingle ? 0 : '0 6px',
                    overflow: 'hidden', transition: 'background 80ms',
                  }}
                    onMouseEnter={e => (e.currentTarget.style.background = color)}
                    onMouseLeave={e => (e.currentTarget.style.background = color + 'CC')}
                  >
                    {!page.isSingle && barWidth > 50 && (
                      <span style={{
                        fontFamily: 'var(--font-mono)', fontSize: 8,
                        color: ink, whiteSpace: 'nowrap',
                        overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>
                        {page.title}
                      </span>
                    )}
                  </button>
                </div>
              </div>
            )
          })}

          {/* Pages without dates */}
          {pagesNoDate.length > 0 && (
            <div style={{ padding: '8px 14px', borderTop: `1px dashed ${border}` }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9,
                letterSpacing: '0.1em', color: ink2, textTransform: 'uppercase', marginBottom: 6 }}>
                Sem data
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {pagesNoDate.map(p => (
                  <button key={p.id} onClick={() => onPageOpen(p)} style={{
                    background: cardBg, border: `1px solid ${border}`,
                    borderRadius: 2, padding: '3px 8px', cursor: 'pointer',
                    fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 12,
                    color: ink, display: 'flex', alignItems: 'center', gap: 5,
                  }}>
                    <span>{p.icon ?? '📄'}</span> {p.title}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Add page */}
          <div style={{ padding: '8px 14px', borderTop: `1px solid ${border}` }}>
            <button className="btn btn-ghost btn-sm" onClick={onNewPage}
              style={{ color: ink2, fontSize: 11 }}>
              + Nova página
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
