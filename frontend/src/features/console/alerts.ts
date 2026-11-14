import type { ConflictsAt, OptimizeResult } from '../../api/types'

export type Alert = {
  key: string
  level: 'CRITICAL' | 'WARNING' | 'RECOMMENDATION' | 'RESOLVED'
  title: string
  detail: string
  section_id: string | null
  trains: string[]
  struck?: string // the risk text shown struck through (resolved items)
}

/** Alerts built only from API fields: detector conflicts, ML watchlist, last optimizer run. */
export function buildAlerts(c: ConflictsAt | undefined, opt: OptimizeResult | null, decided: Record<string, string>): Alert[] {
  const out: Alert[] = []
  const rec = opt?.recommendation
  if (rec && !decided[rec.recommendation_id]) {
    out.push({
      key: `rec-${rec.recommendation_id}`, level: 'RECOMMENDATION',
      title: `Recommendation ${rec.recommendation_id}: ${rec.strategy}`,
      detail: `${rec.actions.join('; ') || 'no action needed'} - weighted delay ${rec.weighted_delay} (${rec.explanation.delta_weighted_delay >= 0 ? '+' : ''}${rec.explanation.delta_weighted_delay})`,
      section_id: null, trains: Object.keys(rec.delays).filter((t) => rec.actions.some((a) => a.includes(t))),
    })
  }
  for (const k of c?.conflicts ?? []) {
    out.push({
      key: `c-${k.conflict_id}-${k.section_id}-${k.later_train}`, level: k.severity,
      title: `${k.severity}: ${k.later_train} ${k.conflict_type.toLowerCase()} on ${k.section_id}`,
      detail: k.conflict_type === 'CLOSURE'
        ? `Planned entry ${k.window_start}, section closed until ${k.window_end} (${k.minutes_short} min short)`
        : `Planned entry ${k.window_start}, ${k.earlier_train} holds it until ${k.window_end} (${k.minutes_short} min short, in ${k.time_to_conflict_min} min)` +
          (k.prediction ? ` - model ${Math.round(k.prediction.conflict_probability * 100)}%` : ''),
      section_id: k.section_id, trains: [k.earlier_train, k.later_train].filter(Boolean) as string[],
    })
  }
  for (const w of c?.ml_watchlist ?? []) {
    out.push({
      key: `ml-${w.train_id}-${w.section_id}`, level: w.resolved_by_plan ? 'RESOLVED' : 'WARNING',
      title: w.resolved_by_plan ? 'Risk resolved by accepted plan' : `AI watch: ${w.train_id} on ${w.section_id}`,
      struck: w.resolved_by_plan ? `AI watch: ${w.train_id} on ${w.section_id}, model ${w.conflict_probability.toFixed(2)}` : undefined,
      detail: w.resolved_by_plan
        ? `In the accepted plan's replay ${w.train_id} waits ${w.plan_wait_min ?? 0} min before this trip.`
        : `The rules miss it; the model flags ${w.conflict_probability.toFixed(2)} (threshold ${w.threshold.toFixed(2)}).` +
          (w.top_drivers[0] ? ` Top driver: ${w.top_drivers[0].feature} ${w.top_drivers[0].direction} the risk.` : ''),
      section_id: w.section_id, trains: [w.train_id],
    })
  }
  return out
}

