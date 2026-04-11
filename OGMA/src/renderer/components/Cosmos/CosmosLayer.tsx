import React, { useMemo } from 'react'

interface Props {
  width: number
  height: number
  seed?: string
  density?: 'low' | 'medium' | 'high'
  dark?: boolean
  style?: React.CSSProperties
}

function seededRng(seed: string) {
  let h = 0
  for (let i = 0; i < seed.length; i++) {
    h = (Math.imul(31, h) + seed.charCodeAt(i)) | 0
  }
  return () => {
    h ^= h << 13; h ^= h >> 17; h ^= h << 5
    return ((h >>> 0) / 4294967296)
  }
}

function starPath(cx: number, cy: number, r: number, rng: () => number): string {
  const points: string[] = []
  for (let i = 0; i < 10; i++) {
    const angle = (Math.PI * i) / 5 - Math.PI / 2
    const radius = i % 2 === 0
      ? r * (1 + rng() * 0.2 - 0.1)
      : r * 0.42 * (1 + rng() * 0.25 - 0.125)
    const x = cx + radius * Math.cos(angle + rng() * 0.12 - 0.06)
    const y = cy + radius * Math.sin(angle + rng() * 0.12 - 0.06)
    points.push(`${x.toFixed(2)},${y.toFixed(2)}`)
  }
  return `M ${points.join(' L ')} Z`
}

export const CosmosLayer: React.FC<Props> = ({
  width, height, seed = 'cosmos', density = 'medium', dark = false, style
}) => {
  const svg = useMemo(() => {
    const rng = seededRng(seed)
    const d = { low: 1, medium: 2, high: 3 }[density]
    const starColor   = dark ? '#C8B99A' : '#5C4E3A'
    const starDim     = dark ? '#8A7A62' : '#9C8E7A'
    const nebulaColor = dark ? '#A07840' : '#7A5C2E'
    const lineColor   = dark ? '#6b5535' : '#9C8E7A'
    const accentColor = dark ? '#D4A820' : '#b8860b'

    const elements: React.ReactElement[] = []
    const key = (prefix: string, i: number) => `${prefix}${i}`

    // Nebulosas
    for (let i = 0; i < d; i++) {
      const cx = rng() * width * 0.8 + width * 0.1
      const cy = rng() * height * 0.8 + height * 0.1
      const rx = (rng() * 0.2 + 0.12) * width
      const ry = (rng() * 0.15 + 0.08) * height
      const op = (rng() * 0.04 + 0.03).toFixed(3)
      const fid = `neb${seed}${i}`.replace(/[^a-z0-9]/gi, '')
      elements.push(
        <g key={key('neb', i)}>
          <defs>
            <filter id={fid}>
              <feGaussianBlur stdDeviation={rx * 0.35} />
            </filter>
          </defs>
          <ellipse cx={cx} cy={cy} rx={rx} ry={ry}
            fill={nebulaColor} opacity={op} filter={`url(#${fid})`} />
        </g>
      )
    }

    // Estrelas
    const nStars = 4 + d * 5
    const sizes  = [4, 6, 8, 12, 16]
    for (let i = 0; i < nStars; i++) {
      const x   = rng() * (width  - 20) + 10
      const y   = rng() * (height - 20) + 10
      const r   = sizes[Math.floor(rng() * 3)]
      const rot = rng() * 60 - 30
      const op  = (rng() * 0.28 + 0.12).toFixed(2)
      const col = rng() > 0.3 ? starColor : starDim
      elements.push(
        <path key={key('star', i)}
          d={starPath(x, y, r, rng)}
          fill={col} opacity={op}
          transform={`rotate(${rot.toFixed(1)},${x.toFixed(1)},${y.toFixed(1)})`} />
      )
    }

    // Constelação
    if (d >= 2) {
      const n = 3 + d
      const pts = Array.from({ length: n }, () => [
        rng() * (width - 20) + 10,
        rng() * (height - 20) + 10,
      ])
      for (let i = 0; i < n - 1; i++) {
        elements.push(
          <line key={key('cl', i)}
            x1={pts[i][0]} y1={pts[i][1]} x2={pts[i+1][0]} y2={pts[i+1][1]}
            stroke={lineColor} strokeWidth={0.7}
            strokeDasharray="2,4" opacity={0.22} />
        )
      }
      for (let i = 0; i < n; i++) {
        elements.push(
          <path key={key('cs', i)}
            d={starPath(pts[i][0], pts[i][1], 4, rng)}
            fill={starColor} opacity={0.32} />
        )
      }
    }

    // Cometa
    if (d >= 2) {
      const cx = rng() * width * 0.4 + width * 0.55
      const cy = rng() * height * 0.3 + height * 0.05
      const ang = rng() * 30 - 50
      const rad = (ang * Math.PI) / 180
      for (let i = 0; i < 3; i++) {
        const len = 14 + i * 10
        elements.push(
          <line key={key('cmt', i)}
            x1={cx} y1={cy}
            x2={(cx - Math.cos(rad) * len).toFixed(1)}
            y2={(cy - Math.sin(rad) * len).toFixed(1)}
            stroke={starColor} strokeWidth={(0.9 - i * 0.25).toFixed(2)}
            opacity={(0.38 - i * 0.1).toFixed(2)} />
        )
      }
      elements.push(
        <ellipse key="cmt-body"
          cx={cx} cy={cy} rx={3.5} ry={1.5}
          fill={accentColor} opacity={0.5}
          transform={`rotate(${ang},${cx},${cy})`} />
      )
    }

    // Lua crescente
    if (d >= 2) {
      const mx = rng() * width * 0.3 + width * 0.05
      const my = rng() * height * 0.5 + height * 0.4
      const mr = 9
      elements.push(
        <g key="moon" opacity={0.26}>
          <circle cx={mx} cy={my} r={mr} fill={starColor} />
          <circle cx={mx + mr * 0.55} cy={my} r={mr * 0.8}
            fill={dark ? '#12161E' : '#F5F0E8'} />
        </g>
      )
    }

    // Planeta
    if (d >= 3) {
      const px = rng() * width * 0.3 + width * 0.65
      const py = rng() * height * 0.3 + height * 0.6
      const pr = 8
      elements.push(
        <g key="planet" opacity={0.22}>
          <ellipse cx={px} cy={py} rx={pr * 1.9} ry={pr * 0.35}
            fill="none" stroke={starDim} strokeWidth={0.8} />
          <circle cx={px} cy={py} r={pr} fill={starDim} />
        </g>
      )
    }

    return elements
  }, [width, height, seed, density, dark])

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={width} height={height}
      viewBox={`0 0 ${width} ${height}`}
      style={{
        position: 'absolute',
        top: 0, left: 0,
        pointerEvents: 'none',
        overflow: 'hidden',
        ...style,
      }}
      aria-hidden
    >
      {svg}
    </svg>
  )
}
