/* ============================================================
   HUB — AppBar
   Barra lateral esquerda fixa com atalhos para os 5 apps
   do ecossistema. Mostra se cada app está rodando e permite
   iniciá-los com um clique.
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { AppName } from '../types'

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
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

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
      })
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
            onClick={() => handleClick(app)}
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
  onClick: () => void
}

function AppButton({ app, running, configured, pulsing, onClick }: AppButtonProps) {
  const [hovered, setHovered] = useState(false)

  return (
    <button
      title={configured ? app.label : `${app.label} — configure o executável`}
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
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
  )
}
