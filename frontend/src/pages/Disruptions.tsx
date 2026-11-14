import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import {
  CircleCheck, CircleSlash, CircleX, Clock4, Construction, History, OctagonPause, RotateCcw, Zap,
} from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { useAddEvent, useNetwork, useResetScenario, useScenario, type NewEvent } from '../api/hooks'
import type { EventType, Network, Scenario, Timetable } from '../api/types'
import { SignalBadge } from '../components/ui/Badges'
import { Button } from '../components/ui/Button'
import { Dialog } from '../components/ui/Dialog'
import { EmptyState } from '../components/ui/EmptyState'
import { Panel, PanelTitle } from '../components/ui/Panel'
import { SkeletonRows } from '../components/ui/Skeleton'
import { TabPanel, Tabs } from '../components/ui/Tabs'
import { ApiError } from '../lib/api'
import { cn } from '../lib/cn'
import { duration, ease, fadeUp, staggerContainer } from '../lib/motion'
import { fmt } from '../lib/time'
import { useConsole, useSim } from '../store/sim'
import { toast } from '../store/toast'

const PRESET: NewEvent = { event_type: 'STOPPAGE', train_id: 'T101', location: 'S_BC', start_time: '10:03', duration_min: 15 }

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
  const add = useAddEvent()
  const reduce = useReducedMotion()
  const [fired, setFired] = useState(0)
  const exists = scenario?.events.some((e) => e.event_type === 'STOPPAGE' && e.train_id === 'T101' && e.location === 'S_BC' && e.start_time === '10:03')

  const inject = () =>
    add.mutate(PRESET, {
      onSuccess: (r) => {
        setFired((n) => n + 1)
        toast({ tone: 'critical', title: `Event ${r.event.event_id} injected`, description: `T101 stops in B-C at 10:03 for 15 min. Known to the console from ${r.event.known_from}.` })
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
            <h2 className="text-xl font-semibold">Reference scenario</h2>
            <SignalBadge tone="critical">Stoppage</SignalBadge>
          </div>
          <p className="mt-1 text-lg text-ink">T101 stops in B-C at <span className="font-mono">10:03</span> for <span className="font-mono">15 min</span></p>
          <MiniCorridor fired={fired} />
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button variant="danger" size="lg" icon={<Zap className="h-5 w-5" aria-hidden />} onClick={inject}
              loading={add.isPending} disabled={exists || !scenario}>
              {exists ? 'Already injected' : 'Inject event'}
            </Button>
            <span className="text-sm text-ink-muted">Becomes known to the console at 10:03 (sim time).</span>
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

// ---- custom event form ------------------------------------------------------------------------
const TAB_ITEMS = [
  { value: 'STOPPAGE', label: 'Stoppage' },
  { value: 'DELAY', label: 'Delay' },
  { value: 'TRACK_UNAVAILABLE', label: 'Track closure' },
  { value: 'PLATFORM_UNAVAILABLE', label: 'Platform', disabled: true, hint: 'not modelled yet' },
]

function EventForm({ network }: { network: Network | undefined }) {
  const add = useAddEvent()
  const [type, setType] = useState<EventType>('STOPPAGE')
  const [train, setTrain] = useState('T202')
  const [location, setLocation] = useState('')
  const [start, setStart] = useState('10:10')
  const [dur, setDur] = useState(5)
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  const needsTrain = type === 'STOPPAGE' || type === 'DELAY'
  const locations = !network ? [] : type === 'DELAY'
    ? network.stations.map((s) => ({ v: s.code, l: `${s.code} - ${s.name}` }))
    : network.sections.map((s) => ({ v: s.section_id, l: `${s.section_id} (${s.from_station}-${s.to_station})` }))
  const loc = locations.some((o) => o.v === location) ? location : locations[0]?.v ?? ''

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    add.mutate(
      { event_type: type, train_id: needsTrain ? train : null, location: loc, start_time: start, duration_min: dur },
      {
        onSuccess: (r) => {
          setOk(true)
          window.setTimeout(() => setOk(false), 1400)
          toast({ tone: type === 'TRACK_UNAVAILABLE' ? 'warning' : 'critical', title: `Event ${r.event.event_id} added`, description: `Known from ${r.event.known_from === 'posting' ? 'now (planned closure)' : r.event.known_from}.` })
        },
        onError: (err) => setError(err instanceof ApiError ? err.message : 'Request failed'),
      },
    )
  }

  return (
    <Panel>
      <PanelTitle hint="validated by the API">Custom event</PanelTitle>
      {!network ? <SkeletonRows rows={3} label="Loading network" /> : (
        <Tabs value={type} onValueChange={(v) => { setType(v as EventType); setError(null) }} label="Event type" items={TAB_ITEMS}>
          {TAB_ITEMS.filter((t) => !t.disabled).map((t) => (
            <TabPanel key={t.value} value={t.value}>
              <motion.form key={t.value} onSubmit={submit} className="grid gap-4 sm:grid-cols-2"
                initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: duration.base, ease: ease.out }}>
                {needsTrain && (
                  <Field label="Train">
                    <select value={train} onChange={(e) => setTrain(e.target.value)} className={inputCls}>
                      {network.trains.map((tr) => <option key={tr.train_id} value={tr.train_id}>{tr.train_id} - {tr.train_type.toLowerCase()}</option>)}
                    </select>
                  </Field>
                )}
                <Field label={type === 'DELAY' ? 'Station' : 'Section'}>
                  <select value={loc} onChange={(e) => setLocation(e.target.value)} className={inputCls}>
                    {locations.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
                  </select>
                </Field>
                <Field label="Start time (sim)">
                  <input type="text" inputMode="numeric" pattern="([01]\d|2[0-3]):[0-5]\d" value={start} onChange={(e) => setStart(e.target.value)}
                    className={cn(inputCls, 'font-mono')} aria-describedby="start-help" required />
                  <span id="start-help" className="text-xs text-ink-dim">HH:MM</span>
                </Field>
                <Field label="Duration (min)">
                  <input type="number" min={1} max={600} value={dur} onChange={(e) => setDur(Number(e.target.value))} className={cn(inputCls, 'font-mono')} required />
                </Field>
                <div className="sm:col-span-2">
                  <AnimatePresence>
                    {error && (
                      <motion.p role="alert" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                        className="mb-3 rounded-xl border border-signal-red/40 bg-signal-red/10 px-3 py-2 text-sm text-signal-red">{error}</motion.p>
                    )}
                  </AnimatePresence>
                  <Button type="submit" variant="primary" loading={add.isPending} success={ok}>{ok ? 'Added' : 'Add event'}</Button>
                </div>
              </motion.form>
            </TabPanel>
          ))}
        </Tabs>
      )}
    </Panel>
  )
}

const inputCls = 'h-11 w-full rounded-xl border border-line/20 bg-canvas-0/60 px-3 text-ink'

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 text-sm text-ink-muted">
      {label}
      {children}
    </label>
  )
}

// ---- reset ----------------------------------------------------------------------------------------
function ScenarioControls({ timetable }: { timetable: Timetable | undefined }) {
  const reset = useResetScenario()
  const { setMinute, setPlaying } = useSim()
  const { setOptimize, setHighlight } = useConsole()
  const [open, setOpen] = useState(false)
  const [choice, setChoice] = useState<Timetable>('reference')

  const confirm = () =>
    reset.mutate(choice, {
      onSuccess: () => {
        setPlaying(false)
        setMinute(9 * 60 + 55)
        setOptimize(null)
        setHighlight(null)
        setOpen(false)
        toast({ tone: 'success', title: 'Scenario reset', description: `${choice === 'full_day' ? 'Full-day' : 'Reference'} timetable, no events, clock at 09:55.` })
      },
    })

  return (
    <Panel>
      <PanelTitle hint={timetable ? `current: ${timetable === 'full_day' ? 'full day' : 'reference'}` : undefined}>Scenario</PanelTitle>
      <p className="text-ink-muted">Start over: clears events, the accepted plan and the decision log.</p>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <select value={choice} onChange={(e) => setChoice(e.target.value as Timetable)} aria-label="Timetable" className={cn(inputCls, 'w-auto')}>
          <option value="reference">Reference (3 trains)</option>
          <option value="full_day">Full day (12 trains)</option>
        </select>
        <Button icon={<RotateCcw className="h-4 w-4" aria-hidden />} onClick={() => setOpen(true)}>Reset scenario</Button>
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
