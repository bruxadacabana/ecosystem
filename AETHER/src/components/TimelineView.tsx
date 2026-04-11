/* ============================================================
   AETHER — TimelineView (4.4)
   Linha do tempo de eventos do projeto.
   Vista vertical: eventos ordenados com data, título e descrição.
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { Character, TimelineEvent, WorldNote } from '../types'

interface TimelineViewProps {
  projectId: string
  onError: (msg: string) => void
  onSuccess: (msg: string) => void
}

export function TimelineView({ projectId, onError, onSuccess }: TimelineViewProps) {
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [characters, setCharacters] = useState<Character[]>([])
  const [notes, setNotes] = useState<WorldNote[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<TimelineEvent | null>(null)
  const [creating, setCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newDate, setNewDate] = useState('')
  const newTitleRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    loadAll()
  }, [projectId])

  useEffect(() => {
    if (creating) newTitleRef.current?.focus()
  }, [creating])

  async function loadAll() {
    setLoading(true)
    const [evR, chR, noR] = await Promise.all([
      cmd.loadTimeline(projectId),
      cmd.listCharacters(projectId),
      cmd.listWorldNotes(projectId),
    ])
    setLoading(false)
    if (!evR.ok) { onError(evR.error.message); return }
    if (chR.ok) setCharacters(chR.data)
    if (noR.ok) setNotes(noR.data)
    setEvents(evR.data)
  }

  async function handleCreate() {
    if (!newTitle.trim()) { setCreating(false); return }
    const r = await cmd.createTimelineEvent(projectId, newTitle.trim(), newDate.trim() || '—')
    if (!r.ok) { onError(r.error.message); return }
    setEvents((prev) => [...prev, r.data])
    setSelected(r.data)
    setCreating(false); setNewTitle(''); setNewDate('')
  }

  function handleEventSaved(updated: TimelineEvent) {
    setSelected(updated)
    setEvents((prev) => prev.map((e) => (e.id === updated.id ? updated : e)))
    onSuccess('Evento salvo.')
  }

  async function handleDelete(ev: TimelineEvent) {
    const r = await cmd.deleteTimelineEvent(projectId, ev.id)
    if (!r.ok) { onError(r.error.message); return }
    setEvents((prev) => prev.filter((e) => e.id !== ev.id))
    if (selected?.id === ev.id) setSelected(null)
    onSuccess(`"${ev.title}" excluído.`)
  }

  function charName(id: string) { return characters.find((c) => c.id === id)?.name ?? id }
  function noteName(id: string) { return notes.find((n) => n.id === id)?.name ?? id }

  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
      {/* Lista de eventos (esquerda) */}
      <aside style={{
        width: '240px',
        flexShrink: 0,
        borderRight: '1px solid var(--rule)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* Cabeçalho */}
        <div style={{ padding: '10px 12px 8px', borderBottom: '1px solid var(--rule)', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--ink-ghost)', flex: 1 }}>Linha do Tempo</span>
          <button
            className="btn btn-ghost btn-icon"
            onClick={() => setCreating(true)}
            title="Novo evento"
            style={{ fontSize: '16px', lineHeight: 1, color: 'var(--ink-faint)', padding: '0 2px' }}
          >+</button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {loading && (
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--ink-ghost)', textAlign: 'center', padding: '20px 0' }}>· · ·</p>
          )}

          {creating && (
            <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--rule)', background: 'var(--paper-dark)' }}>
              <input
                ref={newTitleRef}
                type="text"
                placeholder="Título do evento"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreate()
                  if (e.key === 'Escape') { setCreating(false); setNewTitle(''); setNewDate('') }
                }}
                style={{ width: '100%', fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '13px', background: 'transparent', border: 'none', outline: 'none', color: 'var(--ink)', marginBottom: '4px' }}
              />
              <input
                type="text"
                placeholder="Data / época (ex: Ano 1024)"
                value={newDate}
                onChange={(e) => setNewDate(e.target.value)}
                onBlur={handleCreate}
                style={{ width: '100%', fontFamily: 'var(--font-mono)', fontSize: '10px', background: 'transparent', border: 'none', outline: 'none', color: 'var(--ink-ghost)', letterSpacing: '0.04em' }}
              />
            </div>
          )}

          {!loading && events.length === 0 && !creating && (
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--ink-ghost)', textAlign: 'center', padding: '20px 12px', letterSpacing: '0.04em' }}>
              Nenhum evento. Clique em + para criar.
            </p>
          )}

          {events.map((ev, idx) => (
            <EventListItem
              key={ev.id}
              event={ev}
              index={idx}
              isSelected={selected?.id === ev.id}
              isLast={idx === events.length - 1}
              onClick={() => setSelected(ev)}
              onDelete={() => handleDelete(ev)}
            />
          ))}
        </div>
      </aside>

      {/* Painel de detalhe / editor */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>
        {selected === null ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
            <p style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '20px', color: 'var(--ink-ghost)', margin: 0 }}>
              {events.length > 0 ? 'Selecione um evento.' : 'Linha do tempo vazia.'}
            </p>
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--ink-ghost)', margin: 0, letterSpacing: '0.06em' }}>
              {events.length > 0 ? '' : 'Clique em + para registrar o primeiro evento.'}
            </p>
          </div>
        ) : (
          <TimelineEventForm
            key={selected.id}
            projectId={projectId}
            event={selected}
            characters={characters}
            notes={notes}
            charName={charName}
            noteName={noteName}
            onSaved={handleEventSaved}
            onError={onError}
          />
        )}
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  EventListItem — item na lista lateral com linha de tempo
// ----------------------------------------------------------

function EventListItem({
  event, index, isSelected, isLast, onClick, onDelete,
}: {
  event: TimelineEvent
  index: number
  isSelected: boolean
  isLast: boolean
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
        display: 'flex',
        gap: '0',
        background: isSelected ? 'var(--paper-darker)' : hovered ? 'var(--paper-dark)' : 'transparent',
        cursor: 'pointer',
        transition: 'background var(--transition)',
        padding: '0',
      }}
    >
      {/* Linha do tempo vertical */}
      <div style={{ width: '32px', flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: '12px' }}>
        <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: isSelected ? 'var(--accent)' : 'var(--rule)', border: `2px solid ${isSelected ? 'var(--accent)' : 'var(--paper-darker)'}`, flexShrink: 0, transition: 'background var(--transition)' }} />
        {!isLast && <div style={{ width: '1px', flex: 1, background: 'var(--rule)', minHeight: '20px', marginTop: '2px' }} />}
      </div>

      {/* Conteúdo */}
      <div style={{ flex: 1, padding: '10px 10px 10px 4px', display: 'flex', alignItems: 'flex-start', gap: '6px' }}>
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--accent)', margin: '0 0 2px' }}>
            {event.date_label}
          </p>
          <p style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '13px', color: isSelected ? 'var(--ink)' : 'var(--ink-light)', margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {event.title}
          </p>
        </div>
        {hovered && (
          <button
            className="btn btn-ghost btn-icon"
            onClick={(e) => { e.stopPropagation(); onDelete() }}
            style={{ fontSize: '12px', color: 'var(--ink-ghost)', opacity: 0.6, padding: '0 2px', flexShrink: 0, marginTop: '2px' }}
          >✕</button>
        )}
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  TimelineEventForm — editor de evento (4.4)
// ----------------------------------------------------------

interface TimelineEventFormProps {
  projectId: string
  event: TimelineEvent
  characters: Character[]
  notes: WorldNote[]
  charName: (id: string) => string
  noteName: (id: string) => string
  onSaved: (updated: TimelineEvent) => void
  onError: (msg: string) => void
}

function TimelineEventForm({
  projectId, event, characters, notes, charName, noteName, onSaved, onError,
}: TimelineEventFormProps) {
  const [title, setTitle] = useState(event.title)
  const [dateLabel, setDateLabel] = useState(event.date_label)
  const [description, setDescription] = useState(event.description ?? '')
  const [characterIds, setCharacterIds] = useState<string[]>(event.character_ids)
  const [noteIds, setNoteIds] = useState<string[]>(event.note_ids)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  function mark() { setDirty(true) }

  function toggleChar(id: string) {
    setCharacterIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
    mark()
  }

  function toggleNote(id: string) {
    setNoteIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
    mark()
  }

  async function handleSave() {
    if (!title.trim()) { onError('O título não pode ser vazio.'); return }
    setSaving(true)
    const r = await cmd.saveTimelineEvent(projectId, event.id, {
      title: title.trim(),
      dateLabel: dateLabel.trim() || '—',
      description: description.trim() || null,
      characterIds,
      noteIds,
      chapterIds: event.chapter_ids,
    })
    setSaving(false)
    if (!r.ok) { onError(r.error.message); return }
    setDirty(false)
    onSaved(r.data)
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px 40px' }}>
      {/* Data */}
      <div style={{ marginBottom: '14px' }}>
        <label style={labelStyle}>Data / Época</label>
        <input
          type="text"
          value={dateLabel}
          onChange={(e) => { setDateLabel(e.target.value); mark() }}
          style={{ ...inputStyle, fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--accent)', letterSpacing: '0.08em' }}
          placeholder="ex: Ano 1024, Antes da guerra, Capítulo 7…"
        />
      </div>

      {/* Título */}
      <div style={{ marginBottom: '20px' }}>
        <label style={labelStyle}>Título</label>
        <input
          type="text"
          value={title}
          onChange={(e) => { setTitle(e.target.value); mark() }}
          style={{ ...inputStyle, fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '22px', color: 'var(--ink)' }}
          placeholder="Título do evento"
        />
      </div>

      {/* Descrição */}
      <div style={{ marginBottom: '24px' }}>
        <label style={labelStyle}>Descrição</label>
        <textarea
          value={description}
          onChange={(e) => { setDescription(e.target.value); mark() }}
          rows={4}
          style={{ ...inputStyle, resize: 'vertical', minHeight: '80px', fontFamily: 'var(--font-display)', fontStyle: 'italic', lineHeight: 1.6 }}
          placeholder="O que aconteceu neste evento…"
        />
      </div>

      {/* Personagens vinculados */}
      {characters.length > 0 && (
        <div style={{ marginBottom: '20px' }}>
          <label style={labelStyle}>Personagens presentes</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '6px' }}>
            {characters.map((c) => (
              <TagChip
                key={c.id}
                label={c.name}
                active={characterIds.includes(c.id)}
                onClick={() => toggleChar(c.id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Notas de worldbuilding vinculadas */}
      {notes.length > 0 && (
        <div style={{ marginBottom: '24px' }}>
          <label style={labelStyle}>Locais / Facções / Objetos envolvidos</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '6px' }}>
            {notes.map((n) => (
              <TagChip
                key={n.id}
                label={n.name}
                active={noteIds.includes(n.id)}
                onClick={() => toggleNote(n.id)}
              />
            ))}
          </div>
        </div>
      )}

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
//  TagChip — chip clicável para vincular entidades
// ----------------------------------------------------------

function TagChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: '11px',
        letterSpacing: '0.06em',
        color: active ? 'var(--accent)' : 'var(--ink-ghost)',
        border: `1px solid ${active ? 'var(--accent)' : 'var(--rule)'}`,
        borderRadius: '20px',
        padding: '3px 10px',
        background: active ? 'transparent' : 'var(--paper-dark)',
        cursor: 'pointer',
        transition: 'color var(--transition), border-color var(--transition)',
      }}
    >
      {label}
    </button>
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
