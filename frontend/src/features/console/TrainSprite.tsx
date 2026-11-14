import { animate, useReducedMotion } from 'framer-motion'
import { useLayoutEffect, useRef } from 'react'
import type { TrainState } from '../../api/types'
import { cn } from '../../lib/cn'
import {
  along, anchorAngle, anchorOf, anchorPoint, cumulative, routeBetween, SIGNAL_OFFSET, type Geometry,
} from './geometry'

const fill: Record<string, string> = {
  EXPRESS: 'rgb(var(--c-express))',
  PASSENGER: 'rgb(var(--c-passenger))',
  FREIGHT: 'rgb(var(--c-freight))',
}

/** One train. Shows `now` (the API state at the clock minute); while playing and the next
 *  minute's state is known, glides along the track to `next` in the time left in this minute.
 *  A jump of the clock re-renders from `now`, so it snaps instead of gliding. */
export function TrainSprite({ now, next, geo, glideMs, minute, dimmed, highlighted }: {
  now: TrainState
  next: TrainState | null
  geo: Geometry
  glideMs: number
  minute: number
  dimmed: boolean
  highlighted: boolean
}) {
  const reduce = useReducedMotion()
  const body = useRef<SVGGElement>(null)
  const label = useRef<SVGGElement>(null)
  const from = anchorOf(now, geo)
  const to = next ? anchorOf(next, geo) : null

  useLayoutEffect(() => {
    if (!from || !body.current || !label.current) return
    const place = (x: number, y: number, angle: number) => {
      body.current?.setAttribute('transform', `translate(${x} ${y}) rotate(${angle})`)
      label.current?.setAttribute('transform', `translate(${x} ${y})`)
    }
    const start = anchorPoint(from)
    place(start.x, start.y, anchorAngle(from))
    if (!to || reduce || glideMs < 30) return
    const pts = routeBetween(from, to, geo)
    const cum = cumulative(pts)
    if (cum[cum.length - 1] < 0.5) return
    const controls = animate(0, 1, {
      duration: glideMs / 1000,
      ease: 'linear',
      onUpdate: (f) => {
        const p = along(pts, cum, f)
        place(p.x, p.y, f >= 1 && to.kind === 'point' ? 0 : p.angle)
      },
    })
    return () => controls.stop()
    // the minute is the animation key: a new minute (or a jump) restarts from `now`
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minute, next?.status, next?.location, next?.progress, now.status, now.location, now.progress, glideMs, reduce, geo])

  if (!from) return null
  const delayed = now.current_delay_min > 0
  const waiting = now.status === 'waiting_at_signal'
  const arrived = now.status === 'arrived'
  const stopped = now.stopped
  const colour = fill[now.train_type] ?? 'rgb(var(--c-ink))'

  return (
    <g className={cn('transition-opacity duration-300', dimmed && 'opacity-25', arrived && 'opacity-50')}
       role="img" aria-label={`${now.train_id} ${now.train_type.toLowerCase()}, ${stopped ? 'stopped in' : now.status.replace(/_/g, ' ')} ${now.location}${delayed ? `, ${now.current_delay_min} min late` : ''}`}>
      <g ref={body}>
        {/* motion trail */}
        <rect x={-46} y={-4} width={34} height={8} rx={4} fill={`url(#trail-${now.train_type})`} opacity={waiting || arrived || stopped ? 0 : 0.9} />
        {highlighted && <rect x={-20} y={-11} width={40} height={22} rx={11} fill="none" stroke="rgb(var(--c-cyan))" strokeWidth={2} />}
        <rect x={-15} y={-7} width={30} height={14} rx={7} fill={colour} filter="url(#train-glow)" />
        <rect x={6} y={-4} width={5} height={8} rx={2} fill="rgb(var(--c-canvas-0))" opacity={0.55} />
        {delayed && (
          <circle r={17} fill="none" stroke="rgb(var(--c-red))" strokeWidth={2.5} className="origin-center animate-ring-pulse [transform-box:fill-box]" />
        )}
      </g>
      {/* arrived trains drop their labels so the terminal stays readable (the train strip lists them) */}
      <g ref={label} className={cn('pointer-events-none', arrived && 'opacity-0')}>
        <text y={-22} textAnchor="middle" className="fill-ink font-mono text-[19px] font-semibold">{now.train_id}</text>
        {delayed && <text y={38} textAnchor="middle" className="fill-signal-red font-mono text-[17px] font-semibold">+{now.current_delay_min}</text>}
        {waiting && (
          <g transform={`translate(${SIGNAL_OFFSET} 0)`}>
            <line x1={0} y1={-4} x2={0} y2={-26} stroke="rgb(var(--c-line) / 0.6)" strokeWidth={2} />
            <circle cy={-30} r={5} fill="rgb(var(--c-red))" className="animate-pulse-dot" />
          </g>
        )}
      </g>
    </g>
  )
}
