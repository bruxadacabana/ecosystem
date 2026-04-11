import React, { useCallback, useEffect, useRef, useState } from 'react'
import { fromIpc } from '../../types/errors'
import { useAppStore } from '../../store/useAppStore'
import { Page } from '../../types'
import './StudyTimerTab.css'

const db = () => (window as any).db

// ── Tipos ─────────────────────────────────────────────────────────────────────

interface TimeSession {
  id:           number
  project_id:   number
  page_id:      number | null
  duration_min: number
  session_type: string
  notes:        string | null
  tags:         string | null
  started_at:   string
  ended_at:     string | null
  page_title?:  string
  page_icon?:   string
}

type TimerMode   = 'focus' | 'break'
type TimerStatus = 'idle' | 'running' | 'paused'

const FOCUS_MIN = 25
const BREAK_MIN = 5

// ── Relógio SVG animado ───────────────────────────────────────────────────────

function AnimatedClock({
  totalSecs, remainSecs, status, mode, dark,
}: {
  totalSecs: number; remainSecs: number; status: TimerStatus; mode: TimerMode; dark: boolean
}) {
  const R        = 80
  const CX       = 100
  const CY       = 100
  const circum   = 2 * Math.PI * R
  const progress = totalSecs > 0 ? remainSecs / totalSecs : 1
  const dashOff  = circum * (1 - progress)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = mode === 'focus'
    ? (dark ? '#D4A820' : '#b8860b')
    : (dark ? '#4A8A60' : '#3D7A52')
  const trackC = dark ? '#2A2418' : '#D8D0C0'

  const mm = String(Math.floor(remainSecs / 60)).padStart(2, '0')
  const ss = String(remainSecs % 60).padStart(2, '0')

  // pulsing tick marks (12 dots around the rim)
  const ticks = Array.from({ length: 60 }, (_, i) => {
    const angle = (i / 60) * Math.PI * 2 - Math.PI / 2
    const major = i % 5 === 0
    const r1    = major ? 68 : 72
    const r2    = major ? 76 : 74
    return {
      x1: CX + r1 * Math.cos(angle),
      y1: CY + r1 * Math.sin(angle),
      x2: CX + r2 * Math.cos(angle),
      y2: CY + r2 * Math.sin(angle),
      opacity: major ? 0.45 : 0.2,
    }
  })

  return (
    <svg viewBox="0 0 200 200" className="study-clock-svg">
      {/* outer glow ring */}
      <circle cx={CX} cy={CY} r={R + 6}
        fill="none" stroke={accent} strokeWidth={1} opacity={0.12} />

      {/* tick marks */}
      {ticks.map((t, i) => (
        <line key={i}
          x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2}
          stroke={ink2} strokeWidth={major(i) ? 1.5 : 0.8} opacity={t.opacity} />
      ))}

      {/* track */}
      <circle cx={CX} cy={CY} r={R}
        fill="none" stroke={trackC} strokeWidth={8} />

      {/* progress arc */}
      <circle
        cx={CX} cy={CY} r={R}
        fill="none"
        stroke={accent}
        strokeWidth={8}
        strokeLinecap="round"
        strokeDasharray={circum}
        strokeDashoffset={dashOff}
        transform={`rotate(-90 ${CX} ${CY})`}
        style={{
          transition: status === 'running' ? 'stroke-dashoffset 1s linear' : 'stroke-dashoffset 0.3s ease',
          filter: status === 'running' ? `drop-shadow(0 0 4px ${accent}88)` : 'none',
        }}
      />

      {/* inner face */}
      <circle cx={CX} cy={CY} r={R - 12}
        fill={dark ? '#1A160E' : '#F5F0E8'} />

      {/* mode label */}
      <text x={CX} y={CY - 14}
        textAnchor="middle" dominantBaseline="middle"
        fontFamily="var(--font-mono)"
        fontSize={9} letterSpacing={2}
        fill={accent} opacity={0.8}
      >
        {mode === 'focus' ? 'FOCO' : 'PAUSA'}
      </text>

      {/* time display */}
      <text x={CX} y={CY + 6}
        textAnchor="middle" dominantBaseline="middle"
        fontFamily="var(--font-mono)"
        fontSize={28} fontWeight={300}
        fill={ink}
        style={{ letterSpacing: '-1px' }}
      >
        {mm}:{ss}
      </text>

      {/* status dot */}
      {status === 'running' && (
        <circle cx={CX} cy={CY + 26} r={3} fill={accent}>
          <animate attributeName="opacity" values="1;0.3;1" dur="1.2s" repeatCount="indefinite" />
        </circle>
      )}
      {status === 'paused' && (
        <text x={CX} y={CY + 28}
          textAnchor="middle" fontFamily="var(--font-mono)"
          fontSize={8} fill={ink2} letterSpacing={1}
        >
          PAUSA
        </text>
      )}
    </svg>
  )
}

function major(i: number) { return i % 5 === 0 }

// ── Formatadores ──────────────────────────────────────────────────────────────

function fmtDuration(min: number) {
  if (min < 60) return `${min}min`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m === 0 ? `${h}h` : `${h}h ${m}min`
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('pt-BR', {
    day: '2-digit', month: 'short', year: 'numeric',
  })
}

// ── Componente principal ───────────────────────────────────────────────────────

export interface ActiveTimerBlock {
  blockId:      number | null   // work_block id (null = sem bloco agendado hoje)
  taskId:       number
  taskTitle:    string
  pageId:       number | null
  loggedHours:  number
  plannedHours: number
}

interface Props {
  projectId:    number
  dark:         boolean
  pages:        Page[]
  initialBlock?: ActiveTimerBlock | null
  onAutoLog?:   (blockId: number, newTotalHours: number) => void
}

export function StudyTimerTab({ projectId, dark, pages, initialBlock, onAutoLog }: Props) {
  const { workspace, pushToast } = useAppStore()

  // ── Timer state ─────────────────────────────────────────────────────────────
  const [timerMode,   setTimerMode]   = useState<TimerMode>('focus')
  const [timerStatus, setTimerStatus] = useState<TimerStatus>('idle')
  const [remainSecs,  setRemainSecs]  = useState(FOCUS_MIN * 60)
  const [totalSecs,   setTotalSecs]   = useState(FOCUS_MIN * 60)
  const [sessionStart, setSessionStart] = useState<Date | null>(null)

  // selected page for the current timer session
  const [timerPageId, setTimerPageId] = useState<number | ''>(initialBlock?.pageId ?? '')

  // keep page in sync when initialBlock changes (user clicked ▶ on a different task)
  useEffect(() => {
    if (initialBlock?.pageId) setTimerPageId(initialBlock.pageId)
  }, [initialBlock?.taskId])

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopInterval = () => {
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null }
  }

  const tick = useCallback(() => {
    setRemainSecs(prev => {
      if (prev <= 1) {
        stopInterval()
        return 0
      }
      return prev - 1
    })
  }, [])

  // auto-complete when remainSecs hits 0
  useEffect(() => {
    if (remainSecs === 0 && timerStatus === 'running') {
      setTimerStatus('idle')
      if (timerMode === 'focus' && sessionStart) {
        saveSession('pomodoro', FOCUS_MIN, sessionStart)
        if (initialBlock?.blockId && onAutoLog) {
          const newTotal = Math.min(
            initialBlock.loggedHours + FOCUS_MIN / 60,
            initialBlock.plannedHours
          )
          onAutoLog(initialBlock.blockId, newTotal)
        }
        setTimerMode('break')
        setRemainSecs(BREAK_MIN * 60)
        setTotalSecs(BREAK_MIN * 60)
        pushToast({ kind: 'success', title: 'Pomodoro concluído! ☕', detail: `Pausa de ${BREAK_MIN} minutos.` })
      } else if (timerMode === 'break') {
        setTimerMode('focus')
        setRemainSecs(FOCUS_MIN * 60)
        setTotalSecs(FOCUS_MIN * 60)
        pushToast({ kind: 'info', title: 'Pausa terminada!', detail: 'Pronto para o próximo Pomodoro.' })
      }
      setSessionStart(null)
    }
  }, [remainSecs, timerStatus])

  const startTimer = () => {
    if (!timerPageId) {
      pushToast({ kind: 'error', title: 'Selecione uma página', detail: 'Cada sessão de foco precisa estar ligada a uma página/disciplina.' })
      return
    }
    if (timerStatus === 'idle') setSessionStart(new Date())
    setTimerStatus('running')
    intervalRef.current = setInterval(tick, 1000)
  }

  const pauseTimer = () => {
    stopInterval()
    setTimerStatus('paused')
  }

  const resumeTimer = () => {
    setTimerStatus('running')
    intervalRef.current = setInterval(tick, 1000)
  }

  const resetTimer = () => {
    stopInterval()
    setTimerStatus('idle')
    setSessionStart(null)
    const secs = (timerMode === 'focus' ? FOCUS_MIN : BREAK_MIN) * 60
    setRemainSecs(secs)
    setTotalSecs(secs)
  }

  useEffect(() => () => stopInterval(), [])

  // ── Session save ─────────────────────────────────────────────────────────────
  const [sessions, setSessions] = useState<TimeSession[]>([])

  const loadSessions = useCallback(() => {
    fromIpc<TimeSession[]>(() => db().time.list({ project_id: projectId }), 'timeList')
      .then(r => r.match(data => setSessions(data), _e => {}))
  }, [projectId])

  useEffect(() => { loadSessions() }, [loadSessions])

  const saveSession = async (
    type: string,
    durationMin: number,
    start: Date,
    pageId?: number | null,
    notes?: string,
    tags?: string,
  ) => {
    if (!workspace) return
    const now      = new Date()
    const startIso = start.toISOString()
    const endIso   = now.toISOString()
    const result   = await fromIpc<TimeSession>(
      () => db().time.create({
        workspace_id: workspace.id,
        project_id:   projectId,
        page_id:      pageId ?? null,
        duration_min: durationMin,
        session_type: type,
        notes:        notes?.trim() || null,
        tags:         tags?.trim() || null,
        started_at:   startIso,
        ended_at:     endIso,
      }),
      'timeCreate',
    )
    if (result.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao guardar sessão', detail: result.error.message })
      return
    }
    setSessions(prev => [result.value, ...prev])
  }

  const deleteSession = async (id: number) => {
    const result = await fromIpc<unknown>(
      () => db().time.delete({ id }),
      'timeDelete',
    )
    if (result.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao eliminar sessão', detail: result.error.message })
      return
    }
    setSessions(prev => prev.filter(s => s.id !== id))
  }

  // ── Manual entry state ───────────────────────────────────────────────────────
  type ManMode = 'duration' | 'start_end'
  const [showManual,   setShowManual]   = useState(false)
  const [manMode,      setManMode]      = useState<ManMode>('duration')
  const [manPageId,    setManPageId]    = useState<number | ''>('')
  const [manHours,     setManHours]     = useState('0')
  const [manMins,      setManMins]      = useState('25')
  const [manDate,      setManDate]      = useState(new Date().toISOString().slice(0, 10))
  const [manStartTime, setManStartTime] = useState('09:00')
  const [manEndTime,   setManEndTime]   = useState('09:25')
  const [manNotes,     setManNotes]     = useState('')
  const [manSaving,    setManSaving]    = useState(false)

  const submitManual = async () => {
    if (!manPageId) {
      pushToast({ kind: 'error', title: 'Página obrigatória', detail: 'Selecione a página/disciplina desta sessão.' })
      return
    }
    if (!workspace) return
    let totalMin: number
    let startDt: Date
    let endDt: Date

    if (manMode === 'duration') {
      totalMin = (parseInt(manHours) || 0) * 60 + (parseInt(manMins) || 0)
      if (totalMin <= 0) {
        pushToast({ kind: 'error', title: 'Duração inválida', detail: 'Indique pelo menos 1 minuto.' })
        return
      }
      startDt = new Date(`${manDate}T${manStartTime}:00`)
      endDt   = new Date(startDt.getTime() + totalMin * 60_000)
    } else {
      startDt  = new Date(`${manDate}T${manStartTime}:00`)
      endDt    = new Date(`${manDate}T${manEndTime}:00`)
      if (endDt <= startDt) {
        pushToast({ kind: 'error', title: 'Horário inválido', detail: 'O fim deve ser depois do início.' })
        return
      }
      totalMin = Math.round((endDt.getTime() - startDt.getTime()) / 60_000)
    }

    setManSaving(true)
    const result = await fromIpc<TimeSession>(
      () => db().time.create({
        workspace_id: workspace.id,
        project_id:   projectId,
        page_id:      manPageId || null,
        duration_min: totalMin,
        session_type: 'manual',
        notes:        manNotes.trim() || null,
        tags:         null,
        started_at:   startDt.toISOString(),
        ended_at:     endDt.toISOString(),
      }),
      'timeCreateManual',
    )
    setManSaving(false)
    if (result.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao guardar sessão', detail: result.error.message })
      return
    }
    setSessions(prev => [result.value, ...prev])
    setManHours('0'); setManMins('25'); setManNotes('')
    setShowManual(false)
    pushToast({ kind: 'success', title: 'Sessão registada!' })
  }

  // ── Save timer session manually (finish early) ───────────────────────────────
  const finishEarly = async () => {
    if (!sessionStart || timerMode !== 'focus') return
    stopInterval()
    setTimerStatus('idle')
    const elapsed = Math.round((Date.now() - sessionStart.getTime()) / 60_000)
    if (elapsed >= 1) {
      await saveSession('pomodoro', elapsed, sessionStart, timerPageId || null)
      if (initialBlock?.blockId && onAutoLog) {
        const newTotal = Math.min(
          initialBlock.loggedHours + elapsed / 60,
          initialBlock.plannedHours
        )
        onAutoLog(initialBlock.blockId, newTotal)
      }
      pushToast({ kind: 'success', title: `Sessão de ${elapsed} min registada.` })
    }
    setSessionStart(null)
    setTimerMode('focus')
    setRemainSecs(FOCUS_MIN * 60)
    setTotalSecs(FOCUS_MIN * 60)
  }

  // ── Colors ────────────────────────────────────────────────────────────────────
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const accent = dark ? '#D4A820' : '#b8860b'

  // ── Total time today (for this project) ──────────────────────────────────────
  const today     = new Date().toISOString().slice(0, 10)
  const todayMins = sessions
    .filter(s => s.started_at.startsWith(today))
    .reduce((acc, s) => acc + s.duration_min, 0)

  return (
    <div className="study-timer-root">

      {/* ── Pomodoro section ────────────────────────────────────────────────── */}
      <div className="study-timer-left">
        <div className="study-clock-wrap">
          <AnimatedClock
            totalSecs={totalSecs}
            remainSecs={remainSecs}
            status={timerStatus}
            mode={timerMode}
            dark={dark}
          />
        </div>

        {/* active task indicator */}
        {initialBlock && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: accent,
            textAlign: 'center', marginBottom: 4, letterSpacing: '0.06em',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            maxWidth: 220 }}>
            ▶ {initialBlock.taskTitle}
          </div>
        )}

        {/* page selector */}
        <div className="study-page-sel">
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.12em', color: ink2 }}>
            PÁGINA *
          </span>
          <select
            className="settings-input"
            style={{ flex: 1, fontSize: 11, padding: '3px 6px',
              borderColor: !timerPageId ? '#8B3A2A44' : undefined }}
            value={timerPageId}
            onChange={e => setTimerPageId(e.target.value ? Number(e.target.value) : '')}
          >
            <option value="">— selecione —</option>
            {pages.map(p => (
              <option key={p.id} value={p.id}>
                {p.icon ?? '◦'} {p.title}
              </option>
            ))}
          </select>
        </div>

        {/* controls */}
        <div className="study-controls">
          {timerStatus === 'idle' && (
            <button className="btn study-btn-primary" onClick={startTimer}
              style={{ borderColor: accent, color: accent }}>
              ▶ Iniciar
            </button>
          )}
          {timerStatus === 'running' && (<>
            <button className="btn btn-sm" onClick={pauseTimer}
              style={{ borderColor: border, color: ink2 }}>
              ⏸ Pausar
            </button>
            {timerMode === 'focus' && (
              <button className="btn btn-sm" onClick={finishEarly}
                style={{ borderColor: border, color: ink2 }}>
                ✓ Terminar
              </button>
            )}
          </>)}
          {timerStatus === 'paused' && (<>
            <button className="btn study-btn-primary" onClick={resumeTimer}
              style={{ borderColor: accent, color: accent }}>
              ▶ Retomar
            </button>
            {timerMode === 'focus' && (
              <button className="btn btn-sm" onClick={finishEarly}
                style={{ borderColor: border, color: ink2 }}>
                ✓ Terminar
              </button>
            )}
          </>)}
          <button className="btn btn-ghost btn-sm" onClick={resetTimer}
            style={{ color: ink2 }}>
            ↺ Reset
          </button>
        </div>

        {/* today summary */}
        {todayMins > 0 && (
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2,
            textAlign: 'center', marginTop: 8, letterSpacing: '0.06em',
          }}>
            Hoje: <span style={{ color: accent }}>{fmtDuration(todayMins)}</span> neste projeto
          </div>
        )}
      </div>

      {/* ── Right panel: manual entry + history ─────────────────────────────── */}
      <div className="study-timer-right">

        {/* manual entry toggle */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.14em', color: ink2 }}>
            SESSÕES REGISTADAS
          </span>
          <button
            className="btn btn-sm"
            style={{ borderColor: accent, color: accent, fontSize: 10 }}
            onClick={() => setShowManual(o => !o)}
          >
            + Registo manual
          </button>
        </div>

        {/* manual entry form */}
        {showManual && (
          <div className="study-manual-form" style={{ background: cardBg, borderColor: border }}>
            {/* modo selector */}
            <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
              {(['duration','start_end'] as const).map(m => (
                <button key={m}
                  className="btn btn-sm"
                  style={{ fontSize: 9, padding: '2px 8px',
                    borderColor: manMode === m ? accent : border,
                    color: manMode === m ? accent : ink2 }}
                  onClick={() => setManMode(m)}>
                  {m === 'duration' ? 'Duração + início' : 'Início + fim'}
                </button>
              ))}
            </div>

            <div className="study-form-row">
              <label style={{ color: ink2 }}>Página *</label>
              <select className="settings-input" style={{ flex: 1, fontSize: 11 }}
                value={manPageId} onChange={e => setManPageId(e.target.value ? Number(e.target.value) : '')}>
                <option value="">— selecione —</option>
                {pages.map(p => (
                  <option key={p.id} value={p.id}>{p.icon ?? '◦'} {p.title}</option>
                ))}
              </select>
            </div>

            <div className="study-form-row">
              <label style={{ color: ink2 }}>Data</label>
              <input type="date" className="settings-input"
                style={{ flex: 1, fontSize: 11 }}
                value={manDate} onChange={e => setManDate(e.target.value)} />
            </div>

            {manMode === 'duration' ? (<>
              <div className="study-form-row">
                <label style={{ color: ink2 }}>Duração</label>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <input type="number" min="0" max="23" className="settings-input"
                    style={{ width: 52, fontSize: 11 }}
                    value={manHours} onChange={e => setManHours(e.target.value)} />
                  <span style={{ color: ink2, fontSize: 10 }}>h</span>
                  <input type="number" min="0" max="59" className="settings-input"
                    style={{ width: 52, fontSize: 11 }}
                    value={manMins} onChange={e => setManMins(e.target.value)} />
                  <span style={{ color: ink2, fontSize: 10 }}>min</span>
                </div>
              </div>
              <div className="study-form-row">
                <label style={{ color: ink2 }}>Início</label>
                <input type="time" className="settings-input"
                  style={{ flex: 1, fontSize: 11 }}
                  value={manStartTime} onChange={e => setManStartTime(e.target.value)} />
              </div>
              {manStartTime && (
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2,
                  textAlign: 'right', marginTop: -4 }}>
                  Fim calculado: {(() => {
                    const totalMin = (parseInt(manHours)||0)*60+(parseInt(manMins)||0)
                    const d = new Date(`${manDate}T${manStartTime}:00`)
                    d.setMinutes(d.getMinutes() + totalMin)
                    return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
                  })()}
                </div>
              )}
            </>) : (<>
              <div className="study-form-row">
                <label style={{ color: ink2 }}>Início</label>
                <input type="time" className="settings-input"
                  style={{ flex: 1, fontSize: 11 }}
                  value={manStartTime} onChange={e => setManStartTime(e.target.value)} />
              </div>
              <div className="study-form-row">
                <label style={{ color: ink2 }}>Fim</label>
                <input type="time" className="settings-input"
                  style={{ flex: 1, fontSize: 11 }}
                  value={manEndTime} onChange={e => setManEndTime(e.target.value)} />
              </div>
              {manStartTime && manEndTime && (
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2,
                  textAlign: 'right', marginTop: -4 }}>
                  {(() => {
                    const s = new Date(`${manDate}T${manStartTime}:00`)
                    const e = new Date(`${manDate}T${manEndTime}:00`)
                    const m = Math.max(0, Math.round((e.getTime()-s.getTime())/60_000))
                    const h = Math.floor(m/60), min = m%60
                    return `Duração calculada: ${h > 0 ? `${h}h ` : ''}${min}min`
                  })()}
                </div>
              )}
            </>)}

            <div className="study-form-row" style={{ alignItems: 'flex-start', marginTop: 4 }}>
              <label style={{ color: ink2, marginTop: 4 }}>Notas</label>
              <textarea className="settings-input"
                style={{ flex: 1, fontSize: 11, resize: 'vertical', minHeight: 40 }}
                value={manNotes} onChange={e => setManNotes(e.target.value)}
                placeholder="Observações opcionais…"
              />
            </div>

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 6 }}>
              <button className="btn btn-ghost btn-sm" style={{ color: ink2 }}
                onClick={() => setShowManual(false)}>Cancelar</button>
              <button className="btn btn-sm"
                style={{ borderColor: accent, color: accent }}
                onClick={submitManual} disabled={manSaving}>
                {manSaving ? 'A guardar…' : 'Guardar'}
              </button>
            </div>
          </div>
        )}

        {/* session list */}
        <div className="study-session-list">
          {sessions.length === 0 ? (
            <div style={{
              color: ink2, fontFamily: 'var(--font-mono)', fontSize: 11,
              fontStyle: 'italic', padding: '24px 0', textAlign: 'center', opacity: 0.6,
            }}>
              Nenhuma sessão registada ainda.
            </div>
          ) : sessions.map(s => (
            <div key={s.id} className="study-session-item"
              style={{ borderColor: border, background: cardBg }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 16, lineHeight: 1,
                  color: s.session_type === 'pomodoro' ? accent : ink2,
                }}>
                  {s.session_type === 'pomodoro' ? '◎' : '◦'}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 500,
                      color: accent, flexShrink: 0,
                    }}>
                      {fmtDuration(s.duration_min)}
                    </span>
                    {s.page_title && (
                      <span style={{
                        fontFamily: 'var(--font-mono)', fontSize: 10, color: ink,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {s.page_icon ?? '◦'} {s.page_title}
                      </span>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2 }}>
                      {fmtDate(s.started_at)}
                    </span>
                    {s.tags && s.tags.split(',').map(t => t.trim()).filter(Boolean).map(tag => (
                      <span key={tag} style={{
                        fontFamily: 'var(--font-mono)', fontSize: 8,
                        color: accent, border: `1px solid ${accent}44`,
                        borderRadius: 2, padding: '1px 4px', flexShrink: 0,
                      }}>
                        {tag}
                      </span>
                    ))}
                  </div>
                  {s.notes && (
                    <div style={{
                      fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2,
                      marginTop: 3, fontStyle: 'italic',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {s.notes}
                    </div>
                  )}
                </div>
              </div>
              <button
                className="btn btn-ghost btn-sm"
                style={{ color: ink2, opacity: 0.5, flexShrink: 0, fontSize: 11 }}
                onClick={() => deleteSession(s.id)}
                title="Eliminar sessão"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
