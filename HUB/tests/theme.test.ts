/**
 * Testes unitários para src/lib/theme.ts
 *
 * Mocka localStorage e document.documentElement explicitamente, pois
 * o HUB é um app Tauri (não executa em browser real nos testes).
 * Cobre:
 *   - parseStored (via comportamento de initTheme)
 *   - getTheme: detecta tema pelas classes CSS
 *   - cycleTheme: avança sépia → light → dark → sépia
 *   - THEME_LABEL: rótulos dos temas
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

// ── Mocks de DOM e localStorage ──────────────────────────────────────────────

const _store: Record<string, string> = {}

const localStorageMock = {
  getItem:    (k: string) => _store[k] ?? null,
  setItem:    (k: string, v: string) => { _store[k] = v },
  removeItem: (k: string) => { delete _store[k] },
  clear:      () => { for (const k in _store) delete _store[k] },
}

const classList = {
  _classes: new Set<string>(),
  add:      (...cls: string[]) => cls.forEach(c => classList._classes.add(c)),
  remove:   (...cls: string[]) => cls.forEach(c => classList._classes.delete(c)),
  contains: (c: string) => classList._classes.has(c),
}

const documentMock = {
  documentElement: { classList },
}

vi.stubGlobal('localStorage', localStorageMock)
vi.stubGlobal('document', documentMock)

// ── Reset entre testes ────────────────────────────────────────────────────────

beforeEach(() => {
  localStorageMock.clear()
  classList._classes.clear()
  vi.resetModules()
})

// ── Helpers ───────────────────────────────────────────────────────────────────

async function getThemeModule() {
  return await import('../src/lib/theme')
}


// ---------------------------------------------------------------------------
// initTheme
// ---------------------------------------------------------------------------

describe('initTheme', () => {
  it('sem valor salvo não adiciona classe ao html', async () => {
    const { initTheme } = await getThemeModule()
    initTheme()
    expect(classList._classes.has('dark')).toBe(false)
    expect(classList._classes.has('light')).toBe(false)
  })

  it('valor salvo "dark" adiciona classe dark', async () => {
    localStorageMock.setItem('hub_theme', 'dark')
    const { initTheme } = await getThemeModule()
    initTheme()
    expect(classList._classes.has('dark')).toBe(true)
  })

  it('valor salvo "light" adiciona classe light', async () => {
    localStorageMock.setItem('hub_theme', 'light')
    const { initTheme } = await getThemeModule()
    initTheme()
    expect(classList._classes.has('light')).toBe(true)
  })

  it('valor inválido no localStorage usa sépia (sem classes)', async () => {
    localStorageMock.setItem('hub_theme', 'banana')
    const { initTheme } = await getThemeModule()
    initTheme()
    expect(classList._classes.has('dark')).toBe(false)
    expect(classList._classes.has('light')).toBe(false)
  })
})


// ---------------------------------------------------------------------------
// getTheme
// ---------------------------------------------------------------------------

describe('getTheme', () => {
  it('sem classes retorna sépia', async () => {
    const { getTheme } = await getThemeModule()
    expect(getTheme()).toBe('sepia')
  })

  it('classe dark retorna dark', async () => {
    classList._classes.add('dark')
    const { getTheme } = await getThemeModule()
    expect(getTheme()).toBe('dark')
  })

  it('classe light retorna light', async () => {
    classList._classes.add('light')
    const { getTheme } = await getThemeModule()
    expect(getTheme()).toBe('light')
  })
})


// ---------------------------------------------------------------------------
// cycleTheme
// ---------------------------------------------------------------------------

describe('cycleTheme', () => {
  it('de sépia avança para light', async () => {
    const { cycleTheme } = await getThemeModule()
    expect(cycleTheme()).toBe('light')
  })

  it('de light avança para dark', async () => {
    classList._classes.add('light')
    const { cycleTheme } = await getThemeModule()
    expect(cycleTheme()).toBe('dark')
  })

  it('de dark volta para sépia', async () => {
    classList._classes.add('dark')
    const { cycleTheme } = await getThemeModule()
    expect(cycleTheme()).toBe('sepia')
  })

  it('persiste no localStorage', async () => {
    const { cycleTheme } = await getThemeModule()
    cycleTheme()
    expect(localStorageMock.getItem('hub_theme')).toBe('light')
  })

  it('três ciclos volta ao estado original (sépia)', async () => {
    const { cycleTheme, getTheme } = await getThemeModule()
    cycleTheme()
    cycleTheme()
    cycleTheme()
    expect(getTheme()).toBe('sepia')
  })
})


// ---------------------------------------------------------------------------
// THEME_LABEL
// ---------------------------------------------------------------------------

describe('THEME_LABEL', () => {
  it('contém rótulo para sépia', async () => {
    const { THEME_LABEL } = await getThemeModule()
    expect(THEME_LABEL['sepia']).toBeTruthy()
  })

  it('contém rótulo para dark', async () => {
    const { THEME_LABEL } = await getThemeModule()
    expect(THEME_LABEL['dark']).toBeTruthy()
  })

  it('contém rótulo para light', async () => {
    const { THEME_LABEL } = await getThemeModule()
    expect(THEME_LABEL['light']).toBeTruthy()
  })
})
