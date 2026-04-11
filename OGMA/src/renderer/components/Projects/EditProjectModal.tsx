import React, { useState } from 'react'
import { Modal } from '../UI/Modal'
import { IconPicker } from '../UI/IconPicker'
import { Project, PROJECT_TYPE_LABELS, PROJECT_COLORS, SUBCATEGORIES } from '../../types'
import { useAppStore } from '../../store/useAppStore'

interface Props {
  project: Project
  onClose: () => void
  onDeleted?: () => void
}

export const EditProjectModal: React.FC<Props> = ({ project, onClose, onDeleted }) => {
  const { dark, updateProject, deleteProject } = useAppStore()

  const [name,        setName]        = useState(project.name)
  const [description, setDesc]        = useState(project.description ?? '')
  const [institution, setInstitution] = useState(project.institution ?? '')
  const [icon,        setIcon]        = useState(project.icon ?? '✦')
  const [color,       setColor]       = useState(project.color ?? PROJECT_COLORS[0])
  const [subcategory, setSub]         = useState(project.subcategory ?? '')
  const [status,      setStatus]      = useState(project.status)
  const [submitting,  setSubmit] = useState(false)
  const [confirmDel,  setConfirmDel] = useState(false)
  const [error,       setError]  = useState('')

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'

  const subs = SUBCATEGORIES[project.project_type] ?? []

  const handleSave = async () => {
    if (!name.trim()) { setError('Nome é obrigatório.'); return }
    setSubmit(true)
    setError('')
    const result = await updateProject({
      ...project,
      name: name.trim(),
      description: description.trim() || null,
      institution: project.project_type === 'academic' ? (institution.trim() || null) : null,
      icon, color, subcategory: subcategory || null,
      status,
    })
    setSubmit(false)
    if (result.isErr()) { setError(result.error.message); return }
    onClose()
  }

  const handleDelete = async () => {
    const result = await deleteProject(project.id)
    if (result.isErr()) { setError(result.error.message); return }
    onDeleted?.()
    onClose()
  }

  return (
    <Modal title={`Editar — ${project.name}`} onClose={onClose} dark={dark} width={500}>

      <div className="form-row" style={{ marginBottom: 14 }}>
        <div className="form-group" style={{ flex: 0, minWidth: 60 }}>
          <label className="form-label" style={{ color: ink2 }}>Ícone</label>
          <div style={{ paddingTop: 4 }}>
            <IconPicker value={icon} onChange={setIcon} dark={dark} size={26} suggestFor={name} />
          </div>
        </div>
        <div className="form-group" style={{ flex: 1 }}>
          <label className="form-label" style={{ color: ink2 }}>Nome *</label>
          <input className="input" value={name}
            onChange={e => { setName(e.target.value); setError('') }} autoFocus />
        </div>
      </div>

      <div className="form-group" style={{ marginBottom: 14 }}>
        <label className="form-label" style={{ color: ink2 }}>Descrição</label>
        <textarea className="input" value={description}
          onChange={e => setDesc(e.target.value)} rows={2}
          style={{ resize: 'none' }} placeholder="Opcional..." />
      </div>

      {project.project_type === 'academic' && (
        <div className="form-group" style={{ marginBottom: 14 }}>
          <label className="form-label" style={{ color: ink2 }}>Instituição</label>
          <input className="input" value={institution}
            onChange={e => setInstitution(e.target.value)}
            placeholder="Ex: USP, UNICAMP, IFSP..." />
        </div>
      )}

      {subs.length > 0 && (
        <div className="form-group" style={{ marginBottom: 14 }}>
          <label className="form-label" style={{ color: ink2 }}>Subcategoria</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {subs.map(s => (
              <button key={s}
                style={{
                  fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.08em',
                  padding: '4px 10px', border: `1px solid ${subcategory === s ? color : border}`,
                  borderRadius: 20, cursor: 'pointer',
                  background: subcategory === s ? color + '22' : 'transparent',
                  color: subcategory === s ? color : ink2,
                }}
                onClick={() => setSub(s)}>{s}</button>
            ))}
          </div>
        </div>
      )}

      <div className="form-row" style={{ marginBottom: 14 }}>
        <div className="form-group">
          <label className="form-label" style={{ color: ink2 }}>Cor</label>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {PROJECT_COLORS.map(c => (
              <button key={c} onClick={() => setColor(c)} style={{
                width: 22, height: 22, borderRadius: '50%', background: c, border: 'none',
                cursor: 'pointer', outline: color === c ? `3px solid ${c}` : 'none',
                outlineOffset: 2, transform: color === c ? 'scale(1.1)' : 'scale(1)',
                transition: 'transform 120ms',
              }} />
            ))}
          </div>
        </div>
        <div className="form-group">
          <label className="form-label" style={{ color: ink2 }}>Status</label>
          <select className="input" value={status}
            onChange={e => setStatus(e.target.value as any)}>
            <option value="active">● Ativo</option>
            <option value="paused">◌ Pausado</option>
            <option value="completed">✓ Concluído</option>
            <option value="archived">◻ Arquivado</option>
          </select>
        </div>
      </div>

      {error && <p style={{ color: '#8B3A2A', fontSize: 12, marginBottom: 8 }}>{error}</p>}

      {/* Zona de perigo */}
      {confirmDel ? (
        <div style={{
          padding: '10px 12px', border: `1px solid #8B3A2A`,
          borderRadius: 2, background: '#8B3A2a11', marginBottom: 8,
        }}>
          <p style={{ fontSize: 12, color: '#8B3A2A', marginBottom: 8 }}>
            Tem certeza? Esta ação não pode ser desfeita. Todas as páginas do projeto serão removidas.
          </p>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-danger btn-sm" onClick={handleDelete}>
              Sim, excluir
            </button>
            <button className="btn btn-sm" onClick={() => setConfirmDel(false)}>
              Cancelar
            </button>
          </div>
        </div>
      ) : (
        <button className="btn btn-ghost btn-sm" style={{ color: '#8B3A2A', marginBottom: 4 }}
          onClick={() => setConfirmDel(true)}>
          🗑 Excluir projeto
        </button>
      )}

      <div className="modal-footer" style={{ borderColor: border, padding: '12px 0 0' }}>
        <button className="btn" onClick={onClose}>Cancelar</button>
        <button className="btn btn-primary" disabled={submitting} onClick={handleSave}
          style={{ background: color, borderColor: color }}>
          {submitting ? 'Salvando...' : 'Salvar alterações'}
        </button>
      </div>
    </Modal>
  )
}
