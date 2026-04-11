/* ============================================================
   AETHER — App
   Máquina de estados de navegação:
     splash → loading → vault-setup | home → project
   ============================================================ */

import { useEffect, useState } from 'react'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { Splash } from './components/Splash'
import { VaultSetup } from './components/VaultSetup'
import { HomeScreen } from './components/HomeScreen'
import { ProjectView } from './components/ProjectView'
import * as cmd from './lib/tauri'
import type { Project } from './types'

type AppView = 'splash' | 'loading' | 'vault-setup' | 'home' | 'project'

function App() {
  const [view, setView] = useState<AppView>('splash')
  const [activeProject, setActiveProject] = useState<Project | null>(null)

  // F11 — alternar tela cheia
  useEffect(() => {
    async function handleKey(e: KeyboardEvent) {
      if (e.key === 'F11') {
        e.preventDefault()
        const win = getCurrentWindow()
        const isFull = await win.isFullscreen()
        await win.setFullscreen(!isFull)
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [])

  async function checkVaultAndNavigate() {
    setView('loading')
    const result = await cmd.getVaultPath()

    if (!result.ok || result.data === null) {
      setView('vault-setup')
      return
    }

    setView('home')
  }

  function handleOpenProject(project: Project) {
    setActiveProject(project)
    setView('project')
  }

  if (view === 'splash') {
    return <Splash onDone={checkVaultAndNavigate} />
  }

  if (view === 'loading') {
    return (
      <div
        style={{
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--paper)',
        }}
      >
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            color: 'var(--ink-ghost)',
            letterSpacing: '0.1em',
            animation: 'blink 1.2s ease infinite',
          }}
        >
          · · ·
        </p>
      </div>
    )
  }

  if (view === 'vault-setup') {
    return (
      <VaultSetup
        onDone={() => setView('home')}
      />
    )
  }

  if (view === 'home') {
    return <HomeScreen onOpenProject={handleOpenProject} />
  }

  if (view === 'project' && activeProject !== null) {
    return (
      <ProjectView
        project={activeProject}
        onBack={() => { setActiveProject(null); setView('home') }}
      />
    )
  }

  return null
}

export default App
