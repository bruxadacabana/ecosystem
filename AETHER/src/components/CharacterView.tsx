/* ============================================================
   AETHER — CharacterView (4.1 + 4.2)
   Fichas de personagem com campos customizáveis.
   Relacionamentos entre personagens.
   Layout: lista lateral (220px) + painel de detalhes.
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import { open as openFileDialog } from '@tauri-apps/plugin-dialog'
import * as cmd from '../lib/tauri'
import type { Character, CustomField, Relationship } from '../types'

interface CharacterViewProps {
  projectId: string
  onError: (msg: string) => void
  onSuccess: (msg: string) => void
}

type CharTab = 'ficha' | 'relacoes'

export function CharacterView({ projectId, onError, onSuccess }: CharacterViewProps) {
  const [characters, setCharacters] = useState<Character[]>([])
  const [selected, setSelected] = useState<Character | null>(null)
  const [tab, setTab] = useState<CharTab>('ficha')
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const newInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    loadCharacters()
  }, [projectId])

  useEffect(() => {
    if (creating) newInputRef.current?.focus()
  }, [creating])

  async function loadCharacters() {
    setLoading(true)
    const r = await cmd.listCharacters(projectId)
    setLoading(false)
    if (!r.ok) { onError(r.error.message); return }
    setCharacters(r.data)
  }

  async function handleCreate() {
    if (!newName.trim()) { setCreating(false); return }
    const r = await cmd.createCharacter(projectId, newName.trim())
    if (!r.ok) { onError(r.error.message); return }
    setCharacters((prev) => [...prev, r.data].sort((a, b) => a.name.localeCompare(b.name)))
    setSelected(r.data)
    setCreating(false)
    setNewName('')
  }

  function handleSelectCharacter(char: Character) {
    setSelected(char)
    setTab('ficha')
  }

  function handleCharacterSaved(updated: Character) {
    setSelected(updated)
    setCharacters((prev) =>
      prev.map((c) => (c.id === updated.id ? updated : c))
        .sort((a, b) => a.name.localeCompare(b.name))
    )
    onSuccess(`"${updated.name}" salvo.`)
  }

  async function handleDelete(char: Character) {
    const r = await cmd.deleteCharacter(projectId, char.id)
    if (!r.ok) { onError(r.error.message); return }
    setCharacters((prev) => prev.filter((c) => c.id !== char.id))
    if (selected?.id === char.id) setSelected(null)
    onSuccess(`"${char.name}" excluído.`)
  }

  const filtered = characters.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase())
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
          }}>Personagens</span>
          <button
            className="btn btn-ghost btn-icon"
            onClick={() => setCreating(true)}
            title="Novo personagem"
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

        {/* Lista */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {loading && (
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--ink-ghost)', textAlign: 'center', padding: '20px 0' }}>· · ·</p>
          )}
          {!loading && filtered.length === 0 && !creating && (
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--ink-ghost)', textAlign: 'center', padding: '20px 0', letterSpacing: '0.04em' }}>
              {search ? 'Nenhum resultado.' : 'Nenhum personagem.'}
            </p>
          )}
          {creating && (
            <div style={{ padding: '6px 10px', borderBottom: '1px solid var(--rule)' }}>
              <input
                ref={newInputRef}
                type="text"
                placeholder="Nome do personagem"
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
          {filtered.map((char) => (
            <CharListItem
              key={char.id}
              char={char}
              isSelected={selected?.id === char.id}
              onClick={() => handleSelectCharacter(char)}
              onDelete={() => handleDelete(char)}
            />
          ))}
        </div>
      </aside>

      {/* Painel de detalhes */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>
        {selected === null ? (
          <EmptyDetail hasCharacters={characters.length > 0} />
        ) : (
          <>
            {/* Sub-tabs */}
            <div style={{
              height: '32px',
              display: 'flex',
              alignItems: 'center',
              padding: '0 24px',
              borderBottom: '1px solid var(--rule)',
              gap: '4px',
              flexShrink: 0,
              background: 'var(--paper-dark)',
            }}>
              {(['ficha', 'relacoes'] as CharTab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '10px',
                    letterSpacing: '0.1em',
                    textTransform: 'uppercase',
                    padding: '3px 10px',
                    color: tab === t ? 'var(--accent)' : 'var(--ink-ghost)',
                    background: 'none',
                    border: 'none',
                    borderBottom: tab === t ? '1px solid var(--accent)' : '1px solid transparent',
                    cursor: 'pointer',
                    transition: 'color var(--transition), border-color var(--transition)',
                  }}
                >
                  {t === 'ficha' ? 'Ficha' : 'Relações'}
                </button>
              ))}
            </div>

            {tab === 'ficha' && (
              <CharacterForm
                key={selected.id}
                projectId={projectId}
                character={selected}
                onSaved={handleCharacterSaved}
                onError={onError}
              />
            )}
            {tab === 'relacoes' && (
              <RelationshipPanel
                key={selected.id}
                projectId={projectId}
                character={selected}
                characters={characters}
                onError={onError}
                onSuccess={onSuccess}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  CharListItem
// ----------------------------------------------------------

function CharListItem({
  char, isSelected, onClick, onDelete,
}: {
  char: Character
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
        padding: '8px 10px',
        borderBottom: '1px solid transparent',
        background: isSelected ? 'var(--paper-darker)' : hovered ? 'var(--paper-dark)' : 'transparent',
        cursor: 'pointer',
        transition: 'background var(--transition)',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
      }}
    >
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <p style={{
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          fontSize: '14px',
          color: isSelected ? 'var(--ink)' : 'var(--ink-light)',
          margin: 0,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}>{char.name}</p>
        {char.role && (
          <p style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '10px',
            color: 'var(--ink-ghost)',
            margin: 0,
            letterSpacing: '0.04em',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}>{char.role}</p>
        )}
      </div>
      {hovered && (
        <button
          className="btn btn-ghost btn-icon"
          onClick={(e) => { e.stopPropagation(); onDelete() }}
          title="Excluir personagem"
          style={{ fontSize: '12px', color: 'var(--ink-ghost)', opacity: 0.6, padding: '0 2px', flexShrink: 0 }}
        >✕</button>
      )}
    </div>
  )
}

// ----------------------------------------------------------
//  EmptyDetail
// ----------------------------------------------------------

function EmptyDetail({ hasCharacters }: { hasCharacters: boolean }) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
      <p style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '20px', color: 'var(--ink-ghost)', margin: 0 }}>
        {hasCharacters ? 'Selecione um personagem.' : 'Nenhum personagem ainda.'}
      </p>
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--ink-ghost)', margin: 0, letterSpacing: '0.06em' }}>
        {hasCharacters ? '' : 'Clique em + para criar o primeiro.'}
      </p>
    </div>
  )
}

// ----------------------------------------------------------
//  CharacterForm — editor de ficha (4.1)
// ----------------------------------------------------------

interface CharacterFormProps {
  projectId: string
  character: Character
  onSaved: (updated: Character) => void
  onError: (msg: string) => void
}

function CharacterForm({ projectId, character, onSaved, onError }: CharacterFormProps) {
  const [name, setName] = useState(character.name)
  const [role, setRole] = useState(character.role ?? '')
  const [description, setDescription] = useState(character.description ?? '')
  const [fields, setFields] = useState<CustomField[]>(character.fields)
  const [imagePath, setImagePath] = useState<string | null>(character.image_path)
  const [imageData, setImageData] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  // Carregar imagem quando imagePath muda
  useEffect(() => {
    if (!imagePath) { setImageData(null); return }
    cmd.loadImage(imagePath).then((r) => {
      if (r.ok) setImageData(r.data)
    })
  }, [imagePath])

  function mark() { setDirty(true) }

  function addField() {
    setFields((prev) => [...prev, { label: '', value: '' }])
    mark()
  }

  function updateField(idx: number, key: keyof CustomField, val: string) {
    setFields((prev) => prev.map((f, i) => i === idx ? { ...f, [key]: val } : f))
    mark()
  }

  function removeField(idx: number) {
    setFields((prev) => prev.filter((_, i) => i !== idx))
    mark()
  }

  async function handleAttachImage() {
    const selected = await openFileDialog({
      filters: [{ name: 'Imagem', extensions: ['png', 'jpg', 'jpeg', 'gif', 'webp'] }],
    })
    if (!selected || typeof selected !== 'string') return

    const prefix = `char_${character.id}`
    const r = await cmd.attachImage(projectId, prefix, selected)
    if (!r.ok) { onError(r.error.message); return }

    setImagePath(r.data)
    mark()
  }

  async function handleRemoveImage() {
    if (!imagePath) return
    const r = await cmd.removeImage(imagePath)
    if (!r.ok) { onError(r.error.message); return }
    setImagePath(null)
    setImageData(null)
    mark()
  }

  async function handleSave() {
    if (!name.trim()) { onError('O nome não pode ser vazio.'); return }
    setSaving(true)
    const r = await cmd.saveCharacter(projectId, character.id, {
      name: name.trim(),
      role: role.trim() || null,
      description: description.trim() || null,
      fields: fields.filter((f) => f.label.trim()),
      imagePath,
      chapterIds: character.chapter_ids,
    })
    setSaving(false)
    if (!r.ok) { onError(r.error.message); return }
    setDirty(false)
    onSaved(r.data)
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px 40px' }}>
      {/* Nome */}
      <div style={{ marginBottom: '20px' }}>
        <label style={labelStyle}>Nome</label>
        <input
          type="text"
          value={name}
          onChange={(e) => { setName(e.target.value); mark() }}
          style={{
            ...inputStyle,
            fontFamily: 'var(--font-display)',
            fontStyle: 'italic',
            fontSize: '22px',
            color: 'var(--ink)',
          }}
          placeholder="Nome do personagem"
        />
      </div>

      {/* Papel / Role */}
      <div style={{ marginBottom: '20px' }}>
        <label style={labelStyle}>Papel</label>
        <input
          type="text"
          value={role}
          onChange={(e) => { setRole(e.target.value); mark() }}
          style={inputStyle}
          placeholder="ex: Protagonista, Antagonista, Coadjuvante…"
        />
      </div>

      {/* Imagem */}
      <div style={{ marginBottom: '20px' }}>
        <label style={labelStyle}>Imagem</label>
        {imageData ? (
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
            <img
              src={imageData}
              alt={name}
              style={{
                width: '88px',
                height: '88px',
                objectFit: 'cover',
                border: '1px solid var(--rule)',
                boxShadow: '2px 2px 0 var(--paper-darker)',
              }}
            />
            <button
              className="btn btn-ghost btn-sm"
              onClick={handleRemoveImage}
              style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--ink-ghost)', letterSpacing: '0.06em', marginTop: '4px' }}
            >Remover</button>
          </div>
        ) : (
          <button
            className="btn btn-ghost btn-sm"
            onClick={handleAttachImage}
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
          rows={4}
          style={{
            ...inputStyle,
            resize: 'vertical',
            minHeight: '80px',
            fontFamily: 'var(--font-display)',
            fontStyle: 'italic',
            lineHeight: 1.6,
          }}
          placeholder="Descrição geral do personagem…"
        />
      </div>

      {/* Campos customizáveis */}
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: '10px' }}>
          <label style={{ ...labelStyle, margin: 0, flex: 1 }}>Campos</label>
          <button
            className="btn btn-ghost btn-sm"
            onClick={addField}
            style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--accent)', letterSpacing: '0.06em' }}
          >+ Campo</button>
        </div>
        {fields.length === 0 && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--ink-ghost)', letterSpacing: '0.04em' }}>
            Nenhum campo. Adicione campos livres como "Idade", "Habilidade", "Apelido"…
          </p>
        )}
        {fields.map((field, idx) => (
          <div key={idx} style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'center' }}>
            <input
              type="text"
              placeholder="Rótulo"
              value={field.label}
              onChange={(e) => updateField(idx, 'label', e.target.value)}
              style={{ ...inputStyle, width: '140px', flexShrink: 0 }}
            />
            <input
              type="text"
              placeholder="Valor"
              value={field.value}
              onChange={(e) => updateField(idx, 'value', e.target.value)}
              style={{ ...inputStyle, flex: 1 }}
            />
            <button
              className="btn btn-ghost btn-icon"
              onClick={() => removeField(idx)}
              style={{ color: 'var(--ink-ghost)', fontSize: '12px', flexShrink: 0 }}
            >✕</button>
          </div>
        ))}
      </div>

      {/* Salvar */}
      <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
        <button
          className="btn btn-accent"
          onClick={handleSave}
          disabled={saving || !dirty}
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
//  RelationshipPanel — mapa de relações (4.2)
// ----------------------------------------------------------

interface RelationshipPanelProps {
  projectId: string
  character: Character
  characters: Character[]
  onError: (msg: string) => void
  onSuccess: (msg: string) => void
}

function RelationshipPanel({ projectId, character, characters, onError, onSuccess }: RelationshipPanelProps) {
  const [rels, setRels] = useState<Relationship[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [toId, setToId] = useState('')
  const [kind, setKind] = useState('')
  const [note, setNote] = useState('')

  useEffect(() => {
    loadRels()
  }, [projectId, character.id])

  async function loadRels() {
    setLoading(true)
    const r = await cmd.listRelationships(projectId)
    setLoading(false)
    if (!r.ok) { onError(r.error.message); return }
    // Mostrar só relações que envolvem este personagem
    setRels(r.data.filter((r) => r.from_id === character.id || r.to_id === character.id))
  }

  function charName(id: string) {
    return characters.find((c) => c.id === id)?.name ?? '?'
  }

  async function handleAdd() {
    if (!toId || !kind.trim()) return
    const r = await cmd.addRelationship(projectId, character.id, toId, kind.trim(), note.trim() || null)
    if (!r.ok) { onError(r.error.message); return }
    setRels((prev) => [...prev, r.data])
    setShowForm(false); setToId(''); setKind(''); setNote('')
    onSuccess('Relação adicionada.')
  }

  async function handleDelete(relId: string) {
    const r = await cmd.deleteRelationship(projectId, relId)
    if (!r.ok) { onError(r.error.message); return }
    setRels((prev) => prev.filter((r) => r.id !== relId))
    onSuccess('Relação removida.')
  }

  const others = characters.filter((c) => c.id !== character.id)

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px 40px' }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '20px' }}>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--ink-ghost)', margin: 0, flex: 1 }}>
          Relações de {character.name}
        </p>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => setShowForm((v) => !v)}
          style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--accent)', letterSpacing: '0.06em' }}
        >+ Relação</button>
      </div>

      {showForm && (
        <div style={{ background: 'var(--paper-dark)', border: '1px solid var(--rule)', padding: '16px', marginBottom: '20px', boxShadow: '2px 2px 0 var(--paper-darker)' }}>
          <div style={{ marginBottom: '10px' }}>
            <label style={labelStyle}>Com quem</label>
            <select
              value={toId}
              onChange={(e) => setToId(e.target.value)}
              style={{ ...inputStyle, cursor: 'pointer' }}
            >
              <option value="">Selecionar personagem…</option>
              {others.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div style={{ marginBottom: '10px' }}>
            <label style={labelStyle}>Tipo de relação</label>
            <input
              type="text"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              style={inputStyle}
              placeholder="ex: Aliados, Inimigos, Família, Mentor…"
            />
          </div>
          <div style={{ marginBottom: '14px' }}>
            <label style={labelStyle}>Nota (opcional)</label>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              style={inputStyle}
              placeholder="Observação sobre a relação…"
            />
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="btn btn-accent" onClick={handleAdd}
              style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', letterSpacing: '0.08em' }}
            >Adicionar</button>
            <button className="btn btn-ghost btn-sm" onClick={() => setShowForm(false)}
              style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}
            >Cancelar</button>
          </div>
        </div>
      )}

      {loading && <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--ink-ghost)', letterSpacing: '0.04em' }}>· · ·</p>}
      {!loading && rels.length === 0 && !showForm && (
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--ink-ghost)', letterSpacing: '0.04em' }}>
          Nenhuma relação registrada. Clique em + Relação para adicionar.
        </p>
      )}

      {rels.map((rel) => {
        const fromName = charName(rel.from_id)
        const toName = charName(rel.to_id)
        const direction = rel.from_id === character.id
          ? `→ ${toName}`
          : `← ${fromName}`
        return (
          <RelRow
            key={rel.id}
            rel={rel}
            direction={direction}
            onDelete={() => handleDelete(rel.id)}
          />
        )
      })}
    </div>
  )
}

function RelRow({ rel, direction, onDelete }: { rel: Relationship; direction: string; onDelete: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        padding: '10px 12px',
        marginBottom: '4px',
        background: hovered ? 'var(--paper-dark)' : 'transparent',
        border: '1px solid var(--rule)',
        transition: 'background var(--transition)',
      }}
    >
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
          <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '15px', color: 'var(--ink-light)' }}>{rel.kind}</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--accent)', letterSpacing: '0.04em' }}>{direction}</span>
        </div>
        {rel.note && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--ink-ghost)', margin: '2px 0 0', letterSpacing: '0.04em' }}>{rel.note}</p>
        )}
      </div>
      {hovered && (
        <button
          className="btn btn-ghost btn-icon"
          onClick={onDelete}
          style={{ fontSize: '12px', color: 'var(--ink-ghost)', opacity: 0.6 }}
        >✕</button>
      )}
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
