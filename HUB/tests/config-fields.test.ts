import { describe, it, expect } from 'vitest'
import { buildConfigSections, parseFieldValue, buildUpdates, HIDDEN_KEYS } from '../src/lib/config-fields'

const SAMPLE = {
  sync_root: 'D:\\eco_root',
  akasha: {
    web_search_backend: 'http://t410:8080',
    marginalia_api_key: '',
    max_per_domain: 5,
    semantic_search: true,
    interest_seeds: ['tech', 'filosofia'],
    personality_prompt: 'voce e a akasha',
    base_url: 'http://localhost:7071',      // plumbing → hidden
    exe_path: 'C:\\...\\iniciar.bat',         // plumbing → hidden
    config_path: 'D:\\...\\.config',          // plumbing → hidden
    bg_processing: { worker_active: true },   // runtime dict → excluded
    incoming_insights: [{ x: 1 }],            // array de objetos → excluded
  },
  hub: {
    syncthing_gui_password: 'segredo',        // secret
    last_git_head: 'abc123',                  // runtime → hidden
    data_path: '',
  },
  hermes: { exe_path: 'x' },                  // só plumbing → seção omitida
}

describe('buildConfigSections', () => {
  const sections = buildConfigSections(SAMPLE as Record<string, unknown>)
  const byName = (n: string) => sections.find(s => s.section === n)

  it('coloca sync_root na seção geral como read-only', () => {
    const geral = byName('')
    expect(geral).toBeTruthy()
    const sr = geral!.fields.find(f => f.key === 'sync_root')
    expect(sr).toMatchObject({ type: 'string', readOnly: true, value: 'D:\\eco_root' })
  })

  it('exclui runtime/plumbing', () => {
    const ak = byName('akasha')!
    const keys = ak.fields.map(f => f.key)
    for (const hidden of ['base_url', 'exe_path', 'config_path', 'bg_processing', 'incoming_insights']) {
      expect(keys).not.toContain(hidden)
    }
    expect([...HIDDEN_KEYS]).toContain('bg_processing')
  })

  it('infere tipos corretamente', () => {
    const ak = byName('akasha')!
    const t = (k: string) => ak.fields.find(f => f.key === k)?.type
    expect(t('web_search_backend')).toBe('string')
    expect(t('marginalia_api_key')).toBe('secret')   // contém api_key
    expect(t('max_per_domain')).toBe('number')
    expect(t('semantic_search')).toBe('boolean')
    expect(t('interest_seeds')).toBe('list')
    expect(byName('hub')!.fields.find(f => f.key === 'syncthing_gui_password')?.type).toBe('secret')
  })

  it('omite seções sem campos editáveis', () => {
    expect(byName('hermes')).toBeUndefined()  // só exe_path (hidden)
  })
})

describe('parseFieldValue', () => {
  it('number', () => expect(parseFieldValue('number', '12')).toBe(12))
  it('boolean', () => { expect(parseFieldValue('boolean', 'true')).toBe(true); expect(parseFieldValue('boolean', 'false')).toBe(false) })
  it('list (uma por linha, ignora vazias)', () =>
    expect(parseFieldValue('list', 'a\n b \n\nc')).toEqual(['a', 'b', 'c']))
  it('string passa direto', () => expect(parseFieldValue('string', 'http://x')).toBe('http://x'))
})

describe('buildUpdates', () => {
  it('agrupa por seção, pula read-only, top-level na raiz', () => {
    const up = buildUpdates([
      { section: 'akasha', key: 'web_search_backend', type: 'string', value: 'http://t410:8080', readOnly: false },
      { section: 'akasha', key: 'max_per_domain', type: 'number', value: 8, readOnly: false },
      { section: '', key: 'sync_root', type: 'string', value: 'X', readOnly: true },   // skip
    ])
    expect(up).toEqual({ akasha: { web_search_backend: 'http://t410:8080', max_per_domain: 8 } })
  })
})
