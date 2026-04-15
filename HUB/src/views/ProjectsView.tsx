/* ============================================================
   HUB — ProjectsView
   Grade de projetos do OGMA agrupados por tipo.
   ============================================================ */

import { useEffect, useMemo, useState } from 'react'
import { CosmosLayer } from '../components/CosmosLayer'
import * as cmd from '../lib/tauri'
import type { OgmaProject } from '../types'

interface ProjectsViewProps {
  dataPath: string
  onBack: () => void
  onSelectProject: (project: OgmaProject) => void
}

const TYPE_LABEL: Record<string, string> = {
  academic:   'Acadêmico',
  writing:    'Escrita',
  creative:   'Criativo',
  personal:   'Pessoal',
  work:       'Trabalho',
  research:   'Pesquisa',
  custom:     'Personalizado',
}

const STATUS_LABEL: Record<string, string> = {
  active:   'Ativo',
  paused:   'Pausado',
  done:     'Concluído',
}

export function ProjectsView({ dataPath, onBack, onSelectProject }: ProjectsViewProps) {
  const [projects, setProjects] = useState<OgmaProject[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')

  useEffect(() => {
    cmd.listOgmaProjects(dataPath).then(result => {
      setLoading(false)
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      setProjects(result.data)
    })
  }, [dataPath])

  // Agrupa por project_type mantendo a ordem de sort_order
  const groups = useMemo(() => {
    const map = new Map<string, OgmaProject[]>()
    for (const p of projects) {
      const key = p.project_type ?? 'custom'
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(p)
    }
    return Array.from(map.entries())
  }, [projects])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--paper)' }}>
      {/* Topbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '10px 20px', borderBottom: '1px solid var(--rule)', flexShrink: 0,
      }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack}>← Hub</button>
        <h1 style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 20, color: 'var(--ink)' }}>
          Projetos
        </h1>
        {!loading && !error && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-ghost)', letterSpacing: '0.08em' }}>
            {projects.length} projeto{projects.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Conteúdo */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px 40px' }}>
        {loading && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)' }}>
            Carregando projetos…
          </p>
        )}
        {error && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#8B3A2A' }}>{error}</p>
        )}
        {!loading && !error && projects.length === 0 && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)' }}>
            Nenhum projeto ativo encontrado no OGMA.
          </p>
        )}

        {groups.map(([type, list], gi) => (
          <section key={type} style={{ marginBottom: 32 }}>
            <h2 style={{
              fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.22em',
              textTransform: 'uppercase', color: 'var(--ink-ghost)',
              marginBottom: 12, marginTop: gi === 0 ? 4 : 0,
            }}>
              {TYPE_LABEL[type] ?? type}
            </h2>

            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
              gap: 14,
            }}>
              {list.map((project, pi) => (
                <ProjectCard
                  key={project.id}
                  project={project}
                  seed={gi * 31 + pi * 17 + 5}
                  onClick={() => onSelectProject(project)}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  ProjectCard
// ----------------------------------------------------------

interface ProjectCardProps {
  project: OgmaProject
  seed: number
  onClick: () => void
}

function ProjectCard({ project, seed, onClick }: ProjectCardProps) {
  const [hovered, setHovered] = useState(false)

  const accentColor = project.color ?? 'var(--accent)'
  const statusLabel = STATUS_LABEL[project.status] ?? project.status

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: 'relative',
        display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
        justifyContent: 'flex-end',
        padding: '16px 16px 14px',
        height: 160,
        background: hovered ? 'var(--paper-dark)' : 'var(--paper)',
        border: `1px solid var(--rule)`,
        borderLeft: `3px solid ${accentColor}`,
        borderRadius: 'var(--radius)',
        boxShadow: '3px 3px 0 var(--paper-darker)',
        cursor: 'pointer', textAlign: 'left',
        transition: 'background 140ms ease',
        overflow: 'hidden',
      }}
    >
      <CosmosLayer seed={seed} density="low" animated={hovered} width={260} height={160} />

      <div style={{ position: 'relative', zIndex: 1, width: '100%' }}>
        {/* Ícone + status */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
          {project.icon && (
            <span style={{ fontSize: 20 }}>{project.icon}</span>
          )}
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 8, letterSpacing: '0.12em',
            textTransform: 'uppercase', color: 'var(--ink-ghost)',
            border: '1px solid var(--rule)', borderRadius: 2, padding: '1px 5px',
            marginLeft: 'auto',
          }}>
            {statusLabel}
          </span>
        </div>

        {/* Nome */}
        <h3 style={{
          fontFamily: 'var(--font-display)', fontStyle: 'italic', fontWeight: 'normal',
          fontSize: 18, color: 'var(--ink)', lineHeight: 1.2, marginBottom: 4,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {project.name}
        </h3>

        {/* Subcategoria + descrição */}
        {(project.subcategory || project.description) && (
          <p style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-ghost)',
            lineHeight: 1.5, overflow: 'hidden',
            display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
          }}>
            {project.subcategory ? `${project.subcategory} — ` : ''}
            {project.description ?? ''}
          </p>
        )}
      </div>
    </button>
  )
}
