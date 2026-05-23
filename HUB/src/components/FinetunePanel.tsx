/* ============================================================
   FinetunePanel — painel de fine-tuning no dashboard do LOGOS.

   Exibe:
     - Modelo fine-tuned atual e versão anterior
     - Data do último ciclo
     - Tamanho do corpus no último treino vs. atual (via finetune_state.json)
     - Progresso do ciclo em andamento (etapa, exemplos gerados)
     - Botão "Iniciar ciclo" (habilitado apenas no PC principal, VRAM ≥ 6 GB)
   ============================================================ */

import { useCallback, useEffect, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { FinetuneState, LogosStatus } from '../types'

interface Props {
  /** Status do LOGOS — usado para verificar hardware_profile e VRAM total */
  logosStatus: LogosStatus | null
}

const POLL_MS = 5_000

function formatDate(iso: string): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('pt-BR', {
      day:    '2-digit',
      month:  '2-digit',
      year:   'numeric',
      hour:   '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function stepLabel(step: string): string {
  const labels: Record<string, string> = {
    'iniciando':         'Iniciando…',
    'gerando_dados':     'Gerando Q&A do corpus…',
    'treinando':         'Treinando modelo…',
    'convertendo':       'Convertendo para GGUF…',
    'concluido':         'Concluído',
  }
  if (step.startsWith('erro:')) return `Erro: ${step.slice(5).trim()}`
  return labels[step] ?? step
}

/** True se o hardware suporta fine-tuning (main_pc com VRAM ≥ 6 GB) */
function canFinetune(status: LogosStatus | null): boolean {
  if (!status) return false
  // main_pc = RX 6600 8GB. laptop = MX150 2GB (insuficiente).
  return status.hardware_profile === 'main_pc'
}

export function FinetunePanel({ logosStatus }: Props) {
  const [state,      setState]      = useState<FinetuneState | null>(null)
  const [triggering, setTriggering] = useState(false)
  const [error,      setError]      = useState<string | null>(null)

  const fetchState = useCallback(() => {
    cmd.logosGetFinetuneState().then(r => {
      if (r.ok) setState(r.data)
    })
  }, [])

  useEffect(() => {
    fetchState()
    const id = setInterval(fetchState, POLL_MS)
    return () => clearInterval(id)
  }, [fetchState])

  const handleTrigger = async () => {
    setTriggering(true)
    setError(null)
    const r = await cmd.logosTriggerFinetune()
    setTriggering(false)
    if (!r.ok) {
      setError(r.error.message)
    } else if (!r.data) {
      setError('Ciclo já em andamento.')
    } else {
      fetchState()
    }
  }

  const running   = state?.running ?? false
  const step      = state?.current_step ?? ''
  const allowed   = canFinetune(logosStatus)

  return (
    <section style={{ marginTop: '1.5rem' }}>
      <h3 style={{ fontSize: '0.78rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-faint)', marginBottom: '0.75rem' }}>
        Fine-Tuning Local
      </h3>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem 1.5rem', fontSize: '0.82rem' }}>
        {/* Modelo atual */}
        <Row label="Modelo atual">
          {state?.current_model
            ? <code style={{ color: 'var(--accent)' }}>{state.current_model}</code>
            : <span style={{ color: 'var(--ink-ghost)' }}>—</span>}
        </Row>

        {/* Versão anterior */}
        <Row label="Versão anterior">
          {state?.prev_model
            ? <code style={{ color: 'var(--ink-light)' }}>{state.prev_model}</code>
            : <span style={{ color: 'var(--ink-ghost)' }}>—</span>}
        </Row>

        {/* Último ciclo */}
        <Row label="Último ciclo">
          <span style={{ color: 'var(--ink-light)' }}>{formatDate(state?.last_cycle_at ?? '')}</span>
        </Row>

        {/* Corpus */}
        <Row label="Corpus no último treino">
          <span style={{ color: 'var(--ink-light)' }}>
            {state?.corpus_chunks_at_last_train
              ? `${state.corpus_chunks_at_last_train.toLocaleString('pt-BR')} chunks`
              : '—'}
          </span>
        </Row>
      </div>

      {/* Progresso do ciclo em andamento */}
      {running && (
        <div style={{
          marginTop: '0.75rem',
          padding: '0.5rem 0.75rem',
          background: 'var(--surface-raise)',
          borderRadius: '6px',
          borderLeft: '2px solid var(--accent)',
          fontSize: '0.82rem',
        }}>
          <span style={{ color: 'var(--accent)', marginRight: '0.5rem' }}>●</span>
          <span style={{ color: 'var(--ink-light)' }}>{stepLabel(step)}</span>
          {(state?.examples_generated ?? 0) > 0 && (
            <span style={{ color: 'var(--ink-faint)', marginLeft: '0.75rem' }}>
              {state!.examples_generated.toLocaleString('pt-BR')} exemplos gerados
            </span>
          )}
        </div>
      )}

      {/* Mensagem de erro */}
      {error && (
        <div style={{ marginTop: '0.5rem', fontSize: '0.78rem', color: 'var(--red, #e05c5c)' }}>
          {error}
        </div>
      )}

      {/* Aviso se hardware incompatível */}
      {!allowed && logosStatus && (
        <div style={{ marginTop: '0.5rem', fontSize: '0.78rem', color: 'var(--ink-faint)' }}>
          Fine-tuning disponível apenas no PC principal (VRAM ≥ 6 GB).
          Hardware atual: {logosStatus.hardware_profile_display}
        </div>
      )}

      {/* Botão */}
      <div style={{ marginTop: '0.75rem' }}>
        <button
          onClick={handleTrigger}
          disabled={!allowed || running || triggering}
          style={{
            fontSize: '0.8rem',
            padding: '0.35rem 0.9rem',
            borderRadius: '5px',
            border: 'none',
            cursor: (!allowed || running || triggering) ? 'not-allowed' : 'pointer',
            background: (!allowed || running || triggering) ? 'var(--surface-raise)' : 'var(--accent)',
            color: (!allowed || running || triggering) ? 'var(--ink-faint)' : '#fff',
            transition: 'background 0.15s',
          }}
        >
          {running ? 'Ciclo em andamento…' : triggering ? 'Iniciando…' : 'Iniciar ciclo'}
        </button>
      </div>
    </section>
  )
}

/* Row helper */
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <span style={{ color: 'var(--ink-faint)' }}>{label}</span>
      <span>{children}</span>
    </>
  )
}
