/* ============================================================
   HUB — SyncView
   Gerenciamento do Syncthing: status, pastas, dispositivos.
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { SyncStatus, SyncFolder } from '../lib/tauri'

// ── Utilitários ───────────────────────────────────────────────

function fmtBytes(b: number): string {
  if (b <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let v = b
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function stateColor(state: string, paused: boolean): string {
  if (paused)            return 'var(--ink-ghost)'
  if (state === 'idle')  return '#4A6741'
  if (state === 'error') return '#8B3A2A'
  return 'var(--accent)'   // syncing / scanning
}

function stateLabel(state: string, paused: boolean): string {
  if (paused)               return 'pausada'
  if (state === 'idle')     return 'sincronizada'
  if (state === 'syncing')  return 'sincronizando…'
  if (state === 'scanning') return 'verificando…'
  if (state === 'error')    return 'erro'
  return state
}

// ── Linha de pasta ────────────────────────────────────────────

function FolderRow({
  folder, onRescan, rescanning,
}: {
  folder:     SyncFolder
  onRescan:   (id: string) => void
  rescanning: boolean
}) {
  const color = stateColor(folder.state, folder.paused)
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '8px 0', borderBottom: '1px solid var(--rule)',
    }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {folder.label}
        </div>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', opacity: 0.7,
        }}>
          {folder.path}
        </div>
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color }}>
          {stateLabel(folder.state, folder.paused)}
        </div>
        {folder.need_bytes > 0 && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-ghost)', opacity: 0.6 }}>
            {fmtBytes(folder.need_bytes)} pendente
          </div>
        )}
      </div>
      <button
        onClick={() => onRescan(folder.id)}
        disabled={rescanning}
        title="Forçar re-scan"
        style={{
          fontFamily: 'var(--font-mono)', fontSize: 10,
          background: 'none', border: '1px solid var(--rule)', borderRadius: 3,
          color: 'var(--ink-ghost)', cursor: rescanning ? 'default' : 'pointer',
          padding: '2px 6px', opacity: rescanning ? 0.4 : 0.7, flexShrink: 0,
        }}
      >
        ↻
      </button>
    </div>
  )
}

// ── View principal ────────────────────────────────────────────

interface SyncViewProps {
  autoPaused: boolean   // auto-pausa ativa pelo HUB (apps rodando)
}

export function SyncView({ autoPaused }: SyncViewProps) {
  const [status,      setStatus]      = useState<SyncStatus | null>(null)
  const [manualPause, setManualPause] = useState(false)
  const [starting,    setStarting]    = useState(false)
  const [stopping,    setStopping]    = useState(false)
  const [rescanning,  setRescanning]  = useState<string | null>(null)
  const [err,         setErr]         = useState<string | null>(null)
  const runningRef = useRef(true)

  async function refresh() {
    const res = await cmd.syncthingStatus()
    if (!runningRef.current) return
    if (res.ok) { setStatus(res.data); setErr(null) }
    else setErr(res.error.message)
  }

  useEffect(() => {
    runningRef.current = true
    cmd.syncthingGetPaused().then(r => { if (r.ok) setManualPause(r.data) })
    refresh()
    const id = setInterval(refresh, 5000)
    return () => { runningRef.current = false; clearInterval(id) }
  }, [])

  async function handleStart() {
    setStarting(true)
    await cmd.syncthingStart()
    // aguarda 2s para o processo inicializar antes de re-buscar
    setTimeout(async () => { await refresh(); setStarting(false) }, 2000)
  }

  async function handleStop() {
    setStopping(true)
    await cmd.syncthingShutdown()
    setTimeout(async () => { await refresh(); setStopping(false) }, 1500)
  }

  async function handleTogglePause() {
    const next = !manualPause
    const res = await cmd.syncthingSetPaused(next)
    if (res.ok) {
      setManualPause(next)
      if (next) await cmd.syncthingPauseAll()
      else if (!autoPaused) await cmd.syncthingResumeAll()
    }
  }

  async function handleRescan(folderId: string) {
    setRescanning(folderId)
    await cmd.syncthingRescan(folderId)
    setTimeout(() => setRescanning(null), 1500)
  }

  const running = status?.running ?? false
  const paused  = manualPause || autoPaused

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      padding: '24px 28px', gap: 20, overflowY: 'auto',
    }}>
      {/* Cabeçalho */}
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <span style={{
          fontFamily: 'var(--font-display)', fontStyle: 'italic',
          fontSize: 18, color: 'var(--ink)', letterSpacing: '0.02em',
        }}>
          ⇄ Sync
        </span>
        {err && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#8B3A2A' }}>
            {err}
          </span>
        )}
      </div>

      {/* Status + controles */}
      <div style={{
        background: 'var(--paper-dark)', border: '1px solid var(--rule)',
        borderRadius: 'var(--radius)', padding: '14px 18px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
            background: running ? (paused ? '#b8860b' : '#4A6741') : 'var(--ink-ghost)',
            opacity: running ? 1 : 0.4,
          }} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink)', flex: 1 }}>
            Syncthing — {!running ? 'parado' : paused ? 'pausado' : 'sincronizando'}
          </span>
          {running
            ? (
              <button
                onClick={handleStop}
                disabled={stopping}
                style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, padding: '4px 12px',
                  background: 'transparent', color: 'var(--ink-ghost)',
                  border: '1px solid var(--rule)', borderRadius: 4,
                  cursor: stopping ? 'default' : 'pointer', opacity: stopping ? 0.5 : 1,
                }}
              >
                {stopping ? 'encerrando…' : 'Parar'}
              </button>
            ) : (
              <button
                onClick={handleStart}
                disabled={starting}
                style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, padding: '4px 12px',
                  background: 'var(--accent)', color: 'var(--paper-dark)',
                  border: 'none', borderRadius: 4,
                  cursor: starting ? 'default' : 'pointer', opacity: starting ? 0.5 : 1,
                }}
              >
                {starting ? 'iniciando…' : 'Iniciar'}
              </button>
            )
          }
        </div>

        {/* Pausa manual */}
        {running && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button
              onClick={handleTogglePause}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 10,
                background: 'none', border: 'none', cursor: 'pointer',
                color: manualPause ? 'var(--accent)' : 'var(--ink-ghost)',
                padding: 0, opacity: 0.8,
              }}
            >
              {manualPause ? '▶ retomar sync' : '⏸ pausar sync'}
            </button>
            {autoPaused && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: '#b8860b', opacity: 0.8 }}>
                (pausado automaticamente — apps com banco de dados em uso)
              </span>
            )}
          </div>
        )}
      </div>

      {/* Pastas */}
      {running && status && status.folders.length > 0 && (
        <div style={{
          background: 'var(--paper-dark)', border: '1px solid var(--rule)',
          borderRadius: 'var(--radius)', padding: '14px 18px',
        }}>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)',
            letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8,
          }}>
            Pastas
          </div>
          {status.folders.map(f => (
            <FolderRow
              key={f.id}
              folder={f}
              onRescan={handleRescan}
              rescanning={rescanning === f.id}
            />
          ))}
        </div>
      )}

      {/* Dispositivos */}
      {running && status && status.devices.length > 0 && (
        <div style={{
          background: 'var(--paper-dark)', border: '1px solid var(--rule)',
          borderRadius: 'var(--radius)', padding: '14px 18px',
        }}>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)',
            letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8,
          }}>
            Dispositivos
          </div>
          {status.devices.map(d => (
            <div key={d.device_id} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '7px 0', borderBottom: '1px solid var(--rule)',
            }}>
              <span style={{
                width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                background: d.connected ? '#4A6741' : 'var(--ink-ghost)',
                opacity: d.connected ? 1 : 0.4,
              }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink)', flex: 1 }}>
                {d.name}
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', opacity: 0.6 }}>
                {d.connected ? 'conectado' : d.last_seen ? `último: ${d.last_seen.slice(0, 10)}` : 'desconectado'}
              </span>
            </div>
          ))}
        </div>
      )}

      {!status && !err && (
        <p style={{
          fontFamily: 'var(--font-mono)', fontSize: 11,
          color: 'var(--ink-ghost)', opacity: 0.5, textAlign: 'center', marginTop: 24,
        }}>
          Verificando Syncthing…
        </p>
      )}
    </div>
  )
}
