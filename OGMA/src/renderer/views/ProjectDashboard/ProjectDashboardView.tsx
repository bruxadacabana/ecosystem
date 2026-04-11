import React, { useState, useRef, useEffect } from 'react'
import { Project, Page, PROJECT_TYPE_LABELS, PROJECT_TYPE_ICONS } from '../../types'
import { CosmosLayer } from '../../components/Cosmos/CosmosLayer'
import { useAppStore } from '../../store/useAppStore'
import { ViewRenderer } from './ViewRenderer'
import { NewViewModal } from '../../components/Views/NewViewModal'
import { ManagePropertiesModal } from '../../components/Properties/ManagePropertiesModal'
import { PlannerTab } from './PlannerTab'
import { StudyTimerTab } from './StudyTimerTab'
import { ProjectLocalDashboard } from './ProjectLocalDashboard'
import './ProjectDashboardView.css'

interface Props {
  project:    Project
  dark:       boolean
  onPageOpen: (page: Page) => void
  onEdit:     () => void
  onNewPage:  () => void
}

const VIEW_TYPE_ICONS: Record<string, string> = {
  table:    '☰',
  kanban:   '☷',
  list:     '≡',
  calendar: '☽',
  gallery:  '⊞',
  timeline: '⟶',
  progress: '◎',
}

// ── Header ────────────────────────────────────────────────────────────────────

function ProjectHeader({ project, dark, onEdit }: {
  project: Project; dark: boolean; onEdit: () => void
}) {
  const color  = project.color ?? '#8B7355'
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  return (
    <div className="proj-header" style={{ background: cardBg, borderColor: border }}>
      <CosmosLayer width={800} height={120}
        seed={`proj_header_${project.id}`} density="medium" dark={dark}
        style={{ opacity: 0.55 }} />
      <div className="proj-header-bar" style={{ background: color }} />

      <div className="proj-header-content" style={{ position: 'relative', zIndex: 2 }}>
        <div className="proj-header-icon" style={{ background: color + '33', borderColor: color, color }}>
          {project.icon ?? PROJECT_TYPE_ICONS[project.project_type]}
        </div>
        <div style={{ flex: 1 }}>
          <h1 className="proj-header-name" style={{ color: ink }}>{project.name}</h1>
          <div className="proj-header-meta">
            <span className="badge" style={{ borderColor: color, color }}>
              {PROJECT_TYPE_LABELS[project.project_type]}
            </span>
            {project.subcategory && (
              <span className="badge" style={{ borderColor: border, color: ink2 }}>
                {project.subcategory}
              </span>
            )}
            <span className="badge" style={{
              borderColor: project.status === 'active' ? '#4A6741' : border,
              color: project.status === 'active' ? '#4A6741' : ink2,
            }}>
              {project.status === 'active' ? '● Ativo'
                : project.status === 'paused' ? '◌ Pausado'
                : project.status === 'completed' ? '✓ Concluído' : '◻ Arquivado'}
            </span>
          </div>
          {project.description && (
            <p className="proj-header-desc" style={{ color: ink2 }}>{project.description}</p>
          )}
        </div>
        <button className="btn btn-ghost btn-sm" onClick={onEdit}
          style={{ color: ink2, flexShrink: 0 }}>
          ✎ Editar
        </button>
      </div>
    </div>
  )
}

// ── View principal ────────────────────────────────────────────────────────────

type Section = 'dashboard' | 'planner' | 'tempo'

export const ProjectDashboardView: React.FC<Props> = ({
  project, dark, onPageOpen, onEdit, onNewPage,
}) => {
  const {
    pages, projectProperties, projectViews,
    activeViewId, setActiveView,
    loadViews, loadProperties, loadPages,
  } = useAppStore()

  const [section,          setSection]          = useState<Section>('dashboard')
  const [activeView,       setActiveViewLocal]  = useState<number | null>(null)
  const [showViewsDropdown,setShowViewsDropdown] = useState(false)
  const [showNewView,      setShowNewView]      = useState(false)
  const [showManageProps,  setShowManageProps]  = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const color  = project.color ?? '#8B7355'
  const bg     = dark ? '#1A1610' : '#F5F0E8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  // Close dropdown on outside click
  useEffect(() => {
    if (!showViewsDropdown) return
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowViewsDropdown(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showViewsDropdown])

  const openView = (viewId: number) => {
    setActiveViewLocal(viewId)
    setActiveView(viewId)
    setSection('dashboard') // sai de planner/tempo, usa activeView para detectar
    setShowViewsDropdown(false)
  }

  const openDashboard = () => {
    setActiveViewLocal(null)
    setSection('dashboard')
  }

  const currentView = activeView != null
    ? projectViews.find(v => v.id === activeView) ?? null
    : null

  const showingView = section === 'dashboard' && activeView != null && currentView != null

  const noScroll = showingView && (
    currentView?.view_type === 'kanban'
    || currentView?.view_type === 'calendar'
    || currentView?.view_type === 'timeline'
  )

  // toolbar button style helper
  const toolbarBtn = (active: boolean) => ({
    display: 'flex' as const,
    alignItems: 'center' as const,
    gap: 5,
    padding: '6px 12px',
    border: 'none',
    borderBottom: `2px solid ${active ? color : 'transparent'}`,
    background: 'transparent',
    cursor: 'pointer' as const,
    fontFamily: 'var(--font-mono)',
    fontSize: 10,
    letterSpacing: '0.08em',
    color: active ? color : ink2,
    transition: 'color 120ms, border-color 120ms',
    whiteSpace: 'nowrap' as const,
    marginBottom: -1,
  })

  return (
    <div className={`proj-dashboard-root${noScroll ? ' proj-dashboard-root--kanban' : ''}`}>

      {/* ── Header + toolbar — sempre visíveis ───────────────────────── */}
      <div className="proj-dashboard-top">
        <ProjectHeader project={project} dark={dark} onEdit={onEdit} />

        {/* Toolbar */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 0,
          borderBottom: `1px solid ${border}`,
          padding: '0 4px',
        }}>
          {/* ◉ Início */}
          <button
            style={toolbarBtn(section === 'dashboard' && activeView == null)}
            onClick={openDashboard}
          >
            <span style={{ fontSize: 11 }}>◉</span>
            Início
          </button>

          {/* ▼ Vistas (dropdown) */}
          <div ref={dropdownRef} style={{ position: 'relative' }}>
            <button
              style={{
                ...toolbarBtn(showingView),
                paddingRight: 8,
              }}
              onClick={() => setShowViewsDropdown(v => !v)}
            >
              {currentView && showingView
                ? <><span style={{ fontSize: 11 }}>{VIEW_TYPE_ICONS[currentView.view_type] ?? '◦'}</span>{currentView.name}</>
                : <><span style={{ fontSize: 11 }}>☰</span>Vistas</>
              }
              <span style={{ fontSize: 9, marginLeft: 2, opacity: 0.7 }}>▾</span>
            </button>

            {showViewsDropdown && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, zIndex: 100,
                background: cardBg, border: `1px solid ${border}`, borderRadius: 2,
                boxShadow: `3px 3px 0 ${dark ? '#1A1610' : '#C4B9A8'}`,
                minWidth: 180, padding: '4px 0',
              }}>
                {projectViews.map(v => (
                  <button key={v.id}
                    onClick={() => openView(v.id)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '7px 14px', width: '100%', border: 'none',
                      background: activeView === v.id ? color + '18' : 'transparent',
                      cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 10,
                      color: activeView === v.id ? color : ink2,
                      borderLeft: `3px solid ${activeView === v.id ? color : 'transparent'}`,
                    }}
                  >
                    <span>{VIEW_TYPE_ICONS[v.view_type] ?? '◦'}</span>
                    {v.name}
                  </button>
                ))}
                <div style={{ borderTop: `1px solid ${border}`, margin: '4px 0' }} />
                <button
                  onClick={() => { setShowViewsDropdown(false); setShowNewView(true) }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '7px 14px', width: '100%', border: 'none',
                    background: 'transparent', cursor: 'pointer',
                    fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2,
                    borderLeft: '3px solid transparent',
                  }}
                >
                  + Nova vista
                </button>
              </div>
            )}
          </div>

          {/* Planner */}
          <button
            style={toolbarBtn(section === 'planner')}
            onClick={() => { setSection('planner'); setActiveViewLocal(null) }}
          >
            <span style={{ fontSize: 11 }}>⊞</span>
            Planner
          </button>

          {/* Tempo */}
          <button
            style={toolbarBtn(section === 'tempo')}
            onClick={() => { setSection('tempo'); setActiveViewLocal(null) }}
          >
            <span style={{ fontSize: 11 }}>◎</span>
            Tempo
          </button>

          <div style={{ flex: 1 }} />

          {/* Props + Nova página */}
          <button
            className="btn btn-ghost btn-sm"
            style={{ color: ink2, fontSize: 10, padding: '2px 8px' }}
            onClick={() => setShowManageProps(true)}
          >
            ⚙ Props
          </button>
          <button
            className="btn btn-ghost btn-sm"
            style={{ color: ink2, fontSize: 10, padding: '2px 8px' }}
            onClick={onNewPage}
          >
            + Página
          </button>
        </div>
      </div>

      {/* ── Conteúdo ──────────────────────────────────────────────────── */}
      <div className={`proj-dashboard-content${noScroll ? ' proj-dashboard-content--noscroll' : ''}`}>
        {section === 'tempo' ? (
          <StudyTimerTab projectId={project.id} dark={dark} pages={pages} />
        ) : section === 'planner' ? (
          <PlannerTab projectId={project.id} dark={dark} pages={pages} />
        ) : showingView ? (
          <ViewRenderer
            view={currentView!}
            project={project}
            pages={pages}
            properties={projectProperties}
            dark={dark}
            onPageOpen={onPageOpen}
            onNewPage={onNewPage}
          />
        ) : (
          <ProjectLocalDashboard
            project={project}
            dark={dark}
            pages={pages}
            onPageOpen={onPageOpen}
            onOpenPlanner={() => setSection('planner')}
          />
        )}
      </div>

      {showNewView && (
        <NewViewModal
          project={project}
          properties={projectProperties}
          dark={dark}
          onClose={() => setShowNewView(false)}
          onCreated={(viewId) => { openView(viewId) }}
        />
      )}

      {showManageProps && (
        <ManagePropertiesModal
          project={project}
          dark={dark}
          onClose={() => setShowManageProps(false)}
          onChanged={() => { loadProperties(project.id); loadViews(project.id); loadPages(project.id) }}
        />
      )}
    </div>
  )
}
