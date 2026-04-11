/* ============================================================
   AETHER — Splash Screen
   Carta de apresentação do app. Typewriter reveal + CosmosLayer.
   ============================================================ */

import { useEffect, useState } from 'react'
import { CosmosLayer } from './CosmosLayer'

interface SplashProps {
  onDone: () => void
}

const LOADING_STEPS = [
  'Iniciando AETHER...',
  'Abrindo vault...',
  'Preparando mundos...',
  'Pronto.',
]

const STEP_DELAY = 900   // ms entre cada mensagem
const CHAR_DELAY = 30    // ms entre cada caractere (typewriter)
const DONE_HOLD  = 500   // ms após "Pronto." antes de fechar

function useTypewriter(text: string): string {
  const [displayed, setDisplayed] = useState('')

  useEffect(() => {
    setDisplayed('')
    let i = 0
    const interval = window.setInterval(() => {
      i++
      setDisplayed(text.slice(0, i))
      if (i >= text.length) window.clearInterval(interval)
    }, CHAR_DELAY)
    return () => window.clearInterval(interval)
  }, [text])

  return displayed
}

export function Splash({ onDone }: SplashProps) {
  const [stepIndex, setStepIndex] = useState(0)
  const [visible, setVisible]     = useState(true)
  const currentText = LOADING_STEPS[stepIndex] ?? ''
  const displayed   = useTypewriter(currentText)

  useEffect(() => {
    if (stepIndex >= LOADING_STEPS.length - 1) {
      const t = window.setTimeout(() => {
        setVisible(false)
        window.setTimeout(onDone, 550)
      }, DONE_HOLD + currentText.length * CHAR_DELAY)
      return () => window.clearTimeout(t)
    }

    const t = window.setTimeout(
      () => setStepIndex(i => i + 1),
      STEP_DELAY + currentText.length * CHAR_DELAY,
    )
    return () => window.clearTimeout(t)
  }, [stepIndex, currentText.length, onDone])

  return (
    <div
      aria-label="Carregando AETHER"
      role="status"
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--paper)',
        zIndex: 9999,
        opacity: visible ? 1 : 0,
        transition: 'opacity 550ms ease',
      }}
    >
      {/* Card */}
      <div
        style={{
          position: 'relative',
          width: '520px',
          height: '340px',
          background: 'var(--paper)',
          border: '1px solid var(--rule)',
          borderRadius: 'var(--radius)',
          boxShadow: '8px 8px 0 rgba(44,36,22,0.3)',
          overflow: 'hidden',
          animation: 'paperFall 0.3s ease-out both',
        }}
      >
        {/* Cosmos de fundo */}
        <CosmosLayer seed={42} density="high" animated={true} width={520} height={340} />

        {/* Linha vermelha de margem */}
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

        {/* Conteúdo */}
        <div
          style={{
            position: 'relative',
            zIndex: 2,
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
            padding: '32px',
          }}
        >
          {/* Nome */}
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontStyle: 'italic',
              fontWeight: 'normal',
              fontSize: '68px',
              letterSpacing: '0.06em',
              color: 'var(--ink)',
              lineHeight: 1,
              margin: 0,
            }}
          >
            AETHER
          </h1>

          {/* Subtítulo */}
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '9px',
              textTransform: 'uppercase',
              letterSpacing: '0.22em',
              color: 'var(--ink-faint)',
              margin: 0,
            }}
          >
            FORJA DE MUNDOS
          </p>

          {/* Divisor */}
          <div
            aria-hidden="true"
            style={{
              width: '120px',
              height: '1px',
              background: 'var(--rule)',
              margin: '4px 0',
            }}
          />

          {/* Status — typewriter */}
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              letterSpacing: '0.04em',
              color: 'var(--ink-light)',
              minHeight: '18px',
              margin: 0,
            }}
          >
            {displayed}
            {displayed.length < currentText.length && (
              <span
                aria-hidden="true"
                style={{ animation: 'blink 0.6s step-end infinite' }}
              >
                _
              </span>
            )}
          </p>

          {/* Loading dots — visíveis só enquanto não é "Pronto." */}
          {stepIndex < LOADING_STEPS.length - 1 && (
            <p
              aria-hidden="true"
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '18px',
                letterSpacing: '0.5em',
                color: 'var(--ink-ghost)',
                margin: 0,
                animation: 'blink 1.2s ease infinite',
              }}
            >
              · · ·
            </p>
          )}
        </div>

        {/* Versão */}
        <span
          aria-hidden="true"
          style={{
            position: 'absolute',
            bottom: '12px',
            right: '16px',
            fontFamily: 'var(--font-mono)',
            fontSize: '9px',
            letterSpacing: '0.06em',
            color: 'var(--ink-ghost)',
            zIndex: 2,
          }}
        >
          v0.1.0
        </span>
      </div>
    </div>
  )
}
