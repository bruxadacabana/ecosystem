/* ============================================================
   AETHER — Sistema de Toasts / Notificações
   ============================================================ */

import { useEffect, useRef, useState } from 'react'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface ToastItem {
  id: string
  type: ToastType
  message: string
}

const DISMISS_DELAY: Record<ToastType, number> = {
  success: 3000,
  error:   7000,
  warning: 5000,
  info:    4000,
}

const STYLES: Record<ToastType, React.CSSProperties> = {
  success: { background: '#F0F5EE', borderColor: '#4A6741', color: '#2A4A22' },
  error:   { background: '#F9F2EA', borderColor: '#8B3A2A', color: '#5A1E12' },
  warning: { background: '#F9F5E8', borderColor: '#b8860b', color: '#6B4E00' },
  info:    { background: '#EEF2F9', borderColor: '#2C5F8A', color: '#1A3A5A' },
}

const STYLES_DARK: Record<ToastType, React.CSSProperties> = {
  success: { background: '#162015', borderColor: '#5C8A4E', color: '#8AC880' },
  error:   { background: '#2A1810', borderColor: '#C45A40', color: '#E8A090' },
  warning: { background: '#231C08', borderColor: '#D4A820', color: '#E8C860' },
  info:    { background: '#0E1A28', borderColor: '#4A8ABF', color: '#80B8E8' },
}

// --- Componente individual ---

interface ToastCardProps {
  item: ToastItem
  onDismiss: (id: string) => void
  isDark: boolean
}

function ToastCard({ item, onDismiss, isDark }: ToastCardProps) {
  const style = isDark ? STYLES_DARK[item.type] : STYLES[item.type]

  useEffect(() => {
    const timer = window.setTimeout(
      () => onDismiss(item.id),
      DISMISS_DELAY[item.type],
    )
    return () => window.clearTimeout(timer)
  }, [item.id, item.type, onDismiss])

  return (
    <div
      role="alert"
      aria-live="assertive"
      style={{
        ...style,
        fontFamily: 'var(--font-mono)',
        fontSize: '11px',
        letterSpacing: '0.04em',
        padding: '8px 14px',
        borderRadius: 'var(--radius)',
        border: '1px solid',
        boxShadow: '3px 3px 0 var(--rule)',
        cursor: 'pointer',
        animation: 'toastIn 180ms ease-out both',
        maxWidth: '320px',
        userSelect: 'none',
      }}
      onClick={() => onDismiss(item.id)}
    >
      {item.message}
    </div>
  )
}

// --- Container ---

interface ToastContainerProps {
  toasts: ToastItem[]
  onDismiss: (id: string) => void
}

export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  const isDark = document.documentElement.classList.contains('dark')

  if (toasts.length === 0) return null

  return (
    <div
      aria-label="Notificações"
      style={{
        position: 'fixed',
        bottom: '24px',
        right: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        zIndex: 9999,
      }}
    >
      {toasts.slice(0, 5).map(t => (
        <ToastCard key={t.id} item={t} onDismiss={onDismiss} isDark={isDark} />
      ))}
    </div>
  )
}

// --- Hook ---

let _nextId = 0

export function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const toastsRef = useRef(toasts)
  toastsRef.current = toasts

  function dismiss(id: string) {
    setToasts(prev => prev.filter(t => t.id !== id))
  }

  function show(type: ToastType, message: string) {
    const id = String(++_nextId)
    setToasts(prev => [...prev, { id, type, message }])
  }

  return {
    toasts,
    dismiss,
    success: (msg: string) => show('success', msg),
    error:   (msg: string) => show('error', msg),
    warning: (msg: string) => show('warning', msg),
    info:    (msg: string) => show('info', msg),
  }
}
