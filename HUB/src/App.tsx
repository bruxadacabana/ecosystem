/* ============================================================
   HUB — App Router
   Splash → Layout com Sidebar (seções) + Topbar + Content.
   Seções: Home (dashboard) · LOGOS · Atividade · Configuração.
   Módulos: WritingView · ReadingView · ProjectsView
   (acessíveis via cards do dashboard).
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import { ToastContainer, useToast } from './components/Toast'
import { Sidebar } from './components/Sidebar'
import { Topbar } from './components/Topbar'
import { Splash } from './views/Splash'
import { SyncSetupView } from './views/SyncSetupView'
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
import { MonitoramentoView } from './views/MonitoramentoView'
import { ReflexoesView } from './views/ReflexoesView'
import { GitView } from './views/GitView'
import { SyncView } from './views/SyncView'
import { SearchView } from './views/SearchView'
import { FontesView } from './views/FontesView'
import { InteressesView } from './views/InteressesView'
import { ComunicacoesView } from './views/ComunicacoesView'
import * as cmd from './lib/tauri'
import type { HubSection, HubView, Project, Book, ChapterMeta, ArticleMeta, OgmaProject } from './types'

async function isAkashaRunning(): Promise<boolean> {
  try {
    const r = await fetch('http://127.0.0.1:7071/health', { signal: AbortSignal.timeout(400) })
    return r.ok
  } catch { return false }
}

export default function App() {
  const [ready,           setReady]           = useState(false)
  // null = verificando; false = precisa configurar; true = configurado
  const [syncRootReady,   setSyncRootReady]   = useState<boolean | null>(null)
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

  // Git pause state — persiste em ecosystem.json["hub"]["git_paused"]
  const [gitPaused,    setGitPaused]    = useState(false)
  const gitPausedRef = useRef(false)

  // Syncthing pause state
  const [syncthingManualPaused, setSyncthingManualPaused] = useState(false)
  const syncthingAutoPaused = useRef(false)   // auto-pausado pelo HUB (apps com DB rodando)

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

  // Após o Splash, verifica se sync_root já está configurado
  useEffect(() => {
    if (!ready) return
    cmd.readEcosystemConfig().then(result => {
      const syncRoot = result.ok
        ? String((result.data as Record<string, unknown>)['sync_root'] ?? '')
        : ''
      setSyncRootReady(syncRoot.trim() !== '')
    })
  }, [ready])

  // Assim que sync_root está confirmado, garante que o repo git existe e carrega estado de pause
  useEffect(() => {
    if (!syncRootReady) return
    cmd.gitInitSyncRoot().then(result => {
      if (!result.ok) {
        console.warn('[HUB] git init sync_root falhou:', result.error.message)
      }
    })
    cmd.gitGetPaused().then(res => {
      if (res.ok) {
        setGitPaused(res.data)
        gitPausedRef.current = res.data
      }
    })
    cmd.syncthingGetPaused().then(res => {
      if (res.ok) setSyncthingManualPaused(res.data)
    })
  }, [syncRootReady])

  async function handleToggleGitPaused() {
    const next = !gitPaused
    const res = await cmd.gitSetPaused(next)
    if (res.ok) {
      setGitPaused(next)
      gitPausedRef.current = next
    }
  }

  // Watcher: detecta fechamento de apps e faz auto-commit após 3 s
  const prevRunningRef = useRef<Set<string> | null>(null)
  useEffect(() => {
    if (!syncRootReady) return
    const WATCHED = ['akasha', 'mnemosyne', 'kosmos', 'hermes'] as const

    async function pollApps() {
      const cfgRes = await cmd.readEcosystemConfig()
      if (!cfgRes.ok) return
      const eco = cfgRes.data as Record<string, Record<string, string>>

      const exePaths: Record<string, string> = {}
      for (const app of WATCHED) {
        const p = eco[app]?.exe_path
        if (p) exePaths[app] = p
      }

      // AKASHA: health check (porta 7071) em paralelo com exe_path
      const [statusRes, akashaHealthy] = await Promise.all([
        Object.keys(exePaths).length > 0
          ? cmd.getAllAppStatuses(exePaths)
          : Promise.resolve({ ok: true as const, data: {} as Record<string, boolean> }),
        isAkashaRunning(),
      ])
      if (!statusRes.ok) return
      const current: Record<string, boolean> = { ...statusRes.data }
      current['akasha'] = akashaHealthy || Boolean(statusRes.data['akasha'])

      const prev = prevRunningRef.current
      if (prev !== null) {
        for (const app of WATCHED) {
          const wasRunning = prev.has(app)
          const isRunning  = Boolean(current[app])
          if (wasRunning && !isRunning && !gitPausedRef.current) {
            // App fechou — aguarda gravações finalizarem e commita
            setTimeout(() => {
              cmd.gitCommitForApp(app).then(res => {
                if (res.ok && res.data !== 'nothing') {
                  console.info(`[HUB] auto-commit: ${app} → ${res.data}`)
                }
              })
            }, 3_000)
          }
        }
      }

      const next = new Set<string>()
      for (const app of WATCHED) {
        if (current[app]) next.add(app)
      }
      prevRunningRef.current = next

      // Auto-pausa do Syncthing enquanto apps com banco de dados estão rodando
      const DB_APPS = ['akasha', 'mnemosyne', 'kosmos'] as const
      const anyDbRunning = DB_APPS.some(a => Boolean(current[a]))
      if (anyDbRunning && !syncthingAutoPaused.current) {
        syncthingAutoPaused.current = true
        cmd.syncthingPauseAll().catch(() => {})
      } else if (!anyDbRunning && syncthingAutoPaused.current && !syncthingManualPaused) {
        syncthingAutoPaused.current = false
        // WAL checkpoint em todos os DBs antes de retomar o sync
        await Promise.allSettled(DB_APPS.map(app => cmd.syncthingCheckpointAppDbs(app)))
        cmd.syncthingResumeAll().catch(() => {})
      }
    }

    pollApps()
    const id = setInterval(pollApps, 5_000)
    return () => clearInterval(id)
  }, [syncRootReady])

  // Item 6 — Commit agendado a cada 60 min: commita apenas apps fechados
  useEffect(() => {
    if (!syncRootReady) return

    async function scheduledCommit() {
      if (gitPausedRef.current) return
      const cfgRes = await cmd.readEcosystemConfig()
      if (!cfgRes.ok) return
      const eco      = cfgRes.data as Record<string, Record<string, string>>
      const exePaths: Record<string, string> = {}
      for (const app of ['akasha', 'mnemosyne', 'kosmos', 'hermes'] as const) {
        const p = eco[app]?.exe_path
        if (p) exePaths[app] = p
      }
      const statusRes  = await cmd.getAllAppStatuses(exePaths)
      const runningApps = statusRes.ok
        ? Object.entries(statusRes.data).filter(([, v]) => v).map(([k]) => k)
        : []
      cmd.gitScheduledCommit(runningApps).then(res => {
        if (res.ok && res.data !== 'nothing') {
          console.info(`[HUB] scheduled commit: ${res.data}`)
        }
      })
    }

    const id = setInterval(scheduledCommit, 60 * 60 * 1_000)
    return () => clearInterval(id)
  }, [syncRootReady])

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

    // Seções principais
    switch (section) {
      case 'home':
        return <DashboardView onOpenModule={handleOpenModule} />
      case 'logos':
        return <LogosView />
      case 'atividade':
        return <AtividadeView />
      case 'monitoramento':
        return <MonitoramentoView />
      case 'reflexoes':
        return <ReflexoesView />
      case 'fontes':
        return <FontesView />
      case 'interesses':
        return <InteressesView />
      case 'comunicacoes':
        return <ComunicacoesView />
      case 'git':
        return <GitView paused={gitPaused} onTogglePaused={handleToggleGitPaused} />
      case 'sync':
        return <SyncView autoPaused={syncthingAutoPaused.current} />
      case 'busca':
        return <SearchView />
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

  // Aguarda verificação do sync_root (breve) ou exibe tela de primeiro uso
  if (syncRootReady === null || syncRootReady === false) {
    return (
      <>
        {syncRootReady === false && (
          <SyncSetupView onDone={() => { loadPaths(); setSyncRootReady(true) }} />
        )}
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
