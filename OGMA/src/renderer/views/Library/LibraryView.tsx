import React, { useEffect, useState, useMemo } from 'react'
import { SubSection } from '../../components/Sidebar/Sidebar'
import { fromIpc } from '../../types/errors'
import './LibraryView.css'

const db = () => (window as any).db

// ── Tipos ─────────────────────────────────────────────────────────────────────

interface Reading {
  id:               number
  resource_id:      number | null
  title:            string
  reading_type:     string
  author:           string | null
  publisher:        string | null
  year:             number | null
  isbn:             string | null
  status:           string
  rating:           number | null
  current_page:     number
  total_pages:      number | null
  date_start:       string | null
  date_end:         string | null
  review:           string | null
  progress_type:    'pages' | 'percent'
  progress_percent: number
  created_at:       string
  updated_at:       string
}

interface Resource {
  id:            number
  title:         string
  resource_type: string | null
  url:           string | null
  description:   string | null
  tags_json:     string | null
  metadata_json: string | null
  created_at:    string
  // Leitura associada (LEFT JOIN)
  reading_status:           string | null
  reading_current_page:     number | null
  reading_total_pages:      number | null
  reading_rating:           number | null
  reading_progress_type:    string | null
  reading_progress_percent: number | null
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const READING_STATUS: Record<string, { label: string; color: string }> = {
  want:    { label: 'Quero ler',  color: '#8A7A62' },
  reading: { label: 'Lendo',     color: '#4A7A8A' },
  done:    { label: 'Lido',      color: '#4A6741' },
  paused:  { label: 'Pausado',   color: '#8B7355' },
}

const RESOURCE_TYPE_ICONS: Record<string, string> = {
  link:     '🔗',
  livro:    '📖',
  artigo:   '📄',
  tool:     '⚙',
  template: '◧',
  dataset:  '◈',
  doc:      '📃',
  video:    '▶',
  podcast:  '🎙',
  other:    '◦',
}

type MetaField = { key: string; label: string; type?: 'number' | 'url' }

const META_FIELDS: Record<string, MetaField[]> = {
  livro:    [
    { key: 'author',    label: 'Autor(es)' },
    { key: 'publisher', label: 'Editora' },
    { key: 'year',      label: 'Ano',      type: 'number' },
    { key: 'pages',     label: 'Páginas',  type: 'number' },
    { key: 'isbn',      label: 'ISBN' },
    { key: 'language',  label: 'Língua' },
    { key: 'cover_url', label: 'Capa (URL)', type: 'url' },
  ],
  artigo:   [
    { key: 'authors', label: 'Autores' },
    { key: 'journal', label: 'Revista/Journal' },
    { key: 'year',    label: 'Ano', type: 'number' },
    { key: 'doi',     label: 'DOI' },
    { key: 'volume',  label: 'Volume' },
    { key: 'issue',   label: 'Número' },
  ],
  video:    [
    { key: 'channel',       label: 'Canal' },
    { key: 'platform',      label: 'Plataforma' },
    { key: 'duration',      label: 'Duração' },
    { key: 'thumbnail_url', label: 'Thumbnail', type: 'url' },
  ],
  podcast:  [
    { key: 'host',     label: 'Host' },
    { key: 'series',   label: 'Série' },
    { key: 'episode',  label: 'Episódio' },
    { key: 'duration', label: 'Duração' },
  ],
  tool:     [
    { key: 'version',    label: 'Versão' },
    { key: 'platform',   label: 'Plataforma' },
    { key: 'license',    label: 'Licença' },
    { key: 'github_url', label: 'GitHub', type: 'url' },
  ],
  dataset:  [
    { key: 'format',  label: 'Formato' },
    { key: 'license', label: 'Licença' },
    { key: 'source',  label: 'Fonte' },
  ],
  doc:      [
    { key: 'format',   label: 'Formato' },
    { key: 'version',  label: 'Versão' },
    { key: 'language', label: 'Língua' },
  ],
  template: [
    { key: 'format',     label: 'Formato' },
    { key: 'source_url', label: 'URL Original', type: 'url' },
  ],
  link:     [
    { key: 'domain',   label: 'Domínio' },
    { key: 'language', label: 'Língua' },
  ],
}

function calcProgress(r: Reading | { progress_type?: string | null; progress_percent?: number | null; current_page?: number | null; total_pages?: number | null; reading_progress_type?: string | null; reading_progress_percent?: number | null; reading_current_page?: number | null; reading_total_pages?: number | null }): number | null {
  // Suporte a objecto Reading directo ou Resource com campos reading_*
  const type    = (r as any).progress_type    ?? (r as any).reading_progress_type    ?? 'pages'
  const pct     = (r as any).progress_percent ?? (r as any).reading_progress_percent ?? null
  const cur     = (r as any).current_page     ?? (r as any).reading_current_page     ?? 0
  const total   = (r as any).total_pages      ?? (r as any).reading_total_pages      ?? null
  if (type === 'percent') return pct != null ? Math.min(100, Math.max(0, pct)) : null
  return total && total > 0 ? Math.round((cur / total) * 100) : null
}

function ReadingProgress({ r, dark, compact = false }: { r: Resource; dark: boolean; compact?: boolean }) {
  if (!r.reading_status) return null
  const st      = READING_STATUS[r.reading_status] ?? READING_STATUS.want
  const progress = calcProgress(r)
  const border = dark ? '#3A3020' : '#C4B9A8'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: compact ? 2 : 3,
      marginTop: compact ? 3 : 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: compact ? 9 : 10, color: st.color, fontWeight: 600 }}>{st.label}</span>
        {progress !== null && (
          <span style={{ fontSize: compact ? 9 : 10, color: dark ? '#8A7A62' : '#9C8E7A' }}>
            {progress}%
          </span>
        )}
      </div>
      {progress !== null && (
        <div style={{ height: compact ? 2 : 3, background: border, borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${progress}%`,
            background: st.color, borderRadius: 2, transition: 'width 300ms' }} />
        </div>
      )}
    </div>
  )
}

function stars(n: number | null): string {
  if (!n) return ''
  return '★'.repeat(Math.min(n, 5)) + '☆'.repeat(Math.max(0, 5 - n))
}

// ── Modal de leitura ──────────────────────────────────────────────────────────

function ReadingModal({ initial, dark, onSave, onClose }: {
  initial?: Reading | null; dark: boolean;
  onSave: (data: any) => void; onClose: () => void
}) {
  const [resourceId,    setResourceId]    = useState<number | null>(initial?.resource_id ?? null)
  const [title,         setTitle]         = useState(initial?.title           ?? '')
  const [status,        setStatus]        = useState(initial?.status          ?? 'reading')
  const [progressType,  setProgressType]  = useState<'pages' | 'percent'>(initial?.progress_type ?? 'pages')
  const [curPage,       setCurPage]       = useState(String(initial?.current_page     ?? ''))
  const [totPages,      setTotPages]      = useState(String(initial?.total_pages      ?? ''))
  const [initPercent,   setInitPercent]   = useState(String(initial?.progress_percent ?? ''))
  const [dateStart,     setDateStart]     = useState(initial?.date_start ?? '')
  const [dateEnd,       setDateEnd]       = useState(initial?.date_end   ?? '')
  const [rating,        setRating]        = useState(String(initial?.rating    ?? ''))
  const [review,        setReview]        = useState(initial?.review           ?? '')
  const [resources, setResources] = useState<Resource[]>([])
  const [resQuery,  setResQuery]  = useState('')

  useEffect(() => {
    fromIpc<Resource[]>(() => db().resources.list(), 'listResources')
      .then(r => r.match(data => setResources(data), _e => {}))
  }, [])

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'

  const filteredRes = useMemo(() => {
    const q = resQuery.toLowerCase()
    return resources.filter(r =>
      !q || r.title.toLowerCase().includes(q) || (r.resource_type ?? '').includes(q)
    ).slice(0, 6)
  }, [resources, resQuery])

  const selectResource = (r: Resource) => {
    setResourceId(r.id)
    setTitle(r.title)
    setResQuery('')
  }

  const clearResource = () => {
    setResourceId(null)
    setTitle('')
  }

  const handleSave = () => {
    if (!title.trim()) return
    onSave({
      ...(initial ? { id: initial.id } : {}),
      resource_id:      resourceId,
      title:            title.trim(),
      status,
      progress_type:    progressType,
      progress_percent: progressType === 'percent' ? (initPercent ? parseInt(initPercent) : 0) : 0,
      current_page:     progressType === 'pages' && curPage ? parseInt(curPage) : 0,
      total_pages:      progressType === 'pages' && totPages ? parseInt(totPages) : null,
      date_start:       dateStart || null,
      date_end:         dateEnd   || null,
      rating:           rating ? parseInt(rating) : null,
      review:           review.trim() || null,
    })
  }

  return (
    <div className="library-modal-overlay" onClick={onClose}>
      <div className="library-modal" onClick={e => e.stopPropagation()}
        style={{ background: dark ? '#211D16' : undefined, borderColor: border }}>
        <h2 className="library-modal-title" style={{ color: ink }}>
          {initial ? 'Editar leitura' : 'Registar leitura'}
        </h2>

        {/* Seletor de recurso existente */}
        {!resourceId ? (
          <div className="library-modal-field">
            <label className="library-modal-label" style={{ color: ink2 }}>Buscar nos recursos</label>
            <input className="library-modal-input" value={resQuery}
              onChange={e => setResQuery(e.target.value)}
              placeholder="Nome do livro ou recurso…" autoFocus
              style={{ background: dark ? '#2A2520' : undefined, color: ink, borderColor: border }} />
            {resQuery && filteredRes.length > 0 && (
              <div style={{ border: `1px solid ${border}`, borderTop: 'none', borderRadius: '0 0 4px 4px',
                background: dark ? '#2A2520' : '#F5F0E8', maxHeight: 180, overflowY: 'auto' }}>
                {filteredRes.map(r => (
                  <button key={r.id} onClick={() => selectResource(r)} style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    width: '100%', padding: '8px 12px', background: 'none',
                    border: 'none', cursor: 'pointer', textAlign: 'left',
                    borderBottom: `1px solid ${border}`,
                  }}
                    onMouseEnter={e => (e.currentTarget.style.background = dark ? '#3A3020' : '#EDE7D9')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                  >
                    <span style={{ fontSize: 14 }}>{RESOURCE_TYPE_ICONS[r.resource_type ?? ''] ?? '◦'}</span>
                    <div>
                      <div style={{ fontSize: 13, color: ink }}>{r.title}</div>
                      {r.resource_type && <div style={{ fontSize: 10, color: ink2 }}>{r.resource_type}</div>}
                    </div>
                  </button>
                ))}
              </div>
            )}
            {resQuery && filteredRes.length === 0 && (
              <div style={{ fontSize: 11, color: ink2, padding: '4px 0' }}>
                Nenhum recurso encontrado — preenche o título manualmente abaixo.
              </div>
            )}
          </div>
        ) : (
          <div className="library-modal-field">
            <label className="library-modal-label" style={{ color: ink2 }}>Recurso vinculado</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8,
              padding: '8px 10px', background: dark ? '#2A2520' : '#F5F0E8',
              border: `1px solid ${border}`, borderRadius: 4 }}>
              <span style={{ flex: 1, fontSize: 13, color: ink }}>{title}</span>
              <button onClick={clearResource} style={{
                background: 'none', border: 'none', cursor: 'pointer',
                fontSize: 12, color: ink2, padding: '0 4px',
              }}>✕</button>
            </div>
          </div>
        )}

        {/* Título manual (quando não há recurso vinculado) */}
        {!resourceId && (
          <div className="library-modal-field">
            <label className="library-modal-label" style={{ color: ink2 }}>
              {resources.length > 0 ? 'Ou escreve o título *' : 'O que estás a ler *'}
            </label>
            <input className="library-modal-input" value={title} onChange={e => setTitle(e.target.value)}
              placeholder="Título da obra"
              style={{ background: dark ? '#2A2520' : undefined, color: ink, borderColor: border }} />
          </div>
        )}

        <div className="library-modal-field">
          <label className="library-modal-label" style={{ color: ink2 }}>Status</label>
          <select className="library-modal-input library-modal-input--select" value={status}
            onChange={e => setStatus(e.target.value)}
            style={{ background: dark ? '#2A2520' : undefined, color: ink, borderColor: border }}>
            {Object.entries(READING_STATUS).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
        </div>

        {/* Toggle: método de tracking */}
        <div className="library-modal-field">
          <label className="library-modal-label" style={{ color: ink2 }}>Acompanhar progresso por</label>
          <div style={{ display: 'flex', gap: 8 }}>
            {(['pages', 'percent'] as const).map(t => (
              <button key={t} onClick={() => setProgressType(t)} style={{
                flex: 1, padding: '6px 10px', borderRadius: 4, cursor: 'pointer', fontSize: 12,
                border: `1px solid ${progressType === t ? 'var(--accent)' : border}`,
                background: progressType === t ? 'var(--accent)18' : 'transparent',
                color: progressType === t ? 'var(--accent)' : ink2,
              }}>
                {t === 'pages' ? '📖 Páginas' : '% Porcentagem'}
              </button>
            ))}
          </div>
        </div>

        {progressType === 'pages' ? (
          <div className="library-modal-row">
            <div className="library-modal-field">
              <label className="library-modal-label" style={{ color: ink2 }}>Página atual</label>
              <input type="number" className="library-modal-input" value={curPage}
                onChange={e => setCurPage(e.target.value)} placeholder="0"
                style={{ background: dark ? '#2A2520' : undefined, color: ink, borderColor: border }} />
            </div>
            <div className="library-modal-field">
              <label className="library-modal-label" style={{ color: ink2 }}>Total de páginas</label>
              <input type="number" className="library-modal-input" value={totPages}
                onChange={e => setTotPages(e.target.value)} placeholder="–"
                style={{ background: dark ? '#2A2520' : undefined, color: ink, borderColor: border }} />
            </div>
          </div>
        ) : (
          <div className="library-modal-field">
            <label className="library-modal-label" style={{ color: ink2 }}>Progresso atual (%)</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <input type="number" min={0} max={100} className="library-modal-input"
                value={initPercent} onChange={e => setInitPercent(e.target.value)} placeholder="0"
                style={{ background: dark ? '#2A2520' : undefined, color: ink, borderColor: border, width: 80 }} />
              <div style={{ flex: 1, height: 6, background: border, borderRadius: 3, overflow: 'hidden' }}>
                <div style={{
                  height: '100%', borderRadius: 3, background: 'var(--accent)',
                  width: `${Math.min(100, Math.max(0, parseInt(initPercent) || 0))}%`,
                  transition: 'width 200ms',
                }} />
              </div>
              <span style={{ fontSize: 11, color: ink2, flexShrink: 0 }}>
                {Math.min(100, Math.max(0, parseInt(initPercent) || 0))}%
              </span>
            </div>
          </div>
        )}

        <div className="library-modal-row">
          <div className="library-modal-field">
            <label className="library-modal-label" style={{ color: ink2 }}>Início</label>
            <input type="date" className="library-modal-input" value={dateStart}
              onChange={e => setDateStart(e.target.value)}
              style={{ background: dark ? '#2A2520' : undefined, color: ink, borderColor: border }} />
          </div>
          <div className="library-modal-field">
            <label className="library-modal-label" style={{ color: ink2 }}>Fim</label>
            <input type="date" className="library-modal-input" value={dateEnd}
              onChange={e => setDateEnd(e.target.value)}
              style={{ background: dark ? '#2A2520' : undefined, color: ink, borderColor: border }} />
          </div>
        </div>

        <div className="library-modal-field">
          <label className="library-modal-label" style={{ color: ink2 }}>Avaliação (1–5)</label>
          <input type="number" min={1} max={5} className="library-modal-input" value={rating}
            onChange={e => setRating(e.target.value)} placeholder="–"
            style={{ background: dark ? '#2A2520' : undefined, color: ink, borderColor: border }} />
        </div>

        <div className="library-modal-field">
          <label className="library-modal-label" style={{ color: ink2 }}>Notas</label>
          <textarea className="library-modal-input" value={review}
            onChange={e => setReview(e.target.value)} rows={3}
            placeholder="Impressões, aprendizados, citações…"
            style={{ background: dark ? '#2A2520' : undefined, color: ink,
              borderColor: border, resize: 'vertical', fontFamily: 'inherit' }} />
        </div>

        <div className="library-modal-actions">
          <button className="btn btn-ghost btn-sm" onClick={onClose} style={{ color: ink2 }}>
            Cancelar
          </button>
          <button className="btn btn-sm" onClick={handleSave}
            style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}
            disabled={!title.trim()}>
            {initial ? 'Guardar' : 'Registar'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Modal de recurso ──────────────────────────────────────────────────────────

function ResourceModal({ initial, dark, onSave, onClose }: {
  initial?: Resource | null; dark: boolean;
  onSave: (data: any) => void; onClose: () => void
}) {
  const initMeta = useMemo(() => {
    try { return initial?.metadata_json ? JSON.parse(initial.metadata_json) : {} } catch { return {} }
  }, [initial])

  const [title,       setTitle]       = useState(initial?.title         ?? '')
  const [type,        setType]        = useState(initial?.resource_type ?? 'link')
  const [url,         setUrl]         = useState(initial?.url           ?? '')
  const [desc,        setDesc]        = useState(initial?.description   ?? '')
  const [meta,        setMeta]        = useState<Record<string, string>>(initMeta)
  const [searchQuery, setSearchQuery] = useState('')
  const [searching,   setSearching]   = useState(false)
  const [results,     setResults]     = useState<any[]>([])
  const [searchErr,   setSearchErr]   = useState('')
  // para tipos sem pesquisa (link/video/etc) manter o fetch simples
  const [fetching,    setFetching]    = useState(false)
  const [fetchErr,    setFetchErr]    = useState('')

  const ink     = dark ? '#E8DFC8' : '#2C2416'
  const ink2    = dark ? '#8A7A62' : '#9C8E7A'
  const border  = dark ? '#3A3020' : '#C4B9A8'
  const inputBg = dark ? '#2A2520' : undefined
  const dropBg  = dark ? '#2A2520' : '#F5F0E8'

  const fields = META_FIELDS[type] ?? []
  const hasSearch = type === 'livro' || type === 'artigo'

  const setMetaField = (key: string, val: string) =>
    setMeta(prev => ({ ...prev, [key]: val }))

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    setSearching(true); setSearchErr(''); setResults([])
    const res = await fromIpc<any[]>(
      () => (window as any).db.resources.searchMeta(type, searchQuery.trim()),
      'searchMeta',
    )
    setSearching(false)
    res.match(
      data => { if (data?.length > 0) setResults(data); else setSearchErr('Nenhum resultado encontrado') },
      _e   => setSearchErr('Erro na pesquisa'),
    )
  }

  const applyResult = (r: any) => {
    setTitle(r.title || r.name || '')
    const newMeta: Record<string, string> = {}
    // Todos os campos conhecidos do resultado — nenhum filtrado por field list
    const candidates: Record<string, any> = {
      author:      r.author,
      authors:     r.authors,
      publisher:   r.publisher,
      year:        r.year,
      pages:       r.pages,
      isbn:        r.isbn,
      language:    r.language,
      cover_url:   r.cover_url_m || r.cover_url,
      cover_url_m: r.cover_url_m,
      thumbnail_url: r.thumbnail_url,
      channel:     r.channel,
      journal:     r.journal,
      doi:         r.doi,
      volume:      r.volume,
      issue:       r.issue,
    }
    Object.entries(candidates).forEach(([k, v]) => {
      if (v != null && v !== '' && v !== 'null') newMeta[k] = String(v)
    })
    setMeta(newMeta)
    setResults([])
    setSearchQuery('')
  }

  // fetch para tipos sem pesquisa por lista (link, video, etc.)
  const handleFetch = async () => {
    if (!url.trim()) return
    setFetching(true); setFetchErr('')
    const res = await fromIpc<any>(
      () => (window as any).db.resources.fetchMeta(type, title.trim() || url.trim(), url.trim()),
      'fetchMeta',
    )
    setFetching(false)
    res.match(
      d => {
        if (d && Object.keys(d).length > 0) {
          if (d.title && !title.trim()) setTitle(d.title)
          if (d.description && !desc.trim()) setDesc(d.description)
          const newMeta: Record<string, string> = { ...meta }
          ;['thumbnail_url', 'thumbnail', 'channel', 'domain', 'platform'].forEach(k => {
            if (d[k] && !newMeta[k]) newMeta[k] = String(d[k])
          })
          fields.forEach(f => {
            const v = d[f.key]
            if (v != null && v !== '' && !newMeta[f.key]) newMeta[f.key] = String(v)
          })
          setMeta(newMeta)
        } else setFetchErr('Nenhum resultado encontrado')
      },
      _e => setFetchErr('Erro ao buscar metadados'),
    )
  }

  const handleSave = () => {
    if (!title.trim()) return
    const cleanMeta = Object.fromEntries(Object.entries(meta).filter(([, v]) => v !== ''))
    onSave({
      ...(initial ? { id: initial.id } : {}),
      title: title.trim(), resource_type: type,
      url:   url.trim() || null, description: desc.trim() || null,
      metadata_json: Object.keys(cleanMeta).length > 0 ? JSON.stringify(cleanMeta) : null,
    })
  }

  const coverUrl = meta['cover_url_m'] || meta['cover_url'] || meta['thumbnail_url'] || meta['thumbnail']

  return (
    <div className="library-modal-overlay" onClick={onClose}>
      <div className="library-modal" onClick={e => e.stopPropagation()}
        style={{ background: dark ? '#211D16' : undefined, borderColor: border }}>
        <h2 className="library-modal-title" style={{ color: ink }}>
          {initial ? 'Editar recurso' : 'Novo recurso'}
        </h2>

        {/* Tipo */}
        <div className="library-modal-field">
          <label className="library-modal-label" style={{ color: ink2 }}>Tipo</label>
          <select className="library-modal-input library-modal-input--select" value={type}
            onChange={e => { setType(e.target.value); setMeta({}); setResults([]) }}
            style={{ background: inputBg, color: ink, borderColor: border }}>
            {Object.keys(RESOURCE_TYPE_ICONS).map(t => (
              <option key={t} value={t}>{RESOURCE_TYPE_ICONS[t]} {t}</option>
            ))}
          </select>
        </div>

        {/* Pesquisa por resultados (livro / artigo) */}
        {hasSearch && (
          <div className="library-modal-field">
            <label className="library-modal-label" style={{ color: ink2 }}>
              {type === 'livro' ? '⚡ Pesquisar livro (Open Library)' : '⚡ Pesquisar artigo (CrossRef)'}
            </label>
            <div style={{ display: 'flex', gap: 6 }}>
              <input className="library-modal-input" value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
                placeholder={type === 'livro' ? 'Título ou ISBN…' : 'Título ou DOI…'}
                style={{ background: inputBg, color: ink, borderColor: border, flex: 1 }} />
              <button className="btn btn-sm" onClick={handleSearch}
                disabled={searching || !searchQuery.trim()}
                style={{ borderColor: border, color: ink2, fontSize: 12, flexShrink: 0 }}>
                {searching ? '…' : 'Pesquisar'}
              </button>
            </div>
            {searchErr && <div style={{ fontSize: 11, color: '#8B3A2A', marginTop: 3 }}>{searchErr}</div>}

            {/* Lista de resultados */}
            {results.length > 0 && (
              <div style={{ border: `1px solid ${border}`, borderRadius: 4, overflow: 'hidden', marginTop: 4 }}>
                {results.map((r, i) => (
                  <button key={i} onClick={() => applyResult(r)} style={{
                    display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                    padding: '7px 10px', background: 'none', border: 'none',
                    borderBottom: i < results.length - 1 ? `1px solid ${border}` : 'none',
                    cursor: 'pointer', textAlign: 'left',
                  }}
                    onMouseEnter={e => (e.currentTarget.style.background = dropBg)}
                    onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                  >
                    {r.cover_url && (
                      <img src={r.cover_url} alt="" style={{
                        width: 26, height: 36, objectFit: 'cover',
                        borderRadius: 2, border: `1px solid ${border}`, flexShrink: 0,
                      }} />
                    )}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, color: ink, fontWeight: 500,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.title}
                      </div>
                      <div style={{ fontSize: 10, color: ink2 }}>
                        {r.author || r.authors || ''}
                        {(r.year) ? ` · ${r.year}` : ''}
                        {r.journal ? ` · ${r.journal}` : ''}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Título manual */}
        <div className="library-modal-field">
          <label className="library-modal-label" style={{ color: ink2 }}>
            Título *{hasSearch && title && ' (preenchido automaticamente)'}
          </label>
          <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
            {coverUrl && (
              <img src={coverUrl} alt="capa" style={{
                width: 36, height: 50, objectFit: 'cover',
                borderRadius: 3, border: `1px solid ${border}`, flexShrink: 0, marginTop: 1,
              }} />
            )}
            <input className="library-modal-input" value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder={hasSearch ? 'Ou escreve o título manualmente…' : 'Nome do recurso'}
              autoFocus={!hasSearch}
              style={{ background: inputBg, color: ink, borderColor: border, flex: 1 }} />
          </div>
        </div>

        {/* URL + fetch automático para link/video/etc */}
        <div className="library-modal-field">
          <label className="library-modal-label" style={{ color: ink2 }}>URL</label>
          <div style={{ display: 'flex', gap: 6 }}>
            <input className="library-modal-input" value={url} onChange={e => setUrl(e.target.value)}
              placeholder="https://…"
              style={{ background: inputBg, color: ink, borderColor: border, flex: 1 }} />
            {!hasSearch && (
              <button className="btn btn-sm" onClick={handleFetch}
                disabled={fetching || !url.trim()}
                title="Buscar metadados do URL"
                style={{ borderColor: border, color: ink2, fontSize: 12, flexShrink: 0 }}>
                {fetching ? '…' : '⚡'}
              </button>
            )}
          </div>
          {fetchErr && <div style={{ fontSize: 11, color: '#8B3A2A', marginTop: 3 }}>{fetchErr}</div>}
        </div>

        <div className="library-modal-field">
          <label className="library-modal-label" style={{ color: ink2 }}>URL</label>
          <input className="library-modal-input" value={url} onChange={e => setUrl(e.target.value)}
            placeholder="https://…"
            style={{ background: inputBg, color: ink, borderColor: border }} />
        </div>

        {/* Campos específicos por tipo */}
        {fields.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 12px', marginBottom: 8 }}>
            {fields.map(f => (
              <div key={f.key} className="library-modal-field" style={{ marginBottom: 0 }}>
                <label className="library-modal-label" style={{ color: ink2 }}>{f.label}</label>
                <input
                  className="library-modal-input"
                  type={f.type === 'number' ? 'number' : 'text'}
                  value={meta[f.key] ?? ''}
                  onChange={e => setMetaField(f.key, e.target.value)}
                  style={{ background: inputBg, color: ink, borderColor: border, fontSize: 12 }}
                />
              </div>
            ))}
          </div>
        )}

        <div className="library-modal-field">
          <label className="library-modal-label" style={{ color: ink2 }}>Descrição / Notas</label>
          <textarea className="library-modal-input" value={desc}
            onChange={e => setDesc(e.target.value)} rows={2}
            placeholder="Para que serve, onde foi usado…"
            style={{ background: inputBg, color: ink,
              borderColor: border, resize: 'vertical', fontFamily: 'inherit' }} />
        </div>

        <div className="library-modal-actions">
          <button className="btn btn-ghost btn-sm" onClick={onClose} style={{ color: ink2 }}>
            Cancelar
          </button>
          <button className="btn btn-sm" onClick={handleSave}
            style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}
            disabled={!title.trim()}>
            {initial ? 'Guardar' : 'Adicionar'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Modal de sessão de leitura ────────────────────────────────────────────────

interface ReadingSession {
  id: number; reading_id: number; date: string
  page_start: number; page_end: number
  duration_min: number | null; notes: string | null; created_at: string
}

function SessionModal({ reading, dark, onSave, onClose }: {
  reading: Reading; dark: boolean
  onSave: (data: any) => void; onClose: () => void
}) {
  const byPercent = reading.progress_type === 'percent'
  const today     = new Date().toISOString().slice(0, 10)
  const [date,       setDate]       = useState(today)
  const [pgStart,    setPgStart]    = useState(String(reading.current_page ?? 0))
  const [pgEnd,      setPgEnd]      = useState(String(reading.current_page ?? 0))
  const [pctEnd,     setPctEnd]     = useState(String(reading.progress_percent ?? 0))
  const [duration,   setDuration]   = useState('')
  const [notes,      setNotes]      = useState('')

  const ink     = dark ? '#E8DFC8' : '#2C2416'
  const ink2    = dark ? '#8A7A62' : '#9C8E7A'
  const border  = dark ? '#3A3020' : '#C4B9A8'
  const inputBg = dark ? '#2A2520' : undefined

  const pagesRead  = Math.max(0, (parseInt(pgEnd) || 0) - (parseInt(pgStart) || 0))
  const pctEndNum  = Math.min(100, Math.max(0, parseInt(pctEnd) || 0))
  const pctGain    = Math.max(0, pctEndNum - (reading.progress_percent ?? 0))

  const canSave = byPercent ? pctEndNum > 0 : (parseInt(pgEnd) > 0)

  const handleSave = () => {
    if (!canSave) return
    onSave({
      reading_id:   reading.id,
      date,
      page_start:   byPercent ? 0 : (parseInt(pgStart) || 0),
      page_end:     byPercent ? 0 : (parseInt(pgEnd) || 0),
      percent_end:  byPercent ? pctEndNum : null,
      duration_min: duration ? parseInt(duration) : null,
      notes:        notes.trim() || null,
    })
  }

  return (
    <div className="library-modal-overlay" onClick={onClose}>
      <div className="library-modal" onClick={e => e.stopPropagation()}
        style={{ background: dark ? '#211D16' : undefined, borderColor: border, maxWidth: 380 }}>
        <h2 className="library-modal-title" style={{ color: ink, fontSize: 15 }}>
          Sessão de leitura
        </h2>
        <p style={{ fontSize: 12, color: ink2, margin: '-8px 0 12px', fontStyle: 'italic' }}>
          {reading.title}
        </p>

        <div className="library-modal-field">
          <label className="library-modal-label" style={{ color: ink2 }}>Data</label>
          <input type="date" className="library-modal-input" value={date}
            onChange={e => setDate(e.target.value)}
            style={{ background: inputBg, color: ink, borderColor: border }} />
        </div>

        {byPercent ? (
          /* ── Tracking por porcentagem ── */
          <div className="library-modal-field">
            <label className="library-modal-label" style={{ color: ink2 }}>
              Porcentagem actual *
            </label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <input type="number" min={0} max={100} className="library-modal-input" autoFocus
                value={pctEnd} onChange={e => setPctEnd(e.target.value)}
                style={{ background: inputBg, color: ink, borderColor: border, width: 72 }} />
              <div style={{ flex: 1, height: 6, background: border, borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ height: '100%', borderRadius: 3, background: 'var(--accent)',
                  width: `${pctEndNum}%`, transition: 'width 200ms' }} />
              </div>
              <span style={{ fontSize: 11, color: ink2, flexShrink: 0 }}>{pctEndNum}%</span>
            </div>
            {pctGain > 0 && (
              <div style={{ fontSize: 11, color: ink2, marginTop: 4 }}>
                +{pctGain}% nesta sessão
              </div>
            )}
          </div>
        ) : (
          /* ── Tracking por páginas ── */
          <>
            <div className="library-modal-row">
              <div className="library-modal-field">
                <label className="library-modal-label" style={{ color: ink2 }}>Página início</label>
                <input type="number" className="library-modal-input" value={pgStart}
                  onChange={e => setPgStart(e.target.value)} min={0}
                  style={{ background: inputBg, color: ink, borderColor: border }} />
              </div>
              <div className="library-modal-field">
                <label className="library-modal-label" style={{ color: ink2 }}>Página fim *</label>
                <input type="number" className="library-modal-input" value={pgEnd}
                  onChange={e => setPgEnd(e.target.value)} min={0} autoFocus
                  style={{ background: inputBg, color: ink, borderColor: border }} />
              </div>
            </div>
            {pagesRead > 0 && (
              <div style={{ fontSize: 11, color: ink2, marginTop: -4, marginBottom: 8 }}>
                {pagesRead} página{pagesRead !== 1 ? 's' : ''} lida{pagesRead !== 1 ? 's' : ''}
                {reading.total_pages
                  ? ` · ${Math.round(((parseInt(pgEnd)||0) / reading.total_pages) * 100)}% total`
                  : ''}
              </div>
            )}
          </>
        )}

        <div className="library-modal-field">
          <label className="library-modal-label" style={{ color: ink2 }}>Duração (min)</label>
          <input type="number" className="library-modal-input" value={duration}
            onChange={e => setDuration(e.target.value)} placeholder="–"
            style={{ background: inputBg, color: ink, borderColor: border }} />
        </div>

        <div className="library-modal-field">
          <label className="library-modal-label" style={{ color: ink2 }}>Notas</label>
          <textarea className="library-modal-input" value={notes} onChange={e => setNotes(e.target.value)}
            rows={2} placeholder="Impressões desta sessão…"
            style={{ background: inputBg, color: ink, borderColor: border,
              resize: 'vertical', fontFamily: 'inherit' }} />
        </div>

        <div className="library-modal-actions">
          <button className="btn btn-ghost btn-sm" onClick={onClose} style={{ color: ink2 }}>
            Cancelar
          </button>
          <button className="btn btn-sm" onClick={handleSave}
            style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}
            disabled={!canSave}>
            Registar
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Detalhe de leitura ────────────────────────────────────────────────────────

function ReadingDetailView({ reading: initialReading, dark, onBack, onEdit, onSession }: {
  reading: Reading; dark: boolean
  onBack: () => void
  onEdit: (r: Reading) => void
  onSession: (r: Reading) => void
}) {
  const [reading,  setReading]  = useState<Reading>(initialReading)
  const [tab,      setTab]      = useState<'geral' | 'notas' | 'citacoes' | 'vinculos'>('geral')

  // Sincronizar com o prop quando o pai actualiza (ex: após registar sessão)
  useEffect(() => {
    setReading(initialReading)
    fromIpc<any[]>(() => db().readingSessions.list(initialReading.id), 'syncSessions')
      .then(r => r.match(data => setSessions(data), _e => {}))
  }, [initialReading.current_page, initialReading.status, initialReading.updated_at])
  const [sessions, setSessions] = useState<ReadingSession[]>([])
  const [notes,    setNotes]    = useState<any[]>([])
  const [quotes,   setQuotes]   = useState<any[]>([])
  const [links,    setLinks]    = useState<any[]>([])

  // note/quote inputs
  const [noteChapter, setNoteChapter] = useState('')
  const [noteContent, setNoteContent] = useState('')
  const [quoteText,   setQuoteText]   = useState('')
  const [quoteLoc,    setQuoteLoc]    = useState('')
  // vinculos inputs
  const [pageSearch,  setPageSearch]  = useState('')
  const [pageResults, setPageResults] = useState<any[]>([])
  const [projects,    setProjects]    = useState<any[]>([])
  const [wsId,        setWsId]        = useState<number | null>(null)
  const [showCreate,  setShowCreate]  = useState(false)
  const [newPageProj, setNewPageProj] = useState<number | ''>('')
  const [newPageTitle,setNewPageTitle]= useState('')
  const [creating,    setCreating]    = useState(false)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const inputBg = dark ? '#2A2520' : '#FAF6EE'

  const reload = () => {
    fromIpc<Reading[]>(() => db().readings.list(), 'reloadReadings')
      .then(r => r.match(data => {
        const updated = data.find((x: Reading) => x.id === reading.id)
        if (updated) setReading(updated)
      }, _e => {}))
  }

  useEffect(() => {
    fromIpc<any[]>(() => db().readingSessions.list(reading.id), 'listReadingSessions')
      .then(r => r.match(data => setSessions(data), _e => {}))
  }, [reading.id])

  useEffect(() => {
    if (tab === 'notas')    fromIpc<any[]>(() => db().readingNotes.list(reading.id), 'listReadingNotes')
      .then(r => r.match(data => setNotes(data), _e => {}))
    if (tab === 'citacoes') fromIpc<any[]>(() => db().readingQuotes.list(reading.id), 'listReadingQuotes')
      .then(r => r.match(data => setQuotes(data), _e => {}))
  }, [tab, reading.id])

  const st       = READING_STATUS[reading.status] ?? READING_STATUS.want
  const progress = calcProgress(reading)

  const addNote = async () => {
    if (!noteContent.trim()) return
    await fromIpc<unknown>(() => db().readingNotes.create({ reading_id: reading.id, chapter: noteChapter, content: noteContent.trim() }), 'createReadingNote')
    setNoteContent(''); setNoteChapter('')
    fromIpc<any[]>(() => db().readingNotes.list(reading.id), 'listReadingNotes')
      .then(noteResult => noteResult.match(data => setNotes(data), _e => {}))
  }
  const deleteNote = async (id: number) => {
    await fromIpc<unknown>(() => db().readingNotes.delete(id), 'deleteReadingNote')
    setNotes(prev => prev.filter(n => n.id !== id))
  }

  const addQuote = async () => {
    if (!quoteText.trim()) return
    await fromIpc<unknown>(() => db().readingQuotes.create({ reading_id: reading.id, text: quoteText.trim(), location: quoteLoc }), 'createReadingQuote')
    setQuoteText(''); setQuoteLoc('')
    fromIpc<any[]>(() => db().readingQuotes.list(reading.id), 'listReadingQuotes')
      .then(noteResult => noteResult.match(data => setQuotes(data), _e => {}))
  }
  const deleteQuote = async (id: number) => {
    await fromIpc<unknown>(() => db().readingQuotes.delete(id), 'deleteReadingQuote')
    setQuotes(prev => prev.filter(q => q.id !== id))
  }

  const deleteSession = async (id: number) => {
    await fromIpc<unknown>(() => db().readingSessions.delete(id), 'deleteReadingSession')
    setSessions(prev => prev.filter(s => s.id !== id))
    reload()
  }

  const loadLinks = () =>
    fromIpc<any[]>(() => db().readingLinks.list(reading.id), 'listReadingLinks')
      .then(r => r.match(data => setLinks(data), _e => {}))

  useEffect(() => {
    if (tab !== 'vinculos') return
    loadLinks()
    fromIpc<any[]>(() => db().projects.list(), 'listProjects')
      .then(r => r.match(data => {
        setProjects(data)
        if (data?.[0]?.workspace_id) setWsId(data[0].workspace_id)
      }, _e => {}))
    fromIpc<any>(() => db().workspace.get(), 'getWorkspace').then(r => r.match(data => setWsId(data.id), _e => {}))
  }, [tab])

  useEffect(() => {
    const t = setTimeout(async () => {
      if (!pageSearch.trim()) { setPageResults([]); return }
      const res = await fromIpc<any[]>(() => db().pages.search(pageSearch, 10), 'searchPages')
      res.match(data => setPageResults(data), _e => {})
    }, 300)
    return () => clearTimeout(t)
  }, [pageSearch])

  const addLink = async (page_id: number) => {
    await fromIpc<unknown>(() => db().readingLinks.add(reading.id, page_id), 'addReadingLink')
    loadLinks()
    setPageSearch(''); setPageResults([])
  }

  const handleCreateProject = async (name: string) => {
    if (!wsId) return
    const res = await fromIpc<any>(() => db().projects.create({ workspace_id: wsId, name, project_type: 'custom' }), 'createProject')
    if (res.isOk() && res.value?.id) {
      setProjects(prev => [...prev, res.value])
      setNewPageProj(res.value.id)
      setShowCreate(true)
      setPageSearch(''); setPageResults([])
    }
  }

  const handleCreatePage = async () => {
    if (!newPageTitle.trim() || !newPageProj) return
    setCreating(true)
    try {
      const res = await fromIpc<any>(() => db().pages.create({ project_id: newPageProj, title: newPageTitle.trim() }), 'createPage')
      if (res.isOk() && res.value?.id) {
        await fromIpc<unknown>(() => db().readingLinks.add(reading.id, res.value.id), 'addReadingLink')
        loadLinks()
        setShowCreate(false); setNewPageTitle(''); setNewPageProj('')
      }
    } finally { setCreating(false) }
  }

  const TABS = [
    { key: 'geral',     label: 'Geral' },
    { key: 'notas',     label: `Notas${notes.length ? ` (${notes.length})` : ''}` },
    { key: 'citacoes',  label: `Citações${quotes.length ? ` (${quotes.length})` : ''}` },
    { key: 'vinculos',  label: `Vínculos${links.length ? ` (${links.length})` : ''}` },
  ] as const

  return (
    <div className="library-root">
      {/* Header */}
      <div className="library-toolbar" style={{ borderColor: border, gap: 8 }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack}
          style={{ color: ink2, fontSize: 12 }}>
          ← Voltar
        </button>
        <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic',
          fontSize: 15, color: ink, flex: 1, overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {reading.title}
        </span>
        <button className="btn btn-ghost btn-sm" onClick={() => onSession(reading)}
          style={{ color: ink2, fontSize: 11 }}>📖 Sessão</button>
        <button className="btn btn-ghost btn-sm" onClick={() => onEdit(reading)}
          style={{ color: ink2, fontSize: 11 }}>✎ Editar</button>
      </div>

      {/* Abas */}
      <div style={{ display: 'flex', gap: 2, padding: '0 20px',
        borderBottom: `1px solid ${border}`, background: dark ? '#1A1710' : '#F5F0E8' }}>
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key as any)}
            style={{
              padding: '8px 14px', background: 'none', border: 'none',
              cursor: 'pointer', fontSize: 12,
              color: tab === t.key ? accent : ink2,
              borderBottom: tab === t.key ? `2px solid ${accent}` : '2px solid transparent',
              fontFamily: 'var(--font-body)',
            }}>
            {t.label}
          </button>
        ))}
      </div>

      <div className="library-scroll" style={{ padding: '20px 28px' }}>

        {/* ── Aba Geral ── */}
        {tab === 'geral' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Status + progresso */}
            <div style={{ background: cardBg, border: `1px solid ${border}`,
              borderLeft: `4px solid ${st.color}`, borderRadius: 6, padding: '14px 16px' }}>
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: progress !== null ? 10 : 0 }}>
                <span style={{ fontSize: 12, color: st.color, fontWeight: 600 }}>{st.label}</span>
                {reading.date_start && (
                  <span style={{ fontSize: 11, color: ink2 }}>
                    Início: {reading.date_start}
                    {reading.date_end ? ` · Fim: ${reading.date_end}` : ''}
                  </span>
                )}
                {reading.rating ? (
                  <span style={{ fontSize: 11, color: accent }}>{stars(reading.rating)}</span>
                ) : null}
              </div>
              {progress !== null && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontSize: 11, color: ink2 }}>
                      {reading.progress_type === 'percent'
                        ? `${reading.progress_percent ?? 0}% concluído`
                        : `${reading.current_page} / ${reading.total_pages} págs`}
                    </span>
                    <span style={{ fontSize: 11, color: ink2 }}>{progress}%</span>
                  </div>
                  <div style={{ height: 4, background: border, borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${progress}%`,
                      background: st.color, borderRadius: 2, transition: 'width 300ms' }} />
                  </div>
                </div>
              )}
            </div>

            {reading.review && (
              <div style={{ background: cardBg, border: `1px solid ${border}`,
                borderRadius: 6, padding: '12px 16px' }}>
                <div style={{ fontSize: 11, color: ink2, marginBottom: 4 }}>Notas gerais</div>
                <p style={{ fontSize: 13, color: ink, lineHeight: 1.6, margin: 0,
                  fontStyle: 'italic' }}>{reading.review}</p>
              </div>
            )}

            {/* Histórico de sessões */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between',
                alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontSize: 12, color: ink2, fontWeight: 600,
                  textTransform: 'uppercase', letterSpacing: 1 }}>
                  Sessões ({sessions.length})
                </span>
                <button className="btn btn-ghost btn-sm"
                  onClick={() => onSession(reading)}
                  style={{ fontSize: 11, color: accent }}>
                  + Sessão
                </button>
              </div>
              {sessions.length === 0 ? (
                <div style={{ fontSize: 12, color: ink2, fontStyle: 'italic' }}>
                  Nenhuma sessão registada.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {sessions.map(s => {
                    const pages = s.page_end - s.page_start
                    return (
                      <div key={s.id} style={{ background: cardBg, border: `1px solid ${border}`,
                        borderRadius: 4, padding: '8px 12px',
                        display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ fontSize: 11, color: ink2, minWidth: 80 }}>{s.date}</span>
                        <span style={{ fontSize: 12, color: ink, flex: 1 }}>
                          págs {s.page_start}–{s.page_end}
                          <span style={{ color: ink2 }}> ({pages} pág{pages !== 1 ? 's' : ''})</span>
                          {s.duration_min ? <span style={{ color: ink2 }}> · {s.duration_min} min</span> : ''}
                        </span>
                        {s.notes && (
                          <span style={{ fontSize: 11, color: ink2, fontStyle: 'italic',
                            maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {s.notes}
                          </span>
                        )}
                        <button className="btn btn-ghost btn-sm"
                          style={{ fontSize: 10, color: '#8B3A2A', padding: '1px 5px' }}
                          onClick={() => deleteSession(s.id)}>✕</button>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Aba Notas ── */}
        {tab === 'notas' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6,
              background: cardBg, border: `1px solid ${border}`, borderRadius: 6, padding: 12 }}>
              <input className="library-modal-input" placeholder="Capítulo / secção (opcional)"
                value={noteChapter} onChange={e => setNoteChapter(e.target.value)}
                style={{ background: inputBg, color: ink, borderColor: border, fontSize: 12 }} />
              <textarea className="library-modal-input" placeholder="Nota…"
                value={noteContent} onChange={e => setNoteContent(e.target.value)}
                rows={3} style={{ background: inputBg, color: ink, borderColor: border,
                  resize: 'vertical', fontFamily: 'inherit', fontSize: 13 }} />
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button className="btn btn-sm" onClick={addNote}
                  disabled={!noteContent.trim()}
                  style={{ borderColor: accent, color: accent, fontSize: 12 }}>
                  + Adicionar nota
                </button>
              </div>
            </div>
            {notes.length === 0 ? (
              <div style={{ fontSize: 12, color: ink2, fontStyle: 'italic' }}>Nenhuma nota ainda.</div>
            ) : notes.map(n => (
              <div key={n.id} style={{ background: cardBg, border: `1px solid ${border}`,
                borderRadius: 6, padding: '10px 14px' }}>
                {n.chapter && (
                  <div style={{ fontSize: 10, color: accent, fontWeight: 600,
                    textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 4 }}>
                    {n.chapter}
                  </div>
                )}
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <p style={{ fontSize: 13, color: ink, lineHeight: 1.6, margin: 0, flex: 1 }}>{n.content}</p>
                  <button className="btn btn-ghost btn-sm"
                    style={{ fontSize: 10, color: '#8B3A2A', padding: '1px 5px', flexShrink: 0 }}
                    onClick={() => deleteNote(n.id)}>✕</button>
                </div>
                <div style={{ fontSize: 10, color: ink2, marginTop: 6 }}>
                  {n.created_at?.slice(0, 10)}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── Aba Citações ── */}
        {tab === 'citacoes' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6,
              background: cardBg, border: `1px solid ${border}`, borderRadius: 6, padding: 12 }}>
              <textarea className="library-modal-input" placeholder="«Citação…»"
                value={quoteText} onChange={e => setQuoteText(e.target.value)}
                rows={3} style={{ background: inputBg, color: ink, borderColor: border,
                  resize: 'vertical', fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 14 }} />
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input className="library-modal-input" placeholder="Localização (pág, cap…)"
                  value={quoteLoc} onChange={e => setQuoteLoc(e.target.value)}
                  style={{ background: inputBg, color: ink, borderColor: border, fontSize: 12, flex: 1 }} />
                <button className="btn btn-sm" onClick={addQuote}
                  disabled={!quoteText.trim()}
                  style={{ borderColor: accent, color: accent, fontSize: 12, flexShrink: 0 }}>
                  + Guardar
                </button>
              </div>
            </div>
            {quotes.length === 0 ? (
              <div style={{ fontSize: 12, color: ink2, fontStyle: 'italic' }}>Nenhuma citação ainda.</div>
            ) : quotes.map(q => (
              <div key={q.id} style={{ background: cardBg, border: `1px solid ${border}`,
                borderRadius: 6, padding: '12px 16px', borderLeft: `3px solid ${accent}` }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <p style={{ fontSize: 14, color: ink, fontFamily: 'var(--font-display)',
                    fontStyle: 'italic', lineHeight: 1.7, margin: 0, flex: 1 }}>
                    «{q.text}»
                  </p>
                  <button className="btn btn-ghost btn-sm"
                    style={{ fontSize: 10, color: '#8B3A2A', padding: '1px 5px', flexShrink: 0 }}
                    onClick={() => deleteQuote(q.id)}>✕</button>
                </div>
                {q.location && (
                  <div style={{ fontSize: 11, color: ink2, marginTop: 6 }}>— {q.location}</div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* ── Aba Vínculos ── */}
        {tab === 'vinculos' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {/* Pesquisa de páginas existentes */}
            <div style={{ background: cardBg, border: `1px solid ${border}`, borderRadius: 6, padding: 12 }}>
              <div style={{ fontSize: 11, color: ink2, marginBottom: 6 }}>
                Vincular a uma página de projeto
              </div>
              <div style={{ position: 'relative' }}>
                <input className="library-modal-input"
                  placeholder="Pesquisar página…"
                  value={pageSearch} onChange={e => setPageSearch(e.target.value)}
                  style={{ background: inputBg, color: ink, borderColor: border, width: '100%' }} />
                {(pageResults.length > 0 || (pageSearch.trim() && pageResults.length === 0)) && (
                  <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 10,
                    border: `1px solid ${border}`, borderTop: 'none', borderRadius: '0 0 4px 4px',
                    background: dark ? '#2A2520' : '#F5F0E8', maxHeight: 200, overflowY: 'auto' }}>
                    {pageResults.map((p: any) => (
                      <button key={p.id} onClick={() => addLink(p.id)} style={{
                        display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
                        width: '100%', padding: '7px 10px',
                        background: 'none', border: 'none',
                        borderBottom: `1px solid ${border}`,
                        cursor: 'pointer', textAlign: 'left',
                      }}
                        onMouseEnter={e => (e.currentTarget.style.background = dark ? '#3A3020' : '#EDE7D9')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                      >
                        <div style={{ fontSize: 12, color: ink }}>{p.title}</div>
                        {p.project_name && <div style={{ fontSize: 10, color: ink2 }}>{p.project_name}</div>}
                      </button>
                    ))}
                    {pageSearch.trim() && pageResults.length === 0 && (
                      <button onClick={() => handleCreateProject(pageSearch.trim())} style={{
                        display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
                        width: '100%', padding: '7px 10px',
                        background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
                      }}
                        onMouseEnter={e => (e.currentTarget.style.background = dark ? '#3A3020' : '#EDE7D9')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                      >
                        <div style={{ fontSize: 12, color: accent }}>＋ Criar projeto "{pageSearch}"</div>
                        <div style={{ fontSize: 10, color: ink2 }}>Nenhuma página encontrada</div>
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Criar nova página */}
            <div style={{ background: cardBg, border: `1px solid ${border}`, borderRadius: 6, padding: 12 }}>
              <button className="btn btn-ghost btn-sm"
                style={{ fontSize: 11, color: accent, marginBottom: showCreate ? 10 : 0 }}
                onClick={() => setShowCreate(v => !v)}>
                {showCreate ? '✕ Cancelar' : '＋ Criar nova página de projeto'}
              </button>
              {showCreate && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <select className="library-modal-input"
                    value={newPageProj}
                    onChange={e => setNewPageProj(Number(e.target.value))}
                    style={{ background: inputBg, color: ink, borderColor: border }}>
                    <option value="">Selecionar projeto…</option>
                    {projects.map((p: any) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                  <input className="library-modal-input"
                    placeholder="Título da nova página…"
                    value={newPageTitle}
                    onChange={e => setNewPageTitle(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleCreatePage()}
                    style={{ background: inputBg, color: ink, borderColor: border }} />
                  <button className="btn btn-sm"
                    onClick={handleCreatePage}
                    disabled={creating || !newPageTitle.trim() || !newPageProj}
                    style={{ background: accent, color: '#fff', border: 'none',
                      borderRadius: 4, padding: '5px 14px', cursor: 'pointer',
                      alignSelf: 'flex-start', fontSize: 12 }}>
                    {creating ? 'A criar…' : 'Criar e vincular'}
                  </button>
                </div>
              )}
            </div>

            {/* Lista de vínculos */}
            {links.length === 0 ? (
              <div style={{ fontSize: 12, color: ink2, fontStyle: 'italic' }}>
                Nenhuma página vinculada ainda.
              </div>
            ) : links.map((l: any) => (
              <div key={l.page_id} style={{ background: cardBg, border: `1px solid ${border}`,
                borderRadius: 6, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, color: ink }}>{l.title}</div>
                  <div style={{ fontSize: 10, color: ink2 }}>{l.project_name}</div>
                </div>
                <button className="btn btn-ghost btn-sm"
                  style={{ fontSize: 10, color: '#8B3A2A', padding: '1px 5px' }}
                  onClick={async () => {
                    await fromIpc<unknown>(() => db().readingLinks.remove(reading.id, l.page_id), 'removeReadingLink')
                    setLinks(prev => prev.filter(x => x.page_id !== l.page_id))
                  }}>✕</button>
              </div>
            ))}
          </div>
        )}

      </div>
    </div>
  )
}

// ── ReadingsView ──────────────────────────────────────────────────────────────

// ── Meta de Leitura Anual ─────────────────────────────────────────────────────

function ReadingGoalBanner({ dark }: { dark: boolean }) {
  const year = new Date().getFullYear()
  const [wsId,    setWsId]    = useState<number | null>(null)
  const [target,  setTarget]  = useState<number | null>(null)
  const [done,    setDone]    = useState(0)
  const [editing, setEditing] = useState(false)
  const [input,   setInput]   = useState('')

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  useEffect(() => {
    fromIpc<any>(() => db().workspace.get(), 'getWs').then(r =>
      r.match(ws => setWsId(ws.id), _e => {})
    )
  }, [])

  useEffect(() => {
    if (!wsId) return
    fromIpc<any>(() => db().readingGoals.progress(wsId, year), 'readingGoalProgress')
      .then(r => r.match(data => {
        setTarget(data.target)
        setDone(data.done)
      }, _e => {}))
  }, [wsId, year])

  const save = async () => {
    if (!wsId) return
    const val = parseInt(input)
    if (!val || val < 1) return
    await fromIpc<any>(() => db().readingGoals.set(wsId, year, val), 'setReadingGoal')
    setTarget(val)
    setEditing(false)
  }

  const pct = target && target > 0 ? Math.min(100, Math.round((done / target) * 100)) : 0

  if (!editing && target === null) {
    return (
      <div style={{
        borderBottom: `1px solid ${border}`, padding: '10px 28px',
        background: cardBg, display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2 }}>
          META DE LEITURA {year}
        </span>
        <button className="btn btn-sm" style={{ borderColor: accent, color: accent, fontSize: 10 }}
          onClick={() => { setInput('12'); setEditing(true) }}>
          + Definir meta
        </button>
      </div>
    )
  }

  return (
    <div style={{
      borderBottom: `1px solid ${border}`, padding: '10px 28px',
      background: cardBg, display: 'flex', alignItems: 'center', gap: 16,
      flexWrap: 'wrap',
    }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.12em', color: ink2 }}>
        META {year}
      </span>

      {editing ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            type="number" min="1" max="500"
            className="settings-input"
            style={{ width: 64, fontSize: 11, padding: '2px 6px' }}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEditing(false) }}
            autoFocus
          />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2 }}>livros</span>
          <button className="btn btn-sm" style={{ borderColor: accent, color: accent, fontSize: 10 }}
            onClick={save}>Guardar</button>
          <button className="btn btn-ghost btn-sm" style={{ color: ink2, fontSize: 10 }}
            onClick={() => setEditing(false)}>Cancelar</button>
        </div>
      ) : (
        <>
          <div style={{ flex: 1, minWidth: 160, maxWidth: 300 }}>
            <div style={{
              height: 6, borderRadius: 3,
              background: dark ? '#2A2418' : '#D8D0C0',
              overflow: 'hidden',
            }}>
              <div style={{
                height: '100%', borderRadius: 3,
                width: `${pct}%`,
                background: pct >= 100 ? '#4A6741' : accent,
                transition: 'width 0.4s ease',
              }} />
            </div>
          </div>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: ink }}>
            <span style={{ color: pct >= 100 ? '#4A6741' : accent, fontWeight: 600 }}>{done}</span>
            <span style={{ color: ink2 }}> / {target}</span>
          </span>
          {pct >= 100 && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#4A6741' }}>
              ✓ Meta atingida!
            </span>
          )}
          <button className="btn btn-ghost btn-sm" style={{ color: ink2, fontSize: 10, marginLeft: 'auto' }}
            onClick={() => { setInput(String(target ?? 12)); setEditing(true) }}>
            ✎
          </button>
        </>
      )}
    </div>
  )
}

function ReadingsView({ dark }: { dark: boolean }) {
  const [readings,    setReadings]    = useState<Reading[]>([])
  const [filter,        setFilter]        = useState<string>('reading')
  const [query,         setQuery]         = useState('')
  const [showModal,     setShowModal]     = useState(false)
  const [editReading,   setEditReading]   = useState<Reading | null>(null)
  const [sessionFor,    setSessionFor]    = useState<Reading | null>(null)
  const [detailReading, setDetailReading] = useState<Reading | null>(null)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  const load = () => {
    fromIpc<Reading[]>(() => db().readings.list(), 'listReadings')
      .then(r => r.match(data => setReadings(data), _e => {}))
  }

  useEffect(() => { load() }, [])

  const filtered = useMemo(() => {
    let r = filter === 'all' ? readings : readings.filter(x => x.status === filter)
    if (query.trim()) {
      const q = query.toLowerCase()
      r = r.filter(x => x.title.toLowerCase().includes(q))
    }
    return r
  }, [readings, filter, query])

  const handleSave = async (data: any) => {
    if (data.id) await fromIpc<unknown>(() => db().readings.update(data), 'updateReading')
    else          await fromIpc<unknown>(() => db().readings.create(data), 'createReading')
    load()
    setShowModal(false)
    setEditReading(null)
  }

  const handleDelete = async (id: number) => {
    await fromIpc<unknown>(() => db().readings.delete(id), 'deleteReading')
    load()
  }

  const handleSessionSave = async (data: any) => {
    await fromIpc<unknown>(() => db().readingSessions.create(data), 'createReadingSession')
    setSessionFor(null)
    const result = await fromIpc<Reading[]>(() => db().readings.list(), 'reloadReadingsAfterSession')
    result.match(data => {
      setReadings(data)
      if (detailReading) {
        const updated = data.find(r => r.id === detailReading.id)
        if (updated) setDetailReading(updated)
      }
    }, _e => {})
  }

  // Mostrar detalhe de leitura se seleccionado
  if (detailReading) {
    return (
      <ReadingDetailView
        reading={detailReading}
        dark={dark}
        onBack={() => { setDetailReading(null); load() }}
        onEdit={(r) => { setDetailReading(null); setEditReading(r); setShowModal(true) }}
        onSession={(r) => setSessionFor(r)}
      />
    )
  }

  const daysReading = (r: Reading): number | null => {
    if (!r.date_start) return null
    const start = new Date(r.date_start)
    const end   = r.date_end ? new Date(r.date_end) : new Date()
    return Math.max(0, Math.floor((end.getTime() - start.getTime()) / 86400000))
  }

  const STATUS_FILTERS = [
    { key: 'reading', label: 'A ler'     },
    { key: 'want',    label: 'Quero ler' },
    { key: 'done',    label: 'Lidas'     },
    { key: 'paused',  label: 'Pausadas'  },
    { key: 'all',     label: 'Todas'     },
  ]

  return (
    <div className="library-root">
      <ReadingGoalBanner dark={dark} />
      <div className="library-toolbar" style={{ borderColor: dark ? '#3A3020' : undefined }}>
        {STATUS_FILTERS.map(f => (
          <button key={f.key}
            className={`library-filter-btn${filter === f.key ? ' library-filter-btn--active' : ''}`}
            onClick={() => setFilter(f.key)}
            style={filter === f.key ? { borderColor: accent, color: accent } : {}}>
            {f.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <input className="library-search" placeholder="⌕ Pesquisar…"
          value={query} onChange={e => setQuery(e.target.value)}
          style={{ background: dark ? '#211D16' : undefined,
            borderColor: dark ? '#3A3020' : undefined, color: ink }} />
        <button className="btn btn-sm" onClick={() => { setEditReading(null); setShowModal(true) }}
          style={{ borderColor: accent, color: accent }}>
          + Registar leitura
        </button>
      </div>

      <div className="library-scroll">
        {filtered.length === 0 ? (
          <div className="library-empty">
            <span style={{ fontSize: 36, opacity: 0.4 }}>📖</span>
            <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic',
              fontSize: 16, color: ink }}>
              {query || filter !== 'all' ? 'Nenhuma leitura encontrada' : 'Nenhuma leitura ainda'}
            </span>
            {!query && filter === 'reading' && (
              <button className="btn btn-sm" onClick={() => setShowModal(true)}
                style={{ borderColor: accent, color: accent, marginTop: 8 }}>
                + Registar primeira leitura
              </button>
            )}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '20px 28px' }}>
            {filtered.map(r => {
              const st       = READING_STATUS[r.status] ?? READING_STATUS.want
              const progress = calcProgress(r)
              const days     = daysReading(r)

              return (
                <div key={r.id} style={{
                  background: cardBg, borderRadius: 6, border: `1px solid ${border}`,
                  borderLeft: `4px solid ${st.color}`,
                  padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 8,
                }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                    <div style={{ flex: 1 }}>
                      <button onClick={() => setDetailReading(r)} style={{
                        background: 'none', border: 'none', cursor: 'pointer', padding: 0,
                        textAlign: 'left', fontFamily: 'var(--font-display)', fontSize: 15,
                        fontStyle: 'italic', color: ink, marginBottom: 2,
                        textDecoration: 'underline', textDecorationColor: 'transparent',
                      }}
                        onMouseEnter={e => (e.currentTarget.style.textDecorationColor = ink2)}
                        onMouseLeave={e => (e.currentTarget.style.textDecorationColor = 'transparent')}
                      >
                        {r.title}
                      </button>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ fontSize: 11, color: st.color, fontWeight: 600 }}>
                          {st.label}
                        </span>
                        {days !== null && (
                          <span style={{ fontSize: 10, color: ink2 }}>
                            {days} dia{days !== 1 ? 's' : ''}
                          </span>
                        )}
                        {r.rating ? (
                          <span style={{ fontSize: 10, color: accent }}>{stars(r.rating)}</span>
                        ) : null}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                      <button className="btn btn-ghost btn-sm" title="Registar sessão"
                        style={{ fontSize: 10, padding: '2px 6px', color: ink2 }}
                        onClick={() => setSessionFor(r)}>
                        📖
                      </button>
                      <button className="btn btn-ghost btn-sm" style={{
                        fontSize: 10, padding: '2px 6px', color: ink2,
                      }} onClick={() => { setEditReading(r); setShowModal(true) }}>
                        ✎
                      </button>
                      <button className="btn btn-ghost btn-sm" style={{
                        fontSize: 10, padding: '2px 6px', color: '#8B3A2A',
                      }} onClick={() => handleDelete(r.id)}>
                        ✕
                      </button>
                    </div>
                  </div>

                  {progress !== null && (
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                        <span style={{ fontSize: 10, color: ink2 }}>
                          {r.progress_type === 'percent'
                            ? `${r.progress_percent ?? 0}%`
                            : `${r.current_page} / ${r.total_pages} págs`}
                        </span>
                        <span style={{ fontSize: 10, color: ink2 }}>{progress}%</span>
                      </div>
                      <div style={{ height: 3, background: border, borderRadius: 2, overflow: 'hidden' }}>
                        <div style={{
                          height: '100%', width: `${progress}%`,
                          background: st.color, transition: 'width 300ms', borderRadius: 2,
                        }} />
                      </div>
                    </div>
                  )}

                  {r.review && (
                    <p style={{ fontSize: 11, color: ink2, fontStyle: 'italic',
                      lineHeight: 1.5, margin: 0,
                      overflow: 'hidden', display: '-webkit-box',
                      WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                      {r.review}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {showModal && (
        <ReadingModal
          initial={editReading}
          dark={dark}
          onSave={handleSave}
          onClose={() => { setShowModal(false); setEditReading(null) }}
        />
      )}

      {sessionFor && (
        <SessionModal
          reading={sessionFor}
          dark={dark}
          onSave={handleSessionSave}
          onClose={() => setSessionFor(null)}
        />
      )}
    </div>
  )
}

// ── ResourceDetailView ────────────────────────────────────────────────────────

function ResourceDetailView({ resource: initial, dark, onBack, onEdit }: {
  resource: Resource; dark: boolean
  onBack: () => void; onEdit: (r: Resource) => void
}) {
  const [tab,         setTab]         = useState<'detalhes' | 'vinculos'>('detalhes')
  const [links,       setLinks]       = useState<any[]>([])
  const [pageSearch,  setPageSearch]  = useState('')
  const [pageResults, setPageResults] = useState<any[]>([])
  // Criar nova página / projeto
  const [projects,    setProjects]    = useState<any[]>([])
  const [wsId,        setWsId]        = useState<number | null>(null)
  const [showCreate,  setShowCreate]  = useState(false)
  const [newPageProj, setNewPageProj] = useState<number | ''>('')
  const [newPageTitle,setNewPageTitle]= useState('')
  const [creating,    setCreating]    = useState(false)

  const meta = useMemo(() => {
    try { return initial.metadata_json ? JSON.parse(initial.metadata_json) : {} } catch { return {} }
  }, [initial])

  const fields = META_FIELDS[initial.resource_type ?? ''] ?? []
  const cover  = meta.cover_url_m || meta.cover_url || meta.thumbnail_url

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const inputBg = dark ? '#2A2520' : '#FAF6EE'
  const dropBg  = dark ? '#2A2520' : '#F5F0E8'

  const loadLinks = () =>
    fromIpc<any[]>(() => db().resourcePages.listForResource(initial.id), 'listResourcePages')
      .then(r => r.match(data => setLinks(data), _e => {}))

  useEffect(() => { loadLinks() }, [initial.id])

  useEffect(() => {
    if (tab === 'vinculos') {
      loadLinks()
      fromIpc<any[]>(() => db().projects.list(), 'listProjects')
        .then(r => r.match(data => {
          setProjects(data)
          if (data?.[0]?.workspace_id) setWsId(data[0].workspace_id)
        }, _e => {}))
      fromIpc<any>(() => db().workspace.get(), 'getWorkspace').then(r => r.match(data => setWsId(data.id), _e => {}))
    }
  }, [tab])

  const handleCreateProject = async (name: string) => {
    if (!wsId) return
    const res = await fromIpc<any>(() => db().projects.create({ workspace_id: wsId, name, project_type: 'custom' }), 'createProject')
    if (res.isOk() && res.value?.id) {
      setProjects(prev => [...prev, res.value])
      setNewPageProj(res.value.id)
      setShowCreate(true)
      setPageSearch(''); setPageResults([])
    }
  }

  const handleCreatePage = async () => {
    if (!newPageTitle.trim() || !newPageProj) return
    setCreating(true)
    try {
      const res = await fromIpc<any>(() => db().pages.create({ project_id: newPageProj, title: newPageTitle.trim() }), 'createPage')
      if (res.isOk() && res.value?.id) {
        await fromIpc<unknown>(() => db().resourcePages.add(initial.id, res.value.id), 'addResourcePage')
        loadLinks()
        setShowCreate(false); setNewPageTitle(''); setNewPageProj('')
      }
    } finally { setCreating(false) }
  }

  // Pesquisar páginas para vincular
  const searchPages = async (q: string) => {
    if (!q.trim()) { setPageResults([]); return }
    const res = await fromIpc<any[]>(() => db().pages.search(q, 10), 'searchPages')
    res.match(data => setPageResults(data), _e => {})
  }

  useEffect(() => {
    const t = setTimeout(() => searchPages(pageSearch), 300)
    return () => clearTimeout(t)
  }, [pageSearch])

  const addLink = async (page_id: number) => {
    await fromIpc<unknown>(() => db().resourcePages.add(initial.id, page_id), 'addResourcePage')
    loadLinks()
    setPageSearch(''); setPageResults([])
  }
  const removeLink = async (page_id: number) => {
    await fromIpc<unknown>(() => db().resourcePages.remove(initial.id, page_id), 'removeResourcePage')
    setLinks(prev => prev.filter(l => l.page_id !== page_id))
  }

  const TABS = [
    { key: 'detalhes', label: 'Detalhes' },
    { key: 'vinculos', label: `Vínculos${links.length ? ` (${links.length})` : ''}` },
  ] as const

  return (
    <div className="library-root">
      <div className="library-toolbar" style={{ borderColor: border, gap: 8 }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack} style={{ color: ink2, fontSize: 12 }}>
          ← Voltar
        </button>
        <span style={{ flex: 1, fontFamily: 'var(--font-display)', fontStyle: 'italic',
          fontSize: 15, color: ink, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {initial.title}
        </span>
        <button className="btn btn-ghost btn-sm" onClick={() => onEdit(initial)}
          style={{ color: ink2, fontSize: 11 }}>✎ Editar</button>
      </div>

      <div style={{ display: 'flex', gap: 2, padding: '0 20px',
        borderBottom: `1px solid ${border}`, background: dark ? '#1A1710' : '#F5F0E8' }}>
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key as any)} style={{
            padding: '8px 14px', background: 'none', border: 'none', cursor: 'pointer', fontSize: 12,
            color: tab === t.key ? accent : ink2,
            borderBottom: tab === t.key ? `2px solid ${accent}` : '2px solid transparent',
            fontFamily: 'var(--font-body)',
          }}>{t.label}</button>
        ))}
      </div>

      <div className="library-scroll" style={{ padding: '20px 28px' }}>

        {tab === 'detalhes' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Header: capa + tipo + URL */}
            <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
              {cover ? (
                <img src={cover} alt="capa" style={{
                  width: 80, height: 112, objectFit: 'cover',
                  borderRadius: 4, border: `1px solid ${border}`, flexShrink: 0,
                }} />
              ) : (
                <div style={{ width: 80, height: 112, display: 'flex', alignItems: 'center',
                  justifyContent: 'center', fontSize: 36, background: cardBg,
                  border: `1px solid ${border}`, borderRadius: 4, flexShrink: 0 }}>
                  {RESOURCE_TYPE_ICONS[initial.resource_type ?? ''] ?? '◦'}
                </div>
              )}
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 18, fontFamily: 'var(--font-display)',
                  fontStyle: 'italic', color: ink, marginBottom: 4 }}>
                  {initial.title}
                </div>
                {initial.resource_type && (
                  <span style={{ fontSize: 11, color: ink2, border: `1px solid ${border}`,
                    borderRadius: 3, padding: '1px 6px' }}>
                    {RESOURCE_TYPE_ICONS[initial.resource_type] ?? ''} {initial.resource_type}
                  </span>
                )}
                {initial.url && (
                  <div style={{ fontSize: 11, color: accent, marginTop: 6,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {initial.url}
                  </div>
                )}
              </div>
            </div>

            {/* Campos de metadados */}
            {fields.length > 0 && (
              <div style={{ background: cardBg, border: `1px solid ${border}`,
                borderRadius: 6, padding: '12px 16px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 20px' }}>
                  {fields.map(f => {
                    const v = meta[f.key]
                    if (!v) return null
                    return (
                      <div key={f.key}>
                        <div style={{ fontSize: 10, color: ink2, textTransform: 'uppercase',
                          letterSpacing: 0.8, marginBottom: 2 }}>{f.label}</div>
                        <div style={{ fontSize: 13, color: ink }}>{v}</div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Descrição */}
            {initial.description && (
              <div style={{ background: cardBg, border: `1px solid ${border}`,
                borderRadius: 6, padding: '12px 16px' }}>
                <div style={{ fontSize: 10, color: ink2, textTransform: 'uppercase',
                  letterSpacing: 0.8, marginBottom: 6 }}>Descrição</div>
                <p style={{ fontSize: 13, color: ink, lineHeight: 1.6, margin: 0 }}>
                  {initial.description}
                </p>
              </div>
            )}
          </div>
        )}

        {tab === 'vinculos' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {/* Pesquisa de páginas */}
            <div style={{ background: cardBg, border: `1px solid ${border}`,
              borderRadius: 6, padding: 12 }}>
              <div style={{ fontSize: 11, color: ink2, marginBottom: 6 }}>
                Vincular a uma página de projeto
              </div>
              <div style={{ position: 'relative' }}>
                <input className="library-modal-input"
                  placeholder="Pesquisar página…"
                  value={pageSearch} onChange={e => setPageSearch(e.target.value)}
                  style={{ background: inputBg, color: ink, borderColor: border, width: '100%' }} />
                {(pageResults.length > 0 || (pageSearch.trim() && pageResults.length === 0)) && (
                  <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 10,
                    border: `1px solid ${border}`, borderTop: 'none', borderRadius: '0 0 4px 4px',
                    background: dropBg, maxHeight: 200, overflowY: 'auto' }}>
                    {pageResults.map((p: any) => (
                      <button key={p.id} onClick={() => addLink(p.id)} style={{
                        display: 'flex', alignItems: 'center', gap: 8,
                        width: '100%', padding: '7px 10px',
                        background: 'none', border: 'none',
                        borderBottom: `1px solid ${border}`,
                        cursor: 'pointer', textAlign: 'left',
                      }}
                        onMouseEnter={e => (e.currentTarget.style.background = dark ? '#3A3020' : '#EDE7D9')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                      >
                        <div>
                          <div style={{ fontSize: 12, color: ink }}>{p.title}</div>
                          {p.project_name && <div style={{ fontSize: 10, color: ink2 }}>{p.project_name}</div>}
                        </div>
                      </button>
                    ))}
                    {pageSearch.trim() && pageResults.length === 0 && (
                      <button onClick={() => handleCreateProject(pageSearch.trim())} style={{
                        display: 'flex', alignItems: 'center', gap: 8,
                        width: '100%', padding: '7px 10px',
                        background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
                      }}
                        onMouseEnter={e => (e.currentTarget.style.background = dark ? '#3A3020' : '#EDE7D9')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                      >
                        <div style={{ fontSize: 12, color: accent }}>
                          ＋ Criar projeto "{pageSearch}"
                        </div>
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Criar nova página */}
            <div style={{ background: cardBg, border: `1px solid ${border}`, borderRadius: 6, padding: 12 }}>
              <button className="btn btn-ghost btn-sm"
                style={{ fontSize: 11, color: accent, marginBottom: showCreate ? 10 : 0 }}
                onClick={() => setShowCreate(v => !v)}>
                {showCreate ? '✕ Cancelar' : '＋ Criar nova página de projeto'}
              </button>
              {showCreate && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <select className="library-modal-input"
                    value={newPageProj}
                    onChange={e => setNewPageProj(Number(e.target.value))}
                    style={{ background: inputBg, color: ink, borderColor: border }}>
                    <option value="">Selecionar projeto…</option>
                    {projects.map((p: any) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                  <input className="library-modal-input"
                    placeholder="Título da nova página…"
                    value={newPageTitle}
                    onChange={e => setNewPageTitle(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleCreatePage()}
                    style={{ background: inputBg, color: ink, borderColor: border }} />
                  <button className="btn btn-sm"
                    onClick={handleCreatePage}
                    disabled={creating || !newPageTitle.trim() || !newPageProj}
                    style={{ background: accent, color: '#fff', border: 'none',
                      borderRadius: 4, padding: '5px 14px', cursor: 'pointer',
                      alignSelf: 'flex-start', fontSize: 12 }}>
                    {creating ? 'A criar…' : 'Criar e vincular'}
                  </button>
                </div>
              )}
            </div>

            {/* Lista de vínculos */}
            {links.length === 0 ? (
              <div style={{ fontSize: 12, color: ink2, fontStyle: 'italic' }}>
                Nenhuma página vinculada ainda.
              </div>
            ) : links.map((l: any) => (
              <div key={l.page_id} style={{ background: cardBg, border: `1px solid ${border}`,
                borderRadius: 6, padding: '10px 14px',
                display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, color: ink }}>{l.page_title}</div>
                  <div style={{ fontSize: 10, color: ink2 }}>{l.project_name}</div>
                </div>
                <button className="btn btn-ghost btn-sm"
                  style={{ fontSize: 10, color: '#8B3A2A', padding: '1px 5px' }}
                  onClick={() => removeLink(l.page_id)}>✕</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── ResourcesView ─────────────────────────────────────────────────────────────

function ResourcesView({ dark }: { dark: boolean }) {
  const [resources,     setResources]     = useState<Resource[]>([])
  const [query,         setQuery]         = useState('')
  const [viewMode,      setViewMode]      = useState<'list' | 'grid'>('list')
  const [showModal,     setShowModal]     = useState(false)
  const [editResource,  setEditResource]  = useState<Resource | null>(null)
  const [detailResource,setDetailResource]= useState<Resource | null>(null)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  const load = () => {
    fromIpc<Resource[]>(() => db().resources.list(), 'listResources')
      .then(r => r.match(data => setResources(data), _e => {}))
  }

  useEffect(() => { load() }, [])

  const filtered = useMemo(() => {
    if (!query.trim()) return resources
    const q = query.toLowerCase()
    return resources.filter(r =>
      r.title.toLowerCase().includes(q) ||
      (r.url ?? '').toLowerCase().includes(q) ||
      (r.description ?? '').toLowerCase().includes(q)
    )
  }, [resources, query])

  const handleSave = async (data: any) => {
    if (data.id) await fromIpc<unknown>(() => db().resources.update(data), 'updateResource')
    else          await fromIpc<unknown>(() => db().resources.create(data), 'createResource')
    load(); setShowModal(false); setEditResource(null)
  }

  const handleDelete = async (id: number) => {
    await fromIpc<unknown>(() => db().resources.delete(id), 'deleteResource')
    load()
  }

  if (detailResource) {
    return (
      <ResourceDetailView
        resource={detailResource}
        dark={dark}
        onBack={() => { setDetailResource(null); load() }}
        onEdit={r => { setDetailResource(null); setEditResource(r); setShowModal(true) }}
      />
    )
  }

  return (
    <div className="library-root">
      <div className="library-toolbar" style={{ borderColor: border }}>
        <input className="library-search" placeholder="⌕ Pesquisar…"
          value={query} onChange={e => setQuery(e.target.value)}
          style={{ background: dark ? '#211D16' : undefined, borderColor: border, color: ink }} />
        <div style={{ flex: 1 }} />
        {/* Toggle lista / galeria */}
        <div style={{ display: 'flex', gap: 2, border: `1px solid ${border}`, borderRadius: 4, overflow: 'hidden' }}>
          {(['list', 'grid'] as const).map(m => (
            <button key={m} onClick={() => setViewMode(m)} style={{
              padding: '4px 8px', background: viewMode === m ? border : 'none',
              border: 'none', cursor: 'pointer', fontSize: 13, color: viewMode === m ? ink : ink2,
            }}>
              {m === 'list' ? '☰' : '⊞'}
            </button>
          ))}
        </div>
        <button className="btn btn-sm" onClick={() => { setEditResource(null); setShowModal(true) }}
          style={{ borderColor: accent, color: accent }}>
          + Recurso
        </button>
      </div>

      <div className="library-scroll">
        {filtered.length === 0 ? (
          <div className="library-empty">
            <span style={{ fontSize: 36, opacity: 0.4 }}>◇</span>
            <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 16, color: ink }}>
              {query ? 'Nenhum recurso encontrado' : 'Nenhum recurso ainda'}
            </span>
            {!query && (
              <button className="btn btn-sm" onClick={() => setShowModal(true)}
                style={{ borderColor: accent, color: accent }}>
                + Adicionar primeiro recurso
              </button>
            )}
          </div>
        ) : viewMode === 'list' ? (
          /* ── Vista lista ── */
          <div className="resources-list">
            {filtered.map(r => {
              let meta: Record<string, any> = {}
              try { if (r.metadata_json) meta = JSON.parse(r.metadata_json) } catch {}
              const cover = meta.cover_url_m || meta.cover_url || meta.thumbnail_url
              return (
                <button key={r.id} className="resource-item"
                  onClick={() => setDetailResource(r)}
                  style={{ borderColor: border, boxShadow: `2px 2px 0 ${border}`,
                    background: dark ? '#211D16' : undefined }}>
                  {cover ? (
                    <img src={cover} alt="" style={{
                      width: 32, height: 44, objectFit: 'cover',
                      borderRadius: 2, border: `1px solid ${border}`, flexShrink: 0,
                    }} />
                  ) : (
                    <span className="resource-item-icon">
                      {RESOURCE_TYPE_ICONS[r.resource_type ?? ''] ?? '◦'}
                    </span>
                  )}
                  <div className="resource-item-body">
                    <div className="resource-item-title" style={{ color: ink }}>{r.title}</div>
                    {(meta.author || meta.authors || meta.channel || meta.host) && (
                      <div style={{ fontSize: 11, color: ink2, marginTop: 1 }}>
                        {meta.author || meta.authors || meta.channel || meta.host}
                        {(meta.year || meta.journal) ? <span style={{ opacity: 0.7 }}>
                          {' · '}{meta.journal ?? ''}{meta.year ? ` ${meta.year}` : ''}
                        </span> : null}
                      </div>
                    )}
                    {r.url && <div className="resource-item-url" style={{ color: accent }}>{r.url}</div>}
                    {r.description && <div className="resource-item-desc" style={{ color: ink2 }}>{r.description}</div>}
                    <ReadingProgress r={r} dark={dark} />
                  </div>
                  {r.resource_type && (
                    <span className="resource-item-type" style={{ borderColor: border, color: ink2 }}>
                      {r.resource_type}
                    </span>
                  )}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginLeft: 4 }}>
                    <button className="btn btn-ghost btn-sm" style={{ fontSize: 10, padding: '2px 6px', color: ink2 }}
                      onClick={e => { e.stopPropagation(); setEditResource(r); setShowModal(true) }}>✎</button>
                    <button className="btn btn-ghost btn-sm" style={{ fontSize: 10, padding: '2px 6px', color: '#8B3A2A' }}
                      onClick={e => { e.stopPropagation(); handleDelete(r.id) }}>✕</button>
                  </div>
                </button>
              )
            })}
          </div>
        ) : (
          /* ── Vista galeria ── */
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
            gap: 20, padding: '20px 28px', alignItems: 'start' }}>
            {filtered.map(r => {
              let meta: Record<string, any> = {}
              try { if (r.metadata_json) meta = JSON.parse(r.metadata_json) } catch {}
              const cover = meta.cover_url_m || meta.cover_url || meta.thumbnail_url
              return (
                <div key={r.id} style={{ display: 'flex', flexDirection: 'column',
                  background: cardBg, border: `1px solid ${border}`, borderRadius: 6,
                  overflow: 'hidden', cursor: 'pointer', transition: 'box-shadow 150ms' }}
                  onClick={() => setDetailResource(r)}
                  onMouseEnter={e => (e.currentTarget.style.boxShadow = `0 6px 16px rgba(0,0,0,0.15)`)}
                  onMouseLeave={e => (e.currentTarget.style.boxShadow = 'none')}
                >
                  {/* Capa — proporção 2:3 (capa de livro) */}
                  <div style={{ aspectRatio: '2/3', display: 'flex', alignItems: 'center',
                    justifyContent: 'center', background: dark ? '#2A2520' : '#E8E0D0',
                    overflow: 'hidden', flexShrink: 0, width: '100%' }}>
                    {cover ? (
                      <img src={cover} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
                    ) : (
                      <span style={{ fontSize: 48, opacity: 0.4 }}>
                        {RESOURCE_TYPE_ICONS[r.resource_type ?? ''] ?? '◦'}
                      </span>
                    )}
                  </div>
                  {/* Info */}
                  <div style={{ padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <div style={{ fontSize: 12, color: ink, fontWeight: 500, lineHeight: 1.3,
                      overflow: 'hidden', display: '-webkit-box',
                      WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                      {r.title}
                    </div>
                    {(meta.author || meta.authors) && (
                      <div style={{ fontSize: 10, color: ink2,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {meta.author || meta.authors}
                      </div>
                    )}
                    {meta.year && <div style={{ fontSize: 10, color: ink2 }}>{meta.year}</div>}
                    <ReadingProgress r={r} dark={dark} compact />
                    {r.resource_type && (
                      <div style={{ paddingTop: 3 }}>
                        <span style={{ fontSize: 9, color: ink2, border: `1px solid ${border}`,
                          borderRadius: 3, padding: '1px 4px' }}>
                          {r.resource_type}
                        </span>
                      </div>
                    )}
                  </div>
                  {/* Acções */}
                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 2,
                    padding: '4px 6px', borderTop: `1px solid ${border}` }}>
                    <button className="btn btn-ghost btn-sm" style={{ fontSize: 10, padding: '2px 5px', color: ink2 }}
                      onClick={e => { e.stopPropagation(); setEditResource(r); setShowModal(true) }}>✎</button>
                    <button className="btn btn-ghost btn-sm" style={{ fontSize: 10, padding: '2px 5px', color: '#8B3A2A' }}
                      onClick={e => { e.stopPropagation(); handleDelete(r.id) }}>✕</button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {showModal && (
        <ResourceModal
          initial={editResource}
          dark={dark}
          onSave={handleSave}
          onClose={() => { setShowModal(false); setEditResource(null) }}
        />
      )}
    </div>
  )
}

// ── Export principal ──────────────────────────────────────────────────────────

// ── Library Dashboard ─────────────────────────────────────────────────────────

function LibraryDashboard({ dark, onNavigate }: {
  dark: boolean
  onNavigate: (sub: SubSection) => void
}) {
  const [readings,  setReadings]  = useState<Reading[]>([])
  const [resources, setResources] = useState<Resource[]>([])

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const accent = dark ? '#D4A820' : '#b8860b'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  useEffect(() => {
    fromIpc<Reading[]>(() => db().readings.list(), 'listReadings')
      .then(r => r.match(data => setReadings(data), _e => {}))
    fromIpc<Resource[]>(() => db().resources.list(), 'listResources')
      .then(r => r.match(data => setResources(data), _e => {}))
  }, [])

  // Estatísticas de leituras
  const readingStats = {
    total:   readings.length,
    reading: readings.filter(r => r.status === 'reading').length,
    done:    readings.filter(r => r.status === 'done').length,
    want:    readings.filter(r => r.status === 'want').length,
  }

  // Lendo agora
  const currentlyReading = readings.filter(r => r.status === 'reading').slice(0, 4)

  // Adicionadas recentemente (excluindo as que estão a ler)
  const recentReadings = readings
    .filter(r => r.status !== 'reading')
    .slice(0, 4)

  // Recursos recentes
  const recentResources = resources.slice(0, 5)

  const StatCard = ({ value, label, sub, col }: { value: number | string; label: string; sub?: string; col?: string }) => (
    <div style={{
      background: cardBg, border: `1px solid ${border}`,
      borderRadius: 2, boxShadow: `2px 2px 0 ${border}`,
      padding: '14px 16px', flex: 1, minWidth: 100,
    }}>
      <div style={{ fontFamily: 'var(--font-display)', fontSize: 32,
        fontStyle: 'italic', color: col ?? ink, lineHeight: 1, marginBottom: 4 }}>
        {value}
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9,
        letterSpacing: '0.1em', color: ink }}>{label}</div>
      {sub && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: ink2, marginTop: 1 }}>{sub}</div>}
    </div>
  )

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '28px 32px 48px' }}>

      {/* Título */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 26, fontStyle: 'italic',
          fontWeight: 'normal', color: ink, margin: '0 0 4px' }}>
          Biblioteca
        </h1>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10,
          letterSpacing: '0.14em', color: ink2 }}>
          LEITURAS · RECURSOS
        </div>
      </div>

      {/* Estatísticas */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 28, flexWrap: 'wrap' }}>
        <StatCard value={readingStats.total}   label="Leituras"       sub="no total" />
        <StatCard value={readingStats.reading} label="A ler"          sub="agora"         col={accent} />
        <StatCard value={readingStats.done}    label="Lidas"          sub="concluídas"    col={dark ? '#6A9060' : '#4A6741'} />
        <StatCard value={readingStats.want}    label="Quero ler"      sub="na lista" />
        <StatCard value={resources.length}     label="Recursos"       sub="guardados" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, maxWidth: 1000 }}>

        {/* Lendo agora */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9,
              letterSpacing: '0.16em', color: ink2 }}>
              📖 A LER AGORA
            </div>
            <button onClick={() => onNavigate('readings')} style={{
              fontFamily: 'var(--font-mono)', fontSize: 9, color: accent,
              background: 'none', border: 'none', cursor: 'pointer', letterSpacing: '0.06em',
            }}>
              ver todas →
            </button>
          </div>

          {currentlyReading.length === 0 ? (
            <div style={{ background: cardBg, border: `1px solid ${border}`, borderRadius: 2,
              padding: '20px 16px', textAlign: 'center' }}>
              <div style={{ fontSize: 24, opacity: 0.3, marginBottom: 8 }}>📖</div>
              <div style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic',
                fontSize: 13, color: ink2 }}>Nenhuma leitura em curso</div>
              <button onClick={() => onNavigate('readings')} style={{
                marginTop: 10, fontFamily: 'var(--font-mono)', fontSize: 10,
                color: accent, background: 'none', border: `1px solid ${accent}`,
                borderRadius: 1, padding: '4px 10px', cursor: 'pointer',
              }}>
                + Registar leitura
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {currentlyReading.map(r => {
                const progress = calcProgress(r)
                return (
                  <button key={r.id} onClick={() => onNavigate('readings')} style={{
                    display: 'flex', gap: 10, alignItems: 'center',
                    background: cardBg, border: `1px solid ${border}`,
                    borderLeft: `3px solid ${accent}`,
                    borderRadius: 2, boxShadow: `2px 2px 0 ${border}`,
                    padding: '10px 12px', cursor: 'pointer', textAlign: 'left',
                    transition: 'transform 80ms',
                  }}
                    onMouseEnter={e => (e.currentTarget.style.transform = 'translateY(-1px)')}
                    onMouseLeave={e => (e.currentTarget.style.transform = 'none')}
                  >
                    <div style={{ flex: 1, overflow: 'hidden' }}>
                      <div style={{ fontFamily: 'var(--font-display)', fontSize: 13,
                        fontStyle: 'italic', color: ink, marginBottom: 2,
                        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {r.title}
                      </div>
                      {progress !== null && (
                        <div style={{ marginTop: 5 }}>
                          <div style={{ height: 2, background: border, borderRadius: 1 }}>
                            <div style={{ height: '100%', width: `${progress}%`,
                              background: accent, borderRadius: 1 }} />
                          </div>
                          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9,
                            color: ink2, marginTop: 2 }}>
                            {r.progress_type === 'percent'
                              ? `${r.progress_percent ?? 0}% concluído`
                              : `${r.current_page}/${r.total_pages} págs · ${progress}%`}
                          </div>
                        </div>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Recursos recentes */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9,
              letterSpacing: '0.16em', color: ink2 }}>
              ◇ RECURSOS RECENTES
            </div>
            <button onClick={() => onNavigate('resources')} style={{
              fontFamily: 'var(--font-mono)', fontSize: 9, color: accent,
              background: 'none', border: 'none', cursor: 'pointer', letterSpacing: '0.06em',
            }}>
              ver todos →
            </button>
          </div>

          {recentResources.length === 0 ? (
            <div style={{ background: cardBg, border: `1px solid ${border}`, borderRadius: 2,
              padding: '20px 16px', textAlign: 'center' }}>
              <div style={{ fontSize: 24, opacity: 0.3, marginBottom: 8 }}>◇</div>
              <div style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic',
                fontSize: 13, color: ink2 }}>Nenhum recurso guardado</div>
              <button onClick={() => onNavigate('resources')} style={{
                marginTop: 10, fontFamily: 'var(--font-mono)', fontSize: 10,
                color: accent, background: 'none', border: `1px solid ${accent}`,
                borderRadius: 1, padding: '4px 10px', cursor: 'pointer',
              }}>
                + Adicionar recurso
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {recentResources.map(r => (
                <button key={r.id} onClick={() => onNavigate('resources')} style={{
                  display: 'flex', gap: 10, alignItems: 'center',
                  background: cardBg, border: `1px solid ${border}`,
                  borderRadius: 2, boxShadow: `2px 2px 0 ${border}`,
                  padding: '8px 12px', cursor: 'pointer', textAlign: 'left',
                  transition: 'transform 80ms',
                }}
                  onMouseEnter={e => (e.currentTarget.style.transform = 'translateY(-1px)')}
                  onMouseLeave={e => (e.currentTarget.style.transform = 'none')}
                >
                  <span style={{ fontSize: 16, flexShrink: 0 }}>
                    {RESOURCE_TYPE_ICONS[r.resource_type ?? ''] ?? '◦'}
                  </span>
                  <div style={{ flex: 1, overflow: 'hidden' }}>
                    <div style={{ fontFamily: 'var(--font-display)', fontSize: 13,
                      fontStyle: 'italic', color: ink,
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {r.title}
                    </div>
                    {r.url && (
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10,
                        color: accent, letterSpacing: '0.04em',
                        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {r.url}
                      </div>
                    )}
                  </div>
                  {r.resource_type && (
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9,
                      color: ink2, border: `1px solid ${border}`, borderRadius: 1,
                      padding: '1px 5px', flexShrink: 0, letterSpacing: '0.06em' }}>
                      {r.resource_type}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Leituras recentes (não em curso) */}
        {recentReadings.length > 0 && (
          <div style={{ gridColumn: '1 / -1' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9,
              letterSpacing: '0.16em', color: ink2, marginBottom: 10 }}>
              ✶ ADICIONADAS RECENTEMENTE
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
              {recentReadings.map(r => {
                const st = READING_STATUS[r.status] ?? READING_STATUS.want
                return (
                  <button key={r.id} onClick={() => onNavigate('readings')} style={{
                    background: cardBg, border: `1px solid ${border}`,
                    borderRadius: 2, boxShadow: `2px 2px 0 ${border}`,
                    cursor: 'pointer', textAlign: 'left', overflow: 'hidden',
                    transition: 'transform 80ms',
                  }}
                    onMouseEnter={e => (e.currentTarget.style.transform = 'translateY(-2px)')}
                    onMouseLeave={e => (e.currentTarget.style.transform = 'none')}
                  >
                    <div style={{ height: 6, background: st.color }} />
                    <div style={{ padding: '8px 10px' }}>
                      <div style={{ fontFamily: 'var(--font-display)', fontSize: 12,
                        fontStyle: 'italic', color: ink, marginBottom: 3,
                        display: '-webkit-box', WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                        {r.title}
                      </div>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9,
                        color: st.color, border: `1px solid ${st.color}`,
                        borderRadius: 1, padding: '1px 5px', letterSpacing: '0.06em' }}>
                        {st.label}
                      </span>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Export principal ──────────────────────────────────────────────────────────

export function LibraryView({ dark, activeSub, onNavigateSub }: {
  dark: boolean
  activeSub?: SubSection
  onNavigateSub?: (sub: SubSection) => void
}) {
  if (activeSub === 'readings')  return <ReadingsView  dark={dark} />
  if (activeSub === 'resources') return <ResourcesView dark={dark} />
  return <LibraryDashboard dark={dark} onNavigate={onNavigateSub ?? (() => {})} />
}
