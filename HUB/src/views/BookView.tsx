/* ============================================================
   HUB — BookView
   Árvore de livros e capítulos de um projeto AETHER.
   ============================================================ */

import { useEffect, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { Book, ChapterMeta, ChapterStatus, Project } from '../types'

interface BookViewProps {
  vaultPath: string
  project: Project
  onBack: () => void
  onSelectChapter: (book: Book, chapter: ChapterMeta) => void
}

const STATUS_LABEL: Record<ChapterStatus, string> = {
  draft:    'Rascunho',
  revision: 'Revisão',
  final:    'Final',
}

const STATUS_COLOR: Record<ChapterStatus, string> = {
  draft:    'var(--ink-ghost)',
  revision: 'var(--accent)',
  final:    '#4A6741',
}

function fmtWords(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

export function BookView({ vaultPath, project, onBack, onSelectChapter }: BookViewProps) {
  const [books, setBooks] = useState<Book[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expandedBooks, setExpandedBooks] = useState<Set<string>>(new Set())

  useEffect(() => {
    cmd.listBooks(vaultPath, project.id).then(result => {
      setLoading(false)
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      const loaded = result.data
      setBooks(loaded)
      // Expandir todos os livros por padrão se for single ou tiver só 1
      if (loaded.length <= 2) {
        setExpandedBooks(new Set(loaded.map(b => b.id)))
      }
    })
  }, [vaultPath, project.id])

  function toggleBook(bookId: string) {
    setExpandedBooks(prev => {
      const next = new Set(prev)
      if (next.has(bookId)) next.delete(bookId)
      else next.add(bookId)
      return next
    })
  }

  const totalWords = books.flatMap(b => b.chapters).reduce((s, c) => s + c.word_count, 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--paper)' }}>
      {/* Topbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '10px 20px', borderBottom: '1px solid var(--rule)', flexShrink: 0,
      }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack}>← Projetos</button>
        <div style={{ flex: 1 }}>
          <h1 style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 20, color: 'var(--ink)' }}>
            {project.name}
          </h1>
        </div>
        {totalWords > 0 && (
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 10,
            color: 'var(--ink-ghost)', letterSpacing: '0.1em',
          }}>
            {fmtWords(totalWords)} palavras
          </span>
        )}
      </div>

      {/* Conteúdo */}
      <div style={{ flex: 1, overflow: 'auto', padding: '16px 24px' }}>
        {loading && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)' }}>
            Carregando…
          </p>
        )}
        {error && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#8B3A2A' }}>{error}</p>
        )}
        {!loading && !error && books.length === 0 && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)' }}>
            Nenhum livro encontrado neste projeto.
          </p>
        )}

        {books.map(book => {
          const expanded = expandedBooks.has(book.id)
          const bookWords = book.chapters.reduce((s, c) => s + c.word_count, 0)
          const isSingle = project.project_type === 'single'

          return (
            <div key={book.id} style={{ marginBottom: 8 }}>
              {/* Cabeçalho do livro — oculto em projetos single */}
              {!isSingle && (
                <button
                  onClick={() => toggleBook(book.id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                    padding: '8px 12px', background: 'var(--paper-dark)',
                    border: '1px solid var(--rule)', borderRadius: 'var(--radius)',
                    cursor: 'pointer', textAlign: 'left',
                    fontFamily: 'var(--font-mono)', fontSize: 11,
                    marginBottom: expanded ? 2 : 0,
                  }}
                >
                  <span style={{ color: 'var(--ink-ghost)', fontSize: 9 }}>
                    {expanded ? '▾' : '▸'}
                  </span>
                  <span style={{ flex: 1, color: 'var(--ink)', fontWeight: 'bold' }}>
                    {book.name}
                  </span>
                  <span style={{ color: 'var(--ink-ghost)', fontSize: 10 }}>
                    {book.chapters.length} cap. · {fmtWords(bookWords)} palavras
                  </span>
                </button>
              )}

              {/* Lista de capítulos */}
              {(expanded || isSingle) && (
                <div style={{ paddingLeft: isSingle ? 0 : 16 }}>
                  {book.chapters.map(chapter => (
                    <ChapterRow
                      key={chapter.id}
                      chapter={chapter}
                      onClick={() => onSelectChapter(book, chapter)}
                    />
                  ))}
                  {book.chapters.length === 0 && (
                    <p style={{
                      fontFamily: 'var(--font-mono)', fontSize: 10,
                      color: 'var(--ink-ghost)', padding: '8px 12px',
                    }}>
                      Nenhum capítulo.
                    </p>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  ChapterRow
// ----------------------------------------------------------

interface ChapterRowProps {
  chapter: ChapterMeta
  onClick: () => void
}

function ChapterRow({ chapter, onClick }: ChapterRowProps) {
  const [hovered, setHovered] = useState(false)

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 12, width: '100%',
        padding: '7px 12px',
        background: hovered ? 'var(--paper-dark)' : 'transparent',
        border: 'none', borderBottom: '1px solid var(--rule)',
        cursor: 'pointer', textAlign: 'left',
        transition: 'background 100ms ease',
      }}
    >
      {/* Título */}
      <span style={{
        flex: 1, fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink)',
      }}>
        {chapter.title}
      </span>

      {/* Word count */}
      {chapter.word_count > 0 && (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)' }}>
          {fmtWords(chapter.word_count)}
        </span>
      )}

      {/* Status */}
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.12em',
        textTransform: 'uppercase', color: STATUS_COLOR[chapter.status],
        minWidth: 56, textAlign: 'right',
      }}>
        {STATUS_LABEL[chapter.status]}
      </span>
    </button>
  )
}
