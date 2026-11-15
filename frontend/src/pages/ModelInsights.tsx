import { motion } from 'framer-motion'
import { BrainCircuit, Database, Scale } from 'lucide-react'
import { useState } from 'react'
import { useModelResults } from '../api/hooks'
import type { ClsScores, ModelMetrics, RegScores } from '../api/types'
import { SignalBadge } from '../components/ui/Badges'
import { Panel, PanelTitle } from '../components/ui/Panel'
import { Tabs } from '../components/ui/Tabs'
import { BarChart } from '../features/results/BarChart'
import { f, pct } from '../features/results/format'
import { ResultsGate } from '../features/results/ResultsGate'
import { VariantsTable } from '../features/results/VariantsTable'
import { cn } from '../lib/cn'
import { fadeUp, staggerContainer } from '../lib/motion'

const NAME: Record<string, string> = {
  carry_known_delay: 'Carry known delay', deterministic_projection: 'Deterministic projection (simulator)',
  linear_regression: 'Linear regression', logistic_regression: 'Logistic regression',
  rule_flags_conflict: 'Rule-based detector', random_forest: 'Random forest', xgboost: 'XGBoost',
}
const nm = (k: string) => NAME[k] ?? k

/** Model Insights: stored Phase 4 metrics and SHAP (GET /api/model). SIMULATED. */
export function ModelInsights() {
  const q = useModelResults()
  const d = q.data
  const m = d?.metrics
  return (
    <motion.div className="mx-auto max-w-[96rem] space-y-6" variants={staggerContainer()} initial="hidden" animate="show">
      <motion.div variants={fadeUp} className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-signal-violet">Model insights</p>
          <h1 className="text-3xl font-bold xl:text-4xl">What the models learned, against their baselines</h1>
          <p className="mt-2 max-w-3xl text-ink-muted">
            Stored results of <code className="font-mono text-ink">{d?.command ?? 'python -m ml.train'}</code>, checked against the model files on disk.
            Trained and tested on simulated runs only.
          </p>
        </div>
        <SignalBadge tone="info">SIMULATED</SignalBadge>
      </motion.div>

      <ResultsGate loading={q.isLoading} error={q.isError} status={d?.status} reasons={d?.reasons ?? []} command={d?.command ?? ''} what="model results">
        {m && d && (
          <>
            <DataStrip m={m} datasetCheck={d.dataset_check} />
            <HeadToHead m={m} />
            <div className="grid gap-6 2xl:grid-cols-2">
              <DelayTable m={m} />
              <ConflictTable m={m} />
            </div>
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
              <ShapPanel fi={d.feature_importance} m={m} />
              <div className="space-y-6">
                <AblationPanel m={m} />
                <SmallDataPanel m={m} />
              </div>
            </div>
            {d.evaluation && (
              <Panel>
                <PanelTitle hint={d.evaluation.status === 'ok' ? 'from the Phase 10/10b evaluation' : 'evaluation results are outdated - rerun'}>
                  Does ML risk improve the optimizer's plans?
                </PanelTitle>
                <VariantsTable settings={d.evaluation.settings} conclusion={d.evaluation.conclusion} />
              </Panel>
            )}
          </>
        )}
      </ResultsGate>
    </motion.div>
  )
}

function DataStrip({ m, datasetCheck }: { m: ModelMetrics; datasetCheck: string | null }) {
  const sp = m.data.split
  const items: [string, string, string][] = [
    ['Rows', `${m.data.rows}`, `from ${m.data.runs} simulated runs (seed ${m.seed})`],
    ['Split by run', `${sp.train.runs} / ${sp.val.runs} / ${sp.test.runs}`, 'train / validation / test runs'],
    ['Conflict rate (test)', pct(m.conflict.positive_rate.test), 'share of rows with a wait before the section'],
    ['Dataset check', datasetCheck === 'verified' ? 'verified' : 'model files',
      datasetCheck === 'verified' ? 'training_rows.csv and model files match metrics.json' : datasetCheck ?? '-'],
  ]
  return (
    <motion.div variants={staggerContainer()} className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      {items.map(([k, v, foot]) => (
        <motion.div key={k} variants={fadeUp} className="glass px-4 py-3">
          <p className="text-sm text-ink-muted">{k}</p>
          <p className="mt-1 font-mono text-2xl font-semibold">{v}</p>
          <p className="mt-1 text-xs text-ink-dim">{foot}</p>
        </motion.div>
      ))}
    </motion.div>
  )
}

function HeadToHead({ m }: { m: ModelMetrics }) {
  const rule = m.conflict.baselines.rule_flags_conflict.test
  const op = m.conflict.operating_points.equal_to_rule_precision
  return (
    <Panel>
      <PanelTitle hint={`threshold ${f(op.threshold, 3)}: ${op.rule}`}>
        <span className="inline-flex items-center gap-2"><Scale className="h-5 w-5 text-signal-cyan" aria-hidden /> Head-to-head at equal precision (test)</span>
      </PanelTitle>
      <div className="grid items-center gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div>
          <p className="text-ink-muted">At the rule's precision, the conflict model finds</p>
          <p className="mt-1 font-mono text-5xl font-bold text-signal-cyan">{f(op.test.recall, 3)}</p>
          <p className="text-ink-muted">of real conflicts, against <span className="font-mono text-ink">{f(rule.recall, 3)}</span> for the rule-based detector.</p>
          <p className="mt-2 text-sm text-ink-dim">Precision: model {f(op.test.precision, 3)}, rule {f(rule.precision, 3)}.</p>
        </div>
        <BarChart ariaLabel="Test recall at equal precision: model vs rule (simulated)" digits={3} labelWidth={190}
          bars={[
            { key: 'rule', label: 'Rule-based detector', value: rule.recall, tone: 'baseline' },
            { key: 'model', label: `${nm(m.conflict.best_model)} (equal precision)`, value: op.test.recall, tone: 'ai' },
          ]} />
      </div>
    </Panel>
  )
}

function DelayTable({ m }: { m: ModelMetrics }) {
  const rows: [string, 'baseline' | 'model', { val: RegScores; test: RegScores }][] = [
    ...Object.entries(m.delay.baselines).map(([k, v]) => [k, 'baseline', v] as [string, 'baseline', typeof v]),
    ...Object.entries(m.delay.models).map(([k, v]) => [k, 'model', v] as [string, 'model', typeof v]),
  ]
  return (
    <Panel>
      <PanelTitle hint={`best: ${nm(m.delay.best_model)} (${m.delay.selected_by})`}>Delay at destination (minutes)</PanelTitle>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[34rem] text-sm">
          <thead><tr className="border-b border-line/15 text-left text-xs uppercase tracking-wider text-ink-dim">
            <th className="py-2 pr-2 font-medium">Method</th><th className="font-medium">Val MAE</th><th className="font-medium">Val R²</th>
            <th className="font-medium">Test MAE</th><th className="font-medium">Test RMSE</th><th className="font-medium">Test R²</th>
          </tr></thead>
          <tbody>
            {rows.map(([k, kind, v]) => (
              <tr key={k} className={cn('border-b border-line/10 font-mono', k === m.delay.best_model && 'bg-signal-cyan/[0.07]')}>
                <td className="py-2 pr-2 font-sans">{nm(k)} <span className="ml-1 text-xs text-ink-dim">{kind}</span></td>
                <td>{f(v.val.mae, 3)}</td><td>{f(v.val.r2, 3)}</td><td>{f(v.test.mae, 3)}</td><td>{f(v.test.rmse, 3)}</td><td>{f(v.test.r2, 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

function ConflictTable({ m }: { m: ModelMetrics }) {
  const rows: [string, 'baseline' | 'model', { val: ClsScores; test: ClsScores }][] = [
    ...Object.entries(m.conflict.baselines).map(([k, v]) => [k, 'baseline', v] as [string, 'baseline', typeof v]),
    ...Object.entries(m.conflict.models).map(([k, v]) => [k, 'model', v] as [string, 'model', typeof v]),
  ]
  return (
    <Panel>
      <PanelTitle hint={`best: ${nm(m.conflict.best_model)} (${m.conflict.selected_by}); thresholds at validation recall >= 0.80`}>Conflict before the section</PanelTitle>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[38rem] text-sm">
          <thead><tr className="border-b border-line/15 text-left text-xs uppercase tracking-wider text-ink-dim">
            <th className="py-2 pr-2 font-medium">Method</th><th className="font-medium">Threshold</th><th className="font-medium">Val PR-AUC</th>
            <th className="font-medium">Test P</th><th className="font-medium">Test R</th><th className="font-medium">Test F1</th><th className="font-medium">Test PR-AUC</th>
          </tr></thead>
          <tbody>
            {rows.map(([k, kind, v]) => (
              <tr key={k} className={cn('border-b border-line/10 font-mono', k === m.conflict.best_model && 'bg-signal-cyan/[0.07]')}>
                <td className="py-2 pr-2 font-sans">{nm(k)} <span className="ml-1 text-xs text-ink-dim">{kind}</span></td>
                <td>{v.test.threshold === null ? 'n/a' : f(v.test.threshold, 3)}</td><td>{f(v.val.pr_auc, 3)}</td>
                <td>{f(v.test.precision, 3)}</td><td>{f(v.test.recall, 3)}</td><td>{f(v.test.f1, 3)}</td><td>{f(v.test.pr_auc, 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-ink-dim">The rule is a 0/1 flag, so its PR-AUC is the average precision of that flag.</p>
    </Panel>
  )
}

function AblationPanel({ m }: { m: ModelMetrics }) {
  const a = m.conflict.ablation
  const ops = Object.keys(a.with_rule_flag)
  return (
    <Panel>
      <PanelTitle hint={`${nm(a.model)}, same parameters`}>Ablation: with vs without the rule flag</PanelTitle>
      <table className="w-full text-sm">
        <thead><tr className="border-b border-line/15 text-left text-xs uppercase tracking-wider text-ink-dim">
          <th className="py-2 font-medium">Variant</th><th className="font-medium">Operating point</th><th className="font-medium">Test P</th><th className="font-medium">Test R</th><th className="font-medium">Test PR-AUC</th>
        </tr></thead>
        <tbody>
          {(['with_rule_flag', 'without_rule_flag'] as const).flatMap((v) => ops.map((op) => (
            <tr key={`${v}-${op}`} className="border-b border-line/10 font-mono">
              <td className="py-1.5 font-sans">{v === 'with_rule_flag' ? 'with rule flag' : 'without'}</td>
              <td className="font-sans text-ink-muted">{op.replace(/_/g, ' ')}</td>
              <td>{f(a[v][op].test.precision, 3)}</td><td>{f(a[v][op].test.recall, 3)}</td><td>{f(a[v][op].test.pr_auc, 3)}</td>
            </tr>
          )))}
        </tbody>
      </table>
    </Panel>
  )
}

function SmallDataPanel({ m }: { m: ModelMetrics }) {
  const s = m.small_data_check
  const beat = s.model_val_recall_at_rule_precision > s.rule_val_recall
  return (
    <Panel>
      <PanelTitle hint={`${s.runs} of ${m.data.runs_generated} runs, ${s.n_iter_per_model} configurations per model`}>
        <span className="inline-flex items-center gap-2"><Database className="h-5 w-5 text-signal-amber" aria-hidden /> With less data</span>
      </PanelTitle>
      <p className="text-ink">
        Trained on {s.runs} runs with minimal tuning, the model {beat ? 'beat' : <strong>did not beat</strong>} the rule: validation recall
        <span className="font-mono"> {f(s.model_val_recall_at_rule_precision, 3)}</span> vs <span className="font-mono">{f(s.rule_val_recall, 3)}</span> at
        the rule's precision (<span className="font-mono">{f(s.rule_val_precision, 3)}</span>). The result depends on data volume.
      </p>
    </Panel>
  )
}

function ShapPanel({ fi, m }: { fi: { model: 'delay' | 'conflict'; feature: string; mean_abs_shap: number }[]; m: ModelMetrics }) {
  const [which, setWhich] = useState<'conflict' | 'delay'>('conflict')
  const rows = fi.filter((r) => r.model === which).sort((a, b) => b.mean_abs_shap - a.mean_abs_shap)
  const units = which === 'delay' ? 'minutes' : `raw model output (${m.conflict.best_model === 'xgboost' ? 'log-odds' : 'probability'})`
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="inline-flex items-center gap-2 text-xl font-semibold"><BrainCircuit className="h-5 w-5 text-signal-violet" aria-hidden /> Global SHAP importance</h2>
        <Tabs value={which} onValueChange={(v) => setWhich(v as 'conflict' | 'delay')} label="SHAP model"
          items={[{ value: 'conflict', label: 'Conflict model' }, { value: 'delay', label: 'Delay model' }]}>{null}</Tabs>
      </div>
      <p className="mt-1 text-sm text-ink-muted">Mean |SHAP| over {m.shap_rows} validation rows, in {units}.</p>
      <div className="mt-3">
        <BarChart key={which} ariaLabel={`Global SHAP importance, ${which} model (simulated)`} digits={3} labelWidth={260}
          bars={rows.map((r) => ({ key: r.feature, label: r.feature, value: r.mean_abs_shap, tone: 'ml' }))} />
      </div>
    </Panel>
  )
}
