/* ============================================================
   HUB — ConfigSection
   Aba "config": duas sub-abas — "Caminhos & apps" (SetupView, UI dedicada)
   e "Todas as configs" (ConfigView, editor genérico do ecosystem.json).
   ============================================================ */

import { useState } from 'react'
import { SetupView } from './SetupView'
import { ConfigView } from './ConfigView'

interface Props {
  onBack: () => void
  onSaved?: () => void
}

type Tab = 'paths' | 'all'

export function ConfigSection({ onBack, onSaved }: Props) {
  const [tab, setTab] = useState<Tab>('paths')

  const tabBtn = (id: Tab, label: string) => (
    <button
      onClick={() => setTab(id)}
      style={{
        fontFamily: 'var(--font-mono)', fontSize: 11, padding: '5px 12px',
        background: tab === id ? 'var(--accent)' : 'transparent',
        color: tab === id ? 'var(--paper-dark)' : 'var(--ink-ghost)',
        border: tab === id ? 'none' : '1px solid var(--rule)',
        borderRadius: 4, cursor: 'pointer',
      }}
    >{label}</button>
  )

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ display: 'flex', gap: 8, padding: '10px 24px 0' }}>
        {tabBtn('paths', 'Caminhos & apps')}
        {tabBtn('all', 'Todas as configs')}
      </div>
      <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
        {tab === 'paths'
          ? <SetupView onBack={onBack} onSaved={onSaved} />
          : <ConfigView />}
      </div>
    </div>
  )
}
