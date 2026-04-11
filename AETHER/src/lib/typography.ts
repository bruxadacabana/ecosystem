/* ============================================================
   AETHER — Tipografia do Editor
   Controla fonte, entrelinhamento e largura da coluna.
   Persiste em localStorage. Aplica via CSS custom properties.
   ============================================================ */

export interface TypographySettings {
  fontSize:    number   // px, 13–22
  lineHeight:  number   // 1.4–2.2
  columnWidth: number   // px, 480–920
}

const DEFAULTS: TypographySettings = {
  fontSize:    16,
  lineHeight:  1.75,
  columnWidth: 680,
}

const KEY = 'aether_typography'

export function loadTypography(): TypographySettings {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { ...DEFAULTS }
    const parsed = JSON.parse(raw) as Partial<TypographySettings>
    return {
      fontSize:    clamp(parsed.fontSize    ?? DEFAULTS.fontSize,    13, 22),
      lineHeight:  clamp(parsed.lineHeight  ?? DEFAULTS.lineHeight,  1.4, 2.2),
      columnWidth: clamp(parsed.columnWidth ?? DEFAULTS.columnWidth, 480, 920),
    }
  } catch {
    return { ...DEFAULTS }
  }
}

export function saveTypography(s: TypographySettings): void {
  localStorage.setItem(KEY, JSON.stringify(s))
}

export function applyTypography(s: TypographySettings): void {
  const root = document.documentElement
  root.style.setProperty('--editor-font-size',    `${s.fontSize}px`)
  root.style.setProperty('--editor-line-height',  String(s.lineHeight))
  root.style.setProperty('--editor-col-width',    `${s.columnWidth}px`)
}

export function initTypography(): void {
  applyTypography(loadTypography())
}

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v))
}
