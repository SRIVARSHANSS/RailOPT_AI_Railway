import { motion } from 'framer-motion'
import { Lightbulb } from 'lucide-react'
import type { Conclusion, Desc, EvalSettingName, Paired } from '../../api/types'
import { SignalBadge } from '../../components/ui/Badges'
import { cn } from '../../lib/cn'
import { fadeUp } from '../../lib/motion'
import { ci, f, label, signed } from './format'

type SettingData = { variants_vs_dynamic: Record<string, Record<string, Paired>>; methods: Record<string, Desc> }

/** Phase 10b "ML integration variants" (pre-registered) and the plain conclusion, all from the API. */
export function VariantsTable({ settings, conclusion }: { settings: Record<EvalSettingName, SettingData>; conclusion: Conclusion | null }) {
  const variants = Object.keys(settings.deterministic.variants_vs_dynamic)
  return (
    <motion.div variants={fadeUp} className="space-y-4">
      {conclusion && (
        <div className="flex items-start gap-3 rounded-xl border border-signal-violet/40 bg-signal-violet/10 p-4">
          <Lightbulb className="mt-0.5 h-5 w-5 shrink-0 text-signal-violet" aria-hidden />
          <p className="text-lg font-semibold text-ink">{conclusion.text}</p>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[46rem] text-sm">
          <thead>
            <tr className="border-b border-line/15 text-left text-xs uppercase tracking-wider text-ink-dim">
              <th className="py-2 pr-3 font-medium">Variant (vs RailOpt dynamic, no ML)</th>
              {(['deterministic', 'robustness'] as const).map((s) => (
                <th key={s} className="px-3 py-2 font-medium" colSpan={2}>{s}: weighted delay diff [95% CI]</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-line/10">
              <td className="py-2 pr-3 text-ink-muted">{label('DYNAMIC')} (reference)</td>
              {(['deterministic', 'robustness'] as const).map((s) => (
                <td key={s} className="px-3 py-2 font-mono text-ink-muted" colSpan={2}>
                  mean {f(settings[s].methods.DYNAMIC.mean)} {ci(settings[s].methods.DYNAMIC.mean_ci)}
                </td>
              ))}
            </tr>
            {variants.map((m) => (
              <tr key={m} className="border-b border-line/10">
                <td className="py-2 pr-3 text-ink">
                  {label(m)}
                  {conclusion?.preregistered.includes(m) && <span className="ml-2 text-xs text-signal-violet">pre-registered</span>}
                </td>
                {(['deterministic', 'robustness'] as const).map((s) => {
                  const p = settings[s].variants_vs_dynamic[m].weighted_delay
                  const tone = p.significant ? (p.mean_diff < 0 ? 'success' : 'warning') : 'info'
                  return [
                    <td key={`${s}-v`} className="px-3 py-2 font-mono">
                      <span className={cn(p.significant && p.mean_diff > 0 && 'text-signal-amber', p.significant && p.mean_diff < 0 && 'text-signal-green')}>
                        {signed(p.mean_diff, 2)} {ci(p.mean_diff_ci, 2)}
                      </span>
                      <span className="ml-2 text-xs text-ink-dim">W/T/L {p.wins}/{p.ties}/{p.losses}</span>
                    </td>,
                    <td key={`${s}-s`} className="px-3 py-2">
                      <SignalBadge tone={tone}>{p.significant ? (p.mean_diff < 0 ? 'better' : 'worse') : 'not significant'}</SignalBadge>
                    </td>,
                  ]
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-dim">Diff = variant minus dynamic per scenario; negative = less delay. Significant only when the 95% bootstrap CI excludes 0.</p>
    </motion.div>
  )
}
