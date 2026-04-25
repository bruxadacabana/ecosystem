/* ============================================================
   HUB — DashboardView
   Dashboard principal: 6 cards de status dos apps do ecossistema.
   Cada card mostra status ao vivo, descrição e ações disponíveis.
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { AppName, HubView } from '../types'

interface AppDef {
  name: AppName
  sigla: string
  label: string
  description: string
  module: HubView | null
  candidates: string[]
  isWeb: boolean
}

const APPS: AppDef[] = [
  {
    name: 'aether',
    sigla: 'Æ',
    label: 'AETHER',
    description: 'Editor de ficção e worldbuilding',
    module: 'writing',
    candidates: ['AETHER', 'aether', 'AETHER.exe'],
    isWeb: false,
  },
  {
    name: 'kosmos',
    sigla: 'K',
    label: 'KOSMOS',
    description: 'Leitor de feeds RSS e artigos',
    module: 'reading',
    candidates: ['KOSMOS', 'kosmos', 'KOSMOS.exe'],
    isWeb: false,
  },
  {
    name: 'mnemosyne',
    sigla: 'M',
    label: 'Mnemosyne',
    description: 'Base de conhecimento RAG local',
    module: null,
    candidates: ['Mnemosyne', 'mnemosyne', 'Mnemosyne.exe'],
    isWeb: false,
  },
  {
    name: 'ogma',
    sigla: 'O',
    label: 'OGMA',
    description: 'Gestão de projetos e páginas',
    module: 'projects',
    candidates: ['OGMA', 'ogma', 'OGMA.exe'],
    isWeb: false,
  },
  {
    name: 'hermes',
    sigla: 'H',
    label: 'Hermes',
    description: 'Transcrições de vídeo e áudio',
    module: null,
    candidates: ['Hermes', 'hermes', 'Hermes.exe'],
    isWeb: false,
  },
  {
    name: 'akasha',
    sigla: 'Ak',
    label: 'AKASHA',
    description: 'Motor de busca do ecossistema',
    module: null,
    candidates: ['iniciar.sh', 'akasha/iniciar.sh'],
    isWeb: true,
  },
]

interface DashboardViewProps {
  onOpenModule: (module: HubView) => void
}

export function DashboardView({ onOpenModule }: DashboardViewProps) {
  const [exePaths, setExePaths]  = useState<Partial<Record<AppName, string>>>({})
  const [statuses, setStatuses]  = useState<Partial<Record<AppName, boolean>>>({})
  const [akashaUrl, setAkashaUrl] = useState('http://localhost:7071')
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function loadConfig() {
    cmd.readEcosystemConfig().then(result => {
      if (!result.ok) return
      const eco = result.data as Record<string, Record<string, string>>
      setExePaths({
        aether:    eco.aether?.exe_path    ?? '',
        ogma:      eco.ogma?.exe_path      ?? '',
        kosmos:    eco.kosmos?.exe_path    ?? '',
        mnemosyne: eco.mnemosyne?.exe_path ?? '',
        hermes:    eco.hermes?.exe_path    ?? '',
        akasha:    eco.akasha?.exe_path    ?? '',
      })
      setAkashaUrl(eco.akasha?.base_url ?? 'http://localhost:7071')
    })
  }

  function pollStatuses(paths: Partial<Record<AppName, string>>) {
    const map: Record<string, string> = {}
    for (const [name, path] of Object.entries(paths)) {
      if (path) map[name] = path
    }
    if (Object.keys(map).length === 0) return
    cmd.getAllAppStatuses(map).then(result => {
      if (result.ok) setStatuses(result.data as Partial<Record<AppName, boolean>>)
    })
  }

  useEffect(() => { loadConfig() }, [])

  useEffect(() => {
    pollStatuses(exePaths)
    if (intervalRef.current) clearInterval(intervalRef.current)
    intervalRef.current = setInterval(() => pollStatuses(exePaths), 5_000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [exePaths])

  async function handleLaunch(app: AppDef) {
    const path = exePaths[app.name]
    if (!path) return
    if (app.isWeb && statuses[app.name]) {
      await cmd.launchApp(akashaUrl)
      return
    }
    if (statuses[app.name]) return
    await cmd.launchApp(path)
    setTimeout(() => pollStatuses(exePaths), 1_500)
  }

  return (
    <div
      style={{
        flex: 1,
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gridTemplateRows: 'repeat(2, 1fr)',
        gap: 1,
        background: 'var(--rule)',
        overflow: 'hidden',
        minHeight: 0,
      }}
    >
      {APPS.map(app => (
        <AppCard
          key={app.name}
          app={app}
          running={statuses[app.name] ?? false}
          configured={!!(exePaths[app.name])}
          onLaunch={() => handleLaunch(app)}
          onOpenModule={app.module ? () => onOpenModule(app.module!) : undefined}
        />
      ))}
    </div>
  )
}

// ── Card individual ───────────────────────────────────────────

interface AppCardProps {
  app: AppDef
  running: boolean
  configured: boolean
  onLaunch: () => void
  onOpenModule?: () => void
}

function AppCard({ app, running, configured, onLaunch, onOpenModule }: AppCardProps) {
  const [hovered, setHovered] = useState(false)

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        padding: '22px 26px 18px',
        background: hovered ? 'var(--paper-dark)' : 'var(--paper)',
        transition: 'background 140ms ease',
        gap: 6,
      }}
    >
      {/* Cabeçalho: sigla + status */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontStyle: 'italic',
            fontSize: 30,
            color: 'var(--ink)',
            lineHeight: 1,
            opacity: configured ? 1 : 0.3,
          }}
        >
          {app.sigla}
        </span>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: running ? 'var(--accent-green)' : 'var(--rule)',
            boxShadow: running ? '0 0 6px var(--accent-green)' : 'none',
            marginTop: 6,
            flexShrink: 0,
            transition: 'all 400ms ease',
          }}
        />
      </div>

      {/* Nome */}
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          color: configured ? 'var(--ink)' : 'var(--ink-ghost)',
        }}
      >
        {app.label}
      </div>

      {/* Descrição */}
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--ink-ghost)',
          letterSpacing: '0.03em',
          flex: 1,
        }}
      >
        {configured ? app.description : 'Executável não configurado'}
      </div>

      {/* Status textual */}
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          letterSpacing: '0.06em',
          color: running ? 'var(--accent-green)' : 'var(--ink-ghost)',
          opacity: 0.75,
          marginBottom: 6,
        }}
      >
        {running ? 'rodando' : configured ? 'parado' : '—'}
      </div>

      {/* Ações */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {configured && !running && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={onLaunch}
            style={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}
          >
            iniciar
          </button>
        )}
        {running && app.isWeb && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={onLaunch}
            style={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}
          >
            abrir ↗
          </button>
        )}
        {onOpenModule && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={onOpenModule}
            style={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}
          >
            módulo →
          </button>
        )}
      </div>
    </div>
  )
}
