import React, { useState, useCallback, useEffect, useRef } from 'react'
import { Page, Project, ProjectProperty, PagePropValue, PropOption } from '../../types'
import { fromIpc } from '../../types/errors'
import { CosmosLayer } from '../../components/Cosmos/CosmosLayer'
import { EditorFrame } from '../../components/Editor/EditorFrame'
import { IconPicker } from '../../components/UI/IconPicker'
import { useAppStore } from '../../store/useAppStore'
import { createLogger } from '../../utils/logger'
import './PageView.css'

const log = createLogger('PageView')
const db  = () => (window as any).db

// ── Recursos vinculados ───────────────────────────────────────────────────────

const RESOURCE_ICONS: Record<string, string> = {
  livro: '📖', artigo: '📄', link: '🔗', video: '▶', podcast: '🎙',
  tool: '⚙', template: '◧', dataset: '◈', doc: '📃', other: '◦',
}

function PageResourcePanel({ pageId, dark }: { pageId: number; dark: boolean }) {
  const [resources, setResources] = useState<any[]>([])
  const [expanded,  setExpanded]  = useState(false)

  const bg     = dark ? '#1A1710' : '#F5F0E8'
  const border = dark ? '#3A3020' : '#D4C9B4'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const accent = dark ? '#D4A820' : '#b8860b'

  const load = () => {
    fromIpc<any[]>(() => db().resourcePages.listForPage(pageId), 'listResourcePages')
      .then(r => r.match(data => setResources(data), _e => {}))
  }

  useEffect(() => { load() }, [pageId])

  if (resources.length === 0 && !expanded) {
    return (
      <div style={{ padding: '4px 16px 0', background: bg, borderTop: `1px solid ${border}` }}>
        <button onClick={() => setExpanded(true)} style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em',
          color: ink2, background: 'none', border: 'none', cursor: 'pointer', padding: '6px 0',
        }}>
          + Recurso
        </button>
      </div>
    )
  }

  return (
    <div style={{ padding: '8px 16px', background: bg, borderTop: `1px solid ${border}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: resources.length ? 6 : 0 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em', color: ink2 }}>
          RECURSOS
        </span>
        {resources.length > 0 && (
          <span style={{ fontSize: 9, color: ink2 }}>({resources.length})</span>
        )}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
        {resources.map((r: any) => {
          let meta: any = {}
          try { if (r.metadata_json) meta = JSON.parse(r.metadata_json) } catch {}
          const cover = meta.cover_url || meta.cover_url_m || meta.thumbnail_url
          return (
            <div key={r.resource_id} title={r.title} style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '3px 8px 3px 5px', borderRadius: 3,
              border: `1px solid ${border}`, background: 'transparent',
              fontSize: 11, color: ink,
            }}>
              {cover
                ? <img src={cover} alt="" style={{ width: 16, height: 22, objectFit: 'cover', borderRadius: 1 }} />
                : <span style={{ fontSize: 12 }}>{RESOURCE_ICONS[r.resource_type ?? ''] ?? '◦'}</span>
              }
              <span style={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {r.title}
              </span>
              <button onClick={async () => {
                await fromIpc<unknown>(
                  () => db().resourcePages.remove(r.resource_id, pageId),
                  'removeResourcePage',
                )
                load()
              }} style={{
                background: 'none', border: 'none', cursor: 'pointer',
                fontSize: 9, color: ink2, padding: '0 0 0 2px', lineHeight: 1,
              }}>✕</button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Tags Globais ──────────────────────────────────────────────────────────────

interface Tag { id: number; name: string; color: string | null }

function GlobalTagPanel({ pageId, dark }: { pageId: number; dark: boolean }) {
  const [allTags,    setAllTags]    = useState<Tag[]>([])
  const [pageTags,   setPageTags]   = useState<Tag[]>([])
  const [newTag,     setNewTag]     = useState('')
  const [showInput,  setShowInput]  = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const bg     = dark ? '#1A1610' : '#F5F0E8'
  const accent = dark ? '#D4A820' : '#b8860b'

  const loadTags = useCallback(() => {
    fromIpc<Tag[]>(() => db().tags.list(), 'listTags')
      .then(r => r.match(data => setAllTags(data), _e => {}))
    fromIpc<Tag[]>(() => db().tags.listForPage(pageId), 'listPageTags')
      .then(r => r.match(data => setPageTags(data), _e => {}))
  }, [pageId])

  useEffect(() => { loadTags() }, [loadTags])
  useEffect(() => { if (showInput) inputRef.current?.focus() }, [showInput])

  const pageTagIds = new Set(pageTags.map(t => t.id))

  const handleToggle = async (tag: Tag) => {
    const call = pageTagIds.has(tag.id)
      ? () => db().tags.remove(pageId, tag.id)
      : () => db().tags.assign(pageId, tag.id)
    await fromIpc<unknown>(call, 'toggleTag')
    loadTags()
  }

  const handleCreate = async () => {
    const name = newTag.trim()
    if (!name) return
    const result = await fromIpc<{ id: number }>(() => db().tags.create(name), 'createTag')
    if (result.isOk()) {
      await fromIpc<unknown>(() => db().tags.assign(pageId, result.value.id), 'assignTag')
    }
    setNewTag('')
    setShowInput(false)
    loadTags()
  }

  if (allTags.length === 0 && !showInput) {
    return (
      <div style={{
        padding: '4px 16px 0', background: bg,
        borderTop: `1px solid ${border}`,
      }}>
        <button onClick={() => setShowInput(true)} style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em',
          color: ink2, background: 'none', border: 'none', cursor: 'pointer',
          padding: '6px 0',
        }}>
          + Tag global
        </button>
      </div>
    )
  }

  return (
    <div style={{
      padding: '8px 16px', background: bg,
      borderTop: `1px solid ${border}`,
      display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 5,
    }}>
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em',
        color: ink2, flexShrink: 0,
      }}>
        TAGS
      </span>

      {allTags.map(tag => {
        const active = pageTagIds.has(tag.id)
        const color  = tag.color ?? ink2
        return (
          <button key={tag.id} onClick={() => handleToggle(tag)} style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.06em',
            padding: '2px 8px', borderRadius: 1, cursor: 'pointer', transition: 'all 80ms',
            border: `1px solid ${active ? color : border}`,
            background: active ? color + '22' : 'transparent',
            color: active ? color : ink2,
          }}>
            {tag.name}
          </button>
        )
      })}

      {showInput ? (
        <input
          ref={inputRef}
          value={newTag}
          onChange={e => setNewTag(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') handleCreate()
            if (e.key === 'Escape') { setShowInput(false); setNewTag('') }
          }}
          onBlur={() => { if (!newTag.trim()) setShowInput(false) }}
          placeholder="nova tag…"
          style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.06em',
            padding: '2px 8px', borderRadius: 1, outline: 'none',
            border: `1px solid ${accent}`, background: 'transparent',
            color: accent, width: 100,
          }}
        />
      ) : (
        <button onClick={() => setShowInput(true)} style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2,
          background: 'none', border: `1px dashed ${border}`, borderRadius: 1,
          padding: '2px 8px', cursor: 'pointer',
        }}>
          +
        </button>
      )}
    </div>
  )
}

// ── Eventos / Lembretes vinculados à página ───────────────────────────────────

const EVENT_ICONS: Record<string, string> = {
  prova: '📝', trabalho: '📋', seminario: '🎙', defesa: '🎓',
  prazo: '⏰', reuniao: '👥', outro: '◦',
}
const EVENT_LABELS: Record<string, string> = {
  prova: 'Prova', trabalho: 'Trabalho', seminario: 'Seminário',
  defesa: 'Defesa', prazo: 'Prazo', reuniao: 'Reunião', outro: 'Outro',
}
const EVENT_COLORS: Record<string, string> = {
  prova: '#8B3A2A', trabalho: '#2C5F8A', seminario: '#6B4F72',
  defesa: '#b8860b', prazo: '#7A5C2E', reuniao: '#4A6741', outro: '#8B7355',
}

function PageEventsPanel({ page, project, dark }: { page: Page; project: Project; dark: boolean }) {
  const { pushToast } = useAppStore()
  const [events,   setEvents]   = useState<any[]>([])
  const [expanded, setExpanded] = useState(false)
  const [adding,   setAdding]   = useState(false)

  const [form, setForm] = useState({
    title: '', event_type: 'outro', start_dt: '', all_day: true,
    time: '09:00', reminder_minutes: '' as string | number,
  })

  const bg     = dark ? '#1A1710' : '#F5F0E8'
  const border = dark ? '#3A3020' : '#D4C9B4'
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'

  const load = () => {
    fromIpc<any[]>(() => db().events.listForPage(page.id), 'eventsForPage')
      .then(r => r.match(data => setEvents(data), _e => {}))
  }

  useEffect(() => { load() }, [page.id])

  const handleAdd = async () => {
    if (!form.title.trim() || !form.start_dt) return
    const start_dt = form.all_day ? form.start_dt : `${form.start_dt}T${form.time}:00`
    const rem = form.reminder_minutes !== '' ? Number(form.reminder_minutes) : undefined
    const result = await fromIpc<any>(() => db().events.create({
      title: form.title.trim(),
      event_type: form.event_type,
      start_dt,
      all_day: form.all_day ? 1 : 0,
      linked_page_id: page.id,
      linked_project_id: project.id,
      reminder_minutes: rem,
    }), 'createPageEvent')
    if (result.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao criar evento', detail: result.error.message })
      return
    }
    setAdding(false)
    setForm({ title: '', event_type: 'outro', start_dt: '', all_day: true, time: '09:00', reminder_minutes: '' })
    load()
  }

  const handleDelete = async (id: number) => {
    await fromIpc<any>(() => db().events.delete(id), 'deletePageEvent')
    load()
  }

  const today = new Date().toISOString().slice(0, 10)

  if (events.length === 0 && !expanded) {
    return (
      <div style={{ padding: '4px 16px 0', background: bg, borderTop: `1px solid ${border}` }}>
        <button onClick={() => { setExpanded(true); setAdding(true) }} style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em',
          color: ink2, background: 'none', border: 'none', cursor: 'pointer', padding: '6px 0',
        }}>
          + Actividade / Lembrete
        </button>
      </div>
    )
  }

  return (
    <div style={{ padding: '8px 16px 10px', background: bg, borderTop: `1px solid ${border}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em', color: ink2 }}>
          ACTIVIDADES & LEMBRETES
        </span>
        <button onClick={() => { setExpanded(true); setAdding(true) }}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: accent, fontSize: 13, lineHeight: 1, padding: 0 }}>
          +
        </button>
      </div>

      {/* Lista de eventos */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: adding ? 10 : 0 }}>
        {events.map((ev: any) => {
          const dt    = ev.start_dt?.slice(0, 10) ?? ''
          const past  = dt < today
          const color = EVENT_COLORS[ev.event_type ?? 'outro'] ?? '#8B7355'
          return (
            <div key={ev.id} style={{
              display: 'flex', alignItems: 'center', gap: 7,
              padding: '4px 8px', borderRadius: 2,
              border: `1px solid ${past ? border : color + '55'}`,
              background: past ? 'transparent' : (color + '11'),
              opacity: past ? 0.55 : 1,
            }}>
              <span title={EVENT_LABELS[ev.event_type ?? 'outro']}>
                {EVENT_ICONS[ev.event_type ?? 'outro']}
              </span>
              <span style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: 10, color: ink,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {ev.title}
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: past ? ink2 : color, flexShrink: 0 }}>
                {dt ? new Date(dt + 'T12:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }) : ''}
                {ev.start_dt?.includes('T') && !ev.all_day
                  ? ' ' + ev.start_dt.slice(11, 16)
                  : ''}
              </span>
              <button onClick={() => handleDelete(ev.id)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: ink2, fontSize: 12, padding: 0, lineHeight: 1 }}>
                ×
              </button>
            </div>
          )
        })}
      </div>

      {/* Formulário inline */}
      {adding && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5,
          padding: '8px', border: `1px solid ${border}`, borderRadius: 2,
          background: dark ? '#211D16' : '#EDE7D9' }}>

          {/* Tipo */}
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {Object.entries(EVENT_ICONS).map(([type, icon]) => (
              <button key={type}
                onClick={() => setForm(f => ({ ...f, event_type: type }))}
                title={EVENT_LABELS[type]}
                style={{
                  fontSize: 11, padding: '2px 7px', borderRadius: 2, cursor: 'pointer',
                  border: `1px solid ${form.event_type === type ? EVENT_COLORS[type] : border}`,
                  background: form.event_type === type ? EVENT_COLORS[type] + '22' : 'transparent',
                  color: form.event_type === type ? EVENT_COLORS[type] : ink2,
                  fontFamily: 'var(--font-mono)',
                }}>
                {icon} {EVENT_LABELS[type]}
              </button>
            ))}
          </div>

          {/* Título */}
          <input
            type="text" placeholder="Título da actividade…"
            value={form.title}
            onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
            autoFocus
            style={{
              background: 'none', border: `1px solid ${border}`, borderRadius: 2,
              padding: '4px 8px', fontSize: 11, color: ink, outline: 'none',
              fontFamily: 'var(--font-mono)',
            }}
          />

          {/* Data + hora */}
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
            <input type="date" value={form.start_dt}
              onChange={e => setForm(f => ({ ...f, start_dt: e.target.value }))}
              style={{
                background: 'none', border: `1px solid ${border}`, borderRadius: 2,
                padding: '3px 6px', fontSize: 11, color: ink, outline: 'none',
                colorScheme: dark ? 'dark' : 'light',
              }} />
            <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: ink2, fontFamily: 'var(--font-mono)', cursor: 'pointer' }}>
              <input type="checkbox" checked={form.all_day}
                onChange={e => setForm(f => ({ ...f, all_day: e.target.checked }))} />
              dia inteiro
            </label>
            {!form.all_day && (
              <input type="time" value={form.time}
                onChange={e => setForm(f => ({ ...f, time: e.target.value }))}
                style={{
                  background: 'none', border: `1px solid ${border}`, borderRadius: 2,
                  padding: '3px 6px', fontSize: 11, color: ink, outline: 'none',
                  colorScheme: dark ? 'dark' : 'light',
                }} />
            )}
          </div>

          {/* Lembrete */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, letterSpacing: '0.08em' }}>
              LEMBRETE
            </span>
            <select
              value={form.reminder_minutes}
              onChange={e => setForm(f => ({ ...f, reminder_minutes: e.target.value }))}
              style={{
                background: 'none', border: `1px solid ${border}`, borderRadius: 2,
                padding: '2px 5px', fontSize: 10, color: ink, fontFamily: 'var(--font-mono)',
              }}>
              <option value="">Sem lembrete</option>
              <option value={15}>15 min antes</option>
              <option value={30}>30 min antes</option>
              <option value={60}>1 hora antes</option>
              <option value={1440}>1 dia antes</option>
              <option value={2880}>2 dias antes</option>
            </select>
          </div>

          {/* Acções */}
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={handleAdd}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.08em',
                padding: '3px 12px', border: `1px solid ${accent}`, borderRadius: 2,
                color: accent, background: 'none', cursor: 'pointer',
              }}>
              Guardar
            </button>
            <button onClick={() => { setAdding(false); if (events.length === 0) setExpanded(false) }}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 10,
                padding: '3px 10px', border: `1px solid ${border}`, borderRadius: 2,
                color: ink2, background: 'none', cursor: 'pointer',
              }}>
              Cancelar
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Pré-requisitos (projetos académicos) ──────────────────────────────────────

function PrerequisitesPanel({ page, project, dark }: { page: Page; project: Project; dark: boolean }) {
  const [prereqs,    setPrereqs]    = useState<any[]>([])
  const [dependents, setDependents] = useState<any[]>([])
  const [allPages,   setAllPages]   = useState<any[]>([])
  const [expanded,   setExpanded]   = useState(false)
  const [query,      setQuery]      = useState('')
  const [adding,     setAdding]     = useState(false)
  const { pushToast } = useAppStore()

  const bg     = dark ? '#1A1710' : '#F5F0E8'
  const border = dark ? '#3A3020' : '#D4C9B4'
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'

  const load = () => {
    fromIpc<any[]>(() => db().prerequisites.list(page.id), 'listPrereqs')
      .then(r => r.match(data => setPrereqs(data), _e => {}))
    fromIpc<any[]>(() => db().prerequisites.listDependents(page.id), 'listDependents')
      .then(r => r.match(data => setDependents(data), _e => {}))
  }

  useEffect(() => { load() }, [page.id])

  useEffect(() => {
    if (!adding) return
    fromIpc<any[]>(() => db().pages.list(project.id), 'listPagesForPrereqs')
      .then(r => r.match(data => setAllPages(data.filter((p: any) => p.id !== page.id)), _e => {}))
  }, [adding, project.id, page.id])

  const addPrereq = async (prereqId: number) => {
    const result = await fromIpc<any>(() => db().prerequisites.add(page.id, prereqId), 'addPrereq')
    if (result.isErr() || result.value?.ok === false) {
      pushToast({ kind: 'error', title: 'Erro ao adicionar pré-requisito', detail: result.isErr() ? result.error.message : result.value?.error })
      return
    }
    setQuery(''); setAdding(false); load()
  }

  const removePrereq = async (prereqId: number) => {
    await fromIpc<unknown>(() => db().prerequisites.remove(page.id, prereqId), 'removePrereq')
    load()
  }

  const filtered = allPages.filter(p =>
    !prereqs.find(r => r.id === p.id) &&
    (!query.trim() || p.title.toLowerCase().includes(query.toLowerCase()))
  ).slice(0, 8)

  const hasContent = prereqs.length > 0 || dependents.length > 0

  if (!hasContent && !expanded) {
    return (
      <div style={{ padding: '4px 16px 0', background: bg, borderTop: `1px solid ${border}` }}>
        <button onClick={() => setExpanded(true)} style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em',
          color: ink2, background: 'none', border: 'none', cursor: 'pointer', padding: '6px 0',
        }}>
          + Pré-requisitos
        </button>
      </div>
    )
  }

  return (
    <div style={{ background: bg, borderTop: `1px solid ${border}`, padding: '8px 16px 10px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em', color: ink2, flex: 1 }}>
          PRÉ-REQUISITOS
        </span>
        <button onClick={() => setAdding(a => !a)} style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, color: accent,
          background: 'none', border: 'none', cursor: 'pointer', padding: 0,
        }}>
          {adding ? '✕ Cancelar' : '+ Adicionar'}
        </button>
      </div>

      {/* Lista de pré-requisitos desta página */}
      {prereqs.length === 0 && !adding && (
        <div style={{ fontSize: 11, color: ink2, fontStyle: 'italic', marginBottom: 4 }}>
          Nenhum pré-requisito configurado.
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: prereqs.length ? 6 : 0 }}>
        {prereqs.map(r => (
          <div key={r.id} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: dark ? '#211D16' : '#EDE7D9',
            border: `1px solid ${border}`, borderRadius: 3, padding: '4px 8px',
          }}>
            <span style={{ fontSize: 13, flexShrink: 0 }}>{r.icon ?? '📄'}</span>
            <span style={{ flex: 1, fontSize: 12, color: ink, fontStyle: 'italic',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {r.title}
            </span>
            {r.status_value && (
              <span style={{ fontSize: 9, color: ink2, fontFamily: 'var(--font-mono)',
                border: `1px solid ${border}`, borderRadius: 2, padding: '1px 5px', flexShrink: 0 }}>
                {r.status_value}
              </span>
            )}
            <button onClick={() => removePrereq(r.id)} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: dark ? '#8A4A3A' : '#9B3A2A', fontSize: 13, padding: '0 2px', flexShrink: 0,
            }}>×</button>
          </div>
        ))}
      </div>

      {/* Buscador inline para adicionar */}
      {adding && (
        <div style={{ marginBottom: 6 }}>
          <input
            autoFocus
            placeholder="Buscar página do projecto…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            style={{
              width: '100%', boxSizing: 'border-box',
              background: dark ? '#211D16' : '#EDE7D9',
              border: `1px solid ${border}`, borderRadius: 3,
              color: ink, fontSize: 12, padding: '5px 8px',
              fontFamily: 'var(--font-mono)', outline: 'none',
            }}
          />
          {filtered.map(p => (
            <button key={p.id} onClick={() => addPrereq(p.id)} style={{
              display: 'flex', alignItems: 'center', gap: 7,
              width: '100%', padding: '5px 8px', background: 'none',
              border: 'none', borderBottom: `1px solid ${border}`,
              cursor: 'pointer', textAlign: 'left',
            }}
              onMouseEnter={e => (e.currentTarget.style.background = dark ? '#2A2520' : '#EDE7D9')}
              onMouseLeave={e => (e.currentTarget.style.background = 'none')}
            >
              <span style={{ fontSize: 13 }}>{p.icon ?? '📄'}</span>
              <span style={{ fontSize: 12, color: ink }}>{p.title}</span>
            </button>
          ))}
          {query && filtered.length === 0 && (
            <div style={{ fontSize: 11, color: ink2, padding: '4px 0', fontStyle: 'italic' }}>
              Nenhuma página encontrada.
            </div>
          )}
        </div>
      )}

      {/* Dependentes: páginas que requerem esta */}
      {dependents.length > 0 && (
        <>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em',
            color: ink2, marginBottom: 4, marginTop: 6 }}>
            DESBLOQUEIA
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {dependents.map(d => (
              <span key={d.id} style={{
                fontSize: 11, color: ink2, fontStyle: 'italic',
                background: dark ? '#211D16' : '#EDE7D9',
                border: `1px solid ${border}`, borderRadius: 3, padding: '2px 7px',
              }}>
                {d.icon ?? '📄'} {d.title}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── Backlinks ─────────────────────────────────────────────────────────────────

function BacklinksPanel({ page, dark }: { page: Page; dark: boolean }) {
  const [incoming, setIncoming] = useState<any[]>([])
  const [outgoing, setOutgoing] = useState<any[]>([])
  const [allPages, setAllPages] = useState<any[]>([])
  const [expanded, setExpanded] = useState(false)
  const [addMode,  setAddMode]  = useState<'in' | 'out' | null>(null)
  const [query,    setQuery]    = useState('')
  const { pushToast } = useAppStore()

  const bg     = dark ? '#1A1710' : '#F5F0E8'
  const border = dark ? '#3A3020' : '#D4C9B4'
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'

  const load = () => {
    fromIpc<any[]>(() => db().backlinks.list(page.id), 'listBacklinks')
      .then(r => r.match(data => setIncoming(data), _e => {}))
    fromIpc<any[]>(() => db().backlinks.listOutgoing(page.id), 'listOutgoing')
      .then(r => r.match(data => setOutgoing(data), _e => {}))
  }

  useEffect(() => { load() }, [page.id])

  useEffect(() => {
    if (!addMode) return
    fromIpc<any[]>(() => db().pages.search('', 50), 'searchPagesForBacklinks')
      .then(r => r.match(data => setAllPages(data.filter((p: any) => p.id !== page.id)), _e => {}))
  }, [addMode, page.id])

  const addLink = async (targetId: number) => {
    const [src, tgt] = addMode === 'out' ? [page.id, targetId] : [targetId, page.id]
    await fromIpc<unknown>(() => db().backlinks.add(src, tgt), 'addBacklink')
    setQuery(''); setAddMode(null); load()
  }

  const removeIncoming = async (sourceId: number) => {
    await fromIpc<unknown>(() => db().backlinks.remove(sourceId, page.id), 'removeBacklinkIn')
    load()
  }
  const removeOutgoing = async (targetId: number) => {
    await fromIpc<unknown>(() => db().backlinks.remove(page.id, targetId), 'removeBacklinkOut')
    load()
  }

  const existing = addMode === 'out'
    ? new Set(outgoing.map((p: any) => p.id))
    : new Set(incoming.map((p: any) => p.id))

  const filtered = allPages.filter(p =>
    !existing.has(p.id) &&
    (!query.trim() || p.title.toLowerCase().includes(query.toLowerCase()) || (p.project_name ?? '').toLowerCase().includes(query.toLowerCase()))
  ).slice(0, 8)

  const hasContent = incoming.length > 0 || outgoing.length > 0

  if (!hasContent && !expanded) {
    return (
      <div style={{ padding: '4px 16px 0', background: bg, borderTop: `1px solid ${border}` }}>
        <button onClick={() => setExpanded(true)} style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em',
          color: ink2, background: 'none', border: 'none', cursor: 'pointer', padding: '6px 0',
        }}>
          + Backlinks
        </button>
      </div>
    )
  }

  const PageChip = ({ p, onRemove }: { p: any; onRemove: () => void }) => (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 5,
      background: dark ? '#211D16' : '#EDE7D9',
      border: `1px solid ${border}`, borderRadius: 3, padding: '3px 7px',
    }}>
      <span style={{ fontSize: 12 }}>{p.icon ?? '📄'}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11, color: ink, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {p.title}
        </div>
        {p.project_name && (
          <div style={{ fontSize: 9, color: ink2, fontFamily: 'var(--font-mono)' }}>{p.project_name}</div>
        )}
      </div>
      <button onClick={onRemove} style={{
        background: 'none', border: 'none', cursor: 'pointer',
        color: dark ? '#8A4A3A' : '#9B3A2A', fontSize: 13, padding: '0 2px', flexShrink: 0,
      }}>×</button>
    </div>
  )

  const SearchDropdown = () => (
    <div style={{ marginTop: 4 }}>
      <input autoFocus placeholder="Buscar página…" value={query}
        onChange={e => setQuery(e.target.value)}
        style={{
          width: '100%', boxSizing: 'border-box',
          background: dark ? '#211D16' : '#EDE7D9',
          border: `1px solid ${border}`, borderRadius: 3,
          color: ink, fontSize: 12, padding: '5px 8px',
          fontFamily: 'var(--font-mono)', outline: 'none',
        }}
      />
      {filtered.map(p => (
        <button key={p.id} onClick={() => addLink(p.id)} style={{
          display: 'flex', alignItems: 'center', gap: 7,
          width: '100%', padding: '5px 8px', background: 'none',
          border: 'none', borderBottom: `1px solid ${border}`,
          cursor: 'pointer', textAlign: 'left',
        }}
          onMouseEnter={e => (e.currentTarget.style.background = dark ? '#2A2520' : '#EDE7D9')}
          onMouseLeave={e => (e.currentTarget.style.background = 'none')}
        >
          <span style={{ fontSize: 13 }}>{p.icon ?? '📄'}</span>
          <div>
            <div style={{ fontSize: 12, color: ink }}>{p.title}</div>
            {p.project_name && <div style={{ fontSize: 9, color: ink2, fontFamily: 'var(--font-mono)' }}>{p.project_name}</div>}
          </div>
        </button>
      ))}
      {query && filtered.length === 0 && (
        <div style={{ fontSize: 11, color: ink2, padding: '4px 0', fontStyle: 'italic' }}>Nenhuma página encontrada.</div>
      )}
    </div>
  )

  return (
    <div style={{ background: bg, borderTop: `1px solid ${border}`, padding: '8px 16px 10px' }}>
      {/* Referenciado por (incoming) */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em', color: ink2, flex: 1 }}>
          ← REFERENCIADO POR{incoming.length > 0 ? ` (${incoming.length})` : ''}
        </span>
        <button onClick={() => { setAddMode(addMode === 'in' ? null : 'in'); setQuery('') }} style={{
          fontSize: 10, color: accent, background: 'none', border: 'none', cursor: 'pointer',
          fontFamily: 'var(--font-mono)',
        }}>
          {addMode === 'in' ? '✕' : '+'}
        </button>
      </div>
      {incoming.length === 0 && addMode !== 'in' && (
        <div style={{ fontSize: 11, color: ink2, fontStyle: 'italic', marginBottom: 6 }}>—</div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 4 }}>
        {incoming.map(p => (
          <PageChip key={p.id} p={p} onRemove={() => removeIncoming(p.id)} />
        ))}
      </div>
      {addMode === 'in' && <SearchDropdown />}

      {/* Esta página referencia (outgoing) */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, marginTop: 8 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em', color: ink2, flex: 1 }}>
          → REFERENCIA{outgoing.length > 0 ? ` (${outgoing.length})` : ''}
        </span>
        <button onClick={() => { setAddMode(addMode === 'out' ? null : 'out'); setQuery('') }} style={{
          fontSize: 10, color: accent, background: 'none', border: 'none', cursor: 'pointer',
          fontFamily: 'var(--font-mono)',
        }}>
          {addMode === 'out' ? '✕' : '+'}
        </button>
      </div>
      {outgoing.length === 0 && addMode !== 'out' && (
        <div style={{ fontSize: 11, color: ink2, fontStyle: 'italic' }}>—</div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {outgoing.map(p => (
          <PageChip key={p.id} p={p} onRemove={() => removeOutgoing(p.id)} />
        ))}
      </div>
      {addMode === 'out' && <SearchDropdown />}
    </div>
  )
}

interface Props {
  page:    Page
  project: Project
  dark:    boolean
  onBack:  () => void
}

// ── Painel de propriedades ────────────────────────────────────────────────────

interface PropPanelProps {
  page:       Page
  properties: ProjectProperty[]
  dark:       boolean
  projectId:  number
  onChanged:  () => void
}

function PropPanel({ page, properties, dark, projectId, onChanged }: PropPanelProps) {
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const bg     = dark ? '#1A1610' : '#F5F0E8'

  // Valores locais por property_id
  const [localValues, setLocalValues] = useState<Record<number, PagePropValue>>({})

  // Opções para select/multi_select
  const [propOptions, setPropOptions] = useState<Record<number, PropOption[]>>({})

  // Inicializa ao abrir página
  useEffect(() => {
    const init: Record<number, PagePropValue> = {}
    page.prop_values?.forEach(pv => { init[pv.property_id] = pv })
    setLocalValues(init)
  }, [page.id])

  // Busca opções
  useEffect(() => {
    const selects = properties.filter(p =>
      p.prop_type === 'select' || p.prop_type === 'multi_select'
    )
    if (selects.length === 0) return
    ;(async () => {
      const map: Record<number, PropOption[]> = {}
      await Promise.all(selects.map(async p => {
        const r = await fromIpc<PropOption[]>(() => db().properties.getOptions(p.id), 'getOptions')
        map[p.id] = r.isOk() ? r.value : []
      }))
      setPropOptions(map)
    })()
  }, [properties])

  const setPropValue = useCallback(async (propId: number, field: string, value: any) => {
    // Atualiza local imediatamente (optimistic)
    setLocalValues(prev => ({
      ...prev,
      [propId]: { ...(prev[propId] ?? {} as any), property_id: propId, [field]: value },
    }))
    // Persiste
    const result = await fromIpc<unknown>(
      () => db().pages.setPropValue({ page_id: page.id, property_id: propId, [field]: value }),
      'setPropValue',
    )
    if (result.isOk()) onChanged()
  }, [page.id, onChanged])

  if (properties.length === 0) return null

  return (
    <div className="page-props-panel" style={{ borderColor: border, background: bg }}>
      {properties.map(prop => {
        const pv      = localValues[prop.id]
        const options = propOptions[prop.id] ?? []
        return (
          <div key={prop.id} className="page-prop-row">
            <span className="page-prop-label" style={{ color: ink2 }}>{prop.name}</span>
            <div className="page-prop-value">
              <PropValueEditor
                prop={prop} pv={pv} options={options}
                onSet={setPropValue}
                dark={dark} ink={ink} ink2={ink2} border={border} cardBg={cardBg}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Editor de valor por tipo ──────────────────────────────────────────────────

interface EditorProps {
  prop:    ProjectProperty
  pv:      PagePropValue | undefined
  options: PropOption[]
  onSet:   (propId: number, field: string, value: any) => void
  dark:    boolean
  ink:     string
  ink2:    string
  border:  string
  cardBg:  string
}

function PropValueEditor({ prop, pv, options, onSet, dark, ink, ink2, border, cardBg }: EditorProps) {
  const [editing,  setEditing]  = useState(false)
  const [textVal,  setTextVal]  = useState(pv?.value_text ?? '')
  const [numVal,   setNumVal]   = useState(pv?.value_num != null ? String(pv.value_num) : '')

  // Sync local state ao trocar de página
  useEffect(() => {
    setTextVal(pv?.value_text ?? '')
    setNumVal(pv?.value_num != null ? String(pv.value_num) : '')
    setEditing(false)
  }, [pv?.value_text, pv?.value_num])

  // ── select ────────────────────────────────────────────────────────────────
  if (prop.prop_type === 'select') {
    if (options.length === 0)
      return <span style={{ color: border, fontSize: 11, fontStyle: 'italic' }}>—</span>
    return (
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {options.map(opt => {
          const active = pv?.value_text === opt.label
          return (
            <button
              key={opt.id}
              onClick={() => onSet(prop.id, 'value_text', active ? null : opt.label)}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 9,
                padding: '2px 8px', borderRadius: 20, cursor: 'pointer',
                border: `1px solid ${active ? (opt.color ?? ink2) : border}`,
                background: active ? (opt.color ? opt.color + '22' : (dark ? '#3A3020' : '#EDE7D9')) : 'transparent',
                color: active ? (opt.color ?? ink) : ink2,
                transition: 'all 80ms',
              }}
            >
              {opt.label}
            </button>
          )
        })}
      </div>
    )
  }

  // ── multi_select ──────────────────────────────────────────────────────────
  if (prop.prop_type === 'multi_select') {
    const selected: string[] = (() => {
      try { return JSON.parse(pv?.value_json ?? '[]') } catch { return [] }
    })()
    if (options.length === 0) {
      return <span style={{ color: border, fontSize: 11, fontStyle: 'italic' }}>—</span>
    }
    return (
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {options.map(opt => {
          const active = selected.includes(opt.label)
          const next   = active ? selected.filter(l => l !== opt.label) : [...selected, opt.label]
          return (
            <button
              key={opt.id}
              onClick={() => onSet(prop.id, 'value_json', JSON.stringify(next))}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 9,
                padding: '2px 8px', borderRadius: 20, cursor: 'pointer',
                border: `1px solid ${active ? (opt.color ?? ink2) : border}`,
                background: active ? (opt.color ? opt.color + '22' : (dark ? '#3A3020' : '#EDE7D9')) : 'transparent',
                color: active ? (opt.color ?? ink) : ink2,
                transition: 'all 80ms',
              }}
            >
              {opt.label}
            </button>
          )
        })}
      </div>
    )
  }

  // ── text / url ────────────────────────────────────────────────────────────
  if (prop.prop_type === 'text' || prop.prop_type === 'url') {
    const save = () => {
      setEditing(false)
      onSet(prop.id, 'value_text', textVal.trim() || null)
    }
    if (editing) {
      return (
        <input
          autoFocus
          className="prop-text-input"
          value={textVal}
          onChange={e => setTextVal(e.target.value)}
          onBlur={save}
          onKeyDown={e => {
            if (e.key === 'Enter')  save()
            if (e.key === 'Escape') { setEditing(false); setTextVal(pv?.value_text ?? '') }
          }}
          style={{ borderColor: border, color: ink }}
        />
      )
    }
    return (
      <button className="prop-text-btn"
        onClick={() => { setEditing(true); setTextVal(pv?.value_text ?? '') }}
        style={{ color: pv?.value_text ? ink : border }}>
        {pv?.value_text || <span style={{ fontStyle: 'italic' }}>—</span>}
      </button>
    )
  }

  // ── number ────────────────────────────────────────────────────────────────
  if (prop.prop_type === 'number') {
    const save = () => {
      setEditing(false)
      const v = parseFloat(numVal)
      onSet(prop.id, 'value_num', isNaN(v) ? null : v)
    }
    if (editing) {
      return (
        <input
          autoFocus type="number"
          className="prop-text-input"
          value={numVal}
          onChange={e => setNumVal(e.target.value)}
          onBlur={save}
          onKeyDown={e => {
            if (e.key === 'Enter')  save()
            if (e.key === 'Escape') { setEditing(false); setNumVal(pv?.value_num != null ? String(pv.value_num) : '') }
          }}
          style={{ borderColor: border, color: ink, width: 80 }}
        />
      )
    }
    return (
      <button className="prop-text-btn"
        onClick={() => setEditing(true)}
        style={{ color: pv?.value_num != null ? ink : border }}>
        {pv?.value_num != null ? pv.value_num : <span style={{ fontStyle: 'italic' }}>—</span>}
      </button>
    )
  }

  // ── date ──────────────────────────────────────────────────────────────────
  if (prop.prop_type === 'date') {
    return (
      <input
        type="date"
        className="prop-date-input"
        value={pv?.value_date ?? ''}
        onChange={e => onSet(prop.id, 'value_date', e.target.value || null)}
        style={{ borderColor: border, color: pv?.value_date ? ink : border, colorScheme: dark ? 'dark' : 'light' }}
      />
    )
  }

  // ── checkbox ──────────────────────────────────────────────────────────────
  if (prop.prop_type === 'checkbox') {
    const checked = !!pv?.value_bool
    return (
      <button
        className="prop-checkbox"
        onClick={() => onSet(prop.id, 'value_bool', checked ? 0 : 1)}
        style={{ color: checked ? (dark ? '#6A9060' : '#4A6741') : ink2, borderColor: checked ? (dark ? '#6A9060' : '#4A6741') : border }}
      >
        {checked ? '☑' : '☐'}
      </button>
    )
  }

  // ── color ─────────────────────────────────────────────────────────────────
  if (prop.prop_type === 'color') {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ width: 16, height: 16, borderRadius: 2, background: pv?.value_text ?? border, border: `1px solid ${border}` }} />
        <input
          type="color"
          value={pv?.value_text ?? '#888888'}
          onChange={e => onSet(prop.id, 'value_text', e.target.value)}
          style={{ width: 24, height: 20, border: 'none', padding: 0, background: 'transparent', cursor: 'pointer' }}
        />
      </div>
    )
  }

  return null
}

// ── PageView principal ────────────────────────────────────────────────────────

export const PageView: React.FC<Props> = ({ page, project, dark, onBack }) => {
  const { projectProperties, loadPages } = useAppStore()
  const [saving,       setSaving]       = useState(false)
  const [lastSaved,    setLastSaved]    = useState<Date | null>(null)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleVal,     setTitleVal]     = useState(page.title)
  const [iconVal, setIconVal] = useState(page.icon ?? '📄')

  // Sync title/icon if page prop changes (e.g., store reload)
  useEffect(() => {
    if (!editingTitle) setTitleVal(page.title)
    setIconVal(page.icon ?? '📄')
  }, [page.title, page.icon])

  const color  = project.color ?? '#8B7355'
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  const { pushToast } = useAppStore()

  const handleSave = useCallback(async (bodyJson: string) => {
    setSaving(true)
    const result = await fromIpc<Page>(
      () => db().pages.update({ id: page.id, body_json: bodyJson }),
      'page:save',
    )
    result.match(
      () => { setLastSaved(new Date()); log.debug('page saved', { id: page.id }) },
      e  => { log.error('page save failed', { error: e.message }); pushToast({ kind: 'error', title: 'Erro ao guardar página', detail: e.message }) },
    )
    setSaving(false)
  }, [page.id, pushToast])

  const saveTitle = useCallback(async () => {
    setEditingTitle(false)
    const t = titleVal.trim() || 'Sem título'
    setTitleVal(t)
    const result = await fromIpc<Page>(
      () => db().pages.update({ id: page.id, title: t }),
      'page:saveTitle',
    )
    if (result.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao guardar título', detail: result.error.message })
    }
    loadPages(project.id)
  }, [titleVal, page.id, project.id, loadPages, pushToast])


  const handleDelete = useCallback(async () => {
    if (!window.confirm(`Excluir "${page.title}"? Esta ação pode ser desfeita restaurando do lixo.`)) return
    const result = await fromIpc<unknown>(
      () => db().pages.delete(page.id),
      'page:delete',
    )
    if (result.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao excluir página', detail: result.error.message })
      return
    }
    loadPages(project.id)
    onBack()
  }, [page.id, page.title, project.id, loadPages, onBack, pushToast])

  const formattedDate = (() => {
    try { return new Date(page.created_at).toLocaleDateString('pt-BR') } catch { return '' }
  })()

  return (
    <div className="page-view page-view--editor">

      {/* Cabeçalho */}
      <div className="page-header" style={{ borderColor: border, background: cardBg }}>
        <CosmosLayer width={900} height={90}
          seed={`page_${page.id}`} density="low" dark={dark}
          style={{ opacity: 0.4 }} />
        <div className="page-header-bar" style={{ background: color }} />

        <div className="page-header-content" style={{ position: 'relative', zIndex: 2 }}>
          {/* Ícone editável */}
          <IconPicker
            value={iconVal}
            onChange={async (i) => {
              setIconVal(i)
              const result = await fromIpc<Page>(
                () => db().pages.update({ id: page.id, icon: i }),
                'page:saveIcon',
              )
              if (result.isErr())
                pushToast({ kind: 'error', title: 'Erro ao guardar ícone', detail: result.error.message })
              else loadPages(project.id)
            }}
            dark={dark}
            size={28}
            suggestFor={titleVal}
          />

          <div style={{ flex: 1, overflow: 'hidden' }}>
            {/* Título editável */}
            {editingTitle ? (
              <input
                autoFocus
                className="page-title-input"
                value={titleVal}
                onChange={e => setTitleVal(e.target.value)}
                onBlur={saveTitle}
                onKeyDown={e => {
                  if (e.key === 'Enter')  saveTitle()
                  if (e.key === 'Escape') { setEditingTitle(false); setTitleVal(page.title) }
                }}
                style={{ color: ink, borderColor: border }}
              />
            ) : (
              <h1
                className="page-title page-title--editable"
                style={{ color: ink }}
                onClick={() => setEditingTitle(true)}
                title="Clique para renomear"
              >
                {titleVal}
              </h1>
            )}

            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 3, flexWrap: 'wrap' }}>
              {formattedDate && (
                <span style={{ fontSize: 10, color: ink2, letterSpacing: '0.05em' }}>
                  Criado em {formattedDate}
                </span>
              )}
              <span style={{
                fontSize: 10, color: ink2, letterSpacing: '0.05em',
                marginLeft: 'auto', fontStyle: 'italic',
              }}>
                {saving ? '💾 Salvando...'
                  : lastSaved
                    ? `✓ Salvo às ${lastSaved.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`
                  : ''}
              </span>
            </div>
          </div>

          {/* Ações */}
          <button
            className="btn btn-ghost btn-sm"
            onClick={handleDelete}
            title="Excluir página"
            style={{ color: dark ? '#8A4A3A' : '#8B3A2A', flexShrink: 0, fontSize: 14 }}
          >
            🗑
          </button>
        </div>
      </div>

      {/* Painel de propriedades */}
      {projectProperties.length > 0 && (
        <PropPanel
          page={page}
          properties={projectProperties}
          dark={dark}
          projectId={project.id}
          onChanged={() => loadPages(project.id)}
        />
      )}

      {/* Recursos vinculados */}
      <PageResourcePanel pageId={page.id} dark={dark} />

      {/* Actividades & Lembretes */}
      <PageEventsPanel page={page} project={project} dark={dark} />

      {/* Tags Globais */}
      <GlobalTagPanel pageId={page.id} dark={dark} />

      {/* Pré-requisitos (apenas projetos académicos) */}
      {project.project_type === 'academic' && (
        <PrerequisitesPanel page={page} project={project} dark={dark} />
      )}

      {/* Backlinks */}
      <BacklinksPanel page={page} dark={dark} />

      {/* Editor */}
      <div className="page-editor-area">
        <EditorFrame
          content={page.body_json}
          dark={dark}
          onSave={handleSave}
          onReady={() => log.debug('editor ready', { page: page.id })}
        />
      </div>
    </div>
  )
}
