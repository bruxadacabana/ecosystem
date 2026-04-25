/* ============================================================
   HUB — Topbar
   Barra superior com título da seção, indicador de saúde
   global (N/6 apps rodando) e botão de silêncio do LOGOS.
   ============================================================ */

import { useEffect, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { HubSection, AppName } from '../types'

const SECTION_TITLES: Record<HubSection, string> = {
  home:      'Ecossistema',
  logos:     'LOGOS',
  atividade: 'Atividade',
  config:    'Configuração',
}

const ALL_APPS: AppName[] = ['aether', 'ogma', 'kosmos', 'mnemosyne', 'hermes', 'akasha']

interface TopbarProps {
  section: HubSection
  compact: boolean
  onToggleCompact: () => void
}

export function Topbar({ section, compact, onToggleCompact }: TopbarProps) {
  const [runningCount, setRunningCount] = useState(0)
  const [silencing, setSilencing]       = useState(false)

  useEffect(() => {
    let cancelled = false

    async function pollHealth() {
      const cfgResult = await cmd.readEcosystemConfig()
      if (!cfgResult.ok || cancelled) return

      const eco = cfgResult.data as Record<string, Record<string, string>>
      const map: Record<string, string> = {}
      for (const name of ALL_APPS) {
        const path = eco[name]?.exe_path
        if (path) map[name] = path
      }
      if (Object.keys(map).length === 0) return

      const statusResult = await cmd.getAllAppStatuses(map)
      if (!statusResult.ok || cancelled) return
      setRunningCount(Object.values(statusResult.data).filter(Boolean).length)
    }

    pollHealth()
    const id = setInterval(pollHealth, 10_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  async function handleSilence() {
    setSilencing(true)
    await cmd.logosSilence()
    setSilencing(false)
  }

  const healthColor =
    runningCount === 0 ? 'var(--ink-ghost)' :
    runningCount >= 4  ? 'var(--accent-green)' :
    'var(--accent)'

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
        borderBottom: '1px solid var(--rule)',
        flexShrink: 0,
        background: 'var(--paper)',
        height: 44,
      }}
    >
      {/* Título da seção */}
      <h2
        style={{
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          fontSize: 18,
          color: 'var(--ink)',
          margin: 0,
        }}
      >
        {SECTION_TITLES[section]}
      </h2>

      {/* Controles */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {/* Indicador de saúde global */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: healthColor,
              boxShadow: runningCount > 0 ? `0 0 5px ${healthColor}` : 'none',
              flexShrink: 0,
              transition: 'all 400ms ease',
            }}
          />
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: 'var(--ink-ghost)',
              letterSpacing: '0.06em',
            }}
          >
            {runningCount}/6
          </span>
        </div>

        {/* Silenciar LOGOS */}
        <button
          className="btn btn-ghost btn-sm"
          disabled={silencing}
          onClick={handleSilence}
          title="Silenciar LOGOS — descarregar todos os modelos"
          style={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}
        >
          {silencing ? '…' : '⊘ silenciar'}
        </button>

        {/* Alternar modo compacto */}
        <button
          className="btn btn-ghost btn-sm"
          onClick={onToggleCompact}
          title={compact ? 'Expandir janela' : 'Modo compacto'}
          style={{ fontSize: 13, fontFamily: 'var(--font-mono)', opacity: 0.6, padding: '2px 6px' }}
        >
          {compact ? '⊡' : '⊟'}
        </button>
      </div>
    </div>
  )
}
