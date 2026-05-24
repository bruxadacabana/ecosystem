/* ============================================================
   HUB — SetupView
   Edição e validação dos caminhos do ecosystem.json.
   Seção 1: caminhos de dados (vault, archive, db)
   Seção 2: executáveis dos 5 apps (com auto-descoberta)
   ============================================================ */

import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { open as openDialog } from '@tauri-apps/plugin-dialog'
import * as cmd from '../lib/tauri'
import type { ServiceCredentials, ResetReport } from '../lib/tauri'
import type { EcosystemConfig } from '../types'

const WILL_DELETE = [
  'AKASHA: páginas crawleadas (não salvas)',
  'AKASHA: memória pessoal da IA (personal_memory)',
  'AKASHA: base de conhecimento (akasha_knowledge.db)',
  'KOSMOS: artigos não salvos',
  'Mnemosyne: banco vetorial ChromaDB',
  'Mnemosyne: índice BM25',
  'Mnemosyne: memória pessoal da IA (personal_memory.db)',
  'Compartilhado: communication_history.db',
  'Compartilhado: shared_topic_profile.db',
] as const

const WILL_PRESERVE = [
  'AKASHA: lista de sites (crawl_sites)',
  'AKASHA: userdata (blocked_domains, watch_later, etc.)',
  'AKASHA: arquivos salvos (Web/, Papers/)',
  'KOSMOS: lista de feeds',
  'KOSMOS: artigos salvos (is_saved=1)',
  'Mnemosyne: notebooks (histórico de chats)',
  'Mnemosyne: documentos da biblioteca',
  'Hermes: transcrições, ecosystem.json, modelos LOGOS, .backup/',
] as const

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
  {
    key: 'mnemosyne',
    field: 'watched_dir',
    label: 'Mnemosyne — Biblioteca',
    placeholder: 'Pasta principal monitorada pelo Mnemosyne…',
    validateAs: 'dir',
  },
  {
    key: 'mnemosyne',
    field: 'vault_dir',
    label: 'Mnemosyne — Vault (opcional)',
    placeholder: 'Pasta de notas/vault a indexar junto…',
    validateAs: 'dir',
  },
  {
    key: 'mnemosyne',
    field: 'chroma_dir',
    label: 'Mnemosyne — ChromaDB',
    placeholder: 'Pasta onde o banco vetorial é armazenado…',
    validateAs: 'dir',
  },
  {
    key: 'hermes',
    field: 'recipes_dir',
    label: 'HERMES — Receitas',
    placeholder: 'Pasta onde as receitas extraídas são salvas…',
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
  const [extraDirs, setExtraDirs] = useState<string[]>([])

  const defaultCreds: ServiceCredentials = {
    unpaywall_email: '', qbt_host: 'localhost', qbt_port: 8080,
    qbt_user: '', qbt_password: '', syncthing_gui_user: '', syncthing_gui_password: '',
  }
  const [creds,       setCreds]       = useState<ServiceCredentials>(defaultCreds)
  const [credsSaving, setCredsSaving] = useState(false)
  const [credsSaved,  setCredsSaved]  = useState(false)
  const [credsErr,    setCredsErr]    = useState('')

  const [resetModalOpen, setResetModalOpen] = useState(false)
  const [resetToken,     setResetToken]     = useState('')
  const [resetting,      setResetting]      = useState(false)
  const [resetReport,    setResetReport]    = useState<ResetReport | null>(null)
  const [resetErr,       setResetErr]       = useState('')

  // Carrega valores atuais do ecosystem.json e credenciais
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
      const mnem = eco['mnemosyne'] as Record<string, unknown> | undefined
      setExtraDirs((mnem?.['extra_dirs'] as string[] | undefined) ?? [])
    })
    cmd.getServiceCredentials().then(res => {
      if (res.ok) setCreds(res.data)
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

  async function handleAddExtraDir() {
    const dir = await openDialog({ directory: true, multiple: false })
    if (typeof dir === 'string' && dir && !extraDirs.includes(dir))
      setExtraDirs(prev => [...prev, dir])
  }

  function handleRemoveExtraDir(idx: number) {
    setExtraDirs(prev => prev.filter((_, i) => i !== idx))
  }

  async function handleSaveCreds() {
    setCredsSaving(true)
    setCredsErr('')
    setCredsSaved(false)
    const res = await cmd.saveServiceCredentials(creds)
    setCredsSaving(false)
    if (res.ok) {
      setCredsSaved(true)
      setTimeout(() => setCredsSaved(false), 3000)
    } else {
      setCredsErr(res.error.message)
    }
  }

  async function handleReset() {
    setResetting(true)
    setResetErr('')
    const res = await cmd.ecosystemReset(resetToken)
    setResetting(false)
    if (res.ok) {
      setResetReport(res.data)
      setResetToken('')
    } else {
      setResetErr(res.error.message)
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

    // extra_dirs do Mnemosyne — persiste mesmo quando vazio (sobrescreve lista anterior)
    const mnemSection = ((updates as Record<string, unknown>)['mnemosyne'] ?? {}) as Record<string, unknown>
    mnemSection['extra_dirs'] = extraDirs
    ;(updates as Record<string, unknown>)['mnemosyne'] = mnemSection

    const result = await cmd.saveEcosystemConfig(updates)
    setSaving(false)

    if (!result.ok) {
      setError(result.error.message)
      return
    }

    setSavedMsg('Configuração salva. Reinicie cada app para aplicar os novos caminhos.')
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24, marginBottom: 32 }}>
          {DATA_FIELDS.map(f => renderField(f))}
        </div>

        {/* Pastas extras do Mnemosyne */}
        <label
          style={{
            display: 'block',
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            color: 'var(--ink-ghost)',
            marginBottom: 8,
          }}
        >
          Mnemosyne — Pastas extras para indexação
        </label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 8 }}>
          {extraDirs.length === 0 && (
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)', fontStyle: 'italic', margin: 0 }}>
              Nenhuma pasta extra configurada.
            </p>
          )}
          {extraDirs.map((dir, idx) => (
            <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink)', padding: '4px 8px', background: 'var(--paper-dark)', borderRadius: 'var(--radius)', border: '1px solid var(--rule)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {dir}
              </span>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => handleRemoveExtraDir(idx)}
                style={{ flexShrink: 0, fontSize: 11, padding: '2px 8px', color: 'var(--ribbon)' }}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
        <button
          className="btn btn-ghost btn-sm"
          onClick={handleAddExtraDir}
          style={{ fontSize: 10, padding: '4px 10px', marginBottom: 40 }}
        >
          + Adicionar pasta
        </button>

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

        {/* ── Credenciais e Serviços Externos ─────────────────────────── */}
        <div style={{ borderTop: '1px solid var(--rule)', marginTop: 48, paddingTop: 32 }}>
          <p style={sectionTitleStyle}>Credenciais e Serviços Externos</p>
          <p style={hintStyle}>
            Credenciais lidas pelo AKASHA e outros apps em runtime. Armazenadas localmente no ecosystem.json.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div>
              <label style={labelStyle}>Unpaywall — E-mail</label>
              <input
                type="email"
                value={creds.unpaywall_email}
                placeholder="seu@email.com"
                onChange={e => setCreds(c => ({ ...c, unpaywall_email: e.target.value }))}
                style={inputStyle}
              />
            </div>

            <p style={{ ...labelStyle, marginBottom: 0, color: 'var(--ink-ghost)', fontSize: 11 }}>qBittorrent</p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px', gap: 12 }}>
              <div>
                <label style={labelStyle}>Host</label>
                <input
                  type="text"
                  value={creds.qbt_host}
                  placeholder="localhost"
                  onChange={e => setCreds(c => ({ ...c, qbt_host: e.target.value }))}
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={labelStyle}>Porta</label>
                <input
                  type="number"
                  value={creds.qbt_port}
                  min={1}
                  max={65535}
                  onChange={e => setCreds(c => ({ ...c, qbt_port: Number(e.target.value) }))}
                  style={inputStyle}
                />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={labelStyle}>Usuário</label>
                <input
                  type="text"
                  value={creds.qbt_user}
                  placeholder="admin"
                  onChange={e => setCreds(c => ({ ...c, qbt_user: e.target.value }))}
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={labelStyle}>Senha</label>
                <input
                  type="password"
                  value={creds.qbt_password}
                  placeholder="••••••••"
                  onChange={e => setCreds(c => ({ ...c, qbt_password: e.target.value }))}
                  style={inputStyle}
                />
              </div>
            </div>

            <p style={{ ...labelStyle, marginBottom: 0, color: 'var(--ink-ghost)', fontSize: 11 }}>Syncthing GUI</p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={labelStyle}>Usuário</label>
                <input
                  type="text"
                  value={creds.syncthing_gui_user}
                  placeholder="spacewitch"
                  onChange={e => setCreds(c => ({ ...c, syncthing_gui_user: e.target.value }))}
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={labelStyle}>Senha</label>
                <input
                  type="password"
                  value={creds.syncthing_gui_password}
                  placeholder="••••••••"
                  onChange={e => setCreds(c => ({ ...c, syncthing_gui_password: e.target.value }))}
                  style={inputStyle}
                />
              </div>
            </div>
          </div>

          {credsErr && (
            <p style={{ marginTop: 12, fontFamily: 'var(--font-mono)', fontSize: 11, color: '#8B3A2A' }}>
              {credsErr}
            </p>
          )}
          {credsSaved && (
            <p style={{ marginTop: 12, fontFamily: 'var(--font-mono)', fontSize: 11, color: '#4A6741' }}>
              Credenciais salvas.
            </p>
          )}
          <button
            className="btn btn-ghost btn-sm"
            style={{ marginTop: 16 }}
            onClick={handleSaveCreds}
            disabled={credsSaving}
          >
            {credsSaving ? 'Salvando…' : 'Salvar credenciais'}
          </button>
        </div>

        {/* ── Zona de Risco ────────────────────────────────────────────── */}
        <div style={{ borderTop: '1px solid var(--rule)', marginTop: 48, paddingTop: 32, marginBottom: 40 }}>
          <p style={{ ...sectionTitleStyle, color: 'var(--ribbon)' }}>Zona de Risco</p>
          <p style={hintStyle}>
            Apaga dados transientes (indexação, memória das IAs, artigos não salvos)
            preservando a lista de fontes, feeds, arquivos salvos e configurações.
            Um backup é criado automaticamente antes de qualquer deleção.
          </p>
          <button
            style={{
              fontFamily:   'var(--font-mono)',
              fontSize:     11,
              padding:      '6px 14px',
              background:   'transparent',
              border:       '1px solid var(--ribbon)',
              borderRadius: 'var(--radius)',
              color:        'var(--ribbon)',
              cursor:       'pointer',
            }}
            onClick={() => { setResetModalOpen(true); setResetToken(''); setResetReport(null); setResetErr('') }}
          >
            Resetar dados transientes
          </button>
        </div>
      </div>

      {/* ── Modal de confirmação do reset ────────────────────────────── */}
      {resetModalOpen && (
        <div
          style={{
            position:       'fixed',
            inset:          0,
            background:     'rgba(0,0,0,0.72)',
            zIndex:         9000,
            display:        'flex',
            alignItems:     'center',
            justifyContent: 'center',
          }}
        >
          <div
            style={{
              background:   'var(--paper)',
              borderRadius: 8,
              padding:      '28px 32px',
              maxWidth:     520,
              width:        '90vw',
              maxHeight:    '80vh',
              overflow:     'auto',
              boxShadow:    '0 8px 32px rgba(0,0,0,0.4)',
            }}
          >
            {resetReport ? (
              <>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, color: 'var(--ink)', marginBottom: 16 }}>
                  Reset concluído
                </p>
                <p style={{ ...hintStyle, marginBottom: 8 }}>Apagados ({resetReport.deleted.length}):</p>
                <ul style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink)', paddingLeft: 16, margin: '0 0 12px' }}>
                  {resetReport.deleted.map((d, i) => <li key={i}>{d}</li>)}
                </ul>
                {resetReport.errors.length > 0 && (
                  <>
                    <p style={{ ...hintStyle, color: '#8B3A2A', marginBottom: 8 }}>Erros ({resetReport.errors.length}):</p>
                    <ul style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#8B3A2A', paddingLeft: 16, margin: '0 0 12px' }}>
                      {resetReport.errors.map((e, i) => <li key={i}>{e}</li>)}
                    </ul>
                  </>
                )}
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ marginTop: 8 }}
                  onClick={() => { setResetModalOpen(false); setResetReport(null) }}
                >
                  Fechar
                </button>
              </>
            ) : (
              <>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, color: 'var(--ribbon)', marginBottom: 16 }}>
                  Resetar dados transientes
                </p>
                <p style={{ ...hintStyle, marginBottom: 6, color: 'var(--ink)' }}>Será apagado:</p>
                <ul style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#8B3A2A', paddingLeft: 16, margin: '0 0 16px' }}>
                  {WILL_DELETE.map((d, i) => <li key={i}>{d}</li>)}
                </ul>
                <p style={{ ...hintStyle, marginBottom: 6, color: 'var(--ink)' }}>Será preservado:</p>
                <ul style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#4A6741', paddingLeft: 16, margin: '0 0 20px' }}>
                  {WILL_PRESERVE.map((p, i) => <li key={i}>{p}</li>)}
                </ul>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink)', marginBottom: 8 }}>
                  Digite <strong>RESETAR</strong> para confirmar:
                </p>
                <input
                  type="text"
                  value={resetToken}
                  placeholder="RESETAR"
                  onChange={e => setResetToken(e.target.value)}
                  style={{ ...inputStyle, marginBottom: 8, fontFamily: 'var(--font-mono)' }}
                />
                {resetErr && (
                  <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#8B3A2A', marginBottom: 8 }}>
                    {resetErr}
                  </p>
                )}
                <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => setResetModalOpen(false)}
                    disabled={resetting}
                  >
                    Cancelar
                  </button>
                  <button
                    style={{
                      fontFamily:   'var(--font-mono)',
                      fontSize:     11,
                      padding:      '4px 14px',
                      background:   resetToken === 'RESETAR' ? 'var(--ribbon)' : 'transparent',
                      border:       '1px solid var(--ribbon)',
                      borderRadius: 'var(--radius)',
                      color:        resetToken === 'RESETAR' ? 'white' : 'var(--ribbon)',
                      cursor:       resetToken === 'RESETAR' && !resetting ? 'pointer' : 'not-allowed',
                      opacity:      resetToken === 'RESETAR' && !resetting ? 1 : 0.5,
                    }}
                    onClick={handleReset}
                    disabled={resetting || resetToken !== 'RESETAR'}
                  >
                    {resetting ? 'Resetando…' : 'Confirmar reset'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Estilos compartilhados ─────────────────────────────────────────────────

const sectionTitleStyle: CSSProperties = {
  fontFamily:    'var(--font-mono)',
  fontSize:      10,
  letterSpacing: '0.16em',
  textTransform: 'uppercase',
  color:         'var(--accent)',
  marginBottom:  16,
}

const hintStyle: CSSProperties = {
  fontFamily:   'var(--font-body)',
  fontSize:     12,
  color:        'var(--ink-ghost)',
  marginBottom: 16,
  lineHeight:   1.6,
}

const labelStyle: CSSProperties = {
  display:       'block',
  fontFamily:    'var(--font-mono)',
  fontSize:      10,
  letterSpacing: '0.14em',
  textTransform: 'uppercase',
  color:         'var(--ink-ghost)',
  marginBottom:  6,
}

const inputStyle: CSSProperties = {
  width:        '100%',
  fontFamily:   'var(--font-mono)',
  fontSize:     12,
  padding:      '6px 10px',
  background:   'var(--paper-dark)',
  border:       '1px solid var(--rule)',
  borderRadius: 'var(--radius)',
  color:        'var(--ink)',
  outline:      'none',
  boxSizing:    'border-box',
}
