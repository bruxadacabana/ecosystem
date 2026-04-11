import React, { useEffect, useState } from 'react'

interface Props {
  symbol?: string
  variant?: 'red' | 'gold'
  dismissAfter?: number
  onDismiss?: () => void
}

export const WaxSeal: React.FC<Props> = ({
  symbol = '✓',
  variant = 'red',
  dismissAfter = 1800,
  onDismiss,
}) => {
  const [visible, setVisible] = useState(true)

  useEffect(() => {
    const t = setTimeout(() => {
      setVisible(false)
      onDismiss?.()
    }, dismissAfter)
    return () => clearTimeout(t)
  }, [dismissAfter, onDismiss])

  if (!visible) return null

  return (
    <div
      className={`wax-seal${variant === 'gold' ? ' wax-seal-gold' : ''}`}
      aria-hidden
    >
      {symbol}
    </div>
  )
}
