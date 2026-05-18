/* ============================================================
   HUB — GitView
   Repositório git offline da sync_root do ecossistema.
   - Status em tempo real (polling 5 s)
   - Commit com mensagem opcional (auto-msg se vazio)
   - Log dos últimos 20 commits
   - Diff inline expansível por arquivo
   - Indicador de commits externos (Syncthing)
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { GitFileStatus, GitLogEntry, GitIncomingInfo } from '../types'

// ----------------------------------------------------------
//  Helpers de status
// ----------------------------------------------------------

interface StatusMeta { icon: string; color: string; label: string }

function statusMeta(code: string): StatusMeta {
  const x = code[0] ?? ' '
  const y = code[1] ?? ' '

  if (code === '??') return { icon: '+', color: '#5C8A6B',  label: 'não rastreado' }
  if (code === '!!') return { icon: '·', color: 'var(--ink-ghost)', label: 'ignorado' }

  if (x === 'A')     return { icon: '+', color: '#4A6741',  label: 'adicionado'  }
  if (x === 'D')     return { icon: '−', color: '#8B3A2A',  label: 'deletado'    }
  if (x === 'R')     return { icon: '→', color: '#2C5F8A',  label: 'renomeado'   }
  if (x === 'M')     return { icon: '●', color: 'var(--accent)', label: 'modificado (stage)' }
  if (y === 'M')     return { icon: '●', color: '#b8860b88', label: 'modificado'  }
  if (y === 'D')     return { icon: '−', color: '#8B3A2A88', label: 'deletado (worktree)' }

  return { icon: '·', color: 'var(--ink-ghost)', label: code.trim() || 'alterado' }
}

// ----------------------------------------------------------
//  Componente principal
// ----------------------------------------------------------

export function GitView() {
  const [status,       setStatus]       = useState<GitFileStatus[]>([])
  const [log,          setLog]          = useState<GitLogEntry[]>([])
  const [commitMsg,    setCommitMsg]    = useState('')
  const [committing,   setCommitting]   = useState(false)
  const [commitErr,    setCommitErr]    = useState('')
  const [commitOk,     setCommitOk]     = useState('')
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [diff,         setDiff]         = useState('')
  const [loadingDiff,  setLoadingDiff]  = useState(false)
  const [polling,      setPolling]      = useState(false)
  // Item 7 — commits recebidos via Syncthing desde a última sessão
  const [incoming,     setIncoming]     = useState<GitIncomingInfo | null>(null)
  const [showIncoming, setShowIncoming] = useState(true)

  // Detecção de commits externos nesta sessão: hash HEAD no mount
  const startupHashRef  = useRef<string>('')
  const ownCommitsRef   = useRef<Set<string>>(new Set())
  const [externalCount, setExternalCount] = useState(0)

  // ----------------------------------------------------------
  //  Polling de status + log
  // ----------------------------------------------------------

  async function refresh(silent = false) {
    if (!silent) setPolling(true)

    const [sRes, lRes] = await Promise.all([
      cmd.gitStatus(),
      cmd.gitLog(20),
    ])

    if (sRes.ok)  setStatus(sRes.data)
    if (lRes.ok) {
      const entries = lRes.data
      setLog(entries)

      // Inicializa o hash de referência na primeira carga
      if (startupHashRef.current === '' && entries.length > 0) {
        startupHashRef.current = entries[0].hash
      }

      // Detecta commits externos (não feitos por nós nesta sessão)
      if (startupHashRef.current && entries.length > 0) {
        const external = entries.filter(
          e => e.hash !== startupHashRef.current &&
               !ownCommitsRef.current.has(e.hash)
        )
        // Conta apenas commits mais novos que o startup (aparecem antes no log)
        const startIdx = entries.findIndex(e => e.hash === startupHashRef.current)
        const newExternal = startIdx > 0
          ? entries.slice(0, startIdx).filter(e => !ownCommitsRef.current.has(e.hash))
          : []
        setExternalCount(newExternal.length)
        void external // satisfaz lint
      }
    }

    if (!silent) setPolling(false)
  }

  useEffect(() => {
    refresh()
    const id = setInterval(() => refresh(true), 5_000)
    return () => clearInterval(id)
  }, [])

  // Item 7 — verifica commits recebidos via Syncthing (cross-session)
  useEffect(() => {
    cmd.gitCheckIncoming().then(res => {
      if (res.ok && res.data.count > 0) setIncoming(res.data)
    })
  }, [])

  // ----------------------------------------------------------
  //  Diff ao selecionar arquivo
  // ----------------------------------------------------------

  async function handleSelectFile(path: string) {
    if (selectedFile === path) {
      setSelectedFile(null)
      setDiff('')
      return
    }
    setSelectedFile(path)
    setLoadingDiff(true)
    const res = await cmd.gitDiff(path)
    setLoadingDiff(false)
    if (res.ok) {
      setDiff(res.data.trim() || '(sem diff — arquivo pode ser idêntico ao HEAD)')
    } else {
      setDiff(`Erro: ${res.error.message}`)
    }
  }

  // ----------------------------------------------------------
  //  Commit
  // ----------------------------------------------------------

  async function handleCommit() {
    setCommitting(true)
    setCommitErr('')
    setCommitOk('')
    const res = await cmd.gitCommit(commitMsg.trim() || undefined)
    setCommitting(false)
    if (!res.ok) {
      setCommitErr(res.error.message)
    } else {
      const hash = res.data
      ownCommitsRef.current.add(hash)
      setCommitOk(`Commit ${hash} criado.`)
      setCommitMsg('')
      refresh(true)
    }
  }

  // ----------------------------------------------------------
  //  Render auxiliares
  // ----------------------------------------------------------

  function renderStatusList() {
    if (status.length === 0) {
      return (
        <p style={styles.empty}>Nada para commitar — working tree limpa.</p>
      )
    }
    return status.map(f => {
      const meta = statusMeta(f.status)
      const active = selectedFile === f.path
      return (
        <div
          key={f.path}
          onClick={() => handleSelectFile(f.path)}
          style={{
            ...styles.fileRow,
            background: active ? 'var(--rule)' : 'transparent',
          }}
        >
          <span style={{ color: meta.color, fontWeight: 700, width: 14, flexShrink: 0, textAlign: 'center' }}>
            {meta.icon}
          </span>
          <span
            style={{
              flex: 1,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              color: 'var(--ink)',
            }}
            title={`${meta.label} — ${f.path}`}
          >
            {f.path}
          </span>
          <span style={{ color: meta.color, fontSize: 9, letterSpacing: '0.08em', flexShrink: 0 }}>
            {f.status.trim() || '??'}
          </span>
        </div>
      )
    })
  }

  function renderDiff() {
    if (!selectedFile) return null
    return (
      <div style={styles.diffPanel}>
        <div style={styles.diffHeader}>
          <span style={styles.diffTitle}>{selectedFile}</span>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => { setSelectedFile(null); setDiff('') }}
            style={{ fontSize: 10, padding: '2px 6px' }}
          >
            ✕
          </button>
        </div>
        {loadingDiff ? (
          <p style={styles.empty}>Carregando diff…</p>
        ) : (
          <pre style={styles.diffBody}>{diff}</pre>
        )}
      </div>
    )
  }

  function renderLog() {
    if (log.length === 0) {
      return <p style={styles.empty}>Nenhum commit ainda.</p>
    }
    return log.map((entry, i) => {
      const isOwn      = ownCommitsRef.current.has(entry.hash)
      const isStartup  = entry.hash === startupHashRef.current
      const isExternal = !isOwn && !isStartup && i < log.findIndex(e => e.hash === startupHashRef.current)

      return (
        <div key={entry.hash} style={styles.logRow}>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: isExternal ? '#2C5F8A' : isOwn ? '#4A6741' : 'var(--ink-ghost)',
              width: 56,
              flexShrink: 0,
            }}
          >
            {entry.hash}
          </span>
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--ink)' }}>
            {entry.message}
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-ghost)', flexShrink: 0, marginLeft: 8 }}>
            {entry.date}
          </span>
        </div>
      )
    })
  }

  // ----------------------------------------------------------
  //  Render principal
  // ----------------------------------------------------------

  return (
    <div style={styles.root}>
      {/* Header */}
      <div style={styles.header}>
        <span style={styles.headerTitle}>Repositório offline</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {externalCount > 0 && (
            <span style={styles.externalBadge}>
              ⎇ {externalCount} commit{externalCount > 1 ? 's' : ''} externo{externalCount > 1 ? 's' : ''}
            </span>
          )}
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => refresh()}
            disabled={polling}
            style={{ fontSize: 10, padding: '2px 8px' }}
          >
            {polling ? '…' : '↻ atualizar'}
          </button>
        </div>
      </div>

      {/* Item 7 — Banner de commits recebidos via Syncthing */}
      {incoming && incoming.count > 0 && showIncoming && (
        <div style={styles.incomingBanner}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, flexWrap: 'wrap' as const }}>
            <span style={{ color: '#2C5F8A', fontWeight: 700 }}>
              ⎇ {incoming.count} commit{incoming.count > 1 ? 's' : ''} recebido{incoming.count > 1 ? 's' : ''} desde a última sessão
            </span>
            <span style={{ color: 'var(--ink-ghost)', fontSize: 10 }}>
              — {incoming.entries.slice(0, 3).map(e => e.hash).join(', ')}
              {incoming.count > 3 ? ` + ${incoming.count - 3}…` : ''}
            </span>
          </div>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setShowIncoming(false)}
            style={{ fontSize: 10, padding: '2px 6px', flexShrink: 0 }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Corpo: status (esquerda) + log (direita) */}
      <div style={styles.body}>

        {/* Coluna esquerda: status + commit */}
        <div style={styles.leftCol}>
          <p style={styles.sectionLabel}>
            Alterações
            <span style={{ fontWeight: 400, marginLeft: 6 }}>({status.length})</span>
          </p>

          <div style={styles.fileList}>
            {renderStatusList()}
          </div>

          {/* Diff inline */}
          {renderDiff()}

          {/* Formulário de commit */}
          <div style={styles.commitForm}>
            <input
              type="text"
              value={commitMsg}
              onChange={e => { setCommitMsg(e.target.value); setCommitErr(''); setCommitOk('') }}
              onKeyDown={e => { if (e.key === 'Enter') handleCommit() }}
              placeholder="Mensagem (deixe vazio para mensagem automática)…"
              style={styles.commitInput}
            />
            <button
              className="btn btn-primary"
              onClick={handleCommit}
              disabled={committing}
              style={{ fontSize: 11, padding: '5px 14px', flexShrink: 0 }}
            >
              {committing ? '…' : 'Commit'}
            </button>
          </div>
          {commitErr && <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#8B3A2A', margin: '4px 0 0' }}>{commitErr}</p>}
          {commitOk  && <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#4A6741', margin: '4px 0 0' }}>{commitOk}</p>}
        </div>

        {/* Coluna direita: log */}
        <div style={styles.rightCol}>
          <p style={styles.sectionLabel}>
            Histórico
            <span style={{ fontWeight: 400, marginLeft: 6 }}>({log.length})</span>
          </p>
          <div style={styles.logList}>
            {renderLog()}
          </div>
          {externalCount > 0 && (
            <p style={styles.externalNote}>
              Commits em azul são externos — recebidos via Syncthing nesta sessão.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  Estilos
// ----------------------------------------------------------

const styles = {
  root: {
    display: 'flex',
    flexDirection: 'column' as const,
    height: '100%',
    background: 'var(--paper)',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 20px',
    borderBottom: '1px solid var(--rule)',
    flexShrink: 0,
  },
  headerTitle: {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    letterSpacing: '0.12em',
    textTransform: 'uppercase' as const,
    color: 'var(--ink-ghost)',
  },
  externalBadge: {
    fontFamily: 'var(--font-mono)',
    fontSize: 10,
    color: '#2C5F8A',
    background: 'rgba(44,95,138,0.1)',
    border: '1px solid rgba(44,95,138,0.3)',
    borderRadius: 'var(--radius)',
    padding: '2px 8px',
  },
  body: {
    display: 'flex',
    flex: 1,
    overflow: 'hidden',
  },
  leftCol: {
    width: '42%',
    flexShrink: 0,
    display: 'flex',
    flexDirection: 'column' as const,
    borderRight: '1px solid var(--rule)',
    overflow: 'hidden',
  },
  rightCol: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column' as const,
    overflow: 'hidden',
  },
  sectionLabel: {
    fontFamily: 'var(--font-mono)',
    fontSize: 9,
    letterSpacing: '0.14em',
    textTransform: 'uppercase' as const,
    color: 'var(--accent)',
    margin: 0,
    padding: '10px 16px 6px',
    flexShrink: 0,
    fontWeight: 700 as const,
  },
  fileList: {
    flex: 1,
    overflowY: 'auto' as const,
    minHeight: 0,
  },
  fileRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '5px 16px',
    cursor: 'pointer',
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    borderRadius: 'var(--radius)',
    transition: 'background 100ms',
  },
  diffPanel: {
    borderTop: '1px solid var(--rule)',
    flexShrink: 0,
    maxHeight: '35%',
    display: 'flex',
    flexDirection: 'column' as const,
    overflow: 'hidden',
  },
  diffHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '5px 16px',
    borderBottom: '1px solid var(--rule)',
    flexShrink: 0,
  },
  diffTitle: {
    fontFamily: 'var(--font-mono)',
    fontSize: 10,
    color: 'var(--ink-ghost)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  diffBody: {
    flex: 1,
    overflowY: 'auto' as const,
    margin: 0,
    padding: '8px 16px',
    fontFamily: 'var(--font-code)',
    fontSize: 10,
    lineHeight: 1.6,
    color: 'var(--ink)',
    background: 'var(--paper-dark)',
    whiteSpace: 'pre' as const,
  },
  commitForm: {
    display: 'flex',
    gap: 8,
    padding: '10px 16px',
    borderTop: '1px solid var(--rule)',
    flexShrink: 0,
  },
  commitInput: {
    flex: 1,
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    padding: '5px 8px',
    background: 'var(--paper-dark)',
    border: '1px solid var(--rule)',
    borderRadius: 'var(--radius)',
    color: 'var(--ink)',
    outline: 'none',
  },
  logList: {
    flex: 1,
    overflowY: 'auto' as const,
    minHeight: 0,
  },
  logRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '5px 16px',
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    borderBottom: '1px solid var(--rule)',
  },
  incomingBanner: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '8px 20px',
    background: 'rgba(44,95,138,0.08)',
    borderBottom: '1px solid rgba(44,95,138,0.25)',
    flexShrink: 0,
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
  },
  externalNote: {
    fontFamily: 'var(--font-mono)',
    fontSize: 9,
    color: 'var(--ink-ghost)',
    padding: '6px 16px',
    margin: 0,
    borderTop: '1px solid var(--rule)',
    flexShrink: 0,
  },
  empty: {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    color: 'var(--ink-ghost)',
    fontStyle: 'italic',
    padding: '12px 16px',
    margin: 0,
  },
} as const
