import React, { useState } from 'react'
import { Modal } from '../UI/Modal'
import { IconPicker } from '../UI/IconPicker'
import {
  ProjectType, ProjectCreateInput,
  SUBCATEGORIES, PROJECT_TYPE_LABELS,
  PROJECT_TYPE_ICONS, PROJECT_TYPE_DESCRIPTIONS,
  PROJECT_COLORS,
} from '../../types'
import { useAppStore } from '../../store/useAppStore'
import './NewProjectModal.css'

interface Props {
  onClose: () => void
  onCreated?: (id: number) => void
}

const TYPES: ProjectType[] = ['academic', 'creative', 'research', 'software', 'health', 'hobby', 'idea', 'custom']

// ── Modal principal ───────────────────────────────────────────────────────────

export const NewProjectModal: React.FC<Props> = ({ onClose, onCreated }) => {
  const { dark, createProject, loadProjects } = useAppStore()
  const [step, setStep]           = useState<'type' | 'details'>('type')
  const [selectedType, setType]   = useState<ProjectType | null>(null)
  const [name, setName]           = useState('')
  const [description, setDesc]    = useState('')
  const [icon, setIcon]           = useState('✦')
  const [color, setColor]         = useState(PROJECT_COLORS[0])
  const [subcategory, setSub]     = useState('')
  const [institution, setInstitution] = useState('')
  const [dateStart, setDateStart]     = useState('')
  const [dateEnd, setDateEnd]         = useState('')
  const [submitting, setSubmit]       = useState(false)
  const [error, setError]         = useState('')

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  // ── Step 1: Tipo ──────────────────────────────────────────────────────────

  const renderTypeStep = () => (
    <div>
      <p style={{ fontSize: 12, color: ink2, marginBottom: 16, fontStyle: 'italic' }}>
        Escolha o tipo do projeto. Ele define as propriedades e vistas padrão criadas automaticamente.
      </p>
      <div className="type-grid">
        {TYPES.map(t => (
          <button
            key={t}
            className={`type-card${selectedType === t ? ' selected' : ''}`}
            style={{
              background:  selectedType === t ? color + '22' : cardBg,
              borderColor: selectedType === t ? color : border,
              color: ink,
            }}
            onClick={() => {
              setType(t)
              setSub(SUBCATEGORIES[t][0] ?? '')
              if (t !== 'custom') setIcon(PROJECT_TYPE_ICONS[t])
            }}
          >
            <span className="type-card-icon">{PROJECT_TYPE_ICONS[t]}</span>
            <span className="type-card-label">{PROJECT_TYPE_LABELS[t]}</span>
            <span className="type-card-desc" style={{ color: ink2 }}>
              {PROJECT_TYPE_DESCRIPTIONS[t]}
            </span>
          </button>
        ))}
      </div>

      <div className="modal-footer" style={{ borderColor: border, marginTop: 20, padding: '12px 0 0' }}>
        <button className="btn" onClick={onClose}>Cancelar</button>
        <button
          className="btn btn-primary"
          disabled={!selectedType}
          onClick={() => setStep('details')}
        >
          Continuar →
        </button>
      </div>
    </div>
  )

  // ── Step 2: Detalhes ──────────────────────────────────────────────────────

  const handleSubmit = async () => {
    if (!name.trim()) { setError('O nome do projeto é obrigatório.'); return }
    setSubmit(true)
    setError('')

    const { workspace } = useAppStore.getState()
    const wsId = workspace?.id ?? 1

    const input: ProjectCreateInput = {
      workspace_id: wsId,
      name:         name.trim(),
      description:  description.trim() || undefined,
      icon,
      color,
      project_type: selectedType!,
      subcategory:  subcategory || undefined,
      institution:  selectedType === 'academic' ? (institution.trim() || undefined) : undefined,
      status:       'active',
      date_start:   dateStart || undefined,
      date_end:     dateEnd   || undefined,
      sort_order:   0,
    }

    const result = await createProject(input as any)
    await loadProjects()
    setSubmit(false)

    if (result.isOk()) {
      onCreated?.(result.value.id)
      onClose()
    } else {
      setError(result.error.message)
    }
  }

  const renderDetailsStep = () => {
    const subs = selectedType ? SUBCATEGORIES[selectedType] : []

    return (
      <div>
        {/* Nome e ícone */}
        <div className="form-row" style={{ marginBottom: 14 }}>
          <div className="form-group" style={{ flex: 0, minWidth: 60 }}>
            <label className="form-label" style={{ color: ink2 }}>Ícone</label>
            <div style={{ paddingTop: 4 }}>
              <IconPicker value={icon} onChange={setIcon} dark={dark} size={26} suggestFor={name} />
            </div>
          </div>
          <div className="form-group" style={{ flex: 1 }}>
            <label className="form-label" style={{ color: ink2 }}>Nome *</label>
            <input
              className="input"
              placeholder="Nome do projeto..."
              value={name}
              onChange={e => { setName(e.target.value); setError('') }}
              autoFocus
            />
          </div>
        </div>

        {/* Descrição */}
        <div className="form-group">
          <label className="form-label" style={{ color: ink2 }}>Descrição</label>
          <textarea
            className="input"
            placeholder="Opcional..."
            value={description}
            onChange={e => setDesc(e.target.value)}
            rows={2}
            style={{ resize: 'none', lineHeight: 1.5 }}
          />
        </div>

        {/* Subcategoria */}
        {subs.length > 0 && (
          <div className="form-group">
            <label className="form-label" style={{ color: ink2 }}>Subcategoria</label>
            <div className="sub-grid">
              {subs.map(s => (
                <button
                  key={s}
                  className={`sub-btn${subcategory === s ? ' selected' : ''}`}
                  style={{
                    borderColor: subcategory === s ? color : border,
                    background:  subcategory === s ? color + '22' : 'transparent',
                    color:       subcategory === s ? color : ink2,
                  }}
                  onClick={() => setSub(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Instituição (apenas acadêmico) */}
        {selectedType === 'academic' && (
          <div className="form-group">
            <label className="form-label" style={{ color: ink2 }}>Instituição</label>
            <input
              className="input"
              placeholder="Ex: USP, UNICAMP, IFSP..."
              value={institution}
              onChange={e => setInstitution(e.target.value)}
            />
          </div>
        )}

        {/* Cor */}
        <div className="form-group">
          <label className="form-label" style={{ color: ink2 }}>Cor do projeto</label>
          <div className="color-grid">
            {PROJECT_COLORS.map(c => (
              <button
                key={c}
                className={`color-dot${color === c ? ' selected' : ''}`}
                style={{ background: c, outlineColor: color === c ? c : 'transparent' }}
                onClick={() => setColor(c)}
                title={c}
              />
            ))}
          </div>
        </div>

        {/* Datas */}
        <div className="form-row">
          <div className="form-group">
            <label className="form-label" style={{ color: ink2 }}>Início</label>
            <input type="date" className="input" value={dateStart}
              onChange={e => setDateStart(e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label" style={{ color: ink2 }}>Término previsto</label>
            <input type="date" className="input" value={dateEnd}
              onChange={e => setDateEnd(e.target.value)} />
          </div>
        </div>

        {error && (
          <p style={{ color: '#8B3A2A', fontSize: 12, marginTop: 4 }}>{error}</p>
        )}

        <div className="modal-footer" style={{ borderColor: border, marginTop: 20, padding: '12px 0 0' }}>
          <button className="btn" onClick={() => setStep('type')}>← Voltar</button>
          <button
            className="btn btn-primary"
            disabled={!name.trim() || submitting}
            onClick={handleSubmit}
            style={{ background: color, borderColor: color }}
          >
            {submitting ? 'Criando...' : 'Criar projeto'}
          </button>
        </div>
      </div>
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const titles = {
    type:    'Novo Projeto — Escolha o Tipo',
    details: `Novo Projeto — ${selectedType ? PROJECT_TYPE_LABELS[selectedType] : ''}`,
  }

  return (
    <Modal
      title={titles[step]}
      onClose={onClose}
      dark={dark}
      width={step === 'type' ? 620 : 520}
      footer={null}
    >
      {step === 'type'    && renderTypeStep()}
      {step === 'details' && renderDetailsStep()}
    </Modal>
  )
}
