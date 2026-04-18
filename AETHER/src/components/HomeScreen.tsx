/* ============================================================
   AETHER — HomeScreen
   Lista de projetos do vault. Criar, abrir, deletar projetos.
   ============================================================ */

import { useEffect, useState } from 'react'
import { CosmosLayer } from './CosmosLayer'
import { ThemeToggle } from './ThemeToggle'
import { ToastContainer, useToast } from './Toast'
import * as cmd from '../lib/tauri'
import type { Project, ProjectType } from '../types'

interface HomeScreenProps {
  onOpenProject: (project: Project) => void
}

// ----------------------------------------------------------
//  Utilitários
// ----------------------------------------------------------

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

// Hash numérico simples para usar como seed do CosmosLayer
function hashString(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) {
    h = (Math.imul(31, h) + s.charCodeAt(i)) | 0
  }
  return Math.abs(h)
}

// ----------------------------------------------------------
//  Modal de novo projeto
// ----------------------------------------------------------

interface NewProjectData {
  name: string
  projectType: ProjectType
  description: string
  subtitle: string
  genre: string
  targetAudience: string
  language: string
  tags: string
  hasMagicSystem: boolean
  techLevel: string
  inspirations: string
}

interface NewProjectModalProps {
  onConfirm: (data: NewProjectData) => void
  onCancel: () => void
}

function OptLabel() {
  return (
    <span style={{ color: 'var(--ink-ghost)', textTransform: 'none',
      letterSpacing: 0, fontSize: '11px' }}>
      {' '}(opcional)
    </span>
  )
}

function SectionSep({ label }: { label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', margin: '4px 0 -4px' }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px',
        textTransform: 'uppercase', letterSpacing: '0.18em',
        color: 'var(--ink-ghost)', whiteSpace: 'nowrap' }}>
        {label}
      </span>
      <div style={{ flex: 1, height: '1px', background: 'var(--rule)' }} />
    </div>
  )
}

function NewProjectModal({ onConfirm, onCancel }: NewProjectModalProps) {
  const [name, setName] = useState('')
  const [projectType, setProjectType] = useState<ProjectType>('single')
  const [description, setDescription] = useState('')
  const [subtitle, setSubtitle] = useState('')
  const [genre, setGenre] = useState('')
  const [targetAudience, setTargetAudience] = useState('')
  const [language, setLanguage] = useState('')
  const [tags, setTags] = useState('')
  const [hasMagicSystem, setHasMagicSystem] = useState(false)
  const [techLevel, setTechLevel] = useState('')
  const [inspirations, setInspirations] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (trimmed.length > 0) {
      onConfirm({
        name: trimmed,
        projectType,
        description: description.trim(),
        subtitle: subtitle.trim(),
        genre: genre.trim(),
        targetAudience: targetAudience.trim(),
        language: language.trim(),
        tags: tags.trim(),
        hasMagicSystem,
        techLevel: techLevel.trim(),
        inspirations: inspirations.trim(),
      })
    }
  }

  const typeOptionStyle = (active: boolean): React.CSSProperties => ({
    flex: 1,
    padding: '12px 16px',
    border: `1px solid ${active ? 'var(--accent)' : 'var(--rule)'}`,
    borderRadius: 'var(--radius)',
    background: active ? 'var(--paper-darker)' : 'var(--paper-dark)',
    cursor: 'pointer',
    transition: 'all var(--transition)',
    textAlign: 'left',
    boxShadow: active ? '2px 2px 0 var(--stamp)' : '2px 2px 0 var(--rule)',
  })

  const toggleStyle = (active: boolean): React.CSSProperties => ({
    padding: '7px 14px',
    border: `1px solid ${active ? 'var(--accent)' : 'var(--rule)'}`,
    borderRadius: 'var(--radius)',
    background: active ? 'var(--paper-darker)' : 'var(--paper-dark)',
    cursor: 'pointer',
    fontFamily: 'var(--font-mono)',
    fontSize: '12px',
    color: active ? 'var(--ink)' : 'var(--ink-ghost)',
    transition: 'all var(--transition)',
    boxShadow: active ? '2px 2px 0 var(--stamp)' : '2px 2px 0 var(--rule)',
  })

  return (
    <div
      className="modal-overlay"
      onClick={(e) => { if (e.target === e.currentTarget) onCancel() }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="new-project-title"
        style={{ minWidth: '520px', maxWidth: '600px' }}>
        <h2 className="modal-title" id="new-project-title">Novo Projeto</h2>

        <form onSubmit={handleSubmit}>
          <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px',
            maxHeight: '70vh', overflowY: 'auto' }}>

            {/* Tipo de projeto */}
            <div className="form-group">
              <span className="form-label">Tipo de projeto</span>
              <div style={{ display: 'flex', gap: '10px', marginTop: '4px' }}>
                <button type="button" style={typeOptionStyle(projectType === 'single')}
                  onClick={() => setProjectType('single')}>
                  <p style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic',
                    fontSize: '16px', color: 'var(--ink)', margin: '0 0 4px' }}>Livro único</p>
                  <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px',
                    color: 'var(--ink-faint)', margin: 0, lineHeight: 1.5 }}>Um livro, muitos capítulos.</p>
                </button>
                <button type="button" style={typeOptionStyle(projectType === 'series')}
                  onClick={() => setProjectType('series')}>
                  <p style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic',
                    fontSize: '16px', color: 'var(--ink)', margin: '0 0 4px' }}>Série</p>
                  <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px',
                    color: 'var(--ink-faint)', margin: 0, lineHeight: 1.5 }}>Múltiplos livros numa saga.</p>
                </button>
                <button type="button" style={typeOptionStyle(projectType === 'fanfiction')}
                  onClick={() => setProjectType('fanfiction')}>
                  <p style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic',
                    fontSize: '16px', color: 'var(--ink)', margin: '0 0 4px' }}>Fanfiction</p>
                  <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px',
                    color: 'var(--ink-faint)', margin: 0, lineHeight: 1.5 }}>Um fandom, muitas histórias.</p>
                </button>
              </div>
            </div>

            {/* Título */}
            <div className="form-group">
              <label className="form-label" htmlFor="project-name">
                {projectType === 'single' ? 'Título do livro'
                  : projectType === 'fanfiction' ? 'Nome do fandom'
                  : 'Nome da série'}
              </label>
              <input
                id="project-name"
                className="input"
                type="text"
                placeholder={projectType === 'single' ? 'O título do seu livro...'
                  : projectType === 'fanfiction' ? 'Ex: Harry Potter, Attack on Titan...'
                  : 'O nome da sua saga...'}
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
                maxLength={120}
              />
            </div>

            {/* Subtítulo */}
            <div className="form-group">
              <label className="form-label" htmlFor="project-subtitle">
                Subtítulo <OptLabel />
              </label>
              <input
                id="project-subtitle"
                className="input"
                type="text"
                placeholder="Um subtítulo ou tagline..."
                value={subtitle}
                onChange={(e) => setSubtitle(e.target.value)}
                maxLength={200}
              />
            </div>

            {/* Descrição */}
            <div className="form-group">
              <label className="form-label" htmlFor="project-desc">
                Sinopse <OptLabel />
              </label>
              <textarea
                id="project-desc"
                className="input"
                placeholder="Uma sinopse, premissa ou nota para você mesmo..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={600}
                rows={3}
                style={{ resize: 'none', fontFamily: 'var(--font-display)',
                  fontStyle: 'italic', lineHeight: 1.6 }}
              />
            </div>

            {/* ── Metadados ─────────────────────────────── */}
            <SectionSep label="Metadados" />

            {/* Gênero + Público-alvo */}
            <div style={{ display: 'flex', gap: '12px' }}>
              <div className="form-group" style={{ flex: 1 }}>
                <label className="form-label" htmlFor="project-genre">
                  Gênero <OptLabel />
                </label>
                <input
                  id="project-genre"
                  className="input"
                  type="text"
                  placeholder="Fantasia, Sci-fi, Romance..."
                  value={genre}
                  onChange={(e) => setGenre(e.target.value)}
                  maxLength={80}
                />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label className="form-label" htmlFor="project-audience">
                  Público-alvo <OptLabel />
                </label>
                <input
                  id="project-audience"
                  className="input"
                  type="text"
                  placeholder="Adulto, Young Adult, Infantil..."
                  value={targetAudience}
                  onChange={(e) => setTargetAudience(e.target.value)}
                  maxLength={80}
                />
              </div>
            </div>

            {/* Idioma + Tags */}
            <div style={{ display: 'flex', gap: '12px' }}>
              <div className="form-group" style={{ flex: 1 }}>
                <label className="form-label" htmlFor="project-language">
                  Idioma <OptLabel />
                </label>
                <input
                  id="project-language"
                  className="input"
                  type="text"
                  placeholder="Português, English..."
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  maxLength={60}
                />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label className="form-label" htmlFor="project-tags">
                  Tags <OptLabel />
                </label>
                <input
                  id="project-tags"
                  className="input"
                  type="text"
                  placeholder="magia, guerra, politica..."
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  maxLength={200}
                  title="Separe as tags por vírgulas"
                />
              </div>
            </div>

            {/* ── Worldbuilding ──────────────────────────── */}
            <SectionSep label="Worldbuilding" />

            {/* Sistema de magia */}
            <div className="form-group">
              <span className="form-label">Sistema de magia</span>
              <div style={{ display: 'flex', gap: '8px', marginTop: '6px' }}>
                <button type="button" style={toggleStyle(!hasMagicSystem)}
                  onClick={() => setHasMagicSystem(false)}>
                  Não
                </button>
                <button type="button" style={toggleStyle(hasMagicSystem)}
                  onClick={() => setHasMagicSystem(true)}>
                  Sim
                </button>
              </div>
            </div>

            {/* Nível tecnológico */}
            <div className="form-group">
              <label className="form-label" htmlFor="project-tech">
                Nível tecnológico <OptLabel />
              </label>
              <input
                id="project-tech"
                className="input"
                type="text"
                placeholder="Medieval, Steampunk, Moderno, Sci-fi..."
                value={techLevel}
                onChange={(e) => setTechLevel(e.target.value)}
                maxLength={100}
              />
            </div>

            {/* Inspirações */}
            <div className="form-group">
              <label className="form-label" htmlFor="project-inspirations">
                Inspirações <OptLabel />
              </label>
              <textarea
                id="project-inspirations"
                className="input"
                placeholder="Obras, autores, filmes, músicas que inspiram este projeto..."
                value={inspirations}
                onChange={(e) => setInspirations(e.target.value)}
                maxLength={400}
                rows={2}
                style={{ resize: 'none', lineHeight: 1.5 }}
              />
            </div>

          </div>

          <div className="modal-footer">
            <button type="button" className="btn btn-ghost" onClick={onCancel}>
              Cancelar
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={name.trim().length === 0}
            >
              Criar projeto
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  Card de projeto
// ----------------------------------------------------------

interface ProjectCardProps {
  project: Project
  onOpen: () => void
  onDelete: () => void
  index: number
}

function ProjectCard({ project, onOpen, onDelete, index }: ProjectCardProps) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [hovered, setHovered] = useState(false)
  const seed = hashString(project.id)

  return (
    <div
      className="card"
      style={{
        position: 'relative',
        overflow: 'hidden',
        cursor: 'pointer',
        animationDelay: `${index * 0.04}s`,
        padding: 0,
      }}
      onClick={onOpen}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => { setHovered(false); setConfirmDelete(false) }}
    >
      {/* Cosmos de fundo — baixa densidade */}
      <CosmosLayer seed={seed} density="low" animated={false} width={580} height={90} />

      {/* Linha de margem */}
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          left: '36px',
          width: '1px',
          background: 'var(--margin-line)',
          zIndex: 1,
        }}
      />

      <div
        style={{
          position: 'relative',
          zIndex: 2,
          padding: '14px 16px 14px 52px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
        }}
      >
        {/* Info */}
        <div style={{ minWidth: 0, flex: 1 }}>
          <p
            style={{
              fontFamily: 'var(--font-display)',
              fontStyle: 'italic',
              fontSize: '17px',
              color: 'var(--ink)',
              margin: '0 0 3px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {project.name}
          </p>
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              color: 'var(--ink-ghost)',
              margin: 0,
              letterSpacing: '0.04em',
            }}
          >
            Editado {formatDate(project.updated_at)}
          </p>
        </div>

        {/* Ações — visíveis no hover */}
        {(hovered || confirmDelete) && (
          <div
            style={{ display: 'flex', gap: '4px', flexShrink: 0 }}
            onClick={(e) => e.stopPropagation()}
          >
            {confirmDelete ? (
              <>
                <button
                  className="btn btn-danger btn-sm"
                  onClick={onDelete}
                  title="Confirmar exclusão"
                >
                  Confirmar
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => setConfirmDelete(false)}
                >
                  Cancelar
                </button>
              </>
            ) : (
              <button
                className="btn btn-ghost btn-icon btn-sm"
                onClick={() => setConfirmDelete(true)}
                title="Excluir projeto"
                aria-label="Excluir projeto"
                style={{ color: 'var(--ink-ghost)', fontSize: '18px', lineHeight: 1 }}
              >
                ×
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  HomeScreen
// ----------------------------------------------------------

export function HomeScreen({ onOpenProject }: HomeScreenProps) {
  const toast = useToast()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [showNewModal, setShowNewModal] = useState(false)

  useEffect(() => {
    loadProjects()
  }, [])

  async function loadProjects() {
    setLoading(true)
    const result = await cmd.listProjects()
    setLoading(false)

    if (!result.ok) {
      toast.error(`Erro ao carregar projetos: ${result.error.message}`)
      return
    }
    setProjects(result.data)
  }

  async function handleCreateProject(data: {
    name: string
    projectType: import('../types').ProjectType
    description: string
    subtitle: string
    genre: string
    targetAudience: string
    language: string
    tags: string
    hasMagicSystem: boolean
    techLevel: string
    inspirations: string
  }) {
    setShowNewModal(false)
    const result = await cmd.createProject({
      name: data.name,
      projectType: data.projectType,
      description: data.description || undefined,
      subtitle: data.subtitle || undefined,
      genre: data.genre || undefined,
      targetAudience: data.targetAudience || undefined,
      language: data.language || undefined,
      tags: data.tags ? data.tags.split(',').map((t) => t.trim()).filter(Boolean) : undefined,
      hasMagicSystem: data.hasMagicSystem || undefined,
      techLevel: data.techLevel || undefined,
      inspirations: data.inspirations || undefined,
    })

    if (!result.ok) {
      toast.error(`Não foi possível criar o projeto: ${result.error.message}`)
      return
    }

    toast.success(`Projeto "${result.data.name}" criado.`)
    setProjects((prev) => [result.data, ...prev])
  }

  async function handleDeleteProject(project: Project) {
    const result = await cmd.deleteProject(project.id)

    if (!result.ok) {
      toast.error(`Erro ao excluir: ${result.error.message}`)
      return
    }

    toast.info(`"${project.name}" excluído.`)
    setProjects((prev) => prev.filter((p) => p.id !== project.id))
  }

  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--paper)',
        overflow: 'hidden',
      }}
    >
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />

      {/* Header com CosmosLayer */}
      <header
        style={{
          position: 'relative',
          height: '140px',
          flexShrink: 0,
          overflow: 'hidden',
          borderBottom: '1px solid var(--rule)',
        }}
      >
        <CosmosLayer seed={7} density="medium" animated={true} width={1280} height={140} />

        {/* Linha de margem */}
        <div
          aria-hidden="true"
          style={{
            position: 'absolute',
            top: 0,
            bottom: 0,
            left: '48px',
            width: '1px',
            background: 'var(--margin-line)',
            zIndex: 1,
          }}
        />

        <div
          style={{
            position: 'relative',
            zIndex: 2,
            height: '100%',
            display: 'flex',
            alignItems: 'flex-end',
            padding: '0 40px 20px 64px',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <h1
              style={{
                fontFamily: 'var(--font-display)',
                fontStyle: 'italic',
                fontWeight: 'normal',
                fontSize: '42px',
                color: 'var(--ink)',
                lineHeight: 1,
                margin: '0 0 4px',
                letterSpacing: '0.04em',
              }}
            >
              AETHER
            </h1>
            <p
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                textTransform: 'uppercase',
                letterSpacing: '0.22em',
                color: 'var(--ink-faint)',
                margin: 0,
              }}
            >
              Forja de Mundos
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
            <ThemeToggle />
            <button
              className="btn btn-primary"
              onClick={() => setShowNewModal(true)}
            >
              + Novo Projeto
            </button>
          </div>
        </div>
      </header>

      {/* Lista de projetos */}
      <main
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '28px 40px 40px 64px',
        }}
      >
        {loading && (
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '14px',
              color: 'var(--ink-ghost)',
              letterSpacing: '0.06em',
            }}
          >
            Carregando projetos...
          </p>
        )}

        {!loading && projects.length === 0 && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '200px',
              gap: '12px',
            }}
          >
            <p
              style={{
                fontFamily: 'var(--font-display)',
                fontStyle: 'italic',
                fontSize: '18px',
                color: 'var(--ink-faint)',
                margin: 0,
              }}
            >
              Nenhum projeto ainda.
            </p>
            <p
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '14px',
                color: 'var(--ink-ghost)',
                margin: 0,
                letterSpacing: '0.04em',
              }}
            >
              Crie o seu primeiro mundo acima.
            </p>
          </div>
        )}

        {!loading && projects.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '640px' }}>
            <p className="section-label" style={{ marginBottom: '12px' }}>
              Projetos — {projects.length}
            </p>
            {projects.map((project, i) => (
              <ProjectCard
                key={project.id}
                project={project}
                index={i}
                onOpen={() => onOpenProject(project)}
                onDelete={() => handleDeleteProject(project)}
              />
            ))}
          </div>
        )}
      </main>

      {showNewModal && (
        <NewProjectModal
          onConfirm={handleCreateProject}
          onCancel={() => setShowNewModal(false)}
        />
      )}
    </div>
  )
}
