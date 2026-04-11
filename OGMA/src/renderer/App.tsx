import React, { useEffect, useState, useCallback } from 'react'
import { SplashScreen } from './components/Splash/SplashScreen'
import { Sidebar, Section, SubSection } from './components/Sidebar/Sidebar'
import { DashboardView } from './views/Dashboard/DashboardView'
import { ProjectDashboardView } from './views/ProjectDashboard/ProjectDashboardView'
import { PageView } from './views/PageView/PageView'
import { NewProjectModal } from './components/Projects/NewProjectModal'
import { EditProjectModal } from './components/Projects/EditProjectModal'
import { NewPageModal } from './components/Pages/NewPageModal'
import { CosmosLayer } from './components/Cosmos/CosmosLayer'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ToastContainer } from './components/UI/Toast'
import { SearchModal } from './components/Search/SearchModal'
import { SettingsView } from './views/Settings/SettingsView'
import { LibraryView } from './views/Library/LibraryView'
import { GlobalCalendarView } from './views/GlobalCalendar/GlobalCalendarView'
import { GlobalPlannerView } from './views/GlobalPlanner/GlobalPlannerView'
import { AnalyticsView } from './views/Analytics/AnalyticsView'
import { useAppStore } from './store/useAppStore'
import { Project, Page, PROJECT_TYPE_ICONS, AppSettings } from './types'

const appSettings = () => (window as any).appSettings

type View = Section | 'project' | 'page'

function PlaceholderView({ title, dark }: { title: string; dark: boolean }) {
  const ink  = dark ? '#E8DFC8' : '#2C2416'
  const ink2 = dark ? '#8A7A62' : '#9C8E7A'
  return (
    <div className="content-area empty-state" style={{ position: 'relative' }}>
      <CosmosLayer width={300} height={200} seed={`ph_${title}`}
        density="medium" dark={dark}
        style={{ position: 'relative', top: 0, left: 0 }} />
      <div style={{ fontSize: 40, position: 'relative', zIndex: 2 }}>✦</div>
      <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontStyle: 'italic',
        color: ink, fontWeight: 'normal', position: 'relative', zIndex: 2 }}>{title}</h2>
      <p style={{ fontSize: 12, color: ink2, maxWidth: 280, textAlign: 'center',
        lineHeight: 1.6, fontStyle: 'italic', position: 'relative', zIndex: 2 }}>
        Esta seção será implementada nas próximas fases.
      </p>
    </div>
  )
}

export default function App() {
  const [splashDone,      setSplashDone]      = useState(false)
  const [initialSettings, setInitialSettings] = useState<AppSettings | null>(null)
  const [view,            setView]            = useState<View>('dashboard')
  const [section,         setSection]         = useState<Section>('dashboard')
  const [activeSub,       setActiveSub]       = useState<SubSection | undefined>()
  const [activePage,      setActivePage]      = useState<Page | null>(null)
  const [showNewProject,  setShowNewProject]  = useState(false)
  const [showEditProject, setShowEditProject] = useState(false)
  const [showNewPage,     setShowNewPage]     = useState(false)
  const [showSearch,      setShowSearch]      = useState(false)

  const {
    dark, setDark,
    workspace,
    projects, loadProjects, loadWorkspace,
    activeProject, selectProject, loadPages, pages,
  } = useAppStore()

  const [fontSizeValue, setFontSizeValue] = useState<'small' | 'normal' | 'large'>('normal')

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() =>
    localStorage.getItem('sidebar_collapsed') === 'true'
  )
  const toggleSidebar = () => {
    const next = !sidebarCollapsed
    setSidebarCollapsed(next)
    localStorage.setItem('sidebar_collapsed', String(next))
  }

  // Carregar settings ao iniciar (antes do splash terminar)
  useEffect(() => {
    appSettings().getAll().then((s: AppSettings) => {
      setInitialSettings(s)
      if (s.theme === 'dark') {
        setDark(true)
        document.documentElement.classList.add('dark')
      }
      if (s.ui_font_size) {
        const val = s.ui_font_size
        setFontSizeValue(val)
        document.documentElement.style.fontSize = ({ small: '13px', normal: '15px', large: '17px' } as const)[val] ?? '13px'
      }
    })
  }, [setDark])

  const handleFontSize = useCallback((val: 'small' | 'normal' | 'large') => {
    setFontSizeValue(val)
    document.documentElement.style.fontSize = ({ small: '13px', normal: '15px', large: '17px' } as const)[val] ?? '13px'
    appSettings().set('ui_font_size', val)
  }, [])

  // Aplicar cor de acento do workspace ao CSS quando carregado ou alterado
  useEffect(() => {
    if (!workspace?.accent_color) return
    document.documentElement.style.setProperty('--accent', workspace.accent_color)
  }, [workspace?.accent_color])

  // Manter activePage sincronizado quando o store recarrega as páginas
  useEffect(() => {
    if (activePage) {
      const updated = pages.find(p => p.id === activePage.id)
      if (updated) setActivePage(updated)
    }
  }, [pages])

  useEffect(() => {
    if (!splashDone) return
    loadWorkspace()
    loadProjects()
  }, [splashDone, loadWorkspace, loadProjects])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setShowSearch(s => !s)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const toggleTheme = useCallback(() => {
    const next = !dark
    setDark(next)
    document.documentElement.classList.toggle('dark', next)
    appSettings().set('theme', next ? 'dark' : 'day')
  }, [dark, setDark])

  const handleNavigate = (s: Section) => {
    setSection(s); setView(s); setActivePage(null)
    if (s !== 'library') setActiveSub(undefined)
  }

  const handleProjectSelect = (id: number) => {
    selectProject(id)
    setView('project'); setSection('projects'); setActivePage(null)
  }

  const handlePageOpen = (page: Page) => {
    setActivePage(page)
    setView('page')
  }

  const handleSearchOpen = useCallback((projectId: number, pageId: number) => {
    selectProject(projectId)
    const page = pages.find(p => p.id === pageId)
    if (page) {
      setActivePage(page)
      setView('page')
      setSection('projects')
    } else {
      // Projeto não estava carregado — navegar para o projeto e abrir a página depois
      setView('project')
      setSection('projects')
    }
  }, [selectProject, pages])

  const handleProjectDeleted = () => {
    setView('projects'); setSection('projects'); setActivePage(null)
    loadProjects()
  }

  // Títulos da topbar
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const inkBg  = dark ? '#211D16' : '#EDE7D9'
  const border = dark ? '#3A3020' : '#C4B9A8'

  const topbarTitle = view === 'project' ? (activeProject?.name ?? 'Projeto')
    : view === 'page' ? (activePage?.title ?? 'Página')
    : view === 'dashboard' ? 'Dashboard'
    : view === 'projects' ? 'Projetos'
    : view === 'calendar' ? 'Calendário'
    : view === 'library'
      ? (activeSub === 'readings' ? 'Biblioteca · Leituras'
         : activeSub === 'resources' ? 'Biblioteca · Recursos'
         : 'Biblioteca')
    : view === 'planner' ? 'Planner'
    : view === 'analytics' ? 'Analytics'
    : view === 'settings' ? 'Configurações'
    : view

  return (
    <ErrorBoundary dark={dark}>
      <ToastContainer />
      {!splashDone && <SplashScreen onDone={() => setSplashDone(true)} dark={dark} />}

      <Sidebar
        active={section} activeSub={activeSub}
        projects={projects.map(p => ({ id: p.id, name: p.name, icon: p.icon ?? undefined, color: p.color ?? undefined }))}
        dark={dark}
        collapsed={sidebarCollapsed}
        onToggle={toggleSidebar}
        onNavigate={handleNavigate}
        onNavigateSub={s => { setActiveSub(s); setSection('library'); setView('library') }}
        onProjectSelect={handleProjectSelect}
        onNewProject={() => setShowNewProject(true)}
      />

      <div className="main-area">
        {/* Topbar */}
        <header className="topbar" style={{ background: inkBg, borderColor: border }}>

          {/* Breadcrumb */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, overflow: 'hidden' }}>
            {(view === 'project' || view === 'page') && activeProject && (
              <>
                <button className="btn btn-ghost btn-sm"
                  onClick={() => { setView('projects'); setSection('projects') }}
                  style={{ color: ink2, padding: '2px 6px', flexShrink: 0 }}>
                  Projetos
                </button>
                <span style={{ color: ink2, fontSize: 12 }}>›</span>
                <button className="btn btn-ghost btn-sm"
                  onClick={() => { setView('project'); setActivePage(null) }}
                  style={{ color: view === 'project' ? ink : ink2, padding: '2px 6px', flexShrink: 0 }}>
                  {activeProject.name}
                </button>
                {view === 'page' && activePage && (
                  <>
                    <span style={{ color: ink2, fontSize: 12 }}>›</span>
                    <span style={{ fontFamily: 'var(--font-display)', fontSize: 14,
                      fontStyle: 'italic', color: ink, overflow: 'hidden',
                      textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {activePage.title}
                    </span>
                  </>
                )}
              </>
            )}
            {view !== 'project' && view !== 'page' && (
              <h2 className="topbar-title" style={{ color: ink }}>{topbarTitle}</h2>
            )}
          </div>

          {/* Ações contextuais */}
          <button
            className="btn btn-ghost btn-sm"
            style={{ color: ink2 }}
            title="Ctrl+K"
            onClick={() => setShowSearch(true)}
          >
            ⌕ Buscar
          </button>

          {view === 'project' && activeProject && (
            <button className="btn btn-sm"
              style={{ borderColor: activeProject.color ?? border, color: activeProject.color ?? ink }}
              onClick={() => setShowNewPage(true)}>
              + Página
            </button>
          )}

          {(view === 'projects' && !activeProject) && (
            <button className="btn btn-sm" style={{ borderColor: border, color: ink }}
              onClick={() => setShowNewProject(true)}>
              + Projeto
            </button>
          )}

          <button className="btn btn-ghost btn-icon" onClick={toggleTheme}
            title="Alternar tema" style={{ fontSize: 16 }}>
            {dark ? '☀' : '☽'}
          </button>
        </header>

        {/* Conteúdo */}
        {/* DashboardView mantém-se sempre montado para preservar o estado dos widgets */}
        <div style={{ display: view === 'dashboard' ? 'contents' : 'none' }}>
          {initialSettings && (
            <DashboardView 
              dark={dark} 
              isActive={view === 'dashboard'} // <--- ADICIONE ESTA LINHA
              onProjectOpen={handleProjectSelect} 
              onPageOpen={handleSearchOpen} 
              initialSettings={initialSettings} 
            />
          )}
        </div>

        {view === 'project' && activeProject && (
          <ProjectDashboardView
            project={activeProject} dark={dark}
            onPageOpen={handlePageOpen}
            onEdit={() => setShowEditProject(true)}
            onNewPage={() => setShowNewPage(true)}
          />
        )}

        {view === 'page' && activePage && activeProject && (
          <PageView
            page={activePage} project={activeProject} dark={dark}
            onBack={() => { setView('project'); setActivePage(null) }}
          />
        )}

        {view === 'projects' && (
          <ProjectsGrid
            projects={projects} dark={dark}
            onSelect={handleProjectSelect}
            onNew={() => setShowNewProject(true)}
          />
        )}

        {view === 'calendar'  && <GlobalCalendarView dark={dark} onPageOpen={handleSearchOpen} />}
        {view === 'planner'   && <GlobalPlannerView dark={dark} onProjectOpen={handleProjectSelect} />}
        {view === 'library'   && <LibraryView dark={dark} activeSub={activeSub}
            onNavigateSub={s => { setActiveSub(s); setSection('library'); setView('library') }} />}
        {view === 'analytics' && <AnalyticsView dark={dark} />}
        {view === 'settings'  && <SettingsView dark={dark} onToggleTheme={toggleTheme} fontSizeValue={fontSizeValue} onFontSize={handleFontSize} />}
      </div>

      {/* Modais */}
      {showSearch && (
        <SearchModal
          dark={dark}
          onClose={() => setShowSearch(false)}
          onOpen={handleSearchOpen}
        />
      )}

      {showNewProject && (
        <NewProjectModal
          onClose={() => setShowNewProject(false)}
          onCreated={id => handleProjectSelect(id)}
        />
      )}

      {showEditProject && activeProject && (
        <EditProjectModal
          project={activeProject}
          onClose={() => setShowEditProject(false)}
          onDeleted={handleProjectDeleted}
        />
      )}

      {showNewPage && activeProject && (
        <NewPageModal
          project={activeProject}
          onClose={() => setShowNewPage(false)}
          onCreated={id => {
            const page = pages.find(p => p.id === id)
            if (page) handlePageOpen(page)
          }}
        />
      )}
    </ErrorBoundary>
  )
}

// ── Grade de projetos ─────────────────────────────────────────────────────────

function ProjectsGrid({ projects, dark, onSelect, onNew }: {
  projects: Project[]; dark: boolean;
  onSelect: (id: number) => void; onNew: () => void;
}) {
  const ink    = dark ? '#E8DFC8' : '#2C2416'
  const ink2   = dark ? '#8A7A62' : '#9C8E7A'
  const border = dark ? '#3A3020' : '#C4B9A8'
  const cardBg = dark ? '#211D16' : '#EDE7D9'

  if (projects.length === 0) {
    return (
      <div className="content-area empty-state" style={{ position: 'relative' }}>
        <CosmosLayer width={300} height={180} seed="projects_empty"
          density="medium" dark={dark}
          style={{ position: 'relative', top: 0, left: 0 }} />
        <div style={{ fontSize: 40, position: 'relative', zIndex: 2 }}>✦</div>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontStyle: 'italic',
          color: ink, fontWeight: 'normal', position: 'relative', zIndex: 2 }}>
          Nenhum projeto ainda
        </h2>
        <p style={{ fontSize: 12, color: ink2, position: 'relative', zIndex: 2,
          maxWidth: 260, textAlign: 'center', lineHeight: 1.6 }}>
          Crie seu primeiro projeto para começar a jornada.
        </p>
        <button className="btn btn-primary" onClick={onNew}
          style={{ marginTop: 12, position: 'relative', zIndex: 2 }}>
          + Criar primeiro projeto
        </button>
      </div>
    )
  }

  return (
    <div style={{ padding: '28px 32px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between',
        alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontStyle: 'italic',
          color: ink, fontWeight: 'normal' }}>
          Projetos ativos
        </h2>
        <button className="btn btn-primary" onClick={onNew}>+ Novo projeto</button>
      </div>

      <div style={{ display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
        {projects.map((p, i) => {
          const color = p.color ?? '#8B7355'
          return (
            <button key={p.id} className="card"
              onClick={() => onSelect(p.id)}
              style={{
                background: cardBg, borderColor: border,
                textAlign: 'left', cursor: 'pointer',
                display: 'flex', flexDirection: 'column', gap: 10,
                animationDelay: `${i * 0.04}s`,
                borderLeft: `4px solid ${color}`, padding: '14px 16px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 22 }}>{p.icon ?? PROJECT_TYPE_ICONS[p.project_type]}</span>
                <div>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: 15,
                    fontStyle: 'italic', color: ink }}>
                    {p.name}
                  </div>
                  <div style={{ fontSize: 10, color: ink2, letterSpacing: '0.06em' }}>
                    {p.project_type === 'academic' ? 'Acadêmico'
                      : p.project_type === 'software' ? 'Dev'
                      : p.project_type === 'health' ? 'Saúde'
                      : p.project_type === 'creative' ? 'Criativo'
                      : p.project_type === 'research' ? 'Pesquisa' : 'Personalizado'}
                    {p.subcategory ? ` · ${p.subcategory}` : ''}
                  </div>
                </div>
              </div>
              {p.description && (
                <p style={{ fontSize: 11, color: ink2, fontStyle: 'italic',
                  lineHeight: 1.4, overflow: 'hidden',
                  display: '-webkit-box', WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical' }}>
                  {p.description}
                </p>
              )}
              <div style={{ background: border, height: 4, borderRadius: 2, overflow: 'hidden' }}>
                <div style={{ background: color, width: '0%', height: '100%', borderRadius: 2 }} />
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
