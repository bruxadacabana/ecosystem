/* ============================================================
   HUB — LogosView
   Seção LOGOS: perfis de workflow + monitor de fila/VRAM +
   painel de gerenciamento de modelos Ollama.
   ============================================================ */

import { useCallback, useEffect, useState } from 'react'
import * as cmd from '../lib/tauri'
import { listModels } from '../lib/ollama'
import type { LogosStatus, OllamaModelInfo, OllamaModelEntry, ModelAssignment } from '../types'

const PROFILES = [
  { id: 'normal',  label: 'Normal',  tip: 'Prioridades padrão de cada app'                       },
  { id: 'escrita', label: 'Escrita', tip: 'AETHER P1; KOSMOS reader → P2; Mnemosyne RAG → P3'   },
  { id: 'estudo',  label: 'Estudo',  tip: 'Mnemosyne RAG → P1; KOSMOS reader → P2'               },
  { id: 'consumo', label: 'Consumo', tip: 'KOSMOS P1, Hermes liberado, sem override'              },
]

const P_COLORS: Record<number, string> = {
  1: 'var(--accent)',
  2: 'var(--accent-green)',
  3: 'var(--ink-faint)',
}

interface LogosViewProps {
  onOpenChat: () => void
}

export function LogosView({ onOpenChat }: LogosViewProps) {
  const [status,       setStatus]       = useState<LogosStatus | null>(null)
  const [profile,      setProfile]      = useState('normal')
  const [models,       setModels]       = useState<OllamaModelInfo[]>([])
  const [allModels,    setAllModels]    = useState<OllamaModelEntry[]>([])
  const [silencing,    setSilencing]    = useState(false)
  const [unloading,    setUnloading]    = useState<string | null>(null)
  const [stopping,       setStopping]       = useState(false)
  const [ollamaOnline,   setOllamaOnline]   = useState<boolean | null>(null)
  const [launchStatus,   setLaunchStatus]   = useState<'idle' | 'starting' | 'error'>('idle')
  const [assignments,    setAssignments]    = useState<ModelAssignment[]>([])
  const [editingSlot,    setEditingSlot]    = useState<string | null>(null) // "app_type" key

  const fetchStatus = useCallback(() => {
    cmd.logosGetStatus().then(r => {
      if (!r.ok) return
      setStatus(r.data)
      setProfile(r.data.current_profile)
    })
  }, [])

  const fetchModels = useCallback(() => {
    cmd.logosListModels().then(r => {
      if (r.ok) setModels(r.data)
    })
    cmd.logosListAllModels().then(r => {
      if (r.ok) setAllModels(r.data)
    })
    cmd.logosGetModelAssignments().then(r => {
      if (r.ok) setAssignments(r.data)
    })
  }, [])

  const checkOllama = useCallback(() => {
    listModels()
      .then(() => setOllamaOnline(true))
      .catch(() => setOllamaOnline(false))
  }, [])

  useEffect(() => {
    fetchStatus()
    fetchModels()
    checkOllama()
    const sid = setInterval(fetchStatus, 4_000)
    const mid = setInterval(fetchModels, 8_000)
    const oid = setInterval(checkOllama, 4_000)
    return () => { clearInterval(sid); clearInterval(mid); clearInterval(oid) }
  }, [fetchStatus, fetchModels, checkOllama])

  async function handleProfile(id: string) {
    setProfile(id)
    await cmd.logosSetProfile(id)
  }

  async function handleSilence() {
    setSilencing(true)
    await cmd.logosSilence()
    setSilencing(false)
    fetchModels()
  }

  async function handleLaunchOllama() {
    setLaunchStatus('starting')
    const r = await cmd.launchOllama()
    if (r.ok) {
      setLaunchStatus('idle')
      setTimeout(checkOllama, 1_500)
      setTimeout(checkOllama, 3_500)
    } else {
      setLaunchStatus('error')
      setTimeout(() => setLaunchStatus('idle'), 3_000)
    }
  }

  async function handleSetModel(app: string, modelType: string, model: string) {
    await cmd.logosSetModelAssignment(app, modelType, model)
    setEditingSlot(null)
    cmd.logosGetModelAssignments().then(r => { if (r.ok) setAssignments(r.data) })
  }

  async function handleStopOllama() {
    setStopping(true)
    await cmd.stopOllama()
    setTimeout(() => {
      checkOllama()
      fetchModels()
      setStopping(false)
    }, 1_500)
  }

  async function handleUnload(name: string) {
    setUnloading(name)
    await cmd.logosUnloadModel(name)
    setUnloading(null)
    fetchModels()
  }

  const online         = status !== null
  const queue          = status?.queue ?? [0, 0, 0]
  const vramPct        = status?.vram_pct ?? null
  const vramMb         = status?.vram_used_mb ?? null
  const modelClass     = status?.active_model_class ?? null
  const activePriority = status?.active_priority ?? null
  const activeApp      = status?.active_app ?? null
  const isSurvival     = status?.hardware_mode === 'sobrevivencia'

  let vramColor = 'var(--accent-green)'
  if (vramPct !== null) {
    if (vramPct > 0.85) vramColor = 'var(--ribbon)'
    else if (vramPct > 0.70) vramColor = 'var(--accent)'
  }

  const vramLabel =
    vramMb === null ? '—' :
    vramPct !== null
      ? `${(vramMb / 1000).toFixed(1)} GB · ${Math.round(vramPct * 100)}%`
      : `${vramMb} MB`

  return (
    <div style={{ flex: 1, padding: 36, display: 'flex', flexDirection: 'column', gap: 32, overflowY: 'auto' }}>

      {/* ── Badge: Modo Sobrevivência ──────────────────── */}
      {isSurvival && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '10px 14px',
          border: '1px solid var(--accent)',
          borderRadius: 'var(--radius)',
          background: 'var(--accent)18',
        }}>
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '0.10em',
            textTransform: 'uppercase',
            color: 'var(--accent)',
          }}>
            Modo Sobrevivência — Windows
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', opacity: 0.7 }}>
            · keep_alive: 0 · num_ctx ≤ 2048 · apenas modelos ≤3B · P3 desabilitado
          </span>
        </div>
      )}

      {/* ── Perfis de workflow ─────────────────────────── */}
      <section>
        <Label>Perfil de workflow</Label>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
          {PROFILES.map(p => {
            const active = profile === p.id
            return (
              <button
                key={p.id}
                title={p.tip}
                onClick={() => handleProfile(p.id)}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  letterSpacing: '0.06em',
                  padding: '5px 14px',
                  background: active ? 'var(--accent)' : 'transparent',
                  color: active ? 'var(--paper)' : 'var(--ink-ghost)',
                  border: `1px solid ${active ? 'var(--accent)' : 'var(--rule)'}`,
                  borderRadius: 'var(--radius)',
                  cursor: 'pointer',
                  transition: 'all 150ms ease',
                }}
              >
                {p.label}
              </button>
            )
          })}
        </div>
        {profile !== 'normal' && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', margin: 0 }}>
            {PROFILES.find(p => p.id === profile)?.tip}
          </p>
        )}
      </section>

      {/* ── Monitor de fila ───────────────────────────── */}
      <section>
        <Label>Fila de requisições</Label>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {([1, 2, 3] as const).map(p => {
            const isActive = activePriority === p
            const waiting  = queue[p - 1]
            const color    = P_COLORS[p]
            return (
              <div
                key={p}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '6px 14px',
                  border: `1px solid ${isActive ? color : 'var(--rule)'}`,
                  borderRadius: 'var(--radius)',
                  background: isActive ? `${color}18` : 'transparent',
                  transition: 'all 200ms ease',
                }}
              >
                <span style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: isActive ? color : 'var(--rule)',
                  boxShadow: isActive ? `0 0 5px ${color}` : 'none',
                  flexShrink: 0,
                }} />
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: isActive ? color : 'var(--ink-ghost)' }}>
                  P{p}
                  {waiting > 0 && <span style={{ marginLeft: 4, color: 'var(--ink-faint)' }}>+{waiting}</span>}
                </span>
              </div>
            )
          })}

          {modelClass !== null && (
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              letterSpacing: '0.06em',
              padding: '5px 10px',
              border: `1px solid ${modelClass === 'leve' ? 'var(--accent-green)' : 'var(--accent)'}`,
              borderRadius: 'var(--radius)',
              color: modelClass === 'leve' ? 'var(--accent-green)' : 'var(--accent)',
              opacity: 0.85,
            }}>
              {modelClass}
            </span>
          )}

          {activeApp !== null && (
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              letterSpacing: '0.06em',
              padding: '5px 10px',
              border: '1px solid var(--rule)',
              borderRadius: 'var(--radius)',
              color: 'var(--ink-ghost)',
              opacity: 0.75,
            }}>
              {activeApp}
            </span>
          )}

          {!online && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)' }}>
              LOGOS offline
            </span>
          )}
        </div>
      </section>

      {/* ── VRAM ──────────────────────────────────────── */}
      <section>
        <Label>VRAM</Label>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, maxWidth: 440 }}>
          <div style={{ flex: 1, height: 6, background: 'var(--rule)', borderRadius: 3, overflow: 'hidden' }}>
            {vramPct !== null && (
              <div style={{
                height: '100%',
                width: `${Math.min(100, Math.round(vramPct * 100))}%`,
                background: vramColor,
                transition: 'width 400ms ease, background 400ms ease',
              }} />
            )}
          </div>
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--ink-ghost)',
            whiteSpace: 'nowrap',
            minWidth: 90,
          }}>
            {vramLabel}
          </span>
        </div>
        <Note>
          {isSurvival
            ? 'CPU-only — VRAM não monitorada'
            : 'RX 6600 · 8 GB VRAM · HSA_OVERRIDE_GFX_VERSION=10.3.0'}
        </Note>
      </section>

      {/* ── Modelos por app ──────────────────────────── */}
      {assignments.length > 0 && (
        <section>
          <Label>Modelos por app</Label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {assignments.map(a => {
              const slotKey = `${a.app}_${a.model_type}`
              const isEditing = editingSlot === slotKey
              const fitColor = a.fits_hardware
                ? 'var(--accent-green)'
                : 'var(--ribbon)'
              const fitTitle = a.fits_hardware
                ? `Estimado: ~${a.vram_required_mb} MB · Disponível: ${a.vram_budget_mb} MB`
                : `Não cabe: precisa ~${a.vram_required_mb} MB · Disponível: ${a.vram_budget_mb} MB`
              return (
                <div
                  key={slotKey}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                    padding: '8px 12px',
                    border: '1px solid var(--rule)',
                    borderRadius: 'var(--radius)',
                  }}
                >
                  {/* Linha principal */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', minWidth: 160 }}>
                      {a.label}
                    </span>
                    {!isEditing ? (
                      <>
                        <span style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink)' }}>
                          {a.current_model}
                        </span>
                        {!a.is_custom && (
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--accent-green)', border: '1px solid var(--accent-green)40', borderRadius: 10, padding: '1px 6px' }}>
                            recomendado
                          </span>
                        )}
                        {/* Indicador de compatibilidade */}
                        <span
                          title={fitTitle}
                          style={{
                            width: 7, height: 7, borderRadius: '50%',
                            background: fitColor,
                            flexShrink: 0,
                            cursor: 'help',
                          }}
                        />
                        <button
                          onClick={() => setEditingSlot(slotKey)}
                          style={{
                            fontFamily: 'var(--font-mono)', fontSize: 10,
                            padding: '2px 8px', background: 'transparent',
                            color: 'var(--ink-ghost)', border: '1px solid var(--rule)',
                            borderRadius: 'var(--radius)', cursor: 'pointer',
                          }}
                        >
                          editar
                        </button>
                      </>
                    ) : (
                      <>
                        <select
                          defaultValue={a.current_model}
                          onChange={e => handleSetModel(a.app, a.model_type, e.target.value)}
                          style={{
                            flex: 1, fontFamily: 'var(--font-mono)', fontSize: 11,
                            background: 'var(--paper)', color: 'var(--ink)',
                            border: '1px solid var(--accent)', borderRadius: 'var(--radius)',
                            padding: '3px 6px', cursor: 'pointer',
                          }}
                        >
                          {/* Recomendado primeiro */}
                          <option value={a.recommended_model}>
                            {a.recommended_model} (recomendado)
                          </option>
                          {allModels
                            .filter(m => m.name !== a.recommended_model)
                            .map(m => (
                              <option key={m.name} value={m.name}>{m.name}</option>
                            ))}
                        </select>
                        <button
                          onClick={() => setEditingSlot(null)}
                          style={{
                            fontFamily: 'var(--font-mono)', fontSize: 10,
                            padding: '2px 8px', background: 'transparent',
                            color: 'var(--ink-ghost)', border: '1px solid var(--rule)',
                            borderRadius: 'var(--radius)', cursor: 'pointer',
                          }}
                        >
                          ✕
                        </button>
                      </>
                    )}
                  </div>
                  {/* Botão "usar recomendado" quando customizado */}
                  {a.is_custom && !isEditing && (
                    <button
                      onClick={() => handleSetModel(a.app, a.model_type, a.recommended_model)}
                      style={{
                        fontFamily: 'var(--font-mono)', fontSize: 9,
                        padding: '2px 8px', background: 'transparent',
                        color: 'var(--ink-ghost)', border: '1px solid var(--rule)',
                        borderRadius: 'var(--radius)', cursor: 'pointer',
                        alignSelf: 'flex-start',
                      }}
                    >
                      ↩ usar recomendado ({a.recommended_model})
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* ── Modelos Ollama ────────────────────────────── */}
      <section>
        <Label>Modelos Ollama</Label>
        {!ollamaOnline ? (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)', margin: 0 }}>
            {ollamaOnline === null ? '…' : 'Ollama offline'}
          </p>
        ) : allModels.length === 0 ? (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)', margin: 0 }}>
            Nenhum modelo instalado
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {allModels.map(m => {
              const isActive = m.status === 'active'
              const dotColor = isActive ? 'var(--accent-green)' : 'var(--accent)'
              return (
                <div
                  key={m.name}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '6px 12px',
                    border: `1px solid ${isActive ? 'var(--accent-green)30' : 'var(--rule)'}`,
                    borderRadius: 'var(--radius)',
                    background: isActive ? 'var(--accent-green)08' : 'transparent',
                    transition: 'all 200ms ease',
                  }}
                >
                  {/* Indicador de status */}
                  <span
                    title={isActive ? 'Ativo na VRAM' : 'Disponível'}
                    style={{
                      width: 7, height: 7, borderRadius: '50%',
                      background: dotColor,
                      boxShadow: isActive ? `0 0 5px ${dotColor}` : 'none',
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink)' }}>
                    {m.name}
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', minWidth: 52, textAlign: 'right' }}>
                    {isActive && m.size_vram_mb > 0
                      ? `${m.size_vram_mb >= 1000 ? `${(m.size_vram_mb / 1000).toFixed(1)} GB` : `${m.size_vram_mb} MB`} VRAM`
                      : m.size_disk_mb >= 1000
                        ? `${(m.size_disk_mb / 1000).toFixed(1)} GB`
                        : `${m.size_disk_mb} MB`}
                  </span>
                  {isActive && (
                    <button
                      disabled={unloading === m.name}
                      onClick={() => handleUnload(m.name)}
                      title="Descarregar da VRAM"
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 10,
                        padding: '3px 10px',
                        background: 'transparent',
                        color: 'var(--ink-ghost)',
                        border: '1px solid var(--rule)',
                        borderRadius: 'var(--radius)',
                        cursor: unloading === m.name ? 'wait' : 'pointer',
                        opacity: unloading === m.name ? 0.5 : 1,
                        transition: 'all 150ms ease',
                      }}
                    >
                      {unloading === m.name ? '…' : 'descarregar'}
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* ── Ações ─────────────────────────────────────── */}
      <section style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <button
          className="btn btn-ghost btn-sm"
          onClick={onOpenChat}
          style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}
        >
          Abrir chat →
        </button>
        <button
          className="btn btn-ghost btn-sm"
          disabled={silencing}
          onClick={handleSilence}
          title="Descarregar todos os modelos carregados no Ollama"
          style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}
        >
          {silencing ? '…' : 'Silenciar Ollama'}
        </button>
        {ollamaOnline === false && (
          <button
            className="btn btn-ghost btn-sm"
            disabled={launchStatus === 'starting'}
            onClick={handleLaunchOllama}
            title="Iniciar o servidor Ollama com as flags de hardware corretas"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: launchStatus === 'error' ? 'var(--ribbon)' : 'var(--accent-green)',
              borderColor: launchStatus === 'error' ? 'var(--ribbon)' : 'var(--accent-green)',
              opacity: launchStatus === 'starting' ? 0.6 : 1,
            }}
          >
            {launchStatus === 'starting' ? 'Iniciando…'
             : launchStatus === 'error'   ? 'Erro — tentar novamente'
             : 'Iniciar Ollama'}
          </button>
        )}
        {ollamaOnline === true && (
          <>
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: 'var(--accent-green)',
              opacity: 0.7,
            }}>
              Ollama ativo
            </span>
            <button
              className="btn btn-ghost btn-sm"
              disabled={stopping}
              onClick={handleStopOllama}
              title="Encerrar o processo Ollama"
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: stopping ? 'var(--ink-ghost)' : 'var(--ribbon)',
                borderColor: stopping ? 'var(--rule)' : 'var(--ribbon)',
                opacity: stopping ? 0.5 : 1,
              }}
            >
              {stopping ? '…' : 'Parar Ollama'}
            </button>
          </>
        )}
      </section>
    </div>
  )
}

// ── Helpers de estilo ──────────────────────────────────────────

function Label({ children }: { children: React.ReactNode }) {
  return (
    <h3 style={{
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      letterSpacing: '0.12em',
      textTransform: 'uppercase',
      color: 'var(--ink-ghost)',
      margin: '0 0 12px',
    }}>
      {children}
    </h3>
  )
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <p style={{
      marginTop: 8,
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      color: 'var(--ink-ghost)',
      opacity: 0.6,
      margin: '8px 0 0',
    }}>
      {children}
    </p>
  )
}
