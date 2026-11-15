// Horizontal bar chart with optional 95% CI whiskers. D3 for the scale, React for the SVG,
// Framer Motion for the entrance (scaleX from the baseline: transform only).
import { scaleLinear } from 'd3'
import { motion, useReducedMotion } from 'framer-motion'
import { useRef } from 'react'
import type { Ci } from '../../api/types'
import { duration, ease } from '../../lib/motion'
import { f, useWidth } from './format'

export type Bar = { key: string; label: string; value: number; ci?: Ci; tone: 'baseline' | 'ai' | 'ml' | 'neutral'; note?: string }

const FILL: Record<Bar['tone'], string> = {
  baseline: 'rgb(var(--c-ink-dim))',
  ai: 'rgb(var(--c-cyan))',
  ml: 'rgb(var(--c-violet))',
  neutral: 'rgb(var(--c-passenger))',
}

export function BarChart({ bars, digits = 1, unit, labelWidth = 220, ariaLabel }: {
  bars: Bar[]; digits?: number; unit?: string; labelWidth?: number; ariaLabel: string
}) {
  const wrap = useRef<HTMLDivElement>(null)
  const width = useWidth(wrap)
  const reduce = useReducedMotion()
  const row = 40
  const M = { top: 8, right: 96, bottom: 28, left: Math.min(labelWidth, width * 0.42) }
  const H = M.top + M.bottom + bars.length * row
  const hi = Math.max(1e-9, ...bars.map((b) => (b.ci ? b.ci[1] : b.value)))
  const x = scaleLinear().domain([0, hi]).nice().range([M.left, width - M.right])
  const ticks = x.ticks(Math.max(3, Math.floor((width - M.left - M.right) / 110)))

  return (
    <div ref={wrap} className="w-full">
      <svg width={width} height={H} role="img" aria-label={ariaLabel} className="block">
        {ticks.map((t) => (
          <g key={t} transform={`translate(${x(t)},0)`}>
            <line y1={M.top} y2={H - M.bottom} stroke="rgb(var(--c-line) / 0.1)" />
            <text y={H - 8} textAnchor="middle" className="fill-ink-dim font-mono" fontSize={12}>{t}</text>
          </g>
        ))}
        {bars.map((b, i) => {
          const y = M.top + i * row
          const w = Math.max(0, x(b.value) - x(0))
          return (
            <g key={b.key}>
              <text x={M.left - 10} y={y + row / 2 + 5} textAnchor="end" className="fill-ink" fontSize={14}>{b.label}</text>
              <motion.rect x={x(0)} y={y + 9} width={w} height={row - 18} rx={4} fill={FILL[b.tone]} fillOpacity={0.85}
                style={{ transformBox: 'fill-box', transformOrigin: 'left center' }}
                initial={reduce ? false : { scaleX: 0 }} animate={{ scaleX: 1 }}
                transition={{ duration: duration.slow * 2, ease: ease.out, delay: reduce ? 0 : i * 0.06 }} />
              {b.ci && (
                <motion.g initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }}
                  transition={{ duration: duration.base, delay: reduce ? 0 : 0.5 + i * 0.06 }}>
                  <line x1={x(b.ci[0])} x2={x(b.ci[1])} y1={y + row / 2} y2={y + row / 2} stroke="rgb(var(--c-ink))" strokeWidth={1.5} />
                  {[b.ci[0], b.ci[1]].map((c, k) => (
                    <line key={k} x1={x(c)} x2={x(c)} y1={y + row / 2 - 7} y2={y + row / 2 + 7} stroke="rgb(var(--c-ink))" strokeWidth={1.5} />
                  ))}
                </motion.g>
              )}
              <text x={x(b.ci ? b.ci[1] : b.value) + 8} y={y + row / 2 + 5} className="fill-ink font-mono" fontSize={13}>
                {f(b.value, digits)}{unit ? ` ${unit}` : ''}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
