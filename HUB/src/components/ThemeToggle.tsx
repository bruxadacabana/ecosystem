/* ============================================================
   HUB — ThemeToggle
   Botão que cicla entre os três temas: Sépia → Claro → Escuro.
   ============================================================ */

import { useState } from 'react'
import { cycleTheme, getTheme, THEME_LABEL } from '../lib/theme'

export function ThemeToggle() {
  const [theme, setTheme] = useState(getTheme)

  function handleClick() {
    const next = cycleTheme()
    setTheme(next)
  }

  return (
    <button
      className="btn btn-ghost btn-sm"
      onClick={handleClick}
      title={`Tema atual: ${THEME_LABEL[theme]} — clique para alternar`}
      aria-label={`Alternar tema (atual: ${THEME_LABEL[theme]})`}
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: '11px',
        letterSpacing: '0.1em',
        color: 'var(--ink-ghost)',
        padding: '4px 8px',
      }}
    >
      {THEME_LABEL[theme]}
    </button>
  )
}
