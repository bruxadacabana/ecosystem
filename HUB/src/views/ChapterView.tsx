/* ============================================================
   HUB — ChapterView
   Leitura de capítulo do AETHER com react-markdown.
   ============================================================ */

import { useEffect, useState } from 'react'
import Markdown from 'react-markdown'
import * as cmd from '../lib/tauri'
import type { Book, ChapterMeta } from '../types'

interface ChapterViewProps {
  vaultPath: string
  projectId: string
  book: Book
  chapter: ChapterMeta
  onBack: () => void
}

export function ChapterView({ vaultPath, projectId, book, chapter, onBack }: ChapterViewProps) {
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    setError('')
    setContent('')
    cmd.readChapter(vaultPath, projectId, book.id, chapter.id).then(result => {
      setLoading(false)
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      setContent(result.data)
    })
  }, [vaultPath, projectId, book.id, chapter.id])

  function fmtWords(n: number) {
    return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--paper)' }}>
      {/* Topbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '10px 20px', borderBottom: '1px solid var(--rule)', flexShrink: 0,
      }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack}>← {book.name}</button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h1 style={{
            fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 18,
            color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {chapter.title}
          </h1>
        </div>
        {chapter.word_count > 0 && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)', flexShrink: 0 }}>
            {fmtWords(chapter.word_count)} palavras
          </span>
        )}
      </div>

      {/* Corpo */}
      <div style={{ flex: 1, overflow: 'auto', padding: '40px 0' }}>
        {loading && (
          <p style={{
            fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)',
            textAlign: 'center',
          }}>
            Carregando…
          </p>
        )}
        {error && (
          <p style={{
            fontFamily: 'var(--font-mono)', fontSize: 11, color: '#8B3A2A',
            textAlign: 'center',
          }}>
            {error}
          </p>
        )}
        {!loading && !error && (
          <div style={{ maxWidth: 680, margin: '0 auto', padding: '0 32px' }}>
            {/* Synopsis (se houver) */}
            {chapter.synopsis && (
              <p style={{
                fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)',
                fontStyle: 'italic', marginBottom: 32, paddingBottom: 24,
                borderBottom: '1px solid var(--rule)',
              }}>
                {chapter.synopsis}
              </p>
            )}

            {/* Conteúdo Markdown */}
            <div className="chapter-content">
              <Markdown
                components={{
                  p: ({ children }) => (
                    <p style={{
                      fontFamily: 'var(--font-display)',
                      fontStyle: 'italic',
                      fontSize: 16,
                      lineHeight: 1.8,
                      color: 'var(--ink)',
                      marginBottom: '1.2em',
                      textIndent: '1.5em',
                    }}>
                      {children}
                    </p>
                  ),
                  h1: ({ children }) => (
                    <h1 style={{
                      fontFamily: 'var(--font-display)', fontStyle: 'italic',
                      fontSize: 24, color: 'var(--ink)', marginBottom: '0.8em',
                      marginTop: '1.5em', textAlign: 'center',
                    }}>
                      {children}
                    </h1>
                  ),
                  h2: ({ children }) => (
                    <h2 style={{
                      fontFamily: 'var(--font-display)', fontStyle: 'italic',
                      fontSize: 20, color: 'var(--ink)', marginBottom: '0.6em',
                      marginTop: '1.2em',
                    }}>
                      {children}
                    </h2>
                  ),
                  h3: ({ children }) => (
                    <h3 style={{
                      fontFamily: 'var(--font-mono)', fontSize: 12,
                      letterSpacing: '0.12em', textTransform: 'uppercase',
                      color: 'var(--ink-ghost)', marginBottom: '0.5em',
                      marginTop: '1em',
                    }}>
                      {children}
                    </h3>
                  ),
                  em: ({ children }) => (
                    <em style={{ fontStyle: 'normal', color: 'var(--ink)' }}>
                      {children}
                    </em>
                  ),
                  strong: ({ children }) => (
                    <strong style={{ fontWeight: 'bold' }}>{children}</strong>
                  ),
                  hr: () => (
                    <div style={{
                      textAlign: 'center', margin: '2em 0',
                      color: 'var(--ink-ghost)', fontFamily: 'var(--font-display)',
                      fontSize: 18,
                    }}>
                      * * *
                    </div>
                  ),
                  blockquote: ({ children }) => (
                    <blockquote style={{
                      borderLeft: '2px solid var(--accent)',
                      paddingLeft: 16, marginLeft: 0,
                      color: 'var(--ink-ghost)',
                      fontFamily: 'var(--font-display)', fontStyle: 'italic',
                    }}>
                      {children}
                    </blockquote>
                  ),
                }}
              >
                {content}
              </Markdown>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
