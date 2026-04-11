/**
 * OGMA App Settings — data/settings.json
 * Preferências do utilizador separadas do banco de dados.
 */

import fs from 'fs'
import { SETTINGS } from './paths'
import { createLogger } from './logger'

const log = createLogger('settings')

// ── Tipos ─────────────────────────────────────────────────────────────────────

export interface StoredLocation {
  city:         string
  admin1:       string
  country:      string
  country_code: string
  latitude:     number
  longitude:    number
  hemisphere:   'north' | 'south'
  timezone:     string
}

export interface AppSettings {
  theme?:           'dark' | 'day'
  location?:        StoredLocation | null
  dashboard_order?: string[]
  widget_sizes?:    Record<string, string>
  hidden_widgets?:  string[]
  ui_font_size?:    'small' | 'normal' | 'large'
}

// ── Cache em memória ───────────────────────────────────────────────────────────

let cache: AppSettings = {}

// ── API pública ───────────────────────────────────────────────────────────────

export function initSettings(): void {
  try {
    const raw = fs.readFileSync(SETTINGS, 'utf-8')
    cache = JSON.parse(raw) as AppSettings
    log.info('Settings carregadas', { keys: Object.keys(cache) })
  } catch {
    cache = {}
    persistSettings()
    log.info('Settings inicializadas (ficheiro novo)')
  }
}

export function getSetting<K extends keyof AppSettings>(key: K): AppSettings[K] {
  return cache[key]
}

export function setSetting<K extends keyof AppSettings>(key: K, value: AppSettings[K]): void {
  cache[key] = value
  persistSettings()
}

export function getAllSettings(): AppSettings {
  return { ...cache }
}

// ── Persistência ──────────────────────────────────────────────────────────────

function persistSettings(): void {
  try {
    fs.writeFileSync(SETTINGS, JSON.stringify(cache, null, 2), 'utf-8')
  } catch (e) {
    log.error('Falha ao gravar settings', { error: String(e) })
  }
}
