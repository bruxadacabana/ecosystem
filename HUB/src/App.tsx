/* ============================================================
   HUB — App Router
   Splash → Layout com Sidebar (seções) + Topbar + Content.
   Seções: Home (dashboard) · LOGOS · Atividade · Configuração.
   Módulos: WritingView · ReadingView · ProjectsView · QuestionsView
   (acessíveis via cards do dashboard ou seção LOGOS).
   ============================================================ */

import { useEffect, useState } from 'react'
import { ToastContainer, useToast } from './components/Toast'
import { Sidebar } from './components/Sidebar'
import { Topbar } from './components/Topbar'
import { Splash } from './views/Splash'
import { DashboardView } from './views/DashboardView'
import { LogosView } from './views/LogosView'
import { AtividadeView } from './views/AtividadeView'
import { SetupView } from './views/SetupView'
import { WritingView } from './views/WritingView'
import { BookView } from './views/BookView'
import { ChapterView } from './views/ChapterView'
import { ReadingView } from './views/ReadingView'
import { ArticleView } from './views/ArticleView'
import { ProjectsView } from './views/ProjectsView'
import { PageView } from './views/PageView'
import { QuestionsView } from './views/QuestionsView'
import * as cmd from './lib/tauri'
import type { HubSection, HubView, Project, Book, ChapterMeta, ArticleMeta, OgmaProject } from './types'

export default function App() {
  const [ready,   setReady]   = useState(false)
  const [section, setSection] = useState<HubSection>('home')
  // Módulo aberto sobre a seção atual (null = mostra a seção)
  const [moduleView, setModuleView] = useState<HubView | null>(null)
  const [compact, setCompact] = useState(false)

  // Caminhos carregados do ecosystem.json para os módulos
  const [vaultPath,    setVaultPath]    = useState('')
  const [archivePath,  setArchivePath]  = useState('')
  const [ogmaDataPath, setOgmaDataPath] = useState('')

  // Seleções em profundidade dos módulos
  const [selectedProject,     setSelectedProject]     = useState<Project | null>(null)
  const [selectedBook,        setSelectedBook]        = useState<Book | null>(null)
  const [selectedChapter,     setSelectedChapter]     = useState<ChapterMeta | null>(null)
  const [selectedArticle,     setSelectedArticle]     = useState<ArticleMeta | null>(null)
  const [selectedOgmaProject, setSelectedOgmaProject] = useState<OgmaProject | null>(null)

  const toast = useToast()

  // Carrega caminhos uma vez ao iniciar (e ao voltar ao home via seção)
  function loadPaths() {
    cmd.readEcosystemConfig().then(result => {
      if (!result.ok) return
      const eco = result.data as Record<string, Record<string, string>>
      setVaultPath(eco.aether?.vault_path    ?? '')
      setArchivePath(eco.kosmos?.archive_path ?? '')
      setOgmaDataPath(eco.ogma?.data_path    ?? '')
    })
  }

  useEffect(() => { loadPaths() }, [])

  // ── Navegação ──────────────────────────────────────────────

  function handleSection(s: HubSection) {
    setSection(s)
    setModuleView(null)
    clearModuleState()
    if (s === 'home') loadPaths()
  }

  function handleOpenModule(module: HubView) {
    setModuleView(module)
    clearModuleState()
  }

  function handleCloseModule() {
    setModuleView(null)
    clearModuleState()
  }

  function clearModuleState() {
    setSelectedProject(null)
    setSelectedBook(null)
    setSelectedChapter(null)
    setSelectedArticle(null)
    setSelectedOgmaProject(null)
  }

  async function handleToggleCompact() {
    const next = !compact
    setCompact(next)
    await cmd.setWindowCompact(next)
  }

  // ── Renderização do conteúdo ───────────────────────────────

  function renderContent() {
    // Módulos sobrepõem a seção quando abertos
    if (moduleView === 'writing') {
      if (selectedChapter && selectedProject && selectedBook) {
        return (
          <ChapterView
            vaultPath={vaultPath}
            projectId={selectedProject.id}
            book={selectedBook}
            chapter={selectedChapter}
            onBack={() => setSelectedChapter(null)}
          />
        )
      }
      if (selectedProject) {
        return (
          <BookView
            vaultPath={vaultPath}
            project={selectedProject}
            onBack={() => setSelectedProject(null)}
            onSelectChapter={(book, chapter) => {
              setSelectedBook(book)
              setSelectedChapter(chapter)
            }}
          />
        )
      }
      return (
        <WritingView
          vaultPath={vaultPath}
          onBack={handleCloseModule}
          onSelectProject={p => setSelectedProject(p)}
        />
      )
    }

    if (moduleView === 'reading') {
      if (selectedArticle) {
        return (
          <ArticleView
            archivePath={archivePath}
            article={selectedArticle}
            onBack={() => setSelectedArticle(null)}
            onReadToggled={(path, isRead) =>
              setSelectedArticle(prev =>
                prev?.path === path ? { ...prev, is_read: isRead } : prev,
              )
            }
          />
        )
      }
      return (
        <ReadingView
          archivePath={archivePath}
          onBack={handleCloseModule}
          onSelectArticle={a => setSelectedArticle(a)}
        />
      )
    }

    if (moduleView === 'projects') {
      if (selectedOgmaProject) {
        return (
          <PageView
            dataPath={ogmaDataPath}
            project={selectedOgmaProject}
            onBack={() => setSelectedOgmaProject(null)}
          />
        )
      }
      return (
        <ProjectsView
          dataPath={ogmaDataPath}
          onBack={handleCloseModule}
          onSelectProject={p => setSelectedOgmaProject(p)}
        />
      )
    }

    if (moduleView === 'questions') {
      return <QuestionsView onBack={handleCloseModule} />
    }

    // Seções principais
    switch (section) {
      case 'home':
        return <DashboardView onOpenModule={handleOpenModule} />
      case 'logos':
        return (
          <LogosView
            onOpenChat={() => handleOpenModule('questions')}
          />
        )
      case 'atividade':
        return <AtividadeView />
      case 'config':
        return (
          <SetupView
            onBack={() => handleSection('home')}
            onSaved={() => {
              toast.success('Configuração salva.')
              handleSection('home')
            }}
          />
        )
    }
  }

  // ── Render ─────────────────────────────────────────────────

  if (!ready) {
    return (
      <>
        <Splash onDone={() => setReady(true)} />
        <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />
      </>
    )
  }

  const activeSection: HubSection = moduleView ? 'home' : section

  return (
    <>
      <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
        {/* Sidebar de seções (ocultada em modo compacto) */}
        {!compact && (
          <Sidebar
            section={activeSection}
            onSection={handleSection}
          />
        )}

        {/* Área principal */}
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            minWidth: 0,
            overflow: 'hidden',
          }}
        >
          <Topbar
            section={activeSection}
            compact={compact}
            onToggleCompact={handleToggleCompact}
          />

          <div
            style={{
              flex: 1,
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {renderContent()}
          </div>
        </div>
      </div>

      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />
    </>
  )
}
