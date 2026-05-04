/* ============================================================
   AETHER — Editor WYSIWYG
   TipTap sobre ProseMirror. Sempre renderizado — o usuário
   nunca vê símbolos Markdown, apenas o resultado formatado.
   Parágrafos indentados estilo livro impresso.
   Cursor estilo máquina de escrever.
   Auto-save com debounce 500ms.
   ============================================================ */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Typography from '@tiptap/extension-typography'
import Placeholder from '@tiptap/extension-placeholder'
import { TypographyPanel } from './TypographyPanel'
import { SearchReplace, searchKey } from '../lib/searchReplace'
import * as cmd from '../lib/tauri'
import type { Character, ChapterStatus, WorldNote } from '../types'
import type { ActiveChapter } from './Binder'

// ----------------------------------------------------------
//  Scratchpad — painel de notas lateral por capítulo (3.4/3.5)
// ----------------------------------------------------------

interface ScratchpadProps {
  chapter: ActiveChapter
  onError: (msg: string) => void
  /** Quando false, oculta o header próprio (usado dentro do SplitPanel) */
  showHeader?: boolean
}

function Scratchpad({ chapter, onError, showHeader = true }: ScratchpadProps) {
  const [content, setContent] = useState('')
  const [loaded, setLoaded] = useState(false)
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const chapterRef = useRef(chapter)
  chapterRef.current = chapter

  useEffect(() => {
    setLoaded(false)
    setContent('')
    if (saveTimer.current) clearTimeout(saveTimer.current)

    cmd.readScratchpad(chapter.projectId, chapter.bookId, chapter.chapterId).then((result) => {
      if (result.ok) {
        setContent(result.data)
        setLoaded(true)
      } else {
        onError(`Erro ao carregar scratchpad: ${result.error.message}`)
        setLoaded(true)
      }
    })

    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current)
    }
  }, [chapter.chapterId, chapter.bookId, chapter.projectId])

  function handleChange(value: string) {
    setContent(value)
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(async () => {
      const { projectId, bookId, chapterId } = chapterRef.current
      const result = await cmd.saveScratchpad(projectId, bookId, chapterId, value)
      if (!result.ok) {
        onError(`Erro ao salvar scratchpad: ${result.error.message}`)
      }
    }, 600)
  }

  const inner = (
    <>
      {showHeader && (
        <div style={{
          height: 'var(--topbar-h)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 14px',
          borderBottom: '1px solid var(--rule)',
          flexShrink: 0,
        }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--ink-ghost)' }}>
            Notas
          </span>
        </div>
      )}
      <textarea
        value={content}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={loaded ? 'Notas para este capítulo...' : ''}
        disabled={!loaded}
        style={{
          flex: 1,
          width: '100%',
          padding: '14px',
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          fontSize: '13px',
          lineHeight: 1.65,
          color: 'var(--ink-light)',
          background: 'transparent',
          border: 'none',
          outline: 'none',
          resize: 'none',
          caretColor: 'var(--accent)',
          boxSizing: 'border-box',
        }}
      />
    </>
  )

  if (!showHeader) {
    // Quando embutido no SplitPanel, não precisa de wrapper próprio
    return <>{inner}</>
  }

  return (
    <div style={{
      width: '260px',
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      borderLeft: '1px solid var(--rule)',
      background: 'var(--paper-dark)',
      position: 'relative',
    }}>
      {inner}
    </div>
  )
}

// ----------------------------------------------------------
//  SplitPanel — contêiner do painel lateral com abas (3.4/4.6)
// ----------------------------------------------------------

type SplitTab = 'notas' | 'vinculos' | 'snapshots' | 'anotacoes'

interface SplitPanelProps {
  tab: SplitTab
  onTabChange: (tab: SplitTab) => void
  chapter: ActiveChapter
  wordCount: number
  onError: (msg: string) => void
  onSuccess: (msg: string) => void
}

function SplitPanel({ tab, onTabChange, chapter, wordCount, onError, onSuccess }: SplitPanelProps) {
  const tabStyle = (active: boolean): React.CSSProperties => ({
    fontFamily: 'var(--font-mono)',
    fontSize: '9px',
    textTransform: 'uppercase',
    letterSpacing: '0.12em',
    padding: '3px 8px',
    color: active ? 'var(--accent)' : 'var(--ink-ghost)',
    background: 'none',
    border: 'none',
    borderBottom: active ? '1px solid var(--accent)' : '1px solid transparent',
    cursor: 'pointer',
    transition: 'color var(--transition), border-color var(--transition)',
    whiteSpace: 'nowrap',
  })

  return (
    <div style={{
      width: '260px',
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      borderLeft: '1px solid var(--rule)',
      background: 'var(--paper-dark)',
    }}>
      {/* Abas — scrolláveis horizontalmente */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--rule)', height: '28px', alignItems: 'center', paddingLeft: '4px', overflowX: 'auto' }}>
        <button style={tabStyle(tab === 'notas')} onClick={() => onTabChange('notas')}>Notas</button>
        <button style={tabStyle(tab === 'vinculos')} onClick={() => onTabChange('vinculos')}>Vínculos</button>
        <button style={tabStyle(tab === 'snapshots')} onClick={() => onTabChange('snapshots')}>Histórico</button>
        <button style={tabStyle(tab === 'anotacoes')} onClick={() => onTabChange('anotacoes')}>Anotações</button>
      </div>

      {tab === 'notas' && <Scratchpad chapter={chapter} onError={onError} showHeader={false} />}
      {tab === 'vinculos' && <LinksPanel chapter={chapter} onError={onError} />}
      {tab === 'snapshots' && <SnapshotPanel chapter={chapter} wordCount={wordCount} onError={onError} onSuccess={onSuccess} />}
      {tab === 'anotacoes' && <AnnotationPanel chapter={chapter} onError={onError} />}
    </div>
  )
}

// ----------------------------------------------------------
//  LinksPanel — vínculos personagens/notas por capítulo (4.6)
// ----------------------------------------------------------

interface LinksPanelProps {
  chapter: ActiveChapter
  onError: (msg: string) => void
}

function LinksPanel({ chapter, onError }: LinksPanelProps) {
  const [characters, setCharacters] = useState<Character[]>([])
  const [notes, setNotes] = useState<WorldNote[]>([])
  const [characterIds, setCharacterIds] = useState<string[]>(chapter.characterIds ?? [])
  const [noteIds, setNoteIds] = useState<string[]>(chapter.noteIds ?? [])
  const [saving, setSaving] = useState(false)
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const chapterRef = useRef(chapter)
  chapterRef.current = chapter

  useEffect(() => {
    setCharacterIds(chapter.characterIds ?? [])
    setNoteIds(chapter.noteIds ?? [])
    // Carregar personagens e notas
    cmd.listCharacters(chapter.projectId).then((r) => { if (r.ok) setCharacters(r.data) })
    cmd.listWorldNotes(chapter.projectId).then((r) => { if (r.ok) setNotes(r.data) })
  }, [chapter.chapterId, chapter.projectId])

  function scheduleSync(newCharIds: string[], newNoteIds: string[]) {
    if (saveTimer.current) clearTimeout(saveTimer.current)
    setSaving(true)
    saveTimer.current = setTimeout(async () => {
      const { projectId, bookId, chapterId } = chapterRef.current
      const r = await cmd.updateChapterLinks(projectId, bookId, chapterId, newCharIds, newNoteIds)
      setSaving(false)
      if (!r.ok) onError(`Erro ao salvar vínculos: ${r.error.message}`)
    }, 600)
  }

  function toggleChar(id: string) {
    const next = characterIds.includes(id)
      ? characterIds.filter((x) => x !== id)
      : [...characterIds, id]
    setCharacterIds(next)
    scheduleSync(next, noteIds)
  }

  function toggleNote(id: string) {
    const next = noteIds.includes(id)
      ? noteIds.filter((x) => x !== id)
      : [...noteIds, id]
    setNoteIds(next)
    scheduleSync(characterIds, next)
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '10px 12px' }}>
      {/* Personagens */}
      {characters.length > 0 && (
        <div style={{ marginBottom: '16px' }}>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--ink-ghost)', margin: '0 0 8px' }}>Personagens</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {characters.map((c) => (
              <LinkChip key={c.id} label={c.name} sub={c.role ?? undefined} active={characterIds.includes(c.id)} onClick={() => toggleChar(c.id)} />
            ))}
          </div>
        </div>
      )}

      {/* Worldbuilding */}
      {notes.length > 0 && (
        <div>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--ink-ghost)', margin: '0 0 8px' }}>Mundo</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {notes.map((n) => (
              <LinkChip key={n.id} label={n.name} active={noteIds.includes(n.id)} onClick={() => toggleNote(n.id)} />
            ))}
          </div>
        </div>
      )}

      {characters.length === 0 && notes.length === 0 && (
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--ink-ghost)', letterSpacing: '0.04em', lineHeight: 1.6 }}>
          Crie personagens e notas de worldbuilding para vinculá-los a este capítulo.
        </p>
      )}

      {saving && (
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--ink-ghost)', letterSpacing: '0.06em', marginTop: '10px' }}>Salvando…</p>
      )}
    </div>
  )
}

function LinkChip({ label, sub, active, onClick }: { label: string; sub?: string; active: boolean; onClick: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '5px 8px',
        cursor: 'pointer',
        background: active ? 'transparent' : hovered ? 'var(--paper-darker)' : 'transparent',
        borderLeft: active ? '2px solid var(--accent)' : '2px solid transparent',
        transition: 'background var(--transition), border-color var(--transition)',
      }}
    >
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <p style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '12px', color: active ? 'var(--ink)' : 'var(--ink-light)', margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</p>
        {sub && <p style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--ink-ghost)', margin: 0, letterSpacing: '0.04em' }}>{sub}</p>}
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  SnapshotPanel — histórico de versões (5.5)
// ----------------------------------------------------------

interface SnapshotPanelProps {
  chapter: ActiveChapter
  wordCount: number
  onError: (msg: string) => void
  onSuccess: (msg: string) => void
}

function SnapshotPanel({ chapter, wordCount: _wordCount, onError, onSuccess }: SnapshotPanelProps) {
  const [snapshots, setSnapshots] = useState<import('../types').SnapshotMeta[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [labelInput, setLabelInput] = useState('')
  const [showLabelInput, setShowLabelInput] = useState(false)
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [previewContent, setPreviewContent] = useState('')

  useEffect(() => {
    setPreviewId(null)
    setPreviewContent('')
    load()
  }, [chapter.chapterId, chapter.bookId, chapter.projectId])

  async function load() {
    setLoading(true)
    const r = await cmd.listSnapshots(chapter.projectId, chapter.bookId, chapter.chapterId)
    if (r.ok) setSnapshots(r.data)
    else onError(`Erro ao carregar snapshots: ${r.error.message}`)
    setLoading(false)
  }

  async function handleCreate() {
    setCreating(true)
    const label = labelInput.trim() || undefined
    const r = await cmd.createSnapshot(chapter.projectId, chapter.bookId, chapter.chapterId, label)
    setCreating(false)
    setShowLabelInput(false)
    setLabelInput('')
    if (r.ok) {
      setSnapshots((prev) => [r.data, ...prev])
      onSuccess('Snapshot criado.')
    } else {
      onError(`Erro: ${r.error.message}`)
    }
  }

  async function handlePreview(snapshotId: string) {
    if (previewId === snapshotId) {
      setPreviewId(null)
      setPreviewContent('')
      return
    }
    const r = await cmd.loadSnapshotContent(chapter.projectId, chapter.bookId, snapshotId)
    if (r.ok) {
      setPreviewId(snapshotId)
      setPreviewContent(r.data)
    }
  }

  async function handleRestore(snapshotId: string) {
    if (!confirm('Restaurar este snapshot? O conteúdo atual será substituído (crie um snapshot antes se quiser preservá-lo).')) return
    const r = await cmd.restoreSnapshot(chapter.projectId, chapter.bookId, chapter.chapterId, snapshotId)
    if (r.ok) {
      onSuccess('Snapshot restaurado. Recarregue o capítulo.')
      // Recarregar a página não é ideal — orientar o usuário
    } else {
      onError(`Erro ao restaurar: ${r.error.message}`)
    }
  }

  async function handleDelete(snapshotId: string) {
    const r = await cmd.deleteSnapshot(chapter.projectId, chapter.bookId, snapshotId)
    if (r.ok) {
      setSnapshots((prev) => prev.filter((s) => s.id !== snapshotId))
      if (previewId === snapshotId) { setPreviewId(null); setPreviewContent('') }
    } else {
      onError(`Erro ao deletar: ${r.error.message}`)
    }
  }

  const monoSm: React.CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: '9px', letterSpacing: '0.08em', color: 'var(--ink-ghost)' }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Botão criar snapshot */}
      <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--rule)', flexShrink: 0 }}>
        {showLabelInput ? (
          <form onSubmit={(e) => { e.preventDefault(); handleCreate() }} style={{ display: 'flex', gap: '4px' }}>
            <input
              autoFocus
              value={labelInput}
              onChange={(e) => setLabelInput(e.target.value)}
              placeholder="Rótulo (opcional)"
              onKeyDown={(e) => { if (e.key === 'Escape') setShowLabelInput(false) }}
              style={{
                flex: 1, fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '12px',
                background: 'var(--paper)', border: '1px solid var(--rule)', borderRadius: 'var(--radius)',
                color: 'var(--ink)', padding: '3px 6px', outline: 'none', minWidth: 0,
              }}
            />
            <button type="submit" disabled={creating} className="btn btn-sm" style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', letterSpacing: '0.06em', padding: '3px 8px' }}>
              {creating ? '…' : 'Criar'}
            </button>
          </form>
        ) : (
          <button
            onClick={() => setShowLabelInput(true)}
            style={{
              ...monoSm,
              background: 'none', border: '1px solid var(--rule)', borderRadius: 'var(--radius)',
              cursor: 'pointer', padding: '4px 10px', width: '100%', textAlign: 'center',
              color: 'var(--ink-faint)', textTransform: 'uppercase',
            }}
          >
            + Novo Snapshot
          </button>
        )}
      </div>

      {/* Lista de snapshots */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '6px 0' }}>
        {loading && <p style={{ ...monoSm, padding: '10px 12px', animation: 'blink 1.2s ease infinite' }}>· · ·</p>}
        {!loading && snapshots.length === 0 && (
          <p style={{ ...monoSm, padding: '10px 12px', lineHeight: 1.6 }}>
            Nenhum snapshot ainda. Crie um para preservar o estado atual.
          </p>
        )}
        {snapshots.map((s) => (
          <div key={s.id} style={{ borderBottom: '1px solid var(--rule)' }}>
            <div
              style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                padding: '7px 10px', cursor: 'pointer',
                background: previewId === s.id ? 'var(--paper-darker)' : 'transparent',
              }}
              onClick={() => handlePreview(s.id)}
            >
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--ink-ghost)', margin: 0, letterSpacing: '0.06em' }}>
                  {formatSnapshotDate(s.created_at)}
                </p>
                {s.label && (
                  <p style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '11px', color: 'var(--ink-faint)', margin: '1px 0 0', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {s.label}
                  </p>
                )}
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--ink-ghost)', margin: '1px 0 0' }}>
                  {s.word_count} {s.word_count === 1 ? 'palavra' : 'palavras'}
                </p>
              </div>
              <div style={{ display: 'flex', gap: '3px', flexShrink: 0 }}>
                <button
                  onClick={(e) => { e.stopPropagation(); handleRestore(s.id) }}
                  title="Restaurar este snapshot"
                  style={{ ...monoSm, background: 'none', border: 'none', cursor: 'pointer', padding: '2px 5px', color: 'var(--accent)' }}
                >↩</button>
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(s.id) }}
                  title="Apagar snapshot"
                  style={{ ...monoSm, background: 'none', border: 'none', cursor: 'pointer', padding: '2px 5px', color: 'var(--ink-ghost)' }}
                >×</button>
              </div>
            </div>
            {previewId === s.id && (
              <div style={{ padding: '6px 10px 10px', borderTop: '1px solid var(--rule)', background: 'var(--paper-darker)' }}>
                <p style={{
                  fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '11px',
                  color: 'var(--ink-faint)', margin: 0, lineHeight: 1.6,
                  whiteSpace: 'pre-wrap',
                  overflow: 'hidden',
                  display: '-webkit-box',
                  WebkitLineClamp: 6,
                  WebkitBoxOrient: 'vertical',
                }}>
                  {previewContent.trim() || '(vazio)'}
                </p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function formatSnapshotDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })
    + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

// ----------------------------------------------------------
//  AnnotationPanel — anotações inline (5.6)
// ----------------------------------------------------------

interface AnnotationPanelProps {
  chapter: ActiveChapter
  onError: (msg: string) => void
}

function AnnotationPanel({ chapter, onError }: AnnotationPanelProps) {
  const [annotations, setAnnotations] = useState<import('../types').Annotation[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [newText, setNewText] = useState('')
  const [newQuote, setNewQuote] = useState('')

  useEffect(() => {
    setShowForm(false)
    setNewText('')
    setNewQuote('')
    load()
  }, [chapter.chapterId, chapter.bookId, chapter.projectId])

  async function load() {
    setLoading(true)
    const r = await cmd.listAnnotations(chapter.projectId, chapter.bookId, chapter.chapterId)
    if (r.ok) setAnnotations(r.data)
    else onError(`Erro ao carregar anotações: ${r.error.message}`)
    setLoading(false)
  }

  async function handleCreate() {
    if (!newText.trim()) return
    const r = await cmd.createAnnotation(
      chapter.projectId, chapter.bookId, chapter.chapterId,
      newText.trim(), newQuote.trim()
    )
    if (r.ok) {
      setAnnotations((prev) => [...prev, r.data])
      setShowForm(false)
      setNewText('')
      setNewQuote('')
    } else {
      onError(`Erro: ${r.error.message}`)
    }
  }

  async function handleResolveToggle(ann: import('../types').Annotation) {
    const r = await cmd.updateAnnotation(
      chapter.projectId, chapter.bookId, chapter.chapterId,
      ann.id, ann.text, !ann.resolved
    )
    if (r.ok) setAnnotations((prev) => prev.map((a) => a.id === ann.id ? r.data : a))
    else onError(`Erro: ${r.error.message}`)
  }

  async function handleDelete(id: string) {
    const r = await cmd.deleteAnnotation(chapter.projectId, chapter.bookId, chapter.chapterId, id)
    if (r.ok) setAnnotations((prev) => prev.filter((a) => a.id !== id))
    else onError(`Erro: ${r.error.message}`)
  }

  const monoSm: React.CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: '9px', letterSpacing: '0.08em', color: 'var(--ink-ghost)' }
  const active = annotations.filter((a) => !a.resolved)
  const resolved = annotations.filter((a) => a.resolved)

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Botão criar */}
      <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--rule)', flexShrink: 0 }}>
        {showForm ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
            <input
              autoFocus
              value={newQuote}
              onChange={(e) => setNewQuote(e.target.value)}
              placeholder='Trecho citado (opcional)'
              style={{
                fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '11px',
                background: 'var(--paper)', border: '1px solid var(--rule)', borderRadius: 'var(--radius)',
                color: 'var(--ink-faint)', padding: '3px 6px', outline: 'none',
              }}
            />
            <textarea
              value={newText}
              onChange={(e) => setNewText(e.target.value)}
              placeholder='Anotação...'
              rows={3}
              style={{
                fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '12px',
                background: 'var(--paper)', border: '1px solid var(--rule)', borderRadius: 'var(--radius)',
                color: 'var(--ink)', padding: '4px 6px', outline: 'none', resize: 'none',
              }}
            />
            <div style={{ display: 'flex', gap: '4px', justifyContent: 'flex-end' }}>
              <button onClick={() => setShowForm(false)} className="btn btn-ghost btn-sm" style={monoSm}>Cancelar</button>
              <button onClick={handleCreate} className="btn btn-sm" style={{ ...monoSm, color: 'var(--accent)' }}>Salvar</button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowForm(true)}
            style={{
              ...monoSm, background: 'none', border: '1px solid var(--rule)', borderRadius: 'var(--radius)',
              cursor: 'pointer', padding: '4px 10px', width: '100%', textAlign: 'center',
              color: 'var(--ink-faint)', textTransform: 'uppercase',
            }}
          >
            + Nova Anotação
          </button>
        )}
      </div>

      {/* Lista */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '6px 0' }}>
        {loading && <p style={{ ...monoSm, padding: '10px 12px', animation: 'blink 1.2s ease infinite' }}>· · ·</p>}
        {!loading && annotations.length === 0 && (
          <p style={{ ...monoSm, padding: '10px 12px', lineHeight: 1.6 }}>
            Nenhuma anotação ainda.
          </p>
        )}
        {active.map((ann) => (
          <AnnotationItem key={ann.id} ann={ann} onToggle={handleResolveToggle} onDelete={handleDelete} />
        ))}
        {resolved.length > 0 && (
          <>
            <p style={{ ...monoSm, padding: '8px 10px 4px', textTransform: 'uppercase' }}>Resolvidas</p>
            {resolved.map((ann) => (
              <AnnotationItem key={ann.id} ann={ann} onToggle={handleResolveToggle} onDelete={handleDelete} />
            ))}
          </>
        )}
      </div>
    </div>
  )
}

function AnnotationItem({
  ann,
  onToggle,
  onDelete,
}: {
  ann: import('../types').Annotation
  onToggle: (ann: import('../types').Annotation) => void
  onDelete: (id: string) => void
}) {
  return (
    <div style={{
      padding: '7px 10px',
      borderBottom: '1px solid var(--rule)',
      opacity: ann.resolved ? 0.5 : 1,
    }}>
      {ann.quote && (
        <p style={{
          fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '10px',
          color: 'var(--accent)', margin: '0 0 3px',
          borderLeft: '2px solid var(--accent)', paddingLeft: '5px',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {ann.quote}
        </p>
      )}
      <p style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '12px', color: 'var(--ink-light)', margin: 0, lineHeight: 1.5 }}>
        {ann.text}
      </p>
      <div style={{ display: 'flex', gap: '6px', marginTop: '5px', alignItems: 'center' }}>
        <button
          onClick={() => onToggle(ann)}
          style={{ fontFamily: 'var(--font-mono)', fontSize: '8px', color: ann.resolved ? 'var(--ink-ghost)' : 'var(--accent-green)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, letterSpacing: '0.08em', textTransform: 'uppercase' }}
        >
          {ann.resolved ? 'Reabrir' : 'Resolver'}
        </button>
        <button
          onClick={() => onDelete(ann.id)}
          style={{ fontFamily: 'var(--font-mono)', fontSize: '8px', color: 'var(--ink-ghost)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
        >×</button>
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  Conversão Markdown ↔ TipTap HTML
//  TipTap trabalha com HTML internamente mas persiste
//  Markdown no disco (via os .md do vault).
//  Usamos o próprio StarterKit para parsear/serializar.
// ----------------------------------------------------------

/**
 * Converte Markdown simples em HTML para carregar no TipTap.
 * Cobre os elementos do StarterKit: h1-h6, bold, italic,
 * blockquote, hr, code, codeBlock, listas.
 */
function markdownToHtml(md: string): string {
  if (!md.trim()) return ''

  const lines = md.split('\n')
  const result: string[] = []
  let inCodeBlock = false
  let codeLines: string[] = []
  let codeLang = ''

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // Bloco de código
    if (line.startsWith('```')) {
      if (!inCodeBlock) {
        inCodeBlock = true
        codeLang = line.slice(3).trim()
        codeLines = []
      } else {
        inCodeBlock = false
        const escaped = codeLines.join('\n')
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
        result.push(`<pre><code class="language-${codeLang}">${escaped}</code></pre>`)
        codeLines = []
        codeLang = ''
      }
      continue
    }

    if (inCodeBlock) {
      codeLines.push(line)
      continue
    }

    // Separador horizontal
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) {
      result.push('<hr>')
      continue
    }

    // Títulos
    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/)
    if (headingMatch) {
      const level = headingMatch[1].length
      const content = inlineMarkdown(headingMatch[2])
      result.push(`<h${level}>${content}</h${level}>`)
      continue
    }

    // Blockquote
    if (line.startsWith('> ')) {
      const content = inlineMarkdown(line.slice(2))
      result.push(`<blockquote><p>${content}</p></blockquote>`)
      continue
    }

    // Parágrafo (linha vazia = sem parágrafo)
    if (line.trim() === '') {
      continue
    }

    result.push(`<p>${inlineMarkdown(line)}</p>`)
  }

  return result.join('')
}

/** Processa formatação inline: bold, italic, code */
function inlineMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    // Bold + italic
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/___(.+?)___/g, '<strong><em>$1</em></strong>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.+?)__/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/_(.+?)_/g, '<em>$1</em>')
    // Code inline
    .replace(/`(.+?)`/g, '<code>$1</code>')
}

/**
 * Converte HTML do TipTap de volta para Markdown para salvar em disco.
 * Mantém os .md portáteis e legíveis fora do AETHER.
 */
function htmlToMarkdown(html: string): string {
  if (!html) return ''

  return html
    // Blocos de código
    .replace(/<pre><code[^>]*>([\s\S]*?)<\/code><\/pre>/g, (_, code) =>
      '```\n' + code
        .replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        + '\n```'
    )
    // Títulos
    .replace(/<h([1-6])>(.*?)<\/h[1-6]>/g, (_, level, content) =>
      '#'.repeat(Number(level)) + ' ' + stripTags(content)
    )
    // Blockquote
    .replace(/<blockquote><p>(.*?)<\/p><\/blockquote>/gs, (_, content) =>
      '> ' + stripTags(content)
    )
    // HR
    .replace(/<hr\s*\/?>/g, '---')
    // Bold + italic
    .replace(/<strong><em>(.*?)<\/em><\/strong>/g, '***$1***')
    .replace(/<em><strong>(.*?)<\/strong><\/em>/g, '***$1***')
    // Bold
    .replace(/<strong>(.*?)<\/strong>/g, '**$1**')
    // Italic
    .replace(/<em>(.*?)<\/em>/g, '_$1_')
    // Code inline
    .replace(/<code>(.*?)<\/code>/g, '`$1`')
    // Parágrafos — cada <p> vira uma linha
    .replace(/<p>(.*?)<\/p>/gs, (_, content) => stripTags(content) + '\n')
    // Entidades
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&nbsp;/g, ' ')
    // Limpar quebras duplas excessivas
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, '')
}

function countWords(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

// ----------------------------------------------------------
//  Estados do auto-save
// ----------------------------------------------------------

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

// ----------------------------------------------------------
//  Editor
// ----------------------------------------------------------

interface EditorProps {
  chapter: ActiveChapter
  focusMode?: boolean
  onEnterFocus?: () => void
  onExitFocus?: () => void
  onError: (msg: string) => void
}

export function Editor({ chapter, focusMode = false, onEnterFocus, onExitFocus, onError }: EditorProps) {
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [wordCount, setWordCount] = useState(0)
  const [charCount, setCharCount] = useState(0)
  const [loaded, setLoaded] = useState(false)
  const [chapterStatus, setChapterStatus] = useState<ChapterStatus>(chapter.status)
  const [typewriterMode, setTypewriterMode] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const [replaceInput, setReplaceInput] = useState('')
  const [matchCount, setMatchCount] = useState(0)
  const [currentMatch, setCurrentMatch] = useState(-1)
  const [splitMode, setSplitMode] = useState(false)
  const [splitTab, setSplitTab] = useState<'notas' | 'vinculos' | 'snapshots' | 'anotacoes'>('notas')
  const [wordGoal, setWordGoal] = useState<number | null>(chapter.wordGoal ?? null)
  const [showGoalInput, setShowGoalInput] = useState(false)
  const [goalInputValue, setGoalInputValue] = useState('')
  // Sessão de escrita (5.2)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessionStartWords, setSessionStartWords] = useState(0)
  const [sessionElapsed, setSessionElapsed] = useState(0) // segundos
  const sessionTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const sessionRef = useRef<{ id: string | null; startWords: number }>({ id: null, startWords: 0 })
  const wordCountRef = useRef(0)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const typewriterModeRef = useRef(false)
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const currentChapter = useRef(chapter)
  currentChapter.current = chapter
  typewriterModeRef.current = typewriterMode

  // ----------------------------------------------------------
  //  Modo typewriter: centraliza a linha do cursor verticalmente
  // ----------------------------------------------------------

  const scrollToCursor = useCallback(() => {
    if (!scrollRef.current) return
    const sel = window.getSelection()
    if (!sel || sel.rangeCount === 0) return
    const range = sel.getRangeAt(0)
    const rect = range.getBoundingClientRect()
    const scrollEl = scrollRef.current
    const scrollRect = scrollEl.getBoundingClientRect()
    // Posição do cursor relativa ao container de scroll
    const cursorTop = rect.top - scrollRect.top + scrollEl.scrollTop
    const target = cursorTop - scrollEl.clientHeight / 2
    scrollEl.scrollTo({ top: target, behavior: 'smooth' })
  }, [])

  // ----------------------------------------------------------
  //  Auto-save: debounce 500ms
  // ----------------------------------------------------------

  const scheduleSave = useCallback((html: string) => {
    if (saveTimer.current) clearTimeout(saveTimer.current)

    setSaveStatus('saving')

    saveTimer.current = setTimeout(async () => {
      const markdown = htmlToMarkdown(html)
      const { projectId, bookId, chapterId } = currentChapter.current

      const result = await cmd.saveChapter(projectId, bookId, chapterId, markdown)

      if (!result.ok) {
        setSaveStatus('error')
        onError(`Erro ao salvar: ${result.error.message}`)
        return
      }

      setSaveStatus('saved')
    }, 500)
  }, [onError])

  // ----------------------------------------------------------
  //  TipTap
  // ----------------------------------------------------------

  const editor = useEditor({
    extensions: [
      StarterKit,
      Typography,
      Placeholder.configure({
        placeholder: 'Comece a escrever o seu capítulo...',
      }),
      SearchReplace,
    ],
    content: '',
    editorProps: {
      attributes: {
        class: 'ProseMirror',
        spellcheck: 'true',
        'data-chapter': chapter.chapterId,
      },
    },
    onUpdate({ editor }) {
      const html = editor.getHTML()
      const text = editor.getText()
      const wc = countWords(text)
      setWordCount(wc)
      wordCountRef.current = wc
      setCharCount(text.replace(/\s/g, '').length)
      scheduleSave(html)
      // typewriterMode lido via ref para evitar closure stale
      if (typewriterModeRef.current) scrollToCursor()
    },
  })

  // ----------------------------------------------------------
  //  Busca — helpers para sincronizar estado do plugin
  // ----------------------------------------------------------

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const editorCmds = editor?.commands as unknown as Record<string, (...a: any[]) => boolean> | undefined

  function syncSearchState() {
    if (!editor) return
    const s = searchKey.getState(editor.state)
    if (!s) return
    setMatchCount(s.matches.length)
    setCurrentMatch(s.current)
  }

  function handleSearchInput(value: string) {
    setSearchInput(value)
    if (!editorCmds) return
    editorCmds.setSearchTerm(value)
    syncSearchState()
  }

  function handleNextMatch() {
    if (!editor || !editorCmds) return
    const s = searchKey.getState(editor.state)
    if (!s || s.matches.length === 0) return
    editorCmds.goToMatch((s.current + 1) % s.matches.length)
    syncSearchState()
  }

  function handlePrevMatch() {
    if (!editor || !editorCmds) return
    const s = searchKey.getState(editor.state)
    if (!s || s.matches.length === 0) return
    editorCmds.goToMatch((s.current - 1 + s.matches.length) % s.matches.length)
    syncSearchState()
  }

  function handleReplace() {
    if (!editorCmds) return
    editorCmds.replaceCurrentMatch(replaceInput)
    editorCmds.setSearchTerm(searchInput)
    syncSearchState()
  }

  function handleReplaceAll() {
    if (!editorCmds) return
    editorCmds.replaceAllMatches(replaceInput)
    editorCmds.setSearchTerm(searchInput)
    syncSearchState()
  }

  function openSearch() {
    setShowSearch(true)
    setTimeout(() => searchInputRef.current?.focus(), 30)
  }

  function closeSearch() {
    setShowSearch(false)
    setSearchInput('')
    setReplaceInput('')
    setMatchCount(0)
    setCurrentMatch(-1)
    if (editorCmds) {
      editorCmds.clearSearch()
      editor?.commands.focus()
    }
  }

  // Ctrl+F abre o painel de busca
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault()
        if (showSearch) {
          searchInputRef.current?.focus()
        } else {
          openSearch()
        }
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showSearch, editor])

  // Escape fecha o painel de busca (antes de fechar modo foco)
  useEffect(() => {
    if (!showSearch) return
    function handleEsc(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        closeSearch()
      }
    }
    window.addEventListener('keydown', handleEsc, true)
    return () => window.removeEventListener('keydown', handleEsc, true)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showSearch, editor])

  // ----------------------------------------------------------
  //  Carregar conteúdo ao mudar de capítulo
  // ----------------------------------------------------------

  // Sincronizar status e meta de palavras ao trocar de capítulo
  useEffect(() => {
    setChapterStatus(chapter.status)
    setWordGoal(chapter.wordGoal ?? null)
    setShowGoalInput(false)
  }, [chapter.chapterId])

  // Sessão de escrita: iniciar ao carregar capítulo, encerrar ao trocar (5.2)
  useEffect(() => {
    // Encerrar sessão anterior se houver
    const prev = sessionRef.current
    if (prev.id) {
      cmd.endSession(prev.id, wordCountRef.current)
    }

    setSessionId(null)
    setSessionElapsed(0)
    setSessionStartWords(0)
    if (sessionTimer.current) clearInterval(sessionTimer.current)

    // Iniciar nova sessão
    const { projectId, bookId, chapterId } = chapter
    cmd.startSession(projectId, bookId, chapterId, wordCount).then((result) => {
      if (result.ok) {
        const sid = result.data.id
        const sw = wordCount
        setSessionId(sid)
        setSessionStartWords(sw)
        sessionRef.current = { id: sid, startWords: sw }

        sessionTimer.current = setInterval(() => {
          setSessionElapsed((prev) => prev + 1)
        }, 1000)
      }
    })

    return () => {
      if (sessionTimer.current) {
        clearInterval(sessionTimer.current)
        sessionTimer.current = null
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapter.chapterId, chapter.bookId, chapter.projectId])

  async function handleCycleStatus() {
    const cycle: ChapterStatus[] = ['draft', 'revision', 'final']
    const next = cycle[(cycle.indexOf(chapterStatus) + 1) % cycle.length]
    const result = await cmd.updateChapterStatus(
      chapter.projectId, chapter.bookId, chapter.chapterId, next
    )
    if (result.ok) setChapterStatus(next)
  }

  useEffect(() => {
    if (!editor) return

    setLoaded(false)
    setSaveStatus('idle')
    setWordCount(0)

    // Cancelar save pendente do capítulo anterior
    if (saveTimer.current) {
      clearTimeout(saveTimer.current)
      saveTimer.current = null
    }

    async function load() {
      const result = await cmd.readChapter(
        chapter.projectId,
        chapter.bookId,
        chapter.chapterId,
      )

      if (!result.ok) {
        onError(`Erro ao carregar capítulo: ${result.error.message}`)
        return
      }

      const html = markdownToHtml(result.data)

      // Desabilita onUpdate enquanto carrega para não disparar save
      editor!.setOptions({ editable: false })
      editor!.commands.setContent(html, { emitUpdate: false })
      editor!.setOptions({ editable: true })

      setWordCount(countWords(result.data))
      setCharCount(result.data.replace(/\s/g, '').length)
      setLoaded(true)

      // Foco no editor após carregar
      setTimeout(() => editor!.commands.focus('end'), 50)
    }

    load()

    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current)
    }
  }, [chapter.chapterId, chapter.bookId, chapter.projectId, editor, onError])

  // ----------------------------------------------------------
  //  Limpar ao desmontar
  // ----------------------------------------------------------

  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current)
      if (sessionTimer.current) clearInterval(sessionTimer.current)
      const { id } = sessionRef.current
      if (id) cmd.endSession(id, wordCountRef.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ----------------------------------------------------------
  //  Render
  // ----------------------------------------------------------

  const statusLabel: Record<SaveStatus, string> = {
    idle:   '',
    saving: 'Salvando...',
    saved:  'Salvo',
    error:  'Erro ao salvar',
  }

  const statusClass: Record<SaveStatus, string> = {
    idle:   'editor-statusbar-label',
    saving: 'editor-statusbar-label saving',
    saved:  'editor-statusbar-label saved',
    error:  'editor-statusbar-label',
  }

  return (
    <div className="editor-wrap">
      {/* Topbar — oculta em modo foco */}
      {!focusMode && (
        <div className="editor-topbar">
          <span className="editor-chapter-title">{chapter.title}</span>
          <TypographyPanel />
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setTypewriterMode((v) => !v)}
            title="Modo typewriter — cursor centralizado verticalmente"
            aria-label="Alternar modo typewriter"
            aria-pressed={typewriterMode}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              color: typewriterMode ? 'var(--accent)' : 'var(--ink-ghost)',
              letterSpacing: '0.06em',
              padding: '4px 8px',
            }}
          >
            Type
          </button>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setSplitMode((v) => !v)}
            title="Modo split — editor + notas lado a lado"
            aria-label="Alternar modo split"
            aria-pressed={splitMode}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              color: splitMode ? 'var(--accent)' : 'var(--ink-ghost)',
              letterSpacing: '0.06em',
              padding: '4px 8px',
            }}
          >
            Split
          </button>
          {onEnterFocus && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={onEnterFocus}
              title="Modo foco (Esc para sair)"
              aria-label="Entrar em modo foco"
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                color: 'var(--ink-ghost)',
                letterSpacing: '0.06em',
                padding: '4px 8px',
              }}
            >
              Foco
            </button>
          )}
        </div>
      )}

      {/* Painel de busca e substituição */}
      {showSearch && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '6px 16px',
            borderBottom: '1px solid var(--rule)',
            background: 'var(--paper-dark)',
            flexShrink: 0,
            flexWrap: 'wrap',
          }}
        >
          {/* Grupo busca */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flex: '1 1 200px' }}>
            <input
              ref={searchInputRef}
              value={searchInput}
              onChange={(e) => handleSearchInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.shiftKey ? handlePrevMatch() : handleNextMatch()
                }
              }}
              placeholder="Localizar..."
              style={{
                flex: 1,
                fontFamily: 'var(--font-display)',
                fontStyle: 'italic',
                fontSize: '13px',
                background: 'var(--paper)',
                border: '1px solid var(--rule)',
                borderRadius: 'var(--radius)',
                color: 'var(--ink)',
                padding: '3px 8px',
                outline: 'none',
                minWidth: 0,
              }}
            />
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                color: matchCount > 0 ? 'var(--ink-faint)' : 'var(--ink-ghost)',
                whiteSpace: 'nowrap',
                minWidth: '40px',
              }}
            >
              {searchInput
                ? matchCount === 0
                  ? 'sem resultados'
                  : `${currentMatch + 1}/${matchCount}`
                : ''}
            </span>
            <button
              className="btn btn-ghost btn-icon btn-sm"
              onClick={handlePrevMatch}
              title="Resultado anterior (Shift+Enter)"
              disabled={matchCount === 0}
              style={{ color: 'var(--ink-ghost)', fontSize: '12px' }}
            >
              ▲
            </button>
            <button
              className="btn btn-ghost btn-icon btn-sm"
              onClick={handleNextMatch}
              title="Próximo resultado (Enter)"
              disabled={matchCount === 0}
              style={{ color: 'var(--ink-ghost)', fontSize: '12px' }}
            >
              ▼
            </button>
          </div>

          {/* Divisor */}
          <div style={{ width: '1px', height: '18px', background: 'var(--rule)', flexShrink: 0 }} />

          {/* Grupo substituição */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flex: '1 1 200px' }}>
            <input
              value={replaceInput}
              onChange={(e) => setReplaceInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleReplace()
              }}
              placeholder="Substituir por..."
              style={{
                flex: 1,
                fontFamily: 'var(--font-display)',
                fontStyle: 'italic',
                fontSize: '13px',
                background: 'var(--paper)',
                border: '1px solid var(--rule)',
                borderRadius: 'var(--radius)',
                color: 'var(--ink)',
                padding: '3px 8px',
                outline: 'none',
                minWidth: 0,
              }}
            />
            <button
              className="btn btn-ghost btn-sm"
              onClick={handleReplace}
              disabled={matchCount === 0}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                letterSpacing: '0.04em',
                color: 'var(--ink-faint)',
                whiteSpace: 'nowrap',
              }}
            >
              Substituir
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={handleReplaceAll}
              disabled={matchCount === 0}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                letterSpacing: '0.04em',
                color: 'var(--ink-faint)',
                whiteSpace: 'nowrap',
              }}
            >
              Tudo
            </button>
          </div>

          {/* Fechar */}
          <button
            className="btn btn-ghost btn-icon btn-sm"
            onClick={closeSearch}
            title="Fechar (Esc)"
            style={{ color: 'var(--ink-ghost)', flexShrink: 0 }}
          >
            ×
          </button>
        </div>
      )}

      {/* Área de conteúdo: editor + scratchpad opcional (split mode) */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
        {/* Área de scroll do editor */}
        <div
          ref={scrollRef}
          className="editor-scroll"
          style={{
            flex: 1,
            ...(focusMode ? { paddingTop: '80px', paddingBottom: '120px' } : {}),
          }}
        >
          <div className="editor-column">
            {/* Botão de saída discreto no modo foco */}
            {focusMode && onExitFocus && (
              <div style={{ textAlign: 'right', marginBottom: '24px' }}>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={onExitFocus}
                  title="Sair do modo foco (Esc)"
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '10px',
                    color: 'var(--ink-ghost)',
                    letterSpacing: '0.1em',
                    opacity: 0.5,
                    padding: '3px 8px',
                  }}
                >
                  esc
                </button>
              </div>
            )}

            {!loaded && (
              <p
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '10px',
                  color: 'var(--ink-ghost)',
                  letterSpacing: '0.08em',
                  animation: 'blink 1.2s ease infinite',
                }}
              >
                · · ·
              </p>
            )}
            <EditorContent editor={editor} />
          </div>
        </div>

        {/* Painel lateral — visível no modo split (3.4/3.5/4.6/5.5/5.6) */}
        {splitMode && !focusMode && (
          <SplitPanel
            tab={splitTab}
            onTabChange={setSplitTab}
            chapter={chapter}
            wordCount={wordCount}
            onError={onError}
            onSuccess={() => {}}
          />
        )}
      </div>

      {/* Statusbar — oculta em modo foco */}
      {!focusMode && (
        <div className="editor-statusbar">
          {/* Status do capítulo — clica para ciclar */}
          <button
            onClick={handleCycleStatus}
            title="Clique para alterar o status do capítulo"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              letterSpacing: '0.08em',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: '0 8px 0 0',
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              color: chapterStatus === 'final'    ? 'var(--accent-green)'
                   : chapterStatus === 'revision' ? 'var(--accent)'
                   : 'var(--ink-ghost)',
            }}
          >
            <span style={{
              width: '6px', height: '6px', borderRadius: '50%', flexShrink: 0,
              background: chapterStatus === 'final'    ? 'var(--accent-green)'
                        : chapterStatus === 'revision' ? 'var(--accent)'
                        : 'var(--ink-ghost)',
            }} />
            {chapterStatus === 'draft'    ? 'Rascunho'
           : chapterStatus === 'revision' ? 'Revisão'
           : 'Final'}
          </button>

          {saveStatus !== 'idle' && (
            <span className={statusClass[saveStatus]}>
              {statusLabel[saveStatus]}
            </span>
          )}
          <span style={{ flex: 1 }} />

          {/* Timer de sessão (5.2) */}
          {sessionId && (
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '10px',
              color: 'var(--ink-ghost)',
              letterSpacing: '0.06em',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}>
              <span style={{ opacity: 0.5 }}>◷</span>
              {formatElapsed(sessionElapsed)}
              {wordCount - sessionStartWords > 0 && (
                <span style={{ color: 'var(--accent)', marginLeft: '4px' }}>
                  +{wordCount - sessionStartWords}
                </span>
              )}
            </span>
          )}

          {/* Meta de palavras (5.1) */}
          {showGoalInput ? (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                const n = parseInt(goalInputValue, 10)
                const goal = isNaN(n) || n <= 0 ? null : n
                setWordGoal(goal)
                setShowGoalInput(false)
                cmd.setChapterWordGoal(chapter.projectId, chapter.bookId, chapter.chapterId, goal)
              }}
              style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
            >
              <input
                autoFocus
                value={goalInputValue}
                onChange={(e) => setGoalInputValue(e.target.value)}
                onBlur={() => setShowGoalInput(false)}
                onKeyDown={(e) => { if (e.key === 'Escape') setShowGoalInput(false) }}
                placeholder="meta (palavras)"
                style={{
                  width: '110px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '10px',
                  background: 'var(--paper)',
                  border: '1px solid var(--rule)',
                  borderRadius: 'var(--radius)',
                  color: 'var(--ink)',
                  padding: '2px 6px',
                  outline: 'none',
                }}
              />
            </form>
          ) : (
            <button
              onClick={() => {
                setGoalInputValue(wordGoal ? String(wordGoal) : '')
                setShowGoalInput(true)
              }}
              title={wordGoal ? `Meta: ${wordGoal} palavras — clique para alterar` : 'Definir meta de palavras'}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: '0 4px',
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                color: 'var(--ink-ghost)',
              }}
            >
              {wordGoal ? (
                <>
                  {/* Progresso visual */}
                  <span style={{
                    display: 'inline-block',
                    width: '40px',
                    height: '4px',
                    background: 'var(--rule)',
                    borderRadius: '2px',
                    overflow: 'hidden',
                    verticalAlign: 'middle',
                  }}>
                    <span style={{
                      display: 'block',
                      height: '100%',
                      width: `${Math.min(100, (wordCount / wordGoal) * 100)}%`,
                      background: wordCount >= wordGoal ? 'var(--accent-green)' : 'var(--accent)',
                      transition: 'width 0.3s ease',
                    }} />
                  </span>
                  <span style={{ color: wordCount >= wordGoal ? 'var(--accent-green)' : 'var(--ink-ghost)' }}>
                    {wordCount}/{wordGoal}
                  </span>
                </>
              ) : (
                <span style={{ opacity: 0.4, letterSpacing: '0.04em', fontSize: '10px' }}>meta</span>
              )}
            </button>
          )}

          {wordCount > 0 && (
            <span className="editor-statusbar-label">
              {wordCount} {wordCount === 1 ? 'palavra' : 'palavras'}
              {' · '}
              {charCount} {charCount === 1 ? 'caractere' : 'caracteres'}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
