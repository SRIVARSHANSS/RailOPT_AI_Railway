import { motion } from 'framer-motion'
import { AlertTriangle, Cpu, Radio } from 'lucide-react'
import { useState } from 'react'
import { useEvaluation, useScenario, useStateAt } from '../api/hooks'
import type { EvalSettingName, EvalSummary } from '../api/types'
import { SignalBadge } from '../components/ui/Badges'
import { Panel, PanelTitle } from '../components/ui/Panel'
import { Tabs } from '../components/ui/Tabs'
import { KpiStrip } from '../features/console/KpiStrip'
import { BarChart } from '../features/results/BarChart'
import { BASELINES, ci, f, label, METRIC_LABEL, signed } from '../features/results/format'
import { ReductionChart } from '../features/results/ReductionChart'
import { ResultsGate } from '../features/results/ResultsGate'
import { VariantsTable } from '../features/results/VariantsTable'
import { cn } from '../lib/cn'
import { fadeUp, staggerContainer } from '../lib/motion'
import { fmt } from '../lib/time'
import { useSim } from '../store/sim'

const PHASE10 = ['NO_REPLANNING', 'PRIORITY_DISPATCH', 'SINGLE_SHOT', 'DYNAMIC', 'DYNAMIC_ML']
const TABLE_METRICS = ['weighted_delay', 'avg_delay_min', 'total_delay_min', 'max_delay_min', 'total_wait_min', 'trains_waited', 'throughput_trains_per_hour']

/** Analytics: the stored Phase 10/10b evaluation (GET /api/evaluation) + live session KPIs. SIMULATED. */
export function Analytics() {
  const ev = useEvaluation()
  const [setting, setSetting] = useState<EvalSettingName>('deterministic')
  const [metric, setMetric] = useState('weighted_delay')
  const s = ev.data?.summary

  return (
    <motion.div className="mx-auto max-w-[96rem] space-y-6" variants={staggerContainer()} initial="hidden" animate="show">
      <motion.div variants={fadeUp} className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-signal-cyan">Analytics</p>
          <h1 className="text-3xl font-bold xl:text-4xl">
            {s ? `Evaluation on ${s.config.scenarios} simulated scenarios` : 'Evaluation'}
          </h1>
          <p className="mt-2 max-w-3xl text-ink-muted">
            Stored results of <code className="font-mono text-ink">{ev.data?.command ?? 'python -m eval.run_eval'}</code>: every method on the same
            scenarios, replayed through the simulator. Nothing on this page is recomputed.
          </p>
        </div>
        <SignalBadge tone="info">SIMULATED</SignalBadge>
      </motion.div>

      <LiveSession />

      <ResultsGate loading={ev.isLoading} error={ev.isError} status={ev.data?.status} reasons={ev.data?.reasons ?? []}
        command={ev.data?.command ?? ''} what="evaluation results">
        {s && ev.data && (
          <>
            <SetupStrip s={s} />
            <Panel>
              <div className="flex flex-wrap items-center justify-between gap-4">
                <Tabs value={setting} onValueChange={(v) => setSetting(v as EvalSettingName)} label="Evaluation setting"
                  items={[{ value: 'deterministic', label: 'Deterministic replay' }, { value: 'robustness', label: `Robustness (${s.config.replays} seeded replays)` }]}>{null}</Tabs>
                <label className="flex items-center gap-2 text-sm text-ink-muted">
                  Metric
                  <select value={metric} onChange={(e) => setMetric(e.target.value)}
                    className="rounded-lg border border-line/20 bg-canvas-1 px-3 py-1.5 text-ink">
                    {TABLE_METRICS.map((k) => <option key={k} value={k}>{METRIC_LABEL[k].label}</option>)}
                  </select>
                </label>
              </div>
              <h2 className="mt-5 text-xl font-semibold">{METRIC_LABEL[metric].label} per scenario: mean with 95% bootstrap CI</h2>
              <div className="mt-3">
                <BarChart key={`${setting}-${metric}`} ariaLabel={`${METRIC_LABEL[metric].label}, ${setting}, mean with 95% CI (simulated)`}
                  digits={METRIC_LABEL[metric].digits} unit={METRIC_LABEL[metric].unit}
                  bars={PHASE10.map((m) => {
                    const d = s.settings[setting].methods[m][metric]
                    return { key: m, label: label(m), value: d.mean, ci: d.mean_ci, tone: BASELINES.has(m) ? 'baseline' : m === 'DYNAMIC_ML' ? 'ml' : 'ai' }
                  })} />
              </div>
              <MethodsTable s={s} setting={setting} />
            </Panel>

            {ev.data.distribution?.[setting] && (
              <Panel>
                <PanelTitle hint={`${setting}; above 0 = less weighted delay than no re-planning`}>Per-scenario reduction vs no re-planning</PanelTitle>
                <ReductionChart key={setting} edges={ev.data.distribution[setting].edges}
                  methods={ev.data.distribution[setting].methods} order={PHASE10.slice(1)} />
                <p className="mt-2 text-xs text-ink-dim">Box: quartiles and median (dot = mean); whiskers: 1.5 x IQR; faint bars: histogram of scenarios.</p>
              </Panel>
            )}

            <Panel>
              <PanelTitle hint="pre-registered in docs/ASSUMPTIONS.md 43-46">ML integration variants (Phase 10b)</PanelTitle>
              <VariantsTable conclusion={ev.data.conclusion}
                settings={{
                  deterministic: { variants_vs_dynamic: s.settings.deterministic.variants_vs_dynamic, methods: Object.fromEntries(Object.entries(s.settings.deterministic.methods).map(([m, v]) => [m, v.weighted_delay])) },
                  robustness: { variants_vs_dynamic: s.settings.robustness.variants_vs_dynamic, methods: Object.fromEntries(Object.entries(s.settings.robustness.methods).map(([m, v]) => [m, v.weighted_delay])) },
                }} />
            </Panel>

            <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
              <SolverPanel s={s} totals={ev.data.solver_totals} />
              <LimitsPanel s={s} />
            </div>
          </>
        )}
      </ResultsGate>
    </motion.div>
  )
}

function LiveSession() {
  const minute = useSim((st) => st.minute)
  const scenario = useScenario()
  const state = useStateAt(minute)
  if (!state.data) return null
  return (
    <motion.section variants={fadeUp} className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Radio className="h-4 w-4 text-signal-green" aria-hidden />
        <h2 className="text-lg font-semibold">Live session</h2>
        <span className="text-sm text-ink-muted">
          current scenario at <span className="font-mono text-ink">{fmt(minute)}</span>
          {scenario.data && <> · {scenario.data.timetable === 'full_day' ? 'full day' : 'reference'} timetable · {scenario.data.events.length} events
            {scenario.data.applied_recommendation ? ` · plan ${scenario.data.applied_recommendation} accepted` : ' · no plan accepted'}</>}
        </span>
      </div>
      <KpiStrip kpis={state.data.kpis} history={[state.data.kpis]} />
    </motion.section>
  )
}

function SetupStrip({ s }: { s: EvalSummary }) {
  const items = [
    ['Scenarios', `${s.config.scenarios}`, `seed ${s.config.seed}, ${s.scenarios.trains} trains`],
    ['Disruptions', `${s.scenarios.disruptions_total}`, Object.entries(s.scenarios.types).map(([k, v]) => `${v} ${k.toLowerCase().replace('_', ' ')}`).join(', ')],
    ['Overlap with training', `${s.scenarios.overlap_with_training ?? '-'}`, `of ${s.scenarios.training_runs} training scenarios`],
    ['Violations', `${s.violations}`, `in ${s.replays_checked} replays`],
  ]
  return (
    <motion.div variants={staggerContainer()} className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      {items.map(([k, v, foot]) => (
        <motion.div key={k} variants={fadeUp} className="glass px-4 py-3">
          <p className="text-sm text-ink-muted">{k}</p>
          <p className="mt-1 font-mono text-3xl font-semibold">{v}</p>
          <p className="mt-1 text-xs text-ink-dim">{foot}</p>
        </motion.div>
      ))}
    </motion.div>
  )
}

function MethodsTable({ s, setting }: { s: EvalSummary; setting: EvalSettingName }) {
  const st = s.settings[setting]
  return (
    <div className="mt-6 overflow-x-auto">
      <table className="w-full min-w-[64rem] text-sm">
        <thead>
          <tr className="border-b border-line/15 text-left text-xs uppercase tracking-wider text-ink-dim">
            <th className="py-2 pr-3 font-medium">Method</th>
            {TABLE_METRICS.map((k) => <th key={k} className="px-2 py-2 font-medium">{METRIC_LABEL[k].label}{METRIC_LABEL[k].unit ? ` (${METRIC_LABEL[k].unit})` : ''}</th>)}
            <th className="px-2 py-2 font-medium">vs no re-planning (weighted): W / T / L, mean diff [CI]</th>
          </tr>
        </thead>
        <tbody>
          {PHASE10.map((m) => {
            const p = st.paired_vs_no_replanning[m]?.weighted_delay
            return (
              <tr key={m} className="border-b border-line/10 align-top">
                <td className={cn('py-2 pr-3', BASELINES.has(m) ? 'text-ink-muted' : 'text-ink')}>{label(m)}</td>
                {TABLE_METRICS.map((k) => {
                  const d = st.methods[m][k]
                  const dg = METRIC_LABEL[k].digits
                  return (
                    <td key={k} className="px-2 py-2 font-mono">
                      <span className="text-ink">{f(d.mean, dg)}</span> <span className="text-ink-dim">{ci(d.mean_ci, dg)}</span>
                      <div className="text-xs text-ink-dim">median {f(d.median, dg)}</div>
                    </td>
                  )
                })}
                <td className="px-2 py-2 font-mono">
                  {p ? (
                    <>
                      {p.wins} / {p.ties} / {p.losses} · {signed(p.mean_diff)} {ci(p.mean_diff_ci)}
                      <div>{p.significant ? <span className="text-xs text-signal-green">significant</span> : <span className="text-xs font-semibold text-signal-amber">not significant</span>}</div>
                    </>
                  ) : <span className="text-ink-dim">reference</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-ink-dim">
        Mean [95% bootstrap CI, {s.config.bootstrap} resamples] per scenario. Paired: diff = method - no re-planning per scenario;
        significant only when the CI of the mean difference excludes 0.
      </p>
    </div>
  )
}

function SolverPanel({ s, totals }: { s: EvalSummary; totals: { phase10: { solves: number; optimal: number; solve_s_mean: number; solve_s_max: number }; variants_10b: { solves: number; optimal: number } } | null }) {
  const g = s.single_shot_guarantee
  return (
    <Panel>
      <PanelTitle hint="CP-SAT, 1 worker, 10 s limit">Solver</PanelTitle>
      {totals && (
        <div className="flex flex-wrap items-end gap-6">
          <div>
            <p className="font-mono text-4xl font-bold text-signal-green">{totals.phase10.optimal} / {totals.phase10.solves}</p>
            <p className="text-sm text-ink-muted">OPTIMAL solves (Phase 10 methods)</p>
          </div>
          <div>
            <p className="font-mono text-2xl font-semibold">{f(totals.phase10.solve_s_mean * 1000, 0)} ms</p>
            <p className="text-sm text-ink-muted">mean solve time</p>
          </div>
          <div>
            <p className="font-mono text-2xl font-semibold">{f(totals.phase10.solve_s_max * 1000, 0)} ms</p>
            <p className="text-sm text-ink-muted">max solve time</p>
          </div>
          {totals.variants_10b.solves > 0 && (
            <p className="text-sm text-ink-muted">Phase 10b variants: {totals.variants_10b.optimal} / {totals.variants_10b.solves} OPTIMAL</p>
          )}
        </div>
      )}
      <table className="mt-4 w-full text-sm">
        <thead><tr className="border-b border-line/15 text-left text-xs uppercase tracking-wider text-ink-dim">
          <th className="py-1.5 font-medium">Method</th><th className="font-medium">Solves</th><th className="font-medium">OPTIMAL</th><th className="font-medium">FEASIBLE</th><th className="font-medium">mean / p95 / max (ms)</th>
        </tr></thead>
        <tbody>
          {Object.entries(s.solver).map(([m, v]) => (
            <tr key={m} className="border-b border-line/10 font-mono">
              <td className="py-1.5 font-sans">{label(m)}</td><td>{v.solves}</td><td>{v.optimal}</td><td>{v.feasible}</td>
              <td>{f(v.solve_s_mean * 1000, 0)} / {f(v.solve_s_p95 * 1000, 0)} / {f(v.solve_s_max * 1000, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-sm text-ink-muted">
        Single-shot never worse than no re-planning on the events known when it solved: {g.worse_on_events_known_at_solve.length} exceptions
        in {g.optimal_single_shots} OPTIMAL solves. On the full replay (later disruptions included) it was worse in {g.worse_on_full_replay.length}
        {g.worse_on_full_replay.length ? ` (${g.worse_on_full_replay.join(', ')})` : ''}.
      </p>
    </Panel>
  )
}

function LimitsPanel({ s }: { s: EvalSummary }) {
  const limits = [
    `Simulated: one sample corridor (${s.scenarios.trains} trains), synthetic disruptions and assumed variability. Nothing here measures real railway operations.`,
    `Robustness replays keep each plan frozen; in use RailOpt would re-plan again as actual times drift.`,
    'Waits include planned holds: a held train counts as waiting.',
    'Priority dispatch only differs from first come, first served when two trains wait for the same section at once.',
    'RailOpt advises a human controller; it controls no trains or signals.',
  ]
  return (
    <Panel className="border border-signal-amber/25">
      <PanelTitle hint="read before quoting a number">
        <span className="inline-flex items-center gap-2"><AlertTriangle className="h-5 w-5 text-signal-amber" aria-hidden /> Limits</span>
      </PanelTitle>
      <ul className="space-y-2 text-sm text-ink">
        {limits.map((l) => <li key={l} className="flex gap-2"><Cpu className="mt-0.5 h-4 w-4 shrink-0 text-ink-dim" aria-hidden />{l}</li>)}
      </ul>
    </Panel>
  )
}
