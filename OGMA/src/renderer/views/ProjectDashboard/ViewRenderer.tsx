import React, { useEffect, useState, useMemo } from 'react'
import { Page, Project, ProjectView, ProjectProperty, PropOption, PagePropValue } from '../../types'
import { KanbanView } from '../KanbanView/KanbanView'
import { CalendarView } from '../CalendarView/CalendarView'
import { TimelineView } from '../TimelineView/TimelineView'
import { CosmosLayer } from '../../components/Cosmos/CosmosLayer'
import { AcademicProgressView } from '../AcademicProgress/AcademicProgressView'
import { useAppStore } from '../../store/useAppStore'
import { fromIpc } from '../../types/errors'

const db = () => (window as any).db

export interface ViewRendererProps {
  view:       ProjectView
  project:    Project
  pages:      Page[]
  properties: ProjectProperty[]
  dark:       boolean
  onPageOpen: (page: Page) => void
  onNewPage:  () => void
}

export const ViewRenderer: React.FC<ViewRendererProps> = (props) => {
  switch (props.view.view_type) {
    case 'kanban':   return <KanbanView   {...props} />
    case 'table':    return <TableView    {...props} />
    case 'list':     return <ListView     {...props} />
    case 'calendar': return <CalendarView {...props} />
    case 'timeline': return <TimelineView {...props} />
    case 'gallery':  return <GalleryView          {...props} />
    case 'progress': return <AcademicProgressView {...props} />
    default:         return <ListView             {...props} />
  }
}

// ── TableView ─────────────────────────────────────────────────────────────────

const TableView: React.FC<ViewRendererProps> = ({
  project, pages, properties, dark, onPageOpen, onNewPage,
}) => {
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const color  = project.color ?? '#8B7355'

  const [editCell,    setEditCell]    = useState<{ pageId: number; propId: number } | null>(null)
  const [propOptions, setPropOptions] = useState<Record<number, PropOption[]>>({})
  const [sortCol,     setSortCol]     = useState<number | 'title' | null>(null)
  const [sortDir,     setSortDir]     = useState<'asc' | 'desc'>('asc')
  const [filterText,  setFilterText]  = useState('')
  const [filterProps, setFilterProps] = useState<Record<number, string>>({})

  // Buscar opções de propriedades select/multi_select
  useEffect(() => {
    const selects = properties.filter(p =>
      p.prop_type === 'select' || p.prop_type === 'multi_select'
    )
    if (!selects.length) return
    ;(async () => {
      const map: Record<number, PropOption[]> = {}
      await Promise.all(selects.map(async p => {
        const r = await fromIpc<PropOption[]>(() => db().properties.getOptions(p.id), 'tableGetOptions')
        map[p.id] = r.isOk() ? r.value : []
      }))
      setPropOptions(map)
    })()
  }, [properties])

  // Ordenação
  const toggleSort = (col: number | 'title') => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(col); setSortDir('asc') }
  }

  const sortedPages = useMemo(() => {
    if (!sortCol) return pages
    return [...pages].sort((a, b) => {
      let va: string | number = ''
      let vb: string | number = ''
      if (sortCol === 'title') {
        va = a.title.toLowerCase()
        vb = b.title.toLowerCase()
      } else {
        const pva  = a.prop_values?.find(v => v.property_id === sortCol)
        const pvb  = b.prop_values?.find(v => v.property_id === sortCol)
        const prop = properties.find(p => p.id === sortCol)
        if (prop?.prop_type === 'number') {
          va = pva?.value_num ?? -Infinity
          vb = pvb?.value_num ?? -Infinity
        } else if (prop?.prop_type === 'date') {
          va = pva?.value_date ?? ''
          vb = pvb?.value_date ?? ''
        } else {
          va = (pva?.value_text ?? '').toLowerCase()
          vb = (pvb?.value_text ?? '').toLowerCase()
        }
      }
      const cmp = typeof va === 'number' && typeof vb === 'number'
        ? va - vb
        : String(va).localeCompare(String(vb), 'pt-BR')
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [pages, sortCol, sortDir, properties])

  const { loadPages, pushToast } = useAppStore()

  const setPropValue = async (pageId: number, propId: number, field: string, value: any, keepOpen = false) => {
    if (!keepOpen) setEditCell(null)
    const result = await fromIpc<unknown>(
      () => db().pages.setPropValue({ page_id: pageId, property_id: propId, [field]: value }),
      'tableSetPropValue',
    )
    if (result.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao editar célula', detail: result.error.message })
      return
    }
    loadPages(project.id)
  }

  const visibleProps = properties.slice(0, 6)

  const activeFilterCount = (filterText ? 1 : 0) +
    Object.values(filterProps).filter(Boolean).length

  const filteredPages = useMemo(() => {
    let result = sortedPages
    if (filterText) {
      const q = filterText.toLowerCase()
      result = result.filter(p => p.title.toLowerCase().includes(q))
    }
    Object.entries(filterProps).forEach(([idStr, val]) => {
      if (!val) return
      const propId = Number(idStr)
      result = result.filter(p => {
        const pv = p.prop_values?.find(v => v.property_id === propId)
        return pv?.value_text === val
      })
    })
    return result
  }, [sortedPages, filterText, filterProps])

  const thBase: React.CSSProperties = {
    textAlign:     'left',
    fontFamily:    'var(--font-mono)',
    fontSize:      9,
    letterSpacing: '0.15em',
    fontWeight:    'normal',
    textTransform: 'uppercase',
    cursor:        'pointer',
    userSelect:    'none',
    whiteSpace:    'nowrap',
  }

  const sortArrow = (col: number | 'title') =>
    sortCol === col ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''

  const selectFilters = visibleProps.filter(p => p.prop_type === 'select')

  return (
    <div style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>

      {/* Toolbar de filtros */}
      <div style={{
        display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap',
        padding: '7px 12px', borderBottom: `1px solid ${border}`, flexShrink: 0,
      }}>
        {/* Busca */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 4,
          background: dark ? '#211D16' : '#EDE7D9',
          border: `1px solid ${filterText ? color : border}`,
          borderRadius: 2, padding: '3px 7px',
        }}>
          <span style={{ fontSize: 10, color: ink2 }}>◎</span>
          <input
            type="text"
            value={filterText}
            onChange={e => setFilterText(e.target.value)}
            placeholder="Buscar..."
            style={{
              background: 'none', border: 'none', outline: 'none',
              fontSize: 11, color: ink, fontFamily: 'var(--font-mono)', width: 140,
            }}
          />
          {filterText && (
            <button onClick={() => setFilterText('')}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: ink2, fontSize: 13, padding: 0, lineHeight: 1 }}>
              ×
            </button>
          )}
        </div>

        {/* Filtros por select */}
        {selectFilters.map(p => (
          <select
            key={p.id}
            value={filterProps[p.id] ?? ''}
            onChange={e => setFilterProps(prev => ({ ...prev, [p.id]: e.target.value }))}
            style={{
              fontSize: 10, fontFamily: 'var(--font-mono)',
              background: filterProps[p.id] ? (dark ? '#3A3020' : '#EDE7D9') : 'transparent',
              border: `1px solid ${filterProps[p.id] ? color : border}`,
              color: filterProps[p.id] ? color : ink2,
              borderRadius: 2, padding: '3px 6px', cursor: 'pointer',
            }}
          >
            <option value="">{p.name}: todos</option>
            {(propOptions[p.id] ?? []).map(o => (
              <option key={o.id} value={o.label}>{o.label}</option>
            ))}
          </select>
        ))}

        {/* Limpar filtros */}
        {activeFilterCount > 0 && (
          <button
            onClick={() => { setFilterText(''); setFilterProps({}) }}
            style={{
              fontSize: 9, fontFamily: 'var(--font-mono)', letterSpacing: '0.08em',
              color: ink2, background: 'none', border: `1px solid ${border}`,
              borderRadius: 2, padding: '3px 8px', cursor: 'pointer',
            }}
          >
            LIMPAR ({activeFilterCount})
          </button>
        )}

        <span style={{ marginLeft: 'auto', fontSize: 9, fontFamily: 'var(--font-mono)', color: ink2 }}>
          {filteredPages.length}/{pages.length}
        </span>
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${border}` }}>
            <th
              style={{ ...thBase, padding: '8px 20px', color: sortCol === 'title' ? color : ink2 }}
              onClick={() => toggleSort('title')}
              title="Ordenar por título"
            >
              Título{sortArrow('title')}
            </th>
            {visibleProps.map(p => (
              <th
                key={p.id}
                style={{ ...thBase, padding: '8px 12px', color: sortCol === p.id ? color : ink2 }}
                onClick={() => toggleSort(p.id)}
                title={`Ordenar por ${p.name}`}
              >
                {p.name}{sortArrow(p.id)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filteredPages.map(page => (
            <tr
              key={page.id}
              style={{ borderBottom: `1px solid ${border}` }}
            >
              {/* Célula de título — abre a página */}
              <td
                style={{ padding: '9px 20px', cursor: 'pointer' }}
                onClick={() => { setEditCell(null); onPageOpen(page) }}
                onMouseEnter={e => (e.currentTarget.style.background = dark ? 'rgba(232,223,200,0.04)' : 'rgba(44,36,22,0.04)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 14, flexShrink: 0 }}>{page.icon ?? '📄'}</span>
                  <span style={{
                    fontFamily: 'var(--font-display)', fontStyle: 'italic',
                    fontSize: 13, color: ink,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                    maxWidth: 280,
                  }}>
                    {page.title}
                  </span>
                </div>
              </td>

              {/* Células de propriedade — editáveis inline */}
              {visibleProps.map(p => {
                const pv        = page.prop_values?.find(v => v.property_id === p.id)
                const isEditing = editCell?.pageId === page.id && editCell?.propId === p.id
                const editable  = true

                return (
                  <td
                    key={p.id}
                    style={{
                      padding:   isEditing ? '5px 8px' : '9px 12px',
                      cursor:    editable ? 'pointer' : 'default',
                      minWidth:  100,
                      maxWidth:  220,
                    }}
                    onClick={() => {
                      if (!editable || isEditing) return
                      if (p.prop_type === 'checkbox') {
                        setPropValue(page.id, p.id, 'value_bool', pv?.value_bool ? 0 : 1)
                        return
                      }
                      setEditCell({ pageId: page.id, propId: p.id })
                    }}
                    onMouseEnter={e => {
                      if (!isEditing && editable)
                        e.currentTarget.style.background = dark ? 'rgba(232,223,200,0.04)' : 'rgba(44,36,22,0.04)'
                    }}
                    onMouseLeave={e => {
                      if (!isEditing) e.currentTarget.style.background = 'transparent'
                    }}
                  >
                    {isEditing ? (
                      <InlineCellEditor
                        prop={p} pv={pv}
                        options={propOptions[p.id] ?? []}
                        onSet={(field, value) => setPropValue(page.id, p.id, field, value, p.prop_type === 'multi_select')}
                        onClose={() => setEditCell(null)}
                        dark={dark} ink={ink} ink2={ink2} border={border}
                      />
                    ) : (
                      <PropCell
                        pv={pv} propType={p.prop_type}
                        dark={dark} ink2={ink2} border={border}
                      />
                    )}
                  </td>
                )
              })}
            </tr>
          ))}

          <tr>
            <td colSpan={visibleProps.length + 1} style={{ padding: '6px 20px' }}>
              <button className="btn btn-ghost btn-sm" onClick={onNewPage}
                style={{ color: ink2, fontSize: 11 }}>
                + Nova página
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      {filteredPages.length === 0 && (
        <div style={{
          padding: '40px', textAlign: 'center', color: ink2,
          fontStyle: 'italic', fontSize: 12,
        }}>
          {pages.length === 0 ? 'Nenhuma página neste projeto.' : 'Nenhum resultado para os filtros aplicados.'}
        </div>
      )}
    </div>
  )
}

// ── InlineCellEditor ──────────────────────────────────────────────────────────

function InlineCellEditor({ prop, pv, options, onSet, onClose, dark, ink, ink2, border }: {
  prop:    ProjectProperty
  pv:      PagePropValue | undefined
  options: PropOption[]
  onSet:   (field: string, value: any) => void
  onClose: () => void
  dark: boolean; ink: string; ink2: string; border: string
}) {
  const base: React.CSSProperties = {
    fontSize:     11,
    color:        ink,
    background:   dark ? '#211D16' : '#EDE7D9',
    border:       `1px solid ${border}`,
    borderRadius: 2,
    padding:      '2px 6px',
    outline:      'none',
  }

  if (prop.prop_type === 'select') {
    return (
      <select
        autoFocus
        value={pv?.value_text ?? ''}
        onChange={e => onSet('value_text', e.target.value || null)}
        onBlur={onClose}
        style={{ ...base, width: '100%', maxWidth: 180 }}
      >
        <option value="">—</option>
        {options.map(o => (
          <option key={o.id} value={o.label}>{o.label}</option>
        ))}
      </select>
    )
  }

  if (prop.prop_type === 'multi_select') {
    const selected: string[] = (() => {
      try { return JSON.parse(pv?.value_json ?? '[]') } catch { return [] }
    })()
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 120 }}>
        {options.map(o => {
          const active = selected.includes(o.label)
          const next   = active ? selected.filter(l => l !== o.label) : [...selected, o.label]
          return (
            <button key={o.id} onClick={() => onSet('value_json', JSON.stringify(next))}
              style={{ ...base, display: 'flex', alignItems: 'center', gap: 5,
                background: active ? (o.color ? o.color + '22' : (dark ? '#3A3020' : '#EDE7D9')) : 'transparent',
                borderColor: active ? (o.color ?? border) : border }}>
              <span style={{ width: 7, height: 7, borderRadius: 1, flexShrink: 0,
                background: o.color ?? border }} />
              <span style={{ fontSize: 10 }}>{o.label}</span>
            </button>
          )
        })}
        <button onClick={onClose}
          style={{ ...base, marginTop: 3, borderTop: `1px solid ${border}`,
            fontSize: 10, color: ink2, background: 'transparent', cursor: 'pointer' }}>
          ✓ Ok
        </button>
      </div>
    )
  }

  if (prop.prop_type === 'text' || prop.prop_type === 'url') {
    return (
      <input
        autoFocus
        type="text"
        defaultValue={pv?.value_text ?? ''}
        onBlur={e => onSet('value_text', e.target.value.trim() || null)}
        onKeyDown={e => {
          if (e.key === 'Enter')  onSet('value_text', (e.target as HTMLInputElement).value.trim() || null)
          if (e.key === 'Escape') onClose()
        }}
        style={{ ...base, width: '100%', maxWidth: 180 }}
      />
    )
  }

  if (prop.prop_type === 'number') {
    return (
      <input
        autoFocus
        type="number"
        defaultValue={pv?.value_num ?? ''}
        onBlur={e => {
          const v = parseFloat(e.target.value)
          onSet('value_num', isNaN(v) ? null : v)
        }}
        onKeyDown={e => {
          if (e.key === 'Enter') {
            const v = parseFloat((e.target as HTMLInputElement).value)
            onSet('value_num', isNaN(v) ? null : v)
          }
          if (e.key === 'Escape') onClose()
        }}
        style={{ ...base, width: 90 }}
      />
    )
  }

  if (prop.prop_type === 'date') {
    return (
      <input
        autoFocus
        type="date"
        defaultValue={pv?.value_date ?? ''}
        onChange={e => onSet('value_date', e.target.value || null)}
        onBlur={onClose}
        style={{ ...base, colorScheme: dark ? 'dark' : 'light' }}
      />
    )
  }

  return null
}

// ── ListView ──────────────────────────────────────────────────────────────────

const ListView: React.FC<ViewRendererProps> = ({
  project, pages, properties, dark, onPageOpen, onNewPage,
}) => {
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const color  = project.color ?? '#8B7355'

  const [filterText, setFilterText] = useState('')
  const [sortBy,     setSortBy]     = useState<'default' | 'title' | 'date'>('default')
  const [sortDir,    setSortDir]    = useState<'asc' | 'desc'>('asc')

  // First date property available
  const dateProp = properties.find(p => p.prop_type === 'date')

  const displayPages = useMemo(() => {
    let result = [...pages]
    if (filterText) {
      const q = filterText.toLowerCase()
      result = result.filter(p => p.title.toLowerCase().includes(q))
    }
    if (sortBy === 'title') {
      result.sort((a, b) => {
        const cmp = a.title.localeCompare(b.title, 'pt-BR')
        return sortDir === 'asc' ? cmp : -cmp
      })
    } else if (sortBy === 'date' && dateProp) {
      result.sort((a, b) => {
        const va = a.prop_values?.find(v => v.property_id === dateProp.id)?.value_date ?? ''
        const vb = b.prop_values?.find(v => v.property_id === dateProp.id)?.value_date ?? ''
        const cmp = va.localeCompare(vb)
        return sortDir === 'asc' ? cmp : -cmp
      })
    }
    return result
  }, [pages, filterText, sortBy, sortDir, dateProp])

  const toggleSort = (col: 'title' | 'date') => {
    if (sortBy === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortBy(col); setSortDir('asc') }
  }

  if (pages.length === 0) {
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        gap: 12, padding: '48px 20px', color: ink2,
      }}>
        <span style={{ fontSize: 32, opacity: 0.4 }}>✦</span>
        <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 16, color: ink }}>
          Nenhuma página ainda
        </span>
        <button className="btn btn-sm" onClick={onNewPage}
          style={{ borderColor: color, color }}>
          + Criar primeira página
        </button>
      </div>
    )
  }

  return (
    <div style={{ padding: '16px 0' }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap',
        padding: '0 0 8px', marginBottom: 2, borderBottom: `1px solid ${border}`,
      }}>
        {/* Busca */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 4,
          background: dark ? '#211D16' : '#EDE7D9',
          border: `1px solid ${filterText ? color : border}`,
          borderRadius: 2, padding: '3px 7px',
        }}>
          <span style={{ fontSize: 10, color: ink2 }}>◎</span>
          <input
            type="text"
            value={filterText}
            onChange={e => setFilterText(e.target.value)}
            placeholder="Buscar..."
            style={{
              background: 'none', border: 'none', outline: 'none',
              fontSize: 11, color: ink, fontFamily: 'var(--font-mono)', width: 140,
            }}
          />
          {filterText && (
            <button onClick={() => setFilterText('')}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: ink2, fontSize: 13, padding: 0, lineHeight: 1 }}>
              ×
            </button>
          )}
        </div>

        {/* Ordenação */}
        {(['title', ...(dateProp ? ['date'] : [])] as Array<'title' | 'date'>).map(col => (
          <button key={col} onClick={() => toggleSort(col)}
            style={{
              fontSize: 9, fontFamily: 'var(--font-mono)', letterSpacing: '0.08em',
              color: sortBy === col ? color : ink2,
              background: 'none', border: `1px solid ${sortBy === col ? color : border}`,
              borderRadius: 2, padding: '3px 7px', cursor: 'pointer',
            }}
          >
            {col === 'title' ? 'TÍTULO' : (dateProp?.name.toUpperCase() ?? 'DATA')}
            {sortBy === col ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
          </button>
        ))}

        <button className="btn btn-ghost btn-sm" onClick={onNewPage}
          style={{ color: ink2, fontSize: 10, marginLeft: 'auto' }}>
          + Nova página
        </button>
      </div>

      <div className="pages-list">
        {displayPages.length === 0 ? (
          <div style={{ padding: '24px', textAlign: 'center', color: ink2, fontStyle: 'italic', fontSize: 12 }}>
            Nenhum resultado.
          </div>
        ) : displayPages.map((p, i) => (
          <button
            key={p.id}
            className="page-row"
            style={{ borderColor: border, animationDelay: `${i * 0.04}s` }}
            onClick={() => onPageOpen(p)}
          >
            <span style={{ fontSize: 16, flexShrink: 0 }}>{p.icon ?? '📄'}</span>
            <div style={{ flex: 1, textAlign: 'left', overflow: 'hidden' }}>
              <div style={{
                fontFamily: 'var(--font-display)', fontSize: 14,
                fontStyle: 'italic', color: ink,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                {p.title}
              </div>
              {p.prop_values && p.prop_values.length > 0 && (
                <div style={{ display: 'flex', gap: 6, marginTop: 3, flexWrap: 'wrap' }}>
                  {p.prop_values.filter(pv =>
                    (pv.prop_type === 'select' && pv.value_text) ||
                    (pv.prop_type === 'date'   && pv.value_date)
                  ).slice(0, 3).map(pv => (
                    <span key={pv.id} style={{
                      fontFamily: 'var(--font-mono)', fontSize: 9,
                      letterSpacing: '0.04em', color: ink2,
                    }}>
                      {pv.prop_type === 'date' ? formatDate(pv.value_date) : pv.value_text}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <span style={{ color: ink2, fontSize: 12, flexShrink: 0 }}>›</span>
          </button>
        ))}
      </div>
    </div>
  )
}

// ── GalleryView ───────────────────────────────────────────────────────────────

const GalleryView: React.FC<ViewRendererProps> = ({
  project, pages, properties, dark, onPageOpen, onNewPage,
}) => {
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'
  const color  = project.color ?? '#8B7355'

  const previewProps = properties.filter(p =>
    ['select', 'date', 'number', 'checkbox'].includes(p.prop_type)
  ).slice(0, 3)

  if (pages.length === 0) {
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        gap: 12, padding: '48px 20px', color: ink2,
      }}>
        <span style={{ fontSize: 32, opacity: 0.4 }}>⊞</span>
        <span style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 16, color: ink }}>
          Nenhuma página ainda
        </span>
        <button className="btn btn-sm" onClick={onNewPage} style={{ borderColor: color, color }}>
          + Criar primeira página
        </button>
      </div>
    )
  }

  return (
    <div style={{ padding: '20px 28px 40px' }}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gap: 14,
      }}>
        {pages.map((page, i) => (
          <button
            key={page.id}
            onClick={() => onPageOpen(page)}
            style={{
              background: cardBg, border: `1px solid ${border}`,
              borderRadius: 3, cursor: 'pointer', textAlign: 'left',
              padding: 0, overflow: 'hidden',
              transition: 'border-color 120ms, transform 120ms',
              animationDelay: `${i * 0.03}s`,
              display: 'flex', flexDirection: 'column',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = color
              e.currentTarget.style.transform = 'translateY(-1px)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = border
              e.currentTarget.style.transform = 'translateY(0)'
            }}
          >
            {/* Cover strip */}
            <div style={{
              height:     page.cover_color ? 48 : 8,
              background: page.cover_color ?? color,
              opacity:    page.cover_color ? 1 : 0.35,
              flexShrink: 0,
            }} />

            {/* Card body */}
            <div style={{ padding: '10px 12px 12px', flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6 }}>
                <span style={{ fontSize: 18, lineHeight: 1, flexShrink: 0 }}>
                  {page.icon ?? '📄'}
                </span>
                <span style={{
                  fontFamily: 'var(--font-display)', fontStyle: 'italic',
                  fontSize: 13, color: ink, lineHeight: 1.3,
                  overflow: 'hidden', display: '-webkit-box',
                  WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                }}>
                  {page.title}
                </span>
              </div>

              {previewProps.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {previewProps.map(p => {
                    const pv  = page.prop_values?.find(v => v.property_id === p.id)
                    if (!pv) return null
                    const val = p.prop_type === 'date'     ? formatDate(pv.value_date)
                              : p.prop_type === 'checkbox' ? (pv.value_bool ? '☑' : null)
                              : p.prop_type === 'number'   ? (pv.value_num != null ? String(pv.value_num) : null)
                              : pv.value_text
                    if (!val) return null
                    return (
                      <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                        <span style={{
                          fontFamily: 'var(--font-mono)', fontSize: 8,
                          letterSpacing: '0.06em', color: ink2, textTransform: 'uppercase',
                          flexShrink: 0, minWidth: 40,
                        }}>
                          {p.name}
                        </span>
                        <span style={{
                          fontFamily: 'var(--font-mono)', fontSize: 9, color: ink,
                          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                        }}>
                          {val}
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </button>
        ))}

        {/* Add card */}
        <button
          onClick={onNewPage}
          style={{
            background: 'transparent', border: `1px dashed ${border}`,
            borderRadius: 3, cursor: 'pointer', minHeight: 100,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: ink2, fontFamily: 'var(--font-mono)', fontSize: 11,
            transition: 'border-color 120ms, color 120ms',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.borderColor = color
            e.currentTarget.style.color = color
          }}
          onMouseLeave={e => {
            e.currentTarget.style.borderColor = border
            e.currentTarget.style.color = ink2
          }}
        >
          + Nova página
        </button>
      </div>
    </div>
  )
}

// ── PlaceholderView ───────────────────────────────────────────────────────────

function PlaceholderView({ label, icon, dark }: { label: string; icon: string; dark: boolean }) {
  const ink  = dark ? '#E8DFC8' : '#2C2416'
  const ink2 = dark ? '#8A7A62' : '#9C8E7A'
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', gap: 12, padding: '60px 20px', textAlign: 'center',
      position: 'relative',
    }}>
      <CosmosLayer width={280} height={140} seed={`ph_${label}`}
        density="low" dark={dark}
        style={{ position: 'relative', top: 0, left: 0 }} />
      <span style={{ fontSize: 36, position: 'relative', zIndex: 2 }}>{icon}</span>
      <span style={{
        fontFamily: 'var(--font-display)', fontStyle: 'italic',
        fontSize: 18, color: ink, position: 'relative', zIndex: 2,
      }}>
        {label}
      </span>
      <span style={{ fontSize: 12, color: ink2, fontStyle: 'italic', position: 'relative', zIndex: 2 }}>
        Vista em desenvolvimento.
      </span>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  try {
    return new Date(iso + 'T00:00:00').toLocaleDateString('pt-BR', {
      day: '2-digit', month: 'short',
    })
  } catch { return iso }
}

function PropCell({ pv, propType, dark, ink2, border }: {
  pv: any; propType: string; dark: boolean; ink2: string; border: string;
}) {
  if (!pv) return <span style={{ color: border, fontSize: 11 }}>—</span>

  if (propType === 'date' && pv.value_date) {
    return (
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, letterSpacing: '0.03em' }}>
        {formatDate(pv.value_date)}
      </span>
    )
  }
  if (propType === 'select' && pv.value_text) {
    return (
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.06em',
        padding: '1px 6px', border: `1px solid ${border}`, borderRadius: 2,
        color: ink2,
      }}>
        {pv.value_text}
      </span>
    )
  }
  if (propType === 'multi_select' && pv.value_json) {
    try {
      const tags: string[] = JSON.parse(pv.value_json)
      if (!tags.length) return <span style={{ color: border, fontSize: 11 }}>—</span>
      return (
        <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
          {tags.slice(0, 3).map(t => (
            <span key={t} style={{
              fontFamily: 'var(--font-mono)', fontSize: 9, padding: '1px 5px',
              border: `1px solid ${border}`, borderRadius: 2, color: ink2,
            }}>
              {t}
            </span>
          ))}
          {tags.length > 3 && (
            <span style={{ fontSize: 9, color: border }}>+{tags.length - 3}</span>
          )}
        </div>
      )
    } catch { return <span style={{ color: border, fontSize: 11 }}>—</span> }
  }
  if (propType === 'number' && pv.value_num !== null) {
    return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: ink2 }}>{pv.value_num}</span>
  }
  if (propType === 'checkbox') {
    return <span style={{ fontSize: 14, color: ink2 }}>{pv.value_bool ? '☑' : '☐'}</span>
  }
  if (pv.value_text) {
    return (
      <span style={{
        fontSize: 11, color: ink2,
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        display: 'block', maxWidth: 160,
      }}>
        {pv.value_text}
      </span>
    )
  }
  return <span style={{ color: border, fontSize: 11 }}>—</span>
}
