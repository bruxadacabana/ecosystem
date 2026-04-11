/* ============================================================
   AETHER — ProjectView
   Layout principal: Binder (esquerda) + área central.
   A área central exibe o editor (1.8) ou um placeholder
   quando nenhum capítulo está selecionado.
   ============================================================ */

import { useEffect, useState } from 'react'
import { Binder, type ActiveChapter } from './Binder'
import { CharacterView } from './CharacterView'
import { CosmosLayer } from './CosmosLayer'
import { CorkboardView } from './CorkboardView'
import { Editor } from './Editor'
import { OutlineView } from './OutlineView'
import { StatsView } from './StatsView'
import { TimelineView } from './TimelineView'
import { ToastContainer, useToast } from './Toast'
import { TrashView } from './TrashView'
import { WorldbuildingView } from './WorldbuildingView'
import * as cmd from '../lib/tauri'
import type { Project } from '../types'

interface ProjectViewProps {
  project: Project
  onBack: () => void
}

type ViewMode = 'corkboard' | 'outline' | 'trash' | 'characters' | 'worldbuilding' | 'timeline' | 'stats' | null

export function ProjectView({ project, onBack }: ProjectViewProps) {
  const toast = useToast()
  const [activeChapter, setActiveChapter] = useState<ActiveChapter | null>(null)
  const [focusMode, setFocusMode] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>(null)

  // Sair do modo foco com Escape
  useEffect(() => {
    if (!focusMode) return
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setFocusMode(false)
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [focusMode])

  function handleSelectChapterFromView(chapter: ActiveChapter) {
    setActiveChapter(chapter)
    setViewMode(null)
  }

  function toggleView(mode: Exclude<ViewMode, null>) {
    setViewMode((prev) => (prev === mode ? null : mode))
  }

  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        overflow: 'hidden',
        background: 'var(--paper)',
      }}
    >
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />

      {/* Binder lateral — oculto em modo foco */}
      {!focusMode && (
        <Binder
          projectId={project.id}
          projectName={project.name}
          projectType={project.project_type}
          defaultBookId={project.default_book_id ?? undefined}
          activeChapter={activeChapter}
          onSelectChapter={(ch) => { setActiveChapter(ch); setViewMode(null) }}
          onBack={onBack}
          onError={toast.error}
          onSuccess={toast.success}
        />
      )}

      {/* Área central */}
      <main
        style={{
          flex: 1,
          height: '100%',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Toolbar de vistas — oculta em modo foco */}
        {!focusMode && (
          <ViewToolbar
            viewMode={viewMode}
            onToggle={toggleView}
          />
        )}

        {viewMode === 'corkboard' && (
          <CorkboardView
            projectId={project.id}
            projectType={project.project_type}
            defaultBookId={project.default_book_id ?? undefined}
            onSelectChapter={handleSelectChapterFromView}
            onError={toast.error}
          />
        )}

        {viewMode === 'outline' && (
          <OutlineView
            projectId={project.id}
            projectType={project.project_type}
            defaultBookId={project.default_book_id ?? undefined}
            onSelectChapter={handleSelectChapterFromView}
            onError={toast.error}
          />
        )}

        {viewMode === 'trash' && (
          <TrashView
            projectId={project.id}
            onError={toast.error}
            onSuccess={toast.success}
          />
        )}

        {viewMode === 'characters' && (
          <CharacterView
            projectId={project.id}
            onError={toast.error}
            onSuccess={toast.success}
          />
        )}

        {viewMode === 'worldbuilding' && (
          <WorldbuildingView
            projectId={project.id}
            onError={toast.error}
            onSuccess={toast.success}
          />
        )}

        {viewMode === 'timeline' && (
          <TimelineView
            projectId={project.id}
            onError={toast.error}
            onSuccess={toast.success}
          />
        )}

        {viewMode === 'stats' && (
          <StatsView
            projectId={project.id}
            onError={toast.error}
          />
        )}

        {viewMode === null && (
          activeChapter === null ? (
            <ProjectDashboard project={project} />
          ) : (
            <Editor
              chapter={activeChapter}
              focusMode={focusMode}
              onEnterFocus={() => setFocusMode(true)}
              onExitFocus={() => setFocusMode(false)}
              onError={toast.error}
            />
          )
        )}
      </main>
    </div>
  )
}

// ----------------------------------------------------------
//  ViewToolbar
// ----------------------------------------------------------

interface ViewToolbarProps {
  viewMode: ViewMode
  onToggle: (mode: Exclude<ViewMode, null>) => void
}

function ViewToolbar({ viewMode, onToggle }: ViewToolbarProps) {
  const btnStyle = (active: boolean) => ({
    fontFamily: 'var(--font-mono)',
    fontSize: '10px',
    letterSpacing: '0.1em',
    textTransform: 'uppercase' as const,
    padding: '3px 10px',
    color: active ? 'var(--accent)' : 'var(--ink-ghost)',
    background: 'none',
    border: 'none',
    borderBottom: active ? '1px solid var(--accent)' : '1px solid transparent',
    cursor: 'pointer',
    transition: 'color var(--transition), border-color var(--transition)',
  })

  return (
    <div style={{
      height: '28px',
      display: 'flex',
      alignItems: 'center',
      paddingLeft: '8px',
      borderBottom: '1px solid var(--rule)',
      background: 'var(--paper-dark)',
      flexShrink: 0,
      gap: '0',
      overflowX: 'auto',
    }}>
      <button style={btnStyle(viewMode === 'corkboard')} onClick={() => onToggle('corkboard')} title="Vista mural — cartões de capítulo">Mural</button>
      <button style={btnStyle(viewMode === 'outline')} onClick={() => onToggle('outline')} title="Vista esboço — lista com status e sinopse">Esboço</button>
      <button style={btnStyle(viewMode === 'trash')} onClick={() => onToggle('trash')} title="Lixeira — capítulos excluídos">Lixeira</button>
      {/* Separador visual */}
      <div style={{ width: '1px', height: '14px', background: 'var(--rule)', margin: '0 4px', flexShrink: 0 }} />
      <button style={btnStyle(viewMode === 'characters')} onClick={() => onToggle('characters')} title="Fichas de personagens">Personagens</button>
      <button style={btnStyle(viewMode === 'worldbuilding')} onClick={() => onToggle('worldbuilding')} title="Notas de worldbuilding">Mundo</button>
      <button style={btnStyle(viewMode === 'timeline')} onClick={() => onToggle('timeline')} title="Linha do tempo de eventos">Cronologia</button>
      {/* Separador visual */}
      <div style={{ width: '1px', height: '14px', background: 'var(--rule)', margin: '0 4px', flexShrink: 0 }} />
      <button style={btnStyle(viewMode === 'stats')} onClick={() => onToggle('stats')} title="Estatísticas e sessões de escrita">Stats</button>
    </div>
  )
}

// ----------------------------------------------------------
//  Dashboard do projeto
// ----------------------------------------------------------

function hashString(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) {
    h = (Math.imul(31, h) + s.charCodeAt(i)) | 0
  }
  return Math.abs(h)
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('pt-BR', {
    day: '2-digit', month: 'short', year: 'numeric',
  })
}

function formatWords(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

interface DashboardStats {
  chapters: number
  words: number
}

function ProjectDashboard({ project }: { project: Project }) {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const seed = hashString(project.id)

  useEffect(() => {
    loadStats()
  }, [project.id])

  async function loadStats() {
    const booksResult = await cmd.listBooks(project.id)
    if (!booksResult.ok) return

    let totalChapters = 0
    let totalWords = 0
    for (const meta of booksResult.data) {
      const bookResult = await cmd.openBook(project.id, meta.id)
      if (bookResult.ok) {
        totalChapters += bookResult.data.chapters.length
        totalWords += bookResult.data.chapters.reduce(
          (sum, ch) => sum + ch.word_count, 0
        )
      }
    }
    setStats({ chapters: totalChapters, words: totalWords })
  }

  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {/* Header com CosmosLayer */}
      <div
        style={{
          position: 'relative',
          height: '220px',
          flexShrink: 0,
          overflow: 'hidden',
          borderBottom: '1px solid var(--rule)',
        }}
      >
        <CosmosLayer seed={seed} density="medium" animated={true} width={900} height={220} />

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
            flexDirection: 'column',
            justifyContent: 'flex-end',
            padding: '0 40px 24px 64px',
          }}
        >
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontStyle: 'italic',
              fontWeight: 'normal',
              fontSize: '38px',
              color: 'var(--ink)',
              lineHeight: 1.1,
              margin: '0 0 4px',
              letterSpacing: '0.02em',
            }}
          >
            {project.name}
          </h1>
          {project.subtitle && (
            <p
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
                color: 'var(--ink-faint)',
                margin: 0,
                letterSpacing: '0.06em',
              }}
            >
              {project.subtitle}
            </p>
          )}
        </div>
      </div>

      {/* Corpo do dashboard */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '28px 40px 40px 64px',
          position: 'relative',
        }}
      >
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
            pointerEvents: 'none',
          }}
        />

        {/* Estatísticas */}
        <div
          style={{
            display: 'flex',
            gap: '32px',
            marginBottom: '28px',
            flexWrap: 'wrap',
          }}
        >
          {[
            {
              label: 'Palavras',
              value: stats ? formatWords(stats.words) : '—',
            },
            {
              label: 'Capítulos',
              value: stats ? String(stats.chapters) : '—',
            },
            {
              label: 'Criado em',
              value: formatDate(project.created_at),
            },
          ].map((stat) => (
            <div key={stat.label}>
              <p
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '10px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.18em',
                  color: 'var(--ink-ghost)',
                  margin: '0 0 3px',
                }}
              >
                {stat.label}
              </p>
              <p
                style={{
                  fontFamily: 'var(--font-display)',
                  fontStyle: 'italic',
                  fontSize: '26px',
                  color: 'var(--ink)',
                  margin: 0,
                  lineHeight: 1,
                }}
              >
                {stat.value}
              </p>
            </div>
          ))}
        </div>

        {/* Descrição */}
        {project.description && (
          <div style={{ maxWidth: '560px', marginBottom: '24px' }}>
            <p className="section-label" style={{ marginBottom: '8px' }}>Sinopse</p>
            <p
              style={{
                fontFamily: 'var(--font-display)',
                fontStyle: 'italic',
                fontSize: '16px',
                color: 'var(--ink-light)',
                lineHeight: 1.7,
                margin: 0,
              }}
            >
              {project.description}
            </p>
          </div>
        )}

        {/* Metadados visíveis */}
        {(project.genre || project.target_audience || project.language ||
          project.tags.length > 0 || project.tech_level) && (
          <div style={{ marginBottom: '24px' }}>
            <p className="section-label" style={{ marginBottom: '10px' }}>Detalhes</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {project.genre && <MetaBadge value={project.genre} />}
              {project.target_audience && <MetaBadge value={project.target_audience} />}
              {project.language && <MetaBadge value={project.language} />}
              {project.tech_level && <MetaBadge value={project.tech_level} />}
              {project.has_magic_system && <MetaBadge value="Sistema de magia" accent />}
              {project.tags.map((tag) => (
                <MetaBadge key={tag} value={tag} />
              ))}
            </div>
          </div>
        )}

        {/* Inspirações */}
        {project.inspirations && (
          <div style={{ maxWidth: '560px' }}>
            <p className="section-label" style={{ marginBottom: '8px' }}>Inspirações</p>
            <p
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
                color: 'var(--ink-faint)',
                lineHeight: 1.6,
                margin: 0,
              }}
            >
              {project.inspirations}
            </p>
          </div>
        )}

        {/* Hint quando nenhum dado extra existe */}
        {!project.description && !project.genre && project.tags.length === 0 && (
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              color: 'var(--ink-ghost)',
              margin: 0,
              letterSpacing: '0.06em',
            }}
          >
            Selecione um capítulo no binder para começar a escrever.
          </p>
        )}
      </div>
    </div>
  )
}

function MetaBadge({ value, accent }: { value: string; accent?: boolean }) {
  return (
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: '11px',
        letterSpacing: '0.06em',
        color: accent ? 'var(--accent)' : 'var(--ink-faint)',
        border: `1px solid ${accent ? 'var(--accent)' : 'var(--rule)'}`,
        borderRadius: '20px',
        padding: '3px 10px',
        background: 'var(--paper-dark)',
      }}
    >
      {value}
    </span>
  )
}

