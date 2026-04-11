import React, { useEffect, useState, useRef, useCallback } from 'react'
import { Page, Project, ProjectView, ProjectProperty, PropOption } from '../../types'
import { useAppStore } from '../../store/useAppStore'
import { fromIpc } from '../../types/errors'
import { CosmosLayer } from '../../components/Cosmos/CosmosLayer'
import './KanbanView.css'

const db = () => (window as any).db

interface Props {
  view:       ProjectView
  project:    Project
  pages:      Page[]
  properties: ProjectProperty[]
  dark:       boolean
  onPageOpen: (page: Page) => void
  onNewPage:  () => void
}

export const KanbanView: React.FC<Props> = ({
  view, project, pages, properties, dark, onPageOpen,
}) => {
  const [options, setOptions] = useState<PropOption[]>([])
  const { loadPages, pushToast } = useAppStore()

  const groupPropId = view.group_by_property_id

  useEffect(() => {
    if (!groupPropId) return
    fromIpc<PropOption[]>(() => db().properties.getOptions(groupPropId), 'kanbanGetOptions')
      .then(r => r.match(data => setOptions(data), _e => {}))
  }, [groupPropId])

  // ── Paleta ────────────────────────────────────────────────────────────────

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const bg     = dark ? '#1A1610' : '#F5F0E8'
  const colBg  = dark ? '#211D16' : '#EDE7D9'
  const cardBg = dark ? '#1A1610' : '#F5F0E8'

  // ── Agrupamento ───────────────────────────────────────────────────────────

  const getGroupVal = (page: Page): string | null => {
    if (!groupPropId) return null
    const pv = page.prop_values?.find(v => v.property_id === groupPropId)
    return pv?.value_text ?? null
  }

  const groups = options.map(opt => ({
    option: opt,
    pages:  pages.filter(p => getGroupVal(p) === opt.label),
  }))
  const assignedIds  = new Set(groups.flatMap(g => g.pages.map(p => p.id)))
  const uncategorized = pages.filter(p => !assignedIds.has(p.id))

  // ── Drag & Drop ───────────────────────────────────────────────────────────

  const dragRef        = useRef<{ pageId: number } | null>(null)
  const [dragOverCol, setDragOverCol] = useState<string | null>(null)

  const handleDragStart = (e: React.DragEvent, page: Page) => {
    dragRef.current = { pageId: page.id }
    e.dataTransfer.effectAllowed = 'move'
    ;(e.currentTarget as HTMLElement).classList.add('kanban-card--dragging')
  }

  const handleDragEnd = (e: React.DragEvent) => {
    ;(e.currentTarget as HTMLElement).classList.remove('kanban-card--dragging')
    setDragOverCol(null)
    dragRef.current = null
  }

  const handleDrop = useCallback(async (e: React.DragEvent, optionLabel: string) => {
    e.preventDefault()
    setDragOverCol(null)
    const drag = dragRef.current
    if (!drag || !groupPropId) return
    dragRef.current = null
    const result = await fromIpc<unknown>(
      () => db().pages.setPropValue({ page_id: drag.pageId, property_id: groupPropId, value_text: optionLabel }),
      'kanbanSetStatus',
    )
    if (result.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao mover card', detail: result.error.message })
      return
    }
    loadPages(project.id)
  }, [groupPropId, project.id, loadPages, pushToast])

  // ── Quick add ─────────────────────────────────────────────────────────────

  const [creatingIn, setCreatingIn] = useState<string | null>(null)
  const [quickTitle, setQuickTitle] = useState('')

  const handleQuickAdd = useCallback(async (optionLabel: string) => {
    const title = quickTitle.trim()
    if (!title) { setCreatingIn(null); return }
    const createResult = await fromIpc<{ id: number }>(
      () => db().pages.create({ project_id: project.id, title, sort_order: 0 }),
      'kanbanCreatePage',
    )
    if (createResult.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao criar página', detail: createResult.error.message })
      return
    }
    if (groupPropId) {
      await fromIpc<unknown>(
        () => db().pages.setPropValue({ page_id: createResult.value.id, property_id: groupPropId, value_text: optionLabel }),
        'kanbanSetInitialStatus',
      )
    }
    setQuickTitle('')
    setCreatingIn(null)
    loadPages(project.id)
  }, [quickTitle, groupPropId, project.id, loadPages, pushToast])

  // ── Rodapé do card ────────────────────────────────────────────────────────

  const renderCardFooter = (page: Page) => {
    const footer = page.prop_values?.filter(pv =>
      pv.property_id !== groupPropId && (
        (pv.prop_type === 'date'   && pv.value_date) ||
        (pv.prop_type === 'select' && pv.value_text) ||
        (pv.prop_type === 'number' && pv.value_num !== null)
      )
    ).slice(0, 3)
    if (!footer?.length) return null
    return (
      <div className="kanban-card-footer">
        {footer.map(pv => {
          if (pv.prop_type === 'date' && pv.value_date) {
            return (
              <span key={pv.id} className="kanban-card-date" style={{ color: ink2 }}>
                {new Date(pv.value_date + 'T00:00:00').toLocaleDateString('pt-BR', {
                  day: '2-digit', month: 'short',
                })}
              </span>
            )
          }
          if (pv.prop_type === 'select' && pv.value_text) {
            return (
              <span key={pv.id} className="kanban-tag" style={{ background: border, color: ink2 }}>
                {pv.value_text}
              </span>
            )
          }
          if (pv.prop_type === 'number' && pv.value_num !== null) {
            return (
              <span key={pv.id} className="kanban-card-date" style={{ color: ink2 }}>
                {pv.prop_name}: {pv.value_num}
              </span>
            )
          }
          return null
        })}
      </div>
    )
  }

  // ── Card individual ───────────────────────────────────────────────────────

  const renderCard = (page: Page) => (
    <div
      key={page.id}
      className="kanban-card"
      draggable
      onDragStart={e => handleDragStart(e, page)}
      onDragEnd={handleDragEnd}
      onClick={() => onPageOpen(page)}
      style={{ borderColor: border, background: cardBg }}
    >
      <div className="kanban-card-body">
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 7 }}>
          <span style={{ fontSize: 14, lineHeight: 1.4, flexShrink: 0 }}>
            {page.icon ?? '📄'}
          </span>
          <span className="kanban-card-title" style={{ color: ink }}>
            {page.title}
          </span>
        </div>
        {renderCardFooter(page)}
      </div>
    </div>
  )

  // ── Coluna ────────────────────────────────────────────────────────────────

  const renderColumn = (label: string, colPages: Page[], color: string | null) => {
    const colColor  = color ?? border
    const isTarget  = dragOverCol === label

    return (
      <div
        key={label}
        className="kanban-col"
        style={{ borderColor: colColor, borderTopColor: colColor, background: colBg }}
        onDragOver={e => { e.preventDefault(); setDragOverCol(label) }}
        onDrop={e => handleDrop(e, label)}
      >
        {/* Cabeçalho */}
        <div className="kanban-col-header" style={{ borderColor: border }}>
          <span
            className="kanban-col-name"
            style={{ color: colColor === border ? ink : colColor }}
          >
            {label}
          </span>
          <span style={{
            color: ink2, fontSize: 10,
            fontFamily: 'var(--font-mono)', fontWeight: 'normal',
          }}>
            {colPages.length}
          </span>
        </div>

        {/* Cards */}
        <div className="kanban-cards">
          {isTarget && (
            <div className="kanban-drop-line" style={{ background: colColor }} />
          )}
          {colPages.map(page => renderCard(page))}
        </div>

        {/* Rodapé: quick add */}
        <div className="kanban-col-footer">
          {creatingIn === label ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <textarea
                autoFocus
                className="kanban-quick-input"
                placeholder="Título da página..."
                value={quickTitle}
                onChange={e => setQuickTitle(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleQuickAdd(label)
                  }
                  if (e.key === 'Escape') { setCreatingIn(null); setQuickTitle('') }
                }}
                style={{ borderColor: border, color: ink, background: cardBg }}
              />
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn btn-sm btn-primary" onClick={() => handleQuickAdd(label)}>
                  Adicionar
                </button>
                <button className="btn btn-sm btn-ghost"
                  onClick={() => { setCreatingIn(null); setQuickTitle('') }}
                  style={{ color: ink2 }}>
                  Cancelar
                </button>
              </div>
            </div>
          ) : (
            <button
              className="kanban-add-card-btn"
              onClick={() => { setCreatingIn(label); setQuickTitle('') }}
              style={{ color: ink2, borderColor: border }}
            >
              + Página
            </button>
          )}
        </div>
      </div>
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────

  if (!groupPropId) {
    return (
      <div className="kanban-loading" style={{ color: ink2, position: 'relative' }}>
        <CosmosLayer width={480} height={180} seed="kanban_nogroup" density="low" dark={dark}
          style={{ opacity: dark ? 0.2 : 0.1 }} />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontStyle: 'italic' }}>
          Esta vista não tem agrupamento configurado.
        </span>
      </div>
    )
  }

  return (
    <div className="kanban-root" style={{ background: bg }}>
      <div className="kanban-board">
        {groups.map(({ option, pages: colPages }) =>
          renderColumn(option.label, colPages, option.color)
        )}
        {uncategorized.length > 0 &&
          renderColumn('Sem categoria', uncategorized, null)
        }
      </div>
    </div>
  )
}
