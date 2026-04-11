import React, { useState, useEffect } from 'react'
import { Modal } from '../UI/Modal'
import { IconPicker } from '../UI/IconPicker'
import { Project } from '../../types'
import { useAppStore } from '../../store/useAppStore'
import { fromIpc } from '../../types/errors'
import './NewPageModal.css'

const db = () => (window as any).db

interface Property {
  id: number
  name: string
  prop_key: string
  prop_type: string
  is_required: number
}
interface PropOption { id: number; label: string; color?: string }
interface Tag { id: number; name: string; color?: string }
interface PageItem { id: number; title: string; icon?: string; parent_id?: number | null }

const COVER_COLORS = [
  '#8B7355','#5B7A9D','#7A6B8A','#5B8A6B','#8A5B5B',
  '#B8860B','#2C7873','#6A4C93','#1A535C','#C0392B',
  '#16A085','#8E44AD','#2980B9','#27AE60','#D35400',
  '#1C2833','#4A4A4A','#F5CBA7','#AED6F1','#A9DFBF',
]

function propPayload(prop: Property, value: any): Record<string, any> | null {
  if (value === '' || value === null || value === undefined) return null
  switch (prop.prop_type) {
    case 'number':       return { value_num:  Number(value) }
    case 'checkbox':     return { value_bool: value ? 1 : 0 }
    case 'date':         return { value_date: String(value) }
    case 'multi_select': return { value_json: Array.isArray(value) ? JSON.stringify(value) : value }
    default:             return { value_text: String(value) }  // text, url, select
  }
}

interface Props {
  project:    Project
  onClose:    () => void
  onCreated?: (pageId: number) => void
}

export const NewPageModal: React.FC<Props> = ({ project, onClose, onCreated }) => {
  const { dark, loadPages, pushToast } = useAppStore()

  // basic fields
  const [title,      setTitle]      = useState('')
  const [icon,       setIcon]        = useState('📄')
  const [coverColor, setCoverColor]  = useState<string | null>(null)
  const [parentId,   setParentId]    = useState<number | ''>('')
  const [submitting, setSubmitting]  = useState(false)
  const [error,      setError]       = useState('')

  // loaded data
  const [pages,       setPages]       = useState<PageItem[]>([])
  const [properties,  setProperties]  = useState<Property[]>([])
  const [propOptions, setPropOptions] = useState<Record<number, PropOption[]>>({})
  const [tags,        setTags]        = useState<Tag[]>([])
  const [loading,     setLoading]     = useState(true)

  // dynamic values: prop_id → raw value
  const [propValues, setPropValues] = useState<Record<number, any>>({})
  const [selTags,    setSelTags]    = useState<number[]>([])

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const ink3   = dark ? '#5A4A32' : '#BDB0A0'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const accent = dark ? '#D4A820' : '#b8860b'
  const color  = project.color ?? '#8B7355'

  // Load properties, pages and tags on mount
  useEffect(() => {
    const load = async () => {
      const [pagesR, propsR, tagsR] = await Promise.all([
        fromIpc<PageItem[]>(() => db().pages.list(project.id), 'listPages'),
        fromIpc<Property[]>(() => db().projects.getProperties(project.id), 'getProps'),
        fromIpc<Tag[]>(() => db().tags.list(), 'listTags'),
      ])
      if (pagesR.isOk()) setPages(pagesR.value)
      if (tagsR.isOk())  setTags(tagsR.value)
      if (propsR.isOk()) {
        setProperties(propsR.value)
        // load options for select-type and multi_select-type properties
        const selectProps = propsR.value.filter(p => p.prop_type === 'select' || p.prop_type === 'multi_select')
        if (selectProps.length > 0) {
          const results = await Promise.all(
            selectProps.map(p =>
              fromIpc<PropOption[]>(() => db().properties.getOptions(p.id), 'getOptions')
            )
          )
          const opts: Record<number, PropOption[]> = {}
          selectProps.forEach((p, i) => {
            const r = results[i]
            if (r.isOk()) opts[p.id] = r.value
          })
          setPropOptions(opts)
        }
      }
      setLoading(false)
    }
    load()
  }, [project.id])

  const handleSubmit = async () => {
    if (!title.trim()) { setError('O título é obrigatório.'); return }
    setSubmitting(true)
    setError('')

    const result = await fromIpc<{ id: number }>(
      () => db().pages.create({
        project_id:  project.id,
        title:       title.trim(),
        icon,
        cover_color: coverColor ?? null,
        parent_id:   parentId !== '' ? parentId : null,
        sort_order:  0,
      }),
      'createPage',
    )

    if (result.isErr()) {
      setSubmitting(false)
      setError(result.error.message)
      return
    }

    const pageId = result.value.id

    // Set property values
    const propCalls = properties
      .map(p => {
        const val = propValues[p.id]
        const payload = propPayload(p, val)
        if (!payload) return null
        return fromIpc(() => db().pages.setPropValue({
          page_id: pageId, property_id: p.id, ...payload,
        }), 'setPropValue')
      })
      .filter(Boolean) as unknown as Promise<any>[]

    // Assign tags
    const tagCalls = selTags.map(tagId =>
      fromIpc(() => db().tags.assign(pageId, tagId), 'assignTag')
    )

    await Promise.all([...propCalls, ...tagCalls])

    setSubmitting(false)
    await loadPages(project.id)
    onCreated?.(pageId)
    onClose()
  }

  const toggleTag = (id: number) =>
    setSelTags(prev => prev.includes(id) ? prev.filter(t => t !== id) : [...prev, id])

  const fieldStyle: React.CSSProperties = {
    width: '100%', background: cardBg, border: `1px solid ${border}`,
    borderRadius: 2, padding: '5px 8px', fontSize: 12, color: ink,
    outline: 'none', fontFamily: 'var(--font-mono)', boxSizing: 'border-box',
  }

  const labelStyle: React.CSSProperties = {
    fontSize: 10, letterSpacing: '0.08em', color: ink2,
    textTransform: 'uppercase', fontFamily: 'var(--font-mono)',
    display: 'block', marginBottom: 4,
  }

  const sectionStyle: React.CSSProperties = {
    borderTop: `1px solid ${border}`, paddingTop: 12, marginTop: 12,
  }

  return (
    <Modal title="Nova Página" onClose={onClose} dark={dark} width={580}>
      {/* ── Título + ícone ── */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', marginBottom: 12 }}>
        <div>
          <label style={labelStyle}>Ícone</label>
          <div style={{ paddingTop: 2 }}>
            <IconPicker value={icon} onChange={setIcon} dark={dark} size={26} suggestFor={title} />
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Título *</label>
          <input
            style={fieldStyle}
            placeholder="Nome da página..."
            value={title}
            onChange={e => { setTitle(e.target.value); setError('') }}
            autoFocus
            onKeyDown={e => e.key === 'Enter' && !submitting && handleSubmit()}
          />
        </div>
      </div>

      {error && (
        <p style={{ color: '#8B3A2A', fontSize: 12, marginBottom: 8 }}>{error}</p>
      )}

      {/* ── Cor de capa ── */}
      <div style={sectionStyle}>
        <label style={labelStyle}>Cor de capa</label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
          <button
            type="button"
            title="Sem cor"
            onClick={() => setCoverColor(null)}
            style={{
              width: 20, height: 20, borderRadius: 2, border: `2px solid ${border}`,
              background: 'transparent', cursor: 'pointer', position: 'relative',
              outline: coverColor === null ? `2px solid ${accent}` : 'none',
              outlineOffset: 1,
            }}
          >
            <span style={{ fontSize: 9, color: ink3, lineHeight: '16px' }}>✕</span>
          </button>
          {COVER_COLORS.map(c => (
            <button
              key={c} type="button" title={c}
              onClick={() => setCoverColor(c)}
              style={{
                width: 20, height: 20, borderRadius: 2,
                background: c, border: `1px solid ${border}`,
                cursor: 'pointer',
                outline: coverColor === c ? `2px solid ${accent}` : 'none',
                outlineOffset: 1,
              }}
            />
          ))}
        </div>
      </div>

      {/* ── Página pai ── */}
      <div style={sectionStyle}>
        <label style={labelStyle}>Página pai (opcional)</label>
        <select
          value={parentId}
          onChange={e => setParentId(e.target.value === '' ? '' : Number(e.target.value))}
          style={{ ...fieldStyle, cursor: 'pointer' }}
        >
          <option value="">— nenhuma —</option>
          {pages.map(p => (
            <option key={p.id} value={p.id}>
              {p.icon ? `${p.icon} ` : ''}{p.title}
            </option>
          ))}
        </select>
      </div>

      {/* ── Propriedades do projeto ── */}
      {!loading && properties.length > 0 && (
        <div style={sectionStyle}>
          <label style={labelStyle}>Propriedades</label>
          <div style={{
            display: 'grid',
            gridTemplateColumns: properties.length === 1 ? '1fr' : '1fr 1fr',
            gap: '8px 12px',
          }}>
            {properties.map(prop => (
              <div key={prop.id}>
                <label style={{ ...labelStyle, marginBottom: 2 }}>
                  {prop.name}{prop.is_required ? ' *' : ''}
                </label>
                {prop.prop_type === 'checkbox' ? (
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={!!propValues[prop.id]}
                      onChange={e => setPropValues(prev => ({ ...prev, [prop.id]: e.target.checked }))}
                    />
                    <span style={{ fontSize: 12, color: ink2 }}>{prop.name}</span>
                  </label>
                ) : prop.prop_type === 'select' ? (
                  <select
                    value={propValues[prop.id] ?? ''}
                    onChange={e => setPropValues(prev => ({ ...prev, [prop.id]: e.target.value }))}
                    style={{ ...fieldStyle, cursor: 'pointer' }}
                  >
                    <option value="">— selecione —</option>
                    {(propOptions[prop.id] ?? []).map(opt => (
                      <option key={opt.id} value={opt.label}>{opt.label}</option>
                    ))}
                  </select>
                ) : prop.prop_type === 'multi_select' ? (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {(propOptions[prop.id] ?? []).map(opt => {
                      const sel = (propValues[prop.id] as string[] ?? []).includes(opt.label)
                      return (
                        <button key={opt.id} type="button"
                          onClick={() => {
                            const cur: string[] = propValues[prop.id] ?? []
                            const next = sel ? cur.filter(l => l !== opt.label) : [...cur, opt.label]
                            setPropValues(prev => ({ ...prev, [prop.id]: next }))
                          }}
                          style={{
                            padding: '2px 8px', borderRadius: 10, fontSize: 11,
                            fontFamily: 'var(--font-mono)', cursor: 'pointer',
                            border: `1px solid ${sel ? (opt.color ?? accent) : border}`,
                            background: sel ? (opt.color ? opt.color + '25' : accent + '20') : 'transparent',
                            color: sel ? (opt.color ?? accent) : ink2,
                          }}
                        >{opt.label}</button>
                      )
                    })}
                  </div>
                ) : prop.prop_type === 'date' ? (
                  <input
                    type="date"
                    value={propValues[prop.id] ?? ''}
                    onChange={e => setPropValues(prev => ({ ...prev, [prop.id]: e.target.value }))}
                    style={fieldStyle}
                  />
                ) : prop.prop_type === 'number' ? (
                  <input
                    type="number"
                    placeholder="0"
                    value={propValues[prop.id] ?? ''}
                    onChange={e => setPropValues(prev => ({ ...prev, [prop.id]: e.target.value }))}
                    style={fieldStyle}
                  />
                ) : (
                  <input
                    type={prop.prop_type === 'url' ? 'url' : 'text'}
                    placeholder={prop.prop_type === 'url' ? 'https://...' : `${prop.name}...`}
                    value={propValues[prop.id] ?? ''}
                    onChange={e => setPropValues(prev => ({ ...prev, [prop.id]: e.target.value }))}
                    style={fieldStyle}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Tags ── */}
      {!loading && tags.length > 0 && (
        <div style={sectionStyle}>
          <label style={labelStyle}>Tags</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {tags.map(tag => {
              const selected = selTags.includes(tag.id)
              const tagColor = tag.color ?? accent
              return (
                <button
                  key={tag.id} type="button"
                  onClick={() => toggleTag(tag.id)}
                  style={{
                    padding: '3px 9px', borderRadius: 10, fontSize: 11,
                    fontFamily: 'var(--font-mono)', cursor: 'pointer',
                    border: `1px solid ${selected ? tagColor : border}`,
                    background: selected ? tagColor + '25' : 'transparent',
                    color: selected ? tagColor : ink2,
                    transition: 'all 100ms',
                  }}
                >
                  {tag.name}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* ── Footer ── */}
      <div className="modal-footer" style={{ borderColor: border, padding: '14px 0 0', marginTop: 14 }}>
        <button className="btn" onClick={onClose}>Cancelar</button>
        <button
          className="btn btn-primary"
          disabled={!title.trim() || submitting}
          onClick={handleSubmit}
          style={{ background: color, borderColor: color }}
        >
          {submitting ? 'Criando...' : 'Criar página'}
        </button>
      </div>
    </Modal>
  )
}
