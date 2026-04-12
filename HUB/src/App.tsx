/* ============================================================
   HUB — App Router
   Splash → Home | Setup
   ============================================================ */

import { useState } from 'react'
import { ToastContainer, useToast } from './components/Toast'
import { Splash } from './views/Splash'
import { HomeView } from './views/HomeView'
import { SetupView } from './views/SetupView'
import type { HubView } from './types'

type AppView = 'splash' | 'home' | 'setup' | HubView

export default function App() {
  const [view, setView] = useState<AppView>('splash')
  const toast = useToast()

  function handleSplashDone() {
    setView('home')
  }

  function handleNavigate(target: HubView) {
    setView(target)
  }

  function handleSetup() {
    setView('setup')
  }

  function handleSetupBack() {
    setView('home')
  }

  function handleSetupSaved() {
    toast.success('Configuração salva.')
    setView('home')
  }

  return (
    <>
      {view === 'splash' && (
        <Splash onDone={handleSplashDone} />
      )}

      {view === 'home' && (
        <HomeView
          onNavigate={handleNavigate}
          onSetup={handleSetup}
        />
      )}

      {view === 'setup' && (
        <SetupView
          onBack={handleSetupBack}
          onSaved={handleSetupSaved}
        />
      )}

      {/* Módulos — placeholders para sub-fases seguintes */}
      {(view === 'writing' || view === 'reading' || view === 'projects' || view === 'questions') && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            gap: 16,
            background: 'var(--paper)',
          }}
        >
          <p
            style={{
              fontFamily: 'var(--font-display)',
              fontStyle: 'italic',
              fontSize: 24,
              color: 'var(--ink)',
            }}
          >
            {view === 'writing'   && 'Escrita'}
            {view === 'reading'   && 'Leituras'}
            {view === 'projects'  && 'Projetos'}
            {view === 'questions' && 'Perguntas'}
          </p>
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--ink-ghost)',
            }}
          >
            Em desenvolvimento — próxima sub-fase
          </p>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setView('home')}
          >
            ← Voltar ao Hub
          </button>
        </div>
      )}

      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />
    </>
  )
}
