import React, { useState, useEffect, useCallback } from 'react'
import { Modal } from '../UI/Modal'
import { Project, ProjectProperty, PropOption, PropType } from '../../types'
import { useAppStore } from '../../store/useAppStore'
import { fromIpc } from '../../types/errors'

const db = () => (window as any).db

const PROP_TYPE_LABELS: Record<PropType, string> = {
  text:         'Texto',
  number:       'Número',
  select:       'Seleção',
  multi_select: 'Multi-sel.',
  date:         'Data',
  checkbox:     'Checkbox',
  url:          'URL',
  color:        'Cor',
}

const PROP_TYPE_ICONS: Record<PropType, string> = {
  text:         '𝐓',
  number:       '#',
  select:       '◉',
  multi_select: '◎',
  date:         '☽',
  checkbox:     '☑',
  url:          '↗',
  color:        '⬤',
}

interface Props {
  project:   Project
  dark:      boolean
  onClose:   () => void
  onChanged: () => void
}

export const ManagePropertiesModal: React.FC<Props> = ({
  project, dark, onClose, onChanged,
}) => {
  const { projectProperties, loadProperties, pushToast } = useAppStore()

  const color  = project.color ?? '#8B7355'
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const bg     = dark ? '#1A1610' : '#F5F0E8'

  const [options,       setOptions]       = useState<Record<number, PropOption[]>>({})
  const [expanded,      setExpanded]      = useState<Set<number>>(new Set())
  const [editingName,   setEditingName]   = useState<number | null>(null)
  const [nameVal,       setNameVal]       = useState('')

  // New property
  const [newPropName,   setNewPropName]   = useState('')
  const [newPropType,   setNewPropType]   = useState<PropType>('text')
  const [addingProp,    setAddingProp]    = useState(false)

  // New option
  const [addingOptFor,  setAddingOptFor]  = useState<number | null>(null)
  const [newOptLabel,   setNewOptLabel]   = useState('')
  const [newOptColor,   setNewOptColor]   = useState('#8B7355')

  const loadOptions = useCallback(async (propId: number) => {
    const result = await fromIpc<PropOption[]>(() => db().properties.getOptions(propId), 'getOptions')
    result.match(
      data => setOptions(prev => ({ ...prev, [propId]: data })),
      _e   => {},
    )
  }, [])

  // Pre-carregar opções de todos os select/multi_select ao abrir
  useEffect(() => {
    projectProperties
      .filter(p => p.prop_type === 'select' || p.prop_type === 'multi_select')
      .forEach(p => loadOptions(p.id))
  }, [projectProperties, loadOptions])

  const toggleExpand = async (propId: number) => {
    const next = new Set(expanded)
    if (next.has(propId)) {
      next.delete(propId)
    } else {
      next.add(propId)
      if (!options[propId]) await loadOptions(propId)
    }
    setExpanded(next)
  }

  const saveName = async (prop: ProjectProperty) => {
    const n = nameVal.trim()
    if (n && n !== prop.name) {
      const result = await fromIpc<unknown>(
        () => db().properties.update({ id: prop.id, name: n, prop_type: prop.prop_type }),
        'updateProperty',
      )
      if (result.isErr()) {
        pushToast({ kind: 'error', title: 'Erro ao renomear propriedade', detail: result.error.message })
        setEditingName(null)
        return
      }
      await loadProperties(project.id)
      onChanged()
    }
    setEditingName(null)
  }

  const deleteProp = async (prop: ProjectProperty) => {
    if (!window.confirm(`Excluir propriedade "${prop.name}"? Todos os valores serão perdidos.`)) return
    const result = await fromIpc<unknown>(() => db().properties.delete(prop.id), 'deleteProperty')
    if (result.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao excluir propriedade', detail: result.error.message })
      return
    }
    await loadProperties(project.id)
    onChanged()
  }

  const addProp = async () => {
    const n = newPropName.trim()
    if (!n) return
    setAddingProp(true)
    const key = n.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '') || `prop_${Date.now()}`
    const result = await fromIpc<unknown>(
      () => db().properties.create({ project_id: project.id, name: n, prop_key: key, prop_type: newPropType }),
      'createProperty',
    )
    setAddingProp(false)
    if (result.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao criar propriedade', detail: result.error.message })
      return
    }
    await loadProperties(project.id)
    onChanged()
    setNewPropName('')
  }

  const addOption = async (propId: number) => {
    if (!newOptLabel.trim()) return
    const result = await fromIpc<unknown>(
      () => db().properties.createOption({ property_id: propId, label: newOptLabel.trim(), color: newOptColor }),
      'createOption',
    )
    if (result.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao criar opção', detail: result.error.message })
      return
    }
    await loadOptions(propId)
    setNewOptLabel('')
    setNewOptColor('#8B7355')
    setAddingOptFor(null)
  }

  const deleteOption = async (propId: number, optId: number) => {
    const result = await fromIpc<unknown>(() => db().properties.deleteOption(optId), 'deleteOption')
    if (result.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao excluir opção', detail: result.error.message })
      return
    }
    await loadOptions(propId)
  }

  const rowHover = (e: React.MouseEvent<HTMLDivElement>, on: boolean) => {
    e.currentTarget.style.background = on
      ? (dark ? 'rgba(232,223,200,0.05)' : 'rgba(44,36,22,0.04)')
      : 'transparent'
  }

  return (
    <Modal title="Propriedades das Páginas" onClose={onClose} dark={dark} width={540}>
      <div style={{ maxHeight: 400, overflowY: 'auto', marginBottom: 4 }}>
        {projectProperties.length === 0 ? (
          <p style={{ color: ink2, fontSize: 12, fontStyle: 'italic', padding: '8px 0' }}>
            Nenhuma propriedade configurada.
          </p>
        ) : (
          projectProperties.map(prop => (
            <div key={prop.id}>
              {/* Prop row */}
              <div
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '5px 6px', borderRadius: 2, transition: 'background 80ms',
                }}
                onMouseEnter={e => rowHover(e, editingName !== prop.id)}
                onMouseLeave={e => rowHover(e, false)}
              >
                <span style={{ fontSize: 11, color: ink2, width: 16, textAlign: 'center', flexShrink: 0 }}>
                  {PROP_TYPE_ICONS[prop.prop_type]}
                </span>

                {editingName === prop.id ? (
                  <input
                    autoFocus
                    value={nameVal}
                    onChange={e => setNameVal(e.target.value)}
                    onBlur={() => saveName(prop)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') saveName(prop)
                      if (e.key === 'Escape') setEditingName(null)
                    }}
                    style={{
                      flex: 1, background: 'transparent', border: 'none',
                      borderBottom: `1px solid ${border}`, outline: 'none',
                      fontFamily: 'var(--font-mono)', fontSize: 12, color: ink, padding: '1px 2px',
                    }}
                  />
                ) : (
                  <span
                    style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: 12, color: ink, cursor: 'pointer' }}
                    onClick={() => { setEditingName(prop.id); setNameVal(prop.name) }}
                    title="Clique para renomear"
                  >
                    {prop.name}
                  </span>
                )}

                <span style={{
                  fontSize: 9, fontFamily: 'var(--font-mono)', letterSpacing: '0.04em',
                  color: ink2, border: `1px solid ${border}`, borderRadius: 2, padding: '1px 5px',
                  flexShrink: 0,
                }}>
                  {PROP_TYPE_LABELS[prop.prop_type]}
                </span>

                {(prop.prop_type === 'select' || prop.prop_type === 'multi_select') && (
                  <button
                    className="btn btn-ghost btn-sm"
                    style={{ color: ink2, fontSize: 10, padding: '1px 6px', flexShrink: 0 }}
                    onClick={() => toggleExpand(prop.id)}
                  >
                    {expanded.has(prop.id) ? '▲' : '▼'} {options[prop.id]?.length ?? 0} opções
                  </button>
                )}

                <button
                  className="btn btn-ghost btn-sm"
                  style={{ color: dark ? '#8A4A3A' : '#9B3A2A', padding: '1px 6px', fontSize: 13, flexShrink: 0 }}
                  onClick={() => deleteProp(prop)}
                  title="Excluir propriedade"
                >
                  ×
                </button>
              </div>

              {/* Options editor */}
              {expanded.has(prop.id) && (
                <div style={{
                  marginLeft: 24, marginTop: 2, marginBottom: 6,
                  padding: '6px 10px',
                  border: `1px solid ${border}`, borderRadius: 2,
                  background: bg,
                }}>
                  {(options[prop.id] ?? []).map(opt => (
                    <div key={opt.id} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '3px 0' }}>
                      <span style={{
                        width: 10, height: 10, borderRadius: '50%',
                        background: opt.color ?? border, flexShrink: 0,
                      }} />
                      <span style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: 11, color: ink }}>
                        {opt.label}
                      </span>
                      <button
                        className="btn btn-ghost btn-sm"
                        style={{ color: dark ? '#8A4A3A' : '#9B3A2A', padding: '0 5px', fontSize: 12 }}
                        onClick={() => deleteOption(prop.id, opt.id)}
                      >
                        ×
                      </button>
                    </div>
                  ))}

                  {addingOptFor === prop.id ? (
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 6 }}>
                      <input
                        type="color"
                        value={newOptColor}
                        onChange={e => setNewOptColor(e.target.value)}
                        style={{ width: 24, height: 22, border: 'none', padding: 0, background: 'transparent', cursor: 'pointer', flexShrink: 0 }}
                      />
                      <input
                        autoFocus
                        placeholder="Rótulo da opção..."
                        value={newOptLabel}
                        onChange={e => setNewOptLabel(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter')  addOption(prop.id)
                          if (e.key === 'Escape') { setAddingOptFor(null); setNewOptLabel('') }
                        }}
                        style={{
                          flex: 1, fontFamily: 'var(--font-mono)', fontSize: 11,
                          background: 'transparent', border: 'none',
                          borderBottom: `1px solid ${border}`, outline: 'none',
                          color: ink, padding: '1px 2px',
                        }}
                      />
                      <button className="btn btn-sm" style={{ borderColor: color, color }} onClick={() => addOption(prop.id)}>✓</button>
                      <button className="btn btn-ghost btn-sm" style={{ color: ink2 }} onClick={() => { setAddingOptFor(null); setNewOptLabel('') }}>✕</button>
                    </div>
                  ) : (
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ color: ink2, fontSize: 10, marginTop: (options[prop.id]?.length ?? 0) > 0 ? 6 : 0 }}
                      onClick={() => { setAddingOptFor(prop.id); setNewOptLabel(''); setNewOptColor('#8B7355') }}
                    >
                      + opção
                    </button>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Add property */}
      <div style={{
        paddingTop: 12, borderTop: `1px solid ${border}`,
        display: 'flex', gap: 8, alignItems: 'flex-end',
      }}>
        <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
          <label className="form-label" style={{ color: ink2 }}>Nova propriedade</label>
          <input
            className="input"
            placeholder="Nome..."
            value={newPropName}
            onChange={e => setNewPropName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addProp()}
          />
        </div>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label" style={{ color: ink2 }}>Tipo</label>
          <select
            className="input"
            value={newPropType}
            onChange={e => setNewPropType(e.target.value as PropType)}
            style={{ minWidth: 110 }}
          >
            {(Object.keys(PROP_TYPE_LABELS) as PropType[]).map(t => (
              <option key={t} value={t}>{PROP_TYPE_LABELS[t]}</option>
            ))}
          </select>
        </div>
        <button
          className="btn btn-primary"
          disabled={!newPropName.trim() || addingProp}
          onClick={addProp}
          style={{ background: color, borderColor: color }}
        >
          + Adicionar
        </button>
      </div>

      <div className="modal-footer" style={{ borderColor: border, padding: '12px 0 0', marginTop: 12 }}>
        <button
          className="btn btn-primary"
          onClick={onClose}
          style={{ background: color, borderColor: color }}
        >
          Fechar
        </button>
      </div>
    </Modal>
  )
}
