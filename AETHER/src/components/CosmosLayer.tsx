/* ============================================================
   AETHER — CosmosLayer
   SVG procedural determinístico baseado em seed.
   Mesmo seed = mesmo cosmos. Diferenciais do AETHER:
   - Labels mitológicos nas constelações
   - Nebulosas com etherPulse animado
   ============================================================ */

type Density = 'low' | 'medium' | 'high'

interface CosmosLayerProps {
  seed: number
  density?: Density
  animated?: boolean
  width?: number
  height?: number
  className?: string
}

// PRNG determinístico baseado no seed (mulberry32)
function makePrng(seed: number): () => number {
  let s = seed
  return () => {
    s |= 0
    s = s + 0x6d2b79f5 | 0
    let t = Math.imul(s ^ s >>> 15, 1 | s)
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t
    return ((t ^ t >>> 14) >>> 0) / 4294967296
  }
}

// Gera pontos de uma estrela de N pontas
function starPath(
  cx: number,
  cy: number,
  outerR: number,
  innerR: number,
  points: number,
  rotation: number,
): string {
  const step = Math.PI / points
  let path = ''
  for (let i = 0; i < points * 2; i++) {
    const r = i % 2 === 0 ? outerR : innerR
    const angle = i * step + rotation
    const x = cx + r * Math.cos(angle)
    const y = cy + r * Math.sin(angle)
    path += (i === 0 ? 'M' : 'L') + `${x.toFixed(2)},${y.toFixed(2)}`
  }
  return path + 'Z'
}

const CONSTELLATION_NAMES = [
  'Órion', 'Cassiopeia', 'Perseu', 'Andrômeda', 'Pegasus',
  'Aquila', 'Lyra', 'Cygnus', 'Hercules', 'Draco',
  'Boötes', 'Virgo', 'Scorpius', 'Sagitarius', 'Gemini',
]

const DENSITY_CONFIG = {
  low:    { nebulae: 1, stars: 9,  constPoints: 0, hasComet: false, hasMoon: false, hasPlanet: false },
  medium: { nebulae: 2, stars: 14, constPoints: 5, hasComet: true,  hasMoon: true,  hasPlanet: false },
  high:   { nebulae: 3, stars: 19, constPoints: 6, hasComet: true,  hasMoon: true,  hasPlanet: true  },
}

export function CosmosLayer({
  seed,
  density = 'medium',
  animated = true,
  width = 520,
  height = 340,
  className = '',
}: CosmosLayerProps) {
  const rng = makePrng(seed)
  const cfg = DENSITY_CONFIG[density]

  const filterId = `cosmos-noise-${seed}`
  // --- Nebulosas ---
  const nebulae = Array.from({ length: cfg.nebulae }, (_, i) => ({
    cx: rng() * width,
    cy: rng() * height,
    rx: 60 + rng() * 80,
    ry: 40 + rng() * 60,
    opacity: 0.03 + rng() * 0.04,
    delay: i * 2.5,
  }))

  // --- Estrelas (10 pontas) ---
  const stars = Array.from({ length: cfg.stars }, () => {
    const baseR = 1.8 + rng() * 2.4
    return {
      cx: rng() * width,
      cy: rng() * height,
      outerR: baseR * (0.9 + rng() * 0.2),
      innerR: baseR * 0.4,
      rotation: (rng() - 0.5) * (Math.PI / 3),
      opacity: 0.12 + rng() * 0.28,
    }
  })

  // --- Constelação ---
  const constPoints = cfg.constPoints > 0
    ? Array.from({ length: cfg.constPoints }, () => ({
        x: 40 + rng() * (width - 80),
        y: 40 + rng() * (height - 80),
      }))
    : []

  const constName = cfg.constPoints > 0
    ? CONSTELLATION_NAMES[Math.floor(rng() * CONSTELLATION_NAMES.length)]
    : ''

  const constLabelX = constPoints.length > 0
    ? constPoints.reduce((s, p) => s + p.x, 0) / constPoints.length
    : 0
  const constLabelY = constPoints.length > 0
    ? Math.min(...constPoints.map(p => p.y)) - 8
    : 0

  // --- Cometa ---
  const cometX = rng() * (width * 0.6) + width * 0.2
  const cometY = rng() * (height * 0.4) + height * 0.1
  const cometAngle = -30 + rng() * 20

  // --- Lua crescente ---
  const moonX = 30 + rng() * (width - 60)
  const moonY = 20 + rng() * (height * 0.4)
  const moonR = 10 + rng() * 6

  // --- Planeta ---
  const planetX = 40 + rng() * (width - 80)
  const planetY = 40 + rng() * (height - 80)
  const planetR = 6 + rng() * 4

  return (
    <svg
      className={className}
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        overflow: 'hidden',
      }}
      width={width}
      height={height}
      aria-hidden="true"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid slice"
    >
      <defs>
        <filter id={filterId}>
          <feGaussianBlur stdDeviation="18" />
        </filter>
      </defs>

      {/* Nebulosas com etherPulse */}
      {nebulae.map((n, i) => (
        <ellipse
          key={`nebula-${i}`}
          cx={n.cx}
          cy={n.cy}
          rx={n.rx}
          ry={n.ry}
          fill="var(--stamp)"
          filter={`url(#${filterId})`}
          opacity={n.opacity}
          style={animated ? {
            animation: `etherPulse 8s ease-in-out infinite`,
            animationDelay: `${n.delay}s`,
          } : undefined}
        />
      ))}

      {/* Estrelas de 10 pontas */}
      {stars.map((s, i) => (
        <path
          key={`star-${i}`}
          d={starPath(s.cx, s.cy, s.outerR, s.innerR, 5, s.rotation)}
          fill="var(--ink-light)"
          opacity={s.opacity}
        />
      ))}

      {/* Constelação — pontos ligados por linhas pontilhadas */}
      {constPoints.length > 1 && (
        <g opacity={0.22}>
          {constPoints.slice(0, -1).map((p, i) => (
            <line
              key={`const-line-${i}`}
              x1={p.x} y1={p.y}
              x2={constPoints[i + 1].x} y2={constPoints[i + 1].y}
              stroke="var(--ink-faint)"
              strokeWidth={0.6}
              strokeDasharray="2,4"
            />
          ))}
          {constPoints.map((p, i) => (
            <circle
              key={`const-dot-${i}`}
              cx={p.x} cy={p.y} r={1.2}
              fill="var(--ink-light)"
            />
          ))}
          {/* Label mitológico — exclusivo AETHER */}
          <text
            x={constLabelX}
            y={constLabelY}
            textAnchor="middle"
            fontFamily="var(--font-mono)"
            fontSize={7}
            fill="var(--ink-faint)"
            letterSpacing="0.1em"
            style={{ textTransform: 'uppercase' }}
          >
            {constName}
          </text>
        </g>
      )}

      {/* Cometa — três linhas divergentes + núcleo */}
      {cfg.hasComet && (
        <g
          transform={`translate(${cometX}, ${cometY}) rotate(${cometAngle})`}
          opacity={0.45}
        >
          <line x1={0} y1={0} x2={-28} y2={0}   stroke="var(--ink-faint)" strokeWidth={0.9} />
          <line x1={0} y1={0} x2={-22} y2={-4}  stroke="var(--ink-faint)" strokeWidth={0.65} />
          <line x1={0} y1={0} x2={-22} y2={4}   stroke="var(--ink-faint)" strokeWidth={0.4} />
          <ellipse cx={0} cy={0} rx={2.5} ry={1.5} fill="var(--accent)" opacity={0.5} />
        </g>
      )}

      {/* Lua crescente */}
      {cfg.hasMoon && (
        <g opacity={0.3}>
          <circle cx={moonX} cy={moonY} r={moonR} fill="var(--ink-light)" />
          <circle cx={moonX + moonR * 0.45} cy={moonY} r={moonR * 0.82} fill="var(--paper)" />
        </g>
      )}

      {/* Planeta com anel */}
      {cfg.hasPlanet && (
        <g opacity={0.22}>
          <circle cx={planetX} cy={planetY} r={planetR} fill="var(--ink-faint)" />
          <ellipse
            cx={planetX} cy={planetY}
            rx={planetR * 2.2} ry={planetR * 0.55}
            fill="none"
            stroke="var(--ink-faint)"
            strokeWidth={0.8}
          />
        </g>
      )}
    </svg>
  )
}
