import React, { useCallback, useEffect, useRef, useState } from 'react'
import { fromIpc } from '../../types/errors'
import { useAppStore } from '../../store/useAppStore'
import { CosmosLayer } from '../../components/Cosmos/CosmosLayer'
import './GlobalPlannerView.css'

const db = () => (window as any).db

// ── Tipos e Constantes ────────────────────────────────────────────────────────
interface GlobalTask {
  id: number; project_id: number; page_id: number | null; title: string; task_type: string;
  due_date: string; estimated_hours: number; status: string; done_hours: number;
  project_name?: string; project_color?: string; project_icon?: string;
  page_title?: string; page_icon?: string;
}

interface AgendaBlock {
  id: number; task_id: number; date: string; planned_hours: number; logged_hours: number;
  status: string; task_title: string; task_type: string; due_date: string; estimated_hours: number;
  project_name: string; project_color: string; project_icon: string;
  page_title?: string; page_icon?: string;
}

const TASK_TYPES = ['atividade','aula','prova','trabalho','seminario','defesa','prazo','reuniao','leitura','outro']
const TYPE_LABELS: Record<string, string> = { atividade:'Atividade', aula:'Aula', prova:'Prova', trabalho:'Trabalho', seminario:'Seminário', defesa:'Defesa', prazo:'Prazo', reuniao:'Reunião', leitura:'Leitura', outro:'Outro' }
const TYPE_ICONS: Record<string, string> = { aula: '📚', atividade: '📋', prova: '📝', leitura: '📖', trabalho: '📋', seminario: '🎙', defesa: '🎓', prazo: '⏰', reuniao: '👥', outro: '◦' }
const STATUS_SYMBOL: Record<string, string> = { pending: '•', in_progress: '○', completed: '×', overdue: '!' }
const STATUS_LABEL: Record<string, string> = { pending: 'Pendente', in_progress: 'Em progresso', completed: 'Concluída', overdue: 'Atrasada' }

function daysUntil(dateStr: string) {
  const today = new Date(); today.setHours(0,0,0,0)
  const d = new Date(dateStr + 'T12:00:00'); d.setHours(0,0,0,0)
  return Math.round((d.getTime() - today.getTime()) / 86_400_000)
}
function fmtDate(iso: string) { return new Date(iso + 'T12:00:00').toLocaleDateString('pt-BR', { day:'2-digit', month:'short' }) }

// ── Mini calendário ───────────────────────────────────────────────────────────
function MiniCalendar({ tasksWithDates, filterDate, onFilterDate, dark }: { tasksWithDates: Set<string>; filterDate: string | null; onFilterDate: (d: string | null) => void; dark: boolean }) {
  const [cursor, setCursor] = useState(() => { const n = new Date(); return { year: n.getFullYear(), month: n.getMonth() } })
  const today = new Date().toISOString().slice(0, 10)
  const ink = dark ? '#E8DFC8' : '#2C2416', ink2 = dark ? '#8A7A62' : '#9C8E7A', accent = dark ? '#D4A820' : '#b8860b'
  const firstDay = new Date(cursor.year, cursor.month, 1).getDay()
  const daysInMonth = new Date(cursor.year, cursor.month + 1, 0).getDate()
  const cells: (number | null)[] = [ ...Array(firstDay).fill(null), ...Array.from({ length: daysInMonth }, (_, i) => i + 1) ]
  while (cells.length % 7 !== 0) cells.push(null)
  const monthLabel = new Date(cursor.year, cursor.month, 1).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })
  const isoOf = (d: number) => `${cursor.year}-${String(cursor.month + 1).padStart(2,'0')}-${String(d).padStart(2,'0')}`

  return (
    <div className="bj-mini-cal">
      <div className="bj-mini-cal-header">
        <button className="bj-cal-nav" onClick={() => setCursor(c => { const d = new Date(c.year, c.month - 1); return { year: d.getFullYear(), month: d.getMonth() } })}>‹</button>
        <span style={{ fontFamily:'var(--font-mono)', fontSize:10, letterSpacing:'0.12em', color: ink, textTransform:'uppercase' }}>{monthLabel}</span>
        <button className="bj-cal-nav" onClick={() => setCursor(c => { const d = new Date(c.year, c.month + 1); return { year: d.getFullYear(), month: d.getMonth() } })}>›</button>
      </div>
      <div className="bj-mini-cal-grid">
        {['D','S','T','Q','Q','S','S'].map((d,i) => <div key={i} style={{ fontFamily:'var(--font-mono)', fontSize:9, color:ink2, textAlign:'center' }}>{d}</div>)}
        {cells.map((day, i) => {
          if (!day) return <div key={i} />
          const iso = isoOf(day), isToday = iso === today, selected = iso === filterDate, hasTasks = tasksWithDates.has(iso)
          return (
            <button key={i} className={`bj-cal-day${isToday ? ' bj-cal-day--today' : ''}${selected ? ' bj-cal-day--selected' : ''}`}
              onClick={() => onFilterDate(selected ? null : iso)}
              style={{ color: isToday ? accent : selected ? accent : ink, background: selected ? accent + '22' : 'transparent', borderColor: isToday ? accent : 'transparent' }}>
              {day}
              {hasTasks && !isToday && <span style={{ display:'block', width:3, height:3, borderRadius:'50%', background: accent, margin:'1px auto 0', opacity:0.5 }} />}
            </button>
          )
        })}
      </div>
      {filterDate && <button className="bj-cal-clear" onClick={() => onFilterDate(null)} style={{ color: ink2 }}>limpar filtro ×</button>}
    </div>
  )
}

// ── Item de tarefa Urgente ────────────────────────────────────────────────────
function UrgentTaskItem({ task, dark, onToggleDone }: { task: GlobalTask; dark: boolean; onToggleDone: (t: GlobalTask) => void }) {
  const ink = dark ? '#E8DFC8' : '#2C2416', ink2 = dark ? '#8A7A62' : '#9C8E7A', accent = dark ? '#D4A820' : '#b8860b'
  const days = daysUntil(task.due_date), color = task.project_color ?? '#8B7355'
  const symbolColor = task.status === 'overdue' ? '#C0392B' : task.status === 'completed' ? ink2 : task.status === 'in_progress' ? accent : ink
  return (
    <div className="bj-urgent-item" style={{ opacity: task.status === 'completed' ? 0.45 : 1 }}>
      <button className="bj-bullet-btn" onClick={() => onToggleDone(task)} style={{ color: symbolColor }}>{STATUS_SYMBOL[task.status] ?? '•'}</button>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontFamily:'var(--font-mono)', fontSize:11, color: ink, textDecoration: task.status === 'completed' ? 'line-through' : 'none', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{task.title}</div>
        <div style={{ display:'flex', gap:6, marginTop:2, alignItems:'center' }}>
          <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color: color }}>{task.project_icon ?? '◦'} {task.project_name}</span>
          {task.page_title && <><span style={{ color: ink2, fontSize: 8 }}>/</span><span style={{ fontFamily:'var(--font-mono)', fontSize:9, color: ink }}>{task.page_icon ?? '◦'} {task.page_title}</span></>}
        </div>
      </div>
      <span style={{ fontFamily:'var(--font-mono)', fontSize:9, flexShrink:0, color: days < 0 ? '#C0392B' : days === 0 ? accent : ink2 }}>{days < 0 ? `${Math.abs(days)}d atrás` : days === 0 ? 'hoje' : `${days}d`}</span>
    </div>
  )
}

// ── Bloco da Agenda (Direita) ─────────────────────────────────────────────────
function AgendaBlockItem({ block, dark, onStartFocus }: { block: AgendaBlock; dark: boolean; onStartFocus: (b: AgendaBlock) => void }) {
  const ink = dark ? '#E8DFC8' : '#2C2416', ink2 = dark ? '#8A7A62' : '#9C8E7A', accent = dark ? '#D4A820' : '#b8860b'
  const color = block.project_color ?? '#8B7355'
  const pct = block.planned_hours > 0 ? Math.min(1, (block.logged_hours || 0) / block.planned_hours) : 0

  return (
    <div className="bj-block-item">
      <div style={{ width:3, alignSelf:'stretch', borderRadius:2, background: color, flexShrink:0 }} />
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
          <span style={{ fontFamily:'var(--font-mono)', fontSize:11, color: ink, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', flex:1 }}>{block.task_title}</span>
          <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color: ink2, flexShrink:0, marginLeft:6 }}>{block.planned_hours}h</span>
        </div>
        <div style={{ marginTop:4, height:2, background: dark ? '#2A2418' : '#D8D0C0', borderRadius:1 }}>
          <div style={{ width:`${pct*100}%`, height:'100%', background: color, borderRadius:1, transition:'width 0.3s' }} />
        </div>
        <div style={{ display:'flex', gap:8, marginTop:4, alignItems:'center' }}>
          <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color: color }}>{block.project_icon} {block.project_name}</span>
          {block.page_title && <><span style={{ color: ink2, fontSize: 8 }}>/</span><span style={{ fontFamily:'var(--font-mono)', fontSize:9, color: ink }}>{block.page_icon ?? '◦'} {block.page_title}</span></>}
          <span style={{ flex:1 }} />
          <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color: ink2 }}>{block.logged_hours > 0 ? `${block.logged_hours}h reg.` : ''}</span>
          <button className="btn btn-sm" style={{ borderColor: accent, color: accent, fontSize:9, padding:'2px 8px' }} onClick={() => onStartFocus(block)}>▶ Focar</button>
        </div>
      </div>
    </div>
  )
}

// ── Visualização Pomodoro (relógio de bolso + ampulheta com estrelas) ────────
function PomodoroVisual({ progress, timeLeft, isRunning, accent, dark, ink, ink2, border }: {
  progress: number; timeLeft: number; isRunning: boolean;
  accent: string; dark: boolean; ink: string; ink2: string; border: string;
}) {
  const [vizMode, setVizMode] = useState<'clock'|'hourglass'>('clock')
  const mins = Math.floor(timeLeft / 60).toString().padStart(2, '0')
  const secs = (timeLeft % 60).toString().padStart(2, '0')

  const now = new Date()
  const hourAngle = ((now.getHours() % 12) / 12 + now.getMinutes() / 720) * 360
  const minuteAngle = progress * 360

  const caseBg     = dark ? '#2C2212' : '#DDD0A8'
  const faceBg     = dark ? '#1C1608' : '#F7F2E8'
  const frameColor = dark ? '#7A6030' : '#8B6914'
  const glassColor = dark ? '#18140A' : '#EDE8DC'
  const C60        = 2 * Math.PI * 60

  const ticks = Array.from({ length: 12 }, (_, i) => {
    const a = (i / 12) * Math.PI * 2 - Math.PI / 2
    const main = i % 3 === 0
    return { x1: 65 + Math.cos(a) * 49, y1: 86 + Math.sin(a) * 49,
             x2: 65 + Math.cos(a) * (main ? 42 : 46), y2: 86 + Math.sin(a) * (main ? 42 : 46), main }
  })

  // Areia: topo vai descendo conforme o tempo passa (de y=17 até y=68)
  const sandTop    = 17 + progress * 51
  // Areia inferior: sobe conforme tempo passa (de y=133 até y=82)
  const sandBotTop = 133 - progress * 51

  // Estrelas dentro da areia (visíveis apenas quando cobertas pela areia)
  const topStars = [{x:25,y:28},{x:67,y:23},{x:50,y:40},{x:73,y:32},{x:36,y:50},{x:58,y:57}]
    .filter(s => s.y >= sandTop - 1 && s.y <= 66)
  const botStars = [{x:30,y:122},{x:62,y:112},{x:74,y:128},{x:30,y:109},{x:50,y:120}]
    .filter(s => s.y >= sandBotTop - 1 && s.y <= 131)

  return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:4 }}>
      {/* Toggle relógio / ampulheta */}
      <div style={{ display:'flex', border:`1px solid ${border}`, borderRadius:3, overflow:'hidden' }}>
        <button onClick={() => setVizMode('clock')}
          style={{ padding:'2px 9px', fontSize:8, fontFamily:'var(--font-mono)', letterSpacing:'0.06em',
            background: vizMode==='clock' ? `${accent}22` : 'transparent', border:'none',
            borderRight:`1px solid ${border}`, color: vizMode==='clock' ? accent : ink2, cursor:'pointer' }}>
          ⟳ RELÓGIO
        </button>
        <button onClick={() => setVizMode('hourglass')}
          style={{ padding:'2px 9px', fontSize:8, fontFamily:'var(--font-mono)', letterSpacing:'0.06em',
            background: vizMode==='hourglass' ? `${accent}22` : 'transparent', border:'none',
            color: vizMode==='hourglass' ? accent : ink2, cursor:'pointer' }}>
          ⌛ AMPULHETA
        </button>
      </div>

      {vizMode === 'clock' ? (
        /* ── Relógio de bolso ────────────────────────────────────────── */
        <svg width="130" height="152" viewBox="0 0 130 152">
          {/* Coroa (botão de dar corda) */}
          <rect x="57" y="1" width="16" height="12" rx="4" fill={caseBg} stroke={frameColor} strokeWidth="1.5" />
          <line x1="61" y1="3" x2="61" y2="11" stroke={accent} strokeWidth="0.7" opacity="0.5" />
          <line x1="65" y1="3" x2="65" y2="11" stroke={accent} strokeWidth="0.7" opacity="0.5" />
          <line x1="69" y1="3" x2="69" y2="11" stroke={accent} strokeWidth="0.7" opacity="0.5" />
          {/* Caixa exterior */}
          <circle cx="65" cy="86" r="60" fill={caseBg} stroke={frameColor} strokeWidth="3" />
          {/* Arco de progresso (varre de 12h no sentido horário) */}
          <circle cx="65" cy="86" r="60" fill="none" stroke={accent} strokeWidth="3.5"
            strokeDasharray={C60} strokeDashoffset={C60 * (1 - progress)}
            transform="rotate(-90 65 86)" strokeLinecap="round" opacity="0.75" />
          {/* Anel interior do bisel */}
          <circle cx="65" cy="86" r="56" fill="none" stroke={frameColor} strokeWidth="1" opacity="0.4" />
          {/* Face do mostrador */}
          <circle cx="65" cy="86" r="53" fill={faceBg} />
          {/* Anéis decorativos guilhoché */}
          <circle cx="65" cy="86" r="50" fill="none" stroke={accent} strokeWidth="0.5" opacity="0.15" />
          <circle cx="65" cy="86" r="46" fill="none" stroke={accent} strokeWidth="0.4" opacity="0.10" />
          {/* Marcações das horas */}
          {ticks.map((t, i) => (
            <line key={i} x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2}
              stroke={t.main ? accent : ink2} strokeWidth={t.main ? 2 : 0.8}
              opacity={t.main ? 0.8 : 0.35} />
          ))}
          {/* Ponteiro das horas (hora real) */}
          <g transform={`rotate(${hourAngle.toFixed(1)} 65 86)`}>
            <line x1="65" y1="86" x2="65" y2="65" stroke={ink} strokeWidth="3.5" strokeLinecap="round" opacity="0.65" />
            <line x1="65" y1="86" x2="65" y2="90" stroke={ink} strokeWidth="3.5" strokeLinecap="round" opacity="0.40" />
          </g>
          {/* Ponteiro dos minutos (progresso Pomodoro) */}
          <g transform={`rotate(${minuteAngle.toFixed(1)} 65 86)`}>
            <line x1="65" y1="86" x2="65" y2="52" stroke={accent} strokeWidth="2" strokeLinecap="round" />
            <line x1="65" y1="86" x2="65" y2="93" stroke={accent} strokeWidth="3" strokeLinecap="round" opacity="0.50" />
          </g>
          {/* Jóia central */}
          <circle cx="65" cy="86" r="5" fill={caseBg} stroke={accent} strokeWidth="1.5" />
          <circle cx="65" cy="86" r="2.5" fill={accent} />
          {/* Display digital */}
          <text x="65" y="110" textAnchor="middle" fontFamily="var(--font-mono)" fontSize="11" fill={ink} opacity="0.75">{mins}:{secs}</text>
        </svg>
      ) : (
        /* ── Ampulheta com estrelas ───────────────────────────────────── */
        <svg width="100" height="155" viewBox="0 0 100 155">
          <defs>
            <clipPath id="pomo-clip-top"><polygon points="10,17 90,17 54,68 46,68" /></clipPath>
            <clipPath id="pomo-clip-bot"><polygon points="46,82 54,82 90,133 10,133" /></clipPath>
          </defs>
          {/* Moldura superior */}
          <rect x="4" y="4" width="92" height="14" rx="4" fill={frameColor} opacity="0.85" />
          <line x1="9" y1="9"  x2="91" y2="9"  stroke={accent} strokeWidth="0.6" opacity="0.35" />
          <line x1="9" y1="13" x2="91" y2="13" stroke={accent} strokeWidth="0.4" opacity="0.20" />
          {/* Moldura inferior */}
          <rect x="4" y="133" width="92" height="14" rx="4" fill={frameColor} opacity="0.85" />
          <line x1="9" y1="138" x2="91" y2="138" stroke={accent} strokeWidth="0.6" opacity="0.35" />
          <line x1="9" y1="142" x2="91" y2="142" stroke={accent} strokeWidth="0.4" opacity="0.20" />
          {/* Vidro — metade superior */}
          <polygon points="10,17 90,17 54,68 46,68" fill={glassColor} stroke={accent} strokeWidth="1.5" />
          {/* Gargalo */}
          <rect x="46" y="68" width="8" height="14" fill={glassColor} stroke={accent} strokeWidth="1.2" />
          {/* Vidro — metade inferior */}
          <polygon points="46,82 54,82 90,133 10,133" fill={glassColor} stroke={accent} strokeWidth="1.5" />
          {/* Areia superior (vai diminuindo) */}
          <rect x="0" y={sandTop} width="100" height={Math.max(0, 68 - sandTop)}
            fill={accent} opacity="0.32" clipPath="url(#pomo-clip-top)" />
          {/* Estrelas na areia superior */}
          {topStars.map((s, i) => (
            <circle key={i} cx={s.x} cy={s.y} r="1.8" fill={accent} opacity="0.60"
              className="pomo-star" style={{ animationDelay:`${i * 0.37}s` }} />
          ))}
          {/* Partículas a cair pelo gargalo */}
          {isRunning && [0, 0.22, 0.44].map((delay, i) => (
            <circle key={i} cx={50 + (i - 1)} cy="68" r="1.5" fill={accent} opacity="0.85"
              className="pomo-particle" style={{ animationDelay:`${delay}s` }} />
          ))}
          {/* Areia inferior (vai aumentando) */}
          <rect x="0" y={sandBotTop} width="100" height={Math.max(0, 133 - sandBotTop)}
            fill={accent} opacity="0.42" clipPath="url(#pomo-clip-bot)" />
          {/* Estrelas na areia inferior */}
          {botStars.map((s, i) => (
            <circle key={i} cx={s.x} cy={s.y} r="1.8" fill={accent} opacity="0.70"
              className="pomo-star" style={{ animationDelay:`${(i + 3) * 0.3}s` }} />
          ))}
          {/* Display digital */}
          <text x="50" y="152" textAnchor="middle" fontFamily="var(--font-mono)" fontSize="10" fill={ink} opacity="0.70">{mins}:{secs}</text>
        </svg>
      )}
    </div>
  )
}

// ── Widget Pomodoro / Foco (Esquerda) ─────────────────────────────────────────
function PomodoroWidget({ dark, block, onLogWork, onClear }: { dark: boolean; block: AgendaBlock | null; onLogWork: (h: number, s?: string, e?: string) => void; onClear: () => void }) {
  const ink = dark ? '#E8DFC8' : '#2C2416', ink2 = dark ? '#8A7A62' : '#9C8E7A', accent = dark ? '#D4A820' : '#b8860b', cardBg = dark ? '#1E1A12' : '#EAE4D8', border = dark ? '#3A3020' : '#C4B9A8'
  const [mode, setMode] = useState<'timer'|'manual'>('timer')
  const [timeLeft, setTimeLeft] = useState(25 * 60)
  const [isRunning, setIsRunning] = useState(false)
  
  // Manual state
  const [mStart, setMStart] = useState('')
  const [mEnd, setMEnd] = useState('')
  const [mHours, setMHours] = useState('1.0')

  // Auto-calcular horas no modo manual
  useEffect(() => {
    if (mStart && mEnd) {
      const [sh, sm] = mStart.split(':').map(Number); const [eh, em] = mEnd.split(':').map(Number)
      let diff = (eh * 60 + em) - (sh * 60 + sm)
      if (diff < 0) diff += 24 * 60
      setMHours((diff / 60).toFixed(2))
    }
  }, [mStart, mEnd])

  // Lógica do Timer
  useEffect(() => {
    let interval: any;
    if (isRunning && timeLeft > 0) interval = setInterval(() => setTimeLeft(t => t - 1), 1000)
    else if (timeLeft === 0 && isRunning) {
      setIsRunning(false); onLogWork(25 / 60); setTimeLeft(25 * 60) // Registra 25 min e reseta
    }
    return () => clearInterval(interval)
  }, [isRunning, timeLeft, onLogWork])

  const toggleTimer = () => setIsRunning(!isRunning)
  const resetTimer = () => { setIsRunning(false); setTimeLeft(25 * 60) }
  
  const submitManual = () => {
    const h = parseFloat(mHours)
    if (!isNaN(h) && h > 0) {
      const sDate = mStart ? `${new Date().toISOString().slice(0,10)}T${mStart}:00` : undefined
      const eDate = mEnd ? `${new Date().toISOString().slice(0,10)}T${mEnd}:00` : undefined
      onLogWork(h, sDate, eDate)
      setMStart(''); setMEnd(''); setMHours('1.0')
    }
  }

  const progress = 1 - (timeLeft / (25 * 60))

  return (
    <div className="bj-section" style={{ background: cardBg, borderColor: border, padding: 16, borderRadius: 8, borderWidth: 1, borderStyle: 'solid' }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom: 12 }}>
        <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color: accent, letterSpacing:'0.12em' }}>◈ FOCO ATUAL</div>
        {block && <button onClick={onClear} style={{ background:'transparent', border:'none', color:ink2, cursor:'pointer', fontSize:14 }}>×</button>}
      </div>

      {/* Info do bloco ativo — só aparece quando há bloco selecionado */}
      {block ? (
        <div style={{ textAlign:'center', marginBottom: 12 }}>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color: block.project_color ?? ink }}>{block.project_icon} {block.project_name}</div>
          <div style={{ fontFamily:'var(--font-display)', fontSize:15, color: ink, marginTop:3, fontStyle:'italic' }}>{block.task_title}</div>
        </div>
      ) : (
        <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color: ink2, fontStyle:'italic', textAlign:'center', marginBottom: 10 }}>
          Nenhum bloco selecionado — clique "▶ Focar" na Agenda para vincular.
        </div>
      )}

      <div style={{ display:'flex', gap:0, marginBottom:14, borderBottom:`1px solid ${border}` }}>
        <button style={{ flex:1, padding:'6px 0', fontSize:9, fontFamily:'var(--font-mono)', background:'transparent', border:'none', borderBottom: mode==='timer'?`2px solid ${accent}`:'2px solid transparent', color: mode==='timer'?accent:ink2 }} onClick={() => setMode('timer')}>TIMER</button>
        <button style={{ flex:1, padding:'6px 0', fontSize:9, fontFamily:'var(--font-mono)', background:'transparent', border:'none', borderBottom: mode==='manual'?`2px solid ${accent}`:'2px solid transparent', color: mode==='manual'?accent:ink2 }} onClick={() => setMode('manual')}>MANUAL</button>
      </div>

      {mode === 'timer' ? (
        <div style={{ display:'flex', flexDirection:'column', alignItems:'center' }}>
          <PomodoroVisual progress={progress} timeLeft={timeLeft} isRunning={isRunning}
            accent={accent} dark={dark} ink={ink} ink2={ink2} border={border} />
          <div style={{ display:'flex', gap:8, marginTop:8 }}>
            <button className="btn btn-sm" style={{ borderColor: accent, color: accent, width: 80 }} onClick={toggleTimer}>{isRunning ? 'Pausar' : 'Iniciar'}</button>
            <button className="btn btn-ghost btn-sm" style={{ color: ink2 }} onClick={resetTimer}>Reset</button>
          </div>
          {!block && isRunning && (
            <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color: ink2, fontStyle:'italic', marginTop:8, textAlign:'center' }}>
              O tempo corre mas não será registado sem um bloco vinculado.
            </div>
          )}
        </div>
      ) : (
        <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
          <div style={{ display:'flex', gap:8 }}>
            <div style={{ flex:1 }}><label style={{ display:'block', fontSize:9, color:ink2, marginBottom:2 }}>INÍCIO</label><input type="time" className="settings-input" style={{ width:'100%', fontSize:11 }} value={mStart} onChange={e=>setMStart(e.target.value)} /></div>
            <div style={{ flex:1 }}><label style={{ display:'block', fontSize:9, color:ink2, marginBottom:2 }}>FIM</label><input type="time" className="settings-input" style={{ width:'100%', fontSize:11 }} value={mEnd} onChange={e=>setMEnd(e.target.value)} /></div>
          </div>
          <div><label style={{ display:'block', fontSize:9, color:ink2, marginBottom:2 }}>TOTAL (HORAS)</label><input type="number" step="0.25" className="settings-input" style={{ width:'100%', fontSize:11 }} value={mHours} onChange={e=>setMHours(e.target.value)} /></div>
          <button className="btn btn-sm"
            style={{ borderColor: block ? accent : border, color: block ? accent : ink2, width:'100%', marginTop:8 }}
            disabled={!block} onClick={submitManual}>
            {block ? 'Registar Foco' : 'Selecione um bloco para registar'}
          </button>
        </div>
      )}
    </div>
  )
}


// ── Item de tarefa (Lista Completa) ───────────────────────────────────────────
function TaskRow({ task, dark, expanded, onExpand, projects }: { task: GlobalTask; dark: boolean; expanded: boolean; onExpand: () => void; projects: any[] }) {
  const ink = dark ? '#E8DFC8' : '#2C2416', ink2 = dark ? '#8A7A62' : '#9C8E7A', accent = dark ? '#D4A820' : '#b8860b', border = dark ? '#3A3020' : '#C4B9A8', color = task.project_color ?? '#8B7355'
  const days = daysUntil(task.due_date), symbolColor = task.status === 'overdue' ? '#C0392B' : task.status === 'completed' ? ink2 : task.status === 'in_progress' ? accent : ink
  return (
    <div className={`bj-task-row${expanded ? ' bj-task-row--expanded' : ''}`} style={{ borderColor: expanded ? color + '66' : border }}>
      <div className="bj-task-main" onClick={onExpand}>
        <span className="bj-bullet" style={{ color: symbolColor }}>{STATUS_SYMBOL[task.status] ?? '•'}</span>
        <div style={{ flex:1, minWidth:0 }}>
          <span style={{ fontFamily:'var(--font-mono)', fontSize:11, color: ink, textDecoration: task.status === 'completed' ? 'line-through' : 'none' }}>{task.title}</span>
          <div style={{ display:'flex', gap:6, marginTop:2, alignItems:'center', flexWrap:'wrap' }}>
            <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color, letterSpacing:'0.04em' }}>{task.project_icon ?? '◦'} {task.project_name}</span>
            {task.page_title && <><span style={{ color: ink2, fontSize: 8 }}>/</span><span style={{ fontFamily:'var(--font-mono)', fontSize:9, color: ink, letterSpacing:'0.04em' }}>{task.page_icon ?? '◦'} {task.page_title}</span></>}
            <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color: ink2, marginLeft: 'auto' }}>{TYPE_LABELS[task.task_type] ?? task.task_type}</span>
          </div>
        </div>
        <div style={{ display:'flex', flexDirection:'column', alignItems:'flex-end', gap:2, flexShrink:0 }}>
          <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color: days < 0 ? '#C0392B' : days === 0 ? accent : days <= 3 ? '#C07020' : ink2 }}>{fmtDate(task.due_date)}</span>
          <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color: ink2 }}>{(task.done_hours ?? 0).toFixed(1)}/{task.estimated_hours}h</span>
        </div>
      </div>
    </div>
  )
}

// ── Vista principal ───────────────────────────────────────────────────────────
interface Props { dark: boolean; onProjectOpen: (id: number) => void }

export function GlobalPlannerView({ dark, onProjectOpen }: Props) {
  const { projects, pushToast } = useAppStore()
  const containerRef = useRef<HTMLDivElement>(null)
  const [narrow, setNarrow] = useState(false)

  // Dados
  const [tasks, setTasks] = useState<GlobalTask[]>([])
  const [agendaBlocks, setAgendaBlocks] = useState<AgendaBlock[]>([])
  const [loading, setLoading] = useState(true)

  // Layout & Tabs
  const [rightTab, setRightTab] = useState<'tasks' | 'agenda'>('agenda')
  const [filterDate, setFilterDate] = useState<string | null>(null)
  const [groupBy, setGroupBy] = useState<'date' | 'project'>('date')
  const [showCompleted, setShowCompleted] = useState(false)
  const [daysToShow, setDaysToShow] = useState<1 | 2 | 3>(3)
  
  // Pomodoro
  const [activeFocus, setActiveFocus] = useState<AgendaBlock | null>(null)
  const activeFocusRef = useRef<AgendaBlock | null>(null)
  useEffect(() => { activeFocusRef.current = activeFocus }, [activeFocus])
  const [scheduling, setScheduling] = useState(false)

  const ink2 = dark ? '#8A7A62' : '#9C8E7A', accent = dark ? '#D4A820' : '#b8860b', border = dark ? '#3A3020' : '#C4B9A8'

  useEffect(() => {
    const el = containerRef.current; if (!el) return
    const obs = new ResizeObserver(entries => { for (const e of entries) setNarrow(e.contentRect.width < 860) })
    obs.observe(el); return () => obs.disconnect()
  }, [])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const safeBaseDate = (typeof filterDate === 'string' && filterDate.length >= 10)
        ? filterDate.slice(0, 10)
        : new Date().toISOString().slice(0, 10)

      const tasksRes = await fromIpc<GlobalTask[]>(() => db().planner.listAllTasks({ include_completed: showCompleted }), 'listAllTasks')
      tasksRes.match(d => setTasks(d || []), () => setTasks([]))

      const numDays = daysToShow || 3
      const datesToFetch = Array.from({ length: numDays }).map((_, i) => {
        const d = new Date(safeBaseDate + 'T12:00:00')
        d.setDate(d.getDate() + i)
        return d.toISOString().slice(0, 10)
      })

      const allBlocks: AgendaBlock[] = []
      for (const dateStr of datesToFetch) {
        const res = await fromIpc<AgendaBlock[]>(() => db().planner.todayBlocks(dateStr), 'todayBlocks')
        res.match(d => { if (d && Array.isArray(d)) allBlocks.push(...d) }, () => {})
      }

      setAgendaBlocks(allBlocks)

      if (activeFocusRef.current && !allBlocks.find(b => b.id === activeFocusRef.current!.id)) {
        setActiveFocus(null)
      }

    } catch (error) {
      console.error("🚨 ERRO CRÍTICO NO LOADDATA:", error)
    } finally {
      setLoading(false)
    }
  }, [showCompleted, filterDate, daysToShow])

      // Carregar dados quando o componente montar ou quando as dependências mudarem
      useEffect(() => {
        loadData()
      }, [loadData])

      // Lógica do Log Manual do Pomodoro
  const handleLogWork = async (hours: number, startTime?: string, endTime?: string) => {
    if (!activeFocus) return
    const res = await fromIpc(() => db().planner.logWork({ block_id: activeFocus.id, task_id: activeFocus.task_id, hours, start_time: startTime, end_time: endTime }), 'logWork')
    if (res.isOk()) { pushToast({ kind:'success', title:`+${hours.toFixed(2)}h registadas!` }); loadData() }
    else pushToast({ kind:'error', title:'Erro ao registar tempo.' })
  }

  const handleRescheduleAll = async () => {
    setScheduling(true)
    const r = await fromIpc(() => db().planner.rescheduleAll(), 'rescheduleAll')
    if (r.isOk()) { pushToast({ kind:'success', title:'Reagendamento concluído!' }); loadData() }
    else pushToast({ kind:'error', title:'Erro ao reagendar.' })
    setScheduling(false)
  }

  const taskDates = new Set(tasks.map(t => t.due_date))
  const today3 = new Date(); today3.setDate(today3.getDate() + 2)
  const urgentTasks = tasks.filter(t => t.status !== 'completed' && new Date(t.due_date + 'T12:00:00') <= today3)

  const filteredTasks = tasks
  const groupedTasks = (() => {
    if (groupBy === 'project') {
      const map = new Map<number, GlobalTask[]>()
      for (const t of filteredTasks) { if (!map.has(t.project_id)) map.set(t.project_id, []); map.get(t.project_id)!.push(t) }
      return Array.from(map.entries()).map(([pid, ts]) => ({ key: String(pid), label: ts[0]?.project_name ?? `Projeto`, color: ts[0]?.project_color, tasks: ts }))
    } else {
      const map = new Map<string, GlobalTask[]>()
      for (const t of filteredTasks) { if (!map.has(t.due_date)) map.set(t.due_date, []); map.get(t.due_date)!.push(t) }
      // ↓ A linha abaixo foi atualizada para incluir "color: undefined" ↓
      return Array.from(map.entries()).map(([date, ts]) => ({ key: date, label: fmtDate(date), color: undefined, tasks: ts }))
    }
  })()

  const handleToggleDone = async (task: GlobalTask) => {
    const newStatus = task.status === 'completed' ? 'pending' : 'completed'
    const r = await fromIpc(() => db().planner.updateTask({ id: task.id, status: newStatus }), 'updateTaskStatus')
    if (r.isOk()) setTasks(prev => prev.map(t => t.id === task.id ? { ...t, status: newStatus } : t))
  }

  const now = new Date()
  const weekDays = ['Domingo','Segunda-feira','Terça-feira','Quarta-feira','Quinta-feira','Sexta-feira','Sábado']
  const monthNames = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
  const dateLabel = `${weekDays[now.getDay()]} · ${now.getDate()} de ${monthNames[now.getMonth()]} · ${now.getFullYear()}`

  return (
    <div ref={containerRef} className="bj-root" style={{ position:'relative' }}>
      <div className="bj-dot-bg" />
      <CosmosLayer width={1400} height={900} seed="planner_global" density="low" dark={dark} style={{ position:'absolute', top:0, left:0, opacity: dark ? 0.18 : 0.08, pointerEvents:'none', zIndex:0 }} />

      <div className={`bj-columns${narrow ? ' bj-columns--narrow' : ''}`} style={{ position:'relative', zIndex:1 }}>

        {/* ── COLUNA ESQUERDA ───────────────────────────────────────────── */}
        <div className="bj-col-left">
          <div className="bj-date-header">
            <div style={{ fontFamily:'var(--font-mono)', fontSize:9, letterSpacing:'0.20em', color: ink2, marginBottom:4 }}>{dateLabel.toUpperCase()}</div>
            <div style={{ width:32, height:1, background: accent, marginBottom:12, opacity:0.5 }} />
          </div>

          <MiniCalendar tasksWithDates={taskDates} filterDate={filterDate} onFilterDate={setFilterDate} dark={dark} />
          <div className="bj-section-sep" style={{ borderColor: border }} />

          {/* FOCO / POMODORO */}
          <PomodoroWidget dark={dark} block={activeFocus} onLogWork={handleLogWork} onClear={() => setActiveFocus(null)} />

          <div className="bj-section-sep" style={{ borderColor: border }} />

          <div className="bj-section">
            <div className="bj-section-label" style={{ color: ink2 }}>! URGENTE · PRÓXIMOS 3 DIAS</div>
            {urgentTasks.length === 0 ? <div style={{ fontFamily:'var(--font-mono)', fontSize:10, color: ink2, fontStyle:'italic', opacity:0.5, padding:'8px 0' }}>nenhuma tarefa urgente</div>
              : urgentTasks.map(t => <UrgentTaskItem key={t.id} task={t} dark={dark} onToggleDone={handleToggleDone} />)}
          </div>
        </div>

        {!narrow && <div className="bj-page-divider" style={{ borderColor: border }} />}

        {/* ── COLUNA DIREITA ────────────────────────────────────────────── */}
        <div className="bj-col-right">
          
          {/* HEADER DA DIREITA (TABS) */}
          <div className="bj-right-header" style={{ borderBottom: `1px solid ${border}`, paddingBottom: 16, marginBottom: 16 }}>
            <div style={{ display: 'flex', gap: 16, flex: 1 }}>
              <button onClick={() => setRightTab('agenda')} style={{ background:'transparent', border:'none', fontFamily:'var(--font-mono)', fontSize:12, letterSpacing:'0.1em', cursor:'pointer', borderBottom: rightTab==='agenda'?`2px solid ${accent}`:'2px solid transparent', color: rightTab==='agenda'?accent:ink2, paddingBottom:4 }}>
                AGENDA {filterDate ? `(${fmtDate(filterDate)})` : '(HOJE)'}
              </button>
              <button onClick={() => setRightTab('tasks')} style={{ background:'transparent', border:'none', fontFamily:'var(--font-mono)', fontSize:12, letterSpacing:'0.1em', cursor:'pointer', borderBottom: rightTab==='tasks'?`2px solid ${accent}`:'2px solid transparent', color: rightTab==='tasks'?accent:ink2, paddingBottom:4 }}>
                TAREFAS ABERTAS
              </button>
            </div>
            <button className="btn btn-sm" onClick={handleRescheduleAll} disabled={scheduling}
              style={{ borderColor: accent, color: accent, flexShrink:0, opacity: scheduling ? 0.5 : 1 }}>
              {scheduling ? '…' : '↺ Reagendar'}
            </button>
          </div>

          <div className="bj-task-list">
            {loading ? <div style={{ fontFamily:'var(--font-mono)', fontSize:11, color:ink2, padding:'32px 0', textAlign:'center', opacity:0.5 }}>A carregar…</div> : 
             
             rightTab === 'agenda' ? (
              /* MODO AGENDA */
              <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
                {(() => {
                  const baseDate = (typeof filterDate === 'string' && filterDate.length >= 10)
                    ? filterDate.slice(0, 10)
                    : new Date().toISOString().slice(0, 10)
                  const renderDates = Array.from({ length: daysToShow || 3 }).map((_, i) => {
                    const d = new Date(baseDate + 'T12:00:00')
                    d.setDate(d.getDate() + i)
                    return d.toISOString().slice(0, 10)
                  })
                  const todayStr = new Date().toISOString().slice(0, 10)

                  return renderDates.map(dateStr => {
                    const blocks = agendaBlocks.filter(b => b.date === dateStr)
                    const dateObj = new Date(dateStr + 'T12:00:00')
                    const dayLabel = dateObj.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: 'short' }).replace(/\./g, '')
                    const isToday = dateStr === todayStr

                    return (
                      <div key={dateStr}>
                        <div style={{
                          fontFamily: 'var(--font-mono)', fontSize: 11,
                          letterSpacing: '0.12em', color: isToday ? accent : ink2,
                          borderBottom: `1px solid ${isToday ? accent : border}`,
                          paddingBottom: 4, marginBottom: 12,
                          textTransform: 'uppercase',
                        }}>
                          {dayLabel.toUpperCase()}{isToday ? ' · HOJE' : ''}
                        </div>
                        
                        {blocks.length === 0 ? (
                          <div style={{ fontFamily:'var(--font-mono)', fontSize:11, color:ink2, padding:'16px 0', fontStyle:'italic', opacity:0.5 }}>
                            Livre. Sem tarefas agendadas.
                          </div>
                        ) : (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                            {blocks.map(b => <AgendaBlockItem key={b.id} block={b} dark={dark} onStartFocus={setActiveFocus} />)}
                          </div>
                        )}
                      </div>
                    )
                  })
                })()}
              </div>
             ) : (

              /* MODO TAREFAS (LOG COMPLETO) */
              <>
                <div style={{ display:'flex', justifyContent:'flex-end', gap:6, marginBottom: 16 }}>
                  <button className={`bj-toggle-btn${showCompleted ? ' bj-toggle-btn--active' : ''}`} style={{ color: showCompleted ? accent : ink2, borderColor: showCompleted ? accent : border }} onClick={() => setShowCompleted(o => !o)}>× concluídas</button>
                  <div className="bj-group-toggle" style={{ borderColor: border }}>
                    <button className={groupBy === 'date' ? 'active' : ''} style={{ color: groupBy === 'date' ? accent : ink2 }} onClick={() => setGroupBy('date')}>por data</button>
                    <button className={groupBy === 'project' ? 'active' : ''} style={{ color: groupBy === 'project' ? accent : ink2 }} onClick={() => setGroupBy('project')}>por projeto</button>
                  </div>
                </div>

                {groupedTasks.map(group => (
                  <div key={group.key} className="bj-group">
                    <div className="bj-group-label" style={{ color: group.color ?? ink2, borderColor: group.color ? group.color + '44' : border }}>
                      {groupBy === 'project' && (group.color ? <span style={{ display:'inline-block', width:6, height:6, borderRadius:'50%', background: group.color, marginRight:6 }} /> : null)}
                      {group.label} <span style={{ opacity:0.5, marginLeft:6, fontWeight:'normal' }}>({group.tasks.length})</span>
                    </div>
                    {group.tasks.map(task => <TaskRow key={task.id} task={task} dark={dark} expanded={false} onExpand={()=>{}} projects={projects} />)}
                  </div>
                ))}
              </>
             )
            }
          </div>

        </div>
      </div>
    </div>
  )
}