/* ============================================================
   HUB — SearchView
   Gerenciamento do SearXNG: status do serviço, URL configurável,
   start/stop e teste de conectividade.
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import * as cmd from '../lib/tauri'
import type { SearxngStatus } from '../types'

// ── Primitivos (mesmos da SyncView) ──────────────────────────

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

// ── View principal ────────────────────────────────────────────

export function SearchView() {
  const [status,   setStatus]   = useState<SearxngStatus | null>(null)
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [testing,  setTesting]  = useState(false)
  const [testMsg,  setTestMsg]  = useState<string | null>(null)
  const [err,      setErr]      = useState<string | null>(null)

  // URL editável
  const [url,      setUrl]      = useState('')
  const [urlSaving, setUrlSaving] = useState(false)
  const [urlSaved,  setUrlSaved]  = useState(false)

  const runningRef = useRef(true)

  async function refresh() {
    const res = await cmd.searxngStatus()
    if (!runningRef.current) return
    if (res.ok) {
      setStatus(res.data)
      setUrl(res.data.url)
      setErr(null)
    } else {
      setErr(res.error.message)
    }
  }

  useEffect(() => {
    runningRef.current = true
    refresh()
    return () => { runningRef.current = false }
  }, [])

  useEffect(() => {
    const id = setInterval(refresh, 10_000)
    return () => clearInterval(id)
  }, [])

  async function handleStart() {
    setStarting(true)
    const res = await cmd.searxngStart()
    if (!res.ok) setErr(res.error.message)
    setTimeout(async () => { await refresh(); setStarting(false) }, 2000)
  }

  async function handleStop() {
    setStopping(true)
    const res = await cmd.searxngStop()
    if (!res.ok) setErr(res.error.message)
    setTimeout(async () => { await refresh(); setStopping(false) }, 1500)
  }

  async function handleSaveUrl() {
    const trimmed = url.trim()
    if (!trimmed) return
    setUrlSaving(true)
    const res = await cmd.searxngSetUrl(trimmed)
    setUrlSaving(false)
    if (res.ok) {
      setUrlSaved(true)
      setTimeout(() => setUrlSaved(false), 2000)
      await refresh()
    } else {
      setErr(res.error.message)
    }
  }

  async function handleTest() {
    setTesting(true)
    setTestMsg(null)
    const res = await cmd.searxngStatus()
    setTesting(false)
    if (res.ok) {
      setTestMsg(res.data.reachable
        ? '✓ SearXNG respondeu — healthcheck OK'
        : '✗ SearXNG não respondeu — verifique se está rodando e a URL está correta'
      )
    } else {
      setTestMsg(`✗ Erro: ${res.error.message}`)
    }
    setTimeout(() => setTestMsg(null), 5000)
  }

  const active    = status?.active    ?? false
  const reachable = status?.reachable ?? false

  const dotColor = !status
    ? 'var(--ink-ghost)'
    : reachable
    ? '#4A6741'
    : active
    ? '#b8860b'
    : 'var(--ink-ghost)'

  const statusLabel = !status
    ? 'verificando…'
    : reachable
    ? 'rodando e acessível'
    : active
    ? 'ativo mas sem resposta'
    : 'parado'

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
          ⊙ Busca
        </span>
        {err && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#8B3A2A' }}>
            {err}
          </span>
        )}
      </div>

      {/* Status + controles */}
      <Card>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
            background: dotColor,
            opacity: status ? 1 : 0.4,
          }} />
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink)', flex: 1,
          }}>
            SearXNG — {statusLabel}
          </span>
          {active
            ? <Btn onClick={handleStop}  disabled={stopping}>{stopping  ? 'parando…'   : 'Parar'}</Btn>
            : <Btn onClick={handleStart} disabled={starting} accent>{starting ? 'iniciando…' : 'Iniciar'}</Btn>
          }
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Btn onClick={handleTest} disabled={testing}>
            {testing ? 'testando…' : 'Testar conexão'}
          </Btn>
          {testMsg && (
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 10,
              color: testMsg.startsWith('✓') ? '#4A6741' : '#8B3A2A',
            }}>
              {testMsg}
            </span>
          )}
        </div>
      </Card>

      {/* URL configurável */}
      <Card>
        <SecTitle label="URL do backend" />
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            value={url}
            onChange={e => { setUrl(e.target.value); setUrlSaved(false) }}
            placeholder="http://localhost:8888"
            style={{
              flex: 1, fontFamily: 'var(--font-mono)', fontSize: 12,
              background: 'var(--paper)', border: '1px solid var(--rule)',
              borderRadius: 3, padding: '5px 10px', color: 'var(--ink)',
            }}
          />
          <Btn onClick={handleSaveUrl} disabled={urlSaving || url.trim() === (status?.url ?? '')}>
            {urlSaved ? '✓ salvo' : urlSaving ? 'salvando…' : 'Salvar'}
          </Btn>
        </div>
        <p style={{
          fontFamily: 'var(--font-mono)', fontSize: 9,
          color: 'var(--ink-ghost)', opacity: 0.55, margin: '6px 0 0',
        }}>
          Usado pelo AKASHA como backend primário de busca web.
          Padrão AUR: http://localhost:8888
        </p>
      </Card>

      {/* Info */}
      <Card>
        <SecTitle label="Informações" />
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 10,
          color: 'var(--ink-ghost)', lineHeight: 1.7,
        }}>
          <div>Serviço systemd: <span style={{ color: 'var(--ink)' }}>searxng.service</span></div>
          <div>Fallback de busca: <span style={{ color: 'var(--ink)' }}>DuckDuckGo</span></div>
          <div style={{ marginTop: 6, opacity: 0.6, fontSize: 9 }}>
            Start/Stop pode requerer permissão de administrador dependendo da configuração do sistema.
            Se o botão falhar, use: <code>sudo systemctl start searxng</code>
          </div>
        </div>
      </Card>

    </div>
  )
}
