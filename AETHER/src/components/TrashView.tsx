/* ============================================================
   AETHER — TrashView (3.3)
   Lixeira: capítulos deletados (soft) ficam recuperáveis.
   Lista todos os capítulos na lixeira de todos os livros
   do projeto. Permite restaurar ou excluir permanentemente.
   ============================================================ */

import { useEffect, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { BookMeta, ChapterMeta } from '../types'

interface TrashViewProps {
  projectId: string
  onError: (msg: string) => void
  onSuccess: (msg: string) => void
}

interface TrashEntry {
  chapter: ChapterMeta
  book: BookMeta
}

export function TrashView({ projectId, onError, onSuccess }: TrashViewProps) {
  const [entries, setEntries] = useState<TrashEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadTrash()
  }, [projectId])

  async function loadTrash() {
    setLoading(true)
    const booksResult = await cmd.listBooksForTrash(projectId)
    if (!booksResult.ok) {
      setLoading(false)
      onError(booksResult.error.message)
      return
    }

    const all: TrashEntry[] = []
    for (const book of booksResult.data) {
      const trashResult = await cmd.listTrash(projectId, book.id)
      if (trashResult.ok) {
        for (const chapter of trashResult.data) {
          all.push({ chapter, book })
        }
      }
    }

    // Mais recentes primeiro
    all.sort((a, b) =>
      (b.chapter.trashed_at ?? '').localeCompare(a.chapter.trashed_at ?? '')
    )

    setLoading(false)
    setEntries(all)
  }

  async function handleRestore(entry: TrashEntry) {
    const result = await cmd.restoreChapter(
      projectId,
      entry.book.id,
      entry.chapter.id,
    )
    if (!result.ok) {
      onError(`Erro ao restaurar: ${result.error.message}`)
      return
    }
    onSuccess(`"${entry.chapter.title}" restaurado.`)
    setEntries((prev) => prev.filter((e) => e.chapter.id !== entry.chapter.id))
  }

  async function handlePurge(entry: TrashEntry) {
    const result = await cmd.deleteChapter(
      projectId,
      entry.book.id,
      entry.chapter.id,
    )
    if (!result.ok) {
      onError(`Erro ao excluir: ${result.error.message}`)
      return
    }
    onSuccess(`"${entry.chapter.title}" excluído permanentemente.`)
    setEntries((prev) => prev.filter((e) => e.chapter.id !== entry.chapter.id))
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

  if (entries.length === 0) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
        <p style={{
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          fontSize: '20px',
          color: 'var(--ink-ghost)',
          margin: 0,
        }}>
          Lixeira vazia.
        </p>
        <p style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '11px',
          color: 'var(--ink-ghost)',
          letterSpacing: '0.06em',
          margin: 0,
        }}>
          Capítulos excluídos aparecem aqui.
        </p>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '0 0 40px' }}>
      {/* Cabeçalho */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 120px auto',
        gap: '0 12px',
        padding: '8px 32px',
        borderBottom: '1px solid var(--rule)',
        background: 'var(--paper-dark)',
        position: 'sticky',
        top: 0,
        zIndex: 1,
      }}>
        <ColHeader>Capítulo</ColHeader>
        <ColHeader>Livro</ColHeader>
        <ColHeader>Ações</ColHeader>
      </div>

      {entries.map((entry, idx) => (
        <TrashRow
          key={entry.chapter.id}
          entry={entry}
          isLast={idx === entries.length - 1}
          onRestore={() => handleRestore(entry)}
          onPurge={() => handlePurge(entry)}
        />
      ))}
    </div>
  )
}

// ----------------------------------------------------------
//  ColHeader
// ----------------------------------------------------------

function ColHeader({ children }: { children: React.ReactNode }) {
  return (
    <span style={{
      fontFamily: 'var(--font-mono)',
      fontSize: '9px',
      textTransform: 'uppercase',
      letterSpacing: '0.14em',
      color: 'var(--ink-ghost)',
    }}>
      {children}
    </span>
  )
}

// ----------------------------------------------------------
//  TrashRow
// ----------------------------------------------------------

function formatTrashedAt(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'short',
  })
}

interface TrashRowProps {
  entry: TrashEntry
  isLast: boolean
  onRestore: () => void
  onPurge: () => void
}

function TrashRow({ entry, isLast, onRestore, onPurge }: TrashRowProps) {
  const [hovered, setHovered] = useState(false)

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr 120px auto',
        gap: '0 12px',
        padding: '10px 32px',
        borderBottom: isLast ? '1px solid var(--rule)' : '1px solid transparent',
        background: hovered ? 'var(--paper-dark)' : 'transparent',
        transition: 'background var(--transition)',
        alignItems: 'center',
      }}
    >
      {/* Título + data */}
      <div>
        <p style={{
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          fontSize: '15px',
          color: 'var(--ink-light)',
          margin: '0 0 2px',
          lineHeight: 1.2,
        }}>
          {entry.chapter.title}
        </p>
        {entry.chapter.trashed_at && (
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '10px',
            color: 'var(--ink-ghost)',
            letterSpacing: '0.04em',
          }}>
            Excluído em {formatTrashedAt(entry.chapter.trashed_at)}
          </span>
        )}
      </div>

      {/* Livro */}
      <p style={{
        fontFamily: 'var(--font-mono)',
        fontSize: '11px',
        color: 'var(--ink-ghost)',
        letterSpacing: '0.04em',
        margin: 0,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}>
        {entry.book.name}
      </p>

      {/* Ações */}
      <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
        <button
          className="btn btn-ghost btn-sm"
          onClick={onRestore}
          title="Restaurar capítulo"
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '10px',
            letterSpacing: '0.06em',
            color: 'var(--accent)',
            opacity: hovered ? 1 : 0.6,
            transition: 'opacity var(--transition)',
          }}
        >
          Restaurar
        </button>
        <button
          className="btn btn-ghost btn-sm"
          onClick={onPurge}
          title="Excluir permanentemente"
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '10px',
            letterSpacing: '0.06em',
            color: 'var(--ink-ghost)',
            opacity: hovered ? 1 : 0.4,
            transition: 'opacity var(--transition)',
          }}
        >
          Excluir
        </button>
      </div>
    </div>
  )
}
