/* ============================================================
   AETHER — Binder
   Painel lateral esquerdo: árvore Livros > Capítulos.
   CRUD de livros e capítulos. Largura: var(--sidebar-w).
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import * as cmd from '../lib/tauri'
import { ThemeToggle } from './ThemeToggle'
import type { Book, BookMeta, ChapterMeta, ProjectType } from '../types'

interface BinderProps {
  projectId: string
  projectName: string
  projectType: ProjectType
  defaultBookId?: string
  activeChapter: ActiveChapter | null
  onSelectChapter: (chapter: ActiveChapter) => void
  onBack: () => void
  onError: (msg: string) => void
  onSuccess: (msg: string) => void
}

export interface ActiveChapter {
  projectId: string
  bookId: string
  chapterId: string
  title: string
  status: import('../types').ChapterStatus
  characterIds: string[]
  noteIds: string[]
  /** Meta de palavras para este capítulo (5.1) */
  wordGoal: number | null
}

// ----------------------------------------------------------
//  Inline rename — input que confirma com Enter ou blur
// ----------------------------------------------------------

interface InlineRenameProps {
  initialValue: string
  onConfirm: (value: string) => void
  onCancel: () => void
}

function InlineRename({ initialValue, onConfirm, onCancel }: InlineRenameProps) {
  const [value, setValue] = useState(initialValue)
  const ref = useRef<HTMLInputElement>(null)

  useEffect(() => {
    ref.current?.select()
  }, [])

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') {
      const trimmed = value.trim()
      if (trimmed.length > 0) onConfirm(trimmed)
      else onCancel()
    }
    if (e.key === 'Escape') onCancel()
  }

  return (
    <input
      ref={ref}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => {
        const trimmed = value.trim()
        if (trimmed.length > 0 && trimmed !== initialValue) onConfirm(trimmed)
        else onCancel()
      }}
      onKeyDown={handleKeyDown}
      style={{
        fontFamily: 'var(--font-display)',
        fontStyle: 'italic',
        fontSize: '15px',
        background: 'var(--paper)',
        border: '1px solid var(--accent)',
        borderRadius: 'var(--radius)',
        color: 'var(--ink)',
        padding: '1px 6px',
        width: '100%',
        outline: 'none',
      }}
      maxLength={120}
    />
  )
}

// ----------------------------------------------------------
//  ChapterRow
// ----------------------------------------------------------

interface ChapterRowProps {
  chapter: ChapterMeta
  isActive: boolean
  onSelect: () => void
  onRename: (title: string) => void
  onDelete: () => void
  onSynopsisChange: (synopsis: string | null) => void
}

function ChapterRow({ chapter, isActive, onSelect, onRename, onDelete, onSynopsisChange }: ChapterRowProps) {
  const [renaming, setRenaming] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [synopsis, setSynopsis] = useState(chapter.synopsis ?? '')
  const synopsisTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sincronizar quando o capítulo muda externamente
  useEffect(() => {
    setSynopsis(chapter.synopsis ?? '')
  }, [chapter.id])

  function handleSynopsisChange(value: string) {
    setSynopsis(value)
    if (synopsisTimer.current) clearTimeout(synopsisTimer.current)
    synopsisTimer.current = setTimeout(() => {
      onSynopsisChange(value.trim() || null)
    }, 600)
  }

  const statusColor: Record<string, string> = {
    draft:    'var(--ink-ghost)',
    revision: 'var(--accent)',
    final:    'var(--accent-green)',
  }

  return (
    <div>
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '7px 8px 7px 20px',
        borderRadius: 'var(--radius)',
        background: isActive ? 'var(--paper-darker)' : hovered ? 'var(--paper-dark)' : 'transparent',
        cursor: 'pointer',
        transition: 'background var(--transition)',
      }}
      onClick={onSelect}
    >
      {/* Indicador de status */}
      <span
        style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: statusColor[chapter.status] ?? 'var(--ink-ghost)',
          flexShrink: 0,
        }}
        title={chapter.status}
        aria-label={`Status: ${chapter.status}`}
      />

      {renaming ? (
        <InlineRename
          initialValue={chapter.title}
          onConfirm={(t) => { onRename(t); setRenaming(false) }}
          onCancel={() => setRenaming(false)}
        />
      ) : (
        <>
          <span
            style={{
              flex: 1,
              fontFamily: 'var(--font-display)',
              fontStyle: 'italic',
              fontSize: '15px',
              color: isActive ? 'var(--ink)' : 'var(--ink-light)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              minWidth: 0,
            }}
            onDoubleClick={(e) => { e.stopPropagation(); setRenaming(true) }}
          >
            {chapter.title}
          </span>

          {hovered && (
            <button
              className="btn btn-ghost btn-icon btn-sm"
              onClick={(e) => { e.stopPropagation(); onDelete() }}
              title="Excluir capítulo"
              aria-label="Excluir capítulo"
              style={{ color: 'var(--ink-ghost)', flexShrink: 0 }}
            >
              ×
            </button>
          )}
        </>
      )}
    </div>

    {/* Sinopse — visível apenas no capítulo ativo */}
    {isActive && (
      <textarea
        value={synopsis}
        onChange={(e) => handleSynopsisChange(e.target.value)}
        onClick={(e) => e.stopPropagation()}
        placeholder="Sinopse do capítulo..."
        maxLength={600}
        rows={3}
        style={{
          width: '100%',
          marginTop: '2px',
          marginBottom: '4px',
          padding: '6px 10px 6px 20px',
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          fontSize: '12px',
          lineHeight: 1.5,
          color: 'var(--ink-faint)',
          background: 'transparent',
          border: 'none',
          borderLeft: '2px solid var(--rule)',
          borderRadius: 0,
          resize: 'none',
          outline: 'none',
          boxSizing: 'border-box',
          caretColor: 'var(--accent)',
        }}
      />
    )}
    </div>
  )
}

// ----------------------------------------------------------
//  BookSection
// ----------------------------------------------------------

interface BookSectionProps {
  book: Book
  activeChapter: ActiveChapter | null
  onSelectChapter: (ch: ActiveChapter) => void
  onRenameBook: (name: string) => void
  onDeleteBook: () => void
  onCreateChapter: () => void
  onRenameChapter: (chapterId: string, title: string) => void
  onDeleteChapter: (chapterId: string) => void
  onSynopsisChange: (chapterId: string, synopsis: string | null) => void
}

function BookSection({
  book,
  activeChapter,
  onSelectChapter,
  onRenameBook,
  onDeleteBook,
  onCreateChapter,
  onRenameChapter,
  onDeleteChapter,
  onSynopsisChange,
}: BookSectionProps) {
  const [expanded, setExpanded] = useState(true)
  const [renaming, setRenaming] = useState(false)
  const [hovered, setHovered] = useState(false)

  return (
    <div style={{ marginBottom: '6px' }}>
      {/* Header do livro */}
      <div
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '7px 8px',
          cursor: 'pointer',
          borderRadius: 'var(--radius)',
          background: hovered ? 'var(--paper-darker)' : 'transparent',
          transition: 'background var(--transition)',
        }}
        onClick={() => setExpanded((v) => !v)}
      >
        {/* Seta */}
        <span
          style={{
            fontSize: '11px',
            color: 'var(--ink-ghost)',
            transition: 'transform 140ms',
            transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
            flexShrink: 0,
          }}
          aria-hidden="true"
        >
          ▶
        </span>

        {renaming ? (
          <InlineRename
            initialValue={book.name}
            onConfirm={(n) => { onRenameBook(n); setRenaming(false) }}
            onCancel={() => setRenaming(false)}
          />
        ) : (
          <>
            <span
              style={{
                flex: 1,
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
                color: 'var(--ink-faint)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                minWidth: 0,
              }}
              onDoubleClick={(e) => { e.stopPropagation(); setRenaming(true) }}
            >
              {book.name}
            </span>

            {hovered && (
              <div
                style={{ display: 'flex', gap: '2px', flexShrink: 0 }}
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  className="btn btn-ghost btn-icon btn-sm"
                  onClick={onDeleteBook}
                  title="Excluir livro"
                  aria-label="Excluir livro"
                  style={{ color: 'var(--ink-ghost)' }}
                >
                  ×
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Capítulos */}
      {expanded && (
        <div style={{ marginLeft: '4px', animation: 'fadeIn 0.15s ease both' }}>
          {book.chapters.length === 0 ? (
            <p
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
                color: 'var(--ink-ghost)',
                padding: '6px 8px 6px 20px',
                margin: 0,
                letterSpacing: '0.04em',
              }}
            >
              Nenhum capítulo ainda.
            </p>
          ) : (
            book.chapters.map((ch) => (
              <ChapterRow
                key={ch.id}
                chapter={ch}
                isActive={activeChapter?.chapterId === ch.id}
                onSelect={() =>
                  onSelectChapter({
                    projectId: book.project_id,
                    bookId: book.id,
                    chapterId: ch.id,
                    title: ch.title,
                    status: ch.status,
                    characterIds: ch.character_ids ?? [],
                    noteIds: ch.note_ids ?? [],
                    wordGoal: ch.word_goal ?? null,
                  })
                }
                onRename={(title) => onRenameChapter(ch.id, title)}
                onDelete={() => onDeleteChapter(ch.id)}
                onSynopsisChange={(synopsis) => onSynopsisChange(ch.id, synopsis)}
              />
            ))
          )}

          {/* Botão + Novo capítulo — sempre visível */}
          <button
            className="btn btn-ghost btn-sm"
            onClick={(e) => { e.stopPropagation(); onCreateChapter() }}
            style={{
              width: '100%',
              marginTop: '2px',
              color: 'var(--ink-ghost)',
              fontSize: '13px',
              letterSpacing: '0.04em',
              textAlign: 'left',
              paddingLeft: '20px',
            }}
          >
            + Novo capítulo
          </button>
        </div>
      )}
    </div>
  )
}

// ----------------------------------------------------------
//  Binder
// ----------------------------------------------------------

export function Binder({
  projectId,
  projectName,
  projectType,
  defaultBookId,
  activeChapter,
  onSelectChapter,
  onBack,
  onError,
  onSuccess,
}: BinderProps) {
  const [books, setBooks] = useState<Book[]>([])
  const [loading, setLoading] = useState(true)
  const [creatingBook, setCreatingBook] = useState(false)
  const [newBookName, setNewBookName] = useState('')
  const [newBookSeries, setNewBookSeries] = useState('')

  useEffect(() => {
    loadBooks()
  }, [projectId])

  async function loadBooks() {
    setLoading(true)

    if (projectType === 'single' && defaultBookId) {
      // Single mode: load only the default book directly
      const bookResult = await cmd.openBook(projectId, defaultBookId)
      setLoading(false)
      if (!bookResult.ok) {
        onError(`Erro ao carregar livro: ${bookResult.error.message}`)
        return
      }
      setBooks([bookResult.data])
    } else {
      const result = await cmd.listBooks(projectId)
      setLoading(false)
      if (!result.ok) {
        onError(`Erro ao carregar livros: ${result.error.message}`)
        return
      }
      const fullBooks: Book[] = []
      for (const meta of result.data) {
        const bookResult = await cmd.openBook(projectId, meta.id)
        if (bookResult.ok) fullBooks.push(bookResult.data)
      }
      setBooks(fullBooks)
    }
  }

  async function handleCreateBook(seriesName?: string) {
    const trimmed = newBookName.trim()
    if (!trimmed) return

    setCreatingBook(false)
    setNewBookName('')
    setNewBookSeries('')

    const result = await cmd.createBook(projectId, trimmed, seriesName)
    if (!result.ok) {
      onError(`Erro ao criar livro: ${result.error.message}`)
      return
    }

    const bookResult = await cmd.openBook(projectId, result.data.id)
    if (!bookResult.ok) {
      onError(`Livro criado, mas erro ao carregar: ${bookResult.error.message}`)
      return
    }

    onSuccess(`Livro "${trimmed}" criado.`)
    setBooks((prev) => [...prev, bookResult.data])
  }

  async function handleRenameBook(bookId: string, name: string) {
    const result = await cmd.updateBook(projectId, bookId, name)
    if (!result.ok) { onError(result.error.message); return }
    setBooks((prev) => prev.map((b) => b.id === bookId ? { ...b, name: result.data.name } : b))
  }

  async function handleDeleteBook(book: BookMeta) {
    const result = await cmd.deleteBook(projectId, book.id)
    if (!result.ok) { onError(result.error.message); return }
    onSuccess(`Livro "${book.name}" excluído.`)
    setBooks((prev) => prev.filter((b) => b.id !== book.id))
  }

  async function handleCreateChapter(bookId: string) {
    const book = books.find((b) => b.id === bookId)
    const title = `Capítulo ${(book?.chapters.length ?? 0) + 1}`
    const result = await cmd.createChapter(projectId, bookId, title)
    if (!result.ok) { onError(result.error.message); return }
    setBooks((prev) =>
      prev.map((b) =>
        b.id === bookId ? { ...b, chapters: [...b.chapters, result.data] } : b
      )
    )
  }

  async function handleRenameChapter(bookId: string, chapterId: string, title: string) {
    const result = await cmd.updateChapterTitle(projectId, bookId, chapterId, title)
    if (!result.ok) { onError(result.error.message); return }
    setBooks((prev) =>
      prev.map((b) =>
        b.id === bookId
          ? { ...b, chapters: b.chapters.map((c) => c.id === chapterId ? result.data : c) }
          : b
      )
    )
  }

  async function handleDeleteChapter(bookId: string, chapterId: string) {
    // Soft delete — move para lixeira, recuperável
    const result = await cmd.trashChapter(projectId, bookId, chapterId)
    if (!result.ok) { onError(result.error.message); return }
    setBooks((prev) =>
      prev.map((b) =>
        b.id === bookId
          ? { ...b, chapters: b.chapters.filter((c) => c.id !== chapterId) }
          : b
      )
    )
  }

  async function handleUpdateSynopsis(bookId: string, chapterId: string, synopsis: string | null) {
    const result = await cmd.updateChapterSynopsis(projectId, bookId, chapterId, synopsis)
    if (!result.ok) { onError(result.error.message); return }
    setBooks((prev) =>
      prev.map((b) =>
        b.id === bookId
          ? { ...b, chapters: b.chapters.map((c) => c.id === chapterId ? result.data : c) }
          : b
      )
    )
  }

  return (
    <aside
      style={{
        width: 'var(--sidebar-w)',
        flexShrink: 0,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--paper-dark)',
        borderRight: '1px solid var(--rule)',
        position: 'relative',
      }}
    >
      {/* Linha de margem */}
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          left: '48px',
          width: '1px',
          background: 'var(--margin-line)',
          pointerEvents: 'none',
          zIndex: 0,
        }}
      />

      {/* Topbar do binder */}
      <div
        style={{
          height: 'var(--topbar-h)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 12px 0 16px',
          borderBottom: '1px solid var(--rule)',
          gap: '8px',
          flexShrink: 0,
          position: 'relative',
          zIndex: 1,
        }}
      >
        <button
          className="btn btn-ghost btn-icon btn-sm"
          onClick={onBack}
          title="Voltar para projetos"
          aria-label="Voltar"
          style={{ color: 'var(--ink-faint)', flexShrink: 0 }}
        >
          ←
        </button>
        <span
          style={{
            flex: 1,
            fontFamily: 'var(--font-display)',
            fontStyle: 'italic',
            fontSize: '15px',
            color: 'var(--ink-light)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            minWidth: 0,
          }}
        >
          {projectName}
        </span>
        <ThemeToggle />
      </div>

      {/* Conteúdo do binder */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '12px 8px',
          position: 'relative',
          zIndex: 1,
        }}
      >
        {loading && (
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '13px',
              color: 'var(--ink-ghost)',
              padding: '8px',
              letterSpacing: '0.06em',
            }}
          >
            Carregando...
          </p>
        )}

        {/* Single mode: flat chapter list, no book header */}
        {!loading && projectType === 'single' && books.length > 0 && (() => {
          const book = books[0]
          return (
            <div>
              {book.chapters.length === 0 ? (
                <p
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '13px',
                    color: 'var(--ink-ghost)',
                    padding: '6px 8px 6px 8px',
                    margin: 0,
                    letterSpacing: '0.04em',
                  }}
                >
                  Nenhum capítulo ainda.
                </p>
              ) : (
                book.chapters.map((ch) => (
                  <ChapterRow
                    key={ch.id}
                    chapter={ch}
                    isActive={activeChapter?.chapterId === ch.id}
                    onSelect={() =>
                      onSelectChapter({
                        projectId: book.project_id,
                        bookId: book.id,
                        chapterId: ch.id,
                        title: ch.title,
                        status: ch.status,
                        characterIds: ch.character_ids ?? [],
                        noteIds: ch.note_ids ?? [],
                        wordGoal: ch.word_goal ?? null,
                      })
                    }
                    onRename={(title) => handleRenameChapter(book.id, ch.id, title)}
                    onDelete={() => handleDeleteChapter(book.id, ch.id)}
                    onSynopsisChange={(synopsis) => handleUpdateSynopsis(book.id, ch.id, synopsis)}
                  />
                ))
              )}

              <button
                className="btn btn-ghost btn-sm"
                onClick={() => handleCreateChapter(book.id)}
                style={{
                  width: '100%',
                  marginTop: '4px',
                  color: 'var(--ink-ghost)',
                  fontSize: '13px',
                  letterSpacing: '0.04em',
                  textAlign: 'left',
                  paddingLeft: '8px',
                }}
              >
                + Novo capítulo
              </button>
            </div>
          )
        })()}

        {/* Series mode: book tree */}
        {!loading && projectType === 'series' && books.map((book) => (
          <BookSection
            key={book.id}
            book={book}
            activeChapter={activeChapter}
            onSelectChapter={onSelectChapter}
            onRenameBook={(name) => handleRenameBook(book.id, name)}
            onDeleteBook={() => handleDeleteBook(book)}
            onCreateChapter={() => handleCreateChapter(book.id)}
            onRenameChapter={(cId, title) => handleRenameChapter(book.id, cId, title)}
            onDeleteChapter={(cId) => handleDeleteChapter(book.id, cId)}
            onSynopsisChange={(cId, synopsis) => handleUpdateSynopsis(book.id, cId, synopsis)}
          />
        ))}

        {/* Fanfiction mode: books grouped by series_name */}
        {!loading && projectType === 'fanfiction' && (() => {
          // Agrupar livros por série
          const grouped = new Map<string | null, Book[]>()
          for (const book of books) {
            const key = book.series_name ?? null
            const list = grouped.get(key) ?? []
            list.push(book)
            grouped.set(key, list)
          }

          const seriesKeys = [...grouped.keys()].filter((k): k is string => k !== null)
          const standalones = grouped.get(null) ?? []

          return (
            <>
              {seriesKeys.map((seriesKey) => (
                <div key={seriesKey} style={{ marginBottom: '8px' }}>
                  {/* Cabeçalho da série */}
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '5px 8px 5px 8px',
                    marginBottom: '2px',
                  }}>
                    <div style={{ flex: 1, height: '1px', background: 'var(--rule)' }} />
                    <span style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '10px',
                      textTransform: 'uppercase',
                      letterSpacing: '0.16em',
                      color: 'var(--ink-ghost)',
                      whiteSpace: 'nowrap',
                    }}>
                      {seriesKey}
                    </span>
                    <div style={{ flex: 1, height: '1px', background: 'var(--rule)' }} />
                  </div>

                  {grouped.get(seriesKey)!.map((book) => (
                    <BookSection
                      key={book.id}
                      book={book}
                      activeChapter={activeChapter}
                      onSelectChapter={onSelectChapter}
                      onRenameBook={(name) => handleRenameBook(book.id, name)}
                      onDeleteBook={() => handleDeleteBook(book)}
                      onCreateChapter={() => handleCreateChapter(book.id)}
                      onRenameChapter={(cId, title) => handleRenameChapter(book.id, cId, title)}
                      onDeleteChapter={(cId) => handleDeleteChapter(book.id, cId)}
                      onSynopsisChange={(cId, synopsis) => handleUpdateSynopsis(book.id, cId, synopsis)}
                    />
                  ))}
                </div>
              ))}

              {/* Avulsas (sem série) */}
              {standalones.length > 0 && (
                <div style={{ marginBottom: '8px' }}>
                  {seriesKeys.length > 0 && (
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '5px 8px',
                      marginBottom: '2px',
                    }}>
                      <div style={{ flex: 1, height: '1px', background: 'var(--rule)' }} />
                      <span style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '10px',
                        textTransform: 'uppercase',
                        letterSpacing: '0.16em',
                        color: 'var(--ink-ghost)',
                        whiteSpace: 'nowrap',
                      }}>
                        Avulsas
                      </span>
                      <div style={{ flex: 1, height: '1px', background: 'var(--rule)' }} />
                    </div>
                  )}
                  {standalones.map((book) => (
                    <BookSection
                      key={book.id}
                      book={book}
                      activeChapter={activeChapter}
                      onSelectChapter={onSelectChapter}
                      onRenameBook={(name) => handleRenameBook(book.id, name)}
                      onDeleteBook={() => handleDeleteBook(book)}
                      onCreateChapter={() => handleCreateChapter(book.id)}
                      onRenameChapter={(cId, title) => handleRenameChapter(book.id, cId, title)}
                      onDeleteChapter={(cId) => handleDeleteChapter(book.id, cId)}
                      onSynopsisChange={(cId, synopsis) => handleUpdateSynopsis(book.id, cId, synopsis)}
                    />
                  ))}
                </div>
              )}
            </>
          )
        })()}

        {/* Separador e botão novo livro — Series e Fanfiction */}
        {!loading && (projectType === 'series' || projectType === 'fanfiction') && (
          <>
            {books.length > 0 && (
              <div className="divider" style={{ margin: '12px 0 8px' }} />
            )}
            {creatingBook ? (
              <div style={{ padding: '4px 8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <input
                  className="input"
                  style={{ fontSize: '14px', padding: '5px 10px' }}
                  placeholder={projectType === 'fanfiction' ? 'Título da fanfic...' : 'Nome do livro...'}
                  value={newBookName}
                  onChange={(e) => setNewBookName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleCreateBook(newBookSeries || undefined)
                    if (e.key === 'Escape') { setCreatingBook(false); setNewBookName(''); setNewBookSeries('') }
                  }}
                  autoFocus
                  maxLength={120}
                />
                {projectType === 'fanfiction' && (
                  <input
                    className="input"
                    style={{ fontSize: '13px', padding: '4px 10px' }}
                    placeholder="Série (opcional)..."
                    value={newBookSeries}
                    onChange={(e) => setNewBookSeries(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleCreateBook(newBookSeries || undefined)
                      if (e.key === 'Escape') { setCreatingBook(false); setNewBookName(''); setNewBookSeries('') }
                    }}
                    maxLength={100}
                  />
                )}
                <div style={{ display: 'flex', gap: '4px' }}>
                  <button
                    className="btn btn-primary btn-sm"
                    style={{ flex: 1 }}
                    onClick={() => handleCreateBook(newBookSeries || undefined)}
                  >
                    Criar
                  </button>
                  <button
                    className="btn btn-ghost btn-sm btn-icon"
                    onClick={() => { setCreatingBook(false); setNewBookName(''); setNewBookSeries('') }}
                  >
                    ×
                  </button>
                </div>
              </div>
            ) : (
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setCreatingBook(true)}
                style={{
                  width: '100%',
                  color: 'var(--ink-ghost)',
                  fontSize: '13px',
                  letterSpacing: '0.04em',
                }}
              >
                {projectType === 'fanfiction' ? '+ Nova fanfic' : '+ Novo livro'}
              </button>
            )}
          </>
        )}
      </div>
    </aside>
  )
}
