import React, { useState, useEffect, useRef, useCallback } from 'react'
import { fromIpc } from '../../types/errors'
import './SearchModal.css'

const db = () => (window as any).db

interface SearchResult {
  id: number
  title: string
  icon: string | null
  project_id: number
  project_name: string
  project_color: string | null
  project_icon: string | null
  updated_at: string
}

interface Props {
  dark: boolean
  onClose: () => void
  onOpen: (projectId: number, pageId: number) => void
}

export function SearchModal({ dark, onClose, onOpen }: Props) {
  const [query,   setQuery]   = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [recents, setRecents] = useState<SearchResult[]>([])
  const [active,  setActive]  = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const ink2 = dark ? '#8A7A62' : '#9C8E7A'

  // Carregar recentes ao abrir
  useEffect(() => {
    fromIpc<SearchResult[]>(() => db().pages.listRecent(8), 'listRecent')
      .then(r => r.match(data => setRecents(data), _e => {}))
    inputRef.current?.focus()
  }, [])

  // Busca em tempo real
  useEffect(() => {
    if (!query.trim()) { setResults([]); setActive(0); return }
    fromIpc<SearchResult[]>(() => db().pages.search(query.trim(), 20), 'searchPages')
      .then(r => r.match(data => { setResults(data); setActive(0) }, _e => {}))
  }, [query])

  const items = query.trim() ? results : recents
  const label = query.trim() ? 'Resultados' : 'Recentes'

  const select = useCallback((item: SearchResult) => {
    onOpen(item.project_id, item.id)
    onClose()
  }, [onOpen, onClose])

  // Teclado
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onClose(); return }
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActive(a => Math.min(a + 1, items.length - 1))
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActive(a => Math.max(a - 1, 0))
      }
      if (e.key === 'Enter' && items[active]) {
        select(items[active])
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [items, active, select, onClose])

  return (
    <div className="search-overlay" onClick={onClose}>
      <div
        className="search-panel"
        onClick={e => e.stopPropagation()}
      >
        {/* Input */}
        <div className="search-input-row">
          <span className="search-icon">⌕</span>
          <input
            ref={inputRef}
            className="search-input"
            placeholder="Buscar páginas..."
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          <span className="search-kbd">Esc</span>
        </div>

        {/* Resultados */}
        <div className="search-results">
          {items.length > 0 ? (
            <>
              <div className="search-section-label">{label}</div>
              {items.map((item, i) => (
                <button
                  key={item.id}
                  className={`search-result-item${i === active ? ' search-result-item--active' : ''}`}
                  onClick={() => select(item)}
                  onMouseEnter={() => setActive(i)}
                >
                  <span className="search-result-icon">
                    {item.icon ?? '◦'}
                  </span>
                  <div className="search-result-body">
                    <div className="search-result-title">{item.title}</div>
                    <div
                      className="search-result-project"
                      style={{ color: item.project_color ?? ink2 }}
                    >
                      {item.project_icon ?? '✦'} {item.project_name}
                    </div>
                  </div>
                </button>
              ))}
            </>
          ) : (
            <div className="search-empty">
              {query.trim() ? 'Nenhuma página encontrada' : 'Nenhuma página recente'}
            </div>
          )}
        </div>

        {/* Rodapé */}
        <div className="search-footer">
          <span className="search-footer-hint">
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>↑↓</span> navegar
          </span>
          <span className="search-footer-hint">
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>↵</span> abrir
          </span>
          <span className="search-footer-hint">
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>Esc</span> fechar
          </span>
        </div>
      </div>
    </div>
  )
}
