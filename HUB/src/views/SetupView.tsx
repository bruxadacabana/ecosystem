/* ============================================================
   HUB — SetupView
   Edição e validação dos caminhos do ecosystem.json.
   Seção 1: caminhos de dados (vault, archive, db)
   Seção 2: executáveis dos 5 apps (com auto-descoberta)
   ============================================================ */

import { useEffect, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { EcosystemConfig } from '../types'

interface SetupViewProps {
  onBack: () => void
  onSaved?: () => void
}

interface PathField {
  key: keyof EcosystemConfig
  field: string
  label: string
  placeholder: string
  validateAs: 'dir' | 'file'
  candidates?: string[]   // para auto-descoberta (apenas campos de exe)
}

const DATA_FIELDS: PathField[] = [
  {
    key: 'aether',
    field: 'vault_path',
    label: 'AETHER — Vault',
    placeholder: 'Caminho da pasta vault do AETHER…',
    validateAs: 'dir',
  },
  {
    key: 'kosmos',
    field: 'archive_path',
    label: 'KOSMOS — Archive',
    placeholder: 'Caminho da pasta archive do KOSMOS…',
    validateAs: 'dir',
  },
  {
    key: 'ogma',
    field: 'data_path',
    label: 'OGMA — Dados',
    placeholder: 'Caminho da pasta data do OGMA…',
    validateAs: 'dir',
  },
]

const EXE_FIELDS: PathField[] = [
  {
    key: 'aether',
    field: 'exe_path',
    label: 'AETHER',
    placeholder: 'Caminho para o executável do AETHER…',
    validateAs: 'file',
    candidates: ['AETHER', 'aether', 'AETHER.exe'],
  },
  {
    key: 'ogma',
    field: 'exe_path',
    label: 'OGMA',
    placeholder: 'Caminho para o executável do OGMA…',
    validateAs: 'file',
    candidates: ['OGMA', 'ogma', 'OGMA.exe'],
  },
  {
    key: 'kosmos',
    field: 'exe_path',
    label: 'KOSMOS',
    placeholder: 'Caminho para o executável do KOSMOS…',
    validateAs: 'file',
    candidates: ['KOSMOS', 'kosmos', 'KOSMOS.exe'],
  },
  {
    key: 'mnemosyne',
    field: 'exe_path',
    label: 'Mnemosyne',
    placeholder: 'Caminho para o executável do Mnemosyne…',
    validateAs: 'file',
    candidates: ['Mnemosyne', 'mnemosyne', 'Mnemosyne.exe'],
  },
  {
    key: 'hermes',
    field: 'exe_path',
    label: 'Hermes',
    placeholder: 'Caminho para o executável do Hermes…',
    validateAs: 'file',
    candidates: ['Hermes', 'hermes', 'Hermes.exe'],
  },
  {
    key: 'akasha',
    field: 'exe_path',
    label: 'AKASHA',
    placeholder: 'Caminho para o iniciar.sh do AKASHA…',
    validateAs: 'file',
    candidates: ['iniciar.sh'],
  },
]

const ALL_FIELDS = [...DATA_FIELDS, ...EXE_FIELDS]

type ValidityMap = Record<string, boolean | null>   // null = não verificado
type DetectingMap = Record<string, boolean>

export function SetupView({ onBack }: SetupViewProps) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [validity, setValidity] = useState<ValidityMap>({})
  const [detecting, setDetecting] = useState<DetectingMap>({})
  const [detectingAll, setDetectingAll] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [savedMsg, setSavedMsg] = useState('')
  const [syncRoot, setSyncRoot] = useState('')
  const [applyingSync, setApplyingSync] = useState(false)
  const [syncMsg, setSyncMsg] = useState('')

  // Carrega valores atuais do ecosystem.json
  useEffect(() => {
    cmd.readEcosystemConfig().then(result => {
      if (!result.ok) return
      const eco = result.data as Record<string, unknown>
      const initial: Record<string, string> = {}
      for (const f of ALL_FIELDS) {
        const section = eco[f.key] as Record<string, unknown> | undefined
        initial[`${f.key}.${f.field}`] = String(section?.[f.field] ?? '')
      }
      setValues(initial)
      setSyncRoot(String(eco['sync_root'] ?? ''))
    })
  }, [])

  async function validateField(compositeKey: string, value: string, validateAs: 'dir' | 'file') {
    if (!value.trim()) {
      setValidity(v => ({ ...v, [compositeKey]: null }))
      return
    }
    const result = validateAs === 'file'
      ? await cmd.validateExePath(value.trim())
      : await cmd.validatePath(value.trim())
    setValidity(v => ({ ...v, [compositeKey]: result.ok ? result.data : false }))
  }

  function handleChange(compositeKey: string, value: string) {
    setValues(v => ({ ...v, [compositeKey]: value }))
    setValidity(v => ({ ...v, [compositeKey]: null }))
    setSavedMsg('')
  }

  async function handleDiscoverAll() {
    setDetectingAll(true)
    const result = await cmd.autoDiscoverAllExePaths()
    setDetectingAll(false)

    if (!result.ok || !result.data) return

    const found = result.data
    const newValues: Record<string, string> = {}
    const newValidity: ValidityMap = {}

    for (const f of EXE_FIELDS) {
      const compositeKey = `${f.key}.${f.field}`
      const discovered = found[f.key]
      if (discovered) {
        newValues[compositeKey] = discovered
        newValidity[compositeKey] = true
      }
    }

    setValues(v => ({ ...v, ...newValues }))
    setValidity(v => ({ ...v, ...newValidity }))
  }

  async function handleDiscover(f: PathField) {
    if (!f.candidates) return
    const compositeKey = `${f.key}.${f.field}`
    setDetecting(d => ({ ...d, [compositeKey]: true }))

    const result = await cmd.discoverAppExe(f.candidates)
    setDetecting(d => ({ ...d, [compositeKey]: false }))

    if (result.ok && result.data) {
      setValues(v => ({ ...v, [compositeKey]: result.data as string }))
      setValidity(v => ({ ...v, [compositeKey]: true }))
    } else {
      setValidity(v => ({ ...v, [compositeKey]: false }))
    }
  }

  async function handleApplySyncRoot() {
    if (!syncRoot.trim()) return
    setApplyingSync(true)
    setSyncMsg('')
    const result = await cmd.applySyncRoot(syncRoot.trim())
    setApplyingSync(false)
    if (!result.ok) {
      setSyncMsg(`Erro: ${result.error.message}`)
    } else {
      setSyncMsg('Caminhos aplicados. Reinicie cada app para carregar os novos caminhos.')
      // Recarrega os campos de dados para refletir os novos caminhos
      const eco = await cmd.readEcosystemConfig()
      if (eco.ok) {
        const updated: Record<string, string> = {}
        for (const f of DATA_FIELDS) {
          const section = (eco.data as Record<string, unknown>)[f.key] as Record<string, unknown> | undefined
          updated[`${f.key}.${f.field}`] = String(section?.[f.field] ?? '')
        }
        setValues(v => ({ ...v, ...updated }))
      }
    }
  }

  async function handleSave() {
    setSaving(true)
    setError('')

    const updates: Partial<EcosystemConfig> = {}
    for (const f of ALL_FIELDS) {
      const compositeKey = `${f.key}.${f.field}`
      const val = values[compositeKey]?.trim() ?? ''
      if (val) {
        const section = ((updates as Record<string, unknown>)[f.key] ?? {}) as Record<string, unknown>
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

    setSavedMsg('Configuração salva. Reinicie cada app para aplicar os novos caminhos.')
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

  function renderField(f: PathField) {
    const compositeKey = `${f.key}.${f.field}`
    const value = values[compositeKey] ?? ''
    const isDetecting = detecting[compositeKey] ?? false

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
            onBlur={e => validateField(compositeKey, e.target.value, f.validateAs)}
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
          {f.candidates && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => handleDiscover(f)}
              disabled={isDetecting}
              style={{ flexShrink: 0, fontSize: 10, padding: '4px 8px' }}
            >
              {isDetecting ? '…' : 'Detectar'}
            </button>
          )}
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

        {/* Seção: sincronização */}
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 12 }}>
          Sincronização (Proton Drive)
        </p>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)', marginBottom: 12, lineHeight: 1.6 }}>
          Aponte para a pasta raiz do ecossistema no Proton Drive. As subpastas são criadas automaticamente e os caminhos de todos os apps são configurados de uma vez.
        </p>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', marginBottom: 16, lineHeight: 1.6, fontStyle: 'italic' }}>
          ⚠ Mova seus arquivos existentes para as novas pastas manualmente antes de aplicar.
        </p>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
          <input
            type="text"
            value={syncRoot}
            placeholder="Ex: C:\Users\...\ProtonDrive\ecosystem"
            onChange={e => { setSyncRoot(e.target.value); setSyncMsg('') }}
            style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: 12, padding: '6px 10px', background: 'var(--paper-dark)', border: '1px solid var(--rule)', borderRadius: 'var(--radius)', color: 'var(--ink)', outline: 'none' }}
          />
          <button
            className="btn btn-ghost btn-sm"
            onClick={handleApplySyncRoot}
            disabled={applyingSync || !syncRoot.trim()}
            style={{ flexShrink: 0, fontSize: 10, padding: '4px 10px' }}
          >
            {applyingSync ? '…' : 'Aplicar ao ecossistema'}
          </button>
        </div>
        {syncMsg && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: syncMsg.startsWith('Erro') ? '#8B3A2A' : '#4A6741', marginBottom: 16 }}>
            {syncMsg}
          </p>
        )}
        <div style={{ borderBottom: '1px solid var(--rule)', marginBottom: 32 }} />

        {/* Seção: caminhos de dados */}
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '0.16em',
            textTransform: 'uppercase',
            color: 'var(--accent)',
            marginBottom: 16,
          }}
        >
          Caminhos de dados
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24, marginBottom: 40 }}>
          {DATA_FIELDS.map(f => renderField(f))}
        </div>

        {/* Seção: executáveis */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
              color: 'var(--accent)',
              margin: 0,
            }}
          >
            Executáveis dos apps
          </p>
          <button
            className="btn btn-ghost btn-sm"
            onClick={handleDiscoverAll}
            disabled={detectingAll}
            style={{ fontSize: 10, padding: '4px 10px' }}
          >
            {detectingAll ? '…' : 'Detectar tudo'}
          </button>
        </div>
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--ink-ghost)',
            marginBottom: 16,
            lineHeight: 1.6,
          }}
        >
          Usados pela barra de atalhos para iniciar os apps e monitorar se estão rodando.
          "Detectar tudo" procura os scripts na pasta raiz do ecossistema automaticamente.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {EXE_FIELDS.map(f => renderField(f))}
        </div>

        {error && (
          <p style={{ marginTop: 20, fontFamily: 'var(--font-mono)', fontSize: 11, color: '#8B3A2A' }}>
            {error}
          </p>
        )}

        {savedMsg && (
          <p style={{ marginTop: 20, fontFamily: 'var(--font-mono)', fontSize: 11, color: '#4A6741' }}>
            {savedMsg}
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
