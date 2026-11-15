import { AnimatePresence, motion } from 'framer-motion'
import { CircleSlash, Clock4, Construction, FlaskConical, OctagonPause, Play, Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useNetwork, useScenario, useWhatIf, type NewEvent } from '../api/hooks'
import type { StrategyRow, WhatIfResult, WhatIfSide } from '../api/types'
import { SignalBadge } from '../components/ui/Badges'
import { Button } from '../components/ui/Button'
import { CountUp } from '../components/ui/CountUp'
import { EmptyState } from '../components/ui/EmptyState'
import { Panel, PanelTitle } from '../components/ui/Panel'
import { SkeletonRows } from '../components/ui/Skeleton'
import { EventFields } from '../features/events/EventFields'
import { ApiError } from '../lib/api'
import { cn } from '../lib/cn'
import { duration, ease, fadeUp, staggerContainer } from '../lib/motion'
import { fmt } from '../lib/time'
import { useSim } from '../store/sim'

const MAX_EVENTS = 3
const icon: Record<string, ReactNode> = {
  STOPPAGE: <OctagonPause className="h-4 w-4" aria-hidden />,
  DELAY: <Clock4 className="h-4 w-4" aria-hidden />,
  TRACK_UNAVAILABLE: <Construction className="h-4 w-4" aria-hidden />,
}

function HypotheticalBadge() {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border-2 border-signal-violet bg-signal-violet/15 px-4 py-1.5 text-sm font-bold uppercase tracking-[0.18em] text-signal-violet">
      <FlaskConical className="h-4 w-4" aria-hidden /> Hypothetical
    </span>
  )
}

/** What-If Studio: events are applied by the API to a COPY of the scenario. Nothing live changes. */
export function WhatIf() {
  const scenario = useScenario()
  const network = useNetwork(scenario.data?.timetable)
  const minute = useSim((s) => s.minute)
  const run = useWhatIf()
  const [events, setEvents] = useState<NewEvent[]>([])
  const [result, setResult] = useState<WhatIfResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const go = () => {
    setError(null)
    run.mutate({ minute, events }, {
      onSuccess: setResult,
      onError: (e) => setError(e instanceof ApiError ? e.message : 'The API is not reachable.'),
    })
  }

  if (scenario.isError) {
    return (
      <Panel initial="hidden" animate="show">
        <EmptyState icon={<CircleSlash className="h-7 w-7" />} title="The API is not reachable">
          Start it from the backend folder with <code className="font-mono text-ink">uvicorn app.main:app</code>.
        </EmptyState>
      </Panel>
    )
  }

  return (
    <motion.div className="mx-auto max-w-7xl space-y-6" variants={staggerContainer()} initial="hidden" animate="show">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-signal-violet">What-if studio</p>
          <h1 className="text-3xl font-bold xl:text-4xl">Try events without touching the live scenario</h1>
          <p className="mt-2 max-w-3xl text-ink-muted">
            Build up to three hypothetical events. The API applies them to a copy of the scenario (events and accepted plan),
            treats them as known at <span className="font-mono text-ink">{fmt(minute)}</span>, and compares it with the current scenario.
          </p>
        </div>
        <HypotheticalBadge />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <Panel>
          <PanelTitle hint={`${events.length} / ${MAX_EVENTS}`}>Hypothetical event</PanelTitle>
          <EventFields network={network.data} idPrefix="whatif" submitLabel="Add to what-if" doneLabel="Added"
            disabled={events.length >= MAX_EVENTS}
            onSubmit={async (ev) => {
              if (events.length >= MAX_EVENTS) return `At most ${MAX_EVENTS} hypothetical events.`
              setEvents((xs) => [...xs, ev])
              setResult(null)
              return null
            }} />
        </Panel>

        <Panel>
          <PanelTitle hint="not posted to the scenario">Hypothesis</PanelTitle>
          {events.length === 0 ? (
            <EmptyState icon={<FlaskConical className="h-7 w-7" />} title="No hypothetical events yet">Add one with the form.</EmptyState>
          ) : (
            <ol className="space-y-2">
              <AnimatePresence initial={false}>
                {events.map((ev, i) => (
                  <motion.li key={`${i}-${ev.event_type}-${ev.location}-${ev.start_time}`} layout
                    initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }}
                    transition={{ duration: duration.base, ease: ease.out }}
                    className="flex items-center gap-3 rounded-xl border border-signal-violet/30 bg-signal-violet/10 px-3 py-2">
                    <span className="font-mono text-sm text-signal-violet">H{i + 1}</span>
                    <span className="text-signal-violet">{icon[ev.event_type]}</span>
                    <span className="min-w-0 flex-1 text-sm">
                      {ev.event_type.replace('_', ' ').toLowerCase()} {ev.train_id ?? ''} at {ev.location}, {ev.start_time} for {ev.duration_min} min
                    </span>
                    <button aria-label={`Remove hypothetical event ${i + 1}`} onClick={() => { setEvents((xs) => xs.filter((_, j) => j !== i)); setResult(null) }}
                      className="rounded-lg p-1.5 text-ink-muted hover:bg-white/5 hover:text-ink">
                      <Trash2 className="h-4 w-4" aria-hidden />
                    </button>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ol>
          )}
          <AnimatePresence>
            {error && (
              <motion.p role="alert" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                className="mt-4 rounded-xl border border-signal-red/40 bg-signal-red/10 px-3 py-2 text-sm text-signal-red">{error}</motion.p>
            )}
          </AnimatePresence>
          <div className="mt-5">
            <Button variant="primary" size="lg" icon={<Play className="h-5 w-5" aria-hidden />} onClick={go}
              loading={run.isPending} disabled={events.length === 0}>
              Run what-if at {fmt(minute)}
            </Button>
          </div>
        </Panel>
      </div>

      {run.isPending && !result ? <Panel><SkeletonRows rows={4} label="Comparing current and hypothetical" /></Panel> : null}
      {result && <Comparison result={result} />}
    </motion.div>
  )
}

function Comparison({ result }: { result: WhatIfResult }) {
  const all = [result.current, result.hypothetical].flatMap((s) => s.results.flatMap((r) => Object.values(r.delays)))
  const maxDelay = Math.max(1, ...all)
  return (
    <motion.section variants={fadeUp} initial="hidden" animate="show" className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <HypotheticalBadge />
        <SignalBadge tone="info">SIMULATED</SignalBadge>
        <p className="text-sm text-ink">{result.note} Clock {result.at}.</p>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <SideCard title="Current scenario" side={result.current} maxDelay={maxDelay} />
        <SideCard title="Hypothetical" side={result.hypothetical} maxDelay={maxDelay} hypothetical />
      </div>
    </motion.section>
  )
}

function SideCard({ title, side, maxDelay, hypothetical }: { title: string; side: WhatIfSide; maxDelay: number; hypothetical?: boolean }) {
  const base = side.results.find((r) => r.name === 'NO_REPLANNING')
  const rec = side.recommendation
  const recRow = rec ? side.results.find((r) => r.name === rec.strategy) : undefined
  const flags = side.ml_watchlist.filter((w) => !w.resolved_by_plan && !w.reduced_by_plan).length
  return (
    <div className={cn('glass p-5', hypothetical && 'shadow-[0_0_0_1.5px_rgb(var(--c-violet)),0_18px_50px_-18px_rgb(var(--c-violet)/0.6)]')}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-semibold">{title}</h2>
        {hypothetical ? <HypotheticalBadge /> : <SignalBadge tone="info">Live</SignalBadge>}
      </div>
      <p className="mt-1 font-mono text-sm text-ink-muted">known: {side.known_events.join(', ') || 'none'}</p>

      <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Kpi label="Conflicts" value={side.conflicts.length} tone={side.conflicts.length ? 'text-signal-red' : 'text-signal-green'} />
        <Kpi label="AI flags" value={flags} tone={flags ? 'text-signal-amber' : undefined} />
        <Kpi label="Weighted (keep)" value={base?.weighted_delay ?? 0} />
        <Kpi label="Weighted (rec.)" value={rec?.weighted_delay ?? 0} tone="text-signal-cyan" />
      </dl>

      <div className="mt-5">
        <p className="text-sm font-semibold uppercase tracking-wider text-ink-dim">Delay per train</p>
        <DelayBars label={base?.message.startsWith('keeps') ? 'keep current plan' : 'no re-planning'} row={base} maxDelay={maxDelay} cls="bg-signal-amber" />
        {recRow && <DelayBars label={`recommended: ${rec?.strategy}`} row={recRow} maxDelay={maxDelay} cls="bg-signal-cyan" />}
      </div>

      <div className="mt-5 rounded-xl border border-line/15 bg-canvas-0/40 p-4">
        {rec ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <SignalBadge tone="ai">Recommended</SignalBadge>
              <span className="font-semibold">{rec.strategy}</span>
              <SignalBadge tone={rec.status === 'OPTIMAL' ? 'success' : 'warning'}>{rec.status === 'OPTIMAL' ? 'CP-SAT optimal' : `${rec.status} - not proven optimal`}</SignalBadge>
            </div>
            <p className="mt-2 text-ink">{rec.actions.join('; ') || 'No action needed.'}</p>
            <p className="mt-1 text-sm text-ink">{rec.explanation.expected_impact}</p>
            {hypothetical && <p className="mt-2 text-xs text-ink-muted">Hypothetical recommendation: it cannot be accepted. Post the events on Disruptions to act on them.</p>}
          </>
        ) : <p className="text-ink">No strategy found a plan.</p>}
      </div>
    </div>
  )
}

function Kpi({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded-xl bg-canvas-0/40 px-3 py-2">
      <dt className="text-xs uppercase tracking-wider text-ink-dim">{label}</dt>
      <dd className={cn('text-2xl font-semibold', tone ?? 'text-ink')}><CountUp value={value} durationS={0.6} /></dd>
    </div>
  )
}

function DelayBars({ label, row, maxDelay, cls }: { label: string; row: StrategyRow | undefined; maxDelay: number; cls: string }) {
  if (!row) return null
  return (
    <div className="mt-3">
      <p className="mb-1 text-sm text-ink-muted">{label}</p>
      <div className="space-y-1.5">
        {Object.entries(row.delays).map(([train, d]) => (
          <div key={train} className="flex items-center gap-2 text-sm">
            <span className="w-12 font-mono text-ink-muted">{train}</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
              <motion.div className={cn('h-full origin-left rounded-full', d === 0 ? 'bg-signal-green' : cls)}
                initial={{ scaleX: 0 }} animate={{ scaleX: Math.max(d / maxDelay, d === 0 ? 0.02 : 0) }}
                transition={{ duration: duration.slow * 2, ease: ease.out }} />
            </div>
            <span className="w-14 text-right font-mono tabular">{d} min</span>
          </div>
        ))}
      </div>
    </div>
  )
}
