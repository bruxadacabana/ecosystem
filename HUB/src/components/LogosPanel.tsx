/* ============================================================
   LogosPanel — barra de status do LOGOS em tempo real.
   Mostra prioridade ativa, fila P1/P2/P3 e uso de VRAM.
   Faz polling a cada 5 s via Tauri IPC.
   ============================================================ */

import { useEffect, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { LogosStatus } from '../types'

const POLL_MS = 5_000

const P_COLORS: Record<number, string> = {
  1: 'var(--accent)',
  2: 'var(--accent-green)',
  3: 'var(--ink-faint)',
}

export function LogosPanel() {
  const [status, setStatus] = useState<LogosStatus | null>(null)
  const [silencing, setSilencing] = useState(false)

  useEffect(() => {
    function fetch() {
      cmd.logosGetStatus().then(r => setStatus(r.ok ? r.data : null))
    }
    fetch()
    const id = setInterval(fetch, POLL_MS)
    return () => clearInterval(id)
  }, [])

  async function handleSilence() {
    setSilencing(true)
    await cmd.logosSilence()
    const r = await cmd.logosGetStatus()
    setStatus(r.ok ? r.data : null)
    setSilencing(false)
  }

  const online              = status !== null
  const activePriority      = status?.active_priority ?? null
  const activeModelClass    = status?.active_model_class ?? null
  const queue               = status?.queue ?? ([0, 0, 0] as [number, number, number])
  const vramMb              = status?.vram_used_mb ?? null
  const vramPct             = status?.vram_pct ?? null
  const hwDisplay           = status?.hardware_profile_display ?? null
  const cpuPct              = status?.cpu_pct ?? 0
  const ramFreeMb           = status?.ram_free_mb ?? 0
  const ramTotalMb          = status?.ram_total_mb ?? 0
  const onBattery           = status?.on_battery ?? false
  const preemptedCount      = status?.preempted_count ?? 0

  let vramBarColor = 'var(--accent-green)'
  if (vramPct !== null) {
    if (vramPct > 0.85) vramBarColor = 'var(--ribbon)'
    else if (vramPct > 0.70) vramBarColor = 'var(--accent)'
  }

  const vramLabel =
    vramMb === null ? '—' :
    vramPct !== null
      ? `${(vramMb / 1000).toFixed(1)} GB · ${Math.round(vramPct * 100)}%`
      : `${vramMb} MB`

  // CPU bar — verde < 70%, amarelo 70–85%, vermelho > 85%
  let cpuBarColor = 'var(--accent-green)'
  if (cpuPct > 85) cpuBarColor = 'var(--ribbon)'
  else if (cpuPct > 70) cpuBarColor = 'var(--accent)'

  // RAM — verde > 4 GB livre, amarelo 1.5–4 GB, vermelho < 1.5 GB
  const ramFreeGb = ramFreeMb / 1024
  let ramBarColor = 'var(--accent-green)'
  if (ramFreeGb < 1.5) ramBarColor = 'var(--ribbon)'
  else if (ramFreeGb < 4) ramBarColor = 'var(--accent)'

  // Barra RAM como uso: (total - free) / total * 100
  const ramUsedPct = ramTotalMb > 0 ? Math.min(100, ((ramTotalMb - ramFreeMb) / ramTotalMb) * 100) : 0

  const ramFreeLabel = ramFreeGb >= 1
    ? `${ramFreeGb.toFixed(1)} GB`
    : `${ramFreeMb} MB`

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '7px 20px',
        borderTop: '1px solid var(--rule)',
        background: 'var(--paper-dark)',
        flexShrink: 0,
        flexWrap: 'wrap',
      }}
    >
      {/* LOGOS label + indicador de conectividade */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 64 }}>
        <div
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: online ? 'var(--accent-green)' : 'var(--ink-ghost)',
            boxShadow: online ? '0 0 5px var(--accent-green)' : 'none',
            transition: 'all 200ms ease',
          }}
        />
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '0.1em',
            color: 'var(--ink-faint)',
            textTransform: 'uppercase',
          }}
        >
          LOGOS
        </span>
      </div>

      {/* Perfil de hardware detectado */}
      {hwDisplay !== null && (
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: 'var(--ink-ghost)',
            letterSpacing: '0.04em',
            whiteSpace: 'nowrap',
          }}
          title="Perfil de hardware detectado pelo LOGOS"
        >
          {hwDisplay}
        </span>
      )}

      {/* Slots P1 / P2 / P3 */}
      <div style={{ display: 'flex', gap: 5 }}>
        {([1, 2, 3] as const).map(p => {
          const isActive    = activePriority === p
          const waiting     = queue[p - 1]
          // P3 mostra vermelho quando em bateria (bloqueado)
          const batteryBlock = p === 3 && onBattery
          const color       = batteryBlock ? 'var(--ribbon)' : P_COLORS[p]
          return (
            <div
              key={p}
              title={batteryBlock ? 'P3 bloqueado — modo bateria' : undefined}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '2px 7px',
                border: `1px solid ${isActive ? color : batteryBlock ? 'var(--ribbon)' : 'var(--rule)'}`,
                borderRadius: 'var(--radius)',
                background: isActive ? `${color}22` : batteryBlock ? 'var(--ribbon)11' : 'transparent',
                transition: 'all 200ms ease',
              }}
            >
              <div
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: '50%',
                  background: isActive ? color : batteryBlock ? 'var(--ribbon)' : 'var(--rule)',
                  boxShadow: isActive ? `0 0 4px ${color}` : 'none',
                  transition: 'all 200ms ease',
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10,
                  color: isActive ? color : batteryBlock ? 'var(--ribbon)' : 'var(--ink-ghost)',
                  letterSpacing: '0.06em',
                  lineHeight: 1,
                }}
              >
                P{p}
                {waiting > 0 && (
                  <span style={{ marginLeft: 3, color: 'var(--ink-faint)' }}>
                    +{waiting}
                  </span>
                )}
                {p === 1 && preemptedCount > 0 && (
                  <span style={{ marginLeft: 3, color: 'var(--accent)', fontSize: 9 }} title={`${preemptedCount} preempções P3 desde o startup`}>
                    ↑{preemptedCount}
                  </span>
                )}
              </span>
            </div>
          )
        })}
      </div>

      {/* Badge de bateria */}
      {onBattery && (
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '0.06em',
            color: 'var(--accent)',
            border: '1px solid var(--accent)',
            borderRadius: 'var(--radius)',
            padding: '2px 6px',
          }}
          title="Rodando em bateria — P3 desabilitado, thresholds de P2 mais conservadores"
        >
          bateria
        </span>
      )}

      {/* Badge de classe do modelo ativo */}
      {activeModelClass !== null && (
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '0.06em',
            color: activeModelClass === 'leve' ? 'var(--accent-green)' : 'var(--accent)',
            border: `1px solid ${activeModelClass === 'leve' ? 'var(--accent-green)' : 'var(--accent)'}`,
            borderRadius: 'var(--radius)',
            padding: '2px 6px',
            opacity: 0.8,
          }}
        >
          {activeModelClass}
        </span>
      )}

      {/* Recursos — VRAM (com GPU) ou CPU+RAM (sem GPU) */}
      {vramPct === null ? (
        // Sem GPU discreta: barras de CPU e RAM substituem VRAM
        <div style={{ display: 'flex', gap: 10, flex: 1, minWidth: 160 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, flex: 1 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', letterSpacing: '0.08em', flexShrink: 0 }}>CPU</span>
            <div style={{ flex: 1, height: 4, background: 'var(--rule)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${Math.min(100, Math.round(cpuPct))}%`, background: cpuBarColor, transition: 'width 400ms ease, background 400ms ease' }} />
            </div>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', whiteSpace: 'nowrap', minWidth: 32 }}>{cpuPct.toFixed(0)}%</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, flex: 1 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', letterSpacing: '0.08em', flexShrink: 0 }}>RAM</span>
            <div style={{ flex: 1, height: 4, background: 'var(--rule)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${Math.round(ramUsedPct)}%`, background: ramBarColor, transition: 'width 400ms ease, background 400ms ease' }} />
            </div>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ramBarColor, whiteSpace: 'nowrap', minWidth: 52 }}>{ramFreeLabel} livre</span>
          </div>
        </div>
      ) : (
        // Com GPU: barra de VRAM + CPU% e RAM como texto compacto
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, minWidth: 100, maxWidth: 340 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', letterSpacing: '0.08em', flexShrink: 0 }}>VRAM</span>
          <div style={{ flex: 1, height: 4, background: 'var(--rule)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${Math.min(100, Math.round(vramPct * 100))}%`, background: vramBarColor, transition: 'width 400ms ease, background 400ms ease' }} />
          </div>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', letterSpacing: '0.04em', whiteSpace: 'nowrap', minWidth: 72 }}>{vramLabel}</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', letterSpacing: '0.04em', whiteSpace: 'nowrap', opacity: 0.65 }}
                title="CPU e RAM via sysinfo">
            CPU {cpuPct.toFixed(0)}% · {ramFreeLabel} livre
          </span>
        </div>
      )}

      {/* Botão Silenciar */}
      <button
        className="btn btn-ghost btn-sm"
        disabled={silencing || !online}
        onClick={handleSilence}
        title="Descarregar todos os modelos carregados no Ollama"
        style={{ fontSize: 11, flexShrink: 0, fontFamily: 'var(--font-mono)' }}
      >
        {silencing ? '…' : 'silenciar'}
      </button>
    </div>
  )
}
