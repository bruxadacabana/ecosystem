/* ============================================================
   HUB — App Router
   Splash → Home | Setup | Writing | (outros módulos)
   ============================================================ */

import { useEffect, useState } from 'react'
import { ToastContainer, useToast } from './components/Toast'
import { AppBar } from './components/AppBar'
import { Splash } from './views/Splash'
import { HomeView } from './views/HomeView'
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
import type { HubView, Project, Book, ChapterMeta, ArticleMeta, OgmaProject } from './types'

type AppView = 'splash' | 'home' | 'setup' | HubView | 'book' | 'chapter'

export default function App() {
  const [view, setView] = useState<AppView>('splash')
  const [vaultPath, setVaultPath] = useState('')
  const [archivePath, setArchivePath] = useState('')
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [selectedBook, setSelectedBook] = useState<Book | null>(null)
  const [selectedChapter, setSelectedChapter] = useState<ChapterMeta | null>(null)
  const [selectedArticle, setSelectedArticle] = useState<ArticleMeta | null>(null)
  const [ogmaDataPath, setOgmaDataPath] = useState('')
  const [selectedOgmaProject, setSelectedOgmaProject] = useState<OgmaProject | null>(null)
  const toast = useToast()

  // Carrega caminhos do ecosystem.json na inicialização
  useEffect(() => {
    cmd.readEcosystemConfig().then(result => {
      if (result.ok) {
        setVaultPath(result.data.aether?.vault_path ?? '')
        setArchivePath(result.data.kosmos?.archive_path ?? '')
        setOgmaDataPath(result.data.ogma?.data_path ?? '')
      }
    })
  }, [])

  // Recarrega caminhos quando volta ao home (pode ter sido reconfigurado)
  function handleGoHome() {
    cmd.readEcosystemConfig().then(result => {
      if (result.ok) {
        setVaultPath(result.data.aether?.vault_path ?? '')
        setArchivePath(result.data.kosmos?.archive_path ?? '')
        setOgmaDataPath(result.data.ogma?.data_path ?? '')
      }
    })
    setView('home')
    setSelectedProject(null)
    setSelectedBook(null)
    setSelectedChapter(null)
    setSelectedArticle(null)
    setSelectedOgmaProject(null)
  }

  return (
    <>
      {view === 'splash' && (
        <Splash onDone={() => setView('home')} />
      )}

      {view !== 'splash' && (
        <div style={{ display: 'flex', height: '100%' }}>
          {/* Barra lateral de atalhos — visível em todas as views */}
          <AppBar
            onConfigNeeded={() => {
              toast.info('Configure os executáveis na tela de Configuração.')
              setView('setup')
            }}
          />

          {/* Conteúdo principal */}
          <div style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
            {view === 'home' && (
              <HomeView
                onNavigate={(target: HubView) => setView(target)}
                onSetup={() => setView('setup')}
              />
            )}

            {view === 'setup' && (
              <SetupView
                onBack={() => setView('home')}
                onSaved={() => {
                  toast.success('Configuração salva.')
                  handleGoHome()
                }}
              />
            )}

            {/* ---- Módulo Escrita ---- */}
            {view === 'writing' && (
              <WritingView
                vaultPath={vaultPath}
                onBack={handleGoHome}
                onSelectProject={project => {
                  setSelectedProject(project)
                  setView('book')
                }}
              />
            )}

            {view === 'book' && selectedProject && (
              <BookView
                vaultPath={vaultPath}
                project={selectedProject}
                onBack={() => setView('writing')}
                onSelectChapter={(book, chapter) => {
                  setSelectedBook(book)
                  setSelectedChapter(chapter)
                  setView('chapter')
                }}
              />
            )}

            {view === 'chapter' && selectedProject && selectedBook && selectedChapter && (
              <ChapterView
                vaultPath={vaultPath}
                projectId={selectedProject.id}
                book={selectedBook}
                chapter={selectedChapter}
                onBack={() => setView('book')}
              />
            )}

            {/* ---- Módulo Leituras ---- */}
            {view === 'reading' && !selectedArticle && (
              <ReadingView
                archivePath={archivePath}
                onBack={handleGoHome}
                onSelectArticle={article => {
                  setSelectedArticle(article)
                }}
              />
            )}

            {view === 'reading' && selectedArticle && (
              <ArticleView
                archivePath={archivePath}
                article={selectedArticle}
                onBack={() => setSelectedArticle(null)}
                onReadToggled={(path, isRead) => {
                  setSelectedArticle(prev =>
                    prev?.path === path ? { ...prev, is_read: isRead } : prev
                  )
                }}
              />
            )}

            {/* ---- Módulo Projetos ---- */}
            {view === 'projects' && !selectedOgmaProject && (
              <ProjectsView
                dataPath={ogmaDataPath}
                onBack={handleGoHome}
                onSelectProject={project => setSelectedOgmaProject(project)}
              />
            )}

            {view === 'projects' && selectedOgmaProject && (
              <PageView
                dataPath={ogmaDataPath}
                project={selectedOgmaProject}
                onBack={() => setSelectedOgmaProject(null)}
              />
            )}

            {/* ---- Módulo Perguntas ---- */}
            {view === 'questions' && (
              <QuestionsView onBack={handleGoHome} />
            )}
          </div>
        </div>
      )}

      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />
    </>
  )
}
