/* ============================================================
   HUB — MonitoramentoView
   Painel de processamento em background dos apps do ecossistema.
   Lê campos bg_processing do ecosystem.json a cada 5s.
   ============================================================ */

import { useEffect, useState } from 'react'
import * as cmd from '../lib/tauri'
import type { EcosystemConfig } from '../types'

// ── Tipos locais ──────────────────────────────────────────────

interface AkashaBg {
  knowledge_extraction: number
  worker_active:        boolean
}

interface MnemosyneBg {
  indexing:      boolean
  files_pending: number
  current_file:  string | null
}

// ── Componente auxiliar: linha de status ─────────────────────

function StatusRow({
  label,
  value,
  dim = false,
}: {
  label: string
  value: React.ReactNode
  dim?: boolean
}) {
  return (
    <div
      style={{
        display:        'flex',
        justifyContent: 'space-between',
        alignItems:     'center',
        padding:        '6px 0',
        borderBottom:   '1px solid var(--rule)',
        opacity:        dim ? 0.55 : 1,
      }}
    >
      <span
        style={{
          fontFamily:    'var(--font-mono)',
          fontSize:      11,
          color:         'var(--ink-ghost)',
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize:   12,
          color:      'var(--ink)',
        }}
      >
        {value}
      </span>
    </div>
  )
}

// ── Componente de card de app ────────────────────────────────

function AppBlock({
  sigla,
  active,
  children,
}: {
  sigla: string
  active: boolean
  children: React.ReactNode
}) {
  return (
    <div
      style={{
        background:   'var(--paper-dark)',
        border:       `1px solid ${active ? 'var(--accent)' : 'var(--rule)'}`,
        borderRadius: 'var(--radius)',
        padding:      '14px 18px',
        transition:   'border-color 300ms ease',
      }}
    >
      <div
        style={{
          display:        'flex',
          alignItems:     'center',
          gap:            8,
          marginBottom:   12,
          paddingBottom:  8,
          borderBottom:   '1px solid var(--rule)',
        }}
      >
        <span
          style={{
            width:        8,
            height:       8,
            borderRadius: '50%',
            background:   active ? 'var(--accent)' : 'var(--ink-ghost)',
            flexShrink:   0,
            opacity:      active ? 1 : 0.4,
            transition:   'background 300ms',
          }}
        />
        <span
          style={{
            fontFamily:    'var(--font-display)',
            fontStyle:     'italic',
            fontSize:      15,
            color:         'var(--ink)',
            letterSpacing: '0.02em',
          }}
        >
          {sigla}
        </span>
      </div>
      {children}
    </div>
  )
}

// ── View principal ───────────────────────────────────────────

export function MonitoramentoView() {
  const [eco,       setEco]       = useState<EcosystemConfig | null>(null)
  const [lastPoll,  setLastPoll]  = useState<Date | null>(null)

  async function poll() {
    const result = await cmd.readEcosystemConfig()
    if (result.ok) {
      setEco(result.data as EcosystemConfig)
      setLastPoll(new Date())
    }
  }

  useEffect(() => {
    poll()
    const id = setInterval(poll, 5000)
    return () => clearInterval(id)
  }, [])

  const akashaBg:    AkashaBg    | undefined = (eco?.akasha as any)?.bg_processing
  const mnemosyne:   MnemosyneBg | undefined = (eco?.mnemosyne as any)?.bg_processing

  const akashaActive    = akashaBg?.worker_active   ?? false
  const mnemosyneActive = mnemosyne?.indexing         ?? false

  return (
    <div
      style={{
        flex:           1,
        display:        'flex',
        flexDirection:  'column',
        padding:        '24px 28px',
        gap:            20,
        overflowY:      'auto',
      }}
    >
      {/* Cabeçalho */}
      <div
        style={{
          display:        'flex',
          alignItems:     'baseline',
          justifyContent: 'space-between',
          marginBottom:   4,
        }}
      >
        <span
          style={{
            fontFamily:    'var(--font-display)',
            fontStyle:     'italic',
            fontSize:      18,
            color:         'var(--ink)',
            letterSpacing: '0.02em',
          }}
        >
          ⬡ Monitoramento
        </span>
        {lastPoll && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize:   10,
              color:      'var(--ink-ghost)',
              opacity:    0.6,
            }}
          >
            atualizado {lastPoll.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
        )}
      </div>

      {/* AKASHA */}
      <AppBlock sigla="AKASHA" active={akashaActive}>
        <StatusRow
          label="extração de conhecimento"
          value={
            akashaBg
              ? akashaBg.knowledge_extraction > 0
                ? `${akashaBg.knowledge_extraction} na fila`
                : 'fila vazia'
              : '—'
          }
          dim={!akashaBg || akashaBg.knowledge_extraction === 0}
        />
        <StatusRow
          label="worker"
          value={akashaBg ? (akashaActive ? 'ativo' : 'parado') : '—'}
          dim={!akashaActive}
        />
      </AppBlock>

      {/* Mnemosyne */}
      <AppBlock sigla="Mnemosyne" active={mnemosyneActive}>
        <StatusRow
          label="indexação"
          value={
            mnemosyne
              ? mnemosyne.indexing
                ? `em andamento — ${mnemosyne.files_pending} restante${mnemosyne.files_pending === 1 ? '' : 's'}`
                : 'ociosa'
              : '—'
          }
          dim={!mnemosyne?.indexing}
        />
        {mnemosyne?.indexing && mnemosyne.current_file && (
          <StatusRow
            label="arquivo atual"
            value={
              <span
                style={{
                  maxWidth:     200,
                  overflow:     'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace:   'nowrap',
                  display:      'block',
                }}
                title={mnemosyne.current_file}
              >
                {mnemosyne.current_file.split(/[\\/]/).pop()}
              </span>
            }
          />
        )}
      </AppBlock>

      {/* Nota de rodapé */}
      {!eco && (
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize:   11,
            color:      'var(--ink-ghost)',
            opacity:    0.5,
            textAlign:  'center',
            marginTop:  24,
          }}
        >
          Aguardando leitura do ecosystem.json…
        </p>
      )}
    </div>
  )
}
