import React, { useState, useEffect } from 'react'
import { useAppStore } from '../../store/useAppStore'
import { fromIpc } from '../../types/errors'
import { IconPicker } from '../../components/UI/IconPicker'
import { StoredLocation } from '../../types'
import './SettingsView.css'

const db = () => (window as any).db

interface Props {
  dark: boolean
  onToggleTheme: () => void
  fontSizeValue: 'small' | 'normal' | 'large'
  onFontSize: (val: 'small' | 'normal' | 'large') => void
}

interface GeoResult {
  name:         string
  admin1:       string
  country:      string
  country_code: string
  latitude:     number
  longitude:    number
  timezone:     string
}

export function SettingsView({ dark, onToggleTheme, fontSizeValue, onFontSize }: Props) {
  const { workspace, loadWorkspace, pushToast } = useAppStore()

  const ink2 = dark ? '#8A7A62' : '#9C8E7A'

  const [name,        setName]        = useState('')
  const [icon,        setIcon]        = useState('')
  const [accentColor, setAccentColor] = useState('#b8860b')
  const [saved,       setSaved]       = useState(false)
  const [saving,      setSaving]      = useState(false)

  // Planner
  const [dailyHours,      setDailyHours]      = useState('4')
  const [dailyHoursSaved, setDailyHoursSaved] = useState(false)
  const [perDayHours,     setPerDayHours]     = useState<Record<number,string>>({0:'0',1:'4',2:'4',3:'4',4:'4',5:'4',6:'0'})
  const [perDaySaved,     setPerDaySaved]     = useState(false)

  // Sincronização
  const [syncing,    setSyncing]    = useState(false)
  const [syncResult, setSyncResult] = useState<'ok' | 'error' | null>(null)

  const handleSync = async () => {
    setSyncing(true)
    setSyncResult(null)
    try {
      const r = await db().sync.now()
      setSyncing(false)
      if (r?.ok) {
        setSyncResult('ok')
        pushToast({ kind: 'success', title: 'Sincronizado com Turso.' })
      } else {
        setSyncResult('error')
        pushToast({ kind: 'error', title: r?.error ?? 'Falha na sincronização' })
      }
    } catch (e: any) {
      setSyncing(false)
      setSyncResult('error')
      pushToast({ kind: 'error', title: e?.message ?? 'Falha na sincronização' })
    }
    setTimeout(() => setSyncResult(null), 3000)
  }

  useEffect(() => {
    fromIpc<any>(() => db().config.get('planner_daily_hours'), 'getDailyHours')
      .then(r => { if (r.isOk() && r.value?.value) setDailyHours(r.value.value) })
    fromIpc<any>(() => db().config.get('planner_daily_hours_per_day'), 'getPerDayHours')
      .then(r => {
        if (r.isOk() && r.value?.value) {
          try {
            const parsed = JSON.parse(r.value.value)
            setPerDayHours(Object.fromEntries(Object.entries(parsed).map(([k, v]) => [Number(k), String(v)])) as Record<number,string>)
          } catch {}
        }
      })
  }, [])

  const saveDailyHours = async () => {
    const val = Math.min(24, Math.max(0.5, parseFloat(dailyHours) || 4))
    await fromIpc(() => db().config.set('planner_daily_hours', String(val)), 'setDailyHours')
    setDailyHours(String(val))
    setDailyHoursSaved(true)
    setTimeout(() => setDailyHoursSaved(false), 2000)
  }

  const savePerDayHours = async () => {
    const map: Record<number,number> = {}
    for (let i = 0; i < 7; i++) map[i] = Math.min(24, Math.max(0, parseFloat(perDayHours[i] ?? '') || 0))
    await fromIpc(() => db().config.set('planner_daily_hours_per_day', JSON.stringify(map)), 'setPerDayHours')
    setPerDaySaved(true)
    setTimeout(() => setPerDaySaved(false), 2000)
  }

  // Localização
  const [locQuery,     setLocQuery]     = useState('')
  const [locResults,   setLocResults]   = useState<GeoResult[]>([])
  const [locSearching, setLocSearching] = useState(false)
  const [savedLoc,     setSavedLoc]     = useState<StoredLocation | null>(null)

  // 1. LER do Banco de Dados ao iniciar
  useEffect(() => {
    fromIpc<any>(() => db().config.get('user_location'), 'getLocation').then(r => {
      if (r.isOk() && r.value) {
        try { setSavedLoc(JSON.parse(r.value?.value)) } catch {}
      }
    })
  }, [])

  const searchLocation = async () => {
    if (!locQuery.trim()) return
    setLocSearching(true)
    setLocResults([])
    try {
      const res  = await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(locQuery.trim())}&count=6&language=pt&format=json`)
      const data = await res.json()
      setLocResults(data.results ?? [])
    } catch {
      pushToast({ kind: 'error', title: 'Erro na busca', detail: 'Verifique sua conexão.' })
    }
    setLocSearching(false)
  }

  // 2. GRAVAR no Banco de Dados
  const saveLocation = async (r: GeoResult) => {
    const loc: StoredLocation = {
      city:         r.name,
      admin1:       r.admin1 ?? '',
      country:      r.country,
      country_code: r.country_code,
      latitude:     r.latitude,
      longitude:    r.longitude,
      hemisphere:   r.latitude >= 0 ? 'north' : 'south',
      timezone:     r.timezone ?? 'UTC',
    }
    await fromIpc(() => db().config.set('user_location', JSON.stringify(loc)), 'setLocation')
    setSavedLoc(loc)
    setLocResults([])
    setLocQuery('')
  }

  // 3. APAGAR do Banco de Dados
  const clearLocation = async () => {
    await fromIpc(() => db().config.set('user_location', ''), 'clearLocation')
    setSavedLoc(null)
  }


  // Sincronizar com store
  useEffect(() => {
    if (!workspace) return
    setName(workspace.name)
    setIcon(workspace.icon ?? '✦')
    setAccentColor(workspace.accent_color ?? '#b8860b')
  }, [workspace])

  const handleSave = async () => {
    if (!workspace) return
    setSaving(true)
    const result = await fromIpc<unknown>(
      () => db().workspace.update({
        id:           workspace.id,
        name:         name.trim() || 'Meu Workspace',
        icon:         icon.trim() || '✦',
        accent_color: accentColor,
      }),
      'updateWorkspace',
    )
    setSaving(false)
    if (result.isErr()) {
      pushToast({ kind: 'error', title: 'Erro ao guardar workspace', detail: result.error.message })
      return
    }
    await loadWorkspace()
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const dirty = workspace
    && (name !== workspace.name
     || icon !== (workspace.icon ?? '✦')
     || accentColor !== (workspace.accent_color ?? '#b8860b'))

  return (
    <div className="settings-root">
      <div className="settings-header">
        <h1 className="settings-title">Configurações</h1>
        <div className="settings-subtitle">OGMA · WORKSPACE</div>
      </div>

      {/* ── Workspace ── */}
      <div className="settings-section">
        <div className="settings-section-label">Workspace</div>
        <div className="settings-card">

          <div className="settings-row">
            <span className="settings-row-label">Nome</span>
            <div className="settings-row-control">
              <input
                className="settings-input"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Meu Workspace"
                maxLength={64}
              />
            </div>
          </div>

          <div className="settings-row">
            <span className="settings-row-label">Ícone</span>
            <div className="settings-row-control">
              <IconPicker value={icon} onChange={setIcon} dark={dark} size={22} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-faint)' }}>
                clique para escolher
              </span>
            </div>
          </div>

          <div className="settings-row">
            <span className="settings-row-label">Cor de destaque</span>
            <div className="settings-row-control">
              <div className="settings-color-wrapper">
                <div className="settings-color-swatch" style={{ background: accentColor }} />
                <input
                  type="color" className="settings-color-input"
                  value={accentColor} onChange={e => setAccentColor(e.target.value)}
                  title="Escolher cor"
                />
              </div>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-faint)', letterSpacing: '0.06em' }}>
                {accentColor}
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-faint)', fontStyle: 'italic', marginLeft: 4 }}>
                (aplicado na próxima sessão)
              </span>
            </div>
          </div>

        </div>

        <div className="settings-save-row" style={{ marginTop: 10 }}>
          {saved && <span className="settings-saved-msg" style={{ marginRight: 12 }}>✓ Guardado</span>}
          <button
            className="btn btn-sm"
            style={{ borderColor: dirty ? 'var(--accent)' : 'var(--rule)', color: dirty ? 'var(--accent)' : 'var(--ink-faint)' }}
            onClick={handleSave}
            disabled={!dirty || saving}
          >
            {saving ? 'A guardar…' : 'Guardar alterações'}
          </button>
        </div>
      </div>

      {/* ── Planner ── */}
      <div className="settings-section">
        <div className="settings-section-label">Planner</div>
        <div className="settings-card">
          <div className="settings-row">
            <span className="settings-row-label">Capacidade diária</span>
            <div className="settings-row-control" style={{ gap: 8 }}>
              <input
                type="number" min="0.5" max="24" step="0.5"
                className="settings-input" value={dailyHours}
                onChange={e => setDailyHours(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && saveDailyHours()}
                style={{ width: 70 }}
              />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-faint)' }}>
                horas/dia
              </span>
              <button className="btn btn-sm" onClick={saveDailyHours} style={{ marginLeft: 4 }}>
                {dailyHoursSaved ? '✓ Guardado' : 'Guardar'}
              </button>
            </div>
          </div>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-faint)', marginTop: 8, fontStyle: 'italic' }}>
            Limite padrão quando a capacidade por dia não está configurada abaixo.
          </p>
          <div className="settings-row" style={{ flexDirection:'column', alignItems:'flex-start', gap:6, marginTop: 14 }}>
            <span className="settings-row-label">Capacidade por dia</span>
            <div style={{ display:'flex', gap:6, flexWrap:'wrap', marginTop:4 }}>
              {(['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'] as const).map((label, dow) => (
                <div key={dow} style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:2 }}>
                  <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--ink-faint)' }}>{label}</span>
                  <input type="number" min="0" max="24" step="0.5"
                    className="settings-input" style={{ width:52 }}
                    value={perDayHours[dow] ?? '0'}
                    onChange={e => setPerDayHours(prev => ({ ...prev, [dow]: e.target.value }))}
                  />
                </div>
              ))}
              <button className="btn btn-sm" onClick={savePerDayHours} style={{ alignSelf:'flex-end' }}>
                {perDaySaved ? '✓ Guardado' : 'Guardar'}
              </button>
            </div>
            <p style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'var(--ink-faint)', fontStyle:'italic', margin:0 }}>
              0 horas = não agendar nesse dia. Substitui o limite padrão acima.
            </p>
          </div>
        </div>
      </div>

      {/* ── Localização ── */}
      <div className="settings-section">
        <div className="settings-section-label">Localização</div>
        <div className="settings-card">

          {savedLoc && (
            <>
              <div className="settings-about-row">
                <span className="settings-about-key">Cidade</span>
                <span className="settings-about-val">
                  {savedLoc.city}{savedLoc.admin1 ? `, ${savedLoc.admin1}` : ''}, {savedLoc.country}
                </span>
              </div>
              <div className="settings-about-row" style={{ marginBottom: 14 }}>
                <span className="settings-about-key">Hemisfério</span>
                <span className="settings-about-val">
                  {savedLoc.hemisphere === 'north' ? '☽ Norte' : '☾ Sul'}
                  {' '}·{' '}{savedLoc.latitude.toFixed(2)}°, {savedLoc.longitude.toFixed(2)}°
                </span>
              </div>
            </>
          )}

          <div className="settings-row">
            <span className="settings-row-label">Buscar cidade</span>
            <div className="settings-row-control" style={{ gap: 8 }}>
              <input
                className="settings-input" value={locQuery}
                onChange={e => setLocQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && searchLocation()}
                placeholder="Ex: São Paulo, Belo Horizonte…"
                style={{ flex: 1 }}
              />
              <button
                className="btn btn-sm" onClick={searchLocation}
                disabled={locSearching || !locQuery.trim()} style={{ flexShrink: 0 }}
              >
                {locSearching ? '…' : 'Buscar'}
              </button>
            </div>
          </div>

          {locResults.length > 0 && (
            <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 4 }}>
              {locResults.map((r, i) => (
                <button
                  key={i} className="btn btn-sm"
                  style={{ textAlign: 'left', justifyContent: 'flex-start', gap: 8 }}
                  onClick={() => saveLocation(r)}
                >
                  <span>{r.name}{r.admin1 ? `, ${r.admin1}` : ''}, {r.country}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-faint)', marginLeft: 'auto' }}>
                    {r.latitude.toFixed(2)}°, {r.longitude.toFixed(2)}°
                    {' · '}{r.latitude >= 0 ? 'Norte' : 'Sul'}
                  </span>
                </button>
              ))}
            </div>
          )}

          {savedLoc && (
            <button
              className="btn btn-ghost btn-sm"
              style={{ color: 'var(--ink-faint)', marginTop: 10 }}
              onClick={clearLocation}
            >
              Remover localização
            </button>
          )}

          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-faint)', marginTop: 12, fontStyle: 'italic' }}>
            Usado na Roda do Ano (hemisfério) e na previsão do tempo.
          </p>
        </div>
      </div>


      {/* ── Interface ── */}
      <div className="settings-section">
        <div className="settings-section-label">Interface</div>
        <div className="settings-card">
          <div style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 10, letterSpacing: '0.08em', color: ink2, textTransform: 'uppercase', fontFamily: 'var(--font-mono)', display: 'block', marginBottom: 8 }}>
              Tamanho da fonte
            </label>
            <div style={{ display: 'flex', gap: 6 }}>
              {(['small', 'normal', 'large'] as const).map(size => (
                <button
                  key={size}
                  className={`btn${fontSizeValue === size ? ' btn-primary' : ''}`}
                  onClick={() => onFontSize(size)}
                  style={{ fontSize: size === 'small' ? 10 : size === 'large' ? 14 : 12 }}
                >
                  {size === 'small' ? 'Pequena' : size === 'normal' ? 'Normal' : 'Grande'}
                </button>
              ))}
            </div>
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: ink2, marginTop: 8, fontStyle: 'italic' }}>
              Texto de exemplo — {fontSizeValue === 'small' ? 'fonte compacta (11px)' : fontSizeValue === 'large' ? 'fonte ampliada (15px)' : 'fonte padrão (13px)'}
            </p>
          </div>
        </div>
      </div>

      {/* ── Aparência ── */}
      <div className="settings-section">
        <div className="settings-section-label">Aparência</div>
        <div className="settings-card">
          <div className="settings-row">
            <span className="settings-row-label">Tema</span>
            <div className="settings-row-control">
              <div className="settings-theme-toggle">
                <button
                  className={`settings-theme-btn${!dark ? ' settings-theme-btn--active' : ''}`}
                  onClick={() => dark && onToggleTheme()}
                >☀ Claro</button>
                <button
                  className={`settings-theme-btn${dark ? ' settings-theme-btn--active' : ''}`}
                  onClick={() => !dark && onToggleTheme()}
                >☽ Escuro</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Atalhos ── */}
      <div className="settings-section">
        <div className="settings-section-label">Atalhos de teclado</div>
        <div className="settings-card">
          {[
            ['Busca global',        'Ctrl + K'],
            ['Alternar tema',       '☽ / ☀ na barra superior'],
            ['Fechar modal / sair', 'Esc'],
            ['Navegar resultados',  '↑ ↓'],
            ['Abrir selecionado',   '↵ Enter'],
          ].map(([action, key]) => (
            <div className="settings-about-row" key={action}>
              <span className="settings-about-key">{action}</span>
              <span className="settings-about-val">{key}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Sincronização ── */}
      <div className="settings-section">
        <div className="settings-section-label">Sincronização</div>
        <div className="settings-card">
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-faint)', marginBottom: 12 }}>
            Força uma sincronização manual com o Turso Cloud. Útil caso a sincronização automática tenha falhado no arranque.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button
              className="btn btn-sm"
              onClick={handleSync}
              disabled={syncing}
            >
              {syncing ? '↻ Sincronizando...' : '↻ Sincronizar agora'}
            </button>
            {syncResult === 'ok'    && <span style={{ color: 'var(--accent)', fontSize: 12 }}>✓ Concluído</span>}
            {syncResult === 'error' && <span style={{ color: '#c0392b',       fontSize: 12 }}>✗ Falhou</span>}
          </div>
        </div>
      </div>

      {/* ── Sobre ── */}
      <div className="settings-section">
        <div className="settings-section-label">Sobre</div>
        <div className="settings-card">
          {[
            ['Aplicativo',    'OGMA'],
            ['Versão',        '0.1.0'],
            ['Plataforma',    'Electron + React'],
            ['Base de dados', 'SQLite (better-sqlite3)'],
          ].map(([k, v]) => (
            <div className="settings-about-row" key={k}>
              <span className="settings-about-key">{k}</span>
              <span className="settings-about-val">{v}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
