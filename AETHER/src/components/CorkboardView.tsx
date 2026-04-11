/* ============================================================
   AETHER — CorkboardView (3.1)
   Vista mural: capítulos como cartões dispostos em grade.
   Cada cartão: título, sinopse, status e contagem de palavras.
   ============================================================ */

import { useEffect, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { Book, ChapterMeta, ProjectType } from '../types'
import type { ActiveChapter } from './Binder'

interface CorkboardViewProps {
  projectId: string
  projectType: ProjectType
  defaultBookId?: string
  onSelectChapter: (chapter: ActiveChapter) => void
  onError: (msg: string) => void
}

export function CorkboardView({
  projectId,
  projectType,
  defaultBookId,
  onSelectChapter,
  onError,
}: CorkboardViewProps) {
  const [books, setBooks] = useState<Book[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadBooks()
  }, [projectId])

  async function loadBooks() {
    setLoading(true)
    if (projectType === 'single' && defaultBookId) {
      const result = await cmd.openBook(projectId, defaultBookId)
      setLoading(false)
      if (!result.ok) { onError(result.error.message); return }
      setBooks([result.data])
    } else {
      const listResult = await cmd.listBooks(projectId)
      if (!listResult.ok) { setLoading(false); onError(listResult.error.message); return }
      const fullBooks: Book[] = []
      for (const meta of listResult.data) {
        const r = await cmd.openBook(projectId, meta.id)
        if (r.ok) fullBooks.push(r.data)
      }
      setLoading(false)
      setBooks(fullBooks)
    }
  }

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <p style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '13px',
          color: 'var(--ink-ghost)',
          letterSpacing: '0.06em',
          animation: 'blink 1.2s ease infinite',
        }}>
          · · ·
        </p>
      </div>
    )
  }

  const hasAnyChapter = books.some((b) => b.chapters.length > 0)
  if (!hasAnyChapter) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <p style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '13px',
          color: 'var(--ink-ghost)',
          letterSpacing: '0.06em',
        }}>
          Nenhum capítulo ainda.
        </p>
      </div>
    )
  }

  return (
    <div style={{
      flex: 1,
      overflowY: 'auto',
      padding: '28px 32px 40px',
      background: 'var(--paper)',
    }}>
      {projectType === 'single' && books[0] && (
        <CardGrid
          chapters={books[0].chapters}
          bookId={books[0].id}
          projectId={projectId}
          onSelectChapter={onSelectChapter}
        />
      )}

      {(projectType === 'series' || projectType === 'fanfiction') &&
        books.map((book) => (
          <div key={book.id} style={{ marginBottom: '36px' }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              marginBottom: '16px',
            }}>
              <span style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                textTransform: 'uppercase',
                letterSpacing: '0.18em',
                color: 'var(--ink-ghost)',
                whiteSpace: 'nowrap',
              }}>
                {book.name}
              </span>
              <div style={{ flex: 1, height: '1px', background: 'var(--rule)' }} />
            </div>

            {book.chapters.length === 0 ? (
              <p style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
                color: 'var(--ink-ghost)',
                margin: 0,
                letterSpacing: '0.04em',
              }}>
                Sem capítulos.
              </p>
            ) : (
              <CardGrid
                chapters={book.chapters}
                bookId={book.id}
                projectId={projectId}
                onSelectChapter={onSelectChapter}
              />
            )}
          </div>
        ))}
    </div>
  )
}

// ----------------------------------------------------------
//  CardGrid
// ----------------------------------------------------------

interface CardGridProps {
  chapters: ChapterMeta[]
  bookId: string
  projectId: string
  onSelectChapter: (ch: ActiveChapter) => void
}

function CardGrid({ chapters, bookId, projectId, onSelectChapter }: CardGridProps) {
  return (
    <div style={{
      display: 'flex',
      flexWrap: 'wrap',
      gap: '14px',
    }}>
      {chapters.map((ch) => (
        <CorkCard
          key={ch.id}
          chapter={ch}
          onClick={() =>
            onSelectChapter({
              projectId,
              bookId,
              chapterId: ch.id,
              title: ch.title,
              status: ch.status,
              characterIds: ch.character_ids ?? [],
              noteIds: ch.note_ids ?? [],
              wordGoal: ch.word_goal ?? null,
            })
          }
        />
      ))}
    </div>
  )
}

// ----------------------------------------------------------
//  CorkCard — cartão individual de capítulo
// ----------------------------------------------------------

const STATUS_COLOR: Record<string, string> = {
  draft:    'var(--ink-ghost)',
  revision: 'var(--accent)',
  final:    'var(--accent-green)',
}

const STATUS_LABEL: Record<string, string> = {
  draft:    'Rascunho',
  revision: 'Revisão',
  final:    'Final',
}

interface CorkCardProps {
  chapter: ChapterMeta
  onClick: () => void
}

function CorkCard({ chapter, onClick }: CorkCardProps) {
  const [hovered, setHovered] = useState(false)

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClick() }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        width: '196px',
        minHeight: '164px',
        background: 'var(--paper-dark)',
        border: `1px solid ${hovered ? 'var(--accent)' : 'var(--rule)'}`,
        borderRadius: 'var(--radius)',
        padding: '13px 15px',
        cursor: 'pointer',
        boxShadow: hovered
          ? '3px 3px 0 var(--stamp)'
          : '3px 3px 0 var(--paper-darker)',
        transform: hovered ? 'translate(-1px, -1px)' : 'none',
        transition: 'box-shadow var(--transition), border-color var(--transition), transform var(--transition)',
        display: 'flex',
        flexDirection: 'column',
        gap: '7px',
        animation: 'paperFall 0.22s ease-out both',
        outline: 'none',
      }}
    >
      {/* Status + contagem */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
          <span style={{
            width: '5px',
            height: '5px',
            borderRadius: '50%',
            background: STATUS_COLOR[chapter.status] ?? 'var(--ink-ghost)',
            flexShrink: 0,
          }} />
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '9px',
            textTransform: 'uppercase',
            letterSpacing: '0.12em',
            color: STATUS_COLOR[chapter.status] ?? 'var(--ink-ghost)',
          }}>
            {STATUS_LABEL[chapter.status] ?? chapter.status}
          </span>
        </div>
        {chapter.word_count > 0 && (
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '9px',
            color: 'var(--ink-ghost)',
            letterSpacing: '0.04em',
          }}>
            {chapter.word_count < 1000
              ? `${chapter.word_count}`
              : `${(chapter.word_count / 1000).toFixed(1)}k`}
          </span>
        )}
      </div>

      {/* Título */}
      <p style={{
        fontFamily: 'var(--font-display)',
        fontStyle: 'italic',
        fontSize: '16px',
        color: 'var(--ink)',
        margin: 0,
        lineHeight: 1.2,
      }}>
        {chapter.title}
      </p>

      {/* Sinopse */}
      {chapter.synopsis ? (
        <p style={{
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          fontSize: '12px',
          color: 'var(--ink-faint)',
          margin: 0,
          lineHeight: 1.55,
          overflow: 'hidden',
          display: '-webkit-box',
          WebkitLineClamp: 4,
          WebkitBoxOrient: 'vertical',
        }}>
          {chapter.synopsis}
        </p>
      ) : (
        <p style={{
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          fontSize: '12px',
          color: 'var(--ink-ghost)',
          margin: 0,
          lineHeight: 1.55,
        }}>
          Sem sinopse.
        </p>
      )}
    </div>
  )
}
