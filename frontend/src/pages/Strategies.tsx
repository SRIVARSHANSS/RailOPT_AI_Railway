import { motion } from 'framer-motion'
import { ArrowRight, Check, CircleSlash, Gauge, Lightbulb, Scale, Sparkles, Undo2, X } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDecide, useOptimize } from '../api/hooks'
import type { OptimizeResult, Recommendation, StrategyRow } from '../api/types'
import { SignalBadge } from '../components/ui/Badges'
import { Button } from '../components/ui/Button'
import { CountUp } from '../components/ui/CountUp'
import { EmptyState } from '../components/ui/EmptyState'
import { Panel } from '../components/ui/Panel'
import { ParticleBurst } from '../components/ui/ParticleBurst'
import { SkeletonRows } from '../components/ui/Skeleton'
import { ApiError } from '../lib/api'
import { cn } from '../lib/cn'
import { duration, ease, fadeUp, staggerContainer } from '../lib/motion'
import { fmt } from '../lib/time'
import { useConsole, useSim } from '../store/sim'
import { toast } from '../store/toast'

const LABEL: Record<string, string> = {
  NO_REPLANNING: 'No re-planning',
  PRIORITY_DISPATCH: 'Priority dispatch',
  HOLD: 'A - Hold',
  REROUTE: 'B - Reroute',
  RESEQUENCE: 'C - Resequence',
  COMBINED: 'D - Combined',
}

export function Strategies() {
  const minute = useSim((s) => s.minute)
  const { optimize, setOptimize } = useConsole()
  const run = useOptimize()
  const [error, setError] = useState<string | null>(null)

  const go = () => {
    setError(null)
    run.mutate(minute, {
      onSuccess: (r) => {
        setOptimize(r)
        if (r.recommendation) toast({ tone: 'ai', title: `Recommendation ${r.recommendation.recommendation_id}: ${LABEL[r.recommendation.strategy] ?? r.recommendation.strategy}`, description: `Weighted delay ${r.recommendation.weighted_delay} (${r.recommendation.explanation.delta_weighted_delay >= 0 ? '+' : ''}${r.recommendation.explanation.delta_weighted_delay}).` })
      },
      onError: (e) => setError(e instanceof ApiError ? e.message : 'The API is not reachable. Start it with uvicorn app.main:app --reload.'),
    })
  }

  return (
    <motion.div className="mx-auto max-w-7xl space-y-6" variants={staggerContainer()} initial="hidden" animate="show">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-signal-cyan">Strategy comparison</p>
          <h1 className="text-3xl font-bold xl:text-4xl">Re-plan the corridor</h1>
          <p className="mt-2 max-w-3xl text-ink-muted">
            Every plan is replayed through the simulator; the numbers below come from those replays (SIMULATED).
            {optimize && <> Last run at <span className="font-mono text-ink">{optimize.at}</span>, known events: {optimize.known_events.join(', ') || 'none'}.</>}
          </p>
        </div>
        <Button variant="primary" size="lg" icon={<Sparkles className="h-5 w-5" aria-hidden />} loading={run.isPending} onClick={go}>
          Run optimizer at {fmt(minute)}
        </Button>
      </div>

      {error && <Panel><EmptyState icon={<CircleSlash className="h-7 w-7" />} title="Optimizer unavailable">{error}</EmptyState></Panel>}

      {run.isPending && !optimize ? (
        <Panel><SkeletonRows rows={5} label="Solving strategies" /></Panel>
      ) : !optimize ? (
        <Panel>
          <EmptyState icon={<Scale className="h-7 w-7" />} title="No comparison yet"
            action={<Button variant="primary" onClick={go} loading={run.isPending}>Run optimizer at {fmt(minute)}</Button>}>
            The optimizer compares hold, reroute, resequence and combined plans against no re-planning and priority dispatch,
            using only the events known at the sim time.
          </EmptyState>
        </Panel>
      ) : (
        <>
          {optimize.replanning_from && (
            <Panel className="border-signal-cyan/40">
              <div className="flex flex-wrap items-center gap-3">
                <SignalBadge tone="ai">Re-planning</SignalBadge>
                <p className="min-w-0 flex-1 text-ink">
                  From the current state on top of accepted plan <span className="font-mono">{optimize.replanning_from}</span>:
                  trips already started stay as that plan made them; the baselines keep it, the strategies re-plan the rest.
                </p>
              </div>
            </Panel>
          )}
          <Results result={optimize} />
        </>
      )}
    </motion.div>
  )
}

function Results({ result }: { result: OptimizeResult }) {
  const rec = result.recommendation
  const base = result.results.find((r) => r.name === 'NO_REPLANNING')
  const maxDelay = Math.max(1, ...result.results.flatMap((r) => Object.values(r.delays)))
  return (
    <>
      {rec && base && <RecommendationCard rec={rec} base={base} />}
      <motion.div variants={staggerContainer(0.06)} initial="hidden" animate="show" className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {result.results.map((r) => (
          <StrategyCard key={r.name} row={r} recommended={rec?.strategy === r.name} maxDelay={maxDelay} />
        ))}
      </motion.div>
    </>
  )
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'OPTIMAL') return <SignalBadge tone="success">CP-SAT optimal</SignalBadge>
  if (status === 'FEASIBLE') return <SignalBadge tone="warning">Feasible - not proven optimal</SignalBadge>
  if (status === 'BASELINE') return <SignalBadge tone="info">Baseline</SignalBadge>
  return <SignalBadge tone="critical">{status}</SignalBadge>
}

function StrategyCard({ row, recommended, maxDelay }: { row: StrategyRow; recommended: boolean; maxDelay: number }) {
  return (
    <motion.article variants={fadeUp}
      className={cn('glass relative p-5', recommended && 'shadow-[0_0_0_1.5px_rgb(var(--c-cyan)),0_18px_50px_-18px_rgb(var(--c-cyan)/0.7)]')}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-lg font-semibold">{LABEL[row.name] ?? row.name}{row.message.startsWith('keeps') && <span className="block text-sm font-normal text-ink-muted">keeps the accepted plan</span>}</h3>
        {recommended ? <SignalBadge tone="ai">Recommended</SignalBadge> : <StatusBadge status={row.status} />}
      </div>
      {recommended && <div className="mt-2"><StatusBadge status={row.status} /></div>}
      {row.weighted_delay === null ? (
        <p className="mt-4 text-signal-red">{row.message || 'No plan for this strategy.'}</p>
      ) : (
        <>
          <dl className="mt-4 grid grid-cols-3 gap-2">
            <Metric label="Weighted" value={row.weighted_delay} strong={recommended} />
            <Metric label="Total min" value={row.total_delay ?? 0} />
            <Metric label="Trains/h" value={row.throughput_trains_per_hour ?? 0} decimals={2} />
          </dl>
          <div className="mt-4 space-y-1.5" aria-label="Delay per train">
            {Object.entries(row.delays).map(([train, d]) => (
              <div key={train} className="flex items-center gap-2 text-sm">
                <span className="w-12 font-mono text-ink-muted">{train}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                  <motion.div className={cn('h-full origin-left rounded-full', d === 0 ? 'bg-signal-green' : recommended ? 'bg-signal-cyan' : 'bg-signal-amber')}
                    initial={{ scaleX: 0 }} animate={{ scaleX: Math.max(d / maxDelay, d === 0 ? 0.02 : 0) }}
                    transition={{ duration: duration.slow * 2, ease: ease.out }} />
                </div>
                <span className="w-14 text-right font-mono tabular">{d} min</span>
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm text-ink">
            {row.actions.length ? row.actions.join('; ') : row.kind === 'baseline' ? 'Plain simulator run - no controller actions.' : 'No action needed.'}
          </p>
          {row.solve_seconds !== null && <p className="mt-2 font-mono text-xs text-ink-dim">solved in {row.solve_seconds.toFixed(3)} s - {row.violations ?? 0} violations in replay</p>}
        </>
      )}
    </motion.article>
  )
}

function Metric({ label, value, decimals = 0, strong }: { label: string; value: number; decimals?: number; strong?: boolean }) {
  return (
    <div className="rounded-xl bg-canvas-0/40 px-3 py-2">
      <dt className="text-xs uppercase tracking-wider text-ink-dim">{label}</dt>
      <dd className={cn('text-2xl font-semibold', strong && 'text-signal-cyan')}><CountUp value={value} decimals={decimals} durationS={0.7} /></dd>
    </div>
  )
}

function RecommendationCard({ rec, base }: { rec: Recommendation; base: StrategyRow }) {
  const decide = useDecide()
  const navigate = useNavigate()
  const { decided, markDecided } = useConsole()
  const [burst, setBurst] = useState(0)
  const state = decided[rec.recommendation_id]
  const baseW = base.weighted_delay ?? 0
  const max = Math.max(1, baseW, rec.weighted_delay)

  const choose = (d: 'accept' | 'reject') =>
    decide.mutate({ id: rec.recommendation_id, decision: d }, {
      onSuccess: () => {
        markDecided(rec.recommendation_id, d)
        if (d === 'accept') {
          setBurst((n) => n + 1)
          toast({ tone: 'success', title: `${LABEL[rec.strategy] ?? rec.strategy} accepted`, description: 'Applied to the scenario. Opening the console.' })
          window.setTimeout(() => navigate('/console'), 900)
        } else {
          toast({ tone: 'info', title: 'Recommendation rejected', description: 'The plan is unchanged. The decision is logged.' })
        }
      },
      onError: (e) => toast({ tone: 'warning', title: 'Decision not recorded', description: e instanceof ApiError ? e.message : 'Request failed' }),
    })

  return (
    <motion.section variants={fadeUp} animate={{ opacity: state === 'reject' ? 0.6 : 1 }}
      className="glass relative overflow-hidden p-6 shadow-[0_0_0_1.5px_rgb(var(--c-cyan)/0.8),0_24px_70px_-24px_rgb(var(--c-cyan)/0.6)]">
      <div className="flex flex-wrap items-center gap-3">
        <SignalBadge tone="ai">Recommended</SignalBadge>
        <h2 className="text-2xl font-bold">{LABEL[rec.strategy] ?? rec.strategy}</h2>
        <span className="font-mono text-sm text-ink-muted">{rec.recommendation_id}</span>
        {state === 'accept' && <SignalBadge tone="success">Accepted</SignalBadge>}
        {state === 'reject' && <SignalBadge tone="info">Rejected</SignalBadge>}
      </div>
      <p className="mt-2 text-lg">{rec.actions.join('; ') || 'No action needed.'}</p>

      {/* animated comparison: no re-planning -> recommended, weighted delay */}
      <div className="mt-5 space-y-3" aria-label={`Weighted delay ${baseW} without re-planning, ${rec.weighted_delay} with ${rec.strategy}`}>
        {[{ label: base.message.startsWith('keeps') ? 'Keep current plan' : 'No re-planning', v: baseW, cls: 'bg-signal-amber' }, { label: LABEL[rec.strategy] ?? rec.strategy, v: rec.weighted_delay, cls: 'bg-signal-cyan' }].map((b, i) => (
          <div key={b.label} className="grid grid-cols-[9rem_1fr_4rem] items-center gap-3">
            <span className="text-sm text-ink-muted">{b.label}</span>
            <div className="h-4 overflow-hidden rounded-full bg-white/[0.06]">
              <motion.div className={cn('h-full origin-left rounded-full', b.cls)} initial={{ scaleX: 0 }} animate={{ scaleX: b.v / max }}
                transition={{ duration: 0.9, delay: 0.15 + i * 0.25, ease: ease.out }} />
            </div>
            <span className="text-right font-mono text-xl font-semibold"><CountUp value={b.v} /></span>
          </div>
        ))}
        <p className="font-mono text-ink">
          weighted <span className="text-signal-amber">{baseW}</span> <ArrowRight className="inline h-4 w-4" aria-hidden /> <span className="text-signal-cyan">{rec.weighted_delay}</span>
          {' '}({rec.explanation.delta_weighted_delay}), total {base.total_delay} <ArrowRight className="inline h-4 w-4" aria-hidden /> {rec.total_delay} min ({rec.explanation.delta_total_delay_min})
        </p>
      </div>

      {/* explanation: the API's own sentences */}
      <div className="mt-6 grid gap-3 lg:grid-cols-3">
        <Explain icon={<Lightbulb className="h-4 w-4" />} title="Why" text={rec.explanation.reason} />
        <Explain icon={<Undo2 className="h-4 w-4" />} title="If we do nothing" text={rec.explanation.counterfactual} />
        <Explain icon={<Gauge className="h-4 w-4" />} title="Expected impact" text={rec.explanation.expected_impact} />
      </div>
      <p className="mt-3 text-sm text-ink-muted">{rec.explanation.solver} {rec.explanation.note}</p>

      <div className="mt-6 flex flex-wrap gap-3">
        <span className="relative">
          <Button variant="primary" size="lg" icon={<Check className="h-5 w-5" aria-hidden />} onClick={() => choose('accept')}
            loading={decide.isPending && decide.variables?.decision === 'accept'} success={state === 'accept'} disabled={Boolean(state)}>
            {state === 'accept' ? 'Plan applied' : 'Accept plan'}
          </Button>
          <ParticleBurst run={burst} />
        </span>
        <Button variant="ghost" size="lg" icon={<X className="h-5 w-5" aria-hidden />} onClick={() => choose('reject')}
          loading={decide.isPending && decide.variables?.decision === 'reject'} disabled={Boolean(state)}>
          Reject
        </Button>
      </div>
    </motion.section>
  )
}

function Explain({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return (
    <div className="rounded-xl border border-line/15 bg-canvas-0/40 p-4">
      <p className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-signal-cyan">{icon}{title}</p>
      <p className="mt-2 text-ink">{text}</p>
    </div>
  )
}
