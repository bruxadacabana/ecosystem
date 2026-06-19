/* ============================================================
   HUB — ConfigView (editor genérico do ecosystem.json)
   Expõe TODAS as chaves de config do ecosystem.json (que é por-máquina,
   não sincronizado), escondendo runtime/plumbing. Salva via merge no backend.
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import * as cmd from '../lib/tauri'
import {
  buildConfigSections, buildUpdates, parseFieldValue,
  type ConfigField, type ConfigSectionFields,
} from '../lib/config-fields'

const SECTION_LABELS: Record<string, string> = {
  '': 'Geral', akasha: 'AKASHA', kosmos: 'KOSMOS', mnemosyne: 'Mnemosyne',
  aether: 'AETHER', ogma: 'OGMA', hermes: 'Hermes', hub: 'HUB', logos: 'LOGOS',
}

function Card({ children }: { children: ReactNode }) {
  return (
    <div style={{
      background: 'var(--paper-dark)', border: '1px solid var(--rule)',
      borderRadius: 'var(--radius)', padding: '14px 18px', marginBottom: 14,
    }}>{children}</div>
  )
}

function fieldKey(f: ConfigField): string { return `${f.section}.${f.key}` }

export function ConfigView() {
  const [sections, setSections] = useState<ConfigSectionFields[]>([])
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const running = useRef(true)

  async function load() {
    const res = await cmd.readEcosystemConfig()
    if (!running.current) return
    if (!res.ok) { setErr(res.error.message); return }
    const secs = buildConfigSections(res.data as Record<string, unknown>)
    setSections(secs)
    const init: Record<string, string> = {}
    for (const s of secs) for (const f of s.fields) {
      init[fieldKey(f)] = f.type === 'list'
        ? (f.value as string[]).join('\n')
        : f.type === 'boolean'
        ? String(f.value)
        : String(f.value)
    }
    setEdits(init)
    setErr(null)
  }

  useEffect(() => { running.current = true; load(); return () => { running.current = false } }, [])

  function setEdit(k: string, v: string) { setEdits(prev => ({ ...prev, [k]: v })) }

  async function handleSave() {
    setSaving(true); setSavedMsg(null)
    const allFields: ConfigField[] = sections.flatMap(s => s.fields).map(f => ({
      ...f, value: parseFieldValue(f.type, edits[fieldKey(f)] ?? ''),
    }))
    const updates = buildUpdates(allFields)
    const res = await cmd.saveEcosystemConfig(updates)
    setSaving(false)
    if (res.ok) {
      setSavedMsg('✓ salvo'); setTimeout(() => setSavedMsg(null), 2500); await load()
    } else { setErr(res.error.message) }
  }

  function renderField(f: ConfigField) {
    const k = fieldKey(f)
    const val = edits[k] ?? ''
    const labelStyle: React.CSSProperties = {
      fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)', minWidth: 200,
    }
    const inputStyle: React.CSSProperties = {
      flex: 1, fontFamily: 'var(--font-mono)', fontSize: 12,
      background: 'var(--paper)', border: '1px solid var(--rule)',
      borderRadius: 3, padding: '4px 8px', color: 'var(--ink)',
      opacity: f.readOnly ? 0.5 : 1,
    }
    let control: ReactNode
    if (f.type === 'boolean') {
      control = (
        <input type="checkbox" checked={val === 'true'} disabled={f.readOnly}
          onChange={e => setEdit(k, e.target.checked ? 'true' : 'false')} />
      )
    } else if (f.type === 'list') {
      control = (
        <textarea value={val} disabled={f.readOnly} rows={Math.min(6, Math.max(2, val.split('\n').length))}
          onChange={e => setEdit(k, e.target.value)}
          style={{ ...inputStyle, resize: 'vertical', fontFamily: 'var(--font-mono)' }}
          placeholder="um por linha" />
      )
    } else {
      control = (
        <input
          type={f.type === 'secret' ? 'password' : f.type === 'number' ? 'number' : 'text'}
          value={val} disabled={f.readOnly} onChange={e => setEdit(k, e.target.value)}
          style={inputStyle} autoComplete="off" />
      )
    }
    return (
      <div key={k} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 8 }}>
        <label style={labelStyle}>{f.key}{f.readOnly ? ' (via Sync)' : ''}</label>
        {control}
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '20px 24px', gap: 8, overflowY: 'auto' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 18, color: 'var(--ink)' }}>
          Configurações — todas as chaves
        </span>
        {err && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#8B3A2A' }}>{err}</span>}
      </div>
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', opacity: 0.7, margin: '0 0 8px' }}>
        Editor completo do <code>ecosystem.json</code> desta máquina (config não é sincronizada entre máquinas).
        Estado de runtime e caminhos auto-gerados ficam ocultos.
      </p>

      {sections.map(s => (
        <Card key={s.section || '__top__'}>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)',
            letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 10,
          }}>
            {SECTION_LABELS[s.section] ?? s.section}
          </div>
          {s.fields.map(renderField)}
        </Card>
      ))}

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', position: 'sticky', bottom: 0, paddingTop: 6 }}>
        <button onClick={handleSave} disabled={saving} style={{
          fontFamily: 'var(--font-mono)', fontSize: 12, padding: '5px 14px',
          background: 'var(--accent)', color: 'var(--paper-dark)', border: 'none',
          borderRadius: 4, cursor: saving ? 'default' : 'pointer', opacity: saving ? 0.5 : 1,
        }}>{saving ? 'salvando…' : 'Salvar'}</button>
        {savedMsg && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#4A6741' }}>{savedMsg}</span>}
      </div>
    </div>
  )
}
