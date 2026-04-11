import React, { Component, ErrorInfo } from 'react'

interface Props {
  children:  React.ReactNode
  dark?:     boolean
  fallback?: React.ReactNode
}

interface State {
  error:    Error | null
  errorInfo: ErrorInfo | null
}

/**
 * ErrorBoundary — captura erros de renderização React e exibe uma tela de
 * recuperação em vez de um crash silencioso.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo })

    // Enviar ao logger do main process, se disponível
    try {
      const db = (window as any).db
      if (db?.log?.renderer) {
        db.log.renderer({
          level:   'error',
          module:  'ErrorBoundary',
          message: error.message,
          data:    { stack: error.stack?.slice(0, 800), componentStack: errorInfo.componentStack?.slice(0, 400) },
        })
      }
    } catch { /* não quebrar no handler de erro */ }
  }

  handleReset = () => {
    this.setState({ error: null, errorInfo: null })
  }

  render() {
    const { error, errorInfo } = this.state
    const { children, fallback, dark } = this.props

    if (!error) return children

    if (fallback) return fallback

    const ink    = dark ? '#E8DFC8' : '#2C2416'
    const ink2   = dark ? '#8A7A62' : '#9C8E7A'
    const border = dark ? '#3A3020' : '#C4B9A8'
    const cardBg = dark ? '#211D16' : '#EDE7D9'
    const bg     = dark ? '#1A1610' : '#F5F0E8'
    const ribbon = dark ? '#C45A40' : '#8B3A2A'

    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', height: '100%', padding: '40px 24px',
        background: bg, gap: 16, textAlign: 'center',
      }}>
        <span style={{ fontSize: 36, color: ribbon }}>✕</span>

        <h2 style={{
          fontFamily: 'var(--font-display, "IM Fell English", Georgia, serif)',
          fontStyle: 'italic', fontWeight: 'normal', fontSize: 20,
          color: ink, margin: 0,
        }}>
          Algo correu mal
        </h2>

        <p style={{ fontSize: 12, color: ink2, maxWidth: 380, lineHeight: 1.6, margin: 0 }}>
          Ocorreu um erro inesperado nesta secção. Podes tentar recarregar o componente
          ou reiniciar a aplicação se o problema persistir.
        </p>

        <div style={{
          background: cardBg, border: `1px solid ${border}`, borderRadius: 2,
          padding: '10px 14px', maxWidth: 440, width: '100%', textAlign: 'left',
        }}>
          <p style={{
            fontFamily: 'var(--font-mono, "Special Elite", monospace)',
            fontSize: 11, color: ribbon, margin: '0 0 4px', letterSpacing: '0.04em',
          }}>
            {error.message}
          </p>
          {error.stack && (
            <pre style={{
              fontFamily: 'Courier Prime, Courier New, monospace',
              fontSize: 9, color: ink2, margin: 0,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              maxHeight: 120, overflow: 'auto',
            }}>
              {error.stack.slice(0, 600)}
            </pre>
          )}
        </div>

        <button
          onClick={this.handleReset}
          style={{
            fontFamily: 'var(--font-mono, "Special Elite", monospace)',
            fontSize: 11, letterSpacing: '0.08em',
            padding: '6px 16px', cursor: 'pointer',
            background: 'transparent', border: `1px solid ${border}`,
            borderRadius: 2, color: ink2,
          }}
        >
          Tentar novamente
        </button>
      </div>
    )
  }
}
