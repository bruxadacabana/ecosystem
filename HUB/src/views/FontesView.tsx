/* ============================================================
   HUB — FontesView
   Gestão unificada de fontes (domínios) do ecossistema.
   Lista todos os domínios conhecidos pelo AKASHA e KOSMOS,
   permite ativar/desativar os flags "Biblioteca" e "Feed".
   Estado persiste em ecosystem.json["sources"].
   ============================================================ */

import { useEffect, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { DomainEntry } from '../types'

export function FontesView() {
  const [domains,  setDomains]  = useState<DomainEntry[]>([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState<string | null>(null)
  const [warning,  setWarning]  = useState<string | null>(null)
  const [toggling, setToggling] = useState<string | null>(null)  // "domain:flag" em progresso

  async function load() {
    setLoading(true)
    setError(null)
    setWarning(null)
    const res = await cmd.sourcesGetDomains()
    if (res.ok) {
      setDomains(res.data.domains)
      if (res.data.akasha_error) setWarning(res.data.akasha_error)
    } else {
      setError(res.error.message)
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  async function handleToggle(domain: string, flag: 'library' | 'feed', current: boolean) {
    const key = `${domain}:${flag}`
    setToggling(key)
    setError(null)
    const res = await cmd.sourcesSetFlag(domain, flag, !current)
    if (res.ok) {
      // Ambos os toggles fazem ação real (feed → KOSMOS; library → crawl_sites da
      // AKASHA) — recarrega para refletir o estado real (feed descoberto/removido,
      // library, akasha_url).
      await load()
    } else {
      // Ex.: nenhum feed RSS encontrado no domínio.
      setError(res.error.message)
    }
    setToggling(null)
  }

  if (loading) {
    return (
      <div style={styles.center}>
        <span style={styles.muted}>Carregando fontes…</span>
      </div>
    )
  }

  if (error) {
    return (
      <div style={styles.center}>
        <span style={{ color: 'var(--accent-red)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
          {error}
        </span>
      </div>
    )
  }

  if (domains.length === 0) {
    return (
      <div style={styles.center}>
        <p style={styles.muted}>Nenhuma fonte encontrada.</p>
        <p style={{ ...styles.muted, fontSize: 12 }}>
          Adicione sites à Biblioteca no AKASHA ou feeds no KOSMOS.
        </p>
      </div>
    )
  }

  return (
    <div style={styles.wrapper}>
      <div style={styles.header}>
        <p style={styles.hint}>
          Ativa ou desativa cada domínio para indexação profunda (Biblioteca) e monitoramento de feed.
          O estado é lido pelo AKASHA e KOSMOS em runtime.
        </p>
        <button className="btn btn-ghost btn-sm" onClick={load}>
          ↺ atualizar
        </button>
      </div>

      {warning && (
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, color: '#b8860b',
          background: 'rgba(184, 134, 11, 0.08)',
          borderBottom: '1px solid rgba(184, 134, 11, 0.25)',
          padding: '6px 20px', flexShrink: 0,
        }}>
          ⚠ {warning}
        </div>
      )}
      <div style={styles.tableWrapper}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.thDomain}>Domínio</th>
              <th style={styles.thSources}>Presente em</th>
              <th style={styles.thFlag}>Biblioteca</th>
              <th style={styles.thFlag}>Feed</th>
            </tr>
          </thead>
          <tbody>
            {domains.map(d => {
              const libKey  = `${d.domain}:library`
              const feedKey = `${d.domain}:feed`
              return (
                <tr key={d.domain} style={styles.row}>
                  <td style={styles.tdDomain}>
                    <span style={styles.domainName}>{d.domain}</span>
                    {d.label && d.label !== d.domain && (
                      <span style={styles.domainLabel}>{d.label}</span>
                    )}
                  </td>
                  <td style={styles.tdSources}>
                    {d.akasha_url && <span style={styles.badge}>AKASHA</span>}
                    {d.kosmos_feeds.length > 0 && (
                      <span style={{ ...styles.badge, ...styles.badgeKosmos }}>
                        KOSMOS{d.kosmos_feeds.length > 1 ? ` ×${d.kosmos_feeds.length}` : ''}
                      </span>
                    )}
                  </td>
                  <td style={styles.tdFlag}>
                    <Toggle
                      checked={d.library}
                      disabled={toggling === libKey}
                      onChange={() => handleToggle(d.domain, 'library', d.library)}
                      label="Biblioteca"
                    />
                  </td>
                  <td style={styles.tdFlag}>
                    <Toggle
                      checked={d.feed}
                      disabled={toggling === feedKey}
                      onChange={() => handleToggle(d.domain, 'feed', d.feed)}
                      label="Feed"
                    />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Toggle interno ──────────────────────────────────────────

interface ToggleProps {
  checked:  boolean
  disabled: boolean
  onChange: () => void
  label:    string
}

function Toggle({ checked, disabled, onChange, label }: ToggleProps) {
  return (
    <button
      onClick={onChange}
      disabled={disabled}
      title={label}
      style={{
        background:    checked ? 'var(--accent)' : 'var(--rule)',
        border:        'none',
        borderRadius:  12,
        width:         36,
        height:        20,
        cursor:        disabled ? 'wait' : 'pointer',
        position:      'relative',
        transition:    'background 180ms ease',
        opacity:       disabled ? 0.5 : 1,
        flexShrink:    0,
      }}
    >
      <span
        style={{
          position:   'absolute',
          top:        3,
          left:       checked ? 18 : 3,
          width:      14,
          height:     14,
          borderRadius: '50%',
          background: 'white',
          transition: 'left 180ms ease',
        }}
      />
    </button>
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
  header: {
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
  tableWrapper: {
    flex:     1,
    overflow: 'auto',
    padding:  '0 20px 20px',
  },
  table: {
    width:           '100%',
    borderCollapse:  'collapse' as const,
    fontFamily:      'var(--font-body)',
    fontSize:        13,
    marginTop:       8,
  },
  thDomain: {
    textAlign:     'left' as const,
    padding:       '8px 12px 8px 0',
    borderBottom:  '1px solid var(--rule)',
    color:         'var(--ink-ghost)',
    fontWeight:    600,
    fontFamily:    'var(--font-mono)',
    fontSize:      10,
    letterSpacing: '0.06em',
    textTransform: 'uppercase' as const,
  },
  thSources: {
    textAlign:     'left' as const,
    padding:       '8px 12px',
    borderBottom:  '1px solid var(--rule)',
    color:         'var(--ink-ghost)',
    fontWeight:    600,
    fontFamily:    'var(--font-mono)',
    fontSize:      10,
    letterSpacing: '0.06em',
    textTransform: 'uppercase' as const,
    whiteSpace:    'nowrap' as const,
  },
  thFlag: {
    textAlign:     'center' as const,
    padding:       '8px 12px',
    borderBottom:  '1px solid var(--rule)',
    color:         'var(--ink-ghost)',
    fontWeight:    600,
    fontFamily:    'var(--font-mono)',
    fontSize:      10,
    letterSpacing: '0.06em',
    textTransform: 'uppercase' as const,
    whiteSpace:    'nowrap' as const,
  },
  row: {
    borderBottom: '1px solid color-mix(in srgb, var(--rule) 50%, transparent)',
  },
  tdDomain: {
    padding:       '10px 12px 10px 0',
    verticalAlign: 'middle' as const,
  },
  tdSources: {
    padding:       '10px 12px',
    verticalAlign: 'middle' as const,
  },
  tdFlag: {
    textAlign:     'center' as const,
    padding:       '10px 12px',
    verticalAlign: 'middle' as const,
  },
  domainName: {
    display:     'block',
    color:       'var(--ink)',
    fontFamily:  'var(--font-mono)',
    fontSize:    12,
  },
  domainLabel: {
    display:    'block',
    color:      'var(--ink-ghost)',
    fontSize:   11,
    marginTop:  2,
  },
  badge: {
    display:       'inline-block',
    padding:       '1px 6px',
    borderRadius:  4,
    fontSize:      10,
    fontFamily:    'var(--font-mono)',
    background:    'color-mix(in srgb, var(--accent) 15%, transparent)',
    color:         'var(--accent)',
    marginRight:   4,
    letterSpacing: '0.04em',
  },
  badgeKosmos: {
    background: 'color-mix(in srgb, var(--accent-green) 15%, transparent)',
    color:      'var(--accent-green)',
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
    fontSize:   13,
    color:      'var(--ink-ghost)',
    margin:     0,
  },
} as const
