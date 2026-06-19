// ============================================================
//  HUB — Editor genérico de config: derivação de campos a partir
//  do ecosystem.json. Lógica pura (testável por vitest).
// ============================================================

export type ConfigFieldType = 'string' | 'secret' | 'number' | 'boolean' | 'list'

export interface ConfigField {
  section: string          // ex.: "akasha"; "" para chaves de topo (ex.: sync_root)
  key: string
  type: ConfigFieldType
  value: string | number | boolean | string[]
  readOnly: boolean        // sync_root é read-only aqui (editar via Sync, que deriva paths)
}

export interface ConfigSectionFields {
  section: string
  fields: ConfigField[]
}

// Chaves que NÃO são config do usuário — estado de runtime ou plumbing auto-gerado.
// Nunca aparecem no editor (e o save por merge preserva as que existem no arquivo).
export const HIDDEN_KEYS: ReadonlySet<string> = new Set([
  'bg_processing',
  'incoming_insights',
  'pending_insights',
  'last_git_head',
  'exe_path',
  'base_url',
  'config_path',
])

// Chaves de topo que existem mas são editadas em outro lugar (read-only aqui).
const READONLY_TOP_KEYS: ReadonlySet<string> = new Set(['sync_root'])

function looksSecret(key: string): boolean {
  const k = key.toLowerCase()
  return k.includes('password') || k.includes('secret') || k.includes('token') || k.includes('api_key')
}

function fieldFor(section: string, key: string, value: unknown, readOnly: boolean): ConfigField | null {
  if (HIDDEN_KEYS.has(key)) return null
  if (typeof value === 'boolean') return { section, key, type: 'boolean', value, readOnly }
  if (typeof value === 'number') return { section, key, type: 'number', value, readOnly }
  if (typeof value === 'string') {
    return { section, key, type: looksSecret(key) ? 'secret' : 'string', value, readOnly }
  }
  if (Array.isArray(value)) {
    // Só listas de escalares (strings/números) viram campo; arrays de objetos são ignorados.
    if (value.every(v => typeof v === 'string' || typeof v === 'number')) {
      return { section, key, type: 'list', value: value.map(String), readOnly }
    }
    return null
  }
  // objetos aninhados (dicts) não são editáveis aqui
  return null
}

/**
 * Constrói as seções/campos editáveis a partir do objeto ecosystem.json.
 * - Chaves de topo escalares (ex.: sync_root) vão numa seção "" (geral).
 * - Cada seção-objeto (akasha, kosmos, …) vira uma ConfigSectionFields.
 * - Seções sem campos editáveis são omitidas.
 */
export function buildConfigSections(eco: Record<string, unknown>): ConfigSectionFields[] {
  const out: ConfigSectionFields[] = []

  // Seção "geral" (chaves de topo que não são objetos)
  const topFields: ConfigField[] = []
  for (const [key, value] of Object.entries(eco)) {
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) continue
    const f = fieldFor('', key, value, READONLY_TOP_KEYS.has(key))
    if (f) topFields.push(f)
  }
  if (topFields.length) out.push({ section: '', fields: topFields })

  // Seções por app
  for (const [section, value] of Object.entries(eco)) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) continue
    const fields: ConfigField[] = []
    for (const [key, v] of Object.entries(value as Record<string, unknown>)) {
      const f = fieldFor(section, key, v, false)
      if (f) fields.push(f)
    }
    if (fields.length) out.push({ section, fields })
  }

  return out
}

/** Converte o valor de um input de volta ao tipo certo p/ gravar no ecosystem.json. */
export function parseFieldValue(type: ConfigFieldType, raw: string): string | number | boolean | string[] {
  switch (type) {
    case 'number': {
      const n = Number(raw)
      return Number.isFinite(n) ? n : 0
    }
    case 'boolean':
      return raw === 'true' || raw === '1' || raw === 'on'
    case 'list':
      return raw.split('\n').map(s => s.trim()).filter(Boolean)
    default:
      return raw
  }
}

/** Monta o payload `{section: {key: value}}` para `save_ecosystem_config` (merge no backend). */
export function buildUpdates(fields: ConfigField[]): Record<string, Record<string, unknown>> {
  const updates: Record<string, Record<string, unknown>> = {}
  for (const f of fields) {
    if (f.readOnly) continue
    const sec = f.section || '__top__'
    if (!updates[sec]) updates[sec] = {}
    updates[sec][f.key] = f.value
  }
  // chaves de topo (seção "") vão na raiz do payload, não sob "__top__"
  const top = updates['__top__']
  delete updates['__top__']
  if (top) Object.assign(updates, top)
  return updates
}
