/* ============================================================
   HUB — SetupView
   Edição e validação dos caminhos do ecosystem.json.
   ============================================================ */

import { useEffect, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { EcosystemConfig } from '../types'

interface SetupViewProps {
  onBack: () => void
  onSaved: () => void
}

interface PathField {
  key: keyof EcosystemConfig
  field: string
  label: string
  placeholder: string
}

const FIELDS: PathField[] = [
  {
    key: 'aether',
    field: 'vault_path',
    label: 'AETHER — Vault',
    placeholder: 'Caminho da pasta vault do AETHER…',
  },
  {
    key: 'kosmos',
    field: 'archive_path',
    label: 'KOSMOS — Archive',
    placeholder: 'Caminho da pasta archive do KOSMOS…',
  },
  {
    key: 'ogma',
    field: 'data_path',
    label: 'OGMA — Dados',
    placeholder: 'Caminho da pasta data do OGMA…',
  },
]

type ValidityMap = Record<string, boolean | null>  // null = não verificado ainda

export function SetupView({ onBack, onSaved }: SetupViewProps) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [validity, setValidity] = useState<ValidityMap>({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // Carrega valores atuais do ecosystem.json
  useEffect(() => {
    cmd.readEcosystemConfig().then(result => {
      if (!result.ok) return
      const eco = result.data
      const initial: Record<string, string> = {}
      for (const f of FIELDS) {
        const section = eco[f.key] as Record<string, unknown> | undefined
        initial[`${f.key}.${f.field}`] = String(section?.[f.field] ?? '')
      }
      setValues(initial)
    })
  }, [])

  // Valida um campo quando o valor muda (debounce implícito: ao sair do campo)
  async function validateField(compositeKey: string, value: string) {
    if (!value.trim()) {
      setValidity(v => ({ ...v, [compositeKey]: null }))
      return
    }
    const result = await cmd.validatePath(value.trim())
    setValidity(v => ({ ...v, [compositeKey]: result.ok ? result.data : false }))
  }

  function handleChange(compositeKey: string, value: string) {
    setValues(v => ({ ...v, [compositeKey]: value }))
    setValidity(v => ({ ...v, [compositeKey]: null }))
  }

  async function handleSave() {
    setSaving(true)
    setError('')

    // Montar updates por seção
    const updates: Partial<EcosystemConfig> = {}
    for (const f of FIELDS) {
      const compositeKey = `${f.key}.${f.field}`
      const val = values[compositeKey]?.trim() ?? ''
      if (val) {
        const section = (updates[f.key] ?? {}) as Record<string, string>
        section[f.field] = val
        ;(updates as Record<string, unknown>)[f.key] = section
      }
    }

    const result = await cmd.saveEcosystemConfig(updates)
    setSaving(false)

    if (!result.ok) {
      setError(result.error.message)
      return
    }

    onSaved()
  }

  function validityIcon(compositeKey: string): string {
    const v = validity[compositeKey]
    if (v === null || v === undefined) return ''
    return v ? '✓' : '✗'
  }

  function validityColor(compositeKey: string): string {
    const v = validity[compositeKey]
    if (v === null || v === undefined) return 'var(--ink-ghost)'
    return v ? '#4A6741' : '#8B3A2A'
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--paper)',
      }}
    >
      {/* Topbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '10px 20px',
          borderBottom: '1px solid var(--rule)',
          flexShrink: 0,
        }}
      >
        <button className="btn btn-ghost btn-sm" onClick={onBack}>
          ← Voltar
        </button>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: 'var(--ink-ghost)',
          }}
        >
          Configuração do Ecossistema
        </span>
      </div>

      {/* Conteúdo */}
      <div
        style={{
          flex: 1,
          overflow: 'auto',
          padding: '32px 48px',
          maxWidth: 640,
          width: '100%',
          margin: '0 auto',
        }}
      >
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            color: 'var(--ink-ghost)',
            marginBottom: 32,
            lineHeight: 1.7,
          }}
        >
          Configure os caminhos dos outros apps para ativar os módulos do HUB.
          Os caminhos são gravados no arquivo de configuração compartilhado do ecossistema.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {FIELDS.map(f => {
            const compositeKey = `${f.key}.${f.field}`
            const value = values[compositeKey] ?? ''
            return (
              <div key={compositeKey}>
                <label
                  style={{
                    display: 'block',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                    letterSpacing: '0.14em',
                    textTransform: 'uppercase',
                    color: 'var(--ink-ghost)',
                    marginBottom: 6,
                  }}
                >
                  {f.label}
                </label>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    type="text"
                    value={value}
                    placeholder={f.placeholder}
                    onChange={e => handleChange(compositeKey, e.target.value)}
                    onBlur={e => validateField(compositeKey, e.target.value)}
                    style={{
                      flex: 1,
                      fontFamily: 'var(--font-mono)',
                      fontSize: 12,
                      padding: '6px 10px',
                      background: 'var(--paper-dark)',
                      border: '1px solid var(--rule)',
                      borderRadius: 'var(--radius)',
                      color: 'var(--ink)',
                      outline: 'none',
                    }}
                  />
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 14,
                      color: validityColor(compositeKey),
                      width: 18,
                      textAlign: 'center',
                      flexShrink: 0,
                    }}
                  >
                    {validityIcon(compositeKey)}
                  </span>
                </div>
              </div>
            )
          })}
        </div>

        {error && (
          <p
            style={{
              marginTop: 20,
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: '#8B3A2A',
            }}
          >
            {error}
          </p>
        )}

        <button
          className="btn btn-primary"
          style={{ marginTop: 36 }}
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? 'Salvando…' : 'Salvar configuração'}
        </button>
      </div>
    </div>
  )
}
