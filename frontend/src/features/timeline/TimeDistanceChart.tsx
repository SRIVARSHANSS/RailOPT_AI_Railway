// Time-distance (Marey / string) chart. D3 does the maths (scales, zoom, line paths); React
// renders the SVG. All positions, waits, stops, delays, conflicts and closures come from the API.
import { line, scaleLinear, select, zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from 'd3'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { Maximize2, ZoomIn, ZoomOut } from 'lucide-react'
import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { ClosureBlock, Conflict, Section, Station, TimelineRow } from '../../api/types'
import { cn } from '../../lib/cn'
import { duration, ease } from '../../lib/motion'
import { fmt, toMin } from '../../lib/time'
import { byTrain, rowPoints, timeExtent, trainPoints, TYPE_COLOR, type Pt } from './geometry'

const M = { top: 34, right: 72, bottom: 48, left: 132 }
const H = 600
const LANE_DY = 14 // the alternate lane is drawn this many px beside its main section

type Hover = { row: TimelineRow; kind: 'primary' | 'secondary'; x: number; y: number }

export function TimeDistanceChart({
  stations, sections, trainTypes, primary, secondary, primaryLabel, secondaryLabel,
  closures, conflicts, minute, selected, onSelect,
}: {
  stations: Station[]
  sections: Section[]
  trainTypes: Record<string, string>
  primary: TimelineRow[]
  secondary: TimelineRow[]
  primaryLabel: string
  secondaryLabel: string
  closures: ClosureBlock[]
  conflicts: Conflict[]
  minute: number
  selected: string | null
  onSelect: (train: string | null) => void
}) {
  const wrap = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const zoomRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null)
  const drawn = useRef(false)
  const reduce = useReducedMotion()
  const [width, setWidth] = useState(1000)
  const [t, setT] = useState<ZoomTransform>(zoomIdentity)
  const [hover, setHover] = useState<Hover | null>(null)

  useLayoutEffect(() => {
    const el = wrap.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(560, Math.round(e.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // D3 zoom on the time axis only (the km axis stays fixed)
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const ext: [[number, number], [number, number]] = [[M.left, 0], [width - M.right, H]]
    const z = zoom<SVGSVGElement, unknown>().scaleExtent([1, 16]).extent(ext).translateExtent(ext)
      .on('zoom', (e: { transform: ZoomTransform }) => setT(e.transform))
    zoomRef.current = z
    select(svg).call(z)
    return () => { select(svg).on('.zoom', null) }
  }, [width])

  useEffect(() => { drawn.current = true })

  const kmByStation = useMemo(() => Object.fromEntries(stations.map((s) => [s.code, s.km])), [stations])
  const maxKm = Math.max(1, ...stations.map((s) => s.km))
  const x0 = useMemo(() => scaleLinear().domain(timeExtent([...primary, ...secondary])).range([M.left, width - M.right]),
    [primary, secondary, width])
  const x = t.rescaleX(x0)
  const y = scaleLinear().domain([0, maxKm]).range([M.top, H - M.bottom - LANE_DY])
  const py = (p: Pt) => y(p.km) + p.lane * LANE_DY
  const path = line<Pt>().x((p) => x(p.t)).y(py)
  const ticks = x.ticks(Math.max(4, Math.floor(width / 120))).filter(Number.isInteger)

  const prim = useMemo(() => byTrain(primary), [primary])
  const sec = useMemo(() => byTrain(secondary), [secondary])
  const lanes = sections.filter((s) => s.status === 'standby')
  const plotW = width - M.left - M.right
  const dim = (train: string) => (selected && selected !== train ? 0.16 : 1)

  const zoomBy = (k: number | null) => {
    const svg = svgRef.current, z = zoomRef.current
    if (!svg || !z) return
    const sel = select(svg).transition().duration(reduce ? 0 : duration.slow * 1000)
    if (k === null) z.transform(sel, zoomIdentity)
    else z.scaleBy(sel, k)
  }

  const onMove = (e: React.MouseEvent, row: TimelineRow, kind: Hover['kind']) => {
    const box = wrap.current?.getBoundingClientRect()
    if (box) setHover({ row, kind, x: e.clientX - box.left, y: e.clientY - box.top })
  }

  const draw = !drawn.current && !reduce

  return (
    <div ref={wrap} className="relative" onKeyDown={(e) => { if (e.key === 'Escape') onSelect(null) }}>
      <div className="absolute right-2 top-0 z-10 flex gap-1">
        {([['Zoom in', 1.6, ZoomIn], ['Zoom out', 1 / 1.6, ZoomOut], ['Reset zoom', null, Maximize2]] as const).map(([label, k, Icon]) => (
          <button key={label} aria-label={label} title={label} onClick={() => zoomBy(k)}
            className="rounded-lg border border-line/15 bg-canvas-0/60 p-2 text-ink-muted hover:bg-white/5 hover:text-ink">
            <Icon className="h-4 w-4" aria-hidden />
          </button>
        ))}
      </div>

      <svg ref={svgRef} width={width} height={H} role="img" className="block cursor-grab touch-none select-none active:cursor-grabbing"
        aria-label={`Time-distance chart, simulated. Solid lines: ${primaryLabel}. Dashed lines: ${secondaryLabel}. Scroll or use the buttons to zoom the time axis, drag to pan.`}
        onClick={(e) => { if (e.target === svgRef.current) onSelect(null) }}>
        <defs>
          {/* userSpaceOnUse: flat (zero-height) segments would collapse a bounding-box filter region */}
          <filter id="td-glow" filterUnits="userSpaceOnUse" x={0} y={0} width={width} height={H}>
            <feGaussianBlur stdDeviation="3" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <pattern id="td-hatch" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="9" height="9" fill="rgb(var(--c-red) / 0.08)" />
            <line x1="0" y1="0" x2="0" y2="9" stroke="rgb(var(--c-red) / 0.75)" strokeWidth="3" />
          </pattern>
          <clipPath id="td-plot"><rect x={M.left} y={0} width={plotW} height={H} /></clipPath>
        </defs>

        {/* section bands and labels */}
        {sections.filter((s) => s.status !== 'standby').map((s, i) => {
          const y1 = y(kmByStation[s.from_station] ?? 0), y2 = y(kmByStation[s.to_station] ?? 0)
          return (
            <g key={s.section_id}>
              <rect x={M.left} y={Math.min(y1, y2)} width={plotW} height={Math.abs(y2 - y1)}
                fill={i % 2 ? 'rgb(var(--c-line) / 0.035)' : 'rgb(var(--c-line) / 0.065)'} />
              <text x={M.left - 12} y={(y1 + y2) / 2 + 4} textAnchor="end" className="fill-ink-dim font-mono" fontSize={12}>
                {s.section_id} · {s.tracks} track{s.tracks > 1 ? 's' : ''}
              </text>
            </g>
          )
        })}

        {/* alternate lanes: a parallel band beside the main section */}
        {lanes.map((s) => {
          const y1 = y(kmByStation[s.from_station] ?? 0) + LANE_DY, y2 = y(kmByStation[s.to_station] ?? 0) + LANE_DY
          return (
            <g key={s.section_id}>
              {[y1, y2].map((yy, i) => (
                <line key={i} x1={M.left} x2={width - M.right} y1={yy} y2={yy} stroke="rgb(var(--c-cyan) / 0.45)" strokeDasharray="3 6" />
              ))}
              <text x={M.left - 12} y={(y1 + y2) / 2 + 22} textAnchor="end" className="fill-signal-cyan font-mono" fontSize={12}>
                <tspan x={M.left - 12}>{s.section_id}</tspan>
                <tspan x={M.left - 12} dy={15}>alt lane</tspan>
              </text>
            </g>
          )
        })}

        <g clipPath="url(#td-plot)">
          {/* closures: hatched blocks */}
          {closures.map((c) => (
            <g key={c.event_id}>
              <rect x={x(c.start_min)} y={y(Math.min(c.from_km, c.to_km))} width={Math.max(1, x(c.end_min) - x(c.start_min))}
                height={Math.abs(y(c.to_km) - y(c.from_km))} fill="url(#td-hatch)" stroke="rgb(var(--c-red) / 0.8)" strokeDasharray="4 3" />
              <text x={x(c.start_min) + 6} y={y(Math.min(c.from_km, c.to_km)) + 16} className="fill-signal-red font-semibold" fontSize={13}>
                {c.event_id} closed {c.start}-{c.end}
              </text>
            </g>
          ))}

          {/* conflicts at the sim clock: red band over the overlap window */}
          {conflicts.map((k) => {
            const s = sections.find((q) => q.section_id === k.section_id)
            if (!s) return null
            const ya = y(kmByStation[s.from_station] ?? 0), yb = y(kmByStation[s.to_station] ?? 0)
            const x1 = x(toMin(k.window_start)), x2 = x(toMin(k.window_end))
            return (
              <motion.g key={`${k.conflict_id}-${k.later_train}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: duration.base }}>
                <rect x={x1} y={Math.min(ya, yb)} width={Math.max(2, x2 - x1)} height={Math.abs(yb - ya)}
                  fill="rgb(var(--c-red) / 0.2)" stroke="rgb(var(--c-red))" strokeWidth={1.5} />
                <text x={x1 + 6} y={Math.max(ya, yb) - 8} className="fill-signal-red font-semibold" fontSize={13}>
                  {k.severity} {k.later_train} {k.conflict_type.toLowerCase()} {k.window_start}-{k.window_end}
                </text>
              </motion.g>
            )
          })}

          {/* secondary: thin dashed (planned, or before the accepted plan) */}
          {sec.map(({ train_id, rows }) => (
            <motion.path key={`s-${train_id}-${secondaryLabel}`} d={path(trainPoints(rows)) ?? ''} fill="none"
              stroke={TYPE_COLOR[trainTypes[train_id]] ?? 'rgb(var(--c-ink-muted))'} strokeWidth={2} strokeDasharray="7 6"
              initial={{ opacity: 0 }} animate={{ opacity: 0.7 * dim(train_id) }}
              transition={{ duration: draw ? duration.draw : duration.base, ease: ease.out }} />
          ))}

          {/* primary: solid, glowing (actual / after the accepted plan) */}
          {prim.map(({ train_id, rows }, i) => (
            <motion.path key={`p-${train_id}-${primaryLabel}`} d={path(trainPoints(rows)) ?? ''} fill="none"
              stroke={TYPE_COLOR[trainTypes[train_id]] ?? 'rgb(var(--c-ink))'} strokeWidth={selected === train_id ? 4.5 : 3.25}
              strokeLinejoin="round" strokeLinecap="round" filter="url(#td-glow)"
              initial={draw ? { pathLength: 0, opacity: 1 } : { opacity: 0 }}
              animate={{ pathLength: 1, opacity: dim(train_id) }}
              transition={{ pathLength: { duration: duration.draw, ease: ease.out, delay: i * 0.12 }, opacity: { duration: duration.base } }} />
          ))}

          {/* waits at a signal: red segment along the station line ending in a red tick */}
          {primary.filter((r) => r.wait_min > 0).map((r) => {
            const yy = y(r.from_km), xa = x(r.entry_min - r.wait_min), xb = x(r.entry_min)
            return (
              <g key={`w-${r.train_id}-${r.section_id}`} opacity={dim(r.train_id)}>
                <line x1={xa} x2={xb} y1={yy} y2={yy} stroke="rgb(var(--c-red))" strokeWidth={5} strokeLinecap="round" opacity={0.85} />
                <line x1={xb} x2={xb} y1={yy - 9} y2={yy + 9} stroke="rgb(var(--c-red))" strokeWidth={3} strokeLinecap="round" />
                <text x={(xa + xb) / 2} y={yy - 10} textAnchor="middle" className="fill-signal-red font-mono font-semibold" fontSize={12}>
                  wait {r.wait_min}
                </text>
              </g>
            )
          })}

          {/* hit areas: one per section trip, wide and invisible */}
          {(['secondary', 'primary'] as const).flatMap((kind) =>
            (kind === 'primary' ? prim : sec).flatMap(({ train_id, rows }) => rows.map((r, j) => (
              <path key={`h-${kind}-${train_id}-${r.section_id}`} d={path(rowPoints(r, rows[j - 1])) ?? ''} fill="none"
                stroke="transparent" strokeWidth={16} pointerEvents="stroke" className="cursor-pointer"
                onMouseMove={(e) => onMove(e, r, kind)} onMouseLeave={() => setHover(null)}
                onClick={(e) => { e.stopPropagation(); onSelect(selected === train_id ? null : train_id) }} />
            ))))}

          {/* end labels (train id, so colour is never the only cue) */}
          {prim.map(({ train_id, rows }) => {
            const pts = trainPoints(rows)
            const last = pts[pts.length - 1]
            if (!last) return null
            return (
              <text key={`l-${train_id}`} x={x(last.t) + 8} y={py(last) + 5} opacity={dim(train_id)}
                fill={TYPE_COLOR[trainTypes[train_id]]} className="font-mono font-bold" fontSize={15}>{train_id}</text>
            )
          })}

          {/* now line (sim clock) */}
          <g pointerEvents="none">
            <line x1={x(minute)} x2={x(minute)} y1={M.top - 6} y2={H - M.bottom} stroke="rgb(var(--c-cyan))" strokeWidth={2} />
            <rect x={x(minute) - 30} y={M.top - 30} width={60} height={22} rx={6} fill="rgb(var(--c-cyan))" />
            <text x={x(minute)} y={M.top - 14} textAnchor="middle" className="fill-canvas-0 font-mono font-bold" fontSize={13}>{fmt(minute)}</text>
          </g>
        </g>

        {/* station axis (real km) */}
        {stations.map((s) => (
          <g key={s.code}>
            <line x1={M.left} x2={width - M.right} y1={y(s.km)} y2={y(s.km)} stroke="rgb(var(--c-line) / 0.35)" />
            <text x={M.left - 12} y={y(s.km) - 2} textAnchor="end" className="fill-ink font-display font-bold" fontSize={18}>{s.code}</text>
            <text x={M.left - 12} y={y(s.km) + 15} textAnchor="end" className="fill-ink-muted font-mono" fontSize={12}>{s.km} km</text>
          </g>
        ))}

        {/* time axis */}
        <g>
          <line x1={M.left} x2={width - M.right} y1={H - M.bottom} y2={H - M.bottom} stroke="rgb(var(--c-line) / 0.4)" />
          {ticks.map((m) => (
            <g key={m} transform={`translate(${x(m)},${H - M.bottom})`}>
              <line y2={6} stroke="rgb(var(--c-line) / 0.5)" />
              <line y1={-(H - M.bottom - M.top)} y2={0} stroke="rgb(var(--c-line) / 0.07)" />
              <text y={24} textAnchor="middle" className="fill-ink-muted font-mono" fontSize={13}>{fmt(m)}</text>
            </g>
          ))}
        </g>
      </svg>

      <AnimatePresence>
        {hover && (
          <motion.div key="tip" role="tooltip" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            transition={{ duration: duration.fast }}
            className="glass pointer-events-none absolute z-20 w-72 p-3 text-sm"
            style={{ left: Math.min(hover.x + 16, width - 300), top: Math.max(0, hover.y - 20) }}>
            <TipBody hover={hover} type={trainTypes[hover.row.train_id]} label={hover.kind === 'primary' ? primaryLabel : secondaryLabel} />
          </motion.div>
        )}
      </AnimatePresence>

      <table className="sr-only">
        <caption>{primaryLabel} (simulated)</caption>
        <thead><tr><th>Train</th><th>Section</th><th>Entry</th><th>Exit</th><th>Wait</th><th>Delay</th></tr></thead>
        <tbody>
          {primary.map((r) => (
            <tr key={`${r.train_id}-${r.section_id}`}>
              <td>{r.train_id}</td><td>{r.section_id}</td><td>{r.entry}</td><td>{r.exit}</td><td>{r.wait_min} min</td><td>{r.delay_min ?? '-'} min</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TipBody({ hover, type, label }: { hover: Hover; type: string | undefined; label: string }) {
  const r = hover.row
  return (
    <>
      <div className="flex items-center gap-2">
        <span className="font-mono text-base font-bold" style={{ color: TYPE_COLOR[type ?? ''] }}>{r.train_id}</span>
        <span className="text-xs uppercase tracking-wider text-ink-muted">{type?.toLowerCase()}</span>
        <span className="ml-auto text-xs text-ink-dim">{label}</span>
      </div>
      <p className="mt-1 font-mono text-ink">
        {r.section_id}{r.alternate && <span className="ml-2 text-signal-cyan">alternate line</span>}
      </p>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
        <dt className="text-ink-dim">Entry</dt><dd className="font-mono">{r.from_station} {r.entry}</dd>
        <dt className="text-ink-dim">Exit</dt><dd className="font-mono">{r.to_station} {r.exit}</dd>
        {r.wait_min > 0 && <><dt className="text-ink-dim">Signal</dt><dd className="font-mono text-signal-red">waited {r.wait_min} min</dd></>}
        {r.stops.map((s) => (
          <Fragment key={s.start_min}><dt className="text-ink-dim">Stopped</dt><dd className="font-mono">{fmt(s.start_min)}-{fmt(s.end_min)}</dd></Fragment>
        ))}
        <dt className="text-ink-dim">Delay</dt>
        <dd className={cn('font-mono', (r.delay_min ?? 0) > 0 ? 'text-signal-amber' : 'text-signal-green')}>
          {r.delay_min === null ? '-' : r.delay_min > 0 ? `+${r.delay_min} min at ${r.to_station}` : `on time at ${r.to_station}`}
        </dd>
      </dl>
    </>
  )
}
