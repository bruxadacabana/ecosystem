import React, { useState } from 'react'
import { Modal } from '../UI/Modal'
import { Project, ProjectProperty } from '../../types'
import { useAppStore } from '../../store/useAppStore'
import { fromIpc } from '../../types/errors'

const db = () => (window as any).db

interface Props {
  project:    Project
  properties: ProjectProperty[]
  dark:       boolean
  onClose:    () => void
  onCreated:  (viewId: number) => void
}

type ViewType = 'table' | 'kanban' | 'list' | 'calendar' | 'gallery' | 'timeline'

const VIEW_OPTIONS: { type: ViewType; label: string; icon: string }[] = [
  { type: 'table',    label: 'Tabela',     icon: '☰' },
  { type: 'kanban',   label: 'Kanban',     icon: '☷' },
  { type: 'list',     label: 'Lista',      icon: '≡' },
  { type: 'calendar', label: 'Calendário', icon: '☽' },
  { type: 'timeline', label: 'Linha Tempo',icon: '⟶' },
  { type: 'gallery',  label: 'Galeria',    icon: '⊞' },
]

export const NewViewModal: React.FC<Props> = ({
  project, properties, dark, onClose, onCreated,
}) => {
  const { loadViews } = useAppStore()
  const [name,        setName]        = useState('')
  const [viewType,    setViewType]    = useState<ViewType>('table')
  const [groupById,   setGroupById]   = useState<number | ''>('')
  const [datePropId,  setDatePropId]  = useState<number | ''>('')
  const [submitting,  setSubmitting]  = useState(false)
  const [error,       setError]       = useState('')

  const color  = project.color ?? '#8B7355'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'

  const selectProps = properties.filter(p => p.prop_type === 'select')
  const dateProps   = properties.filter(p => p.prop_type === 'date')
  const needsDate   = viewType === 'calendar' || viewType === 'timeline'

  const handleSubmit = async () => {
    const n = name.trim()
    if (!n) { setError('O nome da vista é obrigatório.'); return }
    setSubmitting(true)
    setError('')
    const result = await fromIpc<{ id: number }>(
      () => db().views.create({
        project_id:           project.id,
        name:                 n,
        view_type:            viewType,
        group_by_property_id: viewType === 'kanban' && groupById ? Number(groupById) : null,
        date_property_id:     needsDate && datePropId ? Number(datePropId) : null,
      }),
      'createView',
    )
    setSubmitting(false)
    result.match(
      async data => { await loadViews(project.id); onCreated(data.id); onClose() },
      e           => setError(e.message),
    )
  }

  return (
    <Modal title="Nova Vista" onClose={onClose} dark={dark} width={420}>
      <div className="form-group" style={{ marginBottom: 14 }}>
        <label className="form-label" style={{ color: ink2 }}>Nome *</label>
        <input
          className="input"
          placeholder="Ex.: Kanban principal, Tabela geral..."
          value={name}
          onChange={e => { setName(e.target.value); setError('') }}
          autoFocus
          onKeyDown={e => e.key === 'Enter' && handleSubmit()}
        />
      </div>

      <div className="form-group" style={{ marginBottom: (viewType === 'kanban' && selectProps.length > 0) || (needsDate && dateProps.length > 0) ? 14 : 0 }}>
        <label className="form-label" style={{ color: ink2 }}>Tipo</label>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {VIEW_OPTIONS.map(opt => (
            <button
              key={opt.type}
              className="btn btn-sm"
              onClick={() => setViewType(opt.type)}
              style={{
                borderColor: viewType === opt.type ? color : border,
                color:       viewType === opt.type ? color : ink2,
                background:  viewType === opt.type ? color + '18' : 'transparent',
                display: 'flex', alignItems: 'center', gap: 4,
              }}
            >
              <span style={{ fontSize: 12 }}>{opt.icon}</span>
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {viewType === 'kanban' && selectProps.length > 0 && (
        <div className="form-group">
          <label className="form-label" style={{ color: ink2 }}>Agrupar por</label>
          <select
            className="input"
            value={groupById}
            onChange={e => setGroupById(e.target.value as any)}
          >
            <option value="">— Nenhuma —</option>
            {selectProps.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      )}

      {needsDate && dateProps.length > 0 && (
        <div className="form-group">
          <label className="form-label" style={{ color: ink2 }}>Propriedade de data</label>
          <select
            className="input"
            value={datePropId}
            onChange={e => setDatePropId(e.target.value as any)}
          >
            <option value="">— Nenhuma —</option>
            {dateProps.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      )}

      {error && <p style={{ color: '#8B3A2A', fontSize: 12, marginBottom: 8 }}>{error}</p>}

      <div className="modal-footer" style={{ borderColor: border, padding: '12px 0 0' }}>
        <button className="btn" onClick={onClose}>Cancelar</button>
        <button
          className="btn btn-primary"
          disabled={!name.trim() || submitting}
          onClick={handleSubmit}
          style={{ background: color, borderColor: color }}
        >
          {submitting ? 'Criando...' : 'Criar vista'}
        </button>
      </div>
    </Modal>
  )
}
