/* ============================================================
   AETHER — VaultSetup
   Tela de primeiro uso: o usuário escolhe a pasta do vault.
   Só aparece quando nenhum vault está configurado.
   ============================================================ */

import { useState } from 'react'
import { open as openDialog } from '@tauri-apps/plugin-dialog'
import { CosmosLayer } from './CosmosLayer'
import * as cmd from '../lib/tauri'

interface VaultSetupProps {
  onDone: () => void
}

export function VaultSetup({ onDone }: VaultSetupProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleChooseFolder() {
    setError(null)

    const selected = await openDialog({
      directory: true,
      multiple: false,
      title: 'Escolha a pasta do vault AETHER',
    })

    if (selected === null) return  // usuário cancelou

    const path = typeof selected === 'string' ? selected : selected

    setLoading(true)
    const result = await cmd.setVaultPath(path)
    setLoading(false)

    if (!result.ok) {
      setError(result.error.message)
      return
    }

    onDone()
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
        animation: 'fadeIn 0.3s ease both',
      }}
    >
      {/* Card de boas-vindas */}
      <div
        style={{
          position: 'relative',
          width: '520px',
          background: 'var(--paper-dark)',
          border: '1px solid var(--rule)',
          borderRadius: 'var(--radius)',
          boxShadow: '8px 8px 0 rgba(44,36,22,0.2)',
          overflow: 'hidden',
          animation: 'paperFall 0.28s ease-out both',
        }}
      >
        {/* Cosmos de fundo */}
        <CosmosLayer seed={1} density="medium" animated={true} width={520} height={300} />

        {/* Linha de margem */}
        <div
          aria-hidden="true"
          style={{
            position: 'absolute',
            top: 0,
            bottom: 0,
            left: '48px',
            width: '1px',
            background: 'var(--margin-line)',
            zIndex: 1,
          }}
        />

        {/* Conteúdo */}
        <div
          style={{
            position: 'relative',
            zIndex: 2,
            padding: '48px 40px 40px',
          }}
        >
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontStyle: 'italic',
              fontWeight: 'normal',
              fontSize: '32px',
              color: 'var(--ink)',
              margin: '0 0 8px',
              lineHeight: 1.2,
            }}
          >
            Bem-vindo ao AETHER
          </h1>

          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '9px',
              textTransform: 'uppercase',
              letterSpacing: '0.2em',
              color: 'var(--ink-faint)',
              margin: '0 0 28px',
            }}
          >
            Forja de Mundos
          </p>

          <div
            style={{
              width: '80px',
              height: '1px',
              background: 'var(--rule)',
              marginBottom: '28px',
            }}
            aria-hidden="true"
          />

          <p
            style={{
              fontFamily: 'var(--font-display)',
              fontStyle: 'italic',
              fontSize: '15px',
              lineHeight: 1.65,
              color: 'var(--ink-light)',
              margin: '0 0 28px',
            }}
          >
            O AETHER guarda seus mundos em uma pasta de sua escolha
            — portátil, versionável, inteiramente sua.
          </p>

          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              color: 'var(--ink-faint)',
              margin: '0 0 28px',
              lineHeight: 1.6,
            }}
          >
            Escolha uma pasta vazia ou existente para ser o seu vault.
            Ela pode estar em qualquer lugar no seu computador.
          </p>

          {error && (
            <p
              role="alert"
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                color: 'var(--ribbon)',
                margin: '0 0 16px',
                padding: '8px 12px',
                border: '1px solid var(--ribbon)',
                borderRadius: 'var(--radius)',
                background: 'transparent',
              }}
            >
              {error}
            </p>
          )}

          <button
            className="btn btn-primary"
            onClick={handleChooseFolder}
            disabled={loading}
            style={{ width: '100%', justifyContent: 'center', display: 'flex' }}
          >
            {loading ? 'Configurando...' : 'Escolher pasta do vault'}
          </button>
        </div>
      </div>
    </div>
  )
}
