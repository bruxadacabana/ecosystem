/* ============================================================
   HUB — ComunicacoesView
   Timeline de comunicações IA → usuária (popups e overlays).
   Mostra quem enviou, o conteúdo, importância e estado de feedback.
   ============================================================ */

import { useEffect, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { CommEntry } from '../types'

const APP_LABELS: Record<string, string> = {
  akasha:   'AKASHA',
  mnemosyne: 'Mnemosyne',
}

const APP_COLORS: Record<string, string> = {
  akasha:    'var(--accent)',
  mnemosyne: '#a78bfa',
}

const FEEDBACK_LABEL: Record<string, string> = {
  confirmed: '✓',
  dismissed: '✗',
}

const FEEDBACK_COLOR: Record<string, string> = {
  confirmed: 'var(--accent-green)',
  dismissed: 'var(--ink-ghost)',
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('pt-BR', {
      day: '2-digit', month: '2-digit', year: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export function ComunicacoesView() {
  const [entries,  setEntries]  = useState<CommEntry[]>([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState<string | null>(null)
  const [filter,   setFilter]   = useState<'all' | 'confirmed' | 'dismissed' | 'pending'>('all')
  const [appFilter, setAppFilter] = useState<'all' | 'akasha' | 'mnemosyne'>('all')

  useEffect(() => {
    setLoading(true)
    cmd.commHistoryGet(200).then(res => {
      if (res.ok) setEntries(res.data)
      else setError(res.error ?? 'Erro ao carregar comunicações.')
      setLoading(false)
    })
  }, [])

  const filtered = entries.filter(e => {
    if (appFilter !== 'all' && e.source_app !== appFilter) return false
    if (filter === 'confirmed')  return e.feedback === 'confirmed'
    if (filter === 'dismissed')  return e.feedback === 'dismissed'
    if (filter === 'pending')    return e.feedback === null
    return true
  })

  const pendingCount = entries.filter(e => e.feedback === null).length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

      {/* Cabeçalho com filtros */}
      <div style={{
        padding: '14px 20px 12px',
        borderBottom: '1px solid var(--rule)',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        flexWrap: 'wrap',
        flexShrink: 0,
      }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)', marginRight: 4 }}>
          {entries.length} entradas · {pendingCount} sem resposta
        </span>

        {/* Filtro por app */}
        {(['all', 'akasha', 'mnemosyne'] as const).map(a => (
          <button
            key={a}
            onClick={() => setAppFilter(a)}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              padding: '3px 8px',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--rule)',
              background: appFilter === a ? 'var(--rule)' : 'transparent',
              color: appFilter === a
                ? (a === 'all' ? 'var(--ink)' : APP_COLORS[a] ?? 'var(--ink)')
                : 'var(--ink-ghost)',
              cursor: 'pointer',
            }}
          >
            {a === 'all' ? 'todas' : APP_LABELS[a] ?? a}
          </button>
        ))}

        <div style={{ width: 1, height: 16, background: 'var(--rule)' }} />

        {/* Filtro por feedback */}
        {(['all', 'pending', 'confirmed', 'dismissed'] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              padding: '3px 8px',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--rule)',
              background: filter === f ? 'var(--rule)' : 'transparent',
              color: filter === f ? 'var(--ink)' : 'var(--ink-ghost)',
              cursor: 'pointer',
            }}
          >
            {f === 'all' ? 'todos' : f === 'pending' ? 'sem resposta' : f === 'confirmed' ? '✓ confirmados' : '✗ dispensados'}
          </button>
        ))}
      </div>

      {/* Lista */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 20px' }}>
        {loading && (
          <p style={{ color: 'var(--ink-ghost)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
            carregando…
          </p>
        )}
        {error && (
          <p style={{ color: 'var(--accent-red)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
            {error}
          </p>
        )}
        {!loading && !error && filtered.length === 0 && (
          <p style={{ color: 'var(--ink-ghost)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
            nenhuma comunicação encontrada.
          </p>
        )}

        {filtered.map(entry => (
          <div
            key={entry.id}
            style={{
              display: 'flex',
              gap: 14,
              padding: '12px 0',
              borderBottom: '1px solid var(--rule)',
            }}
          >
            {/* Indicador lateral */}
            <div style={{
              width: 3,
              borderRadius: 2,
              flexShrink: 0,
              background: APP_COLORS[entry.source_app] ?? 'var(--rule)',
              alignSelf: 'stretch',
            }} />

            <div style={{ flex: 1, minWidth: 0 }}>
              {/* Linha de metadados */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginBottom: 6,
                flexWrap: 'wrap',
              }}>
                <span style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10,
                  color: APP_COLORS[entry.source_app] ?? 'var(--ink-ghost)',
                  letterSpacing: '0.05em',
                }}>
                  {APP_LABELS[entry.source_app] ?? entry.source_app}
                </span>

                {entry.importance !== null && (
                  <span style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                    color: entry.importance >= 7 ? 'var(--accent)' : 'var(--ink-ghost)',
                    border: '1px solid var(--rule)',
                    borderRadius: 3,
                    padding: '1px 5px',
                  }}>
                    imp {entry.importance}
                  </span>
                )}

                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)' }}>
                  {formatDate(entry.sent_at)}
                </span>

                {entry.feedback && (
                  <span style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: FEEDBACK_COLOR[entry.feedback] ?? 'var(--ink-ghost)',
                    marginLeft: 'auto',
                  }}>
                    {FEEDBACK_LABEL[entry.feedback] ?? entry.feedback}
                  </span>
                )}
              </div>

              {/* Conteúdo */}
              <p style={{
                margin: 0,
                fontFamily: 'var(--font-body)',
                fontSize: 13,
                color: 'var(--ink)',
                lineHeight: 1.5,
                wordBreak: 'break-word',
              }}>
                {entry.content}
              </p>

              {/* Tags */}
              {entry.tags.length > 0 && (
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
                  {entry.tags.map((t, i) => (
                    <span
                      key={i}
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 9,
                        color: 'var(--ink-ghost)',
                        border: '1px solid var(--rule)',
                        borderRadius: 3,
                        padding: '1px 5px',
                      }}
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}

              {/* Motivo do dismiss */}
              {entry.feedback_reason && (
                <p style={{
                  margin: '6px 0 0',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  color: 'var(--ink-ghost)',
                  fontStyle: 'italic',
                }}>
                  motivo: {entry.feedback_reason}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
