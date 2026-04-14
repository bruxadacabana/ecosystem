/* ============================================================
   HUB — ReadingView
   Lista de artigos do archive do KOSMOS com filtros.
   ============================================================ */

import { useEffect, useMemo, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { ArticleMeta } from '../types'

interface ReadingViewProps {
  archivePath: string
  onBack: () => void
  onSelectArticle: (article: ArticleMeta) => void
}

type ReadFilter = 'all' | 'unread' | 'read'

export function ReadingView({ archivePath, onBack, onSelectArticle }: ReadingViewProps) {
  const [articles, setArticles]       = useState<ArticleMeta[]>([])
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState('')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [readFilter, setReadFilter]   = useState<ReadFilter>('all')

  useEffect(() => {
    cmd.listArticles(archivePath).then(result => {
      setLoading(false)
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      setArticles(result.data)
    })
  }, [archivePath])

  // Fontes únicas para o filtro de fonte
  const sources = useMemo(() => {
    const set = new Set(articles.map(a => a.source))
    return Array.from(set).sort()
  }, [articles])

  const unreadCount = useMemo(
    () => articles.filter(a => !a.is_read).length,
    [articles],
  )

  const filtered = useMemo(() => {
    return articles.filter(a => {
      const sourceOk = sourceFilter === 'all' || a.source === sourceFilter
      const readOk =
        readFilter === 'all' ||
        (readFilter === 'unread' && !a.is_read) ||
        (readFilter === 'read'   &&  a.is_read)
      return sourceOk && readOk
    })
  }, [articles, sourceFilter, readFilter])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--paper)' }}>
      {/* Topbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '10px 20px', borderBottom: '1px solid var(--rule)', flexShrink: 0,
      }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack}>← Hub</button>
        <h1 style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 20, color: 'var(--ink)' }}>
          Leituras
        </h1>
        {unreadCount > 0 && (
          <span style={{
            background: 'var(--accent)',
            color: 'var(--paper)',
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            letterSpacing: '0.08em',
            padding: '2px 7px',
            borderRadius: 99,
          }}>
            {unreadCount} não lido{unreadCount !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Filtros */}
      {!loading && !error && articles.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '8px 20px', borderBottom: '1px solid var(--rule)',
          flexShrink: 0, flexWrap: 'wrap',
        }}>
          {/* Filtro de fonte */}
          <select
            value={sourceFilter}
            onChange={e => setSourceFilter(e.target.value)}
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 10,
              background: 'var(--paper)', color: 'var(--ink)',
              border: '1px solid var(--rule)', borderRadius: 2, padding: '3px 6px',
              cursor: 'pointer',
            }}
          >
            <option value="all">Todas as fontes</option>
            {sources.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

          {/* Filtro de lido */}
          <div style={{ display: 'flex', gap: 4 }}>
            {(['all', 'unread', 'read'] as ReadFilter[]).map(f => (
              <button
                key={f}
                onClick={() => setReadFilter(f)}
                style={{
                  fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  padding: '3px 8px', border: '1px solid var(--rule)', borderRadius: 2,
                  background: readFilter === f ? 'var(--accent)' : 'transparent',
                  color: readFilter === f ? 'var(--paper)' : 'var(--ink-ghost)',
                  cursor: 'pointer',
                  transition: 'background 120ms, color 120ms',
                }}
              >
                {f === 'all' ? 'Todos' : f === 'unread' ? 'Não lidos' : 'Lidos'}
              </button>
            ))}
          </div>

          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-ghost)', marginLeft: 'auto' }}>
            {filtered.length} artigo{filtered.length !== 1 ? 's' : ''}
          </span>
        </div>
      )}

      {/* Lista */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 20px 32px' }}>
        {loading && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)', padding: '20px 0' }}>
            Carregando artigos…
          </p>
        )}
        {error && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#8B3A2A', padding: '20px 0' }}>{error}</p>
        )}
        {!loading && !error && articles.length === 0 && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)', padding: '20px 0' }}>
            Nenhum artigo encontrado no archive.
          </p>
        )}
        {!loading && !error && articles.length > 0 && filtered.length === 0 && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)', padding: '20px 0' }}>
            Nenhum artigo corresponde aos filtros.
          </p>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {filtered.map(article => (
            <ArticleRow
              key={article.path}
              article={article}
              onClick={() => onSelectArticle(article)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  ArticleRow
// ----------------------------------------------------------

interface ArticleRowProps {
  article: ArticleMeta
  onClick: () => void
}

function ArticleRow({ article, onClick }: ArticleRowProps) {
  const [hovered, setHovered] = useState(false)

  // Formatar data legível
  const dateLabel = article.date
    ? article.date.split(' ')[0]  // apenas YYYY-MM-DD
    : ''

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '10px 12px',
        border: '1px solid var(--rule)',
        borderRadius: 2,
        background: hovered ? 'var(--paper-dark)' : 'transparent',
        cursor: 'pointer', textAlign: 'left',
        transition: 'background 120ms',
        width: '100%',
      }}
    >
      {/* Indicador lido/não lido */}
      <span style={{
        width: 7, height: 7,
        borderRadius: '50%',
        background: article.is_read ? 'transparent' : 'var(--accent)',
        border: article.is_read ? '1px solid var(--rule)' : 'none',
        flexShrink: 0,
      }} />

      {/* Conteúdo */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontFamily: 'var(--font-body)',
          fontSize: 13, color: 'var(--ink)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          opacity: article.is_read ? 0.55 : 1,
        }}>
          {article.title}
        </div>
        <div style={{
          display: 'flex', gap: 10, marginTop: 2,
          fontFamily: 'var(--font-mono)', fontSize: 9,
          color: 'var(--ink-ghost)', letterSpacing: '0.06em',
        }}>
          <span>{article.source}</span>
          {article.author && <span>· {article.author}</span>}
          {dateLabel && <span style={{ marginLeft: 'auto' }}>{dateLabel}</span>}
        </div>
      </div>
    </button>
  )
}
