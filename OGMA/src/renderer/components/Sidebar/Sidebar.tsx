import React, { useState } from 'react'
import { CosmosLayer } from '../Cosmos/CosmosLayer'
import './Sidebar.css'

export type Section =
  | 'dashboard' | 'projects' | 'calendar'
  | 'planner' | 'library' | 'analytics' | 'settings'

export type SubSection = 'resources' | 'readings'

interface Project {
  id: number
  name: string
  icon?: string
  color?: string
  project_type?: string
}

interface Props {
  active: Section
  activeSub?: SubSection
  projects: Project[]
  dark: boolean
  collapsed: boolean
  onToggle: () => void
  onNavigate: (s: Section) => void
  onNavigateSub: (s: SubSection) => void
  onProjectSelect: (id: number) => void
  onNewProject: () => void
}

const NAV: { key: Section; icon: string; label: string }[] = [
  { key: 'dashboard',  icon: '◉', label: 'Dashboard'     },
  { key: 'projects',   icon: '✦', label: 'Projetos'       },
  { key: 'calendar',   icon: '☽', label: 'Calendário'     },
  { key: 'planner',    icon: '◈', label: 'Planner'        },
  { key: 'library',    icon: '✶', label: 'Biblioteca'     },
  { key: 'analytics',  icon: '∿', label: 'Analytics'      },
  { key: 'settings',   icon: '⊛', label: 'Configurações'  },
]

export const Sidebar: React.FC<Props> = ({
  active, activeSub, projects, dark, collapsed, onToggle,
  onNavigate, onNavigateSub, onProjectSelect, onNewProject,
}) => {
  const [projectsOpen, setProjectsOpen] = useState(true)
  const [libraryOpen,  setLibraryOpen]  = useState(false)

  const ink   = dark ? '#E8DFC8' : '#2C2416'
  const ink2  = dark ? '#8A7A62' : '#9C8E7A'

  const toggleButton = (
    <button
      onClick={onToggle}
      title={collapsed ? 'Expandir barra lateral' : 'Recolher barra lateral'}
      style={{
        background: 'none', border: 'none', cursor: 'pointer',
        color: ink2, fontSize: 12, padding: '4px 8px',
        fontFamily: 'var(--font-mono)',
      }}
    >
      {collapsed ? '▶' : '◀'}
    </button>
  )

  return (
    <aside className={`sidebar${collapsed ? ' collapsed' : ''}`}>
      {/* ── Logo ─────────────────────────────────────────── */}
      {collapsed ? (
        <div className="sidebar-logo" style={{ position: 'relative', overflow: 'hidden', height: 76, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <CosmosLayer width={44} height={76} seed="sidebar_logo" density="low" dark={dark} style={{ opacity: 0.6, top: 0, left: 0 }} />
          <div style={{ position: 'relative', zIndex: 2, fontFamily: 'var(--font-display)', fontSize: 20, fontStyle: 'italic', color: ink }}>O</div>
        </div>
      ) : (
        <div className="sidebar-logo" style={{ position: 'relative', overflow: 'hidden', height: 76 }}>
          <CosmosLayer
            width={224} height={76}
            seed="sidebar_logo" density="low" dark={dark}
            style={{ opacity: 0.6, top: 0, left: 0 }}
          />
          <div style={{ position: 'relative', zIndex: 2 }}>
            <div className="sidebar-logo-name" style={{ color: ink }}>OGMA</div>
            <div className="sidebar-logo-sub" style={{ color: ink2 }}>
              PROJETOS · ESTUDOS · LEITURAS
            </div>
          </div>
        </div>
      )}

      {/* ── Navegação ────────────────────────────────────── */}
      <nav className="sidebar-nav">
        {NAV.map(({ key, icon, label }) => (
          <React.Fragment key={key}>
            <button
              className={`nav-item${active === key ? ' active' : ''}`}
              title={collapsed ? label : undefined}
              onClick={() => {
                onNavigate(key)
                if (key === 'projects') setProjectsOpen(o => !o)
                if (key === 'library')  setLibraryOpen(o => !o)
              }}
            >
              <span className="nav-item-icon">{icon}</span>
              {!collapsed && <span>{label}</span>}
              {!collapsed && (key === 'projects' || key === 'library') && (
                <span style={{ marginLeft: 'auto', fontSize: 10, opacity: 0.5 }}>
                  {(key === 'projects' ? projectsOpen : libraryOpen) ? '▾' : '▸'}
                </span>
              )}
            </button>

            {/* Sub-itens de Projetos */}
            {!collapsed && key === 'projects' && projectsOpen && (
              <div className="sidebar-sub-list">
                {projects.length === 0 ? (
                  <span className="nav-sub-item" style={{ fontStyle: 'italic', opacity: 0.5 }}>
                    Nenhum projeto ainda
                  </span>
                ) : (
                  projects.map(p => (
                    <button
                      key={p.id}
                      className="nav-item nav-sub-item"
                      onClick={() => onProjectSelect(p.id)}
                    >
                      <span className="nav-item-icon">{p.icon ?? '◦'}</span>
                      <span className="truncate">{p.name}</span>
                    </button>
                  ))
                )}
                <button
                  className="nav-item nav-sub-item"
                  style={{ opacity: 0.6 }}
                  onClick={onNewProject}
                >
                  <span className="nav-item-icon">+</span>
                  <span>Novo projeto</span>
                </button>
              </div>
            )}

            {/* Sub-itens de Biblioteca */}
            {!collapsed && key === 'library' && libraryOpen && (
              <div className="sidebar-sub-list">
                {(['resources', 'readings'] as SubSection[]).map(sub => (
                  <button
                    key={sub}
                    className={`nav-item nav-sub-item${activeSub === sub ? ' active' : ''}`}
                    onClick={() => onNavigateSub(sub)}
                  >
                    <span className="nav-item-icon">
                      {sub === 'resources' ? '◇' : '📖'}
                    </span>
                    <span>{sub === 'resources' ? 'Recursos' : 'Leituras'}</span>
                  </button>
                ))}
              </div>
            )}
          </React.Fragment>
        ))}
      </nav>

      {/* ── Rodapé ───────────────────────────────────────── */}
      {collapsed ? (
        <div className="sidebar-footer" style={{ justifyContent: 'center', padding: '10px 0' }}>
          {toggleButton}
        </div>
      ) : (
        <div className="sidebar-footer" style={{ position: 'relative', overflow: 'hidden', height: 48, justifyContent: 'space-between' }}>
          <CosmosLayer
            width={224} height={48}
            seed="sidebar_footer" density="low" dark={dark}
            style={{ opacity: 0.45, top: 0, left: 0 }}
          />
          <div style={{
            position: 'relative', zIndex: 2,
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 9, letterSpacing: '0.14em',
              color: ink2,
            }}>
              OGMA v0.1.0
            </span>
          </div>
          {toggleButton}
        </div>
      )}
    </aside>
  )
}
