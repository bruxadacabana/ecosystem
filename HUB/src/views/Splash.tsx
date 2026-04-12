/* ============================================================
   HUB — Splash Screen
   Typewriter animado + CosmosLayer.
   ============================================================ */

import { useEffect, useState } from 'react'
import { CosmosLayer } from '../components/CosmosLayer'

interface SplashProps {
  onDone: () => void
}

const STEPS = [
  'Iniciando HUB...',
  'Lendo ecossistema...',
  'Pronto.',
]

const STEP_DELAY = 600 // ms por passo

export function Splash({ onDone }: SplashProps) {
  const [stepIndex, setStepIndex] = useState(0)
  const [visible, setVisible] = useState(true)

  useEffect(() => {
    if (stepIndex < STEPS.length - 1) {
      const t = window.setTimeout(() => setStepIndex(i => i + 1), STEP_DELAY)
      return () => window.clearTimeout(t)
    } else {
      // Último passo — aguarda um pouco e transita
      const t = window.setTimeout(() => {
        setVisible(false)
        window.setTimeout(onDone, 300)
      }, 800)
      return () => window.clearTimeout(t)
    }
  }, [stepIndex, onDone])

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--paper)',
        opacity: visible ? 1 : 0,
        transition: 'opacity 300ms ease',
        zIndex: 100,
      }}
    >
      <div style={{ position: 'relative', width: 520, height: 340 }}>
        <CosmosLayer seed={1} density="high" animated width={520} height={340} />

        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 16,
          }}
        >
          {/* Título */}
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontStyle: 'italic',
              fontSize: 52,
              color: 'var(--ink)',
              letterSpacing: '0.04em',
            }}
          >
            HUB
          </h1>

          {/* Status typewriter */}
          <p
            key={stepIndex}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--ink-ghost)',
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              animation: 'fadeIn 200ms ease-out both',
            }}
          >
            {STEPS[stepIndex]}
          </p>
        </div>
      </div>
    </div>
  )
}
