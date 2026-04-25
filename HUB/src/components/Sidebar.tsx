/* ============================================================
   HUB — Sidebar
   Barra lateral esquerda fixa com 4 seções de navegação.
   ============================================================ */

import type { HubSection } from '../types'

const SECTIONS: { id: HubSection; symbol: string; label: string }[] = [
  { id: 'home',      symbol: '◎', label: 'Home'    },
  { id: 'logos',     symbol: 'Λ', label: 'LOGOS'   },
  { id: 'atividade', symbol: '≋', label: 'Feed'    },
  { id: 'config',    symbol: '⚙', label: 'Config'  },
]

interface SidebarProps {
  section: HubSection
  onSection: (s: HubSection) => void
}

export function Sidebar({ section, onSection }: SidebarProps) {
  return (
    <div
      style={{
        width: 72,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        borderRight: '1px solid var(--rule)',
        background: 'var(--paper-dark)',
        overflow: 'hidden',
      }}
    >
      {/* Branding */}
      <div
        style={{
          width: '100%',
          padding: '16px 0 18px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderBottom: '1px solid var(--rule)',
          marginBottom: 10,
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontStyle: 'italic',
            fontSize: 19,
            color: 'var(--ink)',
            letterSpacing: '0.02em',
            userSelect: 'none',
          }}
        >
          Hub
        </span>
      </div>

      {/* Section navigation */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
          width: '100%',
          padding: '0 8px',
          flex: 1,
        }}
      >
        {SECTIONS.map(s => {
          const active = section === s.id
          return (
            <button
              key={s.id}
              onClick={() => onSection(s.id)}
              title={s.label}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 4,
                padding: '10px 0',
                width: '100%',
                background: active ? 'var(--rule)' : 'transparent',
                border: 'none',
                borderRadius: 'var(--radius)',
                cursor: 'pointer',
                transition: 'background 140ms ease',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: 15,
                  color: active ? 'var(--accent)' : 'var(--ink-ghost)',
                  transition: 'color 200ms',
                  lineHeight: 1,
                  userSelect: 'none',
                }}
              >
                {s.symbol}
              </span>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 9,
                  letterSpacing: '0.08em',
                  color: active ? 'var(--ink)' : 'var(--ink-ghost)',
                  textTransform: 'uppercase',
                  transition: 'color 200ms',
                  userSelect: 'none',
                }}
              >
                {s.label}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
