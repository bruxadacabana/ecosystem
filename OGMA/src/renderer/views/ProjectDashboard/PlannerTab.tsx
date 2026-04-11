import React, { useCallback, useEffect, useRef, useState } from 'react'
import { fromIpc } from '../../types/errors'
import { useAppStore } from '../../store/useAppStore'
import { StudyTimerTab, ActiveTimerBlock } from './StudyTimerTab'

const db = () => (window as any).db

// ── Tipos ─────────────────────────────────────────────────────────────────────

interface PlannedTask {
  id:              number
  project_id:      number
  page_id:         number | null
  title:           string
  task_type:       string
  due_date:        string
  estimated_hours: number
  status:          string
  done_hours:      number
  priority:        string
  spaced_review:   number
  parent_task_id:  number | null
  page_title?:     string
  page_icon?:      string
}

interface WorkBlock {
  id:            number
  task_id:       number
  date:          string
  planned_hours: number
  logged_hours:  number
  status:        string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const TYPE_ICONS: Record<string, string> = {
  aula: '📚', atividade: '📋', prova: '📝', leitura: '📖',
  trabalho: '📋', seminario: '🎙', defesa: '🎓', prazo: '⏰', reuniao: '👥', outro: '◦',
}
const TYPE_LABELS: Record<string, string> = {
  aula: 'Aula', atividade: 'Atividade', prova: 'Prova', leitura: 'Leitura',
  trabalho: 'Trabalho', seminario: 'Seminário', defesa: 'Defesa', prazo: 'Prazo', reuniao: 'Reunião', outro: 'Outro',
}
const STATUS_COLORS: Record<string, string> = {
  pending: '#8B7355', in_progress: '#b8860b', completed: '#4A6741', overdue: '#8B3A2A',
}
const STATUS_LABELS: Record<string, string> = {
  pending: 'Pendente', in_progress: 'Em andamento', completed: 'Concluída', overdue: 'Atrasada',
}
const PRIORITY_COLORS: Record<string, string> = {
  low: '#8B7355', medium: '#2C5F8A', high: '#b8860b', urgent: '#8B3A2A',
}
const PRIORITY_LABELS: Record<string, string> = {
  low: 'Baixa', medium: 'Média', high: 'Alta', urgent: 'Urgente',
}

function isoToDisplay(iso: string): string {
  const d = new Date(iso.slice(0, 10) + 'T12:00:00')
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })
}

function daysUntil(iso: string): number {
  const today = new Date(); today.setHours(0,0,0,0)
  const due   = new Date(iso.slice(0, 10) + 'T12:00:00'); due.setHours(0,0,0,0)
  return Math.round((due.getTime() - today.getTime()) / 86400000)
}

function weekDates(offset = 0): string[] {
  const today = new Date(); today.setHours(0,0,0,0)
  const day   = today.getDay()
  const monday = new Date(today.getTime() - (day === 0 ? 6 : day - 1) * 86400000)
  monday.setDate(monday.getDate() + offset * 7)
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(monday.getTime() + i * 86400000)
    return d.toISOString().slice(0, 10)
  })
}

const DAY_NAMES = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']

// ── Modal de tarefa ───────────────────────────────────────────────────────────

function TaskModal({ dark, projectId, pages, task, onSave, onClose }: {
  dark:      boolean
  projectId: number
  pages:     any[]
  task:      PlannedTask | null
  onSave:    (t: PlannedTask) => void
  onClose:   () => void
}) {
  const { pushToast } = useAppStore()
  const [title,       setTitle]       = useState(task?.title              ?? '')
  const [taskType,    setTaskType]    = useState(task?.task_type          ?? 'atividade')
  const [dueDate,     setDueDate]     = useState(task?.due_date?.slice(0,10) ?? '')
  const [hours,       setHours]       = useState(String(task?.estimated_hours ?? 1))
  const [pageId,      setPageId]      = useState<number | null>(task?.page_id ?? null)
  const [createPg,    setCreatePg]    = useState(false)
  const [priority,    setPriority]    = useState(task?.priority           ?? 'medium')
  const [spacedReview,setSpacedReview]= useState((task?.spaced_review ?? 0) === 1)
  const [saving,      setSaving]      = useState(false)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const bg     = dark ? '#211D16' : '#EDE7D9'
  const accent = dark ? '#D4A820' : '#b8860b'

  const handleSave = async () => {
    if (!title.trim() || !dueDate) {
      pushToast({ kind: 'error', title: 'Preencha título e prazo.' })
      return
    }
    if (!pageId && !createPg) {
      pushToast({ kind: 'error', title: 'Página obrigatória', detail: 'Vincule a uma página/disciplina do projeto.' })
      return
    }
    setSaving(true)
    try {
      let linkedPageId = pageId
      if (createPg) {
        const r = await fromIpc<any>(
          () => db().pages.create({ project_id: projectId, title: title.trim(), icon: TYPE_ICONS[taskType] ?? '◦' }),
          'createPage'
        )
        if (r.isOk()) linkedPageId = r.value.id
      }
      const payload: any = {
        ...(task ? { id: task.id } : {}),
        project_id:      projectId,
        page_id:         linkedPageId,
        title:           title.trim(),
        task_type:       taskType,
        due_date:        dueDate,
        estimated_hours: parseFloat(hours) || 1,
        priority,
        spaced_review:   spacedReview ? 1 : 0,
      }
      const result = await fromIpc<PlannedTask>(
        () => task ? db().planner.updateTask(payload) : db().planner.createTask(payload),
        'saveTask'
      )
      if (result.isOk()) { onSave(result.value); onClose() }
      else pushToast({ kind: 'error', title: 'Erro ao guardar', detail: result.error.message })
    } finally { setSaving(false) }
  }

  const inp = {
    background: 'transparent', border: `1px solid ${border}`, borderRadius: 2,
    padding: '6px 10px', color: ink, fontFamily: 'var(--font-body)', fontSize: 13, outline: 'none',
  } as const

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 2000,
      background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={{
        background: bg, border: `1px solid ${border}`, borderRadius: 4,
        padding: 28, width: 440, maxWidth: '90vw', display: 'flex', flexDirection: 'column', gap: 14,
      }}>
        <h3 style={{ margin: 0, fontFamily: 'var(--font-display)', color: ink, fontSize: 18 }}>
          {task ? 'Editar tarefa' : 'Nova tarefa'}
        </h3>

        {/* Título */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, letterSpacing: '0.12em' }}>TÍTULO</label>
          <input style={inp} value={title} onChange={e => setTitle(e.target.value)}
            placeholder="Ex: Cálculo — Integrais" autoFocus onKeyDown={e => e.key === 'Enter' && handleSave()} />
        </div>

        {/* Página vinculada (obrigatória) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, letterSpacing: '0.12em' }}>
            PÁGINA / DISCIPLINA *
          </label>
          <select
            value={createPg ? '__new__' : (pageId ?? '__none__')}
            onChange={e => {
              if (e.target.value === '__new__') { setCreatePg(true); setPageId(null) }
              else if (e.target.value === '__none__') { setCreatePg(false); setPageId(null) }
              else { setCreatePg(false); setPageId(Number(e.target.value)) }
            }}
            style={{ ...inp, fontFamily: 'var(--font-body)' }}>
            <option value="__none__">— selecione —</option>
            <option value="__new__">✦ Criar nova página com este título</option>
            {pages.map((p: any) => (
              <option key={p.id} value={p.id}>{p.icon ?? '◦'} {p.title}</option>
            ))}
          </select>
          {createPg && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: accent, fontStyle: 'italic' }}>
              Uma nova página será criada ao guardar.
            </span>
          )}
        </div>

        {/* Tipo + Horas */}
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, letterSpacing: '0.12em' }}>TIPO</label>
            <select value={taskType} onChange={e => setTaskType(e.target.value)}
              style={{ ...inp, fontFamily: 'var(--font-body)' }}>
              {Object.entries(TYPE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{TYPE_ICONS[k]} {v}</option>
              ))}
            </select>
          </div>
          <div style={{ width: 90, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, letterSpacing: '0.12em' }}>HORAS EST.</label>
            <input type="number" min="0.5" max="100" step="0.5" style={{ ...inp, fontFamily: 'var(--font-mono)' }}
              value={hours} onChange={e => setHours(e.target.value)} />
          </div>
        </div>

        {/* Prazo + Prioridade */}
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, letterSpacing: '0.12em' }}>PRAZO</label>
            <input type="date" value={dueDate} onChange={e => setDueDate(e.target.value)}
              style={{ ...inp, fontFamily: 'var(--font-mono)' }} />
          </div>
          <div style={{ width: 110, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, letterSpacing: '0.12em' }}>PRIORIDADE</label>
            <select value={priority} onChange={e => setPriority(e.target.value)}
              style={{ ...inp, fontFamily: 'var(--font-body)', color: PRIORITY_COLORS[priority] ?? ink }}>
              {Object.entries(PRIORITY_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Repetição espaçada */}
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <input type="checkbox" checked={spacedReview} onChange={e => setSpacedReview(e.target.checked)} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, letterSpacing: '0.08em' }}>
            REPETIÇÃO ESPAÇADA — revisões automáticas: 1 → 3 → 7 → 14 → 30 dias
          </span>
        </label>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button className="btn btn-ghost btn-sm" onClick={onClose} style={{ color: ink2 }}>Cancelar</button>
          <button className="btn btn-sm" style={{ borderColor: accent, color: accent }}
            onClick={handleSave} disabled={saving || !title.trim() || !dueDate}>
            {saving ? 'A guardar…' : 'Guardar'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── LogPopover — log horas + editar planned_hours ─────────────────────────────

function LogPopover({ block, dark, onLog, onEditPlanned, onClose }: {
  block: WorkBlock; dark: boolean
  onLog: (h: number) => void
  onEditPlanned: (h: number) => void
  onClose: () => void
}) {
  const [logged,  setLogged]  = useState(String(block.logged_hours || block.planned_hours))
  const [planned, setPlanned] = useState(String(block.planned_hours))
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const bg     = dark ? '#2A2318' : '#F0EAD8'
  const accent = dark ? '#D4A820' : '#b8860b'

  const submit = () => {
    onLog(parseFloat(logged) || 0)
    const p = parseFloat(planned)
    if (!isNaN(p) && p !== block.planned_hours) onEditPlanned(p)
    onClose()
  }

  return (
    <div style={{
      position: 'absolute', top: '100%', left: 0, zIndex: 100,
      background: bg, border: `1px solid ${border}`, borderRadius: 3,
      padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8,
      boxShadow: '0 4px 16px rgba(0,0,0,0.2)', minWidth: 180,
    }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, letterSpacing: '0.1em' }}>
          HORAS REGISTADAS
        </span>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <input type="number" min="0" step="0.25"
            value={logged} onChange={e => setLogged(e.target.value)}
            autoFocus
            style={{ width: 64, background: 'transparent', border: `1px solid ${border}`,
              borderRadius: 2, padding: '4px 8px', color: ink, fontFamily: 'var(--font-mono)', fontSize: 12, outline: 'none' }}
            onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') onClose() }}
          />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2 }}>
            / {block.planned_hours}h plan.
          </span>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, letterSpacing: '0.1em' }}>
          HORAS PLANEADAS (editar bloco)
        </span>
        <input type="number" min="0.25" step="0.25"
          value={planned} onChange={e => setPlanned(e.target.value)}
          style={{ width: 64, background: 'transparent', border: `1px solid ${border}`,
            borderRadius: 2, padding: '4px 8px', color: ink, fontFamily: 'var(--font-mono)', fontSize: 12, outline: 'none' }}
        />
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <button className="btn btn-sm"
          style={{ flex: 1, borderColor: accent, color: accent, fontSize: 10 }}
          onClick={submit}>Confirmar</button>
        <button className="btn btn-ghost btn-sm" onClick={onClose} style={{ color: ink2, fontSize: 10 }}>✕</button>
      </div>
    </div>
  )
}

// ── Vista semanal ─────────────────────────────────────────────────────────────

function WeekView({ tasks, dark, weekOffset, onLog, onWeekChange, onStartFocus }: {
  tasks:        PlannedTask[]
  dark:         boolean
  weekOffset:   number
  onLog:        (blockId: number, hours: number) => void
  onWeekChange: (delta: number) => void
  onStartFocus: (task: PlannedTask, block: WorkBlock) => void
}) {
  const [blocks,  setBlocks]  = useState<WorkBlock[]>([])
  const [openLog, setOpenLog] = useState<number | null>(null)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const accent = dark ? '#D4A820' : '#b8860b'
  const today  = new Date().toISOString().slice(0, 10)
  const dates  = weekDates(weekOffset)

  const loadBlocks = useCallback(async () => {
    if (tasks.length === 0) { setBlocks([]); return }
    const all = await Promise.all(tasks.map(async t => {
      const r = await fromIpc<WorkBlock[]>(() => db().planner.listBlocks(t.id), 'listBlocks')
      return r.isOk() ? r.value : [] as WorkBlock[]
    }))
    setBlocks(all.flat())
  }, [tasks])

  useEffect(() => { loadBlocks() }, [loadBlocks])

  const taskMap = Object.fromEntries(tasks.map(t => [t.id, t]))

  const dayTotals = Object.fromEntries(dates.map(d => [
    d,
    blocks.filter(b => b.date === d && b.status !== 'missed')
          .reduce((s, b) => s + b.planned_hours, 0),
  ]))

  const handleLog = async (block: WorkBlock, hours: number) => {
    const r = await fromIpc<WorkBlock>(() => db().planner.logBlock(block.id, hours), 'logBlock')
    if (r.isOk()) {
      setBlocks(prev => prev.map(b => b.id === block.id ? r.value : b))
      onLog(block.id, hours)
    }
  }

  const handleEditPlanned = async (blockId: number, planned_hours: number) => {
    const r = await fromIpc<WorkBlock>(() => db().planner.updateBlock({ id: blockId, planned_hours }), 'updateBlock')
    if (r.isOk()) setBlocks(prev => prev.map(b => b.id === blockId ? r.value : b))
  }

  const startOfWeek = dates[0]
  const endOfWeek   = dates[6]
  const weekLabel   = `${isoToDisplay(startOfWeek)} – ${isoToDisplay(endOfWeek)}`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8,
        padding: '8px 0 10px', borderBottom: `1px solid ${border}` }}>
        <button className="btn btn-ghost btn-sm" onClick={() => onWeekChange(-1)}
          style={{ color: ink2, padding: '2px 6px' }}>‹</button>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: ink2, letterSpacing: '0.1em', flex: 1 }}>
          {weekLabel}
        </span>
        <button className="btn btn-ghost btn-sm" onClick={() => onWeekChange(1)}
          style={{ color: ink2, padding: '2px 6px' }}>›</button>
        {weekOffset !== 0 && (
          <button className="btn btn-ghost btn-sm" onClick={() => onWeekChange(-weekOffset)}
            style={{ color: accent, padding: '2px 6px', fontSize: 10 }}>Hoje</button>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 4, paddingTop: 10 }}>
        {dates.map((date, i) => {
          const isToday   = date === today
          const dayBlocks = blocks.filter(b => b.date === date && b.status !== 'missed')
          const totalHours = dayTotals[date] ?? 0

          return (
            <div key={date} style={{
              display: 'flex', flexDirection: 'column', gap: 4,
              background: isToday ? (dark ? '#251F14' : '#EAE2CC') : cardBg,
              border: `1px solid ${isToday ? accent + '66' : border}`,
              borderRadius: 3, padding: '6px 6px 8px', minHeight: 100,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9,
                  color: isToday ? accent : ink2, fontWeight: isToday ? 700 : 400, letterSpacing: '0.1em' }}>
                  {DAY_NAMES[i]}
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: isToday ? accent : ink2 }}>
                  {new Date(date + 'T12:00:00').getDate()}
                </span>
              </div>
              {totalHours > 0 && (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: ink2,
                  paddingBottom: 2, borderBottom: `1px solid ${border}` }}>
                  {totalHours.toFixed(1)}h
                </span>
              )}
              {dayBlocks.map(block => {
                const task   = taskMap[block.task_id]
                if (!task) return null
                const isDone = block.status === 'done'
                const color  = STATUS_COLORS[task.status] ?? '#8B7355'
                const isOpen = openLog === block.id
                return (
                  <div key={block.id} style={{ position: 'relative' }}>
                    <div style={{ display: 'flex', alignItems: 'stretch', gap: 1 }}>
                      <button
                        onClick={() => setOpenLog(isOpen ? null : block.id)}
                        title={`${task.title} — ${block.planned_hours}h`}
                        style={{
                          flex: 1, textAlign: 'left',
                          background: color + (isDone ? '33' : '18'),
                          border: `1px solid ${color}${isDone ? '88' : '44'}`,
                          borderLeft: `3px solid ${color}`,
                          borderRight: 'none', borderRadius: '2px 0 0 2px',
                          padding: '3px 5px',
                          fontFamily: 'var(--font-mono)', fontSize: 9,
                          color: isDone ? ink2 : ink,
                          textDecoration: isDone ? 'line-through' : 'none', cursor: 'pointer',
                        }}>
                        <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {TYPE_ICONS[task.task_type]} {task.title}
                        </div>
                        <div style={{ color: isDone ? color : ink2, marginTop: 1 }}>
                          {isDone ? `✓ ${block.logged_hours}h` : `${block.planned_hours}h`}
                        </div>
                      </button>
                      {/* ▶ Foco direto do bloco */}
                      {date === today && !isDone && (
                        <button
                          title="Iniciar foco nesta tarefa"
                          onClick={() => onStartFocus(task, block)}
                          style={{
                            background: color + '18', border: `1px solid ${color}44`,
                            borderLeft: 'none', borderRadius: '0 2px 2px 0',
                            padding: '0 4px', cursor: 'pointer', color: accent, fontSize: 9,
                          }}>▶</button>
                      )}
                    </div>
                    {isOpen && (
                      <LogPopover
                        block={block} dark={dark}
                        onLog={h => handleLog(block, h)}
                        onEditPlanned={h => handleEditPlanned(block.id, h)}
                        onClose={() => setOpenLog(null)}
                      />
                    )}
                  </div>
                )
              })}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── RemindersSection ──────────────────────────────────────────────────────────

const OFFSET_OPTIONS = [
  { label: '15 min antes', value: 15 },
  { label: '1h antes',     value: 60 },
  { label: '3h antes',     value: 180 },
  { label: '1 dia antes',  value: 1440 },
  { label: '3 dias antes', value: 4320 },
  { label: 'Data exacta',  value: 0 },
]

function RemindersSection({ projectId, dark, pages }: {
  projectId: number; dark: boolean; pages: any[]
}) {
  const { pushToast } = useAppStore()
  const [reminders, setReminders] = useState<any[]>([])
  const [showForm,  setShowForm]  = useState(false)

  const [rTitle,    setRTitle]    = useState('')
  const [rPageId,   setRPageId]   = useState<number | ''>('')
  const [rDate,     setRDate]     = useState(new Date().toISOString().slice(0, 10))
  const [rTime,     setRTime]     = useState('09:00')
  const [rOffset,   setROffset]   = useState(60)
  const [rPriority, setRPriority] = useState('medium')
  const [rSaving,   setRSaving]   = useState(false)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const accent = dark ? '#D4A820' : '#b8860b'

  const load = useCallback(async () => {
    const r = await fromIpc<any[]>(() => db().reminders.listForProject(projectId), 'remindersForProject')
    r.match(d => setReminders(d), () => {})
  }, [projectId])

  useEffect(() => { load() }, [load])

  const createReminder = async () => {
    if (!rTitle.trim()) {
      pushToast({ kind: 'error', title: 'Título obrigatório' })
      return
    }
    if (!rPageId) {
      pushToast({ kind: 'error', title: 'Página obrigatória', detail: 'Selecione a página/disciplina deste lembrete.' })
      return
    }
    setRSaving(true)
    // calculate trigger_at based on offset or exact date/time
    let triggerAt: string
    if (rOffset === 0) {
      triggerAt = new Date(`${rDate}T${rTime}:00`).toISOString()
    } else {
      const base = new Date(`${rDate}T${rTime}:00`)
      base.setMinutes(base.getMinutes() - rOffset)
      triggerAt = base.toISOString()
    }
    const result = await fromIpc<any>(
      () => db().reminders.create({
        title:          rTitle.trim(),
        trigger_at:     triggerAt,
        offset_minutes: rOffset > 0 ? rOffset : null,
        linked_page_id: rPageId || null,
        priority:       rPriority,
        project_id:     projectId,
      }),
      'createReminder'
    )
    setRSaving(false)
    if (result.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao criar lembrete', detail: result.error.message })
      return
    }
    setReminders(prev => [...prev, result.value])
    setRTitle(''); setShowForm(false)
    pushToast({ kind: 'success', title: 'Lembrete criado!' })
  }

  const dismiss = async (id: number) => {
    await fromIpc(() => db().reminders.dismiss(id), 'dismissReminder')
    setReminders(prev => prev.filter(r => r.id !== id))
  }

  const del = async (id: number) => {
    await fromIpc(() => db().reminders.delete(id), 'deleteReminder')
    setReminders(prev => prev.filter(r => r.id !== id))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em', color: ink2, flex: 1 }}>
          LEMBRETES ({reminders.length})
        </span>
        <button className="btn btn-sm" onClick={() => setShowForm(o => !o)}
          style={{ borderColor: accent, color: accent, fontSize: 10 }}>
          {showForm ? '×' : '+ Lembrete'}
        </button>
      </div>

      {showForm && (
        <div style={{ background: dark ? '#1E1A12' : '#E8E2D4', border: `1px solid ${border}`,
          borderRadius: 3, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, letterSpacing: '0.1em', display: 'block', marginBottom: 3 }}>
                TÍTULO
              </label>
              <input className="settings-input" style={{ width: '100%', fontSize: 11 }}
                value={rTitle} onChange={e => setRTitle(e.target.value)}
                placeholder="Ex: Entregar trabalho" autoFocus />
            </div>
            <div style={{ width: 90 }}>
              <label style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, letterSpacing: '0.1em', display: 'block', marginBottom: 3 }}>
                PRIORIDADE
              </label>
              <select className="settings-input" style={{ width: '100%', fontSize: 11, color: PRIORITY_COLORS[rPriority] }}
                value={rPriority} onChange={e => setRPriority(e.target.value)}>
                {Object.entries(PRIORITY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, letterSpacing: '0.1em', display: 'block', marginBottom: 3 }}>
              PÁGINA / DISCIPLINA *
            </label>
            <select className="settings-input" style={{ width: '100%', fontSize: 11 }}
              value={rPageId} onChange={e => setRPageId(e.target.value ? Number(e.target.value) : '')}>
              <option value="">— selecione —</option>
              {pages.map((p: any) => <option key={p.id} value={p.id}>{p.icon ?? '◦'} {p.title}</option>)}
            </select>
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, letterSpacing: '0.1em', display: 'block', marginBottom: 3 }}>
                DATA DO EVENTO
              </label>
              <input type="date" className="settings-input" style={{ width: '100%', fontSize: 11 }}
                value={rDate} onChange={e => setRDate(e.target.value)} />
            </div>
            <div style={{ width: 90 }}>
              <label style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, letterSpacing: '0.1em', display: 'block', marginBottom: 3 }}>
                HORA
              </label>
              <input type="time" className="settings-input" style={{ width: '100%', fontSize: 11 }}
                value={rTime} onChange={e => setRTime(e.target.value)} />
            </div>
          </div>

          <div>
            <label style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, letterSpacing: '0.1em', display: 'block', marginBottom: 3 }}>
              NOTIFICAR
            </label>
            <select className="settings-input" style={{ width: '100%', fontSize: 11 }}
              value={rOffset} onChange={e => setROffset(Number(e.target.value))}>
              {OFFSET_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn btn-ghost btn-sm" style={{ color: ink2 }}
              onClick={() => setShowForm(false)}>Cancelar</button>
            <button className="btn btn-sm" style={{ borderColor: accent, color: accent }}
              onClick={createReminder} disabled={rSaving}>
              {rSaving ? 'A criar…' : 'Criar'}
            </button>
          </div>
        </div>
      )}

      {reminders.map(r => {
        const pColor = PRIORITY_COLORS[r.priority ?? 'medium'] ?? '#8B7355'
        const dt = r.trigger_at ? new Date(r.trigger_at).toLocaleDateString('pt-BR', {
          day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
        }) : ''
        return (
          <div key={r.id} style={{
            display: 'flex', alignItems: 'center', gap: 8,
            background: cardBg, border: `1px solid ${border}`,
            borderLeft: `3px solid ${pColor}`, borderRadius: 3, padding: '6px 10px',
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: ink,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {r.title}
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 2 }}>
                {r.page_title && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
                    {r.page_icon ?? '◦'} {r.page_title}
                  </span>
                )}
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>{dt}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: pColor }}>
                  {PRIORITY_LABELS[r.priority ?? 'medium']}
                </span>
              </div>
            </div>
            <button className="btn btn-ghost btn-sm" style={{ color: ink2, fontSize: 10 }}
              onClick={() => dismiss(r.id)} title="Dispensar">✓</button>
            <button className="btn btn-ghost btn-sm" style={{ color: '#8B3A2A', fontSize: 10 }}
              onClick={() => del(r.id)} title="Eliminar">✕</button>
          </div>
        )
      })}

      {reminders.length === 0 && !showForm && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2,
          fontStyle: 'italic', opacity: 0.6 }}>
          Nenhum lembrete activo.
        </div>
      )}
    </div>
  )
}

// ── PlannerTab principal ──────────────────────────────────────────────────────

export function PlannerTab({ projectId, dark, pages }: {
  projectId: number
  dark:      boolean
  pages:     any[]
}) {
  const { pushToast } = useAppStore()
  const [tasks,      setTasks]      = useState<PlannedTask[]>([])
  const [showModal,  setShowModal]  = useState(false)
  const [editTask,   setEditTask]   = useState<PlannedTask | null>(null)
  const [weekOffset, setWeekOffset] = useState(0)
  const [scheduling, setScheduling] = useState(false)
  const [showTimer,  setShowTimer]  = useState(false)
  const [activeBlock, setActiveBlock] = useState<ActiveTimerBlock | null>(null)
  const timerRef = useRef<HTMLDivElement>(null)
  const logVersion = useRef(0)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const bg     = dark ? '#1A1610' : '#F5F0E8'
  const accent = dark ? '#D4A820' : '#b8860b'

  const today = new Date().toISOString().slice(0, 10)

  const loadTasks = async () => {
    const r = await fromIpc<PlannedTask[]>(() => db().planner.listTasks(projectId), 'listTasks')
    if (r.isOk()) setTasks(r.value)
  }

  useEffect(() => { loadTasks() }, [projectId])

  const handleReschedule = async () => {
    setScheduling(true)
    await fromIpc(() => db().planner.schedule(projectId), 'schedule')
    logVersion.current++
    await loadTasks()
    setScheduling(false)
  }

  const handleDelete = async (task: PlannedTask) => {
    if (!confirm(`Excluir "${task.title}"?`)) return
    await fromIpc(() => db().planner.deleteTask(task.id), 'deleteTask')
    setTasks(prev => prev.filter(t => t.id !== task.id))
  }

  const handleSaved = (saved: PlannedTask) => {
    setTasks(prev => {
      const idx = prev.findIndex(t => t.id === saved.id)
      if (idx >= 0) { const next = [...prev]; next[idx] = saved; return next }
      return [...prev, saved]
    })
    logVersion.current++
  }

  // ▶ Iniciar foco a partir de uma tarefa/bloco
  const handleStartFocus = async (task: PlannedTask, block?: WorkBlock) => {
    let blockData: WorkBlock | undefined = block
    if (!blockData) {
      // buscar o bloco de hoje para esta tarefa
      const r = await fromIpc<WorkBlock[]>(() => db().planner.listBlocks(task.id), 'listBlocks')
      if (r.isOk()) {
        blockData = r.value.find(b => b.date === today && b.status !== 'missed')
      }
    }
    setActiveBlock({
      blockId:      blockData?.id ?? null,
      taskId:       task.id,
      taskTitle:    task.title,
      pageId:       task.page_id,
      loggedHours:  blockData?.logged_hours ?? 0,
      plannedHours: blockData?.planned_hours ?? task.estimated_hours,
    })
    setShowTimer(true)
    // scroll para o timer
    setTimeout(() => timerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100)
  }

  // Auto-log chamado pelo StudyTimerTab quando sessão termina
  const handleAutoLog = async (blockId: number, newTotalHours: number) => {
    await fromIpc<WorkBlock>(() => db().planner.logBlock(blockId, newTotalHours), 'autoLogBlock')
    // atualizar activeBlock com os novos logged_hours
    setActiveBlock(prev => prev ? { ...prev, loggedHours: newTotalHours } : prev)
    logVersion.current++
    await loadTasks()
  }

  const active = tasks.filter(t => t.status !== 'completed')
  const done   = tasks.filter(t => t.status === 'completed')

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20,
      minHeight: 0, overflowY: 'auto', background: bg }}>

      {/* Barra de ações */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <button className="btn btn-sm" style={{ borderColor: accent, color: accent }}
          onClick={() => { setEditTask(null); setShowModal(true) }}>
          + Nova Tarefa
        </button>
        <button className="btn btn-ghost btn-sm" style={{ color: ink2 }}
          onClick={handleReschedule} disabled={scheduling}
          title="Recalcula os blocos de trabalho para todas as tarefas ativas">
          {scheduling ? '…' : '↺ Reagendar'}
        </button>
        <button className="btn btn-ghost btn-sm"
          style={{ color: showTimer ? accent : ink2, borderColor: showTimer ? accent : 'transparent', marginLeft: 'auto' }}
          onClick={() => setShowTimer(o => !o)}
          title="Pomodoro / Registo de tempo">
          ◎ {showTimer ? 'Fechar timer' : 'Timer'}
        </button>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2 }}>
          {active.length} tarefa{active.length !== 1 ? 's' : ''} ativa{active.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Lista de tarefas ativas */}
      {active.length === 0 ? (
        <div style={{ padding: '32px 0', textAlign: 'center',
          fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 15, color: ink2 }}>
          Nenhuma tarefa planejada.
          <br /><span style={{ fontSize: 12 }}>Clique em "+ Nova Tarefa" para começar.</span>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {active.map(task => {
            const pct    = Math.min(100, task.estimated_hours > 0
              ? Math.round((task.done_hours / task.estimated_hours) * 100) : 0)
            const color  = STATUS_COLORS[task.status] ?? '#8B7355'
            const pColor = PRIORITY_COLORS[task.priority ?? 'medium'] ?? '#8B7355'
            const d      = daysUntil(task.due_date)
            const isPast = d < 0
            const isReview = task.spaced_review === 1 && task.parent_task_id !== null

            return (
              <div key={task.id} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                background: dark ? '#211D16' : '#EDE7D9',
                border: `1px solid ${isPast ? '#8B3A2A44' : border}`,
                borderLeft: `3px solid ${isReview ? '#4A8A7A' : color}`,
                borderRadius: 3, padding: '8px 12px',
              }}>
                <span style={{ fontSize: 16, flexShrink: 0 }}>{TYPE_ICONS[task.task_type]}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: ink,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {isReview && <span style={{ color: '#4A8A7A', fontSize: 10, marginRight: 4 }}>♻</span>}
                    {task.title}
                    {task.page_title && (
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, marginLeft: 8 }}>
                        {task.page_icon ?? '◦'} {task.page_title}
                      </span>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
                    <div style={{ width: 80, height: 3, background: border, borderRadius: 2, flexShrink: 0 }}>
                      <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2 }} />
                    </div>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
                      {(task.done_hours ?? 0).toFixed(1)}/{task.estimated_hours}h
                    </span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9,
                      color: isPast ? '#8B3A2A' : d <= 3 ? '#b8860b' : ink2 }}>
                      {isPast ? `${Math.abs(d)}d atrasada` : d === 0 ? 'Hoje' : `${d}d`} · {isoToDisplay(task.due_date)}
                    </span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: pColor, marginLeft: 'auto' }}>
                      {PRIORITY_LABELS[task.priority ?? 'medium']}
                    </span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                  {/* ▶ Iniciar foco */}
                  <button className="btn btn-ghost btn-sm"
                    style={{ color: accent, padding: '2px 6px', fontSize: 11 }}
                    onClick={() => handleStartFocus(task)}
                    title="Iniciar foco nesta tarefa">▶</button>
                  <button className="btn btn-ghost btn-sm"
                    style={{ color: ink2, padding: '2px 6px', fontSize: 11 }}
                    onClick={() => { setEditTask(task); setShowModal(true) }}
                    title="Editar">✎</button>
                  <button className="btn btn-ghost btn-sm"
                    style={{ color: '#8B3A2A', padding: '2px 6px', fontSize: 11 }}
                    onClick={() => handleDelete(task)}
                    title="Excluir">✕</button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Vista semanal */}
      <div style={{ background: dark ? '#211D16' : '#EDE7D9', border: `1px solid ${border}`,
        borderRadius: 3, padding: '14px 16px' }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em',
          color: ink2, marginBottom: 10 }}>
          CALENDÁRIO SEMANAL
        </div>
        <WeekView
          key={logVersion.current}
          tasks={tasks}
          dark={dark}
          weekOffset={weekOffset}
          onLog={() => { logVersion.current++; loadTasks() }}
          onWeekChange={delta => setWeekOffset(o => o + delta)}
          onStartFocus={handleStartFocus}
        />
      </div>

      {/* Lembretes */}
      <div style={{ background: dark ? '#211D16' : '#EDE7D9', border: `1px solid ${border}`,
        borderRadius: 3, padding: '14px 16px' }}>
        <RemindersSection projectId={projectId} dark={dark} pages={pages} />
      </div>

      {/* Timer / Pomodoro */}
      <div ref={timerRef} style={{ display: showTimer ? 'block' : 'none' }}>
        <div style={{ background: dark ? '#211D16' : '#EDE7D9', border: `1px solid ${accent}44`,
          borderRadius: 3, padding: '14px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em', color: ink2 }}>
              ◎ POMODORO / TEMPO DE FOCO
              {activeBlock && (
                <span style={{ color: accent, marginLeft: 8 }}>▶ {activeBlock.taskTitle}</span>
              )}
            </span>
            <button className="btn btn-ghost btn-sm" style={{ color: ink2 }}
              onClick={() => { setShowTimer(false); setActiveBlock(null) }}>✕</button>
          </div>
          <StudyTimerTab
            projectId={projectId}
            dark={dark}
            pages={pages}
            initialBlock={activeBlock}
            onAutoLog={handleAutoLog}
          />
        </div>
      </div>

      {/* Tarefas concluídas */}
      {done.length > 0 && (
        <details>
          <summary style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.12em',
            color: ink2, cursor: 'pointer', userSelect: 'none' }}>
            CONCLUÍDAS ({done.length})
          </summary>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
            {done.map(task => (
              <div key={task.id} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                background: dark ? '#211D16' : '#EDE7D9',
                border: `1px solid ${border}`, borderLeft: '3px solid #4A6741',
                borderRadius: 3, padding: '6px 12px', opacity: 0.7,
              }}>
                <span>{TYPE_ICONS[task.task_type]}</span>
                <span style={{ flex: 1, fontFamily: 'var(--font-body)', fontSize: 12, color: ink2,
                  textDecoration: 'line-through' }}>{task.title}</span>
                {task.page_title && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
                    {task.page_icon ?? '◦'} {task.page_title}
                  </span>
                )}
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: '#4A6741' }}>
                  ✓ {task.estimated_hours}h
                </span>
                <button className="btn btn-ghost btn-sm"
                  style={{ color: '#8B3A2A', padding: '2px 6px', fontSize: 11 }}
                  onClick={() => handleDelete(task)}>✕</button>
              </div>
            ))}
          </div>
        </details>
      )}

      {showModal && (
        <TaskModal
          dark={dark} projectId={projectId} pages={pages}
          task={editTask}
          onSave={handleSaved}
          onClose={() => { setShowModal(false); setEditTask(null) }}
        />
      )}
    </div>
  )
}
