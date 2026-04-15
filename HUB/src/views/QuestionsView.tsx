/* ============================================================
   HUB — QuestionsView
   Chat com qualquer modelo Ollama local. Streaming token a token.
   Histórico de sessão em estado local — sem persistência.
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import { listModels, streamChat } from '../lib/ollama'
import type { ChatMessage } from '../lib/ollama'

interface QuestionsViewProps {
  onBack: () => void
}

interface DisplayMessage {
  role: 'user' | 'assistant'
  content: string
}

export function QuestionsView({ onBack }: QuestionsViewProps) {
  const [models, setModels]         = useState<string[]>([])
  const [model, setModel]           = useState('')
  const [messages, setMessages]     = useState<DisplayMessage[]>([])
  const [input, setInput]           = useState('')
  const [streaming, setStreaming]   = useState(false)
  const [streamBuf, setStreamBuf]   = useState('')  // tokens chegando
  const [offline, setOffline]       = useState(false)
  const [loadingModels, setLoadingModels] = useState(true)

  const bottomRef   = useRef<HTMLDivElement>(null)
  const inputRef    = useRef<HTMLTextAreaElement>(null)
  const abortRef    = useRef(false)  // sinaliza cancelamento

  // ----------------------------------------------------------
  //  Carrega modelos
  // ----------------------------------------------------------

  async function fetchModels() {
    setLoadingModels(true)
    setOffline(false)
    try {
      const list = await listModels()
      setModels(list)
      if (list.length > 0) setModel(m => m || list[0])
    } catch {
      setOffline(true)
    } finally {
      setLoadingModels(false)
    }
  }

  useEffect(() => { fetchModels() }, [])

  // ----------------------------------------------------------
  //  Auto-scroll
  // ----------------------------------------------------------

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamBuf])

  // ----------------------------------------------------------
  //  Enviar mensagem
  // ----------------------------------------------------------

  async function handleSend() {
    const text = input.trim()
    if (!text || streaming || !model) return

    const userMsg: DisplayMessage = { role: 'user', content: text }
    const history: ChatMessage[] = [
      ...messages.map(m => ({ role: m.role, content: m.content })),
      { role: 'user', content: text },
    ]

    setMessages(prev => [...prev, userMsg])
    setInput('')
    setStreaming(true)
    setStreamBuf('')
    abortRef.current = false

    let accumulated = ''

    try {
      for await (const token of streamChat(model, history)) {
        if (abortRef.current) break
        accumulated += token
        setStreamBuf(accumulated)
      }
    } catch (err) {
      accumulated += '\n\n*(Erro ao receber resposta.)*'
      setStreamBuf(accumulated)
    }

    // Consolida o buffer como mensagem do assistente
    setMessages(prev => [...prev, { role: 'assistant', content: accumulated }])
    setStreamBuf('')
    setStreaming(false)

    // Foca no input
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleStop() {
    abortRef.current = true
  }

  function handleClear() {
    setMessages([])
    setStreamBuf('')
    setStreaming(false)
    abortRef.current = true
  }

  // ----------------------------------------------------------
  //  Render
  // ----------------------------------------------------------

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--paper)' }}>
      {/* Topbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
        padding: '10px 20px', borderBottom: '1px solid var(--rule)', flexShrink: 0,
      }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack}>← Hub</button>
        <h1 style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 20, color: 'var(--ink)' }}>
          Perguntas
        </h1>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Seletor de modelo */}
          {!offline && models.length > 0 && (
            <select
              value={model}
              onChange={e => setModel(e.target.value)}
              disabled={streaming}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 10,
                background: 'var(--paper)', color: 'var(--ink)',
                border: '1px solid var(--rule)', borderRadius: 2, padding: '3px 6px',
                cursor: streaming ? 'not-allowed' : 'pointer',
              }}
            >
              {models.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          )}

          {/* Limpar histórico */}
          {messages.length > 0 && (
            <button
              onClick={handleClear}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em',
                textTransform: 'uppercase', padding: '3px 8px',
                border: '1px solid var(--rule)', borderRadius: 2,
                background: 'transparent', color: 'var(--ink-ghost)', cursor: 'pointer',
              }}
            >
              Limpar
            </button>
          )}
        </div>
      </div>

      {/* Banner offline */}
      {offline && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '10px 20px', background: 'rgba(139,58,42,0.08)',
          borderBottom: '1px solid rgba(139,58,42,0.2)', flexShrink: 0,
        }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#8B3A2A' }}>
            Ollama não encontrado em localhost:11434
          </span>
          <button
            onClick={fetchModels}
            disabled={loadingModels}
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em',
              textTransform: 'uppercase', padding: '3px 8px',
              border: '1px solid #8B3A2A', borderRadius: 2,
              background: 'transparent', color: '#8B3A2A', cursor: 'pointer',
            }}
          >
            {loadingModels ? 'Verificando…' : 'Tentar novamente'}
          </button>
        </div>
      )}

      {/* Área de mensagens */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px 8px' }}>
        {messages.length === 0 && !streaming && !offline && (
          <EmptyState model={model} loadingModels={loadingModels} />
        )}

        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}

        {/* Mensagem em streaming */}
        {streaming && streamBuf && (
          <MessageBubble message={{ role: 'assistant', content: streamBuf }} streaming />
        )}

        {/* Indicador "digitando" antes dos primeiros tokens */}
        {streaming && !streamBuf && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 0', marginBottom: 8 }}>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em',
              textTransform: 'uppercase', color: 'var(--ink-ghost)',
            }}>
              Gerando
            </span>
            <TypingDots />
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: '12px 20px 16px',
        borderTop: '1px solid var(--rule)', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={streaming || offline || !model}
            placeholder={
              offline        ? 'Ollama offline'       :
              loadingModels  ? 'Carregando modelos…'  :
              !model         ? 'Nenhum modelo disponível' :
                               'Escreva sua pergunta… (Enter para enviar, Shift+Enter para quebrar linha)'
            }
            rows={3}
            style={{
              flex: 1, resize: 'none',
              fontFamily: 'var(--font-mono)', fontSize: 12,
              background: 'var(--paper)', color: 'var(--ink)',
              border: '1px solid var(--rule)', borderRadius: 2,
              padding: '8px 10px', lineHeight: 1.5,
              opacity: (streaming || offline || !model) ? 0.5 : 1,
            }}
          />

          {streaming ? (
            <button
              onClick={handleStop}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em',
                textTransform: 'uppercase', padding: '8px 14px',
                border: '1px solid var(--rule)', borderRadius: 2,
                background: 'var(--paper-dark)', color: 'var(--ink)', cursor: 'pointer',
                alignSelf: 'stretch',
              }}
            >
              ◼ Parar
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim() || !model || offline}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em',
                textTransform: 'uppercase', padding: '8px 14px',
                border: 'none', borderRadius: 2,
                background: (!input.trim() || !model || offline) ? 'var(--paper-dark)' : 'var(--accent)',
                color: (!input.trim() || !model || offline) ? 'var(--ink-ghost)' : 'var(--paper)',
                cursor: (!input.trim() || !model || offline) ? 'not-allowed' : 'pointer',
                transition: 'background 120ms, color 120ms',
                alignSelf: 'stretch',
              }}
            >
              Enviar
            </button>
          )}
        </div>
        <p style={{
          fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-ghost)',
          marginTop: 6, letterSpacing: '0.04em',
        }}>
          Histórico apenas desta sessão — não é salvo.
        </p>
      </div>
    </div>
  )
}

// ----------------------------------------------------------
//  MessageBubble
// ----------------------------------------------------------

interface MessageBubbleProps {
  message: { role: 'user' | 'assistant'; content: string }
  streaming?: boolean
}

function MessageBubble({ message, streaming }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <div style={{
      display: 'flex',
      justifyContent: isUser ? 'flex-end' : 'flex-start',
      marginBottom: 14,
    }}>
      <div style={{
        maxWidth: '78%',
        background: isUser ? 'var(--accent)' : 'var(--paper-dark)',
        color: isUser ? 'var(--paper)' : 'var(--ink)',
        borderRadius: 2,
        padding: '10px 14px',
        boxShadow: '2px 2px 0 var(--paper-darker)',
        position: 'relative',
      }}>
        {/* Rótulo de remetente */}
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 8, letterSpacing: '0.14em',
          textTransform: 'uppercase', marginBottom: 5,
          opacity: 0.65,
        }}>
          {isUser ? 'Você' : 'Assistente'}
        </div>

        {/* Conteúdo */}
        <div style={{
          fontFamily: 'var(--font-body)', fontSize: 13, lineHeight: 1.7,
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
        }}>
          {message.content}
        </div>

        {/* Cursor piscando durante streaming */}
        {streaming && (
          <span style={{
            display: 'inline-block', width: 2, height: '1em',
            background: 'var(--ink)', marginLeft: 2, verticalAlign: 'text-bottom',
            animation: 'blink 0.9s step-end infinite',
          }} />
        )}
      </div>

      <style>{`
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
      `}</style>
    </div>
  )
}

// ----------------------------------------------------------
//  EmptyState
// ----------------------------------------------------------

function EmptyState({ model, loadingModels }: { model: string; loadingModels: boolean }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', height: '100%', gap: 10, paddingBottom: 60,
      minHeight: 200,
    }}>
      <p style={{
        fontFamily: 'var(--font-display)', fontStyle: 'italic',
        fontSize: 22, color: 'var(--ink)', opacity: 0.4,
      }}>
        {loadingModels ? 'Conectando ao Ollama…' : 'Faça uma pergunta'}
      </p>
      {model && !loadingModels && (
        <p style={{
          fontFamily: 'var(--font-mono)', fontSize: 10,
          color: 'var(--ink-ghost)', letterSpacing: '0.06em',
        }}>
          modelo: {model}
        </p>
      )}
    </div>
  )
}

// ----------------------------------------------------------
//  TypingDots
// ----------------------------------------------------------

function TypingDots() {
  return (
    <>
      <span style={{ animation: 'blink 1s step-end infinite', animationDelay: '0ms',   color: 'var(--ink-ghost)' }}>·</span>
      <span style={{ animation: 'blink 1s step-end infinite', animationDelay: '200ms', color: 'var(--ink-ghost)' }}>·</span>
      <span style={{ animation: 'blink 1s step-end infinite', animationDelay: '400ms', color: 'var(--ink-ghost)' }}>·</span>
    </>
  )
}
