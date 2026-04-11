/* ============================================================
   AETHER — TypographyPanel
   Painel flutuante de configurações tipográficas do editor.
   Abre abaixo do botão "T" na topbar.
   ============================================================ */

import { useEffect, useRef, useState } from 'react'
import {
  applyTypography,
  loadTypography,
  saveTypography,
  type TypographySettings,
} from '../lib/typography'

interface SliderProps {
  label: string
  value: number
  min: number
  max: number
  step: number
  display: string
  onChange: (v: number) => void
}

function Slider({ label, value, min, max, step, display, onChange }: SliderProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '11px',
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
          color: 'var(--ink-faint)',
        }}>
          {label}
        </span>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '12px',
          color: 'var(--ink)',
        }}>
          {display}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: '100%', accentColor: 'var(--accent)', cursor: 'pointer' }}
      />
    </div>
  )
}

export function TypographyPanel() {
  const [open, setOpen] = useState(false)
  const [settings, setSettings] = useState<TypographySettings>(loadTypography)
  const panelRef = useRef<HTMLDivElement>(null)
  const btnRef = useRef<HTMLButtonElement>(null)

  // Fechar ao clicar fora
  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (
        panelRef.current && !panelRef.current.contains(e.target as Node) &&
        btnRef.current  && !btnRef.current.contains(e.target as Node)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  function update(patch: Partial<TypographySettings>) {
    const next = { ...settings, ...patch }
    setSettings(next)
    applyTypography(next)
    saveTypography(next)
  }

  function reset() {
    const defaults = { fontSize: 16, lineHeight: 1.75, columnWidth: 680 }
    setSettings(defaults)
    applyTypography(defaults)
    saveTypography(defaults)
  }

  return (
    <div style={{ position: 'relative' }}>
      <button
        ref={btnRef}
        className="btn btn-ghost btn-sm"
        onClick={() => setOpen((v) => !v)}
        title="Tipografia"
        aria-label="Configurações de tipografia"
        aria-expanded={open}
        style={{
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          fontSize: '15px',
          color: open ? 'var(--accent)' : 'var(--ink-ghost)',
          padding: '4px 8px',
          lineHeight: 1,
        }}
      >
        T
      </button>

      {open && (
        <div
          ref={panelRef}
          style={{
            position: 'absolute',
            top: 'calc(100% + 8px)',
            right: 0,
            width: '240px',
            background: 'var(--paper-dark)',
            border: '1px solid var(--rule)',
            borderRadius: 'var(--radius)',
            boxShadow: 'var(--shadow-modal)',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
            zIndex: 100,
            animation: 'fadeIn 0.12s ease both',
          }}
        >
          <Slider
            label="Tamanho"
            value={settings.fontSize}
            min={13}
            max={22}
            step={1}
            display={`${settings.fontSize}px`}
            onChange={(v) => update({ fontSize: v })}
          />
          <Slider
            label="Entrelinhamento"
            value={settings.lineHeight}
            min={1.4}
            max={2.2}
            step={0.05}
            display={settings.lineHeight.toFixed(2)}
            onChange={(v) => update({ lineHeight: v })}
          />
          <Slider
            label="Largura da coluna"
            value={settings.columnWidth}
            min={480}
            max={920}
            step={20}
            display={`${settings.columnWidth}px`}
            onChange={(v) => update({ columnWidth: v })}
          />
          <button
            className="btn btn-ghost btn-sm"
            onClick={reset}
            style={{
              alignSelf: 'flex-end',
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              color: 'var(--ink-ghost)',
              letterSpacing: '0.06em',
            }}
          >
            Restaurar padrões
          </button>
        </div>
      )}
    </div>
  )
}
