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
import * as cmd from './lib/tauri'
import type { HubView, Project, Book, ChapterMeta } from './types'

type AppView = 'splash' | 'home' | 'setup' | HubView | 'book' | 'chapter'

export default function App() {
  const [view, setView] = useState<AppView>('splash')
  const [vaultPath, setVaultPath] = useState('')
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [selectedBook, setSelectedBook] = useState<Book | null>(null)
  const [selectedChapter, setSelectedChapter] = useState<ChapterMeta | null>(null)
  const toast = useToast()

  // Carrega vault_path do ecosystem.json na inicialização
  useEffect(() => {
    cmd.readEcosystemConfig().then(result => {
      if (result.ok) {
        const path = result.data.aether?.vault_path ?? ''
        setVaultPath(path)
      }
    })
  }, [])

  // Recarrega vault_path quando volta ao home (pode ter sido reconfigurado)
  function handleGoHome() {
    cmd.readEcosystemConfig().then(result => {
      if (result.ok) setVaultPath(result.data.aether?.vault_path ?? '')
    })
    setView('home')
    setSelectedProject(null)
    setSelectedBook(null)
    setSelectedChapter(null)
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

            {/* ---- Placeholders — sub-fases 2.3, 2.4, 2.5 ---- */}
            {(view === 'reading' || view === 'projects' || view === 'questions') && (
              <div style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                justifyContent: 'center', height: '100%', gap: 16, background: 'var(--paper)',
              }}>
                <p style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 24, color: 'var(--ink)' }}>
                  {view === 'reading'   && 'Leituras'}
                  {view === 'projects'  && 'Projetos'}
                  {view === 'questions' && 'Perguntas'}
                </p>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-ghost)' }}>
                  Em desenvolvimento — próxima sub-fase
                </p>
                <button className="btn btn-ghost btn-sm" onClick={handleGoHome}>
                  ← Voltar ao Hub
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />
    </>
  )
}
