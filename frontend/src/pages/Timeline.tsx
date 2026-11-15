import { motion } from 'framer-motion'
import { CircleSlash, Route as RouteIcon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useConflictsAt, useNetwork, useTimeline } from '../api/hooks'
import { SignalBadge } from '../components/ui/Badges'
import { EmptyState } from '../components/ui/EmptyState'
import { Panel } from '../components/ui/Panel'
import { Skeleton } from '../components/ui/Skeleton'
import { Tabs } from '../components/ui/Tabs'
import { ClockBar } from '../features/console/ClockBar'
import { TYPE_COLOR } from '../features/timeline/geometry'
import { TimeDistanceChart } from '../features/timeline/TimeDistanceChart'
import { cn } from '../lib/cn'
import { fadeUp, staggerContainer } from '../lib/motion'
import { fmt } from '../lib/time'
import { DEMO_START, useSim } from '../store/sim'

type Mode = 'actual' | 'plan'

/** Time-distance chart of the current scenario (GET /api/timeline). Everything SIMULATED. */
export function Timeline() {
  const tl = useTimeline()
  const network = useNetwork(tl.data?.timetable)
  const minute = useSim((s) => s.minute)
  const conflicts = useConflictsAt(minute)
  const [mode, setMode] = useState<Mode>('actual')
  const [selected, setSelected] = useState<string | null>(null)

  const hasPlan = Boolean(tl.data?.before_plan)
  useEffect(() => { if (!hasPlan && mode === 'plan') setMode('actual') }, [hasPlan, mode])

  const trainTypes = useMemo(
    () => Object.fromEntries((network.data?.trains ?? []).map((t) => [t.train_id, t.train_type])), [network.data])

  if (tl.isError) {
    return (
      <Panel initial="hidden" animate="show" className="mx-auto max-w-5xl">
        <EmptyState icon={<CircleSlash className="h-7 w-7" />} title="The API is not reachable">
          Start it from the backend folder with <code className="font-mono text-ink">uvicorn app.main:app</code>.
        </EmptyState>
      </Panel>
    )
  }

  const d = tl.data
  const before = d?.before_plan ?? null
  const plan = mode === 'plan' && before
  const primaryLabel = plan ? `after: accepted plan ${d?.applied_recommendation}` : 'actual (current scenario)'
  const secondaryLabel = plan ? `before: ${d?.previous_plan ? `plan ${d.previous_plan}` : 'no plan'}` : 'planned timetable'

  return (
    <motion.div className="mx-auto max-w-[96rem] space-y-5" variants={staggerContainer()} initial="hidden" animate="show">
      <motion.div variants={fadeUp} className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-signal-cyan">Timeline</p>
          <h1 className="text-3xl font-bold xl:text-4xl">Time-distance chart</h1>
          <p className="mt-2 max-w-3xl text-ink-muted">
            Each line is a train moving down the corridor (km) over time. Flat = standing still. Scroll or use the buttons to zoom
            the time axis, drag to pan, click a train to follow it.
          </p>
        </div>
        <SignalBadge tone="info">SIMULATED</SignalBadge>
      </motion.div>

      <motion.div variants={fadeUp}><ClockBar resetTo={DEMO_START} /></motion.div>

      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <Tabs value={mode} onValueChange={(v) => setMode(v as Mode)} label="Chart comparison"
            items={[
              { value: 'actual', label: 'Planned vs actual' },
              { value: 'plan', label: 'Before vs after plan', disabled: !hasPlan, hint: hasPlan ? undefined : 'accept a plan first' },
            ]}>{null}</Tabs>
          <Legend primary={primaryLabel} secondary={secondaryLabel} />
        </div>

        {d && (
          <div className="mt-4 flex flex-wrap items-center gap-2" role="group" aria-label="Highlight a train">
            {[...new Set(d.actual.map((r) => r.train_id))].sort().map((id) => (
              <button key={id} aria-pressed={selected === id} onClick={() => setSelected(selected === id ? null : id)}
                className={cn('inline-flex items-center gap-2 rounded-lg border px-2.5 py-1 text-sm transition-colors',
                  selected === id ? 'border-line/60 bg-surface-raised' : 'border-line/15 hover:bg-white/5',
                  selected && selected !== id && 'opacity-50')}>
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: TYPE_COLOR[trainTypes[id]] }} aria-hidden />
                <span className="font-mono font-semibold">{id}</span>
                <span className="text-xs uppercase tracking-wider text-ink-muted">{trainTypes[id]?.toLowerCase()}</span>
              </button>
            ))}
            {selected && <button onClick={() => setSelected(null)} className="text-sm text-ink-muted underline-offset-4 hover:text-ink hover:underline">Show all (Esc)</button>}
          </div>
        )}

        <div className="mt-4 overflow-x-auto">
          {!d || !network.data ? (
            <div className="space-y-3" aria-busy="true" aria-label="Loading the timeline">
              <Skeleton className="h-[600px] w-full rounded-2xl" />
            </div>
          ) : d.actual.length === 0 ? (
            <EmptyState icon={<RouteIcon className="h-7 w-7" />} title="No train movements in this scenario">
              Reset the scenario on Disruptions to load a timetable.
            </EmptyState>
          ) : (
            <TimeDistanceChart
              stations={d.stations} sections={network.data.sections} trainTypes={trainTypes}
              primary={d.actual} secondary={plan ? before : d.planned}
              primaryLabel={primaryLabel} secondaryLabel={secondaryLabel}
              closures={d.closures} conflicts={conflicts.data?.conflicts ?? []} minute={minute}
              selected={selected} onSelect={setSelected} />
          )}
        </div>

        <p className="mt-3 text-sm text-ink-muted">
          Red bands: conflicts the detector sees at {fmt(minute)} (known events, accepted plan). Hatched: posted track closures.
          Red tick: a wait at the signal before entering the section.
          {hasPlan ? '' : ' "Before vs after plan" opens once a recommendation is accepted.'}
        </p>
      </Panel>
    </motion.div>
  )
}

function Legend({ primary, secondary }: { primary: string; secondary: string }) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
      <span className="flex items-center gap-2">
        <svg width="34" height="10" aria-hidden><line x1="2" x2="32" y1="5" y2="5" stroke="rgb(var(--c-ink))" strokeWidth="3.25" strokeLinecap="round" /></svg>
        <span className="text-ink">{primary}</span>
      </span>
      <span className="flex items-center gap-2">
        <svg width="34" height="10" aria-hidden><line x1="2" x2="32" y1="5" y2="5" stroke="rgb(var(--c-ink-muted))" strokeWidth="2" strokeDasharray="7 6" /></svg>
        <span className="text-ink-muted">{secondary}</span>
      </span>
    </div>
  )
}
