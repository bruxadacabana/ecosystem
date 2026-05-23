/* ============================================================
   LogosPanel — barra de status do LOGOS em tempo real.
   Dados estruturais (fila, modelo, perfil) via Tauri IPC a cada 30 s.
   Métricas de hardware (VRAM, CPU, RAM) via SSE a cada 1 s.
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { LogosStatus } from '../types'

const LOGOS_METRICS_URL = 'http://127.0.0.1:7072/logos/metrics/stream'
const STRUCT_POLL_MS    = 30_000

interface MetricsSnapshot {
  vram_used_mb:  number | null
  vram_total_mb: number | null
  vram_pct:      number | null  // 0–100
  cpu_pct:       number
  ram_free_mb:   number
  ram_total_mb:  number
}

const P_COLORS: Record<number, string> = {
  1: 'var(--accent)',
  2: 'var(--accent-green)',
  3: 'var(--ink-faint)',
}

export function LogosPanel() {
  const [status,  setStatus]  = useState<LogosStatus | null>(null)
  const [metrics, setMetrics] = useState<MetricsSnapshot | null>(null)
  const [online,  setOnline]  = useState(false)
  const [silencing, setSilencing] = useState(false)
  const esRef = useRef<EventSource | null>(null)

  // Dados estruturais — pool leve (30 s)
  useEffect(() => {
    function fetchStruct() {
      cmd.logosGetStatus().then(r => {
        if (r.ok) {
          setStatus(r.data)
          setOnline(true)
        } else {
          setStatus(null)
        }
      })
    }
    fetchStruct()
    const id = setInterval(fetchStruct, STRUCT_POLL_MS)
    return () => clearInterval(id)
  }, [])

  // Métricas em tempo real — SSE 1 s
  useEffect(() => {
    function connect() {
      const es = new EventSource(LOGOS_METRICS_URL)
      esRef.current = es

      es.onmessage = (ev) => {
        try {
          const snap: MetricsSnapshot = JSON.parse(ev.data)
          setMetrics(snap)
          setOnline(true)
        } catch {
          // ignore parse error
        }
      }

      es.onerror = () => {
        // SSE caiu — fechar e tentar reconectar após 5 s
        es.close()
        esRef.current = null
        setOnline(false)
        setTimeout(connect, 5_000)
      }
    }

    connect()
    return () => {
      esRef.current?.close()
      esRef.current = null
    }
  }, [])

  async function handleSilence() {
    setSilencing(true)
    await cmd.logosSilence()
    const r = await cmd.logosGetStatus()
    setStatus(r.ok ? r.data : null)
    setSilencing(false)
  }

  const activePriority   = status?.active_priority ?? null
  const activeModelClass = status?.active_model_class ?? null
  const queue            = status?.queue ?? ([0, 0, 0] as [number, number, number])
  const hwDisplay        = status?.hardware_profile_display ?? null
  const onBattery        = status?.on_battery ?? false
  const preemptedCount   = status?.preempted_count ?? 0

  // Preferir métricas SSE; fallback para status do IPC
  const vramMb     = metrics?.vram_used_mb   ?? status?.vram_used_mb   ?? null
  const vramPctRaw = metrics?.vram_pct       ?? (status?.vram_pct != null ? status.vram_pct * 100 : null)
  const cpuPct     = metrics?.cpu_pct        ?? status?.cpu_pct        ?? 0
  const ramFreeMb  = metrics?.ram_free_mb    ?? status?.ram_free_mb    ?? 0
  const ramTotalMb = metrics?.ram_total_mb   ?? status?.ram_total_mb   ?? 0

  // vramPctRaw é 0–100 (tanto do SSE quanto normalizado do IPC acima)
  const vramPct = vramPctRaw  // 0–100

  let vramBarColor = 'var(--accent-green)'
  if (vramPct !== null) {
    if (vramPct > 85) vramBarColor = 'var(--ribbon)'
    else if (vramPct > 70) vramBarColor = 'var(--accent)'
  }

  const vramLabel =
    vramMb === null ? '—' :
    vramPct !== null
      ? `${(vramMb / 1000).toFixed(1)} GB · ${Math.round(vramPct)}%`
      : `${vramMb} MB`

  let cpuBarColor = 'var(--accent-green)'
  if (cpuPct > 85) cpuBarColor = 'var(--ribbon)'
  else if (cpuPct > 70) cpuBarColor = 'var(--accent)'

  const ramFreeGb = ramFreeMb / 1024
  let ramBarColor = 'var(--accent-green)'
  if (ramFreeGb < 1.5) ramBarColor = 'var(--ribbon)'
  else if (ramFreeGb < 4) ramBarColor = 'var(--accent)'

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
            <div style={{ height: '100%', width: `${Math.min(100, Math.round(vramPct))}%`, background: vramBarColor, transition: 'width 400ms ease, background 400ms ease' }} />
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
