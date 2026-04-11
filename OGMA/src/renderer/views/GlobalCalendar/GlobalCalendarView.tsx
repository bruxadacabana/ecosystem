import React, { useState, useEffect, useCallback } from 'react'
import { fromIpc } from '../../types/errors'
import { useAppStore } from '../../store/useAppStore'

const db = () => (window as any).db

const MONTH_NAMES = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                     'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
const DAY_NAMES   = ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb']

function pad(n: number) { return String(n).padStart(2, '0') }

const EVENT_ICONS: Record<string, string> = {
  prova: '📝', trabalho: '📋', seminario: '🎙', defesa: '🎓',
  prazo: '⏰', reuniao: '👥', outro: '◦',
}
const EVENT_LABELS: Record<string, string> = {
  prova: 'Prova', trabalho: 'Trabalho', seminario: 'Seminário',
  defesa: 'Defesa', prazo: 'Prazo', reuniao: 'Reunião', outro: 'Outro',
}
const EVENT_COLORS: Record<string, string> = {
  prova: '#8B3A2A', trabalho: '#2C5F8A', seminario: '#6B4F72',
  defesa: '#b8860b', prazo: '#7A5C2E', reuniao: '#4A6741', outro: '#8B7355',
}

interface CalPage {
  id: number; title: string; icon: string | null
  project_id: number; value_date: string; prop_name: string
  project_name: string; project_color: string | null; project_icon: string | null
}

interface CalEvent {
  id: number; source: 'calendar' | 'planner'; title: string; description: string | null
  start_dt: string; end_dt: string | null; all_day: number
  event_type: string; color: string | null
  linked_page_id: number | null; linked_project_id: number | null
  page_title: string | null; project_name: string | null; project_color: string | null
}

interface Props {
  dark:       boolean
  onPageOpen: (projectId: number, pageId: number) => void
}

// ── EventForm ─────────────────────────────────────────────────────────────────

function EventForm({ dark, onSaved, onClose }: {
  dark: boolean; onSaved: () => void; onClose: () => void
}) {
  const { pushToast } = useAppStore()
  const [form, setForm] = useState({
    title: '', event_type: 'outro', start_dt: new Date().toISOString().slice(0, 10),
    all_day: true, time: '09:00', reminder_minutes: '' as string | number, description: '',
  })

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const accent = dark ? '#D4A820' : '#b8860b'
  const bg     = dark ? '#211D16' : '#EDE7D9'

  const inputStyle: React.CSSProperties = {
    background: 'none', border: `1px solid ${border}`, borderRadius: 2,
    padding: '4px 8px', fontSize: 11, color: ink, outline: 'none',
    fontFamily: 'var(--font-mono)', width: '100%', boxSizing: 'border-box',
  }

  const handleSave = async () => {
    if (!form.title.trim() || !form.start_dt) return
    const start_dt = form.all_day ? form.start_dt : `${form.start_dt}T${form.time}:00`
    const rem = form.reminder_minutes !== '' ? Number(form.reminder_minutes) : undefined
    const result = await fromIpc<any>(() => db().events.create({
      title: form.title.trim(),
      event_type: form.event_type,
      start_dt,
      all_day: form.all_day ? 1 : 0,
      description: form.description || null,
      reminder_minutes: rem,
    }), 'createGlobalEvent')
    if (result.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao criar evento', detail: result.error.message })
      return
    }
    onSaved()
  }

  return (
    <div style={{
      position: 'absolute', top: 40, right: 12, zIndex: 100,
      background: bg, border: `1px solid ${border}`, borderRadius: 3,
      boxShadow: `4px 4px 0 ${border}`, padding: 14, width: 320,
      display: 'flex', flexDirection: 'column', gap: 8,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.14em', color: ink2 }}>
          NOVA ACTIVIDADE
        </span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: ink2, fontSize: 16, lineHeight: 1, padding: 0 }}>×</button>
      </div>

      {/* Tipo */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {Object.entries(EVENT_ICONS).map(([type, icon]) => (
          <button key={type} onClick={() => setForm(f => ({ ...f, event_type: type }))}
            title={EVENT_LABELS[type]}
            style={{
              fontSize: 10, padding: '2px 6px', borderRadius: 2, cursor: 'pointer',
              border: `1px solid ${form.event_type === type ? EVENT_COLORS[type] : border}`,
              background: form.event_type === type ? EVENT_COLORS[type] + '22' : 'transparent',
              color: form.event_type === type ? EVENT_COLORS[type] : ink2,
              fontFamily: 'var(--font-mono)',
            }}>
            {icon} {EVENT_LABELS[type]}
          </button>
        ))}
      </div>

      <input type="text" placeholder="Título…" value={form.title}
        onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
        autoFocus style={inputStyle} />

      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <input type="date" value={form.start_dt}
          onChange={e => setForm(f => ({ ...f, start_dt: e.target.value }))}
          style={{ ...inputStyle, width: 'auto', colorScheme: dark ? 'dark' : 'light' }} />
        <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: ink2, cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
          <input type="checkbox" checked={form.all_day}
            onChange={e => setForm(f => ({ ...f, all_day: e.target.checked }))} />
          dia inteiro
        </label>
        {!form.all_day && (
          <input type="time" value={form.time}
            onChange={e => setForm(f => ({ ...f, time: e.target.value }))}
            style={{ ...inputStyle, width: 'auto', colorScheme: dark ? 'dark' : 'light' }} />
        )}
      </div>

      <select value={form.reminder_minutes}
        onChange={e => setForm(f => ({ ...f, reminder_minutes: e.target.value }))}
        style={{ ...inputStyle }}>
        <option value="">Sem lembrete</option>
        <option value={15}>15 min antes</option>
        <option value={30}>30 min antes</option>
        <option value={60}>1 hora antes</option>
        <option value={1440}>1 dia antes</option>
        <option value={2880}>2 dias antes</option>
      </select>

      <div style={{ display: 'flex', gap: 6 }}>
        <button onClick={handleSave} style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.08em',
          padding: '4px 14px', border: `1px solid ${accent}`, borderRadius: 2,
          color: accent, background: 'none', cursor: 'pointer',
        }}>Guardar</button>
        <button onClick={onClose} style={{
          fontFamily: 'var(--font-mono)', fontSize: 10,
          padding: '4px 10px', border: `1px solid ${border}`, borderRadius: 2,
          color: ink2, background: 'none', cursor: 'pointer',
        }}>Cancelar</button>
      </div>
    </div>
  )
}

// ── GlobalCalendarView ────────────────────────────────────────────────────────

export function GlobalCalendarView({ dark, onPageOpen }: Props) {
  const [tab,      setTab]      = useState<'calendar' | 'agenda' | 'reminders'>('calendar')
  const [year,     setYear]     = useState(new Date().getFullYear())
  const [month,    setMonth]    = useState(new Date().getMonth())
  const [pages,    setPages]    = useState<CalPage[]>([])
  const [events,   setEvents]   = useState<CalEvent[]>([])
  const [upcoming, setUpcoming] = useState<CalEvent[]>([])
  const [reminders,setReminders]= useState<any[]>([])
  const [showForm, setShowForm] = useState(false)

  const { pushToast } = useAppStore()

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const bg     = dark ? '#1A1610' : '#F5F0E8'

  const loadMonth = useCallback(() => {
    fromIpc<CalPage[]>(() => db().calendar.pagesForMonth(year, month), 'calPages')
      .then(r => r.match(data => setPages(data), _e => {}))
    fromIpc<CalEvent[]>(() => db().events.listForMonth(year, month), 'calEvents')
      .then(r => r.match(data => setEvents(data), _e => {}))
  }, [year, month])

  const loadAgenda = useCallback(() => {
    fromIpc<CalEvent[]>(() => db().events.listUpcoming(60), 'upcoming')
      .then(r => r.match(data => setUpcoming(data), _e => {}))
  }, [])

  const loadReminders = useCallback(() => {
    fromIpc<any[]>(() => db().reminders.list(true), 'remindersList')
      .then(r => r.match(data => setReminders(data), _e => {}))
  }, [])

  useEffect(() => { loadMonth() },    [loadMonth])
  useEffect(() => { loadAgenda() },   [loadAgenda])
  useEffect(() => { loadReminders() }, [loadReminders])

  const prevMonth = () => {
    if (month === 0) { setYear(y => y - 1); setMonth(11) }
    else setMonth(m => m - 1)
  }
  const nextMonth = () => {
    if (month === 11) { setYear(y => y + 1); setMonth(0) }
    else setMonth(m => m + 1)
  }

  const handleDismiss = async (id: number) => {
    await fromIpc<any>(() => db().reminders.dismiss(id), 'dismissReminder')
    loadReminders()
  }
  const handleDeleteReminder = async (id: number) => {
    await fromIpc<any>(() => db().reminders.delete(id), 'deleteReminder')
    loadReminders()
  }

  // Agrupar páginas por data
  const pagesByDate: Record<string, CalPage[]> = {}
  pages.forEach(e => {
    const key = e.value_date.slice(0, 10)
    if (!pagesByDate[key]) pagesByDate[key] = []
    pagesByDate[key].push(e)
  })

  // Agrupar eventos por data
  const eventsByDate: Record<string, CalEvent[]> = {}
  events.forEach(e => {
    const key = e.start_dt.slice(0, 10)
    if (!eventsByDate[key]) eventsByDate[key] = []
    eventsByDate[key].push(e)
  })

  // Grid de 42 células
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

  // Agenda: agrupar por data
  const agendaByDate: Record<string, CalEvent[]> = {}
  upcoming.forEach(ev => {
    const key = ev.start_dt.slice(0, 10)
    if (!agendaByDate[key]) agendaByDate[key] = []
    agendaByDate[key].push(ev)
  })
  const agendaDates = Object.keys(agendaByDate).sort()

  const pendingReminders = reminders.filter(r => !r.is_dismissed)
  const dismissedReminders = reminders.filter(r => r.is_dismissed)

  // Legenda de projetos deste mês
  const projectsThisMonth = Array.from(
    new Map(pages.map(e => [e.project_id, { id: e.project_id, name: e.project_name, color: e.project_color }])).values()
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', position: 'relative' }}>

      {/* Barra superior */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '8px 16px', borderBottom: `1px solid ${border}`, flexShrink: 0, background: bg,
      }}>

        {/* Tabs */}
        {(['calendar', 'agenda', 'reminders'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em',
            padding: '3px 10px', border: `1px solid ${tab === t ? accent : border}`,
            borderRadius: 2, background: tab === t ? accent + '22' : 'transparent',
            color: tab === t ? accent : ink2, cursor: 'pointer',
          }}>
            {t === 'calendar' ? '☽ CALENDÁRIO' : t === 'agenda' ? '≡ AGENDA' : '◎ LEMBRETES'}
            {t === 'reminders' && pendingReminders.length > 0 && (
              <span style={{ marginLeft: 5, background: '#8B3A2A', color: '#F5F0E8',
                borderRadius: 8, padding: '0 5px', fontSize: 8 }}>
                {pendingReminders.length}
              </span>
            )}
          </button>
        ))}

        <div style={{ flex: 1 }} />

        {/* Navegação mês (só no tab calendário) */}
        {tab === 'calendar' && (
          <>
            <button className="btn btn-ghost btn-sm" onClick={prevMonth}
              style={{ color: ink2, fontSize: 16 }}>‹</button>
            <span style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontStyle: 'italic',
              color: ink, minWidth: 160, textAlign: 'center' }}>
              {MONTH_NAMES[month]} {year}
            </span>
            <button className="btn btn-ghost btn-sm" onClick={nextMonth}
              style={{ color: ink2, fontSize: 16 }}>›</button>
            <button className="btn btn-ghost btn-sm"
              onClick={() => { setMonth(new Date().getMonth()); setYear(new Date().getFullYear()) }}
              style={{ color: ink2, fontFamily: 'var(--font-mono)', fontSize: 10 }}>
              hoje
            </button>
          </>
        )}

        {/* Legenda */}
        {tab === 'calendar' && projectsThisMonth.length > 0 && (
          <div style={{ display: 'flex', gap: 6, alignItems: 'center',
            borderLeft: `1px solid ${border}`, paddingLeft: 10, flexWrap: 'wrap' }}>
            {projectsThisMonth.map(p => (
              <span key={p.id} style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: p.color ?? ink2,
                display: 'flex', alignItems: 'center', gap: 3 }}>
                <span style={{ display: 'inline-block', width: 6, height: 6,
                  borderRadius: '50%', background: p.color ?? ink2 }} />
                {p.name}
              </span>
            ))}
          </div>
        )}

        {/* Botão nova actividade */}
        <button className="btn btn-sm" onClick={() => setShowForm(f => !f)}
          style={{ borderColor: accent, color: accent, fontFamily: 'var(--font-mono)', fontSize: 10 }}>
          + Actividade
        </button>
      </div>

      {/* EventForm popup */}
      {showForm && (
        <EventForm dark={dark}
          onSaved={() => { setShowForm(false); loadMonth(); loadAgenda() }}
          onClose={() => setShowForm(false)} />
      )}

      {/* ── Tab: Calendário ── */}
      {tab === 'calendar' && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)',
            borderBottom: `1px solid ${border}`, flexShrink: 0, background: bg }}>
            {DAY_NAMES.map(d => (
              <div key={d} style={{ padding: '5px 8px', textAlign: 'center',
                fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em', color: ink2 }}>{d}</div>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)',
            gridAutoRows: 'minmax(88px, 1fr)', flex: 1, overflow: 'auto' }}>
            {cells.map((cell, i) => {
              const cellPages  = pagesByDate[cell.dateStr] ?? []
              const cellEvents = eventsByDate[cell.dateStr] ?? []
              const isToday    = cell.dateStr === todayStr
              const isSunday   = i % 7 === 0
              const total = cellPages.length + cellEvents.length

              return (
                <div key={i} style={{
                  borderRight: `1px solid ${border}`, borderBottom: `1px solid ${border}`,
                  padding: '4px 5px',
                  background: isToday ? (dark ? 'rgba(212,168,32,0.07)' : 'rgba(184,134,11,0.05)') : 'transparent',
                  opacity: cell.current ? 1 : 0.35, overflow: 'hidden',
                }}>
                  <div style={{ marginBottom: 3 }}>
                    {isToday ? (
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 'bold',
                        background: accent, color: dark ? '#1A1610' : '#F5F0E8',
                        borderRadius: 2, padding: '0 4px' }}>{cell.day}</span>
                    ) : (
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10,
                        color: isSunday ? (dark ? '#C45A40' : '#8B3A2A') : ink2 }}>{cell.day}</span>
                    )}
                  </div>

                  {/* Chips de páginas */}
                  {cellPages.slice(0, 2).map(entry => {
                    const color = entry.project_color ?? '#8B7355'
                    return (
                      <button key={`p_${entry.id}_${entry.prop_name}`}
                        onClick={() => onPageOpen(entry.project_id, entry.id)}
                        title={`${entry.title} · ${entry.project_name}`}
                        style={{
                          display: 'block', width: '100%',
                          background: color + '22', border: `1px solid ${color}44`,
                          borderLeft: `3px solid ${color}`, borderRadius: 2,
                          padding: '1px 4px', marginBottom: 2,
                          cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 9,
                          color: ink, textAlign: 'left',
                          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                          transition: 'background 80ms',
                        }}
                        onMouseEnter={e => (e.currentTarget.style.background = color + '44')}
                        onMouseLeave={e => (e.currentTarget.style.background = color + '22')}
                      >
                        {entry.icon ?? '◦'} {entry.title}
                      </button>
                    )
                  })}

                  {/* Chips de eventos */}
                  {cellEvents.slice(0, total <= 3 ? 2 : 1).map(ev => {
                    const color = EVENT_COLORS[ev.event_type ?? 'outro'] ?? '#8B7355'
                    return (
                      <div key={`${ev.source ?? 'c'}_${ev.id}`}
                        title={`${EVENT_LABELS[ev.event_type ?? 'outro']}: ${ev.title}`}
                        style={{
                          display: 'block', width: '100%',
                          background: color + '18', border: `1px solid ${color}55`,
                          borderLeft: `3px solid ${color}`, borderRadius: 2,
                          padding: '1px 4px', marginBottom: 2,
                          fontFamily: 'var(--font-mono)', fontSize: 9,
                          color: ink, textAlign: 'left',
                          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                        }}>
                        {EVENT_ICONS[ev.event_type ?? 'outro']} {ev.title}
                      </div>
                    )
                  })}

                  {total > 3 && (
                    <div style={{ fontSize: 9, color: ink2, fontFamily: 'var(--font-mono)', padding: '0 3px' }}>
                      +{total - 3} mais
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}

      {/* ── Tab: Agenda ── */}
      {tab === 'agenda' && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 24px 40px' }}>
          {agendaDates.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 48, color: ink2, fontStyle: 'italic', fontSize: 13 }}>
              Sem actividades nos próximos 60 dias.
            </div>
          ) : agendaDates.map(date => {
            const dateObj = new Date(date + 'T12:00:00')
            const isToday = date === todayStr
            const label   = dateObj.toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })
            return (
              <div key={date} style={{ marginBottom: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.12em',
                    color: isToday ? accent : ink2, textTransform: 'uppercase',
                  }}>
                    {label}{isToday ? ' · HOJE' : ''}
                  </span>
                  <div style={{ flex: 1, height: 1, background: border }} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {agendaByDate[date].map(ev => {
                    const color = EVENT_COLORS[ev.event_type ?? 'outro'] ?? '#8B7355'
                    const time  = !ev.all_day && ev.start_dt.includes('T')
                      ? ev.start_dt.slice(11, 16) : null
                    return (
                      <div key={`${ev.source ?? 'c'}_${ev.id}`} style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '8px 12px', border: `1px solid ${color}44`,
                        borderLeft: `4px solid ${color}`, borderRadius: 2,
                        background: color + '0E',
                      }}>
                        <span style={{ fontSize: 18, flexShrink: 0 }}>
                          {EVENT_ICONS[ev.event_type ?? 'outro']}
                        </span>
                        <div style={{ flex: 1, overflow: 'hidden' }}>
                          <div style={{ fontFamily: 'var(--font-display)', fontSize: 14,
                            fontStyle: 'italic', color: ink }}>
                            {ev.title}
                          </div>
                          <div style={{ display: 'flex', gap: 8, marginTop: 2 }}>
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9,
                              color, letterSpacing: '0.08em' }}>
                              {EVENT_LABELS[ev.event_type ?? 'outro']}
                            </span>
                            {ev.project_name && (
                              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
                                {ev.project_name}
                              </span>
                            )}
                            {ev.page_title && (
                              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
                                · {ev.page_title}
                              </span>
                            )}
                          </div>
                        </div>
                        {time && (
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11,
                            color, flexShrink: 0 }}>{time}</span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── Tab: Lembretes ── */}
      {tab === 'reminders' && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 24px 40px' }}>
          {pendingReminders.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.14em',
                color: '#8B3A2A', marginBottom: 10 }}>
                PENDENTES
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {pendingReminders.map(r => (
                  <div key={r.id} style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '8px 12px', border: `1px solid ${'#8B3A2A'}55`,
                    borderLeft: `4px solid ${'#8B3A2A'}`, borderRadius: 2,
                    background: '#8B3A2A0E',
                  }}>
                    <span style={{ fontSize: 16 }}>{EVENT_ICONS[r.event_type ?? 'outro']}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontFamily: 'var(--font-display)', fontSize: 13,
                        fontStyle: 'italic', color: ink }}>{r.title}</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, marginTop: 2 }}>
                        {r.trigger_at?.replace('T', ' ').slice(0, 16)}
                        {r.event_start && ` · Evento: ${r.event_start.slice(0, 10)}`}
                      </div>
                    </div>
                    <button onClick={() => handleDismiss(r.id)} style={{
                      fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.06em',
                      padding: '2px 8px', border: `1px solid ${'#4A6741'}`, borderRadius: 2,
                      color: '#4A6741', background: 'none', cursor: 'pointer',
                    }}>✓ Ok</button>
                    <button onClick={() => handleDeleteReminder(r.id)} style={{
                      background: 'none', border: 'none', cursor: 'pointer', color: ink2, fontSize: 14, padding: 0
                    }}>×</button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {dismissedReminders.length > 0 && (
            <div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.14em',
                color: ink2, marginBottom: 10 }}>
                CONCLUÍDOS
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {dismissedReminders.slice(0, 20).map(r => (
                  <div key={r.id} style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '6px 10px', border: `1px solid ${border}`, borderRadius: 2, opacity: 0.5,
                  }}>
                    <span style={{ fontSize: 13 }}>{EVENT_ICONS[r.event_type ?? 'outro']}</span>
                    <span style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2 }}>{r.title}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
                      {r.trigger_at?.slice(0, 10)}
                    </span>
                    <button onClick={() => handleDeleteReminder(r.id)} style={{
                      background: 'none', border: 'none', cursor: 'pointer', color: ink2, fontSize: 13, padding: 0
                    }}>×</button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {reminders.length === 0 && (
            <div style={{ textAlign: 'center', padding: 48, color: ink2, fontStyle: 'italic', fontSize: 13 }}>
              Nenhum lembrete registado.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
