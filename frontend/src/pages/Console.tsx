import { motion } from 'framer-motion'
import { ArrowRight, CircleSlash, RefreshCcw, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useEffect, useMemo, useState } from 'react'
import { useConflictsAt, useNetwork, useScenario, useStateAt } from '../api/hooks'
import type { Kpis, TrainState } from '../api/types'
import { SignalBadge, TrainChip } from '../components/ui/Badges'
import { EmptyState } from '../components/ui/EmptyState'
import { Panel, PanelTitle } from '../components/ui/Panel'
import { Skeleton, SkeletonRows } from '../components/ui/Skeleton'
import { AlertsFeed } from '../features/console/AlertsFeed'
import { ClockBar } from '../features/console/ClockBar'
import { CorridorMap } from '../features/console/CorridorMap'
import { KpiStrip } from '../features/console/KpiStrip'
import { buildGeometry } from '../features/console/geometry'
import { staggerContainer } from '../lib/motion'
import { fmt } from '../lib/time'
import { DEMO_START, minuteMs, REPLAY_DEMO_START, useConsole, useSim } from '../store/sim'


const statusText: Record<TrainState['status'], string> = {
  not_started: 'not started',
  at_station: 'at station',
  waiting_at_signal: 'waiting at signal',
  in_section: 'running',
  arrived: 'arrived',
}

export function Console() {
  const scenario = useScenario()
  const timetable = scenario.data?.timetable ?? 'reference'
  const replay = scenario.data?.mode === 'replay' ? scenario.data.replay : null
  const network = useNetwork(scenario.data ? timetable : undefined)
  const { minute, playing, speed, minuteStartedAt } = useSim()
  const { highlight, setHighlight } = useConsole()

  const now = useStateAt(minute)
  const nextQ = useStateAt(minute + 1, playing)
  const next = playing && nextQ.data && !nextQ.isPlaceholderData ? nextQ.data : null
  const conflicts = useConflictsAt(minute)

  const geo = useMemo(() => (network.data ? buildGeometry(network.data) : null), [network.data])

  // scrubber range: set app-wide by useClockRange (AppShell)

  // KPI history for sparklines: the last 30 polled minutes, restarted on a backwards jump
  const [history, setHistory] = useState<{ m: number; k: Kpis }[]>([])
  useEffect(() => {
    if (!now.data || now.isPlaceholderData) return
    setHistory((h) => {
      const last = h[h.length - 1]
      if (last && minute <= last.m) return minute === last.m ? h : [{ m: minute, k: now.data.kpis }]
      return [...h, { m: minute, k: now.data.kpis }].slice(-30)
    })
  }, [now.data, now.isPlaceholderData, minute])

  const glideMs = next ? Math.max(0, minuteMs(speed) - (performance.now() - minuteStartedAt)) : 0
  const offline = scenario.isError || now.isError

  return (
    <motion.div className="mx-auto max-w-[110rem] space-y-5" variants={staggerContainer()} initial="hidden" animate="show">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-signal-cyan">Traffic console</p>
          <h1 className="text-3xl font-bold xl:text-4xl">{replay ? 'Dindigul - Madurai (DG -> MDU)' : 'Corridor A - B - C - D'}</h1>
        </div>
        <div className="flex items-center gap-2 text-sm text-ink-muted">
          <SignalBadge tone="info">Timetable: {replay ? `real, ${replay.trains} trains on ${replay.date}` : timetable === 'full_day' ? 'full day (12 trains)' : 'reference (3 trains)'}</SignalBadge>
          {now.data && <SignalBadge tone="info">Known events: {now.data.known_events.length ? now.data.known_events.join(', ') : 'none'}</SignalBadge>}
        </div>
      </div>

      {replay && (
        <div role="note" className={`glass flex flex-wrap items-center gap-3 px-5 py-3 ${scenario.data?.data_label === 'REAL' ? 'border border-signal-green/40' : 'border border-signal-violet/40'}`}>
          <span className={`font-mono text-sm font-semibold uppercase tracking-wider ${scenario.data?.data_label === 'REAL' ? 'text-signal-green' : 'text-signal-violet'}`}>{replay.header}</span>
          {scenario.data?.data_label !== 'REAL' && (
            <span className="text-sm text-ink">HYPOTHETICAL on a real recorded day: recorded until {replay.divergence ?? 'the first event'}, simulated after it.</span>
          )}
          <span className="text-sm text-ink-muted">Positions between recorded stations are interpolated (dashed ring).</span>
        </div>
      )}

      <ClockBar resetTo={replay ? REPLAY_DEMO_START : DEMO_START} />

      {now.data?.plan.stale && (
        <motion.div role="status" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
          className="glass flex flex-wrap items-center gap-4 px-5 py-4 shadow-[0_0_0_1.5px_rgb(var(--c-cyan)),0_14px_50px_-14px_rgb(var(--c-cyan)/0.75)]">
          <RefreshCcw className="h-6 w-6 shrink-0 text-signal-cyan animate-breathe" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-lg font-semibold">New event since your accepted plan</p>
            <p className="text-sm text-ink">{now.data.plan.new_events.join(', ')} became known after plan {now.data.plan.applied}. Re-plan from the current state: trips already started stay as they are.</p>
          </div>
          <Link to="/strategies" className="inline-flex h-11 items-center gap-2 rounded-xl bg-gradient-to-r from-signal-cyan to-sky-400 px-4 font-semibold text-canvas-0 hover:shadow-glow">
            Re-optimize <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        </motion.div>
      )}

      {offline ? (
        <Panel>
          <EmptyState icon={<CircleSlash className="h-7 w-7" />} title="The API is not reachable">
            Start it from the backend folder with <code className="font-mono text-ink">uvicorn app.main:app --reload</code>.
          </EmptyState>
        </Panel>
      ) : (
        <>
          {now.data ? <KpiStrip kpis={now.data.kpis} history={history.map((h) => h.k)} /> : (
            <div className="grid grid-cols-2 gap-3 xl:grid-cols-4" role="status" aria-label="Loading KPIs">
              {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-24 rounded-2xl" />)}
            </div>
          )}

          <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_26rem]">
            <Panel className="p-4">
              <PanelTitle hint={highlight ? (
                <button onClick={() => setHighlight(null)} className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-ink hover:bg-white/5">
                  <X className="h-4 w-4" aria-hidden /> Clear highlight
                </button>
              ) : `state at ${fmt(minute)} from the API`}>Corridor map</PanelTitle>
              {geo && now.data ? (
                <CorridorMap geo={geo} now={now.data} next={next} glideMs={glideMs} minute={minute} scenario={scenario.data} highlight={highlight} />
              ) : (
                <Skeleton className="aspect-[3/1] w-full rounded-2xl" />
              )}
              <Legend />
              {now.data && (
                <ul className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3" aria-label="Trains">
                  {now.data.trains.map((t) => (
                    <li key={t.train_id} className="flex items-center justify-between gap-2 rounded-xl border border-line/10 bg-canvas-0/40 px-3 py-2">
                      <TrainChip id={t.train_id} type={t.train_type} />
                      <span className="text-sm text-ink-muted">
                        {t.stopped ? 'stopped in' : statusText[t.status]} {t.status === 'in_section' ? t.location : `at ${t.location}`}
                        {t.interpolated && <span className="ml-1 text-ink-dim">(interpolated)</span>}
                      </span>
                      <span className={t.current_delay_min > 0 ? 'font-mono text-sm font-semibold text-signal-red' : 'font-mono text-sm text-signal-green'}>
                        {t.current_delay_min > 0 ? `+${t.current_delay_min} min` : 'on time'}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>

            <Panel className="p-4">
              <PanelTitle hint={`known at ${fmt(minute)}`}>Live alerts</PanelTitle>
              {conflicts.data || conflicts.isError ? (
                conflicts.isError ? <p className="text-signal-red">Could not load conflicts.</p> : <AlertsFeed conflicts={conflicts.data} loading={conflicts.isFetching && !conflicts.data} plan={now.data?.plan} />
              ) : <SkeletonRows rows={3} label="Loading alerts" />}
              {conflicts.data?.ml_note && <p className="mt-3 text-xs text-ink-dim">Model note: {conflicts.data.ml_note}</p>}
            </Panel>
          </div>
        </>
      )}
    </motion.div>
  )
}

function Legend() {
  const item = (cls: string, label: string) => (
    <span className="inline-flex items-center gap-2"><span className={`h-1.5 w-6 rounded-full ${cls}`} aria-hidden />{label}</span>
  )
  return (
    <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm text-ink-muted">
      {item('bg-line/40', 'free')}
      {item('bg-signal-cyan', 'occupied')}
      {item('bg-signal-amber', 'full')}
      {item('bg-signal-red', 'closed')}
      <span className="inline-flex items-center gap-2"><span className="h-3 w-3 rounded-full border-2 border-signal-red" aria-hidden />delayed train</span>
      <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-signal-red" aria-hidden />red signal: waiting</span>
    </div>
  )
}
