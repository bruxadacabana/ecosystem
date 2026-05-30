/* ============================================================
   HUB — LogosView
   Seção LOGOS: perfis de workflow + monitor de fila/VRAM +
   painel de gerenciamento de modelos instalados.
   ============================================================ */

import { useCallback, useEffect, useRef, useState } from 'react'
import { listen } from '@tauri-apps/api/event'
import * as cmd from '../lib/tauri'
import type { LogosStatus, ModelInfo, ModelEntry, ModelAssignment, RecommendedModel, PullProgress, EmbedCompatWarning, ModelCorruptedEvent } from '../types'
import { FinetunePanel } from '../components/FinetunePanel'

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

export function LogosView() {
  const [status,       setStatus]       = useState<LogosStatus | null>(null)
  const [profile,      setProfile]      = useState('normal')
  const [,             setModels]       = useState<ModelInfo[]>([])
  const [allModels,    setAllModels]    = useState<ModelEntry[]>([])
  const [silencing,    setSilencing]    = useState(false)
  const [unloading,    setUnloading]    = useState<string | null>(null)
  const [stopping,     setStopping]     = useState(false)
  const [starting,     setStarting]     = useState(false)
  const [toggleError,  setToggleError]  = useState<string | null>(null)
  const [assignments,       setAssignments]       = useState<ModelAssignment[]>([])
  const [editingSlot,       setEditingSlot]       = useState<string | null>(null)
  const [pullProgress,      setPullProgress]      = useState<Map<string, PullProgress>>(new Map())
  const [pulling,           setPulling]           = useState<Set<string>>(new Set())
  const [vramLimit,         setVramLimit]         = useState<number>(85)
  const [cpuLimit,          setCpuLimit]          = useState<number>(85)
  const [cpuThreads,        setCpuThreads]        = useState<number>(4)
  const [flashAttention,    setFlashAttention]    = useState<boolean>(true)
  const vramLimitSynced = useRef(false)
  const cpuLimitSynced  = useRef(false)
  const [embedWarning,    setEmbedWarning]    = useState<EmbedCompatWarning | null>(null)
  const [cancelledPulls, setCancelledPulls] = useState<Set<string>>(new Set())
  const [deleting,       setDeleting]       = useState<string | null>(null)
  const [pullErrors,     setPullErrors]     = useState<Map<string, string>>(new Map())
  const [corruptedModels, setCorruptedModels] = useState<ModelCorruptedEvent[]>([])
  const [repairing,       setRepairing]       = useState<Set<string>>(new Set())
  const [assignCollapsed, setAssignCollapsed] = useState(false)

  const fetchStatus = useCallback(() => {
    cmd.logosGetStatus().then(r => {
      if (!r.ok) return
      setStatus(r.data)
      setProfile(r.data.current_profile)
      if (!vramLimitSynced.current) {
        vramLimitSynced.current = true
        setVramLimit(r.data.vram_limit_pct ?? 85)
      }
      if (!cpuLimitSynced.current) {
        cpuLimitSynced.current = true
        setCpuLimit(r.data.cpu_p3_limit_pct ?? 85)
      }
    })
  }, [])

  const fetchModels = useCallback(() => {
    cmd.logosListModels().then(r => { if (r.ok) setModels(r.data) })
    cmd.logosListAllModels().then(r => { if (r.ok) setAllModels(r.data) })
    cmd.logosGetModelAssignments().then(r => { if (r.ok) setAssignments(r.data) })
  }, [])

  useEffect(() => {
    fetchStatus()
    fetchModels()
    const sid = setInterval(fetchStatus, 4_000)
    const mid = setInterval(fetchModels, 8_000)
    return () => { clearInterval(sid); clearInterval(mid) }
  }, [fetchStatus, fetchModels])

  // Escuta aviso de incompatibilidade de embedding
  useEffect(() => {
    let unlisten: (() => void) | undefined
    listen<EmbedCompatWarning>('logos-embed-compat-warning', ev => {
      setEmbedWarning(ev.payload)
    }).then(fn => { unlisten = fn })
    return () => { unlisten?.() }
  }, [])

  // Carrega configurações de recursos do ecosystem.json uma vez ao montar
  useEffect(() => {
    cmd.readEcosystemConfig().then(r => {
      if (!r.ok) return
      const logos = (r.data as { logos?: { cpu_threads?: number; flash_attention?: boolean } }).logos
      if (logos?.cpu_threads   != null) setCpuThreads(logos.cpu_threads)
      if (logos?.flash_attention != null) setFlashAttention(logos.flash_attention)
    })
  }, [])

  // Escuta eventos de progresso de pull do Ollama
  useEffect(() => {
    let unlisten: (() => void) | undefined
    listen<PullProgress>('logos-pull-progress', ev => {
      const p = ev.payload
      setPullProgress(prev => {
        const next = new Map(prev)
        if (p.done || p.error) {
          next.delete(p.model)
          if (p.done) {
            setPulling(s => { const n = new Set(s); n.delete(p.model); return n })
            setCancelledPulls(s => { const n = new Set(s); n.delete(p.model); return n })
            fetchModels()
          }
        } else {
          next.set(p.model, p)
        }
        return next
      })
    }).then(fn => { unlisten = fn })
    return () => { unlisten?.() }
  }, [fetchModels])

  // Escuta modelos corrompidos/incompletos detectados pelo LOGOS
  useEffect(() => {
    let unlisten: (() => void) | undefined
    listen<ModelCorruptedEvent>('logos-model-corrupted', ev => {
      const e = ev.payload
      setCorruptedModels(prev => {
        // Evita duplicatas — mesmo model_name substitui entry anterior
        const filtered = prev.filter(c => c.model_name !== e.model_name)
        return [...filtered, e]
      })
    }).then(fn => { unlisten = fn })
    return () => { unlisten?.() }
  }, [])

  async function handleCpuThreads(n: number) {
    setCpuThreads(n)
    await cmd.saveEcosystemConfig({ logos: { cpu_threads: n } })
  }

  async function handleFlashAttention(enabled: boolean) {
    setFlashAttention(enabled)
    await cmd.saveEcosystemConfig({ logos: { flash_attention: enabled } })
  }

  async function handleCpuLimit(pct: number) {
    setCpuLimit(pct)
    await cmd.logosSetCpuP3LimitPct(pct)
  }

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

  async function handleStartInference() {
    setStarting(true)
    setToggleError(null)
    const r = await cmd.toggleInference(true)
    setStarting(false)
    if (!r.ok) {
      const msg = r.error?.message
        ?? (r.error?.kind === 'NotFound' ? 'Nenhum modelo instalado — baixe um modelo primeiro' : 'Erro ao ligar')
      setToggleError(msg)
      setTimeout(() => setToggleError(null), 6_000)
      return
    }
    // Com lazy loading, "Ligar IA" apenas seta a flag — o modelo carrega na primeira requisição.
    // A UI transita para "enabled_idle" via status poll. Nenhuma espera adicional necessária.
  }

  async function handleSetModel(app: string, modelType: string, model: string) {
    await cmd.logosSetModelAssignment(app, modelType, model)
    setEditingSlot(null)
    cmd.logosGetModelAssignments().then(r => { if (r.ok) setAssignments(r.data) })
  }

  async function handleStopInference() {
    setStopping(true)
    await cmd.toggleInference(false)
    setTimeout(() => {
      fetchModels()
      setStopping(false)
    }, 1_500)
  }

  async function handlePullModel(model: string) {
    setPulling(s => new Set(s).add(model))
    setPullErrors(prev => { const n = new Map(prev); n.delete(model); return n })
    const r = await cmd.logosPullModel(model)
    // Limpa estado imediatamente — o comando só retorna quando o download termina
    setPulling(s => { const n = new Set(s); n.delete(model); return n })
    setPullProgress(prev => { const n = new Map(prev); n.delete(model); return n })
    if (!r.ok) {
      const msg = r.error?.message ?? 'Erro ao baixar modelo'
      setPullErrors(prev => new Map(prev).set(model, msg))
      setTimeout(() => {
        setPullErrors(prev => { const n = new Map(prev); n.delete(model); return n })
      }, 10_000)
      return
    }
    // Download concluído — atualiza is_installed e modelos instalados
    fetchModels()
  }

  async function handleDeleteModel(name: string) {
    if (!window.confirm(`Remover "${name}"? Esta ação apaga o modelo do disco.`)) return
    setDeleting(name)
    const r = await cmd.logosDeleteModel(name)
    setDeleting(null)
    if (r.ok) {
      fetchModels()
    } else {
      const msg = r.error?.message ?? 'Erro desconhecido'
      window.alert(`Não foi possível remover: ${msg}`)
    }
  }

  async function handleRepairModel(modelName: string) {
    setRepairing(s => new Set(s).add(modelName))
    // Passo 1: remove arquivo corrompido do disco (mantém entry no registry)
    const repairResult = await cmd.logosRepairModel(modelName)
    if (!repairResult.ok) {
      setRepairing(s => { const n = new Set(s); n.delete(modelName); return n })
      window.alert(`Erro ao preparar reparo: ${repairResult.error?.message ?? 'erro desconhecido'}`)
      return
    }
    // Remove da lista de corrompidos antes de iniciar download
    setCorruptedModels(prev => prev.filter(c => c.model_name !== modelName))
    // Passo 2: re-baixa usando o mesmo fluxo de pull (mostra progresso)
    await handlePullModel(modelName)
    setRepairing(s => { const n = new Set(s); n.delete(modelName); return n })
  }

  async function handleUnload(name: string) {
    setUnloading(name)
    await cmd.logosUnloadModel(name)
    setUnloading(null)
    fetchModels()
  }

  const online             = status !== null
  const queue              = status?.queue ?? [0, 0, 0]
  const vramPct            = status?.vram_pct ?? null
  const vramMb             = status?.vram_used_mb ?? null
  const modelClass         = status?.active_model_class ?? null
  const activePriority     = status?.active_priority ?? null
  const activeApp          = status?.active_app ?? null
  const isSurvival         = status?.hardware_mode === 'sobrevivencia'
  const hwProfile          = status?.hardware_profile ?? null
  const hwDisplay          = status?.hardware_profile_display ?? null
  const maxConcurrent      = hwProfile === 'main_pc' ? 2 : 1
  const p3VramBlocked      = status?.p3_vram_blocked ?? false

  const chatOnline        = status?.chat_server_online  ?? false
  const chatModel         = status?.chat_server_model   ?? ''
  const chatMs            = status?.chat_response_ms    ?? null
  const embedOnline       = status?.embed_server_online ?? false
  const embedModel        = status?.embed_server_model  ?? ''
  const embedMs           = status?.embed_response_ms   ?? null
  // inference_enabled: "Ligar IA" foi ativado. O modelo pode ainda não estar carregado (lazy).
  const inferenceEnabled  = status?.inference_enabled   ?? false

  let vramColor = 'var(--accent-green)'
  if (vramPct !== null) {
    if (vramPct > 0.85) vramColor = 'var(--ribbon)'
    else if (vramPct > 0.70) vramColor = 'var(--accent)'
  }

  const cpuPct     = status?.cpu_pct    ?? 0
  const ramFreeMb  = status?.ram_free_mb ?? 0
  const ramTotalMb = status?.ram_total_mb ?? 0
  const ramUsedPct = ramTotalMb > 0 ? (ramTotalMb - ramFreeMb) / ramTotalMb : 0

  const cpuColor = cpuPct > 85 ? 'var(--ribbon)' : cpuPct > 70 ? 'var(--accent)' : 'var(--accent-green)'
  const ramColor = ramUsedPct > 0.85 ? 'var(--ribbon)' : ramUsedPct > 0.70 ? 'var(--accent)' : 'var(--accent-green)'

  const vramLabel =
    vramMb === null ? '—' :
    vramPct !== null
      ? `${(vramMb / 1000).toFixed(1)} GB · ${Math.round(vramPct * 100)}%`
      : `${vramMb} MB`

  return (
    <div style={{ flex: 1, padding: 36, display: 'flex', flexDirection: 'column', gap: 32, overflowY: 'auto' }}>

      {/* ── Banners: modelos corrompidos / download incompleto ──────────────── */}
      {corruptedModels.map(c => {
        const isRepairing = repairing.has(c.model_name)
        const isPulling   = pulling.has(c.model_name)
        const progress    = pullProgress.get(c.model_name)
        const reasonLabel = c.reason === 'incomplete_download'
          ? 'download incompleto'
          : c.reason === 'file_missing'
          ? 'arquivo ausente'
          : 'magic bytes inválidos'
        return (
          <div key={c.model_name} style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
            padding: '12px 16px',
            border: '1px solid var(--ribbon)',
            borderRadius: 'var(--radius)',
            background: 'color-mix(in srgb, var(--ribbon) 10%, var(--surface))',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ color: 'var(--ribbon)', fontSize: 15 }}>⚠</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ribbon)' }}>
                  {c.model_type === 'embed' ? 'Embedding' : 'Chat'} — <strong>{c.model_name}</strong>
                </span>
                <span style={{ fontSize: 11, color: 'var(--ink-ghost)', fontFamily: 'var(--font-mono)' }}>
                  {reasonLabel}
                </span>
              </div>
              {!isRepairing && !isPulling && (
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={() => handleRepairModel(c.model_name)}
                    style={{
                      fontFamily: 'var(--font-mono)', fontSize: 11,
                      background: 'var(--ribbon)', color: '#fff',
                      border: 'none', borderRadius: 'var(--radius)',
                      padding: '4px 12px', cursor: 'pointer',
                    }}
                  >
                    Baixar novamente
                  </button>
                  <button
                    onClick={() => setCorruptedModels(prev => prev.filter(x => x.model_name !== c.model_name))}
                    style={{
                      fontFamily: 'var(--font-mono)', fontSize: 11,
                      background: 'transparent', color: 'var(--ink-ghost)',
                      border: '1px solid var(--rule)', borderRadius: 'var(--radius)',
                      padding: '4px 10px', cursor: 'pointer',
                    }}
                  >
                    Dispensar
                  </button>
                </div>
              )}
              {(isRepairing || isPulling) && (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)' }}>
                  {isRepairing && !isPulling ? 'Removendo arquivo…' : 'Baixando…'}
                </span>
              )}
            </div>
            {isPulling && progress && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <div style={{ height: 4, background: 'var(--rule)', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: progress.total ? `${Math.round((progress.completed ?? 0) / progress.total * 100)}%` : '0%',
                    background: 'var(--ribbon)',
                    transition: 'width 0.3s',
                  }} />
                </div>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)' }}>
                  {progress.total
                    ? `${Math.round((progress.completed ?? 0) / 1_048_576)} MB / ${Math.round(progress.total / 1_048_576)} MB`
                    : progress.status}
                </span>
              </div>
            )}
          </div>
        )
      })}

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
        {p3VramBlocked && (
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            marginTop: 8, padding: '4px 10px',
            border: '1px solid var(--ribbon)', borderRadius: 'var(--radius)',
            background: 'var(--ribbon)10',
          }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--ribbon)', flexShrink: 0 }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ribbon)' }}>
              watchdog VRAM: P3 bloqueado — aguardando VRAM &lt; 70%
            </span>
          </div>
        )}
        <Note>
          {isSurvival
            ? 'CPU-only — VRAM não monitorada'
            : hwDisplay
              ? `${hwDisplay} · ${maxConcurrent === 2 ? 'até 2 modelos leves (≤3B) simultâneos' : '1 modelo por vez'}`
              : '—'}
        </Note>
      </section>

      {/* ── Servidores llama.cpp ─────────────────────── */}
      <section>
        <Label>Servidores</Label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <ServerRow
            label="Servidor LLM (chat)"
            port={8081}
            online={chatOnline}
            model={chatModel}
            responseMs={chatMs}
          />
          <ServerRow
            label="Servidor de Embedding"
            port={8082}
            online={embedOnline}
            model={embedModel}
            responseMs={embedMs}
          />
        </div>
      </section>

      {/* ── CPU / RAM ─────────────────────────────────── */}
      {online && (
        <section>
          <Label>Sistema</Label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 440 }}>
            {/* CPU */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)' }}>CPU</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: cpuColor }}>
                  {Math.round(cpuPct)}%
                </span>
              </div>
              <div style={{ height: 6, background: 'var(--rule)', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{
                  height: '100%',
                  width: `${Math.min(100, Math.round(cpuPct))}%`,
                  background: cpuColor,
                  transition: 'width 400ms ease, background 400ms ease',
                }} />
              </div>
            </div>
            {/* RAM */}
            {ramTotalMb > 0 && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)' }}>RAM</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)', whiteSpace: 'nowrap' }}>
                    {`livre ${(ramFreeMb / 1000).toFixed(1)} GB / ${(ramTotalMb / 1000).toFixed(1)} GB`}
                  </span>
                </div>
                <div style={{ height: 6, background: 'var(--rule)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${Math.min(100, Math.round(ramUsedPct * 100))}%`,
                    background: ramColor,
                    transition: 'width 400ms ease, background 400ms ease',
                  }} />
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* ── Configurações de recursos ─────────────────── */}
      <section>
        <Label>Configurações de recursos</Label>

        {/* Slider de limite de VRAM */}
        <div style={{ marginBottom: 16, maxWidth: 400 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)' }}>
              Limite de VRAM (%)
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink)' }}>
              {vramLimit}%
            </span>
          </div>
          <input
            type="range"
            min={50}
            max={95}
            step={1}
            value={vramLimit}
            onChange={e => setVramLimit(Number(e.target.value))}
            onPointerUp={() => cmd.logosSetVramLimitPct(vramLimit)}
            style={{ width: '100%', accentColor: 'var(--accent)', cursor: 'pointer' }}
          />
          <Note>Tarefas P3 bloqueadas quando VRAM ultrapassar este limite</Note>
        </div>

        {/* Slider de limite de CPU P3 */}
        <div style={{ marginBottom: 16, maxWidth: 400 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)' }}>
              Limite de CPU P3 (%)
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink)' }}>
              {cpuLimit}%
            </span>
          </div>
          <input
            type="range"
            min={30}
            max={99}
            step={1}
            value={cpuLimit}
            onChange={e => setCpuLimit(Number(e.target.value))}
            onPointerUp={() => handleCpuLimit(cpuLimit)}
            style={{ width: '100%', accentColor: 'var(--accent)', cursor: 'pointer' }}
          />
          <Note>Tarefas P3 bloqueadas quando CPU ultrapassar este limite</Note>
        </div>

        {/* Threads CPU — apenas WorkPc (modo sobrevivência) */}
        {isSurvival && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)' }}>
              Threads CPU
            </span>
            <select
              value={cpuThreads}
              onChange={e => handleCpuThreads(Number(e.target.value))}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 11,
                background: 'var(--paper)', color: 'var(--ink)',
                border: '1px solid var(--rule)', borderRadius: 'var(--radius)',
                padding: '3px 8px', cursor: 'pointer',
              }}
            >
              <option value={2}>2</option>
              <option value={3}>3</option>
              <option value={4}>4</option>
            </select>
          </div>
        )}

        {/* Toggle FlashAttention */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)' }}>
            FlashAttention
          </span>
          <button
            onClick={() => handleFlashAttention(!flashAttention)}
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 10,
              padding: '3px 12px',
              background: flashAttention ? 'var(--accent)' : 'transparent',
              color: flashAttention ? 'var(--paper)' : 'var(--ink-ghost)',
              border: `1px solid ${flashAttention ? 'var(--accent)' : 'var(--rule)'}`,
              borderRadius: 'var(--radius)', cursor: 'pointer',
              transition: 'all 150ms ease',
            }}
          >
            {flashAttention ? 'Ligado' : 'Desligado'}
          </button>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', opacity: 0.6 }}>
            Otimização de atenção com GPU
          </span>
        </div>
      </section>

      {/* ── Aviso de incompatibilidade de embedding ───── */}
      {embedWarning && (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          padding: '12px 14px',
          border: '1px solid var(--ribbon)',
          borderRadius: 'var(--radius)',
          background: 'var(--ribbon)10',
        }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ribbon)' }}>
            Atenção: incompatibilidade de embedding detectada
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', lineHeight: 1.6 }}>
            Trocar de <strong>{embedWarning.old_model}</strong> ({embedWarning.old_dims} dims) para{' '}
            <strong>{embedWarning.new_model}</strong> ({embedWarning.new_dims} dims) exige reindexação
            completa — os vetores atuais são incompatíveis. Limpe a coleção no Mnemosyne e
            reindexe antes de usar o RAG.
          </span>
          <button
            onClick={() => setEmbedWarning(null)}
            style={{
              alignSelf: 'flex-start',
              fontFamily: 'var(--font-mono)', fontSize: 10,
              padding: '2px 10px', background: 'transparent',
              color: 'var(--ink-ghost)', border: '1px solid var(--rule)',
              borderRadius: 'var(--radius)', cursor: 'pointer',
            }}
          >
            Entendido
          </button>
        </div>
      )}

      {/* ── Modelos por app ──────────────────────────── */}
      {assignments.length > 0 && (
        <section>
          <div
            style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: assignCollapsed ? 0 : 12, cursor: 'pointer', userSelect: 'none' }}
            onClick={() => setAssignCollapsed(c => !c)}
          >
            <CollapseChevron collapsed={assignCollapsed} />
            <h3 style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--ink-ghost)', margin: 0 }}>
              Modelos por app
            </h3>
            {hwDisplay && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, padding: '1px 8px', border: '1px solid var(--accent)40', borderRadius: 10, color: 'var(--accent)' }}>
                {hwDisplay}
              </span>
            )}
            {maxConcurrent === 2 && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, padding: '1px 8px', border: '1px solid var(--accent-green)40', borderRadius: 10, color: 'var(--accent-green)' }}>
                até 2 leves simultâneos
              </span>
            )}
          </div>
          {!assignCollapsed && <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
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
                        {/* Botão baixar — só aparece quando não instalado E pode ser baixado via HUB */}
                        {!a.is_installed && a.is_downloadable && (() => {
                          const isPullingThis = pulling.has(a.current_model)
                          return (
                            <button
                              disabled={isPullingThis}
                              onClick={() => handlePullModel(a.current_model)}
                              style={{
                                fontFamily: 'var(--font-mono)', fontSize: 10,
                                padding: '2px 8px', background: 'transparent',
                                color: isPullingThis ? 'var(--ink-ghost)' : 'var(--accent-green)',
                                border: `1px solid ${isPullingThis ? 'var(--rule)' : 'var(--accent-green)'}`,
                                borderRadius: 'var(--radius)',
                                cursor: isPullingThis ? 'wait' : 'pointer',
                                opacity: isPullingThis ? 0.6 : 1,
                              }}
                            >
                              {isPullingThis ? 'baixando…' : 'baixar'}
                            </button>
                          )
                        })()}
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
                  {/* Progresso de download quando baixando via botão desta linha */}
                  {pulling.has(a.current_model) && (() => {
                    const prog      = pullProgress.get(a.current_model)
                    const pct       = prog?.total && prog.completed != null ? Math.round((prog.completed / prog.total) * 100) : null
                    const fileTotal = prog?.file_total ?? 1
                    const fileIdx   = prog?.file_index ?? 0
                    const fileLabel = fileTotal > 1 ? `Arquivo ${fileIdx + 1}/${fileTotal} · ` : ''
                    return (
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-ghost)' }}>
                        {pct !== null
                          ? <><div style={{ height: 3, background: 'var(--rule)', borderRadius: 2, marginTop: 4 }}><div style={{ height: '100%', width: `${pct}%`, background: 'var(--accent-green)', borderRadius: 2, transition: 'width 0.3s' }} /></div><span>{fileLabel}{pct}%</span></>
                          : <span>{fileLabel}{prog?.status ?? 'baixando…'}</span>
                        }
                      </div>
                    )
                  })()}
                  {pullErrors.has(a.current_model) && (
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ribbon)' }}>
                      {pullErrors.get(a.current_model)}
                    </span>
                  )}
                </div>
              )
            })}
          </div>}
        </section>
      )}

      {/* ── Modelos instalados ───────────────────────── */}
      <section>
        <Label>Modelos instalados</Label>
        {allModels.length === 0 ? (
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
                  {isActive ? (
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
                  ) : (
                    <button
                      disabled={deleting === m.name}
                      onClick={() => handleDeleteModel(m.name)}
                      title="Remover modelo do disco"
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 10,
                        padding: '3px 10px',
                        background: 'transparent',
                        color: deleting === m.name ? 'var(--ink-ghost)' : 'var(--ribbon)',
                        border: `1px solid ${deleting === m.name ? 'var(--rule)' : 'var(--ribbon)40'}`,
                        borderRadius: 'var(--radius)',
                        cursor: deleting === m.name ? 'wait' : 'pointer',
                        opacity: deleting === m.name ? 0.5 : 1,
                        transition: 'all 150ms ease',
                      }}
                    >
                      {deleting === m.name ? '…' : 'remover'}
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* ── Fine-Tuning ───────────────────────────────── */}
      <section>
        <FinetunePanel logosStatus={status} />
      </section>

      {/* ── Ações ─────────────────────────────────────── */}
      {/* Estados:
          disabled      → inference_enabled=false: botão "Ligar IA"
          enabled_idle  → inference_enabled=true + chat offline: "IA ativa — aguardando"
          active        → inference_enabled=true + chat online: modelo carregado */}
      <section style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <button
          className="btn btn-ghost btn-sm"
          disabled={silencing}
          onClick={handleSilence}
          title="Descarregar modelos da memória"
          style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}
        >
          {silencing ? '…' : 'Descarregar modelos'}
        </button>

        {/* Estado: disabled — IA desligada */}
        {!inferenceEnabled && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <button
              className="btn btn-ghost btn-sm"
              disabled={starting}
              onClick={handleStartInference}
              title="Ativar IA — modelo carregará na primeira requisição"
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: toggleError ? 'var(--ribbon)' : 'var(--accent-green)',
                borderColor: toggleError ? 'var(--ribbon)' : 'var(--accent-green)',
                opacity: starting ? 0.6 : 1,
              }}
            >
              {starting ? 'Ativando…' : 'Ligar IA'}
            </button>
            {toggleError && (
              <span style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                color: 'var(--ribbon)',
                maxWidth: 300,
                lineHeight: 1.5,
              }}>
                {toggleError}
              </span>
            )}
          </div>
        )}

        {/* Estado: enabled_idle — IA ativa, modelo ainda não carregado */}
        {inferenceEnabled && !chatOnline && (
          <>
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: 'var(--accent)',
              opacity: 0.85,
            }}
              title="IA ativa — modelo carregará automaticamente na primeira requisição"
            >
              IA ativa — aguardando requisição
            </span>
            <button
              className="btn btn-ghost btn-sm"
              disabled={stopping}
              onClick={handleStopInference}
              title="Desligar IA e cancelar carregamento"
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: stopping ? 'var(--ink-ghost)' : 'var(--ribbon)',
                borderColor: stopping ? 'var(--rule)' : 'var(--ribbon)',
                opacity: stopping ? 0.5 : 1,
              }}
            >
              {stopping ? '…' : 'Desligar IA'}
            </button>
          </>
        )}

        {/* Estado: active — modelo carregado e servindo */}
        {inferenceEnabled && chatOnline && (
          <>
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: 'var(--accent-green)',
              opacity: 0.7,
            }}>
              IA ativa
            </span>
            <button
              className="btn btn-ghost btn-sm"
              disabled={stopping}
              onClick={handleStopInference}
              title="Descarregar modelo e liberar VRAM"
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: stopping ? 'var(--ink-ghost)' : 'var(--ribbon)',
                borderColor: stopping ? 'var(--rule)' : 'var(--ribbon)',
                opacity: stopping ? 0.5 : 1,
              }}
            >
              {stopping ? '…' : 'Desligar IA'}
            </button>
          </>
        )}
      </section>
    </div>
  )
}

// ── Helpers de estilo ──────────────────────────────────────────

function CollapseChevron({ collapsed }: { collapsed: boolean }) {
  return (
    <span style={{
      fontFamily: 'var(--font-mono)', fontSize: 9,
      color: 'var(--ink-ghost)', opacity: 0.6,
      transition: 'transform 150ms ease',
      display: 'inline-block',
      transform: collapsed ? 'rotate(-90deg)' : 'rotate(0deg)',
      userSelect: 'none',
    }}>
      ▾
    </span>
  )
}

function SectionToggle({ label, collapsed, onToggle }: { label: string; collapsed: boolean; onToggle: () => void }) {
  return (
    <div
      onClick={onToggle}
      style={{
        display: 'flex', alignItems: 'center', gap: 6,
        marginBottom: collapsed ? 0 : 12,
        cursor: 'pointer', userSelect: 'none',
      }}
    >
      <CollapseChevron collapsed={collapsed} />
      <h3 style={{
        fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.12em',
        textTransform: 'uppercase', color: 'var(--ink-ghost)', margin: 0,
      }}>
        {label}
      </h3>
    </div>
  )
}

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

function ServerRow({
  label, port, online, model, responseMs,
}: {
  label: string
  port: number
  online: boolean
  model: string
  responseMs: number | null
}) {
  const dotColor = online ? 'var(--accent-green)' : 'var(--rule)'
  const statusText = online
    ? (model || '(carregando…)')
    : 'offline'

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      padding: '6px 12px',
      border: `1px solid ${online ? 'var(--accent-green)20' : 'var(--rule)'}`,
      borderRadius: 'var(--radius)',
      background: online ? 'var(--accent-green)06' : 'transparent',
      transition: 'all 200ms ease',
    }}>
      {/* Status dot */}
      <span
        title={online ? `Online — porta ${port}` : `Offline — porta ${port}`}
        style={{
          width: 7, height: 7, borderRadius: '50%',
          background: dotColor,
          boxShadow: online ? `0 0 5px ${dotColor}` : 'none',
          flexShrink: 0,
          transition: 'all 200ms ease',
        }}
      />
      {/* Label */}
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 10,
        color: 'var(--ink-ghost)', minWidth: 160,
      }}>
        {label}
      </span>
      {/* Modelo ou "offline" */}
      <span style={{
        flex: 1,
        fontFamily: 'var(--font-mono)', fontSize: 11,
        color: online ? 'var(--ink)' : 'var(--ink-ghost)',
        opacity: online ? 1 : 0.5,
      }}>
        {statusText}
      </span>
      {/* Porta */}
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 9,
        color: 'var(--ink-ghost)', opacity: 0.5,
        padding: '1px 6px',
        border: '1px solid var(--rule)',
        borderRadius: 4,
      }}>
        :{port}
      </span>
      {/* Latência */}
      {responseMs !== null && (
        <span
          title="Latência do último /health"
          style={{
            fontFamily: 'var(--font-mono)', fontSize: 9,
            color: responseMs < 50
              ? 'var(--accent-green)'
              : responseMs < 200
                ? 'var(--accent)'
                : 'var(--ribbon)',
            minWidth: 40, textAlign: 'right',
          }}
        >
          {responseMs}ms
        </span>
      )}
    </div>
  )
}
