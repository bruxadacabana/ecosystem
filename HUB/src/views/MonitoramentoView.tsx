/* ============================================================
   HUB — MonitoramentoView
   Painel de processamento em background + editor de personalidade
   + viewer de memória pessoal (AKASHA, Mnemosyne) + status KOSMOS.
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { EcosystemConfig, MemoryEntry } from '../types'

// ── Faixa de logs em tempo real ────────────────────────────────

function LogStrip({ lines }: { lines: string[] }) {
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'nearest' })
  }, [lines])

  return (
    <div style={{
      marginTop: 10,
      background: 'var(--paper)',
      border: '1px solid var(--rule)',
      borderRadius: 4,
      padding: '5px 8px',
      maxHeight: 130,
      overflowY: 'auto',
    }}>
      {lines.length === 0
        ? <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', opacity: 0.5 }}>sem logs</span>
        : lines.map((l, i) => {
            const level = l.match(/\[(ERROR|WARNING|WARN)\]/) ? 'error'
              : l.match(/\[(WARNING|WARN)\]/) ? 'warn' : 'normal'
            return (
              <div key={i} style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                lineHeight: 1.5,
                color: level === 'error' ? '#c0392b'
                  : level === 'warn' ? '#b8860b'
                  : 'var(--ink-ghost)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }} title={l}>
                {l}
              </div>
            )
          })
      }
      <div ref={endRef} />
    </div>
  )
}

function useAkashaLogs(baseUrl: string, active: boolean) {
  const [lines, setLines] = useState<string[]>([])
  useEffect(() => {
    let running = true
    async function poll() {
      try {
        const res = await fetch(`${baseUrl}/system/logs?n=10`)
        if (res.ok) {
          const data = await res.json()
          if (running) setLines(data.lines ?? [])
        }
      } catch { /* AKASHA offline */ }
      if (running) setTimeout(poll, 3000)
    }
    poll()
    return () => { running = false }
  }, [baseUrl, active])
  return lines
}

function useMnemosyneLogs() {
  const [lines, setLines] = useState<string[]>([])
  useEffect(() => {
    let running = true
    async function poll() {
      const res = await cmd.readAppLog('mnemosyne', 10)
      if (running && res.ok) setLines(res.data)
      if (running) setTimeout(poll, 3000)
    }
    poll()
    return () => { running = false }
  }, [])
  return lines
}

// ── Tipos locais ──────────────────────────────────────────────

interface AkashaBg {
  knowledge_extraction: number
  worker_active:        boolean
}

interface MnemosyneBg {
  indexing:      boolean
  files_pending: number
  current_file:  string | null
}

interface KosmosBg {
  pending:       number
  worker_active: boolean
}

// ── Badge de tipo de memória ─────────────────────────────────

const TYPE_COLORS: Record<string, string> = {
  observation: '#4A6741',
  connection:  '#2C5F8A',
  surprise:    '#8B3A2A',
  reflection:  '#6B4C8A',
}

function TypeBadge({ type }: { type: string }) {
  return (
    <span style={{
      fontFamily:    'var(--font-mono)',
      fontSize:      9,
      letterSpacing: '0.1em',
      textTransform: 'uppercase',
      color:         TYPE_COLORS[type] ?? 'var(--ink-ghost)',
      border:        `1px solid ${TYPE_COLORS[type] ?? 'var(--rule)'}55`,
      borderRadius:  3,
      padding:       '1px 5px',
      flexShrink:    0,
    }}>
      {type}
    </span>
  )
}

// ── Viewer de memória (carregado sob demanda) ─────────────────

function MemoryViewer({ app }: { app: 'akasha' | 'mnemosyne' }) {
  const [open,     setOpen]     = useState(false)
  const [entries,  setEntries]  = useState<MemoryEntry[]>([])
  const [loading,  setLoading]  = useState(false)
  const [err,      setErr]      = useState<string | null>(null)
  const [deleting, setDeleting] = useState<number | null>(null)

  async function load() {
    setLoading(true)
    setErr(null)
    const res = await cmd.memoryGetEntries(app, 30)
    setLoading(false)
    if (res.ok) setEntries(res.data)
    else setErr(res.error.message)
  }

  async function handleOpen() {
    const next = !open
    setOpen(next)
    if (next && entries.length === 0) load()
  }

  async function handleDelete(id: number) {
    setDeleting(id)
    const res = await cmd.memoryDeleteEntry(app, id)
    setDeleting(null)
    if (res.ok) setEntries(prev => prev.filter(e => e.id !== id))
  }

  return (
    <div style={{ marginTop: 10 }}>
      <button
        onClick={handleOpen}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          fontFamily: 'var(--font-mono)', fontSize: 10,
          color: 'var(--ink-ghost)', letterSpacing: '0.06em',
          textTransform: 'uppercase', padding: '4px 0', opacity: 0.7,
        }}
      >
        {open ? '▾ memória' : '▸ memória'}
        {entries.length > 0 && ` (${entries.length})`}
      </button>

      {open && (
        <div style={{ marginTop: 6 }}>
          {loading && (
            <p style={sMemory.empty}>carregando…</p>
          )}
          {err && (
            <p style={{ ...sMemory.empty, color: '#8B3A2A' }}>{err}</p>
          )}
          {!loading && !err && entries.length === 0 && (
            <p style={sMemory.empty}>nenhuma entrada de memória ainda.</p>
          )}
          {entries.map(e => (
            <div key={e.id} style={sMemory.row}>
              <div style={sMemory.rowTop}>
                <TypeBadge type={e.type} />
                <span style={sMemory.date}>
                  {e.created_at.slice(0, 16).replace('T', ' ')}
                </span>
                {e.feedback && (
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: 9,
                    color: e.feedback === 'confirmed' ? '#4A6741' : '#8B3A2A',
                    opacity: 0.7,
                  }}>
                    {e.feedback === 'confirmed' ? '✓' : '✗'}
                  </span>
                )}
                <button
                  onClick={() => handleDelete(e.id)}
                  disabled={deleting === e.id}
                  style={{
                    marginLeft: 'auto', background: 'none', border: 'none',
                    cursor: deleting === e.id ? 'default' : 'pointer',
                    fontFamily: 'var(--font-mono)', fontSize: 10,
                    color: 'var(--ink-ghost)', opacity: deleting === e.id ? 0.3 : 0.5,
                    padding: '0 2px',
                  }}
                  title="Apagar entrada"
                >
                  ✕
                </button>
              </div>
              <p style={sMemory.content}>{e.content}</p>
              {e.tags.length > 0 && (
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
                  {e.tags.map(t => (
                    <span key={t} style={sMemory.tag}>{t}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
          {!loading && entries.length > 0 && (
            <button
              onClick={load}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 10,
                color: 'var(--ink-ghost)', background: 'none',
                border: 'none', cursor: 'pointer', marginTop: 6,
                opacity: 0.6,
              }}
            >
              ↻ recarregar
            </button>
          )}
        </div>
      )}
    </div>
  )
}

const sMemory = {
  empty: {
    fontFamily: 'var(--font-mono)', fontSize: 11,
    color: 'var(--ink-ghost)', fontStyle: 'italic', margin: 0,
  } as const,
  row: {
    background: 'var(--paper)', borderRadius: 4, padding: '8px 10px',
    marginBottom: 6, border: '1px solid var(--rule)',
  } as const,
  rowTop: {
    display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4,
  } as const,
  date: {
    fontFamily: 'var(--font-mono)', fontSize: 9,
    color: 'var(--ink-ghost)',
  } as const,
  content: {
    fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink)',
    lineHeight: 1.55, margin: 0, whiteSpace: 'pre-wrap' as const,
  },
  tag: {
    fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-ghost)',
    background: 'var(--rule)', borderRadius: 3, padding: '1px 5px',
  } as const,
}

// ── Componente auxiliar: linha de status ─────────────────────

function StatusRow({
  label, value, dim = false,
}: { label: string; value: React.ReactNode; dim?: boolean }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '6px 0', borderBottom: '1px solid var(--rule)', opacity: dim ? 0.55 : 1,
    }}>
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)',
        letterSpacing: '0.04em', textTransform: 'uppercase',
      }}>
        {label}
      </span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink)' }}>
        {value}
      </span>
    </div>
  )
}

// ── Editor de personalidade ───────────────────────────────────

function PersonalityEditor({
  initialValue, onSave, onReset, resetLabel, resetMsg,
}: {
  initialValue: string
  onSave:       (v: string) => Promise<void>
  onReset:      () => Promise<void>
  resetLabel:   string
  resetMsg:     string
}) {
  const [value,  setValue]  = useState(initialValue)
  const [saving, setSaving] = useState(false)
  const [msg,    setMsg]    = useState<string | null>(null)
  const [open,   setOpen]   = useState(false)

  const prevInitial = useRef(initialValue)
  useEffect(() => {
    if (prevInitial.current !== initialValue && !open) {
      setValue(initialValue)
      prevInitial.current = initialValue
    }
  }, [initialValue, open])

  async function handleSave() {
    setSaving(true)
    setMsg(null)
    try {
      await onSave(value)
      setMsg('Salvo.')
    } catch {
      setMsg('Erro ao salvar.')
    } finally {
      setSaving(false)
      setTimeout(() => setMsg(null), 2500)
    }
  }

  async function handleReset() {
    setSaving(true)
    setMsg(null)
    try {
      await onReset()
      setMsg(resetMsg)
    } catch {
      setMsg('Erro ao reiniciar.')
    } finally {
      setSaving(false)
      setTimeout(() => setMsg(null), 3500)
    }
  }

  return (
    <div style={{ marginTop: 10 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)',
          letterSpacing: '0.06em', textTransform: 'uppercase', padding: '4px 0', opacity: 0.7,
        }}
      >
        {open ? '▾ personalidade' : '▸ personalidade'}
      </button>

      {open && (
        <div style={{ marginTop: 6 }}>
          <textarea
            value={value}
            onChange={e => setValue(e.target.value)}
            rows={4}
            style={{
              width: '100%', boxSizing: 'border-box',
              background: 'var(--paper-darker)', border: '1px solid var(--rule)',
              borderRadius: 4, color: 'var(--ink)', fontFamily: 'var(--font-mono)',
              fontSize: 11, lineHeight: 1.55, padding: '6px 8px',
              resize: 'vertical', outline: 'none',
            }}
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 6, alignItems: 'center' }}>
            <button onClick={handleSave} disabled={saving} style={{
              fontFamily: 'var(--font-mono)', fontSize: 11, padding: '4px 12px',
              background: 'var(--accent)', color: 'var(--paper-dark)', border: 'none',
              borderRadius: 4, cursor: saving ? 'default' : 'pointer', opacity: saving ? 0.6 : 1,
            }}>Salvar</button>
            <button onClick={handleReset} disabled={saving} style={{
              fontFamily: 'var(--font-mono)', fontSize: 11, padding: '4px 12px',
              background: 'transparent', color: 'var(--ink-ghost)',
              border: '1px solid var(--rule)', borderRadius: 4,
              cursor: saving ? 'default' : 'pointer', opacity: saving ? 0.6 : 1,
            }}>{resetLabel}</button>
            {msg && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', opacity: 0.8 }}>
                {msg}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Editor de seeds de interesse ─────────────────────────────

function SeedsEditor({ initialValue, onSave }: { initialValue: string; onSave: (v: string) => Promise<void> }) {
  const [value,  setValue]  = useState(initialValue)
  const [saving, setSaving] = useState(false)
  const [msg,    setMsg]    = useState<string | null>(null)
  const [open,   setOpen]   = useState(false)

  const prevInitial = useRef(initialValue)
  useEffect(() => {
    if (prevInitial.current !== initialValue && !open) {
      setValue(initialValue)
      prevInitial.current = initialValue
    }
  }, [initialValue, open])

  async function handleSave() {
    setSaving(true); setMsg(null)
    try { await onSave(value); setMsg('Salvo.') }
    catch { setMsg('Erro ao salvar.') }
    finally { setSaving(false); setTimeout(() => setMsg(null), 2500) }
  }

  return (
    <div style={{ marginTop: 10 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)',
          letterSpacing: '0.06em', textTransform: 'uppercase', padding: '4px 0', opacity: 0.7,
        }}
      >
        {open ? '▾ temas de interesse' : '▸ temas de interesse'}
      </button>
      {open && (
        <div style={{ marginTop: 6 }}>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', margin: '0 0 6px', opacity: 0.8 }}>
            Tópicos separados por vírgula. Pré-populam o perfil de interesse antes de haver histórico suficiente.
          </p>
          <textarea
            value={value}
            onChange={e => setValue(e.target.value)}
            rows={3}
            placeholder="machine learning, filosofia, rust, biologia..."
            style={{
              width: '100%', boxSizing: 'border-box',
              background: 'var(--paper-darker)', border: '1px solid var(--rule)',
              borderRadius: 4, color: 'var(--ink)', fontFamily: 'var(--font-mono)',
              fontSize: 11, lineHeight: 1.55, padding: '6px 8px',
              resize: 'vertical', outline: 'none',
            }}
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 6, alignItems: 'center' }}>
            <button onClick={handleSave} disabled={saving} style={{
              fontFamily: 'var(--font-mono)', fontSize: 11, padding: '4px 12px',
              background: 'var(--accent)', color: 'var(--paper-dark)', border: 'none',
              borderRadius: 4, cursor: saving ? 'default' : 'pointer', opacity: saving ? 0.6 : 1,
            }}>Salvar</button>
            {msg && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', opacity: 0.8 }}>{msg}</span>}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Card de app ───────────────────────────────────────────────

function AppBlock({ sigla, active, children }: { sigla: string; active: boolean; children: React.ReactNode }) {
  return (
    <div style={{
      background: 'var(--paper-dark)',
      border: `1px solid ${active ? 'var(--accent)' : 'var(--rule)'}`,
      borderRadius: 'var(--radius)', padding: '14px 18px',
      transition: 'border-color 300ms ease',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        marginBottom: 12, paddingBottom: 8, borderBottom: '1px solid var(--rule)',
      }}>
        <span style={{
          width: 8, height: 8, borderRadius: '50%',
          background: active ? 'var(--accent)' : 'var(--ink-ghost)',
          flexShrink: 0, opacity: active ? 1 : 0.4, transition: 'background 300ms',
        }} />
        <span style={{
          fontFamily: 'var(--font-display)', fontStyle: 'italic',
          fontSize: 15, color: 'var(--ink)', letterSpacing: '0.02em',
        }}>
          {sigla}
        </span>
      </div>
      {children}
    </div>
  )
}

// ── View principal ───────────────────────────────────────────

export function MonitoramentoView() {
  const [eco,           setEco]           = useState<EcosystemConfig | null>(null)
  const [lastPoll,      setLastPoll]      = useState<Date | null>(null)
  const [kosmosStats,   setKosmosStats]   = useState<{
    available: boolean; total?: number; pending?: number; analyzed?: number
  } | null>(null)

  async function poll() {
    const result = await cmd.readEcosystemConfig()
    if (result.ok) {
      setEco(result.data as EcosystemConfig)
      setLastPoll(new Date())
    }
    const ks = await cmd.kosmosGetAnalysisStats()
    if (ks.ok) setKosmosStats(ks.data)
  }

  useEffect(() => {
    poll()
    const id = setInterval(poll, 5000)
    return () => clearInterval(id)
  }, [])

  const akashaBg:  AkashaBg    | undefined = (eco?.akasha   as any)?.bg_processing
  const mnemosyne: MnemosyneBg | undefined = (eco?.mnemosyne as any)?.bg_processing
  const kosmosBg:  KosmosBg   | undefined  = (eco?.kosmos   as any)?.bg_processing

  const akashaActive    = akashaBg?.worker_active  ?? false
  const mnemosyneActive = mnemosyne?.indexing       ?? false
  const kosmosActive    = kosmosBg?.worker_active   ?? false

  const akashaBaseUrl        = eco?.akasha?.base_url          ?? 'http://localhost:7071'
  const akashaPersonality    = eco?.akasha?.personality_prompt    ?? ''
  const akashaSeeds          = (eco?.akasha?.interest_seeds ?? []).join(', ')
  const mnemosynePersonality = eco?.mnemosyne?.personality_prompt ?? ''

  async function saveAkashaPersonality(v: string) {
    await cmd.saveEcosystemConfig({ akasha: { personality_prompt: v } as any })
  }
  async function saveAkashaSeeds(v: string) {
    const seeds = v.split(',').map(s => s.trim()).filter(Boolean)
    await cmd.saveEcosystemConfig({ akasha: { interest_seeds: seeds } as any })
  }
  async function resetAkashaMemory() {
    const res = await fetch(`${akashaBaseUrl}/memory/clear`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
  }
  async function saveMnemosynePersonality(v: string) {
    await cmd.saveEcosystemConfig({ mnemosyne: { personality_prompt: v } as any })
  }
  async function resetMnemosyneMemory() {
    await cmd.saveEcosystemConfig({ mnemosyne: { cmd_reset_memory: true } as any })
  }

  const akashaLogs   = useAkashaLogs(akashaBaseUrl, akashaActive)
  const mnemosyneLogs = useMnemosyneLogs()

  // Porcentagem de artigos analisados
  const kosmosAnalyzedPct = kosmosStats?.available && kosmosStats.total
    ? Math.round(((kosmosStats.analyzed ?? 0) / kosmosStats.total) * 100)
    : null

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      padding: '24px 28px', gap: 20, overflowY: 'auto',
    }}>
      {/* Cabeçalho */}
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{
          fontFamily: 'var(--font-display)', fontStyle: 'italic',
          fontSize: 18, color: 'var(--ink)', letterSpacing: '0.02em',
        }}>
          ⬡ Monitoramento
        </span>
        {lastPoll && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', opacity: 0.6 }}>
            atualizado {lastPoll.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
        )}
      </div>

      {/* AKASHA */}
      <AppBlock sigla="AKASHA" active={akashaActive}>
        <StatusRow
          label="extração de conhecimento"
          value={akashaBg
            ? akashaBg.knowledge_extraction > 0 ? `${akashaBg.knowledge_extraction} na fila` : 'fila vazia'
            : '—'}
          dim={!akashaBg || akashaBg.knowledge_extraction === 0}
        />
        <StatusRow
          label="worker"
          value={akashaBg ? (akashaActive ? 'ativo' : 'parado') : '—'}
          dim={!akashaActive}
        />
        <PersonalityEditor
          initialValue={akashaPersonality}
          onSave={saveAkashaPersonality}
          onReset={resetAkashaMemory}
          resetLabel="Reiniciar memória"
          resetMsg="Memória apagada."
        />
        <SeedsEditor initialValue={akashaSeeds} onSave={saveAkashaSeeds} />
        <MemoryViewer app="akasha" />
        <LogStrip lines={akashaLogs} />
      </AppBlock>

      {/* Mnemosyne */}
      <AppBlock sigla="Mnemosyne" active={mnemosyneActive}>
        <StatusRow
          label="indexação"
          value={mnemosyne
            ? mnemosyne.indexing
              ? `em andamento — ${mnemosyne.files_pending} restante${mnemosyne.files_pending === 1 ? '' : 's'}`
              : 'ociosa'
            : '—'}
          dim={!mnemosyne?.indexing}
        />
        {mnemosyne?.indexing && mnemosyne.current_file && (
          <StatusRow
            label="arquivo atual"
            value={
              <span style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}
                title={mnemosyne.current_file}>
                {mnemosyne.current_file.split(/[\\/]/).pop()}
              </span>
            }
          />
        )}
        <PersonalityEditor
          initialValue={mnemosynePersonality}
          onSave={saveMnemosynePersonality}
          onReset={resetMnemosyneMemory}
          resetLabel="Reiniciar memória"
          resetMsg="Solicitado — processará em até 60s."
        />
        <MemoryViewer app="mnemosyne" />
        <LogStrip lines={mnemosyneLogs} />
      </AppBlock>

      {/* KOSMOS */}
      <AppBlock sigla="KOSMOS" active={kosmosActive}>
        <StatusRow
          label="worker de análise"
          value={kosmosBg ? (kosmosActive ? 'ativo' : 'parado') : '—'}
          dim={!kosmosActive}
        />
        <StatusRow
          label="fila de análise"
          value={kosmosBg
            ? kosmosBg.pending > 0 ? `${kosmosBg.pending} na fila` : 'vazia'
            : '—'}
          dim={!kosmosBg || kosmosBg.pending === 0}
        />
        {kosmosStats?.available && (
          <>
            <StatusRow
              label="artigos analisados"
              value={`${kosmosStats.analyzed?.toLocaleString('pt-BR') ?? 0} / ${kosmosStats.total?.toLocaleString('pt-BR') ?? 0}`}
              dim={false}
            />
            {kosmosAnalyzedPct !== null && (
              <div style={{ marginTop: 8 }}>
                <div style={{
                  height: 4, background: 'var(--rule)', borderRadius: 2, overflow: 'hidden',
                }}>
                  <div style={{
                    height: '100%', width: `${kosmosAnalyzedPct}%`,
                    background: kosmosAnalyzedPct === 100
                      ? '#4A6741'
                      : kosmosAnalyzedPct > 50 ? 'var(--accent)' : '#b8860b',
                    borderRadius: 2, transition: 'width 500ms ease',
                  }} />
                </div>
                <p style={{
                  fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-ghost)',
                  margin: '4px 0 0', textAlign: 'right',
                }}>
                  {kosmosAnalyzedPct}% analisado{kosmosStats.pending && kosmosStats.pending > 0
                    ? ` — ${kosmosStats.pending?.toLocaleString('pt-BR')} pendente${kosmosStats.pending === 1 ? '' : 's'}`
                    : ''}
                </p>
              </div>
            )}
          </>
        )}
      </AppBlock>

      {!eco && (
        <p style={{
          fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)',
          opacity: 0.5, textAlign: 'center', marginTop: 24,
        }}>
          Aguardando leitura do ecosystem.json…
        </p>
      )}
    </div>
  )
}
