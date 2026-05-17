/* ============================================================
   HUB — AppBar
   Barra lateral esquerda fixa com atalhos para os 6 apps
   do ecossistema. Mostra se cada app está rodando e permite
   iniciá-los com um clique.
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { AppName } from '../types'

const INSIGHTS_POLL_INTERVAL_MS = 60_000

interface AppDef {
  name: AppName
  sigla: string
  label: string
  candidates: string[]
}

const APPS: AppDef[] = [
  {
    name: 'aether',
    sigla: 'Æ',
    label: 'AETHER',
    candidates: ['AETHER', 'aether', 'AETHER.exe'],
  },
  {
    name: 'ogma',
    sigla: 'O',
    label: 'OGMA',
    candidates: ['OGMA', 'ogma', 'OGMA.exe'],
  },
  {
    name: 'kosmos',
    sigla: 'K',
    label: 'KOSMOS',
    candidates: ['KOSMOS', 'kosmos', 'KOSMOS.exe'],
  },
  {
    name: 'mnemosyne',
    sigla: 'M',
    label: 'Mnemosyne',
    candidates: ['Mnemosyne', 'mnemosyne', 'Mnemosyne.exe'],
  },
  {
    name: 'hermes',
    sigla: 'H',
    label: 'Hermes',
    candidates: ['Hermes', 'hermes', 'Hermes.exe'],
  },
  {
    name: 'akasha',
    sigla: 'Ak',
    label: 'AKASHA',
    candidates: ['akasha/iniciar.sh', 'iniciar.sh'],
  },
]

const POLL_INTERVAL_MS = 5000

interface AppBarProps {
  /** Chamado quando o usuário clica em um app sem executável configurado. */
  onConfigNeeded: () => void
}

export function AppBar({ onConfigNeeded }: AppBarProps) {
  const [exePaths, setExePaths] = useState<Partial<Record<AppName, string>>>({})
  const [statuses, setStatuses] = useState<Partial<Record<AppName, boolean>>>({})
  const [pulsing, setPulsing] = useState<Partial<Record<AppName, boolean>>>({})
  const [akashaBaseUrl, setAkashaBaseUrl] = useState('')
  const [pendingInsights, setPendingInsights] = useState(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const insightsIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ----------------------------------------------------------
  //  Carrega exe_paths do ecosystem.json
  // ----------------------------------------------------------
  function loadExePaths() {
    cmd.readEcosystemConfig().then(result => {
      if (!result.ok) return
      const eco = result.data
      setExePaths({
        aether:    eco.aether?.exe_path    ?? '',
        ogma:      eco.ogma?.exe_path      ?? '',
        kosmos:    eco.kosmos?.exe_path    ?? '',
        mnemosyne: eco.mnemosyne?.exe_path ?? '',
        hermes:    (eco.hermes as { exe_path?: string } | undefined)?.exe_path ?? '',
        akasha:    eco.akasha?.exe_path    ?? '',
      })
      setAkashaBaseUrl(eco.akasha?.base_url ?? 'http://localhost:7071')
    })
  }

  // ----------------------------------------------------------
  //  Polling de insights pendentes (a cada 60s)
  // ----------------------------------------------------------
  function pollInsights() {
    cmd.readEcosystemConfig().then(result => {
      if (!result.ok) return
      const count = result.data.mnemosyne?.pending_insights ?? 0
      setPendingInsights(count)
    })
  }

  // ----------------------------------------------------------
  //  Polling de status (a cada 5s)
  // ----------------------------------------------------------
  function pollStatuses(paths: Partial<Record<AppName, string>>) {
    const map: Record<string, string> = {}
    for (const [name, path] of Object.entries(paths)) {
      if (path) map[name] = path
    }
    if (Object.keys(map).length === 0) return

    cmd.getAllAppStatuses(map).then(result => {
      if (!result.ok) return
      setStatuses(result.data as Partial<Record<AppName, boolean>>)
    })
  }

  useEffect(() => {
    loadExePaths()
    pollInsights()
    insightsIntervalRef.current = setInterval(pollInsights, INSIGHTS_POLL_INTERVAL_MS)
    return () => {
      if (insightsIntervalRef.current) clearInterval(insightsIntervalRef.current)
    }
  }, [])

  useEffect(() => {
    pollStatuses(exePaths)

    if (intervalRef.current) clearInterval(intervalRef.current)
    intervalRef.current = setInterval(() => pollStatuses(exePaths), POLL_INTERVAL_MS)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [exePaths])

  // ----------------------------------------------------------
  //  Clique no botão do app
  // ----------------------------------------------------------
  async function handleClick(app: AppDef) {
    const path = exePaths[app.name]

    if (!path) {
      onConfigNeeded()
      return
    }

    // Se já está rodando: apenas pulsa o indicador
    if (statuses[app.name]) {
      triggerPulse(app.name)
      return
    }

    triggerPulse(app.name)
    const result = await cmd.launchApp(path)
    if (!result.ok) {
      console.error(`[AppBar] Erro ao iniciar ${app.label}: ${result.error.message}`)
    } else {
      // Aguarda um momento para o processo aparecer no SO
      setTimeout(() => pollStatuses(exePaths), 1500)
    }
  }

  function triggerPulse(name: AppName) {
    setPulsing(p => ({ ...p, [name]: true }))
    setTimeout(() => setPulsing(p => ({ ...p, [name]: false })), 700)
  }

  async function handleInsightsBadgeClick() {
    const path = exePaths['mnemosyne']
    if (!path) return
    if (!statuses['mnemosyne']) {
      triggerPulse('mnemosyne')
      await cmd.launchAppWithArgs(path, ['--open-insights'])
      setTimeout(() => pollStatuses(exePaths), 1500)
    }
    // Se já está rodando: a Mnemosyne detecta pending_insights via seu próprio QTimer —
    // não há IPC direto para forçar o painel. O badge permanece visível.
  }

  async function stopAkasha() {
    const base = akashaBaseUrl || 'http://localhost:7071'
    try {
      await fetch(`${base}/shutdown`, { method: 'POST' })
    } catch {
      // processo pode cair antes de responder — ignorar
    }
    setTimeout(() => pollStatuses(exePaths), 1500)
  }

  // ----------------------------------------------------------
  //  Render
  // ----------------------------------------------------------
  return (
    <div
      style={{
        width: 56,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        paddingTop: 16,
        paddingBottom: 16,
        gap: 2,
        borderRight: '1px solid var(--rule)',
        background: 'var(--paper-dark)',
      }}
    >
      {APPS.map(app => {
        const running    = statuses[app.name] ?? false
        const configured = !!(exePaths[app.name])
        const isPulsing  = pulsing[app.name] ?? false

        return (
          <AppButton
            key={app.name}
            app={app}
            running={running}
            configured={configured}
            pulsing={isPulsing}
            pendingInsights={app.name === 'mnemosyne' ? pendingInsights : 0}
            onClick={() => handleClick(app)}
            onStop={app.name === 'akasha' ? stopAkasha : undefined}
            onInsightsBadge={app.name === 'mnemosyne' ? handleInsightsBadgeClick : undefined}
          />
        )
      })}
    </div>
  )
}

// ----------------------------------------------------------
//  Sub-componente: botão individual
// ----------------------------------------------------------

interface AppButtonProps {
  app: AppDef
  running: boolean
  configured: boolean
  pulsing: boolean
  pendingInsights: number
  onClick: () => void
  onStop?: () => void
  onInsightsBadge?: () => void
}

function AppButton({ app, running, configured, pulsing, pendingInsights, onClick, onStop, onInsightsBadge }: AppButtonProps) {
  const [hovered, setHovered] = useState(false)
  const showStop = hovered && running && !!onStop

  return (
    <div
      style={{ position: 'relative', display: 'inline-flex' }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        title={configured ? app.label : `${app.label} — configure o executável`}
        onClick={onClick}
        style={{
          width: 44,
          height: 50,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 5,
          background: hovered && configured ? 'var(--rule)' : 'transparent',
          border: 'none',
          borderRadius: 'var(--radius)',
          cursor: configured ? 'pointer' : 'default',
          opacity: configured ? 1 : 0.35,
          transition: 'background 120ms, opacity 200ms',
          padding: 0,
          userSelect: 'none',
        }}
      >
        {/* Sigla em IM Fell English itálico */}
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontStyle: 'italic',
            fontSize: 17,
            lineHeight: 1,
            color: running ? 'var(--ink)' : 'var(--ink-muted, var(--ink))',
            transition: 'color 300ms',
          }}
        >
          {app.sigla}
        </span>

        {/* Indicador de status */}
        <span
          style={{
            width: 5,
            height: 5,
            borderRadius: '50%',
            background: running ? '#4A6741' : 'var(--rule)',
            transition: 'background 400ms',
            animation: pulsing ? 'etherPulse 0.7s ease-in-out' : 'none',
            flexShrink: 0,
          }}
        />
      </button>

      {/* Botão de parada — aparece ao passar o mouse quando o app está rodando */}
      {showStop && (
        <button
          title={`Encerrar ${app.label}`}
          onClick={e => { e.stopPropagation(); onStop() }}
          style={{
            position: 'absolute',
            top: 2,
            right: 2,
            width: 14,
            height: 14,
            borderRadius: '50%',
            background: '#c0392b',
            border: 'none',
            color: '#fff',
            fontSize: 9,
            lineHeight: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            padding: 0,
          }}
        >
          ✕
        </button>
      )}

      {/* Badge de insights AKASHA→Mnemosyne */}
      {pendingInsights > 0 && !!onInsightsBadge && (
        <button
          title={`${pendingInsights} insight${pendingInsights > 1 ? 's' : ''} do AKASHA — clique para abrir`}
          onClick={e => { e.stopPropagation(); onInsightsBadge() }}
          style={{
            position: 'absolute',
            bottom: 2,
            right: -4,
            minWidth: 16,
            height: 16,
            borderRadius: 8,
            background: '#1B3A4B',
            border: '1px solid #4FC3F7',
            color: '#4FC3F7',
            fontSize: 8,
            fontFamily: 'monospace',
            lineHeight: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            padding: '0 3px',
            whiteSpace: 'nowrap',
          }}
        >
          ⬡ {pendingInsights}
        </button>
      )}
    </div>
  )
}
