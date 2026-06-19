/* ============================================================
   HUB — Componente compartilhado: viewer da memória pessoal das IAs.
   Lê a personal_memory de uma IA (akasha | mnemosyne) via memory_get_entries,
   agrupa por categoria (reflexões, insights, visitas…) em seções dobráveis.

   Dois usos:
   - <MemoryViewer app> — collapsible "▸ memória", COM apagar (MonitoramentoView).
   - <MemoryList app readOnly> — expandido, eager-load, só-leitura (aba Reflexões).
   ============================================================ */

import { useEffect, useState } from 'react'

import * as cmd from '../lib/tauri'
import type { MemoryEntry } from '../types'

const TYPE_COLORS: Record<string, string> = {
  observation: '#4A6741',
  connection:  '#2C5F8A',
  surprise:    '#8B3A2A',
  reflection:  '#6B4C8A',
}

const CATEGORY_LABEL: Record<string, string> = {
  friendship:  'visitas',
  about_user:  'sobre mim',
  interests:   'interesses',
  reflections: 'reflexões',
  world:       'mundo',
}

const CATEGORY_ORDER = ['friendship', 'about_user', 'interests', 'reflections', 'world']

export const sMemory = {
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

function groupByCategory(entries: MemoryEntry[]): [string, MemoryEntry[]][] {
  const map = new Map<string, MemoryEntry[]>()
  for (const e of entries) {
    const cat = e.category ?? 'reflections'
    if (!map.has(cat)) map.set(cat, [])
    map.get(cat)!.push(e)
  }
  const ordered: [string, MemoryEntry[]][] = []
  for (const cat of CATEGORY_ORDER) {
    if (map.has(cat)) ordered.push([cat, map.get(cat)!])
  }
  for (const [cat, list] of map) {
    if (!CATEGORY_ORDER.includes(cat)) ordered.push([cat, list])
  }
  return ordered
}

function MemoryCategorySection({
  category, entries, onDelete, deleting, readOnly, defaultOpen = false,
}: {
  category: string
  entries:  MemoryEntry[]
  onDelete: (id: number) => void
  deleting: number | null
  readOnly: boolean
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const label = CATEGORY_LABEL[category] ?? category

  return (
    <div style={{ marginBottom: 2 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          fontFamily: 'var(--font-mono)', fontSize: 10,
          color: 'var(--ink-ghost)', letterSpacing: '0.06em',
          textTransform: 'uppercase', padding: '3px 0',
          display: 'flex', alignItems: 'center', gap: 6, width: '100%',
        }}
      >
        <span style={{ opacity: 0.6 }}>{open ? '▾' : '▸'}</span>
        <span style={{ opacity: 0.8 }}>{label}</span>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 9,
          color: 'var(--ink-ghost)', opacity: 0.5,
        }}>
          {entries.length}
        </span>
      </button>

      {open && (
        <div style={{ marginTop: 4, marginLeft: 10, maxHeight: 260, overflowY: 'auto', paddingRight: 2 }}>
          {entries.map(e => (
            <div key={e.id} style={sMemory.row}>
              <div style={sMemory.rowTop}>
                <TypeBadge type={e.type} />
                <span style={sMemory.date}>
                  {new Date(e.created_at.replace(' ', 'T') + 'Z').toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}
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
                {!readOnly && (
                  <button
                    onClick={() => onDelete(e.id)}
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
                )}
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
        </div>
      )}
    </div>
  )
}

/** Lista da memória de uma IA: carrega ao montar, agrupa por categoria.
 *  `readOnly` esconde o apagar (usado na aba Reflexões, só-leitura). */
export function MemoryList({ app, readOnly = false }: { app: 'akasha' | 'mnemosyne'; readOnly?: boolean }) {
  const [entries,  setEntries]  = useState<MemoryEntry[]>([])
  const [loading,  setLoading]  = useState(false)
  const [err,      setErr]      = useState<string | null>(null)
  const [deleting, setDeleting] = useState<number | null>(null)

  async function load() {
    setLoading(true)
    setErr(null)
    const res = await cmd.memoryGetEntries(app, 50)
    setLoading(false)
    if (res.ok) setEntries(res.data)
    else setErr(res.error.message)
  }

  useEffect(() => { load() }, [app])  // eslint-disable-line react-hooks/exhaustive-deps

  async function handleDelete(id: number) {
    setDeleting(id)
    const res = await cmd.memoryDeleteEntry(app, id)
    setDeleting(null)
    if (res.ok) setEntries(prev => prev.filter(e => e.id !== id))
  }

  const grouped = groupByCategory(entries)

  return (
    <div>
      {loading && <p style={sMemory.empty}>carregando…</p>}
      {err     && <p style={{ ...sMemory.empty, color: '#8B3A2A' }}>{err}</p>}
      {!loading && !err && entries.length === 0 && (
        <p style={sMemory.empty}>nenhuma entrada de memória ainda.</p>
      )}
      {grouped.map(([cat, list], i) => (
        <MemoryCategorySection
          key={cat}
          category={cat}
          entries={list}
          onDelete={handleDelete}
          deleting={deleting}
          readOnly={readOnly}
          defaultOpen={readOnly && i === 0}
        />
      ))}
      {!loading && entries.length > 0 && (
        <button
          onClick={load}
          style={{
            fontFamily: 'var(--font-mono)', fontSize: 10,
            color: 'var(--ink-ghost)', background: 'none',
            border: 'none', cursor: 'pointer', marginTop: 6, opacity: 0.6,
          }}
        >
          ↻ recarregar
        </button>
      )}
    </div>
  )
}

/** Viewer collapsible "▸ memória" com apagar (usado no MonitoramentoView). */
export function MemoryViewer({ app }: { app: 'akasha' | 'mnemosyne' }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ marginTop: 10 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          fontFamily: 'var(--font-mono)', fontSize: 10,
          color: 'var(--ink-ghost)', letterSpacing: '0.06em',
          textTransform: 'uppercase', padding: '4px 0', opacity: 0.7,
        }}
      >
        {open ? '▾ memória' : '▸ memória'}
      </button>
      {open && <div style={{ marginTop: 6 }}><MemoryList app={app} /></div>}
    </div>
  )
}
