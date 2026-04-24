/* ============================================================
   HUB — HomeView
   Dashboard com 4 cards de módulos + botão de configuração.
   ============================================================ */

import { useEffect, useState } from 'react'
import { CosmosLayer } from '../components/CosmosLayer'
import { LogosPanel } from '../components/LogosPanel'
import { ThemeToggle } from '../components/ThemeToggle'
import * as cmd from '../lib/tauri'
import type { EcosystemConfig, HubView, ModuleCard } from '../types'

interface HomeViewProps {
  onNavigate: (view: HubView) => void
  onSetup: () => void
}

const MODULES: ModuleCard[] = [
  {
    id: 'writing',
    label: 'Escrita',
    description: 'Projetos, livros e capítulos do vault AETHER',
    seed: 7,
    configKey: 'aether',
    configField: 'vault_path',
  },
  {
    id: 'reading',
    label: 'Leituras',
    description: 'Artigos salvos no archive do KOSMOS',
    seed: 13,
    configKey: 'kosmos',
    configField: 'archive_path',
  },
  {
    id: 'projects',
    label: 'Projetos',
    description: 'Projetos e páginas do OGMA',
    seed: 42,
    configKey: 'ogma',
    configField: 'data_path',
  },
  {
    id: 'questions',
    label: 'Perguntas',
    description: 'Chat com modelos do Ollama',
    seed: 99,
    configKey: 'ogma',  // não requer config específica — sempre disponível se Ollama rodar
    configField: '',
  },
]

export function HomeView({ onNavigate, onSetup }: HomeViewProps) {
  const [eco, setEco] = useState<Partial<EcosystemConfig>>({})

  useEffect(() => {
    cmd.readEcosystemConfig().then(result => {
      if (result.ok) setEco(result.data)
    })
  }, [])

  function isEnabled(m: ModuleCard): boolean {
    // Módulo Perguntas está sempre disponível
    if (m.id === 'questions') return true
    if (!m.configField) return true
    const section = eco[m.configKey] as Record<string, string> | undefined
    return Boolean(section?.[m.configField]?.trim())
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--paper)',
      }}
    >
      {/* Topbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 20px',
          borderBottom: '1px solid var(--rule)',
          flexShrink: 0,
        }}
      >
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontStyle: 'italic',
            fontSize: 22,
            color: 'var(--ink)',
          }}
        >
          HUB
        </h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <ThemeToggle />
          <button
            className="btn btn-ghost btn-sm"
            onClick={onSetup}
            title="Configuração do ecossistema"
          >
            ⚙
          </button>
        </div>
      </div>

      {/* Grid de módulos */}
      <div
        style={{
          flex: 1,
          display: 'grid',
          gridTemplateColumns: 'repeat(2, 1fr)',
          gridTemplateRows: 'repeat(2, 1fr)',
          gap: 1,
          background: 'var(--rule)',
          overflow: 'hidden',
          minHeight: 0,
        }}
      >
        {MODULES.map(m => {
          const enabled = isEnabled(m)
          return (
            <button
              key={m.id}
              disabled={!enabled}
              onClick={() => onNavigate(m.id)}
              style={{
                position: 'relative',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'flex-start',
                justifyContent: 'flex-end',
                padding: '28px 32px',
                background: 'var(--paper)',
                border: 'none',
                cursor: enabled ? 'pointer' : 'default',
                opacity: enabled ? 1 : 0.45,
                textAlign: 'left',
                transition: 'background 140ms ease',
                overflow: 'hidden',
              }}
              onMouseEnter={e => {
                if (enabled) {
                  (e.currentTarget as HTMLButtonElement).style.background = 'var(--paper-dark)'
                }
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLButtonElement).style.background = 'var(--paper)'
              }}
            >
              {/* CosmosLayer de fundo */}
              <CosmosLayer
                seed={m.seed}
                density="medium"
                animated={enabled}
                width={600}
                height={400}
                className=""
              />

              {/* Conteúdo */}
              <div style={{ position: 'relative', zIndex: 1 }}>
                <h2
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontStyle: 'italic',
                    fontSize: 28,
                    color: 'var(--ink)',
                    marginBottom: 6,
                  }}
                >
                  {m.label}
                </h2>
                <p
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--ink-ghost)',
                    letterSpacing: '0.06em',
                    maxWidth: 280,
                  }}
                >
                  {enabled
                    ? m.description
                    : 'Configure o caminho nas Configurações para ativar este módulo.'}
                </p>
              </div>
            </button>
          )
        })}
      </div>

      {/* Barra de status do LOGOS */}
      <LogosPanel />
    </div>
  )
}
