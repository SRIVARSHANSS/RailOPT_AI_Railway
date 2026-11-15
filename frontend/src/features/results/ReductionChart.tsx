// Per-scenario weighted delay saved vs no re-planning: histogram + box plot per method.
// Quartiles, whiskers and bin counts come from the API (summarised from eval_results.csv).
import { scaleLinear } from 'd3'
import { motion, useReducedMotion } from 'framer-motion'
import { useRef } from 'react'
import type { DistMethod } from '../../api/types'
import { duration, ease } from '../../lib/motion'
import { BASELINES, f, label, useWidth } from './format'

export function ReductionChart({ edges, methods, order }: { edges: number[]; methods: Record<string, DistMethod>; order: string[] }) {
  const wrap = useRef<HTMLDivElement>(null)
  const width = useWidth(wrap)
  const reduce = useReducedMotion()
  const rows = order.filter((m) => methods[m])
  const row = 74
  const M = { top: 10, right: 24, bottom: 34, left: Math.min(230, width * 0.36) }
  const H = M.top + M.bottom + rows.length * row
  const x = scaleLinear().domain([Math.min(0, edges[0]), edges[edges.length - 1]]).nice().range([M.left, width - M.right])
  const ticks = x.ticks(Math.max(3, Math.floor((width - M.left - M.right) / 100)))
  const maxCount = Math.max(1, ...rows.flatMap((m) => methods[m].histogram))

  return (
    <div ref={wrap} className="w-full">
      <svg width={width} height={H} role="img" className="block"
        aria-label="Per-scenario weighted delay saved compared with no re-planning, per method (simulated)">
        {ticks.map((t) => (
          <g key={t} transform={`translate(${x(t)},0)`}>
            <line y1={M.top} y2={H - M.bottom} stroke={t === 0 ? 'rgb(var(--c-ink-muted))' : 'rgb(var(--c-line) / 0.1)'} strokeWidth={t === 0 ? 1.5 : 1} />
            <text y={H - 12} textAnchor="middle" className="fill-ink-dim font-mono" fontSize={12}>{t}</text>
          </g>
        ))}
        {rows.map((m, i) => {
          const d = methods[m]
          const y0 = M.top + i * row
          const mid = y0 + row * 0.62
          const fill = BASELINES.has(m) ? 'rgb(var(--c-ink-dim))' : m.startsWith('DYNAMIC_ML') ? 'rgb(var(--c-violet))' : 'rgb(var(--c-cyan))'
          return (
            <motion.g key={m} initial={reduce ? false : { opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
              transition={{ duration: duration.slow, ease: ease.out, delay: reduce ? 0 : i * 0.07 }}>
              <text x={M.left - 10} y={mid - 4} textAnchor="end" className="fill-ink" fontSize={14}>{label(m)}</text>
              <text x={M.left - 10} y={mid + 13} textAnchor="end" className="fill-ink-dim" fontSize={11.5}>
                {d.improved} better · {d.unchanged} same · {d.worse} worse
              </text>
              {/* histogram (faint), counts per bin */}
              {d.histogram.map((c, k) => {
                const h = (c / maxCount) * (row * 0.42)
                return c ? <rect key={k} x={x(edges[k]) + 0.5} width={Math.max(1, x(edges[k + 1]) - x(edges[k]) - 1)}
                  y={mid - 12 - h} height={h} fill={fill} fillOpacity={0.22} /> : null
              })}
              {/* box plot */}
              <line x1={x(d.whisker_low)} x2={x(d.whisker_high)} y1={mid} y2={mid} stroke="rgb(var(--c-ink-muted))" strokeWidth={1.5} />
              {[d.whisker_low, d.whisker_high].map((w, k) => (
                <line key={k} x1={x(w)} x2={x(w)} y1={mid - 6} y2={mid + 6} stroke="rgb(var(--c-ink-muted))" strokeWidth={1.5} />
              ))}
              <rect x={x(d.q1)} y={mid - 9} width={Math.max(2, x(d.q3) - x(d.q1))} height={18} rx={3}
                fill={fill} fillOpacity={0.35} stroke={fill} strokeWidth={1.5} />
              <line x1={x(d.median)} x2={x(d.median)} y1={mid - 9} y2={mid + 9} stroke="rgb(var(--c-ink))" strokeWidth={2.5} />
              <circle cx={x(d.mean)} cy={mid} r={4} fill="rgb(var(--c-canvas-0))" stroke="rgb(var(--c-ink))" strokeWidth={1.5}>
                <title>{`mean ${f(d.mean)}, median ${f(d.median)}, quartiles ${f(d.q1)} to ${f(d.q3)}`}</title>
              </circle>
            </motion.g>
          )
        })}
      </svg>
    </div>
  )
}
