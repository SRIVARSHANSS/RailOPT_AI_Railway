import type { Scenario, StateAt } from '../../api/types'
import { cn } from '../../lib/cn'
import { toMin } from '../../lib/time'
import type { Highlight } from '../../store/sim'
import { MAIN_Y, VIEW, type Geometry } from './geometry'
import { TrainSprite } from './TrainSprite'

const TYPES = ['EXPRESS', 'PASSENGER', 'FREIGHT'] as const

/** The corridor: stations at real km, sections tinted by occupancy (from the API state),
 *  closures in red, an accepted reroute as a dashed cyan planned route. Drawing only. */
export function CorridorMap({ geo, now, next, glideMs, minute, scenario, highlight }: {
  geo: Geometry
  now: StateAt
  next: StateAt | null
  glideMs: number
  minute: number
  scenario: Scenario | undefined
  highlight: Highlight
}) {
  const inSection: Record<string, number> = {}
  for (const t of now.trains) if (t.status === 'in_section') inSection[t.location] = (inSection[t.location] ?? 0) + 1
  const closed = new Set(
    (scenario?.events ?? [])
      .filter((e) => e.event_type === 'TRACK_UNAVAILABLE' && toMin(e.start_time) <= minute && minute < toMin(e.start_time) + e.duration_min)
      .map((e) => e.location),
  )
  const planned = new Set((scenario?.route_overrides ?? []).map((r) => r.section_id))
  const plannedTrains = (scenario?.route_overrides ?? []).map((r) => r.train_id)
  const nextById = new Map((next?.trains ?? []).map((t) => [t.train_id, t]))
  const focusSection = highlight?.section_id ?? null

  return (
    <svg viewBox={`0 0 ${VIEW.w} ${VIEW.h}`} className="h-auto w-full" role="group" aria-label="Corridor map A to D (simulated)">
      <defs>
        {/* user-space region: a horizontal track has a zero-height bounding box, so a
            percentage filter region would collapse and hide the line */}
        <filter id="track-glow" filterUnits="userSpaceOnUse" x={0} y={0} width={VIEW.w} height={VIEW.h}>
          <feGaussianBlur stdDeviation="3" result="b" />
          <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="train-glow" x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation="3.5" result="b" />
          <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        {TYPES.map((t) => (
          <linearGradient key={t} id={`trail-${t}`} x1="0" x2="1">
            <stop offset="0" stopColor={`rgb(var(--c-${t.toLowerCase()}))`} stopOpacity="0" />
            <stop offset="1" stopColor={`rgb(var(--c-${t.toLowerCase()}))`} stopOpacity="0.55" />
          </linearGradient>
        ))}
      </defs>

      {/* sections */}
      {Object.values(geo.sections).map((sec) => {
        const n = inSection[sec.section_id] ?? 0
        const isClosed = closed.has(sec.section_id)
        const isPlanned = planned.has(sec.section_id)
        const tone = isClosed ? 'stroke-signal-red' : n >= sec.tracks ? 'stroke-signal-amber' : n > 0 ? 'stroke-signal-cyan' : sec.alternate ? 'stroke-ink-dim/60' : 'stroke-line/40'
        const focused = focusSection === sec.section_id
        return (
          <g key={sec.section_id} className={cn('transition-opacity duration-300', focusSection && !focused && 'opacity-30')}>
            {sec.lanes.map((d, i) => (
              <g key={i}>
                <path d={d} fill="none" strokeWidth={10} className="stroke-canvas-0/70" />
                <path d={d} fill="none" strokeWidth={focused ? 5 : 3.5} strokeLinecap="round" filter="url(#track-glow)"
                  strokeDasharray={isClosed ? '10 8' : sec.alternate && !isPlanned && n === 0 ? '2 7' : undefined}
                  className={focused ? 'stroke-signal-red' : tone} />
                {isPlanned && (
                  <path d={d} fill="none" strokeWidth={3} strokeDasharray="12 10" className="animate-breathe stroke-signal-cyan" />
                )}
              </g>
            ))}
            {sec.showLabel && <text x={sec.labelX} y={sec.labelY} textAnchor="middle" className={cn('font-mono text-[17px]', isClosed ? 'fill-signal-red' : 'fill-ink-muted')}>
              {sec.section_id}
              {sec.alternate ? (isPlanned ? ` - planned route for ${plannedTrains.join(', ')}` : ' - alternate (standby)') : ''}
              {isClosed ? ' - CLOSED' : sec.tracks > 1 ? ` - ${sec.tracks} tracks` : ''}
            </text>}
          </g>
        )
      })}

      {/* stations */}
      {Object.values(geo.stations).map((st) => (
        <g key={st.code} transform={`translate(${st.x} ${MAIN_Y})`}>
          <circle r={26} className="animate-node-pulse origin-center fill-signal-cyan/10 [transform-box:fill-box]" />
          <circle r={16} className="fill-canvas-1 stroke-signal-cyan" strokeWidth={2.5} />
          <text y={7} textAnchor="middle" className="fill-ink font-display text-[19px] font-bold">{st.code}</text>
          <text y={-38 + st.lift} textAnchor="middle" className="fill-ink-muted text-[17px]">{st.name}</text>
          <text y={-60 + st.lift} textAnchor="middle" className="fill-ink-dim font-mono text-[13px] uppercase tracking-wider">{st.platforms} platforms</text>
        </g>
      ))}

      {/* trains (absent until they start) */}
      {now.trains.map((t) => (
        <TrainSprite key={t.train_id} now={t} next={nextById.get(t.train_id) ?? null} geo={geo} glideMs={glideMs} minute={minute}
          dimmed={Boolean(highlight) && !highlight?.trains.includes(t.train_id)}
          highlighted={Boolean(highlight?.trains.includes(t.train_id))} />
      ))}
    </svg>
  )
}
