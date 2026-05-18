/* ============================================================
   HUB — SyncSetupView
   Tela de primeiro uso: configuração da pasta raiz do ecossistema.
   Mostrada apenas quando sync_root não está configurado no ecosystem.json.
   ============================================================ */

import { useState } from 'react'
import { open as openDialog } from '@tauri-apps/plugin-dialog'
import { CosmosLayer } from '../components/CosmosLayer'
import * as cmd from '../lib/tauri'

interface SyncSetupViewProps {
  onDone: () => void
}

export function SyncSetupView({ onDone }: SyncSetupViewProps) {
  const [path, setPath]       = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  async function handlePick() {
    const dir = await openDialog({ directory: true, multiple: false })
    if (typeof dir === 'string' && dir) {
      setPath(dir)
      setError('')
    }
  }

  async function handleConfirm() {
    const p = path.trim()
    if (!p) return
    setLoading(true)
    setError('')
    const result = await cmd.applySyncRoot(p)
    setLoading(false)
    if (!result.ok) {
      setError(result.error.message)
    } else {
      onDone()
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--paper)',
      }}
    >
      <div style={{ position: 'relative', width: 560, height: 380 }}>
        <CosmosLayer seed={3} density="low" animated width={560} height={380} />

        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 20,
            padding: '0 56px',
          }}
        >
          {/* Título */}
          <h2
            style={{
              fontFamily: 'var(--font-display)',
              fontStyle: 'italic',
              fontSize: 36,
              color: 'var(--ink)',
              margin: 0,
              letterSpacing: '0.03em',
            }}
          >
            Primeiro uso
          </h2>

          {/* Descrição */}
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--ink-ghost)',
              textAlign: 'center',
              lineHeight: 1.9,
              margin: 0,
            }}
          >
            Escolha a pasta raiz do ecossistema — onde todos os apps guardam seus dados.
            <br />
            Aponte para sua pasta sincronizada (Syncthing, Proton Drive…) ou qualquer pasta local.
          </p>

          {/* Seletor de pasta */}
          <div style={{ display: 'flex', gap: 8, width: '100%' }}>
            <input
              type="text"
              value={path}
              placeholder="Caminho da pasta raiz…"
              onChange={e => { setPath(e.target.value); setError('') }}
              onKeyDown={e => { if (e.key === 'Enter') handleConfirm() }}
              style={{
                flex: 1,
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
                padding: '7px 10px',
                background: 'var(--paper-dark)',
                border: '1px solid var(--rule)',
                borderRadius: 'var(--radius)',
                color: 'var(--ink)',
                outline: 'none',
              }}
            />
            <button
              className="btn btn-ghost btn-sm"
              onClick={handlePick}
              style={{ flexShrink: 0 }}
            >
              Escolher…
            </button>
          </div>

          {/* Erro */}
          {error && (
            <p
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: '#8B3A2A',
                margin: 0,
                textAlign: 'center',
              }}
            >
              {error}
            </p>
          )}

          {/* Confirmar */}
          <button
            className="btn btn-primary"
            onClick={handleConfirm}
            disabled={loading || !path.trim()}
          >
            {loading ? 'Configurando…' : 'Confirmar'}
          </button>
        </div>
      </div>
    </div>
  )
}
