import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import {
  CircleCheck, CircleSlash, CircleX, Clock4, Construction, History, OctagonPause, RotateCcw, Sparkles, Zap,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useAddEvent, useNetwork, useReplayDays, useResetScenario, useScenario, type NewEvent } from '../api/hooks'
import type { Network, Scenario, Timetable } from '../api/types'
import { SignalBadge } from '../components/ui/Badges'
import { Button } from '../components/ui/Button'
import { Dialog } from '../components/ui/Dialog'
import { EmptyState } from '../components/ui/EmptyState'
import { Panel, PanelTitle } from '../components/ui/Panel'
import { SkeletonRows } from '../components/ui/Skeleton'
import { ApiError } from '../lib/api'
import { cn } from '../lib/cn'
import { ease, fadeUp, staggerContainer } from '../lib/motion'
import { EventFields } from '../features/events/EventFields'
import { useCan } from '../lib/permissions'
import { inputCls } from '../features/events/inputCls'
import { fmt } from '../lib/time'
import { DEMO_START, REPLAY_DEMO_DAY, REPLAY_DEMO_START, useConsole, useSim } from '../store/sim'
import { toast } from '../store/toast'

const PRESET: NewEvent = { event_type: 'STOPPAGE', train_id: 'T101', location: 'S_BC', start_time: '10:03', duration_min: 15 }
// Real day replay demo (docs/DEMO.md): a HYPOTHETICAL stoppage on the recorded 2024-09-12
const REAL_PRESET: NewEvent = { event_type: 'STOPPAGE', train_id: 'R22627', location: 'S_ABI_KQN', start_time: '08:53', duration_min: 25 }

export function Disruptions() {
  const scenario = useScenario()
  const network = useNetwork(scenario.data?.timetable)

  if (scenario.isError) {
    return (
      <Panel initial="hidden" animate="show">
        <EmptyState icon={<CircleSlash className="h-7 w-7" />} title="The API is not reachable">
          Start it from the backend folder with <code className="font-mono text-ink">uvicorn app.main:app --reload</code>.
        </EmptyState>
      </Panel>
    )
  }

  return (
    <motion.div className="mx-auto max-w-7xl space-y-6" variants={staggerContainer()} initial="hidden" animate="show">
      <div>
        <p className="text-sm uppercase tracking-[0.2em] text-signal-cyan">Disruption panel</p>
        <h1 className="text-3xl font-bold xl:text-4xl">Inject events into the scenario</h1>
        <p className="mt-2 max-w-3xl text-ink-muted">
          Stoppages and delays are surprises: the console, detector and optimizer only see them from their start time.
          Planned track closures are known as soon as they are posted.
        </p>
      </div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div className="space-y-6">
          <PresetCard scenario={scenario.data} />
          <EventForm network={network.data} />
        </div>
        <div className="space-y-6">
          <ScenarioControls timetable={scenario.data?.timetable} />
          <EventHistory scenario={scenario.data} />
        </div>
      </div>
    </motion.div>
  )
}

// ---- one-click preset --------------------------------------------------------------------
function PresetCard({ scenario }: { scenario: Scenario | undefined }) {
  const ctl = useCan('control')
  const add = useAddEvent()
  const reduce = useReducedMotion()
  const [fired, setFired] = useState(0)
  const real = scenario?.mode === 'replay' && scenario.replay?.date === REPLAY_DEMO_DAY
  const p = real ? REAL_PRESET : PRESET
  const exists = scenario?.events.some((e) => e.event_type === p.event_type && e.train_id === p.train_id && e.location === p.location && e.start_time === p.start_time)
  const text = real ? 'HYPOTHETICAL: 22627 stops in ABI-KQN at 08:53 for 25 min' : 'T101 stops in B-C at 10:03 for 15 min'

  const inject = () =>
    add.mutate(p, {
      onSuccess: (r) => {
        setFired((n) => n + 1)
        toast({ tone: 'critical', title: `Event ${r.event.event_id} injected`, description: `${text}. Known to the console from ${r.event.known_from}.` })
      },
      onError: (e) => toast({ tone: 'warning', title: 'Event not added', description: e instanceof ApiError ? e.message : 'Request failed' }),
    })

  return (
    <motion.section variants={fadeUp} className="glass relative overflow-hidden p-6">
      <AnimatePresence>
        {fired > 0 && !reduce && (
          <motion.div key={fired} aria-hidden className="pointer-events-none absolute inset-0"
            initial={{ opacity: 1 }} animate={{ opacity: 0 }} transition={{ duration: 0.6, delay: 0.35, ease: ease.out }}>
            <div className="absolute inset-0 bg-signal-red/15" />
            <motion.div className="absolute left-1/2 top-1/2 h-40 w-40 -ml-20 -mt-20 rounded-full border-4 border-signal-red"
              initial={{ scale: 0.2, opacity: 1 }} animate={{ scale: 3.2, opacity: 0 }} transition={{ duration: 0.55, ease: ease.out }} />
          </motion.div>
        )}
      </AnimatePresence>
      <div className="flex items-start gap-4">
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-signal-red/15 text-signal-red">
          <OctagonPause className="h-6 w-6" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold">{real ? 'Real day replay (hypothetical event)' : 'Reference scenario'}</h2>
            <SignalBadge tone="critical">Stoppage</SignalBadge>
          </div>
          {real ? (
            <p className="mt-1 text-lg text-ink">22627 stops in ABI-KQN at <span className="font-mono">08:53</span> for <span className="font-mono">25 min</span> <span className="text-sm text-ink-muted">(hypothetical, on the recorded 2024-09-12)</span></p>
          ) : (
            <p className="mt-1 text-lg text-ink">T101 stops in B-C at <span className="font-mono">10:03</span> for <span className="font-mono">15 min</span></p>
          )}
          {!real && <MiniCorridor fired={fired} />}
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button variant="danger" size="lg" icon={<Zap className="h-5 w-5" aria-hidden />} onClick={inject} lockedReason={ctl.reason}
              loading={add.isPending} disabled={exists || !scenario}>
              {exists ? 'Already injected' : 'Inject event'}
            </Button>
            <span className="text-sm text-ink-muted">Becomes known to the console at {p.start_time} (sim time).</span>
          </div>
        </div>
      </div>
    </motion.section>
  )
}

/** A–B–C–D strip; on injection a red pulse runs into B-C (transform only). */
function MiniCorridor({ fired }: { fired: number }) {
  const reduce = useReducedMotion()
  return (
    <div className="relative mt-4 h-10" aria-hidden>
      <div className="absolute inset-x-2 top-1/2 h-0.5 -translate-y-1/2 bg-line/30" />
      <div className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-signal-red/70" style={{ left: '36%', width: '28%' }} />
      {['A', 'B', 'C', 'D'].map((s, i) => (
        <span key={s} className="absolute top-1/2 grid h-7 w-7 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 border-signal-cyan bg-canvas-1 text-xs font-bold"
          style={{ left: `${[2, 36, 64, 98][i]}%` }}>{s}</span>
      ))}
      {fired > 0 && !reduce && (
        <motion.span key={fired} className="absolute top-[calc(50%-6px)] h-3 w-10 rounded-full bg-signal-red shadow-[0_0_18px_4px_rgb(var(--c-red)/0.7)]"
          style={{ left: '36%' }} initial={{ x: 0, opacity: 0 }} animate={{ x: [0, 120, 150], opacity: [0, 1, 0] }} transition={{ duration: 0.55, ease: ease.out }} />
      )}
    </div>
  )
}

// ---- custom event form (shared fields with the What-If Studio) -----------------------------------
function EventForm({ network }: { network: Network | undefined }) {
  const ctl = useCan('control')
  const add = useAddEvent()
  const post = async (ev: NewEvent): Promise<string | null> => {
    try {
      const r = await add.mutateAsync(ev)
      toast({ tone: ev.event_type === 'TRACK_UNAVAILABLE' ? 'warning' : 'critical', title: `Event ${r.event.event_id} added`,
        description: `Known from ${r.event.known_from === 'posting' ? 'now (planned closure)' : r.event.known_from}.` })
      return null
    } catch (err) {
      return err instanceof ApiError ? err.message : 'Request failed'
    }
  }
  return (
    <Panel>
      <PanelTitle hint="validated by the API">Custom event</PanelTitle>
      <EventFields network={network} onSubmit={post} submitLabel="Add event" doneLabel="Added" idPrefix="live" lockedReason={ctl.reason} />
    </Panel>
  )
}

// ---- reset ----------------------------------------------------------------------------------------
const TIMETABLE_LABEL: Record<string, string> = { reference: 'Reference', full_day: 'Full-day', custom: 'Custom (admin-edited)', dg_mdu: 'Real day' }

function ScenarioControls({ timetable }: { timetable: Timetable | undefined }) {
  const ctl = useCan('control')
  const reset = useResetScenario()
  const { setMinute, setPlaying, setRange } = useSim()
  const clearConsole = useConsole((s) => s.clear)
  const [open, setOpen] = useState(false)
  const [choice, setChoice] = useState<Timetable>('reference')
  const [demoDone, setDemoDone] = useState(false)

  const clearSession = () => {
    setPlaying(false)
    setMinute(DEMO_START)
    clearConsole()
  }

  /** One click before a demo: reference timetable, no events, clean session, clock 09:55. */
  const demoReset = () =>
    reset.mutate({ timetable: 'reference' }, {
      onSuccess: () => {
        clearSession()
        setDemoDone(true)
        window.setTimeout(() => setDemoDone(false), 1600)
        toast({ tone: 'success', title: 'Demo reset', description: 'Reference timetable, no events, no plan, clock at 09:55.' })
      },
      onError: () => toast({ tone: 'warning', title: 'Reset failed', description: 'Is the API running on port 8000?' }),
    })

  const replayDays = useReplayDays()
  const [day, setDay] = useState(REPLAY_DEMO_DAY)
  const loadReal = () =>
    reset.mutate({ timetable: 'dg_mdu', mode: 'replay', date: day }, {
      onSuccess: (s) => {
        setPlaying(false)
        if (s.replay) setRange([s.replay.window_start, s.replay.window_end]) // before the minute: it is clamped to the range
        setMinute(day === REPLAY_DEMO_DAY ? REPLAY_DEMO_START : s.replay?.window_start ?? 0)
        clearConsole()
        toast({ tone: 'success', title: 'Real day loaded', description: `REAL recorded movements, Dindigul -> Madurai, ${day}.` })
      },
      onError: (e) => toast({ tone: 'warning', title: 'Replay not loaded', description: e instanceof ApiError ? e.message : 'Request failed' }),
    })

  const confirm = () =>
    reset.mutate({ timetable: choice }, {
      onSuccess: () => {
        clearSession()
        setOpen(false)
        toast({ tone: 'success', title: 'Scenario reset', description: `${TIMETABLE_LABEL[choice]} timetable, no events, clock at 09:55.` })
      },
    })

  return (
    <Panel>
      <PanelTitle hint={timetable ? `current: ${TIMETABLE_LABEL[timetable]?.toLowerCase() ?? timetable}` : undefined}>Scenario</PanelTitle>
      <p className="text-ink-muted">Start over: clears events, the accepted plan and the decision log.</p>
      <div className="mt-4">
        <Button variant="primary" size="lg" icon={<Sparkles className="h-5 w-5" aria-hidden />} onClick={demoReset} lockedReason={ctl.reason}
          loading={reset.isPending && !open} success={demoDone}>
          {demoDone ? 'Ready at 09:55' : 'Demo reset'}
        </Button>
        <p className="mt-2 text-sm text-ink-muted">Reference timetable, clears session state, clock to 09:55, in one click.</p>
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-line/10 pt-5">
        <select value={choice} onChange={(e) => setChoice(e.target.value as Timetable)} aria-label="Timetable" className={cn(inputCls, 'w-auto')}>
          <option value="reference">Reference (3 trains)</option>
          <option value="full_day">Full day (12 trains)</option>
          <option value="custom">Custom - admin-edited (SIMULATED)</option>
        </select>
        <Button icon={<RotateCcw className="h-4 w-4" aria-hidden />} onClick={() => setOpen(true)} lockedReason={ctl.reason}>Reset scenario</Button>
      </div>
      <div className="mt-5 border-t border-line/10 pt-5">
        <p className="font-semibold">Real day replay - Dindigul to Madurai</p>
        <p className="mt-1 text-sm text-ink-muted">Recorded running times (RSTGCN Sept 2024, CC BY-SA 4.0). Trains move as recorded; anything you add is HYPOTHETICAL.</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <select value={day} onChange={(e) => setDay(e.target.value)} aria-label="Recorded day" className={cn(inputCls, 'w-auto')}>
            {(replayDays.data?.days ?? [{ date: REPLAY_DEMO_DAY, weekday: 'Thu', trains: 22, reproduced_exactly: true, recorded_overtakes: 1 }]).map((d) => (
              <option key={d.date} value={d.date}>
                {d.date} {d.weekday} - {d.trains} trains{d.date === (replayDays.data?.demo_day ?? REPLAY_DEMO_DAY) ? ' (demo day)' : ''}{d.reproduced_exactly ? '' : ' - interpolation unresolved in places'}
              </option>
            ))}
          </select>
          <Button icon={<RotateCcw className="h-4 w-4" aria-hidden />} onClick={loadReal} loading={reset.isPending && !open} lockedReason={ctl.reason}>Load real day</Button>
        </div>
      </div>
      <Dialog open={open} onOpenChange={setOpen} title="Reset the scenario?" description="Events, the accepted plan and the decision log are cleared. This cannot be undone.">
        <div className="flex justify-end gap-3">
          <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="danger" loading={reset.isPending} onClick={confirm}>Reset</Button>
        </div>
      </Dialog>
    </Panel>
  )
}

// ---- history -----------------------------------------------------------------------------------------
const eventIcon: Record<string, ReactNode> = {
  STOPPAGE: <OctagonPause className="h-4 w-4" aria-hidden />,
  DELAY: <Clock4 className="h-4 w-4" aria-hidden />,
  TRACK_UNAVAILABLE: <Construction className="h-4 w-4" aria-hidden />,
  PLATFORM_UNAVAILABLE: <Construction className="h-4 w-4" aria-hidden />,
}

function EventHistory({ scenario }: { scenario: Scenario | undefined }) {
  if (!scenario) return <Panel><SkeletonRows rows={3} label="Loading history" /></Panel>
  const items = [
    ...scenario.events.map((e) => ({
      key: e.event_id, sort: e.start_time, icon: eventIcon[e.event_type], tone: e.event_type === 'TRACK_UNAVAILABLE' ? 'text-signal-amber' : 'text-signal-red',
      title: `${e.event_id} - ${e.event_type.replace('_', ' ').toLowerCase()}${e.train_id ? ` ${e.train_id}` : ''} at ${e.location}`,
      detail: `${e.start_time} for ${e.duration_min} min - known from ${e.known_from === 'posting' ? 'posting' : e.known_from}`,
    })),
    ...scenario.decision_log.map((d) => ({
      key: `${d.recommendation_id}-${d.decision}`, sort: fmt(d.at), tone: d.decision === 'accept' ? 'text-signal-green' : 'text-ink-muted',
      icon: d.decision === 'accept' ? <CircleCheck className="h-4 w-4" aria-hidden /> : <CircleX className="h-4 w-4" aria-hidden />,
      title: `${d.recommendation_id} ${d.decision}ed - ${d.strategy}`,
      detail: `decided for clock ${fmt(d.at)}`,
    })),
  ].sort((a, b) => a.sort.localeCompare(b.sort))

  return (
    <Panel>
      <PanelTitle hint={<span className="inline-flex items-center gap-1"><History className="h-4 w-4" aria-hidden />{items.length} {items.length === 1 ? 'entry' : 'entries'}</span>}>Event history</PanelTitle>
      {items.length === 0 ? (
        <EmptyState icon={<History className="h-7 w-7" />} title="No events yet">Inject the preset or add a custom event.</EmptyState>
      ) : (
        <motion.ol variants={staggerContainer(0.06)} initial="hidden" animate="show" className="relative ml-3 border-l border-line/20">
          {items.map((it) => (
            <motion.li key={it.key} variants={fadeUp} className="relative mb-5 ml-6 last:mb-0">
              <span className={cn('absolute -left-[2.15rem] grid h-8 w-8 place-items-center rounded-full border border-line/20 bg-canvas-1', it.tone)}>{it.icon}</span>
              <p className="font-semibold">{it.title}</p>
              <p className="font-mono text-sm text-ink-muted">{it.detail}</p>
            </motion.li>
          ))}
        </motion.ol>
      )}
    </Panel>
  )
}
