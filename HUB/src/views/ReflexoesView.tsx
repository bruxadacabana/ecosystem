/* ============================================================
   HUB — ReflexoesView
   Aba dedicada à "vida interior" das IAs: lista as reflexões, insights e
   conexões que a Akasha e a Mnemosyne guardam na personal_memory, em seções
   separadas por IA. Somente leitura — o feedback acontece nos pop-ups das IAs.
   Reaproveita o MemoryList compartilhado (mesmo viewer do Monitoramento).
   ============================================================ */

import { MemoryList } from '../components/MemoryViewer'

export function ReflexoesView() {
  return (
    <div style={s.wrapper}>
      <div style={s.header}>
        <h1 style={s.title}>Reflexões</h1>
        <p style={s.subtitle}>
          A vida interior das IAs — o que a Akasha e a Mnemosyne refletem, conectam e
          guardam ao longo do tempo. Somente leitura; o feedback acontece nos pop-ups delas.
        </p>
      </div>

      <div style={s.sections}>
        <section style={s.aiSection}>
          <h2 style={s.aiTitle}>AKASHA</h2>
          <MemoryList app="akasha" readOnly />
        </section>

        <section style={s.aiSection}>
          <h2 style={s.aiTitle}>Mnemosyne</h2>
          <MemoryList app="mnemosyne" readOnly />
        </section>
      </div>
    </div>
  )
}

const s = {
  wrapper: {
    height: '100%', overflowY: 'auto', padding: '24px 28px', boxSizing: 'border-box',
  } as const,
  header: {
    marginBottom: 20, borderBottom: '1px solid var(--rule)', paddingBottom: 14,
  } as const,
  title: {
    fontFamily: 'var(--font-mono)', fontSize: 22, letterSpacing: '0.04em',
    color: 'var(--ink)', margin: 0,
  } as const,
  subtitle: {
    fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-ghost)',
    margin: '6px 0 0', lineHeight: 1.5, maxWidth: 620,
  } as const,
  sections: {
    display: 'flex', gap: 24, alignItems: 'flex-start', flexWrap: 'wrap',
  } as const,
  aiSection: {
    flex: '1 1 360px', minWidth: 320, background: 'var(--paper)',
    border: '1px solid var(--rule)', borderRadius: 6, padding: '14px 16px',
  } as const,
  aiTitle: {
    fontFamily: 'var(--font-mono)', fontSize: 13, letterSpacing: '0.12em',
    color: 'var(--accent)', margin: '0 0 10px', textTransform: 'uppercase',
  } as const,
}
