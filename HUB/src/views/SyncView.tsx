/* ============================================================
   HUB — SyncView
   Gerenciamento do Syncthing: status, pastas, dispositivos,
   atividade recente, logs e backup.
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import * as cmd from '../lib/tauri'
import type {
  SyncStatus, SyncFolder, SyncEvent, SyncLogLine,
  SyncCredentials, BackupReport, IntegrityReport,
} from '../lib/tauri'

// ── Helpers ───────────────────────────────────────────────────

function fmtBytes(b: number): string {
  if (b <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0, v = b
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function fmtRelTime(iso: string): string {
  if (!iso) return ''
  try {
    const diff = (Date.now() - new Date(iso).getTime()) / 1000
    if (diff < 5)    return 'agora'
    if (diff < 60)   return `${Math.round(diff)}s`
    if (diff < 3600) return `${Math.round(diff / 60)}min`
    return `${Math.round(diff / 3600)}h`
  } catch { return '' }
}

function stateColor(state: string, paused: boolean): string {
  if (paused)            return 'var(--ink-ghost)'
  if (state === 'idle')  return '#4A6741'
  if (state === 'error') return '#8B3A2A'
  return 'var(--accent)'
}

function stateLabel(state: string, paused: boolean): string {
  if (paused)               return 'pausada'
  if (state === 'idle')     return 'sincronizada'
  if (state === 'syncing')  return 'sincronizando…'
  if (state === 'scanning') return 'verificando…'
  if (state === 'error')    return 'erro'
  return state
}

function eventIcon(kind: string): string {
  if (kind === 'LocalChangeDetected')  return '↑'
  if (kind === 'RemoteChangeDetected') return '↓'
  if (kind === 'ItemFinished')         return '✓'
  if (kind === 'DeviceConnected')      return '⚡'
  if (kind === 'DeviceDisconnected')   return '◯'
  return '·'
}

// ── Primitivos ────────────────────────────────────────────────

function Card({ children }: { children: ReactNode }) {
  return (
    <div style={{
      background: 'var(--paper-dark)', border: '1px solid var(--rule)',
      borderRadius: 'var(--radius)', padding: '14px 18px',
    }}>
      {children}
    </div>
  )
}

function SecTitle({ label }: { label: string }) {
  return (
    <div style={{
      fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)',
      letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8,
    }}>
      {label}
    </div>
  )
}

function Btn({
  children, onClick, disabled = false, accent = false, title,
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  accent?: boolean
  title?: string
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{
        fontFamily: 'var(--font-mono)', fontSize: 11, padding: '3px 9px',
        background: accent ? 'var(--accent)' : 'transparent',
        color: accent ? 'var(--paper-dark)' : 'var(--ink-ghost)',
        border: accent ? 'none' : '1px solid var(--rule)',
        borderRadius: 4, cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.4 : 0.85, flexShrink: 0,
      }}
    >
      {children}
    </button>
  )
}

function CollapsibleSection({
  title, open, onToggle, children,
}: {
  title:    string
  open:     boolean
  onToggle: () => void
  children: ReactNode
}) {
  return (
    <Card>
      <button
        onClick={onToggle}
        style={{
          all: 'unset', cursor: 'pointer', display: 'flex',
          alignItems: 'center', gap: 6, width: '100%',
        }}
      >
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)',
          letterSpacing: '0.08em', textTransform: 'uppercase', flex: 1,
        }}>
          {title}
        </span>
        <span style={{ fontSize: 9, color: 'var(--ink-ghost)', opacity: 0.5 }}>
          {open ? '▲' : '▼'}
        </span>
      </button>
      {open && <div style={{ marginTop: 10 }}>{children}</div>}
    </Card>
  )
}

// ── FolderRow ─────────────────────────────────────────────────

function FolderRow({
  folder, pausing, onPause, onResume, onRescan, rescanning,
}: {
  folder:     SyncFolder
  pausing:    boolean
  onPause:    (id: string) => void
  onResume:   (id: string) => void
  onRescan:   (id: string) => void
  rescanning: boolean
}) {
  const color   = stateColor(folder.state, folder.paused)
  const total   = folder.in_sync_bytes + folder.need_bytes
  const pct     = total > 0 ? folder.in_sync_bytes / total : 1
  const pending = folder.need_bytes > 0

  return (
    <div style={{ padding: '8px 0', borderBottom: '1px solid var(--rule)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          width: 7, height: 7, borderRadius: '50%',
          background: color, flexShrink: 0,
        }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {folder.label}
          </div>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-ghost)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', opacity: 0.55,
          }}>
            {folder.path}
          </div>
        </div>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 9, color, flexShrink: 0,
        }}>
          {stateLabel(folder.state, folder.paused)}
        </span>
        {folder.paused
          ? <Btn onClick={() => onResume(folder.id)} disabled={pausing} title="Retomar pasta">▶</Btn>
          : <Btn onClick={() => onPause(folder.id)}  disabled={pausing} title="Pausar pasta">⏸</Btn>
        }
        <Btn onClick={() => onRescan(folder.id)} disabled={rescanning} title="Forçar re-scan">↻</Btn>
      </div>

      <div style={{ margin: '5px 0 0', height: 3, background: 'var(--rule)', borderRadius: 2 }}>
        <div style={{
          height: '100%', borderRadius: 2,
          background: pending ? 'var(--accent)' : '#4A6741',
          width: `${Math.round(pct * 100)}%`,
          transition: 'width 0.3s',
        }} />
      </div>
      {pending && (
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 9,
          color: 'var(--accent)', marginTop: 2,
        }}>
          {fmtBytes(folder.need_bytes)} pendente
        </div>
      )}
    </div>
  )
}

// ── EventRow ──────────────────────────────────────────────────

function EventRow({ event }: { event: SyncEvent }) {
  const icon  = eventIcon(event.kind)
  const color = event.kind === 'LocalChangeDetected'  ? 'var(--accent)'
              : event.kind === 'RemoteChangeDetected' ? '#4A8B8B'
              : event.kind === 'ItemFinished'         ? '#4A6741'
              : 'var(--ink-ghost)'

  const shortItem = event.item.length > 40
    ? '…' + event.item.slice(-39)
    : event.item

  return (
    <div style={{
      display: 'flex', alignItems: 'baseline', gap: 6,
      padding: '3px 0', borderBottom: '1px solid var(--rule)',
      fontFamily: 'var(--font-mono)', fontSize: 10,
    }}>
      <span style={{ color, flexShrink: 0, width: 12 }}>{icon}</span>
      <span style={{
        color: 'var(--ink-ghost)', flexShrink: 0,
        maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {event.folder}
      </span>
      <span style={{
        color: 'var(--ink)', flex: 1,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {shortItem}
      </span>
      <span style={{ color: 'var(--ink-ghost)', flexShrink: 0, opacity: 0.45 }}>
        {fmtRelTime(event.time)}
      </span>
    </div>
  )
}

// ── View principal ────────────────────────────────────────────

interface SyncViewProps { autoPaused: boolean }

export function SyncView({ autoPaused }: SyncViewProps) {
  const [status,      setStatus]      = useState<SyncStatus | null>(null)
  const [manualPause, setManualPause] = useState(false)
  const [starting,    setStarting]    = useState(false)
  const [stopping,    setStopping]    = useState(false)
  const [rescanning,  setRescanning]  = useState<string | null>(null)
  const [folderPausing, setFolderPausing] = useState<Set<string>>(new Set())
  const [err,         setErr]         = useState<string | null>(null)

  // Credenciais
  const [credUser,     setCredUser]     = useState('')
  const [credPassword, setCredPassword] = useState('')
  const [credOpen,     setCredOpen]     = useState(false)
  const [credSaving,   setCredSaving]   = useState(false)
  const [credSaved,    setCredSaved]    = useState(false)

  // Atividade recente
  const [events,       setEvents]       = useState<SyncEvent[]>([])
  const lastEventIdRef = useRef(0)

  // Logs
  const [logLines, setLogLines] = useState<SyncLogLine[]>([])
  const [logOpen,  setLogOpen]  = useState(false)

  // Backup e integridade
  const [backupReport,      setBackupReport]      = useState<BackupReport | null>(null)
  const [backingUp,         setBackingUp]         = useState(false)
  const [integrityResults,  setIntegrityResults]  = useState<IntegrityReport[]>([])
  const [checkingIntegrity, setCheckingIntegrity] = useState(false)

  const runningRef = useRef(true)

  // ── Funções de fetch ────────────────────────────────────────

  async function refresh() {
    const res = await cmd.syncthingStatus()
    if (!runningRef.current) return
    if (res.ok) { setStatus(res.data); setErr(null) }
    else setErr(res.error.message)
  }

  async function pollEvents() {
    const res = await cmd.syncthingGetEvents(lastEventIdRef.current, 30)
    if (!runningRef.current) return
    if (res.ok && res.data.length > 0) {
      lastEventIdRef.current = res.data[res.data.length - 1].id
      setEvents(prev => [...prev, ...res.data].slice(-50))
    }
  }

  async function pollLogs() {
    const res = await cmd.syncthingGetLog(60)
    if (!runningRef.current) return
    if (res.ok) setLogLines(res.data)
  }

  // ── Effects ─────────────────────────────────────────────────

  // Mount: carrega estado inicial
  useEffect(() => {
    runningRef.current = true
    cmd.syncthingGetPaused().then(r => { if (r.ok) setManualPause(r.data) })
    cmd.syncthingGetCredentials().then(r => {
      if (r.ok) { setCredUser(r.data.user); setCredPassword(r.data.password) }
    })
    refresh()
    return () => { runningRef.current = false }
  }, [])

  // Status: poll a cada 5s
  useEffect(() => {
    const id = setInterval(refresh, 5000)
    return () => clearInterval(id)
  }, [])

  // Eventos: poll a cada 5s (só quando rodando)
  useEffect(() => {
    if (!status?.running) return
    const id = setInterval(pollEvents, 5000)
    return () => clearInterval(id)
  }, [status?.running])

  // Logs: poll a cada 10s (só quando seção aberta e rodando)
  useEffect(() => {
    if (!logOpen || !status?.running) return
    pollLogs()
    const id = setInterval(pollLogs, 10_000)
    return () => clearInterval(id)
  }, [logOpen, status?.running])

  // ── Handlers ────────────────────────────────────────────────

  async function handleStart() {
    setStarting(true)
    await cmd.syncthingStart()
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

  async function handlePauseFolder(id: string) {
    setFolderPausing(prev => new Set(prev).add(id))
    await cmd.syncthingPauseFolder(id)
    await refresh()
    setFolderPausing(prev => { const s = new Set(prev); s.delete(id); return s })
  }

  async function handleResumeFolder(id: string) {
    setFolderPausing(prev => new Set(prev).add(id))
    await cmd.syncthingResumeFolder(id)
    await refresh()
    setFolderPausing(prev => { const s = new Set(prev); s.delete(id); return s })
  }

  async function handleSaveCreds() {
    setCredSaving(true)
    const res = await cmd.syncthingSetCredentials(credUser, credPassword)
    setCredSaving(false)
    if (res.ok) { setCredSaved(true); setTimeout(() => setCredSaved(false), 2000) }
  }

  async function handleBackup() {
    setBackingUp(true)
    const res = await cmd.backupKeyData()
    setBackingUp(false)
    if (res.ok) setBackupReport(res.data)
  }

  async function handleCheckIntegrity() {
    setCheckingIntegrity(true)
    const apps = ['akasha', 'kosmos']
    const results = await Promise.all(apps.map(app => cmd.checkDbIntegrity(app)))
    const reports: IntegrityReport[] = []
    for (const r of results) { if (r.ok) reports.push(r.data) }
    setIntegrityResults(reports)
    setCheckingIntegrity(false)
  }

  function openWebPanel() {
    try { window.open('https://127.0.0.1:8384', '_blank') } catch { /* */ }
    navigator.clipboard.writeText('https://127.0.0.1:8384').catch(() => {})
  }

  const running = status?.running ?? false
  const paused  = manualPause || autoPaused

  // ── Render ───────────────────────────────────────────────────

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      padding: '24px 28px', gap: 16, overflowY: 'auto',
    }}>

      {/* Cabeçalho */}
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <span style={{
          fontFamily: 'var(--font-display)', fontStyle: 'italic',
          fontSize: 18, color: 'var(--ink)', letterSpacing: '0.02em',
        }}>
          ⇄ Sync
        </span>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {err && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#8B3A2A' }}>
              {err}
            </span>
          )}
          <button
            onClick={openWebPanel}
            title="Abre https://127.0.0.1:8384 e copia URL para clipboard"
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 10, padding: '2px 8px',
              background: 'transparent', border: '1px solid var(--rule)', borderRadius: 3,
              color: 'var(--ink-ghost)', cursor: 'pointer', opacity: 0.7,
            }}
          >
            painel web ↗
          </button>
        </div>
      </div>

      {/* Status + controles globais */}
      <Card>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
            background: running ? (paused ? '#b8860b' : '#4A6741') : 'var(--ink-ghost)',
            opacity: running ? 1 : 0.4,
          }} />
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink)', flex: 1,
          }}>
            Syncthing — {!running ? 'parado' : paused ? 'pausado' : 'rodando'}
          </span>
          {running
            ? <Btn onClick={handleStop}  disabled={stopping}>{stopping  ? 'encerrando…' : 'Parar'}</Btn>
            : <Btn onClick={handleStart} disabled={starting} accent>{starting ? 'iniciando…' : 'Iniciar'}</Btn>
          }
        </div>
        {running && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <button
              onClick={handleTogglePause}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 10,
                background: 'none', border: 'none', cursor: 'pointer',
                color: manualPause ? 'var(--accent)' : 'var(--ink-ghost)',
                padding: 0, opacity: 0.85,
              }}
            >
              {manualPause ? '▶ retomar sync' : '⏸ pausar sync'}
            </button>
            {autoPaused && (
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 9, color: '#b8860b', opacity: 0.85,
              }}>
                ⚠ pausado automaticamente — apps com banco de dados em uso
              </span>
            )}
          </div>
        )}
      </Card>

      {/* Credenciais GUI (recolhível) */}
      <CollapsibleSection
        title="Credenciais GUI"
        open={credOpen}
        onToggle={() => setCredOpen(o => !o)}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              value={credUser}
              onChange={e => setCredUser(e.target.value)}
              placeholder="Usuário"
              style={{
                flex: 1, fontFamily: 'var(--font-mono)', fontSize: 11,
                background: 'var(--paper)', border: '1px solid var(--rule)',
                borderRadius: 3, padding: '4px 8px', color: 'var(--ink)',
              }}
            />
            <input
              type="password"
              value={credPassword}
              onChange={e => setCredPassword(e.target.value)}
              placeholder="Senha"
              style={{
                flex: 1, fontFamily: 'var(--font-mono)', fontSize: 11,
                background: 'var(--paper)', border: '1px solid var(--rule)',
                borderRadius: 3, padding: '4px 8px', color: 'var(--ink)',
              }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Btn onClick={handleSaveCreds} disabled={credSaving}>
              {credSaved ? '✓ salvo' : credSaving ? 'salvando…' : 'Salvar'}
            </Btn>
            {credUser === '' && credPassword === '' && (
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 9, color: '#b8860b', opacity: 0.85,
              }}>
                credenciais não configuradas — o painel web exige login
              </span>
            )}
          </div>
        </div>
      </CollapsibleSection>

      {/* Pastas */}
      {running && status && status.folders.length > 0 && (
        <Card>
          <SecTitle label="Pastas" />
          {status.folders.map(f => (
            <FolderRow
              key={f.id}
              folder={f}
              pausing={folderPausing.has(f.id)}
              onPause={handlePauseFolder}
              onResume={handleResumeFolder}
              onRescan={handleRescan}
              rescanning={rescanning === f.id}
            />
          ))}
        </Card>
      )}

      {/* Dispositivos */}
      {running && status && status.devices.length > 0 && (
        <Card>
          <SecTitle label="Dispositivos" />
          {status.devices.map(d => (
            <div key={d.device_id} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '7px 0', borderBottom: '1px solid var(--rule)',
            }}>
              <span style={{
                width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                background: d.connected ? '#4A6741' : 'var(--ink-ghost)',
                opacity: d.connected ? 1 : 0.4,
              }} />
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink)', flex: 1,
              }}>
                {d.name}
              </span>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 10,
                color: 'var(--ink-ghost)', opacity: 0.6,
              }}>
                {d.connected
                  ? 'conectado'
                  : d.last_seen ? `último: ${d.last_seen.slice(0, 10)}` : 'desconectado'
                }
              </span>
            </div>
          ))}
        </Card>
      )}

      {/* Atividade recente */}
      {running && (
        <Card>
          <SecTitle label="Atividade recente" />
          {events.length === 0
            ? (
              <p style={{
                fontFamily: 'var(--font-mono)', fontSize: 10,
                color: 'var(--ink-ghost)', opacity: 0.5, margin: '6px 0',
              }}>
                Aguardando eventos…
              </p>
            )
            : (
              <div style={{ maxHeight: 210, overflowY: 'auto' }}>
                {[...events].reverse().map((ev, i) => (
                  <EventRow key={`${ev.id}-${i}`} event={ev} />
                ))}
              </div>
            )
          }
        </Card>
      )}

      {/* Logs Syncthing (recolhível) */}
      {running && (
        <CollapsibleSection
          title="Logs Syncthing"
          open={logOpen}
          onToggle={() => setLogOpen(o => !o)}
        >
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
            <Btn onClick={() => setLogLines([])}>limpar</Btn>
          </div>
          <div style={{
            maxHeight: 200, overflowY: 'auto',
            fontFamily: 'var(--font-mono)', fontSize: 10, lineHeight: 1.5,
          }}>
            {logLines.length === 0
              ? <span style={{ color: 'var(--ink-ghost)', opacity: 0.5 }}>Sem logs.</span>
              : [...logLines].reverse().map((l, i) => (
                <div
                  key={i}
                  style={{
                    color: (l.level === 'WARNING' || l.level === 'CRITICAL')
                      ? 'var(--accent)' : 'var(--ink-ghost)',
                    opacity: l.level === 'INFO' || l.level === 'VERBOSE' ? 0.65 : 1,
                    whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                  }}
                >
                  {l.time.slice(11, 19)} [{l.level.slice(0, 4)}] {l.message}
                </div>
              ))
            }
          </div>
        </CollapsibleSection>
      )}

      {/* Backup e integridade */}
      <Card>
        <SecTitle label="Backup e integridade" />
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
          <Btn onClick={handleBackup} disabled={backingUp}>
            {backingUp ? 'criando backup…' : 'Criar backup agora'}
          </Btn>
          <Btn onClick={handleCheckIntegrity} disabled={checkingIntegrity}>
            {checkingIntegrity ? 'verificando…' : 'Verificar integridade'}
          </Btn>
        </div>

        {backupReport && (
          <div style={{ marginBottom: 8 }}>
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: 9,
              color: 'var(--ink-ghost)', marginBottom: 3,
            }}>
              Backup em {backupReport.timestamp.slice(0, 16).replace('T', ' ')}:
            </div>
            {backupReport.backed_up.map(f => (
              <div key={f} style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: '#4A6741' }}>
                ✓ {f}
              </div>
            ))}
            {backupReport.failed.map(f => (
              <div key={f} style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: '#8B3A2A' }}>
                ✗ {f}
              </div>
            ))}
          </div>
        )}

        {integrityResults.length > 0 && (
          <div>
            {integrityResults.map(r => (
              <div
                key={r.app}
                style={{
                  fontFamily: 'var(--font-mono)', fontSize: 9,
                  color: r.ok ? '#4A6741' : '#8B3A2A', marginBottom: 2,
                }}
              >
                {r.ok ? '✓' : '✗'} {r.app}: {r.details}
                {r.wal_size > 0 && ` (WAL: ${fmtBytes(r.wal_size)})`}
              </div>
            ))}
          </div>
        )}
      </Card>

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
