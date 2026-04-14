/* ============================================================
   HUB — WritingView
   Grade de projetos do vault AETHER.
   ============================================================ */

import { useEffect, useState } from 'react'
import { CosmosLayer } from '../components/CosmosLayer'
import * as cmd from '../lib/tauri'
import type { Project } from '../types'

interface WritingViewProps {
  vaultPath: string
  onBack: () => void
  onSelectProject: (project: Project) => void
}

const TYPE_LABEL: Record<string, string> = {
  single:     'Romance',
  series:     'Série',
  fanfiction: 'Fanfiction',
}

export function WritingView({ vaultPath, onBack, onSelectProject }: WritingViewProps) {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    cmd.listWritingProjects(vaultPath).then(result => {
      setLoading(false)
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      setProjects(result.data)
    })
  }, [vaultPath])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--paper)' }}>
      {/* Topbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '10px 20px', borderBottom: '1px solid var(--rule)', flexShrink: 0,
      }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack}>← Hub</button>
        <h1 style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 20, color: 'var(--ink)' }}>
          Escrita
        </h1>
      </div>

      {/* Conteúdo */}
      <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
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
            Nenhum projeto encontrado no vault.
          </p>
        )}

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: 16,
        }}>
          {projects.map((project, i) => (
            <ProjectCard
              key={project.id}
              project={project}
              seed={i * 17 + 3}
              onClick={() => onSelectProject(project)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  ProjectCard
// ----------------------------------------------------------

interface ProjectCardProps {
  project: Project
  seed: number
  onClick: () => void
}

function ProjectCard({ project, seed, onClick }: ProjectCardProps) {
  const [hovered, setHovered] = useState(false)

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        justifyContent: 'flex-end',
        padding: '20px 20px 18px',
        height: 180,
        background: hovered ? 'var(--paper-dark)' : 'var(--paper)',
        border: '1px solid var(--rule)',
        borderRadius: 'var(--radius)',
        boxShadow: '3px 3px 0 var(--paper-darker)',
        cursor: 'pointer',
        textAlign: 'left',
        transition: 'background 140ms ease',
        overflow: 'hidden',
      }}
    >
      <CosmosLayer seed={seed} density="low" animated={hovered} width={280} height={180} />

      <div style={{ position: 'relative', zIndex: 1 }}>
        {/* Tipo */}
        <span style={{
          display: 'block',
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          letterSpacing: '0.16em',
          textTransform: 'uppercase',
          color: 'var(--accent)',
          marginBottom: 4,
        }}>
          {TYPE_LABEL[project.project_type] ?? project.project_type}
          {project.genre ? ` · ${project.genre}` : ''}
        </span>

        {/* Nome */}
        <h2 style={{
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          fontSize: 20,
          color: 'var(--ink)',
          marginBottom: project.description ? 6 : 0,
          lineHeight: 1.2,
        }}>
          {project.name}
        </h2>

        {/* Descrição */}
        {project.description && (
          <p style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: 'var(--ink-ghost)',
            lineHeight: 1.5,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}>
            {project.description}
          </p>
        )}
      </div>
    </button>
  )
}
