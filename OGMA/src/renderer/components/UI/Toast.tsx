import React, { useEffect, useRef } from 'react'
import { useAppStore } from '../../store/useAppStore'
import type { Toast } from '../../store/useAppStore'
import './Toast.css'

// ── Ícones por tipo ────────────────────────────────────────────────────────────

const ICONS: Record<Toast['kind'], string> = {
  error:   '✕',
  success: '✓',
  warning: '⚠',
  info:    'ℹ',
}

// TTL padrão em ms por tipo
const DEFAULT_TTL: Record<Toast['kind'], number> = {
  error:   7000,
  success: 3000,
  warning: 5000,
  info:    4000,
}

// ── Componente individual ──────────────────────────────────────────────────────

function ToastItem({ toast }: { toast: Toast }) {
  const dismissToast = useAppStore(s => s.dismissToast)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const ttl = toast.ttl ?? DEFAULT_TTL[toast.kind]

  useEffect(() => {
    if (ttl > 0) {
      timerRef.current = setTimeout(() => dismissToast(toast.id), ttl)
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [toast.id, ttl, dismissToast])

  return (
    <div className={`toast toast--${toast.kind}`} role="alert" aria-live="polite">
      <span className="toast__icon">{ICONS[toast.kind]}</span>
      <div className="toast__body">
        <span className="toast__title">{toast.title}</span>
        {toast.detail && <span className="toast__detail">{toast.detail}</span>}
      </div>
      <button
        className="toast__close"
        onClick={() => dismissToast(toast.id)}
        aria-label="Fechar notificação"
      >
        ×
      </button>
    </div>
  )
}

// ── Container (colocar no root do App) ────────────────────────────────────────

export function ToastContainer() {
  const toasts = useAppStore(s => s.toasts)
  if (toasts.length === 0) return null

  return (
    <div className="toast-container" aria-label="Notificações">
      {toasts.slice(-5).map(t => (
        <ToastItem key={t.id} toast={t} />
      ))}
    </div>
  )
}
