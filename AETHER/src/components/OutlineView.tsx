/* ============================================================
   AETHER — OutlineView (3.2)
   Vista esboço: lista de capítulos com status, sinopse
   e contagem de palavras. Agrupado por livro.
   ============================================================ */

import { useEffect, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { Book, ChapterMeta, ChapterStatus, ProjectType } from '../types'
import type { ActiveChapter } from './Binder'

interface OutlineViewProps {
  projectId: string
  projectType: ProjectType
  defaultBookId?: string
  onSelectChapter: (chapter: ActiveChapter) => void
  onError: (msg: string) => void
}

export function OutlineView({
  projectId,
  projectType,
  defaultBookId,
  onSelectChapter,
  onError,
}: OutlineViewProps) {
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

  const showBookHeader = projectType !== 'single'

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '0 0 40px' }}>
      {/* Cabeçalho da tabela */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '16px 1fr 140px 80px',
        gap: '0 12px',
        padding: '8px 32px',
        borderBottom: '1px solid var(--rule)',
        background: 'var(--paper-dark)',
        position: 'sticky',
        top: 0,
        zIndex: 1,
      }}>
        <span /> {/* status dot */}
        <ColHeader>Título</ColHeader>
        <ColHeader>Sinopse</ColHeader>
        <ColHeader align="right">Palavras</ColHeader>
      </div>

      {/* Linhas por livro */}
      {books.map((book) => (
        <div key={book.id}>
          {showBookHeader && (
            <div style={{
              padding: '10px 32px 6px',
              borderBottom: '1px solid var(--rule)',
              background: 'var(--paper-dark)',
            }}>
              <span style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '10px',
                textTransform: 'uppercase',
                letterSpacing: '0.18em',
                color: 'var(--ink-ghost)',
              }}>
                {book.name}
              </span>
            </div>
          )}

          {book.chapters.length === 0 && (
            <div style={{ padding: '10px 32px' }}>
              <span style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
                color: 'var(--ink-ghost)',
                letterSpacing: '0.04em',
              }}>
                Sem capítulos.
              </span>
            </div>
          )}

          {book.chapters.map((ch, idx) => (
            <OutlineRow
              key={ch.id}
              chapter={ch}
              index={idx}
              isLast={idx === book.chapters.length - 1}
              onClick={() =>
                onSelectChapter({
                  projectId,
                  bookId: book.id,
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
      ))}
    </div>
  )
}

// ----------------------------------------------------------
//  ColHeader
// ----------------------------------------------------------

function ColHeader({ children, align = 'left' }: { children: React.ReactNode; align?: 'left' | 'right' }) {
  return (
    <span style={{
      fontFamily: 'var(--font-mono)',
      fontSize: '9px',
      textTransform: 'uppercase',
      letterSpacing: '0.14em',
      color: 'var(--ink-ghost)',
      textAlign: align,
    }}>
      {children}
    </span>
  )
}

// ----------------------------------------------------------
//  OutlineRow
// ----------------------------------------------------------

const STATUS_COLOR: Record<ChapterStatus, string> = {
  draft:    'var(--ink-ghost)',
  revision: 'var(--accent)',
  final:    'var(--accent-green)',
}

const STATUS_LABEL: Record<ChapterStatus, string> = {
  draft:    'Rascunho',
  revision: 'Revisão',
  final:    'Final',
}

interface OutlineRowProps {
  chapter: ChapterMeta
  index: number
  isLast: boolean
  onClick: () => void
}

function OutlineRow({ chapter, index, isLast, onClick }: OutlineRowProps) {
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
        display: 'grid',
        gridTemplateColumns: '16px 1fr 140px 80px',
        gap: '0 12px',
        padding: '10px 32px',
        borderBottom: isLast ? '1px solid var(--rule)' : '1px solid transparent',
        background: hovered ? 'var(--paper-dark)' : 'transparent',
        cursor: 'pointer',
        transition: 'background var(--transition)',
        alignItems: 'start',
        outline: 'none',
        animation: `fadeIn ${0.08 + index * 0.03}s ease both`,
      }}
    >
      {/* Status dot */}
      <div style={{ paddingTop: '3px', display: 'flex', justifyContent: 'center' }}>
        <span
          title={STATUS_LABEL[chapter.status]}
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            background: STATUS_COLOR[chapter.status],
            flexShrink: 0,
            display: 'inline-block',
          }}
        />
      </div>

      {/* Título */}
      <p style={{
        fontFamily: 'var(--font-display)',
        fontStyle: 'italic',
        fontSize: '15px',
        color: 'var(--ink)',
        margin: 0,
        lineHeight: 1.3,
      }}>
        {chapter.title}
      </p>

      {/* Sinopse */}
      <p style={{
        fontFamily: 'var(--font-display)',
        fontStyle: 'italic',
        fontSize: '12px',
        color: chapter.synopsis ? 'var(--ink-faint)' : 'var(--ink-ghost)',
        margin: 0,
        lineHeight: 1.5,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}>
        {chapter.synopsis ?? '—'}
      </p>

      {/* Palavras */}
      <p style={{
        fontFamily: 'var(--font-mono)',
        fontSize: '11px',
        color: 'var(--ink-faint)',
        margin: 0,
        textAlign: 'right',
        lineHeight: 1.3,
      }}>
        {chapter.word_count > 0
          ? chapter.word_count < 1000
            ? String(chapter.word_count)
            : `${(chapter.word_count / 1000).toFixed(1)}k`
          : '—'}
      </p>
    </div>
  )
}
