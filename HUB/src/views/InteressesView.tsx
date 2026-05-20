/* ============================================================
   HUB — InteressesView
   Visualização e edição do perfil de interesses (interests.json).
   Mostra tópicos com peso, origem, pin e exclusão.
   Permite adicionar tópicos manuais e disparar re-derivação.
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { TopicEntry } from '../types'

const SOURCE_LABELS: Record<string, string> = {
  akasha_library:      'AKASHA',
  mnemosyne_reflections: 'Mnemosyne',
  kosmos_engagement:   'KOSMOS',
  manual:              'manual',
}

const SOURCE_COLORS: Record<string, string> = {
  akasha_library:        'var(--accent)',
  mnemosyne_reflections: '#a78bfa',
  kosmos_engagement:     'var(--accent-green)',
  manual:                'var(--ink-ghost)',
}

export function InteressesView() {
  const [topics,      setTopics]      = useState<TopicEntry[]>([])
  const [loading,     setLoading]     = useState(true)
  const [refreshing,  setRefreshing]  = useState(false)
  const [error,       setError]       = useState<string | null>(null)
  const [newName,     setNewName]     = useState('')
  const [newWeight,   setNewWeight]   = useState(0.5)
  const [adding,      setAdding]      = useState(false)
  const [showExcluded, setShowExcluded] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function load() {
    setLoading(true)
    setError(null)
    const res = await cmd.interestsGet()
    if (res.ok) {
      setTopics(res.data)
    } else {
      setError(res.error.message)
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  async function handlePin(topic: TopicEntry) {
    await cmd.interestsSetTopic(topic.name, null, !topic.pinned, null)
    setTopics(prev =>
      prev.map(t => t.name === topic.name ? { ...t, pinned: !t.pinned } : t),
    )
  }

  async function handleExclude(topic: TopicEntry) {
    await cmd.interestsSetTopic(topic.name, null, null, true)
    setTopics(prev =>
      prev.map(t => t.name === topic.name ? { ...t, excluded: true } : t),
    )
  }

  async function handleRestore(topic: TopicEntry) {
    await cmd.interestsSetTopic(topic.name, null, null, false)
    setTopics(prev =>
      prev.map(t => t.name === topic.name ? { ...t, excluded: false } : t),
    )
  }

  async function handleRefresh() {
    setRefreshing(true)
    await cmd.interestsRefresh()
    await load()
    setRefreshing(false)
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    const name = newName.trim().toLowerCase()
    if (!name) return
    setAdding(true)
    const res = await cmd.interestsAddManual(name, newWeight)
    if (res.ok) {
      setNewName('')
      setNewWeight(0.5)
      await load()
    }
    setAdding(false)
    inputRef.current?.focus()
  }

  const visible  = topics.filter(t => !t.excluded)
  const excluded = topics.filter(t =>  t.excluded)

  if (loading) {
    return (
      <div style={styles.center}>
        <span style={styles.muted}>Carregando perfil de interesses…</span>
      </div>
    )
  }

  if (error) {
    return (
      <div style={styles.center}>
        <span style={{ color: 'var(--accent-red)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
          {error}
        </span>
        <button className="btn btn-ghost btn-sm" onClick={load}>tentar novamente</button>
      </div>
    )
  }

  return (
    <div style={styles.wrapper}>
      {/* Cabeçalho */}
      <div style={styles.topBar}>
        <p style={styles.hint}>
          Tópicos derivados automaticamente por AKASHA, Mnemosyne e KOSMOS.
          Tópicos fixados (pinned) não são sobrescritos pela atualização automática.
        </p>
        <button
          className="btn btn-ghost btn-sm"
          onClick={handleRefresh}
          disabled={refreshing}
          title="Pinga AKASHA e Mnemosyne para re-exportar interesses, depois recarrega o arquivo"
        >
          {refreshing ? '…' : '↺ atualizar agora'}
        </button>
      </div>

      {/* Formulário — adicionar tópico manual */}
      <form onSubmit={handleAdd} style={styles.addForm}>
        <input
          ref={inputRef}
          type="text"
          value={newName}
          onChange={e => setNewName(e.target.value)}
          placeholder="novo tópico manual…"
          style={styles.addInput}
          disabled={adding}
        />
        <label style={styles.weightLabel}>
          <span style={styles.muted}>peso</span>
          <input
            type="range"
            min={0.1}
            max={1.0}
            step={0.05}
            value={newWeight}
            onChange={e => setNewWeight(parseFloat(e.target.value))}
            style={{ width: 80 }}
            disabled={adding}
          />
          <span style={styles.weightVal}>{newWeight.toFixed(2)}</span>
        </label>
        <button
          type="submit"
          className="btn btn-ghost btn-sm"
          disabled={adding || !newName.trim()}
        >
          {adding ? '…' : '+ adicionar'}
        </button>
      </form>

      {/* Lista de tópicos */}
      <div style={styles.listWrapper}>
        {visible.length === 0 && (
          <p style={{ ...styles.muted, padding: '20px 0', textAlign: 'center' }}>
            Nenhum interesse registrado ainda.
          </p>
        )}
        {visible.map(t => (
          <TopicRow
            key={t.name}
            topic={t}
            onPin={handlePin}
            onExclude={handleExclude}
          />
        ))}

        {/* Tópicos excluídos (colapsável) */}
        {excluded.length > 0 && (
          <div style={styles.excludedSection}>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setShowExcluded(v => !v)}
              style={{ fontSize: 11, opacity: 0.6 }}
            >
              {showExcluded ? '▲' : '▼'} {excluded.length} excluído{excluded.length !== 1 ? 's' : ''}
            </button>
            {showExcluded && excluded.map(t => (
              <TopicRow
                key={t.name}
                topic={t}
                onPin={handlePin}
                onRestore={handleRestore}
                isExcluded
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── TopicRow ────────────────────────────────────────────────

interface TopicRowProps {
  topic:      TopicEntry
  onPin:      (t: TopicEntry) => void
  onExclude?: (t: TopicEntry) => void
  onRestore?: (t: TopicEntry) => void
  isExcluded?: boolean
}

function TopicRow({ topic, onPin, onExclude, onRestore, isExcluded }: TopicRowProps) {
  return (
    <div style={{ ...styles.row, opacity: isExcluded ? 0.45 : 1 }}>
      {/* Barra de peso */}
      <div style={styles.weightBar}>
        <div
          style={{
            ...styles.weightFill,
            width: `${Math.round(topic.weight * 100)}%`,
          }}
        />
      </div>

      {/* Nome */}
      <span style={styles.topicName}>{topic.name}</span>

      {/* Peso numérico */}
      <span style={styles.weightNum}>{topic.weight.toFixed(2)}</span>

      {/* Badges de origem */}
      <div style={styles.sourceBadges}>
        {topic.sources.map(s => (
          <span
            key={s}
            style={{
              ...styles.badge,
              color:      SOURCE_COLORS[s] ?? 'var(--ink-ghost)',
              background: `color-mix(in srgb, ${SOURCE_COLORS[s] ?? 'var(--ink-ghost)'} 12%, transparent)`,
            }}
          >
            {SOURCE_LABELS[s] ?? s}
          </span>
        ))}
      </div>

      {/* Ações */}
      <div style={styles.actions}>
        {isExcluded ? (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => onRestore?.(topic)}
            title="Restaurar tópico"
            style={styles.actionBtn}
          >
            ↩
          </button>
        ) : (
          <>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => onPin(topic)}
              title={topic.pinned ? 'Desafixar (permite sobrescrita)' : 'Fixar (impede sobrescrita automática)'}
              style={{
                ...styles.actionBtn,
                color: topic.pinned ? 'var(--accent)' : 'var(--ink-ghost)',
              }}
            >
              {topic.pinned ? '⊛' : '○'}
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => onExclude?.(topic)}
              title="Excluir tópico"
              style={{ ...styles.actionBtn, color: 'var(--ink-ghost)' }}
            >
              ×
            </button>
          </>
        )}
      </div>
    </div>
  )
}

// ── Estilos ─────────────────────────────────────────────────

const styles = {
  wrapper: {
    display:       'flex',
    flexDirection: 'column' as const,
    height:        '100%',
    overflow:      'hidden',
  },
  topBar: {
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'space-between',
    padding:        '12px 20px',
    borderBottom:   '1px solid var(--rule)',
    gap:            12,
    flexShrink:     0,
  },
  hint: {
    fontFamily: 'var(--font-body)',
    fontSize:   12,
    color:      'var(--ink-ghost)',
    margin:     0,
  },
  addForm: {
    display:      'flex',
    alignItems:   'center',
    gap:          10,
    padding:      '10px 20px',
    borderBottom: '1px solid var(--rule)',
    flexShrink:   0,
  },
  addInput: {
    flex:        1,
    background:  'var(--paper-dark)',
    border:      '1px solid var(--rule)',
    borderRadius: 'var(--radius)',
    color:       'var(--ink)',
    fontFamily:  'var(--font-body)',
    fontSize:    13,
    padding:     '4px 10px',
    outline:     'none',
  },
  weightLabel: {
    display:    'flex',
    alignItems: 'center',
    gap:        6,
    flexShrink: 0,
  },
  weightVal: {
    fontFamily: 'var(--font-mono)',
    fontSize:   11,
    color:      'var(--ink-ghost)',
    minWidth:   32,
  },
  listWrapper: {
    flex:    1,
    overflow: 'auto',
    padding: '8px 20px 20px',
  },
  row: {
    display:    'flex',
    alignItems: 'center',
    gap:        10,
    padding:    '7px 0',
    borderBottom: '1px solid color-mix(in srgb, var(--rule) 40%, transparent)',
  },
  weightBar: {
    width:        80,
    height:       4,
    borderRadius: 2,
    background:   'var(--rule)',
    flexShrink:   0,
    overflow:     'hidden',
  },
  weightFill: {
    height:       '100%',
    borderRadius: 2,
    background:   'var(--accent)',
    transition:   'width 300ms ease',
  },
  topicName: {
    flex:       1,
    fontFamily: 'var(--font-mono)',
    fontSize:   12,
    color:      'var(--ink)',
  },
  weightNum: {
    fontFamily: 'var(--font-mono)',
    fontSize:   11,
    color:      'var(--ink-ghost)',
    flexShrink: 0,
    minWidth:   32,
    textAlign:  'right' as const,
  },
  sourceBadges: {
    display:    'flex',
    gap:        4,
    flexShrink: 0,
  },
  badge: {
    display:       'inline-block',
    padding:       '1px 6px',
    borderRadius:  4,
    fontSize:      10,
    fontFamily:    'var(--font-mono)',
    letterSpacing: '0.04em',
    whiteSpace:    'nowrap' as const,
  },
  actions: {
    display:    'flex',
    gap:        2,
    flexShrink: 0,
  },
  actionBtn: {
    padding:    '2px 6px',
    fontSize:   13,
    lineHeight: 1,
  },
  excludedSection: {
    marginTop: 16,
    display:   'flex',
    flexDirection: 'column' as const,
    gap:       4,
  },
  center: {
    display:        'flex',
    flexDirection:  'column' as const,
    alignItems:     'center',
    justifyContent: 'center',
    height:         '100%',
    gap:            8,
  },
  muted: {
    fontFamily: 'var(--font-body)',
    fontSize:   12,
    color:      'var(--ink-ghost)',
    margin:     0,
  },
} as const
