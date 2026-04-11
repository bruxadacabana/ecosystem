import React from 'react'

const SYMBOLS = ['☿', '♄', '☉', '⊕', '☾', '✦'] as const
type AlchemySymbol = typeof SYMBOLS[number]

interface Props {
  symbol?: AlchemySymbol
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

export const AlchemyLoader: React.FC<Props> = ({
  symbol = '☿',
  size = 'md',
  className = '',
}) => (
  <span
    className={[
      'alchemy-loader',
      size === 'sm' ? 'alchemy-loader-sm' : size === 'lg' ? 'alchemy-loader-lg' : '',
      className,
    ].filter(Boolean).join(' ')}
    role="status"
    aria-label="Carregando"
  >
    {symbol}
  </span>
)

export { SYMBOLS as ALCHEMY_SYMBOLS }
export type { AlchemySymbol }
