// ============================================================
//  HUB — Sistema de Temas
//  Três temas: sépia (padrão), claro, escuro.
//  Mecanismo: classes 'light' e 'dark' no <html>.
//  Persiste em localStorage: 'hub_theme'
// ============================================================

export type Theme = 'sepia' | 'light' | 'dark'

const STORAGE_KEY = 'hub_theme'
const CYCLE: Theme[] = ['sepia', 'light', 'dark']

function applyTheme(theme: Theme): void {
  const html = document.documentElement
  html.classList.remove('light', 'dark')
  if (theme === 'light') html.classList.add('light')
  if (theme === 'dark')  html.classList.add('dark')
}

function parseStored(raw: string | null): Theme {
  if (raw === 'light') return 'light'
  if (raw === 'dark')  return 'dark'
  return 'sepia'
}

export function initTheme(): void {
  const theme = parseStored(localStorage.getItem(STORAGE_KEY))
  applyTheme(theme)
}

export function getTheme(): Theme {
  const html = document.documentElement
  if (html.classList.contains('dark'))  return 'dark'
  if (html.classList.contains('light')) return 'light'
  return 'sepia'
}

export function cycleTheme(): Theme {
  const current = getTheme()
  const next = CYCLE[(CYCLE.indexOf(current) + 1) % CYCLE.length]
  applyTheme(next)
  localStorage.setItem(STORAGE_KEY, next)
  return next
}

export const THEME_LABEL: Record<Theme, string> = {
  sepia: 'Sépia',
  light: 'Claro',
  dark:  'Escuro',
}
