/* ============================================================
   AETHER — WorldbuildingView (4.3)
   Notas de worldbuilding por categoria (locais, facções, etc.)
   Layout: lista lateral agrupada por categoria + painel editor.
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import { open as openFileDialog } from '@tauri-apps/plugin-dialog'
import * as cmd from '../lib/tauri'
import type { CustomField, WorldCategory, WorldNote } from '../types'

interface WorldbuildingViewProps {
  projectId: string
  onError: (msg: string) => void
  onSuccess: (msg: string) => void
}

const CATEGORY_LABELS: Record<WorldCategory, string> = {
  location: 'Locais',
  faction: 'Facções',
  object: 'Objetos',
  concept: 'Conceitos',
  other: 'Outros',
}

const CATEGORY_ORDER: WorldCategory[] = ['location', 'faction', 'object', 'concept', 'other']

export function WorldbuildingView({ projectId, onError, onSuccess }: WorldbuildingViewProps) {
  const [notes, setNotes] = useState<WorldNote[]>([])
  const [selected, setSelected] = useState<WorldNote | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newCategory, setNewCategory] = useState<WorldCategory>('location')
  const newInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    loadNotes()
  }, [projectId])

  useEffect(() => {
    if (creating) newInputRef.current?.focus()
  }, [creating])

  async function loadNotes() {
    setLoading(true)
    const r = await cmd.listWorldNotes(projectId)
    setLoading(false)
    if (!r.ok) { onError(r.error.message); return }
    setNotes(r.data)
  }

  async function handleCreate() {
    if (!newName.trim()) { setCreating(false); return }
    const r = await cmd.createWorldNote(projectId, newName.trim(), newCategory)
    if (!r.ok) { onError(r.error.message); return }
    setNotes((prev) => [...prev, r.data].sort((a, b) => a.name.localeCompare(b.name)))
    setSelected(r.data)
    setCreating(false)
    setNewName('')
  }

  function handleNoteSaved(updated: WorldNote) {
    setSelected(updated)
    setNotes((prev) =>
      prev.map((n) => (n.id === updated.id ? updated : n))
        .sort((a, b) => a.name.localeCompare(b.name))
    )
    onSuccess(`"${updated.name}" salvo.`)
  }

  async function handleDelete(note: WorldNote) {
    const r = await cmd.deleteWorldNote(projectId, note.id)
    if (!r.ok) { onError(r.error.message); return }
    setNotes((prev) => prev.filter((n) => n.id !== note.id))
    if (selected?.id === note.id) setSelected(null)
    onSuccess(`"${note.name}" excluído.`)
  }

  const filtered = notes.filter((n) =>
    n.name.toLowerCase().includes(search.toLowerCase())
  )

  const grouped = CATEGORY_ORDER.reduce<Record<WorldCategory, WorldNote[]>>(
    (acc, cat) => { acc[cat] = filtered.filter((n) => n.category === cat); return acc },
    {} as Record<WorldCategory, WorldNote[]>
  )

  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
      {/* Lista lateral */}
      <aside style={{
        width: '220px',
        flexShrink: 0,
        borderRight: '1px solid var(--rule)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* Cabeçalho */}
        <div style={{
          padding: '10px 12px 8px',
          borderBottom: '1px solid var(--rule)',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}>
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '9px',
            textTransform: 'uppercase',
            letterSpacing: '0.14em',
            color: 'var(--ink-ghost)',
            flex: 1,
          }}>Worldbuilding</span>
          <button
            className="btn btn-ghost btn-icon"
            onClick={() => setCreating(true)}
            title="Nova nota"
            style={{ fontSize: '16px', lineHeight: 1, color: 'var(--ink-faint)', padding: '0 2px' }}
          >+</button>
        </div>

        {/* Busca */}
        <div style={{ padding: '6px 10px', borderBottom: '1px solid var(--rule)' }}>
          <input
            type="text"
            placeholder="Buscar…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              width: '100%',
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              background: 'transparent',
              border: 'none',
              outline: 'none',
              color: 'var(--ink)',
              letterSpacing: '0.04em',
            }}
          />
        </div>

        {/* Lista agrupada por categoria */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {loading && (
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--ink-ghost)', textAlign: 'center', padding: '20px 0' }}>· · ·</p>
          )}

          {creating && (
            <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--rule)', background: 'var(--paper-dark)' }}>
              <select
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value as WorldCategory)}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '10px',
                  color: 'var(--ink-ghost)',
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  width: '100%',
                  marginBottom: '4px',
                  cursor: 'pointer',
                }}
              >
                {CATEGORY_ORDER.map((cat) => (
                  <option key={cat} value={cat}>{CATEGORY_LABELS[cat]}</option>
                ))}
              </select>
              <input
                ref={newInputRef}
                type="text"
                placeholder="Nome da nota"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreate()
                  if (e.key === 'Escape') { setCreating(false); setNewName('') }
                }}
                onBlur={handleCreate}
                style={{
                  width: '100%',
                  fontFamily: 'var(--font-display)',
                  fontStyle: 'italic',
                  fontSize: '13px',
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  color: 'var(--ink)',
                }}
              />
            </div>
          )}

          {!loading && filtered.length === 0 && !creating && (
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--ink-ghost)', textAlign: 'center', padding: '20px 0', letterSpacing: '0.04em' }}>
              {search ? 'Nenhum resultado.' : 'Nenhuma nota ainda.'}
            </p>
          )}

          {CATEGORY_ORDER.map((cat) => {
            const items = grouped[cat]
            if (items.length === 0) return null
            return (
              <div key={cat}>
                <div style={{
                  padding: '5px 10px 3px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '9px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.14em',
                  color: 'var(--ink-ghost)',
                  borderBottom: '1px solid var(--rule)',
                  background: 'var(--paper-dark)',
                }}>
                  {CATEGORY_LABELS[cat]}
                </div>
                {items.map((note) => (
                  <NoteListItem
                    key={note.id}
                    note={note}
                    isSelected={selected?.id === note.id}
                    onClick={() => setSelected(note)}
                    onDelete={() => handleDelete(note)}
                  />
                ))}
              </div>
            )
          })}
        </div>
      </aside>

      {/* Painel de detalhes */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>
        {selected === null ? (
          <EmptyWorldDetail hasNotes={notes.length > 0} />
        ) : (
          <WorldNoteForm
            key={selected.id}
            projectId={projectId}
            note={selected}
            onSaved={handleNoteSaved}
            onError={onError}
          />
        )}
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  NoteListItem
// ----------------------------------------------------------

function NoteListItem({
  note, isSelected, onClick, onDelete,
}: {
  note: WorldNote
  isSelected: boolean
  onClick: () => void
  onDelete: () => void
}) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={onClick}
      style={{
        padding: '7px 10px',
        borderBottom: '1px solid transparent',
        background: isSelected ? 'var(--paper-darker)' : hovered ? 'var(--paper-dark)' : 'transparent',
        cursor: 'pointer',
        transition: 'background var(--transition)',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
      }}
    >
      <p style={{
        fontFamily: 'var(--font-display)',
        fontStyle: 'italic',
        fontSize: '13px',
        color: isSelected ? 'var(--ink)' : 'var(--ink-light)',
        margin: 0,
        flex: 1,
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
      }}>{note.name}</p>
      {hovered && (
        <button
          className="btn btn-ghost btn-icon"
          onClick={(e) => { e.stopPropagation(); onDelete() }}
          style={{ fontSize: '12px', color: 'var(--ink-ghost)', opacity: 0.6, padding: '0 2px', flexShrink: 0 }}
        >✕</button>
      )}
    </div>
  )
}

// ----------------------------------------------------------
//  EmptyWorldDetail
// ----------------------------------------------------------

function EmptyWorldDetail({ hasNotes }: { hasNotes: boolean }) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
      <p style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '20px', color: 'var(--ink-ghost)', margin: 0 }}>
        {hasNotes ? 'Selecione uma nota.' : 'Nenhuma nota ainda.'}
      </p>
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--ink-ghost)', margin: 0, letterSpacing: '0.06em' }}>
        {hasNotes ? '' : 'Clique em + para criar a primeira.'}
      </p>
    </div>
  )
}

// ----------------------------------------------------------
//  WorldNoteForm — editor de nota (4.3)
// ----------------------------------------------------------

interface WorldNoteFormProps {
  projectId: string
  note: WorldNote
  onSaved: (updated: WorldNote) => void
  onError: (msg: string) => void
}

function WorldNoteForm({ projectId, note, onSaved, onError }: WorldNoteFormProps) {
  const [name, setName] = useState(note.name)
  const [category, setCategory] = useState<WorldCategory>(note.category)
  const [description, setDescription] = useState(note.description ?? '')
  const [fields, setFields] = useState<CustomField[]>(note.fields)
  const [imagePath, setImagePath] = useState<string | null>(note.image_path)
  const [imageData, setImageData] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!imagePath) { setImageData(null); return }
    cmd.loadImage(imagePath).then((r) => {
      if (r.ok) setImageData(r.data)
    })
  }, [imagePath])

  function mark() { setDirty(true) }

  function addField() { setFields((prev) => [...prev, { label: '', value: '' }]); mark() }
  function updateField(idx: number, key: keyof CustomField, val: string) {
    setFields((prev) => prev.map((f, i) => i === idx ? { ...f, [key]: val } : f)); mark()
  }
  function removeField(idx: number) {
    setFields((prev) => prev.filter((_, i) => i !== idx)); mark()
  }

  async function handleAttachImage() {
    const selected = await openFileDialog({
      filters: [{ name: 'Imagem', extensions: ['png', 'jpg', 'jpeg', 'gif', 'webp'] }],
    })
    if (!selected || typeof selected !== 'string') return
    const prefix = `note_${note.id}`
    const r = await cmd.attachImage(projectId, prefix, selected)
    if (!r.ok) { onError(r.error.message); return }
    setImagePath(r.data); mark()
  }

  async function handleRemoveImage() {
    if (!imagePath) return
    const r = await cmd.removeImage(imagePath)
    if (!r.ok) { onError(r.error.message); return }
    setImagePath(null); setImageData(null); mark()
  }

  async function handleSave() {
    if (!name.trim()) { onError('O nome não pode ser vazio.'); return }
    setSaving(true)
    const r = await cmd.saveWorldNote(projectId, note.id, {
      name: name.trim(),
      category,
      description: description.trim() || null,
      fields: fields.filter((f) => f.label.trim()),
      imagePath,
      chapterIds: note.chapter_ids,
    })
    setSaving(false)
    if (!r.ok) { onError(r.error.message); return }
    setDirty(false)
    onSaved(r.data)
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px 40px' }}>
      {/* Categoria */}
      <div style={{ marginBottom: '14px' }}>
        <label style={labelStyle}>Categoria</label>
        <select
          value={category}
          onChange={(e) => { setCategory(e.target.value as WorldCategory); mark() }}
          style={{ ...inputStyle, cursor: 'pointer' }}
        >
          {CATEGORY_ORDER.map((cat) => (
            <option key={cat} value={cat}>{CATEGORY_LABELS[cat]}</option>
          ))}
        </select>
      </div>

      {/* Nome */}
      <div style={{ marginBottom: '20px' }}>
        <label style={labelStyle}>Nome</label>
        <input
          type="text"
          value={name}
          onChange={(e) => { setName(e.target.value); mark() }}
          style={{ ...inputStyle, fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '22px', color: 'var(--ink)' }}
          placeholder="Nome da nota"
        />
      </div>

      {/* Imagem */}
      <div style={{ marginBottom: '20px' }}>
        <label style={labelStyle}>Imagem</label>
        {imageData ? (
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
            <img src={imageData} alt={name} style={{ width: '88px', height: '88px', objectFit: 'cover', border: '1px solid var(--rule)', boxShadow: '2px 2px 0 var(--paper-darker)' }} />
            <button className="btn btn-ghost btn-sm" onClick={handleRemoveImage}
              style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--ink-ghost)', letterSpacing: '0.06em', marginTop: '4px' }}
            >Remover</button>
          </div>
        ) : (
          <button className="btn btn-ghost btn-sm" onClick={handleAttachImage}
            style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--ink-faint)', letterSpacing: '0.06em' }}
          >+ Anexar imagem</button>
        )}
      </div>

      {/* Descrição */}
      <div style={{ marginBottom: '20px' }}>
        <label style={labelStyle}>Descrição</label>
        <textarea
          value={description}
          onChange={(e) => { setDescription(e.target.value); mark() }}
          rows={5}
          style={{ ...inputStyle, resize: 'vertical', minHeight: '100px', fontFamily: 'var(--font-display)', fontStyle: 'italic', lineHeight: 1.6 }}
          placeholder="Descrição detalhada…"
        />
      </div>

      {/* Campos customizáveis */}
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: '10px' }}>
          <label style={{ ...labelStyle, margin: 0, flex: 1 }}>Campos</label>
          <button className="btn btn-ghost btn-sm" onClick={addField}
            style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--accent)', letterSpacing: '0.06em' }}
          >+ Campo</button>
        </div>
        {fields.length === 0 && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--ink-ghost)', letterSpacing: '0.04em' }}>
            Campos livres como "Localização", "Governo", "Fundação"…
          </p>
        )}
        {fields.map((field, idx) => (
          <div key={idx} style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'center' }}>
            <input type="text" placeholder="Rótulo" value={field.label}
              onChange={(e) => updateField(idx, 'label', e.target.value)}
              style={{ ...inputStyle, width: '140px', flexShrink: 0 }}
            />
            <input type="text" placeholder="Valor" value={field.value}
              onChange={(e) => updateField(idx, 'value', e.target.value)}
              style={{ ...inputStyle, flex: 1 }}
            />
            <button className="btn btn-ghost btn-icon" onClick={() => removeField(idx)}
              style={{ color: 'var(--ink-ghost)', fontSize: '12px', flexShrink: 0 }}
            >✕</button>
          </div>
        ))}
      </div>

      {/* Salvar */}
      <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
        <button className="btn btn-accent" onClick={handleSave} disabled={saving || !dirty}
          style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', letterSpacing: '0.08em' }}
        >
          {saving ? 'Salvando…' : 'Salvar'}
        </button>
        {!dirty && !saving && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--ink-ghost)', letterSpacing: '0.06em' }}>Salvo</span>
        )}
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  Estilos reutilizáveis
// ----------------------------------------------------------

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontFamily: 'var(--font-mono)',
  fontSize: '9px',
  textTransform: 'uppercase',
  letterSpacing: '0.14em',
  color: 'var(--ink-ghost)',
  marginBottom: '5px',
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  fontFamily: 'var(--font-mono)',
  fontSize: '13px',
  letterSpacing: '0.04em',
  color: 'var(--ink)',
  background: 'transparent',
  border: 'none',
  borderBottom: '1px solid var(--rule)',
  outline: 'none',
  padding: '4px 0',
  caretColor: 'var(--accent)',
}
