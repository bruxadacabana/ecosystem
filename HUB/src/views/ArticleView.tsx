/* ============================================================
   HUB — ArticleView
   Leitura de artigo individual do archive do KOSMOS.
   ============================================================ */

import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import * as cmd from '../lib/tauri'
import type { ArticleContent, ArticleMeta } from '../types'

interface ArticleViewProps {
  archivePath: string
  article: ArticleMeta          // meta já carregada na lista
  onBack: () => void
  onReadToggled: (path: string, isRead: boolean) => void  // atualiza lista pai
}

export function ArticleView({ archivePath, article, onBack, onReadToggled }: ArticleViewProps) {
  const [content, setContent] = useState<ArticleContent | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')
  const [toggling, setToggling] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError('')
    cmd.readArticle(archivePath, article.path).then(result => {
      setLoading(false)
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      setContent(result.data)
    })
  }, [archivePath, article.path])

  async function handleToggleRead() {
    if (toggling) return
    setToggling(true)
    const result = await cmd.toggleRead(archivePath, article.path)
    setToggling(false)
    if (!result.ok) return
    const newIsRead = result.data
    // Atualiza o meta local
    if (content) {
      setContent({ ...content, meta: { ...content.meta, is_read: newIsRead } })
    }
    onReadToggled(article.path, newIsRead)
  }

  const meta = content?.meta ?? article
  const dateLabel = meta.date ? meta.date.split(' ')[0] : ''

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--paper)' }}>
      {/* Topbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '10px 20px', borderBottom: '1px solid var(--rule)', flexShrink: 0,
      }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack}>← Leituras</button>

        <div style={{ flex: 1 }} />

        {/* Botão marcar como lido */}
        <button
          onClick={handleToggleRead}
          disabled={toggling}
          style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em',
            textTransform: 'uppercase',
            padding: '4px 10px', border: '1px solid var(--rule)', borderRadius: 2,
            background: meta.is_read ? 'var(--paper-dark)' : 'var(--accent)',
            color: meta.is_read ? 'var(--ink-ghost)' : 'var(--paper)',
            cursor: toggling ? 'wait' : 'pointer',
            transition: 'background 120ms, color 120ms',
          }}
        >
          {meta.is_read ? '✓ Lido' : 'Marcar como lido'}
        </button>

        {/* Link externo */}
        {meta.url && (
          <a
            href={meta.url}
            target="_blank"
            rel="noreferrer"
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em',
              textTransform: 'uppercase', color: 'var(--ink-ghost)',
              padding: '4px 10px', border: '1px solid var(--rule)', borderRadius: 2,
              textDecoration: 'none',
              transition: 'color 120ms',
            }}
          >
            ↗ Fonte
          </a>
        )}
      </div>

      {/* Corpo */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '28px 32px 48px', maxWidth: 780, width: '100%', margin: '0 auto' }}>
        {loading && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)' }}>
            Carregando artigo…
          </p>
        )}
        {error && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#8B3A2A' }}>{error}</p>
        )}

        {!loading && !error && content && (
          <>
            {/* Cabeçalho do artigo */}
            <header style={{ marginBottom: 28, paddingBottom: 20, borderBottom: '1px solid var(--rule)' }}>
              <h1 style={{
                fontFamily: 'var(--font-display)', fontStyle: 'italic', fontWeight: 'normal',
                fontSize: 26, lineHeight: 1.2, color: 'var(--ink)', marginBottom: 12,
              }}>
                {meta.title}
              </h1>

              <div style={{
                display: 'flex', flexWrap: 'wrap', gap: '4px 16px',
                fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-ghost)',
                letterSpacing: '0.06em',
              }}>
                {meta.source && (
                  <span style={{ color: 'var(--accent)' }}>{meta.source}</span>
                )}
                {meta.author && <span>{meta.author}</span>}
                {dateLabel && <span>{dateLabel}</span>}
                {meta.url && (
                  <a
                    href={meta.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      color: 'var(--ink-ghost)', textDecoration: 'underline',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      maxWidth: 320,
                    }}
                  >
                    {meta.url}
                  </a>
                )}
              </div>
            </header>

            {/* Corpo Markdown */}
            <div className="article-body">
              <ReactMarkdown>{content.body}</ReactMarkdown>
            </div>
          </>
        )}
      </div>

      {/* Estilos do corpo Markdown */}
      <style>{`
        .article-body { color: var(--ink); }
        .article-body p { font-size: 14px; line-height: 1.75; margin-bottom: 1em; }
        .article-body h1, .article-body h2, .article-body h3 {
          font-family: var(--font-display); font-style: italic; font-weight: normal;
          margin: 1.5em 0 0.5em; color: var(--ink);
        }
        .article-body h1 { font-size: 22px; }
        .article-body h2 { font-size: 18px; }
        .article-body h3 { font-size: 15px; }
        .article-body a { color: var(--accent); }
        .article-body blockquote {
          border-left: 3px solid var(--rule); margin: 1em 0;
          padding: 0.5em 1em; font-style: italic; color: var(--ink-ghost);
        }
        .article-body code {
          font-family: var(--font-mono); font-size: 12px;
          background: var(--paper-dark); padding: 1px 4px; border-radius: 2px;
        }
        .article-body pre code { display: block; padding: 12px; overflow-x: auto; }
        .article-body ul, .article-body ol { padding-left: 1.5em; margin-bottom: 1em; }
        .article-body li { font-size: 14px; line-height: 1.7; }
        .article-body img { max-width: 100%; border-radius: 2px; }
        .article-body hr { border: none; border-top: 1px solid var(--rule); margin: 2em 0; }
      `}</style>
    </div>
  )
}
